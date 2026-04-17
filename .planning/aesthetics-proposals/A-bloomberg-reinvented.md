I have a clear picture of the existing code patterns. The Footprint indicator already uses `Consolas` for cells, `Segoe UI` for labels, the `MakeFrozenBrush(...).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush` pattern, and disposes via `DisposeSolidBrush`. My code drops will use exactly these patterns.

I have everything needed. Let me deliver the complete design proposal.

---

# DEEP6 — Aesthetic Direction A: "Bloomberg Terminal Reinvented"

## 1. Design Philosophy

The Bloomberg Terminal is the only piece of trading software whose users defend its 1980s aesthetic with religious fervor — because amber-on-black isn't a style choice, it's a **trust signal**. Every other piece of software on a serious trader's desk is fashion; Bloomberg is permanence. This direction takes that gravitas and modernizes it with three borrowed disciplines: (1) the **Boeing 787 glass-cockpit color caste system** — cyan = selected, magenta = automatic mode active, amber = caution requiring attention, red = warning requiring action, green = engaged & nominal, white = primary data; (2) **NASA mission control restraint** — one font, semantic color only, zero ornament; (3) **HP-HMI / SCADA grayscale-base + color-only-for-alarm** — a chart at rest reads in white, gray, and amber, and color erupts only when the market is doing something. The trader who runs DEEP6 in this skin sits down at a screen that signals the same thing a Bloomberg sit-down signals: **"the person at this terminal is paid to be right."** It is for the trader who manages prop capital, runs a desk, or wants their EOD screenshots to be indistinguishable from an institutional turret.

---

## 2. Complete Color Palette (Verified Hex)

### Surfaces & Chrome

| Token | Hex | Alpha | Use |
|---|---|---|---|
| `bg.terminal` | `#000000` | 1.00 | Main chart background. True black, Bloomberg-canonical. |
| `bg.panel` | `#0A0A0A` | 1.00 | HUD/panel inset (one shade lifted so panels read as separate). |
| `bg.row.zebra` | `#0E0E0E` | 1.00 | Optional alternating row tint in tables/footprint header strip. |
| `grid.major` | `#1F1F1F` | 1.00 | Major grid (every 5th tick / hourly). |
| `grid.minor` | `#141414` | 1.00 | Minor grid (every tick / 10-min). |
| `axis.line` | `#2A2A2A` | 1.00 | Axis spine. |
| `divider` | `#262626` | 1.00 | 1-px separator between chrome regions. |
| `crosshair` | `#FFF799` | 0.55 | Bloomberg pale-yellow highlight, 1 px dashed `[2,2]`. |

### Primary Semantic (Aircraft-Grade Caste System)

| Token | Hex | Caste meaning |
|---|---|---|
| `data.primary` | `#FB8B1E` | **AMBER — primary data, neutral.** Default text, OHLC numerals, prices, volumes when no other state applies. |
| `data.secondary` | `#D7D7D7` | White-secondary. Labels, axes, headers. |
| `data.dim` | `#7A7A7A` | Tertiary text — separators, units, footers. |
| `data.faint` | `#3F3F3F` | Watermark, disabled. |
| `state.selected` | `#4DC7F9` | **CYAN — active/selected/cursor.** 787 glass-cockpit convention. Crosshair price tag, current bar outline, hovered cell. |
| `state.auto` | `#A965F0` | **MAGENTA-VIOLET — autopilot engaged.** Strategy is in auto-execute mode; working orders live. |
| `state.engaged` | `#5DC453` | **GREEN — engaged & nominal.** Position open and in profit, system healthy. |
| `state.caution` | `#FFC107` | **AMBER-CAUTION — attention but not action.** Drawdown approaching, near R-cap. |
| `state.warning` | `#D54135` | **RED — warning, action.** Stop hit, MaxLossBreaker tripped, disconnect. |

### Buy / Sell / Neutral (Footprint Cells)

| Token | Hex | Use |
|---|---|---|
| `flow.buy` | `#5DC453` | Bloomberg green — ask-side fills, buy-aggressor. |
| `flow.sell` | `#D54135` | Bloomberg red — bid-side fills, sell-aggressor. |
| `flow.neutral` | `#7A7A7A` | Mid-spread / unclassified. |
| `flow.buy.dim` | `#2D5F2A` | 4-tier saturation step 1 (low volume buy). |
| `flow.sell.dim` | `#5F221F` | 4-tier saturation step 1 (low volume sell). |

### Imbalance Tier Escalation (1×/2×/3×/4×)

| Tier | Threshold | Buy fill | Sell fill | Border |
|---|---|---|---|---|
| 1× weak | ≥ 150% | `#5DC453` text only, regular weight | `#D54135` text only, regular weight | none |
| 2× medium | ≥ 250% | `#5DC453` bold + `#5DC453` 1 px border | `#D54135` bold + `#D54135` 1 px border | 1 px |
| 3× strong | ≥ 300% | `#4DC7F9` bold (cyan!) + 2 px border + `#4DC7F9` flood @ 18% | `#FF5BB8` bold (magenta!) + 2 px border + flood @ 18% | 2 px |
| 4× extreme | ≥ 400% | tier 3 + outer halo `#4DC7F9` 4 px @ 30% + 1 frame flash `#FFFFFF` | tier 3 + halo `#FF5BB8` 4 px @ 30% + flash | 2 px + halo |

The 1×/2× tier stays in red/green so it reads "expected market behavior." The 3×/4× tier jumps to cyan/magenta — the colors deliberately not used anywhere else in the chart — so a stacked imbalance is **physically impossible to miss on a populated screen**. This is the same reason Boeing reserves cyan for "you are here" and magenta for "the autopilot is doing this": those colors never appear in the ambient field.

### DEEP6 Signature Signals

| Token | Hex | Use |
|---|---|---|
| `sig.absorption` | `#4DC7F9` | Cyan — DEEP6's flagship absorption signature. Pulse halo on the absorbing cell. |
| `sig.exhaustion` | `#FF5BB8` | Magenta — exhaustion signature. Comet-tail gradient into the wick. |
| `sig.confluence` | `#FFF799` | Pale yellow (Bloomberg highlight) — when absorption + exhaustion + GEX confluence stack. |
| `sig.confidence.top` | `#FFFFFF` | White, glow-bordered. Reserved exclusively for top-decile DEEP6 score (≥ 85). One thing on the screen at a time. |

### Levels

| Token | Hex | Style |
|---|---|---|
| `level.poc` | `#FB8B1E` | Amber, 2 px solid horizontal, full-bar width. |
| `level.vah` | `#D7D7D7` | White-secondary, 1 px dotted `[2,3]`. |
| `level.val` | `#D7D7D7` | White-secondary, 1 px dotted `[2,3]`. |
| `level.va.fill` | `#FB8B1E` @ 6% | Subtle amber band between VAH/VAL. |
| `level.naked.poc` | `#FB8B1E` @ 50% | Faded amber, 1.5 px dashed `[6,4]` extending right until touched. |
| `level.pdh.pdl` | `#A965F0` | Magenta-violet — prior day high/low (autopilot color = "yesterday's auto-completion"). |
| `level.gex.zerogamma` | `#FFF799` | Pale yellow, 2 px solid, label `Γ⁰`. The single most important options line. |
| `level.gex.flip` | `#FFC107` | Amber-caution, 1.5 px dash-dot. |
| `level.gex.callwall` | `#5DC453` | Green wall, 1 px solid + label `CW \| +Γ`. |
| `level.gex.putwall` | `#D54135` | Red wall, 1 px solid + label `PW \| -Γ`. |
| `level.gex.voltrigger` | `#FB8B1E` | Amber, 1 px dashed. |
| `level.gex.vanna` | `#4DC7F9` @ 60% | Cyan, 1 px dotted, label `V` — vanna exposure flip. |
| `level.gex.charm` | `#A965F0` @ 60% | Magenta-violet, 1 px dotted, label `C` — charm decay. |

### Strategy P&L States

| Token | Hex | Trigger |
|---|---|---|
| `pnl.flat` | `#7A7A7A` | No position. |
| `pnl.long.green` | `#5DC453` | Long, in profit. |
| `pnl.long.red` | `#D54135` | Long, in loss. |
| `pnl.short.green` | `#5DC453` | Short, in profit. |
| `pnl.short.red` | `#D54135` | Short, in loss. |
| `pnl.warning` | `#FFC107` | Within 25% of stop. |
| `pnl.critical` | `#D54135` | Stop within 5 ticks; flash. |

### Working Order States

| Token | Hex | Style |
|---|---|---|
| `order.limit` | `#A965F0` | Magenta-violet (autopilot color), 1.5 px solid, label `LMT 2 @ ...`. |
| `order.stop` | `#FFC107` | Amber-caution, 1.5 px dashed `[6,3]`, label `STP 2 @ ...`. |
| `order.trail` | `#FB8B1E` | Amber, 1 px dot-dash, repositioned per tick — label `TRL`. |
| `order.target` | `#5DC453` | Green, 1.5 px dotted, label `TGT 2 @ ...`. |
| `order.bracket.shade` | gradient `#A965F0` 8% → 0% | Faint vertical band from entry to current price. |

### Transient Flashes

| Token | Hex | Decay |
|---|---|---|
| `flash.fill` | `#4DC7F9` | 400 ms cyan flash on cell where fill happened. |
| `flash.pull` | `#FFF799` | 200 ms pale-yellow flash on price level where size was pulled. |
| `flash.bigorder` | `#FB8B1E` | 1 Hz pulse for 3 cycles when order ≥ 200 contracts arrives. |
| `flash.alert` | `#D54135` | 1-frame full-chart border flash on hard alert (stop hit, disconnect). |
| `flash.absorption` | `#4DC7F9` | 1.2 s pulse 3 cycles on detected absorption cell. |
| `flash.confidence` | `#FFFFFF` | 1-frame 2 px chart border flash when score crosses ≥ 85. |

---

## 3. Typography Spec

**One typeface family for chrome (sans), one for data (mono). Period.** Bloomberg uses one font for everything; we soften that by using its modern descendants — IBM Plex Mono and Inter — which are the closest open-source equivalents to Bloomberg's proprietary Trade Sans / Trade Sans Mono.

| Role | Font | Size | Weight | Tracking | Notes |
|---|---|---|---|---|---|
| **Cell numerals** | `IBM Plex Mono` → `Consolas` → `JetBrains Mono` → `Menlo` | **10 px** (auto-min 7, auto-max 13) | `400` regular | `0` | Tabular by default. NEVER Arial. |
| **Cell numerals — imbalance tier 2+** | same | same | `600` semibold | `0` | Same metrics, heavier weight. |
| **Bar header strip (per-bar Δ/V/Imb)** | `IBM Plex Mono` → `Consolas` | **9 px** | `400` | `0` | Dim color (`#7A7A7A`). |
| **Axis labels (price, time)** | `IBM Plex Mono` → `Consolas` | **10 px** | `400` | `0` | `#D7D7D7`. |
| **Crosshair price tag** | `IBM Plex Mono` → `Consolas` | **11 px** | `600` | `0` | Cyan (`#4DC7F9`) on `#000000` filled rect. |
| **Chrome labels (legend, button text, panel titles)** | `Inter` → `Segoe UI` → `Helvetica Neue` | **11 px** | `500` medium | `+10/1000` | Slight tracking, all-caps for headers. |
| **Section headers (HUD region labels)** | `Inter` → `Segoe UI` | **10 px** | `600` semibold | `+80/1000` ALL-CAPS | Bloomberg "FUNCTION" header style. |
| **Hero KPI (P&L, score)** | `IBM Plex Mono` → `Consolas` | **22 px** | `300` light | `0` | Light weight makes the number read as architectural. |
| **Hero KPI sublabel** | `Inter` → `Segoe UI` | **9 px** | `500` ALL-CAPS | `+80/1000` | Above the hero number, dim. |
| **Tape/T&S row** | `IBM Plex Mono` → `Consolas` | **10 px** | `400` (`600` on size-tier escalation) | `0` | |
| **Watermark (symbol behind chart)** | `Inter` → `Segoe UI` | **120 px** | `200` thin | `+200/1000` ALL-CAPS | `#3F3F3F` 8% alpha. |

**Existing-code compatibility note:** the current code uses `Consolas` 9 px for `_cellFont` and `Segoe UI` 9–10 px for `_labelFont`. The drop-in code below uses the same `TextFormat` constructor pattern but bumps cell font to 10 px IBM Plex Mono with Consolas as fallback (DirectWrite font fallback chain handled by Windows automatically when the requested font is absent).

---

## 4. Footprint Cell Rendering Recipe

### 4.1 Cell anatomy

```
       ┌────────────────────────────────────────────────────┐
       │                                                    │
  PR ► │  ····  234   ·  287  ····                          │ ◄ price 18452.25
       │  └─────┘     ─└────┘                               │
       │   bid       sep ask                                │
       │   right-     dim left-                             │
       │   align       align                                │
       └────────────────────────────────────────────────────┘
                                ▲
                                │
                      separator = U+2009 thin space
                      tinted #3F3F3F (data.faint)
                      "x" reserved for verbose mode only
```

- Cell numerals: amber `#FB8B1E` for **non-imbalanced** cells (Bloomberg "this is data" color).
- Cell numerals shift to green/red **only** when delta > 0 / < 0 at that level.
- Cell border: zero on tier 0/1; 1 px on tier 2; 2 px on tier 3/4.
- Cell padding: 2 px horizontal, 0 px vertical. **Never** vertical padding — eye loses the column.
- Right-align bid; left-align ask; separator centered. Implemented via two `DrawText` calls per cell with two separate `TextFormat` instances (`TextAlignment.Trailing` for bid, `TextAlignment.Leading` for ask).

### 4.2 Imbalance tier escalation visual

```
Tier 0 (no imbalance):
   ··· 234  ·  287 ···                  amber numbers, no border

Tier 1 (≥ 150%):
   ··· 234  ·  287 ···                  red bid number is now red,
                                         ask number stays amber

Tier 2 (≥ 250%):
   ┌────────────────┐
   │ 234  ·  287    │                   bold + 1px green border (ask-side imb)
   └────────────────┘

Tier 3 (≥ 300%):
   ╔════════════════╗
   ║ 234  ·  287    ║                   bold + 2px CYAN border + cyan flood @ 18%
   ╚════════════════╝                   numbers in CYAN (not green) — caste shift

Tier 4 (≥ 400%):
   ◢▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔◣
   ║ ║ 234  ·  287 ║ ║                  tier 3 + 4px outer cyan halo @ 30%
   ◥▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁◤                  + 1-frame white flash on detection
```

The tier 3 → 4 shift from green/red to cyan/magenta is the **single most important visual mechanic** in this design. The ambient chart is amber. Tier 1–2 imbalances stay in the green/red caste. Tier 3+ enters a different color caste entirely. A trader scanning the chart sees a sea of amber, scattered red/green, and the only thing that visually "rings the bell" is a cyan or magenta border. This is the exact perceptual mechanism the 787 glass cockpit uses to make the autopilot mode disengagement (magenta) impossible to miss in a screen full of white/cyan/green nominal data.

### 4.3 POC marker

Two-layer convention (best of Sierra + ATAS):
1. **Bloomberg amber 2 px horizontal line** drawn at the POC price across the bar's full width, **on top of cells**.
2. **1 px black contour** around the max-volume cell itself (ATAS subtle convention).

Result: the POC reads at a glance from far away (the line) AND the specific winning cell is identified up close (the contour).

### 4.4 Stacked-imbalance zone treatment

```
       ┌─────┬─────┬─────┐                ┌──────────────────────┐
       │ ◄── stacked imb ─►│              │                      │
       │     │     │     │                │                      │
       │ tier3 cells       │   ────────►  │ persistent zone band │
       │     │     │     │                │  drawn behind cells   │
       │     │     │     │                │  cyan #4DC7F9 @ 8%    │
       └─────┴─────┴─────┘                │  extends 30 bars right│
                                          └──────────────────────┘
            Right-gutter marker:
              ┃  ◄── 3 px cyan vertical bar
              ┃      labeled "S3" (3-stack)
              ┃      "S4" / "S5" if deeper
```

Persistent until either price retests the zone (then fade) or 30 bars elapsed. This is **the** highest-alpha visual on the chart.

### 4.5 Absorption signature (DEEP6 flagship)

```
                      ┌───────┐
                  ◌ ◌ │ 1240  │ ◌ ◌            ← absorbing cell
                ◌ ◌ ◌ │ ●ABS  │ ◌ ◌ ◌          cyan halo, 4px outer
                  ◌ ◌ │  cyan │ ◌ ◌            pulses 70%→100%→70%
                      └───────┘                3 cycles over 1.2 s

           label floats below: ABS  Δ-1240/V3100  W:upper
                                ─────────────────────────
                                cyan #4DC7F9 / IBM Plex Mono 9 px
```

Pulse uses a sine-wave alpha modulated against frame timestamp; max 1 active pulse per chart at a time (when a new absorption fires, the prior pulse settles to static 100%).

### 4.6 Exhaustion signature

```
   wick top
     ╲╲╲                  comet-tail gradient
      ╲╲╲                 from cell body (full magenta)
       ╲╲                 to wick tip (white-magenta fade)
        ╲╲                drawn as multi-stop linear gradient
       ┌──┐
       │  │ EXH ↑
       │  │ ─────  magenta #FF5BB8 / IBM Plex Mono 9 px
       └──┘
```

Single-frame draw (no animation) — the gradient itself does the work.

---

## 5. GEX Level Rendering

```
Price axis →

═══════════════════════════════════════════════ ← CW | +Γ 18525    green 1px solid
                                                    "call wall"

────────  ──────  ──────  ──────  ──────       ← naked POC 18510   amber dashed @ 50%
                                                    extends until touched

▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬ ← Γ⁰ 18475          PALE YELLOW 2px solid
                                                    "zero gamma"      Bloomberg highlight color

═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ← FLIP 18450        amber-caution 1.5px dash-dot

· · · · · · · · · · · · · · · · · · · · · · ·  ← V 18425           cyan dotted (vanna)

═══════════════════════════════════════════════ ← PW | -Γ 18400    red 1px solid
                                                    "put wall"

· · · · · · · · · · · · · · · · · · · · · · ·  ← C 18380           magenta dotted (charm)
```

### Label rendering rules
- Label sits in a 1 px-bordered rect, `bg.terminal` fill, label text in level color.
- Label format: `[GLYPH] [PRICE]` left of axis, right-anchored.
- Glyphs: `Γ⁰` (zero gamma), `+Γ` (call wall), `-Γ` (put wall), `Γ↔` (flip), `V` (vanna), `C` (charm), `T` (volatility trigger).
- Font: IBM Plex Mono 10 px regular, color matches line.
- Label background: `#000000` solid (so it punches through any underlying cells).
- Border: 1 px in level color.

The **zero-gamma line in pale yellow** is deliberate: this is the most important options level on the chart, and pale yellow `#FFF799` is Bloomberg's reserved "look here" color. Nothing else on the chart uses it except the crosshair and the rare confluence flag.

---

## 6. Strategy Visualization

### 6.1 Position marker

Top-left corner badge, anchored absolute:

```
┌──────────────────────────────┐
│ ●  LONG 2  @  18452.25       │   ← cyan dot = "selected/active position"
│                              │      LONG/SHORT in caste color (green/red)
│ ─────────────────────────────│      price in amber (data primary)
│  +$240.00      +6.0 ticks    │   ← P&L hero, green if profit, red if loss
│  ─────         ──────────    │      IBM Plex Mono 22 px LIGHT weight
│  GROSS         POINTS        │      tiny ALL-CAPS sublabels
└──────────────────────────────┘
```

### 6.2 Working orders

Drawn as horizontal lines extending from the entry bar to the right edge:

```
  ╴╴╴╴╴╴╴╴╴╴╴╴╴╴ TGT 2 @ 18460.00  +30.50 ──── (green dotted)
  ────────────── LMT 2 @ 18452.00  -0.25  ──── (magenta-violet solid)
                                                  ← entry price
  ╶ ─ ╶ ─ ╶ ─ ╶  TRL @ 18448.00  -4.25    ──── (amber dot-dash, follows price)
  ─ ─ ─ ─ ─ ─ ─ STP 2 @ 18445.00 -7.25    ──── (amber-caution dashed)
```

- Line label sits at the right edge with full price + distance from current.
- All lines fade to 60% alpha when off-screen above/below.
- A faint `state.auto` magenta-violet vertical band (8% alpha, gradient to 0%) connects entry price to current price, signaling "autopilot is engaged on this position."

### 6.3 P&L equity ribbon (bottom of chart)

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│   ╱╲                       ╱╲                                      │
│  ╱  ╲       ╱╲╱╲╲         ╱  ╲          ╱╲╱╲╲╱╲                    │  ← amber line, 1.5 px
│ ╱    ╲╱╲╱╲╱     ╲╲       ╱    ╲╱╲     ╱       ╲                    │     daily equity curve
│       ▼                  ▼      ▼    ▼         ●                    │
│      stop              entry  exit  entry    current                │
│                                                                    │
│ DD: -$240   PEAK: +$1,240   NET: +$840   WR: 64% (11/17)            │
└────────────────────────────────────────────────────────────────────┘
```

- Ribbon ~64 px tall, anchored bottom of price pane (toggleable; collapses to 12 px sparkline when minimized).
- Entry/exit marked by tiny triangle glyphs (▲▼) in caste color.
- Stops marked by small `✕` glyphs in amber-caution.
- Stats line beneath: tabular monospace 9 px, `data.dim` color, separated by 3 spaces (no commas).
- Current position has a single cyan dot `●` pulsing at 0.5 Hz to signal "live."

---

## 7. Full-Chart ASCII Mockup

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ NQ 06-26  ·  1 MIN  ·  VOLUMETRIC                       HTF 5M ↑    K E10 +0.41    DEEP6 SCORE 87 │ ← header strip 22 px
│                                                                                          ●●●●●●●●  │   IBM Plex Mono 10 px
├────────────────────────────────────────────────────────────────────────────────────────────────────┤   amber on black
│                                                                                                    │
│ 18525.00 ═══════════════════════════════════════════════════════════════ CW │ +Γ 18525            │ ← call wall (green)
│                                                                                                    │
│ 18510.00 ─── ─── ─── ─── ─── ─── ─── ─── ─── ─── ─── ─── ─── ─── ─── ─── nPOC 18510             │ ← naked POC (amber 50%)
│                                                                                                    │
│                                          ┌───────┐                                                 │
│ 18495.00          234·287   ...          │ 1240  │ ◌◌◌    ← ABS pulse halo cyan                    │ ← absorption sig
│                                          │  ●ABS │                                                 │
│                  ┌───────┐               └───────┘   ABS  Δ-1240/V3100  W:upper                    │
│ 18490.00         │ 145·398│ ←tier3 cyan border       ────────────────────────                      │
│                  ╚═══════╝                                                                         │
│                                                                                                    │
│ 18475.00 ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬ Γ⁰ 18475                     │ ← zero gamma (pale yellow)
│                                                                                                    │
│ 18470.00  ▓▓▓▓ POC  ───── 1240  ─────  amber 2px line                                              │ ← POC (amber)
│           87·112   ███    298·432                                                                  │
│                    ███             ┃                                                               │
│ 18465.00  142·87   ███    198·87   ┃ ← S3 right-gutter marker                                      │
│                    ███             ┃                                                               │
│ 18460.00  98·203   ███    127·43   ┃   ╴╴╴╴╴╴╴╴╴╴╴╴╴╴╴╴╴ TGT 2 @ 18460.00  +30.50  (green dotted) │ ← target
│                                                                                                    │
│ 18452.25  ────────────────────── LMT 2 @ 18452.00  -0.25  (magenta solid)                          │ ← working limit
│                                                                                                    │
│ 18450.00  ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ ─ ═ FLIP 18450  (amber dash-dot)              │ ← gamma flip
│                                                                                                    │
│ 18448.00  ╶ ─ ╶ ─ ╶ ─ ╶ ─ ╶ ─ ╶ ─ ╶ ─ ╶ ─ ╶ ─ ╶ ─ ╶ ─ ╶ TRL @ 18448.00  -4.25  (amber dot-dash)   │ ← trail stop
│ 18445.00  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ STP 2 @ 18445.00  -7.25  (amber dashed)   │ ← stop
│                                                                                                    │
│ 18400.00 ═══════════════════════════════════════════════════════════════ PW │ -Γ 18400            │ ← put wall (red)
│                                                                                                    │
│      ╔═══════════════════════════════╗                                                             │
│      ║ ●  LONG 2  @  18452.25        ║                                                             │
│      ║ ──────────────────────────── ║                                                             │
│      ║  +$240.00      +6.0 ticks   ║   ← position HUD (top-left)                                  │
│      ║  GROSS         POINTS        ║      IBM Plex Mono 22 px light                              │
│      ╚═══════════════════════════════╝                                                             │
│                                                                                                    │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  ╱╲          ╱╲╱╲╲          ╱╲                  ╱╲╱╲                                               │
│ ╱  ╲       ╱      ╲╲       ╱  ╲       ╱╲      ╱      ╲╲      ╱╲   ←  amber equity curve 1.5 px    │ ← P&L ribbon
│      ▼      ▲        ▼      ▲        ▼   ▲           ●                                             │
│  DD: -$240   PEAK: +$1,240   NET: +$840   WR: 64% (11/17)        14:32:18  RITHMIC OK  12ms       │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                                              ↑
                                                                 footer: dim, IBM Plex Mono 9 px
```

What you should see at a glance:
- **Ambient amber wash** — the chart at rest reads as a Bloomberg-amber field.
- **Cyan halo** at one specific cell = absorption (DEEP6 flagship).
- **Cyan border** at one cell = stacked imbalance (tier 3).
- **Pale yellow horizontal** = the most important options level (zero gamma).
- **Magenta-violet line** = working limit order ("autopilot engaged").
- **Green/red horizontal lines** = call wall / put wall.
- **Position HUD** floats top-left with hero P&L in 22 px IBM Plex Mono Light.

Three intensities of color, semantic-only, zero ornament.

---

## 8. Ready-to-Drop SharpDX Code

These methods use the **exact same patterns already in `DEEP6Footprint.cs`**: `MakeFrozenBrush(...).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush` for brush creation, `DisposeSolidBrush(ref ...)` for cleanup, `TextFormat` constructed with `NinjaTrader.Core.Globals.DirectWriteFactory`, all allocations in `OnRenderTargetChanged()`. Drop into the existing brush field block, the existing `OnRenderTargetChanged()`, and add the new render methods.

### 8.1 Brush field declarations — add to the existing private-field block (~line 766)

```csharp
// ── Bloomberg Reinvented palette ────────────────────────────────────────────
// All hex values verified against Bloomberg Berg theme + 787 glass cockpit caste.

// Surfaces & chrome
private SharpDX.Direct2D1.SolidColorBrush _bgTerminalDx;     // #000000
private SharpDX.Direct2D1.SolidColorBrush _bgPanelDx;        // #0A0A0A
private SharpDX.Direct2D1.SolidColorBrush _gridMajorDx;      // #1F1F1F
private SharpDX.Direct2D1.SolidColorBrush _gridMinorDx;      // #141414
private SharpDX.Direct2D1.SolidColorBrush _axisLineDx;       // #2A2A2A
private SharpDX.Direct2D1.SolidColorBrush _dividerDx;        // #262626
private SharpDX.Direct2D1.SolidColorBrush _crosshairDx;      // #FFF799 @55%

// Caste / data
private SharpDX.Direct2D1.SolidColorBrush _dataPrimaryDx;    // #FB8B1E  amber
private SharpDX.Direct2D1.SolidColorBrush _dataSecondaryDx;  // #D7D7D7
private SharpDX.Direct2D1.SolidColorBrush _dataDimDx;        // #7A7A7A
private SharpDX.Direct2D1.SolidColorBrush _dataFaintDx;      // #3F3F3F
private SharpDX.Direct2D1.SolidColorBrush _stateSelectedDx;  // #4DC7F9  CYAN
private SharpDX.Direct2D1.SolidColorBrush _stateAutoDx;      // #A965F0  MAGENTA-VIOLET
private SharpDX.Direct2D1.SolidColorBrush _stateEngagedDx;   // #5DC453  GREEN
private SharpDX.Direct2D1.SolidColorBrush _stateCautionDx;   // #FFC107  AMBER-CAUTION
private SharpDX.Direct2D1.SolidColorBrush _stateWarningDx;   // #D54135  RED

// Flow
private SharpDX.Direct2D1.SolidColorBrush _flowBuyDx;        // #5DC453
private SharpDX.Direct2D1.SolidColorBrush _flowSellDx;       // #D54135
private SharpDX.Direct2D1.SolidColorBrush _flowBuyDimDx;     // #2D5F2A
private SharpDX.Direct2D1.SolidColorBrush _flowSellDimDx;    // #5F221F

// Imbalance tier 3/4 (caste-shift colors)
private SharpDX.Direct2D1.SolidColorBrush _imbBuyT3Dx;       // #4DC7F9  cyan
private SharpDX.Direct2D1.SolidColorBrush _imbSellT3Dx;      // #FF5BB8  magenta
private SharpDX.Direct2D1.SolidColorBrush _imbBuyT3FillDx;   // #4DC7F9 @18%
private SharpDX.Direct2D1.SolidColorBrush _imbSellT3FillDx;  // #FF5BB8 @18%
private SharpDX.Direct2D1.SolidColorBrush _imbBuyHaloDx;     // #4DC7F9 @30%
private SharpDX.Direct2D1.SolidColorBrush _imbSellHaloDx;    // #FF5BB8 @30%

// Signatures
private SharpDX.Direct2D1.SolidColorBrush _sigAbsorptionDx;  // #4DC7F9
private SharpDX.Direct2D1.SolidColorBrush _sigExhaustionDx;  // #FF5BB8
private SharpDX.Direct2D1.SolidColorBrush _sigConfluenceDx;  // #FFF799
private SharpDX.Direct2D1.SolidColorBrush _sigConfTopDx;     // #FFFFFF

// Levels
private SharpDX.Direct2D1.SolidColorBrush _lvlPocDx;         // #FB8B1E
private SharpDX.Direct2D1.SolidColorBrush _lvlVaDx;          // #D7D7D7
private SharpDX.Direct2D1.SolidColorBrush _lvlVaFillDx;      // #FB8B1E @6%
private SharpDX.Direct2D1.SolidColorBrush _lvlNakedPocDx;    // #FB8B1E @50%
private SharpDX.Direct2D1.SolidColorBrush _lvlPdhPdlDx;      // #A965F0
private SharpDX.Direct2D1.SolidColorBrush _lvlGexZeroDx;     // #FFF799
private SharpDX.Direct2D1.SolidColorBrush _lvlGexFlipDx;     // #FFC107
private SharpDX.Direct2D1.SolidColorBrush _lvlGexCallDx;     // #5DC453
private SharpDX.Direct2D1.SolidColorBrush _lvlGexPutDx;      // #D54135
private SharpDX.Direct2D1.SolidColorBrush _lvlGexVoltrigDx;  // #FB8B1E
private SharpDX.Direct2D1.SolidColorBrush _lvlGexVannaDx;    // #4DC7F9 @60%
private SharpDX.Direct2D1.SolidColorBrush _lvlGexCharmDx;    // #A965F0 @60%

// Orders
private SharpDX.Direct2D1.SolidColorBrush _ordLimitDx;       // #A965F0
private SharpDX.Direct2D1.SolidColorBrush _ordStopDx;        // #FFC107
private SharpDX.Direct2D1.SolidColorBrush _ordTrailDx;       // #FB8B1E
private SharpDX.Direct2D1.SolidColorBrush _ordTargetDx;      // #5DC453

// Type formats
private TextFormat _bbgCellFont;       // IBM Plex Mono 10 regular
private TextFormat _bbgCellFontBold;   // IBM Plex Mono 10 semibold
private TextFormat _bbgCellAskFont;    // 10 regular, leading-aligned
private TextFormat _bbgChromeFont;     // Inter 11 medium
private TextFormat _bbgHeaderFont;     // Inter 10 semibold ALL-CAPS tracking
private TextFormat _bbgKpiFont;        // IBM Plex Mono 22 light
private TextFormat _bbgKpiSubFont;     // Inter 9 medium ALL-CAPS
```

### 8.2 Brush + font allocation — add to `OnRenderTargetChanged()` (after the existing block at line 1196)

```csharp
// ── Bloomberg Reinvented brushes ─────────────────────────────────────────────
_bgTerminalDx     = MakeFrozenBrush(Color.FromRgb(0x00, 0x00, 0x00)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_bgPanelDx        = MakeFrozenBrush(Color.FromRgb(0x0A, 0x0A, 0x0A)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_gridMajorDx      = MakeFrozenBrush(Color.FromRgb(0x1F, 0x1F, 0x1F)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_gridMinorDx      = MakeFrozenBrush(Color.FromRgb(0x14, 0x14, 0x14)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_axisLineDx       = MakeFrozenBrush(Color.FromRgb(0x2A, 0x2A, 0x2A)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_dividerDx        = MakeFrozenBrush(Color.FromRgb(0x26, 0x26, 0x26)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_crosshairDx      = MakeFrozenBrush(Color.FromArgb(140, 0xFF, 0xF7, 0x99)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush; // 55%

_dataPrimaryDx    = MakeFrozenBrush(Color.FromRgb(0xFB, 0x8B, 0x1E)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_dataSecondaryDx  = MakeFrozenBrush(Color.FromRgb(0xD7, 0xD7, 0xD7)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_dataDimDx        = MakeFrozenBrush(Color.FromRgb(0x7A, 0x7A, 0x7A)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_dataFaintDx      = MakeFrozenBrush(Color.FromRgb(0x3F, 0x3F, 0x3F)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_stateSelectedDx  = MakeFrozenBrush(Color.FromRgb(0x4D, 0xC7, 0xF9)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_stateAutoDx      = MakeFrozenBrush(Color.FromRgb(0xA9, 0x65, 0xF0)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_stateEngagedDx   = MakeFrozenBrush(Color.FromRgb(0x5D, 0xC4, 0x53)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_stateCautionDx   = MakeFrozenBrush(Color.FromRgb(0xFF, 0xC1, 0x07)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_stateWarningDx   = MakeFrozenBrush(Color.FromRgb(0xD5, 0x41, 0x35)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

_flowBuyDx        = MakeFrozenBrush(Color.FromRgb(0x5D, 0xC4, 0x53)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_flowSellDx       = MakeFrozenBrush(Color.FromRgb(0xD5, 0x41, 0x35)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_flowBuyDimDx     = MakeFrozenBrush(Color.FromRgb(0x2D, 0x5F, 0x2A)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_flowSellDimDx    = MakeFrozenBrush(Color.FromRgb(0x5F, 0x22, 0x1F)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

_imbBuyT3Dx       = MakeFrozenBrush(Color.FromRgb(0x4D, 0xC7, 0xF9)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_imbSellT3Dx      = MakeFrozenBrush(Color.FromRgb(0xFF, 0x5B, 0xB8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_imbBuyT3FillDx   = MakeFrozenBrush(Color.FromArgb(46, 0x4D, 0xC7, 0xF9)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush; // 18%
_imbSellT3FillDx  = MakeFrozenBrush(Color.FromArgb(46, 0xFF, 0x5B, 0xB8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_imbBuyHaloDx     = MakeFrozenBrush(Color.FromArgb(77, 0x4D, 0xC7, 0xF9)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush; // 30%
_imbSellHaloDx    = MakeFrozenBrush(Color.FromArgb(77, 0xFF, 0x5B, 0xB8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

_sigAbsorptionDx  = MakeFrozenBrush(Color.FromRgb(0x4D, 0xC7, 0xF9)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_sigExhaustionDx  = MakeFrozenBrush(Color.FromRgb(0xFF, 0x5B, 0xB8)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_sigConfluenceDx  = MakeFrozenBrush(Color.FromRgb(0xFF, 0xF7, 0x99)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_sigConfTopDx     = MakeFrozenBrush(Color.FromRgb(0xFF, 0xFF, 0xFF)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

_lvlPocDx         = MakeFrozenBrush(Color.FromRgb(0xFB, 0x8B, 0x1E)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_lvlVaDx          = MakeFrozenBrush(Color.FromRgb(0xD7, 0xD7, 0xD7)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_lvlVaFillDx      = MakeFrozenBrush(Color.FromArgb(15, 0xFB, 0x8B, 0x1E)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush; // 6%
_lvlNakedPocDx    = MakeFrozenBrush(Color.FromArgb(128, 0xFB, 0x8B, 0x1E)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush; // 50%
_lvlPdhPdlDx      = MakeFrozenBrush(Color.FromRgb(0xA9, 0x65, 0xF0)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_lvlGexZeroDx     = MakeFrozenBrush(Color.FromRgb(0xFF, 0xF7, 0x99)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_lvlGexFlipDx     = MakeFrozenBrush(Color.FromRgb(0xFF, 0xC1, 0x07)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_lvlGexCallDx     = MakeFrozenBrush(Color.FromRgb(0x5D, 0xC4, 0x53)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_lvlGexPutDx      = MakeFrozenBrush(Color.FromRgb(0xD5, 0x41, 0x35)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_lvlGexVoltrigDx  = MakeFrozenBrush(Color.FromRgb(0xFB, 0x8B, 0x1E)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_lvlGexVannaDx    = MakeFrozenBrush(Color.FromArgb(153, 0x4D, 0xC7, 0xF9)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush; // 60%
_lvlGexCharmDx    = MakeFrozenBrush(Color.FromArgb(153, 0xA9, 0x65, 0xF0)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

_ordLimitDx       = MakeFrozenBrush(Color.FromRgb(0xA9, 0x65, 0xF0)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_ordStopDx        = MakeFrozenBrush(Color.FromRgb(0xFF, 0xC1, 0x07)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_ordTrailDx       = MakeFrozenBrush(Color.FromRgb(0xFB, 0x8B, 0x1E)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
_ordTargetDx      = MakeFrozenBrush(Color.FromRgb(0x5D, 0xC4, 0x53)).ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

// Type formats — IBM Plex Mono with Consolas fallback (DirectWrite handles fallback)
_bbgCellFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
    "IBM Plex Mono", FontWeight.Regular, FontStyle.Normal, 10f) {
        TextAlignment = TextAlignment.Trailing, ParagraphAlignment = ParagraphAlignment.Center };
_bbgCellFontBold = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
    "IBM Plex Mono", FontWeight.SemiBold, FontStyle.Normal, 10f) {
        TextAlignment = TextAlignment.Trailing, ParagraphAlignment = ParagraphAlignment.Center };
_bbgCellAskFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
    "IBM Plex Mono", FontWeight.Regular, FontStyle.Normal, 10f) {
        TextAlignment = TextAlignment.Leading, ParagraphAlignment = ParagraphAlignment.Center };
_bbgChromeFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
    "Inter", FontWeight.Medium, FontStyle.Normal, 11f);
_bbgHeaderFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
    "Inter", FontWeight.SemiBold, FontStyle.Normal, 10f);
_bbgKpiFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
    "IBM Plex Mono", FontWeight.Light, FontStyle.Normal, 22f) {
        TextAlignment = TextAlignment.Leading, ParagraphAlignment = ParagraphAlignment.Center };
_bbgKpiSubFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
    "Inter", FontWeight.Medium, FontStyle.Normal, 9f);
```

### 8.3 Add to the existing `DisposeDx()` / cleanup region

```csharp
// Bloomberg Reinvented disposals
DisposeSolidBrush(ref _bgTerminalDx);     DisposeSolidBrush(ref _bgPanelDx);
DisposeSolidBrush(ref _gridMajorDx);      DisposeSolidBrush(ref _gridMinorDx);
DisposeSolidBrush(ref _axisLineDx);       DisposeSolidBrush(ref _dividerDx);
DisposeSolidBrush(ref _crosshairDx);
DisposeSolidBrush(ref _dataPrimaryDx);    DisposeSolidBrush(ref _dataSecondaryDx);
DisposeSolidBrush(ref _dataDimDx);        DisposeSolidBrush(ref _dataFaintDx);
DisposeSolidBrush(ref _stateSelectedDx);  DisposeSolidBrush(ref _stateAutoDx);
DisposeSolidBrush(ref _stateEngagedDx);   DisposeSolidBrush(ref _stateCautionDx);
DisposeSolidBrush(ref _stateWarningDx);
DisposeSolidBrush(ref _flowBuyDx);        DisposeSolidBrush(ref _flowSellDx);
DisposeSolidBrush(ref _flowBuyDimDx);     DisposeSolidBrush(ref _flowSellDimDx);
DisposeSolidBrush(ref _imbBuyT3Dx);       DisposeSolidBrush(ref _imbSellT3Dx);
DisposeSolidBrush(ref _imbBuyT3FillDx);   DisposeSolidBrush(ref _imbSellT3FillDx);
DisposeSolidBrush(ref _imbBuyHaloDx);     DisposeSolidBrush(ref _imbSellHaloDx);
DisposeSolidBrush(ref _sigAbsorptionDx);  DisposeSolidBrush(ref _sigExhaustionDx);
DisposeSolidBrush(ref _sigConfluenceDx);  DisposeSolidBrush(ref _sigConfTopDx);
DisposeSolidBrush(ref _lvlPocDx);         DisposeSolidBrush(ref _lvlVaDx);
DisposeSolidBrush(ref _lvlVaFillDx);      DisposeSolidBrush(ref _lvlNakedPocDx);
DisposeSolidBrush(ref _lvlPdhPdlDx);      DisposeSolidBrush(ref _lvlGexZeroDx);
DisposeSolidBrush(ref _lvlGexFlipDx);     DisposeSolidBrush(ref _lvlGexCallDx);
DisposeSolidBrush(ref _lvlGexPutDx);      DisposeSolidBrush(ref _lvlGexVoltrigDx);
DisposeSolidBrush(ref _lvlGexVannaDx);    DisposeSolidBrush(ref _lvlGexCharmDx);
DisposeSolidBrush(ref _ordLimitDx);       DisposeSolidBrush(ref _ordStopDx);
DisposeSolidBrush(ref _ordTrailDx);       DisposeSolidBrush(ref _ordTargetDx);
_bbgCellFont?.Dispose();    _bbgCellFont = null;
_bbgCellFontBold?.Dispose(); _bbgCellFontBold = null;
_bbgCellAskFont?.Dispose(); _bbgCellAskFont = null;
_bbgChromeFont?.Dispose();  _bbgChromeFont = null;
_bbgHeaderFont?.Dispose();  _bbgHeaderFont = null;
_bbgKpiFont?.Dispose();     _bbgKpiFont = null;
_bbgKpiSubFont?.Dispose();  _bbgKpiSubFont = null;
```

### 8.4 Render a footprint cell — drop into the cell-rendering loop

```csharp
/// <summary>
/// Bloomberg Reinvented cell renderer.  Tier escalates the visual:
///   imbTier 0..1 = amber/colored numbers, no border
///   imbTier 2    = colored numbers + 1px border in flow color
///   imbTier 3    = CYAN/MAGENTA numbers + 2px caste-shift border + 18% flood
///   imbTier 4    = tier 3 + 4px outer halo (caller wires the flash separately)
/// </summary>
private void RenderBbgCell(
    SharpDX.Direct2D1.RenderTarget rt,
    SharpDX.RectangleF cellRect,
    long bidVol, long askVol,
    int imbTier,        // 0,1,2,3,4
    bool isImbBuySide,  // true = ask-side won the diagonal compare
    bool isPoc,
    bool isMaxDelta)
{
    // ── tier 4 halo (outer glow) ──────────────────────────────
    if (imbTier >= 4)
    {
        var halo = new SharpDX.RectangleF(cellRect.X - 4, cellRect.Y - 4,
                                          cellRect.Width + 8, cellRect.Height + 8);
        var haloBrush = isImbBuySide ? _imbBuyHaloDx : _imbSellHaloDx;
        rt.FillRectangle(halo, haloBrush);
    }

    // ── tier 3+ flood ─────────────────────────────────────────
    if (imbTier >= 3)
    {
        var fill = isImbBuySide ? _imbBuyT3FillDx : _imbSellT3FillDx;
        rt.FillRectangle(cellRect, fill);
    }

    // ── tier 2+ border ────────────────────────────────────────
    if (imbTier >= 2)
    {
        var borderBrush =
            imbTier >= 3
                ? (isImbBuySide ? _imbBuyT3Dx   : _imbSellT3Dx)   // CASTE SHIFT
                : (isImbBuySide ? _flowBuyDx    : _flowSellDx);
        float borderWidth = imbTier >= 3 ? 2.0f : 1.0f;
        rt.DrawRectangle(cellRect, borderBrush, borderWidth);
    }

    // ── POC contour (1px black on top of any border) ─────────
    if (isPoc)
    {
        rt.DrawRectangle(cellRect, _bgTerminalDx, 1.0f);
    }

    // ── numerals: bid (right-aligned), separator (centered), ask (left-aligned)
    float midX = cellRect.X + cellRect.Width * 0.5f;

    // pick color caste
    SharpDX.Direct2D1.SolidColorBrush bidBrush, askBrush;
    bool useBold = imbTier >= 2;
    if (imbTier >= 3)
    {
        bidBrush = isImbBuySide ? _dataPrimaryDx : _imbSellT3Dx;
        askBrush = isImbBuySide ? _imbBuyT3Dx    : _dataPrimaryDx;
    }
    else if (imbTier >= 1)
    {
        bidBrush = isImbBuySide ? _dataPrimaryDx : _flowSellDx;
        askBrush = isImbBuySide ? _flowBuyDx     : _dataPrimaryDx;
    }
    else
    {
        bidBrush = _dataPrimaryDx;  // ambient amber when nothing's happening
        askBrush = _dataPrimaryDx;
    }

    var bidRect = new SharpDX.RectangleF(cellRect.X + 2, cellRect.Y,
                                         midX - cellRect.X - 6, cellRect.Height);
    var sepRect = new SharpDX.RectangleF(midX - 3, cellRect.Y, 6, cellRect.Height);
    var askRect = new SharpDX.RectangleF(midX + 4, cellRect.Y,
                                         cellRect.Right - midX - 6, cellRect.Height);

    var fmt = useBold ? _bbgCellFontBold : _bbgCellFont;
    rt.DrawText(FormatVolBbg(bidVol), fmt, bidRect, bidBrush);

    // separator: U+2009 thin space rendered as faint dot
    rt.DrawText("·", _bbgCellFont, sepRect, _dataFaintDx);

    rt.DrawText(FormatVolBbg(askVol), _bbgCellAskFont, askRect, askBrush);

    // ── max-delta arrow glyph (top-right corner of cell) ─────
    if (isMaxDelta)
    {
        var glyph = new SharpDX.RectangleF(cellRect.Right - 8, cellRect.Y, 8, 8);
        rt.DrawText(askVol > bidVol ? "▲" : "▼", _bbgCellFont, glyph,
                    askVol > bidVol ? _flowBuyDx : _flowSellDx);
    }
}

private static string FormatVolBbg(long v)
{
    // Bloomberg-style compact: 1234 -> "1234", 12345 -> "12.3k", 1234567 -> "1.2M"
    if (v < 10000)    return v.ToString();
    if (v < 1000000)  return (v / 1000.0).ToString("0.#") + "k";
    return (v / 1000000.0).ToString("0.##") + "M";
}
```

### 8.5 Render absorption signature (cyan halo + label)

```csharp
/// <summary>
/// DEEP6 absorption visual: cyan outer halo, optional pulse, label below.
/// Pulse alpha: caller computes phase via (now.TotalMilliseconds % 1200) / 1200.0
/// </summary>
private void RenderBbgAbsorption(
    SharpDX.Direct2D1.RenderTarget rt,
    SharpDX.RectangleF cellRect,
    long bidVol, long askVol,
    string wickLabel,           // "upper" | "lower" | "body"
    double pulsePhase)          // 0..1, sine modulated by caller
{
    // pulse alpha 70%..100%..70% via sine
    float a = (float)(0.7 + 0.3 * (0.5 + 0.5 * System.Math.Sin(pulsePhase * 2 * System.Math.PI)));
    byte alphaByte = (byte)(a * 255);

    // need a per-frame pulse brush — cheap allocation, single brush
    using (var pulseBrush = new SharpDX.Direct2D1.SolidColorBrush(rt,
        new SharpDX.Color4(0x4D / 255f, 0xC7 / 255f, 0xF9 / 255f, a)))
    {
        // 4px halo
        var halo1 = new SharpDX.RectangleF(cellRect.X - 4, cellRect.Y - 4,
                                           cellRect.Width + 8, cellRect.Height + 8);
        rt.DrawRectangle(halo1, pulseBrush, 2f);
        // 2px inner border (solid cyan)
        rt.DrawRectangle(cellRect, _sigAbsorptionDx, 2f);
    }

    // label below cell
    string label = $"ABS  Δ{(askVol - bidVol):+#;-#;0}/V{bidVol + askVol}  W:{wickLabel}";
    var labelRect = new SharpDX.RectangleF(
        cellRect.X - 4, cellRect.Bottom + 2, 240, 14);

    // small black-fill rect behind label so it punches through anything underneath
    var bg = new SharpDX.RectangleF(labelRect.X, labelRect.Y,
        MeasureTextWidth(label, _bbgCellFont) + 6, 14);
    rt.FillRectangle(bg, _bgTerminalDx);
    rt.DrawText(label, _bbgCellFont, labelRect, _sigAbsorptionDx);
}

private float MeasureTextWidth(string s, TextFormat fmt)
{
    using (var layout = new SharpDX.DirectWrite.TextLayout(
        NinjaTrader.Core.Globals.DirectWriteFactory, s, fmt, 1000f, 100f))
    {
        return layout.Metrics.Width;
    }
}
```

### 8.6 Render a GEX level line + label

```csharp
/// <summary>
/// Renders a GEX horizontal level with Bloomberg-styled label rect at right edge.
/// gexKind: "Γ⁰" | "+Γ" | "-Γ" | "Γ↔" | "V" | "C" | "T"
/// </summary>
private void RenderBbgGexLevel(
    SharpDX.Direct2D1.RenderTarget rt,
    ChartScale chartScale,
    float xLeft, float xRight,
    double price,
    string gexKind,
    string priceLabel)          // "18525.00"
{
    float y = chartScale.GetYByValue(price);

    // pick brush + style by kind
    SharpDX.Direct2D1.SolidColorBrush brush;
    float thickness;
    float[] dashes; // null = solid
    switch (gexKind)
    {
        case "Γ⁰": brush = _lvlGexZeroDx;    thickness = 2f;   dashes = null;                     break;
        case "+Γ": brush = _lvlGexCallDx;    thickness = 1f;   dashes = null;                     break;
        case "-Γ": brush = _lvlGexPutDx;     thickness = 1f;   dashes = null;                     break;
        case "Γ↔": brush = _lvlGexFlipDx;    thickness = 1.5f; dashes = new float[]{6f,3f,1f,3f}; break;
        case "V":  brush = _lvlGexVannaDx;   thickness = 1f;   dashes = new float[]{1f,3f};       break;
        case "C":  brush = _lvlGexCharmDx;   thickness = 1f;   dashes = new float[]{1f,3f};       break;
        case "T":  brush = _lvlGexVoltrigDx; thickness = 1f;   dashes = new float[]{4f,3f};       break;
        default:   brush = _lvlPocDx;        thickness = 1f;   dashes = null;                     break;
    }

    // line
    if (dashes == null)
    {
        rt.DrawLine(new SharpDX.Vector2(xLeft, y),
                    new SharpDX.Vector2(xRight, y), brush, thickness);
    }
    else
    {
        var ssProps = new SharpDX.Direct2D1.StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Custom };
        using (var ss = new SharpDX.Direct2D1.StrokeStyle(rt.Factory, ssProps, dashes))
        {
            rt.DrawLine(new SharpDX.Vector2(xLeft, y),
                        new SharpDX.Vector2(xRight, y), brush, thickness, ss);
        }
    }

    // label rect at the right edge
    string label = $"{gexKind}  {priceLabel}";
    float w = MeasureTextWidth(label, _bbgCellFont) + 8;
    var labelRect = new SharpDX.RectangleF(xRight - w - 2, y - 8, w, 16);
    rt.FillRectangle(labelRect, _bgTerminalDx);                        // black punch-through
    rt.DrawRectangle(labelRect, brush, 1f);                            // 1px border in level color
    var txtRect = new SharpDX.RectangleF(labelRect.X + 4, labelRect.Y, w - 4, 16);
    rt.DrawText(label, _bbgCellFont, txtRect, brush);
}
```

### 8.7 Render the P&L equity ribbon

Drop into `DEEP6Strategy.cs` (or as a companion indicator that reads strategy state):

```csharp
/// <summary>
/// Bloomberg amber equity curve at bottom of price pane.
/// Caller passes equity samples (sessionStart .. now), entry/exit markers, and stats.
/// </summary>
private void RenderBbgEquityRibbon(
    SharpDX.Direct2D1.RenderTarget rt,
    SharpDX.RectangleF ribbonRect,
    System.Collections.Generic.IList<double> equitySamples,  // dollar P&L over time
    System.Collections.Generic.IList<(int sampleIdx, bool isLong, bool isExit)> markers,
    double drawdown, double peak, double net, double winRatePct, int wins, int total,
    string clock, string connStatus, int latencyMs)
{
    if (equitySamples == null || equitySamples.Count < 2) return;

    // ── background panel ─────────────────────────────────────
    rt.FillRectangle(ribbonRect, _bgPanelDx);
    // top divider
    rt.DrawLine(
        new SharpDX.Vector2(ribbonRect.X, ribbonRect.Y),
        new SharpDX.Vector2(ribbonRect.Right, ribbonRect.Y),
        _dividerDx, 1f);

    // ── equity curve (amber 1.5px polyline) ──────────────────
    double minE = double.MaxValue, maxE = double.MinValue;
    foreach (var v in equitySamples) { if (v < minE) minE = v; if (v > maxE) maxE = v; }
    double rng = System.Math.Max(maxE - minE, 1.0);

    float curveTop    = ribbonRect.Y + 8;
    float curveBottom = ribbonRect.Bottom - 22;   // leave 22px for stats line
    float curveH      = curveBottom - curveTop;
    float curveW      = ribbonRect.Width - 16;

    SharpDX.Vector2 prev = new SharpDX.Vector2(
        ribbonRect.X + 8,
        curveBottom - (float)((equitySamples[0] - minE) / rng) * curveH);

    for (int i = 1; i < equitySamples.Count; i++)
    {
        float x = ribbonRect.X + 8 + (curveW * i / (equitySamples.Count - 1));
        float y = curveBottom - (float)((equitySamples[i] - minE) / rng) * curveH;
        var cur = new SharpDX.Vector2(x, y);
        rt.DrawLine(prev, cur, _dataPrimaryDx, 1.5f);  // AMBER curve
        prev = cur;
    }

    // ── entry/exit markers ───────────────────────────────────
    foreach (var (idx, isLong, isExit) in markers)
    {
        if (idx < 0 || idx >= equitySamples.Count) continue;
        float x = ribbonRect.X + 8 + (curveW * idx / (equitySamples.Count - 1));
        float y = curveBottom - (float)((equitySamples[idx] - minE) / rng) * curveH;

        SharpDX.Direct2D1.SolidColorBrush b = isLong ? _flowBuyDx : _flowSellDx;
        // entry = filled triangle, exit = small filled circle
        if (!isExit)
        {
            string glyph = isLong ? "▲" : "▼";
            var tr = new SharpDX.RectangleF(x - 5, y - 6, 10, 10);
            rt.DrawText(glyph, _bbgCellFont, tr, b);
        }
        else
        {
            using (var ell = new SharpDX.Direct2D1.Ellipse(new SharpDX.Vector2(x, y), 3f, 3f))
                rt.FillEllipse(ell, b);
        }
    }

    // ── live position dot (last sample), pulsing cyan ────────
    {
        int last = equitySamples.Count - 1;
        float x = ribbonRect.Right - 8;
        float y = curveBottom - (float)((equitySamples[last] - minE) / rng) * curveH;
        using (var ell = new SharpDX.Direct2D1.Ellipse(new SharpDX.Vector2(x, y), 4f, 4f))
            rt.FillEllipse(ell, _stateSelectedDx);
    }

    // ── stats line (IBM Plex Mono 9 px, dim) ─────────────────
    string stats = string.Format(
        "DD: {0:+$#,0.00;-$#,0.00;$0}   PEAK: {1:+$#,0.00;-$#,0.00;$0}   NET: {2:+$#,0.00;-$#,0.00;$0}   WR: {3:0}% ({4}/{5})",
        drawdown, peak, net, winRatePct, wins, total);
    var statsRect = new SharpDX.RectangleF(
        ribbonRect.X + 8, ribbonRect.Bottom - 18, ribbonRect.Width - 16, 14);
    rt.DrawText(stats, _bbgCellFont, statsRect, _dataDimDx);

    // ── footer info right-aligned ────────────────────────────
    string footer = $"{clock}   {connStatus}   {latencyMs}ms";
    float fw = MeasureTextWidth(footer, _bbgCellFont);
    var footRect = new SharpDX.RectangleF(
        ribbonRect.Right - fw - 8, ribbonRect.Bottom - 18, fw + 4, 14);
    rt.DrawText(footer, _bbgCellFont, footRect, _dataDimDx);
}
```

### 8.8 Optional: Render the position HUD (top-left)

```csharp
private void RenderBbgPositionHud(
    SharpDX.Direct2D1.RenderTarget rt,
    SharpDX.Vector2 anchor,         // top-left corner
    bool isLong, int qty, double avgPx,
    double pnlGross, double pnlPoints, double tickValue)
{
    var box = new SharpDX.RectangleF(anchor.X, anchor.Y, 240, 86);
    rt.FillRectangle(box, _bgPanelDx);
    rt.DrawRectangle(box, _dividerDx, 1f);

    // header line: cyan dot + side + size + price
    var headerRect = new SharpDX.RectangleF(box.X + 10, box.Y + 8, box.Width - 20, 16);
    using (var ell = new SharpDX.Direct2D1.Ellipse(
        new SharpDX.Vector2(box.X + 14, box.Y + 16), 4f, 4f))
        rt.FillEllipse(ell, _stateSelectedDx);          // cyan "active" dot

    string hdr = $"   {(isLong ? "LONG " : "SHORT")} {qty}  @  {avgPx:0.00}";
    var sideBrush = isLong ? _flowBuyDx : _flowSellDx;
    rt.DrawText(hdr, _bbgChromeFont, headerRect, sideBrush);

    // divider
    rt.DrawLine(
        new SharpDX.Vector2(box.X + 10, box.Y + 30),
        new SharpDX.Vector2(box.Right - 10, box.Y + 30),
        _dividerDx, 1f);

    // hero P&L
    var heroBrush = pnlGross >= 0 ? _flowBuyDx : _flowSellDx;
    string hero = $"{pnlGross:+$#,0.00;-$#,0.00;$0.00}";
    var heroRect = new SharpDX.RectangleF(box.X + 10, box.Y + 36, 130, 30);
    rt.DrawText(hero, _bbgKpiFont, heroRect, heroBrush);

    string pts = $"{pnlPoints:+0.0;-0.0;0.0} ticks";
    var ptsRect = new SharpDX.RectangleF(box.X + 140, box.Y + 36, 90, 30);
    rt.DrawText(pts, _bbgKpiFont, ptsRect, heroBrush);

    // sublabels (dim ALL-CAPS)
    rt.DrawText("GROSS", _bbgKpiSubFont,
        new SharpDX.RectangleF(box.X + 10, box.Y + 68, 80, 14), _dataDimDx);
    rt.DrawText("POINTS", _bbgKpiSubFont,
        new SharpDX.RectangleF(box.X + 140, box.Y + 68, 80, 14), _dataDimDx);
}
```

---

## 9. Why This Aesthetic Wins

The Bloomberg amber-on-black caste system wins for DEEP6 because it solves the **single hardest problem in trading-screen design**: how to make a chart densely populated with information *and* loud about exceptional events. By making the ambient field amber and reserving cyan/magenta exclusively for the highest-tier signals (DEEP6's flagship absorption/exhaustion and 3+ stacked imbalances), every screen-element naturally prioritizes itself — the trader's eye is drawn to exactly the things DEEP6 was built to detect, without any signal having to fight for attention through saturation, animation, or size. It also wins on **brand positioning**: the visual language unmistakably says "institutional," which matters because DEEP6's whole thesis (44 microstructure signals, Kronos foundation model, GEX overlay, MBO-quality data) is institutional in a market saturated with retail-flavored TradingView clones. And finally, it wins on **engineering**: the palette is deliberately small (≈18 colors total), the typography is two families, the animation budget is one pulse at a time — which means the visual system stays disciplined as DEEP6 grows new signals, and the rendering stays fast at 200-bar × 30-level density without paying a per-cell gradient tax.
