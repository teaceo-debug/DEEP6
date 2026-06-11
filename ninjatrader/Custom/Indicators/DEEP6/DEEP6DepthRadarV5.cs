// DEEP6 DepthRadar V5 — schema-v2 MBO evidence/ranking JSON renderer.
//
// V5 extends V4 with:
//   - DEEP6_DEPTH_RADAR_V2 schema awareness
//   - source-quality and data-quality HUD
//   - wall rank scores (quality/spoof/iceberg/break-risk)
//   - faster JSON polling + render snapshot throttling

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
    public class DEEP6DepthRadarV5 : Indicator
    {
        private sealed class L2LevelState
        {
            public long     CurrentSize;
            public long     MaxSize;
            public DateTime LastUpdate;
            public int      RefillCount;
            public string   Intent;
            public string   WallState;
            public string   Classification;
            public float    Confidence;
            public float    DurationSec;
            public float    QualityScore;
            public float    SpoofScore;
            public float    IcebergScore;
            public float    BreakRiskScore;
            public string   SourceQuality;
            public string   Evidence;
        }

        private readonly Dictionary<double, L2LevelState> _l2Bids = new Dictionary<double, L2LevelState>();
        private readonly Dictionary<double, L2LevelState> _l2Asks = new Dictionary<double, L2LevelState>();
        private readonly object _l2Lock = new object();
        private DateTime _lastL2Prune = DateTime.MinValue;
        private long _jsonReads;
        private string _schema = "legacy";
        private string _sourceQuality = "UNKNOWN";
        private bool _orderIdAvailable;
        private double _payloadMidPrice;

        private DateTime _jsonLastModified = DateTime.MinValue;
        private Timer _jsonCheckTimer;
        private const int JSON_CHECK_MS = 500;

        private SharpDX.Direct2D1.Brush _wallBidDx;
        private SharpDX.Direct2D1.Brush _wallAskDx;
        private SharpDX.Direct2D1.Brush _intentPassiveDx;
        private SharpDX.Direct2D1.Brush _intentSpoofDx;
        private SharpDX.Direct2D1.Brush _intentReserveDx;
        private SharpDX.Direct2D1.Brush _intentMigratoryDx;

        private SharpDX.Direct2D1.SolidColorBrush[] _glowBidDx;
        private SharpDX.Direct2D1.SolidColorBrush[] _glowAskDx;
        private SharpDX.Direct2D1.SolidColorBrush[] _glowPassiveDx;
        private SharpDX.Direct2D1.SolidColorBrush[] _glowSpoofDx;
        private SharpDX.Direct2D1.SolidColorBrush[] _glowReserveDx;
        private SharpDX.Direct2D1.SolidColorBrush[] _glowMigratoryDx;
        private static readonly float[] GLOW_ALPHAS = { 0.08f, 0.18f, 0.35f };
        private static readonly float[] GLOW_WIDTHS = { 14f, 8f, 5f };

        private SharpDX.Direct2D1.SolidColorBrush _dxHudBg;
        private SharpDX.Direct2D1.SolidColorBrush _dxHudBorder;
        private SharpDX.Direct2D1.SolidColorBrush _dxHudText;
        private TextFormat _labelFont;
        private TextFormat _hudFont;
        private TextFormat _markerFont;

        private Timer _invalidateTimer;
        private int _dirty;
        private int _animateWalls;
        private const int INVALIDATE_MS = 50;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "MBO-native DOM liquidity levels with intent classification (GENUINE/SPOOF/ICEBERG/MIGRATORY), state tracking, and confidence scoring. Reads from LiveMBORadar JSON output.";
                Name = "DEEP6 Depth Radar V5";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = false;
                DisplayInDataBox = false;
                ScaleJustification = ScaleJustification.Right;

                WallMinSize = 10;
                WallStaleSec = 90;
                MaxDepthLevels = 40;
                GlowThreshold = 100;
                ShowBids = true;
                ShowAsks = true;
                ShowLabels = true;
                ColorByIntent = true;
                ShowConfidence = true;
                ShowStateMarkers = true;
                ShowQualityScores = true;
                MinQualityScore = 0;
                MinSpoofScore = 0;
                ShowV2Hud = true;

                WallsJsonPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Personal),
                    "NinjaTrader 8", "templates", "DEEP6", "depth_radar_walls.json");

                WallBidBrush = MakeFrozenBrush(Color.FromArgb(220, 43, 140, 255));
                WallAskBrush = MakeFrozenBrush(Color.FromArgb(220, 255, 138, 61));
            }
            else if (State == State.DataLoaded)
            {
                ClearBooks();
                Interlocked.Exchange(ref _dirty, 1);
                Interlocked.Exchange(ref _animateWalls, 0);
                if (_invalidateTimer == null)
                    _invalidateTimer = new Timer(OnInvalidateTick, null, INVALIDATE_MS, INVALIDATE_MS);
                if (_jsonCheckTimer == null)
                    _jsonCheckTimer = new Timer(OnJsonCheck, null, JSON_CHECK_MS, JSON_CHECK_MS);
                Print("[DEEP6DepthRadarV5] DataLoaded — JSON path: " + WallsJsonPath + " exists=" + File.Exists(WallsJsonPath));
            }
            else if (State == State.Historical)
            {
                try { SetZOrder(-1); } catch { }
            }
            else if (State == State.Realtime)
            {
                Print("[DEEP6DepthRadarV5] Realtime — reading Rithmic DOM data from JSON: " + WallsJsonPath);
            }
            else if (State == State.Terminated)
            {
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
                Interlocked.Exchange(ref _jsonReads, 0);
                Interlocked.Exchange(ref _dirty, 1);
            }
        }

        private void OnJsonCheck(object state)
        {
            try
            {
                if (ReadWallsFromJson())
                    Interlocked.Exchange(ref _dirty, 1);
                else
                    RefreshWallTimestamps();
            }
            catch (Exception ex)
            {
                Print("[DEEP6DepthRadarV5] JSON read failed: " + ex.Message);
            }
        }

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
            if (any)
                Interlocked.Exchange(ref _dirty, 1);
        }

        private bool ReadWallsFromJson()
        {
            if (string.IsNullOrWhiteSpace(WallsJsonPath) || !File.Exists(WallsJsonPath))
                return false;

            var fi = new FileInfo(WallsJsonPath);
            if (fi.LastWriteTimeUtc <= _jsonLastModified)
                return false;

            string json = File.ReadAllText(WallsJsonPath);
            _jsonLastModified = fi.LastWriteTimeUtc;

            string schema = ParseJsonString(json, "schema") ?? "legacy";
            string sourceQuality = ParseJsonString(json, "source_quality") ?? "UNKNOWN";
            double payloadMid = ParseJsonDouble(json, "mid_price");
            bool orderIdAvailable = ParseJsonBool(json, "order_id_available");

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
                _l2Bids.Clear();
                _l2Asks.Clear();

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
                    long size = (long)Math.Round(ParseJsonDouble(item, "size"));
                    long maxSize = (long)Math.Round(ParseJsonDouble(item, "max_size"));
                    int refills = (int)Math.Round(ParseJsonDouble(item, "refill_count"));
                    string intent = ParseJsonString(item, "intent") ?? "PASSIVE_REAL";
                    string wallState = ParseJsonString(item, "state") ?? "ESTABLISHED";
                    string classification = ParseJsonString(item, "classification") ?? "GENUINE";
                    double confidence = ParseJsonDouble(item, "confidence");
                    double duration = ParseJsonDouble(item, "duration_sec");
                    double qualityScore = ParseJsonDouble(item, "quality");
                    double spoofScore = ParseJsonDouble(item, "spoof");
                    double icebergScore = ParseJsonDouble(item, "iceberg");
                    double breakRiskScore = ParseJsonDouble(item, "break_risk");
                    string wallSourceQuality = ParseJsonString(item, "source_quality") ?? sourceQuality;
                    string evidence = ParseJsonStringArrayCompact(item, "evidence");

                    if (price <= 0 || string.IsNullOrEmpty(side) || size <= 0)
                        continue;
                    if (qualityScore < MinQualityScore || spoofScore < MinSpoofScore)
                        continue;

                    var dict = string.Equals(side, "ask", StringComparison.OrdinalIgnoreCase) ? _l2Asks : _l2Bids;
                    dict[price] = new L2LevelState
                    {
                        CurrentSize = size,
                        MaxSize = Math.Max(size, maxSize),
                        LastUpdate = utcNow,
                        RefillCount = refills,
                        Intent = NormalizeIntent(intent, classification, refills),
                        WallState = NormalizeState(wallState),
                        Classification = NormalizeClassification(classification, intent, refills),
                        Confidence = Clamp01((float)confidence),
                        DurationSec = (float)Math.Max(0.0, duration),
                        QualityScore = (float)Math.Max(0.0, qualityScore),
                        SpoofScore = (float)Math.Max(0.0, spoofScore),
                        IcebergScore = (float)Math.Max(0.0, icebergScore),
                        BreakRiskScore = (float)Math.Max(0.0, breakRiskScore),
                        SourceQuality = wallSourceQuality,
                        Evidence = evidence
                    };

                    updated = true;
                }

                if ((utcNow - _lastL2Prune).TotalSeconds > 30)
                {
                    PruneL2(_l2Bids);
                    PruneL2(_l2Asks);
                    _lastL2Prune = utcNow;
                }
            }

            if (updated)
            {
                _schema = schema;
                _sourceQuality = sourceQuality;
                _orderIdAvailable = orderIdAvailable;
                _payloadMidPrice = payloadMid;
                Interlocked.Increment(ref _jsonReads);
                Print(string.Format("[DEEP6DepthRadarV5] JSON loaded {0} bids + {1} asks (WallMinSize={2})",
                    _l2Bids.Count, _l2Asks.Count, WallMinSize));
            }

            return updated;
        }

        private static string ParseJsonString(string json, string key)
        {
            int keyIdx = FindJsonKey(json, key);
            if (keyIdx < 0) return null;
            int colonIdx = json.IndexOf(':', keyIdx);
            if (colonIdx < 0) return null;
            int start = colonIdx + 1;
            while (start < json.Length && char.IsWhiteSpace(json[start])) start++;
            if (start >= json.Length || json[start] != '"') return null;
            start++;
            int end = start;
            bool escape = false;
            while (end < json.Length)
            {
                char c = json[end];
                if (escape) { escape = false; end++; continue; }
                if (c == '\\') { escape = true; end++; continue; }
                if (c == '"') break;
                end++;
            }
            if (end >= json.Length) return null;
            return json.Substring(start, end - start);
        }

        private static bool ParseJsonBool(string json, string key)
        {
            int keyIdx = FindJsonKey(json, key);
            if (keyIdx < 0) return false;
            int colonIdx = json.IndexOf(':', keyIdx);
            if (colonIdx < 0) return false;
            int start = colonIdx + 1;
            while (start < json.Length && char.IsWhiteSpace(json[start])) start++;
            return start + 4 <= json.Length && string.Compare(json, start, "true", 0, 4, StringComparison.OrdinalIgnoreCase) == 0;
        }

        private static string ParseJsonStringArrayCompact(string json, string key)
        {
            int keyIdx = FindJsonKey(json, key);
            if (keyIdx < 0) return string.Empty;
            int arrStart = json.IndexOf('[', keyIdx);
            if (arrStart < 0) return string.Empty;
            int arrEnd = json.IndexOf(']', arrStart);
            if (arrEnd < 0) return string.Empty;
            string raw = json.Substring(arrStart + 1, arrEnd - arrStart - 1);
            return raw.Replace("\\\"", string.Empty).Replace("\"", string.Empty).Replace(" ", string.Empty);
        }

        private static double ParseJsonDouble(string json, string key)
        {
            int keyIdx = FindJsonKey(json, key);
            if (keyIdx < 0) return 0.0;
            int colonIdx = json.IndexOf(':', keyIdx);
            if (colonIdx < 0) return 0.0;
            int start = colonIdx + 1;
            while (start < json.Length && char.IsWhiteSpace(json[start])) start++;
            int end = start;
            while (end < json.Length && (char.IsDigit(json[end]) || json[end] == '.' || json[end] == '-' || json[end] == '+' || json[end] == 'e' || json[end] == 'E'))
                end++;
            if (end == start) return 0.0;

            double result;
            if (double.TryParse(json.Substring(start, end - start), NumberStyles.Float, CultureInfo.InvariantCulture, out result))
                return result;
            return 0.0;
        }

        private static int FindJsonKey(string json, string key)
        {
            return json.IndexOf("\"" + key + "\"", StringComparison.Ordinal);
        }

        private void PruneL2(Dictionary<double, L2LevelState> dict)
        {
            var cutoff = DateTime.UtcNow.AddSeconds(-Math.Max(WallStaleSec * 3, 300));
            var stale = new List<double>();
            foreach (var kv in dict)
                if (kv.Value.LastUpdate < cutoff) stale.Add(kv.Key);
            foreach (var k in stale) dict.Remove(k);
        }

        private void OnInvalidateTick(object state)
        {
            bool shouldRefresh = Interlocked.CompareExchange(ref _dirty, 0, 0) == 1 || Interlocked.CompareExchange(ref _animateWalls, 0, 0) == 1;
            if (!shouldRefresh) return;

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

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            _wallBidDx = WallBidBrush.ToDxBrush(RenderTarget);
            _wallAskDx = WallAskBrush.ToDxBrush(RenderTarget);

            Color bidC = ExtractColor(WallBidBrush, Color.FromArgb(220, 43, 140, 255));
            Color askC = ExtractColor(WallAskBrush, Color.FromArgb(220, 255, 138, 61));
            Color passiveC = Color.FromArgb(220, 43, 140, 255);
            Color spoofC = Color.FromArgb(220, 255, 59, 92);
            Color reserveC = Color.FromArgb(220, 0, 212, 170);
            Color migratoryC = Color.FromArgb(220, 255, 179, 71);

            _intentPassiveDx = CreateSolidDxBrush(passiveC);
            _intentSpoofDx = CreateSolidDxBrush(spoofC);
            _intentReserveDx = CreateSolidDxBrush(reserveC);
            _intentMigratoryDx = CreateSolidDxBrush(migratoryC);

            _glowBidDx = CreateGlowArray(bidC);
            _glowAskDx = CreateGlowArray(askC);
            _glowPassiveDx = CreateGlowArray(passiveC);
            _glowSpoofDx = CreateGlowArray(spoofC);
            _glowReserveDx = CreateGlowArray(reserveC);
            _glowMigratoryDx = CreateGlowArray(migratoryC);

            _dxHudBg = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.03f, 0.04f, 0.06f, 0.84f));
            _dxHudBorder = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.16f, 0.19f, 0.24f, 1f));
            _dxHudText = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.96f, 0.97f, 0.98f, 1f));

            _labelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 10f)
            {
                TextAlignment = SharpDX.DirectWrite.TextAlignment.Trailing,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
            _hudFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 10f);
            _markerFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI Symbol", 10f)
            {
                TextAlignment = SharpDX.DirectWrite.TextAlignment.Trailing,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
        }

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

        private struct RenderSummary
        {
            public int BidCount;
            public int AskCount;
            public int GenCount;
            public int SpoofCount;
            public int IceCount;
            public int MigCount;
            public int ConfidenceCount;
            public float ConfidenceSum;
            public float QualitySum;
            public float MaxSpoof;
            public float MaxIceberg;
            public float MaxBreakRisk;
            public bool HasAnimation;

            public void AddIntent(string intent)
            {
                switch (NormalizeIntent(intent, null, 0))
                {
                    case "SPOOF_LIKE":
                        SpoofCount++;
                        break;
                    case "RESERVE_REFRESH":
                        IceCount++;
                        break;
                    case "MIGRATORY":
                        MigCount++;
                        break;
                    default:
                        GenCount++;
                        break;
                }
            }
        }

        private void RenderWalls(ChartScale cs, float panelRight)
        {
            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;
            DateTime fresh = DateTime.UtcNow.AddSeconds(-WallStaleSec);

            List<KeyValuePair<double, L2LevelState>> bidSnap;
            List<KeyValuePair<double, L2LevelState>> askSnap;
            lock (_l2Lock)
            {
                bidSnap = CloneSnapshot(_l2Bids);
                askSnap = CloneSnapshot(_l2Asks);
            }

            var summary = new RenderSummary();
            if (ShowBids)
                summary.BidCount = DrawWallsForSide(cs, bidSnap, true, fresh, minVis, maxVis, panelRight, ref summary);
            if (ShowAsks)
                summary.AskCount = DrawWallsForSide(cs, askSnap, false, fresh, minVis, maxVis, panelRight, ref summary);

            Interlocked.Exchange(ref _animateWalls, summary.HasAnimation ? 1 : 0);
            DrawHud(summary);
        }

        private List<KeyValuePair<double, L2LevelState>> CloneSnapshot(Dictionary<double, L2LevelState> source)
        {
            var snap = new List<KeyValuePair<double, L2LevelState>>(source.Count);
            foreach (var kv in source)
            {
                snap.Add(new KeyValuePair<double, L2LevelState>(kv.Key, new L2LevelState
                {
                    CurrentSize = kv.Value.CurrentSize,
                    MaxSize = kv.Value.MaxSize,
                    LastUpdate = kv.Value.LastUpdate,
                    RefillCount = kv.Value.RefillCount,
                    Intent = kv.Value.Intent,
                    WallState = kv.Value.WallState,
                    Classification = kv.Value.Classification,
                    Confidence = kv.Value.Confidence,
                    DurationSec = kv.Value.DurationSec,
                    QualityScore = kv.Value.QualityScore,
                    SpoofScore = kv.Value.SpoofScore,
                    IcebergScore = kv.Value.IcebergScore,
                    BreakRiskScore = kv.Value.BreakRiskScore,
                    SourceQuality = kv.Value.SourceQuality,
                    Evidence = kv.Value.Evidence
                }));
            }
            return snap;
        }

        private int DrawWallsForSide(
            ChartScale cs,
            List<KeyValuePair<double, L2LevelState>> snap,
            bool isBid,
            DateTime fresh,
            double minVis,
            double maxVis,
            float panelRight,
            ref RenderSummary summary)
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
            int show = Math.Min(walls.Count, Math.Max(1, MaxDepthLevels));

            float lastLabelY = float.MinValue;
            const float LABEL_MIN_GAP = 14f;

            for (int i = 0; i < show; i++)
            {
                double price = walls[i].Key;
                L2LevelState st = walls[i].Value;
                float y = (float)cs.GetYByValue(price);

                SharpDX.Direct2D1.Brush brush = GetRenderBrush(st.Intent, isBid);
                SharpDX.Direct2D1.SolidColorBrush[] glowBrushes = GetGlowBrushes(st.Intent, isBid);
                float alpha = GetStateAlpha(st.WallState);
                float thickness = (float)Math.Min(4.0, 1.5 + (st.MaxSize / (double)WallMinSize) * 0.4);

                if (string.Equals(st.WallState, "DEFENDING", StringComparison.OrdinalIgnoreCase))
                    thickness *= 2.0f;
                else if (string.Equals(st.WallState, "UNDER_ATTACK", StringComparison.OrdinalIgnoreCase))
                {
                    float pulse = 0.80f + 0.20f * (float)Math.Abs(Math.Sin(DateTime.UtcNow.TimeOfDay.TotalMilliseconds / 250.0));
                    alpha *= pulse;
                    thickness *= 1.15f;
                    summary.HasAnimation = true;
                }

                if (st.MaxSize >= GlowThreshold && glowBrushes != null)
                {
                    for (int g = 0; g < glowBrushes.Length; g++)
                        DrawLineWithOpacity(glowBrushes[g], alpha, (float)ChartPanel.X, y, panelRight - 110f, y, GLOW_WIDTHS[g]);
                }

                DrawLineWithOpacity(brush, alpha, (float)ChartPanel.X, y, panelRight - 110f, y, thickness);

                if (ShowLabels)
                {
                    float labelY = y - 8f;
                    if (lastLabelY == float.MinValue || Math.Abs(labelY - lastLabelY) >= LABEL_MIN_GAP)
                    {
                        string label = BuildWallLabel(isBid ? "BID" : "ASK", price, st);
                        using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, label, _labelFont, 220f, 16f))
                            DrawTextLayoutWithOpacity(brush, alpha, panelRight - 224f, labelY, layout);

                        if (ShowStateMarkers)
                        {
                            string marker = GetStateMarker(st.WallState);
                            if (!string.IsNullOrEmpty(marker))
                            {
                                using (var markerLayout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, marker, _markerFont, 24f, 16f))
                                    DrawTextLayoutWithOpacity(brush, alpha, panelRight - 246f, labelY, markerLayout);
                            }
                        }

                        lastLabelY = labelY;
                    }
                }

                summary.AddIntent(st.Intent);
                summary.ConfidenceSum += st.Confidence;
                summary.QualitySum += st.QualityScore;
                if (st.SpoofScore > summary.MaxSpoof) summary.MaxSpoof = st.SpoofScore;
                if (st.IcebergScore > summary.MaxIceberg) summary.MaxIceberg = st.IcebergScore;
                if (st.BreakRiskScore > summary.MaxBreakRisk) summary.MaxBreakRisk = st.BreakRiskScore;
                summary.ConfidenceCount++;
            }

            return show;
        }

        private void DrawHud(RenderSummary summary)
        {
            if (_hudFont == null || _dxHudBg == null || _dxHudText == null) return;

            long reads = Interlocked.Read(ref _jsonReads);
            int totalBids;
            int totalAsks;
            lock (_l2Lock)
            {
                totalBids = _l2Bids.Count;
                totalAsks = _l2Asks.Count;
            }

            float avgConfidence = summary.ConfidenceCount > 0
                ? (summary.ConfidenceSum / summary.ConfidenceCount) * 100f
                : 0f;

            float avgQuality = summary.ConfidenceCount > 0 ? summary.QualitySum / summary.ConfidenceCount : 0f;
            string sourceQuality = _sourceQuality ?? "UNKNOWN";
            string schema = _schema ?? "legacy";
            string dataMode = _orderIdAvailable ? "TRUE-MBO" : sourceQuality;

            string text = ShowV2Hud
                ? string.Format(
                    "DEPTH RADAR V5 [{0}] {1} | vis B:{2} A:{3} | loaded B:{4} A:{5} | GEN:{6} SPF:{7} ICE:{8} MIG:{9} | Q:{10:0} SPF:{11:0} ICE:{12:0} BRK:{13:0} | reads:{14}",
                    dataMode, schema, summary.BidCount, summary.AskCount, totalBids, totalAsks,
                    summary.GenCount, summary.SpoofCount, summary.IceCount, summary.MigCount,
                    avgQuality, summary.MaxSpoof, summary.MaxIceberg, summary.MaxBreakRisk, reads)
                : string.Format(
                    "DEPTH RADAR V5 [JSON] | vis B:{0} A:{1} | loaded B:{2} A:{3} | GEN:{4} SPF:{5} ICE:{6} MIG:{7} | avg conf:{8:0}% | reads:{9}",
                    summary.BidCount, summary.AskCount, totalBids, totalAsks,
                    summary.GenCount, summary.SpoofCount, summary.IceCount, summary.MigCount,
                    avgConfidence, reads);

            float w = ShowV2Hud ? 980f : 760f;
            float h = 20f;
            float x = (float)(ChartPanel.X + ChartPanel.W) - w - 8f;
            float y = (float)ChartPanel.Y + 30f;

            RenderTarget.FillRectangle(new RectangleF(x, y, w, h), _dxHudBg);
            RenderTarget.DrawRectangle(new RectangleF(x, y, w, h), _dxHudBorder, 1f);

            using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, text, _hudFont, w - 10f, h))
                RenderTarget.DrawTextLayout(new Vector2(x + 5f, y + 2f), layout, _dxHudText);
        }

        private string BuildWallLabel(string side, double price, L2LevelState st)
        {
            string suffix = GetIntentAbbreviation(st.Intent, st.Classification, st.RefillCount);
            string confidence = ShowConfidence ? string.Format(" {0:0}%", st.Confidence * 100f) : string.Empty;
            if (ShowQualityScores)
                return string.Format("{0} {1:F2}  {2} {3} Q{4:0} S{5:0} I{6:0}", side, price, st.CurrentSize, suffix, st.QualityScore, st.SpoofScore, st.IcebergScore);
            return string.Format("{0} {1:F2}  {2} {3}{4}", side, price, st.CurrentSize, suffix, confidence);
        }

        private static string GetIntentAbbreviation(string intent, string classification, int refillCount)
        {
            string normalizedIntent = NormalizeIntent(intent, classification, refillCount);
            switch (normalizedIntent)
            {
                case "SPOOF_LIKE":
                    return "SPF";
                case "RESERVE_REFRESH":
                    return "ICE";
                case "MIGRATORY":
                    return "MIG";
                default:
                    return "GEN";
            }
        }

        private static string GetStateMarker(string state)
        {
            switch (NormalizeState(state))
            {
                case "UNDER_ATTACK":
                    return "⚡";
                case "DEFENDING":
                    return "◆";
                case "EXHAUSTED":
                    return "×";
                case "STALE":
                    return "·";
                case "PULLED":
                    return "↓";
                case "CONSUMED":
                    return "◌";
                default:
                    return string.Empty;
            }
        }

        private float GetStateAlpha(string state)
        {
            switch (NormalizeState(state))
            {
                case "STALE":
                    return 0.30f;
                case "EXHAUSTED":
                    return 0.45f;
                case "PULLED":
                case "CONSUMED":
                    return 0.18f;
                default:
                    return 1.0f;
            }
        }

        private SharpDX.Direct2D1.Brush GetRenderBrush(string intent, bool isBid)
        {
            if (!ColorByIntent)
                return isBid ? _wallBidDx : _wallAskDx;

            switch (NormalizeIntent(intent, null, 0))
            {
                case "SPOOF_LIKE":
                    return _intentSpoofDx;
                case "RESERVE_REFRESH":
                    return _intentReserveDx;
                case "MIGRATORY":
                    return _intentMigratoryDx;
                default:
                    return _intentPassiveDx;
            }
        }

        private SharpDX.Direct2D1.SolidColorBrush[] GetGlowBrushes(string intent, bool isBid)
        {
            if (!ColorByIntent)
                return isBid ? _glowBidDx : _glowAskDx;

            switch (NormalizeIntent(intent, null, 0))
            {
                case "SPOOF_LIKE":
                    return _glowSpoofDx;
                case "RESERVE_REFRESH":
                    return _glowReserveDx;
                case "MIGRATORY":
                    return _glowMigratoryDx;
                default:
                    return _glowPassiveDx;
            }
        }

        private void DrawLineWithOpacity(SharpDX.Direct2D1.Brush brush, float alpha, float x1, float y1, float x2, float y2, float width)
        {
            if (brush == null) return;
            float oldOpacity = brush.Opacity;
            brush.Opacity = Clamp01(oldOpacity * alpha);
            try
            {
                RenderTarget.DrawLine(new Vector2(x1, y1), new Vector2(x2, y2), brush, width);
            }
            finally
            {
                brush.Opacity = oldOpacity;
            }
        }

        private void DrawTextLayoutWithOpacity(SharpDX.Direct2D1.Brush brush, float alpha, float x, float y, TextLayout layout)
        {
            if (brush == null || layout == null) return;
            float oldOpacity = brush.Opacity;
            brush.Opacity = Clamp01(oldOpacity * alpha);
            try
            {
                RenderTarget.DrawTextLayout(new Vector2(x, y), layout, brush);
            }
            finally
            {
                brush.Opacity = oldOpacity;
            }
        }

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
            DisposeBrush(ref _intentPassiveDx);
            DisposeBrush(ref _intentSpoofDx);
            DisposeBrush(ref _intentReserveDx);
            DisposeBrush(ref _intentMigratoryDx);
            DisposeGlowArray(ref _glowBidDx);
            DisposeGlowArray(ref _glowAskDx);
            DisposeGlowArray(ref _glowPassiveDx);
            DisposeGlowArray(ref _glowSpoofDx);
            DisposeGlowArray(ref _glowReserveDx);
            DisposeGlowArray(ref _glowMigratoryDx);
            DisposeSolidBrush(ref _dxHudBg);
            DisposeSolidBrush(ref _dxHudBorder);
            DisposeSolidBrush(ref _dxHudText);
            if (_labelFont != null) { _labelFont.Dispose(); _labelFont = null; }
            if (_hudFont != null) { _hudFont.Dispose(); _hudFont = null; }
            if (_markerFont != null) { _markerFont.Dispose(); _markerFont = null; }
        }

        private SharpDX.Direct2D1.SolidColorBrush CreateSolidDxBrush(Color color)
        {
            return new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                new Color4(color.R / 255f, color.G / 255f, color.B / 255f, color.A / 255f));
        }

        private SharpDX.Direct2D1.SolidColorBrush[] CreateGlowArray(Color c)
        {
            var arr = new SharpDX.Direct2D1.SolidColorBrush[3];
            for (int g = 0; g < 3; g++)
            {
                arr[g] = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                    new Color4(c.R / 255f, c.G / 255f, c.B / 255f, GLOW_ALPHAS[g]));
            }
            return arr;
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

        private static float Clamp01(float value)
        {
            if (value < 0f) return 0f;
            if (value > 1f) return 1f;
            return value;
        }

        private static string NormalizeIntent(string intent, string classification, int refillCount)
        {
            string normalized = (intent ?? string.Empty).Trim().ToUpperInvariant();
            if (normalized == "PASSIVE_REAL" || normalized == "SPOOF_LIKE" || normalized == "RESERVE_REFRESH" || normalized == "MIGRATORY")
                return normalized;

            string cls = (classification ?? string.Empty).Trim().ToUpperInvariant();
            if (cls == "SPOOF") return "SPOOF_LIKE";
            if (cls == "ICEBERG") return "RESERVE_REFRESH";
            if (cls == "MIGRATORY") return "MIGRATORY";
            if (refillCount >= 2) return "RESERVE_REFRESH";
            return "PASSIVE_REAL";
        }

        private static string NormalizeState(string state)
        {
            string normalized = (state ?? string.Empty).Trim().ToUpperInvariant();
            switch (normalized)
            {
                case "FRESH":
                case "ESTABLISHED":
                case "UNDER_ATTACK":
                case "DEFENDING":
                case "EXHAUSTED":
                case "STALE":
                case "PULLED":
                case "CONSUMED":
                    return normalized;
                default:
                    return "ESTABLISHED";
            }
        }

        private static string NormalizeClassification(string classification, string intent, int refillCount)
        {
            string normalized = (classification ?? string.Empty).Trim().ToUpperInvariant();
            if (normalized == "GENUINE" || normalized == "SPOOF" || normalized == "ICEBERG")
                return normalized;

            string normalizedIntent = NormalizeIntent(intent, classification, refillCount);
            if (normalizedIntent == "SPOOF_LIKE") return "SPOOF";
            if (normalizedIntent == "RESERVE_REFRESH") return "ICEBERG";
            return "GENUINE";
        }

        #region Properties

        [NinjaScriptProperty]
        [Display(Name = "Walls JSON Path", Order = 0, GroupName = "0. Data Source",
            Description = "Path to JSON file written by live_mbo_radar.py (Rithmic DOM data)")]
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
            Description = "DOM levels to render per side")]
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

        [NinjaScriptProperty]
        [Display(Name = "Color By Intent", Order = 1, GroupName = "Depth Radar V5")]
        public bool ColorByIntent { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Confidence", Order = 2, GroupName = "Depth Radar V5")]
        public bool ShowConfidence { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show State Markers", Order = 3, GroupName = "Depth Radar V5")]
        public bool ShowStateMarkers { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Quality Scores", Order = 4, GroupName = "Depth Radar V5")]
        public bool ShowQualityScores { get; set; }

        [NinjaScriptProperty]
        [Range(0, 100)]
        [Display(Name = "Min Quality Score", Order = 5, GroupName = "Depth Radar V5",
            Description = "Hide walls below this quality score. Leave 0 to show all walls.")]
        public int MinQualityScore { get; set; }

        [NinjaScriptProperty]
        [Range(0, 100)]
        [Display(Name = "Min Spoof Score", Order = 6, GroupName = "Depth Radar V5",
            Description = "Hide walls below this spoof-like score. Leave 0 to show all walls.")]
        public int MinSpoofScore { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show V2 HUD", Order = 7, GroupName = "Depth Radar V5")]
        public bool ShowV2Hud { get; set; }

        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private DEEP6.DEEP6DepthRadarV5[] cacheDEEP6DepthRadarV5;
		public DEEP6.DEEP6DepthRadarV5 DEEP6DepthRadarV5(string wallsJsonPath, int wallMinSize, int wallStaleSec, int maxDepthLevels, int glowThreshold, bool showBids, bool showAsks, bool showLabels, bool colorByIntent, bool showConfidence, bool showStateMarkers, bool showQualityScores, int minQualityScore, int minSpoofScore, bool showV2Hud)
		{
			return DEEP6DepthRadarV5(Input, wallsJsonPath, wallMinSize, wallStaleSec, maxDepthLevels, glowThreshold, showBids, showAsks, showLabels, colorByIntent, showConfidence, showStateMarkers, showQualityScores, minQualityScore, minSpoofScore, showV2Hud);
		}

		public DEEP6.DEEP6DepthRadarV5 DEEP6DepthRadarV5(ISeries<double> input, string wallsJsonPath, int wallMinSize, int wallStaleSec, int maxDepthLevels, int glowThreshold, bool showBids, bool showAsks, bool showLabels, bool colorByIntent, bool showConfidence, bool showStateMarkers, bool showQualityScores, int minQualityScore, int minSpoofScore, bool showV2Hud)
		{
			if (cacheDEEP6DepthRadarV5 != null)
				for (int idx = 0; idx < cacheDEEP6DepthRadarV5.Length; idx++)
					if (cacheDEEP6DepthRadarV5[idx] != null && cacheDEEP6DepthRadarV5[idx].WallsJsonPath == wallsJsonPath && cacheDEEP6DepthRadarV5[idx].WallMinSize == wallMinSize && cacheDEEP6DepthRadarV5[idx].WallStaleSec == wallStaleSec && cacheDEEP6DepthRadarV5[idx].MaxDepthLevels == maxDepthLevels && cacheDEEP6DepthRadarV5[idx].GlowThreshold == glowThreshold && cacheDEEP6DepthRadarV5[idx].ShowBids == showBids && cacheDEEP6DepthRadarV5[idx].ShowAsks == showAsks && cacheDEEP6DepthRadarV5[idx].ShowLabels == showLabels && cacheDEEP6DepthRadarV5[idx].ColorByIntent == colorByIntent && cacheDEEP6DepthRadarV5[idx].ShowConfidence == showConfidence && cacheDEEP6DepthRadarV5[idx].ShowStateMarkers == showStateMarkers && cacheDEEP6DepthRadarV5[idx].ShowQualityScores == showQualityScores && cacheDEEP6DepthRadarV5[idx].MinQualityScore == minQualityScore && cacheDEEP6DepthRadarV5[idx].MinSpoofScore == minSpoofScore && cacheDEEP6DepthRadarV5[idx].ShowV2Hud == showV2Hud && cacheDEEP6DepthRadarV5[idx].EqualsInput(input))
						return cacheDEEP6DepthRadarV5[idx];
			return CacheIndicator<DEEP6.DEEP6DepthRadarV5>(new DEEP6.DEEP6DepthRadarV5(){ WallsJsonPath = wallsJsonPath, WallMinSize = wallMinSize, WallStaleSec = wallStaleSec, MaxDepthLevels = maxDepthLevels, GlowThreshold = glowThreshold, ShowBids = showBids, ShowAsks = showAsks, ShowLabels = showLabels, ColorByIntent = colorByIntent, ShowConfidence = showConfidence, ShowStateMarkers = showStateMarkers, ShowQualityScores = showQualityScores, MinQualityScore = minQualityScore, MinSpoofScore = minSpoofScore, ShowV2Hud = showV2Hud }, input, ref cacheDEEP6DepthRadarV5);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.DEEP6.DEEP6DepthRadarV5 DEEP6DepthRadarV5(string wallsJsonPath, int wallMinSize, int wallStaleSec, int maxDepthLevels, int glowThreshold, bool showBids, bool showAsks, bool showLabels, bool colorByIntent, bool showConfidence, bool showStateMarkers, bool showQualityScores, int minQualityScore, int minSpoofScore, bool showV2Hud)
		{
			return indicator.DEEP6DepthRadarV5(Input, wallsJsonPath, wallMinSize, wallStaleSec, maxDepthLevels, glowThreshold, showBids, showAsks, showLabels, colorByIntent, showConfidence, showStateMarkers, showQualityScores, minQualityScore, minSpoofScore, showV2Hud);
		}

		public Indicators.DEEP6.DEEP6DepthRadarV5 DEEP6DepthRadarV5(ISeries<double> input , string wallsJsonPath, int wallMinSize, int wallStaleSec, int maxDepthLevels, int glowThreshold, bool showBids, bool showAsks, bool showLabels, bool colorByIntent, bool showConfidence, bool showStateMarkers, bool showQualityScores, int minQualityScore, int minSpoofScore, bool showV2Hud)
		{
			return indicator.DEEP6DepthRadarV5(input, wallsJsonPath, wallMinSize, wallStaleSec, maxDepthLevels, glowThreshold, showBids, showAsks, showLabels, colorByIntent, showConfidence, showStateMarkers, showQualityScores, minQualityScore, minSpoofScore, showV2Hud);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.DEEP6.DEEP6DepthRadarV5 DEEP6DepthRadarV5(string wallsJsonPath, int wallMinSize, int wallStaleSec, int maxDepthLevels, int glowThreshold, bool showBids, bool showAsks, bool showLabels, bool colorByIntent, bool showConfidence, bool showStateMarkers, bool showQualityScores, int minQualityScore, int minSpoofScore, bool showV2Hud)
		{
			return indicator.DEEP6DepthRadarV5(Input, wallsJsonPath, wallMinSize, wallStaleSec, maxDepthLevels, glowThreshold, showBids, showAsks, showLabels, colorByIntent, showConfidence, showStateMarkers, showQualityScores, minQualityScore, minSpoofScore, showV2Hud);
		}

		public Indicators.DEEP6.DEEP6DepthRadarV5 DEEP6DepthRadarV5(ISeries<double> input , string wallsJsonPath, int wallMinSize, int wallStaleSec, int maxDepthLevels, int glowThreshold, bool showBids, bool showAsks, bool showLabels, bool colorByIntent, bool showConfidence, bool showStateMarkers, bool showQualityScores, int minQualityScore, int minSpoofScore, bool showV2Hud)
		{
			return indicator.DEEP6DepthRadarV5(input, wallsJsonPath, wallMinSize, wallStaleSec, maxDepthLevels, glowThreshold, showBids, showAsks, showLabels, colorByIntent, showConfidence, showStateMarkers, showQualityScores, minQualityScore, minSpoofScore, showV2Hud);
		}
	}
}

#endregion
