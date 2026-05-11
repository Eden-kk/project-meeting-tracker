from src.transcript_ingest.detect import detect_format


def test_vtt_content_sniff():
    assert detect_format("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhi") == "vtt"


def test_extension_wins_case_insensitive():
    # Even though the body looks like txt, an SRT extension hint trumps content sniff.
    assert detect_format("Alice: hi", filename_hint="meeting.SRT") == "srt"


def test_plain_speaker_txt():
    assert detect_format("Alice: hi\nBob: hey") == "txt"


def test_json_dict():
    assert detect_format('{"meeting_id": "m_1", "segments": []}') == "json"


def test_srt_grammar():
    payload = (
        "1\n"
        "00:00:00,000 --> 00:00:05,200\n"
        "Alice: hi\n\n"
        "2\n"
        "00:00:05,500 --> 00:00:11,800\n"
        "Bob: hey\n"
    )
    assert detect_format(payload) == "srt"


def test_bytes_input_vtt():
    assert detect_format(b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhi") == "vtt"
