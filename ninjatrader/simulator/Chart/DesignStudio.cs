// DesignStudio: Generates a self-contained HTML design workbench for
// tuning footprint chart visual parameters in real-time.
//
// Features:
//   - Live preview canvas with footprint cells from session data
//   - Control panel with color pickers, sliders, font selectors
//   - Instant re-render on any parameter change
//   - Export current theme as JSON
//   - Export NT8 Color.FromArgb() C# code for DEEP6Footprint.cs
//   - Before/after split-view comparison
//
// Usage:
//   dotnet run --project ninjatrader/simulator -- design --dir sessions/

using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

namespace NinjaScriptSim.Lifecycle
{
    public static class DesignStudio
    {
        public static void Export(SessionData session, string outputPath, double tickSize = 0.25)
        {
            var sb = new StringBuilder();
            sb.AppendLine("<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>");
            sb.AppendLine("<title>DEEP6 Design Studio</title>");
            sb.AppendLine("<style>");
            sb.AppendLine(Css());
            sb.AppendLine("</style></head><body>");

            // Header
            sb.AppendLine("<div id='toolbar'>");
            sb.AppendLine("<h1>DEEP6 Design Studio</h1>");
            sb.AppendLine("<div class='toolbar-actions'>");
            sb.AppendLine("<button onclick='exportThemeJson()'>Export JSON Theme</button>");
            sb.AppendLine("<button onclick='exportNt8Code()'>Export NT8 C# Code</button>");
            sb.AppendLine("<button onclick='resetDefaults()'>Reset Defaults</button>");
            sb.AppendLine("<button onclick='toggleSplit()'>Split View</button>");
            sb.AppendLine("</div></div>");

            // Main layout: controls left, canvas right
            sb.AppendLine("<div id='main'>");
            sb.AppendLine("<div id='controls'>");
            sb.AppendLine(ControlPanel());
            sb.AppendLine("</div>");
            sb.AppendLine("<div id='canvas-wrap'>");
            sb.AppendLine("<canvas id='fp'></canvas>");
            sb.AppendLine("<canvas id='fp-compare' style='display:none'></canvas>");
            sb.AppendLine("</div></div>");

            // Export modal
            sb.AppendLine("<div id='modal' style='display:none'><div id='modal-inner'>");
            sb.AppendLine("<button onclick='closeModal()' class='modal-close'>X</button>");
            sb.AppendLine("<pre id='modal-content'></pre>");
            sb.AppendLine("<button onclick='copyModal()'>Copy to Clipboard</button>");
            sb.AppendLine("</div></div>");

            // Bar data
            sb.AppendLine("<script>");
            sb.AppendLine("const fpBars = [");
            foreach (var bar in session.Bars.Take(30)) // Limit to 30 bars for responsive UI
            {
                long ts = new DateTimeOffset(bar.Time).ToUnixTimeSeconds();
                sb.Append(string.Format(CultureInfo.InvariantCulture,
                    "{{ts:{0},o:{1},h:{2},l:{3},c:{4},vol:{5},levels:{{", ts, bar.Open, bar.High, bar.Low, bar.Close, bar.Volume));
                if (bar.Ticks != null)
                {
                    var levels = new System.Collections.Generic.SortedDictionary<double, (long bid, long ask)>();
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
                        sb.Append(string.Format(CultureInfo.InvariantCulture, "'{0}':[{1},{2}]", kv.Key, kv.Value.bid, kv.Value.ask));
                        first = false;
                    }
                }
                sb.AppendLine("}},");
            }
            sb.AppendLine("];");
            sb.AppendLine($"const TICK_SIZE = {tickSize.ToString(CultureInfo.InvariantCulture)};");

            // Main JS
            sb.AppendLine(MainJs());
            sb.AppendLine("</script></body></html>");

            File.WriteAllText(outputPath, sb.ToString());
        }

        private static string Css() => @"
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#0a0a0a; color:#f5f5f5; font-family:'Inter',-apple-system,sans-serif; overflow:hidden; height:100vh; }
#toolbar { height:48px; background:#111; border-bottom:1px solid #1f1f1f; display:flex; align-items:center; justify-content:space-between; padding:0 16px; }
#toolbar h1 { font-size:14px; font-weight:600; color:#e0e0e0; }
.toolbar-actions { display:flex; gap:8px; }
.toolbar-actions button { background:#1a1a2e; color:#a3ff00; border:1px solid #2a2a3e; border-radius:4px; padding:6px 12px; font-size:11px; cursor:pointer; }
.toolbar-actions button:hover { background:#2a2a3e; }
#main { display:flex; height:calc(100vh - 48px); }
#controls { width:280px; background:#0f0f0f; border-right:1px solid #1f1f1f; overflow-y:auto; padding:12px; flex-shrink:0; }
#canvas-wrap { flex:1; overflow:auto; padding:8px; display:flex; gap:8px; }
canvas { background:#0a0a0a; display:block; }
.section { margin-bottom:16px; }
.section h3 { font-size:11px; color:#666; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px; border-bottom:1px solid #1a1a1a; padding-bottom:4px; }
.ctrl { display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; }
.ctrl label { font-size:11px; color:#999; flex:1; }
.ctrl input[type='color'] { width:32px; height:24px; border:1px solid #333; border-radius:3px; background:transparent; cursor:pointer; }
.ctrl input[type='range'] { width:100px; accent-color:#a3ff00; }
.ctrl input[type='number'] { width:56px; background:#1a1a1a; border:1px solid #333; color:#f5f5f5; border-radius:3px; padding:2px 4px; font-size:11px; text-align:right; }
.ctrl select { background:#1a1a1a; border:1px solid #333; color:#f5f5f5; border-radius:3px; padding:2px 4px; font-size:11px; }
.ctrl .val { font-size:10px; color:#666; width:32px; text-align:right; font-family:'JetBrains Mono',monospace; }
#modal { position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.8); display:flex; align-items:center; justify-content:center; z-index:1000; }
#modal-inner { background:#111; border:1px solid #333; border-radius:8px; padding:16px; max-width:700px; width:90%; max-height:80vh; overflow:auto; position:relative; }
#modal-inner pre { font-size:11px; font-family:'JetBrains Mono',monospace; color:#a3ff00; white-space:pre-wrap; line-height:1.6; }
.modal-close { position:absolute; top:8px; right:8px; background:none; border:none; color:#666; font-size:16px; cursor:pointer; }
";

        private static string ControlPanel() => @"
<div class='section'><h3>Cell Colors</h3>
  <div class='ctrl'><label>Bid (sellers)</label><input type='color' id='c_bid' value='#ff2e63' oninput='render()'></div>
  <div class='ctrl'><label>Ask (buyers)</label><input type='color' id='c_ask' value='#00ff88' oninput='render()'></div>
  <div class='ctrl'><label>POC highlight</label><input type='color' id='c_poc' value='#ffd60a' oninput='render()'></div>
  <div class='ctrl'><label>Grid lines</label><input type='color' id='c_grid' value='#1f1f1f' oninput='render()'></div>
  <div class='ctrl'><label>Background</label><input type='color' id='c_bg' value='#0a0a0a' oninput='render()'></div>
  <div class='ctrl'><label>Cell background</label><input type='color' id='c_cellbg' value='#0f0f0f' oninput='render()'></div>
  <div class='ctrl'><label>Text primary</label><input type='color' id='c_text' value='#f5f5f5' oninput='render()'></div>
  <div class='ctrl'><label>Text dim</label><input type='color' id='c_dim' value='#8a8a8a' oninput='render()'></div>
  <div class='ctrl'><label>Text mute</label><input type='color' id='c_mute' value='#4a4a4a' oninput='render()'></div>
</div>
<div class='section'><h3>Signal Colors</h3>
  <div class='ctrl'><label>ABS bullish</label><input type='color' id='c_abs_bull' value='#00ff88' oninput='render()'></div>
  <div class='ctrl'><label>ABS bearish</label><input type='color' id='c_abs_bear' value='#ff2e63' oninput='render()'></div>
  <div class='ctrl'><label>EXH bullish</label><input type='color' id='c_exh_bull' value='#ffd60a' oninput='render()'></div>
  <div class='ctrl'><label>EXH bearish</label><input type='color' id='c_exh_bear' value='#ff6b35' oninput='render()'></div>
  <div class='ctrl'><label>Other signals</label><input type='color' id='c_sig_other' value='#00d9ff' oninput='render()'></div>
  <div class='ctrl'><label>Tier A</label><input type='color' id='c_tier_a' value='#a3ff00' oninput='render()'></div>
  <div class='ctrl'><label>Tier B</label><input type='color' id='c_tier_b' value='#ffd60a' oninput='render()'></div>
  <div class='ctrl'><label>Tier C</label><input type='color' id='c_tier_c' value='#00d9ff' oninput='render()'></div>
</div>
<div class='section'><h3>Imbalance</h3>
  <div class='ctrl'><label>Imbalance buy</label><input type='color' id='c_imb_buy' value='#00c850' oninput='render()'></div>
  <div class='ctrl'><label>Imbalance sell</label><input type='color' id='c_imb_sell' value='#dc2828' oninput='render()'></div>
  <div class='ctrl'><label>Threshold</label><input type='range' id='imb_thresh' min='1.5' max='5' step='0.1' value='2.5' oninput='render()'><span class='val' id='imb_thresh_val'>2.5</span></div>
</div>
<div class='section'><h3>Geometry</h3>
  <div class='ctrl'><label>Column width</label><input type='range' id='col_w' min='40' max='140' step='5' value='80' oninput='render()'><span class='val' id='col_w_val'>80</span></div>
  <div class='ctrl'><label>Row height</label><input type='range' id='row_h' min='10' max='30' step='1' value='18' oninput='render()'><span class='val' id='row_h_val'>18</span></div>
  <div class='ctrl'><label>Font size</label><input type='range' id='font_sz' min='8' max='16' step='1' value='11' oninput='render()'><span class='val' id='font_sz_val'>11</span></div>
  <div class='ctrl'><label>POC dot size</label><input type='range' id='poc_dot' min='2' max='8' step='1' value='4' oninput='render()'><span class='val' id='poc_dot_val'>4</span></div>
  <div class='ctrl'><label>Imbalance border</label><input type='range' id='imb_border' min='0.5' max='3' step='0.5' value='1.5' oninput='render()'><span class='val' id='imb_border_val'>1.5</span></div>
</div>
<div class='section'><h3>Font</h3>
  <div class='ctrl'><label>Family</label><select id='font_family' onchange='render()'>
    <option value='JetBrains Mono'>JetBrains Mono</option>
    <option value='Consolas'>Consolas</option>
    <option value='SF Mono'>SF Mono</option>
    <option value='Fira Code'>Fira Code</option>
    <option value='monospace'>System monospace</option>
  </select></div>
</div>
<div class='section'><h3>Opacity</h3>
  <div class='ctrl'><label>Min cell alpha</label><input type='range' id='alpha_min' min='0.05' max='0.5' step='0.05' value='0.15' oninput='render()'><span class='val' id='alpha_min_val'>0.15</span></div>
  <div class='ctrl'><label>Max cell alpha</label><input type='range' id='alpha_max' min='0.5' max='1.0' step='0.05' value='0.9' oninput='render()'><span class='val' id='alpha_max_val'>0.9</span></div>
  <div class='ctrl'><label>POC row alpha</label><input type='range' id='poc_alpha' min='0.05' max='0.3' step='0.01' value='0.12' oninput='render()'><span class='val' id='poc_alpha_val'>0.12</span></div>
</div>
<div class='section'><h3>Display</h3>
  <div class='ctrl'><label>Show POC dots</label><input type='checkbox' id='show_poc' checked onchange='render()'></div>
  <div class='ctrl'><label>Show imbalance</label><input type='checkbox' id='show_imb' checked onchange='render()'></div>
  <div class='ctrl'><label>Show OHLC bar</label><input type='checkbox' id='show_ohlc' checked onchange='render()'></div>
  <div class='ctrl'><label>Show grid</label><input type='checkbox' id='show_grid' checked onchange='render()'></div>
  <div class='ctrl'><label>Show time header</label><input type='checkbox' id='show_time' checked onchange='render()'></div>
  <div class='ctrl'><label>Show price labels</label><input type='checkbox' id='show_price' checked onchange='render()'></div>
  <div class='ctrl'><label>Cell text mode</label><select id='text_mode' onchange='render()'>
    <option value='bidxask'>bid x ask</option>
    <option value='delta'>delta only</option>
    <option value='total'>total only</option>
    <option value='none'>color only</option>
  </select></div>
</div>
";

        private static string MainJs() => @"
// ── Theme state ──
function getTheme() {
  const g = id => document.getElementById(id);
  const v = id => g(id).value;
  const n = id => parseFloat(v(id));
  const b = id => g(id).checked;
  return {
    bid: v('c_bid'), ask: v('c_ask'), poc: v('c_poc'), grid: v('c_grid'),
    bg: v('c_bg'), cellBg: v('c_cellbg'), text: v('c_text'), dim: v('c_dim'), mute: v('c_mute'),
    absBull: v('c_abs_bull'), absBear: v('c_abs_bear'),
    exhBull: v('c_exh_bull'), exhBear: v('c_exh_bear'), sigOther: v('c_sig_other'),
    tierA: v('c_tier_a'), tierB: v('c_tier_b'), tierC: v('c_tier_c'),
    imbBuy: v('c_imb_buy'), imbSell: v('c_imb_sell'), imbThreshold: n('imb_thresh'),
    colW: n('col_w'), rowH: n('row_h'), fontSize: n('font_sz'),
    pocDot: n('poc_dot'), imbBorder: n('imb_border'),
    fontFamily: v('font_family'),
    alphaMin: n('alpha_min'), alphaMax: n('alpha_max'), pocAlpha: n('poc_alpha'),
    showPoc: b('show_poc'), showImb: b('show_imb'), showOhlc: b('show_ohlc'),
    showGrid: b('show_grid'), showTime: b('show_time'), showPrice: b('show_price'),
    textMode: v('text_mode'),
  };
}

let savedTheme = null; // for split-view comparison
let splitMode = false;

// ── Update value labels ──
function updateLabels() {
  ['imb_thresh','col_w','row_h','font_sz','poc_dot','imb_border','alpha_min','alpha_max','poc_alpha'].forEach(id => {
    const el = document.getElementById(id + '_val');
    if (el) el.textContent = document.getElementById(id).value;
  });
}

// ── Render ──
function render() {
  updateLabels();
  const t = getTheme();
  renderCanvas('fp', t);
  if (splitMode && savedTheme) renderCanvas('fp-compare', savedTheme);
}

function renderCanvas(canvasId, t) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext('2d');
  const HEADER_H = t.showTime ? 24 : 0;
  const PADDING = t.showPrice ? 50 : 10;

  let gHi = -Infinity, gLo = Infinity;
  fpBars.forEach(b => { if (b.h > gHi) gHi = b.h; if (b.l < gLo) gLo = b.l; });
  gHi += TICK_SIZE * 2; gLo -= TICK_SIZE * 2;

  const priceRows = Math.ceil((gHi - gLo) / TICK_SIZE) + 1;
  const cW = fpBars.length * t.colW + PADDING * 2;
  const cH = priceRows * t.rowH + HEADER_H + 40;
  canvas.width = Math.max(cW, 600); canvas.height = cH;
  canvas.style.width = canvas.width + 'px'; canvas.style.height = cH + 'px';

  const py = price => HEADER_H + (gHi - price) / TICK_SIZE * t.rowH;

  // Background
  ctx.fillStyle = t.bg; ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Price grid
  if (t.showGrid) {
    ctx.font = `10px ""${t.fontFamily}"", monospace`;
    for (let p = gLo; p <= gHi; p += TICK_SIZE * 4) {
      const y = py(p);
      if (t.showPrice) { ctx.fillStyle = t.dim; ctx.textAlign = 'right'; ctx.fillText(p.toFixed(2), PADDING - 4, y + 4); }
      ctx.strokeStyle = t.grid; ctx.lineWidth = 0.5;
      ctx.beginPath(); ctx.moveTo(PADDING, y); ctx.lineTo(canvas.width, y); ctx.stroke();
    }
  }

  // Bars
  fpBars.forEach((bar, i) => {
    const x = PADDING + i * t.colW;

    // Time header
    if (t.showTime) {
      const d = new Date(bar.ts * 1000);
      ctx.font = `10px ""${t.fontFamily}"", monospace`;
      ctx.textAlign = 'center'; ctx.fillStyle = t.dim;
      ctx.fillText(d.toTimeString().slice(0,5), x + t.colW/2, 16);
    }

    // Column line
    if (t.showGrid) {
      ctx.strokeStyle = t.grid; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, HEADER_H); ctx.lineTo(x, cH); ctx.stroke();
    }

    // POC
    let pocPx = bar.c, pocVol = 0;
    const keys = Object.keys(bar.levels);
    let maxVol = 1;
    keys.forEach(px => { const [b,a] = bar.levels[px]; const tot = b+a; if(tot>pocVol){pocVol=tot;pocPx=parseFloat(px);} if(tot>maxVol)maxVol=tot; });

    // Cells
    keys.forEach(px => {
      const price = parseFloat(px);
      const [bid, ask] = bar.levels[px];
      const y = py(price);
      const total = bid + ask;
      const alpha = Math.max(t.alphaMin, Math.min(t.alphaMax, total / maxVol));
      const isPoc = Math.abs(price - pocPx) < TICK_SIZE * 0.5;

      // Cell bg
      if (isPoc) { ctx.fillStyle = hexAlpha(t.poc, t.pocAlpha); }
      else { ctx.fillStyle = t.cellBg; }
      ctx.fillRect(x+1, y - t.rowH/2, t.colW-2, t.rowH);

      // Text
      if (t.textMode !== 'none' && t.rowH >= 14) {
        const halfW = (t.colW - 8) / 2;
        ctx.font = `${t.fontSize}px ""${t.fontFamily}"", monospace`;

        if (t.textMode === 'bidxask') {
          ctx.fillStyle = hexAlpha(t.bid, Math.max(0.3, bid/Math.max(total,1)));
          ctx.textAlign = 'right'; ctx.fillText(bid.toString(), x + halfW, y + 4);
          ctx.fillStyle = t.mute; ctx.textAlign = 'center'; ctx.fillText('x', x + t.colW/2, y + 4);
          ctx.fillStyle = hexAlpha(t.ask, Math.max(0.3, ask/Math.max(total,1)));
          ctx.textAlign = 'left'; ctx.fillText(ask.toString(), x + t.colW/2 + 8, y + 4);
        } else if (t.textMode === 'delta') {
          const d = ask - bid;
          ctx.fillStyle = d >= 0 ? hexAlpha(t.ask, alpha) : hexAlpha(t.bid, alpha);
          ctx.textAlign = 'center'; ctx.fillText((d>=0?'+':'')+d, x + t.colW/2, y + 4);
        } else if (t.textMode === 'total') {
          ctx.fillStyle = hexAlpha(t.text, alpha);
          ctx.textAlign = 'center'; ctx.fillText(total.toString(), x + t.colW/2, y + 4);
        }
      }

      // POC dot
      if (isPoc && t.showPoc) { ctx.fillStyle = t.poc; ctx.fillRect(x+2, y-t.pocDot/2, t.pocDot, t.pocDot); }

      // Imbalance
      if (t.showImb && bid > 0 && ask > 0) {
        if (ask/bid >= t.imbThreshold) { ctx.strokeStyle = t.imbBuy; ctx.lineWidth = t.imbBorder; ctx.strokeRect(x+2, y-t.rowH/2+1, t.colW-4, t.rowH-2); }
        else if (bid/ask >= t.imbThreshold) { ctx.strokeStyle = t.imbSell; ctx.lineWidth = t.imbBorder; ctx.strokeRect(x+2, y-t.rowH/2+1, t.colW-4, t.rowH-2); }
      }
    });

    // OHLC bar
    if (t.showOhlc) {
      ctx.strokeStyle = bar.c >= bar.o ? t.ask : t.bid;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(x+t.colW-4, py(bar.h)); ctx.lineTo(x+t.colW-4, py(bar.l)); ctx.stroke();
    }
  });
}

function hexAlpha(hex, alpha) {
  const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
  return `rgba(${r},${g},${b},${alpha.toFixed(2)})`;
}

// ── Export theme as JSON ──
function exportThemeJson() {
  const t = getTheme();
  document.getElementById('modal-content').textContent = JSON.stringify(t, null, 2);
  document.getElementById('modal').style.display = 'flex';
}

// ── Export as NT8 C# Color.FromArgb ──
function exportNt8Code() {
  const t = getTheme();
  const hex2argb = (hex, alpha=255) => {
    const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
    return `Color.FromArgb(${alpha}, 0x${r.toString(16).padStart(2,'0').toUpperCase()}, 0x${g.toString(16).padStart(2,'0').toUpperCase()}, 0x${b.toString(16).padStart(2,'0').toUpperCase()})`;
  };
  const lines = [
    '// DEEP6 Footprint Theme — generated by Design Studio',
    '// Paste into DEEP6Footprint.cs OnStateChange → SetDefaults',
    '',
    `BidCellBrush      = MakeFrozenBrush(${hex2argb(t.bid)});`,
    `AskCellBrush      = MakeFrozenBrush(${hex2argb(t.ask)});`,
    `CellTextBrush     = MakeFrozenBrush(${hex2argb(t.text)});`,
    `PocBrush          = MakeFrozenBrush(${hex2argb(t.poc)});`,
    `VahBrush          = MakeFrozenBrush(${hex2argb(t.poc)});  // same hue family`,
    `ValBrush          = MakeFrozenBrush(${hex2argb(t.poc)});`,
    `ImbalanceBuyBrush = MakeFrozenBrush(${hex2argb(t.imbBuy, 110)});`,
    `ImbalanceSellBrush= MakeFrozenBrush(${hex2argb(t.imbSell, 110)});`,
    '',
    `// Geometry`,
    `CellFontSize      = ${t.fontSize}f;`,
    `CellColumnWidth   = ${t.colW};`,
    `ImbalanceRatio    = ${t.imbThreshold};`,
    '',
    `// Signal tier colors (for OnRenderTargetChanged)`,
    `// Tier A: ${hex2argb(t.tierA)}`,
    `// Tier B: ${hex2argb(t.tierB)}`,
    `// Tier C: ${hex2argb(t.tierC)}`,
  ];
  document.getElementById('modal-content').textContent = lines.join('\n');
  document.getElementById('modal').style.display = 'flex';
}

function closeModal() { document.getElementById('modal').style.display = 'none'; }
function copyModal() {
  navigator.clipboard.writeText(document.getElementById('modal-content').textContent);
  document.querySelector('#modal-inner button:last-child').textContent = 'Copied!';
  setTimeout(() => document.querySelector('#modal-inner button:last-child').textContent = 'Copy to Clipboard', 2000);
}

function toggleSplit() {
  splitMode = !splitMode;
  const comp = document.getElementById('fp-compare');
  if (splitMode) { savedTheme = getTheme(); comp.style.display = 'block'; }
  else { comp.style.display = 'none'; }
  render();
}

function resetDefaults() {
  const defaults = {c_bid:'#ff2e63',c_ask:'#00ff88',c_poc:'#ffd60a',c_grid:'#1f1f1f',c_bg:'#0a0a0a',c_cellbg:'#0f0f0f',c_text:'#f5f5f5',c_dim:'#8a8a8a',c_mute:'#4a4a4a',c_abs_bull:'#00ff88',c_abs_bear:'#ff2e63',c_exh_bull:'#ffd60a',c_exh_bear:'#ff6b35',c_sig_other:'#00d9ff',c_tier_a:'#a3ff00',c_tier_b:'#ffd60a',c_tier_c:'#00d9ff',c_imb_buy:'#00c850',c_imb_sell:'#dc2828'};
  Object.entries(defaults).forEach(([id,v]) => { const el=document.getElementById(id); if(el) el.value=v; });
  document.getElementById('imb_thresh').value = 2.5;
  document.getElementById('col_w').value = 80;
  document.getElementById('row_h').value = 18;
  document.getElementById('font_sz').value = 11;
  document.getElementById('poc_dot').value = 4;
  document.getElementById('imb_border').value = 1.5;
  document.getElementById('alpha_min').value = 0.15;
  document.getElementById('alpha_max').value = 0.9;
  document.getElementById('poc_alpha').value = 0.12;
  render();
}

// Initial render
render();
";
    }
}
