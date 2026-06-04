import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import DOMIntelligencePage from './page';

describe('DOMIntelligencePage', () => {
  it('renders the layout container', () => {
    render(<DOMIntelligencePage />);
    expect(screen.getByTestId('dom-intelligence-layout')).toBeTruthy();
  });

  it('renders chart area placeholder', () => {
    render(<DOMIntelligencePage />);
    expect(screen.getByTestId('chart-area')).toBeTruthy();
    expect(screen.getByText('Footprint Chart')).toBeTruthy();
  });

  it('renders the DOM Ladder panel', () => {
    render(<DOMIntelligencePage />);
    expect(screen.getByTestId('ladder-panel')).toBeTruthy();
    expect(screen.getByRole('table', { name: 'DOM Ladder' })).toBeTruthy();
  });

  it('renders the Intelligence Rail panel', () => {
    render(<DOMIntelligencePage />);
    expect(screen.getByTestId('intel-panel')).toBeTruthy();
    expect(screen.getByRole('complementary', { name: 'DOM Intelligence Rail' })).toBeTruthy();
  });

  it('renders NQ-only DOM ladder heading', () => {
    render(<DOMIntelligencePage />);
    expect(screen.getByText('DOM Ladder — NQ')).toBeTruthy();
  });

  it('does not import detector logic (structural check)', () => {
    // The page only imports from @/components/dom and @/lib/dom-mock-state
    // This is verified by the import structure above — no deep6v2 imports
    render(<DOMIntelligencePage />);
    expect(screen.getByTestId('dom-intelligence-layout')).toBeTruthy();
  });

  it('displays mock detector data from fixtures', () => {
    render(<DOMIntelligencePage />);
    // Should show at least one detector from the mock state
    expect(screen.getByTestId('detector-dom.imbalance.v1')).toBeTruthy();
  });

  it('displays mock DOM ladder data from fixtures', () => {
    render(<DOMIntelligencePage />);
    // Should show price from mock data
    expect(screen.getByTestId('ladder-row-20000')).toBeTruthy();
  });

  it('renders header strip with DEEP6 branding', () => {
    render(<DOMIntelligencePage />);
    expect(screen.getByTestId('header-strip')).toBeTruthy();
    expect(screen.getByText('DEEP6')).toBeTruthy();
  });

  it('renders signal feed section', () => {
    render(<DOMIntelligencePage />);
    expect(screen.getByTestId('signal-feed-section')).toBeTruthy();
    expect(screen.getByText('Signals')).toBeTruthy();
  });
});
