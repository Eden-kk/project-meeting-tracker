"""Pure-function processing-status transitions; SCOPE.md state diagram."""
from __future__ import annotations

ALLOWED: dict[str, set[str]] = {
    "received": {"transcribing", "parsing", "failed"},
    "transcribing": {"normalizing", "failed"},
    "parsing": {"normalizing", "failed"},
    "normalizing": {"ready", "failed"},
    "ready": set(),
    "failed": set(),
}


def next_status(current: str, target: str) -> str:
    """Validate a transition. Same-state is an idempotent no-op."""
    if current == target:
        return target
    if target not in ALLOWED.get(current, set()):
        raise ValueError(f"illegal transition {current} -> {target}")
    return target
