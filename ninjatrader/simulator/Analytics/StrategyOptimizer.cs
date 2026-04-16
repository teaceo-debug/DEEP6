// StrategyOptimizer: Parallel parameter sweep engine for DEEP6Strategy.
//
// Runs the strategy across all combinations of parameter values, ranks by
// Sharpe ratio / profit factor / net P&L, and exports results to CSV.
//
// Usage:
//   var optimizer = new StrategyOptimizer();
//   optimizer.AddSweep("ScoreEntryThreshold", 50, 90, 5);
//   optimizer.AddSweep("StopLossTicks", 12, 30, 2);
//   var results = optimizer.Run(sessionData);
//   optimizer.ExportCsv(results, "optimization.csv");

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading.Tasks;

namespace NinjaScriptSim.Lifecycle
{
    public class ParameterSweep
    {
        public string Name { get; set; }
        public double From { get; set; }
        public double To { get; set; }
        public double Step { get; set; }

        public IEnumerable<double> Values()
        {
            for (double v = From; v <= To + Step * 0.001; v += Step)
                yield return System.Math.Round(v, 6);
        }

        public int Count => (int)((To - From) / Step) + 1;
    }

    public class OptimizationResult
    {
        public Dictionary<string, double> Parameters { get; set; } = new();
        public int TotalTrades { get; set; }
        public int Winners { get; set; }
        public int Losers { get; set; }
        public double WinRate => TotalTrades > 0 ? (double)Winners / TotalTrades * 100 : 0;
        public double NetPnl { get; set; }
        public double GrossProfit { get; set; }
        public double GrossLoss { get; set; }
        public double ProfitFactor => GrossLoss != 0 ? System.Math.Abs(GrossProfit / GrossLoss) : GrossProfit > 0 ? 999 : 0;
        public double MaxDrawdown { get; set; }
        public double SharpeRatio { get; set; }
        public double AvgWin { get; set; }
        public double AvgLoss { get; set; }
        public int BarsProcessed { get; set; }
        public List<string> Errors { get; set; } = new();
    }

    public class StrategyOptimizer
    {
        private readonly List<ParameterSweep> _sweeps = new();
        public int MaxParallelism { get; set; } = Environment.ProcessorCount;

        public void AddSweep(string paramName, double from, double to, double step)
        {
            _sweeps.Add(new ParameterSweep { Name = paramName, From = from, To = to, Step = step });
        }

        public int TotalCombinations => _sweeps.Aggregate(1, (acc, s) => acc * s.Count);

        /// <summary>
        /// Run all parameter combinations against the given session data.
        /// Uses Parallel.ForEach for multi-core execution.
        /// </summary>
        public List<OptimizationResult> Run(SessionData session)
        {
            var combos = GenerateCombinations();
            var results = new List<OptimizationResult>(combos.Count);
            var lockObj = new object();

            Parallel.ForEach(combos, new ParallelOptions { MaxDegreeOfParallelism = MaxParallelism }, combo =>
            {
                var result = RunSingle(session, combo);
                lock (lockObj) { results.Add(result); }
            });

            return results.OrderByDescending(r => r.SharpeRatio).ToList();
        }

        private OptimizationResult RunSingle(SessionData session, Dictionary<string, double> parameters)
        {
            var runner = new NinjaScriptRunner();
            runner.LoadBars(session.Bars);
            runner.LoadDepthUpdates(session.DepthUpdates);

            var result = new OptimizationResult { Parameters = parameters };

            try
            {
                var script = runner.Run<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>();

                // Apply parameters via reflection on the strategy
                foreach (var kv in parameters)
                {
                    var prop = script.GetType().GetProperty(kv.Key);
                    if (prop != null)
                    {
                        if (prop.PropertyType == typeof(int))
                            prop.SetValue(script, (int)kv.Value);
                        else if (prop.PropertyType == typeof(double))
                            prop.SetValue(script, kv.Value);
                        else if (prop.PropertyType == typeof(bool))
                            prop.SetValue(script, kv.Value != 0);
                    }
                }

                // Parse trades from PrintLog
                var trades = ParseTrades(script.PrintLog);
                result.BarsProcessed = session.Bars.Count;
                result.TotalTrades = trades.Count;
                result.Winners = trades.Count(t => t > 0);
                result.Losers = trades.Count(t => t < 0);
                result.GrossProfit = trades.Where(t => t > 0).Sum();
                result.GrossLoss = trades.Where(t => t < 0).Sum();
                result.NetPnl = trades.Sum();
                result.AvgWin = result.Winners > 0 ? result.GrossProfit / result.Winners : 0;
                result.AvgLoss = result.Losers > 0 ? result.GrossLoss / result.Losers : 0;
                result.MaxDrawdown = ComputeMaxDrawdown(trades);
                result.SharpeRatio = ComputeSharpe(trades);
                result.Errors = runner.Errors;
            }
            catch (Exception ex)
            {
                result.Errors.Add(ex.Message);
            }

            return result;
        }

        /// <summary>Parse trade P&L from strategy Print() output.</summary>
        private static List<double> ParseTrades(IReadOnlyList<string> printLog)
        {
            var trades = new List<double>();
            // Look for DRY-RUN or LIVE entry/exit patterns
            // The strategy prints entry prices and exit would show P&L
            // For now, count entries as trade signals
            foreach (var line in printLog)
            {
                if (line.Contains("DRY-RUN entry:") || line.Contains("LIVE entry CONFIRMED:"))
                    trades.Add(0); // Placeholder — real P&L requires fill simulation
            }
            return trades;
        }

        private static double ComputeMaxDrawdown(List<double> trades)
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

        private static double ComputeSharpe(List<double> trades)
        {
            if (trades.Count < 2) return 0;
            double mean = trades.Average();
            double variance = trades.Sum(t => (t - mean) * (t - mean)) / (trades.Count - 1);
            double stdDev = System.Math.Sqrt(variance);
            return stdDev > 0 ? mean / stdDev * System.Math.Sqrt(252) : 0; // Annualized
        }

        private List<Dictionary<string, double>> GenerateCombinations()
        {
            var combos = new List<Dictionary<string, double>>();
            GenerateCombosRecursive(combos, new Dictionary<string, double>(), 0);
            return combos;
        }

        private void GenerateCombosRecursive(List<Dictionary<string, double>> combos,
            Dictionary<string, double> current, int sweepIdx)
        {
            if (sweepIdx >= _sweeps.Count)
            {
                combos.Add(new Dictionary<string, double>(current));
                return;
            }
            var sweep = _sweeps[sweepIdx];
            foreach (double val in sweep.Values())
            {
                current[sweep.Name] = val;
                GenerateCombosRecursive(combos, current, sweepIdx + 1);
            }
            current.Remove(sweep.Name);
        }

        /// <summary>Export results to CSV.</summary>
        public static void ExportCsv(List<OptimizationResult> results, string outputPath)
        {
            using var writer = new StreamWriter(outputPath);

            // Header
            var paramNames = results.FirstOrDefault()?.Parameters.Keys.ToList() ?? new List<string>();
            var header = string.Join(",", paramNames.Concat(new[]
            {
                "Trades", "WinRate%", "NetPnl", "ProfitFactor", "SharpeRatio",
                "MaxDrawdown", "GrossProfit", "GrossLoss", "AvgWin", "AvgLoss"
            }));
            writer.WriteLine(header);

            foreach (var r in results)
            {
                var paramVals = paramNames.Select(n => r.Parameters.GetValueOrDefault(n, 0).ToString(CultureInfo.InvariantCulture));
                var metrics = new[]
                {
                    r.TotalTrades.ToString(),
                    r.WinRate.ToString("F1", CultureInfo.InvariantCulture),
                    r.NetPnl.ToString("F2", CultureInfo.InvariantCulture),
                    r.ProfitFactor.ToString("F2", CultureInfo.InvariantCulture),
                    r.SharpeRatio.ToString("F3", CultureInfo.InvariantCulture),
                    r.MaxDrawdown.ToString("F2", CultureInfo.InvariantCulture),
                    r.GrossProfit.ToString("F2", CultureInfo.InvariantCulture),
                    r.GrossLoss.ToString("F2", CultureInfo.InvariantCulture),
                    r.AvgWin.ToString("F2", CultureInfo.InvariantCulture),
                    r.AvgLoss.ToString("F2", CultureInfo.InvariantCulture),
                };
                writer.WriteLine(string.Join(",", paramVals.Concat(metrics)));
            }
        }
    }
}
