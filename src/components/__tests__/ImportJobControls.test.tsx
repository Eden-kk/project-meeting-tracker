import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ImportJobControls } from '../ImportJobControls';
import * as jobs from '../../api/importJobs';
import { queryKeys } from '../../api/queryKeys';

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  render(<QueryClientProvider client={client}><ImportJobControls id="m_1" /></QueryClientProvider>);
  return invalidate;
}

describe('ImportJobControls', () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it('requires remote-stop confirmation before retrying a started job', async () => {
    vi.spyOn(jobs, 'getImportJob').mockResolvedValue({ status: 'failed', attempts: 1, error: 'Failed' });
    const retry = vi.spyOn(jobs, 'controlImportJob').mockResolvedValue({ status: 'received', attempts: 1, error: null });
    const invalidate = show();
    const button = await screen.findByRole('button', { name: 'Retry import' });
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(button);
    await waitFor(() => expect(retry).toHaveBeenCalledWith('m_1', 'retry', true));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.meeting('m_1') }));
    expect(await screen.findByRole('button', { name: 'Cancel import' })).toBeEnabled();
  });

  it('allows retry without confirmation when no attempt has started', async () => {
    vi.spyOn(jobs, 'getImportJob').mockResolvedValue({ status: 'cancelled', attempts: 0, error: null });
    const retry = vi.spyOn(jobs, 'controlImportJob').mockResolvedValue({ status: 'received', attempts: 0, error: null });
    show();
    fireEvent.click(await screen.findByRole('button', { name: 'Retry import' }));
    await waitFor(() => expect(retry).toHaveBeenCalledWith('m_1', 'retry', false));
  });

  it('cancels locally and disables controls while the request is pending', async () => {
    vi.spyOn(jobs, 'getImportJob').mockResolvedValue({ status: 'parsing', attempts: 1, error: null });
    let resolve!: (value: jobs.ImportJob) => void;
    const cancel = vi.spyOn(jobs, 'controlImportJob').mockImplementation(() => new Promise(r => { resolve = r; }));
    show();
    const button = await screen.findByRole('button', { name: 'Cancel import' });
    fireEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    expect(screen.getByText(/does not stop remote computation/)).toBeInTheDocument();
    resolve({ status: 'cancelled', attempts: 1, error: null });
    expect(await screen.findByRole('button', { name: 'Retry import' })).toBeDisabled();
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it('reconciles ambiguous mutation errors without automatic retry', async () => {
    vi.spyOn(jobs, 'getImportJob').mockResolvedValue({ status: 'received', attempts: 0, error: null });
    const cancel = vi.spyOn(jobs, 'controlImportJob').mockRejectedValue(new Error('network'));
    const invalidate = show();
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel import' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Action not confirmed');
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['import-job', 'm_1'] });
  });

  it('shows query failures instead of presenting guessed controls', async () => {
    vi.spyOn(jobs, 'getImportJob').mockRejectedValue(new Error('network'));
    show();
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('does not offer ingestion retry once ready', async () => {
    vi.spyOn(jobs, 'getImportJob').mockResolvedValue({ status: 'ready', attempts: 1, error: null });
    show();
    await waitFor(() => expect(jobs.getImportJob).toHaveBeenCalled());
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
