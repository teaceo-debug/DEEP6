// VolPatternDetectorTests: fixture-driven tests for VolPatternDetector.
//
// Covers: VOLP-02 volume bubble, VOLP-03 volume surge, VOLP-06 big delta per level.

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

        // -------------------------------------------------------------------
        // VOLP-02: Volume bubble
        // -------------------------------------------------------------------

        [Test]
        public void Volp02_VolumeBubble_Fires()
        {
            // Level at 20005.00 has vol=800. avgLevelVol=1050/6=175, threshold=175*4=700. 800>700.
            // Net at 20005 = 500-300 = 200 > 0 → direction=+1.
            var bar = new FootprintBar
            {
                BarIndex = 50,
                Open  = 20003.00,
                High  = 20006.00,
                Low   = 20002.00,
                Close = 20004.00,
            };
            bar.Levels[20002.00] = new Cell { AskVol = 30,  BidVol = 20  };
            bar.Levels[20003.00] = new Cell { AskVol = 70,  BidVol = 30  };
            bar.Levels[20004.75] = new Cell { AskVol = 30,  BidVol = 20  };
            bar.Levels[20005.00] = new Cell { AskVol = 500, BidVol = 300 };
            bar.Levels[20005.25] = new Cell { AskVol = 30,  BidVol = 20  };
            bar.Levels[20006.00] = new Cell { AskVol = 0,   BidVol = 0   };
            bar.Finalize();
            // totalVol = 30+20+70+30+30+20+500+300+30+20+0+0 = 1050
            // avgLevelVol = 1050/6 = 175  (6 levels including the zero-vol one)
            // threshold = 175 * 4.0 = 700
            // level 20005: vol = 500+300 = 800 > 700 → bubble

            var session = new SessionContext { VolEma20 = 300.0, TickSize = 0.25 };
            var detector = new VolPatternDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult volp02 = null;
            foreach (var r in results) if (r.SignalId == "VOLP-02") { volp02 = r; break; }

            Assert.That(volp02, Is.Not.Null, "VOLP-02 should fire when a level exceeds bubble_mult * avg_level_vol");
            Assert.That(volp02.Direction, Is.EqualTo(+1), "Ask dominant level → direction=+1");
            Assert.That(volp02.FlagBit,   Is.EqualTo(SignalFlagBits.Mask(SignalFlagBits.VOLP_02)));
            StringAssert.Contains("VOL BUBBLE", volp02.Detail);
        }

        [Test]
        public void Volp02_Fixture_JsonIsValid()
        {
            string path = FixturePath("volp-02-bubble.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // VOLP-03: Volume surge
        // -------------------------------------------------------------------

        [Test]
        public void Volp03_VolumeSurge_Fires()
        {
            // volEma20=300, surgeThreshold=300*3=900. totalVol=1000 > 900.
            // barDelta=0 → deltaRatio=0 < 0.20 → direction=0.
            var bar = new FootprintBar
            {
                BarIndex = 51,
                Open  = 20000.00,
                High  = 20004.00,
                Low   = 19997.00,
                Close = 20001.00,
            };
            bar.Levels[19997.00] = new Cell { AskVol = 200, BidVol = 200 };
            bar.Levels[20000.00] = new Cell { AskVol = 250, BidVol = 250 };
            bar.Levels[20001.00] = new Cell { AskVol = 50,  BidVol = 50  };
            bar.Finalize();
            Assert.That(bar.TotalVol, Is.EqualTo(1000), "Fixture sanity: totalVol=1000");
            Assert.That(bar.BarDelta, Is.EqualTo(0),    "Fixture sanity: barDelta=0");

            var session  = new SessionContext { VolEma20 = 300.0, TickSize = 0.25 };
            var detector = new VolPatternDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult volp03 = null;
            foreach (var r in results) if (r.SignalId == "VOLP-03") { volp03 = r; break; }

            Assert.That(volp03, Is.Not.Null, "VOLP-03 should fire when totalVol > surge_mult * vol_ema");
            Assert.That(volp03.Direction, Is.EqualTo(0), "Balanced delta → direction=0 (context signal)");
            Assert.That(volp03.FlagBit,   Is.EqualTo(SignalFlagBits.Mask(SignalFlagBits.VOLP_03)));
            StringAssert.Contains("VOL SURGE", volp03.Detail);
        }

        [Test]
        public void Volp03_BelowSurgeThreshold_DoesNotFire()
        {
            // volEma20=300, surgeThreshold=900. totalVol=500 < 900 → should NOT fire.
            var bar = new FootprintBar
            {
                BarIndex = 99,
                Open = 20000.00, High = 20002.00, Low = 19999.00, Close = 20001.00
            };
            bar.Levels[19999.00] = new Cell { AskVol = 125, BidVol = 125 };
            bar.Levels[20001.00] = new Cell { AskVol = 125, BidVol = 125 };
            bar.Finalize();

            var session  = new SessionContext { VolEma20 = 300.0, TickSize = 0.25 };
            var detector = new VolPatternDetector();
            var results  = detector.OnBar(bar, session);

            bool hasVolp03 = false;
            foreach (var r in results) if (r.SignalId == "VOLP-03") { hasVolp03 = true; break; }
            Assert.That(hasVolp03, Is.False, "VOLP-03 should NOT fire when totalVol < surgeThreshold");
        }

        [Test]
        public void Volp03_Fixture_JsonIsValid()
        {
            string path = FixturePath("volp-03-surge.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -------------------------------------------------------------------
        // VOLP-06: Big delta per level
        // -------------------------------------------------------------------

        [Test]
        public void Volp06_BigDeltaPerLevel_Fires()
        {
            // Level at 20002.00: askVol=450, bidVol=50 → net_delta=400. 400 >= threshold=80 → fires.
            var bar = new FootprintBar
            {
                BarIndex = 52,
                Open  = 20000.00,
                High  = 20004.00,
                Low   = 19999.00,
                Close = 20003.00,
            };
            bar.Levels[19999.00] = new Cell { AskVol = 50,  BidVol = 0   };
            bar.Levels[20002.00] = new Cell { AskVol = 450, BidVol = 50  };
            bar.Levels[20003.00] = new Cell { AskVol = 50,  BidVol = 400 };
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new VolPatternDetector();
            var results  = detector.OnBar(bar, session);

            SignalResult volp06 = null;
            foreach (var r in results) if (r.SignalId == "VOLP-06") { volp06 = r; break; }

            Assert.That(volp06, Is.Not.Null, "VOLP-06 should fire when |net_delta| >= big_delta_level_threshold");
            Assert.That(volp06.Direction, Is.EqualTo(+1), "Ask-dominant level → direction=+1");
            Assert.That(volp06.FlagBit,   Is.EqualTo(SignalFlagBits.Mask(SignalFlagBits.VOLP_06)));
            StringAssert.Contains("BIG DELTA", volp06.Detail);
        }

        [Test]
        public void Volp06_BelowThreshold_DoesNotFire()
        {
            // All levels have |net_delta| < 80 threshold — VOLP-06 should NOT fire.
            var bar = new FootprintBar
            {
                BarIndex = 98,
                Open = 20000.00, High = 20002.00, Low = 19998.00, Close = 20001.00
            };
            bar.Levels[19998.00] = new Cell { AskVol = 50,  BidVol = 10  };  // net=40 < 80
            bar.Levels[20000.00] = new Cell { AskVol = 100, BidVol = 60  };  // net=40 < 80
            bar.Levels[20001.00] = new Cell { AskVol = 30,  BidVol = 50  };  // |net|=20 < 80
            bar.Finalize();

            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new VolPatternDetector();
            var results  = detector.OnBar(bar, session);

            bool hasVolp06 = false;
            foreach (var r in results) if (r.SignalId == "VOLP-06") { hasVolp06 = true; break; }
            Assert.That(hasVolp06, Is.False, "VOLP-06 should NOT fire when |net_delta| < threshold");
        }

        [Test]
        public void Volp06_Fixture_JsonIsValid()
        {
            string path = FixturePath("volp-06-big-delta-per-level.json");
            Assert.That(File.Exists(path), Is.True, $"Fixture not found: {path}");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }
    }
}
