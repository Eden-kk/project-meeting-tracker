"""Lazy resolver for the in-process `hermes_plugin` package.

The Phase-2 default is to import Hermes directly. If the plugin is not
installed in the current venv (worktree F has not landed yet), the resolver
raises HermesUnavailable so the route can map it to a 503.
"""
from __future__ import annotations


class HermesUnavailable(RuntimeError):
    """Raised when hermes_plugin is missing or its expected entrypoint is absent."""


def _import_or_503():
    try:
        import hermes_plugin  # type: ignore[import-not-found]
    except ImportError as e:
        raise HermesUnavailable(str(e)) from None
    return hermes_plugin


def run_meeting_finalization(meeting_id: str) -> dict:
    mod = _import_or_503()
    fn = getattr(mod, "meeting_finalization", None)
    if fn is None:
        raise HermesUnavailable("hermes_plugin.meeting_finalization not exported")
    return fn(meeting_id=meeting_id)


def run_meeting_qa(meeting_id: str, question: str) -> dict:
    mod = _import_or_503()
    fn = getattr(mod, "meeting_qa", None)
    if fn is None:
        raise HermesUnavailable("hermes_plugin.meeting_qa not exported")
    return fn(meeting_id=meeting_id, question=question)
