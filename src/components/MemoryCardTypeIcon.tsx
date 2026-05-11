import type { MemoryCardType } from '../api/memory_cards.types';

const GLYPH: Record<MemoryCardType, string> = {
  decision: '✔',
  action_item: '↱',
  pain_point: '⚠',
  quote: '“',
  requirement: '■',
  risk: '⚡',
  open_question: '?',
  technical_detail: '⚙',
};

const COLOR: Record<MemoryCardType, string> = {
  decision: 'text-blue-600',
  action_item: 'text-blue-600',
  pain_point: 'text-red-600',
  quote: 'text-gray-600',
  requirement: 'text-gray-800',
  risk: 'text-orange-600',
  open_question: 'text-purple-600',
  technical_detail: 'text-slate-600',
};

const LABEL: Record<MemoryCardType, string> = {
  decision: 'Decision',
  action_item: 'Action item',
  pain_point: 'Pain point',
  quote: 'Quote',
  requirement: 'Requirement',
  risk: 'Risk',
  open_question: 'Open question',
  technical_detail: 'Technical detail',
};

export function memoryCardTypeLabel(type: MemoryCardType): string {
  return LABEL[type];
}

export function MemoryCardTypeIcon({ type }: { type: MemoryCardType }) {
  return (
    <span
      className={`inline-block text-lg leading-none ${COLOR[type]}`}
      aria-label={LABEL[type]}
      role="img"
    >
      {GLYPH[type]}
    </span>
  );
}
