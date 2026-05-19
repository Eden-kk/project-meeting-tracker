"""Bot orchestrator lifecycle tests (Slice 3 + 4).

These tests run from the **repo root** (``pytest bot/tests/``) — do NOT
``cd bot && pytest``, because the worktree's pytest config (asyncio
plugin etc.) is anchored at the root.

All Puppeteer / pactl / ffmpeg calls are mocked. Subtests that need
real Zoom credentials are gated by ``@pytest.mark.skipif`` per the
plan's credentials-bootstrap policy.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import bot as bot_module  # bot/bot.py via tests/conftest.py


def _make_cfg(tmp_path: Path) -> bot_module.BotConfig:
    return bot_module.BotConfig(
        meeting_id="m_test",
        zoom_url="https://zoom.us/j/12345?pwd=abc",
        storage_router_url="http://router.local",
        bot_dir=tmp_path,
        chunk_dir=tmp_path / "chunks",
        chunk_seconds=0.1,
        not_admitted_timeout_s=2.0,
    )


def test_botconfig_resolves_sink_name(tmp_path) -> None:
    cfg = _make_cfg(tmp_path)
    assert cfg.sink_name == "BotSink_m_test"


def test_load_config_requires_env(monkeypatch) -> None:
    monkeypatch.delenv("MEETING_ID", raising=False)
    with pytest.raises(SystemExit):
        bot_module.load_config()


def test_load_config_builds_from_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MEETING_ID", "m_env")
    monkeypatch.setenv("ZOOM_URL", "https://zoom.us/j/99")
    monkeypatch.setenv("STORAGE_ROUTER_URL", "http://r")
    monkeypatch.setenv("BOT_CHUNK_DIR", str(tmp_path))
    cfg = bot_module.load_config()
    assert cfg.meeting_id == "m_env"
    assert cfg.chunk_dir == tmp_path


def test_multipart_body_round_trips(tmp_path) -> None:
    chunk = tmp_path / "chunk-0001.webm"
    chunk.write_bytes(b"\x00\x01\x02hello")
    body, content_type = bot_module._multipart_body(chunk)
    assert content_type.startswith("multipart/form-data; boundary=")
    assert b"chunk-0001.webm" in body
    assert b"\x00\x01\x02hello" in body
    assert body.endswith(b"--\r\n")


def test_upload_chunk_posts_to_audio_chunk_endpoint(tmp_path) -> None:
    cfg = _make_cfg(tmp_path)
    cfg.chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk = cfg.chunk_dir / "chunk-0001.webm"
    chunk.write_bytes(b"abc")
    captured: dict[str, object] = {}

    class FakeResp:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):  # noqa: ARG001
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        return FakeResp()

    with patch.object(bot_module.urllib.request, "urlopen", fake_urlopen):
        status = bot_module.upload_chunk(cfg, chunk)
    assert status == 202
    assert (
        captured["url"]
        == "http://router.local/api/live-meetings/m_test/audio-chunk"
    )
    assert captured["method"] == "POST"


def test_call_end_posts_to_end_endpoint(tmp_path) -> None:
    cfg = _make_cfg(tmp_path)
    captured: dict[str, object] = {}

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):  # noqa: ARG001
        captured["url"] = req.full_url
        return FakeResp()

    with patch.object(bot_module.urllib.request, "urlopen", fake_urlopen):
        status = bot_module.call_end(cfg)
    assert status == 200
    assert captured["url"] == "http://router.local/api/live-meetings/m_test/end"


def test_upload_new_chunks_skips_in_flight(tmp_path) -> None:
    """ffmpeg writes monotonically; the newest file is likely still being written."""
    cfg = _make_cfg(tmp_path)
    cfg.chunk_dir.mkdir(parents=True, exist_ok=True)
    old = cfg.chunk_dir / "chunk-0001.webm"
    old.write_bytes(b"old")
    # Backdate the file so the mtime-based "still being written" guard treats
    # it as closed.
    past = time.time() - 60
    os.utime(old, (past, past))

    # Also create a brand-new file; it must NOT be uploaded yet.
    fresh = cfg.chunk_dir / "chunk-0002.webm"
    fresh.write_bytes(b"fresh")

    seen: list[Path] = []

    def fake_upload(_cfg, path):
        seen.append(path)
        return 202

    with patch.object(bot_module, "upload_chunk", fake_upload):
        uploaded = bot_module.upload_new_chunks(cfg, set())

    assert old.name in uploaded
    assert fresh.name not in uploaded
    assert seen == [old]


# ---------------------------------------------------------------------------
# Slice 4 lifecycle — exercised via patched subprocess.Popen + sink helpers
# ---------------------------------------------------------------------------


def _fake_proc(rc_sequence: list[int | None]) -> MagicMock:
    """Build a Popen-shaped mock whose ``poll()`` returns rc_sequence in order."""
    proc = MagicMock(spec=["poll", "terminate", "kill", "wait", "returncode", "pid"])
    proc.pid = 9001
    poll_iter = iter(rc_sequence + [rc_sequence[-1]] * 50)
    proc.poll.side_effect = lambda: next(poll_iter)
    proc.returncode = rc_sequence[-1] if rc_sequence[-1] is not None else 0
    return proc


def test_run_calls_end_on_clean_exit(tmp_path, monkeypatch) -> None:
    """When zoom-bot.js exits, ``run()`` must call ``call_end()`` once."""
    cfg = _make_cfg(tmp_path)
    cfg.chunk_dir.mkdir(parents=True, exist_ok=True)
    cfg.not_admitted_timeout_s = 60.0

    # Node exits cleanly on the first poll → the loop drains and breaks.
    node_proc = _fake_proc([0])
    ff_proc = _fake_proc([None])

    monkeypatch.setattr(bot_module, "create_pulse_sink", lambda name: "mod-1")
    monkeypatch.setattr(bot_module, "unload_pulse_sink", lambda mid: None)
    monkeypatch.setattr(bot_module, "spawn_node_bot", lambda c: node_proc)
    monkeypatch.setattr(bot_module, "spawn_ffmpeg", lambda c: ff_proc)
    monkeypatch.setattr(bot_module, "upload_new_chunks", lambda cfg, seen: seen)

    end_calls: list[int] = []
    monkeypatch.setattr(
        bot_module, "call_end", lambda c: end_calls.append(1) or 200
    )

    bot_module.run(cfg)
    assert end_calls == [1], "call_end must run exactly once on clean exit"


def test_run_returns_2_when_not_admitted(tmp_path, monkeypatch) -> None:
    """No chunks within ``not_admitted_timeout_s`` → exit code 2."""
    cfg = _make_cfg(tmp_path)
    cfg.chunk_dir.mkdir(parents=True, exist_ok=True)
    cfg.not_admitted_timeout_s = 0.5

    node_proc = _fake_proc([None])
    ff_proc = _fake_proc([None])

    monkeypatch.setattr(bot_module, "create_pulse_sink", lambda name: "mod-1")
    monkeypatch.setattr(bot_module, "unload_pulse_sink", lambda mid: None)
    monkeypatch.setattr(bot_module, "spawn_node_bot", lambda c: node_proc)
    monkeypatch.setattr(bot_module, "spawn_ffmpeg", lambda c: ff_proc)
    monkeypatch.setattr(bot_module, "call_end", lambda c: 200)
    monkeypatch.setattr(bot_module, "upload_new_chunks", lambda cfg, seen: seen)

    assert bot_module.run(cfg) == 2


def test_run_returns_node_rc_when_zoom_exits(tmp_path, monkeypatch) -> None:
    cfg = _make_cfg(tmp_path)
    cfg.chunk_dir.mkdir(parents=True, exist_ok=True)
    cfg.not_admitted_timeout_s = 60.0

    # Node exits cleanly on the very first poll.
    node_proc = _fake_proc([0])
    ff_proc = _fake_proc([None])

    monkeypatch.setattr(bot_module, "create_pulse_sink", lambda name: "mod-1")
    monkeypatch.setattr(bot_module, "unload_pulse_sink", lambda mid: None)
    monkeypatch.setattr(bot_module, "spawn_node_bot", lambda c: node_proc)
    monkeypatch.setattr(bot_module, "spawn_ffmpeg", lambda c: ff_proc)
    monkeypatch.setattr(bot_module, "call_end", lambda c: 200)
    monkeypatch.setattr(bot_module, "upload_new_chunks", lambda cfg, seen: seen)

    assert bot_module.run(cfg) == 0


@pytest.mark.skipif(
    not os.getenv("ZOOM_SDK_KEY"),
    reason="Zoom Marketplace creds not in env (real-meeting smoke).",
)
def test_real_meeting_smoke_placeholder() -> None:
    """Placeholder: the actual real-meeting smoke is the §F manual handbook."""
    pytest.skip("Real-meeting smoke runs out-of-band per bot/README.md.")
