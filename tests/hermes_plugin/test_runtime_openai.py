"""Drive runtime_openai.run_skill against a fake OpenAI client + mock storage."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from hermes_plugin.runtime_openai import _default_openai_client, run_skill


_VALID_CARD = {
    "memory_card_id": "mc_1",
    "meeting_id": "m_fixture001",
    "state": "draft",
    "type": "decision",
    "title": "t",
    "content": "c",
    "source_chunk_ids": ["seg_001"],
    "confidence": 0.9,
}


# --- Fake OpenAI client (mirrors FakeAnthropic in conftest) -----------------


class _FakeFunction:
    def __init__(self, name: str, arguments: str | dict) -> None:
        self.name = name
        if isinstance(arguments, dict):
            self.arguments = json.dumps(arguments)
        else:
            self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str | dict) -> None:
        self.id = call_id
        self.type = "function"
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(
        self,
        *,
        content: str | None = None,
        tool_calls: list[_FakeToolCall] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.role = "assistant"


class _FakeChoice:
    def __init__(self, message: _FakeMessage, finish_reason: str) -> None:
        self.message = message
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, choice: _FakeChoice) -> None:
        self.choices = [choice]


class _FakeCompletions:
    def __init__(self, scripted: list[_FakeResponse]) -> None:
        self._scripted = list(scripted)
        self.calls: list[dict] = []

    def create(self, **kwargs: Any) -> _FakeResponse:
        # Snapshot the messages list so post-hoc assertions see the state
        # at call time, not after subsequent in-place appends by the loop.
        snapshot = dict(kwargs)
        if "messages" in snapshot:
            snapshot["messages"] = [dict(m) for m in snapshot["messages"]]
        self.calls.append(snapshot)
        if not self._scripted:
            raise AssertionError(
                "FakeOpenAI ran out of scripted responses; "
                f"got an extra create() call with messages={kwargs.get('messages')!r}"
            )
        return self._scripted.pop(0)


class _FakeChat:
    def __init__(self, scripted: list[_FakeResponse]) -> None:
        self.completions = _FakeCompletions(scripted)


class FakeOpenAI:
    """Stub mirroring the small slice of openai.OpenAI we use."""

    def __init__(self, scripted_responses: list[_FakeResponse]) -> None:
        self.chat = _FakeChat(scripted_responses)


def _make_text_response(text: str, finish_reason: str = "stop") -> _FakeResponse:
    return _FakeResponse(_FakeChoice(_FakeMessage(content=text), finish_reason))


def _make_tool_call_response(tool_calls: list[_FakeToolCall]) -> _FakeResponse:
    return _FakeResponse(
        _FakeChoice(_FakeMessage(content=None, tool_calls=tool_calls), "tool_calls")
    )


# --- Tests ------------------------------------------------------------------


def test_run_skill_single_shot_no_tools(storage_client):
    """If the model returns a final message immediately, the loop exits in one turn."""
    handler = lambda req: (_ for _ in ()).throw(  # noqa: E731
        AssertionError(f"unexpected request: {req.method} {req.url.path}")
    )
    client = storage_client(handler)
    llm = FakeOpenAI([_make_text_response("Done.", finish_reason="stop")])

    result = run_skill(
        "meeting-qa",
        meeting_id="m_1",
        user_question="What was decided?",
        client=client,
        openai_client=llm,
    )

    assert result["iterations"] == 1
    assert result["tool_calls"] == []
    assert result["final_text"] == "Done."

    # The first call must include the system prompt as messages[0].
    sent = llm.chat.completions.calls[0]["messages"]
    assert sent[0]["role"] == "system"
    assert sent[1]["role"] == "user"
    assert "Question: What was decided?" in sent[1]["content"]


def test_run_skill_tool_use_loop(storage_client, transcript_fixture):
    """One tool call -> tool result -> final text. Verifies wire shape."""
    posts: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path == "/api/meetings/m_fixture001/transcript":
            return httpx.Response(200, json=transcript_fixture)
        if req.method == "POST" and req.url.path == "/api/memory-cards":
            posts.append(req)
            return httpx.Response(200, json=_VALID_CARD)
        raise AssertionError(f"unexpected request: {req.method} {req.url.path}")

    client = storage_client(handler)

    scripted = [
        _make_tool_call_response(
            [_FakeToolCall("call_1", "get_meeting_transcript", {"meeting_id": "m_fixture001"})]
        ),
        _make_tool_call_response(
            [
                _FakeToolCall(
                    "call_2",
                    "create_draft_memory_card",
                    {
                        "meeting_id": "m_fixture001",
                        "type": "decision",
                        "title": "Auth migration timeline",
                        "content": "Delay provider switch.",
                        "source_chunk_ids": ["seg_002"],
                        "confidence": 0.85,
                    },
                )
            ]
        ),
        _make_text_response("Created 1 draft memory card.", finish_reason="stop"),
    ]
    llm = FakeOpenAI(scripted)

    result = run_skill(
        "meeting-memory-extraction",
        meeting_id="m_fixture001",
        client=client,
        openai_client=llm,
    )

    assert result["iterations"] == 3
    assert [c["name"] for c in result["tool_calls"]] == [
        "get_meeting_transcript",
        "create_draft_memory_card",
    ]
    assert len(posts) == 1
    assert result["final_text"] == "Created 1 draft memory card."

    # Verify the second turn (after first tool result) carries the tool reply
    # keyed by tool_call_id, and the assistant tool_calls history that triggered it.
    second_call_messages = llm.chat.completions.calls[1]["messages"]
    tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "call_1"
    assistant_turns = [m for m in second_call_messages if m.get("role") == "assistant"]
    assert assistant_turns and assistant_turns[-1].get("tool_calls")
    # By the third call both tool results are in the history.
    third_call_messages = llm.chat.completions.calls[2]["messages"]
    tool_ids = [m["tool_call_id"] for m in third_call_messages if m.get("role") == "tool"]
    assert tool_ids == ["call_1", "call_2"]


def test_run_skill_max_iterations_cap(storage_client, transcript_fixture):
    """If the model never stops, the loop returns at max_iterations without raising."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path == "/api/meetings/m_fixture001/transcript":
            return httpx.Response(200, json=transcript_fixture)
        raise AssertionError(f"unexpected request: {req.method} {req.url.path}")

    client = storage_client(handler)

    # Always return a tool call, never a final message.
    looped = [
        _make_tool_call_response(
            [_FakeToolCall(f"call_{i}", "get_meeting_transcript", {"meeting_id": "m_fixture001"})]
        )
        for i in range(5)
    ]
    llm = FakeOpenAI(looped)

    result = run_skill(
        "meeting-memory-extraction",
        meeting_id="m_fixture001",
        client=client,
        openai_client=llm,
        max_iterations=3,
    )

    assert result["iterations"] == 3
    assert len(result["tool_calls"]) == 3


def test_run_skill_unknown_tool(storage_client):
    """An unknown tool name surfaces as an unknown_tool result without raising."""

    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {req.method} {req.url.path}")

    client = storage_client(handler)

    scripted = [
        _make_tool_call_response(
            [_FakeToolCall("call_1", "definitely_not_a_tool", {"foo": "bar"})]
        ),
        _make_text_response("Aborted.", finish_reason="stop"),
    ]
    llm = FakeOpenAI(scripted)

    result = run_skill(
        "meeting-memory-extraction",
        meeting_id="m_fixture001",
        client=client,
        openai_client=llm,
    )

    assert result["iterations"] == 2
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["result"]["code"] == "unknown_tool"
    assert result["final_text"] == "Aborted."


def test_run_skill_unknown_skill_raises(storage_client):
    client = storage_client(lambda req: httpx.Response(500))
    llm = FakeOpenAI([])
    with pytest.raises(ValueError):
        run_skill("not-a-real-skill", meeting_id="m_1", client=client, openai_client=llm)


def test_run_skill_qa_requires_user_question(storage_client):
    client = storage_client(lambda req: httpx.Response(500))
    llm = FakeOpenAI([])
    with pytest.raises(ValueError):
        run_skill("meeting-qa", meeting_id="m_1", client=client, openai_client=llm)


def test_default_client_passes_base_url_when_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepinfra.com/v1/openai")
    with patch("openai.OpenAI") as mock_cls:
        _default_openai_client()
    mock_cls.assert_called_once_with(base_url="https://api.deepinfra.com/v1/openai")


def test_default_client_omits_base_url_when_unset(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    with patch("openai.OpenAI") as mock_cls:
        _default_openai_client()
    assert "base_url" not in mock_cls.call_args.kwargs


def test_run_skill_tools_param_shape(storage_client):
    """Verify the OpenAI-shaped tools param reaches chat.completions.create."""
    client = storage_client(lambda req: httpx.Response(500))
    llm = FakeOpenAI([_make_text_response("ok")])

    run_skill(
        "meeting-qa",
        meeting_id="m_1",
        user_question="q?",
        client=client,
        openai_client=llm,
    )

    sent_tools = llm.chat.completions.calls[0]["tools"]
    assert sent_tools, "no tools were passed to OpenAI"
    for entry in sent_tools:
        assert entry["type"] == "function"
        fn = entry["function"]
        assert "name" in fn and "description" in fn and "parameters" in fn
