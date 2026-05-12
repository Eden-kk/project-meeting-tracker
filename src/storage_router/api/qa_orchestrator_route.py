"""POST /api/qa/orchestrator — per-project orchestrator entrypoint.

Asynchronous handler because the underlying ``run_project_orchestrator``
fans out subagents via ``asyncio.gather`` under a per-loop Semaphore.
The route shape mirrors ``/api/qa/workspace`` so SPA + Slack consumers
can swap one for the other with a one-line change.

Kept as its own module rather than appended to ``qa_route.py`` so the
mixed sync/async handler set doesn't muddy that file's surface.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from storage_router import hermes_runtime
from storage_router.db import get_session

log = logging.getLogger(__name__)

router = APIRouter()


class ProjectOrchestratorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(..., min_length=1, max_length=4000)


class ProjectOrchestratorCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str
    meeting_id: str
    memory_card_id: str | None = None
    segment_id: str | None = None


class ProjectOrchestratorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    final_text: str
    citations: list[ProjectOrchestratorCitation] = Field(default_factory=list)
    # Dispatch observability: one entry per subagent run (refused / failed
    # flags + tools_called list). Cheap to surface; useful for debugging
    # dispatch quality without re-running.
    dispatches: list[dict] = Field(default_factory=list)


def _hermes_unavailable(exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "hermes_unavailable", "message": str(exc)}},
    )


@router.post("/api/qa/orchestrator")
async def qa_orchestrator(
    body: ProjectOrchestratorRequest,
    session: Session = Depends(get_session),
):
    """Run the per-project orchestrator and return its synthesized answer.

    The orchestrator returns citations already in the global form
    ``[project:<ws>:meeting:<m>:card:<c>]``; we extract them into the
    structured ``citations`` list so consumers don't need to parse the
    text.
    """
    import asyncio

    # Off-load the blocking provider call to a worker thread. The
    # plugin's ``project_orchestrator`` shim opens its own asyncio loop
    # internally; doing this in a thread keeps us out of the FastAPI
    # event loop while the LLM rounds-trip.
    try:
        result = await asyncio.to_thread(
            hermes_runtime.run_project_orchestrator, body.question
        )
    except hermes_runtime.HermesUnavailable as e:
        return _hermes_unavailable(e)

    final_text = result.get("final_text", "") or ""
    raw_citations = result.get("citations") or []
    citations = [ProjectOrchestratorCitation(**c) for c in raw_citations]

    return ProjectOrchestratorResponse(
        final_text=final_text,
        citations=citations,
        dispatches=result.get("dispatches") or [],
    ).model_dump(mode="json")


__all__ = ["router"]
