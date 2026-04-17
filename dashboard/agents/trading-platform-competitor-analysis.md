Excellent. Got everything I need. The Berg theme gives me confirmed Bloomberg-inspired hex codes (`#000000` background, `#f49f31` amber foreground, `#4dc7f9` cyan cursor, `#d54135` red, `#5dc453` green, `#fff799` yellow highlight). Combined with the Quantower CSS palettes, Lightweight Charts defaults (`#26a69a` / `#ef5350`), the Bloomberg color-hex palette, and the documented platform behaviors, I have enough material. Let me write the deliverable.

---

# DEEP6 Visual Design Intelligence Report
## Competitive Analysis of Best-in-Class Orderflow / Footprint Trading Platforms

**Purpose:** Build the design vocabulary for a NinjaTrader 8 graphics agent that produces award-winning UI/UX, replicating or surpassing the visual quality of Bookmap, ATAS, Sierra Chart, Quantower, Jigsaw, MotiveWave, Investor/RT, TradingView, Bloomberg Terminal, and stock NT8 OFA.

**Audience:** A code-generating agent whose outputs go to NinjaScript indicators. Every spec below is intentionally written as something the agent can lift directly: hex codes, stroke widths, type families, layout rules, semantic color assignments.

---

## 0. Master Design Doctrine (Read This First)

Across every serious orderflow platform the patterns converge on a small, learnable doctrine. The agent should treat these as defaults, only deviating when a specific signal demands it.

1. **Background is never pure black.** Pure `#000000` looks "DOS prompt" amateur. Professional platforms use near-black with a slight blue or warm bias: `#0B0D0F` (Quantower DraculaPro), `#0F1115`, `#101418`, `#0E1117` (GitHub dark), `#161A1E` (Bookmap-class navy), or `#002B36` (Solarized base03). The exception is Bloomberg Terminal, which uses true `#000000` because its amber foreground (`#FB8B1E` / `#F49F31`) needs maximum contrast; this is a brand choice, not a typographic one.
2. **Axes and grid are barely visible.** Grid `alpha 0.06–0.10`, axis lines `alpha 0.20`, axis labels `alpha 0.55`. Anything more is noise. Sierra Chart, Bookmap, and TradingView all converge here.
3. **Bid/Ask color pairs.** Three legitimate schools:
   - **Red/Green** — universal but colorblind-hostile. Use only with high-saturation, lightness-differentiated tints (`#26A69A` teal-green and `#EF5350` coral-red are the TradingView/Lightweight Charts defaults — both have similar luminance; this is intentional).
   - **Cyan/Magenta** — NT8 OFA's imbalance default (`cyan` buy, `magenta` sell). Colorblind-safe, "professional" feel, used by Bookmap for trade dots and by Bloomberg.
   - **Blue/Orange** — Bookmap "main chart" school. Blue/cyan = bids, orange/red = asks; high contrast, ages well.
4. **Yellow is reserved for "max"**: Maximum volume cell, POC, last-trade highlight. NT8 default is `Yellow`. Sierra Chart's POC defaults to a brighter yellow line. Never use yellow as a generic accent — it will always read as "this is the most important cell on screen."
5. **Monospaced tabular numerals are non-negotiable** for any cell that contains a number. Non-tabular fonts cause prices like `15234.25` and `15234.50` to wobble horizontally — instantly amateur. Use **JetBrains Mono**, **IBM Plex Mono**, or **Roboto Mono** with `font-variant-numeric: tabular-nums`. Reserve a proportional sans (Inter, IBM Plex Sans) for chrome only (panel titles, menus, tooltips).
6. **Density is a feature, not a bug.** Bloomberg, Sierra Chart, Jigsaw — the three platforms most associated with "serious traders use this" — all maximize information density. Whitespace is for marketing pages; trading windows are fully populated. The DEEP6 agent should default to dense layouts, then add breathing room only where the eye genuinely benefits.
7. **Color must encode meaning at three intensities.** A professional cell is always answering: (a) which side won (hue), (b) by how much (saturation/value), (c) is this exceptional (border/halo/glow). Three signals stacked in a single 16x16-pixel cell is what makes Bookmap and ATAS feel like they "have intelligence."
8. **No drop shadows on chart objects.** Shadows are for marketing dashboards. They smear the orderbook and destroy crosshair precision. Glows (`box-shadow` with high alpha and zero offset) are acceptable on imbalance halos and bracket-order brackets — sparingly.
9. **Crosshair = 1px, dashed `[2,2]`, alpha 0.5, neutral color.** Bookmap, TradingView, and Sierra Chart all converge on this. Tooltip box uses panel-background color with a 1px border and tabular numerals.
10. **Imbalance highlighting is the highest-leverage visual.** Whatever else the agent gets right, the imbalance treatment must be unmistakable: cyan vs magenta cell border (NT8 convention), or cell flood with semi-transparent fill, or a 2px halo. Stacked imbalances should compound (border + flood + halo on a 3-stack).

---

## 1. Bookmap — The Gold Standard for Heatmap Orderflow

Bookmap is the platform every other footprint product is measured against. Its core innovation isn't the heatmap itself but the *psychophysical mapping* it chose: brighter = denser, warm = ask side, cool = bid side, isolated dots = trades, glow = aggression. Once you've used it, every other DOM looks slow.

### Color Palette (default)

| Element | Description | Approx. Hex |
|---|---|---|
| Chart background | Near-black, barely warm (avoids the cold-blue cast of pure black with blue grid) | `#0E1014` to `#13161A` |
| Heatmap cold (low liquidity) | Deep navy, almost merging with background | `#0F1B3A` → fades to background |
| Heatmap warm (medium liquidity) | Mid-orange | `#F39200` |
| Heatmap hot (high liquidity) | Saturated red-orange | `#FF3D2E` |
| Heatmap incandescent (above upper cutoff) | Pure red / white-hot | `#FF0000` → `#FFFFFF` rim |
| Heatmap below lower cutoff | Pure black (visually disappears) | `#000000` |
| Buy aggressor dot (gradient) | Cyan → bright cyan | `#00D4FF` → `#7DF9FF` |
| Sell aggressor dot (gradient) | Magenta → bright magenta | `#FF36A3` → `#FF6BC1` |
| BBO line | Thin, semi-transparent neutral | `#9CA3AF` at alpha 0.6 |
| Last trade line | White, 1px, dashed | `#FFFFFF` alpha 0.7 |
| Crosshair | White, 1px, dashed `[3,3]` | `#FFFFFF` alpha 0.5 |
| Price ladder text | Off-white, tabular | `#E5E7EB` |
| Time axis text | Mid-gray, tabular | `#9CA3AF` |

### Layout Philosophy

Three vertical bands, edge-to-edge, no padding wasted:
- **Heatmap band (center, ~80% width):** Edge-to-edge fills. No grid lines. The heatmap *is* the grid.
- **Price ladder (right, ~80px):** Configurable columns. Defaults: Volume bars (horizontal, semi-transparent green/red), Trades counter (compact integer), Quotes counter, Quotes Delta. Each column is ~16px wide.
- **Indicator/widget panel (bottom, collapsible):** CVD, position P&L, custom widgets. Activated by a small arrow at the bottom-right of the price ladder.

### Trade Dot Rendering

Three rendering modes the agent must know:
- **Gradient** — single dot, color interpolated between the two aggressor colors based on buy/sell ratio.
- **Solid** — 2-color split (vertical split inside one circle).
- **Pie** — proportional pie chart inside the dot.

Dimensions: **2D vs 3D**. The 3D mode adds a subtle highlight/shadow inside each dot to give a "glass bead" look — it's the "premium" preset but reads as gimmicky at small sizes.

### Refresh Cadence

Rendering targets **125 fps for heatmap, 40 fps for orderflow tracking**. Anything below 30 fps is perceptibly laggy; the agent's NinjaScript renders should batch invalidates to stay above 30 fps.

### What NT8 Should Steal

- The **upper/lower cutoff** concept: liquidity below threshold disappears (background color), above threshold maxes out (pure red). Linear scaling is wrong; humans can only distinguish ~7 intensity steps in a single hue.
- The **price ladder column system**: configurable, not fixed. Each column is its own visual subsystem. Don't pack all data into the cell — split into adjacent specialized columns.
- The **edge-to-edge** rule: Bookmap has zero chrome between price ladder and heatmap. Most NT8 indicators leak default NinjaTrader chrome (gray separators, shadowed borders) — kill all of it.

---

## 2. ATAS — The Most Feature-Rich Footprint

ATAS is the platform where every imaginable footprint variant is implemented and exposed in settings. Its visual identity is more "configurable than opinionated" — but the defaults are well-tuned and the imbalance highlighting is the industry's clearest.

### Footprint Cell Modes (the Bid x Ask family)

ATAS exposes seven variants. The agent should support at minimum the first four:

| Mode | Layout | Use case |
|---|---|---|
| **Bid x Ask** | Two columns per price level — sell volume left, buy volume right | The "default" everyone recognizes |
| **Bid x Ask Ladder** | Split columns, only Delta-winning side highlighted | Cleaner reads at high zoom-out |
| **Bid x Ask Histogram** | Horizontal histogram bars inside each cell, optional numeric | Pattern reading at a glance |
| **Bid x Ask Volume Profile** | Profile shape (horizontal bar) per level, numbers overlaid | Hybrid footprint + profile |
| **Bid x Ask Delta Profile** | Horizontal delta histogram (positive right, negative left from center) | Buyer/seller dominance per level |
| **Bid x Ask Imbalance** | Cell highlights only when diagonal ratio > Imbalance Rate (default **150%**) | Stacked imbalance hunting |

### Color Schemes (9 options, agent should ship the first 3 as presets)

1. **Solid** — flat bid color, flat ask color
2. **Bid/Ask Volume Proportion** — saturation scales with volume
3. **Heatmap by Volume** — full color ramp from cold to hot
4. Heatmap by Trades
5. Heatmap by Delta
6. Volume proportion
7. Trades proportion
8. Delta
9. None

### Imbalance Defaults

- **Default Imbalance Rate: 150%** (compared diagonally — bid at price *N* vs ask at price *N+1*, and vice versa)
- **Bid imbalance highlight:** red flood / red border
- **Ask imbalance highlight:** green flood / green border
- **Border styles:** `Body | Candle | None`. Body is the default — fills the cell with a thin border.
- **Maximum-volume cell:** thin black contour around the highest-volume cell in the bar. This is the ATAS POC marker — much more subtle than NT8's yellow flood, and arguably better looking.

### Typography

- Auto-size font with min/max bounds. Bold toggle. Cluster Values Divider character (default is `x`, e.g. `27x32`) — when set to a thin separator the cell looks dramatically more refined.
- Font choice in ATAS defaults to a system sans (Segoe UI on Windows). The agent should override with a tabular monospace for values, sans for labels.

### Color Defaults

- Bid color: red (`#D14545` family)
- Ask color: green (`#3DB868` family)
- Body delta: dimmed gray when neutral, red/green when biased
- POC cell: black contour (1px solid)
- Background: dark gray, slightly warm (`#1A1A1A`–`#222222` range; brighter than Bookmap)

### Side Panels

- **Smart Tape** — vertical streaming list, monospace, color-coded by aggressor. Rows highlight in red/green flash on print, then fade to base color over ~500ms.
- **DOM Levels** — horizontal lines drawn into the chart from Smart DOM data; line **thickness** encodes volume. Color encodes side.
- **Big Trades** — colored circles plotted on the chart, **size encodes volume**, color encodes aggressor. Top-10 within visible range is the default filter.
- **Cluster Statistic** — strip across the top of each footprint bar showing aggregate stats (delta, volume, max imbalance). The strip is the same width as the bar.

### What NT8 Should Steal

- The **150% diagonal imbalance** default (NT8 ships at 1.5 ratio = same thing, but ATAS exposes it more prominently).
- The **black contour POC** — vastly less garish than NT8's yellow flood.
- The **Cluster Statistic strip** — top-of-bar header showing per-bar stats. NT8 doesn't have this and it's a missing layer.
- The **value divider** customization — even just changing `,` to a thin space (`U+2009`) elevates the cell visually.

---

## 3. Sierra Chart — The Institutional Workhorse

Sierra Chart looks the way it does because the people who use it stopped caring about looks 15 years ago and want maximum information per pixel. The visual language is dense, monospaced, slightly utilitarian — which is exactly why pros respect it. The agent should learn from Sierra's *information architecture* even if it rejects Sierra's *aesthetic*.

### Numbers Bars (Footprint)

Sierra calls footprint "Numbers Bars" and it has **21 distinct background coloring methods** plus 20 text coloring methods. This is overkill for any single user — the agent should ship 3–4 curated presets.

Key configuration concepts the agent must internalize:

- **4-tier color ranges per side:** `Range 0 / 1 / 2 / 3` × `Up / Down`. So instead of one bid color and one ask color, you have a discrete 4-step ladder per side. Default thresholds: `0.25, 0.50, 0.75` (percent of bar max) or `100, 200, 300` (actual volume).
- **Separate text vs background coloring methods.** Background can show "Volume Profile" while text shows "Dominant Side" — two layers of information per cell.
- **POC = 1–3 horizontal yellow line** (configurable thickness), drawn through the highest-volume price level. Display Location can be Column 1, Column 2, Column 3, or All.
- **Equal Bid/Ask volumes** get their own dedicated highlight color — Sierra users care about this, the agent should expose it.
- **Last Trade Price** highlighting modes: `Bold Only | Highlight Only | Bold and Highlight`.
- **Font Size Mode:** `Same as Chart Font` (fixed) or `Automatic` (with min/max bounds). Automatic is what makes Sierra footprints stay readable across zoom levels.
- **Separator character:** customizable. Default is `x` (e.g., `27x32`). Sierra users often switch to `|` or just whitespace for cleaner reads.
- **Profile display:** background fills proportionally from left or center. "Outline variants" render only the border for a wireframe look.

### Default Sierra Color Palette (canonical)

Sierra ships with white-on-black originally, but the modern default is dark theme:

| Element | Default |
|---|---|
| Chart background | `#000000` (true black) — Sierra is unapologetic |
| Up bar | `#00FF00` (pure green) — garish, most users change to teal |
| Down bar | `#FF0000` (pure red) |
| Grid | `#1F1F1F` near-black gray |
| Axis text | `#C0C0C0` light gray |
| POC line | `#FFFF00` yellow, 2px |
| Volume profile fill | `#404040` semi-transparent gray |
| Last price line | `#FFFFFF` white, 1px solid |

### "Sierra Dark" Custom Theme (community standard)

The popular community refinement reduces saturation:
- Background: `#0F0F0F`
- Up: `#26A69A` (teal — borrowed from TradingView)
- Down: `#EF5350` (coral red)
- Grid: `#1A1A1A`
- Text: `#D4D4D4`

### What NT8 Should Steal

- The **4-tier color range** concept: a single hue with 4 saturation steps reads dramatically better than a continuous gradient at footprint cell sizes (12–18px text). Discrete bins are easier to perceive than smooth gradients.
- **Separate text + background coloring methods** — two information channels per cell.
- The **separator character** as a styling lever.
- **Right-aligned vs centered vs left-aligned** value text per column.

---

## 4. Quantower — The Modern Reference

Quantower is what you build if you take Sierra Chart's information architecture and lay a 2024 design system over it. It's the cleanest example of "modern, gradient-aware, themeable" trading UI. Three of its themes (Dracula, DraculaPro, Solarized) are open source — the agent has the **exact CSS variables**.

### Default Theme Palette (extracted from official theme files)

#### Dracula (the default modern dark)

| Variable | Hex | Purpose |
|---|---|---|
| `--windowBGColor` | `#282A36` | Outer window background |
| `--primaryBGColor` | `#44475A` | Card / panel background |
| `--secondaryBGColor` | `#282A36` | Inset panels |
| `--primaryBorderColor` | `#6272A4` | Standard border |
| `--primaryTextColor` | `#F8F8F2` | Body text |
| `--secondaryTextColor` | `#6272A4` | Subdued text |
| `--accentTextColor` | `#8BE9FD` | Cyan accent |
| `--buyColor` | `#50FA7B` | Buy/long green |
| `--sellColor` | `#FF5555` | Sell/short red |
| `--accentColor` | `#BD93F9` | Purple accent for selection / focus |
| `--warningColor` | `#F1FA8C` | Yellow warning |
| `--windowBorderFocusedColor` | `#BD93F9` | Active window outline |
| `--panelsBinds` | `#8BE9FD` | Cyan tag for "linked panels" group |
| `--panelsAnalytics` | `#BD93F9` | Purple tag |
| `--panelsTrading` | `#50FA7B` | Green tag |
| `--panelsPortfolio` | `#F1FA8C` | Yellow tag |
| `--panelsInformational` | `#FFB86C` | Orange tag |
| `--panelsMisc` | `#FF79C6` | Pink tag |

#### DraculaPro (the "midnight oil" preset)

| Variable | Hex |
|---|---|
| `--windowBGColor` | `#0B0D0F` (much darker than Dracula) |
| `--primaryBGColor` | `#263340` |
| `--middleBGColor` | `#3C5166` |
| `--primaryTextColor` | `#F8F8F2` |
| `--accentTextColor` | `#FFCA80` (warm amber accent) |
| `--buyColor` | `#8AFF80` (high-luma green) |
| `--sellColor` | `#FF9580` (peachy red) |
| `--accentColor` | `#6545FE` (electric purple) |
| `--infoColor` | `#45FEDD` (mint cyan) |

#### Solarized

| Variable | Hex |
|---|---|
| `--primaryBGColor` | `#002B36` (Solarized base03) |
| `--secondaryBGColor` | `#073642` |
| `--primaryTextColor` | `#FDF6E3` (base3) |
| `--buyColor` | `#859900` (Solarized green) |
| `--sellColor` | `#DC322F` (Solarized red) |
| `--accentColor` | `#4AA9FF` |

### Footprint (Cluster Chart) Specifics

- Three modes: **Single cluster**, **Double cluster** (two data types stacked per bar), **Imbalance** mode (left = sell volume, right = buy volume).
- Coloring modes: by delta / by volume / by trades.
- **Custom step** — aggregates N price levels into one cell. Critical for high-volatility instruments where the native tick size is too granular.
- **Filtered volume** — minimum threshold below which cells render as empty/dim. Eliminates noise.

### DOM Surface (Quantower's Bookmap-equivalent)

- Coloring modes for Bid/Ask columns: **Histogram | Gradient | Combine**.
- Gradient mode: high-interest zones in bright color, low-interest zones in dull. Quantower is explicit about using "tuned colors and a gradient background" to elevate UX.
- Trades-size drawing types: customizable fill and border per trade size.

### Panel Layout

- Cards with rounded borders (~4–6px radius). Borders are 1px, color `#414D58` or similar mid-tone.
- Panels "stick" to each other when dragged near borders.
- Tabs use a colored dot/strip on the active tab (the `--panelsXxx` color family identifies the group).

### What NT8 Should Steal

- The **panel group color system**: tag every window with a small colored dot in the corner indicating its function (analytics = purple, trading = green, info = orange). This makes a 12-window workspace instantly navigable.
- The **Dracula palette** as a built-in DEEP6 theme — it's the most validated dark fintech palette in existence.
- The **Custom step** aggregation for cluster cells.
- **1px, 6px-radius card borders** as the default panel chrome. NT8's default chrome looks Win95.

---

## 5. Jigsaw / DayTradr — Minimalist DOM Excellence

Jigsaw's identity is "fewer settings, faster execution, GPU-accelerated, designed by traders." The visual minimalism is the point. The agent should learn restraint here.

### Design Philosophy

- "Self-tuning" defaults: user shouldn't need to tweak. The agent's NT8 indicators should land with sensible defaults that need no configuration to look good.
- GPU acceleration for Auction Vista (orderbook history viz) — important because at FOMC/NFP volume, CPU-rendered DOMs lag.
- Resizable icons, repositionable elements, hideable hamburger menu — chrome can disappear entirely.

### Visual Conventions

- **Color usage is sparse and semantic.** Most cells are neutral; color appears only when something is happening (trade just printed, large order just hit the book, imbalance just stacked).
- **Pace of Tape Smart Gauge** — single-purpose visual gauge (bar/dial) that summarizes "how fast is the tape moving right now." No numbers, just a fill level. This is a great pattern: convert a noisy metric into a single ambient visual.
- **Large Trade Circles** — when a trade exceeds size threshold, a circle is drawn at that price level. Size and color = magnitude and aggressor.
- **Reconstructed Tape** — fixes the problem where one large market order shows as 50 separate prints by reconstructing the original. Visually: one large highlighted row instead of 50 thin rows.

### Color Palette

Jigsaw is conservative — typical defaults read as:
- Background: `#1E1E1E` mid-dark gray (less harsh than pure black)
- Bid: blue (`#2D7FE0` family)
- Ask: red (`#E64545` family)
- Tape highlights: yellow flash (`#FFD700`) fading to base over ~300ms
- Volume highlights: cyan (`#00BFFF`)

### Auction Vista (the heatmap-equivalent)

Smaller and less elaborate than Bookmap but with the same conceptual mapping: time on X axis, price on Y, color intensity = liquidity. Rendered with fewer color stops (3–4 vs Bookmap's smooth gradient) which gives it a "blockier" but faster-to-read look.

### What NT8 Should Steal

- The **Pace of Tape gauge** concept: a single ambient visual element that summarizes a noisy metric.
- The **flash-and-fade** pattern for new prints (yellow → base over ~300ms). NT8 indicators almost never use animation; even subtle fades convey "something just happened" better than any static treatment.
- The **3–4 color-stop heatmap** as a faster-to-read alternative to Bookmap's smooth gradient — useful for the agent to know there's a tradeoff.

---

## 6. MotiveWave — Themeable Multi-Pane

MotiveWave is the choice for Elliott Wave traders and offers 180+ drawing components. Its design is more "comprehensive desktop application" than "minimalist trading UI." Useful as a reference for chrome and theming.

### Theme System

- **Window Theme:** Dark, Navy, or Light.
- **Chart Theme** and **Bar Theme** are independent — you can have a dark window but a light chart, etc.
- **Buy/Sell Colors:** Red/Blue or Red/Green presets. The Red/Blue option is good — it's the colorblind-safer choice that some pro shops use as their house style.

### Layout

- **Pages** at the bottom (like browser tabs) for switching layouts.
- **Stacked panels** — multiple panels can occupy the same screen region as tabs.
- **Components Panel** — drag-to-place drawing components (180+).

### What NT8 Should Steal

- **Independent theming layers** (window theme separate from chart theme separate from bar theme) — gives users the granularity they want without forcing maximalist customization.
- **Page tabs** at the bottom for layout switching.

---

## 7. Investor/RT — The Original Footprint

Linn Software pioneered footprint charting ~20 years ago. Its visual language quietly became industry standard. Investor/RT's specific innovation: extensive **per-element coloring methods** for footprint backgrounds (Bid Ask, Bid Ask Shaded Text, Bid Ask Shaded Chart, Strong Side Same Price, Strong Side Imbalance, Constant Text Color, Volume Shaded Text, Volume Shaded Chart). This is the lineage Sierra Chart's 21-method system inherits.

The takeaway for the agent: the *vocabulary* of footprint coloring (terms like "Strong Side," "Volume Shaded," "Imbalance") is older than most platforms and should be respected. Don't invent new names — use the canonical ones.

---

## 8. TradingView — The Modern Web Reference

TradingView isn't a footprint platform but it sets the aesthetic baseline for what "modern trading chart" means. Lightweight Charts (their open-source library) ships with the canonical defaults.

### Lightweight Charts v5.1 Defaults (verified)

| Element | Hex |
|---|---|
| Up candle body | `#26A69A` (teal) |
| Down candle body | `#EF5350` (coral red) |
| Up wick | `#26A69A` |
| Down wick | `#EF5350` |
| Wick neutral | `#737375` |
| Up border | `#26A69A` (or `#378658` darker green) |
| Down border | `#EF5350` |
| Crosshair (typical custom) | `#9B7DFF` with `[2,2]` dash |
| Crosshair label background | `#C3BCDB44` (white-purple tint, ~26% alpha) |

The reason this teal/coral pair is so widely copied: both colors have nearly identical luminance (~0.45). They distinguish by hue alone, which means red-green colorblind viewers can still tell them apart by saturation pattern. This is the single best red/green pair for trading.

### TradingView Dark Theme Convention

- Background: `#131722` (slightly blue-tinted near-black) — distinctive, often imitated.
- Grid: `#2A2E39` very subtle.
- Axis text: `#787B86` mid-gray.
- Watermark: ticker name in `#363A45` extremely faint, behind the chart.

### Crosshair / Tooltip Pattern

- Crosshair: 1px dashed, magnetic-snap to bars optional.
- Tooltip floats top-left, panel-background color, 1px border, tabular numerals showing OHLC.
- Scale labels (current price, crosshair price) render on the axis as small filled rectangles with the price color (green/red/neutral).

### What NT8 Should Steal

- **The teal/coral pair (`#26A69A`/`#EF5350`)** as the agent's universal up/down default. It's the single most-validated color pair in modern trading UI.
- **The `#131722` background tint.** Pure black is amateur; near-black with a 5–10% blue lift is "TradingView modern."
- **The watermark pattern** — ticker symbol in extremely faint text behind the chart. NT8 indicators rarely use this and they should.
- **The price-scale floating label** at the current price level (filled rect with price text in white).

---

## 9. Bloomberg Terminal — The Professional Aesthetic Encoded

Bloomberg's visual identity is deliberately anachronistic and that's exactly why it works. The agent should not directly copy it for charts (the amber-on-black look is specifically branded), but should understand *why* traders associate it with seriousness so it can deploy similar gravitas in DEEP6.

### The Canonical Palette

From the documented Bloomberg color palette and the Berg VS Code theme (which is a verified faithful port):

| Color | Hex | Bloomberg Meaning |
|---|---|---|
| Background | `#000000` | True black (serves as visual silence) |
| Primary foreground (amber) | `#FB8B1E` / `#F49F31` | Default text — non-semantic information |
| Secondary text | `#D7D7D7` / `#ACACAE` | Less prominent labels |
| Cursor / focus | `#4DC7F9` (cyan) | Active element |
| Buy / positive / up | `#5DC453` (green) | Gains, bid side |
| Sell / negative / down | `#D54135` / `#FF433D` | Losses, ask side |
| Highlight / urgent | `#FFF799` (pale yellow) | Inline highlight, search match |
| Active link / data range | `#0068FF` (blue) | Cross-references |
| Cyan / accent | `#4AF6C3` | Alternate accent |
| Warning / orange | `#FB8B1E` (orange) | Same as primary — orange is "default" |
| Magenta / Function key | `#68339C` (purple) | Function group identifier |

### Why Amber on Black Reads as "Professional"

1. **Historical inertia** — amber CRT phosphor (P3) was the standard 1980s monochrome trading screen. Anyone who entered finance before 2000 associates this with "real trading."
2. **High photopic contrast** — amber on black has higher perceived contrast than white on black (amber is closer to the eye's peak sensitivity wavelength, ~555nm).
3. **Eye fatigue** — long sessions on amber are slightly less fatiguing than pure white because of reduced blue-light component. A real ergonomic advantage that became aesthetic signaling.
4. **Brand discipline** — Bloomberg refused to update for 30 years. The continuity itself signals "we are old, established, and don't care what looks fashionable."

### Typography

Bloomberg Terminal uses a custom monospaced font (variant of "Bloomberg Trade Sans Mono" / formerly "Bloomberg Prop"). Characteristics:
- All caps headers, mixed case body.
- Tight letter spacing.
- Cell-grid layout — every character snaps to a fixed grid.
- No italics, almost no bold (bold is reserved for command names).

### Information Density

A typical Bloomberg screen is fully populated edge to edge: 8–12 columns of monospace data, function key tabs at top, command bar at bottom, no whitespace except between logical groups. The agent should treat this as the upper bound of acceptable density — DEEP6 doesn't need to go this far, but should never apologize for being information-rich.

### What NT8 Should Steal

- **The `#FB8B1E` amber as a "neutral data" color** for non-semantic text on dark backgrounds. Far more refined than pure white.
- **The pale yellow `#FFF799` highlight** for inline emphasis (matched price, current row).
- **The discipline of having ONE highlight color across the entire UI** (Bloomberg uses pale yellow, period). The agent should resist using multiple "highlight" treatments.
- **Function-group color tagging** (purple = function key, cyan = active cursor, orange = default) — this is what Quantower's panel-tag system descended from.

---

## 10. NinjaTrader 8 OFA — What Ships, What's Good, What's Not

This is the baseline the agent is improving. NT8's Order Flow+ Volumetric Bars are competent but visually mediocre out of the box. Here's the audit.

### Documented Defaults (from official NT8 help)

| Setting | Default | Verdict |
|---|---|---|
| Imbalance Ratio | `1.5` (= 150% — matches ATAS) | Good default, industry-standard |
| Shading Sensitivity | `20` levels | Reasonable; too granular for small cells |
| Minimum Delta for Imbalance | `10` | Good filter for noise |
| Buy imbalance color | **Cyan** | Excellent — colorblind-safe, distinct |
| Sell imbalance color | **Magenta** | Excellent — pairs with cyan |
| Maximum-volume highlight | **Yellow** | Standard, slightly garish at default saturation |
| Bar style | BidAsk and Delta | Both supported; BidAsk default |
| "Hide Text" mode | Toggleable; emphasizes cells via border colors | Underused — best NT8 feature most users never enable |

### What's Good (Keep)

- **Cyan/magenta imbalance pair** — best-in-class. Don't change this default.
- **Hide Text mode** — when enabled, the chart becomes a pure heatmap with imbalance borders and yellow max-volume cells. This is the "Bookmap mode" of NT8 and most users don't know it exists. The agent should expose this prominently.
- **Delta-shaded bar bodies** — the candle component of the volumetric bar shades up/down based on net delta, not just close > open. Subtle but valuable.
- **Profile View** option — distributes volumetric data as a horizontal profile alongside the cells.

### What's Mediocre (Improve)

- **Default font** — uses Calibri or Segoe UI. Not tabular, not monospaced. Numbers misalign. **Fix:** Swap to JetBrains Mono or Consolas with `tabular_nums`.
- **Default cell padding** — too generous; wastes pixels. **Fix:** Tighten to 1px horizontal, 0px vertical between cells.
- **Default colors for non-imbalance cells** — uses NT8's default "Volume" color which is a flat gray. **Fix:** Implement the Sierra-style 4-tier saturation ladder.
- **POC marking** — NT8 doesn't have a native POC equivalent in Volumetric Bars, only the yellow "max" cell. **Fix:** Draw an explicit horizontal POC line through the bar at the max-volume price (Sierra convention).
- **No flash-and-fade animations.** Imbalances simply "appear." **Fix:** Implement a 200ms cyan/magenta border flash that fades to base.
- **No header strip per bar.** ATAS has a Cluster Statistic strip; NT8 doesn't. **Fix:** Render bar-aggregate stats (delta, total volume, max imbalance count) above each bar.
- **Default chart background** — NT8's default is a pale gray-blue that screams "1998 Windows app." **Fix:** Override to `#0E1014` or `#131722`.

### What's Bad (Replace)

- **Chrome around indicator panels** — gray gradient borders with raised 3D bevels. Pure Win95 garbage. **Fix:** Override with 1px solid border, 6px border-radius if hosting allows, otherwise flat 1px.
- **Toolbar font** — uses system default at small size. Looks like Notepad. **Fix:** Inter 12px for chrome, JetBrains Mono 11px for data.
- **Crosshair** — defaults to a heavy 2px solid line, full opacity. **Fix:** 1px, dashed `[2,2]`, alpha 0.5.

---

## 11. Comparison Tables — The Quick-Reference Matrix

### Table A: Background Color by Platform

| Platform | Background | Character |
|---|---|---|
| Bookmap | `#0E1014`–`#13161A` | Near-black, slight cool bias |
| ATAS | `#1A1A1A`–`#222222` | Mid-dark gray, slightly warm |
| Sierra Chart (default) | `#000000` | True black, unrepentant |
| Sierra Chart (community dark) | `#0F0F0F` | Slight lift from pure black |
| Quantower Dracula | `#282A36` | Lifted dark with purple bias |
| Quantower DraculaPro | `#0B0D0F` | Very dark, neutral |
| Quantower Solarized | `#002B36` | Dark teal-blue |
| Jigsaw | `#1E1E1E` | Mid-dark gray |
| TradingView | `#131722` | Near-black with blue bias |
| Bloomberg | `#000000` | True black |
| NT8 default | Pale gray-blue | Avoid |
| **DEEP6 recommended default** | `#0F1115` | Halfway between TradingView and Bookmap |

### Table B: Bid/Ask Color Pairs

| Platform | Bid (negative/sell) | Ask (positive/buy) | Notes |
|---|---|---|---|
| Bookmap (heatmap) | Blue/cyan | Orange/red | Liquidity, not aggression |
| Bookmap (trade dots) | Magenta | Cyan | Aggression direction |
| ATAS | Red `#D14545` | Green `#3DB868` | Conservative |
| Sierra (legacy) | `#FF0000` | `#00FF00` | Garish |
| Sierra (modern) | `#EF5350` | `#26A69A` | Muted |
| Quantower Dracula | `#FF5555` | `#50FA7B` | High-luma |
| TradingView | `#EF5350` | `#26A69A` | The standard |
| NT8 OFA imbalance | Magenta | Cyan | Excellent default |
| Bloomberg | `#FF433D` | `#5DC453` | Classic |
| **DEEP6 recommended** | `#EF5350` cells / `#FF36A3` magenta for stacked imbalance | `#26A69A` cells / `#00D4FF` cyan for stacked imbalance | Two-tier: muted for default cells, saturated for exceptional events |

### Table C: Imbalance Highlight Treatment

| Platform | Treatment | Default ratio |
|---|---|---|
| ATAS | Cell flood, full color | 150% |
| Sierra Chart | 4-tier saturation step | Threshold-based, configurable |
| NT8 | Cyan/magenta border (Hide Text) or text color (default) | 1.5 (=150%) |
| Bookmap | N/A (heatmap, not footprint) | — |
| Quantower | Cell color shift | Configurable |
| **DEEP6 recommended** | Stack: 1x = saturated text; 2x = saturated text + 1px border; 3x = text + 2px border + flood at alpha 0.4; 4x+ = text + 2px border + flood + flash animation | 150% (industry standard) |

### Table D: Typography

| Platform | Cell numerals | Chrome / labels |
|---|---|---|
| Bookmap | System monospace (tabular) | System sans |
| ATAS | Segoe UI (auto-size) — should be tabular | Segoe UI |
| Sierra | Consolas-style monospace | Same |
| Quantower | Tabular numerals throughout | Inter or system sans |
| TradingView | Roboto Mono or system | Trebuchet/Roboto |
| Bloomberg | Bloomberg Prop Mono | Same |
| NT8 default | Calibri (NOT tabular) — defect | Same |
| **DEEP6 recommended** | JetBrains Mono 11px, `tabular-nums` | Inter 12px |

### Table E: POC Marker Style

| Platform | Treatment |
|---|---|
| Sierra Chart | Yellow horizontal line (1–3px configurable) through max-volume price |
| ATAS | Black 1px contour around max cell (subtle, refined) |
| NT8 OFA | Yellow filled cell (no line) |
| Quantower | Configurable per cluster |
| **DEEP6 recommended** | Yellow 2px horizontal line at max-volume price (Sierra convention) PLUS a 1px black border around the cell (ATAS convention). Best of both. |

### Table F: Crosshair

| Platform | Style | Color | Width |
|---|---|---|---|
| Bookmap | Dashed `[3,3]` | White alpha 0.5 | 1px |
| TradingView | Dashed `[4,4]` | Light purple `#9B7DFF` | 1px |
| Sierra | Solid | Configurable | 1px |
| NT8 default | Solid | Black | 2px (too heavy) |
| **DEEP6 recommended** | Dashed `[2,2]` | `#A0A4B0` alpha 0.55 | 1px |

---

## 12. The "Award-Winning" Web/Fintech Reference Layer

Beyond trading-specific platforms, the modern fintech web shows what an ambitious agent should reach for.

### Robinhood

- **Apple Design Award 2015, Google Material Design Award 2016.**
- Black background when markets closed, white when open — semantic, not just aesthetic.
- Stock tiles: ticker on left, price + chart on right, single accent color (green or red).
- **Removed confetti and gamification elements** under regulatory pressure — useful lesson: animation that celebrates a trade is interpreted as encouraging risk. The agent should never animate P&L gains/losses.
- Typography: custom display font (Capsule Sans) for headers, Söhne for body. Tight, modern.

### Public.com / Modern Investing Apps

- **Dark mode with subtle gradients** (radial gradient backgrounds at ~5% intensity).
- **Bold typography** for hero numbers (P&L, portfolio value) — typically 32–48px.
- **Narrative-rich graphics** — every chart has explanatory annotations.
- Resists the legacy-finance temptation to cram density.

### IBKR Desktop vs TWS

- **TWS (legacy):** "outdated" but powerful. The look the DEEP6 agent must transcend.
- **IBKR Desktop (2024+):** "next-generation" — wraps TWS execution engine in modern UI. Confirms the industry direction: keep institutional power, modernize the surface.

### Stripe (the gold standard for fintech web)

- Striking pink/blue/yellow gradients on marketing surfaces.
- For app surfaces: extremely restrained — near-monochromatic with one accent.
- Documentation interface uses tabular numerals and monospace for code, IBM Plex Sans for body.

### Hudson River Trading's UX Documentation

HRT explicitly published their internal design lessons:
- **Abandoned green text for success** because it was unreadable on existing backgrounds. Validate every color pair with a contrast checker.
- **Bar-chart visualization for runtimes** instead of tables — bar length = runtime, color = status (yellow = pending, red = error). Conversion of dense tabular data into glance-readable visual = the single highest-leverage UX move in trading software.
- **Tailored controls** — domain-specific UI elements, not generic widgets.
- **Dark theme with semantic colors per category** of information.

### Anti-Pattern Catalog (from Devexperts and others)

Tells of amateur trading UI:
1. Generic Windows form controls (default buttons, default dropdowns, default scrollbars).
2. Mixed font families in the same window (Segoe UI label next to Calibri value next to Tahoma button).
3. Drop shadows on chart objects.
4. 3D bevels on panels.
5. Unaligned numeric values (non-tabular numerals).
6. Pure red `#FF0000` and pure green `#00FF00` (eye-searing, dated).
7. More than 2 typeface families in the entire application.
8. Color used decoratively rather than semantically.
9. Cluttered toolbars that try to expose every action.
10. Inability to disable chrome (no "minimal mode").

---

## 13. Color Theory & Accessibility — The Non-Negotiables

For an agent generating colors, these rules are stricter than aesthetic preference.

### The Colorblind Constraint

- ~8% of male traders have red-green deficiency. A platform that fails them looks unprofessional.
- **Rule 1:** Never rely on hue alone. Distinguish by hue AND luminance AND saturation simultaneously.
- **Rule 2:** Avoid pure red + pure green. Use teal/coral (`#26A69A`/`#EF5350`) — different luma curves.
- **Rule 3:** For critical pairs (imbalance), prefer **cyan + magenta** (NT8 default) — these are distinguishable across all common color blindness types.
- **Rule 4:** For heatmaps, the safest accessible scales are: green-black-magenta, cyan-black-red, light-blue-black-yellow, purple-white-orange, blue-white-red. Red-green gradient is the worst possible choice.

### Contrast Validation

- Body text on background: minimum WCAG AA (4.5:1) for normal weight, 3:1 for bold ≥18px.
- Cell numerals: minimum 4.5:1 against the cell background, including imbalance flood states.
- Use the Coolors Color Contrast Checker (HRT's choice) or equivalent before shipping any color combo.

### Saturation Discipline

- Background: maximum saturation 5% (essentially neutral).
- Default text: 0% saturation (neutral white/gray).
- Semantic state (buy/sell): 30–50% saturation (recognizable but not loud).
- Exceptional events (3-stack imbalance, max volume, last trade): 70–90% saturation (loud).
- **Never** set 100% saturation on anything that persists. Reserve max saturation for transient flashes only.

---

## 14. Layout Doctrine — Panel Chrome & Spacing

### Card Pattern (modern default)

```
┌──────────────────────────────┐  ← 1px border, color = #2A2E39 or theme border
│ ● Title                  ⋯ × │  ← Header, 24–28px tall, panel-bg color
├──────────────────────────────┤  ← 1px separator, same color as outer border
│                              │
│   [content fills edge-to-    │
│    edge, no inner padding]   │
│                              │
└──────────────────────────────┘
```

- Border radius: 4–6px on outer corners, 0px on inner separators.
- Header dot (`●`): the panel-group color tag (Quantower convention — purple/cyan/green/orange/yellow/pink).
- Title font: Inter 12px, weight 500.
- Header buttons: 16x16px icons, color = secondary text, hover = primary text.
- No drop shadows. No 3D bevels. No gradients on chrome (gradients only on data).

### Spacing Scale

Use a strict 4px scale: `4, 8, 12, 16, 24, 32, 48`. Never use `5, 7, 10, 13` etc.

### Density Tier

- **Tier 1 (Bloomberg/Sierra):** 11px text, 14–16px row height, 1px gutters. Maximum density. For experienced users on large screens.
- **Tier 2 (Quantower/ATAS):** 12px text, 18–22px row height, 2–4px gutters. Default.
- **Tier 3 (Robinhood/Public):** 14–16px text, 32–48px row height, 8–16px gutters. For mobile / casual.

DEEP6 should default to **Tier 2** with a setting to switch to Tier 1 for power users.

---

## 15. The DEEP6 NT8 Agent — Concrete Recommendations

What the agent should produce when generating a footprint indicator from scratch:

### Defaults Bundle

```
Background:                    #0F1115
Grid:                          #1A1F26 (alpha 0.10)
Axis line:                     #2A3038 (alpha 0.30)
Axis text:                     #9CA3AF
Cell text default:             #D4D4D4 (Inter 11px tabular OR JetBrains Mono 11px)
Cell text bid (sell):          #EF5350 (TradingView coral)
Cell text ask (buy):           #26A69A (TradingView teal)
Cell text neutral:             #9CA3AF
Imbalance buy 1x:              #26A69A bold
Imbalance buy 2x:              #00D4FF bold + 1px border
Imbalance buy 3x:              #00D4FF bold + 2px border + #00D4FF20 flood
Imbalance buy 4x+:             above + 200ms flash animation
Imbalance sell 1x:             #EF5350 bold
Imbalance sell 2x:             #FF36A3 bold + 1px border
Imbalance sell 3x:             #FF36A3 bold + 2px border + #FF36A320 flood
Imbalance sell 4x+:            above + 200ms flash animation
Max volume cell:               #FFD700 background flood at alpha 0.25
POC line:                      #FFD700 2px solid horizontal at max price
Last trade highlight:          #FFF799 2px left border on the row
Crosshair:                     1px dashed [2,2] #A0A4B0 alpha 0.55
Bar header strip:              same width as bar, panel-bg, shows {Δ, Vol, ImbCount}
Cluster separator character:   thin space U+2009 (default), x available as alt
Default font - chrome:         Inter 12px / 500 weight
Default font - cells:          JetBrains Mono 11px / 400 weight, tabular-nums
Default font - axis labels:    JetBrains Mono 10px
Default imbalance ratio:       1.5 (= 150%, industry standard)
Default min delta:             10
Default shading sensitivity:   8 discrete steps (NOT 20 — discrete reads better)
```

### Hard Rules the Agent Enforces

1. Never emit pure `#000000` background, pure `#FF0000`, or pure `#00FF00`.
2. Always use tabular numerals for any numeric value.
3. Never apply drop shadows or 3D bevels.
4. Never animate P&L numbers (regulatory/UX hazard).
5. Always verify every text/background pair against WCAG 4.5:1.
6. Always pair red with cyan (not green) for imbalance highlighting.
7. Always provide a "Hide Text" / minimal mode that reduces the cell to color-only.
8. Always render a POC line (yellow horizontal, 2px) — NT8 doesn't ship this and it's the most-missed feature.
9. Always render a per-bar header strip with aggregated stats (the ATAS Cluster Statistic pattern).
10. Always include a panel-group color dot in the indicator's title bar (Quantower convention).

### Optional Themes the Agent Should Ship

- **DEEP6 Modern** (default — TradingView teal/coral on `#0F1115`)
- **DEEP6 Bookmap** (orange/cyan heatmap-style on `#0E1014`)
- **DEEP6 Bloomberg** (amber/cyan on `#000000` — for the older trader demographic)
- **DEEP6 Dracula** (Quantower's palette ported)
- **DEEP6 Solarized** (the lone light option, on `#FDF6E3`)

---

## 16. Closing Summary

Across every platform researched, the same patterns recur. A serious orderflow visualization is built from:

- A **near-black background** with a slight color bias (5–10% blue or warm).
- **Tabular monospaced numerals** for every cell containing data; sans-serif for chrome.
- A **muted base color pair** (TradingView teal/coral) for default state, escalating to **saturated cyan/magenta** for exceptional events.
- **Discrete saturation tiers** (4 steps) rather than smooth gradients for cell intensity.
- **Yellow reserved exclusively for "max" / POC**.
- **1px chrome, 6px border radius, no shadows, no bevels, no gradients on chrome.**
- **Information density Tier 2** by default, Tier 1 as a power-user mode.
- **Imbalance highlighting that compounds** as ratio grows (text → border → flood → flash).
- **A single highlight color** reused across the UI, not multiple competing highlight treatments.
- **Animation reserved for transient state changes** (flash-and-fade for new prints), never for celebrating P&L.

Bookmap teaches the agent about heatmap psychophysics. ATAS teaches modal richness and the Cluster Statistic strip. Sierra teaches discrete saturation tiers and per-element coloring methods. Quantower hands over a complete, modern dark-fintech palette as open-source CSS. Jigsaw teaches restraint and ambient gauges. TradingView locks in the canonical color pair. Bloomberg teaches that consistency and gravitas beat fashion. NT8 OFA hands over the cyan/magenta imbalance default — keep it, build everything else around it.

The agent's job is to fuse the **information density of Sierra**, the **modal richness of ATAS**, the **chrome modernity of Quantower**, the **color discipline of TradingView**, the **psychophysics of Bookmap**, and the **gravitas of Bloomberg** — then deploy that fusion through NinjaScript so that DEEP6's footprint chart is the most beautiful one a trader has ever loaded into NT8.

---

## Sources

**Bookmap:**
- [Heatmap Settings — Bookmap KB](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapSettings)
- [Colour Settings — Bookmap KB](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapColourSettings)
- [Main Chart — Bookmap KB](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapMainChart)
- [Traded Volume Visualization — Bookmap KB](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapTradedVolumeVisualization)
- [Cumulative Volume Delta — Bookmap KB](https://bookmap.com/knowledgebase/docs/KB-Indicators-CVD)
- [Color Psychology in Market Data Visualization — Bookmap blog](https://bookmap.com/blog/the-role-of-color-psychology-in-market-data-visualization)
- [Bookmap: Market Mapping Insights — LuxAlgo](https://www.luxalgo.com/blog/bookmap-market-mapping-insights/)
- [Heatmap Trading Complete Guide — Bookmap blog](https://bookmap.com/blog/heatmap-in-trading-the-complete-guide-to-market-depth-visualization)

**ATAS:**
- [Cluster Settings — ATAS Help](https://help.atas.net/en/support/solutions/articles/72000606631-cluster-settings)
- [Cluster Chart Functionality — ATAS blog](https://atas.net/blog/cluster-chart-functionality/)
- [Cluster Chart Footprint Anatomy — ATAS](https://atas.net/atas-possibilities/cluster-charts-footprint/cluster-chart-footprint-anatomy/)
- [Smart DOM Updates Overview — ATAS](https://atas.net/atas-possibilities/smart-dom-updates-overview/)
- [Smart Tape Setup — ATAS](https://atas.net/trading-preparation/smart-tape/)
- [DOM Levels — ATAS Help](https://help.atas.net/en/support/solutions/articles/72000602241-dom-levels)
- [Imbalance — How to Find and Trade — ATAS](https://atas.net/atas-possibilities/cluster-charts-footprint/how-to-find-and-trade-imbalance/)

**Sierra Chart:**
- [Numbers Bars — Sierra Chart Docs](https://www.sierrachart.com/index.php?page=doc/NumbersBars.php)
- [Graphics Settings — Sierra Chart Docs](https://www.sierrachart.com/index.php?page=doc/GraphicsSettings.html)
- [Customizing Fonts/Colors — Sierra Chart](https://www.sierrachart.com/index.php?page=doc/ChartTradingCustomizingGraphics.php)
- [Dark Theme Discussion — Sierra Chart Support Board](https://www.sierrachart.com/SupportBoard.php?ThreadID=63661)

**Quantower:**
- [Themes Editor — Quantower Help](https://help.quantower.com/quantower/miscellaneous-panels/themes-editor)
- [Cluster Chart — Quantower Help](https://help.quantower.com/quantower/analytics-panels/chart/volume-analysis-tools/cluster-chart)
- [DOM Surface — Quantower Help](https://help.quantower.com/quantower/analytics-panels/dom-surface)
- [DOM Trader Settings — Quantower Help](https://help.quantower.com/quantower/trading-panels/dom-trader/dom-trader-settings)
- [Quantower-themes (Dracula/DraculaPro/Solarized) — GitHub](https://github.com/mihakralj/Quantower-themes)
- [Order Flow Trading in Quantower — Quantower blog](https://www.quantower.com/blog/order-flow-trading-in-quantower)
- [DOM Surface Update — Quantower blog](https://www.quantower.com/blog/local-sltp-orders-plus-major-dom-surface-update)

**Jigsaw / DayTradr:**
- [Jigsaw Trading Software](https://www.jigsawtrading.com/trading-software/)
- [Jigsaw daytradr — Optimus Futures](https://optimusfutures.com/Platforms/Jigsaw-daytradr.php)
- [Jigsaw daytradr 5.0 Beta](https://www.jigsawtrading.com/blog/daytradr-5-0-trade-faster-smarter-and-more-efficiently-than-ever-before/)

**MotiveWave:**
- [Change Themes — MotiveWave Docs](https://docs.motivewave.com/knowledge-base/general/change-themes)
- [Theme — MotiveWave Docs](https://docs.motivewave.com/user-guide/settings/theme)
- [Components — MotiveWave Docs](https://docs.motivewave.com/user-guide/components)

**Investor/RT (Linn Software):**
- [Footprint Charting Tools — Linn Software](https://www.linnsoft.com/techind/footprint%C2%AE-charting-tools)
- [Linn Software Charts](https://www.linnsoft.com/charts)

**TradingView:**
- [Lightweight Charts Series Customization](https://tradingview.github.io/lightweight-charts/tutorials/customization/series)
- [Lightweight Charts Crosshair Customization](https://tradingview.github.io/lightweight-charts/tutorials/customization/crosshair)
- [TradingView Custom Themes API](https://www.tradingview.com/charting-library-docs/latest/customization/styles/custom-themes/)
- [Lightweight Charts v5 Release](https://www.tradingview.com/blog/en/tradingview-lightweight-charts-version-5-50837/)

**Bloomberg Terminal:**
- [Bloomberg's Customer-Centric Design Ethos](https://www.bloomberg.com/company/stories/bloombergs-customer-centric-design-ethos/)
- [Designing the Terminal for Color Accessibility](https://www.bloomberg.com/company/stories/designing-the-terminal-for-color-accessibility/)
- [Amber on Black — Ted Merz](https://ted-merz.com/2021/06/26/amber-on-black/)
- [Bloomberg Color Palette — color-hex.com](https://www.color-hex.com/color-palette/111776)
- [Berg VS Code theme (Bloomberg-inspired)](https://github.com/jx22/berg)
- [The Impossible Bloomberg Makeover — UX Magazine](https://uxmag.com/articles/the-impossible-bloomberg-makeover)

**NinjaTrader 8 OFA:**
- [Order Flow Volumetric Bars — NT8 Help](https://ninjatrader.com/support/helpGuides/nt8/order_flow_volumetric_bars.htm)
- [Volumetric Bars — NT8 Vendor Support](https://vendor-support.ninjatrader.com/s/article/Volumetric-Bars-Order-Flow)
- [Use Volumetric Bars to Track Buyers & Sellers — NT Medium](https://ninjatrader.medium.com/use-volumetric-bars-to-track-buyers-sellers-see-order-flow-imbalance-e84171abd472)
- [Order Flow Trading & Volumetric Bars — NinjaTrader](https://ninjatrader.com/trading-platform/free-trading-charts/order-flow-trading/)

**Modern fintech / award-winning UI references:**
- [Robinhood Application Design — Canvs Editorial](https://medium.com/canvs/robinhood-5-reasons-the-stock-trading-app-has-cracked-application-design-2e2c727f0735)
- [Inside Robinhood's UI/UX — Mark Helenowski](https://markhelenowski.com/work/inside-robinhoods-ui-ux-explainer.html)
- [Trading Platform UX/UI No-Nos — Devexperts](https://devexperts.com/blog/trading-platform-ux-ui-design-no-nos/)
- [Optimizing UX/UI Design for Trading at HRT](https://www.hudsonrivertrading.com/hrtbeat/optimizing-ux-ui-design-for-trading/)
- [Bridging the gap: trading software UX/UI — ION Group](https://iongroup.com/blog/markets/bridging-the-gap-how-trading-software-ux-ui-can-catch-up-to-the-smartphone/)
- [IBKR Desktop vs TWS — BrokerChooser](https://brokerchooser.com/broker-reviews/interactive-brokers-review/tws-vs-ibkr-desktop)
- [IBM Plex Mono — Google Fonts](https://fonts.google.com/specimen/IBM+Plex+Mono)
- [JetBrains Mono](https://www.jetbrains.com/lp/mono/)
- [Coloring for Colorblindness — David Nichols](https://davidmathlogic.com/colorblind/)
- [Best Charts for Color Blind Viewers — Datylon](https://www.datylon.com/blog/data-visualization-for-colorblind-readers)
