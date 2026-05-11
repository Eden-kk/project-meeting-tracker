import { useEffect, useId, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  searchCards,
  searchTranscripts,
  type CardSearchHit,
  type TranscriptSearchHit,
} from '../api/client';

type Tab = 'transcripts' | 'cards';

/** Debounced workspace-wide search with a tabbed Transcripts / Cards
 *  dropdown (Wave 4.2). Transcripts tab links hits to
 *  `/meetings/{id}#seg-{segment_id}`; Cards tab links to
 *  `/meetings/{id}#card-{memory_card_id}` (the MemoryCardItem renders an
 *  `id="card-..."` anchor on each card).
 */
export function SearchBar() {
  const [raw, setRaw] = useState('');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>('transcripts');
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const listboxId = useId();

  useEffect(() => {
    const t = setTimeout(() => setQ(raw.trim()), 250);
    return () => clearTimeout(t);
  }, [raw]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!wrapperRef.current) return;
      if (!wrapperRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const enabled = q.length >= 2;

  const transcriptsQ = useQuery({
    queryKey: ['searchTranscripts', q],
    queryFn: () => searchTranscripts({ q, limit: 10 }),
    enabled: enabled && tab === 'transcripts',
    staleTime: 30_000,
  });
  const cardsQ = useQuery({
    queryKey: ['searchCards', q],
    queryFn: () => searchCards({ q, limit: 10 }),
    enabled: enabled && tab === 'cards',
    staleTime: 30_000,
  });

  // Prefetch the other tab so toggling feels instant — but only after the
  // user has stopped typing. We piggy-back on the same key so React Query
  // shares the cache.
  useEffect(() => {
    if (!enabled) return;
    if (tab === 'transcripts') {
      searchCards({ q, limit: 10 }).catch(() => undefined);
    } else {
      searchTranscripts({ q, limit: 10 }).catch(() => undefined);
    }
  }, [enabled, q, tab]);

  const transcripts: TranscriptSearchHit[] = transcriptsQ.data?.items ?? [];
  const cards: CardSearchHit[] = cardsQ.data?.items ?? [];

  const showDropdown = open && enabled;
  const activeFetching = tab === 'transcripts' ? transcriptsQ.isFetching : cardsQ.isFetching;
  const activeError = tab === 'transcripts' ? transcriptsQ.isError : cardsQ.isError;
  const activeEmpty =
    !activeFetching &&
    !activeError &&
    (tab === 'transcripts' ? transcripts.length === 0 : cards.length === 0);

  return (
    <div
      ref={wrapperRef}
      className="relative w-full max-w-md"
      data-testid="search-bar"
    >
      <input
        type="search"
        role="combobox"
        aria-label="Search workspace"
        aria-expanded={showDropdown}
        aria-controls={listboxId}
        placeholder="Search transcripts and cards..."
        value={raw}
        onChange={(e) => {
          setRaw(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-gray-500 focus:outline-none"
      />
      {showDropdown && (
        <div
          id={listboxId}
          role="listbox"
          className="absolute right-0 z-40 mt-1 max-h-96 w-full overflow-auto rounded border border-gray-200 bg-white shadow-lg"
        >
          <div
            role="tablist"
            aria-label="Search scopes"
            className="flex border-b border-gray-100 text-xs"
          >
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'transcripts'}
              onClick={() => setTab('transcripts')}
              className={`flex-1 px-3 py-1.5 ${
                tab === 'transcripts'
                  ? 'border-b-2 border-gray-900 font-medium'
                  : 'text-gray-500 hover:bg-gray-50'
              }`}
            >
              Transcripts{' '}
              <span className="text-gray-400">
                ({transcriptsQ.data?.total ?? 0})
              </span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'cards'}
              onClick={() => setTab('cards')}
              className={`flex-1 px-3 py-1.5 ${
                tab === 'cards'
                  ? 'border-b-2 border-gray-900 font-medium'
                  : 'text-gray-500 hover:bg-gray-50'
              }`}
            >
              Cards{' '}
              <span className="text-gray-400">({cardsQ.data?.total ?? 0})</span>
            </button>
          </div>
          {activeFetching && (
            <div className="px-3 py-2 text-sm text-gray-500">Searching…</div>
          )}
          {activeError && (
            <div className="px-3 py-2 text-sm text-red-600">
              Search failed. Try again.
            </div>
          )}
          {activeEmpty && (
            <div className="px-3 py-2 text-sm text-gray-500">No matches.</div>
          )}
          {tab === 'transcripts' &&
            transcripts.map((hit) => (
              <Link
                key={hit.segment_id}
                to={`/meetings/${hit.meeting_id}#seg-${hit.segment_id}`}
                role="option"
                aria-selected={false}
                onClick={() => setOpen(false)}
                className="block border-b border-gray-100 px-3 py-2 last:border-b-0 hover:bg-gray-50"
              >
                <div className="text-xs font-medium text-gray-500">
                  {hit.meeting_title || 'Untitled meeting'} ·{' '}
                  <span className="text-gray-400">{hit.speaker}</span>
                </div>
                <div
                  className="mt-0.5 text-sm text-gray-800"
                  dangerouslySetInnerHTML={{ __html: hit.snippet || hit.text }}
                />
              </Link>
            ))}
          {tab === 'cards' &&
            cards.map((hit) => (
              <Link
                key={hit.memory_card_id}
                to={`/meetings/${hit.meeting_id}#card-${hit.memory_card_id}`}
                role="option"
                aria-selected={false}
                onClick={() => setOpen(false)}
                className="block border-b border-gray-100 px-3 py-2 last:border-b-0 hover:bg-gray-50"
              >
                <div className="text-xs font-medium text-gray-500">
                  {hit.meeting_title || 'Untitled meeting'} ·{' '}
                  <span className="rounded bg-gray-100 px-1 py-0.5 text-gray-600">
                    {hit.type}
                  </span>
                </div>
                <div className="mt-0.5 text-sm font-medium text-gray-900">
                  {hit.title}
                </div>
                <div
                  className="text-xs text-gray-700"
                  dangerouslySetInnerHTML={{ __html: hit.snippet || hit.content }}
                />
              </Link>
            ))}
        </div>
      )}
    </div>
  );
}
