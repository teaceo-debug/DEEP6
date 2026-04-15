// MicroProbDetector: ENG-05 Naïve Bayes micro-probability aggregator.
//
// Python reference: deep6/engines/micro_prob.py MicroProbEngine
//
// Algorithm (micro_prob.py lines 40-90):
//   Reads cross-detector session fields written earlier in the same bar cycle:
//     - session.LastTrespassProbability  (ENG-02 logistic output)
//     - session.LastTrespassDirection    (+1/-1/0)
//     - session.LastIcebergSignals.Count (ENG-04 synthetic + native iceberg count)
//   Applies a simple Naïve Bayes likelihood ratio:
//     log_odds_bull = alpha * (trespass_prob - 0.5) + beta * iceberg_count_bull_bonus
//     p_bull = sigmoid(log_odds_bull)
//   Fires ENG-05 if p_bull > BullThreshold or p_bull < 1-BullThreshold.
//
// CRITICAL REGISTRATION ORDER:
//   MicroProbDetector MUST register AFTER TrespassDetector (ENG-02) and IcebergDetector (ENG-04)
//   so that session.LastTrespassProbability and session.LastIcebergSignals are populated
//   before OnBar() is called here.
//
//   DetectorRegistry.EvaluateBar() calls session.BeginBar() before all detectors run,
//   resetting those fields to neutral — correct, since we want the values from THIS bar.
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines
{
    /// <summary>
    /// Configuration for MicroProbDetector.
    /// Python reference: deep6/engines/signal_config.py MicroProbConfig
    /// </summary>
    public sealed class MicroProbConfig
    {
        /// <summary>Scaling factor applied to trespass probability deviation from 0.5. Python: alpha=2.0</summary>
        public double Alpha = 2.0;

        /// <summary>Bonus log-odds added per iceberg signal fired this bar. Python: beta=0.5</summary>
        public double Beta = 0.5;

        /// <summary>Sigmoid output threshold for bullish signal. Python: bull_threshold=0.70</summary>
        public double BullThreshold = 0.70;

        /// <summary>Minimum trespass probability deviation from 0.5 to count as a valid trespass input.</summary>
        public double TrespassMinDeviation = 0.05;
    }

    /// <summary>
    /// ENG-05 MicroProb: Naïve Bayes micro-probability aggregator.
    ///
    /// Reads cross-detector state written to SessionContext by ENG-02 (TrespassDetector)
    /// and ENG-04 (IcebergDetector) during the same bar cycle. Must register LAST among
    /// engine detectors so those fields are populated before OnBar() is called.
    ///
    /// Python reference: deep6/engines/micro_prob.py MicroProbEngine
    /// </summary>
    public sealed class MicroProbDetector : ISignalDetector
    {
        private readonly MicroProbConfig _cfg;

        public MicroProbDetector() : this(new MicroProbConfig()) { }

        public MicroProbDetector(MicroProbConfig cfg)
        {
            _cfg = cfg ?? new MicroProbConfig();
        }

        /// <inheritdoc/>
        public string Name => "MicroProb";

        /// <inheritdoc/>
        public void Reset() { /* stateless between session resets — session fields are cleared by SessionContext.ResetSession() */ }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || session == null) return Array.Empty<SignalResult>();

            double trespassProb = session.LastTrespassProbability;
            int    trespassDir  = session.LastTrespassDirection;
            int    icebergCount = session.LastIcebergSignals != null ? session.LastIcebergSignals.Count : 0;

            // Guard: if trespass detector did not fire (neutral direction, prob near 0.5),
            // and no iceberg signals, skip — not enough input signal.
            double trespassDeviation = System.Math.Abs(trespassProb - 0.5);
            if (trespassDir == 0 && trespassDeviation < _cfg.TrespassMinDeviation && icebergCount == 0)
                return Array.Empty<SignalResult>();

            // Naïve Bayes log-odds:
            //   log_odds = alpha * (trespass_prob - 0.5) + beta * iceberg_count
            // iceberg_count is always a bullish-agnostic magnitude; we apply it in the
            // direction of the trespass, or as a neutral boost if trespass is neutral.
            double trespassComponent = _cfg.Alpha * (trespassProb - 0.5);
            double icebergComponent  = _cfg.Beta * icebergCount;

            // If trespass fired bearish, the iceberg component reduces bearish log-odds
            // (icebergs = hidden buy orders = bullish context) — apply directionally.
            // Net: combine both components in their natural directions.
            double logOdds = trespassComponent + icebergComponent;

            // Sigmoid: p = 1 / (1 + exp(-logOdds))
            double pBull = 1.0 / (1.0 + System.Math.Exp(-logOdds));

            int direction = 0;
            if      (pBull > _cfg.BullThreshold)       direction = +1;
            else if (pBull < (1.0 - _cfg.BullThreshold)) direction = -1;

            if (direction == 0) return Array.Empty<SignalResult>();

            string label = string.Format(
                "MICRO-PROB {0}: p_bull={1:F3} logOdds={2:F3} trespass_prob={3:F3}({4:+0;-0}) iceberg_n={5}",
                direction > 0 ? "BULL" : "BEAR",
                pBull, logOdds, trespassProb, trespassDir, icebergCount);

            return new[]
            {
                new SignalResult("ENG-05", direction,
                    System.Math.Abs(pBull - 0.5) * 2.0,  // strength = distance from neutral
                    SignalFlagBits.Mask(SignalFlagBits.ENG_05),
                    label,
                    bar.Close)
            };
        }
    }
}
