// TrapDetector: ISignalDetector implementation for TRAP-01..05.
//
// Wave 4 (MODERATE): TRAP-01 Inverse Imbalance Trap (stacked buy imb in red bar),
//                    TRAP-02 Delta Trap (strong delta + price failure),
//                    TRAP-03 False Breakout (break + close back inside),
//                    TRAP-04 Record Vol Rejection (record vol + rejection wick)
// Wave 5 (HARD): TRAP-05 CVD Trend Reversal (polyfit via LeastSquares)
//
// Python reference:
//   TRAP-01: deep6/engines/imbalance.py ImbalanceType.INVERSE_TRAP (stacked version)
//   TRAP-02: deep6/engines/trap.py TrapEngine._detect_delta_trap
//   TRAP-03: deep6/engines/trap.py TrapEngine._detect_false_breakout
//   TRAP-04: deep6/engines/trap.py TrapEngine._detect_high_vol_rejection
//
// TRAP-01 vs IMB-05 distinction:
//   IMB-05 fires when any inverse imbalance exists (even a single one).
//   TRAP-01 requires STACKED imbalances (>= StackedMinCount consecutive levels)
//   against bar direction — a higher conviction setup.
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Math;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Trap
{
    /// <summary>
    /// Configuration for TrapDetector.
    /// Python reference: deep6/engines/signal_config.py TrapConfig
    /// </summary>
    public sealed class TrapConfig
    {
        /// <summary>Minimum stacked consecutive imbalances against bar direction for TRAP-01. Default=3 (T1 tier).</summary>
        public int StackedMinCount = 3;

        /// <summary>Imbalance ratio threshold for TRAP-01 diagonal scan. Default=3.0 (matches IMB default).</summary>
        public double ImbalanceRatio = 3.0;

        /// <summary>Min |prior_delta|/prior_totalVol for TRAP-02 to qualify. Python: trap_delta_ratio=0.35</summary>
        public double TrapDeltaRatio = 0.35;

        /// <summary>Vol multiplier of VolEma needed to qualify for TRAP-03 false breakout. Python: false_breakout_vol_mult=1.0</summary>
        public double FalseBreakoutVolMult = 1.0;

        /// <summary>Vol multiplier of VolEma for TRAP-04 high-volume rejection. Python: hvr_vol_mult=1.5</summary>
        public double HvrVolMult = 1.5;

        /// <summary>Minimum wick fraction for TRAP-04 to fire. Python: hvr_wick_min=0.35</summary>
        public double HvrWickMin = 0.35;

        // ---- TRAP-05 CVD Trend Reversal (Wave 5) ----
        /// <summary>Lookback window for CVD polyfit slope. Python: cvd_trap_lookback=10</summary>
        public int CvdTrapLookback = 10;

        /// <summary>Minimum absolute CVD slope to fire TRAP-05. Python: cvd_trap_min_slope=50</summary>
        public double CvdTrapMinSlope = 50.0;
    }

    /// <summary>
    /// Detects TRAP-01 (Inverse Imbalance Trap), TRAP-02 (Delta Trap),
    /// TRAP-03 (False Breakout), TRAP-04 (Record Vol Rejection).
    ///
    /// TRAP-05 is NOT implemented here — it requires least-squares (Wave 5).
    /// Implements ISignalDetector; state for TRAP-02/03 uses session.PriorBar.
    /// Python reference: deep6/engines/trap.py + deep6/engines/imbalance.py
    /// </summary>
    public sealed class TrapDetector : ISignalDetector
    {
        private readonly TrapConfig _cfg;

        public TrapDetector() : this(new TrapConfig()) { }

        public TrapDetector(TrapConfig cfg)
        {
            _cfg = cfg ?? new TrapConfig();
        }

        /// <inheritdoc/>
        public string Name => "Trap";

        /// <inheritdoc/>
        public void Reset()
        {
            // All state lives in SessionContext (PriorBar, VolHistory). Reset() is a no-op.
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || bar.TotalVol == 0)
                return Array.Empty<SignalResult>();

            var results = new List<SignalResult>();

            // ---------------------------------------------------------------
            // TRAP-01 INVERSE IMBALANCE TRAP
            // Python: imbalance.py ImbalanceType.INVERSE_TRAP — stacked buy imbalances in red bar
            //         (longs trapped); stacked sell imbalances in green bar (shorts trapped).
            // Distinct from IMB-05: TRAP-01 requires STACKED (T1 threshold = 3 consecutive levels).
            // Implementation: run diagonal scan, collect imbalance prices by direction,
            //   check for >= StackedMinCount consecutive prices (within 1.5 ticks of each other).
            // ---------------------------------------------------------------
            if (bar.Levels != null && bar.Levels.Count >= 2)
            {
                double tickSize = session != null && session.TickSize > 0 ? session.TickSize : 0.25;
                bool barBearish = bar.Close < bar.Open;
                bool barBullish = bar.Close > bar.Open;

                // Run lightweight diagonal scan for TRAP-01
                var buyPrices  = new List<double>();
                var sellPrices = new List<double>();
                var sortedPx   = new List<double>(bar.Levels.Keys); // ascending

                for (int i = 0; i < sortedPx.Count; i++)
                {
                    double px = sortedPx[i];
                    Cell lv = bar.Levels[px];

                    // Buy imbalance: ask[P] vs bid[P - tickSize]
                    if (i > 0 && System.Math.Abs(sortedPx[i - 1] - (px - tickSize)) < tickSize * 0.01)
                    {
                        long prevBid = bar.Levels[sortedPx[i - 1]].BidVol;
                        long currAsk = lv.AskVol;
                        if ((prevBid > 0 && (double)currAsk / prevBid >= _cfg.ImbalanceRatio) ||
                            (prevBid == 0 && currAsk > 0))
                            buyPrices.Add(px);
                    }

                    // Sell imbalance: bid[P] vs ask[P + tickSize]
                    if (i < sortedPx.Count - 1 && System.Math.Abs(sortedPx[i + 1] - (px + tickSize)) < tickSize * 0.01)
                    {
                        long nextAsk = bar.Levels[sortedPx[i + 1]].AskVol;
                        long currBid = lv.BidVol;
                        if ((nextAsk > 0 && (double)currBid / nextAsk >= _cfg.ImbalanceRatio) ||
                            (nextAsk == 0 && currBid > 0))
                            sellPrices.Add(px);
                    }
                }

                // Check stacked buy imbalances (>= StackedMinCount consecutive) in a RED bar
                if (barBearish && HasStackedRun(buyPrices, tickSize, _cfg.StackedMinCount))
                {
                    double str = System.Math.Min((double)buyPrices.Count / 7.0, 1.0);
                    results.Add(new SignalResult(
                        "TRAP-01", -1, str,
                        SignalFlagBits.Mask(SignalFlagBits.TRAP_01),
                        string.Format("INVERSE IMB TRAP: {0} stacked BUY imbalances in RED bar — longs trapped",
                            buyPrices.Count)));
                }

                // Check stacked sell imbalances in a GREEN bar
                if (barBullish && HasStackedRun(sellPrices, tickSize, _cfg.StackedMinCount))
                {
                    double str = System.Math.Min((double)sellPrices.Count / 7.0, 1.0);
                    results.Add(new SignalResult(
                        "TRAP-01", +1, str,
                        SignalFlagBits.Mask(SignalFlagBits.TRAP_01),
                        string.Format("INVERSE IMB TRAP: {0} stacked SELL imbalances in GREEN bar — shorts trapped",
                            sellPrices.Count)));
                }
            }

            // ---------------------------------------------------------------
            // TRAP-02 DELTA TRAP
            // Python: prior bar |delta|/totalVol >= trap_delta_ratio
            //         AND both delta and price reversed on current bar.
            // Uses session.PriorBar.
            // ---------------------------------------------------------------
            FootprintBar priorBar = session?.PriorBar;
            if (priorBar != null && priorBar.TotalVol > 0)
            {
                double priorRatio = (double)System.Math.Abs(priorBar.BarDelta) / priorBar.TotalVol;
                if (priorRatio >= _cfg.TrapDeltaRatio)
                {
                    bool priorBull = priorBar.BarDelta > 0;
                    bool deltaReversed = (priorBull && bar.BarDelta < 0) || (!priorBull && bar.BarDelta > 0);
                    bool priceReversed = (priorBull && bar.Close < bar.Open) || (!priorBull && bar.Close > bar.Open);

                    if (deltaReversed && priceReversed)
                    {
                        int dir    = bar.BarDelta > 0 ? +1 : -1;
                        double str = System.Math.Min(priorRatio / (_cfg.TrapDeltaRatio * 2.0), 1.0);
                        results.Add(new SignalResult(
                            "TRAP-02", dir, str,
                            SignalFlagBits.Mask(SignalFlagBits.TRAP_02),
                            string.Format("DELTA TRAP: prior delta ratio {0:F2} reversed; current delta {1:+#;-#;0}",
                                priorRatio, bar.BarDelta)));
                    }
                }
            }

            // ---------------------------------------------------------------
            // TRAP-03 FALSE BREAKOUT
            // Python: bar.high > prior.high AND bar.close < prior.high → longs trapped (dir=-1)
            //         bar.low < prior.low AND bar.close > prior.low   → shorts trapped (dir=+1)
            // Vol gate: bar.total_vol > vol_ema * false_breakout_vol_mult
            // ---------------------------------------------------------------
            if (priorBar != null)
            {
                double volEma  = session?.VolEma20 ?? 0;
                double volGate = volEma * _cfg.FalseBreakoutVolMult;

                if (bar.TotalVol > volGate || volGate <= 0)
                {
                    // Bear false breakout: broke above prior high, closed back below
                    if (bar.High > priorBar.High && bar.Close < priorBar.High)
                    {
                        double str = volGate > 0
                            ? System.Math.Min((bar.TotalVol / volGate - 1.0) / 2.0, 1.0)
                            : 0.5;
                        results.Add(new SignalResult(
                            "TRAP-03", -1, str,
                            SignalFlagBits.Mask(SignalFlagBits.TRAP_03),
                            string.Format("FALSE BREAKOUT TRAP (bear): high {0:F2} > prior {1:F2}, closed {2:F2} < prior high",
                                bar.High, priorBar.High, bar.Close)));
                    }

                    // Bull false breakout: broke below prior low, closed back above
                    if (bar.Low < priorBar.Low && bar.Close > priorBar.Low)
                    {
                        double str = volGate > 0
                            ? System.Math.Min((bar.TotalVol / volGate - 1.0) / 2.0, 1.0)
                            : 0.5;
                        results.Add(new SignalResult(
                            "TRAP-03", +1, str,
                            SignalFlagBits.Mask(SignalFlagBits.TRAP_03),
                            string.Format("FALSE BREAKOUT TRAP (bull): low {0:F2} < prior {1:F2}, closed {2:F2} > prior low",
                                bar.Low, priorBar.Low, bar.Close)));
                    }
                }
            }

            // ---------------------------------------------------------------
            // TRAP-04 RECORD VOL REJECTION
            // Python: bar.total_vol > vol_ema * hvr_vol_mult
            //         AND upper or lower wick vol fraction > hvr_wick_min
            // Wick vol: levels in top or bottom quarter of bar range.
            // Direction: -1 if upper wick dominates, +1 if lower wick dominates.
            // ---------------------------------------------------------------
            if (session != null)
            {
                double volEma4 = session.VolEma20;
                if (volEma4 > 0 && bar.TotalVol > volEma4 * _cfg.HvrVolMult && bar.BarRange > 0 && bar.Levels != null)
                {
                    double rangeQ4  = bar.BarRange / 4.0;
                    double upperZone = bar.High - rangeQ4;
                    double lowerZone = bar.Low  + rangeQ4;

                    long upperVol = 0;
                    long lowerVol = 0;

                    foreach (var kv in bar.Levels)
                    {
                        long lv = kv.Value.AskVol + kv.Value.BidVol;
                        if (kv.Key >= upperZone) upperVol += lv;
                        if (kv.Key <= lowerZone) lowerVol += lv;
                    }

                    double upperFrac = (double)upperVol / bar.TotalVol;
                    double lowerFrac = (double)lowerVol / bar.TotalVol;

                    bool domUpper = upperFrac > lowerFrac && upperFrac >= _cfg.HvrWickMin;
                    bool domLower = lowerFrac >= upperFrac && lowerFrac >= _cfg.HvrWickMin;

                    if (domUpper || domLower)
                    {
                        int dir      = domUpper ? -1 : +1;
                        double wFrac = domUpper ? upperFrac : lowerFrac;
                        double str   = System.Math.Min(wFrac / (_cfg.HvrWickMin * 2.0), 1.0);
                        string label = domUpper ? "upper" : "lower";
                        results.Add(new SignalResult(
                            "TRAP-04", dir, str,
                            SignalFlagBits.Mask(SignalFlagBits.TRAP_04),
                            string.Format("HVR TRAP: vol {0} ({1:F1}×ema), {2} wick frac {3:F1}%",
                                bar.TotalVol, bar.TotalVol / volEma4, label, wFrac * 100)));
                    }
                }
            }

            // ---------------------------------------------------------------
            // TRAP-05 CVD TREND REVERSAL TRAP
            // Python: trap.py lines 298-349 (numpy.polyfit equivalent via LeastSquares)
            // Fire when |cvdSlope| > min_slope AND current bar delta opposes prior CVD trend.
            // ---------------------------------------------------------------
            if (session != null && session.CvdHistory.Count >= _cfg.CvdTrapLookback)
            {
                long[] cvdHistFull = ToLongArray(session.CvdHistory);
                int    w           = _cfg.CvdTrapLookback;
                var    cvdWindow   = new double[w];
                int    startIdx    = cvdHistFull.Length - w;
                for (int i = 0; i < w; i++)
                    cvdWindow[i] = (double)cvdHistFull[startIdx + i];

                var    fit      = LeastSquares.Fit1(cvdWindow);
                double cvdSlope = fit.Slope;

                if (System.Math.Abs(cvdSlope) > _cfg.CvdTrapMinSlope)
                {
                    bool priorTrendBull   = cvdSlope > 0;
                    bool currentDeltaBull = bar.BarDelta > 0;
                    bool reversal = (priorTrendBull && !currentDeltaBull) ||
                                    (!priorTrendBull && currentDeltaBull);

                    if (reversal)
                    {
                        int    dir      = currentDeltaBull ? +1 : -1;
                        double strength = System.Math.Min(System.Math.Abs(cvdSlope) / (_cfg.CvdTrapMinSlope * 10.0), 1.0);
                        results.Add(new SignalResult(
                            "TRAP-05", dir, strength,
                            SignalFlagBits.Mask(SignalFlagBits.TRAP_05),
                            string.Format("CVD TRAP: prior slope {0:+#.00;-#.00;0} (lookback={1}), current delta {2:+#;-#;0} reverses trend (polyfit)",
                                cvdSlope, w, bar.BarDelta)));
                    }
                }
            }

            return results.ToArray();
        }

        // -----------------------------------------------------------------------
        // Private helpers
        // -----------------------------------------------------------------------

        private static long[] ToLongArray(Queue<long> q)
        {
            if (q == null || q.Count == 0) return Array.Empty<long>();
            var arr = new long[q.Count];
            int i = 0;
            foreach (long v in q) arr[i++] = v;
            return arr;
        }

        /// <summary>Returns true if prices list contains a run of >= minCount consecutive prices
        /// (each within 1 tick of the next).</summary>
        private static bool HasStackedRun(List<double> prices, double tickSize, int minCount)
        {
            if (prices.Count < minCount) return false;
            int runLen = 1;
            for (int i = 1; i < prices.Count; i++)
            {
                if (prices[i] - prices[i - 1] <= tickSize * 1.5)
                    runLen++;
                else
                    runLen = 1;
                if (runLen >= minCount) return true;
            }
            return false;
        }
    }
}
