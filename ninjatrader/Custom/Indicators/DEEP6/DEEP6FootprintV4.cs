// DEEP6 Footprint — NinjaTrader 8 indicator.
//
// This file contains the main DEEP6 Footprint indicator: the FootprintBar / Cell
// data structures, AbsorptionDetector (4 variants + VAH/VAL bonus),
// ExhaustionDetector (6 variants + delta gate + cooldown), and profile-anchor
// overlay (prior-day POC/VAH/VAL, PDH/PDL/PDM, naked POCs, prior-week POC).
//
// Options/gamma overlay lives in the companion DEEP6 indicator — add it separately.
//
// Drop-in install: copy this file to
//   %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\DEEP6FootprintV4.cs
// then F5 in the NinjaScript Editor.
//
// See repository docs/ for SETUP, SIGNALS, and ARCHITECTURE reference.
// Port spec: .planning/phases/16-*/PORT-SPEC.md (thresholds authoritative).

#region Using
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Linq;
using System.Text;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript.DrawingTools;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Levels;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
// Type aliases resolve System.Windows.Media vs SharpDX.Direct2D1 ambiguity.
// Bare Brush / Color / SolidColorBrush = WPF. SharpDX variants always fully qualified.
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
using Color = System.Windows.Media.Color;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6FootprintV4 : Indicator
    {
        // ---- State ----
        private readonly Dictionary<int, FootprintBar> _bars = new Dictionary<int, FootprintBar>();
        private readonly object _barsLock = new object();
        private readonly HashSet<int> _finalizedBars = new HashSet<int>();
        private double _bestBid = double.NaN;
        private double _bestAsk = double.NaN;
        private long _priorCvd;
        private FootprintBar _priorFinalized;

        // ---- L2 Liquidity Walls (from Rithmic native depth feed) ----
        // Per-price state: max size ever observed at this level + last-update timestamp + iceberg refill counter.
        // OnMarketDepth populates these on the data thread; OnRender reads on the chart thread (locked snapshot).
        private sealed class L2LevelState
        {
            public long CurrentSize;
            public long MaxSize;
            public DateTime LastUpdate;
            public int RefillCount;
        }
        private readonly Dictionary<double, L2LevelState> _l2Bids = new Dictionary<double, L2LevelState>();
        private readonly Dictionary<double, L2LevelState> _l2Asks = new Dictionary<double, L2LevelState>();
        private readonly object _l2Lock = new object();
        private DateTime _lastL2Prune = DateTime.MinValue;

        // volume EMA (for absorption thresholds) — simple 20-period EMA of TotalVol
        private double _volEma;
        private const double VolEmaAlpha = 2.0 / (20.0 + 1.0);

        // trend EMA (for counter-trend warning on setup markers)
        private double _trendEma;
        private double _trendEmaSlope;
        private double _trendEmaAlpha;

        // ATR via rolling window of (high-low)
        private readonly Queue<double> _atrWindow = new Queue<double>();
        private const int AtrPeriod = 20;
        private double _atr = 1.0;

        // detectors + configs
        private readonly AbsorptionConfig _absCfg = new AbsorptionConfig();
        private readonly ExhaustionConfig _exhCfg = new ExhaustionConfig();
        private readonly ExhaustionDetector _exhDetector = new ExhaustionDetector();

        // ---- Chart Trader toolbar (clickable on/off toggles for each feature, rendered top-left) ----
        private sealed class TraderButton
        {
            public string Label;
            public Func<bool> Get;
            public Action<bool> Set;
            public RectangleF Rect;
        }
        private List<TraderButton> _ctButtons;
        private bool _ctMouseWired;
        private SharpDX.Direct2D1.Brush _ctOnDx, _ctOffDx, _ctBorderDx;
        private TextFormat _ctBtnFont;

        // ──── V2 New Feature State ────────────────────────────────────────────────
        // VWAP (incremental per session — reset at session boundary)
        private double _vwapNumerator;
        private double _vwapDenominator;
        private double _vwapVariance;
        private double _vwapPrice;
        private double _vwap1SigHigh, _vwap1SigLow;
        private double _vwap2SigHigh, _vwap2SigLow;

        // Initial Balance window (9:30–10:30 ET ≈ first 60 one-minute bars)
        private double _ibHigh = double.MinValue;
        private double _ibLow  = double.MaxValue;
        private bool   _ibConfirmed;

        // Bull/Bear Column detection per bar (+1=bull, -1=bear, 0=mixed)
        private readonly Dictionary<int, int> _barColumnType = new Dictionary<int, int>();

        // Stacked imbalance zone boxes (computed per bar close)
        private struct StackedZone
        {
            public double PriceLow;
            public double PriceHigh;
            public int    Tier;       // 1=3–4 rows, 2=5–6 rows, 3=7+ rows
            public int    Direction;  // +1 buy zone, -1 sell zone
        }
        private readonly Dictionary<int, List<StackedZone>> _stackedZones = new Dictionary<int, List<StackedZone>>();

        // Unfinished auction persistent levels (price → bar index when first detected)
        private readonly Dictionary<double, int> _unfinishedAuctions = new Dictionary<double, int>();

        // Large lot marks per bar (barIdx → set of prices that had ≥ LargeLotThreshold contracts in one print)
        private readonly Dictionary<int, HashSet<double>> _largeLotBars = new Dictionary<int, HashSet<double>>();

        // Speed of Tape
        private int      _tradeCountThisSecond;
        private DateTime _tapeSecondWindow = DateTime.MinValue;
        private double   _smoothedTapeSpeed;
        private double   _sessionAvgTapeSpeed;
        private int      _tapeSpeedSamples;

        // Volume Climax per bar (+1=bullish climax at bottom, -1=bearish climax at top)
        private readonly Dictionary<int, int> _volumeClimaxBars = new Dictionary<int, int>();
        private readonly Queue<double>         _nBarHighs = new Queue<double>();
        private readonly Queue<double>         _nBarLows  = new Queue<double>();
        private const int NBarLookback = 20;

        // Heatmap palette (16 intensity steps, pre-built in OnRenderTargetChanged, disposed in DisposeDx)
        private const int HeatmapSteps = 16;
        private readonly SharpDX.Direct2D1.SolidColorBrush[] _heatmapPalette =
            new SharpDX.Direct2D1.SolidColorBrush[HeatmapSteps];

        // V2 rendering brushes (device-dependent)
        private SharpDX.Direct2D1.SolidColorBrush _vwapLineDx;
        private SharpDX.Direct2D1.SolidColorBrush _vwapBand1Dx;
        private SharpDX.Direct2D1.SolidColorBrush _vwapBand2Dx;
        private SharpDX.Direct2D1.SolidColorBrush _ibLineDx;
        private SharpDX.Direct2D1.SolidColorBrush _stackedBuyZoneDx;
        private SharpDX.Direct2D1.SolidColorBrush _stackedSellZoneDx;
        private SharpDX.Direct2D1.SolidColorBrush _unfinishedLineDx;
        private SharpDX.Direct2D1.SolidColorBrush _bullColumnFillDx;
        private SharpDX.Direct2D1.SolidColorBrush _bearColumnFillDx;
        private SharpDX.Direct2D1.SolidColorBrush _largeLotDotDx;
        private SharpDX.Direct2D1.SolidColorBrush _volumeClimaxDx;

        // session reset tracking
        private DateTime _lastSessionDate = DateTime.MinValue;
        private int _sessionBarCount;

        // ---- Phase 18: Confluence Scorer (indicator-side registry + shared state) ----
        // Registry and session run independently of DEEP6Strategy's registry instance.
        // DEEP6Strategy reads results via ScorerSharedState.Latest() (Wave 3 wires entry gating).
        private DetectorRegistry _scorerRegistry;
        private SessionContext   _scorerSession;
        // Latches the most recent ScorerResult so OnRender can read it without re-scoring.
        // Updated once per bar close in OnBarUpdate; read every frame in OnRender.
        // `volatile` ensures the render thread sees writes from the data thread without
        // needing a memory barrier. Reference reads on x64 are atomic; volatile prevents
        // CPU/JIT re-ordering across the read. Matches the pattern used for `_gexProfile`.
        private volatile ScorerResult _lastScorerResult;
        private volatile ScorerResult _activeTradeSetup;
        // Bar index when the latest signal was scored. Used to expire stale armed signals
        // so the MC ACTIVE SIGNAL section + TIER 1 chart overlay only show recent ones.
        private int _armedSignalBarIndex = -1;
        private int _activeSetupBarIndex = -1;
        private double _activeInvalidationPrice = double.NaN;

        // ---- Profile Anchor Levels ----
        private ProfileAnchorLevels _profileAnchors = new ProfileAnchorLevels();
        private DateTime _profileSessionDate = DateTime.MinValue;

        // SharpDX brushes (device-dependent)
        private SharpDX.Direct2D1.Brush _bidDx, _askDx, _textDx, _imbalBuyDx, _imbalSellDx,
                                         _pocDx, _vahDx, _valDx, _gridDx,
                                         _wallBidDx, _wallAskDx;

        // Candle direction outline: green up / red down
        private SharpDX.Direct2D1.SolidColorBrush _candleUpDx, _candleDownDx;
        // Volume-intensity gradient fill (opacity scaled by normVol per cell)
        private SharpDX.Direct2D1.SolidColorBrush _cellVolBuyDx, _cellVolSellDx, _cellVolNeutDx;
        // Imbalance tier fills — buy (cyan) T1/T2/T3
        private SharpDX.Direct2D1.SolidColorBrush _imbBuyT1Dx, _imbBuyT2Dx, _imbBuyT3Dx;
        // Imbalance tier fills — sell (coral) T1/T2/T3
        private SharpDX.Direct2D1.SolidColorBrush _imbSellT1Dx, _imbSellT2Dx, _imbSellT3Dx;
        // Split cell fonts: bid right-aligned, ask left-aligned
        private TextFormat _cellFontRight, _cellFontLeft;

        // Phase 18: Scorer HUD + tier marker brushes (01-COLOR-PALETTE.md tokens)
        // Allocated in OnRenderTargetChanged, disposed in DisposeDx — matches existing pattern.
        private SharpDX.Direct2D1.SolidColorBrush _scoreHudTextDx;    // #E8EAED  primary ink (score line)
        private SharpDX.Direct2D1.SolidColorBrush _scoreHudDimDx;     // #B0B6BE  secondary ink (narrative line)
        private SharpDX.Direct2D1.SolidColorBrush _scoreHudBgDx;      // #0E1014 @ 78%  HUD backdrop
        private SharpDX.Direct2D1.SolidColorBrush _scoreHudBorderDx;  // #262633  1px border
        private SharpDX.Direct2D1.SolidColorBrush _scoreTierALongDx;  // #00E676  TypeA long (saturated green)
        private SharpDX.Direct2D1.SolidColorBrush _scoreTierAShortDx; // #FF1744  TypeA short (saturated red)
        private SharpDX.Direct2D1.SolidColorBrush _scoreTierBLongDx;  // #66BB6A  TypeB long (medium green)
        private SharpDX.Direct2D1.SolidColorBrush _scoreTierBShortDx; // #EF5350  TypeB short (medium red)
        private SharpDX.Direct2D1.SolidColorBrush _scoreTierCLongDx;  // #7CB387 @ 70%  TypeC long (gray-green)
        private SharpDX.Direct2D1.SolidColorBrush _scoreTierCShortDx; // #B87C82 @ 70%  TypeC short (gray-red)
        private SharpDX.Direct2D1.SolidColorBrush _scoreNeutralDx;    // #8A929E  QUIET/DISQUALIFIED dim
        private SharpDX.Direct2D1.SolidColorBrush _scoreLabelBgDx;    // #0E1014 @ 60%  narrative label bg pill
        // HUD monospace font (12pt Consolas for score line; must be disposed with other fonts)
        private TextFormat _hudFont;
        // HUD label font (9pt Segoe UI for narrative + tier lines)
        private TextFormat _hudLabelFont;
        // Profile anchor brushes
        private SharpDX.Direct2D1.SolidColorBrush _anchorPocDx;       // #FFD23F  PD POC
        private SharpDX.Direct2D1.SolidColorBrush _anchorVaDx;        // #C8D17A  PD VAH/VAL/PDH/PDL/PDM
        private SharpDX.Direct2D1.SolidColorBrush _anchorNakedDx;     // #FFD23F @ 60%  naked POC
        private SharpDX.Direct2D1.SolidColorBrush _anchorPwPocDx;     // #E5C24A  prior-week POC
        private SharpDX.Direct2D1.SolidColorBrush _anchorCompositeDx; // #C8D17A @ 12%  composite VA band
        private StrokeStyle _dashStyle;
        private TextFormat _cellFont, _labelFont;

        // ──── F1 PITWALL palette (Aesthetic Option E) ────
        // Aerospace semantic (Boeing 787 PFD grammar)
        private SharpDX.Direct2D1.SolidColorBrush _pwAeroCyanDx;     // #00E0FF  selected/target/limit/zg
        private SharpDX.Direct2D1.SolidColorBrush _pwAeroMagentaDx;  // #FF38C8  autopilot/algo/trail/flip/exhaust
        private SharpDX.Direct2D1.SolidColorBrush _pwAeroGreenDx;    // #3DDC84  engaged/on/nominal
        private SharpDX.Direct2D1.SolidColorBrush _pwAeroAmberDx;    // #FFB300  caution/stop/walls
        private SharpDX.Direct2D1.SolidColorBrush _pwAeroRedDx;      // #FF3030  warn/stopHit
        private SharpDX.Direct2D1.SolidColorBrush _pwAeroWhiteDx;    // #F2F4F8  primary text

        // F1 sector colors (performance grading)
        private SharpDX.Direct2D1.SolidColorBrush _pwSectorPurpleDx; // #A100FF  best ever
        private SharpDX.Direct2D1.SolidColorBrush _pwSectorGreenDx;  // #3DB868  improvement/winner
        private SharpDX.Direct2D1.SolidColorBrush _pwSectorWhiteDx;  // #E8EAED  baseline
        private SharpDX.Direct2D1.SolidColorBrush _pwSectorYellowDx; // #FFD600  slower
        private SharpDX.Direct2D1.SolidColorBrush _pwSectorRedDx;    // #FF1744  loss

        // Tinted fills (lower-alpha versions for cell backgrounds)
        private SharpDX.Direct2D1.SolidColorBrush _pwAbsFillDx;      // cyan @ 22%
        private SharpDX.Direct2D1.SolidColorBrush _pwExhFillDx;      // magenta @ 22%
        private SharpDX.Direct2D1.SolidColorBrush _pwAmberFillDx;    // amber @ 18% (×3 imbal)
        private SharpDX.Direct2D1.SolidColorBrush _pwCyanFillDx;     // cyan @ 28% (×5 buy escalation)
        private SharpDX.Direct2D1.SolidColorBrush _pwMagFillDx;      // magenta @ 28% (×5 sell escalation)

        // Surfaces
        private SharpDX.Direct2D1.SolidColorBrush _pwSurface1Dx;     // #070A0E pill backdrop
        private SharpDX.Direct2D1.SolidColorBrush _pwSurface2Dx;     // #0E1218 raised
        private SharpDX.Direct2D1.SolidColorBrush _pwGridMajorDx;    // #262C36
        private SharpDX.Direct2D1.SolidColorBrush _pwGridLineDx;     // #1A1F26 @ 60%

        // Text
        private SharpDX.Direct2D1.SolidColorBrush _pwTextSecondaryDx; // #9BA3AE
        private SharpDX.Direct2D1.SolidColorBrush _pwTextTertiaryDx;  // #5A636E
        private SharpDX.Direct2D1.SolidColorBrush _pwTextHaloDx;      // #000000 @ 90% (1px outline)

        // Telemetry fonts (legacy pit-wall — still used by GEX pill labels)
        private TextFormat _pwPillValueFont;   // Consolas Bold 13pt
        private TextFormat _pwPillLabelFont;   // Segoe UI Semibold 8pt
        // ▰▰▰ MINIMALIST HUD fonts — large breathing typography, no chrome ▰▰▰
        private TextFormat _pwHudHeroFont;     // Consolas Bold 32pt — the BUY/SELL line
        private TextFormat _pwHudValueFont;    // Consolas Bold 22pt — score / tier values
        private TextFormat _pwHudLabelFont;    // Segoe UI Semibold 12pt — small caps labels

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description         = "DEEP6 Footprint V4 — signal-only variant that removes the footprint print/gray layer and keeps colored absorption levels plus signal markers.";
                Name                = "DEEP6 Footprint V4";
                Calculate           = Calculate.OnEachTick;
                IsOverlay           = true;
                DisplayInDataBox    = false;
                DrawOnPricePanel    = true;
                PaintPriceMarkers   = false;
                ScaleJustification  = ScaleJustification.Right;
                IsSuspendedWhileInactive = true;

                // Defaults tuned for the stripped signal-only view.
                ImbalanceRatio          = 3.0;
                ShowFootprintCells      = false;
                ShowAbsorptionMarkers   = true;
                ShowExhaustionMarkers   = true;
                ShowPoc                 = false;
                ShowValueArea           = false;
                AbsorbWickMinPct        = 30.0;
                ExhaustWickMinPct       = 35.0;
                CellFontSize            = 9f;
                CellColumnWidth         = 80;
                ShowLiquidityWalls      = false;
                LiquidityWallMin        = 100;
                LiquidityWallStaleSec   = 90;
                LiquidityMaxPerSide     = 4;
                ShowChartTrader         = false;

                // Disable side panels/chrome by default so only colored levels + signals remain.
                ShowMissionControl      = false;
                MissionControlWidth     = 240;
                ShowMcActiveSignal      = false;
                ShowMcStatus            = false;
                ShowMcDayPnL            = false;
                ShowMcPosition          = false;
                ShowMcSignalsList       = false;
                ShowMcActionBar         = false;

                // Keep actionable signal overlays, but suppress extra gray context labeling.
                ShowTier1Overlay        = true;
                ShowTier3Dots           = false;
                ArmedSignalValidBars    = 5;
                ShowTrendContextWarning = false;
                TrendEmaPeriod          = 20;

                // Hide HUD chrome in the stripped view.
                ShowScoreHud        = false;
                ScoreHudPaddingPx   = 12;

                ShowProfileAnchors     = false;
                ShowPriorDayLevels     = false;
                ShowNakedPocs          = false;
                ShowCompositeVA        = false;
                NakedPocMaxAgeSessions = 20;

                // Disable footprint-adjacent overlays that add visual clutter.
                ShowVWAP                  = false;
                ShowVWAPBands             = false;
                ShowInitialBalance        = false;
                ShowHeatmapMode           = false;
                ShowStackedZoneBoxes      = false;
                ShowUnfinishedAuctionLines= false;
                ShowLargeLotOverlay       = false;
                LargeLotThreshold         = 50;
                ShowBullBearColumn        = false;
                ShowVolumeClimax          = false;
                VolClimaxMultiplier       = 2.5;

                AnchorPocBrush       = MakeFrozenBrush(Color.FromRgb(0xFF, 0xD2, 0x3F));
                AnchorVaBrush        = MakeFrozenBrush(Color.FromRgb(0xC8, 0xD1, 0x7A));
                AnchorNakedBrush     = MakeFrozenBrush(Color.FromArgb(153, 0xFF, 0xD2, 0x3F)); // 60% alpha
                AnchorPwPocBrush     = MakeFrozenBrush(Color.FromRgb(0xE5, 0xC2, 0x4A));
                AnchorCompositeBrush = MakeFrozenBrush(Color.FromArgb(30, 0xC8, 0xD1, 0x7A));  // ~12% alpha

                // Palette per .planning/design/ninjatrader-chart/01-COLOR-PALETTE.md
                BidCellBrush      = MakeFrozenBrush(Color.FromRgb(0xFF, 0x6B, 0x6B));    // bid dominance
                AskCellBrush      = MakeFrozenBrush(Color.FromRgb(0x4F, 0xC3, 0xF7));    // ask dominance
                CellTextBrush     = MakeFrozenBrush(Color.FromRgb(0xE6, 0xED, 0xF3));    // primary ink
                PocBrush          = MakeFrozenBrush(Color.FromRgb(0xFF, 0xD2, 0x3F));    // POC yellow
                VahBrush          = MakeFrozenBrush(Color.FromRgb(0xC8, 0xD1, 0x7A));    // olive VA (distinct hue vs POC)
                ValBrush          = MakeFrozenBrush(Color.FromRgb(0xC8, 0xD1, 0x7A));
                ImbalanceBuyBrush = MakeFrozenBrush(Color.FromArgb(110, 0, 200, 80));
                ImbalanceSellBrush= MakeFrozenBrush(Color.FromArgb(110, 220, 40, 40));
                WallBidBrush      = MakeFrozenBrush(Color.FromArgb(220, 43, 140, 255));   // bright blue
                WallAskBrush      = MakeFrozenBrush(Color.FromArgb(220, 255, 138, 61));   // warm orange
            }
            else if (State == State.Configure)
            {
                _absCfg.AbsorbWickMin  = AbsorbWickMinPct;
                _exhCfg.ExhaustWickMin = ExhaustWickMinPct;

                // Phase 18: build indicator-side scorer registry (read-only; no risk gates).
                // Mirrors the pattern in DEEP6Strategy.OnStateChange but without strategy-specific
                // detectors that need account context.
                _scorerRegistry = new DetectorRegistry();
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Absorption.AbsorptionDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion.ExhaustionDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Imbalance.ImbalanceDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta.DeltaDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Auction.AuctionDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.VolPattern.VolPatternDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Trap.TrapDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.TrespassDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.CounterSpoofDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.IcebergDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.VPContextDetector());
                _scorerRegistry.Register(new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines.MicroProbDetector());  // LAST

                _scorerSession = new SessionContext { TickSize = TickSize > 0 ? TickSize : 0.25 };
            }
            else if (State == State.DataLoaded)
            {
                lock (_barsLock) { _bars.Clear(); }
                _finalizedBars.Clear();
                _exhDetector.ResetCooldowns();
                _atrWindow.Clear();
                _volEma        = 0.0;
                _trendEma      = 0.0;
                _trendEmaSlope = 0.0;
                _trendEmaAlpha = 2.0 / (TrendEmaPeriod + 1.0);
                _priorCvd = 0;
                _priorFinalized = null;

                _profileAnchors.Reset();
                _profileAnchors.TickSize = TickSize > 0 ? TickSize : 0.25;
                _profileAnchors.NakedPocMaxAgeSessions = NakedPocMaxAgeSessions;
                _profileSessionDate = DateTime.MinValue;

                _ctButtons = new List<TraderButton>
                {
                    new TraderButton { Label = "CELLS", Get = () => ShowFootprintCells,    Set = v => ShowFootprintCells    = v },
                    new TraderButton { Label = "POC",   Get = () => ShowPoc,               Set = v => ShowPoc               = v },
                    new TraderButton { Label = "VA",    Get = () => ShowValueArea,         Set = v => ShowValueArea         = v },
                    new TraderButton { Label = "ANCH",  Get = () => ShowProfileAnchors,    Set = v => ShowProfileAnchors    = v },
                    new TraderButton { Label = "ABS",   Get = () => ShowAbsorptionMarkers, Set = v => ShowAbsorptionMarkers = v },
                    new TraderButton { Label = "EXH",   Get = () => ShowExhaustionMarkers, Set = v => ShowExhaustionMarkers = v },
                    new TraderButton { Label = "L2",    Get = () => ShowLiquidityWalls,    Set = v => ShowLiquidityWalls    = v },
                };
            }
            else if (State == State.Terminated)
            {
                // Always attempt detach — null-conditional makes it safe even when ChartControl is gone.
                try { if (ChartControl != null) ChartControl.MouseDown -= OnChartTraderMouseDown; } catch { }
                _ctMouseWired = false;
                DisposeDx();
            }
        }

        // ---- Tick intake ----

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (State != State.Realtime && State != State.Historical) return;

            if (e.MarketDataType == MarketDataType.Bid) { _bestBid = e.Price; return; }
            if (e.MarketDataType == MarketDataType.Ask) { _bestAsk = e.Price; return; }
            if (e.MarketDataType != MarketDataType.Last) return;
            if (CurrentBar < 0) return;

            int aggressor;
            if (!double.IsNaN(_bestAsk) && e.Price >= _bestAsk) aggressor = 1;
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

                // V2: Large Lot tracking — mark levels with institutional-size single prints
                if (ShowLargeLotOverlay && (long)e.Volume >= LargeLotThreshold)
                {
                    HashSet<double> priceSet;
                    if (!_largeLotBars.TryGetValue(CurrentBar, out priceSet))
                    {
                        priceSet = new HashSet<double>();
                        _largeLotBars[CurrentBar] = priceSet;
                    }
                    priceSet.Add(e.Price);
                }
            }

            // V2: Speed of Tape — count trades per second then compute EMA
            var nowUtc = DateTime.UtcNow;
            if (_tapeSecondWindow == DateTime.MinValue) _tapeSecondWindow = nowUtc;
            if ((nowUtc - _tapeSecondWindow).TotalSeconds >= 1.0)
            {
                double speed = _tradeCountThisSecond;
                _smoothedTapeSpeed = _smoothedTapeSpeed == 0.0
                    ? speed
                    : _smoothedTapeSpeed * 0.7 + speed * 0.3;
                _tapeSpeedSamples++;
                _sessionAvgTapeSpeed = _tapeSpeedSamples == 1
                    ? _smoothedTapeSpeed
                    : _sessionAvgTapeSpeed + (_smoothedTapeSpeed - _sessionAvgTapeSpeed) / _tapeSpeedSamples;
                _tradeCountThisSecond = 0;
                _tapeSecondWindow = nowUtc;
            }
            _tradeCountThisSecond++;
        }

        // ---- L2 depth intake — populates _l2Bids / _l2Asks for Liquidity Wall detection ----

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (!ShowLiquidityWalls) return;
            if (e.Position >= 10) return;   // only top 10 ladder rungs

            Dictionary<double, L2LevelState> dict;
            if (e.MarketDataType == MarketDataType.Bid) dict = _l2Bids;
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
                // Iceberg detection: counted when level was hit hard then refilled to >50% of historical max.
                if (st.MaxSize > 0 && st.CurrentSize < st.MaxSize * 0.5 && newSize >= st.MaxSize * 0.5)
                    st.RefillCount++;
                st.CurrentSize = newSize;
                if (newSize > st.MaxSize) st.MaxSize = newSize;
                st.LastUpdate = DateTime.UtcNow;

                // Periodic prune of stale entries (price levels no longer active).
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

        // WPF brushes created off the UI thread (NT8 calls SetDefaults / OnRenderTargetChanged
        // from worker threads) throw InvalidOperationException unless frozen. Always construct via this helper.
        private static SolidColorBrush MakeFrozenBrush(Color c)
        {
            var b = new SolidColorBrush(c);
            if (b.CanFreeze) b.Freeze();
            return b;
        }

        // ---- Bar lifecycle ----

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;
            if (CurrentBar < 2) return;

            if (!IsFirstTickOfBar) return;

            int prevIdx = CurrentBar - 1;
            FootprintBar prev;
            lock (_barsLock)
            {
                _bars.TryGetValue(prevIdx, out prev);
            }
            if (prev == null) return;

            DateTime currentSessionDate = Bars.GetTime(CurrentBar).Date;
            bool isNewSessionBar = Bars.IsFirstBarOfSession;
            if (_lastSessionDate == DateTime.MinValue)
            {
                _lastSessionDate = currentSessionDate;
                _sessionBarCount = 0;
                if (_scorerSession != null) _scorerSession.ResetSession();
                if (_scorerRegistry != null) _scorerRegistry.ResetAll();
            }

            // Reconcile OHLC with NT8's authoritative bar (handles silent-tick edge case).
            prev.Open = Bars.GetOpen(prevIdx);
            prev.High = Bars.GetHigh(prevIdx);
            prev.Low  = Bars.GetLow(prevIdx);
            prev.Close= Bars.GetClose(prevIdx);
            // Fix 9: guard against double-Finalize on historical replay (bar can re-enter OnBarUpdate).
            if (!_finalizedBars.Contains(prevIdx))
            {
                prev.Finalize(_priorCvd);
                _finalizedBars.Add(prevIdx);
            }
            _priorCvd = prev.Cvd;

            // Update rolling ATR / vol EMA
            _atrWindow.Enqueue(prev.BarRange);
            while (_atrWindow.Count > AtrPeriod) _atrWindow.Dequeue();
            double sum = 0; foreach (var v in _atrWindow) sum += v;
            _atr = _atrWindow.Count == 0 ? 1.0 : Math.Max(sum / _atrWindow.Count, 0.25);
            _volEma = _volEma == 0 ? prev.TotalVol : _volEma + VolEmaAlpha * (prev.TotalVol - _volEma);
            if (_trendEma == 0.0) _trendEma = prev.Close;
            else { double n = _trendEma + _trendEmaAlpha * (prev.Close - _trendEma); _trendEmaSlope = n - _trendEma; _trendEma = n; }

            AdvanceVersionTwoLifecycle(prevIdx, prev);

            // ── V2 per-bar computations (after finalization + scoring) ─────────────
            ComputeV2Bar(prev, prevIdx);

            // Count finalized bars within the active session of the bar being scored.
            if (!isNewSessionBar)
                _sessionBarCount++;

            // Feed profile anchor aggregator — session boundary before bar accumulation.
            {
                DateTime barTimeEt = Bars.GetTime(prevIdx);
                DateTime prevBarDate = barTimeEt.Date;
                if (_profileSessionDate == DateTime.MinValue)
                    _profileSessionDate = prevBarDate;
                if (prevBarDate != _profileSessionDate)
                {
                    _profileAnchors.OnSessionBoundary(prevBarDate);
                    _profileSessionDate = prevBarDate;
                }
                _profileAnchors.OnBarClose(prev, barTimeEt);
            }

            // Compute VAH/VAL for this bar (used by absorption VA bonus).
            var va = FootprintBar.ComputeValueArea(prev, TickSize);

            // Run detectors.
            if (ShowAbsorptionMarkers)
            {
                var abs = AbsorptionDetector.Detect(prev, _atr, _volEma, _absCfg, va.vah, va.val, TickSize);
                for (int i = 0; i < abs.Count; i++) DrawAbsorptionMarker(prevIdx, abs[i]);
            }

            var truePriorBar = _priorFinalized;
            if (ShowExhaustionMarkers)
            {
                var exh = _exhDetector.Detect(prev, truePriorBar, prevIdx, _atr, _exhCfg);
                for (int i = 0; i < exh.Count; i++) DrawExhaustionMarker(prevIdx, exh[i]);
            }

            // ── Phase 18: Confluence Scorer invocation (once per bar close) ──────────────────
            // Runs after all legacy detectors so their output is fully written to prev.
            if (_scorerRegistry != null && _scorerSession != null)
            {
                _scorerSession.Atr20         = _atr;
                _scorerSession.VolEma20      = _volEma;
                _scorerSession.TickSize      = TickSize;
                _scorerSession.Vah           = va.vah;
                _scorerSession.Val           = va.val;
                _scorerSession.PriorBar      = truePriorBar;
                _scorerSession.BarsSinceOpen = _sessionBarCount;

                if (_atr > 0.0)
                {
                    _scorerSession.SessionAtrSamples++;
                    _scorerSession.SessionAvgAtr = _scorerSession.SessionAvgAtr
                        + (_atr - _scorerSession.SessionAvgAtr) / _scorerSession.SessionAtrSamples;
                }

                var signals = _scorerRegistry.EvaluateBar(prev, _scorerSession);

                // P0-1: Compute zoneScore from ProfileAnchorLevels snapshot.
                var _zoneSnap = _profileAnchors.BuildSnapshot();
                double _zoneScore = ZoneScoreCalculator.Compute(prev.Close, _zoneSnap, TickSize);

                var scored = ConfluenceScorer.Score(
                    signals,
                    _scorerSession.BarsSinceOpen,
                    prev.BarDelta,
                    prev.Close,
                    zoneScore:        _zoneScore,
                    zoneDistTicks:    double.MaxValue,
                    tickSize:         TickSize,
                    gexAbsMult:       1.0,
                    gexMomentumMult:  1.0,
                    gexNearWallBonus: 0.0,
                    vpinModifier:     1.0);

                scored.Signals = signals;
                ApplyVersionTwoSetupMetadata(scored, prevIdx, prev.Close);

                if (scored.SetupState == TradeSetupState.Setup || scored.SetupState == TradeSetupState.Armed)
                    RegisterVersionTwoSetup(scored, prevIdx);
                else if (_activeTradeSetup == null)
                    _lastScorerResult = scored;

                ScorerSharedState.Publish(Instrument.FullName, CurrentBar, scored, _scorerSession.SessionAvgAtr);
                DrawScorerTierMarker(prevIdx, scored);
            }
            // ────────────────────────────────────────────────────────────────────────────────

            _priorFinalized = prev;
            if (_scorerSession != null)
                _scorerSession.PriorBar = prev;

            // Session reset for the newly opened session happens AFTER scoring the previous bar.
            if (isNewSessionBar)
            {
                _exhDetector.ResetCooldowns();
                _lastSessionDate = currentSessionDate;
                _sessionBarCount = 0;
                _armedSignalBarIndex = -1;
                _activeSetupBarIndex = -1;
                _activeInvalidationPrice = double.NaN;
                _activeTradeSetup = null;
                if (_scorerSession != null) _scorerSession.ResetSession();
                if (_scorerRegistry != null) _scorerRegistry.ResetAll();

                // V2 session reset
                _vwapNumerator   = 0; _vwapDenominator = 0; _vwapVariance = 0;
                _vwapPrice = 0; _vwap1SigHigh = 0; _vwap1SigLow = 0; _vwap2SigHigh = 0; _vwap2SigLow = 0;
                _ibHigh = double.MinValue; _ibLow = double.MaxValue; _ibConfirmed = false;
                _unfinishedAuctions.Clear();
                _smoothedTapeSpeed = 0; _sessionAvgTapeSpeed = 0; _tapeSpeedSamples = 0; _tradeCountThisSecond = 0;
                _nBarHighs.Clear(); _nBarLows.Clear();
                if (_profileSessionDate != currentSessionDate)
                {
                    _profileAnchors.OnSessionBoundary(currentSessionDate);
                    _profileSessionDate = currentSessionDate;
                }
            }

            // Trim history.
            int cutoff = CurrentBar - 500;
            if (cutoff > 0)
            {
                lock (_barsLock)
                {
                    var stale = _bars.Keys.Where(k => k < cutoff).ToList();
                    foreach (var k in stale) _bars.Remove(k);
                    // V2 dictionaries use the same cutoff
                    var v2stale = new List<int>();
                    foreach (var k in _barColumnType.Keys)   if (k < cutoff) v2stale.Add(k);
                    foreach (var k in v2stale)
                    {
                        _barColumnType.Remove(k);
                        _stackedZones.Remove(k);
                        _largeLotBars.Remove(k);
                        _volumeClimaxBars.Remove(k);
                    }
                }
                _finalizedBars.RemoveWhere(k => k < cutoff);
            }

        }

        private void ApplyVersionTwoSetupMetadata(ScorerResult scored, int signalBarIdx, double barClose)
        {
            if (scored == null) return;

            scored.Confidence = scored.TotalScore;
            scored.LinkedLevelKind = null;
            scored.LinkedLevelPrice = 0.0;
            scored.LinkedLevelDistanceTicks = double.MaxValue;
            scored.ExpireAfterBarIndex = signalBarIdx + System.Math.Max(1, ArmedSignalValidBars);
            scored.TriggerBarIndex = -1;

            if (scored.Tier == SignalTier.DISQUALIFIED || scored.Tier == SignalTier.QUIET || scored.Direction == 0)
            {
                scored.SetupState = TradeSetupState.Invalid;
                return;
            }

            var gex = GexSharedState.Latest(Instrument != null ? Instrument.FullName : null);
            MappedGexLevel linked = SelectLinkedGexLevel(gex, barClose, scored.Direction);
            if (linked != null)
            {
                scored.LinkedLevelKind = linked.Kind;
                scored.LinkedLevelPrice = linked.NqPrice;
                scored.LinkedLevelDistanceTicks = TickSize > 0
                    ? System.Math.Abs(linked.NqPrice - barClose) / TickSize
                    : System.Math.Abs(linked.NqPrice - barClose);
            }

            bool hasDirectionalConfluence = linked != null && scored.LinkedLevelDistanceTicks <= 8.0;
            scored.SetupState = hasDirectionalConfluence ? TradeSetupState.Armed : TradeSetupState.Setup;
            _armedSignalBarIndex = hasDirectionalConfluence ? signalBarIdx : -1;
        }

        private void RegisterVersionTwoSetup(ScorerResult scored, int signalBarIdx)
        {
            if (scored == null) return;

            _activeTradeSetup = scored;
            _activeSetupBarIndex = signalBarIdx;
            _activeInvalidationPrice = ComputeVersionTwoInvalidationPrice(scored);
            _lastScorerResult = scored;
        }

        private void AdvanceVersionTwoLifecycle(int barIdx, FootprintBar closedBar)
        {
            var active = _activeTradeSetup;
            if (active == null || closedBar == null) return;
            if (barIdx <= _activeSetupBarIndex) return;
            if (active.SetupState == TradeSetupState.Invalid || active.SetupState == TradeSetupState.Expired || active.SetupState == TradeSetupState.Triggered)
                return;

            if (barIdx > active.ExpireAfterBarIndex)
            {
                active.SetupState = TradeSetupState.Expired;
                _armedSignalBarIndex = -1;
                _lastScorerResult = active;
                return;
            }

            bool isLong = active.Direction > 0;
            if (!double.IsNaN(_activeInvalidationPrice))
            {
                bool invalidated = isLong ? closedBar.Low <= _activeInvalidationPrice : closedBar.High >= _activeInvalidationPrice;
                if (invalidated)
                {
                    active.SetupState = TradeSetupState.Invalid;
                    _armedSignalBarIndex = -1;
                    _lastScorerResult = active;
                    return;
                }
            }

            if (active.SetupState != TradeSetupState.Armed)
            {
                _lastScorerResult = active;
                return;
            }

            bool triggered = isLong
                ? closedBar.Close > active.EntryPrice && closedBar.Close >= closedBar.Open
                : closedBar.Close < active.EntryPrice && closedBar.Close <= closedBar.Open;

            if (!triggered)
            {
                _lastScorerResult = active;
                return;
            }

            active.SetupState = TradeSetupState.Triggered;
            active.TriggerBarIndex = barIdx;
            _armedSignalBarIndex = barIdx;
            _lastScorerResult = active;
            DrawTriggeredMarker(barIdx, closedBar.Close, isLong);
        }

        private double ComputeVersionTwoInvalidationPrice(ScorerResult scored)
        {
            if (scored == null) return double.NaN;
            double ticks = scored.SetupState == TradeSetupState.Armed ? 8.0 : 6.0;
            if (TickSize <= 0) return scored.EntryPrice;
            return scored.Direction > 0
                ? scored.EntryPrice - ticks * TickSize
                : scored.EntryPrice + ticks * TickSize;
        }

        private void DrawTriggeredMarker(int barIdx, double price, bool isLong)
        {
            int barsAgo = CurrentBar - barIdx;
            if (barsAgo < 0) return;

            string suffix = (isLong ? "LONG" : "SHORT") + "_" + barIdx;
            Brush pick = isLong
                ? MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xE6, 0x76))
                : MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x17, 0x44));

            if (isLong)
                Draw.ArrowUp(this, "V2_TRIGGER_" + suffix, false, barsAgo, price - 6.0 * TickSize, pick);
            else
                Draw.ArrowDown(this, "V2_TRIGGER_" + suffix, false, barsAgo, price + 6.0 * TickSize, pick);

            Draw.Text(this, "V2_TRIGGER_LBL_" + suffix, isLong ? "TRIGGER LONG" : "TRIGGER SHORT",
                barsAgo, price + (isLong ? -11.0 : 11.0) * TickSize, pick);
        }

        private static MappedGexLevel SelectLinkedGexLevel(GexContextSnapshot gex, double price, int direction)
        {
            if (gex == null || gex.Stale || gex.Levels == null || gex.Levels.Count == 0)
                return null;

            string primaryKind = direction > 0 ? "PutWall" : "CallWall";
            MappedGexLevel best = null;
            double bestDist = double.MaxValue;

            for (int i = 0; i < gex.Levels.Count; i++)
            {
                var lv = gex.Levels[i];
                if (lv == null) continue;
                double dist = System.Math.Abs(lv.NqPrice - price);
                bool isPrimary = string.Equals(lv.Kind, primaryKind, System.StringComparison.Ordinal);
                bool isFlip = string.Equals(lv.Kind, "GammaFlip", System.StringComparison.Ordinal);
                bool isSecondary = string.Equals(lv.Kind, "MajorPositive", System.StringComparison.Ordinal)
                    || string.Equals(lv.Kind, "MajorNegative", System.StringComparison.Ordinal);
                if (!isPrimary && !isFlip && !isSecondary) continue;

                double rankDist = dist;
                if (isPrimary) rankDist -= 1000000.0;
                else if (isFlip) rankDist -= 500000.0;

                if (rankDist < bestDist)
                {
                    bestDist = rankDist;
                    best = lv;
                }
            }

            return best;
        }

        private void DrawAbsorptionMarker(int barIdx, AbsorptionSignal s)
        {
            string tag = string.Format("ABS_{0}_{1}_{2}", barIdx, (int)s.Kind, s.Wick);
            Brush brush = s.Direction >= 0 ? Brushes.Cyan : Brushes.Magenta;
            int barsAgo = CurrentBar - barIdx;
            if (s.Direction >= 0)
                Draw.TriangleUp(this, tag, false, barsAgo, s.Price - 4 * TickSize, brush);
            else
                Draw.TriangleDown(this, tag, false, barsAgo, s.Price + 4 * TickSize, brush);
            Draw.Text(this, tag + "_lbl", s.Kind.ToString().Substring(0, Math.Min(3, s.Kind.ToString().Length)).ToUpper(),
                      barsAgo, s.Price + (s.Direction >= 0 ? -8 : 8) * TickSize, brush);
        }

        private void DrawExhaustionMarker(int barIdx, ExhaustionSignal s)
        {
            string tag = string.Format("EXH_{0}_{1}", barIdx, (int)s.Kind);
            Brush brush;
            if (s.Direction > 0) brush = Brushes.Yellow;
            else if (s.Direction < 0) brush = Brushes.OrangeRed;
            else brush = Brushes.Gold;
            int barsAgo = CurrentBar - barIdx;
            if (s.Direction > 0)
                Draw.ArrowUp(this, tag, false, barsAgo, s.Price - 5 * TickSize, brush);
            else if (s.Direction < 0)
                Draw.ArrowDown(this, tag, false, barsAgo, s.Price + 5 * TickSize, brush);
            else
            {
                Draw.Diamond(this, tag, false, barsAgo, s.Price, brush);
                string strText = string.Format("{0:0}%", s.Strength * 100.0);
                Draw.Text(this, tag + "_str", false, strText, barsAgo, s.Price, 0,
                    Brushes.White, new SimpleFont("Arial", 9) { Bold = true },
                    System.Windows.TextAlignment.Center, null, null, 0);
            }
        }

        // ---- Custom render ----

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            _bidDx        = BidCellBrush.ToDxBrush(RenderTarget);
            _askDx        = AskCellBrush.ToDxBrush(RenderTarget);
            _textDx       = CellTextBrush.ToDxBrush(RenderTarget);
            _imbalBuyDx   = ImbalanceBuyBrush.ToDxBrush(RenderTarget);
            _imbalSellDx  = ImbalanceSellBrush.ToDxBrush(RenderTarget);
            _pocDx        = PocBrush.ToDxBrush(RenderTarget);
            _vahDx        = VahBrush.ToDxBrush(RenderTarget);
            _valDx        = ValBrush.ToDxBrush(RenderTarget);
            _gridDx       = MakeFrozenBrush(Color.FromArgb(40, 200, 200, 200)).ToDxBrush(RenderTarget);
            _wallBidDx    = WallBidBrush.ToDxBrush(RenderTarget);
            _wallAskDx    = WallAskBrush.ToDxBrush(RenderTarget);

            // Profile anchor brushes
            _anchorPocDx       = (SharpDX.Direct2D1.SolidColorBrush)AnchorPocBrush.ToDxBrush(RenderTarget);
            _anchorVaDx        = (SharpDX.Direct2D1.SolidColorBrush)AnchorVaBrush.ToDxBrush(RenderTarget);
            _anchorNakedDx     = (SharpDX.Direct2D1.SolidColorBrush)AnchorNakedBrush.ToDxBrush(RenderTarget);
            _anchorPwPocDx     = (SharpDX.Direct2D1.SolidColorBrush)AnchorPwPocBrush.ToDxBrush(RenderTarget);
            _anchorCompositeDx = (SharpDX.Direct2D1.SolidColorBrush)AnchorCompositeBrush.ToDxBrush(RenderTarget);
            if (_dashStyle != null) { _dashStyle.Dispose(); _dashStyle = null; }
            _dashStyle = new StrokeStyle(NinjaTrader.Core.Globals.D2DFactory,
                new StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Dash });
            _ctOnDx       = MakeFrozenBrush(Color.FromArgb(220, 50, 130, 75)).ToDxBrush(RenderTarget);
            _ctOffDx      = MakeFrozenBrush(Color.FromArgb(220, 35, 40, 50)).ToDxBrush(RenderTarget);
            _ctBorderDx   = MakeFrozenBrush(Color.FromArgb(255, 90, 100, 115)).ToDxBrush(RenderTarget);

            // Phase 18: Scorer HUD brushes — palette from 01-COLOR-PALETTE.md + FOOTPRINT-VISUAL-SPEC.md
            _scoreHudTextDx    = MakeFrozenBrush(Color.FromArgb(255, 0xE8, 0xEA, 0xED)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _scoreHudDimDx     = MakeFrozenBrush(Color.FromArgb(255, 0xB0, 0xB6, 0xBE)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _scoreHudBgDx      = MakeFrozenBrush(Color.FromArgb(199, 0x0E, 0x10, 0x14)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // ~78% alpha
            _scoreHudBorderDx  = MakeFrozenBrush(Color.FromArgb(255, 0x26, 0x26, 0x33)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _scoreTierALongDx  = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xE6, 0x76)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // tierA-long #00E676
            _scoreTierAShortDx = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x17, 0x44)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // tierA-short #FF1744
            _scoreTierBLongDx  = MakeFrozenBrush(Color.FromArgb(255, 0x66, 0xBB, 0x6A)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // tierB-long #66BB6A
            _scoreTierBShortDx = MakeFrozenBrush(Color.FromArgb(255, 0xEF, 0x53, 0x50)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // tierB-short #EF5350
            _scoreTierCLongDx  = MakeFrozenBrush(Color.FromArgb(178, 0x7C, 0xB3, 0x87)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // tierC-long  #7CB387 @70%
            _scoreTierCShortDx = MakeFrozenBrush(Color.FromArgb(178, 0xB8, 0x7C, 0x82)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // tierC-short #B87C82 @70%
            _scoreNeutralDx    = MakeFrozenBrush(Color.FromArgb(255, 0x8A, 0x92, 0x9E)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // axis.text #8A929E
            _scoreLabelBgDx    = MakeFrozenBrush(Color.FromArgb(153, 0x0E, 0x10, 0x14)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;  // hud-bg @60%

            // ──── F1 PITWALL palette (Aesthetic Option E) ────
            // Aerospace semantic (Boeing 787 PFD grammar)
            _pwAeroCyanDx     = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwAeroMagentaDx  = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x38, 0xC8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwAeroGreenDx    = MakeFrozenBrush(Color.FromArgb(255, 0x3D, 0xDC, 0x84)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwAeroAmberDx    = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0xB3, 0x00)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwAeroRedDx      = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x30, 0x30)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwAeroWhiteDx    = MakeFrozenBrush(Color.FromArgb(255, 0xF2, 0xF4, 0xF8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

            // F1 sector colors (performance grading)
            _pwSectorPurpleDx = MakeFrozenBrush(Color.FromArgb(255, 0xA1, 0x00, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwSectorGreenDx  = MakeFrozenBrush(Color.FromArgb(255, 0x3D, 0xB8, 0x68)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwSectorWhiteDx  = MakeFrozenBrush(Color.FromArgb(255, 0xE8, 0xEA, 0xED)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwSectorYellowDx = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0xD6, 0x00)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwSectorRedDx    = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x17, 0x44)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

            // Tinted fills for cell backgrounds (alpha-encoded)
            _pwAbsFillDx     = MakeFrozenBrush(Color.FromArgb(56,  0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwExhFillDx     = MakeFrozenBrush(Color.FromArgb(56,  0xFF, 0x38, 0xC8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwAmberFillDx   = MakeFrozenBrush(Color.FromArgb(46,  0xFF, 0xB3, 0x00)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwCyanFillDx    = MakeFrozenBrush(Color.FromArgb(71,  0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwMagFillDx     = MakeFrozenBrush(Color.FromArgb(71,  0xFF, 0x38, 0xC8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

            // Surfaces / chrome
            _pwSurface1Dx     = MakeFrozenBrush(Color.FromArgb(255, 0x07, 0x0A, 0x0E)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwSurface2Dx     = MakeFrozenBrush(Color.FromArgb(230, 0x0E, 0x12, 0x18)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwGridMajorDx    = MakeFrozenBrush(Color.FromArgb(255, 0x26, 0x2C, 0x36)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwGridLineDx     = MakeFrozenBrush(Color.FromArgb(153, 0x1A, 0x1F, 0x26)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

            // Text tokens
            _pwTextSecondaryDx = MakeFrozenBrush(Color.FromArgb(255, 0x9B, 0xA3, 0xAE)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwTextTertiaryDx  = MakeFrozenBrush(Color.FromArgb(255, 0x5A, 0x63, 0x6E)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _pwTextHaloDx      = MakeFrozenBrush(Color.FromArgb(230, 0x00, 0x00, 0x00)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

            // Candle direction outlines
            _candleUpDx   = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xA1, 0x52)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _candleDownDx = MakeFrozenBrush(Color.FromArgb(255, 0xC4, 0x00, 0x1D)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            // Volume gradient fills — base hue, opacity driven per-cell
            _cellVolBuyDx  = MakeFrozenBrush(Color.FromArgb(20,  0x4F, 0xC3, 0xF7)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _cellVolSellDx = MakeFrozenBrush(Color.FromArgb(20,  0xFF, 0x6B, 0x6B)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _cellVolNeutDx = MakeFrozenBrush(Color.FromArgb(20,  0x9B, 0xA3, 0xAE)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            // Imbalance tier fills — buy (cyan)
            _imbBuyT1Dx = MakeFrozenBrush(Color.FromArgb(40,  0x4F, 0xC3, 0xF7)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _imbBuyT2Dx = MakeFrozenBrush(Color.FromArgb(90,  0x4F, 0xC3, 0xF7)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _imbBuyT3Dx = MakeFrozenBrush(Color.FromArgb(150, 0x00, 0xE5, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            // Imbalance tier fills — sell (coral)
            _imbSellT1Dx = MakeFrozenBrush(Color.FromArgb(40,  0xFF, 0x6B, 0x6B)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _imbSellT2Dx = MakeFrozenBrush(Color.FromArgb(90,  0xFF, 0x6B, 0x6B)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _imbSellT3Dx = MakeFrozenBrush(Color.FromArgb(150, 0xFF, 0x33, 0x55)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            // Split cell fonts
            if (_cellFontRight != null) { _cellFontRight.Dispose(); _cellFontRight = null; }
            if (_cellFontLeft  != null) { _cellFontLeft.Dispose();  _cellFontLeft  = null; }
            _cellFontRight = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", CellFontSize)
                { TextAlignment = TextAlignment.Trailing, ParagraphAlignment = ParagraphAlignment.Center };
            _cellFontLeft  = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", CellFontSize)
                { TextAlignment = TextAlignment.Leading,  ParagraphAlignment = ParagraphAlignment.Center };

            // Telemetry fonts (Consolas mono for tabular numerals; Segoe UI Semibold for chrome)
            _pwPillValueFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                "Consolas", FontWeight.Bold, FontStyle.Normal, 13f)
            {
                TextAlignment      = TextAlignment.Leading,
                ParagraphAlignment = ParagraphAlignment.Center
            };
            _pwPillLabelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                "Segoe UI", FontWeight.Bold, FontStyle.Normal, 8f)
            {
                TextAlignment      = TextAlignment.Leading,
                ParagraphAlignment = ParagraphAlignment.Center
            };

            // ▰▰▰ MINIMALIST HUD fonts — large breathing typography, no chrome ▰▰▰
            _pwHudHeroFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                "Consolas", FontWeight.Bold, FontStyle.Normal, 32f)
            {
                TextAlignment      = TextAlignment.Leading,
                ParagraphAlignment = ParagraphAlignment.Center
            };
            _pwHudValueFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                "Consolas", FontWeight.Bold, FontStyle.Normal, 22f)
            {
                TextAlignment      = TextAlignment.Leading,
                ParagraphAlignment = ParagraphAlignment.Center
            };
            _pwHudLabelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                "Segoe UI", FontWeight.Bold, FontStyle.Normal, 12f)
            {
                TextAlignment      = TextAlignment.Leading,
                ParagraphAlignment = ParagraphAlignment.Center
            };

            // HUD fonts — Consolas 12pt for score (monospace), Segoe UI 9pt for narrative/tier
            _hudFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 12f)
            {
                TextAlignment      = TextAlignment.Leading,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
            _hudLabelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 9f)
            {
                TextAlignment      = TextAlignment.Leading,
                ParagraphAlignment = ParagraphAlignment.Center,
            };

            // ──── V2 Feature Brushes ────────────────────────────────────────────────────
            _vwapLineDx        = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0xFF, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _vwapBand1Dx       = MakeFrozenBrush(Color.FromArgb(100, 0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _vwapBand2Dx       = MakeFrozenBrush(Color.FromArgb(45,  0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _ibLineDx          = MakeFrozenBrush(Color.FromArgb(230, 0xFF, 0x95, 0x00)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _stackedBuyZoneDx  = MakeFrozenBrush(Color.FromArgb(180, 0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _stackedSellZoneDx = MakeFrozenBrush(Color.FromArgb(180, 0xFF, 0x38, 0xC8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _unfinishedLineDx  = MakeFrozenBrush(Color.FromArgb(140, 0xFF, 0xD2, 0x3F)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _bullColumnFillDx  = MakeFrozenBrush(Color.FromArgb(18,  0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _bearColumnFillDx  = MakeFrozenBrush(Color.FromArgb(18,  0xFF, 0x38, 0xC8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _largeLotDotDx     = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0xFF, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            _volumeClimaxDx    = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0xD6, 0x00)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

            // Heatmap palette: 16 amber intensity steps (dim → fully opaque)
            for (int hi = 0; hi < HeatmapSteps; hi++)
            {
                byte a = (byte)(10 + hi * 14); // alpha 10 at index 0 → 220 at index 15
                if (_heatmapPalette[hi] != null) { _heatmapPalette[hi].Dispose(); _heatmapPalette[hi] = null; }
                _heatmapPalette[hi] = MakeFrozenBrush(Color.FromArgb(a, 0xFF, 0xB3, 0x00))
                    .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
            }

            // Wire mouse handler once a render target exists (ChartControl is non-null here).
            if (!_ctMouseWired && ChartControl != null)
            {
                ChartControl.MouseDown += OnChartTraderMouseDown;
                _ctMouseWired = true;
            }

            _cellFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", CellFontSize)
            {
                TextAlignment = TextAlignment.Center,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
            _labelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 10f)
            {
                TextAlignment = TextAlignment.Trailing,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
            // Chart Trader button font — cached so RenderChartTrader doesn't allocate
            // 7 unmanaged TextFormat objects per frame at 60fps (~420 allocs/sec).
            _ctBtnFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 10f)
            {
                TextAlignment = TextAlignment.Center,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
        }

        private void DisposeDx()
        {
            DisposeBrush(ref _bidDx); DisposeBrush(ref _askDx); DisposeBrush(ref _textDx);
            DisposeBrush(ref _imbalBuyDx); DisposeBrush(ref _imbalSellDx);
            DisposeBrush(ref _pocDx); DisposeBrush(ref _vahDx); DisposeBrush(ref _valDx);
            DisposeBrush(ref _gridDx);
            DisposeBrush(ref _wallBidDx); DisposeBrush(ref _wallAskDx);
            DisposeBrush(ref _ctOnDx); DisposeBrush(ref _ctOffDx); DisposeBrush(ref _ctBorderDx);
            DisposeSolidBrush(ref _anchorPocDx); DisposeSolidBrush(ref _anchorVaDx);
            DisposeSolidBrush(ref _anchorNakedDx); DisposeSolidBrush(ref _anchorPwPocDx);
            DisposeSolidBrush(ref _anchorCompositeDx);
            if (_dashStyle != null) { _dashStyle.Dispose(); _dashStyle = null; }
            if (_cellFont != null) { _cellFont.Dispose(); _cellFont = null; }
            if (_labelFont != null) { _labelFont.Dispose(); _labelFont = null; }
            if (_ctBtnFont != null) { _ctBtnFont.Dispose(); _ctBtnFont = null; }
            if (_hudFont != null) { _hudFont.Dispose(); _hudFont = null; }
            if (_hudLabelFont != null) { _hudLabelFont.Dispose(); _hudLabelFont = null; }
            // Phase 18 scorer HUD brushes
            DisposeSolidBrush(ref _scoreHudTextDx);
            DisposeSolidBrush(ref _scoreHudDimDx);
            DisposeSolidBrush(ref _scoreHudBgDx);
            DisposeSolidBrush(ref _scoreHudBorderDx);
            DisposeSolidBrush(ref _scoreTierALongDx);
            DisposeSolidBrush(ref _scoreTierAShortDx);
            DisposeSolidBrush(ref _scoreTierBLongDx);
            DisposeSolidBrush(ref _scoreTierBShortDx);
            DisposeSolidBrush(ref _scoreTierCLongDx);
            DisposeSolidBrush(ref _scoreTierCShortDx);
            DisposeSolidBrush(ref _scoreNeutralDx);
            DisposeSolidBrush(ref _scoreLabelBgDx);

            // F1 PITWALL palette
            DisposeSolidBrush(ref _pwAeroCyanDx);
            DisposeSolidBrush(ref _pwAeroMagentaDx);
            DisposeSolidBrush(ref _pwAeroGreenDx);
            DisposeSolidBrush(ref _pwAeroAmberDx);
            DisposeSolidBrush(ref _pwAeroRedDx);
            DisposeSolidBrush(ref _pwAeroWhiteDx);
            DisposeSolidBrush(ref _pwSectorPurpleDx);
            DisposeSolidBrush(ref _pwSectorGreenDx);
            DisposeSolidBrush(ref _pwSectorWhiteDx);
            DisposeSolidBrush(ref _pwSectorYellowDx);
            DisposeSolidBrush(ref _pwSectorRedDx);
            DisposeSolidBrush(ref _pwAbsFillDx);
            DisposeSolidBrush(ref _pwExhFillDx);
            DisposeSolidBrush(ref _pwAmberFillDx);
            DisposeSolidBrush(ref _pwCyanFillDx);
            DisposeSolidBrush(ref _pwMagFillDx);
            DisposeSolidBrush(ref _pwSurface1Dx);
            DisposeSolidBrush(ref _pwSurface2Dx);
            DisposeSolidBrush(ref _pwGridMajorDx);
            DisposeSolidBrush(ref _pwGridLineDx);
            DisposeSolidBrush(ref _pwTextSecondaryDx);
            DisposeSolidBrush(ref _pwTextTertiaryDx);
            DisposeSolidBrush(ref _pwTextHaloDx);
            if (_pwPillValueFont != null) { _pwPillValueFont.Dispose(); _pwPillValueFont = null; }
            if (_pwPillLabelFont != null) { _pwPillLabelFont.Dispose(); _pwPillLabelFont = null; }
            if (_pwHudHeroFont   != null) { _pwHudHeroFont.Dispose();   _pwHudHeroFont   = null; }
            if (_pwHudValueFont  != null) { _pwHudValueFont.Dispose();  _pwHudValueFont  = null; }
            if (_pwHudLabelFont  != null) { _pwHudLabelFont.Dispose();  _pwHudLabelFont  = null; }

            // V2 brushes
            DisposeSolidBrush(ref _vwapLineDx); DisposeSolidBrush(ref _vwapBand1Dx); DisposeSolidBrush(ref _vwapBand2Dx);
            DisposeSolidBrush(ref _ibLineDx);
            DisposeSolidBrush(ref _stackedBuyZoneDx); DisposeSolidBrush(ref _stackedSellZoneDx);
            DisposeSolidBrush(ref _unfinishedLineDx);
            DisposeSolidBrush(ref _bullColumnFillDx); DisposeSolidBrush(ref _bearColumnFillDx);
            DisposeSolidBrush(ref _largeLotDotDx); DisposeSolidBrush(ref _volumeClimaxDx);
            for (int hi = 0; hi < HeatmapSteps; hi++) DisposeSolidBrush(ref _heatmapPalette[hi]);
            // New design system
            DisposeSolidBrush(ref _candleUpDx);   DisposeSolidBrush(ref _candleDownDx);
            DisposeSolidBrush(ref _cellVolBuyDx);  DisposeSolidBrush(ref _cellVolSellDx); DisposeSolidBrush(ref _cellVolNeutDx);
            DisposeSolidBrush(ref _imbBuyT1Dx);   DisposeSolidBrush(ref _imbBuyT2Dx);   DisposeSolidBrush(ref _imbBuyT3Dx);
            DisposeSolidBrush(ref _imbSellT1Dx);  DisposeSolidBrush(ref _imbSellT2Dx);  DisposeSolidBrush(ref _imbSellT3Dx);
            if (_cellFontRight != null) { _cellFontRight.Dispose(); _cellFontRight = null; }
            if (_cellFontLeft  != null) { _cellFontLeft.Dispose();  _cellFontLeft  = null; }
        }

        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush b) { if (b != null) { b.Dispose(); b = null; } }
        private static void DisposeSolidBrush(ref SharpDX.Direct2D1.SolidColorBrush b) { if (b != null) { b.Dispose(); b = null; } }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (IsInHitTest) return;
            if (RenderTarget == null || ChartBars == null) return;
            if (chartControl.Instrument == null) return;
            if (_cellFont == null) return;

            base.OnRender(chartControl, chartScale);
            RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

            double tickSize = chartControl.Instrument.MasterInstrument.TickSize;
            // Account for the Mission Control panel on the right edge (240px by default).
            // Everything chart-area renders into [ChartPanel.X, panelRight) where panelRight
            // shrinks left when the MC panel is on so we don't draw under it.
            // Mirrors the clamp in RenderMissionControl so the two stay in sync.
            float fullPanelRight = (float)(ChartPanel.X + ChartPanel.W);
            float effectiveMcW = (ShowMissionControl && ChartPanel.W >= 200)
                ? Math.Min(MissionControlWidth, Math.Max(40f, (float)ChartPanel.W - 80f))
                : 0f;
            float panelRight = fullPanelRight - effectiveMcW;

            // ▶ TIER 1 (TYPE_A) chart overlay: entry/stop/target lines + price labels.
            // Renders BEFORE cells so cells overlay on top — visual layering rule.
            if (ShowTier1Overlay) RenderTier1Overlay(chartControl, chartScale, panelRight);

            // Chart Trader toolbar (top-left, on top of cells but under entry cards)
            if (ShowChartTrader) RenderChartTrader();

            // Profile anchor levels (prior-day POC/VAH/VAL, PDH/PDL/PDM, naked POCs, prior-week POC)
            if (ShowProfileAnchors) RenderProfileAnchors(chartControl, chartScale, panelRight);

            // Liquidity Walls from Rithmic L2 — large persistent resting orders
            if (ShowLiquidityWalls)
                RenderLiquidityWalls(chartScale, panelRight);

            // ── V2 horizontal context lines (under cells) ────────────────────────────
            if (ShowVWAP && _vwapPrice > 0)
                RenderV2Vwap(chartScale, panelRight);
            if (ShowInitialBalance && _ibHigh > double.MinValue && _ibLow < double.MaxValue)
                RenderV2InitialBalance(chartScale, panelRight);
            if (ShowUnfinishedAuctionLines && _unfinishedAuctions.Count > 0)
                RenderV2UnfinishedAuctions(chartScale, panelRight);

            if (!ShowFootprintCells && !ShowPoc && !ShowValueArea) return;

            int barPaintW = chartControl.GetBarPaintWidth(ChartBars);
            int colW = Math.Max(CellColumnWidth, barPaintW);
            float rowH = (float)Math.Max(8, chartScale.GetPixelsForDistance(tickSize));

            int fromIdx = ChartBars.FromIndex;
            int toIdx = ChartBars.ToIndex;

            Dictionary<int, FootprintBar> snap;
            lock (_barsLock) { snap = new Dictionary<int, FootprintBar>(_bars); }

            for (int barIdx = fromIdx; barIdx <= toIdx; barIdx++)
            {
                FootprintBar fbar;
                if (!snap.TryGetValue(barIdx, out fbar)) continue;
                if (fbar.Levels.Count == 0) continue;

                int xCenter = chartControl.GetXByBarIndex(ChartBars, barIdx);
                float xLeft = xCenter - colW / 2f;

                long maxLevelVol = 0;
                foreach (var kv in fbar.Levels)
                {
                    long v = kv.Value.AskVol + kv.Value.BidVol;
                    if (v > maxLevelVol) maxLevelVol = v;
                }

                // V2: Bull/Bear column full-bar background tint
                if (ShowBullBearColumn)
                {
                    int colType;
                    lock (_barsLock) { _barColumnType.TryGetValue(barIdx, out colType); }
                    if (colType != 0)
                    {
                        var colFill = colType > 0 ? _bullColumnFillDx : _bearColumnFillDx;
                        if (colFill != null && fbar.High > 0 && fbar.Low > 0)
                        {
                            float yHi = chartScale.GetYByValue(fbar.High);
                            float yLo = chartScale.GetYByValue(fbar.Low);
                            RenderTarget.FillRectangle(new RectangleF(xLeft, yHi, colW, yLo - yHi), colFill);
                        }
                    }
                }

                // ── Candle direction for outline/wick color ──────────────────────
                bool isUpCandle = fbar.Close >= fbar.Open;
                var outlineBrush = isUpCandle
                    ? (_candleUpDx   ?? (SharpDX.Direct2D1.SolidColorBrush)_askDx)
                    : (_candleDownDx ?? (SharpDX.Direct2D1.SolidColorBrush)_bidDx);

                // ── Adaptive zoom mode ─────────────────────────────────────────────
                bool detailMode  = colW >= 60;
                bool compactMode = colW < 36;

                float yBarTop  = (float)chartScale.GetYByValue(fbar.High);
                float yBarBot  = (float)chartScale.GetYByValue(fbar.Low);
                float yOpen    = (float)chartScale.GetYByValue(fbar.Open);
                float yClose   = (float)chartScale.GetYByValue(fbar.Close);
                float yBodyTop = Math.Min(yOpen, yClose);
                float yBodyBot = Math.Max(yOpen, yClose);
                float xMid     = xLeft + colW / 2f;

                if (ShowFootprintCells)
                {
                    HashSet<double> largeLotSet = null;
                    if (ShowLargeLotOverlay)
                        lock (_barsLock) { _largeLotBars.TryGetValue(barIdx, out largeLotSet); }

                    foreach (var kv in fbar.Levels)
                    {
                        double px   = kv.Key;
                        var    cell = kv.Value;
                        float  yCenter = (float)chartScale.GetYByValue(px);
                        float  yTop    = yCenter - rowH / 2f;
                        var    rect    = new RectangleF(xLeft, yTop, colW, rowH);

                        // 1. VOLUME GRADIENT — subtle tint, opacity 6%→44% by cell share of bar max
                        long cellVol = cell.AskVol + cell.BidVol;
                        if (cellVol > 0 && maxLevelVol > 0)
                        {
                            float normVol   = (float)cellVol / maxLevelVol;
                            float fillAlpha = 0.06f + normVol * 0.38f;
                            long  delta     = cell.AskVol - cell.BidVol;
                            var   volBrush  = delta > 0 ? _cellVolBuyDx
                                           : delta < 0 ? _cellVolSellDx
                                           : _cellVolNeutDx;
                            if (volBrush != null)
                            {
                                volBrush.Opacity = fillAlpha;
                                RenderTarget.FillRectangle(rect, volBrush);
                                volBrush.Opacity = 1f;
                            }
                        }

                        // V2: Heatmap mode overrides gradient when enabled
                        if (ShowHeatmapMode && maxLevelVol > 0)
                        {
                            int hIdx = (int)((double)cellVol / maxLevelVol * (HeatmapSteps - 1));
                            hIdx = Math.Max(0, Math.Min(HeatmapSteps - 1, hIdx));
                            if (_heatmapPalette[hIdx] != null)
                                RenderTarget.FillRectangle(rect, _heatmapPalette[hIdx]);
                        }

                        // 2. IMBALANCE TIERS — diagonal comparison, 3 escalating levels
                        long   diagBid   = GetBid(fbar, px + tickSize);
                        long   diagAsk   = GetAsk(fbar, px - tickSize);
                        double buyRatio  = (cell.AskVol > 0 && diagBid > 0) ? (double)cell.AskVol / diagBid : 0;
                        double sellRatio = (cell.BidVol > 0 && diagAsk > 0) ? (double)cell.BidVol / diagAsk : 0;

                        SharpDX.Direct2D1.SolidColorBrush imbFill = null;
                        bool isBuyImb  = false;
                        bool isExtreme = false;
                        if      (buyRatio  >= 8.0)           { imbFill = _imbBuyT3Dx;  isBuyImb = true;  isExtreme = true; }
                        else if (buyRatio  >= 5.0)           { imbFill = _imbBuyT2Dx;  isBuyImb = true; }
                        else if (buyRatio  >= ImbalanceRatio){ imbFill = _imbBuyT1Dx;  isBuyImb = true; }
                        else if (sellRatio >= 8.0)           { imbFill = _imbSellT3Dx; isBuyImb = false; isExtreme = true; }
                        else if (sellRatio >= 5.0)           { imbFill = _imbSellT2Dx; isBuyImb = false; }
                        else if (sellRatio >= ImbalanceRatio){ imbFill = _imbSellT1Dx; isBuyImb = false; }
                        if (imbFill != null)
                            RenderTarget.FillRectangle(rect, imbFill);

                        if (isExtreme)
                        {
                            var bktBrush = isBuyImb
                                ? (SharpDX.Direct2D1.Brush)(_pwAeroCyanDx    ?? _imbBuyT3Dx)
                                : (SharpDX.Direct2D1.Brush)(_pwAeroMagentaDx ?? _imbSellT3Dx);
                            DrawCornerBrackets(rect, bktBrush, 6f, 1.5f);
                        }

                        // 3. CELL TEXT — coral bid / cyan ask in detail mode; combined grey in normal; delta in compact
                        if (rowH >= 8f)
                        {
                            if (detailMode)
                            {
                                float halfW = colW / 2f - 6f;
                                string bidStr = FmtVolV3(cell.BidVol);
                                string askStr = FmtVolV3(cell.AskVol);
                                if (_cellFontRight != null && bidStr.Length > 0)
                                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, bidStr, _cellFontRight, halfW, rowH))
                                        RenderTarget.DrawTextLayout(new Vector2(xLeft, yTop), tl,
                                            (SharpDX.Direct2D1.Brush)(_bidDx ?? _pwTextSecondaryDx));
                                if (_cellFont != null)
                                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, "×", _cellFont, 12f, rowH))
                                        RenderTarget.DrawTextLayout(new Vector2(xLeft + halfW, yTop), tl,
                                            (SharpDX.Direct2D1.Brush)(_pwTextTertiaryDx ?? _pwTextSecondaryDx));
                                if (_cellFontLeft != null && askStr.Length > 0)
                                    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, askStr, _cellFontLeft, halfW, rowH))
                                        RenderTarget.DrawTextLayout(new Vector2(xLeft + halfW + 12f, yTop), tl,
                                            (SharpDX.Direct2D1.Brush)(_askDx ?? _pwTextSecondaryDx));
                            }
                            else if (!compactMode)
                            {
                                string lbl = string.Format("{0,4}×{1,-4}", FmtVolV3(cell.BidVol), FmtVolV3(cell.AskVol));
                                var ink = isExtreme
                                    ? (SharpDX.Direct2D1.Brush)(_pwAeroWhiteDx ?? _pwTextSecondaryDx)
                                    : (SharpDX.Direct2D1.Brush)(_pwTextSecondaryDx ?? _textDx);
                                using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, lbl, _cellFont, colW, rowH))
                                    RenderTarget.DrawTextLayout(new Vector2(xLeft, yTop), tl, ink);
                            }
                            else
                            {
                                long   d  = cell.AskVol - cell.BidVol;
                                string ds = (d >= 0 ? "+" : "") + d;
                                var ink = d >= 0
                                    ? (SharpDX.Direct2D1.Brush)(_askDx ?? _pwTextSecondaryDx)
                                    : (SharpDX.Direct2D1.Brush)(_bidDx ?? _pwTextSecondaryDx);
                                using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, ds, _cellFont, colW, rowH))
                                    RenderTarget.DrawTextLayout(new Vector2(xLeft, yTop), tl, ink);
                            }
                        }

                        // V2: Large Lot dot — white square at left edge of cell
                        if (largeLotSet != null && largeLotSet.Contains(px) && _largeLotDotDx != null)
                            RenderTarget.FillRectangle(new RectangleF(xLeft, yCenter - 2.5f, 5f, 5f), _largeLotDotDx);
                    }
                }

                // ── Candle body outline (green=up / red=down), drawn ON TOP of cells ──
                if (outlineBrush != null)
                {
                    float bodyH = Math.Max(2f, yBodyBot - yBodyTop);
                    RenderTarget.DrawRectangle(new RectangleF(xLeft, yBodyTop, colW, bodyH), outlineBrush, 1.5f);
                    RenderTarget.DrawLine(new Vector2(xLeft - 3f, yOpen),  new Vector2(xLeft + 5f, yOpen),  outlineBrush, 1.5f);
                    RenderTarget.DrawLine(new Vector2(xLeft + colW - 5f, yClose), new Vector2(xLeft + colW + 3f, yClose), outlineBrush, 1.5f);
                    if (yBarTop < yBodyTop - 1f)
                        RenderTarget.DrawLine(new Vector2(xMid, yBarTop), new Vector2(xMid, yBodyTop), outlineBrush, 1f);
                    if (yBarBot > yBodyBot + 1f)
                        RenderTarget.DrawLine(new Vector2(xMid, yBodyBot), new Vector2(xMid, yBarBot), outlineBrush, 1f);
                }

                // V2: Stacked zone boxes (on top of cells, below POC/VA)
                if (ShowStackedZoneBoxes)
                {
                    List<StackedZone> zones;
                    lock (_barsLock) { _stackedZones.TryGetValue(barIdx, out zones); }
                    if (zones != null)
                    {
                        foreach (var zone in zones)
                        {
                            float yTop    = (float)chartScale.GetYByValue(zone.PriceHigh + tickSize * 0.5);
                            float yBottom = (float)chartScale.GetYByValue(zone.PriceLow  - tickSize * 0.5);
                            float sw = zone.Tier == 3 ? 2f : zone.Tier == 2 ? 1.5f : 1f;
                            var zBrush = zone.Direction > 0 ? _stackedBuyZoneDx : _stackedSellZoneDx;
                            if (zBrush != null)
                                RenderTarget.DrawRectangle(new RectangleF(xLeft, yTop, colW, yBottom - yTop), zBrush, sw);
                        }
                    }
                }

                // V2: Volume Climax marker
                if (ShowVolumeClimax)
                {
                    int climDir;
                    lock (_barsLock) { _volumeClimaxBars.TryGetValue(barIdx, out climDir); }
                    if (climDir != 0 && _volumeClimaxDx != null)
                    {
                        float yExtreme = (float)chartScale.GetYByValue(climDir > 0 ? fbar.Low : fbar.High);
                        float offset = climDir > 0 ? 2f : -2f;
                        RenderTarget.DrawLine(new Vector2(xLeft, yExtreme + offset),
                            new Vector2(xLeft + colW, yExtreme + offset), _volumeClimaxDx, 2.5f);
                    }
                }

                // ── POC — gold #FFD23F, 2px, rendered LAST on top of cells ──
                if (ShowPoc && fbar.PocPrice > 0)
                {
                    float yPoc  = (float)chartScale.GetYByValue(fbar.PocPrice);
                    var   pocBr = _anchorPocDx ?? (SharpDX.Direct2D1.SolidColorBrush)_pocDx;
                    RenderTarget.FillRectangle(new RectangleF(xLeft, yPoc - 1f, colW, 2f), pocBr);
                }

                // VAH/VAL
                if (ShowValueArea)
                {
                    var va = FootprintBar.ComputeValueArea(fbar, tickSize);
                    float yVah = (float)chartScale.GetYByValue(va.vah);
                    float yVal = (float)chartScale.GetYByValue(va.val);
                    RenderTarget.DrawLine(new Vector2(xLeft, yVah), new Vector2(xLeft + colW, yVah), _vahDx, 1f);
                    RenderTarget.DrawLine(new Vector2(xLeft, yVal), new Vector2(xLeft + colW, yVal), _valDx, 1f);
                }
            }

            // Phase 18: Scoring HUD badge — rendered LAST (highest Z per 03-SPATIAL-LAYOUT.md z-order #20)
            // Anchored top-right of chart-area (NOT under MC panel — uses panelRight which has been narrowed).
            if (ShowScoreHud) RenderScoreHud(panelRight);

            // ▰▰▰ MISSION CONTROL right-side panel — ABSOLUTE TOP Z, paints over everything else.
            // Replaces the legacy F1 PITWALL top strip. Right-edge anchored, full chart height.
            if (ShowMissionControl) RenderMissionControl(chartControl);
        }

        private static long GetBid(FootprintBar bar, double price)
        {
            Cell c; return bar.Levels.TryGetValue(price, out c) ? c.BidVol : 0;
        }
        private static long GetAsk(FootprintBar bar, double price)
        {
            Cell c; return bar.Levels.TryGetValue(price, out c) ? c.AskVol : 0;
        }

        private static string FmtVolV3(long v)
        {
            if (v <= 0)    return "";
            if (v < 10000) return v.ToString();
            return (v / 1000).ToString() + "k";
        }

        // ═══════════════════════════════════════════════════════════════════════════
        // V2 Computation Methods
        // ═══════════════════════════════════════════════════════════════════════════

        private void ComputeV2Bar(FootprintBar bar, int barIdx)
        {
            if (bar == null) return;
            UpdateVwap(bar);
            UpdateInitialBalance(bar);
            DetectBullBearColumn(bar, barIdx);
            DetectStackedZones(bar, barIdx);
            DetectUnfinishedAuctions(bar, barIdx);
            DetectVolumeClimax(bar, barIdx);
        }

        private void UpdateVwap(FootprintBar bar)
        {
            if (bar.TotalVol == 0) return;
            double tp  = (bar.High + bar.Low + bar.Close) / 3.0;
            double vol = bar.TotalVol;
            _vwapNumerator   += tp * vol;
            _vwapDenominator += vol;
            if (_vwapDenominator <= 0) return;
            double newVwap = _vwapNumerator / _vwapDenominator;
            _vwapVariance += vol * (tp - newVwap) * (tp - newVwap);
            _vwapPrice = newVwap;
            double sd = _vwapVariance > 0 ? Math.Sqrt(_vwapVariance / _vwapDenominator) : 0;
            _vwap1SigHigh = _vwapPrice + sd;
            _vwap1SigLow  = _vwapPrice - sd;
            _vwap2SigHigh = _vwapPrice + 2 * sd;
            _vwap2SigLow  = _vwapPrice - 2 * sd;
        }

        private void UpdateInitialBalance(FootprintBar bar)
        {
            if (_ibConfirmed) return;
            if (_sessionBarCount <= 60)
            {
                if (bar.High > _ibHigh || _ibHigh == double.MinValue) _ibHigh = bar.High;
                if (bar.Low  < _ibLow  || _ibLow  == double.MaxValue) _ibLow  = bar.Low;
            }
            else if (_ibHigh > double.MinValue)
            {
                _ibConfirmed = true;
            }
        }

        private void DetectBullBearColumn(FootprintBar bar, int barIdx)
        {
            if (bar.Levels.Count < 6) return;
            bool allBull = true, allBear = true;
            foreach (var kv in bar.Levels)
            {
                long d = kv.Value.AskVol - kv.Value.BidVol;
                if (d <= 0) allBull = false;
                if (d >= 0) allBear = false;
                if (!allBull && !allBear) break;
            }
            int ct = allBull ? 1 : allBear ? -1 : 0;
            lock (_barsLock) { _barColumnType[barIdx] = ct; }
        }

        private void DetectStackedZones(FootprintBar bar, int barIdx)
        {
            if (bar.Levels.Count < 3) return;
            double ts = TickSize > 0 ? TickSize : 0.25;
            double thr = ImbalanceRatio;
            var zones = new List<StackedZone>();
            var prices = new List<double>(bar.Levels.Keys);

            int i = 0;
            while (i < prices.Count)
            {
                Cell c;
                if (!bar.Levels.TryGetValue(prices[i], out c)) { i++; continue; }
                int dir = CellImbalanceDir(c, thr);
                if (dir == 0) { i++; continue; }

                int runLen = 1;
                double endPrice = prices[i];
                for (int j = i + 1; j < prices.Count; j++)
                {
                    if (Math.Abs(prices[j] - prices[j - 1] - ts) > ts * 0.1) break;
                    Cell nc;
                    if (!bar.Levels.TryGetValue(prices[j], out nc)) break;
                    if (CellImbalanceDir(nc, thr) != dir) break;
                    runLen++;
                    endPrice = prices[j];
                }

                if (runLen >= 3)
                {
                    int tier = runLen >= 7 ? 3 : runLen >= 5 ? 2 : 1;
                    zones.Add(new StackedZone { PriceLow = prices[i], PriceHigh = endPrice, Tier = tier, Direction = dir });
                }
                i += runLen;
            }

            if (zones.Count > 0)
                lock (_barsLock) { _stackedZones[barIdx] = zones; }
        }

        private static int CellImbalanceDir(Cell c, double threshold)
        {
            if (c.AskVol > 0)
            {
                double r = (double)c.AskVol / Math.Max(1.0, c.BidVol);
                if (r >= threshold) return +1;
            }
            if (c.BidVol > 0)
            {
                double r = (double)c.BidVol / Math.Max(1.0, c.AskVol);
                if (r >= threshold) return -1;
            }
            return 0;
        }

        private void DetectUnfinishedAuctions(FootprintBar bar, int barIdx)
        {
            double ts = TickSize > 0 ? TickSize : 0.25;
            // Unfinished HIGH: both sides present at bar high
            Cell hc;
            if (bar.Levels.TryGetValue(bar.High, out hc) && hc.AskVol > 0 && hc.BidVol > 0)
                _unfinishedAuctions[bar.High] = barIdx;
            // Unfinished LOW: both sides present at bar low
            Cell lc;
            if (bar.Levels.TryGetValue(bar.Low, out lc) && lc.AskVol > 0 && lc.BidVol > 0)
                _unfinishedAuctions[bar.Low] = barIdx;
            // Cancel levels that this bar traded through
            var revisited = new List<double>();
            foreach (var kv in _unfinishedAuctions)
                if (kv.Value < barIdx && kv.Key >= bar.Low && kv.Key <= bar.High)
                    revisited.Add(kv.Key);
            foreach (var k in revisited) _unfinishedAuctions.Remove(k);
            // Expire levels older than 100 bars
            var expired = new List<double>();
            foreach (var kv in _unfinishedAuctions)
                if (barIdx - kv.Value > 100) expired.Add(kv.Key);
            foreach (var k in expired) _unfinishedAuctions.Remove(k);
        }

        private void DetectVolumeClimax(FootprintBar bar, int barIdx)
        {
            _nBarHighs.Enqueue(bar.High);
            _nBarLows.Enqueue(bar.Low);
            while (_nBarHighs.Count > NBarLookback) _nBarHighs.Dequeue();
            while (_nBarLows.Count  > NBarLookback) _nBarLows.Dequeue();
            if (_volEma <= 0 || _nBarHighs.Count < NBarLookback) return;
            if (bar.TotalVol <= _volEma * VolClimaxMultiplier) return;
            double hi = double.MinValue, lo = double.MaxValue;
            foreach (var h in _nBarHighs) if (h > hi) hi = h;
            foreach (var l in _nBarLows)  if (l < lo) lo = l;
            double mid = (bar.High + bar.Low) / 2.0;
            if      (bar.High >= hi && bar.Close < mid) lock (_barsLock) { _volumeClimaxBars[barIdx] = -1; }
            else if (bar.Low  <= lo && bar.Close > mid) lock (_barsLock) { _volumeClimaxBars[barIdx] = +1; }
        }

        // ═══════════════════════════════════════════════════════════════════════════
        // V2 Rendering Helpers
        // ═══════════════════════════════════════════════════════════════════════════

        private void RenderV2Vwap(ChartScale cs, float panelRight)
        {
            if (_vwapLineDx == null || _vwapPrice <= 0) return;
            float panelLeft = (float)ChartPanel.X;
            float y = cs.GetYByValue(_vwapPrice);
            RenderTarget.DrawLine(new Vector2(panelLeft, y), new Vector2(panelRight, y), _vwapLineDx, 1.5f);
            if (ShowVWAPBands)
            {
                if (_vwapBand1Dx != null && _vwap1SigHigh > 0)
                {
                    float y1h = cs.GetYByValue(_vwap1SigHigh);
                    float y1l = cs.GetYByValue(_vwap1SigLow);
                    RenderTarget.DrawLine(new Vector2(panelLeft, y1h), new Vector2(panelRight, y1h), _vwapBand1Dx, 1f, _dashStyle);
                    RenderTarget.DrawLine(new Vector2(panelLeft, y1l), new Vector2(panelRight, y1l), _vwapBand1Dx, 1f, _dashStyle);
                }
                if (_vwapBand2Dx != null && _vwap2SigHigh > 0)
                {
                    float y2h = cs.GetYByValue(_vwap2SigHigh);
                    float y2l = cs.GetYByValue(_vwap2SigLow);
                    RenderTarget.DrawLine(new Vector2(panelLeft, y2h), new Vector2(panelRight, y2h), _vwapBand2Dx, 1f, _dashStyle);
                    RenderTarget.DrawLine(new Vector2(panelLeft, y2l), new Vector2(panelRight, y2l), _vwapBand2Dx, 1f, _dashStyle);
                }
            }
            if (_labelFont != null)
            {
                using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                    string.Format("VWAP {0:F2}", _vwapPrice), _labelFont, 90f, 14f))
                    RenderTarget.DrawTextLayout(new Vector2(panelRight - 92f, y - 7f), tl, _vwapLineDx);
            }
        }

        private void RenderV2InitialBalance(ChartScale cs, float panelRight)
        {
            if (_ibLineDx == null || _ibHigh <= double.MinValue) return;
            float panelLeft = (float)ChartPanel.X;
            float yH = cs.GetYByValue(_ibHigh);
            float yL = cs.GetYByValue(_ibLow);
            RenderTarget.DrawLine(new Vector2(panelLeft, yH), new Vector2(panelRight, yH), _ibLineDx, 1.5f);
            RenderTarget.DrawLine(new Vector2(panelLeft, yL), new Vector2(panelRight, yL), _ibLineDx, 1.5f);
            if (_labelFont != null)
            {
                using (var tl1 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, "IBH", _labelFont, 30f, 14f))
                    RenderTarget.DrawTextLayout(new Vector2(panelRight - 32f, yH - 7f), tl1, _ibLineDx);
                using (var tl2 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, "IBL", _labelFont, 30f, 14f))
                    RenderTarget.DrawTextLayout(new Vector2(panelRight - 32f, yL - 7f), tl2, _ibLineDx);
            }
        }

        private void RenderV2UnfinishedAuctions(ChartScale cs, float panelRight)
        {
            if (_unfinishedLineDx == null) return;
            float panelLeft  = (float)ChartPanel.X;
            float panelTop   = (float)ChartPanel.Y;
            float panelBot   = panelTop + (float)ChartPanel.H;
            foreach (var kv in _unfinishedAuctions)
            {
                float y = cs.GetYByValue(kv.Key);
                if (y < panelTop || y > panelBot) continue;
                RenderTarget.DrawLine(new Vector2(panelLeft, y), new Vector2(panelRight - 12f, y),
                    _unfinishedLineDx, 1f, _dashStyle);
            }
        }

        // ───────────────────────────────────────────────────────────────────
        // F1 PITWALL — Aesthetic Option E render helpers
        // ───────────────────────────────────────────────────────────────────

        // Targeting-reticle frame: 4 L-shaped corner brackets, no full rectangle.
        // Used to mark extreme imbalance cells + absorption/exhaustion signatures.
        private void DrawCornerBrackets(RectangleF r, SharpDX.Direct2D1.Brush brush, float legLen, float stroke)
        {
            if (brush == null) return;
            // Top-left
            RenderTarget.DrawLine(new Vector2(r.Left, r.Top),
                                  new Vector2(r.Left + legLen, r.Top), brush, stroke);
            RenderTarget.DrawLine(new Vector2(r.Left, r.Top),
                                  new Vector2(r.Left, r.Top + legLen), brush, stroke);
            // Top-right
            RenderTarget.DrawLine(new Vector2(r.Right, r.Top),
                                  new Vector2(r.Right - legLen, r.Top), brush, stroke);
            RenderTarget.DrawLine(new Vector2(r.Right, r.Top),
                                  new Vector2(r.Right, r.Top + legLen), brush, stroke);
            // Bottom-left
            RenderTarget.DrawLine(new Vector2(r.Left, r.Bottom),
                                  new Vector2(r.Left + legLen, r.Bottom), brush, stroke);
            RenderTarget.DrawLine(new Vector2(r.Left, r.Bottom),
                                  new Vector2(r.Left, r.Bottom - legLen), brush, stroke);
            // Bottom-right
            RenderTarget.DrawLine(new Vector2(r.Right, r.Bottom),
                                  new Vector2(r.Right - legLen, r.Bottom), brush, stroke);
            RenderTarget.DrawLine(new Vector2(r.Right, r.Bottom),
                                  new Vector2(r.Right, r.Bottom - legLen), brush, stroke);
        }

        // Draw text with 1px black halo (fighter-HMD legibility rule, MIL-STD-1787 adjacent).
        private void DrawHaloText(string s, TextFormat f, SharpDX.Direct2D1.Brush color, float x, float y, float w, float h)
        {
            if (string.IsNullOrEmpty(s) || f == null || color == null) return;
            using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, s, f, w, h))
            {
                if (_pwTextHaloDx != null)
                {
                    RenderTarget.DrawTextLayout(new Vector2(x - 1, y), tl, _pwTextHaloDx);
                    RenderTarget.DrawTextLayout(new Vector2(x + 1, y), tl, _pwTextHaloDx);
                    RenderTarget.DrawTextLayout(new Vector2(x, y - 1), tl, _pwTextHaloDx);
                    RenderTarget.DrawTextLayout(new Vector2(x, y + 1), tl, _pwTextHaloDx);
                }
                RenderTarget.DrawTextLayout(new Vector2(x, y), tl, color);
            }
        }

        // Measure text width via TextLayout (cached factory). Used by pit-wall strip.
        private float MeasureTextWidth(string s, TextFormat f)
        {
            if (string.IsNullOrEmpty(s) || f == null) return 0f;
            using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, s, f, 9999f, 24f))
            {
                return tl.Metrics.Width + 2f;
            }
        }

        // [REMOVED] Legacy F1 PITWALL strip data structures — superseded by Mission Control panel.
        // Removed: PitWallPill struct, BuildPitWallPills(), SectorBrushForDelta/Confidence helpers,
        // FormatK/FormatSignedK helpers. All call sites are gone since RenderMissionControl
        // (right-side panel) directly composes its sections inline.
        #if FALSE
        private struct PitWallPill
        {
            public string Label;
            public string Value;
            public SharpDX.Direct2D1.Brush EdgeBrush;    // sector-color left edge stripe
            public SharpDX.Direct2D1.Brush ValueBrush;   // value text color
        }

        // Sector-color logic — central source of truth
        private SharpDX.Direct2D1.SolidColorBrush SectorBrushForDelta(long d)
        {
            long ad = Math.Abs(d);
            if (ad >= 2000) return d > 0 ? _pwSectorPurpleDx : _pwSectorRedDx;
            if (ad >= 1000) return d > 0 ? _pwSectorGreenDx  : _pwSectorYellowDx;
            return _pwSectorWhiteDx;
        }

        private SharpDX.Direct2D1.SolidColorBrush SectorBrushForConfidence(double c)
        {
            if (c >= 0.85) return _pwSectorPurpleDx;
            if (c >= 0.70) return _pwSectorGreenDx;
            if (c >= 0.50) return _pwSectorWhiteDx;
            return _pwSectorYellowDx;
        }

        private static string FormatK(long v)
        {
            long av = Math.Abs(v);
            if (av >= 1_000_000) return (v / 1_000_000.0).ToString("F1") + "M";
            if (av >= 1_000)     return (v / 1_000.0).ToString("F0") + "K";
            return v.ToString();
        }

        private static string FormatSignedK(long v)
        {
            return (v >= 0 ? "+" : "−") + FormatK(Math.Abs(v));
        }

        // Pulls live data from the indicator's own state for the pit-wall pills.
        // Wires to: latest bar in _bars (delta, vol, POC), _lastScorerResult (score, narrative).
        // Future v2: bridge from DEEP6Strategy (P&L, Kronos, tire compound) via DataBridgeIndicator.
        private IList<PitWallPill> BuildPitWallPills()
        {
            var list = new List<PitWallPill>(8);

            // Pull current bar from _bars dict
            FootprintBar curBar = null;
            lock (_barsLock)
            {
                if (CurrentBar >= 0)
                    _bars.TryGetValue(CurrentBar, out curBar);
            }

            // 1. Symbol
            string sym = (Instrument != null && Instrument.MasterInstrument != null)
                ? Instrument.MasterInstrument.Name : "—";
            list.Add(new PitWallPill {
                Label = "SYM",
                Value = sym,
                EdgeBrush = _pwAeroWhiteDx,
                ValueBrush = _pwAeroWhiteDx
            });

            // 2. Δ (running delta of current bar)
            long delta = curBar != null ? curBar.RunningDelta : 0L;
            var deltaBrush = SectorBrushForDelta(delta);
            list.Add(new PitWallPill {
                Label = "Δ",
                Value = FormatSignedK(delta),
                EdgeBrush = deltaBrush,
                ValueBrush = deltaBrush
            });

            // 3. VOL
            long vol = curBar != null ? curBar.TotalVol : 0L;
            list.Add(new PitWallPill {
                Label = "VOL",
                Value = FormatK(vol),
                EdgeBrush = vol > 50000 ? _pwAeroAmberDx : null,
                ValueBrush = vol > 50000 ? _pwAeroAmberDx : _pwAeroWhiteDx
            });

            // 4. POC
            double poc = curBar != null ? curBar.PocPrice : 0.0;
            list.Add(new PitWallPill {
                Label = "POC",
                Value = poc > 0 ? poc.ToString("F2") : "—",
                EdgeBrush = _pwSectorPurpleDx,
                ValueBrush = _pwAeroWhiteDx
            });

            // 5. CVD
            long cvd = curBar != null ? curBar.Cvd : 0L;
            list.Add(new PitWallPill {
                Label = "CVD",
                Value = FormatSignedK(cvd),
                EdgeBrush = SectorBrushForDelta(cvd),
                ValueBrush = SectorBrushForDelta(cvd)
            });

            // 6. SCORE — latched from scorer (TotalScore is 0..100; sector-color by absolute value)
            var sr = _lastScorerResult;
            if (sr != null)
            {
                double scoreVal = sr.TotalScore;
                // SectorBrushForConfidence expects 0..1; map 0..100 → 0..1 by /100
                var scoreBrush = SectorBrushForConfidence(scoreVal / 100.0);
                list.Add(new PitWallPill {
                    Label = "SCORE",
                    Value = scoreVal.ToString("F0"),
                    EdgeBrush = scoreBrush,
                    ValueBrush = scoreBrush
                });

                // 7. TIER
                string tierStr = sr.Tier.ToString().Replace("TYPE_", "");
                var tierBrush = sr.Tier == SignalTier.TYPE_A ? _pwSectorPurpleDx
                              : sr.Tier == SignalTier.TYPE_B ? _pwSectorGreenDx
                                                              : _pwTextSecondaryDx;
                list.Add(new PitWallPill {
                    Label = "TIER",
                    Value = tierStr,
                    EdgeBrush = tierBrush,
                    ValueBrush = tierBrush
                });
            }

            return list;
        }
        #endif // FALSE — legacy pit-wall strip orphan code

        // Renders the F1 pit-wall telemetry strip across the top of the chart.
        // ═══════════════════════════════════════════════════════════════════════
        // MISSION CONTROL right-edge panel — TradeDevils-style 240px sidebar.
        // Replaces the top pit-wall strip. Renders 7 sections top-to-bottom:
        //   1. Mode selector (BIAS-FOLLOW / MEAN-REV)
        //   2. ▶ ACTIVE SIGNAL (pulses cyan when TYPE_A armed; renders BUY/SELL plan)
        //   3. Connection status
        //   4. Day P&L safety net (with progress bar to GOAL)
        //   5. Position
        //   6. Signals (44, scrollable virtualized list)
        //   7. Action bar (FLATTEN ALL kill switch)
        // ═══════════════════════════════════════════════════════════════════════
        // ▰▰▰ MINIMALIST HUD — Linear / Stripe / Vercel restraint.
        // No boxes. No borders. No fills. No gradients. Just big breathing typography
        // floating in the top-right corner of the chart. Two colors total: cyan (long)
        // and magenta (short). White for primary text. Everything else dim grey.
        // Reads at a glance from across the room.
        // ▰▰▰
        private void RenderMissionControl(ChartControl chartControl)
        {
            if (_pwHudHeroFont == null || _pwHudLabelFont == null) return;
            if (ChartPanel.W < 200) return;

            float chartTop   = (float)ChartPanel.Y;
            float chartRight = (float)(ChartPanel.X + ChartPanel.W);
            float x = chartRight - 280f;   // 280px column anchor, right-aligned text inside
            float w = 264f;
            float y = chartTop + 16f;

            var sr = _lastScorerResult;
            bool armed = sr != null && sr.Tier == SignalTier.TYPE_A && sr.Direction != 0
                         && IsVersionTwoSignalVisible(sr);

            // ── Line 1 (HERO 32pt): the only thing that screams ──
            //    Armed:  "▶ BUY 21452.25"  in cyan, or  "▶ SELL 21452.25"  in magenta
            //    Idle:   "—" in dim grey (deliberate emptiness — restraint signals quality)
            string heroText;
            SharpDX.Direct2D1.Brush heroBrush;
            if (armed)
            {
                bool isLong = sr.Direction > 0;
                string verb = isLong ? "BUY" : "SELL";
                heroText  = string.Format("\u25B6 {0} {1:F2}", verb, sr.EntryPrice);
                heroBrush = isLong ? (SharpDX.Direct2D1.Brush)_pwAeroCyanDx
                                   : (SharpDX.Direct2D1.Brush)_pwAeroMagentaDx;
            }
            else
            {
                heroText  = "\u2014";
                heroBrush = (SharpDX.Direct2D1.Brush)_pwTextTertiaryDx;
            }
            DrawHaloText(heroText, _pwHudHeroFont, heroBrush, x, y, w, 38);

            // ── Line 2 (16pt label, 14pt value): SCORE ──
            y += 44f;
            DrawHaloText("SCORE", _pwHudLabelFont, _pwTextTertiaryDx, x, y, 60, 18);
            string scoreVal = (sr != null) ? sr.TotalScore.ToString("F0") : "—";
            DrawHaloText(scoreVal, _pwHudValueFont, _pwAeroWhiteDx, x + 70, y, w - 70, 18);

            // ── Line 3: TIER ──
            y += 24f;
            DrawHaloText("TIER", _pwHudLabelFont, _pwTextTertiaryDx, x, y, 60, 18);
            string tierVal = (sr != null) ? TierChar(sr.Tier) : "—";
            var tierBrush = (sr != null && sr.Tier == SignalTier.TYPE_A)
                ? heroBrush
                : (SharpDX.Direct2D1.Brush)_pwAeroWhiteDx;
            DrawHaloText(tierVal, _pwHudValueFont, tierBrush, x + 70, y, w - 70, 18);

            // ── Line 4 (only when armed): tiny stop / target row ──
            if (armed)
            {
                bool isLong = sr.Direction > 0;
                double stopTicks = 12.0, rrRatio = 2.0;
                double stopPx = isLong ? sr.EntryPrice - stopTicks * TickSize
                                       : sr.EntryPrice + stopTicks * TickSize;
                double tgtPx  = isLong ? sr.EntryPrice + stopTicks * rrRatio * TickSize
                                       : sr.EntryPrice - stopTicks * rrRatio * TickSize;

                y += 28f;
                string stopLine = string.Format("STOP  {0:F2}", stopPx);
                string tgtLine  = string.Format("TGT  {0:F2}",  tgtPx);
                DrawHaloText(stopLine, _pwHudLabelFont, _pwTextSecondaryDx, x,           y, 130, 16);
                DrawHaloText(tgtLine,  _pwHudLabelFont, _pwTextSecondaryDx, x + w - 110, y, 110, 16);
            }
        }

        // Section 2: ▶ ACTIVE SIGNAL — renders the BUY/SELL plan when a TYPE_A signal is armed
        private float RenderMcActiveSignal(float x, float y, float w)
        {
            const float sectionH = 142f;
            var rect = new RectangleF(x, y, w, sectionH);

            var sr = _lastScorerResult;
            bool armed = sr != null && sr.Tier == SignalTier.TYPE_A && sr.Direction != 0
                         && IsVersionTwoSignalVisible(sr);

            if (armed)
            {
                // Tinted cyan background (long) or magenta (short) + 3px left edge stripe
                bool isLong = sr.Direction > 0;
                var bgBrush   = isLong ? _pwAbsFillDx : _pwExhFillDx;
                var edgeBrush = isLong ? _pwAeroCyanDx : _pwAeroMagentaDx;
                RenderTarget.FillRectangle(rect, bgBrush);
                RenderTarget.FillRectangle(new RectangleF(x, y, 3f, sectionH), edgeBrush);

                // Header: "▶ ACTIVE SIGNAL"  ...  [TIER A]
                DrawHaloText("\u25B6 ACTIVE SIGNAL", _pwPillLabelFont, edgeBrush,
                             x + 10, y + 6, w - 60, 12);
                // Tier badge (purple)
                var tierBadgeRect = new RectangleF(x + w - 48, y + 6, 38, 12);
                RenderTarget.FillRectangle(tierBadgeRect, _pwSectorPurpleDx);
                DrawHaloText("TIER A", _pwPillLabelFont, _pwAeroWhiteDx,
                             x + w - 44, y + 6, 30, 12);

                // Action line: "▶ BUY NQ @ {entry}"  (14pt bold cyan/magenta)
                string sym = (Instrument != null && Instrument.MasterInstrument != null)
                    ? Instrument.MasterInstrument.Name : "—";
                string verb = isLong ? "BUY" : "SELL";
                string actionLine = string.Format("\u25B6 {0} {1} @ {2:F2}", verb, sym, sr.EntryPrice);
                DrawHaloText(actionLine, _pwPillValueFont, edgeBrush,
                             x + 10, y + 22, w - 20, 16);

                // Stop / Target / R:R lines (compute defaults from entry — strategy decides actuals)
                double stopTicks   = 12.0;   // default fixed-tick stop
                double rrRatio     = 2.0;
                double stopPx      = isLong ? sr.EntryPrice - stopTicks * TickSize
                                            : sr.EntryPrice + stopTicks * TickSize;
                double tgtPx       = isLong ? sr.EntryPrice + stopTicks * rrRatio * TickSize
                                            : sr.EntryPrice - stopTicks * rrRatio * TickSize;
                double tgtTicks    = stopTicks * rrRatio;

                string stopLine = string.Format("STOP  {0:F2}  ({1}{2})",
                    stopPx, isLong ? "-" : "+", stopTicks);
                string tgtLine  = string.Format("TGT   {0:F2}  ({1}{2})",
                    tgtPx, isLong ? "+" : "-", tgtTicks);
                string rrLine   = string.Format("R:R {0:F1}   CONF {1:F0}", rrRatio, sr.TotalScore);

                DrawHaloText(stopLine, _pwPillLabelFont, _pwAeroAmberDx,
                             x + 10, y + 44, w - 20, 12);
                DrawHaloText(tgtLine,  _pwPillLabelFont, _pwSectorGreenDx,
                             x + 10, y + 58, w - 20, 12);
                DrawHaloText(rrLine,   _pwPillLabelFont, _pwSectorPurpleDx,
                             x + 10, y + 72, w - 20, 12);

                // Reason narrative (truncated)
                string reason = TruncateEllipsis(sr.Narrative ?? string.Empty, 60);
                if (reason.Length > 0)
                    DrawHaloText(reason, _pwPillLabelFont, _pwTextSecondaryDx,
                                 x + 10, y + 88, w - 20, 12);

                // EXECUTE NOW button (cyan/magenta, 24px tall)
                var execBtnRect = new RectangleF(x + 10, y + sectionH - 28, w - 20, 22);
                RenderTarget.FillRectangle(execBtnRect, edgeBrush);
                // Black-on-cyan/magenta button text — high contrast on saturated bg
                DrawHaloText("\u25B6 EXECUTE NOW", _pwPillValueFont, _pwTextHaloDx,
                             x + 10, y + sectionH - 28, w - 20, 22);
            }
            else
            {
                // Idle state — section dim, just shows "no active signal"
                RenderTarget.FillRectangle(new RectangleF(x, y, 3f, sectionH),
                    (SharpDX.Direct2D1.Brush)_pwTextTertiaryDx);
                DrawHaloText("ACTIVE SIGNAL", _pwPillLabelFont, _pwTextTertiaryDx,
                             x + 10, y + 6, w - 20, 12);
                DrawHaloText("— no signal armed —", _pwPillLabelFont, _pwTextTertiaryDx,
                             x + 10, y + 60, w - 20, 12);
            }

            // Bottom divider
            RenderTarget.DrawLine(
                new Vector2(x, y + sectionH),
                new Vector2(x + w, y + sectionH),
                _pwGridMajorDx, 1f);
            return y + sectionH;
        }

        // Section 3: connection status (small)
        private float RenderMcStatus(float x, float y, float w)
        {
            const float sectionH = 36f;
            // Strategy ENABLED row + dot
            DrawHaloText("\u25CF STRATEGY", _pwPillLabelFont, _pwSectorGreenDx,
                         x + 10, y + 6, 70, 12);
            DrawHaloText("ENABLED", _pwPillLabelFont, _pwSectorGreenDx,
                         x + w - 60, y + 6, 50, 12);
            DrawHaloText("RITHMIC", _pwPillLabelFont, _pwTextSecondaryDx,
                         x + 10, y + 20, 70, 12);
            DrawHaloText("12ms",    _pwPillLabelFont, _pwAeroWhiteDx,
                         x + w - 50, y + 20, 40, 12);
            RenderTarget.DrawLine(
                new Vector2(x, y + sectionH), new Vector2(x + w, y + sectionH),
                _pwGridLineDx, 1f);
            return y + sectionH;
        }

        // Section 4: Day P&L (safety net) with progress bar
        private float RenderMcDayPnL(float x, float y, float w)
        {
            const float sectionH = 76f;
            DrawHaloText("DAY P&L (SAFETY NET)", _pwPillLabelFont, _pwTextTertiaryDx,
                         x + 10, y + 4, w - 20, 12);

            // Stub values (DataBridge integration deferred to v2)
            double realized = 425.00;   // TODO: bridge from strategy
            double goal = 600.00, limit = -300.00;
            double pct = Math.Max(0, Math.Min(1, realized / goal));

            string realLine = string.Format("REALIZED  +${0,7:F2}", realized);
            string goalLine = string.Format("GOAL  ${0,4:F0}", goal);
            string limLine  = string.Format("LIMIT  -${0,4:F0}", Math.Abs(limit));

            DrawHaloText(realLine, _pwPillLabelFont, _pwSectorGreenDx,
                         x + 10, y + 18, w - 20, 12);
            DrawHaloText(goalLine, _pwPillLabelFont, _pwTextSecondaryDx,
                         x + 10, y + 32, 100, 12);
            DrawHaloText(limLine, _pwPillLabelFont, _pwSectorRedDx,
                         x + w - 90, y + 32, 80, 12);

            // Progress bar to GOAL
            var bgRect = new RectangleF(x + 10, y + 50, w - 20, 4);
            RenderTarget.FillRectangle(bgRect, _pwGridMajorDx);
            var fillRect = new RectangleF(x + 10, y + 50, (w - 20) * (float)pct, 4);
            RenderTarget.FillRectangle(fillRect, _pwSectorGreenDx);
            string pctTxt = string.Format("{0:F0}% to GOAL", pct * 100);
            DrawHaloText(pctTxt, _pwPillLabelFont, _pwTextSecondaryDx,
                         x + 10, y + 58, w - 20, 12);

            RenderTarget.DrawLine(
                new Vector2(x, y + sectionH), new Vector2(x + w, y + sectionH),
                _pwGridLineDx, 1f);
            return y + sectionH;
        }

        // Section 5: Position
        private float RenderMcPosition(float x, float y, float w)
        {
            const float sectionH = 56f;
            DrawHaloText("POSITION", _pwPillLabelFont, _pwTextTertiaryDx,
                         x + 10, y + 4, w - 20, 12);
            // Stub values (DataBridge integration deferred to v2)
            DrawHaloText("Long 2 NQ @ 18452.25", _pwPillLabelFont, _pwAeroWhiteDx,
                         x + 10, y + 18, w - 20, 12);
            DrawHaloText("UNREAL  +$45.00", _pwPillLabelFont, _pwSectorGreenDx,
                         x + 10, y + 32, w - 20, 12);
            RenderTarget.DrawLine(
                new Vector2(x, y + sectionH), new Vector2(x + w, y + sectionH),
                _pwGridLineDx, 1f);
            return y + sectionH;
        }

        // Section 6: 44 signals — scrollable virtualized list
        private void RenderMcSignalsList(float x, float y, float w, float h)
        {
            DrawHaloText("SIGNALS (44)", _pwPillLabelFont, _pwTextTertiaryDx,
                         x + 10, y + 4, w - 20, 12);

            // Hard-coded for v1 — TODO: dynamic enumeration from registry in v2
            var rows = new[] {
                new { L = "ABS",  N = "Absorption",       T = "12:34:01", Recent = true },
                new { L = "EXH",  N = "Exhaustion",       T = "12:32:55", Recent = true },
                new { L = "SI",   N = "Stacked Imbal",    T = "12:34:01", Recent = true },
                new { L = "DR",   N = "Delta Rise",       T = "12:18:40", Recent = false },
                new { L = "DD",   N = "Delta Drop",       T = "11:58:20", Recent = false },
                new { L = "DV",   N = "Delta Diverge",    T = "--",       Recent = false },
                new { L = "DF",   N = "Delta Flip",       T = "12:30:45", Recent = false },
                new { L = "DT",   N = "Delta Tail",       T = "--",       Recent = false },
                new { L = "RV",   N = "Delta Rev",        T = "12:18:09", Recent = false },
                new { L = "TR",   N = "Delta Trap",       T = "11:40:11", Recent = false },
                new { L = "DC",   N = "Delta Cont POC",   T = "--",       Recent = false },
                new { L = "DS",   N = "Delta Sweep",      T = "12:32:55", Recent = false },
                new { L = "TT",   N = "Trapped Trd",      T = "12:14:40", Recent = false },
                new { L = "DI",   N = "Delta Sling",      T = "--",       Recent = false },
                new { L = "II",   N = "Inverse Imb",      T = "11:55:30", Recent = false },
                new { L = "RI",   N = "Rev Imbal",        T = "--",       Recent = false },
                new { L = "OS",   N = "Oversized Imb",    T = "12:01:12", Recent = false },
                new { L = "EP",   N = "Exhaust Print",    T = "11:48:33", Recent = false },
            };

            const float rowH = 14f;
            float listTop = y + 18;
            float listBottom = y + h - 4;
            int maxRows = (int)Math.Max(0, (listBottom - listTop) / rowH);
            int rowCount = Math.Min(rows.Length, maxRows);
            for (int i = 0; i < rowCount; i++)
            {
                var r = rows[i];
                float rowY = listTop + i * rowH;
                // Checkbox (10x10) — checked = cyan
                var cbRect = new RectangleF(x + 10, rowY + 2, 10, 10);
                RenderTarget.FillRectangle(cbRect, _pwAeroCyanDx);
                // Letter code (cyan)
                DrawHaloText(r.L, _pwPillLabelFont, _pwAeroCyanDx,
                             x + 24, rowY, 24, rowH);
                // Signal name (white if recent, secondary otherwise)
                var nameBrush = r.Recent ? (SharpDX.Direct2D1.Brush)_pwAeroWhiteDx : (SharpDX.Direct2D1.Brush)_pwTextSecondaryDx;
                DrawHaloText(r.N, _pwPillLabelFont, nameBrush,
                             x + 50, rowY, 90, rowH);
                // Last-fire timestamp
                var timeBrush = r.Recent ? (SharpDX.Direct2D1.Brush)_pwAeroCyanDx : (SharpDX.Direct2D1.Brush)_pwTextTertiaryDx;
                DrawHaloText(r.T, _pwPillLabelFont, timeBrush,
                             x + w - 60, rowY, 50, rowH);
            }
            if (rows.Length > rowCount)
            {
                string moreLabel = string.Format("\u2026 {0} more", rows.Length - rowCount);
                DrawHaloText(moreLabel, _pwPillLabelFont, _pwTextTertiaryDx,
                             x + 10, listBottom - rowH, w - 20, rowH);
            }
        }

        // Section 7: Action bar — FLATTEN ALL kill switch + Cancel + Pause
        private void RenderMcActionBar(float x, float y, float w)
        {
            const float sectionH = 88f;
            // Top divider
            RenderTarget.DrawLine(
                new Vector2(x, y), new Vector2(x + w, y),
                _pwGridMajorDx, 1f);
            // Background
            RenderTarget.FillRectangle(new RectangleF(x, y, w, sectionH), _pwSurface1Dx);

            // FLATTEN ALL — red, bold, 32px tall
            var flattenRect = new RectangleF(x + 10, y + 8, w - 20, 32);
            RenderTarget.FillRectangle(flattenRect, _pwAeroRedDx);
            DrawHaloText("\u26A0 FLATTEN ALL", _pwPillValueFont, _pwAeroWhiteDx,
                         x + 10, y + 8, w - 20, 32);

            // Cancel Pending
            var cancelRect = new RectangleF(x + 10, y + 46, w - 20, 16);
            RenderTarget.DrawRectangle(cancelRect, _pwTextTertiaryDx, 1f);
            DrawHaloText("Cancel Pending", _pwPillLabelFont, _pwTextSecondaryDx,
                         x + 10, y + 46, w - 20, 16);

            // Pause Strategy
            var pauseRect = new RectangleF(x + 10, y + 66, w - 20, 16);
            RenderTarget.DrawRectangle(pauseRect, _pwTextTertiaryDx, 1f);
            DrawHaloText("Pause Strategy", _pwPillLabelFont, _pwTextSecondaryDx,
                         x + 10, y + 66, w - 20, 16);
        }

        // ═══════════════════════════════════════════════════════════════════════
        // TIER 1 chart overlay — renders Version Two setup/direction/trigger callouts only.
        // No stop/target overlays are drawn on the chart. Called from OnRender.
        // ═══════════════════════════════════════════════════════════════════════
        // True when the latest TYPE_A signal was scored within ArmedSignalValidBars.
        // Prevents stale "EXECUTE NOW" cards from showing all afternoon after a morning fire.
        private bool IsVersionTwoSignalVisible(ScorerResult sr)
        {
            if (sr == null) return false;
            int anchorBar = sr.TriggerBarIndex >= 0 ? sr.TriggerBarIndex : _activeSetupBarIndex;
            if (anchorBar < 0) return false;
            int age = CurrentBar - anchorBar;
            return age >= 0 && age <= ArmedSignalValidBars;
        }

        private void RenderTier1Overlay(ChartControl cc, ChartScale cs, float panelLeftEdge)
        {
            var sr = _lastScorerResult;
            if (sr == null || sr.Tier != SignalTier.TYPE_A || sr.Direction == 0) return;
            if (sr.EntryPrice <= 0) return;
            if (!IsVersionTwoSignalVisible(sr)) return;

            bool isLong = sr.Direction > 0;
            var accent = isLong ? _pwAeroCyanDx : _pwAeroMagentaDx;
            float xRight = panelLeftEdge - 8f;
            float yEntry = cs.GetYByValue(sr.EntryPrice);
            float chartTop = (float)ChartPanel.Y;
            float chartBot = (float)(ChartPanel.Y + ChartPanel.H);
            yEntry = Math.Max(chartTop + 8f, Math.Min(chartBot - 18f, yEntry));

            string stateText;
            switch (sr.SetupState)
            {
                case TradeSetupState.Triggered:
                    stateText = isLong ? "TRIGGER LONG" : "TRIGGER SHORT";
                    break;
                case TradeSetupState.Armed:
                    stateText = isLong ? "WAIT LONG" : "WAIT SHORT";
                    break;
                case TradeSetupState.Invalid:
                    stateText = isLong ? "INVALID LONG" : "INVALID SHORT";
                    break;
                case TradeSetupState.Expired:
                    stateText = isLong ? "EXPIRED LONG" : "EXPIRED SHORT";
                    break;
                default:
                    stateText = isLong ? "SETUP LONG" : "SETUP SHORT";
                    break;
            }

            string detailText = string.Format("TYPE {0} | {1}/100 | {2} CAT{3}",
                TierChar(sr.Tier),
                (int)sr.TotalScore,
                sr.CategoryCount,
                sr.CategoryCount == 1 ? string.Empty : "S");
            DrawHaloText(stateText, _pwPillValueFont, accent, xRight - 190f, yEntry - 18f, 180f, 16f);
            DrawHaloText(detailText, _pwPillLabelFont, _pwAeroWhiteDx, xRight - 140f, yEntry - 4f, 130f, 12f);

            if (sr.SetupState != TradeSetupState.Triggered || sr.TriggerBarIndex < 0 || sr.TriggerBarIndex < ChartBars.FromIndex)
                return;

            float xCenter = cc.GetXByBarIndex(ChartBars, sr.TriggerBarIndex);
            double pulseT = (DateTime.UtcNow.TimeOfDay.TotalMilliseconds % 1200.0) / 1200.0;
            double pulseScale = 1.0 + 0.15 * Math.Sin(pulseT * Math.PI * 2);
            float halfBase = (float)(11.0 * pulseScale);
            float height = (float)(22.0 * pulseScale);
            int hRows = (int)Math.Max(8, Math.Min(40, height));

            if (isLong)
            {
                float yTip = yEntry + 4f;
                for (int i = 0; i <= hRows; i++)
                {
                    float t = (float)i / hRows;
                    float halfW = halfBase * t;
                    float yRow = yTip + height * t;
                    RenderTarget.DrawLine(new Vector2(xCenter - halfW, yRow), new Vector2(xCenter + halfW, yRow), accent, 1.5f);
                }
            }
            else
            {
                float yTip = yEntry - 4f;
                for (int i = 0; i <= hRows; i++)
                {
                    float t = (float)i / hRows;
                    float halfW = halfBase * t;
                    float yRow = yTip - height * t;
                    RenderTarget.DrawLine(new Vector2(xCenter - halfW, yRow), new Vector2(xCenter + halfW, yRow), accent, 1.5f);
                }
            }
        }

        // Renders an absorption signature: cyan reticle + tinted fill + label strip.
        // Call from the marker placement path with the absorption signal data.
        private void RenderAbsorptionSignature(ChartControl cc, ChartScale cs, int barIdx,
                                                double anchorPrice, int direction,
                                                long barDelta, double wickPct)
        {
            if (_pwAbsFillDx == null || _pwAeroCyanDx == null) return;
            int colW = Math.Max(CellColumnWidth, cc.GetBarPaintWidth(ChartBars));
            int xCenter = cc.GetXByBarIndex(ChartBars, barIdx);
            float xLeft = xCenter - colW / 2f;
            float yTop  = cs.GetYByValue(anchorPrice) - 24f;
            const float h = 56f;
            var rect = new RectangleF(xLeft - 4f, yTop, colW + 8f, h);

            RenderTarget.FillRectangle(rect, _pwAbsFillDx);
            DrawCornerBrackets(rect, _pwAeroCyanDx, 8f, 1.5f);

            string lbl = direction > 0 ? "ABSORPTION ▲" : "ABSORPTION ▼";
            DrawHaloText(lbl, _pwPillLabelFont, _pwAeroCyanDx,
                         rect.Left + 8f, rect.Top + 2f, rect.Width - 16f, 12f);

            string data = string.Format("Δ{0:+#;−#;0}  WICK {1:F0}%", barDelta, wickPct);
            DrawHaloText(data, _pwPillValueFont, _pwAeroWhiteDx,
                         rect.Left + 8f, rect.Bottom - 16f, rect.Width - 16f, 14f);
        }

        // Renders an exhaustion signature: magenta reticle + tinted fill + label strip.
        private void RenderExhaustionSignature(ChartControl cc, ChartScale cs, int barIdx,
                                                double anchorPrice, int direction,
                                                long barDelta, double rejectPct)
        {
            if (_pwExhFillDx == null || _pwAeroMagentaDx == null) return;
            int colW = Math.Max(CellColumnWidth, cc.GetBarPaintWidth(ChartBars));
            int xCenter = cc.GetXByBarIndex(ChartBars, barIdx);
            float xLeft = xCenter - colW / 2f;
            float yTop  = cs.GetYByValue(anchorPrice) - 24f;
            const float h = 56f;
            var rect = new RectangleF(xLeft - 4f, yTop, colW + 8f, h);

            RenderTarget.FillRectangle(rect, _pwExhFillDx);
            DrawCornerBrackets(rect, _pwAeroMagentaDx, 8f, 1.5f);

            string lbl = direction > 0 ? "EXHAUSTION ▲" : "EXHAUSTION ▼";
            DrawHaloText(lbl, _pwPillLabelFont, _pwAeroMagentaDx,
                         rect.Left + 8f, rect.Top + 2f, rect.Width - 16f, 12f);

            string data = string.Format("Δ{0:+#;−#;0}  REJ {1:F0}%", barDelta, rejectPct);
            DrawHaloText(data, _pwPillValueFont, _pwAeroWhiteDx,
                         rect.Left + 8f, rect.Bottom - 16f, rect.Width - 16f, 14f);
        }

        // Renders the Chart Trader toolbar: 7 clickable on/off buttons in chart top-left.
        // Each button reflects the state of one indicator feature (Get) and toggles it on click (Set).
        // Lit (green) when on; dim when off. Click handling is in OnChartTraderMouseDown.
        private void RenderChartTrader()
        {
            if (_ctButtons == null || _ctOnDx == null || _ctOffDx == null || _ctBorderDx == null) return;

            const float btnW = 56f, btnH = 22f, gap = 4f;
            float x = (float)ChartPanel.X + 8;
            float y = (float)ChartPanel.Y + 8;

            for (int i = 0; i < _ctButtons.Count; i++)
            {
                var btn = _ctButtons[i];
                btn.Rect = new RectangleF(x, y, btnW, btnH);
                bool on = false;
                try { on = btn.Get(); } catch { }
                var fill = on ? _ctOnDx : _ctOffDx;
                RenderTarget.FillRectangle(btn.Rect, fill);
                RenderTarget.DrawRectangle(btn.Rect, _ctBorderDx, 1f);
                if (_ctBtnFont != null)
                {
                    using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                        btn.Label, _ctBtnFont, btnW, btnH))
                    {
                        RenderTarget.DrawTextLayout(new Vector2(x, y), layout, _textDx);
                    }
                }
                x += btnW + gap;
            }
        }

        // Hit-test the toolbar buttons; toggle the matching feature; force chart redraw.
        // Uses ChartControl.MouseDown wired in OnRenderTargetChanged (when the chart is fully constructed).
        private void OnChartTraderMouseDown(object sender, System.Windows.Input.MouseButtonEventArgs e)
        {
            if (!ShowChartTrader || _ctButtons == null) return;
            if (e.ChangedButton != System.Windows.Input.MouseButton.Left) return;
            if (ChartControl == null) return;

            var pos = e.GetPosition(ChartControl);
            for (int i = 0; i < _ctButtons.Count; i++)
            {
                var btn = _ctButtons[i];
                if (pos.X >= btn.Rect.Left && pos.X <= btn.Rect.Right &&
                    pos.Y >= btn.Rect.Top  && pos.Y <= btn.Rect.Bottom)
                {
                    bool cur = false;
                    try { cur = btn.Get(); } catch { }
                    btn.Set(!cur);
                    e.Handled = true;
                    // ForceRefresh() drives the SharpDX OnRender pipeline; InvalidateVisual()
                    // only triggers the WPF layer and won't repaint our SharpDX overlay.
                    try { ForceRefresh(); } catch { }
                    return;
                }
            }
        }

        // Renders prior-day POC/VAH/VAL, PDH/PDL/PDM, naked POCs, prior-week POC,
        // and optional composite VA band as full-width horizontal lines with right-gutter labels.
        // Colors per FOOTPRINT-VISUAL-SPEC.md §2 and planner notes at top of plan.
        private void RenderProfileAnchors(ChartControl cc, ChartScale cs, float panelRight)
        {
            if (_anchorPocDx == null || _anchorVaDx == null) return;

            var snap = _profileAnchors.BuildSnapshot();
            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;

            // Draw composite VA band first (lowest z-order among anchors — translucent fill)
            if (ShowCompositeVA && snap.CompositeVah.HasValue && snap.CompositeVal.HasValue && _anchorCompositeDx != null)
            {
                float yVah = cs.GetYByValue(snap.CompositeVah.Value);
                float yVal = cs.GetYByValue(snap.CompositeVal.Value);
                if (yVah >= 0 && yVal >= 0)
                {
                    float top  = System.Math.Min(yVah, yVal);
                    float bot  = System.Math.Max(yVah, yVal);
                    var rect = new RectangleF((float)ChartPanel.X, top, panelRight - (float)ChartPanel.X, bot - top);
                    RenderTarget.FillRectangle(rect, _anchorCompositeDx);
                }
            }

            foreach (var anchor in snap.Levels)
            {
                // Gate by user-facing toggles
                bool priorDayKind = anchor.Kind == ProfileAnchorKind.PriorDayPoc ||
                                    anchor.Kind == ProfileAnchorKind.PriorDayVah ||
                                    anchor.Kind == ProfileAnchorKind.PriorDayVal ||
                                    anchor.Kind == ProfileAnchorKind.Pdh         ||
                                    anchor.Kind == ProfileAnchorKind.Pdl         ||
                                    anchor.Kind == ProfileAnchorKind.Pdm;
                if (priorDayKind && !ShowPriorDayLevels) continue;
                if (anchor.Kind == ProfileAnchorKind.NakedPoc && !ShowNakedPocs) continue;
                if ((anchor.Kind == ProfileAnchorKind.CompositeVah ||
                     anchor.Kind == ProfileAnchorKind.CompositeVal) && !ShowCompositeVA) continue;

                double price = anchor.Price;
                if (price < minVis || price > maxVis) continue;

                float y = cs.GetYByValue(price);

                // Choose brush and stroke style
                SharpDX.Direct2D1.SolidColorBrush brush;
                StrokeStyle stroke;
                switch (anchor.Kind)
                {
                    case ProfileAnchorKind.PriorDayPoc:
                        brush = _anchorPocDx; stroke = null; break;
                    case ProfileAnchorKind.PriorDayVah:
                    case ProfileAnchorKind.PriorDayVal:
                    case ProfileAnchorKind.Pdh:
                    case ProfileAnchorKind.Pdl:
                    case ProfileAnchorKind.Pdm:
                        brush = _anchorVaDx; stroke = null; break;
                    case ProfileAnchorKind.NakedPoc:
                        brush = _anchorNakedDx; stroke = _dashStyle; break;
                    case ProfileAnchorKind.PriorWeekPoc:
                        brush = _anchorPwPocDx; stroke = _dashStyle; break;
                    case ProfileAnchorKind.CompositeVah:
                    case ProfileAnchorKind.CompositeVal:
                        brush = _anchorVaDx; stroke = null; break;
                    default:
                        brush = _anchorVaDx; stroke = null; break;
                }
                if (brush == null) continue;

                // Full-width horizontal line (1.5 px weight per plan)
                RenderTarget.DrawLine(
                    new Vector2((float)ChartPanel.X, y),
                    new Vector2(panelRight, y),
                    brush, 1.5f, stroke);

                // Right-gutter label: Segoe UI 9pt, right-aligned, 156×16 px
                if (_labelFont != null)
                {
                    string text = string.Format("{0} ({1:F2})", anchor.Label, price);
                    using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                       text, _labelFont, 156f, 16f))
                    {
                        RenderTarget.DrawTextLayout(new Vector2(panelRight - 160f, y - 8f), layout, brush);
                    }
                }
            }
        }

        // Renders Liquidity Walls (large persistent resting bids/asks from Rithmic L2).
        // Only shows top N walls per side ranked by max-size; only shows fresh walls (recent depth update);
        // line thickness scales with size; iceberg refills annotated with "ICE" tag.
        private void RenderLiquidityWalls(ChartScale cs, float panelRight)
        {
            if (_wallBidDx == null || _wallAskDx == null) return;
            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;
            DateTime fresh = DateTime.UtcNow.AddSeconds(-LiquidityWallStaleSec);

            // Deep-clone inside the lock — L2LevelState is a reference type with mutable long/DateTime
            // fields the data thread continues to write. Without cloning, render reads would race.
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

            DrawWallsForSide(cs, bidSnap, _wallBidDx, "BID", true,  fresh, minVis, maxVis, panelRight);
            DrawWallsForSide(cs, askSnap, _wallAskDx, "ASK", false, fresh, minVis, maxVis, panelRight);
        }

        private void DrawWallsForSide(
            ChartScale cs,
            List<KeyValuePair<double, L2LevelState>> snap,
            SharpDX.Direct2D1.Brush brush,
            string side,
            bool isBid,
            DateTime fresh,
            double minVis,
            double maxVis,
            float panelRight)
        {
            // Filter eligible walls: meet size threshold, recently updated, in visible range.
            var walls = new List<KeyValuePair<double, L2LevelState>>();
            foreach (var kv in snap)
            {
                if (kv.Value.MaxSize < LiquidityWallMin) continue;
                if (kv.Value.LastUpdate < fresh) continue;
                if (kv.Key < minVis || kv.Key > maxVis) continue;
                walls.Add(kv);
            }
            // Top N by max-size.
            walls.Sort((a, b) => b.Value.MaxSize.CompareTo(a.Value.MaxSize));
            int show = Math.Min(walls.Count, LiquidityMaxPerSide);

            for (int i = 0; i < show; i++)
            {
                double price = walls[i].Key;
                var st = walls[i].Value;
                float y = (float)cs.GetYByValue(price);
                // Line thickness scales 1.5px → 4px based on size relative to threshold.
                float thickness = (float)Math.Min(4.0, 1.5 + (st.MaxSize / (double)LiquidityWallMin) * 0.4);
                RenderTarget.DrawLine(
                    new Vector2((float)ChartPanel.X, y),
                    new Vector2(panelRight - 90, y),
                    brush, thickness);

                string label = string.Format("{0} {1:F2}  {2}{3}",
                    side, price, st.MaxSize,
                    st.RefillCount >= 2 ? " ICE×" + st.RefillCount : "");
                using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                    label, _labelFont, 180f, 16f))
                {
                    RenderTarget.DrawTextLayout(new Vector2(panelRight - 184, y - 8), layout, brush);
                }
            }
        }

        // ── Phase 18: Scorer HUD + tier marker rendering helpers ─────────────────────────────

        /// <summary>
        /// Render the 3-line Scoring HUD badge anchored top-right of the chart panel.
        /// Anchored at: x = panelRight - 200, y = ChartPanel.Y + 28
        /// (GEX status badge from DEEP6GexLevels occupies y = 4..22; 28 keeps 6px gap per spec.)
        /// Per FOOTPRINT-VISUAL-SPEC.md section 6 + 03-SPATIAL-LAYOUT.md zone SCORE_HUD.
        /// </summary>
        private void RenderScoreHud(float panelRight)
        {
            if (_hudFont == null || _hudLabelFont == null) return;
            if (_scoreHudTextDx == null || _scoreHudBgDx == null) return;

            var r = _lastScorerResult;
            // Auto-hide when score=0 and tier is QUIET/null (no signal — per typography spec).
            if (r == null) return;
            if (r.TotalScore == 0.0 && (r.Tier == SignalTier.QUIET || r.Tier == SignalTier.DISQUALIFIED))
                return;

            const float hudW   = 200f;
            const float hudH   = 62f;
            // panelRight is narrowed by MissionControlWidth in OnRender if MC panel is on,
            // so this HUD lands to the LEFT of the MC panel automatically.
            float topY = (float)ChartPanel.Y + 28f;
            float leftX = panelRight - hudW - 8f;

            // Background rectangle
            var bgRect = new RectangleF(leftX, topY, hudW, hudH);
            RenderTarget.FillRectangle(bgRect, _scoreHudBgDx);
            RenderTarget.DrawRectangle(bgRect, _scoreHudBorderDx, 1f);

            float textX     = leftX + 8f;
            float lineH     = 18f;
            float textW     = hudW - 16f;

            // Line 1: "Score: +0.87"  (12pt Consolas, primary ink; red-tinted when negative)
            string scoreLine = string.Format("Score: {0:+0.00;-0.00;+0.00}", r.TotalScore / 100.0);
            var scoreInk = (r.TotalScore < 0) ? (SharpDX.Direct2D1.Brush)_scoreTierAShortDx
                                               : (SharpDX.Direct2D1.Brush)_scoreHudTextDx;
            using (var layout1 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                scoreLine, _hudFont, textW, lineH))
            {
                RenderTarget.DrawTextLayout(new Vector2(textX, topY + 6f), layout1, scoreInk);
            }

            // Line 2: "Tier: A" with tier-specific ink
            string tierLine = "Tier: " + TierChar(r.Tier);
            var tierInk = TierBrush(r.Tier, r.Direction);
            using (var layout2 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                tierLine, _hudLabelFont, textW, lineH))
            {
                RenderTarget.DrawTextLayout(new Vector2(textX, topY + 6f + lineH), layout2, tierInk);
            }

            // Line 3: Narrative (≤40 chars, ellipsis) — TypeA only per CONTEXT.md decision;
            // TypeB/C show blank line here (narrative goes to strategy log only).
            string narrative = (r.Tier == SignalTier.TYPE_A && r.Narrative != null)
                ? TruncateEllipsis(r.Narrative, 40)
                : string.Empty;
            if (narrative.Length > 0)
            {
                using (var layout3 = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                    narrative, _hudLabelFont, textW, lineH))
                {
                    RenderTarget.DrawTextLayout(new Vector2(textX, topY + 6f + lineH * 2f), layout3, _scoreHudDimDx);
                }
            }
        }

        /// <summary>
        /// Draw a tier-coded entry marker for the given bar via NT8 Draw.* API.
        /// Called once per bar close in OnBarUpdate (Draw.* must NOT be called from OnRender).
        ///
        /// Marker placement (per FOOTPRINT-VISUAL-SPEC.md section 5):
        ///   Long signals: below bar low (further down than ABS/EXH at -4 ticks → use -8 ticks offset)
        ///   Short signals: above bar high (+8 ticks offset)
        ///
        /// Draw.Dot fallback per 18-RESEARCH.md Open Question 3: if NT8 lacks Draw.Dot, the
        /// catch handler renders a half-opacity Diamond for TypeC.
        /// </summary>
        private void DrawScorerTierMarker(int barIdx, ScorerResult scored)
        {
            if (scored == null) return;
            if (scored.Tier == SignalTier.QUIET || scored.Tier == SignalTier.DISQUALIFIED) return;
            if (scored.Direction == 0) return;

            int barsAgo = CurrentBar - barIdx;
            double entry = scored.EntryPrice > 0 ? scored.EntryPrice : Close[barsAgo];
            bool isLong = scored.Direction > 0;

            // Unique tag per bar per direction — NT8 Draw.* with same tag overwrites (idempotent on repaint).
            string suffix = (isLong ? "L" : "S") + "_" + barIdx;

            // Marker brushes: WPF brushes for Draw.* API (not SharpDX)
            Brush longBrush  = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xE6, 0x76));  // #00E676 TypeA long
            Brush shortBrush = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x17, 0x44));  // #FF1744 TypeA short
            Brush bLongB     = MakeFrozenBrush(Color.FromArgb(255, 0x66, 0xBB, 0x6A));  // #66BB6A TypeB long
            Brush bShortB    = MakeFrozenBrush(Color.FromArgb(255, 0xEF, 0x53, 0x50));  // #EF5350 TypeB short
            Brush cLongB     = MakeFrozenBrush(Color.FromArgb(178, 0x7C, 0xB3, 0x87));  // #7CB387 @70% TypeC long
            Brush cShortB    = MakeFrozenBrush(Color.FromArgb(178, 0xB8, 0x7C, 0x82));  // #B87C82 @70% TypeC short
            Brush setupGray  = MakeFrozenBrush(Color.FromArgb(210, 0x9A, 0xA0, 0xA6));  // restored gray setup marker

            // Offset from bar geometry (ABS/EXH use 4–5 ticks; tier markers use 8 ticks to prevent collision)
            double offset = 8.0 * TickSize;

            // V4: keep the legacy gray setup marker, but keep the footprint number cells hidden.
            string armedLabel = scored.SetupState == TradeSetupState.Armed
                ? (isLong ? "WAIT LONG" : "WAIT SHORT")
                : string.Empty;

            if (scored.SetupState == TradeSetupState.Setup)
            {
                double markerPrice = isLong ? entry - offset : entry + offset;
                Draw.Diamond(this, "SCORE_SETUP_" + suffix, false, barsAgo, markerPrice, setupGray);

                bool counterTrend = ShowTrendContextWarning && _trendEmaSlope != 0.0
                    && (isLong ? _trendEmaSlope < 0 : _trendEmaSlope > 0);
                string stateLabel = (isLong ? "LONG SETUP" : "SHORT SETUP") + (counterTrend ? " [CT]" : string.Empty);
                Draw.Text(this, "SCORE_SETUP_STATE_" + suffix, false, stateLabel, barsAgo, markerPrice, 0,
                    counterTrend ? Brushes.Orange : Brushes.White,
                    new SimpleFont("Arial", 9) { Bold = true },
                    System.Windows.TextAlignment.Center, null, null, 0);

                string detailLabel = string.Format("TYPE {0} | {1}/100 | {2} CAT{3}",
                    TierChar(scored.Tier),
                    (int)scored.TotalScore,
                    scored.CategoryCount,
                    scored.CategoryCount == 1 ? string.Empty : "S");
                double lblPrice = isLong ? markerPrice - 8.0 * TickSize : markerPrice + 8.0 * TickSize;
                Draw.Text(this, "SCORE_SETUP_LBL_" + suffix, detailLabel, barsAgo, lblPrice, setupGray);
                return;
            }

            switch (scored.Tier)
            {
                case SignalTier.TYPE_A:
                {
                    // TypeA: solid Diamond on signal bar, fully saturated.
                    Brush pick = isLong ? longBrush : shortBrush;
                    double markerPrice = isLong ? entry - offset : entry + offset;
                    Draw.Diamond(this, "SCORE_A_" + suffix, false, barsAgo, markerPrice, pick);

                    // Score overlaid on the diamond: "91/6" = score 91, 6 categories.
                    // White bold centered text for contrast against the colored diamond.
                    string scoreStr = string.Format("{0}/{1}", (int)scored.TotalScore, scored.CategoryCount);
                    Draw.Text(this, "SCORE_NUM_" + suffix, false, scoreStr, barsAgo, markerPrice, 0,
                        Brushes.White, new SimpleFont("Arial", 9) { Bold = true },
                        System.Windows.TextAlignment.Center, null, null, 0);

                    // V3: make direction and strength explicit on-chart.
                    double lblPrice = isLong ? markerPrice - 8.0 * TickSize : markerPrice + 8.0 * TickSize;
                    string narrative = armedLabel.Length > 0
                        ? string.Format("{0} | TYPE {1} | {2}/100", armedLabel, TierChar(scored.Tier), (int)scored.TotalScore)
                        : string.Format("{0} SIGNAL | TYPE {1} | {2}/100", isLong ? "LONG" : "SHORT", TierChar(scored.Tier), (int)scored.TotalScore);
                    Draw.Text(this, "SCORE_LBL_" + suffix, narrative, barsAgo, lblPrice, pick);
                    break;
                }
                case SignalTier.TYPE_B:
                {
                    // TypeB: triangle on signal bar — score/cats overlaid on the shape.
                    Brush pick = isLong ? bLongB : bShortB;
                    double markerPrice = isLong ? entry - offset : entry + offset;
                    if (isLong)
                        Draw.TriangleUp(this, "SCORE_B_" + suffix, false, barsAgo, markerPrice, pick);
                    else
                        Draw.TriangleDown(this, "SCORE_B_" + suffix, false, barsAgo, markerPrice, pick);

                    string scoreStr = string.Format("{0}/{1}", (int)scored.TotalScore, scored.CategoryCount);
                    Draw.Text(this, "SCORE_NUM_" + suffix, false, scoreStr, barsAgo, markerPrice, 0,
                        Brushes.White, new SimpleFont("Arial", 9) { Bold = true },
                        System.Windows.TextAlignment.Center, null, null, 0);

                    // V3: make direction and strength explicit on-chart.
                    double lblPrice = isLong ? markerPrice - 6.0 * TickSize : markerPrice + 6.0 * TickSize;
                    string stateText = armedLabel.Length > 0
                        ? string.Format("{0} | TYPE {1} | {2}/100", armedLabel, TierChar(scored.Tier), (int)scored.TotalScore)
                        : string.Format("{0} SIGNAL | TYPE {1} | {2}/100", isLong ? "LONG" : "SHORT", TierChar(scored.Tier), (int)scored.TotalScore);
                    Draw.Text(this, "SCORE_LBL_" + suffix, stateText, barsAgo, lblPrice, pick);
                    break;
                }
                case SignalTier.TYPE_C:
                {
                    // TIER 3 — informational noise. Hidden by default. Tiny 4px dim dot
                    // ONLY when explicitly toggled via ShowTier3Dots. Falls back to dim Diamond
                    // if Draw.Dot is unavailable on the host NT8 build.
                    if (!ShowTier3Dots) break;
                    Brush pick = isLong ? cLongB : cShortB;
                    double markerPrice = isLong ? entry - offset : entry + offset;
                    try
                    {
                        Draw.Dot(this, "SCORE_C_" + suffix, false, barsAgo, markerPrice, pick);
                    }
                    catch (System.MissingMethodException)
                    {
                        Draw.Diamond(this, "SCORE_C_" + suffix, false, barsAgo, markerPrice, pick);
                    }
                    break;
                }
            }
        }

        /// <summary>Returns single-char tier label for HUD line 2.</summary>
        private static string TierChar(SignalTier tier)
        {
            switch (tier)
            {
                case SignalTier.TYPE_A: return "A";
                case SignalTier.TYPE_B: return "B";
                case SignalTier.TYPE_C: return "C";
                default:               return "-";
            }
        }

        /// <summary>
        /// Returns the appropriate SharpDX brush for the given tier + direction combination.
        /// Used by RenderScoreHud for tier line ink.
        /// </summary>
        private SharpDX.Direct2D1.Brush TierBrush(SignalTier tier, int direction)
        {
            switch (tier)
            {
                case SignalTier.TYPE_A:
                    return direction >= 0 ? (SharpDX.Direct2D1.Brush)_scoreTierALongDx
                                          : (SharpDX.Direct2D1.Brush)_scoreTierAShortDx;
                case SignalTier.TYPE_B:
                    return direction >= 0 ? (SharpDX.Direct2D1.Brush)_scoreTierBLongDx
                                          : (SharpDX.Direct2D1.Brush)_scoreTierBShortDx;
                case SignalTier.TYPE_C:
                    return direction >= 0 ? (SharpDX.Direct2D1.Brush)_scoreTierCLongDx
                                          : (SharpDX.Direct2D1.Brush)_scoreTierCShortDx;
                default:
                    return (SharpDX.Direct2D1.Brush)_scoreNeutralDx;
            }
        }

        /// <summary>Truncates text to maxLen chars, appending "..." if truncated.</summary>
        private static string TruncateEllipsis(string text, int maxLen)
        {
            if (text == null) return string.Empty;
            if (text.Length <= maxLen) return text;
            return text.Substring(0, maxLen - 3) + "...";
        }

        // ─────────────────────────────────────────────────────────────────────────────────────

        #region Properties

        [NinjaScriptProperty]
        [Range(1.0, 10.0)]
        [Display(Name = "Imbalance Ratio", Order = 1, GroupName = "1. Detection")]
        public double ImbalanceRatio { get; set; }

        [NinjaScriptProperty]
        [Range(5.0, 80.0)]
        [Display(Name = "Absorption Wick Min %", Order = 2, GroupName = "1. Detection")]
        public double AbsorbWickMinPct { get; set; }

        [NinjaScriptProperty]
        [Range(5.0, 80.0)]
        [Display(Name = "Exhaustion Wick Min %", Order = 3, GroupName = "1. Detection")]
        public double ExhaustWickMinPct { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Footprint Cells", Order = 10, GroupName = "2. Display")]
        public bool ShowFootprintCells { get; set; }

        // ▰▰▰ MISSION CONTROL right-side panel ▰▰▰
        [NinjaScriptProperty]
        [Display(Name = "Show Mission Control Panel", Order = 1, GroupName = "8. Mission Control")]
        public bool ShowMissionControl { get; set; }

        [NinjaScriptProperty]
        [Range(140, 360)]
        [Display(Name = "Panel Width (px)", Order = 2, GroupName = "8. Mission Control")]
        public int MissionControlWidth { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show ACTIVE SIGNAL Section", Order = 3, GroupName = "8. Mission Control")]
        public bool ShowMcActiveSignal { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Status Section", Order = 4, GroupName = "8. Mission Control")]
        public bool ShowMcStatus { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Day P&L Section", Order = 5, GroupName = "8. Mission Control")]
        public bool ShowMcDayPnL { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Position Section", Order = 6, GroupName = "8. Mission Control")]
        public bool ShowMcPosition { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Signals (44) Section", Order = 7, GroupName = "8. Mission Control")]
        public bool ShowMcSignalsList { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show FLATTEN ALL Action Bar", Order = 8, GroupName = "8. Mission Control")]
        public bool ShowMcActionBar { get; set; }

        // ▰▰▰ 3-tier signal clarity ▰▰▰
        [NinjaScriptProperty]
        [Display(Name = "TIER 1 Chart Overlay (entry/stop/target lines)", Order = 1, GroupName = "9. Signal Tiers")]
        public bool ShowTier1Overlay { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "TIER 3 Dots (informational noise — off by default)", Order = 2, GroupName = "9. Signal Tiers")]
        public bool ShowTier3Dots { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Active Signal Valid (bars)", Order = 3, GroupName = "9. Signal Tiers")]
        public int ArmedSignalValidBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Counter-Trend Warning [CT]", Order = 4, GroupName = "9. Signal Tiers",
                 Description = "Appends [CT] in orange to LONG SETUP / SHORT SETUP labels when the signal opposes the trend EMA slope.")]
        public bool ShowTrendContextWarning { get; set; }

        [NinjaScriptProperty]
        [Range(5, 200)]
        [Display(Name = "Trend EMA Period", Order = 5, GroupName = "9. Signal Tiers",
                 Description = "EMA period used to compute trend direction for the [CT] counter-trend warning. Default 20.")]
        public int TrendEmaPeriod { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show POC", Order = 11, GroupName = "2. Display")]
        public bool ShowPoc { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Value Area", Order = 12, GroupName = "2. Display")]
        public bool ShowValueArea { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Absorption Markers", Order = 13, GroupName = "2. Display")]
        public bool ShowAbsorptionMarkers { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Exhaustion Markers", Order = 14, GroupName = "2. Display")]
        public bool ShowExhaustionMarkers { get; set; }

        [NinjaScriptProperty]
        [Range(7f, 16f)]
        [Display(Name = "Cell Font Size", Order = 15, GroupName = "2. Display")]
        public float CellFontSize { get; set; }

        [NinjaScriptProperty]
        [Range(40, 200)]
        [Display(Name = "Cell Column Width (px)", Order = 16, GroupName = "2. Display")]
        public int CellColumnWidth { get; set; }

        // --- Profile Anchor Levels ---

        [NinjaScriptProperty]
        [Display(Name = "Show Profile Anchors", Order = 20, GroupName = "3. Profile Anchors")]
        public bool ShowProfileAnchors { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Prior-Day Levels", Order = 21, GroupName = "3. Profile Anchors")]
        public bool ShowPriorDayLevels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Naked POCs", Order = 22, GroupName = "3. Profile Anchors")]
        public bool ShowNakedPocs { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Composite 5-Day VA", Order = 23, GroupName = "3. Profile Anchors")]
        public bool ShowCompositeVA { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Naked POC Max Age (sessions)", Order = 24, GroupName = "3. Profile Anchors")]
        public int NakedPocMaxAgeSessions { get; set; }

        // Anchor brush properties

        [XmlIgnore]
        [Display(Name = "Anchor POC Color",       Order = 40, GroupName = "4. Colors")]
        public Brush AnchorPocBrush { get; set; }
        [Browsable(false)] public string AnchorPocBrushSerialize       { get { return Serialize.BrushToString(AnchorPocBrush); }       set { AnchorPocBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Anchor VA Color",        Order = 41, GroupName = "4. Colors")]
        public Brush AnchorVaBrush { get; set; }
        [Browsable(false)] public string AnchorVaBrushSerialize        { get { return Serialize.BrushToString(AnchorVaBrush); }        set { AnchorVaBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Anchor Naked POC Color", Order = 42, GroupName = "4. Colors")]
        public Brush AnchorNakedBrush { get; set; }
        [Browsable(false)] public string AnchorNakedBrushSerialize     { get { return Serialize.BrushToString(AnchorNakedBrush); }     set { AnchorNakedBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Anchor PW POC Color",    Order = 43, GroupName = "4. Colors")]
        public Brush AnchorPwPocBrush { get; set; }
        [Browsable(false)] public string AnchorPwPocBrushSerialize     { get { return Serialize.BrushToString(AnchorPwPocBrush); }     set { AnchorPwPocBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Anchor Composite VA",    Order = 44, GroupName = "4. Colors")]
        public Brush AnchorCompositeBrush { get; set; }
        [Browsable(false)] public string AnchorCompositeBrushSerialize { get { return Serialize.BrushToString(AnchorCompositeBrush); } set { AnchorCompositeBrush = Serialize.StringToBrush(value); } }

        [NinjaScriptProperty]
        [Display(Name = "Show Liquidity Walls (Rithmic L2)", Order = 30, GroupName = "5. Liquidity (L2)")]
        public bool ShowLiquidityWalls { get; set; }

        [NinjaScriptProperty]
        [Range(10, 5000)]
        [Display(Name = "Wall Min Size (contracts)", Order = 31, GroupName = "5. Liquidity (L2)")]
        public int LiquidityWallMin { get; set; }

        [NinjaScriptProperty]
        [Range(10, 600)]
        [Display(Name = "Wall Stale (seconds)", Order = 32, GroupName = "5. Liquidity (L2)",
                 Description = "Hide a wall if its price level hasn't seen a depth update in this many seconds")]
        public int LiquidityWallStaleSec { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Max Walls Per Side", Order = 33, GroupName = "5. Liquidity (L2)")]
        public int LiquidityMaxPerSide { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Chart Trader Toolbar", Order = 40, GroupName = "6. Chart Trader",
                 Description = "Top-left clickable on/off buttons for each feature so you can toggle live during trading")]
        public bool ShowChartTrader { get; set; }

        // --- Phase 18: Scorer HUD ---

        [Display(Name = "Show Score HUD", Order = 1, GroupName = "7. DEEP6 Scorer",
                 Description = "Display the 3-line scoring HUD badge (Score / Tier / Narrative) in the top-right corner")]
        public bool ShowScoreHud { get; set; }

        [Range(0, 100)]
        [Display(Name = "Score HUD Padding (px)", Order = 2, GroupName = "7. DEEP6 Scorer",
                 Description = "Horizontal padding between the right edge of the chart panel and the HUD badge")]
        public int ScoreHudPaddingPx { get; set; }

        // --- Brush properties (require *Serialize string companions for XML serialization) ---

        [XmlIgnore]
        [Display(Name = "Bid Cell Color",      Order = 30, GroupName = "4. Colors")]
        public Brush BidCellBrush { get; set; }
        [Browsable(false)] public string BidCellBrushSerialize     { get { return Serialize.BrushToString(BidCellBrush); }     set { BidCellBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Ask Cell Color",      Order = 31, GroupName = "4. Colors")]
        public Brush AskCellBrush { get; set; }
        [Browsable(false)] public string AskCellBrushSerialize     { get { return Serialize.BrushToString(AskCellBrush); }     set { AskCellBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Cell Text Color",     Order = 32, GroupName = "4. Colors")]
        public Brush CellTextBrush { get; set; }
        [Browsable(false)] public string CellTextBrushSerialize    { get { return Serialize.BrushToString(CellTextBrush); }    set { CellTextBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "POC Color",           Order = 33, GroupName = "4. Colors")]
        public Brush PocBrush { get; set; }
        [Browsable(false)] public string PocBrushSerialize         { get { return Serialize.BrushToString(PocBrush); }         set { PocBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "VAH Color",           Order = 34, GroupName = "4. Colors")]
        public Brush VahBrush { get; set; }
        [Browsable(false)] public string VahBrushSerialize         { get { return Serialize.BrushToString(VahBrush); }         set { VahBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "VAL Color",           Order = 35, GroupName = "4. Colors")]
        public Brush ValBrush { get; set; }
        [Browsable(false)] public string ValBrushSerialize         { get { return Serialize.BrushToString(ValBrush); }         set { ValBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Imbalance Buy Color", Order = 36, GroupName = "4. Colors")]
        public Brush ImbalanceBuyBrush { get; set; }
        [Browsable(false)] public string ImbalanceBuyBrushSerialize{ get { return Serialize.BrushToString(ImbalanceBuyBrush); }set { ImbalanceBuyBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Imbalance Sell Color",Order = 37, GroupName = "4. Colors")]
        public Brush ImbalanceSellBrush { get; set; }
        [Browsable(false)] public string ImbalanceSellBrushSerialize{ get { return Serialize.BrushToString(ImbalanceSellBrush); } set { ImbalanceSellBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Wall Bid (resting buy)",  Order = 50, GroupName = "4. Colors")]
        public Brush WallBidBrush { get; set; }
        [Browsable(false)] public string WallBidBrushSerialize { get { return Serialize.BrushToString(WallBidBrush); } set { WallBidBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Wall Ask (resting sell)", Order = 51, GroupName = "4. Colors")]
        public Brush WallAskBrush { get; set; }
        [Browsable(false)] public string WallAskBrushSerialize { get { return Serialize.BrushToString(WallAskBrush); } set { WallAskBrush = Serialize.StringToBrush(value); } }

        // ──── Group 8: V2 Features ────────────────────────────────────────────────

        [NinjaScriptProperty]
        [Display(Name = "Show VWAP", Order = 1, GroupName = "8. V2 Features",
                 Description = "Session VWAP line (white, full-width)")]
        public bool ShowVWAP { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show VWAP Bands (±1σ / ±2σ)", Order = 2, GroupName = "8. V2 Features",
                 Description = "Volume-weighted standard deviation bands around VWAP (dashed cyan)")]
        public bool ShowVWAPBands { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Initial Balance (9:30-10:30)", Order = 3, GroupName = "8. V2 Features",
                 Description = "Initial Balance High/Low lines (first 60 one-minute bars of RTH session)")]
        public bool ShowInitialBalance { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Heatmap Mode", Order = 4, GroupName = "8. V2 Features",
                 Description = "ATAS-style: cell background intensity scales with volume magnitude (amber gradient). Layers under imbalance fills.")]
        public bool ShowHeatmapMode { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Stacked Zone Boxes", Order = 5, GroupName = "8. V2 Features",
                 Description = "Draw bounding box around stacked imbalance rows (≥3 consecutive same-direction). Tier 1=thin, Tier 3=thick.")]
        public bool ShowStackedZoneBoxes { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Unfinished Auction Lines", Order = 6, GroupName = "8. V2 Features",
                 Description = "Persistent dashed line at bar highs/lows with both-sided volume (unfinished auction) until price revisits")]
        public bool ShowUnfinishedAuctionLines { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Large Lot Overlay", Order = 7, GroupName = "8. V2 Features",
                 Description = "White dot on cells where a single print ≥ LargeLotThreshold contracts executed")]
        public bool ShowLargeLotOverlay { get; set; }

        [NinjaScriptProperty]
        [Range(10, 500)]
        [Display(Name = "Large Lot Threshold (contracts)", Order = 8, GroupName = "8. V2 Features",
                 Description = "Minimum contracts per single print to mark as institutional large lot. NQ default: 50.")]
        public int LargeLotThreshold { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Bull/Bear Column Tint", Order = 9, GroupName = "8. V2 Features",
                 Description = "Cyan tint on bars where every price row has positive delta (bull column); magenta on all-negative (bear column)")]
        public bool ShowBullBearColumn { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Volume Climax Markers", Order = 10, GroupName = "8. V2 Features",
                 Description = "Bold horizontal line at bar extreme when volume > VolClimaxMultiplier × EMA(20) at an N-bar high or low")]
        public bool ShowVolumeClimax { get; set; }

        [NinjaScriptProperty]
        [Range(1.5, 5.0)]
        [Display(Name = "Volume Climax Multiplier (× VolEMA)", Order = 11, GroupName = "8. V2 Features",
                 Description = "Bar total volume must exceed VolEMA × this multiplier to qualify as a climax bar. NQ default: 2.5.")]
        public double VolClimaxMultiplier { get; set; }

        #endregion
    }
}
#region NinjaScript generated code. Neither change nor remove.
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6.DEEP6FootprintV4[] cacheDEEP6FootprintV4;
        public DEEP6.DEEP6FootprintV4 DEEP6FootprintV4(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader)
        {
            return DEEP6FootprintV4(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader);
        }

        public DEEP6.DEEP6FootprintV4 DEEP6FootprintV4(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader)
        {
            if (cacheDEEP6FootprintV4 != null)
                for (int idx = 0; idx < cacheDEEP6FootprintV4.Length; idx++)
                    if (cacheDEEP6FootprintV4[idx] != null && cacheDEEP6FootprintV4[idx].ImbalanceRatio == imbalanceRatio && cacheDEEP6FootprintV4[idx].AbsorbWickMinPct == absorbWickMinPct && cacheDEEP6FootprintV4[idx].ExhaustWickMinPct == exhaustWickMinPct && cacheDEEP6FootprintV4[idx].ShowFootprintCells == showFootprintCells && cacheDEEP6FootprintV4[idx].ShowPoc == showPoc && cacheDEEP6FootprintV4[idx].ShowValueArea == showValueArea && cacheDEEP6FootprintV4[idx].ShowAbsorptionMarkers == showAbsorptionMarkers && cacheDEEP6FootprintV4[idx].ShowExhaustionMarkers == showExhaustionMarkers && cacheDEEP6FootprintV4[idx].CellFontSize == cellFontSize && cacheDEEP6FootprintV4[idx].CellColumnWidth == cellColumnWidth && cacheDEEP6FootprintV4[idx].ShowProfileAnchors == showProfileAnchors && cacheDEEP6FootprintV4[idx].ShowPriorDayLevels == showPriorDayLevels && cacheDEEP6FootprintV4[idx].ShowNakedPocs == showNakedPocs && cacheDEEP6FootprintV4[idx].ShowCompositeVA == showCompositeVA && cacheDEEP6FootprintV4[idx].NakedPocMaxAgeSessions == nakedPocMaxAgeSessions && cacheDEEP6FootprintV4[idx].ShowLiquidityWalls == showLiquidityWalls && cacheDEEP6FootprintV4[idx].LiquidityWallMin == liquidityWallMin && cacheDEEP6FootprintV4[idx].LiquidityWallStaleSec == liquidityWallStaleSec && cacheDEEP6FootprintV4[idx].LiquidityMaxPerSide == liquidityMaxPerSide && cacheDEEP6FootprintV4[idx].ShowChartTrader == showChartTrader && cacheDEEP6FootprintV4[idx].EqualsInput(input))
                        return cacheDEEP6FootprintV4[idx];
            return CacheIndicator<DEEP6.DEEP6FootprintV4>(new DEEP6.DEEP6FootprintV4() { ImbalanceRatio = imbalanceRatio, AbsorbWickMinPct = absorbWickMinPct, ExhaustWickMinPct = exhaustWickMinPct, ShowFootprintCells = showFootprintCells, ShowPoc = showPoc, ShowValueArea = showValueArea, ShowAbsorptionMarkers = showAbsorptionMarkers, ShowExhaustionMarkers = showExhaustionMarkers, CellFontSize = cellFontSize, CellColumnWidth = cellColumnWidth, ShowProfileAnchors = showProfileAnchors, ShowPriorDayLevels = showPriorDayLevels, ShowNakedPocs = showNakedPocs, ShowCompositeVA = showCompositeVA, NakedPocMaxAgeSessions = nakedPocMaxAgeSessions, ShowLiquidityWalls = showLiquidityWalls, LiquidityWallMin = liquidityWallMin, LiquidityWallStaleSec = liquidityWallStaleSec, LiquidityMaxPerSide = liquidityMaxPerSide, ShowChartTrader = showChartTrader }, input, ref cacheDEEP6FootprintV4);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6.DEEP6FootprintV4 DEEP6FootprintV4(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader)
        {
            return indicator.DEEP6FootprintV4(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader);
        }

        public Indicators.DEEP6.DEEP6FootprintV4 DEEP6FootprintV4(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader)
        {
            return indicator.DEEP6FootprintV4(input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader);
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.DEEP6.DEEP6FootprintV4 DEEP6FootprintV4(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader)
        {
            return indicator.DEEP6FootprintV4(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader);
        }

        public Indicators.DEEP6.DEEP6FootprintV4 DEEP6FootprintV4(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader)
        {
            return indicator.DEEP6FootprintV4(input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader);
        }
    }
}

#endregion
