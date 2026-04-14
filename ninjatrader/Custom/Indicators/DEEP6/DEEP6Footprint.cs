// DEEP6 Footprint — unified NinjaTrader 8 indicator (single-file build).
//
// This file contains the entire DEEP6 Footprint indicator: the main indicator
// class, the FootprintBar / Cell data structures, AbsorptionDetector (4 variants
// + VAH/VAL bonus), ExhaustionDetector (6 variants + delta gate + cooldown),
// and the massive.com GEX client.
//
// Drop-in install: copy this file alone to
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
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
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

    // ─── from MassiveGexClient.cs ───
    public enum GexLevelKind
    {
        GammaFlip,
        CallWall,
        PutWall,
        MajorPositive,
        MajorNegative,
    }

    public sealed class GexLevel
    {
        public double Strike;
        public double GexNotional;   // signed $ per 1% move
        public GexLevelKind Kind;
        public string Label;
    }

    public sealed class GexProfile
    {
        public string Underlying;
        public double Spot;
        public double GammaFlip;
        public double CallWall;
        public double PutWall;
        public List<GexLevel> Levels = new List<GexLevel>();
        public DateTime FetchedUtc;

        public static GexProfile FromChain(string underlying, double spot, Dictionary<double, double> byStrike)
        {
            var profile = new GexProfile { Underlying = underlying, Spot = spot, FetchedUtc = DateTime.UtcNow };
            var sorted = byStrike.OrderBy(kv => kv.Key).ToList();

            // gamma flip = cumulative GEX zero-crossing (ascending strikes)
            double cum = 0.0;
            double flip = spot;
            bool found = false;
            foreach (var kv in sorted)
            {
                double prev = cum;
                cum += kv.Value;
                if (!found && ((prev <= 0 && cum > 0) || (prev >= 0 && cum < 0)))
                {
                    flip = kv.Key;
                    found = true;
                }
            }
            profile.GammaFlip = flip;

            double callWallStrike = spot, callWallVal = double.NegativeInfinity;
            double putWallStrike  = spot, putWallVal  = double.PositiveInfinity;
            foreach (var kv in sorted)
            {
                if (kv.Value > callWallVal) { callWallVal = kv.Value; callWallStrike = kv.Key; }
                if (kv.Value < putWallVal)  { putWallVal  = kv.Value; putWallStrike  = kv.Key; }
            }
            profile.CallWall = callWallStrike;
            profile.PutWall  = putWallStrike;

            // top 5 absolute GEX nodes as major positive / major negative
            var nodes = sorted
                .OrderByDescending(kv => Math.Abs(kv.Value))
                .Take(8)
                .ToList();
            foreach (var kv in nodes)
            {
                GexLevelKind kind;
                if (Math.Abs(kv.Key - flip) < 1e-6) kind = GexLevelKind.GammaFlip;
                else if (Math.Abs(kv.Key - callWallStrike) < 1e-6) kind = GexLevelKind.CallWall;
                else if (Math.Abs(kv.Key - putWallStrike) < 1e-6) kind = GexLevelKind.PutWall;
                else if (kv.Value > 0) kind = GexLevelKind.MajorPositive;
                else kind = GexLevelKind.MajorNegative;

                profile.Levels.Add(new GexLevel
                {
                    Strike = kv.Key,
                    GexNotional = kv.Value,
                    Kind = kind,
                    Label = string.Format("{0} {1:F0}", KindLabel(kind), kv.Key),
                });
            }
            return profile;
        }

        private static string KindLabel(GexLevelKind k)
        {
            switch (k)
            {
                case GexLevelKind.GammaFlip: return "FLIP";
                case GexLevelKind.CallWall:  return "CALL WALL";
                case GexLevelKind.PutWall:   return "PUT WALL";
                case GexLevelKind.MajorPositive: return "+GEX";
                case GexLevelKind.MajorNegative: return "-GEX";
                default: return "GEX";
            }
        }
    }

    public sealed class MassiveGexClient : IDisposable
    {
        private readonly HttpClient _http;
        private readonly string _apiKey;
        private readonly string _baseUrl;

        public MassiveGexClient(string apiKey, string baseUrl = "https://api.massive.com")
        {
            _apiKey = apiKey ?? throw new ArgumentNullException("apiKey");
            _baseUrl = baseUrl.TrimEnd('/');

            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            _http = new HttpClient
            {
                BaseAddress = new Uri(_baseUrl),
                Timeout = TimeSpan.FromSeconds(8),
            };
            _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);
            _http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            _http.DefaultRequestHeaders.UserAgent.ParseAdd("DEEP6-NT8/1.0");
        }

        // Aggregates chain gamma × OI × 100 × spot² × 0.01 × sign(call=+1, put=-1) per strike.
        // Throws on HTTP/parse failure with a descriptive message — caller catches and Prints.
        public async Task<GexProfile> FetchAsync(string underlying, CancellationToken ct = default(CancellationToken))
        {
            var byStrike = new Dictionary<double, double>();
            double spot = 0;
            int contractsParsed = 0;
            string url = string.Format("/v3/snapshot/options/{0}?limit=250", underlying);
            int safetyPages = 0;

            while (!string.IsNullOrEmpty(url) && safetyPages < 20)
            {
                safetyPages++;
                var req = new HttpRequestMessage(HttpMethod.Get, url);
                var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
                if (!resp.IsSuccessStatusCode)
                {
                    string body = string.Empty;
                    try { body = await resp.Content.ReadAsStringAsync().ConfigureAwait(false); } catch { }
                    if (body.Length > 200) body = body.Substring(0, 200);
                    throw new HttpRequestException(string.Format("HTTP {0} {1} for {2}. Body: {3}",
                        (int)resp.StatusCode, resp.StatusCode, url, body));
                }
                var json = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);

                string nextUrl = ExtractStringField(json, "next_url");
                foreach (var obj in ExtractResultObjects(json))
                {
                    int openInterest = ExtractIntField(obj, "open_interest");
                    if (openInterest <= 0) continue;
                    double gamma = ExtractDoubleField(obj, "gamma");
                    if (gamma == 0) continue;
                    double strike = ExtractDoubleField(obj, "strike_price");
                    if (strike == 0) continue;
                    string ctype = ExtractStringField(obj, "contract_type");
                    if (string.IsNullOrEmpty(ctype)) continue;
                    double localSpot = ExtractDoubleFieldInside(obj, "underlying_asset", "price");
                    if (localSpot > 0) spot = localSpot;
                    double sign = string.Equals(ctype, "call", StringComparison.OrdinalIgnoreCase) ? +1.0 : -1.0;
                    double gex = gamma * openInterest * 100.0 * spot * spot * 0.01 * sign;
                    double acc;
                    byStrike.TryGetValue(strike, out acc);
                    byStrike[strike] = acc + gex;
                    contractsParsed++;
                }
                url = nextUrl;
                if (!string.IsNullOrEmpty(url) && url.StartsWith(_baseUrl)) url = url.Substring(_baseUrl.Length);
            }

            if (spot == 0 || byStrike.Count == 0)
                throw new InvalidOperationException(string.Format(
                    "Parsed {0} contracts but spot={1}, strikes={2}. Likely API returned empty results array — verify symbol '{3}' and that your massive.com plan covers options chain snapshots.",
                    contractsParsed, spot, byStrike.Count, underlying));
            return GexProfile.FromChain(underlying, spot, byStrike);
        }

        public void Dispose() { _http.Dispose(); }

        // ---- Minimal JSON field extraction (no System.Runtime.Serialization dependency) ----

        private static IEnumerable<string> ExtractResultObjects(string json)
        {
            // Locate "results": [...] and yield each top-level object in that array.
            int arrIdx = json.IndexOf("\"results\"");
            if (arrIdx < 0) yield break;
            int arrStart = json.IndexOf('[', arrIdx);
            if (arrStart < 0) yield break;

            int i = arrStart + 1;
            int n = json.Length;
            while (i < n)
            {
                // Skip whitespace and commas
                while (i < n && (json[i] == ' ' || json[i] == '\t' || json[i] == '\n' || json[i] == '\r' || json[i] == ',')) i++;
                if (i >= n) break;
                if (json[i] == ']') yield break;
                if (json[i] != '{') { i++; continue; }

                int start = i;
                int depth = 0;
                bool inStr = false;
                bool esc = false;
                for (; i < n; i++)
                {
                    char c = json[i];
                    if (esc) { esc = false; continue; }
                    if (inStr)
                    {
                        if (c == '\\') esc = true;
                        else if (c == '"') inStr = false;
                        continue;
                    }
                    if (c == '"') { inStr = true; continue; }
                    if (c == '{') depth++;
                    else if (c == '}')
                    {
                        depth--;
                        if (depth == 0) { i++; break; }
                    }
                }
                yield return json.Substring(start, i - start);
            }
        }

        private static string ExtractStringField(string json, string field)
        {
            var m = Regex.Match(json, "\"" + Regex.Escape(field) + "\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"");
            return m.Success ? Regex.Unescape(m.Groups[1].Value) : string.Empty;
        }

        private static int ExtractIntField(string json, string field)
        {
            var m = Regex.Match(json, "\"" + Regex.Escape(field) + "\"\\s*:\\s*(-?\\d+)");
            if (!m.Success) return 0;
            int v;
            return int.TryParse(m.Groups[1].Value, System.Globalization.NumberStyles.Integer,
                System.Globalization.CultureInfo.InvariantCulture, out v) ? v : 0;
        }

        private static double ExtractDoubleField(string json, string field)
        {
            var m = Regex.Match(json, "\"" + Regex.Escape(field) + "\"\\s*:\\s*(-?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?)");
            if (!m.Success) return 0.0;
            double v;
            return double.TryParse(m.Groups[1].Value, System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out v) ? v : 0.0;
        }

        // Extract a double from a named sub-object: {"outer": {"inner": 123.45}}
        private static double ExtractDoubleFieldInside(string json, string outer, string inner)
        {
            var m = Regex.Match(json, "\"" + Regex.Escape(outer) + "\"\\s*:\\s*\\{([^{}]*)\\}");
            return m.Success ? ExtractDoubleField(m.Groups[1].Value, inner) : 0.0;
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

        // GEX
        private MassiveGexClient _gexClient;
        private volatile GexProfile _gexProfile;
        private DateTime _lastGexFetch = DateTime.MinValue;
        private readonly TimeSpan _gexInterval = TimeSpan.FromMinutes(2);
        private CancellationTokenSource _gexCts;
        // Status string updated through every fetch path; visible at top-right of chart and in NT8 Output Window.
        private volatile string _gexStatus = "GEX: idle (no key)";

        // session reset tracking
        private DateTime _lastSessionDate = DateTime.MinValue;

        // SharpDX brushes (device-dependent)
        private SharpDX.Direct2D1.Brush _bidDx, _askDx, _textDx, _imbalBuyDx, _imbalSellDx,
                                         _pocDx, _vahDx, _valDx, _gexFlipDx, _gexCallWallDx,
                                         _gexPutWallDx, _gexPosDx, _gexNegDx, _gridDx,
                                         _wallBidDx, _wallAskDx;
        private TextFormat _cellFont, _labelFont;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description         = "DEEP6 Footprint — per-bar footprint with absorption/exhaustion markers and GEX overlay.";
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
                ShowGexLevels           = true;
                GexUnderlying           = "QQQ";
                GexApiKey               = string.Empty;
                AbsorbWickMinPct        = 30.0;
                ExhaustWickMinPct       = 35.0;
                CellFontSize            = 9f;
                CellColumnWidth         = 80;
                ShowLiquidityWalls      = true;
                LiquidityWallMin        = 100;
                LiquidityWallStaleSec   = 90;
                LiquidityMaxPerSide     = 4;

                BidCellBrush      = Brushes.IndianRed;
                AskCellBrush      = Brushes.LimeGreen;
                CellTextBrush     = Brushes.WhiteSmoke;
                PocBrush          = Brushes.Gold;
                VahBrush          = MakeFrozenBrush(Color.FromRgb(160, 200, 255));
                ValBrush          = MakeFrozenBrush(Color.FromRgb(160, 200, 255));
                ImbalanceBuyBrush = MakeFrozenBrush(Color.FromArgb(110, 0, 200, 80));
                ImbalanceSellBrush= MakeFrozenBrush(Color.FromArgb(110, 220, 40, 40));
                GexFlipBrush      = Brushes.Yellow;
                GexCallWallBrush  = Brushes.LimeGreen;
                GexPutWallBrush   = Brushes.OrangeRed;
                GexPositiveBrush  = MakeFrozenBrush(Color.FromArgb(180, 0, 180, 120));
                GexNegativeBrush  = MakeFrozenBrush(Color.FromArgb(180, 200, 70, 70));
                WallBidBrush      = MakeFrozenBrush(Color.FromArgb(220, 43, 140, 255));   // bright blue
                WallAskBrush      = MakeFrozenBrush(Color.FromArgb(220, 255, 138, 61));   // warm orange
            }
            else if (State == State.Configure)
            {
                _absCfg.AbsorbWickMin  = AbsorbWickMinPct;
                _exhCfg.ExhaustWickMin = ExhaustWickMinPct;
            }
            else if (State == State.DataLoaded)
            {
                _bars.Clear();
                _exhDetector.ResetCooldowns();
                _atrWindow.Clear();
                _volEma = 0.0;
                _priorCvd = 0;
                _priorFinalized = null;

                if (!ShowGexLevels)
                {
                    _gexStatus = "GEX: disabled";
                }
                else if (string.IsNullOrWhiteSpace(GexApiKey))
                {
                    _gexStatus = "GEX: NO API KEY (set in indicator properties)";
                    Print("[DEEP6] GEX disabled — set massive.com API key in indicator properties.");
                }
                else
                {
                    _gexClient = new MassiveGexClient(GexApiKey);
                    _gexCts = new CancellationTokenSource();
                    _gexStatus = "GEX: initializing — first fetch in progress";
                    Print("[DEEP6] GEX client initialized. Fetching " + GexUnderlying + " chain from massive.com…");
                    // Force first fetch immediately instead of waiting 2 minutes.
                    _lastGexFetch = DateTime.MinValue;
                }
            }
            else if (State == State.Terminated)
            {
                if (_gexCts != null) { try { _gexCts.Cancel(); } catch { } }
                if (_gexClient != null) { _gexClient.Dispose(); _gexClient = null; }
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

            // Trim history.
            int cutoff = CurrentBar - 500;
            if (cutoff > 0)
            {
                var stale = _bars.Keys.Where(k => k < cutoff).ToList();
                foreach (var k in stale) _bars.Remove(k);
            }

            // Kick GEX fetch if due.
            MaybeFetchGex();
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

        // ---- GEX fetch ----

        private void MaybeFetchGex()
        {
            if (_gexClient == null) return;
            if (DateTime.UtcNow - _lastGexFetch < _gexInterval) return;
            _lastGexFetch = DateTime.UtcNow;

            var ctsTok = _gexCts == null ? CancellationToken.None : _gexCts.Token;
            var client = _gexClient;
            var underlying = GexUnderlying;
            var indicator = this;

            _gexStatus = "GEX: fetching " + underlying + "…";
            Print("[DEEP6] GEX fetch start: " + underlying + " @ " + DateTime.Now.ToString("HH:mm:ss"));

            Task.Run(async () =>
            {
                try
                {
                    var profile = await client.FetchAsync(underlying, ctsTok).ConfigureAwait(false);
                    if (profile != null && profile.Levels.Count > 0)
                    {
                        indicator._gexProfile = profile;
                        indicator._gexStatus = "GEX: " + profile.Levels.Count + " levels @ " + DateTime.Now.ToString("HH:mm");
                        indicator.Print("[DEEP6] GEX OK: " + profile.Levels.Count + " levels, spot " + profile.Spot.ToString("F2") + ", flip " + profile.GammaFlip.ToString("F2"));
                    }
                    else
                    {
                        indicator._gexStatus = "GEX: empty response (check API key, plan, underlying)";
                        indicator.Print("[DEEP6] GEX FAIL: empty response. Verify (1) API key valid, (2) plan covers options chain snapshot, (3) underlying '" + underlying + "' exists, (4) auth header is Bearer.");
                    }
                }
                catch (Exception ex)
                {
                    indicator._gexStatus = "GEX: ERROR " + ex.GetType().Name;
                    indicator.Print("[DEEP6] GEX EXCEPTION: " + ex.GetType().Name + " — " + ex.Message);
                }
            });
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
            _gexFlipDx    = GexFlipBrush.ToDxBrush(RenderTarget);
            _gexCallWallDx= GexCallWallBrush.ToDxBrush(RenderTarget);
            _gexPutWallDx = GexPutWallBrush.ToDxBrush(RenderTarget);
            _gexPosDx     = GexPositiveBrush.ToDxBrush(RenderTarget);
            _gexNegDx     = GexNegativeBrush.ToDxBrush(RenderTarget);
            _wallBidDx    = WallBidBrush.ToDxBrush(RenderTarget);
            _wallAskDx    = WallAskBrush.ToDxBrush(RenderTarget);

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
        }

        private void DisposeDx()
        {
            DisposeBrush(ref _bidDx); DisposeBrush(ref _askDx); DisposeBrush(ref _textDx);
            DisposeBrush(ref _imbalBuyDx); DisposeBrush(ref _imbalSellDx);
            DisposeBrush(ref _pocDx); DisposeBrush(ref _vahDx); DisposeBrush(ref _valDx);
            DisposeBrush(ref _gridDx);
            DisposeBrush(ref _gexFlipDx); DisposeBrush(ref _gexCallWallDx); DisposeBrush(ref _gexPutWallDx);
            DisposeBrush(ref _gexPosDx); DisposeBrush(ref _gexNegDx);
            DisposeBrush(ref _wallBidDx); DisposeBrush(ref _wallAskDx);
            if (_cellFont != null) { _cellFont.Dispose(); _cellFont = null; }
            if (_labelFont != null) { _labelFont.Dispose(); _labelFont = null; }
        }

        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush b) { if (b != null) { b.Dispose(); b = null; } }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (RenderTarget == null || ChartBars == null) return;
            if (chartControl.Instrument == null) return;
            if (_cellFont == null) return;

            base.OnRender(chartControl, chartScale);
            RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

            double tickSize = chartControl.Instrument.MasterInstrument.TickSize;
            float panelRight = (float)(ChartPanel.X + ChartPanel.W);

            // GEX status badge in top-right corner — always visible so the user knows
            // why levels are/aren't rendering. Color: green=OK, red=ERROR/NO KEY, gray=disabled.
            {
                string status = _gexStatus ?? string.Empty;
                if (!string.IsNullOrEmpty(status))
                {
                    SharpDX.Direct2D1.Brush statusBrush;
                    if (status.IndexOf("ERROR", StringComparison.Ordinal) >= 0 ||
                        status.IndexOf("NO API KEY", StringComparison.Ordinal) >= 0 ||
                        status.IndexOf("empty", StringComparison.Ordinal) >= 0)
                        statusBrush = _gexPutWallDx;
                    else if (status.IndexOf("levels", StringComparison.Ordinal) >= 0)
                        statusBrush = _gexCallWallDx;
                    else
                        statusBrush = _textDx;

                    using (var statusLayout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                              status, _labelFont, 380f, 18f))
                    {
                        RenderTarget.DrawTextLayout(
                            new Vector2(panelRight - 384, (float)ChartPanel.Y + 4),
                            statusLayout, statusBrush);
                    }
                }
            }

            // GEX horizontal levels first (behind everything)
            if (ShowGexLevels && _gexProfile != null)
                RenderGex(_gexProfile, chartControl, chartScale, panelRight);

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
        }

        private static long GetBid(FootprintBar bar, double price)
        {
            Cell c; return bar.Levels.TryGetValue(price, out c) ? c.BidVol : 0;
        }
        private static long GetAsk(FootprintBar bar, double price)
        {
            Cell c; return bar.Levels.TryGetValue(price, out c) ? c.AskVol : 0;
        }

        private void RenderGex(GexProfile gex, ChartControl cc, ChartScale cs, float panelRight)
        {
            // Note: GEX strikes are in the underlying's price space (QQQ),
            // but our chart is NQ. Map QQQ → NQ via a simple multiplier inferred
            // from spot ratio. This is a rough visual overlay, not a tradeable level.
            double nqSpot = (Bars != null && Bars.Count > 0) ? Bars.GetClose(Bars.Count - 1) : 0;
            double qqqSpot = gex.Spot;
            if (nqSpot <= 0 || qqqSpot <= 0) return;
            double mult = nqSpot / qqqSpot;

            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;

            foreach (var lv in gex.Levels)
            {
                double mapped = lv.Strike * mult;
                if (mapped < minVis || mapped > maxVis) continue;

                SharpDX.Direct2D1.Brush brush;
                float width;
                switch (lv.Kind)
                {
                    case GexLevelKind.GammaFlip: brush = _gexFlipDx;     width = 2.0f; break;
                    case GexLevelKind.CallWall:  brush = _gexCallWallDx; width = 1.8f; break;
                    case GexLevelKind.PutWall:   brush = _gexPutWallDx;  width = 1.8f; break;
                    case GexLevelKind.MajorPositive: brush = _gexPosDx;  width = 0.8f; break;
                    default: brush = _gexNegDx; width = 0.8f; break;
                }
                float y = cs.GetYByValue(mapped);
                RenderTarget.DrawLine(new Vector2((float)ChartPanel.X, y),
                                      new Vector2(panelRight, y), brush, width);

                string label = string.Format("{0} ({1:F2})", lv.Label, mapped);
                var lblRect = new RectangleF(panelRight - 160, y - 8, 156, 16);
                using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, label, _labelFont, 156, 16))
                {
                    RenderTarget.DrawTextLayout(new Vector2(panelRight - 160, y - 8), layout, brush);
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

            List<KeyValuePair<double, L2LevelState>> bidSnap, askSnap;
            lock (_l2Lock)
            {
                bidSnap = new List<KeyValuePair<double, L2LevelState>>(_l2Bids);
                askSnap = new List<KeyValuePair<double, L2LevelState>>(_l2Asks);
            }

            DrawWallsForSide(bidSnap, _wallBidDx, "BID", true,  fresh, minVis, maxVis, panelRight);
            DrawWallsForSide(askSnap, _wallAskDx, "ASK", false, fresh, minVis, maxVis, panelRight);
        }

        private void DrawWallsForSide(
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

        [NinjaScriptProperty]
        [Display(Name = "Show GEX Levels", Order = 20, GroupName = "3. GEX (massive.com)")]
        public bool ShowGexLevels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "GEX Underlying (QQQ/NDX)", Order = 21, GroupName = "3. GEX (massive.com)")]
        public string GexUnderlying { get; set; }

        [NinjaScriptProperty]
        [PasswordPropertyText(true)]
        [Display(Name = "massive.com API Key", Order = 22, GroupName = "3. GEX (massive.com)")]
        public string GexApiKey { get; set; }

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
        [Display(Name = "GEX Flip",            Order = 40, GroupName = "4. Colors")]
        public Brush GexFlipBrush { get; set; }
        [Browsable(false)] public string GexFlipBrushSerialize     { get { return Serialize.BrushToString(GexFlipBrush); }     set { GexFlipBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX Call Wall",       Order = 41, GroupName = "4. Colors")]
        public Brush GexCallWallBrush { get; set; }
        [Browsable(false)] public string GexCallWallBrushSerialize { get { return Serialize.BrushToString(GexCallWallBrush); } set { GexCallWallBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX Put Wall",        Order = 42, GroupName = "4. Colors")]
        public Brush GexPutWallBrush { get; set; }
        [Browsable(false)] public string GexPutWallBrushSerialize  { get { return Serialize.BrushToString(GexPutWallBrush); }  set { GexPutWallBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX + Nodes",         Order = 43, GroupName = "4. Colors")]
        public Brush GexPositiveBrush { get; set; }
        [Browsable(false)] public string GexPositiveBrushSerialize { get { return Serialize.BrushToString(GexPositiveBrush); } set { GexPositiveBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX - Nodes",         Order = 44, GroupName = "4. Colors")]
        public Brush GexNegativeBrush { get; set; }
        [Browsable(false)] public string GexNegativeBrushSerialize { get { return Serialize.BrushToString(GexNegativeBrush); } set { GexNegativeBrush = Serialize.StringToBrush(value); } }

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
        public DEEP6.DEEP6Footprint DEEP6Footprint(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showGexLevels, string gexUnderlying, string gexApiKey, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide)
        {
            return DEEP6Footprint(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showGexLevels, gexUnderlying, gexApiKey, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide);
        }

        public DEEP6.DEEP6Footprint DEEP6Footprint(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showGexLevels, string gexUnderlying, string gexApiKey, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide)
        {
            if (cacheDEEP6Footprint != null)
                for (int idx = 0; idx < cacheDEEP6Footprint.Length; idx++)
                    if (cacheDEEP6Footprint[idx] != null && cacheDEEP6Footprint[idx].ImbalanceRatio == imbalanceRatio && cacheDEEP6Footprint[idx].AbsorbWickMinPct == absorbWickMinPct && cacheDEEP6Footprint[idx].ExhaustWickMinPct == exhaustWickMinPct && cacheDEEP6Footprint[idx].ShowFootprintCells == showFootprintCells && cacheDEEP6Footprint[idx].ShowPoc == showPoc && cacheDEEP6Footprint[idx].ShowValueArea == showValueArea && cacheDEEP6Footprint[idx].ShowAbsorptionMarkers == showAbsorptionMarkers && cacheDEEP6Footprint[idx].ShowExhaustionMarkers == showExhaustionMarkers && cacheDEEP6Footprint[idx].CellFontSize == cellFontSize && cacheDEEP6Footprint[idx].CellColumnWidth == cellColumnWidth && cacheDEEP6Footprint[idx].ShowGexLevels == showGexLevels && cacheDEEP6Footprint[idx].GexUnderlying == gexUnderlying && cacheDEEP6Footprint[idx].GexApiKey == gexApiKey && cacheDEEP6Footprint[idx].ShowLiquidityWalls == showLiquidityWalls && cacheDEEP6Footprint[idx].LiquidityWallMin == liquidityWallMin && cacheDEEP6Footprint[idx].LiquidityWallStaleSec == liquidityWallStaleSec && cacheDEEP6Footprint[idx].LiquidityMaxPerSide == liquidityMaxPerSide && cacheDEEP6Footprint[idx].EqualsInput(input))
                        return cacheDEEP6Footprint[idx];
            return CacheIndicator<DEEP6.DEEP6Footprint>(new DEEP6.DEEP6Footprint() { ImbalanceRatio = imbalanceRatio, AbsorbWickMinPct = absorbWickMinPct, ExhaustWickMinPct = exhaustWickMinPct, ShowFootprintCells = showFootprintCells, ShowPoc = showPoc, ShowValueArea = showValueArea, ShowAbsorptionMarkers = showAbsorptionMarkers, ShowExhaustionMarkers = showExhaustionMarkers, CellFontSize = cellFontSize, CellColumnWidth = cellColumnWidth, ShowGexLevels = showGexLevels, GexUnderlying = gexUnderlying, GexApiKey = gexApiKey, ShowLiquidityWalls = showLiquidityWalls, LiquidityWallMin = liquidityWallMin, LiquidityWallStaleSec = liquidityWallStaleSec, LiquidityMaxPerSide = liquidityMaxPerSide }, input, ref cacheDEEP6Footprint);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6.DEEP6Footprint DEEP6Footprint(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showGexLevels, string gexUnderlying, string gexApiKey, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide)
        {
            return indicator.DEEP6Footprint(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showGexLevels, gexUnderlying, gexApiKey, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide);
        }

        public Indicators.DEEP6.DEEP6Footprint DEEP6Footprint(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showGexLevels, string gexUnderlying, string gexApiKey, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide)
        {
            return indicator.DEEP6Footprint(input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showGexLevels, gexUnderlying, gexApiKey, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide);
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.DEEP6.DEEP6Footprint DEEP6Footprint(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showGexLevels, string gexUnderlying, string gexApiKey, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide)
        {
            return indicator.DEEP6Footprint(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showGexLevels, gexUnderlying, gexApiKey, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide);
        }

        public Indicators.DEEP6.DEEP6Footprint DEEP6Footprint(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showGexLevels, string gexUnderlying, string gexApiKey, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide)
        {
            return indicator.DEEP6Footprint(input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showGexLevels, gexUnderlying, gexApiKey, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide);
        }
    }
}

#endregion
