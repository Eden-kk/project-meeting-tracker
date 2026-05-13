import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DeleteMeetingDialog } from '../DeleteMeetingDialog';
import * as client from '../../api/client';

const MEETING = { id: 'm_test_1', title: 'Sprint Planning' };
const WS_ID = 'ws_test';

function renderDialog(overrides?: Partial<Parameters<typeof DeleteMeetingDialog>[0]>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const onClose = vi.fn();
  const onDeleted = vi.fn();
  const utils = render(
    <QueryClientProvider client={qc}>
      <DeleteMeetingDialog
        meeting={MEETING}
        workspaceId={WS_ID}
        onClose={onClose}
        onDeleted={onDeleted}
        {...overrides}
      />
    </QueryClientProvider>,
  );
  return { onClose, onDeleted, ...utils };
}

describe('DeleteMeetingDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the meeting title in the confirm body', () => {
    vi.spyOn(client, 'deleteMeeting').mockResolvedValue({
      meeting_id: MEETING.id,
      deleted_at: new Date().toISOString(),
      blob_removed: true,
    });
    renderDialog();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Sprint Planning/)).toBeInTheDocument();
    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();
  });

  it('calls onClose when Cancel is clicked', async () => {
    vi.spyOn(client, 'deleteMeeting').mockResolvedValue({
      meeting_id: MEETING.id,
      deleted_at: new Date().toISOString(),
      blob_removed: true,
    });
    const { onClose } = renderDialog();
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onDeleted and onClose after successful delete', async () => {
    const spy = vi.spyOn(client, 'deleteMeeting').mockResolvedValue({
      meeting_id: MEETING.id,
      deleted_at: new Date().toISOString(),
      blob_removed: true,
    });
    const { onClose, onDeleted } = renderDialog();
    await userEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith(MEETING.id));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows inline 409 error and keeps dialog open', async () => {
    const err = Object.assign(new Error('already deleted'), { response: { status: 409 } });
    vi.spyOn(client, 'deleteMeeting').mockRejectedValue(err);
    const { onClose, onDeleted } = renderDialog();
    await userEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    await waitFor(() =>
      expect(screen.getByText(/already been deleted/i)).toBeInTheDocument(),
    );
    expect(onDeleted).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});
