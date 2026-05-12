import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useTotalCardCount } from '../useDraftCardCount';
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
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/ws/ws_dev/']}>
        <Routes>
          <Route path="/ws/:workspaceId/*" element={<>{children}</>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('useTotalCardCount', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    registry._resetMigrationLatch();
    registry.upsert(summary('m1'));
    registry.upsert(summary('m2'));
  });

  it('sums per-meeting visible totals across the meeting list', async () => {
    vi.spyOn(client, 'listMeetings').mockRejectedValue(new Error('offline'));
    const spy = vi
      .spyOn(client, 'listMeetingCards')
      .mockImplementation(async (id) => ({
        items: [],
        total: id === 'm1' ? 2 : 1,
      }));

    const { result } = renderHook(() => useTotalCardCount(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.count).toBe(3);
    // Phase-3: there is no `state` filter; the hook calls listMeetingCards
    // with no filter argument at all.
    expect(spy).toHaveBeenCalledWith('m1');
    expect(spy).toHaveBeenCalledWith('m2');
  });
});
