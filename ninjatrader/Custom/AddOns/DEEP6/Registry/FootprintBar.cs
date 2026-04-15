// FootprintBar + Cell: BCL-only types shared by all detectors and test project.
//
// Python reference: deep6/state/footprint.py
// Port spec: .planning/phases/16-.../PORT-SPEC.md §1 Core Types
//
// NT8-specific note: In the NT8 runtime, DEEP6Footprint.cs defines these
// same types in the same namespace (from Phase 16). This file is the BCL-only
// duplicate used by the net8.0 NUnit test project, which cannot reference NT8 DLLs.
//
// When compiled under NT8 (net48, NinjaTrader.Custom.dll), both definitions
// exist in the same assembly — this causes a duplicate-type compile error.
// Solution: This file is included ONLY by the test project via its .csproj
// <Compile Include> glob; NT8 compiles the originals in DEEP6Footprint.cs.
//
// To make both coexist, this file uses a partial-class extension pattern:
// Under net8.0 (test TFM) the types are fresh classes. Under net48 (NT8),
// they come from DEEP6Footprint.cs (which is NOT included in the test .csproj).

using System;
using System.Collections.Generic;
using System.Linq;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6
{
    /// <summary>Per-price-level footprint cell: bid (sell-aggressor) and ask (buy-aggressor) volume.</summary>
    public sealed class Cell
    {
        /// <summary>Sell-aggressor volume (tick price &lt;= best bid).</summary>
        public long BidVol;

        /// <summary>Buy-aggressor volume (tick price &gt;= best ask).</summary>
        public long AskVol;

        /// <summary>Between-spread neutral prints. Not used in signal computation.</summary>
        public long NeutralVol;
    }

    /// <summary>
    /// One completed footprint bar. Populated tick-by-tick via AddTrade(),
    /// finalized at bar close via Finalize().
    ///
    /// Python reference: deep6/state/footprint.py FootprintBar
    /// Port spec: PORT-SPEC.md §1
    /// </summary>
    public sealed class FootprintBar
    {
        public int    BarIndex;
        public double Open, High, Low, Close;

        /// <summary>Price levels — key = price (double), value = Cell. Sorted ascending.</summary>
        public SortedDictionary<double, Cell> Levels = new SortedDictionary<double, Cell>();

        public long   TotalVol;     // sum of (BidVol + AskVol) across all levels
        public long   BarDelta;     // sum of (AskVol - BidVol) across all levels
        public long   Cvd;          // cumulative delta carried forward
        public double PocPrice;     // price level with max volume
        public double BarRange;     // High - Low
        public long   RunningDelta; // intrabar live delta
        public long   MaxDelta;     // intrabar max
        public long   MinDelta;     // intrabar min

        public void AddTrade(double price, long size, int aggressor)
        {
            Cell lv;
            if (!Levels.TryGetValue(price, out lv)) { lv = new Cell(); Levels[price] = lv; }
            if (aggressor == 1) { lv.AskVol += size; RunningDelta += size; }
            else if (aggressor == 2) { lv.BidVol += size; RunningDelta -= size; }
            else { lv.NeutralVol += size; }
            if (RunningDelta > MaxDelta) MaxDelta = RunningDelta;
            if (RunningDelta < MinDelta) MinDelta = RunningDelta;
            if (Open == 0) Open = price;
            if (price > High) High = price;
            if (Low == 0 || price < Low) Low = price;
            Close = price;
            TotalVol += size;
        }

        public void Finalize(long priorCvd = 0)
        {
            // Recompute TotalVol from Levels if it wasn't accumulated via AddTrade().
            // This covers the test-construction pattern where Levels are set directly.
            if (TotalVol == 0 && Levels.Count > 0)
            {
                TotalVol = 0;
                foreach (var lv in Levels.Values) TotalVol += lv.AskVol + lv.BidVol + lv.NeutralVol;
            }

            BarDelta = 0;
            foreach (var lv in Levels.Values) BarDelta += lv.AskVol - lv.BidVol;
            if (Levels.Count > 0)
            {
                double bestPx = 0; long bestVol = -1;
                foreach (var kv in Levels)
                {
                    long v = kv.Value.AskVol + kv.Value.BidVol;
                    if (v > bestVol) { bestVol = v; bestPx = kv.Key; }
                }
                PocPrice = bestPx;
            }
            BarRange = High - Low;
            Cvd = priorCvd + BarDelta;
        }

        /// <summary>
        /// Compute 70% Value Area (VAH, VAL) from this bar's footprint.
        /// Python reference: deep6/engines/poc.py lines 231-257
        /// </summary>
        public static (double vah, double val) ComputeValueArea(FootprintBar bar, double tickSize, double vaPct = 0.70)
        {
            if (bar.Levels.Count == 0 || bar.TotalVol == 0) return (bar.High, bar.Low);
            var sorted = bar.Levels.OrderByDescending(kv => kv.Value.AskVol + kv.Value.BidVol).ToList();
            double target = bar.TotalVol * vaPct;
            double acc = 0;
            var ticksInVa = new List<double>();
            foreach (var kv in sorted)
            {
                acc += kv.Value.AskVol + kv.Value.BidVol;
                ticksInVa.Add(kv.Key);
                if (acc >= target) break;
            }
            if (ticksInVa.Count == 0) return (bar.High, bar.Low);
            return (ticksInVa.Max() + tickSize, ticksInVa.Min());
        }
    }
}
