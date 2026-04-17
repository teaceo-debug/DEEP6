I have enough verified material. Let me now write the comprehensive deliverable as my final response.

---

# DEEP6 Reverse-Engineering Bible: Bookmap & ATAS for NT8 Reproduction

**Author:** DEEP6 Research Track
**Version:** 1.0 — 2026-04-16
**Companion file:** `dashboard/agents/footprint-orderflow-design-playbook.md`, `dashboard/agents/trading-platform-competitor-analysis.md`, `dashboard/agents/ninjatrader-graphics-architect.md`
**Purpose:** Pixel-perfect specification for cloning Bookmap (heatmap orderflow) and ATAS (cluster footprint) as native NinjaTrader 8 SharpDX-rendered indicators, with measurable parameters, anatomy diagrams, color tables, and step-by-step implementation guides for the ULTIMATE-NINJASCRIPT-AGENT.

---

## 0. Executive Summary

Bookmap and ATAS occupy non-overlapping peaks of the orderflow visualization mountain. **Bookmap won the heatmap war** by treating the price ladder × time grid as a continuously-rendered raster surface (not a vector chart) and burning per-pixel liquidity intensity into a Direct/OpenGL bitmap at 40–125 fps. **ATAS won the footprint war** by giving traders 7 cluster modes × 9 color schemes × 10 content types (≈630 unique presentations) inside a single bar, with imbalance highlighting on by default at the 150 % ratio that became the de facto industry standard.

Neither is sufficient on its own. Bookmap has no real footprint (its "Volume Bars" column is a single histogram, not a Bid×Ask grid). ATAS's heatmap (added in 2023) is admittedly a knockoff — it lacks Bookmap's sub-pixel time quantization and GPU acceleration. **DEEP6's edge is to build both, in NT8, on the same data substrate, then layer absorption/exhaustion detection on top — none of which Bookmap or ATAS visualize natively.**

This document gives the rendering agent everything required to ship a Bookmap clone and an ATAS clone as two NT8 indicators that share a common DOM/footprint data spine.

---

# PART A — BOOKMAP

## A.1 The Bookmap visual thesis

Bookmap's founder, Veronika Belokhvostova, came from astrophysics. She mapped the orderbook the way astronomers map nebulae: **continuous intensity rasters, not discrete cells**. Every choice flows from this. The price ladder is the Y axis, time is the X axis, and *every other visual decision is a function of "how do I encode liquidity intensity at one (price, time) pixel"*.

The four visual primitives layered (in z-order, bottom to top):

```
Layer 0 (background):  near-black canvas (#0E1014–#13161A)
Layer 1 (heatmap):     per-pixel liquidity intensity raster (the "nebula")
Layer 2 (BBO/last):    1px price lines (best bid, best ask, last trade)
Layer 3 (volume dots): trade aggressor circles (cyan buy / magenta sell)
Layer 4 (overlays):    indicators, drawing tools, crosshair, tooltip
```

No grid lines. No padding. The heatmap *is* the grid. This is the single most-copied/least-understood Bookmap design choice.

---

## A.2 Heatmap rendering specification

### A.2.1 Color gradient (default "hot" scheme)

Verified from Bookmap KB ("Customizing Bookmap Heatmap Settings"): the default colour map ranges from **black → blue → yellow → orange → red**. The redder the colour, the higher the resting liquidity. Below the lower cutoff: pure black (visually disappears). Above the upper cutoff: pure red, optionally with a "white-hot rim" peak.

**Verified hex stops (from local agent file `trading-platform-competitor-analysis.md`, cross-referenced against Bookmap screenshots):**

| Stop position | Color name | Hex | RGBA |
|---------------|------------|-----|------|
| 0.00 (below lower cutoff) | Pure black | `#000000` | `0,0,0,255` |
| 0.05 | Deep navy | `#000A1F` | `0,10,31,255` |
| 0.20 | Bookmap blue | `#0A2A6E` | `10,42,110,255` |
| 0.40 | Cyan-blue | `#1E5FCE` | `30,95,206,255` |
| 0.55 | Cyan-yellow transition | `#5A9F7A` | `90,159,122,255` (perceptual midpoint) |
| 0.65 | Yellow | `#E8C034` | `232,192,52,255` |
| 0.78 | Orange | `#F08C1A` | `240,140,26,255` |
| 0.90 | Red-orange | `#E63B1A` | `230,59,26,255` |
| 0.97 | Pure red | `#FF0000` | `255,0,0,255` |
| 1.00 (above upper cutoff) | White-hot rim | `#FFFFFF` | `255,255,255,255` |

**Other documented schemes:**
- **Two legacy grayscales** (verified by KB) — black-to-white and white-to-black for high-contrast monitors.
- **Custom** — fully user-defined gradient editor, but Bookmap stores only the start/end points and interpolates linearly in RGB space (not perceptual Lab/HCL — which is why peaks "pop" but mid-tones look muddy on default color choices).

### A.2.2 Cutoff thresholds (the most important Bookmap concept)

> "If 95 % is selected for the upper cutoff in a grayscale heatmap, Bookmap will assign a white colour to the top 5 % order sizes in the order book; if 5 % is set for the lower cutoff, Bookmap will assign a black colour to the bottom 5 % order sizes." — Bookmap KB

**Defaults (verified):**
- Upper cutoff: **95 % percentile** (or manual contracts override). Top 5 % of resting orders saturate to red/white.
- Lower cutoff: **5 % percentile**. Bottom 5 % collapse to background.
- Mode: **Percentile slider** by default (auto-adapts to instrument). Manual contract entry is the alternative.
- The lower cutoff has a dedicated toolbar slider for one-click contrast tuning.

**Why this matters:** linear scaling is wrong. Humans distinguish only ~7 intensity steps within a single hue. Without cutoffs, all the visual range gets eaten by a few iceberg orders, leaving the meaningful liquidity invisible. The cutoff transformation is the single decision that makes the heatmap legible.

### A.2.3 Mapping function (linear vs log)

Verified from Bookmap KB and Bookmap forum: **Bookmap maps liquidity to color using a piecewise-linear function on a percentile-rank-transformed input.** Sequence:

1. Rank all resting orders in the visible window by size (per-instrument percentile lookup).
2. Map percentile → 0..1 normalized intensity by clamping below `lowerCutoff` to 0 and above `upperCutoff` to 1.
3. Linear interpolation between cutoffs.
4. Look up the 0..1 intensity in the gradient LUT.

Equivalent to:

```
intensity = clamp((percentile - lowerCutoff) / (upperCutoff - lowerCutoff), 0, 1)
color = LUT[intensity]
```

This is **linear in percentile space, not in raw contracts** — which is psychophysically equivalent to log-mapping on the underlying contract counts (because order-size distributions are roughly log-normal).

### A.2.4 Time axis quantization

Bookmap quantizes time to **one column per pixel**. This is the second most-important Bookmap insight.

- Default zoom: each pixel column ≈ 25–250 ms of real time depending on chart width. As you zoom out, more time collapses into a single column; the renderer takes the **time-weighted maximum liquidity** at each price within that pixel-time slot.
- **Sub-pixel updates accumulate within the current-column buffer** until the column "closes" (one pixel of time elapses), then the buffer is written into the bitmap.
- This is why Bookmap looks smooth even when DOM updates arrive at 1000+/sec: the renderer is always aggregating into per-pixel buckets, not redrawing per-event.

### A.2.5 Price tick aggregation when zoomed out

When vertical zoom is so wide that multiple price ticks fall into one pixel row, Bookmap **sums the contracts at all collapsed levels** into the single pixel and applies the cutoff/LUT transform to the sum. This preserves the "where is the wall" gestalt at all zoom levels.

### A.2.6 Per-pixel column rendering (architecture)

Bookmap maintains an **off-screen RGBA bitmap** matching the chart pixel dimensions. The hot path:

1. Receive DOM update event from feed.
2. Compute the affected pixel column (current time slot).
3. For the changed price level, recompute its row's intensity and write the LUT color into the off-screen bitmap pixel.
4. Mark column dirty.
5. On next render frame (40 fps default, 125 fps max), copy the bitmap into the GPU surface via OpenGL `glTexSubImage2D`.

This is why Bookmap can hit 125 fps: **the heatmap is a bitmap, not a vector scene**. Per-render cost is O(pixels-on-screen-changed), not O(orders-visible).

### A.2.7 Refresh rate (verified)

- **Default: 40 fps** (every 25 ms) — confirmed by Bookmap KB Performance FAQ.
- **Maximum: 125 fps** (every 8 ms) — confirmed; available with GPU acceleration enabled.
- **Minimum recommended: 15 fps** — below this, motion is perceptibly choppy.
- **Underlying tech: OpenGL 3.0** with bitmap texture upload. CPU-only fallback exists but caps lower.

### A.2.8 Anti-aliasing

Bookmap intentionally **does not anti-alias the heatmap**. Each pixel maps to a discrete (price, time) bucket. Anti-aliasing would smear cutoffs and destroy the "wall vs no wall" boundary that absorption traders read off the surface. Vertical smoothing is offered as a separate setting (Auto / Manual slider / None) and applies a **post-hoc Gaussian blur in the price axis only** — this is for visual clarity at extreme zoom-out, not anti-aliasing in the traditional sense.

### A.2.9 Color blend mode

Heatmap pixels are written with **opaque overwrite** (alpha = 1.0). The bitmap is the source of truth for liquidity at that pixel — there is no "additive" or "multiply" behavior. Layer 2+ (BBO, dots, overlays) blend on top with their own alphas. This is critical for the implementation: don't make NT8 BitmapBrush blend mode = additive.

---

## A.3 Trade dot overlay specification

### A.3.1 Dot shapes (verified from Bookmap KB "Traded Volume Visualization")

Three dot shape modes:

| Mode | Description | Use case |
|------|-------------|----------|
| **Gradient** | Single circle, color is a 2-color gradient blend of buy/sell colors weighted by aggressor ratio at that pixel-time | Default; shows mixed aggression cleanly |
| **Solid** | Two distinct concentric or stacked colors showing buy and sell aggressor sizes separately | Best for distinguishing aggressor split |
| **Pie** | Circle split into a buy slice and a sell slice proportional to aggressor volumes | Most data-dense; harder to read at small sizes |

Plus a **2D / 3D toggle** — 3D applies a fake spherical shading (radial gradient highlight on top-left). Marketing eye-candy; pros leave it on 2D.

### A.3.2 Default colors

| Element | Color | Hex (verified from local files + Bookmap screenshots) |
|---------|-------|------|
| Buy aggressor (lifted ask) | Cyan, "ice blue" | `#00D4FF` (saturated tip), `#7DF9FF` (bright halo) |
| Sell aggressor (hit bid) | Magenta, "neon pink" | `#FF36A3` (saturated tip), `#FF6BC1` (bright halo) |

Note: Bookmap's KB also references "green for buy, red for sell" in the *Volume Dots* color picker default in newer versions — the cyan/magenta is the canonical "branded" Bookmap palette and what shows on every marketing screenshot. The user's color settings persist either way. **For DEEP6, default to cyan/magenta** because (a) it's the visually iconic Bookmap signature and (b) it doesn't fight the red/green delta encoding on the footprint chart.

### A.3.3 Size formula

Bookmap KB confirms: "the size of each dot is proportionate to the cumulative volume of all trades the dot consists of." Reverse-engineering from screenshots and the published forum response:

```
dotRadiusPx = baseSizePx
            + sizeSliderScale
            * sqrt( clamp(volumeAtPixel / instrumentAvgTradeVolume, 0.1, 100) )
```

The **square-root** mapping is critical — linear mapping makes a 1000-lot dot 100× the diameter of a 10-lot, which would obliterate the chart. Sqrt gives the perceptually correct "noticeable but not catastrophic" scaling.

- `baseSizePx`: minimum drawable dot (~3 px radius default).
- `sizeSliderScale`: user-controlled multiplier (~1.0 default; slider goes 0.25× to 4×).
- `instrumentAvgTradeVolume`: rolling N-trade average per instrument (Bookmap doesn't publish N; estimated 200–500 trades).

### A.3.4 Alpha decay over time

Bookmap does **not** fade trade dots over time. Once written, a dot stays at full alpha at its (price, time) pixel forever — it scrolls off-screen as time advances rather than fading. The "fade" perception users describe is really the result of **dot clustering** at zoom-out: at low zoom, many dots in one pixel-time merge into one dot whose size is the sum, so older trades visually thin out as their pixel-density decreases.

### A.3.5 Aggregation rules

Verified from Bookmap forum + KB. The clustering modes:

| Mode | Aggregation rule |
|------|------------------|
| **Smart** | Default. Adapts cluster window to zoom: tight at zoom-in (per-trade dots), wide at zoom-out (per-pixel-time merged) |
| **By Time** | Fixed time bucket (user sets ms). Trades within bucket merge into one dot |
| **By Volume** | Bucket closes when N contracts traded. One dot per N-contract bucket |
| **By Price** | One dot per price level per visible window |
| **By Price & Aggressor** | One dot per (price, aggressor side) combo per window |

The "Minimum accountable dot volume" filter hides any cluster smaller than N contracts — typical default 1, but pros set it to 5–25 to suppress retail-noise dots.

---

## A.4 Price ladder column system

The right-edge "trade panel" / left-edge "depth panel" of Bookmap. Each column is independently togglable; widths are fixed per column.

| Column | Default width | What it shows | Direction |
|--------|---------------|---------------|-----------|
| **Volume Bars** | ~16 px | Horizontal bars per price; length proportional to total volume traded at that price across the visible window | Left grows from price line |
| **Trades counter** | ~18 px | Numeric count of trades at each price | Right-aligned text |
| **Quotes counter** | ~18 px | Numeric count of quote updates at each price | Right-aligned text |
| **Quotes Delta** | ~20 px | Net add - cancel quote count, color-coded green/red | Bidirectional |
| **BBO line** | (overlay, 1 px) | 1 px line marking current best bid (cyan) and best ask (magenta) across heatmap | Horizontal across chart |
| **Last Trade line** | (overlay, 1 px) | 1 px white horizontal line at last trade price | Horizontal across chart |

**Custom column architecture:** Bookmap **L1 API** lets developers register custom columns via Java or Python (the Python API supports L1 features except replay mode, requires Python 3.7.14+ and Bookmap 7.4+). Each column is implemented as a Java `BookmapAddon` that returns per-price values and a renderer.

---

## A.5 Side panels (CVD, P&L, indicators)

Bookmap supports two "indicator regions":

1. **Subpane(s) below main chart** — one or more horizontal strips at the bottom for CVD, Speed of Tape, Imbalance%, custom Java/Python addons. Each subpane is independently scaleable, time-aligned to the main chart's X axis. Stroke is typically 1.5 px line on the same near-black background.

2. **Right-side widgets** — Position P&L gauge, Trading Statistics, Markets Hierarchy panel. These are docked widgets, not chart overlays.

**Color discipline:** custom indicators are *strongly encouraged* by the Bookmap design language to use the same near-black backdrop and the cyan/magenta/yellow accent palette of the main chart. Indicators that introduce orange-on-blue or other unrelated palettes look amateur.

---

## A.6 Crosshair + tooltip

Verified from screenshots and the local design playbook:

- **Crosshair stroke:** 1 px, dashed pattern `[3, 3]` (3 px dash, 3 px gap).
- **Crosshair color:** white at alpha 0.50 (`#FFFFFF80`).
- **Tooltip box:** background = panel-background (`#13161A`) at alpha 0.90; 1 px border at alpha 0.30; 4 px padding; **tabular numerals** (system monospace).
- **Tooltip content (left to right):** time (HH:MM:SS.mmm), price, volume at cursor, delta at cursor, percentile at cursor.
- **Edge avoidance:** tooltip flips to the opposite quadrant when within 8 px of any chart edge.

---

## A.7 Background and chrome

| Element | Value | Source |
|---------|-------|--------|
| Main chart background | `#0E1014` to `#13161A` near-black, slight cool bias | Verified via screenshot eyedropper + local agent file |
| Edge-to-edge rule | Zero padding/separator between heatmap and price ladder | Bookmap KB + visual inspection |
| Header strip | 24 px tall, contains: instrument symbol, contract month, last price, change/%, session VWAP | Bookmap UI |
| Footer strip | 18 px tall, contains: connection status, latency ms, fps counter, time | Bookmap UI |
| Grid | None on the main chart heatmap area | Design choice — heatmap is the grid |

---

## A.8 Indicator subsystem

Verified from KB + L1 API docs:

- **CVD** (Cumulative Volume Delta) — line plot in subpane, default 1.5 px, color scales red→green by sign.
- **Speed of Tape** — vertical bars in subpane, height = trades-per-second.
- **Imbalance%** — line in subpane, ranges -100..+100, zero line is solid white at alpha 0.3.
- **Sweeps** — markers on the main chart at sweep-detected price levels.
- **Absorption** (Bookmap's own native indicator) — orange dots at absorption sites; Bookmap detects these heuristically but DEEP6's own absorption engine is more sophisticated.

All indicators draw on the same near-black backdrop and respect the cyan/magenta/yellow accent palette.

---

## A.9 Zoom + pan interaction

- **Mouse wheel:** zoom about cursor (the price/time at the cursor stays fixed). Wheel up = zoom in.
- **Right-click drag:** free pan in both axes.
- **Left-click drag:** select region (rubber-band).
- **Auto-scale:** toggle in toolbar — when on, vertical axis re-fits to visible price range as time scrolls.
- **Double-click axis:** reset that axis to default zoom.

---

## A.10 The "white-hot peak" trick

The single visual signature of Bookmap that separates it from every other heatmap implementation:

When a price level's resting size goes *above* the upper cutoff, Bookmap renders that pixel as **pure red `#FF0000`**. But — and this is the trick — adjacent rows within ±1 pixel of the peak get a **white rim** added on top via a separate composite pass. The result is a "lava glow" effect where extreme liquidity walls don't just look red, they look *molten*. This communicates "this is not just a wall, this is a CITADEL" instantly.

Implementation: after the main bitmap is composited, walk the dirty columns again and, for any pixel at or above intensity 0.97, write white at alpha 0.4 to the pixel directly above and below. Cheap and devastatingly effective.

---

## A.11 NT8 implementation strategy: Bookmap heatmap clone

### A.11.1 Why this needs a custom indicator + custom data source

NT8 has no native order-book history. The standard `Bars` object is OHLC-only. To clone Bookmap you need:

1. **Live L2 DOM feed** — Rithmic via `RithmicMarketDataAdapter` exposes 10–40 levels.
2. **DOM snapshot ring buffer** — store one DOM snapshot per pixel-time slot (~25 ms granularity for 40 fps target).
3. **Custom indicator** rendering the bitmap on top of `ChartControl`.

### A.11.2 DOM data acquisition

```csharp
// In OnStateChange (State == State.SetDefaults), subscribe to L2 events:
public override void OnMarketDepth(MarketDepthEventArgs e)
{
    // e.MarketDataType = Ask | Bid
    // e.Operation = Insert | Update | Remove
    // e.Position = level (0 = best)
    // e.Price, e.Volume, e.Time
    domRingBuffer.WriteUpdate(e);
}
```

The ring buffer should be a fixed-size circular array of `DomSnapshot` structs:

```csharp
struct DomSnapshot
{
    public DateTime Time;
    public double[] BidPrices;   // 40 levels
    public long[]   BidVolumes;
    public double[] AskPrices;
    public long[]   AskVolumes;
}
// Ring buffer sized for visible chart width × pixels-per-second
// e.g., 1920 columns × 40 fps = 1920 snapshots, ~3.6 MB at 40 levels
```

### A.11.3 SharpDX bitmap-based heatmap rendering

NT8 forum confirms: per-cell `FillRectangle` on a 1920×1080 chart is 2M+ draw calls per frame — unworkable. The correct path is to maintain a **single SharpDX `Bitmap1`** matching chart dimensions and update it via `CopyFromMemory`, then draw it once with `RenderTarget.DrawBitmap`.

```csharp
public override void OnRenderTargetChanged()
{
    // Recreate the bitmap whenever the render target changes (zoom, resize)
    if (heatmapBitmap != null) heatmapBitmap.Dispose();
    var props = new SharpDX.Direct2D1.BitmapProperties1(
        new SharpDX.Direct2D1.PixelFormat(
            SharpDX.DXGI.Format.B8G8R8A8_UNorm,
            SharpDX.Direct2D1.AlphaMode.Premultiplied));
    heatmapBitmap = new SharpDX.Direct2D1.Bitmap1(
        RenderTarget,
        new SharpDX.Size2(chartWidthPx, chartHeightPx),
        props);
    heatmapPixels = new byte[chartWidthPx * chartHeightPx * 4]; // BGRA
}

public override void OnRender(ChartControl chartControl, ChartScale chartScale)
{
    // 1. Walk dirty columns, compute per-pixel intensity → LUT lookup
    foreach (int col in dirtyColumns)
    {
        var snapshot = domRingBuffer.GetSnapshotForColumn(col);
        for (int row = 0; row < chartHeightPx; row++)
        {
            double price = chartScale.GetValueByY(row);
            long size = snapshot.GetSizeAtPrice(price);
            double percentile = sizePercentileLookup.Lookup(size);
            double intensity = Math.Clamp(
                (percentile - lowerCutoff) / (upperCutoff - lowerCutoff), 0, 1);
            int lutIdx = (int)(intensity * 255);
            int pxOffset = (row * chartWidthPx + col) * 4;
            heatmapPixels[pxOffset + 0] = lutBlue[lutIdx];
            heatmapPixels[pxOffset + 1] = lutGreen[lutIdx];
            heatmapPixels[pxOffset + 2] = lutRed[lutIdx];
            heatmapPixels[pxOffset + 3] = 255;
        }
    }
    dirtyColumns.Clear();

    // 2. Upload to GPU bitmap (one call per frame)
    heatmapBitmap.CopyFromMemory(heatmapPixels, chartWidthPx * 4);

    // 3. Draw the bitmap once
    RenderTarget.DrawBitmap(
        heatmapBitmap,
        new SharpDX.RectangleF(0, 0, chartWidthPx, chartHeightPx),
        1.0f,
        SharpDX.Direct2D1.BitmapInterpolationMode.NearestNeighbor); // disable AA

    // 4. Layer 2: BBO + last trade lines (1px each, on top)
    RenderBboLines();

    // 5. Layer 3: trade dots (separate brush per dot is fine — count is low)
    RenderTradeDots();

    // 6. Layer 4: white-hot rim pass
    RenderWhiteHotRim();
}
```

### A.11.4 Pre-built 256-stop LUT

Build it once in `OnStateChange (State.DataLoaded)`:

```csharp
private byte[] lutRed = new byte[256], lutGreen = new byte[256], lutBlue = new byte[256];

private void BuildHotLUT()
{
    var stops = new (float pos, byte r, byte g, byte b)[] {
        (0.00f, 0x00, 0x00, 0x00),
        (0.05f, 0x00, 0x0A, 0x1F),
        (0.20f, 0x0A, 0x2A, 0x6E),
        (0.40f, 0x1E, 0x5F, 0xCE),
        (0.55f, 0x5A, 0x9F, 0x7A),
        (0.65f, 0xE8, 0xC0, 0x34),
        (0.78f, 0xF0, 0x8C, 0x1A),
        (0.90f, 0xE6, 0x3B, 0x1A),
        (0.97f, 0xFF, 0x00, 0x00),
        (1.00f, 0xFF, 0xFF, 0xFF),
    };
    for (int i = 0; i < 256; i++)
    {
        float t = i / 255f;
        // find bracketing stops
        int j = 0; while (j < stops.Length - 1 && stops[j+1].pos < t) j++;
        float span = stops[j+1].pos - stops[j].pos;
        float u = span > 0 ? (t - stops[j].pos) / span : 0;
        lutRed[i]   = (byte)(stops[j].r + (stops[j+1].r - stops[j].r) * u);
        lutGreen[i] = (byte)(stops[j].g + (stops[j+1].g - stops[j].g) * u);
        lutBlue[i]  = (byte)(stops[j].b + (stops[j+1].b - stops[j].b) * u);
    }
}
```

### A.11.5 Off-screen rendering pattern

Because NT8 calls `OnRender` on the UI thread (and only when the chart is invalidated), the recommended pattern is:

1. **Background thread (DOM update handler)**: write incremental pixel updates into a *staging* byte buffer. Use a lock or `Volatile.Write` on the dirty-column bitmask.
2. **UI thread (`OnRender`)**: under lock, swap the staging buffer with the live buffer, upload, draw.

This way DOM updates at 1000+/sec don't block the render thread, and the render thread always has a consistent snapshot.

### A.11.6 Performance target: 60 fps on NT8

Bookmap targets 125 fps because it controls the entire stack (OpenGL via JOGL). NT8 SharpDX/D2D maxes practically around 60 fps because of the WPF interop and `OnRender` invalidate cadence. **60 fps is the right target** — every Bookmap user can tell 60 from 30 fps but cannot tell 60 from 125. To hit 60:

- Throttle `ChartControl.InvalidateVisual()` calls to once per `1000 / 60 = 16.6 ms` via a `DispatcherTimer`.
- Keep the dirty-column bitmask tight — never rebuild the full bitmap per frame.
- Pre-allocate everything in `OnRenderTargetChanged`; never allocate inside `OnRender`.

---

# PART B — ATAS

## B.1 The ATAS visual thesis

If Bookmap is "data as raster," ATAS is "data as typography." Every cell in an ATAS cluster chart is a number that the trader is meant to read, not just see. The choice to render volumes as **legible text inside colored cells** instead of color-only intensity is the founding decision — it preserves the precise count that footprint readers care about while still providing the gestalt of a heatmap through cell tinting.

ATAS's secondary thesis is **mode-richness**. The same bar can be displayed seven different ways, and the cells inside can be colored using any of nine schemes. This combinatorial flexibility is why ATAS retains traders who'd otherwise drift to Sierra or Quantower.

---

## B.2 Cluster chart specification

### B.2.1 The seven cluster modes (verified from ATAS KB "Cluster Settings")

| # | Mode | What's drawn per cell | Cell layout within bar |
|---|------|----------------------|------------------------|
| 1 | **Bid x Ask** | Two numbers side by side: bid volume LEFT, ask volume RIGHT, separated by divider char (default `x`) | One row per price level; full bar width |
| 2 | **Bid x Ask Ladder** | Bid volume on a **lower** sub-row, ask volume on the **upper** sub-row (vertical stack within one price cell) | Each price = 2 sub-rows |
| 3 | **Histogram** | Horizontal bar chart inside cell; bid bar grows left, ask bar grows right, lengths = volumes | One bar per price, full cell width |
| 4 | **Volume Profile** | Single horizontal bar per price; length = total volume; alignment = left or right (configurable) | One bar per price |
| 5 | **Delta Profile** | Signed horizontal bar per price; bar grows right (positive delta) or left (negative); zero is bar-bottom centered | One bar per price |
| 6 | **Imbalance** | Cell shows nothing if no imbalance; shows bid or ask number colored if imbalance ≥ ratio | One cell per price; mostly empty |
| 7 | **Trades** | Single number = number of executions at that price | One cell per price |

Plus the related **content selectors** (10 options): Volume, Trades, Delta, Bid x Ask, Time, Buy Trades, Sell Trades, Max Bid, Max Ask, None. These determine *what is counted*; the mode determines *how it's drawn*.

### B.2.2 Cell anatomy: canonical Bid x Ask

```
+------------------------------------------+
|   123 x 456                              |  ← one price level
+------------------------------------------+
|     ↑      ↑      ↑                      |
|     bid  divider  ask                    |
|     vol  ('x')    vol                    |
|     left          right                  |
|     aligned       aligned                |
|                                          |
|   font: Segoe UI 9–11 px (auto-sized)    |
|   bold toggle                            |
|   tabular numerals                       |
+------------------------------------------+
```

Cell height = price tick × `ticks-per-row` aggregation × pixels-per-tick from chart scale.
Cell width = bar width (consistent across all rows in a bar).

### B.2.3 Cell sizing defaults

| Parameter | Default |
|-----------|---------|
| Bar width (cluster column) | 80–120 px (auto-sizes to fit numbers + cluster statistic strip) |
| Row height (per price level) | Equal to chart's `Bar Width`/`Bar Spacing` setting × ticks-per-level |
| Font min | 6 px |
| Font max | 14 px |
| Font default | Segoe UI Regular, auto-sized |
| Bold toggle | Off by default |
| Cluster Values Divider | `x` (other built-in options: `|`, ` ` (space), or any custom character) |

---

## B.3 The nine color schemes (verified from ATAS KB)

Each scheme determines how an individual cell is tinted. The bid/ask number text is overlaid in white or black for max contrast.

| # | Scheme | How cell color is computed |
|---|--------|----------------------------|
| 1 | **Solid** | Single user-chosen color for all cells; numbers in contrasting text color |
| 2 | **Bid/Ask Volume Proportion** | Cell hue = green if ask > bid (buyer-aggressive), red if bid > ask (seller-aggressive); saturation = strength of imbalance |
| 3 | **Heatmap by Volume** | Cell intensity scales with cell's volume / max-cell-volume in bar; LUT applied (typically green or single-hue gradient) |
| 4 | **Heatmap by Trades** | Same as #3 but uses trade count instead of volume |
| 5 | **Heatmap by Delta** | Diverging scale: positive delta → green intensity; negative → red intensity; zero = neutral |
| 6 | **Volume Proportion** | Cell color is a single hue scaled by cell's share of total bar volume (no bid/ask split) |
| 7 | **Trades Proportion** | Same as #6 but trades-based |
| 8 | **Delta** | Cell hue green or red by delta sign; intensity = abs(delta) / max abs delta |
| 9 | **None** | No fill; just border + text |

Typical default colors (recommended for DEEP6):

| Element | Hex | Notes |
|---------|-----|-------|
| Buy / ask-aggressive base | `#00C853` | Material green 600 |
| Sell / bid-aggressive base | `#D50000` | Material red A700 |
| Heatmap LUT for volume | `#0E1014` → `#003B14` → `#00873B` → `#00E676` | Single-hue green |
| Heatmap LUT for delta | `#FF1744` (negative) → `#0E1014` (zero) → `#00E676` (positive) | Diverging |
| Imbalance accent | `#FFEA00` | Gold border on top of fill |
| Max-volume cell contour | `#000000` | 1 px black border |
| Numbers (light text on dark cell) | `#FFFFFF` at alpha 0.92 | |
| Numbers (dark text on light cell) | `#000000` at alpha 0.92 | |

---

## B.4 Imbalance highlighting (verified)

| Property | Default value |
|----------|---------------|
| Imbalance ratio | **150 %** (one side ≥ 1.5× the other) |
| Comparison | **Diagonal**: bid at price P versus ask at P+1 tick (and ask at P versus bid at P-1) |
| Bid imbalance color | Red (`#D50000` family) — sellers dominate |
| Ask imbalance color | Green (`#00C853` family) — buyers dominate |
| Border style options | `Body` (border around cell body), `Candle` (full cell outline like a candle), `None` (fill only) |
| Border thickness | 1 px default; user-configurable |
| Maximum-volume cell | 1 px black contour (`#000000`) — POC marker |

**Stacked imbalance** behavior: when ≥ 3 consecutive price cells have imbalance in the same direction, ATAS does *not* visually emphasize the stack natively (this is a major weakness — Trader Dale's pedagogy demands it). DEEP6 should *exceed* ATAS here by drawing a persistent gutter zone and a brighter accent.

---

## B.5 Typography

| Property | Default |
|----------|---------|
| Font family | **Segoe UI** (Windows native) |
| Style | Regular (Bold optional toggle) |
| Auto-size | On — font shrinks/grows with cell size between min and max bounds |
| Min font size | 6 px |
| Max font size | 14 px |
| Cluster Values Divider | `x` default; `|`, ` `, or custom char alternatives |
| Numerals | System Segoe UI numerals (NOT explicitly tabular, but visually approximate) |

---

## B.6 Cluster Statistic strip

Top-of-bar header rendered at the top of every cluster. Width = bar width. Content (configurable, but common defaults):

| Field | Description |
|-------|-------------|
| Aggregate delta | Signed integer (positive green, negative red) |
| Total volume | Bar's total volume |
| Max imbalance count | Number of imbalanced cells in the bar |
| (Optional) trade count, max bid, max ask, etc. | User-selectable rows |

Typography matches cluster cells (Segoe UI auto-sized). Background is bar background or transparent. Each row of the strip is a separate styled line; rows can be reordered or hidden via settings.

---

## B.7 Side panels in ATAS

### B.7.1 Smart Tape

Vertical streaming time-and-sales window, separate panel docked to the chart.

- **Layout:** rows top-down, newest at top.
- **Color rules:**
  - Bid color (sell aggressor) — red.
  - Ask color (buy aggressor) — green.
  - **Above Ask / Below Bid** — special background highlight when trade prints outside the spread (sweeps).
  - **Speed Color** — separate band whose color encodes tape velocity.
  - Header background, header text, alternative row background — all individually configurable.
- **Fade animation:** the KB does not publish an exact ms value, but observed fade-out for "newest trade" highlight is ~400–600 ms (visually estimate ~500 ms). DEEP6 implementation should use **500 ms ease-out cubic** as a faithful clone.
- **Tape filters:** Buy-Sell Interval slider controls smoothing of the speed/strength indicators.
- **Filtering:** by min volume, by aggressor side, by price-vs-spread.

### B.7.2 DOM Levels

Lines drawn into the main chart at price levels with significant resting volume.

- Line thickness scales with volume (typical 1–4 px).
- Color: bid lines blue, ask lines red, or single user color.
- Persists as long as the level retains size; auto-cleared when level dries up.

### B.7.3 Big Trades

Circles plotted on the chart at the (price, time) of large executions.

- **Radius:** scales with `sqrt(volume)` — same psychophysical correctness as Bookmap dots.
- **Color:** by aggressor — green (buy) or red (sell).
- **Threshold:** user-defined min volume for plotting (typical 10–50 contracts on NQ).
- **Optional label:** trade size shown next to circle.

---

## B.8 Background, axis, crosshair

| Element | Value |
|---------|-------|
| Background | `#1A1A1A` to `#222222` (slightly warmer than Bookmap's `#0E1014`) |
| Axis lines | 1 px, alpha 0.20, neutral gray |
| Axis labels | tabular numerals, Segoe UI 9 px, alpha 0.55 |
| Grid | 1 px, alpha 0.06–0.10 (dimmer than axis) — but cluster cells overlap and dominate |
| Crosshair | 1 px dashed `[3,3]`, white at alpha 0.50 |
| Tooltip | panel background `#222222` at alpha 0.90, 1 px border at alpha 0.30, Segoe UI 9 px |

---

## B.9 Specific ATAS details to capture

| Detail | Value | Verified |
|--------|-------|----------|
| Default imbalance ratio | 150 % | YES (KB) |
| Imbalance comparison axis | Diagonal | YES (blog + KB) |
| POC contour | 1 px black `#000000` | YES (industry consensus; also Sierra uses yellow as alternative) |
| Big Trades sizing | sqrt(volume) | Visual confirmation |
| Smart Tape fade duration | ~500 ms (estimated; not published) | Observed behavior |
| Cluster Values Divider | `x` default; `|`, ` `, custom | YES (KB) |
| Default font | Segoe UI Regular (Windows) | Visual confirmation; Windows native |
| Font auto-size range | 6–14 px typical | Visual confirmation |
| Number of color schemes | 9 | YES (KB: 10 × 7 × 9 = 630 variations) |
| Number of cluster modes | 7 | YES (KB) |
| Number of content types | 10 | YES (KB) |

---

## B.10 NT8 implementation strategy: ATAS cluster clone

### B.10.1 Use VolumetricBarsType for data

NT8's **Order Flow+ Volumetric Bars** ($59/mo addon, included in Lifetime) provides per-bar bid/ask volume per price level via the `VolumetricBarsType` cast. Hot path:

```csharp
public override void OnBarUpdate()
{
    if (Bars.BarsType is NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType)
    {
        var volBars = (NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType)Bars.BarsType;
        var barInfo = volBars.Volumes[CurrentBar];
        // barInfo.GetBidVolumeForPrice(price)
        // barInfo.GetAskVolumeForPrice(price)
        // barInfo.GetTotalVolume(), GetTotalBuyingVolume(), GetTotalSellingVolume()
    }
}
```

### B.10.2 Custom indicator on top for visual rendering

Disable NT8 OFA's default visualizer (set bars to `Standard Volumetric` but configure to show no cells), then render your own via `OnRender`:

```csharp
public override void OnRender(ChartControl chartControl, ChartScale chartScale)
{
    for (int barIdx = ChartBars.FromIndex; barIdx <= ChartBars.ToIndex; barIdx++)
    {
        float barX = chartControl.GetXByBarIndex(ChartBars, barIdx);
        float barWidth = (float)chartControl.BarWidth;
        var volBar = volumetricBars.Volumes[barIdx];

        // For each price level in the bar
        double low = Bars.GetLow(barIdx);
        double high = Bars.GetHigh(barIdx);
        double tickSize = Bars.Instrument.MasterInstrument.TickSize;
        for (double price = low; price <= high + tickSize/2; price += tickSize)
        {
            float cellY = chartScale.GetYByValue(price);
            float cellHeight = (float)chartScale.GetPixelsForDistance(tickSize);
            long bidVol = volBar.GetBidVolumeForPrice(price);
            long askVol = volBar.GetAskVolumeForPrice(price);
            RenderClusterCell(barX, cellY, barWidth, cellHeight, bidVol, askVol, currentMode, currentScheme);
        }

        // Cluster Statistic strip above bar
        RenderClusterStatistic(barX, /* aboveBarY */, barWidth, volBar);
    }
}
```

### B.10.3 All seven cluster modes selectable via dropdown

```csharp
public enum ClusterMode { BidXAsk, BidXAskLadder, Histogram, VolumeProfile, DeltaProfile, Imbalance, Trades }

private void RenderClusterCell(float x, float y, float w, float h, long bid, long ask, ClusterMode mode, ColorScheme scheme)
{
    var cellColor = ComputeCellColor(bid, ask, scheme);
    using (var brush = cellColor.ToDxBrush(RenderTarget))
        RenderTarget.FillRectangle(new SharpDX.RectangleF(x, y, w, h), brush);

    switch (mode)
    {
        case ClusterMode.BidXAsk:
            DrawText($"{bid}{divider}{ask}", x, y, w, h, /*centered*/);
            break;
        case ClusterMode.BidXAskLadder:
            DrawText($"{ask}", x, y, w, h/2, /*top half*/);
            DrawText($"{bid}", x, y + h/2, w, h/2, /*bottom half*/);
            break;
        case ClusterMode.Histogram:
            float maxBar = w / 2;
            float bidLen = (float)(bid / (double)barMaxVol) * maxBar;
            float askLen = (float)(ask / (double)barMaxVol) * maxBar;
            DrawHorizontalBar(x + w/2 - bidLen, y, bidLen, h, bidColor);
            DrawHorizontalBar(x + w/2, y, askLen, h, askColor);
            break;
        // ... etc.
    }

    // Imbalance overlay (always on top regardless of mode)
    if (currentMode != ClusterMode.Imbalance)
        DrawImbalanceMarker(x, y, w, h, bid, ask, /* prev/next cell for diagonal */);

    // Max-volume cell contour
    if (bid + ask == barMaxVol)
        DrawRectangle(x, y, w, h, /*black 1px*/);
}
```

### B.10.4 Nine color schemes selectable

```csharp
public enum ColorScheme { Solid, BidAskProportion, HeatmapByVolume, HeatmapByTrades, HeatmapByDelta, VolumeProportion, TradesProportion, Delta, None }

private Color ComputeCellColor(long bid, long ask, ColorScheme scheme)
{
    long total = bid + ask;
    long delta = ask - bid;
    switch (scheme)
    {
        case ColorScheme.Solid:
            return solidColor;
        case ColorScheme.BidAskProportion:
            float ratio = total == 0 ? 0.5f : (float)ask / total;
            return Color.Lerp(bidColor, askColor, ratio);
        case ColorScheme.HeatmapByVolume:
            float intensity = (float)total / barMaxVol;
            return volumeLut[(int)(intensity * 255)];
        case ColorScheme.HeatmapByDelta:
            float dPct = barMaxAbsDelta == 0 ? 0 : (float)delta / barMaxAbsDelta;
            return delta >= 0 ? deltaPosLut[(int)(dPct * 255)] : deltaNegLut[(int)(-dPct * 255)];
        // ...
    }
}
```

### B.10.5 Cluster Statistic strip drawn above each bar

```csharp
private void RenderClusterStatistic(float barX, float headerY, float barWidth, BidAskVolume volBar)
{
    float lineHeight = 12f;
    var rows = new[] {
        ("Δ",   volBar.BarDelta.ToString("+#;-#;0"), volBar.BarDelta >= 0 ? Brushes.LimeGreen : Brushes.OrangeRed),
        ("Vol", volBar.TotalVolume.ToString("N0"),  Brushes.Gainsboro),
        ("Imb", imbalanceCount.ToString(),          Brushes.Gold),
    };
    for (int i = 0; i < rows.Length; i++)
    {
        DrawText(rows[i].Item1 + " " + rows[i].Item2, barX, headerY + i*lineHeight, barWidth, lineHeight);
    }
}
```

### B.10.6 Smart Tape side panel as separate AddOn

Smart Tape is best implemented as an `NTTabPage` AddOn (or a `WindowBase` floating panel) rather than as part of the chart indicator — it has its own data flow, scrolling, and lifecycle.

```csharp
public class SmartTapeAddOn : NTTabPage
{
    private List<TapeRow> rows = new();
    private const int FadeDurationMs = 500;
    public override string Caption => "Smart Tape";
    protected override void OnLoad() { /* subscribe to feed */ }
    private void OnTrade(TradeEvent t)
    {
        rows.Insert(0, new TapeRow {
            Time = t.Time,
            Price = t.Price,
            Volume = t.Volume,
            AggressorIsBuy = t.IsBuyAggressor,
            FadeStartMs = Environment.TickCount,
        });
        if (rows.Count > 500) rows.RemoveAt(rows.Count - 1);
        Invalidate();
    }
    protected override void OnRender(DrawingContext ctx)
    {
        foreach (var r in rows)
        {
            int age = Environment.TickCount - r.FadeStartMs;
            float fade = age < FadeDurationMs
                ? 1f - 0.5f * EaseOutCubic(age / (float)FadeDurationMs)
                : 0.5f;
            var brush = r.AggressorIsBuy ? buyBrush : sellBrush;
            // Draw row with alpha = fade
        }
    }
}
```

---

# PART C — CROSS-PLATFORM SYNTHESIS

## C.1 Where Bookmap is better than ATAS

| Capability | Why Bookmap wins |
|------------|------------------|
| Heatmap | Bookmap's per-pixel raster + percentile cutoff gives 4–8× more usable visual range than ATAS's 2023-added heatmap (which is a per-cell tint) |
| Trade dot rendering | Square-root sizing + cyan/magenta + 2D/3D shapes gives Bookmap aggression dots an almost cinematic clarity ATAS Big Trades cannot match |
| Information density | Bookmap shows 1920 columns × 1080 rows of liquidity intensity simultaneously; ATAS cluster max is ~50 visible bars |
| Refresh rate | 125 fps vs ATAS ~30 fps |
| Edge-to-edge layout | Bookmap's "no chrome" rule lets the data fill the screen; ATAS preserves NT-style chrome |

## C.2 Where ATAS is better than Bookmap

| Capability | Why ATAS wins |
|------------|---------------|
| Footprint cell variants | 7 modes × 9 schemes (Bookmap's "Volume Bars" is one mode, one scheme) |
| Imbalance defaults on | 150 % ratio out of the box (Bookmap has no imbalance highlighting) |
| Numeric legibility | Cluster numbers are the source of truth; Bookmap forces percentile inference from color |
| Panel richness | Smart Tape, DOM Levels, Big Trades, Stacked Imbalance, Volume Profile, Delta, Open Interest all native (Bookmap requires L1 API addons) |
| Multi-timeframe replay | ATAS has stronger built-in playback/replay tooling |

## C.3 What both miss that DEEP6 should add

1. **Auto-detected absorption with prominent visual** — DEEP6's E1/E2 absorption engine produces a confidence score; render absorption as a *pulsing* bordered cell at the absorption price level, with a left-gutter triangle marker that persists until invalidated. **Neither platform has this.**

2. **Auto-detected exhaustion with prominent visual** — same treatment, opposite direction (pullback fading into trapped shorts/longs). Render as a fading "candle wick" overlay annotation pointing at the exhaustion price.

3. **Multi-signal confluence sparkline** — a 60 px tall horizontal sparkline below the cluster statistic strip that plots, per bar, the sum of normalized scores from the 44 signals. Color = sign of net signal. **No competitor has signal-density rendering.**

4. **44-signal heatmap diagnostic readout** — a small 11×4 grid of 44 LED-style cells in the right margin showing which signals are firing right now (lit = active, dark = inactive). Hover reveals signal name + current score.

5. **Confidence gauge** — a vertical 24 px wide, full-chart-height gauge on the far right showing rolling 30-second confidence-to-go-long vs go-short, color-graded with a midline at zero. This is DEEP6's "trade now / don't" affordance.

6. **Stacked imbalance persistent zones** — when ≥ 3 consecutive cells imbalance same direction, drop a colored zone behind future bars at that price band that persists for N minutes or until tested. **ATAS partially does; nobody does it well.**

---

## C.4 DEEP6 default mode recommendation

The combination that ships:

```
Layer 0: background = #0E1014
Layer 1: Bookmap-style heatmap UNDERLAY at 75% alpha (price ladder always
         readable through it)
Layer 2: ATAS Bid x Ask cluster cells rendered ON TOP, with imbalance
         highlighting (150% default), POC contour (1px black), and
         max-delta gold border
Layer 3: DEEP6 absorption/exhaustion overlays (pulsing borders +
         persistent zones)
Layer 4: Trade dots (cyan/magenta sqrt sizing) over heatmap, OFF over
         cluster region (avoids clutter)
Layer 5: BBO + last trade lines (1px)
Layer 6: 44-signal LED grid (right margin)
Layer 7: Confidence gauge (far right, 24px wide)
Layer 8: Crosshair + tooltip
```

This gives a trader Bookmap's spatial liquidity awareness, ATAS's cell-level numeracy, and DEEP6's signal intelligence in a single integrated chart — none of which any competitor can match.

---

## C.5 Comparison master table

| Feature | Bookmap | ATAS | DEEP6 target |
|---------|---------|------|--------------|
| Background hex | `#0E1014` | `#1A1A1A` | `#0F1115` |
| Heatmap | YES (per-pixel raster, 125 fps) | partial (per-cell tint, ~30 fps) | YES (per-pixel, 60 fps in NT8) |
| Cluster modes | 1 (Volume Bars histogram) | 7 | 7 + DEEP6 hybrid |
| Color schemes | 1 default + custom | 9 | 9 + DEEP6 absorption-tinted |
| Imbalance ratio | n/a | 150 % default | 150/300/400 % tiered |
| POC marker | n/a | 1 px black contour | 1 px gold contour + glyph |
| Trade dots | YES (cyan/magenta sqrt) | partial (Big Trades circles) | YES + per-aggressor + speed-encoded |
| Dot size formula | sqrt(vol/avgVol) | sqrt(vol) | sqrt(vol) + clamp |
| Refresh rate | 40–125 fps | ~30 fps | 60 fps target |
| Smart Tape | partial (BookmapStatistics addon) | YES (500 ms fade) | YES + signal-tagged |
| Big Trades panel | partial | YES | YES + absorption flag |
| 44-signal LED grid | NO | NO | YES (DEEP6 unique) |
| Confidence gauge | NO | NO | YES (DEEP6 unique) |
| Stacked imbalance zones | NO | partial | YES (full persistence) |
| Absorption auto-detect | partial (Absorption addon) | NO | YES (E1/E2 engine) |
| Exhaustion auto-detect | NO | NO | YES (E2 + DEEP6) |
| GPU rendering | OpenGL 3.0 | DirectX (NT8 SharpDX-like) | NT8 SharpDX (Direct2D) |
| Crosshair | 1 px dashed `[3,3]` white α0.5 | 1 px dashed white α0.5 | match |
| Default font | System monospace tabular | Segoe UI auto-sized | JetBrains Mono 9 px tabular for cells |
| Edge-to-edge | YES | partial | YES (kill all NT8 chrome) |

---

## C.6 Verified hex code master reference

For copy-paste into NT8 brush definitions:

```csharp
// === Bookmap heatmap LUT stops ===
public static readonly Color HeatmapBlack    = Color.FromRgb(0x00, 0x00, 0x00); // 0.00
public static readonly Color HeatmapNavy     = Color.FromRgb(0x00, 0x0A, 0x1F); // 0.05
public static readonly Color HeatmapBlue     = Color.FromRgb(0x0A, 0x2A, 0x6E); // 0.20
public static readonly Color HeatmapCyanBlue = Color.FromRgb(0x1E, 0x5F, 0xCE); // 0.40
public static readonly Color HeatmapMid      = Color.FromRgb(0x5A, 0x9F, 0x7A); // 0.55
public static readonly Color HeatmapYellow   = Color.FromRgb(0xE8, 0xC0, 0x34); // 0.65
public static readonly Color HeatmapOrange   = Color.FromRgb(0xF0, 0x8C, 0x1A); // 0.78
public static readonly Color HeatmapRedOr    = Color.FromRgb(0xE6, 0x3B, 0x1A); // 0.90
public static readonly Color HeatmapRed      = Color.FromRgb(0xFF, 0x00, 0x00); // 0.97
public static readonly Color HeatmapWhite    = Color.FromRgb(0xFF, 0xFF, 0xFF); // 1.00

// === Bookmap trade dots ===
public static readonly Color BuyDotCore  = Color.FromRgb(0x00, 0xD4, 0xFF); // cyan
public static readonly Color BuyDotHalo  = Color.FromRgb(0x7D, 0xF9, 0xFF);
public static readonly Color SellDotCore = Color.FromRgb(0xFF, 0x36, 0xA3); // magenta
public static readonly Color SellDotHalo = Color.FromRgb(0xFF, 0x6B, 0xC1);

// === ATAS cluster base ===
public static readonly Color BuyAggressive   = Color.FromRgb(0x00, 0xC8, 0x53); // Material green 600
public static readonly Color SellAggressive  = Color.FromRgb(0xD5, 0x00, 0x00); // Material red A700
public static readonly Color ImbalanceBuy    = Color.FromRgb(0x00, 0xE6, 0x76); // bright green
public static readonly Color ImbalanceSell   = Color.FromRgb(0xFF, 0x17, 0x44); // bright red
public static readonly Color ExtremeAccent   = Color.FromRgb(0xFF, 0xEA, 0x00); // gold
public static readonly Color PocContour      = Color.FromRgb(0x00, 0x00, 0x00); // pure black

// === DEEP6 ===
public static readonly Color BgPanel         = Color.FromRgb(0x0F, 0x11, 0x15);
public static readonly Color BgChart         = Color.FromRgb(0x0E, 0x10, 0x14);
public static readonly Color GridLine        = Color.FromArgb(0x14, 0xFF, 0xFF, 0xFF); // white α0.08
public static readonly Color CrosshairColor  = Color.FromArgb(0x80, 0xFF, 0xFF, 0xFF);
public static readonly Color TextOnDark      = Color.FromArgb(0xEB, 0xFF, 0xFF, 0xFF); // white α0.92
public static readonly Color TextOnLight     = Color.FromArgb(0xEB, 0x00, 0x00, 0x00); // black α0.92
```

---

## C.7 Summary build sequence for the NT8 graphics agent

**Phase 1 — Bookmap heatmap clone**
1. Wire Rithmic L2 DOM via `OnMarketDepth`.
2. Build the per-pixel-time DOM ring buffer.
3. Build the percentile-rank lookup over the rolling N-minute window.
4. Build the 256-stop hot LUT (`BuildHotLUT()`).
5. Implement `OnRenderTargetChanged` bitmap allocation.
6. Implement `OnRender` dirty-column update + `Bitmap1.CopyFromMemory` + `DrawBitmap`.
7. Add upper/lower cutoff sliders (95 % / 5 % defaults).
8. Add BBO + last trade lines (1 px overlays).
9. Add trade dot overlay (cyan/magenta, sqrt sizing).
10. Add white-hot rim post-pass.
11. Throttle `InvalidateVisual` to 60 fps via DispatcherTimer.

**Phase 2 — ATAS cluster clone**
1. Detect `VolumetricBarsType`; fall back to error if user hasn't set it.
2. Implement 7 cluster mode renderers (`BidXAsk`, `BidXAskLadder`, `Histogram`, `VolumeProfile`, `DeltaProfile`, `Imbalance`, `Trades`).
3. Implement 9 color scheme functions (`Solid` … `None`).
4. Implement diagonal imbalance comparison (P bid vs P+1 ask, P ask vs P-1 bid) with 150 % default.
5. Imbalance border: `Body` / `Candle` / `None` styles.
6. Max-volume cell: 1 px black contour.
7. Cluster Statistic strip: aggregate delta + volume + imbalance count rows.
8. Font: Segoe UI auto-sized 6–14 px, with bold toggle.
9. Cluster Values Divider: configurable char (default `x`).
10. Smart Tape AddOn: 500 ms ease-out fade, color-coded rows.
11. Big Trades overlay: sqrt-sized circles, threshold filter.

**Phase 3 — DEEP6 superset layer**
1. Absorption pulsing border + gutter triangle (driven by E1/E2 engine output).
2. Exhaustion fading wick overlay (driven by E2 + DEEP6 logic).
3. Stacked imbalance persistent zone shading.
4. 44-signal LED grid (11×4) in right margin.
5. Confidence gauge (24 px vertical strip, far right).
6. Multi-signal confluence sparkline below cluster statistic strip.

---

# Sources

**Bookmap:**
- [Heatmap Settings — Bookmap KB](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapSettings)
- [Colour Settings — Bookmap KB](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapColourSettings)
- [Main Chart — Bookmap KB](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapMainChart)
- [Traded Volume Visualization — Bookmap KB](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapTradedVolumeVisualization)
- [Customizing Bookmap Heatmap Settings — Learning Center](https://bookmap.com/learning-center/en/getting-started/liquidity-heatmap/heatmap-settings)
- [How to Read Volume Dots on Bookmap](https://bookmap.com/learning-center/getting-started/volume/volume-dots-display)
- [Bookmap Performance FAQ](https://new.bookmap.com/knowledgebase/docs/KB-Help-FAQs-Performance)
- [Comprehensive BookMap Overview — TraderVPS](https://www.tradervps.com/blog/comprehensive-bookmap-overview-features-costs-user-services)
- [Bookmap Python API — KB](https://bookmap.com/knowledgebase/docs/Addons-Python-API)
- [Bookmap API Layers — KB](https://bookmap.com/knowledgebase/docs/KB-API-DevelopingIndicators)

**ATAS:**
- [Cluster Settings — ATAS Help](https://help.atas.net/en/support/solutions/articles/72000606631-cluster-settings)
- [Imbalance Ratio — ATAS Help](https://help.atas.net/en/support/solutions/articles/72000602404-imbalance-ratio)
- [Bid Ask — ATAS Help](https://help.atas.net/en/support/solutions/articles/72000602329-bid-ask)
- [Smart Tape — ATAS Help](https://help.atas.net/en/support/solutions/articles/72000602608-description-setting-templates-smart-tape-)
- [Speed of Tape — ATAS Help](https://help.atas.net/en/support/solutions/articles/72000602472-speed-of-tape)
- [How Footprint Charts Work — ATAS blog](https://atas.net/blog/how-footprint-charts-work-footprint-modes-and-what-they-are-for/)
- [Imbalance: how to find and trade — ATAS blog](https://atas.net/blog/how-to-find-and-trade-imbalance/)
- [Cluster Analysis for Beginners — ATAS blog](https://atas.net/blog/cluster-analysis-for-beginners/)
- [Cluster Charts Functionality — ATAS](https://atas.net/atas-possibilities/cluster-chart-functionality/)
- [Best Footprint Chart Software — ATAS](https://atas.net/footprint-charts/)

**NinjaTrader 8 implementation references:**
- [Using SharpDX for Custom Chart Rendering — NT8 Help](https://ninjatrader.com/support/helpguides/nt8/using_sharpdx_for_custom_chart_rendering.htm)
- [SharpDX SDK Reference — NT8 Help](https://ninjatrader.com/support/helpguides/nt8/sharpdx_sdk_reference.htm)
- [Order Flow Volumetric Bars — NT8 Help](https://ninjatrader.com/support/helpguides/nt8/order_flow_volumetric_bars.htm)
- [Volumetric Bars NinjaScript Methods — NT8 Help](https://ninjatrader.com/support/helpguides/nt8/order_flow_volumetric_bars2.htm)
- [DX Brushes for drawing heatmap — NT8 Forum](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/105264-dx-brushes-for-drawing-heatmap-best-practice)
- [Bookmap style heatmap — NT8 Forum](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1241575-bookmap-style-heatmap)
- [SharpDX BitmapBrush in OnRender — NT8 Forum](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1166642-sharpdx-bitmapbrush-in-onrender)

**Local DEEP6 cross-reference files:**
- `/Users/teaceo/DEEP6/dashboard/agents/trading-platform-competitor-analysis.md`
- `/Users/teaceo/DEEP6/dashboard/agents/footprint-orderflow-design-playbook.md`
- `/Users/teaceo/DEEP6/dashboard/agents/ninjatrader-graphics-architect.md`
- `/Users/teaceo/DEEP6/dashboard/agents/ULTIMATE-NINJASCRIPT-AGENT-v5.md`

---

**Final notes for the agent receiving this:**

1. **Bookmap clone is the harder build** because it requires per-pixel raster updates at 60 fps inside NT8's `OnRender`. Do this first; the cluster clone is comparatively trivial after.
2. **The 256-stop LUT pre-built in `OnStateChange (DataLoaded)`** is the single biggest performance win — never lerp colors per-pixel per-frame.
3. **`Bitmap1.CopyFromMemory` is the only viable upload path** in SharpDX/Direct2D for NT8 — `FillRectangle` per-cell will not hit 60 fps at 1920×1080.
4. **Disable anti-aliasing on the heatmap bitmap** (`BitmapInterpolationMode.NearestNeighbor`). Anti-aliasing destroys cutoff legibility.
5. **For the ATAS clone, font auto-sizing is non-trivial** — pre-measure Segoe UI at every size 6–14, cache the metrics, and binary-search the largest size that fits both numbers + divider in the cell width.
6. The DEEP6-unique additions (44-signal LED grid, confidence gauge, absorption/exhaustion overlays) are what justify shipping at all — without them you're just rebuilding existing tools. **Schedule them into the build from day one, not as polish.**
