import { useState } from 'react';
import type { MemoryCard } from '../api/memory_cards.types';
import { MemoryCardTypeIcon, memoryCardTypeLabel } from './MemoryCardTypeIcon';

const STATE_STYLE: Record<MemoryCard['state'], string> = {
  draft: 'bg-amber-100 text-amber-800',
  committed: 'bg-green-100 text-green-800',
  rejected: 'bg-gray-200 text-gray-700',
};

const STATE_LABEL: Record<MemoryCard['state'], string> = {
  draft: 'Draft',
  committed: 'Committed',
  rejected: 'Rejected',
};

export type MemoryCardEditPayload = {
  title: string;
  content: string;
};

type Props = {
  card: MemoryCard;
  meetingId: string;
  onApprove: (cardId: string) => void;
  onReject: (cardId: string) => void;
  onEditClick: (cardId: string, patch: MemoryCardEditPayload) => void;
  onEvidenceClick: (segmentId: string) => void;
};

export function MemoryCardItem({
  card,
  onApprove,
  onReject,
  onEditClick,
  onEvidenceClick,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(card.title);
  const [draftContent, setDraftContent] = useState(card.content);

  const isDraft = card.state === 'draft';
  const firstSegmentId = card.source_chunk_ids[0];

  function startEdit() {
    setDraftTitle(card.title);
    setDraftContent(card.content);
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
  }

  function saveEdit() {
    onEditClick(card.memory_card_id, {
      title: draftTitle,
      content: draftContent,
    });
    setEditing(false);
  }

  return (
    <article
      data-testid="memory-card-item"
      data-card-id={card.memory_card_id}
      className="flex flex-col gap-2 rounded border border-gray-200 bg-white p-3 shadow-sm"
    >
      <header className="flex items-start gap-2">
        <MemoryCardTypeIcon type={card.type} />
        <div className="flex-1">
          {editing ? (
            <input
              aria-label="Card title"
              className="w-full rounded border border-gray-300 px-2 py-1 text-sm font-semibold"
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
            />
          ) : (
            <h3 className="text-sm font-semibold">{card.title}</h3>
          )}
          <div className="mt-0.5 text-xs uppercase tracking-wide text-gray-500">
            {memoryCardTypeLabel(card.type)}
          </div>
        </div>
        <span
          className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${STATE_STYLE[card.state]}`}
        >
          {STATE_LABEL[card.state]}
        </span>
      </header>

      {editing ? (
        <textarea
          aria-label="Card content"
          className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          rows={3}
          value={draftContent}
          onChange={(e) => setDraftContent(e.target.value)}
        />
      ) : (
        <p className="line-clamp-2 text-sm text-gray-700">{card.content}</p>
      )}

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

      {isDraft && (
        <div className="mt-1 flex gap-2">
          {editing ? (
            <>
              <button
                type="button"
                onClick={saveEdit}
                className="rounded bg-gray-900 px-3 py-1 text-xs text-white"
              >
                Save
              </button>
              <button
                type="button"
                onClick={cancelEdit}
                className="rounded border border-gray-300 px-3 py-1 text-xs"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => onApprove(card.memory_card_id)}
                className="rounded bg-green-600 px-3 py-1 text-xs text-white"
              >
                Approve
              </button>
              <button
                type="button"
                onClick={startEdit}
                className="rounded border border-gray-300 px-3 py-1 text-xs"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={() => onReject(card.memory_card_id)}
                className="rounded border border-red-300 px-3 py-1 text-xs text-red-700"
              >
                Reject
              </button>
            </>
          )}
        </div>
      )}
    </article>
  );
}
