import { useQuery } from '@tanstack/react-query';
import {
  listMeetingCards,
  type ListMeetingCardsFilters,
} from '../api/client';
import { queryKeys } from '../api/queryKeys';

/**
 * Phase-3 redesign: cards are agent-owned. The approve / reject / edit
 * mutation hooks (useCommitCard / useRejectCard / usePatchCard) were
 * removed along with the per-card state machine; this hook is read-only.
 */
export function useMeetingCards(meetingId: string, filters?: ListMeetingCardsFilters) {
  return useQuery({
    queryKey: queryKeys.meetingCards(meetingId, filters),
    queryFn: () => listMeetingCards(meetingId, filters),
    enabled: Boolean(meetingId),
  });
}
