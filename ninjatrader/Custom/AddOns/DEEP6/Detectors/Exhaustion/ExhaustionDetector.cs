// ExhaustionDetector: ISignalDetector implementation for EXH-01..06.
//
// Python reference: deep6/engines/exhaustion.py detect_exhaustion() lines 1-317
// Port spec: PORT-SPEC.md §3 (authoritative algorithm)
// Signal IDs: EXH-01 (ZeroPrint), EXH-02 (ExhaustionPrint), EXH-03 (ThinPrint),
//             EXH-04 (FatPrint), EXH-05 (FadingMomentum), EXH-06 (BidAskFade)
//
// Cooldown state: Dictionary<ExhaustionType, int> instance field — cleared at Reset().
// EXH-01 (ZeroPrint) is delta-gate exempt per PORT-SPEC.md §3 line 275.
//
// CRITICAL: No NinjaTrader.* using directives.

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion
{
    /// <summary>
    /// Configuration for ExhaustionDetector. Mirrors Python ExhaustionConfig.
    /// Python reference: deep6/engines/signal_config.py ExhaustionConfig lines 48-73
    /// PORT-SPEC.md §3.Config
    /// </summary>
    public sealed class ExhaustionConfig
    {
        /// <summary>Max vol fraction of max-level vol that qualifies as a "thin" level.</summary>
        public double ThinPct             = 0.05;
        /// <summary>Vol multiplier of avg level vol for fat print detection.</summary>
        public double FatMult             = 2.0;
        /// <summary>Wick vol % threshold for exhaustion print at bar extreme.</summary>
        public double ExhaustWickMin      = 35.0;
        /// <summary>Fade ratio — current extreme vol must be below this fraction of prior bar.</summary>
        public double FadeThreshold       = 0.60;
        /// <summary>Bars that must elapse before the same exhaustion sub-type can re-fire.</summary>
        public int    CooldownBars        = 5;
        /// <summary>Enable/disable the universal delta gate for variants EXH-02..06.</summary>
        public bool   DeltaGateEnabled    = true;
        /// <summary>Minimum delta ratio below which gate does not block (noise floor).</summary>
        public double DeltaGateMinRatio   = 0.10;
    }

    /// <summary>Exhaustion sub-type enum matching Python ExhaustionType.</summary>
    public enum ExhaustionType
    {
        ZeroPrint,
        ExhaustionPrint,
        ThinPrint,
        FatPrint,
        FadingMomentum,
        BidAskFade
    }

    /// <summary>
    /// Legacy exhaustion signal struct — returned by Detect() for backwards compat
    /// with DEEP6Strategy / DEEP6Footprint legacy code path (UseNewRegistry = false).
    /// </summary>
    public sealed class ExhaustionSignal
    {
        public ExhaustionType Kind;
        public int    Direction;
        public double Price;
        public double Strength;
        public string Detail;
    }

    /// <summary>
    /// Detects EXH-01..06. Instance owns cooldown state cleared at Reset().
    ///
    /// EXH-01 (ZeroPrint) is exempt from the universal delta gate (structural, not delta-dependent).
    /// EXH-02..06 run only if the delta gate passes.
    ///
    /// Python reference: deep6/engines/exhaustion.py
    /// Port spec: PORT-SPEC.md §3
    /// </summary>
    public sealed class ExhaustionDetector : ISignalDetector
    {
        private readonly ExhaustionConfig _cfg;

        /// <summary>
        /// Cooldown state: maps each ExhaustionType to the barIndex when it last fired.
        /// Cleared at Reset() (session boundary).
        /// Python reference: exhaustion.py _cooldown module-level dict → per-instance here.
        /// </summary>
        private readonly Dictionary<ExhaustionType, int> _cooldown
            = new Dictionary<ExhaustionType, int>();

        public ExhaustionDetector() : this(new ExhaustionConfig()) { }

        public ExhaustionDetector(ExhaustionConfig cfg)
        {
            _cfg = cfg ?? new ExhaustionConfig();
        }

        /// <inheritdoc/>
        public string Name => "Exhaustion";

        /// <inheritdoc/>
        public void Reset()
        {
            _cooldown.Clear();
        }

        /// <summary>Legacy alias used by DEEP6Strategy legacy path.</summary>
        public void ResetCooldowns() => Reset();

        /// <inheritdoc/>
        /// <remarks>
        /// ISignalDetector implementation — returns SignalResult[] with EXH-01..EXH-06 ids.
        /// Delegates to DetectCore(); legacy Detect() wraps this for backwards compat.
        /// </remarks>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            FootprintBar priorBar = session?.PriorBar;
            int  barIndex = session != null ? session.BarsSinceOpen : (bar != null ? bar.BarIndex : 0);
            double atr    = session != null && session.Atr20 > 0 ? session.Atr20 : 1.0;
            return DetectCore(bar, priorBar, barIndex, atr, _cfg);
        }

        /// <summary>
        /// Core detection returning SignalResult[] with EXH-01..EXH-06 signal IDs.
        /// Used by OnBar() (registry path) and bridged by Detect() (legacy path).
        /// </summary>
        private SignalResult[] DetectCore(
            FootprintBar bar,
            FootprintBar priorBar,
            int barIndex,
            double atr,
            ExhaustionConfig cfg)
        {
            if (bar == null || bar.Levels == null || bar.Levels.Count == 0 || bar.TotalVol == 0)
                return Array.Empty<SignalResult>();

            var sorted = new List<double>(bar.Levels.Keys);
            sorted.Sort();
            if (sorted.Count < 2) return Array.Empty<SignalResult>();

            long maxLevelVol = 0;
            foreach (var lv in bar.Levels.Values)
            {
                long v = lv.AskVol + lv.BidVol;
                if (v > maxLevelVol) maxLevelVol = v;
            }
            double avgLevelVol = bar.Levels.Count > 0 ? (double)bar.TotalVol / bar.Levels.Count : 1.0;
            double bodyTop     = System.Math.Max(bar.Open, bar.Close);
            double bodyBot     = System.Math.Min(bar.Open, bar.Close);

            var results = new List<SignalResult>();

            // --- EXH-01: ZERO PRINT (gate-exempt) ---
            // Python reference: exhaustion.py lines 150-166
            if (CheckCooldown(ExhaustionType.ZeroPrint, barIndex, cfg.CooldownBars))
            {
                foreach (double px in sorted)
                {
                    var lv = bar.Levels[px];
                    if (lv.AskVol == 0 && lv.BidVol == 0 && bodyBot < px && px < bodyTop)
                    {
                        int dir = bar.Close > bar.Open ? +1 : -1;
                        results.Add(new SignalResult("EXH-01", dir, 0.6,
                            SignalFlagBits.Mask(SignalFlagBits.EXH_01),
                            string.Format("ZERO PRINT at {0:F2} — price must revisit", px)));
                        SetCooldown(ExhaustionType.ZeroPrint, barIndex);
                        break; // One zero print per bar
                    }
                }
            }

            // --- Universal delta gate (EXH-07) — runs after EXH-01, before EXH-02..06 ---
            // Python reference: exhaustion.py lines 168-172
            if (!DeltaGate(bar, cfg)) return results.ToArray();

            // --- EXH-02: EXHAUSTION PRINT ---
            // Python reference: exhaustion.py lines 174-208
            if (CheckCooldown(ExhaustionType.ExhaustionPrint, barIndex, cfg.CooldownBars))
            {
                double effMin = cfg.ExhaustWickMin * (bar.BarRange > atr * 1.5 ? 1.2 : 1.0);
                double hiPx   = sorted[sorted.Count - 1];
                var    hiLv   = bar.Levels[hiPx];
                if (hiLv.AskVol > 0)
                {
                    double pct = (double)hiLv.AskVol / bar.TotalVol * 100;
                    if (pct >= effMin / 3.0)
                    {
                        results.Add(new SignalResult("EXH-02", -1,
                            System.Math.Min(pct / 20.0, 1.0),
                            SignalFlagBits.Mask(SignalFlagBits.EXH_02),
                            string.Format("EXHAUSTION PRINT at high {0:F2}: ask={1} ({2:F1}%)",
                                hiPx, hiLv.AskVol, pct)));
                        SetCooldown(ExhaustionType.ExhaustionPrint, barIndex);
                    }
                }
                // Re-check cooldown: if high just fired, low must not fire on same bar.
                // Matches legacy DEEP6Footprint.cs double-cooldown pattern — one EXH-02 per bar.
                if (CheckCooldown(ExhaustionType.ExhaustionPrint, barIndex, cfg.CooldownBars))
                {
                    double loPx = sorted[0];
                    var    loLv = bar.Levels[loPx];
                    if (loLv.BidVol > 0)
                    {
                        double pct = (double)loLv.BidVol / bar.TotalVol * 100;
                        if (pct >= cfg.ExhaustWickMin / 3.0)
                        {
                            results.Add(new SignalResult("EXH-02", +1,
                                System.Math.Min(pct / 20.0, 1.0),
                                SignalFlagBits.Mask(SignalFlagBits.EXH_02),
                                string.Format("EXHAUSTION PRINT at low {0:F2}: bid={1} ({2:F1}%)",
                                    loPx, loLv.BidVol, pct)));
                            SetCooldown(ExhaustionType.ExhaustionPrint, barIndex);
                        }
                    }
                }
            }

            // --- EXH-03: THIN PRINT ---
            // Python reference: exhaustion.py lines 210-231
            if (CheckCooldown(ExhaustionType.ThinPrint, barIndex, cfg.CooldownBars))
            {
                int thinCount = 0;
                foreach (double px in sorted)
                {
                    if (px < bodyBot || px > bodyTop) continue;
                    long v = bar.Levels[px].AskVol + bar.Levels[px].BidVol;
                    if (maxLevelVol > 0 && v < maxLevelVol * cfg.ThinPct) thinCount++;
                }
                if (thinCount >= 3)
                {
                    int dir = bar.Close > bar.Open ? +1 : -1;
                    results.Add(new SignalResult("EXH-03", dir,
                        System.Math.Min(thinCount / 7.0, 1.0),
                        SignalFlagBits.Mask(SignalFlagBits.EXH_03),
                        string.Format("THIN PRINT: {0} levels < {1:F0}% max vol — fast move",
                            thinCount, cfg.ThinPct * 100)));
                    SetCooldown(ExhaustionType.ThinPrint, barIndex);
                }
            }

            // --- EXH-04: FAT PRINT ---
            // Python reference: exhaustion.py lines 233-250
            if (CheckCooldown(ExhaustionType.FatPrint, barIndex, cfg.CooldownBars))
            {
                foreach (double px in sorted)
                {
                    long v = bar.Levels[px].AskVol + bar.Levels[px].BidVol;
                    if (v > avgLevelVol * cfg.FatMult)
                    {
                        results.Add(new SignalResult("EXH-04", 0,
                            System.Math.Min(v / (avgLevelVol * cfg.FatMult * 2.0), 1.0),
                            SignalFlagBits.Mask(SignalFlagBits.EXH_04),
                            string.Format("FAT PRINT at {0:F2}: vol={1} ({2:F1}x avg) — strong acceptance",
                                px, v, v / avgLevelVol)));
                        SetCooldown(ExhaustionType.FatPrint, barIndex);
                        break; // One fat print per bar (the fattest)
                    }
                }
            }

            // --- EXH-05: FADING MOMENTUM ---
            // Python reference: exhaustion.py lines 252-272
            if (CheckCooldown(ExhaustionType.FadingMomentum, barIndex, cfg.CooldownBars))
            {
                if (bar.BarRange > 0 && System.Math.Abs(bar.BarDelta) > bar.TotalVol * 0.15)
                {
                    bool barBullish = bar.Close > bar.Open;
                    int  dir        = barBullish ? -1 : +1;
                    results.Add(new SignalResult("EXH-05", dir,
                        System.Math.Min((double)System.Math.Abs(bar.BarDelta) / bar.TotalVol, 1.0),
                        SignalFlagBits.Mask(SignalFlagBits.EXH_05),
                        string.Format("FADING MOMENTUM: price {0} but delta={1:+#;-#;0} opposes — aggression fading",
                            barBullish ? "up" : "down", bar.BarDelta)));
                    SetCooldown(ExhaustionType.FadingMomentum, barIndex);
                }
            }

            // --- EXH-06: BID/ASK FADE ---
            // Python reference: exhaustion.py lines 274-314
            if (priorBar != null && priorBar.Levels != null && priorBar.Levels.Count > 0
                && CheckCooldown(ExhaustionType.BidAskFade, barIndex, cfg.CooldownBars))
            {
                var priorSorted = new List<double>(priorBar.Levels.Keys);
                priorSorted.Sort();

                // Compare ask vol at current high vs prior bar high
                double currHiPx   = sorted[sorted.Count - 1];
                long   currHiAsk  = bar.Levels[currHiPx].AskVol;
                double priorHiPx  = priorSorted[priorSorted.Count - 1];
                long   priorHiAsk = priorBar.Levels[priorHiPx].AskVol;
                if (priorHiAsk > 0 && currHiAsk < priorHiAsk * cfg.FadeThreshold)
                {
                    double str = 1.0 - (priorHiAsk > 0 ? (double)currHiAsk / priorHiAsk : 0);
                    results.Add(new SignalResult("EXH-06", -1, str,
                        SignalFlagBits.Mask(SignalFlagBits.EXH_06),
                        string.Format("ASK FADE at high: curr={0} vs prior={1} ({2:F0}% < {3:F0}%)",
                            currHiAsk, priorHiAsk,
                            (double)currHiAsk / priorHiAsk * 100, cfg.FadeThreshold * 100)));
                    SetCooldown(ExhaustionType.BidAskFade, barIndex);
                }

                // Compare bid vol at current low vs prior bar low
                double currLoPx  = sorted[0];
                long   currLoBid = bar.Levels[currLoPx].BidVol;
                double priorLoPx = priorSorted[0];
                long   priorLoBid = priorBar.Levels[priorLoPx].BidVol;
                if (priorLoBid > 0 && currLoBid < priorLoBid * cfg.FadeThreshold)
                {
                    double str = 1.0 - (priorLoBid > 0 ? (double)currLoBid / priorLoBid : 0);
                    results.Add(new SignalResult("EXH-06", +1, str,
                        SignalFlagBits.Mask(SignalFlagBits.EXH_06),
                        string.Format("BID FADE at low: curr={0} vs prior={1} ({2:F0}% < {3:F0}%)",
                            currLoBid, priorLoBid,
                            (double)currLoBid / priorLoBid * 100, cfg.FadeThreshold * 100)));
                    SetCooldown(ExhaustionType.BidAskFade, barIndex);
                }
            }

            return results.ToArray();
        }

        /// <summary>
        /// Legacy Detect() entry point — compatible with DEEP6Strategy / DEEP6Footprint.
        /// Returns List&lt;ExhaustionSignal&gt; for the legacy code path (UseNewRegistry = false).
        /// Bridges to DetectCore() and converts SignalResult → ExhaustionSignal.
        /// </summary>
        public List<ExhaustionSignal> Detect(
            FootprintBar bar,
            FootprintBar priorBar,
            int barIndex,
            double atr,
            ExhaustionConfig cfg)
        {
            var coreResults = DetectCore(bar, priorBar, barIndex, atr, cfg ?? _cfg);
            var legacy = new List<ExhaustionSignal>(coreResults.Length);
            foreach (var r in coreResults)
            {
                legacy.Add(new ExhaustionSignal
                {
                    Kind      = SignalIdToType(r.SignalId),
                    Direction = r.Direction,
                    Price     = bar != null ? (r.Direction < 0 ? bar.High : (r.Direction > 0 ? bar.Low : bar.Close)) : 0,
                    Strength  = r.Strength,
                    Detail    = r.Detail
                });
            }
            return legacy;
        }

        private static ExhaustionType SignalIdToType(string signalId)
        {
            switch (signalId)
            {
                case "EXH-01": return ExhaustionType.ZeroPrint;
                case "EXH-02": return ExhaustionType.ExhaustionPrint;
                case "EXH-03": return ExhaustionType.ThinPrint;
                case "EXH-04": return ExhaustionType.FatPrint;
                case "EXH-05": return ExhaustionType.FadingMomentum;
                case "EXH-06": return ExhaustionType.BidAskFade;
                default:       return ExhaustionType.ZeroPrint;
            }
        }

        // --- Cooldown helpers ---

        private bool CheckCooldown(ExhaustionType t, int barIndex, int cooldownBars)
        {
            int last;
            if (!_cooldown.TryGetValue(t, out last)) return true;
            return (barIndex - last) >= cooldownBars;
        }

        private void SetCooldown(ExhaustionType t, int barIndex)
        {
            _cooldown[t] = barIndex;
        }

        // --- Delta trajectory gate (EXH-07) ---
        // Python reference: exhaustion.py _delta_trajectory_gate() lines 70-107
        // PORT-SPEC.md §3 "Delta trajectory gate"
        private static bool DeltaGate(FootprintBar bar, ExhaustionConfig cfg)
        {
            if (!cfg.DeltaGateEnabled) return true;
            if (bar.TotalVol == 0) return true;
            double r = System.Math.Abs(bar.BarDelta) / (double)bar.TotalVol;
            if (r < cfg.DeltaGateMinRatio) return true;   // too small → don't block
            if (bar.Close > bar.Open) return bar.BarDelta < 0;   // bullish bar: buyers must be fading
            if (bar.Close < bar.Open) return bar.BarDelta > 0;   // bearish bar: sellers must be fading
            return true;                                          // doji: allow
        }
    }
}
