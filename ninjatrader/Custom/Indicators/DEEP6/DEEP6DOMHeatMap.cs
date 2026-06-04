#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Threading;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
using Color = System.Windows.Media.Color;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6DOMHeatMap : Indicator
    {
        private const int BarCap = 512;
        private const int LevelCap = 512;
        private const int BarMask = BarCap - 1;
        private const int LevelMask = LevelCap - 1;
        private const int PaletteTiers = 20;
        private const int InvalidateIntervalMs = 50;

        private readonly int[] bidHeat = new int[BarCap * LevelCap];
        private readonly int[] askHeat = new int[BarCap * LevelCap];
        private readonly int[] barBaseTick = new int[BarCap];
        private readonly byte[] bidAlphaLut = new byte[PaletteTiers];
        private readonly byte[] askAlphaLut = new byte[PaletteTiers];

        private Timer invalidateTimer;
        private SharpDX.Direct2D1.Brush[] dxBidTierBrushes;
        private SharpDX.Direct2D1.Brush[] dxAskTierBrushes;
        private int ringHead = -1;
        private int activeBarIndex = int.MinValue;
        private int sessionPeakVolume = 200;
        private int dirtyFlag;
        private long depthCallbackCount;
        private long depthCapturedCount;
        private double actualTickSize = 0.25;
        private byte bidColorB;
        private byte bidColorG;
        private byte bidColorR;
        private byte askColorB;
        private byte askColorG;
        private byte askColorR;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 DOM Heat Map — Bookmap-style historical depth heatmap behind candles.";
                Name = "DEEP6 DOM Heat Map";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DrawOnPricePanel = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                ScaleJustification = ScaleJustification.Right;
                IsSuspendedWhileInactive = false;

                DepthLevels = 10;
                ShowBidDepth = true;
                ShowAskDepth = true;
                MaxOpacityPct = 85;
                MinVolumeFilter = 0;
                NormCeiling = 2500;
                NormFloor = 200;
                BidDepthColor = MakeFrozenBrush(Color.FromRgb(0x00, 0xE0, 0xFF));
                AskDepthColor = MakeFrozenBrush(Color.FromRgb(0xFF, 0x17, 0x44));
            }
            else if (State == State.Configure)
            {
                actualTickSize = TickSize > 0 ? TickSize : 0.25;
            }
            else if (State == State.DataLoaded)
            {
                actualTickSize = TickSize > 0 ? TickSize : 0.25;
                Array.Clear(bidHeat, 0, bidHeat.Length);
                Array.Clear(askHeat, 0, askHeat.Length);
                Array.Clear(barBaseTick, 0, barBaseTick.Length);
                ringHead = -1;
                activeBarIndex = int.MinValue;
                sessionPeakVolume = Math.Max(1, NormFloor);
                Interlocked.Exchange(ref dirtyFlag, 0);
                BuildAlphaLookupTables();
                RefreshColorCache();
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

                DisposeTierBrushes();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;

            if (CurrentBar < 0)
                return;

            if (CurrentBar == activeBarIndex)
                return;

            activeBarIndex = CurrentBar;

            if (Bars.IsFirstBarOfSession)
                sessionPeakVolume = Math.Max(1, NormFloor);

            ringHead = (ringHead + 1) & BarMask;

            int sliceOffset = ringHead * LevelCap;
            Array.Clear(bidHeat, sliceOffset, LevelCap);
            Array.Clear(askHeat, sliceOffset, LevelCap);

            int currentTick = PriceToTick(Close[0]);
            barBaseTick[ringHead] = currentTick - (LevelCap >> 1);

            Interlocked.Exchange(ref dirtyFlag, 1);
        }

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (e == null)
                return;

            depthCallbackCount++;

            if (e.MarketDataType != MarketDataType.Bid && e.MarketDataType != MarketDataType.Ask)
                return;

            if (DepthLevels > 0 && e.Position >= DepthLevels)
                return;

            int size = e.Operation == Operation.Remove ? 0 : SafeToInt(e.Volume);

            // Auto-initialize ring if OnBarUpdate hasn't fired yet
            if (ringHead < 0)
            {
                if (e.Price <= 0) return;
                ringHead = 0;
                int initTick = PriceToTick(e.Price);
                barBaseTick[0] = initTick - (LevelCap >> 1);
                Array.Clear(bidHeat, 0, LevelCap);
                Array.Clear(askHeat, 0, LevelCap);
            }

            int tick = PriceToTick(e.Price);
            int baseTick = barBaseTick[ringHead];
            int levelIndex = tick - baseTick;

            // Recenter if price drifted outside the window
            if (levelIndex < 0 || levelIndex >= LevelCap)
            {
                // Only recenter if within reasonable range (not a bogus price)
                if (levelIndex > -LevelCap && levelIndex < LevelCap * 2)
                {
                    int newBaseTick = tick - (LevelCap >> 1);
                    barBaseTick[ringHead] = newBaseTick;
                    int sliceOff = ringHead * LevelCap;
                    Array.Clear(bidHeat, sliceOff, LevelCap);
                    Array.Clear(askHeat, sliceOff, LevelCap);
                    levelIndex = tick - newBaseTick;
                }
                else
                    return;
            }

            int cellIndex = (ringHead * LevelCap) + levelIndex;
            int[] grid = e.MarketDataType == MarketDataType.Bid ? bidHeat : askHeat;

            if (size > grid[cellIndex])
                grid[cellIndex] = size;

            depthCapturedCount++;

            int decayedPeak = (int)(sessionPeakVolume * 0.9995);
            sessionPeakVolume = Math.Max(decayedPeak, size);

            Interlocked.Exchange(ref dirtyFlag, 1);
        }

        public override void OnRenderTargetChanged()
        {
            DisposeTierBrushes();
            if (RenderTarget == null) return;

            RefreshColorCache();
            dxBidTierBrushes = new SharpDX.Direct2D1.Brush[PaletteTiers];
            dxAskTierBrushes = new SharpDX.Direct2D1.Brush[PaletteTiers];

            for (int i = 0; i < PaletteTiers; i++)
            {
                float alpha = bidAlphaLut[i] / 255f;
                dxBidTierBrushes[i] = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                    new Color4(bidColorR / 255f, bidColorG / 255f, bidColorB / 255f, alpha));
                dxAskTierBrushes[i] = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                    new Color4(askColorR / 255f, askColorG / 255f, askColorB / 255f, alpha));
            }
        }

        private void DisposeTierBrushes()
        {
            if (dxBidTierBrushes != null)
            {
                for (int i = 0; i < dxBidTierBrushes.Length; i++)
                    if (dxBidTierBrushes[i] != null) { dxBidTierBrushes[i].Dispose(); dxBidTierBrushes[i] = null; }
                dxBidTierBrushes = null;
            }
            if (dxAskTierBrushes != null)
            {
                for (int i = 0; i < dxAskTierBrushes.Length; i++)
                    if (dxAskTierBrushes[i] != null) { dxAskTierBrushes[i].Dispose(); dxAskTierBrushes[i] = null; }
                dxAskTierBrushes = null;
            }
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (IsInHitTest)
                return;

            if (RenderTarget == null || ChartBars == null || ChartPanel == null)
                return;
            if (dxBidTierBrushes == null || dxAskTierBrushes == null)
                return;

            base.OnRender(chartControl, chartScale);

            int lastVisibleBar = Math.Min(ChartBars.ToIndex, CurrentBar);
            int firstVisibleBar = Math.Max(ChartBars.FromIndex, lastVisibleBar - (BarCap - 1));
            if (lastVisibleBar < firstVisibleBar)
                return;

            int topTick = PriceToTick(chartScale.MaxValue);
            int bottomTick = PriceToTick(chartScale.MinValue);
            if (topTick < bottomTick)
            {
                int swap = topTick;
                topTick = bottomTick;
                bottomTick = swap;
            }

            int displayMax = sessionPeakVolume;
            if (displayMax < NormFloor) displayMax = NormFloor;
            if (displayMax > NormCeiling) displayMax = NormCeiling;
            double logDenom = Math.Log(1.0 + Math.Max(1, displayMax));
            if (logDenom <= 0) logDenom = 1.0;

            float barDistance = Math.Max(1f, (float)chartControl.Properties.BarDistance);
            float halfBar = barDistance * 0.5f;

            AntialiasMode priorMode = RenderTarget.AntialiasMode;
            RenderTarget.AntialiasMode = AntialiasMode.Aliased;

            for (int barIndex = firstVisibleBar; barIndex <= lastVisibleBar; barIndex++)
            {
                int barsAgo = CurrentBar - barIndex;
                if (barsAgo < 0 || barsAgo >= BarCap) continue;

                int slot = (ringHead - barsAgo) & BarMask;
                int baseTick = barBaseTick[slot];
                int sliceOffset = slot * LevelCap;

                float barCenterX = chartControl.GetXByBarIndex(ChartBars, barIndex);
                float cellLeft = barCenterX - halfBar;
                float cellWidth = barDistance;

                for (int tick = topTick; tick >= bottomTick; tick--)
                {
                    int levelIndex = tick - baseTick;
                    if (levelIndex < 0 || levelIndex >= LevelCap) continue;

                    int cellIndex = sliceOffset + levelIndex;
                    int bidVol = ShowBidDepth ? bidHeat[cellIndex] : 0;
                    int askVol = ShowAskDepth ? askHeat[cellIndex] : 0;

                    if (bidVol <= MinVolumeFilter && askVol <= MinVolumeFilter) continue;

                    float cellTop = chartScale.GetYByValue((tick + 1) * actualTickSize);
                    float cellBot = chartScale.GetYByValue(tick * actualTickSize);
                    var rect = new RectangleF(cellLeft, cellTop, cellWidth, Math.Max(1f, cellBot - cellTop));

                    int bidTier = ResolveTier(bidVol, logDenom, displayMax);
                    int askTier = ResolveTier(askVol, logDenom, displayMax);

                    // Draw whichever side has higher volume on top
                    if (bidTier > askTier)
                    {
                        if (askTier > 0) RenderTarget.FillRectangle(rect, dxAskTierBrushes[askTier]);
                        if (bidTier > 0) RenderTarget.FillRectangle(rect, dxBidTierBrushes[bidTier]);
                    }
                    else
                    {
                        if (bidTier > 0) RenderTarget.FillRectangle(rect, dxBidTierBrushes[bidTier]);
                        if (askTier > 0) RenderTarget.FillRectangle(rect, dxAskTierBrushes[askTier]);
                    }
                }
            }

            RenderTarget.AntialiasMode = priorMode;

            // Status HUD
            string status = string.Format("DOM HM | cb={0} cap={1} ring={2} peak={3} bars={4}-{5}",
                depthCallbackCount, depthCapturedCount, ringHead, sessionPeakVolume,
                firstVisibleBar, lastVisibleBar);
            using (var fmt = new SharpDX.DirectWrite.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 10f))
            using (var bg = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0f, 0f, 0f, 0.75f)))
            using (var fg = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0f, 0.9f, 0.4f, 1f)))
            {
                float sx = (float)ChartPanel.X + 8f;
                float sy = (float)ChartPanel.Y + (float)ChartPanel.H - 26f;
                RenderTarget.FillRectangle(new RectangleF(sx, sy, 520f, 20f), bg);
                using (var layout = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, status, fmt, 510f, 18f))
                    RenderTarget.DrawTextLayout(new Vector2(sx + 4f, sy + 2f), layout, fg);
            }
        }

        private void OnInvalidateTimer(object state)
        {
            if (Interlocked.Exchange(ref dirtyFlag, 0) != 1)
                return;

            try
            {
                if (ChartControl != null)
                {
                    ChartControl.Dispatcher.BeginInvoke(new Action(delegate
                    {
                        if (ChartControl != null)
                            ChartControl.InvalidateVisual();
                    }));
                }
            }
            catch { }
        }

        private int ResolveTier(int volume, double logDenominator, int displayMax)
        {
            if (volume <= MinVolumeFilter || volume <= 0)
                return -1;

            int clamped = volume > displayMax ? displayMax : volume;
            int tier = (int)(19.0 * Math.Log(1.0 + clamped) / logDenominator);
            if (tier < 0)
                tier = 0;
            if (tier >= PaletteTiers)
                tier = PaletteTiers - 1;
            return tier;
        }

        private void BuildAlphaLookupTables()
        {
            int maxAlpha = (int)(255.0 * Math.Max(0, Math.Min(100, MaxOpacityPct)) / 100.0);
            for (int i = 0; i < PaletteTiers; i++)
            {
                byte alpha = (byte)Math.Max(0, Math.Min(255, (int)Math.Round((maxAlpha * i) / 19.0)));
                bidAlphaLut[i] = alpha;
                askAlphaLut[i] = alpha;
            }
        }

        private void RefreshColorCache()
        {
            var bid = BidDepthColor as SolidColorBrush;
            var ask = AskDepthColor as SolidColorBrush;

            bidColorB = bid != null ? bid.Color.B : (byte)0x00;
            bidColorG = bid != null ? bid.Color.G : (byte)0xE0;
            bidColorR = bid != null ? bid.Color.R : (byte)0xFF;

            askColorB = ask != null ? ask.Color.B : (byte)0x00;
            askColorG = ask != null ? ask.Color.G : (byte)0x17;
            askColorR = ask != null ? ask.Color.R : (byte)0x44;
        }

        private int PriceToTick(double price)
        {
            return (int)Math.Round(price / actualTickSize, MidpointRounding.AwayFromZero);
        }

        private static int SafeToInt(long value)
        {
            if (value <= 0)
                return 0;

            return value >= int.MaxValue ? int.MaxValue : (int)value;
        }

        private static SolidColorBrush MakeFrozenBrush(Color color)
        {
            var brush = new SolidColorBrush(color);
            if (brush.CanFreeze)
                brush.Freeze();
            return brush;
        }

        private static void SafeDispose<T>(ref T resource) where T : class, IDisposable
        {
            if (resource == null)
                return;

            try { resource.Dispose(); }
            catch { }
            resource = null;
        }

        #region Properties

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "DepthLevels", Order = 1, GroupName = "Parameters")]
        public int DepthLevels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowBidDepth", Order = 2, GroupName = "Parameters")]
        public bool ShowBidDepth { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowAskDepth", Order = 3, GroupName = "Parameters")]
        public bool ShowAskDepth { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "MaxOpacityPct", Order = 4, GroupName = "Parameters")]
        public int MaxOpacityPct { get; set; }

        [NinjaScriptProperty]
        [Range(0, int.MaxValue)]
        [Display(Name = "MinVolumeFilter", Order = 5, GroupName = "Parameters")]
        public int MinVolumeFilter { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100000)]
        [Display(Name = "NormCeiling", Order = 6, GroupName = "Normalization")]
        public int NormCeiling { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100000)]
        [Display(Name = "NormFloor", Order = 7, GroupName = "Normalization")]
        public int NormFloor { get; set; }

        [XmlIgnore]
        [Display(Name = "BidDepthColor", Order = 8, GroupName = "Colors")]
        public Brush BidDepthColor { get; set; }

        [Browsable(false)]
        public string BidDepthColorSerializable
        {
            get { return Serialize.BrushToString(BidDepthColor); }
            set { BidDepthColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "AskDepthColor", Order = 9, GroupName = "Colors")]
        public Brush AskDepthColor { get; set; }

        [Browsable(false)]
        public string AskDepthColorSerializable
        {
            get { return Serialize.BrushToString(AskDepthColor); }
            set { AskDepthColor = Serialize.StringToBrush(value); }
        }

        #endregion
    }
}
