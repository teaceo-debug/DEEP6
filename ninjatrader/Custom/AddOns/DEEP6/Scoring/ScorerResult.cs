// ScorerResult: output POCO from ConfluenceScorer.Score() for one bar.
//
// Python reference: deep6/scoring/scorer.py ScorerResult dataclass
// Port: Phase 18-01 — field-for-field match to Python ScorerResult.
//
// Mutable by design (Phase 17 convention) — in-process only, no cross-boundary serialization.

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring
{
    /// <summary>
    /// Output of the two-layer confluence scorer for one bar.
    /// Mirrors Python deep6/scoring/scorer.py ScorerResult dataclass.
    /// </summary>
    public sealed class ScorerResult
    {
        /// <summary>Final fused score, range 0..100. After all multipliers, bonuses, and VPIN.</summary>
        public double TotalScore;

        /// <summary>Tier classification: DISQUALIFIED..TYPE_A.</summary>
        public SignalTier Tier;

        /// <summary>Dominant direction: +1 bull, -1 bear, 0 neutral.</summary>
        public int Direction;

        /// <summary>Engine agreement ratio 0..1 — fraction of signal votes on dominant side.</summary>
        public double EngineAgreement;

        /// <summary>Number of distinct signal categories agreeing on dominant direction.</summary>
        public int CategoryCount;

        /// <summary>Confluence multiplier applied: 1.0 (< 5 cats) or 1.25 (>= 5 cats).</summary>
        public double ConfluenceMult;

        /// <summary>Zone bonus added: 0, 4, 6, or 8 points based on zone score and proximity.</summary>
        public double ZoneBonus;

        /// <summary>
        /// Entry price for this signal. Derived from dominant ABS/EXH signal's Price field (nonzero).
        /// Falls back to barClose if no ABS/EXH signal has a nonzero Price.
        /// </summary>
        public double EntryPrice;

        /// <summary>
        /// Human-readable tier label matching Python ScorerResult.label format.
        /// TypeA: "TYPE A — TRIPLE CONFLUENCE LONG (N categories, score S)"
        /// TypeB: "TYPE B — DOUBLE CONFLUENCE LONG (N categories, score S)"
        /// TypeC: "TYPE C — SIGNAL (N categories, score S)"
        /// QUIET: dominant signal detail or "QUIET" if no signals.
        /// </summary>
        public string Narrative;

        /// <summary>
        /// Sorted list of signal category names contributing to dominant direction.
        /// One of: "absorption", "exhaustion", "trapped", "imbalance", "delta", "volume_profile", "auction", "poc".
        /// </summary>
        public string[] CategoriesFiring;
    }
}
