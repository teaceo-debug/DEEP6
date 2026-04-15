// AbsorptionDetector: ISignalDetector implementation for ABS-01..04 + ABS-07.
//
// Python reference: deep6/engines/absorption.py detect_absorption() lines 1-244
// Port spec: PORT-SPEC.md §2 (authoritative algorithm)
// Signal IDs: ABS-01 (Classic), ABS-02 (Passive), ABS-03 (Stopping Vol), ABS-04 (Effort vs Result)
// ABS-07: VA extreme bonus applied post-hoc — mutates Detail + bumps Strength on existing results.
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Absorption
{
    /// <summary>
    /// Configuration for AbsorptionDetector. Mirrors Python AbsorptionConfig.
    /// Python reference: deep6/engines/signal_config.py AbsorptionConfig lines 16-44
    /// PORT-SPEC.md §2.Config
    /// </summary>
    public sealed class AbsorptionConfig
    {
        /// <summary>Wick vol % of total bar volume (minimum to consider wick "heavy").</summary>
        public double AbsorbWickMin       = 30.0;
        /// <summary>Max |delta|/wick_vol ratio — high ratio = directional, not absorbed.</summary>
        public double AbsorbDeltaMax      = 0.12;
        /// <summary>Fraction of bar range defining the "extreme zone" for passive absorption.</summary>
        public double PassiveExtremePct   = 0.20;
        /// <summary>Min fraction of total vol that must be in the extreme zone.</summary>
        public double PassiveVolPct       = 0.60;
        /// <summary>Vol multiplier of VolEma required for stopping volume.</summary>
        public double StopVolMult         = 2.0;
        /// <summary>Vol multiplier of VolEma required for effort-vs-result.</summary>
        public double EvrVolMult          = 1.5;
        /// <summary>Max bar range as fraction of ATR for effort-vs-result.</summary>
        public double EvrRangeCap         = 0.30;
        /// <summary>Tick proximity to VAH/VAL for ABS-07 bonus to apply.</summary>
        public double VaExtremeTicks      = 2.0;
        /// <summary>Strength bonus added when signal is at VA extreme.</summary>
        public double VaExtremeStrengthBonus = 0.15;
    }

    /// <summary>
    /// Detects ABS-01 (Classic), ABS-02 (Passive), ABS-03 (Stopping Volume),
    /// ABS-04 (Effort vs Result), and applies ABS-07 (VA Extreme bonus).
    ///
    /// Implements ISignalDetector; stateless between bars (no rolling state for absorption).
    /// Python reference: deep6/engines/absorption.py
    /// Port spec: PORT-SPEC.md §2
    /// </summary>
    public sealed class AbsorptionDetector : ISignalDetector
    {
        private readonly AbsorptionConfig _cfg;

        public AbsorptionDetector() : this(new AbsorptionConfig()) { }

        public AbsorptionDetector(AbsorptionConfig cfg)
        {
            _cfg = cfg ?? new AbsorptionConfig();
        }

        /// <inheritdoc/>
        public string Name => "Absorption";

        /// <inheritdoc/>
        public void Reset()
        {
            // Absorption has no rolling state — nothing to reset.
            // Called at RTH open boundary by DetectorRegistry.ResetAll().
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || bar.Levels == null || bar.Levels.Count == 0
                || bar.TotalVol == 0 || bar.BarRange == 0)
                return Array.Empty<SignalResult>();

            double atr    = session != null ? session.Atr20    : 1.0;
            double volEma = session != null ? session.VolEma20 : (double)bar.TotalVol;
            double? vah   = session?.Vah;
            double? val   = session?.Val;
            double tickSz = session != null && session.TickSize > 0 ? session.TickSize : 0.25;

            if (atr <= 0) atr = 1.0;
            if (volEma <= 0) volEma = bar.TotalVol;

            var results = new List<SignalResult>();

            double bodyTop = System.Math.Max(bar.Open, bar.Close);
            double bodyBot = System.Math.Min(bar.Open, bar.Close);

            long upperVol = 0, upperDelta = 0;
            long lowerVol = 0, lowerDelta = 0;

            foreach (var kv in bar.Levels)
            {
                double px = kv.Key;
                long v  = kv.Value.AskVol + kv.Value.BidVol;
                long d  = kv.Value.AskVol - kv.Value.BidVol;
                if      (px > bodyTop) { upperVol += v; upperDelta += d; }
                else if (px < bodyBot) { lowerVol += v; lowerDelta += d; }
            }

            double effWickMin    = _cfg.AbsorbWickMin * (bar.BarRange > atr * 1.5 ? 1.2 : 1.0);
            double barDeltaRatio = bar.TotalVol == 0 ? 0 : (double)System.Math.Abs(bar.BarDelta) / bar.TotalVol;

            // --- ABS-01: CLASSIC (upper wick then lower wick) ---
            TryClassic(upperVol, upperDelta, bar.TotalVol, effWickMin, _cfg.AbsorbDeltaMax,
                barDeltaRatio, bar.High, "upper", -1, results);
            TryClassic(lowerVol, lowerDelta, bar.TotalVol, effWickMin, _cfg.AbsorbDeltaMax,
                barDeltaRatio, bar.Low, "lower", +1, results);

            // --- ABS-02: PASSIVE ---
            double extremeRange    = bar.BarRange * _cfg.PassiveExtremePct;
            long   upperZoneVol    = 0, lowerZoneVol = 0;
            foreach (var kv in bar.Levels)
            {
                long v = kv.Value.AskVol + kv.Value.BidVol;
                if (kv.Key >= bar.High - extremeRange) upperZoneVol += v;
                if (kv.Key <= bar.Low  + extremeRange) lowerZoneVol += v;
            }
            if (upperZoneVol / (double)bar.TotalVol >= _cfg.PassiveVolPct
                && bar.Close < bar.High - extremeRange)
            {
                double str = System.Math.Min(upperZoneVol / (double)bar.TotalVol, 1.0);
                results.Add(new SignalResult("ABS-02", -1, str,
                    SignalFlagBits.Mask(SignalFlagBits.ABS_02),
                    string.Format("PASSIVE upper: {0:F1}% vol at top 20%",
                        upperZoneVol * 100.0 / bar.TotalVol)));
            }
            if (lowerZoneVol / (double)bar.TotalVol >= _cfg.PassiveVolPct
                && bar.Close > bar.Low + extremeRange)
            {
                double str = System.Math.Min(lowerZoneVol / (double)bar.TotalVol, 1.0);
                results.Add(new SignalResult("ABS-02", +1, str,
                    SignalFlagBits.Mask(SignalFlagBits.ABS_02),
                    string.Format("PASSIVE lower: {0:F1}% vol at bottom 20%",
                        lowerZoneVol * 100.0 / bar.TotalVol)));
            }

            // --- ABS-03: STOPPING VOLUME ---
            if (bar.TotalVol > volEma * _cfg.StopVolMult)
            {
                double str = System.Math.Min(bar.TotalVol / (volEma * _cfg.StopVolMult * 2.0), 1.0);
                if (bar.PocPrice > bodyTop)
                    results.Add(new SignalResult("ABS-03", -1, str,
                        SignalFlagBits.Mask(SignalFlagBits.ABS_03),
                        string.Format("STOPPING VOL upper: POC={0:F2} vol={1} ({2:F1}x avg)",
                            bar.PocPrice, bar.TotalVol, bar.TotalVol / volEma)));
                else if (bar.PocPrice < bodyBot)
                    results.Add(new SignalResult("ABS-03", +1, str,
                        SignalFlagBits.Mask(SignalFlagBits.ABS_03),
                        string.Format("STOPPING VOL lower: POC={0:F2} vol={1} ({2:F1}x avg)",
                            bar.PocPrice, bar.TotalVol, bar.TotalVol / volEma)));
            }

            // --- ABS-04: EFFORT VS RESULT ---
            if (bar.TotalVol > volEma * _cfg.EvrVolMult
                && atr > 0 && bar.BarRange < atr * _cfg.EvrRangeCap)
            {
                int    dir = bar.BarDelta < 0 ? +1 : -1;
                double str = System.Math.Min(bar.TotalVol / (volEma * _cfg.EvrVolMult * 2.0), 1.0);
                double dr  = bar.TotalVol == 0 ? 0 : System.Math.Abs(bar.BarDelta) / (double)bar.TotalVol;
                results.Add(new SignalResult("ABS-04", dir, str,
                    SignalFlagBits.Mask(SignalFlagBits.ABS_04),
                    string.Format("EFFORT vs RESULT: vol={0} ({1:F1}x avg) range={2:F2} ({3:F0}% ATR)",
                        bar.TotalVol, bar.TotalVol / volEma, bar.BarRange, bar.BarRange / atr * 100)));
            }

            // --- ABS-07: VA EXTREME BONUS (post-hoc on all results) ---
            // Mutates Detail and bumps Strength when signal is within VaExtremeTicks of VAH/VAL.
            // Emits a separate diagnostic SignalResult (FlagBit=0) for each affected signal.
            // Python reference: deep6/engines/absorption.py lines 226-243
            if ((vah.HasValue || val.HasValue) && results.Count > 0)
            {
                double prox        = _cfg.VaExtremeTicks * tickSz;
                var    abs07Extra  = new List<SignalResult>();
                for (int i = 0; i < results.Count; i++)
                {
                    // Extract signal price from Detail — use bar.High or bar.Low heuristic
                    // based on direction (ABS-07 bonus checks signal.Price per Python algo).
                    double sigPrice = results[i].Direction < 0 ? bar.High : bar.Low;
                    // For ABS-04 (body) use midpoint
                    if (results[i].SignalId == "ABS-04") sigPrice = (bar.High + bar.Low) / 2.0;

                    bool atVah = vah.HasValue && System.Math.Abs(sigPrice - vah.Value) <= prox;
                    bool atVal = val.HasValue && System.Math.Abs(sigPrice - val.Value) <= prox;
                    if (atVah || atVal)
                    {
                        string tag     = atVah ? "@VAH" : "@VAL";
                        double bumped  = System.Math.Min(results[i].Strength + _cfg.VaExtremeStrengthBonus, 1.0);
                        results[i]     = new SignalResult(
                            results[i].SignalId, results[i].Direction, bumped,
                            results[i].FlagBit,
                            results[i].Detail + " " + tag);

                        // Emit ABS-07 diagnostic (FlagBit=0 per plan spec — no dedicated bit)
                        abs07Extra.Add(new SignalResult("ABS-07", results[i].Direction, bumped, 0UL,
                            string.Format("ABS-07 VA extreme: {0} {1}", results[i].SignalId, tag)));
                    }
                }
                results.AddRange(abs07Extra);
            }

            return results.ToArray();
        }

        // --- Private helpers ---

        private static void TryClassic(
            long wickVol, long wickDelta, long totalVol,
            double effWickMin, double deltaMax, double barDeltaRatio,
            double price, string side, int direction,
            List<SignalResult> results)
        {
            if (wickVol == 0 || totalVol == 0) return;
            double wickPct    = wickVol * 100.0 / totalVol;
            double deltaRatio = System.Math.Abs(wickDelta) / (double)wickVol;
            if (wickPct >= effWickMin
                && deltaRatio < deltaMax
                && barDeltaRatio < deltaMax * 1.5)
            {
                double strength = System.Math.Min(wickPct / 60.0, 1.0) * (1.0 - deltaRatio / deltaMax);
                results.Add(new SignalResult(
                    "ABS-01", direction, System.Math.Max(0, strength),
                    SignalFlagBits.Mask(SignalFlagBits.ABS_01),
                    string.Format("CLASSIC {0}: wick={1:F1}% delta_ratio={2:F3}",
                        side, wickPct, deltaRatio)));
            }
        }
    }
}
