// DataPipelineTests.cs — TDD tests for data pipeline: BBO tracking, trade classification,
// bar accumulation, CVD continuity, bar trimming, session reset.
// Uses test-local type copies to avoid NT8 runtime dependencies.
using System;
using System.Collections.Generic;
using NUnit.Framework;

namespace NinjaTrader.Tests.MADConfluenceAI.DataPipeline
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
    /// Test-local pipeline that mirrors FinalizeCurrentBar / InitDataPipeline logic.
    /// </summary>
    internal class TestDataPipeline
    {
        public MADFootprintBar CurrentBar;
        public List<MADFootprintBar> Bars = new List<MADFootprintBar>();
        public long SessionCvd;
        public int BarCount;
        public double BestBid;
        public double BestAsk;

        public void Init()
        {
            CurrentBar = new MADFootprintBar { BarIndex = 0 };
            Bars.Clear();
            SessionCvd = 0;
            BarCount = 0;
        }

        public int ClassifyAggressor(double price)
        {
            if (BestAsk > 0 && price >= BestAsk) return 1;
            if (BestBid > 0 && price <= BestBid) return 2;
            return 0;
        }

        public void FinalizeCurrentBar(bool resetSession = false)
        {
            if (CurrentBar == null) return;
            if (resetSession) SessionCvd = 0;
            CurrentBar.Finalize(SessionCvd);
            SessionCvd = CurrentBar.Cvd;
            Bars.Add(CurrentBar);
            BarCount++;
            if (Bars.Count > 500) Bars.RemoveAt(0);
            CurrentBar = new MADFootprintBar { BarIndex = BarCount };
        }
    }

    // ── Tests ───────────────────────────────────────────────────────────

    [TestFixture]
    public class DataPipelineTests
    {
        private TestDataPipeline _pipeline;

        [SetUp]
        public void SetUp()
        {
            _pipeline = new TestDataPipeline();
            _pipeline.Init();
        }

        [Test]
        public void BBO_BidUpdate_ChangesBestBid()
        {
            _pipeline.BestBid = 21000.0;
            Assert.AreEqual(21000.0, _pipeline.BestBid);

            _pipeline.BestBid = 21000.25;
            Assert.AreEqual(21000.25, _pipeline.BestBid);
        }

        [Test]
        public void BBO_AskUpdate_ChangesBestAsk()
        {
            _pipeline.BestAsk = 21000.50;
            Assert.AreEqual(21000.50, _pipeline.BestAsk);

            _pipeline.BestAsk = 21000.75;
            Assert.AreEqual(21000.75, _pipeline.BestAsk);
        }

        [Test]
        public void TradeClassification_AtAsk_ReturnsBuy()
        {
            _pipeline.BestBid = 21000.0;
            _pipeline.BestAsk = 21000.25;

            Assert.AreEqual(1, _pipeline.ClassifyAggressor(21000.25));
            Assert.AreEqual(1, _pipeline.ClassifyAggressor(21000.50)); // above ask
        }

        [Test]
        public void TradeClassification_AtBid_ReturnsSell()
        {
            _pipeline.BestBid = 21000.0;
            _pipeline.BestAsk = 21000.25;

            Assert.AreEqual(2, _pipeline.ClassifyAggressor(21000.0));
            Assert.AreEqual(2, _pipeline.ClassifyAggressor(20999.75)); // below bid
        }

        [Test]
        public void TradeClassification_BetweenSpread_ReturnsNeutral()
        {
            _pipeline.BestBid = 21000.0;
            _pipeline.BestAsk = 21000.50;

            Assert.AreEqual(0, _pipeline.ClassifyAggressor(21000.25));
        }

        [Test]
        public void FiftyTickAccumulation_ProducesCorrectBarDelta()
        {
            _pipeline.BestBid = 21000.0;
            _pipeline.BestAsk = 21000.25;

            // 30 buys at ask, 20 sells at bid
            for (int i = 0; i < 30; i++)
                _pipeline.CurrentBar.AddTrade(21000.25, 1, 1);
            for (int i = 0; i < 20; i++)
                _pipeline.CurrentBar.AddTrade(21000.0, 1, 2);

            _pipeline.FinalizeCurrentBar();

            var bar = _pipeline.Bars[0];
            Assert.AreEqual(50, bar.TotalVol);
            Assert.AreEqual(50, bar.TradeCount);
            Assert.AreEqual(10, bar.BarDelta); // 30 - 20
        }

        [Test]
        public void CVD_ContinuityAcrossThreeBars()
        {
            // Bar 1: delta +20
            _pipeline.CurrentBar.AddTrade(21000.0, 30, 1);
            _pipeline.CurrentBar.AddTrade(21000.0, 10, 2);
            _pipeline.FinalizeCurrentBar();
            Assert.AreEqual(20, _pipeline.Bars[0].Cvd);

            // Bar 2: delta -10 → CVD = 20 + (-10) = 10
            _pipeline.CurrentBar.AddTrade(21000.0, 5, 1);
            _pipeline.CurrentBar.AddTrade(21000.0, 15, 2);
            _pipeline.FinalizeCurrentBar();
            Assert.AreEqual(10, _pipeline.Bars[1].Cvd);

            // Bar 3: delta +30 → CVD = 10 + 30 = 40
            _pipeline.CurrentBar.AddTrade(21000.0, 40, 1);
            _pipeline.CurrentBar.AddTrade(21000.0, 10, 2);
            _pipeline.FinalizeCurrentBar();
            Assert.AreEqual(40, _pipeline.Bars[2].Cvd);

            Assert.AreEqual(40, _pipeline.SessionCvd);
        }

        [Test]
        public void BarList_TrimsAt500()
        {
            for (int i = 0; i < 510; i++)
            {
                _pipeline.CurrentBar.AddTrade(21000.0, 1, 1);
                _pipeline.FinalizeCurrentBar();
            }

            Assert.AreEqual(500, _pipeline.Bars.Count);
            // First bar should be bar index 10 (0-9 trimmed)
            Assert.AreEqual(10, _pipeline.Bars[0].BarIndex);
        }

        [Test]
        public void SessionCvd_ResetsOnNewSession()
        {
            // Build up CVD
            _pipeline.CurrentBar.AddTrade(21000.0, 100, 1);
            _pipeline.FinalizeCurrentBar();
            Assert.AreEqual(100, _pipeline.SessionCvd);

            // Reset session
            _pipeline.CurrentBar.AddTrade(21000.0, 50, 1);
            _pipeline.FinalizeCurrentBar(resetSession: true);
            // CVD should be computed from 0 + barDelta(50) = 50
            Assert.AreEqual(50, _pipeline.SessionCvd);
            Assert.AreEqual(50, _pipeline.Bars[1].Cvd);
        }

        [Test]
        public void NewBar_CreatedAfterFinalize()
        {
            _pipeline.CurrentBar.AddTrade(21000.0, 5, 1);
            _pipeline.FinalizeCurrentBar();

            Assert.IsNotNull(_pipeline.CurrentBar);
            Assert.AreEqual(1, _pipeline.CurrentBar.BarIndex);
            Assert.AreEqual(0, _pipeline.CurrentBar.TotalVol);
        }

        [Test]
        public void BarCount_IncrementsCorrectly()
        {
            Assert.AreEqual(0, _pipeline.BarCount);

            _pipeline.CurrentBar.AddTrade(21000.0, 1, 1);
            _pipeline.FinalizeCurrentBar();
            Assert.AreEqual(1, _pipeline.BarCount);

            _pipeline.CurrentBar.AddTrade(21000.0, 1, 1);
            _pipeline.FinalizeCurrentBar();
            Assert.AreEqual(2, _pipeline.BarCount);
        }
    }
}
