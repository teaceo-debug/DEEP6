// DEEP6FootprintMAD — Gray diamond percentages + Liquidity Walls (L2) + MAD levels (TS/TB/FPB).
// Requires live Rithmic connection.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush  = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
using Color = System.Windows.Media.Color;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6FootprintMAD : Indicator
    {
        #region Types

        private sealed class L2LevelState
        {
            public long CurrentSize;
            public long MaxSize;
            public DateTime LastUpdate;
            public int RefillCount;
        }

        private class LevelData
        {
            public double AskVol;
            public double BidVol;
            public double Delta    { get { return AskVol - BidVol; } }
            public double TotalVol { get { return AskVol + BidVol; } }
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

        #endregion

        #region Fields

        // ---- Footprint data (needed for exhaustion detection) ----
        private readonly Dictionary<int, FootprintBar> _bars = new Dictionary<int, FootprintBar>();
        private readonly object _barsLock = new object();
        private readonly HashSet<int> _finalizedBars = new HashSet<int>();
        private double _bestBid = double.NaN;
        private double _bestAsk = double.NaN;
        private long   _priorCvd;
        private FootprintBar _priorFinalized;

        private double _volEma;
        private const double VolEmaAlpha = 2.0 / (20.0 + 1.0);
        private readonly Queue<double> _atrWindow = new Queue<double>();
        private const int AtrPeriod = 20;
        private double _atr = 1.0;

        // ---- Exhaustion detector ----
        private readonly ExhaustionConfig   _exhCfg      = new ExhaustionConfig();
        private readonly ExhaustionDetector _exhDetector = new ExhaustionDetector();

        // ---- L2 Liquidity Walls ----
        private readonly Dictionary<double, L2LevelState> _l2Bids = new Dictionary<double, L2LevelState>();
        private readonly Dictionary<double, L2LevelState> _l2Asks = new Dictionary<double, L2LevelState>();
        private readonly object _l2Lock = new object();
        private DateTime _lastL2Prune = DateTime.MinValue;

        // SharpDX brushes for walls
        private SharpDX.Direct2D1.Brush _wallBidDx, _wallAskDx;
        private TextFormat _labelFont;

        // ---- MADLevels ----
        private Dictionary<double, LevelData>                  _cur;
        private Dictionary<int, Dictionary<double, LevelData>> _hist;
        private List<ActiveLevel> _tsLevels;
        private List<ActiveLevel> _tbLevels;
        private List<ActiveLevel> _fpLevels;
        private double _lastBid   = double.NaN;
        private double _lastAsk   = double.NaN;
        private double _lastTrade = double.NaN;
        private int    _lastDir;

        // session reset
        private DateTime _lastSessionDate = DateTime.MinValue;

        #endregion

        #region OnStateChange

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description              = "Gray diamond percentages + Liquidity Walls (Rithmic L2) + MAD levels (TS/TB/FPB).";
                Name                     = "DEEP6FootprintMAD";
                Calculate                = Calculate.OnEachTick;
                IsOverlay                = true;
                DisplayInDataBox         = false;
                DrawOnPricePanel         = true;
                PaintPriceMarkers        = false;
                IsSuspendedWhileInactive = true;
                BarsRequiredToPlot       = 5;

                // Exhaustion
                ExhaustWickMinPct = 35.0;

                // Liquidity Walls
                ShowLiquidityWalls    = true;
                LiquidityWallMin     = 100;
                LiquidityWallStaleSec = 90;
                LiquidityMaxPerSide  = 4;
                WallBidBrush = MakeFrozenBrush(Color.FromArgb(220, 43, 140, 255));   // bright blue
                WallAskBrush = MakeFrozenBrush(Color.FromArgb(220, 255, 138, 61));   // warm orange

                // MADLevels
                AbsorptionThreshold = 10;
                MinDeltaRatio       = 0.15;
                MinStrength         = 5.0;
                StrongMult          = 3.0;
                ClusterTicks        = 4;
                LevelExtension      = 5;
                LookbackBars        = 100;
                InvalidateOnClose   = true;
                ShowTrappedSellers  = true;
                ShowTrappedBuyers   = true;
                ShowFailedPullbacks = true;
            }
            else if (State == State.Configure)
            {
                _exhCfg.ExhaustWickMin = ExhaustWickMinPct;
            }
            else if (State == State.DataLoaded)
            {
                lock (_barsLock) { _bars.Clear(); }
                _finalizedBars.Clear();
                _exhDetector.ResetCooldowns();
                _atrWindow.Clear();
                _volEma         = 0.0;
                _priorCvd       = 0;
                _priorFinalized = null;

                _cur      = new Dictionary<double, LevelData>();
                _hist     = new Dictionary<int, Dictionary<double, LevelData>>();
                _tsLevels = new List<ActiveLevel>();
                _tbLevels = new List<ActiveLevel>();
                _fpLevels = new List<ActiveLevel>();
                _lastBid   = double.NaN;
                _lastAsk   = double.NaN;
                _lastTrade = double.NaN;
                _lastDir   = 0;
            }
            else if (State == State.Terminated)
            {
                DisposeDx();
            }
        }

        #endregion

        #region Tick intake

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (State != State.Realtime && State != State.Historical) return;

            if (e.MarketDataType == MarketDataType.Bid)
            {
                _bestBid = e.Price;
                _lastBid = e.Price;
                return;
            }
            if (e.MarketDataType == MarketDataType.Ask)
            {
                _bestAsk = e.Price;
                _lastAsk = e.Price;
                return;
            }
            if (e.MarketDataType != MarketDataType.Last) return;
            if (CurrentBar < 0) return;

            // --- Footprint bar accumulation ---
            int aggressor;
            if      (!double.IsNaN(_bestAsk) && e.Price >= _bestAsk) aggressor = 1;
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

            // --- MADLevels tick classification ---
            double px = Math.Round(e.Price / TickSize) * TickSize;
            LevelData ld;
            if (!_cur.TryGetValue(px, out ld))
            {
                ld = new LevelData();
                _cur[px] = ld;
            }

            if      (!double.IsNaN(_lastAsk) && e.Price >= _lastAsk - 0.5 * TickSize)  { ld.AskVol += e.Volume; _lastDir =  1; }
            else if (!double.IsNaN(_lastBid) && e.Price <= _lastBid + 0.5 * TickSize)  { ld.BidVol += e.Volume; _lastDir = -1; }
            else if (!double.IsNaN(_lastTrade) && e.Price > _lastTrade)                 { ld.AskVol += e.Volume; _lastDir =  1; }
            else if (!double.IsNaN(_lastTrade) && e.Price < _lastTrade)                 { ld.BidVol += e.Volume; _lastDir = -1; }
            else if (_lastDir > 0)                                                        ld.AskVol += e.Volume;
            else                                                                          ld.BidVol += e.Volume;

            _lastTrade = e.Price;
        }

        #endregion

        #region L2 depth intake (Liquidity Walls)

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (!ShowLiquidityWalls) return;
            if (e.Position >= 10) return;

            Dictionary<double, L2LevelState> dict;
            if      (e.MarketDataType == MarketDataType.Bid) dict = _l2Bids;
            else if (e.MarketDataType == MarketDataType.Ask) dict = _l2Asks;
            else return;

            long newSize = e.Operation == Operation.Remove ? 0 : (long)e.Volume;

            lock (_l2Lock)
            {
                L2LevelState st;
                if (!dict.TryGetValue(e.Price, out st))
                {
                    st = new L2LevelState();
                    dict[e.Price] = st;
                }
                if (st.MaxSize > 0 && st.CurrentSize < st.MaxSize * 0.5 && newSize >= st.MaxSize * 0.5)
                    st.RefillCount++;
                st.CurrentSize = newSize;
                if (newSize > st.MaxSize) st.MaxSize = newSize;
                st.LastUpdate = DateTime.UtcNow;

                if ((DateTime.UtcNow - _lastL2Prune).TotalSeconds > 30)
                {
                    PruneL2(_l2Bids);
                    PruneL2(_l2Asks);
                    _lastL2Prune = DateTime.UtcNow;
                }
            }
        }

        private static void PruneL2(Dictionary<double, L2LevelState> dict)
        {
            var cutoff = DateTime.UtcNow.AddMinutes(-15);
            var stale = new List<double>();
            foreach (var kv in dict)
                if (kv.Value.LastUpdate < cutoff) stale.Add(kv.Key);
            foreach (var k in stale) dict.Remove(k);
        }

        #endregion

        #region Bar lifecycle

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;
            if (CurrentBar < 2) return;
            if (!IsFirstTickOfBar) return;

            int closed = CurrentBar - 1;

            // --- Finalize footprint bar ---
            FootprintBar prev;
            lock (_barsLock) { _bars.TryGetValue(closed, out prev); }

            if (prev != null)
            {
                prev.Open  = Bars.GetOpen(closed);
                prev.High  = Bars.GetHigh(closed);
                prev.Low   = Bars.GetLow(closed);
                prev.Close = Bars.GetClose(closed);

                if (!_finalizedBars.Contains(closed))
                {
                    prev.Finalize(_priorCvd);
                    _finalizedBars.Add(closed);
                }
                _priorCvd = prev.Cvd;

                _atrWindow.Enqueue(prev.BarRange);
                while (_atrWindow.Count > AtrPeriod) _atrWindow.Dequeue();
                double sum = 0; foreach (var v in _atrWindow) sum += v;
                _atr = _atrWindow.Count == 0 ? 1.0 : Math.Max(sum / _atrWindow.Count, 0.25);
                _volEma = _volEma == 0 ? prev.TotalVol : _volEma + VolEmaAlpha * (prev.TotalVol - _volEma);

                // Session reset
                DateTime barDate = Bars.GetTime(closed).Date;
                if (barDate != _lastSessionDate)
                {
                    _exhDetector.ResetCooldowns();
                    _lastSessionDate = barDate;
                }

                // --- Gray diamond percentages ---
                var exh = _exhDetector.Detect(prev, _priorFinalized, closed, _atr, _exhCfg);
                for (int i = 0; i < exh.Count; i++)
                    DrawExhaustionPercentage(closed, exh[i]);

                _priorFinalized = prev;
            }

            // --- MADLevels ---
            if (_cur.Count > 0)
            {
                _hist[closed] = _cur;
                _cur = new Dictionary<double, LevelData>();
            }

            Expire(_tsLevels);
            Expire(_tbLevels);
            Expire(_fpLevels);

            if (CurrentBar >= BarsRequiredToPlot)
            {
                Dictionary<double, LevelData> levels;
                if (_hist.TryGetValue(closed, out levels))
                {
                    double hi    = High[1];
                    double lo    = Low[1];
                    double cl    = Close[1];
                    double range = hi - lo;

                    if (InvalidateOnClose)
                        CheckInvalidation(cl);

                    if (range >= TickSize)
                    {
                        double closeRel = (cl - lo) / range;
                        double totalAsk = 0, totalBid = 0;
                        foreach (var lv in levels.Values) { totalAsk += lv.AskVol; totalBid += lv.BidVol; }

                        foreach (var kvp in levels)
                        {
                            double px   = kvp.Key;
                            LevelData ld = kvp.Value;
                            if (ld.TotalVol <= 0) continue;
                            double dr = Math.Abs(ld.Delta) / ld.TotalVol;
                            if (dr < MinDeltaRatio) continue;

                            if (ShowTrappedSellers && ld.BidVol >= AbsorptionThreshold
                                && ld.Delta > 0 && px <= lo + 0.25 * range)
                            {
                                double strength = ld.BidVol * dr;
                                if (strength >= MinStrength)
                                    TryPutLevel(_tsLevels, "TS_" + closed + "_" + px, closed, px,
                                        strength, true, Brushes.Lime, DashStyleHelper.Solid, "TS");
                            }
                            if (ShowTrappedBuyers && ld.AskVol >= AbsorptionThreshold
                                && ld.Delta < 0 && px >= hi - 0.25 * range)
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
                                if (totalBid > totalAsk && closeRel >= 0.75)
                                {
                                    double strength = (totalBid - totalAsk) * closeRel;
                                    if (strength >= MinStrength)
                                        TryPutLevel(_fpLevels, "FPB_" + closed, closed, lo,
                                            strength, true, Brushes.Cyan, DashStyleHelper.Dash, "FPB");
                                }
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
                }
            }

            PruneHist();

            int cutoff = CurrentBar - 500;
            if (cutoff > 0)
            {
                lock (_barsLock)
                {
                    var stale = _bars.Keys.Where(k => k < cutoff).ToList();
                    foreach (var k in stale) _bars.Remove(k);
                }
                _finalizedBars.RemoveWhere(k => k < cutoff);
            }
        }

        #endregion

        #region Rendering (Liquidity Walls only)

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            _wallBidDx = WallBidBrush.ToDxBrush(RenderTarget);
            _wallAskDx = WallAskBrush.ToDxBrush(RenderTarget);

            _labelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 10f)
            {
                TextAlignment      = SharpDX.DirectWrite.TextAlignment.Trailing,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (!ShowLiquidityWalls) return;
            if (IsInHitTest) return;
            if (RenderTarget == null || ChartBars == null) return;
            if (chartControl == null || chartControl.Instrument == null) return;

            base.OnRender(chartControl, chartScale);
            RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

            float panelRight = (float)(ChartPanel.X + ChartPanel.W);
            RenderLiquidityWalls(chartScale, panelRight);
        }

        private void RenderLiquidityWalls(ChartScale cs, float panelRight)
        {
            if (_wallBidDx == null || _wallAskDx == null) return;
            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;
            DateTime fresh = DateTime.UtcNow.AddSeconds(-LiquidityWallStaleSec);

            List<KeyValuePair<double, L2LevelState>> bidSnap, askSnap;
            lock (_l2Lock)
            {
                bidSnap = new List<KeyValuePair<double, L2LevelState>>(_l2Bids.Count);
                foreach (var kv in _l2Bids)
                    bidSnap.Add(new KeyValuePair<double, L2LevelState>(kv.Key, new L2LevelState {
                        CurrentSize = kv.Value.CurrentSize, MaxSize = kv.Value.MaxSize,
                        LastUpdate = kv.Value.LastUpdate,   RefillCount = kv.Value.RefillCount }));
                askSnap = new List<KeyValuePair<double, L2LevelState>>(_l2Asks.Count);
                foreach (var kv in _l2Asks)
                    askSnap.Add(new KeyValuePair<double, L2LevelState>(kv.Key, new L2LevelState {
                        CurrentSize = kv.Value.CurrentSize, MaxSize = kv.Value.MaxSize,
                        LastUpdate = kv.Value.LastUpdate,   RefillCount = kv.Value.RefillCount }));
            }

            DrawWallsForSide(cs, bidSnap, _wallBidDx, "BID", fresh, minVis, maxVis, panelRight);
            DrawWallsForSide(cs, askSnap, _wallAskDx, "ASK", fresh, minVis, maxVis, panelRight);
        }

        private void DrawWallsForSide(ChartScale cs,
            List<KeyValuePair<double, L2LevelState>> snap,
            SharpDX.Direct2D1.Brush brush, string side,
            DateTime fresh, double minVis, double maxVis, float panelRight)
        {
            var walls = new List<KeyValuePair<double, L2LevelState>>();
            foreach (var kv in snap)
            {
                if (kv.Value.MaxSize < LiquidityWallMin) continue;
                if (kv.Value.LastUpdate < fresh) continue;
                if (kv.Key < minVis || kv.Key > maxVis) continue;
                walls.Add(kv);
            }
            walls.Sort((a, b) => b.Value.MaxSize.CompareTo(a.Value.MaxSize));
            int show = Math.Min(walls.Count, LiquidityMaxPerSide);

            for (int i = 0; i < show; i++)
            {
                double price = walls[i].Key;
                var st = walls[i].Value;
                float y = (float)cs.GetYByValue(price);
                float thickness = (float)Math.Min(4.0, 1.5 + (st.MaxSize / (double)LiquidityWallMin) * 0.4);

                RenderTarget.DrawLine(
                    new Vector2((float)ChartPanel.X, y),
                    new Vector2(panelRight - 90, y),
                    brush, thickness);

                string label = string.Format("{0} {1:F2}  {2}{3}",
                    side, price, st.MaxSize,
                    st.RefillCount >= 2 ? " ICE\u00D7" + st.RefillCount : "");

                if (_labelFont != null)
                {
                    using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                        label, _labelFont, 180f, 16f))
                    {
                        RenderTarget.DrawTextLayout(new Vector2(panelRight - 184, y - 8), layout, brush);
                    }
                }
            }
        }

        #endregion

        #region Exhaustion percentage markers

        private void DrawExhaustionPercentage(int barIdx, ExhaustionSignal s)
        {
            if (s.Direction != 0) return;

            string tag = string.Format("EXH_{0}_{1}", barIdx, (int)s.Kind);
            int barsAgo = CurrentBar - barIdx;

            Draw.Diamond(this, tag, false, barsAgo, s.Price, Brushes.SlateGray);

            string strText = string.Format("{0:0}%", s.Strength * 100.0);
            Draw.Text(this, tag + "_str", false, strText, barsAgo, s.Price, 0,
                Brushes.White, new SimpleFont("Arial", 9) { Bold = true },
                System.Windows.TextAlignment.Center, null, null, 0);
        }

        #endregion

        #region MADLevels helpers

        private void TryPutLevel(List<ActiveLevel> list, string tag, int detBar, double price,
            double strength, bool isSupport, Brush color, DashStyleHelper dash, string lbl)
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

            DrawLevel(list, tag, detBar, price, strength, isSupport, color, dash, lbl);
        }

        private void DrawLevel(List<ActiveLevel> list, string tag, int detBar, double price,
            double strength, bool isSupport, Brush color, DashStyleHelper dash, string lbl)
        {
            int lineWidth;
            if      (strength >= MinStrength * StrongMult * 2) lineWidth = 3;
            else if (strength >= MinStrength * StrongMult)     lineWidth = 2;
            else                                               lineWidth = 1;

            int end = -(LevelExtension - 1);
            Draw.Line(this, tag, false, 1, price, end, price, color, dash, lineWidth);
            Draw.Text(this, tag + "_L", false, lbl, 1, price + TickSize, 0,
                Brushes.White, new SimpleFont("Arial", lineWidth > 1 ? 8 : 7) { Bold = lineWidth > 1 },
                System.Windows.TextAlignment.Left, null, null, 0);

            list.Add(new ActiveLevel
            {
                DetectedBar = detBar, LineTag = tag, LblTag = tag + "_L",
                Price = price, Strength = strength, IsSupport = isSupport
            });
        }

        private void CheckInvalidation(double barClose)
        {
            InvalidateList(_tsLevels, barClose, true);
            InvalidateList(_tbLevels, barClose, false);
            InvalidateList(_fpLevels, barClose, null);
        }

        private void InvalidateList(List<ActiveLevel> list, double barClose, bool? forceIsSupport)
        {
            for (int i = list.Count - 1; i >= 0; i--)
            {
                bool support = forceIsSupport.HasValue ? forceIsSupport.Value : list[i].IsSupport;
                bool broken  = support
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
            foreach (int k in _hist.Keys) if (k < cut) dead.Add(k);
            foreach (int k in dead) _hist.Remove(k);
        }

        private static SolidColorBrush MakeFrozenBrush(Color c)
        {
            var b = new SolidColorBrush(c);
            if (b.CanFreeze) b.Freeze();
            return b;
        }

        private void DisposeDx()
        {
            if (_wallBidDx != null) { _wallBidDx.Dispose(); _wallBidDx = null; }
            if (_wallAskDx != null) { _wallAskDx.Dispose(); _wallAskDx = null; }
            if (_labelFont != null) { _labelFont.Dispose(); _labelFont = null; }
        }

        #endregion

        #region Properties

        [NinjaScriptProperty]
        [Range(5.0, 80.0)]
        [Display(Name = "Exhaustion Wick Min %", Order = 1, GroupName = "1. Exhaustion")]
        public double ExhaustWickMinPct { get; set; }

        // ---- Liquidity Walls ----

        [NinjaScriptProperty]
        [Display(Name = "Show Liquidity Walls (Rithmic L2)", Order = 1, GroupName = "2. Liquidity (L2)")]
        public bool ShowLiquidityWalls { get; set; }

        [NinjaScriptProperty]
        [Range(10, 5000)]
        [Display(Name = "Wall Min Size (contracts)", Order = 2, GroupName = "2. Liquidity (L2)")]
        public int LiquidityWallMin { get; set; }

        [NinjaScriptProperty]
        [Range(10, 600)]
        [Display(Name = "Wall Stale (seconds)", Order = 3, GroupName = "2. Liquidity (L2)")]
        public int LiquidityWallStaleSec { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Max Walls Per Side", Order = 4, GroupName = "2. Liquidity (L2)")]
        public int LiquidityMaxPerSide { get; set; }

        [XmlIgnore]
        [Display(Name = "Wall Bid (resting buy)", Order = 5, GroupName = "2. Liquidity (L2)")]
        public Brush WallBidBrush { get; set; }
        [Browsable(false)] public string WallBidBrushSerialize { get { return Serialize.BrushToString(WallBidBrush); } set { WallBidBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Wall Ask (resting sell)", Order = 6, GroupName = "2. Liquidity (L2)")]
        public Brush WallAskBrush { get; set; }
        [Browsable(false)] public string WallAskBrushSerialize { get { return Serialize.BrushToString(WallAskBrush); } set { WallAskBrush = Serialize.StringToBrush(value); } }

        // ---- MAD Detection ----

        [NinjaScriptProperty]
        [Range(1.0, double.MaxValue)]
        [Display(Name = "Absorption Threshold", Description = "Min contracts on one side. ~3-5 MNQ, ~15-25 NQ.", Order = 1, GroupName = "3. MAD Detection")]
        public double AbsorptionThreshold { get; set; }

        [NinjaScriptProperty]
        [Range(0.01, 1.0)]
        [Display(Name = "Min Delta Ratio", Order = 2, GroupName = "3. MAD Detection")]
        public double MinDeltaRatio { get; set; }

        [NinjaScriptProperty]
        [Range(0.01, double.MaxValue)]
        [Display(Name = "Min Strength", Order = 3, GroupName = "3. MAD Detection")]
        public double MinStrength { get; set; }

        [NinjaScriptProperty]
        [Range(1.0, 10.0)]
        [Display(Name = "Strong Signal Mult", Order = 4, GroupName = "3. MAD Detection")]
        public double StrongMult { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Cluster Ticks", Order = 5, GroupName = "3. MAD Detection")]
        public int ClusterTicks { get; set; }

        // ---- Display ----

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "Level Extension (bars)", Order = 1, GroupName = "4. Display")]
        public int LevelExtension { get; set; }

        [NinjaScriptProperty]
        [Range(10, 1000)]
        [Display(Name = "Lookback Bars", Order = 2, GroupName = "4. Display")]
        public int LookbackBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Invalidate On Close", Order = 3, GroupName = "4. Display")]
        public bool InvalidateOnClose { get; set; }

        // ---- Signals ----

        [NinjaScriptProperty]
        [Display(Name = "Show Trapped Sellers", Order = 1, GroupName = "5. Signals")]
        public bool ShowTrappedSellers { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Trapped Buyers", Order = 2, GroupName = "5. Signals")]
        public bool ShowTrappedBuyers { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Failed Pullbacks", Order = 3, GroupName = "5. Signals")]
        public bool ShowFailedPullbacks { get; set; }

        #endregion
    }
}
