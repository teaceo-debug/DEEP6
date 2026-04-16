// BridgeClient: Connects to the NT8 DataBridgeServer and receives live
// NDJSON market data, feeding it into a NinjaScriptRunner in real-time.
//
// The bridge works across machines (NT8 on Windows, simulator on macOS)
// via TCP on port 9200 (or SSH tunnel for remote).
//
// Usage:
//   dotnet run --project ninjatrader/simulator -- bridge [host:port]
//
// Modes:
//   1. Record mode: saves received data to an NDJSON file for later replay
//   2. Live mode: feeds data directly into NinjaScriptRunner as it arrives
//   3. Both: record + live simultaneously

using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using NinjaTrader.Data;

namespace NinjaScriptSim.Lifecycle
{
    /// <summary>
    /// TCP client that connects to the NT8 DataBridgeServer and receives
    /// NDJSON market data events in real-time.
    /// </summary>
    public sealed class BridgeClient : IDisposable
    {
        private TcpClient _client;
        private StreamReader _reader;
        private volatile bool _running;
        private readonly string _host;
        private readonly int _port;

        // ── Events for live mode ──
        public event Action<TickData> OnTrade;
        public event Action<DepthUpdate> OnDepth;
        public event Action<BarData> OnBar;
        public event Action OnSessionReset;

        // ── Stats ──
        public long TradesReceived { get; private set; }
        public long DepthEventsReceived { get; private set; }
        public long BarsReceived { get; private set; }
        public bool IsConnected => _client?.Connected == true;

        public BridgeClient(string host = "127.0.0.1", int port = 9200)
        {
            _host = host;
            _port = port;
        }

        /// <summary>
        /// Connect to the NT8 DataBridgeServer.
        /// </summary>
        public void Connect()
        {
            _client = new TcpClient();
            _client.Connect(_host, _port);
            _client.NoDelay = true;
            _reader = new StreamReader(_client.GetStream(), Encoding.UTF8);
            _running = true;
        }

        /// <summary>
        /// Record incoming data to an NDJSON file. Blocks until disconnected or cancelled.
        /// </summary>
        public void RecordTo(string outputPath, CancellationToken ct = default)
        {
            using var writer = new StreamWriter(outputPath, append: false, Encoding.UTF8);
            writer.AutoFlush = true;

            while (_running && !ct.IsCancellationRequested)
            {
                string line = _reader.ReadLine();
                if (line == null) { _running = false; break; }

                writer.WriteLine(line);
                ProcessLine(line);
            }
        }

        /// <summary>
        /// Process incoming data in live mode (fire events). Blocks until disconnected.
        /// </summary>
        public void StreamLive(CancellationToken ct = default)
        {
            while (_running && !ct.IsCancellationRequested)
            {
                string line = _reader.ReadLine();
                if (line == null) { _running = false; break; }

                ProcessLine(line);
            }
        }

        /// <summary>
        /// Record AND stream live simultaneously.
        /// </summary>
        public void RecordAndStream(string outputPath, CancellationToken ct = default)
        {
            using var writer = new StreamWriter(outputPath, append: false, Encoding.UTF8);
            writer.AutoFlush = true;

            while (_running && !ct.IsCancellationRequested)
            {
                string line = _reader.ReadLine();
                if (line == null) { _running = false; break; }

                writer.WriteLine(line);
                ProcessLine(line);
            }
        }

        private void ProcessLine(string line)
        {
            if (string.IsNullOrWhiteSpace(line)) return;

            // Quick type extraction without full JSON parse
            int typeStart = line.IndexOf("\"type\":\"", StringComparison.Ordinal);
            if (typeStart < 0) return;
            typeStart += 8;
            int typeEnd = line.IndexOf('"', typeStart);
            if (typeEnd < 0) return;
            string type = line.Substring(typeStart, typeEnd - typeStart);

            switch (type)
            {
                case "trade":
                    TradesReceived++;
                    if (OnTrade != null)
                    {
                        OnTrade(new TickData
                        {
                            Price = ExtractDouble(line, "price"),
                            Size = ExtractLong(line, "size"),
                            Aggressor = ExtractInt(line, "aggressor"),
                            Time = MsToDateTime(ExtractLong(line, "ts_ms")),
                        });
                    }
                    break;

                case "depth":
                    DepthEventsReceived++;
                    if (OnDepth != null)
                    {
                        int side = ExtractInt(line, "side");
                        long size = ExtractLong(line, "size");
                        OnDepth(new DepthUpdate
                        {
                            Side = side == 0 ? MarketDataType.Bid : MarketDataType.Ask,
                            Operation = size == 0 ? Operation.Remove : Operation.Update,
                            Position = ExtractInt(line, "levelIdx"),
                            Price = ExtractDouble(line, "price"),
                            Volume = size,
                            Time = MsToDateTime(ExtractLong(line, "ts_ms")),
                        });
                    }
                    break;

                case "bar":
                    BarsReceived++;
                    if (OnBar != null)
                    {
                        OnBar(new BarData
                        {
                            Open = ExtractDouble(line, "open"),
                            High = ExtractDouble(line, "high"),
                            Low = ExtractDouble(line, "low"),
                            Close = ExtractDouble(line, "close"),
                            Volume = ExtractLong(line, "totalVol"),
                            Time = MsToDateTime(ExtractLong(line, "ts_ms")),
                        });
                    }
                    break;

                case "session_reset":
                    OnSessionReset?.Invoke();
                    break;
            }
        }

        public void Dispose()
        {
            _running = false;
            try { _reader?.Dispose(); } catch { }
            try { _client?.Close(); } catch { }
        }

        // ── Minimal JSON extractors ──

        private static DateTime MsToDateTime(long ms)
            => ms > 0 ? DateTimeOffset.FromUnixTimeMilliseconds(ms).UtcDateTime : DateTime.UtcNow;

        private static double ExtractDouble(string json, string key)
        {
            string s = ExtractValue(json, key);
            return double.TryParse(s, System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out double v) ? v : 0.0;
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
