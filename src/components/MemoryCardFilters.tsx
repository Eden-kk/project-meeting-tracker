import type { MemoryCardType } from '../api/memory_cards.types';
import { memoryCardTypeLabel } from './MemoryCardTypeIcon';

/**
 * Phase-3 redesign: the per-card state machine was removed, so the
 * "Draft / Committed / Rejected" state pills are gone. Type filter
 * survives.
 *
 * Wave 3.2 — adds a "Needs review" chip that surfaces cards with
 * `confidence < 0.5` (the audit pass already wrote real values by the
 * time this lands). Filtering is client-side; the chip is independent
 * of the type filter and additive.
 */

export type CardFilters = {
  type?: MemoryCardType;
  /** Wave 3.2 — when true, only show cards with confidence < 0.5. */
  needsReview?: boolean;
};

const TYPES: MemoryCardType[] = [
  'decision',
  'action_item',
  'pain_point',
  'quote',
  'requirement',
  'risk',
  'open_question',
  'technical_detail',
];

type Props = {
  value: CardFilters;
  onChange: (next: CardFilters) => void;
};

function pillClass(active: boolean): string {
  return active
    ? 'rounded-full bg-gray-900 px-3 py-1 text-xs font-medium text-white'
    : 'rounded-full border border-gray-300 bg-white px-3 py-1 text-xs text-gray-700';
}

function reviewPillClass(active: boolean): string {
  return active
    ? 'rounded-full bg-red-600 px-3 py-1 text-xs font-medium text-white'
    : 'rounded-full border border-red-300 bg-red-50 px-3 py-1 text-xs text-red-700 hover:bg-red-100';
}

export function MemoryCardFilters({ value, onChange }: Props) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-gray-500">Type</span>
        <button
          type="button"
          className={pillClass(value.type === undefined)}
          onClick={() => onChange({ ...value, type: undefined })}
        >
          All
        </button>
        {TYPES.map((t) => (
          <button
            key={t}
            type="button"
            className={pillClass(value.type === t)}
            onClick={() => onChange({ ...value, type: t })}
          >
            {memoryCardTypeLabel(t)}
          </button>
        ))}
        <button
          type="button"
          data-testid="needs-review-chip"
          aria-pressed={value.needsReview ? 'true' : 'false'}
          className={reviewPillClass(Boolean(value.needsReview))}
          onClick={() => onChange({ ...value, needsReview: !value.needsReview })}
          title="Cards with audit confidence below 50%"
        >
          Needs review
        </button>
      </div>
    </div>
  );
}
