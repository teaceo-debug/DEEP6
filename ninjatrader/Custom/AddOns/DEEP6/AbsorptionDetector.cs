// DEEP6 Footprint — Absorption Detector
// Port of deep6/engines/absorption.py (lines 1-244) for NinjaTrader 8.
// Variants: ABS-01 CLASSIC, ABS-02 PASSIVE, ABS-03 STOPPING_VOLUME, ABS-04 EFFORT_VS_RESULT.
// ABS-07 VAH/VAL proximity bonus applied post-generation.

using System;
using System.Collections.Generic;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6
{
    public enum AbsorptionType
    {
        Classic,
        Passive,
        StoppingVolume,
        EffortVsResult,
    }

    public sealed class AbsorptionSignal
    {
        public AbsorptionType Kind;
        public int Direction;       // +1 bullish, -1 bearish
        public double Price;
        public string Wick;          // "upper" | "lower" | "body"
        public double Strength;      // 0..1
        public double WickPct;
        public double DeltaRatio;
        public string Detail;
        public bool AtVaExtreme;
    }

    public sealed class AbsorptionConfig
    {
        public double AbsorbWickMin          = 30.0;
        public double AbsorbDeltaMax         = 0.12;
        public double PassiveExtremePct      = 0.20;
        public double PassiveVolPct          = 0.60;
        public double StopVolMult            = 2.0;
        public double EvrVolMult             = 1.5;
        public double EvrRangeCap            = 0.30;
        public double VaExtremeTicks         = 2.0;
        public double VaExtremeStrengthBonus = 0.15;
    }

    public static class AbsorptionDetector
    {
        public static List<AbsorptionSignal> Detect(
            FootprintBar bar,
            double atr,
            double volEma,
            AbsorptionConfig cfg,
            double? vah,
            double? val,
            double tickSize)
        {
            var sigs = new List<AbsorptionSignal>();
            if (bar == null || bar.Levels.Count == 0 || bar.TotalVol == 0 || bar.BarRange <= 0)
                return sigs;

            double bodyTop = Math.Max(bar.Open, bar.Close);
            double bodyBot = Math.Min(bar.Open, bar.Close);

            long upperVol = 0, lowerVol = 0, bodyVol = 0;
            long upperDelta = 0, lowerDelta = 0;
            foreach (var kv in bar.Levels)
            {
                double px = kv.Key;
                long v = kv.Value.AskVol + kv.Value.BidVol;
                long d = kv.Value.AskVol - kv.Value.BidVol;
                if (px > bodyTop) { upperVol += v; upperDelta += d; }
                else if (px < bodyBot) { lowerVol += v; lowerDelta += d; }
                else { bodyVol += v; }
            }

            double effWickMin = cfg.AbsorbWickMin * (bar.BarRange > atr * 1.5 ? 1.2 : 1.0);
            double barDeltaRatio = bar.TotalVol == 0
                ? 0.0
                : Math.Abs((double)bar.BarDelta) / bar.TotalVol;

            // ABS-01 CLASSIC
            TryClassic(upperVol, upperDelta, bar.TotalVol, effWickMin, cfg.AbsorbDeltaMax,
                barDeltaRatio, bar.High, "upper", -1, sigs);
            TryClassic(lowerVol, lowerDelta, bar.TotalVol, effWickMin, cfg.AbsorbDeltaMax,
                barDeltaRatio, bar.Low, "lower", +1, sigs);

            // ABS-02 PASSIVE
            double extremeRange = bar.BarRange * cfg.PassiveExtremePct;
            long upperZoneVol = 0, lowerZoneVol = 0;
            foreach (var kv in bar.Levels)
            {
                long v = kv.Value.AskVol + kv.Value.BidVol;
                if (kv.Key >= bar.High - extremeRange) upperZoneVol += v;
                if (kv.Key <= bar.Low + extremeRange) lowerZoneVol += v;
            }
            if (upperZoneVol / (double)bar.TotalVol >= cfg.PassiveVolPct &&
                bar.Close < bar.High - extremeRange)
            {
                double strength = Math.Min(upperZoneVol / (double)bar.TotalVol, 1.0);
                sigs.Add(new AbsorptionSignal
                {
                    Kind = AbsorptionType.Passive,
                    Direction = -1,
                    Price = bar.High,
                    Wick = "upper",
                    Strength = strength,
                    WickPct = upperZoneVol * 100.0 / bar.TotalVol,
                    DeltaRatio = 0,
                    Detail = "PASSIVE upper — heavy vol at top, close held below",
                });
            }
            if (lowerZoneVol / (double)bar.TotalVol >= cfg.PassiveVolPct &&
                bar.Close > bar.Low + extremeRange)
            {
                double strength = Math.Min(lowerZoneVol / (double)bar.TotalVol, 1.0);
                sigs.Add(new AbsorptionSignal
                {
                    Kind = AbsorptionType.Passive,
                    Direction = +1,
                    Price = bar.Low,
                    Wick = "lower",
                    Strength = strength,
                    WickPct = lowerZoneVol * 100.0 / bar.TotalVol,
                    DeltaRatio = 0,
                    Detail = "PASSIVE lower — heavy vol at bottom, close held above",
                });
            }

            // ABS-03 STOPPING VOLUME
            if (volEma > 0 && bar.TotalVol > volEma * cfg.StopVolMult)
            {
                double strength = Math.Min(bar.TotalVol / (volEma * cfg.StopVolMult * 2.0), 1.0);
                if (bar.PocPrice > bodyTop)
                {
                    sigs.Add(new AbsorptionSignal
                    {
                        Kind = AbsorptionType.StoppingVolume,
                        Direction = -1,
                        Price = bar.PocPrice,
                        Wick = "upper",
                        Strength = strength,
                        Detail = "STOPPING VOL — POC in upper wick",
                    });
                }
                else if (bar.PocPrice < bodyBot)
                {
                    sigs.Add(new AbsorptionSignal
                    {
                        Kind = AbsorptionType.StoppingVolume,
                        Direction = +1,
                        Price = bar.PocPrice,
                        Wick = "lower",
                        Strength = strength,
                        Detail = "STOPPING VOL — POC in lower wick",
                    });
                }
            }

            // ABS-04 EFFORT vs RESULT
            if (volEma > 0 && atr > 0 &&
                bar.TotalVol > volEma * cfg.EvrVolMult &&
                bar.BarRange < atr * cfg.EvrRangeCap)
            {
                int dir = bar.BarDelta < 0 ? +1 : -1;
                double strength = Math.Min(bar.TotalVol / (volEma * cfg.EvrVolMult * 2.0), 1.0);
                double deltaRatio = bar.TotalVol == 0
                    ? 0
                    : Math.Abs((double)bar.BarDelta) / bar.TotalVol;
                sigs.Add(new AbsorptionSignal
                {
                    Kind = AbsorptionType.EffortVsResult,
                    Direction = dir,
                    Price = (bar.High + bar.Low) / 2.0,
                    Wick = "body",
                    Strength = strength,
                    DeltaRatio = deltaRatio,
                    Detail = "EFFORT vs RESULT — high vol, narrow range",
                });
            }

            // ABS-07 VA extreme proximity bonus
            double prox = cfg.VaExtremeTicks * tickSize;
            for (int i = 0; i < sigs.Count; i++)
            {
                var s = sigs[i];
                bool atVah = vah.HasValue && Math.Abs(s.Price - vah.Value) <= prox;
                bool atVal = val.HasValue && Math.Abs(s.Price - val.Value) <= prox;
                if (atVah || atVal)
                {
                    s.AtVaExtreme = true;
                    s.Strength = Math.Min(s.Strength + cfg.VaExtremeStrengthBonus, 1.0);
                    s.Detail = s.Detail + (atVah ? " @VAH" : " @VAL");
                }
            }

            return sigs;
        }

        private static void TryClassic(
            long wickVol, long wickDelta, long totalVol,
            double effWickMin, double deltaMax, double barDeltaRatio,
            double price, string side, int direction,
            List<AbsorptionSignal> sigs)
        {
            if (wickVol == 0 || totalVol == 0) return;
            double wickPct = wickVol * 100.0 / totalVol;
            double deltaRatio = Math.Abs((double)wickDelta) / wickVol;
            if (wickPct >= effWickMin &&
                deltaRatio < deltaMax &&
                barDeltaRatio < deltaMax * 1.5)
            {
                double strength = Math.Min(wickPct / 60.0, 1.0) *
                                  (1.0 - deltaRatio / deltaMax);
                if (strength < 0) strength = 0;
                sigs.Add(new AbsorptionSignal
                {
                    Kind = AbsorptionType.Classic,
                    Direction = direction,
                    Price = price,
                    Wick = side,
                    Strength = strength,
                    WickPct = wickPct,
                    DeltaRatio = deltaRatio,
                    Detail = string.Format("CLASSIC {0} — wick {1:F0}% balanced delta", side, wickPct),
                });
            }
        }
    }
}
