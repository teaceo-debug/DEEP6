#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
using System.Net;
using System.Threading;

using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

// NT8 rule: enums used as NinjaScriptProperty types MUST be at global scope (no namespace wrapper).
public enum GexDataProvider { Massive, FlashAlpha }

namespace NinjaTrader.NinjaScript.Indicators
{
    public class GEXGammaOverlay : Indicator
    {
        #region Settings

        [NinjaScriptProperty]
        [Display(Name="Data Provider", Description="Massive=raw options chain (Advanced plan $199/mo). FlashAlpha=pre-computed GEX ($49/mo, free tier available).", Order=1, GroupName="1. API")]
        public GexDataProvider DataProvider { get; set; }

        [NinjaScriptProperty]
        [Display(Name="API Key", Description="Massive.com OR FlashAlpha API key (matches Data Provider selection)", Order=2, GroupName="1. API")]
        public string ApiKey { get; set; }

        [NinjaScriptProperty]
        [Display(Name="ETF Symbol", Description="QQQ for NQ, SPY for ES", Order=3, GroupName="1. API")]
        public string EtfSymbol { get; set; }

        [NinjaScriptProperty]
        [Display(Name="Refresh Seconds", Order=4, GroupName="1. API")]
        [Range(3, 300)]
        public int RefreshSeconds { get; set; }

        [NinjaScriptProperty]
        [Display(Name="Show GEX Levels", Order=1, GroupName="2. Toggles")]
        public bool ShowGexLevels { get; set; }

        [NinjaScriptProperty]
        [Display(Name="Show Gamma Profile", Order=2, GroupName="2. Toggles")]
        public bool ShowGammaProfile { get; set; }

        [NinjaScriptProperty]
        [Display(Name="Show L2 Depth", Order=3, GroupName="2. Toggles")]
        public bool ShowL2Depth { get; set; }

        [NinjaScriptProperty]
        [Display(Name="Profile Width px", Order=4, GroupName="2. Toggles")]
        [Range(40,300)]
        public int ProfileWidth { get; set; }

        [NinjaScriptProperty]
        [Display(Name="L2 Width px", Order=5, GroupName="2. Toggles")]
        [Range(30,200)]
        public int L2Width { get; set; }

        #endregion

        #region State

        private Timer _timer;
        private readonly object _lock = new object();
        private volatile bool _busy;

        private double _callWall, _putWall, _flip, _hvl;
        // v2 pending slots — candidate values from the most recent poll;
        // only committed to the displayed values when 2 polls agree.
        private double _pCallWall, _pPutWall, _pFlip, _pHvl;
        private double _pR1, _pR2, _pS1, _pS2;
        private double _r1, _r2, _s1, _s2;
        private double _ratio = 1;
        private string _status = "Starting...";
        private List<double[]> _agg = new List<double[]>();

        private readonly SortedDictionary<double,int> _bids = new SortedDictionary<double,int>();
        private readonly SortedDictionary<double,int> _asks = new SortedDictionary<double,int>();

        private SharpDX.Direct2D1.Brush _brG, _brR, _brW, _brBg, _brM, _brCW, _brPW, _brFL, _brHV;
        private TextFormat _ft, _ftB;

        #endregion

        private double _cachedFutPrice;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "GEX Gamma Overlay - live levels + profile + L2";
                Name = "GEX Gamma Overlay";
                IsOverlay = true;
                IsSuspendedWhileInactive = true;
                Calculate = Calculate.OnEachTick;
                DataProvider = GexDataProvider.FlashAlpha;
                ApiKey = "";
                EtfSymbol = "QQQ";
                RefreshSeconds = 10;
                ShowGexLevels = true;
                ShowGammaProfile = true;
                ShowL2Depth = true;
                ProfileWidth = 160;
                L2Width = 140;
                _callWall = _putWall = _flip = _hvl = double.NaN;
                _r1 = _r2 = _s1 = _s2 = double.NaN;
            }
            else if (State == State.Historical)
            {
                // CRITICAL: force TLS 1.2 — .NET Framework defaults to TLS 1.0
                // which modern APIs (including Massive.com) reject
                try { ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12 | SecurityProtocolType.Tls11 | SecurityProtocolType.Tls; } catch {}

                if (!string.IsNullOrWhiteSpace(ApiKey))
                {
                    Print("GEX Overlay: starting API poll timer, key=" + ApiKey.Substring(0, Math.Min(6, ApiKey.Length)) + "...");
                    _timer = new Timer(Poll, null, 500, Math.Max(3, RefreshSeconds) * 1000);
                }
                else
                {
                    Print("GEX Overlay: no API key set — GEX levels and gamma profile will not load");
                }
            }
            else if (State == State.Terminated)
            {
                _timer?.Dispose();
                Ddx();
            }
        }

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (!ShowL2Depth) return;
            lock (_lock)
            {
                var d = e.MarketDataType == MarketDataType.Ask ? _asks : _bids;
                if (e.Operation == Operation.Remove) d.Remove(e.Price);
                else d[e.Price] = (int)e.Volume;
            }
        }

        protected override void OnBarUpdate()
        {
            // cache the current futures price so the background poll thread can read it
            if (CurrentBar >= 0)
                _cachedFutPrice = Close[0];
        }

        #region Poll

        private void Poll(object st)
        {
            if (_busy || string.IsNullOrWhiteSpace(ApiKey)) return;
            _busy = true;
            try
            {
                if (DataProvider == GexDataProvider.FlashAlpha)
                    PollFlashAlpha();
                else
                    PollMassive();
            }
            catch (Exception ex) { _status = "Err: " + (ex.Message.Length > 60 ? ex.Message.Substring(0,60) : ex.Message); Print("GEX Poll error: " + ex.Message); }
            finally { _busy = false; }
        }

        // ── Massive.com (Polygon.io) — raw options chain ─────────────────────────
        // Requires Advanced plan ($199/mo). JSON schema: results[n].details.strike_price,
        // results[n].details.contract_type, results[n].greeks.gamma, results[n].open_interest
        private void PollMassive()
        {
            string sym = EtfSymbol.Trim().ToUpper();
            string key = ApiKey.Trim();
            Print("GEX Poll [Massive]: fetching " + sym + "...");
            using (var wc = new WebClient())
            {
                wc.Headers.Add("User-Agent", "NinjaTrader-GEX/1.0");

                string snapRaw = wc.DownloadString(
                    string.Format("https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers/{0}?apiKey={1}",
                        sym, Uri.EscapeDataString(key)));
                double etfPx = XPrice(snapRaw);
                Print("GEX Poll [Massive]: ETF=" + etfPx.ToString("F2"));
                if (etfPx <= 0) { _status = "Massive: no ETF price"; return; }

                string chainRaw = wc.DownloadString(
                    string.Format("https://api.massive.com/v3/snapshot/options/{0}?limit=250&apiKey={1}",
                        sym, Uri.EscapeDataString(key)));
                string all = chainRaw;
                for (int pg = 0; pg < 2; pg++)
                {
                    string nx = XStr(chainRaw, "\"next_url\":\"", "\"");
                    if (string.IsNullOrEmpty(nx)) break;
                    chainRaw = wc.DownloadString(nx + "&apiKey=" + Uri.EscapeDataString(key));
                    all += chainRaw;
                }

                var rows = ParseMassive(all);
                Print("GEX Poll [Massive]: parsed " + rows.Count + " rows");
                if (rows.Count == 0) { _status = "Massive: 0 rows — check Advanced plan ($199/mo required for options)"; return; }

                CommitLevels(rows, etfPx, sym, "Massive");
            }
        }

        // ── FlashAlpha — pre-computed GEX (free tier: 5 calls/day; $49/mo for live) ──
        // Endpoint: GET https://lab.flashalpha.com/v1/exposure/gex/{ticker}
        // Auth: X-API-Key header
        // Response fields: call_wall, put_wall, gamma_flip, net_gex,
        //   strikes[]: { strike, net_gex, call_gex, put_gex, call_oi, put_oi }
        private void PollFlashAlpha()
        {
            string sym = EtfSymbol.Trim().ToUpper();
            string key = ApiKey.Trim();
            Print("GEX Poll [FlashAlpha]: fetching " + sym + "...");
            using (var wc = new WebClient())
            {
                wc.Headers.Add("User-Agent", "NinjaTrader-GEX/1.0");
                wc.Headers.Add("X-API-Key", key);

                // Get ETF price from Yahoo Finance (free, no API key needed)
                double etfPx = 0;
                try
                {
                    string yUrl = string.Format(
                        "https://query1.finance.yahoo.com/v8/finance/chart/{0}?interval=1m&range=1d", sym);
                    wc.Headers.Set("User-Agent", "Mozilla/5.0");
                    string yRaw = wc.DownloadString(yUrl);
                    wc.Headers.Set("User-Agent", "NinjaTrader-GEX/1.0");
                    etfPx = XNested(yRaw, "\"regularMarketPrice\"", ":");
                    if (etfPx <= 0) etfPx = XNested(yRaw, "\"close\"", ":");
                }
                catch (Exception ex2) { Print("GEX [FlashAlpha]: Yahoo price failed: " + ex2.Message); }
                if (etfPx <= 0) { _status = "FlashAlpha: could not get ETF price"; return; }
                Print("GEX Poll [FlashAlpha]: ETF=" + etfPx.ToString("F2"));

                // Restore API key header after Yahoo call (headers are per-request, but WebClient reuses them)
                wc.Headers.Set("X-API-Key", key);
                string gexRaw = wc.DownloadString(
                    string.Format("https://lab.flashalpha.com/v1/exposure/gex/{0}", sym));

                Print("GEX Poll [FlashAlpha]: response (first 400): " + gexRaw.Substring(0, Math.Min(400, gexRaw.Length)));

                // Extract top-level levels
                double cw = XNumField(gexRaw, "\"call_wall\"");
                double pw = XNumField(gexRaw, "\"put_wall\"");
                double fl = XNumField(gexRaw, "\"gamma_flip\"");

                // Parse per-strike data for the gamma profile
                var agg = ParseFlashAlphaStrikes(gexRaw);
                if (agg.Count == 0) { _status = "FlashAlpha: 0 strikes parsed"; return; }

                // HVL = strike with highest absolute net GEX
                double hv = agg.OrderByDescending(a => Math.Abs(a[1])).First()[0];

                CommitLevelsFromPrecomputed(cw, pw, fl, hv, agg, etfPx, sym);
            }
        }

        // Parse per-strike data from FlashAlpha strikes[] array
        // Expected: "strikes":[{"strike":465,"net_gex":-100000,"call_gex":50000,...},...]
        private List<double[]> ParseFlashAlphaStrikes(string j)
        {
            var result = new List<double[]>();
            int arrStart = j.IndexOf("\"strikes\"");
            if (arrStart < 0) return result;
            arrStart = j.IndexOf('[', arrStart);
            if (arrStart < 0) return result;
            int arrEnd = j.IndexOf(']', arrStart);
            if (arrEnd < 0) arrEnd = j.Length;

            string arr = j.Substring(arrStart, arrEnd - arrStart);
            int i = 0;
            while (true)
            {
                int ob = arr.IndexOf('{', i);
                if (ob < 0) break;
                int cb = arr.IndexOf('}', ob);
                if (cb < 0) break;
                string item = arr.Substring(ob, cb - ob + 1);
                i = cb + 1;

                double strike  = XNumField(item, "\"strike\"");
                double netGex  = XNumField(item, "\"net_gex\"");
                double callOI  = XNumField(item, "\"call_oi\"");
                double putOI   = XNumField(item, "\"put_oi\"");
                if (strike <= 0) continue;
                // col0=strike, col1=net_gex (pos=net call, neg=net put), col2=total_oi
                result.Add(new double[] { strike, netGex, callOI + putOI });
            }
            return result.OrderBy(a => a[0]).ToList();
        }

        // Shared level commit for FlashAlpha (pre-computed cw/pw/fl/hv + agg strikes)
        private void CommitLevelsFromPrecomputed(double cw, double pw, double fl, double hv,
            List<double[]> agg, double etfPx, string sym)
        {
            double futPx = _cachedFutPrice;
            double rat = (futPx > 0 && etfPx > 0 && futPx / etfPx > 1.5) ? futPx / etfPx : 1.0;

            var abP = agg.Where(a => a[1] > 0 && a[0] > etfPx).OrderBy(a => a[0]).Select(a => a[0]).ToList();
            var blN = agg.Where(a => a[1] < 0 && a[0] < etfPx).OrderByDescending(a => a[0]).Select(a => a[0]).ToList();
            double r1v = cw > 0 ? cw : (abP.Count > 0 ? abP[0] : double.NaN);
            double r2v = abP.Count > 0 ? abP.FirstOrDefault(x => x > (r1v > 0 ? r1v : 0)) : double.NaN;
            double s1v = pw > 0 ? pw : (blN.Count > 0 ? blN[0] : double.NaN);
            double s2v = blN.Count > 0 ? blN.FirstOrDefault(x => x < (s1v > 0 ? s1v : 99999)) : double.NaN;

            lock (_lock)
            {
                _ratio = rat;
                double ncw = cw * rat; double npw = pw * rat;
                double nfl = fl > 0 ? fl * rat : double.NaN;
                double nhv = hv > 0 ? hv * rat : double.NaN;
                double nr1 = r1v > 0 ? r1v * rat : double.NaN;
                double nr2 = r2v > 0 ? r2v * rat : double.NaN;
                double ns1 = s1v > 0 ? s1v * rat : double.NaN;
                double ns2 = s2v > 0 ? s2v * rat : double.NaN;

                ApplySmoothing(ncw, npw, nfl, nhv, nr1, nr2, ns1, ns2, futPx > 0 ? futPx : etfPx);
                _agg = agg.Select(a => new double[] { a[0] * rat, a[1] }).ToList();
                _status = string.Format("FA {0} {1}strikes {2:F1}x {3:HH:mm:ss}", sym, agg.Count, rat, DateTime.Now);
            }
            try { ChartControl?.Dispatcher?.InvokeAsync(() => ForceRefresh()); } catch { }
            Print("GEX Overlay: " + _status);
        }

        // Shared level commit for Massive (from parsed rows)
        private void CommitLevels(List<double[]> rows, double etfPx, string sym, string tag)
        {
            var agg   = Agg(rows);
            var calls = rows.Where(r => r[4] > 0).OrderByDescending(r => r[3]).ToList();
            var puts  = rows.Where(r => r[4] < 0).OrderBy(r => r[3]).ToList();
            double cw = calls.Count > 0 ? calls[0][0] : double.NaN;
            double pw = puts.Count  > 0 ? puts[0][0]  : double.NaN;
            double fl = Flip(rows);
            double hv = agg.OrderByDescending(a => a[2]).First()[0];

            var abP = agg.Where(a => a[1] > 0 && a[0] > etfPx).OrderBy(a => a[0]).Select(a => a[0]).ToList();
            var blN = agg.Where(a => a[1] < 0 && a[0] < etfPx).OrderByDescending(a => a[0]).Select(a => a[0]).ToList();
            double r1v = !double.IsNaN(cw) ? cw : (abP.Count > 0 ? abP[0] : double.NaN);
            double r2v = abP.Count > 0 ? abP.FirstOrDefault(x => x > (double.IsNaN(r1v) ? 0 : r1v)) : double.NaN;
            double s1v = !double.IsNaN(pw) ? pw : (blN.Count > 0 ? blN[0] : double.NaN);
            double s2v = blN.Count > 0 ? blN.FirstOrDefault(x => x < (double.IsNaN(s1v) ? 99999 : s1v)) : double.NaN;

            double futPx = _cachedFutPrice;
            double rat = (futPx > 0 && etfPx > 0 && futPx / etfPx > 1.5) ? futPx / etfPx : 1.0;

            lock (_lock)
            {
                _ratio = rat;
                double ncw = cw * rat; double npw = pw * rat;
                double nfl = double.IsNaN(fl) ? double.NaN : fl * rat;
                double nhv = hv * rat;
                double nr1 = r1v > 0 ? r1v * rat : double.NaN;
                double nr2 = r2v > 0 ? r2v * rat : double.NaN;
                double ns1 = s1v > 0 ? s1v * rat : double.NaN;
                double ns2 = s2v > 0 ? s2v * rat : double.NaN;

                ApplySmoothing(ncw, npw, nfl, nhv, nr1, nr2, ns1, ns2, futPx > 0 ? futPx : etfPx);
                _agg = agg.Select(a => new double[] { a[0] * rat, a[1] }).ToList();
                _status = string.Format("{0} {1} rows {2}strikes {3:F1}x {4:HH:mm:ss}", tag, rows.Count, agg.Count, rat, DateTime.Now);
            }
            try { ChartControl?.Dispatcher?.InvokeAsync(() => ForceRefresh()); } catch { }
            Print("GEX Overlay: " + _status);
        }

        // Two-poll confirmation smoothing — outliers filtered, stable levels commit
        private void ApplySmoothing(double ncw, double npw, double nfl, double nhv,
            double nr1, double nr2, double ns1, double ns2, double refPx)
        {
            double t = refPx * 0.0010; // 0.10% tolerance
            Func<double,double,bool> ok = (a,b) =>
                (!double.IsNaN(a) && !double.IsNaN(b) && Math.Abs(a-b) < t) ||
                (double.IsNaN(a) && double.IsNaN(b));
            if (ok(ncw, _pCallWall) && !double.IsNaN(ncw)) _callWall = ncw;
            if (ok(npw, _pPutWall)  && !double.IsNaN(npw)) _putWall  = npw;
            if (ok(nfl, _pFlip)     && !double.IsNaN(nfl)) _flip     = nfl;
            if (ok(nhv, _pHvl)      && !double.IsNaN(nhv)) _hvl      = nhv;
            if (ok(nr1, _pR1)       && !double.IsNaN(nr1)) _r1       = nr1;
            if (ok(nr2, _pR2)       && !double.IsNaN(nr2)) _r2       = nr2;
            if (ok(ns1, _pS1)       && !double.IsNaN(ns1)) _s1       = ns1;
            if (ok(ns2, _pS2)       && !double.IsNaN(ns2)) _s2       = ns2;
            _pCallWall=ncw; _pPutWall=npw; _pFlip=nfl; _pHvl=nhv;
            _pR1=nr1; _pR2=nr2; _pS1=ns1; _pS2=ns2;
        }

        // Parse Massive.com options chain — FIXED nesting:
        // results[n].details.strike_price / .contract_type  |  results[n].greeks.gamma  |  results[n].open_interest
        private List<double[]> ParseMassive(string j)
        {
            var rows = new List<double[]>();
            int i = 0;
            while (true)
            {
                // Each result object contains a "details" sub-object
                int di = j.IndexOf("\"details\":", i);
                if (di < 0) break;
                int detailsEnd = di + 2000; // scan window for this result

                // strike_price inside details
                int si = j.IndexOf("\"strike_price\":", di);
                if (si < 0 || si > detailsEnd) { i = di + 10; continue; }
                double strike = XNum(j, si);

                // contract_type inside details
                int ci = j.IndexOf("\"contract_type\":\"", di);
                string tp = (ci >= 0 && ci < detailsEnd) ? XStr(j, "\"contract_type\":\"", "\"", ci) : "";
                double sign = tp == "put" ? -1 : 1;

                // gamma inside greeks (can be after details)
                int gi = j.IndexOf("\"greeks\":", di);
                double gamma = 0;
                if (gi >= 0 && gi < di + 3000)
                {
                    int gammaIdx = j.IndexOf("\"gamma\":", gi);
                    if (gammaIdx >= 0 && gammaIdx < gi + 400)
                        gamma = XNum(j, gammaIdx);
                }

                // open_interest at result level (not nested)
                int oii = j.IndexOf("\"open_interest\":", di);
                double oiv = (oii >= 0 && oii < di + 3000) ? XNum(j, oii) : 0;

                i = di + 10;
                if (strike <= 0 || gamma <= 0 || oiv <= 0 || string.IsNullOrEmpty(tp)) continue;
                rows.Add(new double[] { strike, gamma, oiv, gamma * oiv * 100 * sign, sign });
            }
            return rows.OrderBy(r => r[0]).ToList();
        }

        private List<double[]> Agg(List<double[]> rows)
        {
            var m = new Dictionary<double, double[]>();
            foreach (var r in rows)
            {
                if (!m.TryGetValue(r[0], out var a)) a = new double[] { r[0], 0, 0 };
                a[1] += r[3]; a[2] += r[2];
                m[r[0]] = a;
            }
            return m.Values.OrderBy(a => a[0]).ToList();
        }

        private double Flip(List<double[]> rows)
        {
            double run = 0;
            foreach (var r in rows)
            {
                double prev = run; run += r[3];
                if ((prev <= 0 && run >= 0) || (prev >= 0 && run <= 0)) return r[0];
            }
            return double.NaN;
        }

        private double XPrice(string j)
        {
            double v = XNested(j, "\"lastTrade\"", "\"p\":");
            if (v > 0) return v;
            v = XNested(j, "\"day\"", "\"c\":");
            if (v > 0) return v;
            return XNested(j, "\"prevDay\"", "\"c\":");
        }

        private double XNested(string j, string o, string k)
        {
            int i = j.IndexOf(o); if (i < 0) return 0;
            int n = j.IndexOf(k, i); if (n < 0 || n > i + 500) return 0;
            return XNum(j, n);
        }

        // Extract a numeric value from a top-level JSON field: "fieldName": 123.45
        private double XNumField(string j, string fieldName)
        {
            int idx = j.IndexOf(fieldName); if (idx < 0) return 0;
            return XNum(j, idx);
        }

        // Extract numeric value after the colon following position `after`
        private double XNum(string j, int after)
        {
            int c = j.IndexOf(':', after); if (c < 0) return 0;
            int s = c + 1;
            while (s < j.Length && (j[s] == ' ' || j[s] == '"')) s++;
            int e = s;
            while (e < j.Length && (char.IsDigit(j[e]) || j[e] == '.' || j[e] == '-' || j[e] == '+' || j[e] == 'e' || j[e] == 'E')) e++;
            if (e == s) return 0;
            double.TryParse(j.Substring(s, e - s), NumberStyles.Float, CultureInfo.InvariantCulture, out double v);
            return v;
        }

        private string XStr(string j, string pre, string suf, int from = 0)
        {
            int i = j.IndexOf(pre, from); if (i < 0) return "";
            int s = i + pre.Length;
            int e = j.IndexOf(suf, s); if (e < 0) return "";
            return j.Substring(s, e - s);
        }

        #endregion

        #region Render

        public override void OnRenderTargetChanged()
        {
            Ddx();
            if (RenderTarget == null) return;
            _brG = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(24/255f, 201/255f, 127/255f, 0.9f));
            _brR = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(1f, 90/255f, 95/255f, 0.9f));
            _brW = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.86f, 0.88f, 0.94f, 0.86f));
            _brBg = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.03f, 0.05f, 0.11f, 0.94f));
            _brM = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.58f, 0.64f, 0.80f, 0.55f));
            _brCW = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(24/255f, 201/255f, 127/255f, 1f));
            _brPW = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(217/255f, 70/255f, 239/255f, 1f));
            _brFL = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(247/255f, 181/255f, 0f, 1f));
            _brHV = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(1f, 140/255f, 0f, 1f));
            var fac = NinjaTrader.Core.Globals.DirectWriteFactory;
            _ft = new TextFormat(fac, "Consolas", 10f);
            _ftB = new TextFormat(fac, "Consolas", FontWeight.Bold, FontStyle.Normal, 10f);
        }

        private void Ddx()
        {
            _brG?.Dispose(); _brR?.Dispose(); _brW?.Dispose(); _brBg?.Dispose(); _brM?.Dispose();
            _brCW?.Dispose(); _brPW?.Dispose(); _brFL?.Dispose(); _brHV?.Dispose();
            _ft?.Dispose(); _ftB?.Dispose();
            _brG=_brR=_brW=_brBg=_brM=_brCW=_brPW=_brFL=_brHV=null; _ft=_ftB=null;
        }

        protected override void OnRender(ChartControl cc, ChartScale cs)
        {
            base.OnRender(cc, cs);
            if (RenderTarget == null || _brG == null) return;
            var rt = RenderTarget;
            // Use RenderTarget physical dimensions — cc.ActualWidth is WPF logical (DIP) and
            // underestimates the real canvas at high-DPI, causing panels to land at the wrong x.
            float W = RenderTarget.Size.Width;
            float H = RenderTarget.Size.Height;
            float rr = (ShowGammaProfile ? ProfileWidth : 0) + (ShowL2Depth ? L2Width : 0);
            float cW = W - rr;

            if (ShowGexLevels)
            {
                lock (_lock)
                {
                    DL(rt, cs, cW, _callWall, "Call Wall", _brCW, 2.5f);
                    DL(rt, cs, cW, _putWall, "Put Wall", _brPW, 2.5f);
                    DL(rt, cs, cW, _flip, "Flip", _brFL, 2f);
                    DL(rt, cs, cW, _hvl, "HVL", _brHV, 1.5f);
                    DL(rt, cs, cW, _r1, "R1", _brG, 1.5f);
                    DL(rt, cs, cW, _r2, "R2", _brG, 1f);
                    DL(rt, cs, cW, _s1, "S1", _brR, 1.5f);
                    DL(rt, cs, cW, _s2, "S2", _brR, 1f);
                }
            }

            if (ShowGammaProfile)
            {
                List<double[]> agg;
                lock (_lock) { agg = _agg.ToList(); }
                if (agg.Count > 0)
                {
                    float pW = ProfileWidth, pX = W - pW;
                    rt.FillRectangle(new RectangleF(pX, 0, pW, H), _brBg);
                    double mid = (cs.MaxValue + cs.MinValue) / 2;
                    var vis = agg.Where(a => a[0] >= mid*0.85 && a[0] <= mid*1.15).ToList();
                    if (vis.Count == 0) vis = agg;
                    double mx = vis.Max(a => Math.Abs(a[1]));
                    if (mx <= 0) mx = 1;
                    foreach (var a in vis)
                    {
                        float y = (float)cs.GetYByValue(a[0]);
                        if (y < -5 || y > H+5) continue;
                        float f = (float)(Math.Abs(a[1]) / mx);
                        float bw = Math.Max(2, f * (pW - 6));
                        rt.FillRectangle(new RectangleF(pX+2, y-3, bw, 5), a[1] >= 0 ? _brG : _brR);
                    }
                    double cur = _cachedFutPrice;
                    if (cur > 0)
                    {
                        float yn = (float)cs.GetYByValue(cur);
                        rt.DrawLine(new Vector2(pX, yn), new Vector2(pX+pW, yn), _brW, 1.5f);
                    }
                    rt.DrawText("GEX PROFILE", _ftB, new RectangleF(pX+4, 2, pW-8, 14), _brM);
                }
            }

            if (ShowL2Depth)
            {
                List<KeyValuePair<double,int>> bids, asks;
                lock (_lock) { bids = _bids.ToList(); asks = _asks.ToList(); }
                if (bids.Count > 0 || asks.Count > 0)
                {
                    // v3: detect WALLS - any level with size >= 3x median
                    // and plot them as gold lines across the whole chart
                    var allSizes = bids.Concat(asks).Select(kv => kv.Value).OrderBy(v => v).ToList();
                    int median = allSizes.Count > 0 ? allSizes[allSizes.Count / 2] : 1;
                    int wallThresh = Math.Max(median * 3, 20);
                    using (var gold = new SharpDX.Direct2D1.SolidColorBrush(rt, new Color4(1f, 0.84f, 0f, 0.95f)))
                    using (var goldDk = new SharpDX.Direct2D1.SolidColorBrush(rt, new Color4(0.3f, 0.25f, 0f, 0.8f)))
                    {
                        foreach (var kv in bids.Concat(asks))
                        {
                            if (kv.Value < wallThresh) continue;
                            float wy = (float)cs.GetYByValue(kv.Key);
                            if (wy < -20 || wy > H + 20) continue;
                            // gold line across chart
                            rt.DrawLine(new Vector2(0, wy), new Vector2(cW, wy), goldDk, 4);
                            rt.DrawLine(new Vector2(0, wy), new Vector2(cW, wy), gold, 2);
                            // tag
                            float tgW = 80, tgH = 14;
                            float tgX = cW - tgW - 100;
                            rt.FillRectangle(new RectangleF(tgX, wy - tgH/2, tgW, tgH), gold);
                            using (var tb = new SharpDX.Direct2D1.SolidColorBrush(rt, new Color4(0.08f, 0.05f, 0f, 1f)))
                                rt.DrawText(string.Format("WALL {0}", kv.Value), _ftB, new RectangleF(tgX + 4, wy - tgH/2 + 1, tgW - 8, tgH - 2), tb);
                        }
                    }
                    float lW = L2Width, lX = W - (ShowGammaProfile ? ProfileWidth : 0) - lW;
                    rt.FillRectangle(new RectangleF(lX, 0, lW, H), _brBg);
                    int maxSz = Math.Max(1, bids.Concat(asks).Max(kv => kv.Value));
                    float half = lW/2, ctr = lX + half; float rH = Math.Max(3f, (float)(cs.GetYByValue(0) - cs.GetYByValue(0.25))); if (rH <= 0) rH = 4f;
                    foreach (var kv in bids)
                    {
                        float y = (float)cs.GetYByValue(kv.Key);
                        if (y < -3 || y > H+3) continue;
                        float bw = (kv.Value/(float)maxSz) * (half-4);
                        rt.FillRectangle(new RectangleF(ctr-bw, y-2, bw, 3), _brG);
                        if (bw > 14) rt.DrawText(kv.Value.ToString(), _ft, new RectangleF(ctr-bw, y-6, bw, 12), _brW);
                    }
                    foreach (var kv in asks)
                    {
                        float y = (float)cs.GetYByValue(kv.Key);
                        if (y < -3 || y > H+3) continue;
                        float bw = (kv.Value/(float)maxSz) * (half-4);
                        rt.FillRectangle(new RectangleF(ctr, y-2, bw, 3), _brR);
                        if (bw > 14) rt.DrawText(kv.Value.ToString(), _ft, new RectangleF(ctr+2, y-6, bw, 12), _brW);
                    }
                }
            }

            rt.DrawText(_status, _ft, new RectangleF(4, H-16, W-8, 14), _brM);
        }

        private void DL(RenderTarget rt, ChartScale cs, float cW, double px, string lb, SharpDX.Direct2D1.Brush br, float w)
        {
            if (double.IsNaN(px) || px <= 0) return;
            float y = (float)cs.GetYByValue(px);
            if (y < -20 || y > cs.Height+20) return;
            using (var dk = new SharpDX.Direct2D1.SolidColorBrush(rt, new Color4(0,0,0,0.8f)))
                rt.DrawLine(new Vector2(0,y), new Vector2(cW,y), dk, w+2);
            rt.DrawLine(new Vector2(0,y), new Vector2(cW,y), br, w);
            float tw=88, th=15, tx=cW-tw-4, ty=y-th/2;
            rt.FillRectangle(new RectangleF(tx,ty,tw,th), br);
            using (var t = new SharpDX.Direct2D1.SolidColorBrush(rt, new Color4(0.02f,0.06f,0.10f,1f)))
                rt.DrawText(string.Format("{0}  {1:F2}", lb, px), _ftB, new RectangleF(tx+3,ty+1,tw-6,th-2), t);
        }

        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
{
private GEXGammaOverlay[] cacheGEXGammaOverlay;
public GEXGammaOverlay GEXGammaOverlay(GexDataProvider dataProvider, string apiKey, string etfSymbol, int refreshSeconds, bool showGexLevels, bool showGammaProfile, bool showL2Depth, int profileWidth, int l2Width)
{
return GEXGammaOverlay(Input, dataProvider, apiKey, etfSymbol, refreshSeconds, showGexLevels, showGammaProfile, showL2Depth, profileWidth, l2Width);
}

public GEXGammaOverlay GEXGammaOverlay(ISeries<double> input, GexDataProvider dataProvider, string apiKey, string etfSymbol, int refreshSeconds, bool showGexLevels, bool showGammaProfile, bool showL2Depth, int profileWidth, int l2Width)
{
if (cacheGEXGammaOverlay != null)
for (int idx = 0; idx < cacheGEXGammaOverlay.Length; idx++)
if (cacheGEXGammaOverlay[idx] != null && cacheGEXGammaOverlay[idx].DataProvider == dataProvider && cacheGEXGammaOverlay[idx].ApiKey == apiKey && cacheGEXGammaOverlay[idx].EtfSymbol == etfSymbol && cacheGEXGammaOverlay[idx].RefreshSeconds == refreshSeconds && cacheGEXGammaOverlay[idx].ShowGexLevels == showGexLevels && cacheGEXGammaOverlay[idx].ShowGammaProfile == showGammaProfile && cacheGEXGammaOverlay[idx].ShowL2Depth == showL2Depth && cacheGEXGammaOverlay[idx].ProfileWidth == profileWidth && cacheGEXGammaOverlay[idx].L2Width == l2Width && cacheGEXGammaOverlay[idx].EqualsInput(input))
return cacheGEXGammaOverlay[idx];
return CacheIndicator<GEXGammaOverlay>(new GEXGammaOverlay(){ DataProvider = dataProvider, ApiKey = apiKey, EtfSymbol = etfSymbol, RefreshSeconds = refreshSeconds, ShowGexLevels = showGexLevels, ShowGammaProfile = showGammaProfile, ShowL2Depth = showL2Depth, ProfileWidth = profileWidth, L2Width = l2Width }, input, ref cacheGEXGammaOverlay);
}
}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
{
public Indicators.GEXGammaOverlay GEXGammaOverlay(GexDataProvider dataProvider, string apiKey, string etfSymbol, int refreshSeconds, bool showGexLevels, bool showGammaProfile, bool showL2Depth, int profileWidth, int l2Width)
{
return indicator.GEXGammaOverlay(Input, dataProvider, apiKey, etfSymbol, refreshSeconds, showGexLevels, showGammaProfile, showL2Depth, profileWidth, l2Width);
}

public Indicators.GEXGammaOverlay GEXGammaOverlay(ISeries<double> input, GexDataProvider dataProvider, string apiKey, string etfSymbol, int refreshSeconds, bool showGexLevels, bool showGammaProfile, bool showL2Depth, int profileWidth, int l2Width)
{
return indicator.GEXGammaOverlay(input, dataProvider, apiKey, etfSymbol, refreshSeconds, showGexLevels, showGammaProfile, showL2Depth, profileWidth, l2Width);
}
}
}

namespace NinjaTrader.NinjaScript.Strategies
{
public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
{
public Indicators.GEXGammaOverlay GEXGammaOverlay(GexDataProvider dataProvider, string apiKey, string etfSymbol, int refreshSeconds, bool showGexLevels, bool showGammaProfile, bool showL2Depth, int profileWidth, int l2Width)
{
return indicator.GEXGammaOverlay(Input, dataProvider, apiKey, etfSymbol, refreshSeconds, showGexLevels, showGammaProfile, showL2Depth, profileWidth, l2Width);
}

public Indicators.GEXGammaOverlay GEXGammaOverlay(ISeries<double> input, GexDataProvider dataProvider, string apiKey, string etfSymbol, int refreshSeconds, bool showGexLevels, bool showGammaProfile, bool showL2Depth, int profileWidth, int l2Width)
{
return indicator.GEXGammaOverlay(input, dataProvider, apiKey, etfSymbol, refreshSeconds, showGexLevels, showGammaProfile, showL2Depth, profileWidth, l2Width);
}
}
}

#endregion
