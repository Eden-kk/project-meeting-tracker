"""zoom_bot_dispatcher — shape tests (Slice 1).

Mock Popen so no real bot.py spawns. Verifies:
- _require_zoom_creds() raises with the documented message when any of
  the four credentials is empty.
- dispatch() honors the pool cap (default 3).
- dispatch() hands the right env to the Popen factory.
- terminate() removes the handle and is a silent no-op when absent.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from storage_router import zoom_bot_dispatcher
from storage_router.zoom_bot_dispatcher import (
    BotPoolFull,
    _require_zoom_creds,
    _reset_for_tests,
)


@pytest.fixture(autouse=True)
def _isolate_dispatcher_state() -> None:
    """Each test starts with an empty process registry."""
    _reset_for_tests()
    yield
    _reset_for_tests()


def _fake_proc(*, alive: bool = True, pid: int = 1234) -> MagicMock:
    """Build a Popen-shaped mock that poll() returns None (alive) or 0 (exited)."""
    p = MagicMock(spec=["poll", "terminate", "wait", "kill", "pid"])
    p.poll.return_value = None if alive else 0
    p.pid = pid
    return p


def _set_creds(monkeypatch) -> None:
    """Populate all four Zoom creds on the live settings singleton."""
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings, "zoom_sdk_key", "test-sdk-key"
    )
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings, "zoom_sdk_secret", "test-sdk-secret"
    )
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings, "zoom_oauth_client_id", "test-oauth-id"
    )
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings,
        "zoom_oauth_client_secret",
        "test-oauth-secret",
    )


def test_require_zoom_creds_raises_when_any_missing(monkeypatch) -> None:
    monkeypatch.setattr(zoom_bot_dispatcher.settings, "zoom_sdk_key", "")
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings, "zoom_sdk_secret", "secret"
    )
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings, "zoom_oauth_client_id", "id"
    )
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings, "zoom_oauth_client_secret", "s"
    )
    with pytest.raises(RuntimeError) as excinfo:
        _require_zoom_creds()
    assert "Zoom Marketplace credentials not configured" in str(excinfo.value)
    assert "ZOOM_SDK_KEY" in str(excinfo.value)


def test_require_zoom_creds_passes_when_all_set(monkeypatch) -> None:
    _set_creds(monkeypatch)
    _require_zoom_creds()  # must not raise


def test_dispatch_calls_spawner_with_expected_env(monkeypatch) -> None:
    _set_creds(monkeypatch)
    captured: dict[str, object] = {}

    def spy(cmd: list[str], env: dict[str, str]):
        captured["cmd"] = cmd
        captured["env"] = env
        return _fake_proc()

    zoom_bot_dispatcher.dispatch(
        "m_1",
        "https://zoom.us/j/123",
        storage_router_url="http://router.local",
        spawner=spy,
    )

    assert captured["env"]["MEETING_ID"] == "m_1"
    assert captured["env"]["ZOOM_URL"] == "https://zoom.us/j/123"
    assert captured["env"]["STORAGE_ROUTER_URL"] == "http://router.local"
    assert captured["env"]["ZOOM_SDK_KEY"] == "test-sdk-key"
    # bot.py is the entry point.
    assert captured["cmd"][-1].endswith("bot.py")


def test_dispatch_respects_pool_cap(monkeypatch) -> None:
    _set_creds(monkeypatch)
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings, "zoom_bot_pool_size", 3
    )
    spawner = lambda cmd, env: _fake_proc()
    for i in range(3):
        zoom_bot_dispatcher.dispatch(
            f"m_{i}",
            "https://zoom.us/j/1",
            storage_router_url="http://r",
            spawner=spawner,
        )
    assert zoom_bot_dispatcher.active_count() == 3
    with pytest.raises(BotPoolFull):
        zoom_bot_dispatcher.dispatch(
            "m_4",
            "https://zoom.us/j/1",
            storage_router_url="http://r",
            spawner=spawner,
        )


def test_dispatch_reuses_live_handle_for_same_meeting(monkeypatch) -> None:
    _set_creds(monkeypatch)
    proc = _fake_proc()
    spawner = MagicMock(return_value=proc)
    first = zoom_bot_dispatcher.dispatch(
        "m_dup",
        "https://zoom.us/j/1",
        storage_router_url="http://r",
        spawner=spawner,
    )
    second = zoom_bot_dispatcher.dispatch(
        "m_dup",
        "https://zoom.us/j/1",
        storage_router_url="http://r",
        spawner=spawner,
    )
    assert first is second
    assert spawner.call_count == 1  # second call short-circuited


def test_dispatch_replaces_dead_handle_for_same_meeting(monkeypatch) -> None:
    _set_creds(monkeypatch)
    dead = _fake_proc(alive=False)
    fresh = _fake_proc(alive=True)
    spawner = MagicMock(side_effect=[dead, fresh])
    first = zoom_bot_dispatcher.dispatch(
        "m_revive",
        "https://zoom.us/j/1",
        storage_router_url="http://r",
        spawner=spawner,
    )
    second = zoom_bot_dispatcher.dispatch(
        "m_revive",
        "https://zoom.us/j/1",
        storage_router_url="http://r",
        spawner=spawner,
    )
    assert first is dead
    assert second is fresh
    assert spawner.call_count == 2


def test_dispatch_raises_503_friendly_when_creds_missing(monkeypatch) -> None:
    monkeypatch.setattr(zoom_bot_dispatcher.settings, "zoom_sdk_key", "")
    monkeypatch.setattr(zoom_bot_dispatcher.settings, "zoom_sdk_secret", "")
    monkeypatch.setattr(zoom_bot_dispatcher.settings, "zoom_oauth_client_id", "")
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings, "zoom_oauth_client_secret", ""
    )
    with pytest.raises(RuntimeError, match="not configured"):
        zoom_bot_dispatcher.dispatch(
            "m_x",
            "https://zoom.us/j/1",
            storage_router_url="http://r",
            spawner=lambda *a, **k: _fake_proc(),
        )


def test_terminate_is_noop_when_meeting_absent() -> None:
    zoom_bot_dispatcher.terminate("never_dispatched")  # must not raise


def test_terminate_sigterms_live_handle(monkeypatch) -> None:
    _set_creds(monkeypatch)
    proc = _fake_proc()
    zoom_bot_dispatcher.dispatch(
        "m_term",
        "https://zoom.us/j/1",
        storage_router_url="http://r",
        spawner=lambda cmd, env: proc,
    )
    assert zoom_bot_dispatcher.is_running("m_term")
    zoom_bot_dispatcher.terminate("m_term")
    proc.terminate.assert_called_once()
    assert not zoom_bot_dispatcher.is_running("m_term")


def test_terminate_kills_on_timeout(monkeypatch) -> None:
    import subprocess as _subprocess

    _set_creds(monkeypatch)
    proc = _fake_proc()
    proc.wait.side_effect = [
        _subprocess.TimeoutExpired(cmd="bot.py", timeout=5.0),
        0,
    ]
    zoom_bot_dispatcher.dispatch(
        "m_kill",
        "https://zoom.us/j/1",
        storage_router_url="http://r",
        spawner=lambda cmd, env: proc,
    )
    zoom_bot_dispatcher.terminate("m_kill", timeout_s=0.01)
    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()


# ---------------------------------------------------------------------------
# Route-shape tests (Slice 2). Use the live ASGI client + mock dispatcher.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_route_503_when_creds_missing(client, monkeypatch) -> None:
    monkeypatch.setattr(zoom_bot_dispatcher.settings, "zoom_sdk_key", "")
    monkeypatch.setattr(zoom_bot_dispatcher.settings, "zoom_sdk_secret", "")
    monkeypatch.setattr(zoom_bot_dispatcher.settings, "zoom_oauth_client_id", "")
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings, "zoom_oauth_client_secret", ""
    )
    resp = await client.post(
        "/api/zoom-bot/dispatch",
        json={
            "workspace_id": "ws_dev",
            "zoom_url": "https://zoom.us/j/85412345678",
        },
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "zoom_creds_missing"


@pytest.mark.asyncio
async def test_dispatch_route_400_on_unparseable_url(client, monkeypatch) -> None:
    _set_creds(monkeypatch)
    resp = await client.post(
        "/api/zoom-bot/dispatch",
        json={"workspace_id": "ws_dev", "zoom_url": "https://example.com/foo"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_zoom_url"


@pytest.mark.asyncio
async def test_dispatch_route_creates_meeting_and_calls_dispatcher(
    client, monkeypatch
) -> None:
    _set_creds(monkeypatch)
    captured: dict[str, object] = {}

    def fake_dispatch(meeting_id, zoom_url, *, storage_router_url, spawner=None):
        captured["meeting_id"] = meeting_id
        captured["zoom_url"] = zoom_url
        captured["storage_router_url"] = storage_router_url
        return _fake_proc()

    monkeypatch.setattr(zoom_bot_dispatcher, "dispatch", fake_dispatch)

    resp = await client.post(
        "/api/zoom-bot/dispatch",
        json={
            "workspace_id": "ws_dev",
            "zoom_url": "https://zoom.us/j/85412345678?pwd=abc",
            "title": "Roadmap sync",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["zoom_meeting_number"] == "85412345678"
    assert body["status"] == "live"
    assert captured["meeting_id"] == body["meeting_id"]

    # MeetingRow exists with source_type='zoom_bot' (through the artifact).
    from storage_router.db import SessionLocal
    from storage_router.models.db import ConversationArtifactRow, MeetingRow

    with SessionLocal() as s:
        m = s.get(MeetingRow, body["meeting_id"])
        assert m is not None
        assert m.status == "live"
        assert m.zoom_meeting_number == "85412345678"
        art = s.get(ConversationArtifactRow, m.artifact_id)
        assert art.source_type == "zoom_bot"


def test_require_host_prereqs_raises_when_missing(monkeypatch) -> None:
    """When pactl/ffmpeg/node aren't on PATH, ``dispatch()`` must surface clearly."""
    import shutil as _shutil

    monkeypatch.setattr(_shutil, "which", lambda name: None)
    with pytest.raises(zoom_bot_dispatcher.BotPrereqMissing) as exc:
        zoom_bot_dispatcher._require_host_prereqs()
    assert "pactl" in str(exc.value)
    assert "ffmpeg" in str(exc.value)
    assert "node" in str(exc.value)


def test_require_host_prereqs_passes_when_all_present(monkeypatch) -> None:
    import shutil as _shutil

    monkeypatch.setattr(_shutil, "which", lambda name: "/usr/bin/" + name)
    zoom_bot_dispatcher._require_host_prereqs()  # must not raise


def test_dispatch_skips_prereq_check_when_spawner_injected(monkeypatch) -> None:
    """Tests that pass a mock spawner shouldn't require pactl/ffmpeg/node on PATH."""
    import shutil as _shutil

    _set_creds(monkeypatch)
    monkeypatch.setattr(_shutil, "which", lambda name: None)
    # No raise — the injected spawner bypasses _require_host_prereqs().
    zoom_bot_dispatcher.dispatch(
        "m_inj",
        "https://zoom.us/j/1",
        storage_router_url="http://r",
        spawner=lambda cmd, env: _fake_proc(),
    )


def test_dispatch_calls_prereq_check_when_using_default_spawner(monkeypatch) -> None:
    """When no spawner is injected, missing prereqs become BotPrereqMissing."""
    import shutil as _shutil

    _set_creds(monkeypatch)
    monkeypatch.setattr(_shutil, "which", lambda name: None)
    with pytest.raises(zoom_bot_dispatcher.BotPrereqMissing):
        zoom_bot_dispatcher.dispatch(
            "m_no_prereq",
            "https://zoom.us/j/1",
            storage_router_url="http://r",
        )


@pytest.mark.asyncio
async def test_dispatch_route_returns_bot_pool_full(client, monkeypatch) -> None:
    _set_creds(monkeypatch)

    def fake_dispatch(*a, **kw):
        raise zoom_bot_dispatcher.BotPoolFull("bot pool full (3 active)")

    monkeypatch.setattr(zoom_bot_dispatcher, "dispatch", fake_dispatch)

    resp = await client.post(
        "/api/zoom-bot/dispatch",
        json={
            "workspace_id": "ws_dev",
            "zoom_url": "https://zoom.us/j/85412345678",
        },
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "bot_pool_full"
