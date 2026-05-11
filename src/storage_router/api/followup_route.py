"""Follow-up draft route (Wave 5.3).

POST /api/meetings/{id}/followup-draft

Body: `{recipient?, tone?}`. `recipient` is sanitized (max 100 chars,
alphanumeric + space + hyphen + apostrophe only) — any other character
is rejected with 422. `tone` is constrained to {decisive, warm,
neutral}. The route forwards to `hermes_runtime.run_followup_draft`
and parses the dispatcher's `final_text` into the on-the-wire
`{markdown, cards_referenced}` shape.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from storage_router import hermes_runtime

router = APIRouter()


# A relaxed acceptance set for free-text recipient names. Letters, marks,
# digits, spaces, hyphens, apostrophes only — common "Hi Anne-Marie" /
# "Hi O'Brien" cases work; HTML / script characters do not.
_RECIPIENT_RE = re.compile(r"^[\w \-']{1,100}$", re.UNICODE)


class FollowupDraftRequest(BaseModel):
    """Inbound shape for POST /api/meetings/{id}/followup-draft.

    The validator rejects malformed `recipient` with 422 so the LLM
    never sees attacker-controlled punctuation in the prompt.
    """

    model_config = ConfigDict(extra="forbid")

    recipient: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Free-text recipient name; sanitized to alphanumeric + space + "
            "hyphen + apostrophe only. Optional."
        ),
    )
    tone: Literal["decisive", "warm", "neutral"] | None = None

    @field_validator("recipient")
    @classmethod
    def _validate_recipient(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not _RECIPIENT_RE.match(v):
            raise ValueError(
                "recipient must be 1-100 chars: letters, digits, spaces, "
                "hyphen, apostrophe only"
            )
        return v


class FollowupDraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meeting_id: str
    markdown: str
    cards_referenced: list[str] = Field(default_factory=list)


def _hermes_unavailable(exc: hermes_runtime.HermesUnavailable) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "hermes_unavailable", "message": str(exc)}},
    )


def _parse_skill_output(raw: dict) -> tuple[str, list[str]]:
    """Pull the markdown + cards_referenced out of the dispatcher result.

    The skill is contracted to return JSON in `final_text`; we
    defensively handle the case where the model emitted plain prose
    by treating the entire `final_text` as the markdown body.
    """
    text = (raw or {}).get("final_text", "") or ""
    # Look for a fenced or bare JSON object.
    candidate = text.strip()
    # Strip ```json fences if present.
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```\s*$", "", candidate)
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict) and isinstance(parsed.get("markdown"), str):
            cards = parsed.get("cards_referenced") or []
            if not isinstance(cards, list):
                cards = []
            return parsed["markdown"], [str(c) for c in cards]
    except (json.JSONDecodeError, ValueError):
        pass
    # Fall back: treat the whole text as markdown.
    return text, []


@router.post("/api/meetings/{meeting_id}/followup-draft")
def followup_draft(meeting_id: str, body: FollowupDraftRequest):
    try:
        result = hermes_runtime.run_followup_draft(
            meeting_id,
            recipient=body.recipient,
            tone=body.tone,
        )
    except hermes_runtime.HermesUnavailable as e:
        return _hermes_unavailable(e)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    markdown, cards = _parse_skill_output(result)
    return FollowupDraftResponse(
        meeting_id=meeting_id, markdown=markdown, cards_referenced=cards
    ).model_dump(mode="json")
