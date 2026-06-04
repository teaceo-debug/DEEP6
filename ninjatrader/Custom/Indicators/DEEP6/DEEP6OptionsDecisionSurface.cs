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
    public class DEEP6OptionsDecisionSurface : Indicator
    {
        private readonly object sync = new object();
        private Timer refreshTimer;
        private OdsPayload payload;
        private OdsAsset asset;
        private string statusText = "Waiting for options_decision_surface_v3.json...";
        private DateTime lastFileWriteUtc = DateTime.MinValue;

        private SharpDX.Direct2D1.Brush dxDefend, dxDefendFill;
        private SharpDX.Direct2D1.Brush dxReject, dxRejectFill;
        private SharpDX.Direct2D1.Brush dxAttract, dxAttractFill;
        private SharpDX.Direct2D1.Brush dxFlip, dxFlipFill;
        private SharpDX.Direct2D1.Brush dxLane;
        private SharpDX.Direct2D1.Brush dxPanel, dxBorder, dxText, dxMuted, dxHalo;
        private TextFormat fontPill, fontPillBold, fontMono, fontTiny;
        private StrokeStyle dashStyleCustom;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 Options Decision Surface V3 — FlashAlpha structure + Massive flow confirmation. Separate side-by-side install.";
                Name = "DEEP6 Options Decision Surface";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                IsSuspendedWhileInactive = true;

                JsonFilePath = @"%USERPROFILE%\Documents\NinjaTrader 8\templates\DEEP6\options_decision_surface_v3.json";
                RefreshSeconds = 2;
                StaleSeconds = 180;
                VeryStaleSeconds = 600;
                MaxRenderedLevels = 12;
                ShowStructuralField = true;
                ShowOpenSpaceLanes = true;
                ShowConfluenceZones = true;
                ShowRegimeStrip = true;
                ShowOffscreenLabels = true;
                DefendBrush = Brushes.Teal;
                RejectBrush = Brushes.IndianRed;
                AttractBrush = Brushes.Gold;
                FlipBrush = Brushes.WhiteSmoke;
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

            dxDefend = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f, 0.82f, 0.73f, 1f));
            dxDefendFill = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f, 0.82f, 0.73f, 0.10f));
            dxReject = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.36f, 0.36f, 1f));
            dxRejectFill = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.36f, 0.36f, 0.10f));
            dxAttract = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.99f, 0.78f, 0.20f, 1f));
            dxAttractFill = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.99f, 0.78f, 0.20f, 0.08f));
            dxFlip = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.92f, 0.94f, 0.98f, 1f));
            dxFlipFill = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.92f, 0.94f, 0.98f, 0.06f));
            dxLane = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.45f, 0.55f, 0.70f, 0.35f));
            dxPanel = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.06f, 0.06f, 0.08f, 0.94f));
            dxBorder = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.22f, 0.22f, 0.28f, 1f));
            dxText = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.94f, 0.95f, 0.97f, 1f));
            dxMuted = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.60f, 0.62f, 0.67f, 1f));
            dxHalo = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f, 0f, 0f, 0.85f));

            fontPill = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI Semibold", 11f);
            fontPillBold = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI Bold", 12f);
            fontMono = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 10f);
            fontTiny = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 9f);

            try
            {
                dashStyleCustom = new StrokeStyle(
                    NinjaTrader.Core.Globals.D2DFactory,
                    new StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Custom },
                    new float[] { 6f, 3f }
                );
            }
            catch { dashStyleCustom = null; }
        }

        private void DisposeDx()
        {
            DisposeBrush(ref dxDefend); DisposeBrush(ref dxDefendFill);
            DisposeBrush(ref dxReject); DisposeBrush(ref dxRejectFill);
            DisposeBrush(ref dxAttract); DisposeBrush(ref dxAttractFill);
            DisposeBrush(ref dxFlip); DisposeBrush(ref dxFlipFill);
            DisposeBrush(ref dxLane); DisposeBrush(ref dxPanel); DisposeBrush(ref dxBorder);
            DisposeBrush(ref dxText); DisposeBrush(ref dxMuted); DisposeBrush(ref dxHalo);
            DisposeText(ref fontPill); DisposeText(ref fontPillBold); DisposeText(ref fontMono); DisposeText(ref fontTiny);
            DisposeStroke(ref dashStyleCustom);
        }

        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush b) { if (b != null) { b.Dispose(); b = null; } }
        private static void DisposeText(ref TextFormat f) { if (f != null) { f.Dispose(); f = null; } }
        private static void DisposeStroke(ref StrokeStyle s) { if (s != null) { s.Dispose(); s = null; } }

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
            OdsPayload next = serializer.Deserialize<OdsPayload>(json);
            OdsAsset match = MatchAsset(next);
            DateTime fileUtc = File.GetLastWriteTimeUtc(path);

            lock (sync)
            {
                payload = next;
                asset = match;
                lastFileWriteUtc = fileUtc;
                statusText = match == null ? "No matching asset for " + GetInstrumentRoot() : BuildStatus(next, match, fileUtc);
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

        private OdsAsset MatchAsset(OdsPayload p)
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

        private string BuildStatus(OdsPayload p, OdsAsset a, DateTime fileUtc)
        {
            int age = AgeSeconds(p != null ? p.generated_at_utc : null, fileUtc);
            string health = a != null && a.provider_health != null ? (a.provider_health.overall ?? "unknown") : "unknown";
            string flow = a != null && a.flow_summary != null ? (a.flow_summary.state ?? "NEUTRAL") : "NEUTRAL";
            if (age > VeryStaleSeconds) return string.Format("VERY STALE {0}s | {1} | FLOW {2}", age, health, flow);
            if (age > StaleSeconds) return string.Format("STALE {0}s | {1} | FLOW {2}", age, health, flow);
            return string.Format("OK {0}s | {1} | FLOW {2} | levels {3}", age, health, flow, a.levels != null ? a.levels.Count : 0);
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            OdsAsset a;
            lock (sync) { a = asset; }
            if (RenderTarget == null || ChartPanel == null || a == null) return;

            var levels = a.levels == null ? new List<OdsLevel>() : a.levels
                .Where(l => l != null && l.price > 0)
                .OrderByDescending(l => l.confidence_score)
                .Take(Math.Max(1, MaxRenderedLevels))
                .ToList();

            DrawStructuralField(levels, chartScale);
            DrawOpenSpaceLanes(a.lanes, chartScale);
            DrawPrimaryLines(levels, chartScale);
            DrawSemanticPills(levels, a, chartScale);
            DrawConfluenceZoneLabels(a.confluence_zones, chartScale);
            DrawRegimeStrip(a);
        }

        private void DrawStructuralField(IList<OdsLevel> levels, ChartScale chartScale)
        {
            if (!ShowStructuralField || levels == null) return;
            float panelX = ChartPanel.X;
            float panelW = ChartPanel.W;
            double minV = chartScale.MinValue;
            double maxV = chartScale.MaxValue;

            foreach (var lvl in levels)
            {
                if (lvl == null || lvl.price <= 0 || lvl.price < minV || lvl.price > maxV) continue;
                var fillBrush = GetBehaviorFillBrush(lvl.behavior_state);
                if (fillBrush == null) continue;
                float cy = chartScale.GetYByValue(lvl.price);
                float bandH = lvl.behavior_state == "ATTRACT" ? 12f : lvl.behavior_state == "FLIP" ? 4f : 8f;
                RenderTarget.FillRectangle(new RectangleF(panelX, cy - bandH / 2f, panelW, bandH), fillBrush);
            }
        }

        private void DrawOpenSpaceLanes(IList<OdsLane> lanes, ChartScale chartScale)
        {
            if (!ShowOpenSpaceLanes || lanes == null || dxLane == null) return;
            float panelX = ChartPanel.X;
            float panelW = ChartPanel.W;
            double minV = chartScale.MinValue;
            double maxV = chartScale.MaxValue;
            foreach (var lane in lanes)
            {
                if (lane == null) continue;
                double hi = Math.Max(lane.start_price, lane.end_price);
                double lo = Math.Min(lane.start_price, lane.end_price);
                if (hi < minV || lo > maxV) continue;
                float yTop = chartScale.GetYByValue(Math.Min(hi, maxV));
                float yBot = chartScale.GetYByValue(Math.Max(lo, minV));
                float h = Math.Abs(yBot - yTop);
                if (h >= 1f) RenderTarget.FillRectangle(new RectangleF(panelX, yTop, panelW, h), dxLane);
            }
        }

        private void DrawPrimaryLines(IList<OdsLevel> levels, ChartScale chartScale)
        {
            if (levels == null) return;
            float x1 = ChartPanel.X + 2f;
            float x2 = ChartPanel.X + ChartPanel.W - 4f;
            double minV = chartScale.MinValue;
            double maxV = chartScale.MaxValue;

            foreach (var lvl in levels)
            {
                if (lvl == null || lvl.price <= 0 || lvl.price < minV || lvl.price > maxV) continue;
                float y = chartScale.GetYByValue(lvl.price);
                var brush = GetBehaviorBrush(lvl.behavior_state);
                if (brush == null) continue;

                float strokeW = lvl.behavior_state == "REJECT" ? 2.5f : lvl.behavior_state == "DEFEND" ? 2.2f : lvl.behavior_state == "FLIP" ? 2.8f : lvl.behavior_state == "ATTRACT" ? 1.8f : 1.4f;
                if (!lvl.is_pinned) strokeW = 1.2f;
                if (lvl.is_pinned) strokeW += 0.4f;
                if (lvl.flow_confirmation_state == "FLOW_CONFIRMED") strokeW += 0.5f;
                if (lvl.flow_confirmation_state == "FLOW_ACCELERATING") strokeW += 0.7f;
                if (lvl.flow_confirmation_state == "FLOW_CONTRADICTED") strokeW = Math.Max(1.0f, strokeW - 0.6f);

                bool useDash = lvl.behavior_state == "ATTRACT" || lvl.lifecycle_state == "flipped" || lvl.flow_confirmation_state == "FLOW_CONTRADICTED";
                if (useDash && dashStyleCustom != null)
                    RenderTarget.DrawLine(new Vector2(x1, y), new Vector2(x2, y), brush, strokeW, dashStyleCustom);
                else
                    RenderTarget.DrawLine(new Vector2(x1, y), new Vector2(x2, y), brush, strokeW);
            }
        }

        private void DrawSemanticPills(IList<OdsLevel> levels, OdsAsset a, ChartScale chartScale)
        {
            if (levels == null) return;
            float pillRight = ChartPanel.X + ChartPanel.W - 8f;
            const float pillW = 236f;
            const float pillH = 22f;
            const float accLW = 3f;
            double futuresSpot = a != null ? a.futures_spot : 0;
            double minV = chartScale.MinValue;
            double maxV = chartScale.MaxValue;

            var sorted = levels.Where(l => l != null && l.price > 0).OrderByDescending(l => l.price).ToList();
            int topSlots = 0;
            int botSlots = 0;
            float lastY = float.MinValue;

            foreach (var lvl in sorted)
            {
                float pillY;
                string prefix = "";
                if (lvl.price > maxV)
                {
                    if (!ShowOffscreenLabels) continue;
                    pillY = ChartPanel.Y + 4f + topSlots * 24f;
                    topSlots++;
                    prefix = "▲ ";
                }
                else if (lvl.price < minV)
                {
                    if (!ShowOffscreenLabels) continue;
                    pillY = ChartPanel.Y + ChartPanel.H - 24f - botSlots * 24f;
                    botSlots++;
                    prefix = "▼ ";
                }
                else
                {
                    pillY = chartScale.GetYByValue(lvl.price) - pillH / 2f;
                    if (lastY != float.MinValue && pillY - lastY < 22f) pillY = lastY + 22f;
                    lastY = pillY;
                }

                float pillX = pillRight - pillW;
                var accentBrush = GetBehaviorBrush(lvl.behavior_state) ?? dxText;
                float liveDistPts = futuresSpot > 0 ? (float)(lvl.price - futuresSpot) : (float)lvl.distance_points;
                string flowTag = FlowTag(lvl.flow_confirmation_state);
                string row1 = string.Format("{0}{1}  {2}", prefix, lvl.behavior_state ?? "", FormatSource(lvl.structural_source ?? lvl.role ?? ""));
                string row2 = string.Format("{0:+0;-0;0}  {1}  {2}", (int)liveDistPts, lvl.tier ?? "", flowTag);

                if (dxPanel != null) RenderTarget.FillRectangle(new RectangleF(pillX, pillY, pillW, pillH), dxPanel);
                if (dxBorder != null) RenderTarget.DrawRectangle(new RectangleF(pillX, pillY, pillW, pillH), dxBorder, 1f);
                if (accentBrush != null) RenderTarget.FillRectangle(new RectangleF(pillX, pillY, accLW, pillH), accentBrush);

                float textX = pillX + accLW + 4f;
                float row1Y = pillY + 2f;
                float row2Y = pillY + pillH / 2f;
                float textW = pillW - accLW - 6f;
                float halfH = pillH / 2f;

                if (fontPillBold != null && dxHalo != null)
                {
                    using (var tl1 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, row1, fontPillBold, textW, halfH))
                    {
                        RenderTarget.DrawTextLayout(new Vector2(textX - 1, row1Y - 1), tl1, dxHalo);
                        RenderTarget.DrawTextLayout(new Vector2(textX + 1, row1Y + 1), tl1, dxHalo);
                        RenderTarget.DrawTextLayout(new Vector2(textX, row1Y), tl1, accentBrush ?? dxText);
                    }
                }
                if (fontMono != null && dxHalo != null)
                {
                    using (var tl2 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, row2, fontMono, textW, halfH))
                    {
                        RenderTarget.DrawTextLayout(new Vector2(textX - 1, row2Y - 1), tl2, dxHalo);
                        RenderTarget.DrawTextLayout(new Vector2(textX + 1, row2Y + 1), tl2, dxHalo);
                        RenderTarget.DrawTextLayout(new Vector2(textX, row2Y), tl2, dxMuted ?? dxText);
                    }
                }
            }
        }

        private void DrawConfluenceZoneLabels(IList<OdsConfluenceZone> zones, ChartScale chartScale)
        {
            if (!ShowConfluenceZones || zones == null) return;
            float x2 = ChartPanel.X + ChartPanel.W - 8f;
            double minV = chartScale.MinValue;
            double maxV = chartScale.MaxValue;
            foreach (var zone in zones)
            {
                if (zone == null || zone.zone_high < minV || zone.zone_low > maxV) continue;
                float yHi = chartScale.GetYByValue(Math.Min(zone.zone_high, maxV));
                float yLo = chartScale.GetYByValue(Math.Max(zone.zone_low, minV));
                var brush = GetBehaviorBrush(zone.dominant_behavior) ?? dxMuted;
                RenderTarget.DrawLine(new Vector2(x2 - 14f, yHi), new Vector2(x2, yHi), brush, 1.5f);
                RenderTarget.DrawLine(new Vector2(x2 - 14f, yLo), new Vector2(x2, yLo), brush, 1.5f);
                RenderTarget.DrawLine(new Vector2(x2 - 14f, yHi), new Vector2(x2 - 14f, yLo), brush, 1.0f);

                string zoneLabel = string.Format("{0}  {1}", zone.label ?? zone.dominant_behavior, zone.tier ?? "");
                string rangeLabel = string.Format("{0:0}–{1:0}", zone.zone_low, zone.zone_high);
                float labelX = x2 - 236f;
                float midY = (yHi + yLo) / 2f - 10f;
                if (fontTiny != null)
                {
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, zoneLabel, fontTiny, 220f, 14f))
                        RenderTarget.DrawTextLayout(new Vector2(labelX, midY), tl, brush);
                    using (var tl2 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, rangeLabel, fontMono ?? fontTiny, 220f, 14f))
                        RenderTarget.DrawTextLayout(new Vector2(labelX, midY + 14f), tl2, dxMuted ?? dxText);
                }
            }
        }

        private void DrawRegimeStrip(OdsAsset a)
        {
            if (!ShowRegimeStrip || a == null || a.regime_summary == null) return;
            string regime = a.regime_summary.regime_state ?? a.regime_summary.regime_label ?? "UNKNOWN";
            string flow = a.flow_summary != null ? (a.flow_summary.state ?? "NEUTRAL") : "NEUTRAL";
            string flipLabel = a.regime_summary.flip_price.HasValue ? string.Format("FLIP {0:+0;-0;0}", a.regime_summary.flip_price.Value - a.futures_spot) : "FLIP N/A";
            string content = string.Format("{0} | {1} | {2}", regime, flipLabel, flow);
            float maxW = 360f;
            float stripH = 18f;
            float stripY = ChartPanel.Y + 4f;
            float stripX = ChartPanel.X + ChartPanel.W - maxW - 8f;
            if (dxPanel != null) RenderTarget.FillRectangle(new RectangleF(stripX, stripY, maxW, stripH), dxPanel);
            if (fontTiny != null && dxMuted != null)
            {
                using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, content, fontTiny, maxW - 8f, stripH))
                    RenderTarget.DrawTextLayout(new Vector2(stripX + 4f, stripY + 3f), tl, dxMuted);
            }
        }

        private SharpDX.Direct2D1.Brush GetBehaviorBrush(string state)
        {
            if (state == null) return dxText;
            switch (state)
            {
                case "DEFEND": return dxDefend;
                case "REJECT": return dxReject;
                case "ATTRACT": return dxAttract;
                case "FLIP": return dxFlip;
                case "OPEN_SPACE": return dxLane;
                default: return dxText;
            }
        }

        private SharpDX.Direct2D1.Brush GetBehaviorFillBrush(string state)
        {
            if (state == null) return null;
            switch (state)
            {
                case "DEFEND": return dxDefendFill;
                case "REJECT": return dxRejectFill;
                case "ATTRACT": return dxAttractFill;
                case "FLIP": return dxFlipFill;
                default: return null;
            }
        }

        private static string FormatSource(string src)
        {
            if (string.IsNullOrEmpty(src)) return "";
            if (src == "put_wall") return "PUT WALL";
            if (src == "call_wall") return "CALL WALL";
            if (src == "hvl") return "HVL";
            if (src == "gamma_flip") return "GAMMA";
            if (src == "zero_dte_magnet") return "0DTE MAGNET";
            if (src.StartsWith("pos_gex")) return "+GEX";
            if (src.StartsWith("neg_gex")) return "-GEX";
            return src.ToUpperInvariant().Replace("_", " ");
        }

        private static string FlowTag(string state)
        {
            if (string.IsNullOrEmpty(state)) return "";
            if (state == "FLOW_CONFIRMED") return "FLOW";
            if (state == "FLOW_CONTRADICTED") return "CONTRA";
            if (state == "FLOW_ACCELERATING") return "ACCEL";
            if (state == "FLOW_FADED") return "FADED";
            return "";
        }

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
        [Display(Name = "Max Rendered Levels", Order = 5, GroupName = "1. Data")]
        public int MaxRenderedLevels { get; set; }

        [Display(Name = "Show Structural Field", Order = 6, GroupName = "2. Display")]
        public bool ShowStructuralField { get; set; }
        [Display(Name = "Show Open Space Lanes", Order = 7, GroupName = "2. Display")]
        public bool ShowOpenSpaceLanes { get; set; }
        [Display(Name = "Show Confluence Zones", Order = 8, GroupName = "2. Display")]
        public bool ShowConfluenceZones { get; set; }
        [Display(Name = "Show Regime Strip", Order = 9, GroupName = "2. Display")]
        public bool ShowRegimeStrip { get; set; }
        [Display(Name = "Show Offscreen Labels", Order = 10, GroupName = "2. Display")]
        public bool ShowOffscreenLabels { get; set; }

        [XmlIgnore]
        [Display(Name = "Defend Color", Order = 11, GroupName = "3. Behavior Colors")]
        public Brush DefendBrush { get; set; }
        [Browsable(false)]
        public string DefendBrushSerialize { get { return Serialize.BrushToString(DefendBrush); } set { DefendBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Reject Color", Order = 12, GroupName = "3. Behavior Colors")]
        public Brush RejectBrush { get; set; }
        [Browsable(false)]
        public string RejectBrushSerialize { get { return Serialize.BrushToString(RejectBrush); } set { RejectBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Attract Color", Order = 13, GroupName = "3. Behavior Colors")]
        public Brush AttractBrush { get; set; }
        [Browsable(false)]
        public string AttractBrushSerialize { get { return Serialize.BrushToString(AttractBrush); } set { AttractBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Flip Color", Order = 14, GroupName = "3. Behavior Colors")]
        public Brush FlipBrush { get; set; }
        [Browsable(false)]
        public string FlipBrushSerialize { get { return Serialize.BrushToString(FlipBrush); } set { FlipBrush = Serialize.StringToBrush(value); } }
    }

    public class OdsPayload { public string schema { get; set; } public string service { get; set; } public string service_version { get; set; } public string generated_at_utc { get; set; } public int sequence { get; set; } public List<OdsAsset> assets { get; set; } public List<string> errors { get; set; } }
    public class OdsAsset { public string asset_id { get; set; } public string futures_root { get; set; } public string underlying { get; set; } public double underlying_spot { get; set; } public string futures_symbol { get; set; } public double futures_spot { get; set; } public OdsMapping mapping { get; set; } public OdsFreshness freshness { get; set; } public OdsProviderHealth provider_health { get; set; } public OdsFlowSummary flow_summary { get; set; } public OdsRegime regime_summary { get; set; } public List<OdsLevel> levels { get; set; } public List<OdsLevel> levels_list { get; set; } public List<OdsConfluenceZone> confluence_zones { get; set; } public List<OdsLane> lanes { get; set; } public string chain_error { get; set; } public bool stale { get; set; } public int age_seconds { get; set; } public string as_of_utc { get; set; } }
    public class OdsMapping { public string method { get; set; } public double ratio { get; set; } public string source { get; set; } public double source_spot { get; set; } public double target_spot { get; set; } public string computed_at_utc { get; set; } }
    public class OdsFreshness { public int payload_age_seconds { get; set; } public int chain_snapshot_age_seconds { get; set; } public int spot_age_seconds { get; set; } public int futures_spot_age_seconds { get; set; } public int websocket_age_seconds { get; set; } public int compute_duration_ms { get; set; } public string last_successful_refresh_utc { get; set; } public string health_state { get; set; } }
    public class OdsProviderState { public bool healthy { get; set; } public string state { get; set; } }
    public class OdsProviderHealth { public OdsProviderState flashalpha { get; set; } public OdsProviderState massive { get; set; } public string overall { get; set; } }
    public class OdsFlowSummary { public double signed_premium_5m { get; set; } public double signed_premium_15m { get; set; } public int net_direction { get; set; } public double z_score { get; set; } public string state { get; set; } }
    public class OdsRegime { public string regime_state { get; set; } public string regime_label { get; set; } public string dealer_state { get; set; } public double pin_risk { get; set; } public string vanna_state { get; set; } public string charm_state { get; set; } public double confidence_score { get; set; } public double net_gex { get; set; } public double net_dex { get; set; } public double net_vex { get; set; } public double net_chex { get; set; } public string flow_state { get; set; } public double? flip_price { get; set; } public double? magnet_price { get; set; } }
    public class OdsLevel { public string id { get; set; } public string key { get; set; } public string role { get; set; } public string label { get; set; } public string symbol { get; set; } public string source_underlying { get; set; } public double source_price { get; set; } public double source_strike { get; set; } public double mapped_price { get; set; } public double price { get; set; } public double gex { get; set; } public double value { get; set; } public int abs_gex_rank { get; set; } public double distance_from_spot_source { get; set; } public double distance_from_futures_spot { get; set; } public double distance_points { get; set; } public bool is_pinned { get; set; } public string behavior_state { get; set; } public string structural_source { get; set; } public double confidence_score { get; set; } public double confidence { get; set; } public string tier { get; set; } public string lifecycle_state { get; set; } public string action_hint { get; set; } public string selected_because { get; set; } public string contradicted_because { get; set; } public string flow_confirmation_state { get; set; } public List<string> provider_sources { get; set; } public string confluence_group { get; set; } public string acceleration_context { get; set; } }
    public class OdsConfluenceZone { public string zone_id { get; set; } public double zone_high { get; set; } public double zone_low { get; set; } public string dominant_behavior { get; set; } public string dominant_source { get; set; } public double confidence_score { get; set; } public string tier { get; set; } public List<string> member_level_ids { get; set; } public string action_hint { get; set; } public string label { get; set; } }
    public class OdsLane { public double start_price { get; set; } public double end_price { get; set; } public double width_pts { get; set; } public string label { get; set; } public double confidence_score { get; set; } public string direction_bias { get; set; } public string trigger_condition { get; set; } }
}
