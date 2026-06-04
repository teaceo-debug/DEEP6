#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    // Brand-new local-file-only Massive GEX map.  API keys stay in scripts/massive_gex_map_service.py.
    public class DEEP6MassiveGexMap : Indicator
    {
        private readonly object sync = new object();
        private Timer refreshTimer;
        private MassiveGexMapPayload payload;
        private MassiveGexMapAsset asset;
        private string statusText = "Waiting for massive_gex_map.json...";
        private DateTime lastFileWriteUtc = DateTime.MinValue;
        private int lastSequence = -1;

        private SharpDX.Direct2D1.Brush dxText, dxMuted, dxPanel, dxBorder, dxGreen, dxRed, dxGold, dxBlue, dxPurple, dxAmber;
        private TextFormat fontSmall, fontNormal, fontBold;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 Massive GEX Map — local JSON renderer for the new Massive REST/WebSocket sidecar. No API key in NinjaTrader.";
                Name = "DEEP6 Massive GEX Map";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                IsSuspendedWhileInactive = true;

                JsonFilePath = @"%USERPROFILE%\Documents\NinjaTrader 8\templates\DEEP6\massive_gex_map.json";
                RefreshSeconds = 2;
                StaleSeconds = 180;
                VeryStaleSeconds = 600;
                MaxRenderedLevels = 9;
                ShowHud = true;
                ShowOffscreenLabels = true;
                ShowSourceMetadata = true;
                LineOpacity = 90;
                GammaFlipBrush = Brushes.Gold;
                CallWallBrush = Brushes.IndianRed;
                PutWallBrush = Brushes.LimeGreen;
                HvlBrush = Brushes.DeepSkyBlue;
                PositiveNodeBrush = Brushes.DodgerBlue;
                NegativeNodeBrush = Brushes.MediumPurple;
                NeutralBrush = Brushes.Gainsboro;
            }
            else if (State == State.Historical)
            {
                refreshTimer = new Timer(ReadSnapshotSafe, null, 500, Math.Max(1, RefreshSeconds) * 1000);
            }
            else if (State == State.Terminated)
            {
                if (refreshTimer != null) { refreshTimer.Dispose(); refreshTimer = null; }
                DisposeDx();
            }
        }

        protected override void OnBarUpdate() { }

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;
            dxText = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.95f, 0.95f, 0.97f, 1f));
            dxMuted = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.68f, 0.68f, 0.72f, 1f));
            dxPanel = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.06f, 0.06f, 0.08f, 0.92f));
            dxBorder = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.28f, 0.28f, 0.34f, 1f));
            dxGreen = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.18f, 0.84f, 0.46f, 1f));
            dxRed = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.95f, 0.30f, 0.30f, 1f));
            dxGold = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.98f, 0.78f, 0.25f, 1f));
            dxBlue = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.33f, 0.67f, 1.00f, 1f));
            dxPurple = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.78f, 0.48f, 1.00f, 1f));
            dxAmber = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(1.00f, 0.55f, 0.16f, 1f));
            fontSmall = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 11f);
            fontNormal = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI Semibold", 13f);
            fontBold = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI Bold", 14f);
        }

        private void DisposeDx()
        {
            DisposeText(ref fontSmall); DisposeText(ref fontNormal); DisposeText(ref fontBold);
            DisposeBrush(ref dxText); DisposeBrush(ref dxMuted); DisposeBrush(ref dxPanel); DisposeBrush(ref dxBorder);
            DisposeBrush(ref dxGreen); DisposeBrush(ref dxRed); DisposeBrush(ref dxGold); DisposeBrush(ref dxBlue); DisposeBrush(ref dxPurple); DisposeBrush(ref dxAmber);
        }
        private static void DisposeText(ref TextFormat f) { if (f != null) { f.Dispose(); f = null; } }
        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush b) { if (b != null) { b.Dispose(); b = null; } }

        private void ReadSnapshotSafe(object state)
        {
            try { ReadSnapshot(); }
            catch (Exception ex)
            {
                lock (sync) statusText = "Read error: " + ex.Message;
                RefreshChart();
            }
        }

        private void ReadSnapshot()
        {
            string path = ExpandJsonPath(JsonFilePath);
            if (!File.Exists(path))
            {
                lock (sync) statusText = "Missing JSON: " + path;
                RefreshChart();
                return;
            }
            string json;
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var sr = new StreamReader(fs)) json = sr.ReadToEnd();
            var serializer = new JavaScriptSerializer { MaxJsonLength = 8 * 1024 * 1024 };
            MassiveGexMapPayload next = serializer.Deserialize<MassiveGexMapPayload>(json);
            MassiveGexMapAsset match = MatchAsset(next);
            DateTime fileUtc = File.GetLastWriteTimeUtc(path);
            lock (sync)
            {
                payload = next;
                asset = match;
                lastFileWriteUtc = fileUtc;
                if (match == null) statusText = "No matching asset for " + GetInstrumentRoot();
                else statusText = BuildStatus(next, match, fileUtc);
                if (next != null) lastSequence = next.sequence;
            }
            RefreshChart();
        }

        private void RefreshChart()
        {
            if (ChartControl != null)
                ChartControl.Dispatcher.BeginInvoke(new Action(() => ChartControl.InvalidateVisual()));
        }

        private string ExpandJsonPath(string raw)
        {
            string docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            string profile = Directory.GetParent(docs) != null ? Directory.GetParent(docs).FullName : docs;
            return (raw ?? string.Empty).Replace("%USERPROFILE%", profile).Replace("%USERPROFILE%\\Documents", docs);
        }

        private MassiveGexMapAsset MatchAsset(MassiveGexMapPayload p)
        {
            if (p == null || p.assets == null || p.assets.Count == 0) return null;
            string root = NormalizeRoot(GetInstrumentRoot());
            foreach (var a in p.assets)
                if (a != null && string.Equals(NormalizeRoot(a.futures_root), root, StringComparison.OrdinalIgnoreCase)) return a;
            return p.assets[0];
        }

        private string NormalizeRoot(string root)
        {
            root = (root ?? string.Empty).ToUpperInvariant();
            if (root == "MNQ") return "NQ";
            if (root == "MES") return "ES";
            return root;
        }

        private string GetInstrumentRoot()
        {
            string full = Instrument != null && Instrument.MasterInstrument != null ? Instrument.MasterInstrument.Name : string.Empty;
            if (string.IsNullOrEmpty(full)) return string.Empty;
            int i = full.IndexOf(' ');
            return (i > 0 ? full.Substring(0, i) : full).ToUpperInvariant();
        }

        private int AgeSeconds(string utc, DateTime fallbackFileUtc)
        {
            DateTime dt;
            if (!string.IsNullOrEmpty(utc) && DateTime.TryParse(utc, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out dt))
                return Math.Max(0, (int)(DateTime.UtcNow - dt).TotalSeconds);
            if (fallbackFileUtc != DateTime.MinValue)
                return Math.Max(0, (int)(DateTime.UtcNow - fallbackFileUtc).TotalSeconds);
            return int.MaxValue;
        }

        private string BuildStatus(MassiveGexMapPayload p, MassiveGexMapAsset a, DateTime fileUtc)
        {
            int age = AgeSeconds(p != null ? p.generated_at_utc : null, fileUtc);
            string ws = a.websocket != null ? a.websocket.state : "no_ws";
            int msgs = a.websocket != null ? a.websocket.message_count : 0;
            if (string.IsNullOrEmpty(a.chain_error) == false)
                return "CHAIN ERROR: " + a.chain_error;
            if (age > VeryStaleSeconds) return string.Format("VERY STALE {0}s | WS {1} | msgs {2}", age, ws, msgs);
            if (age > StaleSeconds) return string.Format("STALE {0}s | WS {1} | msgs {2}", age, ws, msgs);
            return string.Format("OK {0}s | WS {1} | msgs {2} | levels {3}", age, ws, msgs, a.levels != null ? a.levels.Count : 0);
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            MassiveGexMapAsset a; MassiveGexMapPayload p; string status; DateTime fileUtc;
            lock (sync) { a = asset; p = payload; status = statusText; fileUtc = lastFileWriteUtc; }
            if (RenderTarget == null || ChartPanel == null) return;
            if (a == null)
            {
                if (ShowHud) DrawHud("DEEP6 Massive GEX Map", status, null, p, fileUtc);
                return;
            }
            DrawLevels(a, chartScale);
            if (ShowHud) DrawHud("DEEP6 Massive GEX Map", status, a, p, fileUtc);
        }

        private void DrawLevels(MassiveGexMapAsset a, ChartScale chartScale)
        {
            if (a.levels == null || a.levels.Count == 0) return;
            double min = chartScale.MinValue;
            double max = chartScale.MaxValue;
            var levels = a.levels.Where(l => l != null && l.price > 0).OrderBy(l => Math.Abs(l.distance_from_futures_spot)).Take(Math.Max(1, MaxRenderedLevels)).ToList();
            int topSlots = 0, bottomSlots = 0;
            foreach (var l in levels)
            {
                SharpDX.Direct2D1.Brush brush = BrushFor(l);
                float y;
                string prefix = string.Empty;
                bool offscreen = false;
                if (l.price > max)
                {
                    if (!ShowOffscreenLabels) continue;
                    y = ChartPanel.Y + 22 + topSlots * 18; topSlots++; prefix = "UP "; offscreen = true;
                }
                else if (l.price < min)
                {
                    if (!ShowOffscreenLabels) continue;
                    y = ChartPanel.Y + ChartPanel.H - 24 - bottomSlots * 18; bottomSlots++; prefix = "DN "; offscreen = true;
                }
                else y = chartScale.GetYByValue(l.price);

                float x1 = ChartPanel.X + 2;
                float x2 = ChartPanel.X + ChartPanel.W - 4;
                var stroke = offscreen ? 1.0f : (l.is_pinned ? 2.2f : 1.3f);
                if (!offscreen) RenderTarget.DrawLine(new Vector2(x1, y), new Vector2(x2, y), brush, stroke);
                else RenderTarget.DrawLine(new Vector2(x2 - 145, y), new Vector2(x2 - 8, y), brush, stroke);

                string txt = string.Format(CultureInfo.InvariantCulture, "{0}{1} {2:0.00}", prefix, CleanLabel(l.label), l.price);
                if (ShowSourceMetadata)
                    txt += string.Format(CultureInfo.InvariantCulture, " | {0} {1:0.##} | {2:+0;-0;0}p", a.underlying, l.source_strike, l.distance_from_futures_spot);
                using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, txt, fontSmall ?? fontNormal, 420, 18))
                    RenderTarget.DrawTextLayout(new Vector2(x2 - layout.Metrics.Width - 8, y - 9), layout, brush);
            }
        }

        private string CleanLabel(string label)
        {
            return string.IsNullOrEmpty(label) ? "GEX" : label.Replace("GAMMA ", "G").Replace("WALL", "WALL");
        }

        private SharpDX.Direct2D1.Brush BrushFor(MassiveGexMapLevel l)
        {
            string role = (l.role ?? l.key ?? string.Empty).ToLowerInvariant();
            if (role.Contains("flip")) return dxGold ?? dxText;
            if (role.Contains("call")) return dxRed ?? dxText;
            if (role.Contains("put")) return dxGreen ?? dxText;
            if (role.Contains("hvl")) return dxBlue ?? dxText;
            if (role.Contains("neg")) return dxPurple ?? dxText;
            if (role.Contains("pos")) return dxBlue ?? dxText;
            return dxText;
        }

        private void DrawHud(string title, string status, MassiveGexMapAsset a, MassiveGexMapPayload p, DateTime fileUtc)
        {
            float x = ChartPanel.X + 12;
            float y = ChartPanel.Y + 28;
            float w = 455;
            float h = a == null ? 62 : 118;
            RenderTarget.FillRectangle(new RectangleF(x, y, w, h), dxPanel ?? dxText);
            RenderTarget.DrawRectangle(new RectangleF(x, y, w, h), dxBorder ?? dxText, 1f);
            using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, title, fontBold, w - 18, 20)) RenderTarget.DrawTextLayout(new Vector2(x + 9, y + 7), tl, dxText);
            SharpDX.Direct2D1.Brush sb = status != null && status.StartsWith("OK") ? dxGreen : status != null && status.StartsWith("STALE") ? dxAmber : dxRed;
            using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, status ?? "", fontSmall, w - 18, 20)) RenderTarget.DrawTextLayout(new Vector2(x + 9, y + 31), tl, sb ?? dxText);
            if (a == null) return;
            string line1 = string.Format(CultureInfo.InvariantCulture, "{0}->{1} ratio {2:0.000000} | spot {3:0.00} -> {4:0.00}", a.underlying, a.futures_root, a.mapping != null ? a.mapping.ratio : 0, a.underlying_spot, a.futures_spot);
            string line2 = string.Format(CultureInfo.InvariantCulture, "seq {0} | schema {1} | file age {2}s", p != null ? p.sequence : 0, p != null ? p.schema : "", fileUtc == DateTime.MinValue ? -1 : (int)(DateTime.UtcNow - fileUtc).TotalSeconds);
            string line3 = a.websocket == null ? "ws: none" : string.Format(CultureInfo.InvariantCulture, "ws {0} auth {1} msgs {2} trades {3} err {4}", a.websocket.state, a.websocket.authenticated, a.websocket.message_count, a.websocket.trade_count, Trunc(a.websocket.last_error, 48));
            string line4 = a.chain == null ? "chain: none" : string.Format(CultureInfo.InvariantCulture, "chain contracts {0} used {1} strikes {2} pages {3}", a.chain.snapshot_contracts, a.chain.used_contracts, a.chain.strike_count, a.chain.pages);
            DrawHudLine(line1, x + 9, y + 54, dxMuted);
            DrawHudLine(line2, x + 9, y + 70, dxMuted);
            DrawHudLine(line3, x + 9, y + 86, dxMuted);
            DrawHudLine(line4, x + 9, y + 102, dxMuted);
        }

        private void DrawHudLine(string s, float x, float y, SharpDX.Direct2D1.Brush b)
        {
            using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, s ?? "", fontSmall, 435, 16)) RenderTarget.DrawTextLayout(new Vector2(x, y), tl, b ?? dxText);
        }
        private string Trunc(string s, int n) { return string.IsNullOrEmpty(s) ? "" : (s.Length <= n ? s : s.Substring(0, n)); }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "JSON File Path", Order = 1, GroupName = "1. Data")]
        public string JsonFilePath { get; set; }
        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Refresh Seconds", Order = 2, GroupName = "1. Data")]
        public int RefreshSeconds { get; set; }
        [NinjaScriptProperty]
        [Range(5, 3600)]
        [Display(Name = "Stale Seconds", Order = 3, GroupName = "1. Data")]
        public int StaleSeconds { get; set; }
        [NinjaScriptProperty]
        [Range(10, 7200)]
        [Display(Name = "Very Stale Seconds", Order = 4, GroupName = "1. Data")]
        public int VeryStaleSeconds { get; set; }
        [NinjaScriptProperty]
        [Range(1, 30)]
        [Display(Name = "Max Rendered Levels", Order = 5, GroupName = "2. Visual")]
        public int MaxRenderedLevels { get; set; }
        [Display(Name = "Show HUD", Order = 6, GroupName = "2. Visual")]
        public bool ShowHud { get; set; }
        [Display(Name = "Show Offscreen Labels", Order = 7, GroupName = "2. Visual")]
        public bool ShowOffscreenLabels { get; set; }
        [Display(Name = "Show Source Metadata", Order = 8, GroupName = "2. Visual")]
        public bool ShowSourceMetadata { get; set; }
        [Range(10, 100)]
        [Display(Name = "Line Opacity", Order = 9, GroupName = "2. Visual")]
        public int LineOpacity { get; set; }
        [XmlIgnore] [Display(Name = "Gamma Flip", Order = 10, GroupName = "3. Colors")] public Brush GammaFlipBrush { get; set; }
        [Browsable(false)] public string GammaFlipBrushSerialize { get { return Serialize.BrushToString(GammaFlipBrush); } set { GammaFlipBrush = Serialize.StringToBrush(value); } }
        [XmlIgnore] [Display(Name = "Call Wall", Order = 11, GroupName = "3. Colors")] public Brush CallWallBrush { get; set; }
        [Browsable(false)] public string CallWallBrushSerialize { get { return Serialize.BrushToString(CallWallBrush); } set { CallWallBrush = Serialize.StringToBrush(value); } }
        [XmlIgnore] [Display(Name = "Put Wall", Order = 12, GroupName = "3. Colors")] public Brush PutWallBrush { get; set; }
        [Browsable(false)] public string PutWallBrushSerialize { get { return Serialize.BrushToString(PutWallBrush); } set { PutWallBrush = Serialize.StringToBrush(value); } }
        [XmlIgnore] [Display(Name = "HVL", Order = 13, GroupName = "3. Colors")] public Brush HvlBrush { get; set; }
        [Browsable(false)] public string HvlBrushSerialize { get { return Serialize.BrushToString(HvlBrush); } set { HvlBrush = Serialize.StringToBrush(value); } }
        [XmlIgnore] [Display(Name = "+GEX Node", Order = 14, GroupName = "3. Colors")] public Brush PositiveNodeBrush { get; set; }
        [Browsable(false)] public string PositiveNodeBrushSerialize { get { return Serialize.BrushToString(PositiveNodeBrush); } set { PositiveNodeBrush = Serialize.StringToBrush(value); } }
        [XmlIgnore] [Display(Name = "-GEX Node", Order = 15, GroupName = "3. Colors")] public Brush NegativeNodeBrush { get; set; }
        [Browsable(false)] public string NegativeNodeBrushSerialize { get { return Serialize.BrushToString(NegativeNodeBrush); } set { NegativeNodeBrush = Serialize.StringToBrush(value); } }
        [XmlIgnore] [Display(Name = "Neutral", Order = 16, GroupName = "3. Colors")] public Brush NeutralBrush { get; set; }
        [Browsable(false)] public string NeutralBrushSerialize { get { return Serialize.BrushToString(NeutralBrush); } set { NeutralBrush = Serialize.StringToBrush(value); } }
        #endregion
    }

    public class MassiveGexMapPayload { public string schema { get; set; } public string service { get; set; } public string service_version { get; set; } public string generated_at_utc { get; set; } public int sequence { get; set; } public List<MassiveGexMapAsset> assets { get; set; } public List<string> errors { get; set; } }
    public class MassiveGexMapAsset { public string asset_id { get; set; } public string futures_root { get; set; } public string underlying { get; set; } public double underlying_spot { get; set; } public string futures_symbol { get; set; } public double futures_spot { get; set; } public MassiveGexMapMapping mapping { get; set; } public MassiveGexMapFreshness freshness { get; set; } public MassiveGexMapWebSocket websocket { get; set; } public MassiveGexMapChain chain { get; set; } public MassiveGexMapSelection selection { get; set; } public List<MassiveGexMapLevel> levels { get; set; } public List<MassiveGexMapLevel> levels_list { get; set; } public string chain_error { get; set; } public bool stale { get; set; } public int age_seconds { get; set; } public string as_of_utc { get; set; } }
    public class MassiveGexMapMapping { public string method { get; set; } public double ratio { get; set; } public string source { get; set; } public double source_spot { get; set; } public double target_spot { get; set; } public string computed_at_utc { get; set; } }
    public class MassiveGexMapFreshness { public int generated_age_s { get; set; } public int chain_snapshot_age_s { get; set; } public int spot_age_s { get; set; } public int futures_spot_age_s { get; set; } public int trade_stream_age_s { get; set; } public bool stale { get; set; } public bool very_stale { get; set; } }
    public class MassiveGexMapWebSocket { public string url_type { get; set; } public string endpoint { get; set; } public string state { get; set; } public bool authenticated { get; set; } public bool subscribed { get; set; } public int subscribed_contracts { get; set; } public string subscription_params { get; set; } public string last_message_utc { get; set; } public string last_trade_utc { get; set; } public int message_count { get; set; } public int trade_count { get; set; } public int reconnect_count { get; set; } public string last_error { get; set; } }
    public class MassiveGexMapChain { public int snapshot_contracts { get; set; } public int used_contracts { get; set; } public int strike_count { get; set; } public int pages { get; set; } public int max_dte { get; set; } public string snapshot_source { get; set; } public string chain_error { get; set; } }
    public class MassiveGexMapSelection { public bool spot_centered { get; set; } public string center_source { get; set; } public double window_pct { get; set; } public double max_above_pct { get; set; } public double max_below_pct { get; set; } public int candidate_strikes { get; set; } public int max_levels { get; set; } public string algorithm { get; set; } }
    public class MassiveGexMapLevel { public string id { get; set; } public string key { get; set; } public string role { get; set; } public string symbol { get; set; } public string label { get; set; } public string action { get; set; } public string side { get; set; } public string source_underlying { get; set; } public double source_strike { get; set; } public double source_price { get; set; } public double mapped_price { get; set; } public double price { get; set; } public double gex { get; set; } public double value { get; set; } public int abs_gex_rank { get; set; } public double distance_from_spot_source { get; set; } public double distance_from_futures_spot { get; set; } public bool is_pinned { get; set; } public double confidence { get; set; } }
}
