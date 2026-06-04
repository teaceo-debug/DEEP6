#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.BarsTypes;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class DEEP6DaleSetupScanner : Indicator
    {
        private sealed class SetupZone
        {
            public string Kind;
            public string Tag;
            public int Direction;
            public int SourcePrimaryBar;
            public double Low;
            public double High;
            public double Price;
            public bool Retested;
        }

        private readonly List<SetupZone> zones = new List<SetupZone>(256);
        private int zoneSequence;
        private int lastVolPrimaryBar = -1;
        private double lastVolBarHigh;
        private double lastVolBarLow;
        private double lastVolPoc;
        private long lastVolBarDelta;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "DEEP6DaleSetupScanner";
                Description = "Trader Dale standalone setup overlay for TDOFBars charts using a hidden secondary volumetric series.";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                DisplayInDataBox = false;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;
                IsSuspendedWhileInactive = true;
                BarsRequiredToPlot = 10;

                VolClusterMultiplier = 2.0;
                MinTradeSize = 100;
                ImbalancePercent = 300;
                StackedMinCount = 3;
                VolumetricPeriod = 5;

                ShowVolumeClusters = true;
                ShowMultipleNodes = true;
                ShowTradesFilter = true;
                ShowStackedImbalances = true;
                ShowUnfinishedBusiness = true;

                VolumeClusterColor = MakeBrush(66, 133, 244, 80);
                MultipleNodeColor = MakeBrush(255, 214, 10, 255);
                TradesFilterColor = MakeBrush(255, 152, 0, 255);
                BuyingImbalanceColor = MakeBrush(76, 175, 80, 90);
                SellingImbalanceColor = MakeBrush(229, 57, 53, 90);
                UnfinishedBusinessColor = MakeBrush(238, 238, 238, 255);
            }
            else if (State == State.Configure)
            {
                AddVolumetric(Instrument.FullName, BarsPeriodType.Minute, VolumetricPeriod, VolumetricDeltaType.BidAsk, 1);
            }
            else if (State == State.DataLoaded)
            {
                zoneSequence = 0;
                lastVolPrimaryBar = -1;
            }
            else if (State == State.Terminated)
            {
                zones.Clear();
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

            if (CurrentBar < 1)
                return;

            UpdateRetests();
            RefreshDrawings();
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
                var volumeBar = volBars.Volumes[CurrentBars[1]];
                if (volumeBar == null)
                    return;

                lastVolPrimaryBar = CurrentBars[0];
                lastVolBarLow = RoundToTick(Lows[1][0]);
                lastVolBarHigh = RoundToTick(Highs[1][0]);
                lastVolBarDelta = volumeBar.BarDelta;
                volumeBar.GetMaximumVolume(null, out lastVolPoc);
                lastVolPoc = RoundToTick(lastVolPoc);

                if (ShowVolumeClusters)
                    DetectVolumeClusters(volumeBar);

                if (ShowMultipleNodes)
                    DetectMultipleNodes(volumeBar);

                if (ShowTradesFilter)
                    DetectTradesFilter(volumeBar);

                if (ShowStackedImbalances)
                    DetectStackedImbalances(volumeBar);

                if (ShowUnfinishedBusiness)
                    DetectUnfinishedBusiness(volumeBar);
            }
            catch
            {
            }
        }

        private void DetectVolumeClusters(dynamic volumeBar)
        {
            double averagePerLevel = GetAveragePerLevelVolume(volumeBar, lastVolBarLow, lastVolBarHigh);
            if (averagePerLevel <= 0)
                return;

            double threshold = averagePerLevel * VolClusterMultiplier;
            bool inRun = false;
            double runLow = 0;
            double runHigh = 0;
            double bestPrice = 0;
            double bestVolume = 0;

            for (double price = lastVolBarLow; price <= lastVolBarHigh + TickSize * 0.5; price += TickSize)
            {
                double rounded = RoundToTick(price);
                double total = GetTotalVolumeForPrice(volumeBar, rounded);
                if (total >= threshold)
                {
                    if (!inRun)
                    {
                        inRun = true;
                        runLow = rounded;
                        bestPrice = rounded;
                        bestVolume = total;
                    }

                    runHigh = rounded;
                    if (total > bestVolume)
                    {
                        bestVolume = total;
                        bestPrice = rounded;
                    }
                }
                else if (inRun)
                {
                    AddZone("VolumeCluster", runLow, runHigh, bestPrice, GetDirectionalBias(), lastVolPrimaryBar);
                    inRun = false;
                }
            }

            if (inRun)
                AddZone("VolumeCluster", runLow, runHigh, bestPrice, GetDirectionalBias(), lastVolPrimaryBar);
        }

        private void DetectMultipleNodes(dynamic volumeBar)
        {
            double pocPrice = lastVolPoc;
            int streak = 1;

            for (int i = zones.Count - 1; i >= 0 && streak < 5; i--)
            {
                SetupZone zone = zones[i];
                if (zone.Kind != "MultipleNode")
                    continue;
                if (Math.Abs(zone.Price - pocPrice) > TickSize)
                    break;
                streak++;
            }

            if (streak >= 2)
                AddZone("MultipleNode", pocPrice, pocPrice, pocPrice, 0, lastVolPrimaryBar);
            else
                AddZone("MultipleNodeSeed", pocPrice, pocPrice, pocPrice, 0, lastVolPrimaryBar);
        }

        private void DetectTradesFilter(dynamic volumeBar)
        {
            for (double price = lastVolBarLow; price <= lastVolBarHigh + TickSize * 0.5; price += TickSize)
            {
                double rounded = RoundToTick(price);
                double ask = volumeBar.GetAskVolumeForPrice(rounded);
                double bid = volumeBar.GetBidVolumeForPrice(rounded);
                double total = Math.Max(ask, bid);
                if (total >= MinTradeSize)
                    AddZone("TradesFilter", rounded, rounded, rounded, 0, lastVolPrimaryBar);
            }
        }

        private void DetectStackedImbalances(dynamic volumeBar)
        {
            double ratioThreshold = ImbalancePercent / 100.0;
            int buyRun = 0;
            int sellRun = 0;
            double buyLow = 0;
            double buyHigh = 0;
            double sellLow = 0;
            double sellHigh = 0;

            for (double price = lastVolBarLow; price <= lastVolBarHigh - TickSize + TickSize * 0.5; price += TickSize)
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
                    if (buyRun == 0)
                        buyLow = rounded;
                    buyHigh = above;
                    buyRun++;
                }
                else
                {
                    FlushStackedZone(buyRun, buyLow, buyHigh, 1);
                    buyRun = 0;
                }

                if (sellingImbalance)
                {
                    if (sellRun == 0)
                        sellLow = rounded;
                    sellHigh = above;
                    sellRun++;
                }
                else
                {
                    FlushStackedZone(sellRun, sellLow, sellHigh, -1);
                    sellRun = 0;
                }
            }

            FlushStackedZone(buyRun, buyLow, buyHigh, 1);
            FlushStackedZone(sellRun, sellLow, sellHigh, -1);
        }

        private void DetectUnfinishedBusiness(dynamic volumeBar)
        {
            double highBid = volumeBar.GetBidVolumeForPrice(lastVolBarHigh);
            double lowAsk = volumeBar.GetAskVolumeForPrice(lastVolBarLow);

            if (highBid > 0)
                AddZone("UnfinishedBusiness", lastVolBarHigh, lastVolBarHigh, lastVolBarHigh, 0, lastVolPrimaryBar);

            if (lowAsk > 0)
                AddZone("UnfinishedBusiness", lastVolBarLow, lastVolBarLow, lastVolBarLow, 0, lastVolPrimaryBar);
        }

        private void FlushStackedZone(int runCount, double low, double high, int direction)
        {
            if (runCount < StackedMinCount)
                return;

            AddZone("StackedImbalance", low, high, direction > 0 ? high : low, direction, lastVolPrimaryBar);
        }

        private void AddZone(string kind, double low, double high, double price, int direction, int sourceBar)
        {
            double roundedLow = RoundToTick(Math.Min(low, high));
            double roundedHigh = RoundToTick(Math.Max(low, high));
            double roundedPrice = RoundToTick(price);

            for (int i = zones.Count - 1; i >= 0; i--)
            {
                SetupZone existing = zones[i];
                if (existing.Kind != kind)
                    continue;
                if (Math.Abs(existing.Low - roundedLow) <= TickSize
                    && Math.Abs(existing.High - roundedHigh) <= TickSize
                    && Math.Abs(existing.Price - roundedPrice) <= TickSize
                    && Math.Abs(existing.SourcePrimaryBar - sourceBar) <= 1)
                    return;
            }

            if (zones.Count >= 250)
                zones.RemoveAt(0);

            SetupZone zone = new SetupZone();
            zone.Kind = kind;
            zone.Tag = kind + "_" + zoneSequence;
            zone.Direction = direction;
            zone.SourcePrimaryBar = Math.Max(sourceBar, 0);
            zone.Low = roundedLow;
            zone.High = roundedHigh;
            zone.Price = roundedPrice;
            zone.Retested = false;
            zoneSequence++;
            zones.Add(zone);
        }

        private void UpdateRetests()
        {
            for (int i = zones.Count - 1; i >= 0; i--)
            {
                SetupZone zone = zones[i];
                if (CurrentBar <= zone.SourcePrimaryBar)
                    continue;

                if (High[0] < zone.Low || Low[0] > zone.High)
                    continue;

                zone.Retested = true;
                if (zone.Kind == "UnfinishedBusiness")
                {
                    RemoveDrawObject(zone.Tag);
                    zones.RemoveAt(i);
                }
            }
        }

        private void RefreshDrawings()
        {
            for (int i = 0; i < zones.Count; i++)
            {
                SetupZone zone = zones[i];
                if (zone.Kind == "MultipleNodeSeed")
                    continue;

                int startBarsAgo = Math.Max(CurrentBar - zone.SourcePrimaryBar, 0);
                if (zone.Kind == "VolumeCluster")
                {
                    Draw.Rectangle(this, zone.Tag, false, startBarsAgo, zone.High, 0, zone.Low, Brushes.Transparent, VolumeClusterColor, 35);
                }
                else if (zone.Kind == "MultipleNode")
                {
                    Draw.HorizontalLine(this, zone.Tag, zone.Price, MultipleNodeColor);
                }
                else if (zone.Kind == "TradesFilter")
                {
                    Draw.Diamond(this, zone.Tag, false, startBarsAgo, zone.Price, TradesFilterColor);
                }
                else if (zone.Kind == "StackedImbalance")
                {
                    Brush fill = zone.Direction > 0 ? BuyingImbalanceColor : SellingImbalanceColor;
                    Draw.Rectangle(this, zone.Tag, false, startBarsAgo, zone.High, 0, zone.Low, Brushes.Transparent, fill, 40);
                }
                else if (zone.Kind == "UnfinishedBusiness")
                {
                    Draw.Line(this, zone.Tag, false, startBarsAgo, zone.Price, 0, zone.Price, UnfinishedBusinessColor, DashStyleHelper.Dot, 1);
                }
            }
        }

        private double GetAveragePerLevelVolume(dynamic volumeBar, double low, double high)
        {
            double total = 0;
            int count = 0;

            for (double price = low; price <= high + TickSize * 0.5; price += TickSize)
            {
                double rounded = RoundToTick(price);
                double levelTotal = GetTotalVolumeForPrice(volumeBar, rounded);
                if (levelTotal <= 0)
                    continue;

                total += levelTotal;
                count++;
            }

            return count > 0 ? total / count : 0;
        }

        private double GetTotalVolumeForPrice(dynamic volumeBar, double price)
        {
            return volumeBar.GetAskVolumeForPrice(price) + volumeBar.GetBidVolumeForPrice(price);
        }

        private int GetDirectionalBias()
        {
            if (Close[0] > Open[0] || lastVolBarDelta > 0)
                return 1;
            if (Close[0] < Open[0] || lastVolBarDelta < 0)
                return -1;
            return 0;
        }

        private double RoundToTick(double price)
        {
            if (TickSize <= 0)
                return price;
            return Math.Round(price / TickSize) * TickSize;
        }

        private static Brush MakeBrush(byte r, byte g, byte b, byte a)
        {
            SolidColorBrush brush = new SolidColorBrush(Color.FromArgb(a, r, g, b));
            brush.Freeze();
            return brush;
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(1.0, 10.0)]
        [Display(Name = "Vol Cluster Multiplier", Order = 1, GroupName = "Parameters")]
        public double VolClusterMultiplier { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Min Trade Size", Order = 2, GroupName = "Parameters")]
        public int MinTradeSize { get; set; }

        [NinjaScriptProperty]
        [Range(100, 1000)]
        [Display(Name = "Imbalance Percent", Order = 3, GroupName = "Parameters")]
        public int ImbalancePercent { get; set; }

        [NinjaScriptProperty]
        [Range(2, 10)]
        [Display(Name = "Stacked Min Count", Order = 4, GroupName = "Parameters")]
        public int StackedMinCount { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Volumetric Period", Order = 5, GroupName = "Parameters")]
        public int VolumetricPeriod { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Volume Clusters", Order = 6, GroupName = "Display")]
        public bool ShowVolumeClusters { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Multiple Nodes", Order = 7, GroupName = "Display")]
        public bool ShowMultipleNodes { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Trades Filter", Order = 8, GroupName = "Display")]
        public bool ShowTradesFilter { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Stacked Imbalances", Order = 9, GroupName = "Display")]
        public bool ShowStackedImbalances { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Unfinished Business", Order = 10, GroupName = "Display")]
        public bool ShowUnfinishedBusiness { get; set; }

        [XmlIgnore]
        [Display(Name = "Volume Cluster Color", Order = 11, GroupName = "Colors")]
        public Brush VolumeClusterColor { get; set; }

        [Browsable(false)]
        public string VolumeClusterColorSerializable
        {
            get { return Serialize.BrushToString(VolumeClusterColor); }
            set { VolumeClusterColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Multiple Node Color", Order = 12, GroupName = "Colors")]
        public Brush MultipleNodeColor { get; set; }

        [Browsable(false)]
        public string MultipleNodeColorSerializable
        {
            get { return Serialize.BrushToString(MultipleNodeColor); }
            set { MultipleNodeColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Trades Filter Color", Order = 13, GroupName = "Colors")]
        public Brush TradesFilterColor { get; set; }

        [Browsable(false)]
        public string TradesFilterColorSerializable
        {
            get { return Serialize.BrushToString(TradesFilterColor); }
            set { TradesFilterColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Buying Imbalance Color", Order = 14, GroupName = "Colors")]
        public Brush BuyingImbalanceColor { get; set; }

        [Browsable(false)]
        public string BuyingImbalanceColorSerializable
        {
            get { return Serialize.BrushToString(BuyingImbalanceColor); }
            set { BuyingImbalanceColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Selling Imbalance Color", Order = 15, GroupName = "Colors")]
        public Brush SellingImbalanceColor { get; set; }

        [Browsable(false)]
        public string SellingImbalanceColorSerializable
        {
            get { return Serialize.BrushToString(SellingImbalanceColor); }
            set { SellingImbalanceColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Unfinished Business Color", Order = 16, GroupName = "Colors")]
        public Brush UnfinishedBusinessColor { get; set; }

        [Browsable(false)]
        public string UnfinishedBusinessColorSerializable
        {
            get { return Serialize.BrushToString(UnfinishedBusinessColor); }
            set { UnfinishedBusinessColor = Serialize.StringToBrush(value); }
        }
        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.
// Intentionally left empty. NinjaTrader appends the cache wrappers during compile.
#endregion
