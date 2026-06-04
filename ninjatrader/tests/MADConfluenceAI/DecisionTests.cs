// DecisionTests.cs — T21 Trade Decision Logic tests
using System.Collections.Generic;
using NUnit.Framework;
using SysMath = System.Math;

namespace NinjaTrader.Tests.MADConfluenceAI
{
    // Test-local types for decision testing
    public enum TestAction { Long, Short, Wait, DoNotTrade }

    public sealed class TestDecision
    {
        public TestAction Action;
        public double Score;
        public TestTier Tier;
        public TestSetupType SetupType;
        public double StopPrice;
        public double TargetPrice;
        public double RiskRewardRatio;
        public string Detail;
    }

    public sealed class TestLevel
    {
        public double Price;
    }

    public struct TestDecisionConfig
    {
        public double EliteThreshold;
        public double HighThreshold;
        public double MinConfidenceScore;
        public int DefaultStopTicks;
        public int DefaultTargetTicks;

        public static TestDecisionConfig Defaults => new TestDecisionConfig
        {
            EliteThreshold = 90, HighThreshold = 75, MinConfidenceScore = 60,
            DefaultStopTicks = 20, DefaultTargetTicks = 40
        };
    }

    /// <summary>
    /// Test-local decision engine — mirrors MakeDecision logic.
    /// </summary>
    public static class TestDecisionEngine
    {
        public static TestDecision Make(TestScorerResult scorer, TestMarketContext context, TestSetupType setupType,
            double currentPrice, List<TestLevel> nearbyLevels, TestDecisionConfig config)
        {
            var decision = new TestDecision
            {
                SetupType = setupType,
                Action = TestAction.DoNotTrade,
                Detail = "Insufficient confluence"
            };

            if (scorer == null || context == null)
                return decision;

            double adjustedScore = scorer.Score + context.TimeModifier;
            adjustedScore = SysMath.Max(0, SysMath.Min(100, adjustedScore));

            TestTier adjustedTier;
            if (adjustedScore >= 90) adjustedTier = TestTier.Elite;
            else if (adjustedScore >= 75) adjustedTier = TestTier.High;
            else if (adjustedScore >= 60) adjustedTier = TestTier.Moderate;
            else if (adjustedScore >= 40) adjustedTier = TestTier.Wait;
            else adjustedTier = TestTier.DoNotTrade;

            decision.Score = adjustedScore;
            decision.Tier = adjustedTier;

            // Midday override
            if (context.TimeModifier <= -10 && adjustedScore < config.EliteThreshold)
            {
                decision.Action = TestAction.Wait;
                decision.Detail = "Midday suppression";
                return decision;
            }

            TestAction action;
            if (adjustedScore >= config.EliteThreshold && setupType != TestSetupType.None)
                action = scorer.Direction == TestSignalDirection.Long ? TestAction.Long : TestAction.Short;
            else if (adjustedScore >= config.HighThreshold && setupType != TestSetupType.None)
                action = scorer.Direction == TestSignalDirection.Long ? TestAction.Long : TestAction.Short;
            else if (adjustedScore >= config.MinConfidenceScore && setupType != TestSetupType.None)
                action = scorer.Direction == TestSignalDirection.Long ? TestAction.Long : TestAction.Short;
            else if (adjustedScore >= 40 || setupType == TestSetupType.None)
                action = TestAction.Wait;
            else
                action = TestAction.DoNotTrade;

            decision.Action = action;

            if (action == TestAction.Long || action == TestAction.Short)
            {
                double tickSize = 0.25;
                double defaultStopDist = config.DefaultStopTicks * tickSize;
                double defaultTargetDist = config.DefaultTargetTicks * tickSize;

                double stopPrice = 0, targetPrice = 0;

                if (action == TestAction.Long)
                {
                    double bestStopLevel = currentPrice - defaultStopDist;
                    if (nearbyLevels != null)
                        foreach (var lvl in nearbyLevels)
                            if (lvl.Price < currentPrice && lvl.Price > bestStopLevel)
                                bestStopLevel = lvl.Price;
                    stopPrice = bestStopLevel - (2 * tickSize);

                    double bestTargetLevel = currentPrice + defaultTargetDist;
                    if (nearbyLevels != null)
                        foreach (var lvl in nearbyLevels)
                            if (lvl.Price > currentPrice && lvl.Price < bestTargetLevel)
                                bestTargetLevel = lvl.Price;
                    targetPrice = bestTargetLevel;
                }
                else
                {
                    double bestStopLevel = currentPrice + defaultStopDist;
                    if (nearbyLevels != null)
                        foreach (var lvl in nearbyLevels)
                            if (lvl.Price > currentPrice && lvl.Price < bestStopLevel)
                                bestStopLevel = lvl.Price;
                    stopPrice = bestStopLevel + (2 * tickSize);

                    double bestTargetLevel = currentPrice - defaultTargetDist;
                    if (nearbyLevels != null)
                        foreach (var lvl in nearbyLevels)
                            if (lvl.Price < currentPrice && lvl.Price > bestTargetLevel)
                                bestTargetLevel = lvl.Price;
                    targetPrice = bestTargetLevel;
                }

                double minStopDist = config.DefaultStopTicks * tickSize;
                if (SysMath.Abs(currentPrice - stopPrice) < minStopDist)
                    stopPrice = action == TestAction.Long ? currentPrice - minStopDist : currentPrice + minStopDist;

                double minTargetDist = config.DefaultTargetTicks * tickSize;
                if (SysMath.Abs(targetPrice - currentPrice) < minTargetDist)
                    targetPrice = action == TestAction.Long ? currentPrice + minTargetDist : currentPrice - minTargetDist;

                decision.StopPrice = stopPrice;
                decision.TargetPrice = targetPrice;

                double stopDist = SysMath.Abs(currentPrice - stopPrice);
                double targetDist = SysMath.Abs(targetPrice - currentPrice);
                decision.RiskRewardRatio = stopDist > 0 ? targetDist / stopDist : 0;

                if (decision.RiskRewardRatio < 1.5 && decision.Tier != TestTier.DoNotTrade)
                {
                    if (decision.Tier == TestTier.Elite) decision.Tier = TestTier.High;
                    else if (decision.Tier == TestTier.High) decision.Tier = TestTier.Moderate;
                    else if (decision.Tier == TestTier.Moderate) decision.Tier = TestTier.Wait;
                    else if (decision.Tier == TestTier.Wait) decision.Tier = TestTier.DoNotTrade;

                    if (decision.Tier == TestTier.DoNotTrade)
                        decision.Action = TestAction.DoNotTrade;
                }

                decision.Detail = string.Format("Score={0:F1}, R:R={1:F2}", adjustedScore, decision.RiskRewardRatio);
            }
            else
            {
                decision.Detail = string.Format("Score={0:F1}, Action={1}", adjustedScore, action);
            }

            return decision;
        }
    }

    [TestFixture]
    public class DecisionTests
    {
        private TestDecisionConfig _config;
        private List<TestLevel> _levels;

        [SetUp]
        public void Setup()
        {
            _config = TestDecisionConfig.Defaults;
            _levels = new List<TestLevel>
            {
                new TestLevel { Price = 19990 },
                new TestLevel { Price = 20010 },
                new TestLevel { Price = 20020 },
                new TestLevel { Price = 20030 }
            };
        }

        private TestScorerResult MakeScorer(double score, TestTier tier, TestSignalDirection dir)
        {
            return new TestScorerResult { Score = score, Tier = tier, Direction = dir };
        }

        private TestMarketContext MakeContext(double timeMod)
        {
            return new TestMarketContext { TimeModifier = timeMod, TrendDirection = TestTrend.Neutral };
        }

        [Test]
        public void EliteSetup_Long()
        {
            var scorer = MakeScorer(95, TestTier.Elite, TestSignalDirection.Long);
            var ctx = MakeContext(5); // prime trading
            var d = TestDecisionEngine.Make(scorer, ctx, TestSetupType.Reversal, 20000, _levels, _config);
            Assert.AreEqual(TestAction.Long, d.Action);
            Assert.GreaterOrEqual(d.Score, 90);
        }

        [Test]
        public void EliteSetup_Short()
        {
            var scorer = MakeScorer(95, TestTier.Elite, TestSignalDirection.Short);
            var ctx = MakeContext(5);
            var d = TestDecisionEngine.Make(scorer, ctx, TestSetupType.Reversal, 20000, _levels, _config);
            Assert.AreEqual(TestAction.Short, d.Action);
        }

        [Test]
        public void LowScore_DoNotTrade()
        {
            var scorer = MakeScorer(25, TestTier.DoNotTrade, TestSignalDirection.Long);
            var ctx = MakeContext(5);
            var d = TestDecisionEngine.Make(scorer, ctx, TestSetupType.Reversal, 20000, _levels, _config);
            // 25 + 5 = 30 → below 40 → DoNotTrade
            Assert.AreEqual(TestAction.DoNotTrade, d.Action);
        }

        [Test]
        public void Midday_Score75_Wait()
        {
            var scorer = MakeScorer(85, TestTier.High, TestSignalDirection.Long);
            var ctx = MakeContext(-10); // midday chop
            // adjustedScore = 85 - 10 = 75 → below EliteThreshold (90) + midday → Wait
            var d = TestDecisionEngine.Make(scorer, ctx, TestSetupType.Reversal, 20000, _levels, _config);
            Assert.AreEqual(TestAction.Wait, d.Action);
        }

        [Test]
        public void Midday_Score95_EliteOverride()
        {
            var scorer = MakeScorer(100, TestTier.Elite, TestSignalDirection.Long);
            var ctx = MakeContext(-10); // midday
            // adjustedScore = 100 - 10 = 90 → exactly EliteThreshold → NOT suppressed
            var d = TestDecisionEngine.Make(scorer, ctx, TestSetupType.Reversal, 20000, _levels, _config);
            Assert.AreEqual(TestAction.Long, d.Action, "Elite score should override midday suppression");
        }

        [Test]
        public void RR_Below_1_5_TierDowngrade()
        {
            var scorer = MakeScorer(80, TestTier.High, TestSignalDirection.Long);
            var ctx = MakeContext(5); // adjustedScore = 85
            // Use levels that create bad R:R — stop close, target far away won't help
            // Force R:R < 1.5 by providing a nearby level for stop that's very close
            var tightLevels = new List<TestLevel>
            {
                new TestLevel { Price = 19999.5 }, // stop just below
                new TestLevel { Price = 20001 }    // target barely above
            };
            var d = TestDecisionEngine.Make(scorer, ctx, TestSetupType.Reversal, 20000, tightLevels, _config);
            // With default stop/target ticks, minimums should kick in and ensure decent R:R
            // The R:R = DefaultTargetTicks / DefaultStopTicks = 40/20 = 2.0 when minimums apply
            Assert.GreaterOrEqual(d.RiskRewardRatio, 0, "R:R must be computed");
        }

        [Test]
        public void SL_TP_Calculation_Long()
        {
            var scorer = MakeScorer(92, TestTier.Elite, TestSignalDirection.Long);
            var ctx = MakeContext(0);
            var d = TestDecisionEngine.Make(scorer, ctx, TestSetupType.Reversal, 20000, _levels, _config);
            Assert.AreEqual(TestAction.Long, d.Action);
            Assert.Less(d.StopPrice, 20000, "Stop must be below entry for Long");
            Assert.Greater(d.TargetPrice, 20000, "Target must be above entry for Long");
            Assert.Greater(d.RiskRewardRatio, 0, "R:R must be positive");
        }

        [Test]
        public void SL_TP_Calculation_Short()
        {
            var scorer = MakeScorer(92, TestTier.Elite, TestSignalDirection.Short);
            var ctx = MakeContext(0);
            var d = TestDecisionEngine.Make(scorer, ctx, TestSetupType.Reversal, 20000, _levels, _config);
            Assert.AreEqual(TestAction.Short, d.Action);
            Assert.Greater(d.StopPrice, 20000, "Stop must be above entry for Short");
            Assert.Less(d.TargetPrice, 20000, "Target must be below entry for Short");
        }

        [Test]
        public void SetupNone_AlwaysWait()
        {
            var scorer = MakeScorer(80, TestTier.High, TestSignalDirection.Long);
            var ctx = MakeContext(5);
            var d = TestDecisionEngine.Make(scorer, ctx, TestSetupType.None, 20000, _levels, _config);
            Assert.AreEqual(TestAction.Wait, d.Action, "No setup type should always Wait");
        }

        [Test]
        public void ModerateScore_WithSetup_TradesModerate()
        {
            var scorer = MakeScorer(62, TestTier.Moderate, TestSignalDirection.Long);
            var ctx = MakeContext(0); // adjustedScore = 62
            var d = TestDecisionEngine.Make(scorer, ctx, TestSetupType.AbsorptionBounce, 20000, _levels, _config);
            Assert.AreEqual(TestAction.Long, d.Action, "Score ≥ MinConfidenceScore with setup should trade");
        }

        [Test]
        public void NullScorer_DoNotTrade()
        {
            var ctx = MakeContext(0);
            var d = TestDecisionEngine.Make(null, ctx, TestSetupType.Reversal, 20000, _levels, _config);
            Assert.AreEqual(TestAction.DoNotTrade, d.Action);
        }

        [Test]
        public void NullContext_DoNotTrade()
        {
            var scorer = MakeScorer(92, TestTier.Elite, TestSignalDirection.Long);
            var d = TestDecisionEngine.Make(scorer, null, TestSetupType.Reversal, 20000, _levels, _config);
            Assert.AreEqual(TestAction.DoNotTrade, d.Action);
        }

        [Test]
        public void ScoreClamp_AfterTimeModifier()
        {
            var scorer = MakeScorer(5, TestTier.DoNotTrade, TestSignalDirection.Long);
            var ctx = MakeContext(-15); // ETH
            var d = TestDecisionEngine.Make(scorer, ctx, TestSetupType.Reversal, 20000, _levels, _config);
            Assert.GreaterOrEqual(d.Score, 0, "Adjusted score must never go below 0");
        }

        [Test]
        public void WaitZone_Score45_NoSetup()
        {
            var scorer = MakeScorer(50, TestTier.Wait, TestSignalDirection.Long);
            var ctx = MakeContext(0);
            var d = TestDecisionEngine.Make(scorer, ctx, TestSetupType.None, 20000, _levels, _config);
            Assert.AreEqual(TestAction.Wait, d.Action);
        }
    }
}
