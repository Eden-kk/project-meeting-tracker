"""Real PostgreSQL claim/recovery tests; fake inference, no external calls."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier, Event

import pytest
from fastapi import BackgroundTasks
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select

from storage_router import dispatcher, import_worker, storage
from storage_router.api.app import create_app
from storage_router.blob import LocalFsBlobStore
from storage_router.models.contracts import NormalizedTranscript
from storage_router.models.db import ConversationArtifactRow, MeetingRow, MeetingSourceRow, SpeakerSegmentRow


def transcript():
    return NormalizedTranscript.model_validate(json.loads(
        (Path(__file__).parents[2] / "fixtures/expected_normalized.json").read_text()
    ))


def seed(factory, *, status="received", source_type="pasted_transcript", deleted=False):
    with factory.begin() as session:
        artifact = storage.create_artifact(
            session, workspace_id="ws_dev", source_type=source_type,
            capture_mode="imported", title="Synthetic", created_by="u_dev", raw_text="Hello",
            raw_file_url="file:///synthetic/audio.wav",
        )
        artifact.processing_status = status
        meeting = storage.create_meeting(session, artifact_id=artifact.id)
        if deleted:
            meeting.deleted_at = datetime.now(timezone.utc)
        return artifact.id, meeting.id


def statuses(factory, aid, mid):
    with factory() as session:
        return (session.get(ConversationArtifactRow, aid).processing_status,
                session.get(MeetingRow, mid).status)


def test_competing_workers_invoke_ingest_once(isolated_db, monkeypatch):
    aid, mid = seed(isolated_db)
    entered, release = Event(), Event()
    calls = []

    def parse(*args, **kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return transcript()

    monkeypatch.setattr(dispatcher, "parse_transcript", parse)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(dispatcher.process_artifact, aid)
        try:
            assert entered.wait(5)
            second = pool.submit(dispatcher.process_artifact, aid)
            second.result(timeout=5)
            assert statuses(isolated_db, aid, mid) == ("parsing", "processing")
        finally:
            release.set()
        first.result(timeout=5)
    assert calls == [1]
    assert statuses(isolated_db, aid, mid) == ("ready", "ready")
    dispatcher.process_artifact(aid)
    assert calls == [1]
    with isolated_db() as session:
        count = session.scalar(select(func.count()).select_from(SpeakerSegmentRow))
    assert count == len(transcript().segments)


@pytest.mark.asyncio
async def test_committed_import_survives_lost_background_schedule(isolated_db, monkeypatch, tmp_path):
    monkeypatch.setattr(BackgroundTasks, "add_task", lambda *args, **kwargs: None)
    captured = []

    def transcribe(path, **kwargs):
        assert path.read_bytes() == b"synthetic"
        captured.append(kwargs)
        return transcript()

    monkeypatch.setattr(dispatcher, "transcribe_voice_file", transcribe)
    app = create_app()
    app.state.blob_store = LocalFsBlobStore(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/conversations/import",
            data={"workspace_id": "ws_dev", "title": "Recovery", "num_speakers": "2"},
            files={"voice_file": ("clip.wav", b"synthetic", "audio/wav")})
    assert response.status_code == 202
    aid, mid = response.json()["artifact_id"], response.json()["meeting_id"]
    assert statuses(isolated_db, aid, mid) == ("received", "processing")
    with isolated_db() as session:
        source = session.scalar(select(MeetingSourceRow).where(MeetingSourceRow.meeting_id == mid))
        assert source.metadata_["num_speakers"] == 2
    assert import_worker.run_once() == 1
    assert captured == [{"num_speakers": 2, "min_speakers": None, "max_speakers": None}]
    assert statuses(isolated_db, aid, mid) == ("ready", "ready")
    assert import_worker.run_once() == 0


@pytest.mark.parametrize("status", ["parsing", "transcribing", "normalizing", "ready", "failed"])
def test_does_not_replay_inflight_or_terminal_work(isolated_db, monkeypatch, status):
    aid, mid = seed(isolated_db, status=status)
    monkeypatch.setattr(dispatcher, "parse_transcript", lambda *a, **k: pytest.fail("unexpected inference"))
    assert import_worker.run_once() == 0
    dispatcher.process_artifact(aid)
    assert statuses(isolated_db, aid, mid)[0] == status


def test_failed_ingest_is_not_automatically_retried(isolated_db, monkeypatch):
    aid, mid = seed(isolated_db)
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise TimeoutError("remote acceptance unknown")

    monkeypatch.setattr(dispatcher, "parse_transcript", fail)
    assert import_worker.run_once() == 1
    assert statuses(isolated_db, aid, mid) == ("failed", "failed")
    assert import_worker.run_once() == 0
    assert calls == [1]


def test_deleted_meetings_are_not_recovered(isolated_db, monkeypatch):
    aid, mid = seed(isolated_db, deleted=True)
    monkeypatch.setattr(dispatcher, "parse_transcript", lambda *a, **k: pytest.fail("unexpected inference"))
    assert import_worker.run_once() == 0
    dispatcher.process_artifact(aid)
    assert statuses(isolated_db, aid, mid) == ("received", "processing")


def test_simultaneous_claims_have_one_winner(isolated_db, monkeypatch):
    aid, mid = seed(isolated_db)
    gate = Barrier(2)
    calls = []
    engine = isolated_db.kw["bind"]

    def before_execute(conn, cursor, statement, parameters, context, many):
        if statement.startswith("UPDATE conversation_artifacts") and "RETURNING" in statement:
            gate.wait(timeout=5)

    def parse(*args, **kwargs):
        calls.append(1)
        return transcript()

    monkeypatch.setattr(dispatcher, "parse_transcript", parse)
    event.listen(engine, "before_cursor_execute", before_execute)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(dispatcher.process_artifact, aid) for _ in range(2)]
            for future in futures:
                future.result(timeout=10)
    finally:
        event.remove(engine, "before_cursor_execute", before_execute)
    assert calls == [1]
    assert statuses(isolated_db, aid, mid) == ("ready", "ready")


def test_crash_after_claim_remains_uncertain_without_replay(isolated_db, monkeypatch):
    aid, mid = seed(isolated_db)

    def crash(*args, **kwargs):
        raise SystemExit("simulated worker termination after claim")

    monkeypatch.setattr(dispatcher, "parse_transcript", crash)
    with pytest.raises(SystemExit):
        dispatcher.process_artifact(aid)
    assert statuses(isolated_db, aid, mid) == ("parsing", "processing")
    assert import_worker.run_once() == 0


def test_segment_failure_rolls_back_partial_results(isolated_db, monkeypatch):
    aid, mid = seed(isolated_db)
    monkeypatch.setattr(dispatcher, "parse_transcript", lambda *a, **k: transcript())
    persist = storage.persist_transcript_segments

    def fail_after_insert(session, meeting_id, result):
        persist(session, meeting_id, result)
        raise RuntimeError("simulated failure before ready commit")

    monkeypatch.setattr(storage, "persist_transcript_segments", fail_after_insert)
    dispatcher.process_artifact(aid)
    assert statuses(isolated_db, aid, mid) == ("failed", "failed")
    with isolated_db() as session:
        assert session.scalar(select(func.count()).select_from(SpeakerSegmentRow)) == 0


def test_worker_ignores_live_and_unsupported_artifacts(isolated_db, monkeypatch):
    aid, _ = seed(isolated_db)
    seed(isolated_db, source_type="zoom_bot")
    with isolated_db.begin() as session:
        session.get(ConversationArtifactRow, aid).capture_mode = "live"
    monkeypatch.setattr(import_worker, "process_artifact", lambda *a: pytest.fail("unexpected dispatch"))
    assert import_worker.run_once() == 0


@pytest.mark.parametrize("isolated_db", ["migrations"], indirect=True)
def test_recovery_on_fresh_alembic_schema(isolated_db, monkeypatch):
    aid, mid = seed(isolated_db)
    monkeypatch.setattr(dispatcher, "parse_transcript", lambda *a, **k: transcript())
    assert import_worker.run_once() == 1
    assert statuses(isolated_db, aid, mid) == ("ready", "ready")
    assert import_worker.run_once() == 0
