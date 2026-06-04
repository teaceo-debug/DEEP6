// LiquidityDetectorTests.cs — TDD tests for 6 detectors:
// IMB-01, ICE-01, LIQSW-01, FAIL-01, TRAP-01, REG-01
// Uses test-local type copies to avoid NT8 runtime dependencies.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using SysMath = System.Math;

namespace NinjaTrader.Tests.MADConfluenceAI.LiquidityDetectors
{
    // ── Test-local type copies ──────────────────────────────────────────

    public enum MADSignalDirection { Long, Short, Neutral }
    public enum MADTrend { Bullish, Bearish, Neutral }

    public sealed class MADSignalResult
    {
        public string SignalId;
        public MADSignalDirection Direction;
        public double Strength;
        public string Detail;
        public double Price;
    }

    public sealed class MADCell
    {
        public long BidVol;
        public long AskVol;
        public long NeutralVol;
        public long Delta => AskVol - BidVol;
        public long TotalVol => AskVol + BidVol + NeutralVol;
        public double ImbalanceRatio
        {
            get
            {
                if (BidVol == 0 && AskVol == 0) return 1.0;
                if (BidVol == 0) return double.MaxValue;
                if (AskVol == 0) return double.MaxValue;
                return AskVol > BidVol ? (double)AskVol / BidVol : (double)BidVol / AskVol;
            }
        }
    }

    public sealed class MADFootprintBar
    {
        public int BarIndex;
        public double Open, High, Low, Close;
        public DateTime BarTime;
        public SortedDictionary<double, MADCell> Levels = new SortedDictionary<double, MADCell>();
        public long TotalVol;
        public long BarDelta;
        public long Cvd;
        public double PocPrice;
        public long MaxDelta;
        public long MinDelta;
        public long RunningDelta;
        public int TradeCount;
        public double BarRange;

        public void AddTrade(double price, long size, int aggressor)
        {
            MADCell cell;
            if (!Levels.TryGetValue(price, out cell)) { cell = new MADCell(); Levels[price] = cell; }
            if (aggressor == 1) { cell.AskVol += size; RunningDelta += size; }
            else if (aggressor == 2) { cell.BidVol += size; RunningDelta -= size; }
            else { cell.NeutralVol += size; }
            if (RunningDelta > MaxDelta) MaxDelta = RunningDelta;
            if (RunningDelta < MinDelta) MinDelta = RunningDelta;
            if (Open == 0) Open = price;
            if (price > High) High = price;
            if (Low == 0 || price < Low) Low = price;
            Close = price;
            TotalVol += size;
            TradeCount++;
        }

        public void Finalize(long priorCvd = 0)
        {
            if (TotalVol == 0 && Levels.Count > 0)
            {
                TotalVol = 0;
                foreach (var lv in Levels.Values) TotalVol += lv.TotalVol;
            }
            BarDelta = 0;
            foreach (var lv in Levels.Values) BarDelta += lv.Delta;
            double bestPx = 0; long bestVol = -1;
            foreach (var kv in Levels)
            {
                long v = kv.Value.TotalVol;
                if (v > bestVol) { bestVol = v; bestPx = kv.Key; }
            }
            PocPrice = bestPx;
            BarRange = High - Low;
            Cvd = priorCvd + BarDelta;
        }
    }

    public sealed class MADLevel
    {
        public double Price;
    }

    public sealed class MADMarketState
    {
        public double Atr20 { get; set; }
        public double VolEma { get; set; }
        public MADTrend HtfBias { get; set; }
    }

    public sealed class MADDeltaPipeline
    {
        public int Count { get; set; }
    }

    // ── Detector logic (test-local copy) ────────────────────────────────

    internal static class Detectors
    {
        public static MADSignalResult DetectImb01(MADFootprintBar bar, double imbalanceRatio)
        {
            if (bar == null || bar.Levels.Count < 3) return null;

            int bestRun = 0;
            double bestStartPrice = 0;
            bool bestAskDom = false;

            int currentRun = 0;
            double currentStartPrice = 0;
            bool currentAskDom = false;

            foreach (var kv in bar.Levels)
            {
                var cell = kv.Value;
                if (cell.TotalVol < 5 || cell.ImbalanceRatio < imbalanceRatio)
                {
                    currentRun = 0;
                    continue;
                }

                bool askDom = cell.AskVol > cell.BidVol;

                if (currentRun == 0 || askDom != currentAskDom)
                {
                    currentRun = 1;
                    currentStartPrice = kv.Key;
                    currentAskDom = askDom;
                }
                else
                {
                    currentRun++;
                }

                if (currentRun > bestRun)
                {
                    bestRun = currentRun;
                    bestStartPrice = currentStartPrice;
                    bestAskDom = currentAskDom;
                }
            }

            if (bestRun < 3) return null;

            var direction = bestAskDom
                ? MADSignalDirection.Long
                : MADSignalDirection.Short;

            double strength = SysMath.Min(1.0, (bestRun - 2.0) / 5.0);

            return new MADSignalResult
            {
                SignalId = "IMB-01",
                Direction = direction,
                Strength = strength,
                Detail = string.Format("Stacked imbalance: {0} levels, {1}-dominant",
                    bestRun, bestAskDom ? "ask" : "bid"),
                Price = bestStartPrice
            };
        }

        public static MADSignalResult DetectIce01(MADFootprintBar bar, bool isDomAvailable, Func<double, int> getRefillCount)
        {
            if (bar == null || bar.Levels.Count == 0 || !isDomAvailable || getRefillCount == null) return null;

            double bestPrice = 0;
            int bestRefills = 0;
            MADCell bestCell = null;

            foreach (var kv in bar.Levels)
            {
                int refills = getRefillCount(kv.Key);
                if (refills >= 3 && refills > bestRefills)
                {
                    bestRefills = refills;
                    bestPrice = kv.Key;
                    bestCell = kv.Value;
                }
            }

            if (bestCell == null) return null;

            var direction = bestCell.BidVol > bestCell.AskVol
                ? MADSignalDirection.Long
                : MADSignalDirection.Short;

            double strength = SysMath.Min(1.0, bestRefills / 10.0);

            return new MADSignalResult
            {
                SignalId = "ICE-01",
                Direction = direction,
                Strength = strength,
                Detail = string.Format("Iceberg at {0}, refills={1}", bestPrice, bestRefills),
                Price = bestPrice
            };
        }

        public static MADSignalResult DetectLiqSw01(MADFootprintBar bar, List<MADLevel> nearbyLevels, double avgBarVol)
        {
            if (bar == null || nearbyLevels == null || nearbyLevels.Count == 0) return null;
            if (bar.BarRange <= 0) return null;
            if (avgBarVol > 0 && bar.TotalVol <= 2.0 * avgBarVol) return null;

            MADSignalResult best = null;
            double bestStrength = 0;

            foreach (var level in nearbyLevels)
            {
                double lp = level.Price;

                if (bar.High > lp && bar.Close < lp)
                {
                    double reversal = SysMath.Abs(bar.Close - bar.High);
                    double s = SysMath.Min(1.0, reversal / bar.BarRange);
                    if (s > bestStrength)
                    {
                        bestStrength = s;
                        best = new MADSignalResult
                        {
                            SignalId = "LIQSW-01",
                            Direction = MADSignalDirection.Short,
                            Strength = s,
                            Detail = string.Format("Sweep above {0}", lp),
                            Price = lp
                        };
                    }
                }

                if (bar.Low < lp && bar.Close > lp)
                {
                    double reversal = SysMath.Abs(bar.Close - bar.Low);
                    double s = SysMath.Min(1.0, reversal / bar.BarRange);
                    if (s > bestStrength)
                    {
                        bestStrength = s;
                        best = new MADSignalResult
                        {
                            SignalId = "LIQSW-01",
                            Direction = MADSignalDirection.Long,
                            Strength = s,
                            Detail = string.Format("Sweep below {0}", lp),
                            Price = lp
                        };
                    }
                }
            }

            return best;
        }

        public static MADSignalResult DetectFail01(MADFootprintBar bar)
        {
            if (bar == null || bar.Levels.Count == 0 || bar.BarRange <= 0) return null;

            MADCell pocCell;
            if (!bar.Levels.TryGetValue(bar.PocPrice, out pocCell) || pocCell == null) return null;

            double tickSize = 0.25;
            bool atHigh = SysMath.Abs(bar.PocPrice - bar.High) <= tickSize;
            bool atLow = SysMath.Abs(bar.PocPrice - bar.Low) <= tickSize;
            if (!atHigh && !atLow) return null;

            double midpoint = bar.Low + bar.BarRange * 0.5;
            MADSignalDirection direction;
            double extremePrice;

            if (atHigh && bar.Close < midpoint)
            {
                direction = MADSignalDirection.Short;
                extremePrice = bar.High;
            }
            else if (atLow && bar.Close > midpoint)
            {
                direction = MADSignalDirection.Long;
                extremePrice = bar.Low;
            }
            else
            {
                return null;
            }

            int levelsNearExtreme = 0;
            foreach (var kv in bar.Levels)
            {
                if (SysMath.Abs(kv.Key - extremePrice) <= tickSize)
                    levelsNearExtreme++;
            }
            if (levelsNearExtreme > 2) return null;

            double avgLevelVol = (double)bar.TotalVol / bar.Levels.Count;
            double strength = SysMath.Min(1.0, pocCell.TotalVol / (avgLevelVol * 3.0));

            return new MADSignalResult
            {
                SignalId = "FAIL-01",
                Direction = direction,
                Strength = strength,
                Detail = string.Format("Failed auction at {0}, POC vol={1}",
                    atHigh ? "high" : "low", pocCell.TotalVol),
                Price = extremePrice
            };
        }

        public static MADSignalResult DetectTrap01(MADFootprintBar bar, List<MADFootprintBar> bars, List<MADLevel> nearbyLevels, double avgBarVol)
        {
            if (bar == null || bars == null || bars.Count < 2) return null;
            if (nearbyLevels == null || nearbyLevels.Count == 0) return null;

            var priorBar = bars[bars.Count - 2];
            MADSignalResult best = null;
            double bestStrength = 0;

            foreach (var level in nearbyLevels)
            {
                double lp = level.Price;

                if (priorBar.High > lp && bar.Close < lp)
                {
                    double s = avgBarVol > 0
                        ? SysMath.Min(1.0, (double)priorBar.TotalVol / (avgBarVol * 2.0))
                        : 0.5;
                    if (s > bestStrength)
                    {
                        bestStrength = s;
                        best = new MADSignalResult
                        {
                            SignalId = "TRAP-01",
                            Direction = MADSignalDirection.Short,
                            Strength = s,
                            Detail = string.Format("Trapped longs above {0}", lp),
                            Price = lp
                        };
                    }
                }

                if (priorBar.Low < lp && bar.Close > lp)
                {
                    double s = avgBarVol > 0
                        ? SysMath.Min(1.0, (double)priorBar.TotalVol / (avgBarVol * 2.0))
                        : 0.5;
                    if (s > bestStrength)
                    {
                        bestStrength = s;
                        best = new MADSignalResult
                        {
                            SignalId = "TRAP-01",
                            Direction = MADSignalDirection.Long,
                            Strength = s,
                            Detail = string.Format("Trapped shorts below {0}", lp),
                            Price = lp
                        };
                    }
                }
            }

            return best;
        }

        public static MADSignalResult DetectReg01(MADMarketState state, MADDeltaPipeline deltaPipeline, List<MADFootprintBar> bars)
        {
            if (state == null || bars == null || bars.Count < 10) return null;

            var lastBar = bars[bars.Count - 1];
            string regime;
            double confidence;

            if (state.VolEma > 0 && lastBar.TotalVol < 0.5 * state.VolEma)
            {
                regime = "Thin";
                double ratio = (double)lastBar.TotalVol / (state.VolEma * 0.5);
                confidence = SysMath.Max(0, SysMath.Min(1.0, 1.0 - ratio));
            }
            else
            {
                int lookback = SysMath.Min(50, bars.Count);
                double[] ranges = new double[lookback];
                for (int i = 0; i < lookback; i++)
                    ranges[i] = bars[bars.Count - 1 - i].BarRange;
                Array.Sort(ranges);

                int belowAtr = 0;
                for (int i = 0; i < lookback; i++)
                {
                    if (ranges[i] <= state.Atr20) belowAtr++;
                }
                double atrPct = (double)belowAtr / lookback;

                if (atrPct > 0.75)
                {
                    regime = "Volatile";
                    confidence = SysMath.Min(1.0, (atrPct - 0.75) / 0.25);
                }
                else if (atrPct < 0.25)
                {
                    regime = "Ranging";
                    confidence = SysMath.Min(1.0, (0.25 - atrPct) / 0.25);
                }
                else
                {
                    int sameSignCount = 0;
                    bool lastPositive = lastBar.BarDelta >= 0;
                    for (int i = bars.Count - 1; i >= SysMath.Max(0, bars.Count - 10); i--)
                    {
                        if ((bars[i].BarDelta >= 0) == lastPositive)
                            sameSignCount++;
                        else
                            break;
                    }

                    bool htfAligned = state.HtfBias != MADTrend.Neutral;

                    if (sameSignCount >= 7 && htfAligned)
                    {
                        regime = "Trending";
                        confidence = SysMath.Min(1.0, sameSignCount / 10.0);
                    }
                    else
                    {
                        regime = "Ranging";
                        confidence = SysMath.Min(1.0, 1.0 - (sameSignCount / 10.0));
                    }
                }
            }

            return new MADSignalResult
            {
                SignalId = "REG-01",
                Direction = MADSignalDirection.Neutral,
                Strength = confidence,
                Detail = string.Format("Regime: {0}", regime),
                Price = lastBar.Close
            };
        }
    }

    // ── Helper ──────────────────────────────────────────────────────────

    internal static class BarHelper
    {
        public static MADFootprintBar MakeMultiLevelBar(
            (double price, long bidVol, long askVol)[] levels, long priorCvd = 0)
        {
            var bar = new MADFootprintBar();
            foreach (var (price, bidVol, askVol) in levels)
            {
                if (askVol > 0) bar.AddTrade(price, askVol, 1);
                if (bidVol > 0) bar.AddTrade(price, bidVol, 2);
            }
            bar.Finalize(priorCvd);
            return bar;
        }
    }

    // ── IMB-01 Tests ────────────────────────────────────────────────────

    [TestFixture]
    public class Imb01Tests
    {
        [Test]
        public void Imb01_Fires_Long_WhenFourConsecutiveAskDominant()
        {
            // 4 consecutive levels with ask:bid > 4:1, each >= 5 contracts
            var bar = new MADFootprintBar();
            bar.Levels[21000.00] = new MADCell { AskVol = 40, BidVol = 5 };  // 4:1 ask, 45 total
            bar.Levels[21000.25] = new MADCell { AskVol = 50, BidVol = 6 };  // ~8:1, 56 total
            bar.Levels[21000.50] = new MADCell { AskVol = 30, BidVol = 5 };  // 6:1, 35 total
            bar.Levels[21000.75] = new MADCell { AskVol = 45, BidVol = 8 };  // ~5.6:1, 53 total
            bar.Levels[21001.00] = new MADCell { AskVol = 10, BidVol = 10 }; // 1:1, no imbalance
            bar.Open = 21000.00; bar.High = 21001.00;
            bar.Low = 21000.00; bar.Close = 21000.50;
            bar.Finalize();

            var result = Detectors.DetectImb01(bar, 1.5);
            Assert.IsNotNull(result, "IMB-01 should fire on 4 consecutive ask-dominant levels");
            Assert.AreEqual("IMB-01", result.SignalId);
            Assert.AreEqual(MADSignalDirection.Long, result.Direction);
            Assert.AreEqual(0.4, result.Strength, 0.01); // (4-2)/5 = 0.4
            Assert.AreEqual(21000.00, result.Price);
        }

        [Test]
        public void Imb01_ReturnsNull_WhenNoThreeConsecutive()
        {
            // Alternating imbalance directions — no 3 consecutive same-direction
            var bar = new MADFootprintBar();
            bar.Levels[21000.00] = new MADCell { AskVol = 40, BidVol = 5 };  // ask dom
            bar.Levels[21000.25] = new MADCell { AskVol = 5, BidVol = 40 };  // bid dom
            bar.Levels[21000.50] = new MADCell { AskVol = 40, BidVol = 5 };  // ask dom
            bar.Levels[21000.75] = new MADCell { AskVol = 5, BidVol = 40 };  // bid dom
            bar.Open = 21000.00; bar.High = 21000.75;
            bar.Low = 21000.00; bar.Close = 21000.50;
            bar.Finalize();

            var result = Detectors.DetectImb01(bar, 1.5);
            Assert.IsNull(result, "IMB-01 should NOT fire when imbalances alternate direction");
        }

        [Test]
        public void Imb01_ReturnsNull_WhenLevelVolumeTooLow()
        {
            // High ratios but each level has < 5 contracts total
            var bar = new MADFootprintBar();
            bar.Levels[21000.00] = new MADCell { AskVol = 4, BidVol = 1 };  // 4:1 but total=5 (borderline)
            bar.Levels[21000.25] = new MADCell { AskVol = 3, BidVol = 0 };  // inf but total=3 < 5
            bar.Levels[21000.50] = new MADCell { AskVol = 3, BidVol = 0 };  // inf but total=3 < 5
            bar.Levels[21000.75] = new MADCell { AskVol = 3, BidVol = 0 };  // inf but total=3 < 5
            bar.Open = 21000.00; bar.High = 21000.75;
            bar.Low = 21000.00; bar.Close = 21000.50;
            bar.Finalize();

            var result = Detectors.DetectImb01(bar, 1.5);
            Assert.IsNull(result, "IMB-01 should NOT fire when level volume < 5 contracts");
        }

        [Test]
        public void Imb01_Fires_AtRelaxedRatio_1Point8()
        {
            // With relaxed threshold (1.5), imbalance of 1.8:1 should qualify
            var bar = new MADFootprintBar();
            bar.Levels[21000.00] = new MADCell { AskVol = 18, BidVol = 10 };  // 1.8:1
            bar.Levels[21000.25] = new MADCell { AskVol = 18, BidVol = 10 };  // 1.8:1
            bar.Levels[21000.50] = new MADCell { AskVol = 18, BidVol = 10 };  // 1.8:1
            bar.Levels[21000.75] = new MADCell { AskVol = 18, BidVol = 10 };  // 1.8:1
            bar.Levels[21001.00] = new MADCell { AskVol = 10, BidVol = 10 };  // balanced
            bar.Open = 21000.00; bar.High = 21001.00;
            bar.Low = 21000.00; bar.Close = 21000.50;
            bar.Finalize();

            var result = Detectors.DetectImb01(bar, 1.5);
            Assert.IsNotNull(result, "IMB-01 should fire at 1.8:1 with relaxed 1.5 threshold");
            Assert.AreEqual("IMB-01", result.SignalId);
            Assert.AreEqual(MADSignalDirection.Long, result.Direction);
        }
    }

    // ── ICE-01 Tests ────────────────────────────────────────────────────

    [TestFixture]
    public class Ice01Tests
    {
        [Test]
        public void Ice01_Fires_WhenThreeRefillsDetected()
        {
            var bar = new MADFootprintBar();
            bar.Levels[21000.00] = new MADCell { BidVol = 80, AskVol = 20 }; // bid-side iceberg
            bar.Levels[21000.25] = new MADCell { BidVol = 10, AskVol = 10 };
            bar.Open = 21000.00; bar.High = 21000.25;
            bar.Low = 21000.00; bar.Close = 21000.25;
            bar.Finalize();

            // Refill function: 5 refills at 21000.00, none elsewhere
            Func<double, int> getRefills = (price) => price == 21000.00 ? 5 : 0;

            var result = Detectors.DetectIce01(bar, true, getRefills);
            Assert.IsNotNull(result, "ICE-01 should fire with 5 refills");
            Assert.AreEqual("ICE-01", result.SignalId);
            Assert.AreEqual(MADSignalDirection.Long, result.Direction, "BidVol > AskVol → passive buyers → Long");
            Assert.AreEqual(0.5, result.Strength, 0.01); // 5/10
            Assert.AreEqual(21000.00, result.Price);
        }

        [Test]
        public void Ice01_ReturnsNull_WhenDomUnavailable()
        {
            var bar = new MADFootprintBar();
            bar.Levels[21000.00] = new MADCell { BidVol = 80, AskVol = 20 };
            bar.Open = 21000.00; bar.High = 21000.00;
            bar.Low = 21000.00; bar.Close = 21000.00;
            bar.Finalize();

            Func<double, int> getRefills = (price) => 10;

            var result = Detectors.DetectIce01(bar, false, getRefills);
            Assert.IsNull(result, "ICE-01 should NOT fire when DOM is unavailable");
        }

        [Test]
        public void Ice01_ReturnsNull_WhenRefillsBelowThreshold()
        {
            var bar = new MADFootprintBar();
            bar.Levels[21000.00] = new MADCell { BidVol = 50, AskVol = 50 };
            bar.Open = 21000.00; bar.High = 21000.00;
            bar.Low = 21000.00; bar.Close = 21000.00;
            bar.Finalize();

            Func<double, int> getRefills = (price) => 2; // below threshold of 3

            var result = Detectors.DetectIce01(bar, true, getRefills);
            Assert.IsNull(result, "ICE-01 should NOT fire with < 3 refills");
        }
    }

    // ── LIQSW-01 Tests ──────────────────────────────────────────────────

    [TestFixture]
    public class LiqSw01Tests
    {
        [Test]
        public void LiqSw01_Fires_Short_WhenSweepAboveLevel()
        {
            // Bar high > level, close < level, volume > 2x avg
            var bar = new MADFootprintBar();
            bar.AddTrade(21000.00, 50, 2);   // low
            bar.AddTrade(21005.00, 200, 1);  // high (sweep above level)
            bar.AddTrade(21001.00, 100, 2);  // close below level
            bar.Finalize();
            // High=21005, Low=21000, Close=21001, TotalVol=350

            var levels = new List<MADLevel> { new MADLevel { Price = 21003.00 } };
            // avgBarVol=100 → vol 350 > 2*100 ✓
            // bar.High=21005 > 21003 ✓, bar.Close=21001 < 21003 ✓

            var result = Detectors.DetectLiqSw01(bar, levels, 100);
            Assert.IsNotNull(result, "LIQSW-01 should fire on sweep above");
            Assert.AreEqual("LIQSW-01", result.SignalId);
            Assert.AreEqual(MADSignalDirection.Short, result.Direction);
            Assert.AreEqual(21003.00, result.Price);
            Assert.Greater(result.Strength, 0);
        }

        [Test]
        public void LiqSw01_Fires_Long_WhenSweepBelowLevel()
        {
            // Bar low < level, close > level, volume > 2x avg
            var bar = new MADFootprintBar();
            bar.AddTrade(21005.00, 50, 1);   // high
            bar.AddTrade(21000.00, 200, 2);  // low (sweep below level)
            bar.AddTrade(21004.00, 100, 1);  // close above level
            bar.Finalize();
            // High=21005, Low=21000, Close=21004, TotalVol=350

            var levels = new List<MADLevel> { new MADLevel { Price = 21002.00 } };

            var result = Detectors.DetectLiqSw01(bar, levels, 100);
            Assert.IsNotNull(result, "LIQSW-01 should fire on sweep below");
            Assert.AreEqual(MADSignalDirection.Long, result.Direction);
            Assert.AreEqual(21002.00, result.Price);
        }

        [Test]
        public void LiqSw01_ReturnsNull_WhenNoLevelBroken()
        {
            // Bar fully below all levels — no sweep
            var bar = new MADFootprintBar();
            bar.AddTrade(21000.00, 100, 1);
            bar.AddTrade(21002.00, 100, 2);
            bar.Finalize();
            // High=21002, Low=21000, TotalVol=200

            var levels = new List<MADLevel> { new MADLevel { Price = 21010.00 } }; // level far above

            var result = Detectors.DetectLiqSw01(bar, levels, 50);
            Assert.IsNull(result, "LIQSW-01 should NOT fire when no level broken");
        }
    }

    // ── FAIL-01 Tests ───────────────────────────────────────────────────

    [TestFixture]
    public class Fail01Tests
    {
        [Test]
        public void Fail01_Fires_Short_WhenPocAtHighAndCloseBelowMid()
        {
            // POC at high, close below midpoint, single print at extreme
            var bar = new MADFootprintBar();
            // Level at high: massive volume (will be POC)
            bar.Levels[21005.00] = new MADCell { AskVol = 200, BidVol = 50 }; // 250 total
            // Level at low: small volume
            bar.Levels[21000.00] = new MADCell { AskVol = 10, BidVol = 10 };  // 20 total
            // Level at close (below midpoint 21002.5)
            bar.Levels[21001.00] = new MADCell { AskVol = 15, BidVol = 15 };  // 30 total
            bar.Open = 21000.00; bar.High = 21005.00;
            bar.Low = 21000.00; bar.Close = 21001.00;
            bar.Finalize();
            // POC=21005, midpoint=21002.5, close=21001 < midpoint ✓
            // Levels near high (within 0.25): only 21005 → 1 level ≤ 2 ✓

            var result = Detectors.DetectFail01(bar);
            Assert.IsNotNull(result, "FAIL-01 should fire: POC at high + close below mid");
            Assert.AreEqual("FAIL-01", result.SignalId);
            Assert.AreEqual(MADSignalDirection.Short, result.Direction);
            Assert.AreEqual(21005.00, result.Price);
            Assert.Greater(result.Strength, 0);
        }

        [Test]
        public void Fail01_ReturnsNull_WhenPocInMiddle()
        {
            // POC in the middle of the bar — not at extreme
            var bar = new MADFootprintBar();
            bar.Levels[21000.00] = new MADCell { AskVol = 10, BidVol = 10 };
            bar.Levels[21002.50] = new MADCell { AskVol = 100, BidVol = 100 }; // POC here
            bar.Levels[21005.00] = new MADCell { AskVol = 10, BidVol = 10 };
            bar.Open = 21000.00; bar.High = 21005.00;
            bar.Low = 21000.00; bar.Close = 21001.00;
            bar.Finalize();
            // POC=21002.50, high=21005, low=21000 → |21002.5-21005|=2.5 > 0.25 AND |21002.5-21000|=2.5 > 0.25

            var result = Detectors.DetectFail01(bar);
            Assert.IsNull(result, "FAIL-01 should NOT fire when POC is in the middle");
        }

        [Test]
        public void Fail01_ReturnsNull_WhenTooManyLevelsAtExtreme()
        {
            // POC at high but 3+ levels near extreme — not a single print
            var bar = new MADFootprintBar();
            bar.Levels[21005.00] = new MADCell { AskVol = 200, BidVol = 50 }; // POC
            bar.Levels[21004.75] = new MADCell { AskVol = 30, BidVol = 30 };  // within 1 tick
            bar.Levels[21005.25] = new MADCell { AskVol = 20, BidVol = 20 };  // within 1 tick
            bar.Levels[21000.00] = new MADCell { AskVol = 5, BidVol = 5 };
            bar.Open = 21000.00; bar.High = 21005.25;
            bar.Low = 21000.00; bar.Close = 21001.00;
            bar.Finalize();
            // 3 levels within 1 tick of high(21005.25): 21005.00, 21004.75(?), 21005.25
            // Actually high=21005.25, within 0.25: 21005.00 (0.25 away ✓), 21005.25 (0 ✓)
            // 21004.75 is 0.50 away from 21005.25 → NOT within 1 tick
            // So only 2 levels near extreme. Need more.
            // Let me adjust: add another level at 21005.25-adjacent
            bar.Levels[21005.50] = new MADCell { AskVol = 15, BidVol = 15 };
            bar.High = 21005.50;
            bar.Finalize();
            // Now high=21005.50. Within 0.25: 21005.25 (0.25 ✓), 21005.50 (0 ✓), 21005.00 (0.50 NO)
            // Still only 2... need 3+ levels within 0.25 of 21005.50
            // Add 21005.75
            bar.Levels[21005.75] = new MADCell { AskVol = 10, BidVol = 10 };
            bar.High = 21005.75;
            bar.Finalize();
            // Within 0.25 of 21005.75: 21005.50 ✓, 21005.75 ✓ = 2 still
            // Actually I need 3 levels WITHIN 1 tick (0.25) of extreme
            // That means prices at: extreme, extreme-0.25, extreme+0.25 (if any above)
            // For NQ with 0.25 ticks, only 2 prices within 0.25 of each other
            // Unless I use sub-tick prices. But with real 0.25 ticks, max 2 levels at any tick boundary

            // Let me use sub-tick prices for the test:
            var testBar = new MADFootprintBar();
            testBar.Levels[21005.00] = new MADCell { AskVol = 200, BidVol = 50 }; // POC
            testBar.Levels[21004.80] = new MADCell { AskVol = 30, BidVol = 30 };  // within 0.25 of 21005
            testBar.Levels[21004.90] = new MADCell { AskVol = 25, BidVol = 25 };  // within 0.25 of 21005
            testBar.Levels[21000.00] = new MADCell { AskVol = 5, BidVol = 5 };
            testBar.Open = 21000.00; testBar.High = 21005.00;
            testBar.Low = 21000.00; testBar.Close = 21001.00;
            testBar.Finalize();
            // Levels near 21005 (within 0.25): 21005.00, 21004.80, 21004.90 → 3 levels > 2

            var result = Detectors.DetectFail01(testBar);
            Assert.IsNull(result, "FAIL-01 should NOT fire when > 2 levels near extreme");
        }
    }

    // ── TRAP-01 Tests ───────────────────────────────────────────────────

    [TestFixture]
    public class Trap01Tests
    {
        [Test]
        public void Trap01_Fires_Short_WhenPriorBarBrokeAbove()
        {
            // Prior bar broke above level, current bar closed below → trapped longs → Short
            var priorBar = new MADFootprintBar();
            priorBar.AddTrade(21000.00, 50, 1);
            priorBar.AddTrade(21006.00, 150, 1); // broke above 21005
            priorBar.Finalize();

            var currentBar = new MADFootprintBar();
            currentBar.AddTrade(21004.00, 50, 2);
            currentBar.AddTrade(21003.00, 50, 2); // closed below 21005
            currentBar.Finalize();

            var bars = new List<MADFootprintBar> { priorBar, currentBar };
            var levels = new List<MADLevel> { new MADLevel { Price = 21005.00 } };

            var result = Detectors.DetectTrap01(currentBar, bars, levels, 100);
            Assert.IsNotNull(result, "TRAP-01 should fire: prior bar broke above, current closed below");
            Assert.AreEqual("TRAP-01", result.SignalId);
            Assert.AreEqual(MADSignalDirection.Short, result.Direction);
            Assert.AreEqual(21005.00, result.Price);
        }

        [Test]
        public void Trap01_Fires_Long_WhenPriorBarBrokeBelow()
        {
            // Prior bar broke below level, current bar closed above → trapped shorts → Long
            var priorBar = new MADFootprintBar();
            priorBar.AddTrade(21005.00, 50, 2);
            priorBar.AddTrade(20999.00, 150, 2); // broke below 21000
            priorBar.Finalize();

            var currentBar = new MADFootprintBar();
            currentBar.AddTrade(21001.00, 50, 1);
            currentBar.AddTrade(21002.00, 50, 1); // closed above 21000
            currentBar.Finalize();

            var bars = new List<MADFootprintBar> { priorBar, currentBar };
            var levels = new List<MADLevel> { new MADLevel { Price = 21000.00 } };

            var result = Detectors.DetectTrap01(currentBar, bars, levels, 100);
            Assert.IsNotNull(result);
            Assert.AreEqual(MADSignalDirection.Long, result.Direction);
        }

        [Test]
        public void Trap01_ReturnsNull_WhenNoBreakout()
        {
            // Prior bar stayed below level — no breakout to trap
            var priorBar = new MADFootprintBar();
            priorBar.AddTrade(21000.00, 50, 1);
            priorBar.AddTrade(21002.00, 50, 1); // high=21002, below 21005
            priorBar.Finalize();

            var currentBar = new MADFootprintBar();
            currentBar.AddTrade(21001.00, 50, 1);
            currentBar.Finalize();

            var bars = new List<MADFootprintBar> { priorBar, currentBar };
            var levels = new List<MADLevel> { new MADLevel { Price = 21005.00 } };

            var result = Detectors.DetectTrap01(currentBar, bars, levels, 100);
            Assert.IsNull(result, "TRAP-01 should NOT fire when no breakout occurred");
        }
    }

    // ── REG-01 Tests ────────────────────────────────────────────────────

    [TestFixture]
    public class Reg01Tests
    {
        private List<MADFootprintBar> MakeBars(int count, double barRange, long delta)
        {
            var bars = new List<MADFootprintBar>();
            long cvd = 0;
            for (int i = 0; i < count; i++)
            {
                var bar = new MADFootprintBar();
                double basePrice = 21000.0 + i;
                if (delta >= 0)
                {
                    bar.AddTrade(basePrice, delta > 0 ? delta : 1, 1);
                    bar.AddTrade(basePrice + barRange, 1, 2);
                }
                else
                {
                    bar.AddTrade(basePrice + barRange, 1, 1);
                    bar.AddTrade(basePrice, -delta, 2);
                }
                bar.Finalize(cvd);
                cvd = bar.Cvd;
                bars.Add(bar);
            }
            return bars;
        }

        [Test]
        public void Reg01_Volatile_WhenHighAtr()
        {
            // Bars with small range but very high ATR → volatile
            // ATR20=10 but bar ranges mostly around 2 → atrPct will be high (most ranges below ATR)
            var bars = MakeBars(20, 2.0, 10);
            var state = new MADMarketState { Atr20 = 10.0, VolEma = 0, HtfBias = MADTrend.Neutral };

            var result = Detectors.DetectReg01(state, null, bars);
            Assert.IsNotNull(result);
            Assert.AreEqual("REG-01", result.SignalId);
            Assert.AreEqual(MADSignalDirection.Neutral, result.Direction);
            // With ATR=10 and all ranges=2, belowAtr=20/20=1.0 → atrPct=1.0 > 0.75 → Volatile
            Assert.That(result.Detail, Does.Contain("Volatile"));
        }

        [Test]
        public void Reg01_Ranging_WhenLowAtrNoTrend()
        {
            // Bars with large range but very low ATR → most ranges above ATR → atrPct low
            var bars = MakeBars(20, 5.0, 10);
            var state = new MADMarketState { Atr20 = 0.5, VolEma = 0, HtfBias = MADTrend.Neutral };

            var result = Detectors.DetectReg01(state, null, bars);
            Assert.IsNotNull(result);
            // ATR=0.5, all ranges=5 → belowAtr=0 → atrPct=0.0 < 0.25 → Ranging
            Assert.That(result.Detail, Does.Contain("Ranging"));
        }

        [Test]
        public void Reg01_Trending_WhenConsistentDeltaAndHtfAligned()
        {
            // Moderate ATR + all deltas positive + HTF bullish
            var bars = MakeBars(15, 3.0, 50); // all positive delta
            var state = new MADMarketState { Atr20 = 3.0, VolEma = 100, HtfBias = MADTrend.Bullish };
            // ATR=3.0, all ranges=3.0 → belowAtr=15/15=1.0 → atrPct=1.0 > 0.75 → Volatile...
            // Hmm, need ATR to be in the middle range (0.25-0.75 percentile)
            // If ATR = 3.0 and bar ranges vary: some above, some below
            // Let me make bars with varied ranges

            var variedBars = new List<MADFootprintBar>();
            long cvd = 0;
            for (int i = 0; i < 15; i++)
            {
                var bar = new MADFootprintBar();
                double basePrice = 21000.0 + i;
                // Range alternates: 2, 4, 2, 4... so avg ~3, ATR ~3
                double range = (i % 2 == 0) ? 2.0 : 4.0;
                bar.AddTrade(basePrice, 50, 1); // all positive delta
                bar.AddTrade(basePrice + range, 1, 2);
                bar.Finalize(cvd);
                cvd = bar.Cvd;
                variedBars.Add(bar);
            }
            // Ranges sorted: 2,2,2,2,2,2,2,2,4,4,4,4,4,4,4 (8 twos, 7 fours)
            // ATR=3.0 → belowAtr = 8 (ranges ≤ 3.0 are the 2s) → atrPct = 8/15 = 0.533
            // 0.25 ≤ 0.533 ≤ 0.75 → middle range → check delta trend
            // All deltas positive (50-1=49 each) → 15 consecutive → sameSignCount = min(10,15) = 10 (loop caps at 10)
            // htfAligned = true → sameSignCount >= 7 → Trending ✓

            state = new MADMarketState { Atr20 = 3.0, VolEma = 100, HtfBias = MADTrend.Bullish };
            var result = Detectors.DetectReg01(state, null, variedBars);
            Assert.IsNotNull(result);
            Assert.That(result.Detail, Does.Contain("Trending"));
        }

        [Test]
        public void Reg01_Thin_WhenLowVolume()
        {
            // Volume < 0.5x VolEma → Thin
            var bars = new List<MADFootprintBar>();
            long cvd = 0;
            for (int i = 0; i < 12; i++)
            {
                var bar = new MADFootprintBar();
                bar.AddTrade(21000.0 + i, 5, 1); // very low volume
                bar.Finalize(cvd);
                cvd = bar.Cvd;
                bars.Add(bar);
            }
            // Last bar TotalVol = 5, VolEma = 200 → 5 < 0.5*200=100 → Thin

            var state = new MADMarketState { Atr20 = 3.0, VolEma = 200, HtfBias = MADTrend.Neutral };

            var result = Detectors.DetectReg01(state, null, bars);
            Assert.IsNotNull(result);
            Assert.That(result.Detail, Does.Contain("Thin"));
        }

        [Test]
        public void Reg01_ReturnsNull_WhenInsufficientBars()
        {
            var bars = MakeBars(5, 2.0, 10); // only 5 bars, need 10
            var state = new MADMarketState { Atr20 = 2.0, VolEma = 100 };

            var result = Detectors.DetectReg01(state, null, bars);
            Assert.IsNull(result, "REG-01 should NOT fire with < 10 bars");
        }
    }
}
