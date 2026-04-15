// DeltaDetectorTests: fixture-driven tests for DeltaDetector.
//
// Covers: DELT-01 rise/drop, DELT-02 tail, DELT-03 reversal, DELT-05 CVD flip, DELT-09 at session min/max.
// Plus: multi-bar sequential test asserting DELT-05 fires only on the sign-change bar.

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

        // -------------------------------------------------------------------
        // DELT-01: Rise classification
        // -------------------------------------------------------------------

        [Test]
        public void Delt01_DeltaRise_FiresPositiveDirection()
        {
            // barDelta=500, totalVol=1000 → direction=+1, strength=0.5
            var bar = new FootprintBar
            {
                BarIndex = 30,
                Open  = 20000.00,
                High  = 20005.00,
                Low   = 19998.00,
                Close = 20003.00,
            };
            bar.Levels[19998.00] = new Cell { AskVol = 100, BidVol = 50  };
            bar.Levels[20000.00] = new Cell { AskVol = 300, BidVol = 200 };
            bar.Levels[20003.00] = new Cell { AskVol = 350, BidVol = 0   };
            bar.Finalize();
            // barDelta = (100-50)+(300-200)+(350-0) = 50+100+350 = 500
            Assert.That(bar.BarDelta, Is.EqualTo(500), "Fixture sanity: barDelta should be 500");
            Assert.That(bar.TotalVol, Is.EqualTo(1000), "Fixture sanity: totalVol should be 1000");

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new DeltaDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult delt01 = null;
            foreach (var r in results) if (r.SignalId == "DELT-01") { delt01 = r; break; }

            Assert.That(delt01, Is.Not.Null, "DELT-01 should fire for positive delta");
            Assert.That(delt01.Direction, Is.EqualTo(+1));
            Assert.That(delt01.Strength,  Is.InRange(0.49, 0.51), "Strength = 500/1000 = 0.5");
            Assert.That(delt01.FlagBit,   Is.EqualTo(SignalFlagBits.Mask(SignalFlagBits.DELT_01)));
        }

        [Test]
        public void Delt01_Fixture_JsonIsValid()
        {
            string path = FixturePath("delt-01-rise-drop.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // DELT-02: Tail at positive extreme
        // -------------------------------------------------------------------

        [Test]
        public void Delt02_TailAtPositiveExtreme_FiresNegativeDirection()
        {
            // barDelta=100, MaxDelta=0 (no AddTrade path) → detector uses delta as extreme,
            // tailRatio=1.0 >= 0.95 → fires DELT-02 direction=-1
            var bar = new FootprintBar
            {
                BarIndex = 31,
                Open  = 20000.00,
                High  = 20005.00,
                Low   = 19998.00,
                Close = 20004.00,
            };
            bar.Levels[19998.00] = new Cell { AskVol = 50,  BidVol = 0  };
            bar.Levels[20000.00] = new Cell { AskVol = 100, BidVol = 50 };
            bar.Finalize();
            // barDelta = (50-0)+(100-50) = 50+50 = 100. MaxDelta=0 (no AddTrade).

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new DeltaDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult delt02 = null;
            foreach (var r in results) if (r.SignalId == "DELT-02") { delt02 = r; break; }

            Assert.That(delt02, Is.Not.Null, "DELT-02 should fire when MaxDelta=0 (trivial extreme, ratio=1.0)");
            Assert.That(delt02.Direction, Is.EqualTo(-1), "Tail at +extreme → bearish direction");
            Assert.That(delt02.FlagBit,   Is.EqualTo(SignalFlagBits.Mask(SignalFlagBits.DELT_02)));
            StringAssert.Contains("TAIL", delt02.Detail);
        }

        [Test]
        public void Delt02_Fixture_JsonIsValid()
        {
            string path = FixturePath("delt-02-tail.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // DELT-03: Reversal — bar UP but delta negative
        // -------------------------------------------------------------------

        [Test]
        public void Delt03_BarUpDeltaNegative_FiresBearishReversal()
        {
            // close=20003 > open=20000 (bullish bar), barDelta=-300 (negative)
            // deltaRatioAbs = 300/1000 = 0.30 > 0.15 → fires DELT-03 direction=-1
            var bar = new FootprintBar
            {
                BarIndex = 32,
                Open  = 20000.00,
                High  = 20005.00,
                Low   = 19997.00,
                Close = 20003.00,
            };
            bar.Levels[19997.00] = new Cell { AskVol = 50,  BidVol = 250 };
            bar.Levels[20000.00] = new Cell { AskVol = 200, BidVol = 350 };
            bar.Levels[20003.00] = new Cell { AskVol = 50,  BidVol = 100 };
            bar.Finalize();
            // barDelta = (50-250)+(200-350)+(50-100) = -200-150-50 = -400? Let me recalc.
            // Actually: 50-250=-200, 200-350=-150, 50-100=-50 → total=-400+100... wait
            // 50-250 = -200
            // 200-350 = -150
            // 50-100 = -50
            // sum = -400. Hmm, but totalVol = 50+250+200+350+50+100 = 1000.
            // deltaRatio = 400/1000 = 0.40 > 0.15. Still fires.
            Assert.That(bar.Close, Is.GreaterThan(bar.Open), "Fixture sanity: bullish bar");
            Assert.That(bar.BarDelta, Is.LessThan(0), "Fixture sanity: negative delta");

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new DeltaDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult delt03 = null;
            foreach (var r in results) if (r.SignalId == "DELT-03") { delt03 = r; break; }

            Assert.That(delt03, Is.Not.Null, "DELT-03 should fire when bar is bullish but delta is negative");
            Assert.That(delt03.Direction, Is.EqualTo(-1), "Bearish hidden reversal → direction=-1");
            Assert.That(delt03.FlagBit,   Is.EqualTo(SignalFlagBits.Mask(SignalFlagBits.DELT_03)));
            StringAssert.Contains("REVERSAL", delt03.Detail);
        }

        [Test]
        public void Delt03_Fixture_JsonIsValid()
        {
            string path = FixturePath("delt-03-reversal.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // DELT-05: CVD flip from positive to negative
        // -------------------------------------------------------------------

        [Test]
        public void Delt05_CvdFlip_PositiveToNegative_FiresBearish()
        {
            // priorCvd=+500, barDelta=-700 → cvd = 500 + (-700) = -200.
            // Sign flip: +500 → -200 → DELT-05 direction=-1.
            var bar = new FootprintBar
            {
                BarIndex = 33,
                Open  = 20003.00,
                High  = 20004.00,
                Low   = 19998.00,
                Close = 19999.00,
            };
            bar.Levels[19998.00] = new Cell { AskVol = 50,  BidVol = 400 };
            bar.Levels[20000.00] = new Cell { AskVol = 100, BidVol = 350 };
            bar.Levels[20003.00] = new Cell { AskVol = 0,   BidVol = 100 };
            bar.Finalize(priorCvd: 500);
            // barDelta = (50-400)+(100-350)+(0-100) = -350-250-100 = -700
            // cvd = 500 + (-700) = -200
            Assert.That(bar.BarDelta, Is.EqualTo(-700), "Fixture sanity: barDelta=-700");
            Assert.That(bar.Cvd,      Is.EqualTo(-200), "Fixture sanity: cvd=-200");

            var session = new SessionContext
            {
                TickSize = 0.25,
                PriorCvd = 500   // positive prior CVD
            };
            var detector = new DeltaDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult delt05 = null;
            foreach (var r in results) if (r.SignalId == "DELT-05") { delt05 = r; break; }

            Assert.That(delt05, Is.Not.Null, "DELT-05 should fire when CVD crosses from positive to negative");
            Assert.That(delt05.Direction, Is.EqualTo(-1), "CVD flip to negative → direction=-1");
            Assert.That(delt05.FlagBit,   Is.EqualTo(SignalFlagBits.Mask(SignalFlagBits.DELT_05)));
            StringAssert.Contains("FLIP", delt05.Detail);
        }

        [Test]
        public void Delt05_Fixture_JsonIsValid()
        {
            string path = FixturePath("delt-05-flip.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // DELT-09: At session maximum
        // -------------------------------------------------------------------

        [Test]
        public void Delt09_AtSessionMax_FiresBearish()
        {
            // sessionMaxDelta=1000, barDelta=980. 980 >= 0.95*1000=950 → DELT-09 direction=-1.
            var bar = new FootprintBar
            {
                BarIndex = 34,
                Open  = 20000.00,
                High  = 20008.00,
                Low   = 19998.00,
                Close = 20007.00,
            };
            bar.Levels[19998.00] = new Cell { AskVol = 10,  BidVol = 0  };
            bar.Levels[20000.00] = new Cell { AskVol = 500, BidVol = 10 };
            bar.Levels[20007.00] = new Cell { AskVol = 480, BidVol = 0  };
            bar.Finalize();
            // barDelta = (10-0)+(500-10)+(480-0) = 10+490+480 = 980
            Assert.That(bar.BarDelta, Is.EqualTo(980), "Fixture sanity: barDelta=980");

            var session = new SessionContext
            {
                TickSize         = 0.25,
                SessionMaxDelta  = 1000,
                SessionMinDelta  = 0,
            };
            var detector = new DeltaDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult delt09 = null;
            foreach (var r in results)
                if (r.SignalId == "DELT-09" && r.Direction == -1) { delt09 = r; break; }

            Assert.That(delt09, Is.Not.Null, "DELT-09 should fire when barDelta >= 95% of session max");
            Assert.That(delt09.Direction, Is.EqualTo(-1), "At session max → bearish warning (-1)");
            Assert.That(delt09.FlagBit,   Is.EqualTo(SignalFlagBits.Mask(SignalFlagBits.DELT_09)));
            StringAssert.Contains("SESSION MAX", delt09.Detail);
        }

        [Test]
        public void Delt09_Fixture_JsonIsValid()
        {
            string path = FixturePath("delt-09-min-max.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // Multi-bar sequential test: DELT-05 fires ONLY on the sign-change bar
        // Feed 3 bars through a shared session:
        //   Bar 1: priorCvd=0, barDelta=+300 → cvd=+300. No flip (prior=0 is excluded by guard).
        //   Bar 2: priorCvd=+300, barDelta=+200 → cvd=+500. No flip (both positive).
        //   Bar 3: priorCvd=+500, barDelta=-800 → cvd=-300. FLIP fires direction=-1.
        // -------------------------------------------------------------------

        [Test]
        public void Delt05_MultiBar_FiresOnlyOnSignChangeBar()
        {
            var detector = new DeltaDetector();
            var session  = new SessionContext { TickSize = 0.25, PriorCvd = 0 };

            // --- Bar 1: positive delta, priorCvd=0 ---
            var bar1 = new FootprintBar
            {
                BarIndex = 40, Open = 20000.00, High = 20003.00, Low = 19999.00, Close = 20002.00
            };
            bar1.Levels[19999.00] = new Cell { AskVol = 200, BidVol = 100 };
            bar1.Levels[20002.00] = new Cell { AskVol = 200, BidVol = 0   };
            bar1.Finalize(priorCvd: 0);
            // barDelta = (200-100)+(200-0) = 100+200 = 300. cvd = 0+300 = +300.

            var r1 = detector.OnBar(bar1, session);

            bool bar1Flip = false;
            foreach (var r in r1) if (r.SignalId == "DELT-05") { bar1Flip = true; break; }
            Assert.That(bar1Flip, Is.False, "DELT-05 should NOT fire on Bar 1 (priorCvd=0 guard)");

            // Advance session: PriorCvd = bar1.Cvd = +300
            session.PriorCvd = bar1.Cvd;

            // --- Bar 2: positive delta, both CVDs positive ---
            var bar2 = new FootprintBar
            {
                BarIndex = 41, Open = 20002.00, High = 20005.00, Low = 20001.00, Close = 20004.00
            };
            bar2.Levels[20001.00] = new Cell { AskVol = 150, BidVol = 100 };
            bar2.Levels[20004.00] = new Cell { AskVol = 150, BidVol = 50  };
            bar2.Finalize(priorCvd: 300);
            // barDelta = (150-100)+(150-50) = 50+100 = 200. cvd = 300+200 = +500.

            var r2 = detector.OnBar(bar2, session);

            bool bar2Flip = false;
            foreach (var r in r2) if (r.SignalId == "DELT-05") { bar2Flip = true; break; }
            Assert.That(bar2Flip, Is.False, "DELT-05 should NOT fire on Bar 2 (both CVDs positive)");

            // Advance session: PriorCvd = bar2.Cvd = +500
            session.PriorCvd = bar2.Cvd;

            // --- Bar 3: large negative delta causes CVD sign flip ---
            var bar3 = new FootprintBar
            {
                BarIndex = 42, Open = 20004.00, High = 20005.00, Low = 19998.00, Close = 19999.00
            };
            bar3.Levels[19998.00] = new Cell { AskVol = 50,  BidVol = 500 };
            bar3.Levels[20000.00] = new Cell { AskVol = 100, BidVol = 450 };
            bar3.Finalize(priorCvd: 500);
            // barDelta = (50-500)+(100-450) = -450-350 = -800. cvd = 500+(-800) = -300.
            Assert.That(bar3.BarDelta, Is.EqualTo(-800), "Bar3 sanity: barDelta=-800");
            Assert.That(bar3.Cvd,      Is.EqualTo(-300), "Bar3 sanity: cvd=-300");

            var r3 = detector.OnBar(bar3, session);

            SignalResult bar3Flip = null;
            foreach (var r in r3) if (r.SignalId == "DELT-05") { bar3Flip = r; break; }
            Assert.That(bar3Flip, Is.Not.Null, "DELT-05 MUST fire on Bar 3 (CVD flipped from +500 to -300)");
            Assert.That(bar3Flip.Direction, Is.EqualTo(-1), "CVD crossed below zero → direction=-1");
        }
    }
}
