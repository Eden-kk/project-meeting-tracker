import json
from pathlib import Path

from src.transcript_ingest.parsers.vtt import parse_vtt
from src.transcript_ingest.parsers.srt import parse_srt
from src.transcript_ingest.parsers.txt import parse_txt
from src.transcript_ingest.parsers.json_parser import parse_json


_FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures"

_EXPECTED_MS = [
    (0, 5200),
    (5500, 11800),
    (12000, 15400),
    (15600, 19200),
    (19500, 25800),
    (26000, 30400),
]
_EXPECTED_SPEAKERS = ["Alice", "Bob", "Alice", "Bob", "Carol", "Alice"]
_EXPECTED_SPEAKER_IDS = [
    "speaker_1",
    "speaker_2",
    "speaker_1",
    "speaker_2",
    "speaker_3",
    "speaker_1",
]


def test_parse_vtt_matches_expected_ms_and_speakers():
    segs = parse_vtt((_FIXTURES / "sample_transcript.vtt").read_text())
    assert len(segs) == 6
    assert [(s["start_ms"], s["end_ms"]) for s in segs] == _EXPECTED_MS
    assert [s["speaker_name"] for s in segs] == _EXPECTED_SPEAKERS
    assert [s["speaker_id"] for s in segs] == _EXPECTED_SPEAKER_IDS
    assert all(s["is_final"] is True for s in segs)
    assert all(s["confidence"] is None for s in segs)


def test_parse_srt_matches_vtt_ms_and_speakers():
    segs = parse_srt((_FIXTURES / "sample_transcript.srt").read_text())
    assert len(segs) == 6
    assert [(s["start_ms"], s["end_ms"]) for s in segs] == _EXPECTED_MS
    assert [s["speaker_name"] for s in segs] == _EXPECTED_SPEAKERS
    assert [s["speaker_id"] for s in segs] == _EXPECTED_SPEAKER_IDS


def test_parse_txt_no_timestamps_speakers_extracted():
    segs = parse_txt((_FIXTURES / "sample_transcript.txt").read_text())
    assert len(segs) == 6
    assert all(s["start_ms"] is None and s["end_ms"] is None for s in segs)
    assert [s["speaker_name"] for s in segs] == _EXPECTED_SPEAKERS
    assert [s["speaker_id"] for s in segs] == _EXPECTED_SPEAKER_IDS


def test_parse_vtt_colon_prefix_speaker():
    """VTT cues using 'Name: text' (Zoom-style) should extract speaker_name."""
    vtt_content = (
        "WEBVTT\n"
        "\n"
        "00:00:00.000 --> 00:00:05.000\n"
        "Steven Ford: hello world\n"
        "\n"
        "00:00:05.500 --> 00:00:09.000\n"
        "Steven Ford: Okay.\n"
        "\n"
        "00:00:09.500 --> 00:00:14.000\n"
        "so the ratio is 3:1 here\n"
    )
    segs = parse_vtt(vtt_content)
    assert len(segs) == 3
    assert segs[0]["speaker_name"] == "Steven Ford"
    assert segs[0]["text"] == "hello world"
    assert segs[0]["speaker_id"] == "speaker_1"
    assert segs[1]["speaker_name"] == "Steven Ford"
    assert segs[1]["text"] == "Okay."
    assert segs[1]["speaker_id"] == "speaker_1"
    # Line with embedded colon but no leading capitalized name prefix
    assert segs[2]["speaker_name"] is None
    assert segs[2]["text"] == "so the ratio is 3:1 here"
    assert segs[2]["speaker_id"] is None


def test_parse_json_passthrough():
    expected = json.loads((_FIXTURES / "expected_normalized.json").read_text())
    segs = parse_json(json.dumps(expected))
    assert len(segs) == 6
    assert [s["start_ms"] for s in segs] == [m[0] for m in _EXPECTED_MS]
    assert [s["speaker_name"] for s in segs] == _EXPECTED_SPEAKERS

    bare = parse_json(json.dumps(expected["segments"]))
    assert len(bare) == 6
    assert bare[0]["text"] == expected["segments"][0]["text"]
