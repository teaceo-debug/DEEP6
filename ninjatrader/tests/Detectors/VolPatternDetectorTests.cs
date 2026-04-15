// VolPatternDetectorTests: fixture-driven tests for VolPatternDetector (VOLP-01..06).
//
// Covers: VOLP-01 sequencing, VOLP-02 bubble, VOLP-03 surge, VOLP-04 POC wave,
//         VOLP-05 delta velocity spike, VOLP-06 big delta per level.

using System;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.VolPattern;

namespace NinjaTrader.Tests.Detectors
{
    [TestFixture]
    public class VolPatternDetectorTests
    {
        private static string FixturePath(string file) =>
            System.IO.Path.Combine(TestContext.CurrentContext.TestDirectory,
                "fixtures", "volpattern", file);

        private static FootprintBar MakeBar(int idx, double open, double high, double low, double close,
            long barDelta, long cvd, long totalVol)
        {
            var bar = new FootprintBar
            {
                BarIndex = idx, Open = open, High = high, Low = low, Close = close,
            };
            bar.Levels[low]  = new Cell { AskVol = (long)(totalVol * 0.4), BidVol = (long)(totalVol * 0.1) };
            bar.Levels[high] = new Cell { AskVol = (long)(totalVol * 0.3), BidVol = (long)(totalVol * 0.2) };
            bar.Finalize();
            // Override after Finalize — Finalize recomputes BarDelta/TotalVol/Cvd from levels.
            bar.BarDelta = barDelta;
            bar.Cvd      = cvd;
            bar.TotalVol = totalVol;
            bar.MaxDelta = barDelta > 0 ? barDelta + 20 : 20;
            bar.MinDelta = barDelta < 0 ? barDelta - 20 : -20;
            return bar;
        }

        // -------------------------------------------------------------------
        // VOLP-01: Volume sequencing fires for 3+ bars of non-decreasing vol
        // -------------------------------------------------------------------

        [Test]
        public void Volp01_Sequencing_ThreeEscalatingBars_Fires()
        {
            // volHistory=[300, 400], current=600. All non-decreasing → run=3 >= minBars=3 → fires
            var bar     = MakeBar(92, 20001.50, 20003.00, 20001.25, 20002.75, 200, 820, 600);
            var session = new SessionContext { TickSize = 0.25, VolEma20 = 350 };
            SessionContext.Push(session.VolHistory,   300L);
            SessionContext.Push(session.VolHistory,   400L);
            SessionContext.Push(session.DeltaHistory, 100L);
            SessionContext.Push(session.DeltaHistory, 120L);

            var results = new VolPatternDetector().OnBar(bar, session);

            SignalResult volp01 = null;
            foreach (var r in results) if (r.SignalId == "VOLP-01") { volp01 = r; break; }
            Assert.That(volp01, Is.Not.Null, "VOLP-01 should fire for 3 escalating volume bars");
            Assert.That(volp01.Direction, Is.EqualTo(+1), "Net positive delta → direction=+1");
        }

        [Test]
        public void Volp01_Fixture_JsonIsValid()
        {
            string path = FixturePath("volp-01-sequencing.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        [Test]
        public void Volp01_OnlyTwoBarsInHistory_DoesNotFire()
        {
            // Only 1 prior bar in history (run=2 < minBars=3) → should NOT fire
            var bar     = MakeBar(50, 20001.0, 20003.0, 20000.75, 20002.5, 200, 700, 500);
            var session = new SessionContext { TickSize = 0.25, VolEma20 = 300 };
            SessionContext.Push(session.VolHistory, 400L);  // only 1 prior bar

            var results = new VolPatternDetector().OnBar(bar, session);

            bool hasVolp01 = false;
            foreach (var r in results) if (r.SignalId == "VOLP-01") { hasVolp01 = true; break; }
            Assert.That(hasVolp01, Is.False, "VOLP-01 should NOT fire with only 2 bars in sequence");
        }

        // -------------------------------------------------------------------
        // VOLP-02: Bubble fires when single level vol > avg * 3.0
        // -------------------------------------------------------------------

        [Test]
        public void Volp02_Bubble_SingleLevelAboveThreshold_Fires()
        {
            // 3 levels: 2 with vol=50, 1 with vol=500. avgLevel=200, bubbleTh=200*3=600? No.
            // avg=600/3=200, bubble=200*3=600. Level 500 < 600. Adjust:
            // 2 levels each vol=50 (100 total), 1 level vol=400. avgLevel=500/3≈167, bubble=167*3=500. 400 < 500? No.
            // Use: 2 levels vol=10 each (20 total), 1 level vol=100. avgLevel=120/3=40, bubble=40*3=120. 100 < 120? No.
            // 2 levels vol=10 each (20 total), 1 level vol=200. avg=220/3≈73, bubble=73*3=220. 200<220? Still no.
            // Use 3 levels: two with 20 each, one with 300. avg=340/3≈113, bubble=113*3=340. 300<340. No.
            // Correct: vol must EXCEED bubble threshold. Use: two levels 5 each (10), one level 1000.
            // avg=1010/3≈337, bubble=337*3=1010. 1000 < 1010. Close but no. Use 2 levels=1 each, 1 level=500.
            // avg=502/3≈167, bubble=167*3=502. 500 < 502. One more: level=600.
            // avg=602/3≈200, bubble=200*3=600. 600 >= 600? Uses strict >. No.
            // Use level=700: avg=702/3=234, bubble=234*3=702. 700 < 702. Argh.
            // Just use: 1 level with 10, another with 10, bubble level with 1000.
            // total=1020, avg=340, bubble=1020. Need lv > 1020? That's impossible since lv=1000.
            // The formula: avgLevelVol = totalVol / levelCount. For 3 levels: avg = total/3.
            // threshold = avg * mult = (total/3) * 3 = total.
            // So level must be > totalVol to fire with 3 levels and mult=3.
            // BUT: level vol IS included in totalVol. So need level > sum_of_all.
            // Solution: use 2 levels only. avg = total/2. threshold = total/2*3 = total*1.5.
            // level vol must be > total*1.5. Impossible (level <= total).
            // Correct solution: use many levels (10) so avg is small.
            // 9 levels with 10 each (90), 1 level with 400. total=490, avg=49, bubble=49*3=147. 400 > 147 → fires!
            var bar = new FootprintBar
            {
                BarIndex = 30,
                Open = 20000.00, High = 20003.00, Low = 20000.00, Close = 20002.00,
                BarDelta = 100, Cvd = 500, TotalVol = 490, MaxDelta = 120, MinDelta = -20,
            };
            // 9 small levels + 1 large bubble level
            for (int i = 0; i < 9; i++)
                bar.Levels[20000.00 + i * 0.25] = new Cell { AskVol = 5, BidVol = 5 };
            bar.Levels[20002.25] = new Cell { AskVol = 250, BidVol = 150 };  // vol=400 > bubble thresh
            bar.Finalize();

            var session = new SessionContext { TickSize = 0.25, VolEma20 = 400 };
            var results = new VolPatternDetector().OnBar(bar, session);

            bool hasVolp02 = false;
            foreach (var r in results) if (r.SignalId == "VOLP-02") { hasVolp02 = true; break; }
            Assert.That(hasVolp02, Is.True, "VOLP-02 should fire when one level vol >> average level vol");
        }

        // -------------------------------------------------------------------
        // VOLP-03: Surge fires when totalVol > volEma * 3.0
        // -------------------------------------------------------------------

        [Test]
        public void Volp03_Surge_HighVol_Fires()
        {
            // totalVol=2000 > volEma=500 * 3 = 1500 → fires
            var bar     = MakeBar(31, 20000.0, 20003.0, 19999.75, 20002.0, 400, 900, 2000);
            var session = new SessionContext { TickSize = 0.25, VolEma20 = 500 };
            var results = new VolPatternDetector().OnBar(bar, session);

            bool hasVolp03 = false;
            foreach (var r in results) if (r.SignalId == "VOLP-03") { hasVolp03 = true; break; }
            Assert.That(hasVolp03, Is.True, "VOLP-03 should fire when totalVol > volEma * 3.0");
        }

        // -------------------------------------------------------------------
        // VOLP-04: POC Wave fires when last N POC prices are strictly monotonic
        // -------------------------------------------------------------------

        [Test]
        public void Volp04_PocWave_StrictlyIncreasingPocs_Fires()
        {
            // pocHistory=[20000.00, 20001.25, 20002.50] all strictly increasing → fires +1
            var bar     = MakeBar(100, 20002.0, 20003.50, 20001.75, 20003.0, 300, 1200, 800);
            var session = new SessionContext { TickSize = 0.25, VolEma20 = 500 };
            SessionContext.Push(session.PocHistory, 20000.00);
            SessionContext.Push(session.PocHistory, 20001.25);
            SessionContext.Push(session.PocHistory, 20002.50);

            var results = new VolPatternDetector().OnBar(bar, session);

            SignalResult volp04 = null;
            foreach (var r in results) if (r.SignalId == "VOLP-04") { volp04 = r; break; }
            Assert.That(volp04, Is.Not.Null, "VOLP-04 should fire for strictly increasing POC history");
            Assert.That(volp04.Direction, Is.EqualTo(+1), "Increasing POC → direction=+1");
        }

        [Test]
        public void Volp04_Fixture_JsonIsValid()
        {
            string path = FixturePath("volp-04-poc-wave.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        [Test]
        public void Volp04_PocWave_RequiresStrictlyMonotonicPocs()
        {
            // 3 POC entries: 20000.00, 20002.00, 20001.00 — NOT strictly increasing → should NOT fire
            var bar     = MakeBar(101, 20001.0, 20003.0, 20000.75, 20002.5, 200, 800, 600);
            var session = new SessionContext { TickSize = 0.25, VolEma20 = 400 };
            SessionContext.Push(session.PocHistory, 20000.00);
            SessionContext.Push(session.PocHistory, 20002.00);
            SessionContext.Push(session.PocHistory, 20001.00);  // went backward

            var results = new VolPatternDetector().OnBar(bar, session);

            bool hasVolp04 = false;
            foreach (var r in results) if (r.SignalId == "VOLP-04") { hasVolp04 = true; break; }
            Assert.That(hasVolp04, Is.False, "VOLP-04 should NOT fire when POC history is not strictly monotonic");
        }

        // -------------------------------------------------------------------
        // VOLP-05: Delta velocity spike fires when |velocity| > volEma * 0.5
        // -------------------------------------------------------------------

        [Test]
        public void Volp05_DeltaVelocitySpike_LargePositiveVelocity_Fires()
        {
            // priorDelta=50, currentDelta=800, velocity=750, threshold=500*0.5=250. 750>250 → fires +1
            var bar     = MakeBar(110, 20000.25, 20003.00, 20000.00, 20002.75, 800, 1200, 1100);
            var session = new SessionContext { TickSize = 0.25, VolEma20 = 500 };
            SessionContext.Push(session.DeltaHistory, 50L);

            var results = new VolPatternDetector().OnBar(bar, session);

            SignalResult volp05 = null;
            foreach (var r in results) if (r.SignalId == "VOLP-05" && r.Direction == +1) { volp05 = r; break; }
            Assert.That(volp05, Is.Not.Null, "VOLP-05 should fire direction=+1 when delta velocity >> threshold");
        }

        [Test]
        public void Volp05_Fixture_JsonIsValid()
        {
            string path = FixturePath("volp-05-delta-velocity-spike.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // VOLP-06: Big delta per level fires when |netDelta| at level > total * 0.15
        // -------------------------------------------------------------------

        [Test]
        public void Volp06_BigDeltaPerLevel_SingleLevelDomination_Fires()
        {
            // level 20000.00: ask=400, bid=50 → net=350. total=500. ratio=0.7 > 0.15 → fires +1
            var bar = new FootprintBar
            {
                BarIndex = 40,
                Open = 20000.00, High = 20001.50, Low = 20000.00, Close = 20001.25,
                BarDelta = 300, Cvd = 500, TotalVol = 500, MaxDelta = 320, MinDelta = -20,
            };
            bar.Levels[20000.00] = new Cell { AskVol = 400, BidVol = 50  };  // net=350, ratio=0.7
            bar.Levels[20001.50] = new Cell { AskVol = 25,  BidVol = 25  };
            bar.Finalize();

            var session = new SessionContext { TickSize = 0.25, VolEma20 = 350 };
            var results = new VolPatternDetector().OnBar(bar, session);

            bool hasVolp06 = false;
            foreach (var r in results) if (r.SignalId == "VOLP-06" && r.Direction == +1) { hasVolp06 = true; break; }
            Assert.That(hasVolp06, Is.True, "VOLP-06 should fire when single level has large ask-bid imbalance");
        }
    }
}
