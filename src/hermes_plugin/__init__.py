"""Hermes plugin: meeting-memory tools for Claude tool-use loops.

Public surface:
- ``__version__``: package version literal.
- ``run_skill``: lazy attribute; resolved from ``hermes_plugin.runtime``.
- ``TOOL_REGISTRY``: lazy attribute; resolved from ``hermes_plugin.tools``.

Lazy resolution lets the bare ``import hermes_plugin`` work before the
later stages land. Accessing ``run_skill`` / ``TOOL_REGISTRY`` raises
``NotImplementedError`` until the implementing modules exist.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__", "run_skill", "TOOL_REGISTRY"]


def __getattr__(name: str):
    if name == "run_skill":
        try:
            from .runtime import run_skill as _run_skill
        except ImportError as exc:
            raise NotImplementedError(
                "hermes_plugin.run_skill not yet implemented"
            ) from exc
        return _run_skill
    if name == "TOOL_REGISTRY":
        try:
            from .tools import TOOL_REGISTRY as _registry
        except ImportError as exc:
            raise NotImplementedError(
                "hermes_plugin.TOOL_REGISTRY not yet implemented"
            ) from exc
        return _registry
    raise AttributeError(f"module 'hermes_plugin' has no attribute {name!r}")
