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
]


def meeting_finalization(
    meeting_id: str,
    chunk_minutes: int | None = 5,
) -> dict:
    """Storage-router-facing entrypoint for /api/meetings/{id}/finalize.

    Routing:
      - Fetch the transcript once.
      - If ``chunk_minutes`` is not None AND every segment carries a
        ``start_ms``, dispatch to :func:`runtime.run_chunked_extraction`
        (Anthropic-only path; one Claude call per time window + one
        summary call).
      - Otherwise fall back to the legacy single-pass
        ``run_skill('meeting-finalization', ...)`` via the LLM dispatcher
        so ``LLM_PROVIDER`` selects the backend. Synthesizes a
        ``chunks_processed=1`` field so the response shape is uniform.
    """
    # Local imports keep `import hermes_plugin` cheap.
    from .client import StorageRouterClient
    from .llm import run_skill as _run_skill
    from .runtime import run_chunked_extraction as _run_chunked
    from .tools import get_meeting_transcript as _get_transcript

    storage_client = StorageRouterClient()
    transcript = _get_transcript({"meeting_id": meeting_id}, storage_client)
    segments = transcript.get("segments", [])

    has_timestamps = bool(segments) and any(
        s.get("start_ms") is not None for s in segments
    )

    if chunk_minutes is not None and has_timestamps:
        return _run_chunked(
            meeting_id,
            chunk_minutes=chunk_minutes,
            prefetched_segments=segments,
            client=storage_client,
        )

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

    # Wave 2.1/2.2: chain the agent-quality passes after the legacy
    # single-pass finalize so untimestamped imports also benefit.
    # Best-effort: failures here don't blow away the extracted cards.
    from .runtime import (  # local import to keep `import hermes_plugin` cheap
        SKILLS_DIR as _SKILLS_DIR,
        run_card_audit as _run_audit,
        run_card_consolidation as _run_consolidation,
    )
    try:
        legacy["audit"] = _run_audit(meeting_id, client=storage_client)
    except Exception:  # noqa: BLE001
        legacy.setdefault("audit", None)
    if (_SKILLS_DIR / "meeting-card-consolidation" / "SKILL.md").is_file():
        try:
            legacy["consolidation"] = _run_consolidation(
                meeting_id, client=storage_client
            )
        except Exception:  # noqa: BLE001
            legacy.setdefault("consolidation", None)
    else:
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
