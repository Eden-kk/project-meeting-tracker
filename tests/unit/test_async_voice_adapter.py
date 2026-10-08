"""Offline transport tests: no database, model calls, or credentials required."""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from storage_router import ingest_adapter_http as adapter


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "clip.webm"
    path.write_bytes(b"synthetic-test-audio")
    return path


def mock_client(monkeypatch, handler):
    real_client = httpx.AsyncClient
    clients = []

    def factory(**kwargs):
        client = real_client(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(adapter.httpx, "AsyncClient", factory)
    return clients


@pytest.mark.asyncio
async def test_success_and_redirect_polling(audio, monkeypatch):
    requests = []
    payload = json.loads((Path(__file__).parents[2] / "fixtures/expected_normalized.json").read_text())

    async def handler(request):
        requests.append(request)
        if request.method == "POST":
            assert b'name="num_speakers"' in request.content
            assert b"synthetic-test-audio" in request.content
            return httpx.Response(303, headers={"location": "/result"})
        return httpx.Response(200, json=payload)

    clients = mock_client(monkeypatch, handler)
    result = await adapter.transcribe_voice_file_async(audio, num_speakers=2)
    assert result.model_dump(mode="json") == adapter.NormalizedTranscript.model_validate(payload).model_dump(mode="json")
    assert [request.method for request in requests] == ["POST", "GET"]
    assert clients[0].is_closed


@pytest.mark.asyncio
async def test_cancellation_closes_request_and_propagates(audio, monkeypatch):
    started, stopped = asyncio.Event(), asyncio.Event()

    async def handler(request):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    clients = mock_client(monkeypatch, handler)
    task = asyncio.create_task(adapter.transcribe_voice_file_async(audio))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
    assert clients[0].is_closed


@pytest.mark.asyncio
async def test_total_deadline_stops_wait_without_retry(audio, monkeypatch):
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.Event().wait()

    clients = mock_client(monkeypatch, handler)
    monkeypatch.setattr(adapter.settings, "voice_ingest_timeout_seconds", 0.02)
    with pytest.raises(TimeoutError):
        await adapter.transcribe_voice_file_async(audio)
    assert len(calls) == 1
    assert clients[0].is_closed


@pytest.mark.asyncio
async def test_http_failure_is_not_retried(audio, monkeypatch):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(503)

    clients = mock_client(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.transcribe_voice_file_async(audio)
    assert len(calls) == 1
    assert clients[0].is_closed


@pytest.mark.asyncio
async def test_deadline_includes_redirect_polling(audio, monkeypatch):
    methods = []

    async def handler(request):
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(303, headers={"location": "/pending-result"})
        await asyncio.Event().wait()

    clients = mock_client(monkeypatch, handler)
    monkeypatch.setattr(adapter.settings, "voice_ingest_timeout_seconds", 0.1)
    with pytest.raises(TimeoutError):
        await adapter.transcribe_voice_file_async(audio)
    assert methods == ["POST", "GET"]
    assert clients[0].is_closed
