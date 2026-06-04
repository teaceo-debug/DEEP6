// MADConfluenceAI.cs — Core: state machine, OnBarUpdate orchestration
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.DrawingTools;
using SharpDX;
using SharpDX.Direct2D1;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public struct MADConfig
    {
        // Signal weights
        public double AbsorptionWeight;
        public double ExhaustionWeight;
        public double DeltaWeight;
        public double ImbalanceWeight;
        public double IcebergWeight;
        public double LiquidityWeight;
        public double TrapWeight;
        // Thresholds
        public double MinConfidenceScore;
        public double EliteThreshold;
        public double HighThreshold;
        public double AbsorptionVolumeMultiplier;
        public double ImbalanceRatio;
        public int SweepReversalSeconds;
        public double ExhaustionDeltaDecay;
        public int TrapFailureSeconds;
        // Session
        public int OpeningRangeMinutes;
        public int WarmupBars;
        // Risk
        public int DefaultStopTicks;
        public int DefaultTargetTicks;
        public double MaxRiskRewardRatio;

        public static MADConfig Defaults => new MADConfig
        {
            AbsorptionWeight = 1.0, ExhaustionWeight = 1.0, DeltaWeight = 1.0,
            ImbalanceWeight = 1.0, IcebergWeight = 1.0, LiquidityWeight = 1.0, TrapWeight = 1.0,
            MinConfidenceScore = 60, EliteThreshold = 90, HighThreshold = 75,
            AbsorptionVolumeMultiplier = 3.0, ImbalanceRatio = 1.5,
            SweepReversalSeconds = 15, ExhaustionDeltaDecay = 0.7, TrapFailureSeconds = 30,
            OpeningRangeMinutes = 30, WarmupBars = 10,
            DefaultStopTicks = 20, DefaultTargetTicks = 40, MaxRiskRewardRatio = 5.0
        };

        public MADConfig Validated()
        {
            var c = this;
            c.AbsorptionWeight = Math.Max(0, Math.Min(3, c.AbsorptionWeight));
            c.ExhaustionWeight = Math.Max(0, Math.Min(3, c.ExhaustionWeight));
            c.DeltaWeight = Math.Max(0, Math.Min(3, c.DeltaWeight));
            c.ImbalanceWeight = Math.Max(0, Math.Min(3, c.ImbalanceWeight));
            c.IcebergWeight = Math.Max(0, Math.Min(3, c.IcebergWeight));
            c.LiquidityWeight = Math.Max(0, Math.Min(3, c.LiquidityWeight));
            c.TrapWeight = Math.Max(0, Math.Min(3, c.TrapWeight));
            c.MinConfidenceScore = Math.Max(0, Math.Min(100, c.MinConfidenceScore));
            c.WarmupBars = Math.Max(10, c.WarmupBars);
            return c;
        }
    }

    public partial class MADConfluenceAI : Indicator
    {
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Institutional-grade execution intelligence for NQ futures — MAD Confluence AI";
                Name = "MAD Confluence AI";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DisplayInDataBox = true;
                DrawOnPricePanel = true;
                DrawHorizontalGridLines = true;
                DrawVerticalGridLines = true;
                PaintPriceMarkers = true;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;
                IsSuspendedWhileInactive = true;
            }
            else if (State == State.Configure)
            {
                AddPlot(Brushes.Transparent, "Score");
                AddPlot(Brushes.Transparent, "Direction");
                AddDataSeries(BarsPeriodType.Minute, 5);
                AddDataSeries(BarsPeriodType.Minute, 15);
            }
            else if (State == State.DataLoaded)
            {
                InitDataPipeline();
                _marketState = new MADMarketState();
                _levelEngine = new MADLevelEngine();
                _config = BuildConfig();
                _lastSignals = new List<MADSignalResult>();
                _signalHistory = new List<SignalHistoryEntry>();
            }
            else if (State == State.Terminated)
            {
                DisposeDx();
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 1) return;

            if (BarsInProgress == 1)
            {
                // 5-minute series: update HTF bias
                _htf5mCloses[_htf5mCount % 25] = Closes[1][0];
                _htf5mCount++;

                if (_htf5mCount >= 20)
                {
                    // Manual SMA(20) from rolling buffer
                    double sum = 0;
                    for (int i = 0; i < 20; i++)
                        sum += _htf5mCloses[(_htf5mCount - 1 - i) % 25];
                    double sma20 = sum / 20.0;
                    double close = Closes[1][0];

                    // Set HtfBias based on close vs SMA20 with 0.1% threshold
                    if (close > sma20 * 1.001)
                        _marketState.HtfBias = MADTrend.Bullish;
                    else if (close < sma20 * 0.999)
                        _marketState.HtfBias = MADTrend.Bearish;
                    else
                        _marketState.HtfBias = MADTrend.Neutral;
                }

                if (_htf5mCount >= 10)
                {
                    // HtfMomentum: % change over last 10 bars
                    double latest = _htf5mCloses[(_htf5mCount - 1) % 25];
                    double oldest = _htf5mCloses[(_htf5mCount - 10) % 25];
                    if (oldest > 0)
                        _marketState.HtfMomentum = (latest - oldest) / oldest;
                }

                return;
            }

            if (BarsInProgress == 2)
            {
                // 15-minute series: reserved for future use
                return;
            }

            if (BarsInProgress != 0) return;

            FinalizeCurrentBar();
            _lastRenderedClose = Close[0];

            // ── T29: Historical mode warm-up ────────────────────────────
            _processedBars++;
            if (_processedBars <= WarmupBars)
            {
                // During warm-up: set score to 0, direction to 0
                Values[0][0] = 0;
                Values[1][0] = 0;
                return; // Skip detection/scoring during warm-up
            }
            if (!_isWarmedUp) _isWarmedUp = true;

            // Initialize state objects if not done yet
            if (_marketState == null) _marketState = new MADMarketState();
            if (_levelEngine == null) _levelEngine = new MADLevelEngine();
            if (_config.WarmupBars == 0) _config = BuildConfig();

            // Update market state
            _marketState.Update(High[0], Low[0], Close[0], (long)Volume[0], Time[0]);

            // Update level engine
            _levelEngine.SetSessionExtremes(_marketState.SessionHigh, _marketState.SessionLow);
            if (_marketState.PrevDayHigh > 0) _levelEngine.SetPriorDayLevels(_marketState.PrevDayHigh, _marketState.PrevDayLow);
            _levelEngine.UpdateVwap(Close[0], (long)Volume[0]);
            _levelEngine.GeneratePsychologicalLevels(Low[0] - 50, High[0] + 50);
            _levelEngine.RecomputeQuality();

            // Get nearby levels for current price
            var nearbyLevels = _levelEngine.GetNearbyLevels(Close[0], 5.0);
            bool isAtKeyLevel = nearbyLevels.Count > 0;

            // Run all 12 detectors
            var signals = new List<MADSignalResult>();
            double avgBarVol = _marketState.VolEma > 0 ? _marketState.VolEma : 1000;

            var abs01 = DetectAbs01(_bars.Count > 0 ? _bars[_bars.Count - 1] : null, _bars, _marketState);
            var abs02 = DetectAbs02(_bars.Count > 0 ? _bars[_bars.Count - 1] : null, _bars, _marketState);
            var exh01 = DetectExh01(_bars.Count > 0 ? _bars[_bars.Count - 1] : null, _bars, _marketState);
            var exh02 = DetectExh02(_bars.Count > 0 ? _bars[_bars.Count - 1] : null, _bars, _marketState);
            var delt01 = DetectDelt01(_bars.Count > 0 ? _bars[_bars.Count - 1] : null, _bars, _marketState, _deltaPipeline);
            var delt02 = DetectDelt02(_bars.Count > 0 ? _bars[_bars.Count - 1] : null, _bars, _marketState, _deltaPipeline);
            var imb01 = DetectImb01(_bars.Count > 0 ? _bars[_bars.Count - 1] : null, _config.ImbalanceRatio);
            var ice01 = DetectIce01(_bars.Count > 0 ? _bars[_bars.Count - 1] : null, _isDomAvailable, GetRefillCount);
            var liqsw01 = DetectLiqSw01(_bars.Count > 0 ? _bars[_bars.Count - 1] : null, nearbyLevels, avgBarVol);
            var fail01 = DetectFail01(_bars.Count > 0 ? _bars[_bars.Count - 1] : null);
            var trap01 = DetectTrap01(_bars.Count > 0 ? _bars[_bars.Count - 1] : null, _bars, nearbyLevels, avgBarVol);
            var reg01 = DetectReg01(_marketState, _deltaPipeline, _bars);

            if (abs01 != null) signals.Add(abs01);
            if (abs02 != null) signals.Add(abs02);
            if (exh01 != null) signals.Add(exh01);
            if (exh02 != null) signals.Add(exh02);
            if (delt01 != null) signals.Add(delt01);
            if (delt02 != null) signals.Add(delt02);
            if (imb01 != null) signals.Add(imb01);
            if (ice01 != null) signals.Add(ice01);
            if (liqsw01 != null) signals.Add(liqsw01);
            if (fail01 != null) signals.Add(fail01);
            if (trap01 != null) signals.Add(trap01);
            if (reg01 != null) signals.Add(reg01);

            _lastSignals = signals;

            // Get regime from REG-01
            MADRegime regime = MADRegime.Ranging;
            if (reg01 != null && reg01.Detail != null)
            {
                if (reg01.Detail.Contains("Trending")) regime = MADRegime.Trending;
                else if (reg01.Detail.Contains("Volatile")) regime = MADRegime.Volatile;
                else if (reg01.Detail.Contains("Thin")) regime = MADRegime.Thin;
            }

            _currentRegime = regime;

            // Run scoring, classification, context, decision
            _scorerResult = RunScoringEngine(signals, _config, regime, isAtKeyLevel);
            var setupType = ClassifySetup(signals, regime, isAtKeyLevel);
            _marketContext = BuildMarketContext(_marketState, regime, Time[0]);
            _decision = MakeDecision(_scorerResult, _marketContext, setupType, Close[0], nearbyLevels, _config);

            // Store signal history for persistent rendering (T11/T13)
            if (signals.Count > 0 || (_decision != null && _decision.Action != MADAction.DoNotTrade))
            {
                _signalHistory.Add(new SignalHistoryEntry
                {
                    BarIndex = CurrentBar,
                    Signals = new List<MADSignalResult>(signals),
                    Decision = _decision
                });
            }
            // Prune entries older than 20 bars
            _signalHistory.RemoveAll(h => CurrentBar - h.BarIndex > 20);
            // Cap buffer at 100 entries
            while (_signalHistory.Count > 100)
                _signalHistory.RemoveAt(0);

            // Set plot values for strategy consumption
            Values[0][0] = _decision != null ? _decision.Score : 0;
            Values[1][0] = _decision != null ? (_decision.Action == MADAction.Long ? 1 : _decision.Action == MADAction.Short ? -1 : 0) : 0;
        }

        #region Signal Weights
        [NinjaScriptProperty]
        [Display(Name = "Absorption Weight", Description = "Weight for absorption signals (0-3)", GroupName = "1 Signal Weights", Order = 1)]
        [Range(0, 3)]
        public double AbsorptionWeight { get; set; } = 1.0;

        [NinjaScriptProperty]
        [Display(Name = "Exhaustion Weight", GroupName = "1 Signal Weights", Order = 2)]
        [Range(0, 3)]
        public double ExhaustionWeight { get; set; } = 1.0;

        [NinjaScriptProperty]
        [Display(Name = "Delta Weight", GroupName = "1 Signal Weights", Order = 3)]
        [Range(0, 3)]
        public double DeltaWeight { get; set; } = 1.0;

        [NinjaScriptProperty]
        [Display(Name = "Imbalance Weight", GroupName = "1 Signal Weights", Order = 4)]
        [Range(0, 3)]
        public double ImbalanceWeight { get; set; } = 1.0;

        [NinjaScriptProperty]
        [Display(Name = "Iceberg Weight", GroupName = "1 Signal Weights", Order = 5)]
        [Range(0, 3)]
        public double IcebergWeight { get; set; } = 1.0;

        [NinjaScriptProperty]
        [Display(Name = "Liquidity Weight", GroupName = "1 Signal Weights", Order = 6)]
        [Range(0, 3)]
        public double LiquidityWeight { get; set; } = 1.0;

        [NinjaScriptProperty]
        [Display(Name = "Trap Weight", GroupName = "1 Signal Weights", Order = 7)]
        [Range(0, 3)]
        public double TrapWeight { get; set; } = 1.0;
        #endregion

        #region Thresholds
        [NinjaScriptProperty]
        [Display(Name = "Min Confidence Score", GroupName = "2 Thresholds", Order = 1)]
        [Range(0, 100)]
        public double MinConfidenceScore { get; set; } = 60;

        [NinjaScriptProperty]
        [Display(Name = "Elite Threshold", GroupName = "2 Thresholds", Order = 2)]
        [Range(75, 100)]
        public double EliteThreshold { get; set; } = 90;

        [NinjaScriptProperty]
        [Display(Name = "High Threshold", GroupName = "2 Thresholds", Order = 3)]
        [Range(50, 95)]
        public double HighThreshold { get; set; } = 75;

        [NinjaScriptProperty]
        [Display(Name = "Absorption Volume Multiplier", GroupName = "2 Thresholds", Order = 4)]
        [Range(1.5, 10)]
        public double AbsorptionVolumeMultiplier { get; set; } = 3.0;

        [NinjaScriptProperty]
        [Display(Name = "Imbalance Ratio", GroupName = "2 Thresholds", Order = 5)]
        [Range(1.5, 10)]
        public double ImbalanceRatio { get; set; } = 1.5;

        [NinjaScriptProperty]
        [Display(Name = "Sweep Reversal Seconds", GroupName = "2 Thresholds", Order = 6)]
        [Range(5, 60)]
        public int SweepReversalSeconds { get; set; } = 15;

        [NinjaScriptProperty]
        [Display(Name = "Exhaustion Delta Decay", GroupName = "2 Thresholds", Order = 7)]
        [Range(0.3, 0.95)]
        public double ExhaustionDeltaDecay { get; set; } = 0.7;

        [NinjaScriptProperty]
        [Display(Name = "Trap Failure Seconds", GroupName = "2 Thresholds", Order = 8)]
        [Range(10, 120)]
        public int TrapFailureSeconds { get; set; } = 30;
        #endregion

        #region Visual Toggles
        [NinjaScriptProperty]
        [Display(Name = "Show Level Zones", GroupName = "3 Visual", Order = 1)]
        public bool ShowLevelZones { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Show Signal Markers", GroupName = "3 Visual", Order = 2)]
        public bool ShowSignalMarkers { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Show Dashboard", GroupName = "3 Visual", Order = 3)]
        public bool ShowDashboard { get; set; } = true;

        // ShowHeatmap, ShowSlTp, ShowFootprintCells, CellColumnWidth, CellFontSize removed in Direction A redesign
        #endregion

        #region Session
        [NinjaScriptProperty]
        [Display(Name = "Opening Range Minutes", GroupName = "4 Session", Order = 1)]
        [Range(5, 120)]
        public int OpeningRangeMinutes { get; set; } = 30;

        [NinjaScriptProperty]
        [Display(Name = "Warmup Bars", GroupName = "4 Session", Order = 2)]
        [Range(10, 200)]
        public int WarmupBars { get; set; } = 10;

        [NinjaScriptProperty]
        [Display(Name = "RTH Start Hour", GroupName = "4 Session", Order = 3)]
        [Range(0, 23)]
        public int RthStartHour { get; set; } = 9;

        [NinjaScriptProperty]
        [Display(Name = "RTH Start Minute", GroupName = "4 Session", Order = 4)]
        [Range(0, 59)]
        public int RthStartMinute { get; set; } = 30;
        #endregion

        #region Risk
        [NinjaScriptProperty]
        [Display(Name = "Default Stop Ticks", GroupName = "5 Risk", Order = 1)]
        [Range(4, 200)]
        public int DefaultStopTicks { get; set; } = 20;

        [NinjaScriptProperty]
        [Display(Name = "Default Target Ticks", GroupName = "5 Risk", Order = 2)]
        [Range(8, 400)]
        public int DefaultTargetTicks { get; set; } = 40;

        [NinjaScriptProperty]
        [Display(Name = "Max Risk Reward Ratio", GroupName = "5 Risk", Order = 3)]
        [Range(1, 10)]
        public double MaxRiskRewardRatio { get; set; } = 5.0;
        #endregion

        // ── Orchestration state ──────────────────────────────────────────
        private MADMarketState _marketState;
        private MADLevelEngine _levelEngine;
        private MADConfig _config;
        private List<MADSignalResult> _lastSignals = new List<MADSignalResult>();
        private double _lastRenderedClose;
        private volatile MADScorerResult _scorerResult;
        private volatile MADDecision _decision;
        private volatile MADMarketContext _marketContext;

        // Signal history buffer for persistent rendering (T11/T13)
        private sealed class SignalHistoryEntry
        {
            public int BarIndex;
            public List<MADSignalResult> Signals;
            public MADDecision Decision;
        }
        private List<SignalHistoryEntry> _signalHistory = new List<SignalHistoryEntry>();

        // ── HTF bias state (5-minute secondary series) ───────────────────
        private double[] _htf5mCloses = new double[25];
        private int _htf5mCount = 0;

        // Helper to build MADConfig from current property values
        private MADConfig BuildConfig() => new MADConfig
        {
            AbsorptionWeight = AbsorptionWeight, ExhaustionWeight = ExhaustionWeight,
            DeltaWeight = DeltaWeight, ImbalanceWeight = ImbalanceWeight,
            IcebergWeight = IcebergWeight, LiquidityWeight = LiquidityWeight, TrapWeight = TrapWeight,
            MinConfidenceScore = MinConfidenceScore, EliteThreshold = EliteThreshold, HighThreshold = HighThreshold,
            AbsorptionVolumeMultiplier = AbsorptionVolumeMultiplier, ImbalanceRatio = ImbalanceRatio,
            SweepReversalSeconds = SweepReversalSeconds, ExhaustionDeltaDecay = ExhaustionDeltaDecay,
            TrapFailureSeconds = TrapFailureSeconds, OpeningRangeMinutes = OpeningRangeMinutes,
            WarmupBars = WarmupBars, DefaultStopTicks = DefaultStopTicks,
            DefaultTargetTicks = DefaultTargetTicks, MaxRiskRewardRatio = MaxRiskRewardRatio
        }.Validated();
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6.MADConfluenceAI[] cacheMADConfluenceAI;
        public DEEP6.MADConfluenceAI MADConfluenceAI()
        {
            return MADConfluenceAI(Input);
        }

        public DEEP6.MADConfluenceAI MADConfluenceAI(ISeries<double> input)
        {
            if (cacheMADConfluenceAI != null)
                for (int idx = cacheMADConfluenceAI.Length - 1; idx >= 0; idx--)
                    if (cacheMADConfluenceAI[idx] != null && cacheMADConfluenceAI[idx].EqualsInput(input))
                        return cacheMADConfluenceAI[idx];
            return CacheIndicator<DEEP6.MADConfluenceAI>(new DEEP6.MADConfluenceAI(), input, ref cacheMADConfluenceAI);
        }
    }
}
#endregion
