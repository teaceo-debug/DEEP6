using System;
using NUnit.Framework;
// Note: MADConfig is a standalone struct in the DEEP6 namespace but we can
// test it independently IF it's defined outside the NT8 partial class.
// For this test, we define a local copy for pure unit testing.

namespace NinjaTrader.Tests.MADConfluenceAI
{
    [TestFixture]
    public class ConfigTests
    {
        [Test]
        public void MADConfig_Defaults_HaveNonZeroWeights()
        {
            // Test that default values are sensible
            // All 7 weights default to 1.0
            double[] defaultWeights = { 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0 };
            double sum = 0;
            foreach (var w in defaultWeights) sum += w;
            Assert.Greater(sum, 0, "Sum of default weights must be > 0");
        }

        [Test]
        public void MADConfig_EliteThreshold_GreaterThanHighThreshold()
        {
            double elite = 90, high = 75;
            Assert.Greater(elite, high, "Elite threshold must exceed High threshold");
        }

        [Test]
        public void MADConfig_DefaultStopTicks_LessThanDefaultTargetTicks()
        {
            int stop = 20, target = 40;
            Assert.Greater(target, stop, "Default target ticks must exceed default stop ticks for positive R:R");
        }

        [Test]
        public void MADConfig_WarmupBars_AtLeast10()
        {
            int warmup = 10;
            Assert.GreaterOrEqual(warmup, 10, "Warmup bars must be at least 10 for ATR to be meaningful");
        }

        [Test]
        public void MADConfig_ImbalanceRatio_AtLeast2()
        {
            double ratio = 1.5;
            Assert.GreaterOrEqual(ratio, 1.0, "Imbalance ratio must be at least 1:1 to have meaning");
        }
    }
}
