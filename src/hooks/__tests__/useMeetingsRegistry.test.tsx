import { describe, it, expect, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useMeetingsRegistry } from '../useMeetingsRegistry';
import * as registry from '../../lib/meetingsRegistry';

describe('useMeetingsRegistry', () => {
  beforeEach(() => {
    localStorage.clear();
    registry._resetMigrationLatch();
  });

  it('returns initial entries and re-renders on in-tab writes', () => {
    const { result } = renderHook(() => useMeetingsRegistry());
    expect(result.current).toEqual([]);

    act(() => {
      registry.upsert({
        meeting_id: 'm1',
        artifact_id: 'a1',
        title: 'one',
        imported_at: '2025-01-01T00:00:00.000Z',
        source_type: 'pasted_transcript',
        detected_pattern: null,
        evidence_quality: 'medium',
        status: 'ready',
        last_seen_at: '2025-01-01T00:00:00.000Z',
      });
    });
    expect(result.current).toHaveLength(1);
    expect(result.current[0].meeting_id).toBe('m1');
  });
});
