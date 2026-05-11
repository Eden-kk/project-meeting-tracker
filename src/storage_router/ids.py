"""ID generator: <prefix>_<base32-uuid4-lowercase>."""
from __future__ import annotations

import base64
import uuid


def new_id(prefix: str) -> str:
    raw = uuid.uuid4().bytes
    body = base64.b32encode(raw).decode("ascii").rstrip("=").lower()
    return f"{prefix}_{body}"
