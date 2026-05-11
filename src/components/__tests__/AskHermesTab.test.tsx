import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AskHermesTab } from '../AskHermesTab';
import * as client from '../../api/client';
import type { AskHermesResponse } from '../../api/memory_cards.types';

const MEETING_ID = 'm_test_1';

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AskHermesTab meetingId={MEETING_ID} onEvidenceClick={() => {}} />
    </QueryClientProvider>,
  );
}

function strongResponse(): AskHermesResponse {
  return {
    answer: 'The team decided to ship by end of Q1.',
    confidence: 0.78,
    weak_evidence: false,
    citations: [
      { segment_id: 'seg_001', speaker: 'Alice', start_ms: 0, end_ms: 5200, text: '...' },
      { segment_id: 'seg_002', speaker: 'Bob', start_ms: 5200, end_ms: 9000, text: '...' },
    ],
  };
}

function weakResponse(): AskHermesResponse {
  return {
    answer: 'Low confidence answer.',
    confidence: 0.32,
    weak_evidence: true,
    citations: [
      { segment_id: 'seg_001', speaker: 'Alice', start_ms: 0, end_ms: 5200, text: '...' },
    ],
  };
}

describe('AskHermesTab', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('sending a question renders the user message + an assistant message with citations', async () => {
    vi.spyOn(client, 'askHermes').mockResolvedValue(strongResponse());
    const user = userEvent.setup();
    renderTab();

    await user.type(screen.getByLabelText(/ask hermes/i), 'what was decided');
    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(await screen.findByText('what was decided')).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.getByText(/team decided to ship by end of q1/i),
      ).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('evidence-pill')).toHaveLength(2);
  });

  it('shows the low-confidence chip when weak_evidence is true', async () => {
    vi.spyOn(client, 'askHermes').mockResolvedValue(weakResponse());
    const user = userEvent.setup();
    renderTab();

    await user.type(screen.getByLabelText(/ask hermes/i), 'weak signal please');
    await user.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByTestId('low-confidence-chip')).toBeInTheDocument();
    });
  });

  it('disables the Send button while the mutation is pending', async () => {
    let resolve!: (r: AskHermesResponse) => void;
    vi.spyOn(client, 'askHermes').mockImplementation(
      () => new Promise<AskHermesResponse>((r) => (resolve = r)),
    );
    const user = userEvent.setup();
    renderTab();

    await user.type(screen.getByLabelText(/ask hermes/i), 'hello');
    const sendBtn = screen.getByRole('button', { name: /send/i });
    await user.click(sendBtn);

    await waitFor(() => expect(sendBtn).toBeDisabled());
    resolve(strongResponse());
    // After resolution and re-render, type fresh draft and the button enables.
    await waitFor(() => expect(screen.getByText(/team decided/i)).toBeInTheDocument());
    await user.type(screen.getByLabelText(/ask hermes/i), 'follow up');
    expect(sendBtn).not.toBeDisabled();
  });
});
