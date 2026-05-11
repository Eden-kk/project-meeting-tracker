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
