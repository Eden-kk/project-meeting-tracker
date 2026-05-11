import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryCardsTab } from '../MemoryCardsTab';
import * as client from '../../api/client';
import { makeFixtureCards } from '../../mocks/fixtures';

const MEETING_ID = 'm_test_1';

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryCardsTab meetingId={MEETING_ID} onEvidenceClick={() => {}} />
    </QueryClientProvider>,
  );
}

describe('MemoryCardsTab (Phase-3, read-only)', () => {
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

  it('filters by type when a type pill is clicked', async () => {
    const seeded = makeFixtureCards(MEETING_ID);
    const decisions = seeded.filter((c) => c.type === 'decision');
    const spy = vi
      .spyOn(client, 'listMeetingCards')
      .mockImplementation(async (_id, filters) => {
        if (filters?.type === 'decision') {
          return { items: decisions, total: decisions.length };
        }
        return { items: seeded, total: seeded.length };
      });

    const user = userEvent.setup();
    renderTab();

    await waitFor(() => {
      expect(screen.getAllByTestId('memory-card-item')).toHaveLength(4);
    });

    await user.click(screen.getByRole('button', { name: /^decision$/i }));

    await waitFor(() => {
      expect(screen.getAllByTestId('memory-card-item')).toHaveLength(1);
    });
    expect(spy).toHaveBeenCalledWith(MEETING_ID, expect.objectContaining({ type: 'decision' }));
  });

  it('does not render state-filter pills (Draft / Committed / Rejected)', async () => {
    const seeded = makeFixtureCards(MEETING_ID);
    vi.spyOn(client, 'listMeetingCards').mockResolvedValue({
      items: seeded,
      total: seeded.length,
    });
    renderTab();
    await waitFor(() =>
      expect(screen.getAllByTestId('memory-card-item')).toHaveLength(4),
    );
    expect(screen.queryByRole('button', { name: /^draft$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^committed$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^rejected$/i })).not.toBeInTheDocument();
  });

  describe('Wave 3.2 — confidence sort + needs-review filter', () => {
    it('sorts cards by confidence desc by default', async () => {
      // Fixture confidences: decision=0.92, action=0.7, pain=0.4, quote=0.85
      const seeded = makeFixtureCards(MEETING_ID);
      vi.spyOn(client, 'listMeetingCards').mockResolvedValue({
        items: seeded,
        total: seeded.length,
      });
      renderTab();
      await waitFor(() =>
        expect(screen.getAllByTestId('memory-card-item')).toHaveLength(4),
      );
      const order = screen
        .getAllByTestId('memory-card-confidence-pill')
        .map((el) => el.textContent);
      expect(order).toEqual(['92%', '85%', '70%', '40%']);
    });

    it('Needs review chip filters to cards with confidence < 0.5', async () => {
      const seeded = makeFixtureCards(MEETING_ID);
      vi.spyOn(client, 'listMeetingCards').mockResolvedValue({
        items: seeded,
        total: seeded.length,
      });
      const user = userEvent.setup();
      renderTab();
      await waitFor(() =>
        expect(screen.getAllByTestId('memory-card-item')).toHaveLength(4),
      );

      await user.click(screen.getByTestId('needs-review-chip'));

      // Only the pain_point fixture has confidence 0.4.
      await waitFor(() =>
        expect(screen.getAllByTestId('memory-card-item')).toHaveLength(1),
      );
      expect(
        screen.getByTestId('memory-card-confidence-pill'),
      ).toHaveTextContent('40%');
    });

    it('Needs review chip + no qualifying cards renders a friendly empty state', async () => {
      // All-confident fixture set.
      const seeded = makeFixtureCards(MEETING_ID).map((c) => ({
        ...c,
        confidence: 0.9,
      }));
      vi.spyOn(client, 'listMeetingCards').mockResolvedValue({
        items: seeded,
        total: seeded.length,
      });
      const user = userEvent.setup();
      renderTab();
      await waitFor(() =>
        expect(screen.getAllByTestId('memory-card-item')).toHaveLength(4),
      );
      await user.click(screen.getByTestId('needs-review-chip'));

      await waitFor(() => {
        expect(screen.queryAllByTestId('memory-card-item')).toHaveLength(0);
      });
      expect(screen.getByText(/no cards need review/i)).toBeInTheDocument();
    });
  });
});
