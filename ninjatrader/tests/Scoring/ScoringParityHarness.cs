// ScoringParityHarness: C# ConfluenceScorer <-> Python replay_scorer parity gate.
//
// Phase 18-04 — Wave 4 parity harness.
//
// For each of 5 scoring-session NDJSON fixtures:
//   1. Load ScoredBarRecord[] via CaptureReplayLoader.LoadScoredBars()
//   2. Score each bar through ConfluenceScorer.Score() (C# in-process)
//   3. Pipe same NDJSON file to `python3 -m deep6.scoring.replay_scorer` (subprocess)
//   4. Parse JSON-line output per bar
//   5. Assert per-bar: |csharp_score - python_score| <= 0.05 AND tier names match
//
// Tolerance: Δscore ≤ 0.05, tier verdict identical.
// Subprocess timeout: 30 seconds per session.
//
// Python3 unavailable: Assert.Ignore() — test skipped, not failed.
// PYTHON3_PATH env var overrides the python3 binary path (for CI environments).

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;
using NinjaTrader.Tests.SessionReplay;

namespace NinjaTrader.Tests.Scoring
{
    [TestFixture]
    [Category("Scoring")]
    public class ScoringParityHarness
    {
        // -----------------------------------------------------------------------
        // Score delta tolerance (SCOR-PAR-01)
        // -----------------------------------------------------------------------
        private const double SCORE_TOLERANCE = 0.05;

        // -----------------------------------------------------------------------
        // Subprocess timeout per session
        // -----------------------------------------------------------------------
        private const int SUBPROCESS_TIMEOUT_MS = 30_000;

        // -----------------------------------------------------------------------
        // Fixture path helpers
        // -----------------------------------------------------------------------
        private static string ScoringFixturesDir() =>
            Path.Combine(TestContext.CurrentContext.TestDirectory,
                "fixtures", "scoring", "sessions");

        private static string ScoringSessionFile(string sessionName) =>
            Path.Combine(ScoringFixturesDir(), sessionName + ".ndjson");

        // -----------------------------------------------------------------------
        // Repo root resolution (walk up from assembly dir until deep6/ is found)
        // -----------------------------------------------------------------------
        private static string ResolveRepoRoot()
        {
            string dir = TestContext.CurrentContext.TestDirectory;
            for (int i = 0; i < 10; i++)
            {
                if (Directory.Exists(Path.Combine(dir, "deep6")))
                    return dir;
                string parent = Directory.GetParent(dir)?.FullName;
                if (parent == null) break;
                dir = parent;
            }
            throw new DirectoryNotFoundException(
                "Cannot locate repo root (no deep6/ directory found walking up from " +
                TestContext.CurrentContext.TestDirectory + ")");
        }

        // -----------------------------------------------------------------------
        // Python subprocess helper
        // -----------------------------------------------------------------------
        private static List<(int barIdx, double score, string tier, string narrative)>
            RunPython(string ndjsonPath, int timeoutMs = SUBPROCESS_TIMEOUT_MS)
        {
            string python = Environment.GetEnvironmentVariable("PYTHON3_PATH");
            string repoRoot = ResolveRepoRoot();
            if (string.IsNullOrEmpty(python))
            {
                // Prefer the project venv python (has deep6 package installed)
                string venvPy = Path.Combine(repoRoot, ".venv", "bin", "python3");
                python = File.Exists(venvPy) ? venvPy : "python3";
            }

            var psi = new ProcessStartInfo
            {
                FileName             = python,
                Arguments            = "-m deep6.scoring.replay_scorer",
                WorkingDirectory     = repoRoot,
                RedirectStandardInput  = true,
                RedirectStandardOutput = true,
                RedirectStandardError  = true,
                UseShellExecute        = false,
            };

            Process proc;
            try
            {
                proc = Process.Start(psi);
                if (proc == null)
                    throw new InvalidOperationException("Process.Start returned null");
            }
            catch (System.ComponentModel.Win32Exception ex)
            {
                // python3 not found on PATH — signal ignore to caller
                throw new FileNotFoundException(
                    "python3 not found: " + ex.Message, python);
            }

            // Pipe the NDJSON file to stdin
            using (var sr = new StreamReader(ndjsonPath))
            {
                string line;
                while ((line = sr.ReadLine()) != null)
                    proc.StandardInput.WriteLine(line);
            }
            proc.StandardInput.Close();

            // Collect stdout async to avoid deadlock (stderr may also be large)
            string stdout = proc.StandardOutput.ReadToEnd();
            string stderr = proc.StandardError.ReadToEnd();

            if (!proc.WaitForExit(timeoutMs))
            {
                proc.Kill();
                throw new TimeoutException(
                    string.Format("Python parity subprocess timed out after {0}ms for {1}.\nstderr: {2}",
                        timeoutMs, Path.GetFileName(ndjsonPath), stderr));
            }

            if (proc.ExitCode != 0)
                throw new InvalidOperationException(
                    string.Format("Python replay_scorer exited with code {0} for {1}.\nstderr: {2}",
                        proc.ExitCode, Path.GetFileName(ndjsonPath), stderr));

            // Parse JSON lines from stdout
            var results = new List<(int, double, string, string)>();
            foreach (string rawLine in stdout.Split('\n'))
            {
                string l = rawLine.Trim();
                if (string.IsNullOrEmpty(l)) continue;
                int    barIdx    = ExtractJsonInt(l, "bar_index");
                double score     = ExtractJsonDouble(l, "score");
                string tier      = ExtractJsonString(l, "tier");
                string narrative = ExtractJsonString(l, "narrative") ?? string.Empty;
                if (tier != null)
                    results.Add((barIdx, score, tier, narrative));
            }
            return results;
        }

        // -----------------------------------------------------------------------
        // Per-session parameterized parity tests
        // -----------------------------------------------------------------------
        [TestCase("scoring-session-01")]
        [TestCase("scoring-session-02")]
        [TestCase("scoring-session-03")]
        [TestCase("scoring-session-04")]
        [TestCase("scoring-session-05")]
        public void Parity_ScoringSession_WithinEnvelope(string sessionName)
        {
            string path = ScoringSessionFile(sessionName);
            Assert.IsTrue(File.Exists(path),
                "Scoring session fixture not found: " + path);

            // Load and C#-score all bars
            var scoredBars = new List<ScoredBarRecord>(CaptureReplayLoader.LoadScoredBars(path));
            Assert.IsTrue(scoredBars.Count > 0,
                string.Format("{0}: no scored_bar records found in fixture", sessionName));

            // Run Python subprocess
            List<(int barIdx, double score, string tier, string narrative)> pythonResults;
            try
            {
                pythonResults = RunPython(path);
            }
            catch (FileNotFoundException ex)
            {
                Assert.Ignore("python3 not on PATH; set PYTHON3_PATH env var. Details: " + ex.Message);
                return;
            }

            // Build bar-index lookup for Python results
            var pyMap = new Dictionary<int, (double score, string tier, string narrative)>();
            foreach (var r in pythonResults)
                pyMap[r.barIdx] = (r.score, r.tier, r.narrative);

            Assert.IsTrue(pyMap.Count > 0,
                string.Format("{0}: Python replay_scorer produced no output", sessionName));

            // Per-bar diff
            var divergences = new List<string>();
            int matchedBars  = 0;
            double maxDelta  = 0.0;
            int tierMismatches = 0;

            foreach (var sbr in scoredBars)
            {
                var csResult = ConfluenceScorer.Score(
                    sbr.Signals,
                    sbr.BarsSinceOpen,
                    sbr.BarDelta,
                    sbr.BarClose,
                    zoneScore:     sbr.ZoneScore,
                    zoneDistTicks: sbr.ZoneDistTicks);

                if (!pyMap.TryGetValue(sbr.BarIdx, out var py))
                {
                    divergences.Add(string.Format(
                        "bar {0}: no Python result (barIdx not in py output)", sbr.BarIdx));
                    continue;
                }

                double delta = System.Math.Abs(csResult.TotalScore - py.score);
                if (delta > maxDelta) maxDelta = delta;
                matchedBars++;

                if (delta > SCORE_TOLERANCE)
                {
                    divergences.Add(string.Format(
                        "bar {0}: SCORE DELTA {1:F4} > {2:F2}  (C#={3:F4}  Py={4:F4})",
                        sbr.BarIdx, delta, SCORE_TOLERANCE, csResult.TotalScore, py.score));
                }

                string csTierStr = csResult.Tier.ToString();
                if (!string.Equals(csTierStr, py.tier, StringComparison.Ordinal))
                {
                    tierMismatches++;
                    divergences.Add(string.Format(
                        "bar {0}: TIER MISMATCH  C#={1}  Py={2}  (score: C#={3:F4} Py={4:F4})",
                        sbr.BarIdx, csTierStr, py.tier, csResult.TotalScore, py.score));
                }
            }

            // Emit per-session summary to test output
            TestContext.Progress.WriteLine(string.Format(
                "[PARITY] {0}: {1} bars matched | maxΔ={2:F4} | tierMismatches={3} | divergences={4}",
                sessionName, matchedBars, maxDelta, tierMismatches, divergences.Count));

            Assert.IsEmpty(divergences,
                string.Format(
                    "{0}: {1} divergences found:\n  {2}",
                    sessionName,
                    divergences.Count,
                    string.Join("\n  ", divergences)));
        }

        // -----------------------------------------------------------------------
        // Minimal JSON field extractors (no Newtonsoft / System.Text.Json dep)
        // -----------------------------------------------------------------------
        private static string ExtractJsonString(string json, string key)
        {
            string search = "\"" + key + "\":\"";
            int start = json.IndexOf(search, StringComparison.Ordinal);
            if (start < 0) return null;
            start += search.Length;
            int end = json.IndexOf('"', start);
            if (end < 0) return null;
            return json.Substring(start, end - start);
        }

        private static int ExtractJsonInt(string json, string key)
        {
            string v = ExtractJsonValue(json, key);
            int r; return int.TryParse(v, out r) ? r : 0;
        }

        private static double ExtractJsonDouble(string json, string key)
        {
            string v = ExtractJsonValue(json, key);
            double r;
            return double.TryParse(v,
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out r) ? r : 0.0;
        }

        private static string ExtractJsonValue(string json, string key)
        {
            string search = "\"" + key + "\":";
            int start = json.IndexOf(search, StringComparison.Ordinal);
            if (start < 0) return null;
            start += search.Length;
            while (start < json.Length && json[start] == ' ') start++;
            if (start >= json.Length) return null;
            int end = start;
            while (end < json.Length && json[end] != ',' && json[end] != '}' && json[end] != ']') end++;
            return json.Substring(start, end - start).Trim();
        }
    }
}
