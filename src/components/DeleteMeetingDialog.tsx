import { useEffect, useId, useRef } from 'react';
import { useDeleteMeeting } from '../hooks/useDeleteMeeting';

type Props = {
  meeting: { id: string; title: string };
  workspaceId: string;
  onClose: () => void;
  onDeleted?: () => void;
};

export function DeleteMeetingDialog({ meeting, workspaceId, onClose, onDeleted }: Props) {
  const dialogId = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const mutation = useDeleteMeeting(workspaceId);

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    dialogRef.current?.querySelector<HTMLElement>('button')?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  function errorMessage(): string {
    const err = mutation.error as (Error & { response?: { status?: number } }) | null;
    if (!err) return '';
    const status = err.response?.status;
    if (status === 409) return 'This meeting has already been deleted.';
    if (status === 404) return 'Meeting not found.';
    return err.message || 'Delete failed. Try again.';
  }

  function onDelete() {
    mutation.mutate(meeting.id, {
      onSuccess: () => {
        onDeleted?.();
        onClose();
      },
    });
  }

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={dialogRef}
        id={dialogId}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${dialogId}-title`}
        className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-5 shadow-lg"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 id={`${dialogId}-title`} className="text-lg font-semibold">
            Delete &ldquo;{meeting.title}&rdquo;?
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-gray-500 hover:bg-gray-100"
          >
            ×
          </button>
        </div>

        <p className="mb-4 text-sm text-gray-700">
          This permanently removes the meeting, its transcript, cards, and the original audio
          file. The summary and decisions cannot be re-played. This action cannot be undone
          from the UI.
        </p>

        {mutation.isError && (
          <p className="mb-3 text-xs text-red-600">{errorMessage()}</p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={mutation.isPending}
            className="rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={mutation.isPending}
            className="rounded bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700 disabled:opacity-50"
          >
            {mutation.isPending ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </>
  );
}
