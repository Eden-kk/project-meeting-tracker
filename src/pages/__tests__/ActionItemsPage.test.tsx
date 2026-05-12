import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ActionItemsPage from '../ActionItemsPage';
import * as client from '../../api/client';
import type { ActionItemRow } from '../../api/memory_cards.types';

function row(overrides: Partial<ActionItemRow> = {}): ActionItemRow {
  return {
    memory_card_id: 'mc_1',
    meeting_id: 'm_1',
    meeting_title: 'Sprint planning',
    meeting_finalized_at: '2026-05-10T10:00:00Z',
    type: 'action_item',
    title: 'Ship login flow',
    content: 'Alice owns the rollout.',
    source_chunk_ids: ['seg_001'],
    speakers_json: ['Alice'],
    confidence: 0.9,
    created_at: '2026-05-10T09:00:00Z',
    updated_at: '2026-05-10T09:00:00Z',
    ...overrides,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(client, 'listWorkspaces').mockResolvedValue({
    items: [{ id: 'ws_dev', name: 'Default', description: null, last_meeting_at: null }],
    total: 1,
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/ws/ws_dev/action-items']}>
        <Routes>
          <Route path="/ws/:workspaceId/action-items" element={<ActionItemsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ActionItemsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders rows returned by the API and links to the source segment', async () => {
    vi.spyOn(client, 'listActionItems').mockResolvedValue({
      items: [row()],
      total: 1,
    });
    renderPage();
    const titleLink = await screen.findByRole('link', { name: /ship login flow/i });
    expect(titleLink).toHaveAttribute('href', '/ws/ws_dev/meetings/m_1#seg:seg_001');
    expect(screen.getByText('Sprint planning')).toBeInTheDocument();
  });

  it('shows empty state when the API returns no items', async () => {
    vi.spyOn(client, 'listActionItems').mockResolvedValue({ items: [], total: 0 });
    renderPage();
    expect(
      await screen.findByRole('heading', { name: /no action items yet/i }),
    ).toBeInTheDocument();
  });
});
