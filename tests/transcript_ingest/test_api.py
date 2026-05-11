from fastapi.testclient import TestClient

from src.transcript_ingest.api import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_file_upload(vtt_fixture_path):
    with vtt_fixture_path.open("rb") as fh:
        r = client.post(
            "/transcript/parse",
            files={"file": ("sample.vtt", fh, "text/vtt")},
            data={"meeting_id": "m_api1"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meeting_id"] == "m_api1"
    assert len(body["segments"]) == 6
    assert body["segments"][0]["source_type"] == "transcript_file"


def test_text_form():
    r = client.post(
        "/transcript/parse",
        data={"text": "Alice: hello\nBob: hi", "meeting_id": "m_api2"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meeting_id"] == "m_api2"
    assert len(body["segments"]) == 2
    assert body["segments"][0]["source_type"] == "pasted_transcript"
    assert body["segments"][0]["start_ms"] is None


def test_missing_input_returns_400():
    r = client.post("/transcript/parse", data={})
    assert r.status_code == 400
