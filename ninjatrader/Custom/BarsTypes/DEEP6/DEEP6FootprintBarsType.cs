// DEEP6 Footprint Bars Type — 5-minute footprint bars for NQ futures.
//
// Appears in Data Series → Type dropdown as "DEEP6 Footprint".
// Set DefaultChartStyle = (ChartStyleType)100 to auto-select DEEP6FootprintStyle.
//
// Data flow:
//   OnDataPoint (data thread) → accumulates ticks into FootprintBar
//   FinalizeAndPublish (data thread) → scores bar, publishes to FootprintSharedState
//   DEEP6FootprintStyle.OnRender (render thread) → reads snapshot from FootprintSharedState
//
// CRITICAL: Namespace must be NinjaTrader.NinjaScript.BarsTypes (no DEEP6 sub-namespace)
//           or NT8 will not discover this type in the dropdown.

#region Using
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Levels;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;
#endregion

namespace NinjaTrader.NinjaScript.BarsTypes
{
    public class DEEP6FootprintBarsType : BarsType
    {
        // ── Tick accumulation ─────────────────────────────────────────────────
        private readonly Dictionary<int, FootprintBar> _bars = new Dictionary<int, FootprintBar>();
        private FootprintBar _currentBar;
        private int          _currentBarIdx = -1;
        private long         _priorCvd;
        private FootprintBar _priorFinalized;

        // Bid/Ask tracking for aggressor classification
        private double _bestBid = double.NaN;
        private double _bestAsk = double.NaN;

        // ── Session tracking ───────────────────────────────────────────────────
        private DateTime _lastSessionDate = DateTime.MinValue;
        private int      _sessionBarCount;

        // ── Rolling ATR / Vol EMA ──────────────────────────────────────────────
        private readonly Queue<double> _atrWindow = new Queue<double>();
        private const int AtrPeriod = 20;
        private double _atr    = 1.0;
        private double _volEma;
        private const double VolEmaAlpha = 2.0 / (AtrPeriod + 1.0);

        // ── Instrument name (populated from first OnDataPoint bars parameter) ────
        // BarsType does not have an Instrument property — access via bars.Instrument
        private string _instrumentName = string.Empty;

        // ── Scoring pipeline ───────────────────────────────────────────────────
        private DetectorRegistry _registry;
        private SessionContext   _session;

        // ── Profile anchors ────────────────────────────────────────────────────
        private ProfileAnchorLevels _profileAnchors = new ProfileAnchorLevels();
        private DateTime _profileSessionDate = DateTime.MinValue;

        // ── VWAP (incremental per session) ─────────────────────────────────────
        private double _vwapNum, _vwapDen, _vwapVar;
        private double _vwapPrice, _vwap1H, _vwap1L, _vwap2H, _vwap2L;

        // ── Initial Balance ────────────────────────────────────────────────────
        private double _ibHigh = double.MinValue;
        private double _ibLow  = double.MaxValue;
        private bool   _ibConfirmed;

        // ── Per-bar classifications ────────────────────────────────────────────
        private readonly Dictionary<int, int>                      _barColumnType    = new Dictionary<int, int>();
        private readonly Dictionary<int, List<StackedZone>>        _stackedZones     = new Dictionary<int, List<StackedZone>>();
        private readonly Dictionary<double, int>                   _unfinishedAuctions = new Dictionary<double, int>();
        private readonly Dictionary<int, HashSet<double>>          _largeLotBars     = new Dictionary<int, HashSet<double>>();
        private readonly Dictionary<int, int>                      _volumeClimaxBars = new Dictionary<int, int>();
        private readonly Queue<double> _nBarHighs = new Queue<double>();
        private readonly Queue<double> _nBarLows  = new Queue<double>();
        private const int NBarLookback = 20;

        // ── L2 walls ───────────────────────────────────────────────────────────
        private sealed class L2State
        {
            public long CurrentSize, MaxSize;
            public DateTime LastUpdate;
            public int RefillCount;
        }
        private readonly Dictionary<double, L2State> _l2Bids = new Dictionary<double, L2State>();
        private readonly Dictionary<double, L2State> _l2Asks = new Dictionary<double, L2State>();
        private DateTime _lastL2Prune = DateTime.MinValue;

        // ════════════════════════════════════════════════════════════════════════
        // Lifecycle
        // ════════════════════════════════════════════════════════════════════════

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name              = "DEEP6 Footprint";
                BarsPeriod        = new BarsPeriod { BarsPeriodType = BarsPeriodType.Minute, Value = 5 };
                BuiltFrom         = BarsPeriodType.Minute;
                DaysToLoad        = 5;
                WeeksToLoad       = 1;
                IsIntraday        = true;
                IsTimeBased       = true;
                DefaultChartStyle = (ChartStyleType)100;

                // User-configurable detection parameters
                ImbalanceRatio        = 3.0;
                LargeLotThreshold     = 50;
                NakedPocMaxAgeSessions= 20;
                VolClimaxMultiplier   = 2.5;
                LiquidityWallMin      = 100;
                LiquidityWallStaleSec = 90;
            }
            else if (State == State.Configure)
            {
                // Remove unused BarsPeriod UI fields
                Properties.Remove(Properties.Find("BaseBarsPeriodType", true));
                Properties.Remove(Properties.Find("BaseBarsPeriodValue", true));
                Properties.Remove(Properties.Find("PointAndFigurePriceType", true));
                Properties.Remove(Properties.Find("ReversalType", true));
                Properties.Remove(Properties.Find("Value2", true));

                // Build scoring pipeline
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

                _session = new SessionContext { TickSize = 0.25 };
            }
            else if (State == State.DataLoaded)
            {
                // _instrumentName and TickSize are populated from bars.Instrument on first OnDataPoint tick.
                // Reset state here; instrument-specific init deferred to first tick.
                if (_session != null) _session.TickSize = 0.25;
                _profileAnchors.TickSize = 0.25;
                _profileAnchors.NakedPocMaxAgeSessions = NakedPocMaxAgeSessions;
                _profileAnchors.Reset();
                _profileSessionDate = DateTime.MinValue;
                _bars.Clear();
                _currentBar = null;
                _currentBarIdx = -1;
                _priorCvd = 0;
                _priorFinalized = null;
                _atrWindow.Clear();
                _volEma = 0;
                ResetSessionV2();
                if (!string.IsNullOrEmpty(_instrumentName)) FootprintSharedState.Clear(_instrumentName);
            }
            else if (State == State.Terminated)
            {
                if (!string.IsNullOrEmpty(_instrumentName)) FootprintSharedState.Clear(_instrumentName);
            }
        }

        // ════════════════════════════════════════════════════════════════════════
        // Tick intake — the hot path
        // ════════════════════════════════════════════════════════════════════════

        protected override void OnDataPoint(Bars bars, double open, double high, double low, double close,
            DateTime time, long volume, bool isBar, double bid, double ask)
        {
            // Populate instrument name from bars on first tick (BarsType has no Instrument property)
            if (string.IsNullOrEmpty(_instrumentName) && bars?.Instrument != null)
            {
                _instrumentName = bars.Instrument.FullName;
                double ts = bars.Instrument.MasterInstrument.TickSize;
                if (_session != null) _session.TickSize = ts;
                _profileAnchors.TickSize = ts;
            }

            // SessionIterator tracks session boundaries (inherited from BarsType)
            SessionIterator ??= new SessionIterator(bars);
            bool isNewSession = SessionIterator.IsNewSession(time, isBar);
            if (isNewSession) SessionIterator.GetNextSession(time, isBar);

            // Track best bid/ask for aggressor classification
            if (bid > 0) _bestBid = bid;
            if (ask > 0) _bestAsk = ask;

            // Classify aggressor side
            int aggressor = 0;
            if (!double.IsNaN(_bestAsk) && close >= _bestAsk) aggressor = 1;       // buy aggressor
            else if (!double.IsNaN(_bestBid) && close <= _bestBid) aggressor = 2;  // sell aggressor

            // Large lot tracking (hot path — do before bar boundary check)
            if (LargeLotThreshold > 0 && volume >= LargeLotThreshold && _currentBarIdx >= 0)
            {
                HashSet<double> s;
                if (!_largeLotBars.TryGetValue(_currentBarIdx, out s))
                { s = new HashSet<double>(); _largeLotBars[_currentBarIdx] = s; }
                s.Add(close);
            }

            // ── Bar boundary logic (mirrors @MinuteBarsType.cs) ────────────────
            if (bars.Count == 0)
            {
                DateTime barTime = TimeToBarTime(bars, time, isBar);
                AddBar(bars, open, high, low, close, barTime, volume);
                _currentBarIdx = 0;
                _currentBar = new FootprintBar { BarIndex = 0 };
                _currentBar.AddTrade(close, volume, aggressor);
                _bars[0] = _currentBar;
            }
            else if (!isBar && time < bars.LastBarTime)
            {
                // Normal intrabar tick — update existing bar
                UpdateBar(bars, high, low, close, bars.LastBarTime, volume);
                _currentBar?.AddTrade(close, volume, aggressor);
            }
            else
            {
                // Bar boundary crossed: finalize current bar, start new
                if (_currentBar != null && _currentBarIdx >= 0)
                    FinalizeAndPublish(bars, _currentBarIdx);

                // Session boundary handling
                if (isNewSession) HandleSessionBoundary(time);
                else _sessionBarCount++;

                DateTime newBarTime = TimeToBarTime(bars, time, isBar);
                AddBar(bars, open, high, low, close, newBarTime, volume);
                int newIdx = bars.Count - 1;
                _currentBarIdx = newIdx;
                _currentBar = new FootprintBar { BarIndex = newIdx };
                _currentBar.AddTrade(close, volume, aggressor);
                _bars[newIdx] = _currentBar;

                // Prune old bars
                int cutoff = newIdx - 500;
                if (cutoff > 0)
                {
                    var stale = new List<int>();
                    foreach (var k in _bars.Keys) if (k < cutoff) stale.Add(k);
                    foreach (var k in stale)
                    {
                        _bars.Remove(k);
                        _barColumnType.Remove(k);
                        _stackedZones.Remove(k);
                        _largeLotBars.Remove(k);
                        _volumeClimaxBars.Remove(k);
                    }
                }
            }
        }

        // Note: OnMarketDepth is not overridable in BarsType.
        // L2 wall data is tracked via a separate DEEP6GexLevels-style indicator if needed.
        // The _l2Bids/_l2Asks dictionaries remain empty — the ChartStyle will show no wall data
        // from the BarsType itself. A future enhancement can bridge L2 data via a separate static.

        // ════════════════════════════════════════════════════════════════════════
        // Bar finalization and publishing
        // ════════════════════════════════════════════════════════════════════════

        private void FinalizeAndPublish(Bars bars, int barIdx)
        {
            var bar = _currentBar;
            if (bar == null) return;

            // Reconcile OHLC with NT8's authoritative values
            if (barIdx < bars.Count)
            {
                bar.Open  = bars.GetOpen(barIdx);
                bar.High  = bars.GetHigh(barIdx);
                bar.Low   = bars.GetLow(barIdx);
                bar.Close = bars.GetClose(barIdx);
            }

            bar.Finalize(_priorCvd);
            _priorCvd = bar.Cvd;

            // ATR / VolEMA
            _atrWindow.Enqueue(bar.BarRange);
            while (_atrWindow.Count > AtrPeriod) _atrWindow.Dequeue();
            double atrSum = 0; foreach (var v in _atrWindow) atrSum += v;
            _atr    = _atrWindow.Count == 0 ? 1.0 : System.Math.Max(atrSum / _atrWindow.Count, 0.25);
            _volEma = _volEma == 0 ? bar.TotalVol : _volEma + VolEmaAlpha * (bar.TotalVol - _volEma);

            // V2 computations
            UpdateVwap(bar);
            UpdateInitialBalance(bar);
            DetectBullBearColumn(bar, barIdx);
            DetectStackedZones(bar, barIdx);
            DetectUnfinishedAuctions(bar, barIdx);
            DetectVolumeClimax(bar, barIdx);

            // Profile anchors
            if (barIdx < bars.Count)
            {
                DateTime bt = bars.GetTime(barIdx);
                if (_profileSessionDate == DateTime.MinValue) _profileSessionDate = bt.Date;
                if (bt.Date != _profileSessionDate) { _profileAnchors.OnSessionBoundary(bt.Date); _profileSessionDate = bt.Date; }
                _profileAnchors.OnBarClose(bar, bt);
            }

            // Scoring
            if (_session != null && _registry != null)
            {
                var va = FootprintBar.ComputeValueArea(bar, _session.TickSize);
                _session.Atr20         = _atr;
                _session.VolEma20      = _volEma;
                _session.Vah           = va.vah;
                _session.Val           = va.val;
                _session.PriorBar      = _priorFinalized;
                _session.BarsSinceOpen = _sessionBarCount;
                if (_atr > 0) { _session.SessionAtrSamples++; _session.SessionAvgAtr += (_atr - _session.SessionAvgAtr) / _session.SessionAtrSamples; }

                var signals  = _registry.EvaluateBar(bar, _session);
                var zoneSnap = _profileAnchors.BuildSnapshot();
                double zoneScore = ZoneScoreCalculator.Compute(bar.Close, zoneSnap, _session.TickSize);
                var scored = ConfluenceScorer.Score(signals, _session.BarsSinceOpen, bar.BarDelta, bar.Close,
                    zoneScore: zoneScore, zoneDistTicks: double.MaxValue, tickSize: _session.TickSize);
                scored.Signals = signals;

                SessionContext.Push(_session.PriceHistory, bar.Close);
                SessionContext.Push(_session.CvdHistory, bar.Cvd);
                SessionContext.Push(_session.DeltaHistory, bar.BarDelta);
                SessionContext.Push(_session.VolHistory, bar.TotalVol);
                SessionContext.Push(_session.TotalVolHistory, bar.TotalVol);
                SessionContext.Push(_session.PocHistory, bar.PocPrice);
                _session.PriorCvd = bar.Cvd;
                _session.SessionPocPrice = bar.PocPrice;
                if (bar.BarDelta > _session.SessionMaxDelta) _session.SessionMaxDelta = bar.BarDelta;
                if (bar.BarDelta < _session.SessionMinDelta) _session.SessionMinDelta = bar.BarDelta;
                _priorFinalized = bar;

                // Build L2 snapshots
                var bSnap = BuildL2CurrentSnapshot(_l2Bids);
                var aSnap = BuildL2CurrentSnapshot(_l2Asks);
                var bMax  = BuildL2MaxSnapshot(_l2Bids);
                var aMax  = BuildL2MaxSnapshot(_l2Asks);
                var bRef  = BuildL2RefillSnapshot(_l2Bids);
                var aRef  = BuildL2RefillSnapshot(_l2Asks);

                // Publish
                int    ct;  _barColumnType.TryGetValue(barIdx, out ct);
                List<StackedZone> sz; _stackedZones.TryGetValue(barIdx, out sz);
                HashSet<double>   ll; _largeLotBars.TryGetValue(barIdx, out ll);
                int    vcd; _volumeClimaxBars.TryGetValue(barIdx, out vcd);

                FootprintSharedState.Publish(
                    _instrumentName,
                    barIdx, bar, scored,
                    _vwapPrice, _vwap1H, _vwap1L, _vwap2H, _vwap2L,
                    _ibHigh, _ibLow,
                    zoneSnap,
                    bSnap, aSnap, bRef, aRef, bMax, aMax,
                    ct, sz, ll != null ? new HashSet<double>(ll) : null, vcd,
                    new Dictionary<double, int>(_unfinishedAuctions));

                ScorerSharedState.Publish(_instrumentName,
                    barIdx, scored, _session.SessionAvgAtr);
            }
        }

        // ════════════════════════════════════════════════════════════════════════
        // V2 computation helpers (identical logic to DEEP6FootprintChart)
        // ════════════════════════════════════════════════════════════════════════

        private void ResetSessionV2()
        {
            _vwapNum = 0; _vwapDen = 0; _vwapVar = 0;
            _vwapPrice = 0; _vwap1H = 0; _vwap1L = 0; _vwap2H = 0; _vwap2L = 0;
            _ibHigh = double.MinValue; _ibLow = double.MaxValue; _ibConfirmed = false;
            _unfinishedAuctions.Clear();
            _nBarHighs.Clear(); _nBarLows.Clear();
        }

        private void HandleSessionBoundary(DateTime time)
        {
            _lastSessionDate = time.Date;
            _sessionBarCount = 0;
            _session?.ResetSession();
            _registry?.ResetAll();
            _profileAnchors?.OnSessionBoundary(time.Date);
            _profileSessionDate = time.Date;
            ResetSessionV2();
        }

        private void UpdateVwap(FootprintBar bar)
        {
            if (bar.TotalVol == 0) return;
            double tp  = (bar.High + bar.Low + bar.Close) / 3.0;
            double vol = bar.TotalVol;
            _vwapNum += tp * vol; _vwapDen += vol;
            if (_vwapDen <= 0) return;
            double nv = _vwapNum / _vwapDen;
            _vwapVar += vol * (tp - nv) * (tp - nv);
            _vwapPrice = nv;
            double sd = _vwapVar > 0 ? System.Math.Sqrt(_vwapVar / _vwapDen) : 0;
            _vwap1H = _vwapPrice + sd;   _vwap1L = _vwapPrice - sd;
            _vwap2H = _vwapPrice + 2*sd; _vwap2L = _vwapPrice - 2*sd;
        }

        private void UpdateInitialBalance(FootprintBar bar)
        {
            if (_ibConfirmed) return;
            if (_sessionBarCount <= 60)
            {
                if (bar.High > _ibHigh || _ibHigh == double.MinValue) _ibHigh = bar.High;
                if (bar.Low  < _ibLow  || _ibLow  == double.MaxValue) _ibLow  = bar.Low;
            }
            else if (_ibHigh > double.MinValue) _ibConfirmed = true;
        }

        private void DetectBullBearColumn(FootprintBar bar, int barIdx)
        {
            if (bar.Levels.Count < 6) return;
            bool allBull = true, allBear = true;
            foreach (var kv in bar.Levels)
            {
                long d = kv.Value.AskVol - kv.Value.BidVol;
                if (d <= 0) allBull = false;
                if (d >= 0) allBear = false;
                if (!allBull && !allBear) break;
            }
            int ct = allBull ? 1 : allBear ? -1 : 0;
            if (ct != 0) _barColumnType[barIdx] = ct;
        }

        private void DetectStackedZones(FootprintBar bar, int barIdx)
        {
            if (bar.Levels.Count < 3) return;
            double ts  = _session?.TickSize ?? 0.25;
            double thr = ImbalanceRatio;
            var zones  = new List<StackedZone>();
            var prices = new List<double>(bar.Levels.Keys);
            int i = 0;
            while (i < prices.Count)
            {
                Cell c; if (!bar.Levels.TryGetValue(prices[i], out c)) { i++; continue; }
                int dir = CellDir(c, thr);
                if (dir == 0) { i++; continue; }
                int run = 1; double ep = prices[i];
                for (int j = i + 1; j < prices.Count; j++)
                {
                    if (System.Math.Abs(prices[j] - prices[j-1] - ts) > ts * 0.1) break;
                    Cell nc; if (!bar.Levels.TryGetValue(prices[j], out nc)) break;
                    if (CellDir(nc, thr) != dir) break;
                    run++; ep = prices[j];
                }
                if (run >= 3)
                    zones.Add(new StackedZone { PriceLow = prices[i], PriceHigh = ep,
                        Tier = run >= 7 ? 3 : run >= 5 ? 2 : 1, Direction = dir });
                i += run;
            }
            if (zones.Count > 0) _stackedZones[barIdx] = zones;
        }

        private static int CellDir(Cell c, double thr)
        {
            if (c.AskVol > 0 && (double)c.AskVol / System.Math.Max(1.0, c.BidVol) >= thr) return +1;
            if (c.BidVol > 0 && (double)c.BidVol / System.Math.Max(1.0, c.AskVol) >= thr) return -1;
            return 0;
        }

        private void DetectUnfinishedAuctions(FootprintBar bar, int barIdx)
        {
            Cell hc; if (bar.Levels.TryGetValue(bar.High, out hc) && hc.AskVol > 0 && hc.BidVol > 0) _unfinishedAuctions[bar.High] = barIdx;
            Cell lc; if (bar.Levels.TryGetValue(bar.Low,  out lc) && lc.AskVol > 0 && lc.BidVol > 0) _unfinishedAuctions[bar.Low]  = barIdx;
            var rev = new List<double>();
            foreach (var kv in _unfinishedAuctions) if (kv.Value < barIdx && kv.Key >= bar.Low && kv.Key <= bar.High) rev.Add(kv.Key);
            foreach (var k in rev) _unfinishedAuctions.Remove(k);
            var exp = new List<double>();
            foreach (var kv in _unfinishedAuctions) if (barIdx - kv.Value > 100) exp.Add(kv.Key);
            foreach (var k in exp) _unfinishedAuctions.Remove(k);
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
            if      (bar.High >= hi && bar.Close < mid) _volumeClimaxBars[barIdx] = -1;
            else if (bar.Low  <= lo && bar.Close > mid) _volumeClimaxBars[barIdx] = +1;
        }

        // ════════════════════════════════════════════════════════════════════════
        // L2 helpers
        // ════════════════════════════════════════════════════════════════════════

        private static void PruneL2(Dictionary<double, L2State> dict)
        {
            var cut = DateTime.UtcNow.AddMinutes(-15);
            var stale = new List<double>();
            foreach (var kv in dict) if (kv.Value.LastUpdate < cut) stale.Add(kv.Key);
            foreach (var k in stale) dict.Remove(k);
        }

        private static Dictionary<double, long> BuildL2CurrentSnapshot(Dictionary<double, L2State> dict)
        {
            var r = new Dictionary<double, long>(dict.Count);
            foreach (var kv in dict) r[kv.Key] = kv.Value.CurrentSize;
            return r;
        }

        private static Dictionary<double, long> BuildL2MaxSnapshot(Dictionary<double, L2State> dict)
        {
            var r = new Dictionary<double, long>(dict.Count);
            foreach (var kv in dict) r[kv.Key] = kv.Value.MaxSize;
            return r;
        }

        private static Dictionary<double, int> BuildL2RefillSnapshot(Dictionary<double, L2State> dict)
        {
            var r = new Dictionary<double, int>(dict.Count);
            foreach (var kv in dict) r[kv.Key] = kv.Value.RefillCount;
            return r;
        }

        // ════════════════════════════════════════════════════════════════════════
        // Required BarsType overrides
        // ════════════════════════════════════════════════════════════════════════

        public override void ApplyDefaultValue(BarsPeriod period) => period.Value = 5;
        public override void ApplyDefaultBasePeriodValue(BarsPeriod period) { }
        public override string ChartLabel(DateTime time) => time.ToString("HH:mm");

        public override int GetInitialLookBackDays(BarsPeriod barsPeriod, TradingHours tradingHours, int barsBack)
        {
            int minutesPerWeek = 0;
            if (tradingHours?.Sessions != null)
            {
                lock (tradingHours.Sessions)
                {
                    foreach (Session session in tradingHours.Sessions)
                    {
                        int bd = (int)session.BeginDay, ed = (int)session.EndDay;
                        if (bd > ed) ed += 7;
                        minutesPerWeek += (ed - bd) * 1440
                            + session.EndTime / 100 * 60   + session.EndTime % 100
                            - (session.BeginTime / 100 * 60 + session.BeginTime % 100);
                    }
                }
            }
            return (int)System.Math.Max(1, System.Math.Ceiling(
                barsBack / System.Math.Max(1.0, minutesPerWeek / 7.0 / barsPeriod.Value) * 1.05));
        }

        public override double GetPercentComplete(Bars bars, DateTime now)
        {
            if (bars.LastBarTime == DateTime.MinValue) return 0;
            double remaining = bars.LastBarTime.Subtract(now).TotalMinutes;
            return now <= bars.LastBarTime ? 1.0 - remaining / bars.BarsPeriod.Value : 1.0;
        }

        private DateTime TimeToBarTime(Bars bars, DateTime time, bool isBar)
        {
            if (isBar) return time;
            if (SessionIterator == null) return time;
            DateTime sessionEnd = SessionIterator.ActualSessionEnd;
            int period = bars.BarsPeriod.Value;
            int minutesSinceSessionStart = (int)(time - SessionIterator.ActualSessionBegin).TotalMinutes;
            int barsElapsed = minutesSinceSessionStart / period;
            DateTime barClose = SessionIterator.ActualSessionBegin.AddMinutes((barsElapsed + 1) * period);
            return barClose <= sessionEnd ? barClose : sessionEnd;
        }

        // ════════════════════════════════════════════════════════════════════════
        // Properties
        // ════════════════════════════════════════════════════════════════════════

        #region Properties

        [NinjaScriptProperty]
        [Range(1.5, 8.0)]
        [Display(Name = "Imbalance Ratio", Order = 1, GroupName = "Detection",
                 Description = "Minimum bid/ask ratio to classify a level as imbalanced (NQ: 3.0–4.0 recommended)")]
        public double ImbalanceRatio { get; set; }

        [NinjaScriptProperty]
        [Range(10, 500)]
        [Display(Name = "Large Lot Threshold (contracts)", Order = 2, GroupName = "Detection",
                 Description = "Minimum contracts in a single print to mark as institutional")]
        public int LargeLotThreshold { get; set; }

        [NinjaScriptProperty]
        [Range(1.5, 5.0)]
        [Display(Name = "Volume Climax Multiplier", Order = 3, GroupName = "Detection",
                 Description = "Bar volume must exceed VolEMA × this value to qualify as a climax bar")]
        public double VolClimaxMultiplier { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Naked POC Max Age (sessions)", Order = 4, GroupName = "Detection")]
        public int NakedPocMaxAgeSessions { get; set; }

        [NinjaScriptProperty]
        [Range(10, 5000)]
        [Display(Name = "Liquidity Wall Min (contracts)", Order = 5, GroupName = "L2 Walls")]
        public int LiquidityWallMin { get; set; }

        [NinjaScriptProperty]
        [Range(10, 600)]
        [Display(Name = "Liquidity Wall Stale (seconds)", Order = 6, GroupName = "L2 Walls")]
        public int LiquidityWallStaleSec { get; set; }

        #endregion
    }
}
