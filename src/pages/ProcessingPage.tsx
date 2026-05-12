import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getMeeting } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { POLL_INTERVAL_MS } from '../lib/constants';
import { useWorkspace } from '../hooks/useWorkspace';
import { StatusTimeline } from '../components/StatusTimeline';
import { patch as patchMeeting } from '../lib/meetingsRegistry';

export default function ProcessingPage() {
  const { workspaceId } = useWorkspace();
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const wsHome = `/ws/${workspaceId}/`;

  const query = useQuery({
    queryKey: queryKeys.meeting(id),
    queryFn: () => getMeeting(id),
    retry: false,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      // Phase-3 auto-finalize: keep polling through `ready` so we catch
      // the `finalizing → finalized` flip without forcing a manual
      // refresh; stop only at terminal states.
      if (s === 'finalized' || s === 'failed') return false;
      return POLL_INTERVAL_MS;
    },
  });

  useEffect(() => {
    if (!query.data) return;
    patchMeeting(id, { status: query.data.status, last_seen_at: new Date().toISOString() });
    // Navigate as soon as the transcript is queryable; the meeting page
    // can show a `finalizing` chip while Hermes runs in the background.
    if (
      query.data.status === 'ready' ||
      query.data.status === 'finalizing' ||
      query.data.status === 'finalized'
    ) {
      navigate(`/ws/${workspaceId}/meetings/${id}`, { replace: true });
    }
  }, [query.data, id, navigate, workspaceId]);

  if (query.isError) {
    return (
      <div className="mx-auto max-w-xl rounded border border-red-200 bg-red-50 p-4">
        <p className="font-medium text-red-700">Meeting not found.</p>
        <Link to={wsHome} className="text-sm text-blue-600 underline">
          Back to import
        </Link>
      </div>
    );
  }

  if (!query.data) {
    return <div className="mx-auto max-w-xl">Loading…</div>;
  }

  const { status } = query.data;

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <h1 className="text-2xl font-semibold">Processing</h1>
      <StatusTimeline status={status} />
      {status === 'failed' && (
        <div className="rounded border border-red-200 bg-red-50 p-4">
          <p className="font-medium text-red-700">Processing failed.</p>
          <Link to={wsHome} className="text-sm text-blue-600 underline">
            Try again
          </Link>
        </div>
      )}
    </div>
  );
}
