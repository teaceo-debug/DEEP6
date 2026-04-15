// ExhaustionParityTests: fixture-driven parity tests for EXH-01..06.
//
// Each test constructs a bar matching the fixture scenario, runs ExhaustionDetector.OnBar(),
// and asserts the expected SignalResult is present (SignalId exact, Direction exact,
// Strength in range, Detail substring match).
//
// Also verifies cooldown behavior: EXH-02 fired at bar N must not re-fire at bar N+1.

using System;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion;

namespace NinjaTrader.Tests.Detectors
{
    [TestFixture]
    public class ExhaustionParityTests
    {
        private static string FixtureDir => Path.Combine(
            TestContext.CurrentContext.TestDirectory, "fixtures", "exhaustion");

        // -----------------------------------------------------------------------
        // EXH-01: Zero Print (delta-gate exempt)
        // -----------------------------------------------------------------------

        [Test]
        public void Exh01_ZeroPrintFixture_EmitsSignal()
        {
            var bar = new FootprintBar
            {
                BarIndex = 10, Open = 20000.00, High = 20005.00, Low = 19999.75, Close = 20004.00
            };
            bar.Levels[20005.00] = new Cell { AskVol = 200, BidVol = 10  };
            bar.Levels[20004.00] = new Cell { AskVol = 150, BidVol = 20  };
            bar.Levels[20002.00] = new Cell { AskVol = 0,   BidVol = 0   };
            bar.Levels[20000.00] = new Cell { AskVol = 100, BidVol = 100 };
            bar.Levels[19999.75] = new Cell { AskVol = 10,  BidVol = 80  };
            bar.Finalize(0);

            var cfg = new ExhaustionConfig { DeltaGateEnabled = false };
            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25 };
            session.BarsSinceOpen = bar.BarIndex;

            var results = new ExhaustionDetector(cfg).OnBar(bar, session);
            AssertSignalPresent(results, "EXH-01", +1, 0.59, 0.61, "ZERO PRINT");
        }

        [Test]
        public void Exh01_FixtureJson_IsValid()
        {
            string path = Path.Combine(FixtureDir, "exh-01-zero-print.json");
            Assert.That(File.Exists(path), Is.True, "exh-01-zero-print.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -----------------------------------------------------------------------
        // EXH-02: Exhaustion Print at bar high
        // -----------------------------------------------------------------------

        [Test]
        public void Exh02_ExhaustionPrintFixture_EmitsSignal()
        {
            // bearish bar (close=20002.50 < open=20004). barDelta=110 > 0 → gate passes.
            // hiPx=20005, hiAsk=120, pct=15% >= effMin/3=11.67%. strength=0.75.
            // EXH-05 also fires (|barDelta|=110 < totalVol*0.15=120? borderline).
            // Test only asserts EXH-02 is present with correct values.
            var bar = new FootprintBar
            {
                BarIndex = 15, Open = 20004.00, High = 20005.00, Low = 20002.00, Close = 20002.50
            };
            bar.Levels[20005.00] = new Cell { AskVol = 120, BidVol = 10  };
            bar.Levels[20004.50] = new Cell { AskVol = 100, BidVol = 90  };
            bar.Levels[20004.00] = new Cell { AskVol = 100, BidVol = 90  };
            bar.Levels[20003.00] = new Cell { AskVol = 80,  BidVol = 80  };
            bar.Levels[20002.50] = new Cell { AskVol = 60,  BidVol = 60  };
            bar.Levels[20002.00] = new Cell { AskVol = 5,   BidVol = 5   };
            bar.Finalize(0);
            // totalVol=800, barDelta=110+10+10+0+0+0=130. pct=120/800*100=15%. strength=0.75.
            // EXH-05: |130| vs 800*0.15=120 — 130>120 means EXH-05 also fires but we only check EXH-02.

            var session = new SessionContext { Atr20 = 5.0, VolEma20 = 300.0, TickSize = 0.25 };
            session.BarsSinceOpen = bar.BarIndex;

            var results = new ExhaustionDetector().OnBar(bar, session);
            AssertSignalPresent(results, "EXH-02", -1, 0.73, 0.77, "EXHAUSTION PRINT at high");
        }

        [Test]
        public void Exh02_Cooldown_PreventsDuplicateFire()
        {
            // After EXH-02 fires at bar 15, same bar at barIndex 16 must not re-fire (CooldownBars=5).
            var detector = new ExhaustionDetector();

            System.Func<int, FootprintBar> makeBar = idx =>
            {
                var b = new FootprintBar
                {
                    BarIndex = idx, Open = 20004.00, High = 20005.00, Low = 20002.00, Close = 20002.50
                };
                b.Levels[20005.00] = new Cell { AskVol = 120, BidVol = 10  };
                b.Levels[20004.50] = new Cell { AskVol = 100, BidVol = 90  };
                b.Levels[20004.00] = new Cell { AskVol = 100, BidVol = 90  };
                b.Levels[20003.00] = new Cell { AskVol = 80,  BidVol = 80  };
                b.Levels[20002.50] = new Cell { AskVol = 60,  BidVol = 60  };
                b.Levels[20002.00] = new Cell { AskVol = 5,   BidVol = 5   };
                b.Finalize(0);
                return b;
            };

            var session = new SessionContext { Atr20 = 5.0, VolEma20 = 300.0, TickSize = 0.25 };

            session.BarsSinceOpen = 15;
            var r1 = detector.OnBar(makeBar(15), session);
            bool fired1 = ContainsSignal(r1, "EXH-02");
            Assert.That(fired1, Is.True, "EXH-02 should fire on first bar");

            session.BarsSinceOpen = 16;
            var r2 = detector.OnBar(makeBar(16), session);
            bool fired2 = ContainsSignal(r2, "EXH-02");
            Assert.That(fired2, Is.False, "EXH-02 must NOT re-fire within cooldown (bar 16, last=15, cooldown=5)");
        }

        [Test]
        public void Exh02_FixtureJson_IsValid()
        {
            string path = Path.Combine(FixtureDir, "exh-02-exhaustion-print.json");
            Assert.That(File.Exists(path), Is.True, "exh-02-exhaustion-print.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -----------------------------------------------------------------------
        // EXH-03: Thin Print — 4 body levels below ThinPct threshold
        // -----------------------------------------------------------------------

        [Test]
        public void Exh03_ThinPrintFixture_EmitsSignal()
        {
            // bearish bar. maxLevelVol=600 (at 20005). 4 body levels < 0.05*600=30 → thinCount=4.
            // dir = close<open ? -1 : +1 → bearish → dir=-1. strength=min(4/7,1)=0.571.
            // EXH-04: avgLevelVol=94.9, fatMult*avg=189.8. 20005 vol=600>189.8 → EXH-04 fires too,
            //         but we only assert EXH-03 is present.
            var bar = new FootprintBar
            {
                BarIndex = 25, Open = 20005.00, High = 20006.00, Low = 20002.00, Close = 20002.50
            };
            bar.Levels[20006.00] = new Cell { AskVol = 5,   BidVol = 5   };
            bar.Levels[20005.00] = new Cell { AskVol = 400, BidVol = 200 };
            bar.Levels[20004.75] = new Cell { AskVol = 8,   BidVol = 4   };
            bar.Levels[20004.50] = new Cell { AskVol = 6,   BidVol = 3   };
            bar.Levels[20004.25] = new Cell { AskVol = 5,   BidVol = 2   };
            bar.Levels[20003.50] = new Cell { AskVol = 7,   BidVol = 4   };
            bar.Levels[20002.50] = new Cell { AskVol = 50,  BidVol = 40  };
            bar.Levels[20002.00] = new Cell { AskVol = 10,  BidVol = 10  };
            bar.Finalize(0);

            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25 };
            session.BarsSinceOpen = bar.BarIndex;

            var results = new ExhaustionDetector().OnBar(bar, session);
            AssertSignalPresent(results, "EXH-03", -1, 0.55, 0.60, "THIN PRINT");
        }

        [Test]
        public void Exh03_FixtureJson_IsValid()
        {
            string path = Path.Combine(FixtureDir, "exh-03-thin-print.json");
            Assert.That(File.Exists(path), Is.True, "exh-03-thin-print.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -----------------------------------------------------------------------
        // EXH-04: Fat Print — first sorted level exceeds avgLevelVol*FatMult
        // -----------------------------------------------------------------------

        [Test]
        public void Exh04_FatPrintFixture_EmitsSignal()
        {
            // bearish bar. avgLevelVol=260. FatMult*avg=520. sorted[0]=20002(900>520).
            // dir=0. strength=min(900/(260*2*2),1)=0.865.
            // EXH-05: |barDelta|=120 < totalVol*0.15=156 → NOT fires.
            var bar = new FootprintBar
            {
                BarIndex = 40, Open = 20004.00, High = 20005.00, Low = 20002.00, Close = 20002.50
            };
            bar.Levels[20002.00] = new Cell { AskVol = 500, BidVol = 400 };
            bar.Levels[20003.00] = new Cell { AskVol = 40,  BidVol = 30  };
            bar.Levels[20004.00] = new Cell { AskVol = 30,  BidVol = 20  };
            bar.Levels[20005.00] = new Cell { AskVol = 10,  BidVol = 10  };
            bar.Finalize(0);
            // totalVol=1040, avgLevelVol=260, strength=min(900/1040,1)=0.865

            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25 };
            session.BarsSinceOpen = bar.BarIndex;

            var results = new ExhaustionDetector().OnBar(bar, session);
            AssertSignalPresent(results, "EXH-04", 0, 0.84, 0.90, "FAT PRINT");
        }

        [Test]
        public void Exh04_FixtureJson_IsValid()
        {
            string path = Path.Combine(FixtureDir, "exh-04-fat-print.json");
            Assert.That(File.Exists(path), Is.True, "exh-04-fat-print.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -----------------------------------------------------------------------
        // EXH-05: Fading Momentum — |barDelta| > totalVol*0.15, price up but delta down
        // -----------------------------------------------------------------------

        [Test]
        public void Exh05_FadingMomentumFixture_EmitsSignal()
        {
            // bullish bar (close>open). barDelta=-410 < 0 → gate passes (bullish→barDelta<0).
            // |410| > 590*0.15=88.5 → EXH-05 fires dir=-1. strength=min(410/590,1)=0.695.
            var bar = new FootprintBar
            {
                BarIndex = 45, Open = 20001.00, High = 20004.00, Low = 20000.50, Close = 20003.50
            };
            bar.Levels[20000.50] = new Cell { AskVol = 10,  BidVol = 200 };
            bar.Levels[20001.00] = new Cell { AskVol = 20,  BidVol = 150 };
            bar.Levels[20002.00] = new Cell { AskVol = 30,  BidVol = 80  };
            bar.Levels[20003.50] = new Cell { AskVol = 20,  BidVol = 60  };
            bar.Levels[20004.00] = new Cell { AskVol = 10,  BidVol = 10  };
            bar.Finalize(0);
            // totalVol=590, barDelta=-410, |barDelta|/totalVol=0.695

            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25 };
            session.BarsSinceOpen = bar.BarIndex;

            var results = new ExhaustionDetector().OnBar(bar, session);
            AssertSignalPresent(results, "EXH-05", -1, 0.68, 0.72, "FADING MOMENTUM");
        }

        [Test]
        public void Exh05_FixtureJson_IsValid()
        {
            string path = Path.Combine(FixtureDir, "exh-05-fading-momentum.json");
            Assert.That(File.Exists(path), Is.True, "exh-05-fading-momentum.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -----------------------------------------------------------------------
        // EXH-06: Bid/Ask Fade — currHighAsk < priorHighAsk * FadeThreshold
        // -----------------------------------------------------------------------

        [Test]
        public void Exh06_BidAskFadeFixture_EmitsSignal()
        {
            // bearish bar (close=20002.25 < open=20004.50). barDelta=65>0 → gate passes.
            // currHiAsk=30, priorHiAsk=200, threshold=120. 30<120 → EXH-06 fires dir=-1.
            // strength=1-(30/200)=0.85.
            // EXH-05: |barDelta|=65 > totalVol*0.15=335*0.15=50.25 → EXH-05 also fires,
            //         but we only assert EXH-06 is present.
            var priorBar = new FootprintBar
            {
                BarIndex = 59, Open = 20003.00, High = 20005.00, Low = 20001.00, Close = 20004.50
            };
            priorBar.Levels[20005.00] = new Cell { AskVol = 200, BidVol = 50  };
            priorBar.Levels[20004.50] = new Cell { AskVol = 100, BidVol = 80  };
            priorBar.Levels[20003.00] = new Cell { AskVol = 60,  BidVol = 40  };
            priorBar.Levels[20002.00] = new Cell { AskVol = 30,  BidVol = 20  };
            priorBar.Levels[20001.00] = new Cell { AskVol = 10,  BidVol = 10  };
            priorBar.Finalize(0);

            var bar = new FootprintBar
            {
                BarIndex = 60, Open = 20004.50, High = 20005.00, Low = 20002.00, Close = 20002.25
            };
            bar.Levels[20005.00] = new Cell { AskVol = 30,  BidVol = 10  };
            bar.Levels[20004.00] = new Cell { AskVol = 80,  BidVol = 60  };
            bar.Levels[20003.00] = new Cell { AskVol = 60,  BidVol = 40  };
            bar.Levels[20002.25] = new Cell { AskVol = 20,  BidVol = 15  };
            bar.Levels[20002.00] = new Cell { AskVol = 10,  BidVol = 10  };
            bar.Finalize(0);

            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25 };
            session.PriorBar = priorBar;
            session.BarsSinceOpen = bar.BarIndex;

            var results = new ExhaustionDetector().OnBar(bar, session);
            AssertSignalPresent(results, "EXH-06", -1, 0.83, 0.87, "ASK FADE at high");
        }

        [Test]
        public void Exh06_FixtureJson_IsValid()
        {
            string path = Path.Combine(FixtureDir, "exh-06-bid-ask-fade.json");
            Assert.That(File.Exists(path), Is.True, "exh-06-bid-ask-fade.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -----------------------------------------------------------------------
        // Helpers
        // -----------------------------------------------------------------------

        private static void AssertSignalPresent(
            SignalResult[] results, string signalId, int direction,
            double strengthMin, double strengthMax, string detailContains)
        {
            SignalResult found = null;
            foreach (var r in results)
            {
                if (r.SignalId == signalId && r.Direction == direction
                    && r.Strength >= strengthMin - 1e-9 && r.Strength <= strengthMax + 1e-9
                    && (detailContains == null || r.Detail.Contains(detailContains)))
                {
                    found = r;
                    break;
                }
            }

            string allResults = "";
            foreach (var r in results)
                allResults += string.Format("\n  [{0} dir={1} str={2:F4}] {3}", r.SignalId, r.Direction, r.Strength, r.Detail);

            Assert.That(found, Is.Not.Null,
                string.Format("Expected signal {0} dir={1} str=[{2:F4},{3:F4}] detail∋'{4}' not found.{5}",
                    signalId, direction, strengthMin, strengthMax, detailContains, allResults));
        }

        private static bool ContainsSignal(SignalResult[] results, string signalId)
        {
            foreach (var r in results)
                if (r.SignalId == signalId) return true;
            return false;
        }
    }
}
