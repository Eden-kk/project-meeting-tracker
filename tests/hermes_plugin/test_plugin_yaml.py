"""Guard the plugin manifest against drifting from the registered tools."""

from __future__ import annotations

from pathlib import Path

import yaml

from hermes_plugin.tools import TOOL_REGISTRY


PLUGIN_YAML = Path(__file__).resolve().parents[2] / "src" / "hermes_plugin" / "plugin.yaml"


def test_plugin_yaml_lists_all_registered_tools():
    spec = yaml.safe_load(PLUGIN_YAML.read_text(encoding="utf-8"))
    assert set(spec["tools"]) == set(TOOL_REGISTRY)


def test_plugin_yaml_top_level_keys():
    spec = yaml.safe_load(PLUGIN_YAML.read_text(encoding="utf-8"))
    assert spec["name"] == "live-meeting-memory"
    assert spec["skills_dir"] == "./skills"
    assert isinstance(spec["version"], str)
