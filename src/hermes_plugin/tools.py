"""Tool implementations bridging Pydantic-validated input to client calls.

Each tool: validate kwargs through the matching input model, call the
client, validate the response through the output model, return the
JSON-serializable dump. Errors are funneled into ``ToolError`` so the
runtime has a single recoverable-failure type to handle.
"""

from __future__ import annotations

from typing import Callable

from pydantic import ValidationError

from .client import StorageRouterClient
from .errors import StorageUnavailable, ToolError
from .schemas import (
    CreateDraftMemoryCardInput,
    CreateDraftMemoryCardOutput,
    FinalizeMeetingMemoryInput,
    FinalizeMeetingMemoryOutput,
    GetMeetingTranscriptInput,
    GetMeetingTranscriptOutput,
    SearchMemoryCardsInput,
    SearchMemoryCardsOutput,
    SearchWorkspaceCardsInput,
    SearchWorkspaceCardsOutput,
    SearchWorkspaceTranscriptsInput,
    SearchWorkspaceTranscriptsOutput,
)

_AGENT_TAG = "hermes-plugin"


def _wrap_validation(exc: ValidationError) -> ToolError:
    return ToolError(status_code=422, code="invalid_input", message=str(exc))


def _wrap_storage(exc: StorageUnavailable) -> ToolError:
    return ToolError(status_code=503, code="storage_unavailable", message=str(exc))


def get_meeting_transcript(args: dict, client: StorageRouterClient) -> dict:
    try:
        parsed = GetMeetingTranscriptInput.model_validate(args)
    except ValidationError as exc:
        raise _wrap_validation(exc) from exc
    try:
        raw = client.get_meeting_transcript(parsed.meeting_id)
    except StorageUnavailable as exc:
        raise _wrap_storage(exc) from exc
    return GetMeetingTranscriptOutput.model_validate(raw).model_dump(mode="json")


def search_memory_cards(args: dict, client: StorageRouterClient) -> dict:
    try:
        parsed = SearchMemoryCardsInput.model_validate(args)
    except ValidationError as exc:
        raise _wrap_validation(exc) from exc
    try:
        raw = client.list_memory_cards(
            parsed.meeting_id,
            type=parsed.type,
            include_hidden=bool(parsed.include_hidden),
        )
    except StorageUnavailable as exc:
        raise _wrap_storage(exc) from exc
    # storage-router's list endpoint returns the pagination shape
    # {items, total}; the plugin's SearchMemoryCardsOutput expects {cards}.
    # Translate transparently so the tool stays usable.
    if isinstance(raw, dict) and "items" in raw and "cards" not in raw:
        raw = {"cards": raw.get("items", [])}
    return SearchMemoryCardsOutput.model_validate(raw).model_dump(mode="json")


def create_draft_memory_card(args: dict, client: StorageRouterClient) -> dict:
    """Create a memory card. The 'draft' name is preserved on the tool for
    backwards compatibility with the Hermes skill prompts; the storage layer
    no longer carries any per-card state machine."""
    try:
        parsed = CreateDraftMemoryCardInput.model_validate(args)
    except ValidationError as exc:
        raise _wrap_validation(exc) from exc
    payload = parsed.model_dump(mode="json", exclude_none=True)
    payload["created_by_agent"] = _AGENT_TAG
    try:
        raw = client.create_memory_card(payload)
    except StorageUnavailable as exc:
        raise _wrap_storage(exc) from exc
    return CreateDraftMemoryCardOutput.model_validate(raw).model_dump(mode="json")


def finalize_meeting_memory(args: dict, client: StorageRouterClient) -> dict:
    try:
        parsed = FinalizeMeetingMemoryInput.model_validate(args)
    except ValidationError as exc:
        raise _wrap_validation(exc) from exc
    try:
        raw = client.finalize_meeting(parsed.meeting_id)
    except StorageUnavailable as exc:
        raise _wrap_storage(exc) from exc
    return FinalizeMeetingMemoryOutput.model_validate(raw).model_dump(mode="json")


def search_workspace_transcripts(args: dict, client: StorageRouterClient) -> dict:
    """Wave 4.3: cross-meeting FTS over speaker_segments, workspace-scoped."""
    try:
        parsed = SearchWorkspaceTranscriptsInput.model_validate(args)
    except ValidationError as exc:
        raise _wrap_validation(exc) from exc
    try:
        raw = client.search_workspace_transcripts(
            parsed.workspace_id, parsed.q, limit=parsed.limit or 10
        )
    except StorageUnavailable as exc:
        raise _wrap_storage(exc) from exc
    return SearchWorkspaceTranscriptsOutput.model_validate(raw).model_dump(mode="json")


def search_workspace_cards(args: dict, client: StorageRouterClient) -> dict:
    """Wave 4.3: cross-meeting FTS over memory_cards, workspace-scoped."""
    try:
        parsed = SearchWorkspaceCardsInput.model_validate(args)
    except ValidationError as exc:
        raise _wrap_validation(exc) from exc
    try:
        raw = client.search_workspace_cards(
            parsed.workspace_id,
            parsed.q,
            type=parsed.type,
            limit=parsed.limit or 10,
        )
    except StorageUnavailable as exc:
        raise _wrap_storage(exc) from exc
    return SearchWorkspaceCardsOutput.model_validate(raw).model_dump(mode="json")


TOOL_REGISTRY: dict[str, Callable[[dict, StorageRouterClient], dict]] = {
    "get_meeting_transcript": get_meeting_transcript,
    "search_memory_cards": search_memory_cards,
    "create_draft_memory_card": create_draft_memory_card,
    "finalize_meeting_memory": finalize_meeting_memory,
    "search_workspace_transcripts": search_workspace_transcripts,
    "search_workspace_cards": search_workspace_cards,
}


TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_meeting_transcript": "Fetch the normalized transcript (segments) for a meeting.",
    "search_memory_cards": "List visible memory cards for a meeting, optionally filtered by type.",
    "create_draft_memory_card": (
        "Create a memory card for a meeting. The server tags "
        "created_by_agent='hermes-plugin' automatically. Card is live "
        "immediately; the audit + consolidation passes flag bad cards."
    ),
    "finalize_meeting_memory": (
        "Finalize a meeting: commit drafts and freeze the memory record."
    ),
    "search_workspace_transcripts": (
        "Cross-meeting Postgres FTS over transcript segments within a "
        "workspace. Returns ranked hits keyed by segment_id + meeting_id "
        "so the caller can cite them with [meeting:<id>:seg:<id>]."
    ),
    "search_workspace_cards": (
        "Cross-meeting Postgres FTS over memory cards within a workspace, "
        "optionally filtered by card type. Returns ranked hits keyed by "
        "memory_card_id + meeting_id so the caller can cite them with "
        "[meeting:<id>:card:<id>]. Hidden cards are excluded automatically."
    ),
}


__all__ = [
    "TOOL_REGISTRY",
    "TOOL_DESCRIPTIONS",
    "get_meeting_transcript",
    "search_memory_cards",
    "create_draft_memory_card",
    "finalize_meeting_memory",
    "search_workspace_transcripts",
    "search_workspace_cards",
]
