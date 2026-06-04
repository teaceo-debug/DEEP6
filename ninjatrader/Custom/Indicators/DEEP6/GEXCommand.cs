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
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class GEXCommand : Indicator
    {
        private readonly object snapshotLock = new object();
        private Timer refreshTimer;
        private AssetSnapshot activeAsset;
        private string statusText = "Waiting for JSON...";

        private SharpDX.Direct2D1.Brush dxText;
        private SharpDX.Direct2D1.Brush dxMuted;
        private SharpDX.Direct2D1.Brush dxPanel;
        private SharpDX.Direct2D1.Brush dxPanel2;
        private SharpDX.Direct2D1.Brush dxBorder;
        private SharpDX.Direct2D1.Brush dxGreen;
        private SharpDX.Direct2D1.Brush dxRed;
        private SharpDX.Direct2D1.Brush dxGold;
        private SharpDX.Direct2D1.Brush dxBlue;
        private SharpDX.Direct2D1.Brush dxPurple;
        private TextFormat fontSmall;
        private TextFormat fontNormal;
        private TextFormat fontBold;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Four-greek exposure dashboard and levels from gex_service.py JSON output.";
                Name = "GEXCommand";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                IsSuspendedWhileInactive = true;

                JsonFilePath = @"C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\gex_command.json";
                RefreshSeconds = 5;
                ShowGex = true;
                ShowVex = true;
                ShowDex = true;
                ShowChex = true;
                ShowHud = true;
                LineOpacity = 85;
                GammaFlipBrush = Brushes.Gold;
                CallWallBrush = Brushes.IndianRed;
                PutWallBrush = Brushes.LimeGreen;
                HvlBrush = Brushes.DeepSkyBlue;
                VannaBrush = Brushes.DodgerBlue;
                DexBrush = Brushes.MediumSeaGreen;
                ChexBrush = Brushes.MediumPurple;
                NeutralBrush = Brushes.Gainsboro;
            }
            else if (State == State.Historical)
            {
                refreshTimer = new Timer(ReadSnapshotSafe, null, 500, Math.Max(1, RefreshSeconds) * 1000);
            }
            else if (State == State.Terminated)
            {
                if (refreshTimer != null)
                {
                    refreshTimer.Dispose();
                    refreshTimer = null;
                }
                DisposeDx();
            }
        }

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null)
                return;

            dxText = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.95f, 0.95f, 0.97f, 1f));
            dxMuted = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.75f, 0.75f, 0.80f, 1f));
            dxPanel = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.08f, 0.08f, 0.10f, 0.92f));
            dxPanel2 = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.13f, 0.13f, 0.16f, 0.96f));
            dxBorder = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.26f, 0.26f, 0.31f, 1f));
            dxGreen = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.18f, 0.84f, 0.46f, 1f));
            dxRed = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.95f, 0.33f, 0.33f, 1f));
            dxGold = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.98f, 0.77f, 0.28f, 1f));
            dxBlue = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.33f, 0.67f, 1.00f, 1f));
            dxPurple = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.80f, 0.50f, 1.00f, 1f));

            fontSmall = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 11f);
            fontNormal = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI Semibold", 13f);
            fontBold = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI Bold", 14f);
        }

        private void DisposeDx()
        {
            if (fontSmall != null) { fontSmall.Dispose(); fontSmall = null; }
            if (fontNormal != null) { fontNormal.Dispose(); fontNormal = null; }
            if (fontBold != null) { fontBold.Dispose(); fontBold = null; }
            DisposeBrush(ref dxText);
            DisposeBrush(ref dxMuted);
            DisposeBrush(ref dxPanel);
            DisposeBrush(ref dxPanel2);
            DisposeBrush(ref dxBorder);
            DisposeBrush(ref dxGreen);
            DisposeBrush(ref dxRed);
            DisposeBrush(ref dxGold);
            DisposeBrush(ref dxBlue);
            DisposeBrush(ref dxPurple);
        }

        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush brush)
        {
            if (brush != null)
            {
                brush.Dispose();
                brush = null;
            }
        }

        private void ReadSnapshotSafe(object state)
        {
            try
            {
                ReadSnapshot();
            }
            catch (Exception ex)
            {
                lock (snapshotLock)
                {
                    statusText = "Read error: " + ex.Message;
                }
                if (ChartControl != null)
                    ChartControl.Dispatcher.BeginInvoke(new Action(() => ChartControl.InvalidateVisual()));
            }
        }

        private void ReadSnapshot()
        {
            string path = ExpandJsonPath(JsonFilePath);
            if (!File.Exists(path))
            {
                lock (snapshotLock)
                    statusText = "Missing JSON: " + path;
                if (ChartControl != null)
                    ChartControl.Dispatcher.BeginInvoke(new Action(() => ChartControl.InvalidateVisual()));
                return;
            }

            FourGreekPayload payload;
            var serializer = new JavaScriptSerializer();
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var sr = new StreamReader(fs))
                payload = serializer.Deserialize<FourGreekPayload>(sr.ReadToEnd());

            AssetSnapshot match = MatchAsset(payload);
            lock (snapshotLock)
            {
                activeAsset = match;
                if (match == null)
                    statusText = "No matching asset in JSON for " + GetInstrumentRoot();
                else if (!string.IsNullOrEmpty(match.chain_error))
                    statusText = match.chain_error;
                else if (match.stale)
                    statusText = string.Format("STALE {0} ({1}s)", match.underlying, match.age_seconds);
                else
                    statusText = string.Format("{0} ok • {1}", match.underlying, match.as_of_utc ?? payload.generated_at_utc ?? string.Empty);
            }

            if (ChartControl != null)
                ChartControl.Dispatcher.BeginInvoke(new Action(() => ChartControl.InvalidateVisual()));
        }

        private string ExpandJsonPath(string raw)
        {
            string user = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            return raw.Replace("%USERPROFILE%\\Documents", user);
        }

        private AssetSnapshot MatchAsset(FourGreekPayload payload)
        {
            if (payload == null || payload.assets == null || payload.assets.Count == 0)
                return null;

            string root = GetInstrumentRoot();
            string target = root == "MNQ" || root == "NQ" ? "NQ"
                          : root == "MES" || root == "ES" ? "ES"
                          : root;

            foreach (var asset in payload.assets)
            {
                if (asset == null || string.IsNullOrEmpty(asset.futures_root))
                    continue;
                if (string.Equals(asset.futures_root, target, StringComparison.OrdinalIgnoreCase))
                    return asset;
            }
            return payload.assets[0];
        }

        private string GetInstrumentRoot()
        {
            string full = Instrument != null && Instrument.MasterInstrument != null
                ? Instrument.MasterInstrument.Name
                : string.Empty;
            if (string.IsNullOrEmpty(full))
                return string.Empty;
            int idx = full.IndexOf(' ');
            return idx > 0 ? full.Substring(0, idx).Trim().ToUpperInvariant() : full.Trim().ToUpperInvariant();
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (RenderTarget == null || ChartPanel == null || fontNormal == null)
                return;

            AssetSnapshot snapshot;
            string localStatus;
            lock (snapshotLock)
            {
                snapshot = activeAsset;
                localStatus = statusText;
            }

            RenderStatus(localStatus, snapshot, chartScale);
            if (snapshot == null)
                return;

            if (ShowHud)
                RenderHud(snapshot);
            RenderLevels(snapshot, chartControl, chartScale);
        }

        protected override void OnBarUpdate()
        {
        }

        private void RenderStatus(string text, AssetSnapshot snapshot, ChartScale chartScale)
        {
            if (dxMuted == null || dxPanel == null || dxBorder == null)
                return;

            float x = (float)(ChartPanel.X + 6);
            float y = (float)(ChartPanel.Y + 4);
            float w = 420f;
            float h = snapshot == null || chartScale == null ? 24f : 56f;
            var rect = new RectangleF(x - 2f, y - 2f, w, h);
            RenderTarget.FillRectangle(rect, dxPanel);
            RenderTarget.DrawRectangle(rect, dxBorder, 1f);

            if (!string.IsNullOrEmpty(text))
            {
                using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, text, fontSmall, w - 8f, 18f))
                    RenderTarget.DrawTextLayout(new Vector2(x + 2f, y + 1f), layout, dxMuted);
            }

            if (snapshot == null || chartScale == null)
                return;

            int total = 0;
            int inRange = 0;
            int below = 0;
            int above = 0;
            double min = chartScale.MinValue;
            double max = chartScale.MaxValue;
            string nearest = null;
            double nearestDistance = double.MaxValue;

            if (snapshot.levels_list != null)
            {
                foreach (var level in snapshot.levels_list)
                {
                    string key = NormalizeKey(level != null ? level.key : null);
                    if (!ShouldShow(key))
                        continue;

                    total++;
                    double price = level != null ? level.price : 0.0;
                    if (price < min)
                    {
                        below++;
                        double distance = min - price;
                        if (distance < nearestDistance)
                        {
                            nearestDistance = distance;
                            nearest = string.Format("next below: {0} {1:F2}", FriendlyKey(key), price);
                        }
                    }
                    else if (price > max)
                    {
                        above++;
                        double distance = price - max;
                        if (distance < nearestDistance)
                        {
                            nearestDistance = distance;
                            nearest = string.Format("next above: {0} {1:F2}", FriendlyKey(key), price);
                        }
                    }
                    else
                    {
                        inRange++;
                    }
                }
            }

            string summary = string.Format(
                "levels {0} • visible {1} • below {2} • above {3} • scale {4:F2}-{5:F2}",
                total,
                inRange,
                below,
                above,
                min,
                max);
            DrawText(x + 2f, y + 20f, summary, fontSmall, inRange > 0 ? dxGreen : dxGold, w - 8f, 16f);

            string hint = string.IsNullOrEmpty(nearest)
                ? string.Format("spot {0:F2} • futures root {1}", snapshot.futures_spot, snapshot.futures_root ?? "?")
                : nearest;
            DrawText(x + 2f, y + 36f, hint, fontSmall, dxText, w - 8f, 16f);
        }

        private void RenderHud(AssetSnapshot snapshot)
        {
            float panelRight = (float)(ChartPanel.X + ChartPanel.W);
            float x = panelRight - 340f;
            float y = (float)ChartPanel.Y + 20f;
            float w = 332f;
            float h = 178f;
            var rect = new RectangleF(x, y, w, h);
            RenderTarget.FillRectangle(rect, dxPanel);
            RenderTarget.DrawRectangle(rect, dxBorder, 1f);

            DrawText(x + 10f, y + 8f, string.Format("{0} • {1}", snapshot.underlying ?? "?", snapshot.futures_root ?? "?"), fontBold, dxText, 240f, 18f);
            DrawText(x + 10f, y + 28f, string.Format("Massive timestamp: {0}", snapshot.as_of_utc ?? "n/a"), fontSmall, dxMuted, 315f, 16f);

            float rowY = y + 52f;
            DrawSection("GEX", snapshot.net_exposures != null ? snapshot.net_exposures.gex : 0.0, dxGold, x + 10f, rowY, snapshot.LevelFor("gamma_flip") != null ? "Flip / Walls / HVL" : "No GEX levels");
            DrawSection("VEX", snapshot.net_exposures != null ? snapshot.net_exposures.vex : 0.0, dxBlue, x + 10f, rowY + 30f, snapshot.regime ?? "n/a");
            DrawSection("DEX", snapshot.net_exposures != null ? snapshot.net_exposures.dex : 0.0, dxGreen, x + 10f, rowY + 60f, "Price magnet");
            DrawSection("CHEX", snapshot.net_exposures != null ? snapshot.net_exposures.chex : 0.0, dxPurple, x + 10f, rowY + 90f, snapshot.CharmDirectionLabel());

            DrawText(x + 10f, y + 148f, snapshot.is_0dte ? "0DTE EXPIRY DAY: YES" : "0DTE EXPIRY DAY: NO", fontNormal, snapshot.is_0dte ? dxGold : dxMuted, 180f, 18f);
            DrawText(x + 190f, y + 148f, snapshot.stale ? "STALE" : "LIVE", fontBold, snapshot.stale ? dxRed : dxGreen, 60f, 18f);
        }

        private void DrawSection(string title, double value, SharpDX.Direct2D1.Brush accent, float x, float y, string subtitle)
        {
            DrawText(x, y, title, fontBold, accent, 52f, 18f);
            DrawText(x + 56f, y, FormatCompact(value), fontNormal, dxText, 112f, 18f);
            DrawText(x + 172f, y, subtitle, fontSmall, dxMuted, 140f, 18f);
        }

        private void RenderLevels(AssetSnapshot snapshot, ChartControl chartControl, ChartScale chartScale)
        {
            if (snapshot.levels_list == null || snapshot.levels_list.Count == 0)
                return;

            float panelLeft = (float)ChartPanel.X;
            float panelRight = (float)(ChartPanel.X + ChartPanel.W);
            float leftBoxW = 150f;
            float rightBoxW = 196f;
            double min = chartScale.MinValue;
            double max = chartScale.MaxValue;
            float topY = (float)ChartPanel.Y + 54f;
            float bottomY = (float)(ChartPanel.Y + ChartPanel.H) - 54f;

            var inRangeLevels = new List<LevelSnapshot>();
            var aboveLevels = new List<LevelSnapshot>();
            var belowLevels = new List<LevelSnapshot>();

            foreach (var level in snapshot.levels_list)
            {
                string key = NormalizeKey(level.key);
                if (!ShouldShow(key))
                    continue;

                if (level.price < min)
                    belowLevels.Add(level);
                else if (level.price > max)
                    aboveLevels.Add(level);
                else
                    inRangeLevels.Add(level);
            }

            foreach (var level in inRangeLevels.OrderByDescending(l => l.price))
            {
                RenderLevelAtY(level, chartScale.GetYByValue(level.price), panelLeft, panelRight, leftBoxW, rightBoxW, snapshot.stale, false, string.Empty);
            }

            const int maxEdgeLevelsPerSide = 4;
            float edgeStep = 24f;

            var topEdge = aboveLevels.OrderBy(l => l.price).Take(maxEdgeLevelsPerSide).ToList();
            for (int i = 0; i < topEdge.Count; i++)
            {
                RenderLevelAtY(topEdge[i], topY + (i * edgeStep), panelLeft, panelRight, leftBoxW, rightBoxW, snapshot.stale, true, "↑ ");
            }

            var bottomEdge = belowLevels.OrderByDescending(l => l.price).Take(maxEdgeLevelsPerSide).ToList();
            for (int i = 0; i < bottomEdge.Count; i++)
            {
                RenderLevelAtY(bottomEdge[i], bottomY - (i * edgeStep), panelLeft, panelRight, leftBoxW, rightBoxW, snapshot.stale, true, "↓ ");
            }
        }

        private void RenderLevelAtY(LevelSnapshot level, float y, float panelLeft, float panelRight, float leftBoxW, float rightBoxW, bool stale, bool edgeClamped, string edgePrefix)
        {
            string key = NormalizeKey(level.key);
            var accent = BrushFor(key);
            float alpha = stale ? 0.45f : Math.Max(0.2f, Math.Min(1f, LineOpacity / 100f));
            if (edgeClamped)
                alpha = Math.Max(alpha, 0.9f);
            var color = ((System.Windows.Media.SolidColorBrush)accent).Color;
            var dxLine = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(color.ScR, color.ScG, color.ScB, alpha));
            try
            {
                RenderTarget.DrawLine(new Vector2(panelLeft + leftBoxW + 8f, y), new Vector2(panelRight - rightBoxW - 8f, y), dxLine, edgeClamped ? Math.Max(2.5f, LevelStroke(key)) : LevelStroke(key));
            }
            finally
            {
                dxLine.Dispose();
            }

            var leftRect = new RectangleF(panelLeft + 4f, y - 10f, leftBoxW, 20f);
            var rightRect = new RectangleF(panelRight - rightBoxW - 4f, y - 10f, rightBoxW, 20f);
            RenderTarget.FillRectangle(leftRect, dxPanel2);
            RenderTarget.FillRectangle(rightRect, dxPanel2);
            RenderTarget.DrawRectangle(leftRect, dxBorder, 1f);
            RenderTarget.DrawRectangle(rightRect, dxBorder, 1f);
            RenderTarget.FillRectangle(new RectangleF(leftRect.X, leftRect.Y, 4f, leftRect.Height), BrushDxFor(key));
            RenderTarget.FillRectangle(new RectangleF(rightRect.X, rightRect.Y, 4f, rightRect.Height), BrushDxFor(key));

            string leftText = edgeClamped ? edgePrefix + (level.action ?? string.Empty) : (level.action ?? string.Empty);
            DrawText(leftRect.X + 8f, leftRect.Y + 2f, leftText, fontSmall, dxText, leftRect.Width - 10f, 16f);
            string rightText = string.Format("{0}{1} {2}  {3:F2}", edgePrefix, level.symbol ?? string.Empty, level.label ?? string.Empty, level.price);
            DrawText(rightRect.X + 8f, rightRect.Y + 1f, rightText, fontNormal, BrushDxFor(key), rightRect.Width - 10f, 18f);
        }

        private bool ShouldShow(string key)
        {
            key = NormalizeKey(key);
            if (string.IsNullOrEmpty(key))
                return true;
            if (key == "gamma_flip" || key == "call_wall" || key == "put_wall" || key == "hvl")
                return ShowGex;
            if (key == "vanna_call" || key == "vanna_put")
                return ShowVex;
            if (key == "dex_peak")
                return ShowDex;
            if (key == "charm_drift")
                return ShowChex;
            return true;
        }

        private float LevelStroke(string key)
        {
            key = NormalizeKey(key);
            if (key == "call_wall" || key == "put_wall") return 2.8f;
            if (key == "gamma_flip" || key == "hvl") return 2.0f;
            return 1.5f;
        }

        private Brush BrushFor(string key)
        {
            key = NormalizeKey(key);
            if (key == "call_wall") return CallWallBrush;
            if (key == "put_wall") return PutWallBrush;
            if (key == "gamma_flip") return GammaFlipBrush;
            if (key == "hvl") return HvlBrush;
            if (key == "vanna_call" || key == "vanna_put") return VannaBrush;
            if (key == "dex_peak") return DexBrush;
            if (key == "charm_drift") return ChexBrush;
            return NeutralBrush;
        }

        private SharpDX.Direct2D1.Brush BrushDxFor(string key)
        {
            key = NormalizeKey(key);
            if (key == "call_wall") return dxRed;
            if (key == "put_wall") return dxGreen;
            if (key == "gamma_flip") return dxGold;
            if (key == "hvl") return dxBlue;
            if (key == "vanna_call" || key == "vanna_put") return dxBlue;
            if (key == "dex_peak") return dxGreen;
            if (key == "charm_drift") return dxPurple;
            return dxText;
        }

        private void DrawText(float x, float y, string text, TextFormat font, SharpDX.Direct2D1.Brush brush, float width, float height)
        {
            if (string.IsNullOrEmpty(text) || font == null || brush == null)
                return;
            using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, text, font, width, height))
                RenderTarget.DrawTextLayout(new Vector2(x, y), layout, brush);
        }

        private string FormatCompact(double value)
        {
            double abs = Math.Abs(value);
            if (abs >= 1_000_000_000.0) return (value / 1_000_000_000.0).ToString("0.00B", CultureInfo.InvariantCulture);
            if (abs >= 1_000_000.0) return (value / 1_000_000.0).ToString("0.00M", CultureInfo.InvariantCulture);
            if (abs >= 1_000.0) return (value / 1_000.0).ToString("0.00K", CultureInfo.InvariantCulture);
            return value.ToString("0.00", CultureInfo.InvariantCulture);
        }

        private string NormalizeKey(string key)
        {
            return string.IsNullOrEmpty(key) ? string.Empty : key.Trim().ToLowerInvariant();
        }

        private string FriendlyKey(string key)
        {
            key = NormalizeKey(key);
            if (string.IsNullOrEmpty(key))
                return "unknown";
            return key.Replace('_', ' ');
        }

        [NinjaScriptProperty]
        [Display(Name = "JSON File Path", GroupName = "1. Data", Order = 1)]
        public string JsonFilePath { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Refresh Seconds", GroupName = "1. Data", Order = 2)]
        public int RefreshSeconds { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show GEX", GroupName = "2. Toggles", Order = 1)]
        public bool ShowGex { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show VEX", GroupName = "2. Toggles", Order = 2)]
        public bool ShowVex { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show DEX", GroupName = "2. Toggles", Order = 3)]
        public bool ShowDex { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show CHEX", GroupName = "2. Toggles", Order = 4)]
        public bool ShowChex { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show HUD", GroupName = "2. Toggles", Order = 5)]
        public bool ShowHud { get; set; }

        [NinjaScriptProperty]
        [Range(10, 100)]
        [Display(Name = "Line Opacity", GroupName = "2. Toggles", Order = 6)]
        public int LineOpacity { get; set; }

        [XmlIgnore]
        [Display(Name = "Gamma Flip", GroupName = "3. Colors", Order = 1)]
        public Brush GammaFlipBrush { get; set; }
        [Browsable(false)] public string GammaFlipBrushSerialize { get { return Serialize.BrushToString(GammaFlipBrush); } set { GammaFlipBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Call Wall", GroupName = "3. Colors", Order = 2)]
        public Brush CallWallBrush { get; set; }
        [Browsable(false)] public string CallWallBrushSerialize { get { return Serialize.BrushToString(CallWallBrush); } set { CallWallBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Put Wall", GroupName = "3. Colors", Order = 3)]
        public Brush PutWallBrush { get; set; }
        [Browsable(false)] public string PutWallBrushSerialize { get { return Serialize.BrushToString(PutWallBrush); } set { PutWallBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "HVL", GroupName = "3. Colors", Order = 4)]
        public Brush HvlBrush { get; set; }
        [Browsable(false)] public string HvlBrushSerialize { get { return Serialize.BrushToString(HvlBrush); } set { HvlBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Vanna", GroupName = "3. Colors", Order = 5)]
        public Brush VannaBrush { get; set; }
        [Browsable(false)] public string VannaBrushSerialize { get { return Serialize.BrushToString(VannaBrush); } set { VannaBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "DEX", GroupName = "3. Colors", Order = 6)]
        public Brush DexBrush { get; set; }
        [Browsable(false)] public string DexBrushSerialize { get { return Serialize.BrushToString(DexBrush); } set { DexBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "CHEX", GroupName = "3. Colors", Order = 7)]
        public Brush ChexBrush { get; set; }
        [Browsable(false)] public string ChexBrushSerialize { get { return Serialize.BrushToString(ChexBrush); } set { ChexBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Neutral", GroupName = "3. Colors", Order = 8)]
        public Brush NeutralBrush { get; set; }
        [Browsable(false)] public string NeutralBrushSerialize { get { return Serialize.BrushToString(NeutralBrush); } set { NeutralBrush = Serialize.StringToBrush(value); } }
    }

    public class FourGreekPayload
    {
        public string generated_at_utc { get; set; }
        public List<AssetSnapshot> assets { get; set; }
    }

    public class AssetSnapshot
    {
        public string underlying { get; set; }
        public string futures_root { get; set; }
        public double underlying_spot { get; set; }
        public double futures_spot { get; set; }
        public double ratio { get; set; }
        public string as_of_utc { get; set; }
        public bool stale { get; set; }
        public int age_seconds { get; set; }
        public bool is_0dte { get; set; }
        public string regime { get; set; }
        public string charm_direction { get; set; }
        public string chain_error { get; set; }
        public NetExposureSnapshot net_exposures { get; set; }
        public List<LevelSnapshot> levels_list { get; set; }

        public LevelSnapshot LevelFor(string key)
        {
            if (levels_list == null)
                return null;
            foreach (var level in levels_list)
                if (string.Equals(level.key, key, StringComparison.OrdinalIgnoreCase))
                    return level;
            return null;
        }

        public string CharmDirectionLabel()
        {
            return string.IsNullOrEmpty(charm_direction) ? "PM DRIFT ?" : "PM DRIFT " + charm_direction;
        }
    }

    public class NetExposureSnapshot
    {
        public double gex { get; set; }
        public double vex { get; set; }
        public double dex { get; set; }
        public double chex { get; set; }
    }

    public class LevelSnapshot
    {
        public string key { get; set; }
        public string symbol { get; set; }
        public string label { get; set; }
        public string action { get; set; }
        public double price { get; set; }
        public double source_price { get; set; }
        public double value { get; set; }
        public string direction { get; set; }
    }
}
