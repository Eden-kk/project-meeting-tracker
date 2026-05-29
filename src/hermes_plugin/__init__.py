"""Hermes plugin: meeting-memory tools for Claude tool-use loops.

Public surface:
- ``__version__``: package version literal.
- ``run_skill``: lazy attribute; resolved from ``hermes_plugin.runtime``.
- ``TOOL_REGISTRY``: lazy attribute; resolved from ``hermes_plugin.tools``.

Lazy resolution lets the bare ``import hermes_plugin`` work before the
later stages land. Accessing ``run_skill`` / ``TOOL_REGISTRY`` raises
``NotImplementedError`` until the implementing modules exist.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "run_skill",
    "TOOL_REGISTRY",
    "meeting_finalization",
    "meeting_qa",
    "followup_draft",
    "workspace_qa",
    "project_orchestrator",
    "live_topic_tracker",
    "live_summary",
    "live_extraction",
    "live_interview_questions",
]


def meeting_finalization(
    meeting_id: str,
    chunk_minutes: int | None = 5,
) -> dict:
    """Storage-router-facing entrypoint for /api/meetings/{id}/finalize.

    Routing (provider-aware):
      - ``LLM_PROVIDER=anthropic`` + non-empty transcript + ``chunk_minutes``
        set: :func:`runtime.run_chunked_extraction`. Timestamped transcripts
        are split into time windows; untimestamped ones collapse to a single
        chunk via the chunker's degraded-mode fallback. Both run
        extraction → audit → consolidation.
      - ``LLM_PROVIDER=openai`` (or any non-anthropic provider) + non-empty
        transcript: single-pass ``meeting-memory-extraction`` skill (routed
        via the LLM dispatcher) followed by audit + consolidation. This path
        works for both timestamped and untimestamped transcripts.
      - Edge-case fallback (empty transcript or ``chunk_minutes=None``):
        legacy single-pass ``meeting-finalization`` skill (audit-only, no
        extraction — caller should ensure cards exist).
    """
    # Local imports keep `import hermes_plugin` cheap.
    import os

    from .client import StorageRouterClient
    from .llm import run_skill as _run_skill
    from .runtime import (
        SKILLS_DIR as _SKILLS_DIR,
        run_card_audit as _run_audit,
        run_card_consolidation as _run_consolidation,
        run_chunked_extraction as _run_chunked,
    )
    from .tools import get_meeting_transcript as _get_transcript

    storage_client = StorageRouterClient()
    transcript = _get_transcript({"meeting_id": meeting_id}, storage_client)
    segments = transcript.get("segments", [])

    # Determine LLM provider.  `run_chunked_extraction` drives the Anthropic
    # tool-use loop directly; it is not routed through the LLM dispatcher.
    # When LLM_PROVIDER=openai we must use the dispatcher-backed single-pass
    # `meeting-memory-extraction` skill instead, which has identical card-
    # creation semantics but works with chat.completions.
    provider = (os.environ.get("LLM_PROVIDER") or "anthropic").strip().lower()

    if chunk_minutes is not None and segments and provider == "anthropic":
        # Anthropic path: time-windowed chunked extraction.  Untimestamped
        # transcripts degrade to a single chunk inside chunk_segments().
        return _run_chunked(
            meeting_id,
            chunk_minutes=chunk_minutes,
            prefetched_segments=segments,
            client=storage_client,
        )

    if segments and provider != "anthropic":
        # OpenAI (or other dispatcher-routed) path.
        # For large transcripts (> _SINGLE_PASS_CHAR_LIMIT chars of text),
        # fall back to chunked extraction to stay within the 4096 output-
        # token cap: the single-pass path feeds the whole transcript as a
        # tool-call result and then asks the model to emit N card calls in
        # one response, which silently produces 0 cards when the transcript
        # is long.  The chunked path passes only one time-window per call.
        import json as _json

        from .runtime_openai import (
            _SINGLE_PASS_CHAR_LIMIT,
            run_chunked_extraction_openai as _run_chunked_openai,
        )

        # Serialize to measure what actually arrives as the tool-call result.
        transcript_json_len = len(_json.dumps({"segments": segments}))

        if chunk_minutes is not None and transcript_json_len > _SINGLE_PASS_CHAR_LIMIT:
            # Large transcript: chunk it.
            result = _run_chunked_openai(
                meeting_id,
                chunk_minutes=chunk_minutes,
                segments=segments,
                client=storage_client,
            )
            audit_result: dict | None = None
            consolidation_result: dict | None = None
            try:
                audit_result = _run_audit(meeting_id, client=storage_client)
            except Exception:  # noqa: BLE001
                pass
            if (_SKILLS_DIR / "meeting-card-consolidation" / "SKILL.md").is_file():
                try:
                    consolidation_result = _run_consolidation(
                        meeting_id, client=storage_client
                    )
                except Exception:  # noqa: BLE001
                    pass
            result["audit"] = audit_result
            result["consolidation"] = consolidation_result
            return result

        # Small transcript: single-pass extraction using the full
        # `meeting-memory-extraction` skill (model calls get_meeting_transcript
        # itself, then emits create_draft_memory_card calls).
        extraction = _run_skill(
            skill_name="meeting-memory-extraction",
            meeting_id=meeting_id,
            user_question=None,
            client=storage_client,
        )
        cards_created = sum(
            1
            for c in extraction.get("tool_calls", [])
            if c.get("name") == "create_draft_memory_card"
            and not (isinstance(c.get("result"), dict) and c["result"].get("error"))
        )
        audit_result = None
        consolidation_result = None
        try:
            audit_result = _run_audit(meeting_id, client=storage_client)
        except Exception:  # noqa: BLE001
            pass
        if (_SKILLS_DIR / "meeting-card-consolidation" / "SKILL.md").is_file():
            try:
                consolidation_result = _run_consolidation(
                    meeting_id, client=storage_client
                )
            except Exception:  # noqa: BLE001
                pass
        # Replace the extraction skill's `final_text` (a bookkeeping line
        # like "Created N cards covering …") with a real narrative
        # summary written from the actual transcript. This mirrors the
        # chunked path's summary-pass step — without it the SPA's Summary
        # tab shows the meta line instead of "the team discussed X".
        try:
            from .runtime_openai import (
                _run_openai_summary_pass as _run_openai_summary,
                _default_openai_client as _openai_client,
            )
            narrative = _run_openai_summary(
                meeting_id=meeting_id,
                topic_sentences=[],
                storage_client=storage_client,
                llm=_openai_client(),
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-2024-11-20"),
            )
            summary_text = narrative or extraction.get("final_text", "")
        except Exception:  # noqa: BLE001 — never fail finalize over summary
            summary_text = extraction.get("final_text", "")
        return {
            "cards_created": cards_created,
            "chunks_processed": 1,
            "summary": summary_text,
            "audit": audit_result,
            "consolidation": consolidation_result,
        }

    # Edge-case: empty transcript or chunk_minutes=None — fall back to the
    # legacy single-pass skill to avoid a silent no-op.
    legacy = _run_skill(
        skill_name="meeting-finalization",
        meeting_id=meeting_id,
        user_question=None,
        client=storage_client,
    )
    # Normalize to the chunked-shape contract.
    if isinstance(legacy, dict):
        legacy.setdefault("chunks_processed", 1)
        legacy.setdefault("cards_created", 0)
        legacy.setdefault("summary", legacy.get("final_text", "") or "")
        legacy.setdefault("audit", None)
        legacy.setdefault("consolidation", None)
    return legacy


def followup_draft(
    meeting_id: str,
    recipient: str | None = None,
    tone: str | None = None,
) -> dict:
    """Storage-router-facing entrypoint for /api/meetings/{id}/followup-draft.

    Thin shim over the dispatcher's ``run_skill`` with the
    ``meeting-followup-draft`` skill. The route layer is responsible
    for sanitizing ``recipient`` and validating ``tone`` before this
    function is called — by the time we get here the inputs are safe
    to splice into the bootstrap prompt.

    Returns the dispatcher's raw shape: ``{"final_text": str, ...}``.
    The route layer parses ``final_text`` into ``{"markdown",
    "cards_referenced"}`` and surfaces only the markdown body to the
    frontend.
    """
    from .llm import run_skill as _run_skill

    parts: list[str] = []
    if recipient:
        parts.append(f"recipient={recipient}")
    if tone:
        parts.append(f"tone={tone}")
    user_question = "; ".join(parts) if parts else None

    return _run_skill(
        skill_name="meeting-followup-draft",
        meeting_id=meeting_id,
        user_question=user_question,
    )


def meeting_qa(meeting_id: str, question: str) -> dict:
    """Storage-router-facing entrypoint for /api/qa/meeting.

    Thin shim over ``run_skill('meeting-qa', meeting_id=..., user_question=question)``.
    Routes through the LLM dispatcher so ``LLM_PROVIDER`` selects the backend.
    """
    from .llm import run_skill as _run_skill

    return _run_skill(
        skill_name="meeting-qa",
        meeting_id=meeting_id,
        user_question=question,
    )


def live_topic_tracker(transcript_snippet: str) -> str:
    """Storage-router-facing entrypoint for the Wave-8.6 30-s topic tick.

    The caller has already pulled the last ≤60 s of finalized sentences
    via `storage.get_transcript(...)` and joined them into a plain
    string. We invoke the `live-topic-tracker` skill (no tools bound)
    and return the model's raw single-line output verbatim — the
    storage-router writes it to `meetings.current_topic`. The skill is
    expected to refuse with the literal sentinel `__TOPIC_INSUFFICIENT__`
    when the snippet is too sparse; the storage-router treats that
    sentinel as "write NULL, don't surface a hallucinated topic."
    """
    from .llm import run_skill as _run_skill

    result = _run_skill(
        skill_name="live-topic-tracker",
        # No meeting_id / workspace_id binding because this skill
        # explicitly does NOT call any tool — passing the snippet via
        # the bootstrap user_question keeps the runtime contract
        # symmetric with `meeting-summary-overall`.
        user_question=transcript_snippet,
    )
    raw = result.get("final_text", "") if isinstance(result, dict) else ""
    return raw.strip()


def live_summary(meeting_id: str) -> dict:
    """Storage-router-facing entrypoint for the Wave 6.3 live summary tick.

    Drives the ``live-meeting-summary`` skill against the transcript-so-far
    of a meeting whose status is currently ``live``. Returns
    ``{"summary": str, "iterations": int}`` — the caller persists the
    summary to ``meetings.live_summary``.

    Provider-routing: when ``LLM_PROVIDER=openai`` the skill is dispatched
    through :mod:`hermes_plugin.runtime_openai`; otherwise the Anthropic
    bounded-tool loop in :mod:`hermes_plugin.runtime` is used.
    """
    import os

    provider = (os.environ.get("LLM_PROVIDER") or "anthropic").strip().lower()
    if provider != "anthropic":
        from .runtime_openai import run_skill as _run_skill_openai

        result = _run_skill_openai("live-meeting-summary", meeting_id)
        return {
            "summary": (result.get("final_text") or "").strip(),
            "iterations": result.get("iterations", 0),
        }

    from .runtime import run_live_summary as _run_live_summary

    return _run_live_summary(meeting_id)


def live_extraction(meeting_id: str, since_ms: int | None) -> dict:
    """Storage-router-facing entrypoint for the Wave 6.4 live extraction tick.

    Drives the ``live-meeting-extraction`` skill against the
    transcript window ``[max(0, since_ms - 30s), now]``. Returns
    ``{cards_created, window_start_ms, window_end_ms, summary,
    iterations}``. The caller persists ``window_end_ms`` back to
    ``meetings.last_live_extraction_end_ms``.

    Provider-routing: when ``LLM_PROVIDER=openai`` the windowing and
    segment-embedding are done here (mirroring runtime.run_live_extraction)
    and the skill is driven via ``runtime_openai`` with only
    ``create_draft_memory_card`` bound, matching the SKILL.md contract.
    For Anthropic, the bounded-tool loop in :mod:`hermes_plugin.runtime`
    is used which applies the since_ms watermark window.
    """
    import os

    provider = (os.environ.get("LLM_PROVIDER") or "anthropic").strip().lower()
    if provider != "anthropic":
        return _run_live_extraction_openai(meeting_id, since_ms)

    from .runtime import run_live_extraction as _run_live_extraction

    return _run_live_extraction(meeting_id, since_ms)


def _run_live_extraction_openai(meeting_id: str, since_ms: int | None) -> dict:
    """OpenAI implementation of the live extraction tick.

    Fetches transcript, applies the watermark window (with 30s overlap),
    embeds segments in the bootstrap message, and runs the
    ``live-meeting-extraction`` skill with only ``create_draft_memory_card``
    bound — matching the SKILL.md contract that expects segments inline.
    """
    import json as _json
    from .client import StorageRouterClient
    from .tools import get_meeting_transcript as _get_transcript
    from .runtime import _format_ms  # ms → "00:00.000" helper

    OVERLAP_MS = 30_000

    storage_client = StorageRouterClient()
    transcript = _get_transcript({"meeting_id": meeting_id}, storage_client)
    segments: list[dict] = transcript.get("segments", [])
    if not segments:
        return {
            "cards_created": 0,
            "window_start_ms": since_ms or 0,
            "window_end_ms": since_ms or 0,
            "summary": "",
            "iterations": 0,
        }

    base_since = since_ms if since_ms is not None else 0
    window_start = max(0, base_since - OVERLAP_MS)
    end_candidates = [s.get("end_ms") for s in segments if s.get("end_ms") is not None]
    if not end_candidates:
        return {
            "cards_created": 0,
            "window_start_ms": window_start,
            "window_end_ms": window_start,
            "summary": "",
            "iterations": 0,
        }
    window_end = max(int(x) for x in end_candidates)

    in_window: list[dict] = []
    for seg in segments:
        seg_start = seg.get("start_ms")
        seg_end = seg.get("end_ms")
        if seg_start is None:
            continue
        if seg_end is None:
            seg_end = seg_start
        if seg_end < window_start or seg_start > window_end:
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

    # Render segments in the same format _render_chunk_text uses.
    seg_lines: list[str] = []
    speakers_seen: dict[str, None] = {}
    for seg in in_window:
        seg_id = seg.get("segment_id", "?")
        speaker = seg.get("speaker_name") or "unknown"
        s_ms = seg.get("start_ms")
        e_ms = seg.get("end_ms")
        ts = f"{_format_ms(s_ms)}-{_format_ms(e_ms)}"
        seg_lines.append(f"[{seg_id}  {ts}  {speaker}] {seg.get('text', '')}")
        if speaker not in speakers_seen:
            speakers_seen[speaker] = None
    chunk_text = "\n".join(seg_lines)
    speakers_str = ", ".join(speakers_seen.keys()) or "(unknown)"

    bootstrap = (
        f"meeting_id: {meeting_id}\n"
        f"window_start: {_format_ms(window_start)}\n"
        f"window_end: {_format_ms(window_end)}\n"
        f"speakers: {speakers_str}\n"
        f"\n--- transcript window ---\n{chunk_text}\n--- end window ---"
    )

    # Load skill + build OpenAI-shaped tools list restricted to card creation.
    from .runtime_openai import _load_skill, _default_openai_client
    from .tools import TOOL_DESCRIPTIONS
    from .schemas import TOOL_JSON_SCHEMAS

    system = _load_skill("live-meeting-extraction")
    tools_param = [
        {
            "type": "function",
            "function": {
                "name": "create_draft_memory_card",
                "description": TOOL_DESCRIPTIONS["create_draft_memory_card"],
                "parameters": TOOL_JSON_SCHEMAS["create_draft_memory_card"],
            },
        }
    ]
    llm = _default_openai_client()
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": bootstrap},
    ]

    from .tools import TOOL_REGISTRY
    from .runtime_openai import (
        _attr,
        _parse_tool_arguments,
        _serialize_tool_calls_for_history,
        _stringify_result,
        _final_text,
    )
    from .errors import ToolError

    cards_created = 0
    iterations = 0
    final_text = ""
    MAX_ITER = 8

    while iterations < MAX_ITER:
        iterations += 1
        response = llm.chat.completions.create(
            model="gpt-4o-2024-11-20",
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
            final_text = _final_text(last_message)
            break

        for tc in tool_calls:
            tool_call_id = _attr(tc, "id")
            function = _attr(tc, "function")
            name = _attr(function, "name")
            tool_input = _parse_tool_arguments(_attr(function, "arguments"))
            try:
                result = TOOL_REGISTRY[name](tool_input, storage_client)
                content_payload = result
                if name == "create_draft_memory_card":
                    cards_created += 1
            except ToolError as exc:
                content_payload = exc.to_payload()
            except KeyError:
                content_payload = {"error": f"Unknown tool: {name}"}
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": _stringify_result(content_payload),
            })

    return {
        "cards_created": cards_created,
        "window_start_ms": window_start,
        "window_end_ms": window_end,
        "summary": final_text.strip(),
        "iterations": iterations,
    }


def project_orchestrator(question: str) -> dict:
    """Storage-router-facing entrypoint for /api/qa/orchestrator.

    Drives the per-project orchestrator (anthropic-only for now). The
    orchestrator decides which project subagent(s) to dispatch based on
    its registry, fans out under an asyncio.Semaphore(3), and synthesizes
    one final answer with citations in the global form
    ``[project:<ws>:meeting:<m>:card:<c>]``.

    Sync-callable so it slots into the existing storage_router pattern;
    internally wraps the async ``run_project_orchestrator`` with
    ``asyncio.run``.
    """
    import asyncio as _asyncio

    from .orchestrator import run_project_orchestrator as _run

    return _asyncio.run(_run(question))


def workspace_qa(workspace_id: str, question: str) -> dict:
    """Storage-router-facing entrypoint for /api/qa/workspace (Wave 4.3).

    Drives the `workspace-qa` skill which is bound to the two
    cross-meeting search tools. Citations come back as
    ``[meeting:<id>:card:<id>]`` or ``[meeting:<id>:seg:<id>]``.
    """
    from .llm import run_skill as _run_skill

    return _run_skill(
        skill_name="workspace-qa",
        workspace_id=workspace_id,
        user_question=question,
    )


def live_interview_questions(
    meeting_id: str,
    interviewee_name: str,
    interviewee_role: str | None,
    transcript_snippet: str,
) -> dict:
    """Storage-router-facing entrypoint for the 60-s interview-questioner tick.

    The caller has already fetched `interviewee_name`, `interviewee_role`, and
    the last ~3 min of finalized sentences. We invoke the
    `live-interview-questioner` skill (bound to read-only workspace tools) and
    return `{"questions": list[str]}`. The skill is expected to return a JSON
    object in `final_text`; we parse it here. If parsing fails we return
    `{"questions": []}` so the storage-router can write gracefully.

    Provider-routing: when `LLM_PROVIDER=openai` the skill is dispatched
    through `runtime_openai`; otherwise the Anthropic bounded-tool loop in
    `runtime` is used.
    """
    import json as _json
    import os

    provider = (os.environ.get("LLM_PROVIDER") or "anthropic").strip().lower()

    bootstrap = (
        f"interviewee_name: {interviewee_name}\n"
        f"interviewee_role: {interviewee_role or 'not specified'}\n"
        f"meeting_id: {meeting_id}\n"
        f"\n--- recent transcript ---\n{transcript_snippet}\n--- end transcript ---"
    )

    if provider != "anthropic":
        from .runtime_openai import run_skill as _run_skill_openai

        # `user_question` is keyword-only on run_skill (both runtimes); passing
        # bootstrap positionally raises "takes from 1 to 2 positional arguments
        # but 3 were given" and silently kills every questioner tick.
        result = _run_skill_openai(
            "live-interview-questioner", meeting_id, user_question=bootstrap
        )
    else:
        from .llm import run_skill as _run_skill

        result = _run_skill(
            skill_name="live-interview-questioner",
            meeting_id=meeting_id,
            user_question=bootstrap,
        )

    raw = (result.get("final_text") or "").strip() if isinstance(result, dict) else ""
    # Strip ```json fences if present.
    import re as _re
    candidate = raw
    if candidate.startswith("```"):
        candidate = _re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = _re.sub(r"\s*```\s*$", "", candidate)
    try:
        parsed = _json.loads(candidate)
        if isinstance(parsed, dict) and isinstance(parsed.get("questions"), list):
            return {"questions": parsed["questions"]}
    except (ValueError, _json.JSONDecodeError):
        pass
    return {"questions": []}


def __getattr__(name: str):
    if name == "run_skill":
        try:
            from .llm import run_skill as _run_skill
        except ImportError as exc:
            raise NotImplementedError(
                "hermes_plugin.run_skill not yet implemented"
            ) from exc
        return _run_skill
    if name == "TOOL_REGISTRY":
        try:
            from .tools import TOOL_REGISTRY as _registry
        except ImportError as exc:
            raise NotImplementedError(
                "hermes_plugin.TOOL_REGISTRY not yet implemented"
            ) from exc
        return _registry
    raise AttributeError(f"module 'hermes_plugin' has no attribute {name!r}")
