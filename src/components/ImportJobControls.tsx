import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { controlImportJob, getImportJob } from '../api/importJobs';
import { queryKeys } from '../api/queryKeys';
import { POLL_INTERVAL_MS } from '../lib/constants';

export function ImportJobControls({ id }: { id: string }) {
  const client = useQueryClient();
  const [remoteStopped, setRemoteStopped] = useState(false);
  const key = ['import-job', id];
  const job = useQuery({
    queryKey: key,
    queryFn: () => getImportJob(id),
    retry: false,
    refetchInterval: q => ['failed', 'cancelled', 'ready'].includes(q.state.data?.status ?? '')
      || q.state.error ? false : POLL_INTERVAL_MS,
  });
  const control = useMutation({
    mutationFn: (action: 'cancel' | 'retry') => controlImportJob(id, action, remoteStopped),
    onSuccess: data => {
      setRemoteStopped(false);
      client.setQueryData(key, data);
      void client.invalidateQueries({ queryKey: queryKeys.meeting(id) });
      void client.invalidateQueries({ queryKey: ['meetings'] });
    },
    onError: () => {
      // A lost HTTP response may hide a committed action. Reconcile first;
      // never automatically repeat a mutation.
      void client.invalidateQueries({ queryKey: key });
      void client.invalidateQueries({ queryKey: queryKeys.meeting(id) });
    },
  });
  if (job.isError) return <p role="alert">Unable to load import controls. Refresh to verify the current state.</p>;
  if (!job.data) return null;
  const retryable = ['failed', 'cancelled'].includes(job.data.status);
  const cancellable = ['received', 'parsing', 'transcribing', 'normalizing'].includes(job.data.status);
  if (!retryable && !cancellable) return null;
  return (
    <section className="space-y-3 rounded border p-4" aria-label="Import controls">
      <p>Attempts: {job.data.attempts}</p>
      {job.data.error && <p>{job.data.error}</p>}
      <p className="text-sm text-gray-600">Cancellation stops accepting results locally. It does not stop remote computation or billing.</p>
      {retryable && <>
        {job.data.attempts > 0 && <label className="flex gap-2">
          <input type="checkbox" checked={remoteStopped} disabled={control.isPending}
            onChange={e => setRemoteStopped(e.target.checked)} />
          I verified that the previous remote job has stopped.
        </label>}
        <button className="rounded bg-blue-600 px-3 py-2 text-white disabled:opacity-50"
          disabled={control.isPending || (job.data.attempts > 0 && !remoteStopped)}
          onClick={() => control.mutate('retry')}>Retry import</button>
      </>}
      {cancellable && <button className="rounded border px-3 py-2 disabled:opacity-50"
        disabled={control.isPending} onClick={() => control.mutate('cancel')}>Cancel import</button>}
      {control.isError && <p role="alert">Action not confirmed. Current state is being refreshed; verify it before trying again.</p>}
    </section>
  );
}
