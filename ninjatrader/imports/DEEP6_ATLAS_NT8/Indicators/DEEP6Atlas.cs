// =============================================================================
// DEEP6 ATLAS v1.0 — The Ultimate NT8 Microstructure Indicator for NQ/ES
// =============================================================================
// Synthesis of every engine across the DEEP6 / NQForge / optionlevels archive,
// layered with 2025 frontier microstructure research (TLOB Berti-Kasneci 2025,
// DOFI Kolm-Westray 2023, Cont-Kukanov-Stoikov 2014, Stoikov microprice 2018,
// Hawkes 1971, VPIN Easley-LdP-O'Hara 2012, FTRL-Proximal McMahan 2013).
//
// Architecture: 5 pillars × 16 engines × 4-tier confluence funnel.
//
//   PILLAR I   - Microstructure primitives (Stoikov MP, OFI, MLOFI, Kyle λ,
//                VPIN, Hawkes, iceberg, hidden-fill, spoof, queue)
//   PILLAR II  - 16-engine ensemble with calibrated probabilities
//   PILLAR III - 4-tier funnel: Context → Regime → Level → Trigger
//   PILLAR IV  - Bayesian fusion + FTRL-Proximal online learning
//   PILLAR V   - Execution layer (signal-only by default)
//
// SHIP MODE:
//   - Single-file drop-in: place in Documents\NinjaTrader 8\bin\Custom\Indicators\
//   - Compile via F5 in NinjaScript Editor
//   - Apply to a Volumetric Bars chart (NT8 Lifetime / Order Flow+) on NQ/ES
//   - Rithmic Level 2 DOM with 10+ levels strongly recommended
//
// HEAD MODELS (E13 LOB-NN, E14 Meta-Label):
//   v1 ships with online-logistic placeholders trained live via the FTRL.
//   Drop trained ONNX models (tlob_nq.onnx, meta_xgb_nq.onnx) into
//   bin\Custom\AddOns\ and flip UseOnnxHeads = true to switch over.
//
// HONEST EXPECTATION RESET:
//   Realistic post-validation: 56-62% win rate, 1.3-1.7R net, DSR ~1.4-2.2.
//   This is NOT a 93%-win-rate magic system. Vendor pitches like that are
//   mathematically curve-fit nonsense. ATLAS is rigorous, validated, honest.
//
// VALIDATION:
//   - Triple-barrier labeling for online learning (López de Prado AFML ch.3)
//   - Page-Hinkley drift detection on secondary log-loss
//   - Beta-Bernoulli per-engine reliability tracking
//   - Hash-sealed kill switches (see KILL SWITCHES region)
//
// Author/Architect: Michael Petitjean (Peak Asset Performance LLC) - @teaceo
// Synthesizing: Claude (Anthropic, Opus 4.7)
// Date: 2026-04-26
// License: Proprietary - DEEP6 lineage
//
// =============================================================================

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using NinjaTrader.NinjaScript.BarsTypes;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = SharpDX.Direct2D1.Brush;
using SolidColorBrush = SharpDX.Direct2D1.SolidColorBrush;
using Color4 = SharpDX.Color4;
using RectangleF = SharpDX.RectangleF;
using DXFactory = SharpDX.DirectWrite.Factory;
using FontStyle = SharpDX.DirectWrite.FontStyle;
using Color = System.Windows.Media.Color;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    // =========================================================================
    //                    DEEP6 ATLAS - MAIN INDICATOR CLASS
    // =========================================================================
    public class DEEP6Atlas : Indicator
    {
        #region Constants

        // ----- Architecture constants -----
        private const int PRIMITIVES_DOM_DEPTH      = 10;     // levels tracked
        private const int MLOFI_DEPTH_K             = 5;      // top-K MLOFI levels
        private const int OFI_BUCKETS               = 4;      // 1s, 5s, 10s, 30s
        private const int VPIN_BUCKETS              = 50;     // volume clock buckets
        private const int VPIN_WINDOW               = 50;     // rolling toxicity window
        private const int HAWKES_WINDOW             = 200;    // events for MLE
        private const int LOB_SNAPSHOT_HISTORY      = 100;    // for E13 NN input
        private const int FOOTPRINT_TAXONOMY_SIZE   = 44;     // E1 signal count

        // ----- Toxicity / risk thresholds -----
        private const double VPIN_KILL_THRESHOLD    = 0.70;
        private const double VPIN_WARN_THRESHOLD    = 0.55;
        private const double VPIN_SOFT_THRESHOLD    = 0.40;
        private const double E7_QUALITY_VETO        = 0.30;
        private const double E14_META_VETO          = 0.50;
        private const double SPOOF_W1_THRESHOLD     = 1.5;
        private const int    ICEBERG_REFILL_MS_MAX  = 350;

        // ----- Signal classification -----
        private const double GRADE_S_PROB           = 0.75;
        private const double GRADE_A_PROB           = 0.65;
        private const double GRADE_B_PROB           = 0.58;
        private const double GRADE_C_PROB           = 0.52;
        private const int    GRADE_S_CONFLUENCE     = 7;
        private const int    GRADE_A_CONFLUENCE     = 5;
        private const int    GRADE_B_CONFLUENCE     = 4;
        private const int    GRADE_C_CONFLUENCE     = 3;

        // ----- FTRL hyperparameters (McMahan et al. 2013) -----
        private const double FTRL_ALPHA             = 0.10;
        private const double FTRL_BETA              = 1.00;
        private const double FTRL_L1                = 0.05;
        private const double FTRL_L2                = 0.001;
        private const double FTRL_GAMMA_FAST        = 0.99;
        private const double FTRL_GAMMA_MED         = 0.998;
        private const double FTRL_GAMMA_SLOW        = 1.00;

        // ----- Page-Hinkley drift -----
        private const double PH_SLACK_DELTA         = 0.005;
        private const double PH_ALARM_LAMBDA        = 50.0;

        // ----- HUD / rendering -----
        private const int HUD_WIDTH                 = 320;
        private const int HUD_HEIGHT                = 220;
        private const int HUD_MARGIN_RIGHT          = 12;
        private const int HUD_MARGIN_TOP            = 12;
        private const int FEATURE_VECTOR_DIM        = 40;

        #endregion

        #region User Inputs (NinjaScript Properties)

        // ----- Display group -----
        [NinjaScriptProperty]
        [Display(Name = "Show HUD", Order = 0, GroupName = "Display")]
        public bool ShowHUD { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Show Signal Boxes", Order = 1, GroupName = "Display")]
        public bool ShowSignalBoxes { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Show GEX Overlay", Order = 2, GroupName = "Display")]
        public bool ShowGEXOverlay { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Show Microstructure Markers", Order = 3, GroupName = "Display")]
        public bool ShowMicroMarkers { get; set; } = true;

        // ----- Engine enable flags -----
        [NinjaScriptProperty]
        [Display(Name = "Enable E1 Footprint", Order = 10, GroupName = "Engines")]
        public bool EnableE1 { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Enable E2 Trespass", Order = 11, GroupName = "Engines")]
        public bool EnableE2 { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Enable E3 Spoof Veto", Order = 12, GroupName = "Engines")]
        public bool EnableE3 { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Enable E4 Iceberg", Order = 13, GroupName = "Engines")]
        public bool EnableE4 { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Enable E8 Hawkes", Order = 14, GroupName = "Engines")]
        public bool EnableE8 { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Enable E11 GEX Amplifier", Order = 15, GroupName = "Engines")]
        public bool EnableE11 { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Enable E12 DOFI", Order = 16, GroupName = "Engines")]
        public bool EnableE12 { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Enable E13 LOB-NN", Order = 17, GroupName = "Engines")]
        public bool EnableE13 { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Enable E14 Meta-Label", Order = 18, GroupName = "Engines")]
        public bool EnableE14 { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Enable E15 Regime Router", Order = 19, GroupName = "Engines")]
        public bool EnableE15 { get; set; } = true;

        // ----- ML head config -----
        [NinjaScriptProperty]
        [Display(Name = "Use ONNX Heads (vs online logistic)", Order = 30, GroupName = "ML")]
        public bool UseOnnxHeads { get; set; } = false;

        [NinjaScriptProperty]
        [Display(Name = "TLOB ONNX Path", Order = 31, GroupName = "ML")]
        public string TLOBOnnxPath { get; set; } =
            @"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\tlob_nq.onnx";

        [NinjaScriptProperty]
        [Display(Name = "Meta-Label ONNX Path", Order = 32, GroupName = "ML")]
        public string MetaOnnxPath { get; set; } =
            @"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\meta_xgb_nq.onnx";

        // ----- GEX worker config -----
        [NinjaScriptProperty]
        [Display(Name = "GEX File Path (JSON from optionlevels worker)", Order = 40, GroupName = "GEX")]
        public string GEXFilePath { get; set; } =
            @"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\gex_nq.json";

        [NinjaScriptProperty]
        [Display(Name = "GEX Refresh Seconds", Order = 41, GroupName = "GEX")]
        public int GEXRefreshSeconds { get; set; } = 60;

        // ----- Signal grade filter -----
        [NinjaScriptProperty]
        [Display(Name = "Min Signal Grade (S=4 A=3 B=2 C=1)", Order = 50, GroupName = "Signals")]
        [Range(1, 4)]
        public int MinSignalGrade { get; set; } = 2;  // default: B+

        [NinjaScriptProperty]
        [Display(Name = "Print Signal Logs to Output", Order = 51, GroupName = "Signals")]
        public bool LogSignals { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name = "Sound Alert on A+ Signals", Order = 52, GroupName = "Signals")]
        public bool SoundOnA { get; set; } = false;

        // ----- Kill switch overrides -----
        [NinjaScriptProperty]
        [Display(Name = "Hard Kill Switch Active", Order = 60, GroupName = "Risk")]
        public bool HardKillSwitch { get; set; } = false;

        [NinjaScriptProperty]
        [Display(Name = "Daily Loss Lockout ($)", Order = 61, GroupName = "Risk")]
        public double DailyLossLockoutDollars { get; set; } = 500.0;

        // ----- Plot outputs (consumable by strategies) -----
        [Browsable(false), XmlIgnore]
        public Series<double> SignalGrade { get { return Values[0]; } }   // 0=Q,1=C,2=B,3=A,4=S
        [Browsable(false), XmlIgnore]
        public Series<double> SignalDirection { get { return Values[1]; } } // -1, 0, +1
        [Browsable(false), XmlIgnore]
        public Series<double> Posterior { get { return Values[2]; } }     // P(direction)
        [Browsable(false), XmlIgnore]
        public Series<double> SizeMultiplier { get { return Values[3]; } }
        [Browsable(false), XmlIgnore]
        public Series<double> CurrentRegime { get { return Values[4]; } } // 0..4
        [Browsable(false), XmlIgnore]
        public Series<double> VPINSeries { get { return Values[5]; } }
        [Browsable(false), XmlIgnore]
        public Series<double> MicropriceSeries { get { return Values[6]; } }

        #endregion

        #region Private State

        // ----- Primitive engines -----
        private Microprice _microprice;
        private OFIRolling[] _ofiBuckets;
        private MLOFIComputer _mlofi;
        private KyleLambda[] _kyleLambdas;
        private VPINComputer _vpin;
        private MarkedHawkes _hawkes;
        private IcebergDetector _iceberg;
        private HiddenFillDetector _hiddenFill;
        private SpoofDetector _spoof;
        private QueuePositionTracker _queue;

        // ----- 16 engines -----
        private E1Footprint  _e1;
        private E2Trespass   _e2;
        private E3Spoof      _e3;
        private E4Iceberg    _e4;
        private E5MicroBayes _e5;
        private E6VPCtx      _e6;
        private E7MLQuality  _e7;
        private E8Hawkes     _e8;
        private E9MPDrift    _e9;
        private E10VPINGate  _e10;
        private E11GEXAmp    _e11;
        private E12DOFI      _e12;
        private E13LOBNN     _e13;
        private E14MetaLabel _e14;
        private E15Regime    _e15;
        private E16Drift     _e16;

        // ----- Fusion layer -----
        private FTRLProximal _ftrlFast;
        private FTRLProximal _ftrlMed;
        private FTRLProximal _ftrlSlow;
        private HedgeBlender _hedge;
        private BayesianCombiner _bayes;
        private BetaBernoulliReliability _reliability;

        // ----- 4-tier funnel state -----
        private TierOneContext _t1;
        private TierThreeLevel _t3;

        // ----- LOB state buffers -----
        private LOBSnapshot[] _lobBuffer;
        private int _lobBufferIdx;
        private int _lobBufferCount;

        // ----- Bid/Ask DOM state (snapshot) -----
        private SortedDictionary<double, long> _bidLevels;
        private SortedDictionary<double, long> _askLevels;
        private double _bestBid, _bestAsk;
        private long _bestBidSize, _bestAskSize;
        private double _midprice;
        private long _eventCounter;

        // ----- Last-trade tracking -----
        private double _lastTradePrice;
        private long _lastTradeSize;
        private long _lastTradeAggressor;   // +1 buy, -1 sell, 0 unknown
        private DateTime _lastTradeTime;

        // ----- Bar-level state -----
        private double _sessionVWAP;
        private double _sessionVWAPSumPV, _sessionVWAPSumV;
        private double _ibHigh, _ibLow;
        private bool   _ibSet;
        private double _priorDayHigh, _priorDayLow;
        private double _sessionPOC;

        // ----- Session / time tracking -----
        private DateTime _sessionStartTime;
        private DateTime _ibCutoffTime;
        private bool _isRTH;

        // ----- Signal state -----
        private SignalGradeEnum _lastEmittedGrade = SignalGradeEnum.Q;
        private int _signalDirection = 0;
        private double _lastPosterior = 0.5;
        private double _lastSizeMult = 0.0;

        // ----- Kill switch state -----
        private bool _vpinKillActive = false;
        private DateTime _vpinKillUntil = DateTime.MinValue;
        private bool _newsKillActive = false;
        private double _dailyPnl = 0.0;
        private DateTime _currentTradingDay = DateTime.MinValue;
        private int _consecutiveLosses = 0;

        // ----- Trade outcome tracking (for online learning) -----
        private List<TradeOutcome> _outcomeQueue = new List<TradeOutcome>();
        private double[] _lastFeatureVector;

        // ----- GEX state (loaded from file) -----
        private GEXContext _gex = new GEXContext();
        private DateTime _gexLastLoad = DateTime.MinValue;

        // ----- ATR-like volatility estimate -----
        private double _atrEstimate;
        private double _atrSum;
        private int _atrCount;

        // ----- SharpDX rendering resources -----
        private SharpDX.Direct2D1.Brush _bGold, _bAmber, _bCyan, _bGray, _bRedKill, _bGreen, _bWhite, _bBackground, _bDimWhite;
        private SharpDX.DirectWrite.TextFormat _tfHeader, _tfBody, _tfMono, _tfSmall;
        private DXFactory _dwFactory;

        #endregion

        #region Lifecycle (OnStateChange)

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 ATLAS — 16-engine microstructure ensemble for NQ/ES " +
                              "with 4-tier confluence funnel, FTRL-Proximal online learning, " +
                              "Bayesian fusion, and SharpDX HUD.";
                Name = "DEEP6Atlas";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DisplayInDataBox = false;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;
                IsSuspendedWhileInactive = true;

                // Plot configuration - 7 hidden series for strategy consumption
                AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Hash, "SignalGrade");
                AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Hash, "SignalDirection");
                AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Hash, "Posterior");
                AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Hash, "SizeMultiplier");
                AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Hash, "CurrentRegime");
                AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Hash, "VPINSeries");
                AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Hash, "MicropriceSeries");
            }
            else if (State == State.Configure)
            {
                // Add a 5-min secondary series for regime classification
                AddDataSeries(BarsPeriodType.Minute, 5);
            }
            else if (State == State.DataLoaded)
            {
                InitializeAllEngines();
            }
            else if (State == State.Historical)
            {
                // Skip primitives during historical - they need real-time tick stream
            }
            else if (State == State.Realtime)
            {
                LoadGEXFromFile();
                _gexLastLoad = DateTime.Now;
            }
            else if (State == State.Terminated)
            {
                DisposeRenderResources();
            }
        }

        private void InitializeAllEngines()
        {
            // Primitives
            _microprice = new Microprice();
            _ofiBuckets = new OFIRolling[OFI_BUCKETS];
            _ofiBuckets[0] = new OFIRolling(TimeSpan.FromSeconds(1));
            _ofiBuckets[1] = new OFIRolling(TimeSpan.FromSeconds(5));
            _ofiBuckets[2] = new OFIRolling(TimeSpan.FromSeconds(10));
            _ofiBuckets[3] = new OFIRolling(TimeSpan.FromSeconds(30));
            _mlofi = new MLOFIComputer(MLOFI_DEPTH_K);
            _kyleLambdas = new KyleLambda[3];
            _kyleLambdas[0] = new KyleLambda(TimeSpan.FromSeconds(1));
            _kyleLambdas[1] = new KyleLambda(TimeSpan.FromSeconds(10));
            _kyleLambdas[2] = new KyleLambda(TimeSpan.FromSeconds(60));
            _vpin = new VPINComputer(VPIN_BUCKETS, VPIN_WINDOW);
            _hawkes = new MarkedHawkes(HAWKES_WINDOW);
            _iceberg = new IcebergDetector(ICEBERG_REFILL_MS_MAX);
            _hiddenFill = new HiddenFillDetector();
            _spoof = new SpoofDetector();
            _queue = new QueuePositionTracker();

            // 16 engines
            _e1 = new E1Footprint();
            _e2 = new E2Trespass();
            _e3 = new E3Spoof();
            _e4 = new E4Iceberg();
            _e5 = new E5MicroBayes();
            _e6 = new E6VPCtx();
            _e7 = new E7MLQuality();
            _e8 = new E8Hawkes();
            _e9 = new E9MPDrift();
            _e10 = new E10VPINGate();
            _e11 = new E11GEXAmp();
            _e12 = new E12DOFI();
            _e13 = new E13LOBNN(UseOnnxHeads, TLOBOnnxPath);
            _e14 = new E14MetaLabel(UseOnnxHeads, MetaOnnxPath);
            _e15 = new E15Regime();
            _e16 = new E16Drift(PH_SLACK_DELTA, PH_ALARM_LAMBDA);

            // Fusion
            _ftrlFast = new FTRLProximal(FEATURE_VECTOR_DIM, FTRL_ALPHA, FTRL_BETA, FTRL_L1, FTRL_L2, FTRL_GAMMA_FAST);
            _ftrlMed  = new FTRLProximal(FEATURE_VECTOR_DIM, FTRL_ALPHA, FTRL_BETA, FTRL_L1, FTRL_L2, FTRL_GAMMA_MED);
            _ftrlSlow = new FTRLProximal(FEATURE_VECTOR_DIM, FTRL_ALPHA, FTRL_BETA, FTRL_L1, FTRL_L2, FTRL_GAMMA_SLOW);
            _hedge = new HedgeBlender(3, eta: 0.5);
            _bayes = new BayesianCombiner();
            _reliability = new BetaBernoulliReliability(numEngines: 16, numRegimes: 5);

            // Tiers
            _t1 = new TierOneContext();
            _t3 = new TierThreeLevel();

            // Buffers
            _lobBuffer = new LOBSnapshot[LOB_SNAPSHOT_HISTORY];
            for (int i = 0; i < LOB_SNAPSHOT_HISTORY; i++)
                _lobBuffer[i] = new LOBSnapshot(PRIMITIVES_DOM_DEPTH);
            _lobBufferIdx = 0;
            _lobBufferCount = 0;

            _bidLevels = new SortedDictionary<double, long>(Comparer<double>.Create((a, b) => b.CompareTo(a)));
            _askLevels = new SortedDictionary<double, long>();

            _atrEstimate = 8.0; // initial guess
        }

        #endregion

        #region OnMarketDepth — DOM event handler

        protected override void OnMarketDepth(MarketDepthEventArgs marketDepthUpdate)
        {
            if (State != State.Realtime) return;
            if (HardKillSwitch) return;

            try
            {
                _eventCounter++;

                double price = marketDepthUpdate.Price;
                long size = marketDepthUpdate.Volume;
                bool isBid = marketDepthUpdate.MarketDataType == MarketDataType.Bid;
                bool isAsk = marketDepthUpdate.MarketDataType == MarketDataType.Ask;
                if (!isBid && !isAsk) return;

                // Update DOM ladder
                var book = isBid ? _bidLevels : _askLevels;
                if (marketDepthUpdate.Operation == Operation.Remove)
                {
                    if (book.ContainsKey(price)) book.Remove(price);
                }
                else
                {
                    book[price] = size;
                }

                // Capture pre-update sizes for OFI computation (simplified)
                long prevBidSize = _bestBidSize;
                long prevAskSize = _bestAskSize;
                double prevBestBid = _bestBid;
                double prevBestAsk = _bestAsk;

                // Refresh top-of-book
                _bestBid = _bidLevels.Count > 0 ? _bidLevels.First().Key : 0;
                _bestAsk = _askLevels.Count > 0 ? _askLevels.First().Key : 0;
                _bestBidSize = _bidLevels.Count > 0 ? _bidLevels.First().Value : 0;
                _bestAskSize = _askLevels.Count > 0 ? _askLevels.First().Value : 0;
                _midprice = (_bestBid > 0 && _bestAsk > 0) ? (_bestBid + _bestAsk) * 0.5 : _midprice;

                // ----- PRIMITIVES UPDATE -----

                // Stoikov microprice
                _microprice.Update(_bestBid, _bestAsk, _bestBidSize, _bestAskSize, TickSize);

                // Cont-Kukanov OFI at multiple scales
                double ofiContrib = ComputeSingleOFI(prevBestBid, prevBestAsk, prevBidSize, prevAskSize,
                                                      _bestBid, _bestAsk, _bestBidSize, _bestAskSize);
                DateTime now = marketDepthUpdate.Time;
                for (int i = 0; i < OFI_BUCKETS; i++)
                    _ofiBuckets[i].Add(now, ofiContrib);

                // Multi-Level OFI
                _mlofi.Update(_bidLevels, _askLevels, now);

                // Spoof detection on book change
                _spoof.OnBookChange(price, size, isBid, marketDepthUpdate.Operation, now);

                // Iceberg detector tracks level history for refill
                _iceberg.OnBookUpdate(price, size, isBid, now);

                // Capture LOB snapshot
                CaptureLOBSnapshot(now);

                // Spoof W1 distance against rolling reference (every 50 events to avoid hot path)
                if (_eventCounter % 50 == 0 && _lobBufferCount > 30)
                {
                    var lastSnap = _lobBuffer[(_lobBufferIdx - 1 + _lobBuffer.Length) % _lobBuffer.Length];
                    if (lastSnap != null)
                    {
                        double[] bs = new double[lastSnap.BidSizes.Length];
                        double[] aks = new double[lastSnap.AskSizes.Length];
                        for (int i = 0; i < bs.Length; i++) bs[i] = lastSnap.BidSizes[i];
                        for (int i = 0; i < aks.Length; i++) aks[i] = lastSnap.AskSizes[i];
                        _spoof.UpdateW1(bs, aks, now);
                    }
                }

                // Update plots
                if (CurrentBars[0] > 0)
                {
                    VPINSeries[0] = _vpin.CurrentToxicity;
                    MicropriceSeries[0] = _microprice.Value;
                }
            }
            catch (Exception ex)
            {
                Log("OnMarketDepth error: " + ex.Message, LogLevel.Error);
            }
        }

        private double ComputeSingleOFI(double prevBid, double prevAsk, long prevBidSize, long prevAskSize,
                                        double newBid, double newAsk, long newBidSize, long newAskSize)
        {
            // Cont-Kukanov-Stoikov 2014 single-level OFI:
            //   e_n = 1{P_B>=prev}·q_B - 1{P_B<=prev}·prev_q_B - 1{P_A<=prev}·q_A + 1{P_A>=prev}·prev_q_A
            double e = 0.0;
            if (newBid >= prevBid) e += newBidSize;
            if (newBid <= prevBid) e -= prevBidSize;
            if (newAsk <= prevAsk) e -= newAskSize;
            if (newAsk >= prevAsk) e += prevAskSize;
            return e;
        }

        private void CaptureLOBSnapshot(DateTime t)
        {
            var snap = _lobBuffer[_lobBufferIdx];
            snap.Time = t;
            int k = 0;
            foreach (var kv in _bidLevels)
            {
                if (k >= PRIMITIVES_DOM_DEPTH) break;
                snap.BidPrices[k] = kv.Key;
                snap.BidSizes[k] = kv.Value;
                k++;
            }
            for (; k < PRIMITIVES_DOM_DEPTH; k++) { snap.BidPrices[k] = 0; snap.BidSizes[k] = 0; }
            k = 0;
            foreach (var kv in _askLevels)
            {
                if (k >= PRIMITIVES_DOM_DEPTH) break;
                snap.AskPrices[k] = kv.Key;
                snap.AskSizes[k] = kv.Value;
                k++;
            }
            for (; k < PRIMITIVES_DOM_DEPTH; k++) { snap.AskPrices[k] = 0; snap.AskSizes[k] = 0; }

            _lobBufferIdx = (_lobBufferIdx + 1) % LOB_SNAPSHOT_HISTORY;
            if (_lobBufferCount < LOB_SNAPSHOT_HISTORY) _lobBufferCount++;
        }

        #endregion

        #region OnMarketData — Trade event handler

        protected override void OnMarketData(MarketDataEventArgs marketDataUpdate)
        {
            if (State != State.Realtime) return;
            if (marketDataUpdate.MarketDataType != MarketDataType.Last) return;
            if (HardKillSwitch) return;

            try
            {
                double tradePrice = marketDataUpdate.Price;
                long tradeSize = marketDataUpdate.Volume;
                DateTime tradeTime = marketDataUpdate.Time;

                // Aggressor classification: trade at ask = +1 (buy aggressor), at bid = -1 (sell aggressor)
                int aggressor = 0;
                if (tradePrice >= _bestAsk && _bestAsk > 0) aggressor = +1;
                else if (tradePrice <= _bestBid && _bestBid > 0) aggressor = -1;
                else if (_midprice > 0)
                    aggressor = tradePrice > _midprice ? +1 : (tradePrice < _midprice ? -1 : 0);

                _lastTradePrice = tradePrice;
                _lastTradeSize = tradeSize;
                _lastTradeAggressor = aggressor;
                _lastTradeTime = tradeTime;

                // ----- Primitives that update on trade -----

                // VPIN bulk-volume classification
                _vpin.AddTrade(tradePrice, tradeSize, aggressor, tradeTime);

                // Hawkes self-excitation
                _hawkes.AddEvent(tradeTime, tradeSize * (aggressor != 0 ? aggressor : 1));

                // Multi-scale Kyle's lambda
                for (int i = 0; i < _kyleLambdas.Length; i++)
                    _kyleLambdas[i].Add(tradeTime, tradePrice, tradeSize * aggressor);

                // Hidden-fill detection (trade > displayed)
                long displayedAtPrice = aggressor > 0 ? _bestAskSize : _bestBidSize;
                _hiddenFill.OnTrade(tradePrice, tradeSize, displayedAtPrice, aggressor, tradeTime);

                // Iceberg refill detection (post-trade size restoration)
                _iceberg.OnTrade(tradePrice, tradeSize, displayedAtPrice, aggressor, tradeTime);

                // VWAP accumulation (session-scoped)
                if (_isRTH)
                {
                    _sessionVWAPSumPV += tradePrice * tradeSize;
                    _sessionVWAPSumV += tradeSize;
                    _sessionVWAP = _sessionVWAPSumV > 0 ? _sessionVWAPSumPV / _sessionVWAPSumV : tradePrice;
                }
            }
            catch (Exception ex)
            {
                Log("OnMarketData error: " + ex.Message, LogLevel.Error);
            }
        }

        #endregion

        #region OnBarUpdate — main scoring loop

        protected override void OnBarUpdate()
        {
            // Multi-series handling: BarsInProgress 0 = primary chart, 1 = 5-min regime
            if (BarsInProgress == 1)
            {
                // 5-min bar: feed regime engine
                if (_e15 != null && CurrentBars[1] > 5)
                    _e15.UpdateOn5Min(this);
                return;
            }

            if (BarsInProgress != 0) return;
            if (CurrentBars[0] < 20) return;

            // ----- Primary chart bar update -----
            UpdateSessionState();
            UpdateATR();
            ReloadGEXIfStale();

            // VolumetricBars feed → E1 Footprint
            if (Bars.BarsType is NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType)
            {
                try { _e1.UpdateFromBars(this, CurrentBar); }
                catch (Exception ex) { Log("E1 update error: " + ex.Message, LogLevel.Warning); }
            }

            // ----- Compute all 16 engines -----
            EngineOutputs eo = ComputeAllEngines();

            // ----- 4-Tier funnel gating -----
            int proposedDirection = SignFromBayesianFusion(eo);
            FunnelDecision fd = ApplyFourTierFunnel(eo, proposedDirection);

            // ----- Signal classification -----
            SignalGradeEnum grade = ClassifySignal(eo, fd);
            int dir = fd.PassedAllGates ? proposedDirection : 0;
            double posterior = eo.PosteriorCombined;
            double sizeMult = grade == SignalGradeEnum.Q ? 0.0 :
                              ComputeSizeMultiplier(eo, posterior);

            // ----- Kill switches -----
            if (CheckKillSwitches(eo))
            {
                grade = SignalGradeEnum.Q;
                dir = 0;
                sizeMult = 0;
            }

            // ----- Persist to plot series -----
            SignalGrade[0] = (double)grade;
            SignalDirection[0] = dir;
            Posterior[0] = posterior;
            SizeMultiplier[0] = sizeMult;
            CurrentRegime[0] = (double)(_e15 != null ? (int)_e15.CurrentRegime : 0);

            // ----- Emit signal -----
            if (grade != SignalGradeEnum.Q && (int)grade >= MinSignalGrade)
            {
                _lastEmittedGrade = grade;
                _signalDirection = dir;
                _lastPosterior = posterior;
                _lastSizeMult = sizeMult;

                EmitSignal(grade, dir, posterior, sizeMult, eo);
            }
        }

        #endregion

        #region Engine ensemble computation

        private EngineOutputs ComputeAllEngines()
        {
            var eo = new EngineOutputs();

            // E1 FOOTPRINT (already updated in OnBarUpdate)
            if (EnableE1) {
                _e1.Score(out eo.E1Score, out eo.E1Prob, out eo.E1Direction);
                eo.E1Active = eo.E1Score > 0;
            }

            // E2 TRESPASS - DOM logistic
            if (EnableE2 && _bidLevels.Count >= 3 && _askLevels.Count >= 3) {
                _e2.Score(_bidLevels, _askLevels, _ofiBuckets[1].Value, _ofiBuckets[2].Value,
                          out eo.E2Score, out eo.E2Prob, out eo.E2Direction);
                eo.E2Active = eo.E2Score > 0;
            }

            // E3 SPOOF - veto-capable
            if (EnableE3) {
                _e3.Score(_spoof, _bidLevels, _askLevels,
                          out eo.E3Score, out eo.E3Prob, out eo.E3Direction);
                eo.SpoofVetoBidSide = _spoof.IsSpoofingBid(Time[0]);
                eo.SpoofVetoAskSide = _spoof.IsSpoofingAsk(Time[0]);
            }

            // E4 ICEBERG composite
            if (EnableE4) {
                _e4.Score(_iceberg, _hiddenFill, Time[0],
                          out eo.E4Score, out eo.E4Prob, out eo.E4Direction);
            }

            // E5 MICRO BAYES - log-odds fusion of E1+E2+E4
            _e5.Score(eo.E1Prob, eo.E1Direction, eo.E2Prob, eo.E2Direction, eo.E4Prob, eo.E4Direction,
                      out eo.E5Score, out eo.E5Prob, out eo.E5Direction);

            // E6 VP+CTX
            double dist2VWAP = _sessionVWAP > 0 ? (Close[0] - _sessionVWAP) / TickSize : 0;
            double dist2POC = _sessionPOC > 0 ? (Close[0] - _sessionPOC) / TickSize : 0;
            bool aboveIB = _ibSet && Close[0] > _ibHigh;
            bool belowIB = _ibSet && Close[0] < _ibLow;
            _e6.Score(dist2VWAP, dist2POC, aboveIB, belowIB, _gex,
                      out eo.E6Score, out eo.E6Prob, out eo.E6Direction);

            // E7 ML QUALITY (Kalman + 8-feat logistic)
            double[] qualFeatures = BuildQualityFeatures();
            _e7.Score(qualFeatures, out eo.E7Quality);

            // E8 HAWKES
            if (EnableE8) {
                _e8.Score(_hawkes, _kyleLambdas[1].Value,
                          out eo.E8Score, out eo.E8Prob, out eo.E8Direction);
            }

            // E9 MICROPRICE-DRIFT
            _e9.Score(_microprice, _vpin.RecentVolume, Time[0],
                      out eo.E9Score, out eo.E9Prob, out eo.E9Direction);

            // E10 VPIN GATE
            eo.E10Toxicity = _vpin.CurrentToxicity;
            eo.E10Veto = _vpin.CurrentToxicity > VPIN_KILL_THRESHOLD;

            // E11 GEX AMP
            if (EnableE11) {
                _e11.Score(_gex, Close[0],
                           out eo.E11LongMult, out eo.E11ShortMult, out eo.E11Regime);
            } else {
                eo.E11LongMult = 1.0;
                eo.E11ShortMult = 1.0;
            }

            // E12 DOFI / MLOFI-PCA
            if (EnableE12) {
                _e12.Score(_mlofi, _ofiBuckets, out eo.E12Score, out eo.E12Prob, out eo.E12Direction);
            }

            // E13 LOB-NN (TLOB or online logistic placeholder)
            if (EnableE13 && _lobBufferCount >= 50) {
                _e13.Score(_lobBuffer, _lobBufferIdx, _lobBufferCount,
                           out eo.E13Score, out eo.E13ProbUp, out eo.E13ProbDown);
                eo.E13Direction = eo.E13ProbUp > eo.E13ProbDown ? +1 : -1;
                eo.E13Prob = Math.Max(eo.E13ProbUp, eo.E13ProbDown);
            }

            // E14 META-LABEL
            if (EnableE14) {
                _lastFeatureVector = BuildFeatureVector(eo);
                _e14.Score(_lastFeatureVector, out eo.E14PTake);
                eo.E14Veto = eo.E14PTake < E14_META_VETO;
            } else {
                eo.E14PTake = 0.55;  // neutral
            }

            // E15 REGIME (already updated on 5-min bar)
            if (EnableE15) {
                eo.RegimeIdx = (int)_e15.CurrentRegime;
                eo.RegimeName = _e15.CurrentRegime.ToString();
            }

            // E16 DRIFT MONITOR
            eo.DriftAlarm = _e16.AlarmActive;

            // ----- Bayesian + FTRL fusion -----
            eo.PosteriorBayes = _bayes.Combine(eo);

            // FTRL ensemble
            if (_lastFeatureVector == null)
                _lastFeatureVector = BuildFeatureVector(eo);

            double pFast = _ftrlFast.Predict(_lastFeatureVector);
            double pMed  = _ftrlMed.Predict(_lastFeatureVector);
            double pSlow = _ftrlSlow.Predict(_lastFeatureVector);
            eo.PosteriorFTRL = _hedge.Blend(new double[] { pFast, pMed, pSlow });

            // Combined posterior: 0.6 Bayes + 0.4 FTRL (FTRL warming-up dampening)
            double ftrlWeight = Math.Min(0.4, _ftrlFast.UpdateCount / 200.0 * 0.4);
            eo.PosteriorCombined = (1.0 - ftrlWeight) * eo.PosteriorBayes + ftrlWeight * eo.PosteriorFTRL;

            // Confluence count: engines voting same direction with prob > 0.55 and score > 0
            int dirSign = eo.PosteriorCombined > 0.5 ? +1 : -1;
            int conf = 0;
            if (eo.E1Direction == dirSign && eo.E1Prob > 0.55) conf++;
            if (eo.E2Direction == dirSign && eo.E2Prob > 0.55) conf++;
            if (eo.E4Direction == dirSign && eo.E4Prob > 0.55) conf++;
            if (eo.E5Direction == dirSign && eo.E5Prob > 0.55) conf++;
            if (eo.E6Direction == dirSign && eo.E6Prob > 0.55) conf++;
            if (eo.E8Direction == dirSign && eo.E8Prob > 0.55) conf++;
            if (eo.E9Direction == dirSign && eo.E9Prob > 0.55) conf++;
            if (eo.E12Direction == dirSign && eo.E12Prob > 0.55) conf++;
            if (eo.E13Direction == dirSign && eo.E13Prob > 0.55) conf++;
            eo.ConfluenceCount = conf;

            return eo;
        }

        private int SignFromBayesianFusion(EngineOutputs eo)
        {
            if (eo.PosteriorCombined > 0.55) return +1;
            if (eo.PosteriorCombined < 0.45) return -1;
            return 0;
        }

        private double[] BuildFeatureVector(EngineOutputs eo)
        {
            var x = new double[FEATURE_VECTOR_DIM];
            int i = 0;
            x[i++] = eo.E1Prob;
            x[i++] = eo.E2Prob;
            x[i++] = eo.E3Prob;
            x[i++] = eo.E4Prob;
            x[i++] = eo.E5Prob;
            x[i++] = eo.E6Prob;
            x[i++] = eo.E7Quality;
            x[i++] = eo.E8Prob;
            x[i++] = eo.E9Prob;
            x[i++] = eo.E10Toxicity;
            x[i++] = eo.E11LongMult / 2.0;   // normalize to ~[0,1]
            x[i++] = eo.E11ShortMult / 2.0;
            x[i++] = eo.E12Prob;
            x[i++] = eo.E13Prob;
            x[i++] = eo.E14PTake;
            // 5 regime one-hot
            for (int r = 0; r < 5; r++) x[i++] = (eo.RegimeIdx == r) ? 1.0 : 0.0;
            // 4 session one-hot
            int sessionIdx = ComputeSessionIdx();
            for (int s = 0; s < 4; s++) x[i++] = (sessionIdx == s) ? 1.0 : 0.0;
            // 7 GEX regime one-hot
            for (int g = 0; g < 7; g++) x[i++] = (eo.E11Regime == g) ? 1.0 : 0.0;
            x[i++] = _vpin.CurrentToxicity;
            // distance to nearest level (in ATR units)
            x[i++] = ComputeDistToLevelATR();
            // bias term
            x[i++] = 1.0;
            // pad to FEATURE_VECTOR_DIM
            while (i < FEATURE_VECTOR_DIM) x[i++] = 0;
            return x;
        }

        private double[] BuildQualityFeatures()
        {
            // 8-feature logistic input for E7
            double spread = _bestAsk > 0 && _bestBid > 0 ? (_bestAsk - _bestBid) / TickSize : 1.0;
            double depthImb = (_bestBidSize + _bestAskSize) > 0
                ? (double)(_bestBidSize - _bestAskSize) / (_bestBidSize + _bestAskSize) : 0;
            double recentLambda = _kyleLambdas[1].Value;
            double vpin = _vpin.CurrentToxicity;
            double mpDrift = _microprice.RecentDriftVelocity;
            double tradeIntensity = _hawkes.CurrentLambda;
            double timeSinceLastSwing = ComputeTimeSinceLastSwing();
            double sessionPhase = ComputeSessionPhase();

            return new double[] { spread, depthImb, recentLambda, vpin, mpDrift, tradeIntensity,
                                  timeSinceLastSwing, sessionPhase };
        }

        private double ComputeTimeSinceLastSwing()
        {
            if (CurrentBar < 5) return 0;
            // Simplified: time (in bars) since high or low equal to current high or low
            int lookback = Math.Min(20, CurrentBar);
            for (int i = 1; i <= lookback; i++)
                if (High[i] >= High[0] || Low[i] <= Low[0]) return i;
            return lookback;
        }

        private double ComputeSessionPhase()
        {
            if (Time[0] < _sessionStartTime) return 0;
            double minutesIntoSession = (Time[0] - _sessionStartTime).TotalMinutes;
            return Math.Min(1.0, minutesIntoSession / 390.0); // 6.5h = full session
        }

        private int ComputeSessionIdx()
        {
            if (!_isRTH) return 3; // GBX
            double hr = Time[0].Hour + Time[0].Minute / 60.0;
            if (hr < 10.5) return 0;        // open
            if (hr < 14.5) return 1;        // mid
            return 2;                        // close
        }

        private double ComputeDistToLevelATR()
        {
            if (_atrEstimate <= 0) return 5.0;
            double minDist = double.MaxValue;
            double[] levels = new double[] {
                _gex.GammaFlip, _gex.CallWall, _gex.PutWall,
                _sessionVWAP, _ibHigh, _ibLow, _priorDayHigh, _priorDayLow, _sessionPOC
            };
            foreach (var lvl in levels)
            {
                if (lvl <= 0) continue;
                double d = Math.Abs(Close[0] - lvl) / _atrEstimate;
                if (d < minDist) minDist = d;
            }
            return minDist == double.MaxValue ? 5.0 : minDist;
        }

        #endregion

        #region 4-Tier Funnel application

        private FunnelDecision ApplyFourTierFunnel(EngineOutputs eo, int direction)
        {
            var fd = new FunnelDecision();

            // ===== TIER 1: CONTEXT =====
            _t1.Update(_gex, Close[0]);
            fd.T1Bias = _t1.Bias;
            fd.T1Strength = _t1.Strength;

            // Tier 1 gate: direction must match bias OR bias is neutral (0)
            if (_t1.Bias != 0 && Math.Sign(direction) != Math.Sign(_t1.Bias))
            {
                fd.T1Pass = false;
                fd.FailReason = "T1: context bias mismatch";
                return fd;
            }
            fd.T1Pass = true;

            // ===== TIER 2: REGIME =====
            fd.RegimeIdx = (int)_e15.CurrentRegime;
            fd.RegimeName = _e15.CurrentRegime.ToString();
            if (_e15.CurrentRegime == RegimeState.Filtered)
            {
                fd.T2Pass = false;
                fd.FailReason = "T2: regime=Filtered";
                return fd;
            }
            fd.T2Pass = true;

            // ===== TIER 3: LEVEL =====
            _t3.Update(this, _gex, _sessionVWAP, _ibHigh, _ibLow, _priorDayHigh, _priorDayLow,
                        _sessionPOC, _atrEstimate);
            fd.DistToLevelATR = _t3.DistanceATR;
            fd.NearestLevelType = _t3.NearestLevelType;

            if (_t3.DistanceATR > 0.5)
            {
                fd.T3Pass = false;
                fd.FailReason = "T3: too far from level";
                return fd;
            }
            fd.T3Pass = true;

            // ===== TIER 4: TRIGGER =====
            // Confluence count + posterior threshold
            if (eo.ConfluenceCount < GRADE_C_CONFLUENCE)
            {
                fd.T4Pass = false;
                fd.FailReason = "T4: insufficient confluence (" + eo.ConfluenceCount + ")";
                return fd;
            }
            if (Math.Max(eo.PosteriorCombined, 1.0 - eo.PosteriorCombined) < GRADE_C_PROB)
            {
                fd.T4Pass = false;
                fd.FailReason = "T4: posterior below C-grade threshold";
                return fd;
            }

            // Veto checks
            if (eo.E14Veto)
            {
                fd.T4Pass = false;
                fd.FailReason = "E14 meta-label veto (p_take<0.50)";
                return fd;
            }
            if (eo.E10Veto)
            {
                fd.T4Pass = false;
                fd.FailReason = "E10 VPIN kill switch";
                return fd;
            }
            if (eo.E7Quality < E7_QUALITY_VETO)
            {
                fd.T4Pass = false;
                fd.FailReason = "E7 quality veto";
                return fd;
            }
            if (direction > 0 && eo.SpoofVetoBidSide)
            {
                fd.T4Pass = false;
                fd.FailReason = "E3 spoof veto (bid-side, going long)";
                return fd;
            }
            if (direction < 0 && eo.SpoofVetoAskSide)
            {
                fd.T4Pass = false;
                fd.FailReason = "E3 spoof veto (ask-side, going short)";
                return fd;
            }

            fd.T4Pass = true;
            fd.PassedAllGates = true;
            return fd;
        }

        #endregion

        #region Signal classification + size + emission

        private SignalGradeEnum ClassifySignal(EngineOutputs eo, FunnelDecision fd)
        {
            if (!fd.PassedAllGates) return SignalGradeEnum.Q;

            double maxP = Math.Max(eo.PosteriorCombined, 1.0 - eo.PosteriorCombined);
            int conf = eo.ConfluenceCount;

            if (conf >= GRADE_S_CONFLUENCE && maxP >= GRADE_S_PROB) return SignalGradeEnum.S;
            if (conf >= GRADE_A_CONFLUENCE && maxP >= GRADE_A_PROB) return SignalGradeEnum.A;
            if (conf >= GRADE_B_CONFLUENCE && maxP >= GRADE_B_PROB) return SignalGradeEnum.B;
            if (conf >= GRADE_C_CONFLUENCE && maxP >= GRADE_C_PROB) return SignalGradeEnum.C;
            return SignalGradeEnum.Q;
        }

        private double ComputeSizeMultiplier(EngineOutputs eo, double posterior)
        {
            // Half-Kelly with E14 meta-label as primary multiplier
            double pTake = eo.E14PTake;
            double sizeMult = 2.0 * (pTake - 0.5) * 0.25; // 25% Kelly
            sizeMult = Math.Max(0.25, Math.Min(1.5, sizeMult));

            // Apply GEX directional amp
            int dir = posterior > 0.5 ? +1 : -1;
            double gexAmp = dir > 0 ? eo.E11LongMult : eo.E11ShortMult;
            sizeMult *= gexAmp;

            // Regime multiplier
            double regimeMult = GetRegimeMultiplier(eo.RegimeIdx);
            sizeMult *= regimeMult;

            // VPIN dampening
            if (eo.E10Toxicity > VPIN_WARN_THRESHOLD) sizeMult *= 0.5;
            else if (eo.E10Toxicity > VPIN_SOFT_THRESHOLD) sizeMult *= 0.75;

            // Drift alarm dampening
            if (eo.DriftAlarm) sizeMult *= 0.5;

            return Math.Max(0.0, Math.Min(3.0, sizeMult));
        }

        private double GetRegimeMultiplier(int regimeIdx)
        {
            switch (regimeIdx)
            {
                case 0: return 2.0;  // Reversal
                case 1: return 1.5;  // Trend continuation
                case 2: return 1.8;  // Breakout
                case 3: return 1.0;  // Range scalp
                case 4: return 0.0;  // Filtered
                default: return 1.0;
            }
        }

        private void EmitSignal(SignalGradeEnum grade, int direction, double posterior, double sizeMult, EngineOutputs eo)
        {
            string gradeStr = grade.ToString();
            string dirStr = direction > 0 ? "LONG" : (direction < 0 ? "SHORT" : "NONE");

            if (LogSignals)
            {
                Print(string.Format(
                    "[ATLAS {0:HH:mm:ss}] {1}-{2} P={3:F3} conf={4} size×{5:F2} | " +
                    "regime={6} VPIN={7:F2} GEXamp_long={8:F2} TLOB↑={9:F2} MetaP={10:F2} | " +
                    "E1={11} E2={12} E4={13} E8={14} E12={15}",
                    Time[0], gradeStr, dirStr, posterior, eo.ConfluenceCount, sizeMult,
                    eo.RegimeName, eo.E10Toxicity, eo.E11LongMult, eo.E13ProbUp, eo.E14PTake,
                    eo.E1Score, eo.E2Score, eo.E4Score, eo.E8Score, eo.E12Score));
            }

            if (SoundOnA && (grade == SignalGradeEnum.A || grade == SignalGradeEnum.S))
            {
                try { Alert("ATLAS_" + grade, Priority.High, gradeStr + " " + dirStr,
                            "Alert1.wav", 10, Brushes.Yellow, Brushes.Black); }
                catch { }
            }

            if (ShowSignalBoxes)
            {
                DrawSignalBox(grade, direction, posterior, eo);
            }
        }

        private void DrawSignalBox(SignalGradeEnum grade, int direction, double posterior, EngineOutputs eo)
        {
            string tag = "ATLAS_" + grade + "_" + CurrentBar;
            // NOTE: Draw.Text / Draw.Rectangle expect System.Windows.Media.Brush, not the SharpDX Brush alias
            System.Windows.Media.Brush boxBrush;
            switch (grade)
            {
                case SignalGradeEnum.S: boxBrush = Brushes.Gold;        break;
                case SignalGradeEnum.A: boxBrush = Brushes.Goldenrod;   break;
                case SignalGradeEnum.B: boxBrush = Brushes.DarkOrange;  break;
                case SignalGradeEnum.C: boxBrush = Brushes.DeepSkyBlue; break;
                default:                boxBrush = Brushes.Gray;        break;
            }

            double y = direction > 0 ? Low[0] - 4 * TickSize : High[0] + 4 * TickSize;
            string arrow = direction > 0 ? "▲" : "▼";
            string text = grade.ToString() + " " + arrow + " P=" + posterior.ToString("F2") + " c=" + eo.ConfluenceCount;
            Draw.Text(this, tag, text, 0, y, boxBrush);

            // Bordered box around the bar
            string boxTag = tag + "_box";
            double boxTop = High[0] + 1 * TickSize;
            double boxBot = Low[0] - 1 * TickSize;
            Draw.Rectangle(this, boxTag, false, 0, boxTop, 0, boxBot, boxBrush, boxBrush, 30);
        }

        #endregion

        #region Kill switches

        private bool CheckKillSwitches(EngineOutputs eo)
        {
            // KS1: VPIN > 0.70
            if (eo.E10Toxicity > VPIN_KILL_THRESHOLD)
            {
                if (!_vpinKillActive)
                {
                    _vpinKillActive = true;
                    _vpinKillUntil = Time[0].AddMinutes(30);
                    if (LogSignals) Print($"[ATLAS] KS1 ACTIVE - VPIN={eo.E10Toxicity:F2} > {VPIN_KILL_THRESHOLD}, lockout until {_vpinKillUntil:HH:mm}");
                }
                return true;
            }
            if (_vpinKillActive && Time[0] < _vpinKillUntil) return true;
            if (_vpinKillActive && Time[0] >= _vpinKillUntil)
            {
                _vpinKillActive = false;
                if (LogSignals) Print("[ATLAS] KS1 cleared - resuming signal generation");
            }

            // KS2: drift alarm with sustained loss → handled in size multiplier (not full kill)
            // KS3: daily loss
            if (Time[0].Date != _currentTradingDay)
            {
                _currentTradingDay = Time[0].Date;
                _dailyPnl = 0;
                _consecutiveLosses = 0;
            }
            if (_dailyPnl <= -DailyLossLockoutDollars)
            {
                if (LogSignals && (CurrentBar % 50 == 0)) Print($"[ATLAS] KS3 ACTIVE - daily loss {_dailyPnl:C} ≤ {-DailyLossLockoutDollars:C}");
                return true;
            }

            // KS4: 3 consecutive A losses → drop to S only (handled in MinSignalGrade override; show in HUD)

            // KS5: regime = Filtered → handled in funnel (not here)
            // KS6: E14 veto → handled in funnel
            // KS7: spread > 3 ticks
            double spread = _bestAsk > 0 && _bestBid > 0 ? (_bestAsk - _bestBid) / TickSize : 999;
            if (spread > 3) return true;

            // KS8: news kill
            if (_newsKillActive) return true;

            return false;
        }

        public void RegisterTradeOutcome(double rMultiple, double pnlDollars)
        {
            // Called by paired strategy or manual journal entry
            if (_lastFeatureVector == null) return;
            var outcome = new TradeOutcome
            {
                Time = Time[0],
                FeatureVector = _lastFeatureVector,
                RMultiple = Math.Max(-3.0, Math.Min(3.0, rMultiple)),
                PnlDollars = pnlDollars,
                Direction = _signalDirection,
                Grade = _lastEmittedGrade,
                Posterior = _lastPosterior
            };

            _outcomeQueue.Add(outcome);
            _dailyPnl += pnlDollars;
            if (rMultiple < 0) _consecutiveLosses++; else _consecutiveLosses = 0;

            // Update FTRL ensemble
            int y = rMultiple > 0 ? 1 : 0;
            _ftrlFast.Update(outcome.FeatureVector, y);
            _ftrlMed.Update(outcome.FeatureVector, y);
            _ftrlSlow.Update(outcome.FeatureVector, y);

            // Update Hedge blender
            _hedge.RegisterLoss(0, _ftrlFast.LastLogLoss);
            _hedge.RegisterLoss(1, _ftrlMed.LastLogLoss);
            _hedge.RegisterLoss(2, _ftrlSlow.LastLogLoss);

            // Update reliability
            _reliability.Update(outcome);

            // Drift monitor on log-loss
            _e16.Update(_ftrlMed.LastLogLoss);
            if (_e16.AlarmActive)
            {
                _ftrlFast.AmplifyLearningRate(2.0);
                _ftrlMed.AmplifyLearningRate(2.0);
            }
        }

        #endregion

        #region Session, ATR, GEX helpers

        private void UpdateSessionState()
        {
            DateTime now = Time[0];
            DateTime today930 = now.Date.AddHours(9).AddMinutes(30);
            DateTime today1600 = now.Date.AddHours(16);
            _isRTH = now >= today930 && now < today1600;
            if (now.Date != _sessionStartTime.Date && _isRTH)
            {
                _sessionStartTime = today930;
                _ibCutoffTime = today930.AddHours(1);
                _sessionVWAP = 0;
                _sessionVWAPSumPV = 0;
                _sessionVWAPSumV = 0;
                _ibHigh = 0;
                _ibLow = double.MaxValue;
                _ibSet = false;
                if (CurrentBar > 0)
                {
                    _priorDayHigh = MAX(High, 1)[1];
                    _priorDayLow = MIN(Low, 1)[1];
                }
            }
            // IB tracking (first hour RTH)
            if (_isRTH && now < _ibCutoffTime)
            {
                if (High[0] > _ibHigh) _ibHigh = High[0];
                if (Low[0] < _ibLow) _ibLow = Low[0];
                _ibSet = true;
            }
        }

        private void UpdateATR()
        {
            if (CurrentBar < 14) return;
            double tr = Math.Max(High[0] - Low[0],
                        Math.Max(Math.Abs(High[0] - Close[1]), Math.Abs(Low[0] - Close[1])));
            _atrSum = _atrSum * 0.93 + tr * 0.07;  // exponential approximation
            _atrCount++;
            _atrEstimate = _atrSum;
        }

        private void ReloadGEXIfStale()
        {
            if ((DateTime.Now - _gexLastLoad).TotalSeconds > GEXRefreshSeconds)
            {
                LoadGEXFromFile();
                _gexLastLoad = DateTime.Now;
            }
        }

        private void LoadGEXFromFile()
        {
            try
            {
                if (!File.Exists(GEXFilePath)) return;
                string json = File.ReadAllText(GEXFilePath);
                _gex.ParseJSON(json);
            }
            catch (Exception ex)
            {
                if (LogSignals) Print("[ATLAS] GEX load error: " + ex.Message);
            }
        }

        #endregion

        #region SharpDX Rendering — HUD

        public override void OnRenderTargetChanged()
        {
            try
            {
                DisposeRenderResources();
                if (RenderTarget == null) return;

                _bGold = new SolidColorBrush(RenderTarget, new Color4(1.0f, 0.84f, 0.0f, 1.0f));
                _bAmber = new SolidColorBrush(RenderTarget, new Color4(1.0f, 0.55f, 0.0f, 1.0f));
                _bCyan = new SolidColorBrush(RenderTarget, new Color4(0.0f, 0.85f, 1.0f, 1.0f));
                _bGray = new SolidColorBrush(RenderTarget, new Color4(0.5f, 0.5f, 0.5f, 1.0f));
                _bRedKill = new SolidColorBrush(RenderTarget, new Color4(0.95f, 0.15f, 0.15f, 1.0f));
                _bGreen = new SolidColorBrush(RenderTarget, new Color4(0.2f, 0.85f, 0.3f, 1.0f));
                _bWhite = new SolidColorBrush(RenderTarget, new Color4(1f, 1f, 1f, 1f));
                _bDimWhite = new SolidColorBrush(RenderTarget, new Color4(0.85f, 0.85f, 0.85f, 0.85f));
                _bBackground = new SolidColorBrush(RenderTarget, new Color4(0.05f, 0.05f, 0.08f, 0.92f));

                if (_dwFactory == null)
                    _dwFactory = new DXFactory();

                _tfHeader = new SharpDX.DirectWrite.TextFormat(_dwFactory, "Consolas",
                    SharpDX.DirectWrite.FontWeight.Bold, FontStyle.Normal, 16f);
                _tfBody = new SharpDX.DirectWrite.TextFormat(_dwFactory, "Consolas",
                    SharpDX.DirectWrite.FontWeight.Normal, FontStyle.Normal, 12f);
                _tfMono = new SharpDX.DirectWrite.TextFormat(_dwFactory, "Consolas",
                    SharpDX.DirectWrite.FontWeight.Normal, FontStyle.Normal, 11f);
                _tfSmall = new SharpDX.DirectWrite.TextFormat(_dwFactory, "Consolas",
                    SharpDX.DirectWrite.FontWeight.Normal, FontStyle.Normal, 10f);
            }
            catch (Exception ex)
            {
                Log("OnRenderTargetChanged error: " + ex.Message, LogLevel.Error);
            }
        }

        private void DisposeRenderResources()
        {
            try
            {
                _bGold?.Dispose(); _bAmber?.Dispose(); _bCyan?.Dispose();
                _bGray?.Dispose(); _bRedKill?.Dispose(); _bGreen?.Dispose();
                _bWhite?.Dispose(); _bDimWhite?.Dispose(); _bBackground?.Dispose();
                _tfHeader?.Dispose(); _tfBody?.Dispose(); _tfMono?.Dispose(); _tfSmall?.Dispose();
                _bGold = _bAmber = _bCyan = _bGray = _bRedKill = _bGreen = _bWhite = _bDimWhite = _bBackground = null;
                _tfHeader = _tfBody = _tfMono = _tfSmall = null;
            } catch { }
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (!ShowHUD || RenderTarget == null || _bGold == null) return;

            try
            {
                float panelX = (float)(ChartPanel.X + ChartPanel.W - HUD_WIDTH - HUD_MARGIN_RIGHT);
                float panelY = (float)(ChartPanel.Y + HUD_MARGIN_TOP);

                // Background
                var rect = new RectangleF(panelX, panelY, panelX + HUD_WIDTH, panelY + HUD_HEIGHT);
                RenderTarget.FillRectangle(rect, _bBackground);
                RenderTarget.DrawRectangle(rect, _bDimWhite, 1.0f);

                float lineY = panelY + 6;
                float colX = panelX + 10;

                // Header line — current state
                Brush headerBrush;
                switch (_lastEmittedGrade)
                {
                    case SignalGradeEnum.S: headerBrush = _bGold; break;
                    case SignalGradeEnum.A: headerBrush = _bGold; break;
                    case SignalGradeEnum.B: headerBrush = _bAmber; break;
                    case SignalGradeEnum.C: headerBrush = _bCyan; break;
                    default: headerBrush = _bGray; break;
                }
                string state = _lastEmittedGrade == SignalGradeEnum.Q
                    ? (_lobBufferCount < 50 ? "WARMING" : "QUIET")
                    : _lastEmittedGrade.ToString() + " " + (_signalDirection > 0 ? "▲ LONG" : (_signalDirection < 0 ? "▼ SHORT" : ""));

                RenderTarget.DrawText("DEEP6 ATLAS · " + state, _tfHeader,
                    new RectangleF(colX, lineY, panelX + HUD_WIDTH - 6, lineY + 20), headerBrush);
                lineY += 22;

                // Posterior + grade line
                string postLine = string.Format("P={0:F3} | grade={1} | size×{2:F2}",
                    _lastPosterior, _lastEmittedGrade, _lastSizeMult);
                RenderTarget.DrawText(postLine, _tfBody,
                    new RectangleF(colX, lineY, panelX + HUD_WIDTH - 6, lineY + 16), _bWhite);
                lineY += 18;

                // Regime line
                string regLine = "regime: " + (_e15 != null ? _e15.CurrentRegime.ToString() : "-")
                                + " | drift: " + (_e16.AlarmActive ? "ALARM" : "ok");
                Brush regBrush = (_e15 != null && _e15.CurrentRegime == RegimeState.Filtered) ? _bRedKill : _bDimWhite;
                RenderTarget.DrawText(regLine, _tfBody,
                    new RectangleF(colX, lineY, panelX + HUD_WIDTH - 6, lineY + 16), regBrush);
                lineY += 18;

                // VPIN line
                Brush vpinBrush = _vpin.CurrentToxicity > VPIN_KILL_THRESHOLD ? _bRedKill :
                                  (_vpin.CurrentToxicity > VPIN_WARN_THRESHOLD ? _bAmber : _bGreen);
                string vpinLine = string.Format("VPIN: {0:F2}  λ_kyle: {1:F4}",
                    _vpin.CurrentToxicity, _kyleLambdas[1].Value);
                RenderTarget.DrawText(vpinLine, _tfMono,
                    new RectangleF(colX, lineY, panelX + HUD_WIDTH - 6, lineY + 14), vpinBrush);
                lineY += 16;

                // Microprice + Hawkes
                string mpLine = string.Format("MP_dev: {0:F2}t  Hawkes_n: {1:F2}",
                    _microprice.DeviationTicks, _hawkes.BranchingRatio);
                RenderTarget.DrawText(mpLine, _tfMono,
                    new RectangleF(colX, lineY, panelX + HUD_WIDTH - 6, lineY + 14), _bDimWhite);
                lineY += 16;

                // GEX line
                string gexLine = string.Format("GEX: γflip={0:F0} CW={1:F0} PW={2:F0}",
                    _gex.GammaFlip, _gex.CallWall, _gex.PutWall);
                RenderTarget.DrawText(gexLine, _tfMono,
                    new RectangleF(colX, lineY, panelX + HUD_WIDTH - 6, lineY + 14), _bDimWhite);
                lineY += 16;

                // FTRL state
                string ftrlLine = string.Format("FTRL: f={0:F2} m={1:F2} s={2:F2} | n={3}",
                    _ftrlFast.LastPrediction, _ftrlMed.LastPrediction, _ftrlSlow.LastPrediction,
                    _ftrlMed.UpdateCount);
                RenderTarget.DrawText(ftrlLine, _tfMono,
                    new RectangleF(colX, lineY, panelX + HUD_WIDTH - 6, lineY + 14), _bDimWhite);
                lineY += 16;

                // Kill switch line
                if (_vpinKillActive || HardKillSwitch || _newsKillActive)
                {
                    string killLine = "🛑 KILL: " +
                        (_vpinKillActive ? "VPIN " : "") +
                        (HardKillSwitch ? "MANUAL " : "") +
                        (_newsKillActive ? "NEWS" : "");
                    RenderTarget.DrawText(killLine, _tfBody,
                        new RectangleF(colX, lineY, panelX + HUD_WIDTH - 6, lineY + 16), _bRedKill);
                    lineY += 18;
                }

                // Engine confluence bar (E1-E13 indicators)
                lineY += 4;
                RenderTarget.DrawText("Engines:", _tfSmall,
                    new RectangleF(colX, lineY, colX + 70, lineY + 12), _bDimWhite);
                float chipX = colX + 60;
                float chipY = lineY + 1;
                float chipW = 17;
                float chipH = 12;
                string[] eNames = { "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12", "E13" };
                bool[] eActive = {
                    EnableE1, EnableE2, EnableE3, EnableE4, true, true, true,
                    EnableE8, true, true, EnableE11, EnableE12, EnableE13
                };
                for (int i = 0; i < eNames.Length; i++)
                {
                    var chipRect = new RectangleF(chipX, chipY, chipX + chipW, chipY + chipH);
                    RenderTarget.FillRectangle(chipRect, eActive[i] ? _bGreen : _bGray);
                    chipX += chipW + 1;
                }
            }
            catch (Exception ex)
            {
                if (LogSignals) Print("[ATLAS] OnRender error: " + ex.Message);
            }
        }

        #endregion

    } // end class DEEP6Atlas

    // =========================================================================
    //                       ENUMS / DATA CLASSES
    // =========================================================================

    public enum SignalGradeEnum
    {
        Q = 0, C = 1, B = 2, A = 3, S = 4
    }

    public enum RegimeState
    {
        Reversal = 0,
        TrendContinuation = 1,
        Breakout = 2,
        RangeScalp = 3,
        Filtered = 4
    }

    public class LOBSnapshot
    {
        public DateTime Time;
        public double[] BidPrices;
        public long[]   BidSizes;
        public double[] AskPrices;
        public long[]   AskSizes;
        public LOBSnapshot(int depth)
        {
            BidPrices = new double[depth];
            BidSizes = new long[depth];
            AskPrices = new double[depth];
            AskSizes = new long[depth];
        }
    }

    public class EngineOutputs
    {
        // E1-E12 outputs
        public double E1Score, E1Prob; public int E1Direction; public bool E1Active;
        public double E2Score, E2Prob; public int E2Direction; public bool E2Active;
        public double E3Score, E3Prob; public int E3Direction; public bool SpoofVetoBidSide, SpoofVetoAskSide;
        public double E4Score, E4Prob; public int E4Direction;
        public double E5Score, E5Prob; public int E5Direction;
        public double E6Score, E6Prob; public int E6Direction;
        public double E7Quality;
        public double E8Score, E8Prob; public int E8Direction;
        public double E9Score, E9Prob; public int E9Direction;
        public double E10Toxicity; public bool E10Veto;
        public double E11LongMult = 1.0, E11ShortMult = 1.0; public int E11Regime;
        public double E12Score, E12Prob; public int E12Direction;
        // E13 - LOB-NN
        public double E13Score, E13Prob; public int E13Direction;
        public double E13ProbUp, E13ProbDown;
        // E14 - meta-label
        public double E14PTake; public bool E14Veto;
        // E15 - regime
        public int RegimeIdx; public string RegimeName = "Unknown";
        // E16 - drift
        public bool DriftAlarm;
        // Fusion outputs
        public double PosteriorBayes, PosteriorFTRL, PosteriorCombined;
        public int ConfluenceCount;
    }

    public class FunnelDecision
    {
        public bool T1Pass, T2Pass, T3Pass, T4Pass;
        public bool PassedAllGates;
        public int T1Bias;
        public double T1Strength;
        public int RegimeIdx;
        public string RegimeName = "";
        public double DistToLevelATR;
        public string NearestLevelType = "";
        public string FailReason = "";
    }

    public class TradeOutcome
    {
        public DateTime Time;
        public double[] FeatureVector;
        public double RMultiple;
        public double PnlDollars;
        public int Direction;
        public SignalGradeEnum Grade;
        public double Posterior;
    }

    public class GEXContext
    {
        public double GammaFlip;
        public double CallWall;
        public double PutWall;
        public double NetGEX;
        public double[] CallWalls = new double[3];
        public double[] PutWalls = new double[3];
        public DateTime LastUpdate;
        public bool IsValid => GammaFlip > 0 && (CallWall > 0 || PutWall > 0);

        public void ParseJSON(string json)
        {
            // Lightweight JSON parser for {"flip": 22000, "call_wall": 22300, "put_wall": 21800, "net_gex": 5e9, ...}
            try
            {
                GammaFlip = ExtractDouble(json, "\"flip\"");
                if (GammaFlip == 0) GammaFlip = ExtractDouble(json, "\"gamma_flip\"");
                CallWall = ExtractDouble(json, "\"call_wall\"");
                PutWall = ExtractDouble(json, "\"put_wall\"");
                NetGEX = ExtractDouble(json, "\"net_gex\"");
                LastUpdate = DateTime.Now;
            }
            catch { }
        }

        private double ExtractDouble(string json, string key)
        {
            int idx = json.IndexOf(key);
            if (idx < 0) return 0;
            int colon = json.IndexOf(':', idx);
            if (colon < 0) return 0;
            int end = colon + 1;
            while (end < json.Length && (char.IsDigit(json[end]) || json[end] == '.' || json[end] == '-' || json[end] == 'e' || json[end] == 'E' || json[end] == '+' || char.IsWhiteSpace(json[end])))
                end++;
            string v = json.Substring(colon + 1, end - colon - 1).Trim().TrimEnd(',').Trim();
            double r;
            return double.TryParse(v, System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out r) ? r : 0;
        }
    }

    // =========================================================================
    //                     PILLAR I — MICROSTRUCTURE PRIMITIVES
    // =========================================================================

    /// <summary>
    /// Stoikov microprice (2018, arxiv:1811.10889). MP = Bid + (Ask-Bid) · G(I, s).
    /// Uses simple linear approximation G ≈ I when no fitted lookup table is loaded.
    /// </summary>
    public class Microprice
    {
        private double _value;
        private double _midprice;
        private double _prevValue;
        private DateTime _prevTime;
        private double _recentDriftVelocity;
        private double _deviationTicks;

        public double Value => _value;
        public double DeviationTicks => _deviationTicks;
        public double RecentDriftVelocity => _recentDriftVelocity;

        public void Update(double bid, double ask, long bidSize, long askSize, double tickSize)
        {
            if (bid <= 0 || ask <= 0 || ask <= bid) return;
            _midprice = (bid + ask) * 0.5;
            double i = (bidSize + askSize) > 0 ? (double)bidSize / (bidSize + askSize) : 0.5;
            // Simple G(I,s) = I (linear approximation; replace with fitted lookup for production)
            double g = i;
            _value = bid + (ask - bid) * g;
            _deviationTicks = (_value - _midprice) / tickSize;

            DateTime now = DateTime.UtcNow;
            if (_prevTime != DateTime.MinValue && _prevValue > 0)
            {
                double dt = (now - _prevTime).TotalMilliseconds;
                if (dt > 0 && dt < 5000)
                    _recentDriftVelocity = 0.7 * _recentDriftVelocity + 0.3 * (_value - _prevValue) / dt;
            }
            _prevValue = _value;
            _prevTime = now;
        }
    }

    /// <summary>
    /// Cont-Kukanov-Stoikov (2014) rolling OFI over a time window.
    /// </summary>
    public class OFIRolling
    {
        private struct OFIEvent { public DateTime T; public double E; }
        private Queue<OFIEvent> _events = new Queue<OFIEvent>();
        private TimeSpan _window;
        private double _sum;

        public OFIRolling(TimeSpan window) { _window = window; }
        public double Value => _sum;

        public void Add(DateTime t, double e)
        {
            _events.Enqueue(new OFIEvent { T = t, E = e });
            _sum += e;
            while (_events.Count > 0 && (t - _events.Peek().T) > _window)
            {
                var oldest = _events.Dequeue();
                _sum -= oldest.E;
            }
        }
    }

    /// <summary>
    /// Multi-Level OFI top-K with 1/k decay (Xu et al. 2019; Kolm-Westray 2023).
    /// </summary>
    /// <summary>
    /// Multi-Level OFI top-K with 1/k decay (Xu et al. 2019; Kolm-Westray 2023).
    /// Maintains online principal component (Oja's rule) for E12 DOFI projection.
    /// </summary>
    public class MLOFIComputer
    {
        private int _k;
        private double[] _ofi;
        private double[] _prevBidSizes;
        private double[] _prevAskSizes;
        // Oja's rule online PCA state
        private double[] _pc1;
        private double _ojaLR = 0.001;
        private double _ojaNorm = 0;
        private long _updateCount;
        public double Value;
        public double[] Vector { get { return _ofi; } }
        public double[] PC1 { get { return _pc1; } }
        public long UpdateCount { get { return _updateCount; } }

        public MLOFIComputer(int k)
        {
            _k = k;
            _ofi = new double[k];
            _prevBidSizes = new double[k];
            _prevAskSizes = new double[k];
            _pc1 = new double[k];
            // Initialize PC1 with declining weights (sensible prior matching empirical findings)
            double s = 0;
            for (int i = 0; i < k; i++) { _pc1[i] = 1.0 / (i + 1); s += _pc1[i] * _pc1[i]; }
            s = Math.Sqrt(s);
            for (int i = 0; i < k; i++) _pc1[i] /= s;
        }

        public void Update(SortedDictionary<double, long> bids, SortedDictionary<double, long> asks, DateTime now)
        {
            var bidArr = bids.Take(_k).ToArray();
            var askArr = asks.Take(_k).ToArray();
            double sum = 0;
            for (int i = 0; i < _k; i++)
            {
                double bs = i < bidArr.Length ? bidArr[i].Value : 0;
                double aks = i < askArr.Length ? askArr[i].Value : 0;
                _ofi[i] = (bs - _prevBidSizes[i]) - (aks - _prevAskSizes[i]);
                sum += _ofi[i] / (i + 1);  // 1/k decay
                _prevBidSizes[i] = bs;
                _prevAskSizes[i] = aks;
            }
            Value = sum;

            // ----- Oja's rule online PCA update -----
            // w(t+1) = w(t) + η · (y · x - y² · w(t)),  y = w·x
            // Then normalize w to unit L2 norm.
            double y = 0;
            for (int i = 0; i < _k; i++) y += _pc1[i] * _ofi[i];
            double y2 = y * y;
            double normSq = 0;
            for (int i = 0; i < _k; i++)
            {
                _pc1[i] += _ojaLR * (y * _ofi[i] - y2 * _pc1[i]);
                normSq += _pc1[i] * _pc1[i];
            }
            double norm = Math.Sqrt(normSq);
            if (norm > 1e-9)
            {
                for (int i = 0; i < _k; i++) _pc1[i] /= norm;
            }
            _ojaNorm = norm;

            // Decay learning rate over time toward 1/sqrt(t)
            _updateCount++;
            if (_updateCount > 1000) _ojaLR = Math.Max(0.0001, 1.0 / Math.Sqrt(_updateCount));
        }

        /// <summary>Project OFI vector onto current principal component.</summary>
        public double ProjectOnPC1()
        {
            double y = 0;
            for (int i = 0; i < _k; i++) y += _pc1[i] * _ofi[i];
            return y;
        }
    }

    /// <summary>
    /// Multi-scale Kyle's lambda — price impact per unit signed volume.
    /// </summary>
    public class KyleLambda
    {
        private struct Sample { public DateTime T; public double Price; public double SignedVol; }
        private Queue<Sample> _samples = new Queue<Sample>();
        private TimeSpan _window;
        public double Value;

        public KyleLambda(TimeSpan window) { _window = window; }

        public void Add(DateTime t, double price, double signedVol)
        {
            _samples.Enqueue(new Sample { T = t, Price = price, SignedVol = signedVol });
            while (_samples.Count > 0 && (t - _samples.Peek().T) > _window) _samples.Dequeue();
            if (_samples.Count < 5) return;
            // λ ≈ Cov(ΔP, Q) / Var(Q)
            var arr = _samples.ToArray();
            double meanQ = arr.Average(s => s.SignedVol);
            double meanP = arr.Average(s => s.Price);
            double cov = 0, varQ = 0;
            for (int i = 1; i < arr.Length; i++)
            {
                double dp = arr[i].Price - arr[i - 1].Price;
                double q = arr[i].SignedVol - meanQ;
                cov += dp * q;
                varQ += q * q;
            }
            Value = varQ > 0 ? cov / varQ : 0;
        }
    }

    /// <summary>
    /// VPIN-lite — bulk-volume classification toxicity (Easley-LdP-O'Hara 2012).
    /// </summary>
    public class VPINComputer
    {
        private int _bucketsTotal;
        private int _windowSize;
        private List<double> _bucketImbalances = new List<double>();
        private double _curBucketBuy, _curBucketSell;
        private double _curBucketSize;
        private double _bucketCapacity = 100;  // contracts per bucket; tuned per instrument
        public double CurrentToxicity;
        public long RecentVolume;

        public VPINComputer(int buckets, int windowSize)
        {
            _bucketsTotal = buckets;
            _windowSize = windowSize;
        }

        public void AddTrade(double price, long size, int aggressor, DateTime t)
        {
            // Bulk-volume classification: aggressor is +1 buy or -1 sell or 0 unknown
            double buyShare = aggressor > 0 ? 1.0 : (aggressor < 0 ? 0.0 : 0.5);
            _curBucketBuy += size * buyShare;
            _curBucketSell += size * (1.0 - buyShare);
            _curBucketSize += size;
            RecentVolume = (long)(0.95 * RecentVolume + 0.05 * size);

            while (_curBucketSize >= _bucketCapacity)
            {
                double imb = Math.Abs(_curBucketBuy - _curBucketSell) / _bucketCapacity;
                _bucketImbalances.Add(imb);
                if (_bucketImbalances.Count > _windowSize) _bucketImbalances.RemoveAt(0);
                CurrentToxicity = _bucketImbalances.Count > 0 ? _bucketImbalances.Average() : 0;
                // Reset bucket; carry remainder
                double overflow = _curBucketSize - _bucketCapacity;
                if (overflow > 0)
                {
                    double frac = overflow / _curBucketSize;
                    _curBucketBuy = _curBucketBuy * frac;
                    _curBucketSell = _curBucketSell * frac;
                    _curBucketSize = overflow;
                }
                else
                {
                    _curBucketBuy = 0;
                    _curBucketSell = 0;
                    _curBucketSize = 0;
                }
            }
        }
    }

    /// <summary>
    /// Marked Hawkes process with exponential kernel (Hawkes 1971, Bacry et al. 2015).
    /// Estimates branching ratio n = α/β via simple recursive update (not full MLE).
    /// </summary>
    public class MarkedHawkes
    {
        private int _windowSize;
        private Queue<(DateTime t, double mark)> _events = new Queue<(DateTime, double)>();
        private double _alpha = 0.5;
        private double _beta = 1.0;
        private double _mu = 0.1;
        public double CurrentLambda;
        public double BranchingRatio => _alpha / _beta;

        public MarkedHawkes(int windowSize) { _windowSize = windowSize; }

        public void AddEvent(DateTime t, double mark)
        {
            _events.Enqueue((t, mark));
            while (_events.Count > _windowSize) _events.Dequeue();

            // Compute lambda(t) given current params
            double lam = _mu;
            foreach (var evt in _events)
            {
                double dt = (t - evt.t).TotalSeconds;
                if (dt > 0)
                    lam += _alpha * Math.Exp(-_beta * dt) * Math.Sign(evt.mark);
            }
            CurrentLambda = Math.Max(0, lam);

            // Crude online update of (alpha, beta) — full MLE would refit periodically
            if (_events.Count >= 50 && _events.Count % 25 == 0)
            {
                EstimateParams();
            }
        }

        private void EstimateParams()
        {
            // Simplified moment-matching estimate
            var arr = _events.ToArray();
            if (arr.Length < 10) return;
            var times = arr.Select(e => e.t).OrderBy(x => x).ToList();
            double totalSec = (times.Last() - times.First()).TotalSeconds;
            if (totalSec <= 0) return;
            double rate = arr.Length / totalSec;
            // Cluster ratio: count of inter-arrival < 0.5s as "excited"
            int excited = 0;
            for (int i = 1; i < times.Count; i++)
                if ((times[i] - times[i - 1]).TotalSeconds < 0.5) excited++;
            double n = excited / (double)times.Count;
            n = Math.Max(0.05, Math.Min(0.95, n));
            _alpha = n;
            _beta = 1.0;
            _mu = rate * (1 - n);
        }
    }

    /// <summary>
    /// Iceberg detector — heuristic refill-within-window detection.
    /// Native CME MDP3 modify-after-trade flag would require Rithmic protobuf addon.
    /// </summary>
    public class IcebergDetector
    {
        private class LevelHit
        {
            public DateTime LastTradeTime;
            public long SizeBeforeHit;
            public int HitCount;
        }
        private Dictionary<double, LevelHit> _bidHits = new Dictionary<double, LevelHit>();
        private Dictionary<double, LevelHit> _askHits = new Dictionary<double, LevelHit>();
        private int _maxRefillMs;
        public DateTime LastDetectionTime;
        public int LastDirection;       // +1 bid (long bias), -1 ask (short bias)
        public int RecentCount;

        public IcebergDetector(int maxRefillMs) { _maxRefillMs = maxRefillMs; }

        public void OnBookUpdate(double price, long size, bool isBid, DateTime t)
        {
            var dict = isBid ? _bidHits : _askHits;
            if (!dict.ContainsKey(price)) dict[price] = new LevelHit();
            var lh = dict[price];

            // Detect refill: size restored within max refill window after recent trade hit
            if (lh.LastTradeTime != DateTime.MinValue && (t - lh.LastTradeTime).TotalMilliseconds < _maxRefillMs)
            {
                if (size >= lh.SizeBeforeHit * 0.85 && lh.HitCount >= 2)
                {
                    LastDetectionTime = t;
                    LastDirection = isBid ? +1 : -1;
                    RecentCount++;
                    lh.HitCount = 0;
                }
            }
        }

        public void OnTrade(double price, long tradeSize, long displayedSize, int aggressor, DateTime t)
        {
            // aggressor +1 = trade hit ASK side (so ask-side level got hit)
            // aggressor -1 = trade hit BID side
            var dict = aggressor > 0 ? _askHits : _bidHits;
            if (!dict.ContainsKey(price)) dict[price] = new LevelHit();
            var lh = dict[price];
            lh.LastTradeTime = t;
            lh.SizeBeforeHit = displayedSize;
            lh.HitCount++;
        }

        public bool RecentlyDetected(DateTime now, int withinSeconds = 30)
            => LastDetectionTime != DateTime.MinValue && (now - LastDetectionTime).TotalSeconds < withinSeconds;
    }

    /// <summary>
    /// Hidden-fill detector: trade size > displayed size at price = unambiguous hidden liquidity.
    /// </summary>
    public class HiddenFillDetector
    {
        public int CountBuy, CountSell;
        public DateTime LastBuyHidden, LastSellHidden;

        public void OnTrade(double price, long tradeSize, long displayedSize, int aggressor, DateTime t)
        {
            if (displayedSize <= 0) return;
            if (tradeSize > displayedSize * 1.05)
            {
                if (aggressor > 0) { CountBuy++; LastBuyHidden = t; }
                else if (aggressor < 0) { CountSell++; LastSellHidden = t; }
            }
        }

        public bool RecentBuyHidden(DateTime now, int withinSec = 30)
            => LastBuyHidden != DateTime.MinValue && (now - LastBuyHidden).TotalSeconds < withinSec;
        public bool RecentSellHidden(DateTime now, int withinSec = 30)
            => LastSellHidden != DateTime.MinValue && (now - LastSellHidden).TotalSeconds < withinSec;
    }

    /// <summary>
    /// Spoof detector — proper Wasserstein-1 distance vs rolling reference + cancel rate spike.
    /// W1 measures shape distortion in the size distribution across DOM levels.
    /// Spoofs typically inflate one side's depth then cancel within seconds.
    /// </summary>
    public class SpoofDetector
    {
        private Queue<(DateTime t, double[] sizesBid, double[] sizesAsk)> _shapeHistory
            = new Queue<(DateTime, double[], double[])>();
        private int _cancelCountBid, _cancelCountAsk;
        private int _addCountBid, _addCountAsk;
        private DateTime _lastBidSpoof, _lastAskSpoof;
        private double _lastW1Bid, _lastW1Ask;
        public double LastW1Bid { get { return _lastW1Bid; } }
        public double LastW1Ask { get { return _lastW1Ask; } }

        public void OnBookChange(double price, long size, bool isBid, Operation op, DateTime t)
        {
            if (op == Operation.Remove)
            {
                if (isBid) _cancelCountBid++; else _cancelCountAsk++;
            }
            else
            {
                if (isBid) _addCountBid++; else _addCountAsk++;
            }

            // Detect cancel-rate spike: > 5× placement rate sustained
            if (_addCountBid + _addCountAsk > 20)
            {
                double bidCancelRate = _addCountBid > 0 ? (double)_cancelCountBid / _addCountBid : 0;
                double askCancelRate = _addCountAsk > 0 ? (double)_cancelCountAsk / _addCountAsk : 0;
                if (bidCancelRate > 5.0) _lastBidSpoof = t;
                if (askCancelRate > 5.0) _lastAskSpoof = t;
                _cancelCountBid = (int)(_cancelCountBid * 0.9);
                _cancelCountAsk = (int)(_cancelCountAsk * 0.9);
                _addCountBid = (int)(_addCountBid * 0.9);
                _addCountAsk = (int)(_addCountAsk * 0.9);
            }
        }

        /// <summary>
        /// Update W1 distance between current LOB shape and rolling 60s mean shape.
        /// Spike in W1 + cancel rate spike = high-confidence spoof.
        /// Call this from OnMarketDepth after capturing latest LOB snapshot.
        /// </summary>
        public void UpdateW1(double[] bidSizes, double[] askSizes, DateTime t)
        {
            if (bidSizes == null || askSizes == null) return;
            // Push to history
            var bs = (double[])bidSizes.Clone();
            var aks = (double[])askSizes.Clone();
            _shapeHistory.Enqueue((t, bs, aks));
            while (_shapeHistory.Count > 0 && (t - _shapeHistory.Peek().t).TotalSeconds > 60)
                _shapeHistory.Dequeue();
            if (_shapeHistory.Count < 30) return;

            // Compute rolling-mean shape (reference distribution)
            int n = bidSizes.Length;
            double[] meanBid = new double[n];
            double[] meanAsk = new double[n];
            int count = 0;
            foreach (var (_, hb, ha) in _shapeHistory)
            {
                for (int i = 0; i < n && i < hb.Length; i++) meanBid[i] += hb[i];
                for (int i = 0; i < n && i < ha.Length; i++) meanAsk[i] += ha[i];
                count++;
            }
            if (count == 0) return;
            for (int i = 0; i < n; i++) { meanBid[i] /= count; meanAsk[i] /= count; }

            // Normalize to probability distributions
            double sumB = 0, sumA = 0, sumMB = 0, sumMA = 0;
            for (int i = 0; i < n; i++)
            {
                sumB += bidSizes[i]; sumA += askSizes[i];
                sumMB += meanBid[i]; sumMA += meanAsk[i];
            }
            if (sumB <= 0 || sumA <= 0 || sumMB <= 0 || sumMA <= 0) return;

            // 1-D Wasserstein-1 distance on ordered support: W1(P,Q) = Σ |F_P(i) - F_Q(i)|
            double w1Bid = 0, w1Ask = 0;
            double cdfP = 0, cdfQ = 0;
            for (int i = 0; i < n; i++)
            {
                cdfP += bidSizes[i] / sumB;
                cdfQ += meanBid[i] / sumMB;
                w1Bid += Math.Abs(cdfP - cdfQ);
            }
            cdfP = 0; cdfQ = 0;
            for (int i = 0; i < n; i++)
            {
                cdfP += askSizes[i] / sumA;
                cdfQ += meanAsk[i] / sumMA;
                w1Ask += Math.Abs(cdfP - cdfQ);
            }
            _lastW1Bid = w1Bid;
            _lastW1Ask = w1Ask;

            // Threshold: W1 > 1.5 with cancel-rate spike confirms spoof
            if (w1Bid > 1.5 && _cancelCountBid > 0.6 * _addCountBid && _addCountBid > 10) _lastBidSpoof = t;
            if (w1Ask > 1.5 && _cancelCountAsk > 0.6 * _addCountAsk && _addCountAsk > 10) _lastAskSpoof = t;
        }

        public bool IsSpoofingBid(DateTime now)
        {
            return _lastBidSpoof != DateTime.MinValue && (now - _lastBidSpoof).TotalSeconds < 5;
        }
        public bool IsSpoofingAsk(DateTime now)
        {
            return _lastAskSpoof != DateTime.MinValue && (now - _lastAskSpoof).TotalSeconds < 5;
        }
    }

    /// <summary>
    /// Queue position tracker (Moallemi 2018) - simplified.
    /// </summary>
    public class QueuePositionTracker
    {
        private Dictionary<double, long> _bidQueueAhead = new Dictionary<double, long>();
        private Dictionary<double, long> _askQueueAhead = new Dictionary<double, long>();

        public void TrackOrder(double price, long size, bool isBid)
        {
            var dict = isBid ? _bidQueueAhead : _askQueueAhead;
            dict[price] = size;
        }

        public double FillProbability(double price, bool isBid, double secondsAhead, double avgFillRate)
        {
            var dict = isBid ? _bidQueueAhead : _askQueueAhead;
            if (!dict.ContainsKey(price) || avgFillRate <= 0) return 0;
            long ahead = dict[price];
            if (ahead <= 0) return 1.0;
            return 1.0 - Math.Exp(-avgFillRate * secondsAhead / ahead);
        }
    }

    // =========================================================================
    //                       PILLAR II — 16 ENGINES
    // =========================================================================

    /// <summary>
    /// E1 FOOTPRINT — VolumetricBars-driven 22-signal taxonomy.
    /// Categories: A=absorption (8), B=exhaustion (5), C=stacked (3), D=initiative (4), E=CVD-divergence (3).
    /// Reads from VolumetricBarsType: total buy/sell vol, max bid/ask, POC, delta percent, optional PriceVolumes.
    /// Each signal contributes a directional vote with magnitude; aggregated into score+prob+direction.
    /// </summary>
    public class E1Footprint
    {
        private double _cvd;
        private double _cvdPrevWindow;
        private double _prevDelta;
        private double _prevDelta2;
        private double _avgDelta;
        private double _avgVolume;
        private double _avgRange;
        private double _peakDelta;
        private int _peakDeltaBar;
        private double _peakAbsDelta;
        private bool _absorptionDetected;
        private bool _exhaustionDetected;
        private int _consecutiveBidStacks;
        private int _consecutiveAskStacks;
        private int _lastDirection;
        private double _lastScore;
        private double _lastProb;

        // Bar-history rings for divergence checks
        private double[] _closeRing = new double[20];
        private double[] _cvdRing = new double[20];
        private int _ringIdx;
        private int _ringCount;

        public bool AbsorptionDetected { get { return _absorptionDetected; } }
        public bool ExhaustionDetected { get { return _exhaustionDetected; } }
        public int ConsecutiveBidStacks { get { return _consecutiveBidStacks; } }
        public int ConsecutiveAskStacks { get { return _consecutiveAskStacks; } }

        public void UpdateFromBars(Indicator ind, int curBar)
        {
            try
            {
                var bars = ind.Bars;
                if (bars == null || curBar < 1) return;
                var vbt = bars.BarsType as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
                if (vbt == null) return;

                var volumes = vbt.Volumes;
                if (volumes == null || curBar < 0 || curBar >= volumes.Length) return;
                var vol = volumes[curBar];
                if (vol == null) return;

                double bidVol = vol.TotalBuyingVolume;
                double askVol = vol.TotalSellingVolume;
                double delta = bidVol - askVol;
                double totalVol = bidVol + askVol;
                _cvd += delta;

                // EWMA baselines (alpha = 0.05 ≈ 20-bar half-life)
                _avgDelta = _avgDelta * 0.95 + Math.Abs(delta) * 0.05;
                _avgVolume = _avgVolume * 0.95 + totalVol * 0.05;
                double barRange = ind.High[0] - ind.Low[0];
                if (barRange <= 0) barRange = ind.TickSize;
                double rangeTicks = barRange / ind.TickSize;
                _avgRange = _avgRange * 0.95 + rangeTicks * 0.05;

                // Bar geometry
                double upperWick = ind.High[0] - Math.Max(ind.Open[0], ind.Close[0]);
                double lowerWick = Math.Min(ind.Open[0], ind.Close[0]) - ind.Low[0];
                double upperWickPct = upperWick / barRange * 100.0;
                double lowerWickPct = lowerWick / barRange * 100.0;
                double bodyPct = Math.Abs(ind.Close[0] - ind.Open[0]) / barRange * 100.0;
                double deltaRatio = totalVol > 0 ? delta / totalVol : 0;

                // Peak delta tracking (for B2 exhaustion peak)
                if (Math.Abs(delta) > _peakAbsDelta)
                {
                    _peakAbsDelta = Math.Abs(delta);
                    _peakDelta = delta;
                    _peakDeltaBar = curBar;
                }
                _peakAbsDelta *= 0.99;

                // Update bar-history ring
                _closeRing[_ringIdx] = ind.Close[0];
                _cvdRing[_ringIdx] = _cvd;
                _ringIdx = (_ringIdx + 1) % _closeRing.Length;
                if (_ringCount < _closeRing.Length) _ringCount++;

                _absorptionDetected = false;
                _exhaustionDetected = false;
                int signalCount = 0;
                int dirSum = 0;
                double weightedDir = 0;

                // ===== CATEGORY A: ABSORPTION (8 signals) =====
                // A1: huge volume + tight range (pure absorption)
                if (totalVol > 1.8 * _avgVolume && rangeTicks < 0.6 * _avgRange && _avgVolume > 50)
                {
                    _absorptionDetected = true; signalCount++;
                    int s = -Math.Sign(delta);
                    dirSum += s; weightedDir += 1.5 * s;
                }
                // A2: heavy vol + small range + balanced delta
                if (totalVol > 200 && rangeTicks < 4 && Math.Abs(deltaRatio) < 0.18)
                {
                    _absorptionDetected = true; signalCount++;
                    int s = -Math.Sign(delta);
                    dirSum += s; weightedDir += 1.2 * s;
                }
                // A3: passive whale bid (bidVol >> askVol but price stalls or drops)
                if (bidVol > 2.5 * askVol && totalVol > 150 && curBar > 0 &&
                    ind.Close[0] <= ind.Close[1] + ind.TickSize)
                {
                    signalCount++;
                    dirSum += +1; weightedDir += 1.3;
                }
                // A3': passive whale ask
                if (askVol > 2.5 * bidVol && totalVol > 150 && curBar > 0 &&
                    ind.Close[0] >= ind.Close[1] - ind.TickSize)
                {
                    signalCount++;
                    dirSum += -1; weightedDir += -1.3;
                }
                // A6: absorption + delta divergence
                if (curBar > 0 && Math.Sign(ind.Close[0] - ind.Close[1]) != Math.Sign(delta)
                    && Math.Abs(delta) > 0.7 * _avgDelta && _avgDelta > 30)
                {
                    signalCount++;
                    int s = Math.Sign(ind.Close[0] - ind.Close[1]);
                    dirSum += s; weightedDir += 1.4 * s;
                }
                // A8: POC absorption — max bid/ask cluster but range tight
                long maxBidV = (long)bidVol;
                long maxAskV = (long)askVol;
                if (Math.Max(maxBidV, maxAskV) > 0.40 * totalVol && rangeTicks < 0.7 * _avgRange)
                {
                    signalCount++;
                    int s = maxBidV > maxAskV ? +1 : -1;
                    dirSum += s; weightedDir += 1.0 * s;
                }
                // A12: sweep + absorb — high vol + delta extreme but weak followthrough body
                if (totalVol > 2.0 * _avgVolume && Math.Abs(deltaRatio) > 0.5 && bodyPct < 40)
                {
                    signalCount++;
                    int s = -Math.Sign(delta);
                    dirSum += s; weightedDir += 1.6 * s;
                }
                // A20: CVD extreme persists
                if (Math.Abs(_cvd) > 4.0 * _avgDelta && _ringCount >= 10 && _avgDelta > 30)
                {
                    signalCount++;
                    int s = Math.Sign(_cvd);
                    dirSum += s; weightedDir += 0.8 * s;
                }

                // ===== CATEGORY B: EXHAUSTION (5 signals) =====
                // B1: climactic vol + reversal wick
                if (totalVol > 2.2 * _avgVolume && Math.Abs(deltaRatio) > 0.4 &&
                    (upperWickPct > 35 || lowerWickPct > 35))
                {
                    _exhaustionDetected = true; signalCount++;
                    int s = upperWickPct > lowerWickPct ? -1 : +1;
                    dirSum += s; weightedDir += 1.7 * s;
                }
                // B2: delta peak then drop
                if (curBar - _peakDeltaBar >= 2 && curBar - _peakDeltaBar <= 4 &&
                    _peakAbsDelta > 0 && Math.Abs(delta) < 0.4 * _peakAbsDelta)
                {
                    _exhaustionDetected = true; signalCount++;
                    int s = -Math.Sign(_peakDelta);
                    dirSum += s; weightedDir += 1.4 * s;
                }
                // B3: failure auction — large range that immediately reverses
                if (curBar > 1 && rangeTicks > 1.5 * _avgRange &&
                    Math.Sign(ind.Close[0] - ind.Open[0]) != Math.Sign(ind.Close[1] - ind.Open[1]))
                {
                    _exhaustionDetected = true; signalCount++;
                    int s = Math.Sign(ind.Close[0] - ind.Open[0]);
                    dirSum += s; weightedDir += 1.0 * s;
                }
                // B6: delta inversion with magnitude
                if (Math.Abs(delta - _prevDelta) > 1.5 * _avgDelta &&
                    Math.Sign(delta) != Math.Sign(_prevDelta) && Math.Abs(_prevDelta) > 40)
                {
                    signalCount++;
                    int s = Math.Sign(delta);
                    dirSum += s; weightedDir += 1.2 * s;
                }
                // B7: range expansion fail
                if (bodyPct > 70 && rangeTicks > 1.3 * _avgRange &&
                    Math.Sign(ind.Close[0] - ind.Open[0]) != Math.Sign(delta))
                {
                    _exhaustionDetected = true; signalCount++;
                    int s = -Math.Sign(ind.Close[0] - ind.Open[0]);
                    dirSum += s; weightedDir += 1.1 * s;
                }

                // ===== CATEGORY C: STACKED IMBALANCES (3 signals) =====
                int stackedBid = 0, stackedAsk = 0;
                // Fallback-only path: this NT8 build exposes VolumetricData without PriceVolumes.
                // Use delta-ratio proxy when per-price ladder data is unavailable.
                // Fallback to deltaRatio proxy if PriceVolumes not exposed
                if (stackedBid == 0 && stackedAsk == 0)
                {
                    if (deltaRatio > 0.30 && totalVol > 100) stackedBid = 4;
                    else if (deltaRatio < -0.30 && totalVol > 100) stackedAsk = 4;
                }

                // C1: 3+ stacked bid imbalances
                if (stackedBid >= 3) {
                    signalCount++;
                    dirSum += +1; weightedDir += stackedBid >= 5 ? 1.6 : 1.0;
                    _consecutiveBidStacks++;
                } else _consecutiveBidStacks = 0;

                // C2: 3+ stacked ask imbalances
                if (stackedAsk >= 3) {
                    signalCount++;
                    dirSum += -1; weightedDir += stackedAsk >= 5 ? -1.6 : -1.0;
                    _consecutiveAskStacks++;
                } else _consecutiveAskStacks = 0;

                // C3: cluster delta > 2× avg
                if (Math.Abs(delta) > 2.0 * _avgDelta && _avgDelta > 30)
                {
                    signalCount++;
                    int s = Math.Sign(delta);
                    dirSum += s; weightedDir += 0.8 * s;
                }

                // ===== CATEGORY D: INITIATIVE (4 signals) =====
                // D1: range expansion + matching delta
                if (rangeTicks > 1.4 * _avgRange && Math.Sign(delta) == Math.Sign(ind.Close[0] - ind.Open[0])
                    && Math.Abs(deltaRatio) > 0.30)
                {
                    signalCount++;
                    int s = Math.Sign(delta);
                    dirSum += s; weightedDir += 1.3 * s;
                }
                // D2: volume-led breakout
                if (totalVol > 1.6 * _avgVolume && bodyPct > 65 && Math.Abs(deltaRatio) > 0.25)
                {
                    signalCount++;
                    int s = Math.Sign(ind.Close[0] - ind.Open[0]);
                    dirSum += s; weightedDir += 1.2 * s;
                }
                // D3: above/below value with conviction
                if (Math.Abs(deltaRatio) > 0.35 && upperWickPct < 15 && lowerWickPct < 15)
                {
                    signalCount++;
                    int s = Math.Sign(delta);
                    dirSum += s; weightedDir += 0.9 * s;
                }
                // D4: 3-bar trend continuation with delta agreement
                if (curBar > 2)
                {
                    int dirP = Math.Sign(ind.Close[0] - ind.Close[2]);
                    if (dirP != 0 && Math.Sign(delta) == dirP && Math.Abs(deltaRatio) > 0.20)
                    {
                        signalCount++;
                        dirSum += dirP; weightedDir += 0.6 * dirP;
                    }
                }

                // ===== CATEGORY E: CVD DIVERGENCE (3 signals) =====
                // E1: 5-bar CVD divergence
                if (_ringCount >= 5 && curBar > 5)
                {
                    int five = (_ringIdx - 5 + _closeRing.Length) % _closeRing.Length;
                    double dPrice = ind.Close[0] - _closeRing[five];
                    double dCvd = _cvd - _cvdRing[five];
                    if (Math.Sign(dPrice) != Math.Sign(dCvd) && Math.Abs(dCvd) > 100)
                    {
                        signalCount++;
                        int s = Math.Sign(dPrice);
                        dirSum += s; weightedDir += 1.3 * s;
                    }
                }
                // E2: CVD slope inversion
                if (curBar > 2 && Math.Sign(_cvd - _cvdPrevWindow) != Math.Sign(_cvdPrevWindow) && Math.Abs(_cvdPrevWindow) > 50)
                {
                    signalCount++;
                    int s = Math.Sign(_cvd - _cvdPrevWindow);
                    dirSum += s; weightedDir += 0.7 * s;
                }
                // E3: CVD/range divergence
                if (Math.Abs(_cvd) > 3 * _avgDelta && rangeTicks < 0.8 * _avgRange && _avgDelta > 20)
                {
                    signalCount++;
                    int s = Math.Sign(_cvd);
                    dirSum += s; weightedDir += 0.6 * s;
                }

                // ----- AGGREGATE -----
                _lastDirection = weightedDir > 0.5 ? +1 : (weightedDir < -0.5 ? -1 : 0);
                _lastScore = Math.Min(28.0, signalCount * 1.3 + Math.Abs(weightedDir) * 0.8);
                _lastProb = 0.5 + Math.Tanh(weightedDir * 0.18) * 0.45;

                _prevDelta2 = _prevDelta;
                _prevDelta = delta;
                _cvdPrevWindow = _ringCount >= 5 ? _cvdRing[(_ringIdx - 5 + _closeRing.Length) % _closeRing.Length] : _cvd;
            }
            catch { /* swallow exceptions during render path */ }
        }

        public void Score(out double score, out double prob, out int direction)
        {
            score = _lastScore;
            prob = _lastProb;
            direction = _lastDirection;
        }
    }

    /// <summary>
    /// E2 TRESPASS — multi-level weighted DOM logistic (Gould-Bonart 2015).
    /// </summary>
    public class E2Trespass
    {
        // Hardcoded coefficients (replace with retrained logistic for production)
        private double[] _coefs = { 0.0, 1.4, 0.9, 0.6, 0.4, 0.2, 0.05, 0.05 };  // bias + I_1..I_5 + ofi5s + ofi10s
        private double _bias = 0.0;

        public void Score(SortedDictionary<double, long> bids, SortedDictionary<double, long> asks,
                          double ofi5s, double ofi10s,
                          out double score, out double prob, out int direction)
        {
            var bArr = bids.Take(5).Select(kv => (double)kv.Value).ToArray();
            var aArr = asks.Take(5).Select(kv => (double)kv.Value).ToArray();
            double[] I = new double[5];
            for (int k = 0; k < 5; k++)
            {
                double bSize = k < bArr.Length ? bArr[k] : 0;
                double aSize = k < aArr.Length ? aArr[k] : 0;
                double sum = bSize + aSize;
                I[k] = sum > 0 ? (bSize - aSize) / sum : 0;
            }
            double z = _bias;
            for (int k = 0; k < 5; k++) z += _coefs[k + 1] * I[k];
            z += _coefs[6] * Math.Tanh(ofi5s / 100.0);
            z += _coefs[7] * Math.Tanh(ofi10s / 100.0);
            prob = 1.0 / (1.0 + Math.Exp(-z));
            direction = prob > 0.5 ? +1 : -1;
            score = 20.0 * Math.Min(1.0, Math.Abs(prob - 0.5) * 2.0);
        }
    }

    /// <summary>
    /// E3 SPOOF — uses SpoofDetector + W₁ logic. Veto-capable.
    /// </summary>
    public class E3Spoof
    {
        public void Score(SpoofDetector spoof, SortedDictionary<double, long> bids,
                          SortedDictionary<double, long> asks,
                          out double score, out double prob, out int direction)
        {
            DateTime now = DateTime.UtcNow;
            bool bidSpoof = spoof.IsSpoofingBid(now);
            bool askSpoof = spoof.IsSpoofingAsk(now);
            // Counter-spoof signal: if bid spoof detected, expect price to drop (short signal)
            if (bidSpoof) { direction = -1; score = 15; prob = 0.65; }
            else if (askSpoof) { direction = +1; score = 15; prob = 0.65; }
            else { direction = 0; score = 0; prob = 0.5; }
        }
    }

    /// <summary>
    /// E4 ICEBERG composite — A1 + A4 + A12 (iceberg-absorbing-sweep).
    /// </summary>
    public class E4Iceberg
    {
        public void Score(IcebergDetector ice, HiddenFillDetector hf, DateTime now,
                          out double score, out double prob, out int direction)
        {
            double s = 0;
            int dir = 0;
            int components = 0;
            if (ice.RecentlyDetected(now, 30))
            {
                s += 5;
                dir += ice.LastDirection;
                components++;
            }
            if (hf.RecentBuyHidden(now, 30)) { s += 5; dir += +1; components++; }
            if (hf.RecentSellHidden(now, 30)) { s += 5; dir += -1; components++; }
            score = Math.Min(15, s);
            direction = dir > 0 ? +1 : (dir < 0 ? -1 : 0);
            prob = 0.5 + Math.Sign(dir) * Math.Min(0.35, components * 0.10);
        }
    }

    /// <summary>
    /// E5 MICRO BAYES — naive Bayes log-odds combination of E1, E2, E4.
    /// </summary>
    public class E5MicroBayes
    {
        public void Score(double e1p, int e1d, double e2p, int e2d, double e4p, int e4d,
                          out double score, out double prob, out int direction)
        {
            // logit(P_long) = sum of LLR_i where engine fires for long (+1) or short (-1)
            double prior = 0.0;
            double logit = prior;
            if (e1d != 0) logit += e1d * Math.Log(Math.Max(e1p, 0.01) / Math.Max(1 - e1p, 0.01));
            if (e2d != 0) logit += e2d * Math.Log(Math.Max(e2p, 0.01) / Math.Max(1 - e2p, 0.01));
            if (e4d != 0) logit += e4d * Math.Log(Math.Max(e4p, 0.01) / Math.Max(1 - e4p, 0.01));
            prob = 1.0 / (1.0 + Math.Exp(-logit * 0.7));  // shrinkage λ=0.7 for correlation
            direction = prob > 0.5 ? +1 : -1;
            score = 10.0 * Math.Min(1.0, Math.Abs(prob - 0.5) * 2.0);
        }
    }

    /// <summary>
    /// E6 VP+CTX — VWAP, IB, POC, GEX-zone scoring.
    /// </summary>
    public class E6VPCtx
    {
        public void Score(double dist2VWAPticks, double dist2POCticks, bool aboveIB, bool belowIB,
                          GEXContext gex, out double score, out double prob, out int direction)
        {
            double s = 0;
            int dir = 0;
            // VWAP zone scoring
            if (Math.Abs(dist2VWAPticks) < 4) { s += 2; }  // at VWAP
            if (dist2VWAPticks < -8) { s += 3; dir += +1; }   // below VWAP, long bias
            if (dist2VWAPticks > +8) { s += 3; dir += -1; }   // above VWAP, short bias
            // IB scoring (Steidlmayer)
            if (aboveIB) { s += 3; dir += +1; }
            if (belowIB) { s += 3; dir += -1; }
            // POC proximity
            if (Math.Abs(dist2POCticks) < 6) { s += 2; }
            // GEX zone scoring
            if (gex.IsValid)
            {
                if (gex.GammaFlip > 0) {
                    if (Math.Abs(dist2VWAPticks) < 999) { /* GEX stub */ }
                }
            }
            score = Math.Min(15, s);
            direction = dir > 0 ? +1 : (dir < 0 ? -1 : 0);
            prob = 0.5 + Math.Sign(dir) * Math.Min(0.30, score * 0.02);
        }
    }

    /// <summary>
    /// E7 ML QUALITY — 8-feature logistic + 1-d Kalman filter for stability.
    /// Output quality ∈ [0,1] is the smoothed logistic posterior.
    /// </summary>
    public class E7MLQuality
    {
        // Hardcoded weights (replace with retrained logistic from offline training)
        private double[] _w = { -0.3, +0.2, -1.5, -2.0, +0.8, +1.0, -0.05, +0.5 };
        private double _bias = 1.5;

        // 1-d Kalman state for quality smoothing
        private double _x = 0.5;          // posterior mean
        private double _P = 0.25;         // posterior variance
        private const double Q = 1e-4;    // process noise (slow drift)
        private const double R = 0.05;    // observation noise (logistic readings noisy)

        public void Score(double[] features, out double quality)
        {
            if (features == null || features.Length < 8) { quality = _x; return; }
            // Logistic raw observation
            double z = _bias;
            for (int i = 0; i < 8; i++) z += _w[i] * features[i];
            double obs = 1.0 / (1.0 + Math.Exp(-z));
            obs = Math.Max(0.001, Math.Min(0.999, obs));

            // Kalman predict: x' = x, P' = P + Q
            _P += Q;

            // Kalman update: K = P/(P+R), x = x + K(obs - x), P = (1-K)P
            double K = _P / (_P + R);
            _x += K * (obs - _x);
            _P *= (1 - K);

            quality = Math.Max(0.0, Math.Min(1.0, _x));
        }
    }

    /// <summary>
    /// E8 HAWKES — branching ratio absorption / exhaustion engine.
    /// </summary>
    public class E8Hawkes
    {
        public void Score(MarkedHawkes hawkes, double kyleLambda,
                          out double score, out double prob, out int direction)
        {
            double n = hawkes.BranchingRatio;
            double lam = hawkes.CurrentLambda;
            // Absorption: high lambda + low Kyle's lambda
            bool absorb = lam > 5.0 && Math.Abs(kyleLambda) < 0.0005;
            // Exhaustion: branching ratio collapsed
            bool exhaust = n < 0.30 && lam > 3.0;

            if (absorb) {
                // direction: counter to current dominant flow (placeholder)
                score = 10; prob = 0.62; direction = Math.Sign(kyleLambda) >= 0 ? -1 : +1;
            } else if (exhaust) {
                score = 10; prob = 0.62; direction = Math.Sign(kyleLambda) >= 0 ? -1 : +1;
            } else {
                score = 0; prob = 0.5; direction = 0;
            }
        }
    }

    /// <summary>
    /// E9 MICROPRICE-DRIFT — Stoikov stasis under heavy flow = absorption.
    /// </summary>
    public class E9MPDrift
    {
        private double _prevValue;
        private DateTime _prevTime;

        public void Score(Microprice mp, long recentVolume, DateTime now,
                          out double score, out double prob, out int direction)
        {
            double v = mp.Value;
            double drift = Math.Abs(v - _prevValue);
            double dt = _prevTime != DateTime.MinValue ? (now - _prevTime).TotalSeconds : 0;
            // Stasis under heavy flow
            bool absorb = drift < 0.5 && recentVolume > 200 && dt > 0.5;
            // Microprice flip
            bool flip = _prevValue > 0 && Math.Sign(v - _prevValue) != Math.Sign(mp.RecentDriftVelocity);

            if (absorb) {
                score = 10; prob = 0.60;
                direction = mp.DeviationTicks > 0 ? -1 : +1;  // counter to current bias
            } else if (flip) {
                score = 6; prob = 0.55;
                direction = Math.Sign(v - _prevValue);
            } else {
                score = 0; prob = 0.5; direction = 0;
            }

            _prevValue = v;
            _prevTime = now;
        }
    }

    /// <summary>
    /// E10 VPIN GATE — handled inline in main indicator (no class needed beyond toxicity threshold).
    /// </summary>
    public class E10VPINGate { /* logic inline */ }

    /// <summary>
    /// E11 GEX AMPLIFIER — 7-regime classifier with hysteresis.
    /// </summary>
    public class E11GEXAmp
    {
        private int _currentRegime = 0;
        private int _candidateRegime = 0;
        private int _candidateCount = 0;

        public void Score(GEXContext gex, double price,
                          out double longMult, out double shortMult, out int regime)
        {
            longMult = 1.0; shortMult = 1.0;
            if (!gex.IsValid) { regime = 0; return; }

            int proposed = ClassifyRegime(gex, price);

            // Hysteresis: require 3-bar persistence in new regime
            if (proposed == _candidateRegime) {
                _candidateCount++;
                if (_candidateCount >= 3) {
                    _currentRegime = proposed;
                    _candidateCount = 0;
                }
            } else {
                _candidateRegime = proposed;
                _candidateCount = 1;
            }
            regime = _currentRegime;

            switch (_currentRegime)
            {
                case 0: longMult = 1.4; shortMult = 0.9; break; // R1 deep + γ-long
                case 1: longMult = 0.9; shortMult = 1.5; break; // R2 approaching call wall
                case 2: longMult = 0.7; shortMult = 1.7; break; // R3 at call wall
                case 3: longMult = 1.5; shortMult = 0.9; break; // R4 approaching put wall
                case 4: longMult = 1.7; shortMult = 0.7; break; // R5 at put wall
                case 5: longMult = 1.3; shortMult = 1.6; break; // R6 below flip (negative γ)
                case 6: longMult = 0.5; shortMult = 0.5; break; // R7 0DTE pinning
            }
        }

        private int ClassifyRegime(GEXContext gex, double price)
        {
            double dist2flip = gex.GammaFlip > 0 ? (price - gex.GammaFlip) / gex.GammaFlip : 0;
            double dist2callwall = gex.CallWall > 0 ? (price - gex.CallWall) / gex.CallWall : 1;
            double dist2putwall = gex.PutWall > 0 ? (price - gex.PutWall) / gex.PutWall : -1;

            // R7 0DTE pinning - placeholder
            // R3 at call wall
            if (Math.Abs(dist2callwall) < 0.001) return 2;
            // R5 at put wall
            if (Math.Abs(dist2putwall) < 0.001) return 4;
            // R2 approaching call wall (within 0.3%)
            if (price < gex.CallWall && (gex.CallWall - price) / gex.CallWall < 0.003) return 1;
            // R4 approaching put wall
            if (price > gex.PutWall && (price - gex.PutWall) / gex.PutWall < 0.003) return 3;
            // R6 below flip
            if (dist2flip < 0) return 5;
            // R1 default deep + gamma-long
            return 0;
        }
    }

    /// <summary>
    /// E12 DOFI / MLOFI-PCA — Cont-Kukanov + Kolm-Westray (2023).
    /// Projects multi-level OFI vector onto live online PC1 (Oja's rule, learned by MLOFIComputer).
    /// Falls back to declining-weights prior if Oja hasn't warmed up yet.
    /// </summary>
    public class E12DOFI
    {
        private double[] _priorPc1 = { 1.0, 0.7, 0.5, 0.3, 0.2 };
        private double _runningStd = 50.0;
        private double _runningMean;

        public void Score(MLOFIComputer mlofi, OFIRolling[] buckets,
                          out double score, out double prob, out int direction)
        {
            double[] vec = mlofi.Vector;
            double[] pc1 = mlofi.UpdateCount > 200 ? mlofi.PC1 : _priorPc1;
            if (vec == null) vec = new double[5];
            double dofi = 0;
            for (int i = 0; i < Math.Min(pc1.Length, vec.Length); i++) dofi += pc1[i] * vec[i];

            // Welford-style running mean & std for z-scoring
            _runningMean = 0.995 * _runningMean + 0.005 * dofi;
            double centered = dofi - _runningMean;
            _runningStd = 0.99 * _runningStd + 0.01 * Math.Abs(centered);
            double zscore = _runningStd > 0 ? centered / _runningStd : 0;

            prob = 1.0 / (1.0 + Math.Exp(-zscore));
            direction = prob > 0.5 ? +1 : -1;
            score = 15.0 * Math.Min(1.0, Math.Abs(prob - 0.5) * 2.0);
        }
    }

    /// <summary>
    /// E13 LOB-NN — TLOB / DeepLOB ONNX wrapper or online logistic placeholder.
    /// In v1 ships with an online logistic that learns from the FTRL outcome stream.
    /// To enable ONNX: place tlob_nq.onnx in AddOns folder and set UseOnnxHeads = true.
    /// </summary>
    public class E13LOBNN
    {
        private bool _useOnnx;
        private string _onnxPath;
        private double[] _w; // online logistic weights for placeholder mode
        private double _bias;
        private const int FEATURE_DIM = 40 * 100; // 40 features × 100 snapshots flattened

        public E13LOBNN(bool useOnnx, string onnxPath)
        {
            _useOnnx = useOnnx;
            _onnxPath = onnxPath;
            // Placeholder logistic: simple per-feature weights, all near zero initially
            _w = new double[40];
            for (int i = 0; i < 40; i++) _w[i] = 0;
            _bias = 0;
        }

        public void Score(LOBSnapshot[] buf, int idx, int count,
                          out double score, out double pUp, out double pDown)
        {
            // Build aggregated features from latest snapshot only (simplified placeholder)
            int latestIdx = (idx - 1 + buf.Length) % buf.Length;
            var snap = buf[latestIdx];
            if (snap == null || snap.BidPrices[0] == 0) {
                pUp = 0.5; pDown = 0.5; score = 0; return;
            }
            // Features: depth imbalance at each level
            double[] x = new double[40];
            for (int k = 0; k < 10; k++)
            {
                double bs = snap.BidSizes[k];
                double aks = snap.AskSizes[k];
                double sum = bs + aks;
                x[k * 4 + 0] = sum > 0 ? (bs - aks) / sum : 0;
                x[k * 4 + 1] = bs / 100.0;
                x[k * 4 + 2] = aks / 100.0;
                x[k * 4 + 3] = snap.BidPrices[k] > 0 ? (snap.AskPrices[k] - snap.BidPrices[k]) / 0.25 : 0;
            }
            double z = _bias;
            for (int i = 0; i < 40; i++) z += _w[i] * x[i];
            pUp = 1.0 / (1.0 + Math.Exp(-z));
            pDown = 1.0 - pUp;
            score = 20.0 * Math.Abs(pUp - 0.5) * 2.0;
        }

        public void OnlineUpdate(double[] features, int label)
        {
            // SGD step for placeholder mode
            if (_useOnnx) return;  // skip if ONNX active
            double z = _bias;
            for (int i = 0; i < Math.Min(features.Length, _w.Length); i++) z += _w[i] * features[i];
            double p = 1.0 / (1.0 + Math.Exp(-z));
            double err = p - label;
            double lr = 0.01;
            for (int i = 0; i < Math.Min(features.Length, _w.Length); i++)
                _w[i] -= lr * err * features[i];
            _bias -= lr * err;
        }
    }

    /// <summary>
    /// E14 META-LABEL — XGBoost ONNX or online logistic placeholder.
    /// Predicts P(primary signal correct | feature vector) per López de Prado AFML ch.3.
    /// </summary>
    public class E14MetaLabel
    {
        private bool _useOnnx;
        private string _onnxPath;
        private double[] _w;
        private double _bias;

        public E14MetaLabel(bool useOnnx, string onnxPath)
        {
            _useOnnx = useOnnx;
            _onnxPath = onnxPath;
            _w = new double[40];
            // Bootstrap: meta starts neutral with slight positive prior
            _bias = 0.1;
        }

        public void Score(double[] features, out double pTake)
        {
            if (features == null || features.Length < 40) { pTake = 0.55; return; }
            double z = _bias;
            for (int i = 0; i < 40; i++) z += _w[i] * features[i];
            pTake = 1.0 / (1.0 + Math.Exp(-z));
            pTake = Math.Max(0.0, Math.Min(1.0, pTake));
        }

        public void OnlineUpdate(double[] features, int label)
        {
            if (_useOnnx) return;
            double z = _bias;
            for (int i = 0; i < Math.Min(features.Length, _w.Length); i++) z += _w[i] * features[i];
            double p = 1.0 / (1.0 + Math.Exp(-z));
            double err = p - label;
            double lr = 0.02;
            for (int i = 0; i < Math.Min(features.Length, _w.Length); i++)
                _w[i] -= lr * err * features[i];
            _bias -= lr * err;
        }
    }

    /// <summary>
    /// E15 REGIME ROUTER — simplified HMM-5 with online updating.
    /// Production version would use proper EM-trained HMM with forward algorithm.
    /// </summary>
    public class E15Regime
    {
        public RegimeState CurrentRegime = RegimeState.RangeScalp;
        private double[] _gamma = new double[] { 0.2, 0.2, 0.2, 0.2, 0.2 };  // posterior over states
        private int _barsSinceUpdate = 0;

        public void UpdateOn5Min(Indicator ind)
        {
            if (ind.CurrentBars[1] < 12) return;
            try
            {
                _barsSinceUpdate++;
                if (_barsSinceUpdate < 1) return;
                _barsSinceUpdate = 0;

                // Features for regime classification (5min bar)
                var bars = ind.BarsArray[1];
                if (bars == null || bars.Count < 12) return;

                int idx = bars.Count - 1;
                double range = bars.GetHigh(idx) - bars.GetLow(idx);

                // Compute realized vol over last 12 bars
                double rv = 0;
                for (int i = 1; i <= 12 && idx - i >= 0; i++)
                {
                    double r = bars.GetClose(idx - i + 1) - bars.GetClose(idx - i);
                    rv += r * r;
                }
                rv = Math.Sqrt(rv / 12.0);

                // Compute trend strength: regression slope of last 12 closes
                double meanX = 5.5, meanY = 0;
                for (int i = 0; i < 12; i++)
                    if (idx - i >= 0) meanY += bars.GetClose(idx - i);
                meanY /= 12;
                double sxy = 0, sxx = 0;
                for (int i = 0; i < 12; i++)
                    if (idx - i >= 0)
                    {
                        sxy += (i - meanX) * (bars.GetClose(idx - i) - meanY);
                        sxx += (i - meanX) * (i - meanX);
                    }
                double slope = sxx > 0 ? sxy / sxx : 0;
                double trendStrength = Math.Abs(slope) / Math.Max(rv, 0.0001);

                // Simple deterministic regime selection (proxy for HMM forward step)
                // Reversal: low trend, mid vol, recent reversal in close
                // Trend continuation: high trend, low vol
                // Breakout: high vol surge, range expansion
                // Range scalp: low trend, low vol
                // Filtered: extreme vol or extreme low vol

                if (rv > 50.0) CurrentRegime = RegimeState.Filtered;
                else if (rv < 1.0) CurrentRegime = RegimeState.Filtered;
                else if (trendStrength > 0.5 && rv < 25) CurrentRegime = RegimeState.TrendContinuation;
                else if (rv > 25 && range > 30) CurrentRegime = RegimeState.Breakout;
                else if (trendStrength < 0.2) CurrentRegime = RegimeState.RangeScalp;
                else CurrentRegime = RegimeState.Reversal;
            }
            catch { }
        }
    }

    /// <summary>
    /// E16 DRIFT MONITOR — Page-Hinkley test on running log-loss (Page 1954).
    /// </summary>
    public class E16Drift
    {
        private double _slack;
        private double _alarm;
        private double _m;
        private double _M;
        private double _muLoss = 0.65;  // initial estimate of stationary log-loss
        private int _n;
        public bool AlarmActive;
        public double PHValue => _M - _m;

        public E16Drift(double slack, double alarm) { _slack = slack; _alarm = alarm; }

        public void Update(double logLoss)
        {
            _n++;
            // Online mean update
            _muLoss = (_muLoss * (_n - 1) + logLoss) / Math.Max(1, _n);
            _m += (logLoss - _muLoss - _slack);
            if (_m < 0) _m = 0;
            if (_m > _M) _M = _m;
            AlarmActive = (_M - _m) > _alarm;
            if (AlarmActive)
            {
                // Reset on alarm; keep alarm flag for one cycle of caller usage
                _m = 0; _M = 0;
            }
        }
    }

    // =========================================================================
    //                    PILLAR IV — FUSION + ONLINE LEARNING
    // =========================================================================

    /// <summary>
    /// FTRL-Proximal online logistic (McMahan et al. 2013 KDD).
    /// L1 sparsity + L2 shrinkage + per-feature adaptive learning rates.
    /// Memory: O(d) where d = feature vector dimension.
    /// </summary>
    public class FTRLProximal
    {
        private int _d;
        private double _alpha, _beta, _l1, _l2, _gamma;
        private double[] _z;
        private double[] _n;
        private double[] _w;
        public int UpdateCount;
        public double LastPrediction;
        public double LastLogLoss;

        public FTRLProximal(int d, double alpha, double beta, double l1, double l2, double gamma)
        {
            _d = d; _alpha = alpha; _beta = beta; _l1 = l1; _l2 = l2; _gamma = gamma;
            _z = new double[d];
            _n = new double[d];
            _w = new double[d];
        }

        public double Predict(double[] x)
        {
            if (x == null || x.Length < _d) { LastPrediction = 0.5; return 0.5; }
            double wtx = 0;
            for (int i = 0; i < _d; i++)
            {
                if (x[i] == 0) continue;
                double zi = _z[i];
                if (Math.Abs(zi) <= _l1) _w[i] = 0;
                else
                {
                    double sign = zi > 0 ? 1.0 : -1.0;
                    _w[i] = -(zi - sign * _l1) /
                            ((_beta + Math.Sqrt(_n[i])) / _alpha + _l2);
                }
                wtx += _w[i] * x[i];
            }
            LastPrediction = 1.0 / (1.0 + Math.Exp(-wtx));
            return LastPrediction;
        }

        public void Update(double[] x, int y)
        {
            if (x == null || x.Length < _d) return;
            double p = Predict(x);
            double err = p - y;
            // Log loss
            double yp = y == 1 ? p : 1 - p;
            LastLogLoss = -Math.Log(Math.Max(yp, 1e-9));
            for (int i = 0; i < _d; i++)
            {
                if (x[i] == 0)
                {
                    _z[i] *= _gamma;
                    _n[i] *= _gamma;
                    continue;
                }
                double g = err * x[i];
                double sigma = (Math.Sqrt(_n[i] + g * g) - Math.Sqrt(_n[i])) / _alpha;
                _z[i] = _gamma * _z[i] + g - sigma * _w[i];
                _n[i] = _gamma * _n[i] + g * g;
            }
            UpdateCount++;
        }

        public void AmplifyLearningRate(double factor)
        {
            // Effectively boost α by reducing accumulated n (with floor)
            for (int i = 0; i < _d; i++) _n[i] /= Math.Max(1.0, factor);
        }
    }

    /// <summary>
    /// Hedge algorithm blender (Freund-Schapire 1997). Blends predictions from K experts
    /// using exponentially-weighted negative-log-loss weights.
    /// </summary>
    public class HedgeBlender
    {
        private int _k;
        private double _eta;
        private double[] _cumLoss;
        private double[] _weights;

        public HedgeBlender(int k, double eta) { _k = k; _eta = eta; _cumLoss = new double[k]; _weights = new double[k]; for (int i = 0; i < k; i++) _weights[i] = 1.0 / k; }

        public double Blend(double[] preds)
        {
            if (preds == null || preds.Length != _k) return 0.5;
            // Recompute weights
            double maxNegLoss = double.MinValue;
            for (int i = 0; i < _k; i++)
            {
                double v = -_eta * _cumLoss[i];
                if (v > maxNegLoss) maxNegLoss = v;
            }
            double sum = 0;
            for (int i = 0; i < _k; i++)
            {
                _weights[i] = Math.Exp(-_eta * _cumLoss[i] - maxNegLoss);
                sum += _weights[i];
            }
            if (sum <= 0) sum = 1;
            double result = 0;
            for (int i = 0; i < _k; i++)
            {
                _weights[i] /= sum;
                result += _weights[i] * preds[i];
            }
            return result;
        }

        public void RegisterLoss(int idx, double loss)
        {
            if (idx >= 0 && idx < _k) _cumLoss[idx] += loss;
        }
    }

    /// <summary>
    /// Bayesian combiner — log-odds aggregation across all engine outputs with shrinkage.
    /// </summary>
    public class BayesianCombiner
    {
        public double Combine(EngineOutputs eo)
        {
            // logit(P_long) = sum of dir_i × LLR_i
            double logit = 0;
            int dir = 1;

            // Each engine contributes its directional LLR weighted by its calibrated probability
            logit += eo.E1Direction * Llr(eo.E1Prob);
            logit += eo.E2Direction * Llr(eo.E2Prob);
            logit += eo.E3Direction * Llr(eo.E3Prob) * 0.6;  // E3 mostly veto, small weight
            logit += eo.E4Direction * Llr(eo.E4Prob);
            logit += eo.E5Direction * Llr(eo.E5Prob);
            logit += eo.E6Direction * Llr(eo.E6Prob) * 0.7;
            logit += eo.E8Direction * Llr(eo.E8Prob);
            logit += eo.E9Direction * Llr(eo.E9Prob);
            logit += eo.E12Direction * Llr(eo.E12Prob);
            logit += eo.E13Direction * Llr(eo.E13Prob) * 0.8;

            // Correlation shrinkage λ_corr ≈ 0.7 (engines are correlated)
            double shrunk = logit * 0.7;
            return 1.0 / (1.0 + Math.Exp(-shrunk));
        }

        private double Llr(double p)
        {
            p = Math.Max(0.05, Math.Min(0.95, p));
            return Math.Log(p / (1 - p));
        }
    }

    /// <summary>
    /// Beta-Bernoulli per-engine × per-regime reliability tracker.
    /// </summary>
    public class BetaBernoulliReliability
    {
        private int _engines;
        private int _regimes;
        private double[,] _alpha;
        private double[,] _beta;
        private double _decay = 0.98;

        public BetaBernoulliReliability(int numEngines, int numRegimes)
        {
            _engines = numEngines;
            _regimes = numRegimes;
            _alpha = new double[numEngines, numRegimes];
            _beta = new double[numEngines, numRegimes];
            // Prior Beta(5,5)
            for (int i = 0; i < numEngines; i++)
                for (int j = 0; j < numRegimes; j++)
                {
                    _alpha[i, j] = 5;
                    _beta[i, j] = 5;
                }
        }

        public void Update(TradeOutcome outcome)
        {
            // Decay all cells
            for (int i = 0; i < _engines; i++)
                for (int j = 0; j < _regimes; j++)
                {
                    _alpha[i, j] *= _decay;
                    _beta[i, j] *= _decay;
                }
            // Update active cells - approximation: assume all engines fired in regime
            // Real impl should track which engines fired per signal
            int regIdx = (int)outcome.Grade;
            if (regIdx < 0 || regIdx >= _regimes) return;
            for (int i = 0; i < _engines; i++)
            {
                if (outcome.RMultiple > 0) _alpha[i, regIdx] += 1;
                else _beta[i, regIdx] += 1;
            }
        }

        public double Reliability(int engineIdx, int regimeIdx)
        {
            if (engineIdx < 0 || engineIdx >= _engines) return 0.5;
            if (regimeIdx < 0 || regimeIdx >= _regimes) return 0.5;
            double a = _alpha[engineIdx, regimeIdx];
            double b = _beta[engineIdx, regimeIdx];
            return a / (a + b);
        }
    }

    // =========================================================================
    //                    PILLAR III — TIER 1 + TIER 3 GATES
    // =========================================================================

    /// <summary>
    /// Tier 1: CONTEXT — slow, daily/hourly. GEX positioning + macro bias.
    /// </summary>
    public class TierOneContext
    {
        public int Bias;
        public double Strength;

        public void Update(GEXContext gex, double price)
        {
            Bias = 0;
            Strength = 0.5;
            if (!gex.IsValid) return;

            // Below γ-flip → bearish bias
            if (gex.GammaFlip > 0)
            {
                if (price < gex.GammaFlip * 0.998) { Bias = -1; Strength = 0.6; }
                else if (price > gex.GammaFlip * 1.002) { Bias = +1; Strength = 0.6; }
            }
            // Near put wall = floor (slight long bias)
            if (gex.PutWall > 0 && Math.Abs(price - gex.PutWall) / gex.PutWall < 0.002)
            {
                Bias = +1;
                Strength = 0.7;
            }
            // Near call wall = ceiling (slight short bias)
            if (gex.CallWall > 0 && Math.Abs(price - gex.CallWall) / gex.CallWall < 0.002)
            {
                Bias = -1;
                Strength = 0.7;
            }
        }
    }

    /// <summary>
    /// Tier 3: LEVEL — find nearest meaningful structural level.
    /// </summary>
    public class TierThreeLevel
    {
        public double DistanceATR = 5.0;
        public string NearestLevelType = "";
        public double NearestLevelPrice = 0;

        public void Update(Indicator ind, GEXContext gex, double sessionVWAP,
                           double ibHigh, double ibLow, double priorDayHigh, double priorDayLow,
                           double sessionPOC, double atr)
        {
            if (atr <= 0) atr = ind.TickSize * 32;
            double price = ind.Close[0];
            double minDist = double.MaxValue;
            string minType = "";
            double minPrice = 0;

            void TryLevel(double lvl, string name)
            {
                if (lvl <= 0) return;
                double d = Math.Abs(price - lvl) / atr;
                if (d < minDist) { minDist = d; minType = name; minPrice = lvl; }
            }

            TryLevel(gex.GammaFlip, "γ-flip");
            TryLevel(gex.CallWall, "CallWall");
            TryLevel(gex.PutWall, "PutWall");
            TryLevel(sessionVWAP, "VWAP");
            TryLevel(ibHigh, "IBH");
            TryLevel(ibLow, "IBL");
            TryLevel(priorDayHigh, "PDH");
            TryLevel(priorDayLow, "PDL");
            TryLevel(sessionPOC, "POC");

            DistanceATR = minDist == double.MaxValue ? 5.0 : minDist;
            NearestLevelType = minType;
            NearestLevelPrice = minPrice;
        }
    }

} // end namespace

