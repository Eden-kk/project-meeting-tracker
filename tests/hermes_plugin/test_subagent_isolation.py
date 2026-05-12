"""Subagent isolation tests — the load-bearing schema-isolation primitive.

These four tests guard the invariant that ``bind_subagent_tools`` produces
LLM-visible tool schemas + callables with NO ``workspace_id`` parameter.
A regression here re-opens the cross-project leak vector.
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

from hermes_plugin import orchestrator as orch


def test_tool_schemas_omit_workspace_id() -> None:
    """LLM-visible schema check: no schema's properties contain workspace_id."""
    callables, schemas = orch.bind_subagent_tools("ws_a")
    assert set(callables.keys()) == {
        "search_cards",
        "search_transcripts",
        "get_meeting_transcript",
        "list_meeting_cards",
    }
    for schema in schemas:
        props = schema["input_schema"].get("properties", {})
        assert "workspace_id" not in props, (
            f"workspace_id leaked into schema for {schema['name']}; "
            "isolation primitive broken"
        )


def test_bound_callable_signature_omits_workspace_id() -> None:
    """Structural guard. ``functools.partial(fn, value)`` (positional) MUST
    remove ``workspace_id`` from ``inspect.signature(callable).parameters``.
    The kwarg form ``partial(fn, workspace_id=value)`` would leave it.
    """
    callables, _ = orch.bind_subagent_tools("ws_a")
    for name, fn in callables.items():
        sig = inspect.signature(fn)
        assert "workspace_id" not in sig.parameters, (
            f"workspace_id still in signature of bound {name!r}; "
            "isolation primitive broken — check that orchestrator uses "
            "positional functools.partial, NOT the kwarg form."
        )


def test_cross_project_leak_via_kwarg_raises() -> None:
    """Try to override the bound workspace_id by passing it as a kwarg —
    should raise TypeError because the positional value is already
    bound. (Multiple-values-for-argument or unexpected-kwarg, depending
    on whether the parameter is positional-only.)
    """
    callables, _ = orch.bind_subagent_tools("ws_a")
    fn = callables["search_cards"]
    with pytest.raises(TypeError):
        fn(q="x", workspace_id="ws_b")


def test_bound_tool_only_sees_bound_workspace() -> None:
    """Mock the underlying ``search_workspace_cards`` and call the bound
    callable; assert the ``args`` dict passed downstream carries
    ``workspace_id='ws_a'`` regardless of caller intent.
    """

    captured: list[dict] = []

    def _fake(args: dict, client):
        captured.append(args)
        return {"items": [{"memory_card_id": "c1", "meeting_id": "m1",
                            "type": "decision", "title": args.get("workspace_id", ""),
                            "content": "x"}], "total": 1}

    with patch.object(orch, "search_workspace_cards", _fake):
        callables, _ = orch.bind_subagent_tools("ws_a")
        out = callables["search_cards"](q="anything")

    assert captured == [{"workspace_id": "ws_a", "q": "anything", "limit": 10}]
    # Sanity: the fake returned ws_a in the title field; confirm.
    assert out["items"][0]["title"] == "ws_a"
