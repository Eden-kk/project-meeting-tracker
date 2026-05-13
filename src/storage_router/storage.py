"""Transactional repository functions over the Phase-1 ORM."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from storage_router.ids import new_id
from storage_router.models.contracts import NormalizedTranscript, SpeakerSegment, SourceType
from storage_router.models.db import (
    ConversationArtifactRow,
    MeetingRow,
    MemoryCardRow,
    SpeakerSegmentRow,
)
from storage_router.state_machine import next_status



def create_artifact(
    session,
    *,
    workspace_id: str,
    source_type: str,
    capture_mode: str,
    title: str,
    created_by: str,
    raw_file_url: str | None = None,
    raw_text: str | None = None,
    visibility: str = "private",
    labels: list[str] | None = None,
) -> ConversationArtifactRow:
    row = ConversationArtifactRow(
        id=new_id("art"),
        workspace_id=workspace_id,
        source_type=source_type,
        capture_mode=capture_mode,
        title=title,
        created_by=created_by,
        raw_file_url=raw_file_url,
        raw_text=raw_text,
        processing_status="received",
        visibility=visibility,
        labels=labels or [],
    )
    session.add(row)
    session.flush()
    return row


def create_meeting(
    session, *, artifact_id: str, title: str = "", status: str = "processing"
) -> MeetingRow:
    row = MeetingRow(id=new_id("m"), artifact_id=artifact_id, title=title, status=status)
    session.add(row)
    session.flush()
    return row


def update_processing_status(session, artifact_id: str, status: str) -> None:
    """SELECT FOR UPDATE → state-machine guard → UPDATE, all in one transaction."""
    row = session.execute(
        select(ConversationArtifactRow)
        .where(ConversationArtifactRow.id == artifact_id)
        .with_for_update()
    ).scalar_one()
    row.processing_status = next_status(row.processing_status, status)
    session.flush()


def update_meeting_status(session, meeting_id: str, status: str) -> None:
    row = session.get(MeetingRow, meeting_id)
    if row is None:
        raise LookupError(f"meeting {meeting_id} not found")
    row.status = status
    session.flush()


def persist_transcript_segments(
    session, meeting_id: str, transcript: NormalizedTranscript
) -> None:
    """Bulk insert segments. Contract segment_id is discarded; PKs are fresh."""
    rows = [
        SpeakerSegmentRow(
            id=new_id("seg"),
            meeting_id=meeting_id,
            speaker_id=seg.speaker_id,
            speaker_name=seg.speaker_name,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            text=seg.text,
            confidence=seg.confidence,
            source_type=seg.source_type.value,
            is_final=seg.is_final,
        )
        for seg in transcript.segments
    ]
    session.add_all(rows)
    session.flush()


def get_meeting(session, meeting_id: str) -> MeetingRow | None:
    return session.execute(
        select(MeetingRow)
        .where(MeetingRow.id == meeting_id)
        .where(MeetingRow.deleted_at.is_(None))
    ).scalar_one_or_none()


def soft_delete_meeting(
    session, meeting_id: str
) -> tuple[MeetingRow, str | None] | None:
    """Soft-delete a meeting. Returns the row + the artifact's raw_file_url
    so the caller can unlink the blob outside the transaction.

    Uses SELECT ... FOR UPDATE so concurrent DELETEs serialize cleanly
    (mirrors the finalize_meeting pattern in qa_route.py). If the row
    is already soft-deleted, returns it unchanged so the caller can 409.
    """
    from datetime import datetime, timezone

    meeting = session.execute(
        select(MeetingRow)
        .where(MeetingRow.id == meeting_id)
        .with_for_update()
    ).scalar_one_or_none()
    if meeting is None:
        return None
    if meeting.deleted_at is None:
        meeting.deleted_at = datetime.now(timezone.utc)
        session.flush()
    artifact = session.get(ConversationArtifactRow, meeting.artifact_id)
    return meeting, (artifact.raw_file_url if artifact else None)


def list_meetings(
    session, *, workspace_id: str, limit: int = 50, offset: int = 0
) -> tuple[list[MeetingRow], int]:
    """Return (rows, total) for a workspace, newest artifact first."""
    base = (
        select(MeetingRow)
        .join(ConversationArtifactRow, MeetingRow.artifact_id == ConversationArtifactRow.id)
        .where(ConversationArtifactRow.workspace_id == workspace_id)
        .where(MeetingRow.deleted_at.is_(None))
    )
    total = session.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    rows = (
        session.execute(
            base.order_by(ConversationArtifactRow.created_at.desc(), MeetingRow.id)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


def get_transcript(session, meeting_id: str) -> NormalizedTranscript:
    rows = (
        session.execute(
            select(SpeakerSegmentRow)
            .where(SpeakerSegmentRow.meeting_id == meeting_id)
            .order_by(SpeakerSegmentRow.start_ms.nulls_last(), SpeakerSegmentRow.id)
        )
        .scalars()
        .all()
    )
    segments = [
        SpeakerSegment(
            segment_id=r.id,
            speaker_id=r.speaker_id,
            speaker_name=r.speaker_name,
            start_ms=r.start_ms,
            end_ms=r.end_ms,
            text=r.text,
            confidence=r.confidence,
            source_type=SourceType(r.source_type),
            is_final=r.is_final,
        )
        for r in rows
    ]
    return NormalizedTranscript(meeting_id=meeting_id, segments=segments)


# --- memory cards ----------------------------------------------------------

def create_memory_card(
    session,
    *,
    meeting_id: str,
    type: str,
    title: str,
    content: str,
    source_chunk_ids: list[str],
    confidence: float,
    source_start_ms: int | None = None,
    source_end_ms: int | None = None,
    speakers_json: list[str] | None = None,
    created_by_agent: str | None = None,
) -> MemoryCardRow:
    """Insert a new MemoryCard. Phase-3 redesign: cards are live on insert;
    there is no `state` column, no `draft → committed` transition. The
    audit + consolidation passes flag bad cards via `hidden_at`.

    Raises LookupError if the meeting does not exist (route maps to 404).
    """
    if get_meeting(session, meeting_id) is None:
        raise LookupError(f"meeting {meeting_id} not found")
    row = MemoryCardRow(
        id=new_id("mem"),
        meeting_id=meeting_id,
        type=type,
        title=title,
        content=content,
        source_chunk_ids=source_chunk_ids,
        source_start_ms=source_start_ms,
        source_end_ms=source_end_ms,
        speakers_json=speakers_json,
        confidence=confidence,
        created_by_agent=created_by_agent,
    )
    session.add(row)
    session.flush()
    return row


def list_meeting_cards(
    session,
    *,
    meeting_id: str,
    type: str | None = None,
    include_hidden: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[MemoryCardRow], int]:
    """Return (rows, total) for a meeting's cards, newest first.

    By default filters out agent-hidden rows (`hidden_at IS NULL`). Set
    `include_hidden=True` for admin / audit views.

    Raises LookupError if the meeting does not exist.
    """
    if get_meeting(session, meeting_id) is None:
        raise LookupError(f"meeting {meeting_id} not found")
    base = select(MemoryCardRow).where(MemoryCardRow.meeting_id == meeting_id)
    if type is not None:
        base = base.where(MemoryCardRow.type == type)
    if not include_hidden:
        base = base.where(MemoryCardRow.hidden_at.is_(None))
    total = session.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    rows = (
        session.execute(
            base.order_by(MemoryCardRow.created_at.desc(), MemoryCardRow.id)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


def get_memory_card(session, card_id: str) -> MemoryCardRow | None:
    return session.get(MemoryCardRow, card_id)


def update_card_confidence(
    session,
    *,
    card_id: str,
    confidence: float,
    reason: str | None = None,
) -> MemoryCardRow:
    """Patch a card's confidence (and optional audit_reason).

    Used by the Wave 2.1 audit pass to downgrade weak cards without
    hiding them. Raises LookupError if the card does not exist.
    """
    row = session.get(MemoryCardRow, card_id)
    if row is None:
        raise LookupError(f"memory card {card_id} not found")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    row.confidence = confidence
    if reason is not None:
        row.audit_reason = reason
    session.flush()
    return row


def hide_card(
    session,
    *,
    card_id: str,
    reason: str | None = None,
) -> MemoryCardRow:
    """Soft-delete a card by setting hidden_at = NOW() + audit_reason.

    Idempotent: hiding an already-hidden card returns the row untouched.
    Raises LookupError if the card does not exist.
    """
    from datetime import datetime, timezone

    row = session.get(MemoryCardRow, card_id)
    if row is None:
        raise LookupError(f"memory card {card_id} not found")
    if row.hidden_at is None:
        row.hidden_at = datetime.now(timezone.utc)
    if reason is not None:
        row.audit_reason = reason
    session.flush()
    return row


def supersede_cards(
    session,
    *,
    loser_id: str,
    winner_id: str,
) -> tuple[MemoryCardRow, MemoryCardRow]:
    """Consolidate `loser` into `winner` (Wave 2.2).

    Validates:
    - both cards exist and belong to the same meeting;
    - neither card is already hidden;
    - loser is not already superseded;
    - loser != winner.

    Effects:
    - loser.superseded_by_id = winner_id
    - loser.hidden_at = NOW() (idempotent if already set)
    - winner.source_chunk_ids gains loser.source_chunk_ids (dedup'd, order preserved)

    Idempotent: calling twice does not double-append source ids and does
    not flip the loser's hidden_at timestamp.
    """
    from datetime import datetime, timezone

    if loser_id == winner_id:
        raise ValueError("loser and winner must differ")
    loser = session.get(MemoryCardRow, loser_id)
    if loser is None:
        raise LookupError(f"memory card {loser_id} not found")
    winner = session.get(MemoryCardRow, winner_id)
    if winner is None:
        raise LookupError(f"memory card {winner_id} not found")
    if loser.meeting_id != winner.meeting_id:
        raise ValueError("cards must belong to the same meeting")
    if winner.hidden_at is not None:
        raise ValueError("winner card is hidden")
    if winner.superseded_by_id is not None:
        raise ValueError("winner card is itself already superseded")

    # Idempotent guard: if loser is already pointed at this winner, just
    # ensure the merge state is consistent and return.
    if loser.superseded_by_id == winner_id:
        # Hidden_at should already be set from the first call.
        if loser.hidden_at is None:
            loser.hidden_at = datetime.now(timezone.utc)
        session.flush()
        return loser, winner

    if loser.superseded_by_id is not None:
        raise ValueError("loser card is already superseded by a different card")

    # Append loser's source chunks to the winner, deduplicating.
    winner_ids = list(winner.source_chunk_ids or [])
    seen = set(winner_ids)
    for cid in loser.source_chunk_ids or []:
        if cid not in seen:
            winner_ids.append(cid)
            seen.add(cid)
    winner.source_chunk_ids = winner_ids

    loser.superseded_by_id = winner_id
    if loser.hidden_at is None:
        loser.hidden_at = datetime.now(timezone.utc)
    session.flush()
    return loser, winner


def list_action_items(
    session,
    *,
    workspace_id: str,
    type: str = "action_item",
    speaker: str | None = None,
    meeting_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Workspace-wide cross-meeting list of visible memory cards of a single type.

    Joins `memory_cards → meetings → conversation_artifacts` so the caller
    can filter by `workspace_id` and surface the source meeting's title +
    `finalized_at` next to each row.

    Default `type="action_item"` powers /api/action-items; passing
    `type="open_question"` reuses the same query for the open-questions
    dashboard. `hidden_at IS NOT NULL` rows are always excluded.

    Returns (items, total) where each item is a flat dict ready for the
    Pydantic response model — joins are flattened here rather than in the
    route so call-sites do not own SQL.
    """
    base = (
        select(
            MemoryCardRow,
            MeetingRow.title.label("meeting_title"),
            MeetingRow.finalized_at.label("meeting_finalized_at"),
        )
        .join(MeetingRow, MemoryCardRow.meeting_id == MeetingRow.id)
        .join(
            ConversationArtifactRow,
            MeetingRow.artifact_id == ConversationArtifactRow.id,
        )
        .where(ConversationArtifactRow.workspace_id == workspace_id)
        .where(MeetingRow.deleted_at.is_(None))
        .where(MemoryCardRow.type == type)
        .where(MemoryCardRow.hidden_at.is_(None))
    )
    if speaker is not None:
        # speakers_json is a JSONB array of strings; case-insensitive
        # contains check ('?' = top-level key) handles the common case.
        base = base.where(MemoryCardRow.speakers_json.op("?")(speaker))
    if meeting_id is not None:
        base = base.where(MemoryCardRow.meeting_id == meeting_id)
    if since is not None:
        base = base.where(MemoryCardRow.created_at >= since)
    if until is not None:
        base = base.where(MemoryCardRow.created_at <= until)

    total = session.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()

    rows = session.execute(
        base.order_by(MemoryCardRow.created_at.desc(), MemoryCardRow.id)
        .limit(limit)
        .offset(offset)
    ).all()

    items: list[dict] = []
    for row in rows:
        card = row[0]
        items.append(
            {
                "memory_card_id": card.id,
                "meeting_id": card.meeting_id,
                "meeting_title": row.meeting_title or "",
                "meeting_finalized_at": row.meeting_finalized_at,
                "type": card.type,
                "title": card.title,
                "content": card.content,
                "source_chunk_ids": list(card.source_chunk_ids),
                "source_start_ms": card.source_start_ms,
                "source_end_ms": card.source_end_ms,
                "speakers_json": (
                    list(card.speakers_json) if card.speakers_json is not None else None
                ),
                "confidence": card.confidence,
                "created_at": card.created_at,
                "updated_at": card.updated_at,
            }
        )
    return items, int(total)

def search_segments_fts(
    session,
    *,
    workspace_id: str,
    query: str | None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Postgres FTS over speaker_segments.search_tsv, scoped to a workspace.

    Returns (rows, total). Each row is a dict with: segment_id, meeting_id,
    meeting_title, speaker_name, start_ms, end_ms, text, rank, snippet.

    When ``query`` is empty/None, returns the most recent segments in the
    workspace (no FTS predicate), ordered by meeting recency then start_ms.
    """
    from sqlalchemy import text

    q = (query or "").strip()

    if not q:
        sql_count = text(
            """
            SELECT COUNT(*)
              FROM speaker_segments s
              JOIN meetings m ON m.id = s.meeting_id AND m.deleted_at IS NULL
              JOIN conversation_artifacts a ON a.id = m.artifact_id
             WHERE a.workspace_id = :ws
            """
        )
        total = session.execute(sql_count, {"ws": workspace_id}).scalar_one()

        sql_rows = text(
            """
            SELECT s.id              AS segment_id,
                   s.meeting_id      AS meeting_id,
                   m.title           AS meeting_title,
                   s.speaker_name    AS speaker_name,
                   s.speaker_id      AS speaker_id,
                   s.start_ms        AS start_ms,
                   s.end_ms          AS end_ms,
                   s.text            AS text,
                   0.0               AS rank,
                   ''                AS snippet
              FROM speaker_segments s
              JOIN meetings m ON m.id = s.meeting_id AND m.deleted_at IS NULL
              JOIN conversation_artifacts a ON a.id = m.artifact_id
             WHERE a.workspace_id = :ws
             ORDER BY m.created_at DESC NULLS LAST,
                      s.start_ms NULLS LAST,
                      s.id
             LIMIT :lim OFFSET :off
            """
        )
        rows = session.execute(
            sql_rows, {"ws": workspace_id, "lim": limit, "off": offset}
        ).mappings().all()
        return [dict(r) for r in rows], int(total)

    sql_count = text(
        """
        SELECT COUNT(*)
          FROM speaker_segments s
          JOIN meetings m ON m.id = s.meeting_id AND m.deleted_at IS NULL
          JOIN conversation_artifacts a ON a.id = m.artifact_id
         WHERE a.workspace_id = :ws
           AND s.search_tsv @@ websearch_to_tsquery('english', :q)
        """
    )
    total = session.execute(sql_count, {"ws": workspace_id, "q": q}).scalar_one()

    sql_rows = text(
        """
        SELECT s.id              AS segment_id,
               s.meeting_id      AS meeting_id,
               m.title           AS meeting_title,
               s.speaker_name    AS speaker_name,
               s.speaker_id      AS speaker_id,
               s.start_ms        AS start_ms,
               s.end_ms          AS end_ms,
               s.text            AS text,
               ts_rank_cd(s.search_tsv, websearch_to_tsquery('english', :q)) AS rank,
               ts_headline(
                 'english', s.text, websearch_to_tsquery('english', :q),
                 'StartSel=<mark>,StopSel=</mark>,MaxFragments=2,MaxWords=20,MinWords=5'
               ) AS snippet
          FROM speaker_segments s
          JOIN meetings m ON m.id = s.meeting_id AND m.deleted_at IS NULL
          JOIN conversation_artifacts a ON a.id = m.artifact_id
         WHERE a.workspace_id = :ws
           AND s.search_tsv @@ websearch_to_tsquery('english', :q)
         ORDER BY rank DESC, s.start_ms NULLS LAST, s.id
         LIMIT :lim OFFSET :off
        """
    )
    rows = session.execute(
        sql_rows, {"ws": workspace_id, "q": q, "lim": limit, "off": offset}
    ).mappings().all()
    return [dict(r) for r in rows], int(total)


def search_cards_fts(
    session,
    *,
    workspace_id: str,
    query: str | None,
    type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Postgres FTS over memory_cards.search_tsv (title || ' ' || content),
    scoped to a workspace. Honors `hidden_at IS NULL`.

    Returns (rows, total). Each row dict has: memory_card_id, meeting_id,
    meeting_title, type, title, content, confidence, source_start_ms,
    source_end_ms, rank, snippet.

    When ``query`` is empty/None, returns the highest-confidence / most
    recent cards matching the remaining filters (workspace, optional
    type). This is the no-`q` path the workspace-qa skill uses for
    general project-progress questions.
    """
    from sqlalchemy import text

    q = (query or "").strip()

    type_clause = "AND c.type = :type " if type else ""
    base_params: dict = {"ws": workspace_id, "lim": limit, "off": offset}
    if type:
        base_params["type"] = type

    if not q:
        sql_count = text(
            f"""
            SELECT COUNT(*)
              FROM memory_cards c
              JOIN meetings m ON m.id = c.meeting_id AND m.deleted_at IS NULL
              JOIN conversation_artifacts a ON a.id = m.artifact_id
             WHERE a.workspace_id = :ws
               AND c.hidden_at IS NULL
               {type_clause}
            """
        )
        total = session.execute(sql_count, base_params).scalar_one()

        sql_rows = text(
            f"""
            SELECT c.id              AS memory_card_id,
                   c.meeting_id      AS meeting_id,
                   m.title           AS meeting_title,
                   c.type            AS type,
                   c.title           AS title,
                   c.content         AS content,
                   c.confidence      AS confidence,
                   c.source_start_ms AS source_start_ms,
                   c.source_end_ms   AS source_end_ms,
                   0.0               AS rank,
                   ''                AS snippet
              FROM memory_cards c
              JOIN meetings m ON m.id = c.meeting_id AND m.deleted_at IS NULL
              JOIN conversation_artifacts a ON a.id = m.artifact_id
             WHERE a.workspace_id = :ws
               AND c.hidden_at IS NULL
               {type_clause}
             ORDER BY c.confidence DESC NULLS LAST,
                      c.created_at DESC,
                      c.id
             LIMIT :lim OFFSET :off
            """
        )
        rows = session.execute(sql_rows, base_params).mappings().all()
        return [dict(r) for r in rows], int(total)

    params: dict = dict(base_params)
    params["q"] = q

    sql_count = text(
        f"""
        SELECT COUNT(*)
          FROM memory_cards c
          JOIN meetings m ON m.id = c.meeting_id AND m.deleted_at IS NULL
          JOIN conversation_artifacts a ON a.id = m.artifact_id
         WHERE a.workspace_id = :ws
           AND c.hidden_at IS NULL
           {type_clause}
           AND c.search_tsv @@ websearch_to_tsquery('english', :q)
        """
    )
    total = session.execute(sql_count, params).scalar_one()

    sql_rows = text(
        f"""
        SELECT c.id              AS memory_card_id,
               c.meeting_id      AS meeting_id,
               m.title           AS meeting_title,
               c.type            AS type,
               c.title           AS title,
               c.content         AS content,
               c.confidence      AS confidence,
               c.source_start_ms AS source_start_ms,
               c.source_end_ms   AS source_end_ms,
               ts_rank_cd(c.search_tsv, websearch_to_tsquery('english', :q)) AS rank,
               ts_headline(
                 'english',
                 coalesce(c.title,'') || ' ' || coalesce(c.content,''),
                 websearch_to_tsquery('english', :q),
                 'StartSel=<mark>,StopSel=</mark>,MaxFragments=2,MaxWords=20,MinWords=5'
               ) AS snippet
          FROM memory_cards c
          JOIN meetings m ON m.id = c.meeting_id AND m.deleted_at IS NULL
          JOIN conversation_artifacts a ON a.id = m.artifact_id
         WHERE a.workspace_id = :ws
           AND c.hidden_at IS NULL
           {type_clause}
           AND c.search_tsv @@ websearch_to_tsquery('english', :q)
         ORDER BY rank DESC, c.created_at DESC, c.id
         LIMIT :lim OFFSET :off
        """
    )
    rows = session.execute(sql_rows, params).mappings().all()
    return [dict(r) for r in rows], int(total)
