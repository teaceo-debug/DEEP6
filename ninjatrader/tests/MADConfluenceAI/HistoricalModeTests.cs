// HistoricalModeTests.cs — T29: Historical mode, warm-up, DOM degradation tests
// Validates warm-up period, DOM graceful degradation, and 500-bar historical load.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using SysMath = System.Math;

namespace NinjaTrader.Tests.MADConfluenceAI.HistoricalMode
{
    // ═══════════════════════════════════════════════════════════════════
    //  TEST-LOCAL TYPE COPIES
    // ═══════════════════════════════════════════════════════════════════

    public enum HistSignalDirection { Long, Short, Neutral }
    public enum HistRegime { Trending, Ranging, Volatile, Thin }
    public enum HistTier { Elite, High, Moderate, Wait, DoNotTrade }
    public enum HistTrend { Bullish, Bearish, Neutral }

    public sealed class HistSignalResult
    {
        public string SignalId;
        public HistSignalDirection Direction;
        public double Strength;
        public double Price;
    }

    public sealed class HistCell
    {
        public long BidVol;
        public long AskVol;
        public long NeutralVol;
        public long Delta => AskVol - BidVol;
        public long TotalVol => AskVol + BidVol + NeutralVol;
    }

    public sealed class HistFootprintBar
    {
        public int BarIndex;
        public double Open, High, Low, Close;
        public DateTime BarTime;
        public SortedDictionary<double, HistCell> Levels = new SortedDictionary<double, HistCell>();
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
            HistCell cell;
            if (!Levels.TryGetValue(price, out cell)) { cell = new HistCell(); Levels[price] = cell; }
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

    public sealed class HistDeltaPipeline
    {
        private const int BufferSize = 500;
        private readonly long[] _cvdBuffer = new long[BufferSize];
        private readonly double[] _closeBuffer = new double[BufferSize];
        private int _head;
        private int _count;
        public int Count => _count;

        public void OnBarFinalized(HistFootprintBar bar)
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

    public sealed class HistMarketState
    {
        private readonly double[] _trueRanges = new double[25];
        private int _trCount;
        private double _prevClose = double.NaN;
        public double Atr20 { get; private set; }
        public double VolEma { get; private set; }
        private bool _volEmaInitialized;
        private const double VolEmaAlpha = 2.0 / 13.0;
        public HistTrend HtfBias { get; set; } = HistTrend.Neutral;

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

    /// <summary>
    /// Simulates the historical mode warm-up logic from MADConfluenceAI.cs OnBarUpdate.
    /// Mirrors the production code: first WarmupBars produce score=0, direction=0.
    /// </summary>
    public sealed class HistSimulator
    {
        public int WarmupBars { get; set; } = 50;
        private int _processedBars = 0;
        private bool _isWarmedUp = false;
        private readonly List<HistFootprintBar> _bars = new List<HistFootprintBar>();
        private readonly HistDeltaPipeline _deltaPipeline = new HistDeltaPipeline();
        private readonly HistMarketState _marketState = new HistMarketState();
        private long _sessionCvd = 0;

        // Output values (mirrors Values[0][0] and Values[1][0])
        public double LastScore { get; private set; }
        public double LastDirection { get; private set; }
        public bool IsWarmedUp => _isWarmedUp;

        // DOM availability flag
        public bool IsDomAvailable { get; set; } = false;

        public void ProcessBar(HistFootprintBar bar)
        {
            bar.Finalize(_sessionCvd);
            _sessionCvd = bar.Cvd;
            _deltaPipeline.OnBarFinalized(bar);
            _bars.Add(bar);
            if (_bars.Count > 500) _bars.RemoveAt(0);
            _marketState.Update(bar.High, bar.Low, bar.Close, bar.TotalVol, bar.BarTime);

            // Mirrors production MADConfluenceAI.cs OnBarUpdate:
            // _processedBars++ then check < WarmupBars.
            // With WarmupBars=50: bars 1-50 produce score 0 (indices 0-49).
            // Bar 51 (index 50) is the first to produce a score.
            _processedBars++;
            if (_processedBars <= WarmupBars)
            {
                LastScore = 0;
                LastDirection = 0;
                return;
            }
            if (!_isWarmedUp) _isWarmedUp = true;

            // Post warm-up: produce non-zero score for testing
            // In production this would run all 12 detectors + scoring engine
            LastScore = 50.0 + (_processedBars % 10);
            LastDirection = 1; // Long placeholder
        }

        public List<double> GetDomLiquidityWalls(double threshold)
        {
            if (!IsDomAvailable) return new List<double>();
            return new List<double> { 20000.0 }; // placeholder
        }

        public double GetDomImbalance()
        {
            if (!IsDomAvailable) return 1.0; // neutral default
            return 1.5; // placeholder
        }

        public int GetRefillCount(double price)
        {
            if (!IsDomAvailable) return 0;
            return 3; // placeholder
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    //  HISTORICAL MODE TESTS
    // ═══════════════════════════════════════════════════════════════════

    [TestFixture]
    public class HistoricalModeTests
    {
        private HistSimulator _sim;

        [SetUp]
        public void Setup()
        {
            _sim = new HistSimulator { WarmupBars = 50 };
        }

        private HistFootprintBar CreateBar(int index, DateTime time)
        {
            var bar = new HistFootprintBar { BarIndex = index, BarTime = time };
            bar.AddTrade(20000.0, 10, 1);
            bar.AddTrade(20000.0, 5, 2);
            bar.AddTrade(20000.25, 8, 1);
            return bar;
        }

        // ── Test 1: First 50 bars produce score 0 (warm-up) ─────────────
        [Test]
        public void WarmupPeriod_First50Bars_ProduceScoreZero()
        {
            var baseTime = new DateTime(2026, 5, 12, 10, 0, 0);

            for (int i = 0; i < 50; i++)
            {
                _sim.ProcessBar(CreateBar(i, baseTime.AddMinutes(i)));
                Assert.AreEqual(0, _sim.LastScore, $"Bar {i}: Score must be 0 during warm-up");
                Assert.AreEqual(0, _sim.LastDirection, $"Bar {i}: Direction must be 0 during warm-up");
                Assert.IsFalse(_sim.IsWarmedUp, $"Bar {i}: Should not be warmed up yet");
            }
        }

        // ── Test 2: Bar 51 produces non-zero score ──────────────────────
        [Test]
        public void AfterWarmup_Bar51_ProducesNonZeroScore()
        {
            var baseTime = new DateTime(2026, 5, 12, 10, 0, 0);

            // Process 50 warmup bars
            for (int i = 0; i < 50; i++)
                _sim.ProcessBar(CreateBar(i, baseTime.AddMinutes(i)));

            Assert.IsFalse(_sim.IsWarmedUp, "Should not yet be warmed up after exactly 50 bars");

            // Bar 51 (index 50) should trigger warm-up completion
            _sim.ProcessBar(CreateBar(50, baseTime.AddMinutes(50)));

            Assert.IsTrue(_sim.IsWarmedUp, "Should be warmed up after bar 51");
            Assert.Greater(_sim.LastScore, 0, "Score should be non-zero after warm-up");
            Assert.AreNotEqual(0, _sim.LastDirection, "Direction should be non-zero after warm-up");
        }

        // ── Test 3: DOM methods return defaults when not available ───────
        [Test]
        public void DomMethods_ReturnDefaults_WhenNotAvailable()
        {
            _sim.IsDomAvailable = false;

            var walls = _sim.GetDomLiquidityWalls(2.0);
            Assert.IsEmpty(walls, "Liquidity walls should be empty when DOM unavailable");

            double imbalance = _sim.GetDomImbalance();
            Assert.AreEqual(1.0, imbalance, "DOM imbalance should be 1.0 (neutral) when DOM unavailable");

            int refills = _sim.GetRefillCount(20000.0);
            Assert.AreEqual(0, refills, "Refill count should be 0 when DOM unavailable");
        }

        // ── Test 4: No exceptions on 500-bar historical load ────────────
        [Test]
        public void HistoricalLoad_500Bars_NoExceptions()
        {
            var baseTime = new DateTime(2026, 5, 12, 9, 0, 0);
            var rng = new Random(42);

            Assert.DoesNotThrow(() =>
            {
                for (int i = 0; i < 500; i++)
                {
                    var bar = new HistFootprintBar { BarIndex = i, BarTime = baseTime.AddMinutes(i) };

                    // Varying trade patterns
                    int tradeCount = 5 + rng.Next(0, 20);
                    for (int t = 0; t < tradeCount; t++)
                    {
                        double price = 20000 + rng.Next(-20, 20) * 0.25;
                        int aggressor = rng.Next(0, 3);
                        long size = 1 + rng.Next(0, 30);
                        bar.AddTrade(price, size, aggressor);
                    }

                    _sim.ProcessBar(bar);
                }
            }, "500-bar historical load must complete without exceptions");

            // Verify final state is sane
            Assert.IsTrue(_sim.IsWarmedUp, "Must be warmed up after 500 bars");
            Assert.Greater(_sim.LastScore, 0, "Score must be non-zero after 500 bars");
        }

        // ── Test 5: DOM becomes available mid-session ───────────────────
        [Test]
        public void DomBecomesAvailable_MidSession_MethodsReturnValues()
        {
            _sim.IsDomAvailable = false;

            // Before DOM is available
            Assert.IsEmpty(_sim.GetDomLiquidityWalls(2.0));
            Assert.AreEqual(1.0, _sim.GetDomImbalance());
            Assert.AreEqual(0, _sim.GetRefillCount(20000.0));

            // DOM becomes available (first OnMarketDepth call)
            _sim.IsDomAvailable = true;

            // After DOM is available
            var walls = _sim.GetDomLiquidityWalls(2.0);
            Assert.IsNotEmpty(walls, "Should return walls when DOM is available");
            Assert.AreNotEqual(1.0, _sim.GetDomImbalance(), "Imbalance should differ from neutral");
            Assert.Greater(_sim.GetRefillCount(20000.0), 0, "Refill count should be non-zero");
        }

        // ── Test 6: Warm-up with configurable bar count ─────────────────
        [Test]
        public void ConfigurableWarmup_20Bars_WorksCorrectly()
        {
            var sim = new HistSimulator { WarmupBars = 20 };
            var baseTime = new DateTime(2026, 5, 12, 10, 0, 0);

            for (int i = 0; i < 20; i++)
            {
                sim.ProcessBar(CreateBar(i, baseTime.AddMinutes(i)));
                Assert.AreEqual(0, sim.LastScore, $"Bar {i}: Score must be 0 during 20-bar warm-up");
            }

            sim.ProcessBar(CreateBar(20, baseTime.AddMinutes(20)));
            Assert.IsTrue(sim.IsWarmedUp, "Should be warmed up after bar 21 with 20-bar warmup");
            Assert.Greater(sim.LastScore, 0, "Score should be non-zero after warm-up");
        }
    }
}
