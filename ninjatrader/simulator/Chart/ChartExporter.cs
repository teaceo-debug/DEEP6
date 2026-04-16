// ChartExporter: Generates self-contained HTML chart files from simulator output.
//
// Three modes:
//   1. CandleChart  — Lightweight Charts candles + signal markers + entry/exit arrows
//   2. FootprintChart — Full footprint cells with bid×ask, POC, VAH/VAL, signals, score HUD
//   3. DashboardJson — JSON output for the Next.js dashboard's WebSocket feed
//
// All HTML files are fully self-contained (inline JS/CSS, CDN for Lightweight Charts).
// Open directly in any browser — no server needed.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using NinjaTrader.NinjaScript;

namespace NinjaScriptSim.Lifecycle
{
    public static class ChartExporter
    {
        // ═══════════════════════════════════════════════════════════════════
        //  Mode 1: Candle Chart (Lightweight Charts)
        // ═══════════════════════════════════════════════════════════════════

        /// <summary>
        /// Generate a standalone HTML file with Lightweight Charts candles,
        /// signal markers, score annotations, and entry/exit arrows.
        /// </summary>
        public static void ExportCandleChart(SessionData session, IReadOnlyList<string> printLog,
            string outputPath, string title = "DEEP6 Simulator — NQ Session")
        {
            var signals = ParseSignals(printLog);
            var entries = ParseEntries(printLog);
            var scores = ParseScores(printLog);

            var sb = new StringBuilder();
            sb.AppendLine("<!DOCTYPE html>");
            sb.AppendLine("<html lang='en'><head><meta charset='UTF-8'>");
            sb.AppendLine($"<title>{title}</title>");
            sb.AppendLine("<style>");
            sb.AppendLine(CssBase());
            sb.AppendLine("</style>");
            sb.AppendLine("<script src='https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js'></script>");
            sb.AppendLine("</head><body>");
            sb.AppendLine($"<div id='header'><h1>{title}</h1>");
            sb.AppendLine($"<span class='meta'>{session.Bars.Count} bars | {signals.Count} signals | {entries.Count} entries</span></div>");
            sb.AppendLine("<div id='chart'></div>");
            sb.AppendLine("<div id='legend'></div>");
            sb.AppendLine("<script>");

            // Chart data
            sb.AppendLine("const bars = [");
            foreach (var bar in session.Bars)
            {
                long ts = new DateTimeOffset(bar.Time).ToUnixTimeSeconds();
                sb.AppendLine(string.Format(CultureInfo.InvariantCulture,
                    "  {{time:{0},open:{1},high:{2},low:{3},close:{4}}},",
                    ts, bar.Open, bar.High, bar.Low, bar.Close));
            }
            sb.AppendLine("];");

            // Volume data
            sb.AppendLine("const volumes = [");
            foreach (var bar in session.Bars)
            {
                long ts = new DateTimeOffset(bar.Time).ToUnixTimeSeconds();
                string color = bar.Close >= bar.Open ? "'rgba(0,255,136,0.3)'" : "'rgba(255,46,99,0.3)'";
                sb.AppendLine(string.Format(CultureInfo.InvariantCulture,
                    "  {{time:{0},value:{1},color:{2}}},", ts, bar.Volume, color));
            }
            sb.AppendLine("];");

            // Signal markers
            sb.AppendLine("const markers = [");
            foreach (var sig in signals)
            {
                string color = sig.Family switch
                {
                    "ABS" => sig.Direction > 0 ? "'#00ff88'" : "'#ff2e63'",
                    "EXH" => sig.Direction > 0 ? "'#ffd60a'" : "'#ff6b35'",
                    _ => "'#00d9ff'",
                };
                string shape = sig.Direction > 0 ? "'arrowUp'" : "'arrowDown'";
                string pos = sig.Direction > 0 ? "'belowBar'" : "'aboveBar'";
                if (sig.BarIndex >= 0 && sig.BarIndex < session.Bars.Count)
                {
                    long ts = new DateTimeOffset(session.Bars[sig.BarIndex].Time).ToUnixTimeSeconds();
                    sb.AppendLine(string.Format(
                        "  {{time:{0},position:{1},color:{2},shape:{3},text:'{4}'}},",
                        ts, pos, color, shape, sig.SignalId));
                }
            }
            foreach (var entry in entries)
            {
                if (entry.BarIndex >= 0 && entry.BarIndex < session.Bars.Count)
                {
                    long ts = new DateTimeOffset(session.Bars[entry.BarIndex].Time).ToUnixTimeSeconds();
                    string color = entry.Direction > 0 ? "'#a3ff00'" : "'#ff2e63'";
                    string shape = entry.Direction > 0 ? "'arrowUp'" : "'arrowDown'";
                    string pos = entry.Direction > 0 ? "'belowBar'" : "'aboveBar'";
                    sb.AppendLine(string.Format(
                        "  {{time:{0},position:{1},color:{2},shape:{3},text:'ENTRY',size:2}},",
                        ts, pos, color, shape));
                }
            }
            sb.AppendLine("];");

            // Chart JS
            sb.AppendLine(JsCandleChart());
            sb.AppendLine("</script>");

            // Score timeline below chart
            if (scores.Count > 0)
            {
                sb.AppendLine("<div id='scores'><h3>Score Timeline</h3><table>");
                sb.AppendLine("<tr><th>Bar</th><th>Score</th><th>Tier</th><th>Narrative</th></tr>");
                foreach (var s in scores.TakeLast(50))
                {
                    string tierClass = s.Tier switch { "TYPE_A" => "tier-a", "TYPE_B" => "tier-b", _ => "tier-c" };
                    sb.AppendLine($"<tr><td>{s.Bar}</td><td class='{tierClass}'>{s.Score:F1}</td><td class='{tierClass}'>{s.Tier}</td><td>{s.Narrative}</td></tr>");
                }
                sb.AppendLine("</table></div>");
            }

            sb.AppendLine("</body></html>");
            File.WriteAllText(outputPath, sb.ToString());
        }

        // ═══════════════════════════════════════════════════════════════════
        //  Mode 2: Footprint Chart (full cells, POC, VAH/VAL, signals)
        // ═══════════════════════════════════════════════════════════════════

        /// <summary>
        /// Generate a standalone HTML footprint chart with bid×ask cells,
        /// POC highlighting, imbalance markers, signal annotations, and score HUD.
        /// Uses HTML5 Canvas for rendering — matches the dashboard's visual language.
        /// </summary>
        public static void ExportFootprintChart(SessionData session, IReadOnlyList<string> printLog,
            string outputPath, double tickSize = 0.25, string title = "DEEP6 Footprint — NQ Session")
        {
            var signals = ParseSignals(printLog);
            var scores = ParseScores(printLog);

            var sb = new StringBuilder();
            sb.AppendLine("<!DOCTYPE html>");
            sb.AppendLine("<html lang='en'><head><meta charset='UTF-8'>");
            sb.AppendLine($"<title>{title}</title>");
            sb.AppendLine("<style>");
            sb.AppendLine(CssBase());
            sb.AppendLine(CssFootprint());
            sb.AppendLine("</style>");
            sb.AppendLine("</head><body>");
            sb.AppendLine($"<div id='header'><h1>{title}</h1>");
            sb.AppendLine($"<span class='meta'>{session.Bars.Count} bars | tick={tickSize} | {signals.Count} signals</span></div>");

            // Score HUD (latest)
            var lastScore = scores.LastOrDefault();
            if (lastScore != null)
            {
                string tierClass = lastScore.Tier switch { "TYPE_A" => "tier-a", "TYPE_B" => "tier-b", _ => "tier-c" };
                sb.AppendLine($"<div id='score-hud'>");
                sb.AppendLine($"<div class='score-value {tierClass}'>{lastScore.Score:F1}</div>");
                sb.AppendLine($"<div class='score-tier {tierClass}'>{lastScore.Tier}</div>");
                sb.AppendLine($"<div class='score-narrative'>{lastScore.Narrative}</div>");
                sb.AppendLine("</div>");
            }

            sb.AppendLine("<div id='footprint-container'><canvas id='fp-canvas'></canvas></div>");
            sb.AppendLine("<script>");

            // Emit bar data as JSON for the canvas renderer
            sb.AppendLine("const fpBars = [");
            foreach (var bar in session.Bars)
            {
                long ts = new DateTimeOffset(bar.Time).ToUnixTimeSeconds();
                sb.AppendLine(string.Format(CultureInfo.InvariantCulture,
                    "  {{ts:{0},o:{1},h:{2},l:{3},c:{4},vol:{5},levels:{{",
                    ts, bar.Open, bar.High, bar.Low, bar.Close, bar.Volume));

                // Build levels from ticks if available
                if (bar.Ticks != null && bar.Ticks.Count > 0)
                {
                    var levels = new SortedDictionary<double, (long bid, long ask)>();
                    foreach (var tick in bar.Ticks)
                    {
                        double px = System.Math.Round(tick.Price / tickSize) * tickSize;
                        if (!levels.ContainsKey(px)) levels[px] = (0, 0);
                        var lv = levels[px];
                        if (tick.Aggressor == 1) levels[px] = (lv.bid, lv.ask + tick.Size);
                        else if (tick.Aggressor == 2) levels[px] = (lv.bid + tick.Size, lv.ask);
                    }
                    bool first = true;
                    foreach (var kv in levels)
                    {
                        if (!first) sb.Append(",");
                        sb.Append(string.Format(CultureInfo.InvariantCulture,
                            "'{0}':[{1},{2}]", kv.Key, kv.Value.bid, kv.Value.ask));
                        first = false;
                    }
                }
                sb.AppendLine("}},");
            }
            sb.AppendLine("];");

            // Signal overlay data
            sb.AppendLine("const fpSignals = [");
            foreach (var sig in signals)
            {
                if (sig.BarIndex >= 0 && sig.BarIndex < session.Bars.Count)
                {
                    sb.AppendLine(string.Format(
                        "  {{bar:{0},id:'{1}',dir:{2},family:'{3}',str:{4}}},",
                        sig.BarIndex, sig.SignalId, sig.Direction, sig.Family,
                        sig.Strength.ToString("F2", CultureInfo.InvariantCulture)));
                }
            }
            sb.AppendLine("];");

            sb.AppendLine($"const TICK_SIZE = {tickSize.ToString(CultureInfo.InvariantCulture)};");
            sb.AppendLine(JsFootprintChart());
            sb.AppendLine("</script>");
            sb.AppendLine("</body></html>");

            File.WriteAllText(outputPath, sb.ToString());
        }

        // ═══════════════════════════════════════════════════════════════════
        //  Mode 3: Dashboard JSON Server
        // ═══════════════════════════════════════════════════════════════════

        /// <summary>
        /// Export session data as JSON matching the Next.js dashboard's FootprintBar format.
        /// Can be served via a static file server or piped into the dashboard's WebSocket.
        /// </summary>
        public static void ExportDashboardJson(SessionData session, IReadOnlyList<string> printLog,
            string outputPath, double tickSize = 0.25)
        {
            var signals = ParseSignals(printLog);
            var scores = ParseScores(printLog);

            using var writer = new StreamWriter(outputPath);
            writer.WriteLine("[");

            for (int i = 0; i < session.Bars.Count; i++)
            {
                var bar = session.Bars[i];
                long ts = new DateTimeOffset(bar.Time).ToUnixTimeSeconds();

                // Build levels
                var levels = new SortedDictionary<double, (long bid, long ask)>();
                if (bar.Ticks != null)
                {
                    foreach (var tick in bar.Ticks)
                    {
                        double px = System.Math.Round(tick.Price / tickSize) * tickSize;
                        if (!levels.ContainsKey(px)) levels[px] = (0, 0);
                        var lv = levels[px];
                        if (tick.Aggressor == 1) levels[px] = (lv.bid, lv.ask + tick.Size);
                        else if (tick.Aggressor == 2) levels[px] = (lv.bid + tick.Size, lv.ask);
                    }
                }

                // Compute POC
                double pocPrice = bar.Close;
                long pocVol = 0;
                foreach (var kv in levels)
                {
                    long total = kv.Value.bid + kv.Value.ask;
                    if (total > pocVol) { pocVol = total; pocPrice = kv.Key; }
                }

                long barDelta = levels.Values.Sum(lv => lv.ask - lv.bid);

                writer.Write("  {");
                writer.Write(string.Format(CultureInfo.InvariantCulture,
                    "\"session_id\":\"sim\",\"bar_index\":{0},\"ts\":{1},\"open\":{2},\"high\":{3},\"low\":{4},\"close\":{5}," +
                    "\"total_vol\":{6},\"bar_delta\":{7},\"cvd\":0,\"poc_price\":{8},\"bar_range\":{9}," +
                    "\"running_delta\":0,\"max_delta\":0,\"min_delta\":0,\"levels\":{{",
                    i, ts, bar.Open, bar.High, bar.Low, bar.Close,
                    bar.Volume, barDelta, pocPrice,
                    (bar.High - bar.Low).ToString(CultureInfo.InvariantCulture)));

                bool firstLevel = true;
                foreach (var kv in levels)
                {
                    if (!firstLevel) writer.Write(",");
                    writer.Write(string.Format(CultureInfo.InvariantCulture,
                        "\"{0}\":{{\"bid_vol\":{1},\"ask_vol\":{2}}}",
                        kv.Key, kv.Value.bid, kv.Value.ask));
                    firstLevel = false;
                }

                writer.Write("}");

                // Attach signals for this bar
                var barSignals = signals.Where(s => s.BarIndex == i).ToList();
                if (barSignals.Count > 0)
                {
                    writer.Write(",\"signals\":[");
                    for (int s = 0; s < barSignals.Count; s++)
                    {
                        if (s > 0) writer.Write(",");
                        writer.Write(string.Format(CultureInfo.InvariantCulture,
                            "{{\"signal_id\":\"{0}\",\"direction\":{1},\"strength\":{2},\"family\":\"{3}\"}}",
                            barSignals[s].SignalId, barSignals[s].Direction,
                            barSignals[s].Strength.ToString("F2", CultureInfo.InvariantCulture),
                            barSignals[s].Family));
                    }
                    writer.Write("]");
                }

                writer.Write("}");
                if (i < session.Bars.Count - 1) writer.Write(",");
                writer.WriteLine();
            }

            writer.WriteLine("]");
        }

        // ═══════════════════════════════════════════════════════════════════
        //  Dashboard HTTP Server
        // ═══════════════════════════════════════════════════════════════════

        /// <summary>
        /// Start a simple HTTP server that serves the dashboard JSON on /api/bars.
        /// The Next.js dashboard can fetch from this endpoint.
        /// </summary>
        public static void StartServer(string jsonPath, int port = 8080)
        {
            var listener = new System.Net.HttpListener();
            listener.Prefixes.Add($"http://+:{port}/");
            listener.Start();
            Console.WriteLine($"  Serving dashboard data on http://localhost:{port}/api/bars");
            Console.WriteLine("  Press Ctrl+C to stop.");

            string jsonContent = File.ReadAllText(jsonPath);

            while (listener.IsListening)
            {
                try
                {
                    var ctx = listener.GetContext();
                    ctx.Response.ContentType = "application/json";
                    ctx.Response.Headers.Add("Access-Control-Allow-Origin", "*");
                    ctx.Response.Headers.Add("Access-Control-Allow-Methods", "GET");

                    byte[] data;
                    if (ctx.Request.Url.AbsolutePath == "/api/bars" || ctx.Request.Url.AbsolutePath == "/")
                        data = Encoding.UTF8.GetBytes(jsonContent);
                    else
                        data = Encoding.UTF8.GetBytes("{\"error\":\"not found\"}");

                    ctx.Response.OutputStream.Write(data, 0, data.Length);
                    ctx.Response.Close();
                }
                catch (System.Net.HttpListenerException) { break; }
            }
        }

        // ═══════════════════════════════════════════════════════════════════
        //  PrintLog Parsers
        // ═══════════════════════════════════════════════════════════════════

        private record SignalInfo(int BarIndex, string SignalId, string Family, int Direction, double Strength);
        private record EntryInfo(int BarIndex, int Direction, string Label);
        private record ScoreInfo(int Bar, double Score, string Tier, string Narrative);

        private static List<SignalInfo> ParseSignals(IReadOnlyList<string> log)
        {
            var results = new List<SignalInfo>();
            int barIdx = 0;
            foreach (var line in log)
            {
                if (line.Contains("[DEEP6 Scorer] bar="))
                {
                    var m = System.Text.RegularExpressions.Regex.Match(line, @"bar=(\d+)");
                    if (m.Success) barIdx = int.Parse(m.Groups[1].Value);
                }
                var sm = System.Text.RegularExpressions.Regex.Match(line, @"\[DEEP6 Registry\] ([\w-]+) dir=([+-]?\d+) str=(\d+\.?\d*)");
                if (sm.Success)
                {
                    string id = sm.Groups[1].Value;
                    string family = id.Length >= 3 ? id.Substring(0, id.IndexOf('-') > 0 ? id.IndexOf('-') : System.Math.Min(4, id.Length)) : id;
                    results.Add(new SignalInfo(barIdx, id, family,
                        int.Parse(sm.Groups[2].Value),
                        double.Parse(sm.Groups[3].Value, CultureInfo.InvariantCulture)));
                }
            }
            return results;
        }

        private static List<EntryInfo> ParseEntries(IReadOnlyList<string> log)
        {
            var results = new List<EntryInfo>();
            int barIdx = 0;
            foreach (var line in log)
            {
                if (line.Contains("[DEEP6 Scorer] bar="))
                {
                    var m = System.Text.RegularExpressions.Regex.Match(line, @"bar=(\d+)");
                    if (m.Success) barIdx = int.Parse(m.Groups[1].Value);
                }
                if (line.Contains("DRY-RUN entry:") || line.Contains("LIVE entry"))
                {
                    int dir = line.Contains("LONG") ? 1 : line.Contains("SHORT") ? -1 : 0;
                    results.Add(new EntryInfo(barIdx, dir, "ENTRY"));
                }
            }
            return results;
        }

        private static List<ScoreInfo> ParseScores(IReadOnlyList<string> log)
        {
            var results = new List<ScoreInfo>();
            foreach (var line in log)
            {
                var m = System.Text.RegularExpressions.Regex.Match(line,
                    @"\[DEEP6 Scorer\] bar=(\d+) score=([+-]?\d+\.?\d*) tier=(\w+) narrative=(.*)");
                if (m.Success)
                {
                    results.Add(new ScoreInfo(
                        int.Parse(m.Groups[1].Value),
                        double.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture),
                        m.Groups[3].Value,
                        m.Groups[4].Value.Trim()));
                }
            }
            return results;
        }

        // ═══════════════════════════════════════════════════════════════════
        //  Inline CSS + JS
        // ═══════════════════════════════════════════════════════════════════

        private static string CssBase() => @"
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0a0a0a; color: #f5f5f5; font-family: 'Inter', -apple-system, sans-serif; }
#header { padding: 16px 24px; border-bottom: 1px solid #1f1f1f; display: flex; align-items: baseline; gap: 16px; }
#header h1 { font-size: 16px; font-weight: 600; color: #e0e0e0; }
.meta { font-size: 12px; color: #8a8a8a; }
#chart { width: 100%; height: 500px; }
#legend { padding: 8px 24px; font-size: 11px; color: #666; }
#scores { padding: 16px 24px; }
#scores h3 { font-size: 13px; color: #8a8a8a; margin-bottom: 8px; }
#scores table { width: 100%; border-collapse: collapse; font-size: 11px; font-family: 'JetBrains Mono', monospace; }
#scores th { text-align: left; color: #666; padding: 4px 8px; border-bottom: 1px solid #1f1f1f; }
#scores td { padding: 4px 8px; border-bottom: 1px solid #111; }
.tier-a { color: #a3ff00; font-weight: 600; }
.tier-b { color: #ffd60a; }
.tier-c { color: #00d9ff; }
#score-hud { position: fixed; top: 60px; right: 24px; background: rgba(14,16,20,0.92);
  border: 1px solid #262633; border-radius: 8px; padding: 12px 16px; z-index: 100;
  font-family: 'JetBrains Mono', monospace; }
.score-value { font-size: 24px; font-weight: 700; }
.score-tier { font-size: 12px; margin-top: 2px; }
.score-narrative { font-size: 10px; color: #8a929e; margin-top: 4px; max-width: 200px; }
";

        private static string CssFootprint() => @"
#footprint-container { width: 100%; overflow-x: auto; padding: 16px; }
#fp-canvas { background: #0a0a0a; display: block; }
";

        private static string JsCandleChart() => @"
const chartEl = document.getElementById('chart');
const chart = LightweightCharts.createChart(chartEl, {
  width: chartEl.clientWidth, height: 500,
  layout: { background: { color: '#0a0a0a' }, textColor: '#8a8a8a' },
  grid: { vertLines: { color: '#111' }, horzLines: { color: '#111' } },
  crosshair: { mode: 0 },
  rightPriceScale: { borderColor: '#1f1f1f' },
  timeScale: { borderColor: '#1f1f1f', timeVisible: true },
});
const candleSeries = chart.addCandlestickSeries({
  upColor: '#00ff88', downColor: '#ff2e63',
  wickUpColor: '#00ff88', wickDownColor: '#ff2e63',
  borderVisible: false,
});
candleSeries.setData(bars);
markers.sort((a,b) => a.time - b.time);
candleSeries.setMarkers(markers);
const volSeries = chart.addHistogramSeries({
  priceFormat: { type: 'volume' },
  priceScaleId: 'vol', scaleMargins: { top: 0.8, bottom: 0 },
});
volSeries.setData(volumes);
chart.timeScale().fitContent();
window.addEventListener('resize', () => chart.applyOptions({ width: chartEl.clientWidth }));
document.getElementById('legend').textContent = `${bars.length} bars | ${markers.length} markers | Lightweight Charts v4.2`;
";

        private static string JsFootprintChart() => @"
const canvas = document.getElementById('fp-canvas');
const ctx = canvas.getContext('2d');

const COL_W = 80;
const ROW_H = 18;
const HEADER_H = 24;
const PADDING = 40;

// Colors matching dashboard palette
const C_BID = '#ff2e63';
const C_ASK = '#00ff88';
const C_POC = '#ffd60a';
const C_RULE = '#1f1f1f';
const C_TEXT = '#f5f5f5';
const C_DIM = '#8a8a8a';
const C_MUTE = '#4a4a4a';
const C_BG = '#0a0a0a';
const C_CELL_BG = '#0f0f0f';

// Compute price range across all bars
let globalHigh = -Infinity, globalLow = Infinity;
fpBars.forEach(b => { if (b.h > globalHigh) globalHigh = b.h; if (b.l < globalLow) globalLow = b.l; });
globalHigh += TICK_SIZE * 2;
globalLow -= TICK_SIZE * 2;

const priceRows = Math.ceil((globalHigh - globalLow) / TICK_SIZE) + 1;
const chartW = fpBars.length * COL_W + PADDING * 2;
const chartH = priceRows * ROW_H + HEADER_H + PADDING;

canvas.width = Math.max(chartW, window.innerWidth);
canvas.height = chartH;
canvas.style.width = canvas.width + 'px';
canvas.style.height = chartH + 'px';

function priceToY(price) {
  return HEADER_H + (globalHigh - price) / TICK_SIZE * ROW_H;
}

// Background
ctx.fillStyle = C_BG;
ctx.fillRect(0, 0, canvas.width, canvas.height);

// Price labels (right side)
ctx.font = '10px ""JetBrains Mono"", monospace';
ctx.textAlign = 'right';
ctx.fillStyle = C_DIM;
for (let p = globalLow; p <= globalHigh; p += TICK_SIZE * 4) {
  const y = priceToY(p);
  ctx.fillText(p.toFixed(2), PADDING - 4, y + 4);
  ctx.strokeStyle = C_RULE;
  ctx.lineWidth = 0.5;
  ctx.beginPath(); ctx.moveTo(PADDING, y); ctx.lineTo(canvas.width, y); ctx.stroke();
}

// Render each bar as a column
fpBars.forEach((bar, i) => {
  const x = PADDING + i * COL_W;

  // Time header
  const date = new Date(bar.ts * 1000);
  const timeStr = date.toTimeString().slice(0, 5);
  ctx.font = '10px ""JetBrains Mono"", monospace';
  ctx.textAlign = 'center';
  ctx.fillStyle = C_DIM;
  ctx.fillText(timeStr, x + COL_W / 2, 16);

  // Column separator
  ctx.strokeStyle = C_RULE;
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(x, HEADER_H); ctx.lineTo(x, chartH); ctx.stroke();

  // Find POC (highest volume level)
  let pocPrice = bar.c, pocVol = 0;
  const levelKeys = Object.keys(bar.levels);
  levelKeys.forEach(px => {
    const [bid, ask] = bar.levels[px];
    const total = bid + ask;
    if (total > pocVol) { pocVol = total; pocPrice = parseFloat(px); }
  });

  // Find max volume for alpha scaling
  let maxVol = 1;
  levelKeys.forEach(px => {
    const [bid, ask] = bar.levels[px];
    if (bid + ask > maxVol) maxVol = bid + ask;
  });

  // Render cells
  levelKeys.forEach(px => {
    const price = parseFloat(px);
    const [bid, ask] = bar.levels[px];
    const y = priceToY(price);
    const total = bid + ask;
    const alpha = Math.max(0.15, Math.min(0.9, total / maxVol));

    // Cell background
    const isPoc = Math.abs(price - pocPrice) < TICK_SIZE * 0.5;
    ctx.fillStyle = isPoc ? 'rgba(255,214,10,0.12)' : C_CELL_BG;
    ctx.fillRect(x + 1, y - ROW_H / 2, COL_W - 2, ROW_H);

    // Bid × Ask text
    const halfW = (COL_W - 8) / 2;
    ctx.font = '11px ""JetBrains Mono"", monospace';

    // Bid (left, red)
    const bidAlpha = Math.max(0.3, bid / Math.max(total, 1));
    ctx.fillStyle = `rgba(255,46,99,${bidAlpha.toFixed(2)})`;
    ctx.textAlign = 'right';
    ctx.fillText(bid.toString(), x + halfW, y + 4);

    // Separator
    ctx.fillStyle = C_MUTE;
    ctx.textAlign = 'center';
    ctx.fillText('×', x + COL_W / 2, y + 4);

    // Ask (right, green)
    const askAlpha = Math.max(0.3, ask / Math.max(total, 1));
    ctx.fillStyle = `rgba(0,255,136,${askAlpha.toFixed(2)})`;
    ctx.textAlign = 'left';
    ctx.fillText(ask.toString(), x + COL_W / 2 + 8, y + 4);

    // POC marker (amber dot)
    if (isPoc) {
      ctx.fillStyle = C_POC;
      ctx.fillRect(x + 2, y - 2, 4, 4);
    }

    // Imbalance highlight (2.5x ratio)
    if (ask > 0 && bid > 0) {
      if (ask / bid >= 2.5) {
        ctx.strokeStyle = C_ASK;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(x + 2, y - ROW_H / 2 + 1, COL_W - 4, ROW_H - 2);
      } else if (bid / ask >= 2.5) {
        ctx.strokeStyle = C_BID;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(x + 2, y - ROW_H / 2 + 1, COL_W - 4, ROW_H - 2);
      }
    }
  });

  // OHLC range indicator (thin line on right edge)
  const yHigh = priceToY(bar.h);
  const yLow = priceToY(bar.l);
  const yOpen = priceToY(bar.o);
  const yClose = priceToY(bar.c);
  const bullish = bar.c >= bar.o;
  ctx.strokeStyle = bullish ? C_ASK : C_BID;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(x + COL_W - 4, yHigh);
  ctx.lineTo(x + COL_W - 4, yLow);
  ctx.stroke();
});

// Signal markers
fpSignals.forEach(sig => {
  const x = PADDING + sig.bar * COL_W + COL_W / 2;
  const bar = fpBars[sig.bar];
  if (!bar) return;
  const y = sig.dir > 0 ? priceToY(bar.l) + 20 : priceToY(bar.h) - 20;
  const color = sig.family === 'ABS' ? (sig.dir > 0 ? '#00ff88' : '#ff2e63')
              : sig.family === 'EXH' ? (sig.dir > 0 ? '#ffd60a' : '#ff6b35')
              : '#00d9ff';

  // Triangle
  ctx.fillStyle = color;
  ctx.beginPath();
  if (sig.dir > 0) {
    ctx.moveTo(x, y); ctx.lineTo(x - 5, y + 8); ctx.lineTo(x + 5, y + 8);
  } else {
    ctx.moveTo(x, y); ctx.lineTo(x - 5, y - 8); ctx.lineTo(x + 5, y - 8);
  }
  ctx.fill();

  // Label
  ctx.font = '9px ""JetBrains Mono"", monospace';
  ctx.textAlign = 'center';
  ctx.fillStyle = color;
  ctx.fillText(sig.id, x, sig.dir > 0 ? y + 20 : y - 12);
});
";
    }
}
