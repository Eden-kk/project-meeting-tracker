import { Link } from 'react-router-dom';
import type { StoredMeetingSummary } from '../lib/meetingsRegistry';
import { SourceIcon } from './SourceIcon';
import { StatusPill } from './StatusPill';

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime()) || d.getTime() === 0) return '—';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function MeetingCard({ meeting }: { meeting: StoredMeetingSummary }) {
  return (
    <Link
      to={`/meetings/${meeting.meeting_id}`}
      className="block rounded border border-gray-200 p-4 transition hover:border-gray-400"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="line-clamp-2 text-sm font-semibold">{meeting.title}</h3>
        <StatusPill status={meeting.status} />
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs text-gray-600">
        <SourceIcon sourceType={meeting.source_type} />
        <span>{formatDate(meeting.imported_at)}</span>
        {meeting.detected_pattern && (
          <span className="rounded bg-gray-100 px-2 py-0.5">{meeting.detected_pattern}</span>
        )}
      </div>
    </Link>
  );
}
