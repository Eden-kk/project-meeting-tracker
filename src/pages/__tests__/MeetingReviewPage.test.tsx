import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MeetingReviewPage from '../MeetingReviewPage';
import * as client from '../../api/client';
import type { Meeting, NormalizedTranscript } from '../../api/client';
import { expectedNormalized, makeFixtureCards } from '../../mocks/fixtures';

function meetingFixture(): Meeting {
  return {
    meeting_id: 'm_fixture001',
    artifact_id: 'art_fixture001',
    title: 'Fixture meeting',
    status: 'ready',
    started_at: null,
    ended_at: null,
    finalized_at: null,
    current_schema: null,
    evidence_quality: 'medium',
  };
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/meetings/:id" element={<MeetingReviewPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('MeetingReviewPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    vi.spyOn(client, 'getMeeting').mockResolvedValue(meetingFixture());
    vi.spyOn(client, 'getMeetingTranscript').mockResolvedValue(
      expectedNormalized as NormalizedTranscript,
    );
    vi.spyOn(client, 'listMeetingCards').mockResolvedValue({ items: [], total: 0 });
  });

  it('renders all fixture segments in Transcript tab', async () => {
    renderAt('/meetings/m_fixture001');
    const rows = await screen.findAllByTestId('transcript-row');
    expect(rows).toHaveLength(expectedNormalized.segments.length);
  });

  it('only Share / Export remains disabled; Memory and Ask are active', async () => {
    renderAt('/meetings/m_fixture001');
    const share = await screen.findByRole('tab', { name: /share \/ export/i });
    expect(share).toHaveAttribute('aria-disabled', 'true');
    expect(share).toHaveAttribute('title', 'Arrives in Phase 8');
    const memory = screen.getByRole('tab', { name: /memory cards/i });
    expect(memory).not.toHaveAttribute('aria-disabled', 'true');
    const ask = screen.getByRole('tab', { name: /ask hermes/i });
    expect(ask).not.toHaveAttribute('aria-disabled', 'true');
  });

  it('Summary tab shows placeholder when meeting has no finalized_summary', async () => {
    const user = userEvent.setup();
    renderAt('/meetings/m_fixture001');
    await waitFor(() => screen.getAllByTestId('transcript-row'));
    await user.click(screen.getByRole('tab', { name: /^summary$/i }));
    expect(
      screen.getByText(/summary will appear after hermes finalizes/i),
    ).toBeInTheDocument();
  });

  it('Summary tab renders finalized_summary text when present', async () => {
    vi.spyOn(client, 'getMeeting').mockResolvedValue({
      ...meetingFixture(),
      finalized_summary: 'Team agreed to ship Phase 2 next quarter.',
    });
    const user = userEvent.setup();
    renderAt('/meetings/m_fixture001');
    await waitFor(() => screen.getAllByTestId('transcript-row'));
    await user.click(screen.getByRole('tab', { name: /^summary$/i }));
    expect(
      screen.getByText(/team agreed to ship phase 2 next quarter/i),
    ).toBeInTheDocument();
  });

  it('Wave 3.1: clicking a memory-card source pill switches to Transcript tab and highlights the cited segment', async () => {
    const cards = makeFixtureCards('m_fixture001');
    vi.spyOn(client, 'listMeetingCards').mockResolvedValue({
      items: cards,
      total: cards.length,
    });
    // Stub scrollIntoView (jsdom doesn't implement it).
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;

    const user = userEvent.setup();
    renderAt('/meetings/m_fixture001');

    // Wait for the meeting + transcript to load (Loading… is replaced by the tab bar).
    await screen.findAllByTestId('transcript-row');
    await user.click(screen.getByRole('tab', { name: /memory cards/i }));
    const pills = await screen.findAllByTestId('memory-card-source-pill');
    expect(pills.length).toBeGreaterThan(0);

    // Click the first card's pill — first fixture card cites seg_001.
    await user.click(pills[0]);

    // Tab flipped back to Transcript.
    await waitFor(() => {
      expect(screen.getAllByTestId('transcript-row').length).toBeGreaterThan(0);
    });

    // The seg_001 row carries the highlight marker.
    await waitFor(() => {
      const row = document.getElementById('segment-seg_001');
      expect(row).not.toBeNull();
      expect(row?.getAttribute('data-highlighted')).toBe('true');
    });

    // scrollIntoView fired against the cited segment node.
    expect(scrollSpy).toHaveBeenCalled();
  });
});
