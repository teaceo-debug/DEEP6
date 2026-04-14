// DEEP6 Footprint — FootprintBar & Cell data structures
// Port of deep6/state/footprint.py for NinjaTrader 8.
// See .planning/phases/16-*/PORT-SPEC.md for authoritative algorithm notes.

using System;
using System.Collections.Generic;
using System.Linq;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6
{
    public sealed class Cell
    {
        public long BidVol;
        public long AskVol;
        public long NeutralVol;

        public long TotalVol => BidVol + AskVol + NeutralVol;
        public long Delta    => AskVol - BidVol;
    }

    public sealed class FootprintBar
    {
        public int BarIndex;
        public double Open;
        public double High;
        public double Low;
        public double Close;
        public SortedDictionary<double, Cell> Levels = new SortedDictionary<double, Cell>();
        public long TotalVol;
        public long BarDelta;
        public long Cvd;
        public double PocPrice;
        public double BarRange;
        public long RunningDelta;
        public long MaxDelta;
        public long MinDelta;

        public void AddTrade(double price, long size, int aggressor)
        {
            if (size <= 0) return;
            Cell lv;
            if (!Levels.TryGetValue(price, out lv))
            {
                lv = new Cell();
                Levels[price] = lv;
            }

            if (aggressor == 1)        // buy (hit ask)
            {
                lv.AskVol += size;
                RunningDelta += size;
            }
            else if (aggressor == 2)   // sell (hit bid)
            {
                lv.BidVol += size;
                RunningDelta -= size;
            }
            else                       // unclassified (between spread)
            {
                lv.NeutralVol += size;
            }

            if (RunningDelta > MaxDelta) MaxDelta = RunningDelta;
            if (RunningDelta < MinDelta) MinDelta = RunningDelta;

            if (Open == 0) Open = price;
            if (price > High) High = price;
            if (Low == 0 || price < Low) Low = price;
            Close = price;
            TotalVol += size;
        }

        public void Finalize(long priorCvd)
        {
            BarDelta = 0;
            double bestPx = 0;
            long bestVol = -1;
            foreach (var kv in Levels)
            {
                BarDelta += kv.Value.AskVol - kv.Value.BidVol;
                long v = kv.Value.AskVol + kv.Value.BidVol;
                if (v > bestVol) { bestVol = v; bestPx = kv.Key; }
            }
            if (Levels.Count > 0) PocPrice = bestPx;
            BarRange = High - Low;
            if (BarRange < 0) BarRange = 0;
            Cvd = priorCvd + BarDelta;
        }

        // 70% Value Area. Returns (VAH, VAL).
        // Port of deep6/engines/poc.py:231-257.
        public static (double vah, double val) ComputeValueArea(FootprintBar bar, double tickSize, double vaPct = 0.70)
        {
            if (bar.Levels.Count == 0 || bar.TotalVol == 0) return (bar.High, bar.Low);
            var sorted = bar.Levels
                .OrderByDescending(kv => kv.Value.AskVol + kv.Value.BidVol)
                .ToList();
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

        // Delta conviction scalar used by delta-family signals.
        // Port of deep6/state/footprint.py:134-161.
        public double DeltaQualityScalar()
        {
            long extreme = Math.Max(Math.Max(Math.Abs(MaxDelta), Math.Abs(MinDelta)), 1);
            if (RunningDelta == 0 && extreme <= 1) return 1.0;
            double ratio = Math.Abs((double)RunningDelta) / extreme;
            if (ratio >= 0.95) return 1.15;
            if (ratio <= 0.35) return 0.7;
            // linear: (0.35, 0.7) → (0.95, 1.15)
            return 0.7 + (ratio - 0.35) * (1.15 - 0.7) / (0.95 - 0.35);
        }
    }
}
