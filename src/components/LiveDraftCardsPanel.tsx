import { useCallback, useEffect, useRef, useState } from 'react';
import { listLiveDraftCards, type MemoryCard } from '../api/client';
import { MemoryCardItem } from './MemoryCardItem';

const POLL_MS = 5000;

type Props = {
  /** Meeting that's currently in ``status='live'``. The panel polls
   * ``/api/live-meetings/{id}/draft-cards`` while ``active`` is true
   * and freezes once the parent flips it to false (typically when the
   * user clicks "End meeting"). */
  meetingId: string | null;
  active: boolean;
};

/**
 * Wave 6.4 — side panel that surfaces draft cards created by the
 * live-meeting-extraction agent tick (~every 2 minutes).
 *
 * Phase-3 design: there are no approve / reject / edit buttons here.
 * The agent owns card quality and the consolidation pass at meeting
 * /end dedupes any cards the 30s overlap window produced twice.
 *
 * Polling cadence is intentionally faster than the agent tick (5s)
 * so the UI feels responsive; most polls return zero new rows.
 */
export function LiveDraftCardsPanel({ meetingId, active }: Props) {
  const [cards, setCards] = useState<MemoryCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const sinceRef = useRef<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    if (!meetingId) return;
    try {
      const resp = await listLiveDraftCards(meetingId, sinceRef.current);
      if (resp.items.length === 0) return;
      // Advance the watermark to the latest created_at we just saw so
      // the next tick only fetches strictly-newer rows.
      sinceRef.current = resp.items[resp.items.length - 1].created_at;
      setCards((prev) => {
        const seen = new Set(prev.map((c) => c.memory_card_id));
        const fresh = resp.items.filter((c) => !seen.has(c.memory_card_id));
        return [...prev, ...fresh];
      });
      setError(null);
    } catch (err) {
      console.warn('live-draft-cards poll failed', err);
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [meetingId]);

  useEffect(() => {
    if (!active || !meetingId) {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    // Reset state when a new meeting takes over the panel.
    sinceRef.current = null;
    setCards([]);
    setError(null);
    poll();
    timerRef.current = setInterval(poll, POLL_MS);
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [active, meetingId, poll]);

  return (
    <aside
      data-testid="live-draft-cards-panel"
      className="rounded border border-amber-200 bg-amber-50 p-4"
    >
      <header className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-amber-900">
          Draft cards
        </h2>
        <span className="text-xs text-amber-700">
          {cards.length} so far
        </span>
      </header>
      {error && (
        <p className="mb-2 text-xs text-red-600" data-testid="live-cards-error">
          Polling failed: {error}
        </p>
      )}
      {cards.length === 0 ? (
        <p className="text-sm italic text-amber-800">
          {active
            ? 'The agent will start producing draft cards once it has heard ~2 minutes of conversation.'
            : 'Start the meeting to begin.'}
        </p>
      ) : (
        <ol className="space-y-2" data-testid="live-cards-list">
          {cards.map((card) => (
            <li key={card.memory_card_id}>
              <MemoryCardItem
                card={card}
                meetingId={meetingId ?? ''}
                /* No transcript-scroll target on the live page (we
                 * render a flat segment list, not the review tabs). */
                onEvidenceClick={() => undefined}
              />
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
