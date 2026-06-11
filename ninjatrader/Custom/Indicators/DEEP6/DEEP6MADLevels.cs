// DEEP6MADLevels — Order flow absorption level detector
// Signals: Trapped Sellers (TS), Trapped Buyers (TB), Failed Pullback Bullish/Bearish (FPB/FPS)
// Requires a live Rithmic connection — signals only appear on bars that close live.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6MADLevels : Indicator
    {
        #region Types

        private class LevelData
        {
            public double AskVol;
            public double BidVol;
            public double Delta    => AskVol - BidVol;
            public double TotalVol => AskVol + BidVol;
        }

        private class ActiveLevel
        {
            public int    DetectedBar;
            public string LineTag;
            public string LblTag;
            public double Price;
            public double Strength;
            public bool   IsSupport; // true = TS/FPB (buy below), false = TB/FPS (sell above)
        }

        #endregion

        #region Fields

        private Dictionary<double, LevelData>                  _cur;
        private Dictionary<int, Dictionary<double, LevelData>> _hist;
        private List<ActiveLevel>                              _tsLevels;
        private List<ActiveLevel>                              _tbLevels;
        private List<ActiveLevel>                              _fpLevels;

        private double _lastBid   = double.NaN;
        private double _lastAsk   = double.NaN;
        private double _lastTrade = double.NaN;
        private int    _lastDir   = 0; // +1=buy, -1=sell — continuation for equal-price ticks

        #endregion

        #region OnStateChange

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description         = "Trapped Seller / Trapped Buyer / Failed Pullback levels with strength scoring and level clustering. Live data required.";
                Name                = "DEEP6MADLevels";
                Calculate           = Calculate.OnEachTick;
                IsOverlay           = true;
                IsAutoScale         = false;
                BarsRequiredToPlot  = 5;

                AbsorptionThreshold = 10;
                MinDeltaRatio       = 0.15;
                MinStrength         = 5.0;
                StrongMult          = 3.0;
                ClusterTicks        = 4;
                LevelExtension      = 15;
                LookbackBars        = 100;
                InvalidateOnClose   = true;
                ShowTrappedSellers  = true;
                ShowTrappedBuyers   = true;
                ShowFailedPullbacks = true;
            }
            else if (State == State.DataLoaded)
            {
                _cur      = new Dictionary<double, LevelData>();
                _hist     = new Dictionary<int, Dictionary<double, LevelData>>();
                _tsLevels = new List<ActiveLevel>();
                _tbLevels = new List<ActiveLevel>();
                _fpLevels = new List<ActiveLevel>();
            }
        }

        #endregion

        #region OnMarketData

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if      (e.MarketDataType == MarketDataType.Bid)  { _lastBid = e.Price; return; }
            else if (e.MarketDataType == MarketDataType.Ask)  { _lastAsk = e.Price; return; }
            else if (e.MarketDataType != MarketDataType.Last) return;
            if (CurrentBar < 1) return;

            double px = Math.Round(e.Price / TickSize) * TickSize;
            if (!_cur.TryGetValue(px, out LevelData ld))
            {
                ld = new LevelData();
                _cur[px] = ld;
            }

            // Classify tick: prefer live bid/ask, fall back to tick rule,
            // then continue last direction for equal-price ticks (iceberg absorption).
            if      (!double.IsNaN(_lastAsk) && e.Price >= _lastAsk - 0.5 * TickSize)  { ld.AskVol += e.Volume; _lastDir =  1; }
            else if (!double.IsNaN(_lastBid) && e.Price <= _lastBid + 0.5 * TickSize)  { ld.BidVol += e.Volume; _lastDir = -1; }
            else if (!double.IsNaN(_lastTrade) && e.Price > _lastTrade)                 { ld.AskVol += e.Volume; _lastDir =  1; }
            else if (!double.IsNaN(_lastTrade) && e.Price < _lastTrade)                 { ld.BidVol += e.Volume; _lastDir = -1; }
            else if (_lastDir > 0)                                                        ld.AskVol += e.Volume;
            else                                                                          ld.BidVol += e.Volume;

            _lastTrade = e.Price;
        }

        #endregion

        #region OnBarUpdate

        protected override void OnBarUpdate()
        {
            if (CurrentBar < BarsRequiredToPlot) return;
            if (BarsInProgress != 0) return;
            if (!IsFirstTickOfBar) return;

            // Archive just-completed bar. Done here (not OnMarketData) because NT8 fires
            // OnBarUpdate before OnMarketData on the bar-transition tick.
            int closed = CurrentBar - 1;
            if (_cur.Count > 0)
            {
                _hist[closed] = _cur;
                _cur = new Dictionary<double, LevelData>();
                PruneHist();
            }

            Expire(_tsLevels);
            Expire(_tbLevels);
            Expire(_fpLevels);

            if (!_hist.TryGetValue(closed, out var levels)) return;

            double hi    = High[1];
            double lo    = Low[1];
            double cl    = Close[1];
            double range = hi - lo;
            if (range < TickSize) return;

            double closeRel = (cl - lo) / range;
            double totalAsk = 0, totalBid = 0;
            foreach (var ld in levels.Values) { totalAsk += ld.AskVol; totalBid += ld.BidVol; }

            // Invalidate existing levels that price closed through
            if (InvalidateOnClose)
                CheckInvalidation(cl);

            // Scan price levels for absorption
            foreach (var kvp in levels)
            {
                double    px = kvp.Key;
                LevelData ld = kvp.Value;
                if (ld.TotalVol <= 0) continue;

                double dr = Math.Abs(ld.Delta) / ld.TotalVol;
                if (dr < MinDeltaRatio) continue;

                // TS: sellers hit the bid near bar low, but buyers absorbed — net delta positive
                if (ShowTrappedSellers
                    && ld.BidVol >= AbsorptionThreshold
                    && ld.Delta > 0
                    && px <= lo + 0.25 * range)
                {
                    double strength = ld.BidVol * dr;
                    if (strength >= MinStrength)
                        TryPutLevel(_tsLevels, "TS_" + closed + "_" + px, closed, px,
                                    strength, true, Brushes.Lime, DashStyleHelper.Solid, "TS");
                }

                // TB: buyers lifted the offer near bar high, but sellers absorbed — net delta negative
                if (ShowTrappedBuyers
                    && ld.AskVol >= AbsorptionThreshold
                    && ld.Delta < 0
                    && px >= hi - 0.25 * range)
                {
                    double strength = ld.AskVol * dr;
                    if (strength >= MinStrength)
                        TryPutLevel(_tbLevels, "TB_" + closed + "_" + px, closed, px,
                                    strength, false, Brushes.Red, DashStyleHelper.Solid, "TB");
                }
            }

            if (ShowFailedPullbacks)
            {
                double totalVol = totalAsk + totalBid;
                if (totalVol > 0)
                {
                    // FPB: net selling but closed top 25% — sellers failed, low = support
                    if (totalBid > totalAsk && closeRel >= 0.75)
                    {
                        double strength = (totalBid - totalAsk) * closeRel;
                        if (strength >= MinStrength)
                            TryPutLevel(_fpLevels, "FPB_" + closed, closed, lo,
                                        strength, true, Brushes.Cyan, DashStyleHelper.Dash, "FPB");
                    }

                    // FPS: net buying but closed bottom 25% — buyers failed, high = resistance
                    if (totalAsk > totalBid && closeRel <= 0.25)
                    {
                        double strength = (totalAsk - totalBid) * (1.0 - closeRel);
                        if (strength >= MinStrength)
                            TryPutLevel(_fpLevels, "FPS_" + closed, closed, hi,
                                        strength, false, Brushes.Orange, DashStyleHelper.Dash, "FPS");
                    }
                }
            }
        }

        #endregion

        #region Helpers

        // Attempt to draw a level. Handles clustering: if a level already exists within
        // ClusterTicks, keep whichever has higher strength and discard the weaker one.
        private void TryPutLevel(List<ActiveLevel> list, string tag, int detBar, double price,
                                  double strength, bool isSupport, Brush color, DashStyleHelper dash, string lbl)
        {
            double clusterRange = ClusterTicks * TickSize;

            for (int i = list.Count - 1; i >= 0; i--)
            {
                if (Math.Abs(list[i].Price - price) <= clusterRange)
                {
                    if (strength <= list[i].Strength) return; // existing is stronger, skip
                    // Incoming is stronger — remove existing and replace
                    RemoveDrawObject(list[i].LineTag);
                    RemoveDrawObject(list[i].LblTag);
                    list.RemoveAt(i);
                    break;
                }
            }

            DrawLevel(list, tag, detBar, price, strength, isSupport, color, dash, lbl);
        }

        private void DrawLevel(List<ActiveLevel> list, string tag, int detBar, double price,
                                double strength, bool isSupport, Brush color, DashStyleHelper dash, string lbl)
        {
            // 3-tier thickness: weak=1px, medium=2px, strong=3px
            int lineWidth;
            if      (strength >= MinStrength * StrongMult * 2) lineWidth = 3;
            else if (strength >= MinStrength * StrongMult)     lineWidth = 2;
            else                                               lineWidth = 1;

            int end = -(LevelExtension - 1);
            Draw.Line(this, tag, false, 1, price, end, price, color, dash, lineWidth);
            Draw.Text(this, tag + "_L", false, lbl, 1, price + TickSize, 0,
                      Brushes.White, new SimpleFont("Arial", lineWidth > 1 ? 8 : 7) { Bold = lineWidth > 1 },
                      TextAlignment.Left, null, null, 0);

            list.Add(new ActiveLevel
            {
                DetectedBar = detBar,
                LineTag     = tag,
                LblTag      = tag + "_L",
                Price       = price,
                Strength    = strength,
                IsSupport   = isSupport
            });
        }

        // Remove levels that price has closed through — they're no longer valid.
        private void CheckInvalidation(double barClose)
        {
            InvalidateList(_tsLevels, barClose, true);
            InvalidateList(_tbLevels, barClose, false);
            InvalidateList(_fpLevels, barClose, null);
        }

        // isSupport=true→remove if close below; false→remove if close above; null→use IsSupport field
        private void InvalidateList(List<ActiveLevel> list, double barClose, bool? forceIsSupport)
        {
            for (int i = list.Count - 1; i >= 0; i--)
            {
                bool support = forceIsSupport.HasValue ? forceIsSupport.Value : list[i].IsSupport;
                bool broken  = support
                    ? barClose < list[i].Price - TickSize   // closed clearly below support
                    : barClose > list[i].Price + TickSize;  // closed clearly above resistance

                if (!broken) continue;
                RemoveDrawObject(list[i].LineTag);
                RemoveDrawObject(list[i].LblTag);
                list.RemoveAt(i);
            }
        }

        private void Expire(List<ActiveLevel> list)
        {
            for (int i = list.Count - 1; i >= 0; i--)
            {
                if (CurrentBar - list[i].DetectedBar <= LevelExtension) continue;
                RemoveDrawObject(list[i].LineTag);
                RemoveDrawObject(list[i].LblTag);
                list.RemoveAt(i);
            }
        }

        private void PruneHist()
        {
            if (_hist.Count <= LookbackBars) return;
            int cut = CurrentBar - LookbackBars;
            var dead = new List<int>();
            foreach (int k in _hist.Keys) if (k < cut) dead.Add(k);
            foreach (int k in dead) _hist.Remove(k);
        }

        #endregion

        #region Properties

        [NinjaScriptProperty]
        [Range(1.0, double.MaxValue)]
        [Display(Name = "Absorption Threshold", Description = "Min contracts on one side of a price level. ~3-5 for MNQ, ~15-25 for NQ.", Order = 1, GroupName = "1. Detection")]
        public double AbsorptionThreshold { get; set; }

        [NinjaScriptProperty]
        [Range(0.01, 1.0)]
        [Display(Name = "Min Delta Ratio", Description = "Min |delta|/totalVol at a level to confirm imbalance (0.15 = 15%)", Order = 2, GroupName = "1. Detection")]
        public double MinDeltaRatio { get; set; }

        [NinjaScriptProperty]
        [Range(0.01, double.MaxValue)]
        [Display(Name = "Min Strength", Description = "Minimum strength score (absorbedVol × deltaRatio) to draw a level. Higher = fewer, stronger signals.", Order = 3, GroupName = "1. Detection")]
        public double MinStrength { get; set; }

        [NinjaScriptProperty]
        [Range(1.0, 10.0)]
        [Display(Name = "Strong Signal Mult", Description = "A signal is 'strong' (★, thick line) when strength >= MinStrength × this multiplier.", Order = 4, GroupName = "1. Detection")]
        public double StrongMult { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Cluster Ticks", Description = "Merge signals within this many ticks — keeps only the strongest in each zone.", Order = 5, GroupName = "1. Detection")]
        public int ClusterTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "Level Extension (bars)", Description = "How many bars to extend level lines to the right before expiring.", Order = 1, GroupName = "2. Display")]
        public int LevelExtension { get; set; }

        [NinjaScriptProperty]
        [Range(10, 1000)]
        [Display(Name = "Lookback Bars", Description = "Bars of tick history to retain in memory.", Order = 2, GroupName = "2. Display")]
        public int LookbackBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Invalidate On Close", Description = "Remove a level when price closes through it (support closed below, resistance closed above).", Order = 3, GroupName = "2. Display")]
        public bool InvalidateOnClose { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Trapped Sellers", Order = 1, GroupName = "3. Signals")]
        public bool ShowTrappedSellers { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Trapped Buyers", Order = 2, GroupName = "3. Signals")]
        public bool ShowTrappedBuyers { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Failed Pullbacks", Order = 3, GroupName = "3. Signals")]
        public bool ShowFailedPullbacks { get; set; }

        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private DEEP6.DEEP6MADLevels[] cacheDEEP6MADLevels;
		public DEEP6.DEEP6MADLevels DEEP6MADLevels(double absorptionThreshold, double minDeltaRatio, double minStrength, double strongMult, int clusterTicks, int levelExtension, int lookbackBars, bool invalidateOnClose, bool showTrappedSellers, bool showTrappedBuyers, bool showFailedPullbacks)
		{
			return DEEP6MADLevels(Input, absorptionThreshold, minDeltaRatio, minStrength, strongMult, clusterTicks, levelExtension, lookbackBars, invalidateOnClose, showTrappedSellers, showTrappedBuyers, showFailedPullbacks);
		}

		public DEEP6.DEEP6MADLevels DEEP6MADLevels(ISeries<double> input, double absorptionThreshold, double minDeltaRatio, double minStrength, double strongMult, int clusterTicks, int levelExtension, int lookbackBars, bool invalidateOnClose, bool showTrappedSellers, bool showTrappedBuyers, bool showFailedPullbacks)
		{
			if (cacheDEEP6MADLevels != null)
				for (int idx = 0; idx < cacheDEEP6MADLevels.Length; idx++)
					if (cacheDEEP6MADLevels[idx] != null && cacheDEEP6MADLevels[idx].AbsorptionThreshold == absorptionThreshold && cacheDEEP6MADLevels[idx].MinDeltaRatio == minDeltaRatio && cacheDEEP6MADLevels[idx].MinStrength == minStrength && cacheDEEP6MADLevels[idx].StrongMult == strongMult && cacheDEEP6MADLevels[idx].ClusterTicks == clusterTicks && cacheDEEP6MADLevels[idx].LevelExtension == levelExtension && cacheDEEP6MADLevels[idx].LookbackBars == lookbackBars && cacheDEEP6MADLevels[idx].InvalidateOnClose == invalidateOnClose && cacheDEEP6MADLevels[idx].ShowTrappedSellers == showTrappedSellers && cacheDEEP6MADLevels[idx].ShowTrappedBuyers == showTrappedBuyers && cacheDEEP6MADLevels[idx].ShowFailedPullbacks == showFailedPullbacks && cacheDEEP6MADLevels[idx].EqualsInput(input))
						return cacheDEEP6MADLevels[idx];
			return CacheIndicator<DEEP6.DEEP6MADLevels>(new DEEP6.DEEP6MADLevels(){ AbsorptionThreshold = absorptionThreshold, MinDeltaRatio = minDeltaRatio, MinStrength = minStrength, StrongMult = strongMult, ClusterTicks = clusterTicks, LevelExtension = levelExtension, LookbackBars = lookbackBars, InvalidateOnClose = invalidateOnClose, ShowTrappedSellers = showTrappedSellers, ShowTrappedBuyers = showTrappedBuyers, ShowFailedPullbacks = showFailedPullbacks }, input, ref cacheDEEP6MADLevels);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.DEEP6.DEEP6MADLevels DEEP6MADLevels(double absorptionThreshold, double minDeltaRatio, double minStrength, double strongMult, int clusterTicks, int levelExtension, int lookbackBars, bool invalidateOnClose, bool showTrappedSellers, bool showTrappedBuyers, bool showFailedPullbacks)
		{
			return indicator.DEEP6MADLevels(Input, absorptionThreshold, minDeltaRatio, minStrength, strongMult, clusterTicks, levelExtension, lookbackBars, invalidateOnClose, showTrappedSellers, showTrappedBuyers, showFailedPullbacks);
		}

		public Indicators.DEEP6.DEEP6MADLevels DEEP6MADLevels(ISeries<double> input , double absorptionThreshold, double minDeltaRatio, double minStrength, double strongMult, int clusterTicks, int levelExtension, int lookbackBars, bool invalidateOnClose, bool showTrappedSellers, bool showTrappedBuyers, bool showFailedPullbacks)
		{
			return indicator.DEEP6MADLevels(input, absorptionThreshold, minDeltaRatio, minStrength, strongMult, clusterTicks, levelExtension, lookbackBars, invalidateOnClose, showTrappedSellers, showTrappedBuyers, showFailedPullbacks);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.DEEP6.DEEP6MADLevels DEEP6MADLevels(double absorptionThreshold, double minDeltaRatio, double minStrength, double strongMult, int clusterTicks, int levelExtension, int lookbackBars, bool invalidateOnClose, bool showTrappedSellers, bool showTrappedBuyers, bool showFailedPullbacks)
		{
			return indicator.DEEP6MADLevels(Input, absorptionThreshold, minDeltaRatio, minStrength, strongMult, clusterTicks, levelExtension, lookbackBars, invalidateOnClose, showTrappedSellers, showTrappedBuyers, showFailedPullbacks);
		}

		public Indicators.DEEP6.DEEP6MADLevels DEEP6MADLevels(ISeries<double> input , double absorptionThreshold, double minDeltaRatio, double minStrength, double strongMult, int clusterTicks, int levelExtension, int lookbackBars, bool invalidateOnClose, bool showTrappedSellers, bool showTrappedBuyers, bool showFailedPullbacks)
		{
			return indicator.DEEP6MADLevels(input, absorptionThreshold, minDeltaRatio, minStrength, strongMult, clusterTicks, levelExtension, lookbackBars, invalidateOnClose, showTrappedSellers, showTrappedBuyers, showFailedPullbacks);
		}
	}
}

#endregion
