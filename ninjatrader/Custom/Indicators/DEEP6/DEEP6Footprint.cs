// DEEP6 Footprint — NinjaTrader 8 indicator.
//
// This file contains the main DEEP6 Footprint indicator: the FootprintBar / Cell
// data structures, AbsorptionDetector (4 variants + VAH/VAL bonus),
// ExhaustionDetector (6 variants + delta gate + cooldown), and profile-anchor
// overlay (prior-day POC/VAH/VAL, PDH/PDL/PDM, naked POCs, prior-week POC).
//
// Options/gamma overlay lives in the companion DEEP6 indicator — add it separately.
//
// Drop-in install: copy this file to
//   %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\DEEP6Footprint.cs
// then F5 in the NinjaScript Editor.
//
// See repository docs/ for SETUP, SIGNALS, and ARCHITECTURE reference.
// Port spec: .planning/phases/16-*/PORT-SPEC.md (thresholds authoritative).

#region Using
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Linq;
using System.Text;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript.DrawingTools;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Levels;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
// Type aliases resolve System.Windows.Media vs SharpDX.Direct2D1 ambiguity.
// Bare Brush / Color / SolidColorBrush = WPF. SharpDX variants always fully qualified.
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
using Color = System.Windows.Media.Color;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.AddOns.DEEP6
{

    // ─── from FootprintBar.cs ───
    public sealed class Cell
    {
        public long BidVol;
        public long AskVol;
        public long NeutralVol;

        public long TotalVol => BidVol + AskVol + NeutralVol;
        public long Delta    => AskVol - BidVol;
    }

    public sealed class FootprintBar
    {
        public int BarIndex;
        public double Open;
        public double High;
        public double Low;
        public double Close;
        public SortedDictionary<double, Cell> Levels = new SortedDictionary<double, Cell>();
        public long TotalVol;
        public long BarDelta;
        public long Cvd;
        public double PocPrice;
        public double BarRange;
        public long RunningDelta;
        public long MaxDelta;
        public long MinDelta;

        public void AddTrade(double price, long size, int aggressor)
        {
            if (size <= 0) return;
            Cell lv;
            if (!Levels.TryGetValue(price, out lv))
            {
                lv = new Cell();
                Levels[price] = lv;
            }

            if (aggressor == 1)        // buy (hit ask)
            {
                lv.AskVol += size;
                RunningDelta += size;
            }
            else if (aggressor == 2)   // sell (hit bid)
            {
                lv.BidVol += size;
                RunningDelta -= size;
            }
            else                       // unclassified (between spread)
            {
                lv.NeutralVol += size;
            }

            if (RunningDelta > MaxDelta) MaxDelta = RunningDelta;
            if (RunningDelta < MinDelta) MinDelta = RunningDelta;

            if (Open == 0) Open = price;
            if (price > High) High = price;
            if (Low == 0 || price < Low) Low = price;
            Close = price;
            TotalVol += size;
        }

        public void Finalize(long priorCvd)
        {
            BarDelta = 0;
            double bestPx = 0;
            long bestVol = -1;
            foreach (var kv in Levels)
            {
                BarDelta += kv.Value.AskVol - kv.Value.BidVol;
                long v = kv.Value.AskVol + kv.Value.BidVol;
                if (v > bestVol) { bestVol = v; bestPx = kv.Key; }
            }
            if (Levels.Count > 0) PocPrice = bestPx;
            BarRange = High - Low;
            if (BarRange < 0) BarRange = 0;
            Cvd = priorCvd + BarDelta;
        }

        // 70% Value Area. Returns (VAH, VAL).
        // Port of deep6/engines/poc.py:231-257.
        public static (double vah, double val) ComputeValueArea(FootprintBar bar, double tickSize, double vaPct = 0.70)
        {
            if (bar.Levels.Count == 0 || bar.TotalVol == 0) return (bar.High, bar.Low);
            var sorted = bar.Levels
                .OrderByDescending(kv => kv.Value.AskVol + kv.Value.BidVol)
                .ToList();
            double target = bar.TotalVol * vaPct;
            double acc = 0;
            var ticksInVa = new List<double>();
            foreach (var kv in sorted)
            {
                acc += kv.Value.AskVol + kv.Value.BidVol;
                ticksInVa.Add(kv.Key);
                if (acc >= target) break;
            }
            if (ticksInVa.Count == 0) return (bar.High, bar.Low);
            return (ticksInVa.Max() + tickSize, ticksInVa.Min());
        }

        // Delta conviction scalar used by delta-family signals.
        // Port of deep6/state/footprint.py:134-161.
        public double DeltaQualityScalar()
        {
            long extreme = Math.Max(Math.Max(Math.Abs(MaxDelta), Math.Abs(MinDelta)), 1);
            if (RunningDelta == 0 && extreme <= 1) return 1.0;
            double ratio = Math.Abs((double)RunningDelta) / extreme;
            if (ratio >= 0.95) return 1.15;
            if (ratio <= 0.35) return 0.7;
            // linear: (0.35, 0.7) → (0.95, 1.15)
            return 0.7 + (ratio - 0.35) * (1.15 - 0.7) / (0.95 - 0.35);
        }
    }

    // ─── from AbsorptionDetector.cs ───
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

    /// <summary>
    /// Legacy static absorption detector. Superseded by the ISignalDetector registry
    /// (NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Absorption.AbsorptionDetector).
    /// Use DEEP6Strategy.UseNewRegistry=true to activate the registry path.
    /// This class will be removed in Phase 18 once session-replay parity is confirmed.
    /// </summary>
    [System.Obsolete("Legacy path superseded by AbsorptionDetector (ISignalDetector). Set UseNewRegistry=true. Scheduled for removal in Phase 18.")]
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

    // ─── from ExhaustionDetector.cs ───
    public enum ExhaustionType
    {
        ZeroPrint,
        ExhaustionPrint,
        ThinPrint,
        FatPrint,
        FadingMomentum,
        BidAskFade,
    }

    public sealed class ExhaustionSignal
    {
        public ExhaustionType Kind;
        public int Direction;    // +1 bullish, -1 bearish, 0 neutral
        public double Price;
        public double Strength;
        public string Detail;
    }

    public sealed class ExhaustionConfig
    {
        public double ThinPct           = 0.05;
        public double FatMult           = 2.0;
        public double ExhaustWickMin    = 35.0;
        public double FadeThreshold     = 0.60;
        public int    CooldownBars      = 5;
        public bool   DeltaGateEnabled  = true;
        public double DeltaGateMinRatio = 0.10;
    }

    /// <summary>
    /// Legacy exhaustion detector. Superseded by the ISignalDetector registry
    /// (NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion.ExhaustionDetector).
    /// Use DEEP6Strategy.UseNewRegistry=true to activate the registry path.
    /// This class will be removed in Phase 18 once session-replay parity is confirmed.
    /// </summary>
    [System.Obsolete("Legacy path superseded by ExhaustionDetector (ISignalDetector). Set UseNewRegistry=true. Scheduled for removal in Phase 18.")]
    public sealed class ExhaustionDetector
    {
        private readonly Dictionary<ExhaustionType, int> _cooldown = new Dictionary<ExhaustionType, int>();

        public void ResetCooldowns() { _cooldown.Clear(); }

        private bool CheckCooldown(ExhaustionType t, int barIndex, int cooldownBars)
        {
            int last;
            if (!_cooldown.TryGetValue(t, out last)) return true;
            return (barIndex - last) >= cooldownBars;
        }

        private void SetCooldown(ExhaustionType t, int barIndex) { _cooldown[t] = barIndex; }

        private static bool DeltaGate(FootprintBar bar, ExhaustionConfig cfg)
        {
            if (!cfg.DeltaGateEnabled) return true;
            if (bar.TotalVol == 0) return true;
            double r = Math.Abs((double)bar.BarDelta) / bar.TotalVol;
            if (r < cfg.DeltaGateMinRatio) return true;
            if (bar.Close > bar.Open) return bar.BarDelta < 0;
            if (bar.Close < bar.Open) return bar.BarDelta > 0;
            return true;
        }

        public List<ExhaustionSignal> Detect(
            FootprintBar bar,
            FootprintBar priorBar,
            int barIndex,
            double atr,
            ExhaustionConfig cfg)
        {
            var sigs = new List<ExhaustionSignal>();
            if (bar == null || bar.Levels.Count == 0 || bar.TotalVol == 0) return sigs;

            var sortedTicks = bar.Levels.Keys.OrderBy(k => k).ToList();
            if (sortedTicks.Count < 2) return sigs;

            long maxLevelVol = 0;
            foreach (var lv in bar.Levels.Values)
            {
                long v = lv.AskVol + lv.BidVol;
                if (v > maxLevelVol) maxLevelVol = v;
            }
            double avgLevelVol = (double)bar.TotalVol / bar.Levels.Count;

            // EXH-01 ZERO PRINT — gate exempt
            if (CheckCooldown(ExhaustionType.ZeroPrint, barIndex, cfg.CooldownBars))
            {
                double bodyTop = Math.Max(bar.Open, bar.Close);
                double bodyBot = Math.Min(bar.Open, bar.Close);
                foreach (var tick in sortedTicks)
                {
                    var lv = bar.Levels[tick];
                    if (lv.AskVol == 0 && lv.BidVol == 0 && tick > bodyBot && tick < bodyTop)
                    {
                        int dir = bar.Close > bar.Open ? +1 : -1;
                        sigs.Add(new ExhaustionSignal
                        {
                            Kind = ExhaustionType.ZeroPrint,
                            Direction = dir,
                            Price = tick,
                            Strength = 0.6,
                            Detail = string.Format("ZERO PRINT @ {0:F2} — must revisit", tick),
                        });
                        SetCooldown(ExhaustionType.ZeroPrint, barIndex);
                        break;
                    }
                }
            }

            // Delta gate — applies to variants 2-6
            if (!DeltaGate(bar, cfg)) return sigs;

            // EXH-02 EXHAUSTION PRINT — heavy volume at single bar extreme
            if (CheckCooldown(ExhaustionType.ExhaustionPrint, barIndex, cfg.CooldownBars))
            {
                double effMin = cfg.ExhaustWickMin * (bar.BarRange > atr * 1.5 ? 1.2 : 1.0);
                double eachLevelThreshold = effMin / 3.0;

                double highTick = sortedTicks[sortedTicks.Count - 1];
                var highLv = bar.Levels[highTick];
                if (highLv.AskVol > 0)
                {
                    double pct = highLv.AskVol * 100.0 / bar.TotalVol;
                    if (pct >= eachLevelThreshold)
                    {
                        double strength = Math.Min(pct / 20.0, 1.0);
                        sigs.Add(new ExhaustionSignal
                        {
                            Kind = ExhaustionType.ExhaustionPrint,
                            Direction = -1,
                            Price = highTick,
                            Strength = strength,
                            Detail = string.Format("EXHAUSTION PRINT high — ask {0:F0}%", pct),
                        });
                        SetCooldown(ExhaustionType.ExhaustionPrint, barIndex);
                    }
                }

                if (CheckCooldown(ExhaustionType.ExhaustionPrint, barIndex, cfg.CooldownBars))
                {
                    double lowTick = sortedTicks[0];
                    var lowLv = bar.Levels[lowTick];
                    if (lowLv.BidVol > 0)
                    {
                        double pct = lowLv.BidVol * 100.0 / bar.TotalVol;
                        if (pct >= eachLevelThreshold)
                        {
                            double strength = Math.Min(pct / 20.0, 1.0);
                            sigs.Add(new ExhaustionSignal
                            {
                                Kind = ExhaustionType.ExhaustionPrint,
                                Direction = +1,
                                Price = lowTick,
                                Strength = strength,
                                Detail = string.Format("EXHAUSTION PRINT low — bid {0:F0}%", pct),
                            });
                            SetCooldown(ExhaustionType.ExhaustionPrint, barIndex);
                        }
                    }
                }
            }

            // EXH-03 THIN PRINT — fast move through body
            if (CheckCooldown(ExhaustionType.ThinPrint, barIndex, cfg.CooldownBars))
            {
                double bodyTop = Math.Max(bar.Open, bar.Close);
                double bodyBot = Math.Min(bar.Open, bar.Close);
                int thinCount = 0;
                foreach (var tick in sortedTicks)
                {
                    if (tick < bodyBot || tick > bodyTop) continue;
                    var lv = bar.Levels[tick];
                    long v = lv.AskVol + lv.BidVol;
                    if (maxLevelVol > 0 && v < maxLevelVol * cfg.ThinPct) thinCount++;
                }
                if (thinCount >= 3)
                {
                    int dir = bar.Close > bar.Open ? +1 : -1;
                    double strength = Math.Min(thinCount / 7.0, 1.0);
                    sigs.Add(new ExhaustionSignal
                    {
                        Kind = ExhaustionType.ThinPrint,
                        Direction = dir,
                        Price = (bar.High + bar.Low) / 2.0,
                        Strength = strength,
                        Detail = string.Format("THIN PRINT — {0} skipped levels", thinCount),
                    });
                    SetCooldown(ExhaustionType.ThinPrint, barIndex);
                }
            }

            // EXH-04 FAT PRINT — strong acceptance level (neutral)
            if (CheckCooldown(ExhaustionType.FatPrint, barIndex, cfg.CooldownBars))
            {
                double fattestPx = 0;
                long fattestVol = 0;
                foreach (var kv in bar.Levels)
                {
                    long v = kv.Value.AskVol + kv.Value.BidVol;
                    if (v > avgLevelVol * cfg.FatMult && v > fattestVol)
                    {
                        fattestPx = kv.Key;
                        fattestVol = v;
                    }
                }
                if (fattestVol > 0)
                {
                    double strength = Math.Min(fattestVol / (avgLevelVol * cfg.FatMult * 2.0), 1.0);
                    sigs.Add(new ExhaustionSignal
                    {
                        Kind = ExhaustionType.FatPrint,
                        Direction = 0,
                        Price = fattestPx,
                        Strength = strength,
                        Detail = string.Format("FAT PRINT @ {0:F2} — acceptance", fattestPx),
                    });
                    SetCooldown(ExhaustionType.FatPrint, barIndex);
                }
            }

            // EXH-05 FADING MOMENTUM — delta diverges from price direction
            if (CheckCooldown(ExhaustionType.FadingMomentum, barIndex, cfg.CooldownBars))
            {
                if (bar.BarRange > 0 && Math.Abs((double)bar.BarDelta) > bar.TotalVol * 0.15)
                {
                    bool bullish = bar.Close > bar.Open;
                    int dir = bullish ? -1 : +1;
                    double strength = Math.Min(Math.Abs((double)bar.BarDelta) / bar.TotalVol, 1.0);
                    sigs.Add(new ExhaustionSignal
                    {
                        Kind = ExhaustionType.FadingMomentum,
                        Direction = dir,
                        Price = bar.Close,
                        Strength = strength,
                        Detail = "FADING MOMENTUM — delta opposite to price",
                    });
                    SetCooldown(ExhaustionType.FadingMomentum, barIndex);
                }
            }

            // EXH-06 BID/ASK FADE vs prior bar
            if (priorBar != null && priorBar.Levels.Count > 0 &&
                CheckCooldown(ExhaustionType.BidAskFade, barIndex, cfg.CooldownBars))
            {
                double currHighTick = sortedTicks[sortedTicks.Count - 1];
                long currHighAsk = bar.Levels[currHighTick].AskVol;

                var priorSorted = priorBar.Levels.Keys.OrderBy(k => k).ToList();
                double priorHighTick = priorSorted[priorSorted.Count - 1];
                long priorHighAsk = priorBar.Levels[priorHighTick].AskVol;

                if (priorHighAsk > 0 && currHighAsk < priorHighAsk * cfg.FadeThreshold)
                {
                    double strength = 1.0 - (currHighAsk / (double)priorHighAsk);
                    sigs.Add(new ExhaustionSignal
                    {
                        Kind = ExhaustionType.BidAskFade,
                        Direction = -1,
                        Price = currHighTick,
                        Strength = strength,
                        Detail = "BID/ASK FADE — ask intensity dropped at top",
                    });
                    SetCooldown(ExhaustionType.BidAskFade, barIndex);
                }
                else
                {
                    double currLowTick = sortedTicks[0];
                    long currLowBid = bar.Levels[currLowTick].BidVol;
                    double priorLowTick = priorSorted[0];
                    long priorLowBid = priorBar.Levels[priorLowTick].BidVol;
                    if (priorLowBid > 0 && currLowBid < priorLowBid * cfg.FadeThreshold)
                    {
                        double strength = 1.0 - (currLowBid / (double)priorLowBid);
                        sigs.Add(new ExhaustionSignal
                        {
                            Kind = ExhaustionType.BidAskFade,
                            Direction = +1,
                            Price = currLowTick,
                            Strength = strength,
                            Detail = "BID/ASK FADE — bid intensity dropped at bottom",
                        });
                        SetCooldown(ExhaustionType.BidAskFade, barIndex);
                    }
                }
            }

            return sigs;
        }
    }

}

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6Footprint : Indicator
    {
        // ---- State ----
        private readonly Dictionary<int, FootprintBar> _bars = new Dictionary<int, FootprintBar>();
        private double _bestBid = double.NaN;
        private double _bestAsk = double.NaN;
        private long _priorCvd;
        private FootprintBar _priorFinalized;

        // ---- L2 Liquidity Walls (from Rithmic native depth feed) ----
        // Per-price state: max size ever observed at this level + last-update timestamp + iceberg refill counter.
        // OnMarketDepth populates these on the data thread; OnRender reads on the chart thread (locked snapshot).
        private sealed class L2LevelState
        {
            public long CurrentSize;
            public long MaxSize;
            public DateTime LastUpdate;
            public int RefillCount;
        }
        private readonly Dictionary<double, L2LevelState> _l2Bids = new Dictionary<double, L2LevelState>();
        private readonly Dictionary<double, L2LevelState> _l2Asks = new Dictionary<double, L2LevelState>();
        private readonly object _l2Lock = new object();
        private DateTime _lastL2Prune = DateTime.MinValue;

        // volume EMA (for absorption thresholds) — simple 20-period EMA of TotalVol
        private double _volEma;
        private const double VolEmaAlpha = 2.0 / (20.0 + 1.0);

        // ATR via rolling window of (high-low)
        private readonly Queue<double> _atrWindow = new Queue<double>();
        private const int AtrPeriod = 20;
        private double _atr = 1.0;

        // detectors + configs
        private readonly AbsorptionConfig _absCfg = new AbsorptionConfig();
        private readonly ExhaustionConfig _exhCfg = new ExhaustionConfig();
        private readonly ExhaustionDetector _exhDetector = new ExhaustionDetector();

        // ---- Chart Trader toolbar (clickable on/off toggles for each feature, rendered top-left) ----
        private sealed class TraderButton
        {
            public string Label;
            public Func<bool> Get;
            public Action<bool> Set;
            public RectangleF Rect;
        }
        private List<TraderButton> _ctButtons;
        private bool _ctMouseWired;
        private SharpDX.Direct2D1.Brush _ctOnDx, _ctOffDx, _ctBorderDx;
        private TextFormat _ctBtnFont;

        // session reset tracking
        private DateTime _lastSessionDate = DateTime.MinValue;

        // ---- Phase 18: Confluence Scorer (indicator-side registry + shared state) ----
        // Registry and session run independently of DEEP6Strategy's registry instance.
        // DEEP6Strategy reads results via ScorerSharedState.Latest() (Wave 3 wires entry gating).
        private DetectorRegistry _scorerRegistry;
        private SessionContext   _scorerSession;
        // Latches the most recent ScorerResult so OnRender can read it without re-scoring.
        // Updated once per bar close in OnBarUpdate; read every frame in OnRender.
        private ScorerResult _lastScorerResult;

        // ---- Profile Anchor Levels ----
        private ProfileAnchorLevels _profileAnchors = new ProfileAnchorLevels();
        private DateTime _profileSessionDate = DateTime.MinValue;

        // SharpDX brushes (device-dependent)
        private SharpDX.Direct2D1.Brush _bidDx, _askDx, _textDx, _imbalBuyDx, _imbalSellDx,
                                         _pocDx, _vahDx, _valDx, _gridDx,
                                         _wallBidDx, _wallAskDx;

        // Phase 18: Scorer HUD + tier marker brushes (01-COLOR-PALETTE.md tokens)
        // Allocated in OnRenderTargetChanged, disposed in DisposeDx — matches existing pattern.
        private SharpDX.Direct2D1.SolidColorBrush _scoreHudTextDx;    // #E8EAED  primary ink (score line)
        private SharpDX.Direct2D1.SolidColorBrush _scoreHudDimDx;     // #B0B6BE  secondary ink (narrative line)
        private SharpDX.Direct2D1.SolidColorBrush _scoreHudBgDx;      // #0E1014 @ 78%  HUD backdrop
        private SharpDX.Direct2D1.SolidColorBrush _scoreHudBorderDx;  // #262633  1px border
        private SharpDX.Direct2D1.SolidColorBrush _scoreTierALongDx;  // #00E676  TypeA long (saturated green)
        private SharpDX.Direct2D1.SolidColorBrush _scoreTierAShortDx; // #FF1744  TypeA short (saturated red)
        private SharpDX.Direct2D1.SolidColorBrush _scoreTierBLongDx;  // #66BB6A  TypeB long (medium green)
        private SharpDX.Direct2D1.SolidColorBrush _scoreTierBShortDx; // #EF5350  TypeB short (medium red)
        private SharpDX.Direct2D1.SolidColorBrush _scoreTierCLongDx;  // #7CB387 @ 70%  TypeC long (gray-green)
        private SharpDX.Direct2D1.SolidColorBrush _scoreTierCShortDx; // #B87C82 @ 70%  TypeC short (gray-red)
        private SharpDX.Direct2D1.SolidColorBrush _scoreNeutralDx;    // #8A929E  QUIET/DISQUALIFIED dim
        private SharpDX.Direct2D1.SolidColorBrush _scoreLabelBgDx;    // #0E1014 @ 60%  narrative label bg pill
        // HUD monospace font (12pt Consolas for score line; must be disposed with other fonts)
        private TextFormat _hudFont;
        // HUD label font (9pt Segoe UI for narrative + tier lines)
        private TextFormat _hudLabelFont;
        // Profile anchor brushes
        private SharpDX.Direct2D1.SolidColorBrush _anchorPocDx;       // #FFD23F  PD POC
        private SharpDX.Direct2D1.SolidColorBrush _anchorVaDx;        // #C8D17A  PD VAH/VAL/PDH/PDL/PDM
        private SharpDX.Direct2D1.SolidColorBrush _anchorNakedDx;     // #FFD23F @ 60%  naked POC
        private SharpDX.Direct2D1.SolidColorBrush _anchorPwPocDx;     // #E5C24A  prior-week POC
        private SharpDX.Direct2D1.SolidColorBrush _anchorCompositeDx; // #C8D17A @ 12%  composite VA band
        private StrokeStyle _dashStyle;
        private TextFormat _cellFont, _labelFont;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description         = "DEEP6 Footprint — per-bar footprint with absorption/exhaustion markers, POC/VA, and profile anchor levels.";
                Name                = "DEEP6 Footprint";
                Calculate           = Calculate.OnEachTick;
                IsOverlay           = true;
                DisplayInDataBox    = false;
                DrawOnPricePanel    = true;
                PaintPriceMarkers   = false;
                ScaleJustification  = ScaleJustification.Right;
                IsSuspendedWhileInactive = true;

                // Defaults
                ImbalanceRatio          = 3.0;
                ShowFootprintCells      = true;
                ShowAbsorptionMarkers   = true;
                ShowExhaustionMarkers   = true;
                ShowPoc                 = true;
                ShowValueArea           = true;
                AbsorbWickMinPct        = 30.0;
                ExhaustWickMinPct       = 35.0;
                CellFontSize            = 9f;
                CellColumnWidth         = 80;
                ShowLiquidityWalls      = true;
                LiquidityWallMin        = 100;
                LiquidityWallStaleSec   = 90;
                LiquidityMaxPerSide     = 4;
                ShowChartTrader         = true;

                // Phase 18: Scorer HUD defaults
                ShowScoreHud        = true;
                ScoreHudPaddingPx   = 12;

                ShowProfileAnchors     = true;
                ShowPriorDayLevels     = true;
                ShowNakedPocs          = true;
                ShowCompositeVA        = false;
                NakedPocMaxAgeSessions = 20;

                AnchorPocBrush       = MakeFrozenBrush(Color.FromRgb(0xFF, 0xD2, 0x3F));
                AnchorVaBrush        = MakeFrozenBrush(Color.FromRgb(0xC8, 0xD1, 0x7A));
                AnchorNakedBrush     = MakeFrozenBrush(Color.FromArgb(153, 0xFF, 0xD2, 0x3F)); // 60% alpha
                AnchorPwPocBrush     = MakeFrozenBrush(Color.FromRgb(0xE5, 0xC2, 0x4A));
                AnchorCompositeBrush = MakeFrozenBrush(Color.FromArgb(30, 0xC8, 0xD1, 0x7A));  // ~12% alpha

                // Palette per .planning/design/ninjatrader-chart/01-COLOR-PALETTE.md
                BidCellBrush      = MakeFrozenBrush(Color.FromRgb(0xFF, 0x6B, 0x6B));    // bid dominance
                AskCellBrush      = MakeFrozenBrush(Color.FromRgb(0x4F, 0xC3, 0xF7));    // ask dominance
                CellTextBrush     = MakeFrozenBrush(Color.FromRgb(0xE6, 0xED, 0xF3));    // primary ink
                PocBrush          = MakeFrozenBrush(Color.FromRgb(0xFF, 0xD2, 0x3F));    // POC yellow
                VahBrush          = MakeFrozenBrush(Color.FromRgb(0xC8, 0xD1, 0x7A));    // olive VA (distinct hue vs POC)
                ValBrush          = MakeFrozenBrush(Color.FromRgb(0xC8, 0xD1, 0x7A));
                ImbalanceBuyBrush = MakeFrozenBrush(Color.FromArgb(110, 0, 200, 80));
                ImbalanceSellBrush= MakeFrozenBrush(Color.FromArgb(110, 220, 40, 40));
                WallBidBrush      = MakeFrozenBrush(Color.FromArgb(220, 43, 140, 255));   // bright blue
                WallAskBrush      = MakeFrozenBrush(Color.FromArgb(220, 255, 138, 61));   // warm orange
            }
            else if (State == State.Configure)
            {
                _absCfg.AbsorbWickMin  = AbsorbWickMinPct;
                _exhCfg.ExhaustWickMin = ExhaustWickMinPct;

                // Phase 18: build indicator-side scorer registry (read-only; no risk gates).
                // Mirrors the pattern in DEEP6Strategy.OnStateChange but without strategy-specific
                // detectors that need account context.
                _scorerRegistry = new DetectorRegistry();
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Absorption.AbsorptionDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion.ExhaustionDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Imbalance.ImbalanceDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta.DeltaDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Auction.AuctionDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.VolPattern.VolPatternDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Trap.TrapDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.TrespassDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.CounterSpoofDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.IcebergDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.VPContextDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.MicroProbDetector());  // LAST

                _scorerSession = new SessionContext { TickSize = TickSize > 0 ? TickSize : 0.25 };
            }
            else if (State == State.DataLoaded)
            {
                _bars.Clear();
                _exhDetector.ResetCooldowns();
                _atrWindow.Clear();
                _volEma = 0.0;
                _priorCvd = 0;
                _priorFinalized = null;

                _profileAnchors.Reset();
                _profileAnchors.TickSize = TickSize > 0 ? TickSize : 0.25;
                _profileAnchors.NakedPocMaxAgeSessions = NakedPocMaxAgeSessions;
                _profileSessionDate = DateTime.MinValue;

                _ctButtons = new List<TraderButton>
                {
                    new TraderButton { Label = "CELLS", Get = () => ShowFootprintCells,    Set = v => ShowFootprintCells    = v },
                    new TraderButton { Label = "POC",   Get = () => ShowPoc,               Set = v => ShowPoc               = v },
                    new TraderButton { Label = "VA",    Get = () => ShowValueArea,         Set = v => ShowValueArea         = v },
                    new TraderButton { Label = "ANCH",  Get = () => ShowProfileAnchors,    Set = v => ShowProfileAnchors    = v },
                    new TraderButton { Label = "ABS",   Get = () => ShowAbsorptionMarkers, Set = v => ShowAbsorptionMarkers = v },
                    new TraderButton { Label = "EXH",   Get = () => ShowExhaustionMarkers, Set = v => ShowExhaustionMarkers = v },
                    new TraderButton { Label = "L2",    Get = () => ShowLiquidityWalls,    Set = v => ShowLiquidityWalls    = v },
                };
            }
            else if (State == State.Terminated)
            {
                // Always attempt detach — null-conditional makes it safe even when ChartControl is gone.
                try { if (ChartControl != null) ChartControl.MouseDown -= OnChartTraderMouseDown; } catch { }
                _ctMouseWired = false;
                DisposeDx();
            }
        }

        // ---- Tick intake ----

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (State != State.Realtime && State != State.Historical) return;

            if (e.MarketDataType == MarketDataType.Bid) { _bestBid = e.Price; return; }
            if (e.MarketDataType == MarketDataType.Ask) { _bestAsk = e.Price; return; }
            if (e.MarketDataType != MarketDataType.Last) return;
            if (CurrentBar < 0) return;

            int aggressor;
            if (!double.IsNaN(_bestAsk) && e.Price >= _bestAsk) aggressor = 1;
            else if (!double.IsNaN(_bestBid) && e.Price <= _bestBid) aggressor = 2;
            else aggressor = 0;

            FootprintBar bar;
            if (!_bars.TryGetValue(CurrentBar, out bar))
            {
                bar = new FootprintBar { BarIndex = CurrentBar };
                _bars[CurrentBar] = bar;
            }
            bar.AddTrade(e.Price, (long)e.Volume, aggressor);
        }

        // ---- L2 depth intake — populates _l2Bids / _l2Asks for Liquidity Wall detection ----

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (!ShowLiquidityWalls) return;
            if (e.Position >= 10) return;   // only top 10 ladder rungs

            Dictionary<double, L2LevelState> dict;
            if (e.MarketDataType == MarketDataType.Bid) dict = _l2Bids;
            else if (e.MarketDataType == MarketDataType.Ask) dict = _l2Asks;
            else return;

            long newSize = e.Operation == Operation.Remove ? 0 : (long)e.Volume;

            lock (_l2Lock)
            {
                L2LevelState st;
                if (!dict.TryGetValue(e.Price, out st))
                {
                    st = new L2LevelState();
                    dict[e.Price] = st;
                }
                // Iceberg detection: counted when level was hit hard then refilled to >50% of historical max.
                if (st.MaxSize > 0 && st.CurrentSize < st.MaxSize * 0.5 && newSize >= st.MaxSize * 0.5)
                    st.RefillCount++;
                st.CurrentSize = newSize;
                if (newSize > st.MaxSize) st.MaxSize = newSize;
                st.LastUpdate = DateTime.UtcNow;

                // Periodic prune of stale entries (price levels no longer active).
                if ((DateTime.UtcNow - _lastL2Prune).TotalSeconds > 30)
                {
                    PruneL2(_l2Bids);
                    PruneL2(_l2Asks);
                    _lastL2Prune = DateTime.UtcNow;
                }
            }
        }

        private static void PruneL2(Dictionary<double, L2LevelState> dict)
        {
            var cutoff = DateTime.UtcNow.AddMinutes(-15);
            var stale = new List<double>();
            foreach (var kv in dict)
                if (kv.Value.LastUpdate < cutoff) stale.Add(kv.Key);
            foreach (var k in stale) dict.Remove(k);
        }

        // WPF brushes created off the UI thread (NT8 calls SetDefaults / OnRenderTargetChanged
        // from worker threads) throw InvalidOperationException unless frozen. Always construct via this helper.
        private static SolidColorBrush MakeFrozenBrush(Color c)
        {
            var b = new SolidColorBrush(c);
            if (b.CanFreeze) b.Freeze();
            return b;
        }

        // ---- Bar lifecycle ----

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;
            if (CurrentBar < 2) return;

            if (!IsFirstTickOfBar) return;

            int prevIdx = CurrentBar - 1;
            FootprintBar prev;
            if (!_bars.TryGetValue(prevIdx, out prev)) return;

            // Reconcile OHLC with NT8's authoritative bar (handles silent-tick edge case).
            prev.Open = Bars.GetOpen(prevIdx);
            prev.High = Bars.GetHigh(prevIdx);
            prev.Low  = Bars.GetLow(prevIdx);
            prev.Close= Bars.GetClose(prevIdx);
            prev.Finalize(_priorCvd);
            _priorCvd = prev.Cvd;

            // Update rolling ATR / vol EMA
            _atrWindow.Enqueue(prev.BarRange);
            while (_atrWindow.Count > AtrPeriod) _atrWindow.Dequeue();
            double sum = 0; foreach (var v in _atrWindow) sum += v;
            _atr = _atrWindow.Count == 0 ? 1.0 : Math.Max(sum / _atrWindow.Count, 0.25);
            _volEma = _volEma == 0 ? prev.TotalVol : _volEma + VolEmaAlpha * (prev.TotalVol - _volEma);

            // Session reset at RTH open (9:30 ET) — simple date-change detection.
            DateTime barDate = Bars.GetTime(prevIdx).Date;
            if (barDate != _lastSessionDate)
            {
                _exhDetector.ResetCooldowns();
                _lastSessionDate = barDate;

                // Phase 18: reset indicator-side scorer session on new trading day.
                if (_scorerSession != null) _scorerSession.ResetSession();
                if (_scorerRegistry != null) _scorerRegistry.ResetAll();
            }

            // Feed profile anchor aggregator — session boundary before bar accumulation.
            {
                DateTime barTimeEt = Bars.GetTime(prevIdx);
                if (barDate != _profileSessionDate)
                {
                    _profileAnchors.OnSessionBoundary(barDate);
                    _profileSessionDate = barDate;
                }
                _profileAnchors.OnBarClose(prev, barTimeEt);
            }

            // Compute VAH/VAL for this bar (used by absorption VA bonus).
            var va = FootprintBar.ComputeValueArea(prev, TickSize);

            // Run detectors.
            if (ShowAbsorptionMarkers)
            {
                var abs = AbsorptionDetector.Detect(prev, _atr, _volEma, _absCfg, va.vah, va.val, TickSize);
                for (int i = 0; i < abs.Count; i++) DrawAbsorptionMarker(prevIdx, abs[i]);
            }
            if (ShowExhaustionMarkers)
            {
                var exh = _exhDetector.Detect(prev, _priorFinalized, prevIdx, _atr, _exhCfg);
                for (int i = 0; i < exh.Count; i++) DrawExhaustionMarker(prevIdx, exh[i]);
            }

            _priorFinalized = prev;

            // ── Phase 18: Confluence Scorer invocation (once per bar close) ──────────────────
            // Runs after all legacy detectors so their output is fully written to prev.
            // The scorer uses its own DetectorRegistry instance (not shared with DEEP6Strategy)
            // to get the full SignalResult[] needed by ConfluenceScorer.Score().
            //
            // VPContext zone proximity deferred; when extended in a follow-up, plumb zoneScore +
            // zoneDistTicks from VPContextDetector output here.
            // (Open Question from 18-RESEARCH.md: "VPContext zone extension not yet wired")
            if (_scorerRegistry != null && _scorerSession != null)
            {
                // Populate session context fields from current bar state.
                _scorerSession.Atr20        = _atr;
                _scorerSession.VolEma20     = _volEma;
                _scorerSession.TickSize     = TickSize;
                _scorerSession.Vah          = va.vah;
                _scorerSession.Val          = va.val;
                _scorerSession.PriorBar     = _priorFinalized;  // now points to prev after the assignment above
                _scorerSession.BarsSinceOpen = prevIdx;         // bar index as session-bar counter

                // Task 4: Accumulate SessionAvgAtr each bar for slow-grind veto.
                // Running average: SessionAvgAtr = (sum of Atr20 values) / SessionAtrSamples.
                // Reset at session boundary via _scorerSession.ResetSession() (SessionAvgAtr=0, SessionAtrSamples=0).
                if (_atr > 0.0)
                {
                    _scorerSession.SessionAtrSamples++;
                    _scorerSession.SessionAvgAtr = _scorerSession.SessionAvgAtr
                        + (_atr - _scorerSession.SessionAvgAtr) / _scorerSession.SessionAtrSamples;
                }

                var signals = _scorerRegistry.EvaluateBar(prev, _scorerSession);
                _scorerSession.PriorBar = prev;  // advance for next bar

                // P0-1: Compute zoneScore from ProfileAnchorLevels snapshot.
                var _zoneSnap = _profileAnchors.BuildSnapshot();
                double _zoneScore = ZoneScoreCalculator.Compute(prev.Close, _zoneSnap, TickSize);

                var scored = ConfluenceScorer.Score(
                    signals,
                    _scorerSession.BarsSinceOpen,
                    prev.BarDelta,
                    prev.Close,
                    zoneScore:        _zoneScore,
                    zoneDistTicks:    double.MaxValue,    // scorer uses zoneScore tier; dist not needed
                    tickSize:         TickSize,
                    gexAbsMult:       1.0,
                    gexMomentumMult:  1.0,
                    gexNearWallBonus: 0.0,
                    vpinModifier:     1.0);

                // Task 4: Attach raw signal array to scored result so DEEP6Strategy can access it
                // for strict directional agreement filter and VOLP-03 observation without a separate
                // shared-state slot. Null-safe: strategy EvaluateWithContext handles null signals.
                scored.Signals = signals;

                _lastScorerResult = scored;
                // Task 4: Publish with session average ATR so DEEP6Strategy slow-grind veto works.
                ScorerSharedState.Publish(Instrument.FullName, CurrentBar, scored, _scorerSession.SessionAvgAtr);

                // Draw tier marker for this bar (uses barsAgo=1 since prevIdx just closed).
                DrawScorerTierMarker(prevIdx, scored);
            }
            // ────────────────────────────────────────────────────────────────────────────────

            // Trim history.
            int cutoff = CurrentBar - 500;
            if (cutoff > 0)
            {
                var stale = _bars.Keys.Where(k => k < cutoff).ToList();
                foreach (var k in stale) _bars.Remove(k);
            }

        }

        private void DrawAbsorptionMarker(int barIdx, AbsorptionSignal s)
        {
            string tag = string.Format("ABS_{0}_{1}_{2}", barIdx, (int)s.Kind, s.Wick);
            Brush brush = s.Direction >= 0 ? Brushes.Cyan : Brushes.Magenta;
            int barsAgo = CurrentBar - barIdx;
            if (s.Direction >= 0)
                Draw.TriangleUp(this, tag, false, barsAgo, s.Price - 4 * TickSize, brush);
            else
                Draw.TriangleDown(this, tag, false, barsAgo, s.Price + 4 * TickSize, brush);
            Draw.Text(this, tag + "_lbl", s.Kind.ToString().Substring(0, Math.Min(3, s.Kind.ToString().Length)).ToUpper(),
                      barsAgo, s.Price + (s.Direction >= 0 ? -8 : 8) * TickSize, brush);
        }

        private void DrawExhaustionMarker(int barIdx, ExhaustionSignal s)
        {
            string tag = string.Format("EXH_{0}_{1}", barIdx, (int)s.Kind);
            Brush brush;
            if (s.Direction > 0) brush = Brushes.Yellow;
            else if (s.Direction < 0) brush = Brushes.OrangeRed;
            else brush = Brushes.SlateGray;
            int barsAgo = CurrentBar - barIdx;
            if (s.Direction > 0)
                Draw.ArrowUp(this, tag, false, barsAgo, s.Price - 5 * TickSize, brush);
            else if (s.Direction < 0)
                Draw.ArrowDown(this, tag, false, barsAgo, s.Price + 5 * TickSize, brush);
            else
                Draw.Diamond(this, tag, false, barsAgo, s.Price, brush);
        }

        // ---- Custom render ----

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            _bidDx        = BidCellBrush.ToDxBrush(RenderTarget);
            _askDx        = AskCellBrush.ToDxBrush(RenderTarget);
            _textDx       = CellTextBrush.ToDxBrush(RenderTarget);
            _imbalBuyDx   = ImbalanceBuyBrush.ToDxBrush(RenderTarget);
            _imbalSellDx  = ImbalanceSellBrush.ToDxBrush(RenderTarget);
            _pocDx        = PocBrush.ToDxBrush(RenderTarget);
            _vahDx        = VahBrush.ToDxBrush(RenderTarget);
            _valDx        = ValBrush.ToDxBrush(RenderTarget);
            _gridDx       = MakeFrozenBrush(Color.FromArgb(40, 200, 200, 200)).ToDxBrush(RenderTarget);
            _wallBidDx    = WallBidBrush.ToDxBrush(RenderTarget);
            _wallAskDx    = WallAskBrush.ToDxBrush(RenderTarget);

            // Profile anchor brushes
            _anchorPocDx       = (SharpDX.Direct2D1.SolidColorBrush)AnchorPocBrush.ToDxBrush(RenderTarget);
            _anchorVaDx        = (SharpDX.Direct2D1.SolidColorBrush)AnchorVaBrush.ToDxBrush(RenderTarget);
            _anchorNakedDx     = (SharpDX.Direct2D1.SolidColorBrush)AnchorNakedBrush.ToDxBrush(RenderTarget);
            _anchorPwPocDx     = (SharpDX.Direct2D1.SolidColorBrush)AnchorPwPocBrush.ToDxBrush(RenderTarget);
            _anchorCompositeDx = (SharpDX.Direct2D1.SolidColorBrush)AnchorCompositeBrush.ToDxBrush(RenderTarget);
            if (_dashStyle != null) { _dashStyle.Dispose(); _dashStyle = null; }
            _dashStyle = new StrokeStyle(NinjaTrader.Core.Globals.D2DFactory,
                new StrokeStyleProperties { DashStyle = DashStyle.Dash });
            _ctOnDx       = MakeFrozenBrush(Color.FromArgb(220, 50, 130, 75)).ToDxBrush(RenderTarget);
            _ctOffDx      = MakeFrozenBrush(Color.FromArgb(220, 35, 40, 50)).ToDxBrush(RenderTarget);
            _ctBorderDx   = MakeFrozenBrush(Color.FromArgb(255, 90, 100, 115)).ToDxBrush(RenderTarget);

            // Phase 18: Scorer HUD brushes — palette from 01-COLOR-PALETTE.md + FOOTPRINT-VISUAL-SPEC.md
            _scoreHudTextDx    = MakeFrozenBrush(Color.FromArgb(255, 0xE8, 0xEA, 0xED)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _scoreHudDimDx     = MakeFrozenBrush(Color.FromArgb(255, 0xB0, 0xB6, 0xBE)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _scoreHudBgDx      = MakeFrozenBrush(Color.FromArgb(199, 0x0E, 0x10, 0x14)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // ~78% alpha
            _scoreHudBorderDx  = MakeFrozenBrush(Color.FromArgb(255, 0x26, 0x26, 0x33)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _scoreTierALongDx  = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xE6, 0x76)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // tierA-long #00E676
            _scoreTierAShortDx = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x17, 0x44)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // tierA-short #FF1744
            _scoreTierBLongDx  = MakeFrozenBrush(Color.FromArgb(255, 0x66, 0xBB, 0x6A)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // tierB-long #66BB6A
            _scoreTierBShortDx = MakeFrozenBrush(Color.FromArgb(255, 0xEF, 0x53, 0x50)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // tierB-short #EF5350
            _scoreTierCLongDx  = MakeFrozenBrush(Color.FromArgb(178, 0x7C, 0xB3, 0x87)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // tierC-long  #7CB387 @70%
            _scoreTierCShortDx = MakeFrozenBrush(Color.FromArgb(178, 0xB8, 0x7C, 0x82)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // tierC-short #B87C82 @70%
            _scoreNeutralDx    = MakeFrozenBrush(Color.FromArgb(255, 0x8A, 0x92, 0x9E)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // axis.text #8A929E
            _scoreLabelBgDx    = MakeFrozenBrush(Color.FromArgb(153, 0x0E, 0x10, 0x14)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // hud-bg @60%

            // HUD fonts — Consolas 12pt for score (monospace), Segoe UI 9pt for narrative/tier
            _hudFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 12f)
            {
                TextAlignment      = TextAlignment.Leading,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
            _hudLabelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 9f)
            {
                TextAlignment      = TextAlignment.Leading,
                ParagraphAlignment = ParagraphAlignment.Center,
            };

            // Wire mouse handler once a render target exists (ChartControl is non-null here).
            if (!_ctMouseWired && ChartControl != null)
            {
                ChartControl.MouseDown += OnChartTraderMouseDown;
                _ctMouseWired = true;
            }

            _cellFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", CellFontSize)
            {
                TextAlignment = TextAlignment.Center,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
            _labelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 10f)
            {
                TextAlignment = TextAlignment.Trailing,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
            // Chart Trader button font — cached so RenderChartTrader doesn't allocate
            // 7 unmanaged TextFormat objects per frame at 60fps (~420 allocs/sec).
            _ctBtnFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 10f)
            {
                TextAlignment = TextAlignment.Center,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
        }

        private void DisposeDx()
        {
            DisposeBrush(ref _bidDx); DisposeBrush(ref _askDx); DisposeBrush(ref _textDx);
            DisposeBrush(ref _imbalBuyDx); DisposeBrush(ref _imbalSellDx);
            DisposeBrush(ref _pocDx); DisposeBrush(ref _vahDx); DisposeBrush(ref _valDx);
            DisposeBrush(ref _gridDx);
            DisposeBrush(ref _wallBidDx); DisposeBrush(ref _wallAskDx);
            DisposeBrush(ref _ctOnDx); DisposeBrush(ref _ctOffDx); DisposeBrush(ref _ctBorderDx);
            DisposeSolidBrush(ref _anchorPocDx); DisposeSolidBrush(ref _anchorVaDx);
            DisposeSolidBrush(ref _anchorNakedDx); DisposeSolidBrush(ref _anchorPwPocDx);
            DisposeSolidBrush(ref _anchorCompositeDx);
            if (_dashStyle != null) { _dashStyle.Dispose(); _dashStyle = null; }
            if (_cellFont != null) { _cellFont.Dispose(); _cellFont = null; }
            if (_labelFont != null) { _labelFont.Dispose(); _labelFont = null; }
            if (_ctBtnFont != null) { _ctBtnFont.Dispose(); _ctBtnFont = null; }
            if (_hudFont != null) { _hudFont.Dispose(); _hudFont = null; }
            if (_hudLabelFont != null) { _hudLabelFont.Dispose(); _hudLabelFont = null; }
            // Phase 18 scorer HUD brushes
            DisposeSolidBrush(ref _scoreHudTextDx);
            DisposeSolidBrush(ref _scoreHudDimDx);
            DisposeSolidBrush(ref _scoreHudBgDx);
            DisposeSolidBrush(ref _scoreHudBorderDx);
            DisposeSolidBrush(ref _scoreTierALongDx);
            DisposeSolidBrush(ref _scoreTierAShortDx);
            DisposeSolidBrush(ref _scoreTierBLongDx);
            DisposeSolidBrush(ref _scoreTierBShortDx);
            DisposeSolidBrush(ref _scoreTierCLongDx);
            DisposeSolidBrush(ref _scoreTierCShortDx);
            DisposeSolidBrush(ref _scoreNeutralDx);
            DisposeSolidBrush(ref _scoreLabelBgDx);
        }

        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush b) { if (b != null) { b.Dispose(); b = null; } }
        private static void DisposeSolidBrush(ref SharpDX.Direct2D1.SolidColorBrush b) { if (b != null) { b.Dispose(); b = null; } }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (RenderTarget == null || ChartBars == null) return;
            if (chartControl.Instrument == null) return;
            if (_cellFont == null) return;

            base.OnRender(chartControl, chartScale);
            RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

            double tickSize = chartControl.Instrument.MasterInstrument.TickSize;
            float panelRight = (float)(ChartPanel.X + ChartPanel.W);

            // Chart Trader toolbar (top-left, on top of cells but under entry cards)
            if (ShowChartTrader) RenderChartTrader();

            // Profile anchor levels (prior-day POC/VAH/VAL, PDH/PDL/PDM, naked POCs, prior-week POC)
            if (ShowProfileAnchors) RenderProfileAnchors(chartControl, chartScale, panelRight);

            // Liquidity Walls from Rithmic L2 — large persistent resting orders
            if (ShowLiquidityWalls)
                RenderLiquidityWalls(chartScale, panelRight);

            if (!ShowFootprintCells && !ShowPoc && !ShowValueArea) return;

            int barPaintW = chartControl.GetBarPaintWidth(ChartBars);
            int colW = Math.Max(CellColumnWidth, barPaintW);
            float rowH = (float)Math.Max(8, chartScale.GetPixelsForDistance(tickSize));

            int fromIdx = ChartBars.FromIndex;
            int toIdx = ChartBars.ToIndex;

            for (int barIdx = fromIdx; barIdx <= toIdx; barIdx++)
            {
                FootprintBar fbar;
                if (!_bars.TryGetValue(barIdx, out fbar)) continue;
                if (fbar.Levels.Count == 0) continue;

                int xCenter = chartControl.GetXByBarIndex(ChartBars, barIdx);
                float xLeft = xCenter - colW / 2f;

                long maxLevelVol = 0;
                foreach (var kv in fbar.Levels)
                {
                    long v = kv.Value.AskVol + kv.Value.BidVol;
                    if (v > maxLevelVol) maxLevelVol = v;
                }

                if (ShowFootprintCells)
                {
                    foreach (var kv in fbar.Levels)
                    {
                        double px = kv.Key;
                        var cell = kv.Value;
                        float yCenter = chartScale.GetYByValue(px);
                        float yTop = yCenter - rowH / 2f;
                        var rect = new RectangleF(xLeft, yTop, colW, rowH);

                        // Imbalance: diagonal ask-at-px vs bid-at-(px+tick), and mirror.
                        long diagBid = GetBid(fbar, px + tickSize);
                        long diagAsk = GetAsk(fbar, px - tickSize);
                        bool buyImbal  = cell.AskVol > 0 && cell.AskVol >= ImbalanceRatio * Math.Max(1, diagBid);
                        bool sellImbal = cell.BidVol > 0 && cell.BidVol >= ImbalanceRatio * Math.Max(1, diagAsk);
                        if (buyImbal)       RenderTarget.FillRectangle(rect, _imbalBuyDx);
                        else if (sellImbal) RenderTarget.FillRectangle(rect, _imbalSellDx);

                        string label = string.Format("{0} x {1}", cell.BidVol, cell.AskVol);
                        using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, label, _cellFont, colW, rowH))
                        {
                            RenderTarget.DrawTextLayout(new Vector2(xLeft, yTop), layout, _textDx);
                        }
                    }
                }

                // POC bar (horizontal tick at POC price spanning column width)
                if (ShowPoc && fbar.PocPrice > 0)
                {
                    float yPoc = chartScale.GetYByValue(fbar.PocPrice);
                    var pocRect = new RectangleF(xLeft, yPoc - 1, colW, 2);
                    RenderTarget.FillRectangle(pocRect, _pocDx);
                }

                // VAH/VAL (at this bar)
                if (ShowValueArea)
                {
                    var va = FootprintBar.ComputeValueArea(fbar, tickSize);
                    float yVah = chartScale.GetYByValue(va.vah);
                    float yVal = chartScale.GetYByValue(va.val);
                    RenderTarget.DrawLine(new Vector2(xLeft, yVah), new Vector2(xLeft + colW, yVah), _vahDx, 1f);
                    RenderTarget.DrawLine(new Vector2(xLeft, yVal), new Vector2(xLeft + colW, yVal), _valDx, 1f);
                }
            }

            // Phase 18: Scoring HUD badge — rendered LAST (highest Z per 03-SPATIAL-LAYOUT.md z-order #20)
            // Anchored top-right of panel below GEX status badge slot (Y+28).
            if (ShowScoreHud) RenderScoreHud(panelRight);
        }

        private static long GetBid(FootprintBar bar, double price)
        {
            Cell c; return bar.Levels.TryGetValue(price, out c) ? c.BidVol : 0;
        }
        private static long GetAsk(FootprintBar bar, double price)
        {
            Cell c; return bar.Levels.TryGetValue(price, out c) ? c.AskVol : 0;
        }

        // Renders the Chart Trader toolbar: 7 clickable on/off buttons in chart top-left.
        // Each button reflects the state of one indicator feature (Get) and toggles it on click (Set).
        // Lit (green) when on; dim when off. Click handling is in OnChartTraderMouseDown.
        private void RenderChartTrader()
        {
            if (_ctButtons == null || _ctOnDx == null || _ctOffDx == null || _ctBorderDx == null) return;

            const float btnW = 56f, btnH = 22f, gap = 4f;
            float x = (float)ChartPanel.X + 8;
            float y = (float)ChartPanel.Y + 8;

            for (int i = 0; i < _ctButtons.Count; i++)
            {
                var btn = _ctButtons[i];
                btn.Rect = new RectangleF(x, y, btnW, btnH);
                bool on = false;
                try { on = btn.Get(); } catch { }
                var fill = on ? _ctOnDx : _ctOffDx;
                RenderTarget.FillRectangle(btn.Rect, fill);
                RenderTarget.DrawRectangle(btn.Rect, _ctBorderDx, 1f);
                if (_ctBtnFont != null)
                {
                    using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                        btn.Label, _ctBtnFont, btnW, btnH))
                    {
                        RenderTarget.DrawTextLayout(new Vector2(x, y), layout, _textDx);
                    }
                }
                x += btnW + gap;
            }
        }

        // Hit-test the toolbar buttons; toggle the matching feature; force chart redraw.
        // Uses ChartControl.MouseDown wired in OnRenderTargetChanged (when the chart is fully constructed).
        private void OnChartTraderMouseDown(object sender, System.Windows.Input.MouseButtonEventArgs e)
        {
            if (!ShowChartTrader || _ctButtons == null) return;
            if (e.ChangedButton != System.Windows.Input.MouseButton.Left) return;
            if (ChartControl == null) return;

            var pos = e.GetPosition(ChartControl);
            for (int i = 0; i < _ctButtons.Count; i++)
            {
                var btn = _ctButtons[i];
                if (pos.X >= btn.Rect.Left && pos.X <= btn.Rect.Right &&
                    pos.Y >= btn.Rect.Top  && pos.Y <= btn.Rect.Bottom)
                {
                    bool cur = false;
                    try { cur = btn.Get(); } catch { }
                    btn.Set(!cur);
                    e.Handled = true;
                    // ForceRefresh() drives the SharpDX OnRender pipeline; InvalidateVisual()
                    // only triggers the WPF layer and won't repaint our SharpDX overlay.
                    try { ForceRefresh(); } catch { }
                    return;
                }
            }
        }

        // Renders prior-day POC/VAH/VAL, PDH/PDL/PDM, naked POCs, prior-week POC,
        // and optional composite VA band as full-width horizontal lines with right-gutter labels.
        // Colors per FOOTPRINT-VISUAL-SPEC.md §2 and planner notes at top of plan.
        private void RenderProfileAnchors(ChartControl cc, ChartScale cs, float panelRight)
        {
            if (_anchorPocDx == null || _anchorVaDx == null) return;

            var snap = _profileAnchors.BuildSnapshot();
            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;

            // Draw composite VA band first (lowest z-order among anchors — translucent fill)
            if (ShowCompositeVA && snap.CompositeVah.HasValue && snap.CompositeVal.HasValue && _anchorCompositeDx != null)
            {
                float yVah = cs.GetYByValue(snap.CompositeVah.Value);
                float yVal = cs.GetYByValue(snap.CompositeVal.Value);
                if (yVah >= 0 && yVal >= 0)
                {
                    float top  = System.Math.Min(yVah, yVal);
                    float bot  = System.Math.Max(yVah, yVal);
                    var rect = new RectangleF((float)ChartPanel.X, top, panelRight - (float)ChartPanel.X, bot - top);
                    RenderTarget.FillRectangle(rect, _anchorCompositeDx);
                }
            }

            foreach (var anchor in snap.Levels)
            {
                // Gate by user-facing toggles
                bool priorDayKind = anchor.Kind == ProfileAnchorKind.PriorDayPoc ||
                                    anchor.Kind == ProfileAnchorKind.PriorDayVah ||
                                    anchor.Kind == ProfileAnchorKind.PriorDayVal ||
                                    anchor.Kind == ProfileAnchorKind.Pdh         ||
                                    anchor.Kind == ProfileAnchorKind.Pdl         ||
                                    anchor.Kind == ProfileAnchorKind.Pdm;
                if (priorDayKind && !ShowPriorDayLevels) continue;
                if (anchor.Kind == ProfileAnchorKind.NakedPoc && !ShowNakedPocs) continue;
                if ((anchor.Kind == ProfileAnchorKind.CompositeVah ||
                     anchor.Kind == ProfileAnchorKind.CompositeVal) && !ShowCompositeVA) continue;

                double price = anchor.Price;
                if (price < minVis || price > maxVis) continue;

                float y = cs.GetYByValue(price);

                // Choose brush and stroke style
                SharpDX.Direct2D1.SolidColorBrush brush;
                StrokeStyle stroke;
                switch (anchor.Kind)
                {
                    case ProfileAnchorKind.PriorDayPoc:
                        brush = _anchorPocDx; stroke = null; break;
                    case ProfileAnchorKind.PriorDayVah:
                    case ProfileAnchorKind.PriorDayVal:
                    case ProfileAnchorKind.Pdh:
                    case ProfileAnchorKind.Pdl:
                    case ProfileAnchorKind.Pdm:
                        brush = _anchorVaDx; stroke = null; break;
                    case ProfileAnchorKind.NakedPoc:
                        brush = _anchorNakedDx; stroke = _dashStyle; break;
                    case ProfileAnchorKind.PriorWeekPoc:
                        brush = _anchorPwPocDx; stroke = _dashStyle; break;
                    case ProfileAnchorKind.CompositeVah:
                    case ProfileAnchorKind.CompositeVal:
                        brush = _anchorVaDx; stroke = null; break;
                    default:
                        brush = _anchorVaDx; stroke = null; break;
                }
                if (brush == null) continue;

                // Full-width horizontal line (1.5 px weight per plan)
                RenderTarget.DrawLine(
                    new Vector2((float)ChartPanel.X, y),
                    new Vector2(panelRight, y),
                    brush, 1.5f, stroke);

                // Right-gutter label: Segoe UI 9pt, right-aligned, 156×16 px
                if (_labelFont != null)
                {
                    string text = string.Format("{0} ({1:F2})", anchor.Label, price);
                    using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                       text, _labelFont, 156f, 16f))
                    {
                        RenderTarget.DrawTextLayout(new Vector2(panelRight - 160f, y - 8f), layout, brush);
                    }
                }
            }
        }

        // Renders Liquidity Walls (large persistent resting bids/asks from Rithmic L2).
        // Only shows top N walls per side ranked by max-size; only shows fresh walls (recent depth update);
        // line thickness scales with size; iceberg refills annotated with "ICE" tag.
        private void RenderLiquidityWalls(ChartScale cs, float panelRight)
        {
            if (_wallBidDx == null || _wallAskDx == null) return;
            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;
            DateTime fresh = DateTime.UtcNow.AddSeconds(-LiquidityWallStaleSec);

            // Deep-clone inside the lock — L2LevelState is a reference type with mutable long/DateTime
            // fields the data thread continues to write. Without cloning, render reads would race.
            List<KeyValuePair<double, L2LevelState>> bidSnap, askSnap;
            lock (_l2Lock)
            {
                bidSnap = new List<KeyValuePair<double, L2LevelState>>(_l2Bids.Count);
                foreach (var kv in _l2Bids)
                    bidSnap.Add(new KeyValuePair<double, L2LevelState>(kv.Key, new L2LevelState {
                        CurrentSize = kv.Value.CurrentSize, MaxSize = kv.Value.MaxSize,
                        LastUpdate = kv.Value.LastUpdate,   RefillCount = kv.Value.RefillCount }));
                askSnap = new List<KeyValuePair<double, L2LevelState>>(_l2Asks.Count);
                foreach (var kv in _l2Asks)
                    askSnap.Add(new KeyValuePair<double, L2LevelState>(kv.Key, new L2LevelState {
                        CurrentSize = kv.Value.CurrentSize, MaxSize = kv.Value.MaxSize,
                        LastUpdate = kv.Value.LastUpdate,   RefillCount = kv.Value.RefillCount }));
            }

            DrawWallsForSide(cs, bidSnap, _wallBidDx, "BID", true,  fresh, minVis, maxVis, panelRight);
            DrawWallsForSide(cs, askSnap, _wallAskDx, "ASK", false, fresh, minVis, maxVis, panelRight);
        }

        private void DrawWallsForSide(
            ChartScale cs,
            List<KeyValuePair<double, L2LevelState>> snap,
            SharpDX.Direct2D1.Brush brush,
            string side,
            bool isBid,
            DateTime fresh,
            double minVis,
            double maxVis,
            float panelRight)
        {
            // Filter eligible walls: meet size threshold, recently updated, in visible range.
            var walls = new List<KeyValuePair<double, L2LevelState>>();
            foreach (var kv in snap)
            {
                if (kv.Value.MaxSize < LiquidityWallMin) continue;
                if (kv.Value.LastUpdate < fresh) continue;
                if (kv.Key < minVis || kv.Key > maxVis) continue;
                walls.Add(kv);
            }
            // Top N by max-size.
            walls.Sort((a, b) => b.Value.MaxSize.CompareTo(a.Value.MaxSize));
            int show = Math.Min(walls.Count, LiquidityMaxPerSide);

            for (int i = 0; i < show; i++)
            {
                double price = walls[i].Key;
                var st = walls[i].Value;
                float y = (float)cs.GetYByValue(price);
                // Line thickness scales 1.5px → 4px based on size relative to threshold.
                float thickness = (float)Math.Min(4.0, 1.5 + (st.MaxSize / (double)LiquidityWallMin) * 0.4);
                RenderTarget.DrawLine(
                    new Vector2((float)ChartPanel.X, y),
                    new Vector2(panelRight - 90, y),
                    brush, thickness);

                string label = string.Format("{0} {1:F2}  {2}{3}",
                    side, price, st.MaxSize,
                    st.RefillCount >= 2 ? " ICE×" + st.RefillCount : "");
                using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                    label, _labelFont, 180f, 16f))
                {
                    RenderTarget.DrawTextLayout(new Vector2(panelRight - 184, y - 8), layout, brush);
                }
            }
        }

        // ── Phase 18: Scorer HUD + tier marker rendering helpers ─────────────────────────────

        /// <summary>
        /// Render the 3-line Scoring HUD badge anchored top-right of the chart panel.
        /// Anchored at: x = panelRight - 200, y = ChartPanel.Y + 28
        /// (GEX status badge from DEEP6GexLevels occupies y = 4..22; 28 keeps 6px gap per spec.)
        /// Per FOOTPRINT-VISUAL-SPEC.md section 6 + 03-SPATIAL-LAYOUT.md zone SCORE_HUD.
        /// </summary>
        private void RenderScoreHud(float panelRight)
        {
            if (_hudFont == null || _hudLabelFont == null) return;
            if (_scoreHudTextDx == null || _scoreHudBgDx == null) return;

            var r = _lastScorerResult;
            // Auto-hide when score=0 and tier is QUIET/null (no signal — per typography spec).
            if (r == null) return;
            if (r.TotalScore == 0.0 && (r.Tier == SignalTier.QUIET || r.Tier == SignalTier.DISQUALIFIED))
                return;

            const float hudW   = 200f;
            const float hudH   = 62f;
            float topY = (float)ChartPanel.Y + 28f;
            float leftX = panelRight - hudW;

            // Background rectangle
            var bgRect = new RectangleF(leftX, topY, hudW, hudH);
            RenderTarget.FillRectangle(bgRect, _scoreHudBgDx);
            RenderTarget.DrawRectangle(bgRect, _scoreHudBorderDx, 1f);

            float textX     = leftX + 8f;
            float lineH     = 18f;
            float textW     = hudW - 16f;

            // Line 1: "Score: +0.87"  (12pt Consolas, primary ink; red-tinted when negative)
            string scoreLine = string.Format("Score: {0:+0.00;-0.00;+0.00}", r.TotalScore / 100.0);
            var scoreInk = (r.TotalScore < 0) ? (SharpDX.Direct2D1.Brush)_scoreTierAShortDx
                                               : (SharpDX.Direct2D1.Brush)_scoreHudTextDx;
            using (var layout1 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                scoreLine, _hudFont, textW, lineH))
            {
                RenderTarget.DrawTextLayout(new Vector2(textX, topY + 6f), layout1, scoreInk);
            }

            // Line 2: "Tier: A" with tier-specific ink
            string tierLine = "Tier: " + TierChar(r.Tier);
            var tierInk = TierBrush(r.Tier, r.Direction);
            using (var layout2 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                tierLine, _hudLabelFont, textW, lineH))
            {
                RenderTarget.DrawTextLayout(new Vector2(textX, topY + 6f + lineH), layout2, tierInk);
            }

            // Line 3: Narrative (≤40 chars, ellipsis) — TypeA only per CONTEXT.md decision;
            // TypeB/C show blank line here (narrative goes to strategy log only).
            string narrative = (r.Tier == SignalTier.TYPE_A && r.Narrative != null)
                ? TruncateEllipsis(r.Narrative, 40)
                : string.Empty;
            if (narrative.Length > 0)
            {
                using (var layout3 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                    narrative, _hudLabelFont, textW, lineH))
                {
                    RenderTarget.DrawTextLayout(new Vector2(textX, topY + 6f + lineH * 2f), layout3, _scoreHudDimDx);
                }
            }
        }

        /// <summary>
        /// Draw a tier-coded entry marker for the given bar via NT8 Draw.* API.
        /// Called once per bar close in OnBarUpdate (Draw.* must NOT be called from OnRender).
        ///
        /// Marker placement (per FOOTPRINT-VISUAL-SPEC.md section 5):
        ///   Long signals: below bar low (further down than ABS/EXH at -4 ticks → use -8 ticks offset)
        ///   Short signals: above bar high (+8 ticks offset)
        ///
        /// Draw.Dot fallback per 18-RESEARCH.md Open Question 3: if NT8 lacks Draw.Dot, the
        /// catch handler renders a half-opacity Diamond for TypeC.
        /// </summary>
        private void DrawScorerTierMarker(int barIdx, ScorerResult scored)
        {
            if (scored == null) return;
            if (scored.Tier == SignalTier.QUIET || scored.Tier == SignalTier.DISQUALIFIED) return;
            if (scored.Direction == 0) return;

            int barsAgo = CurrentBar - barIdx;
            double entry = scored.EntryPrice > 0 ? scored.EntryPrice : Close[barsAgo];
            bool isLong = scored.Direction > 0;

            // Unique tag per bar per direction — NT8 Draw.* with same tag overwrites (idempotent on repaint).
            string suffix = (isLong ? "L" : "S") + "_" + barIdx;

            // Marker brushes: WPF brushes for Draw.* API (not SharpDX)
            Brush longBrush  = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xE6, 0x76));  // #00E676 TypeA long
            Brush shortBrush = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x17, 0x44));  // #FF1744 TypeA short
            Brush bLongB     = MakeFrozenBrush(Color.FromArgb(255, 0x66, 0xBB, 0x6A));  // #66BB6A TypeB long
            Brush bShortB    = MakeFrozenBrush(Color.FromArgb(255, 0xEF, 0x53, 0x50));  // #EF5350 TypeB short
            Brush cLongB     = MakeFrozenBrush(Color.FromArgb(178, 0x7C, 0xB3, 0x87));  // #7CB387 @70% TypeC long
            Brush cShortB    = MakeFrozenBrush(Color.FromArgb(178, 0xB8, 0x7C, 0x82));  // #B87C82 @70% TypeC short

            // Offset from bar geometry (ABS/EXH use 4–5 ticks; tier markers use 8 ticks to prevent collision)
            double offset = 8.0 * TickSize;

            switch (scored.Tier)
            {
                case SignalTier.TYPE_A:
                {
                    // TypeA: solid Diamond, fully saturated — shape encodes highest conviction.
                    Brush pick = isLong ? longBrush : shortBrush;
                    double markerPrice = isLong ? entry - offset : entry + offset;
                    Draw.Diamond(this, "SCORE_A_" + suffix, false, barsAgo, markerPrice, pick);

                    // TypeA narrative label (≤50 chars, ellipsis) adjacent to marker.
                    // Position: 4 more ticks beyond the diamond so text doesn't overlap the shape.
                    double lblPrice = isLong ? markerPrice - 4.0 * TickSize : markerPrice + 4.0 * TickSize;
                    string narrative = TruncateEllipsis(scored.Narrative ?? string.Empty, 50);
                    if (narrative.Length > 0)
                        Draw.Text(this, "SCORE_LBL_" + suffix, narrative, barsAgo, lblPrice, pick);
                    break;
                }
                case SignalTier.TYPE_B:
                {
                    // TypeB: hollow triangle pointing in entry direction, medium saturation.
                    Brush pick = isLong ? bLongB : bShortB;
                    double markerPrice = isLong ? entry - offset : entry + offset;
                    if (isLong)
                        Draw.TriangleUp(this, "SCORE_B_" + suffix, false, barsAgo, markerPrice, pick);
                    else
                        Draw.TriangleDown(this, "SCORE_B_" + suffix, false, barsAgo, markerPrice, pick);
                    break;
                }
                case SignalTier.TYPE_C:
                {
                    // TypeC: small dot if available, fallback to small Diamond at 70% opacity.
                    // Draw.Dot fallback per RESEARCH Open Question 3. If NT8 lacks Draw.Dot,
                    // the catch handler renders a half-opacity Diamond.
                    Brush pick = isLong ? cLongB : cShortB;
                    double markerPrice = isLong ? entry - offset : entry + offset;
                    try
                    {
                        Draw.Dot(this, "SCORE_C_" + suffix, false, barsAgo, markerPrice, pick);
                    }
                    catch (System.MissingMethodException)
                    {
                        Draw.Diamond(this, "SCORE_C_" + suffix, false, barsAgo, markerPrice, pick);
                    }
                    break;
                }
            }
        }

        /// <summary>Returns single-char tier label for HUD line 2.</summary>
        private static string TierChar(SignalTier tier)
        {
            switch (tier)
            {
                case SignalTier.TYPE_A: return "A";
                case SignalTier.TYPE_B: return "B";
                case SignalTier.TYPE_C: return "C";
                default:               return "-";
            }
        }

        /// <summary>
        /// Returns the appropriate SharpDX brush for the given tier + direction combination.
        /// Used by RenderScoreHud for tier line ink.
        /// </summary>
        private SharpDX.Direct2D1.Brush TierBrush(SignalTier tier, int direction)
        {
            switch (tier)
            {
                case SignalTier.TYPE_A:
                    return direction >= 0 ? (SharpDX.Direct2D1.Brush)_scoreTierALongDx
                                          : (SharpDX.Direct2D1.Brush)_scoreTierAShortDx;
                case SignalTier.TYPE_B:
                    return direction >= 0 ? (SharpDX.Direct2D1.Brush)_scoreTierBLongDx
                                          : (SharpDX.Direct2D1.Brush)_scoreTierBShortDx;
                case SignalTier.TYPE_C:
                    return direction >= 0 ? (SharpDX.Direct2D1.Brush)_scoreTierCLongDx
                                          : (SharpDX.Direct2D1.Brush)_scoreTierCShortDx;
                default:
                    return (SharpDX.Direct2D1.Brush)_scoreNeutralDx;
            }
        }

        /// <summary>Truncates text to maxLen chars, appending "..." if truncated.</summary>
        private static string TruncateEllipsis(string text, int maxLen)
        {
            if (text == null) return string.Empty;
            if (text.Length <= maxLen) return text;
            return text.Substring(0, maxLen - 3) + "...";
        }

        // ─────────────────────────────────────────────────────────────────────────────────────

        #region Properties

        [NinjaScriptProperty]
        [Range(1.0, 10.0)]
        [Display(Name = "Imbalance Ratio", Order = 1, GroupName = "1. Detection")]
        public double ImbalanceRatio { get; set; }

        [NinjaScriptProperty]
        [Range(5.0, 80.0)]
        [Display(Name = "Absorption Wick Min %", Order = 2, GroupName = "1. Detection")]
        public double AbsorbWickMinPct { get; set; }

        [NinjaScriptProperty]
        [Range(5.0, 80.0)]
        [Display(Name = "Exhaustion Wick Min %", Order = 3, GroupName = "1. Detection")]
        public double ExhaustWickMinPct { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Footprint Cells", Order = 10, GroupName = "2. Display")]
        public bool ShowFootprintCells { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show POC", Order = 11, GroupName = "2. Display")]
        public bool ShowPoc { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Value Area", Order = 12, GroupName = "2. Display")]
        public bool ShowValueArea { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Absorption Markers", Order = 13, GroupName = "2. Display")]
        public bool ShowAbsorptionMarkers { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Exhaustion Markers", Order = 14, GroupName = "2. Display")]
        public bool ShowExhaustionMarkers { get; set; }

        [NinjaScriptProperty]
        [Range(7f, 16f)]
        [Display(Name = "Cell Font Size", Order = 15, GroupName = "2. Display")]
        public float CellFontSize { get; set; }

        [NinjaScriptProperty]
        [Range(40, 200)]
        [Display(Name = "Cell Column Width (px)", Order = 16, GroupName = "2. Display")]
        public int CellColumnWidth { get; set; }

        // --- Profile Anchor Levels ---

        [NinjaScriptProperty]
        [Display(Name = "Show Profile Anchors", Order = 20, GroupName = "3. Profile Anchors")]
        public bool ShowProfileAnchors { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Prior-Day Levels", Order = 21, GroupName = "3. Profile Anchors")]
        public bool ShowPriorDayLevels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Naked POCs", Order = 22, GroupName = "3. Profile Anchors")]
        public bool ShowNakedPocs { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Composite 5-Day VA", Order = 23, GroupName = "3. Profile Anchors")]
        public bool ShowCompositeVA { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Naked POC Max Age (sessions)", Order = 24, GroupName = "3. Profile Anchors")]
        public int NakedPocMaxAgeSessions { get; set; }

        // Anchor brush properties

        [XmlIgnore]
        [Display(Name = "Anchor POC Color",       Order = 40, GroupName = "4. Colors")]
        public Brush AnchorPocBrush { get; set; }
        [Browsable(false)] public string AnchorPocBrushSerialize       { get { return Serialize.BrushToString(AnchorPocBrush); }       set { AnchorPocBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Anchor VA Color",        Order = 41, GroupName = "4. Colors")]
        public Brush AnchorVaBrush { get; set; }
        [Browsable(false)] public string AnchorVaBrushSerialize        { get { return Serialize.BrushToString(AnchorVaBrush); }        set { AnchorVaBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Anchor Naked POC Color", Order = 42, GroupName = "4. Colors")]
        public Brush AnchorNakedBrush { get; set; }
        [Browsable(false)] public string AnchorNakedBrushSerialize     { get { return Serialize.BrushToString(AnchorNakedBrush); }     set { AnchorNakedBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Anchor PW POC Color",    Order = 43, GroupName = "4. Colors")]
        public Brush AnchorPwPocBrush { get; set; }
        [Browsable(false)] public string AnchorPwPocBrushSerialize     { get { return Serialize.BrushToString(AnchorPwPocBrush); }     set { AnchorPwPocBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Anchor Composite VA",    Order = 44, GroupName = "4. Colors")]
        public Brush AnchorCompositeBrush { get; set; }
        [Browsable(false)] public string AnchorCompositeBrushSerialize { get { return Serialize.BrushToString(AnchorCompositeBrush); } set { AnchorCompositeBrush = Serialize.StringToBrush(value); } }

        [NinjaScriptProperty]
        [Display(Name = "Show Liquidity Walls (Rithmic L2)", Order = 30, GroupName = "5. Liquidity (L2)")]
        public bool ShowLiquidityWalls { get; set; }

        [NinjaScriptProperty]
        [Range(10, 5000)]
        [Display(Name = "Wall Min Size (contracts)", Order = 31, GroupName = "5. Liquidity (L2)")]
        public int LiquidityWallMin { get; set; }

        [NinjaScriptProperty]
        [Range(10, 600)]
        [Display(Name = "Wall Stale (seconds)", Order = 32, GroupName = "5. Liquidity (L2)",
                 Description = "Hide a wall if its price level hasn't seen a depth update in this many seconds")]
        public int LiquidityWallStaleSec { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Max Walls Per Side", Order = 33, GroupName = "5. Liquidity (L2)")]
        public int LiquidityMaxPerSide { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Chart Trader Toolbar", Order = 40, GroupName = "6. Chart Trader",
                 Description = "Top-left clickable on/off buttons for each feature so you can toggle live during trading")]
        public bool ShowChartTrader { get; set; }

        // --- Phase 18: Scorer HUD ---

        [NinjaScriptProperty]
        [Display(Name = "Show Score HUD", Order = 1, GroupName = "7. DEEP6 Scorer",
                 Description = "Display the 3-line scoring HUD badge (Score / Tier / Narrative) in the top-right corner")]
        public bool ShowScoreHud { get; set; }

        [NinjaScriptProperty]
        [Range(0, 100)]
        [Display(Name = "Score HUD Padding (px)", Order = 2, GroupName = "7. DEEP6 Scorer",
                 Description = "Horizontal padding between the right edge of the chart panel and the HUD badge")]
        public int ScoreHudPaddingPx { get; set; }

        // --- Brush properties (require *Serialize string companions for XML serialization) ---

        [XmlIgnore]
        [Display(Name = "Bid Cell Color",      Order = 30, GroupName = "4. Colors")]
        public Brush BidCellBrush { get; set; }
        [Browsable(false)] public string BidCellBrushSerialize     { get { return Serialize.BrushToString(BidCellBrush); }     set { BidCellBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Ask Cell Color",      Order = 31, GroupName = "4. Colors")]
        public Brush AskCellBrush { get; set; }
        [Browsable(false)] public string AskCellBrushSerialize     { get { return Serialize.BrushToString(AskCellBrush); }     set { AskCellBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Cell Text Color",     Order = 32, GroupName = "4. Colors")]
        public Brush CellTextBrush { get; set; }
        [Browsable(false)] public string CellTextBrushSerialize    { get { return Serialize.BrushToString(CellTextBrush); }    set { CellTextBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "POC Color",           Order = 33, GroupName = "4. Colors")]
        public Brush PocBrush { get; set; }
        [Browsable(false)] public string PocBrushSerialize         { get { return Serialize.BrushToString(PocBrush); }         set { PocBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "VAH Color",           Order = 34, GroupName = "4. Colors")]
        public Brush VahBrush { get; set; }
        [Browsable(false)] public string VahBrushSerialize         { get { return Serialize.BrushToString(VahBrush); }         set { VahBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "VAL Color",           Order = 35, GroupName = "4. Colors")]
        public Brush ValBrush { get; set; }
        [Browsable(false)] public string ValBrushSerialize         { get { return Serialize.BrushToString(ValBrush); }         set { ValBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Imbalance Buy Color", Order = 36, GroupName = "4. Colors")]
        public Brush ImbalanceBuyBrush { get; set; }
        [Browsable(false)] public string ImbalanceBuyBrushSerialize{ get { return Serialize.BrushToString(ImbalanceBuyBrush); }set { ImbalanceBuyBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Imbalance Sell Color",Order = 37, GroupName = "4. Colors")]
        public Brush ImbalanceSellBrush { get; set; }
        [Browsable(false)] public string ImbalanceSellBrushSerialize{ get { return Serialize.BrushToString(ImbalanceSellBrush); } set { ImbalanceSellBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Wall Bid (resting buy)",  Order = 50, GroupName = "4. Colors")]
        public Brush WallBidBrush { get; set; }
        [Browsable(false)] public string WallBidBrushSerialize { get { return Serialize.BrushToString(WallBidBrush); } set { WallBidBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Wall Ask (resting sell)", Order = 51, GroupName = "4. Colors")]
        public Brush WallAskBrush { get; set; }
        [Browsable(false)] public string WallAskBrushSerialize { get { return Serialize.BrushToString(WallAskBrush); } set { WallAskBrush = Serialize.StringToBrush(value); } }

        #endregion
    }
}
#region NinjaScript generated code. Neither change nor remove.
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6.DEEP6Footprint[] cacheDEEP6Footprint;
        public DEEP6.DEEP6Footprint DEEP6Footprint(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader)
        {
            return DEEP6Footprint(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader);
        }

        public DEEP6.DEEP6Footprint DEEP6Footprint(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader)
        {
            if (cacheDEEP6Footprint != null)
                for (int idx = 0; idx < cacheDEEP6Footprint.Length; idx++)
                    if (cacheDEEP6Footprint[idx] != null && cacheDEEP6Footprint[idx].ImbalanceRatio == imbalanceRatio && cacheDEEP6Footprint[idx].AbsorbWickMinPct == absorbWickMinPct && cacheDEEP6Footprint[idx].ExhaustWickMinPct == exhaustWickMinPct && cacheDEEP6Footprint[idx].ShowFootprintCells == showFootprintCells && cacheDEEP6Footprint[idx].ShowPoc == showPoc && cacheDEEP6Footprint[idx].ShowValueArea == showValueArea && cacheDEEP6Footprint[idx].ShowAbsorptionMarkers == showAbsorptionMarkers && cacheDEEP6Footprint[idx].ShowExhaustionMarkers == showExhaustionMarkers && cacheDEEP6Footprint[idx].CellFontSize == cellFontSize && cacheDEEP6Footprint[idx].CellColumnWidth == cellColumnWidth && cacheDEEP6Footprint[idx].ShowProfileAnchors == showProfileAnchors && cacheDEEP6Footprint[idx].ShowPriorDayLevels == showPriorDayLevels && cacheDEEP6Footprint[idx].ShowNakedPocs == showNakedPocs && cacheDEEP6Footprint[idx].ShowCompositeVA == showCompositeVA && cacheDEEP6Footprint[idx].NakedPocMaxAgeSessions == nakedPocMaxAgeSessions && cacheDEEP6Footprint[idx].ShowLiquidityWalls == showLiquidityWalls && cacheDEEP6Footprint[idx].LiquidityWallMin == liquidityWallMin && cacheDEEP6Footprint[idx].LiquidityWallStaleSec == liquidityWallStaleSec && cacheDEEP6Footprint[idx].LiquidityMaxPerSide == liquidityMaxPerSide && cacheDEEP6Footprint[idx].ShowChartTrader == showChartTrader && cacheDEEP6Footprint[idx].EqualsInput(input))
                        return cacheDEEP6Footprint[idx];
            return CacheIndicator<DEEP6.DEEP6Footprint>(new DEEP6.DEEP6Footprint() { ImbalanceRatio = imbalanceRatio, AbsorbWickMinPct = absorbWickMinPct, ExhaustWickMinPct = exhaustWickMinPct, ShowFootprintCells = showFootprintCells, ShowPoc = showPoc, ShowValueArea = showValueArea, ShowAbsorptionMarkers = showAbsorptionMarkers, ShowExhaustionMarkers = showExhaustionMarkers, CellFontSize = cellFontSize, CellColumnWidth = cellColumnWidth, ShowProfileAnchors = showProfileAnchors, ShowPriorDayLevels = showPriorDayLevels, ShowNakedPocs = showNakedPocs, ShowCompositeVA = showCompositeVA, NakedPocMaxAgeSessions = nakedPocMaxAgeSessions, ShowLiquidityWalls = showLiquidityWalls, LiquidityWallMin = liquidityWallMin, LiquidityWallStaleSec = liquidityWallStaleSec, LiquidityMaxPerSide = liquidityMaxPerSide, ShowChartTrader = showChartTrader }, input, ref cacheDEEP6Footprint);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6.DEEP6Footprint DEEP6Footprint(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader)
        {
            return indicator.DEEP6Footprint(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader);
        }

        public Indicators.DEEP6.DEEP6Footprint DEEP6Footprint(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader)
        {
            return indicator.DEEP6Footprint(input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader);
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.DEEP6.DEEP6Footprint DEEP6Footprint(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader)
        {
            return indicator.DEEP6Footprint(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader);
        }

        public Indicators.DEEP6.DEEP6Footprint DEEP6Footprint(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader)
        {
            return indicator.DEEP6Footprint(input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader);
        }
    }
}

#endregion
