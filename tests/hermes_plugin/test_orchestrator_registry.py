"""Registry loader + cache behavior tests (mocked session, no DB)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from hermes_plugin import orchestrator as orch


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def order_by(self, *_):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.queries = 0

    def query(self, model):
        self.queries += 1
        return _FakeQuery(self._rows)


@pytest.fixture(autouse=True)
def _reset_cache():
    orch._clear_registry_cache()
    yield
    orch._clear_registry_cache()


def test_load_registry_returns_rows_and_renders_dash_for_null_description():
    rows = [
        SimpleNamespace(id="ws_a", name="Alpha", description=None,
                        last_meeting_at=None),
        SimpleNamespace(id="ws_b", name="Beta", description="Customer interviews.",
                        last_meeting_at=datetime(2026, 5, 1, tzinfo=UTC)),
    ]
    s = _FakeSession(rows)
    result = orch.load_registry(s)
    assert [r.id for r in result] == ["ws_a", "ws_b"]
    assert result[0].description is None
    rendered = orch.render_registry_prompt(result)
    assert "id=ws_a" in rendered
    assert "description=—" in rendered
    assert "description=Customer interviews." in rendered
    assert "last_meeting=2026-05-01T00:00:00+00:00" in rendered


def test_load_registry_caches_within_ttl(monkeypatch):
    rows = [SimpleNamespace(id="ws_a", name="Alpha", description=None,
                            last_meeting_at=None)]
    s = _FakeSession(rows)
    fake_clock = {"now": 1000.0}
    monkeypatch.setattr(orch, "_now_monotonic", lambda: fake_clock["now"])

    orch.load_registry(s)
    assert s.queries == 1
    orch.load_registry(s)  # within TTL
    assert s.queries == 1

    fake_clock["now"] = 1000.0 + orch._REGISTRY_TTL_SEC + 1.0  # past TTL
    orch.load_registry(s)
    assert s.queries == 2


def test_load_registry_empty_renders_placeholder():
    s = _FakeSession([])
    out = orch.render_registry_prompt(orch.load_registry(s))
    assert out == "(no projects registered)"
