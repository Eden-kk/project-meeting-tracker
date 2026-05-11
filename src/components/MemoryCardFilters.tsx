import type { MemoryCardState, MemoryCardType } from '../api/memory_cards.types';
import { memoryCardTypeLabel } from './MemoryCardTypeIcon';

export type CardFilters = {
  state?: MemoryCardState;
  type?: MemoryCardType;
};

const STATES: MemoryCardState[] = ['draft', 'committed', 'rejected'];
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

const STATE_LABEL: Record<MemoryCardState, string> = {
  draft: 'Draft',
  committed: 'Committed',
  rejected: 'Rejected',
};

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
        <span className="text-xs uppercase tracking-wide text-gray-500">State</span>
        <button
          type="button"
          className={pillClass(value.state === undefined)}
          onClick={() => onChange({ ...value, state: undefined })}
        >
          All
        </button>
        {STATES.map((s) => (
          <button
            key={s}
            type="button"
            className={pillClass(value.state === s)}
            onClick={() => onChange({ ...value, state: s })}
          >
            {STATE_LABEL[s]}
          </button>
        ))}
      </div>
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
