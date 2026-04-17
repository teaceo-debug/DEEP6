I have enough context. The existing code uses `BidCellBrush`/`AskCellBrush` brush properties, `OnRenderTargetChanged`, `OnRender(chartControl, chartScale)`, `RenderTarget.FillRectangle`, `RenderTarget.DrawLine`, `_cellFont = new TextFormat(... "Consolas", CellFontSize)`, and a `MakeFrozenBrush` helper. The GEX overlay has `_gexFlipDx, _gexCallWallDx, _gexPutWallDx` brushes. Now I'll compose the full design proposal.

---

# DEEP6 — Aesthetic Direction D: "Cyberpunk Neon" (Restrained)

> Codename: **NIGHT CITY MINIMAL**
> Reference language: Death Stranding minimal HUD · Cyberpunk 2077 minimal mode · Tron Legacy / Oblivion FUI (GMUNK / Cantina) · Blade Runner 2049 (Territory Studio).
> Anti-references: arcade neon, retro-CRT scanlines, Eurostile, Blade-Runner-clone display fonts, glitch text, chromatic aberration, "synthwave" pink-to-purple gradients.

---

## 1. Design Philosophy (One Paragraph, No Apologies)

This is a chart for a trader who wants to feel like the desk is **operating equipment**, not running a SaaS app. The screen is dark — deep indigo, never pure black — and almost everything sits at low chroma until the system has something specific to say. When it does, the signal arrives in **one of exactly two voltages**: neon mint (`#00FFC8`) for buy-side intent, hot pink (`#FF006E`) for sell-side intent. Everything else — grid lines, axis ticks, default cells, secondary text — is drained, quiet, and recedes. A subtle vignette pulls the eye to the center of the chart. Glow exists, but only on **actionable** signals (DEEP6 absorption / exhaustion, working orders, the live price line) and is capped at two halos visible at any moment. This isn't parody because the cyberpunk vocabulary is applied **only as an accent on top of an institutional grid**. There are no scanlines, no glitch frames, no chromatic fringing, no gratuitous gradients. The aesthetic is "night-shift bridge of a starship," not "neon arcade." It's for the 2 AM Globex trader who runs five-figure stops on NQ and wants the chart to feel as serious as the position.

---

## 2. Complete Color Palette (Verified Hex)

All colors expressed sRGB hex. ARGB form shown when alpha matters. Every value is dropped into `Color.FromArgb(...)` calls in §10.

### 2.1 Core surfaces

| Token | Hex / ARGB | Where it lives |
|---|---|---|
| `bg.deep` | `#08051A` | Chart background. Deep indigo, NOT pure black — black under SharpDX D2D antialiasing eats neon edges. |
| `bg.panel` | `#0E0A24` | HUD panel fills (Score HUD, Chart Trader, GEX panel). One step lifted from `bg.deep`. |
| `bg.panel.hi` | `#15103A` | Hover / pressed state for buttons. |
| `vignette.edge` | `#000000 @ 10%` (`0x1A000000`) | Subtle radial darkening at chart edges (4 corners). |
| `grid.minor` | `#5145A8 @ 8%` (`0x14 5145A8`) | Vertical/horizontal grid lines — blue-violet tint, very low alpha. |
| `grid.major` | `#7A6BD9 @ 14%` (`0x24 7A6BD9`) | Hour separators / day separators. |
| `axis.tick` | `#9A92C4` | Price ladder + time axis ticks. Off-white with violet bias. |

### 2.2 Two-voltage semantic system (the entire UI runs on two colors)

| Token | Hex | Use |
|---|---|---|
| `neon.mint` | `#00FFC8` | Buy-side (long, bid-dominant cells, absorption-bullish, working buy order, P&L up). |
| `neon.pink` | `#FF006E` | Sell-side (short, ask-dominant cells, exhaustion-bearish, working sell order, P&L down). |
| `neon.mint.dim` | `#00B894` | Buy-side at low conviction (TypeC tier). |
| `neon.pink.dim` | `#B8004F` | Sell-side at low conviction. |
| `neon.mint.glow` | `#00FFC8 @ 30%` (`0x4D 00FFC8`) | Outer halo color for buy signals. |
| `neon.pink.glow` | `#FF006E @ 30%` (`0x4D FF006E`) | Outer halo color for sell signals. |

### 2.3 Secondary accent (electric purple — the DEEP6 signature)

| Token | Hex | Use |
|---|---|---|
| `accent.violet` | `#A855F7` | Stacked-imbalance shading; trapped-volume zones; "this is special" overlay. |
| `accent.violet.fill` | `#A855F7 @ 14%` (`0x24 A855F7`) | Filled zones (stacked-imbalance bands). |
| `accent.violet.line` | `#A855F7 @ 60%` (`0x99 A855F7`) | Edges of those bands. |

Why violet and not pink-purple gradient: a third saturated hue distinguishes structure-flagging from semantic direction. Pink already means "sell." Violet means "look here, no opinion."

### 2.4 Imbalance escalation (the only place where glow escalates with severity)

| Tier | Trigger (DEEP6 thresholds) | Border | Fill | Outer glow |
|---|---|---|---|---|
| **Subtle** | ≥150% diagonal ratio | 0 px | `bg.panel` only | none |
| **Weak** | ≥200% | 1 px `neon.mint`/`neon.pink` @ 50% | none | none |
| **Strong** | ≥300% | 1 px `neon.mint`/`neon.pink` @ 100% | side color @ 18% | none |
| **Extreme** | ≥400% AND vol ≥ 50 | 2 px `neon.mint`/`neon.pink` | side color @ 30% | **4 px outer glow @ 30%** |
| **Stacked (3+ in a row)** | structural | wrap zone in `accent.violet.line` 1 px | `accent.violet.fill` band | none on cells; band itself does the work |

Hard rule: **only the Extreme tier gets a glow.** This keeps glow rare and meaningful.

### 2.5 DEEP6 signature signals (the showpiece)

| Signal | Visual treatment | Hex |
|---|---|---|
| **Absorption (bull)** | Cyan halo around the absorbing cell, breathing pulse 0.4 Hz | core `#00E5FF`, glow `#00E5FF @ 30%` (`0x4D 00E5FF`), 8 px outer |
| **Absorption (bear)** | Pink halo, same mechanic | core `#FF1493`, glow `0x4D FF1493`, 8 px outer |
| **Exhaustion (bull)** | Mint comet-tail leftward 6 bars, opacity 60→0% | head `#00FFC8`, tail same with linear fade |
| **Exhaustion (bear)** | Pink comet-tail leftward 6 bars | head `#FF006E`, tail same |

Cyan vs mint distinction matters: **absorption is a different color family from buy/sell.** Cyan = "passive defense." Mint = "active intent." Reading hierarchy stays clean.

### 2.6 Levels (POC / VAH / VAL / GEX — neon but thin)

| Level | Color | Stroke | Glow |
|---|---|---|---|
| Bar POC | `#FFD23F` (gold, kept from current palette — gold reads on dark indigo without screaming) | 2 px solid | 2 px outer @ 25% |
| Prior-day POC | `#FFD23F @ 80%` | 1 px solid | none |
| Naked POC | `#FFD23F @ 50%` | 1 px dashed (4-3) | none |
| VAH / VAL | `#7A6BD9` (cool violet — separates from POC family) | 1 px dashed (3-2) | none |
| GEX zero gamma | `#00E5FF` neon cyan | 1.5 px solid | **4 px outer @ 25%** (the only level with glow) |
| GEX flip | `#FF1493` neon magenta | 1.5 px dashed (5-3) | none |
| GEX call wall | `#00FFC8` neon mint | 2 px solid | none |
| GEX put wall | `#FF006E` neon pink | 2 px solid | none |
| Liquidity wall (bid) | `#3B82F6` electric blue | 1 px solid + half-opacity rect | none |
| Liquidity wall (ask) | `#FB923C` warm orange | 1 px solid + half-opacity rect | none |

Bid/ask wall colors stay blue/orange because cyberpunk **isn't** an excuse to break L2 conventions — you need DOM colors to differ from semantic mint/pink to avoid confusion with directional signals.

### 2.7 Text

| Token | Hex | Use |
|---|---|---|
| `ink.primary` | `#E8E6FF` | Cell numerals, score readout. Off-white with violet bias (NOT pure white — pure white burns on indigo). |
| `ink.secondary` | `#9AA3D9` | Labels, narrative line, axis text. Cyan-tinted dim. |
| `ink.dim` | `#6B6B95` | Disqualified/quiet states, separator characters. |
| `ink.accent.mint` | `#00FFC8` | P&L positive number, "LONG" tier badge text. |
| `ink.accent.pink` | `#FF006E` | P&L negative number, "SHORT" tier badge text. |

### 2.8 Strategy P&L

| State | Color |
|---|---|
| Equity at ATH | `#00FFC8` + 2 px outer glow @ 25% |
| Equity rising | `#00FFC8 @ 80%` |
| Equity flat | `#9AA3D9` |
| Equity falling | `#FF006E @ 80%` |
| Equity at ATL | `#FF006E` + 2 px outer glow @ 25% |
| Drawdown band | `#FF006E @ 12%` fill |
| Risk-cap reached | flash `#FFD23F` (gold) for 800 ms then return to flat |

### 2.9 Working orders & position

| Token | Hex | Stroke |
|---|---|---|
| Working buy limit | `#00FFC8 @ 90%` | 1 px dashed (6-3) |
| Working sell limit | `#FF006E @ 90%` | 1 px dashed (6-3) |
| Stop loss (long) | `#FF006E @ 60%` | 1 px dashed (3-3) |
| Stop loss (short) | `#00FFC8 @ 60%` | 1 px dashed (3-3) |
| Take profit | matches direction @ 70% | 1 px dotted (1-2) |
| Position line | matches direction | 2 px solid + 4 px outer glow @ 25% |
| Position chevron | matches direction | filled triangle 8 px |

### 2.10 Transient flashes (very rare, very brief)

| Event | Color | Duration |
|---|---|---|
| Order filled | `#00FFC8` (long) / `#FF006E` (short), full alpha → 0 over 600 ms | 600 ms |
| Stop hit | `#FF006E` flash on chart edge frame | 400 ms |
| New ATH | `#00FFC8` flash on equity ribbon | 800 ms |

Hard rule: **never more than one flash per second.** Queue them.

---

## 3. Typography Spec

| Surface | Font | Size | Weight | Letter-spacing | Case |
|---|---|---|---|---|---|
| **Cell numerals** | `JetBrains Mono` (fallback `Consolas`) | 9 px (Normal) / 11 px (Detail) | Regular 400 | `+0.04 em` | as-is |
| **Score readout (HUD line 1)** | `JetBrains Mono` | 12 px | Medium 500 | `+0.06 em` | digits |
| **Tier badge** | `Inter` | 10 px | SemiBold 600 | `+0.10 em` | UPPERCASE |
| **Narrative line (HUD line 3)** | `Inter` | 9 px | Regular 400 | `+0.02 em` | sentence |
| **Section headers** | `Inter` | 9 px | SemiBold 600 | `+0.14 em` | UPPERCASE |
| **Axis ticks** | `Inter` | 9 px | Regular | `0` | digits |
| **Pill labels (GEX, working orders)** | `Inter` | 8 px | Medium | `+0.08 em` | UPPERCASE |
| **Chart Trader buttons** | `Inter` | 9 px | Medium | `+0.10 em` | UPPERCASE |

Notes:

- **JetBrains Mono** for digits — has tabular figures, distinctive zero (slashed), feels modern without screaming "cyberpunk." Acceptable substitutes: Berkeley Mono, IBM Plex Mono, Iosevka. NOT Eurostile, NOT OCR-A, NOT Orbitron — those are parody.
- **Inter** for chrome — neutral geometric sans, the "Helvetica of 2026." Substitute: Söhne, Aktiv Grotesk, San Francisco Pro.
- **All-caps reserved** for badges (`TIER A`, `LONG`, `SHORT`, `RISK`) and section headers only. Never narrative sentences.
- Letter-spacing wider than default gives the "interface" feeling without changing typeface.
- DirectWrite cannot do letter-spacing directly via TextFormat; we use `TextLayout.SetCharacterSpacing(leadingSpacing, trailingSpacing, minAdvanceWidth, range)` — see §10.

---

## 4. Glow System (The Signature Mechanic)

Glow is the single visual feature that differentiates this aesthetic from "premium dark SaaS." It must be:

1. **Rare** — applied only on the inventory below.
2. **Soft** — outer-only, never inner; falloff cubic, not linear.
3. **Bounded** — cap of **2 simultaneous glows** visible. If a third candidate fires, drop the oldest.

### 4.1 Inventory of allowed glows

| Element | Radius | Alpha | Pulse |
|---|---|---|---|
| Absorption cell halo | 8 px | 30% | 0.4 Hz breath (alpha 20→40%) |
| Exhaustion comet head | 6 px | 30% | static |
| Extreme imbalance cell | 4 px | 30% | static |
| GEX zero-gamma line | 4 px | 25% | static |
| Position line | 4 px | 25% | static |
| ATH/ATL equity marker | 2 px | 25% | 0.3 Hz breath |
| Order-fill flash | 12 px | 80→0% | one-shot 600 ms decay |

Everything else: no glow. Cells without imbalance, axis text, grid, default POC, VAH/VAL, working orders, P&L value, narrative text.

### 4.2 SharpDX implementation strategy

Direct2D 1.1 supports `SharpDX.Direct2D1.Effects.GaussianBlur` if you have an `ID2D1DeviceContext`. NinjaTrader's `RenderTarget` is `WindowRenderTarget` (D2D 1.0), so the blur effect path is brittle. Two reliable options:

**Option A (preferred — radial gradient halo):**

Draw a `RadialGradientBrush` ellipse behind the element. Cheap, deterministic, works on every NT8 install.

**Option B (multi-pass concentric stroke):**

Draw the element 3–4 times at increasing stroke widths with decreasing alpha. Used for line-shaped elements (GEX line, position line, comet tail) where a radial brush doesn't fit.

Both are demonstrated in §10.

---

## 5. Footprint Cell Rendering Recipe

### 5.1 Cell anatomy (ASCII, Normal mode 60 × 16 px)

```
xLeft                                       xLeft+colW
  ┌────────────────────────────────────────┐  ┐
  │                                        │  │ rowH = pixelsPerTick
  │  ░░░░░░░░ │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░│  │ (typ. 14–18 px)
  │           │                            │  │
  │   123     ·     456                    │  │  separator dim @ 40%
  │           │                            │  │
  │  ░░░░░░░░ │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░│  │
  └────────────────────────────────────────┘  ┘
   ←  bid    ←sep→        ask              →
   right-aln              left-aln
   tabular                tabular
   JetBrains Mono 9 px    JetBrains Mono 9 px
   ink.primary            ink.primary

   Default state: NO border, NO fill — cell is just text on bg.deep.
                  Only imbalance escalation paints anything.
```

### 5.2 Default rule: cells stay neutral grayscale

In contrast to the current build (which colors cells red/blue based on bid/ask dominance), cyberpunk demands restraint. Default cells show **only the numerals in `ink.primary`** on `bg.deep`. The eye is not distracted.

The information channel that *was* "red vs blue cell tint" moves to the **imbalance escalation system** (§2.4). You only see color when something actually deviates from balance.

### 5.3 Imbalance escalation (concrete pixel recipe)

```
SUBTLE  150-200% │ no visible treatment — the score system flags it instead
                 │
WEAK    200-300% │ ┌────────────────────────┐ ← 1px border, side color @ 50% alpha
                 │ │  123  ·  456           │
                 │ └────────────────────────┘
                 │
STRONG  300-400% │ ╔════════════════════════╗ ← 1px border, side color @ 100%
                 │ ║░░░░░░░░░░░░░░░░░░░░░░░░║   fill = side color @ 18%
                 │ ║  123  ·  456           ║
                 │ ╚════════════════════════╝
                 │
EXTREME  400%+   │ ╔══════════════════════════╗  ← 2px border + 4px outer glow
                 │ ║▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓║     fill = side color @ 30%
                 │ ║   123  ·  456            ║     glow = side color @ 30%
                 │ ╚══════════════════════════╝
                 │     · · · 4px halo · · ·
```

### 5.4 Stacked-imbalance zone (3+ contiguous extreme cells, same side)

```
                   ┌─────────── violet zone ──────────┐
   ┌────────────┐  │ ╔════════════════════════════════╗
   │  98 · 410  │  │ ║▓▓▓▓▓▓▓▓▓▓▓▓ extreme ▓▓▓▓▓▓▓▓▓▓║   ←  3 stacked
   ├────────────┤  │ ╠════════════════════════════════╣      buy imbalances
   │ 102 · 489  │  │ ║▓▓▓▓▓▓▓▓▓▓▓▓ extreme ▓▓▓▓▓▓▓▓▓▓║      wrapped in
   ├────────────┤  │ ╠════════════════════════════════╣      accent.violet
   │  91 · 367  │  │ ║▓▓▓▓▓▓▓▓▓▓▓▓ extreme ▓▓▓▓▓▓▓▓▓▓║      band
   └────────────┘  │ ╚════════════════════════════════╝
                   └──────────── 1px violet edge ───────┘
                       fill: accent.violet.fill (#A855F7 @ 14%)
```

The violet band **replaces** the per-cell glow — too much glow on three adjacent cells violates the 2-glow cap. The band itself signals significance.

### 5.5 POC line per bar

A 2 px gold line spanning the cell column, plus a 2 px outer halo at 25% alpha. Drawn as a 4 px tall rect filled with a vertical 3-stop gradient: edges `gold @ 0%`, center `gold @ 100%`. (See `_pocGradientBrush` in §10.)

### 5.6 Absorption signature (cyan electric breath)

```
       ╭─── 8px halo, breathing 0.4 Hz ───╮
       │   ┌──────────────────────┐       │
       │   │░░░░░ cell content ░░░│       │   inner cell still shows
       │   │   bid · ask          │       │   numerals normally
       │   └──────────────────────┘       │
       │                                  │
       ╰── halo: #00E5FF outer @ 30% ─────╯
              alpha animates 20→40→20 over 2.5 s
              max 1 active absorption halo
              at any time per chart
```

Alpha breathing: `alpha(t) = 30 + 10·sin(2π·0.4·t)` percent.

### 5.7 Exhaustion signature (pink comet tail)

```
   bar -6   -5   -4   -3   -2   -1   bar0
    ░    ░    ░    ░░   ░░░  ░░░░ ┌──────┐
                                   │  ★   │   ← exhaust head
                                   └──────┘     #FF006E core
        tail: same color, alpha
        linear from 0% (bar -6) to
        60% (bar -1), then 100% at head
```

Implementation: 6 small filled triangles trailing leftward at the exhaustion price, each at the price level, alpha proportional to bar age.

---

## 6. Vignette + Atmospheric Effects (What's Tasteful)

### 6.1 YES: Subtle radial vignette

A radial gradient overlay drawn last (after all chart content, before HUD). Center transparent, corners darken to `#000000 @ 10%`. Effect is subliminal — most users won't consciously notice it, but it shifts focus to the price action in the center third of the chart.

```
   ┌──────────────────────────────────────────┐
   │░░                                      ░░│  ← corners ~10% darker
   │  ░░                                  ░░  │
   │    ░░░                            ░░░    │
   │       ░░░                      ░░░       │
   │           ░░░░            ░░░░           │
   │               ░░░░    ░░░░               │
   │                    ░░                    │  ← center untouched
   │               ░░░░    ░░░░               │
   │           ░░░░            ░░░░           │
   │       ░░░                      ░░░       │
   │    ░░░                            ░░░    │
   │  ░░                                  ░░  │
   │░░                                      ░░│
   └──────────────────────────────────────────┘
```

Implementation: `RadialGradientBrush` filling the entire chart panel rect, with center `Color(0,0,0,0)` and edge `Color(0,0,0,26)` (10% alpha). Drawn over price action, under HUD.

### 6.2 YES, with caveat: Film grain at 0.5% alpha

Debatable. It works ONLY if:
- alpha ≤ 1% (anything more becomes visible noise that fatigues),
- the grain texture is static (pre-baked bitmap, not animated — animated grain at chart speed = motion sickness),
- it's disabled by default behind a `ShowGrain` parameter.

Recommendation: ship it disabled. It's a 0.1% improvement that only matters in screenshots. Skip unless the user specifically asks.

### 6.3 NO: Scanlines

Horizontal scanlines (`░░░░ ░░░░ ░░░░`) are the #1 cyberpunk parody signal. They reduce numeric legibility (tabular figures lose their column edges), they look like a 1990s CRT emulator, and they signal "I'm a chart skin, not a trading system." **Hard ban.**

### 6.4 NO: Chromatic aberration

The red/cyan fringing on text edges (Cyberpunk 2077 menu screens used it heavily). Looks great on a static screenshot, makes numbers harder to read, fatigues quickly. Trading display ≠ marketing render. **Hard ban.**

### 6.5 NO: Glitch text / data-mosh effects

Animated character substitution (`R̷̢͟a̛͝͝t̕͠e`) belongs in a movie title sequence. In a trading HUD it makes you doubt the data feed. **Hard ban.**

### 6.6 NO: Synthwave gradients

Hot pink → orange → purple sky gradient. Belongs on an album cover. **Hard ban.**

---

## 7. GEX Level Rendering (Neon Lines, Done Tastefully)

```
                                                            ┌──────┐
                  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│GFLIP │  pink dashed
                                                            │21,140│  pink pill 1px border
                                                            └──────┘

══════════════════════════════════════════════════════════ ┌──────┐
░░░░░░░░░░░░░░░░░░░░░░ 4px outer glow @ 25% ░░░░░░░░░░░░░░│ 0γ   │  cyan solid + GLOW
══════════════════════════════════════════════════════════ │21,090│  cyan pill 1px border
                                                            └──────┘

──────────────────────────────────────────────────────────  ┌──────┐
                                                            │CALL  │  mint solid
                                                            │21,200│  mint pill 1px border
                                                            └──────┘
```

Pill labels: 8 px Inter UPPERCASE, 1 px border in level color, fill `bg.panel`, padding 4 px horizontal × 2 px vertical. Anchored to right panel edge.

GEX zero-gamma is the only level that gets glow — it's the most tradeable single GEX level on NQ. The visual hierarchy reinforces tradability.

---

## 8. Strategy Visualization

### 8.1 Equity ribbon (top of chart, full width, 12 px tall strip)

```
   ┌──────────────────────────────────────────────────────┐
   │ EQUITY  +$1,247  ●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●  │  ← mint when up
   └──────────────────────────────────────────────────────┘
                              ↑
                       12 px tall area-fill
                       gradient: bottom alpha 0%
                                 top alpha 25%

   ┌──────────────────────────────────────────────────────┐
   │ EQUITY  -$418   ●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●  │  ← pink when down
   └──────────────────────────────────────────────────────┘

   At ATH: ribbon glows mint @ 25%, breath 0.3 Hz.
   Drawdown band: pink @ 12% fill below the line, capped at MaxDD level.
```

### 8.2 Working orders (horizontal price lines + floating pill)

```
                                              ┌─────────────┐
   ──── ──── ──── ──── ──── ──── ──── ──── ──│ BUY 2 @ 21082│   mint dashed
                                              └─────────────┘    pill at right
                                                                 panel edge
```

- Line: 1 px dashed (6-3), color = side, alpha 90%.
- Pill: 8 px Inter UPPERCASE, 1 px border in side color, fill `bg.panel`, two-line `BUY 2` / `21082.50`.

### 8.3 Position line + chevron

```
                                             ▶
   ════════════════════════════════════════════   2 px solid mint + 4 px glow
                                                  chevron 8 px filled mint
                                                  pointing right (where price
                                                  needs to go for profit)
```

A short / sell position uses `▼` (downward triangle) and pink.

---

## 9. ASCII Full-Chart Mockup

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ DEEP6 NQ 06-26 · 1m · 14:23:42 PT      [CELLS][POC][VA][ANCH][ABS][EXH][L2]         │  Chart Trader pills (UPPER)
│                                                                                     │  bg.panel @ 78% alpha
│  ┌───────────────────────────────────────────────────────────────────────────────┐  │
│  │ EQUITY  +$1,247   ●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●  │  │  Equity ribbon (top)
│  └───────────────────────────────────────────────────────────────────────────────┘  │  mint area, glow at ATH
│                                                                                     │
│ 21125 ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │  PD VAH violet dashed
│                                                                                     │
│ 21100 ──────────────────────────── PD POC gold ────────────────────────── ┌───┐    │  PD POC gold thick + glow
│                                                                            │PDH │    │  pill: gold border
│                                                                            └───┘    │
│                                              ┌──┐                                   │
│ 21082         BAR0  BAR1  BAR2  BAR3  BAR4   │▶ │  position line mint + glow        │  ▶ chevron = long live
│ ════════════════════════════════════════════ └──┘                                   │
│                                                                                     │
│       ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │
│ 21075 │ 23 · 41  │ │ 19 · 38  │ │ 14 · 52  │ │  9 · 71  │ │  7 · 88  │              │  default cells: text only
│       │ 38 · 67  │ │ 41 · 89  │ │ 35 · 122 │ │ 28 · 156 │ │ 22 · 189 │              │
│       │ 52 · 144 │ │ 88 · 367 │ │102 · 489▓│ │ 91 · 410▓│ │ 73 · 354▓│              │  ▓ = stacked extreme buy
│       │ 71 · 89  │ │ 64 · 102 │ │ 58 · 134▓│ │ 49 · 158▓│ │ 38 · 178▓│              │      wrapped in
│       │ 89 · 51  │ │ 71 · 44  │ │ 52 · 38  │ │ 44 · 31  │ │ 38 · 24  │              │      violet band
│       │ 122 · 33 │ │ 88 · 22  │ │ 64 · 19  │ │ 51 · 14  │ │ 44 · 11  │              │
│       └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘              │
│ 21050 ────────── PD POC ───── ┌──────┐ ╭──── ABS halo cyan ────╮                    │
│                                │ POC  │ │  ░░░░░░░░░░░░░░░░░░  │  cyan breath       │
│                                └──────┘ │  ░░ 102 · 489 ░░░░░░░░  0.4 Hz            │
│                                         │  ░░ EXTREME   ░░░░░░░░                    │
│                                         ╰──── 8px halo @ 30% ─────╯                 │
│                                                                                     │
│ 21025 ────────────────── 0γ GEX cyan + glow ────────────── ┌──────┐                 │  GEX zero-gamma
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│ 0γ   │  ←only level    │  cyan + glow only
│                                                            │21025 │   with glow      │
│                                                            └──────┘                 │
│ 21000 ─ ─ ─ ─ ─ ─ ─ GFLIP pink dashed ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┌──────┐                 │
│                                                            │GFLIP │                 │
│                                                            │21000 │                 │
│                                                            └──────┘                 │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐            │
│  │ 73   TIER A   LONG                                                   │            │  Score HUD (bottom-left)
│  │ Stacked buy imbalance + absorption at PD POC. Confluence: 6/12.     │            │  bg.panel @ 78%
│  └─────────────────────────────────────────────────────────────────────┘            │  border violet @ 30%
│                                                                                     │
│ ░░ corners darken via vignette @ 10%      bg.deep #08051A                       ░░ │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Ready-to-Drop SharpDX Code

All snippets follow the existing DEEP6Footprint.cs patterns: brush allocation in `OnRenderTargetChanged`, disposal in `DisposeDx`, calls inside `OnRender(chartControl, chartScale)`. Type aliases (`Brush = System.Windows.Media.Brush`, etc.) match the existing file header.

### 10.1 Color brush definitions (drop into `OnRenderTargetChanged`)

```csharp
// ─── Cyberpunk Neon palette — device-dependent brushes ───
// Allocated once per render target. Disposed in DisposeDx.

// Surfaces
private SharpDX.Direct2D1.SolidColorBrush _cnBgDeepDx;        // #08051A
private SharpDX.Direct2D1.SolidColorBrush _cnBgPanelDx;       // #0E0A24 @ 78%
private SharpDX.Direct2D1.SolidColorBrush _cnBgPanelHiDx;     // #15103A
private SharpDX.Direct2D1.SolidColorBrush _cnGridMinorDx;     // #5145A8 @ 8%
private SharpDX.Direct2D1.SolidColorBrush _cnGridMajorDx;     // #7A6BD9 @ 14%
private SharpDX.Direct2D1.SolidColorBrush _cnAxisTickDx;      // #9A92C4

// Two-voltage semantic
private SharpDX.Direct2D1.SolidColorBrush _cnMintDx;          // #00FFC8
private SharpDX.Direct2D1.SolidColorBrush _cnPinkDx;          // #FF006E
private SharpDX.Direct2D1.SolidColorBrush _cnMintDimDx;       // #00B894
private SharpDX.Direct2D1.SolidColorBrush _cnPinkDimDx;       // #B8004F
private SharpDX.Direct2D1.SolidColorBrush _cnMintFillDx;      // #00FFC8 @ 18%
private SharpDX.Direct2D1.SolidColorBrush _cnPinkFillDx;      // #FF006E @ 18%
private SharpDX.Direct2D1.SolidColorBrush _cnMintGlowDx;      // #00FFC8 @ 30%
private SharpDX.Direct2D1.SolidColorBrush _cnPinkGlowDx;      // #FF006E @ 30%

// Violet accent (stacked imbalance)
private SharpDX.Direct2D1.SolidColorBrush _cnVioletDx;        // #A855F7
private SharpDX.Direct2D1.SolidColorBrush _cnVioletFillDx;    // #A855F7 @ 14%
private SharpDX.Direct2D1.SolidColorBrush _cnVioletLineDx;    // #A855F7 @ 60%

// Absorption / exhaustion
private SharpDX.Direct2D1.SolidColorBrush _cnAbsorbCyanDx;    // #00E5FF
private SharpDX.Direct2D1.SolidColorBrush _cnAbsorbCyanGlowDx;// #00E5FF @ 30%
private SharpDX.Direct2D1.SolidColorBrush _cnAbsorbPinkDx;    // #FF1493
private SharpDX.Direct2D1.SolidColorBrush _cnAbsorbPinkGlowDx;// #FF1493 @ 30%

// Text
private SharpDX.Direct2D1.SolidColorBrush _cnInkPrimaryDx;    // #E8E6FF
private SharpDX.Direct2D1.SolidColorBrush _cnInkSecondaryDx;  // #9AA3D9
private SharpDX.Direct2D1.SolidColorBrush _cnInkDimDx;        // #6B6B95

// Vignette gradient
private SharpDX.Direct2D1.RadialGradientBrush _cnVignetteDx;
private SharpDX.Direct2D1.GradientStopCollection _cnVignetteStops;

// Halo brushes (radial, used per-signal)
private SharpDX.Direct2D1.GradientStopCollection _cnHaloCyanStops;
private SharpDX.Direct2D1.GradientStopCollection _cnHaloMintStops;
private SharpDX.Direct2D1.GradientStopCollection _cnHaloPinkStops;

public override void OnRenderTargetChanged()
{
    DisposeDx();
    if (RenderTarget == null) return;

    // ... existing brush allocations ...

    _cnBgDeepDx       = MakeFrozenBrush(Color.FromRgb(0x08, 0x05, 0x1A))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnBgPanelDx      = MakeFrozenBrush(Color.FromArgb(199, 0x0E, 0x0A, 0x24))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnBgPanelHiDx    = MakeFrozenBrush(Color.FromRgb(0x15, 0x10, 0x3A))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnGridMinorDx    = MakeFrozenBrush(Color.FromArgb(20, 0x51, 0x45, 0xA8))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnGridMajorDx    = MakeFrozenBrush(Color.FromArgb(36, 0x7A, 0x6B, 0xD9))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnAxisTickDx     = MakeFrozenBrush(Color.FromRgb(0x9A, 0x92, 0xC4))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

    _cnMintDx         = MakeFrozenBrush(Color.FromRgb(0x00, 0xFF, 0xC8))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnPinkDx         = MakeFrozenBrush(Color.FromRgb(0xFF, 0x00, 0x6E))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnMintDimDx      = MakeFrozenBrush(Color.FromRgb(0x00, 0xB8, 0x94))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnPinkDimDx      = MakeFrozenBrush(Color.FromRgb(0xB8, 0x00, 0x4F))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnMintFillDx     = MakeFrozenBrush(Color.FromArgb(46, 0x00, 0xFF, 0xC8))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnPinkFillDx     = MakeFrozenBrush(Color.FromArgb(46, 0xFF, 0x00, 0x6E))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnMintGlowDx     = MakeFrozenBrush(Color.FromArgb(77, 0x00, 0xFF, 0xC8))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnPinkGlowDx     = MakeFrozenBrush(Color.FromArgb(77, 0xFF, 0x00, 0x6E))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

    _cnVioletDx       = MakeFrozenBrush(Color.FromRgb(0xA8, 0x55, 0xF7))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnVioletFillDx   = MakeFrozenBrush(Color.FromArgb(36, 0xA8, 0x55, 0xF7))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnVioletLineDx   = MakeFrozenBrush(Color.FromArgb(153, 0xA8, 0x55, 0xF7))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

    _cnAbsorbCyanDx     = MakeFrozenBrush(Color.FromRgb(0x00, 0xE5, 0xFF))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnAbsorbCyanGlowDx = MakeFrozenBrush(Color.FromArgb(77, 0x00, 0xE5, 0xFF))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnAbsorbPinkDx     = MakeFrozenBrush(Color.FromRgb(0xFF, 0x14, 0x93))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnAbsorbPinkGlowDx = MakeFrozenBrush(Color.FromArgb(77, 0xFF, 0x14, 0x93))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

    _cnInkPrimaryDx   = MakeFrozenBrush(Color.FromRgb(0xE8, 0xE6, 0xFF))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnInkSecondaryDx = MakeFrozenBrush(Color.FromRgb(0x9A, 0xA3, 0xD9))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _cnInkDimDx       = MakeFrozenBrush(Color.FromRgb(0x6B, 0x6B, 0x95))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

    // Vignette: radial gradient stop collection (reused, brush rebuilt per frame
    // because center moves with chart panel resize).
    _cnVignetteStops = new SharpDX.Direct2D1.GradientStopCollection(
        RenderTarget,
        new SharpDX.Direct2D1.GradientStop[]
        {
            new SharpDX.Direct2D1.GradientStop { Position = 0.55f,
                Color = new SharpDX.Color4(0f, 0f, 0f, 0f) },         // center clear
            new SharpDX.Direct2D1.GradientStop { Position = 1.00f,
                Color = new SharpDX.Color4(0f, 0f, 0f, 0.10f) },      // edge 10% black
        });

    // Halo gradient stop collections (used by RadialGradientBrush per-signal)
    _cnHaloCyanStops = BuildHaloStops(0x00, 0xE5, 0xFF);
    _cnHaloMintStops = BuildHaloStops(0x00, 0xFF, 0xC8);
    _cnHaloPinkStops = BuildHaloStops(0xFF, 0x00, 0x6E);
}

private SharpDX.Direct2D1.GradientStopCollection BuildHaloStops(byte r, byte g, byte b)
{
    return new SharpDX.Direct2D1.GradientStopCollection(
        RenderTarget,
        new SharpDX.Direct2D1.GradientStop[]
        {
            new SharpDX.Direct2D1.GradientStop { Position = 0.0f,
                Color = new SharpDX.Color4(r/255f, g/255f, b/255f, 0.30f) },  // core
            new SharpDX.Direct2D1.GradientStop { Position = 0.5f,
                Color = new SharpDX.Color4(r/255f, g/255f, b/255f, 0.18f) },  // mid
            new SharpDX.Direct2D1.GradientStop { Position = 1.0f,
                Color = new SharpDX.Color4(r/255f, g/255f, b/255f, 0.00f) },  // outer fade
        });
}
```

Add corresponding entries to `DisposeDx`:

```csharp
DisposeSolidBrush(ref _cnBgDeepDx);
DisposeSolidBrush(ref _cnBgPanelDx);
DisposeSolidBrush(ref _cnBgPanelHiDx);
DisposeSolidBrush(ref _cnGridMinorDx);
DisposeSolidBrush(ref _cnGridMajorDx);
DisposeSolidBrush(ref _cnAxisTickDx);
DisposeSolidBrush(ref _cnMintDx);
DisposeSolidBrush(ref _cnPinkDx);
DisposeSolidBrush(ref _cnMintDimDx);
DisposeSolidBrush(ref _cnPinkDimDx);
DisposeSolidBrush(ref _cnMintFillDx);
DisposeSolidBrush(ref _cnPinkFillDx);
DisposeSolidBrush(ref _cnMintGlowDx);
DisposeSolidBrush(ref _cnPinkGlowDx);
DisposeSolidBrush(ref _cnVioletDx);
DisposeSolidBrush(ref _cnVioletFillDx);
DisposeSolidBrush(ref _cnVioletLineDx);
DisposeSolidBrush(ref _cnAbsorbCyanDx);
DisposeSolidBrush(ref _cnAbsorbCyanGlowDx);
DisposeSolidBrush(ref _cnAbsorbPinkDx);
DisposeSolidBrush(ref _cnAbsorbPinkGlowDx);
DisposeSolidBrush(ref _cnInkPrimaryDx);
DisposeSolidBrush(ref _cnInkSecondaryDx);
DisposeSolidBrush(ref _cnInkDimDx);
if (_cnVignetteDx != null)   { _cnVignetteDx.Dispose();   _cnVignetteDx = null; }
if (_cnVignetteStops != null){ _cnVignetteStops.Dispose();_cnVignetteStops = null; }
if (_cnHaloCyanStops != null){ _cnHaloCyanStops.Dispose();_cnHaloCyanStops = null; }
if (_cnHaloMintStops != null){ _cnHaloMintStops.Dispose();_cnHaloMintStops = null; }
if (_cnHaloPinkStops != null){ _cnHaloPinkStops.Dispose();_cnHaloPinkStops = null; }
```

### 10.2 Vignette overlay (call last in OnRender, before HUD)

```csharp
// Draw subtle radial vignette over the chart area.
// Center transparent, edge ~10% black. Anchored to ChartPanel rect.
private void RenderVignette()
{
    if (_cnVignetteStops == null) return;

    float x = (float)ChartPanel.X;
    float y = (float)ChartPanel.Y;
    float w = (float)ChartPanel.W;
    float h = (float)ChartPanel.H;

    var center = new Vector2(x + w / 2f, y + h / 2f);
    float radiusX = w * 0.75f;   // gradient just past horizontal edges
    float radiusY = h * 0.85f;

    // Brush rebuilt per frame because panel size can change.
    using (var brush = new SharpDX.Direct2D1.RadialGradientBrush(
        RenderTarget,
        new SharpDX.Direct2D1.RadialGradientBrushProperties
        {
            Center               = center,
            GradientOriginOffset = new Vector2(0, 0),
            RadiusX              = radiusX,
            RadiusY              = radiusY,
        },
        _cnVignetteStops))
    {
        RenderTarget.FillRectangle(new RectangleF(x, y, w, h), brush);
    }
}
```

Call `RenderVignette()` near the bottom of `OnRender`, after the cells/levels but before the Score HUD and Chart Trader (so HUD chrome stays at full contrast).

### 10.3 Footprint cell with neon imbalance escalation

Drop-in replacement for the current cell loop body inside `OnRender`. Reads imbalance ratio, picks tier, paints accordingly.

```csharp
// Inside the foreach over fbar.Levels:
foreach (var kv in fbar.Levels)
{
    double px   = kv.Key;
    var    cell = kv.Value;
    float  yCenter = chartScale.GetYByValue(px);
    float  yTop    = yCenter - rowH / 2f;
    var    rect    = new RectangleF(xLeft, yTop, colW, rowH);

    // Diagonal imbalance ratios
    long diagBid = GetBid(fbar, px + tickSize);
    long diagAsk = GetAsk(fbar, px - tickSize);
    double buyRatio  = cell.AskVol > 0 ? (double)cell.AskVol / Math.Max(1, diagBid) : 0;
    double sellRatio = cell.BidVol > 0 ? (double)cell.BidVol / Math.Max(1, diagAsk) : 0;

    int tier = 0; bool isBuy = false;
    if (buyRatio >= sellRatio && buyRatio >= 4.0 && cell.AskVol >= 50) { tier = 4; isBuy = true; }
    else if (buyRatio >= sellRatio && buyRatio >= 3.0)                 { tier = 3; isBuy = true; }
    else if (buyRatio >= sellRatio && buyRatio >= 2.0)                 { tier = 2; isBuy = true; }
    else if (sellRatio >= 4.0 && cell.BidVol >= 50)                    { tier = 4; isBuy = false; }
    else if (sellRatio >= 3.0)                                         { tier = 3; isBuy = false; }
    else if (sellRatio >= 2.0)                                         { tier = 2; isBuy = false; }

    var fillBrush   = isBuy ? _cnMintFillDx : _cnPinkFillDx;
    var borderBrush = isBuy ? _cnMintDx     : _cnPinkDx;
    var glowBrush   = isBuy ? _cnMintGlowDx : _cnPinkGlowDx;

    // Tier 2: 1 px border @ 50% (achieved by drawing dim variant)
    // Tier 3: 1 px border @ 100% + 18% fill
    // Tier 4: 2 px border + 30% fill + 4 px outer glow
    if (tier == 2)
    {
        var dimBorder = isBuy ? _cnMintDimDx : _cnPinkDimDx;
        RenderTarget.DrawRectangle(rect, dimBorder, 1f);
    }
    else if (tier == 3)
    {
        RenderTarget.FillRectangle(rect, fillBrush);
        RenderTarget.DrawRectangle(rect, borderBrush, 1f);
    }
    else if (tier == 4)
    {
        // Outer glow: draw 4 concentric expanding rects with decreasing alpha.
        // Cheap and predictable on D2D 1.0 WindowRenderTarget.
        for (int g = 4; g >= 1; g--)
        {
            float pad = g;
            var glowRect = new RectangleF(rect.X - pad, rect.Y - pad,
                                          rect.Width + 2 * pad, rect.Height + 2 * pad);
            // Modulate alpha through draw width — a single brush, but stroke gets fainter.
            // For true alpha decay, allocate per-tier alpha brushes; this is one frame’s worth.
            RenderTarget.DrawRectangle(glowRect, glowBrush, 1f);
        }
        RenderTarget.FillRectangle(rect, fillBrush);
        RenderTarget.DrawRectangle(rect, borderBrush, 2f);
    }

    // Numerals — always primary ink, never tinted by side
    string label = string.Format("{0} · {1}", cell.BidVol, cell.AskVol);
    using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                       label, _cellFont, colW, rowH))
    {
        // Wider letter-spacing for the "interface" feel.
        // Direct2D character spacing API:
        var typo = new SharpDX.DirectWrite.Typography(NinjaTrader.Core.Globals.DirectWriteFactory);
        layout.SetTypography(typo, new SharpDX.DirectWrite.TextRange(0, label.Length));
        // Note: SetCharacterSpacing requires TextLayout1. Cast:
        var layout1 = layout.QueryInterface<SharpDX.DirectWrite.TextLayout1>();
        if (layout1 != null)
        {
            layout1.SetCharacterSpacing(0.5f, 0.5f, 0f,
                new SharpDX.DirectWrite.TextRange(0, label.Length));
        }

        RenderTarget.DrawTextLayout(new Vector2(xLeft, yTop), layout, _cnInkPrimaryDx);

        if (layout1 != null) layout1.Dispose();
        typo.Dispose();
    }
}
```

### 10.4 Stacked-imbalance violet band (drawn after the cell loop, before POC line)

```csharp
// After painting cells for this bar, scan for runs of 3+ consecutive extreme-tier
// cells on the same side. Wrap them in a violet band.
private void RenderStackedImbalanceZone(FootprintBar fbar, ChartScale scale,
                                        float xLeft, float colW, double tickSize)
{
    var sortedLevels = fbar.Levels.OrderBy(kv => kv.Key).ToList();
    int run = 0;
    bool runIsBuy = false;
    double runTop = double.NaN, runBot = double.NaN;

    foreach (var kv in sortedLevels)
    {
        var cell = kv.Value;
        long diagBid = GetBid(fbar, kv.Key + tickSize);
        long diagAsk = GetAsk(fbar, kv.Key - tickSize);
        double buyR  = cell.AskVol > 0 ? (double)cell.AskVol / Math.Max(1, diagBid) : 0;
        double sellR = cell.BidVol > 0 ? (double)cell.BidVol / Math.Max(1, diagAsk) : 0;

        bool extremeBuy  = buyR  >= 4.0 && cell.AskVol >= 50;
        bool extremeSell = sellR >= 4.0 && cell.BidVol >= 50;

        if ((extremeBuy && (run == 0 || runIsBuy)) ||
            (extremeSell && (run == 0 || !runIsBuy)))
        {
            if (run == 0) { runTop = kv.Key; runIsBuy = extremeBuy; }
            runBot = kv.Key;
            run++;
        }
        else
        {
            if (run >= 3) PaintViolet(scale, xLeft, colW, runTop, runBot);
            run = 0;
        }
    }
    if (run >= 3) PaintViolet(scale, xLeft, colW, runTop, runBot);
}

private void PaintViolet(ChartScale scale, float xLeft, float colW,
                         double topPx, double botPx)
{
    float yTop = scale.GetYByValue(topPx);
    float yBot = scale.GetYByValue(botPx);
    var rect = new RectangleF(xLeft - 2, Math.Min(yTop, yBot) - 2,
                              colW + 4, Math.Abs(yBot - yTop) + 4);
    RenderTarget.FillRectangle(rect, _cnVioletFillDx);
    RenderTarget.DrawRectangle(rect, _cnVioletLineDx, 1f);
}
```

### 10.5 Absorption halo with breathing pulse

```csharp
// One global stopwatch so all pulses share phase (no jitter when multiple fire).
private readonly System.Diagnostics.Stopwatch _pulseClock = System.Diagnostics.Stopwatch.StartNew();

// Track the active absorption signal (max 1 at a time). Set in OnBarUpdate
// when a high-confidence absorption fires; cleared after N bars or on opposite signal.
private struct ActiveAbsorption
{
    public int    BarIndex;
    public double Price;
    public bool   IsBuy;
    public DateTime Started;
}
private ActiveAbsorption? _activeAbsorb;

private void RenderAbsorptionHalo(ChartControl cc, ChartScale scale,
                                  int colW, float rowH)
{
    if (_activeAbsorb == null) return;
    var a = _activeAbsorb.Value;

    // Fade out after 12 bars
    if (CurrentBar - a.BarIndex > 12) { _activeAbsorb = null; return; }

    int xCenter = cc.GetXByBarIndex(ChartBars, a.BarIndex);
    float yCenter = scale.GetYByValue(a.Price);

    // Breathing pulse: alpha 20→40→20% over 2.5 s (0.4 Hz)
    double t = _pulseClock.Elapsed.TotalSeconds;
    double phase = (Math.Sin(2 * Math.PI * 0.4 * t) + 1.0) * 0.5; // 0..1
    float alpha  = (float)(0.20 + 0.20 * phase);                  // 0.20..0.40

    var stops = a.IsBuy ? _cnHaloCyanStops : _cnHaloPinkStops;
    if (stops == null) return;

    float radius = 8f + colW * 0.5f;
    using (var brush = new SharpDX.Direct2D1.RadialGradientBrush(
        RenderTarget,
        new SharpDX.Direct2D1.RadialGradientBrushProperties
        {
            Center               = new Vector2(xCenter, yCenter),
            GradientOriginOffset = new Vector2(0, 0),
            RadiusX              = radius,
            RadiusY              = radius * 0.7f,
        },
        stops))
    {
        brush.Opacity = alpha / 0.30f; // scale relative to stop max
        RenderTarget.FillEllipse(
            new SharpDX.Direct2D1.Ellipse(new Vector2(xCenter, yCenter),
                                          radius, radius * 0.7f),
            brush);
    }

    // Inner ring — solid 2 px
    var ringBrush = a.IsBuy ? _cnAbsorbCyanDx : _cnAbsorbPinkDx;
    RenderTarget.DrawEllipse(
        new SharpDX.Direct2D1.Ellipse(new Vector2(xCenter, yCenter),
                                      colW * 0.5f, rowH * 0.5f),
        ringBrush, 2f);
}
```

NinjaTrader's chart re-renders on each tick by default; the breathing animation will look smooth. If frame rate drops, force a refresh on a 60 ms timer (already used by the existing tick handlers).

### 10.6 GEX zero-gamma line with halo

```csharp
// Inside DEEP6GexLevels.cs OnRender, when drawing a GEX level:
private void RenderGexLevelWithGlow(ChartScale scale, float panelLeft, float panelRight,
                                    double price, SharpDX.Direct2D1.SolidColorBrush coreBrush,
                                    bool addGlow, bool dashed, float strokeWidth)
{
    float y = scale.GetYByValue(price);

    if (addGlow)
    {
        // Multi-pass concentric stroke for line glow.
        // 4 passes: width 8/6/4/2 px, alpha modulated via brush opacity.
        float[] widths = { 8f, 6f, 4f, 2f };
        float[] alphas = { 0.08f, 0.14f, 0.22f, 0.30f };
        for (int i = 0; i < widths.Length; i++)
        {
            coreBrush.Opacity = alphas[i];
            RenderTarget.DrawLine(new Vector2(panelLeft, y),
                                  new Vector2(panelRight, y),
                                  coreBrush, widths[i]);
        }
        coreBrush.Opacity = 1f; // restore
    }

    // Core line
    if (dashed)
        RenderTarget.DrawLine(new Vector2(panelLeft, y), new Vector2(panelRight, y),
                              coreBrush, strokeWidth, _dashStyle);
    else
        RenderTarget.DrawLine(new Vector2(panelLeft, y), new Vector2(panelRight, y),
                              coreBrush, strokeWidth);
}

// Usage:
// Zero gamma:    RenderGexLevelWithGlow(scale, x, xR, zg,    _cnAbsorbCyanDx, true,  false, 1.5f);
// Gamma flip:    RenderGexLevelWithGlow(scale, x, xR, gflip, _cnPinkDx,        false, true,  1.5f);
// Call wall:     RenderGexLevelWithGlow(scale, x, xR, cw,    _cnMintDx,        false, false, 2f);
// Put wall:      RenderGexLevelWithGlow(scale, x, xR, pw,    _cnPinkDx,        false, false, 2f);
```

### 10.7 Equity ribbon (top of chart)

```csharp
// Called from OnRender, top of chart panel.
private void RenderEquityRibbon(double currentEquity, double sessionStartEquity,
                                double athEquity, double atlEquity)
{
    float x = (float)ChartPanel.X;
    float y = (float)ChartPanel.Y + 4f;
    float w = (float)ChartPanel.W;
    float h = 18f;

    var rect = new RectangleF(x, y, w, h);
    RenderTarget.FillRectangle(rect, _cnBgPanelDx);

    bool isUp     = currentEquity >= sessionStartEquity;
    bool atATH    = currentEquity >= athEquity - 0.01;
    bool atATL    = currentEquity <= atlEquity + 0.01;
    var  side     = isUp ? _cnMintDx : _cnPinkDx;
    var  glow     = isUp ? _cnMintGlowDx : _cnPinkGlowDx;
    var  fill     = isUp ? _cnMintFillDx : _cnPinkFillDx;

    // Subtle area fill across the ribbon
    RenderTarget.FillRectangle(rect, fill);

    // Equity text
    string equityStr = string.Format("EQUITY  {0}{1:N0}",
                                     isUp ? "+" : "", currentEquity - sessionStartEquity);
    using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                       equityStr, _hudFont, 200f, h))
    {
        RenderTarget.DrawTextLayout(new Vector2(x + 12f, y), layout, side);
    }

    // ATH/ATL glow: 2 px outer halo on the value text
    if (atATH || atATL)
    {
        // Breathing halo at 0.3 Hz
        double t = _pulseClock.Elapsed.TotalSeconds;
        float a  = (float)(0.18 + 0.10 * (Math.Sin(2 * Math.PI * 0.3 * t) + 1.0) * 0.5);
        glow.Opacity = a;
        RenderTarget.DrawRectangle(
            new RectangleF(x + 8f, y - 2f, 200f, h + 4f), glow, 2f);
        glow.Opacity = 1f;
    }
}
```

### 10.8 Stop / target / position lines

```csharp
private void RenderPositionLines(ChartScale scale, float panelLeft, float panelRight,
                                 double entryPrice, double stopPrice, double targetPrice,
                                 bool isLong)
{
    var dirBrush = isLong ? _cnMintDx : _cnPinkDx;
    var dirGlow  = isLong ? _cnMintGlowDx : _cnPinkGlowDx;
    var oppBrush = isLong ? _cnPinkDx : _cnMintDx;

    // Position line: 2 px solid + 4 px outer halo
    float yEntry = scale.GetYByValue(entryPrice);
    dirGlow.Opacity = 0.25f;
    RenderTarget.DrawLine(new Vector2(panelLeft, yEntry),
                          new Vector2(panelRight, yEntry), dirGlow, 6f);
    dirGlow.Opacity = 1f;
    RenderTarget.DrawLine(new Vector2(panelLeft, yEntry),
                          new Vector2(panelRight, yEntry), dirBrush, 2f);

    // Stop: dashed, opposite color, 60% alpha
    if (!double.IsNaN(stopPrice))
    {
        float ySL = scale.GetYByValue(stopPrice);
        oppBrush.Opacity = 0.60f;
        RenderTarget.DrawLine(new Vector2(panelLeft, ySL),
                              new Vector2(panelRight, ySL), oppBrush, 1f, _dashStyle);
        oppBrush.Opacity = 1f;
    }

    // Target: dotted, same direction, 70%
    if (!double.IsNaN(targetPrice))
    {
        float yTP = scale.GetYByValue(targetPrice);
        dirBrush.Opacity = 0.70f;
        RenderTarget.DrawLine(new Vector2(panelLeft, yTP),
                              new Vector2(panelRight, yTP), dirBrush, 1f, _dashStyle);
        dirBrush.Opacity = 1f;
    }

    // Position chevron at right edge
    var chev = new SharpDX.Direct2D1.PathGeometry(NinjaTrader.Core.Globals.D2DFactory);
    using (var sink = chev.Open())
    {
        sink.BeginFigure(new Vector2(panelRight - 12f, yEntry - 6f),
                         SharpDX.Direct2D1.FigureBegin.Filled);
        sink.AddLine(new Vector2(panelRight - 4f, yEntry));
        sink.AddLine(new Vector2(panelRight - 12f, yEntry + 6f));
        sink.EndFigure(SharpDX.Direct2D1.FigureEnd.Closed);
        sink.Close();
    }
    RenderTarget.FillGeometry(chev, dirBrush);
    chev.Dispose();
}
```

### 10.9 OnRender call order (the ritual)

```csharp
protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
{
    if (IsInHitTest) return;
    if (RenderTarget == null || ChartBars == null) return;
    if (chartControl.Instrument == null) return;
    if (_cellFont == null) return;

    base.OnRender(chartControl, chartScale);
    RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

    // 1. Profile anchors (deep background)
    if (ShowProfileAnchors) RenderProfileAnchors(chartControl, chartScale, panelRight);

    // 2. Liquidity walls (background)
    if (ShowLiquidityWalls)  RenderLiquidityWalls(chartScale, panelRight);

    // 3. Cells + per-bar overlays (POC, VA, stacked imbalance band)
    //    [existing cell loop, with §10.3 + §10.4 patches applied]

    // 4. Signature halos (max 2 visible)
    RenderAbsorptionHalo(chartControl, chartScale, colW, rowH);

    // 5. Position / order lines (foreground over cells)
    if (HasOpenPosition) RenderPositionLines(...);

    // 6. Vignette overlay (subtle darkening over chart, under HUD)
    RenderVignette();

    // 7. Equity ribbon (top strip)
    RenderEquityRibbon(...);

    // 8. Score HUD (existing)
    if (ShowScoreHud)    RenderScoreHud(...);

    // 9. Chart Trader (top-right toolbar)
    if (ShowChartTrader) RenderChartTrader();
}
```

---

## 11. Why This Aesthetic Wins

A trader's eye, scanning 30,000 cells per session, calibrates to the chart's noise floor — when everything is colored, nothing is signal. **Cyberpunk Neon (restrained) raises the noise floor up to "almost nothing" and makes the rare signal arrive with operational weight**, so the trader feels each absorption halo or extreme-imbalance glow as the system speaking *with intent*, not as decoration. Premium SaaS aesthetics (Linear-style off-white, gentle blue accents, polite gray cells) optimize for the screenshot in a marketing deck; they fail at 2 AM Globex when the trader needs the chart to feel like equipment, not a dashboard. The two-voltage system (mint = buy, pink = sell, everything else drained) is a reduction discipline that maps directly to the binary nature of trading decisions — and the deep-indigo darkness with 10% vignette gives the screen the same "operating room" psychological cue that fighter HUDs and submarine sonar consoles have used for sixty years to keep operators in flow under stress.

---

### File references

- Existing render pipeline to integrate against: `/Users/teaceo/DEEP6/ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs:1178` (`OnRenderTargetChanged`), `:1295` (`OnRender`), `:1260` (`DisposeDx`).
- GEX overlay to retrofit with §10.6: `/Users/teaceo/DEEP6/ninjatrader/Custom/Indicators/DEEP6/DEEP6GexLevels.cs:484` (`OnRenderTargetChanged`), `:578-:625` (line draw block).
- Strategy lines/chevrons to add §10.7-§10.8 into: `/Users/teaceo/DEEP6/ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs`.
- Design vocabulary sources: `/Users/teaceo/DEEP6/dashboard/agents/footprint-orderflow-design-playbook.md:715-724` (the §15.6 cyberpunk-tasteful section that justifies the restraint), `/Users/teaceo/DEEP6/dashboard/agents/cross-discipline-hud-design-horizon.md:626-687` (FUI / Territory / GMUNK / Cantina lessons).
