import type { StoredMeetingSummary } from '../lib/meetingsRegistry';

const STYLE: Record<StoredMeetingSummary['status'], string> = {
  cancelled: 'bg-gray-100 text-gray-800',
  live: 'bg-blue-100 text-blue-800',
  processing: 'bg-amber-100 text-amber-800',
  ready: 'bg-green-100 text-green-800',
  finalizing: 'bg-blue-100 text-blue-800',
  finalized: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
};

const LABEL: Record<StoredMeetingSummary['status'], string> = {
  cancelled: 'Cancelled locally',
  live: 'Live',
  processing: 'Processing',
  ready: 'Ready',
  finalizing: 'Finalizing',
  finalized: 'Finalized',
  failed: 'Failed',
};

export function StatusPill({ status }: { status: StoredMeetingSummary['status'] }) {
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${STYLE[status]}`}>
      {LABEL[status]}
    </span>
  );
}
