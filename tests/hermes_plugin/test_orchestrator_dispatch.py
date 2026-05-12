"""Orchestrator dispatch tests — fanning out subagents, semaphore behavior,
refusal vs failure, citation rewriting, tools_called surfacing.

All tests mock ``run_skill_dynamic`` so no real LLM call is made; the
mock emulates the subagent's expected JSON output (or a failure mode)
and lets the orchestrator handle the result.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from hermes_plugin import orchestrator as orch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _subagent_response(
    summary: str = "ok",
    refused: bool = False,
    refusal_reason: str | None = None,
    citations: list[dict] | None = None,
) -> dict:
    """Build a well-formed subagent JSON response wrapped as run_skill_dynamic
    would return it (i.e. ``final_text`` is the JSON string)."""
    body = {
        "summary": summary,
        "citations": citations or [],
        "confidence": 0.8,
        "refused": refused,
        "refusal_reason": refusal_reason,
        "failed": False,
        "failure_reason": None,
        "tools_called": ["search_cards"],
    }
    return {"final_text": json.dumps(body), "tool_calls": [], "iterations": 1}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_subagent_refusal_propagates():
    """When subagent returns refused=true, dispatch_to_project carries it
    through with refused=True and failed=False (NOT conflated)."""

    def fake_run(*, system_prompt, tools, tool_schemas, user_message,
                 anthropic_client=None, model=None, max_iterations=10):
        return _subagent_response(
            summary="this project has no data on quantum computing",
            refused=True,
            refusal_reason="no data on quantum computing",
        )

    with patch("hermes_plugin.runtime.run_skill_dynamic", fake_run):
        out = asyncio.run(orch.dispatch_to_project("ws_a", "what about quantum?"))

    assert out["refused"] is True
    assert out["failed"] is False
    assert out["refusal_reason"] == "no data on quantum computing"


def test_subagent_failure_distinct_from_refusal():
    """A non-JSON subagent response → failed=true, refused=false."""

    def fake_run(*, system_prompt, tools, tool_schemas, user_message,
                 anthropic_client=None, model=None, max_iterations=10):
        return {"final_text": "I am not JSON, sorry.",
                "tool_calls": [{"name": "search_cards", "input": {}, "result": {}}],
                "iterations": 1}

    with patch("hermes_plugin.runtime.run_skill_dynamic", fake_run):
        out = asyncio.run(orch.dispatch_to_project("ws_a", "x"))

    assert out["failed"] is True
    assert out["refused"] is False
    assert "non-JSON" in out["failure_reason"]
    # tools_called should fall back to the runtime's tool_calls log.
    assert out["tools_called"] == ["search_cards"]


def test_dispatch_to_projects_semaphore_caps_at_three():
    """Five parallel dispatches; at most 3 in flight at any time."""

    in_flight = {"current": 0, "peak": 0}

    async def fake_dispatch(ws, task, **kw):
        in_flight["current"] += 1
        in_flight["peak"] = max(in_flight["peak"], in_flight["current"])
        # Simulate provider latency. With Semaphore(3) the loop should
        # see peak == 3 (3 enter immediately; 4th + 5th wait).
        await asyncio.sleep(0.05)
        in_flight["current"] -= 1
        return _subagent_response()

    async def _go():
        with patch.object(orch, "dispatch_to_project", fake_dispatch):
            return await orch.dispatch_to_projects(
                ["a", "b", "c", "d", "e"], "test"
            )

    out = asyncio.run(_go())
    assert len(out) == 5
    assert in_flight["peak"] <= 3, (
        f"semaphore breached: peak={in_flight['peak']} (expected ≤3)"
    )
    # And we should see at least 2 concurrent (otherwise the test is
    # vacuous — could happen if dispatches got serialized for some
    # other reason).
    assert in_flight["peak"] >= 2, (
        f"dispatches appear to have been serialized: peak={in_flight['peak']}"
    )


def test_dispatch_to_projects_empty_short_circuits():
    result = asyncio.run(orch.dispatch_to_projects([], "task"))
    assert result == []


def test_dispatch_to_project_normalizes_partial_json():
    """Subagent forgot some optional fields → dispatch fills defaults."""
    def fake_run(*, system_prompt, tools, tool_schemas, user_message,
                 anthropic_client=None, model=None, max_iterations=10):
        return {
            "final_text": json.dumps({"summary": "answer", "confidence": 0.9}),
            "tool_calls": [],
            "iterations": 1,
        }

    with patch("hermes_plugin.runtime.run_skill_dynamic", fake_run):
        out = asyncio.run(orch.dispatch_to_project("ws_a", "x"))

    assert out["summary"] == "answer"
    assert out["confidence"] == 0.9
    assert out["refused"] is False
    assert out["failed"] is False
    assert out["citations"] == []
    assert out["tools_called"] == []


def test_dispatch_to_project_handles_runtime_exception():
    """A raised exception is caught and becomes failed=true."""
    def fake_run(**kwargs):
        raise RuntimeError("provider 500")

    with patch("hermes_plugin.runtime.run_skill_dynamic", fake_run):
        out = asyncio.run(orch.dispatch_to_project("ws_a", "x"))

    assert out["failed"] is True
    assert out["refused"] is False
    assert "provider 500" in out["failure_reason"]
