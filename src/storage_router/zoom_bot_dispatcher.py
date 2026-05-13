"""Per-meeting Zoom-bot subprocess lifecycle.

Mirrors the shape of ``live_extraction.start_for`` / ``stop_for`` but holds
``subprocess.Popen`` handles in a module-global dict keyed by ``meeting_id``,
capped at ``settings.zoom_bot_pool_size`` (default 3).

Slice 1 deliberately keeps ``dispatch()`` shape-complete but does NOT yet
spawn ``bot/bot.py``. The real ``Popen(...)`` call lands in slice 4; in
slice 1 the dispatcher only verifies credentials, enforces the pool cap,
and registers a Popen handle via the injectable ``spawner`` seam so the
tests can pass a mock and assert the env hand-off without ever forking.
"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import Callable, Optional

from storage_router.config import settings

logger = logging.getLogger(__name__)

# meeting_id -> Popen handle. Module-global; mirrors live_extraction._TASKS.
_PROCESSES: dict[str, subprocess.Popen] = {}


class BotPoolFull(RuntimeError):
    """Raised when ``dispatch()`` would exceed ``zoom_bot_pool_size``."""


def _require_zoom_creds() -> None:
    """Raise ``RuntimeError`` if any of the four Marketplace creds are absent.

    Routes map this to HTTP 503 with the documented payload. NEVER call at
    module import — only at dispatch / JWT-signing time.
    """
    missing = [
        name
        for name, value in (
            ("ZOOM_SDK_KEY", settings.zoom_sdk_key),
            ("ZOOM_SDK_SECRET", settings.zoom_sdk_secret),
            ("ZOOM_OAUTH_CLIENT_ID", settings.zoom_oauth_client_id),
            ("ZOOM_OAUTH_CLIENT_SECRET", settings.zoom_oauth_client_secret),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Zoom Marketplace credentials not configured — set "
            "ZOOM_SDK_KEY, ZOOM_SDK_SECRET, ZOOM_OAUTH_CLIENT_ID, "
            "ZOOM_OAUTH_CLIENT_SECRET in the environment before "
            "dispatching a bot."
        )


def _reap_dead() -> None:
    """Drop entries whose Popen has exited so the cap stays honest."""
    dead = [mid for mid, p in _PROCESSES.items() if p.poll() is not None]
    for mid in dead:
        _PROCESSES.pop(mid, None)


def dispatch(
    meeting_id: str,
    zoom_url: str,
    *,
    storage_router_url: str,
    spawner: Optional[Callable[[list[str], dict[str, str]], subprocess.Popen]] = None,
) -> subprocess.Popen:
    """Spawn (or, in slice 1 tests, mock-spawn) a bot subprocess for one meeting.

    Order: creds → cap → spawn. Re-dispatching the same ``meeting_id``
    while a prior handle is still alive returns the existing handle (no
    double-spawn); a dead handle for the same id is replaced silently.

    The ``spawner`` seam exists so slice-1 tests can pass a Popen factory
    that returns a mock; slice 4 wires the production spawner that
    actually launches ``bot/bot.py``.
    """
    _require_zoom_creds()
    _reap_dead()

    existing = _PROCESSES.get(meeting_id)
    if existing is not None and existing.poll() is None:
        return existing

    if len(_PROCESSES) >= settings.zoom_bot_pool_size:
        raise BotPoolFull(
            f"bot pool full ({settings.zoom_bot_pool_size} active); "
            "wait for a meeting to end or raise ZOOM_BOT_POOL_SIZE."
        )

    cmd = ["python", str(settings.zoom_bot_dir / "bot.py")]
    env = {
        **os.environ,
        "MEETING_ID": meeting_id,
        "ZOOM_URL": zoom_url,
        "STORAGE_ROUTER_URL": storage_router_url,
        "ZOOM_SDK_KEY": settings.zoom_sdk_key,
        "ZOOM_BOT_ACCOUNT_EMAIL": settings.zoom_bot_account_email,
    }

    if spawner is None:
        spawner = _default_spawner

    proc = spawner(cmd, env)
    _PROCESSES[meeting_id] = proc
    logger.info("zoom-bot.dispatch meeting=%s pid=%s", meeting_id, proc.pid)
    return proc


def _default_spawner(cmd: list[str], env: dict[str, str]) -> subprocess.Popen:
    """Real Popen spawner. Slice 4 covers the lifecycle tests."""
    return subprocess.Popen(cmd, env=env)


def terminate(meeting_id: str, *, timeout_s: float = 5.0) -> None:
    """SIGTERM then SIGKILL the bot for ``meeting_id``. No-op if absent."""
    proc = _PROCESSES.pop(meeting_id, None)
    if proc is None:
        return
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout_s)


def is_running(meeting_id: str) -> bool:
    """Test helper: did ``dispatch()`` install a live handle for this id?"""
    proc = _PROCESSES.get(meeting_id)
    return proc is not None and proc.poll() is None


def active_count() -> int:
    """Number of currently-alive bot subprocesses."""
    _reap_dead()
    return len(_PROCESSES)


def _reset_for_tests() -> None:
    """Test-only: drop all tracked handles. Does NOT kill the underlying processes."""
    _PROCESSES.clear()


__all__ = [
    "BotPoolFull",
    "_require_zoom_creds",
    "_reset_for_tests",
    "active_count",
    "dispatch",
    "is_running",
    "terminate",
]
