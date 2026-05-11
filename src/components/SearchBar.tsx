import { useEffect, useId, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { searchTranscripts, type TranscriptSearchHit } from '../api/client';

/** Debounced workspace-wide transcript search. Renders an input + a dropdown
 *  of hits. Each hit links to `/meetings/{id}#seg-{segment_id}` so the
 *  transcript view can scroll to the anchor (the transcript view already
 *  emits `id="seg-..."` per segment for the in-meeting evidence flow).
 *
 *  Wave 4.2 will swap the single-shape dropdown for a tabbed Transcripts /
 *  Cards view; the component shell intentionally stays simple here.
 */
export function SearchBar() {
  const [raw, setRaw] = useState('');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const listboxId = useId();

  // Debounce: 250ms after the last keypress before we hit the API.
  useEffect(() => {
    const t = setTimeout(() => setQ(raw.trim()), 250);
    return () => clearTimeout(t);
  }, [raw]);

  // Close the dropdown when the user clicks outside.
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!wrapperRef.current) return;
      if (!wrapperRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const enabled = q.length >= 2;
  const { data, isFetching, isError } = useQuery({
    queryKey: ['searchTranscripts', q],
    queryFn: () => searchTranscripts({ q, limit: 10 }),
    enabled,
    staleTime: 30_000,
  });

  const items: TranscriptSearchHit[] = data?.items ?? [];
  const showDropdown = open && enabled;

  return (
    <div
      ref={wrapperRef}
      className="relative w-full max-w-md"
      data-testid="search-bar"
    >
      <input
        type="search"
        role="combobox"
        aria-label="Search transcripts"
        aria-expanded={showDropdown}
        aria-controls={listboxId}
        placeholder="Search transcripts..."
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
          {isFetching && (
            <div className="px-3 py-2 text-sm text-gray-500">Searching…</div>
          )}
          {isError && (
            <div className="px-3 py-2 text-sm text-red-600">
              Search failed. Try again.
            </div>
          )}
          {!isFetching && !isError && items.length === 0 && (
            <div className="px-3 py-2 text-sm text-gray-500">No matches.</div>
          )}
          {items.map((hit) => (
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
                // The server returns ts_headline output with <mark> wrappers.
                // The headline operates on plain text from speaker_segments;
                // there is no user-supplied HTML in the snippet, so rendering
                // the marks as HTML is safe.
                dangerouslySetInnerHTML={{ __html: hit.snippet || hit.text }}
              />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
