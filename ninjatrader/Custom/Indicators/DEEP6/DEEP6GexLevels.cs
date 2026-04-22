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

            // Gamma flip: interpolated zero-crossing of per-strike net GEX (matches Python gex.py).
            // Walks sorted strikes; when adjacent values change sign, interpolates the exact price.
            double flip = spot;
            bool found = false;
            for (int i = 0; i < sorted.Count - 1; i++)
            {
                double g1 = sorted[i].Value, g2 = sorted[i + 1].Value;
                if (g1 * g2 < 0)
                {
                    double s1 = sorted[i].Key, s2 = sorted[i + 1].Key;
                    flip = s1 + (s2 - s1) * System.Math.Abs(g1) / (System.Math.Abs(g1) + System.Math.Abs(g2));
                    found = true;
                    break;
                }
            }
            if (!found) flip = spot;
            profile.GammaFlip = flip;

            // R1 Call Wall = largest positive GEX strike AT OR ABOVE spot (resistance above price).
            // S1 Put Wall  = largest magnitude negative GEX strike AT OR BELOW spot (support below price).
            // Filtering to above/below ensures walls are structurally meaningful relative to current price.
            double callWallStrike = spot, callWallVal = double.NegativeInfinity;
            double putWallStrike  = spot, putWallVal  = double.PositiveInfinity;
            foreach (var kv in sorted)
            {
                if (kv.Key >= spot && kv.Value > callWallVal) { callWallVal = kv.Value; callWallStrike = kv.Key; }
                if (kv.Key <= spot && kv.Value < putWallVal)  { putWallVal  = kv.Value; putWallStrike  = kv.Key; }
            }
            profile.CallWall = callWallStrike;
            profile.PutWall  = putWallStrike;

            // Always render GammaFlip, CallWall, PutWall regardless of GEX magnitude.
            // The flip is a zero-crossing (low GEX value) and would otherwise be absent from the top-8 list.
            var pinnedStrikes = new System.Collections.Generic.HashSet<double>();

            profile.Levels.Add(new GexLevel { Strike = flip, GexNotional = 0, Kind = GexLevelKind.GammaFlip,
                Label = string.Format("FLIP {0:F0}", flip) });
            pinnedStrikes.Add(flip);

            if (callWallVal > double.NegativeInfinity && System.Math.Abs(callWallStrike - flip) > 1e-4)
            {
                profile.Levels.Add(new GexLevel { Strike = callWallStrike, GexNotional = callWallVal,
                    Kind = GexLevelKind.CallWall, Label = string.Format("SELL WALL {0:F0}", callWallStrike) });
                pinnedStrikes.Add(callWallStrike);
            }
            if (putWallVal < double.PositiveInfinity && System.Math.Abs(putWallStrike - flip) > 1e-4
                && System.Math.Abs(putWallStrike - callWallStrike) > 1e-4)
            {
                profile.Levels.Add(new GexLevel { Strike = putWallStrike, GexNotional = putWallVal,
                    Kind = GexLevelKind.PutWall, Label = string.Format("BUY WALL {0:F0}", putWallStrike) });
                pinnedStrikes.Add(putWallStrike);
            }

            // Fill remaining slots (up to 5) with highest absolute GEX nodes not already pinned.
            var nodes = sorted
                .Where(kv => !pinnedStrikes.Contains(kv.Key))
                .OrderByDescending(kv => System.Math.Abs(kv.Value))
                .Take(5)
                .ToList();
            foreach (var kv in nodes)
            {
                GexLevelKind kind = kv.Value > 0 ? GexLevelKind.MajorPositive : GexLevelKind.MajorNegative;
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
                case GexLevelKind.CallWall:       return "SELL WALL";
                case GexLevelKind.PutWall:        return "BUY WALL";
                case GexLevelKind.MajorPositive:  return "+GEX";
                case GexLevelKind.MajorNegative:  return "-GEX";
                default:                          return "GEX";
            }
        }
    }

    public sealed class MassiveGexClient : IDisposable
    {
        private readonly string _apiKey;
        private readonly string _baseUrl;

        public MassiveGexClient(string apiKey, string baseUrl = "https://api.massive.com")
        {
            _apiKey = apiKey ?? throw new ArgumentNullException("apiKey");
            _baseUrl = baseUrl.TrimEnd('/');
            // Force TLS 1.2 — required by api.massive.com. Set explicitly (not |=) to override any NT8 defaults.
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12 | SecurityProtocolType.Tls11 | SecurityProtocolType.Tls;
            if (ServicePointManager.DefaultConnectionLimit < 8)
                ServicePointManager.DefaultConnectionLimit = 8;
        }

        // Aggregates chain gamma × OI × 100 × spot² × 0.01 × sign(call=+1, put=-1) per strike.
        // Synchronous HttpWebRequest — avoids HttpClient async/TLS issues in NT8's .NET Framework 4.8.
        // Called from Timer thread (no SynchronizationContext) so blocking is safe.
        public GexProfile Fetch(string underlying, CancellationToken ct, double spot = 0)
        {
            var byStrike = new Dictionary<double, double>();
            int contractsParsed = 0;
            string strikeFilter = string.Empty;
            if (spot > 0)
                strikeFilter = string.Format("&strike_price.gte={0:F2}&strike_price.lte={1:F2}",
                    spot * 0.94, spot * 1.06);
            string today = DateTime.UtcNow.ToString("yyyy-MM-dd");
            string expMax = DateTime.UtcNow.AddDays(21).ToString("yyyy-MM-dd");
            string dteFilter = string.Format("&expiration_date.gte={0}&expiration_date.lte={1}", today, expMax);
            // apiKey in query param — Polygon-compatible; confirmed correct for massive.com as of 2026-04-15.
            string url = string.Format("{0}/v3/snapshot/options/{1}?limit=250&apiKey={2}{3}{4}",
                _baseUrl, underlying, Uri.EscapeDataString(_apiKey), strikeFilter, dteFilter);
            int safetyPages = 0;

            while (!string.IsNullOrEmpty(url) && safetyPages < 20)
            {
                ct.ThrowIfCancellationRequested();
                safetyPages++;

                var req = (HttpWebRequest)WebRequest.Create(url);
                req.Method = "GET";
                req.Accept = "application/json";
                req.UserAgent = "DEEP6-NT8/1.0";
                req.Timeout = 30000;
                req.KeepAlive = false;

                string json;
                try
                {
                    using (var resp = (HttpWebResponse)req.GetResponse())
                    using (var reader = new StreamReader(resp.GetResponseStream()))
                        json = reader.ReadToEnd();
                }
                catch (WebException wex)
                {
                    // 4xx/5xx: read body for diagnostics, then rethrow with details.
                    if (wex.Response is HttpWebResponse errResp)
                    {
                        string body = string.Empty;
                        try { using (var r = new StreamReader(errResp.GetResponseStream())) body = r.ReadToEnd(); } catch { }
                        if (body.Length > 300) body = body.Substring(0, 300);
                        throw new Exception(string.Format("HTTP {0} {1} — {2}", (int)errResp.StatusCode, errResp.StatusCode, body));
                    }
                    throw; // network/DNS/TLS error — original WebException message is descriptive
                }

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
            }

            if (spot == 0 || byStrike.Count == 0)
                throw new InvalidOperationException(string.Format(
                    "Parsed {0} contracts but spot={1}, strikes={2}. Verify symbol '{3}' and that your massive.com plan covers options chain snapshots.",
                    contractsParsed, spot, byStrike.Count, underlying));
            return GexProfile.FromChain(underlying, spot, byStrike);
        }

        public void Dispose() { }

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
        private TimeSpan _gexInterval;
        private CancellationTokenSource _gexCts;
        // Background timer drives GEX fetches independently of tape activity.
        private System.Threading.Timer _gexTimer;
        private int _gexFailCount;
        // Price-drift trigger: re-fetch immediately when NQ moves more than PriceDriftPoints.
        private double _nqSpotAtLastFetch;
        private DateTime _driftFetchCooldown = DateTime.MinValue;  // minimum 10s between drift-triggered fetches
        // Sticky status — never cleared on failure.
        private volatile string _gexLastSuccessStatus = "GEX: idle (no key)";
        // Transient status — set during retry, cleared on success.
        private volatile string _gexRetryStatus = string.Empty;
        private readonly object _gexTimerLock = new object();

        // TextLayout cache — rebuilt on fetch, disposed on render-target change.
        // Eliminates 480 COM allocations/sec from the render loop.
        private Dictionary<string, TextLayout> _pillCache = new Dictionary<string, TextLayout>();
        private string _statusCacheKey;
        private TextLayout _statusCacheLayout;
        // Stale overlay brush (amber — allocated alongside other DX brushes)
        private SharpDX.Direct2D1.Brush _pwStaleDx;

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

        // F1 PITWALL — telemetry-pill brushes for level labels (Aesthetic Option E)
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
                Description                  = "Gamma exposure levels from massive.com overlaid on NQ. Use NDX for direct NQ parent index (NQ ≈ NDX × 20).";
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
                FetchIntervalSeconds        = 15;
                PriceDriftPoints            = 10;

                // F1 PITWALL — aerospace 787 PFD color grammar (Aesthetic Option E)
                //   cyan = selected/target  →  GammaFlip (zero-gamma point = primary target)
                //   amber = caution/safety  →  Call/Put walls (price-bound limits)
                //   minor levels: cyan (positive GEX) / magenta (negative GEX)
                GexFlipBrush      = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xE0, 0xFF));   // aero cyan  — zero-gamma regime line
                GexCallWallBrush  = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x3B, 0x30));   // bright red — SELL resistance (R1)
                GexPutWallBrush   = MakeFrozenBrush(Color.FromArgb(255, 0x30, 0xD1, 0x58));   // bright green — BUY support (S1)
                GexPositiveBrush  = MakeFrozenBrush(Color.FromArgb(140, 0x30, 0xD1, 0x58));   // dim green  — minor +GEX nodes
                GexNegativeBrush  = MakeFrozenBrush(Color.FromArgb(140, 0xFF, 0x3B, 0x30));   // dim red    — minor −GEX nodes
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
                    _gexInterval = TimeSpan.FromSeconds(System.Math.Max(15, FetchIntervalSeconds));
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

                // Pass the underlying's own spot from the previous successful fetch as
                // the strike-range hint. First fetch: no hint (0) → no filter → discovers spot.
                // Subsequent fetches: use known spot → ±15% filter → fast and targeted.
                double underlyingSpotHint = 0;
                var prevProfile = _gexProfile;
                if (prevProfile != null && prevProfile.Spot > 0)
                    underlyingSpotHint = prevProfile.Spot;

                try
                {
                    var profile = client.Fetch(underlying, ctsTok, underlyingSpotHint);
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
            _gexFailCount = 0;
            // Invalidate pill label cache — text will change (new prices mapped from new profile).
            if (_pillCache != null) { foreach (var kv in _pillCache) if (kv.Value != null) kv.Value.Dispose(); _pillCache.Clear(); }
            if (_statusCacheLayout != null) { _statusCacheLayout.Dispose(); _statusCacheLayout = null; }
            _statusCacheKey = null;
            // Record NQ price at fetch time so drift trigger can compare against it.
            try { if (Bars != null && Bars.Count > 0) _nqSpotAtLastFetch = Bars.GetClose(Bars.Count - 1); } catch { }
            _gexLastSuccessStatus = "GEX: " + profile.Levels.Count + " levels @ " + DateTime.Now.ToString("HH:mm:ss");
            _gexRetryStatus = string.Empty;
            Print("[DEEP6 GEX] OK: " + profile.Levels.Count + " levels, spot " + profile.Spot.ToString("F2") + ", flip " + profile.GammaFlip.ToString("F2"));
        }

        private void OnGexFetchFailure(Exception ex)
        {
            _gexFailCount++;
            var delay = ComputeGexRetryDelay(_gexFailCount);
            _gexRetryStatus = "retry in " + ((int)delay.TotalSeconds) + "s after " + ex.GetType().Name;
            string inner = ex.InnerException != null ? " | inner: " + ex.InnerException.Message : string.Empty;
            Print("[DEEP6 GEX] EXCEPTION (#" + _gexFailCount + "): " + ex.GetType().Name + " — " + ex.Message + inner + ". Retrying in " + (int)delay.TotalSeconds + "s.");
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
                // Pre-open ramp 9:15–9:30
                if (totalMin < 9 * 60 + 30)
                    return TimeSpan.FromSeconds(15);
                // RTH open surge 9:30–10:30 — highest gamma sensitivity
                if (totalMin < 10 * 60 + 30)
                    return TimeSpan.FromSeconds(5);
                // FOMC window 14:45–15:00
                if (totalMin >= 14 * 60 + 45 && totalMin < 15 * 60)
                    return TimeSpan.FromSeconds(10);
                // 0DTE gamma cliff 15:54–16:05
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
            // Price has drifted enough — kick the timer to fire immediately.
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

            // F1 PITWALL — telemetry-pill brushes
            _pwSurface2Dx   = MakeFrozenBrush(Color.FromArgb(230, 0x0E, 0x12, 0x18)).ToDxBrush(RenderTarget);
            _pwSellFillDx   = MakeFrozenBrush(Color.FromArgb(56,  0xFF, 0x3B, 0x30)).ToDxBrush(RenderTarget);  // red band
            _pwBuyFillDx    = MakeFrozenBrush(Color.FromArgb(56,  0x30, 0xD1, 0x58)).ToDxBrush(RenderTarget);  // green band
            _pwTextHaloDx   = MakeFrozenBrush(Color.FromArgb(230, 0x00, 0x00, 0x00)).ToDxBrush(RenderTarget);
            _pwWhiteTextDx  = MakeFrozenBrush(Color.FromArgb(255, 0xF2, 0xF4, 0xF8)).ToDxBrush(RenderTarget);
            _pwStaleDx      = MakeFrozenBrush(Color.FromArgb(200, 0xFF, 0xBF, 0x00)).ToDxBrush(RenderTarget); // amber — stale warning

            // Invalidate layout cache on device reset — layouts are device-dependent
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

            // Staleness — compute once per frame, used by both badge and level rendering
            var profile = _gexProfile;
            double staleSeconds = profile != null
                ? (DateTime.UtcNow - profile.FetchedUtc).TotalSeconds
                : double.MaxValue;
            bool isStale = staleSeconds > 120;   // >2 min = stale
            bool isVeryStale = staleSeconds > 600; // >10 min = very stale

            // GEX status badge (top-right corner) — cached TextLayout, rebuilt only when text changes
            {
                // Append stale age to status text when data is old
                string status = _gexStatus ?? string.Empty;
                if (isStale && profile != null)
                {
                    int ageSec = (int)staleSeconds;
                    status = status + (isVeryStale ? "  ⚠ STALE " : "  [") +
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

                    // Use cached TextLayout — only rebuild when text actually changes
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

            // GEX horizontal levels — pass stale flag so renderer can dim them
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
                        brush = _gexNegDx; width = 0.8f * staleWidthMult; shortLabel = "−GEX"; break;
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

                    // Cache pill TextLayout by text key — only ~8 unique strings, rebuilt on fetch
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

        // Handles chart click — show GEX detail for hit level.
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
        [Display(Name = "Show GEX Levels", Order = 20, GroupName = "3. GEX (massive.com)")]
        public bool ShowGexLevels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Fetch Interval (seconds, min 15)", Order = 21, GroupName = "3. GEX (massive.com)")]
        public int FetchIntervalSeconds { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Price Drift Re-fetch (NQ points, 0=off)", Order = 22, GroupName = "3. GEX (massive.com)")]
        public int PriceDriftPoints { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "GEX Underlying (QQQ/NDX)", Order = 23, GroupName = "3. GEX (massive.com)")]
        public string GexUnderlying { get; set; }

        [NinjaScriptProperty]
        [PasswordPropertyText(true)]
        [Display(Name = "massive.com API Key", Order = 24, GroupName = "3. GEX (massive.com)")]
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
        public DEEP6.DEEP6GexLevels DEEP6GexLevels(bool showGexLevels, int fetchIntervalSeconds, string gexUnderlying, string gexApiKey)
        {
            return DEEP6GexLevels(Input, showGexLevels, fetchIntervalSeconds, gexUnderlying, gexApiKey);
        }

        public DEEP6.DEEP6GexLevels DEEP6GexLevels(ISeries<double> input, bool showGexLevels, int fetchIntervalSeconds, string gexUnderlying, string gexApiKey)
        {
            if (cacheDEEP6GexLevels != null)
                for (int idx = 0; idx < cacheDEEP6GexLevels.Length; idx++)
                    if (cacheDEEP6GexLevels[idx] != null && cacheDEEP6GexLevels[idx].ShowGexLevels == showGexLevels && cacheDEEP6GexLevels[idx].FetchIntervalSeconds == fetchIntervalSeconds && cacheDEEP6GexLevels[idx].GexUnderlying == gexUnderlying && cacheDEEP6GexLevels[idx].GexApiKey == gexApiKey && cacheDEEP6GexLevels[idx].EqualsInput(input))
                        return cacheDEEP6GexLevels[idx];
            return CacheIndicator<DEEP6.DEEP6GexLevels>(new DEEP6.DEEP6GexLevels() { ShowGexLevels = showGexLevels, FetchIntervalSeconds = fetchIntervalSeconds, GexUnderlying = gexUnderlying, GexApiKey = gexApiKey }, input, ref cacheDEEP6GexLevels);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6.DEEP6GexLevels DEEP6GexLevels(bool showGexLevels, int fetchIntervalSeconds, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6GexLevels(Input, showGexLevels, fetchIntervalSeconds, gexUnderlying, gexApiKey);
        }

        public Indicators.DEEP6.DEEP6GexLevels DEEP6GexLevels(ISeries<double> input, bool showGexLevels, int fetchIntervalSeconds, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6GexLevels(input, showGexLevels, fetchIntervalSeconds, gexUnderlying, gexApiKey);
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.DEEP6.DEEP6GexLevels DEEP6GexLevels(bool showGexLevels, int fetchIntervalSeconds, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6GexLevels(Input, showGexLevels, fetchIntervalSeconds, gexUnderlying, gexApiKey);
        }

        public Indicators.DEEP6.DEEP6GexLevels DEEP6GexLevels(ISeries<double> input, bool showGexLevels, int fetchIntervalSeconds, string gexUnderlying, string gexApiKey)
        {
            return indicator.DEEP6GexLevels(input, showGexLevels, fetchIntervalSeconds, gexUnderlying, gexApiKey);
        }
    }
}
#endregion
