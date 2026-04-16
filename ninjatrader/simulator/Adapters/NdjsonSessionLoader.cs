// NdjsonSessionLoader: Loads captured NDJSON session files into the NinjaScriptRunner.
//
// Reads the same format produced by CaptureHarness (NT8 AddOn) and the NT8 Data Bridge:
//   {"type":"depth","ts_ms":N,"side":S,"levelIdx":L,"price":P,"size":Z[,"priorSize":Q]}
//   {"type":"bar","ts_ms":N,"open":O,"high":H,"low":Lo,"close":C,"barDelta":D,"totalVol":V,"cvd":CV}
//   {"type":"trade","ts_ms":N,"price":P,"size":S,"aggressor":A}
//   {"type":"session_reset","ts_ms":N}
//
// This is the common format shared by:
//   1. CaptureHarness (records from live NT8)
//   2. NT8 Data Bridge (forwards from running NT8 instance)
//   3. Databento adapter (converts MBO events to this format)
//
// Usage:
//   var loader = new NdjsonSessionLoader();
//   var session = loader.Load("path/to/session.ndjson");
//   runner.LoadBars(session.Bars);
//   runner.LoadDepthUpdates(session.DepthUpdates);
//   runner.Run<DEEP6Strategy>();

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using NinjaTrader.Data;

namespace NinjaScriptSim.Lifecycle
{
    /// <summary>
    /// Parsed session data ready for NinjaScriptRunner.
    /// </summary>
    public class SessionData
    {
        public List<BarData> Bars { get; } = new();
        public List<DepthUpdate> DepthUpdates { get; } = new();
        public int TradeCount { get; set; }
        public int SessionResetCount { get; set; }

        /// <summary>Bar period in minutes (detected from timestamps).</summary>
        public int BarPeriodMinutes { get; set; } = 1;
    }

    /// <summary>
    /// Loads NDJSON session files into BarData + DepthUpdate + TickData
    /// for the NinjaScriptRunner lifecycle.
    /// </summary>
    public static class NdjsonSessionLoader
    {
        /// <summary>
        /// Load a single NDJSON file. Bars get tick data attached from
        /// interleaved trade events between bar boundaries.
        /// </summary>
        public static SessionData Load(string ndjsonPath)
        {
            var lines = File.ReadAllLines(ndjsonPath);
            return Parse(lines);
        }

        /// <summary>Load from string array (for testing or streaming).</summary>
        public static SessionData Parse(IEnumerable<string> lines)
        {
            var session = new SessionData();
            var pendingTicks = new List<TickData>();
            BarData currentBar = null;
            DateTime lastBarTime = DateTime.MinValue;

            foreach (string raw in lines)
            {
                string line = raw?.Trim();
                if (string.IsNullOrEmpty(line)) continue;

                string type = ExtractString(line, "type");
                if (type == null) continue;

                switch (type)
                {
                    case "depth":
                    {
                        int side = ExtractInt(line, "side");
                        int levelIdx = ExtractInt(line, "levelIdx");
                        double price = ExtractDouble(line, "price");
                        long size = ExtractLong(line, "size");
                        long tsMs = ExtractLong(line, "ts_ms");

                        session.DepthUpdates.Add(new DepthUpdate
                        {
                            Side = side == 0 ? MarketDataType.Bid : MarketDataType.Ask,
                            Operation = size == 0 ? Operation.Remove : Operation.Update,
                            Position = levelIdx,
                            Price = price,
                            Volume = size,
                            Time = DateTimeOffset.FromUnixTimeMilliseconds(tsMs).UtcDateTime,
                        });
                        break;
                    }

                    case "trade":
                    {
                        double price = ExtractDouble(line, "price");
                        long size = ExtractLong(line, "size");
                        int aggressor = ExtractInt(line, "aggressor");
                        long tsMs = ExtractLong(line, "ts_ms");

                        pendingTicks.Add(new TickData
                        {
                            Price = price,
                            Size = size,
                            Aggressor = aggressor,
                            Time = DateTimeOffset.FromUnixTimeMilliseconds(tsMs).UtcDateTime,
                        });
                        session.TradeCount++;
                        break;
                    }

                    case "bar":
                    {
                        // Attach pending ticks to the previous bar
                        if (currentBar != null && pendingTicks.Count > 0)
                        {
                            currentBar.Ticks = new List<TickData>(pendingTicks);
                            pendingTicks.Clear();
                        }

                        double open = ExtractDouble(line, "open");
                        double high = ExtractDouble(line, "high");
                        double low = ExtractDouble(line, "low");
                        double close = ExtractDouble(line, "close");
                        long totalVol = ExtractLong(line, "totalVol");
                        long tsMs = ExtractLong(line, "ts_ms");
                        DateTime barTime = DateTimeOffset.FromUnixTimeMilliseconds(tsMs).UtcDateTime;

                        // Detect bar period from first two bars
                        if (session.Bars.Count == 1 && lastBarTime != DateTime.MinValue)
                        {
                            int mins = (int)(barTime - lastBarTime).TotalMinutes;
                            if (mins > 0) session.BarPeriodMinutes = mins;
                        }

                        currentBar = new BarData
                        {
                            Open = open,
                            High = high,
                            Low = low,
                            Close = close,
                            Volume = totalVol,
                            Time = barTime,
                        };

                        // If no tick data between bars, synthesize ticks from OHLC
                        // so OnMarketData gets called (builds FootprintBar)
                        if (pendingTicks.Count == 0)
                        {
                            currentBar.Ticks = SynthesizeTicks(currentBar, barTime);
                        }

                        session.Bars.Add(currentBar);
                        lastBarTime = barTime;
                        break;
                    }

                    case "session_reset":
                        session.SessionResetCount++;
                        break;
                }
            }

            // Attach any trailing ticks to the last bar
            if (currentBar != null && pendingTicks.Count > 0)
            {
                currentBar.Ticks = new List<TickData>(pendingTicks);
            }

            return session;
        }

        /// <summary>
        /// Load multiple session files and concatenate them.
        /// </summary>
        public static SessionData LoadMultiple(string[] ndjsonPaths)
        {
            var combined = new SessionData();
            foreach (string path in ndjsonPaths)
            {
                var session = Load(path);
                combined.Bars.AddRange(session.Bars);
                combined.DepthUpdates.AddRange(session.DepthUpdates);
                combined.TradeCount += session.TradeCount;
                combined.SessionResetCount += session.SessionResetCount;
            }
            return combined;
        }

        /// <summary>
        /// Synthesize ticks from bar OHLC when no real tick data is available.
        /// Creates a minimal tick sequence: Open → High → Low → Close with
        /// aggressor classification based on price movement.
        /// </summary>
        private static List<TickData> SynthesizeTicks(BarData bar, DateTime barTime)
        {
            var ticks = new List<TickData>();
            long perTick = System.Math.Max(bar.Volume / 4, 1);
            double mid = (bar.High + bar.Low) / 2.0;

            // Open
            ticks.Add(new TickData
            {
                Price = bar.Open, Size = perTick,
                Aggressor = bar.Open >= mid ? 1 : 2,
                Time = barTime.AddSeconds(-45),
            });
            // High
            ticks.Add(new TickData
            {
                Price = bar.High, Size = perTick,
                Aggressor = 1, // buying pushed to high
                Time = barTime.AddSeconds(-30),
            });
            // Low
            ticks.Add(new TickData
            {
                Price = bar.Low, Size = perTick,
                Aggressor = 2, // selling pushed to low
                Time = barTime.AddSeconds(-15),
            });
            // Close
            ticks.Add(new TickData
            {
                Price = bar.Close, Size = perTick,
                Aggressor = bar.Close > bar.Open ? 1 : 2,
                Time = barTime,
            });

            return ticks;
        }

        // ── Minimal JSON field extractors (same pattern as CaptureReplayLoader) ──

        private static string ExtractString(string json, string key)
        {
            string search = "\"" + key + "\":\"";
            int start = json.IndexOf(search, StringComparison.Ordinal);
            if (start < 0) return null;
            start += search.Length;
            int end = json.IndexOf('"', start);
            if (end < 0) return null;
            return json.Substring(start, end - start);
        }

        private static double ExtractDouble(string json, string key)
        {
            string s = ExtractValue(json, key);
            return double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out double v) ? v : 0.0;
        }

        private static long ExtractLong(string json, string key)
        {
            string s = ExtractValue(json, key);
            return long.TryParse(s, out long v) ? v : 0L;
        }

        private static int ExtractInt(string json, string key)
        {
            string s = ExtractValue(json, key);
            return int.TryParse(s, out int v) ? v : 0;
        }

        private static string ExtractValue(string json, string key)
        {
            string search = "\"" + key + "\":";
            int start = json.IndexOf(search, StringComparison.Ordinal);
            if (start < 0) return null;
            start += search.Length;
            while (start < json.Length && json[start] == ' ') start++;
            if (start >= json.Length) return null;
            int end = start;
            while (end < json.Length && json[end] != ',' && json[end] != '}') end++;
            return json.Substring(start, end - start).Trim();
        }
    }
}
