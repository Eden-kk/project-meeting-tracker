"""LLM provider dispatcher for the hermes plugin runtime.

Reads the ``LLM_PROVIDER`` env var (default ``"anthropic"``) and routes
``run_skill`` calls to either :mod:`hermes_plugin.runtime` (Anthropic
Claude) or :mod:`hermes_plugin.runtime_openai` (OpenAI chat.completions).

Both backends keep the same public signature for ``run_skill`` so the
shim entrypoints in :mod:`hermes_plugin.__init__` (and any future
callers) do not need to know which provider is wired up.
"""

from __future__ import annotations

import os
from typing import Any

_SUPPORTED_PROVIDERS = ("anthropic", "openai")


def _resolve_provider(explicit: str | None) -> str:
    provider = (explicit or os.environ.get("LLM_PROVIDER") or "anthropic").strip().lower()
    if provider not in _SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported LLM_PROVIDER {provider!r}; "
            f"expected one of {_SUPPORTED_PROVIDERS}."
        )
    return provider


def run_skill(*args: Any, provider: str | None = None, **kwargs: Any) -> dict:
    """Dispatch ``run_skill`` to the provider selected by ``LLM_PROVIDER``.

    Parameters mirror the underlying runtime's ``run_skill``. The optional
    ``provider`` keyword overrides the env var (mostly for tests).
    """
    selected = _resolve_provider(provider)
    if selected == "anthropic":
        from .runtime import run_skill as _impl
    else:  # selected == "openai"
        from .runtime_openai import run_skill as _impl
    return _impl(*args, **kwargs)


__all__ = ["run_skill"]
