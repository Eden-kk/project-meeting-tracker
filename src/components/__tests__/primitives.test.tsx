import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { EmptyState } from '../EmptyState';
import { StatChip } from '../StatChip';
import { SourceIcon, sourceLabel } from '../SourceIcon';
import { StatusPill } from '../StatusPill';
import { MeetingCard } from '../MeetingCard';
import { MeetingTable } from '../MeetingTable';
import type { StoredMeetingSummary } from '../../lib/meetingsRegistry';

function wsWrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/ws/ws_dev/']}>
        <Routes>
          <Route path="/ws/:workspaceId/*" element={<>{children}</>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function fix(id: string, overrides: Partial<StoredMeetingSummary> = {}): StoredMeetingSummary {
  return {
    meeting_id: id,
    artifact_id: 'a' + id,
    title: 'Meeting ' + id,
    imported_at: '2025-01-15T10:00:00.000Z',
    source_type: 'pasted_transcript',
    detected_pattern: 'kickoff',
    evidence_quality: 'medium',
    status: 'ready',
    last_seen_at: '2025-01-15T10:00:00.000Z',
    ...overrides,
  };
}

describe('EmptyState', () => {
  it('renders title, body, and CTA link', () => {
    render(
      <MemoryRouter>
        <EmptyState title="No meetings yet" body="Click import to begin." cta={{ to: '/import', label: 'Import' }} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { name: /no meetings yet/i })).toBeInTheDocument();
    expect(screen.getByText(/click import to begin/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /import/i })).toHaveAttribute('href', '/import');
  });
});

describe('StatChip', () => {
  it('renders label and value', () => {
    render(<StatChip label="Total" value={42} />);
    expect(screen.getByText('Total')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });
});

describe('SourceIcon', () => {
  it('exposes a human label via aria-label', () => {
    render(<SourceIcon sourceType="voice_file" />);
    expect(screen.getByLabelText(/voice file/i)).toBeInTheDocument();
    expect(sourceLabel('zoom_rtms')).toBe('Zoom');
  });
});

describe('StatusPill', () => {
  it('renders the status label', () => {
    render(<StatusPill status="processing" />);
    expect(screen.getByText('Processing')).toBeInTheDocument();
  });
});

describe('MeetingCard', () => {
  it('links to the meeting detail page and shows title + status', () => {
    render(wsWrap(<MeetingCard meeting={fix('m1', { title: 'Q1 sync' })} />));
    expect(screen.getByRole('link')).toHaveAttribute('href', '/ws/ws_dev/meetings/m1');
    expect(screen.getByText('Q1 sync')).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
  });
});

describe('MeetingTable', () => {
  it('lists rows with title links and toggles sort on header click', async () => {
    const user = userEvent.setup();
    render(
      wsWrap(
        <MeetingTable meetings={[fix('m1', { title: 'Apple' }), fix('m2', { title: 'Banana' })]} />,
      ),
    );
    expect(screen.getByRole('link', { name: 'Apple' })).toHaveAttribute('href', '/ws/ws_dev/meetings/m1');
    await user.click(screen.getByRole('button', { name: /title/i }));
    const rows = screen.getAllByRole('row');
    // header row + data rows; first data row should be Apple in asc
    const firstDataRow = rows[1];
    expect(firstDataRow).toHaveTextContent('Apple');
  });
});
