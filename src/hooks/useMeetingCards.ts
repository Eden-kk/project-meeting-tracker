import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  commitCard,
  listMeetingCards,
  patchMemoryCard,
  rejectCard,
  type ListMeetingCardsFilters,
} from '../api/client';
import type { PatchMemoryCardInput } from '../api/memory_cards.types';
import { queryKeys } from '../api/queryKeys';

function invalidateMeetingCards(qc: ReturnType<typeof useQueryClient>, meetingId: string) {
  // Prefix-match every filter variant for this meeting.
  qc.invalidateQueries({ queryKey: ['meetingCards', meetingId] });
}

export function useMeetingCards(meetingId: string, filters?: ListMeetingCardsFilters) {
  return useQuery({
    queryKey: queryKeys.meetingCards(meetingId, filters),
    queryFn: () => listMeetingCards(meetingId, filters),
    enabled: Boolean(meetingId),
  });
}

export function useCommitCard(meetingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cardId: string) => commitCard(cardId),
    onSuccess: () => invalidateMeetingCards(qc, meetingId),
  });
}

export function useRejectCard(meetingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cardId: string) => rejectCard(cardId),
    onSuccess: () => invalidateMeetingCards(qc, meetingId),
  });
}

export function usePatchCard(meetingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ cardId, patch }: { cardId: string; patch: PatchMemoryCardInput }) =>
      patchMemoryCard(cardId, patch),
    onSuccess: () => invalidateMeetingCards(qc, meetingId),
  });
}
