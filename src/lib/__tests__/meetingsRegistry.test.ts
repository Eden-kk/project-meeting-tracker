import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  STORAGE_KEY,
  _resetMigrationLatch,
  clear,
  exportJson,
  get,
  list,
  patch,
  remove,
  subscribe,
  upsert,
  type StoredMeetingSummary,
} from '../meetingsRegistry';

function fixture(id: string, overrides: Partial<StoredMeetingSummary> = {}): StoredMeetingSummary {
  return {
    meeting_id: id,
    artifact_id: 'a_' + id,
    title: 'Title ' + id,
    imported_at: '2025-01-01T00:00:00.000Z',
    source_type: 'pasted_transcript',
    detected_pattern: null,
    evidence_quality: 'medium',
    status: 'ready',
    last_seen_at: '2025-01-01T00:00:00.000Z',
    ...overrides,
  };
}

describe('meetingsRegistry', () => {
  beforeEach(() => {
    localStorage.clear();
    _resetMigrationLatch();
  });

  it('upsert + list + get round-trips', () => {
    upsert(fixture('m1'));
    upsert(fixture('m2', { title: 'two' }));
    expect(list().map((s) => s.meeting_id).sort()).toEqual(['m1', 'm2']);
    expect(get('m2')?.title).toBe('two');
  });

  it('patch updates fields without touching others', () => {
    upsert(fixture('m1', { status: 'processing' }));
    patch('m1', { status: 'ready', last_seen_at: '2025-02-01T00:00:00.000Z' });
    const got = get('m1');
    expect(got?.status).toBe('ready');
    expect(got?.last_seen_at).toBe('2025-02-01T00:00:00.000Z');
    expect(got?.title).toBe('Title m1');
  });

  it('patch on missing id is a noop', () => {
    patch('ghost', { status: 'failed' });
    expect(get('ghost')).toBeNull();
  });

  it('remove deletes the entry', () => {
    upsert(fixture('m1'));
    remove('m1');
    expect(get('m1')).toBeNull();
  });

  it('treats parse failures as empty without throwing', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    localStorage.setItem(STORAGE_KEY, '{not json');
    expect(list()).toEqual([]);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('migrates legacy meeting-title:* keys on first read and deletes them', () => {
    localStorage.setItem('meeting-title:legacy-1', 'Old One');
    localStorage.setItem('meeting-title:legacy-2', 'Old Two');
    const result = list();
    const ids = result.map((s) => s.meeting_id).sort();
    expect(ids).toEqual(['legacy-1', 'legacy-2']);
    expect(localStorage.getItem('meeting-title:legacy-1')).toBeNull();
    expect(localStorage.getItem('meeting-title:legacy-2')).toBeNull();
    const found = result.find((s) => s.meeting_id === 'legacy-1');
    expect(found?.title).toBe('Old One');
    expect(found?.imported_at).toBe(new Date(0).toISOString());
  });

  it('does not overwrite an existing registry entry during legacy migration', () => {
    upsert(fixture('legacy-1', { title: 'Real Title' }));
    _resetMigrationLatch();
    localStorage.setItem('meeting-title:legacy-1', 'Old Title');
    list();
    expect(get('legacy-1')?.title).toBe('Real Title');
    expect(localStorage.getItem('meeting-title:legacy-1')).toBeNull();
  });

  it('subscribe fires on upsert/patch/remove/clear', () => {
    const cb = vi.fn();
    const unsub = subscribe(cb);
    upsert(fixture('m1'));
    patch('m1', { status: 'failed' });
    remove('m1');
    clear();
    unsub();
    upsert(fixture('m2'));
    expect(cb).toHaveBeenCalledTimes(4);
  });

  it('exportJson returns a stringified array', () => {
    upsert(fixture('m1'));
    const parsed = JSON.parse(exportJson());
    expect(Array.isArray(parsed)).toBe(true);
    expect(parsed[0].meeting_id).toBe('m1');
  });
});
