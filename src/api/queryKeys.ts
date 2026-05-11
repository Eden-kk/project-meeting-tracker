import type { MemoryCardType } from './memory_cards.types';

type MeetingCardsFilters = {
  type?: MemoryCardType;
  include_hidden?: boolean;
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
    [
      'meetingCards',
      meetingId,
      filters?.type ?? null,
      filters?.include_hidden ?? null,
    ] as const,
  totalCardsAll: (workspaceId: string) => ['totalCardsAll', workspaceId] as const,
};
