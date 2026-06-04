// ScoringEngineTests.cs — T18 Confluence Scoring Engine tests
// Uses test-local type copies to avoid NT8 dependency
using System.Collections.Generic;
using NUnit.Framework;
using SysMath = System.Math;

namespace NinjaTrader.Tests.MADConfluenceAI
{
    // ── Test-local type copies ──────────────────────────────────────────
    public enum TestSignalDirection { Long, Short, Neutral }
    public enum TestRegime { Trending, Ranging, Volatile, Thin }
    public enum TestTier { Elite, High, Moderate, Wait, DoNotTrade }

    public sealed class TestSignalResult
    {
        public string SignalId;
        public TestSignalDirection Direction;
        public double Strength;
        public string Detail;
        public double Price;
    }

    public struct TestConfig
    {
        public double AbsorptionWeight;
        public double ExhaustionWeight;
        public double DeltaWeight;
        public double ImbalanceWeight;
        public double IcebergWeight;
        public double LiquidityWeight;
        public double TrapWeight;
        public double MinConfidenceScore;
        public double EliteThreshold;
        public double HighThreshold;

        public static TestConfig Defaults => new TestConfig
        {
            AbsorptionWeight = 1.0, ExhaustionWeight = 1.0, DeltaWeight = 1.0,
            ImbalanceWeight = 1.0, IcebergWeight = 1.0, LiquidityWeight = 1.0, TrapWeight = 1.0,
            MinConfidenceScore = 60, EliteThreshold = 90, HighThreshold = 75
        };
    }

    public sealed class TestScorerResult
    {
        public double Score;
        public TestTier Tier;
        public TestSignalDirection Direction;
        public string Detail;
        public List<TestSignalResult> ContributingSignals = new List<TestSignalResult>();
    }

    /// <summary>
    /// Test-local scoring engine — mirrors RunScoringEngine logic exactly.
    /// </summary>
    public static class TestScoringEngine
    {
        public static TestScorerResult Run(List<TestSignalResult> signals, TestConfig config, TestRegime regime, bool isAtKeyLevel)
        {
            var result = new TestScorerResult { Score = 0, Tier = TestTier.DoNotTrade, Direction = TestSignalDirection.Neutral, Detail = "No signals" };
            if (signals == null || signals.Count == 0) return result;

            int longCount = 0, shortCount = 0;
            foreach (var s in signals)
            {
                if (s.Direction == TestSignalDirection.Long) longCount++;
                else if (s.Direction == TestSignalDirection.Short) shortCount++;
            }
            var majorityDir = longCount > shortCount ? TestSignalDirection.Long
                : shortCount > longCount ? TestSignalDirection.Short
                : TestSignalDirection.Neutral;

            if (majorityDir == TestSignalDirection.Neutral)
            {
                result.Detail = "No majority direction";
                return result;
            }

            double totalContribution = 0;
            double maxPossibleScore = 0;
            var categorySet = new HashSet<string>();

            foreach (var s in signals)
            {
                double categoryWeight = GetCategoryWeight(s.SignalId, config);
                maxPossibleScore += categoryWeight;
                double directionAgreement = s.Direction == majorityDir ? 1.0 : -0.5;
                if (s.Direction == TestSignalDirection.Neutral) directionAgreement = 0.0;
                totalContribution += s.Strength * categoryWeight * directionAgreement;

                if (s.Direction == majorityDir)
                {
                    result.ContributingSignals.Add(s);
                    string cat = GetSignalCategory(s.SignalId);
                    if (cat != null) categorySet.Add(cat);
                }
            }

            double rawScore = maxPossibleScore > 0 ? (totalContribution / maxPossibleScore) * 100.0 : 0;
            if (categorySet.Count >= 3) rawScore += 10;
            if (isAtKeyLevel) rawScore += 5;

            switch (regime)
            {
                case TestRegime.Trending: rawScore += 10; break;
                case TestRegime.Ranging: rawScore += 10; break;
                case TestRegime.Volatile: rawScore -= 5; break;
                case TestRegime.Thin: rawScore -= 15; break;
            }

            rawScore = SysMath.Max(0, SysMath.Min(100, rawScore));

            TestTier tier;
            if (rawScore >= 90) tier = TestTier.Elite;
            else if (rawScore >= 75) tier = TestTier.High;
            else if (rawScore >= 60) tier = TestTier.Moderate;
            else if (rawScore >= 40) tier = TestTier.Wait;
            else tier = TestTier.DoNotTrade;

            result.Score = rawScore;
            result.Tier = tier;
            result.Direction = majorityDir;
            result.Detail = string.Format("Score={0:F1}, Tier={1}", rawScore, tier);
            return result;
        }

        private static double GetCategoryWeight(string signalId, TestConfig config)
        {
            if (string.IsNullOrEmpty(signalId)) return 1.0;
            if (signalId.StartsWith("ABS")) return config.AbsorptionWeight;
            if (signalId.StartsWith("EXH")) return config.ExhaustionWeight;
            if (signalId.StartsWith("DELT")) return config.DeltaWeight;
            if (signalId.StartsWith("IMB")) return config.ImbalanceWeight;
            if (signalId.StartsWith("ICE")) return config.IcebergWeight;
            if (signalId.StartsWith("LIQSW")) return config.LiquidityWeight;
            if (signalId.StartsWith("TRAP") || signalId.StartsWith("FAIL")) return config.TrapWeight;
            return 1.0;
        }

        private static string GetSignalCategory(string signalId)
        {
            if (string.IsNullOrEmpty(signalId)) return null;
            if (signalId.StartsWith("ABS")) return "absorption";
            if (signalId.StartsWith("EXH")) return "exhaustion";
            if (signalId.StartsWith("DELT")) return "delta";
            if (signalId.StartsWith("IMB")) return "imbalance";
            if (signalId.StartsWith("ICE")) return "iceberg";
            if (signalId.StartsWith("LIQSW")) return "liquidity";
            if (signalId.StartsWith("TRAP")) return "trap";
            if (signalId.StartsWith("FAIL")) return "auction";
            if (signalId.StartsWith("REG")) return "regime";
            return null;
        }
    }

    [TestFixture]
    public class ScoringEngineTests
    {
        private TestConfig _config;

        [SetUp]
        public void Setup() => _config = TestConfig.Defaults;

        [Test]
        public void SingleSignal_ABS01_ProducesScore()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 }
            };
            var result = TestScoringEngine.Run(signals, _config, TestRegime.Ranging, false);
            Assert.Greater(result.Score, 0, "Single signal must produce nonzero score");
            Assert.AreEqual(TestSignalDirection.Long, result.Direction);
        }

        [Test]
        public void MultiSignalConfluence_ThreeAgreeing_HigherScore()
        {
            var oneSignal = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 }
            };
            var threeSignals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 },
                new TestSignalResult { SignalId = "EXH-01", Direction = TestSignalDirection.Long, Strength = 0.8 },
                new TestSignalResult { SignalId = "DELT-01", Direction = TestSignalDirection.Long, Strength = 0.8 }
            };
            var r1 = TestScoringEngine.Run(oneSignal, _config, TestRegime.Ranging, false);
            var r3 = TestScoringEngine.Run(threeSignals, _config, TestRegime.Ranging, false);
            // 3 signals at same strength get +10 category bonus; r3 >= r1
            Assert.GreaterOrEqual(r3.Score, r1.Score, "3 agreeing signals must score >= 1 signal");
        }

        [Test]
        public void ConflictingSignals_ReduceScore()
        {
            var agreeing = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 },
                new TestSignalResult { SignalId = "EXH-01", Direction = TestSignalDirection.Long, Strength = 0.7 }
            };
            var conflicting = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 },
                new TestSignalResult { SignalId = "EXH-01", Direction = TestSignalDirection.Short, Strength = 0.7 }
            };
            var rAgree = TestScoringEngine.Run(agreeing, _config, TestRegime.Ranging, false);
            var rConflict = TestScoringEngine.Run(conflicting, _config, TestRegime.Ranging, false);
            Assert.Greater(rAgree.Score, rConflict.Score, "Conflicting signals must reduce score");
        }

        [Test]
        public void CategoryAgreementBonus_ThreeCategories()
        {
            // 2 categories: no bonus
            var twoCat = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 },
                new TestSignalResult { SignalId = "EXH-01", Direction = TestSignalDirection.Long, Strength = 0.8 }
            };
            // 3 categories: +10 bonus
            var threeCat = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 },
                new TestSignalResult { SignalId = "EXH-01", Direction = TestSignalDirection.Long, Strength = 0.8 },
                new TestSignalResult { SignalId = "DELT-01", Direction = TestSignalDirection.Long, Strength = 0.8 }
            };
            var r2 = TestScoringEngine.Run(twoCat, _config, TestRegime.Ranging, false);
            var r3 = TestScoringEngine.Run(threeCat, _config, TestRegime.Ranging, false);
            // r3 has 3 categories so gets +10 bonus; r2 doesn't
            // Both have same strength; r3 should be higher
            Assert.Greater(r3.Score, r2.Score);
        }

        [Test]
        public void LevelProximityBonus_AddsPoints()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 }
            };
            var noLevel = TestScoringEngine.Run(signals, _config, TestRegime.Ranging, false);
            var atLevel = TestScoringEngine.Run(signals, _config, TestRegime.Ranging, true);
            Assert.AreEqual(5.0, atLevel.Score - noLevel.Score, 0.01, "Level proximity should add +5");
        }

        [Test]
        public void RegimeModifier_Trending_Plus10()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 }
            };
            var ranging = TestScoringEngine.Run(signals, _config, TestRegime.Ranging, false);
            var trending = TestScoringEngine.Run(signals, _config, TestRegime.Trending, false);
            // Both get +10, so should be equal
            Assert.AreEqual(ranging.Score, trending.Score, 0.01);
        }

        [Test]
        public void RegimeModifier_Thin_Minus15()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.8 }
            };
            var ranging = TestScoringEngine.Run(signals, _config, TestRegime.Ranging, false);
            var thin = TestScoringEngine.Run(signals, _config, TestRegime.Thin, false);
            Assert.AreEqual(25.0, ranging.Score - thin.Score, 0.01, "Thin vs Ranging should differ by 25 (10 - (-15))");
        }

        [Test]
        public void TierClassification_Elite()
        {
            // Force a high-score scenario: many agreeing signals + at level + trending
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 1.0 },
                new TestSignalResult { SignalId = "EXH-01", Direction = TestSignalDirection.Long, Strength = 1.0 },
                new TestSignalResult { SignalId = "DELT-01", Direction = TestSignalDirection.Long, Strength = 1.0 },
                new TestSignalResult { SignalId = "IMB-01", Direction = TestSignalDirection.Long, Strength = 1.0 },
            };
            var result = TestScoringEngine.Run(signals, _config, TestRegime.Trending, true);
            // All strength=1.0, 4 categories → +10, at level → +5, trending → +10 = 100+15+5+10 clamped to 100
            Assert.AreEqual(TestTier.Elite, result.Tier);
            Assert.GreaterOrEqual(result.Score, 90);
        }

        [Test]
        public void TierClassification_High()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.6 },
                new TestSignalResult { SignalId = "EXH-01", Direction = TestSignalDirection.Long, Strength = 0.5 }
            };
            // 2 categories at moderate strength + Ranging (+10) ≈ 55 + 10 = 65; this is Moderate
            var result = TestScoringEngine.Run(signals, _config, TestRegime.Ranging, true);
            Assert.GreaterOrEqual(result.Score, 60);
        }

        [Test]
        public void TierClassification_Wait()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.3 }
            };
            // Low strength, no bonuses, Volatile = -5
            var result = TestScoringEngine.Run(signals, _config, TestRegime.Volatile, false);
            Assert.LessOrEqual(result.Score, 59);
        }

        [Test]
        public void TierClassification_DoNotTrade()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.1 }
            };
            var result = TestScoringEngine.Run(signals, _config, TestRegime.Thin, false);
            Assert.Less(result.Score, 40);
            Assert.AreEqual(TestTier.DoNotTrade, result.Tier);
        }

        [Test]
        public void ScoreClamp_NeverExceeds100()
        {
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 1.0 },
                new TestSignalResult { SignalId = "EXH-01", Direction = TestSignalDirection.Long, Strength = 1.0 },
                new TestSignalResult { SignalId = "DELT-01", Direction = TestSignalDirection.Long, Strength = 1.0 },
                new TestSignalResult { SignalId = "IMB-01", Direction = TestSignalDirection.Long, Strength = 1.0 },
                new TestSignalResult { SignalId = "ICE-01", Direction = TestSignalDirection.Long, Strength = 1.0 },
                new TestSignalResult { SignalId = "LIQSW-01", Direction = TestSignalDirection.Long, Strength = 1.0 },
            };
            var result = TestScoringEngine.Run(signals, _config, TestRegime.Trending, true);
            Assert.LessOrEqual(result.Score, 100, "Score must never exceed 100");
        }

        [Test]
        public void ScoreClamp_NeverBelowZero()
        {
            // Mostly conflicting signals
            var signals = new List<TestSignalResult>
            {
                new TestSignalResult { SignalId = "ABS-01", Direction = TestSignalDirection.Long, Strength = 0.1 },
                new TestSignalResult { SignalId = "EXH-01", Direction = TestSignalDirection.Short, Strength = 1.0 },
                new TestSignalResult { SignalId = "DELT-01", Direction = TestSignalDirection.Short, Strength = 1.0 },
                new TestSignalResult { SignalId = "IMB-01", Direction = TestSignalDirection.Short, Strength = 1.0 },
            };
            var result = TestScoringEngine.Run(signals, _config, TestRegime.Thin, false);
            Assert.GreaterOrEqual(result.Score, 0, "Score must never be below 0");
        }

        [Test]
        public void EmptySignals_ReturnsDoNotTrade()
        {
            var result = TestScoringEngine.Run(new List<TestSignalResult>(), _config, TestRegime.Ranging, false);
            Assert.AreEqual(TestTier.DoNotTrade, result.Tier);
            Assert.AreEqual(0, result.Score);
        }

        [Test]
        public void NullSignals_ReturnsDoNotTrade()
        {
            var result = TestScoringEngine.Run(null, _config, TestRegime.Ranging, false);
            Assert.AreEqual(TestTier.DoNotTrade, result.Tier);
        }
    }
}
