import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import OpenQuestionsPage from '../OpenQuestionsPage';
import * as client from '../../api/client';
import type { ActionItemRow } from '../../api/memory_cards.types';

function row(overrides: Partial<ActionItemRow> = {}): ActionItemRow {
  return {
    memory_card_id: 'mc_2',
    meeting_id: 'm_2',
    meeting_title: 'Architecture sync',
    meeting_finalized_at: '2026-05-10T10:00:00Z',
    type: 'open_question',
    title: 'Do we still need redis here?',
    content: '',
    source_chunk_ids: ['seg_007'],
    speakers_json: ['Bob'],
    confidence: 0.7,
    created_at: '2026-05-10T09:00:00Z',
    updated_at: '2026-05-10T09:00:00Z',
    ...overrides,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <OpenQuestionsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('OpenQuestionsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('hits /api/open-questions and renders rows', async () => {
    const spy = vi.spyOn(client, 'listOpenQuestions').mockResolvedValue({
      items: [row()],
      total: 1,
    });
    renderPage();
    const titleLink = await screen.findByRole('link', { name: /redis/i });
    expect(titleLink).toHaveAttribute('href', '/meetings/m_2#seg:seg_007');
    expect(spy).toHaveBeenCalled();
  });

  it('shows the empty state for an empty workspace', async () => {
    vi.spyOn(client, 'listOpenQuestions').mockResolvedValue({ items: [], total: 0 });
    renderPage();
    expect(
      await screen.findByRole('heading', { name: /no open questions yet/i }),
    ).toBeInTheDocument();
  });
});
