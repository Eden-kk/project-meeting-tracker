/** PLACEHOLDER — replaced by pnpm gen:api once worktree G merges. */

export type MemoryCardState = 'draft' | 'committed' | 'rejected';

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
  state: MemoryCardState;
  title: string;
  content: string;
  speakers: string[];
  source_chunk_ids: string[];
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

export type PatchMemoryCardInput = {
  title?: string;
  content?: string;
  type?: MemoryCardType;
  speakers?: string[];
  source_chunk_ids?: string[];
};

export type CommitCardResponse = { card: MemoryCard };
export type RejectCardResponse = { card: MemoryCard };

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
