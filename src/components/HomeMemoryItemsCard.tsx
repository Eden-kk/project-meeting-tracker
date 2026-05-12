import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type {
  ActionItemRow,
  ListActionItemsParams,
  MemoryCardType,
} from '../api/memory_cards.types';
import type { listActionItems } from '../api/client';
import type { queryKeys } from '../api/queryKeys';
import { DEV_WORKSPACE_ID } from '../lib/constants';
import { EmptyState } from './EmptyState';

const HOME_LIMIT = 8;

type Props = {
  type: MemoryCardType;
  title: string;
  dashboardHref: string;
  emptyTitle: string;
  emptyBody: string;
  queryFn: typeof listActionItems;
  queryKey:
    | typeof queryKeys.actionItems
    | typeof queryKeys.openQuestions;
};

/** Compact Home-page card listing the top outstanding items of one
 *  memory-card type. Click a row → navigate to the source meeting at the
 *  cited segment anchor (`#seg:<chunk_id>`); click the header → open the
 *  full dashboard.
 *
 *  Pure teaser surface — no completion / dismissal / filtering. The
 *  dashboard pages own those interactions.
 */
export function HomeMemoryItemsCard({
  type: _type,
  title,
  dashboardHref,
  emptyTitle,
  emptyBody,
  queryFn,
  queryKey,
}: Props) {
  const params: ListActionItemsParams = {
    workspace_id: DEV_WORKSPACE_ID,
    limit: HOME_LIMIT,
  };

  const { data, isLoading, isError } = useQuery({
    queryKey: queryKey(params),
    queryFn: () => queryFn(params),
  });

  const items = data?.items ?? [];

  return (
    <div
      className="rounded border border-gray-200 bg-white p-4"
      data-testid={`home-memory-card-${_type}`}
    >
      <header className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
          {title}
        </h2>
        <Link
          to={dashboardHref}
          className="text-xs font-medium text-gray-700 hover:underline"
        >
          View all →
        </Link>
      </header>

      {isLoading ? (
        <ul className="space-y-2" aria-label="Loading">
          {Array.from({ length: 3 }).map((_, i) => (
            <li
              key={i}
              className="h-10 animate-pulse rounded bg-gray-50"
            />
          ))}
        </ul>
      ) : isError ? (
        <p className="text-sm text-gray-500">Couldn’t load {title.toLowerCase()}.</p>
      ) : items.length === 0 ? (
        <EmptyState
          title={emptyTitle}
          body={emptyBody}
          cta={{ to: '/import', label: 'Import a meeting' }}
        />
      ) : (
        <ul className="divide-y divide-gray-100">
          {items.map((row) => (
            <HomeMemoryItemRow key={row.memory_card_id} row={row} />
          ))}
        </ul>
      )}
    </div>
  );
}

function HomeMemoryItemRow({ row }: { row: ActionItemRow }) {
  const segId = row.source_chunk_ids[0];
  const href = segId
    ? `/meetings/${row.meeting_id}#seg:${segId}`
    : `/meetings/${row.meeting_id}`;
  const display = row.title?.trim() || excerpt(row.content);
  const meta = [
    row.meeting_title || row.meeting_id,
    formatRelative(row.meeting_finalized_at ?? row.created_at ?? null),
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <li className="py-2">
      <Link to={href} className="block hover:bg-gray-50">
        <p className="line-clamp-2 text-sm font-medium text-gray-900">{display}</p>
        <p className="truncate text-xs text-gray-500">{meta}</p>
      </Link>
    </li>
  );
}

function excerpt(s: string | null | undefined, n = 80): string {
  if (!s) return '(untitled)';
  const t = s.trim();
  if (t.length <= n) return t;
  return t.slice(0, n).trimEnd() + '…';
}

/** Tiny relative-time formatter; falls back to locale date past 14 days,
 *  and to em-dash on null. No date-fns dependency. */
export function formatRelative(iso: string | null): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const diff = Date.now() - then;
  const min = 60_000;
  const hour = 60 * min;
  const day = 24 * hour;
  if (diff < min) return 'just now';
  if (diff < hour) return `${Math.floor(diff / min)} min ago`;
  if (diff < day) return `${Math.floor(diff / hour)} hours ago`;
  if (diff < 14 * day) return `${Math.floor(diff / day)} days ago`;
  return new Date(iso).toLocaleDateString();
}
