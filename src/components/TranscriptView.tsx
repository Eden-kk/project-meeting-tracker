import { useEffect, useRef } from 'react';
import type { SpeakerSegment } from '../api/client';
import { msToClock } from '../lib/time';

function speakerLabel(seg: SpeakerSegment): string {
  return seg.speaker_name ?? seg.speaker_id ?? 'Unknown speaker';
}

type Props = {
  segments: SpeakerSegment[];
  /** Wave 3.1 — segment id to flash with a 1.5s highlight. Null = no highlight. */
  highlightedSegmentId?: string | null;
  /** Wave 3.1 — bumps when a NEW highlight request lands so we re-scroll on
   *  repeat clicks of the same evidence pill. */
  highlightTick?: number;
};

export function TranscriptView({
  segments,
  highlightedSegmentId = null,
  highlightTick = 0,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  // When the highlighted segment (or its tick) changes, scroll it into
  // view. We do this here so TranscriptView is the single source of truth
  // for transcript-row layout AND scroll behavior.
  useEffect(() => {
    if (!highlightedSegmentId) return;
    const el = document.getElementById('segment-' + highlightedSegmentId);
    if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [highlightedSegmentId, highlightTick]);

  let prevSpeaker: string | null = null;
  return (
    <div className="space-y-1" ref={containerRef}>
      {segments.map((seg) => {
        const label = speakerLabel(seg);
        const showSpeaker = label !== prevSpeaker;
        prevSpeaker = label;
        const showTimestamp = seg.start_ms != null;
        const isHighlighted = seg.segment_id === highlightedSegmentId;
        return (
          <div
            key={seg.segment_id}
            id={'segment-' + seg.segment_id}
            data-testid="transcript-row"
            data-highlighted={isHighlighted ? 'true' : undefined}
            className={
              'flex gap-3 rounded transition-colors duration-500 ' +
              (isHighlighted ? 'bg-amber-100' : 'bg-transparent')
            }
          >
            {showTimestamp && (
              <span className="w-16 shrink-0 font-mono text-xs text-gray-500">
                {msToClock(seg.start_ms!)}
              </span>
            )}
            <div className={showTimestamp ? '' : 'pl-0'}>
              {showSpeaker ? (
                <span className="font-medium">{label}: </span>
              ) : (
                <span className="ml-4" />
              )}
              <span>{seg.text}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
