// ExhaustionDetectorTests: fixture-driven smoke tests for ExhaustionDetector.
// Fixture: ninjatrader/tests/fixtures/exhaustion/exh-01-zero-print.json
//
// Verifies that EXH-01 fires with correct signal ID, direction=+1 (bullish bar → +1),
// strength=0.6, and FlagBit on a bar with a zero-vol level inside the body.

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
    public class ExhaustionDetectorTests
    {
        /// <summary>
        /// EXH-01 zero-print fires when a level inside the bar body has askVol=0 and bidVol=0.
        /// EXH-01 is delta-gate exempt — fires regardless of delta.
        /// Fixture: exh-01-zero-print.json
        /// Assertion: SignalId=="EXH-01", Direction==+1 (bullish bar close>open), Strength==0.6.
        /// </summary>
        [Test]
        public void Exh01_ZeroPrintFixture_EmitsExpectedSignal()
        {
            // Build bar matching exh-01-zero-print.json
            var bar = new FootprintBar
            {
                BarIndex = 10,
                Open     = 20000.00,
                High     = 20005.00,
                Low      = 19999.75,
                Close    = 20004.00,
            };
            // Levels: 20002.00 is inside body (bodyBot=20000, bodyTop=20004) with zero vol
            bar.Levels[20005.00] = new Cell { AskVol = 200, BidVol = 10  };
            bar.Levels[20004.00] = new Cell { AskVol = 150, BidVol = 20  };
            bar.Levels[20002.00] = new Cell { AskVol = 0,   BidVol = 0   };  // ZERO PRINT
            bar.Levels[20000.00] = new Cell { AskVol = 100, BidVol = 100 };
            bar.Levels[19999.75] = new Cell { AskVol = 10,  BidVol = 80  };
            bar.Finalize(priorCvd: 0);
            // TotalVol = 200+10 + 150+20 + 0+0 + 100+100 + 10+80 = 670
            // barDelta  = (200-10)+(150-20)+(0-0)+(100-100)+(10-80) = 190+130+0+0-70 = 250
            // bodyBot = min(20000,20004)=20000, bodyTop=max(20000,20004)=20004
            // 20002 is inside body (20000 < 20002 < 20004) → zero print fires

            // Use DeltaGateEnabled=false to isolate EXH-01 test from gate
            var cfg = new ExhaustionConfig { DeltaGateEnabled = false };
            var session = new SessionContext
            {
                Atr20    = 4.0,
                VolEma20 = 300.0,
                TickSize = 0.25
            };

            var detector = new ExhaustionDetector(cfg);
            var results  = detector.OnBar(bar, session);

            SignalResult exh01 = null;
            foreach (var r in results)
                if (r.SignalId == "EXH-01") { exh01 = r; break; }

            Assert.That(exh01, Is.Not.Null, "EXH-01 should fire when a level inside body has zero vol");
            Assert.That(exh01.Direction, Is.EqualTo(+1), "Bullish bar (close>open) → direction=+1");
            Assert.That(exh01.Strength,  Is.EqualTo(0.6).Within(1e-9), "EXH-01 strength is fixed at 0.6");
            Assert.That(exh01.FlagBit,   Is.EqualTo(SignalFlagBits.Mask(SignalFlagBits.EXH_01)),
                "FlagBit must equal Mask(EXH_01)");
            StringAssert.Contains("ZERO PRINT", exh01.Detail,
                "Detail should contain 'ZERO PRINT'");
        }

        /// <summary>
        /// EXH-01 should NOT fire when no level inside the body has zero vol.
        /// </summary>
        [Test]
        public void Exh01_NoZeroPrint_DoesNotFire()
        {
            var bar = new FootprintBar
            {
                BarIndex = 5,
                Open     = 20000.00,
                High     = 20005.00,
                Low      = 19999.75,
                Close    = 20004.00,
            };
            // All levels have non-zero vol
            bar.Levels[20004.00] = new Cell { AskVol = 150, BidVol = 20 };
            bar.Levels[20002.00] = new Cell { AskVol = 100, BidVol = 50 };  // non-zero
            bar.Levels[20000.00] = new Cell { AskVol = 100, BidVol = 100 };
            bar.Finalize();

            var cfg     = new ExhaustionConfig { DeltaGateEnabled = false };
            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25 };
            var detector = new ExhaustionDetector(cfg);
            var results  = detector.OnBar(bar, session);

            bool hasExh01 = false;
            foreach (var r in results) if (r.SignalId == "EXH-01") { hasExh01 = true; break; }
            Assert.That(hasExh01, Is.False, "EXH-01 should NOT fire when no zero-vol level in body");
        }

        /// <summary>
        /// Cooldown: EXH-01 should NOT fire twice within CooldownBars bars.
        /// </summary>
        [Test]
        public void Exh01_Cooldown_PreventsDuplicateFire()
        {
            var cfg = new ExhaustionConfig { DeltaGateEnabled = false, CooldownBars = 5 };
            var detector = new ExhaustionDetector(cfg);

            Func<int, FootprintBar> makeBar = (idx) => {
                var b = new FootprintBar
                {
                    BarIndex = idx,
                    Open = 20000.00, High = 20005.00, Low = 19999.75, Close = 20004.00
                };
                b.Levels[20004.00] = new Cell { AskVol = 150, BidVol = 20 };
                b.Levels[20002.00] = new Cell { AskVol = 0,   BidVol = 0  };  // zero print
                b.Levels[20000.00] = new Cell { AskVol = 100, BidVol = 100 };
                b.Finalize();
                return b;
            };

            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25 };

            // First call — should fire
            session.BarsSinceOpen = 1;
            var r1 = detector.OnBar(makeBar(1), session);
            bool fired1 = false;
            foreach (var r in r1) if (r.SignalId == "EXH-01") { fired1 = true; break; }
            Assert.That(fired1, Is.True, "EXH-01 should fire on first zero-print bar");

            // Second call within cooldown — should NOT fire (barIndex 2, cooldown=5, last=1)
            session.BarsSinceOpen = 2;
            var r2 = detector.OnBar(makeBar(2), session);
            bool fired2 = false;
            foreach (var r in r2) if (r.SignalId == "EXH-01") { fired2 = true; break; }
            Assert.That(fired2, Is.False, "EXH-01 should NOT fire within cooldown window");
        }

        /// <summary>
        /// Fixture JSON is valid JSON and parses without error.
        /// </summary>
        [Test]
        public void Exh01Fixture_JsonIsValid()
        {
            string fixturePath = Path.Combine(
                TestContext.CurrentContext.TestDirectory,
                "fixtures", "exhaustion", "exh-01-zero-print.json");
            Assert.That(File.Exists(fixturePath), Is.True,
                $"Fixture file not found at {fixturePath}");
            string json = File.ReadAllText(fixturePath);
            Assert.DoesNotThrow(() => JsonDocument.Parse(json),
                "exh-01-zero-print.json must be valid JSON");
        }
    }
}
