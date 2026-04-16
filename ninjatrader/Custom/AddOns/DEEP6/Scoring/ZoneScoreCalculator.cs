// ZoneScoreCalculator: computes zoneScore from ProfileAnchorSnapshot for ConfluenceScorer.
//
// Algorithm (spec: P0-1):
//   Inside zone (barClose between any anchor level ± 2 ticks): return 8.0
//     → maps to ZONE_HIGH_MIN (50) in ConfluenceScorer → zoneBonus = ZONE_HIGH_BONUS (8.0)
//   Near zone edge (within 4 ticks but not inside): return 4.0
//     → maps to ZONE_MID_MIN (30) in ConfluenceScorer → zoneBonus = ZONE_MID_BONUS (6.0)
//     NOTE: 4.0 here is the raw score representing proximity; scorer uses its own bonus constants
//   No zone proximity: return 0.0
//
// Levels checked: PD_POC, PD_VAH, PD_VAL, NakedPoc, PW_POC
// Other levels (PDH, PDL, PDM, CompositeVAH/VAL) are not checked — they are
// positional/structural levels, not volume-based zone anchors.
//
// NT8-API-free — no NinjaTrader.* using directives.

using NinjaTrader.NinjaScript.AddOns.DEEP6.Levels;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring
{
    /// <summary>
    /// Computes a scalar zone-score [0..100] from <see cref="ProfileAnchorSnapshot"/>
    /// for use as the <c>zoneScore</c> parameter of <see cref="ConfluenceScorer.Score"/>.
    /// </summary>
    public static class ZoneScoreCalculator
    {
        // Score constants that map to ConfluenceScorer's zone-bonus tiers.
        // ZONE_HIGH_MIN in scorer = 50 → zoneBonus = 8.0 (ZONE_HIGH_BONUS)
        // ZONE_MID_MIN in scorer  = 30 → zoneBonus = 6.0 (ZONE_MID_BONUS)
        // Returning 60 (above ZONE_HIGH_MIN) for inside-zone and 35 (above ZONE_MID_MIN)
        // for near-zone-edge ensures the scorer applies the right bonus tier.

        /// <summary>Score returned when bar close is within 2 ticks of an anchor level (inside zone).</summary>
        public const double InsideZoneScore = 60.0;

        /// <summary>Score returned when bar close is within 4 ticks of an anchor level (near edge).</summary>
        public const double NearZoneEdgeScore = 35.0;

        /// <summary>
        /// Compute zone score from <paramref name="snapshot"/> for a bar at <paramref name="barClose"/>.
        /// </summary>
        /// <param name="barClose">Current bar close price.</param>
        /// <param name="snapshot">Profile anchor snapshot from <see cref="ProfileAnchorLevels.BuildSnapshot"/>. Null → 0.0.</param>
        /// <param name="tickSize">Instrument tick size (e.g. 0.25 for NQ).</param>
        /// <returns>
        /// <see cref="InsideZoneScore"/> (60) when bar close is within 2 ticks of a relevant anchor;
        /// <see cref="NearZoneEdgeScore"/> (35) when within 4 ticks;
        /// 0.0 when no anchor is nearby.
        /// </returns>
        public static double Compute(double barClose, ProfileAnchorSnapshot snapshot, double tickSize)
        {
            if (snapshot == null || snapshot.Levels == null || snapshot.Levels.Count == 0)
                return 0.0;

            double insideThresh = 2.0 * tickSize;  // 2 ticks
            double nearThresh   = 4.0 * tickSize;  // 4 ticks

            double bestScore = 0.0;

            foreach (var anchor in snapshot.Levels)
            {
                // Only check volume-profile zone anchors
                if (!IsZoneAnchor(anchor.Kind))
                    continue;

                double dist = System.Math.Abs(barClose - anchor.Price);

                if (dist <= insideThresh)
                {
                    // Inside zone — highest score, no need to keep searching
                    return InsideZoneScore;
                }
                else if (dist <= nearThresh)
                {
                    // Near zone edge — keep looking in case a closer level is inside
                    bestScore = NearZoneEdgeScore;
                }
            }

            return bestScore;
        }

        // -------------------------------------------------------------------------
        // Helper: only POC/VAH/VAL-class anchors count as zone anchors.
        // PDH/PDL/PDM and CompositeVAH/VAL are positional, not volume zones.
        // -------------------------------------------------------------------------
        private static bool IsZoneAnchor(ProfileAnchorKind kind)
        {
            switch (kind)
            {
                case ProfileAnchorKind.PriorDayPoc:
                case ProfileAnchorKind.PriorDayVah:
                case ProfileAnchorKind.PriorDayVal:
                case ProfileAnchorKind.NakedPoc:
                case ProfileAnchorKind.PriorWeekPoc:
                    return true;
                default:
                    return false;
            }
        }
    }
}
