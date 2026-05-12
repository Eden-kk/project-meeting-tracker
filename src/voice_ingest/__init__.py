# Lazy public surface: import on demand so that importing a sub-module
# (e.g. live_diarize) from a host that doesn't have faster_whisper
# installed (storage-router wave8 venv) doesn't blow up at package import
# time.  Callers that need transcribe_voice_file do
#   from voice_ingest.transcribe import transcribe_voice_file
# directly, or use the helper below which defers the heavy import.


def transcribe_voice_file(path, **kw):  # type: ignore[override]
    from .transcribe import transcribe_voice_file as _fn  # noqa: PLC0415

    return _fn(path, **kw)


__all__ = ["transcribe_voice_file"]
