I have enough. Now let me write the deliverable. The user wants a long-form markdown design proposal with concrete SharpDX code. I'll respond with the full design directly as my final message — no files to create, this is a design proposal.

---

# AESTHETIC OPTION E — "F1 TELEMETRY HUD" / PIT-WALL AESTHETIC
## A complete design direction for DEEP6 NinjaTrader 8

> *"Color is currency. Spend it only on state changes. Type is sector time. Layout is the pit wall."*

Identity codename: **DEEP6 / PITWALL.v1**  
Compatible with: `DEEP6Footprint.cs`, `DEEP6GexLevels.cs`, `DEEP6Strategy.cs` (drop-in brush + render block replacements; no schema changes).

---

## 1 · DESIGN PHILOSOPHY (One paragraph)

**This aesthetic is for a trader who is steering at 200 mph.** The pit wall has solved the hardest version of this problem — race engineers absorb 30+ telemetry channels in under 0.5 seconds and call a tire change with zero room for ambiguity. The DEEP6 trader is in the same loop: 44 microstructure signals, two prop accounts, a Kronos directional bias, and a footprint cell grid that updates at 1,000 callbacks/sec. The visual grammar of F1 broadcast (FOM 2018+ package by **MOOV**, Bedfordshire) and the engineering-room tools (**McLaren ATLAS**, **Mercedes "the Wall"**, **Ferrari D2RM**) are merged here with the **Boeing 787 PFD color codification** (FAR 25.1322 cyan/magenta/green/amber/red) — because aviation has spent 60 years deciding exactly what each color *means*. The result: a pure-black canvas where ≥85% of the frame is grayscale, the 15% that is colored is screaming meaningfully, sector-time logic codes every P&L cell, and personal-best states earn the magenta crown. It is not a "dark theme." It is a pit wall.

---

## 2 · COMPLETE COLOR PALETTE (verified hex, semantic-locked)

### 2.1 — Surface tier (the canvas — must be dead quiet)

| Token | Hex | RGBA | Use |
|---|---|---|---|
| `surface.0` (canvas) | `#000000` | 0,0,0,255 | Chart background. **True black.** Not `#0A0E14`. SpaceX Dragon convention. |
| `surface.1` (panel) | `#070A0E` | 7,10,14,255 | HUD pill backdrop (subtle lift only) |
| `surface.2` (raised) | `#0E1218` | 14,18,24,255 | Floating cards, score HUD |
| `surface.scrim` | `#000000 @ 78%` | 0,0,0,199 | Modal/overlay scrim |
| `grid.line` | `#1A1F26 @ 60%` | 26,31,38,153 | Almost invisible grid; 1px hairlines only |
| `grid.major` | `#262C36` | 38,44,54,255 | Sector dividers, panel separators |

### 2.2 — Aerospace semantic colors (Boeing 787 PFD grammar, locked)

| Role | Token | Hex | Discipline |
|---|---|---|---|
| **Selected / target** | `aero.cyan` | `#00E0FF` | Cyan: levels you've selected, profit targets, limit orders |
| **Autopilot / algo-commanded** | `aero.magenta` | `#FF38C8` | Magenta: Kronos predictions, AI-suggested levels, trailing stops |
| **Engaged / ON / nominal** | `aero.green` | `#3DDC84` | Green: live trade engaged, signal firing, healthy state |
| **Caution / abnormal** | `aero.amber` | `#FFB300` | Amber: approaching loss limit, stop level, gamma flip |
| **Warning / immediate action** | `aero.red` | `#FF3030` | Red: stop hit, drawdown breach, kill-switch armed |
| **Primary data / baseline** | `aero.white` | `#F2F4F8` | White: current values, scales, baseline text |

### 2.3 — F1 sector colors (performance grading — used for P&L, signal scores, lap-equivalents)

| Tier | Token | Hex | Meaning |
|---|---|---|---|
| **Personal best ever** | `f1.purple` | `#A100FF` | Best trade, best session, best signal score in history |
| **Improvement (green sector)** | `f1.green` | `#3DB868` | Better than your rolling baseline / winner trade |
| **Baseline (white)** | `f1.white` | `#E8EAED` | Equal to baseline / neutral / scratch |
| **Slower (yellow)** | `f1.yellow` | `#FFD600` | Worse than baseline / breakeven trade with slippage |
| **Loss (red)** | `f1.red` | `#FF1744` | Loss trade / failed signal |
| **Personal worst** | `f1.crimson` | `#7A0014` | All-time worst (drawdown breach record) |

### 2.4 — DEEP6 signature signal colors (telemetry-framed, aerospace-coded)

| Signal | Fill | Frame brackets | Notes |
|---|---|---|---|
| **Absorption** | `aero.cyan` `#00E0FF` @ 22% | `#00E0FF` @ 100%, 1.5px | Cyan = "selected/target" — the signal you act on. Bracket framing: `[` `]` |
| **Exhaustion** | `aero.magenta` `#FF38C8` @ 22% | `#FF38C8` @ 100%, 1.5px | Magenta = "autopilot armed" — Kronos converging. Bracket framing: `[` `]` |
| **Stacked imbalance** | `aero.amber` `#FFB300` → escalate to cyan/magenta | hairline `#FFB300` | Amber base, escalates color per stack count |
| **Liquidity wall (bid)** | `#0099CC @ 35%` | none | Cyan-tinted, sits behind cells |
| **Liquidity wall (ask)** | `#CC0099 @ 35%` | none | Magenta-tinted (mirrors absorption/exhaustion duality) |

### 2.5 — Footprint cells (telemetry data block aesthetic)

| Element | Fill | Text |
|---|---|---|
| Bid-side cell rest | `#000000` (transparent) | `#9BA3AE` (mid-grey, dim — *no color until imbalance*) |
| Ask-side cell rest | `#000000` (transparent) | `#9BA3AE` |
| Buy imbalance ×3 | `#FFB300 @ 18%` (amber base) | `#F2F4F8` |
| Buy imbalance ×5 (escalation) | `#00E0FF @ 28%` (cyan — selected) | `#F2F4F8` bold |
| Sell imbalance ×3 | `#FFB300 @ 18%` | `#F2F4F8` |
| Sell imbalance ×5 (escalation) | `#FF38C8 @ 28%` (magenta) | `#F2F4F8` bold |
| Stacked imbalance zone | `#FFB300 @ 12%` overlay | label in `#FFB300` |

### 2.6 — Levels (POC, VAH/VAL, GEX) — aerospace conventions

| Level | Color | Style | Rationale |
|---|---|---|---|
| Bar POC (current) | `f1.purple` `#A100FF` | 2px solid, full bar width | Purple = "best lap of the bar" — maps perfectly |
| Session POC | `f1.purple` `#A100FF` | 1.5px solid, dashed at chart-right | Best lap of the session |
| VAH / VAL | `aero.white` `#F2F4F8 @ 70%` | 1px solid | Baseline scale marks |
| Naked POC | `f1.purple @ 50%` `#A100FF` | 1px dashed | Faded "best lap" |
| Prior-day POC | `f1.yellow` `#FFD600` | 1.5px solid | Yesterday's best — "P-1 sector time" |
| Prior-week POC | `#E5C24A` (deep yellow) | 1.5px dotted | Older sector time, deeper amber |
| GEX zero-gamma | `aero.cyan` `#00E0FF` | 2px solid | Selected/target — the level the market gravitates to |
| GEX flip | `aero.magenta` `#FF38C8` | 1.5px **dashed** | Autopilot armed — regime change pending |
| Call wall | `aero.amber` `#FFB300` | 2px solid + 6px band @ 20% | Safety limit, top |
| Put wall | `aero.amber` `#FFB300` | 2px solid + 6px band @ 20% | Safety limit, bottom |

### 2.7 — Text tokens

| Role | Hex | Notes |
|---|---|---|
| `text.primary` | `#F2F4F8` | Numbers in cells, KPIs, hero values |
| `text.secondary` | `#9BA3AE` | Labels, axis ticks, dim chrome |
| `text.tertiary` | `#5A636E` | Disabled / placeholder |
| `text.lime` (accent) | `#9FFF00` | RARE — only for telemetry "live ticking" indicator dot, log.info equivalent |
| `text.shadow` | `#000000 @ 90%` | 1px outline halo on all overlay text (fighter-jet HMD rule) |

### 2.8 — Strategy P&L states (sector-color-coded directly)

| State | Color | Trigger |
|---|---|---|
| Personal-best trade | `f1.purple` `#A100FF` | New all-time R-multiple high |
| Winner | `f1.green` `#3DB868` | +R closed trade |
| Scratch / breakeven | `f1.white` `#E8EAED` | ±0.2R |
| Slow win (slippage) | `f1.yellow` `#FFD600` | <0.5R win after target |
| Loser | `f1.red` `#FF1744` | −R closed trade |
| Drawdown record | `f1.crimson` `#7A0014` | New session/day worst |

### 2.9 — Working order states (Boeing aerospace mapping)

| Order type | Color | Style |
|---|---|---|
| Limit (selected target) | `aero.cyan` `#00E0FF` | Solid 1.5px line + cyan filled triangle marker |
| Stop (caution / safety) | `aero.amber` `#FFB300` | Dashed 1.5px line + amber striped band (red-amber barber pole at activation) |
| Trail (autopilot) | `aero.magenta` `#FF38C8` | Dashed 1.5px line + small magenta circle that moves bar-to-bar |
| Bracket OCO group | `#262C36` connector hairline | Dotted 1px line tying limit ↔ stop together |

### 2.10 — Transient flashes (mode-change annunciation, 787 convention)

| Event | Color | Pattern |
|---|---|---|
| Signal fired (this bar) | `f1.purple` border | 3 flashes @ 2Hz, then solid 800ms, then fade to 35% |
| Position opened | `aero.green` border | 1 pulse @ 1Hz |
| Position closed | `aero.cyan` border | 1 pulse @ 1Hz |
| Stop hit | `aero.red` border | 5 flashes @ 4Hz |
| Kronos bias flip | `aero.magenta` border | 3 flashes @ 2Hz |

---

## 3 · TYPOGRAPHY (telemetry-feeling)

### 3.1 — Font stack (with NT8-available fallbacks)

| Role | Primary | Fallback (NT8 default) | Notes |
|---|---|---|---|
| **Cell numerals** (footprint bid x ask) | `JetBrains Mono` (tabular) | `Consolas` | Tabular figures *required* — numbers must not dance. Already used in code as `Consolas`. |
| **Chrome / labels** (panel headers, pill labels) | `Bahnschrift Condensed` | `Segoe UI Semibold` | Compact, geometric, F1-broadcast-feel. Bahnschrift ships with Win10+. |
| **Section headers** (caps tracked) | `Bahnschrift Condensed Bold` | `Segoe UI Bold` | ALL CAPS, letter-spacing +80 |
| **KPI / hero metrics** | `Bahnschrift SemiBold` | `Segoe UI Bold` | LARGE — 28-44pt for the score readout |
| **Telemetry pill values** | `JetBrains Mono Bold` | `Consolas Bold` | Tabular, 10-12pt |

### 3.2 — Type scale (the 0.5-second rule)

| Use | pt | Weight | Color |
|---|---|---|---|
| Hero KPI (Score, Net P&L) | 32 | Bold | `text.primary` |
| Pill value (Δ, Vol, Conf) | 13 | Bold | sector-coded |
| Pill label ("Δ" "VOL" "POC") | 8 | Regular | `text.tertiary` ALL CAPS |
| Cell numeral (10 x 14) | 9 | Regular | `text.primary` or `text.secondary` |
| Section header ("PIT WALL" "ORDER FLOW") | 9 | Bold | `text.tertiary` ALL CAPS, +80 tracking |
| Annotation / tooltip | 10 | Regular | `text.primary` |
| Axis labels | 8 | Regular | `text.tertiary` |

### 3.3 — The 0.5-second rule

Every primary readout must be parseable in **one saccade**:
- Tabular numerals only (no proportional figures — `1.342` and `1.842` must align)
- Maximum 4 numeric chars in a hero cell (use K/M scaling)
- Color does the alerting — text is just data
- 1px black halo on every overlay glyph (fighter HMD rule, MIL-STD adjacent)

---

## 4 · F1 TELEMETRY MECHANICS PORTED TO TRADING

### 4.1 — Sector-time color coding for trade P&L

```
TRADE LOG            (sector colors — purple is best-ever)
─────────────────────────────────────────────────────────
#0142  09:31:14  +1.84R  ESL→ABS  ████████  PURPLE   (PB)
#0143  09:42:08  +0.92R  EXH→TGT  ███████   GREEN
#0144  09:55:21  +0.04R  scratch  ██        WHITE
#0145  10:11:49  −0.31R  stop      ██████   YELLOW   (slow)
#0146  10:24:02  −1.00R  STOP HIT  ████████ RED
─────────────────────────────────────────────────────────
```
- **Purple** triggers when current trade R-multiple > prior session max.
- **Yellow** triggers when winning but below target slippage threshold.
- The bar-fill width is proportional to |R-multiple|.

### 4.2 — Driver delta gauge (portfolio vs benchmark)

A horizontal pill, centered at zero, extending left (red) or right (green) showing **net P&L delta vs day's expectancy**:

```
          ▼
[████─────│─────────] −0.42R   ← red half active
          0
          ▼
[─────────│───███───] +0.18R   ← green half active
          0
                ▼
[─────────│────────████] +0.91R  PB lead glow
          0
```
- Reset at session start.
- Magenta "PB lead" glow if delta exceeds session record.

### 4.3 — Position-change arrows (strategy ranking)

Each strategy in the strategy list gets a 1-tick rank-change arrow:

```
RANK  STRATEGY              P&L     Δrank
 1    DEEP6/Absorption     +2.40R   ↑1   ← cyan arrow
 2    DEEP6/Exhaustion     +1.80R   −    ← grey dash (no change)
 3    DEEP6/Delta Surge    +0.62R   ↓2   ← red arrow
 4    DEEP6/GEX Pin        +0.10R   ↑3   ← cyan arrow (big jump = magenta)
```

### 4.4 — Tire-compound circles (account/risk state)

Small filled disc with 1px white border, character glyph centered:

```
 ●S   = Soft   = aggressive risk (1R/trade, 4 max)         red disc       #FF1744
 ●M   = Medium = standard risk (0.5R, 6 max)               yellow disc    #FFD600
 ●H   = Hard   = conservative (0.25R, 8 max)               white disc     #F2F4F8
 ●W   = Wet    = scaled-down (post-loss circuit breaker)   blue disc      #00B4FF
 ●OFF = no trades (kill switch)                             grey disc     #5A636E
```

Renders next to account name in header strip.

### 4.5 — Lap-time tape (vertical price ladder)

```
       │  21458.50 ─────  ┐
       │  21458.25         │
       │  21458.00 ──VAH── │  scrolling prices @ 9pt grey
       │  21457.75         │
       │  21457.50  ▶      │   ← current price 3x larger,
   ┌───┤                    │     in cyan box, with halo
   │ 21457.25 ◀┤           │
   └───┤                    │
       │  21457.00 ──VAL── │
       │  21456.75         │
       │  21456.50         │
       │  21456.25 ──POC── │  purple line
       └────────────────────┘
```
- 9pt prices scroll smoothly upward as price rises.
- Current price **3x larger**, cyan-bordered black box.
- VAH/VAL/POC inline as labeled tick marks.

### 4.6 — DRS/ERS-style toggle indicators (LED on/off)

```
[ ABS ]  [ EXH ]  [ DLT ]  [ GEX ]  [ KRN ]
  ●        ●        ○        ●        ●
green    green    grey     green   magenta
 ON       ON       OFF      ON      AUTO
```
- Filled green disc = engaged (signal armed)
- Empty grey ring = disabled
- Filled magenta = AI-controlled (Kronos auto-toggle)
- Click cycles state.

---

## 5 · FOOTPRINT CELL RENDERING RECIPE (telemetry-cell aesthetic)

### 5.1 — Cell anatomy

```
┌──────────────────┬──────────────────┐   ← 1px grid.major divider
│   12   x    34   │                  │   ← bid x ask, mono 9pt
│  grey   white    │     PRICE        │
└──────────────────┴──────────────────┘
       bid              ask              ← rest state: NO color, just grey numbers
```

### 5.2 — Imbalance escalation (aerospace amber → cyan/magenta)

```
LEVEL   ratio    fill                       text
─────   ─────    ──────────────────────     ──────
×3      3.0     ▓ amber  #FFB300 @ 18%     white 9pt
×5      5.0     ▓ cyan   #00E0FF @ 28%     white 9pt BOLD   (buy escalation)
×5      5.0     ▓ magenta #FF38C8 @ 28%    white 9pt BOLD   (sell escalation)
×8+     8.0     ▓ + bracket frame [ ]      + label badge   (extreme)
```

### 5.3 — POC marked with "best lap" purple line

```
─────────────────────────────────  yPoc - 1
█████████████████████████████████  yPoc      f1.purple #A100FF, 2px
─────────────────────────────────  yPoc + 1
```
Extends the **full bar paint width**. No fill on cell — the line *crowns* it.

### 5.4 — Stacked-imbalance zones (labeled telemetry sectors)

```
         ┌─────────────────┐
         │                 │  amber #FFB300 @ 12% fill
         │  3 stacked      │  hairline #FFB300 border
   PRICE │  bid imbalance  │  label top-right: "S3·BID" caps
         │                 │
         └─────────────────┘
```

### 5.5 — Absorption signature (cyan box with framing brackets)

```
[─┐                              ┌─]    ← 6px corner brackets
   │   🟦   ABSORPTION ▲         │       cyan #00E0FF
   │                              │
   │   bid x ask  bid x ask       │       cell contents preserved
   │      125 x 4    98 x 2       │
   │                              │
   │   Δ−119  WICK 47%            │      label strip bottom
[─┘                              └─]    ← 6px corner brackets
   ↑                              ↑
   filled cyan #00E0FF @ 22%
```

### 5.6 — Exhaustion signature (magenta box with framing brackets)

Identical layout, color palette swap:
- Bracket / border: `aero.magenta #FF38C8`
- Fill: `#FF38C8 @ 22%`
- Top label: `EXHAUSTION ▼` (or ▲)
- Bottom strip: `Δ+184  REJ 62%`

### 5.7 — The "framing brackets" trick

The brackets are NOT a full rectangle. They're four **L-shaped corner pieces** drawn 6px on each leg, 1.5px stroke. This gives a *targeting reticle* feel (Forza/Gran Turismo HUD), not a "rectangle around the thing" feel — much more telemetry, much less PowerPoint.

---

## 6 · HEADER STRIP — PIT WALL TELEMETRY STRIP (signature element)

The signature visual element. A continuous strip across the top of the chart, ~24px tall, holding sector-time-style pills.

### 6.1 — Layout

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ NQ ●S│Δ −1240│VOL 142K│POC 21457.25│IB 4.2x│KRN +0.62│CONF 0.84│PnL +1.84R│#23 ↑2 │
│ symbol │  →     →        →           →       →         →        purple    arrow   │
│ tire    delta  volume    poc          imbal   kronos   conf      sector   rank   │
│ compound       (mono)    (mono)       (amber  bias    (sector   (purple = PB)     │
│                                       if hot) (cyan/mag) coded)                    │
└─────────────────────────────────────────────────────────────────────────────────────┘
   24px tall, full chart width, surface.1 #070A0E backdrop, hairline grid.major divider below
```

### 6.2 — Pill anatomy

```
┌───────────────┐
│ POC  21457.25 │   ← label 8pt grey caps, value 13pt mono bold white
└───────────────┘    background: surface.2 #0E1218 @ 90%
                      6px horizontal padding, 4px vertical
                      no border (whitespace separates)
                      sector color tints LEFT EDGE 2px when state active:
                      
┌█──────────────┐
│█POC  21457.25 │   ← purple left edge if PB-lap-equivalent
└█──────────────┘    cyan if at selected target, etc.
```

### 6.3 — Pills by left-to-right priority

| # | Pill | Format | Color logic |
|---|---|---|---|
| 1 | Symbol + tire | `NQ ●S` | tire compound disc |
| 2 | Δ (running delta) | `Δ −1240` | sector-coded magnitude (>±2000 = purple/red) |
| 3 | VOL (bar vol) | `VOL 142K` | amber if >2× ADV |
| 4 | POC | `POC 21457.25` | purple left edge if = session POC |
| 5 | IB (imbalance ratio) | `IB 4.2x` | amber ≥3, cyan ≥5 (buy), magenta ≥5 (sell) |
| 6 | KRN (Kronos bias) | `KRN +0.62` | magenta (autopilot color) |
| 7 | CONF (composite) | `CONF 0.84` | sector colors by tier (A/B/C) |
| 8 | PnL | `PnL +1.84R` | sector colors |
| 9 | Trade# + rank delta | `#23 ↑2` | arrow color = direction |

---

## 7 · GEX LEVEL RENDERING (aerospace level lines)

### 7.1 — Line style table

| Level | Color | Stroke | Pattern | Label pill |
|---|---|---|---|---|
| Zero gamma | `aero.cyan #00E0FF` | 2px | solid | cyan-edge pill, "ZG 21450" |
| Gamma flip | `aero.magenta #FF38C8` | 1.5px | dashed (8,4) | magenta-edge pill, "FLIP 21425" |
| Call wall | `aero.amber #FFB300` | 2px solid + 6px band @ 20% | solid, with band | amber pill, "CW 21500" |
| Put wall | `aero.amber #FFB300` | 2px solid + 6px band @ 20% | solid, with band | amber pill, "PW 21400" |
| Positive gex node | `aero.green #3DDC84 @ 60%` | 1px | dotted | small green pill |
| Negative gex node | `aero.red #FF3030 @ 60%` | 1px | dotted | small red pill |

### 7.2 — Label pills (right side of chart)

```
                                              ┌───────────────┐
─────────────────────────────────────────────│█  CW   21500  │   amber edge
                                              └───────────────┘
                                              ┌───────────────┐
═════════════════════════════════════════════│█  ZG   21450  │   cyan edge (target convention)
                                              └───────────────┘
─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│█  FLIP 21425  │   magenta edge (autopilot)
                                              └───────────────┘
─────────────────────────────────────────────│█  PW   21400  │   amber edge
                                              └───────────────┘
```
All labels: monospace 10pt, vertical-center on level, 8px right margin from panel edge.

---

## 8 · STRATEGY VISUALIZATION (pit wall P&L)

### 8.1 — Equity ribbon

A continuous horizontal strip at the **bottom of the chart panel**, 18px tall, showing the session's trade-by-trade R-multiples as colored cells in chronological order:

```
SESSION RIBBON  ─────────────────────────────────────
[█][█][░][▒][░][░][█][▓][░][▒][▒][░][░][░][░][░][░]
 G  G  W  Y  W  W  P  G  W  R  R  W  W  W  W  W  W
                       ↑ purple = personal best of session
```
- One cell per trade, width = bar-paint-width.
- Color = sector grade.
- Hover (or chart-trader click) reveals trade tooltip.
- A faint hairline at zero divides "good half / bad half" of the strip.

### 8.2 — Working orders on chart

```
                                     │
                                     │═══ ▼ LMT 21462 (cyan)        ◀── target
                                     │
─── price action ───●●●●●●●          │
                                     │
                                     │─ ─ ○ TRL 21455 (magenta)     ◀── trailing
                                     │
══════════════════════════════════════│▓▓▓ ▲ STP 21450 (amber band) ◀── stop, with safety stripe
                                     │
```
- Limit: solid cyan line + filled cyan downward triangle on right.
- Trail: dashed magenta line + open magenta circle that moves bar-to-bar.
- Stop: dashed amber line + 4px amber barber-pole stripe band at activation distance.

### 8.3 — Position marker ("fastest sector" overlay)

When in a position, the entry bar gets a **left-edge purple chevron** (3 stacked `>` glyphs) and a faint vertical purple hairline back to the entry candle. Indicates "this is where the lap was set."

### 8.4 — R/R zones (labeled telemetry sectors)

Behind the price between entry and target/stop:
```
████████████████  green @ 8%, label "TGT 2.0R"  (top zone)
                  
─────●───── entry
                  
████████████████  red @ 8%,   label "STP −1.0R"  (bottom zone)
```

---

## 9 · POSITION ARROWS / TIRE / DRS — concrete implementations

### 9.1 — Position-change arrow glyphs

Drawn with `RenderTarget.DrawGeometry` using a triangle path:

```
↑1 (small move up)  : cyan filled triangle, 6×8px, label "1" mono 8pt
↑3 (big move up)    : magenta filled triangle, 8×10px (PB territory), label "3"
↓1                  : amber filled triangle (caution color for slipping)
↓3+                 : red filled triangle
−   (no change)     : grey hairline dash, 6px wide, no label
```

### 9.2 — Tire compound disc

```
SharpDX recipe:
  - Ellipse(center, 6, 6) filled with compound color
  - Ellipse(center, 6, 6) stroked with white #F2F4F8 @ 80%, 1px
  - DrawText centered, 7pt Bahnschrift Bold, color = contrasting
  - Background pad: 8px circular halo, parent color @ 20%, blurred
```

### 9.3 — DRS/ERS toggle (LED indicator)

```
ON state  :  filled disc, glow halo (parent color @ 30%, 4px blur)
OFF state :  hollow ring, 1.5px stroke, no fill, no glow
AUTO state:  filled magenta disc, slow pulse 1Hz between 70%-100% opacity
```

---

## 10 · ASCII FULL-CHART MOCKUP

```
╔════════════════════════════════════════════════════════════════════════════════════════════╗
║ NQ ●S│Δ−1240│VOL 142K│POC 21457.25│IB 4.2x│KRN +0.62│CONF 0.84│PnL +1.84R│#23 ↑2          ║  ← PIT WALL strip 24px
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                            ║
║ [ABS][EXH][DLT][GEX][KRN]                                              ┌───────────────┐  ║
║   ●    ●    ○    ●    ●                                                │█ CW    21500 │  ║
║                                                                         └───────────────┘  ║
║                                                                                            ║
║                          [─┐                                            ┌──────────────┐  ║
║                            │ ABSORPTION ▲                          ════│█ ZG    21450 │══║
║                            │  125 x 4                                   └──────────────┘  ║
║                            │  Δ−119  WICK 47%                                              ║
║                          [─┘                                            ┌─ ─ ─ ─ ─ ─ ─┐  ║
║                                                                       ─ │█ FLIP  21425│─ ║
║          ████████████████████████████ POC 21457.25 (purple line)        └─ ─ ─ ─ ─ ─ ─┘  ║
║                                                                                            ║
║   ●─────●●●─────●●●●●● price action                                     ┌──────────────┐  ║
║                                                                         │█ PW    21400 │  ║
║                                  ▓▓▓▓▓ stacked imbal zone S3·BID ▓▓     └──────────────┘  ║
║                                                                                            ║
║                                          │═══ ▼ LMT 21462                                  ║
║                                          │                                                 ║
║                                          │─ ─ ○ TRL 21455 (mag)                            ║
║                                          │                                                 ║
║                                          │▓▓▓ ▲ STP 21450 (amb)                            ║
║                                                                                            ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ SESSION RIBBON [█][█][░][▒][░][█][▓][░][▒][░][░][░][░][░]                                  ║  ← equity ribbon 18px
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ DEEP6/Absorption  +2.40R ↑1  │  DEEP6/Exhaustion  +1.80R −  │  DEEP6/Delta  +0.62R ↓2     ║  ← strategy rank strip
╚════════════════════════════════════════════════════════════════════════════════════════════╝
```

---

## 11 · READY-TO-DROP SHARPDX CODE

All snippets compatible with the existing `DEEP6Footprint.cs` structure (matches the `_*Dx` brush field naming, `OnRenderTargetChanged` cache pattern, and `MakeFrozenBrush` helper already in the file at lines 987–989, 1178–1252).

### 11.1 — Brush field declarations (add near line 786, with existing `_anchorPocDx` etc.)

```csharp
// ──── F1 PITWALL palette (Aesthetic Option E) ────
// Aerospace semantic (Boeing 787 PFD grammar)
private SharpDX.Direct2D1.SolidColorBrush _pwAeroCyanDx;     // #00E0FF  selected/target/limit/zg
private SharpDX.Direct2D1.SolidColorBrush _pwAeroMagentaDx;  // #FF38C8  autopilot/algo/trail/flip/exhaust
private SharpDX.Direct2D1.SolidColorBrush _pwAeroGreenDx;    // #3DDC84  engaged/on/nominal
private SharpDX.Direct2D1.SolidColorBrush _pwAeroAmberDx;    // #FFB300  caution/stop/walls
private SharpDX.Direct2D1.SolidColorBrush _pwAeroRedDx;      // #FF3030  warn/stopHit
private SharpDX.Direct2D1.SolidColorBrush _pwAeroWhiteDx;    // #F2F4F8  primary text

// F1 sector colors (performance grading)
private SharpDX.Direct2D1.SolidColorBrush _pwSectorPurpleDx; // #A100FF  best ever
private SharpDX.Direct2D1.SolidColorBrush _pwSectorGreenDx;  // #3DB868  improvement/winner
private SharpDX.Direct2D1.SolidColorBrush _pwSectorWhiteDx;  // #E8EAED  baseline
private SharpDX.Direct2D1.SolidColorBrush _pwSectorYellowDx; // #FFD600  slower
private SharpDX.Direct2D1.SolidColorBrush _pwSectorRedDx;    // #FF1744  loss

// Tinted fills (lower-alpha versions for cell backgrounds)
private SharpDX.Direct2D1.SolidColorBrush _pwAbsFillDx;      // cyan @ 22%
private SharpDX.Direct2D1.SolidColorBrush _pwExhFillDx;      // magenta @ 22%
private SharpDX.Direct2D1.SolidColorBrush _pwAmberFillDx;    // amber @ 18% (×3 imbal)
private SharpDX.Direct2D1.SolidColorBrush _pwCyanFillDx;     // cyan @ 28% (×5 buy escalation)
private SharpDX.Direct2D1.SolidColorBrush _pwMagFillDx;      // magenta @ 28% (×5 sell escalation)
private SharpDX.Direct2D1.SolidColorBrush _pwStackZoneDx;    // amber @ 12% (stacked-imbal zone)

// Surfaces
private SharpDX.Direct2D1.SolidColorBrush _pwSurface0Dx;     // #000000 canvas
private SharpDX.Direct2D1.SolidColorBrush _pwSurface1Dx;     // #070A0E pill backdrop
private SharpDX.Direct2D1.SolidColorBrush _pwSurface2Dx;     // #0E1218 raised
private SharpDX.Direct2D1.SolidColorBrush _pwGridLineDx;     // #1A1F26 @ 60%
private SharpDX.Direct2D1.SolidColorBrush _pwGridMajorDx;    // #262C36

// Text
private SharpDX.Direct2D1.SolidColorBrush _pwTextPrimaryDx;   // #F2F4F8
private SharpDX.Direct2D1.SolidColorBrush _pwTextSecondaryDx; // #9BA3AE
private SharpDX.Direct2D1.SolidColorBrush _pwTextTertiaryDx;  // #5A636E
private SharpDX.Direct2D1.SolidColorBrush _pwTextHaloDx;      // #000000 @ 90% (1px outline)

// Telemetry fonts
private TextFormat _pwPillValueFont;   // JetBrains Mono Bold 13pt (fallback Consolas)
private TextFormat _pwPillLabelFont;   // Bahnschrift Condensed 8pt CAPS (fallback Segoe UI)
private TextFormat _pwHeroFont;        // Bahnschrift SemiBold 28pt
private TextFormat _pwCellFont;        // Consolas 9pt (already exists as _cellFont — reuse)

// Stroke styles (cached — Direct2D allocation discipline)
private SharpDX.Direct2D1.StrokeStyle _pwDashStyle;    // for magenta flip / trail
private SharpDX.Direct2D1.StrokeStyle _pwDottedStyle;  // for naked POC / gex nodes
```

### 11.2 — Brush allocation (extend `OnRenderTargetChanged`, line 1178+)

```csharp
public override void OnRenderTargetChanged()
{
    base.OnRenderTargetChanged();
    if (RenderTarget == null) return;

    // ... existing brush allocations ...

    // ──── F1 PITWALL palette ────
    _pwAeroCyanDx     = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0xE0, 0xFF))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwAeroMagentaDx  = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x38, 0xC8))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwAeroGreenDx    = MakeFrozenBrush(Color.FromArgb(255, 0x3D, 0xDC, 0x84))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwAeroAmberDx    = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0xB3, 0x00))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwAeroRedDx      = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x30, 0x30))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwAeroWhiteDx    = MakeFrozenBrush(Color.FromArgb(255, 0xF2, 0xF4, 0xF8))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

    _pwSectorPurpleDx = MakeFrozenBrush(Color.FromArgb(255, 0xA1, 0x00, 0xFF))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwSectorGreenDx  = MakeFrozenBrush(Color.FromArgb(255, 0x3D, 0xB8, 0x68))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwSectorWhiteDx  = MakeFrozenBrush(Color.FromArgb(255, 0xE8, 0xEA, 0xED))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwSectorYellowDx = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0xD6, 0x00))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwSectorRedDx    = MakeFrozenBrush(Color.FromArgb(255, 0xFF, 0x17, 0x44))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

    _pwAbsFillDx     = MakeFrozenBrush(Color.FromArgb(56,  0x00, 0xE0, 0xFF))   // cyan @ 22%
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwExhFillDx     = MakeFrozenBrush(Color.FromArgb(56,  0xFF, 0x38, 0xC8))   // magenta @ 22%
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwAmberFillDx   = MakeFrozenBrush(Color.FromArgb(46,  0xFF, 0xB3, 0x00))   // amber @ 18%
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwCyanFillDx    = MakeFrozenBrush(Color.FromArgb(71,  0x00, 0xE0, 0xFF))   // cyan @ 28%
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwMagFillDx     = MakeFrozenBrush(Color.FromArgb(71,  0xFF, 0x38, 0xC8))   // magenta @ 28%
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwStackZoneDx   = MakeFrozenBrush(Color.FromArgb(31,  0xFF, 0xB3, 0x00))   // amber @ 12%
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

    _pwSurface0Dx     = MakeFrozenBrush(Color.FromArgb(255, 0x00, 0x00, 0x00))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwSurface1Dx     = MakeFrozenBrush(Color.FromArgb(255, 0x07, 0x0A, 0x0E))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwSurface2Dx     = MakeFrozenBrush(Color.FromArgb(230, 0x0E, 0x12, 0x18))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwGridLineDx     = MakeFrozenBrush(Color.FromArgb(153, 0x1A, 0x1F, 0x26))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwGridMajorDx    = MakeFrozenBrush(Color.FromArgb(255, 0x26, 0x2C, 0x36))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

    _pwTextPrimaryDx   = _pwAeroWhiteDx;
    _pwTextSecondaryDx = MakeFrozenBrush(Color.FromArgb(255, 0x9B, 0xA3, 0xAE))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwTextTertiaryDx  = MakeFrozenBrush(Color.FromArgb(255, 0x5A, 0x63, 0x6E))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;
    _pwTextHaloDx      = MakeFrozenBrush(Color.FromArgb(230, 0x00, 0x00, 0x00))
                          .ToDxBrush(RenderTarget) as SharpDX.Direct2D1.SolidColorBrush;

    // Fonts (allocate ONCE — never per-frame; matches existing _hudFont/_cellFont pattern)
    _pwPillValueFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
        "Consolas", FontWeight.Bold, FontStyle.Normal, 13f)
    {
        TextAlignment      = TextAlignment.Leading,
        ParagraphAlignment = ParagraphAlignment.Center
    };
    _pwPillLabelFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
        "Bahnschrift Condensed", FontWeight.Regular, FontStyle.Normal, 8f)
    {
        TextAlignment      = TextAlignment.Leading,
        ParagraphAlignment = ParagraphAlignment.Center
    };
    _pwHeroFont = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory,
        "Bahnschrift SemiBold", FontWeight.SemiBold, FontStyle.Normal, 28f)
    {
        TextAlignment      = TextAlignment.Center,
        ParagraphAlignment = ParagraphAlignment.Center
    };

    // Stroke styles (Direct2D recommends caching, not per-frame allocation)
    var ssDash = new StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Custom };
    _pwDashStyle = new SharpDX.Direct2D1.StrokeStyle(
        RenderTarget.Factory, ssDash, new float[] { 4f, 2f });

    var ssDot = new StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Custom };
    _pwDottedStyle = new SharpDX.Direct2D1.StrokeStyle(
        RenderTarget.Factory, ssDot, new float[] { 1f, 2f });
}
```

Add matching disposes to your existing `DisposeDx` method:

```csharp
DisposeSolidBrush(ref _pwAeroCyanDx);
DisposeSolidBrush(ref _pwAeroMagentaDx);
DisposeSolidBrush(ref _pwAeroGreenDx);
DisposeSolidBrush(ref _pwAeroAmberDx);
DisposeSolidBrush(ref _pwAeroRedDx);
DisposeSolidBrush(ref _pwAeroWhiteDx);
DisposeSolidBrush(ref _pwSectorPurpleDx);
DisposeSolidBrush(ref _pwSectorGreenDx);
DisposeSolidBrush(ref _pwSectorWhiteDx);
DisposeSolidBrush(ref _pwSectorYellowDx);
DisposeSolidBrush(ref _pwSectorRedDx);
DisposeSolidBrush(ref _pwAbsFillDx);
DisposeSolidBrush(ref _pwExhFillDx);
DisposeSolidBrush(ref _pwAmberFillDx);
DisposeSolidBrush(ref _pwCyanFillDx);
DisposeSolidBrush(ref _pwMagFillDx);
DisposeSolidBrush(ref _pwStackZoneDx);
DisposeSolidBrush(ref _pwSurface0Dx);
DisposeSolidBrush(ref _pwSurface1Dx);
DisposeSolidBrush(ref _pwSurface2Dx);
DisposeSolidBrush(ref _pwGridLineDx);
DisposeSolidBrush(ref _pwGridMajorDx);
DisposeSolidBrush(ref _pwTextSecondaryDx);
DisposeSolidBrush(ref _pwTextTertiaryDx);
DisposeSolidBrush(ref _pwTextHaloDx);
if (_pwPillValueFont != null) { _pwPillValueFont.Dispose(); _pwPillValueFont = null; }
if (_pwPillLabelFont != null) { _pwPillLabelFont.Dispose(); _pwPillLabelFont = null; }
if (_pwHeroFont      != null) { _pwHeroFont.Dispose();      _pwHeroFont      = null; }
if (_pwDashStyle     != null) { _pwDashStyle.Dispose();     _pwDashStyle     = null; }
if (_pwDottedStyle   != null) { _pwDottedStyle.Dispose();   _pwDottedStyle   = null; }
```

### 11.3 — Pit-wall telemetry strip renderer

Call this at the **top** of your existing `OnRender` (before everything else, so it sits at the highest Z but is positioned at the top edge):

```csharp
// Renders the F1 pit-wall telemetry strip across the top of the chart.
// Reads latched scoring + bar state — no recomputation.
private void RenderPitWallStrip(ChartControl chartControl)
{
    if (_pwSurface1Dx == null || _pwPillValueFont == null) return;

    const float stripH       = 24f;
    const float pillH        = 18f;
    const float pillGapX     = 6f;
    const float pillPadX     = 6f;
    const float pillEdgeW    = 2f;          // sector-color left edge stripe
    const float labelGapY    = 0f;
    const float chromeYOff   = 3f;          // stripe sits 3px below top edge

    float stripX = (float)ChartPanel.X;
    float stripY = (float)ChartPanel.Y;
    float stripW = (float)ChartPanel.W;

    // Backdrop strip (surface.1)
    var stripRect = new RectangleF(stripX, stripY, stripW, stripH);
    RenderTarget.FillRectangle(stripRect, _pwSurface1Dx);
    // 1px hairline divider below strip (grid.major)
    RenderTarget.DrawLine(
        new Vector2(stripX, stripY + stripH),
        new Vector2(stripX + stripW, stripY + stripH),
        _pwGridMajorDx, 1f);

    // Build pill list — (label, value, edgeColor, valueColor)
    var pills = BuildPitWallPills();    // returns IList<PitWallPill> — see §11.4

    float cursorX = stripX + 8f;
    float pillY   = stripY + chromeYOff;

    foreach (var p in pills)
    {
        // Measure value text
        float valW = MeasureTextWidth(p.Value, _pwPillValueFont);
        float labW = MeasureTextWidth(p.Label, _pwPillLabelFont);
        float pillW = pillPadX + labW + 6f + valW + pillPadX;

        // Pill background (surface.2)
        var pillRect = new RectangleF(cursorX, pillY, pillW, pillH);
        RenderTarget.FillRectangle(pillRect, _pwSurface2Dx);

        // Sector-color left edge (the signature element)
        if (p.EdgeBrush != null)
        {
            var edgeRect = new RectangleF(cursorX, pillY, pillEdgeW, pillH);
            RenderTarget.FillRectangle(edgeRect, p.EdgeBrush);
        }

        // Label (8pt caps, tertiary grey)
        DrawHaloText(p.Label, _pwPillLabelFont, _pwTextTertiaryDx,
                     cursorX + pillPadX + pillEdgeW + 2f, pillY, labW, pillH);

        // Value (13pt mono bold, sector-coded color)
        DrawHaloText(p.Value, _pwPillValueFont, p.ValueBrush ?? _pwTextPrimaryDx,
                     cursorX + pillPadX + pillEdgeW + labW + 8f, pillY, valW, pillH);

        cursorX += pillW + pillGapX;
        if (cursorX > stripX + stripW - 80f) break;   // overflow guard
    }
}

// Helper: measure text width via TextLayout (cached factory)
private float MeasureTextWidth(string s, TextFormat f)
{
    if (string.IsNullOrEmpty(s) || f == null) return 0f;
    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                    s, f, 9999f, 24f))
    {
        return tl.Metrics.Width + 2f;
    }
}

// Helper: draw text with 1px black halo (fighter-HMD legibility rule)
private void DrawHaloText(string s, TextFormat f, SharpDX.Direct2D1.Brush color,
                          float x, float y, float w, float h)
{
    using (var tl = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                    s, f, w, h))
    {
        // 1px halo — 4-direction stamp
        RenderTarget.DrawTextLayout(new Vector2(x - 1, y), tl, _pwTextHaloDx);
        RenderTarget.DrawTextLayout(new Vector2(x + 1, y), tl, _pwTextHaloDx);
        RenderTarget.DrawTextLayout(new Vector2(x, y - 1), tl, _pwTextHaloDx);
        RenderTarget.DrawTextLayout(new Vector2(x, y + 1), tl, _pwTextHaloDx);
        // Foreground
        RenderTarget.DrawTextLayout(new Vector2(x, y), tl, color);
    }
}
```

### 11.4 — Pit-wall pill builder (data → visual)

```csharp
private struct PitWallPill
{
    public string Label;
    public string Value;
    public SharpDX.Direct2D1.Brush EdgeBrush;    // sector-color left edge (or null)
    public SharpDX.Direct2D1.Brush ValueBrush;   // value text color (or null=primary)
}

private IList<PitWallPill> BuildPitWallPills()
{
    var list = new List<PitWallPill>(9);

    // 1. Symbol + tire compound
    list.Add(new PitWallPill {
        Label = "NQ", Value = TireCompoundGlyph(),
        EdgeBrush = TireCompoundEdgeBrush(),
        ValueBrush = TireCompoundEdgeBrush()
    });

    // 2. Δ (running delta of current bar)
    long delta = CurrentBarDelta();
    list.Add(new PitWallPill {
        Label = "Δ", Value = FormatSignedK(delta),
        EdgeBrush = SectorBrushForDelta(delta),
        ValueBrush = SectorBrushForDelta(delta)
    });

    // 3. VOL
    long vol = CurrentBarVol();
    bool volHot = vol > 2 * AverageBarVol();
    list.Add(new PitWallPill {
        Label = "VOL", Value = FormatK(vol),
        EdgeBrush = volHot ? _pwAeroAmberDx : null,
        ValueBrush = volHot ? _pwAeroAmberDx : _pwTextPrimaryDx
    });

    // 4. POC
    double poc = CurrentBarPoc();
    bool isSessionPoc = System.Math.Abs(poc - SessionPoc()) < TickSize() * 0.5;
    list.Add(new PitWallPill {
        Label = "POC", Value = poc.ToString("F2"),
        EdgeBrush = isSessionPoc ? _pwSectorPurpleDx : null,
        ValueBrush = _pwTextPrimaryDx
    });

    // 5. IB (max imbalance ratio in current bar)
    double ib = CurrentBarMaxImbalRatio();
    int ibSide = CurrentBarMaxImbalSide();   // +1 buy, -1 sell
    var ibEdge = ib >= 5.0
        ? (ibSide > 0 ? _pwAeroCyanDx : _pwAeroMagentaDx)
        : (ib >= 3.0 ? _pwAeroAmberDx : null);
    list.Add(new PitWallPill {
        Label = "IB", Value = ib.ToString("F1") + "x",
        EdgeBrush = ibEdge,
        ValueBrush = ibEdge ?? _pwTextPrimaryDx
    });

    // 6. KRN (Kronos bias)
    double kronos = LatchedKronosBias();
    list.Add(new PitWallPill {
        Label = "KRN", Value = (kronos >= 0 ? "+" : "") + kronos.ToString("F2"),
        EdgeBrush = _pwAeroMagentaDx,
        ValueBrush = _pwAeroMagentaDx
    });

    // 7. CONF
    double conf = LatchedConfidence();
    var confBrush = conf >= 0.85 ? _pwSectorPurpleDx
                  : conf >= 0.70 ? _pwSectorGreenDx
                  : conf >= 0.50 ? _pwSectorWhiteDx
                                 : _pwSectorYellowDx;
    list.Add(new PitWallPill {
        Label = "CONF", Value = conf.ToString("F2"),
        EdgeBrush = confBrush, ValueBrush = confBrush
    });

    // 8. PnL
    double pnlR = SessionPnLR();
    var pnlBrush = SectorBrushForPnL(pnlR);
    list.Add(new PitWallPill {
        Label = "PnL", Value = (pnlR >= 0 ? "+" : "") + pnlR.ToString("F2") + "R",
        EdgeBrush = pnlBrush, ValueBrush = pnlBrush
    });

    return list;
}

// Sector color logic — central source of truth
private SharpDX.Direct2D1.SolidColorBrush SectorBrushForPnL(double r)
{
    if (r >= SessionPnLRecord())   return _pwSectorPurpleDx;   // PB (best ever)
    if (r >=  0.5)                  return _pwSectorGreenDx;
    if (r >= -0.2)                  return _pwSectorWhiteDx;
    if (r >= -0.8)                  return _pwSectorYellowDx;
    return _pwSectorRedDx;
}

private SharpDX.Direct2D1.SolidColorBrush SectorBrushForDelta(long d)
{
    long ad = System.Math.Abs(d);
    if (ad >= 2000) return d > 0 ? _pwSectorPurpleDx : _pwSectorRedDx;
    if (ad >= 1000) return d > 0 ? _pwSectorGreenDx  : _pwSectorYellowDx;
    return _pwSectorWhiteDx;
}

private string FormatK(long v)
{
    if (v >= 1_000_000) return (v / 1_000_000.0).ToString("F1") + "M";
    if (v >= 1_000)     return (v / 1_000.0).ToString("F0") + "K";
    return v.ToString();
}
private string FormatSignedK(long v)
{
    return (v >= 0 ? "+" : "−") + FormatK(System.Math.Abs(v));
}
```

### 11.5 — Footprint cell rendering (replace existing buy/sellImbal block at line 1359-1369)

```csharp
// F1 PITWALL imbalance escalation — amber base → cyan/magenta at ×5 → bracket frame at ×8
double diagBidLong = (double)GetBid(fbar, px + tickSize);
double diagAskLong = (double)GetAsk(fbar, px - tickSize);
double buyRatio  = cell.AskVol > 0 ? cell.AskVol / System.Math.Max(1.0, diagBidLong) : 0;
double sellRatio = cell.BidVol > 0 ? cell.BidVol / System.Math.Max(1.0, diagAskLong) : 0;

SharpDX.Direct2D1.Brush cellFillBrush = null;
bool isExtreme = false;

if (buyRatio >= 8.0)  { cellFillBrush = _pwCyanFillDx;    isExtreme = true; }
else if (buyRatio >= 5.0)  cellFillBrush = _pwCyanFillDx;
else if (buyRatio >= ImbalanceRatio) cellFillBrush = _pwAmberFillDx;
else if (sellRatio >= 8.0) { cellFillBrush = _pwMagFillDx; isExtreme = true; }
else if (sellRatio >= 5.0) cellFillBrush = _pwMagFillDx;
else if (sellRatio >= ImbalanceRatio) cellFillBrush = _pwAmberFillDx;

if (cellFillBrush != null)
    RenderTarget.FillRectangle(rect, cellFillBrush);

// Cell numbers — mono, sector-coded
string label = string.Format("{0,4} x {1,-4}", cell.BidVol, cell.AskVol);
var cellTextBrush = isExtreme ? (SharpDX.Direct2D1.Brush)_pwTextPrimaryDx
                              : (SharpDX.Direct2D1.Brush)_pwTextSecondaryDx;
using (var layout = new TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                                    label, _cellFont, colW, rowH))
{
    RenderTarget.DrawTextLayout(new Vector2(xLeft, yTop), layout, cellTextBrush);
}

// Extreme cells get the corner-bracket reticle frame
if (isExtreme)
{
    var bracketBrush = buyRatio >= 8.0 ? (SharpDX.Direct2D1.Brush)_pwAeroCyanDx
                                       : (SharpDX.Direct2D1.Brush)_pwAeroMagentaDx;
    DrawCornerBrackets(rect, bracketBrush, 6f, 1.5f);
}
```

### 11.6 — Corner-bracket reticle (the F1 telemetry framing trick)

```csharp
// Draws four L-shaped corner brackets — the targeting-reticle aesthetic
// from F1/Forza HUDs. NOT a full rectangle — just the corners.
private void DrawCornerBrackets(RectangleF r, SharpDX.Direct2D1.Brush brush,
                                 float legLen, float stroke)
{
    // Top-left
    RenderTarget.DrawLine(new Vector2(r.Left, r.Top),
                          new Vector2(r.Left + legLen, r.Top), brush, stroke);
    RenderTarget.DrawLine(new Vector2(r.Left, r.Top),
                          new Vector2(r.Left, r.Top + legLen), brush, stroke);
    // Top-right
    RenderTarget.DrawLine(new Vector2(r.Right, r.Top),
                          new Vector2(r.Right - legLen, r.Top), brush, stroke);
    RenderTarget.DrawLine(new Vector2(r.Right, r.Top),
                          new Vector2(r.Right, r.Top + legLen), brush, stroke);
    // Bottom-left
    RenderTarget.DrawLine(new Vector2(r.Left, r.Bottom),
                          new Vector2(r.Left + legLen, r.Bottom), brush, stroke);
    RenderTarget.DrawLine(new Vector2(r.Left, r.Bottom),
                          new Vector2(r.Left, r.Bottom - legLen), brush, stroke);
    // Bottom-right
    RenderTarget.DrawLine(new Vector2(r.Right, r.Bottom),
                          new Vector2(r.Right - legLen, r.Bottom), brush, stroke);
    RenderTarget.DrawLine(new Vector2(r.Right, r.Bottom),
                          new Vector2(r.Right, r.Bottom - legLen), brush, stroke);
}
```

### 11.7 — Absorption signature renderer

Call from your absorption-detection path after a fire is confirmed:

```csharp
// Renders an absorption signature — cyan reticle + tinted fill + label strip.
// barIdx, anchorPrice, direction, strength come from your AbsorptionSignal.
private void RenderAbsorptionSignature(ChartControl cc, ChartScale cs,
                                        int barIdx, double anchorPrice,
                                        int direction, double strength,
                                        long barDelta, double wickPct)
{
    int colW = System.Math.Max(CellColumnWidth, cc.GetBarPaintWidth(ChartBars));
    int xCenter = cc.GetXByBarIndex(ChartBars, barIdx);
    float xLeft  = xCenter - colW / 2f;
    float yTop   = cs.GetYByValue(anchorPrice) - 24f;
    float h      = 56f;
    var rect = new RectangleF(xLeft - 4f, yTop, colW + 8f, h);

    // Fill (cyan @ 22%)
    RenderTarget.FillRectangle(rect, _pwAbsFillDx);
    // Corner-bracket reticle (full-strength cyan)
    DrawCornerBrackets(rect, _pwAeroCyanDx, 8f, 1.5f);

    // Top label: "ABSORPTION ▲" in cyan caps
    string lbl = direction > 0 ? "ABSORPTION ▲" : "ABSORPTION ▼";
    DrawHaloText(lbl, _pwPillLabelFont, _pwAeroCyanDx,
                 rect.Left + 8f, rect.Top + 2f, rect.Width - 16f, 12f);

    // Bottom data strip: Δ value + wick%
    string data = string.Format("Δ{0:+#;−#;0}  WICK {1:F0}%", barDelta, wickPct);
    DrawHaloText(data, _pwPillValueFont, _pwTextPrimaryDx,
                 rect.Left + 8f, rect.Bottom - 16f, rect.Width - 16f, 14f);
}

// Exhaustion is identical — swap _pwAbsFillDx for _pwExhFillDx and _pwAeroCyanDx for _pwAeroMagentaDx
private void RenderExhaustionSignature(ChartControl cc, ChartScale cs,
                                        int barIdx, double anchorPrice,
                                        int direction, double strength,
                                        long barDelta, double rejectPct)
{
    int colW = System.Math.Max(CellColumnWidth, cc.GetBarPaintWidth(ChartBars));
    int xCenter = cc.GetXByBarIndex(ChartBars, barIdx);
    float xLeft  = xCenter - colW / 2f;
    float yTop   = cs.GetYByValue(anchorPrice) - 24f;
    float h      = 56f;
    var rect = new RectangleF(xLeft - 4f, yTop, colW + 8f, h);

    RenderTarget.FillRectangle(rect, _pwExhFillDx);
    DrawCornerBrackets(rect, _pwAeroMagentaDx, 8f, 1.5f);

    string lbl = direction > 0 ? "EXHAUSTION ▲" : "EXHAUSTION ▼";
    DrawHaloText(lbl, _pwPillLabelFont, _pwAeroMagentaDx,
                 rect.Left + 8f, rect.Top + 2f, rect.Width - 16f, 12f);

    string data = string.Format("Δ{0:+#;−#;0}  REJ {1:F0}%", barDelta, rejectPct);
    DrawHaloText(data, _pwPillValueFont, _pwTextPrimaryDx,
                 rect.Left + 8f, rect.Bottom - 16f, rect.Width - 16f, 14f);
}
```

### 11.8 — POC as "best lap" purple line (replace line 1372-1378)

```csharp
// POC bar — purple "best lap" line spanning bar paint width
if (ShowPoc && fbar.PocPrice > 0)
{
    float yPoc = chartScale.GetYByValue(fbar.PocPrice);
    var pocRect = new RectangleF(xLeft, yPoc - 1, colW, 2);
    RenderTarget.FillRectangle(pocRect, _pwSectorPurpleDx);
}
```

### 11.9 — GEX level rendering (drop into `DEEP6GexLevels.cs` OnRender, replace existing line drawing)

```csharp
// Aerospace GEX rendering — Boeing color grammar
private void RenderGexLevelAerospace(ChartScale cs, float panelLeft, float panelRight,
                                      double price, GexLevelKind kind, double valueGex)
{
    float y = cs.GetYByValue(price);
    SharpDX.Direct2D1.SolidColorBrush lineBrush = null;
    SharpDX.Direct2D1.StrokeStyle     style     = null;
    float                             stroke    = 1.5f;
    string                            labelTxt  = "";
    bool                              drawBand  = false;

    switch (kind)
    {
        case GexLevelKind.ZeroGamma:
            lineBrush = _pwAeroCyanDx;       stroke = 2f;
            labelTxt  = "ZG  " + price.ToString("F0");
            break;
        case GexLevelKind.Flip:
            lineBrush = _pwAeroMagentaDx;    style = _pwDashStyle;
            labelTxt  = "FLIP " + price.ToString("F0");
            break;
        case GexLevelKind.CallWall:
            lineBrush = _pwAeroAmberDx;      stroke = 2f; drawBand = true;
            labelTxt  = "CW  " + price.ToString("F0");
            break;
        case GexLevelKind.PutWall:
            lineBrush = _pwAeroAmberDx;      stroke = 2f; drawBand = true;
            labelTxt  = "PW  " + price.ToString("F0");
            break;
    }

    // Optional safety band (call/put walls)
    if (drawBand)
    {
        var bandRect = new RectangleF(panelLeft, y - 3f, panelRight - panelLeft, 6f);
        RenderTarget.FillRectangle(bandRect, _pwAmberFillDx);   // amber @ 18%
    }

    // The level line
    if (style != null)
        RenderTarget.DrawLine(new Vector2(panelLeft, y), new Vector2(panelRight - 100f, y),
                              lineBrush, stroke, style);
    else
        RenderTarget.DrawLine(new Vector2(panelLeft, y), new Vector2(panelRight - 100f, y),
                              lineBrush, stroke);

    // Right-side telemetry pill label
    var pillRect = new RectangleF(panelRight - 95f, y - 9f, 90f, 18f);
    RenderTarget.FillRectangle(pillRect, _pwSurface2Dx);
    var edgeRect = new RectangleF(panelRight - 95f, y - 9f, 2f, 18f);
    RenderTarget.FillRectangle(edgeRect, lineBrush);
    DrawHaloText(labelTxt, _pwPillValueFont, _pwTextPrimaryDx,
                 panelRight - 85f, y - 9f, 80f, 18f);
}
```

### 11.10 — Sector-color-coded P&L renderer (equity ribbon)

```csharp
// Renders the bottom-of-chart equity ribbon — one cell per closed trade,
// sector-color-coded.
private void RenderEquityRibbon(IList<ClosedTradeR> trades, double sessionRecord)
{
    if (trades == null || trades.Count == 0) return;

    const float ribbonH = 18f;
    float ribbonY  = (float)(ChartPanel.Y + ChartPanel.H - ribbonH - 24f);
    float ribbonX  = (float)ChartPanel.X + 8f;
    float ribbonW  = (float)ChartPanel.W - 16f;

    // Backdrop
    RenderTarget.FillRectangle(new RectangleF(ribbonX, ribbonY, ribbonW, ribbonH),
                                _pwSurface1Dx);

    // Cell width — fit all trades, min 6px
    float cellW = System.Math.Max(6f, ribbonW / System.Math.Max(1, trades.Count));

    for (int i = 0; i < trades.Count; i++)
    {
        var t = trades[i];
        var brush = (t.R >= sessionRecord) ? _pwSectorPurpleDx
                  : (t.R >=  0.5)          ? _pwSectorGreenDx
                  : (t.R >= -0.2)          ? _pwSectorWhiteDx
                  : (t.R >= -0.8)          ? _pwSectorYellowDx
                                           : _pwSectorRedDx;
        // Cell height proportional to |R|, capped at ribbonH-2
        float h = (float)System.Math.Min(ribbonH - 2f, System.Math.Abs(t.R) * (ribbonH - 2f));
        float yOff = ribbonY + (ribbonH - h) * 0.5f;
        var cellRect = new RectangleF(ribbonX + i * cellW + 1f, yOff, cellW - 2f, h);
        RenderTarget.FillRectangle(cellRect, brush);
    }

    // Zero hairline
    float zeroY = ribbonY + ribbonH * 0.5f;
    RenderTarget.DrawLine(new Vector2(ribbonX, zeroY), new Vector2(ribbonX + ribbonW, zeroY),
                          _pwGridLineDx, 1f);
}

public struct ClosedTradeR { public double R; public DateTime CloseTime; }
```

### 11.11 — Position-change arrows

```csharp
// Renders a position-change arrow (rank delta indicator)
private void RenderRankDelta(float x, float y, int delta)
{
    if (delta == 0)
    {
        // Grey hairline dash
        RenderTarget.DrawLine(new Vector2(x, y + 4f), new Vector2(x + 6f, y + 4f),
                              _pwTextTertiaryDx, 1f);
        return;
    }

    bool up = delta > 0;
    int  mag = System.Math.Abs(delta);
    var brush = up
        ? (mag >= 3 ? (SharpDX.Direct2D1.Brush)_pwAeroMagentaDx : _pwAeroCyanDx)
        : (mag >= 3 ? (SharpDX.Direct2D1.Brush)_pwAeroRedDx     : _pwAeroAmberDx);

    // Triangle path
    var sink = new SharpDX.Direct2D1.PathGeometry(RenderTarget.Factory);
    using (var s = sink.Open())
    {
        if (up)
        {
            s.BeginFigure(new Vector2(x + 4f, y),     FigureBegin.Filled);
            s.AddLine(new Vector2(x + 8f, y + 8f));
            s.AddLine(new Vector2(x,     y + 8f));
        }
        else
        {
            s.BeginFigure(new Vector2(x,     y),     FigureBegin.Filled);
            s.AddLine(new Vector2(x + 8f, y));
            s.AddLine(new Vector2(x + 4f, y + 8f));
        }
        s.EndFigure(FigureEnd.Closed);
        s.Close();
    }
    RenderTarget.FillGeometry(sink, brush);

    // Magnitude label
    string lbl = mag.ToString();
    DrawHaloText(lbl, _pwPillLabelFont, brush, x + 10f, y - 1f, 12f, 12f);

    sink.Dispose();
}
```

### 11.12 — Tire compound disc

```csharp
private string TireCompoundGlyph()
{
    var c = ResolveTireCompound();   // your risk-state classifier
    switch (c)
    {
        case RiskRegime.Aggressive:    return "●S";
        case RiskRegime.Standard:      return "●M";
        case RiskRegime.Conservative:  return "●H";
        case RiskRegime.PostLossBreak: return "●W";
        default:                       return "●OFF";
    }
}
private SharpDX.Direct2D1.SolidColorBrush TireCompoundEdgeBrush()
{
    var c = ResolveTireCompound();
    switch (c)
    {
        case RiskRegime.Aggressive:    return _pwSectorRedDx;
        case RiskRegime.Standard:      return _pwSectorYellowDx;
        case RiskRegime.Conservative:  return _pwAeroWhiteDx;
        case RiskRegime.PostLossBreak: return _pwAeroCyanDx;
        default:                       return _pwTextTertiaryDx;
    }
}
public enum RiskRegime { Aggressive, Standard, Conservative, PostLossBreak, KillSwitch }
```

### 11.13 — Hook into existing OnRender

In your existing `OnRender` method (line 1295), add at the **very top** (after `base.OnRender`):

```csharp
base.OnRender(chartControl, chartScale);
RenderTarget.AntialiasMode = AntialiasMode.PerPrimitive;

// ── F1 PITWALL: telemetry strip at top of chart panel ──
if (ShowPitWallStrip) RenderPitWallStrip(chartControl);

// ── (existing rendering continues) ──
double tickSize = chartControl.Instrument.MasterInstrument.TickSize;
// ...
```

Add the property:

```csharp
[Display(Name="Show Pit-Wall Strip", GroupName="DEEP6 Visuals (PitWall)", Order=1)]
public bool ShowPitWallStrip { get; set; } = true;
```

In `SetDefaults`:

```csharp
ShowPitWallStrip = true;
```

---

## 12 · WHY THIS AESTHETIC WINS (3 sentences)

F1 telemetry is the **only field** in the world that has solved real-time, high-density, multi-channel decision support under literally life-or-death time pressure — institutional trading is the same shape of problem (44 signals, sub-second decisions, capital at risk), but retail trading has never imported the discipline that wins races. By forcing every color to mean something *out of the Boeing/F1 grammar* — cyan = your selected target, magenta = the algo's commanded value, purple = personal best ever, amber = approaching limit — we replace the rainbow chaos of TradingView with a vocabulary the trader's eye learns in one session and reads in ≤0.5 seconds for the rest of their career. And the corner-bracket reticle framing on absorption/exhaustion signatures is the visual masterstroke: it transforms DEEP6's signature signals from "boxes around bars" into **targeting overlays from a fighter HUD**, communicating instantly that the system has *acquired a target* — which is psychologically and aesthetically exactly what an absorption print represents.

---

## SUMMARY OF DELIVERABLES IN THIS PROPOSAL

- One paragraph philosophy (§1)
- Complete palette: 60+ tokens with hex (§2.1–2.10)
- Typography spec: 4 font roles, 7-step type scale, 0.5-sec rule (§3)
- 6 ported F1 mechanics (sector colors, delta gauge, rank arrows, tire compounds, lap tape, DRS toggles) (§4)
- Footprint cell recipe with corner-bracket reticle (§5)
- Pit-wall telemetry strip — the signature element (§6)
- GEX level rendering in aerospace conventions (§7)
- Strategy / equity ribbon / working orders / R-R zones (§8)
- Concrete implementations for arrows, tires, DRS (§9)
- Full ASCII chart mockup (§10)
- 13 ready-to-drop SharpDX code blocks compatible with `DEEP6Footprint.cs` and `DEEP6GexLevels.cs` (§11)
- Why-it-wins (§12)

**Files this design touches when implemented:**
- `/Users/teaceo/DEEP6/ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` — brush fields, OnRenderTargetChanged, OnRender, helpers
- `/Users/teaceo/DEEP6/ninjatrader/Custom/Indicators/DEEP6/DEEP6GexLevels.cs` — RenderGexLevelAerospace replaces existing line drawing
- `/Users/teaceo/DEEP6/ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs` — surfaces TireCompound state + ClosedTradeR list to the indicator (read-only DataBridge pattern, already established in `DataBridgeIndicator.cs`)
