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

        static void PrintUsage()
        {
            Console.WriteLine(@"
NinjaScript Simulator — validate, backtest, and forward-test without NinjaTrader

USAGE:
  dotnet run --project ninjatrader/simulator -- <command> [args]

COMMANDS:
  validate [all|indicator|strategy]     Compile-check + state machine validation
  run [all|indicator|strategy]          Lifecycle replay with synthetic bars
  replay <session.ndjson> [...]         Replay captured NDJSON session(s) through strategy
  replay --dir <directory>              Replay all .ndjson files in directory
  databento <ohlcv.csv>                 Replay Databento OHLCV-1m CSV through strategy
  databento-mbo <trades.csv>            Convert Databento MBO trades → NDJSON → strategy replay
  bridge [host:port]                    Connect to NT8 DataBridge for live data (default 127.0.0.1:9200)
  bridge --record <output.ndjson>       Bridge + record session to file for later replay

DATA FLOW:
  Databento CSV ─┐
  NT8 Bridge ────┤── NDJSON ──→ NinjaScriptRunner ──→ DEEP6Strategy
  Captured .ndjson─┘                                   (full lifecycle)

EXAMPLES:
  # Replay your 5 captured NT8 sessions:
  dotnet run --project ninjatrader/simulator -- replay ninjatrader/tests/fixtures/sessions/*.ndjson

  # Load Databento OHLCV and run strategy:
  dotnet run --project ninjatrader/simulator -- databento NQ_ohlcv_1m.csv

  # Connect to NT8 running on Windows (same machine or via SSH tunnel):
  dotnet run --project ninjatrader/simulator -- bridge 192.168.1.100:9200

  # Record a live session from NT8, then replay it later:
  dotnet run --project ninjatrader/simulator -- bridge --record today.ndjson
  dotnet run --project ninjatrader/simulator -- replay today.ndjson
");
        }

        static int PrintUsageOk() { PrintUsage(); return 0; }
        static int PrintUnknownCommand(string cmd) { Console.WriteLine($"Unknown command: {cmd}"); PrintUsage(); return 1; }
    }
}
