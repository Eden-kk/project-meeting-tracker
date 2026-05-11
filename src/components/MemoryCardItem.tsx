import type { MemoryCard } from '../api/memory_cards.types';
import { MemoryCardTypeIcon, memoryCardTypeLabel } from './MemoryCardTypeIcon';

/**
 * Phase-3 redesign: cards are agent-owned. The approve / reject / edit
 * action bar is gone, along with the state pill (the per-card state
 * machine no longer exists on the server). Evidence is the only
 * interaction surface that survives — clicking it scrolls the
 * Transcript tab to the cited segment (3.1 will animate the highlight).
 */

type Props = {
  card: MemoryCard;
  meetingId: string;
  onEvidenceClick: (segmentId: string) => void;
};

export function MemoryCardItem({ card, onEvidenceClick }: Props) {
  const firstSegmentId = card.source_chunk_ids[0];

  return (
    <article
      data-testid="memory-card-item"
      data-card-id={card.memory_card_id}
      className="flex flex-col gap-2 rounded border border-gray-200 bg-white p-3 shadow-sm"
    >
      <header className="flex items-start gap-2">
        <MemoryCardTypeIcon type={card.type} />
        <div className="flex-1">
          <h3 className="text-sm font-semibold">{card.title}</h3>
          <div className="mt-0.5 text-xs uppercase tracking-wide text-gray-500">
            {memoryCardTypeLabel(card.type)}
          </div>
        </div>
      </header>

      <p className="line-clamp-2 text-sm text-gray-700">{card.content}</p>

      {card.speakers.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {card.speakers.map((s) => (
            <span
              key={s}
              className="inline-block rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700"
            >
              {s}
            </span>
          ))}
        </div>
      )}

      {firstSegmentId && (
        <button
          type="button"
          onClick={() => onEvidenceClick(firstSegmentId)}
          className="self-start text-xs text-blue-600 underline"
        >
          View evidence
        </button>
      )}
    </article>
  );
}
