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
import re
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


def _bootstrap_message(
    skill_name: str,
    meeting_id: Optional[str],
    user_question: Optional[str],
    workspace_id: Optional[str] = None,
) -> str:
    if skill_name == "meeting-qa":
        if not user_question:
            raise ValueError("user_question is required for meeting-qa skill")
        return f"Meeting: {meeting_id}\nQuestion: {user_question}"
    if skill_name == "workspace-qa":
        if not user_question:
            raise ValueError("user_question is required for workspace-qa skill")
        if not workspace_id:
            raise ValueError("workspace_id is required for workspace-qa skill")
        return (
            f"Workspace: {workspace_id}\n"
            f"Question: {user_question}\n\n"
            "Use the cross-meeting search tools to find evidence. Cite every "
            "claim with [meeting:<id>:card:<id>] or [meeting:<id>:seg:<id>]."
        )
    return f"Process meeting {meeting_id}."


def _default_openai_client() -> "openai.OpenAI":
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not set")
    import openai

    base_url = os.environ.get("OPENAI_BASE_URL") or None
    # The openai SDK (≥ 2.x) also reads OPENAI_BASE_URL from the environment
    # on its own. An empty-string value causes it to use "" as the base URL
    # and fail with a connection error. Pass `base_url=` explicitly so we own
    # the resolved value, and temporarily unset the env var so the SDK's own
    # env-reading path cannot pick up the empty string.
    _sentinel = object()
    _old = os.environ.pop("OPENAI_BASE_URL", _sentinel)
    try:
        client = openai.OpenAI(base_url=base_url)
    finally:
        if _old is not _sentinel:
            os.environ["OPENAI_BASE_URL"] = _old  # type: ignore[assignment]
    return client


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
    meeting_id: Optional[str] = None,
    *,
    user_question: Optional[str] = None,
    workspace_id: Optional[str] = None,
    client: Optional[StorageRouterClient] = None,
    openai_client: Optional["openai.OpenAI"] = None,
    model: str = "gpt-4o-2024-11-20",
    max_iterations: int = 16,
) -> dict:
    """Run a skill against OpenAI with all hermes-plugin tools bound.

    For workspace-scoped skills (Wave 4.3 ``workspace-qa``) pass
    ``workspace_id`` and leave ``meeting_id`` as ``None``.

    Returns ``{"final_text": str, "tool_calls": list, "iterations": int}``.
    Hitting ``max_iterations`` returns the partial result with
    ``iterations == max_iterations`` rather than raising.
    """
    system = _load_skill(skill_name)
    tools_param = _build_tools_param()
    bootstrap = _bootstrap_message(
        skill_name, meeting_id, user_question, workspace_id=workspace_id
    )

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


# ---------------------------------------------------------------------------
# Dynamic skill runner (per-project orchestrator + subagent path; OpenAI)
# ---------------------------------------------------------------------------
#
# Mirror of ``hermes_plugin.runtime.run_skill_dynamic`` for the OpenAI
# wire shape. Intentionally a STANDALONE function (not a refactor of
# ``run_skill``'s loop body) to keep the production meeting-finalization
# path untouched.


def run_skill_dynamic(
    *,
    system_prompt: str,
    tools: dict[str, Any],
    tool_schemas: list[dict],
    user_message: str,
    max_iterations: int = 10,
    openai_client: Optional["openai.OpenAI"] = None,
    anthropic_client: Any = None,  # accepted + ignored for signature parity
    model: Optional[str] = None,
) -> dict:
    """OpenAI chat.completions tool-use loop with caller-supplied prompt + tools.

    ``tool_schemas`` here is a list of Anthropic-shape dicts
    ``{name, description, input_schema}``; this function re-wraps them
    into the OpenAI ``{type: function, function: {name, description, parameters}}``
    shape so callers don't have to know which provider they're talking
    to. Callables are invoked with ``**tool_input`` kwargs (NOT the
    ``(args, client)`` shape of the static TOOL_REGISTRY).
    """
    if model is None:
        model = "gpt-4o-2024-11-20"

    llm = openai_client if openai_client is not None else _default_openai_client()
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t["input_schema"],
            },
        }
        for t in tool_schemas
    ]
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    tool_calls_log: list[dict] = []
    iterations = 0
    last_message: Any = None

    while iterations < max_iterations:
        iterations += 1
        response = llm.chat.completions.create(
            model=model,
            messages=messages,
            tools=openai_tools,
            max_tokens=4096,
        )
        choices = _attr(response, "choices") or []
        if not choices:
            break
        choice = choices[0]
        last_message = _attr(choice, "message")
        finish_reason = _attr(choice, "finish_reason")
        tool_calls = _attr(last_message, "tool_calls") or []

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
                fn = tools[name]
            except KeyError:
                result = {
                    "status_code": 404,
                    "code": "unknown_tool",
                    "message": f"No such tool: {name!r}",
                }
                tool_calls_log.append({"name": name, "input": tool_input, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": _stringify_result(result),
                    }
                )
                continue
            try:
                result = fn(**tool_input) if isinstance(tool_input, dict) else fn(tool_input)
                content_payload: Any = result
            except ToolError as exc:
                result = exc.to_payload()
                content_payload = result
            except TypeError as exc:
                result = {
                    "status_code": 422,
                    "code": "invalid_input",
                    "message": str(exc),
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


def _build_chunk_tools_param() -> list[dict]:
    """Per-chunk extraction only needs create_draft_memory_card."""
    name = "create_draft_memory_card"
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": TOOL_JSON_SCHEMAS[name],
            },
        }
    ]


def _format_ms(ms: Optional[int]) -> str:
    if ms is None:
        return "??:??"
    total_s = int(ms // 1000)
    return f"{total_s // 60:02d}:{total_s % 60:02d}"


def _render_chunk_text(chunk: Any) -> str:
    lines: list[str] = []
    for seg in chunk.segments:
        seg_id = seg.get("segment_id", "?")
        speaker = seg.get("speaker_name") or "unknown"
        start = seg.get("start_ms")
        end = seg.get("end_ms")
        ts = f"{_format_ms(start)}-{_format_ms(end)}"
        text = seg.get("text", "")
        lines.append(f"[{seg_id}  {ts}  {speaker}] {text}")
    return "\n".join(lines)


def _run_openai_chunk_loop(
    *,
    meeting_id: str,
    chunk: Any,
    chunk_count: int,
    system: str,
    storage_client: StorageRouterClient,
    llm: "openai.OpenAI",
    model: str,
    max_iterations: int,
) -> tuple[int, str]:
    """Drive the per-chunk OpenAI loop. Returns (cards_created, final_text)."""
    chunk_text = _render_chunk_text(chunk)
    bootstrap = (
        f"meeting_id: {meeting_id}\n"
        f"chunk_index: {chunk.index}\n"
        f"chunk_count: {chunk_count}\n"
        f"window_start: {_format_ms(chunk.start_ms)}\n"
        f"window_end: {_format_ms(chunk.end_ms)}\n"
        f"speakers: {', '.join(chunk.speakers) if chunk.speakers else '(unknown)'}\n"
        f"\n--- transcript window ---\n{chunk_text}\n--- end window ---"
    )

    tools_param = _build_chunk_tools_param()
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": bootstrap},
    ]
    cards_created = 0
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
                if name != "create_draft_memory_card":
                    raise ToolError(
                        status_code=403,
                        code="tool_not_allowed",
                        message=(
                            f"Chunked extraction only permits create_draft_memory_card; "
                            f"got {name!r}"
                        ),
                    )
                result = TOOL_REGISTRY[name](tool_input, storage_client)
                cards_created += 1
                content_payload: Any = result
            except ToolError as exc:
                result = exc.to_payload()
                content_payload = result

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": _stringify_result(content_payload),
                }
            )

    final_text = _final_text(last_message) if last_message is not None else ""
    return cards_created, final_text


# Threshold above which single-pass OpenAI extraction is replaced by
# chunked extraction. 60 000 chars ≈ 15 000 tokens — safely under gpt-4o's
# 128 K context, but the single-pass path needs the whole transcript as a
# tool-call result plus 4 096 output tokens; chunking avoids that wall.
_SINGLE_PASS_CHAR_LIMIT = 60_000


def run_chunked_extraction_openai(
    meeting_id: str,
    *,
    chunk_minutes: int = 5,
    segments: list[dict],
    client: Optional[StorageRouterClient] = None,
    openai_client: Optional["openai.OpenAI"] = None,
    model: str = "gpt-4o-2024-11-20",
    max_iterations: int = 8,
) -> dict:
    """Chunked extraction for OpenAI: split segments into time windows and
    run ``meeting-memory-extraction-chunk`` once per window.

    Returns ``{"cards_created": int, "chunks_processed": int, "summary": str}``.
    """
    from .chunker import chunk_segments as _chunk_segments

    storage_client = client if client is not None else StorageRouterClient()
    llm = openai_client if openai_client is not None else _default_openai_client()
    system = _load_skill("meeting-memory-extraction-chunk")

    chunks = _chunk_segments(segments, chunk_minutes=chunk_minutes)
    if not chunks:
        return {"cards_created": 0, "chunks_processed": 0, "summary": ""}

    total_cards = 0
    chunks_processed = 0
    topic_sentences: list[str] = []

    for chunk in chunks:
        cards_in_chunk, final_text = _run_openai_chunk_loop(
            meeting_id=meeting_id,
            chunk=chunk,
            chunk_count=len(chunks),
            system=system,
            storage_client=storage_client,
            llm=llm,
            model=model,
            max_iterations=max_iterations,
        )
        total_cards += cards_in_chunk
        chunks_processed += 1
        if final_text:
            topic_sentences.append(_strip_chunk_prefix(final_text.strip()))

    summary = _run_openai_summary_pass(
        meeting_id=meeting_id,
        topic_sentences=topic_sentences,
        storage_client=storage_client,
        llm=llm,
        model=model,
    )
    return {
        "cards_created": total_cards,
        "chunks_processed": chunks_processed,
        "summary": summary,
    }


# Legacy chunk-skill outputs sometimes started with `Chunk N/M:`; the
# updated skill drops the prefix but we strip it defensively in case a
# stale skill version is on disk.
_CHUNK_PREFIX_RE = re.compile(r"^\s*Chunk\s+\d+\s*/\s*\d+\s*:\s*", flags=re.IGNORECASE)


def _strip_chunk_prefix(line: str) -> str:
    return _CHUNK_PREFIX_RE.sub("", line).strip()


_SUMMARY_TRANSCRIPT_CHAR_BUDGET = 80_000


def _strip_wrapping_fence(text: str) -> str:
    """Drop a triple-backtick code fence wrapping the whole summary.

    The summary skill asks for raw markdown with no fenced code block,
    but the model sometimes wraps the entire output in ```` ``` ```` (or
    ```` ```markdown ````). The SPA then renders a literal code block
    instead of formatted markdown. Strip a single wrapping fence; leave
    fences in the interior untouched.
    """
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _format_transcript_for_summary(segments: list[dict]) -> str:
    """Render transcript segments into `[mm:ss spkr] text` lines.

    Speaker uses ``speaker_name`` when set (post-rename), falls back to
    ``speaker_id`` so diarization labels are still visible.
    """
    out: list[str] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start_ms = int(seg.get("start_ms") or 0)
        total_s = start_ms // 1000
        mm = total_s // 60
        ss = total_s % 60
        speaker = (
            seg.get("speaker_name")
            or seg.get("speaker_id")
            or "speaker_?"
        )
        out.append(f"[{mm:02d}:{ss:02d} {speaker}] {text}")
    return "\n".join(out)


def _run_openai_summary_pass(
    *,
    meeting_id: str,
    topic_sentences: list[str],
    storage_client: StorageRouterClient,
    llm: Any,
    model: str,
) -> str:
    """Single-shot OpenAI summary pass. Reads the actual transcript via
    `client.get_meeting_transcript` and writes a narrative summary from
    real content. Falls back to `topic_sentences` if the transcript
    fetch fails or exceeds the char budget. Mirrors
    `runtime._run_summary_pass`.
    """
    system = _load_skill("meeting-summary-overall")
    user_text = ""
    try:
        transcript = storage_client.get_meeting_transcript(meeting_id)
        segments = transcript.get("segments") or []
        formatted = _format_transcript_for_summary(segments)
        if formatted and len(formatted) <= _SUMMARY_TRANSCRIPT_CHAR_BUDGET:
            user_text = formatted
    except Exception:  # noqa: BLE001 — fall back to topic_sentences below
        pass
    if not user_text:
        if not topic_sentences:
            return ""
        user_text = "\n".join(topic_sentences)
    response = llm.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        max_tokens=1024,
    )
    text = (response.choices[0].message.content or "").strip()
    return _strip_wrapping_fence(text)


__all__ = ["run_skill", "run_chunked_extraction_openai", "_SINGLE_PASS_CHAR_LIMIT"]
