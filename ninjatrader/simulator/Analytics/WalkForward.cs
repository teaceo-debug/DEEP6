// WalkForward: Rolling in-sample / out-of-sample analyzer.
//
// Splits session data into windows, optimizes on in-sample, validates on
// out-of-sample, rolls forward. Detects overfitting.
//
// Usage:
//   var wf = new WalkForwardAnalyzer(inSampleBars: 200, outOfSampleBars: 50);
//   wf.AddSweep("ScoreEntryThreshold", 50, 90, 10);
//   var results = wf.Run(session);

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;

namespace NinjaScriptSim.Lifecycle
{
    public class WalkForwardWindow
    {
        public int WindowIndex { get; set; }
        public int InSampleStart { get; set; }
        public int InSampleEnd { get; set; }
        public int OutOfSampleStart { get; set; }
        public int OutOfSampleEnd { get; set; }

        // Best parameters from in-sample optimization
        public Dictionary<string, double> BestParams { get; set; } = new();
        public double InSampleSharpe { get; set; }
        public double InSamplePnl { get; set; }
        public int InSampleTrades { get; set; }

        // Out-of-sample results using those parameters
        public double OutOfSampleSharpe { get; set; }
        public double OutOfSamplePnl { get; set; }
        public int OutOfSampleTrades { get; set; }

        // Overfit ratio: OOS_Sharpe / IS_Sharpe. Below 0.5 = likely overfit.
        public double OverfitRatio => InSampleSharpe > 0 ? OutOfSampleSharpe / InSampleSharpe : 0;
    }

    public class WalkForwardReport
    {
        public List<WalkForwardWindow> Windows { get; } = new();
        public int InSampleSize { get; set; }
        public int OutOfSampleSize { get; set; }
        public int StepSize { get; set; }

        // Aggregate metrics
        public double AvgOverfitRatio => Windows.Count > 0 ? Windows.Average(w => w.OverfitRatio) : 0;
        public double TotalOosPnl => Windows.Sum(w => w.OutOfSamplePnl);
        public double AvgOosSharpe => Windows.Count > 0 ? Windows.Average(w => w.OutOfSampleSharpe) : 0;
        public int WindowsWithPositiveOos => Windows.Count(w => w.OutOfSamplePnl > 0);
        public bool IsRobust => AvgOverfitRatio >= 0.5 && WindowsWithPositiveOos >= Windows.Count * 0.6;
    }

    public class WalkForwardAnalyzer
    {
        private readonly int _inSampleBars;
        private readonly int _outOfSampleBars;
        private readonly int _stepBars;
        private readonly StrategyOptimizer _optimizer = new();

        /// <param name="inSampleBars">Bars in each in-sample window.</param>
        /// <param name="outOfSampleBars">Bars in each out-of-sample window.</param>
        /// <param name="stepBars">Bars to advance per window. Defaults to outOfSampleBars.</param>
        public WalkForwardAnalyzer(int inSampleBars = 200, int outOfSampleBars = 50, int stepBars = 0)
        {
            _inSampleBars = inSampleBars;
            _outOfSampleBars = outOfSampleBars;
            _stepBars = stepBars > 0 ? stepBars : outOfSampleBars;
        }

        public void AddSweep(string paramName, double from, double to, double step)
        {
            _optimizer.AddSweep(paramName, from, to, step);
        }

        public WalkForwardReport Run(SessionData fullSession)
        {
            var report = new WalkForwardReport
            {
                InSampleSize = _inSampleBars,
                OutOfSampleSize = _outOfSampleBars,
                StepSize = _stepBars,
            };

            int totalBars = fullSession.Bars.Count;
            int windowIdx = 0;

            for (int start = 0; start + _inSampleBars + _outOfSampleBars <= totalBars; start += _stepBars)
            {
                int isStart = start;
                int isEnd = start + _inSampleBars;
                int oosStart = isEnd;
                int oosEnd = System.Math.Min(oosStart + _outOfSampleBars, totalBars);

                // Extract in-sample data
                var isSession = SliceSession(fullSession, isStart, isEnd);
                var oosSession = SliceSession(fullSession, oosStart, oosEnd);

                // Optimize on in-sample
                var isResults = _optimizer.Run(isSession);
                var best = isResults.FirstOrDefault();

                var window = new WalkForwardWindow
                {
                    WindowIndex = windowIdx++,
                    InSampleStart = isStart,
                    InSampleEnd = isEnd,
                    OutOfSampleStart = oosStart,
                    OutOfSampleEnd = oosEnd,
                    BestParams = best?.Parameters ?? new(),
                    InSampleSharpe = best?.SharpeRatio ?? 0,
                    InSamplePnl = best?.NetPnl ?? 0,
                    InSampleTrades = best?.TotalTrades ?? 0,
                };

                // Test best params on out-of-sample
                if (best != null)
                {
                    var oosResults = _optimizer.Run(oosSession);
                    // Find the result with matching parameters
                    var oosMatch = oosResults.FirstOrDefault(r =>
                        best.Parameters.All(kv => r.Parameters.GetValueOrDefault(kv.Key) == kv.Value));

                    if (oosMatch != null)
                    {
                        window.OutOfSampleSharpe = oosMatch.SharpeRatio;
                        window.OutOfSamplePnl = oosMatch.NetPnl;
                        window.OutOfSampleTrades = oosMatch.TotalTrades;
                    }
                }

                report.Windows.Add(window);
            }

            return report;
        }

        private static SessionData SliceSession(SessionData full, int startBar, int endBar)
        {
            var sliced = new SessionData();
            for (int i = startBar; i < endBar && i < full.Bars.Count; i++)
                sliced.Bars.Add(full.Bars[i]);
            // Include depth updates that fall within the bar time range
            if (sliced.Bars.Count > 0)
            {
                var startTime = sliced.Bars[0].Time;
                var endTime = sliced.Bars[sliced.Bars.Count - 1].Time;
                sliced.DepthUpdates.AddRange(
                    full.DepthUpdates.Where(d => d.Time >= startTime && d.Time <= endTime));
            }
            return sliced;
        }

        public static void PrintReport(WalkForwardReport report)
        {
            Console.WriteLine($"  Windows: {report.Windows.Count} (IS={report.InSampleSize} bars, OOS={report.OutOfSampleSize} bars, step={report.StepSize})");
            Console.WriteLine();
            Console.WriteLine("  {0,4} {1,10} {2,10} {3,10} {4,10} {5,10}",
                "#", "IS Sharpe", "OOS Sharpe", "IS PnL", "OOS PnL", "Overfit%");
            foreach (var w in report.Windows)
            {
                Console.WriteLine("  {0,4} {1,10:F3} {2,10:F3} {3,10:F2} {4,10:F2} {5,10:F1}%",
                    w.WindowIndex, w.InSampleSharpe, w.OutOfSampleSharpe,
                    w.InSamplePnl, w.OutOfSamplePnl, w.OverfitRatio * 100);
            }
            Console.WriteLine();
            Console.WriteLine($"  Average overfit ratio: {report.AvgOverfitRatio:F2} (>0.5 = robust)");
            Console.WriteLine($"  OOS positive windows:  {report.WindowsWithPositiveOos}/{report.Windows.Count}");
            Console.WriteLine($"  Total OOS P&L:         ${report.TotalOosPnl:F2}");
            Console.WriteLine($"  Verdict: {(report.IsRobust ? "ROBUST — parameters generalize" : "OVERFIT — parameters don't generalize")}");
        }

        public static void ExportCsv(WalkForwardReport report, string outputPath)
        {
            using var writer = new StreamWriter(outputPath);
            writer.WriteLine("Window,IS_Start,IS_End,OOS_Start,OOS_End,IS_Sharpe,OOS_Sharpe,IS_PnL,OOS_PnL,OverfitRatio");
            foreach (var w in report.Windows)
            {
                writer.WriteLine(string.Format(CultureInfo.InvariantCulture,
                    "{0},{1},{2},{3},{4},{5:F3},{6:F3},{7:F2},{8:F2},{9:F3}",
                    w.WindowIndex, w.InSampleStart, w.InSampleEnd, w.OutOfSampleStart, w.OutOfSampleEnd,
                    w.InSampleSharpe, w.OutOfSampleSharpe, w.InSamplePnl, w.OutOfSamplePnl, w.OverfitRatio));
            }
        }
    }
}
