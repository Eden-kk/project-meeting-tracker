type Props = {
  /** Latest suggested questions from the backend; null until the first ~60s tick. */
  questions: string[] | null;
  /** Whether the meeting is currently live (controls placeholder text). */
  active: boolean;
};

/**
 * Q1 — compact panel that surfaces the latest 3-5 interview questions
 * proposed by the live-interview-questioner skill. Refreshed every ~60s
 * by the backend (overwrite, not append). The parent reads the value from
 * the existing /segments poll response so no second round-trip is needed.
 */
export function SuggestedQuestionsPanel({ questions, active }: Props) {
  return (
    <aside
      data-testid="suggested-questions-panel"
      className="rounded border border-violet-200 bg-violet-50 p-4"
    >
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-violet-900">
        Suggested questions
      </h2>
      {questions && questions.length > 0 ? (
        <ol
          className="list-decimal space-y-1 pl-4"
          data-testid="suggested-questions-list"
        >
          {questions.map((q, i) => (
            <li key={i} className="text-sm text-violet-950">
              {q}
            </li>
          ))}
        </ol>
      ) : (
        <p
          className="text-sm italic text-violet-700"
          data-testid="suggested-questions-placeholder"
        >
          {active
            ? 'Hermes is preparing the first batch of questions… (≤60s)'
            : 'Start the meeting to begin.'}
        </p>
      )}
    </aside>
  );
}
