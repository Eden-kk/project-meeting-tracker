"""Per-meeting sentence buffer for the Wave 8 live pipeline.

The live path (`POST /api/live-meetings/{id}/audio-chunk`) hands voice-ingest
each ~10-s WebM chunk and gets back a list of raw Whisper segments. Whisper
freely splits mid-sentence at chunk boundaries, so emitting one row per
segment produces flicker on the UI ("...the meeting is" → next poll → "...
the meeting is going"). Wave 8.3 introduces a per-meeting `SentenceBuffer`
that holds the trailing fragment until terminal punctuation arrives in a
later chunk (or the force-flush timeout fires). Only complete sentences
leave this layer.

Wave 8.4 will diarize each complete sentence; Wave 8.5 will gate persistence
on the diarization result. This file knows nothing about either — its only
job is "complete-sentence emission with stable timing anchors".

Pure logic; no async, no IO, no DB.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

# Terminal punctuation: ASCII + CJK full-width.
#
# Lookahead rules differ by terminal class:
#   - ASCII terminals (`. ! ?`) require whitespace, end-of-string, or a
#     closing bracket so we don't split on decimals (3.14).
#   - CJK terminals (`。！？`) split unconditionally — Chinese text has no
#     inter-sentence whitespace, and these glyphs are unambiguous
#     terminators (they don't appear inside numbers or abbreviations).
_ASCII_TERMINAL = r"[.!?]"
_CJK_TERMINAL = r"[。！？]"
_CLOSE = r"[\"'’”』」)\]]?"
_SENTENCE_RE = re.compile(
    rf"(?:({_ASCII_TERMINAL}{_CLOSE})(?=\s|$))"
    rf"|(?:({_CJK_TERMINAL}{_CLOSE}))"
)

# Default force-flush window: a held trailing fragment older than this is
# emitted as its own sentence so a long mid-sentence pause does not stall
# the live UI forever. Configurable per-meeting via the constructor; the
# storage-router reads its default from `voice_ingest.config.PUNCT_MAX_WAIT_MS`.
DEFAULT_PUNCT_MAX_WAIT_MS = 8000


@dataclass(frozen=True)
class WhisperSeg:
    """The minimal shape we consume from voice-ingest's `/voice/transcribe`.

    `start_ms` / `end_ms` are already chunk-offset-shifted by the caller —
    `live_route.receive_chunk` adds the running offset before feeding here,
    so this layer treats the timeline as monotonic across the meeting.
    """

    text: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class CompleteSentence:
    """Output type — guaranteed to end on terminal punctuation OR to be a
    force-flushed trailing fragment after `PUNCT_MAX_WAIT_MS`.
    """

    text: str
    start_ms: int
    end_ms: int


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


@dataclass
class SentenceBuffer:
    """Per-meeting trailing-fragment buffer.

    State is intentionally tiny:
      - `pending_text`: the in-flight prefix carried over from prior feeds.
      - `pending_start_ms`: timeline anchor for `pending_text` (the start of
        the earliest segment that contributed to it).
      - `pending_last_end_ms`: end-of-the-most-recent-segment timestamp, used
        as the `end_ms` if we force-flush.
      - `pending_first_seen_ms`: monotonic wallclock when the trailing
        fragment first started accumulating, used for the force-flush
        timeout check.
    """

    punct_max_wait_ms: int = DEFAULT_PUNCT_MAX_WAIT_MS
    pending_text: str = ""
    pending_start_ms: int | None = None
    pending_last_end_ms: int | None = None
    pending_first_seen_ms: int | None = field(default=None, repr=False)

    def feed(self, segments: list[WhisperSeg]) -> list[CompleteSentence]:
        """Consume Whisper segments and emit any sentences that completed."""
        emitted: list[CompleteSentence] = []
        for seg in segments:
            if not seg.text.strip():
                continue
            # Anchor the running fragment to the earliest contributing segment.
            if self.pending_start_ms is None:
                self.pending_start_ms = seg.start_ms
                self.pending_first_seen_ms = _now_ms()
            self.pending_last_end_ms = seg.end_ms
            # Insert a single space if we're stitching across segments and
            # neither side already has whitespace at the boundary.
            joiner = "" if (not self.pending_text or self.pending_text.endswith(" ") or seg.text.startswith(" ")) else " "
            self.pending_text = f"{self.pending_text}{joiner}{seg.text}"
            emitted.extend(self._drain_complete_sentences())
        # Force-flush a stale trailing fragment if it has been pending too long.
        if self._should_force_flush():
            forced = self._emit_pending_as_sentence()
            if forced is not None:
                emitted.append(forced)
        return emitted

    def flush(self) -> list[CompleteSentence]:
        """Emit any trailing fragment as a final sentence; called on
        `end_live_meeting` so the last partial utterance is not lost."""
        emitted = self._drain_complete_sentences()
        forced = self._emit_pending_as_sentence()
        if forced is not None:
            emitted.append(forced)
        return emitted

    # --- internals -----------------------------------------------------

    def _drain_complete_sentences(self) -> list[CompleteSentence]:
        """Split `pending_text` on terminal punctuation; emit completed ones,
        keep the trailing remainder in `pending_text`.

        Timing rule: each emitted sentence inherits the buffer's anchor as
        its `start_ms` and the most recent segment's `end_ms` as its
        `end_ms`. Sub-sentence-resolution timing is not available — Whisper
        gives us per-segment, not per-token, timestamps.
        """
        if not self.pending_text:
            return []
        out: list[CompleteSentence] = []
        text = self.pending_text
        # Walk the regex matches; everything up to and including each match
        # end is a complete sentence.
        last_cut = 0
        for m in _SENTENCE_RE.finditer(text):
            sentence = text[last_cut : m.end()].strip()
            last_cut = m.end()
            if sentence:
                out.append(
                    CompleteSentence(
                        text=sentence,
                        start_ms=self.pending_start_ms or 0,
                        end_ms=self.pending_last_end_ms or 0,
                    )
                )
        # Whatever is past the last match is the new trailing fragment.
        remainder = text[last_cut:].lstrip()
        if remainder:
            self.pending_text = remainder
            # Anchor of the remainder slides to "now-ish": the last emitted
            # sentence consumed our previous anchor. We set it to the most
            # recent segment's end, the earliest possible start for the
            # remainder.
            if out:
                self.pending_start_ms = self.pending_last_end_ms
                self.pending_first_seen_ms = _now_ms()
        else:
            self._reset()
        return out

    def _should_force_flush(self) -> bool:
        if not self.pending_text or self.pending_first_seen_ms is None:
            return False
        return (_now_ms() - self.pending_first_seen_ms) >= self.punct_max_wait_ms

    def _emit_pending_as_sentence(self) -> CompleteSentence | None:
        if not self.pending_text.strip():
            self._reset()
            return None
        sentence = CompleteSentence(
            text=self.pending_text.strip(),
            start_ms=self.pending_start_ms or 0,
            end_ms=self.pending_last_end_ms or 0,
        )
        self._reset()
        return sentence

    def _reset(self) -> None:
        self.pending_text = ""
        self.pending_start_ms = None
        self.pending_last_end_ms = None
        self.pending_first_seen_ms = None


__all__ = [
    "CompleteSentence",
    "DEFAULT_PUNCT_MAX_WAIT_MS",
    "SentenceBuffer",
    "WhisperSeg",
]
