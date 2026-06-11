#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.DEEP6
{
    public class DEEP6MtfDeltaDivergenceStrategy : Strategy
    {
        private MtfDeltaDivergenceEngine _hourEngine;
        private MtfDeltaDivergenceEngine _fourHourEngine;
        private MtfDeltaDivergenceEngine _dailyEngine;

        private DeltaDivergenceBias _hourBias = DeltaDivergenceBias.Neutral;
        private DeltaDivergenceBias _fourHourBias = DeltaDivergenceBias.Neutral;
        private DeltaDivergenceBias _dailyBias = DeltaDivergenceBias.Neutral;
        private DeltaDivergenceBias _lastCompositeBias = DeltaDivergenceBias.Neutral;

        private object _hourVolBars;
        private object _fourHourVolBars;
        private object _dailyVolBars;

        private int _entryBar = -1;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "DEEP6 MTF Delta Divergence Strategy";
                Description = "Backtestable companion strategy for the 1H / 4H / Daily delta divergence dots.";
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
                TimeInForce = TimeInForce.Day;
                TraceOrders = false;
                RealtimeErrorHandling = RealtimeErrorHandling.StopCancelClose;
                StopTargetHandling = StopTargetHandling.PerEntryExecution;
                BarsRequiredToTrade = 20;
                IsInstantiatedOnEachOptimizationIteration = false;

                PivotLookback = 20;
                MinBarsPerTimeframe = 20;
                MinPriceBreakTicks = 4;
                MinDeltaImprovement = 250;
                CloseConfirmationRatio = 0.50;
                MinAlignedTimeframes = 2;
                StopLossTicks = 24;
                ProfitTargetTicks = 40;
                MaxBarsInTrade = 24;
                MinBarsBetweenEntries = 3;
                Contracts = 1;
            }
            else if (State == State.Configure)
            {
                AddVolumetric(Instrument.FullName, BarsPeriodType.Minute, 60, VolumetricDeltaType.BidAsk, 1);
                AddVolumetric(Instrument.FullName, BarsPeriodType.Minute, 240, VolumetricDeltaType.BidAsk, 1);
                AddVolumetric(Instrument.FullName, BarsPeriodType.Minute, 1440, VolumetricDeltaType.BidAsk, 1);
            }
            else if (State == State.DataLoaded)
            {
                var config = BuildConfig();
                _hourEngine = new MtfDeltaDivergenceEngine(config);
                _fourHourEngine = new MtfDeltaDivergenceEngine(config);
                _dailyEngine = new MtfDeltaDivergenceEngine(config);

                _hourVolBars = BarsArray.Length > 1 ? BarsArray[1].BarsType : null;
                _fourHourVolBars = BarsArray.Length > 2 ? BarsArray[2].BarsType : null;
                _dailyVolBars = BarsArray.Length > 3 ? BarsArray[3].BarsType : null;
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress == 1)
            {
                _hourBias = UpdateTimeframeBias(_hourVolBars, _hourEngine, 1);
                return;
            }

            if (BarsInProgress == 2)
            {
                _fourHourBias = UpdateTimeframeBias(_fourHourVolBars, _fourHourEngine, 2);
                return;
            }

            if (BarsInProgress == 3)
            {
                _dailyBias = UpdateTimeframeBias(_dailyVolBars, _dailyEngine, 3);
                return;
            }

            if (BarsInProgress != 0)
                return;

            if (CurrentBar < BarsRequiredToTrade)
                return;

            DeltaDivergenceBias composite = MtfDeltaDivergenceEngine.ToCompositeBias(
                new[] { _hourBias, _fourHourBias, _dailyBias },
                Math.Max(1, Math.Min(3, MinAlignedTimeframes)));

            if (Position.MarketPosition != MarketPosition.Flat)
            {
                ManageOpenPosition(composite);
                _lastCompositeBias = composite;
                return;
            }

            if (CurrentBar - _entryBar < MinBarsBetweenEntries)
            {
                _lastCompositeBias = composite;
                return;
            }

            if (composite == DeltaDivergenceBias.Neutral || composite == _lastCompositeBias)
            {
                _lastCompositeBias = composite;
                return;
            }

            SetStopLoss(CalculationMode.Ticks, StopLossTicks);
            SetProfitTarget(CalculationMode.Ticks, ProfitTargetTicks);

            if (composite == DeltaDivergenceBias.Bullish)
                EnterLong(Contracts, "MtfDeltaBull");
            else if (composite == DeltaDivergenceBias.Bearish)
                EnterShort(Contracts, "MtfDeltaBear");

            _entryBar = CurrentBar;
            _lastCompositeBias = composite;
        }

        private void ManageOpenPosition(DeltaDivergenceBias composite)
        {
            if (_entryBar >= 0 && CurrentBar - _entryBar >= MaxBarsInTrade)
            {
                if (Position.MarketPosition == MarketPosition.Long)
                    ExitLong("TimedExit", "MtfDeltaBull");
                else if (Position.MarketPosition == MarketPosition.Short)
                    ExitShort("TimedExit", "MtfDeltaBear");
                return;
            }

            if (Position.MarketPosition == MarketPosition.Long && composite == DeltaDivergenceBias.Bearish)
                ExitLong("FlipExit", "MtfDeltaBull");
            else if (Position.MarketPosition == MarketPosition.Short && composite == DeltaDivergenceBias.Bullish)
                ExitShort("FlipExit", "MtfDeltaBear");
        }

        private DeltaDivergenceBias UpdateTimeframeBias(
            object volBars,
            MtfDeltaDivergenceEngine engine,
            int barsArrayIndex)
        {
            if (volBars == null || engine == null)
                return DeltaDivergenceBias.Neutral;

            if (CurrentBars.Length <= barsArrayIndex || CurrentBars[barsArrayIndex] < 0)
                return engine.CurrentBias;

            int barIndex = CurrentBars[barsArrayIndex];
            long? barDelta = TryGetBarDelta(volBars, barIndex);
            if (!barDelta.HasValue)
                return engine.CurrentBias;

            return engine.AddBar(new DeltaDivergenceBar(
                Highs[barsArrayIndex][0],
                Lows[barsArrayIndex][0],
                Closes[barsArrayIndex][0],
                barDelta.Value));
        }

        private static long? TryGetBarDelta(object volBars, int barIndex)
        {
            if (volBars == null || barIndex < 0)
                return null;

            var volumesProperty = volBars.GetType().GetProperty("Volumes");
            if (volumesProperty == null)
                return null;

            var volumes = volumesProperty.GetValue(volBars, null) as System.Collections.IList;
            if (volumes == null || barIndex >= volumes.Count)
                return null;

            object volumeBar = volumes[barIndex];
            if (volumeBar == null)
                return null;

            var barDeltaProperty = volumeBar.GetType().GetProperty("BarDelta");
            if (barDeltaProperty == null)
                return null;

            object rawDelta = barDeltaProperty.GetValue(volumeBar, null);
            if (rawDelta == null)
                return null;

            return Convert.ToInt64(rawDelta);
        }

        private MtfDeltaDivergenceConfig BuildConfig()
        {
            return new MtfDeltaDivergenceConfig
            {
                PivotLookback = PivotLookback,
                MinBars = MinBarsPerTimeframe,
                TickSize = TickSize,
                MinPriceBreakTicks = MinPriceBreakTicks,
                MinDeltaImprovement = MinDeltaImprovement,
                CloseConfirmationRatio = CloseConfirmationRatio,
            };
        }

        [NinjaScriptProperty]
        [Range(5, 200)]
        [Display(Name = "Pivot Lookback", Order = 10, GroupName = "Signal")]
        public int PivotLookback { get; set; }

        [NinjaScriptProperty]
        [Range(5, 200)]
        [Display(Name = "Min Bars Per Timeframe", Order = 20, GroupName = "Signal")]
        public int MinBarsPerTimeframe { get; set; }

        [NinjaScriptProperty]
        [Range(1, 40)]
        [Display(Name = "Min Price Break Ticks", Order = 30, GroupName = "Signal")]
        public int MinPriceBreakTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Min Delta Improvement", Order = 40, GroupName = "Signal")]
        public int MinDeltaImprovement { get; set; }

        [NinjaScriptProperty]
        [Range(0.10, 0.90)]
        [Display(Name = "Close Confirmation Ratio", Order = 50, GroupName = "Signal")]
        public double CloseConfirmationRatio { get; set; }

        [NinjaScriptProperty]
        [Range(1, 3)]
        [Display(Name = "Min Aligned Timeframes", Order = 60, GroupName = "Signal")]
        public int MinAlignedTimeframes { get; set; }

        [NinjaScriptProperty]
        [Range(1, 200)]
        [Display(Name = "Stop Loss Ticks", Order = 70, GroupName = "Risk")]
        public int StopLossTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 400)]
        [Display(Name = "Profit Target Ticks", Order = 80, GroupName = "Risk")]
        public int ProfitTargetTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 200)]
        [Display(Name = "Max Bars In Trade", Order = 90, GroupName = "Risk")]
        public int MaxBarsInTrade { get; set; }

        [NinjaScriptProperty]
        [Range(0, 50)]
        [Display(Name = "Min Bars Between Entries", Order = 100, GroupName = "Risk")]
        public int MinBarsBetweenEntries { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Contracts", Order = 110, GroupName = "Risk")]
        public int Contracts { get; set; }
    }
}
