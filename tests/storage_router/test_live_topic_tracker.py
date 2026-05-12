"""Wave 8.6 — live-topic-tracker tick loop unit tests.

Mocks the Hermes skill via `hermes_plugin.live_topic_tracker` and the
storage layer via `storage.get_transcript`. Verifies:

  - the loop ticks at the configured cadence;
  - the persisted column is updated with the skill's raw output;
  - the refusal sentinel maps to `current_topic = NULL`;
  - cancellation terminates the task cleanly.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from storage_router import live_topic_tracker as ltt


def _fake_transcript(*texts: str):
    segments = [
        SimpleNamespace(text=t, start_ms=i * 1000, end_ms=(i + 1) * 1000)
        for i, t in enumerate(texts)
    ]
    return SimpleNamespace(segments=segments)


def test_build_snippet_takes_trailing_window():
    """Only the last `TOPIC_WINDOW_SECONDS` of finalized text is included."""
    fake = _fake_transcript(*[f"line{i}." for i in range(100)])
    fake_session = MagicMock()
    with patch("storage_router.storage.get_transcript", return_value=fake):
        snippet = ltt._build_snippet(fake_session, "m_test")
    # 100 lines × 1 s each; default window 60 s → last ~60 lines
    # (inclusive of the cutoff boundary, so 61 in this fixture).
    words = snippet.split()
    assert 60 <= len(words) <= 61
    assert words[-1] == "line99."
    # The earliest included line should be near the 60-s cutoff.
    assert words[0] in {"line39.", "line40."}


def test_build_snippet_empty_transcript_returns_empty_string():
    with patch("storage_router.storage.get_transcript", return_value=None):
        assert ltt._build_snippet(MagicMock(), "m_x") == ""


def test_call_skill_maps_refusal_sentinel_to_none():
    with patch("hermes_plugin.live_topic_tracker", return_value="__TOPIC_INSUFFICIENT__"):
        assert ltt._call_skill("anything") is None
    with patch("hermes_plugin.live_topic_tracker", return_value="   "):
        assert ltt._call_skill("anything") is None


def test_call_skill_returns_stripped_topic():
    with patch(
        "hermes_plugin.live_topic_tracker",
        return_value="  Reviewing Q3 revenue projections.  \n",
    ):
        assert ltt._call_skill("anything") == "Reviewing Q3 revenue projections."


@pytest.mark.asyncio
async def test_topic_loop_ticks_then_cancels():
    """One tick should call `_persist_topic` once with the canned topic;
    cancelling the task should exit cleanly without raising upward."""
    sleeps: list[int] = []
    cancel_after_n = 1

    async def _fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= cancel_after_n:
            raise asyncio.CancelledError()
        await asyncio.sleep(0)

    persisted: list[tuple[str, str | None]] = []

    def _capture_persist(meeting_id: str, topic: str | None) -> None:
        persisted.append((meeting_id, topic))

    with patch.object(ltt, "_build_snippet", return_value="word " * 50), \
         patch.object(ltt, "_call_skill", return_value="A topic line."), \
         patch.object(ltt, "_persist_topic", side_effect=_capture_persist):
        with pytest.raises(asyncio.CancelledError):
            await ltt.topic_loop("m_test", tick_seconds=30, sleep=_fake_sleep)

    assert persisted == [("m_test", "A topic line.")]
    assert sleeps == [30]


@pytest.mark.asyncio
async def test_topic_loop_handles_sentinel_writes_none():
    sleeps: list[int] = []

    async def _fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        raise asyncio.CancelledError()

    persisted: list[tuple[str, str | None]] = []

    with patch.object(ltt, "_build_snippet", return_value="word"), \
         patch.object(ltt, "_call_skill", return_value=None), \
         patch.object(ltt, "_persist_topic", side_effect=lambda m, t: persisted.append((m, t))):
        with pytest.raises(asyncio.CancelledError):
            await ltt.topic_loop("m_x", tick_seconds=5, sleep=_fake_sleep)

    assert persisted == [("m_x", None)]


@pytest.mark.asyncio
async def test_topic_loop_skips_persist_when_snippet_empty():
    sleeps: list[int] = []

    async def _fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        raise asyncio.CancelledError()

    with patch.object(ltt, "_build_snippet", return_value=""), \
         patch.object(ltt, "_call_skill") as call, \
         patch.object(ltt, "_persist_topic") as persist:
        with pytest.raises(asyncio.CancelledError):
            await ltt.topic_loop("m_y", tick_seconds=5, sleep=_fake_sleep)

    call.assert_not_called()
    persist.assert_not_called()


def test_start_topic_loop_idempotent():
    """Calling `start_topic_loop` twice for the same meeting reuses the
    existing task instead of spawning a duplicate."""
    fake_app = SimpleNamespace(state=SimpleNamespace(live_tasks={}))

    async def _runner():
        ltt.start_topic_loop(fake_app, "m_idem")
        first = fake_app.state.live_tasks["m_idem"]["topic"]
        ltt.start_topic_loop(fake_app, "m_idem")
        second = fake_app.state.live_tasks["m_idem"]["topic"]
        assert first is second
        ltt.cancel_topic_loop(fake_app, "m_idem")
        # Allow the cancellation to propagate.
        try:
            await first
        except asyncio.CancelledError:
            pass

    asyncio.run(_runner())


def test_cancel_topic_loop_noop_when_unknown_meeting():
    fake_app = SimpleNamespace(state=SimpleNamespace(live_tasks={}))
    # Should not raise even though no entry exists.
    ltt.cancel_topic_loop(fake_app, "m_does_not_exist")
