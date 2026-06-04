#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.BarsTypes;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class StackedZone
    {
        public double PriceLow;
        public double PriceHigh;
        public bool IsBull;
    }

    public class DEEP6DaleConfluence : Indicator
    {
        private const string HudTag = "DEEP6DaleConfluenceHUD";
        private const int MaxPocHistory = 128;
        private const int MaxStackedZones = 128;
        private const int StackedMinCount = 3;

        private Series<double> scoreSeries;
        private Series<double> cumDeltaSeries;
        private Series<double> barDeltaSeries;
        private SimpleFont hudFont;
        private List<double> pocHistory;
        private List<StackedZone> stackedZones;
        private int lastComputedPrimaryBar;
        private int lastBuyImbalanceCount;
        private int lastSellImbalanceCount;
        private double lastBarDelta;
        private double lastCumDelta;
        private double lastScore;

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> Score
        {
            get { return Values[0]; }
        }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "DEEP6 Dale Confluence";
                Description = "Separate-panel Trader Dale confluence histogram using a hidden secondary volumetric series.";
                Calculate = Calculate.OnBarClose;
                IsOverlay = false;
                DrawOnPricePanel = false;
                DisplayInDataBox = true;
                PaintPriceMarkers = true;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;
                IsSuspendedWhileInactive = true;
                BarsRequiredToPlot = 10;

                VolumetricPeriod = 5;
                DeltaWeight = 0.15;
                DivergenceWeight = 0.20;
                CumDeltaWeight = 0.15;
                ImbalanceWeight = 0.15;
                ClusterWeight = 0.10;
                StackedWeight = 0.15;
                AbsorptionWeight = 0.10;
                ImbalancePercent = 300;
                DivergenceLookback = 5;
                ClusterProximityTicks = 10;
                AbsorptionThreshold = 50;
                HighConvictionThreshold = 50;
                ShowHUD = true;

                AddPlot(new Stroke(Brushes.Gray, 2), PlotStyle.Bar, "Score");
                AddLine(Brushes.Gray, 0, "Zero");
                AddLine(new Stroke(Brushes.Green, DashStyleHelper.Dash, 1), 50, "HighLong");
                AddLine(new Stroke(Brushes.Red, DashStyleHelper.Dash, 1), -50, "HighShort");
            }
            else if (State == State.Configure)
            {
                AddVolumetric(Instrument.FullName, BarsPeriodType.Minute, VolumetricPeriod, VolumetricDeltaType.BidAsk, 1);
            }
            else if (State == State.DataLoaded)
            {
                scoreSeries = new Series<double>(this, MaximumBarsLookBack.Infinite);
                cumDeltaSeries = new Series<double>(this, MaximumBarsLookBack.Infinite);
                barDeltaSeries = new Series<double>(this, MaximumBarsLookBack.Infinite);
                pocHistory = new List<double>(MaxPocHistory);
                stackedZones = new List<StackedZone>(MaxStackedZones);
                hudFont = new SimpleFont("Consolas", 12);
                lastComputedPrimaryBar = -1;
            }
            else if (State == State.Terminated)
            {
                RemoveDrawObject(HudTag);
                hudFont = null;
                if (pocHistory != null)
                    pocHistory.Clear();
                if (stackedZones != null)
                    stackedZones.Clear();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress == 1)
            {
                if (CurrentBars[1] < 10 || CurrentBars[0] < 0)
                    return;

                VolumetricBarsType volBars = BarsArray[1].BarsType as VolumetricBarsType;
                if (volBars == null || volBars.Volumes == null || CurrentBars[1] >= volBars.Volumes.Length)
                    return;

                ComputeScore(volBars);
            }
            else if (BarsInProgress == 0)
            {
                if (CurrentBar < 2 || CurrentBar < BarsRequiredToPlot)
                    return;

                if (lastComputedPrimaryBar != CurrentBar)
                    return;

                Values[0][0] = scoreSeries[0];
                PlotBrushes[0][0] = GetScoreBrush(scoreSeries[0]);

                if (ShowHUD)
                    Draw.TextFixed(this, HudTag, GetHudText(), TextPosition.TopRight, Brushes.White, hudFont, Brushes.Black, Brushes.Transparent, 0);
                else
                    RemoveDrawObject(HudTag);
            }
        }

        private void ComputeScore(VolumetricBarsType volBars)
        {
            try
            {
                dynamic volumeBar = volBars.Volumes[CurrentBars[1]];
                if (volumeBar == null)
                    return;

                double open = Opens[0][0];
                double close = Closes[0][0];
                double low = RoundToTick(Lows[1][0]);
                double high = RoundToTick(Highs[1][0]);
                double barDelta = volumeBar.BarDelta;
                double currentCumDelta = CurrentBars[0] == 0 ? barDelta : cumDeltaSeries[1] + barDelta;
                int buyImbalanceCount;
                int sellImbalanceCount;
                double pocPrice;

                double deltaComponent = ComputeBarDeltaDirection(barDelta);
                double divergenceComponent = ComputeDivergenceComponent(open, close, barDelta);
                double cumDeltaComponent = ComputeCumDeltaComponent(currentCumDelta);
                double imbalanceComponent = ComputeImbalanceComponent(volumeBar, low, high, out buyImbalanceCount, out sellImbalanceCount);
                pocPrice = GetPocPrice(volumeBar, close);
                UpdatePocHistory(pocPrice);
                double clusterComponent = ComputeClusterComponent(close);
                double stackedComponent = ComputeStackedZoneComponent(close);
                double absorptionComponent = ComputeAbsorptionComponent(volumeBar, low, high);
                double score = (deltaComponent * DeltaWeight
                    + divergenceComponent * DivergenceWeight
                    + cumDeltaComponent * CumDeltaWeight
                    + imbalanceComponent * ImbalanceWeight
                    + clusterComponent * ClusterWeight
                    + stackedComponent * StackedWeight
                    + absorptionComponent * AbsorptionWeight) * 100.0;

                score = Clamp(score, -100.0, 100.0);

                scoreSeries[0] = score;
                cumDeltaSeries[0] = currentCumDelta;
                barDeltaSeries[0] = barDelta;
                lastComputedPrimaryBar = CurrentBars[0];
                lastBuyImbalanceCount = buyImbalanceCount;
                lastSellImbalanceCount = sellImbalanceCount;
                lastBarDelta = barDelta;
                lastCumDelta = currentCumDelta;
                lastScore = score;
            }
            catch
            {
            }
        }

        private double ComputeBarDeltaDirection(double barDelta)
        {
            if (barDelta > 0)
                return 1.0;
            if (barDelta < 0)
                return -1.0;
            return 0.0;
        }

        private double ComputeDivergenceComponent(double open, double close, double barDelta)
        {
            if (close < open && barDelta > 0)
                return 1.0;
            if (close > open && barDelta < 0)
                return -1.0;
            return 0.0;
        }

        private double ComputeCumDeltaComponent(double currentCumDelta)
        {
            int lookback = Math.Min(Math.Max(DivergenceLookback, 1), CurrentBars[0]);
            if (lookback <= 0)
                return 0.0;

            double priorCumDelta = cumDeltaSeries[lookback];
            if (currentCumDelta > priorCumDelta)
                return 1.0;
            if (currentCumDelta < priorCumDelta)
                return -1.0;
            return 0.0;
        }

        private double ComputeImbalanceComponent(dynamic volumeBar, double low, double high, out int buyCount, out int sellCount)
        {
            double ratioThreshold = ImbalancePercent / 100.0;
            int buyRun = 0;
            int sellRun = 0;
            double buyRunLow = 0.0;
            double buyRunHigh = 0.0;
            double sellRunLow = 0.0;
            double sellRunHigh = 0.0;
            buyCount = 0;
            sellCount = 0;

            for (double price = low; price <= high - TickSize + TickSize * 0.5; price += TickSize)
            {
                double rounded = RoundToTick(price);
                double above = RoundToTick(rounded + TickSize);
                double ask = volumeBar.GetAskVolumeForPrice(rounded);
                double bid = volumeBar.GetBidVolumeForPrice(rounded);
                double bidAbove = volumeBar.GetBidVolumeForPrice(above);
                double askAbove = volumeBar.GetAskVolumeForPrice(above);
                bool buyingImbalance = ask > 0 && bidAbove > 0 && ask / bidAbove >= ratioThreshold;
                bool sellingImbalance = bid > 0 && askAbove > 0 && bid / askAbove >= ratioThreshold;

                if (buyingImbalance)
                {
                    buyCount++;
                    if (buyRun == 0)
                        buyRunLow = rounded;
                    buyRunHigh = above;
                    buyRun++;
                }
                else
                {
                    FlushStackedZone(buyRun, buyRunLow, buyRunHigh, true);
                    buyRun = 0;
                }

                if (sellingImbalance)
                {
                    sellCount++;
                    if (sellRun == 0)
                        sellRunLow = rounded;
                    sellRunHigh = above;
                    sellRun++;
                }
                else
                {
                    FlushStackedZone(sellRun, sellRunLow, sellRunHigh, false);
                    sellRun = 0;
                }
            }

            FlushStackedZone(buyRun, buyRunLow, buyRunHigh, true);
            FlushStackedZone(sellRun, sellRunLow, sellRunHigh, false);

            if (buyCount > sellCount)
                return 1.0;
            if (sellCount > buyCount)
                return -1.0;
            return 0.0;
        }

        private double GetPocPrice(dynamic volumeBar, double fallbackPrice)
        {
            double pocPrice = RoundToTick(fallbackPrice);
            try
            {
                volumeBar.GetMaximumVolume(null, out pocPrice);
            }
            catch
            {
            }

            return RoundToTick(pocPrice);
        }

        private void UpdatePocHistory(double pocPrice)
        {
            if (pocHistory.Count > 0 && Math.Abs(pocHistory[pocHistory.Count - 1] - pocPrice) < TickSize * 0.5)
                return;

            if (pocHistory.Count >= MaxPocHistory)
                pocHistory.RemoveAt(0);

            pocHistory.Add(pocPrice);
        }

        private double ComputeClusterComponent(double close)
        {
            double threshold = ClusterProximityTicks * TickSize;
            double bestBullDistance = double.MaxValue;
            double bestBearDistance = double.MaxValue;

            for (int i = 0; i < pocHistory.Count; i++)
            {
                double poc = pocHistory[i];
                double distance = Math.Abs(close - poc);
                if (distance > threshold)
                    continue;

                if (poc < close && close - poc < bestBullDistance)
                    bestBullDistance = close - poc;
                else if (poc > close && poc - close < bestBearDistance)
                    bestBearDistance = poc - close;
            }

            if (bestBullDistance == double.MaxValue && bestBearDistance == double.MaxValue)
                return 0.0;
            if (bestBullDistance <= bestBearDistance)
                return 1.0;
            return -1.0;
        }

        private double ComputeStackedZoneComponent(double close)
        {
            for (int i = stackedZones.Count - 1; i >= 0; i--)
            {
                StackedZone zone = stackedZones[i];
                if (close < zone.PriceLow || close > zone.PriceHigh)
                    continue;
                return zone.IsBull ? 1.0 : -1.0;
            }

            return 0.0;
        }

        private double ComputeAbsorptionComponent(dynamic volumeBar, double low, double high)
        {
            double range = Math.Max(high - low, TickSize);
            double lowerThird = low + range / 3.0;
            double upperThird = high - range / 3.0;
            double maxLowerBid = 0.0;
            double maxLowerAsk = 0.0;
            double maxUpperBid = 0.0;
            double maxUpperAsk = 0.0;

            for (double price = low; price <= high + TickSize * 0.5; price += TickSize)
            {
                double rounded = RoundToTick(price);
                double ask = volumeBar.GetAskVolumeForPrice(rounded);
                double bid = volumeBar.GetBidVolumeForPrice(rounded);

                if (rounded <= lowerThird)
                {
                    if (bid > maxLowerBid)
                        maxLowerBid = bid;
                    if (ask > maxLowerAsk)
                        maxLowerAsk = ask;
                }

                if (rounded >= upperThird)
                {
                    if (bid > maxUpperBid)
                        maxUpperBid = bid;
                    if (ask > maxUpperAsk)
                        maxUpperAsk = ask;
                }
            }

            if (maxLowerBid >= AbsorptionThreshold && maxLowerAsk >= AbsorptionThreshold)
                return 1.0;
            if (maxUpperBid >= AbsorptionThreshold && maxUpperAsk >= AbsorptionThreshold)
                return -1.0;
            return 0.0;
        }

        private void FlushStackedZone(int runCount, double low, double high, bool isBull)
        {
            if (runCount < StackedMinCount)
                return;

            AddOrUpdateStackedZone(low, high, isBull);
        }

        private void AddOrUpdateStackedZone(double low, double high, bool isBull)
        {
            double priceLow = RoundToTick(Math.Min(low, high));
            double priceHigh = RoundToTick(Math.Max(low, high));

            for (int i = 0; i < stackedZones.Count; i++)
            {
                StackedZone existing = stackedZones[i];
                if (existing.IsBull == isBull
                    && Math.Abs(existing.PriceLow - priceLow) < TickSize * 0.5
                    && Math.Abs(existing.PriceHigh - priceHigh) < TickSize * 0.5)
                    return;
            }

            if (stackedZones.Count >= MaxStackedZones)
                stackedZones.RemoveAt(0);

            StackedZone zone = new StackedZone();
            zone.PriceLow = priceLow;
            zone.PriceHigh = priceHigh;
            zone.IsBull = isBull;
            stackedZones.Add(zone);
        }

        private Brush GetScoreBrush(double score)
        {
            if (score > 50.0)
                return Brushes.Lime;
            if (score > 25.0)
                return Brushes.Green;
            if (score > -25.0)
                return Brushes.Gray;
            if (score > -50.0)
                return Brushes.Orange;
            return Brushes.Red;
        }

        private string GetHudText()
        {
            return string.Format(
                "Score: {0:+0;-0;0}  {1}\nDelta: {2:+#,0;-#,0;0}  CumΔ: {3:+#,0;-#,0;0}\nImbalances: {4}B / {5}S",
                Math.Round(lastScore),
                GetDirectionLabel(lastScore),
                Math.Round(lastBarDelta),
                Math.Round(lastCumDelta),
                lastBuyImbalanceCount,
                lastSellImbalanceCount);
        }

        private string GetDirectionLabel(double score)
        {
            if (score >= HighConvictionThreshold)
                return "▲ LONG";
            if (score <= -HighConvictionThreshold)
                return "▼ SHORT";
            return "■ NEUTRAL";
        }

        private double RoundToTick(double price)
        {
            if (TickSize <= 0)
                return price;
            return Math.Round(price / TickSize) * TickSize;
        }

        private double Clamp(double value, double min, double max)
        {
            if (value < min)
                return min;
            if (value > max)
                return max;
            return value;
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Volumetric Period", Order = 1, GroupName = "Parameters")]
        public int VolumetricPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 1.0)]
        [Display(Name = "Delta Weight", Order = 2, GroupName = "Weights")]
        public double DeltaWeight { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 1.0)]
        [Display(Name = "Divergence Weight", Order = 3, GroupName = "Weights")]
        public double DivergenceWeight { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 1.0)]
        [Display(Name = "Cum Delta Weight", Order = 4, GroupName = "Weights")]
        public double CumDeltaWeight { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 1.0)]
        [Display(Name = "Imbalance Weight", Order = 5, GroupName = "Weights")]
        public double ImbalanceWeight { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 1.0)]
        [Display(Name = "Cluster Weight", Order = 6, GroupName = "Weights")]
        public double ClusterWeight { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 1.0)]
        [Display(Name = "Stacked Weight", Order = 7, GroupName = "Weights")]
        public double StackedWeight { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 1.0)]
        [Display(Name = "Absorption Weight", Order = 8, GroupName = "Weights")]
        public double AbsorptionWeight { get; set; }

        [NinjaScriptProperty]
        [Range(100, 1000)]
        [Display(Name = "Imbalance Percent", Order = 9, GroupName = "Parameters")]
        public int ImbalancePercent { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Divergence Lookback", Order = 10, GroupName = "Parameters")]
        public int DivergenceLookback { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Cluster Proximity Ticks", Order = 11, GroupName = "Parameters")]
        public int ClusterProximityTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Absorption Threshold", Order = 12, GroupName = "Parameters")]
        public int AbsorptionThreshold { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "High Conviction Threshold", Order = 13, GroupName = "Display")]
        public int HighConvictionThreshold { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show HUD", Order = 14, GroupName = "Display")]
        public bool ShowHUD { get; set; }
        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.
// Intentionally left empty. NinjaTrader appends the cache wrappers during compile.
#endregion
