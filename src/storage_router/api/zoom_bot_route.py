"""Zoom-bot dispatch + Meeting SDK JWT-signing routes (Wave 9, Slice 2).

POST /api/zoom-bot/dispatch
    Body: {workspace_id, zoom_url}
    Creates an artifact + MeetingRow(source_type='zoom_bot', status='live'),
    parses the meeting number from the URL, and asks
    `zoom_bot_dispatcher.dispatch(...)` to spawn the bot subprocess.
    Returns 503 when Zoom Marketplace credentials are absent (the
    documented "credentials not configured" payload) or when the bot
    pool is full (`bot_pool_full`). 400 for unparseable URLs.

POST /api/zoom-bot/sdk-jwt
    Body: {meeting_number, role}
    Returns a Zoom Meeting SDK JWT signed with ZOOM_SDK_SECRET (HS256).
    The bot's headless Chromium calls this to authenticate to Zoom.

Per the plan's "Credentials-bootstrap policy", _require_zoom_creds() is
called on every request — module import never touches the credentials.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from storage_router import storage, zoom_bot_dispatcher
from storage_router.config import settings
from storage_router.db import get_session

router = APIRouter()


# Matches the meeting number in a Zoom join URL:
#   https://zoom.us/j/85412345678          -> 85412345678
#   https://us02web.zoom.us/j/12345?pwd=…  -> 12345
#   https://zoom.us/my/alice               -> NOT supported (PMI requires login)
_MEETING_NUM_RE = re.compile(r"zoom\.us/j/(\d+)", re.IGNORECASE)
# Optional passcode query param.
_PWD_RE = re.compile(r"[?&]pwd=([^&]+)", re.IGNORECASE)


def _parse_zoom_url(url: str) -> tuple[str | None, str | None]:
    """Return (meeting_number, passcode|None) or (None, _) on failure."""
    m = _MEETING_NUM_RE.search(url)
    meeting_number = m.group(1) if m else None
    p = _PWD_RE.search(url)
    passcode = p.group(1) if p else None
    return meeting_number, passcode


def _b64url(raw: bytes) -> str:
    """Base64url without padding — what JWS requires."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _sign_meeting_sdk_jwt(
    meeting_number: str,
    *,
    role: int,
    sdk_key: str,
    sdk_secret: str,
    iat: int | None = None,
    exp_seconds: int = 60 * 60 * 2,
) -> str:
    """Sign a Zoom Meeting SDK signature (HS256 JWT) with sdk_secret.

    Payload follows https://developers.zoom.us/docs/meeting-sdk/auth/:
      {sdkKey, mn, role, iat, exp, appKey, tokenExp}

    The hand-off rules:
    - ``role=0`` → participant (bot uses this).
    - ``role=1`` → host (we never use this).
    """
    iat = iat if iat is not None else int(time.time())
    exp = iat + exp_seconds
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sdkKey": sdk_key,
        "appKey": sdk_key,
        "mn": meeting_number,
        "role": role,
        "iat": iat,
        "exp": exp,
        "tokenExp": exp,
    }
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode("ascii")
    sig = hmac.new(sdk_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"


def _creds_missing_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "zoom_creds_missing",
                "message": (
                    "Zoom Marketplace credentials not configured — set "
                    "ZOOM_SDK_KEY, ZOOM_SDK_SECRET, ZOOM_OAUTH_CLIENT_ID, "
                    "ZOOM_OAUTH_CLIENT_SECRET in the environment before "
                    "dispatching a bot."
                ),
            }
        },
    )


class DispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(..., min_length=1, max_length=64)
    zoom_url: str = Field(..., min_length=10, max_length=2048)
    title: str = Field(default="Zoom meeting", max_length=200)


class SdkJwtRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meeting_number: str = Field(..., pattern=r"^\d+$", min_length=5, max_length=16)
    role: Literal[0, 1] = 0


@router.post("/api/zoom-bot/dispatch", status_code=201)
async def dispatch_zoom_bot(
    request: Request,
    body: DispatchRequest,
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Create a meeting + spawn a bot subprocess for it."""
    try:
        zoom_bot_dispatcher._require_zoom_creds()
    except RuntimeError:
        return _creds_missing_response()

    meeting_number, _passcode = _parse_zoom_url(body.zoom_url)
    if meeting_number is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_zoom_url",
                    "message": (
                        "Could not parse a meeting number from the URL. "
                        "Expected a link like https://zoom.us/j/<number>."
                    ),
                }
            },
        )

    artifact = storage.create_artifact(
        session,
        workspace_id=body.workspace_id,
        source_type="zoom_bot",
        capture_mode="live",
        title=body.title,
        created_by="u_dev",
    )
    meeting = storage.create_meeting(
        session, artifact_id=artifact.id, title=body.title, status="live"
    )
    meeting.zoom_meeting_number = meeting_number
    session.commit()

    # Resolve the storage-router URL the bot will call back into. The
    # incoming `Request` already carries the public base URL the client
    # used, which is what the bot (running on the same pod or on a
    # proxied URL) should call.
    storage_router_url = str(request.base_url).rstrip("/")

    try:
        zoom_bot_dispatcher.dispatch(
            meeting.id,
            body.zoom_url,
            storage_router_url=storage_router_url,
        )
    except zoom_bot_dispatcher.BotPoolFull as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "bot_pool_full",
                    "message": str(exc),
                }
            },
        )
    except zoom_bot_dispatcher.BotPrereqMissing as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "bot_prereqs_missing",
                    "message": str(exc),
                }
            },
        )

    return JSONResponse(
        status_code=201,
        content={
            "meeting_id": meeting.id,
            "artifact_id": artifact.id,
            "zoom_meeting_number": meeting_number,
            "status": "live",
        },
    )


@router.post("/api/zoom-bot/sdk-jwt")
async def sign_sdk_jwt(body: SdkJwtRequest) -> JSONResponse:
    """Return a fresh Meeting-SDK signature for the bot's join() call."""
    try:
        zoom_bot_dispatcher._require_zoom_creds()
    except RuntimeError:
        return _creds_missing_response()

    signature = _sign_meeting_sdk_jwt(
        body.meeting_number,
        role=body.role,
        sdk_key=settings.zoom_sdk_key,
        sdk_secret=settings.zoom_sdk_secret,
    )
    return JSONResponse(
        status_code=200,
        content={
            "signature": signature,
            "sdk_key": settings.zoom_sdk_key,
            "meeting_number": body.meeting_number,
            "role": body.role,
        },
    )
