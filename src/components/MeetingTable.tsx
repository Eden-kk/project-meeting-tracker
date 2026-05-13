import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { StoredMeetingSummary } from '../lib/meetingsRegistry';
import { useWorkspace } from '../hooks/useWorkspace';
import { sourceLabel } from './SourceIcon';
import { StatusPill } from './StatusPill';
import { DeleteMeetingDialog } from './DeleteMeetingDialog';

type SortKey = 'title' | 'imported_at' | 'source_type' | 'detected_pattern' | 'status';
type SortDir = 'asc' | 'desc';

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'title', label: 'Title' },
  { key: 'imported_at', label: 'Date' },
  { key: 'source_type', label: 'Source' },
  { key: 'detected_pattern', label: 'Pattern' },
  { key: 'status', label: 'Status' },
];

function compare(a: StoredMeetingSummary, b: StoredMeetingSummary, key: SortKey, dir: SortDir): number {
  const av = a[key] ?? '';
  const bv = b[key] ?? '';
  const cmp = String(av).localeCompare(String(bv));
  return dir === 'asc' ? cmp : -cmp;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime()) || d.getTime() === 0) return '—';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function MeetingTable({ meetings }: { meetings: StoredMeetingSummary[] }) {
  const { workspaceId } = useWorkspace();
  const [sortKey, setSortKey] = useState<SortKey>('imported_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [confirmDelete, setConfirmDelete] = useState<StoredMeetingSummary | null>(null);

  const sorted = [...meetings].sort((a, b) => compare(a, b, sortKey, sortDir));

  function onHeaderClick(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  return (
    <>
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-gray-200 text-left text-xs uppercase text-gray-500">
          {COLUMNS.map((col) => (
            <th key={col.key} className="px-3 py-2 font-medium">
              <button
                type="button"
                onClick={() => onHeaderClick(col.key)}
                className="inline-flex items-center gap-1 hover:text-gray-900"
                aria-sort={sortKey === col.key ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
              >
                {col.label}
                {sortKey === col.key && <span aria-hidden="true">{sortDir === 'asc' ? '↑' : '↓'}</span>}
              </button>
            </th>
          ))}
          <th className="px-3 py-2" />
        </tr>
      </thead>
      <tbody>
        {sorted.map((m) => (
          <tr key={m.meeting_id} className="border-b border-gray-100 hover:bg-gray-50">
            <td className="px-3 py-2">
              <Link to={`/ws/${workspaceId}/meetings/${m.meeting_id}`} className="text-blue-700 hover:underline">
                {m.title}
              </Link>
            </td>
            <td className="px-3 py-2 text-gray-600">{formatDate(m.imported_at)}</td>
            <td className="px-3 py-2 text-gray-600">{sourceLabel(m.source_type)}</td>
            <td className="px-3 py-2 text-gray-600">{m.detected_pattern ?? '—'}</td>
            <td className="px-3 py-2"><StatusPill status={m.status} /></td>
            <td className="px-3 py-2 text-right">
              <button
                type="button"
                onClick={() => setConfirmDelete(m)}
                aria-label={`Delete ${m.title}`}
                className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
              >
                ⋮
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
    {confirmDelete && (
      <DeleteMeetingDialog
        meeting={{ id: confirmDelete.meeting_id, title: confirmDelete.title }}
        workspaceId={workspaceId}
        onClose={() => setConfirmDelete(null)}
        onDeleted={() => setConfirmDelete(null)}
      />
    )}
    </>
  );
}
