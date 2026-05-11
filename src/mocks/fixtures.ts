import expectedNormalizedJson from '../../fixtures/expected_normalized.json';
import type { Meeting, NormalizedTranscript } from '../api/client';

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
