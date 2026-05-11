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

/** Wave 5.1 / 5.2 — cross-meeting dashboard row.
 *
 * The backend flattens `memory_cards` + the source meeting's `title` and
 * `finalized_at` into one shape so the dashboard table needs only a
 * single round-trip.
 */
export type ActionItemRow = {
  memory_card_id: string;
  meeting_id: string;
  meeting_title: string;
  meeting_finalized_at: string | null;
  type: MemoryCardType;
  title: string;
  content: string;
  source_chunk_ids: string[];
  source_start_ms?: number | null;
  source_end_ms?: number | null;
  speakers_json?: string[] | null;
  confidence: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ActionItemListResponse = {
  items: ActionItemRow[];
  total: number;
};

export type ListActionItemsParams = {
  workspace_id: string;
  speaker?: string;
  meeting_id?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
};

/** Wave 5.3 — tone options for the follow-up draft endpoint. */
export type FollowupDraftTone = 'neutral' | 'decisive' | 'warm';

export type FollowupDraftInput = {
  meeting_id: string;
  recipient?: string;
  tone?: FollowupDraftTone;
};

export type FollowupDraftResponse = {
  meeting_id: string;
  markdown: string;
  cards_referenced: string[];
};
