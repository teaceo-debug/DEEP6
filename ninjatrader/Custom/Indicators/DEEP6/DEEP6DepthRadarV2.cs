// DEEP6 DepthRadar V2 — intelligent wall classification upgrade of v1.
//
// v2 starts from the exact DEEP6DepthRadar v1 rendering and DOM intake base,
// then layers in the future wall-classification pipeline:
//   - Wall classification (GENUINE / SPOOF / ICEBERG / STALE)
//   - Spoof detection and contextual scoring hooks
//   - Freshness scoring for aging liquidity
//
// Current scope for this fork:
//   - Preserve v1 wall rendering, glow, labels, and DOM ingestion intact
//   - Keep the same standalone indicator structure and L2 level state model
//   - Serve as the v2 upgrade path for smarter wall interpretation

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = System.Windows.Media.Brush;
using Color = System.Windows.Media.Color;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6DepthRadarV2 : Indicator
    {
        // ---- Per-price dictionaries — written by OnMarketDepth, snapshot-read by OnRender ----
        private readonly Dictionary<double, L2LevelStateV2> _l2Bids = new Dictionary<double, L2LevelStateV2>();
        private readonly Dictionary<double, L2LevelStateV2> _l2Asks = new Dictionary<double, L2LevelStateV2>();
        private readonly object _l2Lock = new object();
        private DateTime _lastL2Prune = DateTime.MinValue;
        private long _depthCallbacks;
        private double _bestBid;
        private double _bestAsk;
        private double _avgWallSize;
        private int _diagPrintCountdown = 5; // one-shot diagnostic: print first 5 render cycles

        // ---- IPC Bridge (Python ML classification service on port 9201) ----
        private DepthRadarBridge _bridge;
        private volatile bool _bridgeConnected;
        private volatile bool _wasBridgeConnected;
        private float _lastIpcLatencyMs;
        private DateTime _jsonLastModified = DateTime.MinValue;
        private Timer _jsonCheckTimer;

        // ---- DX Resources — one brush per wall classification ----
        private SharpDX.Direct2D1.Brush _genuineDx;
        private SharpDX.Direct2D1.Brush _spoofDx;
        private SharpDX.Direct2D1.Brush _icebergDx;
        private SharpDX.Direct2D1.Brush _staleDx;
        // Per-classification glow bloom brushes (3 passes: outer -> inner)
        private SharpDX.Direct2D1.SolidColorBrush[] _glowGenuineDx;
        private SharpDX.Direct2D1.SolidColorBrush[] _glowSpoofDx;
        private SharpDX.Direct2D1.SolidColorBrush[] _glowIcebergDx;
        // Per-classification glow widths (ICEBERG uses wider bloom)
        private static readonly float[] GLOW_WIDTHS_STANDARD = { 14f,  8f,  5f };
        private static readonly float[] GLOW_WIDTHS_ICEBERG  = { 16f, 10f,  6f };
        // HUD
        private SharpDX.Direct2D1.SolidColorBrush _dxHudBg;
        private SharpDX.Direct2D1.SolidColorBrush _dxHudBorder;
        private SharpDX.Direct2D1.SolidColorBrush _dxHudText;
        // Fonts — same as FootprintV7._labelFont
        private TextFormat _labelFont;
        private TextFormat _hudFont;

        // ---- Invalidation ----
        private Timer _invalidateTimer;
        private int _dirty;
        private const int INVALIDATE_MS = 50;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description         = "Full-spectrum DOM liquidity levels with an intelligent wall classification system. Forked from DEEP6 Depth Radar v1 to preserve the original rendering and DOM intake base while preparing v2 for wall classification, spoof detection, and freshness scoring.";
                Name                = "DEEP6 Depth Radar V2";
                Calculate           = Calculate.OnEachTick;
                IsOverlay           = true;
                DrawOnPricePanel    = true;
                PaintPriceMarkers   = false;
                IsSuspendedWhileInactive = false;
                DisplayInDataBox    = false;
                ScaleJustification  = ScaleJustification.Right;

                // Same defaults as FootprintV7 section "5. Liquidity (L2)"
                WallMinSize         = 10;
                WallStaleSec        = 90;
                MaxDepthLevels      = 40;
                GlowThreshold       = 100;
                StaleCrossTimeoutSec = 30;
                ShowBids            = true;
                ShowAsks            = true;
                ShowLabels          = true;
                EnableML            = true;
                WallsJsonPath       = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Personal),
                                        "NinjaTrader 8", "templates", "DEEP6", "depth_radar_walls.json");

                // Classification-based wall colors
                GenuineBrush        = MakeFrozenBrush(Color.FromArgb(220, 46, 204, 113));   // bright green
                SpoofBrush          = MakeFrozenBrush(Color.FromArgb(220, 231, 76, 60));    // alert red
                IcebergBrush        = MakeFrozenBrush(Color.FromArgb(220, 52, 152, 219));   // deep blue
                StaleBrush          = MakeFrozenBrush(Color.FromArgb(100, 149, 165, 166));  // dim gray
            }
            else if (State == State.DataLoaded)
            {
                ClearBooks();
                Interlocked.Exchange(ref _dirty, 1);
                if (_invalidateTimer == null)
                    _invalidateTimer = new Timer(OnInvalidateTick, null, INVALIDATE_MS, INVALIDATE_MS);
                if (_jsonCheckTimer == null)
                    _jsonCheckTimer = new Timer(OnJsonCheck, null, 2000, 2000);
                Print("[DEEP6DepthRadarV2] DataLoaded — JSON path: " + WallsJsonPath + " exists=" + File.Exists(WallsJsonPath));
            }
            else if (State == State.Historical)
            {
                try { SetZOrder(-1); } catch { }
            }
            else if (State == State.Realtime)
            {
                Print("[DEEP6DepthRadarV2] Realtime — waiting for L2 DOM data from Rithmic");
                if (EnableML)
                {
                    _bridge = new DepthRadarBridge(Print, ProcessInboundClassification);
                    _bridge.Start();
                }
                else
                {
                    Print("[DEEP6DepthRadarV2] ML classification disabled — rule-based only");
                }
            }
            else if (State == State.Terminated)
            {
                if (_bridge != null) { _bridge.Dispose(); _bridge = null; _bridgeConnected = false; }
                if (_invalidateTimer != null) { _invalidateTimer.Dispose(); _invalidateTimer = null; }
                if (_jsonCheckTimer != null) { _jsonCheckTimer.Dispose(); _jsonCheckTimer = null; }
                DisposeDx();
                ClearBooks();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0 || CurrentBar < 0) return;

            if (Bars.IsFirstBarOfSession && IsFirstTickOfBar)
            {
                ClearBooks();
                Interlocked.Exchange(ref _depthCallbacks, 0);
                Interlocked.Exchange(ref _dirty, 1);
            }

            double currentPrice = Close[0];
            DateTime utcNow = DateTime.UtcNow;
            bool changed = false;

            lock (_l2Lock)
            {
                foreach (var kv in _l2Bids)
                {
                    L2LevelStateV2 st = kv.Value;
                    if (st.CurrentSize > 0 && currentPrice < kv.Key && !st.PriceTradedThrough)
                    {
                        st.PriceTradedThrough = true;
                        st.PriceCrossTime = utcNow;
                        changed = true;
                    }
                }

                foreach (var kv in _l2Asks)
                {
                    L2LevelStateV2 st = kv.Value;
                    if (st.CurrentSize > 0 && currentPrice > kv.Key && !st.PriceTradedThrough)
                    {
                        st.PriceTradedThrough = true;
                        st.PriceCrossTime = utcNow;
                        changed = true;
                    }
                }
            }

            if (changed)
                Interlocked.Exchange(ref _dirty, 1);
        }

        // ---- L2 depth intake (same as FootprintV7.OnMarketDepth but full DOM depth) ----

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (e == null) return;
            if (e.MarketDataType != MarketDataType.Bid && e.MarketDataType != MarketDataType.Ask) return;
            if (e.Price <= 0) return;
            if (MaxDepthLevels > 0 && e.Position >= MaxDepthLevels) return;

            Interlocked.Increment(ref _depthCallbacks);

            if (e.Position == 0)
            {
                if (e.MarketDataType == MarketDataType.Bid)
                    _bestBid = e.Price;
                else
                    _bestAsk = e.Price;
            }

            DateTime utcNow = DateTime.UtcNow;
            long newSize = e.Operation == Operation.Remove ? 0 : (long)e.Volume;
            var dict = e.MarketDataType == MarketDataType.Bid ? _l2Bids : _l2Asks;

            lock (_l2Lock)
            {
                L2LevelStateV2 st;
                bool existed = dict.TryGetValue(e.Price, out st);
                if (!existed)
                {
                    st = new L2LevelStateV2();
                    st.FirstSeenTime = utcNow;
                    st.OriginalSize = newSize;
                    dict[e.Price] = st;
                }

                long priorSize = st.CurrentSize;

                // Iceberg detection (same logic as FootprintV7)
                if (st.MaxSize > 0 && st.CurrentSize < st.MaxSize * 0.5 && newSize >= st.MaxSize * 0.5)
                    st.RefillCount++;

                if (existed && newSize > 0 && priorSize != newSize)
                    st.ModificationCount++;

                if (existed && priorSize == 0 && newSize > 0)
                    st.CancellationEvents++;

                float cancelRatio = st.CancellationEvents / (float)(st.CancellationEvents + 1);
                _ = cancelRatio;

                st.CurrentSize = newSize;
                if (newSize > st.MaxSize) st.MaxSize = newSize;
                st.LastUpdate = utcNow;

                // Inline classification: new/updated walls get classified immediately
                // so they render between 30s ScoreAllWalls cycles.
                // Full scoring (spoof, freshness, iceberg) is refined during periodic prune.
                if (!st.IsMLClassified && st.Classification == WallClassification.Unknown && st.MaxSize >= WallMinSize)
                    DepthRadarV2Logic.ClassifyWall(st, WallMinSize, utcNow);

                // Periodic prune (same 30s cadence as FootprintV7)
                if ((utcNow - _lastL2Prune).TotalSeconds > 30)
                {
                    PruneL2(_l2Bids);
                    PruneL2(_l2Asks);
                    ScoreAllWalls();
                    _lastL2Prune = utcNow;
                }
            }

            Interlocked.Exchange(ref _dirty, 1);
        }

        private void PruneL2(Dictionary<double, L2LevelStateV2> dict)
        {
            var cutoff = DateTime.UtcNow.AddSeconds(-Math.Max(WallStaleSec * 3, 300));
            var stale = new List<double>();
            foreach (var kv in dict)
                if (kv.Value.LastUpdate < cutoff) stale.Add(kv.Key);
            foreach (var k in stale) dict.Remove(k);
        }

        private void ScoreAllWalls()
        {
            double totalWallSize = 0.0;
            int wallCount = 0;

            foreach (var kv in _l2Bids)
            {
                if (kv.Value.MaxSize < WallMinSize) continue;
                totalWallSize += kv.Value.MaxSize;
                wallCount++;
            }

            foreach (var kv in _l2Asks)
            {
                if (kv.Value.MaxSize < WallMinSize) continue;
                totalWallSize += kv.Value.MaxSize;
                wallCount++;
            }

            _avgWallSize = wallCount > 0 ? totalWallSize / wallCount : 0.0;

            double tickSize = TickSize;
            if (tickSize <= 0)
                tickSize = 1.0;

            DateTime utcNow = DateTime.UtcNow;

            foreach (var kv in _l2Bids)
            {
                double ticksFromBbo = 0.0;
                if (_bestBid > 0)
                    ticksFromBbo = (_bestBid - kv.Key) / tickSize;
                kv.Value.SpoofScore = DepthRadarV2Logic.ComputeSpoofScore(kv.Value, _avgWallSize, ticksFromBbo, utcNow);
                kv.Value.FreshnessScore = DepthRadarV2Logic.ComputeFreshnessScore(kv.Value, ticksFromBbo, utcNow);
                DepthRadarV2Logic.ClassifyWall(kv.Value, WallMinSize, utcNow);
            }

            foreach (var kv in _l2Asks)
            {
                double ticksFromBbo = 0.0;
                if (_bestAsk > 0)
                    ticksFromBbo = (kv.Key - _bestAsk) / tickSize;
                kv.Value.SpoofScore = DepthRadarV2Logic.ComputeSpoofScore(kv.Value, _avgWallSize, ticksFromBbo, utcNow);
                kv.Value.FreshnessScore = DepthRadarV2Logic.ComputeFreshnessScore(kv.Value, ticksFromBbo, utcNow);
                DepthRadarV2Logic.ClassifyWall(kv.Value, WallMinSize, utcNow);
            }

            // Detect disconnect/reconnect transitions
            bool connected = _bridgeConnected;
            bool wasConnected = _wasBridgeConnected;

            if (wasConnected && !connected)
            {
                Print("[DEEP6DepthRadarV2] ML service disconnected — reverting to rule-based");
                RevertToRuleBased();
            }
            else if (!wasConnected && connected)
            {
                Print("[DEEP6DepthRadarV2] ML service reconnected");
            }

            _wasBridgeConnected = connected;

            SendWallSnapshots();
        }

        /// <summary>
        /// Clears IsMLClassified on all walls so the next ClassifyWall() call uses rule-based logic.
        /// Must be called under _l2Lock (caller already holds lock via ScoreAllWalls path).
        /// </summary>
        private void RevertToRuleBased()
        {
            foreach (var kv in _l2Bids)
                kv.Value.IsMLClassified = false;
            foreach (var kv in _l2Asks)
                kv.Value.IsMLClassified = false;
        }

        // ---- IPC Bridge: outbound wall snapshots ----

        private void SendWallSnapshots()
        {
            if (!EnableML) return;
            var bridge = _bridge;
            if (bridge == null || !bridge.IsConnected) return;

            DateTime utcNow = DateTime.UtcNow;
            double tickSize = TickSize;
            if (tickSize <= 0) tickSize = 1.0;

            foreach (var kv in _l2Bids)
            {
                if (kv.Value.MaxSize < WallMinSize) continue;
                double distFromBbo = (_bestBid > 0) ? (_bestBid - kv.Key) / tickSize : 0.0;
                string line = FormatWallSnapshot(kv.Key, "bid", kv.Value, distFromBbo, utcNow);
                if (!bridge.SendLine(line)) return;
            }

            foreach (var kv in _l2Asks)
            {
                if (kv.Value.MaxSize < WallMinSize) continue;
                double distFromBbo = (_bestAsk > 0) ? (kv.Key - _bestAsk) / tickSize : 0.0;
                string line = FormatWallSnapshot(kv.Key, "ask", kv.Value, distFromBbo, utcNow);
                if (!bridge.SendLine(line)) return;
            }

            _bridgeConnected = bridge.IsConnected;
        }

        private static string FormatWallSnapshot(double price, string side, L2LevelStateV2 st, double distFromBbo, DateTime utcNow)
        {
            double timeInBook = (utcNow - st.FirstSeenTime).TotalSeconds;
            return string.Format(CultureInfo.InvariantCulture,
                "{{\"type\":\"wall_snapshot\",\"price\":{0},\"side\":\"{1}\",\"current_size\":{2},\"max_size\":{3}," +
                "\"time_in_book\":{4:F1},\"modification_count\":{5},\"cancellation_count\":{6}," +
                "\"original_size\":{7},\"refill_count\":{8},\"spoof_score\":{9:F1},\"freshness_score\":{10:F2}," +
                "\"price_crossed\":{11},\"distance_from_bbo\":{12:F1}}}",
                price, side, st.CurrentSize, st.MaxSize,
                timeInBook, st.ModificationCount, st.CancellationEvents,
                st.OriginalSize, st.RefillCount, st.SpoofScore, st.FreshnessScore,
                st.PriceTradedThrough ? "true" : "false", distFromBbo);
        }

        // ---- IPC Bridge: inbound classification processing ----

        private void ProcessInboundClassification(string json)
        {
            if (string.IsNullOrEmpty(json)) return;

            string msgType = ParseJsonString(json, "type");

            if (msgType == "wall_classification")
            {
                double price = ParseJsonDouble(json, "price");
                string side = ParseJsonString(json, "side");
                string classification = ParseJsonString(json, "classification");
                float confidence = (float)ParseJsonDouble(json, "confidence");

                WallClassification cls;
                switch (classification)
                {
                    case "GENUINE": cls = WallClassification.Genuine; break;
                    case "SPOOF":   cls = WallClassification.Spoof;   break;
                    case "ICEBERG": cls = WallClassification.Iceberg; break;
                    case "STALE":   cls = WallClassification.Stale;   break;
                    default: return;
                }

                var dict = (side == "ask") ? _l2Asks : _l2Bids;
                lock (_l2Lock)
                {
                    L2LevelStateV2 st;
                    if (dict.TryGetValue(price, out st))
                    {
                        st.Classification = cls;
                        st.Confidence = confidence;
                        st.IsMLClassified = true;
                        st.LastClassificationTime = DateTime.UtcNow;
                    }
                }

                _bridgeConnected = true;
                Interlocked.Exchange(ref _dirty, 1);
            }
            else if (msgType == "heartbeat_ack")
            {
                long sentMs = (long)ParseJsonDouble(json, "echo_timestamp");
                long nowMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                if (sentMs > 0)
                    _lastIpcLatencyMs = (float)(nowMs - sentMs);
                _bridgeConnected = true;
            }
        }

        // Lightweight JSON string field extractor for known fixed-schema messages.
        // No JSON library dependency — .NET Framework 4.8 has no System.Text.Json.
        private static string ParseJsonString(string json, string key)
        {
            string needle = "\"" + key + "\":\"";
            int idx = json.IndexOf(needle, StringComparison.Ordinal);
            if (idx < 0) return null;
            int start = idx + needle.Length;
            int end = json.IndexOf('"', start);
            if (end < 0) return null;
            return json.Substring(start, end - start);
        }

        // Lightweight JSON numeric field extractor for known fixed-schema messages.
        private static double ParseJsonDouble(string json, string key)
        {
            string needle = "\"" + key + "\":";
            int idx = json.IndexOf(needle, StringComparison.Ordinal);
            if (idx < 0) return 0.0;
            int start = idx + needle.Length;
            while (start < json.Length && json[start] == ' ') start++;
            int end = start;
            while (end < json.Length && (char.IsDigit(json[end]) || json[end] == '.' || json[end] == '-' || json[end] == 'e' || json[end] == 'E' || json[end] == '+'))
                end++;
            if (end == start) return 0.0;
            double result;
            if (double.TryParse(json.Substring(start, end - start), NumberStyles.Float, CultureInfo.InvariantCulture, out result))
                return result;
            return 0.0;
        }

        private void OnJsonCheck(object state)
        {
            try
            {
                if (ReadWallsFromJson())
                    Interlocked.Exchange(ref _dirty, 1);
            }
            catch (Exception ex)
            {
                Print("[DEEP6DepthRadarV2] JSON wall read failed: " + ex.Message);
            }
        }

        private bool ReadWallsFromJson()
        {
            if (string.IsNullOrWhiteSpace(WallsJsonPath) || !File.Exists(WallsJsonPath))
            {
                Print("[DEEP6DepthRadarV2] JSON not found: " + (WallsJsonPath ?? "null"));
                return false;
            }

            var fi = new FileInfo(WallsJsonPath);
            if (fi.LastWriteTimeUtc <= _jsonLastModified)
                return false;

            string json = File.ReadAllText(WallsJsonPath);
            _jsonLastModified = fi.LastWriteTimeUtc;

            int wallsIdx = json.IndexOf("\"walls\"", StringComparison.Ordinal);
            if (wallsIdx < 0)
                return false;
            int arrStart = json.IndexOf('[', wallsIdx);
            if (arrStart < 0)
                return false;

            DateTime utcNow = DateTime.UtcNow;
            bool updated = false;
            int i = arrStart + 1;
            int n = json.Length;

            lock (_l2Lock)
            {
                while (i < n)
                {
                    while (i < n && json[i] != '{' && json[i] != ']') i++;
                    if (i >= n || json[i] == ']') break;

                    int objStart = i;
                    int depth = 0;
                    bool inString = false;
                    bool escape = false;
                    for (; i < n; i++)
                    {
                        char c = json[i];
                        if (escape) { escape = false; continue; }
                        if (inString)
                        {
                            if (c == '\\') escape = true;
                            else if (c == '"') inString = false;
                            continue;
                        }

                        if (c == '"') { inString = true; continue; }
                        if (c == '{') depth++;
                        else if (c == '}')
                        {
                            depth--;
                            if (depth == 0) { i++; break; }
                        }
                    }

                    string item = json.Substring(objStart, i - objStart);
                    double price = ParseJsonDouble(item, "price");
                    string side = ParseJsonString(item, "side");
                    string classification = ParseJsonString(item, "classification");
                    double confidenceValue = ParseJsonDouble(item, "confidence");
                    long size = (long)Math.Round(ParseJsonDouble(item, "size"));
                    long maxSize = (long)Math.Round(ParseJsonDouble(item, "max_size"));
                    int refillCount = (int)Math.Round(ParseJsonDouble(item, "refill_count"));
                    double durationSec = ParseJsonDouble(item, "duration_sec");

                    if (price <= 0 || string.IsNullOrEmpty(side))
                        continue;

                    WallClassification cls;
                    switch (classification)
                    {
                        case "GENUINE": cls = WallClassification.Genuine; break;
                        case "SPOOF": cls = WallClassification.Spoof; break;
                        case "ICEBERG": cls = WallClassification.Iceberg; break;
                        case "STALE": cls = WallClassification.Stale; break;
                        default: cls = WallClassification.Unknown; break;
                    }

                    var dict = string.Equals(side, "ask", StringComparison.OrdinalIgnoreCase) ? _l2Asks : _l2Bids;
                    L2LevelStateV2 st;
                    if (!dict.TryGetValue(price, out st))
                    {
                        st = new L2LevelStateV2();
                        dict[price] = st;
                    }

                    if (st.FirstSeenTime == default(DateTime))
                        st.FirstSeenTime = utcNow.AddSeconds(-Math.Max(0.0, durationSec));
                    st.OriginalSize = st.OriginalSize > 0 ? st.OriginalSize : Math.Max(size, maxSize);
                    st.CurrentSize = size;
                    st.MaxSize = Math.Max(st.MaxSize, maxSize);
                    st.RefillCount = Math.Max(st.RefillCount, refillCount);
                    st.Classification = cls;
                    st.Confidence = (float)Math.Max(0.0, Math.Min(1.0, confidenceValue));
                    st.IsMLClassified = true;
                    st.LastClassificationTime = utcNow;
                    st.LastUpdate = utcNow;
                    st.InteractionPrediction = ParseJsonString(item, "interaction");
                    double intConf = ParseJsonDouble(item, "interaction_confidence");
                    st.InteractionConfidence = (float)(intConf > 0 ? intConf : 0);
                    if (cls == WallClassification.Stale)
                    {
                        st.PriceTradedThrough = true;
                        if (st.PriceCrossTime == default(DateTime))
                            st.PriceCrossTime = utcNow;
                    }

                    updated = true;
                }
            }

            if (updated)
                Print("[DEEP6DepthRadarV2] JSON loaded " + _l2Bids.Count + " bids + " + _l2Asks.Count + " asks from " + WallsJsonPath);
            return updated;
        }

        // ---- Invalidation timer ----

        private void OnInvalidateTick(object state)
        {
            if (Interlocked.CompareExchange(ref _dirty, 0, 0) != 1) return;
            try
            {
                if (ChartControl != null)
                    ChartControl.Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (ChartControl != null) ChartControl.InvalidateVisual();
                    }));
            }
            catch { }
        }

        // ---- DX Resource Management ----

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            // Classification brushes
            _genuineDx = GenuineBrush.ToDxBrush(RenderTarget);
            _spoofDx   = SpoofBrush.ToDxBrush(RenderTarget);
            _icebergDx = IcebergBrush.ToDxBrush(RenderTarget);
            _staleDx   = StaleBrush.ToDxBrush(RenderTarget);

            // Per-classification glow bloom brushes
            Color genuineC = ExtractColor(GenuineBrush, Color.FromArgb(220, 46, 204, 113));
            Color spoofC   = ExtractColor(SpoofBrush,   Color.FromArgb(220, 231, 76, 60));
            Color icebergC = ExtractColor(IcebergBrush,  Color.FromArgb(220, 52, 152, 219));

            float[] genuineAlphas = { 0.08f, 0.18f, 0.35f };
            float[] spoofAlphas   = { 0.15f, 0.30f, 0.50f };
            float[] icebergAlphas = { 0.08f, 0.18f, 0.35f };

            _glowGenuineDx = new SharpDX.Direct2D1.SolidColorBrush[3];
            _glowSpoofDx   = new SharpDX.Direct2D1.SolidColorBrush[3];
            _glowIcebergDx = new SharpDX.Direct2D1.SolidColorBrush[3];
            for (int g = 0; g < 3; g++)
            {
                _glowGenuineDx[g] = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                    new Color4(genuineC.R / 255f, genuineC.G / 255f, genuineC.B / 255f, genuineAlphas[g]));
                _glowSpoofDx[g] = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                    new Color4(spoofC.R / 255f, spoofC.G / 255f, spoofC.B / 255f, spoofAlphas[g]));
                _glowIcebergDx[g] = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                    new Color4(icebergC.R / 255f, icebergC.G / 255f, icebergC.B / 255f, icebergAlphas[g]));
            }

            // HUD
            _dxHudBg     = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.03f, 0.04f, 0.06f, 0.84f));
            _dxHudBorder = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.16f, 0.19f, 0.24f, 1f));
            _dxHudText   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.96f, 0.97f, 0.98f, 1f));

            // Same font as FootprintV7._labelFont: Segoe UI 10pt, trailing alignment
            _labelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 10f)
            {
                TextAlignment      = SharpDX.DirectWrite.TextAlignment.Trailing,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
            _hudFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 10f);
        }

        // ---- Rendering (carbon copy of FootprintV7.RenderLiquidityWalls + DrawWallsForSide) ----

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (IsInHitTest) return;
            if (RenderTarget == null || ChartPanel == null || ChartBars == null) return;
            if (_genuineDx == null || _labelFont == null) return;

            base.OnRender(chartControl, chartScale);
            RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

            float panelRight = (float)(ChartPanel.X + ChartPanel.W);
            RenderWalls(chartScale, panelRight);
            Interlocked.Exchange(ref _dirty, 0);
        }

        /// <summary>
        /// Identical to FootprintV7.RenderLiquidityWalls — snapshot under lock, then draw both sides.
        /// </summary>
        private void RenderWalls(ChartScale cs, float panelRight)
        {
            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;
            DateTime fresh = DateTime.UtcNow.AddSeconds(-WallStaleSec);

            // Deep-clone inside the lock (same pattern as FootprintV7)
            List<KeyValuePair<double, L2LevelStateV2>> bidSnap, askSnap;
            lock (_l2Lock)
            {
                bidSnap = new List<KeyValuePair<double, L2LevelStateV2>>(_l2Bids.Count);
                foreach (var kv in _l2Bids)
                    bidSnap.Add(new KeyValuePair<double, L2LevelStateV2>(kv.Key, new L2LevelStateV2 {
                        CurrentSize = kv.Value.CurrentSize, MaxSize = kv.Value.MaxSize,
                        LastUpdate = kv.Value.LastUpdate, RefillCount = kv.Value.RefillCount,
                        Classification = kv.Value.Classification, Confidence = kv.Value.Confidence,
                        LastClassificationTime = kv.Value.LastClassificationTime,
                        PriceTradedThrough = kv.Value.PriceTradedThrough, PriceCrossTime = kv.Value.PriceCrossTime,
                        FirstSeenTime = kv.Value.FirstSeenTime, ModificationCount = kv.Value.ModificationCount,
                        OriginalSize = kv.Value.OriginalSize, CancellationEvents = kv.Value.CancellationEvents,
                        SpoofScore = kv.Value.SpoofScore, FreshnessScore = kv.Value.FreshnessScore,
                        IsMLClassified = kv.Value.IsMLClassified }));

                askSnap = new List<KeyValuePair<double, L2LevelStateV2>>(_l2Asks.Count);
                foreach (var kv in _l2Asks)
                    askSnap.Add(new KeyValuePair<double, L2LevelStateV2>(kv.Key, new L2LevelStateV2 {
                        CurrentSize = kv.Value.CurrentSize, MaxSize = kv.Value.MaxSize,
                        LastUpdate = kv.Value.LastUpdate, RefillCount = kv.Value.RefillCount,
                        Classification = kv.Value.Classification, Confidence = kv.Value.Confidence,
                        LastClassificationTime = kv.Value.LastClassificationTime,
                        PriceTradedThrough = kv.Value.PriceTradedThrough, PriceCrossTime = kv.Value.PriceCrossTime,
                        FirstSeenTime = kv.Value.FirstSeenTime, ModificationCount = kv.Value.ModificationCount,
                        OriginalSize = kv.Value.OriginalSize, CancellationEvents = kv.Value.CancellationEvents,
                        SpoofScore = kv.Value.SpoofScore, FreshnessScore = kv.Value.FreshnessScore,
                        IsMLClassified = kv.Value.IsMLClassified }));
            }

            // One-shot diagnostic: print filter state for first few render cycles
            if (_diagPrintCountdown > 0)
            {
                _diagPrintCountdown--;
                int bidML = 0, askML = 0;
                foreach (var kv in bidSnap) if (kv.Value.IsMLClassified) bidML++;
                foreach (var kv in askSnap) if (kv.Value.IsMLClassified) askML++;
                Print(string.Format("[DEEP6DepthRadarV2-DIAG] bids={0}(ml={1}) asks={2}(ml={3}) visRange={4:F2}-{5:F2} fresh={6} WallMin={7} ShowB={8} ShowA={9} jsonMod={10}",
                    bidSnap.Count, bidML, askSnap.Count, askML, minVis, maxVis, fresh.ToString("HH:mm:ss"), WallMinSize, ShowBids, ShowAsks, _jsonLastModified.ToString("o")));
            }

            int[] classCounts = new int[5];
            if (ShowBids) DrawWallsForSide(cs, bidSnap, "BID", fresh, minVis, maxVis, panelRight, classCounts);
            if (ShowAsks) DrawWallsForSide(cs, askSnap, "ASK", fresh, minVis, maxVis, panelRight, classCounts);
            DrawHud(classCounts[(int)WallClassification.Genuine],
                    classCounts[(int)WallClassification.Spoof],
                    classCounts[(int)WallClassification.Iceberg],
                    classCounts[(int)WallClassification.Stale]);
        }

        /// <summary>
        /// Classification-based wall rendering. Selects brush and glow per wall classification.
        /// Unknown classification walls are skipped entirely.
        /// </summary>
        private void DrawWallsForSide(
            ChartScale cs,
            List<KeyValuePair<double, L2LevelStateV2>> snap,
            string side,
            DateTime fresh,
            double minVis,
            double maxVis,
            float panelRight,
            int[] classCounts)
        {
            if (snap == null || snap.Count == 0) return;

            // Filter eligible walls: meet size threshold, recently updated, in visible range.
            var walls = new List<KeyValuePair<double, L2LevelStateV2>>();
            foreach (var kv in snap)
            {
                if (kv.Value.MaxSize < WallMinSize) continue;
                // ML/JSON-classified walls persist until the source updates them;
                // only expire unclassified live DOM walls after WallStaleSec.
                if (!kv.Value.IsMLClassified && kv.Value.LastUpdate < fresh) continue;
                if (kv.Key < minVis || kv.Key > maxVis) continue;
                walls.Add(kv);
            }

            // Sort by max-size descending.
            walls.Sort((a, b) => b.Value.MaxSize.CompareTo(a.Value.MaxSize));

            int show = walls.Count;
            float lastLabelY = float.MinValue;
            const float LABEL_MIN_GAP = 14f;

            for (int i = 0; i < show; i++)
            {
                double price = walls[i].Key;
                var st = walls[i].Value;

                // Skip Unknown classification walls
                if (st.Classification == WallClassification.Unknown)
                    continue;

                classCounts[(int)st.Classification]++;

                // Select brush and glow arrays by classification
                SharpDX.Direct2D1.Brush wallBrush;
                SharpDX.Direct2D1.SolidColorBrush[] glowBrushes;
                float[] glowWidths;
                bool hasGlow;

                switch (st.Classification)
                {
                    case WallClassification.Genuine:
                        wallBrush   = _genuineDx;
                        glowBrushes = _glowGenuineDx;
                        glowWidths  = GLOW_WIDTHS_STANDARD;
                        hasGlow     = true;
                        break;
                    case WallClassification.Spoof:
                        wallBrush   = _spoofDx;
                        glowBrushes = _glowSpoofDx;
                        glowWidths  = GLOW_WIDTHS_STANDARD;
                        hasGlow     = true;
                        break;
                    case WallClassification.Iceberg:
                        wallBrush   = _icebergDx;
                        glowBrushes = _glowIcebergDx;
                        glowWidths  = GLOW_WIDTHS_ICEBERG;
                        hasGlow     = true;
                        break;
                    case WallClassification.Stale:
                        wallBrush   = _staleDx;
                        glowBrushes = null;
                        glowWidths  = null;
                        hasGlow     = false;
                        break;
                    default:
                        continue;
                }

                if (wallBrush == null) continue;
                float y = (float)cs.GetYByValue(price);

                // Glow bloom for levels >= GlowThreshold (no glow for Stale)
                if (hasGlow && st.MaxSize >= GlowThreshold && glowBrushes != null)
                {
                    for (int g = 0; g < 3; g++)
                        RenderTarget.DrawLine(
                            new Vector2((float)ChartPanel.X, y),
                            new Vector2(panelRight - 90, y),
                            glowBrushes[g],
                            glowWidths[g]);
                }

                // Line thickness scales 1.5px -> 4px based on size
                float thickness = (float)Math.Min(4.0, 1.5 + (st.MaxSize / (double)WallMinSize) * 0.4);
                RenderTarget.DrawLine(
                    new Vector2((float)ChartPanel.X, y),
                    new Vector2(panelRight - 90, y),
                    wallBrush, thickness);

                // Label with classification-specific format
                if (!ShowLabels) continue;

                float labelY = y - 8f;
                if (lastLabelY != float.MinValue && Math.Abs(labelY - lastLabelY) < LABEL_MIN_GAP)
                    continue;

                string classTag;
                switch (st.Classification)
                {
                    case WallClassification.Genuine:
                        classTag = string.Format(" [GENUINE {0}%]", (int)(st.Confidence * 100));
                        break;
                    case WallClassification.Spoof:
                        classTag = string.Format(" [SPOOF {0}%]", (int)(st.Confidence * 100));
                        break;
                    case WallClassification.Iceberg:
                        classTag = string.Format(" [ICE\u00d7{0} {1}%]", st.RefillCount, (int)(st.Confidence * 100));
                        break;
                    case WallClassification.Stale:
                        classTag = " [STALE]";
                        break;
                    default:
                        classTag = "";
                        break;
                }

                string interTag = "";
                if (!string.IsNullOrEmpty(st.InteractionPrediction))
                {
                    string arrow = st.InteractionPrediction == "BOUNCE" ? "\u25B2" :
                                   st.InteractionPrediction == "BREAK" ? "\u25BC" : "\u25C6";
                    interTag = string.Format(" {0}{1} {2}%", arrow, st.InteractionPrediction,
                        (int)(st.InteractionConfidence * 100));
                }
                string label = string.Format("{0} {1:F2}  {2}{3}{4}",
                    side, price, st.MaxSize, classTag, interTag);

                using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                    label, _labelFont, 260f, 16f))
                {
                    RenderTarget.DrawTextLayout(new Vector2(panelRight - 264, labelY), layout, wallBrush);
                }

                lastLabelY = labelY;
            }
        }

        private void DrawHud(int genuineCount, int spoofCount, int icebergCount, int staleCount)
        {
            if (_hudFont == null || _dxHudBg == null || _dxHudText == null) return;

            long callbacks = Interlocked.Read(ref _depthCallbacks);

            string mlStatus;
            if (!EnableML)
                mlStatus = "ML:OFF";
            else if (_bridgeConnected && _lastIpcLatencyMs > 0)
                mlStatus = string.Format("ML:ON [{0}ms]", (int)_lastIpcLatencyMs);
            else if (_bridgeConnected)
                mlStatus = "ML:ON";
            else
                mlStatus = "ML:OFF";

            string text = string.Format("DEPTH RADAR V2 | G:{0} S:{1} I:{2} X:{3} | {4} | cb: {5:N0}",
                genuineCount, spoofCount, icebergCount, staleCount, mlStatus, callbacks);

            float w = 420f;
            float h = 20f;
            float x = (float)(ChartPanel.X + ChartPanel.W) - w - 8f;
            float y = (float)ChartPanel.Y + 8f;

            RenderTarget.FillRectangle(new RectangleF(x, y, w, h), _dxHudBg);
            RenderTarget.DrawRectangle(new RectangleF(x, y, w, h), _dxHudBorder, 1f);

            using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                text, _hudFont, w - 10f, h))
            {
                RenderTarget.DrawTextLayout(new Vector2(x + 5f, y + 2f), layout, _dxHudText);
            }
        }

        // ---- Helpers ----

        private void ClearBooks()
        {
            lock (_l2Lock)
            {
                _l2Bids.Clear();
                _l2Asks.Clear();
                _lastL2Prune = DateTime.MinValue;
                _bestBid = 0.0;
                _bestAsk = 0.0;
                _avgWallSize = 0.0;
            }
            // Reset so the next timer tick reloads the JSON file
            _jsonLastModified = DateTime.MinValue;
        }

        private void DisposeDx()
        {
            DisposeBrush(ref _genuineDx);
            DisposeBrush(ref _spoofDx);
            DisposeBrush(ref _icebergDx);
            DisposeBrush(ref _staleDx);
            DisposeGlowArray(ref _glowGenuineDx);
            DisposeGlowArray(ref _glowSpoofDx);
            DisposeGlowArray(ref _glowIcebergDx);
            DisposeSolidBrush(ref _dxHudBg);
            DisposeSolidBrush(ref _dxHudBorder);
            DisposeSolidBrush(ref _dxHudText);
            if (_labelFont != null) { _labelFont.Dispose(); _labelFont = null; }
            if (_hudFont   != null) { _hudFont.Dispose();   _hudFont   = null; }
        }

        private static void DisposeGlowArray(ref SharpDX.Direct2D1.SolidColorBrush[] arr)
        {
            if (arr == null) return;
            for (int i = 0; i < arr.Length; i++)
                DisposeSolidBrush(ref arr[i]);
            arr = null;
        }

        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush b)
        {
            if (b != null) { b.Dispose(); b = null; }
        }

        private static void DisposeSolidBrush(ref SharpDX.Direct2D1.SolidColorBrush b)
        {
            if (b != null) { b.Dispose(); b = null; }
        }

        private static SolidColorBrush MakeFrozenBrush(Color c)
        {
            var b = new SolidColorBrush(c);
            if (b.CanFreeze) b.Freeze();
            return b;
        }

        private static Color ExtractColor(Brush brush, Color fallback)
        {
            var solid = brush as SolidColorBrush;
            return solid != null ? solid.Color : fallback;
        }

        #region Properties

        [NinjaScriptProperty]
        [Display(Name = "Walls JSON Path", Order = 1, GroupName = "4. Data Source",
            Description = "Local JSON file written by scripts/depth_radar_live.py")]
        public string WallsJsonPath { get; set; }

        [NinjaScriptProperty]
        [Range(1, 5000)]
        [Display(Name = "Wall Min Size (contracts)", Order = 1, GroupName = "1. Liquidity",
            Description = "Minimum contracts to show a level")]
        public int WallMinSize { get; set; }

        [NinjaScriptProperty]
        [Range(10, 600)]
        [Display(Name = "Wall Stale (seconds)", Order = 2, GroupName = "1. Liquidity",
            Description = "Hide levels not updated within this window")]
        public int WallStaleSec { get; set; }

        [NinjaScriptProperty]
        [Range(5, 50)]
        [Display(Name = "Max Depth Levels", Order = 3, GroupName = "1. Liquidity",
            Description = "DOM levels to consume per side (Rithmic provides 40+ for NQ)")]
        public int MaxDepthLevels { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10000)]
        [Display(Name = "Glow Threshold (contracts)", Order = 4, GroupName = "1. Liquidity",
            Description = "Levels at or above this size get a glow bloom effect")]
        public int GlowThreshold { get; set; }

        [NinjaScriptProperty]
        [Range(5, 300)]
        [Display(Name = "Stale Cross Timeout (seconds)", Order = 5, GroupName = "1. Liquidity",
            Description = "Seconds after price crosses a level before marking it STALE")]
        public int StaleCrossTimeoutSec { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Bids", Order = 1, GroupName = "2. Display")]
        public bool ShowBids { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Asks", Order = 2, GroupName = "2. Display")]
        public bool ShowAsks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Labels", Order = 3, GroupName = "2. Display")]
        public bool ShowLabels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable ML Classification", Order = 4, GroupName = "2. Display",
            Description = "Enable ML classification service connection")]
        public bool EnableML { get; set; }

        [XmlIgnore]
        [Display(Name = "Genuine Color", Order = 1, GroupName = "3. Colors",
            Description = "Color for walls classified as genuine resting liquidity")]
        public Brush GenuineBrush { get; set; }

        [Browsable(false)]
        public string GenuineBrushSerialize
        {
            get { return Serialize.BrushToString(GenuineBrush); }
            set { GenuineBrush = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Spoof Color", Order = 2, GroupName = "3. Colors",
            Description = "Color for walls classified as likely spoofing")]
        public Brush SpoofBrush { get; set; }

        [Browsable(false)]
        public string SpoofBrushSerialize
        {
            get { return Serialize.BrushToString(SpoofBrush); }
            set { SpoofBrush = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Iceberg Color", Order = 3, GroupName = "3. Colors",
            Description = "Color for walls classified as iceberg orders")]
        public Brush IcebergBrush { get; set; }

        [Browsable(false)]
        public string IcebergBrushSerialize
        {
            get { return Serialize.BrushToString(IcebergBrush); }
            set { IcebergBrush = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Stale Color", Order = 4, GroupName = "3. Colors",
            Description = "Color for walls classified as stale/aged liquidity")]
        public Brush StaleBrush { get; set; }

        [Browsable(false)]
        public string StaleBrushSerialize
        {
            get { return Serialize.BrushToString(StaleBrush); }
            set { StaleBrush = Serialize.StringToBrush(value); }
        }

        /// <summary>
        /// Snapshot of current bid-side prices classified as genuine walls and meeting
        /// the active <see cref="WallMinSize"/> threshold.
        /// </summary>
        [Browsable(false)]
        [XmlIgnore]
        public List<double> GenuineBidWallPrices
        {
            get
            {
                var result = new List<double>();
                lock (_l2Lock)
                {
                    foreach (var kvp in _l2Bids)
                    {
                        if (kvp.Value == null)
                            continue;
                        if (kvp.Value.CurrentSize < WallMinSize)
                            continue;
                        if (kvp.Value.Classification != WallClassification.Genuine)
                            continue;

                        result.Add(kvp.Key);
                    }
                }
                result.Sort();
                return result;
            }
        }

        /// <summary>
        /// Snapshot of current ask-side prices classified as genuine walls and meeting
        /// the active <see cref="WallMinSize"/> threshold.
        /// </summary>
        [Browsable(false)]
        [XmlIgnore]
        public List<double> GenuineAskWallPrices
        {
            get
            {
                var result = new List<double>();
                lock (_l2Lock)
                {
                    foreach (var kvp in _l2Asks)
                    {
                        if (kvp.Value == null)
                            continue;
                        if (kvp.Value.CurrentSize < WallMinSize)
                            continue;
                        if (kvp.Value.Classification != WallClassification.Genuine)
                            continue;

                        result.Add(kvp.Key);
                    }
                }
                result.Sort();
                return result;
            }
        }

        #endregion

        // ---- Inner class: TCP NDJSON bridge for Python ML classification service ----
        // Listens on port 9201. Accepts one client. Follows DataBridgeServer patterns
        // but lighter weight: single client, bidirectional, heartbeat.

        private sealed class DepthRadarBridge : IDisposable
        {
            private const int BRIDGE_PORT = 9201;
            private const int HEARTBEAT_MS = 5000;

            private TcpListener _listener;
            private TcpClient _client;
            private NetworkStream _stream;
            private StreamReader _reader;
            private Thread _acceptThread;
            private Timer _heartbeatTimer;
            private volatile bool _running;
            private readonly object _clientLock = new object();
            private readonly Action<string> _log;
            private readonly Action<string> _onMessage;

            public volatile bool IsConnected;
            public float LastIpcLatencyMs;

            public DepthRadarBridge(Action<string> log, Action<string> onMessage)
            {
                _log = log;
                _onMessage = onMessage;
            }

            public void Start()
            {
                if (_running) return;
                _running = true;
                _listener = new TcpListener(IPAddress.Loopback, BRIDGE_PORT);
                _listener.Start();
                _acceptThread = new Thread(AcceptLoop)
                {
                    IsBackground = true,
                    Name = "DEEP6-DepthRadar-Bridge"
                };
                _acceptThread.Start();
                _heartbeatTimer = new Timer(OnHeartbeat, null, HEARTBEAT_MS, HEARTBEAT_MS);
                _log("[DepthRadarBridge] Listening on 127.0.0.1:" + BRIDGE_PORT);
            }

            public void Stop()
            {
                _running = false;
                if (_heartbeatTimer != null) { _heartbeatTimer.Dispose(); _heartbeatTimer = null; }
                try { _listener?.Stop(); } catch { }
                lock (_clientLock) { CloseClient(); }
            }

            public void Dispose() { Stop(); }

            private void AcceptLoop()
            {
                while (_running)
                {
                    try
                    {
                        TcpClient client = _listener.AcceptTcpClient();
                        client.NoDelay = true;
                        lock (_clientLock)
                        {
                            // Close prior client — only one connection at a time
                            CloseClient();
                            _client = client;
                            _stream = client.GetStream();
                            _reader = new StreamReader(_stream, Encoding.UTF8);
                            IsConnected = true;
                        }
                        _log("[DepthRadarBridge] Client connected from " + client.Client.RemoteEndPoint);
                        ReadLoop();
                    }
                    catch (SocketException) when (!_running) { break; }
                    catch (Exception ex)
                    {
                        if (_running)
                        {
                            _log("[DepthRadarBridge] Accept error: " + ex.Message);
                            Thread.Sleep(500);
                        }
                    }
                    finally
                    {
                        lock (_clientLock) { CloseClient(); }
                        IsConnected = false;
                    }
                }
            }

            private void ReadLoop()
            {
                // Capture local reference to avoid TOCTOU race with CloseClient
                StreamReader reader = _reader;
                if (reader == null) return;
                try
                {
                    while (_running)
                    {
                        string line = reader.ReadLine();
                        if (line == null) break;
                        if (line.Length == 0) continue;
                        _onMessage(line);
                    }
                }
                catch (IOException) { }
                catch (ObjectDisposedException) { }
            }

            private void OnHeartbeat(object state)
            {
                if (!IsConnected) return;
                long tsMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                string hb = string.Format("{{\"type\":\"heartbeat\",\"timestamp\":{0}}}", tsMs);
                SendLine(hb);
            }

            public bool SendLine(string json)
            {
                lock (_clientLock)
                {
                    if (_client == null || _stream == null) return false;
                    try
                    {
                        byte[] data = Encoding.UTF8.GetBytes(json + "\n");
                        _stream.Write(data, 0, data.Length);
                        return true;
                    }
                    catch
                    {
                        CloseClient();
                        IsConnected = false;
                        return false;
                    }
                }
            }

            // Must be called under _clientLock
            private void CloseClient()
            {
                try { _reader?.Dispose(); } catch { }
                try { _stream?.Dispose(); } catch { }
                try { _client?.Close(); } catch { }
                _reader = null;
                _stream = null;
                _client = null;
            }
        }
    }
}
