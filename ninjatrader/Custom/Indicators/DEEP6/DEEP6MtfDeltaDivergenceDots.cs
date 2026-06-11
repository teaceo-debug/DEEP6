#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6MtfDeltaDivergenceDots : Indicator
    {
        private MtfDeltaDivergenceEngine _hourEngine;
        private MtfDeltaDivergenceEngine _fourHourEngine;
        private MtfDeltaDivergenceEngine _dailyEngine;

        private DeltaDivergenceBias _hourBias = DeltaDivergenceBias.Neutral;
        private DeltaDivergenceBias _fourHourBias = DeltaDivergenceBias.Neutral;
        private DeltaDivergenceBias _dailyBias = DeltaDivergenceBias.Neutral;

        private object _hourVolBars;
        private object _fourHourVolBars;
        private object _dailyVolBars;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "DEEP6 MTF Delta Divergence Dots";
                Description = "Multi-timeframe 1H / 4H / Daily delta divergence shown as three simple green/red dots.";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DrawOnPricePanel = true;
                DisplayInDataBox = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = true;
                BarsRequiredToPlot = 20;

                AddPlot(Brushes.Transparent, "CompositeBias");
                AddPlot(Brushes.Transparent, "HourBias");
                AddPlot(Brushes.Transparent, "FourHourBias");
                AddPlot(Brushes.Transparent, "DailyBias");

                PivotLookback = 20;
                MinBarsPerTimeframe = 20;
                MinPriceBreakTicks = 4;
                MinDeltaImprovement = 250;
                CloseConfirmationRatio = 0.50;
                DotOffsetTicks = 6;
                DotSpacingTicks = 4;
                MinAlignedTimeframes = 2;
                ShowNeutralDots = true;
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
            else if (State == State.Terminated)
            {
                if (_hourEngine != null) _hourEngine.Reset();
                if (_fourHourEngine != null) _fourHourEngine.Reset();
                if (_dailyEngine != null) _dailyEngine.Reset();
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

            if (CurrentBar < 1)
                return;

            DeltaDivergenceBias composite = MtfDeltaDivergenceEngine.ToCompositeBias(
                new[] { _hourBias, _fourHourBias, _dailyBias },
                Math.Max(1, Math.Min(3, MinAlignedTimeframes)));

            Values[0][0] = (double)composite;
            Values[1][0] = (double)_hourBias;
            Values[2][0] = (double)_fourHourBias;
            Values[3][0] = (double)_dailyBias;

            DrawDots(composite);
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

        private void DrawDots(DeltaDivergenceBias composite)
        {
            double basePrice = composite == DeltaDivergenceBias.Bullish
                ? Low[0] - (DotOffsetTicks * TickSize)
                : High[0] + (DotOffsetTicks * TickSize);
            double step = DotSpacingTicks * TickSize;
            bool bullishStack = composite == DeltaDivergenceBias.Bullish;

            DrawDotForBias("DEEP6MtfDelta_H1_", _hourBias, basePrice, bullishStack ? -step * 2.0 : 0.0);
            DrawDotForBias("DEEP6MtfDelta_H4_", _fourHourBias, basePrice, bullishStack ? -step : step);
            DrawDotForBias("DEEP6MtfDelta_D1_", _dailyBias, basePrice, bullishStack ? 0.0 : step * 2.0);
        }

        private void DrawDotForBias(string tagPrefix, DeltaDivergenceBias bias, double basePrice, double offset)
        {
            if (bias == DeltaDivergenceBias.Neutral && !ShowNeutralDots)
                return;

            Brush brush = bias == DeltaDivergenceBias.Bullish
                ? Brushes.Lime
                : bias == DeltaDivergenceBias.Bearish
                    ? Brushes.Red
                    : Brushes.DimGray;

            Draw.Dot(this, tagPrefix + CurrentBar, false, 0, basePrice + offset, brush);
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
        [Display(Name = "Pivot Lookback", Order = 10, GroupName = "Parameters")]
        public int PivotLookback { get; set; }

        [NinjaScriptProperty]
        [Range(5, 200)]
        [Display(Name = "Min Bars Per Timeframe", Order = 20, GroupName = "Parameters")]
        public int MinBarsPerTimeframe { get; set; }

        [NinjaScriptProperty]
        [Range(1, 40)]
        [Display(Name = "Min Price Break Ticks", Order = 30, GroupName = "Parameters")]
        public int MinPriceBreakTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Min Delta Improvement", Order = 40, GroupName = "Parameters")]
        public int MinDeltaImprovement { get; set; }

        [NinjaScriptProperty]
        [Range(0.10, 0.90)]
        [Display(Name = "Close Confirmation Ratio", Order = 50, GroupName = "Parameters")]
        public double CloseConfirmationRatio { get; set; }

        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "Min Aligned Timeframes", Order = 60, GroupName = "Parameters")]
        public int MinAlignedTimeframes { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Dot Offset Ticks", Order = 70, GroupName = "Visual")]
        public int DotOffsetTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "Dot Spacing Ticks", Order = 80, GroupName = "Visual")]
        public int DotSpacingTicks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Neutral Dots", Order = 90, GroupName = "Visual")]
        public bool ShowNeutralDots { get; set; }
    }
}

#if !COMPILE_CHECK
#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6.DEEP6MtfDeltaDivergenceDots[] cacheDEEP6MtfDeltaDivergenceDots;
        public DEEP6.DEEP6MtfDeltaDivergenceDots DEEP6MtfDeltaDivergenceDots(int pivotLookback, int minBarsPerTimeframe, int minPriceBreakTicks, int minDeltaImprovement, double closeConfirmationRatio, int minAlignedTimeframes, int dotOffsetTicks, int dotSpacingTicks, bool showNeutralDots)
        {
            return DEEP6MtfDeltaDivergenceDots(Input, pivotLookback, minBarsPerTimeframe, minPriceBreakTicks, minDeltaImprovement, closeConfirmationRatio, minAlignedTimeframes, dotOffsetTicks, dotSpacingTicks, showNeutralDots);
        }

        public DEEP6.DEEP6MtfDeltaDivergenceDots DEEP6MtfDeltaDivergenceDots(ISeries<double> input, int pivotLookback, int minBarsPerTimeframe, int minPriceBreakTicks, int minDeltaImprovement, double closeConfirmationRatio, int minAlignedTimeframes, int dotOffsetTicks, int dotSpacingTicks, bool showNeutralDots)
        {
            if (cacheDEEP6MtfDeltaDivergenceDots != null)
                for (int idx = 0; idx < cacheDEEP6MtfDeltaDivergenceDots.Length; idx++)
                    if (cacheDEEP6MtfDeltaDivergenceDots[idx] != null
                        && cacheDEEP6MtfDeltaDivergenceDots[idx].PivotLookback == pivotLookback
                        && cacheDEEP6MtfDeltaDivergenceDots[idx].MinBarsPerTimeframe == minBarsPerTimeframe
                        && cacheDEEP6MtfDeltaDivergenceDots[idx].MinPriceBreakTicks == minPriceBreakTicks
                        && cacheDEEP6MtfDeltaDivergenceDots[idx].MinDeltaImprovement == minDeltaImprovement
                        && cacheDEEP6MtfDeltaDivergenceDots[idx].CloseConfirmationRatio == closeConfirmationRatio
                        && cacheDEEP6MtfDeltaDivergenceDots[idx].MinAlignedTimeframes == minAlignedTimeframes
                        && cacheDEEP6MtfDeltaDivergenceDots[idx].DotOffsetTicks == dotOffsetTicks
                        && cacheDEEP6MtfDeltaDivergenceDots[idx].DotSpacingTicks == dotSpacingTicks
                        && cacheDEEP6MtfDeltaDivergenceDots[idx].ShowNeutralDots == showNeutralDots
                        && cacheDEEP6MtfDeltaDivergenceDots[idx].EqualsInput(input))
                        return cacheDEEP6MtfDeltaDivergenceDots[idx];
            return CacheIndicator<DEEP6.DEEP6MtfDeltaDivergenceDots>(new DEEP6.DEEP6MtfDeltaDivergenceDots
            {
                PivotLookback = pivotLookback,
                MinBarsPerTimeframe = minBarsPerTimeframe,
                MinPriceBreakTicks = minPriceBreakTicks,
                MinDeltaImprovement = minDeltaImprovement,
                CloseConfirmationRatio = closeConfirmationRatio,
                MinAlignedTimeframes = minAlignedTimeframes,
                DotOffsetTicks = dotOffsetTicks,
                DotSpacingTicks = dotSpacingTicks,
                ShowNeutralDots = showNeutralDots,
            }, input, ref cacheDEEP6MtfDeltaDivergenceDots);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6.DEEP6MtfDeltaDivergenceDots DEEP6MtfDeltaDivergenceDots(int pivotLookback, int minBarsPerTimeframe, int minPriceBreakTicks, int minDeltaImprovement, double closeConfirmationRatio, int minAlignedTimeframes, int dotOffsetTicks, int dotSpacingTicks, bool showNeutralDots)
        {
            return indicator.DEEP6MtfDeltaDivergenceDots(Input, pivotLookback, minBarsPerTimeframe, minPriceBreakTicks, minDeltaImprovement, closeConfirmationRatio, minAlignedTimeframes, dotOffsetTicks, dotSpacingTicks, showNeutralDots);
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.DEEP6.DEEP6MtfDeltaDivergenceDots DEEP6MtfDeltaDivergenceDots(int pivotLookback, int minBarsPerTimeframe, int minPriceBreakTicks, int minDeltaImprovement, double closeConfirmationRatio, int minAlignedTimeframes, int dotOffsetTicks, int dotSpacingTicks, bool showNeutralDots)
        {
            return indicator.DEEP6MtfDeltaDivergenceDots(Input, pivotLookback, minBarsPerTimeframe, minPriceBreakTicks, minDeltaImprovement, closeConfirmationRatio, minAlignedTimeframes, dotOffsetTicks, dotSpacingTicks, showNeutralDots);
        }
    }
}

#endregion
#endif
