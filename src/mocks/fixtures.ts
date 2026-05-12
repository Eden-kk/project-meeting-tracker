import expectedNormalizedJson from '../../fixtures/expected_normalized.json';
import type { Meeting, MeetingsList, NormalizedTranscript } from '../api/client';
import type { MemoryCard } from '../api/memory_cards.types';

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

/**
 * Seed cards for a meeting, mirroring the four primary card types.
 * source_chunk_ids reference real segment IDs from expected_normalized.json
 * so evidence anchors land on visible transcript rows in dev/e2e.
 *
 * Phase-3 redesign: there is no `state` field; cards are live as soon as
 * the agent creates them. `hidden_at` / `superseded_by_id` default null.
 */
export function makeFixtureCards(meeting_id: string): MemoryCard[] {
  const now = '2025-01-15T10:00:00.000Z';
  return [
    {
      memory_card_id: `mc_${meeting_id}_decision`,
      meeting_id,
      type: 'decision',
      title: 'Adopt new auth migration timeline',
      content: 'The team agreed to ship the auth migration by end of Q1.',
      speakers: ['Alice'],
      source_chunk_ids: ['seg_001'],
      confidence: 0.92,
      audit_reason: null,
      hidden_at: null,
      superseded_by_id: null,
      created_at: now,
      updated_at: now,
    },
    {
      memory_card_id: `mc_${meeting_id}_action`,
      meeting_id,
      type: 'action_item',
      title: 'Draft auth rollback plan',
      content: 'Bob will draft a rollback plan and circulate by Friday.',
      speakers: ['Bob'],
      source_chunk_ids: ['seg_002'],
      confidence: 0.7,
      audit_reason: null,
      hidden_at: null,
      superseded_by_id: null,
      created_at: now,
      updated_at: now,
    },
    {
      memory_card_id: `mc_${meeting_id}_pain`,
      meeting_id,
      type: 'pain_point',
      title: 'Existing OAuth flow brittle in staging',
      content: 'Reports of staging OAuth failures during peak hours.',
      speakers: ['Carol'],
      source_chunk_ids: ['seg_003'],
      confidence: 0.4,
      audit_reason: 'Single anecdote; no metric cited.',
      hidden_at: null,
      superseded_by_id: null,
      created_at: now,
      updated_at: now,
    },
    {
      memory_card_id: `mc_${meeting_id}_quote`,
      meeting_id,
      type: 'quote',
      title: '"Ship it before the next board meeting"',
      content: 'Alice: "We need to ship it before the next board meeting."',
      speakers: ['Alice'],
      source_chunk_ids: ['seg_004'],
      confidence: 0.85,
      audit_reason: null,
      hidden_at: null,
      superseded_by_id: null,
      created_at: now,
      updated_at: now,
    },
  ];
}
