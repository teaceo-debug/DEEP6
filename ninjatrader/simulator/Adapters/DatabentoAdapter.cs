// DatabentoAdapter: Converts Databento MBO/OHLCV data into the NDJSON session
// format consumed by NdjsonSessionLoader → NinjaScriptRunner.
//
// Databento delivers data as binary DBN files or CSV exports. This adapter
// handles both formats and produces the same NDJSON that CaptureHarness writes.
//
// Supported inputs:
//   1. Databento CSV export (trades + depth, from databento.com dashboard)
//   2. Databento DBN binary files (via `databento` Python SDK → CSV pre-export)
//   3. Databento OHLCV-1m bars (simpler, no tick data)
//
// Usage:
//   // From CSV trades file:
//   DatabentoAdapter.ConvertTradesToNdjson("NQ_trades.csv", "session.ndjson");
//
//   // From OHLCV bars:
//   DatabentoAdapter.ConvertOhlcvToNdjson("NQ_ohlcv_1m.csv", "session.ndjson");
//
//   // Direct to runner (no intermediate file):
//   var session = DatabentoAdapter.LoadOhlcvCsv("NQ_ohlcv_1m.csv");
//   runner.LoadBars(session.Bars);
//   runner.Run<DEEP6Strategy>();

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using NinjaTrader.Data;

namespace NinjaScriptSim.Lifecycle
{
    /// <summary>
    /// Converts Databento data files into the simulator's NDJSON session format
    /// or directly into SessionData for the NinjaScriptRunner.
    /// </summary>
    public static class DatabentoAdapter
    {
        // ── Databento MBO trades CSV → NDJSON ────────────────────────────────

        /// <summary>
        /// Convert a Databento MBO trades CSV to NDJSON session file.
        ///
        /// Expected CSV columns (Databento MBO schema):
        ///   ts_event,rtype,publisher_id,instrument_id,action,side,price,size,
        ///   channel_id,order_id,flags,ts_recv,ts_in_delta,sequence
        ///
        /// The 'action' field: T=Trade, A=Add, C=Cancel, M=Modify
        /// The 'side' field: A=Ask, B=Bid, N=None
        /// </summary>
        public static void ConvertMboToNdjson(string csvPath, string outputPath,
            double tickSize = 0.25, int barPeriodSeconds = 60)
        {
            using var writer = new StreamWriter(outputPath);
            writer.WriteLine("{\"type\":\"session_reset\",\"ts_ms\":0}");

            var lines = File.ReadAllLines(csvPath);
            if (lines.Length < 2) return;

            // Parse header
            string[] headers = lines[0].Split(',');
            int iTs = Array.IndexOf(headers, "ts_event");
            int iAction = Array.IndexOf(headers, "action");
            int iSide = Array.IndexOf(headers, "side");
            int iPrice = Array.IndexOf(headers, "price");
            int iSize = Array.IndexOf(headers, "size");

            if (iTs < 0 || iPrice < 0 || iSize < 0)
            {
                // Try alternate header names
                iTs = iTs < 0 ? Array.IndexOf(headers, "ts_recv") : iTs;
                iPrice = iPrice < 0 ? Array.IndexOf(headers, "px") : iPrice;
                iSize = iSize < 0 ? Array.IndexOf(headers, "qty") : iSize;
            }

            if (iTs < 0 || iPrice < 0 || iSize < 0)
                throw new FormatException($"Cannot find required columns in {csvPath}. Found: {lines[0]}");

            // Accumulate into bars
            var currentBar = new BarAccumulator();
            long barBoundary = 0;
            int levelIdx = 0;

            for (int i = 1; i < lines.Length; i++)
            {
                string[] cols = lines[i].Split(',');
                if (cols.Length <= System.Math.Max(iTs, System.Math.Max(iPrice, iSize))) continue;

                long tsNano = long.TryParse(cols[iTs], out long tn) ? tn : 0;
                long tsMs = tsNano / 1_000_000; // nanoseconds → milliseconds
                double price = double.TryParse(cols[iPrice], NumberStyles.Float, CultureInfo.InvariantCulture, out double p) ? p : 0;
                long size = long.TryParse(cols[iSize], out long s) ? s : 0;

                // Databento prices may be in fixed-point (divide by 1e9)
                if (price > 1_000_000_000) price /= 1_000_000_000.0;

                string action = iAction >= 0 && iAction < cols.Length ? cols[iAction].Trim() : "T";
                string side = iSide >= 0 && iSide < cols.Length ? cols[iSide].Trim() : "N";

                if (action == "T" || action == "F") // Trade or Fill
                {
                    // Determine aggressor: Ask-side trade = buy aggressor, Bid-side = sell
                    int aggressor = side == "A" ? 1 : side == "B" ? 2 : 0;

                    // Write trade event
                    writer.WriteLine($"{{\"type\":\"trade\",\"ts_ms\":{tsMs},\"price\":{price.ToString(CultureInfo.InvariantCulture)},\"size\":{size},\"aggressor\":{aggressor}}}");

                    // Accumulate into current bar
                    if (barBoundary == 0) barBoundary = tsMs + barPeriodSeconds * 1000;

                    currentBar.AddTrade(price, size, aggressor);

                    // Bar boundary check
                    if (tsMs >= barBoundary)
                    {
                        currentBar.Finalize();
                        writer.WriteLine(currentBar.ToNdjson(barBoundary));
                        currentBar = new BarAccumulator();
                        barBoundary += barPeriodSeconds * 1000;
                    }
                }
                else if (action == "A" || action == "M" || action == "C") // Add/Modify/Cancel (depth)
                {
                    long depthSize = action == "C" ? 0 : size;
                    int depthSide = side == "B" ? 0 : 1;
                    writer.WriteLine($"{{\"type\":\"depth\",\"ts_ms\":{tsMs},\"side\":{depthSide},\"levelIdx\":{levelIdx % 10},\"price\":{price.ToString(CultureInfo.InvariantCulture)},\"size\":{depthSize}}}");
                    levelIdx++;
                }
            }

            // Flush last bar
            if (currentBar.TradeCount > 0)
            {
                currentBar.Finalize();
                writer.WriteLine(currentBar.ToNdjson(barBoundary));
            }
        }

        // ── Databento OHLCV-1m CSV → SessionData (direct load) ──────────────

        /// <summary>
        /// Load a Databento OHLCV-1m CSV directly into SessionData.
        ///
        /// Expected CSV columns (Databento ohlcv-1m schema):
        ///   ts_event,rtype,publisher_id,instrument_id,open,high,low,close,volume
        ///
        /// Synthesizes ticks from OHLC since MBO tick data isn't available in this schema.
        /// </summary>
        public static SessionData LoadOhlcvCsv(string csvPath)
        {
            var session = new SessionData();
            var lines = File.ReadAllLines(csvPath);
            if (lines.Length < 2) return session;

            string[] headers = lines[0].Split(',');
            int iTs = FindColumn(headers, "ts_event", "ts_recv", "timestamp");
            int iOpen = FindColumn(headers, "open", "px_open");
            int iHigh = FindColumn(headers, "high", "px_high");
            int iLow = FindColumn(headers, "low", "px_low");
            int iClose = FindColumn(headers, "close", "px_close");
            int iVol = FindColumn(headers, "volume", "vol", "size");

            if (iOpen < 0 || iHigh < 0 || iLow < 0 || iClose < 0)
                throw new FormatException($"Cannot find OHLC columns in {csvPath}. Found: {lines[0]}");

            for (int i = 1; i < lines.Length; i++)
            {
                string[] cols = lines[i].Split(',');
                if (cols.Length <= System.Math.Max(iClose, iVol)) continue;

                double open = ParseDouble(cols[iOpen]);
                double high = ParseDouble(cols[iHigh]);
                double low = ParseDouble(cols[iLow]);
                double close = ParseDouble(cols[iClose]);
                long volume = iVol >= 0 ? ParseLong(cols[iVol]) : 0;

                // Databento fixed-point prices (1e9 scaling)
                if (open > 1_000_000_000) { open /= 1e9; high /= 1e9; low /= 1e9; close /= 1e9; }

                DateTime time = DateTime.UtcNow;
                if (iTs >= 0 && iTs < cols.Length)
                {
                    long tsNano = ParseLong(cols[iTs]);
                    if (tsNano > 1_000_000_000_000L) // nanosecond timestamp
                        time = DateTimeOffset.FromUnixTimeMilliseconds(tsNano / 1_000_000).UtcDateTime;
                    else if (tsNano > 1_000_000_000L) // second timestamp
                        time = DateTimeOffset.FromUnixTimeSeconds(tsNano).UtcDateTime;
                    else if (DateTime.TryParse(cols[iTs], CultureInfo.InvariantCulture,
                        DateTimeStyles.AssumeUniversal, out DateTime parsed))
                        time = parsed;
                }

                session.Bars.Add(new BarData
                {
                    Open = open, High = high, Low = low, Close = close,
                    Volume = volume, Time = time,
                });
            }

            return session;
        }

        /// <summary>
        /// Convert Databento OHLCV CSV to NDJSON session file.
        /// </summary>
        public static void ConvertOhlcvToNdjson(string csvPath, string outputPath)
        {
            var session = LoadOhlcvCsv(csvPath);
            using var writer = new StreamWriter(outputPath);
            writer.WriteLine("{\"type\":\"session_reset\",\"ts_ms\":0}");

            foreach (var bar in session.Bars)
            {
                long tsMs = new DateTimeOffset(bar.Time).ToUnixTimeMilliseconds();
                writer.WriteLine(string.Format(CultureInfo.InvariantCulture,
                    "{{\"type\":\"bar\",\"ts_ms\":{0},\"open\":{1},\"high\":{2},\"low\":{3},\"close\":{4},\"barDelta\":0,\"totalVol\":{5}}}",
                    tsMs, bar.Open, bar.High, bar.Low, bar.Close, bar.Volume));
            }
        }

        // ── Helpers ──────────────────────────────────────────────────────────

        private static int FindColumn(string[] headers, params string[] candidates)
        {
            foreach (var c in candidates)
            {
                int idx = Array.FindIndex(headers, h => h.Trim().Equals(c, StringComparison.OrdinalIgnoreCase));
                if (idx >= 0) return idx;
            }
            return -1;
        }

        private static double ParseDouble(string s)
        {
            return double.TryParse(s?.Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out double v) ? v : 0.0;
        }

        private static long ParseLong(string s)
        {
            return long.TryParse(s?.Trim(), out long v) ? v : 0L;
        }

        /// <summary>Accumulates trades into a bar for MBO → NDJSON conversion.</summary>
        private class BarAccumulator
        {
            public double Open, High, Low, Close;
            public long TotalVol, BuyVol, SellVol;
            public int TradeCount;

            public void AddTrade(double price, long size, int aggressor)
            {
                if (TradeCount == 0) { Open = price; High = price; Low = price; }
                if (price > High) High = price;
                if (price < Low) Low = price;
                Close = price;
                TotalVol += size;
                if (aggressor == 1) BuyVol += size;
                else if (aggressor == 2) SellVol += size;
                TradeCount++;
            }

            public void Finalize() { /* nothing extra needed */ }

            public string ToNdjson(long tsMs)
            {
                long delta = BuyVol - SellVol;
                return string.Format(CultureInfo.InvariantCulture,
                    "{{\"type\":\"bar\",\"ts_ms\":{0},\"open\":{1},\"high\":{2},\"low\":{3},\"close\":{4},\"barDelta\":{5},\"totalVol\":{6}}}",
                    tsMs, Open, High, Low, Close, delta, TotalVol);
            }
        }
    }
}
