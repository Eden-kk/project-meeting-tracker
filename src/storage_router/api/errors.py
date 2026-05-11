"""RFC-7807-ish error envelope helpers."""
from __future__ import annotations

from fastapi.responses import JSONResponse


def bad_request(code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=400, content={"error": {"code": code, "message": message}}
    )
