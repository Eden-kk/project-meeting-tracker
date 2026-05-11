"""LLM_PROVIDER dispatcher routing tests."""

from __future__ import annotations

import pytest

from hermes_plugin import llm as llm_dispatcher


def test_default_provider_is_anthropic(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    captured: dict = {}

    def fake_anthropic(**kwargs):
        captured["called"] = "anthropic"
        captured["kwargs"] = kwargs
        return {"final_text": "a", "tool_calls": [], "iterations": 1}

    monkeypatch.setattr("hermes_plugin.runtime.run_skill", fake_anthropic)
    result = llm_dispatcher.run_skill(skill_name="meeting-qa", meeting_id="m_1", user_question="q?")
    assert captured["called"] == "anthropic"
    assert result["final_text"] == "a"


def test_provider_anthropic_explicit(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    captured: dict = {}

    def fake_anthropic(**kwargs):
        captured["called"] = "anthropic"
        return {"final_text": "a", "tool_calls": [], "iterations": 1}

    def fake_openai(**kwargs):
        captured["called"] = "openai"
        return {"final_text": "o", "tool_calls": [], "iterations": 1}

    monkeypatch.setattr("hermes_plugin.runtime.run_skill", fake_anthropic)
    monkeypatch.setattr("hermes_plugin.runtime_openai.run_skill", fake_openai)

    llm_dispatcher.run_skill(skill_name="meeting-qa", meeting_id="m_1", user_question="q?")
    assert captured["called"] == "anthropic"


def test_provider_openai_routes_to_openai_runtime(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    captured: dict = {}

    def fake_openai(**kwargs):
        captured["called"] = "openai"
        captured["kwargs"] = kwargs
        return {"final_text": "o", "tool_calls": [], "iterations": 1}

    monkeypatch.setattr("hermes_plugin.runtime_openai.run_skill", fake_openai)
    result = llm_dispatcher.run_skill(skill_name="meeting-qa", meeting_id="m_1", user_question="q?")
    assert captured["called"] == "openai"
    assert result["final_text"] == "o"
    # kwargs should propagate untouched (no provider= leakage).
    assert "provider" not in captured["kwargs"]


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        llm_dispatcher.run_skill(skill_name="meeting-qa", meeting_id="m_1", user_question="q?")


def test_provider_kwarg_overrides_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")

    def fake_openai(**kwargs):
        return {"final_text": "o", "tool_calls": [], "iterations": 1}

    monkeypatch.setattr("hermes_plugin.runtime_openai.run_skill", fake_openai)
    result = llm_dispatcher.run_skill(
        skill_name="meeting-qa",
        meeting_id="m_1",
        user_question="q?",
        provider="openai",
    )
    assert result["final_text"] == "o"


def test_provider_value_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "OpenAI")

    def fake_openai(**kwargs):
        return {"final_text": "o", "tool_calls": [], "iterations": 1}

    monkeypatch.setattr("hermes_plugin.runtime_openai.run_skill", fake_openai)
    result = llm_dispatcher.run_skill(skill_name="meeting-qa", meeting_id="m_1", user_question="q?")
    assert result["final_text"] == "o"
