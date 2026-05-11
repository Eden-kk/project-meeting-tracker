import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { LiveDraftCardsPanel } from '../LiveDraftCardsPanel';
import * as client from '../../api/client';
import type { MemoryCard } from '../../api/memory_cards.types';

function makeCard(overrides: Partial<MemoryCard> = {}): MemoryCard {
  return {
    memory_card_id: 'mc_a',
    meeting_id: 'm_live_1',
    type: 'decision',
    title: 'Ship by Friday',
    content: 'Bob proposed and Alice agreed.',
    speakers: ['Alice', 'Bob'],
    source_chunk_ids: ['seg_b', 'seg_c'],
    hidden_at: null,
    superseded_by_id: null,
    created_at: '2026-05-11T12:00:00.000Z',
    updated_at: '2026-05-11T12:00:00.000Z',
    ...overrides,
  };
}

describe('LiveDraftCardsPanel (Wave 6.4)', () => {
  // The mock signature is intentionally widened — vitest's spyOn type
  // narrows too aggressively for the (string, string|null|undefined)
  // overload on listLiveDraftCards.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let listSpy: any;

  beforeEach(() => {
    // Only fake setInterval/clearInterval so React Testing Library's
    // ``waitFor`` (which uses setTimeout under the hood) keeps working.
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    listSpy = vi.spyOn(client, 'listLiveDraftCards');
  });

  afterEach(() => {
    vi.useRealTimers();
    listSpy.mockRestore();
  });

  it('shows the empty placeholder when active and no cards yet', async () => {
    listSpy.mockResolvedValue({
      meeting_id: 'm_live_1',
      status: 'live',
      items: [],
    });
    render(<LiveDraftCardsPanel meetingId="m_live_1" active={true} />);
    // Initial poll fires synchronously inside the effect.
    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/will start producing draft cards/i)).toBeInTheDocument();
    expect(screen.getByText(/0 so far/)).toBeInTheDocument();
  });

  it('shows the inactive placeholder when not recording', () => {
    render(<LiveDraftCardsPanel meetingId={null} active={false} />);
    expect(listSpy).not.toHaveBeenCalled();
    expect(screen.getByText(/start the meeting/i)).toBeInTheDocument();
  });

  it('renders cards returned by the polling endpoint', async () => {
    listSpy.mockResolvedValueOnce({
      meeting_id: 'm_live_1',
      status: 'live',
      items: [makeCard()],
    });
    render(<LiveDraftCardsPanel meetingId="m_live_1" active={true} />);
    await waitFor(() => {
      expect(screen.getByText(/ship by friday/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/1 so far/)).toBeInTheDocument();
  });

  it('passes the latest created_at as since_iso on subsequent polls', async () => {
    listSpy
      .mockResolvedValueOnce({
        meeting_id: 'm_live_1',
        status: 'live',
        items: [makeCard({ memory_card_id: 'mc_a', created_at: '2026-05-11T12:00:00.000Z' })],
      })
      .mockResolvedValueOnce({
        meeting_id: 'm_live_1',
        status: 'live',
        items: [
          makeCard({
            memory_card_id: 'mc_b',
            title: 'Second card',
            created_at: '2026-05-11T12:02:00.000Z',
          }),
        ],
      });

    render(<LiveDraftCardsPanel meetingId="m_live_1" active={true} />);
    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(1));
    // First poll: no since_iso.
    expect(listSpy.mock.calls[0]).toEqual(['m_live_1', null]);

    // Advance by the 5s polling interval.
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(2));
    // Second poll: since_iso = first card's created_at.
    expect(listSpy.mock.calls[1]).toEqual([
      'm_live_1',
      '2026-05-11T12:00:00.000Z',
    ]);

    await waitFor(() => {
      expect(screen.getByText(/second card/i)).toBeInTheDocument();
    });
    // Both cards should be on screen.
    expect(screen.getByText(/ship by friday/i)).toBeInTheDocument();
    expect(screen.getByText(/2 so far/)).toBeInTheDocument();
  });

  it('surfaces poll errors without removing prior cards', async () => {
    listSpy
      .mockResolvedValueOnce({
        meeting_id: 'm_live_1',
        status: 'live',
        items: [makeCard()],
      })
      .mockRejectedValueOnce(new Error('network down'));

    render(<LiveDraftCardsPanel meetingId="m_live_1" active={true} />);
    await waitFor(() => expect(screen.getByText(/ship by friday/i)).toBeInTheDocument());
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    await waitFor(() => {
      expect(screen.getByTestId('live-cards-error')).toHaveTextContent(/network down/i);
    });
    // Card stays on screen.
    expect(screen.getByText(/ship by friday/i)).toBeInTheDocument();
  });
});
