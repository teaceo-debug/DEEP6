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
using NinjaTrader.NinjaScript.DrawingTools;
using Brushes = System.Windows.Media.Brushes;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.DEEP6
{
    public class DEEP6Strategy : Strategy
    {
        // ---- Detection state (mirrors indicator) ----
        private readonly Dictionary<int, FootprintBar> _bars = new Dictionary<int, FootprintBar>();
        private double _bestBid = double.NaN, _bestAsk = double.NaN;
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

        private DateTime _lastSessionDate = DateTime.MinValue;

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
                Calculate                    = Calculate.OnEachTick;
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
                EnableLiveTrading            = false;
                ApprovedAccountName          = "Sim101";
                MaxContractsPerTrade         = 1;
                MaxTradesPerSession          = 5;
                DailyLossCapDollars          = 250.0;
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
                _killSwitch = false;
                _tradesThisSession = 0;
                _sessionDate = DateTime.MinValue;

                Print(string.Format("[DEEP6 Strategy] Initialized. EnableLiveTrading={0}, Account={1}, ApprovedAccount={2}",
                    EnableLiveTrading, Account != null ? Account.Name : "?", ApprovedAccountName));
                if (!EnableLiveTrading) Print("[DEEP6 Strategy] DRY RUN — no orders will be submitted. Set EnableLiveTrading=true to go live.");
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
            if (!IsFirstTickOfBar) return;

            int prevIdx = CurrentBar - 1;
            FootprintBar prev;
            if (!_bars.TryGetValue(prevIdx, out prev)) return;

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

            // Run detectors
            var va  = FootprintBar.ComputeValueArea(prev, TickSize);
            var abs = AbsorptionDetector.Detect(prev, _atr, _volEma, _absCfg, va.vah, va.val, TickSize);
            var exh = _exhDetector.Detect(prev, priorBeforePrev, prevIdx, _atr, _exhCfg);

            // Cleanup history
            int cutoff = CurrentBar - 500;
            if (cutoff > 0)
            {
                var stale = _bars.Keys.Where(k => k < cutoff).ToList();
                foreach (var k in stale) _bars.Remove(k);
            }

            if (_killSwitch) return;
            if (Position.MarketPosition != MarketPosition.Flat)
            {
                CheckOpposingExit(abs, exh);
                return;
            }

            EvaluateEntry(prevIdx, abs, exh, va);
        }

        // ---- Confluence / entry decision ----

        private void EvaluateEntry(int barIdx, List<AbsorptionSignal> abs, List<ExhaustionSignal> exh, (double vah, double val) va)
        {
            // Direction-bucket the signals
            int absDir = 0; double absStr = 0; AbsorptionSignal absSig = null;
            foreach (var s in abs)
            {
                if (s.Direction == 0) continue;
                if (Math.Abs(s.Strength) > absStr) { absStr = Math.Abs(s.Strength); absDir = s.Direction; absSig = s; }
            }
            int exhDir = 0; double exhStr = 0; ExhaustionSignal exhSig = null;
            foreach (var s in exh)
            {
                if (s.Direction == 0) continue;
                if (Math.Abs(s.Strength) > exhStr) { exhStr = Math.Abs(s.Strength); exhDir = s.Direction; exhSig = s; }
            }

            // Confluence triggers
            string trigger = null;
            int direction = 0;
            string atmTemplate = AtmTemplateDefault;
            double signalPrice = 0;

            // (a) STACKED: ABS + EXH same direction
            if (absDir != 0 && absDir == exhDir && absStr >= 0.5 && exhStr >= 0.5)
            {
                trigger = "STACKED";
                direction = absDir;
                signalPrice = absSig.Price;
                atmTemplate = AtmTemplateConfluence;
            }
            // (b) VA-EXTREME: absorption at VAH/VAL with strength >= threshold
            else if (absSig != null && absSig.AtVaExtreme && absStr >= ConfluenceVaExtremeStrength)
            {
                trigger = absSig.Wick == "lower" ? "VA-EXTREME-VAL" : "VA-EXTREME-VAH";
                direction = absDir;
                signalPrice = absSig.Price;
                atmTemplate = AtmTemplateAbsorption;
            }
            // (c) WALL-ANCHORED: signal within N ticks of supportive wall
            else if (absSig != null || exhSig != null)
            {
                var sig = absSig != null ? (object)absSig : exhSig;
                int dir = absSig != null ? absSig.Direction : exhSig.Direction;
                double price = absSig != null ? absSig.Price : exhSig.Price;
                double str   = absSig != null ? absSig.Strength : exhSig.Strength;
                if (str >= 0.55 && IsWallAnchored(price, dir))
                {
                    trigger = "WALL-ANCHORED-" + (absSig != null ? "ABS" : "EXH");
                    direction = dir;
                    signalPrice = price;
                    atmTemplate = absSig != null ? AtmTemplateAbsorption : AtmTemplateExhaustion;
                }
            }

            if (trigger == null || direction == 0) return;

            // Risk gates
            if (!RiskGatesPass(direction, signalPrice, trigger, barIdx)) return;

            // Take the trade (or dry-run log)
            EnterWithAtm(direction, atmTemplate, trigger, signalPrice);
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

                // Use the explicit-quantity overload so the strategy's MaxContractsPerTrade wins
                // over whatever quantity the ATM template was saved with.
                AtmStrategyCreate(action, OrderType.Market, MaxContractsPerTrade, 0, 0, TimeInForce.Day,
                    orderId, atmTemplate, atmGuid,
                    (atmCallbackErrorCode, atmCallbackId) =>
                    {
                        if (atmCallbackErrorCode == ErrorCode.NoError)
                        {
                            _activeAtmGuid = atmGuid;
                            _lastEntryBar = CurrentBar;
                            _tradesThisSession++;
                            Print(string.Format("[DEEP6 Strategy] LIVE entry CONFIRMED: {0} qty={1} ATM='{2}' trigger={3} @ {4:F2} atmGuid={5}",
                                side, MaxContractsPerTrade, atmTemplate, trigger, signalPrice, atmGuid));
                        }
                        else
                        {
                            Print(string.Format("[DEEP6 Strategy] LIVE entry REJECTED: ATM='{0}' code={1} (id={2}). Counter NOT incremented.",
                                atmTemplate, atmCallbackErrorCode, atmCallbackId));
                        }
                    });
                Print(string.Format("[DEEP6 Strategy] LIVE entry submitted: {0} qty={1} ATM='{2}' trigger={3} @ {4:F2} (awaiting callback)",
                    side, MaxContractsPerTrade, atmTemplate, trigger, signalPrice));
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
                    if (!string.IsNullOrEmpty(_activeAtmGuid))
                    {
                        AtmStrategyClose(_activeAtmGuid);
                        _activeAtmGuid = null;
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
        public double ConfluenceVaExtremeStrength { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Wall Proximity (ticks)", Order = 23, GroupName = "3. Detection")]
        public int ConfluenceWallProximityTicks { get; set; }

        [NinjaScriptProperty]
        [Range(10, 5000)]
        [Display(Name = "Liquidity Wall Min Size", Order = 24, GroupName = "3. Detection")]
        public int LiquidityWallMin { get; set; }

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

        #endregion
    }
}

// Note: NinjaTrader Strategies do NOT use a generated factory region (unlike Indicators).
// CacheIndicator<T> requires T : Indicator, which would fail constraint check on Strategy subclass.
// NT8 instantiates strategies directly via reflection on State.SetDefaults.
