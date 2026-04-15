// DeltaHardTests: fixture-driven tests for DELT-08 (Slingshot) and DELT-10 (CVD Polyfit Divergence).
//
// Wave 5 additions — both signals require rolling history (DELT-08: DeltaHistory+TotalVolHistory,
// DELT-10: CvdHistory+PriceHistory via LeastSquares.Fit1).
//
// Python reference: deep6/engines/delta.py DeltaEngine.process() lines 263-316

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta;

namespace NinjaTrader.Tests.Detectors
{
    [TestFixture]
    public class DeltaHardTests
    {
        private static string FixturePath(string file) =>
            Path.Combine(TestContext.CurrentContext.TestDirectory,
                "fixtures", "delta", file);

        private static FootprintBar MakeBar(double open, double high, double low, double close,
            long barDelta, long cvd, long totalVol, long maxDelta = 0, long minDelta = 0)
        {
            var bar = new FootprintBar
            {
                BarIndex = 1, Open = open, High = high, Low = low, Close = close,
            };
            bar.Levels[low]  = new Cell { AskVol = totalVol / 3, BidVol = totalVol / 6 };
            bar.Levels[high] = new Cell { AskVol = totalVol / 6, BidVol = totalVol / 3 };
            bar.Finalize();
            bar.BarDelta = barDelta;
            bar.Cvd      = cvd;
            bar.TotalVol = totalVol;
            bar.MaxDelta = maxDelta != 0 ? maxDelta : (barDelta > 0 ? barDelta : 50);
            bar.MinDelta = minDelta != 0 ? minDelta : (barDelta < 0 ? barDelta : -50);
            return bar;
        }

        private static SessionContext MakeSessionWithHistory(
            long[] deltaHistory, long[] totalVolHistory,
            long[] cvdHistory = null, double[] priceHistory = null)
        {
            var session = new SessionContext { TickSize = 0.25, VolEma20 = 500 };
            if (deltaHistory != null)
                foreach (var v in deltaHistory) SessionContext.Push(session.DeltaHistory, v);
            if (totalVolHistory != null)
                foreach (var v in totalVolHistory) SessionContext.Push(session.TotalVolHistory, v);
            if (cvdHistory != null)
                foreach (var v in cvdHistory) SessionContext.Push(session.CvdHistory, v);
            if (priceHistory != null)
                foreach (var v in priceHistory) SessionContext.Push(session.PriceHistory, v);
            return session;
        }

        // -------------------------------------------------------------------
        // DELT-08: Slingshot — 3 prior quiet bars then explosive current bar
        // -------------------------------------------------------------------

        [Test]
        public void Delt08_Slingshot_FiresBullish_FromFixture()
        {
            // Fixture: delt-08-slingshot.json
            // 3 quiet prior bars (|delta| < vol*0.05), then explosive current (delta=900, vol=1000)
            var session = MakeSessionWithHistory(
                deltaHistory:     new long[]   { 10, 15, -8 },
                totalVolHistory:  new long[]   { 1000, 1000, 1000 },
                cvdHistory:       new long[]   { 10, 25, 17 },
                priceHistory:     new double[] { 19990.0, 19995.0, 19998.0 });

            var bar = MakeBar(20000.0, 20010.0, 19998.0, 20008.0, 900, 900, 1000);
            var results = new DeltaDetector().OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "DELT-08" && r.Direction == 1),
                "DELT-08 bullish slingshot should fire when 3 quiet bars precede explosive positive delta");
        }

        [Test]
        public void Delt08_FiresBearish_WhenNegativeExplosiveDelta()
        {
            // 3 quiet prior bars + explosive negative delta
            var session = MakeSessionWithHistory(
                deltaHistory:    new long[] { 5, -10, 8 },
                totalVolHistory: new long[] { 1000, 1000, 1000 });

            var bar = MakeBar(20010.0, 20012.0, 19998.0, 20000.0, -900, -900, 1000);
            var results = new DeltaDetector().OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "DELT-08" && r.Direction == -1),
                "DELT-08 bearish slingshot should fire for explosive negative delta");
        }

        [Test]
        public void Delt08_RequiresFourBarDeltaHistory_NoFireWithFewerBars()
        {
            // Only 2 prior bars in history — requires 3 for slingshot; should NOT fire
            var session = MakeSessionWithHistory(
                deltaHistory:    new long[] { 5, -10 },
                totalVolHistory: new long[] { 1000, 1000 });

            var bar = MakeBar(20000.0, 20010.0, 19998.0, 20008.0, 900, 900, 1000);
            var results = new DeltaDetector().OnBar(bar, session);

            Assert.That(results, Has.None.Matches<SignalResult>(r => r.SignalId == "DELT-08"),
                "DELT-08 should NOT fire with fewer than 3 prior bars in DeltaHistory");
        }

        [Test]
        public void Delt08_DoesNotFire_WhenCurrentBarNotExplosive()
        {
            // 3 quiet prior bars, but current delta is also quiet (not explosive)
            var session = MakeSessionWithHistory(
                deltaHistory:    new long[] { 5, -10, 8 },
                totalVolHistory: new long[] { 1000, 1000, 1000 });

            // delta=100 = 10% of vol=1000, less than explosive threshold of 30%
            var bar = MakeBar(20000.0, 20010.0, 19998.0, 20008.0, 100, 100, 1000);
            var results = new DeltaDetector().OnBar(bar, session);

            Assert.That(results, Has.None.Matches<SignalResult>(r => r.SignalId == "DELT-08"),
                "DELT-08 should NOT fire when current bar delta ratio is below explosive threshold");
        }

        [Test]
        public void Delt08_DetailString_ContainsSlopeOrPolyfit()
        {
            // Verify diagnostic Detail string is informative
            var session = MakeSessionWithHistory(
                deltaHistory:    new long[] { 5, -10, 8 },
                totalVolHistory: new long[] { 1000, 1000, 1000 });

            var bar = MakeBar(20000.0, 20010.0, 19998.0, 20008.0, 900, 900, 1000);
            var results = new DeltaDetector().OnBar(bar, session);

            var delt08 = Array.Find(results, r => r.SignalId == "DELT-08");
            Assert.That(delt08, Is.Not.Null, "DELT-08 should fire");
            Assert.That(delt08.Detail, Does.Contain("slope").Or.Contain("polyfit").Or.Contain("SLINGSHOT"),
                "DELT-08 Detail should mention slope or slingshot for diagnostic traceability");
        }

        // -------------------------------------------------------------------
        // DELT-10: CVD Polyfit Divergence
        // -------------------------------------------------------------------

        [Test]
        public void Delt10_BearishDivergence_PriceUpCvdDown_FromFixture()
        {
            // Fixture: delt-10-cvd-divergence.json
            // priceHistory ascending (slope ~+1), cvdHistory descending (slope ~-100)
            var session = MakeSessionWithHistory(
                deltaHistory:    null,
                totalVolHistory: null,
                cvdHistory:   new long[]   { 500, 400, 300, 200, 100, 0, -100, -200, -300, -400 },
                priceHistory: new double[] { 20000.0, 20001.0, 20002.0, 20003.0, 20004.0,
                                             20005.0, 20006.0, 20007.0, 20008.0, 20009.0 });

            var bar = MakeBar(20008.0, 20010.0, 20005.0, 20009.0, -200, -400, 500);
            var results = new DeltaDetector().OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "DELT-10" && r.Direction == -1),
                "DELT-10 bearish divergence: price ascending but CVD descending → direction=-1");
        }

        [Test]
        public void Delt10_BullishDivergence_PriceDownCvdUp()
        {
            // priceHistory descending (slope ~-1), cvdHistory ascending (slope ~+100)
            var session = MakeSessionWithHistory(
                deltaHistory:    null,
                totalVolHistory: null,
                cvdHistory:   new long[]   { -500, -400, -300, -200, -100, 0, 100, 200, 300, 400 },
                priceHistory: new double[] { 20009.0, 20008.0, 20007.0, 20006.0, 20005.0,
                                             20004.0, 20003.0, 20002.0, 20001.0, 20000.0 });

            var bar = MakeBar(20001.0, 20005.0, 19998.0, 20000.0, 200, 400, 500);
            var results = new DeltaDetector().OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "DELT-10" && r.Direction == 1),
                "DELT-10 bullish divergence: price descending but CVD ascending → direction=+1");
        }

        [Test]
        public void Delt10_DoesNotFire_WhenInsufficientHistory()
        {
            // Only 5 bars in history — default window is 10; should not fire
            var session = MakeSessionWithHistory(
                deltaHistory:    null,
                totalVolHistory: null,
                cvdHistory:   new long[]   { 500, 400, 300, 200, 100 },
                priceHistory: new double[] { 20000.0, 20001.0, 20002.0, 20003.0, 20004.0 });

            var bar = MakeBar(20004.0, 20006.0, 20002.0, 20005.0, -100, -100, 300);
            var results = new DeltaDetector().OnBar(bar, session);

            Assert.That(results, Has.None.Matches<SignalResult>(r => r.SignalId == "DELT-10"),
                "DELT-10 should NOT fire when history has fewer bars than CvdDivergenceWindow");
        }

        [Test]
        public void Delt10_DetailString_MentionsSlopeOrPolyfit()
        {
            var session = MakeSessionWithHistory(
                deltaHistory:    null,
                totalVolHistory: null,
                cvdHistory:   new long[]   { 500, 400, 300, 200, 100, 0, -100, -200, -300, -400 },
                priceHistory: new double[] { 20000.0, 20001.0, 20002.0, 20003.0, 20004.0,
                                             20005.0, 20006.0, 20007.0, 20008.0, 20009.0 });

            var bar = MakeBar(20008.0, 20010.0, 20005.0, 20009.0, -200, -400, 500);
            var results = new DeltaDetector().OnBar(bar, session);

            var delt10 = Array.Find(results, r => r.SignalId == "DELT-10");
            Assert.That(delt10, Is.Not.Null, "DELT-10 should fire");
            Assert.That(delt10.Detail, Does.Contain("slope").Or.Contain("polyfit"),
                "DELT-10 Detail should mention slope/polyfit for diagnostic traceability");
        }
    }
}
