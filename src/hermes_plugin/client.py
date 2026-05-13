"""Sync httpx wrapper around storage-router's /api/* surface."""

from __future__ import annotations

import os
from typing import Optional

import httpx

from .errors import StorageUnavailable, ToolError

_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


class StorageRouterClient:
    """Thin wrapper exposing the four routes hermes-plugin tools need.

    Tests inject ``transport=httpx.MockTransport(...)`` to drive
    deterministic responses without a live router.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        transport: Optional[httpx.BaseTransport] = None,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
    ) -> None:
        resolved_base = base_url or os.environ.get(
            "STORAGE_ROUTER_URL", "http://127.0.0.1:8000"
        )
        self._client = httpx.Client(
            base_url=resolved_base,
            transport=transport,
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "StorageRouterClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # --- routes ---

    def get_meeting_transcript(self, meeting_id: str) -> dict:
        return self._request("GET", f"/api/meetings/{meeting_id}/transcript")

    def list_memory_cards(
        self,
        meeting_id: str,
        *,
        type: Optional[str] = None,
        include_hidden: bool = False,
    ) -> dict:
        """List visible cards for a meeting (Phase-3: no `state` filter).

        ``include_hidden`` is forwarded to the server which controls the
        agent-driven `hidden_at IS NULL` filter.
        """
        params: dict[str, str] = {}
        if type is not None:
            params["type"] = type
        if include_hidden:
            params["include_hidden"] = "true"
        return self._request(
            "GET",
            f"/api/meetings/{meeting_id}/memory-cards",
            params=params or None,
        )

    def create_memory_card(self, payload: dict) -> dict:
        return self._request("POST", "/api/memory-cards", json=payload)

    def search_workspace_transcripts(
        self,
        workspace_id: str,
        q: Optional[str] = None,
        *,
        limit: int = 10,
    ) -> dict:
        """Wave 4.3: cross-meeting transcript FTS, scoped to a workspace.

        When ``q`` is None/empty, the route returns the most recent
        segments in the workspace (no FTS predicate).
        """
        params: dict[str, str | int] = {
            "workspace_id": workspace_id,
            "limit": limit,
        }
        if q:
            params["q"] = q
        return self._request("GET", "/api/search/transcripts", params=params)

    def search_workspace_cards(
        self,
        workspace_id: str,
        q: Optional[str] = None,
        *,
        type: Optional[str] = None,
        limit: int = 10,
    ) -> dict:
        """Wave 4.3: cross-meeting card FTS, scoped to a workspace.

        When ``q`` is None/empty, the route returns the highest-confidence
        / most recent cards matching the remaining filters.
        """
        params: dict[str, str | int] = {
            "workspace_id": workspace_id,
            "limit": limit,
        }
        if q:
            params["q"] = q
        if type is not None:
            params["type"] = type
        return self._request("GET", "/api/search/cards", params=params)

    def finalize_meeting(self, meeting_id: str) -> dict:
        return self._request("POST", f"/api/meetings/{meeting_id}/finalize")

    def update_card_confidence(
        self,
        card_id: str,
        confidence: float,
        reason: str | None = None,
    ) -> dict:
        payload: dict = {"confidence": confidence}
        if reason is not None:
            payload["reason"] = reason
        return self._request(
            "PATCH", f"/api/memory-cards/{card_id}/confidence", json=payload
        )

    def hide_card(self, card_id: str, reason: str | None = None) -> dict:
        payload: dict = {}
        if reason is not None:
            payload["reason"] = reason
        return self._request(
            "POST", f"/api/memory-cards/{card_id}/hide", json=payload
        )

    def supersede_card(self, loser_id: str, winner_id: str) -> dict:
        return self._request(
            "POST",
            f"/api/memory-cards/{loser_id}/supersede-into/{winner_id}",
        )

    # --- internals ---

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> dict:
        try:
            response = self._client.request(method, path, params=params, json=json)
        except httpx.HTTPError as exc:
            raise StorageUnavailable(f"{method} {path} transport error: {exc}") from exc

        if 200 <= response.status_code < 300:
            try:
                return response.json()
            except ValueError as exc:
                raise StorageUnavailable(
                    f"{method} {path} returned non-JSON body"
                ) from exc

        if 400 <= response.status_code < 500:
            code, message = _extract_error(response)
            raise ToolError(
                status_code=response.status_code,
                code=code,
                message=message,
            )

        # 5xx
        raise StorageUnavailable(
            f"{method} {path} returned {response.status_code}: {response.text[:200]}"
        )


def _extract_error(response: httpx.Response) -> tuple[str, str]:
    """Pull a {code, message} pair from a 4xx body, with sane fallbacks."""
    try:
        body = response.json()
    except ValueError:
        return f"http_{response.status_code}", response.text[:200] or response.reason_phrase
    if isinstance(body, dict):
        code = str(body.get("code") or f"http_{response.status_code}")
        message = str(body.get("message") or body.get("detail") or response.reason_phrase)
        return code, message
    return f"http_{response.status_code}", str(body)[:200]
