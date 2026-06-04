// MarketContextTests.cs — T20 Market Context Engine tests
using System;
using NUnit.Framework;

namespace NinjaTrader.Tests.MADConfluenceAI
{
    // Test-local type copies
    public enum TestTrend { Bullish, Bearish, Neutral }
    public enum TestSessionType { TrendDay, RotationalDay, BreakoutDay, ChopDay, Unknown }

    public sealed class TestMarketContext
    {
        public TestTrend TrendDirection;
        public double TimeModifier;
        public TestSessionType SessionType;
        public double Momentum;
    }

    public sealed class TestMarketState
    {
        public TestTrend HtfBias = TestTrend.Neutral;
        public double HtfMomentum;
        public double Atr20;
        public double SessionHigh;
        public double SessionLow;
    }

    /// <summary>
    /// Test-local context builder — mirrors BuildMarketContext logic.
    /// </summary>
    public static class TestContextBuilder
    {
        public static TestMarketContext Build(TestMarketState state, TestRegime regime, DateTime barTime)
        {
            var ctx = new TestMarketContext();
            ctx.TrendDirection = state != null ? state.HtfBias : TestTrend.Neutral;

            TimeSpan tod = barTime.TimeOfDay;
            double hours = tod.TotalHours;

            if (hours >= 9.5 && hours < 10.0)
                ctx.TimeModifier = -5;
            else if (hours >= 10.0 && hours < 11.5)
                ctx.TimeModifier = 5;
            else if (hours >= 11.5 && hours < 13.5)
                ctx.TimeModifier = -10;
            else if (hours >= 13.5 && hours < 15.0)
                ctx.TimeModifier = 3;
            else if (hours >= 15.0 && hours < 16.0)
                ctx.TimeModifier = -5;
            else
                ctx.TimeModifier = -15;

            if (state != null && state.Atr20 > 0)
            {
                double sessionRange = state.SessionHigh - state.SessionLow;
                double rangeRatio = sessionRange / state.Atr20;

                if (regime == TestRegime.Trending && rangeRatio > 1.5)
                    ctx.SessionType = TestSessionType.TrendDay;
                else if (regime == TestRegime.Ranging && rangeRatio < 0.8)
                    ctx.SessionType = TestSessionType.ChopDay;
                else if (regime == TestRegime.Volatile)
                    ctx.SessionType = TestSessionType.BreakoutDay;
                else if (regime == TestRegime.Ranging)
                    ctx.SessionType = TestSessionType.RotationalDay;
                else
                    ctx.SessionType = TestSessionType.Unknown;
            }
            else
            {
                ctx.SessionType = TestSessionType.Unknown;
            }

            ctx.Momentum = state != null ? state.HtfMomentum : 0;
            return ctx;
        }
    }

    [TestFixture]
    public class MarketContextTests
    {
        private TestMarketState _state;

        [SetUp]
        public void Setup()
        {
            _state = new TestMarketState
            {
                HtfBias = TestTrend.Bullish,
                HtfMomentum = 0.005,
                Atr20 = 20.0,
                SessionHigh = 20050,
                SessionLow = 20010
            };
        }

        [Test]
        public void MiddayChop_Modifier_MinusTen()
        {
            var barTime = new DateTime(2025, 1, 15, 12, 0, 0); // 12:00 ET
            var ctx = TestContextBuilder.Build(_state, TestRegime.Ranging, barTime);
            Assert.AreEqual(-10, ctx.TimeModifier, "Midday (11:30-13:30) modifier should be -10");
        }

        [Test]
        public void PrimeTrading_Modifier_PlusFive()
        {
            var barTime = new DateTime(2025, 1, 15, 10, 30, 0); // 10:30 ET
            var ctx = TestContextBuilder.Build(_state, TestRegime.Ranging, barTime);
            Assert.AreEqual(5, ctx.TimeModifier, "Prime trading (10:00-11:30) modifier should be +5");
        }

        [Test]
        public void ETH_Modifier_MinusFifteen()
        {
            var barTime = new DateTime(2025, 1, 15, 7, 0, 0); // 7:00 ET — outside RTH
            var ctx = TestContextBuilder.Build(_state, TestRegime.Ranging, barTime);
            Assert.AreEqual(-15, ctx.TimeModifier, "ETH modifier should be -15");
        }

        [Test]
        public void Opening_Modifier_MinusFive()
        {
            var barTime = new DateTime(2025, 1, 15, 9, 45, 0); // 9:45 ET
            var ctx = TestContextBuilder.Build(_state, TestRegime.Ranging, barTime);
            Assert.AreEqual(-5, ctx.TimeModifier, "Opening (9:30-10:00) modifier should be -5");
        }

        [Test]
        public void Afternoon_Modifier_PlusThree()
        {
            var barTime = new DateTime(2025, 1, 15, 14, 0, 0); // 14:00 ET
            var ctx = TestContextBuilder.Build(_state, TestRegime.Ranging, barTime);
            Assert.AreEqual(3, ctx.TimeModifier, "Afternoon (13:30-15:00) modifier should be +3");
        }

        [Test]
        public void Close_Modifier_MinusFive()
        {
            var barTime = new DateTime(2025, 1, 15, 15, 30, 0); // 15:30 ET
            var ctx = TestContextBuilder.Build(_state, TestRegime.Ranging, barTime);
            Assert.AreEqual(-5, ctx.TimeModifier, "Close (15:00-16:00) modifier should be -5");
        }

        [Test]
        public void TrendDirection_FromState()
        {
            var barTime = new DateTime(2025, 1, 15, 10, 30, 0);
            var ctx = TestContextBuilder.Build(_state, TestRegime.Trending, barTime);
            Assert.AreEqual(TestTrend.Bullish, ctx.TrendDirection);
        }

        [Test]
        public void SessionType_TrendDay()
        {
            _state.Atr20 = 20.0;
            _state.SessionHigh = 20100;
            _state.SessionLow = 20050; // range = 50, ratio = 2.5 > 1.5
            var barTime = new DateTime(2025, 1, 15, 10, 30, 0);
            var ctx = TestContextBuilder.Build(_state, TestRegime.Trending, barTime);
            Assert.AreEqual(TestSessionType.TrendDay, ctx.SessionType);
        }

        [Test]
        public void SessionType_ChopDay()
        {
            _state.Atr20 = 20.0;
            _state.SessionHigh = 20010;
            _state.SessionLow = 20000; // range = 10, ratio = 0.5 < 0.8
            var barTime = new DateTime(2025, 1, 15, 10, 30, 0);
            var ctx = TestContextBuilder.Build(_state, TestRegime.Ranging, barTime);
            Assert.AreEqual(TestSessionType.ChopDay, ctx.SessionType);
        }

        [Test]
        public void NullState_SafeDefaults()
        {
            var barTime = new DateTime(2025, 1, 15, 10, 30, 0);
            var ctx = TestContextBuilder.Build(null, TestRegime.Ranging, barTime);
            Assert.AreEqual(TestTrend.Neutral, ctx.TrendDirection);
            Assert.AreEqual(TestSessionType.Unknown, ctx.SessionType);
            Assert.AreEqual(0, ctx.Momentum);
        }
    }
}
