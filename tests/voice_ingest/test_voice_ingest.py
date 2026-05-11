import difflib
import re

from src.voice_ingest import schema, transcribe_voice_file

_ASCII_PUNCT = ".,!?;:'\"()-"
_CJK_PUNCT = "，。！？；：「」『』（）、"
_CJK_RE = re.compile(r"[一-鿿]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def _normalize(text: str) -> str:
    text = text.lower()
    for ch in _ASCII_PUNCT + _CJK_PUNCT:
        text = text.replace(ch, "")
    return re.sub(r"\s+", " ", text).strip()


def _is_zh(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def test_round_trip(audio_fixture_path, expected_text):
    result = transcribe_voice_file(str(audio_fixture_path), meeting_id="m_fixture001")
    schema.validate(result)
    assert result["meeting_id"] == "m_fixture001"

    segs = result["segments"]
    actual_en = " ".join(s["text"] for s in segs if not _is_zh(s["text"]))
    actual_zh = " ".join(s["text"] for s in segs if _is_zh(s["text"]))

    expected_lines = [ln for ln in expected_text.splitlines() if ln.strip()]
    expected_en = next((ln for ln in expected_lines if not _is_zh(ln)), "")
    expected_zh = next((ln for ln in expected_lines if _is_zh(ln)), "")

    en_ratio = difflib.SequenceMatcher(None, _normalize(actual_en), _normalize(expected_en)).ratio()
    zh_ratio = difflib.SequenceMatcher(None, _normalize(actual_zh), _normalize(expected_zh)).ratio()

    msg = (
        f"en_ratio={en_ratio:.3f} zh_ratio={zh_ratio:.3f}; "
        f"actual_en={actual_en!r} actual_zh={actual_zh!r}; "
        f"if low, retry with WHISPER_MODEL=large-v3 WHISPER_DEVICE=cuda WHISPER_COMPUTE_TYPE=float16"
    )
    assert en_ratio >= 0.85, msg
    assert zh_ratio >= 0.55, msg

    assert any(_LATIN_RE.search(s["text"]) for s in segs), "no English segment"
    assert any(_CJK_RE.search(s["text"]) for s in segs), "no Chinese segment"
