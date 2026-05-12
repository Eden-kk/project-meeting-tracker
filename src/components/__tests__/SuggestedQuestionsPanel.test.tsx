import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SuggestedQuestionsPanel } from '../SuggestedQuestionsPanel';

describe('SuggestedQuestionsPanel (Q1)', () => {
  it('renders the placeholder when questions is null and active', () => {
    render(<SuggestedQuestionsPanel questions={null} active={true} />);
    expect(
      screen.getByTestId('suggested-questions-placeholder'),
    ).toHaveTextContent('Hermes is preparing the first batch of questions… (≤60s)');
  });

  it('renders 3 questions as a numbered list', () => {
    const qs = [
      'Tell me about your experience with distributed systems.',
      'How do you handle on-call incidents?',
      'What would you change about your current team process?',
    ];
    render(<SuggestedQuestionsPanel questions={qs} active={true} />);
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent(qs[0]);
    expect(items[2]).toHaveTextContent(qs[2]);
  });

  it('renders all items in the array as given', () => {
    const qs = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5'];
    render(<SuggestedQuestionsPanel questions={qs} active={true} />);
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(5);
    expect(items[4]).toHaveTextContent('Q5');
  });
});
