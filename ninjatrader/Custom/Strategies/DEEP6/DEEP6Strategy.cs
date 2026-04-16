// DEEP6 Strategy — auto-trader companion to DEEP6Footprint indicator.
//
// SAFETY-FIRST DESIGN
// ===================
// 1. Defaults to DRY_RUN mode. Live order routing requires explicit user
//    opt-in via EnableLiveTrading = true AND ApprovedAccountName match.
// 2. Hard caps: max contracts/trade, max trades/session, daily loss cap,
//    RTH-only window, news-blackout windows.
// 3. Reuses signal types from the indicator's AddOns.DEEP6 namespace —
//    install DEEP6Footprint.cs first (this strategy file references its types).
// 4. Bracket orders via NT8 ATM templates — see docs/ATM-STRATEGIES.md.
//    User configures bracket parameters in NT8 UI; strategy references templates by name.
//
// CONFLUENCE LOGIC
// ================
// Fires only on Tier 3 confluence (matching INTERACTION-LOGIC.md):
//   (a) STACKED:  Absorption + Exhaustion same direction within 1 bar
//   (b) VA-EXTREME: signal at VAH/VAL with strength >= 0.75
//   (c) WALL-ANCHORED: signal within 3 ticks of supportive Liquidity Wall
// Single-component setups, regardless of strength, do NOT fire here.
//
// THIS DUPLICATES THE PYTHON DEEP6 EXECUTION PATH. Keep this in mind:
// running both NT8 strategy + Python engine on the same Rithmic account
// will conflict. Use sim accounts here while Python is being built, OR
// disable the Python execution side, OR use this in dry-run only.

#region Using
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.NinjaScript;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.AddOns.DEEP6;   // Cell, FootprintBar, AbsorptionDetector, ExhaustionDetector, signal types
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Imbalance;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Auction;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.VolPattern;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Trap;
using NinjaTrader.NinjaScript.DrawingTools;
using Brushes = System.Windows.Media.Brushes;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.DEEP6
{
    public class DEEP6Strategy : Strategy
    {
        // ---- Detection state (mirrors indicator) ----
        private readonly Dictionary<int, FootprintBar> _bars = new Dictionary<int, FootprintBar>();
#if NINJASCRIPT_SIM
        private double _bestBid = double.NaN, _bestAsk = double.NaN;  // volatile double not supported in .NET 8+
#else
        private volatile double _bestBid = double.NaN, _bestAsk = double.NaN;
#endif
        private readonly object _barsLock = new object();
        private long _priorCvd;
        private FootprintBar _priorFinalized;

        private readonly Queue<double> _atrWindow = new Queue<double>();
        private const int AtrPeriod = 20;
        private double _atr = 1.0;
        private double _volEma;
        private const double VolEmaAlpha = 2.0 / (20.0 + 1.0);

        private readonly AbsorptionConfig _absCfg = new AbsorptionConfig();
        private readonly ExhaustionConfig _exhCfg = new ExhaustionConfig();
        private readonly ExhaustionDetector _exhDetector = new ExhaustionDetector();

        // ---- Phase 17 detector registry (UseNewRegistry feature flag) ----
        // When UseNewRegistry = false, strategy uses legacy ABS/EXH code path.
        // When UseNewRegistry = true (default since Phase 17 Wave 5 parity PASS), uses registry.
        // Phase 18-03: scorer-gated EvaluateEntry reads ScorerSharedState published by DEEP6Footprint.
        private NinjaTrader.NinjaScript.AddOns.DEEP6.Registry.DetectorRegistry _registry;
        private NinjaTrader.NinjaScript.AddOns.DEEP6.Registry.SessionContext    _session;

        // ---- L2 wall state for wall-anchored confluence ----
        private sealed class L2State { public long CurrentSize, MaxSize; public DateTime LastUpdate; }
        private readonly Dictionary<double, L2State> _l2Bids = new Dictionary<double, L2State>();
        private readonly Dictionary<double, L2State> _l2Asks = new Dictionary<double, L2State>();
        private readonly object _l2Lock = new object();

        // ---- Risk + lifecycle state ----
        private DateTime _sessionDate = DateTime.MinValue;
        private int _tradesThisSession;
        private double _sessionStartBalance = double.NaN;   // NaN until first valid Account read; gates loss-cap fail-closed
        private bool _killSwitch;     // set when daily loss cap hit; resets next session
        private int _lastEntryBar = -1;
        private string _activeAtmGuid;   // tracks live ATM bracket so we can AtmStrategyClose() instead of racing ExitLong/Short

        // ---- R1: EvaluateWithContext session gate state ----
        // Owns VolSurgeFiredThisSession flag; reset at session boundary (when _sessionDate changes).
        private ScorerEntryGate.SessionGateState _gateState = new ScorerEntryGate.SessionGateState();

        // News blackout windows (NY time) — hard-coded major releases; user can extend
        private static readonly (int hour, int min, int durationMin)[] NewsBlackouts = new[]
        {
            (8, 25, 15),    // 08:30 ET — most data releases (CPI, PPI, NFP at month start, jobless claims)
            (10, 0, 5),     // 10:00 ET — ISM, consumer confidence
            (14, 0, 15),    // 14:00 ET — FOMC announcement (only on FOMC days, but blackout is harmless otherwise)
        };

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description                  = "DEEP6 Auto-Trader — fires Tier 3 confluence setups via ATM bracket templates.";
                Name                         = "DEEP6 Strategy";
                Calculate                    = Calculate.OnBarClose;
                EntriesPerDirection          = 1;
                EntryHandling                = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;
                ExitOnSessionCloseSeconds    = 30;
                IsFillLimitOnTouch           = false;
                MaximumBarsLookBack          = MaximumBarsLookBack.TwoHundredFiftySix;
                OrderFillResolution          = OrderFillResolution.Standard;
                Slippage                     = 0;
                StartBehavior                = StartBehavior.WaitUntilFlat;
                TimeInForce                  = TimeInForce.Day;
                TraceOrders                  = false;
                RealtimeErrorHandling        = RealtimeErrorHandling.StopCancelClose;
                StopTargetHandling           = StopTargetHandling.PerEntryExecution;
                BarsRequiredToTrade          = 20;
                IsInstantiatedOnEachOptimizationIteration = false;

                // SAFETY DEFAULTS
                // UseNewRegistry default is true (Phase 17 Wave 5 parity PASS); override per-instance in NT8 if needed
                UseNewRegistry               = true;
                EnableLiveTrading            = false;
                ApprovedAccountName          = "Sim101";
                MaxContractsPerTrade         = 2;      // R1: scale-out requires 2 contracts (50% T1, 50% T2)
                MaxTradesPerSession          = 5;
                DailyLossCapDollars          = 500.0;  // R1: updated from 250 → 500 per PRODUCTION-CONFIG.md
                RthStartHour                 = 9;
                RthStartMinute               = 35;
                RthEndHour                   = 15;
                RthEndMinute                 = 50;
                MinBarsBetweenEntries        = 3;
                RespectNewsBlackouts         = true;

                AbsorbWickMinPct             = 30.0;
                ExhaustWickMinPct            = 35.0;
                ConfluenceVaExtremeStrength  = 0.75;
                ConfluenceWallProximityTicks = 3;
                LiquidityWallMin             = 100;

                AtmTemplateAbsorption        = "DEEP6_Absorption";
                AtmTemplateExhaustion        = "DEEP6_Exhaustion";
                AtmTemplateConfluence        = "DEEP6_Confluence";
                AtmTemplateDefault           = "DEEP6_Practice";

                // R1: scorer entry gate defaults — TYPE_B + threshold=70 (round1 meta-optimization walk-forward optimum)
                ScoreEntryThreshold          = 70.0;
                MinTierForEntry              = SignalTier.TYPE_B;

                // R1/R2: new entry filter properties per PRODUCTION-CONFIG.md
                StrictDirectionEnabled       = true;
                BlackoutWindowStart          = 1530;
                BlackoutWindowEnd            = 1600;

                // R1/R2: exit management properties per PRODUCTION-CONFIG.md
                StopLossTicks                = 20;
                ScaleOutEnabled              = true;
                ScaleOutPercent              = 0.5;
                ScaleOutTargetTicks          = 16;
                TargetTicks                  = 32;
                BreakevenEnabled             = true;
                BreakevenActivationTicks     = 10;
                BreakevenOffsetTicks         = 2;
                MaxBarsInTrade               = 60;
                ExitOnOpposingScore          = 0.3;

                // R1/R2: regime veto properties per PRODUCTION-CONFIG.md
                VolSurgeVetoEnabled          = true;
                SlowGrindVetoEnabled         = true;
                SlowGrindAtrRatio            = 0.5;
            }
            else if (State == State.Configure)
            {
                _absCfg.AbsorbWickMin  = AbsorbWickMinPct;
                _exhCfg.ExhaustWickMin = ExhaustWickMinPct;
                _gateState = new ScorerEntryGate.SessionGateState();

                // Phase 17 Waves 1-4: Initialize registry when feature flag is on.
                // Default is false — live ABS/EXH path stays active until Wave 5 full-session parity passes.
                if (UseNewRegistry)
                {
                    _registry = new NinjaTrader.NinjaScript.AddOns.DEEP6.Registry.DetectorRegistry();
                    // Wave 1: migrated legacy detectors
                    _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Absorption.AbsorptionDetector());
                    _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion.ExhaustionDetector());
                    // Waves 3+4: 5 new family detectors (IMB / DELT / AUCT / VOLP / TRAP)
                    _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Imbalance.ImbalanceDetector());
                    _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta.DeltaDetector());
                    _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Auction.AuctionDetector());
                    _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.VolPattern.VolPatternDetector());
                    _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Trap.TrapDetector());
                    // Wave 5 (Phase 17-05): Engine detectors ENG-02..07
                    // CRITICAL: registration order — MicroProbDetector (ENG-05) MUST be last
                    // because it reads session fields written by TrespassDetector (ENG-02) and
                    // IcebergDetector (ENG-04) during the same bar cycle.
                    _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.TrespassDetector());
                    _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.CounterSpoofDetector());
                    _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.IcebergDetector());
                    _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.VPContextDetector());
                    _registry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.MicroProbDetector());  // LAST
                    // Fix 11: _session initialized in DataLoaded (after TickSize is valid), not here.
                    Print("[DEEP6 Strategy] UseNewRegistry=true: Waves 1-5 detectors registered (ABS/EXH/IMB/DELT/AUCT/VOLP/TRAP + ENG-02..07).");
                }
                else
                {
                    _registry = null;
                    _session  = null;
                }
            }
            else if (State == State.DataLoaded)
            {
                lock (_barsLock) { _bars.Clear(); }
                _exhDetector.ResetCooldowns();
                _atrWindow.Clear();
                _volEma = 0.0;
                _priorCvd = 0;
                _priorFinalized = null;
                _killSwitch = false;
                _tradesThisSession = 0;
                _sessionDate = DateTime.MinValue;

                // Fix 11: initialize _session here (DataLoaded) so TickSize is valid.
                if (UseNewRegistry && _registry != null)
                    _session = new NinjaTrader.NinjaScript.AddOns.DEEP6.Registry.SessionContext { TickSize = TickSize > 0 ? TickSize : 0.25 };

                Print(string.Format("[DEEP6 Strategy] Initialized. EnableLiveTrading={0}, Account={1}, ApprovedAccount={2}",
                    EnableLiveTrading, Account != null ? Account.Name : "?", ApprovedAccountName));
                if (!EnableLiveTrading) Print("[DEEP6 Strategy] DRY RUN — no orders will be submitted. Set EnableLiveTrading=true to go live.");
            }
            else if (State == State.Terminated)
            {
                // Fix 10: clean up all state on termination to avoid memory leaks.
                lock (_barsLock) { _bars.Clear(); }
                lock (_l2Lock) { _l2Bids.Clear(); _l2Asks.Clear(); }
                _atrWindow.Clear();
                _registry = null;
                _session  = null;
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

            lock (_barsLock)
            {
                FootprintBar bar;
                if (!_bars.TryGetValue(CurrentBar, out bar))
                {
                    bar = new FootprintBar { BarIndex = CurrentBar };
                    _bars[CurrentBar] = bar;
                }
                bar.AddTrade(e.Price, (long)e.Volume, aggressor);
            }
        }

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (e.Position >= 10) return;
            Dictionary<double, L2State> dict;
            if (e.MarketDataType == MarketDataType.Bid) dict = _l2Bids;
            else if (e.MarketDataType == MarketDataType.Ask) dict = _l2Asks;
            else return;

            long newSize = e.Operation == Operation.Remove ? 0 : (long)e.Volume;
            lock (_l2Lock)
            {
                L2State st;
                if (!dict.TryGetValue(e.Price, out st)) { st = new L2State(); dict[e.Price] = st; }
                st.CurrentSize = newSize;
                if (newSize > st.MaxSize) st.MaxSize = newSize;
                st.LastUpdate = DateTime.UtcNow;
            }
        }

        // ---- Bar lifecycle + entry logic ----

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;
            if (CurrentBar < BarsRequiredToTrade) return;

            int prevIdx = CurrentBar - 1;
            FootprintBar prev;
            lock (_barsLock)
            {
                _bars.TryGetValue(prevIdx, out prev);
            }
            if (prev == null) return;

            // Reconcile + finalize
            prev.Open = Bars.GetOpen(prevIdx);
            prev.High = Bars.GetHigh(prevIdx);
            prev.Low  = Bars.GetLow(prevIdx);
            prev.Close= Bars.GetClose(prevIdx);
            prev.Finalize(_priorCvd);
            _priorCvd = prev.Cvd;

            _atrWindow.Enqueue(prev.BarRange);
            while (_atrWindow.Count > AtrPeriod) _atrWindow.Dequeue();
            double sum = 0; foreach (var v in _atrWindow) sum += v;
            _atr = _atrWindow.Count == 0 ? 1.0 : Math.Max(sum / _atrWindow.Count, TickSize);
            _volEma = _volEma == 0 ? prev.TotalVol : _volEma + VolEmaAlpha * (prev.TotalVol - _volEma);

            // Session boundary — reset risk counters
            DateTime barDate = Bars.GetTime(prevIdx).Date;
            if (barDate != _sessionDate)
            {
                _sessionDate = barDate;
                _tradesThisSession = 0;
                _killSwitch = false;
                _sessionStartBalance = double.NaN;   // re-capture below once Account/balance are valid
                _exhDetector.ResetCooldowns();
                // R1: reset session gate state (clears VolSurgeFiredThisSession and other session flags)
                _gateState.ResetSession();
                // Phase 17: reset registry + session at RTH open boundary
                if (UseNewRegistry && _registry != null)
                {
                    _session?.ResetSession();
                    _registry.ResetAll();
                }
                Print(string.Format("[DEEP6 Strategy] New session {0}. Counters reset. Will capture session start balance on first non-null Account.",
                    _sessionDate.ToString("yyyy-MM-dd")));
            }
            // Lazy capture: keep trying until we get a real account balance, then freeze it for the session.
            if (double.IsNaN(_sessionStartBalance) && Account != null)
            {
                double bal = GetAccountValue();
                if (bal > 0)
                {
                    _sessionStartBalance = bal;
                    Print(string.Format("[DEEP6 Strategy] Session start balance captured: ${0:F2}.", bal));
                }
            }
            // Capture the bar-before-prev BEFORE we overwrite _priorFinalized — otherwise
            // the exhaustion detector receives null for the prior bar and BID_ASK_FADE never fires.
            var priorBeforePrev = _priorFinalized;
            _priorFinalized = prev;

            // Run detectors — legacy path or registry path depending on UseNewRegistry flag
            var va  = FootprintBar.ComputeValueArea(prev, TickSize);
            List<AbsorptionSignal> abs;
            List<ExhaustionSignal> exh;

            if (UseNewRegistry && _registry != null && _session != null)
            {
                // Phase 17 Wave 2: registry path — populate SessionContext then call EvaluateBar.
                // Risk gates execute BEFORE this branch (above via _killSwitch + Position check).
                _session.Atr20        = _atr;
                _session.VolEma20     = _volEma;
                _session.TickSize     = TickSize;
                _session.Vah          = va.vah;
                _session.Val          = va.val;
                _session.PriorBar     = priorBeforePrev;
                _session.BarsSinceOpen = prevIdx;

                var regResults = _registry.EvaluateBar(prev, _session);
                _session.PriorBar = prev;   // advance prior bar for next bar

                // Log non-ABS/EXH signals once (ABS/EXH drive confluence below; others are observational)
                foreach (var sr in regResults)
                {
                    if (!sr.SignalId.StartsWith("ABS") && !sr.SignalId.StartsWith("EXH"))
                        Print(string.Format("[DEEP6 Registry] {0} dir={1:+#;-#;0} str={2:F2} | {3}",
                            sr.SignalId, sr.Direction, sr.Strength, sr.Detail));
                }

                // Convert SignalResult[] → legacy list types so EvaluateEntry + CheckOpposingExit
                // can consume them without modification (risk gates are in those methods, untouched).
                abs = new List<AbsorptionSignal>();
                exh = new List<ExhaustionSignal>();
                foreach (var r in regResults)
                {
                    if (r.SignalId.StartsWith("ABS") && r.SignalId != "ABS-07")
                    {
                        abs.Add(new AbsorptionSignal
                        {
                            Kind        = AbsorptionType.Classic,   // best-effort mapping for confluence
                            Direction   = r.Direction,
                            Price       = r.Direction < 0 ? prev.High : r.Direction > 0 ? prev.Low : prev.Close,
                            Wick        = r.Direction < 0 ? "upper" : "lower",
                            Strength    = r.Strength,
                            AtVaExtreme = r.Detail != null && (r.Detail.Contains("@VAH") || r.Detail.Contains("@VAL")),
                            Detail      = r.Detail,
                        });
                    }
                    else if (r.SignalId.StartsWith("EXH"))
                    {
                        exh.Add(new ExhaustionSignal
                        {
                            Kind      = ExhaustionType.ZeroPrint,   // best-effort mapping; not used for gating
                            Direction = r.Direction,
                            Price     = r.Direction < 0 ? prev.High : r.Direction > 0 ? prev.Low : prev.Close,
                            Strength  = r.Strength,
                            Detail    = r.Detail,
                        });
                    }
                }
            }
            else
            {
                // Legacy path (UseNewRegistry=false, default) — unchanged behavior
                abs = AbsorptionDetector.Detect(prev, _atr, _volEma, _absCfg, va.vah, va.val, TickSize);
                exh = _exhDetector.Detect(prev, priorBeforePrev, prevIdx, _atr, _exhCfg);
            }

            // Cleanup history
            int cutoff = CurrentBar - 500;
            if (cutoff > 0)
            {
                lock (_barsLock)
                {
                    var stale = _bars.Keys.Where(k => k < cutoff).ToList();
                    foreach (var k in stale) _bars.Remove(k);
                }
            }

            if (_killSwitch) return;
            if (Position.MarketPosition != MarketPosition.Flat)
            {
                CheckOpposingExit(abs, exh);
                return;
            }

            // Phase 18-03: scorer-gated entry — read latest result published by DEEP6Footprint indicator.
            ScorerResult _scored = ScorerSharedState.Latest(Instrument.FullName);
            int _latestBarIdx    = ScorerSharedState.LatestBarIndex(Instrument.FullName);

            // R1: Observe signals into session gate state for VOLP-03 tracking (each bar, before Evaluate).
            // Also read sessionAvgAtr from ScorerSharedState for slow-grind veto.
            SignalResult[] _barSignals = null;
            double _sessionAvgAtr = 0.0;
            if (_scored != null)
            {
                _barSignals   = _scored.Signals;
                _sessionAvgAtr = ScorerSharedState.LatestSessionAvgAtr(Instrument.FullName);
                _gateState.ObserveSignals(_barSignals);
            }

            // SC5 per-bar log — fires every scored bar regardless of whether entry triggers.
            // Format matches ScorerEntryGate.BuildLogLine pattern (bar / score / tier / narrative).
            if (_scored != null && _latestBarIdx == CurrentBar)
            {
                Print(string.Format(
                    "[DEEP6 Scorer] bar={0} score={1:+0.00;-0.00;+0.00} tier={2} narrative={3}",
                    CurrentBar, _scored.TotalScore, _scored.Tier, _scored.Narrative ?? string.Empty));
            }

            // R1: Derive barTimeHHMM from the bar's timestamp for time-of-day blackout gate.
            DateTime barTs = Bars.GetTime(prevIdx);
            int barTimeHHMM = barTs.Hour * 100 + barTs.Minute;

            EvaluateEntry(CurrentBar, _scored, _barSignals, _sessionAvgAtr, barTimeHHMM);
        }

        // ---- Confluence / entry decision ----

        /// <summary>
        /// R1: Scorer-gated entry with full R1/R2 context vetos.
        /// Entry fires only when EvaluateWithContext() == Passed AND RiskGatesPass() approves.
        /// Risk gates (account whitelist, RTH, news, cooldown, max trades, daily loss cap) remain
        /// evaluated AFTER the scorer gate but BEFORE EnterWithAtm — order unchanged.
        ///
        /// R1 gates added:
        ///   - VOLP-03 session veto (via _gateState.VolSurgeFiredThisSession)
        ///   - Slow-grind ATR veto (current ATR vs session average ATR)
        ///   - Strict directional agreement filter
        ///   - Time-of-day blackout (BlackoutWindowStart–BlackoutWindowEnd ET)
        /// </summary>
        private void EvaluateEntry(int barIdx, ScorerResult scored, SignalResult[] signals = null,
                                   double sessionAvgAtr = 0.0, int barTimeHHMM = 0)
        {
            var outcome = ScorerEntryGate.EvaluateWithContext(
                scored,
                ScoreEntryThreshold,
                MinTierForEntry,
                _gateState,
                volSurgeVetoEnabled:    VolSurgeVetoEnabled,
                slowGrindVetoEnabled:   SlowGrindVetoEnabled,
                slowGrindAtrRatio:      SlowGrindAtrRatio,
                currentAtr:             _atr,
                sessionAvgAtr:          sessionAvgAtr,
                strictDirectionEnabled: StrictDirectionEnabled,
                signals:                signals,
                blackoutWindowStart:    BlackoutWindowStart,
                blackoutWindowEnd:      BlackoutWindowEnd,
                barTimeHHMM:            barTimeHHMM);

            if (outcome != ScorerEntryGate.GateOutcome.Passed)
            {
                // Log non-trivial veto outcomes for session-level diagnostics.
                if (outcome == ScorerEntryGate.GateOutcome.VolSurgeVeto)
                    Print(string.Format("[DEEP6 Strategy] bar={0} VOLP-03 veto active — no new entries this session.", barIdx));
                else if (outcome == ScorerEntryGate.GateOutcome.SlowGrindVeto)
                    Print(string.Format("[DEEP6 Strategy] bar={0} slow-grind veto — ATR {1:F4} < {2:F2}×sessionAvg {3:F4}.",
                        barIdx, _atr, SlowGrindAtrRatio, sessionAvgAtr));
                else if (outcome == ScorerEntryGate.GateOutcome.BlackoutVeto)
                    Print(string.Format("[DEEP6 Strategy] bar={0} blackout veto — time {1:D4} in [{2},{3}].",
                        barIdx, barTimeHHMM, BlackoutWindowStart, BlackoutWindowEnd));
                return;
            }

            double entryPrice = scored.EntryPrice > 0 ? scored.EntryPrice : Close[0];
            string trigger    = string.Format("SCORER_{0}_{1:F0}", scored.Tier, scored.TotalScore);

            // RISK GATES — still evaluated before any order submission (unchanged behavior).
            if (!RiskGatesPass(scored.Direction, entryPrice, trigger, barIdx)) return;

            // R1: Select ATM template based on scale-out configuration.
            string atmTemplate = SelectAtmTemplate(scored);
            EnterWithAtm(scored.Direction, atmTemplate, trigger, entryPrice);
        }

        /// <summary>
        /// R1: Select ATM template based on scale-out configuration.
        /// If ScaleOutEnabled, use AtmTemplateConfluence (DEEP6_Confluence — dual-target with T1+T2).
        /// Otherwise, fall back to AtmTemplateDefault (single-target).
        ///
        /// NOTE: The DEEP6_Confluence ATM template MUST be created in NT8 ATM Strategy editor with:
        ///   Quantity=2, Profit Target 1=16 ticks (50% = 1 contract), Profit Target 2=32 ticks,
        ///   Stop Loss=20 ticks. See PRE-LIVE-CHECKLIST.md item 9 and EXECUTION-SIM.md Section 6.
        /// </summary>
        private string SelectAtmTemplate(ScorerResult scored)
        {
            return ScaleOutEnabled ? AtmTemplateConfluence : AtmTemplateDefault;
        }

        private bool IsWallAnchored(double signalPrice, int signalDir)
        {
            // Bullish signal: look for a SUPPORTIVE wall (bid wall) below within N ticks
            // Bearish signal: look for a SUPPORTIVE wall (ask wall) above within N ticks
            var dict = signalDir > 0 ? _l2Bids : _l2Asks;
            double prox = ConfluenceWallProximityTicks * TickSize;
            DateTime fresh = DateTime.UtcNow.AddSeconds(-90);
            lock (_l2Lock)
            {
                foreach (var kv in dict)
                {
                    // Use CurrentSize (live), not MaxSize (historical max — would phantom-fire on pulled walls)
                    if (kv.Value.CurrentSize < LiquidityWallMin) continue;
                    if (kv.Value.LastUpdate < fresh) continue;
                    double dist = Math.Abs(kv.Key - signalPrice);
                    bool onCorrectSide = signalDir > 0 ? kv.Key <= signalPrice : kv.Key >= signalPrice;
                    if (onCorrectSide && dist <= prox) return true;
                }
            }
            return false;
        }

        // ---- Risk gates ----

        private bool RiskGatesPass(int direction, double signalPrice, string trigger, int barIdx)
        {
            // 1. Account check — only fire on the approved account
            if (Account == null || Account.Name != ApprovedAccountName)
            {
                Print(string.Format("[DEEP6 Strategy] BLOCKED — account '{0}' != approved '{1}'.",
                    Account == null ? "null" : Account.Name, ApprovedAccountName));
                return false;
            }

            // 2. RTH window
            var t = Time[0].TimeOfDay;
            var rthStart = new TimeSpan(RthStartHour, RthStartMinute, 0);
            var rthEnd   = new TimeSpan(RthEndHour, RthEndMinute, 0);
            if (t < rthStart || t > rthEnd)
            {
                Print(string.Format("[DEEP6 Strategy] BLOCKED — outside RTH ({0:hh\\:mm}).", t));
                return false;
            }

            // 3. News blackout
            if (RespectNewsBlackouts)
            {
                foreach (var nb in NewsBlackouts)
                {
                    var nbStart = new TimeSpan(nb.hour, nb.min, 0);
                    var nbEnd   = nbStart + TimeSpan.FromMinutes(nb.durationMin);
                    if (t >= nbStart && t <= nbEnd)
                    {
                        Print(string.Format("[DEEP6 Strategy] BLOCKED — news blackout {0:hh\\:mm}-{1:hh\\:mm}.", nbStart, nbEnd));
                        return false;
                    }
                }
            }

            // 4. Cooldown between entries
            if (barIdx - _lastEntryBar < MinBarsBetweenEntries)
            {
                Print(string.Format("[DEEP6 Strategy] BLOCKED — within cooldown ({0} bars since last entry).", barIdx - _lastEntryBar));
                return false;
            }

            // 5. Max trades per session
            if (_tradesThisSession >= MaxTradesPerSession)
            {
                Print(string.Format("[DEEP6 Strategy] BLOCKED — max trades reached ({0}).", _tradesThisSession));
                return false;
            }

            // 6. Daily loss cap — fail-closed if we never captured a valid session-start balance
            if (double.IsNaN(_sessionStartBalance) || _sessionStartBalance <= 0)
            {
                Print("[DEEP6 Strategy] BLOCKED — session start balance not yet captured. Loss cap cannot be enforced; refusing entries.");
                return false;
            }
            double currentBal = GetAccountValue();
            double sessionPnl = currentBal - _sessionStartBalance;
            if (sessionPnl <= -DailyLossCapDollars)
            {
                _killSwitch = true;
                Print(string.Format("[DEEP6 Strategy] KILL SWITCH — daily loss cap hit. Session P&L ${0:F2}. No more trades today.",
                    sessionPnl));
                return false;
            }

            return true;
        }

        // ---- Entry submission ----

        private void EnterWithAtm(int direction, string atmTemplate, string trigger, double signalPrice)
        {
            string side = direction > 0 ? "LONG" : "SHORT";
            string label = string.Format("DEEP6_{0}_{1}_{2}", trigger, side, CurrentBar);

            // R1: ATM bracket configuration log.
            // Format: [DEEP6 Strategy] ATM created: stop={S}t, T1={T1}t@{P}%, T2={T2}t, BE@MFE{BE}t
            // If ScaleOutEnabled: dual-target DEEP6_Confluence template (T1=ScaleOutTargetTicks, T2=TargetTicks).
            // If not: single-target AtmTemplateDefault (stop=StopLossTicks, target=TargetTicks).
            // NOTE: ATM template MUST be configured in NT8 ATM Strategy editor to match these values.
            //   DEEP6_Confluence: Qty=2, T1=16t@50%, T2=32t, SL=20t (per PRE-LIVE-CHECKLIST.md item 9).
            if (ScaleOutEnabled)
            {
                Print(string.Format(
                    "[DEEP6 Strategy] ATM created: stop={0}t, T1={1}t@{2:P0}, T2={3}t, BE@MFE{4}t (template={5})",
                    StopLossTicks, ScaleOutTargetTicks, ScaleOutPercent, TargetTicks,
                    BreakevenEnabled ? BreakevenActivationTicks : 0, atmTemplate));
            }
            else
            {
                Print(string.Format(
                    "[DEEP6 Strategy] ATM created: stop={0}t, T1={1}t (single-target, scale-out disabled, template={2})",
                    StopLossTicks, TargetTicks, atmTemplate));
            }

            if (!EnableLiveTrading)
            {
                Print(string.Format("[DEEP6 Strategy] DRY-RUN entry: {0} qty={1} ATM='{2}' @ signal price {3:F2} (label {4})",
                    side, MaxContractsPerTrade, atmTemplate, signalPrice, label));
                _lastEntryBar = CurrentBar;
                _tradesThisSession++;
                return;
            }

            try
            {
                var atmGuid = Guid.NewGuid().ToString();
                var orderId = Guid.NewGuid().ToString();
                OrderAction action = direction > 0 ? OrderAction.Buy : OrderAction.SellShort;

                // NT8 8.1 AtmStrategyCreate: 9-arg signature (no quantity param).
                // Quantity is inherited from the ATM template's saved Qty field.
                // User MUST set the ATM template qty to match MaxContractsPerTrade in NT8 UI.
                AtmStrategyCreate(action, OrderType.Market, 0, 0, TimeInForce.Day,
                    orderId, atmTemplate, atmGuid,
                    (atmCallbackErrorCode, atmCallbackId) =>
                    {
                        if (atmCallbackErrorCode == ErrorCode.NoError)
                        {
                            _activeAtmGuid = atmGuid;
                            _lastEntryBar = CurrentBar;
                            _tradesThisSession++;
                            Print(string.Format("[DEEP6 Strategy] LIVE entry CONFIRMED: {0} ATM='{1}' trigger={2} @ {3:F2} atmGuid={4}",
                                side, atmTemplate, trigger, signalPrice, atmGuid));
                        }
                        else
                        {
                            Print(string.Format("[DEEP6 Strategy] LIVE entry REJECTED: ATM='{0}' code={1} (id={2}). Counter NOT incremented.",
                                atmTemplate, atmCallbackErrorCode, atmCallbackId));
                        }
                    });
                Print(string.Format("[DEEP6 Strategy] LIVE entry submitted: {0} ATM='{1}' trigger={2} @ {3:F2} (qty from template; awaiting callback)",
                    side, atmTemplate, trigger, signalPrice));
            }
            catch (Exception ex)
            {
                Print(string.Format("[DEEP6 Strategy] ENTRY EXCEPTION: {0} — {1}", ex.GetType().Name, ex.Message));
            }
        }

        // ---- In-position exit on opposing signal ----

        private void CheckOpposingExit(List<AbsorptionSignal> abs, List<ExhaustionSignal> exh)
        {
            int holdingDir = Position.MarketPosition == MarketPosition.Long ? +1 : -1;
            bool opposingSignal = false;
            double maxOppStr = 0;

            foreach (var s in abs)
                if (s.Direction != 0 && s.Direction != holdingDir && s.Strength > maxOppStr)
                { opposingSignal = true; maxOppStr = s.Strength; }
            foreach (var s in exh)
                if (s.Direction != 0 && s.Direction != holdingDir && s.Strength > maxOppStr)
                { opposingSignal = true; maxOppStr = s.Strength; }

            if (!opposingSignal || maxOppStr < 0.6) return;

            Print(string.Format("[DEEP6 Strategy] EXIT — opposing signal strength {0:F2} fired against {1} position.",
                maxOppStr, Position.MarketPosition));
            if (EnableLiveTrading)
            {
                try
                {
                    // AtmStrategyClose tears down the entire bracket cleanly (cancels stop+target,
                    // submits a market exit). ExitLong/Short would race the bracket's own protective
                    // orders and can leave orphaned stops or double-exit.
                    string atmGuidToClose;
                    lock (_l2Lock)
                    {
                        atmGuidToClose = _activeAtmGuid;
                        if (!string.IsNullOrEmpty(atmGuidToClose)) _activeAtmGuid = null;
                    }
                    if (!string.IsNullOrEmpty(atmGuidToClose))
                    {
                        AtmStrategyClose(atmGuidToClose);
                    }
                    else
                    {
                        // Fallback if we never captured a guid (legacy / external entry)
                        if (Position.MarketPosition == MarketPosition.Long) ExitLong("DEEP6_OppExit");
                        else ExitShort("DEEP6_OppExit");
                    }
                }
                catch (Exception ex) { Print("[DEEP6 Strategy] Exit exception: " + ex.Message); }
            }
        }

        private double GetAccountValue()
        {
            try
            {
                if (Account == null) return 0;
                return Account.Get(AccountItem.NetLiquidation, Currency.UsDollar);
            }
            catch { return 0; }
        }

        protected override void OnPositionUpdate(Position position, double averagePrice, int quantity, MarketPosition marketPosition)
        {
            if (marketPosition == MarketPosition.Flat && quantity == 0)
            {
                Print(string.Format("[DEEP6 Strategy] Position flat. Trades today: {0}/{1}.",
                    _tradesThisSession, MaxTradesPerSession));
            }
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId, double price, int quantity,
            MarketPosition marketPosition, string orderId, DateTime time)
        {
            string orderName = (execution != null && execution.Order != null) ? execution.Order.Name : "?";
            Print(string.Format("[DEEP6 Strategy] Execution: {0} {1} @ {2:F2} qty {3} (orderId={4})",
                marketPosition, orderName, price, quantity, orderId));
            // When the bracket fully exits the position, drop our active-bracket handle.
            if (marketPosition == MarketPosition.Flat && Position.Quantity == 0)
                _activeAtmGuid = null;
        }

        #region Properties

        [NinjaScriptProperty]
        [Display(Name = "Enable Live Trading", Order = 1, GroupName = "1. Safety",
                 Description = "MUST be true for orders to actually submit. Default false (dry-run).")]
        public bool EnableLiveTrading { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Approved Account Name", Order = 2, GroupName = "1. Safety",
                 Description = "Strategy refuses to trade unless current account name matches exactly. Default 'Sim101'.")]
        public string ApprovedAccountName { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Max Contracts Per Trade", Order = 3, GroupName = "1. Safety")]
        public int MaxContractsPerTrade { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Max Trades Per Session", Order = 4, GroupName = "1. Safety")]
        public int MaxTradesPerSession { get; set; }

        [NinjaScriptProperty]
        [Range(50, 10000)]
        [Display(Name = "Daily Loss Cap ($)", Order = 5, GroupName = "1. Safety",
                 Description = "Strategy stops trading for the day if session P&L drops below this many dollars (negative).")]
        public double DailyLossCapDollars { get; set; }

        [NinjaScriptProperty]
        [Range(0, 23)]
        [Display(Name = "RTH Start Hour (NY)", Order = 10, GroupName = "2. Window")]
        public int RthStartHour { get; set; }

        [NinjaScriptProperty]
        [Range(0, 59)]
        [Display(Name = "RTH Start Minute", Order = 11, GroupName = "2. Window")]
        public int RthStartMinute { get; set; }

        [NinjaScriptProperty]
        [Range(0, 23)]
        [Display(Name = "RTH End Hour (NY)", Order = 12, GroupName = "2. Window")]
        public int RthEndHour { get; set; }

        [NinjaScriptProperty]
        [Range(0, 59)]
        [Display(Name = "RTH End Minute", Order = 13, GroupName = "2. Window")]
        public int RthEndMinute { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Min Bars Between Entries", Order = 14, GroupName = "2. Window")]
        public int MinBarsBetweenEntries { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Respect News Blackouts", Order = 15, GroupName = "2. Window",
                 Description = "Skip entries during 08:25-08:40, 10:00-10:05, 14:00-14:15 NY time")]
        public bool RespectNewsBlackouts { get; set; }

        [NinjaScriptProperty]
        [Range(5.0, 80.0)]
        [Display(Name = "Absorption Wick Min %", Order = 20, GroupName = "3. Detection")]
        public double AbsorbWickMinPct { get; set; }

        [NinjaScriptProperty]
        [Range(5.0, 80.0)]
        [Display(Name = "Exhaustion Wick Min %", Order = 21, GroupName = "3. Detection")]
        public double ExhaustWickMinPct { get; set; }

        [NinjaScriptProperty]
        [Range(0.5, 1.0)]
        [Display(Name = "VA-Extreme Strength Threshold", Order = 22, GroupName = "3. Detection")]
        [System.Obsolete("Phase 18-03: scorer-driven entry replaces hardcoded VA-EXTREME rule. Retained to avoid breaking saved strategy configs.")]
        public double ConfluenceVaExtremeStrength { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Wall Proximity (ticks)", Order = 23, GroupName = "3. Detection")]
        [System.Obsolete("Phase 18-03: scorer-driven entry replaces hardcoded WALL-ANCHORED rule. Retained to avoid breaking saved strategy configs.")]
        public int ConfluenceWallProximityTicks { get; set; }

        [NinjaScriptProperty]
        [Range(10, 5000)]
        [Display(Name = "Liquidity Wall Min Size", Order = 24, GroupName = "3. Detection")]
        public int LiquidityWallMin { get; set; }

        // ---- Phase 18-03: Scorer entry gate ----

        [NinjaScriptProperty]
        [Range(0.0, 100.0)]
        [Display(Name = "Score Entry Threshold", Order = 1, GroupName = "5. Score",
                 Description = "Minimum TotalScore required to fire an entry. R1: 70.0 (round1 meta-optimization walk-forward optimum, was 60.0).")]
        public double ScoreEntryThreshold { get; set; } = 70.0;

        [NinjaScriptProperty]
        [Display(Name = "Min Tier For Entry", Order = 2, GroupName = "5. Score",
                 Description = "Minimum SignalTier required to fire an entry. P0-4: TYPE_B default (was TYPE_A).")]
        public SignalTier MinTierForEntry { get; set; } = SignalTier.TYPE_B;

        // ---- R1/R2: Entry filters (Group "2. Entry" per PRODUCTION-CONFIG.md) ----

        [NinjaScriptProperty]
        [Display(Name = "Strict Direction Enabled", Order = 5, GroupName = "2. Entry",
                 Description = "R1: when true, any signal opposing the dominant direction vetoes entry. Delta Sharpe +19.601. Source: SIGNAL-FILTER.md section 5.")]
        public bool StrictDirectionEnabled { get; set; } = true;

        [NinjaScriptProperty]
        [Range(0, 2359)]
        [Display(Name = "Blackout Window Start (HHMM)", Order = 6, GroupName = "2. Entry",
                 Description = "R1: start of time-of-day blackout window as HHMM int (e.g. 1530 = 15:30 ET). Source: ENTRY-TIMING.md.")]
        public int BlackoutWindowStart { get; set; } = 1530;

        [NinjaScriptProperty]
        [Range(0, 2359)]
        [Display(Name = "Blackout Window End (HHMM)", Order = 7, GroupName = "2. Entry",
                 Description = "R1: end of time-of-day blackout window as HHMM int inclusive (e.g. 1600 = 16:00 ET).")]
        public int BlackoutWindowEnd { get; set; } = 1600;

        // ---- R1/R2: Exit management (Group "3. Exit" per PRODUCTION-CONFIG.md) ----

        [NinjaScriptProperty]
        [Range(1, 200)]
        [Display(Name = "Stop Loss (ticks)", Order = 1, GroupName = "3. Exit",
                 Description = "R1: fixed stop-loss distance in ticks. Default 20 (=$100/contract). Source: EXIT-STRATEGY.md stop analysis.")]
        public int StopLossTicks { get; set; } = 20;

        [NinjaScriptProperty]
        [Display(Name = "Scale Out Enabled", Order = 2, GroupName = "3. Exit",
                 Description = "R1: exit ScaleOutPercent of position at ScaleOutTargetTicks; hold remainder to TargetTicks. Requires DEEP6_Confluence ATM template with 2-target setup.")]
        public bool ScaleOutEnabled { get; set; } = true;

        [NinjaScriptProperty]
        [Range(0.1, 0.9)]
        [Display(Name = "Scale Out Percent", Order = 3, GroupName = "3. Exit",
                 Description = "R1: fraction of position to exit at T1 partial target. Default 0.5 (50%).")]
        public double ScaleOutPercent { get; set; } = 0.5;

        [NinjaScriptProperty]
        [Range(1, 200)]
        [Display(Name = "Scale Out Target (ticks, T1)", Order = 4, GroupName = "3. Exit",
                 Description = "R1: first target in ticks for partial exit (T1). Default 16. Source: EXIT-STRATEGY.md Experiment 4 winner.")]
        public int ScaleOutTargetTicks { get; set; } = 16;

        [NinjaScriptProperty]
        [Range(1, 400)]
        [Display(Name = "Target Ticks (T2 final)", Order = 5, GroupName = "3. Exit",
                 Description = "R1: final target in ticks for the held position (T2). Default 32. Source: EXIT-STRATEGY.md scale-out winner.")]
        public int TargetTicks { get; set; } = 32;

        [NinjaScriptProperty]
        [Display(Name = "Breakeven Enabled", Order = 6, GroupName = "3. Exit",
                 Description = "R1: when MFE reaches BreakevenActivationTicks, move stop to entry + BreakevenOffsetTicks. Source: EXIT-STRATEGY.md Experiment 3 winner.")]
        public bool BreakevenEnabled { get; set; } = true;

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "Breakeven Activation (ticks MFE)", Order = 7, GroupName = "3. Exit",
                 Description = "R1: MFE in ticks at which breakeven stop is armed. Default 10. Source: EXIT-STRATEGY.md.")]
        public int BreakevenActivationTicks { get; set; } = 10;

        [NinjaScriptProperty]
        [Range(0, 20)]
        [Display(Name = "Breakeven Offset (ticks above entry)", Order = 8, GroupName = "3. Exit",
                 Description = "R1: ticks above entry for the breakeven stop (absorbs 1-tick slippage). Default 2. Source: EXIT-STRATEGY.md lock+2t result.")]
        public int BreakevenOffsetTicks { get; set; } = 2;

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "Max Bars In Trade", Order = 9, GroupName = "3. Exit",
                 Description = "R1: maximum bars to hold a position before forced flat exit. Default 60. Source: OPTIMIZATION-REPORT.md rank-1 config.")]
        public int MaxBarsInTrade { get; set; } = 60;

        [NinjaScriptProperty]
        [Range(0.0, 1.0)]
        [Display(Name = "Exit On Opposing Score", Order = 10, GroupName = "3. Exit",
                 Description = "Opposing-direction score threshold that triggers an early exit. Default 0.3. Source: OPTIMIZATION-REPORT.md rank-1 config.")]
        public double ExitOnOpposingScore { get; set; } = 0.3;

        // ---- R1/R2: Regime filters (Group "4. Filters" per PRODUCTION-CONFIG.md) ----

        [NinjaScriptProperty]
        [Display(Name = "Vol Surge Veto Enabled", Order = 1, GroupName = "4. Filters",
                 Description = "R1: P0-3 VOLP-03 session-level veto. Blocks all entries in any session where VOLP-03 fires. Source: SIGNAL-ATTRIBUTION.md 0% win rate, SIGNAL-FILTER.md +18.921 delta Sharpe.")]
        public bool VolSurgeVetoEnabled { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Slow Grind Veto Enabled", Order = 2, GroupName = "4. Filters",
                 Description = "R1: P0-5 slow-grind ATR veto. Blocks entry when current ATR < SlowGrindAtrRatio × session average ATR. Source: REGIME-ANALYSIS.md.")]
        public bool SlowGrindVetoEnabled { get; set; } = true;

        [NinjaScriptProperty]
        [Range(0.1, 1.0)]
        [Display(Name = "Slow Grind ATR Ratio", Order = 3, GroupName = "4. Filters",
                 Description = "R1: block entry when bar ATR < this ratio × session avg ATR. Default 0.5. Source: BacktestConfig default validated across 50 sessions.")]
        public double SlowGrindAtrRatio { get; set; } = 0.5;

        [NinjaScriptProperty]
        [Display(Name = "ATM Template — Absorption", Order = 30, GroupName = "4. ATM Templates")]
        public string AtmTemplateAbsorption { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ATM Template — Exhaustion", Order = 31, GroupName = "4. ATM Templates")]
        public string AtmTemplateExhaustion { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ATM Template — Confluence", Order = 32, GroupName = "4. ATM Templates")]
        public string AtmTemplateConfluence { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ATM Template — Default", Order = 33, GroupName = "4. ATM Templates")]
        public string AtmTemplateDefault { get; set; }

        // ---- Phase 17 migration flag ----
        // Default true: Phase 17 Wave 5 session-replay parity PASSED (180/180 tests).
        // Legacy ABS/EXH path marked [Obsolete]; scheduled for removal in Phase 18.
        // See 17-05-PARITY-REPORT.md for full parity verdict.
        [NinjaScriptProperty]
        [Display(Name = "UseNewRegistry", Order = 100, GroupName = "DEEP6 Migration",
                 Description = "Phase 17 migration flag. Default true = full Wave 1-5 registry path (ENG-02..07). " +
                               "Flipped to true after Wave 5 session-replay parity PASSED 2026-04-15.")]
        public bool UseNewRegistry { get; set; } = true;

        #endregion
    }
}

// Note: NinjaTrader Strategies do NOT use a generated factory region (unlike Indicators).
// CacheIndicator<T> requires T : Indicator, which would fail constraint check on Strategy subclass.
// NT8 instantiates strategies directly via reflection on State.SetDefaults.
