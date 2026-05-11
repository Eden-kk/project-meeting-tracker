import type { MemoryCardState, MemoryCardType } from './memory_cards.types';

type MeetingCardsFilters = {
  state?: MemoryCardState;
  type?: MemoryCardType;
};

export const queryKeys = {
  meetings: (params: { workspace_id: string }) =>
    ['meetings', params.workspace_id] as const,
  meeting: (id: string) => ['meeting', id] as const,
  transcript: (id: string) => ['transcript', id] as const,
  // Filter args follow the meetingId so prefix-invalidation by
  // ['meetingCards', meetingId] (TanStack Query v5) refreshes every filter
  // variant for that meeting.
  meetingCards: (meetingId: string, filters?: MeetingCardsFilters) =>
    ['meetingCards', meetingId, filters?.state ?? null, filters?.type ?? null] as const,
  draftCountAll: (workspaceId: string) => ['draftCountAll', workspaceId] as const,
};
