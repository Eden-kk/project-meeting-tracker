"""Shared fixtures for hermes_plugin tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest
from anthropic.types import Message

from hermes_plugin.client import StorageRouterClient


WORKTREE_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def transcript_fixture() -> dict:
    """Load the canonical normalized transcript fixture from worktree root.

    We read in-place rather than copy so the fixture cannot drift.
    """
    path = WORKTREE_ROOT / "fixtures" / "expected_normalized.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def mock_transport_factory() -> Callable[[Callable[[httpx.Request], httpx.Response]], httpx.MockTransport]:
    """Factory that wraps a handler in httpx.MockTransport.

    Tests pass a handler that returns scripted responses; the factory
    keeps the wrapper boilerplate out of the test bodies.
    """

    def _make(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
        return httpx.MockTransport(handler)

    return _make


@pytest.fixture
def storage_client(mock_transport_factory) -> Callable[[Callable[[httpx.Request], httpx.Response]], StorageRouterClient]:
    """Returns a builder that yields a StorageRouterClient bound to a mock handler."""

    def _make(handler: Callable[[httpx.Request], httpx.Response]) -> StorageRouterClient:
        return StorageRouterClient(transport=mock_transport_factory(handler))

    return _make


class _FakeMessages:
    def __init__(self, scripted: list[dict]) -> None:
        self._scripted = list(scripted)
        self.calls: list[dict] = []

    def create(self, **kwargs: Any) -> Message:
        self.calls.append(kwargs)
        if not self._scripted:
            raise AssertionError(
                "FakeAnthropic ran out of scripted responses; "
                f"got an extra create() call with messages={kwargs.get('messages')!r}"
            )
        next_payload = self._scripted.pop(0)
        return Message.model_validate(next_payload)


class FakeAnthropic:
    """Stub mirroring the small slice of anthropic.Anthropic we use.

    Each scripted response is built via Message.model_validate so
    attribute access (.content, .stop_reason, .usage) matches the real
    SDK shape.
    """

    def __init__(self, scripted_responses: list[dict]) -> None:
        self.messages = _FakeMessages(scripted_responses)


@pytest.fixture
def fake_anthropic() -> Callable[[list[dict]], FakeAnthropic]:
    """Factory: tests pass a list of scripted Message payloads."""

    def _make(scripted: list[dict]) -> FakeAnthropic:
        return FakeAnthropic(scripted)

    return _make


def make_message(
    *,
    content: list[dict],
    stop_reason: str,
    msg_id: str = "msg_test",
    model: str = "claude-sonnet-4-5",
) -> dict:
    """Helper that constructs a payload validatable by Message.model_validate."""
    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
