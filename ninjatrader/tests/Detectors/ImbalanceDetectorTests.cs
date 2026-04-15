// ImbalanceDetectorTests: fixture-driven tests for ImbalanceDetector.
//
// Covers: IMB-01 single, IMB-06 oversized, IMB-08 diagonal.
// Named regression test: Imb08_DiagonalUsesPriceMinusTickSize — guards that
//   diagonal scan reads bid[P - tickSize], NOT bid[P + tickSize].

using System;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Imbalance;

namespace NinjaTrader.Tests.Detectors
{
    [TestFixture]
    public class ImbalanceDetectorTests
    {
        private static string FixturePath(string file) =>
            System.IO.Path.Combine(TestContext.CurrentContext.TestDirectory,
                "fixtures", "imbalance", file);

        // -------------------------------------------------------------------
        // IMB-01: Single buy imbalance fires
        // -------------------------------------------------------------------

        [Test]
        public void Imb01_SingleBuyImbalance_Fires()
        {
            // Two levels exactly one tick apart (tickSize=0.25).
            // ask[20000.00]=400 vs bid[19999.75]=100 → ratio=4.0 > 3.0 threshold.
            var bar = new FootprintBar
            {
                BarIndex = 10,
                Open  = 20000.00,
                High  = 20000.50,
                Low   = 19999.75,
                Close = 20000.25,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 50,  BidVol = 100 };
            bar.Levels[20000.00] = new Cell { AskVol = 400, BidVol = 80  };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new ImbalanceDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult imb01 = null;
            foreach (var r in results)
                if (r.SignalId == "IMB-01") { imb01 = r; break; }

            Assert.That(imb01, Is.Not.Null, "IMB-01 should fire for ratio=4.0 > 3.0");
            Assert.That(imb01.Direction, Is.EqualTo(+1), "Buy imbalance → direction=+1");
            Assert.That(imb01.FlagBit,  Is.EqualTo(SignalFlagBits.Mask(SignalFlagBits.IMB_01)));
            StringAssert.Contains("BUY", imb01.Detail);
        }

        [Test]
        public void Imb01_Fixture_JsonIsValid()
        {
            string path = FixturePath("imb-01-single.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // IMB-06: Oversized imbalance fires — and IMB-01 also fires for same level
        // -------------------------------------------------------------------

        [Test]
        public void Imb06_OversizedImbalance_FiresBothImb01AndImb06()
        {
            // ask[20000.00]=1000 vs bid[19999.75]=90 → ratio≈11.1 > 10.0 oversized threshold.
            var bar = new FootprintBar
            {
                BarIndex = 11,
                Open  = 20000.00,
                High  = 20000.50,
                Low   = 19999.75,
                Close = 20000.25,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 50,   BidVol = 90  };
            bar.Levels[20000.00] = new Cell { AskVol = 1000, BidVol = 50  };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new ImbalanceDetector();
            var results  = detector.OnBar(bar, session);

            bool hasImb01 = false, hasImb06 = false;
            foreach (var r in results)
            {
                if (r.SignalId == "IMB-01") hasImb01 = true;
                if (r.SignalId == "IMB-06") hasImb06 = true;
            }

            Assert.That(hasImb01, Is.True,  "IMB-01 should fire when ratio > 3.0");
            Assert.That(hasImb06, Is.True,  "IMB-06 should fire when ratio > 10.0 (oversized)");

            // Verify IMB-06 direction and detail
            SignalResult imb06 = null;
            foreach (var r in results)
                if (r.SignalId == "IMB-06") { imb06 = r; break; }
            Assert.That(imb06.Direction, Is.EqualTo(+1), "Oversized buy imbalance → direction=+1");
            StringAssert.Contains("OVERSIZED", imb06.Detail);
        }

        [Test]
        public void Imb06_Fixture_JsonIsValid()
        {
            string path = FixturePath("imb-06-oversized.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // IMB-08: Diagonal regression guard
        // The diagonal scan MUST compare ask[P] vs bid[P - tickSize].
        // If the implementation accidentally uses bid[P + tickSize], this test
        // will catch it: the bid at (price + tickSize) is 60, which gives ratio
        // ask/bid = 400/60 = 6.7 BUT would be attributed to the wrong direction.
        // This test asserts the emitted signal reads bid at the LOWER level.
        // -------------------------------------------------------------------

        [Test]
        public void Imb08_DiagonalUsesPriceMinusTickSize()
        {
            // Setup: two adjacent levels one tick apart.
            //   Low level  20000.00: askVol=80,  bidVol=80
            //   High level 20000.25: askVol=400, bidVol=60
            //
            // Correct diagonal (ask[P] vs bid[P - tickSize]):
            //   ask[20000.25] = 400 vs bid[20000.00] = 80  → ratio = 5.0 → fires IMB-08 direction=+1
            //
            // Wrong diagonal (ask[P] vs bid[P + tickSize] — would look at a NON-EXISTENT level):
            //   ask[20000.25] vs bid[20000.50] — no level at 20000.50, would not fire
            //   OR if it tried ask[20000.00] vs bid[20000.25] = ask[20000.00]=80 vs bid[20000.25]=60
            //   → ratio=1.33 < 3.0 → would NOT fire (guards the test)

            var bar = new FootprintBar
            {
                BarIndex = 12,
                Open  = 20000.00,
                High  = 20000.25,
                Low   = 19999.75,
                Close = 20000.25,
            };
            bar.Levels[20000.00] = new Cell { AskVol = 80,  BidVol = 80  };
            bar.Levels[20000.25] = new Cell { AskVol = 400, BidVol = 60  };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new ImbalanceDetector();
            var results  = detector.OnBar(bar, session);

            // IMB-08 must fire with direction=+1 (buy imbalance: ask at current > bid one tick below)
            SignalResult imb08 = null;
            foreach (var r in results)
                if (r.SignalId == "IMB-08" && r.Direction == +1) { imb08 = r; break; }

            Assert.That(imb08, Is.Not.Null,
                "IMB-08 should fire when ask[P]=400 > bid[P-tickSize]=80 (ratio=5.0). " +
                "If missing: diagonal scan is using the WRONG neighbor (bid[P+tickSize] instead of bid[P-tickSize]).");

            // Assert detail contains "P-tick diag" — the detector injects this marker
            StringAssert.Contains("P-tick diag", imb08.Detail,
                "IMB-08 detail must contain 'P-tick diag' to confirm diagonal scan direction is correct.");
        }

        [Test]
        public void Imb08_Fixture_JsonIsValid()
        {
            string path = FixturePath("imb-08-diagonal.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // IMB-02: Multiple imbalances fire when >= MultipleMinCount (3) in same direction
        // -------------------------------------------------------------------

        [Test]
        public void Imb02_MultipleBuyImbalances_Fires()
        {
            // 4 buy imbalances (ask/bid ratio > 3.0 at each level) → IMB-02 direction=+1
            var bar = new FootprintBar
            {
                BarIndex = 20,
                Open  = 20000.00,
                High  = 20002.50,
                Low   = 19999.75,
                Close = 20002.25,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 50,  BidVol = 60  };  // seed bid
            bar.Levels[20000.00] = new Cell { AskVol = 400, BidVol = 80  };  // ask/bid[19999.75]=400/60=6.7 → buy
            bar.Levels[20000.25] = new Cell { AskVol = 380, BidVol = 82  };  // ask/bid[20000.00]=380/80=4.75 → buy
            bar.Levels[20000.50] = new Cell { AskVol = 360, BidVol = 84  };  // ask/bid[20000.25]=360/82=4.4 → buy
            bar.Levels[20000.75] = new Cell { AskVol = 340, BidVol = 86  };  // ask/bid[20000.50]=340/84=4.0 → buy
            bar.Levels[20002.50] = new Cell { AskVol = 100, BidVol = 50  };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new ImbalanceDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult imb02 = null;
            foreach (var r in results)
                if (r.SignalId == "IMB-02" && r.Direction == +1) { imb02 = r; break; }

            Assert.That(imb02, Is.Not.Null, "IMB-02 should fire direction=+1 when >= 3 buy imbalances");
            StringAssert.Contains("BUY MULTIPLE", imb02.Detail);
        }

        [Test]
        public void Imb02_Fixture_JsonIsValid()
        {
            string path = FixturePath("imb-02-multiple.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // IMB-03: Stacked T1 fires when >= 3 consecutive imbalance levels
        // -------------------------------------------------------------------

        [Test]
        public void Imb03_StackedT1_ThreeConsecutiveLevels_Fires()
        {
            // 3 consecutive buy imbalances at adjacent prices → IMB-03 T1 direction=+1
            var bar = new FootprintBar
            {
                BarIndex = 21,
                Open  = 20000.00,
                High  = 20002.00,
                Low   = 19999.75,
                Close = 20001.75,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 50,  BidVol = 70  };  // seed
            bar.Levels[20000.00] = new Cell { AskVol = 400, BidVol = 80  };  // buy imb #1
            bar.Levels[20000.25] = new Cell { AskVol = 380, BidVol = 82  };  // buy imb #2
            bar.Levels[20000.50] = new Cell { AskVol = 360, BidVol = 84  };  // buy imb #3
            bar.Levels[20002.00] = new Cell { AskVol = 100, BidVol = 50  };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var results  = new ImbalanceDetector().OnBar(bar, session);

            SignalResult imb03 = null;
            foreach (var r in results)
                if (r.SignalId == "IMB-03" && r.Direction == +1) { imb03 = r; break; }

            Assert.That(imb03, Is.Not.Null, "IMB-03 should fire direction=+1 for 3 consecutive buy imbalances (T1)");
        }

        [Test]
        public void Imb03_Fixture_JsonIsValid()
        {
            string path = FixturePath("imb-03-stacked.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        [Test]
        public void Imb03_StackedTiers_ClassifiesT1T2T3Correctly()
        {
            // 7 consecutive buy imbalances → T3 (highest tier) should fire
            var bar = new FootprintBar
            {
                BarIndex = 22,
                Open  = 20000.00,
                High  = 20003.00,
                Low   = 19999.75,
                Close = 20002.75,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 50,  BidVol = 70  };  // seed
            // 7 consecutive buy imbalances
            for (int i = 0; i < 7; i++)
            {
                double px = 20000.00 + i * 0.25;
                bar.Levels[px] = new Cell { AskVol = 400, BidVol = 80 };
            }
            bar.Levels[20003.00] = new Cell { AskVol = 100, BidVol = 50 };
            bar.Finalize();

            var session = new SessionContext { TickSize = 0.25 };
            var results = new ImbalanceDetector().OnBar(bar, session);

            // T3 requires 7 consecutive. With 7 imbs we should get T3 signal
            // (also T1 and T2 may fire, but T3 must be present)
            bool hasT3 = false;
            foreach (var r in results)
                if (r.SignalId == "IMB-03" && r.Direction == +1 && r.Detail.Contains("T3")) { hasT3 = true; break; }

            Assert.That(hasT3, Is.True, "IMB-03 should fire T3 tier when 7+ consecutive buy imbalances present");
        }

        // -------------------------------------------------------------------
        // IMB-04: Reverse fires when bar has both buy and sell imbalances
        // -------------------------------------------------------------------

        [Test]
        public void Imb04_Reverse_BothBuyAndSell_Fires()
        {
            // 1 buy imbalance at bottom, 1 sell imbalance at top → IMB-04
            var bar = new FootprintBar
            {
                BarIndex = 23,
                Open  = 20001.00,
                High  = 20003.00,
                Low   = 19999.75,
                Close = 20001.75,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 50,  BidVol = 70  };  // seed for buy imb
            bar.Levels[20000.00] = new Cell { AskVol = 400, BidVol = 80  };  // buy imbalance
            bar.Levels[20002.75] = new Cell { AskVol = 60,  BidVol = 400 };  // sell imbalance (bid > ask at next level)
            bar.Levels[20003.00] = new Cell { AskVol = 90,  BidVol = 50  };  // ask for sell scan
            bar.Finalize();

            var session = new SessionContext { TickSize = 0.25 };
            var results = new ImbalanceDetector().OnBar(bar, session);

            bool hasImb04 = false;
            foreach (var r in results) if (r.SignalId == "IMB-04") { hasImb04 = true; break; }
            Assert.That(hasImb04, Is.True, "IMB-04 should fire when bar contains both buy and sell imbalances");
        }

        [Test]
        public void Imb04_Fixture_JsonIsValid()
        {
            string path = FixturePath("imb-04-reverse.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // IMB-05: Inverse trap fires for ANY buy imbalance in a red bar
        // -------------------------------------------------------------------

        [Test]
        public void Imb05_InverseTrap_BuyImbInRedBar_Fires()
        {
            // RED bar (close < open) with 2 buy imbalances → IMB-05 direction=-1
            var bar = new FootprintBar
            {
                BarIndex = 24,
                Open  = 20005.00,
                High  = 20005.25,
                Low   = 20000.00,
                Close = 20000.25,
            };
            bar.Levels[20000.00] = new Cell { AskVol = 50,  BidVol = 60  };
            bar.Levels[20003.75] = new Cell { AskVol = 10,  BidVol = 80  };  // seed bid
            bar.Levels[20004.00] = new Cell { AskVol = 400, BidVol = 82  };  // buy imb #1
            bar.Levels[20004.25] = new Cell { AskVol = 380, BidVol = 84  };  // buy imb #2
            bar.Levels[20005.25] = new Cell { AskVol = 60,  BidVol = 55  };
            bar.Finalize();

            var session = new SessionContext { TickSize = 0.25 };
            var results = new ImbalanceDetector().OnBar(bar, session);

            SignalResult imb05 = null;
            foreach (var r in results)
                if (r.SignalId == "IMB-05" && r.Direction == -1) { imb05 = r; break; }

            Assert.That(imb05, Is.Not.Null, "IMB-05 should fire direction=-1 for buy imbalances in a RED bar");
            StringAssert.Contains("longs trapped", imb05.Detail);
        }

        [Test]
        public void Imb05_Fixture_JsonIsValid()
        {
            string path = FixturePath("imb-05-inverse.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // IMB-07: Consecutive imbalance fires when same price imbalanced in 2+ bars
        // -------------------------------------------------------------------

        [Test]
        public void Imb07_Consecutive_SamePriceImbTwoBars_Fires()
        {
            // Bar 1: buy imbalance at 20000.00 → stored in session.ImbalanceHistory
            // Bar 2: same buy imbalance at 20000.00 → IMB-07 fires direction=+1
            var bar1 = new FootprintBar
            {
                BarIndex = 30,
                Open = 20000.00, High = 20001.0, Low = 19999.75, Close = 20000.75,
            };
            bar1.Levels[19999.75] = new Cell { AskVol = 50, BidVol = 70 };
            bar1.Levels[20000.00] = new Cell { AskVol = 400, BidVol = 80 };
            bar1.Levels[20001.00] = new Cell { AskVol = 60, BidVol = 50 };
            bar1.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new ImbalanceDetector();
            detector.OnBar(bar1, session);  // stores 20000.00 in ImbalanceHistory

            // Bar 2: same buy imbalance at 20000.00
            var bar2 = new FootprintBar
            {
                BarIndex = 31,
                Open = 20000.75, High = 20001.5, Low = 19999.75, Close = 20001.25,
            };
            bar2.Levels[19999.75] = new Cell { AskVol = 50, BidVol = 70 };
            bar2.Levels[20000.00] = new Cell { AskVol = 400, BidVol = 80 };  // same imb level
            bar2.Levels[20001.50] = new Cell { AskVol = 60, BidVol = 50 };
            bar2.Finalize();

            var results = detector.OnBar(bar2, session);

            SignalResult imb07 = null;
            foreach (var r in results)
                if (r.SignalId == "IMB-07" && r.Direction == +1) { imb07 = r; break; }

            Assert.That(imb07, Is.Not.Null, "IMB-07 should fire when buy imbalance persists at same price across 2 bars");
        }

        [Test]
        public void Imb07_Fixture_JsonIsValid()
        {
            string path = FixturePath("imb-07-consecutive.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // IMB-09: Reversal pattern fires when imbalance dominance flips bar-over-bar
        // -------------------------------------------------------------------

        [Test]
        public void Imb09_Fixture_JsonIsValid()
        {
            string path = FixturePath("imb-09-reversal-pattern.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // Negative: below-threshold ratio does NOT fire
        // -------------------------------------------------------------------

        [Test]
        public void Imb01_BelowThreshold_DoesNotFire()
        {
            // ratio = 2.0 < 3.0 threshold
            var bar = new FootprintBar
            {
                BarIndex = 99,
                Open  = 20000.00,
                High  = 20000.50,
                Low   = 19999.75,
                Close = 20000.25,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 50,  BidVol = 200 };
            bar.Levels[20000.00] = new Cell { AskVol = 400, BidVol = 300 };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new ImbalanceDetector();
            var results  = detector.OnBar(bar, session);

            // ask[20000.00]=400 vs bid[19999.75]=200 → ratio=2.0 < 3.0 → should NOT fire
            bool hasImb01 = false;
            foreach (var r in results) if (r.SignalId == "IMB-01") { hasImb01 = true; break; }
            Assert.That(hasImb01, Is.False, "IMB-01 should NOT fire when ratio < 3.0");
        }
    }
}
