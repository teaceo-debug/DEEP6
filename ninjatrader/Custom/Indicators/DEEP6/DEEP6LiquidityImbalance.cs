// DEEP6 Liquidity Imbalance — NinjaTrader 8 sub-panel indicator.
// Option 1: PURE COLOR + ONE BIG WORD
//
// Sub-panel: entire direction row fills with state color. One word centered at 32pt Bold.
//   BUY  (#00E676 green)   — Trespass Long (high conviction)
//   BUY  (#00BFA5 teal)    — Counter Buy (wall pulled)
//   SELL (#FF1744 red)     — Trespass Short
//   SELL (#FF4081 pink)    — Counter Sell
//   WAIT (#1A2A1E/cyan)    — Watching Long (building)
//   WAIT (#2A1A1E/coral)   — Watching Short
//   STOP (#FFD23F yellow)  — Spoof Alert (stand aside)
//   ...  (no fill, dim)    — Wait
//   OFF  (no fill, dim)    — DOM Offline
//
// Price chart signals:
//   ArrowUp   + "BUY"  (#00E676) — Trespass Long
//   ArrowDown + "SELL" (#FF1744) — Trespass Short
//   Diamond   + "BUY"  (#00BFA5) — Counter Buy
//   Diamond   + "SELL" (#FF4081) — Counter Sell
//
// Deploy to:
//   %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\DEEP6LiquidityImbalance.cs

#region Using
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = System.Windows.Media.Brush;
using Color = System.Windows.Media.Color;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6LiquidityImbalance : Indicator
    {
        // ─────────────────────────────────────────────────────────────────
        //  Constants
        // ─────────────────────────────────────────────────────────────────
        private const int    DomMaxLevels  = 40;
        private const int    LobBayesDepth = 5;
        private const double KalmanQ       = 0.01;
        private const double KalmanR       = 0.1;

        private const int S_WAIT        = 0;
        private const int S_WATCH_LONG  = 1;
        private const int S_WATCH_SHORT = 2;
        private const int S_SPOOF       = 3;
        private const int S_CSP_BULL    = 4;
        private const int S_CSP_BEAR    = 5;
        private const int S_TRSP_LONG   = 6;
        private const int S_TRSP_SHORT  = 7;

        // ─────────────────────────────────────────────────────────────────
        //  DOM state
        // ─────────────────────────────────────────────────────────────────
        private readonly double[] _bidSize    = new double[DomMaxLevels];
        private readonly double[] _askSize    = new double[DomMaxLevels];
        private readonly double[] _bidPrice   = new double[DomMaxLevels];
        private readonly double[] _askPrice   = new double[DomMaxLevels];
        private readonly double[] _prevBidSize = new double[DomMaxLevels];
        private readonly double[] _prevAskSize = new double[DomMaxLevels];
        private bool _prevDomCaptured;

        // ─────────────────────────────────────────────────────────────────
        //  Intrabar accumulators
        // ─────────────────────────────────────────────────────────────────
        private double _bidAdded, _askAdded, _bidCancelled, _askCancelled;
        private double _barBidTrades, _barAskTrades, _bestBid, _bestAsk;

        // ─────────────────────────────────────────────────────────────────
        //  Rolling spoof history
        // ─────────────────────────────────────────────────────────────────
        private double[] _hqHistory, _uqHistory, _acHistory;
        private double[] _leHistory, _toqHistory, _cotHistory;
        private int _histIdx, _histCount;

        // ─────────────────────────────────────────────────────────────────
        //  Kalman filter
        // ─────────────────────────────────────────────────────────────────
        private double _kalmanX = 0.5;
        private double _kalmanP = 1.0;

        // ─────────────────────────────────────────────────────────────────
        //  Cached values (read by OnRender)
        // ─────────────────────────────────────────────────────────────────
        private double _lastImbalanceRatio;
        private double _lastMpLong;
        private double _lastMpShort;
        private double _lastSpoofScore;
        private double _liveDomBid;
        private double _liveDomAsk;
        private bool   _lastCspBull;
        private bool   _lastCspBear;

        // ─────────────────────────────────────────────────────────────────
        //  WPF signal marker brushes (price panel)
        // ─────────────────────────────────────────────────────────────────
        private SolidColorBrush _wBull;    // #00E676
        private SolidColorBrush _wBear;    // #FF1744
        private SolidColorBrush _wCspBull; // #00BFA5
        private SolidColorBrush _wCspBear; // #FF4081

        // ─────────────────────────────────────────────────────────────────
        //  SharpDX resources — direction row fills (alpha baked in)
        // ─────────────────────────────────────────────────────────────────
        private SharpDX.Direct2D1.SolidColorBrush _dxFillTrspLong;    // #00E676 @ 70%
        private SharpDX.Direct2D1.SolidColorBrush _dxFillTrspShort;   // #FF1744 @ 70%
        private SharpDX.Direct2D1.SolidColorBrush _dxFillCspBull;     // #00BFA5 @ 60%
        private SharpDX.Direct2D1.SolidColorBrush _dxFillCspBear;     // #FF4081 @ 60%
        private SharpDX.Direct2D1.SolidColorBrush _dxFillWatchLong;   // #1A2A1E solid dark green
        private SharpDX.Direct2D1.SolidColorBrush _dxFillWatchShort;  // #2A1A1E solid dark red
        private SharpDX.Direct2D1.SolidColorBrush _dxFillSpoof;       // #FFD23F @ 50%

        // ─────────────────────────────────────────────────────────────────
        //  SharpDX resources — word text brushes
        // ─────────────────────────────────────────────────────────────────
        private SharpDX.Direct2D1.SolidColorBrush _dxWordTrspLong;    // #0A1F12
        private SharpDX.Direct2D1.SolidColorBrush _dxWordTrspShort;   // #1F0A0D
        private SharpDX.Direct2D1.SolidColorBrush _dxWordCspBull;     // #071A17
        private SharpDX.Direct2D1.SolidColorBrush _dxWordCspBear;     // #1F071A
        private SharpDX.Direct2D1.SolidColorBrush _dxWordSpoof;       // #1F1A07
        private SharpDX.Direct2D1.SolidColorBrush _dxWordWatchLong;   // #4FC3F7 cyan
        private SharpDX.Direct2D1.SolidColorBrush _dxWordWatchShort;  // #FF6B6B coral
        private SharpDX.Direct2D1.SolidColorBrush _dxWordDim;         // #3D4450

        // ─────────────────────────────────────────────────────────────────
        //  SharpDX resources — structure / evidence
        // ─────────────────────────────────────────────────────────────────
        private SharpDX.Direct2D1.SolidColorBrush _dxBg;
        private SharpDX.Direct2D1.SolidColorBrush _dxTrack;
        private SharpDX.Direct2D1.SolidColorBrush _dxTrspLong;   // evidence bar fill (green)
        private SharpDX.Direct2D1.SolidColorBrush _dxTrspShort;  // evidence bar fill (red)
        private SharpDX.Direct2D1.SolidColorBrush _dxProb;       // CONF bar teal
        private SharpDX.Direct2D1.SolidColorBrush _dxSpoofSafe;  // SPOOF bar green
        private SharpDX.Direct2D1.SolidColorBrush _dxSpoof;      // SPOOF bar pink
        private SharpDX.Direct2D1.SolidColorBrush _dxSep;
        private SharpDX.Direct2D1.SolidColorBrush _dxTextDim;
        private SharpDX.Direct2D1.SolidColorBrush _dxDomOn;
        private SharpDX.Direct2D1.SolidColorBrush _dxDomOff;
        private SharpDX.Direct2D1.SolidColorBrush _dxTick;

        private SharpDX.DirectWrite.TextFormat _fmtHdr;     // 8.5pt header
        private SharpDX.DirectWrite.TextFormat _fmtBigWord; // 32pt Bold Consolas
        private SharpDX.DirectWrite.TextFormat _fmtCol;     // 8.5pt evidence labels

        // ─────────────────────────────────────────────────────────────────
        //  OnStateChange
        // ─────────────────────────────────────────────────────────────────
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description              = "Liquidity Imbalance: BUY / SELL / WAIT / STOP at a glance. Color = action.";
                Name                     = "DEEP6 Liquidity Imbalance";
                Calculate                = Calculate.OnEachTick;
                IsOverlay                = false;
                DrawOnPricePanel         = true;
                PaintPriceMarkers        = false;
                IsSuspendedWhileInactive = true;
                ScaleJustification       = ScaleJustification.Right;

                LobDepthLevels     = 10;
                ImbalanceThreshold = 0.30;
                MpMinConfidence    = 0.80;
                MaxSpoofScore      = 0.20;
                W1Threshold        = 0.25;
                SpoofRollingBars   = 20;
                BayesianPrior      = 0.5;

                var hide = MakeFrozenBrush(Color.FromRgb(0x0E, 0x10, 0x14));
                AddPlot(new Stroke(hide, 1), PlotStyle.Bar,  "ImbalanceRatio");
                AddPlot(new Stroke(hide, 1), PlotStyle.Line, "MicroProbLong");
                AddPlot(new Stroke(hide, 1), PlotStyle.Line, "MicroProbShort");
                AddPlot(new Stroke(hide, 1), PlotStyle.Line, "SpoofScore");
            }
            else if (State == State.DataLoaded)
            {
                int cap = System.Math.Max(SpoofRollingBars, 1);
                _hqHistory  = new double[cap]; _uqHistory  = new double[cap];
                _acHistory  = new double[cap]; _leHistory  = new double[cap];
                _toqHistory = new double[cap]; _cotHistory = new double[cap];
                _histIdx = 0; _histCount = 0;
                _kalmanX = 0.5; _kalmanP = 1.0;
                _bestBid = 0; _bestAsk = 0;
                _prevDomCaptured = false;
                _liveDomBid = 0; _liveDomAsk = 0;
                _lastCspBull = false; _lastCspBear = false;

                _wBull    = MakeFrozenBrush(Color.FromRgb(0x00, 0xE6, 0x76));
                _wBear    = MakeFrozenBrush(Color.FromRgb(0xFF, 0x17, 0x44));
                _wCspBull = MakeFrozenBrush(Color.FromRgb(0x00, 0xBF, 0xA5));
                _wCspBear = MakeFrozenBrush(Color.FromRgb(0xFF, 0x40, 0x81));
            }
            else if (State == State.Terminated)
            {
                DisposeDx();
            }
        }

        // ─────────────────────────────────────────────────────────────────
        //  SharpDX lifecycle
        // ─────────────────────────────────────────────────────────────────
        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;
            var rt  = RenderTarget;
            var dwf = NinjaTrader.Core.Globals.DirectWriteFactory;

            // Direction row fills (alpha baked into Color4)
            _dxFillTrspLong   = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.000f, 0.902f, 0.463f, 0.70f)); // #00E676 @70%
            _dxFillTrspShort  = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(1.000f, 0.090f, 0.267f, 0.70f)); // #FF1744 @70%
            _dxFillCspBull    = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.000f, 0.749f, 0.647f, 0.60f)); // #00BFA5 @60%
            _dxFillCspBear    = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(1.000f, 0.251f, 0.506f, 0.60f)); // #FF4081 @60%
            _dxFillWatchLong  = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.102f, 0.165f, 0.118f, 1.00f)); // #1A2A1E solid
            _dxFillWatchShort = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.165f, 0.102f, 0.118f, 1.00f)); // #2A1A1E solid
            _dxFillSpoof      = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(1.000f, 0.824f, 0.247f, 0.50f)); // #FFD23F @50%

            // Word text brushes (dark on colored fill, or colored on dark bg)
            _dxWordTrspLong   = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.039f, 0.122f, 0.071f, 1.00f)); // #0A1F12
            _dxWordTrspShort  = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.122f, 0.039f, 0.051f, 1.00f)); // #1F0A0D
            _dxWordCspBull    = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.027f, 0.102f, 0.090f, 1.00f)); // #071A17
            _dxWordCspBear    = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.122f, 0.027f, 0.102f, 1.00f)); // #1F071A
            _dxWordSpoof      = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.122f, 0.102f, 0.027f, 1.00f)); // #1F1A07
            _dxWordWatchLong  = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.310f, 0.765f, 0.969f, 1.00f)); // #4FC3F7 cyan
            _dxWordWatchShort = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(1.000f, 0.420f, 0.420f, 1.00f)); // #FF6B6B coral
            _dxWordDim        = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.239f, 0.267f, 0.314f, 1.00f)); // #3D4450

            // Structure brushes
            _dxBg        = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.055f, 0.063f, 0.078f, 1.00f)); // #0E1014
            _dxTrack     = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.165f, 0.188f, 0.231f, 1.00f)); // #2A303B
            _dxTrspLong  = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.000f, 0.902f, 0.463f, 0.90f)); // #00E676
            _dxTrspShort = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(1.000f, 0.090f, 0.267f, 0.90f)); // #FF1744
            _dxProb      = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.000f, 0.749f, 0.647f, 0.90f)); // #00BFA5
            _dxSpoofSafe = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.000f, 0.906f, 0.463f, 0.85f)); // #00E776
            _dxSpoof     = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(1.000f, 0.251f, 0.506f, 0.90f)); // #FF4081
            _dxSep       = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.784f, 0.784f, 0.784f, 0.10f));
            _dxTextDim   = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.420f, 0.447f, 0.502f, 1.00f));
            _dxDomOn     = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.000f, 0.906f, 0.463f, 1.00f));
            _dxDomOff    = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(1.000f, 0.420f, 0.420f, 1.00f));
            _dxTick      = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(1.000f, 0.824f, 0.247f, 0.70f));

            _fmtHdr     = new SharpDX.DirectWrite.TextFormat(dwf, "Segoe UI", 8.5f);
            _fmtBigWord = new SharpDX.DirectWrite.TextFormat(dwf, "Consolas",
                null, FontWeight.Bold, FontStyle.Normal, FontStretch.Normal, 32.0f, "");
            _fmtCol     = new SharpDX.DirectWrite.TextFormat(dwf, "Consolas", 8.5f);
        }

        private void DisposeDx()
        {
            _dxFillTrspLong?.Dispose();   _dxFillTrspLong   = null;
            _dxFillTrspShort?.Dispose();  _dxFillTrspShort  = null;
            _dxFillCspBull?.Dispose();    _dxFillCspBull    = null;
            _dxFillCspBear?.Dispose();    _dxFillCspBear    = null;
            _dxFillWatchLong?.Dispose();  _dxFillWatchLong  = null;
            _dxFillWatchShort?.Dispose(); _dxFillWatchShort = null;
            _dxFillSpoof?.Dispose();      _dxFillSpoof      = null;
            _dxWordTrspLong?.Dispose();   _dxWordTrspLong   = null;
            _dxWordTrspShort?.Dispose();  _dxWordTrspShort  = null;
            _dxWordCspBull?.Dispose();    _dxWordCspBull    = null;
            _dxWordCspBear?.Dispose();    _dxWordCspBear    = null;
            _dxWordSpoof?.Dispose();      _dxWordSpoof      = null;
            _dxWordWatchLong?.Dispose();  _dxWordWatchLong  = null;
            _dxWordWatchShort?.Dispose(); _dxWordWatchShort = null;
            _dxWordDim?.Dispose();        _dxWordDim        = null;
            _dxBg?.Dispose();             _dxBg             = null;
            _dxTrack?.Dispose();          _dxTrack          = null;
            _dxTrspLong?.Dispose();       _dxTrspLong       = null;
            _dxTrspShort?.Dispose();      _dxTrspShort      = null;
            _dxProb?.Dispose();           _dxProb           = null;
            _dxSpoofSafe?.Dispose();      _dxSpoofSafe      = null;
            _dxSpoof?.Dispose();          _dxSpoof          = null;
            _dxSep?.Dispose();            _dxSep            = null;
            _dxTextDim?.Dispose();        _dxTextDim        = null;
            _dxDomOn?.Dispose();          _dxDomOn          = null;
            _dxDomOff?.Dispose();         _dxDomOff         = null;
            _dxTick?.Dispose();           _dxTick           = null;
            _fmtHdr?.Dispose();           _fmtHdr           = null;
            _fmtBigWord?.Dispose();       _fmtBigWord       = null;
            _fmtCol?.Dispose();           _fmtCol           = null;
        }

        // ─────────────────────────────────────────────────────────────────
        //  OnRender — Option 1: Pure color + one big word
        // ─────────────────────────────────────────────────────────────────
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (RenderTarget == null || _dxBg == null || _fmtBigWord == null) return;

            float px = (float)chartControl.CanvasLeft;
            float py = (float)chartScale.GetYByValue(chartScale.MaxValue);
            float pw = (float)(chartControl.CanvasRight - chartControl.CanvasLeft);
            float ph = (float)(chartScale.GetYByValue(chartScale.MinValue) - py);
            if (pw < 20f || ph < 24f) return;

            RenderTarget.FillRectangle(new RectangleF(px, py, pw, ph), _dxBg);

            // ── Row geometry ───────────────────────────────────────────
            const float HDR_H = 18f;
            const float COL_H = 26f;
            float dirY = py + HDR_H;
            float dirH = ph - HDR_H - COL_H;
            if (dirH < 8f) dirH = 8f;

            // ── Header ─────────────────────────────────────────────────
            bool   domOn  = (_liveDomBid + _liveDomAsk) > 0;
            string domTxt = domOn
                ? string.Format("DOM  {0:N0} / {1:N0}", _liveDomBid, _liveDomAsk)
                : "DOM OFFLINE";
            DxLine(px + 6f,         py + 1f, pw * 0.46f - 6f, HDR_H, "LIQ IMB", _fmtHdr, _dxTextDim, TextAlignment.Leading);
            DxLine(px + pw * 0.46f, py + 1f, pw * 0.52f,      HDR_H, domTxt,    _fmtHdr, domOn ? _dxDomOn : _dxDomOff, TextAlignment.Trailing);
            RenderTarget.DrawLine(new SharpDX.Vector2(px, py + HDR_H), new SharpDX.Vector2(px + pw, py + HDR_H), _dxSep, 1f);

            // ── Resolve state ──────────────────────────────────────────
            float imb  = (float)_lastImbalanceRatio;
            float mp   = (float)_lastMpLong;
            float spf  = (float)_lastSpoofScore;
            float thr  = (float)(ImbalanceThreshold * 100f);
            float mpTh = (float)(MpMinConfidence    * 100f);
            float spTh = (float)(MaxSpoofScore      * 100f);
            bool  off  = !domOn;

            int state = S_WAIT;
            if (!off)
            {
                if      (imb >  thr && mp > mpTh && spf < spTh)                state = S_TRSP_LONG;
                else if (imb < -thr && (100f - mp) > mpTh && spf < spTh)       state = S_TRSP_SHORT;
                else if (_lastCspBull)                                           state = S_CSP_BULL;
                else if (_lastCspBear)                                           state = S_CSP_BEAR;
                else if (spf >= spTh)                                            state = S_SPOOF;
                else if (imb >  thr * 0.5f)                                     state = S_WATCH_LONG;
                else if (imb < -thr * 0.5f)                                     state = S_WATCH_SHORT;
            }

            // ── State → fill + word ────────────────────────────────────
            SharpDX.Direct2D1.SolidColorBrush fillBr, wordBr;
            string word;
            bool   hasFill;

            switch (state)
            {
                case S_TRSP_LONG:
                    fillBr = _dxFillTrspLong;  wordBr = _dxWordTrspLong;  word = "BUY";  hasFill = true;  break;
                case S_TRSP_SHORT:
                    fillBr = _dxFillTrspShort; wordBr = _dxWordTrspShort; word = "SELL"; hasFill = true;  break;
                case S_CSP_BULL:
                    fillBr = _dxFillCspBull;   wordBr = _dxWordCspBull;   word = "BUY";  hasFill = true;  break;
                case S_CSP_BEAR:
                    fillBr = _dxFillCspBear;   wordBr = _dxWordCspBear;   word = "SELL"; hasFill = true;  break;
                case S_WATCH_LONG:
                    fillBr = _dxFillWatchLong; wordBr = _dxWordWatchLong; word = "WAIT"; hasFill = true;  break;
                case S_WATCH_SHORT:
                    fillBr = _dxFillWatchShort;wordBr = _dxWordWatchShort;word = "WAIT"; hasFill = true;  break;
                case S_SPOOF:
                    fillBr = _dxFillSpoof;     wordBr = _dxWordSpoof;     word = "STOP"; hasFill = true;  break;
                default:
                    fillBr = null; wordBr = _dxWordDim;
                    word   = off ? "OFF" : "...";
                    hasFill = false; break;
            }

            // ── Direction row: fill + word ─────────────────────────────
            if (hasFill)
                RenderTarget.FillRectangle(new RectangleF(px, dirY, pw, dirH), fillBr);

            DxLine(px, dirY, pw, dirH, word, _fmtBigWord, wordBr, TextAlignment.Center);

            RenderTarget.DrawLine(new SharpDX.Vector2(px, dirY + dirH), new SharpDX.Vector2(px + pw, dirY + dirH), _dxSep, 1f);

            // ── Evidence row: 3 columns ────────────────────────────────
            float colY = dirY + dirH;
            float colW = pw / 3f;
            float barH = System.Math.Max(COL_H * 0.35f, 5f);
            float lblH = COL_H - barH;
            float bPad = 5f;

            RenderTarget.DrawLine(new SharpDX.Vector2(px + colW,      colY), new SharpDX.Vector2(px + colW,      colY + COL_H), _dxSep, 1f);
            RenderTarget.DrawLine(new SharpDX.Vector2(px + colW * 2f, colY), new SharpDX.Vector2(px + colW * 2f, colY + COL_H), _dxSep, 1f);

            // Col 0: IMB bidirectional
            float c0x = px + bPad, c0w = colW - bPad * 2f, by0 = colY + lblH;
            RenderTarget.FillRectangle(new RectangleF(c0x, by0, c0w, barH), _dxTrack);
            float ctrX    = c0x + c0w * 0.5f;
            float imbFill = Clamp01f(System.Math.Abs(imb) / 100f) * c0w * 0.5f;
            var   imbBr   = imb >= 0 ? _dxTrspLong : _dxTrspShort;
            if (imbFill > 0)
                RenderTarget.FillRectangle(new RectangleF(imb >= 0 ? ctrX : ctrX - imbFill, by0, imbFill, barH), imbBr);
            RenderTarget.DrawLine(new SharpDX.Vector2(ctrX, by0), new SharpDX.Vector2(ctrX, by0 + barH), _dxSep, 1f);
            float ithX  = c0x + c0w * (0.5f + (float)ImbalanceThreshold * 0.5f);
            float ithXn = c0x + c0w * (0.5f - (float)ImbalanceThreshold * 0.5f);
            RenderTarget.DrawLine(new SharpDX.Vector2(ithX,  by0), new SharpDX.Vector2(ithX,  by0 + barH), _dxTick, 1f);
            RenderTarget.DrawLine(new SharpDX.Vector2(ithXn, by0), new SharpDX.Vector2(ithXn, by0 + barH), _dxTick, 1f);
            DxLine(c0x, colY, c0w, lblH,
                off ? "IMB  --" : string.Format("IMB  {0:+0;-0; 0}%", (int)imb),
                _fmtCol,
                off ? _dxTextDim : (imb >= 0 ? _dxTrspLong : (System.Math.Abs(imb) < 1f ? _dxTextDim : _dxTrspShort)),
                TextAlignment.Center);

            // Col 1: CONF
            float c1x = px + colW + bPad, c1w = colW - bPad * 2f, by1 = colY + lblH;
            RenderTarget.FillRectangle(new RectangleF(c1x, by1, c1w, barH), _dxTrack);
            RenderTarget.FillRectangle(new RectangleF(c1x, by1, Clamp01f(mp / 100f) * c1w, barH), _dxProb);
            float mpThX = c1x + (float)MpMinConfidence * c1w;
            RenderTarget.DrawLine(new SharpDX.Vector2(mpThX, by1), new SharpDX.Vector2(mpThX, by1 + barH), _dxTick, 1f);
            DxLine(c1x, colY, c1w, lblH,
                off ? "CONF  --" : string.Format("CONF  {0:0}%", (int)mp),
                _fmtCol, off ? _dxTextDim : (mp >= mpTh ? _dxProb : _dxTextDim), TextAlignment.Center);

            // Col 2: SPOOF
            float c2x = px + colW * 2f + bPad, c2w = colW - bPad * 2f, by2 = colY + lblH;
            bool  clean  = spf < spTh;
            var   spBr   = clean ? _dxSpoofSafe : _dxSpoof;
            RenderTarget.FillRectangle(new RectangleF(c2x, by2, c2w, barH), _dxTrack);
            RenderTarget.FillRectangle(new RectangleF(c2x, by2, Clamp01f(spf / 100f) * c2w, barH), spBr);
            float spThX = c2x + (float)MaxSpoofScore * c2w;
            RenderTarget.DrawLine(new SharpDX.Vector2(spThX, by2), new SharpDX.Vector2(spThX, by2 + barH), _dxTick, 1f);
            DxLine(c2x, colY, c2w, lblH,
                off ? "SPOOF  --" : string.Format("SPOOF  {0:0}%  {1}", (int)spf, clean ? "OK" : "!!"),
                _fmtCol, off ? _dxTextDim : spBr, TextAlignment.Center);
        }

        private void DxLine(float x, float y, float w, float h, string text,
            SharpDX.DirectWrite.TextFormat fmt,
            SharpDX.Direct2D1.SolidColorBrush brush,
            TextAlignment align)
        {
            if (w <= 2f || h <= 2f) return;
            using (var layout = new SharpDX.DirectWrite.TextLayout(
                NinjaTrader.Core.Globals.DirectWriteFactory, text, fmt, w, h))
            {
                layout.TextAlignment      = align;
                layout.ParagraphAlignment = ParagraphAlignment.Center;
                RenderTarget.DrawTextLayout(new SharpDX.Vector2(x, y), layout, brush);
            }
        }

        private static float Clamp01f(float v) => v < 0f ? 0f : v > 1f ? 1f : v;

        // ─────────────────────────────────────────────────────────────────
        //  OnMarketDepth
        // ─────────────────────────────────────────────────────────────────
        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (e.Position >= DomMaxLevels) return;
            int pos = e.Position; double vol = e.Volume;

            if (e.MarketDataType == MarketDataType.Bid)
            {
                switch (e.Operation)
                {
                    case Operation.Add:
                        _bidSize[pos] = vol; _bidPrice[pos] = e.Price; _bidAdded += vol; break;
                    case Operation.Update:
                        double pb = _bidSize[pos]; _bidSize[pos] = vol; _bidPrice[pos] = e.Price;
                        if (vol > pb) _bidAdded += (vol - pb); else _bidCancelled += (pb - vol); break;
                    case Operation.Remove:
                        _bidCancelled += _bidSize[pos]; _bidSize[pos] = 0; _bidPrice[pos] = 0; break;
                }
                if (pos == 0) _bestBid = _bidPrice[0];
            }
            else if (e.MarketDataType == MarketDataType.Ask)
            {
                switch (e.Operation)
                {
                    case Operation.Add:
                        _askSize[pos] = vol; _askPrice[pos] = e.Price; _askAdded += vol; break;
                    case Operation.Update:
                        double pa = _askSize[pos]; _askSize[pos] = vol; _askPrice[pos] = e.Price;
                        if (vol > pa) _askAdded += (vol - pa); else _askCancelled += (pa - vol); break;
                    case Operation.Remove:
                        _askCancelled += _askSize[pos]; _askSize[pos] = 0; _askPrice[pos] = 0; break;
                }
                if (pos == 0) _bestAsk = _askPrice[0];
            }
        }

        // ─────────────────────────────────────────────────────────────────
        //  OnMarketData
        // ─────────────────────────────────────────────────────────────────
        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (e.MarketDataType != MarketDataType.Last) return;
            if (_bestAsk > 0 && System.Math.Abs(e.Price - _bestAsk) < 0.001) _barAskTrades += e.Volume;
            else if (_bestBid > 0 && System.Math.Abs(e.Price - _bestBid) < 0.001) _barBidTrades += e.Volume;
        }

        // ─────────────────────────────────────────────────────────────────
        //  OnBarUpdate
        // ─────────────────────────────────────────────────────────────────
        protected override void OnBarUpdate()
        {
            if (CurrentBar < 1) return;

            if (IsFirstTickOfBar)
            {
                double totalBid  = DomTotal(_bidSize, 0, DomMaxLevels);
                double totalAsk  = DomTotal(_askSize, 0, DomMaxLevels);
                double totalBoth = totalBid + totalAsk;
                _liveDomBid = totalBid;
                _liveDomAsk = totalAsk;

                // Spoof components
                double hq = 0, uq = 0, ac = 0, le = 0;
                if (_bidAdded + _askAdded > 0)
                    hq = System.Math.Abs(_askAdded - _bidAdded) / (_askAdded + _bidAdded);
                if (totalBoth > 50)  // guard: require min DOM depth
                    uq = System.Math.Abs(totalBid - totalAsk) / totalBoth;
                if (totalBoth > 0)
                    ac = System.Math.Abs(_askCancelled - _bidCancelled) / totalBoth;
                double bidL25 = DomTotal(_bidSize, 1, 5);
                double askL25 = DomTotal(_askSize, 1, 5);
                if (totalBoth > 0)
                    le = System.Math.Abs(askL25 - bidL25) / totalBoth;

                double askImb = (totalBoth > 0) ? (totalAsk - totalBid) / totalBoth : 0;
                int toq = ((askImb > 0.10 && _barBidTrades > _barAskTrades) ||
                           (-askImb > 0.10 && _barAskTrades > _barBidTrades)) ? 1 : 0;
                int cot = 0;
                if (Bars != null && CurrentBar >= 1)
                {
                    double ret = Close[0] - Open[0];
                    double caF = (totalBoth > 0) ? _askCancelled / totalBoth : 0;
                    double cbF = (totalBoth > 0) ? _bidCancelled / totalBoth : 0;
                    if ((caF > 0.10 && ret > 0) || (cbF > 0.10 && ret < 0)) cot = 1;
                }

                int cap = _hqHistory.Length;
                _hqHistory [_histIdx] = hq;  _uqHistory [_histIdx] = uq;
                _acHistory [_histIdx] = ac;  _leHistory [_histIdx] = le;
                _toqHistory[_histIdx] = toq; _cotHistory[_histIdx] = cot;
                _histIdx   = (_histIdx + 1) % cap;
                _histCount = System.Math.Min(_histCount + 1, cap);

                // Require 3+ bars before trusting rolling-max (prevents 100% on cold start)
                double spoofRaw = (_histCount >= 3)
                    ? Clamp01(0.20 * RollingMax(_hqHistory,  _histCount) +
                              0.20 * RollingMax(_uqHistory,  _histCount) +
                              0.15 * RollingMax(_acHistory,  _histCount) +
                              0.15 * RollingMax(_leHistory,  _histCount) +
                              0.15 * RollingMax(_toqHistory, _histCount) +
                              0.15 * RollingMax(_cotHistory, _histCount))
                    : 0.0;

                int    depth = System.Math.Min(LobDepthLevels, DomMaxLevels);
                double sumB  = DomTotal(_bidSize, 0, depth);
                double sumA  = DomTotal(_askSize, 0, depth);
                double imbalanceRatio = (sumB + sumA > 0) ? (sumB - sumA) / (sumB + sumA) : 0;

                // Queue microprice (L1)
                double iL1   = (_bidSize[0] + _askSize[0] > 0)
                    ? (_bidSize[0] - _askSize[0]) / (_bidSize[0] + _askSize[0]) : 0;
                double mpLong1tick = (iL1 + 1.0) / 2.0;

                // Bayesian LOB (5-level)
                double sumB5 = DomTotal(_bidSize, 0, LobBayesDepth);
                double sumA5 = DomTotal(_askSize, 0, LobBayesDepth);
                double iLob5 = (sumB5 + sumA5 > 0) ? (sumB5 - sumA5) / (sumB5 + sumA5) : 0;
                double pUpLob = (iLob5 + 1.0) / 2.0;
                double prior  = Clamp01(BayesianPrior);
                double denom  = pUpLob * prior + (1.0 - pUpLob) * (1.0 - prior);
                double pFinalUp = (denom < 1e-12) ? prior : (pUpLob * prior) / denom;
                pFinalUp = Clamp01(pFinalUp);

                // Kalman fusion
                double xPred = _kalmanX, pPred = _kalmanP + KalmanQ;
                double k1 = pPred / (pPred + KalmanR);
                xPred = xPred + k1 * (mpLong1tick - xPred);
                double pCov = (1.0 - k1) * pPred;
                double k2 = pCov / (pCov + KalmanR);
                _kalmanX = xPred + k2 * (pFinalUp - xPred);
                _kalmanP = (1.0 - k2) * pCov;

                double mpFinalLong  = Clamp01(_kalmanX) * 100.0;
                double mpFinalShort = 100.0 - mpFinalLong;

                // Wasserstein-1 (CounterSpoof)
                double w1Bid = 0, w1Ask = 0;
                if (_prevDomCaptured)
                {
                    w1Bid = Wasserstein1(_prevBidSize, _bidSize, depth);
                    w1Ask = Wasserstein1(_prevAskSize, _askSize, depth);
                }
                Array.Copy(_bidSize, _prevBidSize, DomMaxLevels);
                Array.Copy(_askSize, _prevAskSize, DomMaxLevels);
                _prevDomCaptured = true;

                Values[0][0] = imbalanceRatio * 100.0;
                Values[1][0] = mpFinalLong;
                Values[2][0] = mpFinalShort;
                Values[3][0] = spoofRaw * 100.0;

                _lastImbalanceRatio = imbalanceRatio * 100.0;
                _lastMpLong         = mpFinalLong;
                _lastMpShort        = mpFinalShort;
                _lastSpoofScore     = spoofRaw * 100.0;

                bool trespassLong  = imbalanceRatio  >  ImbalanceThreshold &&
                                     mpFinalLong  / 100.0 > MpMinConfidence &&
                                     spoofRaw < MaxSpoofScore;
                bool trespassShort = imbalanceRatio  < -ImbalanceThreshold &&
                                     mpFinalShort / 100.0 > MpMinConfidence &&
                                     spoofRaw < MaxSpoofScore;
                bool cspBull = (w1Ask > W1Threshold) && (w1Ask > w1Bid);
                bool cspBear = (w1Bid > W1Threshold) && (w1Bid > w1Ask);
                _lastCspBull = cspBull;
                _lastCspBear = cspBear;

                // Price chart signals — BUY / SELL labels, no jargon
                if (trespassLong)
                {
                    Draw.ArrowUp(this, "TL_" + CurrentBar, false, 0, Low[0]  - 3 * TickSize, _wBull);
                    Draw.Text(this,    "TT_" + CurrentBar, "BUY",  0, Low[0]  - 8 * TickSize, _wBull);
                }
                if (trespassShort)
                {
                    Draw.ArrowDown(this, "TS_" + CurrentBar, false, 0, High[0] + 3 * TickSize, _wBear);
                    Draw.Text(this,      "ST_" + CurrentBar, "SELL", 0, High[0] + 8 * TickSize, _wBear);
                }
                if (cspBull)
                {
                    Draw.Diamond(this, "CB_" + CurrentBar, false, 0, Low[0]  - 5 * TickSize, _wCspBull);
                    Draw.Text(this,    "CT_" + CurrentBar, "BUY",  0, Low[0]  - 10 * TickSize, _wCspBull);
                }
                if (cspBear)
                {
                    Draw.Diamond(this, "CS_" + CurrentBar, false, 0, High[0] + 5 * TickSize, _wCspBear);
                    Draw.Text(this,    "CST_"+ CurrentBar, "SELL", 0, High[0] + 10 * TickSize, _wCspBear);
                }

                _bidAdded = 0; _askAdded = 0; _bidCancelled = 0; _askCancelled = 0;
                _barBidTrades = 0; _barAskTrades = 0;
            }
            else
            {
                int    depth  = System.Math.Min(LobDepthLevels, DomMaxLevels);
                double sumBid = DomTotal(_bidSize, 0, depth);
                double sumAsk = DomTotal(_askSize, 0, depth);
                double imb    = (sumBid + sumAsk > 0) ? (sumBid - sumAsk) / (sumBid + sumAsk) : 0;
                _liveDomBid         = sumBid;
                _liveDomAsk         = sumAsk;
                _lastImbalanceRatio = imb * 100.0;
                Values[0][0]        = _lastImbalanceRatio;
                Values[1][0]        = _lastMpLong;
                Values[2][0]        = _lastMpShort;
                Values[3][0]        = _lastSpoofScore;
            }
        }

        // ─────────────────────────────────────────────────────────────────
        //  Helpers
        // ─────────────────────────────────────────────────────────────────
        private static double DomTotal(double[] arr, int start, int end)
        {
            double s = 0; int lim = System.Math.Min(end, arr.Length);
            for (int i = start; i < lim; i++) s += arr[i];
            return s;
        }

        private static double Clamp01(double v) => v < 0 ? 0 : v > 1 ? 1 : v;

        private static double RollingMax(double[] arr, int count)
        {
            if (count <= 0) return 0;
            double m = arr[0]; int lim = System.Math.Min(count, arr.Length);
            for (int i = 1; i < lim; i++) if (arr[i] > m) m = arr[i];
            return m;
        }

        private static double Wasserstein1(double[] u, double[] v, int n)
        {
            n = System.Math.Min(n, System.Math.Min(u.Length, v.Length));
            if (n == 0) return 0;
            double sumU = 0, sumV = 0;
            for (int i = 0; i < n; i++) { sumU += u[i]; sumV += v[i]; }
            if (sumU == 0 || sumV == 0) return 0;
            double w1 = 0, cdfU = 0, cdfV = 0;
            for (int i = 0; i < n; i++)
            {
                cdfU += u[i] / sumU; cdfV += v[i] / sumV;
                w1   += System.Math.Abs(cdfU - cdfV);
            }
            return w1;
        }

        private static SolidColorBrush MakeFrozenBrush(Color c)
        {
            var b = new SolidColorBrush(c);
            if (b.CanFreeze) b.Freeze();
            return b;
        }

        // ─────────────────────────────────────────────────────────────────
        //  Properties
        // ─────────────────────────────────────────────────────────────────
        #region Parameters
        [NinjaScriptProperty] [Range(1, 20)]
        [Display(Name = "LOB Depth Levels", GroupName = "Signal Parameters", Order = 1)]
        public int LobDepthLevels { get; set; }

        [NinjaScriptProperty] [Range(0.01, 1.0)]
        [Display(Name = "Imbalance Threshold", GroupName = "Signal Parameters", Order = 2)]
        public double ImbalanceThreshold { get; set; }

        [NinjaScriptProperty] [Range(0.0, 1.0)]
        [Display(Name = "MP Min Confidence", GroupName = "Signal Parameters", Order = 3)]
        public double MpMinConfidence { get; set; }

        [NinjaScriptProperty] [Range(0.0, 1.0)]
        [Display(Name = "Max Spoof Score", GroupName = "Signal Parameters", Order = 4)]
        public double MaxSpoofScore { get; set; }

        [NinjaScriptProperty] [Range(0.0, 1.0)]
        [Display(Name = "W1 Threshold", GroupName = "Signal Parameters", Order = 5)]
        public double W1Threshold { get; set; }

        [NinjaScriptProperty] [Range(1, 50)]
        [Display(Name = "Spoof Rolling Bars", GroupName = "Signal Parameters", Order = 6)]
        public int SpoofRollingBars { get; set; }

        [NinjaScriptProperty] [Range(0.0, 1.0)]
        [Display(Name = "Bayesian Prior P(up)", GroupName = "Signal Parameters", Order = 7)]
        public double BayesianPrior { get; set; }
        #endregion

        #region Plot accessors
        [Browsable(false)] [XmlIgnore] public Series<double> ImbalanceRatio => Values[0];
        [Browsable(false)] [XmlIgnore] public Series<double> MicroProbLong  => Values[1];
        [Browsable(false)] [XmlIgnore] public Series<double> MicroProbShort => Values[2];
        [Browsable(false)] [XmlIgnore] public Series<double> SpoofScore     => Values[3];
        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6.DEEP6LiquidityImbalance[] cacheDEEP6LiquidityImbalance;
        public DEEP6.DEEP6LiquidityImbalance DEEP6LiquidityImbalance(int lobDepthLevels, double imbalanceThreshold, double mpMinConfidence, double maxSpoofScore, double w1Threshold, int spoofRollingBars, double bayesianPrior)
        {
            return DEEP6LiquidityImbalance(Input, lobDepthLevels, imbalanceThreshold, mpMinConfidence, maxSpoofScore, w1Threshold, spoofRollingBars, bayesianPrior);
        }

        public DEEP6.DEEP6LiquidityImbalance DEEP6LiquidityImbalance(ISeries<double> input, int lobDepthLevels, double imbalanceThreshold, double mpMinConfidence, double maxSpoofScore, double w1Threshold, int spoofRollingBars, double bayesianPrior)
        {
            if (cacheDEEP6LiquidityImbalance != null)
                for (int idx = 0; idx < cacheDEEP6LiquidityImbalance.Length; idx++)
                    if (cacheDEEP6LiquidityImbalance[idx] != null
                        && cacheDEEP6LiquidityImbalance[idx].LobDepthLevels      == lobDepthLevels
                        && cacheDEEP6LiquidityImbalance[idx].ImbalanceThreshold  == imbalanceThreshold
                        && cacheDEEP6LiquidityImbalance[idx].MpMinConfidence     == mpMinConfidence
                        && cacheDEEP6LiquidityImbalance[idx].MaxSpoofScore       == maxSpoofScore
                        && cacheDEEP6LiquidityImbalance[idx].W1Threshold         == w1Threshold
                        && cacheDEEP6LiquidityImbalance[idx].SpoofRollingBars    == spoofRollingBars
                        && cacheDEEP6LiquidityImbalance[idx].BayesianPrior       == bayesianPrior
                        && cacheDEEP6LiquidityImbalance[idx].EqualsInput(input))
                        return cacheDEEP6LiquidityImbalance[idx];
            return CacheIndicator<DEEP6.DEEP6LiquidityImbalance>(
                new DEEP6.DEEP6LiquidityImbalance()
                {
                    LobDepthLevels     = lobDepthLevels,
                    ImbalanceThreshold = imbalanceThreshold,
                    MpMinConfidence    = mpMinConfidence,
                    MaxSpoofScore      = maxSpoofScore,
                    W1Threshold        = w1Threshold,
                    SpoofRollingBars   = spoofRollingBars,
                    BayesianPrior      = bayesianPrior,
                }, input, ref cacheDEEP6LiquidityImbalance);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6.DEEP6LiquidityImbalance DEEP6LiquidityImbalance(int lobDepthLevels, double imbalanceThreshold, double mpMinConfidence, double maxSpoofScore, double w1Threshold, int spoofRollingBars, double bayesianPrior)
        {
            return indicator.DEEP6LiquidityImbalance(Input, lobDepthLevels, imbalanceThreshold, mpMinConfidence, maxSpoofScore, w1Threshold, spoofRollingBars, bayesianPrior);
        }

        public Indicators.DEEP6.DEEP6LiquidityImbalance DEEP6LiquidityImbalance(ISeries<double> input, int lobDepthLevels, double imbalanceThreshold, double mpMinConfidence, double maxSpoofScore, double w1Threshold, int spoofRollingBars, double bayesianPrior)
        {
            return indicator.DEEP6LiquidityImbalance(input, lobDepthLevels, imbalanceThreshold, mpMinConfidence, maxSpoofScore, w1Threshold, spoofRollingBars, bayesianPrior);
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.DEEP6.DEEP6LiquidityImbalance DEEP6LiquidityImbalance(int lobDepthLevels, double imbalanceThreshold, double mpMinConfidence, double maxSpoofScore, double w1Threshold, int spoofRollingBars, double bayesianPrior)
        {
            return indicator.DEEP6LiquidityImbalance(Input, lobDepthLevels, imbalanceThreshold, mpMinConfidence, maxSpoofScore, w1Threshold, spoofRollingBars, bayesianPrior);
        }

        public Indicators.DEEP6.DEEP6LiquidityImbalance DEEP6LiquidityImbalance(ISeries<double> input, int lobDepthLevels, double imbalanceThreshold, double mpMinConfidence, double maxSpoofScore, double w1Threshold, int spoofRollingBars, double bayesianPrior)
        {
            return indicator.DEEP6LiquidityImbalance(input, lobDepthLevels, imbalanceThreshold, mpMinConfidence, maxSpoofScore, w1Threshold, spoofRollingBars, bayesianPrior);
        }
    }
}
#endregion
