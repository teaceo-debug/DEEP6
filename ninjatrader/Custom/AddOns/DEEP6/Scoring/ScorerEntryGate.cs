// ScorerEntryGate: NT8-API-free entry gate helper for scorer-driven DEEP6Strategy.
//
// Extracted from DEEP6Strategy.EvaluateEntry to enable unit testing without
// an NT8 runtime host. Strategy consumes GateOutcome.Passed before delegating
// to RiskGatesPass + EnterWithAtm.
//
// Phase 18-03

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring
{
    /// <summary>
    /// Static entry gate helper — evaluates a <see cref="ScorerResult"/> against
    /// score threshold and minimum tier.  NT8-API-free so it can be unit-tested.
    /// </summary>
    public static class ScorerEntryGate
    {
        /// <summary>Gate outcome — ordered from most-rejected to passing.</summary>
        public enum GateOutcome
        {
            /// <summary>ScorerResult is null (indicator not loaded or no bars yet).</summary>
            NoScore,

            /// <summary>Direction is 0 — ambiguous signal, no entry.</summary>
            NoDirection,

            /// <summary>TotalScore is below the configured threshold.</summary>
            BelowScore,

            /// <summary>Tier is below the configured minimum tier.</summary>
            BelowTier,

            /// <summary>All gates passed — caller may proceed to risk gates.</summary>
            Passed
        }

        /// <summary>
        /// Evaluate whether entry should be considered, given scorer output and thresholds.
        /// Does NOT touch NT8 APIs — safe to call from unit tests.
        /// </summary>
        /// <param name="scored">Latest scorer result from <see cref="ScorerSharedState.Latest"/>. Null → NoScore.</param>
        /// <param name="scoreThreshold">Minimum TotalScore required (e.g. 80.0 for TypeA default).</param>
        /// <param name="minTier">Minimum tier required (e.g. SignalTier.TYPE_A).</param>
        /// <returns>
        /// <see cref="GateOutcome.Passed"/> if all conditions are satisfied;
        /// otherwise the first failing gate outcome.
        /// </returns>
        public static GateOutcome Evaluate(ScorerResult scored, double scoreThreshold, SignalTier minTier)
        {
            if (scored == null)
                return GateOutcome.NoScore;
            if (scored.Direction == 0)
                return GateOutcome.NoDirection;
            if (scored.TotalScore < scoreThreshold)
                return GateOutcome.BelowScore;
            if ((int)scored.Tier < (int)minTier)
                return GateOutcome.BelowTier;
            return GateOutcome.Passed;
        }

        /// <summary>
        /// Build the SC5 per-bar log line for a scored bar.
        /// Returns empty string if <paramref name="scored"/> is null.
        ///
        /// Format: [DEEP6 Scorer] bar={barIdx} score={+0.00} tier={Tier} narrative={Narrative}
        /// </summary>
        /// <param name="barIdx">CurrentBar index at time of scoring.</param>
        /// <param name="scored">The scorer result to format.</param>
        public static string BuildLogLine(int barIdx, ScorerResult scored)
        {
            if (scored == null)
                return string.Empty;
            return string.Format(
                "[DEEP6 Scorer] bar={0} score={1:+0.00;-0.00;+0.00} tier={2} narrative={3}",
                barIdx,
                scored.TotalScore,
                scored.Tier,
                scored.Narrative ?? string.Empty);
        }
    }
}
