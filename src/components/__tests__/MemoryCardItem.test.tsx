import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryCardItem } from '../MemoryCardItem';
import type { MemoryCard } from '../../api/memory_cards.types';

function makeCard(overrides: Partial<MemoryCard> = {}): MemoryCard {
  return {
    memory_card_id: 'mc_1',
    meeting_id: 'm_1',
    type: 'decision',
    title: 'Adopt new auth migration timeline',
    content: 'The team agreed to ship the auth migration by end of Q1.',
    speakers: ['Alice'],
    source_chunk_ids: ['seg_001'],
    confidence: 0.9,
    audit_reason: null,
    hidden_at: null,
    superseded_by_id: null,
    created_at: '2025-01-15T10:00:00.000Z',
    updated_at: '2025-01-15T10:00:00.000Z',
    ...overrides,
  };
}

function renderItem(card: MemoryCard) {
  const onEvidenceClick = vi.fn();
  render(
    <MemoryCardItem
      card={card}
      meetingId="m_1"
      onEvidenceClick={onEvidenceClick}
    />,
  );
  return { onEvidenceClick };
}

describe('MemoryCardItem (Phase-3, read-only)', () => {
  it('renders title, content, and the type icon', () => {
    renderItem(makeCard());
    expect(screen.getByText(/adopt new auth migration timeline/i)).toBeInTheDocument();
    expect(screen.getByText(/end of q1/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/decision/i)).toBeInTheDocument();
  });

  it('does NOT render the legacy approve / reject / edit buttons', () => {
    renderItem(makeCard());
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^edit$/i })).not.toBeInTheDocument();
  });

  it('does NOT render a state pill (the per-card state machine is gone)', () => {
    renderItem(makeCard());
    expect(screen.queryByText(/^draft$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^committed$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^rejected$/i)).not.toBeInTheDocument();
  });

  it('Evidence button fires onEvidenceClick with the first source chunk id', async () => {
    const user = userEvent.setup();
    const { onEvidenceClick } = renderItem(
      makeCard({ source_chunk_ids: ['seg_042', 'seg_099'] }),
    );
    await user.click(screen.getByRole('button', { name: /view evidence/i }));
    expect(onEvidenceClick).toHaveBeenCalledWith('seg_042');
  });

  describe('Wave 3.2 — confidence pill', () => {
    it('renders a green pill when confidence > 0.8', () => {
      renderItem(makeCard({ confidence: 0.92 }));
      const pill = screen.getByTestId('memory-card-confidence-pill');
      expect(pill).toHaveAttribute('data-confidence-bucket', 'high');
      expect(pill).toHaveTextContent('92%');
    });

    it('renders a yellow pill when confidence is in [0.5, 0.8]', () => {
      renderItem(makeCard({ confidence: 0.65 }));
      const pill = screen.getByTestId('memory-card-confidence-pill');
      expect(pill).toHaveAttribute('data-confidence-bucket', 'medium');
      expect(pill).toHaveTextContent('65%');
    });

    it('renders a red pill when confidence < 0.5 and exposes audit_reason as the tooltip', () => {
      renderItem(
        makeCard({ confidence: 0.3, audit_reason: 'Single anecdote; no metric cited.' }),
      );
      const pill = screen.getByTestId('memory-card-confidence-pill');
      expect(pill).toHaveAttribute('data-confidence-bucket', 'low');
      expect(pill).toHaveTextContent('30%');
      expect(pill).toHaveAttribute('title', 'Single anecdote; no metric cited.');
    });
  });
});
