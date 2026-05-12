import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useMeetings, mergeServerAndRegistry, meetingToSummary } from '../useMeetings';
import * as client from '../../api/client';
import * as registry from '../../lib/meetingsRegistry';
import type { Meeting } from '../../api/client';
import type { StoredMeetingSummary } from '../../lib/meetingsRegistry';

function meetingFixture(overrides: Partial<Meeting> = {}): Meeting {
  return {
    meeting_id: 'm1',
    artifact_id: 'a1',
    title: 'Server title',
    status: 'ready',
    started_at: null,
    ended_at: null,
    finalized_at: null,
    current_schema: null,
    evidence_quality: 'medium',
    ...overrides,
  };
}

function summaryFixture(overrides: Partial<StoredMeetingSummary> = {}): StoredMeetingSummary {
  return {
    meeting_id: 'm1',
    artifact_id: 'a1',
    title: 'Registry title',
    imported_at: '2025-01-01T00:00:00.000Z',
    source_type: 'pasted_transcript',
    detected_pattern: null,
    evidence_quality: 'unknown',
    status: 'processing',
    last_seen_at: '2025-01-01T00:00:00.000Z',
    ...overrides,
  };
}

function wrap(): { wrapper: ({ children }: { children: ReactNode }) => JSX.Element } {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // useMeetings now reads workspaceId from useParams() via useWorkspace,
  // so the hook must render inside a /ws/:workspaceId route.
  return {
    wrapper: ({ children }) => (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/ws/ws_dev']}>
          <Routes>
            <Route path="/ws/:workspaceId" element={<>{children}</>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    ),
  };
}

describe('mergeServerAndRegistry', () => {
  const recentIso = () => new Date(Date.now() - 30_000).toISOString();
  const ancientIso = '2025-01-01T00:00:00.000Z';

  it('server fields win on overlap; registry adds source_type/imported_at', () => {
    const { merged } = mergeServerAndRegistry(
      [meetingFixture({ title: 'Server', status: 'ready' })],
      [summaryFixture({ title: 'Registry', status: 'processing', source_type: 'voice_file' })],
    );
    expect(merged).toHaveLength(1);
    expect(merged[0].title).toBe('Server');
    expect(merged[0].status).toBe('ready');
    expect(merged[0].source_type).toBe('voice_file');
    expect(merged[0].imported_at).toBe(ancientIso);
  });

  it('fresh registry-only entries (within grace window) are appended after the server run', () => {
    const { merged, staleIds } = mergeServerAndRegistry(
      [meetingFixture({ meeting_id: 'm_server' })],
      [summaryFixture({ meeting_id: 'm_local', last_seen_at: recentIso() })],
    );
    expect(merged.map((m) => m.meeting_id)).toEqual(['m_server', 'm_local']);
    expect(staleIds).toEqual([]);
  });

  it('stale registry-only entries (past grace window) are pruned and returned in staleIds', () => {
    const { merged, staleIds } = mergeServerAndRegistry(
      [meetingFixture({ meeting_id: 'm_server' })],
      [summaryFixture({ meeting_id: 'm_local', last_seen_at: ancientIso })],
    );
    expect(merged.map((m) => m.meeting_id)).toEqual(['m_server']);
    expect(staleIds).toEqual(['m_local']);
  });

  it('preserves server ordering', () => {
    const { merged } = mergeServerAndRegistry(
      [
        meetingFixture({ meeting_id: 'm_third' }),
        meetingFixture({ meeting_id: 'm_second' }),
        meetingFixture({ meeting_id: 'm_first' }),
      ],
      [],
    );
    expect(merged.map((m) => m.meeting_id)).toEqual(['m_third', 'm_second', 'm_first']);
  });
});

describe('meetingToSummary', () => {
  it('falls back to registry title when server returns empty string', () => {
    const out = meetingToSummary(
      meetingFixture({ title: '' }),
      summaryFixture({ title: 'Registry kept this' }),
    );
    expect(out.title).toBe('Registry kept this');
  });

  it('flattens detected_pattern.primary_pattern from the server', () => {
    const out = meetingToSummary(
      meetingFixture({
        detected_pattern: {
          primary_pattern: 'kickoff',
          confidence: 0.9,
        },
      }),
    );
    expect(out.detected_pattern).toBe('kickoff');
  });
});

describe('useMeetings', () => {
  beforeEach(() => {
    localStorage.clear();
    registry._resetMigrationLatch();
    vi.restoreAllMocks();
  });

  it('returns registry contents on network failure (offline fallback)', async () => {
    vi.spyOn(client, 'listMeetings').mockRejectedValue(new Error('network down'));
    act(() => {
      registry.upsert(summaryFixture({ meeting_id: 'm_local', title: 'Local only' }));
    });
    const { result } = renderHook(() => useMeetings(), wrap());
    await waitFor(() => expect(result.current.isOffline).toBe(true));
    expect(result.current.meetings.map((m) => m.meeting_id)).toEqual(['m_local']);
  });

  it('returns merged list on network success (fresh registry entries survive)', async () => {
    vi.spyOn(client, 'listMeetings').mockResolvedValue({
      items: [meetingFixture({ meeting_id: 'm_server', title: 'Server' })],
      total: 1,
    });
    const recent = new Date(Date.now() - 30_000).toISOString();
    act(() => {
      registry.upsert(
        summaryFixture({ meeting_id: 'm_local', title: 'Local only', last_seen_at: recent }),
      );
    });
    const { result } = renderHook(() => useMeetings(), wrap());
    await waitFor(() => expect(result.current.meetings.length).toBe(2));
    expect(result.current.isOffline).toBe(false);
    expect(result.current.meetings.map((m) => m.meeting_id)).toEqual(['m_server', 'm_local']);
  });

  it('prunes stale registry entries (past grace window) from localStorage after a successful fetch', async () => {
    vi.spyOn(client, 'listMeetings').mockResolvedValue({
      items: [meetingFixture({ meeting_id: 'm_server', title: 'Server' })],
      total: 1,
    });
    act(() => {
      // ancient timestamp = older than the 5-minute grace window
      registry.upsert(
        summaryFixture({
          meeting_id: 'm_stale',
          title: 'Was deleted server-side',
          last_seen_at: '2025-01-01T00:00:00.000Z',
        }),
      );
    });
    const { result } = renderHook(() => useMeetings(), wrap());
    // Wait for server-fetch resolution: the merged list contains the server
    // item (initial loading state would only show the registry's m_stale).
    await waitFor(() =>
      expect(result.current.meetings.map((m) => m.meeting_id)).toContain('m_server'),
    );
    expect(result.current.meetings.map((m) => m.meeting_id)).toEqual(['m_server']);
    // After the prune effect runs, the stale id is gone from localStorage too.
    await waitFor(() => expect(registry.get('m_stale')).toBeNull());
  });
});
