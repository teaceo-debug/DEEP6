// DEEP6 GEX Levels V2 -- WebSocket streaming version.
// Defaults to DataSource=LocalFile; reads gex_command.json written by gex_service_v2.py.
// Run: pip install websockets && python scripts/gex_service_v2.py
// Shared types (GexDataSource, GexJson, clients) are defined in DEEP6GexLevels.cs.
#region Using
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.IO;
using System.Net;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript.DrawingTools;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
using Color = System.Windows.Media.Color;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    using NinjaTrader.NinjaScript.AddOns.DEEP6;
    using NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge;

    public class DEEP6GexLevelsV2 : Indicator
    {
        #region Fields

        // GEX fetch state
        private MassiveGexClient _gexClient;
        private FlashAlphaClient _flashAlphaClient;
        private GexBotClient     _gexBotClient;
        private LocalFileGexClient _localFileClient;
        private Func<CancellationToken, GexProfile> _fetchDelegate;
        private volatile GexProfile _gexProfile;
        private TimeSpan _gexInterval;
        private CancellationTokenSource _gexCts;
        // Background timer drives GEX fetches independently of tape activity.
        private System.Threading.Timer _gexTimer;
        private int _gexFailCount;
        // Price-drift trigger: re-fetch immediately when NQ moves more than PriceDriftPoints.
        private double _nqSpotAtLastFetch;
        private DateTime _driftFetchCooldown = DateTime.MinValue;  // minimum 10s between drift-triggered fetches
        // Sticky status â€” never cleared on failure.
        private volatile string _gexLastSuccessStatus = "GEX: idle (no key)";
        // Transient status â€” set during retry, cleared on success.
        private volatile string _gexRetryStatus = string.Empty;
        private readonly object _gexTimerLock = new object();

        // TextLayout cache â€” rebuilt on fetch, disposed on render-target change.
        // Eliminates 480 COM allocations/sec from the render loop.
        private Dictionary<string, TextLayout> _pillCache = new Dictionary<string, TextLayout>();
        private string _statusCacheKey;
        private TextLayout _statusCacheLayout;
        // Stale overlay brush (amber â€” allocated alongside other DX brushes)
        private SharpDX.Direct2D1.Brush _pwStaleDx;
        // TradeGEX-style heatmap band fills (transparent, drawn behind lines)
        private SharpDX.Direct2D1.Brush _gexPosBandDx;   // cyan  â€” positive-GEX zone fill
        private SharpDX.Direct2D1.Brush _gexNegBandDx;   // orange â€” negative-GEX zone fill

        // Composed status view
        private string _gexStatus
        {
            get
            {
                var s = _gexLastSuccessStatus ?? string.Empty;
                var r = _gexRetryStatus ?? string.Empty;
                return string.IsNullOrEmpty(r) ? s : s + "  [" + r + "]";
            }
        }

        #endregion

        #region Brushes (SharpDX device-dependent)

        private SharpDX.Direct2D1.Brush _gexFlipDx, _gexCallWallDx, _gexPutWallDx, _gexPosDx, _gexNegDx;
        private SharpDX.Direct2D1.Brush _textDx;
        private TextFormat _labelFont;

        // F1 PITWALL â€” telemetry-pill brushes for level labels (Aesthetic Option E)
        private SharpDX.Direct2D1.Brush _pwSurface2Dx;     // #0E1218  raised pill backdrop
        private SharpDX.Direct2D1.Brush _pwSellFillDx;     // red  @ 22%   SELL wall safety band
        private SharpDX.Direct2D1.Brush _pwBuyFillDx;      // green @ 22%  BUY wall safety band
        private SharpDX.Direct2D1.Brush _pwTextHaloDx;     // black @ 90%  1px halo for legibility
        private SharpDX.Direct2D1.Brush _pwWhiteTextDx;    // #F2F4F8      pill value text

        #endregion

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description                  = "GEX Levels V2 — real-time WebSocket streaming via gex_service_v2.py. Set DataSource=LocalFile and run: python scripts/gex_service_v2.py";
                Name                         = "DEEP6 GEX Levels V2";
                Calculate                    = Calculate.OnEachTick;
                IsOverlay                    = true;
                DrawOnPricePanel             = true;
                PaintPriceMarkers            = false;
                ScaleJustification           = ScaleJustification.Right;
                IsSuspendedWhileInactive     = true;

                ShowGexLevels                = true;
                ShowGexBands                = true;
                BandMaxHeightPoints         = 80;
                DataSource                  = GexDataSource.LocalFile;
                GexUnderlying               = "QQQ";
                GexApiKey                   = string.Empty;
                FlashAlphaApiKey            = string.Empty;
                GexBotApiKey                = string.Empty;
                GexBotTicker                = "NQ_NDX";
                LocalGexFilePath            = System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    @"NinjaTrader 8\templates\DEEP6\gex_command.json");
                FetchIntervalSeconds        = 15;
                PriceDriftPoints            = 10;

                // F1 PITWALL â€” aerospace 787 PFD color grammar (Aesthetic Option E)
                //   cyan = selected/target  â†’  GammaFlip (zero-gamma point = primary target)
                //   amber = caution/safety  â†’  Call/Put walls (price-bound limits)
                //   minor levels: cyan (positive GEX) / magenta (negative GEX)
                GexFlipBrush      = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xE0, 0xFF));   // aero cyan  â€” zero-gamma regime line
                GexCallWallBrush  = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x3B, 0x30));   // bright red â€” SELL resistance (R1)
                GexPutWallBrush   = MakeFrozenBrush(Color.FromArgb(255, 0x30, 0xD1, 0x58));   // bright green â€” BUY support (S1)
                GexPositiveBrush  = MakeFrozenBrush(Color.FromArgb(140, 0x30, 0xD1, 0x58));   // dim green  â€” minor +GEX nodes
                GexNegativeBrush  = MakeFrozenBrush(Color.FromArgb(140, 0xFF, 0x3B, 0x30));   // dim red    â€” minor âˆ’GEX nodes
            }
            else if (State == State.DataLoaded)
            {
                if (!ShowGexLevels)
                {
                    _gexLastSuccessStatus = "GEX: disabled";
                    _gexRetryStatus = string.Empty;
                    return;
                }
                _gexInterval = TimeSpan.FromSeconds(System.Math.Max(15, FetchIntervalSeconds));
                _gexCts = new CancellationTokenSource();
                _gexFailCount = 0;

                switch (DataSource)
                {
                    case GexDataSource.FlashAlpha:
                        if (string.IsNullOrWhiteSpace(FlashAlphaApiKey))
                        { _gexLastSuccessStatus = "GEX [FlashAlpha]: set FlashAlpha API Key in properties (free at flashalpha.com)"; return; }
                        _flashAlphaClient = new FlashAlphaClient(FlashAlphaApiKey);
                        _fetchDelegate = ct => _flashAlphaClient.Fetch(GexUnderlying, ct);
                        Print("[DEEP6 GEX] FlashAlpha: fetching " + GexUnderlying + " levelsâ€¦");
                        break;

                    case GexDataSource.GEXBot:
                        if (string.IsNullOrWhiteSpace(GexBotApiKey))
                        { _gexLastSuccessStatus = "GEX [GEXBot]: set GEXBot API Key in properties (gexbot.com)"; return; }
                        _gexBotClient = new GexBotClient(GexBotApiKey);
                        _fetchDelegate = ct => _gexBotClient.Fetch(GexBotTicker, ct);
                        Print("[DEEP6 GEX] GEXBot: fetching " + GexBotTicker + "â€¦");
                        break;

                    case GexDataSource.LocalFile:
                        _localFileClient = new LocalFileGexClient(LocalGexFilePath);
                        _fetchDelegate = ct => _localFileClient.Fetch("NQ", ct);
                        Print("[DEEP6 GEX] LocalFile: reading " + LocalGexFilePath + "â€¦");
                        break;

                    default: // Massive
                        if (string.IsNullOrWhiteSpace(GexApiKey))
                        { _gexLastSuccessStatus = "GEX [Massive]: set API Key in properties (massive.com)"; return; }
                        _gexClient = new MassiveGexClient(GexApiKey);
                        _fetchDelegate = null; // massive uses legacy path in GexTimerTick
                        Print("[DEEP6 GEX] Massive: fetching " + GexUnderlying + " chainâ€¦");
                        break;
                }

                _gexLastSuccessStatus = "GEX [" + DataSource + "]: initializingâ€¦";
                _gexRetryStatus = string.Empty;
                _gexTimer = new System.Threading.Timer(GexTimerTick, null, TimeSpan.Zero, System.Threading.Timeout.InfiniteTimeSpan);
            }
            else if (State == State.Terminated)
            {
                if (Instrument != null) GexSharedState.Clear(Instrument.FullName);
                if (_gexTimer != null) { try { _gexTimer.Dispose(); } catch { } _gexTimer = null; }
                if (_gexCts != null) { try { _gexCts.Cancel(); } catch { } }
                if (_gexClient != null) { _gexClient.Dispose(); _gexClient = null; }
                if (_flashAlphaClient != null) { _flashAlphaClient.Dispose(); _flashAlphaClient = null; }
                if (_gexBotClient != null) { _gexBotClient.Dispose(); _gexBotClient = null; }
                if (_localFileClient != null) { _localFileClient.Dispose(); _localFileClient = null; }
                _fetchDelegate = null;
                DisposeDx();
            }
        }

        #region Timer callbacks

        private void GexTimerTick(object state)
        {
            if (!System.Threading.Monitor.TryEnter(_gexTimerLock)) return;
            try
            {
                var ctsTok = _gexCts == null ? CancellationToken.None : _gexCts.Token;
                if (ctsTok.IsCancellationRequested) return;

                string label = DataSource.ToString();
                _gexRetryStatus = "fetching [" + label + "]â€¦";
                Print("[DEEP6 GEX] Fetch start [" + label + "] @ " + DateTime.Now.ToString("HH:mm:ss"));

                try
                {
                    GexProfile profile;
                    if (_fetchDelegate != null)
                    {
                        // FlashAlpha / GEXBot / LocalFile
                        profile = _fetchDelegate(ctsTok);
                    }
                    else
                    {
                        // Massive (legacy path â€” keeps spot-hint optimisation)
                        var client = _gexClient;
                        if (client == null) return;
                        double spotHint = 0;
                        var prev = _gexProfile;
                        if (prev != null && prev.Spot > 0) spotHint = prev.Spot;
                        profile = client.Fetch(GexUnderlying, ctsTok, spotHint);
                    }

                    if (profile != null && profile.Levels.Count > 0)
                        OnGexFetchSuccess(profile);
                    else
                        OnGexFetchFailure(new InvalidOperationException("empty response â€” check API key/plan/ticker"));
                }
                catch (OperationCanceledException) { }
                catch (Exception ex) { OnGexFetchFailure(ex); }
            }
            finally
            {
                System.Threading.Monitor.Exit(_gexTimerLock);
                ScheduleNextGexTick();
            }
        }

        private void OnGexFetchSuccess(GexProfile profile)
        {
            _gexProfile = profile;
            _gexFailCount = 0;
            // Invalidate pill label cache â€” text will change (new prices mapped from new profile).
            if (_pillCache != null) { foreach (var kv in _pillCache) if (kv.Value != null) kv.Value.Dispose(); _pillCache.Clear(); }
            if (_statusCacheLayout != null) { _statusCacheLayout.Dispose(); _statusCacheLayout = null; }
            _statusCacheKey = null;
            // Record NQ price at fetch time so drift trigger can compare against it.
            try { if (Bars != null && Bars.Count > 0) _nqSpotAtLastFetch = Bars.GetClose(Bars.Count - 1); } catch { }
            PublishSharedSnapshot(profile);
            _gexLastSuccessStatus = "GEX: " + profile.Levels.Count + " levels @ " + DateTime.Now.ToString("HH:mm:ss");
            _gexRetryStatus = string.Empty;
            Print("[DEEP6 GEX] OK: " + profile.Levels.Count + " levels, spot " + profile.Spot.ToString("F2") + ", flip " + profile.GammaFlip.ToString("F2"));
        }

        private void PublishSharedSnapshot(GexProfile profile)
        {
            if (profile == null || profile.Levels == null || profile.Levels.Count == 0) return;
            double nqSpot = _nqSpotAtLastFetch;
            if (nqSpot <= 0)
            {
                try { if (Bars != null && Bars.Count > 0) nqSpot = Bars.GetClose(Bars.Count - 1); } catch { nqSpot = 0; }
            }
            if (nqSpot <= 0 || profile.Spot <= 0 || Instrument == null) return;

            double ratio = nqSpot / profile.Spot;
            var snap = new GexContextSnapshot
            {
                Instrument = Instrument.FullName,
                FetchedUtc = profile.FetchedUtc,
                Stale = false,
                Underlying = profile.Underlying,
                UnderlyingSpot = profile.Spot,
                NqSpot = nqSpot,
                MappingRatio = ratio,
                GammaFlip = profile.GammaFlip * ratio,
                CallWall = profile.CallWall * ratio,
                PutWall = profile.PutWall * ratio,
            };

            for (int i = 0; i < profile.Levels.Count; i++)
            {
                var lv = profile.Levels[i];
                if (lv == null || lv.Strike <= 0) continue;
                snap.Levels.Add(new MappedGexLevel
                {
                    Kind = lv.Kind.ToString(),
                    NqPrice = lv.Strike * ratio,
                    SourceStrike = lv.Strike,
                    SourceSpot = profile.Spot,
                    Weight = Math.Abs(lv.GexNotional),
                });
            }

            GexSharedState.Publish(Instrument.FullName, snap);
        }

        private void OnGexFetchFailure(Exception ex)
        {
            _gexFailCount++;
            var delay = ComputeGexRetryDelay(_gexFailCount);
            _gexRetryStatus = "retry in " + ((int)delay.TotalSeconds) + "s after " + ex.GetType().Name;
            string inner = ex.InnerException != null ? " | inner: " + ex.InnerException.Message : string.Empty;
            Print("[DEEP6 GEX] EXCEPTION (#" + _gexFailCount + "): " + ex.GetType().Name + " â€” " + ex.Message + inner + ". Retrying in " + (int)delay.TotalSeconds + "s.");
        }

        // 5s â†’ 15s â†’ 60s â†’ 120s (cap = _gexInterval).
        private TimeSpan ComputeGexRetryDelay(int failCount)
        {
            if (failCount <= 0) return TimeSpan.FromSeconds(60);
            switch (failCount)
            {
                case 1: return TimeSpan.FromSeconds(5);
                case 2: return TimeSpan.FromSeconds(15);
                case 3: return TimeSpan.FromSeconds(60);
                default: return _gexInterval;
            }
        }

        private void ScheduleNextGexTick()
        {
            if (_gexTimer == null) return;
            try
            {
                var next = _gexFailCount == 0 ? AdaptiveInterval() : ComputeGexRetryDelay(_gexFailCount);
                _gexTimer.Change(next, System.Threading.Timeout.InfiniteTimeSpan);
            }
            catch (ObjectDisposedException) { /* shutting down */ }
        }

        private static readonly TimeZoneInfo _etZone =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        // Returns the optimal polling interval based on time of day (ET).
        // Fast at open/close where gamma sensitivity is highest; slow pre-market.
        private TimeSpan AdaptiveInterval()
        {
            try
            {
                var et = TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, _etZone);
                int totalMin = et.Hour * 60 + et.Minute;
                // Pre-market / post-market
                if (totalMin < 9 * 60 + 15 || totalMin >= 16 * 60 + 5)
                    return TimeSpan.FromSeconds(60);
                // Pre-open ramp 9:15â€“9:30
                if (totalMin < 9 * 60 + 30)
                    return TimeSpan.FromSeconds(15);
                // RTH open surge 9:30â€“10:30 â€” highest gamma sensitivity
                if (totalMin < 10 * 60 + 30)
                    return TimeSpan.FromSeconds(5);
                // FOMC window 14:45â€“15:00
                if (totalMin >= 14 * 60 + 45 && totalMin < 15 * 60)
                    return TimeSpan.FromSeconds(10);
                // 0DTE gamma cliff 15:54â€“16:05
                if (totalMin >= 15 * 60 + 54)
                    return TimeSpan.FromSeconds(5);
                // Standard RTH mid-session
                return TimeSpan.FromSeconds(15);
            }
            catch
            {
                return _gexInterval;
            }
        }

        #endregion

        #region Price-drift trigger

        protected override void OnBarUpdate()
        {
            if (_gexClient == null || _nqSpotAtLastFetch <= 0 || PriceDriftPoints <= 0) return;
            double nqNow = Close[0];
            double drift = System.Math.Abs(nqNow - _nqSpotAtLastFetch);
            if (drift < PriceDriftPoints) return;
            if (DateTime.UtcNow < _driftFetchCooldown) return;
            // Price has drifted enough â€” kick the timer to fire immediately.
            _driftFetchCooldown = DateTime.UtcNow.AddSeconds(10);
            try { _gexTimer?.Change(TimeSpan.Zero, System.Threading.Timeout.InfiniteTimeSpan); } catch { }
        }

        #endregion

        #region Render

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            _gexFlipDx     = GexFlipBrush.ToDxBrush(RenderTarget);
            _gexCallWallDx = GexCallWallBrush.ToDxBrush(RenderTarget);
            _gexPutWallDx  = GexPutWallBrush.ToDxBrush(RenderTarget);
            _gexPosDx      = GexPositiveBrush.ToDxBrush(RenderTarget);
            _gexNegDx      = GexNegativeBrush.ToDxBrush(RenderTarget);
            _textDx        = MakeFrozenBrush(Color.FromArgb(220, 220, 220, 220)).ToDxBrush(RenderTarget);

            // F1 PITWALL â€” telemetry-pill brushes
            _pwSurface2Dx   = MakeFrozenBrush(Color.FromArgb(230, 0x0E, 0x12, 0x18)).ToDxBrush(RenderTarget);
            _pwSellFillDx   = MakeFrozenBrush(Color.FromArgb(56,  0xFF, 0x3B, 0x30)).ToDxBrush(RenderTarget);  // red band
            _pwBuyFillDx    = MakeFrozenBrush(Color.FromArgb(56,  0x30, 0xD1, 0x58)).ToDxBrush(RenderTarget);  // green band
            _pwTextHaloDx   = MakeFrozenBrush(Color.FromArgb(230, 0x00, 0x00, 0x00)).ToDxBrush(RenderTarget);
            _pwWhiteTextDx  = MakeFrozenBrush(Color.FromArgb(255, 0xF2, 0xF4, 0xF8)).ToDxBrush(RenderTarget);
            _pwStaleDx      = MakeFrozenBrush(Color.FromArgb(200, 0xFF, 0xBF, 0x00)).ToDxBrush(RenderTarget); // amber â€” stale warning
            _gexPosBandDx   = MakeFrozenBrush(Color.FromArgb(80,  0x00, 0xE0, 0xFF)).ToDxBrush(RenderTarget); // cyan   @ 31% â€” +GEX heatmap band
            _gexNegBandDx   = MakeFrozenBrush(Color.FromArgb(80,  0xFF, 0x80, 0x00)).ToDxBrush(RenderTarget); // orange @ 31% â€” -GEX heatmap band

            // Invalidate layout cache on device reset â€” layouts are device-dependent
            if (_pillCache != null) { foreach (var kv in _pillCache) if (kv.Value != null) kv.Value.Dispose(); _pillCache.Clear(); }
            if (_statusCacheLayout != null) { _statusCacheLayout.Dispose(); _statusCacheLayout = null; }
            _statusCacheKey = null;

            // F1 PITWALL: dash style is currently unused (zero-gamma is solid cyan).
            // If a user toggle is added later for "dashed flip", construct it here:
            //   var dashProps = new StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Dash };
            //   _pwDashStyle = RenderTarget.Factory.CreateStrokeStyle(dashProps);
            // Note: NT8 production has a (Factory, props, float[]) ctor that the simulator stub
            // doesn't expose; use Factory.CreateStrokeStyle(props) for sim-compatible code.

            _labelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 9f)
            {
                TextAlignment      = TextAlignment.Trailing,
                ParagraphAlignment = ParagraphAlignment.Center,
            };
        }

        private void DisposeDx()
        {
            DisposeBrush(ref _gexFlipDx); DisposeBrush(ref _gexCallWallDx);
            DisposeBrush(ref _gexPutWallDx); DisposeBrush(ref _gexPosDx);
            DisposeBrush(ref _gexNegDx); DisposeBrush(ref _textDx);
            DisposeBrush(ref _pwSurface2Dx);
            DisposeBrush(ref _pwSellFillDx); DisposeBrush(ref _pwBuyFillDx);
            DisposeBrush(ref _pwTextHaloDx); DisposeBrush(ref _pwWhiteTextDx);
            DisposeBrush(ref _pwStaleDx);
            DisposeBrush(ref _gexPosBandDx); DisposeBrush(ref _gexNegBandDx);
            if (_labelFont != null) { _labelFont.Dispose(); _labelFont = null; }
            if (_pillCache != null) { foreach (var kv in _pillCache) if (kv.Value != null) kv.Value.Dispose(); _pillCache.Clear(); }
            if (_statusCacheLayout != null) { _statusCacheLayout.Dispose(); _statusCacheLayout = null; }
            _statusCacheKey = null;
        }

        private static void DisposeBrush(ref SharpDX.Direct2D1.Brush b)
        {
            if (b != null) { b.Dispose(); b = null; }
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (RenderTarget == null || ChartBars == null) return;
            if (chartControl.Instrument == null) return;
            if (_labelFont == null) return;

            base.OnRender(chartControl, chartScale);
            RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

            float panelRight = (float)(ChartPanel.X + ChartPanel.W);

            // Staleness â€” compute once per frame, used by both badge and level rendering
            var profile = _gexProfile;
            double staleSeconds = profile != null
                ? (DateTime.UtcNow - profile.FetchedUtc).TotalSeconds
                : double.MaxValue;
            bool isStale = staleSeconds > 120;   // >2 min = stale
            bool isVeryStale = staleSeconds > 600; // >10 min = very stale

            // GEX status badge (top-right corner) â€” cached TextLayout, rebuilt only when text changes
            {
                // Append stale age to status text when data is old
                string status = _gexStatus ?? string.Empty;
                if (isStale && profile != null)
                {
                    int ageSec = (int)staleSeconds;
                    status = status + (isVeryStale ? "  âš  STALE " : "  [") +
                             (ageSec >= 60 ? (ageSec / 60) + "m" : ageSec + "s") +
                             (isVeryStale ? " old" : "]");
                }

                if (!string.IsNullOrEmpty(status))
                {
                    SharpDX.Direct2D1.Brush statusBrush;
                    if (isVeryStale)
                        statusBrush = _pwStaleDx ?? _textDx;       // amber = very stale
                    else if (isStale)
                        statusBrush = _pwStaleDx ?? _textDx;       // amber = stale
                    else if (status.IndexOf("ERROR", StringComparison.Ordinal) >= 0 ||
                             status.IndexOf("NO API KEY", StringComparison.Ordinal) >= 0 ||
                             status.IndexOf("empty", StringComparison.Ordinal) >= 0)
                        statusBrush = _gexCallWallDx ?? _textDx;   // red = error
                    else if (status.IndexOf("levels", StringComparison.Ordinal) >= 0)
                        statusBrush = _gexPutWallDx ?? _textDx;    // green = success
                    else
                        statusBrush = _textDx;

                    // Use cached TextLayout â€” only rebuild when text actually changes
                    if (_statusCacheKey != status || _statusCacheLayout == null)
                    {
                        if (_statusCacheLayout != null) { _statusCacheLayout.Dispose(); _statusCacheLayout = null; }
                        _statusCacheLayout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                            status, _labelFont, 420f, 18f);
                        _statusCacheKey = status;
                    }

                    if (statusBrush != null && _statusCacheLayout != null)
                        RenderTarget.DrawTextLayout(
                            new Vector2(panelRight - 424, (float)ChartPanel.Y + 4),
                            _statusCacheLayout, statusBrush);
                }
            }

            // GEX horizontal levels â€” pass stale flag so renderer can dim them
            if (ShowGexLevels && profile != null)
                RenderGexLevels(profile, chartControl, chartScale, panelRight, isStale);
        }

        private void RenderGexLevels(GexProfile gex, ChartControl cc, ChartScale cs, float panelRight, bool isStale)
        {
            double nqSpot = (Bars != null && Bars.Count > 0) ? Bars.GetClose(Bars.Count - 1) : 0;
            double underlyingSpot = gex.Spot;
            if (nqSpot <= 0 || underlyingSpot <= 0) return;
            double mult = nqSpot / underlyingSpot;

            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;

            // â”€â”€ TradeGEX-style heatmap bands (drawn first so lines/pills render on top) â”€â”€
            if (ShowGexBands && BandMaxHeightPoints > 0 && _gexPosBandDx != null && _gexNegBandDx != null)
            {
                double maxGex = 0;
                foreach (var lv in gex.Levels)
                    if (lv.Kind != GexLevelKind.GammaFlip && System.Math.Abs(lv.GexNotional) > maxGex)
                        maxGex = System.Math.Abs(lv.GexNotional);

                if (maxGex > 0)
                {
                    foreach (var lv in gex.Levels)
                    {
                        if (lv.Kind == GexLevelKind.GammaFlip) continue;
                        double mapped = lv.Strike * mult;
                        double bandHalfPts = (System.Math.Abs(lv.GexNotional) / maxGex) * (BandMaxHeightPoints * 0.5);
                        if (mapped + bandHalfPts < minVis || mapped - bandHalfPts > maxVis) continue;
                        if (bandHalfPts < 0.5) continue;

                        float yTop  = cs.GetYByValue(mapped + bandHalfPts);
                        float yBot  = cs.GetYByValue(mapped - bandHalfPts);
                        float bandH = System.Math.Abs(yBot - yTop);
                        if (bandH < 1f) continue;

                        var fillBrush = lv.GexNotional > 0 ? _gexPosBandDx : _gexNegBandDx;
                        RenderTarget.FillRectangle(
                            new RectangleF((float)ChartPanel.X, yTop,
                                           panelRight - (float)ChartPanel.X, bandH),
                            fillBrush);
                    }
                }
            }

            const float pillW    = 96f;
            const float pillH    = 18f;
            const float pillEdge = 2f;
            float pillX    = panelRight - pillW - 4f;
            float lineEndX = pillX - 4f;

            // Stale: dim line opacity by lowering stroke width and using the stale brush for minor levels
            float staleWidthMult = isStale ? 0.5f : 1.0f;

            foreach (var lv in gex.Levels)
            {
                double mapped = lv.Strike * mult;
                if (mapped < minVis || mapped > maxVis) continue;

                SharpDX.Direct2D1.Brush brush;
                SharpDX.Direct2D1.Brush bandFill = null;
                float width;
                string shortLabel;
                switch (lv.Kind)
                {
                    case GexLevelKind.GammaFlip:
                        brush = isStale ? (_pwStaleDx ?? _gexFlipDx) : _gexFlipDx;
                        width = 1.5f * staleWidthMult; shortLabel = "FLIP"; break;
                    case GexLevelKind.CallWall:
                        brush = _gexCallWallDx; width = 3.0f * staleWidthMult;
                        bandFill = isStale ? null : _pwSellFillDx; shortLabel = "SELL"; break;
                    case GexLevelKind.PutWall:
                        brush = _gexPutWallDx; width = 3.0f * staleWidthMult;
                        bandFill = isStale ? null : _pwBuyFillDx; shortLabel = "BUY"; break;
                    case GexLevelKind.MajorPositive:
                        brush = _gexPosDx; width = 0.8f * staleWidthMult; shortLabel = "+GEX"; break;
                    default:
                        brush = _gexNegDx; width = 0.8f * staleWidthMult; shortLabel = "âˆ’GEX"; break;
                }
                if (brush == null) continue;

                float y = cs.GetYByValue(mapped);

                if (bandFill != null)
                {
                    var bandRect = new RectangleF((float)ChartPanel.X, y - 4f,
                                                   panelRight - (float)ChartPanel.X, 8f);
                    RenderTarget.FillRectangle(bandRect, bandFill);
                }

                RenderTarget.DrawLine(new Vector2((float)ChartPanel.X, y),
                                      new Vector2(lineEndX, y), brush, width);

                if (_pwSurface2Dx != null && _pwWhiteTextDx != null && _pwTextHaloDx != null)
                {
                    var pillRect = new RectangleF(pillX, y - pillH * 0.5f, pillW, pillH);
                    RenderTarget.FillRectangle(pillRect, _pwSurface2Dx);

                    var edgeRect = new RectangleF(pillX, y - pillH * 0.5f, pillEdge, pillH);
                    RenderTarget.FillRectangle(edgeRect, brush);

                    // Cache pill TextLayout by text key â€” only ~8 unique strings, rebuilt on fetch
                    string pillTxt = string.Format("{0}  {1:F0}", shortLabel, mapped);
                    TextLayout layout;
                    if (!_pillCache.TryGetValue(pillTxt, out layout) || layout == null)
                    {
                        layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                pillTxt, _labelFont, pillW - 12f, pillH);
                        _pillCache[pillTxt] = layout;
                    }

                    var origin = new Vector2(pillX + 6f, y - pillH * 0.5f);
                    RenderTarget.DrawTextLayout(new Vector2(origin.X - 1, origin.Y), layout, _pwTextHaloDx);
                    RenderTarget.DrawTextLayout(new Vector2(origin.X + 1, origin.Y), layout, _pwTextHaloDx);
                    RenderTarget.DrawTextLayout(new Vector2(origin.X, origin.Y - 1), layout, _pwTextHaloDx);
                    RenderTarget.DrawTextLayout(new Vector2(origin.X, origin.Y + 1), layout, _pwTextHaloDx);
                    RenderTarget.DrawTextLayout(origin, layout, _pwWhiteTextDx);
                }
                else
                {
                    string label = string.Format("{0} ({1:F2})", lv.Label, mapped);
                    TextLayout layout;
                    if (!_pillCache.TryGetValue(label, out layout) || layout == null)
                    {
                        layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                label, _labelFont, 156, 16);
                        _pillCache[label] = layout;
                    }
                    RenderTarget.DrawTextLayout(new Vector2(panelRight - 160, y - 8), layout, brush);
                }
            }
        }

        #endregion

        // Handles chart click â€” show GEX detail for hit level.
        // Uses 'new' instead of 'override' for cross-version NT8 compatibility.
        // NT8 8.0.27+ has this as a virtual method on IndicatorBase; older versions don't.
        // With 'new', this compiles on all versions. On 8.0.27+ you can change to 'override'.
        protected new void OnChartPanelMouseDown(ChartControl chartControl, ChartPanel chartPanel,
                                                    ChartScale chartScale, ChartAnchor dataPoint)
        {
            if (!ShowGexLevels || _gexProfile == null) return;

            double nqSpot = (Bars != null && Bars.Count > 0) ? Bars.GetClose(Bars.Count - 1) : 0;
            double underlyingSpot = _gexProfile.Spot;
            if (nqSpot <= 0 || underlyingSpot <= 0) return;
            double mult = nqSpot / underlyingSpot;

            foreach (var lv in _gexProfile.Levels)
            {
                double mapped = lv.Strike * mult;
                double clickPrice = dataPoint.Price;
                if (System.Math.Abs(clickPrice - mapped) < 5.0)
                {
                    Print(string.Format("[DEEP6 GEX] {0}  strike={1:F2}  mapped={2:F2}  GEX=${3:F0}M",
                        lv.Label, lv.Strike, mapped, lv.GexNotional / 1e6));
                    break;
                }
            }
        }

        private static SolidColorBrush MakeFrozenBrush(Color c)
        {
            var b = new SolidColorBrush(c);
            if (b.CanFreeze) b.Freeze();
            return b;
        }

        #region Properties

        [NinjaScriptProperty]
        [Display(Name = "Show GEX Levels", Order = 10, GroupName = "3. GEX Levels")]
        public bool ShowGexLevels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show GEX Bands (heatmap)", Order = 11, GroupName = "3. GEX Levels")]
        public bool ShowGexBands { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Band Max Height (NQ pts)", Order = 12, GroupName = "3. GEX Levels")]
        public int BandMaxHeightPoints { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Fetch Interval (seconds, min 15)", Order = 13, GroupName = "3. GEX Levels")]
        public int FetchIntervalSeconds { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Price Drift Re-fetch (NQ points, 0=off)", Order = 14, GroupName = "3. GEX Levels")]
        public int PriceDriftPoints { get; set; }

        // â”€â”€ Data source selection â”€â”€

        [NinjaScriptProperty]
        [Display(Name = "Data Source", Order = 20, GroupName = "3. GEX Levels",
            Description = "FlashAlpha = pre-computed levels (free API key at flashalpha.com); GEXBot = native NQ prices (gexbot.com); LocalFile = reads gex_command.json from gex_service.py; Massive = raw chain (original, requires Advanced plan $199/mo)")]
        public GexDataSource DataSource { get; set; }

        // â”€â”€ FlashAlpha â”€â”€
        [NinjaScriptProperty]
        [PasswordPropertyText(true)]
        [Display(Name = "FlashAlpha API Key", Order = 30, GroupName = "3. GEX Levels",
            Description = "Free key at flashalpha.com â€” 5 req/day free, Basic $79/mo for live polling (QQQ supported)")]
        public string FlashAlphaApiKey { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "FlashAlpha Symbol (QQQ/NDX)", Order = 31, GroupName = "3. GEX Levels")]
        public string GexUnderlying { get; set; }

        // â”€â”€ GEXBot â”€â”€
        [NinjaScriptProperty]
        [PasswordPropertyText(true)]
        [Display(Name = "GEXBot API Key", Order = 40, GroupName = "3. GEX Levels",
            Description = "From gexbot.com â€” supports NQ_NDX, NDX, QQQ (NQ_NDX returns native NQ prices)")]
        public string GexBotApiKey { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "GEXBot Ticker", Order = 41, GroupName = "3. GEX Levels",
            Description = "NQ_NDX (recommended for NQ), NDX, QQQ, SPX, ES_SPX")]
        public string GexBotTicker { get; set; }

        // â”€â”€ Local File â”€â”€
        [NinjaScriptProperty]
        [Display(Name = "Local GEX JSON Path", Order = 50, GroupName = "3. GEX Levels",
            Description = "Path to gex_command.json written by gex_service.py. Run: python scripts/gex_service.py")]
        public string LocalGexFilePath { get; set; }

        // â”€â”€ Massive (legacy) â”€â”€
        [NinjaScriptProperty]
        [PasswordPropertyText(true)]
        [Display(Name = "Massive.com API Key (legacy)", Order = 60, GroupName = "3. GEX Levels",
            Description = "Original Massive/Polygon API key â€” requires Advanced plan $199/mo for real-time greeks")]
        public string GexApiKey { get; set; }

        // --- Brush properties ---

        [XmlIgnore]
        [Display(Name = "GEX Flip",      Order = 40, GroupName = "4. Colors")]
        public Brush GexFlipBrush { get; set; }
        [Browsable(false)] public string GexFlipBrushSerialize      { get { return Serialize.BrushToString(GexFlipBrush); }      set { GexFlipBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX Call Wall", Order = 41, GroupName = "4. Colors")]
        public Brush GexCallWallBrush { get; set; }
        [Browsable(false)] public string GexCallWallBrushSerialize  { get { return Serialize.BrushToString(GexCallWallBrush); }  set { GexCallWallBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX Put Wall",  Order = 42, GroupName = "4. Colors")]
        public Brush GexPutWallBrush { get; set; }
        [Browsable(false)] public string GexPutWallBrushSerialize   { get { return Serialize.BrushToString(GexPutWallBrush); }   set { GexPutWallBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX + Nodes",   Order = 43, GroupName = "4. Colors")]
        public Brush GexPositiveBrush { get; set; }
        [Browsable(false)] public string GexPositiveBrushSerialize  { get { return Serialize.BrushToString(GexPositiveBrush); }  set { GexPositiveBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "GEX - Nodes",   Order = 44, GroupName = "4. Colors")]
        public Brush GexNegativeBrush { get; set; }
        [Browsable(false)] public string GexNegativeBrushSerialize  { get { return Serialize.BrushToString(GexNegativeBrush); }  set { GexNegativeBrush = Serialize.StringToBrush(value); } }

        #endregion
    }
}
#region NinjaScript generated code. Neither change nor remove.
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6.DEEP6GexLevelsV2[] cacheDEEP6GexLevelsV2;
        public DEEP6.DEEP6GexLevelsV2 DEEP6GexLevelsV2(bool showGexLevels, int fetchIntervalSeconds, string gexUnderlying, string gexApiKey)
        {
            return DEEP6GexLevelsV2(Input, showGexLevels, fetchIntervalSeconds, gexUnderlying, gexApiKey);
        }

        public DEEP6.DEEP6GexLevelsV2 DEEP6GexLevelsV2(ISeries<double> input, bool showGexLevels, int fetchIntervalSeconds, string gexUnderlying, string gexApiKey)
        {
            if (cacheDEEP6GexLevelsV2 != null)
                for (int idx = 0; idx < cacheDEEP6GexLevelsV2.Length; idx++)
                    if (cacheDEEP6GexLevelsV2[idx] != null && cacheDEEP6GexLevelsV2[idx].ShowGexLevels == showGexLevels && cacheDEEP6GexLevelsV2[idx].FetchIntervalSeconds == fetchIntervalSeconds && cacheDEEP6GexLevelsV2[idx].GexUnderlying == gexUnderlying && cacheDEEP6GexLevelsV2[idx].GexApiKey == gexApiKey && cacheDEEP6GexLevelsV2[idx].EqualsInput(input))
                        return cacheDEEP6GexLevelsV2[idx];
            return CacheIndicator<DEEP6.DEEP6GexLevelsV2>(new DEEP6.DEEP6GexLevelsV2() { ShowGexLevels = showGexLevels, FetchIntervalSeconds = fetchIntervalSeconds, GexUnderlying = gexUnderlying, GexApiKey = gexApiKey }, input, ref cacheDEEP6GexLevelsV2);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6.DEEP6GexLevelsV2 DEEP6GexLevelsV2(bool showGexLevels, int fetchIntervalSeconds, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6GexLevelsV2(Input, showGexLevels, fetchIntervalSeconds, gexUnderlying, gexApiKey);
        }

        public Indicators.DEEP6.DEEP6GexLevelsV2 DEEP6GexLevelsV2(ISeries<double> input, bool showGexLevels, int fetchIntervalSeconds, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6GexLevelsV2(input, showGexLevels, fetchIntervalSeconds, gexUnderlying, gexApiKey);
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.DEEP6.DEEP6GexLevelsV2 DEEP6GexLevelsV2(bool showGexLevels, int fetchIntervalSeconds, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6GexLevelsV2(Input, showGexLevels, fetchIntervalSeconds, gexUnderlying, gexApiKey);
        }

        public Indicators.DEEP6.DEEP6GexLevelsV2 DEEP6GexLevelsV2(ISeries<double> input, bool showGexLevels, int fetchIntervalSeconds, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6GexLevelsV2(input, showGexLevels, fetchIntervalSeconds, gexUnderlying, gexApiKey);
        }
    }
}
#endregion

