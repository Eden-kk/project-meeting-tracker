"""GET /api/workspaces — list every workspace for the top-right switcher.

No auth, no membership filter, no pagination — matches the rest of the
single-workspace-world API. Sort: most-recently-active first, then by
display name as a stable tiebreaker.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from storage_router.db import get_session
from storage_router.models.contracts import Workspace, WorkspaceListResponse
from storage_router.models.db import Workspace as WorkspaceRow

router = APIRouter()


@router.get("/api/workspaces", response_model=WorkspaceListResponse)
def list_workspaces(session: Session = Depends(get_session)) -> WorkspaceListResponse:
    """Return every workspace row sorted by recency.

    Sort key: `last_meeting_at DESC NULLS LAST, name ASC`. The NULLS-LAST
    part keeps brand-new workspaces (no meetings yet) below the active
    ones rather than floating to the top with NULL > anything semantics.
    """
    rows = session.execute(
        select(WorkspaceRow).order_by(
            WorkspaceRow.last_meeting_at.desc().nulls_last(),
            WorkspaceRow.name.asc(),
        )
    ).scalars().all()
    items = [
        Workspace(
            id=row.id,
            name=row.name,
            description=row.description,
            last_meeting_at=row.last_meeting_at,
        )
        for row in rows
    ]
    return WorkspaceListResponse(items=items, total=len(items))
