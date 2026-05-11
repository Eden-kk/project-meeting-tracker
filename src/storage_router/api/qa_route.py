"""Hermes-backed finalize + QA endpoints.

Both routes resolve the Hermes plugin at call-time via
`storage_router.hermes_runtime`; tests monkeypatch `run_meeting_finalization`
and `run_meeting_qa` to inject stub responses without installing a plugin.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from storage_router import hermes_runtime, storage
from storage_router.api.memory_cards_route import _row_to_card
from storage_router.db import get_session
from storage_router.models.db import MeetingRow
from storage_router.models.memory_cards import (
    FinalizeResponse,
    MemoryCardCreate,
    QAEvidenceItem,
    QARequest,
    QAResponse,
)

router = APIRouter()


def _hermes_unavailable(exc: hermes_runtime.HermesUnavailable) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "hermes_unavailable", "message": str(exc)}},
    )


@router.post("/api/meetings/{meeting_id}/finalize")
def finalize_meeting(
    meeting_id: str,
    chunk_minutes: int = Query(5, ge=1, le=30),
    session: Session = Depends(get_session),
):
    meeting = session.execute(
        select(MeetingRow).where(MeetingRow.id == meeting_id).with_for_update()
    ).scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    if meeting.status == "finalized":
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "already_finalized"}},
        )

    try:
        result = hermes_runtime.run_meeting_finalization(
            meeting_id, chunk_minutes=chunk_minutes
        )
    except hermes_runtime.HermesUnavailable as e:
        return _hermes_unavailable(e)

    # Two payload shapes coexist during the chunked-summarization rollout:
    #   * Legacy single-pass: {"cards": [...], "summary": "..."} — route
    #     persists the cards itself.
    #   * Chunked path: {"cards_created": int, "summary": str,
    #     "chunks_processed": int} — cards were already persisted by the
    #     create_draft_memory_card tool inside the plugin.
    # Phase-3: `needs_review` field is gone (PR #19 dropped it).
    cards_payload = result.get("cards")
    if cards_payload is not None:
        cards_in = [MemoryCardCreate(**c) for c in cards_payload]
        for card in cards_in:
            storage.create_memory_card(
                session,
                meeting_id=meeting_id,
                type=card.type.value,
                title=card.title,
                content=card.content,
                source_chunk_ids=card.source_chunk_ids,
                confidence=card.confidence,
                source_start_ms=card.source_start_ms,
                source_end_ms=card.source_end_ms,
                speakers_json=card.speakers_json,
                created_by_agent=card.created_by_agent,
            )
        cards_created = len(cards_in)
    else:
        cards_created = int(result.get("cards_created", 0))

    finalized_at = datetime.now(UTC)
    meeting.status = "finalized"
    meeting.finalized_at = finalized_at
    session.commit()

    return FinalizeResponse(
        meeting_id=meeting_id,
        finalized_at=finalized_at,
        cards_created=cards_created,
        summary=result.get("summary", ""),
        chunks_processed=int(result.get("chunks_processed", 1)),
    ).model_dump(mode="json")


@router.post("/api/qa/meeting")
def qa_meeting(body: QARequest, session: Session = Depends(get_session)):
    if session.get(MeetingRow, body.meeting_id) is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    try:
        result = hermes_runtime.run_meeting_qa(body.meeting_id, body.question)
    except hermes_runtime.HermesUnavailable as e:
        return _hermes_unavailable(e)
    # The plugin's `run_skill` returns {final_text, tool_calls, iterations}.
    # Translate to the frontend's AskHermesResponse contract:
    # {answer, confidence, citations: [{segment_id, speaker, start_ms, end_ms, text}], weak_evidence}.
    import json as _json
    import re
    from storage_router.models.db import SpeakerSegmentRow

    answer_text = result.get("final_text") or result.get("answer", "")
    weak_evidence = False
    try:
        parsed_refusal = _json.loads(answer_text)
        if isinstance(parsed_refusal, dict) and parsed_refusal.get("refused"):
            weak_evidence = True
    except Exception:
        pass

    seg_ids: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"\[seg:([^\]]+)\]", answer_text or ""):
        sid = m.group(1)
        if sid not in seen:
            seen.add(sid)
            seg_ids.append(sid)

    citations: list[dict] = []
    if seg_ids:
        rows = session.query(SpeakerSegmentRow).filter(SpeakerSegmentRow.id.in_(seg_ids)).all()
        by_id = {r.id: r for r in rows}
        for sid in seg_ids:
            row = by_id.get(sid)
            if row is None:
                continue
            citations.append({
                "segment_id": row.id,
                "speaker": row.speaker_name or row.speaker_id or "Unknown",
                "start_ms": int(row.start_ms or 0),
                "end_ms": int(row.end_ms or 0),
                "text": row.text or "",
            })

    if not citations and not weak_evidence:
        weak_evidence = True

    return QAResponse(
        answer=answer_text,
        confidence=0.4 if weak_evidence else 0.85,
        citations=[QAEvidenceItem(**c) for c in citations],
        weak_evidence=weak_evidence,
    ).model_dump(mode="json")


# Re-export for parity with cards_route's _row_to_card (kept reachable for tests).
__all__ = ["router", "_row_to_card"]
