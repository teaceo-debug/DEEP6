// ScorerEntryGate: NT8-API-free entry gate helper for scorer-driven DEEP6Strategy.
//
// Extracted from DEEP6Strategy.EvaluateEntry to enable unit testing without
// an NT8 runtime host. Strategy consumes GateOutcome.Passed before delegating
// to RiskGatesPass + EnterWithAtm.
//
// Phase 18-03
//
// P0-3: VOLP-03 volume-surge regime veto.
//   Session-level flag (_volSurgeFiredThisSession) set when any signal with
//   SignalId starting "VOLP-03" appears in a bar's result set.
//   When VolSurgeVetoEnabled=true and flag is set, Evaluate() returns VolSurgeVeto.
//   Flag reset via ResetSession().
//
// P0-5: Slow-grind ATR veto.
//   If sessionContext.Atr20 < SlowGrindAtrRatio × sessionContext.SessionAvgAtr, veto.
//   Requires SessionContext with Atr20 and SessionAvgAtr populated.
//   Checked via EvaluateWithContext() overload.

using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring
{
    /// <summary>
    /// Static-stateful entry gate helper — evaluates a <see cref="ScorerResult"/> against
    /// score threshold, minimum tier, and regime vetos.  NT8-API-free so it can be unit-tested.
    ///
    /// Session state (P0-3/P0-5) is held in a per-call <see cref="SessionGateState"/> object
    /// passed by the caller, keeping this class thread-safe and testable.
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

            /// <summary>P0-3: VOLP-03 volume-surge fired this session — regime is volatile, block entry.</summary>
            VolSurgeVeto,

            /// <summary>P0-5: Current ATR is below SlowGrindAtrRatio × session average ATR — slow-grind regime, block entry.</summary>
            SlowGrindVeto,

            /// <summary>R1: At least one signal opposes the dominant direction — strict directional agreement failed.</summary>
            DirectionalDisagreementVeto,

            /// <summary>R1: Bar timestamp falls within the time-of-day blackout window (e.g. 1530–1600 ET).</summary>
            BlackoutVeto,

            /// <summary>All gates passed — caller may proceed to risk gates.</summary>
            Passed
        }

        /// <summary>
        /// Per-session mutable state for the entry gate.
        /// Caller owns this object and resets it at each session boundary.
        /// </summary>
        public sealed class SessionGateState
        {
            /// <summary>P0-3: True once VOLP-03 has fired on any bar this session.</summary>
            public bool VolSurgeFiredThisSession;

            /// <summary>Reset all session-scoped flags. Call at RTH session open.</summary>
            public void ResetSession()
            {
                VolSurgeFiredThisSession = false;
            }

            /// <summary>
            /// P0-3: Inspect a bar's signal array; set VolSurgeFiredThisSession if VOLP-03 is present.
            /// Call once per bar close, before Evaluate().
            /// </summary>
            public void ObserveSignals(SignalResult[] signals)
            {
                if (signals == null) return;
                foreach (var sig in signals)
                {
                    if (sig != null && sig.SignalId != null &&
                        sig.SignalId.StartsWith("VOLP-03", System.StringComparison.Ordinal))
                    {
                        VolSurgeFiredThisSession = true;
                        return;
                    }
                }
            }
        }

        /// <summary>
        /// Evaluate whether entry should be considered, given scorer output and thresholds.
        /// Does NOT touch NT8 APIs — safe to call from unit tests.
        /// Legacy overload: no regime vetos (backwards-compatible).
        /// </summary>
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
        /// Full evaluate with regime vetos (P0-3 VOLP-03, P0-5 slow-grind) and R1 directional filter.
        /// </summary>
        /// <param name="scored">Latest scorer result. Null → NoScore.</param>
        /// <param name="scoreThreshold">Minimum TotalScore required.</param>
        /// <param name="minTier">Minimum tier required.</param>
        /// <param name="gateState">Session-level gate state (owns VolSurgeFiredThisSession).</param>
        /// <param name="volSurgeVetoEnabled">P0-3 toggle.</param>
        /// <param name="slowGrindVetoEnabled">P0-5 toggle.</param>
        /// <param name="slowGrindAtrRatio">P0-5 ratio threshold (default 0.5).</param>
        /// <param name="currentAtr">Current bar ATR (0 = not available → veto skipped).</param>
        /// <param name="sessionAvgAtr">Session rolling average ATR (0 = not available → veto skipped).</param>
        /// <param name="strictDirectionEnabled">R1: when true, any signal opposing the dominant direction vetoes entry.</param>
        /// <param name="signals">Signal array for the bar — required when strictDirectionEnabled=true.</param>
        /// <param name="blackoutWindowStart">R1: start of time-of-day blackout as HHMM int (e.g. 1530). 0 = disabled.</param>
        /// <param name="blackoutWindowEnd">R1: end of time-of-day blackout as HHMM int (e.g. 1600). Inclusive.</param>
        /// <param name="barTimeHHMM">R1: current bar time as HHMM int derived from session open + barsSinceOpen. 0 = skip check.</param>
        public static GateOutcome EvaluateWithContext(
            ScorerResult     scored,
            double           scoreThreshold,
            SignalTier       minTier,
            SessionGateState gateState,
            bool             volSurgeVetoEnabled     = true,
            bool             slowGrindVetoEnabled    = true,
            double           slowGrindAtrRatio       = 0.5,
            double           currentAtr              = 0.0,
            double           sessionAvgAtr           = 0.0,
            bool             strictDirectionEnabled  = true,
            SignalResult[]   signals                 = null,
            int              blackoutWindowStart     = 0,
            int              blackoutWindowEnd       = 0,
            int              barTimeHHMM             = 0)
        {
            if (scored == null)
                return GateOutcome.NoScore;
            if (scored.Direction == 0)
                return GateOutcome.NoDirection;
            if (scored.TotalScore < scoreThreshold)
                return GateOutcome.BelowScore;
            if ((int)scored.Tier < (int)minTier)
                return GateOutcome.BelowTier;

            // P0-3: VOLP-03 volume-surge regime veto
            if (volSurgeVetoEnabled && gateState != null && gateState.VolSurgeFiredThisSession)
                return GateOutcome.VolSurgeVeto;

            // P0-5: Slow-grind ATR veto
            if (slowGrindVetoEnabled
                && currentAtr > 0.0
                && sessionAvgAtr > 0.0
                && currentAtr < slowGrindAtrRatio * sessionAvgAtr)
                return GateOutcome.SlowGrindVeto;

            // R1: Strict directional agreement — any signal opposing dominant direction vetoes entry.
            // Source: SIGNAL-FILTER.md section 5 — delta Sharpe +19.601 for strict mode.
            if (strictDirectionEnabled && signals != null && scored.Direction != 0)
            {
                int dominant = scored.Direction;
                foreach (var sig in signals)
                {
                    if (sig == null) continue;
                    int sigDir = sig.Direction;
                    // Only veto if signal has an explicit opposing direction (not neutral/0)
                    if (sigDir != 0 && sigDir != dominant)
                        return GateOutcome.DirectionalDisagreementVeto;
                }
            }

            // R1: Time-of-day blackout window — block entries during low-quality time bands.
            // Source: ENTRY-TIMING.md — 1530-1600 is worst window (25.31t avg, delta -13.9t vs peak).
            if (blackoutWindowStart > 0 && blackoutWindowEnd >= blackoutWindowStart && barTimeHHMM > 0)
            {
                if (barTimeHHMM >= blackoutWindowStart && barTimeHHMM <= blackoutWindowEnd)
                    return GateOutcome.BlackoutVeto;
            }

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
