import { useState } from 'react';
import {
  useCommitCard,
  useMeetingCards,
  usePatchCard,
  useRejectCard,
} from '../hooks/useMeetingCards';
import { EmptyState } from './EmptyState';
import { MemoryCardFilters, type CardFilters } from './MemoryCardFilters';
import { MemoryCardItem, type MemoryCardEditPayload } from './MemoryCardItem';

type Props = {
  meetingId: string;
  onEvidenceClick: (segmentId: string) => void;
};

export function MemoryCardsTab({ meetingId, onEvidenceClick }: Props) {
  const [filters, setFilters] = useState<CardFilters>({});
  const cards = useMeetingCards(meetingId, filters);
  const commit = useCommitCard(meetingId);
  const reject = useRejectCard(meetingId);
  const patch = usePatchCard(meetingId);

  const mutationError = commit.isError || reject.isError || patch.isError;

  function handleEdit(cardId: string, payload: MemoryCardEditPayload) {
    patch.mutate({ cardId, patch: payload });
  }

  return (
    <div className="space-y-3">
      <MemoryCardFilters value={filters} onChange={setFilters} />

      {mutationError && (
        <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
          Card update failed. Try again.
        </div>
      )}

      {cards.isLoading && <p className="text-sm text-gray-500">Loading cards…</p>}
      {cards.isError && (
        <p className="text-sm text-red-700">Failed to load memory cards.</p>
      )}

      {cards.data && cards.data.items.length === 0 && (
        <EmptyState
          title="No memory cards yet"
          body="Cards will appear here once extraction completes."
        />
      )}

      {cards.data && cards.data.items.length > 0 && (
        <div
          className="grid gap-3 sm:grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
          data-testid="memory-card-grid"
        >
          {cards.data.items.map((card) => (
            <MemoryCardItem
              key={card.memory_card_id}
              card={card}
              meetingId={meetingId}
              onApprove={(id) => commit.mutate(id)}
              onReject={(id) => reject.mutate(id)}
              onEditClick={handleEdit}
              onEvidenceClick={onEvidenceClick}
            />
          ))}
        </div>
      )}
    </div>
  );
}
