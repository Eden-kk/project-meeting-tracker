"""HTTP ingest adapter — call shape, timeout selection, error propagation."""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from storage_router import ingest_adapter_http
from storage_router.api.app import create_app
from storage_router.models.contracts import NormalizedTranscript

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "expected_normalized.json"


def _fixture_payload() -> dict:
    with open(_FIXTURE) as f:
        return json.load(f)


def test_transcribe_voice_file_posts_to_voice_url(tmp_path, monkeypatch) -> None:
    """Voice path uses the voice ingest URL + voice timeout, multipart upload."""
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF....fakewav")

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["timeout"] = request.extensions.get("timeout")
        captured["body_len"] = len(request.content)
        return httpx.Response(200, json=_fixture_payload())

    transport = httpx.MockTransport(handler)
    real_post = httpx.post

    def fake_post(url, **kwargs):
        with httpx.Client(transport=transport) as c:
            return c.post(url, **kwargs)

    monkeypatch.setattr(httpx, "post", fake_post)
    result = ingest_adapter_http.transcribe_voice_file(audio)
    assert isinstance(result, NormalizedTranscript)
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/voice/transcribe")
    assert captured["url"].startswith("http://127.0.0.1:8021")
    # Per-route timeout: voice gets the long ceiling.
    assert captured["timeout"] == {
        "connect": 1800.0,
        "read": 1800.0,
        "write": 1800.0,
        "pool": 1800.0,
    }
    # Avoid lint warning that real_post is unused.
    _ = real_post


def test_parse_transcript_posts_to_transcript_url(monkeypatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content)
        captured["timeout"] = request.extensions.get("timeout")
        return httpx.Response(200, json=_fixture_payload())

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: httpx.Client(transport=transport).post(url, **kwargs),
    )
    result = ingest_adapter_http.parse_transcript(
        "Alice: hi", format="txt", source_type="pasted_transcript"
    )
    assert isinstance(result, NormalizedTranscript)
    assert captured["url"].endswith("/transcript/parse")
    assert captured["url"].startswith("http://127.0.0.1:8011")
    assert captured["json"] == {
        "text": "Alice: hi",
        "format": "txt",
        "source_type": "pasted_transcript",
    }
    # Transcript path gets the tight 30s ceiling.
    assert captured["timeout"] == {
        "connect": 30.0,
        "read": 30.0,
        "write": 30.0,
        "pool": 30.0,
    }


def test_parse_transcript_decodes_bytes(monkeypatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=_fixture_payload())

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: httpx.Client(transport=transport).post(url, **kwargs),
    )
    ingest_adapter_http.parse_transcript(b"hi there", format="txt")
    assert captured["json"]["text"] == "hi there"


def test_http_error_propagates(monkeypatch) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(503, json={"error": "downstream_unavailable"})
    )
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: httpx.Client(transport=transport).post(url, **kwargs),
    )
    with pytest.raises(httpx.HTTPStatusError):
        ingest_adapter_http.parse_transcript("hi", format="txt")


# ---------------------------------------------------------------------------
# CORS regex: anchored alternation must reject lookalike domains.
# ---------------------------------------------------------------------------

def _cors_regex() -> re.Pattern:
    app = create_app()
    for mw in app.user_middleware:
        # CORSMiddleware stores allow_origin_regex compiled in `kwargs`.
        if "allow_origin_regex" in mw.kwargs:
            return re.compile(mw.kwargs["allow_origin_regex"])
    raise AssertionError("CORS middleware not configured")


def test_cors_regex_accepts_real_tunnel_hosts() -> None:
    rx = _cors_regex()
    for origin in (
        "http://localhost",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "https://abc-123.trycloudflare.com",
        "https://abc-123.lhr.life",
        "https://abc.localhost.run",
    ):
        assert rx.match(origin), origin


def test_cors_regex_rejects_lookalike_hosts() -> None:
    rx = _cors_regex()
    for origin in (
        "https://evil-lhr.life",
        "https://lhr.life.evil.com",
        "https://localhost.run.evil.com",
        "http://localhost.evil.com",
        "https://abctrycloudflarexcom",
        "https://lhr.life",  # bare domain, no subdomain
    ):
        assert not rx.match(origin), origin
