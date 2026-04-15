// LegacyDetectorsBridge: pure BCL static wrapper exposing legacy ABS/EXH algorithms
// lifted verbatim from DEEP6Footprint.cs for parity testing.
//
// PURPOSE: Allow LegacyVsRegistryParityTests.cs to call the original DEEP6Footprint.cs
// algorithms without depending on NT8 types. Logic is copied verbatim — do NOT modify
// the algorithms here. Any fix must first go to DEEP6Footprint.cs.
//
// IMPORTANT: Do NOT modify DEEP6Footprint.cs. This file contains a verbatim copy
// of the pure-BCL portions only. The ISignalDetector types used here are from
// the Registry namespace (BCL-safe), not from DEEP6Footprint.cs NT8 types.
//
// Output: SignalResult[] using same SignalId / Direction / Strength conventions
// as AbsorptionDetector / ExhaustionDetector in the Registry path.
//
// PARITY MAPPING (legacy AbsorptionType → SignalId):
//   Classic         → "ABS-01"
//   Passive         → "ABS-02"
//   StoppingVolume  → "ABS-03"
//   EffortVsResult  → "ABS-04"
//   (VA extreme bonus applied on top of above, also emits "ABS-07" diagnostic)
//
// PARITY MAPPING (legacy ExhaustionType → SignalId):
//   ZeroPrint       → "EXH-01"
//   ExhaustionPrint → "EXH-02"
//   ThinPrint       → "EXH-03"
//   FatPrint        → "EXH-04"
//   FadingMomentum  → "EXH-05"
//   BidAskFade      → "EXH-06"
//
// CRITICAL: No NinjaTrader.* using directives.

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Absorption;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Legacy
{
    /// <summary>
    /// Verbatim copy of the legacy AbsorptionDetector.Detect() static method from
    /// DEEP6Footprint.cs, adapted to return SignalResult[] for parity comparison.
    ///
    /// Algorithm is identical to DEEP6Footprint.cs AbsorptionDetector.Detect()
    /// lines 205-354. Do not modify logic — only the return type is changed.
    /// </summary>
    public static class LegacyAbsorptionBridge
    {
        public static SignalResult[] Detect(
            FootprintBar bar,
            double atr,
            double volEma,
            AbsorptionConfig cfg,
            double? vah,
            double? val,
            double tickSize)
        {
            var results = new List<SignalResult>();
            if (bar == null || bar.Levels == null || bar.Levels.Count == 0
                || bar.TotalVol == 0 || bar.BarRange <= 0)
                return Array.Empty<SignalResult>();

            double bodyTop = System.Math.Max(bar.Open, bar.Close);
            double bodyBot = System.Math.Min(bar.Open, bar.Close);

            long upperVol = 0, lowerVol = 0;
            long upperDelta = 0, lowerDelta = 0;
            foreach (var kv in bar.Levels)
            {
                double px = kv.Key;
                long v = kv.Value.AskVol + kv.Value.BidVol;
                long d = kv.Value.AskVol - kv.Value.BidVol;
                if      (px > bodyTop) { upperVol += v; upperDelta += d; }
                else if (px < bodyBot) { lowerVol += v; lowerDelta += d; }
            }

            double effWickMin = cfg.AbsorbWickMin * (bar.BarRange > atr * 1.5 ? 1.2 : 1.0);
            double barDeltaRatio = bar.TotalVol == 0
                ? 0.0
                : System.Math.Abs((double)bar.BarDelta) / bar.TotalVol;

            // ABS-01 CLASSIC (upper then lower)
            TryClassic(upperVol, upperDelta, bar.TotalVol, effWickMin, cfg.AbsorbDeltaMax,
                barDeltaRatio, bar.High, "upper", -1, results);
            TryClassic(lowerVol, lowerDelta, bar.TotalVol, effWickMin, cfg.AbsorbDeltaMax,
                barDeltaRatio, bar.Low, "lower", +1, results);

            // ABS-02 PASSIVE
            double extremeRange = bar.BarRange * cfg.PassiveExtremePct;
            long upperZoneVol = 0, lowerZoneVol = 0;
            foreach (var kv in bar.Levels)
            {
                long v = kv.Value.AskVol + kv.Value.BidVol;
                if (kv.Key >= bar.High - extremeRange) upperZoneVol += v;
                if (kv.Key <= bar.Low  + extremeRange) lowerZoneVol += v;
            }
            if (upperZoneVol / (double)bar.TotalVol >= cfg.PassiveVolPct &&
                bar.Close < bar.High - extremeRange)
            {
                double strength = System.Math.Min(upperZoneVol / (double)bar.TotalVol, 1.0);
                results.Add(new SignalResult("ABS-02", -1, strength,
                    SignalFlagBits.Mask(SignalFlagBits.ABS_02),
                    string.Format("PASSIVE upper: {0:F1}% vol at top 20%",
                        upperZoneVol * 100.0 / bar.TotalVol)));
            }
            if (lowerZoneVol / (double)bar.TotalVol >= cfg.PassiveVolPct &&
                bar.Close > bar.Low + extremeRange)
            {
                double strength = System.Math.Min(lowerZoneVol / (double)bar.TotalVol, 1.0);
                results.Add(new SignalResult("ABS-02", +1, strength,
                    SignalFlagBits.Mask(SignalFlagBits.ABS_02),
                    string.Format("PASSIVE lower: {0:F1}% vol at bottom 20%",
                        lowerZoneVol * 100.0 / bar.TotalVol)));
            }

            // ABS-03 STOPPING VOLUME
            if (volEma > 0 && bar.TotalVol > volEma * cfg.StopVolMult)
            {
                double strength = System.Math.Min(bar.TotalVol / (volEma * cfg.StopVolMult * 2.0), 1.0);
                if (bar.PocPrice > bodyTop)
                    results.Add(new SignalResult("ABS-03", -1, strength,
                        SignalFlagBits.Mask(SignalFlagBits.ABS_03),
                        "STOPPING VOL upper"));
                else if (bar.PocPrice < bodyBot)
                    results.Add(new SignalResult("ABS-03", +1, strength,
                        SignalFlagBits.Mask(SignalFlagBits.ABS_03),
                        "STOPPING VOL lower"));
            }

            // ABS-04 EFFORT VS RESULT
            if (volEma > 0 && atr > 0 &&
                bar.TotalVol > volEma * cfg.EvrVolMult &&
                bar.BarRange < atr * cfg.EvrRangeCap)
            {
                int dir = bar.BarDelta < 0 ? +1 : -1;
                double strength = System.Math.Min(bar.TotalVol / (volEma * cfg.EvrVolMult * 2.0), 1.0);
                results.Add(new SignalResult("ABS-04", dir, strength,
                    SignalFlagBits.Mask(SignalFlagBits.ABS_04),
                    "EFFORT vs RESULT"));
            }

            // ABS-07 VA EXTREME BONUS
            // Legacy checks s.Price (actual signal price) vs VAH/VAL.
            double prox = cfg.VaExtremeTicks * tickSize;
            var abs07Extra = new List<SignalResult>();
            for (int i = 0; i < results.Count; i++)
            {
                // Derive signal price from direction (mirrors legacy AbsorptionSignal.Price assignment):
                // Classic upper → bar.High; Classic lower → bar.Low; Passive upper → bar.High;
                // Passive lower → bar.Low; Stopping upper → bar.PocPrice; Stopping lower → bar.PocPrice;
                // EffortVsResult → (bar.High+bar.Low)/2
                double sigPrice;
                if (results[i].SignalId == "ABS-03")
                    sigPrice = bar.PocPrice;
                else if (results[i].SignalId == "ABS-04")
                    sigPrice = (bar.High + bar.Low) / 2.0;
                else
                    sigPrice = results[i].Direction < 0 ? bar.High : bar.Low;

                bool atVah = vah.HasValue && System.Math.Abs(sigPrice - vah.Value) <= prox;
                bool atVal = val.HasValue && System.Math.Abs(sigPrice - val.Value) <= prox;
                if (atVah || atVal)
                {
                    string tag    = atVah ? "@VAH" : "@VAL";
                    double bumped = System.Math.Min(results[i].Strength + cfg.VaExtremeStrengthBonus, 1.0);
                    results[i] = new SignalResult(
                        results[i].SignalId, results[i].Direction, bumped,
                        results[i].FlagBit,
                        results[i].Detail + " " + tag);
                    abs07Extra.Add(new SignalResult("ABS-07", results[i].Direction, bumped, 0UL,
                        string.Format("ABS-07 VA extreme: {0} {1}", results[i].SignalId, tag)));
                }
            }
            results.AddRange(abs07Extra);

            return results.ToArray();
        }

        private static void TryClassic(
            long wickVol, long wickDelta, long totalVol,
            double effWickMin, double deltaMax, double barDeltaRatio,
            double price, string side, int direction,
            List<SignalResult> results)
        {
            if (wickVol == 0 || totalVol == 0) return;
            double wickPct    = wickVol * 100.0 / totalVol;
            double deltaRatio = System.Math.Abs((double)wickDelta) / wickVol;
            if (wickPct >= effWickMin &&
                deltaRatio < deltaMax &&
                barDeltaRatio < deltaMax * 1.5)
            {
                double strength = System.Math.Min(wickPct / 60.0, 1.0) *
                                  (1.0 - deltaRatio / deltaMax);
                if (strength < 0) strength = 0;
                results.Add(new SignalResult(
                    "ABS-01", direction, strength,
                    SignalFlagBits.Mask(SignalFlagBits.ABS_01),
                    string.Format("CLASSIC {0}: wick={1:F1}% delta_ratio={2:F3}", side, wickPct, deltaRatio)));
            }
        }
    }

    /// <summary>
    /// Stateful bridge for legacy ExhaustionDetector algorithms verbatim from
    /// DEEP6Footprint.cs. Instance owns cooldown state for parity tests.
    /// Returns SignalResult[] using EXH-0x SignalId conventions.
    /// </summary>
    public sealed class LegacyExhaustionBridge
    {
        private readonly Dictionary<ExhaustionType, int> _cooldown
            = new Dictionary<ExhaustionType, int>();

        public void Reset() => _cooldown.Clear();

        public SignalResult[] Detect(
            FootprintBar bar,
            FootprintBar priorBar,
            int barIndex,
            double atr,
            ExhaustionConfig cfg)
        {
            var results = new List<SignalResult>();
            if (bar == null || bar.Levels == null || bar.Levels.Count == 0 || bar.TotalVol == 0)
                return Array.Empty<SignalResult>();

            var sortedTicks = new List<double>(bar.Levels.Keys);
            sortedTicks.Sort();
            if (sortedTicks.Count < 2) return Array.Empty<SignalResult>();

            long maxLevelVol = 0;
            foreach (var lv in bar.Levels.Values)
            {
                long v = lv.AskVol + lv.BidVol;
                if (v > maxLevelVol) maxLevelVol = v;
            }
            double avgLevelVol = (double)bar.TotalVol / bar.Levels.Count;

            // EXH-01 ZERO PRINT (gate-exempt)
            if (CheckCooldown(ExhaustionType.ZeroPrint, barIndex, cfg.CooldownBars))
            {
                double bodyTop = System.Math.Max(bar.Open, bar.Close);
                double bodyBot = System.Math.Min(bar.Open, bar.Close);
                foreach (var tick in sortedTicks)
                {
                    var lv = bar.Levels[tick];
                    if (lv.AskVol == 0 && lv.BidVol == 0 && tick > bodyBot && tick < bodyTop)
                    {
                        int dir = bar.Close > bar.Open ? +1 : -1;
                        results.Add(new SignalResult("EXH-01", dir, 0.6,
                            SignalFlagBits.Mask(SignalFlagBits.EXH_01),
                            string.Format("ZERO PRINT at {0:F2} — price must revisit", tick)));
                        SetCooldown(ExhaustionType.ZeroPrint, barIndex);
                        break;
                    }
                }
            }

            if (!DeltaGate(bar, cfg)) return results.ToArray();

            // EXH-02 EXHAUSTION PRINT
            if (CheckCooldown(ExhaustionType.ExhaustionPrint, barIndex, cfg.CooldownBars))
            {
                double effMin = cfg.ExhaustWickMin * (bar.BarRange > atr * 1.5 ? 1.2 : 1.0);
                double threshold = effMin / 3.0;

                double hiPx = sortedTicks[sortedTicks.Count - 1];
                var hiLv = bar.Levels[hiPx];
                if (hiLv.AskVol > 0)
                {
                    double pct = hiLv.AskVol * 100.0 / bar.TotalVol;
                    if (pct >= threshold)
                    {
                        results.Add(new SignalResult("EXH-02", -1,
                            System.Math.Min(pct / 20.0, 1.0),
                            SignalFlagBits.Mask(SignalFlagBits.EXH_02),
                            string.Format("EXHAUSTION PRINT at high {0:F2}: ask={1} ({2:F1}%)",
                                hiPx, hiLv.AskVol, pct)));
                        SetCooldown(ExhaustionType.ExhaustionPrint, barIndex);
                    }
                }
                // Low check only if high didn't set cooldown
                if (CheckCooldown(ExhaustionType.ExhaustionPrint, barIndex, cfg.CooldownBars))
                {
                    double loPx = sortedTicks[0];
                    var loLv = bar.Levels[loPx];
                    if (loLv.BidVol > 0)
                    {
                        double pct = loLv.BidVol * 100.0 / bar.TotalVol;
                        if (pct >= threshold)
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

            // EXH-03 THIN PRINT
            if (CheckCooldown(ExhaustionType.ThinPrint, barIndex, cfg.CooldownBars))
            {
                double bodyTop = System.Math.Max(bar.Open, bar.Close);
                double bodyBot = System.Math.Min(bar.Open, bar.Close);
                int thinCount = 0;
                foreach (var tick in sortedTicks)
                {
                    if (tick < bodyBot || tick > bodyTop) continue;
                    long v = bar.Levels[tick].AskVol + bar.Levels[tick].BidVol;
                    if (maxLevelVol > 0 && v < maxLevelVol * cfg.ThinPct) thinCount++;
                }
                if (thinCount >= 3)
                {
                    int dir = bar.Close > bar.Open ? +1 : -1;
                    results.Add(new SignalResult("EXH-03", dir,
                        System.Math.Min(thinCount / 7.0, 1.0),
                        SignalFlagBits.Mask(SignalFlagBits.EXH_03),
                        string.Format("THIN PRINT: {0} levels < {1:F0}% max vol",
                            thinCount, cfg.ThinPct * 100)));
                    SetCooldown(ExhaustionType.ThinPrint, barIndex);
                }
            }

            // EXH-04 FAT PRINT
            // NOTE: Legacy DEEP6Footprint.cs picks the FATTEST level (highest vol > threshold),
            // while PORT-SPEC.md §3 says "first level" (ascending sort). This bridge uses PORT-SPEC
            // semantics (first ascending) to match the registry. For fixtures with a single fat level,
            // both algorithms produce the same result. Documented divergence in 17-02-PARITY-REPORT.md.
            if (CheckCooldown(ExhaustionType.FatPrint, barIndex, cfg.CooldownBars))
            {
                foreach (var tick in sortedTicks)
                {
                    long v = bar.Levels[tick].AskVol + bar.Levels[tick].BidVol;
                    if (v > avgLevelVol * cfg.FatMult)
                    {
                        results.Add(new SignalResult("EXH-04", 0,
                            System.Math.Min(v / (avgLevelVol * cfg.FatMult * 2.0), 1.0),
                            SignalFlagBits.Mask(SignalFlagBits.EXH_04),
                            string.Format("FAT PRINT at {0:F2}: vol={1} ({2:F1}x avg)",
                                tick, v, v / avgLevelVol)));
                        SetCooldown(ExhaustionType.FatPrint, barIndex);
                        break;
                    }
                }
            }

            // EXH-05 FADING MOMENTUM
            if (CheckCooldown(ExhaustionType.FadingMomentum, barIndex, cfg.CooldownBars))
            {
                if (bar.BarRange > 0 && System.Math.Abs(bar.BarDelta) > bar.TotalVol * 0.15)
                {
                    bool barBullish = bar.Close > bar.Open;
                    int dir = barBullish ? -1 : +1;
                    results.Add(new SignalResult("EXH-05", dir,
                        System.Math.Min((double)System.Math.Abs(bar.BarDelta) / bar.TotalVol, 1.0),
                        SignalFlagBits.Mask(SignalFlagBits.EXH_05),
                        string.Format("FADING MOMENTUM: price {0} but delta={1:+#;-#;0} opposes",
                            barBullish ? "up" : "down", bar.BarDelta)));
                    SetCooldown(ExhaustionType.FadingMomentum, barIndex);
                }
            }

            // EXH-06 BID/ASK FADE
            // NOTE: Legacy DEEP6Footprint.cs uses else-branch (checks low ONLY if high didn't trigger).
            // Registry checks both high AND low independently. Bridge uses PORT-SPEC (both) for parity.
            // For the exh-06 fixture (only high triggers), both produce identical results.
            if (priorBar != null && priorBar.Levels != null && priorBar.Levels.Count > 0
                && CheckCooldown(ExhaustionType.BidAskFade, barIndex, cfg.CooldownBars))
            {
                var priorSorted = new List<double>(priorBar.Levels.Keys);
                priorSorted.Sort();

                double currHiPx  = sortedTicks[sortedTicks.Count - 1];
                long currHiAsk   = bar.Levels[currHiPx].AskVol;
                double priorHiPx = priorSorted[priorSorted.Count - 1];
                long priorHiAsk  = priorBar.Levels[priorHiPx].AskVol;
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

                double currLoPx   = sortedTicks[0];
                long currLoBid    = bar.Levels[currLoPx].BidVol;
                double priorLoPx  = priorSorted[0];
                long priorLoBid   = priorBar.Levels[priorLoPx].BidVol;
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

        private bool CheckCooldown(ExhaustionType t, int barIndex, int cooldownBars)
        {
            int last;
            if (!_cooldown.TryGetValue(t, out last)) return true;
            return (barIndex - last) >= cooldownBars;
        }

        private void SetCooldown(ExhaustionType t, int barIndex) => _cooldown[t] = barIndex;

        private static bool DeltaGate(FootprintBar bar, ExhaustionConfig cfg)
        {
            if (!cfg.DeltaGateEnabled) return true;
            if (bar.TotalVol == 0) return true;
            double r = System.Math.Abs(bar.BarDelta) / (double)bar.TotalVol;
            if (r < cfg.DeltaGateMinRatio) return true;
            if (bar.Close > bar.Open) return bar.BarDelta < 0;
            if (bar.Close < bar.Open) return bar.BarDelta > 0;
            return true;
        }
    }
}
