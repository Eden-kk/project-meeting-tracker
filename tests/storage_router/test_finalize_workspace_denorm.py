"""Denormalization test: finalizing a meeting updates the workspace's
``last_meeting_at`` to the meeting's ``finalized_at``.

Skipped when the migration ``0021_workspaces_orchestrator_fields`` has
NOT been applied (the test environment may run against a pre-migration
shared Postgres). The skip is detected via an information_schema probe
so the test stays correct across environments.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from storage_router import hermes_runtime
from storage_router.db import SessionLocal
from storage_router.models.db import MeetingRow, Workspace
from storage_router.storage import create_artifact, create_meeting


def _has_last_meeting_at_column() -> bool:
    with SessionLocal() as s:
        row = s.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'workspaces' "
                "AND column_name = 'last_meeting_at'"
            )
        ).first()
        return row is not None


pytestmark = pytest.mark.skipif(
    not _has_last_meeting_at_column(),
    reason="migration 0021_workspaces_orchestrator_fields not applied",
)


def _seed_meeting(workspace_id: str = "ws_dev") -> str:
    with SessionLocal() as s:
        a = create_artifact(
            s,
            workspace_id=workspace_id,
            source_type="pasted_transcript",
            capture_mode="imported",
            title="denorm-test",
            created_by="u_dev",
            raw_text="hello",
        )
        m = create_meeting(s, artifact_id=a.id)
        # Mark it ``ready`` so _finalize_inner is willing to proceed.
        m.status = "ready"
        s.commit()
        return m.id


def test_finalize_updates_workspace_last_meeting_at(monkeypatch):
    """Run _finalize_inner with a no-op extraction; assert the workspace
    row's ``last_meeting_at`` is set to the meeting's finalized_at."""
    meeting_id = _seed_meeting()

    # Stub the LLM-driven extraction to return zero cards (we only care
    # about the meta-state transition for this test).
    monkeypatch.setattr(
        hermes_runtime,
        "run_meeting_finalization",
        lambda mid, chunk_minutes=5: {"cards": []},
    )

    hermes_runtime._finalize_inner(meeting_id)

    with SessionLocal() as s:
        meeting = s.get(MeetingRow, meeting_id)
        assert meeting is not None
        assert meeting.status == "finalized"
        assert meeting.finalized_at is not None

        workspace = s.get(Workspace, "ws_dev")
        assert workspace is not None
        assert workspace.last_meeting_at is not None
        # The denorm value tracks the meeting's finalized_at exactly.
        assert workspace.last_meeting_at == meeting.finalized_at
