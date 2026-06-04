// DataTypesTests.cs — TDD tests for MADCell, MADFootprintBar, MADSignalResult, MADSignalDirection
// Uses test-local copies of the types to avoid NT8 runtime dependencies.
using System;
using System.Collections.Generic;
using NUnit.Framework;

namespace NinjaTrader.Tests.MADConfluenceAI
{
    // ── Test-local type copies (identical logic to MADConfluenceAI.Data.cs) ──

    public enum MADSignalDirection { Long, Short, Neutral }

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
        public double VahPrice;
        public double ValPrice;
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

        public double DeltaQualityScalar()
        {
            long extreme = System.Math.Abs(MaxDelta) > System.Math.Abs(MinDelta) ? System.Math.Abs(MaxDelta) : System.Math.Abs(MinDelta);
            if (extreme == 0) return 0.0;
            double q = (double)System.Math.Abs(BarDelta) / extreme;
            return System.Math.Min(1.15, System.Math.Max(0.0, q));
        }
    }

    // ── Tests ───────────────────────────────────────────────────────────

    [TestFixture]
    public class DataTypesTests
    {
        // ── MADCell tests ───────────────────────────────────────────────

        [Test]
        public void MADCell_Delta_ReturnsAskMinusBid()
        {
            var cell = new MADCell { AskVol = 150, BidVol = 80 };
            Assert.AreEqual(70, cell.Delta);
        }

        [Test]
        public void MADCell_TotalVol_SumsAllThreeTypes()
        {
            var cell = new MADCell { AskVol = 100, BidVol = 50, NeutralVol = 25 };
            Assert.AreEqual(175, cell.TotalVol);
        }

        [Test]
        public void MADCell_ImbalanceRatio_MaxValue_WhenOneSideZero()
        {
            var askOnly = new MADCell { AskVol = 100, BidVol = 0 };
            Assert.AreEqual(double.MaxValue, askOnly.ImbalanceRatio);

            var bidOnly = new MADCell { AskVol = 0, BidVol = 100 };
            Assert.AreEqual(double.MaxValue, bidOnly.ImbalanceRatio);
        }

        [Test]
        public void MADCell_ImbalanceRatio_One_WhenBothZero()
        {
            var cell = new MADCell { AskVol = 0, BidVol = 0 };
            Assert.AreEqual(1.0, cell.ImbalanceRatio);
        }

        [Test]
        public void MADCell_ImbalanceRatio_CorrectWhenAskDominates()
        {
            var cell = new MADCell { AskVol = 200, BidVol = 100 };
            Assert.AreEqual(2.0, cell.ImbalanceRatio, 0.001);
        }

        [Test]
        public void MADCell_ImbalanceRatio_CorrectWhenBidDominates()
        {
            var cell = new MADCell { AskVol = 50, BidVol = 150 };
            Assert.AreEqual(3.0, cell.ImbalanceRatio, 0.001);
        }

        // ── MADFootprintBar.AddTrade tests ──────────────────────────────

        [Test]
        public void AddTrade_BuyAggressor_AccumulatesAskVol()
        {
            var bar = new MADFootprintBar();
            bar.AddTrade(21000.0, 5, 1);  // buy at ask
            bar.AddTrade(21000.0, 3, 1);  // buy at ask again

            Assert.AreEqual(8, bar.Levels[21000.0].AskVol);
            Assert.AreEqual(0, bar.Levels[21000.0].BidVol);
            Assert.AreEqual(8, bar.RunningDelta);
            Assert.AreEqual(8, bar.TotalVol);
            Assert.AreEqual(2, bar.TradeCount);
        }

        [Test]
        public void AddTrade_SellAggressor_AccumulatesBidVol()
        {
            var bar = new MADFootprintBar();
            bar.AddTrade(21000.0, 10, 2);  // sell at bid

            Assert.AreEqual(10, bar.Levels[21000.0].BidVol);
            Assert.AreEqual(0, bar.Levels[21000.0].AskVol);
            Assert.AreEqual(-10, bar.RunningDelta);
        }

        [Test]
        public void AddTrade_NeutralAggressor_AccumulatesNeutralVol()
        {
            var bar = new MADFootprintBar();
            bar.AddTrade(21000.0, 7, 0);  // neutral

            Assert.AreEqual(7, bar.Levels[21000.0].NeutralVol);
            Assert.AreEqual(0, bar.RunningDelta);
        }

        [Test]
        public void AddTrade_TracksOHLC_Correctly()
        {
            var bar = new MADFootprintBar();
            bar.AddTrade(21000.0, 1, 1);
            bar.AddTrade(21005.0, 1, 1);
            bar.AddTrade(20995.0, 1, 2);
            bar.AddTrade(21002.0, 1, 1);

            Assert.AreEqual(21000.0, bar.Open);
            Assert.AreEqual(21005.0, bar.High);
            Assert.AreEqual(20995.0, bar.Low);
            Assert.AreEqual(21002.0, bar.Close);
        }

        [Test]
        public void AddTrade_TracksMaxMinDelta()
        {
            var bar = new MADFootprintBar();
            bar.AddTrade(21000.0, 10, 1);  // delta = +10
            bar.AddTrade(21000.0, 15, 2);  // delta = -5
            bar.AddTrade(21000.0, 3, 1);   // delta = -2

            Assert.AreEqual(10, bar.MaxDelta);
            Assert.AreEqual(-5, bar.MinDelta);
        }

        // ── MADFootprintBar.Finalize tests ──────────────────────────────

        [Test]
        public void Finalize_ComputesCorrectPOC()
        {
            var bar = new MADFootprintBar();
            bar.AddTrade(21000.0, 50, 1);
            bar.AddTrade(21000.0, 30, 2);   // 21000 total = 80
            bar.AddTrade(21005.0, 100, 1);   // 21005 total = 100 (POC)
            bar.AddTrade(20995.0, 20, 2);    // 20995 total = 20
            bar.Finalize();

            Assert.AreEqual(21005.0, bar.PocPrice);
        }

        [Test]
        public void Finalize_ComputesCVD_WithPriorCvd()
        {
            var bar = new MADFootprintBar();
            bar.AddTrade(21000.0, 30, 1);   // ask +30
            bar.AddTrade(21000.0, 10, 2);   // bid +10
            bar.Finalize(priorCvd: 500);

            // BarDelta = 30 - 10 = 20
            Assert.AreEqual(20, bar.BarDelta);
            // CVD = 500 + 20 = 520
            Assert.AreEqual(520, bar.Cvd);
        }

        [Test]
        public void Finalize_ComputesBarRange()
        {
            var bar = new MADFootprintBar();
            bar.AddTrade(21000.0, 1, 1);
            bar.AddTrade(21010.0, 1, 1);
            bar.Finalize();

            Assert.AreEqual(10.0, bar.BarRange, 0.001);
        }

        [Test]
        public void Finalize_RecomputesTotalVol_WhenDirectlyPopulated()
        {
            // Simulate direct level population (no AddTrade)
            var bar = new MADFootprintBar();
            bar.Levels[21000.0] = new MADCell { AskVol = 40, BidVol = 20 };
            bar.Levels[21005.0] = new MADCell { AskVol = 30, BidVol = 10 };
            // TotalVol is 0 since we didn't use AddTrade
            bar.Finalize();

            Assert.AreEqual(100, bar.TotalVol);  // 40+20+30+10
        }

        // ── DeltaQualityScalar tests ────────────────────────────────────

        [Test]
        public void DeltaQualityScalar_ReturnsOne_WhenDeltaEqualsMax()
        {
            var bar = new MADFootprintBar();
            // All buys, no reversals: BarDelta == MaxDelta
            bar.AddTrade(21000.0, 50, 1);
            bar.Finalize();

            double q = bar.DeltaQualityScalar();
            Assert.AreEqual(1.0, q, 0.01);
        }

        [Test]
        public void DeltaQualityScalar_ReturnsZero_WhenEmptyBar()
        {
            var bar = new MADFootprintBar();
            double q = bar.DeltaQualityScalar();
            Assert.AreEqual(0.0, q);
        }

        [Test]
        public void DeltaQualityScalar_LessThanOne_WhenPartialReversal()
        {
            var bar = new MADFootprintBar();
            bar.AddTrade(21000.0, 100, 1);  // delta +100 (MaxDelta=100)
            bar.AddTrade(21000.0, 50, 2);   // delta +50
            bar.Finalize();

            // BarDelta = 100-50 = 50, extreme = 100, q = 50/100 = 0.5
            double q = bar.DeltaQualityScalar();
            Assert.AreEqual(0.5, q, 0.01);
        }

        // ── MADSignalResult tests ───────────────────────────────────────

        [Test]
        public void MADSignalResult_DefaultValues()
        {
            var sig = new MADSignalResult
            {
                SignalId = "E01-Absorption",
                Direction = MADSignalDirection.Long,
                Strength = 0.85,
                Detail = "heavy bid absorption at 21000",
                Price = 21000.0
            };

            Assert.AreEqual("E01-Absorption", sig.SignalId);
            Assert.AreEqual(MADSignalDirection.Long, sig.Direction);
            Assert.AreEqual(0.85, sig.Strength, 0.001);
            Assert.AreEqual(21000.0, sig.Price);
        }

        [Test]
        public void MADSignalDirection_HasThreeValues()
        {
            var values = Enum.GetValues(typeof(MADSignalDirection));
            Assert.AreEqual(3, values.Length);
        }
    }
}
