"""Errors raised by the hermes-plugin client and tool layer."""

from __future__ import annotations


class ToolError(Exception):
    """Raised on recoverable failures the model can react to.

    Carries an HTTP-style ``status_code`` (e.g. 404, 422, 503), a short
    ``code`` token, and a human-readable ``message``. The runtime
    surfaces this back to the model as a ``tool_result`` with
    ``is_error=True`` so the loop can continue.
    """

    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message

    def to_payload(self) -> dict:
        return {
            "status_code": self.status_code,
            "code": self.code,
            "message": self.message,
        }


class StorageUnavailable(Exception):
    """Raised when storage-router is unreachable or returned 5xx/garbage.

    The tool layer wraps this as a ``ToolError(status_code=503,
    code='storage_unavailable')`` so callers see a single error type.
    """


class HermesPluginError(Exception):
    """Base class for hermes_plugin runtime errors that escape the tool loop."""


class ChunkedExtractionError(HermesPluginError):
    """Raised when a per-chunk Claude call fails mid-run.

    Carries partial-progress counts so callers (and the storage-router
    seam) can surface "we got K cards across N chunks before bailing"
    instead of pretending no progress was made.
    """

    def __init__(
        self,
        *,
        chunks_processed: int,
        cards_created: int,
        cause: BaseException,
    ) -> None:
        self.chunks_processed = chunks_processed
        self.cards_created = cards_created
        self.cause = cause
        super().__init__(
            f"Chunked extraction failed after {chunks_processed} chunk(s) "
            f"and {cards_created} card(s): {cause!r}"
        )
