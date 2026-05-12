import type { MemoryCard } from '../api/memory_cards.types';
import { MemoryCardTypeIcon, memoryCardTypeLabel } from './MemoryCardTypeIcon';

/**
 * Phase-3 redesign: cards are agent-owned. The approve / reject / edit
 * action bar is gone, along with the state pill (the per-card state
 * machine no longer exists on the server). Evidence is the only
 * interaction surface that survives — clicking it scrolls the
 * Transcript tab to the cited segment with a 1.5s flash (Wave 3.1).
 *
 * Wave 3.2 — adds a confidence pill (red <0.5, yellow 0.5–0.8, green >0.8)
 * fed by the audit pass that runs as Stage 2 of `run_chunked_extraction`.
 */

type Props = {
  card: MemoryCard;
  meetingId: string;
  onEvidenceClick: (segmentId: string) => void;
};

type ConfidenceBucket = 'low' | 'medium' | 'high';

export function bucketConfidence(c: number): ConfidenceBucket {
  if (c < 0.5) return 'low';
  if (c <= 0.8) return 'medium';
  return 'high';
}

function confidencePillClass(bucket: ConfidenceBucket): string {
  switch (bucket) {
    case 'low':
      return 'rounded-full border border-red-300 bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700';
    case 'medium':
      return 'rounded-full border border-yellow-300 bg-yellow-50 px-2 py-0.5 text-xs font-medium text-yellow-800';
    case 'high':
      return 'rounded-full border border-green-300 bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700';
  }
}

export function MemoryCardItem({ card, onEvidenceClick }: Props) {
  const firstSegmentId = card.source_chunk_ids[0];
  const bucket = bucketConfidence(card.confidence ?? 1);
  const confidencePct = Math.round((card.confidence ?? 1) * 100);

  return (
    <article
      data-testid="memory-card-item"
      data-card-id={card.memory_card_id}
      data-confidence-bucket={bucket}
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
        <span
          data-testid="memory-card-confidence-pill"
          data-confidence-bucket={bucket}
          title={card.audit_reason ?? `Audit confidence: ${confidencePct}%`}
          className={confidencePillClass(bucket)}
        >
          {confidencePct}%
        </span>
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
          data-testid="memory-card-source-pill"
          onClick={() => onEvidenceClick(firstSegmentId)}
          title="Jump to the cited transcript segment"
          className="self-start rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs text-blue-700 hover:bg-blue-100"
        >
          View evidence
        </button>
      )}
    </article>
  );
}
