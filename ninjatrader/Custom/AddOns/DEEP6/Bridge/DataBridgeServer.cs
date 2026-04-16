// DataBridgeServer: NT8 AddOn that forwards OnMarketData/OnMarketDepth events
// over a local WebSocket to the NinjaScript Simulator running on macOS.
//
// This runs INSIDE NinjaTrader 8 (Windows). It opens a local TCP listener
// and writes NDJSON lines for every tick, depth update, and bar close.
//
// Install: copy to %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\AddOns\DEEP6\Bridge\
// then F5 in the NinjaScript Editor.
//
// The simulator connects as a TCP client and receives the same NDJSON format
// that CaptureHarness produces — seamless integration.
//
// Configuration: attach to any NQ chart. The bridge starts automatically
// when State == DataLoaded and stops on Terminated.
//
// Network: listens on 127.0.0.1:9200 by default (configurable).
// Cross-machine: if NT8 runs on Windows and simulator on macOS, change
// the bind address or use SSH port forwarding.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge
{
    /// <summary>
    /// TCP server that streams NDJSON market data events to connected clients.
    /// Designed to run as a singleton — only one instance per NT8 session.
    /// Thread-safe: the NT8 data thread calls Write*() methods; the server
    /// thread handles client connections and sends.
    /// </summary>
    public sealed class DataBridgeServer : IDisposable
    {
        private TcpListener _listener;
        private readonly List<TcpClient> _clients = new();
        private readonly object _lock = new();
        private Thread _acceptThread;
        private volatile bool _running;
        private readonly int _port;

        public int Port => _port;
        public int ClientCount { get { lock (_lock) return _clients.Count; } }

        public DataBridgeServer(int port = 9200)
        {
            _port = port;
        }

        public void Start()
        {
            if (_running) return;
            _running = true;
            _listener = new TcpListener(IPAddress.Loopback, _port);
            _listener.Start();
            _acceptThread = new Thread(AcceptLoop) { IsBackground = true, Name = "DEEP6-Bridge-Accept" };
            _acceptThread.Start();
        }

        public void Stop()
        {
            _running = false;
            try { _listener?.Stop(); } catch { }
            lock (_lock)
            {
                foreach (var c in _clients)
                    try { c.Close(); } catch { }
                _clients.Clear();
            }
        }

        public void Dispose() => Stop();

        private void AcceptLoop()
        {
            while (_running)
            {
                try
                {
                    var client = _listener.AcceptTcpClient();
                    client.NoDelay = true;
                    lock (_lock) _clients.Add(client);
                    // Send session_reset to new client
                    SendLine(client, "{\"type\":\"session_reset\",\"ts_ms\":" +
                        DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + "}");
                }
                catch (SocketException) when (!_running) { break; }
                catch { Thread.Sleep(100); }
            }
        }

        // ── Event writers (called from NT8 data thread) ──

        public void WriteTrade(double price, long size, int aggressor)
        {
            long tsMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            string line = string.Format(CultureInfo.InvariantCulture,
                "{{\"type\":\"trade\",\"ts_ms\":{0},\"price\":{1},\"size\":{2},\"aggressor\":{3}}}",
                tsMs, price, size, aggressor);
            Broadcast(line);
        }

        public void WriteDepth(int side, int levelIdx, double price, long size)
        {
            long tsMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            string line = string.Format(CultureInfo.InvariantCulture,
                "{{\"type\":\"depth\",\"ts_ms\":{0},\"side\":{1},\"levelIdx\":{2},\"price\":{3},\"size\":{4}}}",
                tsMs, side, levelIdx, price, size);
            Broadcast(line);
        }

        public void WriteBar(double open, double high, double low, double close,
            long barDelta, long totalVol, long cvd)
        {
            long tsMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            string line = string.Format(CultureInfo.InvariantCulture,
                "{{\"type\":\"bar\",\"ts_ms\":{0},\"open\":{1},\"high\":{2},\"low\":{3},\"close\":{4},\"barDelta\":{5},\"totalVol\":{6},\"cvd\":{7}}}",
                tsMs, open, high, low, close, barDelta, totalVol, cvd);
            Broadcast(line);
        }

        public void WriteSessionReset()
        {
            long tsMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            Broadcast("{\"type\":\"session_reset\",\"ts_ms\":" + tsMs + "}");
        }

        // ── Internal ──

        private void Broadcast(string line)
        {
            byte[] data = Encoding.UTF8.GetBytes(line + "\n");
            lock (_lock)
            {
                for (int i = _clients.Count - 1; i >= 0; i--)
                {
                    try
                    {
                        _clients[i].GetStream().Write(data, 0, data.Length);
                    }
                    catch
                    {
                        // Client disconnected — remove
                        try { _clients[i].Close(); } catch { }
                        _clients.RemoveAt(i);
                    }
                }
            }
        }

        private void SendLine(TcpClient client, string line)
        {
            try
            {
                byte[] data = Encoding.UTF8.GetBytes(line + "\n");
                client.GetStream().Write(data, 0, data.Length);
            }
            catch { }
        }
    }
}
