"""Wave 8.2 — assert Whisper is invoked with code-switching-friendly params.

This is a config-level test: it patches the underlying `WhisperModel` so we
can inspect the keyword arguments passed to `model.transcribe(...)` without
needing GPU or a 3 GB model download. The semantic assertion ("zh-en
code-switching transcribes correctly end-to-end") is covered by the existing
`test_round_trip` in `test_voice_ingest.py`, which uses a real bilingual
fixture.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.voice_ingest import config, transcribe


def test_default_whisper_model_is_large_v3():
    # The default in voice_ingest.config must be `large-v3` so deploys
    # without an explicit override get the code-switching-capable model.
    assert config.WHISPER_MODEL == "large-v3" or "WHISPER_MODEL" in __import__("os").environ, (
        "config.WHISPER_MODEL default must be 'large-v3' (got "
        f"{config.WHISPER_MODEL!r}); only acceptable override is the env var."
    )


def test_transcribe_passes_condition_on_previous_text(tmp_path):
    # Patch the lazy `_get_model()` so we never instantiate a real WhisperModel.
    fake_model = MagicMock()
    # `model.transcribe(...)` returns `(segments_iter, info)`.
    fake_model.transcribe.return_value = (iter([]), MagicMock())

    fake_path = tmp_path / "stub.wav"
    fake_path.write_bytes(b"\x00")  # contents irrelevant; we mock the model

    with patch.object(transcribe, "_get_model", return_value=fake_model):
        # `assign_speakers` will be called with an empty segments list — fine.
        transcribe.transcribe_voice_file(str(fake_path), meeting_id="m_unit")

    # Verify the keyword arguments that gate code-switching behaviour.
    fake_model.transcribe.assert_called_once()
    _args, kwargs = fake_model.transcribe.call_args
    assert kwargs.get("condition_on_previous_text") is True, (
        "Whisper must be called with condition_on_previous_text=True so the "
        "decoder primes itself on the prior chunk's tokens — required for "
        "mid-utterance Chinese↔English code-switching."
    )
    assert kwargs.get("language") is None, (
        "language must remain None (auto-detect) for code-switching."
    )
