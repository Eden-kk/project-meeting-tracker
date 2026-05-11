import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HomePage from '../HomePage';
import * as registry from '../../lib/meetingsRegistry';

function fixture(id: string, overrides: Partial<registry.StoredMeetingSummary> = {}): registry.StoredMeetingSummary {
  return {
    meeting_id: id,
    artifact_id: 'a' + id,
    title: 'Meeting ' + id,
    imported_at: '2025-01-15T10:00:00.000Z',
    source_type: 'pasted_transcript',
    detected_pattern: null,
    evidence_quality: 'medium',
    status: 'ready',
    last_seen_at: '2025-01-15T10:00:00.000Z',
    ...overrides,
  };
}

function renderHome() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  );
}

describe('HomePage', () => {
  beforeEach(() => {
    localStorage.clear();
    registry._resetMigrationLatch();
  });

  it('shows empty state when registry is empty', () => {
    renderHome();
    expect(screen.getByRole('heading', { name: /no meetings yet/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^new import$/i })).toHaveAttribute('href', '/import');
  });

  it('shows stats and recent cards when registry has entries', () => {
    act(() => {
      registry.upsert(fixture('m1', { title: 'A', imported_at: '2025-02-01T00:00:00.000Z', status: 'processing' }));
      registry.upsert(fixture('m2', { title: 'B', imported_at: '2025-02-02T00:00:00.000Z', status: 'failed' }));
      registry.upsert(fixture('m3', { title: 'C', imported_at: '2025-02-03T00:00:00.000Z', status: 'ready' }));
    });
    renderHome();
    expect(screen.getByText('Total')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('1 / 1 / 1')).toBeInTheDocument();
    // Most recent first
    const cards = screen.getAllByRole('link').filter((a) => a.getAttribute('href')?.startsWith('/meetings/'));
    expect(cards[0]).toHaveTextContent('C');
  });

  it('caps recent cards at 6', () => {
    act(() => {
      for (let i = 0; i < 9; i++) {
        registry.upsert(fixture('m' + i, { imported_at: `2025-03-0${(i % 9) + 1}T00:00:00.000Z` }));
      }
    });
    renderHome();
    const cards = screen.getAllByRole('link').filter((a) => a.getAttribute('href')?.startsWith('/meetings/'));
    expect(cards).toHaveLength(6);
  });
});
