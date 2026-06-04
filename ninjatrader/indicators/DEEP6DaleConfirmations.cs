#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.BarsTypes;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class DEEP6DaleConfirmations : Indicator
    {
        private Series<double> maxCellVolSeries;
        private Series<double> deltaSeries;
        private Series<double> cumDeltaSeries;
        private Series<double> hasAbsorptionSeries;
        private Series<double> supportBidSeries;
        private Series<double> resistanceAskSeries;
        private Series<double> absorptionPriceSeries;
        private Swing _swing;
        private SimpleFont _labelFont;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "DEEP6 Dale Confirmations";
                Description = "TDOFBars overlay that detects Dale's four confirmation setups using a hidden volumetric series.";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DrawOnPricePanel = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;
                IsSuspendedWhileInactive = true;
                BarsRequiredToPlot = 20;

                VolumetricPeriod = 5;
                LookbackBars = 20;
                LimitMultiplier = 3.0;
                AbsorptionMultiplier = 2.0;
                DeltaThreshold = 200;
                DivergenceLookback = 5;
                SRProximityTicks = 10;
                SwingStrength = 5;
                ShowLimitOrders = true;
                ShowAbsorption = true;
                ShowAggressiveDelta = true;
                ShowCumDeltaDiv = true;
            }
            else if (State == State.Configure)
            {
                AddVolumetric(Instrument.FullName, BarsPeriodType.Minute, VolumetricPeriod, VolumetricDeltaType.BidAsk, 1);
            }
            else if (State == State.DataLoaded)
            {
                maxCellVolSeries = new Series<double>(this, MaximumBarsLookBack.TwoHundredFiftySix);
                deltaSeries = new Series<double>(this, MaximumBarsLookBack.TwoHundredFiftySix);
                cumDeltaSeries = new Series<double>(this, MaximumBarsLookBack.TwoHundredFiftySix);
                hasAbsorptionSeries = new Series<double>(this, MaximumBarsLookBack.TwoHundredFiftySix);
                supportBidSeries = new Series<double>(this, MaximumBarsLookBack.TwoHundredFiftySix);
                resistanceAskSeries = new Series<double>(this, MaximumBarsLookBack.TwoHundredFiftySix);
                absorptionPriceSeries = new Series<double>(this, MaximumBarsLookBack.TwoHundredFiftySix);
                _swing = Swing(SwingStrength);
                _labelFont = new SimpleFont("Consolas", 11);
            }
            else if (State == State.Terminated)
            {
                _labelFont = null;
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress == 1)
            {
                ProcessVolumetricBar();
                return;
            }

            if (BarsInProgress != 0)
                return;

            if (CurrentBar < BarsRequiredToPlot || CurrentBars.Length < 2 || CurrentBars[1] < 0)
                return;

            if (CurrentBar < Math.Max(LookbackBars, DivergenceLookback) + SwingStrength)
                return;

            double proximity = SRProximityTicks * TickSize;
            bool atResistance = _swing.SwingHigh[0] > 0 && Math.Abs(Close[0] - _swing.SwingHigh[0]) <= proximity;
            bool atSupport = _swing.SwingLow[0] > 0 && Math.Abs(Close[0] - _swing.SwingLow[0]) <= proximity;
            if (!atSupport && !atResistance)
                return;

            double rollingAvg = GetRollingAverage(maxCellVolSeries, LookbackBars);
            if (rollingAvg <= 0)
                return;

            if (ShowLimitOrders)
                DrawLimitOrderConfirmation(atSupport, atResistance, rollingAvg);

            if (ShowAbsorption)
                DrawAbsorptionConfirmation(atSupport, atResistance);

            if (ShowAggressiveDelta)
                DrawAggressiveDeltaConfirmation(atSupport, atResistance);

            if (ShowCumDeltaDiv)
                DrawCumulativeDeltaDivergence(atSupport, atResistance);
        }

        private void ProcessVolumetricBar()
        {
            if (CurrentBars[0] < 0 || CurrentBars[1] < 0)
                return;

            VolumetricBarsType volBars = BarsArray[1].BarsType as VolumetricBarsType;
            if (volBars == null || volBars.Volumes == null)
                return;

            try
            {
                dynamic volumeBar = volBars.Volumes[CurrentBars[1]];
                if (volumeBar == null)
                    return;

                double barLow = RoundToTick(Lows[1][0]);
                double barHigh = RoundToTick(Highs[1][0]);
                if (barHigh < barLow)
                    return;

                double supportLevel = _swing != null && _swing.SwingLow[0] > 0 ? RoundToTick(_swing.SwingLow[0]) : barLow;
                double resistanceLevel = _swing != null && _swing.SwingHigh[0] > 0 ? RoundToTick(_swing.SwingHigh[0]) : barHigh;
                double proximity = SRProximityTicks * TickSize;
                double maxCellVol = 0;
                double totalCellVol = 0;
                int cellCount = 0;
                double strongestSupportBid = 0;
                double strongestResistanceAsk = 0;
                double absorptionPrice = 0;
                bool hasAbsorption = false;

                for (double price = barLow; price <= barHigh + TickSize * 0.5; price += TickSize)
                {
                    double roundedPrice = RoundToTick(price);
                    double ask = volumeBar.GetAskVolumeForPrice(roundedPrice);
                    double bid = volumeBar.GetBidVolumeForPrice(roundedPrice);
                    double total = ask + bid;

                    if (total > maxCellVol)
                        maxCellVol = total;

                    totalCellVol += total;
                    cellCount++;

                    if (Math.Abs(roundedPrice - supportLevel) <= proximity && bid > strongestSupportBid)
                        strongestSupportBid = bid;

                    if (Math.Abs(roundedPrice - resistanceLevel) <= proximity && ask > strongestResistanceAsk)
                        strongestResistanceAsk = ask;
                }

                double avgCellVol = cellCount > 0 ? totalCellVol / cellCount : 0;
                if (avgCellVol > 0)
                {
                    double absorptionThreshold = avgCellVol * AbsorptionMultiplier;
                    for (double price = barLow; price <= barHigh + TickSize * 0.5; price += TickSize)
                    {
                        double roundedPrice = RoundToTick(price);
                        double ask = volumeBar.GetAskVolumeForPrice(roundedPrice);
                        double bid = volumeBar.GetBidVolumeForPrice(roundedPrice);
                        if (bid > absorptionThreshold && ask > absorptionThreshold)
                        {
                            hasAbsorption = true;
                            absorptionPrice = roundedPrice;
                            break;
                        }
                    }
                }

                maxCellVolSeries[0] = maxCellVol;
                deltaSeries[0] = volumeBar.BarDelta;
                cumDeltaSeries[0] = volumeBar.CumulativeDelta;
                hasAbsorptionSeries[0] = hasAbsorption ? 1.0 : 0.0;
                supportBidSeries[0] = strongestSupportBid;
                resistanceAskSeries[0] = strongestResistanceAsk;
                absorptionPriceSeries[0] = absorptionPrice;
            }
            catch
            {
            }
        }

        private void DrawLimitOrderConfirmation(bool atSupport, bool atResistance, double rollingAvg)
        {
            double threshold = LimitMultiplier * rollingAvg;
            double maxCellVol = maxCellVolSeries[0];
            if (maxCellVol <= threshold)
                return;

            if (atSupport && supportBidSeries[0] > 0)
                Draw.ArrowUp(this, "D6LimitLong_" + CurrentBar, true, 0, Low[0] - TickSize, Brushes.Lime);

            if (atResistance && resistanceAskSeries[0] > 0)
                Draw.ArrowDown(this, "D6LimitShort_" + CurrentBar, true, 0, High[0] + TickSize, Brushes.Red);
        }

        private void DrawAbsorptionConfirmation(bool atSupport, bool atResistance)
        {
            if (hasAbsorptionSeries[0] <= 0 || absorptionPriceSeries[0] <= 0)
                return;

            if (atSupport || atResistance)
                Draw.Diamond(this, "D6Absorption_" + CurrentBar, true, 0, absorptionPriceSeries[0], Brushes.Cyan);
        }

        private void DrawAggressiveDeltaConfirmation(bool atSupport, bool atResistance)
        {
            if (atSupport && deltaSeries[0] > DeltaThreshold)
                Draw.TriangleUp(this, "D6AggBuy_" + CurrentBar, true, 0, Low[0] - (TickSize * 2.0), Brushes.Green);

            if (atResistance && deltaSeries[0] < -DeltaThreshold)
                Draw.TriangleDown(this, "D6AggSell_" + CurrentBar, true, 0, High[0] + (TickSize * 2.0), Brushes.Orange);
        }

        private void DrawCumulativeDeltaDivergence(bool atSupport, bool atResistance)
        {
            if (CurrentBar < DivergenceLookback)
                return;

            double priorLow = Low[1];
            double priorHigh = High[1];
            double priorCumLow = cumDeltaSeries[1];
            double priorCumHigh = cumDeltaSeries[1];

            for (int barsAgo = 2; barsAgo <= DivergenceLookback; barsAgo++)
            {
                if (Low[barsAgo] < priorLow)
                    priorLow = Low[barsAgo];
                if (High[barsAgo] > priorHigh)
                    priorHigh = High[barsAgo];
                if (cumDeltaSeries[barsAgo] < priorCumLow)
                    priorCumLow = cumDeltaSeries[barsAgo];
                if (cumDeltaSeries[barsAgo] > priorCumHigh)
                    priorCumHigh = cumDeltaSeries[barsAgo];
            }

            bool bullishDiv = atSupport && Low[0] < priorLow && cumDeltaSeries[0] > priorCumLow;
            bool bearishDiv = atResistance && High[0] > priorHigh && cumDeltaSeries[0] < priorCumHigh;

            if (bullishDiv)
            {
                Draw.Text(this, "D6CumDivBull_" + CurrentBar, true, "↑ CumΔ Div", 0, Low[0] - (TickSize * 4.0), 0,
                    Brushes.Lime, _labelFont, TextAlignment.Center, Brushes.Transparent, Brushes.Transparent, 0);
            }

            if (bearishDiv)
            {
                Draw.Text(this, "D6CumDivBear_" + CurrentBar, true, "↓ CumΔ Div", 0, High[0] + (TickSize * 4.0), 0,
                    Brushes.Red, _labelFont, TextAlignment.Center, Brushes.Transparent, Brushes.Transparent, 0);
            }
        }

        private double GetRollingAverage(Series<double> series, int lookback)
        {
            if (lookback <= 0)
                return 0;

            double sum = 0;
            int count = 0;
            int maxBarsAgo = Math.Min(CurrentBar, lookback);
            for (int barsAgo = 1; barsAgo <= maxBarsAgo; barsAgo++)
            {
                double value = series[barsAgo];
                if (value <= 0)
                    continue;
                sum += value;
                count++;
            }

            return count > 0 ? sum / count : 0;
        }

        private double RoundToTick(double price)
        {
            if (TickSize <= 0)
                return price;

            return Math.Round(price / TickSize) * TickSize;
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Volumetric Period", Order = 1, GroupName = "Parameters")]
        public int VolumetricPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "Lookback Bars", Order = 2, GroupName = "Parameters")]
        public int LookbackBars { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20.0)]
        [Display(Name = "Limit Multiplier", Order = 3, GroupName = "Parameters")]
        public double LimitMultiplier { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20.0)]
        [Display(Name = "Absorption Multiplier", Order = 4, GroupName = "Parameters")]
        public double AbsorptionMultiplier { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Delta Threshold", Order = 5, GroupName = "Parameters")]
        public int DeltaThreshold { get; set; }

        [NinjaScriptProperty]
        [Range(2, 50)]
        [Display(Name = "Divergence Lookback", Order = 6, GroupName = "Parameters")]
        public int DivergenceLookback { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "S/R Proximity Ticks", Order = 7, GroupName = "Parameters")]
        public int SRProximityTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "Swing Strength", Order = 8, GroupName = "Parameters")]
        public int SwingStrength { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Limit Orders", Order = 9, GroupName = "Display")]
        public bool ShowLimitOrders { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Absorption", Order = 10, GroupName = "Display")]
        public bool ShowAbsorption { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Aggressive Delta", Order = 11, GroupName = "Display")]
        public bool ShowAggressiveDelta { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Cum Delta Div", Order = 12, GroupName = "Display")]
        public bool ShowCumDeltaDiv { get; set; }
        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.
// Intentionally left empty. NinjaTrader appends the cache wrappers during compile.
#endregion
