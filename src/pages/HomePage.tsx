import { Link } from 'react-router-dom';
import { useMeetings } from '../hooks/useMeetings';
import { MeetingCard } from '../components/MeetingCard';
import { StatChip } from '../components/StatChip';
import { EmptyState } from '../components/EmptyState';
import { sourceLabel } from '../components/SourceIcon';
import type { StoredMeetingSummary } from '../lib/meetingsRegistry';

const RECENT_LIMIT = 6;

function readyCount(meetings: StoredMeetingSummary[]): number {
  return meetings.filter((m) => m.status === 'ready' || m.status === 'live' || m.status === 'finalized').length;
}

function processingCount(meetings: StoredMeetingSummary[]): number {
  return meetings.filter((m) => m.status === 'processing').length;
}

function failedCount(meetings: StoredMeetingSummary[]): number {
  return meetings.filter((m) => m.status === 'failed').length;
}

function topSource(meetings: StoredMeetingSummary[]): string {
  if (meetings.length === 0) return '—';
  const counts = new Map<StoredMeetingSummary['source_type'], number>();
  for (const m of meetings) counts.set(m.source_type, (counts.get(m.source_type) ?? 0) + 1);
  let best: StoredMeetingSummary['source_type'] | null = null;
  let bestN = -1;
  for (const [k, v] of counts) {
    if (v > bestN) {
      best = k;
      bestN = v;
    }
  }
  return best ? sourceLabel(best) : '—';
}

export default function HomePage() {
  const { meetings } = useMeetings();
  // Server already returns newest-first; preserve that order. For
  // registry-only entries appended on the end, secondary sort by
  // imported_at keeps recently-imported drafts near the top.
  const recent = meetings.slice(0, RECENT_LIMIT);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Home</h1>
        <Link to="/import" className="rounded bg-gray-900 px-4 py-2 text-sm text-white">
          New import
        </Link>
      </header>

      {meetings.length === 0 ? (
        <EmptyState
          title="No meetings yet"
          body="Import a transcript or audio file to get started."
          cta={{ to: '/import', label: 'Import' }}
        />
      ) : (
        <>
          <section aria-label="Stats" className="grid gap-3 sm:grid-cols-3">
            <StatChip label="Total" value={meetings.length} />
            <StatChip
              label="Ready / Processing / Failed"
              value={`${readyCount(meetings)} / ${processingCount(meetings)} / ${failedCount(meetings)}`}
            />
            <StatChip label="Top source" value={topSource(meetings)} />
          </section>

          <section aria-label="Recent meetings">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">Recent meetings</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {recent.map((m) => (
                <MeetingCard key={m.meeting_id} meeting={m} />
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
