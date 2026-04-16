// BacktestE2ETests: End-to-end integration test: C# backtest -> CSV -> Python vbt harness.
// Phase quick-260415-u6v

using System;
using System.Diagnostics;
using System.IO;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Backtest;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;

namespace NinjaTrader.Tests.Backtest
{
    [TestFixture]
    [Category("E2E")]
    public class BacktestE2ETests
    {
        private string _tempDir;

        [SetUp]
        public void SetUp()
        {
            _tempDir = Path.Combine(Path.GetTempPath(), "bt_e2e_" + Path.GetRandomFileName());
            Directory.CreateDirectory(_tempDir);
        }

        [TearDown]
        public void TearDown()
        {
            if (Directory.Exists(_tempDir))
                Directory.Delete(_tempDir, true);
        }

        // ------------------------------------------------------------------
        // Helper: walk up from testDirectory to find the repo root (.git dir)
        // ------------------------------------------------------------------
        private static string FindRepoRoot()
        {
            string dir = TestContext.CurrentContext.TestDirectory;
            while (dir != null)
            {
                if (Directory.Exists(Path.Combine(dir, ".git")))
                    return dir;
                dir = Path.GetDirectoryName(dir);
            }
            throw new InvalidOperationException(
                "Could not find repo root (.git) starting from " +
                TestContext.CurrentContext.TestDirectory);
        }

        // ------------------------------------------------------------------
        // Helper: resolve fixture session paths
        // ------------------------------------------------------------------
        private static string[] GetSessionPaths()
        {
            string testDir  = TestContext.CurrentContext.TestDirectory;
            string fixtures = Path.Combine(testDir, "fixtures", "scoring", "sessions");
            var paths = new string[5];
            for (int i = 1; i <= 5; i++)
                paths[i - 1] = Path.Combine(fixtures, $"scoring-session-{i:D2}.ndjson");
            return paths;
        }

        // ------------------------------------------------------------------
        // Test 1: Full E2E — 5 sessions -> BacktestRunner -> CSV -> vbt_harness
        // ------------------------------------------------------------------
        [Test]
        public void E2E_FiveSessions_BacktestAndExportAndVbt()
        {
            string[] sessionPaths = GetSessionPaths();

            // Verify fixtures exist
            foreach (var p in sessionPaths)
                Assert.IsTrue(File.Exists(p), $"Session fixture not found: {p}");

            // Use lower thresholds so real fixtures produce trades
            var config = new BacktestConfig
            {
                ScoreEntryThreshold = 40.0,
                MinTierForEntry     = SignalTier.TYPE_C,
                StopLossTicks       = 20,
                TargetTicks         = 40,
                MaxBarsInTrade      = 30,
                SlippageTicks       = 1.0,
                TickSize            = 0.25,
                TickValue           = 5.0,
                InitialCapital      = 50000.0,
                ContractsPerTrade   = 1,
            };

            // --- Step 1: Run backtest ---
            var runner = new BacktestRunner();
            var result = runner.Run(config, sessionPaths);

            Assert.Greater(result.Trades.Count, 0, "Expected at least 1 trade from 5 sessions.");

            foreach (var t in result.Trades)
            {
                Assert.IsNotEmpty(t.ExitReason, "Trade ExitReason should not be empty.");
                Assert.Greater(t.DurationBars, 0, "Trade DurationBars should be > 0.");
            }

            Assert.GreaterOrEqual(result.WinRate, 0.0, "WinRate lower bound.");
            Assert.LessOrEqual(result.WinRate, 1.0, "WinRate upper bound.");

            // --- Step 2: Export CSV ---
            string csvPath = Path.Combine(_tempDir, "trades.csv");
            CsvTradeExporter.Export(result, csvPath);

            Assert.IsTrue(File.Exists(csvPath), "CSV file should exist after export.");
            string[] csvLines = File.ReadAllLines(csvPath);
            Assert.Greater(csvLines.Length, 1, "CSV should have header + at least one data row.");
            Assert.AreEqual(result.Trades.Count + 1, csvLines.Length,
                "CSV line count should equal trades.Count + 1 (header).");

            // --- Step 3: Invoke vbt_harness Python subprocess ---
            string repoRoot = FindRepoRoot();
            string python3  = FindPython3(repoRoot);

            if (python3 == null)
            {
                TestContext.Out.WriteLine("SKIP: python3 not found — skipping vbt_harness subprocess assertion.");
                Assert.Ignore("python3 not available in this environment.");
                return;
            }

            string outputDir = Path.Combine(_tempDir, "vbt_out");
            Directory.CreateDirectory(outputDir);

            var psi = new ProcessStartInfo(
                python3,
                $"-m deep6.backtest.vbt_harness --mode import --trades-csv \"{csvPath}\" --output-dir \"{outputDir}\"")
            {
                WorkingDirectory        = repoRoot,
                RedirectStandardOutput  = true,
                RedirectStandardError   = true,
                UseShellExecute         = false,
            };

            Process proc = null;
            try
            {
                proc = Process.Start(psi);
                bool exited = proc.WaitForExit(30_000); // 30-second timeout (T-u6v-03)
                string stdout = proc.StandardOutput.ReadToEnd();
                string stderr = proc.StandardError.ReadToEnd();

                if (!exited)
                {
                    proc.Kill();
                    TestContext.Out.WriteLine("TIMEOUT: vbt_harness did not complete within 30s.");
                    TestContext.Out.WriteLine("stderr: " + stderr);
                    Assert.Fail("vbt_harness subprocess timed out after 30 seconds.");
                }

                TestContext.Out.WriteLine("vbt_harness stdout:\n" + stdout);
                if (!string.IsNullOrEmpty(stderr))
                    TestContext.Out.WriteLine("vbt_harness stderr:\n" + stderr);

                Assert.AreEqual(0, proc.ExitCode,
                    "vbt_harness import mode failed.\nstderr: " + stderr);

                string reportPath = Path.Combine(outputDir, "report.html");
                Assert.IsTrue(File.Exists(reportPath),
                    "HTML report should be generated at " + reportPath);
            }
            catch (Exception ex) when (ex is System.ComponentModel.Win32Exception
                                     || ex is FileNotFoundException)
            {
                // python3 binary found but failed to launch (rare)
                TestContext.Out.WriteLine("SKIP: subprocess launch failed: " + ex.Message);
                Assert.Ignore("python3 subprocess could not be launched: " + ex.Message);
            }
            finally
            {
                proc?.Dispose();
            }
        }

        // ------------------------------------------------------------------
        // Test 2: Summary smoke test — no exceptions on summary property access
        // ------------------------------------------------------------------
        [Test]
        public void E2E_BacktestResult_PrintsSummary()
        {
            string[] sessionPaths = GetSessionPaths();
            foreach (var p in sessionPaths)
                Assert.IsTrue(File.Exists(p), $"Session fixture not found: {p}");

            // Run only session-01 with permissive thresholds
            var config = new BacktestConfig
            {
                ScoreEntryThreshold = 40.0,
                MinTierForEntry     = SignalTier.TYPE_C,
                StopLossTicks       = 20,
                TargetTicks         = 40,
                MaxBarsInTrade      = 30,
                SlippageTicks       = 1.0,
            };

            var result = new BacktestRunner().Run(config, new[] { sessionPaths[0] });

            // Smoke test: access all summary properties without throwing
            TestContext.Out.WriteLine($"TotalTrades:          {result.TotalTrades}");
            TestContext.Out.WriteLine($"WinRate:              {result.WinRate:P1}");
            TestContext.Out.WriteLine($"ProfitFactor:         {result.ProfitFactor:F2}");
            TestContext.Out.WriteLine($"SharpeEstimate:       {result.SharpeEstimate:F3}");
            TestContext.Out.WriteLine($"MaxDrawdownTicks:     {result.MaxDrawdownTicks:F1}");
            TestContext.Out.WriteLine($"MaxConsecutiveLosses: {result.MaxConsecutiveLosses}");
            TestContext.Out.WriteLine($"NetPnlDollars:        {result.NetPnlDollars:C}");
            TestContext.Out.WriteLine($"AvgWinTicks:          {result.AvgWinTicks:F1}");
            TestContext.Out.WriteLine($"AvgLossTicks:         {result.AvgLossTicks:F1}");

            // No assertion beyond "did not throw"
            Assert.Pass("Summary properties computed without exception.");
        }

        // ------------------------------------------------------------------
        // Helper: find python3 executable
        // ------------------------------------------------------------------
        private static string FindPython3(string repoRoot)
        {
            // Prefer .venv in repo root
            string[] candidates =
            {
                Path.Combine(repoRoot, ".venv", "bin", "python3"),
                "/usr/local/bin/python3",
                "/opt/homebrew/bin/python3",
                "python3",
            };

            foreach (var candidate in candidates)
            {
                // For absolute paths, check file exists
                if (Path.IsPathRooted(candidate))
                {
                    if (File.Exists(candidate)) return candidate;
                }
                else
                {
                    // "python3" — rely on PATH; assume it exists
                    return candidate;
                }
            }

            return null;
        }
    }
}
