"""Wave 8.5 — diarization gate unit tests.

Tests the inline gate helper (`gate_assign`) against fake `LiveDiarizer`
implementations: one that resolves on the first poll, one that resolves
on the Nth poll, one that never resolves (timeout path). Sleep is
injected so tests run in milliseconds, not seconds.
"""

from __future__ import annotations

import asyncio

import pytest

from storage_router.diarization_gate import gate_assign


class _FakeDiar:
    def __init__(self, schedule: list[str | None]) -> None:
        # Each `assign` call pops the next return value off the schedule.
        # If schedule is exhausted, all subsequent calls return None.
        self._schedule = list(schedule)

    def assign(self, t0_ms: int, t1_ms: int) -> str | None:
        if not self._schedule:
            return None
        return self._schedule.pop(0)


@pytest.mark.asyncio
async def test_gate_returns_label_on_first_poll():
    diar = _FakeDiar(["speaker_2"])
    sleeps: list[float] = []

    async def _no_sleep(s: float) -> None:
        sleeps.append(s)

    result = await gate_assign(
        diar, 0, 5_000, timeout_ms=10_000, poll_ms=500, sleep=_no_sleep
    )
    assert result.speaker_id == "speaker_2"
    assert result.gated_unknown is False
    assert result.waited_ms == 0
    assert sleeps == []  # never slept


@pytest.mark.asyncio
async def test_gate_resolves_on_third_poll():
    diar = _FakeDiar([None, None, "speaker_1"])
    sleeps: list[float] = []

    async def _no_sleep(s: float) -> None:
        sleeps.append(s)

    result = await gate_assign(
        diar, 0, 5_000, timeout_ms=10_000, poll_ms=500, sleep=_no_sleep
    )
    assert result.speaker_id == "speaker_1"
    assert result.gated_unknown is False
    assert result.waited_ms == 1000  # two 500-ms sleeps before resolve
    assert sleeps == [0.5, 0.5]


@pytest.mark.asyncio
async def test_gate_times_out_to_unknown():
    diar = _FakeDiar([])  # always returns None
    sleeps: list[float] = []

    async def _no_sleep(s: float) -> None:
        sleeps.append(s)

    result = await gate_assign(
        diar, 0, 5_000, timeout_ms=2_000, poll_ms=500, sleep=_no_sleep
    )
    assert result.speaker_id == "unknown"
    assert result.gated_unknown is True
    assert result.waited_ms == 2_000
    # Polling cadence: poll, sleep, poll, sleep, poll, sleep, poll, sleep,
    # final poll — 4 sleeps of 0.5 s = 2 s.
    assert sleeps == [0.5, 0.5, 0.5, 0.5]


@pytest.mark.asyncio
async def test_gate_handles_uneven_final_step():
    """If `timeout_ms` is not a clean multiple of `poll_ms`, the final
    sleep is shorter so we don't overshoot the wallclock deadline."""
    diar = _FakeDiar([])
    sleeps: list[float] = []

    async def _no_sleep(s: float) -> None:
        sleeps.append(s)

    result = await gate_assign(
        diar, 0, 1_000, timeout_ms=1_200, poll_ms=500, sleep=_no_sleep
    )
    assert result.gated_unknown is True
    assert result.waited_ms == 1_200
    # 500 + 500 + 200.
    assert sleeps == [0.5, 0.5, 0.2]


@pytest.mark.asyncio
async def test_real_asyncio_sleep_is_used_by_default():
    """Smoke: gate_assign without injected sleep uses asyncio.sleep
    (i.e., the sleep is awaitable). We use a tiny timeout so the test
    completes in <100 ms."""
    diar = _FakeDiar([None, "speaker_5"])
    result = await asyncio.wait_for(
        gate_assign(diar, 0, 1_000, timeout_ms=500, poll_ms=50),
        timeout=2.0,
    )
    assert result.speaker_id == "speaker_5"
    assert result.gated_unknown is False
