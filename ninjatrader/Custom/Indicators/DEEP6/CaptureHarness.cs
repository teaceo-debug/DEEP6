// CaptureHarness: NDJSON session capture for offline parity testing.
//
// Purpose:
//   Records real-time depth events and bar completions to a line-delimited JSON file
//   so the same session can be replayed deterministically in tests (CaptureReplayLoader).
//
// Output file format: captures/YYYY-MM-DD-session.ndjson
//   Each line is a self-contained JSON object:
//     {"type":"depth","ts_ms":1234567890123,"side":0,"levelIdx":0,"price":20000.0,"size":500,"priorSize":450}
//     {"type":"bar","ts_ms":1234567890456,"open":20000.0,"high":20002.0,"low":19998.0,"close":20001.0,"barDelta":200,"totalVol":500}
//     {"type":"session_reset","ts_ms":1234567890789}
//
// Usage (in NT8 indicator OnMarketDepth / OnBarUpdate):
//   private CaptureHarness _capture;
//   // In OnStateChange State.Configure:
//   _capture = new CaptureHarness(AppDomain.CurrentDomain.BaseDirectory);
//   // In OnMarketDepth:
//   _capture.WriteDepth(side, levelIdx, price, size, priorSize);
//   // In OnBarUpdate (bar close):
//   _capture.WriteBar(bar);
//   // In session reset:
//   _capture.WriteSessionReset();
//
// Thread safety: all writes are synchronized on a per-instance lock.
//   Designed for single-indicator use; not intended for concurrent writers.
//
// File lifecycle:
//   New file per calendar day (date is the indicator's first bar date).
//   File is flushed and closed on Dispose or when the session resets on a new date.
//
// Note: This file is NT8-facing (references System.IO for file writes).
//   It is NOT compiled into the test project — only in the NT8 indicator assembly.
//   Test-side replay uses CaptureReplayLoader (tests/SessionReplay/).

using System;
using System.IO;
using System.Text;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6
{
    /// <summary>
    /// NDJSON session capture harness. Records depth + bar events for offline parity replay.
    ///
    /// Output: captures/YYYY-MM-DD-session.ndjson (one file per trading date).
    /// Schema documented in file header.
    ///
    /// Parity test tolerance: ±2 signals per type per session (see SessionReplayParityTests).
    /// </summary>
    public sealed class CaptureHarness : IDisposable
    {
        private readonly string _outputDir;
        private StreamWriter _writer;
        private string _currentDate;
        private readonly object _lock = new object();
        private bool _disposed = false;

        /// <summary>
        /// Create a CaptureHarness writing to <paramref name="outputDir"/>/captures/.
        /// Directory is created if it does not exist.
        /// </summary>
        public CaptureHarness(string outputDir)
        {
            _outputDir = Path.Combine(outputDir ?? ".", "captures");
            Directory.CreateDirectory(_outputDir);
        }

        /// <summary>
        /// Write a DOM depth event. Call from indicator OnMarketDepth.
        /// </summary>
        /// <param name="side">0=bid, 1=ask</param>
        /// <param name="levelIdx">Level index 0..39</param>
        /// <param name="price">Price at this DOM level</param>
        /// <param name="size">Current size (0 = cleared)</param>
        /// <param name="priorSize">Size before this update. Null if not tracked.</param>
        public void WriteDepth(int side, int levelIdx, double price, long size, long? priorSize)
        {
            long tsMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            string line = priorSize.HasValue
                ? string.Format(
                    "{{\"type\":\"depth\",\"ts_ms\":{0},\"side\":{1},\"levelIdx\":{2},\"price\":{3},\"size\":{4},\"priorSize\":{5}}}",
                    tsMs, side, levelIdx, price, size, priorSize.Value)
                : string.Format(
                    "{{\"type\":\"depth\",\"ts_ms\":{0},\"side\":{1},\"levelIdx\":{2},\"price\":{3},\"size\":{4}}}",
                    tsMs, side, levelIdx, price, size);
            WriteLine(line);
        }

        /// <summary>
        /// Write a completed bar event. Call from indicator OnBarUpdate at bar close.
        /// </summary>
        public void WriteBar(Registry.FootprintBar bar)
        {
            if (bar == null) return;
            long tsMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            string line = string.Format(
                "{{\"type\":\"bar\",\"ts_ms\":{0},\"open\":{1},\"high\":{2},\"low\":{3},\"close\":{4},\"barDelta\":{5},\"totalVol\":{6},\"cvd\":{7}}}",
                tsMs, bar.Open, bar.High, bar.Low, bar.Close, bar.BarDelta, bar.TotalVol, bar.Cvd);
            WriteLine(line);
        }

        /// <summary>
        /// Write a session reset marker (RTH open / date change). Triggers file rotation.
        /// </summary>
        public void WriteSessionReset()
        {
            long tsMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            string line = string.Format("{{\"type\":\"session_reset\",\"ts_ms\":{0}}}", tsMs);
            WriteLine(line);
            lock (_lock) { CloseFile(); }
        }

        private void WriteLine(string line)
        {
            lock (_lock)
            {
                if (_disposed) return;
                EnsureFile();
                try
                {
                    _writer.WriteLine(line);
                    _writer.Flush();
                }
                catch
                {
                    // File write errors must not propagate to NT8 indicator hot path
                }
            }
        }

        private void EnsureFile()
        {
            string today = DateTime.UtcNow.ToString("yyyy-MM-dd");
            if (_writer != null && _currentDate == today) return;

            CloseFile();
            _currentDate = today;
            string path = Path.Combine(_outputDir, string.Format("{0}-session.ndjson", today));
            _writer = new StreamWriter(path, append: true, encoding: Encoding.UTF8);
        }

        private void CloseFile()
        {
            if (_writer != null)
            {
                try { _writer.Flush(); _writer.Dispose(); }
                catch { }
                _writer = null;
            }
        }

        /// <summary>Flush and close the current capture file.</summary>
        public void Dispose()
        {
            lock (_lock)
            {
                if (_disposed) return;
                _disposed = true;
                CloseFile();
            }
        }
    }
}
