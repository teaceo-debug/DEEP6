// DeltaDetector: ISignalDetector implementation for DELT-01..11 (excluding DELT-08/10, Wave 5).
//
// Wave 3 (TRIVIAL): DELT-01 Rise/Drop, DELT-02 Tail, DELT-03 Reversal,
//                   DELT-05 CVD Flip, DELT-09 At Session Min/Max
// Wave 4 (MODERATE): DELT-04 Divergence (3-bar short-window),
//                    DELT-06 Delta Trap, DELT-07 Delta Sweep, DELT-11 Velocity
//
// DEFERRED to Wave 5: DELT-08 Slingshot (4-bar history), DELT-10 CVD polyfit (LeastSquares)
//
// Python reference: deep6/engines/delta.py DeltaEngine.process()
//
// Rolling state: uses session.DeltaHistory, session.CvdHistory, session.PriceHistory.
// Push current bar's values at END of OnBar so next bar sees history through prior bar only.
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta
{
    /// <summary>
    /// Configuration for DeltaDetector.
    /// Python reference: deep6/engines/signal_config.py DeltaConfig
    /// </summary>
    public sealed class DeltaConfig
    {
        /// <summary>Tail signal fires when bar closes within this fraction of its intrabar extreme.
        /// Python: tail_threshold=0.95</summary>
        public double TailThreshold = 0.95;

        /// <summary>Minimum |delta|/totalVol ratio for DELT-03 reversal signal.
        /// Python: reversal_min_delta_ratio=0.10</summary>
        public double ReversalMinDeltaRatio = 0.10;

        /// <summary>Lookback for DELT-04 short-window divergence (bars). Python: divergence_lookback=3</summary>
        public int DivergenceLookback = 3;

        /// <summary>Minimum divergence magnitude (slope) to fire DELT-04.
        /// Python: min_divergence_magnitude=0.1 (used as |slope| > threshold)</summary>
        public double DivergenceMagnitude = 0.1;

        /// <summary>Fraction of total vol that qualifies prior bar as "trap delta". Python: trap_delta_ratio=0.35</summary>
        public double TrapDeltaRatio = 0.35;

        /// <summary>Minimum price levels spanning bar for DELT-07 sweep. Python: sweep_min_levels=4</summary>
        public int SweepMinLevels = 4;

        /// <summary>Volume acceleration ratio: second half / first half. Python: sweep_vol_increase_ratio=1.5</summary>
        public double SweepVolIncreaseRatio = 1.5;

        /// <summary>CVD velocity threshold for DELT-11 fire (absolute units). Python: velocity_accel_ratio=0.15
        /// (fire when |accel| > totalVol * velocity_accel_ratio)</summary>
        public double VelocityAccelRatio = 0.15;
    }

    /// <summary>
    /// Detects DELT-01..11 (minus DELT-08/10 deferred to Wave 5).
    ///
    /// Implements ISignalDetector. Rolling history state lives in SessionContext.
    /// Python reference: deep6/engines/delta.py DeltaEngine
    /// </summary>
    public sealed class DeltaDetector : ISignalDetector
    {
        private readonly DeltaConfig _cfg;

        public DeltaDetector() : this(new DeltaConfig()) { }

        public DeltaDetector(DeltaConfig cfg)
        {
            _cfg = cfg ?? new DeltaConfig();
        }

        /// <inheritdoc/>
        public string Name => "Delta";

        /// <inheritdoc/>
        public void Reset()
        {
            // All rolling state is on SessionContext; ResetSession() clears it.
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || bar.TotalVol == 0)
                return Array.Empty<SignalResult>();

            var results = new List<SignalResult>();
            var cfg     = _cfg;

            long   delta = bar.BarDelta;
            long   cvd   = bar.Cvd;
            long   total = bar.TotalVol;

            // Snapshot histories BEFORE pushing current bar (so history = prior bars only)
            long[] deltaArr = ToArray(session?.DeltaHistory);
            long[] cvdArr   = ToArray(session?.CvdHistory);
            double[] priceArr = ToArray(session?.PriceHistory);

            // ---------------------------------------------------------------
            // DELT-01 RISE/DROP — always fires when delta != 0
            // Python: delta > 0 → RISE, < 0 → DROP. Strength = |delta|/totalVol.
            // ---------------------------------------------------------------
            if (delta > 0)
            {
                results.Add(new SignalResult(
                    "DELT-01", +1, System.Math.Min((double)delta / total, 1.0),
                    SignalFlagBits.Mask(SignalFlagBits.DELT_01),
                    string.Format("DELTA RISE: {0:+#;-#;0} ({1:F0}% of vol)",
                        delta, (double)delta / total * 100)));
            }
            else if (delta < 0)
            {
                results.Add(new SignalResult(
                    "DELT-01", -1, System.Math.Min((double)-delta / total, 1.0),
                    SignalFlagBits.Mask(SignalFlagBits.DELT_01),
                    string.Format("DELTA DROP: {0:+#;-#;0} ({1:F0}% of vol)",
                        delta, (double)-delta / total * 100)));
            }

            // ---------------------------------------------------------------
            // DELT-02 TAIL — delta closes near its intrabar extreme
            // Python: tail_ratio = delta / extreme >= tail_threshold (0.95)
            // MaxDelta / MinDelta are intrabar running extremes on FootprintBar.
            // ---------------------------------------------------------------
            if (delta > 0)
            {
                long extreme = bar.MaxDelta > 0 ? bar.MaxDelta : delta;
                double tailRatio = extreme > 0 ? (double)delta / extreme : 0.0;
                if (tailRatio >= cfg.TailThreshold)
                {
                    results.Add(new SignalResult(
                        "DELT-02", +1, tailRatio,
                        SignalFlagBits.Mask(SignalFlagBits.DELT_02),
                        string.Format("DELTA TAIL: closed at {0:F0}% of intrabar max ({1:+#;-#;0}/{2:+#;-#;0})",
                            tailRatio * 100, delta, extreme)));
                }
            }
            else if (delta < 0)
            {
                long extreme = bar.MinDelta < 0 ? bar.MinDelta : delta;
                double tailRatio = extreme < 0 ? (double)delta / extreme : 0.0;
                if (tailRatio >= cfg.TailThreshold)
                {
                    results.Add(new SignalResult(
                        "DELT-02", -1, tailRatio,
                        SignalFlagBits.Mask(SignalFlagBits.DELT_02),
                        string.Format("DELTA TAIL: closed at {0:F0}% of intrabar min ({1:+#;-#;0}/{2:+#;-#;0})",
                            tailRatio * 100, delta, extreme)));
                }
            }

            // ---------------------------------------------------------------
            // DELT-03 REVERSAL — delta sign contradicts bar direction
            // Python: close > open but delta < 0, or close < open but delta > 0
            // Strength = min(|delta|/totalVol, 1.0).
            // ---------------------------------------------------------------
            if (total > 0)
            {
                double deltaRatioAbs = (double)System.Math.Abs(delta) / total;
                if (deltaRatioAbs >= cfg.ReversalMinDeltaRatio)
                {
                    bool barBullish = bar.Close > bar.Open;
                    bool barBearish = bar.Close < bar.Open;
                    if (barBullish && delta < 0)
                    {
                        results.Add(new SignalResult(
                            "DELT-03", -1, System.Math.Min(deltaRatioAbs, 1.0),
                            SignalFlagBits.Mask(SignalFlagBits.DELT_03),
                            string.Format("DELTA REVERSAL (bearish hidden): bar closed UP but delta={0:+#;-#;0}", delta)));
                    }
                    else if (barBearish && delta > 0)
                    {
                        results.Add(new SignalResult(
                            "DELT-03", +1, System.Math.Min(deltaRatioAbs, 1.0),
                            SignalFlagBits.Mask(SignalFlagBits.DELT_03),
                            string.Format("DELTA REVERSAL (bullish hidden): bar closed DOWN but delta={0:+#;-#;0}", delta)));
                    }
                }
            }

            // ---------------------------------------------------------------
            // DELT-04 DIVERGENCE (short-window 3-bar)
            // Plan spec: compare price slope vs delta slope over last 3 bars.
            // priceSlope = (bar.Close - priorBar2.Close) / 2.0
            // deltaSlope = (bar.BarDelta - priorBarDelta2) / 2.0
            // Fire when signs differ AND both |slopes| > DivergenceMagnitude.
            //
            // Python uses the N-bar high/low comparison (see delta.py lines 191-207).
            // This wave uses the PLAN SPEC 3-bar slope approach (simpler, no polyfit).
            // ---------------------------------------------------------------
            int divLb = cfg.DivergenceLookback; // = 3
            if (priceArr.Length >= divLb - 1 && cvdArr.Length >= divLb - 1)
            {
                // We have at least 2 prior prices/cvds in history + current bar = 3 total
                double priorClose2 = priceArr[priceArr.Length - (divLb - 1)];
                long   priorCvd2   = cvdArr[cvdArr.Length - (divLb - 1)];

                double priceSlope = (bar.Close - priorClose2) / (divLb - 1.0);
                double deltaSlope = (double)(cvd - priorCvd2) / (divLb - 1.0);

                if (System.Math.Abs(priceSlope) > cfg.DivergenceMagnitude &&
                    System.Math.Abs(deltaSlope) > cfg.DivergenceMagnitude &&
                    System.Math.Sign(priceSlope) != System.Math.Sign((long)(deltaSlope + 0.5)))
                {
                    // Direction opposite to priceSlope (fade the divergence)
                    int dir = -System.Math.Sign(priceSlope);
                    string label = priceSlope > 0 ? "BEARISH DIVERGENCE: price up but CVD failing"
                                                   : "BULLISH DIVERGENCE: price down but CVD holding";
                    results.Add(new SignalResult(
                        "DELT-04", dir, 0.8,
                        SignalFlagBits.Mask(SignalFlagBits.DELT_04),
                        label));
                }
            }

            // ---------------------------------------------------------------
            // DELT-05 CVD FLIP — sign change in cumulative delta
            // Python: prev_cvd >= 0 and cvd < 0 → short; prev_cvd <= 0 and cvd > 0 → long
            // ---------------------------------------------------------------
            if (cvdArr.Length >= 1)
            {
                long prevCvd = cvdArr[cvdArr.Length - 1];
                if (prevCvd >= 0 && cvd < 0)
                {
                    results.Add(new SignalResult(
                        "DELT-05", -1, 0.6,
                        SignalFlagBits.Mask(SignalFlagBits.DELT_05),
                        string.Format("CVD FLIP: crossed below zero ({0:+#;-#;0} → {1:+#;-#;0})",
                            prevCvd, cvd)));
                }
                else if (prevCvd <= 0 && cvd > 0)
                {
                    results.Add(new SignalResult(
                        "DELT-05", +1, 0.6,
                        SignalFlagBits.Mask(SignalFlagBits.DELT_05),
                        string.Format("CVD FLIP: crossed above zero ({0:+#;-#;0} → {1:+#;-#;0})",
                            prevCvd, cvd)));
                }
            }

            // ---------------------------------------------------------------
            // DELT-06 TRAP — aggressive prior delta + price reversal
            // Python: prev_delta > total_vol * trap_delta_ratio AND close < open → bear trap
            //         prev_delta < -total_vol * trap_delta_ratio AND close > open → bull trap
            // Uses DeltaHistory (prior bar delta).
            // ---------------------------------------------------------------
            if (deltaArr.Length >= 1)
            {
                long prevDelta = deltaArr[deltaArr.Length - 1];
                double trapTh  = total * cfg.TrapDeltaRatio;

                // Strong buying delta then price drops (longs trapped)
                if (prevDelta > trapTh && bar.Close < bar.Open)
                {
                    results.Add(new SignalResult(
                        "DELT-06", -1, 0.7,
                        SignalFlagBits.Mask(SignalFlagBits.DELT_06),
                        string.Format("DELTA TRAP: prev delta={0:+#;-#;0} (bullish) but price dropped",
                            prevDelta)));
                }
                // Strong selling delta then price rises (shorts trapped)
                if (prevDelta < -trapTh && bar.Close > bar.Open)
                {
                    results.Add(new SignalResult(
                        "DELT-06", +1, 0.7,
                        SignalFlagBits.Mask(SignalFlagBits.DELT_06),
                        string.Format("DELTA TRAP: prev delta={0:+#;-#;0} (bearish) but price rose",
                            prevDelta)));
                }
            }

            // ---------------------------------------------------------------
            // DELT-07 SWEEP — rapid delta accumulation, volume accelerates
            // Python: bar spans >= sweep_min_levels AND second-half vol > first-half * ratio
            // ---------------------------------------------------------------
            if (bar.Levels != null && bar.Levels.Count >= cfg.SweepMinLevels)
            {
                var sortedPrices = new List<double>(bar.Levels.Keys);
                int mid = sortedPrices.Count / 2;

                long firstHalfVol = 0;
                for (int i = 0; i < mid; i++)
                {
                    var lv = bar.Levels[sortedPrices[i]];
                    firstHalfVol += lv.BidVol + lv.AskVol;
                }
                long secondHalfVol = 0;
                for (int i = mid; i < sortedPrices.Count; i++)
                {
                    var lv = bar.Levels[sortedPrices[i]];
                    secondHalfVol += lv.BidVol + lv.AskVol;
                }

                if (firstHalfVol > 0 && secondHalfVol >= firstHalfVol * cfg.SweepVolIncreaseRatio)
                {
                    int dir = delta >= 0 ? +1 : -1;
                    results.Add(new SignalResult(
                        "DELT-07", dir, 0.8,
                        SignalFlagBits.Mask(SignalFlagBits.DELT_07),
                        string.Format("DELTA SWEEP: {0} levels, vol accelerated ({1} → {2}, {3:F1}x increase)",
                            sortedPrices.Count, firstHalfVol, secondHalfVol,
                            (double)secondHalfVol / firstHalfVol)));
                }
            }

            // ---------------------------------------------------------------
            // DELT-09 AT SESSION MIN/MAX
            // Python: if cvd >= session_max → bearish warning; if cvd <= session_min → bullish warning
            // Use session.SessionMaxDelta / SessionMinDelta (updated AFTER evaluation this bar).
            // ---------------------------------------------------------------
            if (session != null)
            {
                long sMax = session.SessionMaxDelta;
                long sMin = session.SessionMinDelta;

                // Only fire if we have meaningful session range
                if (sMax != sMin)
                {
                    if (delta >= sMax && sMax != 0)
                    {
                        results.Add(new SignalResult(
                            "DELT-09", +1, 0.5,
                            SignalFlagBits.Mask(SignalFlagBits.DELT_09),
                            string.Format("CVD AT SESSION MAX: {0:+#;-#;0}", delta)));
                    }
                    if (delta <= sMin && sMin != 0)
                    {
                        results.Add(new SignalResult(
                            "DELT-09", -1, 0.5,
                            SignalFlagBits.Mask(SignalFlagBits.DELT_09),
                            string.Format("CVD AT SESSION MIN: {0:+#;-#;0}", delta)));
                    }
                }

                // Update session extremes AFTER evaluation (so this bar is considered next time)
                if (delta > session.SessionMaxDelta) session.SessionMaxDelta = delta;
                if (delta < session.SessionMinDelta) session.SessionMinDelta = delta;
            }

            // ---------------------------------------------------------------
            // DELT-11 VELOCITY — rate of change of CVD (acceleration)
            // Python: velocity = cvd[-1] - cvd[-2]; accel = velocity - (cvd[-2] - cvd[-3])
            //         fires when |accel| > totalVol * velocity_accel_ratio
            // Requires at least 2 prior CVD values in history.
            // ---------------------------------------------------------------
            if (cvdArr.Length >= 2)
            {
                long vel  = cvd - cvdArr[cvdArr.Length - 1];
                long vel1 = cvdArr[cvdArr.Length - 1] - cvdArr[cvdArr.Length - 2];
                long accel = vel - vel1;
                double accelTh = total * cfg.VelocityAccelRatio;

                if (System.Math.Abs(accel) > accelTh)
                {
                    int dir = accel > 0 ? +1 : -1;
                    results.Add(new SignalResult(
                        "DELT-11", dir, System.Math.Min((double)System.Math.Abs(accel) / total, 1.0),
                        SignalFlagBits.Mask(SignalFlagBits.DELT_11),
                        string.Format("DELTA VELOCITY: accel={0:+#;-#;0} — {1}",
                            accel, dir > 0 ? "accelerating" : "decelerating")));
                }
            }

            // ---------------------------------------------------------------
            // PUSH current bar values to histories AFTER all signals evaluated
            // ---------------------------------------------------------------
            if (session != null)
            {
                SessionContext.Push(session.DeltaHistory, delta);
                SessionContext.Push(session.CvdHistory,   cvd);
                SessionContext.Push(session.PriceHistory, bar.Close);
            }

            return results.ToArray();
        }

        // -----------------------------------------------------------------------
        // Private helpers
        // -----------------------------------------------------------------------

        private static long[] ToArray(Queue<long> q)
        {
            if (q == null || q.Count == 0) return Array.Empty<long>();
            var arr = new long[q.Count];
            int i = 0;
            foreach (long v in q) arr[i++] = v;
            return arr;
        }

        private static double[] ToArray(Queue<double> q)
        {
            if (q == null || q.Count == 0) return Array.Empty<double>();
            var arr = new double[q.Count];
            int i = 0;
            foreach (double v in q) arr[i++] = v;
            return arr;
        }
    }
}
