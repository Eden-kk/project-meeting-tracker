import { useMemo, useState } from 'react';
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
 * Wave 3.2 — sorts cards by confidence desc by default and applies the
 * client-side "Needs review" filter (confidence < 0.5). Both are kept
 * client-side per plan; the server still returns the canonical visible
 * set ordered by created_at.
 *
 * Wave 5.3 adds the "Draft follow-up" button which opens
 * FollowupDraftDialog — a Hermes-backed markdown drafter.
 */
export function MemoryCardsTab({ meetingId, onEvidenceClick }: Props) {
  const [filters, setFilters] = useState<CardFilters>({});
  const [followupOpen, setFollowupOpen] = useState(false);
  // Only forward server-side filters (type) to the API; keep client-side
  // chips like needsReview out of the query key so they don't trigger
  // refetches.
  const cards = useMeetingCards(meetingId, { type: filters.type });

  const visibleCards = useMemo(() => {
    if (!cards.data) return [];
    let items = cards.data.items;
    if (filters.needsReview) {
      items = items.filter((c) => (c.confidence ?? 1) < 0.5);
    }
    // Sort by confidence desc; treat missing confidence as 1 (server-default
    // for old rows pre-audit-pass) so they sort to the top alongside strong
    // cards. Stable on `created_at` desc as a tiebreak.
    return [...items].sort((a, b) => {
      const dc = (b.confidence ?? 1) - (a.confidence ?? 1);
      if (dc !== 0) return dc;
      return (b.created_at ?? '').localeCompare(a.created_at ?? '');
    });
  }, [cards.data, filters.needsReview]);

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

      {cards.data && visibleCards.length === 0 && (
        <EmptyState
          title={filters.needsReview ? 'No cards need review' : 'No memory cards yet'}
          body={
            filters.needsReview
              ? 'All extracted cards are above the audit confidence threshold.'
              : 'Cards will appear here once extraction completes.'
          }
        />
      )}

      {cards.data && visibleCards.length > 0 && (
        <div
          className="grid gap-3 sm:grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
          data-testid="memory-card-grid"
        >
          {visibleCards.map((card) => (
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
