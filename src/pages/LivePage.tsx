import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createLiveMeeting,
  endLiveMeeting,
  listLiveSegments,
  uploadLiveChunk,
  type LiveSegment,
} from '../api/client';

type Phase = 'idle' | 'recording' | 'ending' | 'ended' | 'error';

const CHUNK_MS = 10000;
const POLL_MS = 2000;

/**
 * Live meeting capture (Phase 3 Wave 6.1).
 *
 * Flow:
 *   1. User clicks "Start meeting" -> POST /api/live-meetings.
 *   2. Browser MediaRecorder is started with `timeslice=CHUNK_MS`, so the
 *      `dataavailable` callback fires every ~10s with one WebM blob.
 *   3. Each blob is uploaded via POST /api/live-meetings/{id}/audio-chunk.
 *   4. A 2s polling loop refreshes the live transcript panel.
 *   5. "End meeting" stops the recorder, drains any pending chunk, and
 *      POSTs /end to flip status to 'ready'.
 *
 * The MediaRecorder path itself can't run in JSDOM, so the unit test only
 * asserts the idle render. End-to-end coverage of the create-meeting path
 * lives in `e2e/live-capture.spec.ts` (mocked backend).
 */
export default function LivePage() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [meetingId, setMeetingId] = useState<string | null>(null);
  const [title, setTitle] = useState('Live meeting');
  const [segments, setSegments] = useState<LiveSegment[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // Wave 6.3: rolling summary refreshed by the backend every ~120s.
  // The segments-poll response carries it, so we don't need a separate
  // poll loop. NULL until the first agent tick succeeds.
  const [liveSummary, setLiveSummary] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const seqRef = useRef(0);
  const meetingRef = useRef<string | null>(null);
  const lastSegIdRef = useRef<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const phaseRef = useRef<Phase>('idle');

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const pollSegments = useCallback(async () => {
    const id = meetingRef.current;
    if (!id) return;
    try {
      const resp = await listLiveSegments(id, lastSegIdRef.current);
      // Wave 6.3: rolling summary is bundled into every segments
      // response. Update unconditionally — even on a tick that adds
      // zero new segments — so the panel reflects the latest agent
      // pass.
      setLiveSummary(resp.live_summary ?? null);
      if (resp.segments.length === 0) return;
      lastSegIdRef.current = resp.segments[resp.segments.length - 1].segment_id;
      setSegments((prev) => [...prev, ...resp.segments]);
    } catch (err) {
      // Polling errors are non-fatal; surface them only if we have nothing.
      console.warn('live-poll failed', err);
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollSegments();
    pollingRef.current = setInterval(pollSegments, POLL_MS);
  }, [pollSegments, stopPolling]);

  const handleStart = useCallback(async () => {
    setErrorMsg(null);
    if (typeof navigator === 'undefined' || !navigator.mediaDevices) {
      setErrorMsg('This browser does not expose a microphone API.');
      setPhase('error');
      phaseRef.current = 'error';
      return;
    }
    try {
      const created = await createLiveMeeting(title.trim() || 'Live meeting');
      meetingRef.current = created.meeting_id;
      setMeetingId(created.meeting_id);
      seqRef.current = 0;
      lastSegIdRef.current = null;
      setSegments([]);
      setLiveSummary(null);

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Start one MediaRecorder segment. When it stops, schedule the next
      // so each chunk gets its own EBML init segment and is self-contained.
      function startSegment() {
        if (!streamRef.current) return;
        const recorder = new MediaRecorder(streamRef.current, { mimeType: 'audio/webm' });
        recorderRef.current = recorder;

        recorder.ondataavailable = async (event) => {
          if (event.data.size === 0) return;
          const id = meetingRef.current;
          if (!id) return;
          const seq = seqRef.current;
          seqRef.current += 1;
          try {
            await uploadLiveChunk(id, event.data, seq);
          } catch (err) {
            console.warn('chunk upload failed', err);
          }
        };

        recorder.onstop = () => {
          // Chain next segment only while still recording.
          if (phaseRef.current === 'recording') {
            startSegment();
          }
        };

        recorder.start();
        setTimeout(() => {
          if (recorder.state === 'recording') recorder.stop();
        }, CHUNK_MS);
      }

      phaseRef.current = 'recording';
      setPhase('recording');
      startSegment();
      startPolling();
    } catch (err) {
      console.error(err);
      setErrorMsg(err instanceof Error ? err.message : 'Could not start meeting.');
      phaseRef.current = 'error';
      setPhase('error');
    }
  }, [startPolling, title]);

  const handleStop = useCallback(async () => {
    phaseRef.current = 'ending';
    setPhase('ending');
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    const id = meetingRef.current;
    if (id) {
      try {
        await endLiveMeeting(id);
      } catch (err) {
        console.warn('end meeting failed', err);
      }
      // One last poll to flush any segments the backend wrote between the
      // last 2s tick and the stop.
      await pollSegments();
    }
    stopPolling();
    phaseRef.current = 'ended';
    setPhase('ended');
  }, [pollSegments, stopPolling]);

  useEffect(() => {
    return () => {
      stopPolling();
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [stopPolling]);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Live meeting</h1>
        <p className="text-sm text-gray-600">
          Capture a meeting straight from your microphone. Chunks upload every{' '}
          {CHUNK_MS / 1000} seconds.
        </p>
      </header>

      <section className="space-y-3 rounded border border-gray-200 bg-white p-4">
        <label className="block text-sm font-medium" htmlFor="live-title">
          Title
        </label>
        <input
          id="live-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={phase === 'recording' || phase === 'ending'}
          className="w-full rounded border border-gray-300 p-2 disabled:bg-gray-100"
        />

        <div className="flex items-center gap-3">
          {phase === 'idle' || phase === 'ended' || phase === 'error' ? (
            <button
              type="button"
              onClick={handleStart}
              className="rounded bg-red-600 px-4 py-2 text-white hover:bg-red-700"
            >
              Start meeting
            </button>
          ) : (
            <button
              type="button"
              onClick={handleStop}
              disabled={phase === 'ending'}
              className="rounded bg-gray-900 px-4 py-2 text-white disabled:opacity-50"
            >
              {phase === 'ending' ? 'Ending…' : 'End meeting'}
            </button>
          )}
          <span
            data-testid="live-phase"
            className="text-xs uppercase tracking-wide text-gray-500"
          >
            {phase}
          </span>
          {meetingId && (
            <span className="text-xs text-gray-500">id: {meetingId}</span>
          )}
        </div>

        {errorMsg && <p className="text-sm text-red-600">{errorMsg}</p>}
      </section>

      {/* Wave 6.3: rolling agent summary, refreshed every ~120s by the
          backend. The same JSON field arrives on every segments-poll
          response, so we don't run a second polling loop. */}
      <section
        className="rounded border border-blue-200 bg-blue-50 p-4"
        data-testid="live-summary-panel"
      >
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-blue-900">
          Rolling summary
        </h2>
        {liveSummary ? (
          <p
            className="whitespace-pre-line text-sm text-blue-950"
            data-testid="live-summary-text"
          >
            {liveSummary}
          </p>
        ) : (
          <p className="text-sm italic text-blue-700">
            {phase === 'recording'
              ? 'The agent will produce a summary once it has heard ~2 minutes of conversation.'
              : 'No summary yet — start the meeting to begin.'}
          </p>
        )}
      </section>

      <section className="rounded border border-gray-200 bg-white p-4">
        <h2 className="mb-3 text-lg font-medium">Live transcript</h2>
        {segments.length === 0 ? (
          <p className="text-sm text-gray-500">
            {phase === 'recording'
              ? 'Waiting for the first chunk…'
              : 'Start the meeting to see the live transcript here.'}
          </p>
        ) : (
          <ol className="space-y-2" data-testid="live-segments">
            {segments.map((s) => (
              <li key={s.segment_id} className="text-sm">
                <span className="mr-2 text-gray-400">
                  {s.start_ms != null ? `${(s.start_ms / 1000).toFixed(0)}s` : '·'}
                </span>
                {s.speaker_name && (
                  <span className="mr-2 font-medium text-gray-700">
                    {s.speaker_name}:
                  </span>
                )}
                <span>{s.text}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
