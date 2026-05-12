import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { askWorkspace, type WorkspaceQACitation } from '../api/client';
import { useWorkspace } from '../hooks/useWorkspace';

function citationLink(workspaceId: string, c: WorkspaceQACitation): string {
  const base = `/ws/${workspaceId}/meetings/${c.meeting_id}`;
  if (c.memory_card_id) {
    return `${base}#card-${c.memory_card_id}`;
  }
  if (c.segment_id) {
    return `${base}#seg-${c.segment_id}`;
  }
  return base;
}

function citationLabel(c: WorkspaceQACitation): string {
  if (c.memory_card_id) return 'card';
  if (c.segment_id) return 'segment';
  return 'meeting';
}

export default function AskPage() {
  const { workspaceId } = useWorkspace();
  const [question, setQuestion] = useState('');

  const ask = useMutation({
    mutationFn: () => askWorkspace({ workspace_id: workspaceId, question }),
  });

  return (
    <div className="space-y-6" data-testid="ask-page">
      <header>
        <h1 className="text-2xl font-semibold">Ask Hermes</h1>
        <p className="text-sm text-gray-600">
          Free-form question across every meeting in this workspace. Hermes
          searches transcripts and memory cards, then cites the sources.
        </p>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim().length === 0) return;
          ask.mutate();
        }}
        className="flex gap-2"
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What did we decide about the auth migration?"
          className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm focus:border-gray-500 focus:outline-none"
          aria-label="Ask a workspace-wide question"
        />
        <button
          type="submit"
          disabled={ask.isPending || question.trim().length === 0}
          className="rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {ask.isPending ? 'Asking…' : 'Ask'}
        </button>
      </form>

      {ask.isError && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          Sorry — the workspace QA service is unavailable. Try again later.
        </div>
      )}

      {ask.data && (
        <section className="space-y-4" data-testid="ask-answer">
          <div className="rounded border border-gray-200 bg-white p-4">
            <div className="flex items-center justify-between text-xs text-gray-500">
              <span>
                Confidence:{' '}
                <span className="font-medium text-gray-800">
                  {(ask.data.confidence * 100).toFixed(0)}%
                </span>
              </span>
              {ask.data.weak_evidence && (
                <span className="rounded bg-yellow-100 px-2 py-0.5 text-yellow-800">
                  Weak evidence
                </span>
              )}
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-gray-900">
              {ask.data.answer}
            </p>
          </div>

          {ask.data.citations.length > 0 && (
            <div>
              <h2 className="text-sm font-medium text-gray-700">Citations</h2>
              <ul className="mt-2 space-y-2">
                {ask.data.citations.map((c, i) => (
                  <li key={`${c.meeting_id}-${c.memory_card_id ?? c.segment_id ?? i}`}>
                    <Link
                      to={citationLink(workspaceId, c)}
                      className="block rounded border border-gray-100 px-3 py-2 hover:bg-gray-50"
                    >
                      <div className="text-xs text-gray-500">
                        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-600">
                          {citationLabel(c)}
                        </span>{' '}
                        · {c.meeting_title || 'Untitled meeting'}
                      </div>
                      <div className="mt-1 text-sm text-gray-800">
                        {c.snippet}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
