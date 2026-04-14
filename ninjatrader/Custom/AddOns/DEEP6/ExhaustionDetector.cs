// DEEP6 Footprint — Exhaustion Detector
// Port of deep6/engines/exhaustion.py (lines 1-317) for NinjaTrader 8.
// Variants: EXH-01..06. Delta trajectory gate applies to EXH-02..06; EXH-01 (zero print) is gate-exempt.
// Cooldown state MUST be reset at session boundaries via ResetCooldowns().

using System;
using System.Collections.Generic;
using System.Linq;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6
{
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
}
