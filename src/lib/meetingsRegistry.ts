/**
 * Per-browser meetings registry, backed by localStorage.
 *
 * Single source of truth for the library page (no backend listing endpoint
 * exists in Phase 1). Each page that loads a meeting opportunistically
 * refreshes its registry entry from the API response, so the registry is
 * eventually consistent with the server.
 *
 * Concurrency: last-write-wins on the whole `StoredMeetingSummary` blob.
 * `patch()` reads → spreads → writes synchronously; cross-tab interleaving
 * may lose a field but is acceptable for Phase 1 (single-user).
 *
 * Schema version: the `:v1` key suffix is the version. On read, if a future
 * `:v2` key exists, prefer it and ignore `:v1`. On parse failure of any
 * version, log a warning and treat as empty.
 *
 * Notification: writes dispatch a `change` event on a module-level
 * EventTarget so the writing tab re-renders. Cross-tab updates arrive via
 * the browser's native `storage` event (handled in useMeetingsRegistry).
 */
import type { components } from '../api/types';

type MeetingStatus = components['schemas']['Meeting']['status'];
type SegmentSourceType = components['schemas']['SpeakerSegment']['source_type'];
type EvidenceQuality = components['schemas']['Meeting']['evidence_quality'];

export type StoredMeetingSummary = {
  meeting_id: string;
  artifact_id: string;
  title: string;
  imported_at: string; // ISO 8601, set on first registry write
  source_type: SegmentSourceType;
  detected_pattern: string | null;
  evidence_quality: EvidenceQuality;
  status: MeetingStatus;
  last_seen_at: string; // ISO, updated on every API refresh
};

export const STORAGE_KEY = 'tracker:meetings:v1';
const LEGACY_TITLE_PREFIX = 'meeting-title:';

const bus = new EventTarget();
export const REGISTRY_CHANGE_EVENT = 'change';

let migrated = false;

function readRaw(): Record<string, StoredMeetingSummary> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return {};
    return parsed as Record<string, StoredMeetingSummary>;
  } catch (err) {
    console.warn('[meetingsRegistry] failed to parse storage; treating as empty', err);
    return {};
  }
}

function writeRaw(table: Record<string, StoredMeetingSummary>): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(table));
  bus.dispatchEvent(new Event(REGISTRY_CHANGE_EVENT));
}

function migrateLegacyKeysOnce(table: Record<string, StoredMeetingSummary>): Record<string, StoredMeetingSummary> {
  if (migrated) return table;
  migrated = true;
  const epoch = new Date(0).toISOString();
  const next = { ...table };
  let dirty = false;
  const toRemove: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key || !key.startsWith(LEGACY_TITLE_PREFIX)) continue;
    const id = key.slice(LEGACY_TITLE_PREFIX.length);
    toRemove.push(key);
    if (next[id]) continue;
    const title = localStorage.getItem(key) ?? 'Untitled meeting';
    next[id] = {
      meeting_id: id,
      artifact_id: '',
      title,
      imported_at: epoch,
      source_type: 'transcript_file',
      detected_pattern: null,
      evidence_quality: 'unknown',
      status: 'ready',
      last_seen_at: epoch,
    };
    dirty = true;
  }
  for (const key of toRemove) localStorage.removeItem(key);
  if (dirty) writeRaw(next);
  return next;
}

export function list(): StoredMeetingSummary[] {
  const table = migrateLegacyKeysOnce(readRaw());
  return Object.values(table);
}

export function get(id: string): StoredMeetingSummary | null {
  const table = migrateLegacyKeysOnce(readRaw());
  return table[id] ?? null;
}

export function upsert(summary: StoredMeetingSummary): void {
  const table = migrateLegacyKeysOnce(readRaw());
  table[summary.meeting_id] = summary;
  writeRaw(table);
}

export function patch(id: string, partial: Partial<StoredMeetingSummary>): void {
  const table = migrateLegacyKeysOnce(readRaw());
  const existing = table[id];
  if (!existing) return;
  table[id] = { ...existing, ...partial };
  writeRaw(table);
}

export function remove(id: string): void {
  const table = migrateLegacyKeysOnce(readRaw());
  if (!(id in table)) return;
  delete table[id];
  writeRaw(table);
}

export function exportJson(): string {
  return JSON.stringify(list(), null, 2);
}

export function clear(): void {
  localStorage.removeItem(STORAGE_KEY);
  bus.dispatchEvent(new Event(REGISTRY_CHANGE_EVENT));
}

export function subscribe(listener: () => void): () => void {
  bus.addEventListener(REGISTRY_CHANGE_EVENT, listener);
  return () => bus.removeEventListener(REGISTRY_CHANGE_EVENT, listener);
}

/** Test-only helper. Resets the once-per-tab migration latch. */
export function _resetMigrationLatch(): void {
  migrated = false;
}
