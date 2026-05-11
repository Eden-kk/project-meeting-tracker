import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Wave 3.1 — coordinates "click an evidence pill on a memory card → switch
 * to Transcript tab → scroll the cited segment into view → flash a 1.5s
 * highlight" without coupling MemoryCardsTab and TranscriptView.
 *
 * The owning page (currently MeetingReviewPage) calls `goto(segmentId)`
 * which:
 *   - sets `targetSegmentId` for downstream consumers (TranscriptView reads
 *     it to render the transient highlight class),
 *   - schedules a clear after `highlightMs` so the highlight fades after
 *     the dwell window without sticky styling,
 *   - and triggers a `tick` change so consumers can re-react when the
 *     SAME segment is clicked twice in a row (e.g. user lands back on the
 *     transcript and clicks the same pill again — they should still see
 *     the flash).
 *
 * The hook itself does not perform the scroll or the tab switch — those
 * are page-level concerns. It just owns the highlight lifecycle.
 */
export type ScrollTarget = {
  /** Currently-highlighted segment id, or null when no highlight is active. */
  targetSegmentId: string | null;
  /** Monotonic counter — bumps on every goto() so consumers can re-fire effects. */
  tick: number;
  /** Request a highlight + scroll for the given segment. */
  goto: (segmentId: string) => void;
};

export function useScrollTarget(highlightMs: number = 1500): ScrollTarget {
  const [targetSegmentId, setTargetSegmentId] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const timerRef = useRef<number | null>(null);

  const goto = useCallback(
    (segmentId: string) => {
      if (timerRef.current != null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      setTargetSegmentId(segmentId);
      setTick((t) => t + 1);
      timerRef.current = window.setTimeout(() => {
        setTargetSegmentId(null);
        timerRef.current = null;
      }, highlightMs);
    },
    [highlightMs],
  );

  useEffect(
    () => () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
    },
    [],
  );

  return { targetSegmentId, tick, goto };
}
