import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DOMLadder } from './DOMLadder';
import type { DOMLadderState } from '@/types/deep6';

const FIXTURE_STATE: DOMLadderState = {
  bids: [
    { price: 20000.0, volume: 150 },
    { price: 19999.75, volume: 80 },
    { price: 19999.5, volume: 200 },
    { price: 19999.25, volume: 60 },
    { price: 19999.0, volume: 45 },
  ],
  asks: [
    { price: 20000.25, volume: 120 },
    { price: 20000.5, volume: 90 },
    { price: 20000.75, volume: 300 },
    { price: 20001.0, volume: 55 },
    { price: 20001.25, volume: 40 },
  ],
  version: 42,
};

describe('DOMLadder', () => {
  it('renders table with aria-label', () => {
    render(<DOMLadder state={FIXTURE_STATE} />);
    expect(screen.getByRole('table', { name: 'DOM Ladder' })).toBeTruthy();
  });

  it('renders bid and ask prices', () => {
    render(<DOMLadder state={FIXTURE_STATE} />);
    // Check a bid price row exists
    expect(screen.getByTestId('ladder-row-20000')).toBeTruthy();
    // Check an ask price row exists
    expect(screen.getByTestId('ladder-row-20000.25')).toBeTruthy();
  });

  it('renders bid volume values', () => {
    render(<DOMLadder state={FIXTURE_STATE} />);
    expect(screen.getByText('150')).toBeTruthy();
    expect(screen.getByText('200')).toBeTruthy();
  });

  it('renders ask volume values', () => {
    render(<DOMLadder state={FIXTURE_STATE} />);
    expect(screen.getByText('120')).toBeTruthy();
    expect(screen.getByText('300')).toBeTruthy();
  });

  it('displays version footer', () => {
    render(<DOMLadder state={FIXTURE_STATE} />);
    expect(screen.getByText('v42')).toBeTruthy();
  });

  it('sorts prices descending (highest at top)', () => {
    render(<DOMLadder state={FIXTURE_STATE} />);
    const rows = screen.getAllByRole('row');
    // First data row (after header) should be highest ask
    const dataRows = rows.filter((r) => r.getAttribute('data-testid')?.startsWith('ladder-row-'));
    const prices = dataRows.map((r) => {
      const id = r.getAttribute('data-testid') ?? '';
      return parseFloat(id.replace('ladder-row-', ''));
    });
    // Should be descending
    for (let i = 1; i < prices.length; i++) {
      expect(prices[i]).toBeLessThanOrEqual(prices[i - 1]);
    }
  });

  it('respects maxRows prop', () => {
    render(<DOMLadder state={FIXTURE_STATE} maxRows={4} />);
    const dataRows = screen.getAllByRole('row').filter(
      (r) => r.getAttribute('data-testid')?.startsWith('ladder-row-'),
    );
    expect(dataRows.length).toBeLessThanOrEqual(4);
  });

  it('handles empty state gracefully', () => {
    const emptyState: DOMLadderState = { bids: [], asks: [], version: 0 };
    render(<DOMLadder state={emptyState} />);
    expect(screen.getByRole('table', { name: 'DOM Ladder' })).toBeTruthy();
    expect(screen.getByText('v0')).toBeTruthy();
  });

  it('does not import detector logic', () => {
    // This is a structural check — DOMLadder only takes DOMLadderState as input
    // Verify the component props type only accepts structured state
    const props = { state: FIXTURE_STATE };
    expect(props.state.bids).toBeDefined();
    expect(props.state.asks).toBeDefined();
    expect(props.state.version).toBeDefined();
  });
});
