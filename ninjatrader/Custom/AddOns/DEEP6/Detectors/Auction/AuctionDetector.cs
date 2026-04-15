// AuctionDetector: ISignalDetector implementation for AUCT-01..05.
//
// Wave 3 (TRIVIAL): AUCT-02 Finished Auction
// Wave 4 (MODERATE): AUCT-01 Unfinished Business (in-memory only, Phase 17),
//                    AUCT-03 Poor High/Low, AUCT-04 Volume Void, AUCT-05 Market Sweep
//
// Python reference: deep6/engines/auction.py AuctionEngine.process()
//
// AUCT-01 in-memory note: cross-session SQLite persistence is deferred to Phase 18+.
// This phase tracks unfinished levels in session.UnfinishedLevels (Dictionary<double,int>).
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Auction
{
    /// <summary>
    /// Configuration for AuctionDetector.
    /// Python reference: deep6/engines/signal_config.py AuctionConfig
    /// </summary>
    public sealed class AuctionConfig
    {
        /// <summary>Vol fraction of avg level vol below which high/low is "poor". Python: poor_extreme_vol_ratio=0.15</summary>
        public double PoorExtremeVolRatio = 0.15;

        /// <summary>Vol fraction of max level vol below which a level is a "void". Python: void_vol_ratio=0.05</summary>
        public double VoidVolRatio = 0.05;

        /// <summary>Vol fraction above which a void neighbor must be. Python: void_neighbor_min=0.5</summary>
        public double VoidNeighborMin = 0.5;

        /// <summary>Minimum void levels to fire AUCT-04. Python: void_min_levels=2</summary>
        public int VoidMinLevels = 2;

        /// <summary>Minimum levels for AUCT-05 sweep. Python: sweep_min_levels=6</summary>
        public int SweepMinLevels = 6;

        /// <summary>Volume acceleration factor for sweep (upper half / lower half). Python: sweep_vol_increase=1.5</summary>
        public double SweepVolIncrease = 1.5;
    }

    /// <summary>
    /// Detects AUCT-01 (Unfinished Business), AUCT-02 (Finished Auction),
    /// AUCT-03 (Poor High/Low), AUCT-04 (Volume Void), AUCT-05 (Market Sweep).
    ///
    /// Implements ISignalDetector. AUCT-01 uses session.UnfinishedLevels for in-memory tracking.
    /// Python reference: deep6/engines/auction.py
    /// </summary>
    public sealed class AuctionDetector : ISignalDetector
    {
        private readonly AuctionConfig _cfg;

        public AuctionDetector() : this(new AuctionConfig()) { }

        public AuctionDetector(AuctionConfig cfg)
        {
            _cfg = cfg ?? new AuctionConfig();
        }

        /// <inheritdoc/>
        public string Name => "Auction";

        /// <inheritdoc/>
        public void Reset()
        {
            // UnfinishedLevels lives in SessionContext — session.ResetSession() clears it.
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || bar.Levels == null || bar.Levels.Count < 2 || bar.TotalVol == 0)
                return Array.Empty<SignalResult>();

            var results = new List<SignalResult>();

            // Get extreme levels from sorted dictionary (first = low, last = high)
            double highPx = double.NaN;
            double lowPx  = double.NaN;
            foreach (var kv in bar.Levels)
            {
                if (double.IsNaN(lowPx))  lowPx  = kv.Key;
                highPx = kv.Key;
            }
            if (double.IsNaN(highPx) || double.IsNaN(lowPx)) return Array.Empty<SignalResult>();

            Cell highLevel = bar.Levels[highPx];
            Cell lowLevel  = bar.Levels[lowPx];

            int barIndex = bar.BarIndex;

            // -------------------------------------------------------------------
            // AUCT-01 UNFINISHED BUSINESS
            // Python: non-zero bid at bar high = price will return upward (+1)
            //         non-zero ask at bar low  = price will return downward (-1)
            // Track in session.UnfinishedLevels; expire entries > UnfinishedMaxAge bars.
            // -------------------------------------------------------------------
            if (session != null && session.UnfinishedLevels != null)
            {
                // Expire old entries first
                var toRemove = new List<double>();
                foreach (var kv in session.UnfinishedLevels)
                {
                    if (barIndex - kv.Value > SessionContext.UnfinishedMaxAge)
                        toRemove.Add(kv.Key);
                }
                foreach (double px in toRemove) session.UnfinishedLevels.Remove(px);
            }

            if (highLevel.BidVol > 0)
            {
                results.Add(new SignalResult(
                    "AUCT-01", +1, 0.6,
                    SignalFlagBits.Mask(SignalFlagBits.AUCT_01),
                    string.Format("UNFINISHED BUSINESS at high {0:F2}: bid_vol={1} — price will return",
                        highPx, highLevel.BidVol)));
                if (session != null && session.UnfinishedLevels != null)
                    session.UnfinishedLevels[highPx] = barIndex;
            }

            if (lowLevel.AskVol > 0)
            {
                results.Add(new SignalResult(
                    "AUCT-01", -1, 0.6,
                    SignalFlagBits.Mask(SignalFlagBits.AUCT_01),
                    string.Format("UNFINISHED BUSINESS at low {0:F2}: ask_vol={1} — price will return",
                        lowPx, lowLevel.AskVol)));
                if (session != null && session.UnfinishedLevels != null)
                    session.UnfinishedLevels[lowPx] = barIndex;
            }

            // -------------------------------------------------------------------
            // AUCT-02 FINISHED AUCTION
            // Python: zero bid at high (buyers exhausted) → direction=-1
            //         zero ask at low (sellers exhausted)  → direction=+1
            // -------------------------------------------------------------------
            if (highLevel.BidVol == 0 && highLevel.AskVol > 0)
            {
                results.Add(new SignalResult(
                    "AUCT-02", -1, 1.0,
                    SignalFlagBits.Mask(SignalFlagBits.AUCT_02),
                    string.Format("FINISHED AUCTION at high {0:F2}: zero bid — buyers exhausted", highPx)));
            }

            if (lowLevel.AskVol == 0 && lowLevel.BidVol > 0)
            {
                results.Add(new SignalResult(
                    "AUCT-02", +1, 1.0,
                    SignalFlagBits.Mask(SignalFlagBits.AUCT_02),
                    string.Format("FINISHED AUCTION at low {0:F2}: zero ask — sellers exhausted", lowPx)));
            }

            // -------------------------------------------------------------------
            // AUCT-03 POOR HIGH/LOW
            // Python: vol at high or low < avg_level_vol * poor_extreme_vol_ratio
            // avg_level_vol = total_vol / level_count
            // -------------------------------------------------------------------
            double avgVol  = (double)bar.TotalVol / bar.Levels.Count;
            long   highVol = highLevel.AskVol + highLevel.BidVol;
            long   lowVol  = lowLevel.AskVol + lowLevel.BidVol;
            double poorTh  = avgVol * _cfg.PoorExtremeVolRatio;

            if (highVol < poorTh)
            {
                results.Add(new SignalResult(
                    "AUCT-03", -1, 0.5,
                    SignalFlagBits.Mask(SignalFlagBits.AUCT_03),
                    string.Format("POOR HIGH at {0:F2}: vol={1} ({2:F0}% avg) — incomplete auction",
                        highPx, highVol, avgVol > 0 ? highVol / avgVol * 100 : 0)));
            }

            if (lowVol < poorTh)
            {
                results.Add(new SignalResult(
                    "AUCT-03", +1, 0.5,
                    SignalFlagBits.Mask(SignalFlagBits.AUCT_03),
                    string.Format("POOR LOW at {0:F2}: vol={1} ({2:F0}% avg) — incomplete auction",
                        lowPx, lowVol, avgVol > 0 ? lowVol / avgVol * 100 : 0)));
            }

            // -------------------------------------------------------------------
            // AUCT-04 VOLUME VOID
            // Python: levels with vol < max_level_vol * void_vol_ratio; count >= void_min_levels
            // -------------------------------------------------------------------
            long maxLevelVol = 0;
            foreach (var kv in bar.Levels)
            {
                long lv = kv.Value.AskVol + kv.Value.BidVol;
                if (lv > maxLevelVol) maxLevelVol = lv;
            }

            int voidCount = 0;
            double voidTh = maxLevelVol * _cfg.VoidVolRatio;
            foreach (var kv in bar.Levels)
            {
                long lv = kv.Value.AskVol + kv.Value.BidVol;
                if (lv < voidTh && lv > 0)
                    voidCount++;
            }

            if (voidCount >= _cfg.VoidMinLevels)
            {
                int dir = bar.Close > bar.Open ? +1 : -1;
                double str = System.Math.Min((double)voidCount / 7.0, 1.0);
                results.Add(new SignalResult(
                    "AUCT-04", dir, str,
                    SignalFlagBits.Mask(SignalFlagBits.AUCT_04),
                    string.Format("VOLUME VOID: {0} thin levels — fast-move zone", voidCount)));
            }

            // -------------------------------------------------------------------
            // AUCT-05 MARKET SWEEP
            // Python: bar spans >= sweep_min_levels AND second-half vol > first-half vol * sweep_vol_increase
            // Direction = sign of bar close vs open.
            // -------------------------------------------------------------------
            if (bar.Levels.Count >= _cfg.SweepMinLevels)
            {
                var sortedPrices = new List<double>(bar.Levels.Keys);
                int half = sortedPrices.Count / 2;
                bool barUp = bar.Close > bar.Open;

                long firstHalfVol;
                long secondHalfVol;

                if (barUp)
                {
                    // Up sweep: second half (upper levels) should have more vol
                    firstHalfVol  = SumVol(bar, sortedPrices, 0, half);
                    secondHalfVol = SumVol(bar, sortedPrices, half, sortedPrices.Count);
                }
                else
                {
                    // Down sweep: lower half (first in sorted) should have more vol
                    firstHalfVol  = SumVol(bar, sortedPrices, half, sortedPrices.Count);
                    secondHalfVol = SumVol(bar, sortedPrices, 0, half);
                }

                if (firstHalfVol > 0 && secondHalfVol > firstHalfVol * _cfg.SweepVolIncrease)
                {
                    int dir = barUp ? +1 : -1;
                    double str = System.Math.Min(secondHalfVol / (double)firstHalfVol / 3.0, 1.0);
                    string label = barUp ? "UP" : "DOWN";
                    results.Add(new SignalResult(
                        "AUCT-05", dir, str,
                        SignalFlagBits.Mask(SignalFlagBits.AUCT_05),
                        string.Format("MARKET SWEEP {0}: {1} levels, vol accelerated ({2} → {3}, {4:F1}x)",
                            label, sortedPrices.Count, firstHalfVol, secondHalfVol,
                            firstHalfVol > 0 ? (double)secondHalfVol / firstHalfVol : 0)));
                }
            }

            return results.ToArray();
        }

        // -----------------------------------------------------------------------
        // Private helpers
        // -----------------------------------------------------------------------

        private static long SumVol(FootprintBar bar, List<double> sortedPrices, int start, int end)
        {
            long total = 0;
            for (int i = start; i < end; i++)
            {
                var lv = bar.Levels[sortedPrices[i]];
                total += lv.AskVol + lv.BidVol;
            }
            return total;
        }
    }
}
