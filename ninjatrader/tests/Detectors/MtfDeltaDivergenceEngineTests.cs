using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta;

namespace NinjaTrader.Tests.Detectors
{
    [TestFixture]
    public class MtfDeltaDivergenceEngineTests
    {
        private static DeltaDivergenceBar Bar(double high, double low, double close, long delta)
        {
            return new DeltaDivergenceBar(high, low, close, delta);
        }

        [Test]
        public void InsufficientHistory_RemainsNeutral()
        {
            var engine = new MtfDeltaDivergenceEngine(new MtfDeltaDivergenceConfig
            {
                PivotLookback = 5,
                MinBars = 5,
                TickSize = 0.25,
                MinPriceBreakTicks = 2,
                MinDeltaImprovement = 100,
                CloseConfirmationRatio = 0.50,
            });

            for (int i = 0; i < 5; i++)
                engine.AddBar(Bar(101 + i, 100 + i, 100.75 + i, -50 - (i * 10)));

            Assert.That(engine.CurrentBias, Is.EqualTo(DeltaDivergenceBias.Neutral));
        }

        [Test]
        public void LowerLowWithStrongerDeltaAndUpperClose_FiresBullish()
        {
            var engine = new MtfDeltaDivergenceEngine(new MtfDeltaDivergenceConfig
            {
                PivotLookback = 6,
                MinBars = 6,
                TickSize = 0.25,
                MinPriceBreakTicks = 2,
                MinDeltaImprovement = 150,
                CloseConfirmationRatio = 0.50,
            });

            engine.AddBar(Bar(101.00, 100.00, 100.40, -150));
            engine.AddBar(Bar(100.80, 99.75, 100.10, -250));
            engine.AddBar(Bar(100.60, 99.50, 99.90, -350));
            engine.AddBar(Bar(100.40, 99.25, 99.60, -450));
            engine.AddBar(Bar(100.20, 99.00, 99.40, -1000));
            engine.AddBar(Bar(100.10, 98.50, 99.85, -300));

            Assert.That(engine.CurrentBias, Is.EqualTo(DeltaDivergenceBias.Bullish));
        }

        [Test]
        public void HigherHighWithWeakerDeltaAndLowerClose_FiresBearish()
        {
            var engine = new MtfDeltaDivergenceEngine(new MtfDeltaDivergenceConfig
            {
                PivotLookback = 6,
                MinBars = 6,
                TickSize = 0.25,
                MinPriceBreakTicks = 2,
                MinDeltaImprovement = 150,
                CloseConfirmationRatio = 0.50,
            });

            engine.AddBar(Bar(100.50, 99.50, 100.10, 150));
            engine.AddBar(Bar(100.75, 99.75, 100.40, 250));
            engine.AddBar(Bar(101.00, 100.00, 100.60, 350));
            engine.AddBar(Bar(101.25, 100.20, 100.90, 450));
            engine.AddBar(Bar(101.50, 100.40, 101.10, 1000));
            engine.AddBar(Bar(102.10, 100.60, 100.90, 300));

            Assert.That(engine.CurrentBias, Is.EqualTo(DeltaDivergenceBias.Bearish));
        }

        [Test]
        public void LowerLowWithoutDeltaImprovement_StaysNeutral()
        {
            var engine = new MtfDeltaDivergenceEngine(new MtfDeltaDivergenceConfig
            {
                PivotLookback = 6,
                MinBars = 6,
                TickSize = 0.25,
                MinPriceBreakTicks = 2,
                MinDeltaImprovement = 150,
                CloseConfirmationRatio = 0.50,
            });

            engine.AddBar(Bar(101.00, 100.00, 100.40, -150));
            engine.AddBar(Bar(100.80, 99.75, 100.10, -250));
            engine.AddBar(Bar(100.60, 99.50, 99.90, -350));
            engine.AddBar(Bar(100.40, 99.25, 99.60, -450));
            engine.AddBar(Bar(100.20, 99.00, 99.40, -800));
            engine.AddBar(Bar(100.10, 98.50, 99.85, -750));

            Assert.That(engine.CurrentBias, Is.EqualTo(DeltaDivergenceBias.Neutral));
        }

        [Test]
        public void CompositeBias_RequiresConfiguredAgreement()
        {
            Assert.That(
                MtfDeltaDivergenceEngine.ToCompositeBias(
                    new[]
                    {
                        DeltaDivergenceBias.Bullish,
                        DeltaDivergenceBias.Bullish,
                        DeltaDivergenceBias.Bullish,
                    },
                    3),
                Is.EqualTo(DeltaDivergenceBias.Bullish));

            Assert.That(
                MtfDeltaDivergenceEngine.ToCompositeBias(
                    new[]
                    {
                        DeltaDivergenceBias.Bearish,
                        DeltaDivergenceBias.Bearish,
                        DeltaDivergenceBias.Neutral,
                    },
                    3),
                Is.EqualTo(DeltaDivergenceBias.Neutral));
        }
    }
}
