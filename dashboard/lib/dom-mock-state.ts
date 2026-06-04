/**
 * dom-mock-state.ts — Deterministic fixture state for DOM intelligence components.
 *
 * Derived from golden session fixture data structure (golden_quiet_rth.json),
 * not hand-crafted values. All prices are NQ-only (20000 range).
 *
 * Used by: DOMLadder, IntelligenceRail, dom-intelligence page layout.
 */
import type {
  DOMLadderState,
  DOMLadderLevel,
  IntelligenceRailState,
  ActiveDetectorSummary,
} from '@/types/deep6';

// ── Golden session-derived DOM state ─────────────────────────────────────────
//
// These values mirror the price/volume structure from golden_quiet_rth.json.
// The golden fixture uses NQ tick size 0.25, prices around 20000.

const GOLDEN_BIDS: DOMLadderLevel[] = [
  { price: 20000.00, volume: 56 },
  { price: 19999.75, volume: 76 },
  { price: 19999.50, volume: 137 },
  { price: 19999.25, volume: 58 },
  { price: 19999.00, volume: 117 },
  { price: 19998.75, volume: 48 },
  { price: 19998.50, volume: 92 },
  { price: 19998.25, volume: 63 },
  { price: 19998.00, volume: 85 },
  { price: 19997.75, volume: 41 },
];

const GOLDEN_ASKS: DOMLadderLevel[] = [
  { price: 20000.25, volume: 124 },
  { price: 20000.50, volume: 112 },
  { price: 20000.75, volume: 187 },
  { price: 20001.00, volume: 72 },
  { price: 20001.25, volume: 55 },
  { price: 20001.50, volume: 98 },
  { price: 20001.75, volume: 43 },
  { price: 20002.00, volume: 67 },
  { price: 20002.25, volume: 31 },
  { price: 20002.50, volume: 89 },
];

export const MOCK_DOM_LADDER_STATE: DOMLadderState = {
  bids: GOLDEN_BIDS,
  asks: GOLDEN_ASKS,
  version: 1,
};

// ── Golden session-derived intelligence state ────────────────────────────────

const MOCK_DETECTORS: ActiveDetectorSummary[] = [
  {
    detector_id: 'dom.imbalance.v1',
    name: 'Order Book Imbalance',
    tier: 'MECHANICAL',
    fire_count: 14,
    last_direction: 1,
    last_confidence: 0.82,
  },
  {
    detector_id: 'dom.thinness.v1',
    name: 'Liquidity Thinness',
    tier: 'MECHANICAL',
    fire_count: 7,
    last_direction: -1,
    last_confidence: 0.65,
  },
  {
    detector_id: 'dom.absorption.v1',
    name: 'Absorption',
    tier: 'MECHANICAL',
    fire_count: 5,
    last_direction: 1,
    last_confidence: 0.91,
  },
  {
    detector_id: 'dom.sweep_reload.v1',
    name: 'Sweep + Reload',
    tier: 'MECHANICAL',
    fire_count: 3,
    last_direction: 1,
    last_confidence: 0.74,
  },
  {
    detector_id: 'dom.iceberg.v1',
    name: 'Iceberg Refill',
    tier: 'MECHANICAL',
    fire_count: 2,
    last_direction: 0,
    last_confidence: 0.58,
  },
  {
    detector_id: 'dom.pull_replace.v1',
    name: 'Pull/Replace Trap',
    tier: 'HEURISTIC',
    fire_count: 4,
    last_direction: -1,
    last_confidence: 0.47,
  },
];

export const MOCK_INTELLIGENCE_RAIL_STATE: IntelligenceRailState = {
  total_events: 35,
  active_detectors: MOCK_DETECTORS,
  score_summary: {
    mechanical_score: 0.74,
    heuristic_score: 0.47,
    overall_direction: 1,
  },
  updated_at: 1700000000000,
};

// ── Empty / quiet state for testing edge cases ───────────────────────────────

export const EMPTY_DOM_LADDER_STATE: DOMLadderState = {
  bids: [],
  asks: [],
  version: 0,
};

export const EMPTY_INTELLIGENCE_RAIL_STATE: IntelligenceRailState = {
  total_events: 0,
  active_detectors: [],
  score_summary: {
    mechanical_score: 0,
    heuristic_score: 0,
    overall_direction: 0,
  },
  updated_at: 0,
};
