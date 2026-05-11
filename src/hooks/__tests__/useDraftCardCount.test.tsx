import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useDraftCardCount } from '../useDraftCardCount';
import * as client from '../../api/client';
import * as registry from '../../lib/meetingsRegistry';

function summary(id: string): registry.StoredMeetingSummary {
  return {
    meeting_id: id,
    artifact_id: 'a' + id,
    title: 'Meeting ' + id,
    imported_at: '2025-01-15T10:00:00.000Z',
    source_type: 'pasted_transcript',
    detected_pattern: null,
    evidence_quality: 'medium',
    status: 'ready',
    last_seen_at: '2025-01-15T10:00:00.000Z',
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('useDraftCardCount', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    registry._resetMigrationLatch();
    registry.upsert(summary('m1'));
    registry.upsert(summary('m2'));
  });

  it('sums per-meeting draft totals across the meeting list', async () => {
    vi.spyOn(client, 'listMeetings').mockRejectedValue(new Error('offline'));
    const spy = vi
      .spyOn(client, 'listMeetingCards')
      .mockImplementation(async (id) => ({
        items: [],
        total: id === 'm1' ? 2 : 0,
      }));

    const { result } = renderHook(() => useDraftCardCount(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.count).toBe(2);
    expect(spy).toHaveBeenCalledWith('m1', { state: 'draft' });
    expect(spy).toHaveBeenCalledWith('m2', { state: 'draft' });
  });
});
