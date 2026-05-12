import { useQueries } from '@tanstack/react-query';
import { listMeetingCards } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { useMeetings } from './useMeetings';

export const TOTAL_COUNT_MAX_MEETINGS = 50;

/**
 * Sum visible memory cards across the workspace. Phase-3 replacement for
 * the old `useDraftCardCount` (the per-card state machine is gone — there
 * is no "draft" anymore; the agent's audit + consolidation passes own
 * quality). Hook + file name kept stable to minimize churn elsewhere.
 *
 * The workspace id is read from the URL by `useMeetings()` → `useWorkspace()`
 * — callers no longer pass it through.
 */
export function useTotalCardCount(): {
  count: number;
  isLoading: boolean;
  isError: boolean;
} {
  const { meetings } = useMeetings();
  const slice = meetings.slice(0, TOTAL_COUNT_MAX_MEETINGS);

  const results = useQueries({
    queries: slice.map((m) => ({
      queryKey: queryKeys.meetingCards(m.meeting_id),
      queryFn: () => listMeetingCards(m.meeting_id),
      staleTime: 30_000,
      retry: false,
    })),
  });

  const isLoading = results.some((r) => r.isLoading);
  const isError = results.some((r) => r.isError);
  const count = results.reduce((acc, r) => acc + (r.data?.total ?? 0), 0);
  return { count, isLoading, isError };
}
