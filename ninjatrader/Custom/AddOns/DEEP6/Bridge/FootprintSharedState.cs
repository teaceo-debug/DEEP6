// FootprintSharedState — atomic snapshot bridge between DEEP6FootprintBarsType and DEEP6FootprintStyle.
//
// Pattern mirrors GexSharedState.cs: static ConcurrentDictionary, immutable snapshot, lock-free reads.
//
// Thread model:
//   WRITE: BarsType data thread — publishes one FootprintSharedData per bar close
//   READ:  ChartStyle render thread — reads latest reference, zero blocking
//
// NT8-API-free: no NinjaTrader.* using directives.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge
{
    // ─── Supporting types ──────────────────────────────────────────────────────

    /// <summary>
    /// A zone of consecutive imbalance rows within a single bar.
    /// Extracted from the private struct in DEEP6FootprintChart for shared use across BarsType and ChartStyle.
    /// </summary>
    public sealed class StackedZone
    {
        public double PriceLow;
        public double PriceHigh;
        public int    Tier;       // 1 = 3–4 rows, 2 = 5–6 rows, 3 = 7+ rows
        public int    Direction;  // +1 buy zone, -1 sell zone
    }

    /// <summary>Per-bar supplementary rendering data computed at bar close by the BarsType.</summary>
    public sealed class BarAuxData
    {
        public int                 ColumnType;      // +1 bull column, -1 bear column, 0 mixed
        public List<StackedZone>   StackedZones;
        public HashSet<double>     LargeLotPrices;
        public int                 VolumeClimaxDir; // +1 bullish climax, -1 bearish climax, 0 none
    }

    /// <summary>
    /// Snapshot of all published data for one instrument.
    /// Immutable after publication — the BarsType creates a new instance on each bar close.
    /// </summary>
    public sealed class FootprintSharedData
    {
        // Bar-indexed data
        public readonly Dictionary<int, FootprintBar>  Bars    = new Dictionary<int, FootprintBar>();
        public readonly Dictionary<int, Scoring.ScorerResult> Scores  = new Dictionary<int, Scoring.ScorerResult>();
        public readonly Dictionary<int, BarAuxData>    AuxData = new Dictionary<int, BarAuxData>();

        // Session VWAP (latest values at bar close)
        public double VwapPrice, Vwap1H, Vwap1L, Vwap2H, Vwap2L;

        // Initial Balance
        public double IbHigh = double.MinValue;
        public double IbLow  = double.MaxValue;

        // Profile anchor levels snapshot
        public Levels.ProfileAnchorSnapshot Anchors;

        // L2 walls: price → (currentSize, maxSize, refillCount)
        public Dictionary<double, L2WallEntry> L2Bids;
        public Dictionary<double, L2WallEntry> L2Asks;

        // Unfinished auction levels: price → barIdx when first detected
        public Dictionary<double, int> UnfinishedLevels;

        // Latest score (for HUD)
        public Scoring.ScorerResult LatestScore;

        // Meta
        public int      LastBarIdx;
        public DateTime LastPublishedUtc;
    }

    /// <summary>L2 wall entry stored in the snapshot.</summary>
    public struct L2WallEntry
    {
        public long CurrentSize;
        public long MaxSize;
        public int  RefillCount;
    }

    // ─── Static bridge ─────────────────────────────────────────────────────────

    /// <summary>
    /// Thread-safe static bridge between DEEP6FootprintBarsType (writes, data thread)
    /// and DEEP6FootprintStyle (reads, render thread).
    ///
    /// Publish pattern: build a new FootprintSharedData snapshot on the data thread,
    /// then atomically replace the stored reference. Readers get a stable reference
    /// with no locking needed (x64 reference reads are atomic; ConcurrentDictionary
    /// uses memory barriers ensuring visibility).
    /// </summary>
    public static class FootprintSharedState
    {
        private static readonly ConcurrentDictionary<string, FootprintSharedData> _data =
            new ConcurrentDictionary<string, FootprintSharedData>(StringComparer.Ordinal);

        /// <summary>
        /// Publish a completed bar. Called by BarsType once per bar close on the data thread.
        /// Creates a new immutable snapshot carrying all bar + session data.
        /// </summary>
        public static void Publish(
            string                                          instrument,
            int                                             barIdx,
            FootprintBar                                    bar,
            Scoring.ScorerResult                            score,
            double                                          vwap,
            double                                          vwap1H, double vwap1L,
            double                                          vwap2H, double vwap2L,
            double                                          ibHigh, double ibLow,
            Levels.ProfileAnchorSnapshot                    anchors,
            Dictionary<double, long>                        l2Bids,
            Dictionary<double, long>                        l2Asks,
            Dictionary<double, int>                         l2BidRefills,
            Dictionary<double, int>                         l2AskRefills,
            Dictionary<double, long>                        l2BidMax,
            Dictionary<double, long>                        l2AskMax,
            int                                             barColumnType,
            List<StackedZone>                               stackedZones,
            HashSet<double>                                 largeLotPrices,
            int                                             volumeClimaxDir,
            Dictionary<double, int>                         unfinishedLevels)
        {
            if (string.IsNullOrWhiteSpace(instrument) || bar == null) return;

            FootprintSharedData existing;
            _data.TryGetValue(instrument, out existing);

            var next = new FootprintSharedData();

            // Carry over all existing bars (shallow copy of references — FootprintBar is read-only after finalization)
            if (existing != null)
            {
                foreach (var kv in existing.Bars)    next.Bars[kv.Key]    = kv.Value;
                foreach (var kv in existing.Scores)  next.Scores[kv.Key]  = kv.Value;
                foreach (var kv in existing.AuxData) next.AuxData[kv.Key] = kv.Value;
            }

            // Add / replace this bar
            next.Bars[barIdx]    = bar;
            next.Scores[barIdx]  = score;
            next.AuxData[barIdx] = new BarAuxData
            {
                ColumnType       = barColumnType,
                StackedZones     = stackedZones,
                LargeLotPrices   = largeLotPrices,
                VolumeClimaxDir  = volumeClimaxDir
            };

            // Session levels
            next.VwapPrice = vwap;
            next.Vwap1H = vwap1H; next.Vwap1L = vwap1L;
            next.Vwap2H = vwap2H; next.Vwap2L = vwap2L;
            next.IbHigh = ibHigh; next.IbLow = ibLow;
            next.Anchors = anchors;

            // L2 walls
            next.L2Bids = BuildL2Snapshot(l2Bids, l2BidMax, l2BidRefills);
            next.L2Asks = BuildL2Snapshot(l2Asks, l2AskMax, l2AskRefills);

            // Unfinished auctions (copy to prevent shared mutation)
            next.UnfinishedLevels = unfinishedLevels != null
                ? new Dictionary<double, int>(unfinishedLevels)
                : new Dictionary<double, int>();

            next.LatestScore      = score;
            next.LastBarIdx       = barIdx;
            next.LastPublishedUtc = DateTime.UtcNow;

            // Prune rolling window (keep last 500 bars)
            int cutoff = barIdx - 500;
            if (cutoff > 0)
            {
                var toRemove = new List<int>();
                foreach (var k in next.Bars.Keys) if (k < cutoff) toRemove.Add(k);
                foreach (var k in toRemove)
                {
                    next.Bars.Remove(k);
                    next.Scores.Remove(k);
                    next.AuxData.Remove(k);
                }
            }

            // Atomic replace — single reference write, visible to all readers immediately
            _data[instrument] = next;
        }

        /// <summary>
        /// Read-only access for the render thread.
        /// Returns null if nothing has been published yet.
        /// </summary>
        public static FootprintSharedData GetData(string instrument)
        {
            if (string.IsNullOrWhiteSpace(instrument)) return null;
            FootprintSharedData d;
            return _data.TryGetValue(instrument, out d) ? d : null;
        }

        /// <summary>Remove all data for an instrument. Called by BarsType on Terminated.</summary>
        public static void Clear(string instrument)
        {
            if (string.IsNullOrWhiteSpace(instrument)) return;
            FootprintSharedData dummy;
            _data.TryRemove(instrument, out dummy);
        }

        // ── Helpers ──────────────────────────────────────────────────────────────

        private static Dictionary<double, L2WallEntry> BuildL2Snapshot(
            Dictionary<double, long> sizes,
            Dictionary<double, long> maxSizes,
            Dictionary<double, int>  refills)
        {
            if (sizes == null) return new Dictionary<double, L2WallEntry>();
            var result = new Dictionary<double, L2WallEntry>(sizes.Count);
            foreach (var kv in sizes)
            {
                long mx = 0; int rf = 0;
                if (maxSizes != null) maxSizes.TryGetValue(kv.Key, out mx);
                if (refills  != null) refills.TryGetValue(kv.Key, out rf);
                result[kv.Key] = new L2WallEntry
                {
                    CurrentSize = kv.Value,
                    MaxSize     = mx,
                    RefillCount = rf
                };
            }
            return result;
        }
    }
}
