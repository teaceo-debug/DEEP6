// DEEP6 Footprint — NinjaTrader 8 indicator
// Renders a per-bar footprint (bid × ask volume per price level), POC/VAH/VAL markers,
// absorption & exhaustion signal triangles, and optional GEX overlay levels fetched
// from massive.com.
//
// Parallel deliverable alongside the DEEP6 Python auto-trading system. Read-only —
// no order entry. Uses NT8's native Rithmic L2 feed; no external data connection.
//
// Install: drop this file + AddOns\DEEP6\*.cs into
//   %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\
// then right-click Indicators pane → Reload NinjaScript. Chart → add "DEEP6 Footprint".

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript.DrawingTools;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6Footprint : Indicator
    {
        // ---- State ----
        private readonly Dictionary<int, FootprintBar> _bars = new Dictionary<int, FootprintBar>();
        private double _bestBid = double.NaN;
        private double _bestAsk = double.NaN;
        private long _priorCvd;
        private FootprintBar _priorFinalized;

        // volume EMA (for absorption thresholds) — simple 20-period EMA of TotalVol
        private double _volEma;
        private const double VolEmaAlpha = 2.0 / (20.0 + 1.0);

        // ATR via rolling window of (high-low)
        private readonly Queue<double> _atrWindow = new Queue<double>();
        private const int AtrPeriod = 20;
        private double _atr = 1.0;

        // detectors + configs
        private readonly AbsorptionConfig _absCfg = new AbsorptionConfig();
        private readonly ExhaustionConfig _exhCfg = new ExhaustionConfig();
        private readonly ExhaustionDetector _exhDetector = new ExhaustionDetector();

        // GEX
        private MassiveGexClient _gexClient;
        private volatile GexProfile _gexProfile;
        private DateTime _lastGexFetch = DateTime.MinValue;
        private readonly TimeSpan _gexInterval = TimeSpan.FromMinutes(2);
        private CancellationTokenSource _gexCts;

        // session reset tracking
        private DateTime _lastSessionDate = DateTime.MinValue;

        // SharpDX brushes (device-dependent)
        private SharpDX.Direct2D1.Brush _bidDx, _askDx, _textDx, _imbalBuyDx, _imbalSellDx,
                                         _pocDx, _vahDx, _valDx, _gexFlipDx, _gexCallWallDx,
                                         _gexPutWallDx, _gexPosDx, _gexNegDx, _gridDx;
        private TextFormat _cellFont, _labelFont;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description         = "DEEP6 Footprint — per-bar footprint with absorption/exhaustion markers and GEX overlay.";
                Name                = "DEEP6 Footprint";
                Calculate           = Calculate.OnEachTick;
                IsOverlay           = true;
                DisplayInDataBox    = false;
                DrawOnPricePanel    = true;
                PaintPriceMarkers   = false;
                ScaleJustification  = ScaleJustification.Right;
                IsSuspendedWhileInactive = true;

                // Defaults
                ImbalanceRatio          = 3.0;
                ShowFootprintCells      = true;
                ShowAbsorptionMarkers   = true;
                ShowExhaustionMarkers   = true;
                ShowPoc                 = true;
                ShowValueArea           = true;
                ShowGexLevels           = true;
                GexUnderlying           = "QQQ";
                GexApiKey               = string.Empty;
                AbsorbWickMinPct        = 30.0;
                ExhaustWickMinPct       = 35.0;
                CellFontSize            = 9f;
                CellColumnWidth         = 80;

                BidCellBrush      = Brushes.IndianRed;
                AskCellBrush      = Brushes.LimeGreen;
                CellTextBrush     = Brushes.WhiteSmoke;
                PocBrush          = Brushes.Gold;
                VahBrush          = MakeFrozenBrush(Color.FromRgb(160, 200, 255));
                ValBrush          = MakeFrozenBrush(Color.FromRgb(160, 200, 255));
                ImbalanceBuyBrush = MakeFrozenBrush(Color.FromArgb(110, 0, 200, 80));
                ImbalanceSellBrush= MakeFrozenBrush(Color.FromArgb(110, 220, 40, 40));
                GexFlipBrush      = Brushes.Yellow;
                GexCallWallBrush  = Brushes.LimeGreen;
                GexPutWallBrush   = Brushes.OrangeRed;
                GexPositiveBrush  = MakeFrozenBrush(Color.FromArgb(180, 0, 180, 120));
                GexNegativeBrush  = MakeFrozenBrush(Color.FromArgb(180, 200, 70, 70));
            }
            else if (State == State.Configure)
            {
                _absCfg.AbsorbWickMin  = AbsorbWickMinPct;
                _exhCfg.ExhaustWickMin = ExhaustWickMinPct;
            }
            else if (State == State.DataLoaded)
            {
                _bars.Clear();
                _exhDetector.ResetCooldowns();
                _atrWindow.Clear();
                _volEma = 0.0;
                _priorCvd = 0;
                _priorFinalized = null;

                if (ShowGexLevels && !string.IsNullOrWhiteSpace(GexApiKey))
                {
                    _gexClient = new MassiveGexClient(GexApiKey);
                    _gexCts = new CancellationTokenSource();
                }
            }
            else if (State == State.Terminated)
            {
                if (_gexCts != null) { try { _gexCts.Cancel(); } catch { } }
                if (_gexClient != null) { _gexClient.Dispose(); _gexClient = null; }
                DisposeDx();
            }
        }

        // ---- Tick intake ----

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (State != State.Realtime && State != State.Historical) return;

            if (e.MarketDataType == MarketDataType.Bid) { _bestBid = e.Price; return; }
            if (e.MarketDataType == MarketDataType.Ask) { _bestAsk = e.Price; return; }
            if (e.MarketDataType != MarketDataType.Last) return;
            if (CurrentBar < 0) return;

            int aggressor;
            if (!double.IsNaN(_bestAsk) && e.Price >= _bestAsk) aggressor = 1;
            else if (!double.IsNaN(_bestBid) && e.Price <= _bestBid) aggressor = 2;
            else aggressor = 0;

            FootprintBar bar;
            if (!_bars.TryGetValue(CurrentBar, out bar))
            {
                bar = new FootprintBar { BarIndex = CurrentBar };
                _bars[CurrentBar] = bar;
            }
            bar.AddTrade(e.Price, (long)e.Volume, aggressor);
        }

        // WPF brushes created off the UI thread (NT8 calls SetDefaults / OnRenderTargetChanged
        // from worker threads) throw InvalidOperationException unless frozen. Always construct via this helper.
        private static SolidColorBrush MakeFrozenBrush(Color c)
        {
            var b = new SolidColorBrush(c);
            if (b.CanFreeze) b.Freeze();
            return b;
        }

        // ---- Bar lifecycle ----

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;
            if (CurrentBar < 2) return;

            if (!IsFirstTickOfBar) return;

            int prevIdx = CurrentBar - 1;
            FootprintBar prev;
            if (!_bars.TryGetValue(prevIdx, out prev)) return;

            // Reconcile OHLC with NT8's authoritative bar (handles silent-tick edge case).
            prev.Open = Bars.GetOpen(prevIdx);
            prev.High = Bars.GetHigh(prevIdx);
            prev.Low  = Bars.GetLow(prevIdx);
            prev.Close= Bars.GetClose(prevIdx);
            prev.Finalize(_priorCvd);
            _priorCvd = prev.Cvd;

            // Update rolling ATR / vol EMA
            _atrWindow.Enqueue(prev.BarRange);
            while (_atrWindow.Count > AtrPeriod) _atrWindow.Dequeue();
            double sum = 0; foreach (var v in _atrWindow) sum += v;
            _atr = _atrWindow.Count == 0 ? 1.0 : Math.Max(sum / _atrWindow.Count, 0.25);
            _volEma = _volEma == 0 ? prev.TotalVol : _volEma + VolEmaAlpha * (prev.TotalVol - _volEma);

            // Session reset at RTH open (9:30 ET) — simple date-change detection.
            DateTime barDate = Bars.GetTime(prevIdx).Date;
            if (barDate != _lastSessionDate)
            {
                _exhDetector.ResetCooldowns();
                _lastSessionDate = barDate;
            }

            // Compute VAH/VAL for this bar (used by absorption VA bonus).
            var va = FootprintBar.ComputeValueArea(prev, TickSize);

            // Run detectors.
            if (ShowAbsorptionMarkers)
            {
                var abs = AbsorptionDetector.Detect(prev, _atr, _volEma, _absCfg, va.vah, va.val, TickSize);
                for (int i = 0; i < abs.Count; i++) DrawAbsorptionMarker(prevIdx, abs[i]);
            }
            if (ShowExhaustionMarkers)
            {
                var exh = _exhDetector.Detect(prev, _priorFinalized, prevIdx, _atr, _exhCfg);
                for (int i = 0; i < exh.Count; i++) DrawExhaustionMarker(prevIdx, exh[i]);
            }

            _priorFinalized = prev;

            // Trim history.
            int cutoff = CurrentBar - 500;
            if (cutoff > 0)
            {
                var stale = _bars.Keys.Where(k => k < cutoff).ToList();
                foreach (var k in stale) _bars.Remove(k);
            }

            // Kick GEX fetch if due.
            MaybeFetchGex();
        }

        private void DrawAbsorptionMarker(int barIdx, AbsorptionSignal s)
        {
            string tag = string.Format("ABS_{0}_{1}_{2}", barIdx, (int)s.Kind, s.Wick);
            Brush brush = s.Direction >= 0 ? Brushes.Cyan : Brushes.Magenta;
            int barsAgo = CurrentBar - barIdx;
            if (s.Direction >= 0)
                Draw.TriangleUp(this, tag, false, barsAgo, s.Price - 4 * TickSize, brush);
            else
                Draw.TriangleDown(this, tag, false, barsAgo, s.Price + 4 * TickSize, brush);
            Draw.Text(this, tag + "_lbl", s.Kind.ToString().Substring(0, Math.Min(3, s.Kind.ToString().Length)).ToUpper(),
                      barsAgo, s.Price + (s.Direction >= 0 ? -8 : 8) * TickSize, brush);
        }

        private void DrawExhaustionMarker(int barIdx, ExhaustionSignal s)
        {
            string tag = string.Format("EXH_{0}_{1}", barIdx, (int)s.Kind);
            Brush brush;
            if (s.Direction > 0) brush = Brushes.Yellow;
            else if (s.Direction < 0) brush = Brushes.OrangeRed;
            else brush = Brushes.SlateGray;
            int barsAgo = CurrentBar - barIdx;
            if (s.Direction > 0)
                Draw.ArrowUp(this, tag, false, barsAgo, s.Price - 5 * TickSize, brush);
            else if (s.Direction < 0)
                Draw.ArrowDown(this, tag, false, barsAgo, s.Price + 5 * TickSize, brush);
            else
                Draw.Diamond(this, tag, false, barsAgo, s.Price, brush);
        }

        // ---- GEX fetch ----

        private void MaybeFetchGex()
        {
            if (_gexClient == null) return;
            if (DateTime.UtcNow - _lastGexFetch < _gexInterval) return;
            _lastGexFetch = DateTime.UtcNow;

            var ctsTok = _gexCts == null ? CancellationToken.None : _gexCts.Token;
            var client = _gexClient;
            var underlying = GexUnderlying;

            Task.Run(async () =>
            {
                try
                {
                    var profile = await client.FetchAsync(underlying, ctsTok).ConfigureAwait(false);
                    if (profile != null) _gexProfile = profile;
                }
                catch { }
            });
        }

        // ---- Custom render ----

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            _bidDx        = BidCellBrush.ToDxBrush(RenderTarget);
            _askDx        = AskCellBrush.ToDxBrush(RenderTarget);
            _textDx       = CellTextBrush.ToDxBrush(RenderTarget);
            _imbalBuyDx   = ImbalanceBuyBrush.ToDxBrush(RenderTarget);
            _imbalSellDx  = ImbalanceSellBrush.ToDxBrush(RenderTarget);
            _pocDx        = PocBrush.ToDxBrush(RenderTarget);
            _vahDx        = VahBrush.ToDxBrush(RenderTarget);
            _valDx        = ValBrush.ToDxBrush(RenderTarget);
            _gridDx       = MakeFrozenBrush(Color.FromArgb(40, 200, 200, 200)).ToDxBrush(RenderTarget);
            _gexFlipDx    = GexFlipBrush.ToDxBrush(RenderTarget);
            _gexCallWallDx= GexCallWallBrush.ToDxBrush(RenderTarget);
            _gexPutWallDx = GexPutWallBrush.ToDxBrush(RenderTarget);
            _gexPosDx     = GexPositiveBrush.ToDxBrush(RenderTarget);
            _gexNegDx     = GexNegativeBrush.ToDxBrush(RenderTarget);

            _cellFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", CellFontSize)
            {
                TextAlignment = TextAlignment.Center,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
            _labelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 10f)
            {
                TextAlignment = TextAlignment.Trailing,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
        }

        private void DisposeDx()
        {
            DisposeBrush(ref _bidDx); DisposeBrush(ref _askDx); DisposeBrush(ref _textDx);
            DisposeBrush(ref _imbalBuyDx); DisposeBrush(ref _imbalSellDx);
            DisposeBrush(ref _pocDx); DisposeBrush(ref _vahDx); DisposeBrush(ref _valDx);
            DisposeBrush(ref _gridDx);
            DisposeBrush(ref _gexFlipDx); DisposeBrush(ref _gexCallWallDx); DisposeBrush(ref _gexPutWallDx);
            DisposeBrush(ref _gexPosDx); DisposeBrush(ref _gexNegDx);
            if (_cellFont != null) { _cellFont.Dispose(); _cellFont = null; }
            if (_labelFont != null) { _labelFont.Dispose(); _labelFont = null; }
        }

        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush b) { if (b != null) { b.Dispose(); b = null; } }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (RenderTarget == null || ChartBars == null) return;
            if (chartControl.Instrument == null) return;
            if (_cellFont == null) return;

            base.OnRender(chartControl, chartScale);
            RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

            double tickSize = chartControl.Instrument.MasterInstrument.TickSize;
            float panelRight = (float)(ChartPanel.X + ChartPanel.W);

            // GEX horizontal levels first (behind everything)
            if (ShowGexLevels && _gexProfile != null)
                RenderGex(_gexProfile, chartControl, chartScale, panelRight);

            if (!ShowFootprintCells && !ShowPoc && !ShowValueArea) return;

            int barPaintW = chartControl.GetBarPaintWidth(ChartBars);
            int colW = Math.Max(CellColumnWidth, barPaintW);
            float rowH = (float)Math.Max(8, chartScale.GetPixelsForDistance(tickSize));

            int fromIdx = ChartBars.FromIndex;
            int toIdx = ChartBars.ToIndex;

            for (int barIdx = fromIdx; barIdx <= toIdx; barIdx++)
            {
                FootprintBar fbar;
                if (!_bars.TryGetValue(barIdx, out fbar)) continue;
                if (fbar.Levels.Count == 0) continue;

                int xCenter = chartControl.GetXByBarIndex(ChartBars, barIdx);
                float xLeft = xCenter - colW / 2f;

                long maxLevelVol = 0;
                foreach (var kv in fbar.Levels)
                {
                    long v = kv.Value.AskVol + kv.Value.BidVol;
                    if (v > maxLevelVol) maxLevelVol = v;
                }

                if (ShowFootprintCells)
                {
                    foreach (var kv in fbar.Levels)
                    {
                        double px = kv.Key;
                        var cell = kv.Value;
                        float yCenter = chartScale.GetYByValue(px);
                        float yTop = yCenter - rowH / 2f;
                        var rect = new RectangleF(xLeft, yTop, colW, rowH);

                        // Imbalance: diagonal ask-at-px vs bid-at-(px+tick), and mirror.
                        long diagBid = GetBid(fbar, px + tickSize);
                        long diagAsk = GetAsk(fbar, px - tickSize);
                        bool buyImbal  = cell.AskVol > 0 && cell.AskVol >= ImbalanceRatio * Math.Max(1, diagBid);
                        bool sellImbal = cell.BidVol > 0 && cell.BidVol >= ImbalanceRatio * Math.Max(1, diagAsk);
                        if (buyImbal)       RenderTarget.FillRectangle(rect, _imbalBuyDx);
                        else if (sellImbal) RenderTarget.FillRectangle(rect, _imbalSellDx);

                        string label = string.Format("{0} x {1}", cell.BidVol, cell.AskVol);
                        using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, label, _cellFont, colW, rowH))
                        {
                            RenderTarget.DrawTextLayout(new Vector2(xLeft, yTop), layout, _textDx);
                        }
                    }
                }

                // POC bar (horizontal tick at POC price spanning column width)
                if (ShowPoc && fbar.PocPrice > 0)
                {
                    float yPoc = chartScale.GetYByValue(fbar.PocPrice);
                    var pocRect = new RectangleF(xLeft, yPoc - 1, colW, 2);
                    RenderTarget.FillRectangle(pocRect, _pocDx);
                }

                // VAH/VAL (at this bar)
                if (ShowValueArea)
                {
                    var va = FootprintBar.ComputeValueArea(fbar, tickSize);
                    float yVah = chartScale.GetYByValue(va.vah);
                    float yVal = chartScale.GetYByValue(va.val);
                    RenderTarget.DrawLine(new Vector2(xLeft, yVah), new Vector2(xLeft + colW, yVah), _vahDx, 1f);
                    RenderTarget.DrawLine(new Vector2(xLeft, yVal), new Vector2(xLeft + colW, yVal), _valDx, 1f);
                }
            }
        }

        private static long GetBid(FootprintBar bar, double price)
        {
            Cell c; return bar.Levels.TryGetValue(price, out c) ? c.BidVol : 0;
        }
        private static long GetAsk(FootprintBar bar, double price)
        {
            Cell c; return bar.Levels.TryGetValue(price, out c) ? c.AskVol : 0;
        }

        private void RenderGex(GexProfile gex, ChartControl cc, ChartScale cs, float panelRight)
        {
            // Note: GEX strikes are in the underlying's price space (QQQ),
            // but our chart is NQ. Map QQQ → NQ via a simple multiplier inferred
            // from spot ratio. This is a rough visual overlay, not a tradeable level.
            double nqSpot = (Bars != null && Bars.Count > 0) ? Bars.GetClose(Bars.Count - 1) : 0;
            double qqqSpot = gex.Spot;
            if (nqSpot <= 0 || qqqSpot <= 0) return;
            double mult = nqSpot / qqqSpot;

            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;

            foreach (var lv in gex.Levels)
            {
                double mapped = lv.Strike * mult;
                if (mapped < minVis || mapped > maxVis) continue;

                SharpDX.Direct2D1.Brush brush;
                float width;
                switch (lv.Kind)
                {
                    case GexLevelKind.GammaFlip: brush = _gexFlipDx;     width = 2.0f; break;
                    case GexLevelKind.CallWall:  brush = _gexCallWallDx; width = 1.8f; break;
                    case GexLevelKind.PutWall:   brush = _gexPutWallDx;  width = 1.8f; break;
                    case GexLevelKind.MajorPositive: brush = _gexPosDx;  width = 0.8f; break;
                    default: brush = _gexNegDx; width = 0.8f; break;
                }
                float y = cs.GetYByValue(mapped);
                RenderTarget.DrawLine(new Vector2((float)ChartPanel.X, y),
                                      new Vector2(panelRight, y), brush, width);

                string label = string.Format("{0} ({1:F2})", lv.Label, mapped);
                var lblRect = new RectangleF(panelRight - 160, y - 8, 156, 16);
                using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, label, _labelFont, 156, 16))
                {
                    RenderTarget.DrawTextLayout(new Vector2(panelRight - 160, y - 8), layout, brush);
                }
            }
        }

        #region Properties

        [NinjaScriptProperty]
        [Range(1.0, 10.0)]
        [Display(Name = "Imbalance Ratio", Order = 1, GroupName = "1. Detection")]
        public double ImbalanceRatio { get; set; }

        [NinjaScriptProperty]
        [Range(5.0, 80.0)]
        [Display(Name = "Absorption Wick Min %", Order = 2, GroupName = "1. Detection")]
        public double AbsorbWickMinPct { get; set; }

        [NinjaScriptProperty]
        [Range(5.0, 80.0)]
        [Display(Name = "Exhaustion Wick Min %", Order = 3, GroupName = "1. Detection")]
        public double ExhaustWickMinPct { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Footprint Cells", Order = 10, GroupName = "2. Display")]
        public bool ShowFootprintCells { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show POC", Order = 11, GroupName = "2. Display")]
        public bool ShowPoc { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Value Area", Order = 12, GroupName = "2. Display")]
        public bool ShowValueArea { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Absorption Markers", Order = 13, GroupName = "2. Display")]
        public bool ShowAbsorptionMarkers { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Exhaustion Markers", Order = 14, GroupName = "2. Display")]
        public bool ShowExhaustionMarkers { get; set; }

        [NinjaScriptProperty]
        [Range(7f, 16f)]
        [Display(Name = "Cell Font Size", Order = 15, GroupName = "2. Display")]
        public float CellFontSize { get; set; }

        [NinjaScriptProperty]
        [Range(40, 200)]
        [Display(Name = "Cell Column Width (px)", Order = 16, GroupName = "2. Display")]
        public int CellColumnWidth { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show GEX Levels", Order = 20, GroupName = "3. GEX (massive.com)")]
        public bool ShowGexLevels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "GEX Underlying (QQQ/NDX)", Order = 21, GroupName = "3. GEX (massive.com)")]
        public string GexUnderlying { get; set; }

        [NinjaScriptProperty]
        [PasswordPropertyText(true)]
        [Display(Name = "massive.com API Key", Order = 22, GroupName = "3. GEX (massive.com)")]
        public string GexApiKey { get; set; }

        // --- Brush properties (require *Serialize string companions for XML serialization) ---

        [XmlIgnore]
        [Display(Name = "Bid Cell Color",      Order = 30, GroupName = "4. Colors")]
        public Brush BidCellBrush { get; set; }
        [Browsable(false)] public string BidCellBrushSerialize     { get { return Serialize.BrushToString(BidCellBrush); }     set { BidCellBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Ask Cell Color",      Order = 31, GroupName = "4. Colors")]
        public Brush AskCellBrush { get; set; }
        [Browsable(false)] public string AskCellBrushSerialize     { get { return Serialize.BrushToString(AskCellBrush); }     set { AskCellBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Cell Text Color",     Order = 32, GroupName = "4. Colors")]
        public Brush CellTextBrush { get; set; }
        [Browsable(false)] public string CellTextBrushSerialize    { get { return Serialize.BrushToString(CellTextBrush); }    set { CellTextBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "POC Color",           Order = 33, GroupName = "4. Colors")]
        public Brush PocBrush { get; set; }
        [Browsable(false)] public string PocBrushSerialize         { get { return Serialize.BrushToString(PocBrush); }         set { PocBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "VAH Color",           Order = 34, GroupName = "4. Colors")]
        public Brush VahBrush { get; set; }
        [Browsable(false)] public string VahBrushSerialize         { get { return Serialize.BrushToString(VahBrush); }         set { VahBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "VAL Color",           Order = 35, GroupName = "4. Colors")]
        public Brush ValBrush { get; set; }
        [Browsable(false)] public string ValBrushSerialize         { get { return Serialize.BrushToString(ValBrush); }         set { ValBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Imbalance Buy Color", Order = 36, GroupName = "4. Colors")]
        public Brush ImbalanceBuyBrush { get; set; }
        [Browsable(false)] public string ImbalanceBuyBrushSerialize{ get { return Serialize.BrushToString(ImbalanceBuyBrush); }set { ImbalanceBuyBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Imbalance Sell Color",Order = 37, GroupName = "4. Colors")]
        public Brush ImbalanceSellBrush { get; set; }
        [Browsable(false)] public string ImbalanceSellBrushSerialize{ get { return Serialize.BrushToString(ImbalanceSellBrush); } set { ImbalanceSellBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX Flip",            Order = 40, GroupName = "4. Colors")]
        public Brush GexFlipBrush { get; set; }
        [Browsable(false)] public string GexFlipBrushSerialize     { get { return Serialize.BrushToString(GexFlipBrush); }     set { GexFlipBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX Call Wall",       Order = 41, GroupName = "4. Colors")]
        public Brush GexCallWallBrush { get; set; }
        [Browsable(false)] public string GexCallWallBrushSerialize { get { return Serialize.BrushToString(GexCallWallBrush); } set { GexCallWallBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX Put Wall",        Order = 42, GroupName = "4. Colors")]
        public Brush GexPutWallBrush { get; set; }
        [Browsable(false)] public string GexPutWallBrushSerialize  { get { return Serialize.BrushToString(GexPutWallBrush); }  set { GexPutWallBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX + Nodes",         Order = 43, GroupName = "4. Colors")]
        public Brush GexPositiveBrush { get; set; }
        [Browsable(false)] public string GexPositiveBrushSerialize { get { return Serialize.BrushToString(GexPositiveBrush); } set { GexPositiveBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX - Nodes",         Order = 44, GroupName = "4. Colors")]
        public Brush GexNegativeBrush { get; set; }
        [Browsable(false)] public string GexNegativeBrushSerialize { get { return Serialize.BrushToString(GexNegativeBrush); } set { GexNegativeBrush = Serialize.StringToBrush(value); } }

        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6.DEEP6Footprint[] cacheDEEP6Footprint;
        public DEEP6.DEEP6Footprint DEEP6Footprint(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showGexLevels, string gexUnderlying, string gexApiKey)
        {
            return DEEP6Footprint(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showGexLevels, gexUnderlying, gexApiKey);
        }

        public DEEP6.DEEP6Footprint DEEP6Footprint(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showGexLevels, string gexUnderlying, string gexApiKey)
        {
            if (cacheDEEP6Footprint != null)
                for (int idx = 0; idx < cacheDEEP6Footprint.Length; idx++)
                    if (cacheDEEP6Footprint[idx] != null && cacheDEEP6Footprint[idx].ImbalanceRatio == imbalanceRatio && cacheDEEP6Footprint[idx].AbsorbWickMinPct == absorbWickMinPct && cacheDEEP6Footprint[idx].ExhaustWickMinPct == exhaustWickMinPct && cacheDEEP6Footprint[idx].ShowFootprintCells == showFootprintCells && cacheDEEP6Footprint[idx].ShowPoc == showPoc && cacheDEEP6Footprint[idx].ShowValueArea == showValueArea && cacheDEEP6Footprint[idx].ShowAbsorptionMarkers == showAbsorptionMarkers && cacheDEEP6Footprint[idx].ShowExhaustionMarkers == showExhaustionMarkers && cacheDEEP6Footprint[idx].CellFontSize == cellFontSize && cacheDEEP6Footprint[idx].CellColumnWidth == cellColumnWidth && cacheDEEP6Footprint[idx].ShowGexLevels == showGexLevels && cacheDEEP6Footprint[idx].GexUnderlying == gexUnderlying && cacheDEEP6Footprint[idx].GexApiKey == gexApiKey && cacheDEEP6Footprint[idx].EqualsInput(input))
                        return cacheDEEP6Footprint[idx];
            return CacheIndicator<DEEP6.DEEP6Footprint>(new DEEP6.DEEP6Footprint() { ImbalanceRatio = imbalanceRatio, AbsorbWickMinPct = absorbWickMinPct, ExhaustWickMinPct = exhaustWickMinPct, ShowFootprintCells = showFootprintCells, ShowPoc = showPoc, ShowValueArea = showValueArea, ShowAbsorptionMarkers = showAbsorptionMarkers, ShowExhaustionMarkers = showExhaustionMarkers, CellFontSize = cellFontSize, CellColumnWidth = cellColumnWidth, ShowGexLevels = showGexLevels, GexUnderlying = gexUnderlying, GexApiKey = gexApiKey }, input, ref cacheDEEP6Footprint);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6.DEEP6Footprint DEEP6Footprint(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showGexLevels, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6Footprint(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showGexLevels, gexUnderlying, gexApiKey);
        }

        public Indicators.DEEP6.DEEP6Footprint DEEP6Footprint(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showGexLevels, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6Footprint(input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showGexLevels, gexUnderlying, gexApiKey);
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.DEEP6.DEEP6Footprint DEEP6Footprint(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showGexLevels, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6Footprint(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showGexLevels, gexUnderlying, gexApiKey);
        }

        public Indicators.DEEP6.DEEP6Footprint DEEP6Footprint(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showGexLevels, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6Footprint(input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showGexLevels, gexUnderlying, gexApiKey);
        }
    }
}

#endregion
