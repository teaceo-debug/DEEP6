# Trading UI/UX Design Knowledge Base

**Purpose:** Canonical design-taste reference for the DEEP6 NinjaTrader graphics design agent. Every recommendation here is calibrated for professional NQ futures traders working with footprint charts, DOM heatmaps, order flow, and ML-driven signal overlays. This is a *taste library* — it tells the agent what a senior financial-product designer would do, with the specific hex codes, font names, spacing values, easing curves, and contrast ratios required to actually ship the work.

**Render target:** NinjaTrader 8 (SharpDX / Direct2D), with secondary targets being TradingView Lightweight Charts (web dashboard) and Plotly (Python research notebooks). Anywhere a recommendation is render-target-specific, it is called out explicitly.

**Ground rule:** Specificity over inspiration. If a section says "use orange," it is broken. Every claim in this document carries a value the agent can paste into code.

---

## 0. The Five Laws of Trading-Interface Design

Before any color or font, internalize these. Every other rule in this document is downstream.

1. **Glance time is the only time.** A professional trader looks at the screen for fractions of a second between decisions. If the design forces them to *read* anything to extract state, it has failed. Color, position, and shape must encode state pre-attentively (≤200ms perception).
2. **Density is a feature, not a bug.** Consumer UX rules ("more whitespace = more premium") are *inverted* in trading. Bloomberg looks dense because traders demand it. Negative space is a luxury most panels cannot afford. Reduce ink only when ink does not encode information.
3. **Trust is the entire product.** A signal that *looks* gimmicky will be ignored even if it is profitable. A signal that looks credible will be over-trusted even if it is noise. Design must accurately convey the *epistemic status* of every number on screen — how it was computed, how confident the system is, when it was last refreshed.
4. **Every pixel that moves costs attention.** Animation must be either (a) load-bearing (a price flash that *is* the alert) or (b) absent. There is no decorative motion in a trading interface. Ever.
5. **The chart is the model. The UI is the interface to the model.** UI chrome (panels, headers, sidebars) must structurally recede so that the chart — the actual epistemic surface — dominates. If the chrome is the most colorful or contrasty element, the design has betrayed its purpose.

---

## 1. Color Theory for Financial Interfaces

### 1.1 Why dark backgrounds dominate trading

Three reasons, in descending order of importance:

1. **Eye fatigue over 8-12 hour sessions.** A bright background pushed through a 600-nit monitor for 10 hours produces measurable accommodation strain and headache. Dark backgrounds push this load onto pupil dilation, which the eye handles indefinitely.
2. **Pre-attentive contrast for moving data.** Tape, prices, and order-book deltas are encoded as luminous marks against dark voids. The signal *is* the photons; the background *is* the absence of photons. This is the optical inverse of reading text.
3. **CRT/amber heritage.** Bloomberg's amber-on-black, born in the 1980s when color monitors were rare, became the visual signature of professional finance. The convention is now self-fulfilling — dark UI signals "professional tool" the way light UI signals "consumer app."

OLED-specific note: pure black (`#000000`) saves OLED battery but creates "black smearing" on rapid pans. For desktop trading workstations on LCD/IPS panels, pure black is acceptable; for any OLED context (mobile companion app, modern laptop), use `#0A0A0A` to `#121212`.

### 1.2 The dark-background palette: specific values

The DEEP6 dark palette. Use these exact OKLCH and hex values. Variables map to NinjaTrader `SolidColorBrush` constructor inputs (divide each RGB byte by 255 for SharpDX `Color4`).

| Token | Hex | OKLCH | Role |
|-------|-----|-------|------|
| `bg.canvas` | `#0A0A0B` | `oklch(0.13 0.005 270)` | Outermost background, chart void |
| `bg.surface` | `#101012` | `oklch(0.16 0.006 270)` | Panel background, one elevation up |
| `bg.surface.raised` | `#16161A` | `oklch(0.20 0.008 270)` | Modal, dialog, hover plate |
| `bg.surface.overlay` | `#1C1C22` | `oklch(0.24 0.010 270)` | Tooltip, dropdown, popover |
| `border.subtle` | `#1F1F24` | `oklch(0.26 0.008 270)` | Hairline panel divider |
| `border.default` | `#2A2A31` | `oklch(0.32 0.010 270)` | Card outline, input border |
| `border.strong` | `#3D3D46` | `oklch(0.42 0.012 270)` | Active focus, selected row |
| `text.primary` | `#F4F4F6` | `oklch(0.96 0.004 270)` | Body text, prices, headlines |
| `text.secondary` | `#A1A1AA` | `oklch(0.72 0.012 270)` | Labels, metadata, axis ticks |
| `text.tertiary` | `#71717A` | `oklch(0.55 0.014 270)` | Disabled, placeholders, deemphasized |
| `text.disabled` | `#52525B` | `oklch(0.45 0.014 270)` | Inactive controls |

**Rules of elevation:** lighter = closer to viewer. Material Design's overlay technique (semi-transparent white over `#121212`) is correct in spirit but heavier than necessary. Above, each tier is a discrete step in OKLCH lightness (~+0.04 `L`) with a mild +0.002 `C` boost. This produces a perceptually uniform staircase. Never use shadows on dark backgrounds — they barely render and create grime. Use **borders or +1 elevation step** instead.

### 1.3 Semantic colors: bullish / bearish / neutral

The Western convention is red-down / green-up. Asian markets (China, Japan, South Korea) invert this: red-up / green-down, rooted in the yang/red association with vitality. **DEEP6 ships Western default with a single config flip to invert** — same hex values, role tokens swap. Never hardcode `red` or `green` in component code; reference `color.directional.up` and `color.directional.down`.

**Default Western directional palette** (calibrated for dark backgrounds — saturation reduced from typical web to avoid retinal vibration):

| Token | Hex | OKLCH | Notes |
|-------|-----|-------|-------|
| `directional.up` | `#26A65B` | `oklch(0.66 0.16 145)` | Bull. Slightly desaturated emerald, not pure RGB green |
| `directional.up.strong` | `#3DDC84` | `oklch(0.78 0.18 148)` | High-conviction bull (e.g. P0 signal) |
| `directional.up.subtle` | `#1A4A30` | `oklch(0.36 0.08 148)` | Background fill for bull rows |
| `directional.down` | `#E5484D` | `oklch(0.64 0.20 27)` | Bear. Tomato-leaning red, not fire-engine |
| `directional.down.strong` | `#FF6B6B` | `oklch(0.72 0.21 22)` | High-conviction bear |
| `directional.down.subtle` | `#4A1A1C` | `oklch(0.32 0.10 25)` | Background fill for bear rows |
| `directional.neutral` | `#A1A1AA` | `oklch(0.72 0.012 270)` | Doji, flat tape, no signal |

**Why these exact values:**
- Pure RGB green (`#00FF00`) on dark backgrounds vibrates and reads as "neon." `#26A65B` is the same hue family but at L=0.66 — bright enough to pop against `#0A0A0B` but not enough to sear.
- Pure RGB red (`#FF0000`) is too saturated; use `#E5484D` (tomato/Radix red-9). The 27° hue is shifted slightly toward orange, which improves CVD distinguishability.
- Both directional colors are matched at L≈0.65 — equiluminant, so a deuteranope sees them as the *same lightness* and can distinguish only by hue + position. This forces you to add the redundant cue (see §1.4) but means colorblind viewers don't see one as "bigger" than the other.

### 1.4 Color-blind safety (~8% of male traders)

Red-green deficiency is the most common form. **Never rely on color alone** for directional state. Always pair with a redundant cue:

| Cue | Implementation |
|-----|----------------|
| Position | Bull below, bear above on a stacked delta. Up-arrow vs down-arrow. |
| Shape | Triangle (▲ ▼) for direction. Filled vs hollow candles. |
| Brightness | Bull = brighter shade, bear = darker shade — works for ~95% of CVD types |
| Pattern | Diagonal hatching for "low confidence" overlay |
| Text | "+1.25" / "−1.25" with explicit sign — never just color |

**Color-blind-safe alternative palettes** (offer as user theme):

| Palette | Up | Down | Notes |
|---------|----|----|-------|
| Blue/Orange (Okabe-Ito) | `#0072B2` | `#D55E00` | Best universal — works for protan, deutan, tritan |
| Cyan/Magenta | `#56B4E9` | `#CC79A7` | Strong on dark backgrounds |
| Yellow/Blue | `#F0E442` | `#0072B2` | High brightness contrast |

The Bloomberg Terminal explicitly uses blue + red (not green + red) in its CVD-accessible mode and keeps amber as the *non-semantic* default — meaning amber means "data" and color is reserved for "polarity." DEEP6 follows the same principle: amber/white text for *neutral* data, color reserved for *directional state.*

### 1.5 Heatmap gradients (Bookmap-style DOM liquidity)

A footprint cell's color encodes a *quantity* (volume, delta, imbalance ratio). The choice of colormap directly determines whether traders can read magnitude correctly.

**Use perceptually uniform colormaps. Never use rainbow / jet / hsv-cycled palettes** — they introduce false contour bands at hue inflection points and are unreadable for CVD.

| Colormap | Best for | Notes |
|----------|----------|-------|
| **Viridis** | General volume heatmap, dual-purpose (CVD + perception) | Blue → green → yellow, monotonic luminance |
| **Magma** | Single-polarity intensity (e.g. liquidity density) | Black → purple → orange → cream — looks "liquid molten" against dark UI |
| **Inferno** | Same as magma, slightly higher contrast | Use when the heatmap is the *primary* visual |
| **Cividis** | Maximum CVD safety | Yellow-blue, designed specifically for CVD |
| **Turbo** | When you *must* use rainbow (legacy compat) | Improved version of jet, still less ideal than magma |

**Bookmap's specific choice:** they use a custom dark-blue → cyan → yellow → red gradient for liquidity intensity (low → high). It works because (a) the gradient has monotonically increasing luminance, (b) the warm endpoints (yellow → red) read as "hot/heavy" matching mental model, and (c) the dark-blue start is nearly invisible against the dark canvas, making low-liquidity cells *recede* visually — an implicit declutter.

**For DEEP6 footprint cells (signed delta — both polarities):** use a *diverging* colormap, not sequential.

| Token | Hex | OKLCH | Use |
|-------|-----|-------|-----|
| `heatmap.delta.bear.5` | `#7A1F22` | `oklch(0.30 0.13 25)` | Strong negative delta |
| `heatmap.delta.bear.4` | `#A02831` | `oklch(0.42 0.16 25)` | |
| `heatmap.delta.bear.3` | `#C53037` | `oklch(0.55 0.19 26)` | |
| `heatmap.delta.bear.2` | `#E5484D` | `oklch(0.64 0.20 27)` | |
| `heatmap.delta.bear.1` | `#F08080` | `oklch(0.74 0.16 23)` | Mild negative delta |
| `heatmap.delta.zero` | `#2A2A31` | `oklch(0.32 0.010 270)` | Neutral / zero |
| `heatmap.delta.bull.1` | `#7AD4A4` | `oklch(0.80 0.13 150)` | Mild positive delta |
| `heatmap.delta.bull.2` | `#3DDC84` | `oklch(0.78 0.18 148)` | |
| `heatmap.delta.bull.3` | `#26A65B` | `oklch(0.66 0.16 145)` | |
| `heatmap.delta.bull.4` | `#1F8048` | `oklch(0.55 0.14 145)` | |
| `heatmap.delta.bull.5` | `#155E36` | `oklch(0.42 0.12 145)` | Strong positive delta |

This is a 10-stop diverging scale through neutral gray. Endpoint OKLCH lightness matches across polarities (≈0.30/0.42 for strong; ≈0.74/0.80 for mild) so the eye sees magnitude symmetrically. The neutral midpoint at L=0.32 is intentionally close to the canvas brightness — zero-delta cells visually disappear.

### 1.6 The Bloomberg amber tradition

Hex value commonly cited: `#FFB000` for amber. Bloomberg's actual deployed amber across the Terminal is closer to `#FF9E0F` (slightly more orange, slightly less saturated). For DEEP6 — when an "amber" accent is needed (e.g., a "Bloomberg-mode" theme, or a dedicated alert tier that is neither bullish nor bearish) — use:

| Token | Hex | OKLCH | Use |
|-------|-----|-------|-----|
| `accent.amber` | `#FF9E0F` | `oklch(0.78 0.17 65)` | Pure amber, Bloomberg homage |
| `accent.amber.subtle` | `#3D2A0A` | `oklch(0.28 0.06 65)` | Background fill |

Never combine amber and red on the same surface — they collide hue-wise. Amber is the Bloomberg solution for "data that has no polarity" (a price, an account number, a timestamp). Red and green are reserved for state changes.

### 1.7 Accent colors — sparingly

Rules:
- **Maximum 2 accent colors** in a single view (a third reads as chaos)
- Accents are for **interactive affordances** (selection, focus, primary CTA) — *not* data
- Accent should not collide with directional palette

| Token | Hex | OKLCH | Use |
|-------|-----|-------|-----|
| `accent.primary` | `#3B82F6` | `oklch(0.65 0.18 257)` | Primary action, focus ring, link |
| `accent.primary.hover` | `#60A5FA` | `oklch(0.74 0.16 252)` | Hover state |
| `accent.violet` | `#8B5CF6` | `oklch(0.65 0.21 290)` | Secondary affordance, ML signal |

Why blue and violet: both are far enough in hue from the red/green directional axis that they cannot be confused with bull/bear state. Blue is also the safest CVD hue — preserved in all common CVD types.

### 1.8 Status colors

| Token | Hex | OKLCH | Use |
|-------|-----|-------|-----|
| `status.info` | `#3B82F6` | `oklch(0.65 0.18 257)` | Info banner |
| `status.success` | `#26A65B` | `oklch(0.66 0.16 145)` | Order filled, connection up |
| `status.warning` | `#F59E0B` | `oklch(0.75 0.17 70)` | Throttled, degraded mode |
| `status.danger` | `#E5484D` | `oklch(0.64 0.20 27)` | Connection lost, order rejected |
| `status.danger.bg` | `#4A1A1C` | `oklch(0.32 0.10 25)` | Background of danger banner |

`status.success` deliberately equals `directional.up`. Same color, same meaning ("things are good"). `status.danger` equals `directional.down`. This consistency reduces the learner's cognitive load.

### 1.9 Contrast ratios — what to actually hit

WCAG 2.1 minimums against `bg.canvas` (`#0A0A0B`):

| Element | Foreground | Ratio | WCAG |
|---------|------------|-------|------|
| Body text | `#F4F4F6` | 18.4:1 | AAA |
| Secondary text | `#A1A1AA` | 8.9:1 | AAA |
| Tertiary text | `#71717A` | 4.8:1 | AA only — use only for ≥14pt or non-critical |
| Disabled text | `#52525B` | 2.8:1 | Below AA — acceptable for disabled controls only |
| Bull signal | `#26A65B` | 6.4:1 | AA large, AAA large |
| Bear signal | `#E5484D` | 4.6:1 | AA |
| Amber | `#FF9E0F` | 9.2:1 | AAA |
| Blue accent | `#3B82F6` | 4.7:1 | AA |

Floor: 4.5:1 for any text that conveys state. Never put a 3:1 directional color on a chart and expect a CVD trader to read it. If you cannot hit 4.5:1, raise the foreground lightness or add a redundant cue.

---

## 2. Typography for Trading

### 2.1 The two-font rule

A trading interface uses **exactly two typefaces**:

1. **A geometric humanist sans-serif** for UI chrome, labels, headers, body.
2. **A monospace** for any numeric data — prices, sizes, deltas, counts, timestamps to the second/ms.

Three or more fonts is design tourism. Two is the institutional standard.

### 2.2 The recommended stacks

**Primary (sans):**

```
font-family: 'Inter', 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
font-feature-settings: 'cv11', 'ss01', 'ss03'; /* Inter — straight-sided 1, alt 'a', single-storey 'g' */
font-variant-numeric: tabular-nums; /* mandatory globally */
```

**Mono (data):**

```
font-family: 'JetBrains Mono', 'IBM Plex Mono', 'Berkeley Mono', 'SF Mono', 'Cascadia Code', Menlo, Consolas, monospace;
font-feature-settings: 'tnum', 'zero', 'ss20'; /* tabular nums, slashed zero, alt construction */
font-variant-numeric: tabular-nums slashed-zero;
```

**Why these specifically:**

| Font | Why | Avoid for |
|------|-----|-----------|
| Inter | Best-in-class screen-rendered humanist sans, OpenType variants for unambiguous 1/I/l | nothing — universal default |
| IBM Plex Sans | Slightly more "industrial," pairs with IBM Plex Mono for visual unity | brand-neutral apps |
| JetBrains Mono | Excellent on-screen rendering at small sizes, slashed zero, ligatures off by default | print |
| IBM Plex Mono | Squarer, slightly more institutional feel, matches IBM Plex Sans | tight columns (slightly wider than JetBrains) |
| Berkeley Mono | Premium feel, refined detail | budgets — paid commercial license |
| SF Mono | Apple system, free, works everywhere on macOS | Windows-only delivery |

**Avoid:** Roboto Mono (over-saturated stroke at small sizes), Courier (looks like 1990), Fira Code (ligatures cause confusion in price display).

**For NinjaTrader (WPF/SharpDX):** WPF rendering of `Consolas` and `Cascadia Code` is the practical default since they ship with Windows. If shipping a custom font, embed via `pack://application:,,,/Fonts/#JetBrains Mono` and pre-load `Typeface` objects at indicator init (not in `OnRender` — typeface resolution is expensive).

### 2.3 Tabular figures: non-negotiable

Trading interfaces *require* tabular figures. Without them, prices in a column do not align — `4500.25` and `4517.75` will be different widths because `1` is narrower than `5` in proportional figures. The eye cannot scan a misaligned price ladder.

CSS:
```css
* { font-variant-numeric: tabular-nums; }
```

WPF (NinjaScript):
```csharp
var typeface = new Typeface(new FontFamily("JetBrains Mono"), FontStyles.Normal, FontWeights.Normal, FontStretches.Normal);
// Tabular figures are default in true monospace fonts; for proportional fonts, set OpenType feature:
// In WPF, use Typography.NumeralAlignment="Tabular" on TextBlock
```

XAML:
```xml
<TextBlock Text="{Binding Price, StringFormat={}{0:N2}}"
           FontFamily="JetBrains Mono"
           Typography.NumeralAlignment="Tabular"
           Typography.NumeralStyle="Lining" />
```

For SharpDX direct text rendering (e.g., on-canvas price labels): use a monospace font and align decimals manually by calculating string width to the decimal point and right-justifying to that anchor. Never rely on proportional spacing for ladder prices.

### 2.4 Type scale

A modular scale tuned for dense dashboards. Base = 13px (smaller than typical 16px web base — this is a trading platform, not a marketing site).

| Token | Size (px) | Line-height | Weight | Use |
|-------|-----------|-------------|--------|-----|
| `text.micro` | 10 | 14 | 500 | Axis labels, footnotes, version strings |
| `text.xs` | 11 | 16 | 500 | Secondary metadata, table cells |
| `text.sm` | 12 | 16 | 400 | Compact body, dense table rows |
| `text.base` | 13 | 18 | 400 | Default body text |
| `text.md` | 14 | 20 | 500 | Section headers |
| `text.lg` | 16 | 22 | 600 | Panel titles |
| `text.xl` | 20 | 28 | 600 | Page titles |
| `text.price.sm` | 12 | 16 | 500 mono | Compact price display |
| `text.price.base` | 14 | 18 | 500 mono | Standard price display |
| `text.price.lg` | 18 | 22 | 600 mono | Featured price (current bid/ask) |
| `text.price.xl` | 28 | 32 | 600 mono | Hero price display |
| `text.metric.sm` | 11 | 14 | 600 mono | KPI value, small card |
| `text.metric.lg` | 24 | 28 | 700 mono | KPI value, hero card |

**Weight pairings:**
- Body text always 400 (regular). 300 (light) is unreadable on dark backgrounds — fringes blur into the background.
- Labels at 500 (medium). Provides visual lift without shouting.
- Headers at 600 (semibold). 700 (bold) is reserved for KPI numbers and hero stats.
- 800/900 (extra-bold/black) — never. Looks like ad copy.

### 2.5 Letter-spacing (tracking)

| Use | tracking |
|-----|----------|
| Body text | `0` |
| All-caps small labels (`OPEN`, `CLOSED`, `LIVE`) | `+0.06em` (60/1000) |
| All-caps micro labels (≤10px) | `+0.10em` |
| Display headers | `-0.02em` to `-0.01em` (slight tighten) |
| Numeric data | `0` (don't tighten — breaks tabular alignment) |

### 2.6 Number alignment in tables

Prices and quantities **right-align**. Always. The decimal column should align across rows. Symbol/text columns left-align. Never center-align numeric data — it makes magnitude comparison impossible.

If you have variable-precision quantities (`1`, `1.5`, `1.25`), pad to the maximum precision in the column with `0` — `1.00`, `1.50`, `1.25`. Right-align *and* pad — both are required.

### 2.7 Anti-aliasing on dark backgrounds

Sub-pixel anti-aliasing (LCD-optimized) was designed for black-on-white. On dark backgrounds, it produces colored fringes. Force grayscale anti-aliasing:

```css
-webkit-font-smoothing: antialiased;
-moz-osx-font-smoothing: grayscale;
```

For SharpDX text rendering in NinjaTrader, set:
```csharp
RenderTarget.TextAntialiasMode = SharpDX.Direct2D1.TextAntialiasMode.Grayscale;
```

Never use `Cleartype` on dark UI — fringes are visible.

---

## 3. Information Density & Cognitive Load

### 3.1 Tufte for traders

Edward Tufte's data-ink ratio: maximize the ink that encodes data, minimize ink that doesn't. In a trading interface this manifests as:

| Remove | Keep |
|--------|------|
| Box borders around every panel | Subtle hairline (`#1F1F24`) only between unrelated regions |
| Heavy gridlines | Tick marks at axis only; gridlines at 30% opacity if used |
| Background gradients | Flat surfaces |
| 3D candlesticks / charts | Flat 2D — 3D adds zero information |
| Drop shadows | Replace with +1 elevation step |
| Decorative icons | Functional icons only — every glyph earns its pixels |
| Redundant axis labels | Single axis labeled, duplicates suppressed |
| Default chart titles ("Price Chart") | Title is the *insight*, not the *label* |

### 3.2 Trader-specific density tolerance

Bloomberg Terminal cells are 3-4× denser than the densest "well-designed" consumer app. Traders self-select for high density tolerance — the very act of choosing to trade implies comfort with information overload.

Default to **denser than you think correct.** A row height of 20-24px is normal in a watchlist (not the 48-56px of consumer dashboards). A footprint cell of 14-18px tall is reasonable. The user can up-size if they need; cannot reduce below a minimum.

### 3.3 Glanceability vs. depth

Three-tier rule for any data point:

1. **Glance (0.2s)** — one pre-attentive cue conveys state. Color, position, or shape only.
2. **Scan (1-2s)** — the user is reading numbers. Tabular alignment, hierarchy, weight contrast.
3. **Hover/click (deliberate)** — full detail, methodology, history, raw inputs.

Example: a confidence score.
- Glance: small colored chip — green `#26A65B` chip = high confidence, amber `#F59E0B` = medium, red `#E5484D` = low.
- Scan: chip text shows the number — `0.87`.
- Hover: tooltip reveals the contributing signals, weights, when last computed, historical accuracy of this score range.

### 3.4 F-pattern, Z-pattern, and the trader gaze

Standard reading patterns assume reading. Traders do not read — they scan known regions for state changes. Their gaze pattern is:

1. Top-left → core symbol + last price
2. Top-right → P&L, account state
3. Center → chart (the actual surface of attention)
4. Bottom strip → tape, log, alerts

Place the most actionable state in the **upper-right** of any panel — that is where a trained trader's eye returns to between actions.

### 3.5 Pre-attentive attribute hierarchy

When you need *one* attribute to convey state, use them in this order of perceptual priority:

1. **Position** (most accurate — humans compare positions on a common axis better than any other cue)
2. **Length** (bar charts work because of this)
3. **Hue** (categorical — red vs green vs blue)
4. **Brightness** (ordinal — light vs dark)
5. **Size** (volume bubbles)
6. **Motion / flicker** (most attention-grabbing — reserve for *alerts only*)
7. **Shape** (categorical, weak)

Stack attributes for redundancy (color + shape + position) *only* when the channel must be CVD-safe and high-stakes.

---

## 4. Layout & Composition

### 4.1 The 4px sub-grid / 8px grid

DEEP6 uses an **8px primary grid with a 4px sub-grid**. All margins, paddings, gaps, and component dimensions are multiples of 4. Most are multiples of 8.

| Token | px | Use |
|-------|----|----|
| `space.0.5` | 2 | Hairline, badge inset |
| `space.1` | 4 | Inner padding of small chips, icon-text gap |
| `space.2` | 8 | Tight padding, compact list-item gap |
| `space.3` | 12 | Default cell padding |
| `space.4` | 16 | Default panel padding, card gap |
| `space.5` | 20 | Section spacing |
| `space.6` | 24 | Large panel padding |
| `space.8` | 32 | Major section break |
| `space.10` | 40 | Page-level spacing |
| `space.12` | 48 | Hero spacing |

### 4.2 Border radii

| Token | px | Use |
|-------|----|----|
| `radius.none` | 0 | Tables, dense data grids |
| `radius.sm` | 2 | Chips, badges, micro-buttons |
| `radius.base` | 4 | Inputs, buttons, cards |
| `radius.md` | 6 | Panels, dialogs |
| `radius.lg` | 8 | Modals, surfaces |
| `radius.full` | 9999 | Pills, status dots |

Rule: smaller radii in dense regions (data tables = 0 or 2px). Larger radii in modal/dialog surfaces (6-8px). Never mix radii of vastly different sizes within a single composition (a 0px table inside a 16px-radius card is fine; a 8px button inside a 0px card is wrong).

### 4.3 Panel structure

Every panel has:
1. **Header** (28-32px tall): title left, controls right. `border-bottom: 1px solid var(--border-subtle)`.
2. **Body** (flex-grow): the content. Padding = `space.3` (12px) for dense, `space.4` (16px) for standard.
3. **Optional footer** (24-28px): metadata, status, last-updated.

The header background is `bg.surface.raised` (one elevation up). The body is `bg.surface`. This produces a subtle "lid" effect that helps the eye find panel boundaries without explicit borders.

### 4.4 Multi-monitor and ultrawide

Professional NQ traders run 3-4 monitors at 1440p/4K. The DEEP6 main UI must not assume a single canvas:

- **Min viable workspace:** 1920×1080 (1 monitor)
- **Target workspace:** 3840×2160 (4K) or 2× 2560×1440 (dual QHD)
- **Stretch:** 5120×1440 (32:9 ultrawide) or 4× monitors

For ultrawide, lay out as **three 16:9 logical regions** rather than a single ultra-wide chart. Charts wider than 2:1 force horizontal scanning that exceeds the foveal arc.

### 4.5 Responsive density

When viewport shrinks below 1440px wide, *do not* shrink the chart — shrink chrome:
- Collapse sidebar to icon rail (40px wide)
- Hide secondary metadata in panel headers
- Reduce table cell padding from 12px → 8px
- Switch from labeled buttons to icon-only with tooltip

Below 1024px, treat as "companion mode" — execute orders + monitor only, no analysis.

### 4.6 Visual weight balance

A balanced dashboard has **one focal element** per primary view. The chart usually wins. KPI cards balance the chart by *count*, not by individual visual weight — six small cards weigh the same as one chart panel.

If two elements compete for focus, the user's eye oscillates and decision latency increases. Solve by:
- Reducing the contrast of one element (tertiary text instead of primary)
- Reducing its size
- Moving it below the fold

---

## 5. Motion & Animation

### 5.1 When motion helps

Only three legitimate uses of motion in a trading UI:

1. **Price flash on update.** Cell briefly tints `directional.up.subtle` (`#1A4A30`) for upticks, `directional.down.subtle` (`#4A1A1C`) for downticks. Duration: 200ms. Easing: `ease-out`.
2. **Alert pulse.** A new high-priority signal pulses its border opacity from 100% → 50% → 100% twice. Total duration: 800ms. Then static.
3. **Panel collapse / expand.** Layout changes use 150-200ms `ease-in-out` to give spatial continuity. Without it, the eye loses track of where panels went.

That is the entire list. No hover scale-ups, no parallax, no entrance animations, no decorative loops.

### 5.2 When motion hurts

| Pattern | Why it's bad |
|---------|-------------|
| Animated GIF spinners on load | Looks amateur; replace with subtle pulsing skeleton |
| Hover scale on chart cells | Distracts from actual price action; user wants to *read*, not be *delighted* |
| Sliding panel transitions over 300ms | Feels sluggish during fast tape; user needs the panel *now* |
| Animated number tickers (count-up) | Hides the actual final value during animation — unacceptable in finance |
| Parallax scrolling | Causes nausea, vestibular issues, has no place in a tool |

### 5.3 Easing curves

| Name | cubic-bezier | When to use |
|------|--------------|-------------|
| `linear` | `cubic-bezier(0,0,1,1)` | Continuous data update (e.g., a progress bar tracking real elapsed time) |
| `ease-out` | `cubic-bezier(0, 0, 0.2, 1)` | Default for UI affordances — a panel sliding in, a tooltip appearing |
| `ease-in-out` | `cubic-bezier(0.4, 0, 0.2, 1)` | Layout transitions (panel collapse) |
| `ease-out.snap` | `cubic-bezier(0.16, 1, 0.3, 1)` | Sharp settle — focus ring snap, dropdown open |
| `ease-in.fast` | `cubic-bezier(0.4, 0, 1, 1)` | Element exiting view |

Never use `ease-in` alone for entering elements — it feels heavy. Never use bounce or spring overshoot — finance is not casual.

### 5.4 Duration budget

| Action | Duration |
|--------|----------|
| Hover state change (color shift) | 100ms |
| Price flash on tick | 200ms |
| Tooltip appear | 150ms |
| Tooltip disappear | 100ms |
| Panel collapse/expand | 200ms |
| Modal appear | 200ms |
| Alert pulse (full cycle) | 400ms × 2 = 800ms |

**Hard rule:** never block a frame. At 60fps a frame is 16.67ms. Any synchronous work in a render path that exceeds ~10ms drops frames. In SharpDX `OnRender`, all brush creation must be cached to a dictionary at `OnRenderTargetChanged` — never inside the render loop.

### 5.5 prefers-reduced-motion

Mandatory respect:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

For NinjaTrader desktop, expose a checkbox: "Reduce motion" — when on, replace all flashes with static color changes, disable pulses, snap layouts.

### 5.6 Flash to attract attention

Reserve for *high-priority alerts only* (P0/P1 in the DEEP6 signal taxonomy). Pattern: opacity pulse of the alert badge from 1.0 → 0.4 → 1.0 over 600ms, 2 cycles, then static. Avoid full-element flashes that strobe — both for accessibility and because a strobing surface is *less* readable.

---

## 6. Iconography

### 6.1 Library choice

**Default:** Lucide. 1500+ icons, 24px grid, 1.5px stroke, rounded caps. MIT licensed. Active maintenance.

**Alternatives:**
- **Phosphor** — when you need weight variants (thin/light/regular/bold/duotone). Useful for emphasizing primary vs secondary action icons.
- **Heroicons** — Tailwind's library. 1.5px stroke, slightly more conservative aesthetic. Good fallback.
- **Tabler Icons** — 4000+ icons, also 1.5px stroke. Useful when Lucide is missing a specific glyph.

**Avoid:**
- Material Symbols — too generic, screams "Google product"
- Font Awesome — inconsistent stroke weights, looks dated
- Emoji — never in a professional trading UI

### 6.2 Sizing and alignment

| Icon role | Size |
|-----------|------|
| Inline with body text | 14×14px |
| Toolbar / compact button | 16×16px |
| Standard button | 18×18px |
| Large action | 20×20px |
| Hero icon | 24×24px |
| Status dot | 8×8px circle |

**Stroke width:** always 1.5px on dark backgrounds. 2px feels heavy and 1px disappears.

**Alignment with text:** icon center should align with text x-height (not cap-height). For 13px Inter, that means center the 14px icon at 60-65% of text height from baseline.

### 6.3 Trading-specific glyph conventions

| Concept | Glyph | Notes |
|---------|-------|-------|
| Bull / long | ▲ filled triangle, green | Up-arrow alone is ambiguous (could be "scroll up") |
| Bear / short | ▼ filled triangle, red | |
| Buy order | `arrow-up-right` (Lucide) | Suggests entry/long |
| Sell order | `arrow-down-right` | |
| Stop loss | `shield-alert` | Universal |
| Take profit | `target` | |
| Live / connected | filled circle, green, slowly pulsing (1.5s cycle) | The pulse signals "alive" |
| Disconnected | filled circle, red, static | |
| Throttled / degraded | filled circle, amber, static | |
| Algorithm running | `cpu` or `activity` | |
| Manual override | `hand` | |
| Alert / signal | `bell` for notifications, `zap` for high-conviction signal | |

Reserve `zap` (lightning bolt) for the highest-conviction signal tier only — its visual weight is exhausted if used everywhere.

### 6.4 Stroke vs. fill

- **Outline (stroke)**: default for all icons. Reads as "control" or "available action."
- **Filled**: indicates active/selected state. A filled `bell` means alerts on; outline means alerts off.
- Mixing stroke and fill in the same toolbar is acceptable *if* the meaning is consistent (selected = filled).

---

## 7. Charts as Data Visualization

### 7.1 The cardinal rules (Tufte / Cleveland / Few)

1. **Show the data.** Every pixel that does not encode data is a tax.
2. **Avoid distortion.** Linear scale unless logarithmic is specifically justified.
3. **Reveal the data at several levels of detail.** A chart at glance, on hover, on zoom.
4. **Encourage comparison.** Adjacent small multiples > one large chart with overlays.
5. **Integrate with text.** Annotations on the chart, not in a legend below.

### 7.2 Linear vs. logarithmic scale

| Use | Scale |
|-----|-------|
| NQ intraday price | Linear — the dollar value of a tick is constant |
| Multi-year stock chart | Log — equal % moves should appear equal |
| Volume | Log if range > 100×; otherwise linear |
| Confidence / probability | Linear 0-1 |
| Latency (1ms-1s) | Log — magnitude differences span orders |

### 7.3 Footprint chart specifics

A NinjaTrader footprint cell encodes (price, time, bid-volume, ask-volume, delta). The DEEP6 standard rendering:

- **Cell width**: bar width / 2 — bid on left, ask on right
- **Cell height**: tick × cell-pixel-multiplier (default 4-6px per tick)
- **Cell fill**: heatmap color (see §1.5) keyed to delta or volume per user setting
- **Text inside cell**: monospace, size 9-11px, white at 90% opacity for legibility against any cell color
- **POC (Point of Control)** highlight: 1px outline in `accent.amber` (`#FF9E0F`)
- **VAH/VAL (Value Area High/Low)**: 1px dashed line in `text.secondary` (`#A1A1AA`)
- **Imbalance markers**: `directional.up.strong` triangle on bid, `directional.down.strong` triangle on ask, drawn at the imbalance level

### 7.4 DOM heatmap (Bookmap-style)

- **Time axis** horizontal, scrolling left
- **Price axis** vertical, log if range > 50 ticks
- **Cell color** = liquidity intensity, perceptually uniform colormap (magma or custom dark-blue → cyan → yellow → red)
- **Trades** overlaid as dots; dot diameter = log(volume), dot color = aggressor side (green = market buy, red = market sell)
- **Best bid/ask** thin solid line at color `text.secondary`
- **VWAP** thin solid line at `accent.amber`
- **Background** pure `bg.canvas` (`#0A0A0B`) — chart is the only colorful surface

### 7.5 Sparklines and small multiples

A KPI card with a sparkline tells more truth than the same KPI with a single number:

```
Daily P&L          $1,247   ▁▂▃▅▇▆▄▃▂▁  ← 5d sparkline
```

Sparkline rules:
- Height: 1 line of text (≈14-18px)
- Width: 60-100px
- No axis, no labels — pure shape
- Single color matching the metric's directional polarity
- Endpoint dot: 2px circle in same color, marks "current value"

Small multiples for comparing 6-12 tickers, 6-12 timeframes, 6-12 strategies: identical scale, identical chart type, gridded layout. The eye does the comparison.

### 7.6 Annotation patterns

- Direct labels on the chart > legend below the chart
- Labels positioned 4-6px from the data point, with a 1px line connecting them if needed
- Label background: `bg.surface.overlay` at 90% opacity to maintain chart readability
- Never put annotation text *on* a candle — always offset

---

## 8. Accessibility (WCAG + Trading-Specific)

### 8.1 Contrast requirements

(See §1.9 for specific values.) Floor: 4.5:1 for body text, 3:1 for large text and UI affordances.

### 8.2 Color-blind safety

(See §1.4.) Always pair color with redundant cue (shape, position, label).

### 8.3 Keyboard navigation

Every action accessible via keyboard. Trading specifics:

| Key | Action |
|-----|--------|
| `Space` | Pause/resume tape |
| `B` | Buy at market (with confirmation) |
| `S` | Sell at market |
| `F` | Flatten position |
| `C` | Cancel all orders |
| `Esc` | Close modal, cancel input |
| `Tab` | Focus next interactive |
| `?` | Show keyboard map |

Visible focus ring on all focusable elements: 2px solid `accent.primary` (`#3B82F6`) with `outline-offset: 2px`. Never `outline: none` without replacement.

### 8.4 Adjustable density and font size

Expose three density levels: `compact` (default for 4K), `standard`, `comfortable` (for 1080p or accessibility). Each scales spacing by `0.875×`, `1×`, `1.125×`.

Font size adjustable via a global multiplier `0.9× → 1× → 1.1× → 1.25×`.

### 8.5 Reduced motion

(See §5.5.) Hard requirement.

### 8.6 Screen reader considerations

For traders with low vision, screen reader friendliness matters. Every numeric region must have an accessible label:

```html
<span aria-label="Bid: 4527.25, depth: 47">
  4527.25 <span class="depth">47</span>
</span>
```

Time-sensitive updates use `aria-live="polite"` for non-critical, `aria-live="assertive"` for high-priority alerts.

---

## 9. Dark Theme Design Specifically

### 9.1 Black is not one color

| Hex | OKLCH L | Name | Use |
|-----|---------|------|-----|
| `#000000` | 0.00 | Pure black | OLED-only, mobile companion |
| `#09090B` | 0.12 | Zinc-tinted near-black | Vercel/shadcn modern default |
| `#0A0A0B` | 0.13 | DEEP6 canvas | Our default |
| `#0E0E10` | 0.15 | Slightly cooler | Linear-style |
| `#121212` | 0.18 | Material baseline | Material Design recommendation |
| `#171717` | 0.20 | Neutral mid-dark | shadcn `zinc-900` |
| `#1A1A1F` | 0.23 | Elevated surface | Card/panel background |

DEEP6 chose `#0A0A0B` (with a faint cool tint at hue 270°) because:
- Darker than Material's `#121212` — better for chart contrast on a desktop monitor
- Slightly lighter than pure black — avoids OLED smearing on modern laptops
- Faint cool tint keeps it from feeling "warm/yellowish" which reads as "cheap LCD"

### 9.2 Saturation must decrease

A color that looks "vibrant red" against white looks "neon screaming red" against black. Reduce chroma (saturation) by ~15-25% when porting a light-theme palette to dark.

In OKLCH terms: light-theme red at `oklch(0.55 0.24 27)` becomes dark-theme red at `oklch(0.64 0.20 27)` — slightly lighter, slightly less chromatic.

### 9.3 The "blue stained-glass" trap

If everything in your UI is in the blue family (background blue-black, text blue-white, accent blue), the result is monochromatic and feels cold/medical. Solution: keep background neutral (`oklch L 270`), let directional/state colors carry hue.

### 9.4 Shadows on dark — they don't work

A shadow needs a darker color than the surface. On `#0A0A0B`, there's nothing darker. Solutions:

- **Elevation by lightness** (preferred): the raised surface is `+1 step` lighter (`#16161A` over `#101012`).
- **Border instead**: 1px `border.default` (`#2A2A31`) defines the edge.
- **Inner glow** on the bottom edge of the elevated surface: `inset 0 -1px 0 rgba(255,255,255,0.04)` simulates a top-light with a subtle highlight on the lower lip. Very effective.
- **Outer glow** for emphasis: `box-shadow: 0 0 0 1px var(--accent-primary)` for focus, or `0 0 24px rgba(59,130,246,0.15)` for soft halo around important elements.

Never use `box-shadow: 0 4px 12px rgba(0,0,0,0.5)` on a dark surface. It reads as a smudge.

---

## 10. Award-Winning Reference Library

These are the references the agent should imitate (in spirit, not by copy-paste). Each chosen for a specific reason.

| Reference | Why study it |
|-----------|--------------|
| **Bloomberg Terminal** | The institutional ground truth. Density, monospace prices, color-as-state. Imitate the discipline; don't imitate the 1980s aesthetic. |
| **Linear** | Best modern dark UI. Inter typography, OKLCH-driven elevation, density without clutter. Their "feel of polish" is invisible alignment rigor. |
| **Stripe Dashboard** | Best modern light/dark transition, clear hierarchy, restrained color palette. Their data tables are master-class. |
| **Vercel** | Pure neutral palette (true black, true white), Geist font family, near-zero radius. Confident minimalism. |
| **Notion** | How to handle dense data without panic — generous whitespace WHEN information density is low, dense WHEN it isn't. |
| **Fey** | Modern stock research app. Dark theme done right, no gimmicks, beautiful charts, modern type. |
| **TradingView** | Industry-standard chart UX. Color palette `#131722` background, `#2962FF` accent, white/grey text. |
| **Bookmap** | Heatmap rendering — the gold standard for liquidity visualization. |
| **Tradingriot / Tradephant** | Modern indie trader UIs that prove dark + dense + readable can be beautiful. |
| **Apple Stocks (macOS)** | How to make a glance-able portfolio panel. Sparklines, tabular figures, restrained color. |

**Avoid imitating:**
- Robinhood (too consumer / gamified; "casino aesthetic")
- ThinkOrSwim (information rich but visually chaotic — high density without hierarchy)
- TradeStation legacy (1990s skeuomorphism, gradients, drop shadows — exemplar of what *not* to do)

---

## 11. Anti-Patterns

### 11.1 The amateur tells

If your UI exhibits any of these, traders will distrust it before you've shown them the alpha:

| Anti-pattern | Why it fails | Fix |
|--------------|-------------|-----|
| Bootstrap default styling | Looks like a bank's customer portal circa 2014 | Custom design system from scratch |
| Material Design components | "I built this with React Material UI" — generic | Custom components, or shadcn/ui as raw primitive |
| Bright candy colors on dark (`#FF00FF`, `#00FFFF`) | Reads as "demo/toy" | Use the desaturated palette in §1.2 |
| Gradient backgrounds on charts | Adds no information, masks data | Flat fills only |
| Drop shadows everywhere | Reads as "1990s skeuomorphism" | Borders or elevation steps |
| Five+ accent colors | Information hierarchy collapses | Max 2 accents per view |
| Oversized whitespace ("modern", "clean") | Wastes 40% of the screen, traders hate it | Density rules from §3 |
| Icons without labels | New users guess; old users forget | Labels by default; icon-only behind tooltip |
| Animated everything | Looks toy-like, drops frames during fast tape | Motion only as defined in §5.1 |
| Numbers without tabular figures | Prices misalign in columns | Mandatory `font-variant-numeric: tabular-nums` |
| Centered numeric data | Magnitude comparison impossible | Right-align numbers always |
| Comic Sans / Papyrus / decorative fonts | Self-explanatory | Two-font rule from §2.1 |
| Decorative emoji | Reads as "consumer chat app" | Lucide icons only |
| GIF spinners | 2003 aesthetic | Skeleton states or subtle pulse |
| "Free trial" / sales banners | Reads as marketing site, not tool | A trading tool is not a landing page |
| Confidence shown as a percentage to 2 decimals (`73.42%`) | False precision destroys trust — implies the model is calibrated to 0.01% | Round to nearest 5% or show as Low/Med/High chip |
| Rainbow color palettes (jet, hsv) | Misleads on magnitude, fails CVD | Perceptually uniform colormaps from §1.5 |

### 11.2 The "casino" tell

A trading platform must not look like a gambling app. Differences to internalize:

| Casino aesthetic | Institutional aesthetic |
|------------------|------------------------|
| Saturated red/yellow/gold accents | Desaturated, neutral palette with restrained color |
| Gradient buttons with glow effects | Flat buttons with subtle border |
| Animated background particles | Static surfaces |
| "🎉 BIG WIN!" celebration overlays | No reaction to wins/losses, ever — the chart is the only feedback |
| Bonus / rewards / streak counters | Equity curve and risk metrics only |
| "Spin to win" / lottery interactions | Deterministic, deliberate execution flow |
| Sound effects on click | Silent except for explicit alert sounds |
| Confetti on order fill | Flash + log line, that's it |

If a feature *could* exist in an online casino, it does not belong in DEEP6.

---

## 12. Visual Storytelling for Indicators

### 12.1 Designing a confidence score that *looks* credible

The DEEP6 signal engine outputs a unified confidence score (0-1) per signal. A confidence number with no visible reasoning is gimmick. A confidence number with visible reasoning is research.

**Glance representation:**
- Small chip, 20-24px wide, color-coded:
  - `≥ 0.85` → green chip `#26A65B`, white text
  - `0.60-0.84` → amber chip `#F59E0B`, dark text
  - `< 0.60` → red chip `#E5484D`, white text
  - `< 0.40` → grey chip `#52525B`, white text — or simply *don't display the signal at all*
- Number rendered as `0.87`, never `87%` (percent implies calibration to 1% — 0-1 implies a model output)

**Scan representation:**
- Chip plus a tiny horizontal bar (60px wide, 4px tall) that visually represents the score
- Bar fill color matches chip color
- Background of bar at `bg.surface.raised`

**Hover/click representation:**
- Tooltip shows top 3 contributing signals, each with weight and value
- Shows when last computed (e.g., "12s ago")
- Shows historical hit rate for this score range (e.g., "Score range 0.85-0.95 historically wins 67% of the time, n=234")

**Anti-pattern:** showing the confidence as a 0-100 bar that *animates* up to its value on render. Looks gamified. Render the final value statically.

### 12.2 Alert states (info / success / warning / danger)

| State | Background | Border | Icon | Text |
|-------|------------|--------|------|------|
| Info | `oklch(0.32 0.10 257)` ≈ `#1E3A5F` | `#3B82F6` | `info` | `text.primary` |
| Success | `oklch(0.32 0.10 145)` ≈ `#1A4A30` | `#26A65B` | `check-circle` | `text.primary` |
| Warning | `oklch(0.34 0.10 70)` ≈ `#4A350A` | `#F59E0B` | `alert-triangle` | `text.primary` |
| Danger | `oklch(0.32 0.10 25)` ≈ `#4A1A1C` | `#E5484D` | `alert-octagon` | `text.primary` |

All use a 12px left border (4px wide if compact). Icon at 16px sized. Text at 13px. Padding `space.3` (12px).

### 12.3 Making ML/AI signals feel trustworthy

Three principles, drawn directly from human-AI collaboration research:

1. **Show provenance.** Every AI-derived value has a small "ai" indicator (a subtle `cpu` icon at 12px, color `accent.violet` `#8B5CF6`). The user always knows which numbers were generated by a model vs. computed deterministically.
2. **Show uncertainty honestly.** Never round low confidence up to look better. A 0.51 signal must look like 0.51, not 0.85. False confidence is the fastest way to destroy trust.
3. **Show calibration.** Periodically (e.g., end-of-session report), display the realized hit rate vs. predicted confidence. If the model says 0.80 and wins 78% of the time, show that. If it says 0.80 and wins 50% of the time, *show that too* — and surface the model as miscalibrated.

### 12.4 Conveying uncertainty visually

| Level of uncertainty | Visual treatment |
|----------------------|------------------|
| High confidence | Solid color, full opacity |
| Medium confidence | Solid color at 70% opacity |
| Low confidence | Diagonal hatching pattern overlay, or dashed border |
| Stale data | Reduced opacity (50%) + small `clock` icon |
| Estimated | Italic text + "≈" prefix |
| Predicted (ML) | Dashed line for the predicted region of a chart |
| Out-of-sample warning | Yellow `alert-triangle` badge with tooltip |

### 12.5 The trustworthy aesthetic checklist

Before shipping any indicator, the agent must verify:

- [ ] Numbers use tabular figures
- [ ] Color encodes state, never decoration
- [ ] Confidence is shown with provenance (where it came from)
- [ ] Uncertainty is shown, not hidden
- [ ] Stale data is visually distinct from fresh data
- [ ] No animation that hides a number
- [ ] No celebration / gamification cues
- [ ] Click-through to methodology is available
- [ ] Last-updated timestamp is visible somewhere on the surface
- [ ] CVD-safe (a deuteranope can read all state)
- [ ] Reduced-motion mode is respected
- [ ] Contrast ratios pass WCAG AA minimum

---

## 13. NinjaTrader / SharpDX Implementation Notes

The agent will primarily render via SharpDX in `OnRender`. Key constraints unique to this rendering path:

### 13.1 Brush lifecycle

Brushes are GPU-resident and tied to the `RenderTarget`. They must be:
- Created in `OnRenderTargetChanged` (or first `OnRender`)
- Cached in a `Dictionary<string, SharpDX.Direct2D1.Brush>`
- Disposed in `OnRenderTargetChanged` when target is null

```csharp
private Dictionary<string, SharpDX.Direct2D1.Brush> dxBrushes;

protected override void OnRenderTargetChanged()
{
    if (dxBrushes != null)
        foreach (var b in dxBrushes.Values) b?.Dispose();
    dxBrushes = new Dictionary<string, SharpDX.Direct2D1.Brush>();
    
    if (RenderTarget != null)
    {
        dxBrushes["bg.canvas"] = ToDxColor4(0x0A, 0x0A, 0x0B, 1.0f).ToBrush(RenderTarget);
        dxBrushes["directional.up"] = ToDxColor4(0x26, 0xA6, 0x5B, 1.0f).ToBrush(RenderTarget);
        // ... rest of palette
    }
}

private SharpDX.Color4 ToDxColor4(byte r, byte g, byte b, float a) =>
    new SharpDX.Color4(r / 255f, g / 255f, b / 255f, a);
```

Never `new SolidColorBrush(...)` inside `OnRender` — it will allocate per frame and destroy performance.

### 13.2 Text rendering

Pre-create `SharpDX.DirectWrite.TextFormat` objects in `OnStateChange(State.SetDefaults)` once per font/size combination. Cache. Reuse.

```csharp
private SharpDX.DirectWrite.TextFormat textFormatPriceBase;

protected override void OnStateChange()
{
    if (State == State.SetDefaults)
    {
        var factory = new SharpDX.DirectWrite.Factory();
        textFormatPriceBase = new SharpDX.DirectWrite.TextFormat(
            factory, "JetBrains Mono", SharpDX.DirectWrite.FontWeight.Medium,
            SharpDX.DirectWrite.FontStyle.Normal, 14f);
        textFormatPriceBase.TextAlignment = SharpDX.DirectWrite.TextAlignment.Trailing; // right-align
    }
}
```

Antialias mode: set once globally.

```csharp
RenderTarget.TextAntialiasMode = SharpDX.Direct2D1.TextAntialiasMode.Grayscale;
```

### 13.3 Performance budget

For 1000+ DOM updates/sec, `OnRender` runs frequently. Hard budget: <2ms per render. This means:
- No allocation in render path
- No string concatenation (use cached `StringBuilder` or pre-formatted strings)
- No font resolution
- No brush creation
- No file/log I/O

Profile every change. If a render exceeds 4ms, the chart will start dropping frames and the trader will feel it.

### 13.4 DPI scaling

`OnRender` receives the chart in DIPs (device-independent pixels). Multiply all explicit pixel sizes by `(float)PresentationSource.FromVisual(ChartControl)?.CompositionTarget.TransformToDevice.M11 ?? 1f` if rendering at native resolution. For most cases, working in DIPs is fine — Direct2D handles the scale.

---

## 14. The Ten Commandments (Quick Reference)

For the agent's working memory:

1. **Two fonts. Always.** Inter for chrome, JetBrains Mono for data.
2. **Tabular figures everywhere.** No exceptions for numbers.
3. **8px grid.** Every margin, padding, gap is a multiple of 4, usually 8.
4. **Dark canvas at `#0A0A0B`.** Elevate surfaces by lightness, not shadow.
5. **Color = state.** Amber/white = neutral data. Green = up. Red = down. Blue = action. Violet = AI/ML.
6. **Right-align numbers.** Center-align is for poetry.
7. **No motion that hides data.** Price flashes are 200ms and only that.
8. **Density first.** Traders want more, not less. Whitespace is for designers.
9. **CVD-safe by default.** Color + shape + position. Always redundant.
10. **Trust by transparency.** Show provenance, show uncertainty, show last-updated.

If a design choice conflicts with one of these, the design choice loses.

---

## Sources

- [Bloomberg: Designing the Terminal for Color Accessibility](https://www.bloomberg.com/company/stories/designing-the-terminal-for-color-accessibility/)
- [Bloomberg: How Bloomberg Terminal UX designers conceal complexity](https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/)
- [Ted Merz: Amber on Black (Bloomberg history)](https://ted-merz.com/2021/06/26/amber-on-black/)
- [Bookmap: Heatmap Trading Guide](https://bookmap.com/blog/heatmap-in-trading-the-complete-guide-to-market-depth-visualization)
- [Bookmap: The Role of Color Psychology in Market Data Visualization](https://bookmap.com/blog/the-role-of-color-psychology-in-market-data-visualization)
- [Bookmap: Heatmap settings (Knowledge Base)](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapSettings)
- [TradingView Brand Color Palette](https://mobbin.com/colors/brand/tradingview)
- [Linear: How we redesigned the Linear UI](https://linear.app/now/how-we-redesigned-the-linear-ui)
- [Linear: A calmer interface for a product in motion](https://linear.app/now/behind-the-latest-design-refresh)
- [Material Design: Dark Theme](https://github.com/material-components/material-components-android/blob/master/docs/theming/Dark.md)
- [Material Design dark theme codelab](https://codelabs.developers.google.com/codelabs/design-material-darktheme)
- [Muzli: Dark Mode Design Systems Complete Guide](https://muz.li/blog/dark-mode-design-systems-a-complete-guide-to-patterns-tokens-and-hierarchy/)
- [W3C WCAG 2.2 Understanding Contrast (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
- [WebAIM: Contrast and Color Accessibility](https://webaim.org/articles/contrast/)
- [MDN: prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion)
- [web.dev: prefers-reduced-motion](https://web.dev/articles/prefers-reduced-motion)
- [W3C WCAG 2.1 Animation from Interactions](https://www.w3.org/WAI/WCAG21/Understanding/animation-from-interactions.html)
- [Tatiana Mac: prefers-reduced-motion no-motion-first](https://www.tatianamac.com/posts/prefers-reduced-motion)
- [Okabe-Ito color palette reference](https://easystats.github.io/see/reference/scale_color_okabeito.html)
- [Coloring for Colorblindness — David Nichols](https://davidmathlogic.com/colorblind/)
- [VisualisingData: Five ways to design for red-green colour-blindness](https://visualisingdata.com/2019/08/five-ways-to-design-for-red-green-colour-blindness/)
- [Matplotlib Choosing Colormaps](https://matplotlib.org/stable/users/explain/colors/colormaps.html)
- [Viridis colormap intro](https://cran.r-project.org/web/packages/viridis/vignettes/intro-to-viridis.html)
- [Domestic Engineering: Why Viridis not Jet](https://www.domestic-engineering.com/drafts/viridis/viridis.html)
- [Kenneth Moreland: Color Map Advice for Scientific Visualization](https://www.kennethmoreland.com/color-advice/)
- [OKLCH Color Picker (Evil Martians)](https://oklch.com/)
- [Evil Martians: OKLCH in CSS — why we moved from RGB and HSL](https://evilmartians.com/chronicles/oklch-in-css-why-quit-rgb-hsl)
- [Björn Ottosson: Two new color spaces for color picking — Okhsv and Okhsl](https://bottosson.github.io/posts/colorpicker/)
- [Oklab color space (Wikipedia)](https://en.wikipedia.org/wiki/Oklab_color_space)
- [Tufte: The Visual Display of Quantitative Information](https://www.edwardtufte.com/book/the-visual-display-of-quantitative-information/)
- [Tufte: Sparkline theory and practice](https://www.edwardtufte.com/notebook/sparkline-theory-and-practice-edward-tufte/)
- [GA Tech: Tufte's Design Principles (PDF)](https://faculty.cc.gatech.edu/~stasko/7450/16/Notes/tufte.pdf)
- [Interaction Design Foundation: Preattentive Visual Properties](https://ixdf.org/literature/article/preattentive-visual-properties-and-how-to-use-them-in-information-visualization)
- [Preattentive attributes in data visualization (UX Collective)](https://uxdesign.cc/preattentive-attributes-of-visual-perception-and-their-application-to-data-visualizations-7b0fb50e1375)
- [JetBrains Mono](https://www.jetbrains.com/lp/mono/)
- [IBM Plex Mono — Google Fonts](https://fonts.google.com/specimen/IBM+Plex+Mono)
- [MadeGood: Best Coding Fonts (Berkeley Mono context)](https://madegooddesigns.com/coding-fonts/)
- [MDN: font-variant-numeric](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/font-variant-numeric)
- [MDN: font-feature-settings](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/font-feature-settings)
- [OpenType tnum (otf.show)](https://otf.show/tnum)
- [TypeNetwork: OpenType at Work — Figure Styles](https://typenetwork.com/articles/opentype-at-work-figure-styles)
- [Lucide Icons](https://lucide.dev/)
- [Cieden: Spacing best practices (8pt grid system)](https://cieden.com/book/sub-atomic/spacing/spacing-best-practices)
- [UX Planet: 8 point grid system in UX design](https://uxplanet.org/everything-you-should-know-about-8-point-grid-system-in-ux-design-b69cb945b18d)
- [easings.net — Easing Functions Cheat Sheet](https://easings.net/)
- [MDN: cubic-bezier()](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Values/easing-function/cubic-bezier)
- [Crafting Easing Curves for User Interfaces (Ryan Brownhill)](https://medium.com/@ryan_brownhill/crafting-easing-curves-for-user-interfaces-34f39e1b4a43)
- [Stripe: Designing accessible color systems](https://stripe.com/blog/accessible-color-systems)
- [Vercel Design System Breakdown (SeedFlip)](https://seedflip.co/blog/vercel-design-system)
- [Fey App — Dark Themed Websites](https://www.dark.design/website/fey)
- [Fey: Make better investments](https://fey.com/)
- [Daniel Cheung: Asian vs Western stock market color schemes](https://medium.com/@danvim/deep-dive-into-the-opposing-color-schemes-in-asian-vs-western-stock-market-prices-part-1-origin-4e3ccdb27c99)
- [BehavioralEconomics.com: When Red Means Go (Cultural Reactance)](https://www.behavioraleconomics.com/when-red-means-go/)
- [AI UX Design Guide: Confidence Visualization](https://www.aiuxdesign.guide/patterns/confidence-visualization)
- [Agentic Design: Confidence Visualization UI Patterns](https://agentic-design.ai/patterns/ui-ux-patterns/confidence-visualization-patterns)
- [Frontiers: Trusting AI — does uncertainty visualization affect decision-making](https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2025.1464348/full)
- [Google PAIR: Explainability + Trust](https://pair.withgoogle.com/chapter/explainability-trust/)
- [NinjaTrader: Using SharpDX for Custom Chart Rendering](https://ninjatrader.com/support/helpguides/nt8/using_sharpdx_for_custom_chart_rendering.htm)
- [NinjaTrader Forum: DX Brushes for drawing heatmap best practice](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/105264-dx-brushes-for-drawing-heatmap-best-practice)
- [NinjaTrader Forum: Brush to SharpDx.color](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1198391-brush-to-sharpdx-color)
- [Awwwards: Dashboard Inspiration](https://www.awwwards.com/inspiration/dashboard-blanktm)
- [Orbital Computers: Configuring Multi-Monitor Trading PC Setups](https://orbitalcomputers.com/working-with-multi-monitor-setups-5-screens/)
- [TradeFundrr: Best Multi Monitor Setups for Traders](https://tradefundrr.com/best-multi-monitor-setups-for-traders/)
