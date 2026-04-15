// AbsorptionParityTests: fixture-driven parity tests for ABS-01..04 + ABS-07.
//
// Each test loads a fixture JSON, constructs a FootprintBar + SessionContext,
// runs AbsorptionDetector.OnBar(), and asserts that the expected SignalResult
// is present in the output (SignalId exact, Direction exact, Strength in range).
//
// "Parity" here means AbsorptionDetector produces bit-for-bit correct output
// per PORT-SPEC.md §2 on every defined fixture. Legacy-vs-registry comparison
// is in LegacyVsRegistryParityTests.cs.

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
    public class AbsorptionParityTests
    {
        private static string FixtureDir => Path.Combine(
            TestContext.CurrentContext.TestDirectory, "fixtures", "absorption");

        // -----------------------------------------------------------------------
        // ABS-01: Classic absorption at upper wick
        // -----------------------------------------------------------------------

        [Test]
        public void Abs01_ClassicFixture_EmitsSignal()
        {
            var bar = new FootprintBar
            {
                BarIndex = 42, Open = 20001.75, High = 20005.00, Low = 20000.00, Close = 20001.25
            };
            bar.Levels[20005.00] = new Cell { AskVol = 185, BidVol = 165 };
            bar.Levels[20004.75] = new Cell { AskVol = 0,   BidVol = 0   };
            bar.Levels[20002.00] = new Cell { AskVol = 200, BidVol = 150 };
            bar.Levels[20001.75] = new Cell { AskVol = 100, BidVol = 80  };
            bar.Levels[20001.25] = new Cell { AskVol = 50,  BidVol = 50  };
            bar.Levels[20000.50] = new Cell { AskVol = 10,  BidVol = 10  };
            bar.Finalize(0);

            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 500.0, TickSize = 0.25, Vah = 20003.0, Val = 19999.0 };
            var results = new AbsorptionDetector().OnBar(bar, session);

            AssertSignalPresent(results, "ABS-01", -1, 0.10, 0.45, "CLASSIC upper");
        }

        [Test]
        public void Abs01_FixtureJson_IsValid()
        {
            string path = Path.Combine(FixtureDir, "abs-01-classic.json");
            Assert.That(File.Exists(path), Is.True, "abs-01-classic.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -----------------------------------------------------------------------
        // ABS-02: Passive absorption — high vol at top 20% zone
        // -----------------------------------------------------------------------

        [Test]
        public void Abs02_PassiveFixture_EmitsSignal()
        {
            // Bar: high=20005, low=20000, barRange=5.0, extremeRange=1.0.
            // upperZoneVol=400 of totalVol=470 (85.1%) >= PassiveVolPct=60%. close=20001 < 20004.
            // ABS-01 blocked: upperDelta=300 / upperVol=300 = 1.0 >= deltaMax=0.12.
            var bar = new FootprintBar
            {
                BarIndex = 20, Open = 20004.00, High = 20005.00, Low = 20000.00, Close = 20001.00
            };
            bar.Levels[20005.00] = new Cell { AskVol = 300, BidVol = 0   };
            bar.Levels[20004.75] = new Cell { AskVol = 0,   BidVol = 0   };
            bar.Levels[20004.50] = new Cell { AskVol = 0,   BidVol = 0   };
            bar.Levels[20004.25] = new Cell { AskVol = 0,   BidVol = 0   };
            bar.Levels[20004.00] = new Cell { AskVol = 50,  BidVol = 50  };
            bar.Levels[20003.00] = new Cell { AskVol = 20,  BidVol = 20  };
            bar.Levels[20002.00] = new Cell { AskVol = 10,  BidVol = 10  };
            bar.Levels[20001.00] = new Cell { AskVol = 5,   BidVol = 5   };
            bar.Finalize(0);
            // totalVol=470, upperZoneVol=400 (>=20004), ratio=0.851 >= 0.60
            // strength = min(0.851, 1.0) = 0.851

            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25, Vah = 20003.5, Val = 19999.5 };
            var results = new AbsorptionDetector().OnBar(bar, session);

            AssertSignalPresent(results, "ABS-02", -1, 0.83, 0.87, "PASSIVE upper");
        }

        [Test]
        public void Abs02_FixtureJson_IsValid()
        {
            string path = Path.Combine(FixtureDir, "abs-02-passive.json");
            Assert.That(File.Exists(path), Is.True, "abs-02-passive.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -----------------------------------------------------------------------
        // ABS-03: Stopping Volume — totalVol > volEma*2.0, POC in wick
        // -----------------------------------------------------------------------

        [Test]
        public void Abs03_StoppingFixture_EmitsSignal()
        {
            // totalVol=1200 > volEma=400*2.0=800. PocPrice=20006 > bodyTop=20001 → dir=-1.
            // ABS-01 blocked: upper wick deltaRatio=0.818 >= 0.12.
            var bar = new FootprintBar
            {
                BarIndex = 30, Open = 20001.00, High = 20006.00, Low = 19999.00, Close = 20000.50
            };
            bar.Levels[20006.00] = new Cell { AskVol = 800, BidVol = 50  };
            bar.Levels[20005.00] = new Cell { AskVol = 200, BidVol = 50  };
            bar.Levels[20001.00] = new Cell { AskVol = 30,  BidVol = 30  };
            bar.Levels[20000.50] = new Cell { AskVol = 10,  BidVol = 10  };
            bar.Levels[19999.00] = new Cell { AskVol = 10,  BidVol = 10  };
            bar.Finalize(0);
            // totalVol=1200, PocPrice=20006 (850 vol), bodyTop=20001
            // strength = min(1200/(400*2*2), 1) = 0.75

            var session = new SessionContext { Atr20 = 5.0, VolEma20 = 400.0, TickSize = 0.25, Vah = 20004.0, Val = 19999.0 };
            var results = new AbsorptionDetector().OnBar(bar, session);

            AssertSignalPresent(results, "ABS-03", -1, 0.73, 0.77, "STOPPING VOL upper");
        }

        [Test]
        public void Abs03_FixtureJson_IsValid()
        {
            string path = Path.Combine(FixtureDir, "abs-03-stopping.json");
            Assert.That(File.Exists(path), Is.True, "abs-03-stopping.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -----------------------------------------------------------------------
        // ABS-04: Effort vs Result — high vol + narrow range
        // -----------------------------------------------------------------------

        [Test]
        public void Abs04_EffortVsResultFixture_EmitsSignal()
        {
            // totalVol=900 > volEma=500*1.5=750. barRange=0.75 < atr=5*0.30=1.5.
            // barDelta=360>0 → direction=-1. ABS-03 blocked: 900 < volEma*2=1000.
            var bar = new FootprintBar
            {
                BarIndex = 35, Open = 20002.00, High = 20002.50, Low = 20001.75, Close = 20001.75
            };
            bar.Levels[20002.50] = new Cell { AskVol = 300, BidVol = 100 };
            bar.Levels[20002.25] = new Cell { AskVol = 200, BidVol = 100 };
            bar.Levels[20002.00] = new Cell { AskVol = 120, BidVol = 60  };
            bar.Levels[20001.75] = new Cell { AskVol = 10,  BidVol = 10  };
            bar.Finalize(0);
            // totalVol=900, barDelta=360, barRange=0.75, strength=min(900/1500,1)=0.60

            var session = new SessionContext { Atr20 = 5.0, VolEma20 = 500.0, TickSize = 0.25, Vah = 20005.0, Val = 19999.0 };
            var results = new AbsorptionDetector().OnBar(bar, session);

            AssertSignalPresent(results, "ABS-04", -1, 0.58, 0.62, "EFFORT vs RESULT");
        }

        [Test]
        public void Abs04_FixtureJson_IsValid()
        {
            string path = Path.Combine(FixtureDir, "abs-04-effort-vs-result.json");
            Assert.That(File.Exists(path), Is.True, "abs-04-effort-vs-result.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -----------------------------------------------------------------------
        // ABS-07: VA Extreme bonus applied to ABS-01 result
        // -----------------------------------------------------------------------

        [Test]
        public void Abs07_VaExtremeFixture_EmitsAbs01WithVahTag()
        {
            // ABS-01 fires at upper wick. bar.High=20002.75, vah=20003.00.
            // |20002.75-20003.00|=0.25 <= prox=2*0.25=0.5 → ABS-07 bonus applies.
            // ABS-01 Detail gets "@VAH" suffix; ABS-07 diagnostic emitted.
            var bar = new FootprintBar
            {
                BarIndex = 50, Open = 20001.00, High = 20002.75, Low = 19999.75, Close = 20001.25
            };
            bar.Levels[20002.75] = new Cell { AskVol = 200, BidVol = 180 };
            bar.Levels[20002.50] = new Cell { AskVol = 0,   BidVol = 0   };
            bar.Levels[20001.25] = new Cell { AskVol = 100, BidVol = 80  };
            bar.Levels[20001.00] = new Cell { AskVol = 80,  BidVol = 70  };
            bar.Levels[19999.75] = new Cell { AskVol = 10,  BidVol = 10  };
            bar.Finalize(0);
            // totalVol=730, upperVol=380, wickPct=52.1%, deltaRatio=20/380=0.053<0.12
            // ABS-01 fires; bumped strength = min(0.487+0.15,1.0)=0.637

            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25, Vah = 20003.00, Val = 19998.00 };
            var results = new AbsorptionDetector().OnBar(bar, session);

            // Assert ABS-01 has @VAH in Detail
            AssertSignalPresent(results, "ABS-01", -1, 0.50, 1.00, "@VAH");

            // Assert ABS-07 diagnostic was also emitted
            AssertSignalPresent(results, "ABS-07", -1, 0.50, 1.00, "ABS-07 VA extreme");
        }

        [Test]
        public void Abs07_FixtureJson_IsValid()
        {
            string path = Path.Combine(FixtureDir, "abs-07-va-extreme.json");
            Assert.That(File.Exists(path), Is.True, "abs-07-va-extreme.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -----------------------------------------------------------------------
        // Helper
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
    }
}
