// =================================================================================
//  InstitutionalConfluence.cs
//  =========================
//  NinjaTrader 8 indicator that consumes the confluence_server.py middleware
//  and renders:
//
//    - GEX horizontal lines: Flip, Call Wall, Put Wall, HVL
//    - MTF Premium / Equilibrium / Discount zones (Daily, 4H, Chart) as ICT ranges
//    - HUD panel (top-right) with:
//        GEX bias        | DP bias        | Macro regime
//        Confluence score (-5 .. +5)  with breakdown
//        Conflict alerts (STOP_BUYING, FULL_SEND_LONG, etc.)
//
//  Data source: http://127.0.0.1:8765/confluence/nq?price=<NQ>&mtf_d=...&mtf_4h=...
//
//  Author:  Michael / Peak Asset Performance LLC
//  Phases:  2 (skeleton + lines + MTF) + 3 (HUD + scoring + alerts)  combined
//  Pairs:   confluence_server.py  +  ConfluenceBiasFilter.cs (DEEP6 ATLAS bridge)
// =================================================================================

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using System.Web.Script.Serialization;
using Brush = System.Windows.Media.Brush;
using SolidColorBrush = SharpDX.Direct2D1.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.PeakAssetPerformance
{
    // -----------------------------------------------------------------------------
    //  PAYLOAD DTOs  (mirror of UnifiedPayload from the Python middleware)
    // -----------------------------------------------------------------------------
    public class GexLayer
    {
        public double? flip       { get; set; }
        public double? call_wall  { get; set; }
        public double? put_wall   { get; set; }
        public double? hvl        { get; set; }
        public double? net_gex    { get; set; }
        public string  bias       { get; set; } = "NEUTRAL";
        public bool    stale      { get; set; }
        public string  source_ts  { get; set; }  // extra JSON field
    }

    public class DarkPoolLayer
    {
        public double? raw_offex_pct   { get; set; }
        public double? dp_vwap         { get; set; }
        public double? total_block_val { get; set; }
        public string  bias            { get; set; } = "NEUTRAL";
        public double  confidence      { get; set; }
        public bool    stale           { get; set; }
        public string  source_ts       { get; set; }  // extra JSON field
        public object  blocks_24h      { get; set; }  // extra JSON field (array, ignored)
    }

    public class RegimeLayer
    {
        public string macro        { get; set; } = "NEUTRAL";
        public string vol_regime   { get; set; } = "NORMAL";
        public string thesis_trend { get; set; } = "FLAT";
        public string pcr_bias     { get; set; } = "NEUTRAL";
        public bool   stale        { get; set; }
        public string source_ts    { get; set; }  // extra JSON field
    }

    public class CompositeLayer
    {
        public double qqq_setup_score { get; set; }
        public string narrative       { get; set; } = "";
        public string opus_verdict    { get; set; } = "UNKNOWN";
        public bool   stale           { get; set; }
        public string source_ts       { get; set; }  // extra JSON field
    }

    public class ConfluencePayload
    {
        public string         ts                { get; set; }
        public string         symbol            { get; set; }
        public string         proxy             { get; set; }  // extra JSON field
        public double?        price             { get; set; }
        public GexLayer       gex               { get; set; }
        public DarkPoolLayer  darkpool          { get; set; }
        public RegimeLayer    regime            { get; set; }
        public CompositeLayer composite         { get; set; }
        public double         dp_signal         { get; set; }
        public double         gex_signal        { get; set; }
        public double         regime_signal     { get; set; }
        public double         mtf_signal        { get; set; }
        public int            confluence_score  { get; set; }
        public string         alert             { get; set; }
        public string         alert_reason      { get; set; }
        public object         weights           { get; set; }  // extra JSON field (dict, ignored)
    }

    // -----------------------------------------------------------------------------
    //  INDICATOR
    // -----------------------------------------------------------------------------
    public class InstitutionalConfluence : Indicator
    {
        // ----- shared HTTP client (one per process is the .NET idiom)
        private static readonly HttpClient _http = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(8)
        };

        // ----- polling state
        private System.Threading.Timer  _pollTimer;
        private readonly object         _payloadLock = new object();
        private ConfluencePayload       _latest;       // latest server response
        private DateTime                _latestStamp = DateTime.MinValue;
        private bool                    _isPolling;    // re-entrancy guard

        // ----- MTF zone state (calculated locally from BarsArray)
        private string _mtfDaily = "UNKNOWN";
        private string _mtf4h    = "UNKNOWN";
        private string _mtfChart = "UNKNOWN";

        // Premium/Discount range bounds for the current daily/4h sessions
        private double _dailyHigh, _dailyLow, _dailyMid;
        private double _h4High,    _h4Low,    _h4Mid;
        private double _chartHigh, _chartLow, _chartMid;

        // Primary bars only — no AddDataSeries (keeps indicator on price panel)
        private const int  BIP_PRIMARY = 0;

        // ----- HUD rendering resources (initialized in OnRenderTargetChanged)
        private SharpDX.Direct2D1.Brush _bgBrush, _textBrush, _accentBrush;
        private SharpDX.Direct2D1.Brush _bullBrush, _bearBrush, _neutralBrush;
        private SharpDX.Direct2D1.Brush _alertBgBrush, _alertBorderBrush;
        private SharpDX.Direct2D1.Brush _borderBrush, _dimBrush;
        private SharpDX.Direct2D1.Brush _scorePosBrush, _scoreNegBrush, _scoreBarBgBrush;
        private TextFormat _hudFont, _hudHeaderFont, _hudLabelFont, _hudSmallFont, _hudScoreFont;

        // -----------------------------------------------------------------------------
        //  USER PROPERTIES
        // -----------------------------------------------------------------------------
        [NinjaScriptProperty]
        [Display(Name="Server URL", Order=1, GroupName="Connection")]
        public string ServerUrl { get; set; } = "http://127.0.0.1:8767";

        [NinjaScriptProperty]
        [Range(2, 300)]
        [Display(Name="Poll Interval (sec)", Order=2, GroupName="Connection")]
        public int PollIntervalSec { get; set; } = 15;

        [NinjaScriptProperty]
        [Display(Name="Show GEX Lines", Order=10, GroupName="Display")]
        public bool ShowGexLines { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name="Show MTF Zones", Order=11, GroupName="Display")]
        public bool ShowMtfZones { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name="Show HUD Panel", Order=12, GroupName="Display")]
        public bool ShowHud { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name="Audible Alerts", Order=13, GroupName="Display")]
        public bool AudibleAlerts { get; set; } = true;

        [XmlIgnore]
        [Display(Name="Call Wall Color", Order=20, GroupName="Colors")]
        public Brush CallWallBrush { get; set; } = Brushes.DodgerBlue;
        [Browsable(false)] public string CallWallBrushSerialize {
            get { return Serialize.BrushToString(CallWallBrush); }
            set { CallWallBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name="Put Wall Color", Order=21, GroupName="Colors")]
        public Brush PutWallBrush { get; set; } = Brushes.OrangeRed;
        [Browsable(false)] public string PutWallBrushSerialize {
            get { return Serialize.BrushToString(PutWallBrush); }
            set { PutWallBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name="GEX Flip Color", Order=22, GroupName="Colors")]
        public Brush FlipBrush { get; set; } = Brushes.MediumPurple;
        [Browsable(false)] public string FlipBrushSerialize {
            get { return Serialize.BrushToString(FlipBrush); }
            set { FlipBrush = Serialize.StringToBrush(value); } }

        // Public read-only signal accessor for strategies (ConfluenceBiasFilter consumes this)
        [Browsable(false), XmlIgnore]
        public ConfluencePayload Latest
        {
            get { lock (_payloadLock) return _latest; }
        }

        // =============================================================================
        //  STATE MACHINE
        // =============================================================================
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                                = "Institutional Confluence";
                Description                         = "GEX + Dark Pool + Macro confluence HUD with DP-dominant scoring";
                Calculate                           = Calculate.OnEachTick;
                IsOverlay                           = true;
                DisplayInDataBox                    = false;
                DrawOnPricePanel                    = true;
                PaintPriceMarkers                   = false;
                ScaleJustification                  = ScaleJustification.Right;
                IsSuspendedWhileInactive            = true;
            }
            else if (State == State.DataLoaded)
            {
                // Kick off polling timer
                _pollTimer = new System.Threading.Timer(
                    _ => PollServerAsync(),
                    null,
                    TimeSpan.FromMilliseconds(500),
                    TimeSpan.FromSeconds(PollIntervalSec));
            }
            else if (State == State.Terminated)
            {
                _pollTimer?.Dispose();
                _pollTimer = null;

                DisposeRenderResources();
            }
        }

        // =============================================================================
        //  BAR UPDATE -- compute MTF zones from BarsArray
        // =============================================================================
        protected override void OnBarUpdate()
        {
            if (BarsInProgress != BIP_PRIMARY) return;
            if (CurrentBars[BIP_PRIMARY] < 1) return;

            // Chart zone: 50-bar rolling range on 4H bars
            int chartLB = Math.Min(50, CurrentBars[BIP_PRIMARY]);
            _chartHigh = MAX(High, chartLB)[0];
            _chartLow  = MIN(Low,  chartLB)[0];
            _chartMid  = (_chartHigh + _chartLow) / 2.0;
            _mtfChart  = ClassifyZone(Close[0], _chartHigh, _chartLow, _chartMid);

            // Daily zone: last 4 × 4H bars ≈ 1 trading day
            int dailyLB = Math.Min(4, CurrentBars[BIP_PRIMARY]);
            _dailyHigh = MAX(High, dailyLB)[0];
            _dailyLow  = MIN(Low,  dailyLB)[0];
            _dailyMid  = (_dailyHigh + _dailyLow) / 2.0;
            _mtfDaily  = ClassifyZone(Close[0], _dailyHigh, _dailyLow, _dailyMid);

            // 4H zone: same as chart (chart IS 4H)
            _h4High = _chartHigh;
            _h4Low  = _chartLow;
            _h4Mid  = _chartMid;
            _mtf4h  = _mtfChart;
        }

        private static string ClassifyZone(double price, double high, double low, double mid)
        {
            if (high <= low) return "UNKNOWN";
            double range = high - low;
            double upperBand = mid + range * 0.15;   // 65% .. 100% = PREMIUM
            double lowerBand = mid - range * 0.15;   //  0% .. 35% = DISCOUNT
            if (price >= upperBand) return "PREMIUM";
            if (price <= lowerBand) return "DISCOUNT";
            return "EQUILIBRIUM";
        }

        // =============================================================================
        //  HTTP POLLING (runs on Timer thread -- NEVER block calculation thread)
        // =============================================================================
        private async void PollServerAsync()
        {
            if (_isPolling) return;   // skip if previous still in flight
            _isPolling = true;

            try
            {
                // Build query string with current price + MTF zones
                double curPrice = (CurrentBars[BIP_PRIMARY] > 0) ? Closes[BIP_PRIMARY][0] : 0.0;
                string url = string.Format(
                    "{0}/confluence/nq?price={1:F2}&mtf_d={2}&mtf_4h={3}&mtf_chart={4}",
                    ServerUrl.TrimEnd('/'),
                    curPrice,
                    _mtfDaily,
                    _mtf4h,
                    _mtfChart);

                using (var resp = await _http.GetAsync(url).ConfigureAwait(false))
                {
                    resp.EnsureSuccessStatusCode();
                    string json = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
                    var payload = new JavaScriptSerializer { MaxJsonLength = 8 * 1024 * 1024 }.Deserialize<ConfluencePayload>(json);

                    bool isNewAlert = false;
                    string priorAlert = null;

                    lock (_payloadLock)
                    {
                        priorAlert = _latest?.alert;
                        _latest = payload;
                        _latestStamp = DateTime.UtcNow;
                        isNewAlert = (payload?.alert != null && payload.alert != priorAlert);
                    }

                    if (isNewAlert && AudibleAlerts && payload != null)
                    {
                        // NT8 alert dispatch -- thread-safe
                        Dispatcher.InvokeAsync(() =>
                        {
                            try
                            {
                                Alert(
                                    "ConfluenceAlert_" + payload.alert,
                                    Priority.High,
                                    string.Format("[{0}] {1}", payload.alert, payload.alert_reason ?? ""),
                                    NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav",
                                    0,
                                    Brushes.Black,
                                    Brushes.OrangeRed);
                            }
                            catch (Exception ex) { Print("Alert dispatch error: " + ex.Message); }
                        });
                    }

                    // Trigger redraw — UpdateDrawLabels will be called from OnRender
                    ForceRefresh();
                }
            }
            catch (TaskCanceledException) { /* timeout, will retry */ }
            catch (Exception ex)
            {
                // Don't spam the log; throttle errors
                if ((DateTime.UtcNow - _latestStamp).TotalSeconds > 60)
                    Print(string.Format("[Confluence] poll error: {0}", ex.Message));
            }
            finally
            {
                _isPolling = false;
            }
        }

        // =============================================================================
        //  RENDERING -- GEX lines + MTF zones via draw objects (persistent across bars)
        // =============================================================================
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);

            ConfluencePayload p;
            lock (_payloadLock) { p = _latest; }

            // 1) Zone bands (SharpDX fills, behind everything else)
            if (ShowMtfZones && RenderTarget != null && _chartHigh > _chartLow)
            {
                try { DrawZoneBands(chartScale); }
                catch { }
            }

            // 2) GEX horizontal lines (persistent draw objects)
            if (ShowGexLines && p?.gex != null)
                DrawGexLines(p.gex);

            // 3) GEX level labels (SharpDX text at right edge of lines)
            if (ShowGexLines && p?.gex != null && RenderTarget != null)
            {
                try { DrawGexLabels(p.gex, chartScale); }
                catch { }
            }

            // 4) Clean up old test draw objects (runs each render, idempotent)
            if (p != null)
            {
                try { UpdateDrawLabels(p); }
                catch { }
            }

            // 5) SharpDX HUD panel
            if (ShowHud && p != null && RenderTarget != null)
            {
                try { DrawHud(chartControl, chartScale, p); }
                catch (Exception ex) { Print("[Confluence] DrawHud error: " + ex.Message); }
            }
        }

        // Called on render thread — removes old diagnostic/test draw objects (idempotent cleanup)
        private void UpdateDrawLabels(ConfluencePayload p)
        {
            RemoveDrawObject("IC_ARROW");
            RemoveDrawObject("IC_TR");
            RemoveDrawObject("IC_BL");
            RemoveDrawObject("IC_HUD_SCORE");
            RemoveDrawObject("IC_HUD_GEX");
            RemoveDrawObject("IC_HUD_TR");
            RemoveDrawObject("IC_HUD_TL");
            RemoveDrawObject("IC_LOADED_MARKER");
            RemoveDrawObject("IC_HUD_FALLBACK");
        }

        private void DrawGexLines(GexLayer g)
        {
            // RemoveDrawObject + Draw.HorizontalLine keeps levels live as they change
            if (g.flip.HasValue)
                Draw.HorizontalLine(this, "GEX_FLIP", g.flip.Value, FlipBrush,
                    DashStyleHelper.Dot, 2);
            if (g.call_wall.HasValue)
                Draw.HorizontalLine(this, "GEX_CALL_WALL", g.call_wall.Value, CallWallBrush,
                    DashStyleHelper.Dash, 2);
            if (g.put_wall.HasValue)
                Draw.HorizontalLine(this, "GEX_PUT_WALL", g.put_wall.Value, PutWallBrush,
                    DashStyleHelper.Dash, 2);
            if (g.hvl.HasValue)
                Draw.HorizontalLine(this, "GEX_HVL", g.hvl.Value, Brushes.Gold,
                    DashStyleHelper.DashDot, 1);
        }

        private void DrawMtfZones(ChartControl cc, ChartScale cs)
        {
            // Rectangles drawn via Draw.Rectangle (persistent)
            // Use last 100 bars as the x-axis anchor span
            if (CurrentBars[BIP_PRIMARY] < 10) return;

            int barsAgo = Math.Min(100, CurrentBars[BIP_PRIMARY] - 1);

            // CHART (lightest)
            if (_chartHigh > _chartLow)
            {
                double premTop = _chartHigh;
                double premBot = _chartHigh - (_chartHigh - _chartLow) * 0.35;
                double discTop = _chartLow + (_chartHigh - _chartLow) * 0.35;
                double discBot = _chartLow;

                Draw.Rectangle(this, "ZONE_CHART_PREMIUM", false,
                    barsAgo, premTop, 0, premBot,
                    Brushes.Red, Brushes.Red, 4);
                Draw.Rectangle(this, "ZONE_CHART_DISCOUNT", false,
                    barsAgo, discTop, 0, discBot,
                    Brushes.LimeGreen, Brushes.LimeGreen, 4);
            }
        }

        // -----------------------------------------------------------------------------
        //  SharpDX zone bands — Premium (red) and Discount (green) shaded areas
        // -----------------------------------------------------------------------------
        private void DrawZoneBands(ChartScale chartScale)
        {
            if (_chartHigh <= _chartLow) return;
            double range = _chartHigh - _chartLow;

            // Premium zone: top 35%
            double premTop = _chartHigh;
            double premBot = _chartHigh - range * 0.35;

            // Discount zone: bottom 35%
            double discTop = _chartLow + range * 0.35;
            double discBot = _chartLow;

            // Convert prices to pixel Y coordinates
            float pxPremTop = (float)chartScale.GetYByValue(premTop);
            float pxPremBot = (float)chartScale.GetYByValue(premBot);
            float pxDiscTop = (float)chartScale.GetYByValue(discTop);
            float pxDiscBot = (float)chartScale.GetYByValue(discBot);

            // Chart pixel X bounds
            float chartLeft = (float)ChartPanel.X;
            float chartW    = (float)ChartPanel.W;

            // Premium band (semi-transparent red)
            if (pxPremTop < pxPremBot)  // Y is inverted in screen coords
            {
                var rect = new RectangleF(chartLeft, pxPremTop, chartW, pxPremBot - pxPremTop);
                using (var brush = new SolidColorBrush(RenderTarget, new Color4(0.85f, 0.15f, 0.15f, 0.08f)))
                    RenderTarget.FillRectangle(rect, brush);
                // Left edge label
                using (var labelBrush = new SolidColorBrush(RenderTarget, new Color4(0.90f, 0.30f, 0.30f, 0.70f)))
                {
                    var labelRect = new RectangleF(chartLeft + 4f, pxPremTop + 3f, 80f, 14f);
                    RenderTarget.DrawText("PREMIUM", _hudSmallFont ?? _hudFont, labelRect, labelBrush);
                }
            }

            // Discount band (semi-transparent green)
            if (pxDiscTop < pxDiscBot)
            {
                var rect = new RectangleF(chartLeft, pxDiscTop, chartW, pxDiscBot - pxDiscTop);
                using (var brush = new SolidColorBrush(RenderTarget, new Color4(0.15f, 0.75f, 0.25f, 0.08f)))
                    RenderTarget.FillRectangle(rect, brush);
                using (var labelBrush = new SolidColorBrush(RenderTarget, new Color4(0.25f, 0.85f, 0.35f, 0.70f)))
                {
                    var labelRect = new RectangleF(chartLeft + 4f, pxDiscBot - 16f, 80f, 14f);
                    RenderTarget.DrawText("DISCOUNT", _hudSmallFont ?? _hudFont, labelRect, labelBrush);
                }
            }
        }

        // -----------------------------------------------------------------------------
        //  GEX level labels — SharpDX text at right edge of each horizontal line
        // -----------------------------------------------------------------------------
        private void DrawGexLabels(GexLayer g, ChartScale chartScale)
        {
            var font = _hudSmallFont ?? _hudFont;
            if (font == null) return;

            float labelX = (float)(ChartPanel.X + ChartPanel.W) - 72f;
            float labelW = 70f;
            float labelH = 14f;

            // Call Wall label
            if (g.call_wall.HasValue)
            {
                float y = (float)chartScale.GetYByValue(g.call_wall.Value) - 7f;
                using (var b = new SolidColorBrush(RenderTarget, new Color4(0.25f, 0.55f, 1.00f, 0.85f)))
                    RenderTarget.DrawText("CALL WALL", font, new RectangleF(labelX, y, labelW, labelH), b);
            }

            // Put Wall label
            if (g.put_wall.HasValue)
            {
                float y = (float)chartScale.GetYByValue(g.put_wall.Value) - 7f;
                using (var b = new SolidColorBrush(RenderTarget, new Color4(1.00f, 0.45f, 0.10f, 0.85f)))
                    RenderTarget.DrawText("PUT WALL", font, new RectangleF(labelX, y, labelW, labelH), b);
            }

            // Flip label
            if (g.flip.HasValue)
            {
                float y = (float)chartScale.GetYByValue(g.flip.Value) - 7f;
                using (var b = new SolidColorBrush(RenderTarget, new Color4(0.80f, 0.20f, 0.95f, 0.85f)))
                    RenderTarget.DrawText("GEX FLIP", font, new RectangleF(labelX, y, labelW, labelH), b);
            }
        }

        // -----------------------------------------------------------------------------
        //  HUD  (Bloomberg Terminal-quality panel)
        // -----------------------------------------------------------------------------
        private void DrawHud(ChartControl cc, ChartScale cs, ConfluencePayload p)
        {
            EnsureRenderResources();
            if (_hudFont == null)
            {
                string fallback = string.Format(
                    "CONFLUENCE | GEX:{0} DP:{1} Score:{2:+0;-0;0} | {3}",
                    p.gex?.bias ?? "?",
                    p.darkpool?.bias ?? "?",
                    p.confluence_score,
                    p.alert ?? "OK");
                Draw.TextFixed(this, "IC_HUD_FALLBACK", fallback,
                    TextPosition.TopRight, Brushes.Gold, new SimpleFont("Consolas", 11),
                    Brushes.Transparent, Brushes.Black, 0);
                return;
            }

            float pad   = 16f;
            float width = 360f;
            float totalH = 240f + (!string.IsNullOrEmpty(p.alert) ? 42f : 0f);
            float x  = (float)(ChartPanel.X + ChartPanel.W) - width - pad;
            float y  = (float)ChartPanel.Y + pad;
            float lx = x + 12f;

            // Background panel
            var bg = new RectangleF(x, y, width, totalH);
            RenderTarget.FillRectangle(bg, _bgBrush);
            RenderTarget.DrawRectangle(bg, _borderBrush, 0.8f);

            // Header bar — tinted amber strip
            var headerRect = new RectangleF(x, y, width, 22f);
            using (var headerFill = new SolidColorBrush(RenderTarget, new Color4(1.00f, 0.55f, 0.00f, 0.18f)))
                RenderTarget.FillRectangle(headerRect, headerFill);
            RenderTarget.DrawText("INSTITUTIONAL CONFLUENCE", _hudHeaderFont,
                new RectangleF(lx, y + 4f, width - 24, 18f), _accentBrush);
            float ly = y + 26f;

            // Amber separator
            RenderTarget.DrawLine(new Vector2(x + 1, ly), new Vector2(x + width - 1, ly), _accentBrush, 0.5f);
            ly += 6f;

            // Row 1 — GEX
            string gexValue = (p.gex?.bias ?? "?").ToUpper();
            string gexSub = null;
            if (p.gex?.flip.HasValue == true)
                gexSub = string.Format("Flip {0:N0}   CW {1:N0}   PW {2:N0}",
                    p.gex.flip.Value, p.gex.call_wall ?? 0, p.gex.put_wall ?? 0);
            ly = DrawDataRow(lx, ly, width, "GEX", gexValue, BiasBrush(p.gex?.bias), gexSub);

            // Divider
            RenderTarget.DrawLine(new Vector2(x + 8, ly), new Vector2(x + width - 8, ly), _borderBrush, 0.5f);
            ly += 4f;

            // Row 2 — Dark Pool
            string dpValue = string.Format("{0}  {1:F0}% conf",
                (p.darkpool?.bias ?? "?").ToUpper(), (p.darkpool?.confidence ?? 0) * 100);
            ly = DrawDataRow(lx, ly, width, "DARK POOL", dpValue, BiasBrush(p.darkpool?.bias));

            // Divider
            RenderTarget.DrawLine(new Vector2(x + 8, ly), new Vector2(x + width - 8, ly), _borderBrush, 0.5f);
            ly += 4f;

            // Row 3 — Regime
            string regValue = (p.regime?.macro ?? "?").Replace("_", " ");
            ly = DrawDataRow(lx, ly, width, "REGIME", regValue, BiasBrush(p.regime?.macro));

            // Divider
            RenderTarget.DrawLine(new Vector2(x + 8, ly), new Vector2(x + width - 8, ly), _borderBrush, 0.5f);
            ly += 4f;

            // Row 4 — MTF Zones
            string mtfValue = string.Format("Daily:{0}  Chart:{1}", Cap(_mtfDaily), Cap(_mtfChart));
            var mtfBrush = (_mtfDaily == "PREMIUM") ? _bearBrush
                         : (_mtfDaily == "DISCOUNT") ? _bullBrush
                         : _neutralBrush;
            ly = DrawDataRow(lx, ly, width, "MTF ZONES", mtfValue, mtfBrush);

            // Thick separator before score
            ly += 4f;
            RenderTarget.DrawLine(new Vector2(x + 1, ly), new Vector2(x + width - 1, ly), _borderBrush, 1.5f);
            ly += 8f;

            // Score number (large, left side)
            string scoreStr = p.confluence_score.ToString("+0;-0;0");
            var scoreBrush = p.confluence_score >= 2 ? _bullBrush
                           : p.confluence_score <= -2 ? _bearBrush
                           : _neutralBrush;
            RenderTarget.DrawText(scoreStr, _hudScoreFont, new RectangleF(lx, ly, 60f, 26f), scoreBrush);

            // Signal bar (beside score)
            float barX = lx + 64f;
            float barW = width - 100f;
            float barH = 10f;
            float barY = ly + 8f;
            RenderTarget.FillRectangle(new RectangleF(barX, barY, barW, barH), _scoreBarBgBrush);
            float scorePct = Math.Max(-1f, Math.Min(1f, p.confluence_score / 5.0f));
            float midX = barX + barW / 2f;
            if (scorePct >= 0)
            {
                float fillW = (barW / 2f) * scorePct;
                RenderTarget.FillRectangle(new RectangleF(midX, barY, fillW, barH), _scorePosBrush);
            }
            else
            {
                float fillW = (barW / 2f) * (-scorePct);
                RenderTarget.FillRectangle(new RectangleF(midX - fillW, barY, fillW, barH), _scoreNegBrush);
            }
            // Center tick mark
            RenderTarget.DrawLine(new Vector2(midX, barY), new Vector2(midX, barY + barH), _borderBrush, 1f);
            ly += 28f;

            // Score breakdown
            string breakdown = string.Format("DP {0:+0.0;-0.0;0}  GEX {1:+0.0;-0.0;0}  REG {2:+0.0;-0.0;0}  MTF {3:+0.0;-0.0;0}",
                p.dp_signal, p.gex_signal, p.regime_signal, p.mtf_signal);
            RenderTarget.DrawText(breakdown, _hudSmallFont, new RectangleF(lx, ly, width - 24, 14f), _dimBrush);
            ly += 16f;

            // Alert box (at bottom if active)
            if (!string.IsNullOrEmpty(p.alert))
            {
                ly += 4f;
                var alertRect = new RectangleF(x + 4, ly, width - 8, 34f);
                RenderTarget.FillRectangle(alertRect, _alertBgBrush);
                RenderTarget.DrawRectangle(alertRect, _alertBorderBrush, 1f);
                RenderTarget.DrawText("\u26A0  " + p.alert.Replace("_", " "), _hudFont,
                    new RectangleF(x + 10, ly + 4, width - 20, 16f), _bearBrush);
                if (!string.IsNullOrEmpty(p.alert_reason))
                    RenderTarget.DrawText(p.alert_reason, _hudSmallFont,
                        new RectangleF(x + 10, ly + 20, width - 20, 13f), _dimBrush);
            }
        }

        private float DrawDataRow(float lx, float ly, float width, string label, string value,
            SharpDX.Direct2D1.Brush valueBrush, string subtext = null)
        {
            RenderTarget.DrawText(label, _hudLabelFont, new RectangleF(lx, ly, 90f, 17f), _dimBrush);
            RenderTarget.DrawText(value, _hudFont, new RectangleF(lx + 90f, ly, width - 100f, 17f), valueBrush ?? _textBrush);
            ly += 18f;
            if (!string.IsNullOrEmpty(subtext))
            {
                RenderTarget.DrawText(subtext, _hudSmallFont,
                    new RectangleF(lx + 90f, ly, width - 100f, 14f), _dimBrush);
                ly += 14f;
            }
            return ly;
        }

        private SharpDX.Direct2D1.Brush BiasBrush(string bias)
        {
            switch ((bias ?? "").ToUpperInvariant())
            {
                case "BULLISH":
                case "BULL":
                case "RISK_ON":
                    return _bullBrush;
                case "BEARISH":
                case "BEAR":
                case "RISK_OFF":
                    return _bearBrush;
                default:
                    return _neutralBrush;
            }
        }

        private static string Cap(string s)
        {
            if (string.IsNullOrEmpty(s) || s == "UNKNOWN") return "—";
            return char.ToUpper(s[0]) + s.Substring(1).ToLower();
        }

        // -----------------------------------------------------------------------------
        //  Render target lifecycle
        // -----------------------------------------------------------------------------
        public override void OnRenderTargetChanged()
        {
            DisposeRenderResources();
            if (RenderTarget == null) return;

            // Background: very dark blue-black, high opacity
            _bgBrush          = new SolidColorBrush(RenderTarget, new Color4(0.04f, 0.04f, 0.08f, 0.94f));
            // Border: subtle blue-gray
            _borderBrush      = new SolidColorBrush(RenderTarget, new Color4(0.20f, 0.25f, 0.35f, 1.00f));
            // Header/accent: Bloomberg orange
            _accentBrush      = new SolidColorBrush(RenderTarget, new Color4(1.00f, 0.55f, 0.00f, 1.00f));
            // Body text: near-white
            _textBrush        = new SolidColorBrush(RenderTarget, new Color4(0.87f, 0.87f, 0.90f, 1.00f));
            // Dim label text: medium gray
            _dimBrush         = new SolidColorBrush(RenderTarget, new Color4(0.50f, 0.52f, 0.58f, 1.00f));
            // Bullish: clean green
            _bullBrush        = new SolidColorBrush(RenderTarget, new Color4(0.20f, 0.85f, 0.35f, 1.00f));
            // Bearish: clean red
            _bearBrush        = new SolidColorBrush(RenderTarget, new Color4(0.95f, 0.25f, 0.25f, 1.00f));
            // Neutral: mid gray
            _neutralBrush     = new SolidColorBrush(RenderTarget, new Color4(0.60f, 0.63f, 0.70f, 1.00f));
            // Alert
            _alertBgBrush     = new SolidColorBrush(RenderTarget, new Color4(0.45f, 0.07f, 0.07f, 0.92f));
            _alertBorderBrush = new SolidColorBrush(RenderTarget, new Color4(0.90f, 0.20f, 0.20f, 1.00f));
            // Score bar
            _scorePosBrush    = new SolidColorBrush(RenderTarget, new Color4(0.15f, 0.70f, 0.30f, 0.80f));
            _scoreNegBrush    = new SolidColorBrush(RenderTarget, new Color4(0.80f, 0.18f, 0.18f, 0.80f));
            _scoreBarBgBrush  = new SolidColorBrush(RenderTarget, new Color4(0.12f, 0.13f, 0.16f, 1.00f));

            var factory = Core.Globals.DirectWriteFactory;
            _hudHeaderFont = new TextFormat(factory, "Segoe UI", FontWeight.SemiBold, FontStyle.Normal, 11f);
            _hudLabelFont  = new TextFormat(factory, "Segoe UI", FontWeight.Normal,   FontStyle.Normal, 10f);
            _hudFont       = new TextFormat(factory, "Segoe UI", FontWeight.Normal,   FontStyle.Normal, 11f);
            _hudScoreFont  = new TextFormat(factory, "Consolas", FontWeight.Bold,     FontStyle.Normal, 20f);
            _hudSmallFont  = new TextFormat(factory, "Segoe UI", FontWeight.Normal,   FontStyle.Normal, 9f);
        }

        private void EnsureRenderResources()
        {
            if (_hudFont == null && RenderTarget != null)
                OnRenderTargetChanged();
        }

        private void DisposeRenderResources()
        {
            _bgBrush?.Dispose();          _bgBrush = null;
            _borderBrush?.Dispose();      _borderBrush = null;
            _textBrush?.Dispose();        _textBrush = null;
            _dimBrush?.Dispose();         _dimBrush = null;
            _accentBrush?.Dispose();      _accentBrush = null;
            _bullBrush?.Dispose();        _bullBrush = null;
            _bearBrush?.Dispose();        _bearBrush = null;
            _neutralBrush?.Dispose();     _neutralBrush = null;
            _alertBgBrush?.Dispose();     _alertBgBrush = null;
            _alertBorderBrush?.Dispose(); _alertBorderBrush = null;
            _scorePosBrush?.Dispose();    _scorePosBrush = null;
            _scoreNegBrush?.Dispose();    _scoreNegBrush = null;
            _scoreBarBgBrush?.Dispose();  _scoreBarBgBrush = null;
            _hudFont?.Dispose();          _hudFont = null;
            _hudHeaderFont?.Dispose();    _hudHeaderFont = null;
            _hudLabelFont?.Dispose();     _hudLabelFont = null;
            _hudSmallFont?.Dispose();     _hudSmallFont = null;
            _hudScoreFont?.Dispose();     _hudScoreFont = null;
        }
    }
}

