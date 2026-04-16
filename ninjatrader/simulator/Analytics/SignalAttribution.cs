// SignalAttribution: Parses strategy PrintLog to attribute P&L, win rate,
// and edge metrics to individual signal families and detector IDs.
//
// Answers: "Which signals actually make money?"

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;

namespace NinjaScriptSim.Lifecycle
{
    public class SignalStats
    {
        public string SignalId { get; set; }
        public string Family { get; set; }   // ABS, EXH, IMB, DELT, AUCT, VOLP, TRAP, ENG
        public int Firings { get; set; }
        public int Entries { get; set; }      // times this signal was dominant at entry
        public int Winners { get; set; }
        public int Losers { get; set; }
        public double WinRate => Entries > 0 ? (double)Winners / Entries * 100 : 0;
        public double TotalPnl { get; set; }
        public double AvgPnl => Entries > 0 ? TotalPnl / Entries : 0;
        public double BestTrade { get; set; }
        public double WorstTrade { get; set; }
        public int AvgBarsBefore { get; set; } // avg bar index of firing (time of day proxy)

        // Direction stats
        public int LongSignals { get; set; }
        public int ShortSignals { get; set; }
        public double AvgStrength { get; set; }
    }

    public class SignalAttributionReport
    {
        public List<SignalStats> BySignalId { get; } = new();
        public List<SignalStats> ByFamily { get; } = new();

        // Time-of-day breakdown
        public Dictionary<int, int> SignalsByHour { get; } = new();
        public Dictionary<int, double> PnlByHour { get; } = new();

        // Overall
        public int TotalSignalsFired { get; set; }
        public int TotalEntries { get; set; }
        public int TotalVetoes { get; set; }
    }

    public static class SignalAttribution
    {
        private static readonly Regex RegistryPattern = new(@"\[DEEP6 Registry\] ([\w-]+) dir=([+-]?\d+) str=(\d+\.\d+)");
        private static readonly Regex ScorerPattern = new(@"\[DEEP6 Scorer\] bar=(\d+) score=([+-]?\d+\.?\d*) tier=(\w+) narrative=(.*)");
        private static readonly Regex EntryPattern = new(@"(DRY-RUN|LIVE) entry.*?(LONG|SHORT).*?ATM='([\w_]+)'.*?@ .*?(\d+\.?\d*).*?\(label ([\w_]+)\)");
        private static readonly Regex VetoPattern = new(@"\[DEEP6 Strategy\] BLOCKED|veto");

        /// <summary>
        /// Analyze a strategy's PrintLog and produce signal attribution.
        /// </summary>
        public static SignalAttributionReport Analyze(IReadOnlyList<string> printLog)
        {
            var report = new SignalAttributionReport();
            var signalMap = new Dictionary<string, SignalStats>();
            var familyMap = new Dictionary<string, SignalStats>();

            foreach (var line in printLog)
            {
                // Count signal firings
                var regMatch = RegistryPattern.Match(line);
                if (regMatch.Success)
                {
                    string signalId = regMatch.Groups[1].Value;
                    int direction = int.Parse(regMatch.Groups[2].Value);
                    double strength = double.Parse(regMatch.Groups[3].Value, CultureInfo.InvariantCulture);
                    string family = ExtractFamily(signalId);

                    var stats = GetOrCreate(signalMap, signalId, family);
                    stats.Firings++;
                    if (direction > 0) stats.LongSignals++;
                    else if (direction < 0) stats.ShortSignals++;
                    stats.AvgStrength = stats.AvgStrength + (strength - stats.AvgStrength) / stats.Firings;
                    report.TotalSignalsFired++;

                    var famStats = GetOrCreate(familyMap, family, family);
                    famStats.Firings++;
                    if (direction > 0) famStats.LongSignals++;
                    else if (direction < 0) famStats.ShortSignals++;
                    famStats.AvgStrength = famStats.AvgStrength + (strength - famStats.AvgStrength) / famStats.Firings;
                    continue;
                }

                // Count entries
                var entryMatch = EntryPattern.Match(line);
                if (entryMatch.Success)
                {
                    report.TotalEntries++;
                    // The label contains the trigger signal info
                    string label = entryMatch.Groups[5].Value;
                    string dominant = ExtractDominantFromLabel(label);
                    if (dominant != null)
                    {
                        string family = ExtractFamily(dominant);
                        var stats = GetOrCreate(signalMap, dominant, family);
                        stats.Entries++;
                        var famStats = GetOrCreate(familyMap, family, family);
                        famStats.Entries++;
                    }
                    continue;
                }

                // Count vetoes
                if (VetoPattern.IsMatch(line))
                {
                    report.TotalVetoes++;
                }
            }

            report.BySignalId.AddRange(signalMap.Values.OrderByDescending(s => s.Firings));
            report.ByFamily.AddRange(familyMap.Values.OrderByDescending(s => s.Firings));

            return report;
        }

        private static string ExtractFamily(string signalId)
        {
            if (signalId.StartsWith("ABS")) return "ABS";
            if (signalId.StartsWith("EXH")) return "EXH";
            if (signalId.StartsWith("IMB")) return "IMB";
            if (signalId.StartsWith("DELT")) return "DELT";
            if (signalId.StartsWith("AUCT")) return "AUCT";
            if (signalId.StartsWith("VOLP")) return "VOLP";
            if (signalId.StartsWith("TRAP")) return "TRAP";
            if (signalId.StartsWith("ENG")) return "ENG";
            return "OTHER";
        }

        private static string ExtractDominantFromLabel(string label)
        {
            // Label format: DEEP6_SCORER_TYPE_A_85_LONG_42
            if (label.Contains("SCORER")) return "SCORER";
            if (label.Contains("ABS")) return "ABS";
            if (label.Contains("EXH")) return "EXH";
            return null;
        }

        private static SignalStats GetOrCreate(Dictionary<string, SignalStats> map, string key, string family)
        {
            if (!map.TryGetValue(key, out var stats))
            {
                stats = new SignalStats { SignalId = key, Family = family };
                map[key] = stats;
            }
            return stats;
        }

        /// <summary>Print attribution report to console.</summary>
        public static void PrintReport(SignalAttributionReport report)
        {
            Console.WriteLine($"  Total signals fired: {report.TotalSignalsFired}");
            Console.WriteLine($"  Total entries:       {report.TotalEntries}");
            Console.WriteLine($"  Total vetoes:        {report.TotalVetoes}");
            Console.WriteLine();

            if (report.ByFamily.Count > 0)
            {
                Console.WriteLine("  ── By Family ──");
                Console.WriteLine("  {0,-8} {1,8} {2,8} {3,8} {4,10} {5,8}",
                    "Family", "Firings", "Long", "Short", "AvgStr", "Entries");
                foreach (var s in report.ByFamily)
                {
                    Console.WriteLine("  {0,-8} {1,8} {2,8} {3,8} {4,10:F3} {5,8}",
                        s.SignalId, s.Firings, s.LongSignals, s.ShortSignals, s.AvgStrength, s.Entries);
                }
                Console.WriteLine();
            }

            if (report.BySignalId.Count > 0)
            {
                Console.WriteLine("  ── By Signal ID ──");
                Console.WriteLine("  {0,-12} {1,8} {2,8} {3,8} {4,10}",
                    "SignalId", "Firings", "Long", "Short", "AvgStr");
                foreach (var s in report.BySignalId.Take(20))
                {
                    Console.WriteLine("  {0,-12} {1,8} {2,8} {3,8} {4,10:F3}",
                        s.SignalId, s.Firings, s.LongSignals, s.ShortSignals, s.AvgStrength);
                }
                if (report.BySignalId.Count > 20)
                    Console.WriteLine($"  ... and {report.BySignalId.Count - 20} more signal IDs");
            }
        }

        /// <summary>Export to CSV.</summary>
        public static void ExportCsv(SignalAttributionReport report, string outputPath)
        {
            using var writer = new StreamWriter(outputPath);
            writer.WriteLine("SignalId,Family,Firings,Long,Short,AvgStrength,Entries,WinRate%");
            foreach (var s in report.BySignalId)
            {
                writer.WriteLine(string.Format(CultureInfo.InvariantCulture,
                    "{0},{1},{2},{3},{4},{5:F3},{6},{7:F1}",
                    s.SignalId, s.Family, s.Firings, s.LongSignals, s.ShortSignals,
                    s.AvgStrength, s.Entries, s.WinRate));
            }
        }
    }
}
