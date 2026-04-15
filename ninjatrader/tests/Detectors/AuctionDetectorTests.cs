// AuctionDetectorTests: fixture-driven tests for AuctionDetector.
//
// Covers: AUCT-02 finished auction (zero bid at high = bearish; zero ask at low = bullish).

using System;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Auction;

namespace NinjaTrader.Tests.Detectors
{
    [TestFixture]
    public class AuctionDetectorTests
    {
        private static string FixturePath(string file) =>
            System.IO.Path.Combine(TestContext.CurrentContext.TestDirectory,
                "fixtures", "auction", file);

        // -------------------------------------------------------------------
        // AUCT-02: Finished auction at bar high — bearish
        // -------------------------------------------------------------------

        [Test]
        public void Auct02_FinishedAuction_ZeroBidAtHigh_FiresBearish()
        {
            // Level at bar high (20010.00): bidVol=0, askVol=200 → direction=-1
            var bar = new FootprintBar
            {
                BarIndex = 20,
                Open  = 20005.00,
                High  = 20010.00,
                Low   = 20003.00,
                Close = 20006.00,
            };
            bar.Levels[20003.00] = new Cell { AskVol = 50,  BidVol = 50  };
            bar.Levels[20005.00] = new Cell { AskVol = 200, BidVol = 150 };
            bar.Levels[20006.00] = new Cell { AskVol = 180, BidVol = 120 };
            bar.Levels[20010.00] = new Cell { AskVol = 200, BidVol = 0   };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new AuctionDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult auct02 = null;
            foreach (var r in results)
                if (r.SignalId == "AUCT-02" && r.Direction == -1) { auct02 = r; break; }

            Assert.That(auct02, Is.Not.Null, "AUCT-02 should fire direction=-1 when bidVol=0 at high");
            Assert.That(auct02.Direction, Is.EqualTo(-1), "Zero bid at bar high → bearish (-1)");
            Assert.That(auct02.Strength,  Is.EqualTo(1.0), "Finished auction strength=1.0");
            Assert.That(auct02.FlagBit,   Is.EqualTo(SignalFlagBits.Mask(SignalFlagBits.AUCT_02)));
            StringAssert.Contains("FINISHED AUCTION", auct02.Detail);
        }

        [Test]
        public void Auct02_Fixture_JsonIsValid()
        {
            string path = FixturePath("auct-02-finished.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // AUCT-02: Finished auction at bar low — bullish
        // -------------------------------------------------------------------

        [Test]
        public void Auct02_FinishedAuction_ZeroAskAtLow_FiresBullish()
        {
            // Level at bar low (19995.00): askVol=0, bidVol=150 → direction=+1
            var bar = new FootprintBar
            {
                BarIndex = 21,
                Open  = 20000.00,
                High  = 20005.00,
                Low   = 19995.00,
                Close = 20001.00,
            };
            bar.Levels[19995.00] = new Cell { AskVol = 0,   BidVol = 150 };
            bar.Levels[20000.00] = new Cell { AskVol = 200, BidVol = 180 };
            bar.Levels[20005.00] = new Cell { AskVol = 100, BidVol = 90  };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new AuctionDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult auct02 = null;
            foreach (var r in results)
                if (r.SignalId == "AUCT-02" && r.Direction == +1) { auct02 = r; break; }

            Assert.That(auct02, Is.Not.Null, "AUCT-02 should fire direction=+1 when askVol=0 at low");
            Assert.That(auct02.Direction, Is.EqualTo(+1), "Zero ask at bar low → bullish (+1)");
            Assert.That(auct02.Strength,  Is.EqualTo(1.0));
            StringAssert.Contains("FINISHED AUCTION", auct02.Detail);
        }

        // -------------------------------------------------------------------
        // Negative: non-zero bid at high — AUCT-02 should NOT fire
        // -------------------------------------------------------------------

        [Test]
        public void Auct02_NonZeroBidAtHigh_DoesNotFire()
        {
            var bar = new FootprintBar
            {
                BarIndex = 22,
                Open  = 20000.00,
                High  = 20005.00,
                Low   = 19998.00,
                Close = 20002.00,
            };
            bar.Levels[19998.00] = new Cell { AskVol = 20,  BidVol = 20  };
            bar.Levels[20000.00] = new Cell { AskVol = 200, BidVol = 150 };
            bar.Levels[20005.00] = new Cell { AskVol = 80,  BidVol = 50  }; // bidVol > 0 at high
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new AuctionDetector();
            var results  = detector.OnBar(bar, session);

            bool hasAuct02Bearish = false;
            foreach (var r in results)
                if (r.SignalId == "AUCT-02" && r.Direction == -1) { hasAuct02Bearish = true; break; }

            Assert.That(hasAuct02Bearish, Is.False,
                "AUCT-02 bearish should NOT fire when bidVol > 0 at bar high");
        }
    }
}
