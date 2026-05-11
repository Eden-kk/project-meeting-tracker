import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryCardsTab } from '../MemoryCardsTab';
import * as client from '../../api/client';
import { makeFixtureCards } from '../../mocks/fixtures';
import type { MemoryCard } from '../../api/memory_cards.types';

const MEETING_ID = 'm_test_1';

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryCardsTab meetingId={MEETING_ID} onEvidenceClick={() => {}} />
    </QueryClientProvider>,
  );
}

describe('MemoryCardsTab', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the four seeded fixture cards', async () => {
    const seeded = makeFixtureCards(MEETING_ID);
    vi.spyOn(client, 'listMeetingCards').mockResolvedValue({
      items: seeded,
      total: seeded.length,
    });

    renderTab();

    await waitFor(() => {
      const items = screen.getAllByTestId('memory-card-item');
      expect(items).toHaveLength(4);
    });
  });

  it('filters down to drafts when the Draft pill is clicked', async () => {
    const seeded = makeFixtureCards(MEETING_ID);
    const drafts = seeded.filter((c) => c.state === 'draft');
    const spy = vi
      .spyOn(client, 'listMeetingCards')
      .mockImplementation(async (_id, filters) => {
        if (filters?.state === 'draft') {
          return { items: drafts, total: drafts.length };
        }
        return { items: seeded, total: seeded.length };
      });

    const user = userEvent.setup();
    renderTab();

    await waitFor(() => {
      expect(screen.getAllByTestId('memory-card-item')).toHaveLength(4);
    });

    await user.click(screen.getByRole('button', { name: /^draft$/i }));

    await waitFor(() => {
      expect(screen.getAllByTestId('memory-card-item')).toHaveLength(3);
    });
    expect(spy).toHaveBeenCalledWith(MEETING_ID, expect.objectContaining({ state: 'draft' }));
  });

  it('approving a draft refetches and the card pill flips to Committed', async () => {
    const seeded = makeFixtureCards(MEETING_ID);
    const target = seeded.find((c) => c.state === 'draft')!;

    let approved = false;
    vi.spyOn(client, 'listMeetingCards').mockImplementation(async () => {
      const items: MemoryCard[] = seeded.map((c) =>
        c.memory_card_id === target.memory_card_id && approved
          ? { ...c, state: 'committed' }
          : c,
      );
      return { items, total: items.length };
    });
    vi.spyOn(client, 'commitCard').mockImplementation(async () => {
      approved = true;
      return { ...target, state: 'committed' };
    });

    const user = userEvent.setup();
    renderTab();

    const items = await screen.findAllByTestId('memory-card-item');
    const targetItem = items.find(
      (el) => el.getAttribute('data-card-id') === target.memory_card_id,
    )!;

    await user.click(within(targetItem).getByRole('button', { name: /approve/i }));

    await waitFor(() => {
      const refreshed = screen
        .getAllByTestId('memory-card-item')
        .find((el) => el.getAttribute('data-card-id') === target.memory_card_id)!;
      expect(within(refreshed).getByText(/committed/i)).toBeInTheDocument();
    });
  });
});
