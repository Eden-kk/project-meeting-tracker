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
    state: 'draft',
    title: 'Adopt new auth migration timeline',
    content: 'The team agreed to ship the auth migration by end of Q1.',
    speakers: ['Alice'],
    source_chunk_ids: ['seg_001'],
    created_at: '2025-01-15T10:00:00.000Z',
    updated_at: '2025-01-15T10:00:00.000Z',
    ...overrides,
  };
}

function renderItem(card: MemoryCard) {
  const onApprove = vi.fn();
  const onReject = vi.fn();
  const onEditClick = vi.fn();
  const onEvidenceClick = vi.fn();
  render(
    <MemoryCardItem
      card={card}
      meetingId="m_1"
      onApprove={onApprove}
      onReject={onReject}
      onEditClick={onEditClick}
      onEvidenceClick={onEvidenceClick}
    />,
  );
  return { onApprove, onReject, onEditClick, onEvidenceClick };
}

describe('MemoryCardItem', () => {
  it('renders title, content, and the type icon', () => {
    renderItem(makeCard());
    expect(screen.getByText(/adopt new auth migration timeline/i)).toBeInTheDocument();
    expect(screen.getByText(/end of q1/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/decision/i)).toBeInTheDocument();
  });

  it('renders the action bar for draft cards but not for committed cards', () => {
    const { rerender } = render(
      <MemoryCardItem
        card={makeCard()}
        meetingId="m_1"
        onApprove={() => {}}
        onReject={() => {}}
        onEditClick={() => {}}
        onEvidenceClick={() => {}}
      />,
    );
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    rerender(
      <MemoryCardItem
        card={makeCard({ state: 'committed' })}
        meetingId="m_1"
        onApprove={() => {}}
        onReject={() => {}}
        onEditClick={() => {}}
        onEvidenceClick={() => {}}
      />,
    );
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
  });

  it('Approve fires onApprove with the card id', async () => {
    const user = userEvent.setup();
    const { onApprove } = renderItem(makeCard());
    await user.click(screen.getByRole('button', { name: /approve/i }));
    expect(onApprove).toHaveBeenCalledWith('mc_1');
  });

  it('Edit then Save fires onEditClick with the patch payload', async () => {
    const user = userEvent.setup();
    const { onEditClick } = renderItem(makeCard());
    await user.click(screen.getByRole('button', { name: /^edit$/i }));
    const titleInput = screen.getByLabelText(/card title/i);
    await user.clear(titleInput);
    await user.type(titleInput, 'New title');
    const contentInput = screen.getByLabelText(/card content/i);
    await user.clear(contentInput);
    await user.type(contentInput, 'New content');
    await user.click(screen.getByRole('button', { name: /save/i }));
    expect(onEditClick).toHaveBeenCalledWith('mc_1', {
      title: 'New title',
      content: 'New content',
    });
  });

  it('Evidence button fires onEvidenceClick with the first source chunk id', async () => {
    const user = userEvent.setup();
    const { onEvidenceClick } = renderItem(
      makeCard({ source_chunk_ids: ['seg_042', 'seg_099'] }),
    );
    await user.click(screen.getByRole('button', { name: /view evidence/i }));
    expect(onEvidenceClick).toHaveBeenCalledWith('seg_042');
  });
});
