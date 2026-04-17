I have enough research. Let me now compose the comprehensive footprint design playbook.

---

# DEEP6 Footprint & Orderflow Visual Design Playbook

**The reference manual for the NinjaTrader 8 SharpDX rendering agent. Every cell layout, every imbalance highlight, every color, every threshold — distilled from Bookmap, ATAS, Sierra Chart, Quantower, NT8 OFA, Jigsaw, Trader Dale, Axia Futures, and academic microstructure research.**

Audience: an AI agent that will write SharpDX `OnRender()` code for footprint, DOM heatmap, CVD, profile, absorption/exhaustion overlays, and trade annotations on NQ futures. It must produce designs that are readable at six bars wide AND at two hundred bars wide, accessible in light and dark themes, performant at 60 fps with 200 visible bars × 30 price levels, and visually communicate the DEEP6 thesis: **absorption and exhaustion are the highest-alpha reversal signals**.

---

## 1. The Footprint Cell — Anatomy & Every Variant

The footprint cell is the atomic unit of the entire system. A "bar" is a vertical stack of cells, one per price tick (or per `Ticks per Level` aggregation). NT8 calls this a *Volumetric Bar*; ATAS calls it a *Cluster*; Sierra calls it a *Numbers Bar*; Quantower calls it a *Cluster Chart*. They all render the same fundamental object: **a rectangle representing one price level inside one time bucket, displaying microstructure data**.

### 1.1 The seven canonical cell layouts

| Layout | Cell content | When to use | Width pressure |
|---|---|---|---|
| **Bid x Ask (split)** | `123 x 456` — bid volume left, ask volume right, separator in middle | Default professional view; required for absorption & imbalance reading | Wide cells (≥ 60 px) |
| **Delta** | Single signed number `+333` or `-128`, color-coded | Compressed bars, multi-bar context, beginners | Narrow OK (≥ 30 px) |
| **Volume (total)** | Single number `579` | Volume profile overlay use, highest-volume search | Narrow OK |
| **Profile (histogram-in-cell)** | Horizontal bar inside cell, length = % of bar's max volume | Compact macro view; lets you spot POC at a glance | Width irrelevant |
| **Trades (count)** | `42` (number of trades), often paired with volume | Detecting iceberg fills (high trade count, even bid/ask) | Narrow |
| **Bid/Ask + Profile (Sierra "Split Profile")** | Split horizontal bar: left half = bid volume length, right half = ask volume length | Most information-dense per pixel | Medium |
| **Delta + Volume (Quantower "Double")** | Two stacked rows: top = delta, bottom = volume | When traders want both flow and participation in one cell | Tall cells (≥ 24 px) |

### 1.2 ASCII anatomy of the canonical Bid x Ask cell

```
 ┌──────────────────────────────────────┐
 │  bid_vol  │ separator │  ask_vol     │   ← one price level (one tick)
 │   123     │     x     │     456      │   ← right-align bid, left-align ask
 └──────────────────────────────────────┘
   ↑        ↑           ↑
   tabular  separator   tabular
   monospace  is        monospace
   right-    decorative left-
   aligned   ('x','|',' ') aligned
```

**Critical rule: numbers must be tabular (monospace digits)** — otherwise the eye cannot scan a column of cells fast. Use JetBrains Mono, IBM Plex Mono, or any sans monospace; in WPF/SharpDX use a font with tabular figures via `font-feature-settings: "tnum"` equivalent. NT8 default is Arial which lacks proper tabular figures — **override this**.

### 1.3 Stacked vs side-by-side variants

- **Side-by-side (default):** `bid x ask` reads horizontally. Best for wide cells. The standard since X-Trader/CQG.
- **Stacked (bid above ask):** Saves horizontal space; harder to read at speed. Used by some Sierra layouts.
- **Diagonal:** Bid value at upper-left, ask value at lower-right (or vice versa). Visually encodes the diagonal-imbalance comparison rule. Niche; ATAS supports.
- **Centered single value:** Just delta or volume, centered in cell. The "compressed" mode for zoomed-out views.

### 1.4 Cell sizing recommendations (NT8 SharpDX coordinates)

| Mode | Cell width | Cell height | Font px | Padding (px) | Use when |
|---|---|---|---|---|---|
| **Macro** | 18–28 | 8–12 | 7 | 1 | > 80 visible bars |
| **Normal** | 36–60 | 14–18 | 9 | 2 | 30–80 visible bars |
| **Detail** | 72–110 | 20–28 | 11 | 3 | 10–30 visible bars |
| **Forensic** | 120–180 | 30–40 | 13–14 | 4 | < 10 bars (replay/post-mortem) |

**Rule:** if `cellWidth < 36 px` → auto-collapse to Delta layout. If `cellWidth < 22 px` → auto-collapse to Profile-only layout. Never render text smaller than **7 px** — it becomes anti-aliased mush in DirectWrite.

### 1.5 Text alignment within cells

- Right-align bid (`\t`-like padding from middle), left-align ask. **Never** left-align both — the eye loses the column.
- Decimal-align if fractional volumes are possible (rare in futures; always integers in NQ).
- The separator (`x`, `|`, `·`, or just a space) should be **dimmer** than the numbers — about 40% opacity of the text color. It's a visual divider, not data.

### 1.6 Compact vs full

When zoomed out, sacrifice in this order:
1. Drop the separator character (use whitespace).
2. Drop the leading zeros, render `1k` / `1.2k` / `12k` for values ≥ 1000.
3. Switch to delta layout.
4. Switch to profile-bar-only layout.
5. Switch to a single colored line per cell (heatmap mode).

---

## 2. Imbalance Highlighting — The Single Most Important Visual Mechanic

Imbalance is what separates a "footprint chart" from "a candlestick with numbers." It must be **immediately and unmistakably visible** without overwhelming the rest of the chart.

### 2.1 Threshold defaults across platforms

| Platform | Default ratio | Notes |
|---|---|---|
| **NT8 OFA Volumetric Bars** | **1.5** (i.e., one side ≥ 150% of other) | Plus minimum delta of 10 |
| **ATAS** | **150%** | Diagonal default |
| **Sierra Chart** | Compare thresholds 0.25 / 0.50 / 0.75 (4 tiers) | Plus actual volume thresholds 100/200/300 |
| **Quantower** | User-configured, 200% common | Diagonal mode is the default |
| **TradingView Volume Footprint** | 300% (3x) for "real" imbalance | The 3x convention came from the original Investor RT/MarketDelta era |
| **Trader Dale's pedagogy** | **300% / 3x** for "trading-quality" imbalance | What most retail education uses |

**DEEP6 recommended defaults:**
- **150%** → "weak imbalance" — subtle highlight (1 px border tint)
- **300%** → "strong imbalance" — full highlight (filled cell tint + 1 px border)
- **400%+** → "extreme imbalance" — full highlight + glow
- **Minimum absolute volume:** 10 contracts (NQ has 5 lot common; 10 prevents flagging noise)

### 2.2 Diagonal vs horizontal comparison

This is non-obvious and matters a lot.

- **Horizontal:** compare `bid[N]` vs `ask[N]` at the **same** price level. Catches level-by-level battles.
- **Diagonal (industry preferred):** compare `bid[N]` vs `ask[N+1]` (the ask one tick *above*). The reasoning: an aggressive seller hitting bid at price N and an aggressive buyer lifting ask at price N+1 *cannot logically be the same trade*. Diagonal comparison prevents counting the same auction twice and matches the actual mechanics of how trades cross the spread.

**NT8, ATAS, Sierra, Quantower all default to diagonal.** DEEP6 should default to diagonal and only expose horizontal as a debugging mode.

```
DIAGONAL IMBALANCE LOGIC
─────────────────────────
                        Price Level
        bid_vol          ↓             ask_vol
  ┌───────────┐ ┌──┐ ┌─────────────┐
  │           │ │N+│ │   ASK[N+1]  │ ← compare ASK[N+1] vs BID[N]
  │           │ │1 │ │             │   (ratio ASK[N+1] / BID[N])
  └───────────┘ └──┘ └─────────────┘
  ┌───────────┐ ┌──┐ ┌─────────────┐
  │  BID[N]   │ │N │ │             │ ← compare BID[N] vs ASK[N-1]
  │           │ │  │ │             │   (ratio BID[N] / ASK[N-1])
  └───────────┘ └──┘ └─────────────┘
```

### 2.3 Stacked imbalances — the highest-alpha visual signal

A "stacked imbalance" = ≥ 3 consecutive price levels with imbalance in the same direction. This is the dominant retail/prop-firm setup taught by Trader Dale and Axia Futures. **It must be visually unmistakable.**

DEEP6 design:
- Single imbalanced cell → cell border tint
- 2 stacked → border + small triangle marker on left edge
- **3+ stacked → vertical line on the chart's right gutter spanning the stack range, plus a label "S3"/"S4"/"S5"**, plus a horizontal "zone" rectangle drawn at the price range (this becomes a tradable S/R level for replay)

Color convention: **buy-side stack = bright green/cyan vertical line; sell-side stack = bright red/magenta vertical line.** These zones should persist on the chart even after the bar closes — they are *the most actionable visual artifact* on a footprint chart.

### 2.4 Color treatments per imbalance state

| State | Cell fill | Cell border | Text weight | Glow |
|---|---|---|---|---|
| Normal | base bid/ask color, 30% opacity | none | Regular | none |
| 150–250% imbalance | base color, 50% opacity | 1 px tint | Regular | none |
| 250–400% imbalance | accent color, 70% opacity | 1.5 px solid | Semi-bold | none |
| 400%+ imbalance | accent color, 90% opacity | 2 px solid | Bold | 4 px outer glow at 30% alpha |
| Stacked (3+) | as above per cell | + connecting bar in chart gutter | Bold | persistent zone shading |
| Buying climax (large delta + price stalls) | base + diagonal hatching | 2 px dashed | Bold | pulse animation 0.5 Hz, 2 cycles |
| Selling climax | mirror of buying climax | | | |
| Failed auction (high vol single-print at extreme then reversal) | full cell + X overlay | 2 px solid | Bold + italic | flash once on detection |

### 2.5 Specific color recommendations for imbalances (dark theme)

| Element | Hex | Rationale |
|---|---|---|
| Buy imbalance fill | `#00E676` at 70% alpha | Bright green, distinct from normal-cell green |
| Buy imbalance border | `#00E676` at 100% | Crisp edge |
| Sell imbalance fill | `#FF1744` at 70% alpha | Bright red-magenta, distinct from normal-cell red |
| Sell imbalance border | `#FF1744` at 100% | |
| Stacked-buy zone shading | `#00E676` at 12% alpha | Persistent zone, low intensity |
| Stacked-sell zone shading | `#FF1744` at 12% alpha | |
| "Extreme" imbalance accent (400%+) | `#FFEA00` (gold) border on top of fill | Gold = "look here NOW" |

For light theme: use `#00897B` (teal) and `#D32F2F` (red), since pure bright greens vanish on white.

---

## 3. Delta Visualization

Delta is the second-most-read number on a footprint chart. It appears in three places:

1. **Per-cell delta** (Delta layout)
2. **Per-bar delta** (bar statistics row at bottom)
3. **Cumulative delta** (separate pane or overlay)

### 3.1 Per-bar delta gradient

Use a **diverging color scale** anchored at zero. Bookmap, NT8, ATAS all use this:

```
 Strong sell        Neutral         Strong buy
  -∞                  0                  +∞
  ████─────────────────────────────████
  #B71C1C   #EF5350  #424242  #66BB6A   #1B5E20
  (deep)    (red)   (gray)    (green)   (deep)
```

NT8's `Strength Sensitivity` defaults to **20 levels** of gradient. DEEP6 should match this default — too coarse (5 levels) and the gradient is steppy; too fine (50+) and humans can't distinguish adjacent shades.

### 3.2 Cumulative delta visualization — three styles

| Style | Layout | Pros | Cons | Best for |
|---|---|---|---|---|
| **CVD line** in subpane | Smooth line, with histogram fills below | Clean, easy divergence reading | Adds a pane | Default for all DEEP6 charts |
| **CVD candles** | OHLC bars built from CVD instead of price | Shows CVD's own structure | Confusing initially | Advanced traders |
| **CVD overlay** on price pane | Faint line overlaid on price (different scale) | No extra pane | Crowds price | Compact mode |

### 3.3 Delta divergence highlights

This is one of the highest-value visual features. When price makes a higher high but CVD makes a lower high → **bearish divergence** (and vice versa).

Visual treatment:
- Draw a thin dashed line (1 px, 50% opacity) from the prior swing high on price to the new swing high on price
- Draw the corresponding line on the CVD pane
- If they diverge, render the price line in **gold (`#FFD600`)** and add a small "÷" glyph at the right end
- Label: "BEAR DIV" or "BULL DIV" in 8 px monospace, semi-transparent

### 3.4 Max/Min delta markers

Within each bar, NT8 highlights the cell with the highest delta in **yellow** (`#FFEA00`) by default. This is good — keep it but use a thin border instead of fill so it doesn't fight with imbalance highlighting. Add a tiny `▲` glyph for max-positive-delta cell and `▼` for max-negative-delta cell.

---

## 4. Volume Profile / Market Profile

### 4.1 The four canonical profile elements

| Element | Definition | Visual convention |
|---|---|---|
| **POC** (Point of Control) | Price level with most volume in the period | **Solid horizontal line, 2 px**, bright color (`#FFD600` gold) |
| **VAH** (Value Area High) | Top of the 70% volume range | Dotted line, 1 px, white (`#E0E0E0`) |
| **VAL** (Value Area Low) | Bottom of 70% volume range | Dotted line, 1 px, white |
| **Value Area shading** | Region between VAH and VAL | Filled rectangle, 8% alpha, neutral white/gray |

The 70% threshold is *not arbitrary* — it's one standard deviation from a normal distribution.

### 4.2 Profile placement modes

| Mode | Where | Use |
|---|---|---|
| **Right-attached** | Histogram on right edge of bar | Default for per-bar profiles |
| **Left-attached** | Histogram on left edge | When right edge has another overlay |
| **Step** | Bars step out into next time slot | Multi-period composite |
| **Floating** | User-positioned anywhere | Ad-hoc analysis |

### 4.3 Naked VPOCs (Virgin Points of Control)

A "naked" or "virgin" POC is a prior session's POC that price has not yet revisited. These are very high-probability magnets.

Visual: extend the prior POC line **forward in time** at 50% opacity until price touches it. On touch, fade it out over 5 bars to mark "filled." This requires per-frame state in `OnRender()`.

### 4.4 TPO (Time Price Opportunity) lettering

Classic Market Profile uses 30-min letters (A, B, C…). Most modern systems use blocks instead. For DEEP6:
- Letters at **8 px monospace** when zoomed in
- Switch to colored blocks (1 cell per TPO) when too small for letters
- Color the **Initial Balance** TPOs (first hour: A and B) in a distinct shade — `#7E57C2` (purple)
- **Single Prints** (TPOs touched only once) get a 1 px outline to mark them as untested liquidity gaps

### 4.5 Composite vs session profiles

- Session profile = single day. Per-bar opacity 100%.
- Composite (multi-day) = aggregated. Render at 40% opacity *behind* the session profile so both are visible. Use a different hue (e.g., session = teal, composite = blue-violet).

---

## 5. Heatmap Rendering (Bookmap-style)

A heatmap visualizes resting limit-order liquidity over **time** — the missing dimension in a static DOM.

### 5.1 Color gradient — the Bookmap convention

```
  Low liquidity ────────────────────────► High liquidity
  
  Cool ─────────────────────► Hot
  #0D47A1 (deep blue)
       #1976D2 (blue)
            #00ACC1 (cyan)
                 #FFB300 (amber)
                      #F4511E (orange-red)
                           #FFFFFF (white-hot)
```

Bookmap's exact gradient uses a perceptually uniform **viridis-meets-inferno** style: blue → cyan → green → yellow → red → white. The white-hot peak indicates the strongest resting walls.

For DEEP6 NQ rendering:
- Background: `#0A0E1A` (near-black with cool tint)
- Use a 256-step LUT (lookup table) precomputed at indicator initialization to avoid per-pixel math in `OnRender()`
- Map liquidity → log scale (linear leaves you with all-blue except for whales)

### 5.2 Time decay

Historical liquidity that has since been pulled or filled should fade out over time. Standard approach:
- Fully opaque while present
- Fade to 60% over 30 seconds after pull
- Fade to 0% over the next 5 minutes

This creates the classic "ghost trail" of pulled liquidity, which itself becomes an actionable signal (spoofing detection).

### 5.3 Trade bubble overlay

Dots/bubbles overlaid on the heatmap encode aggressive market trades:
- **Green bubble** = aggressive buy (lifted offer)
- **Red bubble** = aggressive sell (hit bid)
- **Half-and-half bubble** = balanced trade pair
- Bubble **radius ∝ √(trade size)** — sqrt scaling so a 1000-lot doesn't cover the chart
- Bubble **alpha** decays over 10 seconds to indicate "recent vs less-recent"

### 5.4 Iceberg detection visualization

When a level absorbs >> its visible size, mark it with:
- A **diamond glyph** at the price level
- Label: `ICE: 2400` (cumulative absorbed beyond visible)
- Color: bright cyan (`#00E5FF`) — distinct from buy/sell

### 5.5 Spoofing/pulled liquidity flash

When a large resting order disappears without being filled (bid pulled, ask pulled):
- Single-frame **white flash** on the price level
- Followed by accelerated decay (fade in 1 second)
- Optional: small `↶` glyph for "pulled"

---

## 6. DOM Visualization

### 6.1 Vertical ladder vs horizontal bars

Vertical ladder (price down the center column, bid on left, ask on right) is the universal convention. Jigsaw, X-Trader, CQG, NT8 SuperDOM, ATAS DOM all use this.

```
 ┌──────────┬─────────┬──────────┐
 │  BID Q   │  PRICE  │  ASK Q   │
 ├──────────┼─────────┼──────────┤
 │      120 │ 18452.50│          │   ← best ask
 │      245 │ 18452.25│          │
 │      387 │ 18452.00│          │
 │          │ 18451.75│      450 │   ← best bid
 │          │ 18451.50│      623 │
 │          │ 18451.25│      891 │
 └──────────┴─────────┴──────────┘
```

### 6.2 Bid/ask coloration

- Bid quantities: `#1565C0` (medium blue) bars
- Ask quantities: `#C62828` (medium red) bars
- Quantity bar length = log scale of size, capped at column width
- Quantity number inside or to side of bar (left for ask side, right for bid side — outside the bar so the bar reads cleanly)

### 6.3 Recent change highlights

- **Adds:** background flash green for 200 ms then fade
- **Removes/pulls:** background flash white-yellow for 200 ms then fade
- **Fills:** background flash cyan for 400 ms (longer because it's a real event)

### 6.4 Order book imbalance gauge

Top-of-DOM micro-widget: a horizontal bar 100 px wide, divided proportionally to total bid vs total ask volume across N levels. Color split bid-blue / ask-red. Center marker = 50/50. When imbalance > 70/30, pulse the dominant side.

### 6.5 Big order detection

Threshold (NQ): `≥ 200 contracts at one level`. Treatment:
- Bar background changes to gold (`#FFC107`)
- Add `★` glyph
- If order persists > 30 seconds, escalate to glow

---

## 7. Tape (Time & Sales) Visualization

### 7.1 Aggressor coloration

| Trade type | Color | Background |
|---|---|---|
| Aggressive buy (at ask) | `#00E676` | transparent |
| Aggressive sell (at bid) | `#FF1744` | transparent |
| Mid-market | `#9E9E9E` | transparent |
| Block trade (≥ 50 NQ) | original color | `#FFD600` background tint |

### 7.2 Size emphasis

Critical for fast tape reading:
- 1 lot: 9 px regular
- 2–9 lots: 9 px semi-bold
- 10–49 lots: 11 px bold
- 50+ lots: 13 px bold + background tint
- 100+ lots: 14 px bold + background + flash on arrival

### 7.3 Aggregation patterns (Jigsaw Reconstructed Tape style)

Group trades within a **2-second sliding window at the same price** into a single line:
```
[14:32:15.234]  +47 @ 18452.50   (12 trades aggregated)
```
Show original trade count in dim text. This is the Jigsaw reconstructed-tape secret — it lets you see one 47-lot buy instead of forty-seven 1-lot prints.

### 7.4 Block trade highlighting

Trades ≥ 95th percentile of recent activity get a 1 px gold border around the row. Trades ≥ 99th percentile get a brief horizontal flash across the entire tape pane.

---

## 8. Cumulative Volume Delta (CVD)

Treated above (§3.2–3.3); additional design notes:

### 8.1 Reset behaviors

- **Session reset** (default): CVD resets at session open (NQ: 17:00 CT). Render a vertical dashed line at reset.
- **Continuous (untruncated):** Useful for long-context analysis but loses scale meaning.
- **Custom anchor:** User clicks a bar → CVD anchors there.

### 8.2 CVD-vs-Price divergence panel

Best-in-class: a small chart-in-chart at top-right corner showing the last 30 bars' price as a sparkline overlaid with CVD as a second sparkline (different color, secondary axis). Divergence becomes immediately visible without leaving the main view.

---

## 9. Absorption & Exhaustion — DEEP6's Core Visual Signals

These get the **most prominent** treatment because they ARE the trading thesis.

### 9.1 Absorption visual

**Definition:** Heavy aggressive volume hits a price level but price does not move. Limit orders absorb the aggression.

```
DETECTION RULE (visual):
- Cell has high volume AND price stalls for ≥ 2 bars at this level
- Often paired with high bid AND high ask volume at same level (both sides eating)
- Or one side stays imbalanced while the close stays the same
```

**Visualization:**
1. The absorption cell gets a **2 px solid white border** that pulses (animate alpha 70% → 100% → 70% over 1.2 seconds) for 5 cycles, then settles at 100%
2. A horizontal line is drawn from the cell extending 5 bars to the right at 80% opacity, then fading
3. Label: `ABS  2400/3100` (volumes that hit but didn't move price)
4. The label is in **electric cyan (`#00E5FF`)** — the DEEP6 absorption signature color

The pulse uses the SharpDX timer in `ChartControl.OnRender()`. Use sparingly: max 1 active pulse per chart at a time, otherwise UX becomes carnival.

### 9.2 Exhaustion visual

**Definition:** A move running out of steam — heavy delta in trend direction, but price barely advances at the extreme.

**Visualization:**
1. The exhaustion cell gets a **gradient fade** — strong color at the body of the candle, fading to white toward the wick tip
2. A **comet-tail glyph** drawn from cell into the wick area
3. Label: `EXH  ↓` or `EXH ↑` arrow indicating the direction of the failed push
4. Color: **electric magenta (`#FF00E5`)** — DEEP6 exhaustion signature color

### 9.3 Confidence score visualization (for DEEP6's 44-signal synthesis)

DEEP6 produces a unified 0–100 confidence score. Render this as a **vertical bar gauge** anchored to the right edge of the chart, color-graded:

```
 ┌──┐
 │██│  100
 │██│   90  ← DEEP6 confidence currently
 │██│   80
 │░░│   70
 │░░│   60
 │░░│   50
 │░░│   40
 │░░│   30
 │░░│   20
 │░░│   10
 └──┘    0
```

Color stops:
- 0–30: `#424242` (gray, "no signal")
- 30–50: `#90CAF9` (pale blue, "weak")
- 50–70: `#42A5F5` (blue, "watching")
- 70–85: `#FFC107` (amber, "actionable")
- 85–100: `#00E5FF` cyan + glow ("HIGH CONVICTION")

When the gauge crosses into the top tier, optionally trigger a single-frame chart border flash.

### 9.4 Multi-signal confluence sparkline

Below the confidence gauge, a tiny 44-cell heatmap (one cell per signal, 4 px each) shows which signals are firing right now. Each cell:
- Black = inactive
- Dim color = mild signal
- Bright = strong signal
- Hover (NT8 hit-test) → tooltip with signal name + value

This is the "what's lighting up" diagnostic readout, modeled after multi-channel oscilloscope displays.

### 9.5 Trade entry/exit annotation conventions

| Event | Glyph | Color | Position |
|---|---|---|---|
| Long entry | `▲` filled triangle | `#00E676` | Below bar |
| Short entry | `▼` filled triangle | `#FF1744` | Above bar |
| Long exit (target) | `●` filled circle | `#00E676` outline | At exit price on bar |
| Long exit (stop) | `✕` X mark | `#FF6E40` | At exit price |
| Short exit (target) | `●` filled circle | `#FF1744` outline | At exit price |
| Short exit (stop) | `✕` X mark | `#FF6E40` | At exit price |
| Trail stop | `┐ ┘` corner brackets | `#FFB300` dashed | Trailing the price |
| Take-profit zone | filled rect | `#00E676` 15% alpha | from entry to target |
| Stop-loss zone | filled rect | `#FF1744` 15% alpha | from entry to stop |

A trade is shown as a connected line: entry triangle → curve → exit dot/X. The line color matches the side. P&L label floats above the exit point: `+$240` or `-$120`.

---

## 10. Confidence/Probability Visualization

Beyond §9.3's gauge:

### 10.1 Multi-bar small multiples

For backtesting/replay views, render a horizontal strip of mini gauges, one per recent signal event, so you can see the conviction history at a glance:

```
[●●●○○] [●●●●○] [●●○○○] [●●●●●] ←  recent confidence per event
```

### 10.2 Stacked bar (component contributions)

When the agent designs a "why did the system trade?" panel, decompose the confidence into its top contributors as a stacked horizontal bar:

```
 [E1: 18][E2: 14][E5: 12][E10: 11][others: 27] = 82
```
Each segment colored by signal family.

### 10.3 Heatmap of historical signal performance

A 2D grid showing signal × time-of-day → win-rate. Useful for the "when is each signal good?" page in the analytics dashboard. Use the same cool-to-hot LUT as the liquidity heatmap for consistency.

---

## 11. Chart Annotations

### 11.1 Position size indicator

Top-left corner badge: `LONG 2 @ 18452.25` with a colored ribbon. Size of ribbon = position size relative to max risk allocation.

### 11.2 Risk/reward shaded regions

When a trade is open, render two filled rectangles:
- Profit zone: from entry to take-profit, `#00E676` at 15% alpha
- Loss zone: from entry to stop, `#FF1744` at 15% alpha

These should be **clipped behind** the price/footprint cells so they don't obscure data.

---

## 12. Multi-timeframe Visualization

### 12.1 HTF bias indicator placement

Top-right corner (the "metadata corner"):
```
 ┌─────────────────────────────┐
 │ NQ 1m │ HTF: 5m ↑ │ K: +0.4 │  ← header strip
 └─────────────────────────────┘
```
- HTF directional bias as colored arrow
- Kronos E10 directional score as small numeric

### 12.2 Lower-TF detail with HTF context

Render HTF candles as **faint outlines behind** the main TF bars. 30% opacity, no fill, just outlines. The eye can locate the HTF structure without it dominating.

### 12.3 Synced crosshairs

When user moves crosshair on price pane, mirror the X-axis position on CVD/profile/heatmap subpanes. NT8 supports this via `ChartControl.CrossHairChanged`.

---

## 13. Information Panels & Overlays

### 13.1 Header strip (top of chart)

Layout, left to right:
```
[symbol] [tf] [O H L C] [Vol] [Δ] [POC] [VAH/VAL] [HTF bias] [K E10] [confidence]
```

Each segment fixed-width; uses **9 px tabular monospace**; subtle vertical separators (`#424242`) between segments.

### 13.2 Footer status bar

Bottom, lower priority info:
```
[connection: RITHMIC OK] [latency: 12ms] [bars: 487] [data: tick replay] [time]
```
Render in 8 px, dimmed (60% opacity) to recede.

### 13.3 Floating tooltip on hover

On cell hover (using `ChartControl` mouse hit-testing):
```
 ┌─────────────────────┐
 │ 18452.25            │
 │ Bid: 1230  Ask: 287 │
 │ Δ: -943             │
 │ Trades: 88          │
 │ POC: yes            │
 │ Imb: bid 4.3x       │
 │ Time: 14:32:18      │
 └─────────────────────┘
```
Background: `#1E1E1E` at 95% alpha. Border: 1 px `#424242`. Padding: 6 px. Max width 200 px.

### 13.4 Watermark conventions

NT8 native watermark: `NQ 06-26  1 Minute  Volumetric` in the chart background at 8% opacity. Keep it. Add DEEP6 brand mark if appropriate, also at 8%.

---

## 14. Color Semantic Standards for Orderflow

### 14.1 Master palette (DEEP6 dark theme)

```
BACKGROUNDS
─────────────────────────────────────────
chart_bg            #0A0E1A   near-black, cool tint
panel_bg            #12182B   slightly lighter for panels
gridline            #1E2538   subtle grid
divider             #2A3349   between sections
hover_bg            #1A2138   cell hover

PRIMARY SEMANTIC
─────────────────────────────────────────
buy / bid           #00E676   bright green (delta-positive)
sell / ask          #FF1744   bright red (delta-negative)
neutral             #9E9E9E   gray
mid                 #00BCD4   teal (mid-market trades)

SIGNALS (DEEP6-specific)
─────────────────────────────────────────
absorption          #00E5FF   electric cyan
exhaustion          #FF00E5   electric magenta
confluence high     #FFD600   gold
confidence top      #FFFFFF   white (with glow)
imbalance buy       #00E676   matches buy
imbalance sell      #FF1744   matches sell
extreme imbalance   #FFEA00   gold accent border on top

LEVELS
─────────────────────────────────────────
POC                 #FFD600   gold solid line
VAH / VAL           #E0E0E0   white dotted
naked POC           #FFD600 @ 60%  faded gold
session boundary    #7E57C2   purple dashed

TEXT
─────────────────────────────────────────
text_primary        #ECEFF1   off-white
text_secondary      #B0BEC5   gray-blue
text_dim            #607D8B   muted
text_buy            #69F0AE   slightly brighter than fill green
text_sell           #FF8A80   slightly brighter than fill red

POSITION / TRADE
─────────────────────────────────────────
long_marker         #00E676
short_marker        #FF1744
target_line         #00E676 @ 60%  dashed
stop_line           #FF6E40 dashed
trail_line          #FFB300 dashed
profit_zone         #00E676 @ 15%
loss_zone           #FF1744 @ 15%

ALERTS / FLASHES
─────────────────────────────────────────
new_order_flash     #00FF00 single-frame
fill_flash          #00BCD4 400ms
pull_flash          #FFFF00 200ms
big_order_pulse     #FFC107 1Hz
```

### 14.2 Light theme equivalents

For light mode (rare on trading desks but required for some users):
- Backgrounds: `#FAFAFA` / `#FFFFFF`
- Buy: `#00897B` (teal — bright greens vanish on white)
- Sell: `#D32F2F`
- Absorption: `#0091EA`
- Exhaustion: `#D500F9`
- POC: `#FF6F00` (deeper amber)

### 14.3 Color-blind accessibility

WCAG requires 3:1 contrast for graphical elements. The DEEP6 palette above passes for buy/sell vs background. **But green/red is the worst pairing for deuteranopia (most common)**. Mitigations:
- Encode buy/sell in **shape AND color**: triangles up/down, not just color
- Encode imbalance with **border style** in addition to color (solid vs dashed)
- Provide a "deuteranopia mode" alt palette: blue (`#2196F3`) for buy, orange (`#FF9800`) for sell — both colors that protanopes/deuteranopes can distinguish

---

## 15. Innovative / Award-Worthy Ideas Not Yet Mainstream

These are ideas the agent should consider when asked to design something *new* rather than copy existing platforms.

### 15.1 Animated POC strength pulse

The POC line on a developing session breathes (alpha 80%→100%→80% at 0.3 Hz) with intensity proportional to how dominant it is. If it's a textbook 2σ POC, slow gentle pulse. If it's a generational liquidity magnet, faster + glow. **Subtle**, not arcade.

### 15.2 Liquidity flow vector field (WebGL — for the Next.js dashboard, not NT8)

Treat the order book as a vector field. Aggressive market orders are forces. Render as flowing particles trailing through the heatmap, like wind on a weather map. This is gimmick-territory but for the dashboard's "liquidity flow" tab it's beautiful and informative.

### 15.3 Audio sonification

Map per-bar delta intensity to a soft chime. Buy delta = warm pad; sell delta = cool pad. Volume = velocity. Designed for ambient awareness while focused on something else. **Off by default**, opt-in toggle.

### 15.4 Trade impact particle effects

When a large trade prints, a **single, brief, low-saturation particle burst** at the price level. Think Linear/Stripe-tier subtle motion, not arcade game. Particles fade in 600 ms. Triggered only for trades above the 99th percentile.

### 15.5 Bloomberg-meets-Linear aesthetic

The Bloomberg Terminal taught traders to associate **information density** with **professionalism**. Linear taught designers to associate **typographic restraint and modern monochrome accents** with **quality**. The DEEP6 visual brand should sit at this intersection:
- Bloomberg-tier density (no wasted pixels)
- Linear-tier typography (Inter for UI, JetBrains Mono for numbers)
- One accent color per signal, never more
- Dark backgrounds with **luminance hierarchy** instead of color hierarchy
- Animation only for events, never decoration

### 15.6 Cyberpunk done tastefully

If a "neon mode" is requested:
- Background `#08051A` (deep indigo-black)
- Buy `#00FFC8` (mint neon)
- Sell `#FF006E` (hot pink neon)
- Outer glow on actionable signals only (8 px, 30% alpha)
- Subtle vignette darkening at chart edges to focus attention center

The trick is **using the neon vocabulary on the same restrained grid**. Don't add CRT scanlines. Don't add glitch text. The neon is the only departure.

### 15.7 Generative-art inspired backgrounds

Behind the chart, a very subtle **Voronoi mesh** pattern (1% opacity) that responds to volatility. Not animated — just present. Adds character without distracting.

### 15.8 "Trade ghost" replay overlay

In replay mode, render a faint version of where the price went *next* (the future, played back). This makes post-mortem analysis far more powerful — you can study setups against their actual outcomes visually.

### 15.9 Imbalance lineage

When a stacked imbalance level gets retested later, animate a **brief connecting line** between the original imbalance and the retest. Visually demonstrates the level's continued relevance.

### 15.10 Heatmap diff overlay

Toggle: show today's heatmap **minus** yesterday's at the same time. Reveals where today's liquidity profile differs from typical, pointing to event-driven setups.

---

## 16. Real-World Platform Comparison

| Feature | Bookmap | ATAS | Sierra Chart | NT8 OFA | Quantower | Jigsaw | DEEP6 target |
|---|---|---|---|---|---|---|---|
| Cell layouts | n/a (heatmap) | 10+ | 16+ | 2 | 3 | n/a | 8 |
| Imbalance default | n/a | 150% | tiered | 1.5x + 10 | user-set | n/a | 150/300/400 tiered |
| Diagonal imbalance | n/a | yes | yes | yes | yes | n/a | yes (default) |
| Stacked imbalance markers | n/a | yes | partial | no native | yes | n/a | yes (with zones) |
| Heatmap | core | basic | extension | none | basic | none | full Bookmap-style |
| CVD | yes | yes | yes | yes (sub) | yes | yes | yes (multi-style) |
| Absorption detection | manual | manual | manual | manual | manual | manual | **auto + visual** (DEEP6 edge) |
| Exhaustion detection | manual | manual | manual | manual | manual | manual | **auto + visual** (DEEP6 edge) |
| Color theme variants | 3 | 5+ | many | many | 5+ | few | dark default + light + neon |
| Reconstructed tape | partial | yes | partial | no | yes | **yes (signature)** | yes (Jigsaw-style aggregation) |
| Volume profile | yes | yes | yes | yes | yes | basic | yes |

**Where DEEP6 wins:** automatic absorption/exhaustion detection with prominent visual treatment. This must be the platform's most distinctive visual feature.

---

## 17. Anti-Patterns Specific to Footprint

| Anti-pattern | Why it's bad | DEEP6 mitigation |
|---|---|---|
| Cells too small for text | Numbers become gray mush; user must zoom every time | Auto-collapse to delta/profile mode below 36 px width |
| Too many simultaneous colors | No visual hierarchy; everything screams | Limit to: 2 base (buy/sell), 2 accents (POC/imbalance), 2 signals (absorption/exhaustion) |
| Imbalance threshold too sensitive (1.2x) | Every cell flagged → noise | Default 1.5x soft, 3x hard, 4x extreme |
| Volume profile dominates | Footprint cells fight for space | Profile at 40% width of bar max |
| Heatmap saturation hides price | Liquidity wash blocks candle | Cap heatmap alpha at 75%; render price ON TOP of heatmap with 1 px outline so it's always legible |
| Animation overused | Distracting | Reserve animation for: detection events, fills, and very rare confluence triggers. Max 1 active animation per chart. |
| Centered text in narrow cells | Numbers hop horizontally as digits change | Right-align bid, left-align ask — always |
| Variable-width digits | Numbers don't line up vertically | Mandate tabular monospace fonts |
| Subtle imbalance colors that match the cell base | Imbalance vanishes into the cell | Imbalance accent must be *brighter and more saturated* than base |
| POC drawn under cells | Disappears | Render POC line on top, after cells |
| TPO letters when too small | Unreadable mush | Auto-switch to colored blocks below 8 px |
| Stacked-imbalance highlighting only on the cell | Easy to miss | ALSO add gutter line + persistent zone shading |
| Per-bar stats row with same font weight as cells | Stats compete with data | Stats row: 7 px regular, dimmer color |
| CVD overlay on price with no second axis labeled | Scale ambiguity | Always show CVD axis on right edge |
| Animated CVD line redrawing every tick | Performance hit | Throttle to 4 Hz redraw for CVD line |
| Heatmap LUT computed per pixel per frame | 60 fps becomes 12 fps | Precompute 256-entry LUT at init |

---

## 18. NT8 SharpDX Implementation Considerations

### 18.1 Built-in OFA vs custom rendering

NT8's `VolumetricBarsType` provides the data feed and basic rendering. To customize beyond NT8 defaults, the agent has two options:

| Approach | Pros | Cons |
|---|---|---|
| Override colors/settings via `BarsType` properties | Easy, integrates with chart styles | Limited to NT8's parameter set |
| Custom indicator rendering on top, with `Bars.GetBarVolumeInfo()` | Full visual control | Must reimplement cell/profile/imbalance rendering; more code |

**DEEP6 should do BOTH:**
- Use built-in `VolumetricBarsType` for the base footprint cell rendering (it's already optimized)
- Layer DEEP6-specific overlays as separate indicators that read `Bars[i].VolumeInfo` and render on top

### 18.2 Per-cell text rendering

DirectWrite via SharpDX is the right call. Use `RenderTarget.DrawText()` (faster than `DrawTextLayout()` for short snippets like cell numbers). Cache `TextFormat` instances in `OnRenderTargetChanged()` — never construct per-frame.

```csharp
// Pseudo-code pattern
protected override void OnRenderTargetChanged()
{
    cellTextFormat?.Dispose();
    cellTextFormat = new SharpDX.DirectWrite.TextFormat(
        Core.Globals.DirectWriteFactory,
        "JetBrains Mono",
        SharpDX.DirectWrite.FontWeight.Regular,
        SharpDX.DirectWrite.FontStyle.Normal,
        9.0f);
    cellTextFormat.TextAlignment = TextAlignment.Trailing; // for right-aligned bid
}
```

### 18.3 Brushes are device-dependent

Per NT8 SharpDX docs: brushes can ONLY be created during `OnRender()` or `OnRenderTargetChanged()`. Cache them in `OnRenderTargetChanged()`, dispose in `OnRenderTargetChanged()` and `OnTermination()`.

### 18.4 Performance: 200 bars × 30 levels

That's 6000 cells per frame. At 60 fps that's 360,000 cell renders per second. Optimization:
- Skip cells where `volume == 0`
- Skip cells outside the visible range (`ChartControl.CanvasRight` etc.)
- Pre-filter `Bars` you'll iterate once per frame, not per cell
- Use `RenderTarget.FillRectangle` (filled cells) before all `DrawText` calls — batch primitives by type
- For heatmap: render to a cached bitmap, only re-render changed columns

### 18.5 Cell hit-testing for hover tooltips

Use `ChartControl.MouseMove` event. Convert mouse coords to (`barIndex`, `priceLevel`) using `ChartControl.GetTimeByX()` and `ChartScale.GetPriceByY()`. Look up the cell in your indicator's data store. Render the tooltip in `OnRender()` based on stored hover state.

### 18.6 Theme switching at runtime

Listen to `ChartControl.PropertyChanged` for theme changes; rebuild cached brushes in `OnRenderTargetChanged()`. Don't hard-code colors — read from a `DeepSixPalette` static class indexed by `IsDarkTheme`.

---

## 19. Design Recipe: "Build me a DEEP6 NQ footprint chart"

Putting it all together, here's the canonical DEEP6 footprint chart composition:

### Layer stack (back to front)

1. **Background:** `#0A0E1A` solid fill
2. **Grid:** `#1E2538` 1 px lines, 5-tick horizontal spacing
3. **Heatmap:** liquidity over time, 75% max alpha, log-scaled, viridis-style LUT
4. **Volume profile:** session profile right-attached, 40% bar width, with VAH/VAL shading
5. **Naked POCs:** prior session POCs extended forward, gold @ 60% alpha
6. **Footprint cells:** Bid x Ask layout, JetBrains Mono 9 px tabular, color-coded by delta
7. **Imbalance highlights:** 150/300/400% tiered, diagonal comparison
8. **Stacked imbalance zones:** persistent shaded zones + gutter markers
9. **Candle outline:** thin (1 px) outline on top of cells so OHLC is readable
10. **POC line for current bar:** gold solid 2 px
11. **CVD overlay** (optional) at 40% alpha
12. **Absorption markers:** electric cyan with pulse animation
13. **Exhaustion markers:** electric magenta with comet-tail
14. **Trade entry/exit markers:** triangles with P&L labels
15. **Risk/reward zones:** filled rectangles at 15% alpha
16. **Crosshair:** white 1 px with price/time labels
17. **Confidence gauge:** right-edge vertical bar
18. **Multi-signal sparkline:** below confidence gauge
19. **Header strip:** symbol/TF/OHLCV/Δ/POC/HTF/K/conf
20. **Footer status bar:** connection/latency/bars
21. **Hover tooltip:** floats above all when active

### Default cell sizing (1-min NQ on a 1080p screen)

- Visible bars: 60
- Cell width: 48 px
- Cell height: 16 px
- Font: JetBrains Mono Regular 9 px
- Padding: 2 px
- Separator: dim `x` at 40% opacity
- Cell border: 0 px when normal; 1.5 px when imbalanced

### Auto-collapse rules (when user zooms out)

- Width < 36 px → drop to Delta layout
- Width < 22 px → drop to Profile-only (horizontal bar, no text)
- Width < 12 px → render bars as colored candles only (no cells), but keep imbalance zones

---

## 20. Visual States Per Market Condition

The agent should know which design recipe to invoke for each market state:

| Market state | Detection | Visual treatment |
|---|---|---|
| **Quiet/balanced** | Low volume, balanced delta | Cells at 60% saturation, no animations, neutral palette emphasized |
| **Trending up** | Sustained positive delta, higher highs | Cells slightly brighter, CVD line foregrounded, exhaustion watch active (highlight nearby resistance from naked POCs) |
| **Trending down** | Mirror of above | Mirror |
| **Absorption in progress** | High volume + price stalls | Pulse animation on absorbing level, "ABS" label, persistent zone after detection |
| **Climactic** | Extreme delta + extreme volume + reversal pattern | Full-width chart border flash (one frame), gold border on cell, prominent label |
| **Stacked imbalance forming** | 2 consecutive imbalances same direction | Subtle gutter marker; on 3rd cell, full zone activation with sound (if enabled) |
| **Failed auction** | Single print at extreme + immediate reversal | X overlay + persistent line at extreme |
| **Liquidity vacuum** | Sudden pull of large book | White flash on pulled level, decay animation, optional alert |
| **News spike** | Volatility burst above threshold | Auto-zoom out, increase cell padding, dim historical cells, focus on current bar |

---

## 21. Checklist — What "Done Right" Looks Like

When the agent finishes designing a footprint visualization, verify:

- [ ] Tabular monospace digits (no font-jitter as values change)
- [ ] Right-aligned bid, left-aligned ask
- [ ] Diagonal imbalance comparison
- [ ] Tiered imbalance thresholds (150/300/400)
- [ ] Stacked imbalance gets gutter markers + zone shading
- [ ] Absorption uses cyan + pulse, max 1 active animation
- [ ] Exhaustion uses magenta + comet-tail
- [ ] POC is gold solid line, on top of cells
- [ ] VAH/VAL shaded value area
- [ ] CVD divergence highlighted with dashed lines + DIV label
- [ ] Heatmap caps at 75% alpha so price stays readable
- [ ] Trade markers use BOTH shape AND color (color-blind safe)
- [ ] Position size + R/R zones rendered behind cells
- [ ] Hover tooltips work via `ChartControl` hit-testing
- [ ] All brushes cached in `OnRenderTargetChanged()`
- [ ] No text below 7 px
- [ ] Auto-collapse layout below 36 px / 22 px cell widths
- [ ] Light theme variant available
- [ ] Color-blind alt palette available
- [ ] Header strip shows symbol/TF/OHLCV/Δ/POC/HTF/K/confidence
- [ ] Confidence gauge anchored to right edge
- [ ] Multi-signal sparkline shows which of 44 signals are firing
- [ ] Performance: maintains 60 fps with 200 bars × 30 levels visible

---

## Sources

**Footprint chart fundamentals**
- [Volume footprint charts: a complete guide — TradingView](https://www.tradingview.com/support/solutions/43000726164-volume-footprint-charts-a-complete-guide/)
- [Footprint Charts: A Complete Guide to Advanced Trading Analysis (Optimus Futures)](https://optimusfutures.com/blog/footprint-charts/)
- [Order Flow Trading with Footprint Charts: Complete Guide 2026 (LiteFinance)](https://www.litefinance.org/blog/for-beginners/trading-strategies/order-flow-trading-with-footprint-charts/)
- [Footprint Chart Trading: Learn How to Use Order Flow and Delta (Trade The Pool)](https://tradethepool.com/fundamental/mastering-footprint-charts-trading/)
- [Footprint Charts Explained: Order Flow Trading | NinjaTrader](https://ninjatrader.com/futures/blogs/ninjatrader-order-flow/)
- [Footprint Charts Explained: Volume, Orderflow & Imbalance Guide (PriceActionNinja)](https://priceactionninja.com/footprint-charts-explained-volume-orderflow-imbalance-guide/)
- [Defining the Footprint Chart (HighStrike)](https://highstrike.com/footprint-chart/)
- [#Footprint - Orderflow chart (ClusterDelta)](https://clusterdelta.com/footprint)

**Imbalance specifics**
- [Imbalance - what is it? How to find and trade imbalance (ATAS)](https://atas.net/atas-possibilities/cluster-charts-footprint/how-to-find-and-trade-imbalance/)
- [Imbalance Charts (GoCharting)](https://gocharting.com/docs/orderflow/imbalance-charts)
- [Order Flow Day Trading Strategy - Stacked Imbalances (Trader Dale)](https://www.trader-dale.com/order-flow-day-trading-strategy-stacked-imbalances/)
- [Using Stacked Imbalances to Identify Key Market Reversals (MarketCalls)](https://www.marketcalls.in/orderflow/using-stacked-imbalances-to-identify-key-market-reversals-orderflow-tutorial.html)
- [The Most Powerful Order Flow Imbalance Setups (Trader Dale)](https://www.trader-dale.com/the-most-powerful-order-flow-imbalance-setups-full-training-9-dec-25/)
- [Order Flow Imbalance Signals (QuantVPS)](https://www.quantvps.com/blog/order-flow-imbalance-signals)

**Platform documentation**
- [Order Flow Volumetric Bars (NinjaTrader)](https://ninjatrader.com/support/helpGuides/nt8/order_flow_volumetric_bars.htm)
- [Order Flow Volume Profile (NinjaTrader)](https://ninjatrader.com/support/helpguides/nt8/order_flow_volume_profile.htm)
- [Order Flow Price On Volume Bars (NinjaTrader)](https://ninjatrader.com/support/helpGuides/nt8/order-flow-price-on-volume-bars.htm)
- [Volumetric Bars - Order Flow+ on NinjaTrader Desktop](https://vendor-support.ninjatrader.com/s/article/Volumetric-Bars-Order-Flow)
- [Use Volumetric Bars to Track Buyers & Sellers (NinjaTrader Medium)](https://ninjatrader.medium.com/use-volumetric-bars-to-track-buyers-sellers-see-order-flow-imbalance-e84171abd472)
- [Cluster Settings (ATAS)](https://help.atas.net/en/support/solutions/articles/72000606631-cluster-settings)
- [Cluster charts functionality (ATAS)](https://atas.net/blog/cluster-chart-functionality/)
- [Numbers Bars (Sierra Chart)](https://www.sierrachart.com/index.php?page=doc/NumbersBars.php)
- [Comparison of Different OrderFlow Tools in Sierra Chart (TicinoTrader)](https://www.ticinotrader.ch/comparison-of-different-orderflow-tools-in-sierra-chart-part-1/)
- [Cluster chart (Quantower)](https://help.quantower.com/quantower/analytics-panels/chart/volume-analysis-tools/cluster-chart)
- [Volume Analysis Tools (Quantower)](https://help.quantower.com/quantower/analytics-panels/chart/volume-analysis-tools)
- [Volume profiles (Quantower)](https://help.quantower.com/quantower/analytics-panels/chart/volume-analysis-tools/volume-profiles)
- [Imbalance on footprint chart and Rithmic Plug-in Mode (Quantower)](https://www.quantower.com/blog/imbalance-footprint-chart-and-rithmic-plugin)

**Bookmap & heatmap**
- [Heatmap Trading: Complete Guide to Market Depth Visualization (Bookmap)](https://bookmap.com/blog/heatmap-in-trading-the-complete-guide-to-market-depth-visualization)
- [Heatmap settings (Bookmap KB)](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapSettings)
- [Bookmap Heatmap Overview](https://bookmap.com/en/learning-center/getting-started/liquidity-heatmap/heatmap-overview)
- [Traded Volume Visualization (Bookmap KB)](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapTradedVolumeVisualization)
- [C5 Heatmap Trading for Beginners (Bookmap)](https://bookmap.com/learning-center/order-flow-phenomena)
- [Reading orderflow with Bookmap](https://www.tradethematrix.net/post/reading-orderflow-with-bookmap)

**Volume profile / Market profile**
- [Volume profile indicators: basic concepts (TradingView)](https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/)
- [Time Price Opportunity (TPO) indicator (TradingView)](https://www.tradingview.com/support/solutions/43000713306-time-price-opportunity-tpo-indicator/)
- [Value Area Explained: VAH, VAL, and POC](https://marketprofile.info/articles/value-area-explained)
- [The Ultimate Guide to Value Area Trading Strategy (QuantVPS)](https://www.quantvps.com/blog/value-area-trading-strategy-guide)
- [Market Profile aka TPO Charts (GoCharting)](https://gocharting.com/docs/orderflow/market-profile-aka-tpo-charts)
- [Volume Profile Trading: Value Area, Naked POC (Buildix)](https://www.buildix.trade/blog/volume-profile-trading-strategies-value-area-naked-poc-free-guide-2026)
- [Market Profile vs Volume Profile (Opo Finance)](https://blog.opofinance.com/en/market-profile-vs-volume-profile/)

**CVD / Cumulative Volume Delta**
- [CVD Indicator: Cumulative Volume Delta Trading Guide (LiteFinance)](https://www.litefinance.org/blog/for-beginners/best-technical-indicators/cvd-indicator/)
- [Cumulative Volume Delta (QuantVPS)](https://www.quantvps.com/blog/cumulative-volume-delta)
- [Cumulative Volume Delta Trading Strategy (Bookmap)](https://bookmap.com/blog/how-cumulative-volume-delta-transform-your-trading-strategy)
- [Cumulative delta divergence (ForexBee)](https://forexbee.co/cumulative-delta-divergence/)
- [Cumulative Volume Delta Explained (LuxAlgo)](https://www.luxalgo.com/blog/cumulative-volume-delta-explained/)

**DOM / Order book**
- [Depth of Market (DOM) Explained (QuantStrategy)](https://quantstrategy.io/blog/depth-of-market-dom-explained-using-order-book/)
- [Depth of Market (DOM) (Bookmap)](https://bookmap.com/blog/depth-of-market-dom-from-basics-to-evolution)
- [How to build an order book visualization (Databento)](https://medium.databento.com/how-to-build-an-order-book-dom-visualization-using-databento-react-and-rust-9eac46d36cf6)
- [Order Book Heatmaps and Cumulative Depth Charts (QuantStrategy)](https://quantstrategy.io/blog/order-book-heatmaps-and-cumulative-depth-charts-best/)

**Tape / T&S**
- [Listening to Jigsaw's Reconstructed Tape (PriceSquawk)](https://pricesquawk.com/listening-jigsaws-reconstructed-tape/)
- [Lesson 6 - Reconstructed Tape (Jigsaw Trading)](https://www.jigsawtrading.com/learn-to-trade-free-order-flow-analysis-lessons-lesson6/)
- [Lesson 4 - Tape Reader Setup (Jigsaw Trading)](https://www.jigsawtrading.com/learn-to-trade-free-order-flow-analysis-lessons-lesson4/)
- [Trading Software Overview (Jigsaw Trading)](https://www.jigsawtrading.com/trading-software/)

**Absorption / Exhaustion**
- [Order Flow: How to Spot Reversals with the Absorption Setup (Trader Dale)](https://www.trader-dale.com/order-flow-how-to-spot-reversals-with-the-absorption-setup-17th-feb-26/)
- [The ULTIMATE Order Flow Trading Guide (Trader Dale)](https://www.trader-dale.com/the-ultimate-order-flow-trading-guide-step-by-step-tutorial-2nd-oct-25/)
- [What is Exhaustion Candlestick? (AlphaEx Capital)](https://www.alphaexcapital.com/forex/forex-market-analysis/candlestick-patterns/what-is-exhaustion-candlestick)
- [Exhaustion Candlestick Patterns Explained (ForexBee)](https://forexbee.co/exhaustion-candlesticks/)
- [Reading Order Flow Through Candlesticks (Candle Whisperer)](https://candlewhisper.com/en/blog/2026-01-17-order-flow-candlestick-guide)

**Education / Schools**
- [The Footprint Edge Course (Axia Futures)](https://axiafutures.com/course/the-footprint-edge-course/)
- [How Can Footprint Improve Your Trade Execution (Axia Futures)](https://axiafutures.com/blog/how-can-footprint-help-your-trade-execution/)
- [Footprint Strategies (Axia Futures)](https://axiafutures.com/blog/footprint-strategies-you-can-apply-in-your-trading/)
- [Three Trading Techniques Using Footprint (Axia Futures)](https://axiafutures.com/blog/three-trading-techniques-using-footprint/)
- [Beginners Guide to Order Flow PART 1 (Trader Dale)](https://www.trader-dale.com/beginners-guide-to-order-flow-part-1-what-is-order-flow/)

**SharpDX / NT8 implementation**
- [Using SharpDX for Custom Chart Rendering (NinjaTrader)](https://ninjatrader.com/support/helpguides/nt8/using_sharpdx_for_custom_chart_rendering.htm)
- [SharpDX SDK Reference (NinjaTrader)](https://ninjatrader.com/support/helpguides/nt8/sharpdx_sdk_reference.htm)
- [SharpDX.DirectWrite (NinjaTrader)](https://ninjatrader.com/support/helpguides/nt8/sharpdx_directwrite.htm)
- [SharpDX.DirectWrite.TextFormat (NinjaTrader)](https://ninjatrader.com/support/helpguides/nt8/sharpdx_directwrite_textformat.htm)
- [SharpDX vs NinjaTrader Custom Draw.Text (NT8 Forum)](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1133587-sharpdx-vs-ninjatrader-custom-draw-text)
- [DrawTextLayout (NinjaTrader)](https://ninjatrader.com/support/helpguides/nt8/sharpdx_direct2d1_rendertarget_drawtextlayout.htm)

**Color / typography / accessibility**
- [Trading via Order Flow, new Coloring Themes (Quantower)](https://www.quantower.com/blog/order-flow-trading-in-quantower)
- [Designing the Terminal for Color Accessibility (Bloomberg)](https://www.bloomberg.com/company/stories/designing-the-terminal-for-color-accessibility/)
- [How Bloomberg Terminal UX designers conceal complexity (Bloomberg)](https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/)
- [Innovating a modern icon: Bloomberg Terminal](https://www.bloomberg.com/company/stories/innovating-a-modern-icon-how-bloomberg-keeps-the-terminal-cutting-edge/)
- [3 ways to make your charts more accessible (Flourish)](https://flourish.studio/blog/accessible-chart-design/)
- [An Accessibility-First Approach To Chart Visual Design (Smashing)](https://www.smashingmagazine.com/2022/07/accessibility-first-approach-chart-visual-design/)
- [Accessible Data Visualization in Fintech (HackerNoon)](https://hackernoon.com/accessible-data-visualization-in-fintech-why-it-matters)
- [Which fonts to use for your charts and tables (Datawrapper)](https://www.datawrapper.de/blog/fonts-for-data-visualization)
- [JetBrains Mono](https://www.jetbrains.com/lp/mono/)
- [Tabular figures - Wikipedia](https://en.wikipedia.org/wiki/Tabular_figures)
- [Clutter-Free: 3 Cs for Better Charts (NN/g)](https://www.nngroup.com/articles/clutter-charts/)

**Innovative / aesthetic**
- [Cyberpunk Neon Candle Driver (TradingView)](https://www.tradingview.com/script/QbiZ29Iu/)
- [How to Make Cyberpunk Dark Mode Data Visualizations (TDS)](https://medium.com/data-science/how-to-make-cyberpunk-dark-mode-data-visualizations-in-python-b28f82386e75)
- [How To Create a Cyberpunk Color Palette (Page Flows)](https://pageflows.com/resources/cyberpunk-color-palette/)
- [Neon Crypto Dashboard - Cyberpunk Trading Interface (Dribbble)](https://dribbble.com/shots/26769442-Neon-Crypto-Dashboard-Cyberpunk-Trading-Interface)

**Microstructure research**
- [Order Flow Imbalance in Market Microstructure (EmergentMind)](https://www.emergentmind.com/topics/order-flow-imbalance)
- [Multi-Level Order-Flow Imbalance in a Limit Order Book (Oxford)](https://ora.ox.ac.uk/objects/uuid:9b7d0422-4ef1-48e7-a2d4-4eaa8a0a7ec1/files/m89dedb16194e627a2c92d14e3329bd48)
- [Cross-impact of order flow imbalance in equity markets (Taylor & Francis)](https://www.tandfonline.com/doi/full/10.1080/14697688.2023.2236159)
- [Returns and Order Flow Imbalances (arXiv)](https://arxiv.org/html/2508.06788)
- [Getting Started with VisualHFT](https://www.visualhft.com/blog/getting-started-with-visualhft-real-time-market-microstructure-analysis)
