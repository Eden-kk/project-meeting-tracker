"""Per-project orchestrator: routing layer that dispatches to per-project subagents.

Two-layer design (orchestrator → subagent). The orchestrator only sees
the project registry; subagents see one project's data each. Workspace
isolation in the subagent is enforced by binding ``workspace_id`` over
each tool with **positional** ``functools.partial`` (see the
``ISOLATION INVARIANT`` note in ``hermes_plugin.tools`` and the
structural guard in ``tests/hermes_plugin/test_subagent_isolation.py``
test 2). The bound callable's schema no longer exposes ``workspace_id``,
so the LLM has no slot through which to target a different project.

Public surface (called by the storage-router shim
``storage_router.hermes_runtime.run_project_orchestrator``):

- ``load_registry(session)`` — per-process 60s-cached read of workspaces.
- ``bind_subagent_tools(workspace_id)`` — returns
  ``(callables, schemas)``; both have ``workspace_id`` absent.
- ``dispatch_to_project(workspace_id, task)`` — run one subagent.
- ``dispatch_to_projects(workspace_ids, task)`` — fan out under
  ``asyncio.Semaphore(3)``.
- ``run_project_orchestrator(question)`` — async top-level entry.
- ``prefix_citations_with_project(session, final_text, default_project_id)``
  — global citation rewriter; used by the orchestrator after final
  synthesis AND by the existing ``/api/qa/workspace`` route as a
  post-processor so one citation format ships everywhere.

Concurrency notes:
- ``_REGISTRY_CACHE`` is a per-process module-global; uvicorn workers=1
  makes that safe. If multi-worker is ever adopted, this becomes
  per-worker (still correct, just slightly more DB load).
- The semaphore is **lazy-created in the running event loop** via
  ``_get_semaphore()``; a module-level Semaphore bound to an exited
  loop raises "Future attached to a different loop" on the next call.
"""

from __future__ import annotations

import asyncio
import functools
import json as _json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .client import StorageRouterClient
from .tools import (
    get_meeting_transcript,
    search_memory_cards,
    search_workspace_cards,
    search_workspace_transcripts,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectRow:
    id: str
    name: str
    description: Optional[str]
    last_meeting_at: Optional[Any]  # datetime; Any to avoid extra imports


_REGISTRY_TTL_SEC = 60.0
_REGISTRY_CACHE: tuple[list[ProjectRow], float] | None = None


def _now_monotonic() -> float:
    """Indirection point so tests can monkeypatch the clock."""
    return time.monotonic()


def load_registry(session: Any) -> list[ProjectRow]:
    """Read the workspaces registry, cached per-process for ~60s.

    The registry is small (O(N projects)) and rarely changes mid-
    conversation; a 60s TTL keeps prompt-rendering cheap and means a
    brand-new workspace can take up to one minute to appear (accepted).
    """
    global _REGISTRY_CACHE
    now = _now_monotonic()
    if _REGISTRY_CACHE is not None:
        rows, fetched_at = _REGISTRY_CACHE
        if now - fetched_at < _REGISTRY_TTL_SEC:
            return rows

    from storage_router.models.db import Workspace

    rows = session.query(Workspace).order_by(Workspace.id).all()
    out = [
        ProjectRow(
            id=r.id,
            name=r.name,
            description=getattr(r, "description", None),
            last_meeting_at=getattr(r, "last_meeting_at", None),
        )
        for r in rows
    ]
    _REGISTRY_CACHE = (out, now)
    return out


def _clear_registry_cache() -> None:
    """Test hook — also useful if a caller wants to force a fresh read."""
    global _REGISTRY_CACHE
    _REGISTRY_CACHE = None


def render_registry_prompt(rows: list[ProjectRow]) -> str:
    """Render the registry into the orchestrator's system-prompt section."""
    if not rows:
        return "(no projects registered)"
    lines: list[str] = []
    for r in rows:
        desc = (r.description or "—").strip() or "—"
        if len(desc) > 200:
            desc = desc[:197] + "..."
        when = r.last_meeting_at.isoformat() if r.last_meeting_at else "never"
        lines.append(f"id={r.id}, name={r.name}, description={desc}, last_meeting={when}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Subagent tool binding (ISOLATION-CRITICAL)
# ---------------------------------------------------------------------------


def _search_cards_bound(workspace_id: str, /, *, q: str, type: Optional[str] = None, limit: int = 10) -> dict:
    """Workspace-bound wrapper. ``workspace_id`` is positional-only so the
    schema derived from the partial-applied callable has no ``workspace_id``
    slot. The LLM-visible parameters are ``q``, ``type``, ``limit`` only.
    """
    client = StorageRouterClient()
    args = {"workspace_id": workspace_id, "q": q, "limit": limit}
    if type is not None:
        args["type"] = type
    return search_workspace_cards(args, client)


def _search_transcripts_bound(workspace_id: str, /, *, q: str, limit: int = 10) -> dict:
    client = StorageRouterClient()
    args = {"workspace_id": workspace_id, "q": q, "limit": limit}
    return search_workspace_transcripts(args, client)


def _get_meeting_transcript_bound(workspace_id: str, /, *, meeting_id: str) -> dict:
    """Workspace_id is bound but not transitively enforced at the storage
    layer for transcript fetch — it's an isolation primitive for the
    LLM-visible schema, not a DB ACL. The runtime trusts that meeting_id
    came from a search call already scoped to this workspace.
    """
    del workspace_id  # consumed by the partial; kept in signature for symmetry.
    client = StorageRouterClient()
    return get_meeting_transcript({"meeting_id": meeting_id}, client)


def _list_meeting_cards_bound(
    workspace_id: str,
    /,
    *,
    meeting_id: str,
    type: Optional[str] = None,
) -> dict:
    del workspace_id  # see note in _get_meeting_transcript_bound.
    client = StorageRouterClient()
    args = {"meeting_id": meeting_id, "include_hidden": False}
    if type is not None:
        args["type"] = type
    return search_memory_cards(args, client)


# Public LLM-visible tool names → underlying bound callable factory.
# Keep the value side as the unbound function (taking workspace_id
# positionally first); ``bind_subagent_tools`` partials each one.
_SUBAGENT_TOOLS: dict[str, Callable[..., dict]] = {
    "search_cards": _search_cards_bound,
    "search_transcripts": _search_transcripts_bound,
    "get_meeting_transcript": _get_meeting_transcript_bound,
    "list_meeting_cards": _list_meeting_cards_bound,
}


_SUBAGENT_TOOL_DESCRIPTIONS: dict[str, str] = {
    "search_cards": (
        "Cross-meeting FTS over this project's memory cards. Returns ranked "
        "hits keyed by memory_card_id + meeting_id; cite as "
        "[meeting:<id>:card:<id>]."
    ),
    "search_transcripts": (
        "Cross-meeting FTS over this project's transcript segments. Returns "
        "ranked hits keyed by segment_id + meeting_id; cite as "
        "[meeting:<id>:seg:<id>]."
    ),
    "get_meeting_transcript": (
        "Full normalized transcript for one meeting in this project."
    ),
    "list_meeting_cards": (
        "List visible memory cards for one meeting in this project, "
        "optionally filtered by card type (decision, action_item, "
        "open_question, requirement, summary)."
    ),
}


_SUBAGENT_TOOL_SCHEMAS: dict[str, dict] = {
    "search_cards": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "q": {"type": "string", "minLength": 1, "maxLength": 500},
            "type": {
                "type": "string",
                "enum": [
                    "decision",
                    "action_item",
                    "open_question",
                    "requirement",
                    "summary",
                ],
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": ["q"],
    },
    "search_transcripts": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "q": {"type": "string", "minLength": 1, "maxLength": 500},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": ["q"],
    },
    "get_meeting_transcript": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"meeting_id": {"type": "string", "minLength": 1}},
        "required": ["meeting_id"],
    },
    "list_meeting_cards": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "meeting_id": {"type": "string", "minLength": 1},
            "type": {
                "type": "string",
                "enum": [
                    "decision",
                    "action_item",
                    "open_question",
                    "requirement",
                    "summary",
                ],
            },
        },
        "required": ["meeting_id"],
    },
}


def bind_subagent_tools(
    workspace_id: str,
) -> tuple[dict[str, Callable[..., dict]], list[dict]]:
    """Bind every subagent tool to one workspace and return ``(callables, schemas)``.

    Each callable is ``functools.partial(fn, workspace_id)`` — positional —
    so the resulting callable's signature (and the LLM-visible schema)
    does NOT contain a ``workspace_id`` parameter. See ISOLATION INVARIANT
    in ``hermes_plugin.tools``.

    The returned schemas are the static per-tool schemas already stripped
    of ``workspace_id``; they are used directly as the ``tools=[…]`` param
    on the LLM call.
    """
    callables: dict[str, Callable[..., dict]] = {
        name: functools.partial(fn, workspace_id)
        for name, fn in _SUBAGENT_TOOLS.items()
    }
    schemas: list[dict] = [
        {
            "name": name,
            "description": _SUBAGENT_TOOL_DESCRIPTIONS[name],
            "input_schema": _SUBAGENT_TOOL_SCHEMAS[name],
        }
        for name in _SUBAGENT_TOOLS
    ]
    return callables, schemas


# ---------------------------------------------------------------------------
# Subagent dispatch
# ---------------------------------------------------------------------------


_SUBAGENT_FAILURE_DEFAULTS = {
    "summary": "",
    "citations": [],
    "confidence": 0.0,
    "refused": False,
    "refusal_reason": None,
    "tools_called": [],
}


def _parse_subagent_json(text: str) -> dict | None:
    """Strip optional ```json fences and json.loads. Returns None on failure."""
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove a fenced code block; tolerate ```json or bare ```.
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        obj = _json.loads(stripped)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _build_subagent_prompt(name: str, workspace_id: str, description: str | None) -> str:
    """Render the subagent SKILL.md template with the per-project bindings."""
    from .runtime import _load_skill  # local import keeps module load cheap

    raw = _load_skill("project-subagent")
    desc = (description or "(no description)").strip()
    return (
        raw.replace("{{name}}", name)
        .replace("{{workspace_id}}", workspace_id)
        .replace("{{description}}", desc)
    )


async def dispatch_to_project(
    workspace_id: str,
    task: str,
    *,
    name: str | None = None,
    description: str | None = None,
    anthropic_client: Any = None,
    model: str | None = None,
) -> dict:
    """Run one subagent against one project. Always returns the canonical
    8-field shape — never raises. Distinguishes refusal (subagent
    correctly reported "no data on X") from failure (system error,
    JSON parse miss, provider 5xx).
    """
    from .runtime import run_skill_dynamic

    callables, schemas = bind_subagent_tools(workspace_id)
    system_prompt = _build_subagent_prompt(
        name or workspace_id, workspace_id, description
    )
    user_message = f"Task: {task}"

    try:
        # Run blocking client call in a thread so the orchestrator's
        # event loop is free to fan out other dispatches.
        result = await asyncio.to_thread(
            run_skill_dynamic,
            system_prompt=system_prompt,
            tools=callables,
            tool_schemas=schemas,
            user_message=user_message,
            anthropic_client=anthropic_client,
            model=model,
        )
    except Exception as exc:  # noqa: BLE001 — fire-and-forget surface.
        logger.exception("dispatch_to_project: subagent run errored (ws=%s)", workspace_id)
        return {
            **_SUBAGENT_FAILURE_DEFAULTS,
            "failed": True,
            "failure_reason": f"subagent_runtime_error: {exc!s}"[:500],
            "_workspace_id": workspace_id,
        }

    final_text = (result or {}).get("final_text", "") or ""
    tools_called_runtime = [c.get("name", "?") for c in (result or {}).get("tool_calls", [])]

    parsed = _parse_subagent_json(final_text)
    if parsed is None:
        return {
            **_SUBAGENT_FAILURE_DEFAULTS,
            "failed": True,
            "failure_reason": f"subagent returned non-JSON: {final_text[:200]!r}",
            "tools_called": tools_called_runtime,
            "_workspace_id": workspace_id,
        }

    # Normalize: enforce the 8-field shape with sane defaults.
    normalized = {
        "summary": str(parsed.get("summary", "")),
        "citations": list(parsed.get("citations") or []),
        "confidence": float(parsed.get("confidence") or 0.0),
        "refused": bool(parsed.get("refused", False)),
        "refusal_reason": parsed.get("refusal_reason"),
        "failed": bool(parsed.get("failed", False)),
        "failure_reason": parsed.get("failure_reason"),
        "tools_called": (
            list(parsed.get("tools_called") or [])
            or tools_called_runtime  # fall back if subagent forgot
        ),
        "_workspace_id": workspace_id,
    }
    return normalized


_LOOP_SEMAPHORES: "dict[int, asyncio.Semaphore]" = {}
_MAX_PARALLEL_DISPATCH = 3


def _get_semaphore() -> asyncio.Semaphore:
    """Return a Semaphore bound to the *current* running loop. Lazy-created
    per-loop because a module-level Semaphore is bound to whatever loop
    happened to be running at import time (and ``asyncio.run`` creates a
    fresh loop each call, leaving a stale Semaphore that raises "Future
    attached to a different loop" on its next acquire).
    """
    loop = asyncio.get_running_loop()
    key = id(loop)
    sem = _LOOP_SEMAPHORES.get(key)
    if sem is None:
        sem = asyncio.Semaphore(_MAX_PARALLEL_DISPATCH)
        _LOOP_SEMAPHORES[key] = sem
    return sem


async def dispatch_to_projects(
    workspace_ids: list[str],
    task: str,
    *,
    registry_by_id: dict[str, ProjectRow] | None = None,
    anthropic_client: Any = None,
    model: str | None = None,
) -> list[dict]:
    """Fan out to many subagents under a per-loop Semaphore(3). Returns
    one result per id, in the same order. Empty input → ``[]``.
    """
    if not workspace_ids:
        return []
    sem = _get_semaphore()
    registry_by_id = registry_by_id or {}

    async def _one(ws: str) -> dict:
        row = registry_by_id.get(ws)
        async with sem:
            return await dispatch_to_project(
                ws,
                task,
                name=(row.name if row else None),
                description=(row.description if row else None),
                anthropic_client=anthropic_client,
                model=model,
            )

    return await asyncio.gather(*[_one(ws) for ws in workspace_ids])


# ---------------------------------------------------------------------------
# Citation post-processor (global)
# ---------------------------------------------------------------------------


_CARD_TOKEN_RE = re.compile(r"\[meeting:([^:\]]+):card:([^\]]+)\]")
_SEG_TOKEN_RE = re.compile(r"\[meeting:([^:\]]+):seg:([^\]]+)\]")
# Skip already-prefixed citations.
_PREFIXED_TOKEN_RE = re.compile(r"\[project:[^:\]]+:meeting:")


def prefix_citations_with_project(
    session: Any,
    final_text: str,
    default_project_id: Optional[str],
) -> str:
    """Rewrite ``[meeting:<m>:card:<c>]`` / ``[meeting:<m>:seg:<s>]`` to
    ``[project:<ws>:meeting:<m>:card:<c>]`` etc., resolving the workspace
    via ``meetings.artifact_id → conversation_artifacts.workspace_id``.

    Falls back to ``default_project_id`` when the meeting cannot be
    resolved (deleted / cross-environment id). If neither resolution
    works the token is left as-is with a single logged WARN.
    """
    if not final_text:
        return final_text

    meeting_ids: set[str] = set()
    for m in _CARD_TOKEN_RE.finditer(final_text):
        meeting_ids.add(m.group(1))
    for m in _SEG_TOKEN_RE.finditer(final_text):
        meeting_ids.add(m.group(1))
    if not meeting_ids:
        return final_text

    ws_by_meeting: dict[str, str] = {}
    try:
        from sqlalchemy import text as _sql_text

        rows = session.execute(
            _sql_text(
                "SELECT m.id, ca.workspace_id "
                "FROM meetings m "
                "JOIN conversation_artifacts ca ON ca.id = m.artifact_id "
                "WHERE m.id = ANY(:ids) AND m.deleted_at IS NULL"
            ),
            {"ids": list(meeting_ids)},
        ).all()
        for row in rows:
            ws_by_meeting[row[0]] = row[1]
    except Exception:  # noqa: BLE001 — best-effort post-processor.
        logger.exception("prefix_citations_with_project: meeting→workspace lookup failed")

    missed: set[str] = set()

    def _rewrite(match: re.Match[str], kind: str) -> str:
        mid, inner = match.group(1), match.group(2)
        ws = ws_by_meeting.get(mid) or default_project_id
        if ws is None:
            missed.add(mid)
            return match.group(0)
        return f"[project:{ws}:meeting:{mid}:{kind}:{inner}]"

    out = _CARD_TOKEN_RE.sub(lambda m: _rewrite(m, "card"), final_text)
    out = _SEG_TOKEN_RE.sub(lambda m: _rewrite(m, "seg"), out)

    if missed:
        logger.warning(
            "prefix_citations_with_project: could not resolve workspace for %d meeting id(s); "
            "left tokens unprefixed",
            len(missed),
        )
    return out


# ---------------------------------------------------------------------------
# Orchestrator dispatch tools (LLM-facing)
# ---------------------------------------------------------------------------


_DISPATCH_TOOL_SCHEMAS = [
    {
        "name": "dispatch_to_project",
        "description": (
            "Dispatch one project subagent for a focused task. Returns the "
            "subagent's structured JSON response with summary, citations, "
            "confidence, and refusal/failure flags."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "project_id": {"type": "string", "minLength": 1},
                "task": {"type": "string", "minLength": 1, "maxLength": 4000},
            },
            "required": ["project_id", "task"],
        },
    },
    {
        "name": "dispatch_to_projects",
        "description": (
            "Dispatch multiple project subagents in parallel (capped at 3 "
            "in-flight). Returns a list of structured JSON responses, one "
            "per project_id, in the same order."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "project_ids": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1,
                    "maxItems": 16,
                },
                "task": {"type": "string", "minLength": 1, "maxLength": 4000},
            },
            "required": ["project_ids", "task"],
        },
    },
]


async def run_project_orchestrator(
    question: str,
    *,
    session: Any = None,
    anthropic_client: Any = None,
    model: str | None = None,
) -> dict:
    """Top-level entry. Loads registry, drives the orchestrator skill in
    a tool-use loop with the two dispatch tools, post-processes
    citations, returns ``{final_text, citations, dispatches}``.

    ``session`` is required for the citation rewriter's meeting→workspace
    lookup. If None we open one via storage_router.db.SessionLocal.
    """
    from .runtime import run_skill_dynamic, _load_skill

    # 1. Resolve session (caller may pass one in for test injection).
    close_session = False
    if session is None:
        from storage_router.db import SessionLocal

        session = SessionLocal()
        close_session = True

    try:
        # 2. Load registry, render into the orchestrator's system prompt.
        rows = load_registry(session)
        registry_by_id = {r.id: r for r in rows}

        base_skill = _load_skill("project-orchestrator")
        registry_block = render_registry_prompt(rows)
        system_prompt = base_skill.replace(
            "(The runtime injects the live registry into this section at instantiation\n"
            "time. The list above is a placeholder for the prompt template.)",
            registry_block,
        )

        # 3. Build the orchestrator's two LLM-facing tools as async-capable
        #    callables. ``run_skill_dynamic`` is sync, so we use sync
        #    wrappers that block on the inner asyncio coroutine.
        dispatches_log: list[dict] = []

        def _dispatch_one_sync(*, project_id: str, task: str) -> dict:
            row = registry_by_id.get(project_id)
            coro = dispatch_to_project(
                project_id,
                task,
                name=(row.name if row else None),
                description=(row.description if row else None),
                anthropic_client=anthropic_client,
                model=model,
            )
            res = asyncio.run(coro)
            dispatches_log.append(res)
            return res

        def _dispatch_many_sync(*, project_ids: list[str], task: str) -> dict:
            coro = dispatch_to_projects(
                project_ids,
                task,
                registry_by_id=registry_by_id,
                anthropic_client=anthropic_client,
                model=model,
            )
            res_list = asyncio.run(coro)
            dispatches_log.extend(res_list)
            return {"results": res_list}

        tools: dict[str, Callable[..., dict]] = {
            "dispatch_to_project": _dispatch_one_sync,
            "dispatch_to_projects": _dispatch_many_sync,
        }

        # 4. Run the orchestrator skill. Off-load to a thread because
        #    each dispatch tool internally calls ``asyncio.run``, which
        #    requires no running loop in the calling thread.
        result = await asyncio.to_thread(
            run_skill_dynamic,
            system_prompt=system_prompt,
            tools=tools,
            tool_schemas=_DISPATCH_TOOL_SCHEMAS,
            user_message=f"User question: {question}",
            anthropic_client=anthropic_client,
            model=model,
        )

        # 5. Citation post-processing — rewrite to the global format.
        raw_text = (result or {}).get("final_text", "") or ""
        prefixed = prefix_citations_with_project(
            session, raw_text, default_project_id=None
        )

        return {
            "final_text": prefixed,
            "citations": _extract_citations(prefixed),
            "dispatches": dispatches_log,
        }
    finally:
        if close_session:
            try:
                session.close()
            except Exception:
                pass


_PROJECT_CARD_RE = re.compile(
    r"\[project:([^:\]]+):meeting:([^:\]]+):card:([^\]]+)\]"
)
_PROJECT_SEG_RE = re.compile(
    r"\[project:([^:\]]+):meeting:([^:\]]+):seg:([^\]]+)\]"
)


def _extract_citations(text: str) -> list[dict]:
    """Parse prefixed citation tokens out of the final orchestrator text.
    Returns a stable, de-duplicated list suitable for the route response.
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for m in _PROJECT_CARD_RE.finditer(text or ""):
        key = ("card", m.group(1), m.group(2), m.group(3))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "workspace_id": m.group(1),
            "meeting_id": m.group(2),
            "memory_card_id": m.group(3),
        })
    for m in _PROJECT_SEG_RE.finditer(text or ""):
        key = ("seg", m.group(1), m.group(2), m.group(3))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "workspace_id": m.group(1),
            "meeting_id": m.group(2),
            "segment_id": m.group(3),
        })
    return out


__all__ = [
    "ProjectRow",
    "load_registry",
    "render_registry_prompt",
    "bind_subagent_tools",
    "dispatch_to_project",
    "dispatch_to_projects",
    "prefix_citations_with_project",
    "run_project_orchestrator",
]
