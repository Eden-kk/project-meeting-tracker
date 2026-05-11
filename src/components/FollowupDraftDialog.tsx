import { useEffect, useId, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { draftFollowup } from '../api/client';
import type { FollowupDraftTone } from '../api/memory_cards.types';

type Props = {
  meetingId: string;
  open: boolean;
  onClose: () => void;
};

const TONES: FollowupDraftTone[] = ['neutral', 'decisive', 'warm'];

/** Wave 5.3 — modal: optional recipient + tone, generates a markdown
 * follow-up email body, shows it in a textarea, and lets the user
 * copy to clipboard.
 *
 * The recipient sanitizer mirrors the backend regex
 * (`^[\w \-']{1,100}$`) so the user gets a synchronous validation
 * error instead of a 422 round-trip. The character set intentionally
 * matches `\w` in Python's UNICODE mode (Unicode letters, digits,
 * underscore) — JS `\w` is ASCII-only, so we use a broader regex.
 */
const RECIPIENT_RE = /^[\p{L}\p{M}\p{N}_ \-']{1,100}$/u;

export function FollowupDraftDialog({ meetingId, open, onClose }: Props) {
  const dialogId = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const [recipient, setRecipient] = useState('');
  const [tone, setTone] = useState<FollowupDraftTone>('neutral');
  const [copied, setCopied] = useState(false);
  const [recipientError, setRecipientError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      draftFollowup({
        meeting_id: meetingId,
        recipient: recipient.trim() || undefined,
        tone,
      }),
  });

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    dialogRef.current?.querySelector<HTMLElement>('input, textarea, button')?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previouslyFocused?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const v = recipient.trim();
    if (v && !RECIPIENT_RE.test(v)) {
      setRecipientError('Letters, digits, spaces, hyphens, and apostrophes only.');
      return;
    }
    setRecipientError(null);
    setCopied(false);
    mutation.mutate();
  }

  async function onCopy() {
    if (!mutation.data) return;
    try {
      await navigator.clipboard.writeText(mutation.data.markdown);
      setCopied(true);
    } catch {
      setCopied(false);
    }
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
        className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-5 shadow-lg"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 id={`${dialogId}-title`} className="text-lg font-semibold">
            Draft follow-up
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

        <form onSubmit={onSubmit} className="space-y-3">
          <label className="block text-sm">
            <span className="mb-1 block text-gray-700">Recipient (optional)</span>
            <input
              type="text"
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              maxLength={100}
              placeholder="e.g. Anne-Marie"
              className="w-full rounded border border-gray-300 px-3 py-2"
              aria-invalid={recipientError !== null}
              aria-describedby={recipientError ? `${dialogId}-err` : undefined}
            />
            {recipientError && (
              <p id={`${dialogId}-err`} className="mt-1 text-xs text-red-700">
                {recipientError}
              </p>
            )}
          </label>

          <fieldset className="text-sm">
            <legend className="mb-1 text-gray-700">Tone</legend>
            <div className="flex gap-2">
              {TONES.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTone(t)}
                  aria-pressed={tone === t}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    tone === t
                      ? 'border-gray-900 bg-gray-900 text-white'
                      : 'border-gray-300 bg-white text-gray-700'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </fieldset>

          <button
            type="submit"
            disabled={mutation.isPending}
            className="rounded bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {mutation.isPending ? 'Drafting…' : 'Generate draft'}
          </button>
        </form>

        {mutation.isError && (
          <p className="mt-3 text-sm text-red-700">
            Failed to generate draft. {(mutation.error as Error)?.message ?? ''}
          </p>
        )}

        {mutation.data && (
          <div className="mt-4 space-y-2">
            <textarea
              value={mutation.data.markdown}
              readOnly
              rows={10}
              aria-label="Follow-up draft markdown"
              className="w-full rounded border border-gray-300 p-3 font-mono text-xs"
            />
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onCopy}
                className="rounded border border-gray-300 px-3 py-1 text-xs"
              >
                Copy to clipboard
              </button>
              {copied && <span className="text-xs text-green-700">Copied!</span>}
              {mutation.data.cards_referenced.length > 0 && (
                <span className="text-xs text-gray-500">
                  Cites {mutation.data.cards_referenced.length} card
                  {mutation.data.cards_referenced.length === 1 ? '' : 's'}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
