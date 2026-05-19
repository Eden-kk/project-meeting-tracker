import { useState, type FormEvent } from 'react';
import { dispatchZoomBot, type ZoomBotDispatched } from '../api/client';

type Props = {
  workspaceId: string;
  onDispatched?: (result: ZoomBotDispatched) => void;
};

// Accept the common Zoom join URL shapes. `/my/<vanity>` is intentionally
// rejected — it requires a logged-in account that knows the PMI, which
// the bot doesn't have.
const ZOOM_URL_RE = /https?:\/\/(?:[a-z0-9-]+\.)?zoom\.us\/j\/\d+/i;

/**
 * Wave 9 (zoom-bot): paste-a-Zoom-URL form.
 *
 * Shows the affirmative disclosure required by the plan's "Recording-
 * consent disclosure" section: the bot's display name + the host-admit
 * requirement. Calls dispatchZoomBot() and surfaces any 503 / 400 from
 * the storage-router as inline error text (no toast, no redirect — the
 * `onDispatched` callback is the parent's signal that a new meeting
 * appeared).
 */
export function ZoomUrlForm({ workspaceId, onDispatched }: Props) {
  const [zoomUrl, setZoomUrl] = useState('');
  const [title, setTitle] = useState('Zoom meeting');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmedUrl = zoomUrl.trim();
  const urlValid = ZOOM_URL_RE.test(trimmedUrl);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!urlValid || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await dispatchZoomBot({
        workspaceId,
        zoomUrl: trimmedUrl,
        title: title.trim() || 'Zoom meeting',
      });
      onDispatched?.(result);
      setZoomUrl('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Dispatch failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      data-testid="zoom-url-form"
      className="space-y-3 rounded border border-violet-200 bg-violet-50 p-4"
    >
      <header>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-violet-900">
          Or record a Zoom meeting
        </h2>
        <p className="mt-1 text-xs text-violet-800">
          Hermes will join as a participant named{' '}
          <strong>Hermes — Note-taking Bot</strong>. The host must admit it
          from the Zoom waiting room before audio capture begins.
        </p>
      </header>

      <label className="block text-sm font-medium text-violet-900" htmlFor="zoom-url">
        Zoom meeting URL
      </label>
      <input
        id="zoom-url"
        type="url"
        value={zoomUrl}
        onChange={(e) => setZoomUrl(e.target.value)}
        placeholder="https://zoom.us/j/85412345678?pwd=…"
        disabled={busy}
        className="w-full rounded border border-violet-300 p-2 disabled:bg-gray-100"
        aria-invalid={trimmedUrl.length > 0 && !urlValid}
      />

      <label className="block text-sm font-medium text-violet-900" htmlFor="zoom-title">
        Meeting title (optional)
      </label>
      <input
        id="zoom-title"
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        disabled={busy}
        className="w-full rounded border border-violet-300 p-2 disabled:bg-gray-100"
      />

      <button
        type="submit"
        disabled={!urlValid || busy}
        className="rounded bg-violet-600 px-4 py-2 text-white hover:bg-violet-700 disabled:opacity-50"
      >
        {busy ? 'Dispatching…' : 'Dispatch Hermes to this Zoom call'}
      </button>

      {trimmedUrl.length > 0 && !urlValid && (
        <p className="text-sm text-amber-700" data-testid="zoom-url-validation">
          Paste a join link like <code>https://zoom.us/j/&lt;number&gt;</code>.
          Personal Meeting IDs (<code>/my/&lt;vanity&gt;</code>) aren’t supported
          by the bot.
        </p>
      )}
      {error && (
        <p className="text-sm text-red-700" data-testid="zoom-url-error">
          {error}
        </p>
      )}
    </form>
  );
}
