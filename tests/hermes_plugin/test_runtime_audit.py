"""Wave 2.1: tests for the meeting-card-audit pass.

Exercises ``run_card_audit`` with a mocked Anthropic client and a mocked
storage router. Confirms:
- weak cards get their confidence patched via update_card_confidence;
- unsupported cards get hidden via hide_card;
- a tool budget violation (create_draft_memory_card) is rejected;
- the count summary is correct.
"""

from __future__ import annotations

import httpx

from hermes_plugin.runtime import run_card_audit

from .conftest import make_message


_CARD_A = {
    "memory_card_id": "mc_a",
    "meeting_id": "m_audit01",
    "type": "decision",
    "title": "Strongly supported decision",
    "content": "x",
    "source_chunk_ids": ["seg_001"],
    "confidence": 0.9,
}

_CARD_B = {
    "memory_card_id": "mc_b",
    "meeting_id": "m_audit01",
    "type": "open_question",
    "title": "Wobbly inference",
    "content": "x",
    "source_chunk_ids": ["seg_002"],
    "confidence": 0.8,
}

_CARD_C = {
    "memory_card_id": "mc_c",
    "meeting_id": "m_audit01",
    "type": "risk",
    "title": "Hallucinated risk",
    "content": "x",
    "source_chunk_ids": ["seg_003"],
    "confidence": 0.7,
}


def _transcript() -> dict:
    return {
        "meeting_id": "m_audit01",
        "segments": [
            {
                "segment_id": "seg_001",
                "speaker_id": "speaker_1",
                "speaker_name": "Alice",
                "start_ms": 0,
                "end_ms": 5000,
                "text": "We've decided to ship by Friday.",
                "confidence": None,
                "source_type": "transcript_file",
                "is_final": True,
            },
            {
                "segment_id": "seg_002",
                "speaker_id": "speaker_2",
                "speaker_name": "Bob",
                "start_ms": 6000,
                "end_ms": 11000,
                "text": "Maybe we should talk to legal at some point.",
                "confidence": None,
                "source_type": "transcript_file",
                "is_final": True,
            },
            {
                "segment_id": "seg_003",
                "speaker_id": "speaker_1",
                "speaker_name": "Alice",
                "start_ms": 12000,
                "end_ms": 18000,
                "text": "Thanks everyone for showing up today.",
                "confidence": None,
                "source_type": "transcript_file",
                "is_final": True,
            },
        ],
    }


def _audit_storage_handler():
    """Return a mock-transport handler that serves transcript+cards and
    records every PATCH/POST the audit pass makes."""
    log: list[tuple[str, str, dict | None]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if req.method == "GET" and path == "/api/meetings/m_audit01/transcript":
            return httpx.Response(200, json=_transcript())
        if req.method == "GET" and path == "/api/meetings/m_audit01/memory-cards":
            return httpx.Response(
                200,
                json={"items": [_CARD_A, _CARD_B, _CARD_C], "total": 3},
            )
        if (
            req.method == "PATCH"
            and path.startswith("/api/memory-cards/")
            and path.endswith("/confidence")
        ):
            body = httpx.Request("POST", path, content=req.content)._content
            import json as _json
            payload = _json.loads(req.content.decode()) if req.content else {}
            card_id = path.split("/")[3]
            log.append(("patch_confidence", card_id, payload))
            patched = dict(_CARD_B if card_id == "mc_b" else _CARD_A)
            patched["confidence"] = payload["confidence"]
            patched["audit_reason"] = payload.get("reason")
            return httpx.Response(200, json=patched)
        if (
            req.method == "POST"
            and path.startswith("/api/memory-cards/")
            and path.endswith("/hide")
        ):
            import json as _json
            payload = _json.loads(req.content.decode()) if req.content else {}
            card_id = path.split("/")[3]
            log.append(("hide", card_id, payload))
            hidden = dict(_CARD_C if card_id == "mc_c" else _CARD_A)
            hidden["hidden_at"] = "2026-05-11T12:00:00Z"
            hidden["audit_reason"] = payload.get("reason")
            return httpx.Response(200, json=hidden)
        raise AssertionError(f"unexpected request: {req.method} {path}")

    return handler, log


def _audit_turns_normal() -> list[dict]:
    """Three turns: downgrade mc_b → hide mc_c → end_turn summary."""
    return [
        make_message(
            msg_id="audit_t1",
            content=[
                {
                    "type": "tool_use",
                    "id": "tu1",
                    "name": "update_card_confidence",
                    "input": {
                        "card_id": "mc_b",
                        "confidence": 0.4,
                        "reason": "speaker only speculated about legal review",
                    },
                }
            ],
            stop_reason="tool_use",
        ),
        make_message(
            msg_id="audit_t2",
            content=[
                {
                    "type": "tool_use",
                    "id": "tu2",
                    "name": "hide_card",
                    "input": {
                        "card_id": "mc_c",
                        "reason": "no supporting evidence in cited segments",
                    },
                }
            ],
            stop_reason="tool_use",
        ),
        make_message(
            msg_id="audit_t3",
            content=[
                {
                    "type": "text",
                    "text": "Hid 1 card (mc_c); downgraded 1 (mc_b).",
                }
            ],
            stop_reason="end_turn",
        ),
    ]


def test_run_card_audit_downgrades_and_hides(storage_client, fake_anthropic) -> None:
    handler, log = _audit_storage_handler()
    client = storage_client(handler)
    llm = fake_anthropic(_audit_turns_normal())

    result = run_card_audit("m_audit01", client=client, anthropic_client=llm)

    assert result["cards_hidden"] == 1
    assert result["cards_downgraded"] == 1
    assert "Hid 1" in result["summary"]
    # storage saw exactly one PATCH and one POST hide.
    patch_calls = [e for e in log if e[0] == "patch_confidence"]
    hide_calls = [e for e in log if e[0] == "hide"]
    assert len(patch_calls) == 1 and patch_calls[0][1] == "mc_b"
    assert patch_calls[0][2]["confidence"] == 0.4
    assert len(hide_calls) == 1 and hide_calls[0][1] == "mc_c"


def test_run_card_audit_rejects_disallowed_tool(storage_client, fake_anthropic) -> None:
    """Audit pass must not be able to create new cards. A create_draft call
    must surface as a tool_error to the agent."""
    handler, _ = _audit_storage_handler()
    client = storage_client(handler)

    scripted = [
        make_message(
            msg_id="t1",
            content=[
                {
                    "type": "tool_use",
                    "id": "tu_bad",
                    "name": "create_draft_memory_card",
                    "input": {
                        "meeting_id": "m_audit01",
                        "type": "decision",
                        "title": "new",
                        "content": "x",
                        "source_chunk_ids": ["seg_001"],
                        "confidence": 0.9,
                    },
                }
            ],
            stop_reason="tool_use",
        ),
        make_message(
            msg_id="t2",
            content=[{"type": "text", "text": "ok, stopping."}],
            stop_reason="end_turn",
        ),
    ]
    llm = fake_anthropic(scripted)

    result = run_card_audit("m_audit01", client=client, anthropic_client=llm)

    # No cards hidden/downgraded; the disallowed tool was rejected.
    assert result["cards_hidden"] == 0
    assert result["cards_downgraded"] == 0
