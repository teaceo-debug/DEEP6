import { describe, it, expect } from 'vitest';
import {
  MOCK_DOM_LADDER_STATE,
  MOCK_INTELLIGENCE_RAIL_STATE,
  EMPTY_DOM_LADDER_STATE,
  EMPTY_INTELLIGENCE_RAIL_STATE,
} from './dom-mock-state';

describe('dom-mock-state', () => {
  describe('MOCK_DOM_LADDER_STATE', () => {
    it('has bids and asks arrays', () => {
      expect(Array.isArray(MOCK_DOM_LADDER_STATE.bids)).toBe(true);
      expect(Array.isArray(MOCK_DOM_LADDER_STATE.asks)).toBe(true);
    });

    it('has non-empty bids and asks', () => {
      expect(MOCK_DOM_LADDER_STATE.bids.length).toBeGreaterThan(0);
      expect(MOCK_DOM_LADDER_STATE.asks.length).toBeGreaterThan(0);
    });

    it('uses NQ price range (around 20000)', () => {
      for (const bid of MOCK_DOM_LADDER_STATE.bids) {
        expect(bid.price).toBeGreaterThan(19000);
        expect(bid.price).toBeLessThan(21000);
      }
      for (const ask of MOCK_DOM_LADDER_STATE.asks) {
        expect(ask.price).toBeGreaterThan(19000);
        expect(ask.price).toBeLessThan(21000);
      }
    });

    it('has NQ tick increments (0.25)', () => {
      for (const bid of MOCK_DOM_LADDER_STATE.bids) {
        expect((bid.price * 4) % 1).toBeCloseTo(0, 5);
      }
    });

    it('has version number', () => {
      expect(MOCK_DOM_LADDER_STATE.version).toBeGreaterThanOrEqual(0);
    });
  });

  describe('MOCK_INTELLIGENCE_RAIL_STATE', () => {
    it('has active detectors array', () => {
      expect(Array.isArray(MOCK_INTELLIGENCE_RAIL_STATE.active_detectors)).toBe(true);
      expect(MOCK_INTELLIGENCE_RAIL_STATE.active_detectors.length).toBeGreaterThan(0);
    });

    it('has total_events count', () => {
      expect(MOCK_INTELLIGENCE_RAIL_STATE.total_events).toBeGreaterThan(0);
    });

    it('has score_summary with valid direction', () => {
      expect([-1, 0, 1]).toContain(MOCK_INTELLIGENCE_RAIL_STATE.score_summary.overall_direction);
    });

    it('includes both MECHANICAL and HEURISTIC tiers', () => {
      const tiers = new Set(MOCK_INTELLIGENCE_RAIL_STATE.active_detectors.map(d => d.tier));
      expect(tiers.has('MECHANICAL')).toBe(true);
      expect(tiers.has('HEURISTIC')).toBe(true);
    });

    it('does not include DISCRETIONARY_OVERLAY tier (Phase 4 scope)', () => {
      const tiers = new Set(MOCK_INTELLIGENCE_RAIL_STATE.active_detectors.map(d => d.tier));
      expect(tiers.has('DISCRETIONARY_OVERLAY')).toBe(false);
    });

    it('all confidences are between 0 and 1', () => {
      for (const det of MOCK_INTELLIGENCE_RAIL_STATE.active_detectors) {
        expect(det.last_confidence).toBeGreaterThanOrEqual(0);
        expect(det.last_confidence).toBeLessThanOrEqual(1);
      }
    });
  });

  describe('empty states', () => {
    it('EMPTY_DOM_LADDER_STATE has empty arrays', () => {
      expect(EMPTY_DOM_LADDER_STATE.bids).toHaveLength(0);
      expect(EMPTY_DOM_LADDER_STATE.asks).toHaveLength(0);
      expect(EMPTY_DOM_LADDER_STATE.version).toBe(0);
    });

    it('EMPTY_INTELLIGENCE_RAIL_STATE has zero events', () => {
      expect(EMPTY_INTELLIGENCE_RAIL_STATE.total_events).toBe(0);
      expect(EMPTY_INTELLIGENCE_RAIL_STATE.active_detectors).toHaveLength(0);
      expect(EMPTY_INTELLIGENCE_RAIL_STATE.score_summary.overall_direction).toBe(0);
    });
  });
});
