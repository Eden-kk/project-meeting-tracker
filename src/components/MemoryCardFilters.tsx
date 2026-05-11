import type { MemoryCardType } from '../api/memory_cards.types';
import { memoryCardTypeLabel } from './MemoryCardTypeIcon';

/**
 * Phase-3 redesign: the per-card state machine was removed, so the
 * "Draft / Committed / Rejected" state pills are gone. Only the type
 * filter survives.
 */

export type CardFilters = {
  type?: MemoryCardType;
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
      </div>
    </div>
  );
}
