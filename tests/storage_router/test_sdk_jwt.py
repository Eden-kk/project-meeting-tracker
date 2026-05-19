"""POST /api/zoom-bot/sdk-jwt — Meeting SDK JWT signing (Slice 2).

Plan §"JWT-signing endpoint uses ZOOM_SDK_SECRET ONLY" — the negative
test verifies that an OAuth-client-secret-signed verification FAILS,
proving the endpoint does not accidentally use the wrong secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

import pytest

from storage_router import zoom_bot_dispatcher
from storage_router.api import zoom_bot_route


def _set_creds(monkeypatch) -> None:
    monkeypatch.setattr(zoom_bot_dispatcher.settings, "zoom_sdk_key", "k_sdk")
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings, "zoom_sdk_secret", "s_meeting_sdk"
    )
    monkeypatch.setattr(zoom_bot_dispatcher.settings, "zoom_oauth_client_id", "oid")
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings,
        "zoom_oauth_client_secret",
        "s_oauth_client",
    )
    # The route reads `settings` directly; the dispatcher imports the
    # same singleton, so a single monkeypatch flips both call sites.
    monkeypatch.setattr(zoom_bot_route.settings, "zoom_sdk_key", "k_sdk")
    monkeypatch.setattr(
        zoom_bot_route.settings, "zoom_sdk_secret", "s_meeting_sdk"
    )


def _verify_hs256(token: str, secret: str) -> bool:
    """Verify a JWS HS256 token signature against ``secret``."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        return False
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(
        secret.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    # base64url-decode the provided signature.
    padded = sig_b64 + "=" * (-len(sig_b64) % 4)
    provided = base64.urlsafe_b64decode(padded)
    return hmac.compare_digest(expected, provided)


@pytest.mark.asyncio
async def test_sdk_jwt_503_when_creds_missing(client, monkeypatch) -> None:
    monkeypatch.setattr(zoom_bot_dispatcher.settings, "zoom_sdk_key", "")
    monkeypatch.setattr(zoom_bot_dispatcher.settings, "zoom_sdk_secret", "")
    monkeypatch.setattr(zoom_bot_dispatcher.settings, "zoom_oauth_client_id", "")
    monkeypatch.setattr(
        zoom_bot_dispatcher.settings, "zoom_oauth_client_secret", ""
    )
    resp = await client.post(
        "/api/zoom-bot/sdk-jwt", json={"meeting_number": "12345"}
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "zoom_creds_missing"
    assert "ZOOM_SDK_KEY" in body["error"]["message"]


@pytest.mark.asyncio
async def test_sdk_jwt_signs_with_sdk_secret_and_fails_with_oauth_secret(
    client, monkeypatch
) -> None:
    """Plan-locked: JWT must verify with ZOOM_SDK_SECRET, NOT with the OAuth secret."""
    _set_creds(monkeypatch)
    resp = await client.post(
        "/api/zoom-bot/sdk-jwt", json={"meeting_number": "85412345678"}
    )
    assert resp.status_code == 200
    token = resp.json()["signature"]
    assert _verify_hs256(token, "s_meeting_sdk") is True
    # Negative — verifying with the OAuth client secret MUST fail.
    assert _verify_hs256(token, "s_oauth_client") is False


@pytest.mark.asyncio
async def test_sdk_jwt_payload_shape(client, monkeypatch) -> None:
    _set_creds(monkeypatch)
    resp = await client.post(
        "/api/zoom-bot/sdk-jwt", json={"meeting_number": "85412345678"}
    )
    body = resp.json()
    assert body["sdk_key"] == "k_sdk"
    assert body["meeting_number"] == "85412345678"
    assert body["role"] == 0

    # Decode the payload to check exp is in the future.
    _h, payload_b64, _sig = body["signature"].split(".")
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded))
    assert payload["sdkKey"] == "k_sdk"
    assert payload["mn"] == "85412345678"
    assert payload["role"] == 0
    assert payload["exp"] > payload["iat"]


@pytest.mark.skipif(
    not os.getenv("ZOOM_SDK_KEY"),
    reason="Zoom Marketplace creds not in env (CI path).",
)
@pytest.mark.asyncio
async def test_sdk_jwt_with_real_creds_verifies(client) -> None:
    """Smoke test against real Marketplace creds — only runs when env is populated."""
    resp = await client.post(
        "/api/zoom-bot/sdk-jwt", json={"meeting_number": "12345"}
    )
    assert resp.status_code == 200
    token = resp.json()["signature"]
    real_secret = os.environ["ZOOM_SDK_SECRET"]
    assert _verify_hs256(token, real_secret) is True
