// ParityChecker: Compares simulator Print() output against NT8's Output window
// to verify the simulator produces identical results.
//
// Usage:
//   1. Record a session from NT8 via bridge: bridge --record session.ndjson
//   2. Copy NT8's Output window to a text file: nt8-output.txt
//   3. Run parity check:
//      dotnet run --project ninjatrader/simulator -- parity session.ndjson nt8-output.txt

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;

namespace NinjaScriptSim.Lifecycle
{
    public class ParityDifference
    {
        public int LineNumber { get; set; }
        public string Category { get; set; } // "MISSING", "EXTRA", "MISMATCH"
        public string SimLine { get; set; }
        public string Nt8Line { get; set; }
        public string Detail { get; set; }
    }

    public class ParityReport
    {
        public int SimLineCount { get; set; }
        public int Nt8LineCount { get; set; }
        public int MatchedLines { get; set; }
        public int Differences { get; set; }
        public double MatchRate => SimLineCount > 0 ? (double)MatchedLines / System.Math.Max(SimLineCount, Nt8LineCount) * 100 : 0;
        public List<ParityDifference> Diffs { get; } = new();

        // Per-category counts
        public int SignalMatches { get; set; }
        public int SignalDiffs { get; set; }
        public int ScoreMatches { get; set; }
        public int ScoreDiffs { get; set; }
        public int EntryMatches { get; set; }
        public int EntryDiffs { get; set; }
        public int VetoMatches { get; set; }
        public int VetoDiffs { get; set; }

        public bool Passed => Differences == 0;
    }

    public static class ParityChecker
    {
        // Patterns to extract structured data from Print() lines
        private static readonly Regex ScorePattern = new(@"\[DEEP6 Scorer\] bar=(\d+) score=([+-]?\d+\.?\d*) tier=(\w+)");
        private static readonly Regex EntryPattern = new(@"(DRY-RUN|LIVE) entry.*?:\s*(LONG|SHORT).*?@ .*?(\d+\.\d+)");
        private static readonly Regex SignalPattern = new(@"\[DEEP6 Registry\] ([\w-]+) dir=([+-]?\d+) str=(\d+\.\d+)");
        private static readonly Regex VetoPattern = new(@"BLOCKED|veto");
        private static readonly Regex SessionPattern = new(@"\[DEEP6 Strategy\] New session");

        /// <summary>
        /// Compare simulator output against NT8 output.
        /// Filters to [DEEP6 ...] tagged lines and compares semantically.
        /// </summary>
        public static ParityReport Compare(IReadOnlyList<string> simOutput, string[] nt8Lines)
        {
            var report = new ParityReport
            {
                SimLineCount = simOutput.Count,
                Nt8LineCount = nt8Lines.Length,
            };

            // Filter to DEEP6-tagged lines only
            var simFiltered = simOutput.Where(l => l.Contains("[DEEP6")).ToList();
            var nt8Filtered = nt8Lines.Where(l => l.Contains("[DEEP6")).ToList();

            // Categorize each line
            var simCategorized = simFiltered.Select(Categorize).ToList();
            var nt8Categorized = nt8Filtered.Select(Categorize).ToList();

            // Compare by category groups
            int sm = 0, sd = 0, em = 0, ed = 0, sigm = 0, sigd = 0, vm = 0, vd = 0;
            CompareCategory(report, simCategorized, nt8Categorized, "scorer", ref sm, ref sd);
            CompareCategory(report, simCategorized, nt8Categorized, "entry", ref em, ref ed);
            CompareCategory(report, simCategorized, nt8Categorized, "signal", ref sigm, ref sigd);
            CompareCategory(report, simCategorized, nt8Categorized, "veto", ref vm, ref vd);
            report.ScoreMatches = sm; report.ScoreDiffs = sd;
            report.EntryMatches = em; report.EntryDiffs = ed;
            report.SignalMatches = sigm; report.SignalDiffs = sigd;
            report.VetoMatches = vm; report.VetoDiffs = vd;

            report.MatchedLines = sm + em + sigm + vm;
            report.Differences = report.Diffs.Count;

            return report;
        }

        /// <summary>Load NT8 output from a text file (copy-pasted from Output window).</summary>
        public static string[] LoadNt8Output(string path)
        {
            return File.ReadAllLines(path)
                .Where(l => !string.IsNullOrWhiteSpace(l))
                .ToArray();
        }

        private static (string category, string key, string line) Categorize(string line)
        {
            if (ScorePattern.IsMatch(line))
            {
                var m = ScorePattern.Match(line);
                return ("scorer", $"bar={m.Groups[1].Value}", line);
            }
            if (EntryPattern.IsMatch(line))
            {
                var m = EntryPattern.Match(line);
                return ("entry", $"{m.Groups[2].Value}@{m.Groups[3].Value}", line);
            }
            if (SignalPattern.IsMatch(line))
            {
                var m = SignalPattern.Match(line);
                return ("signal", $"{m.Groups[1].Value}_dir{m.Groups[2].Value}", line);
            }
            if (VetoPattern.IsMatch(line))
                return ("veto", line.GetHashCode().ToString(), line);
            if (SessionPattern.IsMatch(line))
                return ("session", "reset", line);
            return ("other", line.GetHashCode().ToString(), line);
        }

        private static void CompareCategory(ParityReport report,
            List<(string category, string key, string line)> sim,
            List<(string category, string key, string line)> nt8,
            string category, ref int matches, ref int diffs)
        {
            var simItems = sim.Where(s => s.category == category).ToList();
            var nt8Items = nt8.Where(s => s.category == category).ToList();

            var simKeys = simItems.Select(s => s.key).ToList();
            var nt8Keys = nt8Items.Select(s => s.key).ToList();

            // Find matches and differences
            int matchCount = 0;
            var nt8Matched = new HashSet<int>();

            for (int i = 0; i < simItems.Count; i++)
            {
                int nt8Idx = -1;
                for (int j = 0; j < nt8Items.Count; j++)
                {
                    if (!nt8Matched.Contains(j) && simItems[i].key == nt8Items[j].key)
                    {
                        nt8Idx = j;
                        break;
                    }
                }

                if (nt8Idx >= 0)
                {
                    matchCount++;
                    nt8Matched.Add(nt8Idx);
                }
                else
                {
                    report.Diffs.Add(new ParityDifference
                    {
                        LineNumber = i,
                        Category = "EXTRA_SIM",
                        SimLine = simItems[i].line,
                        Detail = $"Simulator produced {category} event not found in NT8 output",
                    });
                }
            }

            for (int j = 0; j < nt8Items.Count; j++)
            {
                if (!nt8Matched.Contains(j))
                {
                    report.Diffs.Add(new ParityDifference
                    {
                        LineNumber = j,
                        Category = "MISSING_SIM",
                        Nt8Line = nt8Items[j].line,
                        Detail = $"NT8 produced {category} event not found in simulator output",
                    });
                }
            }

            matches = matchCount;
            diffs = report.Diffs.Count;
        }

        /// <summary>Print a human-readable parity report.</summary>
        public static void PrintReport(ParityReport report)
        {
            Console.WriteLine($"  Match rate: {report.MatchRate:F1}% ({report.MatchedLines}/{System.Math.Max(report.SimLineCount, report.Nt8LineCount)})");
            Console.WriteLine($"  Scores:  {report.ScoreMatches} matched, {report.ScoreDiffs} diffs");
            Console.WriteLine($"  Entries: {report.EntryMatches} matched, {report.EntryDiffs} diffs");
            Console.WriteLine($"  Signals: {report.SignalMatches} matched, {report.SignalDiffs} diffs");
            Console.WriteLine($"  Vetoes:  {report.VetoMatches} matched, {report.VetoDiffs} diffs");

            if (report.Diffs.Count > 0)
            {
                Console.WriteLine();
                Console.WriteLine($"  Differences ({report.Diffs.Count}):");
                foreach (var d in report.Diffs.Take(20))
                {
                    Console.WriteLine($"    [{d.Category}] {d.Detail}");
                    if (d.SimLine != null) Console.WriteLine($"      SIM: {d.SimLine}");
                    if (d.Nt8Line != null) Console.WriteLine($"      NT8: {d.Nt8Line}");
                }
                if (report.Diffs.Count > 20)
                    Console.WriteLine($"    ... and {report.Diffs.Count - 20} more");
            }
        }
    }
}
