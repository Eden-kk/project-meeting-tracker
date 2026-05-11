/** PLACEHOLDER — replaced by `pnpm gen:api` once worktree G merges.
 *
 *  Phase-3 redesign: dropped `MemoryCardState` (no per-card state machine
 *  on the server anymore) and `needs_review`. Added `hidden_at` and
 *  `superseded_by_id` from the agent quality surface; the list endpoint
 *  hides agent-soft-deleted rows by default.
 */

export type MemoryCardType =
  | 'decision'
  | 'action_item'
  | 'pain_point'
  | 'quote'
  | 'requirement'
  | 'risk'
  | 'open_question'
  | 'technical_detail';

export type MemoryCard = {
  memory_card_id: string;
  meeting_id: string;
  type: MemoryCardType;
  title: string;
  content: string;
  speakers: string[];
  source_chunk_ids: string[];
  hidden_at: string | null;
  superseded_by_id: string | null;
  created_at: string;
  updated_at: string;
};

export type MemoryCardListResponse = {
  items: MemoryCard[];
  total: number;
};

export type CreateMemoryCardInput = {
  meeting_id: string;
  type: MemoryCardType;
  title: string;
  content: string;
  speakers?: string[];
  source_chunk_ids?: string[];
};

export type FinalizeMeetingResponse = {
  meeting_id: string;
  finalized_at: string;
};

export type AskHermesInput = {
  meeting_id: string;
  question: string;
};

export type EvidenceCitation = {
  segment_id: string;
  speaker: string;
  start_ms: number;
  end_ms: number;
  text: string;
};

export type AskHermesResponse = {
  answer: string;
  confidence: number;
  citations: EvidenceCitation[];
  weak_evidence: boolean;
};
