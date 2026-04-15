// TrespassDetector: ENG-02 multi-level weighted DOM queue imbalance + logistic approximation.
//
// Python reference: deep6/engines/trespass.py TrespassEngine
//
// Algorithm (trespass.py lines 100-134):
//   1. Compute weighted_bid = sum(BidDomLevels[i] * w[i] for i in 0..depth-1)
//      Compute weighted_ask = sum(AskDomLevels[i] * w[i] for i in 0..depth-1)
//      where w[i] = 1/(i+1) (closer-to-best-bid levels weighted higher)
//   2. imbalance_ratio = weighted_bid / weighted_ask (guard ask=0)
//   3. probability = clamp((ratio - 1.0) * 0.5 + 0.5, 0, 1)   — logistic approximation
//   4. Fire ENG-02 when probability > threshold (bull) or < 1-threshold (bear)
//
// Implements IDepthConsumingDetector so OnDepth updates BidDomLevels/AskDomLevels
// in-place (allocation-free hot path).
//
// Writes LastTrespassProbability + LastTrespassDirection to SessionContext after OnBar
// so MicroProbDetector (ENG-05) can consume them.
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).

using System;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines
{
    /// <summary>
    /// Configuration for TrespassDetector.
    /// Python reference: deep6/engines/signal_config.py TrespassConfig
    /// </summary>
    public sealed class TrespassConfig
    {
        /// <summary>Number of top-of-book levels to include in weighted sum. Python: trespass_depth=10</summary>
        public int TrespassDepth = 10;

        /// <summary>Probability threshold for bullish signal: probability > threshold. Python: bull_ratio_threshold implies ~0.65</summary>
        public double BullThreshold = 0.65;

        /// <summary>Probability threshold for bearish signal: probability < 1-threshold. Python: bear_ratio_threshold implies ~0.35</summary>
        public double BearThreshold = 0.35;
    }

    /// <summary>
    /// ENG-02 Trespass: multi-level weighted DOM queue imbalance detector.
    ///
    /// Implements IDepthConsumingDetector — receives real-time OnDepth() updates from
    /// DetectorRegistry.DispatchDepth(). Reads BidDomLevels/AskDomLevels from SessionContext
    /// (updated in-place by DispatchDepth and OnDepth).
    ///
    /// Python reference: deep6/engines/trespass.py TrespassEngine
    /// </summary>
    public sealed class TrespassDetector : IDepthConsumingDetector
    {
        private readonly TrespassConfig _cfg;

        // Pre-computed weight array: w[i] = 1/(i+1) — avoids allocation on hot path.
        // Python: self._weights = [1.0 / (i + 1) for i in range(LEVELS)]
        private readonly double[] _weights;

        public TrespassDetector() : this(new TrespassConfig()) { }

        public TrespassDetector(TrespassConfig cfg)
        {
            _cfg = cfg ?? new TrespassConfig();
            // Pre-compute weights once at construction — never reallocated.
            _weights = new double[40];
            for (int i = 0; i < 40; i++) _weights[i] = 1.0 / (i + 1);
        }

        /// <inheritdoc/>
        public string Name => "Trespass";

        /// <inheritdoc/>
        public void Reset() { /* DOM state lives in SessionContext arrays — reset handled by SessionContext.ResetSession() */ }

        /// <inheritdoc/>
        /// <summary>
        /// Receive a DOM depth update. Updates session.BidDomLevels / AskDomLevels in-place.
        /// Called up to 1000/sec from indicator OnMarketDepth — must be allocation-free.
        /// </summary>
        public void OnDepth(SessionContext session, int side, int levelIdx, double price, long size, long? priorSize)
        {
            if (session == null || levelIdx < 0 || levelIdx >= 40) return;
            // Arrays are also updated by DetectorRegistry.DispatchDepth, so this is redundant
            // but kept for correctness if OnDepth is ever called standalone.
            if (side == 0) session.BidDomLevels[levelIdx] = size;
            else           session.AskDomLevels[levelIdx] = size;
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || session == null) return Array.Empty<SignalResult>();

            int    depth = _cfg.TrespassDepth;
            double weightedBid = 0.0;
            double weightedAsk = 0.0;

            for (int i = 0; i < depth && i < 40; i++)
            {
                double w = _weights[i];
                weightedBid += session.BidDomLevels[i] * w;
                weightedAsk += session.AskDomLevels[i] * w;
            }

            // Guard: all-zero DOM (not yet populated) → neutral
            if (weightedBid == 0.0 && weightedAsk == 0.0)
            {
                session.LastTrespassProbability = 0.5;
                session.LastTrespassDirection   = 0;
                return Array.Empty<SignalResult>();
            }

            // Guard: ask side empty → extreme bid pressure (logistic → 1.0)
            double probability;
            double imbalanceRatio;
            if (weightedAsk == 0.0)
            {
                imbalanceRatio = 0.0;
                probability    = 0.0;
            }
            else
            {
                imbalanceRatio = weightedBid / weightedAsk;
                // Logistic approximation matching trespass.py line 130:
                //   probability = min(max((ratio - 1.0) * 0.5 + 0.5, 0), 1)
                probability = System.Math.Max(0.0, System.Math.Min(1.0, (imbalanceRatio - 1.0) * 0.5 + 0.5));
            }

            // Write to SessionContext for MicroProbDetector (ENG-05) cross-read.
            int direction = 0;
            if      (probability > _cfg.BullThreshold) direction = +1;
            else if (probability < _cfg.BearThreshold) direction = -1;

            session.LastTrespassProbability = probability;
            session.LastTrespassDirection   = direction;

            if (direction == 0) return Array.Empty<SignalResult>();

            string label = direction > 0
                ? string.Format("TRESPASS BULL: weighted bid={0:F1} > ask={1:F1}, ratio={2:F3}, prob={3:F3}",
                    weightedBid, weightedAsk, imbalanceRatio, probability)
                : string.Format("TRESPASS BEAR: weighted ask={0:F1} > bid={1:F1}, ratio={2:F3}, prob={3:F3}",
                    weightedAsk, weightedBid, imbalanceRatio, probability);

            return new[]
            {
                new SignalResult("ENG-02", direction,
                    System.Math.Abs(probability - 0.5) * 2.0,   // strength = distance from neutral
                    SignalFlagBits.Mask(SignalFlagBits.ENG_02),
                    label,
                    bar.Close)
            };
        }
    }
}
