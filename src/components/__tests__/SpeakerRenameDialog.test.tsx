import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SpeakerRenameDialog } from '../SpeakerRenameDialog';
import * as client from '../../api/client';

describe('SpeakerRenameDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the dialog with the speaker id in the heading', () => {
    vi.spyOn(client, 'renameLiveSpeaker').mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(
      <SpeakerRenameDialog
        meetingId="m_1"
        speakerId="speaker_2"
        onSuccess={vi.fn()}
        onClose={onClose}
      />,
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/rename speaker_2/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/new name/i)).toBeInTheDocument();
  });

  it('calls renameLiveSpeaker and onSuccess on happy path', async () => {
    const spy = vi.spyOn(client, 'renameLiveSpeaker').mockResolvedValue(undefined);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    render(
      <SpeakerRenameDialog
        meetingId="m_1"
        speakerId="speaker_1"
        onSuccess={onSuccess}
        onClose={onClose}
      />,
    );

    await userEvent.type(screen.getByLabelText(/new name/i), 'Alice');
    await userEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(spy).toHaveBeenCalledWith('m_1', 'speaker_1', 'Alice'));
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it('shows an error message on API failure', async () => {
    vi.spyOn(client, 'renameLiveSpeaker').mockRejectedValue(new Error('server error'));
    render(
      <SpeakerRenameDialog
        meetingId="m_1"
        speakerId="speaker_1"
        onSuccess={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    await userEvent.type(screen.getByLabelText(/new name/i), 'Bob');
    await userEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() =>
      expect(screen.getByText(/server error/i)).toBeInTheDocument(),
    );
  });
});
