import { useMutation, useQueryClient } from '@tanstack/react-query';
import { deleteMeeting } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { remove as removeFromRegistry } from '../lib/meetingsRegistry';

export function useDeleteMeeting(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteMeeting,
    onSuccess: (_data, meetingId) => {
      removeFromRegistry(meetingId);
      qc.invalidateQueries({ queryKey: queryKeys.meetings({ workspace_id: workspaceId }) });
    },
  });
}
