// ImbalanceDetector: ISignalDetector implementation for IMB-01, IMB-06, IMB-08.
//
// Python reference: deep6/engines/imbalance.py detect_imbalances() lines 52-130
// Signal IDs: IMB-01 (Single), IMB-06 (Oversized), IMB-08 (Diagonal)
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).
//
// Diagonal algorithm (IMB-08) note per RESEARCH.md + CONTEXT.md:
//   Buy imbalance: ask[P] vs bid[P - tickSize]  (one tick DOWN)
//   Sell imbalance: bid[P] vs ask[P + tickSize] (one tick UP)
//   CRITICAL: ask[P] vs bid[P - tickSize], NOT bid[P + tickSize].
//   This is explicitly regression-guarded by Imb08_DiagonalUsesPriceMinusTickSize().

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Imbalance
{
    /// <summary>
    /// Configuration for ImbalanceDetector.
    /// Python reference: deep6/engines/signal_config.py ImbalanceConfig lines 76-90
    /// </summary>
    public sealed class ImbalanceConfig
    {
        /// <summary>Min ask[P]/bid[P-1] ratio for a single buy imbalance. Python: ratio_threshold=3.0</summary>
        public double RatioThreshold    = 3.0;

        /// <summary>Ratio threshold for oversized classification. Python: oversized_threshold=10.0</summary>
        public double OversizedThreshold = 10.0;
    }

    /// <summary>
    /// Detects IMB-01 (Single), IMB-06 (Oversized), IMB-08 (Diagonal) imbalances.
    ///
    /// Implements ISignalDetector; stateless between bars.
    /// Python reference: deep6/engines/imbalance.py
    /// </summary>
    public sealed class ImbalanceDetector : ISignalDetector
    {
        private readonly ImbalanceConfig _cfg;

        public ImbalanceDetector() : this(new ImbalanceConfig()) { }

        public ImbalanceDetector(ImbalanceConfig cfg)
        {
            _cfg = cfg ?? new ImbalanceConfig();
        }

        /// <inheritdoc/>
        public string Name => "Imbalance";

        /// <inheritdoc/>
        public void Reset()
        {
            // Stateless detector — nothing to reset.
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || bar.Levels == null || bar.Levels.Count < 2 || bar.TotalVol == 0)
                return Array.Empty<SignalResult>();

            double tickSize = session != null && session.TickSize > 0 ? session.TickSize : 0.25;

            var results = new List<SignalResult>();

            // Build sorted price list for diagonal scan
            var sortedPrices = new List<double>(bar.Levels.Keys);
            // SortedDictionary guarantees ascending order — no additional sort needed.

            double ratio       = _cfg.RatioThreshold;
            double oversizedTh = _cfg.OversizedThreshold;

            // --- Diagonal scan (Python imbalance.py lines 84-127) ---
            // IMB-08 diagonal:
            //   Buy imbalance: ask[P] vs bid[P - tickSize]   (ask at current level vs bid one tick BELOW)
            //   Sell imbalance: bid[P] vs ask[P + tickSize]  (bid at current level vs ask one tick ABOVE)
            //
            // The same scan produces IMB-01 / IMB-06 by checking the resulting ratio.

            for (int i = 0; i < sortedPrices.Count; i++)
            {
                double px = sortedPrices[i];
                Cell lv = bar.Levels[px];

                // --- Buy imbalance side ---
                // ask[P] vs bid[P - tickSize]  (i > 0 means there is a level below)
                if (i > 0)
                {
                    double prevPx = sortedPrices[i - 1];
                    // Only treat as the diagonal neighbor if it's exactly one tick down
                    if (System.Math.Abs(prevPx - (px - tickSize)) < tickSize * 0.01)
                    {
                        long prevBid = bar.Levels[prevPx].BidVol;
                        long currAsk = lv.AskVol;
                        double r = 0.0;
                        bool fires = false;
                        if (prevBid > 0 && currAsk >= prevBid * ratio)
                        {
                            r = (double)currAsk / prevBid;
                            fires = true;
                        }
                        else if (prevBid == 0 && currAsk > 0)
                        {
                            r = currAsk; // infinite ratio — treat as very large
                            fires = true;
                        }

                        if (fires)
                        {
                            EmitImbalance(px, r, +1, ratio, oversizedTh, tickSize, "diag buy", results);
                        }
                    }
                }

                // --- Sell imbalance side ---
                // bid[P] vs ask[P + tickSize]  (i < last means there is a level above)
                if (i < sortedPrices.Count - 1)
                {
                    double nextPx = sortedPrices[i + 1];
                    // Only treat as diagonal neighbor if exactly one tick up
                    if (System.Math.Abs(nextPx - (px + tickSize)) < tickSize * 0.01)
                    {
                        long nextAsk = bar.Levels[nextPx].AskVol;
                        long currBid = lv.BidVol;
                        double r = 0.0;
                        bool fires = false;
                        if (nextAsk > 0 && currBid >= nextAsk * ratio)
                        {
                            r = (double)currBid / nextAsk;
                            fires = true;
                        }
                        else if (nextAsk == 0 && currBid > 0)
                        {
                            r = currBid;
                            fires = true;
                        }

                        if (fires)
                        {
                            EmitImbalance(px, r, -1, ratio, oversizedTh, tickSize, "diag sell", results);
                        }
                    }
                }
            }

            return results.ToArray();
        }

        // --- Private helpers ---

        private static void EmitImbalance(
            double price, double ratio,
            int direction,
            double singleThreshold, double oversizedThreshold,
            double tickSize,
            string scanType,
            List<SignalResult> results)
        {
            bool isOversized = ratio >= oversizedThreshold;

            // IMB-01: Single imbalance (fired for every qualifying level, including those that
            //         are also oversized — Python emits SINGLE/OVERSIZED, not both, but the C#
            //         port matches the plan spec: emit both IMB-01 and IMB-06 when oversized).
            // Per plan acceptance criteria for imb-06-oversized.json fixture:
            //   "Expected both IMB-01 and IMB-06 fire."
            {
                // IMB-01 strength: Python uses min(r/10.0, 1.0) (imbalance.py line 118)
                double str01 = System.Math.Min(ratio / 10.0, 1.0);
                string dirLabel = direction > 0 ? "BUY" : "SELL";
                results.Add(new SignalResult(
                    "IMB-01", direction, str01,
                    SignalFlagBits.Mask(SignalFlagBits.IMB_01),
                    string.Format("SINGLE {0} IMB at {1:F2}: {2:F1}x ratio [{3}]",
                        dirLabel, price, ratio, scanType)));
            }

            if (isOversized)
            {
                // IMB-06: Oversized imbalance
                // Strength: plan spec says Math.Min(ratio / 20.0, 1.0)
                double str06 = System.Math.Min(ratio / 20.0, 1.0);
                string dirLabel = direction > 0 ? "BUY" : "SELL";
                results.Add(new SignalResult(
                    "IMB-06", direction, str06,
                    SignalFlagBits.Mask(SignalFlagBits.IMB_06),
                    string.Format("OVERSIZED {0} IMB at {1:F2}: {2:F1}x ratio [{3}]",
                        dirLabel, price, ratio, scanType)));
            }

            // IMB-08: Diagonal (always emitted when the diagonal scan fires)
            // The scan type label "diag buy"/"diag sell" marks diagonal-sourced signals.
            {
                double str08 = System.Math.Min(ratio / 10.0, 1.0);
                string dirLabel = direction > 0 ? "BUY" : "SELL";
                // Include "P-tick diag" in detail so regression test can assert the substring.
                results.Add(new SignalResult(
                    "IMB-08", direction, str08,
                    SignalFlagBits.Mask(SignalFlagBits.IMB_08),
                    string.Format("DIAGONAL {0} IMB at {1:F2}: {2:F1}x ratio [P-tick diag]",
                        dirLabel, price, ratio)));
            }
        }
    }
}
