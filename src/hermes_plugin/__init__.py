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
    "live_topic_tracker",
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
        return {
            "cards_created": cards_created,
            "chunks_processed": 1,
            "summary": extraction.get("final_text", ""),
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
