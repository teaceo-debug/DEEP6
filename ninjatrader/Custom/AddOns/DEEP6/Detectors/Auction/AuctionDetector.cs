// AuctionDetector: ISignalDetector implementation for AUCT-02 (Finished Auction).
//
// Python reference: deep6/engines/auction.py AuctionEngine.process() lines 137-152
// Signal IDs: AUCT-02 (Finished Auction)
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).
//
// Auction theory: A "finished auction" occurs when the extreme price level (high or low)
// has zero volume on the opposing side — buyers are absent at the high (no bid),
// or sellers are absent at the low (no ask). This signals exhaustion of the prior move.

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Auction
{
    /// <summary>
    /// Detects AUCT-02 (Finished Auction) — zero bid at bar high, or zero ask at bar low.
    ///
    /// Implements ISignalDetector; stateless between bars.
    /// Python reference: deep6/engines/auction.py AuctionEngine.process() lines 137-152
    /// AUCT-01/03/04/05 come in Wave 4.
    /// </summary>
    public sealed class AuctionDetector : ISignalDetector
    {
        public AuctionDetector() { }

        /// <inheritdoc/>
        public string Name => "Auction";

        /// <inheritdoc/>
        public void Reset()
        {
            // Stateless detector — nothing to reset.
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || bar.Levels == null || bar.Levels.Count < 2 || bar.TotalVol == 0)
                return Array.Empty<SignalResult>();

            var results = new List<SignalResult>();

            // Get extreme levels: lowest and highest prices in the bar's level dictionary.
            // SortedDictionary is ascending — first key = bar low, last key = bar high.
            double highPx = double.NaN;
            double lowPx  = double.NaN;
            foreach (var kv in bar.Levels)
            {
                if (double.IsNaN(lowPx))  lowPx  = kv.Key;  // first element = lowest
                highPx = kv.Key;                              // last element = highest
            }

            if (double.IsNaN(highPx) || double.IsNaN(lowPx)) return Array.Empty<SignalResult>();

            Cell highLevel = bar.Levels[highPx];
            Cell lowLevel  = bar.Levels[lowPx];

            // --- AUCT-02 FINISHED AUCTION ---
            // Python auction.py lines 138-152:
            //   if high_level.bid_vol == 0 and high_level.ask_vol > 0 → direction = -1 (bearish: buyers exhausted at top)
            //   if low_level.ask_vol == 0 and low_level.bid_vol > 0   → direction = +1 (bullish: sellers exhausted at bottom)

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

            return results.ToArray();
        }
    }
}
