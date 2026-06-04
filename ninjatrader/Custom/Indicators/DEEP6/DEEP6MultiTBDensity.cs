// DEEP6MultiTBDensity — Multi-level trapped buyer / trapped seller absorption density detector
// Detects when multiple TB/TS absorption levels fire on the same wick and when those signals cluster across consecutive bars.
// Requires a live Rithmic connection — signals only appear on bars that close live.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Media;
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
    /// <summary>
    /// Detects multi-level trapped-buyer and trapped-seller absorption in bar wick zones,
    /// then marks consecutive-bar clusters of those signals.
    /// </summary>
    public class DEEP6MultiTBDensity : Indicator
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
            public bool   IsSupport;
        }

        private class SignalLevel
        {
            public double Price;
            public double Strength;
        }

        #endregion

        #region Fields

        private Dictionary<double, LevelData>                  _cur;
        private Dictionary<int, Dictionary<double, LevelData>> _hist;
        private List<ActiveLevel>                              _tsLevels;
        private List<ActiveLevel>                              _tbLevels;

        private double _lastBid   = double.NaN;
        private double _lastAsk   = double.NaN;
        private double _lastTrade = double.NaN;
        private int    _lastDir   = 0; // +1=buy, -1=sell — continuation for equal-price ticks

        private int _consecutiveTB;
        private int _consecutiveTS;

        // Quality gate state
        private List<double> _barVolumes;     // rolling bar volumes for session avg
        private List<double> _barDeltas;      // rolling bar deltas for exhaustion check
        private DateTime     _lastSessionDate = DateTime.MinValue;

        #endregion

        #region OnStateChange

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description        = "Qualified multi-level trapped buyer/seller absorption with research-backed quality gates.";
                Name               = "DEEP6MultiTBDensity";
                Calculate          = Calculate.OnEachTick;
                IsOverlay          = true;
                IsAutoScale        = false;
                BarsRequiredToPlot = 20;

                // Detection — raised from original defaults based on walk-forward research
                AbsorptionThreshold = 25;     // was 10 — requires real institutional volume per level
                MinDeltaRatio       = 0.20;   // was 0.15 — tighter imbalance requirement
                MinLevelCount       = 4;      // was 3 — need 4+ levels absorbing on same wick
                MinConsecutiveBars  = 2;
                MinStrength         = 15.0;   // was 5.0 — aggregate strength must be substantial
                ClusterTicks        = 4;

                // Quality gates — research-backed filters that eliminate noise
                MinVolumeRatio      = 1.5;    // bar volume must be 1.5× session average
                RequireOppositeDelta = true;  // prior cumulative delta must oppose signal direction
                DeltaLookback       = 10;     // bars of delta history for exhaustion check
                MinWickRatio        = 0.30;   // wick must be ≥30% of bar range
                EnableTimeFilter    = false;  // set true to restrict to specific hours
                TimeFilterStart     = 9;      // 9 = 9:30 AM ET (hour of bar_ts)
                TimeFilterEnd       = 16;     // 16 = 4:00 PM ET
                MinBarRangeTicks    = 8;      // skip tiny bars — need 8+ ticks of range (2 NQ points)

                // Display
                LevelExtension      = 15;
                LookbackBars        = 100;
                InvalidateOnClose   = true;
                ShowIndividualLevels = false;  // was true — OFF by default to reduce clutter
                ShowMultiSignals     = true;
                ShowClusterSignals   = true;
            }
            else if (State == State.DataLoaded)
            {
                _cur        = new Dictionary<double, LevelData>();
                _hist       = new Dictionary<int, Dictionary<double, LevelData>>();
                _tsLevels   = new List<ActiveLevel>();
                _tbLevels   = new List<ActiveLevel>();
                _barVolumes = new List<double>(200);
                _barDeltas  = new List<double>(200);
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

            // ── Session reset ───────────────────────────────────────────
            DateTime today = Time[0].Date;
            if (today != _lastSessionDate)
            {
                _consecutiveTB = 0;
                _consecutiveTS = 0;
                _barVolumes.Clear();
                _barDeltas.Clear();
                _lastSessionDate = today;
            }

            // ── Archive completed bar ───────────────────────────────────
            int closed = CurrentBar - 1;
            if (_cur.Count > 0)
            {
                _hist[closed] = _cur;
                _cur = new Dictionary<double, LevelData>();
                PruneHist();
            }

            Expire(_tsLevels);
            Expire(_tbLevels);

            if (!_hist.TryGetValue(closed, out var levels))
            {
                ResetRuns();
                return;
            }

            double hi    = High[1];
            double lo    = Low[1];
            double op    = Open[1];
            double cl    = Close[1];
            double range = hi - lo;

            if (InvalidateOnClose)
                CheckInvalidation(cl);

            // Compute bar-level volume and delta from tick data
            double barVol = 0;
            double barDelta = 0;
            foreach (var ld in levels.Values)
            {
                barVol   += ld.TotalVol;
                barDelta += ld.Delta;
            }
            _barVolumes.Add(barVol);
            _barDeltas.Add(barDelta);

            // ── QUALITY GATE 1: Minimum bar range ───────────────────────
            double rangeTicks = range / TickSize;
            if (rangeTicks < MinBarRangeTicks)
            {
                ResetRuns();
                return;
            }

            // ── QUALITY GATE 2: Time-of-day filter ──────────────────────
            if (EnableTimeFilter)
            {
                int barHour = Time[1].Hour;
                if (barHour < TimeFilterStart || barHour >= TimeFilterEnd)
                {
                    ResetRuns();
                    return;
                }
            }

            // ── QUALITY GATE 3: Volume must exceed session average ──────
            bool volumeQualified = true;
            if (MinVolumeRatio > 0 && _barVolumes.Count >= 10)
            {
                double avgVol = 0;
                for (int i = 0; i < _barVolumes.Count; i++)
                    avgVol += _barVolumes[i];
                avgVol /= _barVolumes.Count;

                if (avgVol > 0)
                    volumeQualified = barVol >= avgVol * MinVolumeRatio;
            }

            // ── QUALITY GATE 4: Wick ratio ──────────────────────────────
            double upperWick = hi - Math.Max(op, cl);
            double lowerWick = Math.Min(op, cl) - lo;
            double maxWick   = Math.Max(upperWick, lowerWick);
            double wickRatio  = range > 0 ? maxWick / range : 0;
            bool   wickQualified = wickRatio >= MinWickRatio;

            // ── QUALITY GATE 5: Delta exhaustion context ────────────────
            // TB (bearish signal) requires prior positive cumulative delta (buyers exhausted)
            // TS (bullish signal) requires prior negative cumulative delta (sellers exhausted)
            double cumDelta = 0;
            bool   hasDeltaHistory = false;
            if (_barDeltas.Count > DeltaLookback)
            {
                hasDeltaHistory = true;
                int start = _barDeltas.Count - 1 - DeltaLookback;
                int end   = _barDeltas.Count - 1; // exclude current bar
                for (int i = start; i < end; i++)
                    cumDelta += _barDeltas[i];
            }

            bool tbDeltaQualified = !RequireOppositeDelta || !hasDeltaHistory || cumDelta > 0;
            bool tsDeltaQualified = !RequireOppositeDelta || !hasDeltaHistory || cumDelta < 0;

            // ── Scan wick zones for absorption ──────────────────────────
            double upperWickFloor = hi - 0.25 * range;
            double lowerWickCeil  = lo + 0.25 * range;

            var tbSignals = new List<SignalLevel>();
            var tsSignals = new List<SignalLevel>();
            double tbStrength = 0.0;
            double tsStrength = 0.0;

            foreach (var kvp in levels)
            {
                double px = kvp.Key;
                LevelData ld = kvp.Value;
                if (ld == null || ld.TotalVol <= 0) continue;

                double dr = Math.Abs(ld.Delta) / ld.TotalVol;
                if (dr < MinDeltaRatio) continue;

                if (px >= upperWickFloor
                    && ld.AskVol >= AbsorptionThreshold
                    && ld.Delta < 0)
                {
                    double strength = ld.AskVol * dr;
                    if (strength > 0)
                    {
                        tbSignals.Add(new SignalLevel { Price = px, Strength = strength });
                        tbStrength += strength;
                    }
                }

                if (px <= lowerWickCeil
                    && ld.BidVol >= AbsorptionThreshold
                    && ld.Delta > 0)
                {
                    double strength = ld.BidVol * dr;
                    if (strength > 0)
                    {
                        tsSignals.Add(new SignalLevel { Price = px, Strength = strength });
                        tsStrength += strength;
                    }
                }
            }

            // ── Apply ALL quality gates to determine qualified signals ──
            bool rawMultiTB = tbSignals.Count >= MinLevelCount && tbStrength >= MinStrength;
            bool rawMultiTS = tsSignals.Count >= MinLevelCount && tsStrength >= MinStrength;

            bool multiTB = rawMultiTB && volumeQualified && wickQualified && tbDeltaQualified;
            bool multiTS = rawMultiTS && volumeQualified && wickQualified && tsDeltaQualified;

            bool hasTBLevels = tbSignals.Count > 0;
            bool hasTSLevels = tsSignals.Count > 0;

            // ── Draw qualified signals only ─────────────────────────────
            if (ShowIndividualLevels)
            {
                if (multiTB)
                    foreach (SignalLevel signal in tbSignals)
                        TryPutLevel(_tbLevels, BuildLevelTag("MTB", closed, signal.Price), closed, signal.Price,
                            signal.Strength, false, Brushes.Red, DashStyleHelper.Solid, "TB", tbSignals.Count);

                if (multiTS)
                    foreach (SignalLevel signal in tsSignals)
                        TryPutLevel(_tsLevels, BuildLevelTag("MTS", closed, signal.Price), closed, signal.Price,
                            signal.Strength, true, Brushes.Lime, DashStyleHelper.Solid, "TS", tsSignals.Count);
            }

            UpdateConsecutiveRuns(multiTB, multiTS, hasTBLevels && volumeQualified, hasTSLevels && volumeQualified);

            if (ShowMultiSignals)
            {
                if (multiTB)
                    DrawMultiBarSignal(true, closed, tbSignals.Count, hi, lo);

                if (multiTS)
                    DrawMultiBarSignal(false, closed, tsSignals.Count, hi, lo);
            }

            if (ShowClusterSignals)
            {
                if (multiTB && _consecutiveTB >= MinConsecutiveBars)
                    DrawClusterSignal(true, closed, _consecutiveTB, hi, lo);

                if (multiTS && _consecutiveTS >= MinConsecutiveBars)
                    DrawClusterSignal(false, closed, _consecutiveTS, hi, lo);
            }
        }

        #endregion

        #region Helpers

        private void TryPutLevel(List<ActiveLevel> list, string tag, int detBar, double price,
            double strength, bool isSupport, Brush color, DashStyleHelper dash, string lbl, int levelCount)
        {
            double clusterRange = ClusterTicks * TickSize;

            for (int i = list.Count - 1; i >= 0; i--)
            {
                if (Math.Abs(list[i].Price - price) <= clusterRange)
                {
                    if (strength <= list[i].Strength) return;
                    RemoveDrawObject(list[i].LineTag);
                    RemoveDrawObject(list[i].LblTag);
                    list.RemoveAt(i);
                    break;
                }
            }

            DrawLevel(list, tag, detBar, price, strength, isSupport, color, dash, lbl, levelCount);
        }

        private void DrawLevel(List<ActiveLevel> list, string tag, int detBar, double price,
            double strength, bool isSupport, Brush color, DashStyleHelper dash, string lbl, int levelCount)
        {
            int lineWidth = GetLineWidth(levelCount);
            int end = -(LevelExtension - 1);

            Draw.Line(this, tag, false, 1, price, end, price, color, dash, lineWidth);
            Draw.Text(this, tag + "_L", false, lbl, 1, price + (isSupport ? TickSize : -TickSize), 0,
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

        private void DrawMultiBarSignal(bool isTB, int barIndex, int count, double hi, double lo)
        {
            int barsAgo = CurrentBar - barIndex;
            string tag  = (isTB ? "MTBA_" : "MTSA_") + barIndex;
            double y    = isTB ? hi + 3 * TickSize : lo - 3 * TickSize;
            Brush brush = isTB ? Brushes.Red : Brushes.Lime;
            string text = (isTB ? "TB×" : "TS×") + count;
            double labelY = isTB ? y + 2 * TickSize : y - 2 * TickSize;

            if (isTB)
                Draw.ArrowDown(this, tag, false, barsAgo, y, brush);
            else
                Draw.ArrowUp(this, tag, false, barsAgo, y, brush);

            Draw.Text(this, tag + "_LBL", false, text, barsAgo, labelY, 0,
                Brushes.White, new SimpleFont("Arial", count >= 5 ? 9 : 8) { Bold = count >= MinLevelCount },
                TextAlignment.Center, null, null, 0);
        }

        private void DrawClusterSignal(bool isTB, int barIndex, int runLength, double hi, double lo)
        {
            int barsAgo = CurrentBar - barIndex;
            string tag  = (isTB ? "MTBC_" : "MTSC_") + barIndex;
            double y    = isTB ? hi + 6 * TickSize : lo - 6 * TickSize;
            Brush brush = isTB ? Brushes.Magenta : Brushes.Cyan;
            string text = (isTB ? "TB-CLU×" : "TS-CLU×") + runLength;
            double labelY = isTB ? y + 2 * TickSize : y - 2 * TickSize;

            Draw.Diamond(this, tag, false, barsAgo, y, brush);
            Draw.Text(this, tag + "_LBL", false, text, barsAgo, labelY, 0,
                brush, new SimpleFont("Arial", 10) { Bold = true },
                TextAlignment.Center, null, null, 0);
        }

        private void UpdateConsecutiveRuns(bool multiTB, bool multiTS, bool hasTBLevels, bool hasTSLevels)
        {
            if (!hasTBLevels) _consecutiveTB = 0;
            else _consecutiveTB = multiTB ? _consecutiveTB + 1 : 0;

            if (!hasTSLevels) _consecutiveTS = 0;
            else _consecutiveTS = multiTS ? _consecutiveTS + 1 : 0;
        }

        private void ResetRuns()
        {
            _consecutiveTB = 0;
            _consecutiveTS = 0;
        }

        private string BuildLevelTag(string prefix, int barIndex, double price)
        {
            return prefix + "_" + barIndex + "_" + price.ToString("0.#####");
        }

        private int GetLineWidth(int levelCount)
        {
            if (levelCount >= 7) return 3;
            if (levelCount >= 5) return 2;
            return 1;
        }

        private void CheckInvalidation(double barClose)
        {
            InvalidateList(_tsLevels, barClose, true);
            InvalidateList(_tbLevels, barClose, false);
        }

        private void InvalidateList(List<ActiveLevel> list, double barClose, bool forceIsSupport)
        {
            for (int i = list.Count - 1; i >= 0; i--)
            {
                bool broken = forceIsSupport
                    ? barClose < list[i].Price - TickSize
                    : barClose > list[i].Price + TickSize;

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
            foreach (int k in _hist.Keys)
                if (k < cut)
                    dead.Add(k);
            foreach (int k in dead)
                _hist.Remove(k);
        }

        #endregion

        #region Properties — Detection

        /// <summary>
        /// Minimum contracts absorbed on one side of a price level.
        /// </summary>
        [NinjaScriptProperty]
        [Range(1.0, double.MaxValue)]
        [Display(Name = "Absorption Threshold", Description = "Minimum contracts on the absorbed side of a price level.", Order = 1, GroupName = "1. Detection")]
        public double AbsorptionThreshold { get; set; }

        /// <summary>
        /// Minimum absolute delta divided by total volume required at a price level.
        /// </summary>
        [NinjaScriptProperty]
        [Range(0.01, 1.0)]
        [Display(Name = "Min Delta Ratio", Description = "Minimum |delta| / total volume required for a level to qualify.", Order = 2, GroupName = "1. Detection")]
        public double MinDeltaRatio { get; set; }

        /// <summary>
        /// Minimum number of qualifying wick levels required for a multi-level signal.
        /// </summary>
        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "Min Level Count", Description = "Minimum qualifying TB or TS levels on one bar to trigger a multi-level signal.", Order = 3, GroupName = "1. Detection")]
        public int MinLevelCount { get; set; }

        /// <summary>
        /// Minimum consecutive multi-signal bars required before a cluster marker is drawn.
        /// </summary>
        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "Min Consecutive Bars", Description = "Minimum consecutive multi-level bars needed for a cluster signal.", Order = 4, GroupName = "1. Detection")]
        public int MinConsecutiveBars { get; set; }

        /// <summary>
        /// Minimum aggregate strength required before a multi-level signal is drawn.
        /// </summary>
        [NinjaScriptProperty]
        [Range(0.01, double.MaxValue)]
        [Display(Name = "Min Strength", Description = "Minimum aggregate strength required to draw a multi-level signal.", Order = 5, GroupName = "1. Detection")]
        public double MinStrength { get; set; }

        /// <summary>
        /// Merge levels that occur within this many ticks of each other.
        /// </summary>
        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Cluster Ticks", Description = "Merge absorption levels within this many ticks and keep the strongest.", Order = 6, GroupName = "1. Detection")]
        public int ClusterTicks { get; set; }

        /// <summary>
        /// Bar volume must exceed session average × this ratio. Set 0 to disable.
        /// Research: volume_ratio ≥ 1.5 improved TRAP signals; ≥ 2.0 improved ABS signals.
        /// </summary>
        [NinjaScriptProperty]
        [Range(0.0, 10.0)]
        [Display(Name = "Min Volume Ratio", Description = "Bar volume must exceed session avg × this value. 0 = disabled. Research: 1.5 for TRAP, 2.0 for ABS.", Order = 1, GroupName = "2. Quality Gates")]
        public double MinVolumeRatio { get; set; }

        /// <summary>
        /// Require prior cumulative delta to be OPPOSITE the signal direction.
        /// TB (bearish) requires prior positive delta (buyer exhaustion).
        /// TS (bullish) requires prior negative delta (seller exhaustion).
        /// Research: +28.79 tick improvement for absorption with 20-bar opposite delta.
        /// </summary>
        [NinjaScriptProperty]
        [Display(Name = "Require Opposite Delta", Description = "Only signal when prior cumulative delta opposes signal direction (exhaustion context). Research-validated edge.", Order = 2, GroupName = "2. Quality Gates")]
        public bool RequireOppositeDelta { get; set; }

        /// <summary>
        /// Number of bars to look back for cumulative delta exhaustion check.
        /// Research: 10-bar and 20-bar lookbacks both validated.
        /// </summary>
        [NinjaScriptProperty]
        [Range(3, 50)]
        [Display(Name = "Delta Lookback", Description = "Bars of prior delta to sum for exhaustion check. Research: 10 or 20 bars.", Order = 3, GroupName = "2. Quality Gates")]
        public int DeltaLookback { get; set; }

        /// <summary>
        /// Wick must be at least this fraction of bar range. Ensures meaningful rejection.
        /// Research: wick_ratio ≥ 0.30 indicates genuine price rejection, not just noise.
        /// </summary>
        [NinjaScriptProperty]
        [Range(0.0, 0.90)]
        [Display(Name = "Min Wick Ratio", Description = "Max wick must be ≥ this fraction of bar range. 0.30 = 30% wick. Ensures genuine rejection.", Order = 4, GroupName = "2. Quality Gates")]
        public double MinWickRatio { get; set; }

        /// <summary>
        /// Enable time-of-day restriction. Research: Opening Drive (9:30-10:30) and Close (15:00-16:00) had strongest edges.
        /// </summary>
        [NinjaScriptProperty]
        [Display(Name = "Enable Time Filter", Description = "Restrict signals to specific hours. Research: best edges at 9:30-10:30 and 15:00-16:00.", Order = 5, GroupName = "2. Quality Gates")]
        public bool EnableTimeFilter { get; set; }

        /// <summary>
        /// Start hour for time filter (inclusive). 9 = 9:00 AM.
        /// </summary>
        [NinjaScriptProperty]
        [Range(0, 23)]
        [Display(Name = "Time Filter Start Hour", Description = "Start hour (inclusive). 9 = 9 AM, 14 = 2 PM.", Order = 6, GroupName = "2. Quality Gates")]
        public int TimeFilterStart { get; set; }

        /// <summary>
        /// End hour for time filter (exclusive). 16 = 4:00 PM.
        /// </summary>
        [NinjaScriptProperty]
        [Range(1, 24)]
        [Display(Name = "Time Filter End Hour", Description = "End hour (exclusive). 16 = up to 4 PM.", Order = 7, GroupName = "2. Quality Gates")]
        public int TimeFilterEnd { get; set; }

        /// <summary>
        /// Minimum bar range in ticks. Skips tiny/inside bars that produce noise signals.
        /// 8 ticks = 2 NQ points. Prevents signals on doji and inside bars.
        /// </summary>
        [NinjaScriptProperty]
        [Range(0, 100)]
        [Display(Name = "Min Bar Range (ticks)", Description = "Skip bars with range below this many ticks. 8 = 2 NQ points.", Order = 8, GroupName = "2. Quality Gates")]
        public int MinBarRangeTicks { get; set; }

        #endregion

        #region Properties — Display

        /// <summary>
        /// Number of bars to extend absorption levels to the right.
        /// </summary>
        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "Level Extension", Description = "How many bars level lines should extend before expiring.", Order = 1, GroupName = "2. Display")]
        public int LevelExtension { get; set; }

        /// <summary>
        /// Number of bars of archived tick history retained in memory.
        /// </summary>
        [NinjaScriptProperty]
        [Range(10, 2000)]
        [Display(Name = "Lookback Bars", Description = "Bars of per-price tick history retained in memory.", Order = 2, GroupName = "2. Display")]
        public int LookbackBars { get; set; }

        /// <summary>
        /// Remove an active level when price closes through it.
        /// </summary>
        [NinjaScriptProperty]
        [Display(Name = "Invalidate On Close", Description = "Remove a level once price closes clearly through it.", Order = 3, GroupName = "2. Display")]
        public bool InvalidateOnClose { get; set; }

        /// <summary>
        /// Draw thin horizontal levels for each detected absorption price.
        /// </summary>
        [NinjaScriptProperty]
        [Display(Name = "Show Individual Levels", Description = "Draw a horizontal level for each qualifying absorption price on a multi-signal bar.", Order = 1, GroupName = "3. Signals")]
        public bool ShowIndividualLevels { get; set; }

        /// <summary>
        /// Draw arrow markers for multi-level TB and TS bars.
        /// </summary>
        [NinjaScriptProperty]
        [Display(Name = "Show Multi Signals", Description = "Draw arrow markers and count labels for multi-level TB/TS bars.", Order = 2, GroupName = "3. Signals")]
        public bool ShowMultiSignals { get; set; }

        /// <summary>
        /// Draw diamond markers for consecutive multi-level TB and TS clusters.
        /// </summary>
        [NinjaScriptProperty]
        [Display(Name = "Show Cluster Signals", Description = "Draw cluster diamonds when consecutive multi-level bars reach the configured threshold.", Order = 3, GroupName = "3. Signals")]
        public bool ShowClusterSignals { get; set; }

        #endregion
    }
}
