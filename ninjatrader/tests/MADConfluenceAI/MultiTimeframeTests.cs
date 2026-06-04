// MultiTimeframeTests.cs — TDD tests for HTF bias logic (T11)
// Tests the bias computation logic directly via a test-local helper
// that mirrors the OnBarUpdate HTF computation. No NT8 dependency.
using System;
using NUnit.Framework;

namespace NinjaTrader.Tests.MADConfluenceAI.MultiTimeframe
{
    // ── Test-local enums/types (mirrors Scoring.cs) ─────────────────────

    public enum MADTrend { Bullish, Bearish, Neutral }

    /// <summary>
    /// Test helper that mirrors the HTF bias computation from MADConfluenceAI.OnBarUpdate.
    /// Operates on a rolling buffer of 5-minute closes.
    /// </summary>
    public sealed class HtfBiasComputer
    {
        private readonly double[] _closes = new double[25];
        private int _count;

        public MADTrend HtfBias { get; private set; } = MADTrend.Neutral;
        public double HtfMomentum { get; private set; }
        public double LastSma20 { get; private set; }

        /// <summary>
        /// Feed a 5-minute close. Mirrors the BarsInProgress==1 logic.
        /// </summary>
        public void AddClose(double close)
        {
            _closes[_count % 25] = close;
            _count++;

            if (_count >= 20)
            {
                // Manual SMA(20) from rolling buffer
                double sum = 0;
                for (int i = 0; i < 20; i++)
                    sum += _closes[(_count - 1 - i) % 25];
                double sma20 = sum / 20.0;
                LastSma20 = sma20;

                if (close > sma20 * 1.001)
                    HtfBias = MADTrend.Bullish;
                else if (close < sma20 * 0.999)
                    HtfBias = MADTrend.Bearish;
                else
                    HtfBias = MADTrend.Neutral;
            }

            if (_count >= 10)
            {
                double latest = _closes[(_count - 1) % 25];
                double oldest = _closes[(_count - 10) % 25];
                if (oldest > 0)
                    HtfMomentum = (latest - oldest) / oldest;
            }
        }

        public int Count => _count;
    }

    // ── Tests ───────────────────────────────────────────────────────────

    [TestFixture]
    public class MultiTimeframeTests
    {
        [Test]
        public void AscendingCloses_ProducesBullishBias()
        {
            var computer = new HtfBiasComputer();

            // 20 ascending closes: 20000, 20010, 20020, ...
            for (int i = 0; i < 20; i++)
                computer.AddClose(20000.0 + i * 10.0);

            // Last close = 20190, SMA20 = avg of 20000..20190 = 20095
            // 20190 > 20095 * 1.001 = 20115.095 → Bullish
            Assert.AreEqual(MADTrend.Bullish, computer.HtfBias, "Ascending closes should produce Bullish bias");
        }

        [Test]
        public void DescendingCloses_ProducesBearishBias()
        {
            var computer = new HtfBiasComputer();

            // 20 descending closes: 21000, 20990, 20980, ...
            for (int i = 0; i < 20; i++)
                computer.AddClose(21000.0 - i * 10.0);

            // Last close = 20810, SMA20 = avg of 21000..20810 = 20905
            // 20810 < 20905 * 0.999 = 20884.095 → Bearish
            Assert.AreEqual(MADTrend.Bearish, computer.HtfBias, "Descending closes should produce Bearish bias");
        }

        [Test]
        public void CloseNearSma20_ProducesNeutralBias()
        {
            var computer = new HtfBiasComputer();

            // 20 flat closes at same price → SMA = close exactly → Neutral
            for (int i = 0; i < 20; i++)
                computer.AddClose(21000.0);

            Assert.AreEqual(MADTrend.Neutral, computer.HtfBias, "Flat closes should produce Neutral bias");
        }

        [Test]
        public void Momentum_PositiveWhenPricesRising()
        {
            var computer = new HtfBiasComputer();

            // 10 ascending closes
            for (int i = 0; i < 10; i++)
                computer.AddClose(20000.0 + i * 20.0);

            // Momentum = (latest - oldest) / oldest = (20180 - 20000) / 20000 = 0.009
            Assert.Greater(computer.HtfMomentum, 0, "Momentum should be positive when prices rise");
        }

        [Test]
        public void Momentum_NegativeWhenPricesFalling()
        {
            var computer = new HtfBiasComputer();

            // 10 descending closes
            for (int i = 0; i < 10; i++)
                computer.AddClose(21000.0 - i * 20.0);

            // Momentum = (20820 - 21000) / 21000 = negative
            Assert.Less(computer.HtfMomentum, 0, "Momentum should be negative when prices fall");
        }

        [Test]
        public void InsufficientHistory_StaysNeutral()
        {
            var computer = new HtfBiasComputer();

            // Only 19 bars — not enough for SMA20
            for (int i = 0; i < 19; i++)
                computer.AddClose(20000.0 + i * 50.0);  // strong uptrend

            Assert.AreEqual(MADTrend.Neutral, computer.HtfBias,
                "With < 20 bars, bias should stay Neutral regardless of price direction");
        }

        [Test]
        public void Momentum_ZeroWithFewerThan10Bars()
        {
            var computer = new HtfBiasComputer();

            for (int i = 0; i < 9; i++)
                computer.AddClose(20000.0 + i * 100.0);

            Assert.AreEqual(0.0, computer.HtfMomentum,
                "With < 10 bars, momentum should remain at default 0");
        }

        [Test]
        public void BiasTransitions_BullishToBearish()
        {
            var computer = new HtfBiasComputer();

            // First 20 bars ascending → Bullish
            for (int i = 0; i < 20; i++)
                computer.AddClose(20000.0 + i * 10.0);
            Assert.AreEqual(MADTrend.Bullish, computer.HtfBias);

            // Then 10 bars sharply descending → should transition to Bearish
            for (int i = 0; i < 10; i++)
                computer.AddClose(20000.0 - i * 20.0);

            // After adding declining bars, the SMA20 will eventually be above the close
            Assert.AreEqual(MADTrend.Bearish, computer.HtfBias,
                "Bias should transition from Bullish to Bearish on sharp decline");
        }
    }
}
