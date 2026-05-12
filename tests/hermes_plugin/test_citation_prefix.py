"""Citation post-processor tests — global rewrite to ``[project:<ws>:meeting:...]``."""

from __future__ import annotations

from hermes_plugin import orchestrator as orch


class _FakeRow(tuple):
    """SQLAlchemy ``.all()`` returns rows that index like tuples."""
    def __new__(cls, mid, ws):
        return super().__new__(cls, (mid, ws))


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, ws_by_meeting: dict):
        self._map = ws_by_meeting
        self.calls: list[dict] = []

    def execute(self, stmt, params=None):
        params = params or {}
        self.calls.append(params)
        ids = params.get("ids", [])
        rows = [_FakeRow(m, self._map[m]) for m in ids if m in self._map]
        return _FakeResult(rows)


def test_rewrite_card_token():
    text = "We agreed to ship [meeting:m1:card:c2]."
    s = _FakeSession({"m1": "ws_a"})
    out = orch.prefix_citations_with_project(s, text, default_project_id=None)
    assert out == "We agreed to ship [project:ws_a:meeting:m1:card:c2]."


def test_rewrite_seg_token():
    text = "Bob said it [meeting:m1:seg:s7]."
    s = _FakeSession({"m1": "ws_a"})
    out = orch.prefix_citations_with_project(s, text, default_project_id=None)
    assert out == "Bob said it [project:ws_a:meeting:m1:seg:s7]."


def test_multiple_citations_one_paragraph():
    text = (
        "First [meeting:m1:card:c1], then later [meeting:m2:seg:s9], "
        "and finally [meeting:m1:card:c2]."
    )
    s = _FakeSession({"m1": "ws_a", "m2": "ws_b"})
    out = orch.prefix_citations_with_project(s, text, default_project_id=None)
    assert "[project:ws_a:meeting:m1:card:c1]" in out
    assert "[project:ws_b:meeting:m2:seg:s9]" in out
    assert "[project:ws_a:meeting:m1:card:c2]" in out
    # Make sure no legacy form survives.
    assert "[meeting:m1:card:c1]" not in out
    assert "[meeting:m2:seg:s9]" not in out


def test_unresolved_meeting_falls_back_to_default_project():
    text = "Stale ref [meeting:m_missing:card:c1]."
    s = _FakeSession({})  # no mapping
    out = orch.prefix_citations_with_project(s, text, default_project_id="ws_caller")
    assert out == "Stale ref [project:ws_caller:meeting:m_missing:card:c1]."


def test_unresolved_meeting_no_default_left_as_is():
    text = "Stale ref [meeting:m_missing:card:c1]."
    s = _FakeSession({})
    out = orch.prefix_citations_with_project(s, text, default_project_id=None)
    assert out == text  # untouched (logs a WARN, doesn't crash)
