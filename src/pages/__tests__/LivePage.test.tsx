import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import LivePage from '../LivePage';

// MediaRecorder + getUserMedia are JSDOM-unfriendly; the recording flow is
// validated manually via the handbook + by Playwright with a mocked backend.
// This test only asserts the idle render so we still catch trivial regressions
// (missing copy, broken JSX, etc.).
describe('LivePage', () => {
  it('renders the idle controls', () => {
    render(
      <MemoryRouter>
        <LivePage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', { name: /live meeting/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /start meeting/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/title/i)).toHaveValue('Live meeting');
    expect(screen.getByTestId('live-phase')).toHaveTextContent('idle');
  });
});
