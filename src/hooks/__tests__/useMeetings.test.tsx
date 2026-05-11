import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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
  return {
    wrapper: ({ children }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>,
  };
}

describe('mergeServerAndRegistry', () => {
  it('server fields win on overlap; registry adds source_type/imported_at', () => {
    const merged = mergeServerAndRegistry(
      [meetingFixture({ title: 'Server', status: 'ready' })],
      [summaryFixture({ title: 'Registry', status: 'processing', source_type: 'voice_file' })],
    );
    expect(merged).toHaveLength(1);
    expect(merged[0].title).toBe('Server');
    expect(merged[0].status).toBe('ready');
    expect(merged[0].source_type).toBe('voice_file');
    expect(merged[0].imported_at).toBe('2025-01-01T00:00:00.000Z');
  });

  it('registry-only entries are appended after the server run', () => {
    const merged = mergeServerAndRegistry(
      [meetingFixture({ meeting_id: 'm_server' })],
      [summaryFixture({ meeting_id: 'm_local' })],
    );
    expect(merged.map((m) => m.meeting_id)).toEqual(['m_server', 'm_local']);
  });

  it('preserves server ordering', () => {
    const merged = mergeServerAndRegistry(
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
    const { result } = renderHook(() => useMeetings('ws_dev'), wrap());
    await waitFor(() => expect(result.current.isOffline).toBe(true));
    expect(result.current.meetings.map((m) => m.meeting_id)).toEqual(['m_local']);
  });

  it('returns merged list on network success', async () => {
    vi.spyOn(client, 'listMeetings').mockResolvedValue({
      items: [meetingFixture({ meeting_id: 'm_server', title: 'Server' })],
      total: 1,
    });
    act(() => {
      registry.upsert(summaryFixture({ meeting_id: 'm_local', title: 'Local only' }));
    });
    const { result } = renderHook(() => useMeetings('ws_dev'), wrap());
    await waitFor(() => expect(result.current.meetings.length).toBe(2));
    expect(result.current.isOffline).toBe(false);
    expect(result.current.meetings.map((m) => m.meeting_id)).toEqual(['m_server', 'm_local']);
  });
});
