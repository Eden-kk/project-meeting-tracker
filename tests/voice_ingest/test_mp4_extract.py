"""Verify the mp4 → wav pre-extraction step in transcribe_voice_file.

The full transcribe pipeline pulls a Whisper model into memory, which is
expensive in CI. We mock _get_model + assign_speakers and only assert
that ffmpeg is invoked with --vn / -ar 16000 when the input has a video
suffix, and that the temporary wav is cleaned up after the call.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# All voice_ingest tests presume the heavy ML stack (faster-whisper +
# pyannote) is installed; skip cleanly otherwise so unit-test runs on a
# slim env still go green.
pytest.importorskip("faster_whisper")

from src.voice_ingest import transcribe as transcribe_mod  # noqa: E402


class _FakeWhisperSegment:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = -0.2


def _fake_model() -> MagicMock:
    m = MagicMock()
    m.transcribe.return_value = (
        iter([_FakeWhisperSegment(0.0, 1.0, "hello")]),
        MagicMock(),
    )
    return m


def test_mp4_input_triggers_ffmpeg_extraction(tmp_path: Path) -> None:
    fake_mp4 = tmp_path / "meeting.mp4"
    fake_mp4.write_bytes(b"\x00")  # contents irrelevant; we mock ffmpeg

    captured: dict = {}

    def _fake_ffmpeg_run(cmd, capture_output=True):
        # First arg "ffmpeg", later args include -i <input>, -vn, -ar 16000, <output>
        captured["cmd"] = cmd
        out_path = cmd[-1]
        Path(out_path).write_bytes(b"RIFFfakewavdata")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    with patch.object(transcribe_mod, "_get_model", return_value=_fake_model()), \
         patch.object(transcribe_mod, "assign_speakers", side_effect=lambda p, segs: segs), \
         patch.object(transcribe_mod.subprocess, "run", side_effect=_fake_ffmpeg_run), \
         patch.object(transcribe_mod.shutil, "which", return_value="/usr/bin/ffmpeg"):
        result = transcribe_mod.transcribe_voice_file(str(fake_mp4), meeting_id="m_test01")

    assert result["meeting_id"] == "m_test01"
    assert len(result["segments"]) == 1

    cmd = captured["cmd"]
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd                  # drop video stream
    assert "-ac" in cmd and "1" in cmd   # mono
    assert "-ar" in cmd and "16000" in cmd  # 16 kHz
    assert str(fake_mp4) in cmd          # input was the mp4
    extracted = cmd[-1]
    assert extracted.endswith(".wav")
    assert not Path(extracted).exists(), "extracted wav should be cleaned up after transcribe"


def test_wav_input_skips_ffmpeg(tmp_path: Path) -> None:
    fake_wav = tmp_path / "meeting.wav"
    fake_wav.write_bytes(b"RIFFfakewavdata")

    with patch.object(transcribe_mod, "_get_model", return_value=_fake_model()), \
         patch.object(transcribe_mod, "assign_speakers", side_effect=lambda p, segs: segs), \
         patch.object(transcribe_mod.subprocess, "run") as ffmpeg_mock:
        transcribe_mod.transcribe_voice_file(str(fake_wav), meeting_id="m_test02")

    ffmpeg_mock.assert_not_called()


def test_mp4_input_with_no_ffmpeg_raises(tmp_path: Path) -> None:
    fake_mp4 = tmp_path / "meeting.mp4"
    fake_mp4.write_bytes(b"\x00")

    with patch.object(transcribe_mod, "_get_model", return_value=_fake_model()), \
         patch.object(transcribe_mod.shutil, "which", return_value=None):
        try:
            transcribe_mod.transcribe_voice_file(str(fake_mp4), meeting_id="m_test03")
        except RuntimeError as e:
            assert "ffmpeg" in str(e).lower()
        else:
            raise AssertionError("expected RuntimeError when ffmpeg missing")
