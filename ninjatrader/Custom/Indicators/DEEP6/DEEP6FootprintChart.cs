// DEEP6 Footprint Chart — clean primary footprint chart indicator.
//
// Design goal: replace the underlying candlestick with a professional footprint.
// Add this indicator to a 5-minute chart; enable HideUnderlyingCandles to cover
// the candles. The footprint IS the chart.
//
// Visual grammar (no Mission Control, no Chart Trader, no tier diamonds):
//   Cells     — bid×ask in Consolas mono, coral-red bid, sky-cyan ask
//   POC       — 2px purple stripe across cell row
//   VA band   — olive tint between VAH and VAL
//   Heatmap   — optional amber volume-intensity gradient per cell
//   VWAP      — white solid + dashed cyan ±1σ/±2σ bands
//   IB        — amber Initial Balance High/Low lines
//   Anchors   — prior-day POC/VAH/VAL, naked POCs, prior-week POC
//   L2 walls  — bid/ask resting order markers from Rithmic
//   Score stripe — 4px right-edge colored bar per bar (TYPE_A=saturated, TYPE_B=medium, TYPE_C=dim)
//   Score HUD — slim 2-line badge: score number + tier label

#region Using
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
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
using NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Levels;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
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
    public class DEEP6FootprintChart : Indicator
    {
        // ── Tick accumulation ────────────────────────────────────────────────
        private readonly Dictionary<int, FootprintBar> _bars = new Dictionary<int, FootprintBar>();
        private readonly object _barsLock = new object();
        private readonly HashSet<int> _finalizedBars = new HashSet<int>();
        private double _bestBid = double.NaN;
        private double _bestAsk = double.NaN;
        private long   _priorCvd;
        private FootprintBar _priorFinalized;

        // ── L2 walls ─────────────────────────────────────────────────────────
        private sealed class L2LevelState
        {
            public long CurrentSize, MaxSize;
            public DateTime LastUpdate;
            public int RefillCount;
        }
        private readonly Dictionary<double, L2LevelState> _l2Bids = new Dictionary<double, L2LevelState>();
        private readonly Dictionary<double, L2LevelState> _l2Asks = new Dictionary<double, L2LevelState>();
        private readonly object _l2Lock = new object();
        private DateTime _lastL2Prune = DateTime.MinValue;

        // ── Rolling ATR / Vol EMA ────────────────────────────────────────────
        private readonly Queue<double> _atrWindow = new Queue<double>();
        private const int AtrPeriod = 20;
        private double _atr = 1.0;
        private double _volEma;
        private const double VolEmaAlpha = 2.0 / (20.0 + 1.0);

        // ── Session tracking ─────────────────────────────────────────────────
        private DateTime _lastSessionDate = DateTime.MinValue;
        private int _sessionBarCount;

        // ── Score storage (for stripe rendering) ─────────────────────────────
        private readonly Dictionary<int, ScorerResult> _barScores = new Dictionary<int, ScorerResult>();
        private volatile ScorerResult _lastScore;
        private DetectorRegistry _registry;
        private SessionContext   _session;

        // ── Profile anchors ──────────────────────────────────────────────────
        private ProfileAnchorLevels _profileAnchors = new ProfileAnchorLevels();
        private DateTime _profileSessionDate = DateTime.MinValue;

        // ── V2 state: VWAP ───────────────────────────────────────────────────
        private double _vwapNum, _vwapDen, _vwapVar;
        private double _vwapPrice, _vwap1H, _vwap1L, _vwap2H, _vwap2L;

        // ── V2 state: Initial Balance ─────────────────────────────────────────
        private double _ibHigh = double.MinValue;
        private double _ibLow  = double.MaxValue;
        private bool   _ibConfirmed;

        // ── V2 state: per-bar classifications ────────────────────────────────
        private struct StackedZone { public double PriceLow, PriceHigh; public int Tier, Direction; }
        private readonly Dictionary<int, int>            _barColumnType    = new Dictionary<int, int>();
        private readonly Dictionary<int, List<StackedZone>> _stackedZones  = new Dictionary<int, List<StackedZone>>();
        private readonly Dictionary<double, int>          _unfinishedAuctions = new Dictionary<double, int>();
        private readonly Dictionary<int, HashSet<double>> _largeLotBars    = new Dictionary<int, HashSet<double>>();
        private readonly Dictionary<int, int>            _volumeClimaxBars = new Dictionary<int, int>();
        private readonly Queue<double> _nBarHighs = new Queue<double>();
        private readonly Queue<double> _nBarLows  = new Queue<double>();
        private const int NBarLookback = 20;

        // ── V2 state: tape speed ─────────────────────────────────────────────
        private int _tradeCountThisSecond;
        private DateTime _tapeSecondWindow = DateTime.MinValue;
        private double _smoothedTapeSpeed, _sessionAvgTapeSpeed;
        private int _tapeSpeedSamples;

        // ── SharpDX brushes ──────────────────────────────────────────────────
        private SharpDX.Direct2D1.Brush _bidDx, _askDx, _textDx, _pocDx, _vahDx, _valDx;
        private SharpDX.Direct2D1.Brush _wallBidDx, _wallAskDx, _bgCoverDx;
        private SharpDX.Direct2D1.SolidColorBrush _anchorPocDx, _anchorVaDx, _anchorNakedDx, _anchorPwPocDx, _anchorCompositeDx;
        private SharpDX.Direct2D1.SolidColorBrush _pwAmberFillDx, _pwCyanFillDx, _pwMagFillDx;
        private SharpDX.Direct2D1.SolidColorBrush _pwTextSecondaryDx, _pwTextTertiaryDx, _pwTextHaloDx;
        private SharpDX.Direct2D1.SolidColorBrush _pwAeroCyanDx, _pwAeroMagentaDx, _pwAeroWhiteDx;
        private SharpDX.Direct2D1.SolidColorBrush _pwSectorPurpleDx;
        private SharpDX.Direct2D1.SolidColorBrush _hudBgDx, _hudTextDx, _hudDimDx, _hudBorderDx;
        private SharpDX.Direct2D1.SolidColorBrush _tierALongDx, _tierAShortDx, _tierBLongDx, _tierBShortDx;
        private SharpDX.Direct2D1.SolidColorBrush _tierCLongDx, _tierCShortDx, _tierNeutralDx;
        private StrokeStyle _dashStyle;
        private TextFormat  _cellFont, _labelFont, _hudFont, _hudSmallFont;

        // ── V2 brushes ───────────────────────────────────────────────────────
        private SharpDX.Direct2D1.SolidColorBrush _vwapLineDx, _vwapBand1Dx, _vwapBand2Dx;
        private SharpDX.Direct2D1.SolidColorBrush _ibLineDx;
        private SharpDX.Direct2D1.SolidColorBrush _stackedBuyZoneDx, _stackedSellZoneDx;
        private SharpDX.Direct2D1.SolidColorBrush _unfinishedLineDx;
        private SharpDX.Direct2D1.SolidColorBrush _bullColumnFillDx, _bearColumnFillDx;
        private SharpDX.Direct2D1.SolidColorBrush _largeLotDotDx, _volumeClimaxDx;
        private const int HeatmapSteps = 16;
        private readonly SharpDX.Direct2D1.SolidColorBrush[] _heatmapPalette =
            new SharpDX.Direct2D1.SolidColorBrush[HeatmapSteps];

        // ════════════════════════════════════════════════════════════════════
        // Lifecycle
        // ════════════════════════════════════════════════════════════════════

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description      = "DEEP6 Footprint Chart — clean 5-minute footprint. Add to a 5-minute chart.";
                Name             = "DEEP6 Footprint Chart";
                Calculate        = Calculate.OnEachTick;
                IsOverlay        = true;
                DrawOnPricePanel = true;
                DisplayInDataBox = false;
                PaintPriceMarkers= false;
                ScaleJustification = ScaleJustification.Right;
                IsSuspendedWhileInactive = true;

                // Footprint cells
                ImbalanceRatio     = 3.0;
                ShowFootprintCells = true;
                ShowPoc            = true;
                ShowValueArea      = true;
                CellFontSize       = 9f;
                CellColumnWidth    = 80;

                // Candle suppression
                HideUnderlyingCandles = true;

                // Session levels
                ShowVWAP            = true;
                ShowVWAPBands       = true;
                ShowInitialBalance  = true;
                ShowProfileAnchors  = true;
                ShowPriorDayLevels  = true;
                ShowNakedPocs       = true;
                NakedPocMaxAgeSessions = 20;

                // Volume patterns
                ShowHeatmapMode         = false;
                ShowStackedZoneBoxes    = true;
                ShowUnfinishedAuctionLines = true;
                ShowLargeLotOverlay     = true;
                LargeLotThreshold       = 50;
                ShowBullBearColumn      = true;
                ShowVolumeClimax        = true;
                VolClimaxMultiplier     = 2.5;

                // L2 walls
                ShowLiquidityWalls   = true;
                LiquidityWallMin     = 100;
                LiquidityWallStaleSec= 90;
                LiquidityMaxPerSide  = 4;

                // Scoring HUD
                ShowScoreHud = true;

                // Colors
                BidCellBrush       = MakeFrozenBrush(Color.FromRgb(0xFF, 0x6B, 0x6B));
                AskCellBrush       = MakeFrozenBrush(Color.FromRgb(0x4F, 0xC3, 0xF7));
                CellTextBrush      = MakeFrozenBrush(Color.FromRgb(0xE6, 0xED, 0xF3));
                PocBrush           = MakeFrozenBrush(Color.FromRgb(0xA1, 0x00, 0xFF));
                VahBrush           = MakeFrozenBrush(Color.FromRgb(0xC8, 0xD1, 0x7A));
                ValBrush           = MakeFrozenBrush(Color.FromRgb(0xC8, 0xD1, 0x7A));
                WallBidBrush       = MakeFrozenBrush(Color.FromArgb(220, 43, 140, 255));
                WallAskBrush       = MakeFrozenBrush(Color.FromArgb(220, 255, 138, 61));
                AnchorPocBrush     = MakeFrozenBrush(Color.FromRgb(0xFF, 0xD2, 0x3F));
                AnchorVaBrush      = MakeFrozenBrush(Color.FromRgb(0xC8, 0xD1, 0x7A));
                AnchorNakedBrush   = MakeFrozenBrush(Color.FromArgb(153, 0xFF, 0xD2, 0x3F));
                AnchorPwPocBrush   = MakeFrozenBrush(Color.FromRgb(0xE5, 0xC2, 0x4A));
                AnchorCompositeBrush = MakeFrozenBrush(Color.FromArgb(30, 0xC8, 0xD1, 0x7A));
            }
            else if (State == State.Configure)
            {
                _registry = new DetectorRegistry();
                _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Absorption.AbsorptionDetector());
                _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion.ExhaustionDetector());
                _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Imbalance.ImbalanceDetector());
                _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta.DeltaDetector());
                _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Auction.AuctionDetector());
                _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.VolPattern.VolPatternDetector());
                _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Trap.TrapDetector());
                _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.TrespassDetector());
                _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.CounterSpoofDetector());
                _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.IcebergDetector());
                _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.VPContextDetector());
                _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.MicroProbDetector());
                _session = new SessionContext { TickSize = TickSize > 0 ? TickSize : 0.25 };
            }
            else if (State == State.DataLoaded)
            {
                lock (_barsLock) { _bars.Clear(); }
                _finalizedBars.Clear();
                _atrWindow.Clear();
                _volEma = 0; _priorCvd = 0; _priorFinalized = null;
                _profileAnchors.Reset();
                _profileAnchors.TickSize = TickSize > 0 ? TickSize : 0.25;
                _profileAnchors.NakedPocMaxAgeSessions = NakedPocMaxAgeSessions;
                _profileSessionDate = DateTime.MinValue;
                ResetV2Session();
            }
            else if (State == State.Terminated)
            {
                try { } catch { }
                DisposeDx();
            }
        }

        // ════════════════════════════════════════════════════════════════════
        // Tick intake
        // ════════════════════════════════════════════════════════════════════

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

            lock (_barsLock)
            {
                FootprintBar bar;
                if (!_bars.TryGetValue(CurrentBar, out bar))
                {
                    bar = new FootprintBar { BarIndex = CurrentBar };
                    _bars[CurrentBar] = bar;
                }
                bar.AddTrade(e.Price, (long)e.Volume, aggressor);

                if (ShowLargeLotOverlay && (long)e.Volume >= LargeLotThreshold)
                {
                    HashSet<double> s;
                    if (!_largeLotBars.TryGetValue(CurrentBar, out s))
                    { s = new HashSet<double>(); _largeLotBars[CurrentBar] = s; }
                    s.Add(e.Price);
                }
            }

            var now = DateTime.UtcNow;
            if (_tapeSecondWindow == DateTime.MinValue) _tapeSecondWindow = now;
            if ((now - _tapeSecondWindow).TotalSeconds >= 1.0)
            {
                double spd = _tradeCountThisSecond;
                _smoothedTapeSpeed = _smoothedTapeSpeed == 0 ? spd : _smoothedTapeSpeed * 0.7 + spd * 0.3;
                _tapeSpeedSamples++;
                _sessionAvgTapeSpeed = _tapeSpeedSamples == 1 ? _smoothedTapeSpeed
                    : _sessionAvgTapeSpeed + (_smoothedTapeSpeed - _sessionAvgTapeSpeed) / _tapeSpeedSamples;
                _tradeCountThisSecond = 0;
                _tapeSecondWindow = now;
            }
            _tradeCountThisSecond++;
        }

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (!ShowLiquidityWalls) return;
            if (e.Position >= 10) return;
            var dict = e.MarketDataType == MarketDataType.Bid ? _l2Bids : e.MarketDataType == MarketDataType.Ask ? _l2Asks : null;
            if (dict == null) return;
            long newSize = e.Operation == Operation.Remove ? 0 : (long)e.Volume;
            lock (_l2Lock)
            {
                L2LevelState st;
                if (!dict.TryGetValue(e.Price, out st)) { st = new L2LevelState(); dict[e.Price] = st; }
                if (st.MaxSize > 0 && st.CurrentSize < st.MaxSize * 0.5 && newSize >= st.MaxSize * 0.5) st.RefillCount++;
                st.CurrentSize = newSize;
                if (newSize > st.MaxSize) st.MaxSize = newSize;
                st.LastUpdate = DateTime.UtcNow;
                if ((DateTime.UtcNow - _lastL2Prune).TotalSeconds > 30)
                { PruneL2(_l2Bids); PruneL2(_l2Asks); _lastL2Prune = DateTime.UtcNow; }
            }
        }

        private static void PruneL2(Dictionary<double, L2LevelState> dict)
        {
            var cut = DateTime.UtcNow.AddMinutes(-15);
            var stale = new List<double>();
            foreach (var kv in dict) if (kv.Value.LastUpdate < cut) stale.Add(kv.Key);
            foreach (var k in stale) dict.Remove(k);
        }

        // ════════════════════════════════════════════════════════════════════
        // Bar lifecycle
        // ════════════════════════════════════════════════════════════════════

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;
            if (CurrentBar < 2) return;
            if (!IsFirstTickOfBar) return;

            int prevIdx = CurrentBar - 1;
            FootprintBar prev;
            lock (_barsLock) { _bars.TryGetValue(prevIdx, out prev); }
            if (prev == null) return;

            DateTime curDate  = Bars.GetTime(CurrentBar).Date;
            bool isNewSession = Bars.IsFirstBarOfSession;
            if (_lastSessionDate == DateTime.MinValue)
            {
                _lastSessionDate = curDate;
                _sessionBarCount = 0;
                _session?.ResetSession();
                _registry?.ResetAll();
            }

            prev.Open  = Bars.GetOpen(prevIdx);
            prev.High  = Bars.GetHigh(prevIdx);
            prev.Low   = Bars.GetLow(prevIdx);
            prev.Close = Bars.GetClose(prevIdx);
            if (!_finalizedBars.Contains(prevIdx)) { prev.Finalize(_priorCvd); _finalizedBars.Add(prevIdx); }
            _priorCvd = prev.Cvd;

            _atrWindow.Enqueue(prev.BarRange);
            while (_atrWindow.Count > AtrPeriod) _atrWindow.Dequeue();
            double atrSum = 0; foreach (var v in _atrWindow) atrSum += v;
            _atr = _atrWindow.Count == 0 ? 1.0 : Math.Max(atrSum / _atrWindow.Count, 0.25);
            _volEma = _volEma == 0 ? prev.TotalVol : _volEma + VolEmaAlpha * (prev.TotalVol - _volEma);

            // V2 computations
            UpdateVwap(prev);
            UpdateInitialBalance(prev);
            DetectBullBearColumn(prev, prevIdx);
            DetectStackedZones(prev, prevIdx);
            DetectUnfinishedAuctions(prev, prevIdx);
            DetectVolumeClimax(prev, prevIdx);

            // Profile anchors
            {
                DateTime bt = Bars.GetTime(prevIdx);
                if (_profileSessionDate == DateTime.MinValue) _profileSessionDate = bt.Date;
                if (bt.Date != _profileSessionDate) { _profileAnchors.OnSessionBoundary(bt.Date); _profileSessionDate = bt.Date; }
                _profileAnchors.OnBarClose(prev, bt);
            }

            // Signal scoring
            if (_registry != null && _session != null)
            {
                var va = FootprintBar.ComputeValueArea(prev, TickSize);
                _session.Atr20        = _atr;
                _session.VolEma20     = _volEma;
                _session.TickSize     = TickSize;
                _session.Vah          = va.vah;
                _session.Val          = va.val;
                _session.PriorBar     = _priorFinalized;
                _session.BarsSinceOpen= _sessionBarCount;
                if (_atr > 0) { _session.SessionAtrSamples++; _session.SessionAvgAtr += (_atr - _session.SessionAvgAtr) / _session.SessionAtrSamples; }

                var signals = _registry.EvaluateBar(prev, _session);
                var zoneSnap = _profileAnchors.BuildSnapshot();
                double zoneScore = ZoneScoreCalculator.Compute(prev.Close, zoneSnap, TickSize);
                var scored = ConfluenceScorer.Score(signals, _session.BarsSinceOpen, prev.BarDelta, prev.Close,
                    zoneScore: zoneScore, zoneDistTicks: double.MaxValue, tickSize: TickSize);
                scored.Signals = signals;
                lock (_barsLock) { _barScores[prevIdx] = scored; }
                _lastScore = scored;
                ScorerSharedState.Publish(Instrument.FullName, CurrentBar, scored, _session.SessionAvgAtr);

                // Push rolling histories
                SessionContext.Push(_session.PriceHistory, prev.Close);
                SessionContext.Push(_session.CvdHistory, prev.Cvd);
                SessionContext.Push(_session.DeltaHistory, prev.BarDelta);
                SessionContext.Push(_session.VolHistory, prev.TotalVol);
                SessionContext.Push(_session.TotalVolHistory, prev.TotalVol);
                SessionContext.Push(_session.PocHistory, prev.PocPrice);
                _session.PriorCvd = prev.Cvd;
                _session.SessionPocPrice = prev.PocPrice;
                if (prev.BarDelta > _session.SessionMaxDelta) _session.SessionMaxDelta = prev.BarDelta;
                if (prev.BarDelta < _session.SessionMinDelta) _session.SessionMinDelta = prev.BarDelta;
            }

            _priorFinalized = prev;
            if (_session != null) _session.PriorBar = prev;

            if (isNewSession)
            {
                _lastSessionDate = curDate; _sessionBarCount = 0;
                _session?.ResetSession(); _registry?.ResetAll();
                if (_profileSessionDate != curDate) { _profileAnchors.OnSessionBoundary(curDate); _profileSessionDate = curDate; }
                ResetV2Session();
            }
            else { _sessionBarCount++; }

            int cutoff = CurrentBar - 500;
            if (cutoff > 0)
            {
                lock (_barsLock)
                {
                    var stale = _bars.Keys.Where(k => k < cutoff).ToList();
                    foreach (var k in stale) _bars.Remove(k);
                    var v2s = new List<int>();
                    foreach (var k in _barColumnType.Keys) if (k < cutoff) v2s.Add(k);
                    foreach (var k in v2s) { _barColumnType.Remove(k); _stackedZones.Remove(k); _largeLotBars.Remove(k); _volumeClimaxBars.Remove(k); _barScores.Remove(k); }
                }
                _finalizedBars.RemoveWhere(k => k < cutoff);
            }
        }

        // ════════════════════════════════════════════════════════════════════
        // V2 computation helpers
        // ════════════════════════════════════════════════════════════════════

        private void ResetV2Session()
        {
            _vwapNum = 0; _vwapDen = 0; _vwapVar = 0;
            _vwapPrice = 0; _vwap1H = 0; _vwap1L = 0; _vwap2H = 0; _vwap2L = 0;
            _ibHigh = double.MinValue; _ibLow = double.MaxValue; _ibConfirmed = false;
            _unfinishedAuctions.Clear();
            _smoothedTapeSpeed = 0; _sessionAvgTapeSpeed = 0; _tapeSpeedSamples = 0; _tradeCountThisSecond = 0;
            _nBarHighs.Clear(); _nBarLows.Clear();
        }

        private void UpdateVwap(FootprintBar bar)
        {
            if (bar.TotalVol == 0) return;
            double tp = (bar.High + bar.Low + bar.Close) / 3.0;
            double vol = bar.TotalVol;
            _vwapNum += tp * vol; _vwapDen += vol;
            if (_vwapDen <= 0) return;
            double nv = _vwapNum / _vwapDen;
            _vwapVar += vol * (tp - nv) * (tp - nv);
            _vwapPrice = nv;
            double sd = _vwapVar > 0 ? Math.Sqrt(_vwapVar / _vwapDen) : 0;
            _vwap1H = _vwapPrice + sd;   _vwap1L = _vwapPrice - sd;
            _vwap2H = _vwapPrice + 2*sd; _vwap2L = _vwapPrice - 2*sd;
        }

        private void UpdateInitialBalance(FootprintBar bar)
        {
            if (_ibConfirmed) return;
            if (_sessionBarCount <= 60)
            { if (bar.High > _ibHigh || _ibHigh == double.MinValue) _ibHigh = bar.High; if (bar.Low < _ibLow || _ibLow == double.MaxValue) _ibLow = bar.Low; }
            else if (_ibHigh > double.MinValue) _ibConfirmed = true;
        }

        private void DetectBullBearColumn(FootprintBar bar, int barIdx)
        {
            if (bar.Levels.Count < 6) return;
            bool allBull = true, allBear = true;
            foreach (var kv in bar.Levels) { long d = kv.Value.AskVol - kv.Value.BidVol; if (d <= 0) allBull = false; if (d >= 0) allBear = false; if (!allBull && !allBear) break; }
            int ct = allBull ? 1 : allBear ? -1 : 0;
            lock (_barsLock) { _barColumnType[barIdx] = ct; }
        }

        private void DetectStackedZones(FootprintBar bar, int barIdx)
        {
            if (bar.Levels.Count < 3) return;
            double ts = TickSize > 0 ? TickSize : 0.25;
            var zones = new List<StackedZone>();
            var prices = new List<double>(bar.Levels.Keys);
            int i = 0;
            while (i < prices.Count)
            {
                Cell c; if (!bar.Levels.TryGetValue(prices[i], out c)) { i++; continue; }
                int dir = CellDir(c, ImbalanceRatio);
                if (dir == 0) { i++; continue; }
                int run = 1; double ep = prices[i];
                for (int j = i + 1; j < prices.Count; j++)
                {
                    if (Math.Abs(prices[j] - prices[j-1] - ts) > ts * 0.1) break;
                    Cell nc; if (!bar.Levels.TryGetValue(prices[j], out nc)) break;
                    if (CellDir(nc, ImbalanceRatio) != dir) break;
                    run++; ep = prices[j];
                }
                if (run >= 3) zones.Add(new StackedZone { PriceLow = prices[i], PriceHigh = ep, Tier = run >= 7 ? 3 : run >= 5 ? 2 : 1, Direction = dir });
                i += run;
            }
            if (zones.Count > 0) lock (_barsLock) { _stackedZones[barIdx] = zones; }
        }

        private static int CellDir(Cell c, double thr)
        {
            if (c.AskVol > 0 && (double)c.AskVol / Math.Max(1.0, c.BidVol) >= thr) return +1;
            if (c.BidVol > 0 && (double)c.BidVol / Math.Max(1.0, c.AskVol) >= thr) return -1;
            return 0;
        }

        private void DetectUnfinishedAuctions(FootprintBar bar, int barIdx)
        {
            Cell hc; if (bar.Levels.TryGetValue(bar.High, out hc) && hc.AskVol > 0 && hc.BidVol > 0) _unfinishedAuctions[bar.High] = barIdx;
            Cell lc; if (bar.Levels.TryGetValue(bar.Low,  out lc) && lc.AskVol > 0 && lc.BidVol > 0) _unfinishedAuctions[bar.Low]  = barIdx;
            var rev = new List<double>(); foreach (var kv in _unfinishedAuctions) if (kv.Value < barIdx && kv.Key >= bar.Low && kv.Key <= bar.High) rev.Add(kv.Key); foreach (var k in rev) _unfinishedAuctions.Remove(k);
            var exp = new List<double>(); foreach (var kv in _unfinishedAuctions) if (barIdx - kv.Value > 100) exp.Add(kv.Key); foreach (var k in exp) _unfinishedAuctions.Remove(k);
        }

        private void DetectVolumeClimax(FootprintBar bar, int barIdx)
        {
            _nBarHighs.Enqueue(bar.High); _nBarLows.Enqueue(bar.Low);
            while (_nBarHighs.Count > NBarLookback) _nBarHighs.Dequeue();
            while (_nBarLows.Count  > NBarLookback) _nBarLows.Dequeue();
            if (_volEma <= 0 || _nBarHighs.Count < NBarLookback || bar.TotalVol <= _volEma * VolClimaxMultiplier) return;
            double hi = double.MinValue, lo = double.MaxValue;
            foreach (var h in _nBarHighs) if (h > hi) hi = h;
            foreach (var l in _nBarLows)  if (l < lo) lo = l;
            double mid = (bar.High + bar.Low) / 2.0;
            if      (bar.High >= hi && bar.Close < mid) lock (_barsLock) { _volumeClimaxBars[barIdx] = -1; }
            else if (bar.Low  <= lo && bar.Close > mid) lock (_barsLock) { _volumeClimaxBars[barIdx] = +1; }
        }

        // ════════════════════════════════════════════════════════════════════
        // SharpDX resource management
        // ════════════════════════════════════════════════════════════════════

        private static SolidColorBrush MakeFrozenBrush(Color c) { var b = new SolidColorBrush(c); if (b.CanFreeze) b.Freeze(); return b; }

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            _bidDx     = BidCellBrush.ToDxBrush(RenderTarget);
            _askDx     = AskCellBrush.ToDxBrush(RenderTarget);
            _textDx    = CellTextBrush.ToDxBrush(RenderTarget);
            _pocDx     = PocBrush.ToDxBrush(RenderTarget);
            _vahDx     = VahBrush.ToDxBrush(RenderTarget);
            _valDx     = ValBrush.ToDxBrush(RenderTarget);
            _wallBidDx = WallBidBrush.ToDxBrush(RenderTarget);
            _wallAskDx = WallAskBrush.ToDxBrush(RenderTarget);

            _anchorPocDx       = (SharpDX.Direct2D1.SolidColorBrush)AnchorPocBrush.ToDxBrush(RenderTarget);
            _anchorVaDx        = (SharpDX.Direct2D1.SolidColorBrush)AnchorVaBrush.ToDxBrush(RenderTarget);
            _anchorNakedDx     = (SharpDX.Direct2D1.SolidColorBrush)AnchorNakedBrush.ToDxBrush(RenderTarget);
            _anchorPwPocDx     = (SharpDX.Direct2D1.SolidColorBrush)AnchorPwPocBrush.ToDxBrush(RenderTarget);
            _anchorCompositeDx = (SharpDX.Direct2D1.SolidColorBrush)AnchorCompositeBrush.ToDxBrush(RenderTarget);

            _bgCoverDx      = MakeFrozenBrush(Color.FromRgb(0x0E, 0x10, 0x14)).ToDxBrush(RenderTarget);
            _pwAmberFillDx  = MakeFrozenBrush(Color.FromArgb(46,  0xFF, 0xB3, 0x00)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwCyanFillDx   = MakeFrozenBrush(Color.FromArgb(71,  0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwMagFillDx    = MakeFrozenBrush(Color.FromArgb(71,  0xFF, 0x38, 0xC8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwAeroCyanDx   = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwAeroMagentaDx= MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x38, 0xC8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwAeroWhiteDx  = MakeFrozenBrush(Color.FromArgb(255, 0xF2, 0xF4, 0xF8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwSectorPurpleDx= MakeFrozenBrush(Color.FromArgb(255, 0xA1, 0x00, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwTextSecondaryDx= MakeFrozenBrush(Color.FromArgb(255, 0x9B, 0xA3, 0xAE)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwTextTertiaryDx = MakeFrozenBrush(Color.FromArgb(255, 0x5A, 0x63, 0x6E)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwTextHaloDx     = MakeFrozenBrush(Color.FromArgb(230, 0x00, 0x00, 0x00)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _bullColumnFillDx = MakeFrozenBrush(Color.FromArgb(18,  0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _bearColumnFillDx = MakeFrozenBrush(Color.FromArgb(18,  0xFF, 0x38, 0xC8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _largeLotDotDx    = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0xFF, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _volumeClimaxDx   = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0xD6, 0x00)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _vwapLineDx       = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0xFF, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _vwapBand1Dx      = MakeFrozenBrush(Color.FromArgb(100, 0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _vwapBand2Dx      = MakeFrozenBrush(Color.FromArgb(45,  0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _ibLineDx         = MakeFrozenBrush(Color.FromArgb(230, 0xFF, 0x95, 0x00)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _stackedBuyZoneDx = MakeFrozenBrush(Color.FromArgb(180, 0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _stackedSellZoneDx= MakeFrozenBrush(Color.FromArgb(180, 0xFF, 0x38, 0xC8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _unfinishedLineDx = MakeFrozenBrush(Color.FromArgb(140, 0xFF, 0xD2, 0x3F)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

            // Score HUD brushes
            _hudBgDx     = MakeFrozenBrush(Color.FromArgb(199, 0x0E, 0x10, 0x14)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _hudTextDx   = MakeFrozenBrush(Color.FromArgb(255, 0xE8, 0xEA, 0xED)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _hudDimDx    = MakeFrozenBrush(Color.FromArgb(255, 0xB0, 0xB6, 0xBE)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _hudBorderDx = MakeFrozenBrush(Color.FromArgb(255, 0x26, 0x26, 0x33)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

            // Tier stripe brushes
            _tierALongDx  = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xE6, 0x76)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _tierAShortDx = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x17, 0x44)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _tierBLongDx  = MakeFrozenBrush(Color.FromArgb(255, 0x66, 0xBB, 0x6A)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _tierBShortDx = MakeFrozenBrush(Color.FromArgb(255, 0xEF, 0x53, 0x50)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _tierCLongDx  = MakeFrozenBrush(Color.FromArgb(130, 0x7C, 0xB3, 0x87)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _tierCShortDx = MakeFrozenBrush(Color.FromArgb(130, 0xB8, 0x7C, 0x82)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _tierNeutralDx= MakeFrozenBrush(Color.FromArgb(255, 0x8A, 0x92, 0x9E)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

            _dashStyle = new StrokeStyle(NinjaTrader.Core.Globals.D2DFactory, new StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Dash });
            _cellFont   = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", CellFontSize) { TextAlignment = TextAlignment.Center, ParagraphAlignment = ParagraphAlignment.Center };
            _labelFont  = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 9f) { TextAlignment = TextAlignment.Trailing, ParagraphAlignment = ParagraphAlignment.Center };
            _hudFont    = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", FontWeight.Bold, FontStyle.Normal, 14f) { TextAlignment = TextAlignment.Leading, ParagraphAlignment = ParagraphAlignment.Center };
            _hudSmallFont= new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI",  FontWeight.SemiBold, FontStyle.Normal, 10f) { TextAlignment = TextAlignment.Leading, ParagraphAlignment = ParagraphAlignment.Center };

            for (int hi = 0; hi < HeatmapSteps; hi++)
            {
                byte a = (byte)(10 + hi * 14);
                if (_heatmapPalette[hi] != null) { _heatmapPalette[hi].Dispose(); _heatmapPalette[hi] = null; }
                _heatmapPalette[hi] = MakeFrozenBrush(Color.FromArgb(a, 0xFF, 0xB3, 0x00)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            }
        }

        private void DisposeDx()
        {
            DisposeBrush(ref _bidDx); DisposeBrush(ref _askDx); DisposeBrush(ref _textDx);
            DisposeBrush(ref _pocDx); DisposeBrush(ref _vahDx); DisposeBrush(ref _valDx);
            DisposeBrush(ref _wallBidDx); DisposeBrush(ref _wallAskDx); DisposeBrush(ref _bgCoverDx);
            DisposeSB(ref _anchorPocDx); DisposeSB(ref _anchorVaDx); DisposeSB(ref _anchorNakedDx); DisposeSB(ref _anchorPwPocDx); DisposeSB(ref _anchorCompositeDx);
            DisposeSB(ref _pwAmberFillDx); DisposeSB(ref _pwCyanFillDx); DisposeSB(ref _pwMagFillDx);
            DisposeSB(ref _pwAeroCyanDx); DisposeSB(ref _pwAeroMagentaDx); DisposeSB(ref _pwAeroWhiteDx); DisposeSB(ref _pwSectorPurpleDx);
            DisposeSB(ref _pwTextSecondaryDx); DisposeSB(ref _pwTextTertiaryDx); DisposeSB(ref _pwTextHaloDx);
            DisposeSB(ref _bullColumnFillDx); DisposeSB(ref _bearColumnFillDx); DisposeSB(ref _largeLotDotDx); DisposeSB(ref _volumeClimaxDx);
            DisposeSB(ref _vwapLineDx); DisposeSB(ref _vwapBand1Dx); DisposeSB(ref _vwapBand2Dx); DisposeSB(ref _ibLineDx);
            DisposeSB(ref _stackedBuyZoneDx); DisposeSB(ref _stackedSellZoneDx); DisposeSB(ref _unfinishedLineDx);
            DisposeSB(ref _hudBgDx); DisposeSB(ref _hudTextDx); DisposeSB(ref _hudDimDx); DisposeSB(ref _hudBorderDx);
            DisposeSB(ref _tierALongDx); DisposeSB(ref _tierAShortDx); DisposeSB(ref _tierBLongDx); DisposeSB(ref _tierBShortDx);
            DisposeSB(ref _tierCLongDx); DisposeSB(ref _tierCShortDx); DisposeSB(ref _tierNeutralDx);
            if (_dashStyle != null) { _dashStyle.Dispose(); _dashStyle = null; }
            if (_cellFont    != null) { _cellFont.Dispose();    _cellFont    = null; }
            if (_labelFont   != null) { _labelFont.Dispose();   _labelFont   = null; }
            if (_hudFont     != null) { _hudFont.Dispose();     _hudFont     = null; }
            if (_hudSmallFont!= null) { _hudSmallFont.Dispose();_hudSmallFont= null; }
            for (int hi = 0; hi < HeatmapSteps; hi++) DisposeSB(ref _heatmapPalette[hi]);
        }

        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush b) { if (b != null) { b.Dispose(); b = null; } }
        private static void DisposeSB(ref SharpDX.Direct2D1.SolidColorBrush b) { if (b != null) { b.Dispose(); b = null; } }

        // ════════════════════════════════════════════════════════════════════
        // OnRender
        // ════════════════════════════════════════════════════════════════════

        protected override void OnRender(ChartControl cc, ChartScale cs)
        {
            if (IsInHitTest) return;
            if (RenderTarget == null || ChartBars == null || cc.Instrument == null || _cellFont == null) return;
            base.OnRender(cc, cs);
            RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

            double ts = cc.Instrument.MasterInstrument.TickSize;
            float panelLeft  = (float)ChartPanel.X;
            float panelRight = (float)(ChartPanel.X + ChartPanel.W);
            float panelTop   = (float)ChartPanel.Y;
            float panelBot   = panelTop + (float)ChartPanel.H;

            // Session level lines (behind cells)
            if (ShowVWAP && _vwapPrice > 0) RenderVwap(cs, panelLeft, panelRight, panelTop, panelBot);
            if (ShowInitialBalance && _ibHigh > double.MinValue) RenderIB(cs, panelLeft, panelRight);
            if (ShowUnfinishedAuctionLines && _unfinishedAuctions.Count > 0) RenderUnfinishedLines(cs, panelLeft, panelRight, panelTop, panelBot);
            if (ShowProfileAnchors) RenderProfileAnchors(cc, cs, panelLeft, panelRight);

            // L2 walls
            if (ShowLiquidityWalls) RenderL2Walls(cc, cs, panelLeft, panelRight);

            if (!ShowFootprintCells && !ShowPoc && !ShowValueArea) goto renderHud;

            int barPaintW = cc.GetBarPaintWidth(ChartBars);
            int colW = Math.Max(CellColumnWidth, barPaintW);
            float rowH = (float)Math.Max(8, cs.GetPixelsForDistance(ts));
            int fromIdx = ChartBars.FromIndex;
            int toIdx   = ChartBars.ToIndex;

            Dictionary<int, FootprintBar> snap;
            lock (_barsLock) { snap = new Dictionary<int, FootprintBar>(_bars); }

            for (int barIdx = fromIdx; barIdx <= toIdx; barIdx++)
            {
                FootprintBar fbar;
                if (!snap.TryGetValue(barIdx, out fbar) || fbar.Levels.Count == 0) continue;

                int xCenter = cc.GetXByBarIndex(ChartBars, barIdx);
                float xLeft = xCenter - colW / 2f;
                float xRight = xLeft + colW;

                // Cover underlying candle
                if (HideUnderlyingCandles && fbar.High > 0 && fbar.Low > 0 && _bgCoverDx != null)
                {
                    float yH = cs.GetYByValue(fbar.High + ts);
                    float yL = cs.GetYByValue(fbar.Low  - ts);
                    RenderTarget.FillRectangle(new RectangleF(xLeft - 2, yH, colW + 4, yL - yH), _bgCoverDx);
                }

                // VA band (behind cells)
                if (ShowValueArea && fbar.High > 0)
                {
                    var va = FootprintBar.ComputeValueArea(fbar, ts);
                    if (va.vah > 0 && va.val > 0 && _anchorCompositeDx != null)
                    {
                        float yVah = cs.GetYByValue(va.vah);
                        float yVal = cs.GetYByValue(va.val);
                        RenderTarget.FillRectangle(new RectangleF(xLeft, yVah, colW, yVal - yVah), _anchorCompositeDx);
                    }
                }

                // Bull/Bear column tint
                if (ShowBullBearColumn)
                {
                    int ct; lock (_barsLock) { _barColumnType.TryGetValue(barIdx, out ct); }
                    if (ct != 0 && fbar.High > 0)
                    {
                        var fill = ct > 0 ? _bullColumnFillDx : _bearColumnFillDx;
                        if (fill != null) RenderTarget.FillRectangle(new RectangleF(xLeft, cs.GetYByValue(fbar.High), colW, cs.GetYByValue(fbar.Low) - cs.GetYByValue(fbar.High)), fill);
                    }
                }

                // Cells
                if (ShowFootprintCells)
                {
                    long maxVol = 0;
                    foreach (var kv in fbar.Levels) { long v = kv.Value.AskVol + kv.Value.BidVol; if (v > maxVol) maxVol = v; }

                    HashSet<double> lotSet = null;
                    if (ShowLargeLotOverlay) lock (_barsLock) { _largeLotBars.TryGetValue(barIdx, out lotSet); }

                    foreach (var kv in fbar.Levels)
                    {
                        double px = kv.Key;
                        var cell = kv.Value;
                        float yCenter = cs.GetYByValue(px);
                        float yTop = yCenter - rowH / 2f;
                        var rect = new RectangleF(xLeft, yTop, colW, rowH);

                        // Heatmap
                        if (ShowHeatmapMode && maxVol > 0)
                        {
                            long cv = cell.AskVol + cell.BidVol;
                            int hIdx = Math.Max(0, Math.Min(HeatmapSteps-1, (int)((double)cv / maxVol * (HeatmapSteps-1))));
                            if (_heatmapPalette[hIdx] != null) RenderTarget.FillRectangle(rect, _heatmapPalette[hIdx]);
                        }

                        // Diagonal imbalance fill
                        long diagBid = GetBid(fbar, px + ts), diagAsk = GetAsk(fbar, px - ts);
                        double buyR  = cell.AskVol > 0 ? cell.AskVol / Math.Max(1.0, diagBid) : 0;
                        double sellR = cell.BidVol > 0 ? cell.BidVol / Math.Max(1.0, diagAsk) : 0;
                        SharpDX.Direct2D1.Brush fillBrush = null;
                        bool isExtreme = false, isBuyExt = false;
                        if      (buyR  >= 8.0) { fillBrush = _pwCyanFillDx;  isExtreme = true; isBuyExt = true; }
                        else if (buyR  >= 5.0)   fillBrush = _pwCyanFillDx;
                        else if (buyR  >= ImbalanceRatio) fillBrush = _pwAmberFillDx;
                        else if (sellR >= 8.0) { fillBrush = _pwMagFillDx;   isExtreme = true; isBuyExt = false; }
                        else if (sellR >= 5.0)   fillBrush = _pwMagFillDx;
                        else if (sellR >= ImbalanceRatio) fillBrush = _pwAmberFillDx;
                        if (fillBrush != null) RenderTarget.FillRectangle(rect, fillBrush);

                        // Cell text (suppressed if row too small)
                        if (rowH >= 8 && _cellFont != null)
                        {
                            var ink = isExtreme ? (SharpDX.Direct2D1.Brush)_pwAeroWhiteDx : (SharpDX.Direct2D1.Brush)_pwTextSecondaryDx;
                            string lbl = string.Format("{0,4} x {1,-4}", cell.BidVol, cell.AskVol);
                            using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, lbl, _cellFont, colW, rowH))
                                RenderTarget.DrawTextLayout(new Vector2(xLeft, yTop), tl, ink ?? _textDx);
                        }

                        // Extreme corner brackets
                        if (isExtreme)
                            DrawCornerBrackets(rect, isBuyExt ? (SharpDX.Direct2D1.Brush)_pwAeroCyanDx : (SharpDX.Direct2D1.Brush)_pwAeroMagentaDx, 5f, 1.5f);

                        // Large lot dot
                        if (lotSet != null && lotSet.Contains(px) && _largeLotDotDx != null)
                            RenderTarget.FillRectangle(new RectangleF(xLeft, yCenter - 2.5f, 5f, 5f), _largeLotDotDx);
                    }
                }

                // POC
                if (ShowPoc && fbar.PocPrice > 0)
                {
                    float yPoc = cs.GetYByValue(fbar.PocPrice);
                    RenderTarget.FillRectangle(new RectangleF(xLeft, yPoc - 1, colW, 2), _pwSectorPurpleDx ?? (SharpDX.Direct2D1.SolidColorBrush)_pocDx);
                }

                // VAH/VAL lines
                if (ShowValueArea)
                {
                    var va = FootprintBar.ComputeValueArea(fbar, ts);
                    if (va.vah > 0) RenderTarget.DrawLine(new Vector2(xLeft, cs.GetYByValue(va.vah)), new Vector2(xLeft + colW, cs.GetYByValue(va.vah)), _vahDx, 1f);
                    if (va.val > 0) RenderTarget.DrawLine(new Vector2(xLeft, cs.GetYByValue(va.val)), new Vector2(xLeft + colW, cs.GetYByValue(va.val)), _valDx, 1f);
                }

                // Stacked zone boxes
                if (ShowStackedZoneBoxes)
                {
                    List<StackedZone> zones; lock (_barsLock) { _stackedZones.TryGetValue(barIdx, out zones); }
                    if (zones != null) foreach (var z in zones)
                    {
                        float yT = cs.GetYByValue(z.PriceHigh + ts * 0.5f);
                        float yB = cs.GetYByValue(z.PriceLow  - ts * 0.5f);
                        float sw = z.Tier == 3 ? 2f : z.Tier == 2 ? 1.5f : 1f;
                        var zb = z.Direction > 0 ? _stackedBuyZoneDx : _stackedSellZoneDx;
                        if (zb != null) RenderTarget.DrawRectangle(new RectangleF(xLeft, yT, colW, yB - yT), zb, sw);
                    }
                }

                // Volume climax
                if (ShowVolumeClimax)
                {
                    int cd; lock (_barsLock) { _volumeClimaxBars.TryGetValue(barIdx, out cd); }
                    if (cd != 0 && _volumeClimaxDx != null)
                    {
                        float yExt = cs.GetYByValue(cd > 0 ? fbar.Low : fbar.High);
                        float off  = cd > 0 ? 2f : -2f;
                        RenderTarget.DrawLine(new Vector2(xLeft, yExt + off), new Vector2(xLeft + colW, yExt + off), _volumeClimaxDx, 2.5f);
                    }
                }

                // Score stripe — 4px right-edge bar colored by tier
                {
                    ScorerResult sr; lock (_barsLock) { _barScores.TryGetValue(barIdx, out sr); }
                    if (sr != null && sr.Tier != SignalTier.QUIET && sr.Tier != SignalTier.DISQUALIFIED && fbar.High > 0)
                    {
                        var stripeBrush = GetTierBrush(sr.Tier, sr.Direction);
                        if (stripeBrush != null)
                        {
                            float yH = cs.GetYByValue(fbar.High);
                            float yL = cs.GetYByValue(fbar.Low);
                            RenderTarget.FillRectangle(new RectangleF(xRight - 4f, yH, 4f, yL - yH), stripeBrush);
                        }
                    }
                }
            }

            renderHud:
            if (ShowScoreHud) RenderSlimHud(panelRight);
        }

        // ── Render helpers ────────────────────────────────────────────────────

        private SharpDX.Direct2D1.SolidColorBrush GetTierBrush(SignalTier tier, int dir)
        {
            if (tier == SignalTier.TYPE_A) return dir > 0 ? _tierALongDx : _tierAShortDx;
            if (tier == SignalTier.TYPE_B) return dir > 0 ? _tierBLongDx : _tierBShortDx;
            if (tier == SignalTier.TYPE_C) return dir > 0 ? _tierCLongDx : _tierCShortDx;
            return null;
        }

        private void RenderSlimHud(float panelRight)
        {
            var sr = _lastScore;
            if (sr == null || _hudFont == null) return;

            float x = panelRight - 120f;
            float y = (float)ChartPanel.Y + 10f;

            string scoreLine = string.Format("{0:F1}", sr.TotalScore);
            string tierLine  = sr.Narrative ?? sr.Tier.ToString();

            var bgRect = new RectangleF(x - 4, y - 2, 114f, 36f);
            if (_hudBgDx != null) RenderTarget.FillRectangle(bgRect, _hudBgDx);
            if (_hudBorderDx != null) RenderTarget.DrawRectangle(bgRect, _hudBorderDx, 1f);

            var tierColor = GetTierBrush(sr.Tier, sr.Direction) ?? _tierNeutralDx;
            if (tierColor != null) RenderTarget.FillRectangle(new RectangleF(x - 4, y - 2, 3f, 36f), tierColor);

            if (_hudTextDx != null)
                using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, scoreLine, _hudFont, 60f, 18f))
                    RenderTarget.DrawTextLayout(new Vector2(x, y), tl, _hudTextDx);

            if (_hudDimDx != null && _hudSmallFont != null)
            {
                string tier = sr.Tier == SignalTier.TYPE_A ? "TYPE A" : sr.Tier == SignalTier.TYPE_B ? "TYPE B" : sr.Tier == SignalTier.TYPE_C ? "TYPE C" : "QUIET";
                using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, tier, _hudSmallFont, 110f, 14f))
                    RenderTarget.DrawTextLayout(new Vector2(x, y + 18f), tl, tierColor ?? _hudDimDx);
            }
        }

        private void RenderVwap(ChartScale cs, float l, float r, float top, float bot)
        {
            if (_vwapLineDx == null || _vwapPrice <= 0) return;
            float y = cs.GetYByValue(_vwapPrice);
            if (y >= top && y <= bot) RenderTarget.DrawLine(new Vector2(l, y), new Vector2(r, y), _vwapLineDx, 1.5f);
            if (ShowVWAPBands && _vwapBand1Dx != null)
            {
                float y1h = cs.GetYByValue(_vwap1H), y1l = cs.GetYByValue(_vwap1L);
                if (y1h >= top && y1h <= bot) RenderTarget.DrawLine(new Vector2(l, y1h), new Vector2(r, y1h), _vwapBand1Dx, 1f, _dashStyle);
                if (y1l >= top && y1l <= bot) RenderTarget.DrawLine(new Vector2(l, y1l), new Vector2(r, y1l), _vwapBand1Dx, 1f, _dashStyle);
                if (_vwapBand2Dx != null)
                {
                    float y2h = cs.GetYByValue(_vwap2H), y2l = cs.GetYByValue(_vwap2L);
                    if (y2h >= top && y2h <= bot) RenderTarget.DrawLine(new Vector2(l, y2h), new Vector2(r, y2h), _vwapBand2Dx, 1f, _dashStyle);
                    if (y2l >= top && y2l <= bot) RenderTarget.DrawLine(new Vector2(l, y2l), new Vector2(r, y2l), _vwapBand2Dx, 1f, _dashStyle);
                }
            }
            if (_labelFont != null) using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, string.Format("VWAP {0:F2}", _vwapPrice), _labelFont, 90f, 14f)) RenderTarget.DrawTextLayout(new Vector2(r - 92f, y - 7f), tl, _vwapLineDx);
        }

        private void RenderIB(ChartScale cs, float l, float r)
        {
            if (_ibLineDx == null || _ibHigh <= double.MinValue) return;
            float yH = cs.GetYByValue(_ibHigh), yL = cs.GetYByValue(_ibLow);
            RenderTarget.DrawLine(new Vector2(l, yH), new Vector2(r, yH), _ibLineDx, 1.5f);
            RenderTarget.DrawLine(new Vector2(l, yL), new Vector2(r, yL), _ibLineDx, 1.5f);
            if (_labelFont != null)
            {
                using (var t1 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, "IBH", _labelFont, 30f, 14f)) RenderTarget.DrawTextLayout(new Vector2(r - 32f, yH - 7f), t1, _ibLineDx);
                using (var t2 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, "IBL", _labelFont, 30f, 14f)) RenderTarget.DrawTextLayout(new Vector2(r - 32f, yL - 7f), t2, _ibLineDx);
            }
        }

        private void RenderUnfinishedLines(ChartScale cs, float l, float r, float top, float bot)
        {
            if (_unfinishedLineDx == null) return;
            foreach (var kv in _unfinishedAuctions)
            {
                float y = cs.GetYByValue(kv.Key);
                if (y < top || y > bot) continue;
                RenderTarget.DrawLine(new Vector2(l, y), new Vector2(r - 12f, y), _unfinishedLineDx, 1f, _dashStyle);
            }
        }

        private void RenderProfileAnchors(ChartControl cc, ChartScale cs, float l, float r)
        {
            var snap = _profileAnchors.BuildSnapshot();
            if (snap == null || snap.Levels == null) return;
            float panelTop = (float)ChartPanel.Y;
            float panelBot = panelTop + (float)ChartPanel.H;

            foreach (var anch in snap.Levels)
            {
                if (anch == null || anch.Price <= 0) continue;
                float y = cs.GetYByValue(anch.Price);
                if (y < panelTop || y > panelBot) continue;

                SharpDX.Direct2D1.SolidColorBrush brush;
                float strokeW = 1f;
                bool dashed = false;
                string lbl = anch.Label ?? string.Empty;

                switch (anch.Kind)
                {
                    case NinjaTrader.NinjaScript.AddOns.DEEP6.Levels.ProfileAnchorKind.PriorDayPoc:
                        brush = _anchorPocDx; strokeW = 1.5f; break;
                    case NinjaTrader.NinjaScript.AddOns.DEEP6.Levels.ProfileAnchorKind.NakedPoc:
                        brush = _anchorNakedDx; dashed = true; break;
                    case NinjaTrader.NinjaScript.AddOns.DEEP6.Levels.ProfileAnchorKind.PriorWeekPoc:
                        brush = _anchorPwPocDx; dashed = true; break;
                    case NinjaTrader.NinjaScript.AddOns.DEEP6.Levels.ProfileAnchorKind.CompositeVah:
                    case NinjaTrader.NinjaScript.AddOns.DEEP6.Levels.ProfileAnchorKind.CompositeVal:
                        brush = _anchorCompositeDx; dashed = true; break;
                    default:
                        brush = _anchorVaDx; break;
                }
                if (brush == null) continue;
                RenderTarget.DrawLine(new Vector2(l, y), new Vector2(r, y), brush, strokeW, dashed ? _dashStyle : null);
                if (_labelFont != null && !string.IsNullOrEmpty(lbl))
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, lbl, _labelFont, 80f, 14f))
                        RenderTarget.DrawTextLayout(new Vector2(r - 82f, y - 7f), tl, brush);
            }

            // Composite VA band fill
            if (snap.CompositeVah.HasValue && snap.CompositeVal.HasValue && _anchorCompositeDx != null)
            {
                float yVah = cs.GetYByValue(snap.CompositeVah.Value);
                float yVal = cs.GetYByValue(snap.CompositeVal.Value);
                RenderTarget.FillRectangle(new RectangleF(l, yVah, r - l, yVal - yVah), _anchorCompositeDx);
            }
        }

        private void RenderL2Walls(ChartControl cc, ChartScale cs, float l, float r)
        {
            Dictionary<double, L2LevelState> bidSnap, askSnap;
            lock (_l2Lock) { bidSnap = new Dictionary<double, L2LevelState>(_l2Bids); askSnap = new Dictionary<double, L2LevelState>(_l2Asks); }
            float panelTop = (float)ChartPanel.Y, panelBot = panelTop + (float)ChartPanel.H;
            var cutoff = DateTime.UtcNow.AddSeconds(-LiquidityWallStaleSec);
            int threshold = LiquidityWallMin;

            RenderWallSide(cs, bidSnap, _wallBidDx, l, r, panelTop, panelBot, cutoff, threshold, true);
            RenderWallSide(cs, askSnap, _wallAskDx, l, r, panelTop, panelBot, cutoff, threshold, false);
        }

        private void RenderWallSide(ChartScale cs, Dictionary<double, L2LevelState> dict,
            SharpDX.Direct2D1.Brush brush, float l, float r, float top, float bot,
            DateTime cutoff, int threshold, bool isBid)
        {
            if (brush == null) return;
            var walls = new List<(double price, long sz, int refills)>();
            foreach (var kv in dict)
                if (kv.Value.CurrentSize >= threshold && kv.Value.LastUpdate >= cutoff)
                    walls.Add((kv.Key, kv.Value.CurrentSize, kv.Value.RefillCount));
            walls.Sort((a, b) => b.sz.CompareTo(a.sz));
            int drawn = 0;
            foreach (var w in walls)
            {
                if (drawn >= LiquidityMaxPerSide) break;
                float y = cs.GetYByValue(w.price);
                if (y < top || y > bot) continue;
                float sw = Math.Min(4f, 1.5f + (float)w.sz / threshold * 0.5f);
                RenderTarget.DrawLine(new Vector2(l, y), new Vector2(r, y), brush, sw);
                if (_labelFont != null)
                {
                    string lbl = w.refills > 0 ? string.Format("{0} ICE×{1}", w.sz, w.refills) : w.sz.ToString();
                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, lbl, _labelFont, 80f, 14f))
                        RenderTarget.DrawTextLayout(new Vector2(r - 82f, y - 7f), tl, brush);
                }
                drawn++;
            }
        }

        private void DrawCornerBrackets(RectangleF r, SharpDX.Direct2D1.Brush b, float leg, float sw)
        {
            if (b == null) return;
            RenderTarget.DrawLine(new Vector2(r.Left, r.Top),    new Vector2(r.Left + leg, r.Top),    b, sw);
            RenderTarget.DrawLine(new Vector2(r.Left, r.Top),    new Vector2(r.Left, r.Top + leg),    b, sw);
            RenderTarget.DrawLine(new Vector2(r.Right, r.Top),   new Vector2(r.Right - leg, r.Top),   b, sw);
            RenderTarget.DrawLine(new Vector2(r.Right, r.Top),   new Vector2(r.Right, r.Top + leg),   b, sw);
            RenderTarget.DrawLine(new Vector2(r.Left, r.Bottom), new Vector2(r.Left + leg, r.Bottom), b, sw);
            RenderTarget.DrawLine(new Vector2(r.Left, r.Bottom), new Vector2(r.Left, r.Bottom - leg), b, sw);
            RenderTarget.DrawLine(new Vector2(r.Right, r.Bottom),new Vector2(r.Right - leg, r.Bottom),b, sw);
            RenderTarget.DrawLine(new Vector2(r.Right, r.Bottom),new Vector2(r.Right, r.Bottom - leg),b, sw);
        }

        private static long GetBid(FootprintBar bar, double price) { Cell c; return bar.Levels.TryGetValue(price, out c) ? c.BidVol : 0; }
        private static long GetAsk(FootprintBar bar, double price) { Cell c; return bar.Levels.TryGetValue(price, out c) ? c.AskVol : 0; }

        // ════════════════════════════════════════════════════════════════════
        // Properties
        // ════════════════════════════════════════════════════════════════════

        #region Properties

        // ── Group 1: Footprint Cells ──────────────────────────────────────

        [NinjaScriptProperty]
        [Range(1.0, 10.0)]
        [Display(Name = "Imbalance Ratio", Order = 1, GroupName = "1. Footprint Cells")]
        public double ImbalanceRatio { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Footprint Cells", Order = 2, GroupName = "1. Footprint Cells")]
        public bool ShowFootprintCells { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show POC", Order = 3, GroupName = "1. Footprint Cells")]
        public bool ShowPoc { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Value Area", Order = 4, GroupName = "1. Footprint Cells")]
        public bool ShowValueArea { get; set; }

        [NinjaScriptProperty]
        [Range(6f, 14f)]
        [Display(Name = "Cell Font Size", Order = 5, GroupName = "1. Footprint Cells")]
        public float CellFontSize { get; set; }

        [NinjaScriptProperty]
        [Range(40, 300)]
        [Display(Name = "Cell Column Width (px)", Order = 6, GroupName = "1. Footprint Cells")]
        public int CellColumnWidth { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Hide Underlying Candles", Order = 7, GroupName = "1. Footprint Cells",
                 Description = "Paint over OHLC candles so the footprint IS the chart")]
        public bool HideUnderlyingCandles { get; set; }

        // ── Group 2: Session Levels ───────────────────────────────────────

        [NinjaScriptProperty]
        [Display(Name = "Show VWAP", Order = 1, GroupName = "2. Session Levels")]
        public bool ShowVWAP { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show VWAP Bands (±1σ/±2σ)", Order = 2, GroupName = "2. Session Levels")]
        public bool ShowVWAPBands { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Initial Balance", Order = 3, GroupName = "2. Session Levels")]
        public bool ShowInitialBalance { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Profile Anchors", Order = 4, GroupName = "2. Session Levels")]
        public bool ShowProfileAnchors { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Prior-Day Levels", Order = 5, GroupName = "2. Session Levels")]
        public bool ShowPriorDayLevels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Naked POCs", Order = 6, GroupName = "2. Session Levels")]
        public bool ShowNakedPocs { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Naked POC Max Age (sessions)", Order = 7, GroupName = "2. Session Levels")]
        public int NakedPocMaxAgeSessions { get; set; }

        // ── Group 3: Volume Patterns ──────────────────────────────────────

        [NinjaScriptProperty]
        [Display(Name = "Show Heatmap Mode", Order = 1, GroupName = "3. Volume Patterns")]
        public bool ShowHeatmapMode { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Stacked Zone Boxes", Order = 2, GroupName = "3. Volume Patterns")]
        public bool ShowStackedZoneBoxes { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Unfinished Auction Lines", Order = 3, GroupName = "3. Volume Patterns")]
        public bool ShowUnfinishedAuctionLines { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Large Lot Overlay", Order = 4, GroupName = "3. Volume Patterns")]
        public bool ShowLargeLotOverlay { get; set; }

        [NinjaScriptProperty]
        [Range(10, 500)]
        [Display(Name = "Large Lot Threshold (contracts)", Order = 5, GroupName = "3. Volume Patterns")]
        public int LargeLotThreshold { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Bull/Bear Column Tint", Order = 6, GroupName = "3. Volume Patterns")]
        public bool ShowBullBearColumn { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Volume Climax Markers", Order = 7, GroupName = "3. Volume Patterns")]
        public bool ShowVolumeClimax { get; set; }

        [NinjaScriptProperty]
        [Range(1.5, 5.0)]
        [Display(Name = "Volume Climax Multiplier", Order = 8, GroupName = "3. Volume Patterns")]
        public double VolClimaxMultiplier { get; set; }

        // ── Group 4: Liquidity Walls ──────────────────────────────────────

        [NinjaScriptProperty]
        [Display(Name = "Show Liquidity Walls", Order = 1, GroupName = "4. Liquidity (L2)")]
        public bool ShowLiquidityWalls { get; set; }

        [NinjaScriptProperty]
        [Range(10, 5000)]
        [Display(Name = "Wall Min Size (contracts)", Order = 2, GroupName = "4. Liquidity (L2)")]
        public int LiquidityWallMin { get; set; }

        [NinjaScriptProperty]
        [Range(10, 600)]
        [Display(Name = "Wall Stale (seconds)", Order = 3, GroupName = "4. Liquidity (L2)")]
        public int LiquidityWallStaleSec { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Max Walls Per Side", Order = 4, GroupName = "4. Liquidity (L2)")]
        public int LiquidityMaxPerSide { get; set; }

        // ── Group 5: Scoring HUD ──────────────────────────────────────────

        [NinjaScriptProperty]
        [Display(Name = "Show Score HUD", Order = 1, GroupName = "5. Scoring")]
        public bool ShowScoreHud { get; set; }

        // ── Brush properties ──────────────────────────────────────────────

        [XmlIgnore] [Display(Name = "Bid Cell Color", Order = 10, GroupName = "6. Colors")]
        public Brush BidCellBrush { get; set; }
        [Browsable(false)] public string BidCellBrushSerialize { get { return Serialize.BrushToString(BidCellBrush); } set { BidCellBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Ask Cell Color", Order = 11, GroupName = "6. Colors")]
        public Brush AskCellBrush { get; set; }
        [Browsable(false)] public string AskCellBrushSerialize { get { return Serialize.BrushToString(AskCellBrush); } set { AskCellBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Cell Text Color", Order = 12, GroupName = "6. Colors")]
        public Brush CellTextBrush { get; set; }
        [Browsable(false)] public string CellTextBrushSerialize { get { return Serialize.BrushToString(CellTextBrush); } set { CellTextBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "POC Color", Order = 13, GroupName = "6. Colors")]
        public Brush PocBrush { get; set; }
        [Browsable(false)] public string PocBrushSerialize { get { return Serialize.BrushToString(PocBrush); } set { PocBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "VAH Color", Order = 14, GroupName = "6. Colors")]
        public Brush VahBrush { get; set; }
        [Browsable(false)] public string VahBrushSerialize { get { return Serialize.BrushToString(VahBrush); } set { VahBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "VAL Color", Order = 15, GroupName = "6. Colors")]
        public Brush ValBrush { get; set; }
        [Browsable(false)] public string ValBrushSerialize { get { return Serialize.BrushToString(ValBrush); } set { ValBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Wall Bid Color", Order = 20, GroupName = "6. Colors")]
        public Brush WallBidBrush { get; set; }
        [Browsable(false)] public string WallBidBrushSerialize { get { return Serialize.BrushToString(WallBidBrush); } set { WallBidBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Wall Ask Color", Order = 21, GroupName = "6. Colors")]
        public Brush WallAskBrush { get; set; }
        [Browsable(false)] public string WallAskBrushSerialize { get { return Serialize.BrushToString(WallAskBrush); } set { WallAskBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Anchor POC Color",       Order = 30, GroupName = "6. Colors")]
        public Brush AnchorPocBrush { get; set; }
        [Browsable(false)] public string AnchorPocBrushSerialize { get { return Serialize.BrushToString(AnchorPocBrush); } set { AnchorPocBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Anchor VA Color",        Order = 31, GroupName = "6. Colors")]
        public Brush AnchorVaBrush { get; set; }
        [Browsable(false)] public string AnchorVaBrushSerialize { get { return Serialize.BrushToString(AnchorVaBrush); } set { AnchorVaBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Anchor Naked POC Color", Order = 32, GroupName = "6. Colors")]
        public Brush AnchorNakedBrush { get; set; }
        [Browsable(false)] public string AnchorNakedBrushSerialize { get { return Serialize.BrushToString(AnchorNakedBrush); } set { AnchorNakedBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Anchor PW POC Color",   Order = 33, GroupName = "6. Colors")]
        public Brush AnchorPwPocBrush { get; set; }
        [Browsable(false)] public string AnchorPwPocBrushSerialize { get { return Serialize.BrushToString(AnchorPwPocBrush); } set { AnchorPwPocBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore] [Display(Name = "Anchor Composite VA",   Order = 34, GroupName = "6. Colors")]
        public Brush AnchorCompositeBrush { get; set; }
        [Browsable(false)] public string AnchorCompositeBrushSerialize { get { return Serialize.BrushToString(AnchorCompositeBrush); } set { AnchorCompositeBrush = Serialize.StringToBrush(value); } }

        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6.DEEP6FootprintChart[] cacheDEEP6FootprintChart;
        public DEEP6.DEEP6FootprintChart DEEP6FootprintChart(double imbalanceRatio, bool showFootprintCells, bool showPoc, bool showValueArea, float cellFontSize, int cellColumnWidth, bool hideUnderlyingCandles, bool showVWAP, bool showVWAPBands, bool showInitialBalance, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, int nakedPocMaxAgeSessions, bool showHeatmapMode, bool showStackedZoneBoxes, bool showUnfinishedAuctionLines, bool showLargeLotOverlay, int largeLotThreshold, bool showBullBearColumn, bool showVolumeClimax, double volClimaxMultiplier, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showScoreHud)
        {
            return DEEP6FootprintChart(Input, imbalanceRatio, showFootprintCells, showPoc, showValueArea, cellFontSize, cellColumnWidth, hideUnderlyingCandles, showVWAP, showVWAPBands, showInitialBalance, showProfileAnchors, showPriorDayLevels, showNakedPocs, nakedPocMaxAgeSessions, showHeatmapMode, showStackedZoneBoxes, showUnfinishedAuctionLines, showLargeLotOverlay, largeLotThreshold, showBullBearColumn, showVolumeClimax, volClimaxMultiplier, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showScoreHud);
        }

        public DEEP6.DEEP6FootprintChart DEEP6FootprintChart(ISeries<double> input, double imbalanceRatio, bool showFootprintCells, bool showPoc, bool showValueArea, float cellFontSize, int cellColumnWidth, bool hideUnderlyingCandles, bool showVWAP, bool showVWAPBands, bool showInitialBalance, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, int nakedPocMaxAgeSessions, bool showHeatmapMode, bool showStackedZoneBoxes, bool showUnfinishedAuctionLines, bool showLargeLotOverlay, int largeLotThreshold, bool showBullBearColumn, bool showVolumeClimax, double volClimaxMultiplier, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showScoreHud)
        {
            if (cacheDEEP6FootprintChart != null)
                for (int idx = 0; idx < cacheDEEP6FootprintChart.Length; idx++)
                    if (cacheDEEP6FootprintChart[idx] != null
                        && cacheDEEP6FootprintChart[idx].ImbalanceRatio == imbalanceRatio
                        && cacheDEEP6FootprintChart[idx].ShowFootprintCells == showFootprintCells
                        && cacheDEEP6FootprintChart[idx].CellColumnWidth == cellColumnWidth
                        && cacheDEEP6FootprintChart[idx].EqualsInput(input))
                        return cacheDEEP6FootprintChart[idx];
            return CacheIndicator<DEEP6.DEEP6FootprintChart>(new DEEP6.DEEP6FootprintChart()
            {
                ImbalanceRatio = imbalanceRatio, ShowFootprintCells = showFootprintCells,
                ShowPoc = showPoc, ShowValueArea = showValueArea, CellFontSize = cellFontSize,
                CellColumnWidth = cellColumnWidth, HideUnderlyingCandles = hideUnderlyingCandles,
                ShowVWAP = showVWAP, ShowVWAPBands = showVWAPBands, ShowInitialBalance = showInitialBalance,
                ShowProfileAnchors = showProfileAnchors, ShowPriorDayLevels = showPriorDayLevels,
                ShowNakedPocs = showNakedPocs, NakedPocMaxAgeSessions = nakedPocMaxAgeSessions,
                ShowHeatmapMode = showHeatmapMode, ShowStackedZoneBoxes = showStackedZoneBoxes,
                ShowUnfinishedAuctionLines = showUnfinishedAuctionLines, ShowLargeLotOverlay = showLargeLotOverlay,
                LargeLotThreshold = largeLotThreshold, ShowBullBearColumn = showBullBearColumn,
                ShowVolumeClimax = showVolumeClimax, VolClimaxMultiplier = volClimaxMultiplier,
                ShowLiquidityWalls = showLiquidityWalls, LiquidityWallMin = liquidityWallMin,
                LiquidityWallStaleSec = liquidityWallStaleSec, LiquidityMaxPerSide = liquidityMaxPerSide,
                ShowScoreHud = showScoreHud
            }, input, ref cacheDEEP6FootprintChart);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6.DEEP6FootprintChart DEEP6FootprintChart(double imbalanceRatio, bool showFootprintCells, bool showPoc, bool showValueArea, float cellFontSize, int cellColumnWidth, bool hideUnderlyingCandles, bool showVWAP, bool showVWAPBands, bool showInitialBalance, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, int nakedPocMaxAgeSessions, bool showHeatmapMode, bool showStackedZoneBoxes, bool showUnfinishedAuctionLines, bool showLargeLotOverlay, int largeLotThreshold, bool showBullBearColumn, bool showVolumeClimax, double volClimaxMultiplier, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showScoreHud)
        { return indicator.DEEP6FootprintChart(Input, imbalanceRatio, showFootprintCells, showPoc, showValueArea, cellFontSize, cellColumnWidth, hideUnderlyingCandles, showVWAP, showVWAPBands, showInitialBalance, showProfileAnchors, showPriorDayLevels, showNakedPocs, nakedPocMaxAgeSessions, showHeatmapMode, showStackedZoneBoxes, showUnfinishedAuctionLines, showLargeLotOverlay, largeLotThreshold, showBullBearColumn, showVolumeClimax, volClimaxMultiplier, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showScoreHud); }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.DEEP6.DEEP6FootprintChart DEEP6FootprintChart(double imbalanceRatio, bool showFootprintCells, bool showPoc, bool showValueArea, float cellFontSize, int cellColumnWidth, bool hideUnderlyingCandles, bool showVWAP, bool showVWAPBands, bool showInitialBalance, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, int nakedPocMaxAgeSessions, bool showHeatmapMode, bool showStackedZoneBoxes, bool showUnfinishedAuctionLines, bool showLargeLotOverlay, int largeLotThreshold, bool showBullBearColumn, bool showVolumeClimax, double volClimaxMultiplier, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showScoreHud)
        { return indicator.DEEP6FootprintChart(Input, imbalanceRatio, showFootprintCells, showPoc, showValueArea, cellFontSize, cellColumnWidth, hideUnderlyingCandles, showVWAP, showVWAPBands, showInitialBalance, showProfileAnchors, showPriorDayLevels, showNakedPocs, nakedPocMaxAgeSessions, showHeatmapMode, showStackedZoneBoxes, showUnfinishedAuctionLines, showLargeLotOverlay, largeLotThreshold, showBullBearColumn, showVolumeClimax, volClimaxMultiplier, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showScoreHud); }
    }
}
#endregion
