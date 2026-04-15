// DeltaDetectorTests: fixture-driven tests for DeltaDetector (DELT-01..11, minus DELT-08/10).
//
// Covers: DELT-01 rise/drop, DELT-02 tail, DELT-03 reversal, DELT-04 divergence,
//         DELT-05 CVD flip, DELT-06 delta trap, DELT-07 sweep, DELT-09 session min/max,
//         DELT-11 velocity. DELT-08/10 deferred (Wave 5).

using System;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta;

namespace NinjaTrader.Tests.Detectors
{
    [TestFixture]
    public class DeltaDetectorTests
    {
        private static string FixturePath(string file) =>
            System.IO.Path.Combine(TestContext.CurrentContext.TestDirectory,
                "fixtures", "delta", file);

        // Helper: build a minimal bar with levels
        private static FootprintBar MakeBar(int idx, double open, double high, double low, double close,
            long barDelta, long cvd, long totalVol, long maxDelta = 0, long minDelta = 0)
        {
            var bar = new FootprintBar
            {
                BarIndex = idx,
                Open  = open,
                High  = high,
                Low   = low,
                Close = close,
            };
            // Add 2 stub levels so TotalVol check passes
            bar.Levels[low]  = new Cell { AskVol = (long)(totalVol * 0.5), BidVol = (long)(totalVol * 0.1) };
            bar.Levels[high] = new Cell { AskVol = (long)(totalVol * 0.2), BidVol = (long)(totalVol * 0.2) };
            bar.Finalize();
            // Override computed values AFTER Finalize — Finalize recomputes BarDelta/TotalVol/Cvd from Levels.
            // For unit tests we inject specific values independent of stub level layout.
            bar.BarDelta = barDelta;
            bar.Cvd      = cvd;
            bar.TotalVol = totalVol;
            bar.MaxDelta = maxDelta != 0 ? maxDelta : (barDelta > 0 ? barDelta + 20 : 20);
            bar.MinDelta = minDelta != 0 ? minDelta : (barDelta < 0 ? barDelta - 20 : -20);
            return bar;
        }

        // -------------------------------------------------------------------
        // DELT-01: Rise fires when barDelta > 0; Drop when barDelta < 0
        // -------------------------------------------------------------------

        [Test]
        public void Delt01_DeltaRise_Fires()
        {
            var bar     = MakeBar(1, 20000.0, 20002.0, 19999.75, 20001.0, 300, 300, 800);
            var session = new SessionContext { TickSize = 0.25 };
            var results = new DeltaDetector().OnBar(bar, session);

            SignalResult delt01 = null;
            foreach (var r in results) if (r.SignalId == "DELT-01" && r.Direction == +1) { delt01 = r; break; }
            Assert.That(delt01, Is.Not.Null, "DELT-01 should fire direction=+1 when barDelta > 0");
            StringAssert.Contains("RISE", delt01.Detail);
        }

        [Test]
        public void Delt01_DeltaDrop_Fires()
        {
            var bar     = MakeBar(2, 20002.0, 20002.25, 19999.75, 20000.0, -300, -300, 800);
            var session = new SessionContext { TickSize = 0.25 };
            var results = new DeltaDetector().OnBar(bar, session);

            SignalResult delt01 = null;
            foreach (var r in results) if (r.SignalId == "DELT-01" && r.Direction == -1) { delt01 = r; break; }
            Assert.That(delt01, Is.Not.Null, "DELT-01 should fire direction=-1 when barDelta < 0");
        }

        // -------------------------------------------------------------------
        // DELT-02: Tail fires when delta closes near intrabar extreme (>= 95%)
        // -------------------------------------------------------------------

        [Test]
        public void Delt02_DeltaTail_BullishExtremeClose_Fires()
        {
            // delta=800, maxDelta=820. tailRatio=800/820=0.976>=0.95 → fires
            var bar = MakeBar(3, 20000.0, 20003.0, 19999.75, 20002.75, 800, 800, 1000, maxDelta: 820);
            var session = new SessionContext { TickSize = 0.25 };
            var results = new DeltaDetector().OnBar(bar, session);

            bool hasDelt02 = false;
            foreach (var r in results) if (r.SignalId == "DELT-02" && r.Direction == +1) { hasDelt02 = true; break; }
            Assert.That(hasDelt02, Is.True, "DELT-02 should fire direction=+1 when delta≈maxDelta");
        }

        // -------------------------------------------------------------------
        // DELT-03: Reversal fires when bar direction contradicts delta sign
        // -------------------------------------------------------------------

        [Test]
        public void Delt03_BullishBarNegativeDelta_Fires()
        {
            // bar closes up (green), but delta = -200 → hidden bearish
            var bar = MakeBar(4, 20000.0, 20003.0, 19999.75, 20002.0, -200, -200, 600);
            var session = new SessionContext { TickSize = 0.25 };
            var results = new DeltaDetector().OnBar(bar, session);

            SignalResult delt03 = null;
            foreach (var r in results) if (r.SignalId == "DELT-03" && r.Direction == -1) { delt03 = r; break; }
            Assert.That(delt03, Is.Not.Null, "DELT-03 should fire direction=-1 when green bar but negative delta");
        }

        // -------------------------------------------------------------------
        // DELT-04: Divergence fires when price slope and CVD slope diverge
        // -------------------------------------------------------------------

        [Test]
        public void Delt04_Divergence_PriceUpCvdDown_Fires()
        {
            // Fixture: priorClose2=20000.0, priorCvd2=1000; current close=20002.0, cvd=700
            // priceSlope=(20002-20000)/2=+1.0  (up)
            // deltaSlope=(700-1000)/2=-150.0   (down)
            // Signs differ → DELT-04 direction=-1 (fade the up price move)
            // DELT-04 needs priceArr.Length >= 2 and cvdArr.Length >= 2 (divLb-1=2).
            // priorClose2 = priceArr[len-2], priorCvd2 = cvdArr[len-2].
            // Seed 2 prior entries: bar[i-2] and bar[i-1].
            // priceSlope = (close - priceArr[len-2]) / (3-1) = (20002 - 20000) / 2 = +1.0
            // deltaSlope = (cvd - cvdArr[len-2]) / (3-1) = (700 - 1000) / 2 = -150
            // Signs differ AND both magnitudes > 0.1 → DELT-04 fires direction=-1
            var bar = MakeBar(10, 20001.0, 20003.0, 20000.75, 20002.0, -50, 700, 600);
            var session = new SessionContext { TickSize = 0.25 };

            SessionContext.Push(session.PriceHistory, 20000.0);  // bar[i-2]: close (oldest)
            SessionContext.Push(session.PriceHistory, 20001.0);  // bar[i-1]: close
            SessionContext.Push(session.CvdHistory,   1000L);    // bar[i-2]: cvd (oldest)
            SessionContext.Push(session.CvdHistory,   900L);     // bar[i-1]: cvd

            var results = new DeltaDetector().OnBar(bar, session);

            SignalResult delt04 = null;
            foreach (var r in results) if (r.SignalId == "DELT-04") { delt04 = r; break; }
            Assert.That(delt04, Is.Not.Null, "DELT-04 should fire when price up but CVD down");
            Assert.That(delt04.Direction, Is.EqualTo(-1), "direction=-1 (fade the divergent up move)");
        }

        [Test]
        public void Delt04_Fixture_JsonIsValid()
        {
            string path = FixturePath("delt-04-divergence.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // DELT-05: CVD Flip fires when CVD crosses zero
        // -------------------------------------------------------------------

        [Test]
        public void Delt05_CvdFlipBearish_PrevPositiveCurrNegative_Fires()
        {
            var bar     = MakeBar(5, 20002.0, 20002.25, 19999.75, 20000.0, -500, -100, 800);
            var session = new SessionContext { TickSize = 0.25 };
            // Seed prior CVD as positive
            SessionContext.Push(session.CvdHistory, 200L);

            var results = new DeltaDetector().OnBar(bar, session);

            bool hasDelt05 = false;
            foreach (var r in results) if (r.SignalId == "DELT-05" && r.Direction == -1) { hasDelt05 = true; break; }
            Assert.That(hasDelt05, Is.True, "DELT-05 should fire direction=-1 when CVD crosses below zero");
        }

        // -------------------------------------------------------------------
        // DELT-06: Delta Trap fires when prior delta strongly positive and price drops
        // -------------------------------------------------------------------

        [Test]
        public void Delt06_DeltaTrap_BullishPriorDelta_PriceDrops_Fires()
        {
            // priorDelta=800, currentTotalVol=900, trapTh=900*0.35=315. 800>315 AND close<open → fires
            var bar     = MakeBar(6, 20003.0, 20003.50, 19999.75, 20000.0, -300, 700, 900);
            var session = new SessionContext { TickSize = 0.25 };
            // Seed prior delta
            SessionContext.Push(session.DeltaHistory, 800L);

            var results = new DeltaDetector().OnBar(bar, session);

            SignalResult delt06 = null;
            foreach (var r in results) if (r.SignalId == "DELT-06" && r.Direction == -1) { delt06 = r; break; }
            Assert.That(delt06, Is.Not.Null, "DELT-06 should fire when bullish prior delta but price drops");
        }

        [Test]
        public void Delt06_Fixture_JsonIsValid()
        {
            string path = FixturePath("delt-06-trap.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // DELT-07: Sweep fires when bar has >= SweepMinLevels with vol accelerating
        // -------------------------------------------------------------------

        [Test]
        public void Delt07_Sweep_UpperHalfVol_Accelerates_Fires()
        {
            // 6 levels. Lower 3 vol=300, upper 3 vol=1800. 1800/300=6 > 1.5 → fires
            var bar = new FootprintBar
            {
                BarIndex = 7,
                Open  = 20000.00,
                High  = 20003.00,
                Low   = 20000.00,
                Close = 20002.75,
                BarDelta   = 500,
                Cvd        = 1200,
                TotalVol   = 2100,
                MaxDelta   = 520,
                MinDelta   = -20,
            };
            bar.Levels[20000.00] = new Cell { AskVol = 50,  BidVol = 50  };
            bar.Levels[20000.50] = new Cell { AskVol = 50,  BidVol = 50  };
            bar.Levels[20001.00] = new Cell { AskVol = 50,  BidVol = 50  };
            bar.Levels[20001.50] = new Cell { AskVol = 300, BidVol = 300 };
            bar.Levels[20002.25] = new Cell { AskVol = 300, BidVol = 300 };
            bar.Levels[20002.75] = new Cell { AskVol = 300, BidVol = 300 };
            bar.Finalize();

            var session = new SessionContext { TickSize = 0.25 };
            var results = new DeltaDetector().OnBar(bar, session);

            SignalResult delt07 = null;
            foreach (var r in results) if (r.SignalId == "DELT-07") { delt07 = r; break; }
            Assert.That(delt07, Is.Not.Null, "DELT-07 should fire when second-half vol >> first-half vol");
        }

        [Test]
        public void Delt07_Fixture_JsonIsValid()
        {
            string path = FixturePath("delt-07-sweep.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // DELT-09: Session min/max fires when delta >= sessionMax or <= sessionMin
        // -------------------------------------------------------------------

        [Test]
        public void Delt09_AtSessionMax_Fires()
        {
            // delta=500, sessionMax=400, sessionMin=-100. 500 >= 400 → fires +1
            var bar     = MakeBar(8, 20000.0, 20003.0, 19999.75, 20002.0, 500, 800, 700);
            var session = new SessionContext { TickSize = 0.25, SessionMaxDelta = 400, SessionMinDelta = -100 };

            var results = new DeltaDetector().OnBar(bar, session);

            bool hasDelt09 = false;
            foreach (var r in results) if (r.SignalId == "DELT-09" && r.Direction == +1) { hasDelt09 = true; break; }
            Assert.That(hasDelt09, Is.True, "DELT-09 should fire direction=+1 when delta >= sessionMax");
        }

        // -------------------------------------------------------------------
        // DELT-11: Velocity fires when CVD acceleration > totalVol * accelRatio
        // -------------------------------------------------------------------

        [Test]
        public void Delt11_Velocity_AcceleratingCvd_Fires()
        {
            // cvdHistory=[100, 200], current cvd=900
            // vel = 900 - 200 = 700; vel1 = 200 - 100 = 100; accel = 600
            // accelTh = 800 * 0.15 = 120. 600 > 120 → fires +1
            var bar     = MakeBar(9, 20000.0, 20003.0, 19999.75, 20002.75, 800, 900, 800);
            var session = new SessionContext { TickSize = 0.25 };
            SessionContext.Push(session.CvdHistory, 100L);
            SessionContext.Push(session.CvdHistory, 200L);

            var results = new DeltaDetector().OnBar(bar, session);

            SignalResult delt11 = null;
            foreach (var r in results) if (r.SignalId == "DELT-11" && r.Direction == +1) { delt11 = r; break; }
            Assert.That(delt11, Is.Not.Null, "DELT-11 should fire direction=+1 on accelerating CVD");
        }

        [Test]
        public void Delt11_Fixture_JsonIsValid()
        {
            string path = FixturePath("delt-11-velocity.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // DELT-08 / DELT-10 deferred guard
        // -------------------------------------------------------------------

        [Test]
        public void Delt08_NotFiredInWave4()
        {
            var bar     = MakeBar(11, 20000.0, 20003.0, 19999.75, 20002.0, 300, 500, 700);
            var session = new SessionContext { TickSize = 0.25 };

            // Pre-load 4 bars of delta history (DELT-08 would need this)
            for (int i = 0; i < 4; i++) SessionContext.Push(session.DeltaHistory, 100L + i * 50);

            var results = new DeltaDetector().OnBar(bar, session);

            bool hasDelt08 = false;
            foreach (var r in results) if (r.SignalId == "DELT-08") { hasDelt08 = true; break; }
            Assert.That(hasDelt08, Is.False, "DELT-08 should NOT fire in Wave 4 (deferred to Wave 5)");
        }

        [Test]
        public void Delt10_NotFiredInWave4()
        {
            var bar     = MakeBar(12, 20000.0, 20003.0, 19999.75, 20002.0, 300, 500, 700);
            var session = new SessionContext { TickSize = 0.25 };

            var results = new DeltaDetector().OnBar(bar, session);

            bool hasDelt10 = false;
            foreach (var r in results) if (r.SignalId == "DELT-10") { hasDelt10 = true; break; }
            Assert.That(hasDelt10, Is.False, "DELT-10 should NOT fire in Wave 4 (deferred to Wave 5)");
        }

        // -------------------------------------------------------------------
        // Rolling history: detector pushes current values to session after each bar
        // -------------------------------------------------------------------

        [Test]
        public void DeltaDetector_PushesHistoryAfterEvaluation()
        {
            var bar     = MakeBar(50, 20000.0, 20002.0, 19999.75, 20001.0, 300, 700, 600);
            var session = new SessionContext { TickSize = 0.25 };
            Assert.That(session.DeltaHistory.Count, Is.EqualTo(0));

            new DeltaDetector().OnBar(bar, session);

            Assert.That(session.DeltaHistory.Count, Is.EqualTo(1), "DeltaHistory should have 1 entry after first bar");
            Assert.That(session.CvdHistory.Count,   Is.EqualTo(1), "CvdHistory should have 1 entry after first bar");
            Assert.That(session.PriceHistory.Count, Is.EqualTo(1), "PriceHistory should have 1 entry after first bar");
        }
    }
}
