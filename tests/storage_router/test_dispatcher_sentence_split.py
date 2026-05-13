"""Batch ingest path: per-sentence rows via `SentenceBuffer` (parity with live).

The live path (`api/live_route.receive_chunk`) feeds whisper segments through
a `SentenceBuffer` so each persisted `speaker_segments` row holds exactly
one sentence. Until this fix, the batch path
(`dispatcher.process_artifact` → mp4 / audio-file imports) wrote whatever
whisper-style segments came back from voice-ingest directly, producing
5-30 s rows that contained multiple sentences and broke downstream search /
quote extraction. This test pins the buffer wiring on the batch path.

DB note: per `conftest._clean_db`, this suite truncates known tables on a
live Postgres. The DB is unreachable from the CLI sandbox, so this file is
written to pass `--collect-only`; execution is deferred to the pod. We
also avoid touching the database in-test by capturing the
`NormalizedTranscript` that `persist_transcript_segments` would receive and
asserting against its segment list — this means the test does not require
the artifact/meeting rows to actually exist for the per-sentence assertion
itself.
"""

from __future__ import annotations

from typing import Any

import pytest

from storage_router import dispatcher
from storage_router.models.contracts import (
    NormalizedTranscript,
    SourceType,
    SpeakerSegment,
)


def _whisper_like_transcript(meeting_id: str = "__placeholder__") -> NormalizedTranscript:
    """Two long-form whisper-style chunks, each with multiple sentences.

    Mirrors what voice-ingest returns from `transcribe_voice_file_async` for
    a freshly uploaded mp4: ~10-20 s segments containing 2-3 sentences each.
    Speaker turns are simulated by changing `speaker_id` between the chunks
    so the per-speaker grouping is exercised too.
    """
    return NormalizedTranscript(
        meeting_id=meeting_id,
        segments=[
            SpeakerSegment(
                segment_id="seg-1",
                speaker_id="speaker_1",
                speaker_name=None,
                start_ms=0,
                end_ms=8000,
                text="Hello there. How are you doing today?",
                confidence=0.91,
                source_type=SourceType.voice_file,
                is_final=True,
            ),
            SpeakerSegment(
                segment_id="seg-2",
                speaker_id="speaker_2",
                speaker_name=None,
                start_ms=8000,
                end_ms=20000,
                text="I'm doing well, thanks. The project is on track! Let's continue.",
                confidence=0.88,
                source_type=SourceType.voice_file,
                is_final=True,
            ),
        ],
    )


def test_split_helper_emits_one_segment_per_sentence() -> None:
    """Pure-function check on `_split_transcript_per_sentence` — no DB.

    Two whisper chunks (2 sentences, then 3 sentences). After the split, the
    transcript MUST have five segments, each ending on terminal punctuation,
    and the speaker_id of each sentence MUST match the chunk it came from
    (no stitching across the speaker turn).
    """
    raw = _whisper_like_transcript()
    out = dispatcher._split_transcript_per_sentence(raw)

    texts = [s.text for s in out.segments]
    assert texts == [
        "Hello there.",
        "How are you doing today?",
        "I'm doing well, thanks.",
        "The project is on track!",
        "Let's continue.",
    ]
    # Every emitted sentence keeps its source-chunk's speaker label.
    speakers = [s.speaker_id for s in out.segments]
    assert speakers == [
        "speaker_1",
        "speaker_1",
        "speaker_2",
        "speaker_2",
        "speaker_2",
    ]
    # Terminal punctuation is preserved on each row.
    for s in out.segments:
        assert s.text[-1] in {".", "!", "?"}
    # source_type / is_final / confidence inherit from the parent chunk.
    assert {s.source_type for s in out.segments} == {SourceType.voice_file}
    assert all(s.is_final for s in out.segments)


def test_split_helper_handles_empty_transcript() -> None:
    """Empty input → empty output; no exceptions, no buffer state leaks."""
    empty = NormalizedTranscript(meeting_id="m_test", segments=[])
    out = dispatcher._split_transcript_per_sentence(empty)
    assert out.segments == []


def test_split_helper_force_flushes_trailing_fragment() -> None:
    """A whisper chunk that lacks terminal punctuation (the file ends mid-
    word) must still produce a row — `SentenceBuffer.flush()` emits the
    held fragment so audio with no final period isn't silently dropped."""
    raw = NormalizedTranscript(
        meeting_id="m_test",
        segments=[
            SpeakerSegment(
                segment_id="seg-1",
                speaker_id="speaker_1",
                speaker_name=None,
                start_ms=0,
                end_ms=4000,
                text="this audio ends mid sentence with no terminal punctuation",
                confidence=None,
                source_type=SourceType.voice_file,
                is_final=True,
            ),
        ],
    )
    out = dispatcher._split_transcript_per_sentence(raw)
    assert len(out.segments) == 1
    assert (
        out.segments[0].text
        == "this audio ends mid sentence with no terminal punctuation"
    )
    assert out.segments[0].speaker_id == "speaker_1"


def test_process_artifact_persists_per_sentence_rows(monkeypatch) -> None:
    """End-to-end on the batch path with the DB writes captured in-memory.

    We patch `transcribe_voice_file` to return a synthetic multi-sentence
    transcript and `storage.persist_transcript_segments` to capture the
    transcript handed to it. The captured transcript MUST be the per-
    sentence shape — five segments, terminal punctuation, speaker labels
    intact — which is the contract this fix establishes.

    All other dispatcher dependencies (DB session, state-machine updates,
    auto-finalize) are stubbed so the test runs without Postgres.
    """
    raw_transcript = _whisper_like_transcript()
    captured: dict[str, Any] = {}

    # 1) Replace the voice-ingest call with our synthetic whisper output.
    monkeypatch.setattr(
        dispatcher, "transcribe_voice_file", lambda _p: raw_transcript
    )
    # 2) Capture what the dispatcher actually tries to persist.
    def _capture(_session, meeting_id: str, transcript: NormalizedTranscript) -> None:
        captured["meeting_id"] = meeting_id
        captured["transcript"] = transcript

    monkeypatch.setattr(
        "storage_router.storage.persist_transcript_segments", _capture
    )
    # 3) Neutralise the rest of the dispatcher's DB-touching surface.
    monkeypatch.setattr(
        "storage_router.storage.update_processing_status",
        lambda *_a, **_kw: None,
    )
    monkeypatch.setattr(
        "storage_router.storage.update_meeting_status",
        lambda *_a, **_kw: None,
    )
    # 4) Don't fire Hermes finalize in this unit test.
    monkeypatch.setattr(
        "storage_router.hermes_runtime.auto_finalize_meeting",
        lambda _mid: None,
    )

    # 5) Stub `SessionLocal` so the `with SessionLocal() as session:` block
    #    yields a fake session that produces our seeded artifact + meeting.
    class _FakeArtifact:
        source_type = "voice_file"
        raw_file_url = "file:///tmp/fake.mp4"
        raw_text = None
        processing_status = "received"

    class _FakeMeeting:
        id = "m_unit_test"
        artifact_id = "art_unit_test"
        status = "processing"

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def get(self, model, _id):
            from storage_router.models.db import (
                ConversationArtifactRow,
                MeetingRow,
            )

            if model is ConversationArtifactRow:
                return _FakeArtifact()
            if model is MeetingRow:
                return _FakeMeeting()
            return None

        def execute(self, _stmt):
            class _Result:
                def scalar_one_or_none(self_inner):
                    return _FakeMeeting()

            return _Result()

        def commit(self):
            return None

        def rollback(self):
            return None

    monkeypatch.setattr(dispatcher, "SessionLocal", _FakeSession)

    dispatcher.process_artifact("art_unit_test")

    assert "transcript" in captured, "persist_transcript_segments was not called"
    segments = captured["transcript"].segments
    assert [s.text for s in segments] == [
        "Hello there.",
        "How are you doing today?",
        "I'm doing well, thanks.",
        "The project is on track!",
        "Let's continue.",
    ]
    # Speaker labels survive the split.
    assert [s.speaker_id for s in segments] == [
        "speaker_1",
        "speaker_1",
        "speaker_2",
        "speaker_2",
        "speaker_2",
    ]
    # Terminal punctuation preserved on every sentence-row.
    assert all(s.text[-1] in {".", "!", "?"} for s in segments)


@pytest.mark.skip(
    reason=(
        "Reserved for live Postgres run on the pod: drive the full HTTP "
        "import route and read `speaker_segments` rows back via "
        "`/api/meetings/{id}/transcript`. The CLI sandbox has no DB, so "
        "this case is left out of `--collect-only` execution and re-enabled "
        "once the pod's voice-ingest stub returns multi-sentence whisper "
        "chunks."
    )
)
async def test_http_import_writes_per_sentence_rows() -> None:  # pragma: no cover
    """Placeholder: covered by the unit test above + the pod's e2e run."""
