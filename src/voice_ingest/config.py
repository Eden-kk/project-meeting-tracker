"""Env-var driven configuration for the voice-ingest worktree.

All configuration is read at import time from environment variables. Defaults
are chosen so the package is usable on a CPU-only laptop without any setup
beyond `pip install -r requirements.txt`.
"""

from __future__ import annotations

import os
from pathlib import Path


def _resolve_device(raw: str) -> str:
    if raw != "auto":
        return raw
    try:
        import torch  # local import; avoids hard import at config load if torch missing

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


_WORKTREE_ROOT = Path(__file__).resolve().parents[2]

WHISPER_MODEL: str = os.environ.get("WHISPER_MODEL", "medium")
WHISPER_DEVICE: str = _resolve_device(os.environ.get("WHISPER_DEVICE", "auto"))
WHISPER_COMPUTE_TYPE: str = os.environ.get(
    "WHISPER_COMPUTE_TYPE",
    "float16" if WHISPER_DEVICE == "cuda" else "int8",
)

HF_TOKEN: str | None = os.environ.get("HF_TOKEN") or None
PYANNOTE_PIPELINE: str = os.environ.get(
    "PYANNOTE_PIPELINE", "pyannote/speaker-diarization-3.1"
)

MODEL_CACHE_DIR: Path = Path(
    os.environ.get("MODEL_CACHE_DIR", str(_WORKTREE_ROOT / "models"))
)

MAX_UPLOAD_BYTES: int = int(os.environ.get("MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))

WORKTREE_ROOT: Path = _WORKTREE_ROOT
