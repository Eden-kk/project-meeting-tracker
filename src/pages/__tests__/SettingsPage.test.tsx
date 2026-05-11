import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import SettingsPage from '../SettingsPage';

describe('SettingsPage', () => {
  it('renders heading and phase callouts', () => {
    render(<SettingsPage />);
    expect(screen.getByRole('heading', { name: /settings/i })).toBeInTheDocument();
    expect(screen.getByText(/workspace settings — phase 2/i)).toBeInTheDocument();
    expect(screen.getByText(/theme — phase 2/i)).toBeInTheDocument();
    expect(screen.getByText(/export library json — phase 2\.1/i)).toBeInTheDocument();
  });
});
