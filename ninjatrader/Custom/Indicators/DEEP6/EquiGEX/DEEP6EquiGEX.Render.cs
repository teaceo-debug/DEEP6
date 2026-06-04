#region Using declarations
using System;
using System.Collections.Generic;
using NinjaTrader.Gui.Chart;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public partial class DEEP6EquiGEX
    {
        #region DX Resources

        private bool _dxOk;

        private SharpDX.Direct2D1.Brush _dxSfvLine;
        private SharpDX.Direct2D1.Brush _dxPremiumFill;
        private SharpDX.Direct2D1.Brush _dxDiscountFill;
        private SharpDX.Direct2D1.Brush _dxEquilibriumFill;
        private SharpDX.Direct2D1.Brush _dxPanel;
        private SharpDX.Direct2D1.Brush _dxText;
        private SharpDX.Direct2D1.Brush _dxBullish;
        private SharpDX.Direct2D1.Brush _dxBearish;
        private SharpDX.Direct2D1.Brush _dxNeutral;
        private SharpDX.Direct2D1.Brush _dxStale;
        private SharpDX.Direct2D1.Brush _dxBorder;
        private SharpDX.Direct2D1.Brush _dxMuted;
        private SharpDX.Direct2D1.Brush _dxPremiumLine;
        private SharpDX.Direct2D1.Brush _dxDiscountLine;
        private SharpDX.Direct2D1.Brush _dxChipText;

        private TextFormat _fontData;
        private TextFormat _fontValues;
        private TextFormat _fontLabels;
        private TextFormat _fontBias;
        private TextFormat _fontTitle;

        private StrokeStyle _dxDash;

        #endregion

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
        }

        private void InitDx()
        {
            if (RenderTarget == null)
                return;

            DisposeDx();

            try
            {
                SharpDX.Direct2D1.Brush B(float r, float g, float b, float a = 1f)
                    => new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(r, g, b, a));

                _dxSfvLine = B(1.0f, 0.84f, 0f, 1f);
                _dxPremiumFill = B(0.95f, 0.25f, 0.25f, 0.15f);
                _dxDiscountFill = B(0.2f, 0.85f, 0.3f, 0.15f);
                _dxEquilibriumFill = B(0.3f, 0.3f, 0.3f, 0.08f);
                _dxPanel = B(0.04f, 0.05f, 0.07f, 0.92f);
                _dxText = B(0.96f, 0.97f, 0.98f, 1f);
                _dxBullish = B(0.2f, 0.85f, 0.3f, 0.85f);
                _dxBearish = B(0.95f, 0.25f, 0.25f, 0.85f);
                _dxNeutral = B(1.0f, 0.65f, 0f, 0.85f);
                _dxStale = B(0.95f, 0.15f, 0.15f, 0.9f);
                _dxBorder = B(0.16f, 0.19f, 0.24f, 1f);
                _dxMuted = B(0.5f, 0.5f, 0.55f, 0.7f);
                _dxPremiumLine = B(0.95f, 0.25f, 0.25f, 0.6f);
                _dxDiscountLine = B(0.2f, 0.85f, 0.3f, 0.6f);
                _dxChipText = B(0.96f, 0.97f, 0.98f, 1f);

                var dw = NinjaTrader.Core.Globals.DirectWriteFactory;
                _fontData = new TextFormat(dw, "Consolas", 9f) { WordWrapping = WordWrapping.NoWrap };
                _fontValues = new TextFormat(dw, "Consolas", FontWeight.Bold, FontStyle.Normal, 14f)
                {
                    WordWrapping = WordWrapping.NoWrap
                };
                _fontLabels = new TextFormat(dw, "Segoe UI", 11f) { WordWrapping = WordWrapping.NoWrap };
                _fontBias = new TextFormat(dw, "Segoe UI", FontWeight.Bold, FontStyle.Normal, 14f)
                {
                    WordWrapping = WordWrapping.NoWrap,
                    TextAlignment = TextAlignment.Center,
                    ParagraphAlignment = ParagraphAlignment.Center
                };
                _fontTitle = new TextFormat(dw, "Segoe UI", FontWeight.Bold, FontStyle.Normal, 14f)
                {
                    WordWrapping = WordWrapping.NoWrap
                };

                _dxDash = new StrokeStyle(
                    NinjaTrader.Core.Globals.D2DFactory,
                    new StrokeStyleProperties
                    {
                        DashStyle = DashStyle.Dash,
                        LineJoin = LineJoin.Round,
                        StartCap = CapStyle.Round,
                        EndCap = CapStyle.Round
                    });

                _dxOk = true;
            }
            catch
            {
                DisposeDx();
            }
        }

        private void DisposeDx()
        {
            _dxOk = false;

            void D<T>(ref T x) where T : class, IDisposable
            {
                if (x != null)
                {
                    try { x.Dispose(); }
                    catch { }
                    x = null;
                }
            }

            D(ref _dxSfvLine);
            D(ref _dxPremiumFill);
            D(ref _dxDiscountFill);
            D(ref _dxEquilibriumFill);
            D(ref _dxPanel);
            D(ref _dxText);
            D(ref _dxBullish);
            D(ref _dxBearish);
            D(ref _dxNeutral);
            D(ref _dxStale);
            D(ref _dxBorder);
            D(ref _dxMuted);
            D(ref _dxPremiumLine);
            D(ref _dxDiscountLine);
            D(ref _dxChipText);

            D(ref _fontData);
            D(ref _fontValues);
            D(ref _fontLabels);
            D(ref _fontBias);
            D(ref _fontTitle);

            D(ref _dxDash);
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);

            if (IsInHitTest || _unsupportedInstrument)
                return;

            if (RenderTarget == null || chartControl == null || chartScale == null || ChartPanel == null || ChartBars == null)
                return;

            if (CurrentBar < BarsRequiredToPlot)
                return;

            if (!_dxOk)
                InitDx();

            if (!_dxOk)
                return;

            float panelLeft = (float)ChartPanel.X;
            float panelTop = (float)ChartPanel.Y;
            float panelWidth = (float)ChartPanel.W;
            float panelHeight = (float)ChartPanel.H;
            float panelRight = panelLeft + panelWidth;
            float panelBottom = panelTop + panelHeight;

            if (panelWidth <= 0 || panelHeight <= 0)
                return;

            int from = ChartBars.FromIndex;
            int to = ChartBars.ToIndex;
            if (from < 0 || to < from)
                return;

            GexState gexState = GetGexState();
            bool showStaleBadge = gexState == null || !gexState.HasData || gexState.IsStale;

            Dictionary<int, (double sfv, double premium, double discount)> sfvSnap = null;
            try
            {
                sfvSnap = new Dictionary<int, (double sfv, double premium, double discount)>();
                foreach (KeyValuePair<int, (double sfv, double premium, double discount)> kvp in _sfvHistory)
                    sfvSnap[kvp.Key] = kvp.Value;
            }
            catch
            {
                sfvSnap = null;
            }

            float premiumY = ClampY(chartScale.GetYByValue(CurrentPremiumBand), panelTop, panelBottom);
            float discountY = ClampY(chartScale.GetYByValue(CurrentDiscountBand), panelTop, panelBottom);
            float sfvY = ClampY(chartScale.GetYByValue(CurrentSFV), panelTop, panelBottom);

            if (discountY < premiumY)
            {
                float swap = premiumY;
                premiumY = discountY;
                discountY = swap;
            }

            float xLeft = (float)chartControl.GetXByBarIndex(ChartBars, from);
            float xRight = (float)chartControl.GetXByBarIndex(ChartBars, to);
            if (xRight < xLeft)
            {
                float swap = xLeft;
                xLeft = xRight;
                xRight = swap;
            }

            float barWidth = (float)Math.Max(ChartControl.BarWidth, 1);
            xLeft = Math.Max(panelLeft, xLeft - barWidth);
            xRight = Math.Min(panelRight, xRight + barWidth);
            if (xRight <= xLeft)
            {
                xLeft = panelLeft;
                xRight = panelRight;
            }

            RenderZoneFills(panelLeft, panelTop, panelWidth, panelBottom, premiumY, discountY);
            RenderBandBorders(xLeft, xRight, premiumY, discountY);
            RenderSfvLine(chartControl, chartScale, sfvSnap, from, to, panelTop, panelBottom);
            RenderZoneLabels(panelLeft, panelRight, panelTop, panelBottom, premiumY, discountY, sfvY);

            if (ShowDashboard)
            {
                RenderHeaderBar(panelLeft, panelTop);
                RenderBiasChip(panelRight, panelTop);
                if (showStaleBadge)
                    RenderStaleBadge(panelRight, panelTop, gexState);
            }
        }

        private void RenderZoneFills(float panelLeft, float panelTop, float panelWidth, float panelBottom, float premiumY, float discountY)
        {
            if (premiumY > panelTop)
            {
                RenderTarget.FillRectangle(
                    new RectangleF(panelLeft, panelTop, panelWidth, premiumY - panelTop),
                    _dxPremiumFill);
            }

            if (discountY > premiumY)
            {
                RenderTarget.FillRectangle(
                    new RectangleF(panelLeft, premiumY, panelWidth, discountY - premiumY),
                    _dxEquilibriumFill);
            }

            if (panelBottom > discountY)
            {
                RenderTarget.FillRectangle(
                    new RectangleF(panelLeft, discountY, panelWidth, panelBottom - discountY),
                    _dxDiscountFill);
            }
        }

        private void RenderBandBorders(float xLeft, float xRight, float premiumY, float discountY)
        {
            RenderTarget.DrawLine(
                new Vector2(xLeft, premiumY),
                new Vector2(xRight, premiumY),
                _dxPremiumLine,
                1.5f,
                _dxDash);

            RenderTarget.DrawLine(
                new Vector2(xLeft, discountY),
                new Vector2(xRight, discountY),
                _dxDiscountLine,
                1.5f,
                _dxDash);
        }

        private void RenderSfvLine(
            ChartControl chartControl,
            ChartScale chartScale,
            Dictionary<int, (double sfv, double premium, double discount)> sfvSnap,
            int from,
            int to,
            float panelTop,
            float panelBottom)
        {
            if (sfvSnap == null || sfvSnap.Count == 0)
                return;

            AntialiasMode prior = RenderTarget.AntialiasMode;
            RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

            bool hasPrev = false;
            float prevX = 0f;
            float prevY = 0f;

            for (int barIndex = from; barIndex <= to; barIndex++)
            {
                (double sfv, double premium, double discount) point;
                if (!sfvSnap.TryGetValue(barIndex, out point))
                {
                    hasPrev = false;
                    continue;
                }

                float x = (float)chartControl.GetXByBarIndex(ChartBars, barIndex);
                float y = ClampY(chartScale.GetYByValue(point.sfv), panelTop, panelBottom);

                if (hasPrev)
                    RenderTarget.DrawLine(new Vector2(prevX, prevY), new Vector2(x, y), _dxSfvLine, 2f);

                prevX = x;
                prevY = y;
                hasPrev = true;
            }

            RenderTarget.AntialiasMode = prior;
        }

        private void RenderZoneLabels(
            float panelLeft,
            float panelRight,
            float panelTop,
            float panelBottom,
            float premiumY,
            float discountY,
            float sfvY)
        {
            const float insetX = 12f;
            const float insetY = 6f;
            const float labelHeight = 18f;
            float width = Math.Min(180f, Math.Max(120f, panelRight - panelLeft - 24f));
            float x = panelLeft + insetX;

            float premCenter = panelTop + (premiumY - panelTop) * 0.5f;
            float eqCenter = premiumY + (discountY - premiumY) * 0.5f;
            float discCenter = discountY + (panelBottom - discountY) * 0.5f;

            DrawZoneLabel("PREMIUM ZONE", x, ClampLabelY(premCenter - labelHeight * 0.5f, panelTop, panelBottom, labelHeight, insetY), width, labelHeight, _dxPremiumLine);
            DrawZoneLabel("EQUILIBRIUM ZONE", x, ClampLabelY(eqCenter - labelHeight * 0.5f, panelTop, panelBottom, labelHeight, insetY), width, labelHeight, _dxMuted);
            DrawZoneLabel("DISCOUNT ZONE", x, ClampLabelY(discCenter - labelHeight * 0.5f, panelTop, panelBottom, labelHeight, insetY), width, labelHeight, _dxDiscountLine);

            float sfvTagWidth = 118f;
            float sfvTagX = panelRight - sfvTagWidth - 10f;
            float sfvTagY = ClampLabelY(sfvY - 10f, panelTop, panelBottom, 20f, insetY);
            RectangleF tagRect = new RectangleF(sfvTagX, sfvTagY, sfvTagWidth, 20f);
            RenderTarget.FillRectangle(tagRect, _dxPanel);
            RenderTarget.DrawRectangle(tagRect, _dxBorder, 1f);
            RenderTarget.DrawText("SFV " + FormatPrice(CurrentSFV), _fontData, tagRect, _dxSfvLine, DrawTextOptions.Clip);
        }

        private void DrawZoneLabel(string text, float x, float y, float width, float height, SharpDX.Direct2D1.Brush brush)
        {
            RectangleF rect = new RectangleF(x, y, width, height);
            RenderTarget.FillRectangle(rect, _dxPanel);
            RenderTarget.DrawRectangle(rect, _dxBorder, 1f);
            RenderTarget.DrawText(text, _fontLabels, rect, brush, DrawTextOptions.Clip);
        }

        private void RenderHeaderBar(float panelLeft, float panelTop)
        {
            float x = panelLeft + 10f;
            float y = panelTop + 10f;
            float width = 460f;
            float height = ShowDebugValues ? 72f : 56f;

            RectangleF barRect = new RectangleF(x, y, width, height);
            RenderTarget.FillRectangle(barRect, _dxPanel);
            RenderTarget.DrawRectangle(barRect, _dxBorder, 1f);

            RectangleF titleRect = new RectangleF(x + 10f, y + 6f, 220f, 20f);
            RectangleF symbolRect = new RectangleF(x + 10f, y + 28f, 140f, 16f);
            RectangleF priceLabelRect = new RectangleF(x + 155f, y + 8f, 60f, 16f);
            RectangleF priceValueRect = new RectangleF(x + 155f, y + 24f, 115f, 22f);
            RectangleF sfvLabelRect = new RectangleF(x + 275f, y + 8f, 60f, 16f);
            RectangleF sfvValueRect = new RectangleF(x + 275f, y + 24f, 115f, 22f);
            RectangleF zoneRect = new RectangleF(x + 395f, y + 8f, 55f, 16f);
            RectangleF zoneValueRect = new RectangleF(x + 395f, y + 24f, 55f, 22f);

            RenderTarget.DrawText("EQUILIBRIUM MODEL", _fontTitle, titleRect, _dxText, DrawTextOptions.Clip);
            RenderTarget.DrawText(Instrument != null ? Instrument.FullName : "UNKNOWN", _fontData, symbolRect, _dxMuted, DrawTextOptions.Clip);
            RenderTarget.DrawText("PRICE", _fontLabels, priceLabelRect, _dxMuted, DrawTextOptions.Clip);
            RenderTarget.DrawText(FormatPrice(Close[0]), _fontValues, priceValueRect, _dxText, DrawTextOptions.Clip);
            RenderTarget.DrawText("SFV", _fontLabels, sfvLabelRect, _dxMuted, DrawTextOptions.Clip);
            RenderTarget.DrawText(FormatPrice(CurrentSFV), _fontValues, sfvValueRect, _dxSfvLine, DrawTextOptions.Clip);
            RenderTarget.DrawText("ZONE", _fontLabels, zoneRect, _dxMuted, DrawTextOptions.Clip);
            RenderTarget.DrawText(GetZoneText(), _fontData, zoneValueRect, GetZoneBrush(), DrawTextOptions.Clip);

            if (ShowDebugValues)
            {
                RectangleF debugRect = new RectangleF(x + 10f, y + 50f, width - 20f, 16f);
                string debugText = "γ=" + _gammaRegime + "  Trend=" + _currentTrend + "  AVWAP=" + FormatPrice(_currentAVWAP) + "  Score=" + _biasScore;
                RenderTarget.DrawText(debugText, _fontData, debugRect, _dxMuted, DrawTextOptions.Clip);
            }
        }

        private void RenderBiasChip(float panelRight, float panelTop)
        {
            float width = 160f;
            float height = 34f;
            float x = panelRight - width - 12f;
            float y = panelTop + 12f;

            RectangleF chipRect = new RectangleF(x, y, width, height);
            SharpDX.Direct2D1.Brush chipBrush = GetBiasBrush();

            RenderTarget.FillRectangle(chipRect, chipBrush);
            RenderTarget.DrawRectangle(chipRect, _dxBorder, 1f);
            RenderTarget.DrawText(GetBiasText(), _fontBias, chipRect, _dxChipText, DrawTextOptions.Clip);
        }

        private void RenderStaleBadge(float panelRight, float panelTop, GexState gexState)
        {
            float width = 160f;
            float height = 24f;
            float x = panelRight - width - 12f;
            float y = panelTop + 52f;

            RectangleF badgeRect = new RectangleF(x, y, width, height);
            RenderTarget.FillRectangle(badgeRect, _dxStale);
            RenderTarget.DrawRectangle(badgeRect, _dxBorder, 1f);

            string text = "STALE FEED";
            if (gexState != null && !string.IsNullOrEmpty(gexState.StatusText) && !gexState.HasData)
                text = gexState.StatusText.ToUpperInvariant();

            RenderTarget.DrawText(text, _fontLabels, badgeRect, _dxChipText, DrawTextOptions.Clip);
        }

        private string GetZoneText()
        {
            switch (CurrentZone)
            {
                case ZoneType.Premium:
                    return "PREMIUM";
                case ZoneType.Discount:
                    return "DISCOUNT";
                case ZoneType.Equilibrium:
                    return "EQUIL";
                default:
                    return "UNKNOWN";
            }
        }

        private SharpDX.Direct2D1.Brush GetZoneBrush()
        {
            switch (CurrentZone)
            {
                case ZoneType.Premium:
                    return _dxBearish;
                case ZoneType.Discount:
                    return _dxBullish;
                case ZoneType.Equilibrium:
                    return _dxNeutral;
                default:
                    return _dxMuted;
            }
        }

        private string GetBiasText()
        {
            switch (CurrentBias)
            {
                case BiasDirection.Bullish:
                    return "BULLISH";
                case BiasDirection.Bearish:
                    return "BEARISH";
                default:
                    return "NEUTRAL";
            }
        }

        private SharpDX.Direct2D1.Brush GetBiasBrush()
        {
            switch (CurrentBias)
            {
                case BiasDirection.Bullish:
                    return _dxBullish;
                case BiasDirection.Bearish:
                    return _dxBearish;
                default:
                    return _dxNeutral;
            }
        }

        private static string FormatPrice(double value)
        {
            return value.ToString("F2");
        }

        private static float ClampY(float value, float min, float max)
        {
            if (value < min)
                return min;
            if (value > max)
                return max;
            return value;
        }

        private static float ClampLabelY(float value, float panelTop, float panelBottom, float labelHeight, float inset)
        {
            float min = panelTop + inset;
            float max = panelBottom - labelHeight - inset;
            if (value < min)
                return min;
            if (value > max)
                return max;
            return value;
        }
    }
}
