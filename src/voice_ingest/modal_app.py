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
            # Fixed, image-baked cache locations so weights are present on
            # every cold container (no per-request 3GB re-download that blew
            # past Modal's 150s web-request limit -> HTTP 303).
            "MODEL_CACHE_DIR": "/models",
            "HF_HOME": "/models/hf",
            # HF_TOKEN is injected at runtime via Modal Secret 'hf-token-tracker'.
        }
    )
)


def _download_models() -> None:
    """Bake whisper + pyannote weights into the image at build time.

    Runs on CPU during the image build (with HF_TOKEN from the secret) so a
    cold GPU container only has to LOAD weights from local disk, not download
    ~3GB over the network inside a 150s-bounded web request.
    """
    import os
    from faster_whisper import WhisperModel

    WhisperModel(
        "Systran/faster-whisper-large-v3",
        device="cpu",
        compute_type="int8",
        download_root="/models",
    )
    from pyannote.audio import Pipeline

    Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=os.environ["HF_TOKEN"],
    )


image = (
    image
    .run_function(
        _download_models,
        secrets=[modal.Secret.from_name("hf-token-tracker")],
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
    # whisper-large-v3 + pyannote on a full 30-60 min meeting exceeds 10 min
    # of GPU compute; the old 600s ceiling timed out (HTTP 500) once
    # diarization actually started running. 40 min gives ample headroom.
    # The storage-router client timeout (config.voice_ingest_timeout_seconds)
    # is set higher so the client always outlasts the function.
    timeout=2400,
    scaledown_window=300,
    max_containers=2,
    secrets=[modal.Secret.from_name("hf-token-tracker")],
)
@modal.concurrent(max_inputs=4)
@modal.asgi_app()
def fastapi():
    """Mount the voice_ingest FastAPI app under Modal's HTTP endpoint.

    This function body runs ONCE per container at startup (Modal calls it to
    obtain the ASGI app), so we preload whisper + pyannote here — at
    container init, which is bounded by the function `timeout` (600s), NOT
    the 150s web-request limit. With weights baked into the image, the load
    is local-disk only (~tens of seconds), the container goes warm, and
    every /voice/transcribe is fast with diarization running. Previously
    models lazy-loaded inside the first request, which downloaded ~3GB and
    blew past the 150s limit (HTTP 303) before diarization could ever run.
    Keeping the function name `fastapi` preserves the deployed URL.
    """
    import sys

    sys.path.insert(0, "/app")
    from voice_ingest.transcribe import _get_model
    from voice_ingest.diarize import _get_pipeline

    _get_model()
    try:
        _get_pipeline()
    except Exception as exc:  # noqa: BLE001 — don't block ASR if diarize load fails
        print(f"pyannote preload failed: {type(exc).__name__}: {exc}")

    from voice_ingest.api import app as fastapi_app  # noqa: WPS433

    return fastapi_app
