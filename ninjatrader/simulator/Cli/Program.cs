// NinjaScriptSim CLI — validate and test NinjaScript code without NinjaTrader.
//
// Usage:
//   dotnet run --project ninjatrader/simulator -- validate           # compile-check all DEEP6 scripts
//   dotnet run --project ninjatrader/simulator -- validate indicator # compile-check indicator only
//   dotnet run --project ninjatrader/simulator -- validate strategy  # compile-check strategy only
//   dotnet run --project ninjatrader/simulator -- run indicator      # run indicator lifecycle with sample bars
//   dotnet run --project ninjatrader/simulator -- run strategy       # run strategy lifecycle with sample bars
//   dotnet run --project ninjatrader/simulator -- lifecycle          # run full lifecycle for all scripts

using System;
using System.Collections.Generic;
using System.Diagnostics;
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
            string target = args.Length > 1 ? args[1].ToLower() : "all";

            return command switch
            {
                "validate" => RunValidate(target),
                "run" => RunLifecycle(target),
                "lifecycle" => RunLifecycle("all"),
                "help" or "--help" or "-h" => PrintUsageOk(),
                _ => PrintUnknownCommand(command),
            };
        }

        static int RunValidate(string target)
        {
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Compile Validation");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            // If we got here, the project COMPILED — all NinjaScript source files
            // are valid C# against the stub assembly. That's the primary gate.
            Console.WriteLine("[PASS] All NinjaScript source files compiled successfully against stubs.");
            Console.WriteLine();

            // Now run lifecycle validation (state machine, no bar data)
            int failures = 0;
            var runner = new NinjaScriptRunner();

            if (target == "all" || target == "indicator")
            {
                failures += ValidateScript<NinjaTrader.NinjaScript.Indicators.DEEP6.DEEP6Footprint>(runner, "DEEP6Footprint (Indicator)");
            }

            if (target == "all" || target == "strategy")
            {
                failures += ValidateScript<NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy>(runner, "DEEP6Strategy (Strategy)");
            }

            Console.WriteLine();
            if (failures == 0)
            {
                Console.WriteLine("[PASS] All validation checks passed.");
                return 0;
            }
            else
            {
                Console.WriteLine($"[FAIL] {failures} validation check(s) failed.");
                return 1;
            }
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
                    foreach (var err in runner.Errors)
                        Console.WriteLine($"    ERROR: {err}");
                    return 1;
                }
                else
                {
                    Console.WriteLine($"OK ({sw.ElapsedMilliseconds}ms)");
                    if (runner.Warnings.Count > 0)
                    {
                        foreach (var warn in runner.Warnings)
                            Console.WriteLine($"    WARN: {warn}");
                    }
                    // Print summary of Print() output if any
                    if (script.PrintLog.Count > 0)
                    {
                        Console.WriteLine($"    Print output: {script.PrintLog.Count} line(s)");
                        int maxShow = Math.Min(5, script.PrintLog.Count);
                        for (int i = 0; i < maxShow; i++)
                            Console.WriteLine($"      > {script.PrintLog[i]}");
                        if (script.PrintLog.Count > maxShow)
                            Console.WriteLine($"      ... and {script.PrintLog.Count - maxShow} more");
                    }
                    return 0;
                }
            }
            catch (Exception ex)
            {
                sw.Stop();
                Console.WriteLine($"CRASH ({sw.ElapsedMilliseconds}ms)");
                Console.WriteLine($"    {ex.GetType().Name}: {ex.Message}");
                Console.WriteLine($"    {ex.StackTrace?.Split('\n')[0]}");
                return 1;
            }
        }

        static int RunLifecycle(string target)
        {
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine(" NinjaScript Simulator — Lifecycle Replay");
            Console.WriteLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            Console.WriteLine();

            // Generate sample bars for a simulated NQ session
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
                    if (runner.Errors.Count > 0)
                    {
                        Console.WriteLine($"FAIL ({sw.ElapsedMilliseconds}ms)");
                        foreach (var err in runner.Errors)
                            Console.WriteLine($"    ERROR: {err}");
                        failures++;
                    }
                    else
                    {
                        Console.WriteLine($"OK ({sw.ElapsedMilliseconds}ms, {script.PrintLog.Count} print lines)");
                    }
                }
                catch (Exception ex)
                {
                    sw.Stop();
                    Console.WriteLine($"CRASH ({sw.ElapsedMilliseconds}ms)");
                    Console.WriteLine($"    {ex.GetType().Name}: {ex.Message}");
                    failures++;
                }
            }

            if (target == "all" || target == "strategy")
            {
                Console.Write("  Running DEEP6Strategy lifecycle... ");
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
                        failures++;
                    }
                    else
                    {
                        Console.WriteLine($"OK ({sw.ElapsedMilliseconds}ms, {script.PrintLog.Count} print lines)");
                    }
                }
                catch (Exception ex)
                {
                    sw.Stop();
                    Console.WriteLine($"CRASH ({sw.ElapsedMilliseconds}ms)");
                    Console.WriteLine($"    {ex.GetType().Name}: {ex.Message}");
                    failures++;
                }
            }

            Console.WriteLine();
            if (failures == 0)
            {
                Console.WriteLine("[PASS] All lifecycle checks passed.");
                return 0;
            }
            else
            {
                Console.WriteLine($"[FAIL] {failures} lifecycle check(s) failed.");
                return 1;
            }
        }

        /// <summary>
        /// Generate synthetic NQ 1-minute bars for a simulated RTH session.
        /// Includes tick data within each bar for OnMarketData replay.
        /// </summary>
        static List<BarData> GenerateSampleBars()
        {
            var bars = new List<BarData>();
            var rng = new Random(42);
            double price = 19000.0;
            double tickSize = 0.25;
            var baseTime = new DateTime(2026, 4, 16, 9, 30, 0); // RTH open

            for (int i = 0; i < 60; i++) // 60 one-minute bars (9:30-10:30 ET)
            {
                double change = (rng.NextDouble() - 0.48) * 20.0; // slight upward bias
                double open = Math.Round(price / tickSize) * tickSize;
                double close = Math.Round((price + change) / tickSize) * tickSize;
                double high = Math.Max(open, close) + rng.Next(1, 8) * tickSize;
                double low = Math.Min(open, close) - rng.Next(1, 8) * tickSize;
                long volume = rng.Next(500, 3000);
                var barTime = baseTime.AddMinutes(i + 1);

                // Generate ticks within the bar
                var ticks = new List<TickData>();
                int tickCount = rng.Next(20, 80);
                double tickPrice = open;
                long tickVolRemaining = volume;
                for (int t = 0; t < tickCount && tickVolRemaining > 0; t++)
                {
                    double tickChange = (rng.NextDouble() - 0.5) * 4.0 * tickSize;
                    tickPrice = Math.Round(Math.Max(low, Math.Min(high, tickPrice + tickChange)) / tickSize) * tickSize;
                    long tickSize2 = Math.Min(rng.Next(1, 30), tickVolRemaining);
                    int aggressor = tickPrice >= (high - (high - low) * 0.3) ? 1
                                  : tickPrice <= (low + (high - low) * 0.3) ? 2
                                  : rng.Next(0, 3);

                    ticks.Add(new TickData
                    {
                        Price = tickPrice,
                        Size = tickSize2,
                        Aggressor = aggressor,
                        Time = barTime.AddSeconds(-60 + (60.0 * t / tickCount)),
                    });
                    tickVolRemaining -= tickSize2;
                }
                // Ensure last tick is at close price
                if (ticks.Count > 0) ticks[ticks.Count - 1].Price = close;

                bars.Add(new BarData
                {
                    Open = open, High = high, Low = low, Close = close,
                    Volume = volume, Time = barTime,
                    Ticks = ticks,
                });

                price = close;
            }

            return bars;
        }

        static void PrintUsage()
        {
            Console.WriteLine(@"
NinjaScript Simulator — validate and test NinjaScript code without NinjaTrader

USAGE:
  dotnet run --project ninjatrader/simulator -- <command> [target]

COMMANDS:
  validate [all|indicator|strategy]   Compile-check + state machine validation
  run [all|indicator|strategy]        Full lifecycle replay with sample bars
  lifecycle                           Alias for 'run all'
  help                                Show this help

EXAMPLES:
  dotnet run --project ninjatrader/simulator -- validate
  dotnet run --project ninjatrader/simulator -- validate indicator
  dotnet run --project ninjatrader/simulator -- run strategy
  dotnet run --project ninjatrader/simulator -- lifecycle

The compilation itself IS the primary gate — if `dotnet build` succeeds,
all NinjaScript source files are valid C# against the NT8 stub assembly.
The validate/run commands additionally exercise the lifecycle state machine.
");
        }

        static int PrintUsageOk() { PrintUsage(); return 0; }
        static int PrintUnknownCommand(string cmd) { Console.WriteLine($"Unknown command: {cmd}"); PrintUsage(); return 1; }
    }
}
