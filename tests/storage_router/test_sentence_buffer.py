"""Wave 8.3 — sentence buffer unit tests.

Pure logic tests; no DB, no HTTP, no asyncio. Force-flush timing is
exercised via monkeypatching `_now_ms` so the test does not have to sleep.
"""

from __future__ import annotations

import pytest

from storage_router import sentence_buffer
from storage_router.sentence_buffer import (
    CompleteSentence,
    SentenceBuffer,
    WhisperSeg,
)


def _seg(text: str, start_ms: int, end_ms: int) -> WhisperSeg:
    return WhisperSeg(text=text, start_ms=start_ms, end_ms=end_ms)


def test_single_chunk_with_terminal_punctuation_emits_one_sentence():
    buf = SentenceBuffer()
    out = buf.feed([_seg("Hello world.", 0, 1000)])
    assert len(out) == 1
    assert out[0].text == "Hello world."
    assert out[0].start_ms == 0
    assert out[0].end_ms == 1000
    # Buffer should be drained.
    assert buf.pending_text == ""


def test_fragment_held_across_feeds_until_terminal_arrives():
    buf = SentenceBuffer()
    # Chunk 1 ends mid-sentence.
    out1 = buf.feed([_seg("the meeting is", 0, 1000)])
    assert out1 == [], "no terminal punctuation yet, must hold"
    # Chunk 2 completes it.
    out2 = buf.feed([_seg("going well.", 1000, 2000)])
    assert len(out2) == 1
    assert out2[0].text == "the meeting is going well."
    # The earlier anchor (start_ms=0) is preserved.
    assert out2[0].start_ms == 0
    assert out2[0].end_ms == 2000


def test_three_chunk_split_yields_one_complete_sentence():
    """The plan's verification spec: 3 chunks where chunk 1 ends mid-
    sentence; chunk 1 yields 0 sentences, chunk 2 (containing the period)
    yields 1 complete sentence joining chunks 1+2."""
    buf = SentenceBuffer()
    chunk1 = buf.feed([_seg("the project status", 0, 1500)])
    chunk2 = buf.feed([_seg("is on track. We are", 1500, 3000)])
    chunk3 = buf.feed([_seg("ahead of schedule.", 3000, 4500)])
    assert chunk1 == []
    assert len(chunk2) == 1
    assert chunk2[0].text == "the project status is on track."
    assert len(chunk3) == 1
    assert chunk3[0].text == "We are ahead of schedule."


def test_multiple_sentences_in_one_chunk_emit_in_order():
    buf = SentenceBuffer()
    out = buf.feed([_seg("First. Second! Third?", 0, 3000)])
    assert [s.text for s in out] == ["First.", "Second!", "Third?"]


def test_cjk_terminal_punctuation_splits_sentences():
    buf = SentenceBuffer()
    out = buf.feed([_seg("你好。今天天气不错！我们开始吧？", 0, 3000)])
    assert [s.text for s in out] == ["你好。", "今天天气不错！", "我们开始吧？"]


def test_zh_en_codeswitch_splits_on_either_terminal():
    buf = SentenceBuffer()
    out = buf.feed([_seg("Let me 解释 a bit。 Then we move on.", 0, 4000)])
    assert len(out) == 2
    assert out[0].text == "Let me 解释 a bit。"
    assert out[1].text == "Then we move on."


def test_flush_emits_trailing_fragment():
    buf = SentenceBuffer()
    buf.feed([_seg("Trailing fragment without terminator", 0, 1000)])
    forced = buf.flush()
    assert len(forced) == 1
    assert forced[0].text == "Trailing fragment without terminator"
    assert forced[0].start_ms == 0
    assert forced[0].end_ms == 1000
    # And buffer is empty after flush.
    assert buf.pending_text == ""


def test_flush_on_empty_buffer_is_noop():
    buf = SentenceBuffer()
    assert buf.flush() == []


def test_force_flush_after_punct_max_wait_ms(monkeypatch):
    """A trailing fragment older than `punct_max_wait_ms` must force-emit
    on the next `feed` so the live UI does not stall on a long pause."""
    fake_now = {"ms": 0}

    def _patched_now() -> int:
        return fake_now["ms"]

    monkeypatch.setattr(sentence_buffer, "_now_ms", _patched_now)

    buf = SentenceBuffer(punct_max_wait_ms=5000)
    fake_now["ms"] = 0
    out1 = buf.feed([_seg("Hanging fragment", 0, 1000)])
    assert out1 == []

    # Advance wallclock past the timeout AND feed an empty list so the
    # only path that can emit is the force-flush check.
    fake_now["ms"] = 6000
    out2 = buf.feed([])
    assert len(out2) == 1
    assert out2[0].text == "Hanging fragment"


def test_whitespace_only_segments_are_ignored():
    buf = SentenceBuffer()
    out = buf.feed([_seg("   ", 0, 1000), _seg("\n", 1000, 2000)])
    assert out == []
    # No anchor was set because no real text arrived.
    assert buf.pending_start_ms is None


def test_anchor_resets_for_remainder_after_emit():
    """After emitting one sentence in a chunk, the trailing remainder
    should anchor at the previous segment's end_ms (not at the original
    chunk start)."""
    buf = SentenceBuffer()
    out = buf.feed([_seg("Done. Continuing", 0, 2000)])
    assert len(out) == 1
    assert out[0].text == "Done."
    # The remainder is now pending; its anchor moved to 2000.
    assert buf.pending_text == "Continuing"
    assert buf.pending_start_ms == 2000


def test_complete_sentence_is_immutable_dataclass():
    s = CompleteSentence(text="x.", start_ms=0, end_ms=100)
    with pytest.raises(Exception):
        s.text = "y."  # frozen dataclass
