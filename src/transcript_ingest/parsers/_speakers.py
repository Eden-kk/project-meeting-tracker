"""Speaker registry — assigns speaker_N ids in order of first appearance."""
from __future__ import annotations

from typing import Callable


def make_speaker_registry() -> Callable[[str | None], str | None]:
    seen: dict[str, str] = {}

    def assign(name: str | None) -> str | None:
        if name is None:
            return None
        if name not in seen:
            seen[name] = f"speaker_{len(seen) + 1}"
        return seen[name]

    return assign
