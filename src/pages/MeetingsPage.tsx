import { useMemo, useState } from 'react';
import { useMeetings } from '../hooks/useMeetings';
import { MeetingCard } from '../components/MeetingCard';
import { MeetingTable } from '../components/MeetingTable';
import { EmptyState } from '../components/EmptyState';
import { sourceLabel } from '../components/SourceIcon';
import type { StoredMeetingSummary } from '../lib/meetingsRegistry';

const SOURCE_TYPES: StoredMeetingSummary['source_type'][] = [
  'voice_file',
  'transcript_file',
  'pasted_transcript',
  'live_voice',
  'zoom_rtms',
];
const STATUSES: StoredMeetingSummary['status'][] = ['live', 'processing', 'ready', 'finalized', 'failed'];

type View = 'table' | 'cards';

function chipClass(active: boolean): string {
  const base = 'rounded-full border px-3 py-1 text-xs';
  return active ? `${base} border-gray-900 bg-gray-900 text-white` : `${base} border-gray-300 bg-white text-gray-700`;
}

export default function MeetingsPage() {
  const { meetings } = useMeetings();
  const [search, setSearch] = useState('');
  const [sourceFilters, setSourceFilters] = useState<Set<StoredMeetingSummary['source_type']>>(new Set());
  const [statusFilters, setStatusFilters] = useState<Set<StoredMeetingSummary['status']>>(new Set());
  const [patternFilters, setPatternFilters] = useState<Set<string>>(new Set());
  const [view, setView] = useState<View>('table');

  const patterns = useMemo(() => {
    const set = new Set<string>();
    for (const m of meetings) if (m.detected_pattern) set.add(m.detected_pattern);
    return [...set].sort();
  }, [meetings]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return meetings.filter((m) => {
      if (q && !m.title.toLowerCase().includes(q)) return false;
      if (sourceFilters.size > 0 && !sourceFilters.has(m.source_type)) return false;
      if (statusFilters.size > 0 && !statusFilters.has(m.status)) return false;
      if (patternFilters.size > 0 && (!m.detected_pattern || !patternFilters.has(m.detected_pattern))) return false;
      return true;
    });
  }, [meetings, search, sourceFilters, statusFilters, patternFilters]);

  function toggle<T>(set: Set<T>, value: T, setter: (s: Set<T>) => void) {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    setter(next);
  }

  if (meetings.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Meetings</h1>
        <EmptyState
          title="No meetings yet"
          body="Import a transcript or audio file to get started."
          cta={{ to: '/import', label: 'Import' }}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Meetings</h1>
        <div className="flex gap-2 text-sm">
          <button
            type="button"
            onClick={() => setView('table')}
            aria-pressed={view === 'table'}
            className={chipClass(view === 'table')}
          >
            Table
          </button>
          <button
            type="button"
            onClick={() => setView('cards')}
            aria-pressed={view === 'cards'}
            className={chipClass(view === 'cards')}
          >
            Cards
          </button>
        </div>
      </header>

      <input
        type="search"
        placeholder="Search by title…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        aria-label="Search meetings"
        className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
      />

      <div className="space-y-2">
        <FilterRow label="Source">
          {SOURCE_TYPES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => toggle(sourceFilters, s, setSourceFilters)}
              aria-pressed={sourceFilters.has(s)}
              className={chipClass(sourceFilters.has(s))}
            >
              {sourceLabel(s)}
            </button>
          ))}
        </FilterRow>
        <FilterRow label="Status">
          {STATUSES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => toggle(statusFilters, s, setStatusFilters)}
              aria-pressed={statusFilters.has(s)}
              className={chipClass(statusFilters.has(s))}
            >
              {s}
            </button>
          ))}
        </FilterRow>
        {patterns.length > 0 && (
          <FilterRow label="Pattern">
            {patterns.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => toggle(patternFilters, p, setPatternFilters)}
                aria-pressed={patternFilters.has(p)}
                className={chipClass(patternFilters.has(p))}
              >
                {p}
              </button>
            ))}
          </FilterRow>
        )}
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-gray-500">No meetings match the current filters.</p>
      ) : view === 'table' ? (
        <MeetingTable meetings={filtered} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((m) => (
            <MeetingCard key={m.meeting_id} meeting={m} />
          ))}
        </div>
      )}
    </div>
  );
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</span>
      {children}
    </div>
  );
}
