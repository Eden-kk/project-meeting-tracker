import type { SpeakerSegment } from '../api/client';
import { msToClock } from '../lib/time';

function speakerLabel(seg: SpeakerSegment): string {
  return seg.speaker_name ?? seg.speaker_id ?? 'Unknown speaker';
}

export function TranscriptView({ segments }: { segments: SpeakerSegment[] }) {
  let prevSpeaker: string | null = null;
  return (
    <div className="space-y-1">
      {segments.map((seg) => {
        const label = speakerLabel(seg);
        const showSpeaker = label !== prevSpeaker;
        prevSpeaker = label;
        const showTimestamp = seg.start_ms != null;
        return (
          <div
            key={seg.segment_id}
            id={'segment-' + seg.segment_id}
            className="flex gap-3"
            data-testid="transcript-row"
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
