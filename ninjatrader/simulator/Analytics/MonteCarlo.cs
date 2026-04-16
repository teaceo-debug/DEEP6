// MonteCarlo: Trade resampling for drawdown distribution analysis.
//
// Shuffles the order of trades 10,000 times, computes drawdown distribution.
// Answers: "What's the worst drawdown I should expect?"
//
// Usage:
//   var mc = MonteCarlo.Run(trades, iterations: 10000);
//   MonteCarlo.PrintReport(mc);

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;

namespace NinjaScriptSim.Lifecycle
{
    public class MonteCarloResult
    {
        public int Iterations { get; set; }
        public int TradeCount { get; set; }
        public double OriginalPnl { get; set; }
        public double OriginalMaxDrawdown { get; set; }

        // Drawdown distribution (percentiles)
        public double DrawdownP50 { get; set; }     // median
        public double DrawdownP75 { get; set; }
        public double DrawdownP90 { get; set; }
        public double DrawdownP95 { get; set; }
        public double DrawdownP99 { get; set; }
        public double DrawdownWorst { get; set; }

        // Final equity distribution
        public double EquityP5 { get; set; }        // worst 5%
        public double EquityP25 { get; set; }
        public double EquityP50 { get; set; }       // median
        public double EquityP75 { get; set; }
        public double EquityP95 { get; set; }

        // Probability of ruin
        public double ProbOfBreakeven { get; set; }  // P(final equity > 0)
        public double ProbOfDoubleDrawdown { get; set; } // P(drawdown > 2x original)

        // Raw distributions (for CSV export)
        public double[] DrawdownDistribution { get; set; }
        public double[] EquityDistribution { get; set; }
    }

    public static class MonteCarlo
    {
        /// <summary>
        /// Run Monte Carlo simulation by reshuffling trade order.
        /// </summary>
        /// <param name="trades">List of trade P&L values (in dollars or ticks).</param>
        /// <param name="iterations">Number of random permutations. Default 10,000.</param>
        /// <param name="seed">Random seed for reproducibility. -1 = random.</param>
        public static MonteCarloResult Run(List<double> trades, int iterations = 10000, int seed = 42)
        {
            if (trades.Count == 0)
                return new MonteCarloResult { Iterations = iterations, TradeCount = 0 };

            var rng = seed >= 0 ? new Random(seed) : new Random();
            var drawdowns = new double[iterations];
            var finalEquities = new double[iterations];

            double originalPnl = trades.Sum();
            double originalMdd = MaxDrawdown(trades);

            for (int iter = 0; iter < iterations; iter++)
            {
                // Fisher-Yates shuffle
                var shuffled = trades.ToArray();
                for (int i = shuffled.Length - 1; i > 0; i--)
                {
                    int j = rng.Next(i + 1);
                    (shuffled[i], shuffled[j]) = (shuffled[j], shuffled[i]);
                }

                drawdowns[iter] = MaxDrawdown(shuffled);
                finalEquities[iter] = shuffled.Sum();
            }

            Array.Sort(drawdowns);
            Array.Sort(finalEquities);

            return new MonteCarloResult
            {
                Iterations = iterations,
                TradeCount = trades.Count,
                OriginalPnl = originalPnl,
                OriginalMaxDrawdown = originalMdd,

                DrawdownP50 = Percentile(drawdowns, 0.50),
                DrawdownP75 = Percentile(drawdowns, 0.75),
                DrawdownP90 = Percentile(drawdowns, 0.90),
                DrawdownP95 = Percentile(drawdowns, 0.95),
                DrawdownP99 = Percentile(drawdowns, 0.99),
                DrawdownWorst = drawdowns[drawdowns.Length - 1],

                EquityP5 = Percentile(finalEquities, 0.05),
                EquityP25 = Percentile(finalEquities, 0.25),
                EquityP50 = Percentile(finalEquities, 0.50),
                EquityP75 = Percentile(finalEquities, 0.75),
                EquityP95 = Percentile(finalEquities, 0.95),

                ProbOfBreakeven = (double)finalEquities.Count(e => e > 0) / iterations * 100,
                ProbOfDoubleDrawdown = (double)drawdowns.Count(d => d > originalMdd * 2) / iterations * 100,

                DrawdownDistribution = drawdowns,
                EquityDistribution = finalEquities,
            };
        }

        /// <summary>
        /// Parse trade P&L from strategy PrintLog.
        /// Extracts DRY-RUN and LIVE entries, estimates P&L from subsequent bars.
        /// </summary>
        public static List<double> ExtractTradesFromLog(IReadOnlyList<string> printLog)
        {
            var trades = new List<double>();
            // The strategy prints entry/exit info. Parse it.
            double entryPrice = 0;
            int direction = 0;
            bool inTrade = false;

            foreach (var line in printLog)
            {
                if (line.Contains("DRY-RUN entry:") || line.Contains("LIVE entry CONFIRMED:"))
                {
                    // Parse direction and price
                    if (line.Contains("LONG")) direction = 1;
                    else if (line.Contains("SHORT")) direction = -1;
                    else continue;

                    // Extract price after "@ signal price"
                    int atIdx = line.IndexOf("@ signal price ", StringComparison.Ordinal);
                    if (atIdx < 0) atIdx = line.IndexOf("@ ", StringComparison.Ordinal);
                    if (atIdx >= 0)
                    {
                        string priceStr = line.Substring(atIdx).Split(' ').FirstOrDefault(s =>
                            double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out _));
                        if (priceStr != null)
                            double.TryParse(priceStr, NumberStyles.Float, CultureInfo.InvariantCulture, out entryPrice);
                    }
                    inTrade = true;
                }
                else if (inTrade && (line.Contains("Position flat") || line.Contains("EXIT")))
                {
                    // Exit — record trade (P&L unknown without fill price, use 0 as placeholder)
                    trades.Add(0);
                    inTrade = false;
                }
            }

            // If still in trade at end, close it
            if (inTrade) trades.Add(0);

            return trades;
        }

        private static double MaxDrawdown(IEnumerable<double> trades)
        {
            double peak = 0, equity = 0, maxDd = 0;
            foreach (var t in trades)
            {
                equity += t;
                if (equity > peak) peak = equity;
                double dd = peak - equity;
                if (dd > maxDd) maxDd = dd;
            }
            return maxDd;
        }

        private static double MaxDrawdown(double[] trades)
        {
            double peak = 0, equity = 0, maxDd = 0;
            foreach (var t in trades)
            {
                equity += t;
                if (equity > peak) peak = equity;
                double dd = peak - equity;
                if (dd > maxDd) maxDd = dd;
            }
            return maxDd;
        }

        private static double Percentile(double[] sorted, double p)
        {
            if (sorted.Length == 0) return 0;
            double idx = p * (sorted.Length - 1);
            int lower = (int)System.Math.Floor(idx);
            int upper = (int)System.Math.Ceiling(idx);
            if (lower == upper) return sorted[lower];
            double frac = idx - lower;
            return sorted[lower] * (1 - frac) + sorted[upper] * frac;
        }

        public static void PrintReport(MonteCarloResult mc)
        {
            Console.WriteLine($"  Trades: {mc.TradeCount}, Iterations: {mc.Iterations}");
            Console.WriteLine($"  Original P&L: ${mc.OriginalPnl:F2}, Original Max DD: ${mc.OriginalMaxDrawdown:F2}");
            Console.WriteLine();
            Console.WriteLine("  ── Drawdown Distribution ──");
            Console.WriteLine($"    50th percentile (median): ${mc.DrawdownP50:F2}");
            Console.WriteLine($"    75th percentile:          ${mc.DrawdownP75:F2}");
            Console.WriteLine($"    90th percentile:          ${mc.DrawdownP90:F2}");
            Console.WriteLine($"    95th percentile:          ${mc.DrawdownP95:F2}");
            Console.WriteLine($"    99th percentile:          ${mc.DrawdownP99:F2}");
            Console.WriteLine($"    Worst case:               ${mc.DrawdownWorst:F2}");
            Console.WriteLine();
            Console.WriteLine("  ── Equity Distribution ──");
            Console.WriteLine($"    5th percentile (worst):   ${mc.EquityP5:F2}");
            Console.WriteLine($"    25th percentile:          ${mc.EquityP25:F2}");
            Console.WriteLine($"    50th percentile (median): ${mc.EquityP50:F2}");
            Console.WriteLine($"    75th percentile:          ${mc.EquityP75:F2}");
            Console.WriteLine($"    95th percentile (best):   ${mc.EquityP95:F2}");
            Console.WriteLine();
            Console.WriteLine($"  Prob of breakeven (P&L > 0):      {mc.ProbOfBreakeven:F1}%");
            Console.WriteLine($"  Prob of 2x max drawdown:          {mc.ProbOfDoubleDrawdown:F1}%");
        }

        public static void ExportCsv(MonteCarloResult mc, string outputPath)
        {
            using var writer = new StreamWriter(outputPath);
            writer.WriteLine("iteration,max_drawdown,final_equity");
            for (int i = 0; i < mc.DrawdownDistribution.Length; i++)
            {
                writer.WriteLine(string.Format(CultureInfo.InvariantCulture,
                    "{0},{1:F2},{2:F2}", i, mc.DrawdownDistribution[i], mc.EquityDistribution[i]));
            }
        }
    }
}
