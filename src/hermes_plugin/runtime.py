"""Anthropic tool-use loop wiring hermes-plugin tools into a skill prompt."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from . import chunker as _chunker_mod
from .chunker import Chunk, chunk_segments
from .client import StorageRouterClient
from .errors import ChunkedExtractionError, ToolError
from .schemas import TOOL_JSON_SCHEMAS
from .tools import TOOL_DESCRIPTIONS, TOOL_REGISTRY, get_meeting_transcript

logger = logging.getLogger(__name__)

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
    meeting_id: Optional[str] = None,
    *,
    user_question: Optional[str] = None,
    workspace_id: Optional[str] = None,
    client: Optional[StorageRouterClient] = None,
    anthropic_client: Optional["anthropic.Anthropic"] = None,
    model: str = "claude-sonnet-4-5",
    max_iterations: int = 16,
) -> dict:
    """Run a skill against Claude with all hermes-plugin tools bound.

    For meeting-scoped skills pass ``meeting_id``; for workspace-scoped
    skills (Wave 4.3 ``workspace-qa``) pass ``workspace_id`` and leave
    ``meeting_id`` as ``None``.

    Returns {"final_text": str, "tool_calls": list, "iterations": int}.
    Hitting ``max_iterations`` returns the partial result with
    ``iterations == max_iterations`` rather than raising.
    """
    system = _load_skill(skill_name)
    tools_param = _build_tools_param()
    bootstrap = _bootstrap_message(
        skill_name, meeting_id, user_question, workspace_id=workspace_id
    )

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


# ---------------------------------------------------------------------------
# Chunked extraction
# ---------------------------------------------------------------------------


def _format_ms(ms: Optional[int]) -> str:
    if ms is None:
        return "??:??"
    total_s = int(ms // 1000)
    return f"{total_s // 60:02d}:{total_s % 60:02d}"


def _render_chunk_text(chunk: Chunk) -> str:
    """Format a chunk's segments into the bootstrap user message body."""
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


def _build_chunk_tools_param() -> list[dict]:
    """Per-chunk extraction only needs create_draft_memory_card."""
    name = "create_draft_memory_card"
    return [
        {
            "name": name,
            "description": TOOL_DESCRIPTIONS[name],
            "input_schema": TOOL_JSON_SCHEMAS[name],
        }
    ]


def _run_chunk_loop(
    *,
    meeting_id: str,
    chunk: Chunk,
    chunk_count: int,
    system: str,
    storage_client: StorageRouterClient,
    llm: Any,
    model: str,
    max_iterations: int,
) -> tuple[int, str]:
    """Drive the per-chunk Claude loop. Returns (cards_created, final_text)."""
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
    messages: list[dict] = [{"role": "user", "content": bootstrap}]
    cards_created = 0
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
                is_error = False
                content_payload: Any = result
            except ToolError as exc:
                result = exc.to_payload()
                is_error = True
                content_payload = result

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "is_error": is_error,
                    "content": _stringify_result(content_payload),
                }
            )

        if not tool_results:
            break

        messages.append({"role": "user", "content": tool_results})

    final_text = _final_text(last_message) if last_message is not None else ""
    return cards_created, final_text


def _run_bounded_skill(
    *,
    skill_name: str,
    bootstrap: str,
    allowed_tools: list[str],
    storage_client: StorageRouterClient,
    llm: Any,
    model: str,
    max_iterations: int = 12,
) -> dict:
    """Generic bounded-tool-budget loop for the Wave 2 audit + consolidation passes.

    Mirrors the per-chunk loop but parameterised by skill prompt and the
    set of tools the agent is permitted to call. Any tool outside
    ``allowed_tools`` returns a tool error to the agent (which is then
    expected to give up that call). Returns
    ``{tool_calls: list, final_text: str, iterations: int}``.
    """
    system = _load_skill(skill_name)
    tools_param = [
        {
            "name": name,
            "description": TOOL_DESCRIPTIONS[name],
            "input_schema": TOOL_JSON_SCHEMAS[name],
        }
        for name in allowed_tools
    ]
    allowed_set = set(allowed_tools)

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
                if name not in allowed_set:
                    raise ToolError(
                        status_code=403,
                        code="tool_not_allowed",
                        message=(
                            f"Skill {skill_name!r} only permits "
                            f"{sorted(allowed_set)}; got {name!r}"
                        ),
                    )
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
            break

        messages.append({"role": "user", "content": tool_results})

    return {
        "final_text": _final_text(last_message) if last_message is not None else "",
        "tool_calls": tool_calls_log,
        "iterations": iterations,
    }


def run_card_audit(
    meeting_id: str,
    *,
    client: Optional[StorageRouterClient] = None,
    anthropic_client: Optional["anthropic.Anthropic"] = None,
    model: str = "claude-sonnet-4-5",
    max_iterations: int = 12,
) -> dict:
    """Wave 2.1: run the meeting-card-audit skill on a finalized meeting.

    Returns ``{cards_audited, cards_hidden, cards_downgraded, iterations}``.
    """
    storage_client = client if client is not None else StorageRouterClient()
    llm = anthropic_client if anthropic_client is not None else _default_anthropic_client()

    bootstrap = (
        f"meeting_id: {meeting_id}\n"
        "Audit every visible memory card for this meeting against the "
        "transcript. Downgrade weak cards via update_card_confidence; "
        "hide unsupported cards via hide_card. Report a one-paragraph "
        "summary at the end."
    )
    result = _run_bounded_skill(
        skill_name="meeting-card-audit",
        bootstrap=bootstrap,
        allowed_tools=[
            "get_meeting_transcript",
            "search_memory_cards",
            "update_card_confidence",
            "hide_card",
        ],
        storage_client=storage_client,
        llm=llm,
        model=model,
        max_iterations=max_iterations,
    )
    hidden = sum(
        1 for c in result["tool_calls"] if c["name"] == "hide_card"
    )
    downgraded = sum(
        1 for c in result["tool_calls"] if c["name"] == "update_card_confidence"
    )
    return {
        "cards_hidden": hidden,
        "cards_downgraded": downgraded,
        "iterations": result["iterations"],
        "summary": result["final_text"],
    }


def run_card_consolidation(
    meeting_id: str,
    *,
    client: Optional[StorageRouterClient] = None,
    anthropic_client: Optional["anthropic.Anthropic"] = None,
    model: str = "claude-sonnet-4-5",
    max_iterations: int = 12,
) -> dict:
    """Wave 2.2: run the meeting-card-consolidation skill.

    Returns ``{cards_merged, iterations, summary}``.
    """
    storage_client = client if client is not None else StorageRouterClient()
    llm = anthropic_client if anthropic_client is not None else _default_anthropic_client()

    bootstrap = (
        f"meeting_id: {meeting_id}\n"
        "Scan the remaining visible memory cards for this meeting. For "
        "every pair of cards that say substantially the same thing, "
        "pick the better one (winner) and merge the other (loser) via "
        "supersede_card(loser_id, winner_id). Report a one-paragraph "
        "summary at the end."
    )
    result = _run_bounded_skill(
        skill_name="meeting-card-consolidation",
        bootstrap=bootstrap,
        allowed_tools=["search_memory_cards", "supersede_card"],
        storage_client=storage_client,
        llm=llm,
        model=model,
        max_iterations=max_iterations,
    )
    merged = sum(
        1 for c in result["tool_calls"] if c["name"] == "supersede_card"
    )
    return {
        "cards_merged": merged,
        "iterations": result["iterations"],
        "summary": result["final_text"],
    }


def _run_summary_pass(
    *,
    topic_sentences: list[str],
    llm: Any,
    model: str,
) -> str:
    """One Claude call with no tools that consolidates topic sentences."""
    if not topic_sentences:
        return ""
    system = _load_skill("meeting-summary-overall")
    bootstrap = "\n".join(topic_sentences)
    msg = llm.messages.create(
        model=model,
        system=system,
        messages=[{"role": "user", "content": bootstrap}],
        max_tokens=1024,
    )
    return _final_text(msg)


def run_chunked_extraction(
    meeting_id: str,
    *,
    chunk_minutes: int = 5,
    prefetched_segments: Optional[list[dict]] = None,
    client: Optional[StorageRouterClient] = None,
    anthropic_client: Optional["anthropic.Anthropic"] = None,
    model: str = "claude-sonnet-4-5",
    max_iterations: int = 8,
) -> dict:
    """Run chunk-scoped extraction across a meeting transcript.

    Returns ``{cards_created, chunks_processed, summary}``.

    On a per-chunk Claude failure the function raises
    :class:`ChunkedExtractionError` carrying the partial-progress counts;
    cards persisted by completed chunks remain in storage.
    """
    storage_client = client if client is not None else StorageRouterClient()
    llm = anthropic_client if anthropic_client is not None else _default_anthropic_client()

    if prefetched_segments is None:
        transcript = get_meeting_transcript(
            {"meeting_id": meeting_id}, storage_client
        )
        segments = transcript.get("segments", [])
    else:
        segments = list(prefetched_segments)

    chunks = _chunker_mod.chunk_segments(segments, chunk_minutes=chunk_minutes)
    if not chunks:
        return {"cards_created": 0, "chunks_processed": 0, "summary": ""}

    system = _load_skill("meeting-memory-extraction-chunk")

    total_cards = 0
    chunks_processed = 0
    topic_sentences: list[str] = []

    for chunk in chunks:
        try:
            cards_in_chunk, final_text = _run_chunk_loop(
                meeting_id=meeting_id,
                chunk=chunk,
                chunk_count=len(chunks),
                system=system,
                storage_client=storage_client,
                llm=llm,
                model=model,
                max_iterations=max_iterations,
            )
        except Exception as exc:  # noqa: BLE001 — per-chunk boundary
            logger.exception(
                "chunked_extraction.chunk_failed",
                extra={
                    "meeting_id": meeting_id,
                    "chunk_index": chunk.index,
                    "chunks_processed": chunks_processed,
                    "cards_created": total_cards,
                },
            )
            raise ChunkedExtractionError(
                chunks_processed=chunks_processed,
                cards_created=total_cards,
                cause=exc,
            ) from exc
        total_cards += cards_in_chunk
        chunks_processed += 1
        if final_text:
            topic_sentences.append(final_text.strip())

    summary = _run_summary_pass(
        topic_sentences=topic_sentences, llm=llm, model=model
    )

    # Wave 2.1 + 2.2: agent quality passes run AFTER extraction. They
    # are best-effort — a failure here should not blow away the cards
    # the extraction pass already persisted; log + continue.
    audit_result: dict | None = None
    consolidation_result: dict | None = None
    try:
        audit_result = run_card_audit(
            meeting_id,
            client=storage_client,
            anthropic_client=llm,
            model=model,
        )
    except Exception:  # noqa: BLE001 — quality pass must not fail the extraction
        logger.exception(
            "chunked_extraction.audit_failed",
            extra={"meeting_id": meeting_id},
        )
    # Consolidation skill ships in Wave 2.2; in 2.1 the directory is
    # absent and the call would raise immediately. Only invoke it when
    # the skill is on disk so 2.1 ships in isolation.
    if (SKILLS_DIR / "meeting-card-consolidation" / "SKILL.md").is_file():
        try:
            consolidation_result = run_card_consolidation(
                meeting_id,
                client=storage_client,
                anthropic_client=llm,
                model=model,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "chunked_extraction.consolidation_failed",
                extra={"meeting_id": meeting_id},
            )

    return {
        "cards_created": total_cards,
        "chunks_processed": chunks_processed,
        "summary": summary,
        "audit": audit_result,
        "consolidation": consolidation_result,
    }


def run_live_extraction(
    meeting_id: str,
    since_ms: Optional[int],
    *,
    overlap_ms: int = 30_000,
    client: Optional[StorageRouterClient] = None,
    anthropic_client: Optional["anthropic.Anthropic"] = None,
    model: str = "claude-sonnet-4-5",
    max_iterations: int = 8,
) -> dict:
    """Wave 6.4: per-tick draft-card extraction over a recent transcript window.

    Pulls the full transcript-so-far for ``meeting_id``, filters it to
    the window ``[max(0, since_ms - overlap_ms), latest_end_ms]``, and
    drives the ``live-meeting-extraction`` skill over that window with
    only ``create_draft_memory_card`` bound. Returns
    ``{cards_created, window_start_ms, window_end_ms, summary, iterations}``.

    The ``since_ms`` argument is the ``last_live_extraction_end_ms``
    high-water mark from the previous tick (None on the first tick —
    we then process from time zero up to the latest segment). The 30s
    overlap is so a finding spoken across a tick boundary is caught
    by the adjacent window; the consolidation pass at /end merges
    duplicates.

    The caller (the live scheduler) is responsible for persisting the
    returned ``window_end_ms`` back to ``meetings.last_live_extraction_end_ms``
    so the next tick advances the watermark.
    """
    storage_client = client if client is not None else StorageRouterClient()
    llm = (
        anthropic_client
        if anthropic_client is not None
        else _default_anthropic_client()
    )

    transcript = get_meeting_transcript(
        {"meeting_id": meeting_id}, storage_client
    )
    segments: list[dict] = transcript.get("segments", [])
    if not segments:
        return {
            "cards_created": 0,
            "window_start_ms": since_ms or 0,
            "window_end_ms": since_ms or 0,
            "summary": "",
            "iterations": 0,
        }

    # Compute window. ``since_ms is None`` -> start at 0 (first tick).
    base_since = since_ms if since_ms is not None else 0
    window_start = max(0, base_since - overlap_ms)
    # The "now" cap is the latest segment we've seen. We deliberately
    # do NOT trust wall-clock here — we want the watermark to advance
    # in transcript time, not real time, so a slow STT path doesn't
    # cause us to skip ahead.
    end_candidates = [
        s.get("end_ms") for s in segments if s.get("end_ms") is not None
    ]
    if not end_candidates:
        # No segment has a known end time — bail rather than emit a
        # zero-width window.
        return {
            "cards_created": 0,
            "window_start_ms": window_start,
            "window_end_ms": window_start,
            "summary": "",
            "iterations": 0,
        }
    window_end = max(int(x) for x in end_candidates)

    # Filter segments to the window. Keep a segment if any portion of
    # it overlaps [window_start, window_end] — we err on the side of
    # inclusion so the model sees boundary segments in full.
    in_window: list[dict] = []
    for seg in segments:
        seg_start = seg.get("start_ms")
        seg_end = seg.get("end_ms")
        if seg_start is None:
            continue
        if seg_end is None:
            seg_end = seg_start
        if seg_end < window_start:
            continue
        if seg_start > window_end:
            continue
        in_window.append(seg)

    if not in_window:
        return {
            "cards_created": 0,
            "window_start_ms": window_start,
            "window_end_ms": window_end,
            "summary": "",
            "iterations": 0,
        }

    # Reuse the chunk-loop infra: build a synthetic Chunk and call the
    # same per-chunk runner, but pointed at the live skill prompt.
    synthetic_chunk = Chunk(
        index=0,
        start_ms=window_start,
        end_ms=window_end,
        segments=in_window,
        speakers=_collect_speakers_from_segments(in_window),
    )
    system = _load_skill("live-meeting-extraction")
    cards_in_window, final_text = _run_chunk_loop(
        meeting_id=meeting_id,
        chunk=synthetic_chunk,
        chunk_count=1,
        system=system,
        storage_client=storage_client,
        llm=llm,
        model=model,
        max_iterations=max_iterations,
    )
    return {
        "cards_created": cards_in_window,
        "window_start_ms": window_start,
        "window_end_ms": window_end,
        "summary": (final_text or "").strip(),
        "iterations": 1,
    }


def _collect_speakers_from_segments(segments: list[dict]) -> list[str]:
    """De-duped speaker names in first-seen order (live-extraction helper)."""
    seen: dict[str, None] = {}
    for s in segments:
        name = s.get("speaker_name")
        if name and name not in seen:
            seen[name] = None
    return list(seen.keys())


def run_live_summary(
    meeting_id: str,
    *,
    client: Optional[StorageRouterClient] = None,
    anthropic_client: Optional["anthropic.Anthropic"] = None,
    model: str = "claude-sonnet-4-5",
    max_iterations: int = 4,
) -> dict:
    """Wave 6.3: rolling summary tick during a live meeting.

    Drives the ``live-meeting-summary`` skill with only
    ``get_meeting_transcript`` bound. Returns
    ``{"summary": str, "iterations": int}``. The caller (the live
    scheduler) is responsible for persisting the returned ``summary``
    to ``meetings.live_summary``.
    """
    storage_client = client if client is not None else StorageRouterClient()
    llm = (
        anthropic_client
        if anthropic_client is not None
        else _default_anthropic_client()
    )

    bootstrap = (
        f"meeting_id: {meeting_id}\n"
        "Call get_meeting_transcript once for this meeting, then write a "
        "3-5 sentence rolling summary of what has been discussed so far. "
        "End your turn with the summary as plain text."
    )
    result = _run_bounded_skill(
        skill_name="live-meeting-summary",
        bootstrap=bootstrap,
        allowed_tools=["get_meeting_transcript"],
        storage_client=storage_client,
        llm=llm,
        model=model,
        max_iterations=max_iterations,
    )
    return {
        "summary": (result.get("final_text") or "").strip(),
        "iterations": result.get("iterations", 0),
    }


__all__ = [
    "run_skill",
    "run_chunked_extraction",
    "run_card_audit",
    "run_card_consolidation",
    "run_live_summary",
    "run_live_extraction",
]
