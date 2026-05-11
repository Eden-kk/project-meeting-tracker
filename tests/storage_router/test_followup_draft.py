"""Tests for the follow-up draft route (Wave 5.3).

The Hermes plugin is mocked so these tests stay deterministic and do
not require an Anthropic / OpenAI key.
"""
from __future__ import annotations

import json

import pytest

from storage_router import hermes_runtime
from storage_router.db import SessionLocal
from storage_router.storage import create_artifact, create_meeting


def _seed_meeting() -> str:
    with SessionLocal() as s:
        a = create_artifact(
            s,
            workspace_id="ws_dev",
            source_type="pasted_transcript",
            capture_mode="imported",
            title="t",
            created_by="u_dev",
            raw_text="hi",
        )
        m = create_meeting(s, artifact_id=a.id, title="t")
        s.commit()
        return m.id


@pytest.mark.asyncio
async def test_followup_draft_happy_path(client, monkeypatch):
    """A well-formed plugin response is parsed into markdown + cards_referenced."""
    meeting_id = _seed_meeting()
    payload = {
        "final_text": json.dumps(
            {
                "markdown": "Hi team,\n\n- Action: ship login",
                "cards_referenced": ["mem_1", "mem_2"],
            }
        )
    }
    monkeypatch.setattr(
        hermes_runtime, "run_followup_draft", lambda *a, **kw: payload
    )

    res = await client.post(
        f"/api/meetings/{meeting_id}/followup-draft",
        json={"tone": "decisive"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["meeting_id"] == meeting_id
    assert "ship login" in body["markdown"]
    assert body["cards_referenced"] == ["mem_1", "mem_2"]


@pytest.mark.asyncio
async def test_followup_draft_accepts_empty_body(client, monkeypatch):
    meeting_id = _seed_meeting()
    monkeypatch.setattr(
        hermes_runtime,
        "run_followup_draft",
        lambda *a, **kw: {
            "final_text": json.dumps({"markdown": "Hi team,", "cards_referenced": []})
        },
    )
    res = await client.post(f"/api/meetings/{meeting_id}/followup-draft", json={})
    assert res.status_code == 200
    assert res.json()["markdown"] == "Hi team,"


@pytest.mark.asyncio
async def test_followup_draft_rejects_bad_recipient(client, monkeypatch):
    meeting_id = _seed_meeting()
    called = {"yes": False}

    def _spy(*a, **kw):
        called["yes"] = True
        return {"final_text": "{}"}

    monkeypatch.setattr(hermes_runtime, "run_followup_draft", _spy)

    res = await client.post(
        f"/api/meetings/{meeting_id}/followup-draft",
        json={"recipient": "<script>alert(1)</script>"},
    )
    assert res.status_code == 422
    assert called["yes"] is False  # never reached the plugin


@pytest.mark.asyncio
async def test_followup_draft_accepts_unicode_recipient(client, monkeypatch):
    """Unicode names with hyphen / apostrophe must pass the sanitizer."""
    meeting_id = _seed_meeting()
    captured = {}

    def _spy(meeting_id, recipient=None, tone=None):
        captured["recipient"] = recipient
        captured["tone"] = tone
        return {"final_text": json.dumps({"markdown": "ok", "cards_referenced": []})}

    monkeypatch.setattr(hermes_runtime, "run_followup_draft", _spy)
    res = await client.post(
        f"/api/meetings/{meeting_id}/followup-draft",
        json={"recipient": "Anne-Marie O'Brien", "tone": "warm"},
    )
    assert res.status_code == 200
    assert captured["recipient"] == "Anne-Marie O'Brien"
    assert captured["tone"] == "warm"


@pytest.mark.asyncio
async def test_followup_draft_rejects_invalid_tone(client, monkeypatch):
    meeting_id = _seed_meeting()
    monkeypatch.setattr(
        hermes_runtime, "run_followup_draft", lambda *a, **kw: {"final_text": "{}"}
    )
    res = await client.post(
        f"/api/meetings/{meeting_id}/followup-draft",
        json={"tone": "hostile"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_followup_draft_503_when_hermes_missing(client, monkeypatch):
    meeting_id = _seed_meeting()

    def _boom(*a, **kw):
        raise hermes_runtime.HermesUnavailable("not installed")

    monkeypatch.setattr(hermes_runtime, "run_followup_draft", _boom)

    res = await client.post(f"/api/meetings/{meeting_id}/followup-draft", json={})
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "hermes_unavailable"


@pytest.mark.asyncio
async def test_followup_draft_handles_fenced_json(client, monkeypatch):
    """The skill may wrap its JSON output in ```json fences — strip them."""
    meeting_id = _seed_meeting()
    payload = {
        "final_text": "```json\n"
        + json.dumps({"markdown": "ok", "cards_referenced": ["m1"]})
        + "\n```"
    }
    monkeypatch.setattr(
        hermes_runtime, "run_followup_draft", lambda *a, **kw: payload
    )
    res = await client.post(f"/api/meetings/{meeting_id}/followup-draft", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["markdown"] == "ok"
    assert body["cards_referenced"] == ["m1"]


@pytest.mark.asyncio
async def test_followup_draft_falls_back_to_raw_text(client, monkeypatch):
    """If the skill emits plain markdown (no JSON), surface it as-is."""
    meeting_id = _seed_meeting()
    monkeypatch.setattr(
        hermes_runtime,
        "run_followup_draft",
        lambda *a, **kw: {"final_text": "# Notes\n\n- ship login"},
    )
    res = await client.post(f"/api/meetings/{meeting_id}/followup-draft", json={})
    assert res.status_code == 200
    body = res.json()
    assert "ship login" in body["markdown"]
    assert body["cards_referenced"] == []
