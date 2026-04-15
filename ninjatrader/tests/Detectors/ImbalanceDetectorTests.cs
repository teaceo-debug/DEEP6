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
