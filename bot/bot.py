#!/usr/bin/env python3
"""Hermes Zoom bot — Python orchestrator (Slice 3).

Spawned by ``storage_router.zoom_bot_dispatcher`` as a child process
with these env vars:

    MEETING_ID            — the storage-router's meeting_id (target of uploads).
    ZOOM_URL              — the Zoom join URL (passed through to zoom-bot.js).
    STORAGE_ROUTER_URL    — base URL the bot calls back for JWT + chunks + end.
    ZOOM_BOT_ACCOUNT_EMAIL — informational only (used as the bot's display name suffix).

The orchestrator:

1. Creates a per-meeting PulseAudio null-sink named ``BotSink_<meeting_id>``
   so concurrent bots can't cross-contaminate.
2. Spawns ``node zoom-bot.js`` (Puppeteer → headless Chromium → Zoom Web SDK).
3. Spawns ``ffmpeg`` to slice the sink monitor into 10-second WebM/Opus chunks.
4. Watches the chunk directory and POSTs each new file to
   ``${STORAGE_ROUTER_URL}/api/live-meetings/${MEETING_ID}/audio-chunk``.
5. On SIGTERM, on zoom-bot.js exit (Zoom emits onMeetingEnd), or on
   ffmpeg exit, calls ``POST /api/live-meetings/${MEETING_ID}/end`` and
   tears down the sink + child processes.

Slice 3 makes the orchestrator standalone-runnable (no dispatcher
required — the user can ``export MEETING_ID=... ZOOM_URL=... && python
bot.py`` for the §F smoke test in the plan). Slice 4 wires the
dispatcher to spawn this script automatically.

This module avoids 3rd-party Python deps (no requests / aiohttp): the
stdlib ``urllib`` handles the chunk upload and the ``/end`` POST. The
only out-of-process tools we shell out to are ``pactl``, ``node``,
and ``ffmpeg`` — all expected to be available on the pod (see README).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes-zoom-bot")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


class BotConfig:
    """Captured-at-startup env. Constructed by the orchestrator and the tests."""

    def __init__(
        self,
        *,
        meeting_id: str,
        zoom_url: str,
        storage_router_url: str,
        bot_dir: Path,
        chunk_dir: Path,
        bot_account_email: str = "",
        chunk_seconds: float = 10.0,
        not_admitted_timeout_s: float = 300.0,
    ) -> None:
        self.meeting_id = meeting_id
        self.zoom_url = zoom_url
        self.storage_router_url = storage_router_url.rstrip("/")
        self.bot_dir = bot_dir
        self.chunk_dir = chunk_dir
        self.bot_account_email = bot_account_email
        self.chunk_seconds = chunk_seconds
        self.not_admitted_timeout_s = not_admitted_timeout_s
        self.sink_name = f"BotSink_{meeting_id}"


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        print(f"FATAL: env var {name} is required", file=sys.stderr)
        sys.exit(2)
    return value


def load_config() -> BotConfig:
    """Build a ``BotConfig`` from the process env."""
    meeting_id = _require_env("MEETING_ID")
    zoom_url = _require_env("ZOOM_URL")
    storage_router_url = _require_env("STORAGE_ROUTER_URL")
    bot_dir = Path(os.environ.get("BOT_DIR", Path(__file__).resolve().parent))
    chunk_dir = Path(
        os.environ.get(
            "BOT_CHUNK_DIR", tempfile.mkdtemp(prefix=f"hermes-bot-{meeting_id}-")
        )
    )
    chunk_dir.mkdir(parents=True, exist_ok=True)
    return BotConfig(
        meeting_id=meeting_id,
        zoom_url=zoom_url,
        storage_router_url=storage_router_url,
        bot_dir=bot_dir,
        chunk_dir=chunk_dir,
        bot_account_email=os.environ.get("ZOOM_BOT_ACCOUNT_EMAIL", ""),
    )


# ---------------------------------------------------------------------------
# Audio sink
# ---------------------------------------------------------------------------


def create_pulse_sink(sink_name: str) -> Optional[str]:
    """Load a null-sink module named ``sink_name``. Return the module ID."""
    if shutil.which("pactl") is None:
        raise RuntimeError(
            "pactl not found on PATH — install pulseaudio on the host."
        )
    result = subprocess.run(
        [
            "pactl",
            "load-module",
            "module-null-sink",
            f"sink_name={sink_name}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def unload_pulse_sink(module_id: Optional[str]) -> None:
    """Best-effort sink unload. Silent no-op when pactl is unavailable."""
    if not module_id or shutil.which("pactl") is None:
        return
    subprocess.run(["pactl", "unload-module", module_id], check=False)


# ---------------------------------------------------------------------------
# Children
# ---------------------------------------------------------------------------


def spawn_node_bot(cfg: BotConfig) -> subprocess.Popen:
    """Launch the Puppeteer driver. Inherits env from the parent."""
    if shutil.which("node") is None:
        raise RuntimeError("node not found on PATH — install Node.js >=18.")
    return subprocess.Popen(
        ["node", str(cfg.bot_dir / "zoom-bot.js")],
        env={
            **os.environ,
            "ZOOM_URL": cfg.zoom_url,
            "MEETING_ID": cfg.meeting_id,
            "STORAGE_ROUTER_URL": cfg.storage_router_url,
            "BOT_SINK_NAME": cfg.sink_name,
            "BOT_DISPLAY_NAME": "Hermes — Note-taking Bot",
        },
    )


def spawn_ffmpeg(cfg: BotConfig) -> subprocess.Popen:
    """ffmpeg captures the sink monitor as numbered WebM/Opus chunks."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH.")
    monitor = f"{cfg.sink_name}.monitor"
    out_pattern = str(cfg.chunk_dir / "chunk-%04d.webm")
    return subprocess.Popen(
        [
            "ffmpeg",
            "-loglevel", "warning",
            "-f", "pulse",
            "-i", monitor,
            "-c:a", "libopus",
            "-f", "segment",
            "-segment_time", str(cfg.chunk_seconds),
            "-reset_timestamps", "1",
            out_pattern,
        ]
    )


# ---------------------------------------------------------------------------
# Upload loop
# ---------------------------------------------------------------------------


def _multipart_body(
    chunk_path: Path,
    *,
    boundary: str = "----hermes-zoom-bot-boundary",
) -> tuple[bytes, str]:
    """Hand-rolled multipart/form-data — avoids a `requests` dependency."""
    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"audio\"; "
        f"filename=\"{chunk_path.name}\"\r\n"
        f"Content-Type: audio/webm\r\n\r\n"
    ).encode("utf-8")
    body += chunk_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


def upload_chunk(cfg: BotConfig, chunk_path: Path) -> int:
    """POST one chunk to the live-meetings audio-chunk endpoint. Returns status."""
    body, content_type = _multipart_body(chunk_path)
    url = (
        f"{cfg.storage_router_url}/api/live-meetings/"
        f"{cfg.meeting_id}/audio-chunk"
    )
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        logger.warning("upload_chunk %s -> %s %s", chunk_path.name, exc.code, exc.reason)
        return exc.code


def call_end(cfg: BotConfig) -> int:
    """Tell the storage-router this meeting is done. Idempotent — re-calling is safe."""
    url = (
        f"{cfg.storage_router_url}/api/live-meetings/"
        f"{cfg.meeting_id}/end"
    )
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        # /end races with finalize — a 409 just means "already ended", that's fine.
        return exc.code
    except urllib.error.URLError as exc:
        logger.warning("call_end network err: %s", exc)
        return 0


def upload_new_chunks(
    cfg: BotConfig, uploaded: set[str]
) -> set[str]:
    """Scan chunk_dir, upload any file not already in ``uploaded``. Mutates and returns."""
    for path in sorted(cfg.chunk_dir.glob("chunk-*.webm")):
        if path.name in uploaded:
            continue
        # ffmpeg writes monotonically; assume the highest-numbered file
        # is still being written and skip the last one until the next
        # iteration so we never upload a half-flushed chunk.
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        # Heuristic: if the file has not been touched for >2 chunk_seconds
        # it's safe to consider closed.
        if time.time() - stat.st_mtime < max(cfg.chunk_seconds, 1.0):
            continue
        status = upload_chunk(cfg, path)
        if 200 <= status < 300:
            uploaded.add(path.name)
    return uploaded


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run(cfg: BotConfig) -> int:
    """Orchestrator main. Returns the exit code."""
    logger.info(
        "starting meeting=%s sink=%s chunk_dir=%s",
        cfg.meeting_id, cfg.sink_name, cfg.chunk_dir,
    )

    sink_module: Optional[str] = None
    node_proc: Optional[subprocess.Popen] = None
    ff_proc: Optional[subprocess.Popen] = None
    uploaded: set[str] = set()
    exit_code = 0
    end_called = False

    def cleanup_once() -> None:
        nonlocal end_called
        if not end_called:
            call_end(cfg)
            end_called = True
        if node_proc is not None and node_proc.poll() is None:
            node_proc.terminate()
        if ff_proc is not None and ff_proc.poll() is None:
            ff_proc.terminate()
        unload_pulse_sink(sink_module)

    def _on_signal(signo, _frame) -> None:
        logger.info("received signal %s — cleaning up", signo)
        cleanup_once()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    try:
        sink_module = create_pulse_sink(cfg.sink_name)
        node_proc = spawn_node_bot(cfg)
        ff_proc = spawn_ffmpeg(cfg)

        started_at = time.time()
        while True:
            time.sleep(1.0)
            uploaded = upload_new_chunks(cfg, uploaded)

            # node_proc exit → zoom-bot.js called onMeetingEnd OR the
            # join failed. Either way we drain the final chunks and call /end.
            node_rc = node_proc.poll() if node_proc else None
            if node_rc is not None:
                logger.info("zoom-bot.js exited rc=%s", node_rc)
                # Flush any straggler chunks before exit.
                time.sleep(cfg.chunk_seconds + 1.0)
                uploaded = upload_new_chunks(cfg, uploaded)
                exit_code = node_rc
                break

            # ffmpeg crashed — surface and bail.
            if ff_proc and ff_proc.poll() is not None:
                logger.warning("ffmpeg exited rc=%s", ff_proc.returncode)
                exit_code = 3
                break

            # Bot still not admitted after the timeout → fail-fast.
            if (
                len(uploaded) == 0
                and (time.time() - started_at) > cfg.not_admitted_timeout_s
            ):
                logger.warning(
                    "no chunks uploaded after %.0fs — host did not admit",
                    cfg.not_admitted_timeout_s,
                )
                exit_code = 2
                break

        return exit_code
    except RuntimeError as exc:
        # Missing pactl / ffmpeg / node surfaces here.
        logger.error("startup failed: %s", exc)
        return 4
    finally:
        cleanup_once()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    cfg = load_config()
    return run(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
