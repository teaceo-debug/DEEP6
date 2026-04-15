// VolPatternDetector: ISignalDetector implementation for VOLP-01..06.
//
// Wave 3 (TRIVIAL): VOLP-02 Bubble, VOLP-03 Surge, VOLP-06 Big Delta Per Level
// Wave 4 (MODERATE): VOLP-01 Sequencing (3+ bars escalating),
//                    VOLP-04 POC Wave (POC migrating direction),
//                    VOLP-05 Delta Velocity Spike
//
// Python reference: deep6/engines/vol_patterns.py VolPatternEngine
//
// Rolling state: session.VolHistory (VOLP-01), session.PocHistory (VOLP-04),
//                session.DeltaHistory (VOLP-05 delta velocity).
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.VolPattern
{
    /// <summary>
    /// Configuration for VolPatternDetector.
    /// Python reference: deep6/engines/signal_config.py VolPatternConfig
    /// </summary>
    public sealed class VolPatternConfig
    {
        /// <summary>Bubble: level vol > avg_level_vol * this multiplier. Python: bubble_mult=3.0</summary>
        public double BubbleMult = 3.0;

        /// <summary>Surge: bar vol > vol_ema * this multiplier. Python: surge_mult=3.0</summary>
        public double SurgeMult = 3.0;

        /// <summary>Surge: min |delta|/vol ratio to assign direction. Python: surge_delta_min_ratio=0.10</summary>
        public double SurgeDeltaMinRatio = 0.10;

        /// <summary>Sequencing: min bars for vol escalation. Python: vol_seq_min_bars=3</summary>
        public int VolSeqMinBars = 3;

        /// <summary>Sequencing: each bar vol >= prior * this ratio. Python: vol_seq_step_ratio=1.0 (non-decreasing)</summary>
        public double VolSeqStepRatio = 1.0;

        /// <summary>Big delta per level: |net_delta_at_level|/total_vol threshold. Python: big_delta_level_ratio=0.15</summary>
        public double BigDeltaLevelRatio = 0.15;

        /// <summary>POC wave: bars of monotonic POC migration. Python: poc_wave_bars=3</summary>
        public int PocWaveBars = 3;

        /// <summary>Delta velocity spike: |velocity| > vol_ema * this multiplier. Python: delta_velocity_mult=0.5</summary>
        public double DeltaVelocityMult = 0.5;
    }

    /// <summary>
    /// Detects VOLP-01..06 volume pattern signals.
    ///
    /// Implements ISignalDetector. Rolling state in SessionContext.
    /// Python reference: deep6/engines/vol_patterns.py VolPatternEngine
    /// </summary>
    public sealed class VolPatternDetector : ISignalDetector
    {
        private readonly VolPatternConfig _cfg;

        public VolPatternDetector() : this(new VolPatternConfig()) { }

        public VolPatternDetector(VolPatternConfig cfg)
        {
            _cfg = cfg ?? new VolPatternConfig();
        }

        /// <inheritdoc/>
        public string Name => "VolPattern";

        /// <inheritdoc/>
        public void Reset()
        {
            // All rolling state is on SessionContext; Reset() is a no-op.
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || bar.TotalVol == 0 || bar.Levels == null || bar.Levels.Count == 0)
                return Array.Empty<SignalResult>();

            var results = new List<SignalResult>();
            var cfg     = _cfg;

            double volEma = session != null ? session.VolEma20 : 0;

            // ---------------------------------------------------------------
            // VOLP-01 SEQUENCING
            // Python: 3+ consecutive bars where each vol >= prior * step_ratio
            // AND all bars have same sign of delta (direction consistent).
            // Uses session.VolHistory (totalVol per bar, oldest first).
            // ---------------------------------------------------------------
            if (session != null && session.VolHistory != null)
            {
                long[] volHist = ToArray(session.VolHistory);
                // We need at least (min_bars - 1) prior bars; current bar is the latest
                if (volHist.Length >= cfg.VolSeqMinBars - 1)
                {
                    // Build combined sequence: history + current bar
                    int histLen = volHist.Length;
                    // Walk backwards from current bar to find longest qualifying run
                    // Run: each step vol[i] >= vol[i-1] * step_ratio
                    long[] runVols = new long[histLen + 1];
                    int[] runDir   = new int[histLen + 1];

                    // Fill from history + current
                    for (int i = 0; i < histLen; i++) runVols[i] = volHist[i];
                    runVols[histLen] = bar.TotalVol;

                    // Delta signs: we only have the current bar's delta directly;
                    // for prior bars we use DeltaHistory if available
                    long[] deltaHist = ToArray(session.DeltaHistory);

                    // Build run ending at current bar
                    int runLen = 1;
                    for (int i = histLen - 1; i >= 0; i--)
                    {
                        long newer = runVols[i + 1];
                        long older = runVols[i];
                        if (older > 0 && newer >= older * cfg.VolSeqStepRatio)
                            runLen++;
                        else
                            break;
                    }

                    if (runLen >= cfg.VolSeqMinBars)
                    {
                        // Compute net delta over the run for direction
                        long netDelta = bar.BarDelta;
                        int startIdx = histLen - (runLen - 1);
                        if (startIdx >= 0 && deltaHist.Length >= runLen - 1)
                        {
                            for (int i = deltaHist.Length - (runLen - 1); i < deltaHist.Length; i++)
                                netDelta += deltaHist[i];
                        }
                        int dir = System.Math.Sign(netDelta);
                        double str = System.Math.Min((double)(runLen - cfg.VolSeqMinBars + 1) / (cfg.VolSeqMinBars + 1), 1.0);
                        results.Add(new SignalResult(
                            "VOLP-01", dir, str,
                            SignalFlagBits.Mask(SignalFlagBits.VOLP_01),
                            string.Format("VOL SEQUENCING: {0} bars escalating (each >= {1:F0}% of prior); net delta {2:+#;-#;0}",
                                runLen, cfg.VolSeqStepRatio * 100, netDelta)));
                    }
                }
                // Push current bar's totalVol to history (after evaluation)
                SessionContext.Push(session.VolHistory, bar.TotalVol);
            }

            // ---------------------------------------------------------------
            // VOLP-02 BUBBLE
            // Python: single level vol > avg_level_vol * bubble_mult
            // Direction: ask_dominance = +1, bid_dominance = -1.
            // ---------------------------------------------------------------
            if (bar.Levels.Count > 0)
            {
                double avgLevelVol = (double)bar.TotalVol / bar.Levels.Count;
                double bubbleTh    = avgLevelVol * cfg.BubbleMult;
                long   bestVol     = 0;
                double bestPx      = 0;
                int    bestNet     = 0;

                foreach (var kv in bar.Levels)
                {
                    long lv = kv.Value.AskVol + kv.Value.BidVol;
                    if (lv > bubbleTh && lv > bestVol)
                    {
                        bestVol = lv;
                        bestPx  = kv.Key;
                        bestNet = (int)(kv.Value.AskVol - kv.Value.BidVol);
                    }
                }

                if (bestVol > 0)
                {
                    int dir    = System.Math.Sign(bestNet);
                    double str = System.Math.Min((bestVol / bubbleTh - 1.0) / 3.0, 1.0);
                    results.Add(new SignalResult(
                        "VOLP-02", dir, str,
                        SignalFlagBits.Mask(SignalFlagBits.VOLP_02),
                        string.Format("VOL BUBBLE at {0:F2}: {1} contracts ({2:F1}x avg level vol)",
                            bestPx, bestVol, bestVol / avgLevelVol)));
                }
            }

            // ---------------------------------------------------------------
            // VOLP-03 SURGE
            // Python: bar.total_vol > vol_ema * surge_mult
            // Direction = sign(delta) if |delta/vol| > surge_delta_min_ratio, else 0.
            // ---------------------------------------------------------------
            if (volEma > 0)
            {
                double surgeTh = volEma * cfg.SurgeMult;
                if (bar.TotalVol > surgeTh)
                {
                    double deltaRatio = (double)System.Math.Abs(bar.BarDelta) / bar.TotalVol;
                    int dir = deltaRatio > cfg.SurgeDeltaMinRatio ? System.Math.Sign(bar.BarDelta) : 0;
                    double str = System.Math.Min((bar.TotalVol / surgeTh - 1.0) / 2.0, 1.0);
                    results.Add(new SignalResult(
                        "VOLP-03", dir, str,
                        SignalFlagBits.Mask(SignalFlagBits.VOLP_03),
                        string.Format("VOL SURGE: {0} contracts ({1:F1}x ema); delta {2:+#;-#;0} ({3:F1}%)",
                            bar.TotalVol, bar.TotalVol / volEma, bar.BarDelta, deltaRatio * 100)));
                }
            }

            // ---------------------------------------------------------------
            // VOLP-04 POC WAVE
            // Python: last poc_wave_bars POC prices are strictly monotonic (all up or all down).
            // Uses session.PocHistory (prior bar POC prices, oldest first).
            // ---------------------------------------------------------------
            if (session != null && session.PocHistory != null)
            {
                double[] pocHist = ToArray(session.PocHistory);
                int n = cfg.PocWaveBars;
                if (pocHist.Length >= n)
                {
                    // Check last n entries are strictly monotonic
                    int startPos = pocHist.Length - n;
                    bool allUp   = true;
                    bool allDown = true;
                    for (int i = startPos; i < pocHist.Length - 1; i++)
                    {
                        if (pocHist[i + 1] <= pocHist[i]) allUp   = false;
                        if (pocHist[i + 1] >= pocHist[i]) allDown = false;
                    }

                    if (allUp || allDown)
                    {
                        int dir = allUp ? +1 : -1;
                        double displacement = System.Math.Abs(pocHist[pocHist.Length - 1] - pocHist[startPos]);
                        double str = System.Math.Min(displacement / 10.0, 1.0);
                        results.Add(new SignalResult(
                            "VOLP-04", dir, str,
                            SignalFlagBits.Mask(SignalFlagBits.VOLP_04),
                            string.Format("POC WAVE: POC migrated {0:+0;-0;0} for {1} bars ({2:F2} → {3:F2})",
                                dir, n, pocHist[startPos], pocHist[pocHist.Length - 1])));
                    }
                }
            }

            // ---------------------------------------------------------------
            // VOLP-05 DELTA VELOCITY SPIKE
            // Python: velocity = bar.bar_delta - prior_bar.bar_delta
            //         fire if |velocity| > vol_ema * delta_velocity_mult
            // Uses session.DeltaHistory to get prior bar's delta.
            // ---------------------------------------------------------------
            if (session != null && session.DeltaHistory != null && volEma > 0)
            {
                long[] deltaHist = ToArray(session.DeltaHistory);
                if (deltaHist.Length >= 1)
                {
                    long priorDelta = deltaHist[deltaHist.Length - 1];
                    long velocity   = bar.BarDelta - priorDelta;
                    double velTh    = volEma * cfg.DeltaVelocityMult;

                    if (System.Math.Abs(velocity) > velTh)
                    {
                        int dir    = System.Math.Sign(velocity);
                        double str = System.Math.Min((double)System.Math.Abs(velocity) / (velTh * 3.0), 1.0);
                        results.Add(new SignalResult(
                            "VOLP-05", dir, str,
                            SignalFlagBits.Mask(SignalFlagBits.VOLP_05),
                            string.Format("DELTA VELOCITY SPIKE: velocity {0:+#;-#;0} (prior {1:+#;-#;0} → current {2:+#;-#;0}); threshold {3:F0}",
                                velocity, priorDelta, bar.BarDelta, velTh)));
                    }
                }
            }

            // ---------------------------------------------------------------
            // VOLP-06 BIG DELTA PER LEVEL
            // Python: find level with |ask_vol - bid_vol| / total_vol > big_delta_level_ratio
            // ---------------------------------------------------------------
            if (bar.TotalVol > 0)
            {
                double bigTh = cfg.BigDeltaLevelRatio;
                double bestRatio = 0;
                double bestPx06  = 0;
                int bestDir06    = 0;

                foreach (var kv in bar.Levels)
                {
                    long net = kv.Value.AskVol - kv.Value.BidVol;
                    double r = (double)System.Math.Abs(net) / bar.TotalVol;
                    if (r > bigTh && r > bestRatio)
                    {
                        bestRatio = r;
                        bestPx06  = kv.Key;
                        bestDir06 = System.Math.Sign(net);
                    }
                }

                if (bestRatio > 0)
                {
                    results.Add(new SignalResult(
                        "VOLP-06", bestDir06, System.Math.Min(bestRatio / (bigTh * 2), 1.0),
                        SignalFlagBits.Mask(SignalFlagBits.VOLP_06),
                        string.Format("BIG DELTA PER LEVEL at {0:F2}: {1:F1}% of session vol",
                            bestPx06, bestRatio * 100)));
                }
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
