using System;

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    // Classification priority is safety-first:
    // SPOOF > STALE > ICEBERG > GENUINE
    // Flag risks before confirming quality.
    public enum WallClassification
    {
        Unknown = 0,
        Genuine = 1,
        Spoof   = 2,
        Iceberg = 3,
        Stale   = 4
    }

    /// <summary>
    /// Per-price-level state tracker for DEEP6 Depth Radar V2.
    /// </summary>
    public sealed class L2LevelStateV2
    {
        /// <summary>Current resting size at this price level.</summary>
        public long CurrentSize;

        /// <summary>Peak size observed at this price level.</summary>
        public long MaxSize;

        /// <summary>Timestamp of the most recent update to this level.</summary>
        public DateTime LastUpdate;

        /// <summary>Number of refill events observed for this level.</summary>
        public int RefillCount;

        /// <summary>Current classification assigned to this level.</summary>
        public WallClassification Classification = WallClassification.Unknown;

        /// <summary>Classification confidence in the range 0 to 1.</summary>
        public float Confidence = 0f;

        /// <summary>Timestamp when the classification was last updated.</summary>
        public DateTime LastClassificationTime;

        /// <summary>Indicates whether price has traded through this level.</summary>
        public bool PriceTradedThrough = false;

        /// <summary>Timestamp when price first crossed through this level.</summary>
        public DateTime PriceCrossTime;

        /// <summary>Timestamp when this level first appeared on the DOM.</summary>
        public DateTime FirstSeenTime;

        /// <summary>Number of times this order level has been modified.</summary>
        public int ModificationCount;

        /// <summary>Original resting size when the order was first placed.</summary>
        public long OriginalSize;

        /// <summary>Number of times size dropped to zero and later reappeared.</summary>
        public int CancellationEvents;

        /// <summary>Rule-based spoof score in the range 0 to 100.</summary>
        public float SpoofScore = 0f;

        /// <summary>Freshness score in the range 0 to 1, where 1 is fresh and 0 is stale.</summary>
        public float FreshnessScore = 1f;

        /// <summary>Indicates whether machine learning has classified this level.</summary>
        public bool IsMLClassified = false;

        /// <summary>Predicted interaction outcome: BOUNCE, BREAK, HOLD, or empty if no prediction.</summary>
        public string InteractionPrediction = "";

        /// <summary>Confidence of the interaction prediction (0-1).</summary>
        public float InteractionConfidence = 0f;
    }

    /// <summary>
    /// Testable scoring and classification logic for Depth Radar V2.
    /// Methods accept utcNow explicitly for deterministic unit testing.
    /// </summary>
    internal static class DepthRadarV2Logic
    {
        internal static float ComputeSpoofScore(L2LevelStateV2 st, double avgWallSize, double ticksFromBBO, DateTime utcNow)
        {
            float cancelRatio = st.CancellationEvents / (float)(st.CancellationEvents + 1);
            float cancellationScore = Math.Min(40f, (cancelRatio / 0.95f) * 40f);

            float timeInBookScore = 0f;
            if (st.CancellationEvents > 0)
            {
                double timeInBook = (utcNow - st.FirstSeenTime).TotalMilliseconds;
                timeInBookScore = Math.Max(0f, Math.Min(25f, 25f * (1f - (float)((timeInBook - 500.0) / 4500.0))));
            }

            float sizeRatio = st.MaxSize / (float)Math.Max(1.0, avgWallSize);
            float sizeAnomalyScore = Math.Max(0f, Math.Min(20f, (sizeRatio - 1f) / 4f * 20f));

            float distanceScore = 0f;
            if (ticksFromBBO > 0.0)
                distanceScore = Math.Min(10f, (float)(ticksFromBBO / 10.0) * 10f);

            float elapsedSeconds = (float)Math.Max(1.0, (utcNow - st.FirstSeenTime).TotalSeconds);
            float modRate = st.ModificationCount / elapsedSeconds;
            float modificationScore = Math.Min(5f, (modRate / 10f) * 5f);

            return cancellationScore + timeInBookScore + sizeAnomalyScore + distanceScore + modificationScore;
        }

        internal static float ComputeFreshnessScore(L2LevelStateV2 st, double ticksFromBBO, DateTime utcNow)
        {
            double minutesSinceUpdate = (utcNow - st.LastUpdate).TotalMinutes;
            float timeDecay = (float)Math.Exp(-0.02 * minutesSinceUpdate);

            float priceCrossPenalty = 1.0f;
            if (st.PriceTradedThrough)
            {
                double secondsSinceCross = (utcNow - st.PriceCrossTime).TotalSeconds;
                priceCrossPenalty = (float)Math.Exp(-0.1 * secondsSinceCross);
            }

            float modPenalty = (float)Math.Exp(-0.05 * st.ModificationCount);
            float distancePenalty = 1f / (1f + 0.05f * (float)ticksFromBBO);

            float result = timeDecay * priceCrossPenalty * modPenalty * distancePenalty;
            return Math.Max(0f, Math.Min(1f, result));
        }

        internal static void ClassifyWall(L2LevelStateV2 st, int wallMinSize, DateTime utcNow)
        {
            if (st.IsMLClassified)
                return;

            if (st.SpoofScore >= 70f)
            {
                st.Classification = WallClassification.Spoof;
                st.Confidence = st.SpoofScore / 100f;
                st.LastClassificationTime = utcNow;
                return;
            }

            if (st.FreshnessScore < 0.1f)
            {
                st.Classification = WallClassification.Stale;
                st.Confidence = 1f - st.FreshnessScore;
                st.LastClassificationTime = utcNow;
                return;
            }

            if (st.RefillCount >= 2)
            {
                st.Classification = WallClassification.Iceberg;
                st.Confidence = Math.Min(1f, st.RefillCount * 0.2f);
                st.LastClassificationTime = utcNow;
                return;
            }

            if (st.MaxSize >= wallMinSize)
            {
                st.Classification = WallClassification.Genuine;
                st.Confidence = st.FreshnessScore;
                st.LastClassificationTime = utcNow;
                return;
            }

            st.Classification = WallClassification.Unknown;
            st.Confidence = 0f;
            st.LastClassificationTime = utcNow;
        }
    }
}
