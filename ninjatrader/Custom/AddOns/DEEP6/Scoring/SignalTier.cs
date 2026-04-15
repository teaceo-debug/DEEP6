// SignalTier: Tier classification enum for the two-layer confluence scorer.
//
// Python reference: deep6/scoring/scorer.py SignalTier (IntEnum)
// Port: Phase 18-01 — verbatim enum values matching Python IntEnum ordinals.
//
// DISQUALIFIED (-1) is intentionally the lowest — plan 15-03 / D-33.
// Vetoes (e.g. SPOOF_DETECTED from ConfluenceRules) force the result here
// regardless of raw score. Pre-existing code compares tiers as ordinals;
// DISQUALIFIED < QUIET ensures "tier >= QUIET" gates exclude it.

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring
{
    /// <summary>
    /// Signal tier classification output from ConfluenceScorer.Score().
    /// Ordinal values match Python SignalTier IntEnum (scorer.py) exactly.
    /// </summary>
    public enum SignalTier
    {
        /// <summary>Vetoed by ConfluenceRules (e.g. spoofing detected). Not tradeable.</summary>
        DISQUALIFIED = -1,

        /// <summary>No confluence or midday block active. No trade signal.</summary>
        QUIET = 0,

        /// <summary>3+ categories, score >= 50. Alert only — not auto-executed.</summary>
        TYPE_C = 1,

        /// <summary>4+ categories, score >= 72. Tradeable with confirmation.</summary>
        TYPE_B = 2,

        /// <summary>5+ categories, score >= 80, abs/exh + zone + delta agree. High conviction.</summary>
        TYPE_A = 3
    }
}
