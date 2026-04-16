// DEEP6 GEX Levels — standalone NinjaTrader 8 indicator.
//
// Displays gamma-exposure levels from massive.com on any NQ chart.
// This indicator is extracted from DEEP6Footprint.cs so GEX can be used
// independently on any chart type (not just footprint).
//
// Install: copy to
//   %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\DEEP6GexLevels.cs
// then F5 in the NinjaScript Editor.

#region Using
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
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

namespace NinjaTrader.NinjaScript.AddOns.DEEP6
{
    // ─── GEX types (public, not nested, so DEEP6Footprint.cs can also use them) ───

    public enum GexLevelKind
    {
        GammaFlip,
        CallWall,
        PutWall,
        MajorPositive,
        MajorNegative,
    }

    public sealed class GexLevel
    {
        public double Strike;
        public double GexNotional;   // signed $ per 1% move
        public GexLevelKind Kind;
        public string Label;
    }

    public sealed class GexProfile
    {
        public string Underlying;
        public double Spot;
        public double GammaFlip;
        public double CallWall;
        public double PutWall;
        public List<GexLevel> Levels = new List<GexLevel>();
        public DateTime FetchedUtc;

        public static GexProfile FromChain(string underlying, double spot, Dictionary<double, double> byStrike)
        {
            var profile = new GexProfile { Underlying = underlying, Spot = spot, FetchedUtc = DateTime.UtcNow };
            var sorted = byStrike.OrderBy(kv => kv.Key).ToList();

            // gamma flip = cumulative GEX zero-crossing (ascending strikes)
            double cum = 0.0;
            double flip = spot;
            bool found = false;
            foreach (var kv in sorted)
            {
                double prev = cum;
                cum += kv.Value;
                if (!found && ((prev <= 0 && cum > 0) || (prev >= 0 && cum < 0)))
                {
                    flip = kv.Key;
                    found = true;
                }
            }
            profile.GammaFlip = flip;

            double callWallStrike = spot, callWallVal = double.NegativeInfinity;
            double putWallStrike  = spot, putWallVal  = double.PositiveInfinity;
            foreach (var kv in sorted)
            {
                if (kv.Value > callWallVal) { callWallVal = kv.Value; callWallStrike = kv.Key; }
                if (kv.Value < putWallVal)  { putWallVal  = kv.Value; putWallStrike  = kv.Key; }
            }
            profile.CallWall = callWallStrike;
            profile.PutWall  = putWallStrike;

            // top 8 absolute GEX nodes as major positive / major negative
            var nodes = sorted
                .OrderByDescending(kv => System.Math.Abs(kv.Value))
                .Take(8)
                .ToList();
            foreach (var kv in nodes)
            {
                GexLevelKind kind;
                if (System.Math.Abs(kv.Key - flip) < 1e-6) kind = GexLevelKind.GammaFlip;
                else if (System.Math.Abs(kv.Key - callWallStrike) < 1e-6) kind = GexLevelKind.CallWall;
                else if (System.Math.Abs(kv.Key - putWallStrike) < 1e-6) kind = GexLevelKind.PutWall;
                else if (kv.Value > 0) kind = GexLevelKind.MajorPositive;
                else kind = GexLevelKind.MajorNegative;

                profile.Levels.Add(new GexLevel
                {
                    Strike = kv.Key,
                    GexNotional = kv.Value,
                    Kind = kind,
                    Label = string.Format("{0} {1:F0}", KindLabel(kind), kv.Key),
                });
            }
            return profile;
        }

        private static string KindLabel(GexLevelKind k)
        {
            switch (k)
            {
                case GexLevelKind.GammaFlip:     return "FLIP";
                case GexLevelKind.CallWall:       return "CALL WALL";
                case GexLevelKind.PutWall:        return "PUT WALL";
                case GexLevelKind.MajorPositive:  return "+GEX";
                case GexLevelKind.MajorNegative:  return "-GEX";
                default:                          return "GEX";
            }
        }
    }

    public sealed class MassiveGexClient : IDisposable
    {
        private readonly HttpClient _http;
        private readonly string _apiKey;
        private readonly string _baseUrl;

        public MassiveGexClient(string apiKey, string baseUrl = "https://api.massive.com")
        {
            _apiKey = apiKey ?? throw new ArgumentNullException("apiKey");
            _baseUrl = baseUrl.TrimEnd('/');

            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            // Raise connection limit so paginated fetches don't serialize on .NET's default of 2 per host.
            if (ServicePointManager.DefaultConnectionLimit < 8)
                ServicePointManager.DefaultConnectionLimit = 8;
            // NOTE: If massive.com ever returns 401 with query-param auth, swap to DefaultRequestHeaders.Authorization Bearer.
            // Python ref (deep6/engines/gex.py) confirms query-param is correct as of 2026-04-15.
            _http = new HttpClient
            {
                BaseAddress = new Uri(_baseUrl),
                Timeout = TimeSpan.FromSeconds(30),
            };
            _http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            _http.DefaultRequestHeaders.UserAgent.ParseAdd("DEEP6-NT8/1.0");
        }

        // Aggregates chain gamma × OI × 100 × spot² × 0.01 × sign(call=+1, put=-1) per strike.
        // Throws on HTTP/parse failure with a descriptive message — caller catches and Prints.
        public async Task<GexProfile> FetchAsync(string underlying, CancellationToken ct = default(CancellationToken))
        {
            var byStrike = new Dictionary<double, double>();
            double spot = 0;
            int contractsParsed = 0;
            // First-page URL carries apiKey as query param (Polygon-compatible; matches deep6/engines/gex.py ref).
            // Pagination: next_url returned by the API already embeds apiKey — do NOT re-append.
            string url = string.Format("/v3/snapshot/options/{0}?limit=250&apiKey={1}", underlying, Uri.EscapeDataString(_apiKey));
            int safetyPages = 0;

            while (!string.IsNullOrEmpty(url) && safetyPages < 20)
            {
                safetyPages++;
                var req = new HttpRequestMessage(HttpMethod.Get, url);
                var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
                if (!resp.IsSuccessStatusCode)
                {
                    string body = string.Empty;
                    try { body = await resp.Content.ReadAsStringAsync().ConfigureAwait(false); } catch { }
                    if (body.Length > 200) body = body.Substring(0, 200);
                    throw new HttpRequestException(string.Format("HTTP {0} {1} for {2}. Body: {3}",
                        (int)resp.StatusCode, resp.StatusCode, url, body));
                }
                var json = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);

                string nextUrl = ExtractStringField(json, "next_url");
                foreach (var obj in ExtractResultObjects(json))
                {
                    int openInterest = ExtractIntField(obj, "open_interest");
                    if (openInterest <= 0) continue;
                    double gamma = ExtractDoubleField(obj, "gamma");
                    if (gamma == 0) continue;
                    double strike = ExtractDoubleField(obj, "strike_price");
                    if (strike == 0) continue;
                    string ctype = ExtractStringField(obj, "contract_type");
                    if (string.IsNullOrEmpty(ctype)) continue;
                    double localSpot = ExtractDoubleFieldInside(obj, "underlying_asset", "price");
                    if (localSpot > 0) spot = localSpot;
                    double sign = string.Equals(ctype, "call", StringComparison.OrdinalIgnoreCase) ? +1.0 : -1.0;
                    double gex = gamma * openInterest * 100.0 * spot * spot * 0.01 * sign;
                    double acc;
                    byStrike.TryGetValue(strike, out acc);
                    byStrike[strike] = acc + gex;
                    contractsParsed++;
                }
                url = nextUrl;
                if (!string.IsNullOrEmpty(url) && url.StartsWith(_baseUrl)) url = url.Substring(_baseUrl.Length);
            }

            if (spot == 0 || byStrike.Count == 0)
                throw new InvalidOperationException(string.Format(
                    "Parsed {0} contracts but spot={1}, strikes={2}. Likely API returned empty results array — verify symbol '{3}' and that your massive.com plan covers options chain snapshots.",
                    contractsParsed, spot, byStrike.Count, underlying));
            return GexProfile.FromChain(underlying, spot, byStrike);
        }

        public void Dispose() { _http.Dispose(); }

        // ---- Minimal JSON field extraction (no System.Runtime.Serialization dependency) ----

        private static IEnumerable<string> ExtractResultObjects(string json)
        {
            // Locate "results": [...] and yield each top-level object in that array.
            int arrIdx = json.IndexOf("\"results\"");
            if (arrIdx < 0) yield break;
            int arrStart = json.IndexOf('[', arrIdx);
            if (arrStart < 0) yield break;

            int i = arrStart + 1;
            int n = json.Length;
            while (i < n)
            {
                // Skip whitespace and commas
                while (i < n && (json[i] == ' ' || json[i] == '\t' || json[i] == '\n' || json[i] == '\r' || json[i] == ',')) i++;
                if (i >= n) break;
                if (json[i] == ']') yield break;
                if (json[i] != '{') { i++; continue; }

                int start = i;
                int depth = 0;
                bool inStr = false;
                bool esc = false;
                for (; i < n; i++)
                {
                    char c = json[i];
                    if (esc) { esc = false; continue; }
                    if (inStr)
                    {
                        if (c == '\\') esc = true;
                        else if (c == '"') inStr = false;
                        continue;
                    }
                    if (c == '"') { inStr = true; continue; }
                    if (c == '{') depth++;
                    else if (c == '}')
                    {
                        depth--;
                        if (depth == 0) { i++; break; }
                    }
                }
                yield return json.Substring(start, i - start);
            }
        }

        private static string ExtractStringField(string json, string field)
        {
            var m = Regex.Match(json, "\"" + Regex.Escape(field) + "\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"");
            return m.Success ? Regex.Unescape(m.Groups[1].Value) : string.Empty;
        }

        private static int ExtractIntField(string json, string field)
        {
            var m = Regex.Match(json, "\"" + Regex.Escape(field) + "\"\\s*:\\s*(-?\\d+)");
            if (!m.Success) return 0;
            int v;
            return int.TryParse(m.Groups[1].Value, System.Globalization.NumberStyles.Integer,
                System.Globalization.CultureInfo.InvariantCulture, out v) ? v : 0;
        }

        private static double ExtractDoubleField(string json, string field)
        {
            var m = Regex.Match(json, "\"" + Regex.Escape(field) + "\"\\s*:\\s*(-?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?)");
            if (!m.Success) return 0.0;
            double v;
            return double.TryParse(m.Groups[1].Value, System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out v) ? v : 0.0;
        }

        // Extract a double from a named sub-object: {"outer": {"inner": 123.45}}
        private static double ExtractDoubleFieldInside(string json, string outer, string inner)
        {
            var m = Regex.Match(json, "\"" + Regex.Escape(outer) + "\"\\s*:\\s*\\{([^{}]*)\\}");
            return m.Success ? ExtractDoubleField(m.Groups[1].Value, inner) : 0.0;
        }
    }
}

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    using NinjaTrader.NinjaScript.AddOns.DEEP6;

    public class DEEP6GexLevels : Indicator
    {
        #region Fields

        // GEX fetch state
        private MassiveGexClient _gexClient;
        private volatile GexProfile _gexProfile;
        private readonly TimeSpan _gexInterval = TimeSpan.FromMinutes(2);
        private CancellationTokenSource _gexCts;
        // Background timer drives GEX fetches independently of tape activity.
        private System.Threading.Timer _gexTimer;
        private int _gexFailCount;
        private DateTime _gexLastSuccess = DateTime.MinValue;
        // Sticky status — never cleared on failure.
        private volatile string _gexLastSuccessStatus = "GEX: idle (no key)";
        // Transient status — set during retry, cleared on success.
        private volatile string _gexRetryStatus = string.Empty;
        private readonly object _gexTimerLock = new object();

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

        #endregion

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description                  = "Gamma exposure levels from massive.com overlaid on NQ via underlying spot ratio.";
                Name                         = "DEEP6 GEX Levels";
                Calculate                    = Calculate.OnEachTick;
                IsOverlay                    = true;
                DrawOnPricePanel             = true;
                PaintPriceMarkers            = false;
                ScaleJustification           = ScaleJustification.Right;
                IsSuspendedWhileInactive     = true;

                ShowGexLevels                = true;
                GexUnderlying               = "QQQ";
                GexApiKey                   = string.Empty;

                GexFlipBrush      = Brushes.Yellow;
                GexCallWallBrush  = Brushes.LimeGreen;
                GexPutWallBrush   = Brushes.OrangeRed;
                GexPositiveBrush  = MakeFrozenBrush(Color.FromArgb(180, 0, 180, 120));
                GexNegativeBrush  = MakeFrozenBrush(Color.FromArgb(180, 200, 70, 70));
            }
            else if (State == State.DataLoaded)
            {
                if (!ShowGexLevels)
                {
                    _gexLastSuccessStatus = "GEX: disabled";
                    _gexRetryStatus = string.Empty;
                }
                else if (string.IsNullOrWhiteSpace(GexApiKey))
                {
                    _gexLastSuccessStatus = "GEX: NO API KEY (set in indicator properties)";
                    _gexRetryStatus = string.Empty;
                    Print("[DEEP6 GEX] Disabled — set massive.com API key in indicator properties.");
                }
                else
                {
                    _gexClient = new MassiveGexClient(GexApiKey);
                    _gexCts = new CancellationTokenSource();
                    _gexFailCount = 0;
                    _gexLastSuccessStatus = "GEX: initializing — first fetch in progress";
                    _gexRetryStatus = string.Empty;
                    Print("[DEEP6 GEX] Client initialized. Fetching " + GexUnderlying + " chain from massive.com…");
                    _gexTimer = new System.Threading.Timer(GexTimerTick, null, TimeSpan.Zero, System.Threading.Timeout.InfiniteTimeSpan);
                }
            }
            else if (State == State.Terminated)
            {
                if (_gexTimer != null) { try { _gexTimer.Dispose(); } catch { } _gexTimer = null; }
                if (_gexCts != null) { try { _gexCts.Cancel(); } catch { } }
                if (_gexClient != null) { _gexClient.Dispose(); _gexClient = null; }
                DisposeDx();
            }
        }

        #region Timer callbacks

        private void GexTimerTick(object state)
        {
            if (!System.Threading.Monitor.TryEnter(_gexTimerLock)) return;
            try
            {
                var client = _gexClient;
                if (client == null) return;
                var ctsTok = _gexCts == null ? CancellationToken.None : _gexCts.Token;
                if (ctsTok.IsCancellationRequested) return;
                var underlying = GexUnderlying;

                _gexRetryStatus = "fetching " + underlying + "…";
                Print("[DEEP6 GEX] Fetch start: " + underlying + " @ " + DateTime.Now.ToString("HH:mm:ss"));

                try
                {
                    var profile = client.FetchAsync(underlying, ctsTok).GetAwaiter().GetResult();
                    if (profile != null && profile.Levels.Count > 0)
                        OnGexFetchSuccess(profile);
                    else
                        OnGexFetchFailure(new InvalidOperationException("empty response (check API key, plan, underlying)"));
                }
                catch (OperationCanceledException) { /* shutdown — stay silent */ }
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
            _gexLastSuccess = DateTime.UtcNow;
            _gexFailCount = 0;
            _gexLastSuccessStatus = "GEX: " + profile.Levels.Count + " levels @ " + DateTime.Now.ToString("HH:mm");
            _gexRetryStatus = string.Empty;
            Print("[DEEP6 GEX] OK: " + profile.Levels.Count + " levels, spot " + profile.Spot.ToString("F2") + ", flip " + profile.GammaFlip.ToString("F2"));
        }

        private void OnGexFetchFailure(Exception ex)
        {
            _gexFailCount++;
            var delay = ComputeGexRetryDelay(_gexFailCount);
            _gexRetryStatus = "retry in " + ((int)delay.TotalSeconds) + "s after " + ex.GetType().Name;
            Print("[DEEP6 GEX] EXCEPTION (#" + _gexFailCount + "): " + ex.GetType().Name + " — " + ex.Message + ". Retrying in " + (int)delay.TotalSeconds + "s.");
        }

        // 5s → 15s → 60s → 120s (cap = _gexInterval).
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
                var next = _gexFailCount == 0 ? _gexInterval : ComputeGexRetryDelay(_gexFailCount);
                _gexTimer.Change(next, System.Threading.Timeout.InfiniteTimeSpan);
            }
            catch (ObjectDisposedException) { /* shutting down */ }
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
            if (_labelFont != null) { _labelFont.Dispose(); _labelFont = null; }
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

            // GEX status badge (top-right corner)
            {
                string status = _gexStatus ?? string.Empty;
                if (!string.IsNullOrEmpty(status))
                {
                    SharpDX.Direct2D1.Brush statusBrush;
                    if (status.IndexOf("ERROR", StringComparison.Ordinal) >= 0 ||
                        status.IndexOf("NO API KEY", StringComparison.Ordinal) >= 0 ||
                        status.IndexOf("empty", StringComparison.Ordinal) >= 0)
                        statusBrush = _gexPutWallDx ?? _textDx;
                    else if (status.IndexOf("levels", StringComparison.Ordinal) >= 0)
                        statusBrush = _gexCallWallDx ?? _textDx;
                    else
                        statusBrush = _textDx;

                    if (statusBrush != null)
                    {
                        using (var statusLayout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                                                  status, _labelFont, 380f, 18f))
                        {
                            RenderTarget.DrawTextLayout(
                                new Vector2(panelRight - 384, (float)ChartPanel.Y + 4),
                                statusLayout, statusBrush);
                        }
                    }
                }
            }

            // GEX horizontal levels
            if (ShowGexLevels && _gexProfile != null)
                RenderGexLevels(_gexProfile, chartControl, chartScale, panelRight);
        }

        private void RenderGexLevels(GexProfile gex, ChartControl cc, ChartScale cs, float panelRight)
        {
            // GEX strikes are in the underlying's price space (QQQ),
            // but our chart is NQ. Map QQQ → NQ via a simple multiplier inferred
            // from spot ratio. This is a rough visual overlay, not a tradeable level.
            double nqSpot = (Bars != null && Bars.Count > 0) ? Bars.GetClose(Bars.Count - 1) : 0;
            double qqqSpot = gex.Spot;
            if (nqSpot <= 0 || qqqSpot <= 0) return;
            double mult = nqSpot / qqqSpot;

            double minVis = cs.MinValue;
            double maxVis = cs.MaxValue;

            foreach (var lv in gex.Levels)
            {
                double mapped = lv.Strike * mult;
                if (mapped < minVis || mapped > maxVis) continue;

                SharpDX.Direct2D1.Brush brush;
                float width;
                switch (lv.Kind)
                {
                    case GexLevelKind.GammaFlip:     brush = _gexFlipDx;     width = 2.0f; break;
                    case GexLevelKind.CallWall:       brush = _gexCallWallDx; width = 1.8f; break;
                    case GexLevelKind.PutWall:        brush = _gexPutWallDx;  width = 1.8f; break;
                    case GexLevelKind.MajorPositive:  brush = _gexPosDx;      width = 0.8f; break;
                    default:                          brush = _gexNegDx;      width = 0.8f; break;
                }
                if (brush == null) continue;

                float y = cs.GetYByValue(mapped);
                RenderTarget.DrawLine(new Vector2((float)ChartPanel.X, y),
                                      new Vector2(panelRight, y), brush, width);

                string label = string.Format("{0} ({1:F2})", lv.Label, mapped);
                using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, label, _labelFont, 156, 16))
                {
                    RenderTarget.DrawTextLayout(new Vector2(panelRight - 160, y - 8), layout, brush);
                }
            }
        }

        #endregion

        // Handles chart click — show GEX detail for hit level.
        protected override void OnChartPanelMouseDown(ChartControl chartControl, ChartPanel chartPanel,
                                                        ChartScale chartScale, ChartAnchor dataPoint)
        {
            if (!ShowGexLevels || _gexProfile == null) return;

            double nqSpot = (Bars != null && Bars.Count > 0) ? Bars.GetClose(Bars.Count - 1) : 0;
            double qqqSpot = _gexProfile.Spot;
            if (nqSpot <= 0 || qqqSpot <= 0) return;
            double mult = nqSpot / qqqSpot;

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
        [Display(Name = "Show GEX Levels", Order = 20, GroupName = "3. GEX (massive.com)")]
        public bool ShowGexLevels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "GEX Underlying (QQQ/NDX)", Order = 21, GroupName = "3. GEX (massive.com)")]
        public string GexUnderlying { get; set; }

        [NinjaScriptProperty]
        [PasswordPropertyText(true)]
        [Display(Name = "massive.com API Key", Order = 22, GroupName = "3. GEX (massive.com)")]
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
        private DEEP6.DEEP6GexLevels[] cacheDEEP6GexLevels;
        public DEEP6.DEEP6GexLevels DEEP6GexLevels(bool showGexLevels, string gexUnderlying, string gexApiKey)
        {
            return DEEP6GexLevels(Input, showGexLevels, gexUnderlying, gexApiKey);
        }

        public DEEP6.DEEP6GexLevels DEEP6GexLevels(ISeries<double> input, bool showGexLevels, string gexUnderlying, string gexApiKey)
        {
            if (cacheDEEP6GexLevels != null)
                for (int idx = 0; idx < cacheDEEP6GexLevels.Length; idx++)
                    if (cacheDEEP6GexLevels[idx] != null && cacheDEEP6GexLevels[idx].ShowGexLevels == showGexLevels && cacheDEEP6GexLevels[idx].GexUnderlying == gexUnderlying && cacheDEEP6GexLevels[idx].GexApiKey == gexApiKey && cacheDEEP6GexLevels[idx].EqualsInput(input))
                        return cacheDEEP6GexLevels[idx];
            return CacheIndicator<DEEP6.DEEP6GexLevels>(new DEEP6.DEEP6GexLevels() { ShowGexLevels = showGexLevels, GexUnderlying = gexUnderlying, GexApiKey = gexApiKey }, input, ref cacheDEEP6GexLevels);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6.DEEP6GexLevels DEEP6GexLevels(bool showGexLevels, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6GexLevels(Input, showGexLevels, gexUnderlying, gexApiKey);
        }

        public Indicators.DEEP6.DEEP6GexLevels DEEP6GexLevels(ISeries<double> input, bool showGexLevels, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6GexLevels(input, showGexLevels, gexUnderlying, gexApiKey);
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.DEEP6.DEEP6GexLevels DEEP6GexLevels(bool showGexLevels, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6GexLevels(Input, showGexLevels, gexUnderlying, gexApiKey);
        }

        public Indicators.DEEP6.DEEP6GexLevels DEEP6GexLevels(ISeries<double> input, bool showGexLevels, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6GexLevels(input, showGexLevels, gexUnderlying, gexApiKey);
        }
    }
}
#endregion
