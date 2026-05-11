import { useState } from 'react';
import { useMeetingCards } from '../hooks/useMeetingCards';
import { EmptyState } from './EmptyState';
import { FollowupDraftDialog } from './FollowupDraftDialog';
import { MemoryCardFilters, type CardFilters } from './MemoryCardFilters';
import { MemoryCardItem } from './MemoryCardItem';

type Props = {
  meetingId: string;
  onEvidenceClick: (segmentId: string) => void;
};

/**
 * Phase-3 redesign: read-only card grid. The approve / reject / edit
 * mutations were removed along with the per-card state machine (the
 * agent owns quality via audit + consolidation passes shipped in 2.1
 * and 2.2).
 *
 * Wave 5.3 adds the "Draft follow-up" button which opens
 * FollowupDraftDialog — a Hermes-backed markdown drafter.
 */
export function MemoryCardsTab({ meetingId, onEvidenceClick }: Props) {
  const [filters, setFilters] = useState<CardFilters>({});
  const [followupOpen, setFollowupOpen] = useState(false);
  const cards = useMeetingCards(meetingId, filters);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <MemoryCardFilters value={filters} onChange={setFilters} />
        <button
          type="button"
          onClick={() => setFollowupOpen(true)}
          className="rounded border border-gray-300 px-3 py-1 text-xs hover:bg-gray-50"
        >
          Draft follow-up
        </button>
      </div>

      <FollowupDraftDialog
        meetingId={meetingId}
        open={followupOpen}
        onClose={() => setFollowupOpen(false)}
      />

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
              onEvidenceClick={onEvidenceClick}
            />
          ))}
        </div>
      )}
    </div>
  );
}
