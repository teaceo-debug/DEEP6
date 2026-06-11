// DEEP6 Footprint V7 — NinjaTrader 8 indicator.
//
// This file contains the DEEP6 Footprint V7 indicator: a simplified, low-noise
// execution-focused fork of V6 with clearer plain-English signal states.
//
// It preserves the footprint / scorer / profile-anchor core while trimming
// on-chart clutter so long/short readiness and trigger state are obvious.
//
// This file contains the main DEEP6 Footprint V7 indicator: the FootprintBar / Cell
// data structures, AbsorptionDetector (4 variants + VAH/VAL bonus),
// ExhaustionDetector (6 variants + delta gate + cooldown), and profile-anchor
// overlay (prior-day POC/VAH/VAL, PDH/PDL/PDM, naked POCs, prior-week POC).
//
// Options/gamma overlay lives in the companion DEEP6 indicator — add it separately.
//
// Drop-in install: copy this file to
//   %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\DEEP6FootprintV7.cs
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
using NinjaTrader.NinjaScript.AddOns.DEEP6.Levels;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge;
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
    public class DEEP6FootprintV7 : Indicator
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

        // session reset tracking
        private DateTime _lastSessionDate = DateTime.MinValue;

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
        // Bar index when the latest signal was scored. Used to expire stale armed signals
        // so the MC ACTIVE SIGNAL section + TIER 1 chart overlay only show recent ones.
        private int _armedSignalBarIndex = -1;
        private ScorerResult _activeTradeSetup;
        private int _activeSetupBarIndex = -1;
        private double _activeInvalidationPrice = double.NaN;
        private int _sessionBarCount;

        // ---- Profile Anchor Levels ----
        private ProfileAnchorLevels _profileAnchors = new ProfileAnchorLevels();
        private DateTime _profileSessionDate = DateTime.MinValue;

        // SharpDX brushes (device-dependent)
        private SharpDX.Direct2D1.Brush _bidDx, _askDx, _textDx, _imbalBuyDx, _imbalSellDx,
                                         _pocDx, _vahDx, _valDx, _gridDx,
                                         _wallBidDx, _wallAskDx;

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
                Description         = "DEEP6 Footprint V7 — low-noise execution footprint with plain-English setup, ready, and triggered signals.";
                Name                = "DEEP6 Footprint V7";
                Calculate           = Calculate.OnEachTick;
                IsOverlay           = true;
                DisplayInDataBox    = false;
                DrawOnPricePanel    = true;
                PaintPriceMarkers   = false;
                ScaleJustification  = ScaleJustification.Right;
                IsSuspendedWhileInactive = true;

                // Defaults
                ImbalanceRatio          = 3.0;
                ShowFootprintCells      = true;
                ShowAbsorptionMarkers   = false;
                ShowExhaustionMarkers   = false;
                ShowPoc                 = true;
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

                // ▰▰▰ MISSION CONTROL right-side panel — TradeDevils-style sidebar (Option F) ▰▰▰
                ShowMissionControl      = false;
                MissionControlWidth     = 240;
                ShowMcActiveSignal      = true;
                ShowMcStatus            = true;
                ShowMcDayPnL            = true;
                ShowMcPosition          = true;
                ShowMcSignalsList       = true;
                ShowMcActionBar         = true;

                // ▰▰▰ 3-tier signal clarity — TIER 1 lines/callout + TIER 3 dots toggle ▰▰▰
                ShowTier1Overlay        = true;
                ShowTier3Dots           = false;   // hidden by default — informational noise
                ArmedSignalValidBars    = 3;       // Scalp signals expire quickly on the five-minute chart

                // Phase 18: Scorer HUD defaults
                ShowScoreHud        = false;
                ScoreHudPaddingPx   = 12;

                ShowProfileAnchors     = true;
                ShowPriorDayLevels     = true;
                ShowNakedPocs          = false;
                ShowCompositeVA        = false;
                NakedPocMaxAgeSessions = 20;

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
                _volEma = 0.0;
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
                try { ScorerSharedState.Clear(Instrument != null ? Instrument.FullName : null); } catch { }
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
            }
        }

        // ---- L2 depth intake — populates _l2Bids / _l2Asks for Liquidity Wall detection ----

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (e.Position >= 10) return;   // only top 10 ladder rungs

            int side;
            Dictionary<double, L2LevelState> dict;
            if (e.MarketDataType == MarketDataType.Bid) { dict = _l2Bids; side = 0; _bestBid = e.Price; }
            else if (e.MarketDataType == MarketDataType.Ask) { dict = _l2Asks; side = 1; _bestAsk = e.Price; }
            else return;

            long newSize = e.Operation == Operation.Remove ? 0 : (long)e.Volume;
            long? priorSize = null;

            if (_scorerRegistry != null && _scorerSession != null)
            {
                _scorerSession.BestBid = _bestBid;
                _scorerSession.BestAsk = _bestAsk;
            }

            if (!ShowLiquidityWalls)
            {
                if (_scorerRegistry != null && _scorerSession != null)
                    _scorerRegistry.DispatchDepth(_scorerSession, side, e.Position, e.Price, (double)newSize, (double)(priorSize ?? 0));
                return;
            }

            lock (_l2Lock)
            {
                L2LevelState st;
                if (!dict.TryGetValue(e.Price, out st))
                {
                    st = new L2LevelState();
                    dict[e.Price] = st;
                }
                priorSize = st.CurrentSize;
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

            if (_scorerRegistry != null && _scorerSession != null)
                _scorerRegistry.DispatchDepth(_scorerSession, side, e.Position, e.Price, (double)newSize, (double)(priorSize ?? 0));
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
            if (_lastSessionDate == DateTime.MinValue)
                _lastSessionDate = Bars.GetTime(prevIdx).Date;
            bool isNewSessionBar = currentSessionDate != _lastSessionDate;

            // Reconcile OHLC with NT8's authoritative bar (handles silent-tick edge case).
            prev.Open = Bars.GetOpen(prevIdx);
            prev.High = Bars.GetHigh(prevIdx);
            prev.Low  = Bars.GetLow(prevIdx);
            prev.Close= Bars.GetClose(prevIdx);
            if (!_finalizedBars.Contains(prevIdx))
            {
                prev.Finalize(_priorCvd);
                _finalizedBars.Add(prevIdx);
            }
            _priorCvd = prev.Cvd;

            // Update rolling ATR / vol EMA.
            _atrWindow.Enqueue(prev.BarRange);
            while (_atrWindow.Count > AtrPeriod) _atrWindow.Dequeue();
            double sum = 0; foreach (var v in _atrWindow) sum += v;
            _atr = _atrWindow.Count == 0 ? 1.0 : Math.Max(sum / _atrWindow.Count, 0.25);
            _volEma = _volEma == 0 ? prev.TotalVol : _volEma + VolEmaAlpha * (prev.TotalVol - _volEma);

            // Advance any existing scalp setup before scoring the just-closed bar for a new one.
            AdvanceVersionTwoLifecycle(prevIdx, prev);
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

                var sharedResult = _lastScorerResult ?? scored;
                ScorerSharedState.Publish(Instrument.FullName, prevIdx, sharedResult, _scorerSession.SessionAvgAtr);
                DrawScorerTierMarker(prevIdx, scored);
            }

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

            string scalpFamily = DetectScalpFamily(scored);
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

            var anchorSnap = _profileAnchors.BuildSnapshot();
            ProfileAnchor linkedAnchor = SelectLinkedProfileAnchor(anchorSnap, barClose, scored.Direction);
            if (linked == null && linkedAnchor != null)
            {
                scored.LinkedLevelKind = linkedAnchor.Label;
                scored.LinkedLevelPrice = linkedAnchor.Price;
                scored.LinkedLevelDistanceTicks = TickSize > 0
                    ? System.Math.Abs(linkedAnchor.Price - barClose) / TickSize
                    : System.Math.Abs(linkedAnchor.Price - barClose);
            }

            bool nearStructure = scored.LinkedLevelDistanceTicks <= (scalpFamily == "PULLBACK" ? 4.0 : 8.0);
            bool allowArmed = scalpFamily == "REVERSAL"
                ? nearStructure && scored.Tier != SignalTier.TYPE_C
                : nearStructure && scored.Tier == SignalTier.TYPE_A;

            scored.Confidence = scored.TotalScore + (nearStructure ? 6.0 : 0.0) + (linked != null ? 4.0 : 0.0);
            scored.SetupState = allowArmed ? TradeSetupState.Armed : TradeSetupState.Setup;
            _armedSignalBarIndex = allowArmed ? signalBarIdx : -1;
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
                if (_scorerSession != null)
                    ScorerSharedState.Publish(Instrument.FullName, barIdx, active, _scorerSession.SessionAvgAtr);
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
                    if (_scorerSession != null)
                        ScorerSharedState.Publish(Instrument.FullName, barIdx, active, _scorerSession.SessionAvgAtr);
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
            if (_scorerSession != null)
                ScorerSharedState.Publish(Instrument.FullName, barIdx, active, _scorerSession.SessionAvgAtr);
            DrawTriggeredMarker(barIdx, closedBar.Close, isLong);
        }

        private double ComputeVersionTwoInvalidationPrice(ScorerResult scored)
        {
            if (scored == null) return double.NaN;
            string scalpFamily = DetectScalpFamily(scored);
            double ticks = scalpFamily == "PULLBACK"
                ? (scored.SetupState == TradeSetupState.Armed ? 5.0 : 4.0)
                : (scored.SetupState == TradeSetupState.Armed ? 8.0 : 6.0);
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
                Draw.ArrowUp(this, "V7_TRIGGER_" + suffix, false, barsAgo, price - 6.0 * TickSize, pick);
            else
                Draw.ArrowDown(this, "V7_TRIGGER_" + suffix, false, barsAgo, price + 6.0 * TickSize, pick);

            Draw.Text(this, "V7_TRIGGER_LBL_" + suffix, isLong ? "Long Triggered" : "Short Triggered",
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

        private static ProfileAnchor SelectLinkedProfileAnchor(ProfileAnchorSnapshot snap, double price, int direction)
        {
            if (snap == null || snap.Levels == null || snap.Levels.Count == 0)
                return null;

            ProfileAnchor best = null;
            double bestDist = double.MaxValue;
            for (int i = 0; i < snap.Levels.Count; i++)
            {
                var anchor = snap.Levels[i];
                if (anchor == null) continue;

                bool supported = anchor.Kind == ProfileAnchorKind.PriorDayPoc
                    || anchor.Kind == ProfileAnchorKind.PriorDayVah
                    || anchor.Kind == ProfileAnchorKind.PriorDayVal
                    || anchor.Kind == ProfileAnchorKind.NakedPoc
                    || anchor.Kind == ProfileAnchorKind.PriorWeekPoc
                    || anchor.Kind == ProfileAnchorKind.Pdh
                    || anchor.Kind == ProfileAnchorKind.Pdl;
                if (!supported) continue;

                double dist = System.Math.Abs(anchor.Price - price);
                double rank = dist;
                if (direction > 0 && (anchor.Kind == ProfileAnchorKind.PriorDayVal || anchor.Kind == ProfileAnchorKind.Pdl || anchor.Kind == ProfileAnchorKind.NakedPoc))
                    rank -= 1000000.0;
                else if (direction < 0 && (anchor.Kind == ProfileAnchorKind.PriorDayVah || anchor.Kind == ProfileAnchorKind.Pdh || anchor.Kind == ProfileAnchorKind.NakedPoc))
                    rank -= 1000000.0;

                if (rank < bestDist)
                {
                    bestDist = rank;
                    best = anchor;
                }
            }

            return best;
        }

        private static bool HasCategory(ScorerResult scored, string category)
        {
            if (scored == null || scored.CategoriesFiring == null || string.IsNullOrEmpty(category))
                return false;
            for (int i = 0; i < scored.CategoriesFiring.Length; i++)
            {
                if (string.Equals(scored.CategoriesFiring[i], category, System.StringComparison.OrdinalIgnoreCase))
                    return true;
            }
            return false;
        }

        private static string DetectScalpFamily(ScorerResult scored)
        {
            bool reversal = HasCategory(scored, "absorption")
                || HasCategory(scored, "exhaustion")
                || HasCategory(scored, "trapped")
                || HasCategory(scored, "auction");
            bool continuation = HasCategory(scored, "imbalance")
                || HasCategory(scored, "delta")
                || HasCategory(scored, "volume_profile")
                || HasCategory(scored, "poc");

            if (reversal && !continuation) return "REVERSAL";
            if (continuation && !reversal) return "PULLBACK";
            if (reversal) return "REVERSAL";
            return "PULLBACK";
        }

        private string GetSignalHeadline(ScorerResult scored)
        {
            if (scored == null || scored.Direction == 0)
                return "No Signal";

            string direction = scored.Direction > 0 ? "Long" : "Short";
            switch (scored.SetupState)
            {
                case TradeSetupState.Setup:
                    return string.Format("Potential {0}", direction);
                case TradeSetupState.Armed:
                    return string.Format("{0} Ready", direction);
                case TradeSetupState.Triggered:
                    return string.Format("{0} Triggered", direction);
                case TradeSetupState.Invalid:
                    return string.Format("{0} Canceled", direction);
                case TradeSetupState.Expired:
                    return string.Format("{0} Expired", direction);
                default:
                    return string.Format("{0} Signal", direction);
            }
        }

        private string GetSignalDetailText(ScorerResult scored)
        {
            if (scored == null)
                return string.Empty;

            string family = DetectScalpFamily(scored) == "REVERSAL" ? "Reversal" : "Pullback";
            string anchor = string.IsNullOrWhiteSpace(scored.LinkedLevelKind) ? family : scored.LinkedLevelKind;
            string triggerSide = scored.Direction > 0 ? "above" : "below";
            int barsLeft = System.Math.Max(0, scored.ExpireAfterBarIndex - CurrentBar);

            switch (scored.SetupState)
            {
                case TradeSetupState.Setup:
                    return string.Format("{0} | {1}", family, anchor);
                case TradeSetupState.Armed:
                    if (!double.IsNaN(_activeInvalidationPrice))
                        return string.Format("{0} | Entry {1:F2} | Risk {2:F2} | {3} bars left", family, scored.EntryPrice, _activeInvalidationPrice, barsLeft);
                    return string.Format("{0} | Entry {1:F2} | {2} bars left", family, scored.EntryPrice, barsLeft);
                case TradeSetupState.Triggered:
                    return string.Format("{0} | Triggered {1} {2:F2}", family, triggerSide, scored.EntryPrice);
                case TradeSetupState.Invalid:
                    if (!double.IsNaN(_activeInvalidationPrice))
                        return string.Format("{0} | Lost {1:F2}", family, _activeInvalidationPrice);
                    return string.Format("{0} | Canceled", family);
                case TradeSetupState.Expired:
                    return string.Format("{0} | No trigger", family);
                default:
                    return string.Format("{0} | Entry {1:F2}", family, scored.EntryPrice);
            }
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
            else brush = Brushes.SlateGray;
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

            // ▶ TIER 1 (TYPE_A) chart overlay: setup/direction/trigger callouts only.
            // Renders BEFORE cells so cells overlay on top — visual layering rule.
            if (ShowTier1Overlay) RenderTier1Overlay(chartControl, chartScale, panelRight);

            // Chart Trader toolbar (top-left, on top of cells but under entry cards)
            if (ShowChartTrader) RenderChartTrader();

            // Profile anchor levels (prior-day POC/VAH/VAL, PDH/PDL/PDM, naked POCs, prior-week POC)
            if (ShowProfileAnchors) RenderProfileAnchors(chartControl, chartScale, panelRight);

            // Liquidity Walls from Rithmic L2 — large persistent resting orders
            if (ShowLiquidityWalls)
                RenderLiquidityWalls(chartScale, panelRight);

            bool showFootprintArea = ShowFootprintCells || ShowPoc || ShowValueArea;
            if (showFootprintArea)
            {
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

                    if (ShowFootprintCells)
                    {
                        foreach (var kv in fbar.Levels)
                        {
                            double px = kv.Key;
                            var cell = kv.Value;
                            float yCenter = chartScale.GetYByValue(px);
                            float yTop = yCenter - rowH / 2f;
                            var rect = new RectangleF(xLeft, yTop, colW, rowH);

                            long diagBid = GetBid(fbar, px + tickSize);
                            long diagAsk = GetAsk(fbar, px - tickSize);
                            double buyRatio  = cell.AskVol > 0 ? cell.AskVol / Math.Max(1.0, (double)diagBid) : 0;
                            double sellRatio = cell.BidVol > 0 ? cell.BidVol / Math.Max(1.0, (double)diagAsk) : 0;

                            SharpDX.Direct2D1.Brush cellFillBrush = null;
                            bool isExtreme = false;
                            bool isBuyExtreme = false;
                            if      (buyRatio  >= 8.0)               { cellFillBrush = _pwCyanFillDx;  isExtreme = true; isBuyExtreme = true; }
                            else if (buyRatio  >= 5.0)                 cellFillBrush = _pwCyanFillDx;
                            else if (buyRatio  >= ImbalanceRatio)      cellFillBrush = _pwAmberFillDx;
                            else if (sellRatio >= 8.0)               { cellFillBrush = _pwMagFillDx;   isExtreme = true; isBuyExtreme = false; }
                            else if (sellRatio >= 5.0)                 cellFillBrush = _pwMagFillDx;
                            else if (sellRatio >= ImbalanceRatio)      cellFillBrush = _pwAmberFillDx;
                            if (cellFillBrush != null)
                                RenderTarget.FillRectangle(rect, cellFillBrush);

                            // V6 intentionally removes the per-cell bid/ask number text from V1.
                            // Keep the cell fills/brackets/markers, but do not draw the gray left/right numbers.
                            if (isExtreme)
                            {
                                var bracketBrush = isBuyExtreme
                                    ? (SharpDX.Direct2D1.Brush)_pwAeroCyanDx
                                    : (SharpDX.Direct2D1.Brush)_pwAeroMagentaDx;
                                DrawCornerBrackets(rect, bracketBrush, 6f, 1.5f);
                            }
                        }
                    }

                    if (ShowPoc && fbar.PocPrice > 0)
                    {
                        float yPoc = chartScale.GetYByValue(fbar.PocPrice);
                        var pocRect = new RectangleF(xLeft, yPoc - 1, colW, 2);
                        RenderTarget.FillRectangle(pocRect, _pwSectorPurpleDx ?? (SharpDX.Direct2D1.SolidColorBrush)_pocDx);
                    }

                    if (ShowValueArea)
                    {
                        var va = FootprintBar.ComputeValueArea(fbar, tickSize);
                        float yVah = chartScale.GetYByValue(va.vah);
                        float yVal = chartScale.GetYByValue(va.val);
                        RenderTarget.DrawLine(new Vector2(xLeft, yVah), new Vector2(xLeft + colW, yVah), _vahDx, 1f);
                        RenderTarget.DrawLine(new Vector2(xLeft, yVal), new Vector2(xLeft + colW, yVal), _valDx, 1f);
                    }
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
        private bool IsArmedSignalValid()
        {
            if (_armedSignalBarIndex < 0) return false;
            int age = CurrentBar - _armedSignalBarIndex;
            return age >= 0 && age <= ArmedSignalValidBars;
        }

        // ▰▰▰ MINIMALIST HUD — Formula 1 / Bloomberg hybrid, typography-only, zero chrome ▰▰▰
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
            float w = Math.Min(MissionControlWidth, Math.Max(160f, (float)ChartPanel.W - 32f));
            float x = chartRight - w - 16f;
            float y = chartTop + 16f;

            var sr = _lastScorerResult;
            bool armed = sr != null && sr.Tier == SignalTier.TYPE_A && sr.Direction != 0
                         && IsArmedSignalValid();

            // ── Line 1 (HERO 32pt): the only thing that screams ──
            //    Armed:  "▶ BUY 21452.25"  in cyan, or  "▶ SELL 21452.25"  in magenta
            //    Idle:   "—" in dim grey (deliberate emptiness — restraint signals quality)
            string heroText;
            SharpDX.Direct2D1.Brush heroBrush;
            if (armed)
            {
                bool isLong = sr.Direction > 0;
                heroText  = string.Format("\u25B6 {0} {1:F2}", GetSignalHeadline(sr).ToUpperInvariant(), sr.EntryPrice);
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

            // ── Line 4 (only when armed): execution state, not stop/target plan ──
            if (armed)
            {
                y += 28f;
                string stateLine = GetSignalDetailText(sr);
                DrawHaloText(stateLine, _pwHudLabelFont, heroBrush, x, y, w, 16);
            }
        }

        // Section 2: ▶ ACTIVE SIGNAL — renders the BUY/SELL plan when a TYPE_A signal is armed
        private float RenderMcActiveSignal(float x, float y, float w)
        {
            const float sectionH = 142f;
            var rect = new RectangleF(x, y, w, sectionH);

            var sr = _lastScorerResult;
            bool armed = sr != null && sr.Tier == SignalTier.TYPE_A && sr.Direction != 0
                         && IsArmedSignalValid();

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
        // TIER 1 chart overlay — renders Version Six setup/direction/trigger callouts only.
        // No stop/target overlays are drawn on the chart. Called from OnRender.
        // ═══════════════════════════════════════════════════════════════════════
        private bool IsVersionSixSignalVisible(ScorerResult sr)
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
            if (!IsVersionSixSignalVisible(sr)) return;

            bool isLong = sr.Direction > 0;
            SharpDX.Direct2D1.Brush accent;
            switch (sr.SetupState)
            {
                case TradeSetupState.Armed:
                case TradeSetupState.Triggered:
                    accent = isLong ? (SharpDX.Direct2D1.Brush)_scoreTierALongDx : (SharpDX.Direct2D1.Brush)_scoreTierAShortDx;
                    break;
                default:
                    accent = (SharpDX.Direct2D1.Brush)_scoreNeutralDx;
                    break;
            }
            float xRight = panelLeftEdge - 8f;
            float yEntry = cs.GetYByValue(sr.EntryPrice);
            float chartTop = (float)ChartPanel.Y;
            float chartBot = (float)(ChartPanel.Y + ChartPanel.H);
            yEntry = Math.Max(chartTop + 8f, Math.Min(chartBot - 18f, yEntry));

            string stateText = GetSignalHeadline(sr);
            string detailText = GetSignalDetailText(sr);
            DrawHaloText(stateText, _pwPillValueFont, accent, xRight - 230f, yEntry - 18f, 220f, 16f);
            DrawHaloText(detailText, _pwPillLabelFont, _pwAeroWhiteDx, xRight - 230f, yEntry - 4f, 220f, 12f);

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
                                    anchor.Kind == ProfileAnchorKind.Pdh         ||
                                    anchor.Kind == ProfileAnchorKind.Pdl;
                if (priorDayKind && !ShowPriorDayLevels) continue;
                if (anchor.Kind == ProfileAnchorKind.PriorDayVah ||
                    anchor.Kind == ProfileAnchorKind.PriorDayVal ||
                    anchor.Kind == ProfileAnchorKind.Pdm)
                    continue;
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
            float leftX = panelRight - hudW - Math.Max(0, ScoreHudPaddingPx);

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
        /// Draw a tier-coded setup/armed marker for the given bar via NT8 Draw.* API.
        /// Setup is a gray context marker only. Armed keeps strong long/short clarity.
        /// Triggered markers are drawn separately by DrawTriggeredMarker.
        /// </summary>
        private void DrawScorerTierMarker(int barIdx, ScorerResult scored)
        {
            if (scored == null) return;
            if (scored.Tier != SignalTier.TYPE_A) return;
            if (scored.Direction == 0) return;
            if (scored.SetupState == TradeSetupState.Triggered ||
                scored.SetupState == TradeSetupState.Invalid ||
                scored.SetupState == TradeSetupState.Expired)
                return;

            int barsAgo = CurrentBar - barIdx;
            double entry = scored.EntryPrice > 0 ? scored.EntryPrice : Close[barsAgo];
            bool isLong = scored.Direction > 0;

            string suffix = (isLong ? "L" : "S") + "_" + barIdx;

            Brush longBrush  = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xE6, 0x76));
            Brush shortBrush = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x17, 0x44));
            Brush setupGray  = MakeFrozenBrush(Color.FromArgb(210, 0x9A, 0xA0, 0xA6));

            double markerPrice = isLong ? entry - 8.0 * TickSize : entry + 8.0 * TickSize;
            string headline = GetSignalHeadline(scored);

            if (scored.SetupState == TradeSetupState.Setup)
            {
                Draw.Diamond(this, "SCORE_SETUP_" + suffix, false, barsAgo, markerPrice, setupGray);
                Draw.Text(this, "SCORE_SETUP_STATE_" + suffix, false, headline, barsAgo, markerPrice, 0,
                    Brushes.White, new SimpleFont("Arial", 9) { Bold = true },
                    System.Windows.TextAlignment.Center, null, null, 0);
                return;
            }

            Brush readyBrush = isLong ? longBrush : shortBrush;
            Draw.Diamond(this, "SCORE_A_" + suffix, false, barsAgo, markerPrice, readyBrush);
            Draw.Text(this, "SCORE_READY_LBL_" + suffix, false, headline, barsAgo, markerPrice, 0,
                Brushes.White, new SimpleFont("Arial", 9) { Bold = true },
                System.Windows.TextAlignment.Center, null, null, 0);
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
        [Display(Name = "TIER 1 Chart Overlay (setup/direction/trigger)", Order = 1, GroupName = "9. Signal Tiers")]
        public bool ShowTier1Overlay { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "TIER 3 Dots (informational noise — off by default)", Order = 2, GroupName = "9. Signal Tiers")]
        public bool ShowTier3Dots { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Active Signal Valid (bars)", Order = 3, GroupName = "9. Signal Tiers")]
        public int ArmedSignalValidBars { get; set; }

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

        [NinjaScriptProperty]
        [Display(Name = "Show Score HUD", Order = 1, GroupName = "7. DEEP6 Scorer",
                 Description = "Display the 3-line scoring HUD badge (Score / Tier / Narrative) in the top-right corner")]
        public bool ShowScoreHud { get; set; }

        [NinjaScriptProperty]
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

        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private DEEP6.DEEP6FootprintV7[] cacheDEEP6FootprintV7;
		public DEEP6.DEEP6FootprintV7 DEEP6FootprintV7(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showMissionControl, int missionControlWidth, bool showMcActiveSignal, bool showMcStatus, bool showMcDayPnL, bool showMcPosition, bool showMcSignalsList, bool showMcActionBar, bool showTier1Overlay, bool showTier3Dots, int armedSignalValidBars, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader, bool showScoreHud, int scoreHudPaddingPx)
		{
			return DEEP6FootprintV7(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showMissionControl, missionControlWidth, showMcActiveSignal, showMcStatus, showMcDayPnL, showMcPosition, showMcSignalsList, showMcActionBar, showTier1Overlay, showTier3Dots, armedSignalValidBars, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader, showScoreHud, scoreHudPaddingPx);
		}

		public DEEP6.DEEP6FootprintV7 DEEP6FootprintV7(ISeries<double> input, double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showMissionControl, int missionControlWidth, bool showMcActiveSignal, bool showMcStatus, bool showMcDayPnL, bool showMcPosition, bool showMcSignalsList, bool showMcActionBar, bool showTier1Overlay, bool showTier3Dots, int armedSignalValidBars, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader, bool showScoreHud, int scoreHudPaddingPx)
		{
			if (cacheDEEP6FootprintV7 != null)
				for (int idx = 0; idx < cacheDEEP6FootprintV7.Length; idx++)
					if (cacheDEEP6FootprintV7[idx] != null && cacheDEEP6FootprintV7[idx].ImbalanceRatio == imbalanceRatio && cacheDEEP6FootprintV7[idx].AbsorbWickMinPct == absorbWickMinPct && cacheDEEP6FootprintV7[idx].ExhaustWickMinPct == exhaustWickMinPct && cacheDEEP6FootprintV7[idx].ShowFootprintCells == showFootprintCells && cacheDEEP6FootprintV7[idx].ShowMissionControl == showMissionControl && cacheDEEP6FootprintV7[idx].MissionControlWidth == missionControlWidth && cacheDEEP6FootprintV7[idx].ShowMcActiveSignal == showMcActiveSignal && cacheDEEP6FootprintV7[idx].ShowMcStatus == showMcStatus && cacheDEEP6FootprintV7[idx].ShowMcDayPnL == showMcDayPnL && cacheDEEP6FootprintV7[idx].ShowMcPosition == showMcPosition && cacheDEEP6FootprintV7[idx].ShowMcSignalsList == showMcSignalsList && cacheDEEP6FootprintV7[idx].ShowMcActionBar == showMcActionBar && cacheDEEP6FootprintV7[idx].ShowTier1Overlay == showTier1Overlay && cacheDEEP6FootprintV7[idx].ShowTier3Dots == showTier3Dots && cacheDEEP6FootprintV7[idx].ArmedSignalValidBars == armedSignalValidBars && cacheDEEP6FootprintV7[idx].ShowPoc == showPoc && cacheDEEP6FootprintV7[idx].ShowValueArea == showValueArea && cacheDEEP6FootprintV7[idx].ShowAbsorptionMarkers == showAbsorptionMarkers && cacheDEEP6FootprintV7[idx].ShowExhaustionMarkers == showExhaustionMarkers && cacheDEEP6FootprintV7[idx].CellFontSize == cellFontSize && cacheDEEP6FootprintV7[idx].CellColumnWidth == cellColumnWidth && cacheDEEP6FootprintV7[idx].ShowProfileAnchors == showProfileAnchors && cacheDEEP6FootprintV7[idx].ShowPriorDayLevels == showPriorDayLevels && cacheDEEP6FootprintV7[idx].ShowNakedPocs == showNakedPocs && cacheDEEP6FootprintV7[idx].ShowCompositeVA == showCompositeVA && cacheDEEP6FootprintV7[idx].NakedPocMaxAgeSessions == nakedPocMaxAgeSessions && cacheDEEP6FootprintV7[idx].ShowLiquidityWalls == showLiquidityWalls && cacheDEEP6FootprintV7[idx].LiquidityWallMin == liquidityWallMin && cacheDEEP6FootprintV7[idx].LiquidityWallStaleSec == liquidityWallStaleSec && cacheDEEP6FootprintV7[idx].LiquidityMaxPerSide == liquidityMaxPerSide && cacheDEEP6FootprintV7[idx].ShowChartTrader == showChartTrader && cacheDEEP6FootprintV7[idx].ShowScoreHud == showScoreHud && cacheDEEP6FootprintV7[idx].ScoreHudPaddingPx == scoreHudPaddingPx && cacheDEEP6FootprintV7[idx].EqualsInput(input))
						return cacheDEEP6FootprintV7[idx];
			return CacheIndicator<DEEP6.DEEP6FootprintV7>(new DEEP6.DEEP6FootprintV7(){ ImbalanceRatio = imbalanceRatio, AbsorbWickMinPct = absorbWickMinPct, ExhaustWickMinPct = exhaustWickMinPct, ShowFootprintCells = showFootprintCells, ShowMissionControl = showMissionControl, MissionControlWidth = missionControlWidth, ShowMcActiveSignal = showMcActiveSignal, ShowMcStatus = showMcStatus, ShowMcDayPnL = showMcDayPnL, ShowMcPosition = showMcPosition, ShowMcSignalsList = showMcSignalsList, ShowMcActionBar = showMcActionBar, ShowTier1Overlay = showTier1Overlay, ShowTier3Dots = showTier3Dots, ArmedSignalValidBars = armedSignalValidBars, ShowPoc = showPoc, ShowValueArea = showValueArea, ShowAbsorptionMarkers = showAbsorptionMarkers, ShowExhaustionMarkers = showExhaustionMarkers, CellFontSize = cellFontSize, CellColumnWidth = cellColumnWidth, ShowProfileAnchors = showProfileAnchors, ShowPriorDayLevels = showPriorDayLevels, ShowNakedPocs = showNakedPocs, ShowCompositeVA = showCompositeVA, NakedPocMaxAgeSessions = nakedPocMaxAgeSessions, ShowLiquidityWalls = showLiquidityWalls, LiquidityWallMin = liquidityWallMin, LiquidityWallStaleSec = liquidityWallStaleSec, LiquidityMaxPerSide = liquidityMaxPerSide, ShowChartTrader = showChartTrader, ShowScoreHud = showScoreHud, ScoreHudPaddingPx = scoreHudPaddingPx }, input, ref cacheDEEP6FootprintV7);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.DEEP6.DEEP6FootprintV7 DEEP6FootprintV7(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showMissionControl, int missionControlWidth, bool showMcActiveSignal, bool showMcStatus, bool showMcDayPnL, bool showMcPosition, bool showMcSignalsList, bool showMcActionBar, bool showTier1Overlay, bool showTier3Dots, int armedSignalValidBars, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader, bool showScoreHud, int scoreHudPaddingPx)
		{
			return indicator.DEEP6FootprintV7(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showMissionControl, missionControlWidth, showMcActiveSignal, showMcStatus, showMcDayPnL, showMcPosition, showMcSignalsList, showMcActionBar, showTier1Overlay, showTier3Dots, armedSignalValidBars, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader, showScoreHud, scoreHudPaddingPx);
		}

		public Indicators.DEEP6.DEEP6FootprintV7 DEEP6FootprintV7(ISeries<double> input , double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showMissionControl, int missionControlWidth, bool showMcActiveSignal, bool showMcStatus, bool showMcDayPnL, bool showMcPosition, bool showMcSignalsList, bool showMcActionBar, bool showTier1Overlay, bool showTier3Dots, int armedSignalValidBars, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader, bool showScoreHud, int scoreHudPaddingPx)
		{
			return indicator.DEEP6FootprintV7(input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showMissionControl, missionControlWidth, showMcActiveSignal, showMcStatus, showMcDayPnL, showMcPosition, showMcSignalsList, showMcActionBar, showTier1Overlay, showTier3Dots, armedSignalValidBars, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader, showScoreHud, scoreHudPaddingPx);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.DEEP6.DEEP6FootprintV7 DEEP6FootprintV7(double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showMissionControl, int missionControlWidth, bool showMcActiveSignal, bool showMcStatus, bool showMcDayPnL, bool showMcPosition, bool showMcSignalsList, bool showMcActionBar, bool showTier1Overlay, bool showTier3Dots, int armedSignalValidBars, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader, bool showScoreHud, int scoreHudPaddingPx)
		{
			return indicator.DEEP6FootprintV7(Input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showMissionControl, missionControlWidth, showMcActiveSignal, showMcStatus, showMcDayPnL, showMcPosition, showMcSignalsList, showMcActionBar, showTier1Overlay, showTier3Dots, armedSignalValidBars, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader, showScoreHud, scoreHudPaddingPx);
		}

		public Indicators.DEEP6.DEEP6FootprintV7 DEEP6FootprintV7(ISeries<double> input , double imbalanceRatio, double absorbWickMinPct, double exhaustWickMinPct, bool showFootprintCells, bool showMissionControl, int missionControlWidth, bool showMcActiveSignal, bool showMcStatus, bool showMcDayPnL, bool showMcPosition, bool showMcSignalsList, bool showMcActionBar, bool showTier1Overlay, bool showTier3Dots, int armedSignalValidBars, bool showPoc, bool showValueArea, bool showAbsorptionMarkers, bool showExhaustionMarkers, float cellFontSize, int cellColumnWidth, bool showProfileAnchors, bool showPriorDayLevels, bool showNakedPocs, bool showCompositeVA, int nakedPocMaxAgeSessions, bool showLiquidityWalls, int liquidityWallMin, int liquidityWallStaleSec, int liquidityMaxPerSide, bool showChartTrader, bool showScoreHud, int scoreHudPaddingPx)
		{
			return indicator.DEEP6FootprintV7(input, imbalanceRatio, absorbWickMinPct, exhaustWickMinPct, showFootprintCells, showMissionControl, missionControlWidth, showMcActiveSignal, showMcStatus, showMcDayPnL, showMcPosition, showMcSignalsList, showMcActionBar, showTier1Overlay, showTier3Dots, armedSignalValidBars, showPoc, showValueArea, showAbsorptionMarkers, showExhaustionMarkers, cellFontSize, cellColumnWidth, showProfileAnchors, showPriorDayLevels, showNakedPocs, showCompositeVA, nakedPocMaxAgeSessions, showLiquidityWalls, liquidityWallMin, liquidityWallStaleSec, liquidityMaxPerSide, showChartTrader, showScoreHud, scoreHudPaddingPx);
		}
	}
}

#endregion
