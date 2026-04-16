// NinjaScriptSim CLI — validate, backtest, and forward-test NinjaScript code without NinjaTrader.
//
// Usage:
//   dotnet run --project ninjatrader/simulator -- validate                  # compile-check all DEEP6 scripts
//   dotnet run --project ninjatrader/simulator -- run                       # lifecycle replay with sample bars
//   dotnet run --project ninjatrader/simulator -- replay session.ndjson     # replay captured NDJSON session
//   dotnet run --project ninjatrader/simulator -- replay *.ndjson           # replay multiple sessions
//   dotnet run --project ninjatrader/simulator -- databento ohlcv.csv      # replay Databento OHLCV CSV
//   dotnet run --project ninjatrader/simulator -- databento-mbo trades.csv # convert + replay Databento MBO
//   dotnet run --project ninjatrader/simulator -- bridge [host:port]       # connect to NT8 data bridge
//   dotnet run --project ninjatrader/simulator -- bridge --record out.ndjson  # bridge + save to file

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using NinjaScriptSim.Lifecycle;

namespace NinjaScriptSim.Cli
{
    class Program
    {
        static int Main(string[] args)
        {
            if (args.Length == 0)
            {
                PrintUsage();
                return 1;
            }

            string command = args[0].ToLower();
            string[] rest = args.Length > 1 ? args[1..] : Array.Empty<string>();

            return command switch
            {
                "validate" => RunValidate(rest.FirstOrDefault() ?? "all"),
                "run" => RunLifecycle(rest.FirstOrDefault() ?? "all"),
                "lifecycle" => RunLifecycle("all"),
                "replay" => RunReplay(rest),
                "databento" => RunDatabento(rest, mbo: false),
                "databento-mbo" => RunDatabento(rest, mbo: true),
                "bridge" => RunBridge(rest),
                "optimize" => RunOptimize(rest),
                "parity" => RunParity(rest),
                "signals" => RunSignals(rest),
                "walkforward" => RunWalkForward(rest),
                "montecarlo" => RunMonteCarlo(rest),
                "classify" => RunClassify(rest),
                "backtest" => RunBacktest(rest),
                "chart" => RunChart(rest),
                "footprint" => RunFootprint(rest),
                "design" => RunDesign(rest),
                "serve" => RunServe(rest),
                "help" or "--help" or "-h" => PrintUsageOk(),
                _ => PrintUnknownCommand(command),
            };
        }

        // ══════════════════════════════════════════════════════════════════
        //  REPLAY — load captured NDJSON sessions, run through strategy
        // ══════════════════════════════════════════════════════════════════

        static int RunReplay(string[] args)
        {
            if (args.Length == 0)
            {
                Console.WriteLine("Usage: replay <session.ndjson> [session2.ndjson ...]");
                Console.WriteLine("       replay --dir <directory>  (all .ndjson files)");
                return 1;
            }

            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Session Replay");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            // Collect files
            var files = new List<string>();
            if (args[0] == "--dir" && args.Length > 1)
            {
                files.AddRange(Directory.GetFiles(args[1], "*.ndjson").OrderBy(f => f));
            }
            else
            {
                foreach (var arg in args)
                {
                    if (File.Exists(arg)) files.Add(arg);
                    else Console.WriteLine($"  WARN: file not found: {arg}");
                }
            }

            if (files.Count == 0) { Console.WriteLine("No NDJSON files found."); return 1; }

            Console.WriteLine($"  Loading {files.Count} session file(s)...");
            var sw = Stopwatch.StartNew();
            var session = NdjsonSessionLoader.LoadMultiple(files.ToArray());
            sw.Stop();

            Console.WriteLine($"  Loaded: {session.Bars.Count} bars, {session.DepthUpdates.Count} depth events, " +
                $"{session.TradeCount} trades ({sw.ElapsedMilliseconds}ms)");
            Console.WriteLine();

            return RunSessionData(session, "NDJSON Replay");
        }

        // ══════════════════════════════════════════════════════════════════
        //  DATABENTO — load Databento CSV files, run through strategy
        // ══════════════════════════════════════════════════════════════════

        static int RunDatabento(string[] args, bool mbo)
        {
            if (args.Length == 0)
            {
                Console.WriteLine(mbo
                    ? "Usage: databento-mbo <trades.csv>  (Databento MBO trades CSV)"
                    : "Usage: databento <ohlcv.csv>       (Databento OHLCV-1m CSV)");
                return 1;
            }

            string csvPath = args[0];
            if (!File.Exists(csvPath)) { Console.WriteLine($"File not found: {csvPath}"); return 1; }

            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine($" NinjaScript Simulator — Databento {(mbo ? "MBO" : "OHLCV")} Replay");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            var sw = Stopwatch.StartNew();

            SessionData session;
            if (mbo)
            {
                // Convert MBO to NDJSON first, then load
                string tmpNdjson = Path.GetTempFileName();
                try
                {
                    Console.Write("  Converting MBO CSV → NDJSON... ");
                    DatabentoAdapter.ConvertMboToNdjson(csvPath, tmpNdjson);
                    Console.WriteLine("OK");
                    session = NdjsonSessionLoader.Load(tmpNdjson);
                }
                finally
                {
                    try { File.Delete(tmpNdjson); } catch { }
                }
            }
            else
            {
                Console.Write("  Loading OHLCV CSV... ");
                session = DatabentoAdapter.LoadOhlcvCsv(csvPath);
                Console.WriteLine("OK");
            }

            sw.Stop();
            Console.WriteLine($"  Loaded: {session.Bars.Count} bars, {session.DepthUpdates.Count} depth events ({sw.ElapsedMilliseconds}ms)");
            Console.WriteLine();

            return RunSessionData(session, $"Databento {(mbo ? "MBO" : "OHLCV")}");
        }

        // ══════════════════════════════════════════════════════════════════
        //  BRIDGE — connect to NT8 DataBridgeServer for live data
        // ══════════════════════════════════════════════════════════════════

        static int RunBridge(string[] args)
        {
            string host = "127.0.0.1";
            int port = 9200;
            string recordPath = null;

            // Parse args
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--record" && i + 1 < args.Length)
                {
                    recordPath = args[++i];
                }
                else if (args[i].Contains(':'))
                {
                    var parts = args[i].Split(':');
                    host = parts[0];
                    int.TryParse(parts[1], out port);
                }
                else if (int.TryParse(args[i], out int p))
                {
                    port = p;
                }
            }

            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — NT8 Data Bridge");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();
            Console.WriteLine($"  Connecting to {host}:{port}...");

            using var client = new BridgeClient(host, port);
            try
            {
                client.Connect();
                Console.WriteLine("  Connected! Receiving live data from NT8.");
                if (recordPath != null)
                    Console.WriteLine($"  Recording to: {recordPath}");
                Console.WriteLine("  Press Ctrl+C to stop.");
                Console.WriteLine();

                var cts = new CancellationTokenSource();
                Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

                // Status updates
                var statusTimer = new System.Threading.Timer(_ =>
                {
                    Console.Write($"\r  Trades: {client.TradesReceived}  Depth: {client.DepthEventsReceived}  Bars: {client.BarsReceived}    ");
                }, null, 1000, 2000);

                try
                {
                    if (recordPath != null)
                        client.RecordTo(recordPath, cts.Token);
                    else
                        client.StreamLive(cts.Token);
                }
                catch (OperationCanceledException) { }

                statusTimer.Dispose();
                Console.WriteLine();
                Console.WriteLine();
                Console.WriteLine($"  Session summary: {client.TradesReceived} trades, {client.DepthEventsReceived} depth, {client.BarsReceived} bars");

                if (recordPath != null && File.Exists(recordPath))
                {
                    var fi = new FileInfo(recordPath);
                    Console.WriteLine($"  Recorded to: {recordPath} ({fi.Length / 1024}KB)");
                    Console.WriteLine($"  Replay with: dotnet run --project ninjatrader/simulator -- replay {recordPath}");
                }

                return 0;
            }
            catch (System.Net.Sockets.SocketException ex)
            {
                Console.WriteLine($"  Connection failed: {ex.Message}");
                Console.WriteLine();
                Console.WriteLine("  Make sure the DataBridgeIndicator is running in NT8:");
                Console.WriteLine("    1. Copy DataBridgeIndicator.cs to NT8 Custom\\Indicators\\DEEP6\\");
                Console.WriteLine("    2. F5 compile in NinjaScript Editor");
                Console.WriteLine("    3. Add 'DEEP6 DataBridge' indicator to any NQ chart");
                Console.WriteLine($"    4. Verify port {port} matches (default 9200)");
                return 1;
            }
        }

        // ══════════════════════════════════════════════════════════════════
        //  Common: Run SessionData through strategy
        // ══════════════════════════════════════════════════════════════════

        static int RunSessionData(SessionData session, string label)
        {
            var runner = new NinjaScriptRunner();
            runner.LoadBars(session.Bars);
            runner.LoadDepthUpdates(session.DepthUpdates);

            // Run strategy
            Console.Write($"  Running DEEP6Strategy through {session.Bars.Count} bars... ");
            var sw = Stopwatch.StartNew();
            try
            {
                var script = runner.Run<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>();
                sw.Stop();

                if (runner.Errors.Count > 0)
                {
                    Console.WriteLine($"FAIL ({sw.ElapsedMilliseconds}ms)");
                    foreach (var err in runner.Errors)
                        Console.WriteLine($"    ERROR: {err}");
                    return 1;
                }

                Console.WriteLine($"OK ({sw.ElapsedMilliseconds}ms)");
                Console.WriteLine();

                // Print strategy output summary
                var entries = script.PrintLog.Where(l => l.Contains("entry") || l.Contains("ENTRY") || l.Contains("EnterLong") || l.Contains("EnterShort")).ToList();
                var exits = script.PrintLog.Where(l => l.Contains("EXIT") || l.Contains("ExitLong") || l.Contains("ExitShort") || l.Contains("Position flat")).ToList();
                var vetoes = script.PrintLog.Where(l => l.Contains("BLOCKED") || l.Contains("veto")).ToList();
                var scores = script.PrintLog.Where(l => l.Contains("[DEEP6 Scorer]")).ToList();

                Console.WriteLine($"  ── {label} Results ──");
                Console.WriteLine($"  Bars processed:    {session.Bars.Count}");
                Console.WriteLine($"  Scored bars:       {scores.Count}");
                Console.WriteLine($"  Entry signals:     {entries.Count}");
                Console.WriteLine($"  Exit signals:      {exits.Count}");
                Console.WriteLine($"  Vetoed entries:    {vetoes.Count}");
                Console.WriteLine($"  Total print lines: {script.PrintLog.Count}");
                Console.WriteLine();

                // Show last few entries
                if (entries.Count > 0)
                {
                    Console.WriteLine("  Last entries:");
                    foreach (var e in entries.TakeLast(5))
                        Console.WriteLine($"    {e}");
                    Console.WriteLine();
                }

                // Show veto breakdown
                if (vetoes.Count > 0)
                {
                    var vetoTypes = vetoes
                        .Select(v => {
                            if (v.Contains("daily loss")) return "daily_loss_cap";
                            if (v.Contains("max trades")) return "max_trades";
                            if (v.Contains("cooldown")) return "cooldown";
                            if (v.Contains("RTH")) return "outside_rth";
                            if (v.Contains("news")) return "news_blackout";
                            if (v.Contains("account")) return "account_mismatch";
                            if (v.Contains("VOLP-03")) return "vol_surge_veto";
                            if (v.Contains("slow-grind")) return "slow_grind_veto";
                            if (v.Contains("blackout")) return "time_blackout";
                            return "other";
                        })
                        .GroupBy(v => v)
                        .OrderByDescending(g => g.Count());

                    Console.WriteLine("  Veto breakdown:");
                    foreach (var g in vetoTypes)
                        Console.WriteLine($"    {g.Key}: {g.Count()}");
                }

                // Show fill engine results (real P&L)
                if (runner.FillResult != null && runner.FillResult.Trades.Count > 0)
                {
                    Console.WriteLine();
                    FillSimulator.PrintReport(runner.FillResult);
                }

                return 0;
            }
            catch (Exception ex)
            {
                sw.Stop();
                Console.WriteLine($"CRASH ({sw.ElapsedMilliseconds}ms)");
                Console.WriteLine($"    {ex.GetType().Name}: {ex.Message}");
                return 1;
            }
        }

        // ══════════════════════════════════════════════════════════════════
        //  BACKTEST — full backtest with trade journal + equity chart
        // ══════════════════════════════════════════════════════════════════

        static int RunBacktest(string[] args)
        {
            string tradesCsv = null, equityHtml = null;
            var files = new List<string>();

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--trades" && i + 1 < args.Length) tradesCsv = args[++i];
                else if (args[i] == "--equity" && i + 1 < args.Length) equityHtml = args[++i];
                else if (args[i] == "--dir" && i + 1 < args.Length)
                    files.AddRange(Directory.GetFiles(args[++i], "*.ndjson").OrderBy(f => f));
                else if (File.Exists(args[i])) files.Add(args[i]);
            }

            if (files.Count == 0) { Console.WriteLine("Usage: backtest <session.ndjson> [--trades trades.csv] [--equity equity.html]"); return 1; }

            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Full Backtest");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            var session = NdjsonSessionLoader.LoadMultiple(files.ToArray());
            var runner = new NinjaScriptRunner();
            runner.LoadBars(session.Bars);
            runner.LoadDepthUpdates(session.DepthUpdates);

            var sw = Stopwatch.StartNew();
            runner.Run<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>();
            sw.Stop();

            Console.WriteLine($"  Completed in {sw.ElapsedMilliseconds}ms ({session.Bars.Count} bars)");
            Console.WriteLine();

            if (runner.FillResult != null)
            {
                FillSimulator.PrintReport(runner.FillResult);

                if (tradesCsv != null)
                {
                    FillSimulator.ExportCsv(runner.FillResult, tradesCsv);
                    Console.WriteLine($"\n  Trade journal: {tradesCsv}");
                }
                if (equityHtml != null)
                {
                    FillSimulator.ExportEquityChart(runner.FillResult, equityHtml);
                    Console.WriteLine($"  Equity curve:  {equityHtml}");
                }
            }
            else
            {
                Console.WriteLine("  No fill results (strategy may not have run).");
            }

            return 0;
        }

        // ══════════════════════════════════════════════════════════════════
        //  VALIDATE + RUN (unchanged from previous version)
        // ══════════════════════════════════════════════════════════════════

        static int RunValidate(string target)
        {
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Compile Validation");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();
            Console.WriteLine("[PASS] All NinjaScript source files compiled successfully against stubs.");
            Console.WriteLine();

            int failures = 0;
            var runner = new NinjaScriptRunner();

            if (target == "all" || target == "indicator")
                failures += ValidateScript<NinjaTrader.NinjaScript.Indicators.DEEP6.DEEP6Footprint>(runner, "DEEP6Footprint (Indicator)");
            if (target == "all" || target == "strategy")
                failures += ValidateScript<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>(runner, "DEEP6Strategy (Strategy)");

            Console.WriteLine();
            Console.WriteLine(failures == 0 ? "[PASS] All validation checks passed." : $"[FAIL] {failures} validation check(s) failed.");
            return failures == 0 ? 0 : 1;
        }

        static int ValidateScript<T>(NinjaScriptRunner runner, string label) where T : NinjaTrader.NinjaScript.NinjaScriptBase, new()
        {
            Console.Write($"  Validating {label}... ");
            var sw = Stopwatch.StartNew();
            try
            {
                var script = runner.ValidateOnly<T>();
                sw.Stop();
                if (runner.Errors.Count > 0)
                {
                    Console.WriteLine($"FAIL ({sw.ElapsedMilliseconds}ms)");
                    foreach (var err in runner.Errors) Console.WriteLine($"    ERROR: {err}");
                    return 1;
                }
                Console.WriteLine($"OK ({sw.ElapsedMilliseconds}ms)");
                if (script.PrintLog.Count > 0)
                {
                    Console.WriteLine($"    Print output: {script.PrintLog.Count} line(s)");
                    foreach (var line in script.PrintLog.Take(5)) Console.WriteLine($"      > {line}");
                    if (script.PrintLog.Count > 5) Console.WriteLine($"      ... and {script.PrintLog.Count - 5} more");
                }
                return 0;
            }
            catch (Exception ex)
            {
                sw.Stop();
                Console.WriteLine($"CRASH ({sw.ElapsedMilliseconds}ms)");
                Console.WriteLine($"    {ex.GetType().Name}: {ex.Message}");
                return 1;
            }
        }

        static int RunLifecycle(string target)
        {
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Lifecycle Replay");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            var bars = GenerateSampleBars();
            Console.WriteLine($"  Generated {bars.Count} sample NQ bars (1-min, simulated RTH session)");
            Console.WriteLine();

            int failures = 0;
            var runner = new NinjaScriptRunner();
            runner.LoadBars(bars);

            if (target == "all" || target == "indicator")
            {
                Console.Write("  Running DEEP6Footprint lifecycle... ");
                var sw = Stopwatch.StartNew();
                try
                {
                    var script = runner.Run<NinjaTrader.NinjaScript.Indicators.DEEP6.DEEP6Footprint>();
                    sw.Stop();
                    Console.WriteLine(runner.Errors.Count > 0 ? $"FAIL ({sw.ElapsedMilliseconds}ms)" : $"OK ({sw.ElapsedMilliseconds}ms, {script.PrintLog.Count} print lines)");
                    if (runner.Errors.Count > 0) { foreach (var err in runner.Errors) Console.WriteLine($"    ERROR: {err}"); failures++; }
                }
                catch (Exception ex) { sw.Stop(); Console.WriteLine($"CRASH: {ex.Message}"); failures++; }
            }

            if (target == "all" || target == "strategy")
            {
                Console.Write("  Running DEEP6Strategy lifecycle... ");
                var sw = Stopwatch.StartNew();
                try
                {
                    var script = runner.Run<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>();
                    sw.Stop();
                    Console.WriteLine(runner.Errors.Count > 0 ? $"FAIL ({sw.ElapsedMilliseconds}ms)" : $"OK ({sw.ElapsedMilliseconds}ms, {script.PrintLog.Count} print lines)");
                    if (runner.Errors.Count > 0) { foreach (var err in runner.Errors) Console.WriteLine($"    ERROR: {err}"); failures++; }
                }
                catch (Exception ex) { sw.Stop(); Console.WriteLine($"CRASH: {ex.Message}"); failures++; }
            }

            Console.WriteLine();
            Console.WriteLine(failures == 0 ? "[PASS] All lifecycle checks passed." : $"[FAIL] {failures} lifecycle check(s) failed.");
            return failures == 0 ? 0 : 1;
        }

        static List<BarData> GenerateSampleBars()
        {
            var bars = new List<BarData>();
            var rng = new Random(42);
            double price = 19000.0;
            double tickSize = 0.25;
            var baseTime = new DateTime(2026, 4, 16, 9, 30, 0);

            for (int i = 0; i < 60; i++)
            {
                double change = (rng.NextDouble() - 0.48) * 20.0;
                double open = Math.Round(price / tickSize) * tickSize;
                double close = Math.Round((price + change) / tickSize) * tickSize;
                double high = Math.Max(open, close) + rng.Next(1, 8) * tickSize;
                double low = Math.Min(open, close) - rng.Next(1, 8) * tickSize;
                long volume = rng.Next(500, 3000);
                var barTime = baseTime.AddMinutes(i + 1);

                var ticks = new List<TickData>();
                int tickCount = rng.Next(20, 80);
                double tickPrice = open;
                long tickVolRemaining = volume;
                for (int t = 0; t < tickCount && tickVolRemaining > 0; t++)
                {
                    double tickChange = (rng.NextDouble() - 0.5) * 4.0 * tickSize;
                    tickPrice = Math.Round(Math.Max(low, Math.Min(high, tickPrice + tickChange)) / tickSize) * tickSize;
                    long tickSize2 = Math.Min(rng.Next(1, 30), tickVolRemaining);
                    int aggressor = tickPrice >= (high - (high - low) * 0.3) ? 1 : tickPrice <= (low + (high - low) * 0.3) ? 2 : rng.Next(0, 3);
                    ticks.Add(new TickData { Price = tickPrice, Size = tickSize2, Aggressor = aggressor, Time = barTime.AddSeconds(-60 + (60.0 * t / tickCount)) });
                    tickVolRemaining -= tickSize2;
                }
                if (ticks.Count > 0) ticks[ticks.Count - 1].Price = close;

                bars.Add(new BarData { Open = open, High = high, Low = low, Close = close, Volume = volume, Time = barTime, Ticks = ticks });
                price = close;
            }
            return bars;
        }

        // ══════════════════════════════════════════════════════════════════
        //  OPTIMIZE — parallel parameter sweep
        // ══════════════════════════════════════════════════════════════════

        static int RunOptimize(string[] args)
        {
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Strategy Optimizer");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            // Parse: optimize --data <files> --sweep Param=from:step:to [--output file.csv]
            var dataFiles = new List<string>();
            var optimizer = new StrategyOptimizer();
            string outputCsv = "optimization-results.csv";

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--data" && i + 1 < args.Length) { dataFiles.Add(args[++i]); }
                else if (args[i] == "--dir" && i + 1 < args.Length)
                {
                    dataFiles.AddRange(Directory.GetFiles(args[++i], "*.ndjson").OrderBy(f => f));
                }
                else if (args[i] == "--sweep" && i + 1 < args.Length)
                {
                    var parts = args[++i].Split('=');
                    if (parts.Length == 2)
                    {
                        var range = parts[1].Split(':');
                        if (range.Length == 3 &&
                            double.TryParse(range[0], NumberStyles.Float, CultureInfo.InvariantCulture, out double from) &&
                            double.TryParse(range[1], NumberStyles.Float, CultureInfo.InvariantCulture, out double step) &&
                            double.TryParse(range[2], NumberStyles.Float, CultureInfo.InvariantCulture, out double to))
                        {
                            optimizer.AddSweep(parts[0], from, to, step);
                        }
                    }
                }
                else if (args[i] == "--output" && i + 1 < args.Length) { outputCsv = args[++i]; }
                else if (File.Exists(args[i])) { dataFiles.Add(args[i]); }
            }

            if (dataFiles.Count == 0)
            {
                Console.WriteLine("Usage: optimize --data <session.ndjson> --sweep ScoreEntryThreshold=50:5:90 [--output results.csv]");
                return 1;
            }

            var session = NdjsonSessionLoader.LoadMultiple(dataFiles.ToArray());
            Console.WriteLine($"  Data: {session.Bars.Count} bars from {dataFiles.Count} file(s)");
            Console.WriteLine($"  Combinations: {optimizer.TotalCombinations}");
            Console.WriteLine($"  Parallelism: {optimizer.MaxParallelism} cores");
            Console.WriteLine();

            var sw = Stopwatch.StartNew();
            var results = optimizer.Run(session);
            sw.Stop();

            Console.WriteLine($"  Completed {results.Count} runs in {sw.ElapsedMilliseconds}ms");
            Console.WriteLine();

            // Show top 10
            Console.WriteLine("  ── Top 10 by Sharpe ──");
            Console.WriteLine("  {0,5} {1,8} {2,8} {3,10} {4,10} {5,10}",
                "Rank", "Trades", "WinRate", "NetPnl", "PF", "Sharpe");
            foreach (var (r, idx) in results.Take(10).Select((r, i) => (r, i)))
            {
                string paramStr = string.Join(" ", r.Parameters.Select(kv => $"{kv.Key}={kv.Value}"));
                Console.WriteLine("  {0,5} {1,8} {2,7:F1}% {3,10:F2} {4,10:F2} {5,10:F3}  {6}",
                    idx + 1, r.TotalTrades, r.WinRate, r.NetPnl, r.ProfitFactor, r.SharpeRatio, paramStr);
            }

            StrategyOptimizer.ExportCsv(results, outputCsv);
            Console.WriteLine();
            Console.WriteLine($"  Full results: {outputCsv} ({results.Count} rows)");
            return 0;
        }

        // ══════════════════════════════════════════════════════════════════
        //  PARITY — compare simulator vs NT8 output
        // ══════════════════════════════════════════════════════════════════

        static int RunParity(string[] args)
        {
            if (args.Length < 2)
            {
                Console.WriteLine("Usage: parity <session.ndjson> <nt8-output.txt>");
                return 1;
            }

            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Parity Check");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            string sessionPath = args[0];
            string nt8Path = args[1];

            // Run session through simulator
            var session = NdjsonSessionLoader.Load(sessionPath);
            var runner = new NinjaScriptRunner();
            runner.LoadBars(session.Bars);
            runner.LoadDepthUpdates(session.DepthUpdates);
            var script = runner.Run<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>();

            // Load NT8 output
            var nt8Lines = ParityChecker.LoadNt8Output(nt8Path);

            Console.WriteLine($"  Simulator: {script.PrintLog.Count} lines");
            Console.WriteLine($"  NT8:       {nt8Lines.Length} lines");
            Console.WriteLine();

            var report = ParityChecker.Compare(script.PrintLog, nt8Lines);
            ParityChecker.PrintReport(report);

            Console.WriteLine();
            Console.WriteLine(report.Passed
                ? "[PASS] Simulator output matches NT8."
                : $"[DIFF] {report.Differences} difference(s) found.");

            return report.Passed ? 0 : 1;
        }

        // ══════════════════════════════════════════════════════════════════
        //  SIGNALS — signal attribution analysis
        // ══════════════════════════════════════════════════════════════════

        static int RunSignals(string[] args)
        {
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Signal Attribution");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            var files = CollectFiles(args);
            if (files.Count == 0) { Console.WriteLine("Usage: signals <session.ndjson> [--output signals.csv]"); return 1; }

            string outputCsv = args.FirstOrDefault(a => a.EndsWith(".csv")) ??
                (args.Contains("--output") ? args[Array.IndexOf(args, "--output") + 1] : null);

            var session = NdjsonSessionLoader.LoadMultiple(files.ToArray());
            var runner = new NinjaScriptRunner();
            runner.LoadBars(session.Bars);
            runner.LoadDepthUpdates(session.DepthUpdates);
            var script = runner.Run<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>();

            var report = SignalAttribution.Analyze(script.PrintLog);
            SignalAttribution.PrintReport(report);

            if (outputCsv != null)
            {
                SignalAttribution.ExportCsv(report, outputCsv);
                Console.WriteLine($"\n  Exported: {outputCsv}");
            }

            return 0;
        }

        // ══════════════════════════════════════════════════════════════════
        //  WALKFORWARD — rolling in-sample / out-of-sample
        // ══════════════════════════════════════════════════════════════════

        static int RunWalkForward(string[] args)
        {
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Walk-Forward Analysis");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            int isBars = 200, oosBars = 50;
            string outputCsv = null;
            var files = new List<string>();

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--is" && i + 1 < args.Length) int.TryParse(args[++i], out isBars);
                else if (args[i] == "--oos" && i + 1 < args.Length) int.TryParse(args[++i], out oosBars);
                else if (args[i] == "--output" && i + 1 < args.Length) outputCsv = args[++i];
                else if (args[i] == "--dir" && i + 1 < args.Length)
                    files.AddRange(Directory.GetFiles(args[++i], "*.ndjson").OrderBy(f => f));
                else if (File.Exists(args[i])) files.Add(args[i]);
            }

            if (files.Count == 0) { Console.WriteLine("Usage: walkforward <session.ndjson> [--is 200] [--oos 50]"); return 1; }

            var session = NdjsonSessionLoader.LoadMultiple(files.ToArray());
            Console.WriteLine($"  Data: {session.Bars.Count} bars, IS={isBars}, OOS={oosBars}");
            Console.WriteLine();

            var wf = new WalkForwardAnalyzer(isBars, oosBars);
            wf.AddSweep("ScoreEntryThreshold", 50, 90, 10);

            var sw = Stopwatch.StartNew();
            var report = wf.Run(session);
            sw.Stop();

            Console.WriteLine($"  Completed in {sw.ElapsedMilliseconds}ms");
            Console.WriteLine();
            WalkForwardAnalyzer.PrintReport(report);

            if (outputCsv != null)
            {
                WalkForwardAnalyzer.ExportCsv(report, outputCsv);
                Console.WriteLine($"\n  Exported: {outputCsv}");
            }

            return 0;
        }

        // ══════════════════════════════════════════════════════════════════
        //  MONTECARLO — trade resampling for drawdown distributions
        // ══════════════════════════════════════════════════════════════════

        static int RunMonteCarlo(string[] args)
        {
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Monte Carlo Analysis");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            int iterations = 10000;
            string outputCsv = null;
            var files = new List<string>();

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--iterations" && i + 1 < args.Length) int.TryParse(args[++i], out iterations);
                else if (args[i] == "--output" && i + 1 < args.Length) outputCsv = args[++i];
                else if (args[i] == "--dir" && i + 1 < args.Length)
                    files.AddRange(Directory.GetFiles(args[++i], "*.ndjson").OrderBy(f => f));
                else if (File.Exists(args[i])) files.Add(args[i]);
            }

            if (files.Count == 0) { Console.WriteLine("Usage: montecarlo <session.ndjson> [--iterations 10000]"); return 1; }

            // Run strategy to get trades
            var session = NdjsonSessionLoader.LoadMultiple(files.ToArray());
            var runner = new NinjaScriptRunner();
            runner.LoadBars(session.Bars);
            runner.LoadDepthUpdates(session.DepthUpdates);
            var script = runner.Run<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>();

            var trades = MonteCarlo.ExtractTradesFromLog(script.PrintLog);
            Console.WriteLine($"  Extracted {trades.Count} trades from {session.Bars.Count} bars");
            Console.WriteLine($"  Running {iterations} iterations...");

            var sw = Stopwatch.StartNew();
            var mc = MonteCarlo.Run(trades, iterations);
            sw.Stop();

            Console.WriteLine($"  Completed in {sw.ElapsedMilliseconds}ms");
            Console.WriteLine();
            MonteCarlo.PrintReport(mc);

            if (outputCsv != null)
            {
                MonteCarlo.ExportCsv(mc, outputCsv);
                Console.WriteLine($"\n  Exported: {outputCsv} ({iterations} rows)");
            }

            return 0;
        }

        // ══════════════════════════════════════════════════════════════════
        //  CLASSIFY — session regime classification
        // ══════════════════════════════════════════════════════════════════

        static int RunClassify(string[] args)
        {
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Session Classifier");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            string outputCsv = null;
            var files = new List<string>();

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--output" && i + 1 < args.Length) outputCsv = args[++i];
                else if (args[i] == "--dir" && i + 1 < args.Length)
                    files.AddRange(Directory.GetFiles(args[++i], "*.ndjson").OrderBy(f => f));
                else if (File.Exists(args[i])) files.Add(args[i]);
            }

            if (files.Count == 0) { Console.WriteLine("Usage: classify <session1.ndjson> <session2.ndjson> ... [--output classify.csv]"); return 1; }

            Console.WriteLine($"  Analyzing {files.Count} sessions...");
            Console.WriteLine();

            var sw = Stopwatch.StartNew();
            var report = SessionClassifier.Classify(files.ToArray());
            sw.Stop();

            Console.WriteLine($"  Completed in {sw.ElapsedMilliseconds}ms");
            Console.WriteLine();
            SessionClassifier.PrintReport(report);

            if (outputCsv != null)
            {
                SessionClassifier.ExportCsv(report, outputCsv);
                Console.WriteLine($"\n  Exported: {outputCsv}");
            }

            return 0;
        }

        // ══════════════════════════════════════════════════════════════════
        //  Helpers
        // ══════════════════════════════════════════════════════════════════

        static List<string> CollectFiles(string[] args)
        {
            var files = new List<string>();
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--dir" && i + 1 < args.Length)
                    files.AddRange(Directory.GetFiles(args[++i], "*.ndjson").OrderBy(f => f));
                else if (args[i] == "--output" || args[i] == "--csv") i++; // skip value
                else if (File.Exists(args[i])) files.Add(args[i]);
            }
            return files;
        }

        // ══════════════════════════════════════════════════════════════════
        //  CHART — standalone HTML candle chart
        // ══════════════════════════════════════════════════════════════════

        static int RunChart(string[] args)
        {
            string outputPath = "chart.html";
            var files = new List<string>();

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--output" && i + 1 < args.Length) outputPath = args[++i];
                else if (args[i] == "--dir" && i + 1 < args.Length)
                    files.AddRange(Directory.GetFiles(args[++i], "*.ndjson").OrderBy(f => f));
                else if (File.Exists(args[i])) files.Add(args[i]);
            }

            if (files.Count == 0) { Console.WriteLine("Usage: chart <session.ndjson> [--output chart.html]"); return 1; }

            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Chart Export");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            var session = NdjsonSessionLoader.LoadMultiple(files.ToArray());
            var runner = new NinjaScriptRunner();
            runner.LoadBars(session.Bars);
            runner.LoadDepthUpdates(session.DepthUpdates);
            var script = runner.Run<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>();

            ChartExporter.ExportCandleChart(session, script.PrintLog, outputPath);
            Console.WriteLine($"  Chart exported: {outputPath}");
            Console.WriteLine($"  Bars: {session.Bars.Count} | Signals: {script.PrintLog.Count(l => l.Contains("[DEEP6 Registry]"))} | Entries: {script.PrintLog.Count(l => l.Contains("entry"))}");
            Console.WriteLine($"  Open with: open {outputPath}");
            return 0;
        }

        // ══════════════════════════════════════════════════════════════════
        //  FOOTPRINT — standalone HTML footprint chart (full cells)
        // ══════════════════════════════════════════════════════════════════

        static int RunFootprint(string[] args)
        {
            string outputPath = "footprint.html";
            var files = new List<string>();

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--output" && i + 1 < args.Length) outputPath = args[++i];
                else if (args[i] == "--dir" && i + 1 < args.Length)
                    files.AddRange(Directory.GetFiles(args[++i], "*.ndjson").OrderBy(f => f));
                else if (File.Exists(args[i])) files.Add(args[i]);
            }

            if (files.Count == 0) { Console.WriteLine("Usage: footprint <session.ndjson> [--output footprint.html]"); return 1; }

            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Footprint Chart Export");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            var session = NdjsonSessionLoader.LoadMultiple(files.ToArray());
            var runner = new NinjaScriptRunner();
            runner.LoadBars(session.Bars);
            runner.LoadDepthUpdates(session.DepthUpdates);
            var script = runner.Run<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>();

            ChartExporter.ExportFootprintChart(session, script.PrintLog, outputPath);
            Console.WriteLine($"  Footprint exported: {outputPath}");
            Console.WriteLine($"  Bars: {session.Bars.Count} | Levels rendered per bar | Signals overlaid");
            Console.WriteLine($"  Open with: open {outputPath}");
            return 0;
        }

        // ══════════════════════════════════════════════════════════════════
        //  DESIGN — Chart Design Studio (live parameter tuning)
        // ══════════════════════════════════════════════════════════════════

        static int RunDesign(string[] args)
        {
            string outputPath = "design-studio.html";
            var files = new List<string>();

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--output" && i + 1 < args.Length) outputPath = args[++i];
                else if (args[i] == "--dir" && i + 1 < args.Length)
                    files.AddRange(Directory.GetFiles(args[++i], "*.ndjson").OrderBy(f => f));
                else if (File.Exists(args[i])) files.Add(args[i]);
            }

            if (files.Count == 0) { Console.WriteLine("Usage: design <session.ndjson> [--output design-studio.html]"); return 1; }

            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Design Studio");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            var session = NdjsonSessionLoader.LoadMultiple(files.ToArray());
            DesignStudio.Export(session, outputPath);
            Console.WriteLine($"  Design Studio exported: {outputPath}");
            Console.WriteLine($"  Bars loaded: {System.Math.Min(session.Bars.Count, 30)} (capped at 30 for responsiveness)");
            Console.WriteLine();
            Console.WriteLine("  Features:");
            Console.WriteLine("    - Live color pickers for all cell/signal/tier colors");
            Console.WriteLine("    - Sliders for geometry (column width, row height, font size)");
            Console.WriteLine("    - Opacity curves, imbalance threshold, display toggles");
            Console.WriteLine("    - Export JSON Theme (for simulator + dashboard)");
            Console.WriteLine("    - Export NT8 C# Code (Color.FromArgb for DEEP6Footprint.cs)");
            Console.WriteLine("    - Split-view comparison (before/after)");
            Console.WriteLine();
            Console.WriteLine($"  Open with: open {outputPath}");
            return 0;
        }

        // ══════════════════════════════════════════════════════════════════
        //  SERVE — JSON server for Next.js dashboard
        // ══════════════════════════════════════════════════════════════════

        static int RunServe(string[] args)
        {
            int port = 8080;
            var files = new List<string>();

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--port" && i + 1 < args.Length) int.TryParse(args[++i], out port);
                else if (args[i] == "--dir" && i + 1 < args.Length)
                    files.AddRange(Directory.GetFiles(args[++i], "*.ndjson").OrderBy(f => f));
                else if (File.Exists(args[i])) files.Add(args[i]);
            }

            if (files.Count == 0) { Console.WriteLine("Usage: serve <session.ndjson> [--port 8080]"); return 1; }

            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Dashboard Server");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            var session = NdjsonSessionLoader.LoadMultiple(files.ToArray());
            var runner = new NinjaScriptRunner();
            runner.LoadBars(session.Bars);
            runner.LoadDepthUpdates(session.DepthUpdates);
            var script = runner.Run<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>();

            // Export JSON to temp file, then serve
            string jsonPath = Path.GetTempFileName() + ".json";
            ChartExporter.ExportDashboardJson(session, script.PrintLog, jsonPath);
            Console.WriteLine($"  Session: {session.Bars.Count} bars → dashboard JSON");

            try
            {
                ChartExporter.StartServer(jsonPath, port);
            }
            finally
            {
                try { File.Delete(jsonPath); } catch { }
            }

            return 0;
        }

        static void PrintUsage()
        {
            Console.WriteLine(@"
NinjaScript Simulator — validate, backtest, analyze, and forward-test without NinjaTrader

USAGE:
  dotnet run --project ninjatrader/simulator -- <command> [args]

DATA COMMANDS:
  validate [all|indicator|strategy]     Compile-check + state machine validation
  run [all|indicator|strategy]          Lifecycle replay with synthetic bars
  replay <session.ndjson> [...]         Replay captured NDJSON session(s) through strategy
  replay --dir <directory>              Replay all .ndjson files in directory
  databento <ohlcv.csv>                 Replay Databento OHLCV-1m CSV
  databento-mbo <trades.csv>            Convert Databento MBO trades → replay
  bridge [host:port]                    Connect to NT8 DataBridge for live data
  bridge --record <output.ndjson>       Bridge + record for later replay

ANALYTICS COMMANDS:
  optimize --data <files> --sweep P=f:s:t   Parallel parameter sweep (CSV output)
  parity <session.ndjson> <nt8-output.txt>  Compare simulator vs NT8 output
  signals <session.ndjson> [--output .csv]  Signal attribution (per-detector stats)
  walkforward <files> [--is 200] [--oos 50] Walk-forward overfit detection
  montecarlo <files> [--iterations 10000]   Monte Carlo drawdown distribution
  classify <session1> <session2> ...        Classify sessions by regime/outcome

CHART COMMANDS:
  chart <session.ndjson> [--output c.html]  Candle chart (Lightweight Charts) + signals + entries
  footprint <session.ndjson> [--output f.html]  Footprint chart (bid x ask cells, POC, signals, HUD)
  serve <session.ndjson> [--port 8080]      JSON server for the Next.js dashboard

EXAMPLES:
  # Replay captured sessions:
  dotnet run --project ninjatrader/simulator -- replay --dir ninjatrader/tests/fixtures/sessions/

  # Parameter optimization:
  dotnet run --project ninjatrader/simulator -- optimize \
    --dir ninjatrader/tests/fixtures/sessions/ \
    --sweep ScoreEntryThreshold=50:5:90 --sweep StopLossTicks=12:2:30

  # Signal attribution (which detectors make money?):
  dotnet run --project ninjatrader/simulator -- signals --dir ninjatrader/tests/fixtures/sessions/

  # Parity check (simulator vs NT8):
  dotnet run --project ninjatrader/simulator -- parity session.ndjson nt8-output.txt

  # Monte Carlo drawdown analysis:
  dotnet run --project ninjatrader/simulator -- montecarlo --dir sessions/ --iterations 10000

  # Walk-forward (overfit detection):
  dotnet run --project ninjatrader/simulator -- walkforward --dir sessions/ --is 200 --oos 50

  # Session regime classification:
  dotnet run --project ninjatrader/simulator -- classify --dir ninjatrader/tests/fixtures/sessions/

  # Connect to NT8 bridge:
  dotnet run --project ninjatrader/simulator -- bridge 192.168.1.100:9200
");
        }

        static int PrintUsageOk() { PrintUsage(); return 0; }
        static int PrintUnknownCommand(string cmd) { Console.WriteLine($"Unknown command: {cmd}"); PrintUsage(); return 1; }
    }
}
