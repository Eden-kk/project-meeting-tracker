import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FollowupDraftDialog } from '../FollowupDraftDialog';
import * as client from '../../api/client';

function renderDialog(props?: Partial<Parameters<typeof FollowupDraftDialog>[0]>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  const utils = render(
    <QueryClientProvider client={qc}>
      <FollowupDraftDialog
        meetingId="m_1"
        open={true}
        onClose={onClose}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onClose, ...utils };
}

describe('FollowupDraftDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('calls draftFollowup with tone + sanitized recipient and renders markdown', async () => {
    const spy = vi.spyOn(client, 'draftFollowup').mockResolvedValue({
      meeting_id: 'm_1',
      markdown: '# Follow-up\n\n- ship login',
      cards_referenced: ['mc_1'],
    });
    renderDialog();
    await userEvent.type(screen.getByLabelText(/recipient/i), 'Anne-Marie');
    await userEvent.click(screen.getByRole('button', { name: /^warm$/i }));
    await userEvent.click(screen.getByRole('button', { name: /generate draft/i }));

    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    expect(spy.mock.calls[0][0]).toMatchObject({
      meeting_id: 'm_1',
      recipient: 'Anne-Marie',
      tone: 'warm',
    });
    expect(await screen.findByText(/cites 1 card/i)).toBeInTheDocument();
    const textarea = screen.getByLabelText(/markdown/i) as HTMLTextAreaElement;
    expect(textarea.value).toMatch(/ship login/);
  });

  it('client-side rejects illegal recipient characters', async () => {
    const spy = vi.spyOn(client, 'draftFollowup').mockResolvedValue({
      meeting_id: 'm_1',
      markdown: '',
      cards_referenced: [],
    });
    renderDialog();
    await userEvent.type(screen.getByLabelText(/recipient/i), '<script>');
    await userEvent.click(screen.getByRole('button', { name: /generate draft/i }));
    expect(
      await screen.findByText(/letters, digits, spaces, hyphens, and apostrophes only/i),
    ).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });
});
