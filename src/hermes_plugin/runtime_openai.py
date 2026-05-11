"""OpenAI native chat.completions tool-use loop wiring hermes-plugin tools.

Mirrors :mod:`hermes_plugin.runtime` for OpenAI's chat.completions API.

Single-skill loop only; chunked extraction is Anthropic-only for this
iteration. The same ``TOOL_REGISTRY`` and SKILL.md prompts are reused;
only the wire-protocol shape differs:

* System prompt rides as ``messages[0]`` with ``role="system"``.
* Tools are declared as ``[{"type": "function", "function": {...}}]``.
* Tool calls come back as ``message.tool_calls[]`` with stringified JSON
  arguments; results go back as ``role="tool"`` messages keyed by
  ``tool_call_id``.
* ``finish_reason == "tool_calls"`` continues the loop; anything else
  ends it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .client import StorageRouterClient
from .errors import ToolError
from .schemas import TOOL_JSON_SCHEMAS
from .tools import TOOL_DESCRIPTIONS, TOOL_REGISTRY

if TYPE_CHECKING:  # pragma: no cover
    import openai


SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def _load_skill(skill_name: str) -> str:
    path = SKILLS_DIR / skill_name / "SKILL.md"
    if not path.is_file():
        raise ValueError(f"Unknown skill: {skill_name!r} (expected {path})")
    return path.read_text(encoding="utf-8")


def _build_tools_param() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": TOOL_JSON_SCHEMAS[name],
            },
        }
        for name in TOOL_REGISTRY
    ]


def _bootstrap_message(skill_name: str, meeting_id: str, user_question: Optional[str]) -> str:
    if skill_name == "meeting-qa":
        if not user_question:
            raise ValueError("user_question is required for meeting-qa skill")
        return f"Meeting: {meeting_id}\nQuestion: {user_question}"
    return f"Process meeting {meeting_id}."


def _default_openai_client() -> "openai.OpenAI":
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not set")
    import openai

    base_url = os.environ.get("OPENAI_BASE_URL") or None
    kwargs = {"base_url": base_url} if base_url else {}
    return openai.OpenAI(**kwargs)


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read an attribute whether ``obj`` is a Pydantic model or a dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _final_text(message: Any) -> str:
    """Extract the assistant text out of a chat.completions choice message."""
    text = _attr(message, "content")
    if text is None:
        return ""
    if isinstance(text, str):
        return text
    # Some OpenAI responses use a list of content parts; collect "text" pieces.
    parts: list[str] = []
    for part in text:
        if _attr(part, "type") == "text":
            t = _attr(part, "text") or ""
            if t:
                parts.append(t)
    return "\n\n".join(parts)


def _parse_tool_arguments(raw: Any) -> dict:
    """OpenAI returns function.arguments as a JSON-encoded string."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw_arguments": raw}
        return parsed if isinstance(parsed, dict) else {"_raw_arguments": parsed}
    if hasattr(raw, "model_dump"):
        return raw.model_dump()
    return dict(raw)


def _stringify_result(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False, default=str)


def _serialize_tool_calls_for_history(tool_calls: list[Any]) -> list[dict]:
    """Re-encode tool_calls into the dict shape the API expects on the next turn."""
    out: list[dict] = []
    for tc in tool_calls:
        function = _attr(tc, "function")
        out.append(
            {
                "id": _attr(tc, "id"),
                "type": "function",
                "function": {
                    "name": _attr(function, "name"),
                    "arguments": _attr(function, "arguments") or "{}",
                },
            }
        )
    return out


def run_skill(
    skill_name: str,
    meeting_id: str,
    *,
    user_question: Optional[str] = None,
    client: Optional[StorageRouterClient] = None,
    openai_client: Optional["openai.OpenAI"] = None,
    model: str = "gpt-4o-2024-11-20",
    max_iterations: int = 16,
) -> dict:
    """Run a skill against OpenAI with the four hermes-plugin tools bound.

    Returns ``{"final_text": str, "tool_calls": list, "iterations": int}``.
    Hitting ``max_iterations`` returns the partial result with
    ``iterations == max_iterations`` rather than raising.
    """
    system = _load_skill(skill_name)
    tools_param = _build_tools_param()
    bootstrap = _bootstrap_message(skill_name, meeting_id, user_question)

    storage_client = client if client is not None else StorageRouterClient()
    llm = openai_client if openai_client is not None else _default_openai_client()

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": bootstrap},
    ]
    tool_calls_log: list[dict] = []
    iterations = 0
    last_message: Any = None

    while iterations < max_iterations:
        iterations += 1
        response = llm.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools_param,
            max_tokens=4096,
        )

        choices = _attr(response, "choices") or []
        if not choices:
            break
        choice = choices[0]
        last_message = _attr(choice, "message")
        finish_reason = _attr(choice, "finish_reason")
        tool_calls = _attr(last_message, "tool_calls") or []

        # Re-attach the assistant turn so subsequent tool messages have
        # matching ``tool_call_id`` context.
        assistant_entry: dict = {
            "role": "assistant",
            "content": _attr(last_message, "content"),
        }
        if tool_calls:
            assistant_entry["tool_calls"] = _serialize_tool_calls_for_history(tool_calls)
        messages.append(assistant_entry)

        if finish_reason != "tool_calls" or not tool_calls:
            break

        for tc in tool_calls:
            tool_call_id = _attr(tc, "id")
            function = _attr(tc, "function")
            name = _attr(function, "name")
            tool_input = _parse_tool_arguments(_attr(function, "arguments"))

            try:
                result = TOOL_REGISTRY[name](tool_input, storage_client)
                content_payload: Any = result
            except ToolError as exc:
                result = exc.to_payload()
                content_payload = result
            except KeyError:
                result = {
                    "status_code": 404,
                    "code": "unknown_tool",
                    "message": f"No such tool: {name!r}",
                }
                content_payload = result

            tool_calls_log.append({"name": name, "input": tool_input, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": _stringify_result(content_payload),
                }
            )

    return {
        "final_text": _final_text(last_message) if last_message is not None else "",
        "tool_calls": tool_calls_log,
        "iterations": iterations,
    }


__all__ = ["run_skill"]
