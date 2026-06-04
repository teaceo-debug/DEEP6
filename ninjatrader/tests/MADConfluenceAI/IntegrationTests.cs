// IntegrationTests.cs — T27: Full lifecycle integration tests for MADConfluenceAI
// Uses test-local type copies of ALL needed types to avoid NT8 runtime dependency.
using System;
using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using SysMath = System.Math;

namespace NinjaTrader.Tests.MADConfluenceAI.Integration
{
    // ═══════════════════════════════════════════════════════════════════
    //  TEST-LOCAL TYPE COPIES — mirrors production types exactly
    // ═══════════════════════════════════════════════════════════════════

    #region Enums
    public enum IntSignalDirection { Long, Short, Neutral }
    public enum IntRegime { Trending, Ranging, Volatile, Thin }
    public enum IntTier { Elite, High, Moderate, Wait, DoNotTrade }
    public enum IntAction { Long, Short, Wait, DoNotTrade }
    public enum IntTrend { Bullish, Bearish, Neutral }
    public enum IntSetupType { Reversal, Breakout, FailedBreakout, AbsorptionBounce, TrendContinuation, ExhaustionReversal, LiquiditySweepReversal, None }
    public enum IntLevelType { PrevDayHigh, PrevDayLow, PrevDayMid, SessionPoc, SessionVah, SessionVal, VwapLine, Psychological, NakedPoc, OpeningRangeHigh, OpeningRangeLow, SessionHigh, SessionLow }
    #endregion

    #region Core Types
    public sealed class IntSignalResult
    {
        public string SignalId;
        public IntSignalDirection Direction;
        public double Strength;
        public string Detail;
        public double Price;
    }

    public sealed class IntCell
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

    public sealed class IntFootprintBar
    {
        public int BarIndex;
        public double Open, High, Low, Close;
        public DateTime BarTime;
        public SortedDictionary<double, IntCell> Levels = new SortedDictionary<double, IntCell>();
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
            IntCell cell;
            if (!Levels.TryGetValue(price, out cell)) { cell = new IntCell(); Levels[price] = cell; }
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

        public double DeltaQualityScalar()
        {
            long extreme = SysMath.Abs(MaxDelta) > SysMath.Abs(MinDelta) ? SysMath.Abs(MaxDelta) : SysMath.Abs(MinDelta);
            if (extreme == 0) return 0.0;
            double q = (double)SysMath.Abs(BarDelta) / extreme;
            return SysMath.Min(1.15, SysMath.Max(0.0, q));
        }
    }

    public sealed class IntDeltaPipeline
    {
        private const int BufferSize = 500;
        private readonly long[] _cvdBuffer = new long[BufferSize];
        private readonly double[] _closeBuffer = new double[BufferSize];
        private int _head;
        private int _count;
        public int Count => _count;

        public void OnBarFinalized(IntFootprintBar bar)
        {
            _cvdBuffer[_head] = bar.Cvd;
            _closeBuffer[_head] = bar.Close;
            _head = (_head + 1) % BufferSize;
            if (_count < BufferSize) _count++;
        }

        public long GetCvd(int barsAgo)
        {
            if (barsAgo < 0 || barsAgo >= _count) return 0;
            int idx = ((_head - 1 - barsAgo) % BufferSize + BufferSize) % BufferSize;
            return _cvdBuffer[idx];
        }

        public double GetClose(int barsAgo)
        {
            if (barsAgo < 0 || barsAgo >= _count) return 0;
            int idx = ((_head - 1 - barsAgo) % BufferSize + BufferSize) % BufferSize;
            return _closeBuffer[idx];
        }

        public double CheckDivergence(int lookback)
        {
            if (_count < lookback || lookback < 2) return 0;
            double priceNow = GetClose(0);
            double priceThen = GetClose(lookback - 1);
            long cvdNow = GetCvd(0);
            long cvdThen = GetCvd(lookback - 1);
            bool priceDown = priceNow < priceThen;
            bool priceUp = priceNow > priceThen;
            bool cvdUp = cvdNow > cvdThen;
            bool cvdDown = cvdNow < cvdThen;
            if (priceDown && cvdUp) return 1.0;
            if (priceUp && cvdDown) return -1.0;
            return 0;
        }

        public double DeltaRoC
        {
            get
            {
                if (_count < 2) return 0;
                int n = SysMath.Min(10, _count);
                return (double)(GetCvd(0) - GetCvd(n - 1)) / n;
            }
        }

        public double DeltaAccel
        {
            get
            {
                int half = _count / 2;
                int n = SysMath.Min(10, half);
                if (n < 2) return 0;
                double rocNow = (double)(GetCvd(0) - GetCvd(n - 1)) / n;
                double rocPrev = (double)(GetCvd(n) - GetCvd(n + n - 1)) / n;
                return rocNow - rocPrev;
            }
        }

        public void Reset()
        {
            _head = 0;
            _count = 0;
            Array.Clear(_cvdBuffer, 0, BufferSize);
            Array.Clear(_closeBuffer, 0, BufferSize);
        }
    }

    public sealed class IntMarketState
    {
        private readonly double[] _trueRanges = new double[25];
        private int _trCount;
        private double _prevClose = double.NaN;
        public double Atr20 { get; private set; }
        public double VolEma { get; private set; }
        private bool _volEmaInitialized;
        private const double VolEmaAlpha = 2.0 / 13.0;
        public DateTime SessionDate { get; private set; }
        public bool IsRth { get; private set; }
        public double SessionHigh { get; private set; }
        public double SessionLow { get; private set; }
        public double PrevDayHigh { get; private set; }
        public double PrevDayLow { get; private set; }
        public double PrevDayClose { get; private set; }
        public IntTrend HtfBias { get; set; } = IntTrend.Neutral;
        public double HtfMomentum { get; set; }
        public TimeSpan RthStart { get; set; } = new TimeSpan(9, 30, 0);
        public TimeSpan RthEnd { get; set; } = new TimeSpan(16, 0, 0);
        public int OpeningRangeMinutes { get; set; } = 30;
        private double _lastClose;

        public void Update(double high, double low, double close, long volume, DateTime barTime)
        {
            TimeSpan t = barTime.TimeOfDay;
            IsRth = t >= RthStart && t < RthEnd;
            if (barTime.Date != SessionDate)
            {
                if (SessionDate != default(DateTime))
                {
                    PrevDayHigh = SessionHigh;
                    PrevDayLow = SessionLow;
                    PrevDayClose = _lastClose;
                }
                SessionDate = barTime.Date;
                SessionHigh = high;
                SessionLow = low;
            }
            if (high > SessionHigh) SessionHigh = high;
            if (low < SessionLow || SessionLow == 0) SessionLow = low;

            double tr;
            if (double.IsNaN(_prevClose))
                tr = high - low;
            else
                tr = SysMath.Max(high - low, SysMath.Max(SysMath.Abs(high - _prevClose), SysMath.Abs(low - _prevClose)));
            _trueRanges[_trCount % 25] = tr;
            _trCount++;
            if (_trCount >= 20)
            {
                double sum = 0;
                for (int i = 0; i < 20; i++) sum += _trueRanges[(_trCount - 1 - i) % 25];
                Atr20 = sum / 20.0;
            }
            _prevClose = close;
            _lastClose = close;
            if (!_volEmaInitialized) { VolEma = volume; _volEmaInitialized = true; }
            else VolEma = volume * VolEmaAlpha + VolEma * (1 - VolEmaAlpha);
        }

        public void Reset()
        {
            _trCount = 0; _prevClose = double.NaN; Atr20 = 0; VolEma = 0;
            _volEmaInitialized = false; SessionDate = default; SessionHigh = 0; SessionLow = 0;
            PrevDayHigh = 0; PrevDayLow = 0; PrevDayClose = 0;
            HtfBias = IntTrend.Neutral; HtfMomentum = 0; _lastClose = 0;
        }
    }

    public sealed class IntLevel
    {
        public IntLevelType Type;
        public double Price;
        public int TouchCount;
        public double QualityScore = 0.5;
    }

    public sealed class IntLevelEngine
    {
        private readonly List<IntLevel> _levels = new List<IntLevel>();
        public IReadOnlyList<IntLevel> Levels => _levels;

        public void SetPriorDayLevels(double high, double low)
        {
            _levels.Add(new IntLevel { Type = IntLevelType.PrevDayHigh, Price = high });
            _levels.Add(new IntLevel { Type = IntLevelType.PrevDayLow, Price = low });
            _levels.Add(new IntLevel { Type = IntLevelType.PrevDayMid, Price = (high + low) / 2.0 });
        }

        public List<IntLevel> GetNearbyLevels(double price, double toleranceTicks)
        {
            double tolerance = toleranceTicks * 0.25;
            var nearby = new List<IntLevel>();
            foreach (var l in _levels)
                if (SysMath.Abs(l.Price - price) <= tolerance)
                    nearby.Add(l);
            return nearby;
        }
    }

    public struct IntConfig
    {
        public double AbsorptionWeight, ExhaustionWeight, DeltaWeight, ImbalanceWeight, IcebergWeight, LiquidityWeight, TrapWeight;
        public double MinConfidenceScore, EliteThreshold, HighThreshold;
        public double AbsorptionVolumeMultiplier, ImbalanceRatio;
        public int SweepReversalSeconds;
        public double ExhaustionDeltaDecay;
        public int TrapFailureSeconds, OpeningRangeMinutes, WarmupBars;
        public int DefaultStopTicks, DefaultTargetTicks;
        public double MaxRiskRewardRatio;

        public static IntConfig Defaults => new IntConfig
        {
            AbsorptionWeight = 1.0, ExhaustionWeight = 1.0, DeltaWeight = 1.0,
            ImbalanceWeight = 1.0, IcebergWeight = 1.0, LiquidityWeight = 1.0, TrapWeight = 1.0,
            MinConfidenceScore = 60, EliteThreshold = 90, HighThreshold = 75,
            AbsorptionVolumeMultiplier = 3.0, ImbalanceRatio = 3.0,
            SweepReversalSeconds = 15, ExhaustionDeltaDecay = 0.7, TrapFailureSeconds = 30,
            OpeningRangeMinutes = 30, WarmupBars = 50,
            DefaultStopTicks = 20, DefaultTargetTicks = 40, MaxRiskRewardRatio = 5.0
        };
    }

    public sealed class IntScorerResult
    {
        public double Score;
        public IntTier Tier;
        public IntSignalDirection Direction;
        public string Detail;
        public List<IntSignalResult> ContributingSignals = new List<IntSignalResult>();
    }
    #endregion

    #region Scoring Engine (test-local)
    public static class IntScoringEngine
    {
        public static IntScorerResult Run(List<IntSignalResult> signals, IntConfig config, IntRegime regime, bool isAtKeyLevel)
        {
            var result = new IntScorerResult { Score = 0, Tier = IntTier.DoNotTrade, Direction = IntSignalDirection.Neutral, Detail = "No signals" };
            if (signals == null || signals.Count == 0) return result;

            int longCount = 0, shortCount = 0;
            foreach (var s in signals)
            {
                if (s.Direction == IntSignalDirection.Long) longCount++;
                else if (s.Direction == IntSignalDirection.Short) shortCount++;
            }
            var majorityDir = longCount > shortCount ? IntSignalDirection.Long
                : shortCount > longCount ? IntSignalDirection.Short
                : IntSignalDirection.Neutral;
            if (majorityDir == IntSignalDirection.Neutral) { result.Detail = "No majority direction"; return result; }

            double totalContribution = 0;
            double maxPossibleScore = 0;
            var categorySet = new HashSet<string>();

            foreach (var s in signals)
            {
                double categoryWeight = GetCategoryWeight(s.SignalId, config);
                maxPossibleScore += categoryWeight;
                double directionAgreement = s.Direction == majorityDir ? 1.0 : -0.5;
                if (s.Direction == IntSignalDirection.Neutral) directionAgreement = 0.0;
                totalContribution += s.Strength * categoryWeight * directionAgreement;
                if (s.Direction == majorityDir)
                {
                    result.ContributingSignals.Add(s);
                    string cat = GetSignalCategory(s.SignalId);
                    if (cat != null) categorySet.Add(cat);
                }
            }

            double rawScore = maxPossibleScore > 0 ? (totalContribution / maxPossibleScore) * 100.0 : 0;
            if (categorySet.Count >= 3) rawScore += 10;
            if (isAtKeyLevel) rawScore += 5;

            switch (regime)
            {
                case IntRegime.Trending: rawScore += 10; break;
                case IntRegime.Ranging: rawScore += 10; break;
                case IntRegime.Volatile: rawScore -= 5; break;
                case IntRegime.Thin: rawScore -= 15; break;
            }
            rawScore = SysMath.Max(0, SysMath.Min(100, rawScore));

            IntTier tier;
            if (rawScore >= 90) tier = IntTier.Elite;
            else if (rawScore >= 75) tier = IntTier.High;
            else if (rawScore >= 60) tier = IntTier.Moderate;
            else if (rawScore >= 40) tier = IntTier.Wait;
            else tier = IntTier.DoNotTrade;

            result.Score = rawScore;
            result.Tier = tier;
            result.Direction = majorityDir;
            result.Detail = string.Format("Score={0:F1}, Tier={1}, Categories={2}", rawScore, tier, categorySet.Count);
            return result;
        }

        private static double GetCategoryWeight(string signalId, IntConfig config)
        {
            if (string.IsNullOrEmpty(signalId)) return 1.0;
            if (signalId.StartsWith("ABS")) return config.AbsorptionWeight;
            if (signalId.StartsWith("EXH")) return config.ExhaustionWeight;
            if (signalId.StartsWith("DELT")) return config.DeltaWeight;
            if (signalId.StartsWith("IMB")) return config.ImbalanceWeight;
            if (signalId.StartsWith("ICE")) return config.IcebergWeight;
            if (signalId.StartsWith("LIQSW")) return config.LiquidityWeight;
            if (signalId.StartsWith("TRAP") || signalId.StartsWith("FAIL")) return config.TrapWeight;
            return 1.0;
        }

        private static string GetSignalCategory(string signalId)
        {
            if (string.IsNullOrEmpty(signalId)) return null;
            if (signalId.StartsWith("ABS")) return "absorption";
            if (signalId.StartsWith("EXH")) return "exhaustion";
            if (signalId.StartsWith("DELT")) return "delta";
            if (signalId.StartsWith("IMB")) return "imbalance";
            if (signalId.StartsWith("ICE")) return "iceberg";
            if (signalId.StartsWith("LIQSW")) return "liquidity";
            if (signalId.StartsWith("TRAP")) return "trap";
            if (signalId.StartsWith("FAIL")) return "auction";
            if (signalId.StartsWith("REG")) return "regime";
            return null;
        }
    }
    #endregion

    #region Detector Stubs (test-local — mirrors Signals.cs logic)
    public static class IntDetectors
    {
        public static IntSignalResult DetectAbs01(IntFootprintBar bar, double absorptionVolumeMultiplier)
        {
            if (bar == null || bar.Levels.Count == 0 || bar.TotalVol == 0) return null;
            double avgLevelVol = (double)bar.TotalVol / bar.Levels.Count;
            double threshold = absorptionVolumeMultiplier * avgLevelVol;
            if (bar.BarRange > 0.5) return null;
            double bestPrice = 0; long bestVol = 0; IntCell bestCell = null;
            foreach (var kv in bar.Levels)
            {
                if (kv.Value.TotalVol > threshold && kv.Value.TotalVol > bestVol)
                { bestVol = kv.Value.TotalVol; bestPrice = kv.Key; bestCell = kv.Value; }
            }
            if (bestCell == null) return null;
            var direction = bestCell.BidVol > bestCell.AskVol ? IntSignalDirection.Long : IntSignalDirection.Short;
            double strength = SysMath.Min(1.0, (double)bestCell.TotalVol / (absorptionVolumeMultiplier * 2.0 * avgLevelVol));
            return new IntSignalResult { SignalId = "ABS-01", Direction = direction, Strength = strength, Price = bestPrice };
        }

        public static IntSignalResult DetectAbs02(List<IntFootprintBar> bars)
        {
            if (bars == null || bars.Count < 3) return null;
            int start = bars.Count - 3;
            long cumDelta = 0;
            double highestHigh = double.MinValue, lowestLow = double.MaxValue;
            for (int i = start; i < bars.Count; i++)
            {
                cumDelta += bars[i].BarDelta;
                if (bars[i].High > highestHigh) highestHigh = bars[i].High;
                if (bars[i].Low < lowestLow) lowestLow = bars[i].Low;
            }
            if (highestHigh - lowestLow > 0.75) return null;
            long totalAbsDelta = 0;
            foreach (var b in bars) totalAbsDelta += SysMath.Abs(b.BarDelta);
            double avgBarDelta = bars.Count > 0 ? (double)totalAbsDelta / bars.Count : 1.0;
            if (avgBarDelta < 1.0) avgBarDelta = 1.0;
            if (SysMath.Abs(cumDelta) <= 3.0 * avgBarDelta) return null;
            var direction = cumDelta < 0 ? IntSignalDirection.Long : IntSignalDirection.Short;
            double strength = SysMath.Min(1.0, SysMath.Abs(cumDelta) / (avgBarDelta * 5.0));
            return new IntSignalResult { SignalId = "ABS-02", Direction = direction, Strength = strength, Price = bars[bars.Count - 1].Close };
        }

        public static IntSignalResult DetectExh01(IntFootprintBar bar)
        {
            if (bar == null || bar.Levels.Count == 0 || bar.TotalVol == 0) return null;
            if (bar.BarRange <= 0 || bar.DeltaQualityScalar() <= 0.5) return null;
            double avgLevelVol = (double)bar.TotalVol / bar.Levels.Count;
            IntCell cellAtHigh = null, cellAtLow = null;
            bar.Levels.TryGetValue(bar.High, out cellAtHigh);
            bar.Levels.TryGetValue(bar.Low, out cellAtLow);
            long volAtHigh = cellAtHigh != null ? cellAtHigh.TotalVol : 0;
            long volAtLow = cellAtLow != null ? cellAtLow.TotalVol : 0;
            bool exhaustionAtHigh = volAtHigh > volAtLow && volAtHigh > 2.0 * avgLevelVol;
            bool exhaustionAtLow = volAtLow > volAtHigh && volAtLow > 2.0 * avgLevelVol;
            if (!exhaustionAtHigh && !exhaustionAtLow) return null;
            double midpoint = bar.Low + bar.BarRange * 0.5;
            if (exhaustionAtHigh && bar.Close >= midpoint) return null;
            if (exhaustionAtLow && bar.Close <= midpoint) return null;
            var direction = exhaustionAtHigh ? IntSignalDirection.Short : IntSignalDirection.Long;
            double distanceFromExtreme = exhaustionAtHigh ? bar.High - bar.Close : bar.Close - bar.Low;
            double strength = SysMath.Min(1.0, distanceFromExtreme / bar.BarRange);
            return new IntSignalResult { SignalId = "EXH-01", Direction = direction, Strength = strength, Price = exhaustionAtHigh ? bar.High : bar.Low };
        }

        public static IntSignalResult DetectExh02(List<IntFootprintBar> bars)
        {
            if (bars == null || bars.Count < 3) return null;
            int n = bars.Count;
            long d0 = bars[n - 1].BarDelta, d1 = bars[n - 2].BarDelta, d2 = bars[n - 3].BarDelta;
            if (d2 == 0) return null;
            bool positive = d2 > 0;
            if (positive && (d1 <= 0 || d0 <= 0)) return null;
            if (!positive && (d1 >= 0 || d0 >= 0)) return null;
            double absD0 = SysMath.Abs(d0), absD1 = SysMath.Abs(d1), absD2 = SysMath.Abs(d2);
            if (absD2 == 0) return null;
            if (absD0 >= 0.7 * absD1) return null;
            if (absD1 >= 0.7 * absD2) return null;
            bool pricePushingUp = bars[n - 1].Close > bars[n - 3].Close;
            bool pricePushingDown = bars[n - 1].Close < bars[n - 3].Close;
            if (positive && !pricePushingUp) return null;
            if (!positive && !pricePushingDown) return null;
            var direction = positive ? IntSignalDirection.Short : IntSignalDirection.Long;
            return new IntSignalResult { SignalId = "EXH-02", Direction = direction, Strength = SysMath.Min(1.0, 1.0 - (absD0 / absD2)), Price = bars[n - 1].Close };
        }

        public static IntSignalResult DetectDelt01(IntDeltaPipeline dp)
        {
            if (dp == null || dp.Count < 10) return null;
            double divergence = dp.CheckDivergence(10);
            if (divergence == 0) return null;
            var direction = divergence > 0 ? IntSignalDirection.Long : IntSignalDirection.Short;
            return new IntSignalResult { SignalId = "DELT-01", Direction = direction, Strength = SysMath.Min(1.0, SysMath.Abs(divergence) / 500.0), Price = dp.GetClose(0) };
        }

        public static IntSignalResult DetectDelt02(IntDeltaPipeline dp)
        {
            if (dp == null || dp.Count < 11) return null;
            double accel = dp.DeltaAccel;
            double roc = dp.DeltaRoC;
            if (SysMath.Abs(accel) < 1.0) return null;
            IntSignalDirection direction;
            if (accel > 0 && roc < 0) direction = IntSignalDirection.Long;
            else if (accel < 0 && roc > 0) direction = IntSignalDirection.Short;
            else return null;
            return new IntSignalResult { SignalId = "DELT-02", Direction = direction, Strength = SysMath.Min(1.0, SysMath.Abs(accel) / 100.0), Price = dp.GetClose(0) };
        }

        public static IntSignalResult DetectImb01(IntFootprintBar bar, double imbalanceRatio)
        {
            if (bar == null || bar.Levels.Count < 3) return null;
            int bestRun = 0; bool bestAskDom = false; double bestStartPrice = 0;
            int currentRun = 0; bool currentAskDom = false; double currentStartPrice = 0;
            foreach (var kv in bar.Levels)
            {
                var cell = kv.Value;
                if (cell.TotalVol < 5 || cell.ImbalanceRatio < imbalanceRatio) { currentRun = 0; continue; }
                bool askDom = cell.AskVol > cell.BidVol;
                if (currentRun == 0 || askDom != currentAskDom) { currentRun = 1; currentStartPrice = kv.Key; currentAskDom = askDom; }
                else currentRun++;
                if (currentRun > bestRun) { bestRun = currentRun; bestStartPrice = currentStartPrice; bestAskDom = currentAskDom; }
            }
            if (bestRun < 3) return null;
            var direction = bestAskDom ? IntSignalDirection.Long : IntSignalDirection.Short;
            return new IntSignalResult { SignalId = "IMB-01", Direction = direction, Strength = SysMath.Min(1.0, (bestRun - 2.0) / 5.0), Price = bestStartPrice };
        }

        public static IntSignalResult DetectIce01(IntFootprintBar bar, bool isDomAvailable, Func<double, int> getRefillCount)
        {
            if (bar == null || bar.Levels.Count == 0 || !isDomAvailable || getRefillCount == null) return null;
            double bestPrice = 0; int bestRefills = 0; IntCell bestCell = null;
            foreach (var kv in bar.Levels)
            {
                int refills = getRefillCount(kv.Key);
                if (refills >= 3 && refills > bestRefills) { bestRefills = refills; bestPrice = kv.Key; bestCell = kv.Value; }
            }
            if (bestCell == null) return null;
            var direction = bestCell.BidVol > bestCell.AskVol ? IntSignalDirection.Long : IntSignalDirection.Short;
            return new IntSignalResult { SignalId = "ICE-01", Direction = direction, Strength = SysMath.Min(1.0, bestRefills / 10.0), Price = bestPrice };
        }

        public static IntSignalResult DetectLiqSw01(IntFootprintBar bar, List<IntLevel> nearbyLevels, double avgBarVol)
        {
            if (bar == null || nearbyLevels == null || nearbyLevels.Count == 0) return null;
            if (bar.BarRange <= 0 || (avgBarVol > 0 && bar.TotalVol <= 2.0 * avgBarVol)) return null;
            IntSignalResult best = null; double bestStrength = 0;
            foreach (var level in nearbyLevels)
            {
                if (bar.High > level.Price && bar.Close < level.Price)
                {
                    double s = SysMath.Min(1.0, SysMath.Abs(bar.Close - bar.High) / bar.BarRange);
                    if (s > bestStrength) { bestStrength = s; best = new IntSignalResult { SignalId = "LIQSW-01", Direction = IntSignalDirection.Short, Strength = s, Price = level.Price }; }
                }
                if (bar.Low < level.Price && bar.Close > level.Price)
                {
                    double s = SysMath.Min(1.0, SysMath.Abs(bar.Close - bar.Low) / bar.BarRange);
                    if (s > bestStrength) { bestStrength = s; best = new IntSignalResult { SignalId = "LIQSW-01", Direction = IntSignalDirection.Long, Strength = s, Price = level.Price }; }
                }
            }
            return best;
        }

        public static IntSignalResult DetectFail01(IntFootprintBar bar)
        {
            if (bar == null || bar.Levels.Count == 0 || bar.BarRange <= 0) return null;
            IntCell pocCell;
            if (!bar.Levels.TryGetValue(bar.PocPrice, out pocCell) || pocCell == null) return null;
            bool atHigh = SysMath.Abs(bar.PocPrice - bar.High) <= 0.25;
            bool atLow = SysMath.Abs(bar.PocPrice - bar.Low) <= 0.25;
            if (!atHigh && !atLow) return null;
            double midpoint = bar.Low + bar.BarRange * 0.5;
            if (atHigh && bar.Close >= midpoint) return null;
            if (atLow && bar.Close <= midpoint) return null;
            int levelsNearExtreme = 0;
            double extremePrice = atHigh ? bar.High : bar.Low;
            foreach (var kv in bar.Levels) if (SysMath.Abs(kv.Key - extremePrice) <= 0.25) levelsNearExtreme++;
            if (levelsNearExtreme > 2) return null;
            var direction = atHigh ? IntSignalDirection.Short : IntSignalDirection.Long;
            double avgLevelVol = (double)bar.TotalVol / bar.Levels.Count;
            return new IntSignalResult { SignalId = "FAIL-01", Direction = direction, Strength = SysMath.Min(1.0, pocCell.TotalVol / (avgLevelVol * 3.0)), Price = extremePrice };
        }

        public static IntSignalResult DetectTrap01(IntFootprintBar bar, List<IntFootprintBar> bars, List<IntLevel> nearbyLevels, double avgBarVol)
        {
            if (bar == null || bars == null || bars.Count < 2 || nearbyLevels == null || nearbyLevels.Count == 0) return null;
            var priorBar = bars[bars.Count - 2];
            IntSignalResult best = null; double bestStrength = 0;
            foreach (var level in nearbyLevels)
            {
                if (priorBar.High > level.Price && bar.Close < level.Price)
                {
                    double s = avgBarVol > 0 ? SysMath.Min(1.0, (double)priorBar.TotalVol / (avgBarVol * 2.0)) : 0.5;
                    if (s > bestStrength) { bestStrength = s; best = new IntSignalResult { SignalId = "TRAP-01", Direction = IntSignalDirection.Short, Strength = s, Price = level.Price }; }
                }
                if (priorBar.Low < level.Price && bar.Close > level.Price)
                {
                    double s = avgBarVol > 0 ? SysMath.Min(1.0, (double)priorBar.TotalVol / (avgBarVol * 2.0)) : 0.5;
                    if (s > bestStrength) { bestStrength = s; best = new IntSignalResult { SignalId = "TRAP-01", Direction = IntSignalDirection.Long, Strength = s, Price = level.Price }; }
                }
            }
            return best;
        }

        public static IntSignalResult DetectReg01(IntMarketState state, List<IntFootprintBar> bars)
        {
            if (state == null || bars == null || bars.Count < 10) return null;
            var lastBar = bars[bars.Count - 1];
            string regime; double confidence;
            if (state.VolEma > 0 && lastBar.TotalVol < 0.5 * state.VolEma)
            { regime = "Thin"; confidence = SysMath.Max(0, SysMath.Min(1.0, 1.0 - (double)lastBar.TotalVol / (state.VolEma * 0.5))); }
            else { regime = "Ranging"; confidence = 0.5; }
            return new IntSignalResult { SignalId = "REG-01", Direction = IntSignalDirection.Neutral, Strength = confidence, Price = lastBar.Close, Detail = regime };
        }
    }
    #endregion

    // ═══════════════════════════════════════════════════════════════════
    //  INTEGRATION TESTS
    // ═══════════════════════════════════════════════════════════════════

    [TestFixture]
    public class IntegrationTests
    {
        private IntConfig _config;

        [SetUp]
        public void Setup() => _config = IntConfig.Defaults;

        // ── Helper: Create a bar with N trades ──────────────────────────
        private IntFootprintBar CreateBar(int barIndex, double basePrice, int buyCount, int sellCount, DateTime time, long priorCvd = 0)
        {
            var bar = new IntFootprintBar { BarIndex = barIndex, BarTime = time };
            for (int i = 0; i < buyCount; i++)
                bar.AddTrade(basePrice + (i % 3) * 0.25, 5, 1);
            for (int i = 0; i < sellCount; i++)
                bar.AddTrade(basePrice - (i % 2) * 0.25, 4, 2);
            bar.Finalize(priorCvd);
            return bar;
        }

        // ── Test 1: Full 20-bar lifecycle ───────────────────────────────
        [Test]
        public void FullLifecycle_20Bars_ProducesValidScoreAndTier()
        {
            var bars = new List<IntFootprintBar>();
            var deltaPipeline = new IntDeltaPipeline();
            var marketState = new IntMarketState();
            long cvd = 0;

            var baseTime = new DateTime(2026, 5, 12, 10, 0, 0);
            for (int i = 0; i < 20; i++)
            {
                var bar = CreateBar(i, 20000.0 + i * 0.25, buyCount: 15 + i, sellCount: 10, baseTime.AddMinutes(i), cvd);
                cvd = bar.Cvd;
                deltaPipeline.OnBarFinalized(bar);
                bars.Add(bar);
                marketState.Update(bar.High, bar.Low, bar.Close, bar.TotalVol, bar.BarTime);
            }

            var lastBar = bars[bars.Count - 1];

            // Run all 12 detectors on last bar
            var signals = new List<IntSignalResult>();
            var s1 = IntDetectors.DetectAbs01(lastBar, _config.AbsorptionVolumeMultiplier);
            var s2 = IntDetectors.DetectAbs02(bars);
            var s3 = IntDetectors.DetectExh01(lastBar);
            var s4 = IntDetectors.DetectExh02(bars);
            var s5 = IntDetectors.DetectDelt01(deltaPipeline);
            var s6 = IntDetectors.DetectDelt02(deltaPipeline);
            var s7 = IntDetectors.DetectImb01(lastBar, _config.ImbalanceRatio);
            var s8 = IntDetectors.DetectIce01(lastBar, false, null);
            var s9 = IntDetectors.DetectLiqSw01(lastBar, new List<IntLevel>(), 0);
            var s10 = IntDetectors.DetectFail01(lastBar);
            var s11 = IntDetectors.DetectTrap01(lastBar, bars, new List<IntLevel>(), 0);
            var s12 = IntDetectors.DetectReg01(marketState, bars);

            foreach (var s in new[] { s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12 })
                if (s != null) signals.Add(s);

            // Run scoring on whatever signals fired
            var result = IntScoringEngine.Run(signals, _config, IntRegime.Ranging, false);

            // Assertions: score in valid range, tier is one of 5 values
            Assert.GreaterOrEqual(result.Score, 0, "Score must be >= 0");
            Assert.LessOrEqual(result.Score, 100, "Score must be <= 100");
            Assert.That(new[] { IntTier.Elite, IntTier.High, IntTier.Moderate, IntTier.Wait, IntTier.DoNotTrade },
                Contains.Item(result.Tier), "Tier must be one of the 5 valid values");
        }

        // ── Test 2: Multi-bar signal tracking (ABS-02 passive absorption) ──
        [Test]
        public void MultiBarSignalTracking_Abs02_FiresOnThreeBarLookback()
        {
            var bars = new List<IntFootprintBar>();
            var baseTime = new DateTime(2026, 5, 12, 10, 0, 0);
            long cvd = 0;

            // Create 10 bars with moderate delta so avgBarDelta is reasonable
            for (int i = 0; i < 7; i++)
            {
                var bar = new IntFootprintBar { BarIndex = i, BarTime = baseTime.AddMinutes(i) };
                bar.AddTrade(20000.0, 10, 2);
                bar.AddTrade(20000.0, 8, 1);
                bar.Finalize(cvd);
                cvd = bar.Cvd;
                bars.Add(bar);
            }

            // Now create 3 bars with MASSIVE sell pressure but minimal price movement
            // cumDelta over last 3 bars must be > 3× avgBarDelta
            // avgBarDelta across all bars ~ 2-3 (from the first 7 bars)
            // We need cumDelta over 3 bars > 3 * ~10 = 30
            for (int i = 7; i < 10; i++)
            {
                var bar = new IntFootprintBar { BarIndex = i, BarTime = baseTime.AddMinutes(i) };
                // Heavy sell at same price (passive buyer absorbing)
                bar.AddTrade(20000.0, 200, 2);   // massive sell
                bar.AddTrade(20000.0, 5, 1);     // tiny buy
                bar.Finalize(cvd);
                cvd = bar.Cvd;
                bars.Add(bar);
            }

            var result = IntDetectors.DetectAbs02(bars);
            Assert.IsNotNull(result, "ABS-02 should fire when heavy delta over 3 bars with minimal price movement");
            Assert.AreEqual("ABS-02", result.SignalId);
            Assert.AreEqual(IntSignalDirection.Long, result.Direction, "Negative delta absorbed → bullish signal");
        }

        // ── Test 3: Session rollover handling ───────────────────────────
        [Test]
        public void SessionRollover_CapturesPriorDayLevels()
        {
            var state = new IntMarketState();
            var deltaPipeline = new IntDeltaPipeline();

            // Day 1
            var day1 = new DateTime(2026, 5, 11, 10, 0, 0);
            state.Update(20100, 19900, 20050, 1000, day1);
            state.Update(20150, 19850, 20000, 1200, day1.AddMinutes(1));

            // Day 2 — session rollover
            var day2 = new DateTime(2026, 5, 12, 9, 30, 0);
            state.Update(20010, 19990, 20005, 800, day2);

            Assert.AreEqual(20150, state.PrevDayHigh, "Prior day high should be captured");
            Assert.AreEqual(19850, state.PrevDayLow, "Prior day low should be captured");
            Assert.AreEqual(20000, state.PrevDayClose, "Prior day close should be captured");

            // CVD resets on new pipeline (simulating session reset)
            deltaPipeline.Reset();
            Assert.AreEqual(0, deltaPipeline.Count, "Delta pipeline should reset");
        }

        // ── Test 4: Scoring parity (deterministic) ──────────────────────
        [Test]
        public void ScoringParity_SameInputs_ProduceIdenticalScores()
        {
            var signals = new List<IntSignalResult>
            {
                new IntSignalResult { SignalId = "ABS-01", Direction = IntSignalDirection.Long, Strength = 0.85, Price = 20000 },
                new IntSignalResult { SignalId = "EXH-01", Direction = IntSignalDirection.Long, Strength = 0.7, Price = 20000 },
                new IntSignalResult { SignalId = "DELT-01", Direction = IntSignalDirection.Long, Strength = 0.6, Price = 20000 }
            };

            var r1 = IntScoringEngine.Run(signals, _config, IntRegime.Ranging, true);
            var r2 = IntScoringEngine.Run(signals, _config, IntRegime.Ranging, true);
            var r3 = IntScoringEngine.Run(signals, _config, IntRegime.Ranging, true);

            Assert.AreEqual(r1.Score, r2.Score, 0.0001, "Run 1 vs Run 2 must be identical");
            Assert.AreEqual(r2.Score, r3.Score, 0.0001, "Run 2 vs Run 3 must be identical");
            Assert.AreEqual(r1.Tier, r2.Tier);
            Assert.AreEqual(r2.Tier, r3.Tier);
        }

        // ── Test 5: Conflicting signals reduce score ────────────────────
        [Test]
        public void ConflictingSignals_ABS01Long_DELT01Short_LowerScore()
        {
            var agreeing = new List<IntSignalResult>
            {
                new IntSignalResult { SignalId = "ABS-01", Direction = IntSignalDirection.Long, Strength = 0.8 },
                new IntSignalResult { SignalId = "DELT-01", Direction = IntSignalDirection.Long, Strength = 0.8 }
            };
            var conflicting = new List<IntSignalResult>
            {
                new IntSignalResult { SignalId = "ABS-01", Direction = IntSignalDirection.Long, Strength = 0.8 },
                new IntSignalResult { SignalId = "DELT-01", Direction = IntSignalDirection.Short, Strength = 0.8 }
            };

            var rAgree = IntScoringEngine.Run(agreeing, _config, IntRegime.Ranging, false);
            var rConflict = IntScoringEngine.Run(conflicting, _config, IntRegime.Ranging, false);

            Assert.Greater(rAgree.Score, rConflict.Score, "Conflicting signals must produce lower score");
        }

        // ── Test 6: Elite setup ─────────────────────────────────────────
        [Test]
        public void EliteSetup_FiveAgreeingSignals_AtKeyLevel_Ranging_ScoreGte90()
        {
            var signals = new List<IntSignalResult>
            {
                new IntSignalResult { SignalId = "ABS-01", Direction = IntSignalDirection.Long, Strength = 1.0 },
                new IntSignalResult { SignalId = "EXH-01", Direction = IntSignalDirection.Long, Strength = 1.0 },
                new IntSignalResult { SignalId = "DELT-01", Direction = IntSignalDirection.Long, Strength = 1.0 },
                new IntSignalResult { SignalId = "IMB-01", Direction = IntSignalDirection.Long, Strength = 1.0 },
                new IntSignalResult { SignalId = "ICE-01", Direction = IntSignalDirection.Long, Strength = 1.0 },
            };

            var result = IntScoringEngine.Run(signals, _config, IntRegime.Ranging, true);

            Assert.GreaterOrEqual(result.Score, 90, "5 agreeing signals at key level in Ranging should be Elite");
            Assert.AreEqual(IntTier.Elite, result.Tier);
        }

        // ── Test 7: DoNotTrade — single weak signal in Thin regime ──────
        [Test]
        public void DoNotTrade_SingleWeakSignal_ThinRegime()
        {
            var signals = new List<IntSignalResult>
            {
                new IntSignalResult { SignalId = "ABS-01", Direction = IntSignalDirection.Long, Strength = 0.1 }
            };

            var result = IntScoringEngine.Run(signals, _config, IntRegime.Thin, false);

            Assert.Less(result.Score, 40, "Single weak signal in Thin should be < 40");
            Assert.AreEqual(IntTier.DoNotTrade, result.Tier);
        }

        // ── Test 8: Empty bar handling ──────────────────────────────────
        [Test]
        public void EmptyBar_ZeroVolume_NoCrash_NoSignals()
        {
            var emptyBar = new IntFootprintBar
            {
                BarIndex = 0,
                BarTime = DateTime.Now,
                Open = 0, High = 0, Low = 0, Close = 0,
                TotalVol = 0
            };
            emptyBar.Finalize();

            // All detectors should return null for empty bar
            Assert.IsNull(IntDetectors.DetectAbs01(emptyBar, 3.0));
            Assert.IsNull(IntDetectors.DetectExh01(emptyBar));
            Assert.IsNull(IntDetectors.DetectImb01(emptyBar, 3.0));
            Assert.IsNull(IntDetectors.DetectFail01(emptyBar));

            // Scoring on empty signals → WAIT/DoNotTrade
            var result = IntScoringEngine.Run(new List<IntSignalResult>(), _config, IntRegime.Ranging, false);
            Assert.AreEqual(IntTier.DoNotTrade, result.Tier);
        }

        // ── Test 9: First bar guard ─────────────────────────────────────
        [Test]
        public void FirstBarGuard_NoSignals_WhenSingleBar()
        {
            var bars = new List<IntFootprintBar>();
            var bar = CreateBar(0, 20000.0, 5, 5, DateTime.Now);
            bars.Add(bar);

            // Detectors requiring lookback should return null
            Assert.IsNull(IntDetectors.DetectAbs02(bars), "ABS-02 needs 3 bars minimum — not 1");
            Assert.IsNull(IntDetectors.DetectExh02(bars), "EXH-02 needs 3 bars minimum — not 1");

            // Delta pipeline with only 1 bar shouldn't fire divergence
            var dp = new IntDeltaPipeline();
            dp.OnBarFinalized(bar);
            Assert.IsNull(IntDetectors.DetectDelt01(dp), "DELT-01 needs 10 bars");
            Assert.IsNull(IntDetectors.DetectDelt02(dp), "DELT-02 needs 11 bars");
        }

        // ── Test 10: All 12 detectors called without crash ──────────────
        [Test]
        public void AllDetectorsCalled_NoCrash()
        {
            var bars = new List<IntFootprintBar>();
            var dp = new IntDeltaPipeline();
            var state = new IntMarketState();
            long cvd = 0;

            var baseTime = new DateTime(2026, 5, 12, 10, 0, 0);
            for (int i = 0; i < 15; i++)
            {
                var bar = CreateBar(i, 20000 + i * 0.5, buyCount: 10, sellCount: 8, baseTime.AddMinutes(i), cvd);
                cvd = bar.Cvd;
                dp.OnBarFinalized(bar);
                bars.Add(bar);
                state.Update(bar.High, bar.Low, bar.Close, bar.TotalVol, bar.BarTime);
            }

            var lastBar = bars[bars.Count - 1];
            var levels = new List<IntLevel> { new IntLevel { Type = IntLevelType.PrevDayLow, Price = 20000 } };

            // All 12 detectors called — no exceptions expected
            Assert.DoesNotThrow(() =>
            {
                IntDetectors.DetectAbs01(lastBar, _config.AbsorptionVolumeMultiplier);
                IntDetectors.DetectAbs02(bars);
                IntDetectors.DetectExh01(lastBar);
                IntDetectors.DetectExh02(bars);
                IntDetectors.DetectDelt01(dp);
                IntDetectors.DetectDelt02(dp);
                IntDetectors.DetectImb01(lastBar, _config.ImbalanceRatio);
                IntDetectors.DetectIce01(lastBar, false, null);
                IntDetectors.DetectLiqSw01(lastBar, levels, 500);
                IntDetectors.DetectFail01(lastBar);
                IntDetectors.DetectTrap01(lastBar, bars, levels, 500);
                IntDetectors.DetectReg01(state, bars);
            }, "All 12 detectors must run without exception");
        }

        // ── Test 11: DeltaPipeline full lifecycle ───────────────────────
        [Test]
        public void DeltaPipeline_20Bars_CvdTracksCorrectly()
        {
            var dp = new IntDeltaPipeline();
            long cvd = 0;
            var baseTime = new DateTime(2026, 5, 12, 10, 0, 0);

            for (int i = 0; i < 20; i++)
            {
                var bar = new IntFootprintBar { BarIndex = i, BarTime = baseTime.AddMinutes(i) };
                bar.AddTrade(20000 + i * 0.25, 10, 1);
                bar.AddTrade(20000 + i * 0.25, 3, 2);
                bar.Finalize(cvd);
                cvd = bar.Cvd;
                dp.OnBarFinalized(bar);
            }

            Assert.AreEqual(20, dp.Count);
            // CVD should be monotonically increasing (more buys than sells each bar)
            Assert.Greater(dp.GetCvd(0), dp.GetCvd(19), "CVD should increase over 20 bars with net buying");
        }

        // ── Test 12: MarketState ATR stabilizes after 20 bars ───────────
        [Test]
        public void MarketState_Atr20_StabilizesAfter20Bars()
        {
            var state = new IntMarketState();
            var baseTime = new DateTime(2026, 5, 12, 10, 0, 0);

            for (int i = 0; i < 25; i++)
            {
                double high = 20000 + 5;
                double low = 20000 - 5;
                state.Update(high, low, 20000, 1000, baseTime.AddMinutes(i));
            }

            // With constant 10-point range bars, ATR20 should = 10
            Assert.AreEqual(10.0, state.Atr20, 0.5, "ATR20 with constant 10-point bars should be ~10");
        }
    }
}
