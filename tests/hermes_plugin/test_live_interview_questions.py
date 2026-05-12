"""Q1 — tests for the hermes_plugin.live_interview_questions public shim.

The shim must:
  * dispatch to `llm.run_skill` (or `runtime_openai.run_skill` when
    `LLM_PROVIDER=openai`) with skill_name='live-interview-questioner';
  * encode interviewee_name and interviewee_role into the bootstrap user
    message so the skill prompt has full context;
  * parse `final_text` as JSON and return `{"questions": list[str]}`;
  * return `{"questions": []}` when parsing fails or the model refuses.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path


def test_skill_md_exists():
    pkg = importlib.import_module("hermes_plugin")
    skill_dir = Path(pkg.__file__).parent / "skills" / "live-interview-questioner"
    skill_md = skill_dir / "SKILL.md"
    assert skill_md.is_file(), "live-interview-questioner/SKILL.md is missing"
    body = skill_md.read_text()
    assert "questions" in body
    assert "interviewee" in body.lower()


def test_shim_dispatches_to_llm_run_skill(monkeypatch):
    import hermes_plugin.llm as llm
    pkg = importlib.import_module("hermes_plugin")

    captured: dict = {}

    def _fake_run_skill(*, skill_name, meeting_id=None, user_question=None, **kw):
        captured["skill_name"] = skill_name
        captured["meeting_id"] = meeting_id
        captured["user_question"] = user_question
        return {"final_text": json.dumps({"questions": ["Q1?", "Q2?", "Q3?"]})}

    monkeypatch.setattr(llm, "run_skill", _fake_run_skill)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    out = pkg.live_interview_questions(
        meeting_id="m_1",
        interviewee_name="Alice",
        interviewee_role="Staff Engineer",
        transcript_snippet="We talked about deployments.",
    )
    assert captured["skill_name"] == "live-interview-questioner"
    assert captured["meeting_id"] == "m_1"
    assert "Alice" in captured["user_question"]
    assert "Staff Engineer" in captured["user_question"]
    assert out == {"questions": ["Q1?", "Q2?", "Q3?"]}


def test_shim_dispatches_to_openai_path(monkeypatch):
    import hermes_plugin.runtime_openai as rt_openai
    pkg = importlib.import_module("hermes_plugin")

    captured: dict = {}

    def _fake_run_skill_openai(skill_name, meeting_id, user_question=None):
        captured["skill_name"] = skill_name
        captured["user_question"] = user_question
        return {"final_text": json.dumps({"questions": ["Openai Q1?", "Openai Q2?"]})}

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setattr(rt_openai, "run_skill", _fake_run_skill_openai)

    out = pkg.live_interview_questions(
        meeting_id="m_2",
        interviewee_name="Bob",
        interviewee_role="SRE",
        transcript_snippet="He mentioned the alerting pipeline.",
    )
    assert captured["skill_name"] == "live-interview-questioner"
    assert "Bob" in captured["user_question"]
    assert "SRE" in captured["user_question"]
    assert out["questions"] == ["Openai Q1?", "Openai Q2?"]


def test_shim_returns_empty_list_on_parse_failure(monkeypatch):
    import hermes_plugin.llm as llm
    pkg = importlib.import_module("hermes_plugin")

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(
        llm,
        "run_skill",
        lambda **kw: {"final_text": "not valid json at all"},
    )

    out = pkg.live_interview_questions(
        meeting_id="m_3",
        interviewee_name="Carol",
        interviewee_role=None,
        transcript_snippet="short clip",
    )
    assert out == {"questions": []}


def test_shim_interviewee_name_and_role_appear_in_bootstrap(monkeypatch):
    import hermes_plugin.llm as llm
    pkg = importlib.import_module("hermes_plugin")

    seen_question: list[str] = []

    def _capture(**kw):
        seen_question.append(kw.get("user_question", ""))
        return {"final_text": json.dumps({"questions": []})}

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(llm, "run_skill", _capture)

    pkg.live_interview_questions(
        meeting_id="m_4",
        interviewee_name="Dana",
        interviewee_role="Product Manager",
        transcript_snippet="Dana talked about the roadmap.",
    )
    assert len(seen_question) == 1
    msg = seen_question[0]
    assert "Dana" in msg
    assert "Product Manager" in msg
    assert "Dana talked about the roadmap." in msg
