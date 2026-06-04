// =================================================================================
//  EquilibriumModel.cs
//  ===================
//  Sibling indicator to InstitutionalConfluence.cs. Consumes the Equilibrium
//  Model endpoint (/equilibrium/nq) from confluence_server.py and renders:
//
//    - Synthetic Fair Value (SFV) horizontal line (yellow dashed) — the magnet
//    - Premium zone band (red fill, between SFV and upper_premium)
//    - Discount zone band (green fill, between lower_discount and SFV)
//    - Extreme bands (red/green dotted lines at ±2.5σ)
//    - GEX level lines:
//        Weekly: Call Wall (cyan dashed) / Zero Gamma (yellow solid) / Put Wall (magenta dashed)
//        Daily:  Call Wall (cyan dotted) / Zero Gamma (yellow dotted) / Put Wall (magenta dotted)
//    - HUD panel (top-LEFT to avoid InstitutionalConfluence HUD on top-right):
//        PRICE / SFV / DISTANCE / ZONE
//        Weekly + Daily strike level summary
//        4-regime grid (2x2): Gamma / Vol / Trend / InstBias
//        Alerts list (CRITICAL / WARNING / INFO)
//
//  Posts NQ price, NDX spot, realized vol (5d/30d), and EMAs (20/50) on each poll.
//  Designed to be loaded ALONGSIDE InstitutionalConfluence.cs on the same NQ chart.
//
//  Author: Michael / Peak Asset Performance LLC
// =================================================================================

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
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
using SolidColorBrush = SharpDX.Direct2D1.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.PeakAssetPerformance
{
    // -----------------------------------------------------------------------------
    //  PAYLOAD DTOs  (mirror EquilibriumPayload from equilibrium_module.py)
    // -----------------------------------------------------------------------------
    public class EqStrikeBar
    {
        public double strike { get; set; }
        public double gex    { get; set; }
        public string type   { get; set; } = "NET";
    }

    public class EqGexProfile
    {
        public string         timeframe   { get; set; }
        public string         expiry_date { get; set; }
        public double         net_gex     { get; set; }
        public double?        call_wall   { get; set; }
        public double?        zero_gamma  { get; set; }
        public double?        put_wall    { get; set; }
        public double?        hvl         { get; set; }
        public List<EqStrikeBar> histogram { get; set; } = new List<EqStrikeBar>();
        public string         source      { get; set; }
        public bool           stale       { get; set; }
    }

    public class EqRegimeQuad
    {
        public string gamma_regime       { get; set; } = "NEUTRAL";
        public string gamma_label        { get; set; } = "";
        public string volatility_regime  { get; set; } = "STABLE";
        public string vol_label          { get; set; } = "";
        public string trend_alignment    { get; set; } = "NEUTRAL";
        public string trend_label        { get; set; } = "";
        public string institutional_bias { get; set; } = "NEUTRAL";
        public string bias_label         { get; set; } = "";
    }

    public class EqAlert
    {
        public string severity { get; set; }
        public string icon     { get; set; }
        public string msg      { get; set; }
    }

    public class EquilibriumPayload
    {
        public string         ts              { get; set; }
        public string         symbol          { get; set; }
        public string         proxy_index     { get; set; }
        public double?        price           { get; set; }
        public double?        price_ndx       { get; set; }
        public EqGexProfile   weekly          { get; set; }
        public EqGexProfile   daily           { get; set; }
        public double?        sfv             { get; set; }
        public double?        upper_premium   { get; set; }
        public double?        lower_discount  { get; set; }
        public double?        extreme_upper   { get; set; }
        public double?        extreme_lower   { get; set; }
        public double?        sigma_points    { get; set; }
        public string         current_zone    { get; set; } = "UNKNOWN";
        public double?        distance_to_sfv { get; set; }
        public EqRegimeQuad   regime          { get; set; } = new EqRegimeQuad();
        public List<EqAlert>  alerts          { get; set; } = new List<EqAlert>();
    }

    // -----------------------------------------------------------------------------
    //  INDICATOR
    // -----------------------------------------------------------------------------
    public class EquilibriumModel : Indicator
    {
        private static readonly HttpClient _http = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(10)
        };

        private System.Threading.Timer _pollTimer;
        private readonly object        _payloadLock = new object();
        private EquilibriumPayload     _latest;
        private DateTime               _latestStamp = DateTime.MinValue;
        private bool                   _isPolling;
        private string                 _priorAlertHash = "";

        // BarsArray indices: 0 = NQ primary, 1 = NDX
        private const int BIP_NQ  = 0;
        private const int BIP_NDX = 1;

        // SharpDX
        private SharpDX.Direct2D1.Brush _bgBrush, _textBrush, _accentBrush;
        private SharpDX.Direct2D1.Brush _bullBrush, _bearBrush, _neutralBrush, _warnBrush;
        private SharpDX.Direct2D1.Brush _premBgBrush, _discBgBrush;
        private SharpDX.Direct2D1.Brush _sfvBrush;
        private SharpDX.Direct2D1.Brush _alertCritBrush, _alertWarnBrush, _alertInfoBrush;
        private TextFormat _font, _bigFont, _smallFont, _hugeFont;

        // -----------------------------------------------------------------------------
        //  USER PROPERTIES
        // -----------------------------------------------------------------------------
        [NinjaScriptProperty]
        [Display(Name="Server URL", Order=1, GroupName="Connection")]
        public string ServerUrl { get; set; } = "http://127.0.0.1:8767";

        [NinjaScriptProperty]
        [Range(15, 300)]
        [Display(Name="Poll Interval (sec)", Order=2, GroupName="Connection")]
        public int PollIntervalSec { get; set; } = 60;

        [NinjaScriptProperty]
        [Display(Name="NDX Symbol", Order=3, GroupName="Connection")]
        public string NdxSymbol { get; set; } = "^NDX";  // NT8 symbol mapping varies

        [NinjaScriptProperty]
        [Display(Name="Show SFV Line", Order=10, GroupName="Display")]
        public bool ShowSfv { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name="Show Zone Bands", Order=11, GroupName="Display")]
        public bool ShowZoneBands { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name="Show GEX Level Lines", Order=12, GroupName="Display")]
        public bool ShowGexLevels { get; set; } = true;

        [NinjaScriptProperty]
        [Display(Name="Show Equilibrium HUD", Order=13, GroupName="Display")]
        public bool ShowHud { get; set; } = true;

        [NinjaScriptProperty]
        [Range(20, 200)]
        [Display(Name="Realized Vol Lookback (bars)", Order=20, GroupName="Inputs")]
        public int RvLookback { get; set; } = 100;

        // Read-only public accessor for bridge consumption
        [Browsable(false), XmlIgnore]
        public EquilibriumPayload Latest
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
                Name                     = "Equilibrium Model";
                Description              = "Weekly + Daily GEX Synthetic SFV + 4-regime classifier";
                Calculate                = Calculate.OnEachTick;
                IsOverlay                = true;
                DisplayInDataBox         = false;
                DrawOnPricePanel         = true;
                PaintPriceMarkers        = false;
                IsSuspendedWhileInactive = true;
            }
            else if (State == State.Configure)
            {
                // NDX as secondary BarsArray series
                AddDataSeries(NdxSymbol, BarsPeriodType.Minute, 5);
            }
            else if (State == State.DataLoaded)
            {
                _pollTimer = new System.Threading.Timer(
                    _ => PollServerAsync(),
                    null,
                    TimeSpan.FromMilliseconds(2000),  // initial delay
                    TimeSpan.FromSeconds(PollIntervalSec));
            }
            else if (State == State.Terminated)
            {
                _pollTimer?.Dispose();
                _pollTimer = null;
                DisposeRenderResources();
            }
        }

        protected override void OnBarUpdate()
        {
            // No per-bar computation needed; everything is on-demand via poll.
            // BarsArray[1] (NDX) drives spot value used in the polling URL.
        }

        // =============================================================================
        //  HTTP POLLING
        // =============================================================================
        private async void PollServerAsync()
        {
            if (_isPolling) return;
            _isPolling = true;

            try
            {
                if (CurrentBars[BIP_NQ] < RvLookback + 5 ||
                    CurrentBars[BIP_NDX] < 5)
                {
                    // Not enough history yet
                    return;
                }

                double nqPx  = Closes[BIP_NQ][0];
                double ndxPx = Closes[BIP_NDX][0];

                // Realized vol -- daily decimal scale from log returns
                double rv5  = ComputeRealizedVol(5);
                double rv30 = ComputeRealizedVol(30);

                // EMAs
                double ema20 = EMA(Closes[BIP_NQ], 20)[0];
                double ema50 = EMA(Closes[BIP_NQ], 50)[0];

                string url = string.Format(
                    "{0}/equilibrium/nq?price={1:F2}&ndx={2:F2}&rv5={3:F6}&rv30={4:F6}&ema20={5:F2}&ema50={6:F2}",
                    ServerUrl.TrimEnd('/'),
                    nqPx, ndxPx, rv5, rv30, ema20, ema50);

                using (var resp = await _http.GetAsync(url).ConfigureAwait(false))
                {
                    resp.EnsureSuccessStatusCode();
                    string json = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
                    var payload = new JavaScriptSerializer { MaxJsonLength = 8 * 1024 * 1024 }.Deserialize<EquilibriumPayload>(json);

                    bool newAlerts = false;
                    string alertHash = "";
                    if (payload?.alerts != null && payload.alerts.Count > 0)
                        alertHash = string.Join("|", payload.alerts.Select(a => a.severity + ":" + a.msg));

                    lock (_payloadLock)
                    {
                        _latest = payload;
                        _latestStamp = DateTime.UtcNow;
                        if (alertHash != _priorAlertHash && !string.IsNullOrEmpty(alertHash))
                            newAlerts = true;
                        _priorAlertHash = alertHash;
                    }

                    if (newAlerts && payload?.alerts != null)
                    {
                        var crit = payload.alerts.FirstOrDefault(a => a.severity == "CRITICAL");
                        if (crit != null)
                        {
                            Dispatcher.InvokeAsync(() =>
                            {
                                try
                                {
                                    Alert("EQM_" + crit.severity,
                                        Priority.High,
                                        "[EQUILIBRIUM] " + crit.msg,
                                        NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav",
                                        0,
                                        Brushes.Black, Brushes.Red);
                                }
                                catch (Exception ex) { Print("EQM alert err: " + ex.Message); }
                            });
                        }
                    }

                    ForceRefresh();
                }
            }
            catch (TaskCanceledException) { /* timeout */ }
            catch (Exception ex)
            {
                if ((DateTime.UtcNow - _latestStamp).TotalSeconds > 120)
                    Print("[Equilibrium] poll err: " + ex.Message);
            }
            finally
            {
                _isPolling = false;
            }
        }

        // Log-return realized vol (sample stdev, daily scale assumed)
        private double ComputeRealizedVol(int periods)
        {
            int n = Math.Min(periods * 78, RvLookback); // ~78 5-min bars per day; cap by lookback
            if (CurrentBars[BIP_NQ] < n + 1) return 0.0;

            var rets = new List<double>(n);
            for (int i = 0; i < n; i++)
            {
                double p1 = Closes[BIP_NQ][i];
                double p0 = Closes[BIP_NQ][i + 1];
                if (p0 > 0) rets.Add(Math.Log(p1 / p0));
            }
            if (rets.Count < 2) return 0.0;
            double mean = rets.Sum() / rets.Count;
            double var  = rets.Sum(r => (r - mean) * (r - mean)) / (rets.Count - 1);
            double stdev = Math.Sqrt(var);
            // Scale per-bar stdev to daily (78 bars/day for 5-min)
            return stdev * Math.Sqrt(78.0);
        }

        // =============================================================================
        //  RENDERING
        // =============================================================================
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);

            EquilibriumPayload p;
            lock (_payloadLock) { p = _latest; }
            if (p == null) return;

            // 1) SFV line + zone bands as draw objects
            if (ShowSfv) DrawSfvLine(p);
            if (ShowZoneBands) DrawZoneBands(p);
            if (ShowGexLevels) DrawGexLevelLines(p);

            // 2) HUD panel (SharpDX, top-LEFT to differ from InstitutionalConfluence)
            if (ShowHud && RenderTarget != null) DrawHud(chartControl, chartScale, p);
        }

        private void DrawSfvLine(EquilibriumPayload p)
        {
            if (!p.sfv.HasValue) return;
            Draw.HorizontalLine(this, "EQM_SFV", p.sfv.Value, Brushes.Yellow,
                DashStyleHelper.Dash, 3);
            // Optional small label via draw text
            if (CurrentBars[0] > 1)
            {
                Draw.Text(this, "EQM_SFV_LABEL",
                    string.Format("SFV {0:F2}", p.sfv.Value),
                    0, p.sfv.Value, Brushes.Yellow);
            }
        }

        private void DrawZoneBands(EquilibriumPayload p)
        {
            if (!p.sfv.HasValue || !p.upper_premium.HasValue || !p.lower_discount.HasValue)
                return;

            if (CurrentBars[BIP_NQ] < 10) return;
            int barsAgo = Math.Min(200, CurrentBars[BIP_NQ] - 1);

            // Premium zone (red fill: upper_premium → SFV)
            Draw.Rectangle(this, "EQM_PREM_ZONE", false,
                barsAgo, p.upper_premium.Value, 0, p.sfv.Value,
                Brushes.IndianRed, Brushes.IndianRed, 8);

            // Discount zone (green fill: SFV → lower_discount)
            Draw.Rectangle(this, "EQM_DISC_ZONE", false,
                barsAgo, p.sfv.Value, 0, p.lower_discount.Value,
                Brushes.SeaGreen, Brushes.SeaGreen, 8);

            // Extreme bands as dotted lines
            if (p.extreme_upper.HasValue)
                Draw.HorizontalLine(this, "EQM_EXT_UP", p.extreme_upper.Value,
                    Brushes.OrangeRed, DashStyleHelper.Dot, 1);
            if (p.extreme_lower.HasValue)
                Draw.HorizontalLine(this, "EQM_EXT_DN", p.extreme_lower.Value,
                    Brushes.LimeGreen, DashStyleHelper.Dot, 1);
        }

        private void DrawGexLevelLines(EquilibriumPayload p)
        {
            // Weekly GEX levels (bold)
            if (p.weekly != null)
            {
                if (p.weekly.call_wall.HasValue)
                    Draw.HorizontalLine(this, "EQM_W_CALL", p.weekly.call_wall.Value,
                        Brushes.Cyan, DashStyleHelper.Dash, 2);
                if (p.weekly.zero_gamma.HasValue)
                    Draw.HorizontalLine(this, "EQM_W_ZG", p.weekly.zero_gamma.Value,
                        Brushes.Goldenrod, DashStyleHelper.Solid, 2);
                if (p.weekly.put_wall.HasValue)
                    Draw.HorizontalLine(this, "EQM_W_PUT", p.weekly.put_wall.Value,
                        Brushes.Magenta, DashStyleHelper.Dash, 2);
            }

            // Daily GEX levels (lighter)
            if (p.daily != null)
            {
                if (p.daily.call_wall.HasValue)
                    Draw.HorizontalLine(this, "EQM_D_CALL", p.daily.call_wall.Value,
                        Brushes.LightCyan, DashStyleHelper.Dot, 1);
                if (p.daily.zero_gamma.HasValue)
                    Draw.HorizontalLine(this, "EQM_D_ZG", p.daily.zero_gamma.Value,
                        Brushes.LightYellow, DashStyleHelper.Dot, 1);
                if (p.daily.put_wall.HasValue)
                    Draw.HorizontalLine(this, "EQM_D_PUT", p.daily.put_wall.Value,
                        Brushes.Pink, DashStyleHelper.Dot, 1);
            }
        }

        // -----------------------------------------------------------------------------
        //  HUD (top-LEFT to coexist with InstitutionalConfluence top-RIGHT)
        // -----------------------------------------------------------------------------
        private void DrawHud(ChartControl cc, ChartScale cs, EquilibriumPayload p)
        {
            EnsureRenderResources();
            if (_font == null) return;

            float pad = 12f;
            float width  = 320f;
            float height = 380f;
            float x = (float)ChartPanel.X + pad;
            float y = (float)ChartPanel.Y + pad;

            var bg = new RectangleF(x, y, width, height);
            RenderTarget.FillRectangle(bg, _bgBrush);

            float lx = x + 12f;
            float ly = y + 10f;
            const float lineH = 17f;

            // -- HEADER
            RenderTarget.DrawText("EQUILIBRIUM MODEL", _bigFont,
                new RectangleF(lx, ly, width - 24, lineH), _accentBrush);
            ly += lineH + 4;
            RenderTarget.DrawLine(new Vector2(lx, ly), new Vector2(x + width - 12, ly),
                _accentBrush, 0.6f);
            ly += 6;

            // -- PRICE / SFV / DISTANCE
            string priceLine = string.Format("Price:  {0,9:F2}", p.price ?? 0);
            RenderTarget.DrawText(priceLine, _font,
                new RectangleF(lx, ly, width - 24, lineH), _textBrush);
            ly += lineH;

            if (p.sfv.HasValue)
            {
                string sfvLine = string.Format("SFV:    {0,9:F2}", p.sfv.Value);
                RenderTarget.DrawText(sfvLine, _font,
                    new RectangleF(lx, ly, width - 24, lineH), _accentBrush);
                ly += lineH;
            }

            if (p.distance_to_sfv.HasValue)
            {
                string distLine = string.Format("Δ to SFV:  {0,+0;-0;0} pts", p.distance_to_sfv.Value);
                var distBrush = Math.Abs(p.distance_to_sfv.Value) > 30 ? _warnBrush : _textBrush;
                RenderTarget.DrawText(distLine, _font,
                    new RectangleF(lx, ly, width - 24, lineH), distBrush);
                ly += lineH;
            }

            // -- ZONE BADGE
            string zone = p.current_zone ?? "UNKNOWN";
            var zoneBrush = zone == "PREMIUM"     ? _bearBrush
                          : zone == "DISCOUNT"    ? _bullBrush
                          : zone == "EQUILIBRIUM" ? _neutralBrush
                          : _textBrush;
            string zoneLine = "Zone:   " + zone;
            RenderTarget.DrawText(zoneLine, _font,
                new RectangleF(lx, ly, width - 24, lineH), zoneBrush);
            ly += lineH;

            // separator
            ly += 4;
            RenderTarget.DrawLine(new Vector2(lx, ly), new Vector2(x + width - 12, ly),
                _accentBrush, 0.4f);
            ly += 4;

            // -- WEEKLY GEX (3 columns)
            if (p.weekly != null && !p.weekly.stale)
            {
                string wLine = string.Format("Weekly  Net:{0:+0.00;-0.00;0}B", p.weekly.net_gex / 1e9);
                RenderTarget.DrawText(wLine, _font,
                    new RectangleF(lx, ly, width - 24, lineH), _textBrush);
                ly += lineH;

                string wLevels = string.Format("  C:{0:F0}  ZG:{1:F0}  P:{2:F0}",
                    p.weekly.call_wall ?? 0, p.weekly.zero_gamma ?? 0, p.weekly.put_wall ?? 0);
                RenderTarget.DrawText(wLevels, _smallFont,
                    new RectangleF(lx, ly, width - 24, lineH), _textBrush);
                ly += lineH - 2;
            }

            // -- DAILY GEX
            if (p.daily != null && !p.daily.stale)
            {
                string dLine = string.Format("Daily   Net:{0:+0.00;-0.00;0}B", p.daily.net_gex / 1e9);
                RenderTarget.DrawText(dLine, _font,
                    new RectangleF(lx, ly, width - 24, lineH), _textBrush);
                ly += lineH;

                string dLevels = string.Format("  C:{0:F0}  ZG:{1:F0}  P:{2:F0}",
                    p.daily.call_wall ?? 0, p.daily.zero_gamma ?? 0, p.daily.put_wall ?? 0);
                RenderTarget.DrawText(dLevels, _smallFont,
                    new RectangleF(lx, ly, width - 24, lineH), _textBrush);
                ly += lineH - 2;
            }

            // separator
            ly += 4;
            RenderTarget.DrawLine(new Vector2(lx, ly), new Vector2(x + width - 12, ly),
                _accentBrush, 0.4f);
            ly += 4;

            // -- 4-REGIME GRID (2x2)
            if (p.regime != null)
            {
                DrawRegimeGrid(lx, ly, width - 24, p.regime);
                ly += 56;   // grid height
            }

            // separator
            ly += 4;
            RenderTarget.DrawLine(new Vector2(lx, ly), new Vector2(x + width - 12, ly),
                _accentBrush, 0.4f);
            ly += 4;

            // -- ALERTS (top 3)
            if (p.alerts != null && p.alerts.Count > 0)
            {
                RenderTarget.DrawText("ALERTS", _font,
                    new RectangleF(lx, ly, width - 24, lineH), _accentBrush);
                ly += lineH;

                foreach (var a in p.alerts.Take(3))
                {
                    var brush = a.severity == "CRITICAL" ? _alertCritBrush
                              : a.severity == "WARNING"  ? _alertWarnBrush
                              :                            _alertInfoBrush;
                    string alertLine = string.Format("{0} {1}",
                        a.icon ?? "·", a.msg ?? "");
                    if (alertLine.Length > 48)
                        alertLine = alertLine.Substring(0, 45) + "...";
                    RenderTarget.DrawText(alertLine, _smallFont,
                        new RectangleF(lx, ly, width - 24, lineH), brush);
                    ly += lineH - 2;
                }
            }
        }

        private void DrawRegimeGrid(float gx, float gy, float gw, EqRegimeQuad r)
        {
            float cellW = (gw - 4) / 2f;
            float cellH = 26f;

            DrawRegimeCell(gx,                gy,             cellW, cellH,
                "GAMMA", r.gamma_regime, r.gamma_label, BiasBrush(r.gamma_regime));
            DrawRegimeCell(gx + cellW + 4,   gy,             cellW, cellH,
                "VOL",   r.volatility_regime, r.vol_label,
                r.volatility_regime == "EXPANSION" ? _warnBrush : _textBrush);
            DrawRegimeCell(gx,                gy + cellH + 4, cellW, cellH,
                "TREND", r.trend_alignment, r.trend_label, BiasBrush(r.trend_alignment));
            DrawRegimeCell(gx + cellW + 4,   gy + cellH + 4, cellW, cellH,
                "BIAS",  r.institutional_bias.Replace("_", " "), r.bias_label,
                BiasBrush(r.institutional_bias));
        }

        private void DrawRegimeCell(float cx, float cy, float cw, float ch,
                                     string title, string value, string sub,
                                     SharpDX.Direct2D1.Brush valBrush)
        {
            var rect = new RectangleF(cx, cy, cw, ch);
            RenderTarget.DrawRectangle(rect, _accentBrush, 0.3f);
            RenderTarget.DrawText(title, _smallFont,
                new RectangleF(cx + 4, cy + 1, cw - 6, 11), _accentBrush);
            RenderTarget.DrawText(value ?? "—", _font,
                new RectangleF(cx + 4, cy + 11, cw - 6, 14), valBrush);
        }

        private SharpDX.Direct2D1.Brush BiasBrush(string b)
        {
            switch ((b ?? "").ToUpperInvariant())
            {
                case "POSITIVE":
                case "BULLISH":
                case "DEFEND_DISCOUNT":
                case "FOLLOW_MOMENTUM":
                    return _bullBrush;
                case "NEGATIVE":
                case "BEARISH":
                case "FADE_PREMIUM":
                case "CAUTION":
                    return _bearBrush;
                default:
                    return _neutralBrush;
            }
        }

        // -----------------------------------------------------------------------------
        //  Render target lifecycle
        // -----------------------------------------------------------------------------
        public override void OnRenderTargetChanged()
        {
            DisposeRenderResources();
            if (RenderTarget == null) return;

            _bgBrush       = new SolidColorBrush(RenderTarget, new Color4(0.07f, 0.07f, 0.11f, 0.94f));
            _textBrush     = new SolidColorBrush(RenderTarget, new Color4(0.88f, 0.88f, 0.90f, 1f));
            _accentBrush   = new SolidColorBrush(RenderTarget, new Color4(0.95f, 0.80f, 0.20f, 1f));
            _bullBrush     = new SolidColorBrush(RenderTarget, new Color4(0.30f, 0.95f, 0.40f, 1f));
            _bearBrush     = new SolidColorBrush(RenderTarget, new Color4(0.95f, 0.30f, 0.30f, 1f));
            _neutralBrush  = new SolidColorBrush(RenderTarget, new Color4(0.70f, 0.70f, 0.70f, 1f));
            _warnBrush     = new SolidColorBrush(RenderTarget, new Color4(0.95f, 0.65f, 0.20f, 1f));
            _premBgBrush   = new SolidColorBrush(RenderTarget, new Color4(0.65f, 0.20f, 0.20f, 0.25f));
            _discBgBrush   = new SolidColorBrush(RenderTarget, new Color4(0.20f, 0.65f, 0.30f, 0.25f));
            _sfvBrush      = new SolidColorBrush(RenderTarget, new Color4(0.95f, 0.85f, 0.10f, 1f));
            _alertCritBrush= new SolidColorBrush(RenderTarget, new Color4(0.98f, 0.35f, 0.35f, 1f));
            _alertWarnBrush= new SolidColorBrush(RenderTarget, new Color4(0.95f, 0.75f, 0.25f, 1f));
            _alertInfoBrush= new SolidColorBrush(RenderTarget, new Color4(0.65f, 0.78f, 0.95f, 1f));

            var factory   = Core.Globals.DirectWriteFactory;
            _font         = new TextFormat(factory, "Consolas", FontWeight.Normal, FontStyle.Normal, 12f);
            _bigFont      = new TextFormat(factory, "Consolas", FontWeight.Bold,   FontStyle.Normal, 13f);
            _smallFont    = new TextFormat(factory, "Consolas", FontWeight.Normal, FontStyle.Normal, 10f);
            _hugeFont     = new TextFormat(factory, "Consolas", FontWeight.Bold,   FontStyle.Normal, 16f);
        }

        private void EnsureRenderResources()
        {
            if (_font == null && RenderTarget != null) OnRenderTargetChanged();
        }

        private void DisposeRenderResources()
        {
            _bgBrush?.Dispose();         _bgBrush = null;
            _textBrush?.Dispose();       _textBrush = null;
            _accentBrush?.Dispose();     _accentBrush = null;
            _bullBrush?.Dispose();       _bullBrush = null;
            _bearBrush?.Dispose();       _bearBrush = null;
            _neutralBrush?.Dispose();    _neutralBrush = null;
            _warnBrush?.Dispose();       _warnBrush = null;
            _premBgBrush?.Dispose();     _premBgBrush = null;
            _discBgBrush?.Dispose();     _discBgBrush = null;
            _sfvBrush?.Dispose();        _sfvBrush = null;
            _alertCritBrush?.Dispose();  _alertCritBrush = null;
            _alertWarnBrush?.Dispose();  _alertWarnBrush = null;
            _alertInfoBrush?.Dispose();  _alertInfoBrush = null;
            _font?.Dispose();            _font = null;
            _bigFont?.Dispose();         _bigFont = null;
            _smallFont?.Dispose();       _smallFont = null;
            _hugeFont?.Dispose();        _hugeFont = null;
        }
    }
}

