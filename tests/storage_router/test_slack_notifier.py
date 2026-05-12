"""``slack_notifier.notify_finalize`` unit tests.

These tests stub out ``SessionLocal``, ``storage.list_meeting_cards``,
and the slack-sdk ``WebClient`` so they run without a live Postgres or
network. They cover:

1. No-op when required env vars are unset.
2. One top-level post + N threaded replies for N non-empty card types.
3. Empty card sections are skipped entirely (no empty thread replies).
4. Link target uses ``source_chunk_ids[0]`` when present, falls back
   to ``/meetings/<id>`` when absent.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime

from storage_router import slack_notifier


# --- test fixtures ----------------------------------------------------------

@dataclass
class _FakeMeeting:
    id: str = "m1"
    title: str = "Meeting One"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    finalized_summary: str = "We covered roadmap, risks, and next steps."
    speaker_label_map: dict | None = None
    slack_thread_ts: str | None = None


@dataclass
class _FakeCard:
    title: str
    source_chunk_ids: list[str] = field(default_factory=list)


class _FakeSession:
    """Minimal session stub honouring the calls notify_finalize makes."""

    def __init__(self, meeting: _FakeMeeting, cards_by_type: dict[str, list[_FakeCard]]):
        self._meeting = meeting
        self._cards = cards_by_type

    # SessionLocal context manager protocol.
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, _cls, _meeting_id):
        return self._meeting

    def commit(self):
        pass


class _FakeWebClient:
    def __init__(self, *, token=None):
        self.token = token
        self.calls: list[dict] = []

    def chat_postMessage(self, **kwargs):
        self.calls.append(kwargs)
        # Mimic slack_sdk SlackResponse with a dict-like .get for "ts".
        return {"ok": True, "ts": f"ts-{len(self.calls)}"}


@contextmanager
def _patched_world(monkeypatch, *, meeting, cards_by_type, captured_client_holder):
    """Install fake SessionLocal + WebClient + storage helpers."""
    from storage_router import storage

    session = _FakeSession(meeting, cards_by_type)

    def _fake_session_local():
        return session

    monkeypatch.setattr("storage_router.slack_notifier.log", slack_notifier.log)
    # Patch DB layer.
    monkeypatch.setattr("storage_router.db.SessionLocal", _fake_session_local)
    # Patch storage helpers used by the notifier.
    monkeypatch.setattr(
        storage,
        "list_meeting_cards",
        lambda session, *, meeting_id, type, limit=50: (
            cards_by_type.get(type, []),
            len(cards_by_type.get(type, [])),
        ),
    )

    class _Transcript:
        segments: list = []

    monkeypatch.setattr(storage, "get_transcript", lambda s, mid: _Transcript())

    # Patch WebClient symbol IN the slack_sdk module so notify_finalize's
    # `from slack_sdk import WebClient` picks it up.
    import slack_sdk

    def _factory(*, token):
        client = _FakeWebClient(token=token)
        captured_client_holder.append(client)
        return client

    monkeypatch.setattr(slack_sdk, "WebClient", _factory)
    yield session


# --- tests ------------------------------------------------------------------

def test_notify_finalize_is_noop_when_env_unset(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_DEFAULT_CHANNEL_ID", raising=False)

    import slack_sdk

    instantiated: list = []

    def _spy(*, token):
        instantiated.append(token)
        return object()

    monkeypatch.setattr(slack_sdk, "WebClient", _spy)
    slack_notifier.notify_finalize("m1")
    assert instantiated == [], "WebClient must not be instantiated when env is unset"


def test_notify_finalize_posts_one_top_level_plus_one_thread_per_nonempty_type(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("SLACK_DEFAULT_CHANNEL_ID", "C123")
    monkeypatch.setenv("SLACK_FRONTEND_BASE_URL", "https://x.test")

    meeting = _FakeMeeting()
    cards_by_type = {
        "decision": [_FakeCard("Ship Tuesday", ["seg-1"])],
        "action_item": [_FakeCard("Alice writes RFC", ["seg-2"])],
        "open_question": [_FakeCard("What about prod?", ["seg-3"])],
        "risk": [_FakeCard("DB capacity", ["seg-4"])],
        "pain_point": [],
    }
    holder: list = []
    with _patched_world(
        monkeypatch, meeting=meeting, cards_by_type=cards_by_type, captured_client_holder=holder
    ):
        slack_notifier.notify_finalize("m1")

    assert len(holder) == 1
    client = holder[0]
    # 1 top-level + 4 thread replies (decision, action_item, open_question,
    # risk+pain_point grouped — only risk has rows here, so the section is posted).
    assert len(client.calls) == 5
    # First call: top-level (no thread_ts).
    top = client.calls[0]
    assert "thread_ts" not in top
    assert top["channel"] == "C123"
    # Remaining four are all thread replies of the top-level message.
    for reply in client.calls[1:]:
        assert reply["thread_ts"] == "ts-1"
        assert reply["channel"] == "C123"


def test_notify_finalize_skips_empty_card_types(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("SLACK_DEFAULT_CHANNEL_ID", "C123")
    monkeypatch.setenv("SLACK_FRONTEND_BASE_URL", "https://x.test")

    meeting = _FakeMeeting()
    # Only TWO non-empty card types.
    cards_by_type = {
        "decision": [_FakeCard("Ship Tuesday", ["seg-1"])],
        "action_item": [_FakeCard("Alice writes RFC", ["seg-2"])],
        "open_question": [],
        "risk": [],
        "pain_point": [],
    }
    holder: list = []
    with _patched_world(
        monkeypatch, meeting=meeting, cards_by_type=cards_by_type, captured_client_holder=holder
    ):
        slack_notifier.notify_finalize("m1")

    client = holder[0]
    # 1 top-level + exactly 2 thread replies — no empty sections posted.
    assert len(client.calls) == 3
    for reply in client.calls[1:]:
        assert reply["thread_ts"] == "ts-1"


def test_notify_finalize_link_falls_back_to_meeting_when_no_source_chunk(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("SLACK_DEFAULT_CHANNEL_ID", "C123")
    monkeypatch.setenv("SLACK_FRONTEND_BASE_URL", "https://x.test")

    meeting = _FakeMeeting(id="m1")
    cards_by_type = {
        "decision": [
            _FakeCard("Has segment", ["seg-77"]),
            _FakeCard("No segment", []),
        ],
        "action_item": [],
        "open_question": [],
        "risk": [],
        "pain_point": [],
    }
    holder: list = []
    with _patched_world(
        monkeypatch, meeting=meeting, cards_by_type=cards_by_type, captured_client_holder=holder
    ):
        slack_notifier.notify_finalize("m1")

    client = holder[0]
    # The single threaded reply is at index 1.
    reply = client.calls[1]
    text = reply["blocks"][0]["text"]["text"]
    assert "https://x.test/meetings/m1#seg:seg-77" in text
    # Card without source_chunk_ids falls back to /meetings/<id> only.
    assert "https://x.test/meetings/m1|No segment" in text
