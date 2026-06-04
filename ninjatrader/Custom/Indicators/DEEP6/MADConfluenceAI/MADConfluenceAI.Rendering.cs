// MADConfluenceAI.Rendering.cs — Level-first confluence overlay
// Three layers: level zones, floating confluence chip, bar breadcrumbs
using System;
using System.Collections.Generic;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using NinjaTrader.Gui.Chart;

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public partial class MADConfluenceAI : Indicator
    {
        // ── LEVEL ZONE BRUSHES ───────────────────────────────────────────
        private SolidColorBrush _brushPdh;
        private SolidColorBrush _brushPdl;
        private SolidColorBrush _brushPdMid;
        private SolidColorBrush _brushVwap;
        private SolidColorBrush _brushVwapBand;
        private SolidColorBrush _brushPoc;
        private SolidColorBrush _brushVaLine;
        private SolidColorBrush _brushOrRange;
        private SolidColorBrush _brushSession;
        private SolidColorBrush _brushNakedPoc;
        private SolidColorBrush _brushPwHigh;
        private SolidColorBrush _brushLevelLabel;

        // ── CHIP & BREADCRUMB BRUSHES ────────────────────────────────────
        private SolidColorBrush _brushChipBg;
        private SolidColorBrush _brushChipBorder;
        private SolidColorBrush _brushChipText;
        private SolidColorBrush _brushChipDim;
        private SolidColorBrush _brushTagBg;
        private SolidColorBrush _brushAccentGreen;
        private SolidColorBrush _brushAccentAmber;
        private SolidColorBrush _brushAccentMagenta;
        private SolidColorBrush _brushAccentGray;
        private SolidColorBrush _brushCyan;

        // ── TEXT FORMATS ─────────────────────────────────────────────────
        private TextFormat _fmtLevelLabel;
        private TextFormat _fmtChipTier;
        private TextFormat _fmtChipScore;
        private TextFormat _fmtChipDetail;

        // ── STROKE STYLES ────────────────────────────────────────────────
        private StrokeStyle _dashedStroke;

        // ── RENDER THROTTLE ──────────────────────────────────────────────
        private DateTime _lastRenderTime = DateTime.MinValue;
        private const int RenderThrottleMs = 125;

        // ── RENDERING STATE (set by OnBarUpdate, read by OnRender) ───────
        private MADRegime _currentRegime;

        // ══════════════════════════════════════════════════════════════════
        //  OnRender — 3-LAYER DISPATCH
        // ══════════════════════════════════════════════════════════════════

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (RenderTarget == null || chartControl == null || ChartBars == null) return;

            var now = DateTime.UtcNow;
            if ((now - _lastRenderTime).TotalMilliseconds < RenderThrottleMs) return;
            _lastRenderTime = now;

            if (ShowLevelZones)
                RenderLevelZones(chartControl, chartScale);

            if (ShowSignalMarkers)
                RenderBreadcrumbs(chartControl, chartScale);

            RenderConfluenceChip(chartControl, chartScale);
        }

        // ══════════════════════════════════════════════════════════════════
        //  OnRenderTargetChanged — CREATE BRUSHES + TEXT FORMATS
        // ══════════════════════════════════════════════════════════════════

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            var rt = RenderTarget;
            var dwFactory = NinjaTrader.Core.Globals.DirectWriteFactory;

            // Level brushes
            _brushPdh        = new SolidColorBrush(rt, new Color4(1.0f, 0.2f, 0.2f, 0.30f));
            _brushPdl        = new SolidColorBrush(rt, new Color4(0.2f, 1.0f, 0.2f, 0.30f));
            _brushPdMid      = new SolidColorBrush(rt, new Color4(0.6f, 0.6f, 0.6f, 0.25f));
            _brushVwap       = new SolidColorBrush(rt, new Color4(0.2f, 0.5f, 1.0f, 0.40f));
            _brushVwapBand   = new SolidColorBrush(rt, new Color4(0.2f, 0.5f, 1.0f, 0.20f));
            _brushPoc        = new SolidColorBrush(rt, new Color4(1.0f, 0.82f, 0.25f, 0.50f));
            _brushVaLine     = new SolidColorBrush(rt, new Color4(0.78f, 0.82f, 0.48f, 0.35f));
            _brushOrRange    = new SolidColorBrush(rt, new Color4(0.6f, 0.3f, 0.9f, 0.30f));
            _brushSession    = new SolidColorBrush(rt, new Color4(1.0f, 1.0f, 1.0f, 0.25f));
            _brushNakedPoc   = new SolidColorBrush(rt, new Color4(1.0f, 0.82f, 0.25f, 0.40f));
            _brushPwHigh     = new SolidColorBrush(rt, new Color4(0.0f, 0.7f, 0.7f, 0.30f));
            _brushLevelLabel = new SolidColorBrush(rt, new Color4(1.0f, 1.0f, 1.0f, 0.85f));

            // Chip & breadcrumb brushes
            _brushChipBg        = new SolidColorBrush(rt, new Color4(0.055f, 0.063f, 0.078f, 0.92f));
            _brushChipBorder    = new SolidColorBrush(rt, new Color4(0.149f, 0.149f, 0.200f, 0.70f));
            _brushChipText      = new SolidColorBrush(rt, new Color4(0.949f, 0.957f, 0.973f, 1.0f));
            _brushChipDim       = new SolidColorBrush(rt, new Color4(0.608f, 0.639f, 0.682f, 1.0f));
            _brushTagBg         = new SolidColorBrush(rt, new Color4(0.067f, 0.075f, 0.094f, 0.85f));
            _brushAccentGreen   = new SolidColorBrush(rt, new Color4(0.0f, 0.902f, 0.463f, 1.0f));
            _brushAccentAmber   = new SolidColorBrush(rt, new Color4(1.0f, 0.702f, 0.0f, 1.0f));
            _brushAccentMagenta = new SolidColorBrush(rt, new Color4(1.0f, 0.220f, 0.784f, 1.0f));
            _brushAccentGray    = new SolidColorBrush(rt, new Color4(0.353f, 0.388f, 0.431f, 1.0f));
            _brushCyan          = new SolidColorBrush(rt, new Color4(0.0f, 0.878f, 1.0f, 1.0f));

            // Text formats
            _fmtLevelLabel = new TextFormat(dwFactory, "Consolas", FontWeight.Normal, FontStyle.Normal, FontStretch.Normal, 9f);
            _fmtChipTier   = new TextFormat(dwFactory, "Consolas", FontWeight.Bold, FontStyle.Normal, FontStretch.Normal, 12f);
            _fmtChipScore  = new TextFormat(dwFactory, "Consolas", FontWeight.Bold, FontStyle.Normal, FontStretch.Normal, 16f);
            _fmtChipDetail = new TextFormat(dwFactory, "Consolas", FontWeight.Normal, FontStyle.Normal, FontStretch.Normal, 9f);

            // Stroke style
            _dashedStroke = new StrokeStyle(rt.Factory, new StrokeStyleProperties
            {
                DashStyle = DashStyle.Dash, DashCap = CapStyle.Flat,
                StartCap = CapStyle.Flat, EndCap = CapStyle.Flat
            });
        }

        // ══════════════════════════════════════════════════════════════════
        //  DisposeDx — SAFE DISPOSAL OF ALL GPU RESOURCES
        // ══════════════════════════════════════════════════════════════════

        private void DisposeDx()
        {
            SafeDispose(ref _brushPdh);
            SafeDispose(ref _brushPdl);
            SafeDispose(ref _brushPdMid);
            SafeDispose(ref _brushVwap);
            SafeDispose(ref _brushVwapBand);
            SafeDispose(ref _brushPoc);
            SafeDispose(ref _brushVaLine);
            SafeDispose(ref _brushOrRange);
            SafeDispose(ref _brushSession);
            SafeDispose(ref _brushNakedPoc);
            SafeDispose(ref _brushPwHigh);
            SafeDispose(ref _brushLevelLabel);

            SafeDispose(ref _brushChipBg);
            SafeDispose(ref _brushChipBorder);
            SafeDispose(ref _brushChipText);
            SafeDispose(ref _brushChipDim);
            SafeDispose(ref _brushTagBg);
            SafeDispose(ref _brushAccentGreen);
            SafeDispose(ref _brushAccentAmber);
            SafeDispose(ref _brushAccentMagenta);
            SafeDispose(ref _brushAccentGray);
            SafeDispose(ref _brushCyan);

            SafeDisposeFormat(ref _fmtLevelLabel);
            SafeDisposeFormat(ref _fmtChipTier);
            SafeDisposeFormat(ref _fmtChipScore);
            SafeDisposeFormat(ref _fmtChipDetail);

            if (_dashedStroke != null && !_dashedStroke.IsDisposed)
            { _dashedStroke.Dispose(); _dashedStroke = null; }
        }

        private static void SafeDispose(ref SolidColorBrush brush)
        {
            if (brush != null && !brush.IsDisposed) brush.Dispose();
            brush = null;
        }

        private static void SafeDisposeFormat(ref TextFormat fmt)
        {
            if (fmt != null && !fmt.IsDisposed) fmt.Dispose();
            fmt = null;
        }

        // ══════════════════════════════════════════════════════════════════
        //  LAYER 1: LEVEL ZONES — max 3 zones, 8px band, right-edge tag
        // ══════════════════════════════════════════════════════════════════

        private void RenderLevelZones(ChartControl chartControl, ChartScale chartScale)
        {
            var engine = _levelEngine;
            if (engine == null || engine.Levels == null || engine.Levels.Count == 0) return;
            if (_brushPdh == null || _fmtLevelLabel == null) return;

            int fromIdx = ChartBars.FromIndex;
            int toIdx = ChartBars.ToIndex;
            float x1 = chartControl.GetXByBarIndex(ChartBars, fromIdx);
            float x2 = chartControl.GetXByBarIndex(ChartBars, toIdx);
            float chartRight = (float)(ChartPanel.X + ChartPanel.W);

            double currentPrice = _lastRenderedClose > 0
                ? _lastRenderedClose
                : chartScale.GetValueByY((float)(ChartPanel.H / 2));

            var nearbySource = engine.GetNearbyLevels(currentPrice, 5.0);
            if (nearbySource == null || nearbySource.Count == 0) return;

            // Filter out Psychological, sort by quality, take top 3
            var filtered = new List<MADLevel>();
            foreach (var level in nearbySource)
            {
                if (level != null && level.Type != MADLevelType.Psychological)
                    filtered.Add(level);
            }
            if (filtered.Count == 0) return;

            filtered.Sort((a, b) => b.QualityScore.CompareTo(a.QualityScore));
            int count = Math.Min(3, filtered.Count);

            for (int i = 0; i < count; i++)
            {
                var level = filtered[i];
                float y = chartScale.GetYByValue(level.Price);
                if (y < -50 || y > ChartPanel.H + 50) continue;

                var brush = GetLevelBrush(level.Type);
                if (brush == null || brush.IsDisposed) continue;

                // Zone band: 8px tall (±4px from level price)
                float zoneTop = y - 4f;
                var zoneRect = new RectangleF(x1, zoneTop, x2 - x1, 8f);

                // Fill at half opacity (≈20% effective alpha)
                float savedOp = brush.Opacity;
                brush.Opacity = 0.5f;
                RenderTarget.FillRectangle(zoneRect, brush);

                // Border lines at full opacity, 1.5px solid
                brush.Opacity = savedOp;
                RenderTarget.DrawLine(
                    new Vector2(x1, zoneTop), new Vector2(x2, zoneTop),
                    brush, 1.5f);
                RenderTarget.DrawLine(
                    new Vector2(x1, zoneTop + 8f), new Vector2(x2, zoneTop + 8f),
                    brush, 1.5f);

                // Right-edge tag: 72×18px dark background with label
                float tagW = 72f;
                float tagH = 18f;
                float tagLeft = chartRight - tagW - 4f;
                float tagTop = y - tagH / 2f;
                RenderTarget.FillRectangle(
                    new RectangleF(tagLeft, tagTop, tagW, tagH), _brushTagBg);

                string label = GetLevelLabel(level.Type, level.Price);
                RenderTarget.DrawText(label, _fmtLevelLabel,
                    new RectangleF(tagLeft + 4f, tagTop + 2f, tagW - 8f, tagH - 4f),
                    _brushLevelLabel);
            }
        }

        // ══════════════════════════════════════════════════════════════════
        //  LAYER 2: CONFLUENCE CHIP — 152×52, only when score >= 60
        // ══════════════════════════════════════════════════════════════════

        private void RenderConfluenceChip(ChartControl chartControl, ChartScale chartScale)
        {
            var decision = _decision;
            if (decision == null || decision.Score < 60) return;
            if (_brushChipBg == null || _fmtChipTier == null) return;

            double currentPrice = _lastRenderedClose > 0 ? _lastRenderedClose : 0;
            if (currentPrice <= 0) return;

            // Find nearest non-Psychological level for vertical anchor
            float chipY = chartScale.GetYByValue(currentPrice);
            var engine = _levelEngine;
            if (engine != null)
            {
                var nearby = engine.GetNearbyLevels(currentPrice, 5.0);
                if (nearby != null)
                {
                    double bestDist = double.MaxValue;
                    foreach (var lv in nearby)
                    {
                        if (lv == null || lv.Type == MADLevelType.Psychological) continue;
                        double dist = Math.Abs(lv.Price - currentPrice);
                        if (dist < bestDist)
                        {
                            bestDist = dist;
                            chipY = chartScale.GetYByValue(lv.Price);
                        }
                    }
                }
            }

            // Chip dimensions
            float chipW = 152f;
            float chipH = 52f;
            float chipRight = (float)(ChartPanel.X + ChartPanel.W) - 84f;
            float chipLeft = chipRight - chipW;
            float chipTop = chipY - chipH / 2f;

            // Clamp to visible panel
            float panelH = (float)ChartPanel.H;
            if (chipTop < 2f) chipTop = 2f;
            if (chipTop + chipH > panelH - 2f) chipTop = panelH - chipH - 2f;

            var chipRect = new RectangleF(chipLeft, chipTop, chipW, chipH);
            var accentBrush = GetTierAccentBrush(decision.Tier);

            // Background + accent border
            RenderTarget.FillRectangle(chipRect, _brushChipBg);
            RenderTarget.DrawRectangle(chipRect, accentBrush, 1f);

            float cx = chipLeft + 8f;
            float cy = chipTop + 4f;
            float innerW = chipW - 16f;

            // Row 1: Direction arrow + tier badge (12pt bold)
            string arrow = decision.Action == MADAction.Long ? "\u25B2 "
                         : decision.Action == MADAction.Short ? "\u25BC "
                         : "";
            string tierText = arrow + GetTierText(decision.Tier);
            RenderTarget.DrawText(tierText, _fmtChipTier,
                new RectangleF(cx, cy, innerW, 16f), accentBrush);
            cy += 16f;

            // Row 2: Score (16pt bold, accent-colored)
            string scoreText = string.Format("{0:F0}", decision.Score);
            RenderTarget.DrawText(scoreText, _fmtChipScore,
                new RectangleF(cx, cy, innerW, 20f), accentBrush);
            cy += 18f;

            // Row 3: Top 2 signal codes (9pt dim)
            var scorer = _scorerResult;
            if (scorer != null && scorer.ContributingSignals != null
                && scorer.ContributingSignals.Count > 0)
            {
                int showCount = Math.Min(2, scorer.ContributingSignals.Count);
                string codes = "";
                for (int i = 0; i < showCount; i++)
                {
                    if (i > 0) codes += " + ";
                    codes += scorer.ContributingSignals[i].SignalId;
                }
                RenderTarget.DrawText(codes, _fmtChipDetail,
                    new RectangleF(cx, cy, innerW, 12f), _brushChipDim);
            }

            // DOM availability dot: 4px green at top-right corner
            if (_isDomAvailable && _brushAccentGreen != null && !_brushAccentGreen.IsDisposed)
            {
                var dotCenter = new Vector2(chipLeft + chipW - 8f, chipTop + 8f);
                RenderTarget.FillEllipse(
                    new Ellipse(dotCenter, 2f, 2f), _brushAccentGreen);
            }
        }

        // ══════════════════════════════════════════════════════════════════
        //  LAYER 3: BREADCRUMBS — diamond markers for ELITE/HIGH signals
        // ══════════════════════════════════════════════════════════════════

        private void RenderBreadcrumbs(ChartControl chartControl, ChartScale chartScale)
        {
            var history = _signalHistory;
            if (history == null || history.Count == 0) return;
            if (_brushCyan == null) return;

            int fromIdx = ChartBars.FromIndex;
            int toIdx = ChartBars.ToIndex;
            int rendered = 0;

            // Newest to oldest, max 5 breadcrumbs
            for (int h = history.Count - 1; h >= 0 && rendered < 5; h--)
            {
                var entry = history[h];
                if (entry.Decision == null || entry.Decision.Score < 75) continue;

                int barIdx = entry.BarIndex;
                if (barIdx < fromIdx || barIdx > toIdx) continue;

                int age = toIdx - barIdx;
                if (age > 5) continue;

                // Find strongest directional signal in this entry
                MADSignalResult bestSignal = null;
                foreach (var sig in entry.Signals)
                {
                    if (sig == null || sig.Direction == MADSignalDirection.Neutral) continue;
                    if (bestSignal == null || sig.Strength > bestSignal.Strength)
                        bestSignal = sig;
                }
                if (bestSignal == null) continue;

                float x = chartControl.GetXByBarIndex(ChartBars, barIdx);
                bool isShort = bestSignal.Direction == MADSignalDirection.Short;

                // Position above High (Short) or below Low (Long), offset 6px
                double price = isShort
                    ? Highs[0].GetValueAt(barIdx)
                    : Lows[0].GetValueAt(barIdx);
                float y = chartScale.GetYByValue(price);
                y += isShort ? -6f : 6f;

                // Color by signal category
                var brush = GetBreadcrumbBrush(bestSignal.SignalId);

                // Alpha fading: 1.0 at age 0, 0.4 at age 5
                float alpha = 1.0f - (age * 0.12f);
                if (alpha < 0.4f) alpha = 0.4f;

                float savedOp = brush.Opacity;
                brush.Opacity = alpha;
                DrawDiamond(x, y, 5f, brush);
                brush.Opacity = savedOp;

                rendered++;
            }
        }

        // ── Diamond shape (10px rotated square) ──────────────────────────

        private void DrawDiamond(float cx, float cy, float halfSize, SolidColorBrush brush)
        {
            if (brush == null || brush.IsDisposed) return;
            using (var geo = new PathGeometry(RenderTarget.Factory))
            {
                using (var sink = geo.Open())
                {
                    sink.BeginFigure(new Vector2(cx, cy - halfSize), FigureBegin.Filled);
                    sink.AddLine(new Vector2(cx + halfSize, cy));
                    sink.AddLine(new Vector2(cx, cy + halfSize));
                    sink.AddLine(new Vector2(cx - halfSize, cy));
                    sink.EndFigure(FigureEnd.Closed);
                    sink.Close();
                }
                RenderTarget.FillGeometry(geo, brush);
            }
        }

        // ══════════════════════════════════════════════════════════════════
        //  HELPERS
        // ══════════════════════════════════════════════════════════════════

        private SolidColorBrush GetLevelBrush(MADLevelType type)
        {
            switch (type)
            {
                case MADLevelType.PrevDayHigh:      return _brushPdh;
                case MADLevelType.PrevDayLow:       return _brushPdl;
                case MADLevelType.PrevDayMid:       return _brushPdMid;
                case MADLevelType.PrevWeekHigh:
                case MADLevelType.PrevWeekLow:      return _brushPwHigh;
                case MADLevelType.VwapLine:          return _brushVwap;
                case MADLevelType.Vwap1SigmaUp:
                case MADLevelType.Vwap1SigmaDown:
                case MADLevelType.Vwap2SigmaUp:
                case MADLevelType.Vwap2SigmaDown:
                case MADLevelType.Vwap3SigmaUp:
                case MADLevelType.Vwap3SigmaDown:   return _brushVwapBand;
                case MADLevelType.SessionPoc:        return _brushPoc;
                case MADLevelType.SessionVah:
                case MADLevelType.SessionVal:        return _brushVaLine;
                case MADLevelType.OpeningRangeHigh:
                case MADLevelType.OpeningRangeLow:   return _brushOrRange;
                case MADLevelType.SessionHigh:
                case MADLevelType.SessionLow:        return _brushSession;
                case MADLevelType.NakedPoc:          return _brushNakedPoc;
                default:                             return _brushSession;
            }
        }

        private static string GetLevelLabel(MADLevelType type, double price)
        {
            string prefix;
            switch (type)
            {
                case MADLevelType.PrevDayHigh:      prefix = "PDH"; break;
                case MADLevelType.PrevDayLow:       prefix = "PDL"; break;
                case MADLevelType.PrevDayMid:       prefix = "PDM"; break;
                case MADLevelType.PrevWeekHigh:     prefix = "PWH"; break;
                case MADLevelType.PrevWeekLow:      prefix = "PWL"; break;
                case MADLevelType.VwapLine:         prefix = "VWAP"; break;
                case MADLevelType.Vwap1SigmaUp:     prefix = "V+1s"; break;
                case MADLevelType.Vwap1SigmaDown:   prefix = "V-1s"; break;
                case MADLevelType.Vwap2SigmaUp:     prefix = "V+2s"; break;
                case MADLevelType.Vwap2SigmaDown:   prefix = "V-2s"; break;
                case MADLevelType.Vwap3SigmaUp:     prefix = "V+3s"; break;
                case MADLevelType.Vwap3SigmaDown:   prefix = "V-3s"; break;
                case MADLevelType.SessionPoc:       prefix = "POC"; break;
                case MADLevelType.SessionVah:       prefix = "VAH"; break;
                case MADLevelType.SessionVal:       prefix = "VAL"; break;
                case MADLevelType.OpeningRangeHigh: prefix = "ORH"; break;
                case MADLevelType.OpeningRangeLow:  prefix = "ORL"; break;
                case MADLevelType.SessionHigh:      prefix = "HOD"; break;
                case MADLevelType.SessionLow:       prefix = "LOD"; break;
                case MADLevelType.NakedPoc:         prefix = "nPOC"; break;
                default:                            prefix = "LVL"; break;
            }
            return string.Format("{0} {1:F2}", prefix, price);
        }

        private SolidColorBrush GetTierAccentBrush(MADTier tier)
        {
            switch (tier)
            {
                case MADTier.Elite:      return _brushAccentGreen;
                case MADTier.High:       return _brushAccentAmber;
                case MADTier.Moderate:   return _brushAccentMagenta;
                case MADTier.Wait:       return _brushChipDim;
                case MADTier.DoNotTrade: return _brushAccentGray;
                default:                 return _brushChipDim;
            }
        }

        private static string GetTierText(MADTier tier)
        {
            switch (tier)
            {
                case MADTier.Elite:      return "ELITE";
                case MADTier.High:       return "HIGH";
                case MADTier.Moderate:   return "MOD";
                case MADTier.Wait:       return "WATCH";
                case MADTier.DoNotTrade: return "DNT";
                default:                 return "---";
            }
        }

        private SolidColorBrush GetBreadcrumbBrush(string signalId)
        {
            if (signalId == null) return _brushAccentAmber;
            if (signalId.StartsWith("ABS")) return _brushCyan;
            if (signalId.StartsWith("EXH")) return _brushAccentMagenta;
            if (signalId.StartsWith("DELT")) return _brushAccentGreen;
            return _brushAccentAmber;
        }
    }
}
