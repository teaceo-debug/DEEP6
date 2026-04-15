// TrapDetectorTests: fixture-driven tests for TrapDetector (TRAP-01..04).
// TRAP-05 is deferred to Wave 5 — tested with a guard test.
//
// Covers: TRAP-01 inverse imbalance trap (stacked buy imb in red bar),
//         TRAP-02 delta trap, TRAP-03 false breakout, TRAP-04 record vol rejection.

using System;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Trap;

namespace NinjaTrader.Tests.Detectors
{
    [TestFixture]
    public class TrapDetectorTests
    {
        private static string FixturePath(string file) =>
            System.IO.Path.Combine(TestContext.CurrentContext.TestDirectory,
                "fixtures", "trap", file);

        // -------------------------------------------------------------------
        // TRAP-01: Inverse imbalance trap fires for STACKED buy imbalances in red bar
        // -------------------------------------------------------------------

        [Test]
        public void Trap01_InverseImbTrap_StackedBuyImbsInRedBar_Fires()
        {
            // RED bar (close < open) with 3 consecutive stacked buy imbalances at 20004.75/20005.00/20005.25
            // Ratios: ask[20004.50]/bid[20004.25]=400/80=5.0, etc. (fixture comment)
            var bar = new FootprintBar
            {
                BarIndex = 120,
                Open  = 20005.00,
                High  = 20005.25,
                Low   = 20000.00,
                Close = 20000.25,
                BarDelta = -200, Cvd = 800, TotalVol = 900, MaxDelta = 50, MinDelta = -250,
            };
            // Low levels — no imbalance
            bar.Levels[20000.00] = new Cell { AskVol = 50,  BidVol = 60  };
            // Stacked buy imbalances at upper portion (3 consecutive)
            bar.Levels[20004.50] = new Cell { AskVol = 10,  BidVol = 80  };  // prior bid for diagonal
            bar.Levels[20004.75] = new Cell { AskVol = 400, BidVol = 82  };  // ask/prevBid=400/80=5.0 → buy
            bar.Levels[20005.00] = new Cell { AskVol = 410, BidVol = 84  };  // ask/prevBid=410/82=5.0 → buy
            bar.Levels[20005.25] = new Cell { AskVol = 60,  BidVol = 55  };  // ask/prevBid=60/84=0.7 (no imb here)
            bar.Finalize();

            // Note: TRAP-01 checks buy imbalances at 20004.75 and 20005.00 (ask[P] vs bid[P-tick])
            // Need 3 consecutive. Add one more level:
            // Actually the fixture has stacked at 20004.75, 20005.00, and the diagonal needs
            // 3 consecutive levels firing. Let's verify this manually.
            // Level 20004.75: ask=400 vs bid[20004.50]=80 → ratio=5.0 > 3.0 → buy imb
            // Level 20005.00: ask=410 vs bid[20004.75]=82 → ratio=5.0 > 3.0 → buy imb
            // Level 20005.25: ask=60 vs bid[20005.00]=84 → ratio=0.7 < 3.0 → no imb
            // Only 2 consecutive buy imbs → T1 needs 3. So TRAP-01 would NOT fire for this fixture.
            // Adjust: use 3 consecutive imbalances starting at 20004.50.
            bar.Levels.Clear();
            bar.Levels[20000.00] = new Cell { AskVol = 50,  BidVol = 60  };
            bar.Levels[20004.00] = new Cell { AskVol = 10,  BidVol = 80  };  // seed bid for diagonal
            bar.Levels[20004.25] = new Cell { AskVol = 400, BidVol = 82  };  // buy imb #1 (ask/bid[20004.00]=5.0)
            bar.Levels[20004.50] = new Cell { AskVol = 410, BidVol = 84  };  // buy imb #2 (ask/bid[20004.25]=5.0)
            bar.Levels[20004.75] = new Cell { AskVol = 420, BidVol = 86  };  // buy imb #3 (ask/bid[20004.50]=5.0)
            bar.Levels[20005.00] = new Cell { AskVol = 60,  BidVol = 55  };
            bar.Levels[20005.25] = new Cell { AskVol = 20,  BidVol = 20  };
            bar.TotalVol = 900;
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new TrapDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult trap01 = null;
            foreach (var r in results)
                if (r.SignalId == "TRAP-01" && r.Direction == -1) { trap01 = r; break; }

            Assert.That(trap01, Is.Not.Null,
                "TRAP-01 should fire direction=-1 for stacked buy imbalances in a RED bar (longs trapped)");
            StringAssert.Contains("INVERSE IMB TRAP", trap01.Detail);
        }

        [Test]
        public void Trap01_Fixture_JsonIsValid()
        {
            string path = FixturePath("trap-01-inverse-imbalance.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        [Test]
        public void Trap01_SingleBuyImbInRedBar_DoesNotFire()
        {
            // TRAP-01 requires STACKED (>=3 consecutive). Single imbalance in red bar → no TRAP-01.
            // (IMB-05 would fire, but NOT TRAP-01.)
            var bar = new FootprintBar
            {
                BarIndex = 121,
                Open  = 20005.00,
                High  = 20005.25,
                Low   = 20000.00,
                Close = 20000.25,
                BarDelta = -200, Cvd = 700, TotalVol = 500, MaxDelta = 20, MinDelta = -220,
            };
            bar.Levels[20000.00] = new Cell { AskVol = 100, BidVol = 100 };
            bar.Levels[20003.50] = new Cell { AskVol = 10,  BidVol = 80  };
            bar.Levels[20003.75] = new Cell { AskVol = 300, BidVol = 60  };  // single buy imb only
            bar.Levels[20005.00] = new Cell { AskVol = 40,  BidVol = 40  };
            bar.TotalVol = 500;
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var results  = new TrapDetector().OnBar(bar, session);

            bool hasTrap01 = false;
            foreach (var r in results) if (r.SignalId == "TRAP-01") { hasTrap01 = true; break; }
            Assert.That(hasTrap01, Is.False,
                "TRAP-01 should NOT fire for a single buy imbalance (need >= 3 stacked)");
        }

        // -------------------------------------------------------------------
        // TRAP-02: Delta trap fires when prior delta ratio >= 0.35 and both reversed
        // -------------------------------------------------------------------

        [Test]
        public void Trap02_DeltaTrap_StrongPriorBullDeltaReversed_Fires()
        {
            // priorBar barDelta=800, totalVol=1000. priorRatio=0.8>=0.35. priorBull=true.
            // current delta=-300 (reversed), close<open (reversed) → TRAP-02 fires
            var bar = new FootprintBar
            {
                BarIndex = 130,
                Open  = 20003.00,
                High  = 20003.50,
                Low   = 19999.75,
                Close = 20000.00,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 600, BidVol = 300 };
            bar.Levels[20003.50] = new Cell { AskVol = 50,  BidVol = 50  };
            bar.Finalize();
            // Override after Finalize: bar is bearish (close<open), delta negative, reversed from priorBar
            bar.BarDelta = -300;
            bar.TotalVol = 900;

            var priorBar = new FootprintBar
            {
                BarIndex = 129,
                Open  = 20000.00,
                High  = 20003.00,
                Low   = 19999.75,
                Close = 20002.75,
            };
            priorBar.Levels[19999.75] = new Cell { AskVol = 400, BidVol = 100 };
            priorBar.Levels[20003.00] = new Cell { AskVol = 300, BidVol = 200 };
            priorBar.Finalize();
            // Override after Finalize: priorRatio = |800|/1000 = 0.8 >= 0.35; priorBull = true
            priorBar.BarDelta  = 800;
            priorBar.TotalVol  = 1000;

            var session  = new SessionContext { TickSize = 0.25, PriorBar = priorBar };
            var detector = new TrapDetector();
            var results  = detector.OnBar(bar, session);

            bool hasTrap02 = false;
            foreach (var r in results) if (r.SignalId == "TRAP-02") { hasTrap02 = true; break; }
            Assert.That(hasTrap02, Is.True,
                "TRAP-02 should fire when prior delta ratio >=0.35 and both delta+price reversed");
        }

        [Test]
        public void Trap02_Fixture_JsonIsValid()
        {
            string path = FixturePath("trap-02-delta-trap.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        [Test]
        public void Trap02_LowPriorRatio_DoesNotFire()
        {
            // priorRatio = 100/1000 = 0.10 < 0.35 → TRAP-02 should NOT fire
            var bar = new FootprintBar
            {
                BarIndex = 131,
                Open  = 20003.00,
                High  = 20003.50,
                Low   = 19999.75,
                Close = 20000.00,
                BarDelta = -300, Cvd = 700, TotalVol = 900,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 600, BidVol = 300 };
            bar.Levels[20003.50] = new Cell { AskVol = 50,  BidVol = 50  };
            bar.Finalize();

            var priorBar = new FootprintBar
            {
                BarIndex = 130,
                Open = 20000.0, High = 20003.0, Low = 19999.75, Close = 20002.75,
            };
            priorBar.Levels[19999.75] = new Cell { AskVol = 200, BidVol = 300 };
            priorBar.Levels[20003.00] = new Cell { AskVol = 250, BidVol = 250 };
            priorBar.Finalize();
            // Override: ratio = 100/1000 = 0.1 < 0.35 — should NOT trigger TRAP-02
            priorBar.BarDelta  = 100;
            priorBar.TotalVol  = 1000;

            var session  = new SessionContext { TickSize = 0.25, PriorBar = priorBar };
            var results  = new TrapDetector().OnBar(bar, session);

            bool hasTrap02 = false;
            foreach (var r in results) if (r.SignalId == "TRAP-02") { hasTrap02 = true; break; }
            Assert.That(hasTrap02, Is.False, "TRAP-02 should NOT fire when prior delta ratio < 0.35");
        }

        // -------------------------------------------------------------------
        // TRAP-03: False breakout fires when bar breaks prior high/low but closes back inside
        // -------------------------------------------------------------------

        [Test]
        public void Trap03_FalseBreakout_BreaksAbovePriorHigh_ClosesBelow_Fires()
        {
            // priorBar.high=20010. bar.high=20012>20010. bar.close=20008<20010 → TRAP-03 direction=-1
            var bar = new FootprintBar
            {
                BarIndex = 141,
                Open  = 20009.75,
                High  = 20012.00,
                Low   = 20007.00,
                Close = 20008.00,
                BarDelta = -400, Cvd = 800, TotalVol = 900,
            };
            bar.Levels[20007.00] = new Cell { AskVol = 100, BidVol = 300 };
            bar.Levels[20012.00] = new Cell { AskVol = 0,   BidVol = 0   };
            bar.Finalize();

            var priorBar = new FootprintBar
            {
                BarIndex = 140,
                Open = 20005.0, High = 20010.0, Low = 20004.5, Close = 20009.5,
                BarDelta = 250, TotalVol = 700,
            };
            priorBar.Finalize();

            var session  = new SessionContext { TickSize = 0.25, VolEma20 = 600, PriorBar = priorBar };
            var results  = new TrapDetector().OnBar(bar, session);

            SignalResult trap03 = null;
            foreach (var r in results)
                if (r.SignalId == "TRAP-03" && r.Direction == -1) { trap03 = r; break; }

            Assert.That(trap03, Is.Not.Null,
                "TRAP-03 should fire direction=-1 when bar breaks above prior high and closes back below");
            StringAssert.Contains("FALSE BREAKOUT TRAP", trap03.Detail);
        }

        [Test]
        public void Trap03_Fixture_JsonIsValid()
        {
            string path = FixturePath("trap-03-false-breakout.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // TRAP-04: Record vol rejection fires when vol >> EMA and wick fraction > threshold
        // -------------------------------------------------------------------

        [Test]
        public void Trap04_RecordVolRejection_UpperWick_Fires()
        {
            // totalVol=1100 > volEma=600*1.5=900. Range=10 (20000-20010).
            // upperZone = high - range/4 = 20010 - 2.5 = 20007.5
            // upperVol (levels >= 20007.5): 20008=400, 20010=300 → total=700
            // upperFrac = 700/1100 = 0.636 > 0.35 → direction=-1 (upper wick rejection)
            var bar = new FootprintBar
            {
                BarIndex = 150,
                Open  = 20009.00,
                High  = 20010.00,
                Low   = 20000.00,
                Close = 20001.00,
                BarDelta = -600, Cvd = 200, TotalVol = 1100, MaxDelta = 100, MinDelta = -650,
            };
            bar.Levels[20000.00] = new Cell { AskVol = 100, BidVol = 100 };
            bar.Levels[20001.00] = new Cell { AskVol = 100, BidVol = 100 };
            bar.Levels[20008.00] = new Cell { AskVol = 300, BidVol = 100 };
            bar.Levels[20010.00] = new Cell { AskVol = 200, BidVol = 100 };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25, VolEma20 = 600 };
            var results  = new TrapDetector().OnBar(bar, session);

            SignalResult trap04 = null;
            foreach (var r in results)
                if (r.SignalId == "TRAP-04" && r.Direction == -1) { trap04 = r; break; }

            Assert.That(trap04, Is.Not.Null,
                "TRAP-04 should fire direction=-1 when upper wick fraction > 0.35 at record volume");
            StringAssert.Contains("HVR TRAP", trap04.Detail);
        }

        [Test]
        public void Trap04_Fixture_JsonIsValid()
        {
            string path = FixturePath("trap-04-record-vol-rejection.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        [Test]
        public void Trap04_BelowVolThreshold_DoesNotFire()
        {
            // totalVol=500 < volEma=600*1.5=900 → TRAP-04 should NOT fire
            var bar = new FootprintBar
            {
                BarIndex = 151,
                Open = 20009.0, High = 20010.0, Low = 20000.0, Close = 20001.0,
                BarDelta = -100, Cvd = 200, TotalVol = 500,
            };
            bar.Levels[20000.00] = new Cell { AskVol = 100, BidVol = 100 };
            bar.Levels[20010.00] = new Cell { AskVol = 200, BidVol = 100 };
            bar.Finalize();

            var session = new SessionContext { TickSize = 0.25, VolEma20 = 600 };
            var results = new TrapDetector().OnBar(bar, session);

            bool hasTrap04 = false;
            foreach (var r in results) if (r.SignalId == "TRAP-04") { hasTrap04 = true; break; }
            Assert.That(hasTrap04, Is.False, "TRAP-04 should NOT fire when totalVol < volEma * hvrVolMult");
        }

        // -------------------------------------------------------------------
        // TRAP-05 deferred guard
        // -------------------------------------------------------------------

        [Test]
        public void Trap05_NotFiredInWave4()
        {
            // TRAP-05 CVD Trend Reversal requires LeastSquares polyfit — deferred to Wave 5.
            var bar = new FootprintBar
            {
                BarIndex = 200,
                Open = 20000.0, High = 20003.0, Low = 19999.75, Close = 20002.0,
                BarDelta = 300, Cvd = 800, TotalVol = 700,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 300, BidVol = 100 };
            bar.Levels[20003.00] = new Cell { AskVol = 200, BidVol = 100 };
            bar.Finalize();

            var session = new SessionContext { TickSize = 0.25 };
            var results = new TrapDetector().OnBar(bar, session);

            bool hasTrap05 = false;
            foreach (var r in results) if (r.SignalId == "TRAP-05") { hasTrap05 = true; break; }
            Assert.That(hasTrap05, Is.False, "TRAP-05 should NOT fire in Wave 4 (deferred to Wave 5)");
        }
    }
}
