import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { getMeeting, getMeetingTranscript } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { Tabs, type TabDef } from '../components/Tabs';
import { TranscriptView } from '../components/TranscriptView';
import { MemoryCardsTab } from '../components/MemoryCardsTab';
import { AskHermesTab } from '../components/AskHermesTab';
import { patch as patchMeeting } from '../lib/meetingsRegistry';

const TABS: TabDef[] = [
  { id: 'summary', label: 'Summary' },
  { id: 'transcript', label: 'Transcript' },
  { id: 'memory', label: 'Memory Cards' },
  { id: 'ask', label: 'Ask Hermes' },
  { id: 'share', label: 'Share / Export', disabled: true, tooltip: 'Arrives in Phase 8' },
];

export default function MeetingReviewPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [tab, setTab] = useState('transcript');

  const meetingQuery = useQuery({
    queryKey: queryKeys.meeting(id),
    queryFn: () => getMeeting(id),
    retry: false,
  });

  const transcriptQuery = useQuery({
    queryKey: queryKeys.transcript(id),
    queryFn: () => getMeetingTranscript(id),
    retry: false,
  });

  useEffect(() => {
    if (!meetingQuery.data) return;
    patchMeeting(id, {
      status: meetingQuery.data.status,
      evidence_quality: meetingQuery.data.evidence_quality,
      detected_pattern: meetingQuery.data.detected_pattern?.primary_pattern ?? null,
      last_seen_at: new Date().toISOString(),
    });
  }, [meetingQuery.data, id]);

  function handleEvidenceClick(segmentId: string) {
    setTab('transcript');
    requestAnimationFrame(() => {
      document.getElementById('segment-' + segmentId)?.scrollIntoView({ block: 'center' });
    });
  }

  if (meetingQuery.isError) {
    return (
      <div className="mx-auto max-w-3xl">
        <p>Meeting not found.</p>
        <Link to="/" className="text-sm text-blue-600 underline">
          Back to home
        </Link>
      </div>
    );
  }

  if (!meetingQuery.data) return <div>Loading…</div>;

  const meeting = meetingQuery.data;
  const segments = transcriptQuery.data?.segments ?? [];
  const title = meeting.title || 'Untitled meeting';
  const sourceType = segments[0]?.source_type ?? null;
  const detectedPattern = meeting.detected_pattern?.primary_pattern ?? 'Pending — Phase 2';

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">{title}</h1>
        <div className="flex flex-wrap gap-3 text-sm text-gray-600">
          {sourceType && <span>Source: {sourceType}</span>}
          <span>Pattern: {detectedPattern}</span>
          <span className="rounded bg-gray-100 px-2 py-0.5 text-xs">
            evidence: {meeting.evidence_quality}
          </span>
        </div>
      </header>

      <Tabs tabs={TABS} value={tab} onChange={setTab}>
        {tab === 'summary' && (
          <p>Summary not yet available — extraction lands in Phase 2.</p>
        )}
        {tab === 'transcript' && <TranscriptView segments={segments} />}
        {/* Memory + Ask tabs mounted persistently so chat session and filter
            state survive tab toggles within the same meeting. */}
        <div className={tab === 'memory' ? '' : 'hidden'}>
          <MemoryCardsTab meetingId={id} onEvidenceClick={handleEvidenceClick} />
        </div>
        <div className={tab === 'ask' ? '' : 'hidden'}>
          <AskHermesTab meetingId={id} onEvidenceClick={handleEvidenceClick} />
        </div>
      </Tabs>
    </div>
  );
}
