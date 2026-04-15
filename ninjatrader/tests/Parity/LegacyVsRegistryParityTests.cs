// LegacyVsRegistryParityTests: gate suite comparing legacy static ABS/EXH algorithms
// (via LegacyDetectorsBridge) vs the registry path (AbsorptionDetector + ExhaustionDetector)
// on identical synthetic FootprintBar inputs.
//
// Wave 2 gate: ALL tests must pass before Wave 3 can begin.
// If any test fails, PARITY: FAIL and the regression must be investigated.
//
// Coverage:
//   - 10 fixture bars (ABS-01..04 + ABS-07, EXH-01..06) covering every legacy sub-type
//   - 10 seeded-random bars (seed=17) combining ABS+EXH triggers
//   - Cooldown parity test (EXH-02 suppressed in both paths after first fire)
//
// Parity semantics:
//   SignalId  — exact string equality
//   Direction — exact int equality
//   Strength  — within 1e-4 tolerance
//   FlagBit   — exact ulong equality (both paths use SignalFlagBits.Mask)
//
// Note: Detail strings are NOT compared (legacy and registry have different formatting).

using System;
using System.Collections.Generic;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Absorption;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Legacy;

namespace NinjaTrader.Tests.Parity
{
    [TestFixture]
    public class LegacyVsRegistryParityTests
    {
        // -----------------------------------------------------------------------
        // Shared config — must match default values in both legacy and registry
        // -----------------------------------------------------------------------
        private static readonly AbsorptionConfig AbsCfg = new AbsorptionConfig();
        private static readonly ExhaustionConfig ExhCfg = new ExhaustionConfig();

        // -----------------------------------------------------------------------
        // Fixture: ABS-01 classic bar
        // -----------------------------------------------------------------------
        [Test]
        public void Parity_Abs01_Classic()
        {
            var bar = MakeAbs01Bar();
            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 500.0, TickSize = 0.25, Vah = 20003.0, Val = 19999.0 };
            AssertAbsParity(bar, session);
        }

        // -----------------------------------------------------------------------
        // Fixture: ABS-02 passive bar
        // -----------------------------------------------------------------------
        [Test]
        public void Parity_Abs02_Passive()
        {
            var bar = MakeAbs02Bar();
            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25, Vah = 20003.5, Val = 19999.5 };
            AssertAbsParity(bar, session);
        }

        // -----------------------------------------------------------------------
        // Fixture: ABS-03 stopping volume bar
        // -----------------------------------------------------------------------
        [Test]
        public void Parity_Abs03_Stopping()
        {
            var bar = MakeAbs03Bar();
            var session = new SessionContext { Atr20 = 5.0, VolEma20 = 400.0, TickSize = 0.25, Vah = 20004.0, Val = 19999.0 };
            AssertAbsParity(bar, session);
        }

        // -----------------------------------------------------------------------
        // Fixture: ABS-04 effort vs result bar
        // -----------------------------------------------------------------------
        [Test]
        public void Parity_Abs04_EffortVsResult()
        {
            var bar = MakeAbs04Bar();
            var session = new SessionContext { Atr20 = 5.0, VolEma20 = 500.0, TickSize = 0.25, Vah = 20005.0, Val = 19999.0 };
            AssertAbsParity(bar, session);
        }

        // -----------------------------------------------------------------------
        // Fixture: ABS-07 VA extreme bonus bar
        // -----------------------------------------------------------------------
        [Test]
        public void Parity_Abs07_VaExtreme()
        {
            var bar = MakeAbs07Bar();
            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25, Vah = 20003.00, Val = 19998.00 };
            AssertAbsParity(bar, session);
        }

        // -----------------------------------------------------------------------
        // Fixture: EXH-01 zero print bar
        // -----------------------------------------------------------------------
        [Test]
        public void Parity_Exh01_ZeroPrint()
        {
            var bar = MakeExh01Bar();
            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25 };
            session.BarsSinceOpen = bar.BarIndex;
            AssertExhParity(bar, null, bar.BarIndex, session);
        }

        // -----------------------------------------------------------------------
        // Fixture: EXH-02 exhaustion print bar
        // -----------------------------------------------------------------------
        [Test]
        public void Parity_Exh02_ExhaustionPrint()
        {
            var bar = MakeExh02Bar();
            var session = new SessionContext { Atr20 = 5.0, VolEma20 = 300.0, TickSize = 0.25 };
            session.BarsSinceOpen = bar.BarIndex;
            AssertExhParity(bar, null, bar.BarIndex, session);
        }

        // -----------------------------------------------------------------------
        // Fixture: EXH-03 thin print bar
        // -----------------------------------------------------------------------
        [Test]
        public void Parity_Exh03_ThinPrint()
        {
            var bar = MakeExh03Bar();
            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25 };
            session.BarsSinceOpen = bar.BarIndex;
            AssertExhParity(bar, null, bar.BarIndex, session);
        }

        // -----------------------------------------------------------------------
        // Fixture: EXH-04 fat print bar
        // -----------------------------------------------------------------------
        [Test]
        public void Parity_Exh04_FatPrint()
        {
            var bar = MakeExh04Bar();
            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25 };
            session.BarsSinceOpen = bar.BarIndex;
            AssertExhParity(bar, null, bar.BarIndex, session);
        }

        // -----------------------------------------------------------------------
        // Fixture: EXH-05 fading momentum bar
        // -----------------------------------------------------------------------
        [Test]
        public void Parity_Exh05_FadingMomentum()
        {
            var bar = MakeExh05Bar();
            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25 };
            session.BarsSinceOpen = bar.BarIndex;
            AssertExhParity(bar, null, bar.BarIndex, session);
        }

        // -----------------------------------------------------------------------
        // Fixture: EXH-06 bid/ask fade bar (requires priorBar)
        // -----------------------------------------------------------------------
        [Test]
        public void Parity_Exh06_BidAskFade()
        {
            var priorBar = MakeExh06PriorBar();
            var bar      = MakeExh06Bar();
            var session = new SessionContext { Atr20 = 4.0, VolEma20 = 300.0, TickSize = 0.25 };
            session.PriorBar = priorBar;
            session.BarsSinceOpen = bar.BarIndex;
            AssertExhParity(bar, priorBar, bar.BarIndex, session);
        }

        // -----------------------------------------------------------------------
        // Cooldown parity: EXH-02 fires once then is suppressed in BOTH paths
        // -----------------------------------------------------------------------
        [Test]
        public void ExhaustionCooldown_Parity()
        {
            var legacyBridge = new LegacyExhaustionBridge();
            var registryDet  = new ExhaustionDetector();

            FootprintBar b1 = MakeExh02Bar();  // barIndex=15
            FootprintBar b2 = MakeExh02Bar();  // same bar pattern, bump barIndex by 1
            b2.BarIndex = b1.BarIndex + 1;

            var session = new SessionContext { Atr20 = 5.0, VolEma20 = 300.0, TickSize = 0.25 };

            // First bar: both paths fire EXH-02
            session.BarsSinceOpen = b1.BarIndex;
            var legR1 = legacyBridge.Detect(b1, null, b1.BarIndex, session.Atr20, ExhCfg);
            var regR1 = registryDet.OnBar(b1, session);

            bool legFired1 = ContainsSignal(legR1, "EXH-02");
            bool regFired1 = ContainsSignal(regR1, "EXH-02");
            Assert.That(legFired1, Is.True, "Legacy: EXH-02 should fire on first bar");
            Assert.That(regFired1, Is.True, "Registry: EXH-02 should fire on first bar");

            // Second bar within cooldown: both paths suppress EXH-02
            session.BarsSinceOpen = b2.BarIndex;
            var legR2 = legacyBridge.Detect(b2, null, b2.BarIndex, session.Atr20, ExhCfg);
            var regR2 = registryDet.OnBar(b2, session);

            bool legFired2 = ContainsSignal(legR2, "EXH-02");
            bool regFired2 = ContainsSignal(regR2, "EXH-02");
            Assert.That(legFired2, Is.False, "Legacy: EXH-02 must NOT re-fire within cooldown");
            Assert.That(regFired2, Is.False, "Registry: EXH-02 must NOT re-fire within cooldown");

            // Both paths agree on suppression
            Assert.That(legFired2, Is.EqualTo(regFired2),
                "Cooldown suppression must be identical between legacy and registry paths");
        }

        // -----------------------------------------------------------------------
        // 10 seeded-random bars (seed=17) — verify parity on arbitrary bars
        // -----------------------------------------------------------------------
        [Test]
        public void Parity_SeededRandom_Bars()
        {
            var rng = new Random(17);
            int divergences = 0;
            var divergenceLog = new List<string>();

            for (int i = 0; i < 10; i++)
            {
                var (bar, session) = MakeRandomBar(rng, i + 100);
                var legacyBridge = new LegacyExhaustionBridge();

                // ABS path
                var legAbs = LegacyAbsorptionBridge.Detect(
                    bar, session.Atr20, session.VolEma20, AbsCfg,
                    session.Vah, session.Val, session.TickSize);
                var regAbs = new AbsorptionDetector().OnBar(bar, session);

                string absDiff = FindDivergence("ABS bar#" + i, legAbs, regAbs);
                if (absDiff != null) { divergences++; divergenceLog.Add(absDiff); }

                // EXH path
                var legExh = legacyBridge.Detect(bar, null, bar.BarIndex, session.Atr20, ExhCfg);
                session.BarsSinceOpen = bar.BarIndex;
                var regExh = new ExhaustionDetector().OnBar(bar, session);

                string exhDiff = FindDivergence("EXH bar#" + i, legExh, regExh);
                if (exhDiff != null) { divergences++; divergenceLog.Add(exhDiff); }
            }

            Assert.That(divergences, Is.EqualTo(0),
                "Seeded-random parity divergences found:\n" + string.Join("\n", divergenceLog));
        }

        // -----------------------------------------------------------------------
        // Bar factory helpers — identical bars used across fixture + parity tests
        // -----------------------------------------------------------------------

        private static FootprintBar MakeAbs01Bar()
        {
            var b = new FootprintBar { BarIndex = 42, Open = 20001.75, High = 20005.00, Low = 20000.00, Close = 20001.25 };
            b.Levels[20005.00] = new Cell { AskVol = 185, BidVol = 165 };
            b.Levels[20004.75] = new Cell { AskVol = 0,   BidVol = 0   };
            b.Levels[20002.00] = new Cell { AskVol = 200, BidVol = 150 };
            b.Levels[20001.75] = new Cell { AskVol = 100, BidVol = 80  };
            b.Levels[20001.25] = new Cell { AskVol = 50,  BidVol = 50  };
            b.Levels[20000.50] = new Cell { AskVol = 10,  BidVol = 10  };
            b.Finalize(0);
            return b;
        }

        private static FootprintBar MakeAbs02Bar()
        {
            var b = new FootprintBar { BarIndex = 20, Open = 20004.00, High = 20005.00, Low = 20000.00, Close = 20001.00 };
            b.Levels[20005.00] = new Cell { AskVol = 300, BidVol = 0   };
            b.Levels[20004.75] = new Cell { AskVol = 0,   BidVol = 0   };
            b.Levels[20004.50] = new Cell { AskVol = 0,   BidVol = 0   };
            b.Levels[20004.25] = new Cell { AskVol = 0,   BidVol = 0   };
            b.Levels[20004.00] = new Cell { AskVol = 50,  BidVol = 50  };
            b.Levels[20003.00] = new Cell { AskVol = 20,  BidVol = 20  };
            b.Levels[20002.00] = new Cell { AskVol = 10,  BidVol = 10  };
            b.Levels[20001.00] = new Cell { AskVol = 5,   BidVol = 5   };
            b.Finalize(0);
            return b;
        }

        private static FootprintBar MakeAbs03Bar()
        {
            var b = new FootprintBar { BarIndex = 30, Open = 20001.00, High = 20006.00, Low = 19999.00, Close = 20000.50 };
            b.Levels[20006.00] = new Cell { AskVol = 800, BidVol = 50  };
            b.Levels[20005.00] = new Cell { AskVol = 200, BidVol = 50  };
            b.Levels[20001.00] = new Cell { AskVol = 30,  BidVol = 30  };
            b.Levels[20000.50] = new Cell { AskVol = 10,  BidVol = 10  };
            b.Levels[19999.00] = new Cell { AskVol = 10,  BidVol = 10  };
            b.Finalize(0);
            return b;
        }

        private static FootprintBar MakeAbs04Bar()
        {
            var b = new FootprintBar { BarIndex = 35, Open = 20002.00, High = 20002.50, Low = 20001.75, Close = 20001.75 };
            b.Levels[20002.50] = new Cell { AskVol = 300, BidVol = 100 };
            b.Levels[20002.25] = new Cell { AskVol = 200, BidVol = 100 };
            b.Levels[20002.00] = new Cell { AskVol = 120, BidVol = 60  };
            b.Levels[20001.75] = new Cell { AskVol = 10,  BidVol = 10  };
            b.Finalize(0);
            return b;
        }

        private static FootprintBar MakeAbs07Bar()
        {
            var b = new FootprintBar { BarIndex = 50, Open = 20001.00, High = 20002.75, Low = 19999.75, Close = 20001.25 };
            b.Levels[20002.75] = new Cell { AskVol = 200, BidVol = 180 };
            b.Levels[20002.50] = new Cell { AskVol = 0,   BidVol = 0   };
            b.Levels[20001.25] = new Cell { AskVol = 100, BidVol = 80  };
            b.Levels[20001.00] = new Cell { AskVol = 80,  BidVol = 70  };
            b.Levels[19999.75] = new Cell { AskVol = 10,  BidVol = 10  };
            b.Finalize(0);
            return b;
        }

        private static FootprintBar MakeExh01Bar()
        {
            var b = new FootprintBar { BarIndex = 10, Open = 20000.00, High = 20005.00, Low = 19999.75, Close = 20004.00 };
            b.Levels[20005.00] = new Cell { AskVol = 200, BidVol = 10  };
            b.Levels[20004.00] = new Cell { AskVol = 150, BidVol = 20  };
            b.Levels[20002.00] = new Cell { AskVol = 0,   BidVol = 0   };
            b.Levels[20000.00] = new Cell { AskVol = 100, BidVol = 100 };
            b.Levels[19999.75] = new Cell { AskVol = 10,  BidVol = 80  };
            b.Finalize(0);
            return b;
        }

        private static FootprintBar MakeExh02Bar()
        {
            var b = new FootprintBar { BarIndex = 15, Open = 20004.00, High = 20005.00, Low = 20002.00, Close = 20002.50 };
            b.Levels[20005.00] = new Cell { AskVol = 120, BidVol = 10  };
            b.Levels[20004.50] = new Cell { AskVol = 100, BidVol = 90  };
            b.Levels[20004.00] = new Cell { AskVol = 100, BidVol = 90  };
            b.Levels[20003.00] = new Cell { AskVol = 80,  BidVol = 80  };
            b.Levels[20002.50] = new Cell { AskVol = 60,  BidVol = 60  };
            b.Levels[20002.00] = new Cell { AskVol = 5,   BidVol = 5   };
            b.Finalize(0);
            return b;
        }

        private static FootprintBar MakeExh03Bar()
        {
            var b = new FootprintBar { BarIndex = 25, Open = 20005.00, High = 20006.00, Low = 20002.00, Close = 20002.50 };
            b.Levels[20006.00] = new Cell { AskVol = 5,   BidVol = 5   };
            b.Levels[20005.00] = new Cell { AskVol = 400, BidVol = 200 };
            b.Levels[20004.75] = new Cell { AskVol = 8,   BidVol = 4   };
            b.Levels[20004.50] = new Cell { AskVol = 6,   BidVol = 3   };
            b.Levels[20004.25] = new Cell { AskVol = 5,   BidVol = 2   };
            b.Levels[20003.50] = new Cell { AskVol = 7,   BidVol = 4   };
            b.Levels[20002.50] = new Cell { AskVol = 50,  BidVol = 40  };
            b.Levels[20002.00] = new Cell { AskVol = 10,  BidVol = 10  };
            b.Finalize(0);
            return b;
        }

        private static FootprintBar MakeExh04Bar()
        {
            var b = new FootprintBar { BarIndex = 40, Open = 20004.00, High = 20005.00, Low = 20002.00, Close = 20002.50 };
            b.Levels[20002.00] = new Cell { AskVol = 500, BidVol = 400 };
            b.Levels[20003.00] = new Cell { AskVol = 40,  BidVol = 30  };
            b.Levels[20004.00] = new Cell { AskVol = 30,  BidVol = 20  };
            b.Levels[20005.00] = new Cell { AskVol = 10,  BidVol = 10  };
            b.Finalize(0);
            return b;
        }

        private static FootprintBar MakeExh05Bar()
        {
            var b = new FootprintBar { BarIndex = 45, Open = 20001.00, High = 20004.00, Low = 20000.50, Close = 20003.50 };
            b.Levels[20000.50] = new Cell { AskVol = 10,  BidVol = 200 };
            b.Levels[20001.00] = new Cell { AskVol = 20,  BidVol = 150 };
            b.Levels[20002.00] = new Cell { AskVol = 30,  BidVol = 80  };
            b.Levels[20003.50] = new Cell { AskVol = 20,  BidVol = 60  };
            b.Levels[20004.00] = new Cell { AskVol = 10,  BidVol = 10  };
            b.Finalize(0);
            return b;
        }

        private static FootprintBar MakeExh06PriorBar()
        {
            var b = new FootprintBar { BarIndex = 59, Open = 20003.00, High = 20005.00, Low = 20001.00, Close = 20004.50 };
            b.Levels[20005.00] = new Cell { AskVol = 200, BidVol = 50  };
            b.Levels[20004.50] = new Cell { AskVol = 100, BidVol = 80  };
            b.Levels[20003.00] = new Cell { AskVol = 60,  BidVol = 40  };
            b.Levels[20002.00] = new Cell { AskVol = 30,  BidVol = 20  };
            b.Levels[20001.00] = new Cell { AskVol = 10,  BidVol = 10  };
            b.Finalize(0);
            return b;
        }

        private static FootprintBar MakeExh06Bar()
        {
            var b = new FootprintBar { BarIndex = 60, Open = 20004.50, High = 20005.00, Low = 20002.00, Close = 20002.25 };
            b.Levels[20005.00] = new Cell { AskVol = 30,  BidVol = 10  };
            b.Levels[20004.00] = new Cell { AskVol = 80,  BidVol = 60  };
            b.Levels[20003.00] = new Cell { AskVol = 60,  BidVol = 40  };
            b.Levels[20002.25] = new Cell { AskVol = 20,  BidVol = 15  };
            b.Levels[20002.00] = new Cell { AskVol = 10,  BidVol = 10  };
            b.Finalize(0);
            return b;
        }

        // -----------------------------------------------------------------------
        // Seeded-random bar generator
        // -----------------------------------------------------------------------
        private static (FootprintBar bar, SessionContext session) MakeRandomBar(Random rng, int barIdx)
        {
            double basePrice = 20000.0 + rng.NextDouble() * 10.0;
            basePrice = System.Math.Round(basePrice / 0.25) * 0.25;
            double barRange = 0.25 + rng.NextDouble() * 6.0;
            barRange = System.Math.Round(barRange / 0.25) * 0.25;
            double open  = basePrice;
            double high  = open + barRange;
            double low   = open - rng.NextDouble() * barRange * 0.5;
            low  = System.Math.Round(low  / 0.25) * 0.25;
            double close = low + rng.NextDouble() * barRange;
            close = System.Math.Round(close / 0.25) * 0.25;
            if (close > high) close = high;
            if (close < low)  close = low;

            var bar = new FootprintBar { BarIndex = barIdx, Open = open, High = high, Low = low, Close = close };

            // Add 3-8 levels between low and high
            int levels = 3 + rng.Next(6);
            double step = (high - low) / System.Math.Max(levels - 1, 1);
            for (int i = 0; i < levels; i++)
            {
                double px = System.Math.Round((low + i * step) / 0.25) * 0.25;
                long ask = (long)(rng.NextDouble() * 300);
                long bid = (long)(rng.NextDouble() * 300);
                if (!bar.Levels.ContainsKey(px))
                    bar.Levels[px] = new Cell { AskVol = ask, BidVol = bid };
            }
            bar.Finalize(0);

            double atr = 1.0 + rng.NextDouble() * 6.0;
            double vah = high + rng.NextDouble() * 2.0;
            vah = System.Math.Round(vah / 0.25) * 0.25;
            double val = low - rng.NextDouble() * 2.0;
            val = System.Math.Round(val / 0.25) * 0.25;

            var session = new SessionContext
            {
                Atr20    = atr,
                VolEma20 = 200.0 + rng.NextDouble() * 400.0,
                TickSize = 0.25,
                Vah      = vah,
                Val      = val,
            };
            session.BarsSinceOpen = barIdx;

            return (bar, session);
        }

        // -----------------------------------------------------------------------
        // Parity assertion helpers
        // -----------------------------------------------------------------------

        private static void AssertAbsParity(FootprintBar bar, SessionContext session)
        {
            var legacy = LegacyAbsorptionBridge.Detect(
                bar, session.Atr20, session.VolEma20, AbsCfg,
                session.Vah, session.Val, session.TickSize);
            var registry = new AbsorptionDetector().OnBar(bar, session);

            string diff = FindDivergence("ABS", legacy, registry);
            Assert.That(diff, Is.Null,
                "ABS legacy vs registry divergence on bar#" + bar.BarIndex + ":\n" + diff);
        }

        private static void AssertExhParity(
            FootprintBar bar, FootprintBar priorBar, int barIndex, SessionContext session)
        {
            var legacyBridge = new LegacyExhaustionBridge();
            var legacy   = legacyBridge.Detect(bar, priorBar, barIndex, session.Atr20, ExhCfg);
            var registry = new ExhaustionDetector().OnBar(bar, session);

            string diff = FindDivergence("EXH", legacy, registry);
            Assert.That(diff, Is.Null,
                "EXH legacy vs registry divergence on bar#" + bar.BarIndex + ":\n" + diff);
        }

        /// <summary>
        /// Compare two SignalResult[] by (SignalId, Direction, Strength±1e-4, FlagBit).
        /// Returns null if parity, otherwise returns a human-readable divergence description.
        /// </summary>
        private static string FindDivergence(string label, SignalResult[] a, SignalResult[] b)
        {
            // Sort by SignalId then Direction for stable comparison
            Array.Sort(a, CompareSignals);
            Array.Sort(b, CompareSignals);

            if (a.Length != b.Length)
                return string.Format("{0}: count mismatch — legacy={1}, registry={2}\n  legacy: {3}\n  registry: {4}",
                    label, a.Length, b.Length, Describe(a), Describe(b));

            for (int i = 0; i < a.Length; i++)
            {
                if (a[i].SignalId != b[i].SignalId)
                    return string.Format("{0}[{1}]: SignalId mismatch — legacy='{2}', registry='{3}'",
                        label, i, a[i].SignalId, b[i].SignalId);
                if (a[i].Direction != b[i].Direction)
                    return string.Format("{0}[{1}] {2}: Direction mismatch — legacy={3}, registry={4}",
                        label, i, a[i].SignalId, a[i].Direction, b[i].Direction);
                if (System.Math.Abs(a[i].Strength - b[i].Strength) > 1e-4)
                    return string.Format("{0}[{1}] {2}: Strength mismatch — legacy={3:F6}, registry={4:F6} (delta={5:E2})",
                        label, i, a[i].SignalId, a[i].Strength, b[i].Strength,
                        System.Math.Abs(a[i].Strength - b[i].Strength));
                if (a[i].FlagBit != b[i].FlagBit)
                    return string.Format("{0}[{1}] {2}: FlagBit mismatch — legacy={3}, registry={4}",
                        label, i, a[i].SignalId, a[i].FlagBit, b[i].FlagBit);
            }
            return null;
        }

        private static int CompareSignals(SignalResult x, SignalResult y)
        {
            int c = string.Compare(x.SignalId, y.SignalId, StringComparison.Ordinal);
            if (c != 0) return c;
            return x.Direction.CompareTo(y.Direction);
        }

        private static string Describe(SignalResult[] arr)
        {
            if (arr.Length == 0) return "(empty)";
            var parts = new List<string>();
            foreach (var r in arr)
                parts.Add(string.Format("[{0} dir={1} str={2:F4} flag={3}]",
                    r.SignalId, r.Direction, r.Strength, r.FlagBit));
            return string.Join(", ", parts);
        }

        private static bool ContainsSignal(SignalResult[] results, string signalId)
        {
            foreach (var r in results)
                if (r.SignalId == signalId) return true;
            return false;
        }
    }
}
