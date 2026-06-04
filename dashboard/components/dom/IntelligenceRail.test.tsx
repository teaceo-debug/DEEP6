import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IntelligenceRail } from './IntelligenceRail';
import type { IntelligenceRailState } from '@/types/deep6';

const FIXTURE_STATE: IntelligenceRailState = {
  total_events: 47,
  active_detectors: [
    {
      detector_id: 'dom.imbalance.v1',
      name: 'Order Book Imbalance',
      tier: 'MECHANICAL',
      fire_count: 12,
      last_direction: 1,
      last_confidence: 0.85,
    },
    {
      detector_id: 'dom.absorption.v1',
      name: 'Absorption',
      tier: 'MECHANICAL',
      fire_count: 8,
      last_direction: -1,
      last_confidence: 0.72,
    },
    {
      detector_id: 'dom.pull_replace.v1',
      name: 'Pull/Replace Trap',
      tier: 'HEURISTIC',
      fire_count: 3,
      last_direction: 0,
      last_confidence: 0.45,
    },
  ],
  score_summary: {
    mechanical_score: 0.78,
    heuristic_score: 0.45,
    overall_direction: 1,
  },
  updated_at: Date.now(),
};

describe('IntelligenceRail', () => {
  it('renders with aria-label', () => {
    render(<IntelligenceRail state={FIXTURE_STATE} />);
    expect(screen.getByRole('complementary', { name: 'DOM Intelligence Rail' })).toBeTruthy();
  });

  it('displays overall direction', () => {
    render(<IntelligenceRail state={FIXTURE_STATE} />);
    expect(screen.getByTestId('overall-direction').textContent).toBe('LONG');
  });

  it('displays total event count', () => {
    render(<IntelligenceRail state={FIXTURE_STATE} />);
    expect(screen.getByTestId('event-counts').textContent).toContain('Events: 47');
  });

  it('displays mechanical and heuristic counts', () => {
    render(<IntelligenceRail state={FIXTURE_STATE} />);
    const counts = screen.getByTestId('event-counts').textContent ?? '';
    expect(counts).toContain('Mech: 2');
    expect(counts).toContain('Heur: 1');
  });

  it('renders all active detectors', () => {
    render(<IntelligenceRail state={FIXTURE_STATE} />);
    expect(screen.getByTestId('detector-dom.imbalance.v1')).toBeTruthy();
    expect(screen.getByTestId('detector-dom.absorption.v1')).toBeTruthy();
    expect(screen.getByTestId('detector-dom.pull_replace.v1')).toBeTruthy();
  });

  it('displays detector names', () => {
    render(<IntelligenceRail state={FIXTURE_STATE} />);
    expect(screen.getByText('Order Book Imbalance')).toBeTruthy();
    expect(screen.getByText('Absorption')).toBeTruthy();
    expect(screen.getByText('Pull/Replace Trap')).toBeTruthy();
  });

  it('displays score summary values', () => {
    render(<IntelligenceRail state={FIXTURE_STATE} />);
    const summary = screen.getByTestId('score-summary');
    expect(summary.textContent).toContain('M: 0.78');
    expect(summary.textContent).toContain('H: 0.45');
  });

  it('shows empty state message when no detectors', () => {
    const emptyState: IntelligenceRailState = {
      ...FIXTURE_STATE,
      active_detectors: [],
    };
    render(<IntelligenceRail state={emptyState} />);
    expect(screen.getByText('No active detectors')).toBeTruthy();
  });

  it('displays confidence as percentage', () => {
    render(<IntelligenceRail state={FIXTURE_STATE} />);
    expect(screen.getByText('85%')).toBeTruthy();
    expect(screen.getByText('72%')).toBeTruthy();
  });
});
