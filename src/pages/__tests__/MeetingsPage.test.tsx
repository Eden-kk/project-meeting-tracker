import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, act, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MeetingsPage from '../MeetingsPage';
import * as client from '../../api/client';
import * as registry from '../../lib/meetingsRegistry';
import type { Meeting } from '../../api/client';

function meetingFixture(overrides: Partial<Meeting> = {}): Meeting {
  return {
    meeting_id: 'm1',
    artifact_id: 'a1',
    title: 'Server meeting',
    status: 'ready',
    started_at: null,
    ended_at: null,
    finalized_at: null,
    current_schema: null,
    evidence_quality: 'medium',
    ...overrides,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MeetingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('MeetingsPage', () => {
  beforeEach(() => {
    localStorage.clear();
    registry._resetMigrationLatch();
    vi.restoreAllMocks();
  });

  it('shows empty state when API returns no meetings', async () => {
    vi.spyOn(client, 'listMeetings').mockResolvedValue({ items: [], total: 0 });
    renderPage();
    expect(await screen.findByRole('heading', { name: /no meetings yet/i })).toBeInTheDocument();
  });

  it('search filters by case-insensitive title substring', async () => {
    vi.spyOn(client, 'listMeetings').mockResolvedValue({
      items: [
        meetingFixture({ meeting_id: 'm1', title: 'Quarterly review' }),
        meetingFixture({ meeting_id: 'm2', title: 'Daily standup' }),
      ],
      total: 2,
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByLabelText(/search meetings/i)).toBeInTheDocument());
    const search = screen.getByLabelText(/search meetings/i);
    await user.type(search, 'STAND');
    expect(screen.getByRole('link', { name: 'Daily standup' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Quarterly review' })).not.toBeInTheDocument();
  });

  it('source filter chip narrows the list (registry-supplied source_type)', async () => {
    // The API does not surface source_type today, so source filtering uses
    // the registry-side value the import flow recorded.  Seed registry to
    // match server ids so the merge attaches the right source_type.
    vi.spyOn(client, 'listMeetings').mockResolvedValue({
      items: [
        meetingFixture({ meeting_id: 'm1', title: 'Voice one' }),
        meetingFixture({ meeting_id: 'm2', title: 'Pasted one' }),
      ],
      total: 2,
    });
    act(() => {
      registry.upsert({
        meeting_id: 'm1', artifact_id: 'a1', title: 'Voice one',
        imported_at: '2025-01-15T10:00:00.000Z',
        source_type: 'voice_file', detected_pattern: null,
        evidence_quality: 'medium', status: 'ready',
        last_seen_at: '2025-01-15T10:00:00.000Z',
      });
      registry.upsert({
        meeting_id: 'm2', artifact_id: 'a2', title: 'Pasted one',
        imported_at: '2025-01-15T10:00:00.000Z',
        source_type: 'pasted_transcript', detected_pattern: null,
        evidence_quality: 'medium', status: 'ready',
        last_seen_at: '2025-01-15T10:00:00.000Z',
      });
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByRole('link', { name: 'Voice one' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /^voice file$/i }));
    expect(screen.getByRole('link', { name: 'Voice one' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Pasted one' })).not.toBeInTheDocument();
  });

  it('pattern chips appear only for patterns present in the merged list', async () => {
    vi.spyOn(client, 'listMeetings').mockResolvedValue({
      items: [
        meetingFixture({
          meeting_id: 'm1',
          detected_pattern: { primary_pattern: 'kickoff', confidence: 0.9 },
        }),
        meetingFixture({ meeting_id: 'm2', detected_pattern: undefined }),
      ],
      total: 2,
    });
    renderPage();
    await waitFor(() => expect(screen.getByRole('button', { name: 'kickoff' })).toBeInTheDocument());
  });

  it('view toggle switches between table and cards', async () => {
    vi.spyOn(client, 'listMeetings').mockResolvedValue({
      items: [meetingFixture({ meeting_id: 'm1', title: 'Only' })],
      total: 1,
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /^cards$/i }));
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    const links = screen.getAllByRole('link');
    expect(links.some((l) => l.getAttribute('href') === '/meetings/m1')).toBe(true);
  });

  it('shows "no meetings match" when filters exclude every entry', async () => {
    vi.spyOn(client, 'listMeetings').mockResolvedValue({
      items: [meetingFixture({ meeting_id: 'm1', title: 'Ready one', status: 'ready' })],
      total: 1,
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByRole('link', { name: 'Ready one' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /^failed$/i }));
    expect(screen.getByText(/no meetings match the current filters/i)).toBeInTheDocument();
    const statusRow = screen.getByText('Status').parentElement!;
    expect(within(statusRow).getByRole('button', { name: 'failed' })).toBeInTheDocument();
  });
});
