import { useQueries } from '@tanstack/react-query';
import { listMeetingCards } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { useMeetings } from './useMeetings';

export const DRAFT_COUNT_MAX_MEETINGS = 50;

export function useDraftCardCount(workspaceId?: string): {
  count: number;
  isLoading: boolean;
  isError: boolean;
} {
  const { meetings } = useMeetings(workspaceId);
  const slice = meetings.slice(0, DRAFT_COUNT_MAX_MEETINGS);

  const results = useQueries({
    queries: slice.map((m) => ({
      queryKey: queryKeys.meetingCards(m.meeting_id, { state: 'draft' as const }),
      queryFn: () => listMeetingCards(m.meeting_id, { state: 'draft' }),
      staleTime: 30_000,
      retry: false,
    })),
  });

  const isLoading = results.some((r) => r.isLoading);
  const isError = results.some((r) => r.isError);
  const count = results.reduce((acc, r) => acc + (r.data?.total ?? 0), 0);
  return { count, isLoading, isError };
}
