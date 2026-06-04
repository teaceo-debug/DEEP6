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
    /// <summary>
    /// Unified DEEP6 GEX command center overlay.
    /// Reads massive_gex_map.json from the Python sidecar and renders regime, levels, and semantic actions.
    /// </summary>
    public class DEEP6GexCommandCenter : Indicator
    {
        #region Fields
        private readonly object sync = new object();
        private Timer refreshTimer;
        private V3Payload payload;
        private V3Asset activeAsset;
        private string statusText = "Waiting for massive_gex_map.json...";
        private DateTime fileWriteUtc = DateTime.MinValue;
        private DateTime lastReadUtc = DateTime.MinValue;

        private SharpDX.Direct2D1.Brush dxText;
        private SharpDX.Direct2D1.Brush dxMuted;
        private SharpDX.Direct2D1.Brush dxPanel;
        private SharpDX.Direct2D1.Brush dxBorder;
        private SharpDX.Direct2D1.Brush dxGreen;
        private SharpDX.Direct2D1.Brush dxRed;
        private SharpDX.Direct2D1.Brush dxGold;
        private SharpDX.Direct2D1.Brush dxBlue;
        private SharpDX.Direct2D1.Brush dxPositive;
        private SharpDX.Direct2D1.Brush dxPurple;
        private SharpDX.Direct2D1.Brush dxAmber;
        private SharpDX.Direct2D1.Brush dxHalo;

        private TextFormat fontSmall;
        private TextFormat fontNormal;
        private TextFormat fontBold;
        private TextFormat fontMono;
        #endregion

        #region Lifecycle
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 unified GEX command center overlay for Python sidecar JSON.";
                Name = "DEEP6 GEX Command Center";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                ScaleJustification = ScaleJustification.Right;
                IsSuspendedWhileInactive = true;
                DisplayInDataBox = false;
                BarsRequiredToPlot = 0;

                JsonFilePath = @"%USERPROFILE%\Documents\NinjaTrader 8\templates\DEEP6\massive_gex_map.json";
                RefreshSeconds = 2;
                StaleSeconds = 180;

                MaxRenderedLevels = 6;
                MaxDistancePoints = 500;
                ShowRegimeBadge = true;
                ShowStatusBar = true;
                ShowActionLabels = true;
                HideStaleLevels = false;

                GammaFlipBrush = Brushes.Gold;
                CallWallBrush = Brushes.IndianRed;
                PutWallBrush = Brushes.LimeGreen;
                MagnetBrush = Brushes.DeepSkyBlue;
                PositiveNodeBrush = Brushes.DodgerBlue;
                NegativeNodeBrush = Brushes.MediumPurple;
            }
            else if (State == State.Historical)
            {
                refreshTimer = new Timer(ReadSnapshotSafe, null, 250, Math.Max(1, RefreshSeconds) * 1000);
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

        protected override void OnBarUpdate()
        {
        }

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null)
                return;

            dxText = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.94f, 0.95f, 0.97f, 1f));
            dxMuted = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.68f, 0.70f, 0.75f, 1f));
            dxPanel = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.04f, 0.05f, 0.07f, 0.92f));
            dxBorder = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.26f, 0.28f, 0.34f, 1f));
            dxGreen = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToDxColor(PutWallBrush, new Color4(0.18f, 0.84f, 0.46f, 1f)));
            dxRed = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToDxColor(CallWallBrush, new Color4(0.96f, 0.32f, 0.32f, 1f)));
            dxGold = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToDxColor(GammaFlipBrush, new Color4(1.00f, 0.78f, 0.22f, 1f)));
            dxBlue = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToDxColor(MagnetBrush, new Color4(0.28f, 0.67f, 1.00f, 1f)));
            dxPositive = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToDxColor(PositiveNodeBrush, new Color4(0.18f, 0.55f, 1.00f, 1f)));
            dxPurple = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToDxColor(NegativeNodeBrush, new Color4(0.78f, 0.48f, 1.00f, 1f)));
            dxAmber = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(1.00f, 0.55f, 0.14f, 1f));
            dxHalo = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0f, 0f, 0f, 0.78f));

            var factory = NinjaTrader.Core.Globals.DirectWriteFactory;
            fontSmall = new TextFormat(factory, "Segoe UI", 11f);
            fontNormal = new TextFormat(factory, "Segoe UI Semibold", 12f);
            fontBold = new TextFormat(factory, "Segoe UI Bold", 13f);
            fontMono = new TextFormat(factory, "Consolas", 10f);
        }

        private void DisposeDx()
        {
            DisposeText(ref fontSmall);
            DisposeText(ref fontNormal);
            DisposeText(ref fontBold);
            DisposeText(ref fontMono);
            DisposeBrush(ref dxText);
            DisposeBrush(ref dxMuted);
            DisposeBrush(ref dxPanel);
            DisposeBrush(ref dxBorder);
            DisposeBrush(ref dxGreen);
            DisposeBrush(ref dxRed);
            DisposeBrush(ref dxGold);
            DisposeBrush(ref dxBlue);
            DisposeBrush(ref dxPositive);
            DisposeBrush(ref dxPurple);
            DisposeBrush(ref dxAmber);
            DisposeBrush(ref dxHalo);
        }

        private static void DisposeText(ref TextFormat f)
        {
            if (f != null)
            {
                f.Dispose();
                f = null;
            }
        }

        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush b)
        {
            if (b != null)
            {
                b.Dispose();
                b = null;
            }
        }
        #endregion

        #region Data Loading
        private void ReadSnapshotSafe(object state)
        {
            try
            {
                ReadSnapshot();
            }
            catch (Exception ex)
            {
                lock (sync)
                    statusText = "GEX CC read error: " + Shorten(ex.Message, 110);
                RefreshChart();
            }
        }

        private void ReadSnapshot()
        {
            string path = ExpandPath(JsonFilePath);
            if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            {
                lock (sync)
                    statusText = "GEX CC missing JSON: " + path;
                RefreshChart();
                return;
            }

            string json;
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var sr = new StreamReader(fs))
                json = sr.ReadToEnd();

            var serializer = new JavaScriptSerializer { MaxJsonLength = 8 * 1024 * 1024 };
            V3Payload next = serializer.Deserialize<V3Payload>(json);
            V3Asset asset = MatchAsset(next);
            DateTime writeUtc = File.GetLastWriteTimeUtc(path);
            DateTime readUtc = DateTime.UtcNow;

            lock (sync)
            {
                payload = next;
                activeAsset = asset;
                fileWriteUtc = writeUtc;
                lastReadUtc = readUtc;
                statusText = BuildStatus(next, asset, writeUtc);
            }
            RefreshChart();
        }

        private void RefreshChart()
        {
            try
            {
                if (ChartControl != null)
                    ChartControl.Dispatcher.BeginInvoke(new Action(delegate { ChartControl.InvalidateVisual(); }));
            }
            catch { }
        }

        private string ExpandPath(string raw)
        {
            string docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            string profile = Directory.GetParent(docs) != null ? Directory.GetParent(docs).FullName : docs;
            return (raw ?? string.Empty)
                .Replace("%USERPROFILE%\\Documents", docs)
                .Replace("%USERPROFILE%", profile);
        }

        private V3Asset MatchAsset(V3Payload p)
        {
            if (p == null || p.assets == null || p.assets.Count == 0)
                return null;
            string root = NormalizeRoot(GetInstrumentRoot());
            foreach (var a in p.assets)
            {
                if (a == null)
                    continue;
                if (string.Equals(NormalizeRoot(a.futures_root), root, StringComparison.OrdinalIgnoreCase))
                    return a;
            }
            return p.assets[0];
        }

        private string NormalizeRoot(string root)
        {
            root = (root ?? string.Empty).Trim().ToUpperInvariant();
            if (root == "MNQ") return "NQ";
            if (root == "MES") return "ES";
            return root;
        }

        private string GetInstrumentRoot()
        {
            string full = Instrument != null && Instrument.MasterInstrument != null
                ? Instrument.MasterInstrument.Name
                : string.Empty;
            if (string.IsNullOrEmpty(full))
                return string.Empty;
            int idx = full.IndexOf(' ');
            return (idx > 0 ? full.Substring(0, idx) : full).Trim().ToUpperInvariant();
        }

        private string BuildStatus(V3Payload p, V3Asset a, DateTime writeUtc)
        {
            if (p == null)
                return "GEX CC: JSON parse returned empty payload";

            int age = AgeSeconds(p.generated_at_utc, writeUtc);
            if (a == null)
                return string.Format(CultureInfo.InvariantCulture, "GEX CC: no asset for {0} | age {1}s", GetInstrumentRoot(), age);
            if (!string.IsNullOrEmpty(a.chain_error))
                return "GEX CC chain error: " + Shorten(a.chain_error, 96);

            int levelCount = LevelCount(a);
            string stale = age > StaleSeconds ? "STALE" : "OK";
            string mapText = BuildMappingText(a);

            return string.Format(CultureInfo.InvariantCulture,
                "GEX CC {0} | {1} | {2} levels | {3}s",
                stale,
                mapText,
                levelCount,
                age);
        }

        private int AgeSeconds(string utc, DateTime fallbackUtc)
        {
            DateTime parsed;
            if (!string.IsNullOrEmpty(utc) && DateTime.TryParse(utc, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out parsed))
                return Math.Max(0, (int)(DateTime.UtcNow - parsed).TotalSeconds);
            if (fallbackUtc != DateTime.MinValue)
                return Math.Max(0, (int)(DateTime.UtcNow - fallbackUtc).TotalSeconds);
            return int.MaxValue;
        }
        #endregion

        #region Rendering
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (RenderTarget == null || ChartPanel == null || fontSmall == null)
                return;

            V3Payload localPayload;
            V3Asset localAsset;
            string localStatus;
            DateTime localFileUtc;
            DateTime localReadUtc;
            lock (sync)
            {
                localPayload = payload;
                localAsset = activeAsset;
                localStatus = statusText;
                localFileUtc = fileWriteUtc;
                localReadUtc = lastReadUtc;
            }

            bool stale = false;
            if (localPayload != null)
                stale = AgeSeconds(localPayload.generated_at_utc, localFileUtc) > StaleSeconds;
            if (localAsset != null && (localAsset.stale || (localAsset.freshness != null && localAsset.freshness.stale)))
                stale = true;

            if (ShowStatusBar)
                DrawStatus(localStatus, localAsset, stale);

            if (ShowRegimeBadge)
                DrawRegimeBadge(localAsset, localPayload, localFileUtc, localReadUtc, stale);

            if (localAsset == null)
                return;
            if (HideStaleLevels && stale)
                return;

            DrawLevels(localAsset, chartScale, stale);
        }

        private void DrawStatus(string text, V3Asset asset, bool stale)
        {
            if (dxPanel == null || dxBorder == null || dxText == null)
                return;

            float x = (float)ChartPanel.X + 8f;
            float y = (float)ChartPanel.Y + 6f;
            float w = 520f;
            float h = 26f;
            RenderTarget.FillRectangle(new RectangleF(x, y, w, h), dxPanel);
            RenderTarget.DrawRectangle(new RectangleF(x, y, w, h), dxBorder, 1f);
            SharpDX.Direct2D1.Brush brush = stale ? (dxAmber ?? dxText) : asset == null ? (dxMuted ?? dxText) : (dxGreen ?? dxText);
            DrawText(x + 8f, y + 5f, text ?? string.Empty, fontSmall, brush, w - 16f, h - 8f);
        }

        private void DrawRegimeBadge(V3Asset asset, V3Payload localPayload, DateTime localFileUtc, DateTime localReadUtc, bool stale)
        {
            if (dxPanel == null || dxBorder == null || dxText == null || fontBold == null || fontSmall == null || fontMono == null)
                return;

            float w = 200f;
            float h = 70f;
            float x = (float)(ChartPanel.X + ChartPanel.W) - w - 8f;
            float y = (float)ChartPanel.Y + 8f;

            var panel = new RoundedRectangle
            {
                Rect = new RectangleF(x, y, x + w, y + h),
                RadiusX = 7f,
                RadiusY = 7f
            };

            RenderTarget.FillRoundedRectangle(panel, dxPanel);
            RenderTarget.DrawRoundedRectangle(panel, dxBorder, 1f);

            RegimeInfo regime = GetRegimeInfo(asset);
            int age = localPayload != null ? AgeSeconds(localPayload.generated_at_utc, localFileUtc) : AgeSeconds(null, localReadUtc);
            string line1 = "REGIME: " + regime.Name;
            string line2 = BuildMappingText(asset);
            string line3 = string.Format(CultureInfo.InvariantCulture, "⏱ {0}s | {1} levels | {2}", age == int.MaxValue ? -1 : age, LevelCount(asset), stale ? "STALE" : "OK");
            if (line3.IndexOf("-1s", StringComparison.Ordinal) >= 0)
                line3 = string.Format(CultureInfo.InvariantCulture, "⏱ ? | {0} levels | {1}", LevelCount(asset), stale ? "STALE" : "OK");

            DrawText(x + 10f, y + 8f, line1, fontBold, regime.Brush ?? dxAmber ?? dxText, w - 20f, 18f);
            DrawText(x + 10f, y + 29f, line2, fontSmall, dxMuted ?? dxText, w - 20f, 16f);
            DrawText(x + 10f, y + 48f, line3, fontMono, stale ? (dxAmber ?? dxText) : (dxText ?? regime.Brush), w - 20f, 16f);
        }

        private void DrawLevels(V3Asset asset, ChartScale chartScale, bool stale)
        {
            List<V3Level> raw = GetLevels(asset);
            if (raw == null || raw.Count == 0)
                return;

            double refPrice = CurrentPrice(asset);
            if (refPrice <= 0)
                return;

            double maxDistance = Math.Max(1, MaxDistancePoints);
            var candidates = new List<V3Level>();
            foreach (var l in raw)
            {
                if (l == null || l.price <= 0)
                    continue;
                l._distance = l.distance_from_futures_spot != 0 ? l.distance_from_futures_spot : l.price - refPrice;
                if (Math.Abs(l._distance) <= maxDistance)
                    candidates.Add(l);
            }

            candidates = candidates
                .OrderBy(l => IsPriorityRole(l) ? 0 : 1)
                .ThenBy(l => Math.Abs(l._distance))
                .ThenBy(l => RoleSort(l))
                .Take(Math.Max(1, MaxRenderedLevels))
                .ToList();

            float left = (float)ChartPanel.X + 2f;
            float right = (float)(ChartPanel.X + ChartPanel.W) - 4f;
            float labelWidth = 200f;
            float labelHeight = 22f;
            float lineRight = right - labelWidth - 12f;
            int topSlots = 0;
            int bottomSlots = 0;
            double min = chartScale.MinValue;
            double max = chartScale.MaxValue;

            foreach (var l in candidates)
            {
                bool offscreen = false;
                float y;
                string prefix = string.Empty;
                if (l.price > max)
                {
                    if (!IsPriorityRole(l))
                        continue;
                    offscreen = true;
                    prefix = "▲ ";
                    y = (float)ChartPanel.Y + 86f + topSlots * 24f;
                    topSlots++;
                }
                else if (l.price < min)
                {
                    if (!IsPriorityRole(l))
                        continue;
                    offscreen = true;
                    prefix = "▼ ";
                    y = (float)(ChartPanel.Y + ChartPanel.H) - 32f - bottomSlots * 24f;
                    bottomSlots++;
                }
                else
                {
                    y = chartScale.GetYByValue(l.price);
                }

                SharpDX.Direct2D1.Brush brush = BrushFor(l);
                if (brush == null)
                    continue;

                float width = IsPinnedRole(l) ? 2.4f : 1.5f;
                if (stale)
                    width = Math.Max(1.0f, width * 0.65f);

                if (!offscreen)
                {
                    RenderTarget.DrawLine(new Vector2(left, y), new Vector2(lineRight, y), dxHalo ?? brush, width + 2.0f);
                    RenderTarget.DrawLine(new Vector2(left, y), new Vector2(lineRight, y), brush, width);
                }
                else
                {
                    RenderTarget.DrawLine(new Vector2(right - 320f, y), new Vector2(right - 8f, y), dxHalo ?? brush, width + 2.0f);
                    RenderTarget.DrawLine(new Vector2(right - 320f, y), new Vector2(right - 8f, y), brush, width);
                }

                string label = BuildLevelLabel(prefix, l, refPrice);
                DrawLabelBox(right - labelWidth, y - (labelHeight / 2f), labelWidth, labelHeight, label, brush);
            }
        }

        private void DrawLabelBox(float x, float y, float w, float h, string text, SharpDX.Direct2D1.Brush accent)
        {
            RenderTarget.FillRectangle(new RectangleF(x, y, w, h), dxPanel ?? accent);
            RenderTarget.DrawRectangle(new RectangleF(x, y, w, h), dxBorder ?? accent, 1f);
            RenderTarget.FillRectangle(new RectangleF(x, y, 4f, h), accent);
            DrawText(x + 8f, y + 3f, text, fontNormal, dxText ?? accent, w - 14f, h - 4f);
        }

        private void DrawText(float x, float y, string text, TextFormat font, SharpDX.Direct2D1.Brush brush, float width, float height)
        {
            if (string.IsNullOrEmpty(text) || font == null || brush == null)
                return;

            using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, text, font, width, height))
                RenderTarget.DrawTextLayout(new Vector2(x, y), layout, brush);
        }
        #endregion

        #region Helpers
        private List<V3Level> GetLevels(V3Asset asset)
        {
            if (asset == null)
                return null;
            if (asset.levels_list != null && asset.levels_list.Count > 0)
                return asset.levels_list;
            return asset.levels;
        }

        private int LevelCount(V3Asset asset)
        {
            List<V3Level> levels = GetLevels(asset);
            return levels != null ? levels.Count : 0;
        }

        private double CurrentPrice(V3Asset a)
        {
            try
            {
                if (CurrentBar >= 0 && Close != null && Close.Count > 0 && Close[0] > 0)
                    return Close[0];
            }
            catch { }

            if (a != null && a.futures_spot > 0)
                return a.futures_spot;
            return 0;
        }

        private bool IsPriorityRole(V3Level l)
        {
            string role = (l != null ? (l.role ?? l.key ?? l.id ?? string.Empty) : string.Empty).ToLowerInvariant();
            return role == "gamma_flip" || role == "call_wall" || role == "put_wall";
        }

        private bool IsPinnedRole(V3Level l)
        {
            return IsPriorityRole(l);
        }

        private int RoleSort(V3Level l)
        {
            string role = (l != null ? (l.role ?? l.key ?? l.label ?? string.Empty) : string.Empty).ToLowerInvariant();
            if (role.Contains("flip")) return 0;
            if (role.Contains("call")) return 1;
            if (role.Contains("put")) return 2;
            if (role.Contains("magnet") || role.Contains("hvl")) return 3;
            if (role.Contains("pos")) return 4;
            if (role.Contains("neg")) return 5;
            return 9;
        }

        private string BuildLevelLabel(string prefix, V3Level l, double refPrice)
        {
            string role = CleanRole(l);
            double dist = l != null ? l._distance : 0;
            if (dist == 0 && l != null && l.price > 0 && refPrice > 0)
                dist = l.price - refPrice;

            string label = string.Format(
                CultureInfo.InvariantCulture,
                "{0}{1} {2:0.00} {3:+0;-0;0}p",
                prefix,
                role,
                l != null ? l.price : 0,
                dist);

            if (ShowActionLabels)
            {
                string action = CleanAction(l);
                if (!string.IsNullOrEmpty(action))
                    label += " — " + action;
            }

            return Shorten(label, 52);
        }

        private string CleanRole(V3Level l)
        {
            string role = (l != null ? (l.role ?? l.key ?? l.label ?? "GEX") : "GEX").ToUpperInvariant();
            role = role.Replace("GAMMA_", string.Empty)
                       .Replace("POS_GEX", "+GEX")
                       .Replace("NEG_GEX", "-GEX")
                       .Replace("_", " ")
                       .Trim();
            if (string.IsNullOrWhiteSpace(role))
                role = "GEX";
            return role;
        }

        private string CleanAction(V3Level l)
        {
            string action = l != null ? (l.action ?? string.Empty) : string.Empty;
            action = action.Replace('_', ' ').Trim();
            if (string.IsNullOrWhiteSpace(action))
            {
                string role = (l != null ? (l.role ?? l.key ?? string.Empty) : string.Empty).ToLowerInvariant();
                if (role.Contains("flip")) action = "REGIME PIVOT";
                else if (role.Contains("call")) action = "RESISTANCE";
                else if (role.Contains("put")) action = "SUPPORT";
                else if (role.Contains("magnet") || role.Contains("hvl")) action = "MAGNET";
            }
            return action.ToUpperInvariant();
        }

        private string BuildMappingText(V3Asset asset)
        {
            if (asset == null)
                return "?→? | ratio ?";

            string source = !string.IsNullOrWhiteSpace(asset.underlying) ? asset.underlying : (!string.IsNullOrWhiteSpace(asset.mapping != null ? asset.mapping.source : null) ? asset.mapping.source : "?");
            string target = !string.IsNullOrWhiteSpace(asset.futures_root) ? asset.futures_root : "?";
            double ratio = asset.mapping != null ? asset.mapping.ratio : 0;

            return ratio > 0
                ? string.Format(CultureInfo.InvariantCulture, "{0}→{1} | ratio {2:0.0}x", source, target, ratio)
                : string.Format(CultureInfo.InvariantCulture, "{0}→{1} | ratio ?", source, target);
        }

        private RegimeInfo GetRegimeInfo(V3Asset asset)
        {
            if (asset == null)
                return new RegimeInfo { Name = "UNKNOWN", Brush = dxAmber ?? dxText };

            V3Level flip = null;
            List<V3Level> levels = GetLevels(asset);
            if (levels != null)
            {
                foreach (var level in levels)
                {
                    if (level == null)
                        continue;
                    string role = (level.role ?? level.key ?? string.Empty).ToLowerInvariant();
                    if (role == "gamma_flip" || role.Contains("flip"))
                    {
                        flip = level;
                        break;
                    }
                }
            }

            if (flip == null || flip.price <= 0 || asset.futures_spot <= 0)
                return new RegimeInfo { Name = "UNKNOWN", Brush = dxAmber ?? dxText };

            return asset.futures_spot > flip.price
                ? new RegimeInfo { Name = "POSITIVE", Brush = dxGreen ?? dxText }
                : new RegimeInfo { Name = "NEGATIVE", Brush = dxRed ?? dxText };
        }

        private SharpDX.Direct2D1.Brush BrushFor(V3Level l)
        {
            string role = (l != null ? (l.role ?? l.key ?? l.label ?? string.Empty) : string.Empty).ToLowerInvariant();
            if (role.Contains("flip")) return dxGold ?? dxText;
            if (role.Contains("call")) return dxRed ?? dxText;
            if (role.Contains("put")) return dxGreen ?? dxText;
            if (role.Contains("hvl") || role.Contains("magnet")) return dxBlue ?? dxText;
            if (role.Contains("pos")) return dxPositive ?? dxBlue ?? dxText;
            if (role.Contains("neg")) return dxPurple ?? dxText;
            return dxText;
        }

        private Color4 ToDxColor(Brush brush, Color4 fallback)
        {
            var solid = brush as System.Windows.Media.SolidColorBrush;
            if (solid == null)
                return fallback;

            var c = solid.Color;
            return new Color4(c.R / 255f, c.G / 255f, c.B / 255f, c.A / 255f);
        }

        private static string Shorten(string text, int max)
        {
            if (string.IsNullOrEmpty(text) || text.Length <= max)
                return text ?? string.Empty;
            return text.Substring(0, max - 3) + "...";
        }

        private class RegimeInfo
        {
            public string Name { get; set; }
            public SharpDX.Direct2D1.Brush Brush { get; set; }
        }
        #endregion

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
        [Range(1, 12)]
        [Display(Name = "Max Rendered Levels", Order = 10, GroupName = "2. Display")]
        public int MaxRenderedLevels { get; set; }

        [NinjaScriptProperty]
        [Range(10, 3000)]
        [Display(Name = "Max Distance Points", Order = 11, GroupName = "2. Display")]
        public int MaxDistancePoints { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Regime Badge", Order = 12, GroupName = "2. Display")]
        public bool ShowRegimeBadge { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Status Bar", Order = 13, GroupName = "2. Display")]
        public bool ShowStatusBar { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Action Labels", Order = 14, GroupName = "2. Display")]
        public bool ShowActionLabels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Hide Stale Levels", Order = 15, GroupName = "2. Display")]
        public bool HideStaleLevels { get; set; }

        [XmlIgnore]
        [Display(Name = "Gamma Flip", Order = 20, GroupName = "3. Colors")]
        public Brush GammaFlipBrush { get; set; }
        [Browsable(false)] public string GammaFlipBrushSerialize { get { return Serialize.BrushToString(GammaFlipBrush); } set { GammaFlipBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Call Wall", Order = 21, GroupName = "3. Colors")]
        public Brush CallWallBrush { get; set; }
        [Browsable(false)] public string CallWallBrushSerialize { get { return Serialize.BrushToString(CallWallBrush); } set { CallWallBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Put Wall", Order = 22, GroupName = "3. Colors")]
        public Brush PutWallBrush { get; set; }
        [Browsable(false)] public string PutWallBrushSerialize { get { return Serialize.BrushToString(PutWallBrush); } set { PutWallBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Magnet", Order = 23, GroupName = "3. Colors")]
        public Brush MagnetBrush { get; set; }
        [Browsable(false)] public string MagnetBrushSerialize { get { return Serialize.BrushToString(MagnetBrush); } set { MagnetBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "+GEX Node", Order = 24, GroupName = "3. Colors")]
        public Brush PositiveNodeBrush { get; set; }
        [Browsable(false)] public string PositiveNodeBrushSerialize { get { return Serialize.BrushToString(PositiveNodeBrush); } set { PositiveNodeBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "-GEX Node", Order = 25, GroupName = "3. Colors")]
        public Brush NegativeNodeBrush { get; set; }
        [Browsable(false)] public string NegativeNodeBrushSerialize { get { return Serialize.BrushToString(NegativeNodeBrush); } set { NegativeNodeBrush = Serialize.StringToBrush(value); } }
        #endregion

        #region Data Classes
        public class V3Payload
        {
            public string schema { get; set; }
            public string service { get; set; }
            public string service_version { get; set; }
            public string generated_at_utc { get; set; }
            public int sequence { get; set; }
            public List<V3Asset> assets { get; set; }
            public List<string> errors { get; set; }
        }

        public class V3Asset
        {
            public string asset_id { get; set; }
            public string futures_root { get; set; }
            public string underlying { get; set; }
            public double underlying_spot { get; set; }
            public string futures_symbol { get; set; }
            public double futures_spot { get; set; }
            public V3Mapping mapping { get; set; }
            public V3Freshness freshness { get; set; }
            public V3Chain chain { get; set; }
            public V3Selection selection { get; set; }
            public List<V3Level> levels { get; set; }
            public List<V3Level> levels_list { get; set; }
            public string chain_error { get; set; }
            public bool stale { get; set; }
            public int age_seconds { get; set; }
            public string as_of_utc { get; set; }
        }

        public class V3Mapping { public string method { get; set; } public double ratio { get; set; } public string source { get; set; } public double source_spot { get; set; } public double target_spot { get; set; } public string computed_at_utc { get; set; } }
        public class V3Freshness { public int generated_age_s { get; set; } public int chain_snapshot_age_s { get; set; } public int spot_age_s { get; set; } public int futures_spot_age_s { get; set; } public bool stale { get; set; } public bool very_stale { get; set; } }
        public class V3Chain { public int snapshot_contracts { get; set; } public int used_contracts { get; set; } public int strike_count { get; set; } public int pages { get; set; } public int max_dte { get; set; } public string snapshot_source { get; set; } public string chain_error { get; set; } }
        public class V3Selection { public bool spot_centered { get; set; } public string center_source { get; set; } public double window_pct { get; set; } public double max_above_pct { get; set; } public double max_below_pct { get; set; } public int candidate_strikes { get; set; } public int max_levels { get; set; } public string algorithm { get; set; } }
        public class V3Level
        {
            public string id { get; set; }
            public string key { get; set; }
            public string role { get; set; }
            public string symbol { get; set; }
            public string label { get; set; }
            public string action { get; set; }
            public string side { get; set; }
            public string source_underlying { get; set; }
            public double source_strike { get; set; }
            public double source_price { get; set; }
            public double mapped_price { get; set; }
            public double price { get; set; }
            public double gex { get; set; }
            public double value { get; set; }
            public int abs_gex_rank { get; set; }
            public double distance_from_spot_source { get; set; }
            public double distance_from_futures_spot { get; set; }
            public bool is_pinned { get; set; }
            public double confidence { get; set; }
            [ScriptIgnore]
            public double _distance { get; set; }
        }
        #endregion
    }
}
