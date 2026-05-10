from fastapi.testclient import TestClient

from src.voice_ingest import schema
from src.voice_ingest.api import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "model" in body


def test_transcribe_round_trip(audio_fixture_path):
    with open(audio_fixture_path, "rb") as f:
        r = client.post(
            "/voice/transcribe",
            files={"audio": ("sample_audio.wav", f, "audio/wav")},
            data={"meeting_id": "m_api_test"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meeting_id"] == "m_api_test"
    schema.validate(body)
