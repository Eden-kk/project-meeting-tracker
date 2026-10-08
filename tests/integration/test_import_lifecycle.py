"""Import control races against real PostgreSQL; no remote inference."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import BackgroundTasks
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy import text

from storage_router import dispatcher, import_worker, storage
from storage_router.api.app import create_app
from storage_router.import_lifecycle import change_job
from storage_router.models.db import ConversationArtifactRow, SpeakerSegmentRow
from test_import_recovery import seed, statuses, transcript


def change(factory, mid, action, remote_stopped=False):
    with factory.begin() as session:
        return change_job(session, mid, action, remote_stopped)


def test_cancel_before_claim_and_recover_retry(isolated_db, monkeypatch):
    aid, mid = seed(isolated_db)
    assert change(isolated_db, mid, "cancel")["status"] == "cancelled"
    assert import_worker.run_once() == 0
    assert change(isolated_db, mid, "retry")["status"] == "received"
    monkeypatch.setattr(dispatcher, "parse_transcript", lambda *a, **k: transcript())
    assert import_worker.run_once() == 1
    assert statuses(isolated_db, aid, mid) == ("ready", "ready")


@pytest.mark.parametrize("old_fails", [False, True])
def test_cancel_retry_fences_old_success_and_failure(isolated_db, monkeypatch, old_fails):
    aid, mid = seed(isolated_db)
    entered, release = Event(), Event()
    calls = []

    def parse(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            entered.set()
            assert release.wait(10)
            if old_fails:
                raise RuntimeError("old attempt")
        return transcript()

    monkeypatch.setattr(dispatcher, "parse_transcript", parse)
    with ThreadPoolExecutor(max_workers=1) as pool:
        old = pool.submit(dispatcher.process_artifact, aid)
        try:
            assert entered.wait(5)
            change(isolated_db, mid, "cancel")
            with pytest.raises(ValueError, match="previous remote job"):
                change(isolated_db, mid, "retry")
            # Simulates a user explicitly confirming stop; a delayed old response
            # must still be fenced even if their confirmation was mistaken.
            change(isolated_db, mid, "retry", True)
            dispatcher.process_artifact(aid)
            assert statuses(isolated_db, aid, mid) == ("ready", "ready")
        finally:
            release.set()
        old.result(timeout=5)
    assert statuses(isolated_db, aid, mid) == ("ready", "ready")
    with isolated_db() as session:
        assert session.get(ConversationArtifactRow, aid).processing_attempts == 2
        assert session.scalar(select(func.count()).select_from(SpeakerSegmentRow)) == len(transcript().segments)


@pytest.mark.parametrize("operation", ["cancel", "delete"])
def test_late_result_after_cancel_or_delete_is_discarded(isolated_db, monkeypatch, operation):
    aid, mid = seed(isolated_db)
    entered, release = Event(), Event()
    finalized = []

    def parse(*a, **k):
        entered.set()
        assert release.wait(10)
        return transcript()

    monkeypatch.setattr(dispatcher, "parse_transcript", parse)
    from storage_router import hermes_runtime
    monkeypatch.setattr(hermes_runtime, "auto_finalize_meeting", finalized.append)
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(dispatcher.process_artifact, aid)
        try:
            assert entered.wait(5)
            with isolated_db.begin() as session:
                if operation == "delete":
                    storage.soft_delete_meeting(session, mid)
                else:
                    change_job(session, mid, "cancel")
        finally:
            release.set()
        task.result(timeout=5)
    assert finalized == []
    with isolated_db() as session:
        assert session.scalar(select(func.count()).select_from(SpeakerSegmentRow)) == 0


def test_retry_race_accepts_only_one_request(isolated_db):
    _, mid = seed(isolated_db, status="failed")

    def retry():
        try:
            change(isolated_db, mid, "retry", True)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(retry) for _ in range(2)]
        assert sorted(f.result(timeout=5) for f in futures) == [False, True]


@pytest.mark.parametrize("status", ["ready", "received", "parsing"])
def test_retry_rejects_nonterminal_states(isolated_db, status):
    _, mid = seed(isolated_db, status=status)
    with pytest.raises(ValueError):
        change(isolated_db, mid, "retry", True)


@pytest.mark.asyncio
@pytest.mark.parametrize("isolated_db", ["migrations"], indirect=True)
async def test_control_api_on_migrated_schema(isolated_db, monkeypatch):
    aid, mid = seed(isolated_db)
    monkeypatch.setattr(BackgroundTasks, "add_task", lambda *a, **k: None)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        url = f"/api/meetings/{mid}/import-job"
        assert (await client.get(url)).json()["attempts"] == 0
        assert (await client.post(url + "/cancel")).json()["status"] == "cancelled"
        assert statuses(isolated_db, aid, mid) == ("cancelled", "cancelled")
        assert (await client.post(url + "/retry", json={})).status_code == 202
        assert (await client.post(url + "/retry", json={})).status_code == 409
        assert (await client.post(url + "/retry", json={"remote_stopped": "yes"})).status_code == 422
        assert (await client.get("/api/meetings/missing/import-job")).status_code == 404


@pytest.mark.parametrize("isolated_db", ["migrations"], indirect=True)
def test_migration_preserves_legacy_remote_confirmation(isolated_db):
    aid, mid = seed(isolated_db, status="failed")
    with isolated_db() as session:
        schema = session.scalar(text("SELECT current_schema()"))
    for revision in ("0025_meeting_source_zoom_bot", "head"):
        command = "downgrade" if revision != "head" else "upgrade"
        subprocess.run([sys.executable, "-m", "alembic", command, revision],
            cwd=Path(__file__).parents[2], check=True, capture_output=True, text=True,
            env={**os.environ, "DATABASE_URL": os.environ["MEETING_TEST_DATABASE_URL"],
                 "PGOPTIONS": f"-csearch_path={schema}"})
    with isolated_db() as session:
        assert session.get(ConversationArtifactRow, aid).processing_attempts == 1
    with pytest.raises(ValueError, match="previous remote job"):
        change(isolated_db, mid, "retry")
