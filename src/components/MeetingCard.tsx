import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { StoredMeetingSummary } from '../lib/meetingsRegistry';
import { useWorkspace } from '../hooks/useWorkspace';
import { SourceIcon } from './SourceIcon';
import { StatusPill } from './StatusPill';
import { DeleteMeetingDialog } from './DeleteMeetingDialog';

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime()) || d.getTime() === 0) return '—';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function MeetingCard({ meeting }: { meeting: StoredMeetingSummary }) {
  const { workspaceId } = useWorkspace();
  const [showDelete, setShowDelete] = useState(false);
  return (
    <>
      <Link
        to={`/ws/${workspaceId}/meetings/${meeting.meeting_id}`}
        className="block rounded border border-gray-200 p-4 transition hover:border-gray-400"
      >
        <div className="flex items-start justify-between gap-2">
          <h3 className="line-clamp-2 flex-1 text-sm font-semibold">{meeting.title}</h3>
          <div className="flex shrink-0 items-center gap-1">
            <StatusPill status={meeting.status} />
            <button
              type="button"
              aria-label={`Delete ${meeting.title}`}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setShowDelete(true);
              }}
              className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            >
              ⋮
            </button>
          </div>
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs text-gray-600">
          <SourceIcon sourceType={meeting.source_type} />
          <span>{formatDate(meeting.imported_at)}</span>
          {meeting.detected_pattern && (
            <span className="rounded bg-gray-100 px-2 py-0.5">{meeting.detected_pattern}</span>
          )}
        </div>
      </Link>
      {showDelete && (
        <DeleteMeetingDialog
          meeting={{ id: meeting.meeting_id, title: meeting.title }}
          workspaceId={workspaceId}
          onClose={() => setShowDelete(false)}
          onDeleted={() => setShowDelete(false)}
        />
      )}
    </>
  );
}
