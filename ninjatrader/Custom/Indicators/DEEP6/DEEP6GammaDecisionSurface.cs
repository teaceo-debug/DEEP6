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
    public class DEEP6GammaDecisionSurface : Indicator
    {
        #region Fields
        private readonly object sync = new object();
        private Timer refreshTimer;
        private GdsPayload payload;
        private GdsAsset asset;
        private string statusText = "Waiting for massive_gex_map_v2.json...";
        private DateTime lastFileWriteUtc = DateTime.MinValue;
        private int lastSequence = -1;
        private Dictionary<string, double> liveLevelDistances = new Dictionary<string, double>();

        // B2: Behavior brushes
        private SharpDX.Direct2D1.Brush dxDefend, dxDefendFill;
        private SharpDX.Direct2D1.Brush dxReject, dxRejectFill;
        private SharpDX.Direct2D1.Brush dxAttract, dxAttractFill;
        private SharpDX.Direct2D1.Brush dxFlip, dxFlipFill;
        private SharpDX.Direct2D1.Brush dxLane;
        // B2: UI brushes
        private SharpDX.Direct2D1.Brush dxPanel, dxBorder, dxText, dxMuted, dxHalo, dxStaleDim;
        // B2: Fonts
        private TextFormat fontPill, fontPillBold, fontMono, fontTiny;
        // B4: Cached dash style for ATTRACT / flipped lines
        private SharpDX.Direct2D1.StrokeStyle dashStyleCustom;
        #endregion

        #region Lifecycle
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description          = "DEEP6 Gamma Decision Surface V2 — behavior-first semantic GEX map. Levels communicate trader intent: DEFEND / REJECT / ATTRACT / FLIP / OPEN SPACE. No API key in NinjaTrader.";
                Name                 = "DEEP6 Gamma Decision Surface";
                Calculate            = Calculate.OnEachTick;
                IsOverlay            = true;
                IsSuspendedWhileInactive = true;

                JsonFilePath         = @"%USERPROFILE%\Documents\NinjaTrader 8\templates\DEEP6\massive_gex_map_v2.json";
                RefreshSeconds       = 2;
                StaleSeconds         = 180;
                VeryStaleSeconds     = 600;
                MaxRenderedLevels    = 12;
                ShowStructuralField  = true;
                ShowOpenSpaceLanes   = true;
                ShowConfluenceZones  = true;
                ShowRegimeStrip      = true;
                ShowOffscreenLabels  = true;
                DefendBrush          = Brushes.Teal;
                RejectBrush          = Brushes.IndianRed;
                AttractBrush         = Brushes.Gold;
                FlipBrush            = Brushes.WhiteSmoke;
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

            // Behavior solid + fill brushes
            dxDefend      = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f,    0.82f, 0.73f, 1f));
            dxDefendFill  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f,    0.82f, 0.73f, 0.10f));
            dxReject      = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(1f,    0.36f, 0.36f, 1f));
            dxRejectFill  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(1f,    0.36f, 0.36f, 0.10f));
            dxAttract     = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.99f, 0.78f, 0.20f, 1f));
            dxAttractFill = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.99f, 0.78f, 0.20f, 0.08f));
            dxFlip        = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.92f, 0.94f, 0.98f, 1f));
            dxFlipFill    = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.92f, 0.94f, 0.98f, 0.06f));
            dxLane        = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.45f, 0.55f, 0.70f, 0.35f));

            // UI brushes
            dxPanel    = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.06f, 0.06f, 0.08f, 0.94f));
            dxBorder   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.22f, 0.22f, 0.28f, 1f));
            dxText     = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.94f, 0.95f, 0.97f, 1f));
            dxMuted    = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.60f, 0.62f, 0.67f, 1f));
            dxHalo     = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f,    0f,    0f,    0.85f));
            dxStaleDim = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f,    0f,    0f,    0.35f));

            // Fonts
            fontPill     = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI Semibold", 11f);
            fontPillBold = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI Bold", 12f);
            fontMono     = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 10f);
            fontTiny     = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 9f);

            // Cached dash stroke style for ATTRACT / flipped lines
            try
            {
                dashStyleCustom = new SharpDX.Direct2D1.StrokeStyle(
                    NinjaTrader.Core.Globals.D2DFactory,
                    new SharpDX.Direct2D1.StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Custom },
                    new float[] { 6f, 3f });
            }
            catch { dashStyleCustom = null; }
        }
        #endregion

        #region DX Disposal
        private void DisposeDx()
        {
            DisposeBrush(ref dxDefend);  DisposeBrush(ref dxDefendFill);
            DisposeBrush(ref dxReject);  DisposeBrush(ref dxRejectFill);
            DisposeBrush(ref dxAttract); DisposeBrush(ref dxAttractFill);
            DisposeBrush(ref dxFlip);    DisposeBrush(ref dxFlipFill);
            DisposeBrush(ref dxLane);
            DisposeBrush(ref dxPanel);   DisposeBrush(ref dxBorder);  DisposeBrush(ref dxText);
            DisposeBrush(ref dxMuted);   DisposeBrush(ref dxHalo);    DisposeBrush(ref dxStaleDim);
            DisposeText(ref fontPill);   DisposeText(ref fontPillBold);
            DisposeText(ref fontMono);   DisposeText(ref fontTiny);
            DisposeStroke(ref dashStyleCustom);
        }

        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush b) { if (b != null) { b.Dispose(); b = null; } }
        private static void DisposeText(ref TextFormat f)               { if (f != null) { f.Dispose(); f = null; } }
        private static void DisposeStroke(ref SharpDX.Direct2D1.StrokeStyle s) { if (s != null) { s.Dispose(); s = null; } }
        #endregion

        #region Data Loading
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
            GdsPayload next = serializer.Deserialize<GdsPayload>(json);
            GdsAsset match = MatchAsset(next);
            DateTime fileUtc = File.GetLastWriteTimeUtc(path);

            var newDists = new Dictionary<string, double>();
            if (match != null && match.levels != null)
                foreach (var lvl in match.levels)
                    if (lvl != null && lvl.id != null)
                        newDists[lvl.id] = lvl.price - match.futures_spot;

            lock (sync)
            {
                payload = next;
                asset = match;
                lastFileWriteUtc = fileUtc;
                liveLevelDistances = newDists;
                statusText = match == null ? "No matching asset for " + GetInstrumentRoot()
                                           : BuildStatus(next, match, fileUtc);
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

        private GdsAsset MatchAsset(GdsPayload p)
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

        private string BuildStatus(GdsPayload p, GdsAsset a, DateTime fileUtc)
        {
            int age = AgeSeconds(p != null ? p.generated_at_utc : null, fileUtc);
            string ws = a.websocket != null ? a.websocket.state : "no_ws";
            int msgs = a.websocket != null ? a.websocket.message_count : 0;
            if (!string.IsNullOrEmpty(a.chain_error))
                return "CHAIN ERROR: " + a.chain_error;
            if (age > VeryStaleSeconds) return string.Format("VERY STALE {0}s | WS {1} | msgs {2}", age, ws, msgs);
            if (age > StaleSeconds) return string.Format("STALE {0}s | WS {1} | msgs {2}", age, ws, msgs);
            return string.Format("OK {0}s | WS {1} | msgs {2} | levels {3}", age, ws, msgs, a.levels != null ? a.levels.Count : 0);
        }
        #endregion

        #region Rendering
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            GdsAsset a; GdsPayload p;
            lock (sync) { a = asset; p = payload; }
            if (RenderTarget == null || ChartPanel == null) return;
            if (a == null) return;

            var levels = a.levels;
            if (levels == null || levels.Count == 0) return;
            var topN = levels
                .Where(l => l != null && l.price > 0)
                .OrderByDescending(l => l.confidence_score)
                .Take(Math.Max(1, MaxRenderedLevels))
                .ToList();

            // Layer 2: structural zone fills
            DrawStructuralField(topN, chartScale);
            // Layer 3: open space lanes
            DrawOpenSpaceLanes(a.lanes, chartScale);
            // Layer 3: primary level lines
            DrawPrimaryLines(topN, chartScale);
            // Layer 4: semantic pills (right-edge labels)
            DrawSemanticPills(topN, a, chartScale);
            // Layer 4: confluence zone brackets
            DrawConfluenceZoneLabels(a.confluence_zones, chartScale);
            // Layer 5: regime strip
            DrawRegimeStrip(a);
        }

        // B3 — Layer 2: full-width zone fills behind price action
        private void DrawStructuralField(IList<GdsLevel> levels, ChartScale chartScale)
        {
            if (levels == null || !ShowStructuralField) return;
            float panelX = ChartPanel.X;
            float panelW = ChartPanel.W;
            double minV = chartScale.MinValue;
            double maxV = chartScale.MaxValue;

            foreach (var lvl in levels)
            {
                if (lvl == null || lvl.price <= 0) continue;
                if (lvl.price < minV || lvl.price > maxV) continue;

                SharpDX.Direct2D1.Brush fillBrush = GetBehaviorFillBrush(lvl.behavior_state);
                if (fillBrush == null) continue;

                float cy = chartScale.GetYByValue(lvl.price);
                float bandH = lvl.behavior_state == "ATTRACT" ? 12f : lvl.behavior_state == "FLIP" ? 4f : 8f;
                float bandY = cy - bandH / 2f;

                RenderTarget.FillRectangle(new RectangleF(panelX, bandY, panelW, bandH), fillBrush);
            }
        }

        // B4 — Layer 3: horizontal level lines with behavior-driven styling
        private void DrawPrimaryLines(IList<GdsLevel> levels, ChartScale chartScale)
        {
            if (levels == null) return;
            float x1 = ChartPanel.X + 2f;
            float x2 = ChartPanel.X + ChartPanel.W - 4f;
            double minV = chartScale.MinValue;
            double maxV = chartScale.MaxValue;

            foreach (var lvl in levels)
            {
                if (lvl == null || lvl.price <= 0) continue;
                if (lvl.price < minV || lvl.price > maxV) continue;

                float y = chartScale.GetYByValue(lvl.price);
                SharpDX.Direct2D1.Brush brush = GetBehaviorBrush(lvl.behavior_state);
                if (brush == null) continue;

                // Line weight by behavior
                float strokeW = lvl.behavior_state == "REJECT" ? 2.5f
                    : lvl.behavior_state == "DEFEND" ? 2.2f
                    : lvl.behavior_state == "FLIP"   ? 2.8f
                    : lvl.behavior_state == "ATTRACT" ? 1.8f
                    : 1.4f;

                // Secondary levels thinner; pinned levels thicker
                if (!lvl.is_pinned) strokeW = 1.2f;
                if (lvl.is_pinned)  strokeW += 0.4f;

                // ATTRACT or flipped lifecycle: use dashed line
                bool useDash = lvl.behavior_state == "ATTRACT" || lvl.lifecycle_state == "flipped";
                if (useDash && dashStyleCustom != null)
                    RenderTarget.DrawLine(new Vector2(x1, y), new Vector2(x2, y), brush, strokeW, dashStyleCustom);
                else
                    RenderTarget.DrawLine(new Vector2(x1, y), new Vector2(x2, y), brush, strokeW);
            }
        }

        // B5 — Layer 3: open-space corridor fills
        private void DrawOpenSpaceLanes(IList<GdsLane> lanes, ChartScale chartScale)
        {
            if (lanes == null || !ShowOpenSpaceLanes || dxLane == null) return;
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

                float yTop  = chartScale.GetYByValue(Math.Min(hi, maxV));
                float yBot  = chartScale.GetYByValue(Math.Max(lo, minV));
                float laneH = Math.Abs(yBot - yTop);
                if (laneH < 1f) continue;

                RenderTarget.FillRectangle(new RectangleF(panelX, yTop, panelW, laneH), dxLane);
            }
        }

        // B6 — Layer 4: right-edge semantic pill labels with halo text
        private void DrawSemanticPills(IList<GdsLevel> levels, GdsAsset a, ChartScale chartScale)
        {
            if (levels == null) return;
            float pillRight = ChartPanel.X + ChartPanel.W - 8f;
            const float pillW = 220f;
            const float pillH = 20f;
            const float accLW = 3f;

            double futuresSpot = a != null ? a.futures_spot : 0;
            double minV = chartScale.MinValue;
            double maxV = chartScale.MaxValue;

            var sorted = levels
                .Where(l => l != null && l.price > 0)
                .OrderByDescending(l => l.price)
                .ToList();

            int topSlots = 0;
            int botSlots = 0;
            float lastY = float.MinValue;

            foreach (var lvl in sorted)
            {
                float pillY;
                string distPrefix = "";

                if (lvl.price > maxV)
                {
                    if (!ShowOffscreenLabels) continue;
                    pillY = ChartPanel.Y + 4f + topSlots * 24f;
                    topSlots++;
                    distPrefix = "\u25B2 ";  // ▲
                }
                else if (lvl.price < minV)
                {
                    if (!ShowOffscreenLabels) continue;
                    pillY = ChartPanel.Y + ChartPanel.H - 24f - botSlots * 24f;
                    botSlots++;
                    distPrefix = "\u25BC ";  // ▼
                }
                else
                {
                    pillY = chartScale.GetYByValue(lvl.price) - pillH / 2f;
                    if (lastY != float.MinValue && pillY - lastY < 22f)
                        pillY = lastY + 22f;
                    lastY = pillY;
                }

                float pillX = pillRight - pillW;
                SharpDX.Direct2D1.Brush accentBrush = GetBehaviorBrush(lvl.behavior_state) ?? dxText;

                // B9: live distance from futures spot
                float liveDistPts = futuresSpot > 0
                    ? (float)(lvl.price - futuresSpot)
                    : (float)lvl.distance_points;

                // Pill background
                if (dxPanel != null)
                    RenderTarget.FillRectangle(new RectangleF(pillX, pillY, pillW, pillH), dxPanel);
                // Left accent strip
                if (accentBrush != null)
                    RenderTarget.FillRectangle(new RectangleF(pillX, pillY, accLW, pillH), accentBrush);

                // Row 1: behavior + source
                string sourcePart = FormatSource(lvl.structural_source ?? lvl.role ?? "");
                string row1 = string.Format("{0}  {1}", lvl.behavior_state ?? "", sourcePart);
                // Row 2: distance + tier
                string row2 = string.Format("{0}{1:+0;-0;0}  {2}", distPrefix, (int)liveDistPts, lvl.tier ?? "");

                float textX = pillX + accLW + 4f;
                float row1Y = pillY + 2f;
                float row2Y = pillY + pillH / 2f;
                float textW = pillW - accLW - 6f;
                float halfH = pillH / 2f;

                // Halo pass + primary text
                TextFormat f1 = fontPillBold ?? fontPill;
                TextFormat f2 = fontMono ?? fontPill;
                if (f1 != null && dxHalo != null)
                {
                    using (var tl1 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, row1, f1, textW, halfH))
                    {
                        RenderTarget.DrawTextLayout(new Vector2(textX - 1, row1Y - 1), tl1, dxHalo);
                        RenderTarget.DrawTextLayout(new Vector2(textX + 1, row1Y + 1), tl1, dxHalo);
                        RenderTarget.DrawTextLayout(new Vector2(textX, row1Y), tl1, accentBrush ?? dxText);
                    }
                }
                if (f2 != null && dxHalo != null)
                {
                    using (var tl2 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, row2, f2, textW, halfH))
                    {
                        RenderTarget.DrawTextLayout(new Vector2(textX - 1, row2Y - 1), tl2, dxHalo);
                        RenderTarget.DrawTextLayout(new Vector2(textX + 1, row2Y + 1), tl2, dxHalo);
                        RenderTarget.DrawTextLayout(new Vector2(textX, row2Y), tl2, dxMuted ?? dxText);
                    }
                }
            }
        }

        // B7 — Layer 4: confluence zone bracket labels
        private void DrawConfluenceZoneLabels(IList<GdsConfluenceZone> zones, ChartScale chartScale)
        {
            if (zones == null || !ShowConfluenceZones) return;
            float x2 = ChartPanel.X + ChartPanel.W - 8f;
            double minV = chartScale.MinValue;
            double maxV = chartScale.MaxValue;

            foreach (var zone in zones)
            {
                if (zone == null) continue;
                if (zone.zone_high < minV || zone.zone_low > maxV) continue;

                float yHi = chartScale.GetYByValue(Math.Min(zone.zone_high, maxV));
                float yLo = chartScale.GetYByValue(Math.Max(zone.zone_low, minV));
                SharpDX.Direct2D1.Brush brush = GetBehaviorBrush(zone.dominant_behavior) ?? dxMuted;

                // Bracket marks
                RenderTarget.DrawLine(new Vector2(x2 - 14f, yHi), new Vector2(x2, yHi), brush, 1.5f);
                RenderTarget.DrawLine(new Vector2(x2 - 14f, yLo), new Vector2(x2, yLo), brush, 1.5f);
                RenderTarget.DrawLine(new Vector2(x2 - 14f, yHi), new Vector2(x2 - 14f, yLo), brush, 1.0f);

                // Label
                string zoneLabel = string.Format("{0}  {1}", zone.label ?? zone.dominant_behavior, zone.tier ?? "");
                string rangeLabel = string.Format("{0:0}\u2013{1:0}", zone.zone_low, zone.zone_high);
                float labelX = x2 - 224f;
                float midY = (yHi + yLo) / 2f - 10f;

                TextFormat fLabel = fontTiny ?? fontPill;
                TextFormat fRange = fontMono ?? fontTiny ?? fontPill;
                if (fLabel != null && brush != null)
                {
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, zoneLabel, fLabel, 220f, 14f))
                        RenderTarget.DrawTextLayout(new Vector2(labelX, midY), tl, brush);
                }
                if (fRange != null && dxMuted != null)
                {
                    using (var tl2 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, rangeLabel, fRange, 220f, 14f))
                        RenderTarget.DrawTextLayout(new Vector2(labelX, midY + 14f), tl2, dxMuted);
                }
            }
        }

        // B8 — Layer 5: compact regime strip at top-right
        private void DrawRegimeStrip(GdsAsset a)
        {
            if (!ShowRegimeStrip || a == null || a.regime_summary == null) return;
            var r = a.regime_summary;
            var fa = a.flashalpha;

            // Build regime label — prefer FlashAlpha regime string if live
            string regimeLabel;
            if (fa != null && fa.health == "live" && !string.IsNullOrEmpty(fa.regime))
            {
                if (fa.regime.Contains("negative"))      regimeLabel = "NEG GEX";
                else if (fa.regime.Contains("positive")) regimeLabel = "POS GEX";
                else                                     regimeLabel = "NEUTRAL";
            }
            else
            {
                regimeLabel = r.dominant_regime ?? "NEUTRAL";
            }

            // Flip distance
            string flipLabel = r.flip_price.HasValue
                ? string.Format("FLIP {0:+0;-0;0}", r.flip_price.Value - a.futures_spot)
                : "FLIP N/A";

            // FlashAlpha VEX/CHEX/0DTE tags (only when live)
            string faContext = "";
            if (fa != null && fa.health == "live")
            {
                string vexTag  = fa.vex_direction  == "bullish" ? "VEX\u2191BULL"
                               : fa.vex_direction  == "bearish" ? "VEX\u2193BEAR"
                               : "VEX~";
                string chexTag = fa.chex_direction == "bullish" ? "CHEX\u2191BULL"
                               : fa.chex_direction == "bearish" ? "CHEX\u2193BEAR"
                               : "CHEX~";
                string zdteTag = fa.zero_dte_pct > 0.01
                    ? string.Format("0DTE {0:F0}%", fa.zero_dte_pct * 100.0)
                    : "";

                var parts = new List<string> { vexTag, chexTag };
                if (!string.IsNullOrEmpty(zdteTag)) parts.Add(zdteTag);
                faContext = " | " + string.Join(" | ", parts);
            }

            string content = string.Format("{0} | {1}{2}", regimeLabel, flipLabel, faContext);

            float maxW   = 440f;
            float stripH = 18f;
            float stripY = ChartPanel.Y + 4f;
            float stripX = ChartPanel.X + ChartPanel.W - maxW - 8f;

            if (dxPanel != null)
                RenderTarget.FillRectangle(new RectangleF(stripX, stripY, maxW, stripH), dxPanel);

            TextFormat fStrip = fontTiny ?? fontPill;
            if (dxMuted != null && fStrip != null)
            {
                using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, content, fStrip, maxW - 8f, stripH))
                    RenderTarget.DrawTextLayout(new Vector2(stripX + 4f, stripY + 3f), tl, dxMuted);
            }
        }
        #endregion

        #region Helpers
        private SharpDX.Direct2D1.Brush GetBehaviorBrush(string state)
        {
            if (state == null) return dxText;
            switch (state)
            {
                case "DEFEND":     return dxDefend;
                case "REJECT":     return dxReject;
                case "ATTRACT":    return dxAttract;
                case "FLIP":       return dxFlip;
                case "OPEN_SPACE": return dxLane;
                default:           return dxText;
            }
        }

        private SharpDX.Direct2D1.Brush GetBehaviorFillBrush(string state)
        {
            if (state == null) return null;
            switch (state)
            {
                case "DEFEND":  return dxDefendFill;
                case "REJECT":  return dxRejectFill;
                case "ATTRACT": return dxAttractFill;
                case "FLIP":    return dxFlipFill;
                default:        return null;
            }
        }

        private static string FormatSource(string src)
        {
            if (string.IsNullOrEmpty(src)) return "";
            if (src == "put_wall")    return "PUT WALL";
            if (src == "call_wall")   return "CALL WALL";
            if (src == "hvl")         return "HVL";
            if (src == "gamma_flip")  return "FLIP";
            if (src.StartsWith("pos_gex")) return "+GEX";
            if (src.StartsWith("neg_gex")) return "-GEX";
            return src.ToUpperInvariant();
        }
        #endregion

        #region Properties
        // Group 1 — Data
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

        // Group 2 — Display
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

        // Group 3 — Behavior Colors
        [XmlIgnore]
        [Display(Name = "Defend Color", Order = 11, GroupName = "3. Behavior Colors")]
        public Brush DefendBrush { get; set; }
        [Browsable(false)]
        public string DefendBrushSerialize
        {
            get { return Serialize.BrushToString(DefendBrush); }
            set { DefendBrush = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Reject Color", Order = 12, GroupName = "3. Behavior Colors")]
        public Brush RejectBrush { get; set; }
        [Browsable(false)]
        public string RejectBrushSerialize
        {
            get { return Serialize.BrushToString(RejectBrush); }
            set { RejectBrush = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Attract Color", Order = 13, GroupName = "3. Behavior Colors")]
        public Brush AttractBrush { get; set; }
        [Browsable(false)]
        public string AttractBrushSerialize
        {
            get { return Serialize.BrushToString(AttractBrush); }
            set { AttractBrush = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Flip Color", Order = 14, GroupName = "3. Behavior Colors")]
        public Brush FlipBrush { get; set; }
        [Browsable(false)]
        public string FlipBrushSerialize
        {
            get { return Serialize.BrushToString(FlipBrush); }
            set { FlipBrush = Serialize.StringToBrush(value); }
        }
        #endregion
    }

    #region DTOs
    public class GdsPayload { public string schema { get; set; } public string service { get; set; } public string service_version { get; set; } public string generated_at_utc { get; set; } public int sequence { get; set; } public List<GdsAsset> assets { get; set; } public List<string> errors { get; set; } }

    public class GdsAsset { public string asset_id { get; set; } public string futures_root { get; set; } public string underlying { get; set; } public double underlying_spot { get; set; } public string futures_symbol { get; set; } public double futures_spot { get; set; } public GdsMapping mapping { get; set; } public GdsFreshness freshness { get; set; } public GdsWebSocket websocket { get; set; } public GdsChain chain { get; set; } public GdsSelection selection { get; set; } public List<GdsLevel> levels { get; set; } public List<GdsLevel> levels_list { get; set; } public List<GdsConfluenceZone> confluence_zones { get; set; } public List<GdsLane> lanes { get; set; } public GdsRegime regime_summary { get; set; } public GdsFlashAlpha flashalpha { get; set; } public string chain_error { get; set; } public bool stale { get; set; } public int age_seconds { get; set; } public string as_of_utc { get; set; } }

    public class GdsMapping { public string method { get; set; } public double ratio { get; set; } public string source { get; set; } public double source_spot { get; set; } public double target_spot { get; set; } public string computed_at_utc { get; set; } }

    public class GdsFreshness { public int payload_age_seconds { get; set; } public int chain_snapshot_age_seconds { get; set; } public int spot_age_seconds { get; set; } public int futures_spot_age_seconds { get; set; } public int websocket_age_seconds { get; set; } public int compute_duration_ms { get; set; } public string last_successful_refresh_utc { get; set; } public string health_state { get; set; } }

    public class GdsWebSocket { public string url_type { get; set; } public string endpoint { get; set; } public string state { get; set; } public bool authenticated { get; set; } public bool subscribed { get; set; } public int subscribed_contracts { get; set; } public string subscription_params { get; set; } public string last_message_utc { get; set; } public string last_trade_utc { get; set; } public int message_count { get; set; } public int trade_count { get; set; } public int reconnect_count { get; set; } public string last_error { get; set; } }

    public class GdsChain { public int snapshot_contracts { get; set; } public int used_contracts { get; set; } public int strike_count { get; set; } public int pages { get; set; } public int max_dte { get; set; } public string snapshot_source { get; set; } public string chain_error { get; set; } }

    public class GdsSelection { public bool spot_centered { get; set; } public string center_source { get; set; } public double window_pct { get; set; } public double max_above_pct { get; set; } public double max_below_pct { get; set; } public int candidate_strikes { get; set; } public int near_candidate_strikes { get; set; } public int max_levels { get; set; } public string algorithm { get; set; } }

    public class GdsLevel { public string id { get; set; } public string key { get; set; } public string role { get; set; } public string symbol { get; set; } public string label { get; set; } public string action { get; set; } public string side { get; set; } public string source_underlying { get; set; } public double source_strike { get; set; } public double source_price { get; set; } public double mapped_price { get; set; } public double price { get; set; } public double gex { get; set; } public double value { get; set; } public int abs_gex_rank { get; set; } public double distance_from_spot_source { get; set; } public double distance_from_futures_spot { get; set; } public bool is_pinned { get; set; } public double confidence { get; set; } public string behavior_state { get; set; } public string structural_source { get; set; } public double confidence_score { get; set; } public string selected_because { get; set; } public double distance_points { get; set; } public string tier { get; set; } public string lifecycle_state { get; set; } public string action_hint { get; set; } public string confluence_group { get; set; } public string acceleration_context { get; set; } }

    public class GdsConfluenceZone { public string zone_id { get; set; } public double zone_high { get; set; } public double zone_low { get; set; } public string dominant_behavior { get; set; } public string dominant_source { get; set; } public double confidence_score { get; set; } public string tier { get; set; } public List<string> member_level_ids { get; set; } public string action_hint { get; set; } public string label { get; set; } }

    public class GdsLane { public double start_price { get; set; } public double end_price { get; set; } public double width_pts { get; set; } }

    public class GdsRegime { public double net_gex { get; set; } public string dominant_regime { get; set; } public double? flip_price { get; set; } public double? magnet_price { get; set; } }

    public class GdsFlashAlpha
    {
        public string  regime          { get; set; }
        public double? gamma_flip_qqq  { get; set; }
        public double? gamma_flip_nq   { get; set; }
        public double? call_wall_qqq   { get; set; }
        public double? call_wall_nq    { get; set; }
        public double? put_wall_qqq    { get; set; }
        public double? put_wall_nq     { get; set; }
        public double  net_gex         { get; set; }
        public double  net_dex         { get; set; }
        public double  net_vex         { get; set; }
        public double  net_chex        { get; set; }
        public string  vex_direction   { get; set; }
        public string  chex_direction  { get; set; }
        public double  zero_dte_pct    { get; set; }
        public double  zero_dte_pct_raw { get; set; }
        public double  zero_dte_net_gex { get; set; }
        public double? zero_dte_magnet_qqq { get; set; }
        public double? zero_dte_magnet_nq  { get; set; }
        public string  as_of_utc       { get; set; }
        public string  health          { get; set; }
    }
    #endregion
}
