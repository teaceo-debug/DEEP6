// DEEP6DepthRadarV2Tests: comprehensive unit tests for Phase A logic.
//
// Tests cover:
//   - L2LevelStateV2 default field values and enum values
//   - ComputeSpoofScore component scoring (cancellation, time-in-book, size, distance, mod frequency)
//   - ComputeFreshnessScore decay and penalty factors
//   - ClassifyWall priority chain (SPOOF > STALE > ICEBERG > GENUINE > UNKNOWN)
//   - ML override behavior

using System;
using NUnit.Framework;
using NinjaTrader.NinjaScript.Indicators.DEEP6;

namespace NinjaTrader.Tests.Indicators
{
    [TestFixture]
    public class L2LevelStateV2Tests
    {
        [Test]
        public void DefaultFields_HaveExpectedValues()
        {
            var st = new L2LevelStateV2();
            Assert.That(st.CurrentSize, Is.EqualTo(0));
            Assert.That(st.MaxSize, Is.EqualTo(0));
            Assert.That(st.RefillCount, Is.EqualTo(0));
            Assert.That(st.ModificationCount, Is.EqualTo(0));
            Assert.That(st.OriginalSize, Is.EqualTo(0));
            Assert.That(st.CancellationEvents, Is.EqualTo(0));
            Assert.That(st.Classification, Is.EqualTo(WallClassification.Unknown));
            Assert.That(st.Confidence, Is.EqualTo(0f));
            Assert.That(st.FreshnessScore, Is.EqualTo(1f));
            Assert.That(st.SpoofScore, Is.EqualTo(0f));
            Assert.That(st.PriceTradedThrough, Is.False);
            Assert.That(st.IsMLClassified, Is.False);
        }

        [Test]
        public void WallClassification_EnumValues_AreCorrect()
        {
            Assert.That((int)WallClassification.Unknown, Is.EqualTo(0));
            Assert.That((int)WallClassification.Genuine, Is.EqualTo(1));
            Assert.That((int)WallClassification.Spoof, Is.EqualTo(2));
            Assert.That((int)WallClassification.Iceberg, Is.EqualTo(3));
            Assert.That((int)WallClassification.Stale, Is.EqualTo(4));
        }
    }

    [TestFixture]
    public class ComputeSpoofScoreTests
    {
        private static readonly DateTime BaseTime = new DateTime(2026, 1, 15, 12, 0, 0, DateTimeKind.Utc);

        [Test]
        public void KnownSpoofPattern_HighCancelShortTime_ScoreAbove70()
        {
            var st = new L2LevelStateV2
            {
                CancellationEvents = 20,
                FirstSeenTime = BaseTime.AddMilliseconds(-800),
                MaxSize = 500,
                ModificationCount = 30
            };
            double avgWallSize = 100.0;
            double ticksFromBBO = 8.0;

            float score = DepthRadarV2Logic.ComputeSpoofScore(st, avgWallSize, ticksFromBBO, BaseTime);
            Assert.That(score, Is.GreaterThanOrEqualTo(70f),
                "High cancel ratio + short time-in-book + large size + far distance should score >= 70");
        }

        [Test]
        public void GenuinePattern_NoCancels_ScoreBelow40()
        {
            var st = new L2LevelStateV2
            {
                CancellationEvents = 0,
                FirstSeenTime = BaseTime.AddMinutes(-5),
                MaxSize = 80,
                ModificationCount = 0
            };
            double avgWallSize = 100.0;
            double ticksFromBBO = 1.0;

            float score = DepthRadarV2Logic.ComputeSpoofScore(st, avgWallSize, ticksFromBBO, BaseTime);
            Assert.That(score, Is.LessThan(40f),
                "No cancellations + long time-in-book + normal size should score < 40");
        }

        [Test]
        public void CancellationComponent_HighRatio_Caps40()
        {
            // cancelRatio = 50/(50+1) = 0.98 -> cancellationScore = min(40, (0.98/0.95)*40) = 40
            var st = new L2LevelStateV2
            {
                CancellationEvents = 50,
                FirstSeenTime = BaseTime.AddMinutes(-10),
                MaxSize = 100,
                ModificationCount = 0
            };
            float score = DepthRadarV2Logic.ComputeSpoofScore(st, 100.0, 0.0, BaseTime);
            // With 50 cancels, cancel component alone should be near 40
            // timeInBook component: firstSeen 10min ago = 600000ms, (600000-500)/4500 >> 1 => 25*(1 - large) = 0
            // No size anomaly (ratio=1), no distance, no mod rate
            Assert.That(score, Is.InRange(38f, 42f),
                "50 cancellations should yield cancellation component near 40");
        }

        [Test]
        public void TimeInBookComponent_ShortTime_Max25()
        {
            // firstSeen 500ms ago: timeInBook=500ms, (500-500)/4500=0, score=25*(1-0)=25
            var st = new L2LevelStateV2
            {
                CancellationEvents = 1,
                FirstSeenTime = BaseTime.AddMilliseconds(-500),
                MaxSize = 100,
                ModificationCount = 0
            };
            float score = DepthRadarV2Logic.ComputeSpoofScore(st, 100.0, 0.0, BaseTime);
            // cancelRatio = 1/2 = 0.5 -> cancellationScore = (0.5/0.95)*40 = ~21.05
            // timeInBook = 500ms -> timeInBookScore = 25*(1 - 0) = 25
            // total should be around 21 + 25 = 46
            Assert.That(score, Is.GreaterThan(40f),
                "Short time-in-book with cancellation should contribute ~25 points");
        }

        [Test]
        public void TimeInBookComponent_NoCancels_IsZero()
        {
            var st = new L2LevelStateV2
            {
                CancellationEvents = 0,
                FirstSeenTime = BaseTime.AddMilliseconds(-500),
                MaxSize = 100,
                ModificationCount = 0
            };
            float score = DepthRadarV2Logic.ComputeSpoofScore(st, 100.0, 0.0, BaseTime);
            // No cancels -> cancelRatio=0, cancellationScore=0, timeInBookScore=0
            Assert.That(score, Is.LessThanOrEqualTo(5f),
                "No cancellation events means time-in-book component is skipped");
        }

        [Test]
        public void SizeAnomalyComponent_5xAvg_Max20()
        {
            var st = new L2LevelStateV2
            {
                CancellationEvents = 0,
                FirstSeenTime = BaseTime.AddMinutes(-5),
                MaxSize = 500,
                ModificationCount = 0
            };
            // sizeRatio = 500/100 = 5.0, (5-1)/4 * 20 = 20
            float score = DepthRadarV2Logic.ComputeSpoofScore(st, 100.0, 0.0, BaseTime);
            Assert.That(score, Is.InRange(18f, 22f),
                "5x average size should yield size anomaly component near 20");
        }

        [Test]
        public void DistanceComponent_10Ticks_Max10()
        {
            var st = new L2LevelStateV2
            {
                CancellationEvents = 0,
                FirstSeenTime = BaseTime.AddMinutes(-5),
                MaxSize = 100,
                ModificationCount = 0
            };
            float score = DepthRadarV2Logic.ComputeSpoofScore(st, 100.0, 10.0, BaseTime);
            // distanceScore = min(10, (10/10)*10) = 10
            Assert.That(score, Is.InRange(8f, 12f),
                "10 ticks from BBO should yield distance component of 10");
        }

        [Test]
        public void ModFrequencyComponent_HighRate_Max5()
        {
            var st = new L2LevelStateV2
            {
                CancellationEvents = 0,
                FirstSeenTime = BaseTime.AddSeconds(-1),
                MaxSize = 100,
                ModificationCount = 20
            };
            // elapsed = 1s, modRate = 20/1 = 20, modScore = min(5, (20/10)*5) = 5
            float score = DepthRadarV2Logic.ComputeSpoofScore(st, 100.0, 0.0, BaseTime);
            Assert.That(score, Is.InRange(3f, 7f),
                "20 modifications in 1 second should yield mod component near 5");
        }
    }

    [TestFixture]
    public class ComputeFreshnessScoreTests
    {
        private static readonly DateTime BaseTime = new DateTime(2026, 1, 15, 12, 0, 0, DateTimeKind.Utc);

        [Test]
        public void FreshWall_JustUpdated_ScoreAbove085()
        {
            var st = new L2LevelStateV2
            {
                LastUpdate = BaseTime,
                PriceTradedThrough = false,
                ModificationCount = 0
            };
            float score = DepthRadarV2Logic.ComputeFreshnessScore(st, 0.0, BaseTime);
            Assert.That(score, Is.GreaterThan(0.85f),
                "Just-updated wall with no cross and no mods should have freshness > 0.85");
        }

        [Test]
        public void FreshWall_ZeroTicksFromBBO_ScoreIs1()
        {
            var st = new L2LevelStateV2
            {
                LastUpdate = BaseTime,
                PriceTradedThrough = false,
                ModificationCount = 0
            };
            float score = DepthRadarV2Logic.ComputeFreshnessScore(st, 0.0, BaseTime);
            Assert.That(score, Is.InRange(0.99f, 1.0f),
                "Perfect conditions should yield freshness near 1.0");
        }

        [Test]
        public void PriceCrossed_20sAgo_DecaysSignificantly()
        {
            var st = new L2LevelStateV2
            {
                LastUpdate = BaseTime,
                PriceTradedThrough = true,
                PriceCrossTime = BaseTime.AddSeconds(-20),
                ModificationCount = 0
            };
            float score = DepthRadarV2Logic.ComputeFreshnessScore(st, 0.0, BaseTime);
            // priceCrossPenalty = exp(-0.1 * 20) = exp(-2) ~ 0.135
            Assert.That(score, Is.LessThan(0.2f),
                "Price crossed 20s ago should cause major freshness decay via exp(-2)");
        }

        [Test]
        public void StaleWall_OldUpdate_ManyMods_NearZero()
        {
            var st = new L2LevelStateV2
            {
                LastUpdate = BaseTime.AddMinutes(-60),
                PriceTradedThrough = true,
                PriceCrossTime = BaseTime.AddMinutes(-30),
                ModificationCount = 50
            };
            float score = DepthRadarV2Logic.ComputeFreshnessScore(st, 5.0, BaseTime);
            Assert.That(score, Is.LessThan(0.05f),
                "Old update + price cross + many mods should yield freshness near 0");
        }

        [Test]
        public void TimeDecay_5MinOld_ModerateDecay()
        {
            var st = new L2LevelStateV2
            {
                LastUpdate = BaseTime.AddMinutes(-5),
                PriceTradedThrough = false,
                ModificationCount = 0
            };
            float score = DepthRadarV2Logic.ComputeFreshnessScore(st, 0.0, BaseTime);
            // timeDecay = exp(-0.02 * 5) = exp(-0.1) ~ 0.905
            Assert.That(score, Is.InRange(0.85f, 0.95f),
                "5 minutes old with no other penalties should have moderate time decay");
        }

        [Test]
        public void ModPenalty_10Mods_ReducesFreshness()
        {
            var st = new L2LevelStateV2
            {
                LastUpdate = BaseTime,
                PriceTradedThrough = false,
                ModificationCount = 10
            };
            float score = DepthRadarV2Logic.ComputeFreshnessScore(st, 0.0, BaseTime);
            // modPenalty = exp(-0.05 * 10) = exp(-0.5) ~ 0.607
            Assert.That(score, Is.InRange(0.55f, 0.65f),
                "10 modifications should reduce freshness via exp(-0.5) penalty");
        }

        [Test]
        public void DistancePenalty_20Ticks_ReducesFreshness()
        {
            var st = new L2LevelStateV2
            {
                LastUpdate = BaseTime,
                PriceTradedThrough = false,
                ModificationCount = 0
            };
            float score = DepthRadarV2Logic.ComputeFreshnessScore(st, 20.0, BaseTime);
            // distancePenalty = 1 / (1 + 0.05 * 20) = 1/2 = 0.5
            Assert.That(score, Is.InRange(0.45f, 0.55f),
                "20 ticks from BBO should halve freshness via distance penalty");
        }
    }

    [TestFixture]
    public class ClassifyWallTests
    {
        private static readonly DateTime BaseTime = new DateTime(2026, 1, 15, 12, 0, 0, DateTimeKind.Utc);
        private const int WallMinSize = 50;

        [Test]
        public void SpoofBeatsIceberg_HighSpoofScore_ClassifiesAsSpoof()
        {
            var st = new L2LevelStateV2
            {
                SpoofScore = 75f,
                FreshnessScore = 0.8f,
                RefillCount = 3,
                MaxSize = 100
            };
            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);
            Assert.That(st.Classification, Is.EqualTo(WallClassification.Spoof),
                "SpoofScore >= 70 should classify as Spoof even with high refill count");
            Assert.That(st.Confidence, Is.EqualTo(0.75f).Within(0.01f),
                "Spoof confidence should be SpoofScore / 100");
        }

        [Test]
        public void StaleBeatsIceberg_LowFreshness_ClassifiesAsStale()
        {
            var st = new L2LevelStateV2
            {
                SpoofScore = 30f,
                FreshnessScore = 0.05f,
                RefillCount = 3,
                MaxSize = 100
            };
            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);
            Assert.That(st.Classification, Is.EqualTo(WallClassification.Stale),
                "FreshnessScore < 0.1 should classify as Stale even with high refill count");
            Assert.That(st.Confidence, Is.EqualTo(0.95f).Within(0.01f),
                "Stale confidence should be 1 - FreshnessScore");
        }

        [Test]
        public void IcebergBeatsGenuine_HighRefills_ClassifiesAsIceberg()
        {
            var st = new L2LevelStateV2
            {
                SpoofScore = 30f,
                FreshnessScore = 0.8f,
                RefillCount = 3,
                MaxSize = 100
            };
            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);
            Assert.That(st.Classification, Is.EqualTo(WallClassification.Iceberg),
                "RefillCount >= 2 with no spoof/stale flags should classify as Iceberg");
            Assert.That(st.Confidence, Is.EqualTo(0.6f).Within(0.01f),
                "Iceberg confidence should be min(1, RefillCount * 0.2) = 0.6");
        }

        [Test]
        public void Genuine_NoFlags_GoodFreshness_ClassifiesAsGenuine()
        {
            var st = new L2LevelStateV2
            {
                SpoofScore = 20f,
                FreshnessScore = 0.9f,
                RefillCount = 0,
                MaxSize = 100
            };
            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);
            Assert.That(st.Classification, Is.EqualTo(WallClassification.Genuine),
                "MaxSize >= WallMinSize with no other flags should classify as Genuine");
            Assert.That(st.Confidence, Is.EqualTo(0.9f).Within(0.01f),
                "Genuine confidence should equal FreshnessScore");
        }

        [Test]
        public void Unknown_SmallWall_ClassifiesAsUnknown()
        {
            var st = new L2LevelStateV2
            {
                SpoofScore = 10f,
                FreshnessScore = 0.9f,
                RefillCount = 0,
                MaxSize = 30
            };
            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);
            Assert.That(st.Classification, Is.EqualTo(WallClassification.Unknown),
                "MaxSize < WallMinSize with no spoof/stale/iceberg flags should be Unknown");
            Assert.That(st.Confidence, Is.EqualTo(0f),
                "Unknown classification should have zero confidence");
        }

        [Test]
        public void MLOverride_PreservesExistingClassification()
        {
            var st = new L2LevelStateV2
            {
                IsMLClassified = true,
                Classification = WallClassification.Iceberg,
                Confidence = 0.95f,
                SpoofScore = 80f,
                FreshnessScore = 0.5f,
                RefillCount = 0,
                MaxSize = 100
            };
            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);
            Assert.That(st.Classification, Is.EqualTo(WallClassification.Iceberg),
                "IsMLClassified=true should prevent rule-based classification override");
            Assert.That(st.Confidence, Is.EqualTo(0.95f),
                "ML-classified confidence should not be overwritten");
        }

        [Test]
        public void SpoofBoundary_Exactly70_ClassifiesAsSpoof()
        {
            var st = new L2LevelStateV2
            {
                SpoofScore = 70f,
                FreshnessScore = 0.8f,
                RefillCount = 0,
                MaxSize = 100
            };
            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);
            Assert.That(st.Classification, Is.EqualTo(WallClassification.Spoof),
                "SpoofScore exactly 70 should classify as Spoof (>= threshold)");
        }

        [Test]
        public void SpoofBoundary_69_DoesNotClassifyAsSpoof()
        {
            var st = new L2LevelStateV2
            {
                SpoofScore = 69f,
                FreshnessScore = 0.8f,
                RefillCount = 0,
                MaxSize = 100
            };
            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);
            Assert.That(st.Classification, Is.Not.EqualTo(WallClassification.Spoof),
                "SpoofScore 69 should NOT classify as Spoof (below 70 threshold)");
        }

        [Test]
        public void FreshnessBoundary_Exactly01_IsNotStale()
        {
            var st = new L2LevelStateV2
            {
                SpoofScore = 10f,
                FreshnessScore = 0.1f,
                RefillCount = 0,
                MaxSize = 100
            };
            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);
            Assert.That(st.Classification, Is.Not.EqualTo(WallClassification.Stale),
                "FreshnessScore exactly 0.1 should NOT classify as Stale (threshold is < 0.1)");
        }

        [Test]
        public void IcebergBoundary_1Refill_NotIceberg()
        {
            var st = new L2LevelStateV2
            {
                SpoofScore = 10f,
                FreshnessScore = 0.8f,
                RefillCount = 1,
                MaxSize = 100
            };
            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);
            Assert.That(st.Classification, Is.Not.EqualTo(WallClassification.Iceberg),
                "RefillCount 1 should NOT classify as Iceberg (threshold is >= 2)");
            Assert.That(st.Classification, Is.EqualTo(WallClassification.Genuine),
                "With MaxSize >= WallMinSize and no flags, should fall through to Genuine");
        }

        [Test]
        public void ClassifyWall_SetsLastClassificationTime()
        {
            var st = new L2LevelStateV2
            {
                SpoofScore = 10f,
                FreshnessScore = 0.8f,
                RefillCount = 0,
                MaxSize = 100
            };
            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);
            Assert.That(st.LastClassificationTime, Is.EqualTo(BaseTime),
                "ClassifyWall should set LastClassificationTime to the provided utcNow");
        }
    }

    [TestFixture]
    public class IntegrationTests
    {
        private static readonly DateTime BaseTime = new DateTime(2026, 1, 15, 12, 0, 0, DateTimeKind.Utc);
        private const int WallMinSize = 50;

        [Test]
        public void MLClassified_True_PreservesClassification()
        {
            // Set ML classification to Iceberg with high confidence
            var st = new L2LevelStateV2
            {
                IsMLClassified = true,
                Classification = WallClassification.Iceberg,
                Confidence = 0.92f,
                // Rule-based would classify as Spoof if allowed
                SpoofScore = 85f,
                FreshnessScore = 0.05f,
                RefillCount = 0,
                MaxSize = 100
            };

            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);

            Assert.That(st.Classification, Is.EqualTo(WallClassification.Iceberg),
                "ML classification must be preserved when IsMLClassified=true");
            Assert.That(st.Confidence, Is.EqualTo(0.92f),
                "ML confidence must be preserved when IsMLClassified=true");
            // LastClassificationTime should NOT be updated by rule-based
            Assert.That(st.LastClassificationTime, Is.Not.EqualTo(BaseTime),
                "Rule-based ClassifyWall should not update LastClassificationTime when ML override is active");
        }

        [Test]
        public void MLClassified_False_RunsRuleBased()
        {
            var st = new L2LevelStateV2
            {
                IsMLClassified = false,
                Classification = WallClassification.Iceberg,
                Confidence = 0.92f,
                // Rule-based should override to Spoof
                SpoofScore = 85f,
                FreshnessScore = 0.8f,
                RefillCount = 0,
                MaxSize = 100
            };

            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);

            Assert.That(st.Classification, Is.EqualTo(WallClassification.Spoof),
                "When IsMLClassified=false, rule-based should override previous classification");
            Assert.That(st.Confidence, Is.EqualTo(0.85f).Within(0.01f),
                "Spoof confidence should be SpoofScore/100 from rule-based logic");
            Assert.That(st.LastClassificationTime, Is.EqualTo(BaseTime),
                "Rule-based should update LastClassificationTime");
        }

        [Test]
        public void SpoofScoreThenFreshnessThenClassify_FullSequence()
        {
            // Simulate the full scoring + classification pipeline
            var st = new L2LevelStateV2
            {
                CancellationEvents = 25,
                FirstSeenTime = BaseTime.AddMilliseconds(-600),
                MaxSize = 400,
                ModificationCount = 20,
                LastUpdate = BaseTime.AddSeconds(-2),
                PriceTradedThrough = false,
                RefillCount = 0,
                IsMLClassified = false
            };

            double avgWallSize = 100.0;
            double ticksFromBBO = 8.0;

            // Step 1: Compute spoof score
            float spoofScore = DepthRadarV2Logic.ComputeSpoofScore(st, avgWallSize, ticksFromBBO, BaseTime);
            st.SpoofScore = spoofScore;

            // Step 2: Compute freshness score
            float freshnessScore = DepthRadarV2Logic.ComputeFreshnessScore(st, ticksFromBBO, BaseTime);
            st.FreshnessScore = freshnessScore;

            // Step 3: Classify
            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);

            // Verify the pipeline produced consistent results
            Assert.That(st.SpoofScore, Is.GreaterThan(0f), "SpoofScore should be computed");
            Assert.That(st.FreshnessScore, Is.GreaterThan(0f).And.LessThanOrEqualTo(1f),
                "FreshnessScore should be in (0, 1]");
            Assert.That(st.Classification, Is.Not.EqualTo(WallClassification.Unknown),
                "Wall with MaxSize=400 >= WallMinSize=50 should not be Unknown");
            Assert.That(st.LastClassificationTime, Is.EqualTo(BaseTime),
                "Classification time should be set");

            // With 25 cancellations + short time + large size + distance,
            // spoof score should be high enough for Spoof classification
            Assert.That(st.SpoofScore, Is.GreaterThanOrEqualTo(70f),
                "High cancel + short time + big size + distance should yield SpoofScore >= 70");
            Assert.That(st.Classification, Is.EqualTo(WallClassification.Spoof),
                "Pipeline should classify this pattern as Spoof");
        }

        [Test]
        public void FullSequence_GenuineWall_NotSpoof()
        {
            var st = new L2LevelStateV2
            {
                CancellationEvents = 0,
                FirstSeenTime = BaseTime.AddMinutes(-10),
                MaxSize = 80,
                ModificationCount = 1,
                LastUpdate = BaseTime,
                PriceTradedThrough = false,
                RefillCount = 0,
                IsMLClassified = false
            };

            float spoofScore = DepthRadarV2Logic.ComputeSpoofScore(st, 100.0, 1.0, BaseTime);
            st.SpoofScore = spoofScore;

            float freshnessScore = DepthRadarV2Logic.ComputeFreshnessScore(st, 1.0, BaseTime);
            st.FreshnessScore = freshnessScore;

            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);

            Assert.That(st.SpoofScore, Is.LessThan(40f),
                "Genuine wall pattern should have low spoof score");
            Assert.That(st.FreshnessScore, Is.GreaterThan(0.8f),
                "Recently updated wall should have high freshness");
            Assert.That(st.Classification, Is.EqualTo(WallClassification.Genuine),
                "Genuine wall should be classified as Genuine");
        }

        [Test]
        public void FullSequence_StaleWall()
        {
            var st = new L2LevelStateV2
            {
                CancellationEvents = 0,
                FirstSeenTime = BaseTime.AddHours(-1),
                MaxSize = 100,
                ModificationCount = 30,
                LastUpdate = BaseTime.AddMinutes(-60),
                PriceTradedThrough = true,
                PriceCrossTime = BaseTime.AddMinutes(-30),
                RefillCount = 0,
                IsMLClassified = false
            };

            st.SpoofScore = DepthRadarV2Logic.ComputeSpoofScore(st, 100.0, 5.0, BaseTime);
            st.FreshnessScore = DepthRadarV2Logic.ComputeFreshnessScore(st, 5.0, BaseTime);

            DepthRadarV2Logic.ClassifyWall(st, WallMinSize, BaseTime);

            Assert.That(st.FreshnessScore, Is.LessThan(0.1f),
                "Old + price-crossed + many-mods wall should be very stale");
            Assert.That(st.Classification, Is.EqualTo(WallClassification.Stale),
                "Stale freshness should classify as Stale");
        }
    }
}
