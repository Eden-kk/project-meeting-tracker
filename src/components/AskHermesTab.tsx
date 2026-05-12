import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { askHermes } from '../api/client';
import type { AskHermesResponse, EvidenceCitation } from '../api/memory_cards.types';
import { msToClock } from '../lib/time';
import { AnswerBody } from './AnswerBody';

type Message =
  | { id: string; role: 'user'; text: string }
  | {
      id: string;
      role: 'assistant';
      text: string;
      citations: EvidenceCitation[];
      weakEvidence: boolean;
      confidence: number;
    };

type Props = {
  meetingId: string;
  onEvidenceClick: (segmentId: string) => void;
};

export function AskHermesTab({ meetingId, onEvidenceClick }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');

  const mutation = useMutation({
    mutationFn: (question: string) => askHermes({ meeting_id: meetingId, question }),
    onSuccess: (resp: AskHermesResponse) => {
      setMessages((prev) => [
        ...prev,
        {
          id: `a_${prev.length}`,
          role: 'assistant',
          text: resp.answer,
          citations: resp.citations,
          weakEvidence: resp.weak_evidence,
          confidence: resp.confidence,
        },
      ]);
    },
  });

  function handleSend() {
    const trimmed = draft.trim();
    if (!trimmed || mutation.isPending) return;
    setMessages((prev) => [
      ...prev,
      { id: `u_${prev.length}`, role: 'user', text: trimmed },
    ]);
    setDraft('');
    mutation.mutate(trimmed);
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        className="flex max-h-[500px] flex-col gap-3 overflow-y-auto rounded border border-gray-200 bg-gray-50 p-3"
        data-testid="ask-hermes-messages"
      >
        {messages.length === 0 && (
          <p className="text-sm text-gray-500">
            Ask a question about this meeting to get started.
          </p>
        )}
        {messages.map((m) => {
          if (m.role === 'user') {
            return (
              <div key={m.id} className="self-end max-w-[80%]">
                <div className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white">
                  {m.text}
                </div>
              </div>
            );
          }
          const lowConfidence = m.weakEvidence || m.confidence < 0.5;
          return (
            <div key={m.id} className="self-start max-w-[80%] space-y-1">
              <div className="rounded-lg bg-white px-3 py-2 shadow-sm">
                <AnswerBody text={m.text} onSegClick={onEvidenceClick} />
              </div>
              {lowConfidence && (
                <div
                  className="inline-block rounded bg-yellow-100 px-2 py-0.5 text-xs text-yellow-800"
                  data-testid="low-confidence-chip"
                >
                  Low confidence — verify with the transcript
                </div>
              )}
              {m.citations.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {m.citations.map((c) => (
                    <button
                      key={c.segment_id}
                      type="button"
                      onClick={() => onEvidenceClick(c.segment_id)}
                      className="rounded-full border border-gray-300 bg-white px-2 py-0.5 text-xs text-gray-700"
                      data-testid="evidence-pill"
                    >
                      {c.speaker} · {msToClock(c.start_ms)}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {mutation.isPending && (
          <div className="self-start text-xs text-gray-500">Hermes is thinking…</div>
        )}
      </div>

      <div className="flex gap-2">
        <textarea
          aria-label="Ask Hermes a question"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKey}
          rows={2}
          className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm"
          placeholder="What did the team decide about onboarding?"
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={mutation.isPending || draft.trim().length === 0}
          className="self-end rounded bg-gray-900 px-4 py-2 text-sm text-white disabled:bg-gray-400"
        >
          Send
        </button>
      </div>
    </div>
  );
}
