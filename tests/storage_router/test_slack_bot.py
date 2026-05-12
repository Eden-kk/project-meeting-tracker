"""Slack Socket Mode lifecycle + app_mention handler unit tests.

These tests deliberately avoid spinning up a real WebSocket: they probe
the env-gating behaviour of :func:`slack_bot.start` and the mention
dispatch inside :func:`slack_bot._handle_app_mention` with a fake
async web client.
"""
from __future__ import annotations

import pytest

from storage_router import slack_bot


class _Spy:
    def __init__(self):
        self.calls: list[dict] = []

    async def chat_postMessage(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"ok": True, "ts": "1.0"}


@pytest.mark.asyncio
async def test_start_is_noop_when_env_unset(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_DEFAULT_CHANNEL_ID", raising=False)

    class _App:
        class state:
            slack_task = "sentinel"

    app = _App()
    await slack_bot.start(app)
    assert app.state.slack_task is None, "start must not spawn a task when env is unset"


@pytest.mark.asyncio
async def test_handle_app_mention_routes_to_workspace_qa(monkeypatch):
    captured: dict = {}

    def _fake_qa(workspace_id: str, question: str) -> dict:
        captured["workspace_id"] = workspace_id
        captured["question"] = question
        return {"final_text": "We decided X [meeting:m1:seg:s1]."}

    from storage_router import hermes_runtime

    monkeypatch.setattr(hermes_runtime, "run_workspace_qa", _fake_qa)
    monkeypatch.setenv("SLACK_FRONTEND_BASE_URL", "https://x.test")

    web = _Spy()
    event = {
        "type": "app_mention",
        "text": "<@U01234ABC> what did we decide?",
        "channel": "C999",
        "ts": "1700000000.000100",
    }
    await slack_bot._handle_app_mention(event, web)

    assert captured == {"workspace_id": "ws_dev", "question": "what did we decide?"}
    assert len(web.calls) == 1
    reply = web.calls[0]
    assert reply["channel"] == "C999"
    assert reply["thread_ts"] == "1700000000.000100"
    # Block payload should include the rewritten citation as a Slack link.
    blocks = reply["blocks"]
    text = blocks[0]["text"]["text"]
    assert "[meeting:m1:seg:s1]" not in text
    assert "https://x.test/meetings/m1#seg:s1" in text


@pytest.mark.asyncio
async def test_handle_app_mention_replies_when_hermes_unavailable(monkeypatch):
    from storage_router import hermes_runtime

    def _boom(workspace_id: str, question: str) -> dict:
        raise hermes_runtime.HermesUnavailable("not installed")

    monkeypatch.setattr(hermes_runtime, "run_workspace_qa", _boom)

    web = _Spy()
    event = {
        "type": "app_mention",
        "text": "<@U01> hi",
        "channel": "C1",
        "ts": "1.1",
    }
    await slack_bot._handle_app_mention(event, web)
    assert len(web.calls) == 1
    assert "offline" in web.calls[0]["text"].lower()
    assert web.calls[0]["thread_ts"] == "1.1"


@pytest.mark.asyncio
async def test_handle_app_mention_uses_thread_ts_when_present(monkeypatch):
    from storage_router import hermes_runtime

    monkeypatch.setattr(
        hermes_runtime,
        "run_workspace_qa",
        lambda w, q: {"final_text": "ok"},
    )

    web = _Spy()
    event = {
        "type": "app_mention",
        "text": "<@U01> ?",
        "channel": "C1",
        "ts": "9.9",
        "thread_ts": "3.3",  # already in a thread — reply belongs to the thread
    }
    await slack_bot._handle_app_mention(event, web)
    assert web.calls[0]["thread_ts"] == "3.3"
