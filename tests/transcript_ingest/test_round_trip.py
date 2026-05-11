"""End-to-end contract tests across all input fixtures."""
from __future__ import annotations

from src.transcript_ingest import parse_transcript
from src.transcript_ingest.schema import validate


def test_vtt_matches_golden(vtt_fixture_path, expected_normalized):
    payload = vtt_fixture_path.read_text()
    expected = {
        **expected_normalized,
        "meeting_id": expected_normalized["meeting_id"],
    }
    result = parse_transcript(
        payload,
        filename_hint="sample.vtt",
        meeting_id=expected_normalized["meeting_id"],
    )
    assert result == expected


def test_srt_timestamps_match_vtt_ms(vtt_fixture_path, srt_fixture_path):
    vtt_result = parse_transcript(vtt_fixture_path.read_text(), filename_hint="sample.vtt", meeting_id="m_x")
    srt_result = parse_transcript(srt_fixture_path.read_text(), filename_hint="sample.srt", meeting_id="m_x")
    assert [(s["start_ms"], s["end_ms"]) for s in srt_result["segments"]] == [
        (s["start_ms"], s["end_ms"]) for s in vtt_result["segments"]
    ]
    assert [s["speaker_id"] for s in srt_result["segments"]] == [
        s["speaker_id"] for s in vtt_result["segments"]
    ]
    assert [s["speaker_name"] for s in srt_result["segments"]] == [
        s["speaker_name"] for s in vtt_result["segments"]
    ]


def test_txt_no_timestamps(txt_fixture_path):
    result = parse_transcript(txt_fixture_path.read_text(), filename_hint="sample.txt", meeting_id="m_t")
    assert all(s["start_ms"] is None and s["end_ms"] is None for s in result["segments"])
    assert [s["speaker_name"] for s in result["segments"]] == ["Alice", "Bob", "Alice", "Bob", "Carol", "Alice"]
    assert all(s["source_type"] == "pasted_transcript" for s in result["segments"])


def test_all_outputs_schema_valid(vtt_fixture_path, srt_fixture_path, txt_fixture_path):
    for path, hint in (
        (vtt_fixture_path, "sample.vtt"),
        (srt_fixture_path, "sample.srt"),
        (txt_fixture_path, "sample.txt"),
    ):
        result = parse_transcript(path.read_text(), filename_hint=hint, meeting_id="m_v")
        validate(result)
