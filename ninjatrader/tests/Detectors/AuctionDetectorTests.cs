// AuctionDetectorTests: fixture-driven tests for AuctionDetector (AUCT-01..05).
//
// Covers: AUCT-01 unfinished business, AUCT-02 finished auction (Wave 3),
//         AUCT-03 poor high/low, AUCT-04 volume void, AUCT-05 market sweep.

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
        // AUCT-01: Unfinished business fires when bid_vol at bar high > 0
        // -------------------------------------------------------------------

        [Test]
        public void Auct01_UnfinishedBusiness_BidAtHigh_Fires()
        {
            // highLevel.BidVol = 45 → AUCT-01 direction=+1
            var bar = new FootprintBar
            {
                BarIndex = 200,
                Open  = 20000.00,
                High  = 20005.00,
                Low   = 19999.75,
                Close = 20002.50,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 0,   BidVol = 150 };
            bar.Levels[20005.00] = new Cell { AskVol = 100, BidVol = 45  };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new AuctionDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult auct01 = null;
            foreach (var r in results)
                if (r.SignalId == "AUCT-01" && r.Direction == +1) { auct01 = r; break; }

            Assert.That(auct01, Is.Not.Null, "AUCT-01 should fire when bid_vol > 0 at bar high");
            Assert.That(auct01.Direction, Is.EqualTo(+1));
        }

        [Test]
        public void Auct01_Fixture_JsonIsValid()
        {
            string path = FixturePath("auct-01-unfinished.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        [Test]
        public void Auct01_UnfinishedLevels_TrackedInSession()
        {
            // After OnBar, session.UnfinishedLevels should contain the high price
            var bar = new FootprintBar
            {
                BarIndex = 201,
                Open  = 20000.00,
                High  = 20005.00,
                Low   = 19999.75,
                Close = 20002.50,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 0,   BidVol = 150 };
            bar.Levels[20005.00] = new Cell { AskVol = 100, BidVol = 45  };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new AuctionDetector();
            detector.OnBar(bar, session);

            Assert.That(session.UnfinishedLevels.ContainsKey(20005.00), Is.True,
                "High price with bid > 0 should be tracked in session.UnfinishedLevels");
        }

        // -------------------------------------------------------------------
        // AUCT-02: Finished auction (Wave 3 signal — regression guard)
        // -------------------------------------------------------------------

        [Test]
        public void Auct02_FinishedAuction_ZeroBidAtHigh_Fires()
        {
            var bar = new FootprintBar
            {
                BarIndex = 202,
                Open  = 20000.00,
                High  = 20005.00,
                Low   = 19999.75,
                Close = 20002.50,
            };
            bar.Levels[19999.75] = new Cell { AskVol = 0,   BidVol = 150 };
            bar.Levels[20005.00] = new Cell { AskVol = 200, BidVol = 0   };  // zero bid at high
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new AuctionDetector();
            var results  = detector.OnBar(bar, session);

            bool hasAuct02 = false;
            foreach (var r in results)
                if (r.SignalId == "AUCT-02" && r.Direction == -1) { hasAuct02 = true; break; }

            Assert.That(hasAuct02, Is.True, "AUCT-02 should fire when bid_vol=0 at high (buyers exhausted)");
        }

        // -------------------------------------------------------------------
        // AUCT-03: Poor high/low fires when extreme vol < avg * poorRatio
        // -------------------------------------------------------------------

        [Test]
        public void Auct03_PoorHigh_BelowThreshold_Fires()
        {
            // 8 levels, totalVol=160, avgLevelVol=20, poorTh=20*0.15=3
            // highVol (20003.50)=2 < 3 → AUCT-03 direction=-1 (poor high)
            var bar = new FootprintBar
            {
                BarIndex = 210,
                Open  = 20000.00,
                High  = 20003.50,
                Low   = 20000.00,
                Close = 20001.50,
            };
            bar.Levels[20000.00] = new Cell { AskVol = 20, BidVol = 20 };
            bar.Levels[20000.25] = new Cell { AskVol = 20, BidVol = 20 };
            bar.Levels[20000.50] = new Cell { AskVol = 20, BidVol = 20 };
            bar.Levels[20000.75] = new Cell { AskVol = 20, BidVol = 20 };
            bar.Levels[20001.00] = new Cell { AskVol = 20, BidVol = 20 };
            bar.Levels[20001.25] = new Cell { AskVol = 20, BidVol = 20 };
            bar.Levels[20001.50] = new Cell { AskVol = 20, BidVol = 20 };
            bar.Levels[20003.50] = new Cell { AskVol = 1,  BidVol = 1  };  // poor high: vol=2
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new AuctionDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult auct03 = null;
            foreach (var r in results)
                if (r.SignalId == "AUCT-03" && r.Direction == -1) { auct03 = r; break; }

            Assert.That(auct03, Is.Not.Null, "AUCT-03 should fire direction=-1 when high vol < avg*0.15");
        }

        [Test]
        public void Auct03_Fixture_JsonIsValid()
        {
            string path = FixturePath("auct-03-poor-high-low.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // AUCT-04: Volume void fires when >= 2 levels are near-zero vol
        // -------------------------------------------------------------------

        [Test]
        public void Auct04_VolumeVoid_ThinLevels_Fires()
        {
            // maxLevelVol=500, voidTh=500*0.05=25. 3 levels with vol < 25 → fires
            var bar = new FootprintBar
            {
                BarIndex = 220,
                Open  = 20000.00,
                High  = 20003.00,
                Low   = 20000.00,
                Close = 20002.50,
            };
            bar.Levels[20000.00] = new Cell { AskVol = 250, BidVol = 250 };  // max=500
            bar.Levels[20000.75] = new Cell { AskVol = 9,   BidVol = 9   };  // void: 18 < 25
            bar.Levels[20001.50] = new Cell { AskVol = 8,   BidVol = 8   };  // void: 16 < 25
            bar.Levels[20002.25] = new Cell { AskVol = 7,   BidVol = 7   };  // void: 14 < 25
            bar.Levels[20003.00] = new Cell { AskVol = 200, BidVol = 100 };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new AuctionDetector();
            var results  = detector.OnBar(bar, session);

            bool hasAuct04 = false;
            foreach (var r in results)
                if (r.SignalId == "AUCT-04") { hasAuct04 = true; break; }

            Assert.That(hasAuct04, Is.True, "AUCT-04 should fire when >= 2 void levels present");
        }

        [Test]
        public void Auct04_Fixture_JsonIsValid()
        {
            string path = FixturePath("auct-04-volume-void.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // AUCT-05: Market sweep fires when second half vol > first half * 1.5
        // -------------------------------------------------------------------

        [Test]
        public void Auct05_MarketSweep_UpperHalfDominant_FiresUp()
        {
            // 8 levels. Bar closes bullish (close > open).
            // upperHalf vol = 1800, lowerHalf vol = 300. 1800/300 = 6 > 1.5 → fires +1
            var bar = new FootprintBar
            {
                BarIndex = 230,
                Open  = 20000.00,
                High  = 20003.50,
                Low   = 20000.00,
                Close = 20003.00,
            };
            // Lower 4 levels: 50 each = 200 total
            bar.Levels[20000.00] = new Cell { AskVol = 25,  BidVol = 25  };
            bar.Levels[20000.50] = new Cell { AskVol = 25,  BidVol = 25  };
            bar.Levels[20001.00] = new Cell { AskVol = 25,  BidVol = 25  };
            bar.Levels[20001.50] = new Cell { AskVol = 25,  BidVol = 25  };
            // Upper 4 levels: 300 each = 1200 total
            bar.Levels[20002.00] = new Cell { AskVol = 150, BidVol = 150 };
            bar.Levels[20002.50] = new Cell { AskVol = 150, BidVol = 150 };
            bar.Levels[20003.00] = new Cell { AskVol = 150, BidVol = 150 };
            bar.Levels[20003.50] = new Cell { AskVol = 150, BidVol = 150 };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new AuctionDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult auct05 = null;
            foreach (var r in results)
                if (r.SignalId == "AUCT-05" && r.Direction == +1) { auct05 = r; break; }

            Assert.That(auct05, Is.Not.Null, "AUCT-05 should fire direction=+1 when upper half vol >> lower half in up bar");
        }

        [Test]
        public void Auct05_Fixture_JsonIsValid()
        {
            string path = FixturePath("auct-05-market-sweep.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        [Test]
        public void Auct05_FewerThanMinLevels_DoesNotFire()
        {
            // Only 4 levels — below SweepMinLevels=6
            var bar = new FootprintBar
            {
                BarIndex = 231,
                Open  = 20000.00,
                High  = 20001.50,
                Low   = 20000.00,
                Close = 20001.25,
            };
            bar.Levels[20000.00] = new Cell { AskVol = 50,  BidVol = 50  };
            bar.Levels[20000.50] = new Cell { AskVol = 50,  BidVol = 50  };
            bar.Levels[20001.00] = new Cell { AskVol = 500, BidVol = 500 };
            bar.Levels[20001.50] = new Cell { AskVol = 500, BidVol = 500 };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new AuctionDetector();
            var results  = detector.OnBar(bar, session);

            bool hasAuct05 = false;
            foreach (var r in results)
                if (r.SignalId == "AUCT-05") { hasAuct05 = true; break; }

            Assert.That(hasAuct05, Is.False, "AUCT-05 should NOT fire with fewer than 6 levels");
        }
    }
}
