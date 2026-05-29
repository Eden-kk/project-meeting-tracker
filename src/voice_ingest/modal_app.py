"""Modal deployment of the voice_ingest FastAPI service.

Wraps src/voice_ingest/api.py and pins it to a single GPU container so
faster-whisper + pyannote run on an A10G.

Deploy from the repo root:
    modal deploy src/voice_ingest/modal_app.py

URL after deploy: https://hao-ai-lab--voice-ingest-fastapi.modal.run

Health:     GET  /healthz
Transcribe: POST /voice/transcribe (multipart: audio=<file>, meeting_id=<str>)

Diarization
-----------
pyannote needs ``HF_TOKEN`` at runtime. We inject it via the Modal
Secret ``hf-token-tracker`` (key inside the secret MUST be ``HF_TOKEN``
to match ``src/voice_ingest/config.py``). When the env var is missing,
``voice_ingest.diarize.assign_speakers`` falls back to single-speaker
(every segment labelled ``speaker_1``).
"""
from __future__ import annotations

from pathlib import Path

import modal

# Resolve repo root relative to this file: src/voice_ingest/modal_app.py.
# Only used at deploy time for `.add_local_dir` — when this module is
# re-imported inside the container from /root/modal_app.py the resolution
# degrades to "/" which is harmless (the local-dir mounts were already
# baked into the image at deploy).
_here = Path(__file__).resolve()
REPO_ROOT = _here.parents[2] if len(_here.parents) >= 3 else Path("/")

# CUDA-12 cuDNN runtime base — CTranslate2's GPU mode needs cuDNN 9 / CUDA 12.
image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04",
        add_python="3.12",
    )
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install(
        "fastapi==0.115.0",
        "uvicorn==0.30.6",
        "python-multipart==0.0.10",
        "pydantic==2.9.2",
        "jsonschema==4.23.0",
        "faster-whisper==1.0.3",
        "requests>=2.31",  # transitive of faster_whisper.utils
        # Diarization stack — requires HF_TOKEN + license acceptance for
        # pyannote/speaker-diarization-3.1 on HuggingFace.
        "torch==2.4.1",
        "torchaudio==2.4.1",
        "pyannote.audio==3.3.2",
        # pyannote 3.3.2 calls hf_hub_download(use_auth_token=...), which
        # huggingface_hub>=1.0 removed (renamed to `token`). Unpinned, pip
        # floated to hub 1.17 and EVERY diarization call failed with
        # "unexpected keyword argument 'use_auth_token'" -> silent single-
        # speaker fallback. Pin to the last 0.x line that still accepts it.
        "huggingface_hub==0.25.2",
        # pyannote pulls matplotlib (via pyannote.metrics) at pipeline-load
        # time; it isn't auto-installed in this slim image, so add it
        # explicitly or from_pretrained dies with ModuleNotFoundError.
        "matplotlib",
    )
    .env(
        {
            # Whisper-large-v3 from HF; CTranslate2 caches the model in /root.
            "WHISPER_MODEL": "Systran/faster-whisper-large-v3",
            "WHISPER_DEVICE": "cuda",
            "WHISPER_COMPUTE_TYPE": "float16",
            "MAX_UPLOAD_BYTES": "209715200",
            "PYANNOTE_PIPELINE": "pyannote/speaker-diarization-3.1",
            # HF_TOKEN is injected at runtime via Modal Secret 'hf-token-tracker'.
        }
    )
    .add_local_dir(
        str(REPO_ROOT / "src" / "voice_ingest"),
        "/app/voice_ingest",
    )
    # voice_ingest.config sets WORKTREE_ROOT = parents[2] of voice_ingest/__init__.py.
    # When the package lives at /app/voice_ingest, parents[2] = '/'. So `referencing`-loaded
    # schemas resolve via /schemas/*.json. Mount the schemas directory there.
    .add_local_dir(
        str(REPO_ROOT / "schemas"),
        "/schemas",
    )
)

app = modal.App("voice-ingest")


@app.function(
    image=image,
    gpu="A10G",
    timeout=600,
    scaledown_window=300,
    max_containers=2,
    secrets=[modal.Secret.from_name("hf-token-tracker")],
)
@modal.concurrent(max_inputs=4)
@modal.asgi_app()
def fastapi():
    """Mount the voice_ingest FastAPI app under Modal's HTTP endpoint."""
    import sys

    sys.path.insert(0, "/app")
    from voice_ingest.api import app as fastapi_app  # noqa: WPS433

    return fastapi_app
