// ImbalanceDetector: ISignalDetector implementation for IMB-01..09.
//
// Wave 3 (TRIVIAL): IMB-01 Single, IMB-06 Oversized, IMB-08 Diagonal
// Wave 4 (MODERATE): IMB-02 Multiple, IMB-03 Stacked T1/T2/T3, IMB-04 Reverse,
//                    IMB-05 Inverse (trapped), IMB-07 Consecutive, IMB-09 Reversal
//
// Python reference: deep6/engines/imbalance.py detect_imbalances()
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).
//
// Diagonal algorithm (IMB-08) note per RESEARCH.md + CONTEXT.md:
//   Buy imbalance: ask[P] vs bid[P - tickSize]  (one tick DOWN)
//   Sell imbalance: bid[P] vs ask[P + tickSize] (one tick UP)
//   CRITICAL: ask[P] vs bid[P - tickSize], NOT bid[P + tickSize].

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Imbalance
{
    /// <summary>
    /// Configuration for ImbalanceDetector.
    /// Python reference: deep6/engines/signal_config.py ImbalanceConfig
    /// </summary>
    public sealed class ImbalanceConfig
    {
        /// <summary>Min ask[P]/bid[P-1] ratio for a single buy imbalance. Python: ratio_threshold=3.0</summary>
        public double RatioThreshold    = 3.0;

        /// <summary>Ratio threshold for oversized classification. Python: oversized_threshold=10.0</summary>
        public double OversizedThreshold = 10.0;

        /// <summary>Min count of imbalances in same direction for MULTIPLE signal. Python: multiple_min_count=3</summary>
        public int MultipleMinCount = 3;

        /// <summary>Stacked T1 consecutive level threshold. Python: stacked_t1=3</summary>
        public int StackedT1 = 3;

        /// <summary>Stacked T2 consecutive level threshold. Python: stacked_t2=5</summary>
        public int StackedT2 = 5;

        /// <summary>Stacked T3 consecutive level threshold. Python: stacked_t3=7</summary>
        public int StackedT3 = 7;

        /// <summary>Gap tolerance for stacked run detection (in ticks). Python: stacked_gap_tolerance=2</summary>
        public int StackedGapTolerance = 2;

        /// <summary>Min imbalances for inverse trap to fire. Python: inverse_min_imbalances=2</summary>
        public int InverseMinImbalances = 2;
    }

    /// <summary>
    /// Detects IMB-01..09 imbalance signals.
    ///
    /// Implements ISignalDetector; stateless for single-bar signals.
    /// IMB-07 (consecutive) and IMB-09 (reversal) use SessionContext.ImbalanceHistory.
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
            // Cross-bar state (ImbalanceHistory) lives in SessionContext — Reset() is a no-op.
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || bar.Levels == null || bar.Levels.Count < 2 || bar.TotalVol == 0)
                return Array.Empty<SignalResult>();

            double tickSize = session != null && session.TickSize > 0 ? session.TickSize : 0.25;

            var results = new List<SignalResult>();

            // Build sorted price list for diagonal scan.
            // SortedDictionary guarantees ascending order.
            var sortedPrices = new List<double>(bar.Levels.Keys);

            double ratio       = _cfg.RatioThreshold;
            double oversizedTh = _cfg.OversizedThreshold;

            // ---------------------------------------------------------------
            // DIAGONAL SCAN (IMB-08 / IMB-01 / IMB-06)
            // Python imbalance.py lines 84-127: diagonal comparison across adjacent ticks.
            //   Buy imbalance: ask[P] vs bid[P - tickSize]
            //   Sell imbalance: bid[P] vs ask[P + tickSize]
            // ---------------------------------------------------------------
            var buyImbPrices  = new List<double>();  // prices that fired buy imbalance
            var sellImbPrices = new List<double>();  // prices that fired sell imbalance
            var buyRatios     = new Dictionary<double, double>();
            var sellRatios    = new Dictionary<double, double>();

            for (int i = 0; i < sortedPrices.Count; i++)
            {
                double px = sortedPrices[i];
                Cell lv = bar.Levels[px];

                // --- Buy imbalance: ask[P] vs bid[P - tickSize] ---
                if (i > 0)
                {
                    double prevPx = sortedPrices[i - 1];
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
                            r = currAsk;
                            fires = true;
                        }

                        if (fires)
                        {
                            buyImbPrices.Add(px);
                            buyRatios[px] = r;
                            EmitSingleOversizedDiag(px, r, +1, ratio, oversizedTh, results);
                        }
                    }
                }

                // --- Sell imbalance: bid[P] vs ask[P + tickSize] ---
                if (i < sortedPrices.Count - 1)
                {
                    double nextPx = sortedPrices[i + 1];
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
                            sellImbPrices.Add(px);
                            sellRatios[px] = r;
                            EmitSingleOversizedDiag(px, r, -1, ratio, oversizedTh, results);
                        }
                    }
                }
            }

            // ---------------------------------------------------------------
            // IMB-02 MULTIPLE
            // Python: fire when >= multiple_min_count imbalances in same direction.
            // Strength = min(count / (multiple_min * 2), 1.0)
            // ---------------------------------------------------------------
            int multipleMin = _cfg.MultipleMinCount;
            if (buyImbPrices.Count >= multipleMin)
            {
                double midPx = buyImbPrices[buyImbPrices.Count / 2];
                double str   = System.Math.Min((double)buyImbPrices.Count / (multipleMin * 2.0), 1.0);
                results.Add(new SignalResult(
                    "IMB-02", +1, str,
                    SignalFlagBits.Mask(SignalFlagBits.IMB_02),
                    string.Format("BUY MULTIPLE: {0} buy imbalances in bar (>= {1} threshold)",
                        buyImbPrices.Count, multipleMin)));
            }
            if (sellImbPrices.Count >= multipleMin)
            {
                double midPx = sellImbPrices[sellImbPrices.Count / 2];
                double str   = System.Math.Min((double)sellImbPrices.Count / (multipleMin * 2.0), 1.0);
                results.Add(new SignalResult(
                    "IMB-02", -1, str,
                    SignalFlagBits.Mask(SignalFlagBits.IMB_02),
                    string.Format("SELL MULTIPLE: {0} sell imbalances in bar (>= {1} threshold)",
                        sellImbPrices.Count, multipleMin)));
            }

            // ---------------------------------------------------------------
            // IMB-03 STACKED T1/T2/T3
            // Python: find consecutive-level runs; classify by count: T1>=3, T2>=5, T3>=7
            // Gap tolerance = stacked_gap_tolerance ticks between consecutive imbalance levels.
            // Emit ONLY the highest tier detected for each run.
            // ---------------------------------------------------------------
            EmitStackedRuns(buyImbPrices,  +1, tickSize, results, _cfg);
            EmitStackedRuns(sellImbPrices, -1, tickSize, results, _cfg);

            // ---------------------------------------------------------------
            // IMB-04 REVERSE
            // Python: fire when bar contains BOTH buy and sell imbalances.
            // Direction = sign of net count (buy_count - sell_count).
            // ---------------------------------------------------------------
            if (buyImbPrices.Count > 0 && sellImbPrices.Count > 0)
            {
                int netSign = System.Math.Sign(buyImbPrices.Count - sellImbPrices.Count);
                results.Add(new SignalResult(
                    "IMB-04", netSign, 0.5,
                    SignalFlagBits.Mask(SignalFlagBits.IMB_04),
                    string.Format("REVERSE: {0} buy + {1} sell imbalances in same bar",
                        buyImbPrices.Count, sellImbPrices.Count)));
            }

            // ---------------------------------------------------------------
            // IMB-05 INVERSE TRAP
            // Python: buy imbalances in RED bar = trapped longs (direction=-1)
            //         sell imbalances in GREEN bar = trapped shorts (direction=+1)
            // ---------------------------------------------------------------
            int invMin = _cfg.InverseMinImbalances;
            bool barBearish = bar.Close < bar.Open;
            bool barBullish = bar.Close > bar.Open;
            if (barBearish && buyImbPrices.Count >= invMin)
            {
                double str = System.Math.Min((double)buyImbPrices.Count / 7.0, 1.0);
                results.Add(new SignalResult(
                    "IMB-05", -1, str,
                    SignalFlagBits.Mask(SignalFlagBits.IMB_05),
                    string.Format("INVERSE TRAP: {0} BUY imbalances in RED bar — longs trapped (80-85% win rate)",
                        buyImbPrices.Count)));
            }
            if (barBullish && sellImbPrices.Count >= invMin)
            {
                double str = System.Math.Min((double)sellImbPrices.Count / 7.0, 1.0);
                results.Add(new SignalResult(
                    "IMB-05", +1, str,
                    SignalFlagBits.Mask(SignalFlagBits.IMB_05),
                    string.Format("INVERSE TRAP: {0} SELL imbalances in GREEN bar — shorts trapped",
                        sellImbPrices.Count)));
            }

            // ---------------------------------------------------------------
            // IMB-07 CONSECUTIVE
            // Python: same imbalance at same price level across consecutive bars.
            // Use session.ImbalanceHistory to find levels imbalanced in prior bar too.
            // ---------------------------------------------------------------
            if (session != null && session.ImbalanceHistory != null && session.ImbalanceHistory.Count > 0)
            {
                // Get prior bar's imbalance map (most recent entry = prior bar)
                var priorMap = GetLastHistoryEntry(session.ImbalanceHistory);
                if (priorMap != null)
                {
                    // Buy consecutive: price in both current buy scan and prior bar buy scan
                    foreach (double px in buyImbPrices)
                    {
                        if (priorMap.ContainsKey(px))
                        {
                            double r = buyRatios.ContainsKey(px) ? buyRatios[px] : 0.0;
                            results.Add(new SignalResult(
                                "IMB-07", +1, 0.75,
                                SignalFlagBits.Mask(SignalFlagBits.IMB_07),
                                string.Format("CONSECUTIVE BUY IMB at {0:F2}: persistent across 2 bars", px)));
                        }
                    }
                    // Sell consecutive
                    foreach (double px in sellImbPrices)
                    {
                        // For sell, we store with negative ratio sign in history; use negative key convention
                        double negPx = -px;
                        if (priorMap.ContainsKey(negPx))
                        {
                            results.Add(new SignalResult(
                                "IMB-07", -1, 0.75,
                                SignalFlagBits.Mask(SignalFlagBits.IMB_07),
                                string.Format("CONSECUTIVE SELL IMB at {0:F2}: persistent across 2 bars", px)));
                        }
                    }
                }
            }

            // ---------------------------------------------------------------
            // IMB-09 REVERSAL PATTERN
            // Python: prior bar dominated by buy imbalances, current dominated by sell (or vice versa).
            // Dominant = side has >= 2 imbalances AND > 2x the other side.
            // ---------------------------------------------------------------
            if (session != null && session.ImbalanceHistory != null && session.ImbalanceHistory.Count > 0)
            {
                var priorMap = GetLastHistoryEntry(session.ImbalanceHistory);
                if (priorMap != null)
                {
                    int priorBuyCount  = 0;
                    int priorSellCount = 0;
                    foreach (var kv in priorMap)
                    {
                        if (kv.Key >= 0) priorBuyCount++;
                        else             priorSellCount++;
                    }

                    int currBuy  = buyImbPrices.Count;
                    int currSell = sellImbPrices.Count;

                    bool priorDomBuy  = priorBuyCount  >= 2 && priorBuyCount  > priorSellCount * 2;
                    bool priorDomSell = priorSellCount >= 2 && priorSellCount > priorBuyCount  * 2;
                    bool currDomBuy   = currBuy        >= 2 && currBuy        > currSell       * 2;
                    bool currDomSell  = currSell       >= 2 && currSell       > currBuy        * 2;

                    if (priorDomBuy && currDomSell)
                    {
                        double str = System.Math.Min((priorBuyCount + currSell) / 10.0, 1.0);
                        results.Add(new SignalResult(
                            "IMB-09", -1, str,
                            SignalFlagBits.Mask(SignalFlagBits.IMB_09),
                            string.Format("IMB REVERSAL (bearish): prior had {0} buy imbalances, now {1} sell imbalances",
                                priorBuyCount, currSell)));
                    }
                    else if (priorDomSell && currDomBuy)
                    {
                        double str = System.Math.Min((priorSellCount + currBuy) / 10.0, 1.0);
                        results.Add(new SignalResult(
                            "IMB-09", +1, str,
                            SignalFlagBits.Mask(SignalFlagBits.IMB_09),
                            string.Format("IMB REVERSAL (bullish): prior had {0} sell imbalances, now {1} buy imbalances",
                                priorSellCount, currBuy)));
                    }
                }
            }

            // ---------------------------------------------------------------
            // UPDATE ImbalanceHistory for next bar (IMB-07/09 cross-bar state)
            // Store buy imbalances with positive keys, sell with negative keys.
            // ---------------------------------------------------------------
            if (session != null && session.ImbalanceHistory != null)
            {
                var barMap = new Dictionary<double, double>();
                foreach (double px in buyImbPrices)
                    barMap[px]  = buyRatios.ContainsKey(px) ? buyRatios[px] : 1.0;
                foreach (double px in sellImbPrices)
                    barMap[-px] = sellRatios.ContainsKey(px) ? sellRatios[px] : 1.0;
                SessionContext.Push(session.ImbalanceHistory, barMap);
            }

            return results.ToArray();
        }

        // -----------------------------------------------------------------------
        // Private helpers
        // -----------------------------------------------------------------------

        /// <summary>Emit IMB-01, IMB-06, and IMB-08 for a diagonal-triggered level.</summary>
        private static void EmitSingleOversizedDiag(
            double price, double ratio,
            int direction,
            double singleThreshold, double oversizedThreshold,
            List<SignalResult> results)
        {
            bool isOversized = ratio >= oversizedThreshold;
            string dirLabel  = direction > 0 ? "BUY" : "SELL";

            // IMB-01: every qualifying level
            results.Add(new SignalResult(
                "IMB-01", direction, System.Math.Min(ratio / 10.0, 1.0),
                SignalFlagBits.Mask(SignalFlagBits.IMB_01),
                string.Format("SINGLE {0} IMB at {1:F2}: {2:F1}x ratio [P-tick diag]",
                    dirLabel, price, ratio)));

            // IMB-06: oversized
            if (isOversized)
            {
                results.Add(new SignalResult(
                    "IMB-06", direction, System.Math.Min(ratio / 20.0, 1.0),
                    SignalFlagBits.Mask(SignalFlagBits.IMB_06),
                    string.Format("OVERSIZED {0} IMB at {1:F2}: {2:F1}x ratio [P-tick diag]",
                        dirLabel, price, ratio)));
            }

            // IMB-08: diagonal (always emitted for diagonal scan hits)
            results.Add(new SignalResult(
                "IMB-08", direction, System.Math.Min(ratio / 10.0, 1.0),
                SignalFlagBits.Mask(SignalFlagBits.IMB_08),
                string.Format("DIAGONAL {0} IMB at {1:F2}: {2:F1}x ratio [P-tick diag]",
                    dirLabel, price, ratio)));
        }

        /// <summary>
        /// Find consecutive runs in imb_prices and emit IMB-03 stacked signals.
        /// Python: imbalance.py lines 170-209.
        /// </summary>
        private static void EmitStackedRuns(
            List<double> imbPrices, int direction, double tickSize,
            List<SignalResult> results, ImbalanceConfig cfg)
        {
            if (imbPrices.Count < cfg.StackedT1) return;

            // Find runs: consecutive prices within gap_tolerance ticks
            double gapMax = tickSize * cfg.StackedGapTolerance;
            var runs = new List<List<double>>();
            var currentRun = new List<double> { imbPrices[0] };

            for (int j = 1; j < imbPrices.Count; j++)
            {
                if (imbPrices[j] - imbPrices[j - 1] <= gapMax + tickSize * 0.01)
                {
                    currentRun.Add(imbPrices[j]);
                }
                else
                {
                    if (currentRun.Count >= cfg.StackedT1) runs.Add(currentRun);
                    currentRun = new List<double> { imbPrices[j] };
                }
            }
            if (currentRun.Count >= cfg.StackedT1) runs.Add(currentRun);

            foreach (var run in runs)
            {
                int n = run.Count;
                string tier;
                double str;
                if (n >= cfg.StackedT3)      { tier = "T3"; str = 1.0; }
                else if (n >= cfg.StackedT2) { tier = "T2"; str = 0.66; }
                else                         { tier = "T1"; str = 0.33; }

                double midPx   = run[run.Count / 2];
                string dirLabel = direction > 0 ? "BUY" : "SELL";
                results.Add(new SignalResult(
                    "IMB-03", direction, str,
                    SignalFlagBits.Mask(SignalFlagBits.IMB_03),
                    string.Format("STACKED {0} x{1} ({2}) at {3:F2}",
                        dirLabel, n, tier, midPx)));
            }
        }

        /// <summary>Return the most recently enqueued entry from a Queue without dequeuing.</summary>
        private static Dictionary<double, double> GetLastHistoryEntry(
            Queue<Dictionary<double, double>> q)
        {
            if (q.Count == 0) return null;
            Dictionary<double, double> last = null;
            foreach (var entry in q) last = entry;
            return last;
        }
    }
}
