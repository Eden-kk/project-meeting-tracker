#!/usr/bin/env python3.12
"""Live smoke for hermes-plugin meeting-memory-extraction.

Runs the real Anthropic API + real storage-router. Skips cleanly
(exit 0) when either ANTHROPIC_API_KEY is missing or the storage
router is unreachable, so CI stays green before worktree G merges.

Usage:
    .venv/bin/python scripts/smoke_extraction.py [meeting_id]
"""

from __future__ import annotations

import json
import os
import sys

import httpx

from hermes_plugin.runtime import run_skill

DEFAULT_MEETING_ID = "m_fixture001"


def _storage_router_reachable(url: str) -> bool:
    try:
        with httpx.Client(base_url=url, timeout=httpx.Timeout(2.0, connect=2.0)) as c:
            response = c.head("/")
        return response.status_code < 500
    except httpx.HTTPError:
        return False


def main(argv: list[str]) -> int:
    meeting_id = argv[1] if len(argv) > 1 else DEFAULT_MEETING_ID

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("SKIP: ANTHROPIC_API_KEY required for live smoke.")
        return 0

    storage_url = os.environ.get("STORAGE_ROUTER_URL", "http://127.0.0.1:8000")
    if not _storage_router_reachable(storage_url):
        print(
            f"SKIP: storage-router not reachable at {storage_url}; "
            "start it before live smoke."
        )
        return 0

    result = run_skill("meeting-memory-extraction", meeting_id=meeting_id)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
