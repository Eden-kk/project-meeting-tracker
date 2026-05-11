"""Tests for the hermes_plugin.followup_draft public shim (Wave 5.3).

The shim must:
  * forward (meeting_id, recipient, tone) to the LLM dispatcher's
    run_skill with skill_name='meeting-followup-draft';
  * encode optional recipient + tone into the bootstrap `user_question`;
  * accept the SKILL.md prompt without import-time errors.
"""
from __future__ import annotations

import importlib
from pathlib import Path


def test_skill_md_exists():
    pkg = importlib.import_module("hermes_plugin")
    skill_dir = Path(pkg.__file__).parent / "skills" / "meeting-followup-draft"
    skill_md = skill_dir / "SKILL.md"
    assert skill_md.is_file(), "meeting-followup-draft/SKILL.md is missing"
    body = skill_md.read_text()
    assert "tone" in body.lower()
    assert "cards_referenced" in body


def test_followup_draft_invokes_dispatcher(monkeypatch):
    import hermes_plugin.llm as llm
    pkg = importlib.import_module("hermes_plugin")

    captured: dict = {}

    def _fake_run_skill(*, skill_name, meeting_id, user_question=None, **kw):
        captured["skill_name"] = skill_name
        captured["meeting_id"] = meeting_id
        captured["user_question"] = user_question
        return {"final_text": '{"markdown": "ok", "cards_referenced": []}'}

    monkeypatch.setattr(llm, "run_skill", _fake_run_skill)
    out = pkg.followup_draft(meeting_id="m_1", recipient="Bob", tone="warm")
    assert captured["skill_name"] == "meeting-followup-draft"
    assert captured["meeting_id"] == "m_1"
    assert "recipient=Bob" in captured["user_question"]
    assert "tone=warm" in captured["user_question"]
    assert "markdown" in out["final_text"]


def test_followup_draft_no_optional_args(monkeypatch):
    """When both recipient and tone are omitted, user_question is None."""
    import hermes_plugin.llm as llm
    pkg = importlib.import_module("hermes_plugin")

    captured: dict = {}

    def _fake_run_skill(*, skill_name, meeting_id, user_question=None, **kw):
        captured["user_question"] = user_question
        return {"final_text": "{}"}

    monkeypatch.setattr(llm, "run_skill", _fake_run_skill)
    pkg.followup_draft(meeting_id="m_1")
    assert captured["user_question"] is None
