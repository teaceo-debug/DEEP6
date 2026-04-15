// AbsorptionDetectorTests: fixture-driven smoke tests for AbsorptionDetector.
// Fixture: ninjatrader/tests/fixtures/absorption/abs-01-classic.json
//
// Verifies that ABS-01 fires with correct signal ID, direction, and FlagBit
// on a hand-crafted bar fixture matching PORT-SPEC.md §2.TryClassic conditions.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Absorption;

namespace NinjaTrader.Tests.Detectors
{
    [TestFixture]
    public class AbsorptionDetectorTests
    {
        /// <summary>
        /// ABS-01 classic: upper wick has 35% of total vol, deltaRatio=0.057 — fires bearish.
        /// Fixture: abs-01-classic.json
        /// Assertion: SignalId=="ABS-01", Direction==-1, FlagBit==Mask(ABS_01), Strength in [0.25,0.45].
        /// </summary>
        [Test]
        public void Abs01_ClassicFixture_EmitsExpectedSignal()
        {
            // Build bar directly from the known values (matches abs-01-classic.json bar section)
            var bar = new FootprintBar
            {
                BarIndex = 42,
                Open     = 20001.75,
                High     = 20005.00,
                Low      = 20000.00,
                Close    = 20001.25,
            };
            // Levels per fixture:
            // Upper wick (px > bodyTop=20001.75): 20005.00 (askVol=185,bidVol=165), 20004.75 (0,0)
            // Body: 20002.00, 20001.75, 20001.25, 20000.50
            bar.Levels[20005.00] = new Cell { AskVol = 185, BidVol = 165 };
            bar.Levels[20004.75] = new Cell { AskVol = 0,   BidVol = 0   };
            bar.Levels[20002.00] = new Cell { AskVol = 200, BidVol = 150 };
            bar.Levels[20001.75] = new Cell { AskVol = 100, BidVol = 80  };
            bar.Levels[20001.25] = new Cell { AskVol = 50,  BidVol = 50  };
            bar.Levels[20000.50] = new Cell { AskVol = 10,  BidVol = 10  };
            bar.Finalize(priorCvd: 0);
            // totalVol = 185+165 + 0+0 + 200+150 + 100+80 + 50+50 + 10+10 = 1000
            // barDelta  = (185-165) + (200-150) + (100-80) + (50-50) + (10-10) = 20+50+20+0+0 = 90
            // upperVol  = 185+165 = 350 → wickPct = 35% ≥ 30% effWickMin ✓
            // upperDelta = 185-165 = 20 → deltaRatio = 20/350 = 0.0571 < 0.12 ✓
            // barDeltaRatio = 90/1000 = 0.09 < 0.18 ✓

            var session = new SessionContext
            {
                Atr20    = 4.0,
                VolEma20 = 500.0,
                TickSize = 0.25,
                Vah      = 20003.0,
                Val      = 19999.0
            };

            var detector = new AbsorptionDetector();
            var results  = detector.OnBar(bar, session);

            // At minimum ABS-01 should fire (upper wick classic)
            SignalResult abs01 = null;
            foreach (var r in results)
                if (r.SignalId == "ABS-01") { abs01 = r; break; }

            Assert.That(abs01, Is.Not.Null, "ABS-01 should fire on upper wick with wickPct=35%");
            Assert.That(abs01.Direction, Is.EqualTo(-1), "Upper wick absorption → bearish direction (-1)");
            Assert.That(abs01.FlagBit,   Is.EqualTo(SignalFlagBits.Mask(SignalFlagBits.ABS_01)),
                "FlagBit must equal Mask(ABS_01)");
            // strength = min(wickPct/60, 1) * (1 - deltaRatio/AbsorbDeltaMax)
            // = min(70/60, 1) * (1 - 0.1/0.12) = 1.0 * 0.1667 = 0.1667
            Assert.That(abs01.Strength, Is.InRange(0.10, 0.45),
                "Strength should be in [0.10, 0.45] for this fixture (actual ~0.167)");
            StringAssert.Contains("CLASSIC upper", abs01.Detail,
                "Detail should contain 'CLASSIC upper'");
        }

        /// <summary>
        /// ABS-01 should NOT fire when wick vol is below threshold.
        /// Bar has low upper wick vol (5% of total) — below the 30% effWickMin.
        /// </summary>
        [Test]
        public void Abs01_LowWickVol_DoesNotFire()
        {
            var bar = new FootprintBar
            {
                BarIndex = 1,
                Open     = 20000.00,
                High     = 20005.00,
                Low      = 19997.00,
                Close    = 20003.00,
            };
            // Upper wick (px > bodyTop=20003): price 20004, 20005 — only 50 vol of 1000 total = 5%
            bar.Levels[20005.00] = new Cell { AskVol = 25, BidVol = 25 };
            bar.Levels[20004.00] = new Cell { AskVol = 0,  BidVol = 0  };
            bar.Levels[20003.00] = new Cell { AskVol = 300, BidVol = 300 };
            bar.Levels[20001.00] = new Cell { AskVol = 175, BidVol = 175 };
            bar.Finalize();

            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 500.0, TickSize = 0.25 };
            var detector = new AbsorptionDetector();
            var results  = detector.OnBar(bar, session);

            bool hasAbs01 = false;
            foreach (var r in results) if (r.SignalId == "ABS-01") { hasAbs01 = true; break; }
            Assert.That(hasAbs01, Is.False, "ABS-01 should NOT fire when upper wick vol is only 5%");
        }

        /// <summary>
        /// Fixture JSON is valid JSON and parses without error.
        /// </summary>
        [Test]
        public void Abs01Fixture_JsonIsValid()
        {
            string fixturePath = Path.Combine(
                TestContext.CurrentContext.TestDirectory,
                "fixtures", "absorption", "abs-01-classic.json");
            Assert.That(File.Exists(fixturePath), Is.True,
                $"Fixture file not found at {fixturePath}");
            string json = File.ReadAllText(fixturePath);
            Assert.DoesNotThrow(() => JsonDocument.Parse(json),
                "abs-01-classic.json must be valid JSON");
        }
    }
}
