"""Regenerate fixtures/sample_audio.wav as a ~10s bilingual (en+zh) sample.

Uses Microsoft Edge TTS (no API key) with one male English voice and one female
Mandarin voice so Stage 4 diarization has acoustically distinct speakers.

Idempotent at the content invariant level (duration band, channel/rate, expected
text), not byte-for-byte: Edge TTS streams from a remote endpoint and returned
bytes vary across calls.
"""

from __future__ import annotations

import asyncio
import io
import sys
import tempfile
from pathlib import Path

import edge_tts
import torch
import torchaudio

ROOT = Path(__file__).resolve().parents[1]
OUT_WAV = ROOT / "fixtures" / "sample_audio.wav"

LINES = [
    ("en-US-GuyNeural", "Welcome to the meeting. Today we will discuss the project timeline and the deployment schedule."),
    ("zh-CN-XiaoxiaoNeural", "大家好，今天我们来讨论一下项目的进度和下一步的计划。"),
]

TARGET_SR = 16000


async def _synthesize(voice: str, text: str) -> bytes:
    communicate = edge_tts.Communicate(text=text, voice=voice)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


def _load_mp3_to_mono16k(mp3_bytes: bytes) -> torch.Tensor:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as tmp:
        tmp.write(mp3_bytes)
        tmp.flush()
        wav, sr = torchaudio.load(tmp.name)
    if wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    if sr != TARGET_SR:
        wav = torchaudio.functional.resample(wav, sr, TARGET_SR)
    return wav


async def main() -> int:
    try:
        await edge_tts.list_voices()
    except Exception as exc:
        print(f"Edge TTS unreachable (network required): {exc}", file=sys.stderr)
        return 1

    chunks: list[torch.Tensor] = []
    for voice, text in LINES:
        mp3 = await _synthesize(voice, text)
        chunks.append(_load_mp3_to_mono16k(mp3))

    audio = torch.cat(chunks, dim=1)
    OUT_WAV.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(OUT_WAV), audio, TARGET_SR)
    dur = audio.shape[1] / TARGET_SR
    print(f"wrote {OUT_WAV} ({dur:.2f}s, mono 16k)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
