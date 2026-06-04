// PerformanceTests.cs — T28: Performance profiling for MADConfluenceAI
// Validates bar processing, tick processing, memory, and delta pipeline latency.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using NUnit.Framework;
using SysMath = System.Math;

namespace NinjaTrader.Tests.MADConfluenceAI.Performance
{
    // ═══════════════════════════════════════════════════════════════════
    //  TEST-LOCAL TYPE COPIES
    // ═══════════════════════════════════════════════════════════════════

    public enum PerfSignalDirection { Long, Short, Neutral }
    public enum PerfRegime { Trending, Ranging, Volatile, Thin }
    public enum PerfTier { Elite, High, Moderate, Wait, DoNotTrade }
    public enum PerfTrend { Bullish, Bearish, Neutral }

    public sealed class PerfSignalResult
    {
        public string SignalId;
        public PerfSignalDirection Direction;
        public double Strength;
        public string Detail;
        public double Price;
    }

    public sealed class PerfCell
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

    public sealed class PerfFootprintBar
    {
        public int BarIndex;
        public double Open, High, Low, Close;
        public DateTime BarTime;
        public SortedDictionary<double, PerfCell> Levels = new SortedDictionary<double, PerfCell>();
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
            PerfCell cell;
            if (!Levels.TryGetValue(price, out cell)) { cell = new PerfCell(); Levels[price] = cell; }
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

    public sealed class PerfDeltaPipeline
    {
        private const int BufferSize = 500;
        private readonly long[] _cvdBuffer = new long[BufferSize];
        private readonly double[] _closeBuffer = new double[BufferSize];
        private int _head;
        private int _count;
        public int Count => _count;

        public void OnBarFinalized(PerfFootprintBar bar)
        {
            _cvdBuffer[_head] = bar.Cvd;
            _closeBuffer[_head] = bar.Close;
            _head = (_head + 1) % BufferSize;
            if (_count < BufferSize) _count++;
        }

        public void Reset()
        {
            _head = 0; _count = 0;
            Array.Clear(_cvdBuffer, 0, BufferSize);
            Array.Clear(_closeBuffer, 0, BufferSize);
        }
    }

    public sealed class PerfMarketState
    {
        private readonly double[] _trueRanges = new double[25];
        private int _trCount;
        private double _prevClose = double.NaN;
        public double Atr20 { get; private set; }
        public double VolEma { get; private set; }
        private bool _volEmaInitialized;
        private const double VolEmaAlpha = 2.0 / 13.0;
        public PerfTrend HtfBias { get; set; } = PerfTrend.Neutral;

        public void Update(double high, double low, double close, long volume, DateTime barTime)
        {
            double tr = double.IsNaN(_prevClose) ? high - low
                : SysMath.Max(high - low, SysMath.Max(SysMath.Abs(high - _prevClose), SysMath.Abs(low - _prevClose)));
            _trueRanges[_trCount % 25] = tr;
            _trCount++;
            if (_trCount >= 20)
            {
                double sum = 0;
                for (int i = 0; i < 20; i++) sum += _trueRanges[(_trCount - 1 - i) % 25];
                Atr20 = sum / 20.0;
            }
            _prevClose = close;
            if (!_volEmaInitialized) { VolEma = volume; _volEmaInitialized = true; }
            else VolEma = volume * VolEmaAlpha + VolEma * (1 - VolEmaAlpha);
        }
    }

    public struct PerfConfig
    {
        public double AbsorptionWeight, ExhaustionWeight, DeltaWeight, ImbalanceWeight, IcebergWeight, LiquidityWeight, TrapWeight;
        public double MinConfidenceScore, EliteThreshold, HighThreshold;
        public double AbsorptionVolumeMultiplier, ImbalanceRatio;

        public static PerfConfig Defaults => new PerfConfig
        {
            AbsorptionWeight = 1.0, ExhaustionWeight = 1.0, DeltaWeight = 1.0,
            ImbalanceWeight = 1.0, IcebergWeight = 1.0, LiquidityWeight = 1.0, TrapWeight = 1.0,
            MinConfidenceScore = 60, EliteThreshold = 90, HighThreshold = 75,
            AbsorptionVolumeMultiplier = 3.0, ImbalanceRatio = 3.0
        };
    }

    public sealed class PerfScorerResult
    {
        public double Score;
        public PerfTier Tier;
        public PerfSignalDirection Direction;
        public List<PerfSignalResult> ContributingSignals = new List<PerfSignalResult>();
    }

    public static class PerfScoringEngine
    {
        public static PerfScorerResult Run(List<PerfSignalResult> signals, PerfConfig config, PerfRegime regime)
        {
            var result = new PerfScorerResult { Score = 0, Tier = PerfTier.DoNotTrade, Direction = PerfSignalDirection.Neutral };
            if (signals == null || signals.Count == 0) return result;
            int longCount = 0, shortCount = 0;
            foreach (var s in signals)
            {
                if (s.Direction == PerfSignalDirection.Long) longCount++;
                else if (s.Direction == PerfSignalDirection.Short) shortCount++;
            }
            var majorityDir = longCount > shortCount ? PerfSignalDirection.Long
                : shortCount > longCount ? PerfSignalDirection.Short : PerfSignalDirection.Neutral;
            if (majorityDir == PerfSignalDirection.Neutral) return result;

            double totalContribution = 0, maxPossibleScore = 0;
            var categorySet = new HashSet<string>();
            foreach (var s in signals)
            {
                double categoryWeight = 1.0;
                maxPossibleScore += categoryWeight;
                double directionAgreement = s.Direction == majorityDir ? 1.0 : -0.5;
                if (s.Direction == PerfSignalDirection.Neutral) directionAgreement = 0.0;
                totalContribution += s.Strength * categoryWeight * directionAgreement;
                if (s.Direction == majorityDir) result.ContributingSignals.Add(s);
            }
            double rawScore = maxPossibleScore > 0 ? (totalContribution / maxPossibleScore) * 100.0 : 0;
            rawScore = SysMath.Max(0, SysMath.Min(100, rawScore));

            if (rawScore >= 90) result.Tier = PerfTier.Elite;
            else if (rawScore >= 75) result.Tier = PerfTier.High;
            else if (rawScore >= 60) result.Tier = PerfTier.Moderate;
            else if (rawScore >= 40) result.Tier = PerfTier.Wait;
            else result.Tier = PerfTier.DoNotTrade;

            result.Score = rawScore;
            result.Direction = majorityDir;
            return result;
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    //  PERFORMANCE TESTS
    // ═══════════════════════════════════════════════════════════════════

    [TestFixture]
    public class PerformanceTests
    {
        // ── Test 1: Bar processing latency < 2ms average ────────────────
        [Test]
        public void BarProcessingLatency_100Bars_AverageLessThan2ms()
        {
            var config = PerfConfig.Defaults;
            var bars = new List<PerfFootprintBar>();
            var deltaPipeline = new PerfDeltaPipeline();
            var marketState = new PerfMarketState();
            long cvd = 0;
            var baseTime = new DateTime(2026, 5, 12, 10, 0, 0);
            var rng = new Random(42);

            // Warmup pass (JIT)
            for (int i = 0; i < 10; i++)
            {
                var warmupBar = new PerfFootprintBar { BarIndex = i, BarTime = baseTime };
                for (int t = 0; t < 50; t++)
                    warmupBar.AddTrade(20000 + rng.Next(-5, 5) * 0.25, rng.Next(1, 20), rng.Next(0, 3));
                warmupBar.Finalize(0);
            }

            var sw = Stopwatch.StartNew();

            for (int i = 0; i < 100; i++)
            {
                var bar = new PerfFootprintBar { BarIndex = i, BarTime = baseTime.AddMinutes(i) };

                // Simulate 50 ticks per bar
                for (int t = 0; t < 50; t++)
                {
                    double price = 20000 + rng.Next(-10, 10) * 0.25;
                    int aggressor = rng.Next(0, 3);
                    bar.AddTrade(price, rng.Next(1, 20), aggressor);
                }

                bar.Finalize(cvd);
                cvd = bar.Cvd;
                deltaPipeline.OnBarFinalized(bar);
                bars.Add(bar);
                marketState.Update(bar.High, bar.Low, bar.Close, bar.TotalVol, bar.BarTime);

                // Run scoring with some signals
                var signals = new List<PerfSignalResult>
                {
                    new PerfSignalResult { SignalId = "ABS-01", Direction = PerfSignalDirection.Long, Strength = 0.7 },
                    new PerfSignalResult { SignalId = "DELT-01", Direction = PerfSignalDirection.Long, Strength = 0.6 }
                };
                PerfScoringEngine.Run(signals, config, PerfRegime.Ranging);
            }

            sw.Stop();
            double avgMs = sw.Elapsed.TotalMilliseconds / 100.0;
            Assert.Less(avgMs, 2.0, $"Average bar processing latency was {avgMs:F3}ms, must be < 2ms");
            TestContext.WriteLine($"Bar processing: {avgMs:F3}ms avg over 100 bars ({sw.Elapsed.TotalMilliseconds:F1}ms total)");
        }

        // ── Test 2: Tick processing latency < 0.05ms (50us) average ────
        [Test]
        public void TickProcessingLatency_10000Ticks_AverageLessThan50us()
        {
            var bar = new PerfFootprintBar { BarIndex = 0, BarTime = DateTime.Now };
            var rng = new Random(42);

            // Warmup (JIT)
            for (int i = 0; i < 1000; i++)
                bar.AddTrade(20000 + rng.Next(-5, 5) * 0.25, rng.Next(1, 20), rng.Next(0, 3));
            bar = new PerfFootprintBar { BarIndex = 0, BarTime = DateTime.Now };

            var sw = Stopwatch.StartNew();

            for (int i = 0; i < 10000; i++)
            {
                double price = 20000 + rng.Next(-20, 20) * 0.25;
                int aggressor = rng.Next(0, 3);
                long size = rng.Next(1, 50);
                bar.AddTrade(price, size, aggressor);
            }

            sw.Stop();
            double avgUs = sw.Elapsed.TotalMilliseconds / 10000.0 * 1000.0; // microseconds
            double avgMs = sw.Elapsed.TotalMilliseconds / 10000.0;
            Assert.Less(avgMs, 0.05, $"Average tick latency was {avgUs:F1}us ({avgMs:F4}ms), must be < 50us");
            TestContext.WriteLine($"Tick processing: {avgUs:F1}us avg over 10,000 ticks ({sw.Elapsed.TotalMilliseconds:F1}ms total)");
        }

        // ── Test 3: Memory allocation < 10KB per AddTrade call ──────────
        [Test]
        public void MemoryAllocation_100AddTrade_LessThan10KBAverage()
        {
            var bar = new PerfFootprintBar { BarIndex = 0, BarTime = DateTime.Now };
            var rng = new Random(42);

            // Warmup (force GC, stabilize)
            for (int i = 0; i < 500; i++)
                bar.AddTrade(20000 + rng.Next(-5, 5) * 0.25, rng.Next(1, 20), rng.Next(0, 3));
            bar = new PerfFootprintBar { BarIndex = 0, BarTime = DateTime.Now };
            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();

            long before = GC.GetAllocatedBytesForCurrentThread();

            for (int i = 0; i < 100; i++)
            {
                double price = 20000 + (i % 20) * 0.25; // Reuse price levels to minimize new cell allocation
                bar.AddTrade(price, rng.Next(1, 20), rng.Next(0, 3));
            }

            long after = GC.GetAllocatedBytesForCurrentThread();
            long allocatedBytes = after - before;
            double avgKB = (double)allocatedBytes / 100.0 / 1024.0;

            Assert.Less(avgKB, 10.0, $"Average allocation was {avgKB:F2}KB per AddTrade, must be < 10KB");
            TestContext.WriteLine($"Memory: {avgKB:F2}KB avg per AddTrade ({allocatedBytes / 1024.0:F1}KB total for 100 calls)");
        }

        // ── Test 4: Delta pipeline < 0.1ms per bar ──────────────────────
        [Test]
        public void DeltaPipelinePerformance_1000Bars_LessThan01msPerBar()
        {
            var pipeline = new PerfDeltaPipeline();
            var rng = new Random(42);

            // Warmup
            for (int i = 0; i < 50; i++)
            {
                var warmup = new PerfFootprintBar { BarIndex = i };
                warmup.AddTrade(20000, 10, 1);
                warmup.Finalize(0);
                pipeline.OnBarFinalized(warmup);
            }
            pipeline.Reset();

            long cvd = 0;
            var bars = new PerfFootprintBar[1000];
            for (int i = 0; i < 1000; i++)
            {
                bars[i] = new PerfFootprintBar { BarIndex = i, BarTime = DateTime.Now.AddMinutes(i) };
                bars[i].AddTrade(20000 + rng.Next(-10, 10) * 0.25, rng.Next(1, 30), rng.Next(0, 3));
                bars[i].AddTrade(20000 + rng.Next(-10, 10) * 0.25, rng.Next(1, 30), rng.Next(0, 3));
                bars[i].Finalize(cvd);
                cvd = bars[i].Cvd;
            }

            var sw = Stopwatch.StartNew();

            for (int i = 0; i < 1000; i++)
                pipeline.OnBarFinalized(bars[i]);

            sw.Stop();
            double avgMs = sw.Elapsed.TotalMilliseconds / 1000.0;
            Assert.Less(avgMs, 0.1, $"Delta pipeline avg was {avgMs:F4}ms per bar, must be < 0.1ms");
            TestContext.WriteLine($"Delta pipeline: {avgMs:F4}ms avg over 1,000 bars ({sw.Elapsed.TotalMilliseconds:F2}ms total)");
        }
    }
}
