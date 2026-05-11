import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ImportPage from '../ImportPage';
import * as client from '../../api/client';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ImportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ImportPage', () => {
  beforeEach(() => {
    navigateMock.mockReset();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('shows error when title is empty and skips mutation', async () => {
    const spy = vi.spyOn(client, 'importConversation').mockResolvedValue({
      artifact_id: 'a',
      meeting_id: 'm',
      processing_status: 'received',
    });
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));
    expect(await screen.findByText(/title is required/i)).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it('paste + submit calls importConversation with pasted_transcript and navigates', async () => {
    const spy = vi.spyOn(client, 'importConversation').mockResolvedValue({
      artifact_id: 'art_1',
      meeting_id: 'm_1',
      processing_status: 'received',
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole('tab', { name: /paste transcript/i }));
    await user.type(screen.getByLabelText(/pasted transcript/i), 'hello world');
    await user.type(screen.getByLabelText(/^title$/i), 'My meeting');
    await user.click(screen.getByRole('button', { name: /submit/i }));

    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    const arg = spy.mock.calls[0][0];
    expect(arg.pasted_transcript).toBe('hello world');
    expect(arg.title).toBe('My meeting');
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/meetings/m_1/processing'));
    expect(localStorage.getItem('meeting-title:m_1')).toBe('My meeting');
  });

  it('shows size error when file exceeds 100 MB', async () => {
    const user = userEvent.setup();
    renderPage();
    const big = new File([new Uint8Array(1)], 'big.wav', { type: 'audio/wav' });
    Object.defineProperty(big, 'size', { value: 200 * 1024 * 1024 });
    const fileInput = screen.getByLabelText(/upload file/i) as HTMLInputElement;
    await user.upload(fileInput, big);
    expect(await screen.findByText(/exceeds 100 MB limit/i)).toBeInTheDocument();
  });
});
