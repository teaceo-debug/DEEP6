// NarrativeCascade: Narrative label assembly for scored bars.
//
// Python reference: deep6/scoring/scorer.py lines 499–508 (tier label format)
//                   deep6/engines/narrative.py (NarrativeResult.label — dominant signal detail)
// Port: Phase 18-01 — tier-specific label format verbatim from Python scorer.py.
//
// NT8-API-free: no NinjaTrader.Cbi, NinjaTrader.NinjaScript.Indicators, or NinjaTrader.Data usings.

// NOTE: System.Math is fully qualified (System.Math.Round) because the project
// also contains NinjaTrader.NinjaScript.AddOns.DEEP6.Math which shadows System.Math.
using System.Collections.Generic;
using System.Text;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring
{
    /// <summary>
    /// Assembles human-readable narrative labels for scored bars.
    /// Label formats match Python scorer.py lines 499–508 verbatim.
    /// </summary>
    public static class NarrativeCascade
    {
        private const int MaxDetailLength = 50;

        /// <summary>
        /// Build the tier label for a scored bar.
        /// Matches Python scorer.py label assembly (lines 499–508).
        ///
        /// TypeA: "TYPE A — TRIPLE CONFLUENCE LONG (N categories, score S)"
        /// TypeB: "TYPE B — DOUBLE CONFLUENCE LONG (N categories, score S)"
        /// TypeC: "TYPE C — SIGNAL (N categories, score S)"
        /// QUIET/DISQUALIFIED: dominant signal detail from signals array, or "QUIET" if empty.
        /// </summary>
        public static string BuildLabel(ScorerResult partial, NinjaTrader.NinjaScript.AddOns.DEEP6.Registry.SignalResult[] signals)
        {
            int n   = partial.CategoryCount;
            int s   = (int)System.Math.Round(partial.TotalScore, System.MidpointRounding.AwayFromZero);
            string dirStr = partial.Direction > 0 ? "LONG" : "SHORT";

            switch (partial.Tier)
            {
                case SignalTier.TYPE_A:
                    return $"TYPE A \u2014 TRIPLE CONFLUENCE {dirStr} ({n} categories, score {s})";

                case SignalTier.TYPE_B:
                    return $"TYPE B \u2014 DOUBLE CONFLUENCE {dirStr} ({n} categories, score {s})";

                case SignalTier.TYPE_C:
                    return $"TYPE C \u2014 SIGNAL ({n} categories, score {s})";

                default:
                    // QUIET or DISQUALIFIED — return dominant signal detail or "QUIET"
                    return BuildDominantDetail(signals, partial.Direction, maxSupporting: 2);
            }
        }

        /// <summary>
        /// Build a compact detail label from dominant-direction signals.
        /// Returns dominant.Detail + " + " + supporting[0].SignalId + " + " + supporting[1].SignalId,
        /// truncated to 50 chars with ellipsis if longer.
        /// Returns "QUIET" if no signals have a nonzero direction matching dominant.
        /// </summary>
        public static string BuildDominantDetail(
            NinjaTrader.NinjaScript.AddOns.DEEP6.Registry.SignalResult[] signals,
            int direction,
            int maxSupporting = 2)
        {
            if (signals == null || signals.Length == 0)
                return "QUIET";

            // Find dominant-direction signals
            var dominant    = new List<NinjaTrader.NinjaScript.AddOns.DEEP6.Registry.SignalResult>();
            foreach (var s in signals)
            {
                if (s.Direction == direction && direction != 0)
                    dominant.Add(s);
            }

            if (dominant.Count == 0)
                return "QUIET";

            // Primary = first signal with a non-empty Detail
            NinjaTrader.NinjaScript.AddOns.DEEP6.Registry.SignalResult primary = null;
            foreach (var s in dominant)
            {
                if (!string.IsNullOrEmpty(s.Detail))
                {
                    primary = s;
                    break;
                }
            }
            if (primary == null)
                primary = dominant[0];

            if (dominant.Count == 1)
                return Truncate(primary.Detail ?? primary.SignalId);

            // Append up to maxSupporting supporting signal IDs
            var sb = new StringBuilder(primary.Detail ?? primary.SignalId);
            int added = 0;
            foreach (var s in dominant)
            {
                if (s == primary) continue;
                if (added >= maxSupporting) break;
                sb.Append(" + ").Append(s.SignalId);
                added++;
            }

            return Truncate(sb.ToString());
        }

        private static string Truncate(string text)
        {
            if (string.IsNullOrEmpty(text))
                return "QUIET";
            if (text.Length <= MaxDetailLength)
                return text;
            return text.Substring(0, MaxDetailLength - 3) + "...";
        }
    }
}
