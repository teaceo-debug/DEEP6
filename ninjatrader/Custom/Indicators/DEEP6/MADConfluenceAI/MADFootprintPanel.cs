// MADFootprintPanel.cs — Dedicated footprint cell sub-panel
// Renders bid×ask cells, imbalance coloring, and POC lines in a separate panel
// Data types (MADCell, MADFootprintBar) are shared from MADConfluenceAI.Data.cs
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using Brushes = System.Windows.Media.Brushes;
using NinjaTrader.Cbi;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class MADFootprintPanel : Indicator
    {
        private readonly object _dataLock = new object();

        private double _bestBid;
        private double _bestAsk;
        private List<MADFootprintBar> _bars;
        private MADFootprintBar _currentBar;

        private SolidColorBrush _brushCellBg;
        private SolidColorBrush _brushCellText;
        private SolidColorBrush _brushCellDim;
        private SolidColorBrush _brushImbModerate;
        private SolidColorBrush _brushImbStrong;
        private SolidColorBrush _brushImbSell;
        private SolidColorBrush _brushImbExtreme;
        private SolidColorBrush _brushPoc;
        private SolidColorBrush _brushGridLine;
        private TextFormat _cellFont;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Dedicated footprint cell sub-panel for MADConfluenceAI.";
                Name = "MADFootprintPanel";
                IsOverlay = false;
                DrawOnPricePanel = false;
                Calculate = Calculate.OnEachTick;
                IsSuspendedWhileInactive = true;
                DisplayInDataBox = false;

                CellFontSize = 9;
                MaxCellBars = 30;
            }
            else if (State == State.Configure)
            {
                AddPlot(Brushes.Transparent, "Anchor");
            }
            else if (State == State.DataLoaded)
            {
                InitDataPipeline();
            }
            else if (State == State.Terminated)
            {
                DisposeDx();
            }
        }

        [NinjaScriptProperty]
        [Range(7, 14)]
        [Display(Name = "CellFontSize", Order = 1, GroupName = "Parameters")]
        public int CellFontSize { get; set; }

        [NinjaScriptProperty]
        [Range(5, 100)]
        [Display(Name = "MaxCellBars", Order = 2, GroupName = "Parameters")]
        public int MaxCellBars { get; set; }

        private void InitDataPipeline()
        {
            _bestBid = 0;
            _bestAsk = 0;
            _bars = new List<MADFootprintBar>();
            _currentBar = null;
        }

        private void FinalizeCurrentBar()
        {
            if (_currentBar != null)
            {
                long priorCvd = _bars.Count > 0 ? _bars[_bars.Count - 1].Cvd : 0;
                _currentBar.Finalize(priorCvd);
                _bars.Add(_currentBar);
            }

            _currentBar = new MADFootprintBar { BarIndex = CurrentBar, BarTime = Time[0] };
        }

        protected override void OnMarketData(MarketDataEventArgs marketDataUpdate)
        {
            lock (_dataLock)
            {
                if (marketDataUpdate.MarketDataType == MarketDataType.Bid)
                {
                    _bestBid = marketDataUpdate.Price;
                    return;
                }

                if (marketDataUpdate.MarketDataType == MarketDataType.Ask)
                {
                    _bestAsk = marketDataUpdate.Price;
                    return;
                }

                if (marketDataUpdate.MarketDataType != MarketDataType.Last)
                    return;

                if (_currentBar == null)
                    return;

                double price = marketDataUpdate.Price;
                long volume = marketDataUpdate.Volume;
                int aggressor = 0;

                if (_bestAsk > 0 && price >= _bestAsk)
                    aggressor = 1;
                else if (_bestBid > 0 && price <= _bestBid)
                    aggressor = 2;

                _currentBar.AddTrade(price, volume, aggressor);
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;

            Values[0][0] = Close[0];

            lock (_dataLock)
            {
                if (_currentBar == null || IsFirstTickOfBar)
                    FinalizeCurrentBar();
            }
        }

        public override void OnCalculateMinMax()
        {
            MinValue = double.MaxValue;
            MaxValue = double.MinValue;

            if (ChartBars == null) return;
            int from = ChartBars.FromIndex;
            int to = ChartBars.ToIndex;

            for (int i = from; i <= to; i++)
            {
                if (i < 0 || i >= Bars.Count) continue;
                double h = Highs[0].GetValueAt(i);
                double l = Lows[0].GetValueAt(i);
                if (h > MaxValue) MaxValue = h;
                if (l < MinValue) MinValue = l;
            }

            // Pad by 2 ticks
            double tick = TickSize > 0 ? TickSize : 0.25;
            MinValue -= 2 * tick;
            MaxValue += 2 * tick;
        }

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null)
                return;

            _brushCellBg = new SolidColorBrush(RenderTarget, new Color4(0.055f, 0.063f, 0.078f, 0.85f));
            _brushCellText = new SolidColorBrush(RenderTarget, new Color4(0.949f, 0.957f, 0.973f, 1.0f));
            _brushCellDim = new SolidColorBrush(RenderTarget, new Color4(0.608f, 0.639f, 0.682f, 1.0f));
            _brushImbModerate = new SolidColorBrush(RenderTarget, new Color4(1.0f, 0.702f, 0.0f, 0.18f));
            _brushImbStrong = new SolidColorBrush(RenderTarget, new Color4(0.0f, 0.878f, 1.0f, 0.28f));
            _brushImbSell = new SolidColorBrush(RenderTarget, new Color4(1.0f, 0.220f, 0.784f, 0.28f));
            _brushImbExtreme = new SolidColorBrush(RenderTarget, new Color4(1.0f, 1.0f, 1.0f, 1.0f));
            _brushPoc = new SolidColorBrush(RenderTarget, new Color4(1.0f, 0.824f, 0.247f, 0.60f));
            _brushGridLine = new SolidColorBrush(RenderTarget, new Color4(0.149f, 0.149f, 0.200f, 0.40f));
            _cellFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", FontWeight.Normal, FontStyle.Normal, FontStretch.Normal, (float)CellFontSize);
        }

        private void DisposeDx()
        {
            SafeDispose(ref _brushCellBg);
            SafeDispose(ref _brushCellText);
            SafeDispose(ref _brushCellDim);
            SafeDispose(ref _brushImbModerate);
            SafeDispose(ref _brushImbStrong);
            SafeDispose(ref _brushImbSell);
            SafeDispose(ref _brushImbExtreme);
            SafeDispose(ref _brushPoc);
            SafeDispose(ref _brushGridLine);

            if (_cellFont != null)
            {
                _cellFont.Dispose();
                _cellFont = null;
            }
        }

        private static void SafeDispose(ref SolidColorBrush b)
        {
            if (b != null && !b.IsDisposed) b.Dispose();
            b = null;
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (RenderTarget == null || ChartBars == null) return;

            // Dark background for entire panel
            var panelRect = new RectangleF(0, 0, (float)ChartPanel.W, (float)ChartPanel.H);
            RenderTarget.FillRectangle(panelRect, _brushCellBg);

            RenderCells(chartControl, chartScale);
            RenderPocLines(chartControl, chartScale);
        }

        private void RenderCells(ChartControl chartControl, ChartScale chartScale)
        {
            List<MADFootprintBar> bars;
            lock (_dataLock)
            {
                bars = _bars == null ? null : new List<MADFootprintBar>(_bars);
            }

            if (bars == null || bars.Count == 0 || _cellFont == null) return;

            double tickSize = TickSize > 0 ? TickSize : 0.25;
            float tickHeight = Math.Max(1f, Math.Abs(chartScale.GetYByValue(0) - chartScale.GetYByValue(tickSize)));
            if (tickHeight < 3f) return;

            int fromIdx = ChartBars.FromIndex;
            int toIdx = ChartBars.ToIndex;

            // ADAPTIVE bar width — key fix from the overlay approach
            float adaptiveBarWidth = 8f;
            if (toIdx > fromIdx)
            {
                float x1 = chartControl.GetXByBarIndex(ChartBars, fromIdx);
                float x2 = chartControl.GetXByBarIndex(ChartBars, fromIdx + 1);
                adaptiveBarWidth = Math.Abs(x2 - x1);
            }

            bool showText = adaptiveBarWidth >= 20f && tickHeight >= 10f;
            if (adaptiveBarWidth < 6f) return;

            float cellWidth = adaptiveBarWidth - 2f; // 1px gap between bars

            int maxBars = Math.Min(MaxCellBars, bars.Count);
            int startIdx = bars.Count - maxBars;
            if (startIdx < 0) startIdx = 0;

            for (int i = startIdx; i < bars.Count; i++)
            {
                var bar = bars[i];
                if (bar == null || bar.Levels == null || bar.Levels.Count == 0) continue;
                if (bar.BarIndex < fromIdx || bar.BarIndex > toIdx) continue;

                float barCenterX = chartControl.GetXByBarIndex(ChartBars, bar.BarIndex);
                float cellLeft = barCenterX - cellWidth * 0.5f;

                foreach (var kv in bar.Levels)
                {
                    double price = kv.Key;
                    if (price < bar.Low || price > bar.High) continue;

                    var cell = kv.Value;
                    if (cell.TotalVol == 0) continue;

                    float y = chartScale.GetYByValue(price);
                    if (y < -10 || y > ChartPanel.H + 10) continue;

                    var cellRect = new RectangleF(cellLeft, y - tickHeight * 0.5f, cellWidth, tickHeight);

                    // --- Imbalance coloring (diagonal comparison) ---
                    double nextPrice = price + tickSize;
                    MADCell nextCell = null;
                    bar.Levels.TryGetValue(nextPrice, out nextCell);

                    float imbRatio = 1.0f;
                    bool isBuyImb = false;
                    if (nextCell != null && nextCell.BidVol > 0 && cell.AskVol > 0)
                    {
                        imbRatio = (float)cell.AskVol / nextCell.BidVol;
                        isBuyImb = true;
                    }
                    else if (cell.BidVol > 0)
                    {
                        double prevPrice = price - tickSize;
                        MADCell prevCell = null;
                        bar.Levels.TryGetValue(prevPrice, out prevCell);
                        if (prevCell != null && prevCell.AskVol > 0)
                        {
                            imbRatio = (float)cell.BidVol / prevCell.AskVol;
                            isBuyImb = false;
                        }
                    }

                    // Cell background based on imbalance tier
                    bool isExtreme = false;
                    if (imbRatio >= 5.0f)
                    {
                        isExtreme = true;
                        RenderTarget.FillRectangle(cellRect, isBuyImb ? _brushImbStrong : _brushImbSell);
                    }
                    else if (imbRatio >= 3.0f)
                    {
                        RenderTarget.FillRectangle(cellRect, isBuyImb ? _brushImbStrong : _brushImbSell);
                    }
                    else if (imbRatio >= 1.5f)
                    {
                        RenderTarget.FillRectangle(cellRect, _brushImbModerate);
                    }
                    else
                    {
                        // Subtle delta-based coloring: green tint for buy, red for sell
                        // Just use a very subtle grid line for normal cells
                    }

                    // --- Cell border (subtle grid) ---
                    RenderTarget.DrawRectangle(cellRect, _brushGridLine, 0.5f);

                    // --- Text ---
                    if (showText)
                    {
                        string cellText = string.Format("{0,4} x {1,-4}", cell.BidVol, cell.AskVol);
                        var textRect = new RectangleF(cellLeft + 1, y - tickHeight * 0.5f + 1, cellWidth - 2, tickHeight - 2);
                        var textBrush = isExtreme ? _brushImbExtreme : _brushCellText;
                        RenderTarget.DrawText(cellText, _cellFont, textRect, textBrush);
                    }
                    else if (cell.TotalVol > 0)
                    {
                        RenderTarget.DrawLine(new Vector2(cellRect.Left, cellRect.Top), new Vector2(cellRect.Right, cellRect.Top), _brushCellDim, 0.5f);
                    }

                    // --- Corner brackets for extreme imbalances ---
                    if (isExtreme)
                    {
                        float bLen = Math.Min(5f, cellWidth * 0.2f);
                        float bx1 = cellRect.Left, by1 = cellRect.Top;
                        float bx2 = cellRect.Right, by2 = cellRect.Bottom;
                        RenderTarget.DrawLine(new Vector2(bx1, by1), new Vector2(bx1 + bLen, by1), _brushImbExtreme, 1f);
                        RenderTarget.DrawLine(new Vector2(bx1, by1), new Vector2(bx1, by1 + bLen), _brushImbExtreme, 1f);
                        RenderTarget.DrawLine(new Vector2(bx2, by1), new Vector2(bx2 - bLen, by1), _brushImbExtreme, 1f);
                        RenderTarget.DrawLine(new Vector2(bx2, by1), new Vector2(bx2, by1 + bLen), _brushImbExtreme, 1f);
                        RenderTarget.DrawLine(new Vector2(bx1, by2), new Vector2(bx1 + bLen, by2), _brushImbExtreme, 1f);
                        RenderTarget.DrawLine(new Vector2(bx1, by2), new Vector2(bx1, by2 - bLen), _brushImbExtreme, 1f);
                        RenderTarget.DrawLine(new Vector2(bx2, by2), new Vector2(bx2 - bLen, by2), _brushImbExtreme, 1f);
                        RenderTarget.DrawLine(new Vector2(bx2, by2), new Vector2(bx2, by2 - bLen), _brushImbExtreme, 1f);
                    }
                }
            }
        }

        private void RenderPocLines(ChartControl chartControl, ChartScale chartScale)
        {
            List<MADFootprintBar> bars;
            lock (_dataLock)
            {
                bars = _bars == null ? null : new List<MADFootprintBar>(_bars);
            }

            if (bars == null || bars.Count == 0 || _brushPoc == null) return;

            int fromIdx = ChartBars.FromIndex;
            int toIdx = ChartBars.ToIndex;

            float adaptiveBarWidth = 8f;
            if (toIdx > fromIdx)
            {
                float x1 = chartControl.GetXByBarIndex(ChartBars, fromIdx);
                float x2 = chartControl.GetXByBarIndex(ChartBars, fromIdx + 1);
                adaptiveBarWidth = Math.Abs(x2 - x1);
            }
            float halfW = (adaptiveBarWidth - 2f) * 0.5f;

            int maxBars = Math.Min(MaxCellBars, bars.Count);
            int startIdx = bars.Count - maxBars;
            if (startIdx < 0) startIdx = 0;

            for (int i = startIdx; i < bars.Count; i++)
            {
                var bar = bars[i];
                if (bar == null || bar.PocPrice <= 0) continue;
                if (bar.BarIndex < fromIdx || bar.BarIndex > toIdx) continue;

                float cx = chartControl.GetXByBarIndex(ChartBars, bar.BarIndex);
                float pocY = chartScale.GetYByValue(bar.PocPrice);
                if (pocY < -10 || pocY > ChartPanel.H + 10) continue;

                RenderTarget.DrawLine(
                    new Vector2(cx - halfW, pocY),
                    new Vector2(cx + halfW, pocY),
                    _brushPoc, 2f);
            }
        }
    }
}

#region NinjaScript generated code. Neither change nor remove.
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6.MADFootprintPanel[] cacheMADFootprintPanel;
        public DEEP6.MADFootprintPanel MADFootprintPanel()
        {
            return MADFootprintPanel(Input);
        }
        public DEEP6.MADFootprintPanel MADFootprintPanel(ISeries<double> input)
        {
            if (cacheMADFootprintPanel != null)
                for (int idx = cacheMADFootprintPanel.Length - 1; idx >= 0; idx--)
                    if (cacheMADFootprintPanel[idx] != null && cacheMADFootprintPanel[idx].EqualsInput(input))
                        return cacheMADFootprintPanel[idx];
            return CacheIndicator<DEEP6.MADFootprintPanel>(new DEEP6.MADFootprintPanel(), input, ref cacheMADFootprintPanel);
        }
    }
}
#endregion
