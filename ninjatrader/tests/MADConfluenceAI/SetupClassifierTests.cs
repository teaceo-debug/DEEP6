// SetupClassifierTests.cs — T19 Setup Classifier tests
using System.Collections.Generic;
using NUnit.Framework;

namespace NinjaTrader.Tests.MADConfluenceAI
{
    // Test-local enum mirroring MADSetupType
    public enum TestSetupType
    {
        Reversal, Breakout, FailedBreakout, AbsorptionBounce,
        TrendContinuation, ExhaustionReversal, LiquiditySweepReversal, None
    }

    /// <summary>
    /// Test-local classifier — mirrors ClassifySetup logic exactly.
    /// </summary>
    public static class TestSetupClassifier
    {
        public static TestSetupType Classify(List<TestSignalResult> signals, TestRegime regime, bool isAtKeyLevel)
        {
            if (signals == null || signals.Count == 0) return TestSetupType.None;

            bool hasAbs = false, hasExh = false, hasImb = false, hasTrap = false;
            bool hasDelt = false, hasDelt02 = false, hasLiqSw = false;

            foreach (var s in signals)
            {
                if (s.SignalId == null) continue;
                if (s.SignalId.StartsWith("ABS")) hasAbs = true;
                if (s.SignalId.StartsWith("EXH")) hasExh = true;
                if (s.SignalId.StartsWith("IMB")) hasImb = true;
                if (s.SignalId.StartsWith("TRAP")) hasTrap = true;
                if (s.SignalId.StartsWith("DELT")) hasDelt = true;
                if (s.SignalId == "DELT-02") hasDelt02 = true;
                if (s.SignalId.StartsWith("LIQSW")) hasLiqSw = true;
            }

            if (hasAbs && hasExh && isAtKeyLevel && regime == TestRegime.Ranging)
                return TestSetupType.Reversal;
            if (hasImb && regime == TestRegime.Trending)
                return TestSetupType.Breakout;
            if (hasTrap)
                return TestSetupType.FailedBreakout;
            if (hasAbs && hasDelt)
                return TestSetupType.AbsorptionBounce;
            if (regime == TestRegime.Trending && hasDelt02)
                return TestSetupType.TrendContinuation;
            if (hasExh && hasDelt)
                return TestSetupType.ExhaustionReversal;
            if (hasLiqSw && hasAbs)
                return TestSetupType.LiquiditySweepReversal;
            return TestSetupType.None;
        }
    }

    [TestFixture]
    public class SetupClassifierTests
    {
        [Test]
        public void Reversal_ABS_EXH_AtKeyLevel_Ranging()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 },
                new TestSignalResult { SignalId = "EXH-01", Direction = TestSignalDirection.Long, Strength = 0.7 }
            };
            var result = TestSetupClassifier.Classify(signals, TestRegime.Ranging, true);
            Assert.AreEqual(TestSetupType.Reversal, result);
        }

        [Test]
        public void Breakout_IMB_Trending()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "IMB-01", Direction = TestSignalDirection.Long, Strength = 0.6 }
            };
            var result = TestSetupClassifier.Classify(signals, TestRegime.Trending, false);
            Assert.AreEqual(TestSetupType.Breakout, result);
        }

        [Test]
        public void FailedBreakout_TRAP()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "TRAP-01", Direction = TestSignalDirection.Short, Strength = 0.7 }
            };
            var result = TestSetupClassifier.Classify(signals, TestRegime.Ranging, false);
            Assert.AreEqual(TestSetupType.FailedBreakout, result);
        }

        [Test]
        public void AbsorptionBounce_ABS_DELT()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 },
                new TestSignalResult { SignalId = "DELT-01", Direction = TestSignalDirection.Long, Strength = 0.6 }
            };
            var result = TestSetupClassifier.Classify(signals, TestRegime.Volatile, false);
            Assert.AreEqual(TestSetupType.AbsorptionBounce, result);
        }

        [Test]
        public void TrendContinuation_DELT02_Trending()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "DELT-02", Direction = TestSignalDirection.Long, Strength = 0.7 }
            };
            var result = TestSetupClassifier.Classify(signals, TestRegime.Trending, false);
            Assert.AreEqual(TestSetupType.TrendContinuation, result);
        }

        [Test]
        public void ExhaustionReversal_EXH_DELT()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "EXH-01", Direction = TestSignalDirection.Short, Strength = 0.8 },
                new TestSignalResult { SignalId = "DELT-01", Direction = TestSignalDirection.Short, Strength = 0.6 }
            };
            var result = TestSetupClassifier.Classify(signals, TestRegime.Ranging, false);
            Assert.AreEqual(TestSetupType.ExhaustionReversal, result);
        }

        [Test]
        public void LiquiditySweepReversal_LIQSW_ABS()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "LIQSW-01", Direction = TestSignalDirection.Long, Strength = 0.9 },
                new TestSignalResult { SignalId = "ABS-02", Direction = TestSignalDirection.Long, Strength = 0.7 }
            };
            var result = TestSetupClassifier.Classify(signals, TestRegime.Ranging, false);
            Assert.AreEqual(TestSetupType.LiquiditySweepReversal, result);
        }

        [Test]
        public void NoMatch_ReturnsNone()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ICE-01", Direction = TestSignalDirection.Long, Strength = 0.5 }
            };
            var result = TestSetupClassifier.Classify(signals, TestRegime.Ranging, false);
            Assert.AreEqual(TestSetupType.None, result);
        }

        [Test]
        public void EmptySignals_ReturnsNone()
        {
            var result = TestSetupClassifier.Classify(new List<TestSignalResult>(), TestRegime.Ranging, false);
            Assert.AreEqual(TestSetupType.None, result);
        }

        [Test]
        public void Priority_Reversal_BeatsAbsorptionBounce()
        {
            // Has ABS + EXH + DELT at key level + Ranging → should pick Reversal (higher priority)
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 },
                new TestSignalResult { SignalId = "EXH-01", Direction = TestSignalDirection.Long, Strength = 0.7 },
                new TestSignalResult { SignalId = "DELT-01", Direction = TestSignalDirection.Long, Strength = 0.6 }
            };
            var result = TestSetupClassifier.Classify(signals, TestRegime.Ranging, true);
            Assert.AreEqual(TestSetupType.Reversal, result, "Reversal should take priority over AbsorptionBounce");
        }
    }
}
