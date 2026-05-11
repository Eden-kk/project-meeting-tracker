"""Anthropic tool-use loop wiring hermes-plugin tools into a skill prompt."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .client import StorageRouterClient
from .errors import ToolError
from .schemas import TOOL_JSON_SCHEMAS
from .tools import TOOL_DESCRIPTIONS, TOOL_REGISTRY

if TYPE_CHECKING:  # pragma: no cover
    import anthropic


SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def _load_skill(skill_name: str) -> str:
    path = SKILLS_DIR / skill_name / "SKILL.md"
    if not path.is_file():
        raise ValueError(f"Unknown skill: {skill_name!r} (expected {path})")
    return path.read_text(encoding="utf-8")


def _build_tools_param() -> list[dict]:
    return [
        {
            "name": name,
            "description": TOOL_DESCRIPTIONS[name],
            "input_schema": TOOL_JSON_SCHEMAS[name],
        }
        for name in TOOL_REGISTRY
    ]


def _bootstrap_message(skill_name: str, meeting_id: str, user_question: Optional[str]) -> str:
    if skill_name == "meeting-qa":
        if not user_question:
            raise ValueError("user_question is required for meeting-qa skill")
        return f"Meeting: {meeting_id}\nQuestion: {user_question}"
    return f"Process meeting {meeting_id}."


def _default_anthropic_client() -> "anthropic.Anthropic":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    import anthropic

    return anthropic.Anthropic()


def _block_attr(block: Any, name: str) -> Any:
    """Read an attribute from a block whether it's a Pydantic model or a dict."""
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _final_text(message: Any) -> str:
    parts: list[str] = []
    for block in _block_attr(message, "content") or []:
        if _block_attr(block, "type") == "text":
            text = _block_attr(block, "text") or ""
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def _serialize_tool_input(value: Any) -> Any:
    """Anthropic tool_use.input is a dict already; pass through defensively."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    # Pydantic model fallback (newer SDK builds may return a model)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)


def run_skill(
    skill_name: str,
    meeting_id: str,
    *,
    user_question: Optional[str] = None,
    client: Optional[StorageRouterClient] = None,
    anthropic_client: Optional["anthropic.Anthropic"] = None,
    model: str = "claude-sonnet-4-5",
    max_iterations: int = 16,
) -> dict:
    """Run a skill against Claude with the four hermes-plugin tools bound.

    Returns {"final_text": str, "tool_calls": list, "iterations": int}.
    Hitting ``max_iterations`` returns the partial result with
    ``iterations == max_iterations`` rather than raising.
    """
    system = _load_skill(skill_name)
    tools_param = _build_tools_param()
    bootstrap = _bootstrap_message(skill_name, meeting_id, user_question)

    storage_client = client if client is not None else StorageRouterClient()
    llm = anthropic_client if anthropic_client is not None else _default_anthropic_client()

    messages: list[dict] = [{"role": "user", "content": bootstrap}]
    tool_calls_log: list[dict] = []
    iterations = 0
    last_message: Any = None

    while iterations < max_iterations:
        iterations += 1
        last_message = llm.messages.create(
            model=model,
            system=system,
            tools=tools_param,
            messages=messages,
            max_tokens=4096,
        )

        # Re-attach the assistant turn so the tool_result blocks below
        # have the matching tool_use_id context.
        assistant_content = _block_attr(last_message, "content") or []
        messages.append({"role": "assistant", "content": assistant_content})

        stop_reason = _block_attr(last_message, "stop_reason")
        if stop_reason != "tool_use":
            break

        tool_results: list[dict] = []
        for block in assistant_content:
            if _block_attr(block, "type") != "tool_use":
                continue
            name = _block_attr(block, "name")
            tool_use_id = _block_attr(block, "id")
            tool_input = _serialize_tool_input(_block_attr(block, "input"))
            try:
                result = TOOL_REGISTRY[name](tool_input, storage_client)
                is_error = False
                content_payload: Any = result
            except ToolError as exc:
                result = exc.to_payload()
                is_error = True
                content_payload = result
            except KeyError:
                result = {
                    "status_code": 404,
                    "code": "unknown_tool",
                    "message": f"No such tool: {name!r}",
                }
                is_error = True
                content_payload = result

            tool_calls_log.append({"name": name, "input": tool_input, "result": result})
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "is_error": is_error,
                    "content": _stringify_result(content_payload),
                }
            )

        if not tool_results:
            # stop_reason said tool_use but no tool_use blocks present;
            # treat as end of loop to avoid spinning.
            break

        messages.append({"role": "user", "content": tool_results})

    return {
        "final_text": _final_text(last_message) if last_message is not None else "",
        "tool_calls": tool_calls_log,
        "iterations": iterations,
    }


def _stringify_result(payload: Any) -> str:
    """Tool results must be strings on the wire."""
    import json

    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False, default=str)


__all__ = ["run_skill"]
