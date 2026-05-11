"""Pure-function state-machine tests."""
from __future__ import annotations

import pytest

from storage_router.state_machine import ALLOWED, next_status

LEGAL = [
    ("received", "transcribing"),
    ("received", "parsing"),
    ("received", "failed"),
    ("transcribing", "normalizing"),
    ("transcribing", "failed"),
    ("parsing", "normalizing"),
    ("parsing", "failed"),
    ("normalizing", "ready"),
    ("normalizing", "failed"),
]


@pytest.mark.parametrize(("cur", "tgt"), LEGAL)
def test_legal_transitions(cur: str, tgt: str) -> None:
    assert next_status(cur, tgt) == tgt


def test_self_loops_are_idempotent() -> None:
    for state in ALLOWED:
        assert next_status(state, state) == state


def test_illegal_transitions_raise() -> None:
    with pytest.raises(ValueError, match="illegal transition"):
        next_status("received", "ready")
    with pytest.raises(ValueError, match="illegal transition"):
        next_status("ready", "transcribing")
