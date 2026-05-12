import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import HomePage from '../HomePage';
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

function summary(id: string, overrides: Partial<registry.StoredMeetingSummary> = {}): registry.StoredMeetingSummary {
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
    ...overrides,
  };
}

function renderHome() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('HomePage', () => {
  beforeEach(() => {
    localStorage.clear();
    registry._resetMigrationLatch();
    vi.restoreAllMocks();
    vi.spyOn(client, 'listMeetingCards').mockResolvedValue({ items: [], total: 0 });
    // New Outstanding cards on Home call these two endpoints; default to empty.
    vi.spyOn(client, 'listActionItems').mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(client, 'listOpenQuestions').mockResolvedValue({ items: [], total: 0 });
  });

  it('shows empty state when API returns nothing and registry is empty', async () => {
    vi.spyOn(client, 'listMeetings').mockResolvedValue({ items: [], total: 0 });
    renderHome();
    expect(await screen.findByRole('heading', { name: /no meetings yet/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^new import$/i })).toHaveAttribute('href', '/import');
  });

  it('renders stats and recent cards from the API list', async () => {
    vi.spyOn(client, 'listMeetings').mockResolvedValue({
      items: [
        meetingFixture({ meeting_id: 'm3', title: 'C', status: 'ready' }),
        meetingFixture({ meeting_id: 'm2', title: 'B', status: 'failed' }),
        meetingFixture({ meeting_id: 'm1', title: 'A', status: 'processing' }),
      ],
      total: 3,
    });
    renderHome();
    await waitFor(() => expect(screen.getByText('Total')).toBeInTheDocument());
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('1 / 1 / 1')).toBeInTheDocument();
    // First server entry comes first.
    const cards = screen.getAllByRole('link').filter((a) => a.getAttribute('href')?.startsWith('/meetings/'));
    expect(cards[0]).toHaveTextContent('C');
  });

  it('renders the Total cards across workspace chip with summed visible totals', async () => {
    vi.spyOn(client, 'listMeetings').mockResolvedValue({
      items: [
        meetingFixture({ meeting_id: 'm1', title: 'A' }),
        meetingFixture({ meeting_id: 'm2', title: 'B' }),
      ],
      total: 2,
    });
    vi.spyOn(client, 'listMeetingCards').mockImplementation(async (id) => ({
      items: [],
      total: id === 'm1' ? 2 : 1,
    }));

    renderHome();

    const chipLabel = await screen.findByText(/total cards across workspace/i);
    const chip = chipLabel.closest('div.rounded') as HTMLElement;
    await waitFor(() => {
      expect(chip.querySelector('div.text-xl')?.textContent).toBe('3');
    });
    // The original three stat chips must still be present.
    expect(screen.getByText('Total')).toBeInTheDocument();
    expect(screen.getByText('Ready / Processing / Failed')).toBeInTheDocument();
    expect(screen.getByText('Top source')).toBeInTheDocument();
    // Phase-3: legacy chip label is gone.
    expect(screen.queryByText(/cards needing review/i)).not.toBeInTheDocument();
  });

  it('renders the Outstanding section with Action items and Open questions cards', async () => {
    vi.spyOn(client, 'listMeetings').mockResolvedValue({
      items: [meetingFixture({ meeting_id: 'm1', title: 'A' })],
      total: 1,
    });
    const aiSpy = vi.spyOn(client, 'listActionItems').mockResolvedValue({
      items: [
        {
          memory_card_id: 'mc-a1',
          meeting_id: 'm1',
          meeting_title: 'A',
          meeting_finalized_at: new Date(Date.now() - 60_000).toISOString(),
          type: 'action_item',
          title: 'Ship it',
          content: '',
          source_chunk_ids: ['c-1'],
          confidence: 0.9,
        },
      ],
      total: 1,
    });
    const oqSpy = vi.spyOn(client, 'listOpenQuestions').mockResolvedValue({
      items: [
        {
          memory_card_id: 'mc-q1',
          meeting_id: 'm1',
          meeting_title: 'A',
          meeting_finalized_at: new Date(Date.now() - 60_000).toISOString(),
          type: 'open_question',
          title: 'Who owns ingestion?',
          content: '',
          source_chunk_ids: ['c-2'],
          confidence: 0.8,
        },
      ],
      total: 1,
    });

    renderHome();

    await waitFor(() => expect(screen.getByText('Action items')).toBeInTheDocument());
    expect(screen.getByText('Open questions')).toBeInTheDocument();
    expect(await screen.findByText('Ship it')).toBeInTheDocument();
    expect(await screen.findByText('Who owns ingestion?')).toBeInTheDocument();
    // Both endpoints called with limit=8.
    expect(aiSpy).toHaveBeenCalledWith(expect.objectContaining({ limit: 8 }));
    expect(oqSpy).toHaveBeenCalledWith(expect.objectContaining({ limit: 8 }));
    // Header "View all" links go to the dashboards.
    const viewAllLinks = screen.getAllByRole('link', { name: /view all/i });
    expect(viewAllLinks.map((a) => a.getAttribute('href'))).toEqual(
      expect.arrayContaining(['/action-items', '/open-questions']),
    );
  });

  it('falls back to registry on network failure and caps at 6 cards', async () => {
    vi.spyOn(client, 'listMeetings').mockRejectedValue(new Error('offline'));
    act(() => {
      for (let i = 0; i < 9; i++) {
        registry.upsert(summary('m' + i));
      }
    });
    renderHome();
    await waitFor(() => {
      const cards = screen.getAllByRole('link').filter((a) => a.getAttribute('href')?.startsWith('/meetings/'));
      expect(cards).toHaveLength(6);
    });
  });
});
