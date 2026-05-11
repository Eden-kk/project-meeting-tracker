import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, act, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import MeetingsPage from '../MeetingsPage';
import * as registry from '../../lib/meetingsRegistry';
import type { StoredMeetingSummary } from '../../lib/meetingsRegistry';

function fixture(id: string, overrides: Partial<StoredMeetingSummary> = {}): StoredMeetingSummary {
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

function renderPage() {
  return render(
    <MemoryRouter>
      <MeetingsPage />
    </MemoryRouter>,
  );
}

describe('MeetingsPage', () => {
  beforeEach(() => {
    localStorage.clear();
    registry._resetMigrationLatch();
  });

  it('shows empty state when registry is empty', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: /no meetings yet/i })).toBeInTheDocument();
  });

  it('search filters by case-insensitive title substring', async () => {
    const user = userEvent.setup();
    act(() => {
      registry.upsert(fixture('m1', { title: 'Quarterly review' }));
      registry.upsert(fixture('m2', { title: 'Daily standup' }));
    });
    renderPage();
    const search = screen.getByLabelText(/search meetings/i);
    await user.type(search, 'STAND');
    expect(screen.getByRole('link', { name: 'Daily standup' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Quarterly review' })).not.toBeInTheDocument();
  });

  it('source filter chip narrows the list', async () => {
    const user = userEvent.setup();
    act(() => {
      registry.upsert(fixture('m1', { title: 'Voice one', source_type: 'voice_file' }));
      registry.upsert(fixture('m2', { title: 'Pasted one', source_type: 'pasted_transcript' }));
    });
    renderPage();
    await user.click(screen.getByRole('button', { name: /^voice file$/i }));
    expect(screen.getByRole('link', { name: 'Voice one' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Pasted one' })).not.toBeInTheDocument();
  });

  it('pattern chips appear only for patterns present in the registry', () => {
    act(() => {
      registry.upsert(fixture('m1', { detected_pattern: 'kickoff' }));
      registry.upsert(fixture('m2', { detected_pattern: null }));
    });
    renderPage();
    expect(screen.getByRole('button', { name: 'kickoff' })).toBeInTheDocument();
  });

  it('view toggle switches between table and cards', async () => {
    const user = userEvent.setup();
    act(() => {
      registry.upsert(fixture('m1'));
    });
    renderPage();
    expect(screen.getByRole('table')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^cards$/i }));
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    // The card layout uses MeetingCard (a link); verify the meeting link renders
    const links = screen.getAllByRole('link');
    expect(links.some((l) => l.getAttribute('href') === '/meetings/m1')).toBe(true);
  });

  it('shows "no meetings match" when filters exclude every entry', async () => {
    const user = userEvent.setup();
    act(() => {
      registry.upsert(fixture('m1', { status: 'ready' }));
    });
    renderPage();
    await user.click(screen.getByRole('button', { name: /^failed$/i }));
    expect(screen.getByText(/no meetings match the current filters/i)).toBeInTheDocument();
    // sanity: the chip-row label "Status" is still there
    const statusRow = screen.getByText('Status').parentElement!;
    expect(within(statusRow).getByRole('button', { name: 'failed' })).toBeInTheDocument();
  });
});
