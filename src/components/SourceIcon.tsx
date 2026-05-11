import type { StoredMeetingSummary } from '../lib/meetingsRegistry';

const LABELS: Record<StoredMeetingSummary['source_type'], string> = {
  voice_file: 'Voice file',
  transcript_file: 'Transcript file',
  pasted_transcript: 'Pasted',
  live_voice: 'Live voice',
  zoom_rtms: 'Zoom',
};

const GLYPHS: Record<StoredMeetingSummary['source_type'], string> = {
  voice_file: 'V',
  transcript_file: 'T',
  pasted_transcript: 'P',
  live_voice: 'L',
  zoom_rtms: 'Z',
};

export function SourceIcon({ sourceType }: { sourceType: StoredMeetingSummary['source_type'] }) {
  return (
    <span
      aria-label={LABELS[sourceType]}
      title={LABELS[sourceType]}
      className="inline-flex h-5 w-5 items-center justify-center rounded bg-gray-100 text-[10px] font-semibold text-gray-700"
    >
      {GLYPHS[sourceType]}
    </span>
  );
}

export function sourceLabel(sourceType: StoredMeetingSummary['source_type']): string {
  return LABELS[sourceType];
}
