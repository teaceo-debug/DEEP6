// DEEP6 DepthRadar V3 — JSON Rithmic direct-feed version of V1.
//
// Functionally identical to DEEP6 Depth Radar V1:
//   - Same single brush per side via .ToDxBrush()
//   - Same continuous thickness formula: Min(4, 1.5 + (MaxSize/WallMin)*0.4)
//   - Same label format, font, positioning
//   - Same ICE annotation
//   - Same glow bloom on levels >= GlowThreshold
//   - Same HUD
//
// Only difference from V1:
//   - No OnMarketDepth — does NOT consume NT8's native L2 DOM feed
//   - Reads wall data from a JSON file written by scripts/depth_radar_live.py
//     which connects directly to Rithmic via async-rithmic and streams DOM data
//   - JSON file is polled every 2 seconds for changes (same pattern as V2)

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
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
    public class DEEP6DepthRadarV3 : Indicator
    {
        // ---- L2 Level State (identical to V1.L2LevelState) ----
        private sealed class L2LevelState
        {
            public long     CurrentSize;
            public long     MaxSize;
            public DateTime LastUpdate;
            public int      RefillCount;
        }

        // ---- Per-price dictionaries — written by JSON reader, snapshot-read by OnRender ----
        private readonly Dictionary<double, L2LevelState> _l2Bids = new Dictionary<double, L2LevelState>();
        private readonly Dictionary<double, L2LevelState> _l2Asks = new Dictionary<double, L2LevelState>();
        private readonly object _l2Lock = new object();
        private DateTime _lastL2Prune = DateTime.MinValue;
        private long _jsonReads;

        // ---- JSON file polling ----
        private DateTime _jsonLastModified = DateTime.MinValue;
        private Timer _jsonCheckTimer;
        private const int JSON_CHECK_MS = 2000;

        // ---- DX Resources (identical types to V1) ----
        private SharpDX.Direct2D1.Brush _wallBidDx;
        private SharpDX.Direct2D1.Brush _wallAskDx;
        // Glow bloom brushes for levels >= GlowThreshold (3 passes: outer -> inner)
        private SharpDX.Direct2D1.SolidColorBrush[] _glowBidDx;
        private SharpDX.Direct2D1.SolidColorBrush[] _glowAskDx;
        private static readonly float[] GLOW_ALPHAS = { 0.08f, 0.18f, 0.35f };
        private static readonly float[] GLOW_WIDTHS = { 14f,   8f,    5f    };
        // HUD
        private SharpDX.Direct2D1.SolidColorBrush _dxHudBg;
        private SharpDX.Direct2D1.SolidColorBrush _dxHudBorder;
        private SharpDX.Direct2D1.SolidColorBrush _dxHudText;
        // Fonts — same as V1 / FootprintV7._labelFont
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
                Description         = "Full-spectrum DOM liquidity levels — JSON Rithmic direct-feed version. Identical rendering to DEEP6 Depth Radar V1. Reads wall data from scripts/depth_radar_live.py JSON output instead of NT8 OnMarketDepth.";
                Name                = "DEEP6 Depth Radar V3";
                Calculate           = Calculate.OnEachTick;
                IsOverlay           = true;
                DrawOnPricePanel    = true;
                PaintPriceMarkers   = false;
                IsSuspendedWhileInactive = false;
                DisplayInDataBox    = false;
                ScaleJustification  = ScaleJustification.Right;

                // Lower default than V1 — JSON source already pre-filters via depth_radar_live.py --min-wall
                WallMinSize         = 10;
                WallStaleSec        = 90;
                MaxDepthLevels      = 40;
                GlowThreshold       = 100;
                ShowBids            = true;
                ShowAsks            = true;
                ShowLabels          = true;

                // JSON source path — default matches depth_radar_live.py output
                WallsJsonPath       = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Personal),
                                        "NinjaTrader 8", "templates", "DEEP6", "depth_radar_walls.json");

                // Same colors as V1
                WallBidBrush        = MakeFrozenBrush(Color.FromArgb(220, 43, 140, 255));   // bright blue
                WallAskBrush        = MakeFrozenBrush(Color.FromArgb(220, 255, 138, 61));   // warm orange
            }
            else if (State == State.DataLoaded)
            {
                ClearBooks();
                Interlocked.Exchange(ref _dirty, 1);
                if (_invalidateTimer == null)
                    _invalidateTimer = new Timer(OnInvalidateTick, null, INVALIDATE_MS, INVALIDATE_MS);
                if (_jsonCheckTimer == null)
                    _jsonCheckTimer = new Timer(OnJsonCheck, null, JSON_CHECK_MS, JSON_CHECK_MS);
                Print("[DEEP6DepthRadarV3] DataLoaded — JSON path: " + WallsJsonPath + " exists=" + File.Exists(WallsJsonPath));
                // Early diagnostic — confirms V3 is on the chart and initializing
                try
                {
                    string diagPath = Path.Combine(Path.GetTempPath(), "deep6_v3_diag.txt");
                    File.WriteAllText(diagPath, string.Format(
                        "state=DataLoaded\ntime={0}\njsonPath={1}\njsonExists={2}\nWallMinSize={3}\n",
                        DateTime.UtcNow.ToString("o"), WallsJsonPath, File.Exists(WallsJsonPath), WallMinSize));
                }
                catch { }
            }
            else if (State == State.Historical)
            {
                try { SetZOrder(-1); } catch { }
            }
            else if (State == State.Realtime)
            {
                Print("[DEEP6DepthRadarV3] Realtime — reading Rithmic DOM data from JSON: " + WallsJsonPath);
            }
            else if (State == State.Terminated)
            {
                if (_invalidateTimer != null) { _invalidateTimer.Dispose(); _invalidateTimer = null; }
                if (_jsonCheckTimer  != null) { _jsonCheckTimer.Dispose();  _jsonCheckTimer  = null; }
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
                Interlocked.Exchange(ref _jsonReads, 0);
                Interlocked.Exchange(ref _dirty, 1);
            }
        }

        // ---- JSON file polling (replaces V1's OnMarketDepth) ----

        private void OnJsonCheck(object state)
        {
            try
            {
                if (ReadWallsFromJson())
                {
                    Interlocked.Exchange(ref _dirty, 1);
                }
                else
                {
                    // File hasn't changed — refresh LastUpdate on all walls to prevent staleness.
                    // Unlike V1's OnMarketDepth (continuous streaming), V3 reads snapshots from
                    // a JSON file. Walls should stay alive as long as the snapshot is current.
                    RefreshWallTimestamps();
                }
            }
            catch (Exception ex)
            {
                Print("[DEEP6DepthRadarV3] JSON read failed: " + ex.Message);
            }
        }

        /// <summary>
        /// Keeps all walls alive by resetting their LastUpdate to now.
        /// Called on timer ticks when the JSON file hasn't changed.
        /// </summary>
        private void RefreshWallTimestamps()
        {
            DateTime utcNow = DateTime.UtcNow;
            bool any = false;
            lock (_l2Lock)
            {
                foreach (var kv in _l2Bids)
                {
                    kv.Value.LastUpdate = utcNow;
                    any = true;
                }
                foreach (var kv in _l2Asks)
                {
                    kv.Value.LastUpdate = utcNow;
                    any = true;
                }
            }
            if (any) Interlocked.Exchange(ref _dirty, 1);
        }

        /// <summary>
        /// Reads the JSON file written by scripts/depth_radar_live.py and populates
        /// the bid/ask dictionaries with L2LevelState entries. Only re-reads when
        /// the file's last-write timestamp has changed.
        ///
        /// JSON format (from depth_radar_live.py):
        /// {
        ///   "timestamp": "...",
        ///   "symbol": "NQM6",
        ///   "mid_price": 19483.50,
        ///   "wall_count": 15,
        ///   "walls": [
        ///     { "price": 19480.00, "side": "bid", "size": 150, "max_size": 200,
        ///       "duration_sec": 45.2, "refill_count": 2, ... },
        ///     ...
        ///   ]
        /// }
        ///
        /// V3 only reads the fields V1 cares about: price, side, size, max_size, refill_count.
        /// Classification fields are ignored (V1 has no classification system).
        /// </summary>
        private bool ReadWallsFromJson()
        {
            if (string.IsNullOrWhiteSpace(WallsJsonPath) || !File.Exists(WallsJsonPath))
                return false;

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

            // Clear existing data on each full JSON read — the JSON is a complete snapshot
            lock (_l2Lock)
            {
                _l2Bids.Clear();
                _l2Asks.Clear();

                while (i < n)
                {
                    // Find next object
                    while (i < n && json[i] != '{' && json[i] != ']') i++;
                    if (i >= n || json[i] == ']') break;

                    // Extract the JSON object substring
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
                    double price    = ParseJsonDouble(item, "price");
                    string side     = ParseJsonString(item, "side");
                    long   size     = (long)Math.Round(ParseJsonDouble(item, "size"));
                    long   maxSize  = (long)Math.Round(ParseJsonDouble(item, "max_size"));
                    int    refills  = (int)Math.Round(ParseJsonDouble(item, "refill_count"));

                    if (price <= 0 || string.IsNullOrEmpty(side))
                        continue;
                    // Skip walls below threshold or with zero current size
                    if (size <= 0)
                        continue;

                    var dict = string.Equals(side, "ask", StringComparison.OrdinalIgnoreCase) ? _l2Asks : _l2Bids;

                    dict[price] = new L2LevelState
                    {
                        CurrentSize = size,
                        MaxSize     = Math.Max(size, maxSize),
                        LastUpdate  = utcNow,
                        RefillCount = refills,
                    };

                    updated = true;
                }

                // Prune stale entries (same cadence check as V1)
                if ((utcNow - _lastL2Prune).TotalSeconds > 30)
                {
                    PruneL2(_l2Bids);
                    PruneL2(_l2Asks);
                    _lastL2Prune = utcNow;
                }
            }

            if (updated)
            {
                Interlocked.Increment(ref _jsonReads);
                string msg = string.Format("[DEEP6DepthRadarV3] JSON loaded {0} bids + {1} asks (WallMinSize={2})",
                    _l2Bids.Count, _l2Asks.Count, WallMinSize);
                Print(msg);

                // Write diagnostic file for debugging
                try
                {
                    string diagPath = Path.Combine(Path.GetTempPath(), "deep6_v3_diag.txt");
                    File.WriteAllText(diagPath, string.Format(
                        "time={0}\nbids={1}\nasks={2}\nWallMinSize={3}\nWallStaleSec={4}\nreads={5}\njsonPath={6}\n",
                        DateTime.UtcNow.ToString("o"), _l2Bids.Count, _l2Asks.Count,
                        WallMinSize, WallStaleSec, Interlocked.Read(ref _jsonReads), WallsJsonPath));
                }
                catch { }
            }

            return updated;
        }

        // Lightweight JSON string field extractor (no JSON library — .NET Framework 4.8)
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

        // Lightweight JSON numeric field extractor
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

        private void PruneL2(Dictionary<double, L2LevelState> dict)
        {
            var cutoff = DateTime.UtcNow.AddSeconds(-Math.Max(WallStaleSec * 3, 300));
            var stale = new List<double>();
            foreach (var kv in dict)
                if (kv.Value.LastUpdate < cutoff) stale.Add(kv.Key);
            foreach (var k in stale) dict.Remove(k);
        }

        // ---- Invalidation timer (identical to V1) ----

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

        // ---- DX Resource Management (identical to V1) ----

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            _wallBidDx = WallBidBrush.ToDxBrush(RenderTarget);
            _wallAskDx = WallAskBrush.ToDxBrush(RenderTarget);

            Color bidC = ExtractColor(WallBidBrush, Color.FromArgb(220, 43, 140, 255));
            Color askC = ExtractColor(WallAskBrush, Color.FromArgb(220, 255, 138, 61));
            _glowBidDx = new SharpDX.Direct2D1.SolidColorBrush[3];
            _glowAskDx = new SharpDX.Direct2D1.SolidColorBrush[3];
            for (int g = 0; g < 3; g++)
            {
                _glowBidDx[g] = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                    new Color4(bidC.R / 255f, bidC.G / 255f, bidC.B / 255f, GLOW_ALPHAS[g]));
                _glowAskDx[g] = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                    new Color4(askC.R / 255f, askC.G / 255f, askC.B / 255f, GLOW_ALPHAS[g]));
            }

            _dxHudBg     = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.03f, 0.04f, 0.06f, 0.84f));
            _dxHudBorder = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.16f, 0.19f, 0.24f, 1f));
            _dxHudText   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.96f, 0.97f, 0.98f, 1f));

            _labelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 10f)
            {
                TextAlignment      = SharpDX.DirectWrite.TextAlignment.Trailing,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
            _hudFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 10f);
        }

        // ---- Rendering (identical to V1) ----

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (IsInHitTest) return;
            if (RenderTarget == null || ChartPanel == null || ChartBars == null) return;
            if (_wallBidDx == null || _wallAskDx == null || _labelFont == null) return;

            base.OnRender(chartControl, chartScale);
            RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

            float panelRight = (float)(ChartPanel.X + ChartPanel.W);
            RenderWalls(chartScale, panelRight);
            Interlocked.Exchange(ref _dirty, 0);
        }

        /// <summary>
        /// Identical to V1.RenderWalls — snapshot under lock, then draw both sides.
        /// </summary>
        private void RenderWalls(ChartScale cs, float panelRight)
        {
            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;
            DateTime fresh = DateTime.UtcNow.AddSeconds(-WallStaleSec);

            List<KeyValuePair<double, L2LevelState>> bidSnap, askSnap;
            lock (_l2Lock)
            {
                bidSnap = new List<KeyValuePair<double, L2LevelState>>(_l2Bids.Count);
                foreach (var kv in _l2Bids)
                    bidSnap.Add(new KeyValuePair<double, L2LevelState>(kv.Key, new L2LevelState {
                        CurrentSize = kv.Value.CurrentSize, MaxSize = kv.Value.MaxSize,
                        LastUpdate  = kv.Value.LastUpdate,  RefillCount = kv.Value.RefillCount }));

                askSnap = new List<KeyValuePair<double, L2LevelState>>(_l2Asks.Count);
                foreach (var kv in _l2Asks)
                    askSnap.Add(new KeyValuePair<double, L2LevelState>(kv.Key, new L2LevelState {
                        CurrentSize = kv.Value.CurrentSize, MaxSize = kv.Value.MaxSize,
                        LastUpdate  = kv.Value.LastUpdate,  RefillCount = kv.Value.RefillCount }));
            }

            int bidRendered = 0, askRendered = 0;
            if (ShowBids) bidRendered = DrawWallsForSide(cs, bidSnap, _wallBidDx, "BID", true,  fresh, minVis, maxVis, panelRight);
            if (ShowAsks) askRendered = DrawWallsForSide(cs, askSnap, _wallAskDx, "ASK", false, fresh, minVis, maxVis, panelRight);
            DrawHud(bidRendered, askRendered);
        }

        /// <summary>
        /// Identical to V1.DrawWallsForSide — same brush, same thickness formula,
        /// same label format, same coordinates. No LiquidityMaxPerSide cap.
        /// Glow bloom for levels >= GlowThreshold.
        /// </summary>
        private int DrawWallsForSide(
            ChartScale cs,
            List<KeyValuePair<double, L2LevelState>> snap,
            SharpDX.Direct2D1.Brush brush,
            string side,
            bool isBid,
            DateTime fresh,
            double minVis,
            double maxVis,
            float panelRight)
        {
            if (snap == null || snap.Count == 0) return 0;

            var walls = new List<KeyValuePair<double, L2LevelState>>();
            foreach (var kv in snap)
            {
                if (kv.Value.MaxSize < WallMinSize) continue;
                if (kv.Value.LastUpdate < fresh) continue;
                if (kv.Key < minVis || kv.Key > maxVis) continue;
                walls.Add(kv);
            }

            walls.Sort((a, b) => b.Value.MaxSize.CompareTo(a.Value.MaxSize));

            int show = walls.Count;
            float lastLabelY = float.MinValue;
            const float LABEL_MIN_GAP = 14f;

            for (int i = 0; i < show; i++)
            {
                double price = walls[i].Key;
                var st = walls[i].Value;
                float y = (float)cs.GetYByValue(price);

                // Glow bloom for levels >= GlowThreshold
                if (st.MaxSize >= GlowThreshold)
                {
                    var glowBrushes = isBid ? _glowBidDx : _glowAskDx;
                    if (glowBrushes != null)
                    {
                        for (int g = 0; g < 3; g++)
                            RenderTarget.DrawLine(
                                new Vector2((float)ChartPanel.X, y),
                                new Vector2(panelRight - 90, y),
                                glowBrushes[g],
                                GLOW_WIDTHS[g]);
                    }
                }

                // Line thickness scales 1.5px -> 4px (same formula as V1)
                float thickness = (float)Math.Min(4.0, 1.5 + (st.MaxSize / (double)WallMinSize) * 0.4);
                RenderTarget.DrawLine(
                    new Vector2((float)ChartPanel.X, y),
                    new Vector2(panelRight - 90, y),
                    brush, thickness);

                // Label (same format as V1: "BID 21025.50  150 ICExN")
                if (!ShowLabels) continue;

                float labelY = y - 8f;
                if (lastLabelY != float.MinValue && Math.Abs(labelY - lastLabelY) < LABEL_MIN_GAP)
                    continue;

                string label = string.Format("{0} {1:F2}  {2}{3}",
                    side, price, st.MaxSize,
                    st.RefillCount >= 2 ? " ICE\u00d7" + st.RefillCount : "");

                using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                    label, _labelFont, 180f, 16f))
                {
                    RenderTarget.DrawTextLayout(new Vector2(panelRight - 184, labelY), layout, brush);
                }

                lastLabelY = labelY;
            }

            return show;
        }

        private void DrawHud(int bidCount, int askCount)
        {
            if (_hudFont == null || _dxHudBg == null || _dxHudText == null) return;

            long reads = Interlocked.Read(ref _jsonReads);
            int totalBids, totalAsks;
            lock (_l2Lock) { totalBids = _l2Bids.Count; totalAsks = _l2Asks.Count; }
            string text = string.Format("DEPTH RADAR V3 [JSON] | vis B:{0} A:{1} | loaded B:{2} A:{3} | reads:{4}",
                bidCount, askCount, totalBids, totalAsks, reads);

            float w = 520f;
            float h = 20f;
            // Top-right position to avoid NinjaTrader logo watermark
            float x = (float)(ChartPanel.X + ChartPanel.W) - w - 8f;
            float y = (float)ChartPanel.Y + 30f;

            RenderTarget.FillRectangle(new RectangleF(x, y, w, h), _dxHudBg);
            RenderTarget.DrawRectangle(new RectangleF(x, y, w, h), _dxHudBorder, 1f);

            using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                text, _hudFont, w - 10f, h))
            {
                RenderTarget.DrawTextLayout(new Vector2(x + 5f, y + 2f), layout, _dxHudText);
            }
        }

        // ---- Helpers (identical to V1) ----

        private void ClearBooks()
        {
            lock (_l2Lock)
            {
                _l2Bids.Clear();
                _l2Asks.Clear();
                _lastL2Prune = DateTime.MinValue;
            }
        }

        private void DisposeDx()
        {
            DisposeBrush(ref _wallBidDx);
            DisposeBrush(ref _wallAskDx);
            DisposeGlowArray(ref _glowBidDx);
            DisposeGlowArray(ref _glowAskDx);
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
        [Display(Name = "Walls JSON Path", Order = 0, GroupName = "0. Data Source",
            Description = "Path to JSON file written by scripts/depth_radar_live.py (Rithmic DOM data)")]
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
        [Display(Name = "Show Bids", Order = 1, GroupName = "2. Display")]
        public bool ShowBids { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Asks", Order = 2, GroupName = "2. Display")]
        public bool ShowAsks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Labels", Order = 3, GroupName = "2. Display")]
        public bool ShowLabels { get; set; }

        [XmlIgnore]
        [Display(Name = "Bid Color (resting buy)", Order = 1, GroupName = "3. Colors")]
        public Brush WallBidBrush { get; set; }

        [Browsable(false)]
        public string WallBidBrushSerialize
        {
            get { return Serialize.BrushToString(WallBidBrush); }
            set { WallBidBrush = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Ask Color (resting sell)", Order = 2, GroupName = "3. Colors")]
        public Brush WallAskBrush { get; set; }

        [Browsable(false)]
        public string WallAskBrushSerialize
        {
            get { return Serialize.BrushToString(WallAskBrush); }
            set { WallAskBrush = Serialize.StringToBrush(value); }
        }

        #endregion
    }
}
