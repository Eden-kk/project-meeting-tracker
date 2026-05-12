import { Link } from 'react-router-dom';
import type { ActionItemRow } from '../api/memory_cards.types';
import { useWorkspace } from '../hooks/useWorkspace';

type Props = {
  rows: ActionItemRow[];
  /** Empty-state message shown when `rows` is empty after filtering. */
  emptyMessage?: string;
};

/** Shared table component for the cross-meeting dashboards (5.1 + 5.2).
 *
 * Reused by both /action-items and /open-questions; rendering is the
 * same shape — only the upstream type filter and page title differ.
 */
export function ActionItemsTable({ rows, emptyMessage = 'No items.' }: Props) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-500">{emptyMessage}</p>;
  }
  return (
    <div className="overflow-x-auto rounded border border-gray-200">
      <table className="min-w-full text-sm" data-testid="action-items-table">
        <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
          <tr>
            <th className="px-3 py-2">Title</th>
            <th className="px-3 py-2">Speaker</th>
            <th className="px-3 py-2">Meeting</th>
            <th className="px-3 py-2">Finalized</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <ActionItemRowView key={r.memory_card_id} row={r} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ActionItemRowView({ row }: { row: ActionItemRow }) {
  const { workspaceId } = useWorkspace();
  // Anchor `#seg:<segment_id>` matches the transcript-tab scroll target
  // shipped by Phase-2.5 (see TranscriptView). Fall back to first
  // source_chunk_id when source_start_ms is not addressable.
  const segId = row.source_chunk_ids[0];
  const meetingBase = `/ws/${workspaceId}/meetings/${row.meeting_id}`;
  const href = segId ? `${meetingBase}#seg:${segId}` : meetingBase;
  const speaker = (row.speakers_json ?? []).join(', ') || '—';
  const finalized = row.meeting_finalized_at
    ? new Date(row.meeting_finalized_at).toLocaleString()
    : '—';
  return (
    <tr className="border-t border-gray-100 hover:bg-gray-50">
      <td className="px-3 py-2">
        <Link to={href} className="font-medium text-gray-900 hover:underline">
          {row.title}
        </Link>
        {row.content && (
          <p className="mt-1 text-xs text-gray-500 line-clamp-2">{row.content}</p>
        )}
      </td>
      <td className="px-3 py-2 text-gray-700">{speaker}</td>
      <td className="px-3 py-2">
        <Link to={meetingBase} className="text-gray-700 hover:underline">
          {row.meeting_title || row.meeting_id}
        </Link>
      </td>
      <td className="px-3 py-2 text-gray-500">{finalized}</td>
    </tr>
  );
}
