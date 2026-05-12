import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HomeMemoryItemsCard, formatRelative } from '../HomeMemoryItemsCard';
import { queryKeys } from '../../api/queryKeys';
import type { ActionItemRow, ListActionItemsParams, ActionItemListResponse } from '../../api/memory_cards.types';

function row(overrides: Partial<ActionItemRow> = {}): ActionItemRow {
  return {
    memory_card_id: 'mc-1',
    meeting_id: 'm-1',
    meeting_title: 'Standup',
    meeting_finalized_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
    type: 'action_item',
    title: 'Ship the cards',
    content: 'Land the home-cards slice.',
    source_chunk_ids: ['chunk-7'],
    confidence: 0.9,
    ...overrides,
  };
}

function renderCard(props: {
  queryFn: (params: ListActionItemsParams) => Promise<ActionItemListResponse>;
}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <HomeMemoryItemsCard
          type="action_item"
          title="Action items"
          dashboardHref="/action-items"
          emptyTitle="No action items yet"
          emptyBody="Items will appear here."
          queryFn={props.queryFn}
          queryKey={queryKeys.actionItems}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('HomeMemoryItemsCard', () => {
  it('requests limit=8 and renders whatever the server returns', async () => {
    const items = Array.from({ length: 12 }).map((_, i) =>
      row({ memory_card_id: `mc-${i}`, title: `Item ${i}` }),
    );
    // Server obeys limit=8 — return 8 even though fixture has 12 candidates.
    const queryFn = vi.fn(async (params: ListActionItemsParams) => ({
      items: items.slice(0, params.limit ?? items.length),
      total: items.length,
    }));

    renderCard({ queryFn });

    await waitFor(() => {
      expect(screen.getByText('Item 0')).toBeInTheDocument();
    });
    expect(queryFn).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 8 }),
    );
    // 8 rows rendered (Item 0..7); Item 8+ not in payload.
    expect(screen.getByText('Item 7')).toBeInTheDocument();
    expect(screen.queryByText('Item 8')).not.toBeInTheDocument();
  });

  it('renders the empty state with /import CTA when no items', async () => {
    const queryFn = vi.fn(async () => ({ items: [], total: 0 }));
    renderCard({ queryFn });

    expect(
      await screen.findByRole('heading', { name: /no action items yet/i }),
    ).toBeInTheDocument();
    const cta = screen.getByRole('link', { name: /import a meeting/i });
    expect(cta).toHaveAttribute('href', '/import');
  });

  it('row href uses #seg:<first chunk> when source_chunk_ids non-empty, plain meeting URL otherwise', async () => {
    const queryFn = vi.fn(async () => ({
      items: [
        row({ memory_card_id: 'a', title: 'With chunk', source_chunk_ids: ['c-42'] }),
        row({ memory_card_id: 'b', title: 'No chunk', source_chunk_ids: [], meeting_id: 'm-9' }),
      ],
      total: 2,
    }));
    renderCard({ queryFn });

    const withChunk = await screen.findByRole('link', { name: /with chunk/i });
    expect(withChunk).toHaveAttribute('href', '/meetings/m-1#seg:c-42');
    const noChunk = screen.getByRole('link', { name: /no chunk/i });
    expect(noChunk).toHaveAttribute('href', '/meetings/m-9');
  });
});

describe('formatRelative', () => {
  it('returns "—" on null', () => {
    expect(formatRelative(null)).toBe('—');
  });
  it('returns "just now" for sub-minute', () => {
    expect(formatRelative(new Date(Date.now() - 5_000).toISOString())).toBe('just now');
  });
  it('returns "N min ago" under an hour', () => {
    expect(formatRelative(new Date(Date.now() - 5 * 60_000).toISOString())).toBe('5 min ago');
  });
  it('returns locale date past 14 days', () => {
    const iso = new Date(Date.now() - 30 * 24 * 60 * 60_000).toISOString();
    const out = formatRelative(iso);
    // Locale-dependent string but must not be one of the relative variants.
    expect(out).not.toMatch(/just now|min ago|hours ago|days ago/);
  });
});
