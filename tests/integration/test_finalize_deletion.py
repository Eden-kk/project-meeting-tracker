"""Deletion must fence downstream publication as well as ingestion."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from storage_router import hermes_runtime, storage
from storage_router.models.db import MeetingRow
from test_import_recovery import seed


def ready(factory, deleted=False):
    _, mid = seed(factory, status="ready", deleted=deleted)
    with factory.begin() as session:
        session.get(MeetingRow, mid).status = "ready"
    return mid


def test_deleted_meeting_does_not_start_finalization(isolated_db, monkeypatch):
    mid = ready(isolated_db, deleted=True)
    monkeypatch.setattr(hermes_runtime, "run_meeting_finalization", lambda _: pytest.fail("remote call"))
    hermes_runtime._finalize_inner(mid)


@pytest.mark.parametrize("fails", [False, True])
def test_delete_during_finalization_discards_success_and_failure(isolated_db, monkeypatch, fails):
    mid = ready(isolated_db)
    entered, release = Event(), Event()

    def finalize(_):
        entered.set()
        assert release.wait(10)
        if fails:
            raise RuntimeError("synthetic external failure")
        return {"summary": "must not persist", "cards": []}

    monkeypatch.setattr(hermes_runtime, "run_meeting_finalization", finalize)
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(hermes_runtime._finalize_inner, mid)
        try:
            assert entered.wait(5)
            with isolated_db.begin() as session:
                storage.soft_delete_meeting(session, mid)
        finally:
            release.set()
        task.result(timeout=5)
    with isolated_db() as session:
        row = session.get(MeetingRow, mid)
        assert row.status == "finalizing"
        assert row.finalized_summary is None
        assert row.last_finalize_error is None


def test_finalization_failure_redacts_external_exception(isolated_db, monkeypatch):
    mid = ready(isolated_db)

    def fail(_):
        raise RuntimeError("https://example.invalid/?secret=synthetic")

    monkeypatch.setattr(hermes_runtime, "run_meeting_finalization", fail)
    hermes_runtime._finalize_inner(mid)
    with isolated_db() as session:
        row = session.get(MeetingRow, mid)
        assert row.status == "ready"
        assert "secret" not in row.last_finalize_error
