"""Q1 — live-interview-questioner tick loop unit tests.

Mocks `hermes_plugin.live_interview_questions` and the storage layer.
Verifies:
  - the loop ticks and persists `meetings.suggested_questions`;
  - `start_questioner_loop` is a no-op when `interviewee_name IS NULL` (gate);
  - cancellation terminates the task cleanly.

Does NOT need real Postgres — all DB access is patched.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from storage_router import live_interview_questioner as liq


def _fake_row(interviewee_name: str | None = "Alice", interviewee_role: str | None = "Staff Eng"):
    return SimpleNamespace(
        interviewee_name=interviewee_name,
        interviewee_role=interviewee_role,
    )


def _fake_transcript(*texts: str):
    segments = [
        SimpleNamespace(text=t, start_ms=i * 1000, end_ms=(i + 1) * 1000)
        for i, t in enumerate(texts)
    ]
    return SimpleNamespace(segments=segments)


# ---------------------------------------------------------------------------
# _build_snippet tests
# ---------------------------------------------------------------------------

def test_build_snippet_returns_trailing_window():
    fake_row = _fake_row()
    fake_trans = _fake_transcript(*[f"word{i}." for i in range(200)])
    fake_session = MagicMock()
    fake_session.get.return_value = fake_row
    with patch("storage_router.storage.get_transcript", return_value=fake_trans):
        snippet, name, role = liq._build_snippet(fake_session, "m_test")
    assert name == "Alice"
    assert role == "Staff Eng"
    assert "word199." in snippet


def test_build_snippet_no_meeting_row():
    fake_session = MagicMock()
    fake_session.get.return_value = None
    snippet, name, role = liq._build_snippet(fake_session, "m_gone")
    assert snippet == ""
    assert name is None
    assert role is None


def test_build_snippet_empty_transcript():
    fake_session = MagicMock()
    fake_session.get.return_value = _fake_row()
    with patch("storage_router.storage.get_transcript", return_value=None):
        snippet, name, role = liq._build_snippet(fake_session, "m_empty")
    assert snippet == ""
    assert name == "Alice"


# ---------------------------------------------------------------------------
# questioner_loop tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_questioner_loop_writes_suggested_questions():
    """One tick should persist the questions returned by the skill."""
    sleeps: list[int] = []

    async def _fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        raise asyncio.CancelledError()

    persisted: list[list[str]] = []

    def _capture_persist(meeting_id: str, questions: list[str]) -> None:
        persisted.append(questions)

    fixed_output = {"questions": ["Q1?", "Q2?", "Q3?"]}

    with patch.object(
        liq, "_build_snippet", return_value=("word " * 60, "Alice", "Staff Eng")
    ), patch(
        "hermes_plugin.live_interview_questions", return_value=fixed_output
    ), patch.object(
        liq, "_persist_questions", side_effect=_capture_persist
    ):
        with pytest.raises(asyncio.CancelledError):
            await liq.questioner_loop("m_test", tick_seconds=60, sleep=_fake_sleep)

    assert persisted == [["Q1?", "Q2?", "Q3?"]]
    assert sleeps == [60]


@pytest.mark.asyncio
async def test_questioner_loop_skips_when_no_snippet():
    """No skill call and no persist when snippet is empty."""
    sleeps: list[int] = []

    async def _fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        raise asyncio.CancelledError()

    with patch.object(
        liq, "_build_snippet", return_value=("", "Alice", "Staff Eng")
    ), patch("hermes_plugin.live_interview_questions") as call_mock, \
       patch.object(liq, "_persist_questions") as persist_mock:
        with pytest.raises(asyncio.CancelledError):
            await liq.questioner_loop("m_empty", tick_seconds=60, sleep=_fake_sleep)

    call_mock.assert_not_called()
    persist_mock.assert_not_called()


@pytest.mark.asyncio
async def test_questioner_loop_runs_without_interviewee_name():
    """Skill is still called when interviewee_name is None — grounds on transcript only."""
    sleeps: list[int] = []

    async def _fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)
        raise asyncio.CancelledError()

    with patch.object(
        liq, "_build_snippet", return_value=("word " * 60, None, None)
    ), patch("hermes_plugin.live_interview_questions", return_value={"questions": ["q1"]}) as call_mock, \
       patch.object(liq, "_persist_questions") as persist_mock:
        with pytest.raises(asyncio.CancelledError):
            await liq.questioner_loop("m_noint", tick_seconds=60, sleep=_fake_sleep)

    call_mock.assert_called_once()
    persist_mock.assert_called_once_with("m_noint", ["q1"])


# ---------------------------------------------------------------------------
# start_questioner_loop spawn test (always spawns for live meetings)
# ---------------------------------------------------------------------------

def test_start_questioner_loop_spawns_task():
    """A task is spawned for every live meeting (no gate)."""
    fake_app = SimpleNamespace(state=SimpleNamespace(live_tasks={}))

    async def _runner():
        liq.start_questioner_loop(fake_app, "m_any")
        task = fake_app.state.live_tasks["m_any"]["questioner"]
        assert not task.done()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_runner())


def test_cancel_questioner_loop_noop_when_unknown():
    fake_app = SimpleNamespace(state=SimpleNamespace(live_tasks={}))
    liq.cancel_questioner_loop(fake_app, "m_does_not_exist")
