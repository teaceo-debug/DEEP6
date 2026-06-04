// DeltaPipelineTests.cs — TDD tests for MADDeltaPipeline: CVD recording,
// divergence detection, DeltaRoC, DeltaAccel, circular buffer, reset.
// Uses test-local type copies to avoid NT8 runtime dependencies.
using System;
using System.Collections.Generic;
using NUnit.Framework;

namespace NinjaTrader.Tests.MADConfluenceAI.DeltaPipeline
{
    // ── Test-local type copies ──────────────────────────────────────────

    public sealed class MADCell
    {
        public long BidVol;
        public long AskVol;
        public long NeutralVol;
        public long Delta => AskVol - BidVol;
        public long TotalVol => AskVol + BidVol + NeutralVol;
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

    /// <summary>
    /// Test-local copy of MADDeltaPipeline (identical logic to Data.cs).
    /// </summary>
    public sealed class MADDeltaPipeline
    {
        private const int BufferSize = 500;
        private readonly long[] _cvdBuffer = new long[BufferSize];
        private readonly double[] _closeBuffer = new double[BufferSize];
        private int _head;
        private int _count;

        public int Count => _count;

        public void OnBarFinalized(MADFootprintBar bar)
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
                int n = System.Math.Min(10, _count);
                return (double)(GetCvd(0) - GetCvd(n - 1)) / n;
            }
        }

        public double DeltaAccel
        {
            get
            {
                int half = _count / 2;
                int n = System.Math.Min(10, half);
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

    // ── Helper: build a finalized bar with given CVD and close ───────────

    internal static class BarBuilder
    {
        public static MADFootprintBar MakeBar(long buyVol, long sellVol, double close, long priorCvd)
        {
            var bar = new MADFootprintBar();
            bar.AddTrade(close, buyVol, 1);
            if (sellVol > 0) bar.AddTrade(close, sellVol, 2);
            bar.Finalize(priorCvd);
            return bar;
        }
    }

    // ── Tests ───────────────────────────────────────────────────────────

    [TestFixture]
    public class DeltaPipelineTests
    {
        private MADDeltaPipeline _pipeline;

        [SetUp]
        public void SetUp()
        {
            _pipeline = new MADDeltaPipeline();
        }

        [Test]
        public void CvdSeries_RecordedAcross20Bars()
        {
            long cvd = 0;
            for (int i = 0; i < 20; i++)
            {
                var bar = BarBuilder.MakeBar(100, 50, 21000.0 + i, cvd);
                cvd = bar.Cvd;
                _pipeline.OnBarFinalized(bar);
            }

            Assert.AreEqual(20, _pipeline.Count);
            Assert.AreEqual(cvd, _pipeline.GetCvd(0));
        }

        [Test]
        public void GetCvd0_ReturnsLatest()
        {
            var bar1 = BarBuilder.MakeBar(100, 0, 21000.0, 0);
            _pipeline.OnBarFinalized(bar1);
            Assert.AreEqual(100, _pipeline.GetCvd(0));

            var bar2 = BarBuilder.MakeBar(50, 0, 21001.0, 100);
            _pipeline.OnBarFinalized(bar2);
            Assert.AreEqual(150, _pipeline.GetCvd(0));
        }

        [Test]
        public void GetCvd5_ReturnsFiveBarsAgo()
        {
            long cvd = 0;
            long[] cvdValues = new long[10];
            for (int i = 0; i < 10; i++)
            {
                var bar = BarBuilder.MakeBar(10 * (i + 1), 0, 21000.0 + i, cvd);
                cvd = bar.Cvd;
                cvdValues[i] = cvd;
                _pipeline.OnBarFinalized(bar);
            }

            // GetCvd(5) should return the CVD from 5 bars ago = cvdValues[4]
            Assert.AreEqual(cvdValues[4], _pipeline.GetCvd(5));
        }

        [Test]
        public void DeltaRoC_AfterTenPlusBars()
        {
            long cvd = 0;
            // Feed 15 bars, each with delta +10
            for (int i = 0; i < 15; i++)
            {
                var bar = BarBuilder.MakeBar(10, 0, 21000.0, cvd);
                cvd = bar.Cvd;
                _pipeline.OnBarFinalized(bar);
            }

            // RoC over 10 bars: (cvd[0] - cvd[9]) / 10 = (150 - 60) / 10 = 9.0
            // cvd[0] = 150, cvd[9] = 150 - 9*10 = 60
            double roc = _pipeline.DeltaRoC;
            Assert.AreEqual(9.0, roc, 0.001);
        }

        [Test]
        public void DeltaAccel_IsRoCChange()
        {
            long cvd = 0;
            // First 10 bars: delta +10 each
            for (int i = 0; i < 10; i++)
            {
                var bar = BarBuilder.MakeBar(10, 0, 21000.0, cvd);
                cvd = bar.Cvd;
                _pipeline.OnBarFinalized(bar);
            }
            // Next 10 bars: delta +20 each
            for (int i = 0; i < 10; i++)
            {
                var bar = BarBuilder.MakeBar(20, 0, 21000.0, cvd);
                cvd = bar.Cvd;
                _pipeline.OnBarFinalized(bar);
            }

            // Count = 20, half = 10, n = 10
            // rocNow period [0..9]: latest 10 bars all +20 delta → RoC = (cvd[0]-cvd[9])/10
            // rocPrev period [10..19]: prior 10 bars all +10 delta → RoC = (cvd[10]-cvd[19])/10
            // Accel = rocNow - rocPrev
            double accel = _pipeline.DeltaAccel;
            Assert.Greater(accel, 0, "Acceleration should be positive when RoC increases");
        }

        [Test]
        public void CheckDivergence_BearishReturnsNegative()
        {
            long cvd = 0;
            // Price rising (close increasing), CVD falling (more sells than buys)
            // Bar 1: close 21000, cvd positive
            var bar1 = BarBuilder.MakeBar(100, 0, 21000.0, cvd);
            cvd = bar1.Cvd;
            _pipeline.OnBarFinalized(bar1);

            // Bars 2-5: price rises, but CVD drops
            for (int i = 1; i <= 4; i++)
            {
                var bar = BarBuilder.MakeBar(5, 30, 21000.0 + i * 5, cvd);
                cvd = bar.Cvd;
                _pipeline.OnBarFinalized(bar);
            }

            // Price went from 21000 → 21020 (up), CVD went from 100 → 100-25*4=0 (down)
            double div = _pipeline.CheckDivergence(5);
            Assert.Less(div, 0, "Bearish divergence should return negative");
        }

        [Test]
        public void CheckDivergence_BullishReturnsPositive()
        {
            long cvd = 0;
            // Bar 1: high close, positive CVD
            var bar1 = BarBuilder.MakeBar(10, 0, 21020.0, cvd);
            cvd = bar1.Cvd;
            _pipeline.OnBarFinalized(bar1);

            // Bars 2-5: price falls, but CVD rises (buying the dip)
            for (int i = 1; i <= 4; i++)
            {
                var bar = BarBuilder.MakeBar(30, 5, 21020.0 - i * 5, cvd);
                cvd = bar.Cvd;
                _pipeline.OnBarFinalized(bar);
            }

            // Price went from 21020 → 21000 (down), CVD rose (up)
            double div = _pipeline.CheckDivergence(5);
            Assert.Greater(div, 0, "Bullish divergence should return positive");
        }

        [Test]
        public void CheckDivergence_AgreementReturnsZero()
        {
            long cvd = 0;
            // Price rising AND CVD rising (agreement)
            for (int i = 0; i < 5; i++)
            {
                var bar = BarBuilder.MakeBar(50, 10, 21000.0 + i * 5, cvd);
                cvd = bar.Cvd;
                _pipeline.OnBarFinalized(bar);
            }

            double div = _pipeline.CheckDivergence(5);
            Assert.AreEqual(0, div, "Agreement should return zero");
        }

        [Test]
        public void CircularBuffer_At500Plus()
        {
            long cvd = 0;
            for (int i = 0; i < 510; i++)
            {
                var bar = BarBuilder.MakeBar(10, 0, 21000.0 + (i % 100), cvd);
                cvd = bar.Cvd;
                _pipeline.OnBarFinalized(bar);
            }

            // Count should cap at 500
            Assert.AreEqual(500, _pipeline.Count);
            // Latest CVD should still be accessible
            Assert.AreEqual(cvd, _pipeline.GetCvd(0));
        }

        [Test]
        public void Reset_ClearsState()
        {
            long cvd = 0;
            for (int i = 0; i < 10; i++)
            {
                var bar = BarBuilder.MakeBar(10, 0, 21000.0, cvd);
                cvd = bar.Cvd;
                _pipeline.OnBarFinalized(bar);
            }
            Assert.AreEqual(10, _pipeline.Count);

            _pipeline.Reset();
            Assert.AreEqual(0, _pipeline.Count);
            Assert.AreEqual(0, _pipeline.GetCvd(0));
            Assert.AreEqual(0, _pipeline.DeltaRoC);
        }

        [Test]
        public void GetCvd_OutOfRange_ReturnsZero()
        {
            var bar = BarBuilder.MakeBar(100, 0, 21000.0, 0);
            _pipeline.OnBarFinalized(bar);

            Assert.AreEqual(0, _pipeline.GetCvd(5));  // only 1 bar, asking for 5 ago
            Assert.AreEqual(0, _pipeline.GetCvd(-1)); // negative index
        }

        [Test]
        public void DeltaRoC_InsufficientBars_ReturnsZero()
        {
            Assert.AreEqual(0, _pipeline.DeltaRoC);

            var bar = BarBuilder.MakeBar(100, 0, 21000.0, 0);
            _pipeline.OnBarFinalized(bar);
            Assert.AreEqual(0, _pipeline.DeltaRoC); // only 1 bar, need 2
        }
    }
}
