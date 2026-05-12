"""Wave 8.5 — diarization gate.

The user's hard rule for the live path: a row in `speaker_segments` must
not appear until BOTH (a) its text is a complete sentence (Wave 8.3) and
(b) its speaker label is settled by pyannote (Wave 8.4). This module
provides the gate.

Implementation: a small async helper `gate_assign(diarizer, t0_ms, t1_ms)`
that polls `LiveDiarizer.assign` every `poll_ms` and either returns a
non-None speaker label OR returns `None` after `timeout_ms` so the
caller can persist the row with `speaker_id="unknown"` and not stall.

The plan describes a per-meeting asyncio queue + consumer task. This
inline poll keeps the same observable contract (sentences persisted in
order, at most `timeout_ms` after their completion, never relabelled)
but with one fewer moving part — the consumer task / per-meeting
lifecycle disappears. The chunk handler (`live_route.receive_chunk`) is
already an async function, so an `await asyncio.sleep(...)` inside it
yields the event loop just as a separate task would.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


class _DiarizerLike(Protocol):
    def assign(self, t0_ms: int, t1_ms: int) -> str | None: ...


@dataclass(frozen=True)
class GateResult:
    """The outcome of a single gate cycle for one sentence.

    `speaker_id == "unknown"` and `gated_unknown is True` when the
    timeout fired before the diarizer settled a label.
    """

    speaker_id: str
    gated_unknown: bool
    waited_ms: int


async def gate_assign(
    diarizer: _DiarizerLike,
    t0_ms: int,
    t1_ms: int,
    *,
    timeout_ms: int = 10_000,
    poll_ms: int = 500,
    sleep: callable = asyncio.sleep,  # injectable for tests
) -> GateResult:
    """Poll `diarizer.assign(t0, t1)` until non-None or `timeout_ms` elapses.

    Returns a `GateResult` either way; callers persist the row with the
    returned `speaker_id` (which may be `"unknown"` on timeout). The
    `waited_ms` field is logged so we can tune the timeout against
    real-world p95 latency.
    """
    waited = 0
    label: str | None = None
    while waited < timeout_ms:
        label = diarizer.assign(t0_ms, t1_ms)
        if label is not None:
            return GateResult(speaker_id=label, gated_unknown=False, waited_ms=waited)
        # Sleep in `poll_ms` increments until either the diarizer settles
        # or the budget runs out. The final iteration may be smaller than
        # `poll_ms` so we don't overshoot the wallclock deadline.
        step = min(poll_ms, timeout_ms - waited)
        await sleep(step / 1000.0)
        waited += step
    logger.info(
        "diarization_gate: timeout for [%s, %s] after %s ms — falling back to unknown",
        t0_ms,
        t1_ms,
        waited,
    )
    return GateResult(speaker_id="unknown", gated_unknown=True, waited_ms=waited)


__all__ = ["GateResult", "gate_assign"]
