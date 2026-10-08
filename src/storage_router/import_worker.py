"""Recover committed, unclaimed imports; never replay uncertain in-flight work.

Run alongside the API with the SAME database, ingest settings and blob mount:
python -m storage_router.import_worker --poll-seconds 5
"""
from __future__ import annotations

import argparse
import logging
import time

from sqlalchemy import select

from storage_router.db import SessionLocal
from storage_router.dispatcher import process_artifact
from storage_router.models.db import ConversationArtifactRow, MeetingRow

log = logging.getLogger(__name__)
IMPORT_TYPES = ("voice_file", "transcript_file", "pasted_transcript")


def run_once(*, batch_size: int = 20) -> int:
    """Scan a bounded batch; process_artifact atomically claims each record.

    Return candidate count, not success count: another worker may win a claim.
    Committed received rows survive API failure before BackgroundTasks starts.
    """
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be between 1 and 100")
    with SessionLocal() as session:
        ids = list(session.scalars(
            select(ConversationArtifactRow.id)
            .join(MeetingRow, MeetingRow.artifact_id == ConversationArtifactRow.id)
            .where(ConversationArtifactRow.capture_mode == "imported")
            .where(ConversationArtifactRow.source_type.in_(IMPORT_TYPES))
            .where(ConversationArtifactRow.processing_status == "received")
            .where(MeetingRow.deleted_at.is_(None))
            .order_by(ConversationArtifactRow.created_at, ConversationArtifactRow.id)
            .limit(batch_size)
        ))
    for artifact_id in ids:
        process_artifact(artifact_id)
    return len(ids)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 100 or not 0.1 <= args.poll_seconds <= 60:
        parser.error("batch-size must be 1..100; poll-seconds must be 0.1..60")
    logging.basicConfig(level=logging.INFO)
    try:
        while True:
            try:
                count = run_once(batch_size=args.batch_size)
                log.info("scanned %d pending import candidates", count)
            except Exception:
                log.exception("import recovery scan failed; pending records remain in database")
                if args.once:
                    raise
            if args.once:
                return
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        log.info("worker stopped; claimed work is not automatically replayed")


if __name__ == "__main__":
    main()
