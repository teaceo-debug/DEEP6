// CaptureReplayLoader: test-side NDJSON session replay engine.
//
// Reads .ndjson files produced by CaptureHarness and replays them deterministically
// through DetectorRegistry, collecting SignalResult[] per bar.
//
// Schema (each line is one of):
//   {"type":"depth","ts_ms":N,"side":S,"levelIdx":L,"price":P,"size":Z[,"priorSize":Q]}
//   {"type":"bar","ts_ms":N,"open":O,"high":H,"low":Lo,"close":C,"barDelta":D,"totalVol":V,"cvd":CV}
//   {"type":"session_reset","ts_ms":N}
//
// Usage:
//   var loader = new CaptureReplayLoader();
//   var result = loader.Replay(ndjsonLines, registry, session);
//   // result.BarResults[i] = SignalResult[] for bar i

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.Tests.SessionReplay
{
    /// <summary>
    /// Result of replaying a single captured session.
    /// </summary>
    public sealed class ReplayResult
    {
        /// <summary>SignalResult[] per bar, in bar order.</summary>
        public List<SignalResult[]> BarResults { get; } = new List<SignalResult[]>();

        /// <summary>Total depth events replayed.</summary>
        public int DepthEventCount { get; set; }

        /// <summary>Total bars replayed.</summary>
        public int BarCount => BarResults.Count;

        /// <summary>Total signals fired across all bars.</summary>
        public int TotalSignals
        {
            get
            {
                int n = 0;
                foreach (var r in BarResults) if (r != null) n += r.Length;
                return n;
            }
        }

        /// <summary>
        /// Count signals with a given SignalId prefix across all bars.
        /// </summary>
        public int CountByPrefix(string prefix)
        {
            int n = 0;
            foreach (var bar in BarResults)
                if (bar != null)
                    foreach (var r in bar)
                        if (r != null && r.SignalId != null && r.SignalId.StartsWith(prefix))
                            n++;
            return n;
        }
    }

    /// <summary>
    /// Replays a captured NDJSON session through a DetectorRegistry.
    ///
    /// Designed for SessionReplayParityTests: replay a known session and verify
    /// signal counts are within ±2 of expected values.
    /// </summary>
    public sealed class CaptureReplayLoader
    {
        /// <summary>
        /// Replay an NDJSON session from a string array (one element per line).
        /// </summary>
        public ReplayResult Replay(
            IEnumerable<string> ndjsonLines,
            DetectorRegistry registry,
            SessionContext session)
        {
            var result = new ReplayResult();

            foreach (string raw in ndjsonLines)
            {
                string line = raw?.Trim();
                if (string.IsNullOrEmpty(line)) continue;

                string type = ExtractString(line, "type");
                if (type == null) continue;

                if (type == "depth")
                {
                    int    side     = ExtractInt(line, "side");
                    int    levelIdx = ExtractInt(line, "levelIdx");
                    double price    = ExtractDouble(line, "price");
                    long   size     = ExtractLong(line, "size");
                    long?  prior    = HasKey(line, "priorSize") ? (long?)ExtractLong(line, "priorSize") : null;

                    registry.DispatchDepth(session, side, levelIdx, price, size, prior);
                    result.DepthEventCount++;
                }
                else if (type == "bar")
                {
                    double open     = ExtractDouble(line, "open");
                    double high     = ExtractDouble(line, "high");
                    double low      = ExtractDouble(line, "low");
                    double close    = ExtractDouble(line, "close");
                    long   delta    = ExtractLong(line, "barDelta");
                    long   totalVol = ExtractLong(line, "totalVol");
                    long   cvd      = HasKey(line, "cvd") ? ExtractLong(line, "cvd") : 0;

                    var bar = new FootprintBar
                    {
                        BarIndex = result.BarCount,
                        Open  = open,
                        High  = high,
                        Low   = low,
                        Close = close,
                    };
                    // Add synthetic levels so bar passes basic guards in detectors
                    bar.Levels[low]  = new Cell { AskVol = totalVol / 3, BidVol = totalVol / 6 };
                    bar.Levels[high] = new Cell { AskVol = totalVol / 6, BidVol = totalVol / 3 };
                    bar.Finalize();
                    bar.BarDelta = delta;
                    bar.TotalVol = totalVol;
                    bar.Cvd      = cvd;

                    var signals = registry.EvaluateBar(bar, session);
                    result.BarResults.Add(signals);
                }
                else if (type == "session_reset")
                {
                    session.ResetSession();
                    registry.ResetAll();
                }
            }

            return result;
        }

        // -----------------------------------------------------------------------
        // Minimal JSON field extractors (no System.Text.Json dependency on hot path;
        // avoids adding a heavy JSON parser dependency to the test project).
        // These are parse-only helpers for well-formed NDJSON.
        // -----------------------------------------------------------------------

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

        private static bool HasKey(string json, string key)
        {
            return json.IndexOf("\"" + key + "\":", StringComparison.Ordinal) >= 0;
        }

        private static double ExtractDouble(string json, string key)
        {
            string s = ExtractValue(json, key);
            double v;
            return double.TryParse(s, System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out v) ? v : 0.0;
        }

        private static long ExtractLong(string json, string key)
        {
            string s = ExtractValue(json, key);
            long v;
            return long.TryParse(s, out v) ? v : 0L;
        }

        private static int ExtractInt(string json, string key)
        {
            string s = ExtractValue(json, key);
            int v;
            return int.TryParse(s, out v) ? v : 0;
        }

        private static string ExtractValue(string json, string key)
        {
            string search = "\"" + key + "\":";
            int start = json.IndexOf(search, StringComparison.Ordinal);
            if (start < 0) return null;
            start += search.Length;
            // Skip leading whitespace
            while (start < json.Length && json[start] == ' ') start++;
            if (start >= json.Length) return null;
            // Find end: comma or } or end of string
            int end = start;
            while (end < json.Length && json[end] != ',' && json[end] != '}') end++;
            return json.Substring(start, end - start).Trim();
        }
    }
}
