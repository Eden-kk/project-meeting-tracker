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


def run_meeting_finalization(meeting_id: str, chunk_minutes: int = 5) -> dict:
    """Forward to ``hermes_plugin.meeting_finalization`` with the chunk knob.

    ``chunk_minutes`` is the time-window size (in minutes) used when the
    transcript carries timestamps. The plugin falls back to single-pass
    finalization for untimestamped transcripts regardless of this value.
    """
    mod = _import_or_503()
    fn = getattr(mod, "meeting_finalization", None)
    if fn is None:
        raise HermesUnavailable("hermes_plugin.meeting_finalization not exported")
    return fn(meeting_id=meeting_id, chunk_minutes=chunk_minutes)


def run_meeting_qa(meeting_id: str, question: str) -> dict:
    mod = _import_or_503()
    fn = getattr(mod, "meeting_qa", None)
    if fn is None:
        raise HermesUnavailable("hermes_plugin.meeting_qa not exported")
    return fn(meeting_id=meeting_id, question=question)
