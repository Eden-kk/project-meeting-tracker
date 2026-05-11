import expectedNormalizedJson from '../../fixtures/expected_normalized.json';
import type { Meeting, MeetingsList, NormalizedTranscript } from '../api/client';

export const expectedNormalized = expectedNormalizedJson as NormalizedTranscript;

export function makeFixtureMeeting(
  meeting_id: string,
  artifact_id: string,
  title: string = '',
): Meeting {
  return {
    meeting_id,
    artifact_id,
    title,
    status: 'processing',
    started_at: null,
    ended_at: null,
    finalized_at: null,
    current_schema: null,
    evidence_quality: 'medium',
  };
}

export function makeFixtureMeetingsList(count: number = 3): MeetingsList {
  const items: Meeting[] = Array.from({ length: count }, (_, i) =>
    makeFixtureMeeting(`m_lib_${i}`, `art_lib_${i}`, `Library meeting ${i}`),
  );
  return { items, total: items.length };
}
