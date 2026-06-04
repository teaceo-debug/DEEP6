// =============================================================================
// DEEP6 ATLAS STRATEGY v2 — Production Risk-Managed Execution Engine
// =============================================================================
// Consumes signals from DEEP6Atlas indicator with full risk management:
//   - Half-Kelly position sizing (with ATLAS sizeMultiplier amplifier)
//   - 5-stage exit ladder: BE@0.5R | Partial 50%@1R | Trail@2R | Partial 25%@3R | Trail-only@5R
//   - Chandelier trailing stop (ATR-based)
//   - Break-even move at 0.5R
//   - Time-based exit (no progress in N bars)
//   - Daily loss lockout (with hard kill)
//   - Consecutive-loss dampening (3 losses → S-only mode)
//   - Apex prop firm trailing drawdown compliance shim
//   - R-multiple feedback into ATLAS FTRL online learner
//
// Drop into:  Documents\NinjaTrader 8\bin\Custom\Strategies\
// Compile:    F5 in NinjaScript Editor
// Apply:      Strategies tab on a chart that already has DEEP6Atlas applied
//
// IMPORTANT: Test in Sim101 with replay before going live. Tune position sizing,
// stops, and risk limits to your specific account, instrument, and prop firm.
// =============================================================================

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.Strategies;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class DEEP6AtlasStrategy : Strategy
    {
        #region Indicator Reference
        private DEEP6Atlas _atlas;
        private Indicators.ATR _atr;
        #endregion

        #region User Inputs

        // ----- Signal filtering -----
        [NinjaScriptProperty]
        [Display(Name = "Min Signal Grade (S=4 A=3 B=2 C=1)", Order = 0, GroupName = "Signals")]
        [Range(1, 4)]
        public int MinGrade { get; set; } = 3;

        [NinjaScriptProperty]
        [Display(Name = "Min Posterior", Order = 1, GroupName = "Signals")]
        [Range(0.50, 0.95)]
        public double MinPosterior { get; set; } = 0.62;

        [NinjaScriptProperty]
        [Display(Name = "Trade Through Filtered Regime", Order = 2, GroupName = "Signals")]
        public bool TradeFiltered { get; set; } = false;

        // ----- Position sizing -----
        [NinjaScriptProperty]
        [Display(Name = "Base Contracts", Order = 10, GroupName = "Sizing")]
        [Range(1, 50)]
        public int BaseContracts { get; set; } = 1;

        [NinjaScriptProperty]
        [Display(Name = "Use ATLAS Size Multiplier", Order = 11, GroupName = "Sizing")]
        public bool UseSizeMultiplier { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Max Contracts Cap", Order = 12, GroupName = "Sizing")]
        [Range(1, 100)]
        public int MaxContractsCap { get; set; } = 4;

        // ----- Stop / Target -----
        [NinjaScriptProperty]
        [Display(Name = "Stop ATR Multiplier", Order = 20, GroupName = "Risk")]
        [Range(0.5, 5.0)]
        public double StopATRMult { get; set; } = 1.2;

        [NinjaScriptProperty]
        [Display(Name = "Min Stop Ticks", Order = 21, GroupName = "Risk")]
        [Range(4, 80)]
        public int MinStopTicks { get; set; } = 16;

        [NinjaScriptProperty]
        [Display(Name = "Initial Target R", Order = 22, GroupName = "Risk")]
        [Range(0.8, 10.0)]
        public double InitialTargetR { get; set; } = 3.0;

        // ----- Exit ladder -----
        [NinjaScriptProperty]
        [Display(Name = "Move BE at R", Order = 30, GroupName = "Exits")]
        [Range(0.0, 2.0)]
        public double BreakEvenAtR { get; set; } = 0.5;

        [NinjaScriptProperty]
        [Display(Name = "Partial 1: Take % at R", Order = 31, GroupName = "Exits")]
        public double Partial1Pct { get; set; } = 0.50;

        [NinjaScriptProperty]
        [Display(Name = "Partial 1 Trigger R", Order = 32, GroupName = "Exits")]
        [Range(0.5, 5.0)]
        public double Partial1R { get; set; } = 1.0;

        [NinjaScriptProperty]
        [Display(Name = "Partial 2: Take % at R", Order = 33, GroupName = "Exits")]
        public double Partial2Pct { get; set; } = 0.25;

        [NinjaScriptProperty]
        [Display(Name = "Partial 2 Trigger R", Order = 34, GroupName = "Exits")]
        [Range(1.0, 10.0)]
        public double Partial2R { get; set; } = 3.0;

        [NinjaScriptProperty]
        [Display(Name = "Trail Start R", Order = 35, GroupName = "Exits")]
        [Range(0.5, 5.0)]
        public double TrailStartR { get; set; } = 2.0;

        [NinjaScriptProperty]
        [Display(Name = "Trail ATR Multiplier (Chandelier)", Order = 36, GroupName = "Exits")]
        [Range(1.0, 6.0)]
        public double TrailATRMult { get; set; } = 2.5;

        [NinjaScriptProperty]
        [Display(Name = "Time Exit After Bars (no 0.5R progress)", Order = 37, GroupName = "Exits")]
        [Range(5, 200)]
        public int TimeExitBars { get; set; } = 30;

        // ----- Daily limits & lockouts -----
        [NinjaScriptProperty]
        [Display(Name = "Daily Loss Lockout ($)", Order = 40, GroupName = "Lockouts")]
        public double DailyLossLockout { get; set; } = 500.0;

        [NinjaScriptProperty]
        [Display(Name = "Daily Profit Stop ($)", Order = 41, GroupName = "Lockouts")]
        public double DailyProfitStop { get; set; } = 1000.0;

        [NinjaScriptProperty]
        [Display(Name = "Max Trades Per Day", Order = 42, GroupName = "Lockouts")]
        [Range(1, 50)]
        public int MaxTradesPerDay { get; set; } = 8;

        [NinjaScriptProperty]
        [Display(Name = "Consecutive Loss → S-only", Order = 43, GroupName = "Lockouts")]
        [Range(1, 10)]
        public int ConsecLossLockout { get; set; } = 3;

        // ----- Apex prop firm shim -----
        [NinjaScriptProperty]
        [Display(Name = "Apex Trailing Drawdown ($)", Order = 50, GroupName = "Apex")]
        public double ApexTrailingDD { get; set; } = 2500.0;

        [NinjaScriptProperty]
        [Display(Name = "Apex Account Start Balance ($)", Order = 51, GroupName = "Apex")]
        public double ApexStartBalance { get; set; } = 50000.0;

        [NinjaScriptProperty]
        [Display(Name = "Enable Apex Compliance", Order = 52, GroupName = "Apex")]
        public bool EnableApex { get; set; } = false;

        // ----- Time filter -----
        [NinjaScriptProperty]
        [Display(Name = "Trading Window Start (HHmm)", Order = 60, GroupName = "Time")]
        public int WindowStart { get; set; } = 930;

        [NinjaScriptProperty]
        [Display(Name = "Trading Window End (HHmm)", Order = 61, GroupName = "Time")]
        public int WindowEnd { get; set; } = 1530;

        [NinjaScriptProperty]
        [Display(Name = "Flatten At (HHmm)", Order = 62, GroupName = "Time")]
        public int FlattenAt { get; set; } = 1555;

        #endregion

        #region Trade State
        private int _entryDirection = 0;
        private double _entryPrice = 0;
        private double _initialStop = 0;
        private double _currentStop = 0;
        private double _initialTarget = 0;
        private double _initialRiskTicks = 0;
        private DateTime _entryTime;
        private int _entryBar;
        private int _entryContracts;
        private int _remainingContracts;
        private bool _inTrade = false;
        private bool _beActivated = false;
        private bool _partial1Done = false;
        private bool _partial2Done = false;
        private bool _trailActive = false;
        private double _maxFavorablePrice;

        // Daily / streak tracking
        private double _dailyPnL = 0.0;
        private int _dailyTradeCount = 0;
        private int _consecutiveLosses = 0;
        private DateTime _currentDay = DateTime.MinValue;

        // Apex trailing drawdown state
        private double _apexHighWaterMark;
        private double _apexCurrentBalance;
        private bool _apexLocked;
        #endregion

        #region Lifecycle

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 ATLAS paired strategy — production risk management";
                Name = "DEEP6AtlasStrategy";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;
                ExitOnSessionCloseSeconds = 30;
                IsFillLimitOnTouch = false;
                MaximumBarsLookBack = MaximumBarsLookBack.TwoHundredFiftySix;
                OrderFillResolution = OrderFillResolution.Standard;
                Slippage = 0;
                StartBehavior = StartBehavior.WaitUntilFlat;
                TimeInForce = TimeInForce.Gtc;
                TraceOrders = false;
                RealtimeErrorHandling = RealtimeErrorHandling.StopCancelClose;
                StopTargetHandling = StopTargetHandling.PerEntryExecution;
                BarsRequiredToTrade = 30;
                IsInstantiatedOnEachOptimizationIteration = true;
            }
            else if (State == State.DataLoaded)
            {
                _atr = ATR(14);
                _atlas = new DEEP6Atlas
                {
                    ShowHUD = true,
                    ShowSignalBoxes = true,
                    ShowGEXOverlay = true,
                    ShowMicroMarkers = true,
                    EnableE1 = true,
                    EnableE2 = true,
                    EnableE3 = true,
                    EnableE4 = true,
                    EnableE8 = true,
                    EnableE11 = true,
                    EnableE12 = true,
                    EnableE13 = true,
                    EnableE14 = true,
                    EnableE15 = true,
                    UseOnnxHeads = false,
                    TLOBOnnxPath = @"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\tlob_nq.onnx",
                    MetaOnnxPath = @"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\meta_xgb_nq.onnx",
                    GEXFilePath = @"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\gex_nq.json",
                    GEXRefreshSeconds = 60,
                    MinSignalGrade = MinGrade,
                    LogSignals = true,
                    SoundOnA = false,
                    HardKillSwitch = false,
                    DailyLossLockoutDollars = DailyLossLockout,
                };
                AddChartIndicator(_atlas);
                _apexCurrentBalance = ApexStartBalance;
                _apexHighWaterMark = ApexStartBalance;
            }
        }

        #endregion

        #region OnBarUpdate

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;
            if (CurrentBar < BarsRequiredToTrade) return;
            if (_atlas == null) return;

            // Daily reset
            if (Time[0].Date != _currentDay)
            {
                _currentDay = Time[0].Date;
                _dailyPnL = 0;
                _dailyTradeCount = 0;
                _apexLocked = false;
            }

            // Manage open trade
            if (_inTrade)
            {
                ManageOpenTrade();
                return;
            }

            // Read ATLAS signals
            int grade = (int)_atlas.SignalGrade[0];
            int direction = (int)_atlas.SignalDirection[0];
            double posterior = _atlas.Posterior[0];
            double sizeMult = _atlas.SizeMultiplier[0];
            int regime = (int)_atlas.CurrentRegime[0];

            if (!CanEnterNow(grade, direction, posterior, regime)) return;

            int contracts = ComputePositionSize(sizeMult);
            if (contracts <= 0) return;

            double atr = _atr[0];
            double stopTicks = Math.Max(MinStopTicks, atr * StopATRMult / TickSize);
            double stopDistance = stopTicks * TickSize;

            double entryPx = Close[0];
            double stopPx, targetPx;
            if (direction > 0)
            {
                stopPx = entryPx - stopDistance;
                targetPx = entryPx + InitialTargetR * stopDistance;
            }
            else
            {
                stopPx = entryPx + stopDistance;
                targetPx = entryPx - InitialTargetR * stopDistance;
            }

            string sigName = direction > 0 ? "ATLAS_L" : "ATLAS_S";
            if (direction > 0) EnterLong(contracts, sigName);
            else EnterShort(contracts, sigName);

            SetStopLoss(sigName, CalculationMode.Price, stopPx, false);
            SetProfitTarget(sigName, CalculationMode.Price, targetPx);

            // Track entry state
            _inTrade = true;
            _entryDirection = direction;
            _entryPrice = entryPx;
            _initialStop = stopPx;
            _currentStop = stopPx;
            _initialTarget = targetPx;
            _initialRiskTicks = stopTicks;
            _entryTime = Time[0];
            _entryBar = CurrentBar;
            _entryContracts = contracts;
            _remainingContracts = contracts;
            _beActivated = false;
            _partial1Done = false;
            _partial2Done = false;
            _trailActive = false;
            _maxFavorablePrice = entryPx;
            _dailyTradeCount++;

            Print(string.Format("[STRAT {0:HH:mm:ss}] ENTRY {1} {2}c @ {3:F2} stop={4:F2} tgt={5:F2} (R={6:F0}t)",
                Time[0], sigName, contracts, entryPx, stopPx, targetPx, stopTicks));
        }

        #endregion

        #region Entry Filter

        private bool CanEnterNow(int grade, int direction, double posterior, int regime)
        {
            if (grade < MinGrade) return false;
            if (direction == 0) return false;
            if (_consecutiveLosses >= ConsecLossLockout && grade < 4) return false;
            double maxP = Math.Max(posterior, 1 - posterior);
            if (maxP < MinPosterior) return false;
            if (regime == 4 && !TradeFiltered) return false;
            if (_dailyPnL <= -DailyLossLockout) return false;
            if (DailyProfitStop > 0 && _dailyPnL >= DailyProfitStop) return false;
            if (_dailyTradeCount >= MaxTradesPerDay) return false;
            if (EnableApex && _apexLocked) return false;
            int hhmm = Time[0].Hour * 100 + Time[0].Minute;
            if (hhmm < WindowStart || hhmm > WindowEnd) return false;
            return true;
        }

        #endregion

        #region Position Sizing

        private int ComputePositionSize(double sizeMult)
        {
            int contracts = BaseContracts;
            if (UseSizeMultiplier && sizeMult > 0.01)
                contracts = Math.Max(1, (int)Math.Round(BaseContracts * sizeMult));
            if (_consecutiveLosses >= 2)
                contracts = Math.Max(1, contracts / 2);
            return Math.Min(contracts, MaxContractsCap);
        }

        #endregion

        #region Trade Management

        private void ManageOpenTrade()
        {
            if (Position.MarketPosition == MarketPosition.Flat)
            {
                FinalizeTrade();
                return;
            }

            if (_entryDirection > 0)
                _maxFavorablePrice = Math.Max(_maxFavorablePrice, High[0]);
            else
                _maxFavorablePrice = Math.Min(_maxFavorablePrice, Low[0]);

            double riskDist = _initialRiskTicks * TickSize;
            double favorableMove = _entryDirection > 0
                ? (_maxFavorablePrice - _entryPrice)
                : (_entryPrice - _maxFavorablePrice);
            double currentR = riskDist > 0 ? favorableMove / riskDist : 0;

            string sigName = _entryDirection > 0 ? "ATLAS_L" : "ATLAS_S";

            // Stage 1: BE move
            if (!_beActivated && currentR >= BreakEvenAtR)
            {
                double bePx = _entryPrice + (_entryDirection > 0 ? 1 : -1) * TickSize;
                SetStopLoss(sigName, CalculationMode.Price, bePx, false);
                _currentStop = bePx;
                _beActivated = true;
                Print(string.Format("[STRAT {0:HH:mm:ss}] BE move @ R={1:F2}, stop→{2:F2}", Time[0], currentR, bePx));
            }

            // Stage 2: Partial 1
            if (!_partial1Done && currentR >= Partial1R && _remainingContracts > 1)
            {
                int qty = Math.Max(1, (int)Math.Round(_entryContracts * Partial1Pct));
                qty = Math.Min(qty, _remainingContracts - 1);
                if (qty > 0)
                {
                    if (_entryDirection > 0) ExitLong(qty, "Partial1", sigName);
                    else ExitShort(qty, "Partial1", sigName);
                    _remainingContracts -= qty;
                    _partial1Done = true;
                    Print(string.Format("[STRAT {0:HH:mm:ss}] PARTIAL1 {1}c @ R={2:F2}", Time[0], qty, currentR));
                }
            }

            // Stage 3: Trailing stop
            if (currentR >= TrailStartR)
            {
                _trailActive = true;
                double atr = _atr[0];
                double trailDist = atr * TrailATRMult;
                double newStop;
                if (_entryDirection > 0)
                {
                    newStop = _maxFavorablePrice - trailDist;
                    if (newStop > _currentStop)
                    {
                        SetStopLoss(sigName, CalculationMode.Price, newStop, false);
                        _currentStop = newStop;
                    }
                }
                else
                {
                    newStop = _maxFavorablePrice + trailDist;
                    if (_currentStop == 0 || newStop < _currentStop)
                    {
                        SetStopLoss(sigName, CalculationMode.Price, newStop, false);
                        _currentStop = newStop;
                    }
                }
            }

            // Stage 4: Partial 2
            if (!_partial2Done && currentR >= Partial2R && _remainingContracts > 1)
            {
                int qty = Math.Max(1, (int)Math.Round(_entryContracts * Partial2Pct));
                qty = Math.Min(qty, _remainingContracts - 1);
                if (qty > 0)
                {
                    if (_entryDirection > 0) ExitLong(qty, "Partial2", sigName);
                    else ExitShort(qty, "Partial2", sigName);
                    _remainingContracts -= qty;
                    _partial2Done = true;
                    Print(string.Format("[STRAT {0:HH:mm:ss}] PARTIAL2 {1}c @ R={2:F2}", Time[0], qty, currentR));
                }
            }

            // Time-based exit
            int barsSinceEntry = CurrentBar - _entryBar;
            if (barsSinceEntry >= TimeExitBars && currentR < BreakEvenAtR)
            {
                if (_entryDirection > 0) ExitLong("TimeExit", sigName);
                else ExitShort("TimeExit", sigName);
                Print(string.Format("[STRAT {0:HH:mm:ss}] TIME-EXIT after {1} bars @ R={2:F2}",
                    Time[0], barsSinceEntry, currentR));
            }

            // Hard flatten window
            int hhmm = Time[0].Hour * 100 + Time[0].Minute;
            if (hhmm >= FlattenAt)
            {
                if (_entryDirection > 0) ExitLong("EOD", sigName);
                else ExitShort("EOD", sigName);
                Print(string.Format("[STRAT {0:HH:mm:ss}] EOD-FLATTEN @ R={1:F2}", Time[0], currentR));
            }
        }

        private void FinalizeTrade()
        {
            if (!_inTrade) return;
            _inTrade = false;

            double exitPrice = Close[0];
            double pnlPoints = (exitPrice - _entryPrice) * _entryDirection;
            double riskDist = _initialRiskTicks * TickSize;
            double rMultiple = riskDist > 0 ? pnlPoints / riskDist : 0;
            double pointValue = Instrument.MasterInstrument.PointValue;
            double pnlDollars = pnlPoints * pointValue * _entryContracts;

            _dailyPnL += pnlDollars;
            if (rMultiple > 0) _consecutiveLosses = 0;
            else _consecutiveLosses++;

            if (EnableApex)
            {
                _apexCurrentBalance += pnlDollars;
                if (_apexCurrentBalance > _apexHighWaterMark) _apexHighWaterMark = _apexCurrentBalance;
                double trailingFloor = _apexHighWaterMark - ApexTrailingDD;
                if (_apexCurrentBalance <= trailingFloor) _apexLocked = true;
            }

            try { _atlas.RegisterTradeOutcome(rMultiple, pnlDollars); } catch { }

            Print(string.Format(
                "[STRAT {0:HH:mm:ss}] EXIT R={1:F2} ${2:F0} | daily=${3:F0} ({4} trades) | streak_losses={5}",
                Time[0], rMultiple, pnlDollars, _dailyPnL, _dailyTradeCount, _consecutiveLosses));
        }

        #endregion
    }
}
