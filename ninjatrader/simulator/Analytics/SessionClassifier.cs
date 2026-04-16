// SessionClassifier: Clusters trading sessions by regime and outcome.
//
// For each session, computes market features (ATR, volume, delta, range),
// then classifies into regime types and correlates with P&L outcome.
//
// Answers: "What kind of days does this strategy work on?"

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;

namespace NinjaScriptSim.Lifecycle
{
    public enum SessionRegime
    {
        Trending,       // Strong directional move, high delta bias
        MeanReverting,  // Range-bound, delta oscillates
        HighVolatility, // ATR > 1.5x average
        LowVolatility,  // ATR < 0.5x average
        VolumeSurge,    // Volume > 2x average
        Quiet,          // Low volume + low ATR
    }

    public class SessionProfile
    {
        public int SessionIndex { get; set; }
        public DateTime Date { get; set; }
        public int BarCount { get; set; }

        // Market features
        public double AvgAtr { get; set; }
        public double AvgVolume { get; set; }
        public double TotalDelta { get; set; }
        public double SessionRange { get; set; }    // High - Low of entire session
        public double DeltaBias { get; set; }       // abs(TotalDelta) / TotalVolume
        public double VolatilityRank { get; set; }  // Percentile vs other sessions (0-100)

        // Strategy outcome
        public int Entries { get; set; }
        public int Vetoes { get; set; }
        public double NetPnl { get; set; }
        public int Winners { get; set; }
        public int Losers { get; set; }

        // Classification
        public SessionRegime PrimaryRegime { get; set; }
        public string Outcome { get; set; }  // "Profitable", "Flat", "Losing"
    }

    public class ClassificationReport
    {
        public List<SessionProfile> Sessions { get; } = new();

        // Regime → outcome correlation
        public Dictionary<SessionRegime, RegimeStats> ByRegime { get; } = new();

        public class RegimeStats
        {
            public int Count { get; set; }
            public int Profitable { get; set; }
            public int Losing { get; set; }
            public double AvgPnl { get; set; }
            public double WinRate => Count > 0 ? (double)Profitable / Count * 100 : 0;
            public List<double> PnlValues { get; } = new();
        }
    }

    public static class SessionClassifier
    {
        /// <summary>
        /// Classify sessions from multiple NDJSON files.
        /// Each file = one session.
        /// </summary>
        public static ClassificationReport Classify(string[] sessionPaths)
        {
            var report = new ClassificationReport();

            // First pass: compute features for each session
            for (int i = 0; i < sessionPaths.Length; i++)
            {
                var session = NdjsonSessionLoader.Load(sessionPaths[i]);
                var profile = ComputeProfile(session, i);
                profile.Date = session.Bars.Count > 0 ? session.Bars[0].Time.Date : DateTime.MinValue;

                // Run strategy to get outcome
                var runner = new NinjaScriptRunner();
                runner.LoadBars(session.Bars);
                runner.LoadDepthUpdates(session.DepthUpdates);
                try
                {
                    var script = runner.Run<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>();
                    profile.Entries = script.PrintLog.Count(l => l.Contains("entry"));
                    profile.Vetoes = script.PrintLog.Count(l => l.Contains("BLOCKED") || l.Contains("veto"));
                }
                catch { }

                report.Sessions.Add(profile);
            }

            // Second pass: compute volatility ranks
            var sortedByAtr = report.Sessions.OrderBy(s => s.AvgAtr).ToList();
            for (int i = 0; i < sortedByAtr.Count; i++)
                sortedByAtr[i].VolatilityRank = (double)i / System.Math.Max(sortedByAtr.Count - 1, 1) * 100;

            // Classify regimes
            double globalAvgAtr = report.Sessions.Count > 0 ? report.Sessions.Average(s => s.AvgAtr) : 1;
            double globalAvgVol = report.Sessions.Count > 0 ? report.Sessions.Average(s => s.AvgVolume) : 1;

            foreach (var s in report.Sessions)
            {
                s.PrimaryRegime = ClassifyRegime(s, globalAvgAtr, globalAvgVol);
                s.Outcome = s.NetPnl > 50 ? "Profitable" : s.NetPnl < -50 ? "Losing" : "Flat";
            }

            // Build regime → outcome map
            foreach (SessionRegime regime in Enum.GetValues(typeof(SessionRegime)))
            {
                var sessions = report.Sessions.Where(s => s.PrimaryRegime == regime).ToList();
                if (sessions.Count == 0) continue;

                report.ByRegime[regime] = new ClassificationReport.RegimeStats
                {
                    Count = sessions.Count,
                    Profitable = sessions.Count(s => s.Outcome == "Profitable"),
                    Losing = sessions.Count(s => s.Outcome == "Losing"),
                    AvgPnl = sessions.Average(s => s.NetPnl),
                };
                report.ByRegime[regime].PnlValues.AddRange(sessions.Select(s => s.NetPnl));
            }

            return report;
        }

        /// <summary>Classify a single session from SessionData (already loaded).</summary>
        public static SessionProfile ComputeProfile(SessionData session, int index = 0)
        {
            var profile = new SessionProfile { SessionIndex = index, BarCount = session.Bars.Count };

            if (session.Bars.Count == 0) return profile;

            double atrSum = 0;
            double volSum = 0;
            double deltaSum = 0;
            double sessionHigh = double.MinValue, sessionLow = double.MaxValue;

            foreach (var bar in session.Bars)
            {
                double range = bar.High - bar.Low;
                atrSum += range;
                volSum += bar.Volume;
                sessionHigh = System.Math.Max(sessionHigh, bar.High);
                sessionLow = System.Math.Min(sessionLow, bar.Low);

                // Estimate delta from ticks if available
                if (bar.Ticks != null)
                {
                    foreach (var t in bar.Ticks)
                    {
                        if (t.Aggressor == 1) deltaSum += t.Size;
                        else if (t.Aggressor == 2) deltaSum -= t.Size;
                    }
                }
            }

            profile.AvgAtr = session.Bars.Count > 0 ? atrSum / session.Bars.Count : 0;
            profile.AvgVolume = session.Bars.Count > 0 ? volSum / session.Bars.Count : 0;
            profile.TotalDelta = deltaSum;
            profile.SessionRange = sessionHigh - sessionLow;
            profile.DeltaBias = volSum > 0 ? System.Math.Abs(deltaSum) / volSum : 0;

            return profile;
        }

        private static SessionRegime ClassifyRegime(SessionProfile s, double avgAtr, double avgVol)
        {
            if (s.AvgAtr > avgAtr * 1.5) return SessionRegime.HighVolatility;
            if (s.AvgAtr < avgAtr * 0.5 && s.AvgVolume < avgVol * 0.5) return SessionRegime.Quiet;
            if (s.AvgAtr < avgAtr * 0.5) return SessionRegime.LowVolatility;
            if (s.AvgVolume > avgVol * 2.0) return SessionRegime.VolumeSurge;
            if (s.DeltaBias > 0.3) return SessionRegime.Trending;
            return SessionRegime.MeanReverting;
        }

        public static void PrintReport(ClassificationReport report)
        {
            Console.WriteLine($"  Sessions analyzed: {report.Sessions.Count}");
            Console.WriteLine();

            Console.WriteLine("  ── Session Profiles ──");
            Console.WriteLine("  {0,4} {1,10} {2,6} {3,8} {4,8} {5,8} {6,16} {7,10}",
                "#", "Date", "Bars", "AvgATR", "AvgVol", "Delta%", "Regime", "Outcome");
            foreach (var s in report.Sessions)
            {
                Console.WriteLine("  {0,4} {1,10} {2,6} {3,8:F2} {4,8:F0} {5,8:F1}% {6,16} {7,10}",
                    s.SessionIndex, s.Date.ToString("yyyy-MM-dd"), s.BarCount,
                    s.AvgAtr, s.AvgVolume, s.DeltaBias * 100, s.PrimaryRegime, s.Outcome);
            }
            Console.WriteLine();

            if (report.ByRegime.Count > 0)
            {
                Console.WriteLine("  ── Regime → Outcome ──");
                Console.WriteLine("  {0,16} {1,6} {2,10} {3,8} {4,10}",
                    "Regime", "Count", "WinRate%", "AvgPnl", "Profitable");
                foreach (var kv in report.ByRegime.OrderByDescending(r => r.Value.WinRate))
                {
                    Console.WriteLine("  {0,16} {1,6} {2,10:F1}% {3,8:F2} {4,10}",
                        kv.Key, kv.Value.Count, kv.Value.WinRate, kv.Value.AvgPnl,
                        $"{kv.Value.Profitable}/{kv.Value.Count}");
                }
            }
        }

        public static void ExportCsv(ClassificationReport report, string outputPath)
        {
            using var writer = new StreamWriter(outputPath);
            writer.WriteLine("Session,Date,Bars,AvgATR,AvgVolume,TotalDelta,DeltaBias,SessionRange,VolRank,Regime,Entries,Vetoes,NetPnl,Outcome");
            foreach (var s in report.Sessions)
            {
                writer.WriteLine(string.Format(CultureInfo.InvariantCulture,
                    "{0},{1},{2},{3:F2},{4:F0},{5:F0},{6:F3},{7:F2},{8:F1},{9},{10},{11},{12:F2},{13}",
                    s.SessionIndex, s.Date.ToString("yyyy-MM-dd"), s.BarCount,
                    s.AvgAtr, s.AvgVolume, s.TotalDelta, s.DeltaBias, s.SessionRange,
                    s.VolatilityRank, s.PrimaryRegime, s.Entries, s.Vetoes, s.NetPnl, s.Outcome));
            }
        }
    }
}
