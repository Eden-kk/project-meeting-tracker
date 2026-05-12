import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useScrollTarget } from '../useScrollTarget';

describe('useScrollTarget', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts with no target and tick=0', () => {
    const { result } = renderHook(() => useScrollTarget(1500));
    expect(result.current.targetSegmentId).toBeNull();
    expect(result.current.tick).toBe(0);
  });

  it('goto() sets the segment id, bumps tick, and clears after the highlight window', () => {
    const { result } = renderHook(() => useScrollTarget(1500));

    act(() => result.current.goto('seg_42'));
    expect(result.current.targetSegmentId).toBe('seg_42');
    expect(result.current.tick).toBe(1);

    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(result.current.targetSegmentId).toBeNull();
  });

  it('repeated goto() resets the timer and bumps tick on every call', () => {
    const { result } = renderHook(() => useScrollTarget(1500));

    act(() => result.current.goto('seg_1'));
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    // Same segment again — tick must bump so consumers re-fire effects.
    act(() => result.current.goto('seg_1'));
    expect(result.current.tick).toBe(2);

    // Original 1500ms timer should have been cleared; only 500ms in,
    // so still highlighted.
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(result.current.targetSegmentId).toBe('seg_1');

    // Full new window elapses; clears.
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.targetSegmentId).toBeNull();
  });
});
