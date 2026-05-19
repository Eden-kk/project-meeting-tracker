import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ZoomUrlForm } from '../ZoomUrlForm';
import * as client from '../../api/client';

describe('ZoomUrlForm', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the disclosure copy + URL input + submit button', () => {
    render(<ZoomUrlForm workspaceId="ws_dev" />);
    expect(
      screen.getByText(/Hermes — Note-taking Bot/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Zoom meeting URL/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Dispatch Hermes/i }),
    ).toBeDisabled();
  });

  it('keeps the submit button disabled for invalid URLs', async () => {
    render(<ZoomUrlForm workspaceId="ws_dev" />);
    const input = screen.getByLabelText(/Zoom meeting URL/i);
    await userEvent.type(input, 'https://example.com/foo');
    expect(
      screen.getByRole('button', { name: /Dispatch Hermes/i }),
    ).toBeDisabled();
    expect(screen.getByTestId('zoom-url-validation')).toBeInTheDocument();
  });

  it('dispatches the bot and clears the URL on happy path', async () => {
    const spy = vi.spyOn(client, 'dispatchZoomBot').mockResolvedValue({
      meeting_id: 'm_zoom_1',
      artifact_id: 'art_1',
      zoom_meeting_number: '85412345678',
      status: 'live',
    });
    const onDispatched = vi.fn();
    render(<ZoomUrlForm workspaceId="ws_dev" onDispatched={onDispatched} />);

    const input = screen.getByLabelText(/Zoom meeting URL/i);
    await userEvent.type(
      input,
      'https://zoom.us/j/85412345678?pwd=abc',
    );
    await userEvent.click(
      screen.getByRole('button', { name: /Dispatch Hermes/i }),
    );

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({
        workspaceId: 'ws_dev',
        zoomUrl: 'https://zoom.us/j/85412345678?pwd=abc',
        title: 'Zoom meeting',
      }),
    );
    expect(onDispatched).toHaveBeenCalledWith(
      expect.objectContaining({ meeting_id: 'm_zoom_1' }),
    );
    // After dispatch, the URL input is cleared.
    expect((input as HTMLInputElement).value).toBe('');
  });

  it('shows the API error message on failure', async () => {
    vi.spyOn(client, 'dispatchZoomBot').mockRejectedValue(
      new Error('bot pool full'),
    );
    render(<ZoomUrlForm workspaceId="ws_dev" />);

    await userEvent.type(
      screen.getByLabelText(/Zoom meeting URL/i),
      'https://zoom.us/j/12345',
    );
    await userEvent.click(
      screen.getByRole('button', { name: /Dispatch Hermes/i }),
    );

    await waitFor(() =>
      expect(screen.getByTestId('zoom-url-error')).toHaveTextContent(
        /bot pool full/i,
      ),
    );
  });
});
