import { api } from './client';
import type { components } from './types';

export type ImportJob = components['schemas']['ImportJob'];

export async function getImportJob(id: string): Promise<ImportJob> {
  return (await api.get<ImportJob>(`/api/meetings/${id}/import-job`)).data;
}

export async function controlImportJob(
  id: string, action: 'cancel' | 'retry', remoteStopped = false,
): Promise<ImportJob> {
  return (await api.post<ImportJob>(`/api/meetings/${id}/import-job/${action}`,
    action === 'retry' ? { remote_stopped: remoteStopped } : undefined)).data;
}
