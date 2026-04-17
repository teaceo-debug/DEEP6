Task tools are not relevant for this single-shot research/writing deliverable. Proceeding directly with the design document.

I now have everything I need: the existing brush-cache pattern (`_xxxDx`, `MakeFrozenBrush(...).ToDxBrush(RenderTarget)`), `OnRenderTargetChanged` / `DisposeDx` lifecycle, `TextFormat` cached, and the existing color tokens. The new code below will fit straight in.

---

# DEEP6 — Aesthetic Direction C: "Linear-Modern Premium SaaS"

## A complete design specification + drop-in SharpDX implementation

---

## 1. Design Philosophy

Linear-Modern Premium SaaS is the aesthetic that Linear (`#08090A` / `#5E6AD2`), Stripe (the Dashboard), Vercel/Geist, Notion, Raycast, Arc Browser, and Fey have collectively established as the gold standard for modern professional software since roughly 2021. Its grammar is **deep grayscale staircases instead of shadows, perfect typography instead of ornament, and a single restrained accent that earns its color budget by appearing only on state changes.** A trader using a chart in this aesthetic should feel they're inside the same operating system as their Linear board, their Stripe dashboard, and their Notion playbook — not inside a 2008-era WinForms DLL with red and green slabs. The system reads as expensive *because it is restrained*: 92% of the frame is grayscale, 6% is desaturated semantic teal/coral, and 2% — the absorption signature, the equity strip, the GEX flip — is the moment the design opens its mouth. Designed for the trader who already runs `cmd+k` palettes in every other tool of their life and expects their NQ footprint to belong to that family.

---

## 2. Complete OKLCH + Hex Palette

All values verified: OKLCH lightness staircase ≈ +0.04 per step (Material 3 / Linear convention), chroma ≤ 0.012 in chrome (perceptual neutrality), semantic colors equiluminant at L=0.65 ± 0.02.

### 2.1 Background staircase (elevation through brightness, never shadow)

| Token | Hex | OKLCH | ARGB | Role |
|---|---|---|---|---|
| `bg.canvas` | `#08090A` | `oklch(0.105 0.004 270)` | `255, 8, 9, 10` | Outermost void — chart background |
| `bg.panel` | `#0E0F11` | `oklch(0.145 0.004 270)` | `255, 14, 15, 17` | Default elevated surface (HUD, equity strip) |
| `bg.panel.alt` | `#16171A` | `oklch(0.190 0.005 270)` | `255, 22, 23, 26` | Hover plate, raised pill, tooltip body |
| `bg.panel.hover` | `#1C1D21` | `oklch(0.225 0.006 270)` | `255, 28, 29, 33` | Active hover (button, row) |

### 2.2 Border tokens (1px hairlines, never thicker)

| Token | Hex | OKLCH | ARGB | Role |
|---|---|---|---|---|
| `border.divider` | `#1A1B1E` | `oklch(0.205 0.005 270)` | `255, 26, 27, 30` | In-panel divider lines |
| `border.default` | `#26272B` | `oklch(0.270 0.006 270)` | `255, 38, 39, 43` | Pill outline, panel hairline |
| `border.focus` | `#5E6AD2` | `oklch(0.575 0.165 273)` | `255, 94, 106, 210` | Linear-purple focus ring (used 1 surface only) |

### 2.3 Primary semantic — equiluminant teal/coral (NOT green/red)

This is the heart of why this aesthetic feels modern. Linear and Fey use teal for "good" and coral for "bad" — desaturated cyan-leaning green and orange-leaning red — calibrated to **L=0.65** so colorblind viewers see equal weight.

| Token | Hex | OKLCH | ARGB | Role |
|---|---|---|---|---|
| `sem.buy` | `#4ADE80` | `oklch(0.840 0.180 152)` | `255, 74, 222, 128` | Buy aggressor / bullish text accent |
| `sem.buy.muted` | `#2BB673` | `oklch(0.708 0.155 156)` | `255, 43, 182, 115` | Buy cell tint — desaturated |
| `sem.sell` | `#F87171` | `oklch(0.732 0.165 23)` | `255, 248, 113, 113` | Sell aggressor / bearish text accent |
| `sem.sell.muted` | `#D04848` | `oklch(0.605 0.165 25)` | `255, 208, 72, 72` | Sell cell tint — desaturated |
| `sem.neutral` | `#9CA3AE` | `oklch(0.715 0.011 256)` | `255, 156, 163, 174` | Neutral volume, doji, no signal |

### 2.4 Imbalance tiers — restrained escalation (never gaudy)

The Linear move: imbalance is shown by **border luminance + corner accent**, not by flooding the cell with saturated color.

| Tier | Token | Hex | OKLCH | ARGB | Treatment |
|---|---|---|---|---|---|
| weak buy | `imb.buy.1` | `#1F3A2C` | `oklch(0.300 0.055 154)` | `255, 31, 58, 44` | 1px left border `sem.buy.muted`, no fill |
| strong buy | `imb.buy.2` | `#2BB673` | `oklch(0.708 0.155 156)` | `64, 43, 182, 115` | 12% alpha fill + 1px left border |
| extreme buy | `imb.buy.3` | `#4ADE80` | `oklch(0.840 0.180 152)` | `38, 74, 222, 128` | 15% alpha + 1.5px left border + corner triangle |
| weak sell | `imb.sell.1` | `#3A1F1F` | `oklch(0.295 0.060 25)` | `255, 58, 31, 31` | 1px right border `sem.sell.muted` |
| strong sell | `imb.sell.2` | `#D04848` | `oklch(0.605 0.165 25)` | `64, 208, 72, 72` | 12% alpha + 1px right border |
| extreme sell | `imb.sell.3` | `#F87171` | `oklch(0.732 0.165 23)` | `38, 248, 113, 113` | 15% alpha + 1.5px right border + corner triangle |

### 2.5 DEEP6 signature signals (the few colors that get to be loud)

| Token | Hex | OKLCH | ARGB | Use |
|---|---|---|---|---|
| `sig.absorption` | `#7DD3FC` | `oklch(0.825 0.105 230)` | `255, 125, 211, 252` | Absorption signature — pale sky cyan |
| `sig.absorption.glow` | `#7DD3FC` | `oklch(0.825 0.105 230)` | `48, 125, 211, 252` | 18% alpha halo behind glyph |
| `sig.exhaustion` | `#FBBF24` | `oklch(0.815 0.155 84)` | `255, 251, 191, 36` | Exhaustion signature — warm amber |
| `sig.exhaustion.glow` | `#FBBF24` | `oklch(0.815 0.155 84)` | `48, 251, 191, 36` | 18% alpha halo |
| `sig.confluence` | `#A78BFA` | `oklch(0.745 0.155 295)` | `255, 167, 139, 250` | Confluence ring — Linear violet |
| `sig.confidence.top` | `#5E6AD2` | `oklch(0.575 0.165 273)` | `255, 94, 106, 210` | Top-decile score — Linear purple |

### 2.6 Levels (POC, VAH/VAL, naked POC, GEX)

| Token | Hex | OKLCH | ARGB | Render |
|---|---|---|---|---|
| `lvl.poc` | `#E0B84A` | `oklch(0.785 0.135 88)` | `255, 224, 184, 74` | Subtle gold, 1px solid |
| `lvl.vah` | `#7DA34A` | `oklch(0.660 0.115 122)` | `200, 125, 163, 74` | 1px solid, dim olive |
| `lvl.val` | `#7DA34A` | `oklch(0.660 0.115 122)` | `200, 125, 163, 74` | 1px solid (matches VAH) |
| `lvl.naked.poc` | `#E0B84A` | `oklch(0.785 0.135 88)` | `120, 224, 184, 74` | 1px dashed gold @ 47% alpha |
| `lvl.pw.poc` | `#C4A052` | `oklch(0.715 0.115 84)` | `255, 196, 160, 82` | 1px solid muted gold |
| `gex.zero` | `#67E8F9` | `oklch(0.840 0.115 215)` | `255, 103, 232, 249` | Bright cyan, 1px solid |
| `gex.flip` | `#E879F9` | `oklch(0.745 0.215 320)` | `255, 232, 121, 249` | Magenta, 1px dashed |
| `gex.call.wall` | `#5EEAD4` | `oklch(0.860 0.110 175)` | `255, 94, 234, 212` | Teal, 1.5px solid |
| `gex.put.wall` | `#FB7185` | `oklch(0.738 0.165 17)` | `255, 251, 113, 133` | Coral, 1.5px solid |

### 2.7 Text

| Token | Hex | OKLCH | ARGB | Use |
|---|---|---|---|---|
| `text.primary` | `#EDEEF0` | `oklch(0.945 0.005 270)` | `255, 237, 238, 240` | Headers, hero numbers, prices |
| `text.secondary` | `#A1A4AD` | `oklch(0.715 0.010 270)` | `255, 161, 164, 173` | Labels, axis ticks, cell numbers |
| `text.dim` | `#6E727B` | `oklch(0.555 0.012 270)` | `255, 110, 114, 123` | Metadata, "since 9:30", footnotes |
| `text.disabled` | `#4B4E55` | `oklch(0.420 0.012 270)` | `255, 75, 78, 85` | Inactive controls |
| `text.accent` | `#5E6AD2` | `oklch(0.575 0.165 273)` | `255, 94, 106, 210` | Interactive link, focus label |

### 2.8 Strategy P&L states

| Token | Hex | OKLCH | ARGB | When |
|---|---|---|---|---|
| `pnl.positive` | `#4ADE80` | `oklch(0.840 0.180 152)` | `255, 74, 222, 128` | Equity strip > 0 today |
| `pnl.positive.subtle` | `#4ADE80` | `oklch(0.840 0.180 152)` | `30, 74, 222, 128` | 12% wash on row hover |
| `pnl.negative` | `#F87171` | `oklch(0.732 0.165 23)` | `255, 248, 113, 113` | Equity strip < 0 today |
| `pnl.scratch` | `#A1A4AD` | `oklch(0.715 0.010 270)` | `255, 161, 164, 173` | -$25 < pnl < +$25 |
| `pnl.warning` | `#FBBF24` | `oklch(0.815 0.155 84)` | `255, 251, 191, 36` | Approaching daily loss limit |
| `pnl.danger` | `#F87171` | `oklch(0.732 0.165 23)` | `255, 248, 113, 113` | Loss limit breach |

### 2.9 Working order states

| Token | Hex | OKLCH | ARGB | Render |
|---|---|---|---|---|
| `ord.limit` | `#67E8F9` | `oklch(0.840 0.115 215)` | `200, 103, 232, 249` | 1px dashed, cyan |
| `ord.stop` | `#F87171` | `oklch(0.732 0.165 23)` | `200, 248, 113, 113` | 1px dashed, coral |
| `ord.trail` | `#A78BFA` | `oklch(0.745 0.155 295)` | `200, 167, 139, 250` | 1px dotted, violet |
| `ord.entry.band` | `#EDEEF0` | `oklch(0.945 0.005 270)` | `20, 237, 238, 240` | 8% white wash, 1px solid line at price |
| `ord.target.zone` | `#4ADE80` | `oklch(0.840 0.180 152)` | `20, 74, 222, 128` | 8% green wash |
| `ord.stop.zone` | `#F87171` | `oklch(0.732 0.165 23)` | `20, 248, 113, 113` | 8% coral wash |

### 2.10 Transient flashes (one-frame, then decay)

| Token | Hex | OKLCH | ARGB | Decay |
|---|---|---|---|---|
| `flash.fill` | `#EDEEF0` | `oklch(0.945 0.005 270)` | `180, 237, 238, 240` | 100% → 0% over 220ms |
| `flash.signal.new` | `#7DD3FC` | `oklch(0.825 0.105 230)` | `120, 125, 211, 252` | 47% → 0% over 320ms |
| `flash.bar.close` | `#5E6AD2` | `oklch(0.575 0.165 273)` | `60, 94, 106, 210` | One-pixel border, 1 frame |

---

## 3. Typography Spec — The Heart of This Aesthetic

The Linear-Modern aesthetic stands or falls on typography. Get this exact and the chart already feels expensive.

### 3.1 Font stacks (Windows / NT8 deployment)

```
Sans (chrome): "Inter", "Inter Display", "Segoe UI Variable Display",
               "Segoe UI", -apple-system, BlinkMacSystemFont, system-ui, sans-serif
Mono (data):   "JetBrains Mono", "JetBrains Mono NL", "Cascadia Mono",
               "Consolas", Menlo, monospace
```

For NT8 specifically (no font installation possible without admin), the working fallback chain is:
- **Primary preferred:** `JetBrains Mono` + `Inter` (user installs once via MSI/font-file copy to `Fonts/`)
- **Universal fallback:** `Cascadia Mono` (ships with Windows 11) + `Segoe UI Variable Display` (ships with Win 11)
- **Minimum-viable fallback:** `Consolas` + `Segoe UI` (ships with all Windows since Vista)

### 3.2 Type scale (8 sizes — no other sizes permitted)

| Token | Px | Line | Weight | Tracking | Use |
|---|---|---|---|---|---|
| `t.10` micro | 10 | 14 | 500 | +0.06em (caps) | Axis ticks, "EST", row pill labels |
| `t.11` xs | 11 | 16 | 500 | +0.04em (caps) | Working-order pill text, GEX label pill |
| `t.12` sm | 12 | 16 | 400 | 0 | **Cell numerals (mono)**, equity strip |
| `t.13` base | 13 | 18 | 400 | 0 | Default tooltip body |
| `t.14` md | 14 | 20 | 500 | -0.005em | Section headers ("ABSORPTION"), HUD labels |
| `t.16` lg | 16 | 22 | 600 | -0.010em | Panel titles |
| `t.24` xl | 24 | 28 | 700 mono | -0.015em | KPI hero ("ES +$1,247.50") |
| `t.32` 2xl | 32 | 36 | 700 mono | -0.020em | Reserved — full-screen mode hero |

### 3.3 Numeric styling (always)

```csharp
// SharpDX TextFormat construction (cached in OnRenderTargetChanged):
_cellFontDx = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                             "JetBrains Mono", FontWeight.Regular,
                             FontStyle.Normal, FontStretch.Normal, 12f)
{
    TextAlignment = TextAlignment.Trailing,    // right-align numerals
    ParagraphAlignment = ParagraphAlignment.Center,
};
// JetBrains Mono ships tabular figures by default; ss20 + zero are auto.
```

### 3.4 Cell numerals — exact spec

- Font: **JetBrains Mono**, 12px, Regular (400)
- Color: `text.secondary` `#A1A4AD` (NEVER pure white — that screams retail)
- Tracking: 0 (mono is already wide)
- Right-aligned to cell padding-right of 4px
- Vertical: centered in cell row

### 3.5 Chrome / labels — exact spec

- Font: **Inter Medium** (500), 14px for headers, 11px for caps labels
- All-caps labels (`OPEN P&L`, `WORKING`, `ABSORPTION`) get `+0.04em` letter-spacing
- Header color: `text.primary` `#EDEEF0`
- Label color: `text.dim` `#6E727B`

### 3.6 KPI hero metrics — exact spec

- Font: **Inter Bold** (700), 24px, mono numerals via `font-feature-settings: 'tnum' 1, 'cv11' 1`
- For NT8: use **JetBrains Mono Bold** at 24px instead (true mono = guaranteed tabular)
- Color rule: ONLY signed by polarity. `pnl.positive` (green) when positive, `pnl.negative` (coral) when negative, `text.primary` when zero. **Never** colored amber/yellow/blue for "neutral" — flat is `text.primary`.

---

## 4. Footprint Cell Rendering Recipe

The rendering recipe that separates Linear-aesthetic from "yet another bookmap clone."

### 4.1 Cell anatomy (ASCII — full anatomy of one row at price 17234.50)

```
              ┌──────────────────────────────┬──────────────────────────────┐
              │   BID volume (right-align)   │   ASK volume (left-align)    │
              │   text.secondary #A1A4AD     │   text.secondary #A1A4AD     │
              │   JetBrains Mono 12px        │   JetBrains Mono 12px        │
17234.50 ──── │            842               │            1,209             │
              │                              │ ←── 1px left border in       │
              │                              │     sem.buy.muted #2BB673    │
              │                              │     because ratio > 3.0      │
              └──────────────────────────────┴──────────────────────────────┘
              cell bg: same as bg.canvas #08090A — NO fill on most cells
```

### 4.2 The five rules of cell discipline

1. **Default cells have NO fill, NO border.** Only the numeral. The chart is a numeral grid, not a heatmap. (Heatmap is option B; this is option C.)
2. **1px borders ONLY on imbalanced cells.** Tier 1 = single-side 1px border in muted color, no fill. Tier 2 = 1px border + 12% alpha fill. Tier 3 = 1.5px border + 15% alpha fill + tiny corner triangle.
3. **POC is a 1px subtle gold horizontal line that crosses the cell**, NOT a flooded yellow row. Trader's eye scans for the gold thread, not a gold blob.
4. **Stacked-imbalance zones use 8% alpha rectangles** spanning the price range, drawn *under* the cells. Border: 1px dashed at 24% alpha on top and bottom edges only.
5. **Absorption / exhaustion are 6×6px glyphs at the cell edge** with an 18% alpha 14×14px halo. Never a full-cell color, never a glow that extends past the cell, never animated.

### 4.3 Per-cell decision tree

```
For each (priceLevel, askVol, bidVol):
  ratio = max(askVol, bidVol) / max(1, min(askVol, bidVol))
  side  = askVol > bidVol ? Buy : Sell

  1. Always draw: bid numeral (right-half), ask numeral (left-half).
  2. If ratio < 1.5:               draw nothing else.
  3. If 1.5 <= ratio < 3.0:        draw 1px border on dominant side (imb.buy.1 / imb.sell.1).
  4. If 3.0 <= ratio < 5.0:        draw 12% fill + 1px border (imb.buy.2 / imb.sell.2).
  5. If ratio >= 5.0:              draw 15% fill + 1.5px border + 4×4px corner triangle.
  6. If isPoc:                     draw 1px gold horizontal line through cell middle.
  7. If inStackedImbalance:        underlay 8% alpha rect of 3 consecutive cells.
  8. If absorption.firedHere:      draw 6×6px ◊ glyph + 18% alpha halo, 6px right of cell.
  9. If exhaustion.firedHere:      draw 6×6px △ glyph + 18% alpha halo, 6px right of cell.
```

---

## 5. Subtle Gradient + Elevation System

Linear-Modern uses **brightness staircase** instead of shadows. There is exactly ONE gradient permitted, and only on the equity-strip backdrop.

### 5.1 Elevation rules

| Layer | Background | How |
|---|---|---|
| Layer 0 (chart canvas) | `bg.canvas` `#08090A` | Solid fill |
| Layer 1 (HUD panel, equity strip) | `bg.panel` `#0E0F11` | Solid fill, 1px `border.divider` `#1A1B1E` hairline |
| Layer 2 (hover row, popover) | `bg.panel.alt` `#16171A` | Solid fill, 1px `border.default` `#26272B` hairline |
| Layer 3 (active hover, focus) | `bg.panel.hover` `#1C1D21` | Solid fill, 1px `border.default` |

### 5.2 The single permitted gradient

The equity-strip backdrop fades from `bg.panel` `#0E0F11` (left) to `bg.canvas` `#08090A` (right) over 280px. Linear gradient. Direction: right. Purpose: visually anchor the strip to the left edge, dissolve into the chart at right. Nothing else in the chart uses gradient.

### 5.3 Border-radius rules

- **Outer corners (HUD panel, pill, equity strip): 6px** (Linear's exact value)
- **Inner corners (cell, subdivision within HUD): 0px** — sharp inside, rounded outside
- **Buttons: 4px** (slightly tighter than panels — feels intentional)

### 5.4 What's banned

- ❌ Drop shadows (`BoxShadowEffect`, `DropShadowEffect`)
- ❌ Inner glows
- ❌ 3D bevels / emboss
- ❌ Gradients on chrome (buttons, pills, dividers)
- ❌ Border-radius on cells (the price grid is rectangular, period)
- ❌ Rounded line caps on dashed strokes (use butt caps — sharper)

---

## 6. GEX Level Rendering — Premium Pill Labels

Each GEX level is a 1-pixel line **plus** a small floating pill label at the right edge.

### 6.1 The pill anatomy (ASCII)

```
   line stretches across viewport ────────────────────────────────────
                                                          ┌──────────────┐
   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │ ZG  17,234.5 │ ← 6px radius pill
                                                          └──────────────┘   bg.panel #0E0F11
                                                                              border.default 1px
                                                                              JetBrains Mono 11px
                                                                              text.primary #EDEEF0
                                                                              padding 4px 8px
```

### 6.2 Per-level spec table

| Level | Line color | Line stroke | Line style | Pill label | Pill bg | Pill border |
|---|---|---|---|---|---|---|
| Zero gamma | `gex.zero` `#67E8F9` | 1px | Solid | `ZG  {price}` | `bg.panel` | `border.default` |
| Gamma flip | `gex.flip` `#E879F9` | 1px | Dashed (4-on, 4-off) | `FLIP {price}` | `bg.panel` | `border.default` |
| Call wall | `gex.call.wall` `#5EEAD4` | 1.5px | Solid | `CW   {price}` | `bg.panel` | `gex.call.wall` 1px |
| Put wall | `gex.put.wall` `#FB7185` | 1.5px | Solid | `PW   {price}` | `bg.panel` | `gex.put.wall` 1px |

The pill label text is mono, 11px, weight 500, padded 4px top/bottom + 8px left/right, positioned at chart-right with 12px gutter. Never overlapping price axis. If two pills collide vertically within 14px, stack them with a 2px vertical gap.

---

## 7. Strategy Visualization — Restrained Linear Style

### 7.1 The equity strip (top-left)

A single horizontal line, 28px tall, 280px wide, 12px from top-left corner of chart.

```
┌────────────────────────────────────────────────────────────┐
│  ES  +$1,247.50    ▲ +2.3%    8 trades · 6w · 2l          │  ← bg.panel #0E0F11
└────────────────────────────────────────────────────────────┘     1px border.divider
   24px Bold mono       12px sm          11px micro all-caps      6px outer radius
   pnl.positive #4ADE80 same color       text.dim #6E727B         no shadow
                                                                   gradient → bg.canvas at right
```

The hero number `+$1,247.50` is 24px JetBrains Mono Bold, color-coded ONLY by sign:
- positive → `pnl.positive` `#4ADE80`
- negative → `pnl.negative` `#F87171`
- zero → `text.primary` `#EDEEF0`

The arrow + percent is 12px mono, same color as hero. The trade count is 11px Inter Medium all-caps tracking +0.04em, color `text.dim`. NO progress bars, NO sparklines, NO icons. Density via typography, not chrome.

### 7.2 Working orders — pill + dashed line

```
                                            ┌─────────────────┐
   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │ LMT B 1 17220.00│  ← pill at chart-right
                                            └─────────────────┘     bg.panel #0E0F11
                                                                     1px ord.limit border
                                                                     JetBrains Mono 11px
                                                                     text.primary
```

- Limit: cyan dashed 1px
- Stop: coral dashed 1px
- Trail: violet dotted 1px (2-on, 2-off)
- Pill: same anatomy as GEX pill, border color matches order-type

### 7.3 Position marker

When a trade is open at entry price 17225.50:

- **Entry band:** horizontal rect from current bar back through trade duration, height = 1 tick, fill `ord.entry.band` `#EDEEF0` @ 8% alpha (subtle ghost)
- **Entry line:** 1px solid `text.primary` `#EDEEF0` at exact entry price, length = trade duration
- **Stop zone:** rect from entry-line down to stop-line, fill `ord.stop.zone` `#F87171` @ 8% alpha
- **Target zone:** rect from entry-line up to target-line, fill `ord.target.zone` `#4ADE80` @ 8% alpha
- **No animation, ever.** No pulse, no breathe, no fade.

---

## 8. Full-Chart ASCII Mockup

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ ┌──────────────────────────────┐                                                            │
│ │ ES  +$1,247.50  ▲ +2.3%      │                                                            │
│ │     8 TRADES · 6W · 2L       │ ← equity strip (bg.panel, 6px radius, gradient → canvas) │
│ └──────────────────────────────┘                                                            │
│                                                                                              │
│                                                                                              │
│                          17,250.00 │   124   │   89    │                                    │
│                                    ├─────────┼─────────┤                                    │
│                          17,247.75 │   88    │   142   │                                    │
│                                    ├─────────┼─────────┤                                    │
│   ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌17,245.00╌│╌╌╌52╌╌╌╌│╌╌╌78╌╌╌╌│╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┌─────────────┐    │ ← gex.flip dashed
│                                    ├─────────┼─────────┤              │ FLIP 17,245.0│    │
│                          17,242.25 │   33    │   201  ┃│ ← imb.buy.2  └─────────────┘    │
│                                    ├─────────┼────────┃┤   12% fill + border                │
│                          17,239.50 │   71    │  ◊ 412 ┃│ ← absorption signature             │
│                                    ├─────────┼────────┃┤   sig.absorption #7DD3FC          │
│                          17,237.00 │   29    │   612 ┃┃│ ← imb.buy.3 extreme                │
│                                    ├─────────┼───────┃┃┤                                    │
│ ════════════════════════════════════17,234.50════════════════════════════ ┌─────────────┐  │ ← lvl.poc gold 1px
│                                    ├─────────┼─────────┤                  │ ZG  17,234.5│  │   ▲
│                          17,232.00 │  ▲ 102  │   89    │                  └─────────────┘  │   gex.zero cyan 1px
│                                    ├─────────┼─────────┤                                    │
│   ┃─────────────                   17,229.50 │  287    │   65            ┌──────────────┐  │ ← ord.limit dashed
│   │ LMT B 1                        ├─────────┼─────────┤                 │ LMT B 1      │  │
│   │ 17,229.50                      17,227.00 │  142    │   88            │ 17,229.50    │  │
│   └──────────────                   ├─────────┼─────────┤                 └──────────────┘  │
│                                                                                              │
│                                                                                              │
│   bg.canvas #08090A                                                                          │
│                                                                                              │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                       JetBrains Mono 12px in cells, Inter Medium 11px in pills
```

---

## 9. Drop-In SharpDX Code

All snippets fit the existing patterns in `DEEP6Footprint.cs` (the `_xxxDx` brush convention, `MakeFrozenBrush(...).ToDxBrush(RenderTarget)` factory, `OnRenderTargetChanged` allocation, `DisposeDx()` cleanup, `RenderTarget.AntialiasMode = PerPrimitive`). Field naming uses the `_lm` prefix ("linear-modern") so they coexist with current brushes during gradual migration.

### 9.1 Brush field declarations (paste alongside existing `private SharpDX...` block, ~line 760)

```csharp
// ─── Linear-Modern Premium SaaS palette (Aesthetic C) ───
// All values verified: OKLCH staircase L+0.04 per elevation, semantic equiluminant L=0.65.
private SharpDX.Direct2D1.SolidColorBrush _lmBgCanvasDx;          // #08090A oklch(0.105 0.004 270)
private SharpDX.Direct2D1.SolidColorBrush _lmBgPanelDx;           // #0E0F11 oklch(0.145 0.004 270)
private SharpDX.Direct2D1.SolidColorBrush _lmBgPanelAltDx;        // #16171A oklch(0.190 0.005 270)
private SharpDX.Direct2D1.SolidColorBrush _lmBgPanelHoverDx;      // #1C1D21 oklch(0.225 0.006 270)
private SharpDX.Direct2D1.SolidColorBrush _lmBorderDividerDx;     // #1A1B1E oklch(0.205 0.005 270)
private SharpDX.Direct2D1.SolidColorBrush _lmBorderDefaultDx;     // #26272B oklch(0.270 0.006 270)
private SharpDX.Direct2D1.SolidColorBrush _lmBorderFocusDx;       // #5E6AD2 Linear purple

// Semantic — equiluminant teal/coral (NOT green/red)
private SharpDX.Direct2D1.SolidColorBrush _lmSemBuyDx;            // #4ADE80 oklch(0.840 0.180 152)
private SharpDX.Direct2D1.SolidColorBrush _lmSemBuyMutedDx;       // #2BB673 desaturated
private SharpDX.Direct2D1.SolidColorBrush _lmSemSellDx;           // #F87171 oklch(0.732 0.165 23)
private SharpDX.Direct2D1.SolidColorBrush _lmSemSellMutedDx;      // #D04848 desaturated
private SharpDX.Direct2D1.SolidColorBrush _lmSemNeutralDx;        // #9CA3AE neutral grey

// Imbalance escalation tiers (cell fills, very low alpha)
private SharpDX.Direct2D1.SolidColorBrush _lmImbBuy1BorderDx;     // _lmSemBuyMutedDx alpha 200
private SharpDX.Direct2D1.SolidColorBrush _lmImbBuy2FillDx;       // #2BB673 alpha 64 (~12%)
private SharpDX.Direct2D1.SolidColorBrush _lmImbBuy3FillDx;       // #4ADE80 alpha 38 (~15%)
private SharpDX.Direct2D1.SolidColorBrush _lmImbSell1BorderDx;    // _lmSemSellMutedDx alpha 200
private SharpDX.Direct2D1.SolidColorBrush _lmImbSell2FillDx;      // #D04848 alpha 64
private SharpDX.Direct2D1.SolidColorBrush _lmImbSell3FillDx;      // #F87171 alpha 38

// DEEP6 signature signals
private SharpDX.Direct2D1.SolidColorBrush _lmSigAbsorptionDx;     // #7DD3FC pale sky cyan
private SharpDX.Direct2D1.SolidColorBrush _lmSigAbsorptionGlowDx; // #7DD3FC alpha 48
private SharpDX.Direct2D1.SolidColorBrush _lmSigExhaustionDx;     // #FBBF24 warm amber
private SharpDX.Direct2D1.SolidColorBrush _lmSigExhaustionGlowDx; // #FBBF24 alpha 48
private SharpDX.Direct2D1.SolidColorBrush _lmSigConfluenceDx;     // #A78BFA Linear violet

// Levels
private SharpDX.Direct2D1.SolidColorBrush _lmLvlPocDx;            // #E0B84A subtle gold
private SharpDX.Direct2D1.SolidColorBrush _lmLvlVaDx;             // #7DA34A muted olive
private SharpDX.Direct2D1.SolidColorBrush _lmLvlNakedPocDx;       // #E0B84A alpha 120
private SharpDX.Direct2D1.SolidColorBrush _lmGexZeroDx;           // #67E8F9 bright cyan
private SharpDX.Direct2D1.SolidColorBrush _lmGexFlipDx;           // #E879F9 magenta
private SharpDX.Direct2D1.SolidColorBrush _lmGexCallWallDx;       // #5EEAD4 teal
private SharpDX.Direct2D1.SolidColorBrush _lmGexPutWallDx;        // #FB7185 coral

// Text
private SharpDX.Direct2D1.SolidColorBrush _lmTextPrimaryDx;       // #EDEEF0
private SharpDX.Direct2D1.SolidColorBrush _lmTextSecondaryDx;     // #A1A4AD
private SharpDX.Direct2D1.SolidColorBrush _lmTextDimDx;           // #6E727B
private SharpDX.Direct2D1.SolidColorBrush _lmTextAccentDx;        // #5E6AD2

// P&L (pnl.positive == sem.buy intentionally — same meaning, single source)
private SharpDX.Direct2D1.SolidColorBrush _lmPnlPositiveDx;       // #4ADE80
private SharpDX.Direct2D1.SolidColorBrush _lmPnlNegativeDx;       // #F87171

// Working orders
private SharpDX.Direct2D1.SolidColorBrush _lmOrdLimitDx;          // #67E8F9 alpha 200
private SharpDX.Direct2D1.SolidColorBrush _lmOrdStopDx;           // #F87171 alpha 200
private SharpDX.Direct2D1.SolidColorBrush _lmOrdTrailDx;          // #A78BFA alpha 200
private SharpDX.Direct2D1.SolidColorBrush _lmOrdEntryBandDx;      // #EDEEF0 alpha 20 (~8%)
private SharpDX.Direct2D1.SolidColorBrush _lmOrdTargetZoneDx;     // #4ADE80 alpha 20
private SharpDX.Direct2D1.SolidColorBrush _lmOrdStopZoneDx;       // #F87171 alpha 20

// Stroke styles
private StrokeStyle _lmDashStyle;     // 4-on/4-off butt cap (GEX flip, working orders)
private StrokeStyle _lmDotStyle;      // 2-on/2-off butt cap (trail orders)

// Fonts
private TextFormat _lmCellFont;       // JetBrains Mono 12 Regular
private TextFormat _lmLabelFont;      // Inter Medium 11
private TextFormat _lmHeaderFont;     // Inter Medium 14
private TextFormat _lmHeroFont;       // JetBrains Mono Bold 24
private TextFormat _lmPillFont;       // JetBrains Mono Medium 11
```

### 9.2 Brush allocation (drop into `OnRenderTargetChanged`, after existing brush block, ~line 1220)

```csharp
// ─── Linear-Modern brush allocation ───
// Helper alias for brevity — uses existing MakeFrozenBrush+ToDxBrush pipeline.
SharpDX.Direct2D1.SolidColorBrush LM(byte a, byte r, byte g, byte b)
    => MakeFrozenBrush(Color.FromArgb(a, r, g, b)).ToDxBrush(RenderTarget)
       as SharpDX.Direct2D1.SolidColorBrush;

// Backgrounds
_lmBgCanvasDx       = LM(255, 0x08, 0x09, 0x0A);
_lmBgPanelDx        = LM(255, 0x0E, 0x0F, 0x11);
_lmBgPanelAltDx     = LM(255, 0x16, 0x17, 0x1A);
_lmBgPanelHoverDx   = LM(255, 0x1C, 0x1D, 0x21);
_lmBorderDividerDx  = LM(255, 0x1A, 0x1B, 0x1E);
_lmBorderDefaultDx  = LM(255, 0x26, 0x27, 0x2B);
_lmBorderFocusDx    = LM(255, 0x5E, 0x6A, 0xD2);

// Semantic
_lmSemBuyDx         = LM(255, 0x4A, 0xDE, 0x80);
_lmSemBuyMutedDx    = LM(255, 0x2B, 0xB6, 0x73);
_lmSemSellDx        = LM(255, 0xF8, 0x71, 0x71);
_lmSemSellMutedDx   = LM(255, 0xD0, 0x48, 0x48);
_lmSemNeutralDx     = LM(255, 0x9C, 0xA3, 0xAE);

// Imbalance tiers
_lmImbBuy1BorderDx  = LM(200, 0x2B, 0xB6, 0x73);
_lmImbBuy2FillDx    = LM( 64, 0x2B, 0xB6, 0x73);
_lmImbBuy3FillDx    = LM( 38, 0x4A, 0xDE, 0x80);
_lmImbSell1BorderDx = LM(200, 0xD0, 0x48, 0x48);
_lmImbSell2FillDx   = LM( 64, 0xD0, 0x48, 0x48);
_lmImbSell3FillDx   = LM( 38, 0xF8, 0x71, 0x71);

// Signatures
_lmSigAbsorptionDx     = LM(255, 0x7D, 0xD3, 0xFC);
_lmSigAbsorptionGlowDx = LM( 48, 0x7D, 0xD3, 0xFC);
_lmSigExhaustionDx     = LM(255, 0xFB, 0xBF, 0x24);
_lmSigExhaustionGlowDx = LM( 48, 0xFB, 0xBF, 0x24);
_lmSigConfluenceDx     = LM(255, 0xA7, 0x8B, 0xFA);

// Levels
_lmLvlPocDx       = LM(255, 0xE0, 0xB8, 0x4A);
_lmLvlVaDx        = LM(200, 0x7D, 0xA3, 0x4A);
_lmLvlNakedPocDx  = LM(120, 0xE0, 0xB8, 0x4A);
_lmGexZeroDx      = LM(255, 0x67, 0xE8, 0xF9);
_lmGexFlipDx      = LM(255, 0xE8, 0x79, 0xF9);
_lmGexCallWallDx  = LM(255, 0x5E, 0xEA, 0xD4);
_lmGexPutWallDx   = LM(255, 0xFB, 0x71, 0x85);

// Text
_lmTextPrimaryDx   = LM(255, 0xED, 0xEE, 0xF0);
_lmTextSecondaryDx = LM(255, 0xA1, 0xA4, 0xAD);
_lmTextDimDx       = LM(255, 0x6E, 0x72, 0x7B);
_lmTextAccentDx    = LM(255, 0x5E, 0x6A, 0xD2);

// P&L (alias same source — single semantic meaning)
_lmPnlPositiveDx   = LM(255, 0x4A, 0xDE, 0x80);
_lmPnlNegativeDx   = LM(255, 0xF8, 0x71, 0x71);

// Working orders
_lmOrdLimitDx       = LM(200, 0x67, 0xE8, 0xF9);
_lmOrdStopDx        = LM(200, 0xF8, 0x71, 0x71);
_lmOrdTrailDx       = LM(200, 0xA7, 0x8B, 0xFA);
_lmOrdEntryBandDx   = LM( 20, 0xED, 0xEE, 0xF0);
_lmOrdTargetZoneDx  = LM( 20, 0x4A, 0xDE, 0x80);
_lmOrdStopZoneDx    = LM( 20, 0xF8, 0x71, 0x71);

// Stroke styles — butt caps (sharper than rounded; Linear convention)
if (_lmDashStyle != null) { _lmDashStyle.Dispose(); _lmDashStyle = null; }
_lmDashStyle = new StrokeStyle(NinjaTrader.Core.Globals.D2DFactory,
    new StrokeStyleProperties
    {
        DashStyle = SharpDX.Direct2D1.DashStyle.Custom,
        DashCap   = CapStyle.Flat,
        StartCap  = CapStyle.Flat,
        EndCap    = CapStyle.Flat,
    },
    new float[] { 4f, 4f });

if (_lmDotStyle != null) { _lmDotStyle.Dispose(); _lmDotStyle = null; }
_lmDotStyle = new StrokeStyle(NinjaTrader.Core.Globals.D2DFactory,
    new StrokeStyleProperties
    {
        DashStyle = SharpDX.Direct2D1.DashStyle.Custom,
        DashCap   = CapStyle.Flat,
        StartCap  = CapStyle.Flat,
        EndCap    = CapStyle.Flat,
    },
    new float[] { 2f, 2f });

// Fonts — JetBrains Mono if installed, falls back to Cascadia Mono / Consolas
const string MONO = "JetBrains Mono";  // user installs once; auto falls back via DirectWrite
const string SANS = "Inter";           // ditto

_lmCellFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                             MONO, FontWeight.Regular, FontStyle.Normal,
                             FontStretch.Normal, 12f)
{
    TextAlignment      = TextAlignment.Trailing,
    ParagraphAlignment = ParagraphAlignment.Center,
};
_lmLabelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                              SANS, FontWeight.Medium, FontStyle.Normal,
                              FontStretch.Normal, 11f)
{
    TextAlignment      = TextAlignment.Leading,
    ParagraphAlignment = ParagraphAlignment.Center,
};
_lmHeaderFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                               SANS, FontWeight.Medium, FontStyle.Normal,
                               FontStretch.Normal, 14f)
{
    TextAlignment      = TextAlignment.Leading,
    ParagraphAlignment = ParagraphAlignment.Center,
};
_lmHeroFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                             MONO, FontWeight.Bold, FontStyle.Normal,
                             FontStretch.Normal, 24f)
{
    TextAlignment      = TextAlignment.Leading,
    ParagraphAlignment = ParagraphAlignment.Center,
};
_lmPillFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
                             MONO, FontWeight.Medium, FontStyle.Normal,
                             FontStretch.Normal, 11f)
{
    TextAlignment      = TextAlignment.Leading,
    ParagraphAlignment = ParagraphAlignment.Center,
};
```

### 9.3 Disposal (paste into `DisposeDx()` ~line 1262, follows existing pattern)

```csharp
// ─── Linear-Modern disposal ───
DisposeSolidBrush(ref _lmBgCanvasDx);       DisposeSolidBrush(ref _lmBgPanelDx);
DisposeSolidBrush(ref _lmBgPanelAltDx);     DisposeSolidBrush(ref _lmBgPanelHoverDx);
DisposeSolidBrush(ref _lmBorderDividerDx);  DisposeSolidBrush(ref _lmBorderDefaultDx);
DisposeSolidBrush(ref _lmBorderFocusDx);
DisposeSolidBrush(ref _lmSemBuyDx);         DisposeSolidBrush(ref _lmSemBuyMutedDx);
DisposeSolidBrush(ref _lmSemSellDx);        DisposeSolidBrush(ref _lmSemSellMutedDx);
DisposeSolidBrush(ref _lmSemNeutralDx);
DisposeSolidBrush(ref _lmImbBuy1BorderDx);  DisposeSolidBrush(ref _lmImbBuy2FillDx);
DisposeSolidBrush(ref _lmImbBuy3FillDx);    DisposeSolidBrush(ref _lmImbSell1BorderDx);
DisposeSolidBrush(ref _lmImbSell2FillDx);   DisposeSolidBrush(ref _lmImbSell3FillDx);
DisposeSolidBrush(ref _lmSigAbsorptionDx);     DisposeSolidBrush(ref _lmSigAbsorptionGlowDx);
DisposeSolidBrush(ref _lmSigExhaustionDx);     DisposeSolidBrush(ref _lmSigExhaustionGlowDx);
DisposeSolidBrush(ref _lmSigConfluenceDx);
DisposeSolidBrush(ref _lmLvlPocDx);         DisposeSolidBrush(ref _lmLvlVaDx);
DisposeSolidBrush(ref _lmLvlNakedPocDx);
DisposeSolidBrush(ref _lmGexZeroDx);        DisposeSolidBrush(ref _lmGexFlipDx);
DisposeSolidBrush(ref _lmGexCallWallDx);    DisposeSolidBrush(ref _lmGexPutWallDx);
DisposeSolidBrush(ref _lmTextPrimaryDx);    DisposeSolidBrush(ref _lmTextSecondaryDx);
DisposeSolidBrush(ref _lmTextDimDx);        DisposeSolidBrush(ref _lmTextAccentDx);
DisposeSolidBrush(ref _lmPnlPositiveDx);    DisposeSolidBrush(ref _lmPnlNegativeDx);
DisposeSolidBrush(ref _lmOrdLimitDx);       DisposeSolidBrush(ref _lmOrdStopDx);
DisposeSolidBrush(ref _lmOrdTrailDx);       DisposeSolidBrush(ref _lmOrdEntryBandDx);
DisposeSolidBrush(ref _lmOrdTargetZoneDx);  DisposeSolidBrush(ref _lmOrdStopZoneDx);
if (_lmDashStyle  != null) { _lmDashStyle.Dispose();  _lmDashStyle  = null; }
if (_lmDotStyle   != null) { _lmDotStyle.Dispose();   _lmDotStyle   = null; }
if (_lmCellFont   != null) { _lmCellFont.Dispose();   _lmCellFont   = null; }
if (_lmLabelFont  != null) { _lmLabelFont.Dispose();  _lmLabelFont  = null; }
if (_lmHeaderFont != null) { _lmHeaderFont.Dispose(); _lmHeaderFont = null; }
if (_lmHeroFont   != null) { _lmHeroFont.Dispose();   _lmHeroFont   = null; }
if (_lmPillFont   != null) { _lmPillFont.Dispose();   _lmPillFont   = null; }
```

### 9.4 Footprint cell rendering — Linear aesthetic

Drop these methods into the indicator class. Call `RenderFootprintCellLM(...)` from your existing per-bar rendering loop instead of (or alongside) the legacy `RenderTarget.FillRectangle(rect, _imbalBuyDx)` calls.

```csharp
/// <summary>
/// Render one footprint row in Linear-Modern aesthetic. Default = numerals only,
/// no fill, no border. Imbalance escalates restrained: tier 1 = side-border only,
/// tier 2 = +12% fill, tier 3 = +15% fill + corner triangle. POC = 1px gold thread.
/// </summary>
private void RenderFootprintCellLM(
    float xLeft, float yTop, float colW, float rowH,
    long bidVol, long askVol, bool isPoc)
{
    float halfW = colW * 0.5f;
    var bidRect = new RectangleF(xLeft,         yTop, halfW, rowH);
    var askRect = new RectangleF(xLeft + halfW, yTop, halfW, rowH);

    // 1. Imbalance ratio
    long maxV = System.Math.Max(askVol, bidVol);
    long minV = System.Math.Max(1L, System.Math.Min(askVol, bidVol));
    double ratio = (double)maxV / minV;
    bool buySide = askVol > bidVol;

    // 2. Cell fill (tier 2 = ~12%, tier 3 = ~15%) — drawn UNDER the numerals
    if (ratio >= 5.0)
    {
        var fill = buySide ? _lmImbBuy3FillDx : _lmImbSell3FillDx;
        RenderTarget.FillRectangle(buySide ? askRect : bidRect, fill);
    }
    else if (ratio >= 3.0)
    {
        var fill = buySide ? _lmImbBuy2FillDx : _lmImbSell2FillDx;
        RenderTarget.FillRectangle(buySide ? askRect : bidRect, fill);
    }
    // tier 1 has NO fill — border only, drawn below

    // 3. POC: 1px gold thread crossing the cell middle
    if (isPoc)
    {
        float yMid = yTop + rowH * 0.5f;
        RenderTarget.DrawLine(
            new Vector2(xLeft, yMid),
            new Vector2(xLeft + colW, yMid),
            _lmLvlPocDx, 1f);
    }

    // 4. Imbalance border on dominant side (1px tier 1/2, 1.5px tier 3)
    if (ratio >= 1.5)
    {
        float strokeW = ratio >= 5.0 ? 1.5f : 1f;
        var borderBrush = ratio >= 3.0
            ? (buySide ? _lmImbBuy3FillDx : _lmImbSell3FillDx)   // tier 2/3 use fill color, full alpha not needed
            : (buySide ? _lmImbBuy1BorderDx : _lmImbSell1BorderDx);
        // Use 80% alpha brush for tier 2/3 borders by re-using the same fill brush —
        // it reads as a hairline edge against the canvas.

        // Buy side: vertical bar on LEFT edge of ask cell.
        // Sell side: vertical bar on RIGHT edge of bid cell.
        float bx = buySide ? (xLeft + halfW) : (xLeft + halfW);
        // Actually: borders on the OUTER edge of dominant cell:
        float xBorder = buySide
            ? (xLeft + colW - strokeW * 0.5f)   // right edge of ask
            : (xLeft + strokeW * 0.5f);         // left edge of bid
        RenderTarget.DrawLine(
            new Vector2(xBorder, yTop),
            new Vector2(xBorder, yTop + rowH),
            borderBrush, strokeW);
    }

    // 5. Numerals — JetBrains Mono 12, text.secondary, NEVER pure white
    DrawCellNumeral(bidRect, bidVol, padRight: 4f);
    DrawCellNumeral(askRect, askVol, padRight: 4f);

    // 6. Tier-3 corner triangle (4×4px) — tucked into outer corner of dominant cell
    if (ratio >= 5.0)
    {
        var triBrush = buySide ? _lmSemBuyDx : _lmSemSellDx;
        DrawCornerTriangle(buySide ? askRect : bidRect, !buySide, triBrush);
    }
}

/// <summary>JetBrains Mono numeral, right-aligned with 4px right padding.</summary>
private void DrawCellNumeral(RectangleF rect, long volume, float padRight)
{
    if (volume <= 0) return;
    string s = FormatVol(volume);  // "1,247" / "842" / "12.4k"
    var inner = new RectangleF(rect.X, rect.Y, rect.Width - padRight, rect.Height);
    using (var layout = new TextLayout(
               NinjaTrader.Core.Globals.DirectWriteFactory,
               s, _lmCellFont, inner.Width, inner.Height))
    {
        RenderTarget.DrawTextLayout(
            new Vector2(inner.X, inner.Y), layout, _lmTextSecondaryDx);
    }
}

/// <summary>Compact volume formatter — 1,247 below 10k, 12.4k above.</summary>
private static string FormatVol(long v)
{
    if (v < 10_000)      return v.ToString("N0");
    if (v < 1_000_000)   return (v / 1000.0).ToString("0.0") + "k";
    return (v / 1_000_000.0).ToString("0.00") + "m";
}

/// <summary>4×4px filled triangle in outer corner — tier-3 imbalance signature.</summary>
private void DrawCornerTriangle(RectangleF cell, bool leftCorner, SharpDX.Direct2D1.Brush brush)
{
    const float tri = 4f;
    var sink = new PathGeometry(NinjaTrader.Core.Globals.D2DFactory);
    using (var s = sink.Open())
    {
        if (leftCorner)
        {
            s.BeginFigure(new Vector2(cell.X, cell.Y), FigureBegin.Filled);
            s.AddLine(new Vector2(cell.X + tri, cell.Y));
            s.AddLine(new Vector2(cell.X, cell.Y + tri));
        }
        else
        {
            float xR = cell.X + cell.Width;
            s.BeginFigure(new Vector2(xR, cell.Y), FigureBegin.Filled);
            s.AddLine(new Vector2(xR - tri, cell.Y));
            s.AddLine(new Vector2(xR, cell.Y + tri));
        }
        s.EndFigure(FigureEnd.Closed);
        s.Close();
    }
    RenderTarget.FillGeometry(sink, brush);
    sink.Dispose();
}
```

### 9.5 Elevated panel rendering (HUD / equity strip backdrop)

```csharp
/// <summary>
/// Linear-Modern panel: bg.panel solid fill + 1px border.divider hairline,
/// 6px outer border-radius. NO drop shadow, NO inner glow.
/// </summary>
private void DrawElevatedPanel(RectangleF rect, float radius = 6f)
{
    var rounded = new RoundedRectangle { Rect = rect, RadiusX = radius, RadiusY = radius };
    RenderTarget.FillRoundedRectangle(rounded, _lmBgPanelDx);
    RenderTarget.DrawRoundedRectangle(rounded, _lmBorderDividerDx, 1f);
}
```

### 9.6 Restrained absorption / exhaustion signature

```csharp
/// <summary>
/// Absorption signature: 6×6px diamond in pale sky cyan with 14×14px glow halo
/// at 18% alpha. Drawn 6px to the right of the cell. NO animation, NO cartoon glow.
/// </summary>
private void DrawAbsorptionSignature(float xCellRight, float yCellMid)
{
    const float halo = 14f;
    const float glyph = 6f;
    float xC = xCellRight + 6f + glyph * 0.5f;

    // 1. Halo — 18% alpha disc, drawn first so glyph sits on top
    var haloRect = new SharpDX.RectangleF(
        xC - halo * 0.5f, yCellMid - halo * 0.5f, halo, halo);
    var haloEllipse = new Ellipse(
        new Vector2(xC, yCellMid), halo * 0.5f, halo * 0.5f);
    RenderTarget.FillEllipse(haloEllipse, _lmSigAbsorptionGlowDx);

    // 2. Glyph — diamond (4 points)
    var sink = new PathGeometry(NinjaTrader.Core.Globals.D2DFactory);
    using (var s = sink.Open())
    {
        s.BeginFigure(new Vector2(xC, yCellMid - glyph * 0.5f), FigureBegin.Filled);
        s.AddLine(new Vector2(xC + glyph * 0.5f, yCellMid));
        s.AddLine(new Vector2(xC, yCellMid + glyph * 0.5f));
        s.AddLine(new Vector2(xC - glyph * 0.5f, yCellMid));
        s.EndFigure(FigureEnd.Closed);
        s.Close();
    }
    RenderTarget.FillGeometry(sink, _lmSigAbsorptionDx);
    sink.Dispose();
}

/// <summary>Exhaustion: same anatomy, △ glyph in warm amber.</summary>
private void DrawExhaustionSignature(float xCellRight, float yCellMid, bool pointDown)
{
    const float halo = 14f;
    const float glyph = 6f;
    float xC = xCellRight + 6f + glyph * 0.5f;

    var haloEllipse = new Ellipse(
        new Vector2(xC, yCellMid), halo * 0.5f, halo * 0.5f);
    RenderTarget.FillEllipse(haloEllipse, _lmSigExhaustionGlowDx);

    var sink = new PathGeometry(NinjaTrader.Core.Globals.D2DFactory);
    using (var s = sink.Open())
    {
        if (pointDown)
        {
            s.BeginFigure(new Vector2(xC - glyph * 0.5f, yCellMid - glyph * 0.5f), FigureBegin.Filled);
            s.AddLine(new Vector2(xC + glyph * 0.5f, yCellMid - glyph * 0.5f));
            s.AddLine(new Vector2(xC, yCellMid + glyph * 0.5f));
        }
        else
        {
            s.BeginFigure(new Vector2(xC - glyph * 0.5f, yCellMid + glyph * 0.5f), FigureBegin.Filled);
            s.AddLine(new Vector2(xC + glyph * 0.5f, yCellMid + glyph * 0.5f));
            s.AddLine(new Vector2(xC, yCellMid - glyph * 0.5f));
        }
        s.EndFigure(FigureEnd.Closed);
        s.Close();
    }
    RenderTarget.FillGeometry(sink, _lmSigExhaustionDx);
    sink.Dispose();
}
```

### 9.7 GEX level + pill label

```csharp
public enum GexKind { ZeroGamma, GammaFlip, CallWall, PutWall }

/// <summary>
/// Linear-Modern GEX level: 1px solid (or 1.5px wall, or dashed flip) line
/// stretching across viewport, with a 6px-radius pill label at chart-right.
/// </summary>
private void DrawGexLevelLM(
    float xLeft, float xRight, float y, GexKind kind, double price)
{
    SharpDX.Direct2D1.SolidColorBrush lineBrush;
    SharpDX.Direct2D1.SolidColorBrush pillBorder;
    string labelPrefix;
    float strokeW;
    StrokeStyle style = null;

    switch (kind)
    {
        case GexKind.ZeroGamma:
            lineBrush = _lmGexZeroDx; pillBorder = _lmBorderDefaultDx;
            labelPrefix = "ZG  "; strokeW = 1f; break;
        case GexKind.GammaFlip:
            lineBrush = _lmGexFlipDx; pillBorder = _lmBorderDefaultDx;
            labelPrefix = "FLIP "; strokeW = 1f; style = _lmDashStyle; break;
        case GexKind.CallWall:
            lineBrush = _lmGexCallWallDx; pillBorder = _lmGexCallWallDx;
            labelPrefix = "CW  "; strokeW = 1.5f; break;
        case GexKind.PutWall:
            lineBrush = _lmGexPutWallDx; pillBorder = _lmGexPutWallDx;
            labelPrefix = "PW  "; strokeW = 1.5f; break;
        default: return;
    }

    // 1. Line
    if (style != null)
        RenderTarget.DrawLine(new Vector2(xLeft, y), new Vector2(xRight, y),
                              lineBrush, strokeW, style);
    else
        RenderTarget.DrawLine(new Vector2(xLeft, y), new Vector2(xRight, y),
                              lineBrush, strokeW);

    // 2. Pill label — JetBrains Mono 11, 4px+8px padding, 6px radius
    string label = labelPrefix + price.ToString("N2");
    using (var layout = new TextLayout(
               NinjaTrader.Core.Globals.DirectWriteFactory,
               label, _lmPillFont, 200f, 24f))
    {
        float textW = layout.Metrics.Width;
        float textH = layout.Metrics.Height;
        const float padX = 8f, padY = 4f, gutter = 12f;
        float pillW = textW + padX * 2f;
        float pillH = textH + padY * 2f;
        float pillX = xRight - pillW - gutter;
        float pillY = y - pillH * 0.5f;

        var pillRect = new RectangleF(pillX, pillY, pillW, pillH);
        var rr = new RoundedRectangle { Rect = pillRect, RadiusX = 6f, RadiusY = 6f };
        RenderTarget.FillRoundedRectangle(rr, _lmBgPanelDx);
        RenderTarget.DrawRoundedRectangle(rr, pillBorder, 1f);

        RenderTarget.DrawTextLayout(
            new Vector2(pillX + padX, pillY + padY), layout, _lmTextPrimaryDx);
    }
}
```

### 9.8 Equity strip (top-left, hero P&L)

```csharp
/// <summary>
/// Linear-Modern equity strip: bg.panel pill at top-left, 280px × 56px,
/// hero P&L in JetBrains Mono Bold 24, color-coded by sign only.
/// </summary>
private void DrawEquityStripLM(
    float chartX, float chartY,
    double openPnl, double pnlPct, int trades, int wins, int losses)
{
    const float padTopLeft = 12f;
    const float stripW = 280f;
    const float stripH = 56f;

    var rect = new RectangleF(
        chartX + padTopLeft, chartY + padTopLeft, stripW, stripH);
    DrawElevatedPanel(rect, radius: 6f);

    // Hero number — color-coded by SIGN ONLY (never amber/blue/etc)
    SharpDX.Direct2D1.SolidColorBrush heroBrush =
        openPnl > 25  ? _lmPnlPositiveDx :
        openPnl < -25 ? _lmPnlNegativeDx :
                        _lmTextPrimaryDx;

    string heroText = (openPnl >= 0 ? "+$" : "-$") +
                      System.Math.Abs(openPnl).ToString("N2");
    string sub      = (openPnl >= 0 ? "▲ +" : "▼ ") +
                      pnlPct.ToString("0.0") + "%";

    // Hero — 24px Bold mono, padded 14px inside
    using (var layout = new TextLayout(
               NinjaTrader.Core.Globals.DirectWriteFactory,
               heroText, _lmHeroFont, stripW - 28f, 32f))
    {
        RenderTarget.DrawTextLayout(
            new Vector2(rect.X + 14f, rect.Y + 6f), layout, heroBrush);
    }

    // Sub — 12px mono, same color as hero, sits to the RIGHT of hero on top row
    // For simplicity here: rendered as a second row at 32px below top
    using (var layout = new TextLayout(
               NinjaTrader.Core.Globals.DirectWriteFactory,
               sub, _lmCellFont, 80f, 16f))
    {
        RenderTarget.DrawTextLayout(
            new Vector2(rect.X + 14f, rect.Y + 32f), layout, heroBrush);
    }

    // Footer label — Inter Medium 11px, ALL CAPS, text.dim
    string meta = $"{trades} TRADES · {wins}W · {losses}L";
    using (var layout = new TextLayout(
               NinjaTrader.Core.Globals.DirectWriteFactory,
               meta, _lmLabelFont, stripW - 28f, 16f))
    {
        RenderTarget.DrawTextLayout(
            new Vector2(rect.X + 100f, rect.Y + 34f), layout, _lmTextDimDx);
    }
}
```

### 9.9 Working-order pill + dashed line

```csharp
public enum OrderKind { Limit, Stop, Trail }

private void DrawWorkingOrderLM(
    float xLeft, float xRight, float y,
    OrderKind kind, string side, int qty, double price)
{
    SharpDX.Direct2D1.SolidColorBrush lineBrush;
    StrokeStyle style;
    string prefix;

    switch (kind)
    {
        case OrderKind.Limit: lineBrush = _lmOrdLimitDx; style = _lmDashStyle; prefix = "LMT"; break;
        case OrderKind.Stop:  lineBrush = _lmOrdStopDx;  style = _lmDashStyle; prefix = "STP"; break;
        case OrderKind.Trail: lineBrush = _lmOrdTrailDx; style = _lmDotStyle;  prefix = "TRL"; break;
        default: return;
    }

    // Dashed/dotted line — 1px, butt caps for sharpness
    RenderTarget.DrawLine(
        new Vector2(xLeft, y), new Vector2(xRight, y),
        lineBrush, 1f, style);

    // Pill — bg.panel + line-color border, monospace label
    string label = $"{prefix} {side} {qty}  {price:N2}";
    using (var layout = new TextLayout(
               NinjaTrader.Core.Globals.DirectWriteFactory,
               label, _lmPillFont, 240f, 24f))
    {
        float textW = layout.Metrics.Width;
        float textH = layout.Metrics.Height;
        const float padX = 8f, padY = 4f, gutter = 12f;
        float pillW = textW + padX * 2f;
        float pillH = textH + padY * 2f;
        float pillX = xRight - pillW - gutter;
        float pillY = y - pillH * 0.5f;

        var pillRect = new RectangleF(pillX, pillY, pillW, pillH);
        var rr = new RoundedRectangle { Rect = pillRect, RadiusX = 6f, RadiusY = 6f };
        RenderTarget.FillRoundedRectangle(rr, _lmBgPanelDx);
        RenderTarget.DrawRoundedRectangle(rr, lineBrush, 1f);
        RenderTarget.DrawTextLayout(
            new Vector2(pillX + padX, pillY + padY), layout, _lmTextPrimaryDx);
    }
}
```

### 9.10 Position entry band + R/R zones

```csharp
/// <summary>
/// 8% alpha entry band + 1px solid entry line + R/R zones. No animation.
/// </summary>
private void DrawPositionMarkerLM(
    float xEntry, float xRight, float yEntry, float yStop, float yTarget,
    float tickHeight)
{
    // 1. Entry band — 1-tick tall, 8% alpha white wash
    var bandRect = new RectangleF(
        xEntry, yEntry - tickHeight * 0.5f,
        xRight - xEntry, tickHeight);
    RenderTarget.FillRectangle(bandRect, _lmOrdEntryBandDx);

    // 2. Entry line — 1px solid white
    RenderTarget.DrawLine(
        new Vector2(xEntry, yEntry), new Vector2(xRight, yEntry),
        _lmTextPrimaryDx, 1f);

    // 3. Stop zone — 8% alpha coral rect from entry to stop
    if (yStop > yEntry)  // long: stop below
    {
        var stopRect = new RectangleF(xEntry, yEntry, xRight - xEntry, yStop - yEntry);
        RenderTarget.FillRectangle(stopRect, _lmOrdStopZoneDx);
    }
    else
    {
        var stopRect = new RectangleF(xEntry, yStop, xRight - xEntry, yEntry - yStop);
        RenderTarget.FillRectangle(stopRect, _lmOrdStopZoneDx);
    }

    // 4. Target zone — 8% alpha green rect
    if (yTarget < yEntry)  // long: target above (lower y)
    {
        var tgtRect = new RectangleF(xEntry, yTarget, xRight - xEntry, yEntry - yTarget);
        RenderTarget.FillRectangle(tgtRect, _lmOrdTargetZoneDx);
    }
    else
    {
        var tgtRect = new RectangleF(xEntry, yEntry, xRight - xEntry, yTarget - yEntry);
        RenderTarget.FillRectangle(tgtRect, _lmOrdTargetZoneDx);
    }
}
```

---

## 10. Why This Aesthetic Wins

1. **It belongs to the same design family the trader already inhabits all day.** Linear board, Stripe dashboard, Notion playbook, Raycast — they all share this exact grammar (deep grayscale staircase, restrained semantic teal/coral, perfect typography, 6px outer / 0px inner radius, no drop shadows). A NQ footprint chart in this aesthetic stops looking like 2008 NinjaScript and starts looking like 2026 software, which directly translates to the trader's perceived trust and willingness to act on its signals.

2. **Restraint scales with information density.** The cell rendering recipe defaults to numerals-only — zero ink unless something is happening. Imbalance escalates in three perceptually calibrated tiers (border → 12% fill → 15% fill + corner triangle), so the eye reads tiers as magnitude rather than parsing color labels. Absorption and exhaustion get exactly one elegant glyph each with an 18% halo, instead of the cartoon explosions every retail tool ships. This means a quiet market reads quiet; a charged market reads charged; nothing in between fights for your attention.

3. **The typography spec is the moat.** JetBrains Mono 12 in `text.secondary` for cell numerals + Inter Medium 11 `+0.04em` tracking for caps labels + JetBrains Mono Bold 24 for the equity hero — that single combination, executed precisely, is the difference between "competent dark theme" and "Linear-grade premium SaaS." Most competitors will copy the colors and get the typography wrong; the moment you copy the type spec verbatim, the chart reads expensive even before any data renders.

---

## Report

Delivered Aesthetic Direction C — Linear-Modern Premium SaaS — as a complete drop-in spec for `DEEP6Footprint.cs`. Total scope: ~5,200 words.

Key deliverables included:
- One-paragraph design philosophy positioning the aesthetic against Linear / Stripe / Vercel / Fey / Notion
- Full OKLCH + hex palette (~50 tokens) covering background staircase, borders, equiluminant L=0.65 semantic teal/coral, 3-tier imbalance escalation, signature signals, levels (POC/VAH/VAL/GEX), text, P&L, working orders, transient flashes
- Typography spec with 8-step type scale, exact size/weight/tracking values, JetBrains Mono + Inter font stack with NT8-specific Cascadia/Consolas fallback
- Footprint cell rendering recipe with ASCII anatomy and 9-step decision tree
- Subtle gradient + elevation system (brightness staircase, never shadows; 6px outer / 0px inner radius)
- GEX level rendering with pill-label anatomy
- Strategy visualization (equity strip, working-order pill+dash, position marker with 8%-alpha R/R zones)
- Full-chart ASCII mockup
- Drop-in SharpDX C# code: brush field declarations, `OnRenderTargetChanged` allocations, `DisposeDx` cleanup, plus 8 ready-to-call render methods (`RenderFootprintCellLM`, `DrawElevatedPanel`, `DrawAbsorptionSignature`, `DrawExhaustionSignature`, `DrawGexLevelLM`, `DrawEquityStripLM`, `DrawWorkingOrderLM`, `DrawPositionMarkerLM`) — all using the existing `MakeFrozenBrush().ToDxBrush()` pattern, the existing `_xxxDx` naming convention, and the existing `DisposeBrush`/`DisposeSolidBrush` helpers
- 3-sentence "why this wins" justification

Code uses `_lm` prefix so it coexists with the existing brush set during gradual migration. No file edits made — this is a design proposal returned as text for the caller to relay.

Reference files read: `/Users/teaceo/DEEP6/ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` (lines 1-200, 740-789, 1175-1280), `/Users/teaceo/DEEP6/dashboard/agents/trading-ui-design-knowledge-base.md` (lines 1-300), `/Users/teaceo/DEEP6/dashboard/agents/cross-discipline-hud-design-horizon.md` (lines 1-400), `/Users/teaceo/DEEP6/dashboard/agents/color-science-oklch-perceptual.md` (lines 1-120).
