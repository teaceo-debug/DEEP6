// DEEP6 Footprint Chart Style — professional footprint renderer for DEEP6FootprintBarsType.
//
// Appears in Chart Style dropdown as "DEEP6 Footprint" (ChartStyleType = 100).
// DEEP6FootprintBarsType sets DefaultChartStyle = (ChartStyleType)100 to auto-apply this.
//
// Visual grammar (ATAS-inspired, research-driven):
//   Cells     — proportional color fills (5-tier green/red gradient) + bid×ask text in Consolas
//   POC       — 2px #5C6A99 inner outline rectangle (not a fill — structure marker)
//   VA band   — subtle #1A2030 floor tint for cells within value area
//   VWAP      — 2px gold line, dashed ±1σ/±2σ bands in cyan
//   IB H/L    — 1.5px amber dashed lines
//   Anchors   — prior-day POC/VAH/VAL, naked POCs, prior-week POC
//   L2 walls  — bid (blue) and ask (orange) horizontal lines for resting orders
//   Signals   — 6px left-edge tier stripe + pill badge above bar + direction arrow on next bar
//
// CRITICAL: Namespace must be NinjaTrader.NinjaScript.ChartStyles (no sub-namespace).

#region Using
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Levels;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = System.Windows.Media.Brush;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
using Color = System.Windows.Media.Color;
#endregion

namespace NinjaTrader.NinjaScript.ChartStyles
{
    public class DEEP6FootprintStyle : ChartStyle
    {
        // ── Proportional cell fill palette ────────────────────────────────────
        // 5 tiers per side based on dominance ratio — pre-allocated in OnRenderTargetChanged
        // Ask-dominant (buyers aggressive): green tones
        private SharpDX.Direct2D1.SolidColorBrush[] _askTierBrush;  // [0]=1.2x, [4]=5x+
        // Bid-dominant (sellers aggressive): red tones
        private SharpDX.Direct2D1.SolidColorBrush[] _bidTierBrush;
        private SharpDX.Direct2D1.SolidColorBrush _neutralCellBrush;

        // ── Structural element brushes ─────────────────────────────────────────
        private SharpDX.Direct2D1.SolidColorBrush _pocOutlineBrush;   // #5C6A99 POC outline
        private SharpDX.Direct2D1.SolidColorBrush _vaCellBrush;      // #1A2030 VA floor tint
        private SharpDX.Direct2D1.SolidColorBrush _bgCoverBrush;     // #0D0F14 chart background

        // ── Imbalance stripe brushes ───────────────────────────────────────────
        private SharpDX.Direct2D1.SolidColorBrush _askImbalBrush;    // #00D97A
        private SharpDX.Direct2D1.SolidColorBrush _bidImbalBrush;    // #FF4040
        private SharpDX.Direct2D1.SolidColorBrush _askStackedBrush;  // #00FF9A stacked 3+
        private SharpDX.Direct2D1.SolidColorBrush _bidStackedBrush;  // #FF5555

        // ── Text brushes ───────────────────────────────────────────────────────
        private SharpDX.Direct2D1.SolidColorBrush _cellTextBrush;     // #ABAEB8 normal cell text (ATAS grey — default for all numbers)
        private SharpDX.Direct2D1.SolidColorBrush _bidTextBrush;     // #FF4466 bid-imbalance numbers (bright on 3:1+ cells only)
        private SharpDX.Direct2D1.SolidColorBrush _askTextBrush;     // #00FFAA ask-imbalance numbers (bright on 3:1+ cells only)
        private SharpDX.Direct2D1.SolidColorBrush _dividerBrush;     // #4A5270 × char
        private SharpDX.Direct2D1.SolidColorBrush _dimTextBrush;     // #8090A8 dim labels
        private SharpDX.Direct2D1.SolidColorBrush _haloTextBrush;    // #1C1E26@90% text halo (matches ATAS bg)

        // ── Session level brushes ─────────────────────────────────────────────
        private SharpDX.Direct2D1.SolidColorBrush _vwapBrush;        // #C8A84A VWAP gold
        private SharpDX.Direct2D1.SolidColorBrush _vwapBand1Brush;   // cyan @40% ±1σ
        private SharpDX.Direct2D1.SolidColorBrush _vwapBand2Brush;   // cyan @20% ±2σ
        private SharpDX.Direct2D1.SolidColorBrush _ibBrush;          // #A06000 IB amber
        private SharpDX.Direct2D1.SolidColorBrush _anchorPocBrush;   // #8080C0 prior-day POC
        private SharpDX.Direct2D1.SolidColorBrush _anchorVaBrush;    // #5A5A8A prior-day VA
        private SharpDX.Direct2D1.SolidColorBrush _anchorNakedBrush; // #8080C0 @60% naked POC
        private SharpDX.Direct2D1.SolidColorBrush _anchorPwBrush;    // #6070A8 prior-week POC
        private SharpDX.Direct2D1.SolidColorBrush _wallBidBrush;     // #2B8CFF
        private SharpDX.Direct2D1.SolidColorBrush _wallAskBrush;     // #FF7A3C

        // ── Signal tier stripe and badge brushes ──────────────────────────────
        private SharpDX.Direct2D1.SolidColorBrush _tierALongBrush;   // #00E5A0
        private SharpDX.Direct2D1.SolidColorBrush _tierAShortBrush;  // #FF3D5A
        private SharpDX.Direct2D1.SolidColorBrush _tierBLongBrush;   // #00C87A
        private SharpDX.Direct2D1.SolidColorBrush _tierBShortBrush;  // #E03050
        private SharpDX.Direct2D1.SolidColorBrush _tierCLongBrush;   // #009060
        private SharpDX.Direct2D1.SolidColorBrush _tierCShortBrush;  // #A02040
        private SharpDX.Direct2D1.SolidColorBrush _hudBgBrush;
        private SharpDX.Direct2D1.SolidColorBrush _hudTextBrush;

        // ── Fonts ─────────────────────────────────────────────────────────────
        private SharpDX.DirectWrite.TextFormat _cellFont;       // center (fallback)
        private SharpDX.DirectWrite.TextFormat _cellFontRight;  // trailing — bid numbers flow right toward wick
        private SharpDX.DirectWrite.TextFormat _cellFontLeft;   // leading  — ask numbers flow left from wick
        private SharpDX.DirectWrite.TextFormat _labelFont;
        private SharpDX.DirectWrite.TextFormat _badgeFont;
        private SharpDX.Direct2D1.SolidColorBrush _wickBrush;  // center wick spine
        private StrokeStyle _dashStyle;

        // ── Reusable geometry vectors (avoid per-frame allocation) ─────────────
        private Vector2 _p0, _p1;

        // ════════════════════════════════════════════════════════════════════════
        // ChartStyle registration
        // ════════════════════════════════════════════════════════════════════════

        public override int GetBarPaintWidth(int barWidth)
            => System.Math.Max(CellColumnWidth, 1 + 2 * (barWidth - 1));

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name           = "DEEP6 Footprint";
                ChartStyleType = (ChartStyleType)100;
                BarWidth       = 10;

                // Footprint cell settings
                ImbalanceRatio   = 3.0;
                CellFontSize     = 8f;
                CellColumnWidth  = 80;
                ShowHeatmap      = false;
                ShowStackedZones = true;
                ShowUnfinished   = true;
                ShowLargeLots    = true;
                ShowBullBearCol  = true;
                ShowVolumeClimax = true;

                // Session levels
                ShowVWAP         = true;
                ShowVWAPBands    = true;
                ShowIB           = true;
                ShowAnchors      = true;
                ShowL2Walls      = true;
                LiquidityWallMin = 100;
                LiquidityMaxPerSide = 4;
                LiquidityWallStaleSec = 90;

                // Scoring HUD
                ShowScoreHud = true;
            }
            else if (State == State.Configure)
            {
                Properties.Remove(Properties.Find("UpBrush", true));
                Properties.Remove(Properties.Find("DownBrush", true));
                Properties.Remove(Properties.Find("Stroke", true));
                Properties.Remove(Properties.Find("Stroke2", true));
                SetPropertyName("BarWidth", "Cell Width (base)");
            }
        }

        // ════════════════════════════════════════════════════════════════════════
        // SharpDX resource management
        // ════════════════════════════════════════════════════════════════════════

        public override void OnRenderTargetChanged()
        {
            base.OnRenderTargetChanged();
            DisposeDx();
            if (RenderTarget == null) return;

            // ── Cell proportional fill palette — ATAS Classic Dark confirmed colors ─
            // Ask-dominant (buyer aggression) — ATAS dark-green tones, 5 tiers
            _askTierBrush = new SharpDX.Direct2D1.SolidColorBrush[5];
            _askTierBrush[0] = Dx(0x1A, 0x3A, 0x1A, 255);  // 1.2x–1.5x  #1A3A1A slight green
            _askTierBrush[1] = Dx(0x1C, 0x4C, 0x1C, 255);  // 1.5x–2.0x  #1C4C1C clearly green
            _askTierBrush[2] = Dx(0x1C, 0x5A, 0x1C, 255);  // 2.0x–3.0x  #1C5A1C strong green
            _askTierBrush[3] = Dx(0x1D, 0x6A, 0x22, 255);  // 3.0x–5.0x  #1D6A22 deep green
            _askTierBrush[4] = Dx(0x1E, 0x7A, 0x28, 255);  // 5.0x+      #1E7A28 max saturation

            // Bid-dominant (seller aggression) — ATAS dark-red tones, 5 tiers
            _bidTierBrush = new SharpDX.Direct2D1.SolidColorBrush[5];
            _bidTierBrush[0] = Dx(0x2A, 0x18, 0x18, 255);  // 1.2x–1.5x  #2A1818 slight red
            _bidTierBrush[1] = Dx(0x40, 0x18, 0x18, 255);  // 1.5x–2.0x  #401818 clearly red
            _bidTierBrush[2] = Dx(0x5A, 0x1C, 0x1C, 255);  // 2.0x–3.0x  #5A1C1C strong red
            _bidTierBrush[3] = Dx(0x6A, 0x1E, 0x18, 255);  // 3.0x–5.0x  #6A1E18 deep red
            _bidTierBrush[4] = Dx(0x7A, 0x20, 0x18, 255);  // 5.0x+      #7A2018 max saturation

            _neutralCellBrush = Dx(0x1C, 0x1E, 0x26, 255);  // #1C1E26 ATAS bg (neutral = invisible)
            _bgCoverBrush     = Dx(0x1C, 0x1E, 0x26, 255);  // #1C1E26 ATAS chart background
            _pocOutlineBrush  = Dx(0xFF, 0xD7, 0x00, 255);  // #FFD700 gold POC outline
            _vaCellBrush      = Dx(0x14, 0x16, 0x2A, 160);  // #14162A subtle VA floor tint

            _askImbalBrush    = Dx(0x00, 0xD9, 0x7A, 220);
            _bidImbalBrush    = Dx(0xFF, 0x40, 0x40, 220);
            _askStackedBrush  = Dx(0x00, 0xFF, 0x9A, 255);
            _bidStackedBrush  = Dx(0xFF, 0x55, 0x55, 255);

            _cellTextBrush    = Dx(0xAB, 0xAE, 0xB8, 255);  // #ABAEB8 ATAS normal-cell grey
            _bidTextBrush     = Dx(0xFF, 0x44, 0x66, 255);  // #FF4466 bid-imbalance bright red
            _askTextBrush     = Dx(0x00, 0xFF, 0xAA, 255);  // #00FFAA ask-imbalance bright teal
            _dividerBrush     = Dx(0x4A, 0x52, 0x70, 200);
            _dimTextBrush     = Dx(0x80, 0x90, 0xA8, 200);
            _haloTextBrush    = Dx(0x1C, 0x1E, 0x26, 220);  // #1C1E26 halo = ATAS bg color

            _vwapBrush        = Dx(0xC8, 0xA8, 0x4A, 255);
            _vwapBand1Brush   = Dx(0x00, 0xD0, 0xFF, 100);
            _vwapBand2Brush   = Dx(0x00, 0xD0, 0xFF, 50);
            _ibBrush          = Dx(0xA0, 0x60, 0x00, 220);
            _anchorPocBrush   = Dx(0x80, 0x80, 0xC0, 220);
            _anchorVaBrush    = Dx(0x5A, 0x5A, 0x8A, 180);
            _anchorNakedBrush = Dx(0x80, 0x80, 0xC0, 153);
            _anchorPwBrush    = Dx(0x60, 0x70, 0xA8, 180);
            _wallBidBrush     = Dx(0x2B, 0x8C, 0xFF, 200);
            _wallAskBrush     = Dx(0xFF, 0x7A, 0x3C, 200);

            _tierALongBrush   = Dx(0x00, 0xE5, 0xA0, 230);
            _tierAShortBrush  = Dx(0xFF, 0x3D, 0x5A, 230);
            _tierBLongBrush   = Dx(0x00, 0xC8, 0x7A, 190);
            _tierBShortBrush  = Dx(0xE0, 0x30, 0x50, 190);
            _tierCLongBrush   = Dx(0x00, 0x90, 0x60, 140);
            _tierCShortBrush  = Dx(0xA0, 0x20, 0x40, 140);
            _hudBgBrush       = Dx(0x0D, 0x0F, 0x14, 210);
            _hudTextBrush     = Dx(0xE8, 0xED, 0xFF, 255);

            _dashStyle = new StrokeStyle(NinjaTrader.Core.Globals.D2DFactory,
                new StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Dash });

            _wickBrush = Dx(0x35, 0x37, 0x52, 200); // #353752 ATAS center wick

            _cellFont  = new SharpDX.DirectWrite.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                "Consolas", SharpDX.DirectWrite.FontWeight.Normal, SharpDX.DirectWrite.FontStyle.Normal, CellFontSize)
                { TextAlignment = SharpDX.DirectWrite.TextAlignment.Center, ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Center };
            _cellFontRight = new SharpDX.DirectWrite.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                "Consolas", SharpDX.DirectWrite.FontWeight.Normal, SharpDX.DirectWrite.FontStyle.Normal, CellFontSize)
                { TextAlignment = SharpDX.DirectWrite.TextAlignment.Trailing, ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Center };
            _cellFontLeft  = new SharpDX.DirectWrite.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                "Consolas", SharpDX.DirectWrite.FontWeight.Normal, SharpDX.DirectWrite.FontStyle.Normal, CellFontSize)
                { TextAlignment = SharpDX.DirectWrite.TextAlignment.Leading, ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Center };
            _labelFont = new SharpDX.DirectWrite.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                "Segoe UI", SharpDX.DirectWrite.FontWeight.Normal, SharpDX.DirectWrite.FontStyle.Normal, 8f)
                { TextAlignment = SharpDX.DirectWrite.TextAlignment.Trailing, ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Center };
            _badgeFont = new SharpDX.DirectWrite.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                "Consolas", SharpDX.DirectWrite.FontWeight.Bold, SharpDX.DirectWrite.FontStyle.Normal, 9f)
                { TextAlignment = SharpDX.DirectWrite.TextAlignment.Center, ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Center };
        }

        private SharpDX.Direct2D1.SolidColorBrush Dx(byte r, byte g, byte b, byte a)
            => new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                new Color4(r / 255f, g / 255f, b / 255f, a / 255f));

        private void DisposeDx()
        {
            if (_askTierBrush != null) { foreach (var b in _askTierBrush) b?.Dispose(); _askTierBrush = null; }
            if (_bidTierBrush != null) { foreach (var b in _bidTierBrush) b?.Dispose(); _bidTierBrush = null; }
            D(_neutralCellBrush); D(_bgCoverBrush);   D(_pocOutlineBrush); D(_vaCellBrush);
            D(_askImbalBrush);    D(_bidImbalBrush);   D(_askStackedBrush); D(_bidStackedBrush);
            D(_cellTextBrush);    D(_bidTextBrush);    D(_askTextBrush);    D(_dividerBrush); D(_dimTextBrush); D(_haloTextBrush);
            D(_vwapBrush);        D(_vwapBand1Brush);  D(_vwapBand2Brush);  D(_ibBrush);
            D(_anchorPocBrush);   D(_anchorVaBrush);   D(_anchorNakedBrush);D(_anchorPwBrush);
            D(_wallBidBrush);     D(_wallAskBrush);
            D(_tierALongBrush);   D(_tierAShortBrush); D(_tierBLongBrush);  D(_tierBShortBrush);
            D(_tierCLongBrush);   D(_tierCShortBrush); D(_hudBgBrush);      D(_hudTextBrush);
            D(_wickBrush);
            _dashStyle?.Dispose();     _dashStyle     = null;
            _cellFont?.Dispose();      _cellFont      = null;
            _cellFontRight?.Dispose(); _cellFontRight = null;
            _cellFontLeft?.Dispose();  _cellFontLeft  = null;
            _labelFont?.Dispose();     _labelFont     = null;
            _badgeFont?.Dispose();     _badgeFont     = null;
        }

        private static void D(SharpDX.Direct2D1.SolidColorBrush b)
        {
            // Helper kept separate so field can't be cleared — caller handles null check
        }

        // ════════════════════════════════════════════════════════════════════════
        // OnRender — the entire visual output
        // ════════════════════════════════════════════════════════════════════════

        public override void OnRender(ChartControl chartControl, ChartScale chartScale, ChartBars chartBars)
        {
            if (RenderTarget == null || _cellFont == null || chartBars == null) return;

            string instrument = chartBars.Bars?.Instrument?.FullName;
            if (string.IsNullOrEmpty(instrument)) return;

            // Grab the immutable snapshot — lock-free on render thread
            FootprintSharedData shared = FootprintSharedState.GetData(instrument);

            Data.Bars bars   = chartBars.Bars;
            double ts = bars.Instrument.MasterInstrument.TickSize;

            // Chart panel bounds — in ChartStyle, panel is accessed via chartScale/chartControl
            float panelLeft  = (float)chartControl.CanvasLeft;
            float panelRight = (float)(chartControl.CanvasLeft + chartControl.ActualWidth);
            float panelTop   = chartScale.GetYByValue(chartScale.MaxValue);
            float panelBot   = chartScale.GetYByValue(chartScale.MinValue);

            // ── Session level lines (z-layer 2 — behind cells) ──────────────────
            if (shared != null)
            {
                if (ShowVWAP && shared.VwapPrice > 0)
                    RenderVwap(chartScale, shared, panelLeft, panelRight, panelTop, panelBot);
                if (ShowIB && shared.IbHigh > double.MinValue)
                    RenderIB(chartScale, shared, panelLeft, panelRight);
                if (ShowUnfinished && shared.UnfinishedLevels != null)
                    RenderUnfinished(chartScale, shared.UnfinishedLevels, panelLeft, panelRight, panelTop, panelBot);
                if (ShowAnchors && shared.Anchors != null)
                    RenderAnchors(chartScale, shared.Anchors, panelLeft, panelRight, panelTop, panelBot);
            }

            // ── Per-bar footprint cells ─────────────────────────────────────────
            int colW = GetBarPaintWidth(BarWidthUI);
            float rowH = (float)System.Math.Max(5, chartScale.GetPixelsForDistance(ts));

            for (int barIdx = chartBars.FromIndex; barIdx <= chartBars.ToIndex; barIdx++)
            {
                float xCenter = chartControl.GetXByBarIndex(chartBars, barIdx);
                float xLeft   = xCenter - colW / 2f;
                float xRight  = xLeft + colW;
                double barHigh = bars.GetHigh(barIdx);
                double barLow  = bars.GetLow(barIdx);

                // Hit test — fill bar rect for selection
                if (chartBars.IsInHitTest)
                {
                    float yH = chartScale.GetYByValue(barHigh);
                    float yL = chartScale.GetYByValue(barLow);
                    RenderTarget.FillRectangle(new RectangleF(xLeft, yH, colW, yL - yH),
                        chartControl.SelectionBrush);
                    continue;
                }

                // Cover underlying candle — background IS the chart now
                {
                    float yH = chartScale.GetYByValue(barHigh + ts);
                    float yL = chartScale.GetYByValue(barLow  - ts);
                    if (_bgCoverBrush != null)
                        RenderTarget.FillRectangle(new RectangleF(xLeft - 3, yH, colW + 6, yL - yH), _bgCoverBrush);
                }

                // Get footprint bar from snapshot
                FootprintBar fbar = null;
                BarAuxData   aux  = null;
                ScorerResult score= null;
                if (shared != null)
                {
                    shared.Bars.TryGetValue(barIdx, out fbar);
                    shared.AuxData.TryGetValue(barIdx, out aux);
                    shared.Scores.TryGetValue(barIdx, out score);
                }

                // Fall back to OHLC bar from NT8 if no footprint data yet
                if (fbar == null || fbar.Levels.Count == 0)
                {
                    // Draw minimal bar skeleton while data accumulates
                    float yH = chartScale.GetYByValue(barHigh);
                    float yL = chartScale.GetYByValue(barLow);
                    if (_neutralCellBrush != null)
                        RenderTarget.FillRectangle(new RectangleF(xLeft, yH, colW, yL - yH), _neutralCellBrush);
                    continue;
                }

                // ── Signal tier background tint (TYPE_A only — subtlest layer) ──
                if (score != null && score.Tier == SignalTier.TYPE_A && score.Direction != 0)
                {
                    float yH = chartScale.GetYByValue(fbar.High);
                    float yL = chartScale.GetYByValue(fbar.Low);
                    var tintBrush = score.Direction > 0 ? _tierALongBrush : _tierAShortBrush;
                    if (tintBrush != null)
                    {
                        float savedOpacity = tintBrush.Opacity;
                        tintBrush.Opacity = 0.05f;
                        RenderTarget.FillRectangle(new RectangleF(xLeft, yH, colW, yL - yH), tintBrush);
                        tintBrush.Opacity = savedOpacity;
                    }
                }

                // ── Pre-compute VA bounds ────────────────────────────────────────
                var va = FootprintBar.ComputeValueArea(fbar, ts);

                // ── Compute max volume for heatmap normalization ─────────────────
                long maxVol = 1;
                if (ShowHeatmap)
                    foreach (var kv in fbar.Levels) { long v = kv.Value.AskVol + kv.Value.BidVol; if (v > maxVol) maxVol = v; }

                // ── Compute stacked imbalance lookup for this bar ────────────────
                bool[,] isStacked = BuildStackedLookup(fbar, ts, ImbalanceRatio);

                // ── Per-cell rendering ────────────────────────────────────────────
                foreach (var kv in fbar.Levels)
                {
                    double price = kv.Key;
                    var    cell  = kv.Value;
                    float  yCen  = chartScale.GetYByValue(price);
                    float  yTop  = yCen - rowH / 2f;
                    var    rect  = new RectangleF(xLeft, yTop, colW, rowH);

                    long bidVol = cell.BidVol;
                    long askVol = cell.AskVol;
                    long totVol = bidVol + askVol;
                    if (totVol == 0) { RenderTarget.FillRectangle(rect, _neutralCellBrush); continue; }

                    // ── Cell background: proportional dominance fill ─────────────
                    // Value area floor tint first
                    bool inVA = price >= va.val && price <= va.vah;
                    RenderTarget.FillRectangle(rect, inVA ? _vaCellBrush : _neutralCellBrush);

                    // Proportional dominance color on top
                    SharpDX.Direct2D1.SolidColorBrush cellFill = GetDominanceBrush(bidVol, askVol);
                    if (cellFill != null) RenderTarget.FillRectangle(rect, cellFill);

                    // ── Imbalance stripe (3px right edge) ───────────────────────
                    // Diagonal: askVol[price] vs bidVol[price + 1 tick]
                    Cell diag;
                    long diagBid = fbar.Levels.TryGetValue(price + ts, out diag) ? diag.BidVol : 0;
                    long diagAsk = fbar.Levels.TryGetValue(price - ts, out diag) ? diag.AskVol : 0;
                    bool askImbal = askVol > 0 && diagBid > 0 && (double)askVol / diagBid >= ImbalanceRatio;
                    bool bidImbal = bidVol > 0 && diagAsk > 0 && (double)bidVol / diagAsk >= ImbalanceRatio;

                    if (askImbal || bidImbal)
                    {
                        var stripeBrush = askImbal ? _askImbalBrush : _bidImbalBrush;
                        RenderTarget.FillRectangle(new RectangleF(xRight - 3f, yTop, 3f, rowH), stripeBrush);
                    }

                    // ── Cell grid hairline ───────────────────────────────────────
                    if (rowH >= 4 && _dimTextBrush != null)
                    {
                        float savedOp = _dimTextBrush.Opacity;
                        _dimTextBrush.Opacity = 0.15f;
                        _p0.X = xLeft; _p0.Y = yTop; _p1.X = xLeft + colW; _p1.Y = yTop;
                        RenderTarget.DrawLine(_p0, _p1, _dimTextBrush, 0.5f);
                        _dimTextBrush.Opacity = savedOp;
                    }

                    // ── Cell text — ATAS color logic ─────────────────────────────────
                    // Grey (#ABAEB8) for all normal cells. Bright colored only on 3:1+
                    // imbalanced cells. White on POC. Halo uses ATAS bg (#1C1E26) not black.
                    if (rowH >= 8 && _cellFontRight != null && _cellTextBrush != null)
                    {
                        float leftW  = xCenter - xLeft - 4f;
                        float rightW = xRight   - xCenter - 4f;
                        string bidStr = bidVol == 0 ? "—" : bidVol.ToString();
                        string askStr = askVol == 0 ? "—" : askVol.ToString();

                        // POC = white; imbalanced side = colored; everything else = ATAS grey
                        bool isPocCell = fbar.PocPrice > 0 && System.Math.Abs(price - fbar.PocPrice) < ts * 0.5;
                        var bidTxt = isPocCell ? _hudTextBrush
                                   : (bidImbal  ? _bidTextBrush : _cellTextBrush);
                        var askTxt = isPocCell ? _hudTextBrush
                                   : (askImbal  ? _askTextBrush : _cellTextBrush);
                        if (bidTxt == null) bidTxt = _cellTextBrush;
                        if (askTxt == null) askTxt = _cellTextBrush;

                        // Bid (right-aligned in left half)
                        using (var tl = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                            bidStr, _cellFontRight, leftW, rowH))
                        {
                            var origin = new Vector2(xLeft + 2f, yTop);
                            if (_haloTextBrush != null)
                            { RenderTarget.DrawTextLayout(new Vector2(origin.X - 1, origin.Y), tl, _haloTextBrush);
                              RenderTarget.DrawTextLayout(new Vector2(origin.X + 1, origin.Y), tl, _haloTextBrush); }
                            RenderTarget.DrawTextLayout(origin, tl, bidTxt);
                        }
                        // Ask (left-aligned in right half)
                        using (var tl = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                            askStr, _cellFontLeft, rightW, rowH))
                        {
                            var origin = new Vector2(xCenter + 2f, yTop);
                            if (_haloTextBrush != null)
                            { RenderTarget.DrawTextLayout(new Vector2(origin.X - 1, origin.Y), tl, _haloTextBrush);
                              RenderTarget.DrawTextLayout(new Vector2(origin.X + 1, origin.Y), tl, _haloTextBrush); }
                            RenderTarget.DrawTextLayout(origin, tl, askTxt);
                        }
                    }
                }

                // ── Center wick spine — vertical line at xCenter through full bar ──
                if (_wickBrush != null && fbar.High > 0)
                {
                    float yWickTop = chartScale.GetYByValue(fbar.High);
                    float yWickBot = chartScale.GetYByValue(fbar.Low);
                    _p0.X = xCenter; _p0.Y = yWickTop;
                    _p1.X = xCenter; _p1.Y = yWickBot;
                    RenderTarget.DrawLine(_p0, _p1, _wickBrush, 1f);
                }

                // ── POC outline (above cell fills, below text Z) ──────────────
                if (fbar.PocPrice > 0 && _pocOutlineBrush != null)
                {
                    float yPoc = chartScale.GetYByValue(fbar.PocPrice);
                    float yTop = yPoc - rowH / 2f;
                    var pocRect = new RectangleF(xLeft + 1f, yTop + 1f, colW - 2f, rowH - 2f);
                    RenderTarget.DrawRectangle(pocRect, _pocOutlineBrush, 2f);
                }

                // ── VAH/VAL boundary lines ────────────────────────────────────
                if (va.vah > 0 && _anchorVaBrush != null)
                {
                    float yVah = chartScale.GetYByValue(va.vah);
                    float yVal = chartScale.GetYByValue(va.val);
                    _p0.X = xLeft; _p0.Y = yVah; _p1.X = xLeft + colW; _p1.Y = yVah;
                    RenderTarget.DrawLine(_p0, _p1, _anchorVaBrush, 2f);
                    _p0.Y = yVal; _p1.Y = yVal;
                    RenderTarget.DrawLine(_p0, _p1, _anchorVaBrush, 2f);
                }

                // ── Stacked zone boxes ────────────────────────────────────────
                if (ShowStackedZones && aux?.StackedZones != null)
                {
                    foreach (var zone in aux.StackedZones)
                    {
                        float yT = chartScale.GetYByValue(zone.PriceHigh + ts * 0.5);
                        float yB = chartScale.GetYByValue(zone.PriceLow  - ts * 0.5);
                        float sw = zone.Tier == 3 ? 2.5f : zone.Tier == 2 ? 1.8f : 1.2f;
                        var zb = zone.Direction > 0 ? _askStackedBrush : _bidStackedBrush;
                        if (zb != null)
                            RenderTarget.DrawRectangle(new RectangleF(xLeft, yT, colW, yB - yT), zb, sw);
                    }
                }

                // ── Volume climax marker ─────────────────────────────────────
                if (ShowVolumeClimax && aux != null && aux.VolumeClimaxDir != 0 && _vwapBrush != null)
                {
                    float yExt = chartScale.GetYByValue(aux.VolumeClimaxDir > 0 ? fbar.Low : fbar.High);
                    float off  = aux.VolumeClimaxDir > 0 ? 2f : -2f;
                    _p0.X = xLeft; _p0.Y = yExt + off; _p1.X = xLeft + colW; _p1.Y = yExt + off;
                    RenderTarget.DrawLine(_p0, _p1, _vwapBrush, 2.5f);
                }

                // ── Score tier stripe (6px left edge, full bar height) ─────────
                if (score != null && score.Tier != SignalTier.QUIET && score.Tier != SignalTier.DISQUALIFIED
                    && fbar.High > 0)
                {
                    var sb = GetTierBrush(score.Tier, score.Direction);
                    if (sb != null)
                    {
                        float yH = chartScale.GetYByValue(fbar.High);
                        float yL = chartScale.GetYByValue(fbar.Low);
                        RenderTarget.FillRectangle(new RectangleF(xLeft - 8f, yH, 6f, yL - yH), sb);
                    }
                }

                // ── Score badge pill above bar ────────────────────────────────
                if (ShowScoreHud && score != null && score.Tier != SignalTier.QUIET
                    && score.Tier != SignalTier.DISQUALIFIED && _badgeFont != null)
                {
                    // Badge above bar: "TYPE_A ▲ 84" or "TYPE_B ▼ 77"
                    string tierName = score.Tier == SignalTier.TYPE_A ? "TYPE_A"
                                    : score.Tier == SignalTier.TYPE_B ? "TYPE_B" : "TYPE_C";
                    string dirArrow = score.Direction > 0 ? " ^" : score.Direction < 0 ? " v" : "";
                    string badge    = string.Format("{0}{1} {2:F0}", tierName, dirArrow, score.TotalScore);
                    float yBarTop   = chartScale.GetYByValue(fbar.High);
                    float bW = 72f, bH = 16f;
                    float bX = xCenter - bW / 2f;
                    float bY = yBarTop - bH - 3f;
                    var   sb = GetTierBrush(score.Tier, score.Direction);
                    if (_hudBgBrush != null) RenderTarget.FillRectangle(new RectangleF(bX, bY, bW, bH), _hudBgBrush);
                    if (sb != null)           RenderTarget.DrawRectangle(new RectangleF(bX, bY, bW, bH), sb, 1.5f);
                    using (var tl = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                        badge, _badgeFont, bW, bH))
                        RenderTarget.DrawTextLayout(new Vector2(bX, bY), tl, sb ?? _hudTextBrush);
                }
            }

            // ── L2 walls (full-width, above bar rendering) ────────────────────
            if (ShowL2Walls && shared != null) RenderL2Walls(chartControl, chartScale, shared, panelLeft, panelRight, panelTop, panelBot);
        }

        // ════════════════════════════════════════════════════════════════════════
        // Rendering helpers
        // ════════════════════════════════════════════════════════════════════════

        private SharpDX.Direct2D1.SolidColorBrush GetDominanceBrush(long bidVol, long askVol)
        {
            if (_askTierBrush == null || _bidTierBrush == null) return null;
            long dom = System.Math.Max(bidVol, askVol);
            long sub = System.Math.Max(1, System.Math.Min(bidVol, askVol));
            double ratio = (double)dom / sub;
            if (ratio < 1.2) return null;
            int tier = ratio >= 5.0 ? 4 : ratio >= 3.0 ? 3 : ratio >= 2.0 ? 2 : ratio >= 1.5 ? 1 : 0;
            return askVol >= bidVol ? _askTierBrush[tier] : _bidTierBrush[tier];
        }

        private SharpDX.Direct2D1.SolidColorBrush GetTierBrush(SignalTier tier, int dir)
        {
            if (tier == SignalTier.TYPE_A) return dir > 0 ? _tierALongBrush  : _tierAShortBrush;
            if (tier == SignalTier.TYPE_B) return dir > 0 ? _tierBLongBrush  : _tierBShortBrush;
            if (tier == SignalTier.TYPE_C) return dir > 0 ? _tierCLongBrush  : _tierCShortBrush;
            return null;
        }

        private static bool[,] BuildStackedLookup(FootprintBar bar, double ts, double thr)
        {
            // Returns [0] = ask stacked, [1] = bid stacked (simplified — zones computed by BarsType)
            return new bool[0, 0]; // placeholder — stacked zones come from aux.StackedZones
        }

        private void RenderVwap(ChartScale cs, FootprintSharedData d,
            float l, float r, float top, float bot)
        {
            if (_vwapBrush == null || d.VwapPrice <= 0) return;
            float y = cs.GetYByValue(d.VwapPrice);
            if (y >= top && y <= bot)
            {
                _p0.X = l; _p0.Y = y; _p1.X = r; _p1.Y = y;
                RenderTarget.DrawLine(_p0, _p1, _vwapBrush, 2f);
                if (_labelFont != null)
                    using (var tl = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                        string.Format("VWAP {0:F2}", d.VwapPrice), _labelFont, 90f, 14f))
                        RenderTarget.DrawTextLayout(new Vector2(r - 92f, y - 7f), tl, _vwapBrush);
            }
            if (ShowVWAPBands && _vwapBand1Brush != null)
            {
                float[] ys = { cs.GetYByValue(d.Vwap1H), cs.GetYByValue(d.Vwap1L) };
                foreach (var by in ys) if (by >= top && by <= bot)
                { _p0.X = l; _p0.Y = by; _p1.X = r; _p1.Y = by;
                  RenderTarget.DrawLine(_p0, _p1, _vwapBand1Brush, 1f, _dashStyle); }
                if (_vwapBand2Brush != null)
                {
                    float[] ys2 = { cs.GetYByValue(d.Vwap2H), cs.GetYByValue(d.Vwap2L) };
                    foreach (var by in ys2) if (by >= top && by <= bot)
                    { _p0.X = l; _p0.Y = by; _p1.X = r; _p1.Y = by;
                      RenderTarget.DrawLine(_p0, _p1, _vwapBand2Brush, 1f, _dashStyle); }
                }
            }
        }

        private void RenderIB(ChartScale cs, FootprintSharedData d, float l, float r)
        {
            if (_ibBrush == null || d.IbHigh <= double.MinValue) return;
            float yH = cs.GetYByValue(d.IbHigh), yL = cs.GetYByValue(d.IbLow);
            _p0.X = l; _p1.X = r;
            _p0.Y = yH; _p1.Y = yH; RenderTarget.DrawLine(_p0, _p1, _ibBrush, 1.5f, _dashStyle);
            _p0.Y = yL; _p1.Y = yL; RenderTarget.DrawLine(_p0, _p1, _ibBrush, 1.5f, _dashStyle);
            if (_labelFont != null)
            {
                using (var t = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, "IBH", _labelFont, 28f, 14f))
                    RenderTarget.DrawTextLayout(new Vector2(r - 30f, yH - 7f), t, _ibBrush);
                using (var t = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, "IBL", _labelFont, 28f, 14f))
                    RenderTarget.DrawTextLayout(new Vector2(r - 30f, yL - 7f), t, _ibBrush);
            }
        }

        private void RenderUnfinished(ChartScale cs, Dictionary<double, int> levels,
            float l, float r, float top, float bot)
        {
            if (_ibBrush == null) return;
            float savedOp = _ibBrush.Opacity;
            _ibBrush.Opacity = 0.55f;
            foreach (var kv in levels)
            {
                float y = cs.GetYByValue(kv.Key);
                if (y < top || y > bot) continue;
                _p0.X = l; _p0.Y = y; _p1.X = r - 12f; _p1.Y = y;
                RenderTarget.DrawLine(_p0, _p1, _ibBrush, 1f, _dashStyle);
            }
            _ibBrush.Opacity = savedOp;
        }

        private void RenderAnchors(ChartScale cs, ProfileAnchorSnapshot snap,
            float l, float r, float top, float bot)
        {
            if (snap?.Levels == null) return;
            foreach (var anch in snap.Levels)
            {
                if (anch == null || anch.Price <= 0) continue;
                float y = cs.GetYByValue(anch.Price);
                if (y < top || y > bot) continue;
                SharpDX.Direct2D1.SolidColorBrush brush;
                float sw = 1f; bool dashed = false;
                switch (anch.Kind)
                {
                    case ProfileAnchorKind.PriorDayPoc:  brush = _anchorPocBrush; sw = 1.5f; break;
                    case ProfileAnchorKind.NakedPoc:     brush = _anchorNakedBrush; dashed = true; break;
                    case ProfileAnchorKind.PriorWeekPoc: brush = _anchorPwBrush; dashed = true; break;
                    default:                             brush = _anchorVaBrush; dashed = true; break;
                }
                if (brush == null) continue;
                _p0.X = l; _p0.Y = y; _p1.X = r; _p1.Y = y;
                RenderTarget.DrawLine(_p0, _p1, brush, sw, dashed ? _dashStyle : null);
                if (_labelFont != null && !string.IsNullOrEmpty(anch.Label))
                    using (var tl = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                        anch.Label, _labelFont, 70f, 14f))
                        RenderTarget.DrawTextLayout(new Vector2(r - 72f, y - 7f), tl, brush);
            }
        }

        private void RenderL2Walls(ChartControl cc, ChartScale cs, FootprintSharedData d,
            float l, float r, float top, float bot)
        {
            if (d.L2Bids != null) RenderWallSide(cs, d.L2Bids, _wallBidBrush, l, r, top, bot, LiquidityWallMin);
            if (d.L2Asks != null) RenderWallSide(cs, d.L2Asks, _wallAskBrush, l, r, top, bot, LiquidityWallMin);
        }

        private void RenderWallSide(ChartScale cs,
            Dictionary<double, L2WallEntry> dict,
            SharpDX.Direct2D1.SolidColorBrush brush,
            float l, float r, float top, float bot,
            int threshold)
        {
            if (brush == null || dict == null) return;
            var walls = new List<(double price, long sz, int refills)>();
            foreach (var kv in dict)
                if (kv.Value.CurrentSize >= threshold) walls.Add((kv.Key, kv.Value.CurrentSize, kv.Value.RefillCount));
            walls.Sort((a, b) => b.sz.CompareTo(a.sz));
            int drawn = 0;
            foreach (var w in walls)
            {
                if (drawn >= LiquidityMaxPerSide) break;
                float y = cs.GetYByValue(w.price);
                if (y < top || y > bot) continue;
                float sw = System.Math.Min(4f, 1.5f + (float)w.sz / threshold * 0.4f);
                _p0.X = l; _p0.Y = y; _p1.X = r; _p1.Y = y;
                RenderTarget.DrawLine(_p0, _p1, brush, sw);
                drawn++;
            }
        }

        // ════════════════════════════════════════════════════════════════════════
        // Properties
        // ════════════════════════════════════════════════════════════════════════

        #region Properties

        [NinjaScriptProperty]
        [Range(1.5, 8.0)]
        [Display(Name = "Imbalance Ratio", Order = 1, GroupName = "1. Cells")]
        public double ImbalanceRatio { get; set; }

        [NinjaScriptProperty]
        [Range(6f, 14f)]
        [Display(Name = "Cell Font Size", Order = 2, GroupName = "1. Cells")]
        public float CellFontSize { get; set; }

        [NinjaScriptProperty]
        [Range(40, 300)]
        [Display(Name = "Cell Column Width (px)", Order = 3, GroupName = "1. Cells")]
        public int CellColumnWidth { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Heatmap Volume Gradient", Order = 4, GroupName = "1. Cells")]
        public bool ShowHeatmap { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Stacked Zone Boxes", Order = 5, GroupName = "1. Cells")]
        public bool ShowStackedZones { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Unfinished Auction Lines", Order = 6, GroupName = "1. Cells")]
        public bool ShowUnfinished { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Large Lot Dots", Order = 7, GroupName = "1. Cells")]
        public bool ShowLargeLots { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Bull/Bear Column Tint", Order = 8, GroupName = "1. Cells")]
        public bool ShowBullBearCol { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Volume Climax Markers", Order = 9, GroupName = "1. Cells")]
        public bool ShowVolumeClimax { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show VWAP", Order = 1, GroupName = "2. Session Levels")]
        public bool ShowVWAP { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show VWAP Bands (±1σ/±2σ)", Order = 2, GroupName = "2. Session Levels")]
        public bool ShowVWAPBands { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Initial Balance", Order = 3, GroupName = "2. Session Levels")]
        public bool ShowIB { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Profile Anchors", Order = 4, GroupName = "2. Session Levels")]
        public bool ShowAnchors { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show L2 Liquidity Walls", Order = 1, GroupName = "3. L2 Walls")]
        public bool ShowL2Walls { get; set; }

        [NinjaScriptProperty]
        [Range(10, 5000)]
        [Display(Name = "Wall Min Size (contracts)", Order = 2, GroupName = "3. L2 Walls")]
        public int LiquidityWallMin { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Max Walls Per Side", Order = 3, GroupName = "3. L2 Walls")]
        public int LiquidityMaxPerSide { get; set; }

        [NinjaScriptProperty]
        [Range(10, 600)]
        [Display(Name = "Wall Stale (seconds)", Order = 4, GroupName = "3. L2 Walls")]
        public int LiquidityWallStaleSec { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Score HUD + Tier Badges", Order = 1, GroupName = "4. Scoring")]
        public bool ShowScoreHud { get; set; }

        #endregion
    }
}
