#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
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
using Brushes = System.Windows.Media.Brushes;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    /// <summary>
    /// DEEP6 MBO Heat Map — renders live NT8 MarketDepth liquidity levels as a heat map overlay.
    /// Native architecture: NT8 MarketDepth → DOMAccumulator → SharpDX heat map.
    /// </summary>
    public class DEEP6MBOHeatMap : Indicator
    {
        private const int ComputeIntervalMs = 2000;

        private readonly object sync = new object();
        private Timer computeTimer;
        private DOMAccumulator accumulator;
        private RenderSnapshot payload;
        private string statusText = "MBO: Waiting for MarketDepth...";
        private DateTime lastDepthUtc = DateTime.MinValue;

        // --- SharpDX brushes (created in OnRenderTargetChanged, disposed on change/terminate) ---
        private SharpDX.Direct2D1.Brush dxText;
        private SharpDX.Direct2D1.Brush dxMuted;
        private SharpDX.Direct2D1.Brush dxPanel;
        private SharpDX.Direct2D1.Brush dxBorder;
        private SharpDX.Direct2D1.Brush dxBidLow;      // low-heat bid: dim cyan
        private SharpDX.Direct2D1.Brush dxBidMid;      // mid-heat bid: cyan
        private SharpDX.Direct2D1.Brush dxBidHigh;     // high-heat bid: bright cyan
        private SharpDX.Direct2D1.Brush dxAskLow;      // low-heat ask: dim red
        private SharpDX.Direct2D1.Brush dxAskMid;      // mid-heat ask: red
        private SharpDX.Direct2D1.Brush dxAskHigh;     // high-heat ask: bright red
        private SharpDX.Direct2D1.Brush dxAmber;       // stale warning
        private SharpDX.Direct2D1.Brush dxGreen;       // OK status
        private SharpDX.Direct2D1.Brush dxHalo;        // shadow behind lines
        private SharpDX.Direct2D1.Brush dxRefill;      // refill indicator (gold)

        // --- Text formats ---
        private TextFormat fontSmall;
        private TextFormat fontNormal;
        private TextFormat fontBold;
        private TextFormat fontData;

        // --- Stroke styles ---
        private StrokeStyle dashedStyle;

        #region Lifecycle

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 MBO Heat Map — renders live NT8 MarketDepth DOM liquidity as a heat map overlay.";
                Name = "DEEP6 MBO Heat Map";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                ScaleJustification = ScaleJustification.Right;
                IsSuspendedWhileInactive = false;

                WallMinSize = 100;
                WallStaleSec = 90;
                DecayHalfLifeSec = 120;
                MaxRenderedLevels = 4;
                MaxDistancePoints = 200;
                ShowStatus = true;
                ShowBands = true;
                BandWidthPoints = 2.0;
                MinHeatToRender = 0.15;
                LineOpacity = 85;
                BandOpacity = 22;

                BidLevelBrush = Brushes.Cyan;
                AskLevelBrush = Brushes.IndianRed;
                WallBrush = Brushes.Gold;
            }
            else if (State == State.Configure)
            {
                var factory = NinjaTrader.Core.Globals.D2DFactory;
                dashedStyle = new StrokeStyle(factory, new StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Dash });
            }
            else if (State == State.DataLoaded)
            {
                accumulator = new DOMAccumulator(WallMinSize, WallStaleSec, MaxRenderedLevels, DecayHalfLifeSec);
                statusText = "MBO: Waiting for MarketDepth...";
                payload = null;
                lastDepthUtc = DateTime.MinValue;
                computeTimer = new Timer(ComputeSnapshotSafe, null, 250, ComputeIntervalMs);
            }
            else if (State == State.Terminated)
            {
                if (computeTimer != null)
                {
                    computeTimer.Dispose();
                    computeTimer = null;
                }

                accumulator = null;
                payload = null;
                DisposeDx();
                SafeDispose(ref dashedStyle);
            }
        }

        protected override void OnBarUpdate() { }

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (e == null) return;
            if (e.MarketDataType != MarketDataType.Bid && e.MarketDataType != MarketDataType.Ask) return;

            int size = e.Operation == Operation.Remove ? 0 : SafeToInt(e.Volume);

            lock (sync)
            {
                if (accumulator == null) return;
                accumulator.OnMarketDepth(e.MarketDataType, e.Position, e.Price, size, e.Operation);
                lastDepthUtc = DateTime.UtcNow;
            }
        }

        #endregion

        #region Brush Lifecycle

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            float lineA = LineOpacity / 100f;
            float bandA = BandOpacity / 100f;

            // Text / UI
            dxText   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.949f, 0.957f, 0.973f, 1f));       // #F2F4F8
            dxMuted  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.608f, 0.639f, 0.682f, 1f));       // #9BA3AE
            dxPanel  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.04f, 0.05f, 0.07f, 0.88f));       // dark panel bg
            dxBorder = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.149f, 0.173f, 0.212f, 1f));       // #262C36
            dxAmber  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(1f, 0.702f, 0f, 1f));               // #FFB300
            dxGreen  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0f, 0.902f, 0.463f, 1f));           // #00E676
            dxHalo   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0f, 0f, 0f, 0.70f));
            dxRefill = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(1f, 0.824f, 0.247f, 1f));           // #FFD23F

            // Bid heat tiers: cyan spectrum
            dxBidLow  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0f, 0.878f, 1f, 0.35f * lineA));   // dim cyan
            dxBidMid  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0f, 0.878f, 1f, 0.65f * lineA));   // mid cyan
            dxBidHigh = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0f, 0.878f, 1f, 1f * lineA));      // bright cyan

            // Ask heat tiers: red spectrum
            dxAskLow  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(1f, 0.090f, 0.267f, 0.35f * lineA));
            dxAskMid  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(1f, 0.090f, 0.267f, 0.65f * lineA));
            dxAskHigh = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(1f, 0.090f, 0.267f, 1f * lineA));

            var dwFactory = NinjaTrader.Core.Globals.DirectWriteFactory;
            fontSmall  = new TextFormat(dwFactory, "Segoe UI", 10f);
            fontNormal = new TextFormat(dwFactory, "Segoe UI Semibold", 11f);
            fontBold   = new TextFormat(dwFactory, "Segoe UI Bold", 12f);
            fontData   = new TextFormat(dwFactory, "Consolas", SharpDX.DirectWrite.FontWeight.Medium, SharpDX.DirectWrite.FontStyle.Normal, 11f);
        }

        private void DisposeDx()
        {
            SafeDispose(ref fontSmall);
            SafeDispose(ref fontNormal);
            SafeDispose(ref fontBold);
            SafeDispose(ref fontData);
            SafeDispose(ref dxText);
            SafeDispose(ref dxMuted);
            SafeDispose(ref dxPanel);
            SafeDispose(ref dxBorder);
            SafeDispose(ref dxBidLow);
            SafeDispose(ref dxBidMid);
            SafeDispose(ref dxBidHigh);
            SafeDispose(ref dxAskLow);
            SafeDispose(ref dxAskMid);
            SafeDispose(ref dxAskHigh);
            SafeDispose(ref dxAmber);
            SafeDispose(ref dxGreen);
            SafeDispose(ref dxHalo);
            SafeDispose(ref dxRefill);
        }

        private static void SafeDispose<T>(ref T resource) where T : class, IDisposable
        {
            if (resource != null)
            {
                try { resource.Dispose(); } catch { }
                resource = null;
            }
        }

        #endregion

        #region Live Snapshot Build

        private void ComputeSnapshotSafe(object state)
        {
            try { ComputeSnapshot(); }
            catch (Exception ex)
            {
                lock (sync) statusText = "MBO compute error: " + Shorten(ex.Message, 100);
                RefreshChart();
            }
        }

        private void ComputeSnapshot()
        {
            RenderSnapshot nextPayload;
            string nextStatus;

            lock (sync)
            {
                if (accumulator == null) return;

                accumulator.Reconfigure(WallMinSize, WallStaleSec, MaxRenderedLevels, DecayHalfLifeSec);
                nextPayload = accumulator.BuildSnapshot(DateTime.UtcNow);
                payload = nextPayload;
                nextStatus = BuildStatus(nextPayload, accumulator);
                statusText = nextStatus;
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

        private string BuildStatus(RenderSnapshot p, DOMAccumulator dom)
        {
            if (dom == null || !dom.HasDepth)
                return "MBO: Waiting for MarketDepth...";

            int bidLevels = p != null && p.levels != null ? p.levels.Count(l => l.side == "bid") : 0;
            int askLevels = p != null && p.levels != null ? p.levels.Count(l => l.side == "ask") : 0;

            return string.Format(CultureInfo.InvariantCulture,
                "MBO LIVE | {0} bid / {1} ask | mid={2:F2} | {3} tracked",
                bidLevels,
                askLevels,
                dom.MidPrice,
                dom.TrackedLevelCount);
        }

        private static int SafeToInt(long value)
        {
            if (value <= 0) return 0;
            return value >= int.MaxValue ? int.MaxValue : (int)value;
        }

        #endregion

        #region Rendering

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (RenderTarget == null || ChartPanel == null || fontSmall == null) return;

            RenderSnapshot localPayload;
            string localStatus;
            DateTime localDepthUtc;
            lock (sync)
            {
                localPayload = payload;
                localStatus = statusText;
                localDepthUtc = lastDepthUtc;
            }

            bool stale = false;
            if (localDepthUtc != DateTime.MinValue)
                stale = (DateTime.UtcNow - localDepthUtc).TotalSeconds > Math.Max(WallStaleSec, ComputeIntervalMs / 1000.0 * 2.0);

            if (ShowStatus) DrawStatus(localStatus, localPayload, stale);
            if (localPayload == null || localPayload.levels == null || localPayload.levels.Count == 0) return;

            DrawHeatLevels(localPayload, chartScale, stale);
        }

        private void DrawStatus(string text, RenderSnapshot p, bool stale)
        {
            if (dxPanel == null || dxText == null) return;
            float x = (float)ChartPanel.X + 8f;
            float y = (float)ChartPanel.Y + 6f;
            float w = 540f;
            float h = 24f;

            RenderTarget.FillRectangle(new RectangleF(x, y, w, h), dxPanel);
            RenderTarget.DrawRectangle(new RectangleF(x, y, w, h), dxBorder ?? dxText, 1f);

            SharpDX.Direct2D1.Brush statusBrush = stale ? (dxAmber ?? dxText) : p == null ? (dxMuted ?? dxText) : (dxGreen ?? dxText);
            DrawText(x + 6f, y + 4f, text ?? "", fontSmall, statusBrush, w - 12f, h - 6f);
        }

        private void DrawHeatLevels(RenderSnapshot p, ChartScale chartScale, bool stale)
        {
            double refPrice = 0;
            try
            {
                if (CurrentBar >= 0 && Close != null && Close.Count > 0 && Close[0] > 0)
                    refPrice = Close[0];
            }
            catch { }
            if (refPrice <= 0 && p.mid_price > 0) refPrice = p.mid_price;
            if (refPrice <= 0) return;

            double maxDist = Math.Max(1, MaxDistancePoints);
            var candidates = new List<MBOLevel>();
            foreach (var lvl in p.levels)
            {
                if (lvl == null || lvl.price <= 0) continue;
                if (lvl.heat < MinHeatToRender) continue;
                double dist = lvl.distance != 0 ? lvl.distance : lvl.price - refPrice;
                if (Math.Abs(dist) > maxDist) continue;
                candidates.Add(lvl);
            }

            // Sort by heat descending, take top N per side
            var bids = candidates.Where(l => l.side == "bid").OrderByDescending(l => l.heat).Take(MaxRenderedLevels).ToList();
            var asks = candidates.Where(l => l.side == "ask").OrderByDescending(l => l.heat).Take(MaxRenderedLevels).ToList();
            var toRender = bids.Concat(asks).ToList();
            if (toRender.Count == 0) return;

            float left = (float)ChartPanel.X + 2f;
            float right = (float)(ChartPanel.X + ChartPanel.W) - 4f;
            float labelW = 190f;
            double min = chartScale.MinValue;
            double max = chartScale.MaxValue;

            foreach (var lvl in toRender)
            {
                if (lvl.price < min || lvl.price > max) continue;

                float y = chartScale.GetYByValue(lvl.price);
                bool isBid = lvl.side == "bid";
                SharpDX.Direct2D1.Brush lineBrush = GetHeatBrush(lvl.heat, isBid);
                float lineWidth = 1.0f + (float)lvl.heat * 2.0f;

                if (stale)
                    lineWidth = Math.Max(0.8f, lineWidth * 0.5f);

                // Draw heat band (filled rectangle around the price level)
                if (ShowBands && BandWidthPoints > 0)
                {
                    float bandTop = chartScale.GetYByValue(lvl.price + BandWidthPoints * 0.5);
                    float bandBot = chartScale.GetYByValue(lvl.price - BandWidthPoints * 0.5);
                    float bandAlpha = (float)(lvl.heat * BandOpacity / 100.0);
                    Color4 bandColor = isBid
                        ? new Color4(0f, 0.878f, 1f, bandAlpha)      // cyan band
                        : new Color4(1f, 0.090f, 0.267f, bandAlpha); // red band

                    using (var bandBrush = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, bandColor))
                    {
                        RenderTarget.AntialiasMode = AntialiasMode.Aliased;
                        RenderTarget.FillRectangle(new RectangleF(left, bandTop, right - labelW - left, bandBot - bandTop), bandBrush);
                        RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;
                    }
                }

                // Draw shadow + line
                RenderTarget.DrawLine(new Vector2(left, y), new Vector2(right - labelW - 8f, y), dxHalo ?? lineBrush, lineWidth + 2f);
                RenderTarget.DrawLine(new Vector2(left, y), new Vector2(right - labelW - 8f, y), lineBrush, lineWidth);

                // Draw refill indicator (small gold diamond on the line)
                if (lvl.refill_count > 0 && dxRefill != null)
                {
                    float diamX = left + 20f;
                    float diamSize = 4f;
                    RenderTarget.DrawLine(new Vector2(diamX, y - diamSize), new Vector2(diamX + diamSize, y), dxRefill, 1.5f);
                    RenderTarget.DrawLine(new Vector2(diamX + diamSize, y), new Vector2(diamX, y + diamSize), dxRefill, 1.5f);
                    RenderTarget.DrawLine(new Vector2(diamX, y + diamSize), new Vector2(diamX - diamSize, y), dxRefill, 1.5f);
                    RenderTarget.DrawLine(new Vector2(diamX - diamSize, y), new Vector2(diamX, y - diamSize), dxRefill, 1.5f);
                }

                // Label box
                string label = BuildLabel(lvl);
                DrawLabelBox(right - labelW, y - 12f, labelW - 4f, 24f, label, lineBrush, isBid, lvl.heat);
            }
        }

        private SharpDX.Direct2D1.Brush GetHeatBrush(double heat, bool isBid)
        {
            if (isBid)
            {
                if (heat >= 0.7) return dxBidHigh ?? dxText;
                if (heat >= 0.4) return dxBidMid ?? dxText;
                return dxBidLow ?? dxText;
            }
            else
            {
                if (heat >= 0.7) return dxAskHigh ?? dxText;
                if (heat >= 0.4) return dxAskMid ?? dxText;
                return dxAskLow ?? dxText;
            }
        }

        private string BuildLabel(MBOLevel lvl)
        {
            string side = lvl.side == "bid" ? "BID" : "ASK";
            string wallTag = lvl.is_wall ? " ★" : "";
            string refillTag = lvl.refill_count > 0 ? string.Format(" R{0}", lvl.refill_count) : "";
            string persist = lvl.persistence_sec > 0 ? string.Format(" {0}s", (int)lvl.persistence_sec) : "";
            return string.Format(CultureInfo.InvariantCulture,
                "{0} {1:0.00}  {2}{3}{4}{5}",
                side, lvl.price, lvl.current_size, wallTag, refillTag, persist);
        }

        private void DrawLabelBox(float x, float y, float w, float h, string text,
            SharpDX.Direct2D1.Brush accent, bool isBid, double heat)
        {
            // Panel background
            RenderTarget.FillRectangle(new RectangleF(x, y, w, h), dxPanel ?? accent);
            RenderTarget.DrawRectangle(new RectangleF(x, y, w, h), dxBorder ?? accent, 1f);

            // Left accent stripe (4px, color = heat tier)
            RenderTarget.FillRectangle(new RectangleF(x, y, 4f, h), accent);

            // Heat bar (thin bar across bottom showing relative intensity)
            float barWidth = (float)(heat * (w - 8f));
            Color4 barColor = isBid
                ? new Color4(0f, 0.878f, 1f, 0.4f)
                : new Color4(1f, 0.090f, 0.267f, 0.4f);
            using (var barBrush = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, barColor))
            {
                RenderTarget.FillRectangle(new RectangleF(x + 4f, y + h - 3f, barWidth, 3f), barBrush);
            }

            // Text
            DrawText(x + 8f, y + 3f, text, fontData ?? fontNormal, dxText ?? accent, w - 12f, h - 4f);
        }

        private void DrawText(float x, float y, string text, TextFormat font, SharpDX.Direct2D1.Brush brush, float width, float height)
        {
            if (string.IsNullOrEmpty(text) || font == null || brush == null) return;
            using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, text, font, width, height))
                RenderTarget.DrawTextLayout(new Vector2(x, y), layout, brush);
        }

        private static string Shorten(string text, int max)
        {
            if (string.IsNullOrEmpty(text) || text.Length <= max) return text ?? string.Empty;
            return text.Substring(0, max - 3) + "...";
        }

        #endregion

        #region Properties

        [NinjaScriptProperty]
        [Range(1, 5000)]
        [Display(Name = "Wall Min Size", Order = 1, GroupName = "1. Data")]
        public int WallMinSize { get; set; }

        [NinjaScriptProperty]
        [Range(1.0, 3600.0)]
        [Display(Name = "Wall Stale Sec", Order = 2, GroupName = "1. Data")]
        public double WallStaleSec { get; set; }

        [NinjaScriptProperty]
        [Range(1.0, 3600.0)]
        [Display(Name = "Decay Half-Life Sec", Order = 3, GroupName = "1. Data")]
        public double DecayHalfLifeSec { get; set; }

        [NinjaScriptProperty]
        [Range(1, 12)]
        [Display(Name = "Max Rendered Levels", Order = 10, GroupName = "2. Display")]
        public int MaxRenderedLevels { get; set; }

        [NinjaScriptProperty]
        [Range(10, 2000)]
        [Display(Name = "Max Distance Points", Order = 11, GroupName = "2. Display",
            Description = "Only render levels within this distance from current price")]
        public int MaxDistancePoints { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Status", Order = 12, GroupName = "2. Display")]
        public bool ShowStatus { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Heat Bands", Order = 13, GroupName = "2. Display",
            Description = "Render filled bands around significant levels")]
        public bool ShowBands { get; set; }

        [NinjaScriptProperty]
        [Range(0.25, 20.0)]
        [Display(Name = "Band Width (Points)", Order = 14, GroupName = "2. Display")]
        public double BandWidthPoints { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 1.0)]
        [Display(Name = "Min Heat to Render", Order = 15, GroupName = "2. Display",
            Description = "Levels below this heat value are hidden (0.0–1.0)")]
        public double MinHeatToRender { get; set; }

        [NinjaScriptProperty]
        [Range(10, 100)]
        [Display(Name = "Line Opacity %", Order = 16, GroupName = "2. Display")]
        public int LineOpacity { get; set; }

        [NinjaScriptProperty]
        [Range(5, 60)]
        [Display(Name = "Band Opacity %", Order = 17, GroupName = "2. Display")]
        public int BandOpacity { get; set; }

        [XmlIgnore]
        [Display(Name = "Bid Level Color", Order = 20, GroupName = "3. Colors")]
        public Brush BidLevelBrush { get; set; }
        [Browsable(false)] public string BidLevelBrushSerialize { get { return Serialize.BrushToString(BidLevelBrush); } set { BidLevelBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Ask Level Color", Order = 21, GroupName = "3. Colors")]
        public Brush AskLevelBrush { get; set; }
        [Browsable(false)] public string AskLevelBrushSerialize { get { return Serialize.BrushToString(AskLevelBrush); } set { AskLevelBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Wall Highlight", Order = 22, GroupName = "3. Colors")]
        public Brush WallBrush { get; set; }
        [Browsable(false)] public string WallBrushSerialize { get { return Serialize.BrushToString(WallBrush); } set { WallBrush = Serialize.StringToBrush(value); } }

        #endregion

        #region Data Classes

        private sealed class RenderSnapshot
        {
            public DateTime generated_at_utc { get; set; }
            public double mid_price { get; set; }
            public double spread { get; set; }
            public int total_bid_depth { get; set; }
            public int total_ask_depth { get; set; }
            public List<MBOLevel> levels { get; set; }
        }

        private sealed class OrderBookLevel
        {
            public int Position { get; set; }
            public double Price { get; set; }
            public int Size { get; set; }
        }

        private sealed class LevelTracker
        {
            public double price { get; set; }
            public string side { get; set; }
            public int current_size { get; set; }
            public int peak_size { get; set; }
            public double first_seen { get; set; }
            public double last_seen { get; set; }
            public int last_size { get; set; }
            public int refill_count { get; set; }
            public int snapshots { get; set; }
            public double cumulative_size { get; set; }
            public double heat { get; set; }

            public double persistence_sec
            {
                get
                {
                    if (first_seen <= 0 || last_seen <= 0) return 0.0;
                    return Math.Max(0.0, last_seen - first_seen);
                }
            }
        }

        private sealed class DOMAccumulator
        {
            private readonly Dictionary<int, OrderBookLevel> bidBookByPosition = new Dictionary<int, OrderBookLevel>();
            private readonly Dictionary<int, OrderBookLevel> askBookByPosition = new Dictionary<int, OrderBookLevel>();
            private readonly Dictionary<double, LevelTracker> bidLevels = new Dictionary<double, LevelTracker>();
            private readonly Dictionary<double, LevelTracker> askLevels = new Dictionary<double, LevelTracker>();

            public DOMAccumulator(int wallMinSize, double wallStaleSec, int maxLevelsPerSide, double decayHalfLifeSec)
            {
                Reconfigure(wallMinSize, wallStaleSec, maxLevelsPerSide, decayHalfLifeSec);
            }

            public int WallMinSize { get; private set; }
            public double WallStaleSec { get; private set; }
            public int MaxLevelsPerSide { get; private set; }
            public double DecayHalfLifeSec { get; private set; }
            public double MidPrice { get; private set; }
            public double Spread { get; private set; }
            public int TotalBidDepth { get; private set; }
            public int TotalAskDepth { get; private set; }
            public int SnapshotCount { get; private set; }
            public bool HasDepth { get { return bidBookByPosition.Count > 0 || askBookByPosition.Count > 0; } }
            public int TrackedLevelCount { get { return bidLevels.Count + askLevels.Count; } }

            public void Reconfigure(int wallMinSize, double wallStaleSec, int maxLevelsPerSide, double decayHalfLifeSec)
            {
                WallMinSize = Math.Max(1, wallMinSize);
                WallStaleSec = Math.Max(1.0, wallStaleSec);
                MaxLevelsPerSide = Math.Max(1, maxLevelsPerSide);
                DecayHalfLifeSec = Math.Max(1.0, decayHalfLifeSec);
            }

            public void OnMarketDepth(MarketDataType side, int position, double price, int size, Operation operation)
            {
                if (position < 0 || price <= 0) return;

                Dictionary<int, OrderBookLevel> book = side == MarketDataType.Bid ? bidBookByPosition : askBookByPosition;

                if (operation == Operation.Remove || size <= 0)
                {
                    book.Remove(position);
                    return;
                }

                book[position] = new OrderBookLevel
                {
                    Position = position,
                    Price = price,
                    Size = size
                };
            }

            public RenderSnapshot BuildSnapshot(DateTime utcNow)
            {
                double now = MonotonicSeconds();
                SnapshotCount++;

                List<Tuple<double, int>> bids = bidBookByPosition.Values
                    .Where(l => l != null && l.Price > 0 && l.Size > 0)
                    .OrderBy(l => l.Position)
                    .Select(l => Tuple.Create(l.Price, l.Size))
                    .ToList();

                List<Tuple<double, int>> asks = askBookByPosition.Values
                    .Where(l => l != null && l.Price > 0 && l.Size > 0)
                    .OrderBy(l => l.Position)
                    .Select(l => Tuple.Create(l.Price, l.Size))
                    .ToList();

                if (bids.Count > 0 && asks.Count > 0)
                {
                    MidPrice = (bids[0].Item1 + asks[0].Item1) / 2.0;
                    Spread = asks[0].Item1 - bids[0].Item1;
                }

                TotalBidDepth = bids.Sum(x => x.Item2);
                TotalAskDepth = asks.Sum(x => x.Item2);

                var seenBidPrices = new HashSet<double>();
                foreach (var bid in bids)
                {
                    seenBidPrices.Add(bid.Item1);
                    UpdateLevel(bidLevels, bid.Item1, "bid", bid.Item2, now);
                }

                var seenAskPrices = new HashSet<double>();
                foreach (var ask in asks)
                {
                    seenAskPrices.Add(ask.Item1);
                    UpdateLevel(askLevels, ask.Item1, "ask", ask.Item2, now);
                }

                PruneStale(bidLevels, seenBidPrices, now);
                PruneStale(askLevels, seenAskPrices, now);

                return new RenderSnapshot
                {
                    generated_at_utc = utcNow,
                    mid_price = MidPrice,
                    spread = Spread,
                    total_bid_depth = TotalBidDepth,
                    total_ask_depth = TotalAskDepth,
                    levels = GetSignificantLevels(utcNow)
                };
            }

            private void UpdateLevel(Dictionary<double, LevelTracker> levels, double price, string side, int size, double now)
            {
                LevelTracker tracker;
                if (!levels.TryGetValue(price, out tracker))
                {
                    tracker = new LevelTracker
                    {
                        price = price,
                        side = side,
                        first_seen = now
                    };
                    levels[price] = tracker;
                }

                int prevSize = tracker.current_size;
                double dt = tracker.last_seen > 0 ? now - tracker.last_seen : 0.0;

                if (prevSize > 0 && tracker.last_size < prevSize * 0.3 && size >= prevSize * 0.7)
                    tracker.refill_count++;

                double decay = dt > 0 ? Math.Pow(0.5, dt / Math.Max(DecayHalfLifeSec, 1.0)) : 1.0;
                tracker.cumulative_size = tracker.cumulative_size * decay + size;

                tracker.last_size = tracker.current_size;
                tracker.current_size = size;
                tracker.peak_size = Math.Max(tracker.peak_size, size);
                tracker.last_seen = now;
                tracker.snapshots++;
            }

            private void PruneStale(Dictionary<double, LevelTracker> levels, HashSet<double> seenPrices, double now)
            {
                List<double> stalePrices = new List<double>();
                foreach (var kvp in levels)
                {
                    if (!seenPrices.Contains(kvp.Key) && (now - kvp.Value.last_seen) > WallStaleSec)
                        stalePrices.Add(kvp.Key);
                }

                foreach (double stalePrice in stalePrices)
                    levels.Remove(stalePrice);
            }

            private List<MBOLevel> GetSignificantLevels(DateTime utcNow)
            {
                List<LevelTracker> allLevels = new List<LevelTracker>();

                foreach (LevelTracker tracker in bidLevels.Values)
                    if (tracker.current_size >= WallMinSize)
                        allLevels.Add(tracker);

                foreach (LevelTracker tracker in askLevels.Values)
                    if (tracker.current_size >= WallMinSize)
                        allLevels.Add(tracker);

                if (allLevels.Count == 0)
                    return new List<MBOLevel>();

                double maxCumulative = allLevels.Max(t => t.cumulative_size);
                if (maxCumulative <= 0)
                    maxCumulative = 1.0;

                foreach (LevelTracker tracker in allLevels)
                {
                    double rawHeat = tracker.cumulative_size / maxCumulative;
                    double persistenceBoost = Math.Min(tracker.persistence_sec / 300.0, 0.3);
                    double refillBoost = Math.Min(tracker.refill_count * 0.1, 0.2);
                    tracker.heat = Math.Max(0.0, Math.Min(1.0, rawHeat + persistenceBoost + refillBoost));
                }

                List<LevelTracker> topBids = allLevels
                    .Where(t => t.side == "bid")
                    .OrderByDescending(t => t.heat)
                    .Take(MaxLevelsPerSide)
                    .ToList();

                List<LevelTracker> topAsks = allLevels
                    .Where(t => t.side == "ask")
                    .OrderByDescending(t => t.heat)
                    .Take(MaxLevelsPerSide)
                    .ToList();

                List<MBOLevel> result = new List<MBOLevel>();
                foreach (LevelTracker tracker in topBids.Concat(topAsks).OrderByDescending(t => t.heat))
                {
                    DateTime firstUtc = utcNow - TimeSpan.FromSeconds(Math.Max(0.0, MonotonicSeconds() - tracker.first_seen));
                    DateTime lastUtc = utcNow - TimeSpan.FromSeconds(Math.Max(0.0, MonotonicSeconds() - tracker.last_seen));

                    result.Add(new MBOLevel
                    {
                        price = tracker.price,
                        side = tracker.side,
                        current_size = tracker.current_size,
                        peak_size = tracker.peak_size,
                        heat = Math.Round(tracker.heat, 4),
                        persistence_sec = Math.Round(tracker.persistence_sec, 1),
                        first_seen_utc = firstUtc.ToString("o", CultureInfo.InvariantCulture),
                        last_seen_utc = lastUtc.ToString("o", CultureInfo.InvariantCulture),
                        refill_count = tracker.refill_count,
                        is_wall = tracker.current_size >= WallMinSize,
                        distance = MidPrice > 0 ? Math.Round(tracker.price - MidPrice, 2) : 0.0
                    });
                }

                return result;
            }

            private static double MonotonicSeconds()
            {
                return (double)DateTime.UtcNow.Ticks / TimeSpan.TicksPerSecond;
            }
        }

        public class MBOLevel
        {
            public double price { get; set; }
            public string side { get; set; }
            public int current_size { get; set; }
            public int peak_size { get; set; }
            public double heat { get; set; }
            public double persistence_sec { get; set; }
            public string first_seen_utc { get; set; }
            public string last_seen_utc { get; set; }
            public int refill_count { get; set; }
            public bool is_wall { get; set; }
            public double distance { get; set; }
        }

        #endregion
    }
}
