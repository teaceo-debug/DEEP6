#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
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
using Color = System.Windows.Media.Color;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6LiquidityHeatMap : Indicator
    {
        private const int PaletteTiers = 20;
        private const int InvalidateIntervalMs = 50;
        private const double FadeOutSeconds = 2.0;

        private readonly Dictionary<double, LiquidityLevel> bidLevels = new Dictionary<double, LiquidityLevel>();
        private readonly Dictionary<double, LiquidityLevel> askLevels = new Dictionary<double, LiquidityLevel>();
        private readonly List<double> pruneKeys = new List<double>(256);
        private readonly byte[] alphaLut = new byte[PaletteTiers];

        private Timer invalidateTimer;
        private SharpDX.Direct2D1.Brush[] dxBidTierBrushes;
        private SharpDX.Direct2D1.Brush[] dxAskTierBrushes;
        private SharpDX.Direct2D1.Brush dxHudText;
        private SharpDX.Direct2D1.Brush dxHudPanel;
        private SharpDX.Direct2D1.Brush dxHudBorder;
        private SharpDX.Direct2D1.Brush dxPriceLine;
        private TextFormat hudFont;

        private LiquidityLevel[] renderBids = new LiquidityLevel[0];
        private LiquidityLevel[] renderAsks = new LiquidityLevel[0];
        private int renderPeakSize = 1;
        private int renderActiveBidCount;
        private int renderActiveAskCount;
        private int renderRecentBidCount;
        private int renderRecentAskCount;
        private int renderHasFadingLevels;

        private int dirtyFlag;
        private int snapshotFailureCount;
        private int sessionPeakSize = 1;
        private int pruneCountdown;
        private double actualTickSize = 0.25;
        private long depthCallbackCount;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 Liquidity Heat Map — thick DOM liquidity bands rendered behind price.";
                Name = "DEEP6 Liquidity Heat Map";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DrawOnPricePanel = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                ScaleJustification = ScaleJustification.Right;
                IsSuspendedWhileInactive = false;

                MinSizeFilter = 20;
                ReferenceMax = 500;
                MaxOpacityPct = 80;
                MinPersistenceSeconds = 0.5;
                MinDistancePoints = 0;
                ShowBidDepth = true;
                ShowAskDepth = true;
                ShowDOMLadder = true;
                DOMLadderWidth = 80;
                StaleSeconds = 30;
                DepthLevels = 40;
                BidColor = MakeFrozenBrush(Color.FromRgb(0x00, 0xE0, 0xFF));
                AskColor = MakeFrozenBrush(Color.FromRgb(0xFF, 0x17, 0x44));
            }
            else if (State == State.Configure)
            {
                actualTickSize = TickSize > 0 ? TickSize : 0.25;
            }
            else if (State == State.DataLoaded)
            {
                actualTickSize = TickSize > 0 ? TickSize : 0.25;
                BuildAlphaLookupTable();
                ClearAllLevels();
                renderPeakSize = Math.Max(1, ReferenceMax);
                Interlocked.Exchange(ref dirtyFlag, 1);
                if (invalidateTimer == null)
                    invalidateTimer = new Timer(OnInvalidateTimer, null, InvalidateIntervalMs, InvalidateIntervalMs);
            }
            else if (State == State.Historical)
            {
                try { SetZOrder(-1); } catch { }
            }
            else if (State == State.Terminated)
            {
                if (invalidateTimer != null)
                {
                    invalidateTimer.Dispose();
                    invalidateTimer = null;
                }

                DisposeDx();
                ClearAllLevels();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;

            if (CurrentBar < 0)
                return;

            actualTickSize = TickSize > 0 ? TickSize : actualTickSize;

            if (Bars.IsFirstBarOfSession && IsFirstTickOfBar)
            {
                ClearAllLevels();
                Interlocked.Exchange(ref depthCallbackCount, 0);
                Interlocked.Exchange(ref dirtyFlag, 1);
            }
        }

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (e == null)
                return;

            Interlocked.Increment(ref depthCallbackCount);

            if (e.MarketDataType != MarketDataType.Bid && e.MarketDataType != MarketDataType.Ask)
                return;

            if (DepthLevels > 0 && e.Position >= DepthLevels)
                return;

            if (e.Price <= 0)
                return;

            int size = e.Operation == Operation.Remove ? 0 : SafeToInt(e.Volume);
            DateTime nowUtc = DateTime.UtcNow;

            Dictionary<double, LiquidityLevel> book = e.MarketDataType == MarketDataType.Bid ? bidLevels : askLevels;
            LiquidityLevel level;
            if (!book.TryGetValue(e.Price, out level))
            {
                level = new LiquidityLevel();
                level.Price = e.Price;
                level.FirstSeen = nowUtc;
                level.LastSeen = nowUtc;
                level.LastNonZero = DateTime.MinValue;
                level.IsActive = false;
                book[e.Price] = level;
            }

            level.LastSeen = nowUtc;

            int priorSize = level.CurrentSize;

            if (e.Operation == Operation.Remove || size <= 0)
            {
                if (priorSize > 0 || level.LastNonZero == DateTime.MinValue)
                    level.LastNonZero = nowUtc;
                level.CurrentSize = 0;
                level.IsActive = false;
            }
            else
            {
                level.CurrentSize = size;
                level.IsActive = true;
                level.LastNonZero = nowUtc;
                level.LastNonZeroSize = size;
                if (level.PeakSize < size)
                    level.PeakSize = size;
                if (sessionPeakSize < size)
                    sessionPeakSize = size;
            }

            pruneCountdown++;
            if (pruneCountdown >= 64)
            {
                pruneCountdown = 0;
                PruneStaleLevels(bidLevels, nowUtc);
                PruneStaleLevels(askLevels, nowUtc);
            }

            Interlocked.Exchange(ref dirtyFlag, 1);
        }

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null)
                return;

            BuildAlphaLookupTable();

            Color bid = ExtractBrushColor(BidColor, Color.FromRgb(0x00, 0xE0, 0xFF));
            Color ask = ExtractBrushColor(AskColor, Color.FromRgb(0xFF, 0x17, 0x44));

            dxBidTierBrushes = new SharpDX.Direct2D1.Brush[PaletteTiers];
            dxAskTierBrushes = new SharpDX.Direct2D1.Brush[PaletteTiers];

            for (int i = 0; i < PaletteTiers; i++)
            {
                float alpha = alphaLut[i] / 255f;
                dxBidTierBrushes[i] = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                    new Color4(bid.R / 255f, bid.G / 255f, bid.B / 255f, alpha));
                dxAskTierBrushes[i] = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                    new Color4(ask.R / 255f, ask.G / 255f, ask.B / 255f, alpha));
            }

            dxHudText = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.96f, 0.97f, 0.98f, 1f));
            dxHudPanel = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.03f, 0.04f, 0.06f, 0.84f));
            dxHudBorder = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.16f, 0.19f, 0.24f, 1f));
            dxPriceLine = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.92f, 0.95f, 0.99f, 0.40f));
            hudFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 11f);
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (IsInHitTest)
                return;

            if (RenderTarget == null || ChartPanel == null || ChartBars == null)
                return;

            if (dxBidTierBrushes == null || dxAskTierBrushes == null || hudFont == null)
                return;

            base.OnRender(chartControl, chartScale);
            EnsureRenderSnapshot();

            float left = (float)ChartPanel.X;
            float right = (float)(ChartPanel.X + ChartPanel.W);
            float bottom = (float)(ChartPanel.Y + ChartPanel.H);
            float fullWidth = Math.Max(1f, right - left);
            float ladderWidthMax = Math.Max(12f, DOMLadderWidth);

            AntialiasMode priorAntialias = RenderTarget.AntialiasMode;
            RenderTarget.AntialiasMode = AntialiasMode.Aliased;

            double currentPrice = 0;
            try { if (CurrentBar >= 0 && Close != null && Close.Count > 0) currentPrice = Close[0]; } catch { }

            if (ShowBidDepth)
                DrawLiquidityLevels(renderBids, true, chartScale, left, right, fullWidth, ladderWidthMax, currentPrice);
            if (ShowAskDepth)
                DrawLiquidityLevels(renderAsks, false, chartScale, left, right, fullWidth, ladderWidthMax, currentPrice);

            RenderTarget.AntialiasMode = priorAntialias;

            DrawCurrentPriceLine(chartScale, left, right);
            DrawStatusHud(left, bottom);
        }

        private void DrawLiquidityLevels(LiquidityLevel[] levels, bool isBid, ChartScale chartScale,
            float left, float right, float fullWidth, float ladderWidthMax, double currentPrice)
        {
            if (levels == null || levels.Length == 0)
                return;

            double minValue = chartScale.MinValue;
            double maxValue = chartScale.MaxValue;
            DateTime nowUtc = DateTime.UtcNow;
            int referenceMax = Math.Max(1, Math.Max(ReferenceMax, Math.Max(renderPeakSize, sessionPeakSize)));

            for (int i = 0; i < levels.Length; i++)
            {
                LiquidityLevel level = levels[i];
                if (level == null)
                    continue;
                if (level.Price < minValue || level.Price > maxValue)
                    continue;

                int renderSize = level.IsActive ? level.CurrentSize : level.LastNonZeroSize;
                if (renderSize < MinSizeFilter)
                    continue;

                // Spoof reduction: skip levels that haven't persisted long enough
                if (level.IsActive && MinPersistenceSeconds > 0)
                {
                    double dwellSec = (nowUtc - level.FirstSeen).TotalSeconds;
                    if (dwellSec < MinPersistenceSeconds)
                        continue;
                }

                // Distance filter: skip levels too close to current price
                if (currentPrice > 0 && MinDistancePoints > 0)
                {
                    double dist = Math.Abs(level.Price - currentPrice);
                    if (dist < MinDistancePoints)
                        continue;
                }

                double fadeFactor = 1.0;
                if (!level.IsActive)
                {
                    if (level.LastNonZero == DateTime.MinValue)
                        continue;

                    double fadeAge = (nowUtc - level.LastNonZero).TotalSeconds;
                    if (fadeAge >= FadeOutSeconds)
                        continue;

                    fadeFactor = 1.0 - (fadeAge / FadeOutSeconds);
                }

                double normalized = NormalizeSize(renderSize, referenceMax);
                double intensity = normalized * fadeFactor;
                if (intensity <= 0.02)
                    continue;

                int tierIndex = GetTierIndex(intensity);
                SharpDX.Direct2D1.Brush bandBrush = GetTierBrush(isBid, tierIndex);
                if (bandBrush == null)
                    continue;

                float y = chartScale.GetYByValue(level.Price);
                float rawTickHeight = Math.Abs(chartScale.GetYByValue(level.Price) - chartScale.GetYByValue(level.Price + actualTickSize));
                float bandHeight = Math.Max(3f, rawTickHeight * 1.35f);
                float bandTop = y - (bandHeight * 0.5f);
                float bandBottom = y + (bandHeight * 0.5f);
                float drawRight = level.IsActive ? right : left + (float)(fullWidth * fadeFactor);
                if (drawRight <= left + 1f)
                    continue;

                RenderTarget.FillRectangle(new RectangleF(left, bandTop, drawRight - left, bandBottom - bandTop), bandBrush);

                if (ShowDOMLadder && level.IsActive)
                {
                    float ladderWidth = (float)Math.Max(6.0, ladderWidthMax * normalized);
                    if (ladderWidth > fullWidth)
                        ladderWidth = fullWidth;
                    RenderTarget.FillRectangle(new RectangleF(right - ladderWidth, bandTop, ladderWidth, bandBottom - bandTop), bandBrush);
                }
            }
        }

        private void DrawCurrentPriceLine(ChartScale chartScale, float left, float right)
        {
            if (dxPriceLine == null || Close == null || Close.Count == 0 || CurrentBar < 0)
                return;

            double price = Close[0];
            if (price <= 0 || price < chartScale.MinValue || price > chartScale.MaxValue)
                return;

            float y = chartScale.GetYByValue(price);
            RenderTarget.DrawLine(new Vector2(left, y), new Vector2(right, y), dxPriceLine, 1f);
        }

        private void DrawStatusHud(float left, float bottom)
        {
            if (dxHudPanel == null || dxHudText == null || dxHudBorder == null || hudFont == null)
                return;

            string text = string.Format(CultureInfo.InvariantCulture,
                "LIQ HM | {0} bid / {1} ask | peak={2} | depth callbacks: {3:N0}",
                renderActiveBidCount,
                renderActiveAskCount,
                Math.Max(renderPeakSize, sessionPeakSize),
                Interlocked.Read(ref depthCallbackCount));

            float x = left + 8f;
            float width = 420f;
            float height = 22f;
            float y = bottom - height - 8f;

            RenderTarget.FillRectangle(new RectangleF(x, y, width, height), dxHudPanel);
            RenderTarget.DrawRectangle(new RectangleF(x, y, width, height), dxHudBorder, 1f);
            using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, text, hudFont, width - 10f, height))
                RenderTarget.DrawTextLayout(new Vector2(x + 5f, y + 3f), layout, dxHudText);
        }

        private void EnsureRenderSnapshot()
        {
            bool needsRefresh = Interlocked.CompareExchange(ref dirtyFlag, 0, 0) == 1 || renderHasFadingLevels == 1;
            if (!needsRefresh)
                return;

            LiquidityLevel[] nextBids;
            LiquidityLevel[] nextAsks;
            int activeBidCount;
            int activeAskCount;
            int recentBidCount;
            int recentAskCount;
            int peakSize;
            int hasFades;

            if (!TryCopyBook(bidLevels, out nextBids, out activeBidCount, out recentBidCount, out peakSize, out hasFades))
            {
                snapshotFailureCount++;
                return;
            }

            int askPeak;
            int askFades;
            if (!TryCopyBook(askLevels, out nextAsks, out activeAskCount, out recentAskCount, out askPeak, out askFades))
            {
                snapshotFailureCount++;
                return;
            }

            renderBids = nextBids;
            renderAsks = nextAsks;
            renderActiveBidCount = activeBidCount;
            renderActiveAskCount = activeAskCount;
            renderRecentBidCount = recentBidCount;
            renderRecentAskCount = recentAskCount;
            renderPeakSize = Math.Max(1, Math.Max(sessionPeakSize, Math.Max(peakSize, askPeak)));
            renderHasFadingLevels = hasFades == 1 || askFades == 1 ? 1 : 0;
            snapshotFailureCount = 0;
            Interlocked.Exchange(ref dirtyFlag, 0);
        }

        private bool TryCopyBook(Dictionary<double, LiquidityLevel> source, out LiquidityLevel[] snapshot,
            out int activeCount, out int recentCount, out int peakSize, out int hasFades)
        {
            snapshot = new LiquidityLevel[0];
            activeCount = 0;
            recentCount = 0;
            peakSize = 1;
            hasFades = 0;

            for (int attempt = 0; attempt < 2; attempt++)
            {
                try
                {
                    DateTime nowUtc = DateTime.UtcNow;
                    List<LiquidityLevel> items = new List<LiquidityLevel>(source.Count);

                    foreach (KeyValuePair<double, LiquidityLevel> pair in source)
                    {
                        LiquidityLevel level = pair.Value;
                        if (level == null)
                            continue;

                        LiquidityLevel copy = level.Clone();
                        items.Add(copy);

                        if (copy.IsActive && copy.CurrentSize > 0)
                            activeCount++;

                        bool recent = copy.IsActive;
                        if (!recent && copy.LastNonZero != DateTime.MinValue)
                        {
                            double fadeAge = (nowUtc - copy.LastNonZero).TotalSeconds;
                            if (fadeAge < FadeOutSeconds && copy.LastNonZeroSize >= MinSizeFilter)
                            {
                                recent = true;
                                hasFades = 1;
                            }
                        }

                        if (recent)
                            recentCount++;

                        if (peakSize < copy.PeakSize)
                            peakSize = copy.PeakSize;
                    }

                    snapshot = items.ToArray();
                    return true;
                }
                catch (InvalidOperationException)
                {
                }
            }

            return false;
        }

        private void OnInvalidateTimer(object state)
        {
            if (ChartControl == null)
                return;

            bool needsRefresh = Interlocked.CompareExchange(ref dirtyFlag, 0, 0) == 1 || renderHasFadingLevels == 1;
            if (!needsRefresh)
                return;

            try
            {
                ChartControl.Dispatcher.BeginInvoke(new Action(delegate { ChartControl.InvalidateVisual(); }));
            }
            catch { }
        }

        private void PruneStaleLevels(Dictionary<double, LiquidityLevel> levels, DateTime nowUtc)
        {
            if (levels.Count == 0)
                return;

            pruneKeys.Clear();

            foreach (KeyValuePair<double, LiquidityLevel> pair in levels)
            {
                LiquidityLevel level = pair.Value;
                if (level == null)
                {
                    pruneKeys.Add(pair.Key);
                    continue;
                }

                double staleAge = (nowUtc - level.LastSeen).TotalSeconds;
                bool fadedOut = !level.IsActive && level.LastNonZero != DateTime.MinValue
                    && (nowUtc - level.LastNonZero).TotalSeconds >= FadeOutSeconds;

                if (staleAge > StaleSeconds || fadedOut)
                    pruneKeys.Add(pair.Key);
            }

            for (int i = 0; i < pruneKeys.Count; i++)
                levels.Remove(pruneKeys[i]);
        }

        private void BuildAlphaLookupTable()
        {
            int maxOpacity = Clamp(MaxOpacityPct, 1, 100);
            double maxAlpha = maxOpacity / 100.0;

            for (int i = 0; i < PaletteTiers; i++)
            {
                double pct = (i + 1) / (double)PaletteTiers;
                double alpha = 0.05 + ((maxAlpha - 0.05) * pct);
                alphaLut[i] = (byte)Clamp((int)Math.Round(alpha * 255.0), 13, 255);
            }
        }

        private double NormalizeSize(int size, int referenceMax)
        {
            if (size <= 0)
                return 0.0;

            double numerator = Math.Log(1.0 + size);
            double denominator = Math.Log(1.0 + Math.Max(1, referenceMax));
            if (denominator <= 0)
                return 0.0;

            double normalized = numerator / denominator;
            if (normalized < 0.0) return 0.0;
            if (normalized > 1.0) return 1.0;
            return normalized;
        }

        private int GetTierIndex(double intensity)
        {
            if (intensity <= 0)
                return 0;

            int index = (int)Math.Round(intensity * (PaletteTiers - 1));
            if (index < 0) index = 0;
            if (index >= PaletteTiers) index = PaletteTiers - 1;
            return index;
        }

        private SharpDX.Direct2D1.Brush GetTierBrush(bool isBid, int tierIndex)
        {
            if (tierIndex < 0) tierIndex = 0;
            if (tierIndex >= PaletteTiers) tierIndex = PaletteTiers - 1;

            SharpDX.Direct2D1.Brush[] brushes = isBid ? dxBidTierBrushes : dxAskTierBrushes;
            if (brushes == null || brushes.Length <= tierIndex)
                return null;

            return brushes[tierIndex];
        }

        private void DisposeDx()
        {
            DisposeTierBrushes(ref dxBidTierBrushes);
            DisposeTierBrushes(ref dxAskTierBrushes);
            SafeDispose(ref dxHudText);
            SafeDispose(ref dxHudPanel);
            SafeDispose(ref dxHudBorder);
            SafeDispose(ref dxPriceLine);
            SafeDispose(ref hudFont);
        }

        private static void DisposeTierBrushes(ref SharpDX.Direct2D1.Brush[] brushes)
        {
            if (brushes == null)
                return;

            for (int i = 0; i < brushes.Length; i++)
                SafeDispose(ref brushes[i]);

            brushes = null;
        }

        private static void SafeDispose<T>(ref T resource) where T : class, IDisposable
        {
            if (resource == null)
                return;

            try { resource.Dispose(); }
            catch { }
            resource = null;
        }

        private void ClearAllLevels()
        {
            bidLevels.Clear();
            askLevels.Clear();
            pruneKeys.Clear();
            renderBids = new LiquidityLevel[0];
            renderAsks = new LiquidityLevel[0];
            renderActiveBidCount = 0;
            renderActiveAskCount = 0;
            renderRecentBidCount = 0;
            renderRecentAskCount = 0;
            renderHasFadingLevels = 0;
            sessionPeakSize = Math.Max(1, ReferenceMax);
            renderPeakSize = Math.Max(1, ReferenceMax);
            pruneCountdown = 0;
        }

        private static int SafeToInt(long value)
        {
            if (value <= 0)
                return 0;
            if (value >= int.MaxValue)
                return int.MaxValue;
            return (int)value;
        }

        private static int Clamp(int value, int min, int max)
        {
            if (value < min) return min;
            if (value > max) return max;
            return value;
        }

        private static Brush MakeFrozenBrush(Color color)
        {
            SolidColorBrush brush = new SolidColorBrush(color);
            if (brush.CanFreeze)
                brush.Freeze();
            return brush;
        }

        private static Color ExtractBrushColor(Brush brush, Color fallback)
        {
            SolidColorBrush solid = brush as SolidColorBrush;
            if (solid != null)
                return solid.Color;
            return fallback;
        }

        #region Properties

        [NinjaScriptProperty]
        [Range(1, 5000)]
        [Display(Name = "MinSizeFilter", Order = 1, GroupName = "1. Data")]
        public int MinSizeFilter { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100000)]
        [Display(Name = "ReferenceMax", Order = 2, GroupName = "1. Data")]
        public int ReferenceMax { get; set; }

        [NinjaScriptProperty]
        [Range(0, 30)]
        [Display(Name = "Min Persistence (sec)", Order = 3, GroupName = "1. Filters",
            Description = "Spoof reduction — levels must persist this long before rendering")]
        public double MinPersistenceSeconds { get; set; }

        [NinjaScriptProperty]
        [Range(0, 500)]
        [Display(Name = "Min Distance (points)", Order = 4, GroupName = "1. Filters",
            Description = "Hide levels within this distance of current price (reduces near-price noise)")]
        public double MinDistancePoints { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "MaxOpacityPct", Order = 3, GroupName = "2. Display")]
        public int MaxOpacityPct { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowBidDepth", Order = 4, GroupName = "2. Display")]
        public bool ShowBidDepth { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowAskDepth", Order = 5, GroupName = "2. Display")]
        public bool ShowAskDepth { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowDOMLadder", Order = 6, GroupName = "2. Display")]
        public bool ShowDOMLadder { get; set; }

        [NinjaScriptProperty]
        [Range(20, 400)]
        [Display(Name = "DOMLadderWidth", Order = 7, GroupName = "2. Display")]
        public int DOMLadderWidth { get; set; }

        [NinjaScriptProperty]
        [Range(1.0, 300.0)]
        [Display(Name = "StaleSeconds", Order = 8, GroupName = "1. Data")]
        public double StaleSeconds { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "DepthLevels", Order = 9, GroupName = "1. Data")]
        public int DepthLevels { get; set; }

        [XmlIgnore]
        [Display(Name = "BidColor", Order = 10, GroupName = "3. Colors")]
        public Brush BidColor { get; set; }

        [Browsable(false)]
        public string BidColorSerializable
        {
            get { return Serialize.BrushToString(BidColor); }
            set { BidColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "AskColor", Order = 11, GroupName = "3. Colors")]
        public Brush AskColor { get; set; }

        [Browsable(false)]
        public string AskColorSerializable
        {
            get { return Serialize.BrushToString(AskColor); }
            set { AskColor = Serialize.StringToBrush(value); }
        }

        #endregion

        private sealed class LiquidityLevel
        {
            public double Price;
            public int CurrentSize;
            public int PeakSize;
            public int LastNonZeroSize;
            public DateTime FirstSeen;
            public DateTime LastSeen;
            public DateTime LastNonZero;
            public bool IsActive;

            public LiquidityLevel Clone()
            {
                return new LiquidityLevel
                {
                    Price = Price,
                    CurrentSize = CurrentSize,
                    PeakSize = PeakSize,
                    LastNonZeroSize = LastNonZeroSize,
                    FirstSeen = FirstSeen,
                    LastSeen = LastSeen,
                    LastNonZero = LastNonZero,
                    IsActive = IsActive
                };
            }
        }
    }
}
