// DeltaDetector: ISignalDetector implementation for DELT-01, DELT-02, DELT-03, DELT-05, DELT-09.
//
// Python reference: deep6/engines/delta.py DeltaEngine.process() lines 108-281
// Signal IDs:
//   DELT-01: Rise/Drop — direction of bar delta
//   DELT-02: Tail — bar delta at 95%+ of intrabar extreme
//   DELT-03: Reversal — delta sign contradicts bar direction
//   DELT-05: CVD Flip — sign change in cumulative delta
//   DELT-09: Delta at session min/max
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).
//
// Rolling state ownership (CONTEXT.md D-01):
//   Session-level queues (DeltaHistory, CvdHistory) live on SessionContext.
//   Session extremes (SessionMaxDelta, SessionMinDelta) also on SessionContext.
//   This detector reads those fields; it does NOT own them.
//   Push to histories happens at END of OnBar so next bar sees current bar as prior.

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta
{
    /// <summary>
    /// Configuration for DeltaDetector.
    /// Python reference: deep6/engines/signal_config.py DeltaConfig lines 101-140
    /// </summary>
    public sealed class DeltaConfig
    {
        /// <summary>Min |delta|/totalVol ratio for DELT-02 tail signal. Python: tail_threshold=0.95</summary>
        public double TailThreshold = 0.95;

        /// <summary>Min |delta|/totalVol ratio for DELT-03 reversal to fire. Python: reversal_min_delta_ratio=0.15</summary>
        public double ReversalMinDeltaRatio = 0.15;

        /// <summary>Fraction of session extreme at which DELT-09 fires (0.95 = within 5% of extreme). Plan spec §DELT-09.</summary>
        public double AtExtremeFraction = 0.95;
    }

    /// <summary>
    /// Detects DELT-01 (Rise/Drop), DELT-02 (Tail), DELT-03 (Reversal),
    /// DELT-05 (CVD Flip), DELT-09 (At Session Min/Max).
    ///
    /// Implements ISignalDetector; uses SessionContext for rolling state.
    /// Python reference: deep6/engines/delta.py DeltaEngine.process()
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
            // Session-level state lives on SessionContext which is reset by the indicator.
            // This detector has no private rolling state.
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || bar.TotalVol == 0)
                return Array.Empty<SignalResult>();

            long delta   = bar.BarDelta;
            long cvd     = bar.Cvd;
            var  results = new List<SignalResult>();

            // --- DELT-01: RISE/DROP ---
            // Python delta.py lines 128-138: classify sign of bar delta.
            // Strength = min(|delta| / totalVol, 1.0)
            // Always emits for non-zero delta (classification signal).
            if (delta > 0)
            {
                double str = System.Math.Min((double)delta / bar.TotalVol, 1.0);
                results.Add(new SignalResult(
                    "DELT-01", +1, str,
                    SignalFlagBits.Mask(SignalFlagBits.DELT_01),
                    string.Format("DELTA RISE: {0:+#;-#;0} ({1:F0}% of vol)",
                        delta, (double)delta / bar.TotalVol * 100)));
            }
            else if (delta < 0)
            {
                double str = System.Math.Min((double)System.Math.Abs(delta) / bar.TotalVol, 1.0);
                results.Add(new SignalResult(
                    "DELT-01", -1, str,
                    SignalFlagBits.Mask(SignalFlagBits.DELT_01),
                    string.Format("DELTA DROP: {0:+#;-#;0} ({1:F0}% of vol)",
                        delta, (double)System.Math.Abs(delta) / bar.TotalVol * 100)));
            }

            // --- DELT-02: TAIL ---
            // Python delta.py lines 140-165:
            //   if delta > 0: extreme = max_delta; fires if delta/extreme >= tail_threshold
            //   if delta < 0: extreme = min_delta; fires if delta/extreme >= tail_threshold
            //   Direction is OPPOSITE to delta sign (tail at +extreme → bearish exhaustion).
            // Note: FootprintBar.MaxDelta/MinDelta are intrabar extremes set by AddTrade().
            //       For test bars constructed via Levels (not AddTrade), MaxDelta=MinDelta=0.
            //       Guard: if extreme == 0, treat as equal to delta (trivial tail ratio of 1.0).
            if (delta > 0)
            {
                long extreme     = bar.MaxDelta > 0 ? bar.MaxDelta : delta;
                double tailRatio = extreme > 0 ? (double)delta / extreme : 0.0;
                if (tailRatio >= _cfg.TailThreshold)
                {
                    results.Add(new SignalResult(
                        "DELT-02", -1, tailRatio,
                        SignalFlagBits.Mask(SignalFlagBits.DELT_02),
                        string.Format("DELTA TAIL at +extreme: {0:F0}% of max ({1:+#}/{2:+#})",
                            tailRatio * 100, delta, extreme)));
                }
            }
            else if (delta < 0)
            {
                long extreme     = bar.MinDelta < 0 ? bar.MinDelta : delta;
                double tailRatio = extreme < 0 ? (double)delta / extreme : 0.0;
                if (tailRatio >= _cfg.TailThreshold)
                {
                    results.Add(new SignalResult(
                        "DELT-02", +1, tailRatio,
                        SignalFlagBits.Mask(SignalFlagBits.DELT_02),
                        string.Format("DELTA TAIL at -extreme: {0:F0}% of min ({1:+#}/{2:+#})",
                            tailRatio * 100, delta, extreme)));
                }
            }

            // --- DELT-03: REVERSAL ---
            // Python delta.py lines 168-187:
            //   Bar direction (close vs open) contradicts delta sign.
            //   Requires min delta ratio to avoid noise on flat bars.
            if (bar.TotalVol > 0)
            {
                double deltaRatioAbs = (double)System.Math.Abs(delta) / bar.TotalVol;
                if (deltaRatioAbs >= _cfg.ReversalMinDeltaRatio)
                {
                    bool barBullish = bar.Close > bar.Open;
                    bool barBearish = bar.Close < bar.Open;

                    if (barBullish && delta < 0)
                    {
                        results.Add(new SignalResult(
                            "DELT-03", -1,
                            System.Math.Min(deltaRatioAbs, 1.0),
                            SignalFlagBits.Mask(SignalFlagBits.DELT_03),
                            string.Format("DELTA REVERSAL (bearish hidden): bar UP but delta={0:+#;-#;0} (selling dominated)",
                                delta)));
                    }
                    else if (barBearish && delta > 0)
                    {
                        results.Add(new SignalResult(
                            "DELT-03", +1,
                            System.Math.Min(deltaRatioAbs, 1.0),
                            SignalFlagBits.Mask(SignalFlagBits.DELT_03),
                            string.Format("DELTA REVERSAL (bullish hidden): bar DOWN but delta={0:+#;-#;0} (buying dominated)",
                                delta)));
                    }
                }
            }

            // --- DELT-05: CVD FLIP ---
            // Python delta.py lines 209-221:
            //   Fires when CVD sign changes vs prior bar CVD.
            //   Uses session.PriorCvd (set by indicator after each bar).
            //   Direction = Math.Sign(current cvd).
            if (session != null)
            {
                long priorCvd = session.PriorCvd;
                if (priorCvd != 0)
                {
                    if (priorCvd >= 0 && cvd < 0)
                    {
                        results.Add(new SignalResult(
                            "DELT-05", -1, 0.6,
                            SignalFlagBits.Mask(SignalFlagBits.DELT_05),
                            string.Format("CVD FLIP: crossed below zero ({0:+#;-#;0} → {1:+#;-#;0})",
                                priorCvd, cvd)));
                    }
                    else if (priorCvd <= 0 && cvd > 0)
                    {
                        results.Add(new SignalResult(
                            "DELT-05", +1, 0.6,
                            SignalFlagBits.Mask(SignalFlagBits.DELT_05),
                            string.Format("CVD FLIP: crossed above zero ({0:+#;-#;0} → {1:+#;-#;0})",
                                priorCvd, cvd)));
                    }
                }
            }

            // --- DELT-09: AT SESSION MIN/MAX ---
            // Plan spec §DELT-09: fire when barDelta >= session.SessionMaxDelta * 0.95 (at session max,
            //   bearish warning) or <= session.SessionMinDelta * 0.95 (at session min, bullish warning).
            //   Update session extremes AFTER evaluation so current bar can be the new extreme next bar.
            if (session != null)
            {
                long sMax = session.SessionMaxDelta;
                long sMin = session.SessionMinDelta;

                // At session max (bearish — buyers potentially exhausted at session peak)
                if (sMax > 0 && delta >= (long)(sMax * _cfg.AtExtremeFraction))
                {
                    results.Add(new SignalResult(
                        "DELT-09", -1, 0.7,
                        SignalFlagBits.Mask(SignalFlagBits.DELT_09),
                        string.Format("DELT-09 AT SESSION MAX: delta={0:+#;-#;0} >= {1:F0}% of session max {2:+#}",
                            delta, _cfg.AtExtremeFraction * 100, sMax)));
                }

                // At session min (bullish — sellers potentially exhausted at session trough)
                if (sMin < 0 && delta <= (long)(sMin * _cfg.AtExtremeFraction))
                {
                    results.Add(new SignalResult(
                        "DELT-09", +1, 0.7,
                        SignalFlagBits.Mask(SignalFlagBits.DELT_09),
                        string.Format("DELT-09 AT SESSION MIN: delta={0:+#;-#;0} <= {1:F0}% of session min {2:+#}",
                            delta, _cfg.AtExtremeFraction * 100, sMin)));
                }

                // Update session extremes after evaluation
                if (delta > session.SessionMaxDelta) session.SessionMaxDelta = delta;
                if (delta < session.SessionMinDelta) session.SessionMinDelta = delta;
            }

            // --- Push rolling histories at END (so next bar sees this bar as prior) ---
            if (session != null)
            {
                SessionContext.Push(session.DeltaHistory, delta);
                SessionContext.Push(session.CvdHistory,   cvd);
            }

            return results.ToArray();
        }
    }
}
