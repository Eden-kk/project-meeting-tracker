import type { Meeting } from '../api/client';

type Step = { label: string; state: 'done' | 'active' | 'pending' | 'failed' };

function stepsFor(status: Meeting['status']): Step[] {
  if (status === 'failed') {
    return [
      { label: 'Conversation received', state: 'done' },
      { label: 'Failed', state: 'failed' },
    ];
  }
  if (status === 'finalized') {
    return [
      { label: 'Conversation received', state: 'done' },
      { label: 'Transcribing/parsing', state: 'done' },
      { label: 'Normalizing', state: 'done' },
      { label: 'Hermes extraction', state: 'done' },
    ];
  }
  if (status === 'finalizing') {
    return [
      { label: 'Conversation received', state: 'done' },
      { label: 'Transcribing/parsing', state: 'done' },
      { label: 'Normalizing', state: 'done' },
      { label: 'Hermes extraction', state: 'active' },
    ];
  }
  if (status === 'ready') {
    return [
      { label: 'Conversation received', state: 'done' },
      { label: 'Transcribing/parsing', state: 'done' },
      { label: 'Normalizing', state: 'done' },
      { label: 'Hermes extraction', state: 'pending' },
    ];
  }
  // processing / live
  return [
    { label: 'Conversation received', state: 'done' },
    { label: 'Transcribing/parsing', state: 'active' },
    { label: 'Normalizing', state: 'pending' },
    { label: 'Hermes extraction', state: 'pending' },
  ];
}

const dotClass: Record<Step['state'], string> = {
  done: 'bg-green-500',
  active: 'bg-blue-500 animate-pulse',
  pending: 'bg-gray-300',
  failed: 'bg-red-500',
};

export function StatusTimeline({ status }: { status: Meeting['status'] }) {
  const steps = stepsFor(status);
  return (
    <ol className="space-y-2" data-testid="status-timeline">
      {steps.map((step, i) => (
        <li key={i} className="flex items-center gap-3">
          <span className={`inline-block h-3 w-3 rounded-full ${dotClass[step.state]}`} />
          <span className={step.state === 'failed' ? 'text-red-600' : ''}>
            {step.label}
            {step.label === 'Hermes extraction' && step.state === 'active' && (
              <span className="ml-2 text-xs text-blue-600">— extracting…</span>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}
