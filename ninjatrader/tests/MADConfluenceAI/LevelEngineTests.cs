using System;
using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using NinjaTrader.NinjaScript.Indicators.DEEP6;

namespace NinjaTrader.Tests.MADConfluenceAI
{
    [TestFixture]
    public class LevelEngineTests
    {
        private MADLevelEngine _engine;

        [SetUp]
        public void SetUp()
        {
            _engine = new MADLevelEngine();
        }

        // ---- Test 1: VWAP weighted average from 3 ticks ----

        [Test]
        public void UpdateVwap_ThreeTicks_VwapEqualsWeightedAverage()
        {
            // Tick 1: price=20000, vol=100  → PV=2,000,000
            // Tick 2: price=20010, vol=200  → PV=4,002,000
            // Tick 3: price=20005, vol=300  → PV=6,001,500
            // Total PV = 12,003,500  Total V = 600
            // VWAP = 12,003,500 / 600 = 20005.8333...
            _engine.UpdateVwap(20000.0, 100);
            _engine.UpdateVwap(20010.0, 200);
            _engine.UpdateVwap(20005.0, 300);

            double expectedVwap = (20000.0 * 100 + 20010.0 * 200 + 20005.0 * 300) / 600.0;
            Assert.AreEqual(expectedVwap, _engine.VwapValue, 0.0001,
                "VWAP should be the volume-weighted average of all ticks");
        }

        // ---- Test 2: VWAP sigma bands are above/below VWAP ----

        [Test]
        public void UpdateVwap_SigmaBands_AreAboveAndBelowVwap()
        {
            // Use prices with spread to produce non-zero sigma
            _engine.UpdateVwap(20000.0, 100);
            _engine.UpdateVwap(20020.0, 100);
            _engine.UpdateVwap(20010.0, 100);

            Assert.Greater(_engine.Vwap1SigmaUp, _engine.VwapValue,
                "1-sigma upper should be above VWAP");
            Assert.Less(_engine.Vwap1SigmaDown, _engine.VwapValue,
                "1-sigma lower should be below VWAP");
            Assert.Greater(_engine.Vwap2SigmaUp, _engine.Vwap1SigmaUp,
                "2-sigma upper should be above 1-sigma upper");
            Assert.Less(_engine.Vwap2SigmaDown, _engine.Vwap1SigmaDown,
                "2-sigma lower should be below 1-sigma lower");
        }

        // ---- Test 3: GetNearbyLevels finds PDL when price is 1 tick above it ----

        [Test]
        public void GetNearbyLevels_FindsPdl_WhenPriceIs1TickAbove()
        {
            _engine.SetPriorDayLevels(20100.0, 20000.0);
            _engine.RecomputeQuality();

            // Price is 1 tick (0.25) above PDL=20000
            var nearby = _engine.GetNearbyLevels(20000.25, toleranceTicks: 1);

            Assert.IsTrue(nearby.Any(l => l.Type == MADLevelType.PrevDayLow),
                "Should find PrevDayLow within 1 tick tolerance");
        }

        // ---- Test 4: GetNearbyLevels returns empty when no levels within tolerance ----

        [Test]
        public void GetNearbyLevels_ReturnsEmpty_WhenNoLevelsWithinTolerance()
        {
            _engine.SetPriorDayLevels(20100.0, 20000.0);

            // Price is 100 points away — far beyond any reasonable tolerance
            var nearby = _engine.GetNearbyLevels(19800.0, toleranceTicks: 2);

            Assert.AreEqual(0, nearby.Count,
                "Should return empty list when no levels are within tolerance");
        }

        // ---- Test 5: SetPriorDayLevels stores correct H/L/Mid ----

        [Test]
        public void SetPriorDayLevels_StoresCorrectHighLowMid()
        {
            _engine.SetPriorDayLevels(20150.0, 20050.0);

            var levels = _engine.Levels;
            var pdh = levels.FirstOrDefault(l => l.Type == MADLevelType.PrevDayHigh);
            var pdl = levels.FirstOrDefault(l => l.Type == MADLevelType.PrevDayLow);
            var pdm = levels.FirstOrDefault(l => l.Type == MADLevelType.PrevDayMid);

            Assert.IsNotNull(pdh, "PrevDayHigh should exist");
            Assert.IsNotNull(pdl, "PrevDayLow should exist");
            Assert.IsNotNull(pdm, "PrevDayMid should exist");
            Assert.AreEqual(20150.0, pdh.Price, 0.001);
            Assert.AreEqual(20050.0, pdl.Price, 0.001);
            Assert.AreEqual(20100.0, pdm.Price, 0.001, "Mid should be (H+L)/2");
        }

        // ---- Test 6: GeneratePsychologicalLevels creates levels at 25-point intervals ----

        [Test]
        public void GeneratePsychologicalLevels_CreatesAt25PointIntervals()
        {
            _engine.GeneratePsychologicalLevels(20000.0, 20100.0);

            var psychLevels = _engine.Levels
                .Where(l => l.Type == MADLevelType.Psychological)
                .OrderBy(l => l.Price)
                .ToList();

            // 20000, 20025, 20050, 20075, 20100 = 5 levels
            Assert.AreEqual(5, psychLevels.Count,
                "Should create levels at 20000, 20025, 20050, 20075, 20100");
            Assert.AreEqual(20000.0, psychLevels[0].Price, 0.001);
            Assert.AreEqual(20025.0, psychLevels[1].Price, 0.001);
            Assert.AreEqual(20050.0, psychLevels[2].Price, 0.001);
            Assert.AreEqual(20075.0, psychLevels[3].Price, 0.001);
            Assert.AreEqual(20100.0, psychLevels[4].Price, 0.001);
        }

        // ---- Test 7: RecordTouch increments TouchCount on nearby level ----

        [Test]
        public void RecordTouch_IncrementsTouchCount_OnNearbyLevel()
        {
            _engine.SetPriorDayLevels(20100.0, 20000.0);

            // Touch PDL exactly
            _engine.RecordTouch(20000.0);
            _engine.RecordTouch(20000.0);
            _engine.RecordTouch(20000.0);

            var pdl = _engine.Levels.First(l => l.Type == MADLevelType.PrevDayLow);
            Assert.AreEqual(3, pdl.TouchCount,
                "TouchCount should be 3 after three touches");
        }

        // ---- Test 8: Quality score increases when levels are confluent ----

        [Test]
        public void RecomputeQuality_ConfluenceBoosts_WhenLevelsAtSamePrice()
        {
            // Place PDL and SessionLow at exact same price → confluence
            _engine.SetPriorDayLevels(20100.0, 20000.0);
            _engine.SetSessionExtremes(20100.0, 20000.0);
            _engine.RecomputeQuality();

            var pdl = _engine.Levels.First(l => l.Type == MADLevelType.PrevDayLow);
            var sessionLow = _engine.Levels.First(l => l.Type == MADLevelType.SessionLow);

            // PDL base = 0.80 + confluence bonus (at least 0.08)
            Assert.Greater(pdl.QualityScore, 0.80,
                "PDL quality should exceed base 0.80 due to confluence with SessionLow");

            // Now create an isolated engine to compare
            var isolated = new MADLevelEngine();
            isolated.SetPriorDayLevels(20100.0, 20000.0);
            // No session extremes at same price
            isolated.SetSessionExtremes(20200.0, 19900.0);
            isolated.RecomputeQuality();

            var isolatedPdl = isolated.Levels.First(l => l.Type == MADLevelType.PrevDayLow);
            Assert.Greater(pdl.QualityScore, isolatedPdl.QualityScore,
                "Confluent PDL should have higher quality than isolated PDL");
        }

        // ---- Test 9: ResetSession clears VWAP-related levels ----

        [Test]
        public void ResetSession_ClearsVwapAndSessionLevels()
        {
            _engine.UpdateVwap(20000.0, 100);
            _engine.UpdateVwap(20010.0, 200);
            _engine.SetSessionExtremes(20050.0, 19950.0);
            _engine.SetPriorDayLevels(20100.0, 19900.0); // these should survive

            int preResetCount = _engine.Levels.Count;
            Assert.Greater(preResetCount, 0, "Should have levels before reset");

            _engine.ResetSession();

            Assert.AreEqual(0.0, _engine.VwapValue, "VwapValue should be 0 after reset");
            Assert.AreEqual(0.0, _engine.Vwap1SigmaUp, "Vwap1SigmaUp should be 0 after reset");

            // VWAP and session levels should be gone
            Assert.IsFalse(_engine.Levels.Any(l => l.Type == MADLevelType.VwapLine),
                "VwapLine level should be removed");
            Assert.IsFalse(_engine.Levels.Any(l => l.Type == MADLevelType.SessionHigh),
                "SessionHigh level should be removed");

            // PriorDay levels should survive
            Assert.IsTrue(_engine.Levels.Any(l => l.Type == MADLevelType.PrevDayHigh),
                "PrevDayHigh should survive ResetSession");
            Assert.IsTrue(_engine.Levels.Any(l => l.Type == MADLevelType.PrevDayLow),
                "PrevDayLow should survive ResetSession");
        }

        // ---- Test 10: MaxLevels cap stops at 200 ----

        [Test]
        public void MaxLevelsCap_StopsAt200()
        {
            // Generate psychological levels over a huge range to exceed 200
            // 25-point spacing over 6000 points = 241 levels
            _engine.GeneratePsychologicalLevels(18000.0, 24000.0);

            Assert.LessOrEqual(_engine.Levels.Count, 200,
                "Level count should never exceed MaxLevels (200)");
        }

        // ---- Test 11: SetVolumeLevels stores POC/VAH/VAL ----

        [Test]
        public void SetVolumeLevels_StoresPocVahVal()
        {
            _engine.SetVolumeLevels(20050.0, 20075.0, 20025.0);

            var poc = _engine.Levels.FirstOrDefault(l => l.Type == MADLevelType.SessionPoc);
            var vah = _engine.Levels.FirstOrDefault(l => l.Type == MADLevelType.SessionVah);
            var val = _engine.Levels.FirstOrDefault(l => l.Type == MADLevelType.SessionVal);

            Assert.IsNotNull(poc);
            Assert.IsNotNull(vah);
            Assert.IsNotNull(val);
            Assert.AreEqual(20050.0, poc.Price, 0.001);
            Assert.AreEqual(20075.0, vah.Price, 0.001);
            Assert.AreEqual(20025.0, val.Price, 0.001);
        }

        // ---- Test 12: SetVolumeLevels updates existing levels (no duplicates) ----

        [Test]
        public void SetVolumeLevels_UpdatesExistingLevels_NoDuplicates()
        {
            _engine.SetVolumeLevels(20050.0, 20075.0, 20025.0);
            _engine.SetVolumeLevels(20060.0, 20080.0, 20030.0);

            var pocs = _engine.Levels.Where(l => l.Type == MADLevelType.SessionPoc).ToList();
            Assert.AreEqual(1, pocs.Count, "Should have exactly one SessionPoc, not duplicates");
            Assert.AreEqual(20060.0, pocs[0].Price, 0.001, "POC should reflect updated price");
        }

        // ---- Test 13: RecordTouch does not increment distant levels ----

        [Test]
        public void RecordTouch_DoesNotIncrement_DistantLevels()
        {
            _engine.SetPriorDayLevels(20100.0, 20000.0);

            // Touch at 20050 — far from both PDH (20100) and PDL (20000)
            _engine.RecordTouch(20050.0);

            var pdh = _engine.Levels.First(l => l.Type == MADLevelType.PrevDayHigh);
            var pdl = _engine.Levels.First(l => l.Type == MADLevelType.PrevDayLow);
            Assert.AreEqual(0, pdh.TouchCount, "PDH should not be touched at 20050");
            Assert.AreEqual(0, pdl.TouchCount, "PDL should not be touched at 20050");
        }

        // ---- Test 14: VWAP with uniform price gives zero sigma ----

        [Test]
        public void UpdateVwap_UniformPrice_GivesZeroSigma()
        {
            _engine.UpdateVwap(20000.0, 100);
            _engine.UpdateVwap(20000.0, 200);
            _engine.UpdateVwap(20000.0, 300);

            Assert.AreEqual(20000.0, _engine.VwapValue, 0.001,
                "VWAP should equal the uniform price");
            Assert.AreEqual(_engine.VwapValue, _engine.Vwap1SigmaUp, 0.001,
                "Sigma bands should collapse to VWAP when price is uniform");
            Assert.AreEqual(_engine.VwapValue, _engine.Vwap1SigmaDown, 0.001,
                "Sigma bands should collapse to VWAP when price is uniform");
        }
    }
}
