---
phase: 11.2
slug: ui-redesign
title: DEEP6 Dashboard UI v2 — TERMINAL NOIR
status: draft
supersedes: .planning/phases/11-deep6-trading-web-app/11-UI-SPEC.md
created: 2026-04-14
constraint: Visual layer only — no changes to WebSocket/Zustand/replay wiring or Phase 9 backend
---

# UI-SPEC v2 — TERMINAL NOIR

> "If a Bloomberg terminal lived inside a Bookmap chart and they both moonlighted at a Tokyo trading desk circa 2049."

## 0 · Aesthetic Direction (read before opening any other section)

**Name:** TERMINAL NOIR
**Three-word brief:** Dense. Saturated. Reverent.

This is not a SaaS dashboard. It is an **instrument**. The screen is a piece of professional equipment used for hours by a trader who does not need it to be friendly — they need it to be *true*. Every pixel must carry information or atmosphere. Whitespace is a tool, not a default.

**The five non-negotiables:**

1. **Pure black, not "near-black."** Background is `#000000`. The previous v1 used `#0a0a0f`. That was wrong — neons only sing against true black.
2. **One typeface, one weight family, infinite hierarchy through size and color.** JetBrains Mono only. No Inter. No Geist. The terminal commitment is total.
3. **Saturated neons earn their place.** Five accent colors, each with a single semantic owner. No purple gradients. No drop-shadows on text.
4. **Information density before whitespace.** If a panel has < 4 distinct data points visible at once, it is wasting screen real estate.
5. **Glow as light, not as effect.** Neons emit. They don't `box-shadow: 0 0 12px`. They use real bloom via layered radial gradients + selective `filter: drop-shadow()` for the signal moment.

**One thing the user remembers:** the **Confluence Pulse** — a circular meter to the right of the chart whose ring is composed of 44 individual signal arcs that ignite as their engines fire, surrounding the running confluence number. When TYPE_A fires, the whole ring flashes white-hot for 200ms then settles into its signal-color. This is the dashboard's signature.

---

## 1 · Color System

### Surface palette

| Token | Hex | Role | Coverage |
|---|---|---|---|
| `--void` | `#000000` | True-black canvas — chart background, app background | 65% |
| `--surface-1` | `#0a0a0a` | First elevation — panels, sidebars | 20% |
| `--surface-2` | `#141414` | Second elevation — cards, modals, hover states | 8% |
| `--rule` | `#1f1f1f` | Rule lines, borders, dividers | structural |
| `--rule-bright` | `#2a2a2a` | Active rules, focused borders | 1% |

### Text

| Token | Hex | Use |
|---|---|---|
| `--text` | `#f5f5f5` | Primary text — labels, narratives |
| `--text-dim` | `#8a8a8a` | Secondary — units, metadata, axis labels |
| `--text-mute` | `#4a4a4a` | Tertiary — disabled, placeholder, decorative chrome |

### Neon palette (semantic owners — strict)

| Token | Hex | Owner | Never used for |
|---|---|---|---|
| `--bid` | `#ff2e63` | Sellers hit bid; bearish delta; SHORT bias; loss P&L | anything UI-chrome |
| `--ask` | `#00ff88` | Buyers lift offer; bullish delta; LONG bias; win P&L; circuit-breaker OK | anything UI-chrome |
| `--cyan` | `#00d9ff` | TYPE_C signal; LVN zone outline; replay mode active | TYPE_A or TYPE_B |
| `--amber` | `#ffd60a` | TYPE_B signal; HVN/POC; warning state | success states |
| `--lime` | `#a3ff00` | TYPE_A signal; high confluence (≥80); the **only** "wow" color | anything else, ever |
| `--magenta` | `#ff00aa` | Kronos E10 / ML inferences (ALL ML attribution) | non-ML data |

The accent budget is **lime alone** in the 60/30/10 sense. The other neons are semantic, not decorative. Together they should never exceed 12% of pixel coverage in a normal frame.

### Glow recipe

Glow is **bloom**, not blur. Implementation:

```css
.glow {
  /* Layer 1: text in solid neon */
  color: var(--lime);
  /* Layer 2: drop-shadow halo (filter, NOT box-shadow — clips to glyph edges) */
  filter:
    drop-shadow(0 0 4px color-mix(in oklch, var(--lime) 80%, transparent))
    drop-shadow(0 0 12px color-mix(in oklch, var(--lime) 40%, transparent));
}
```

Glow is reserved for: TYPE_A signal pills, the Confluence Pulse number when ≥80, the LIVE indicator, and the connection dot when active.

---

## 2 · Typography

**One font:** **JetBrains Mono** (variable, weights 100–800).
**No exceptions.** Every label, every number, every narrative.

### Scale (4 sizes — strict)

| Size | px | Weight | Line | Use |
|---|---|---|---|---|
| `text-xs` | 11 | 400 | 1.2 | Axis labels, replay timestamps, footprint cell text |
| `text-sm` | 13 | 500 | 1.3 | Body, narratives, labels, badges |
| `text-md` | 16 | 600 | 1.2 | Panel headings, instrument code (NQ), price display |
| `text-display` | 56 | 700 | 1.0 | Confluence Pulse number — the only large number on screen |

### Letter-spacing rules

- Labels and headings: `letter-spacing: 0.08em` (terminal feel)
- Numbers and prices: `letter-spacing: 0` (tabular alignment)
- The display number: `letter-spacing: -0.04em` (tight, monumental)

### Tabular numerics — mandatory

Every number that updates in real time uses `font-variant-numeric: tabular-nums`. Without it, the numbers shimmer as digits change width. Apply via global utility:

```css
.tnum { font-variant-numeric: tabular-nums; }
```

---

## 3 · Spatial System

### Grid

8-point grid for spacing. Four tokens, no exceptions:

```
--space-1: 4px    /* tight pairings (icon + text) */
--space-2: 8px    /* default gap */
--space-3: 16px   /* panel padding */
--space-4: 32px   /* major separations */
```

Rule densities — fixed:

- Footprint cell row height: **16px** (was 20 in v1; tightened for density)
- Signal feed entry: **44px** (badge + narrative + score line)
- T&S row: **18px**
- Header strip: **44px**
- Replay strip: **52px** (touch target)

### Layout — asymmetric, not 3 even columns

The v1 spec used a 1fr | 320px | 240px three-column layout. **It looks like a generic dashboard.** v2 breaks the symmetry:

```
┌──────────────────────────────────────────────────────────────────┐
│ HEADER STRIP (44px) — DEEP6 ▸ NQ ▸ price • E10 • GEX • clock     │
├────────────────────────────┬─────────────┬───────────────────────┤
│                            │             │                       │
│                            │  CONFLUENCE │   SIGNAL FEED         │
│       FOOTPRINT            │   PULSE     │   (12-row ticker)     │
│       CHART                │   (320×320) │                       │
│       (flex-1)             │   ★ HERO    │                       │
│                            │             ├───────────────────────┤
│                            │  KRONOS E10 │                       │
│                            │  (ring)     │   T&S TAPE            │
│                            │             │   (compact)           │
│                            ├─────────────┤                       │
│                            │  ZONE LIST  │                       │
│                            │  (POC/VAH/  │                       │
│                            │   VAL/HVN)  │                       │
│                            │             │                       │
├────────────────────────────┴─────────────┴───────────────────────┤
│ REPLAY STRIP (52px) — session • controls • speed • LIVE pill     │
└──────────────────────────────────────────────────────────────────┘
```

Specifically: chart `flex-1 min-w-0`, center column **320px shrink-0** (hero column), right column **300px shrink-0**. The center column being a fixed visual anchor (not just sidebar fodder) is the layout's defining choice.

---

## 4 · Component Specifications

### 4.1 · Confluence Pulse (the signature — 320 × 320)

The hero. A circular meter with three concentric rings:

**Outer ring (radius 150 → 142px stroke):** 44 individual arcs, one per signal in the system. Each arc is `8.18°` wide with a `0.5°` gap. Ignited arcs glow in their category color (absorption=lime, exhaustion=lime, imbalance=cyan, delta=amber, auction=cyan, volume=amber, trap=bid, ml=magenta). Unlit arcs are `--rule`. Newly-firing arcs do a 200ms ease-out to their bright state.

**Middle ring (radius 130 → 122px stroke):** 8 category sectors (45° each), filled in the category color at opacity = `category_score / 100`. This is the at-a-glance category view.

**Inner core (radius 100):**
- Top half: the confluence number, `text-display` (56px JetBrains Mono 700), color = `--lime` if ≥80, `--amber` if 50–79, `--text-mute` if <50. Tabular numerics. The number ticks via digit-roll animation when it changes (Motion's `useMotionValue` + `animate`).
- Bottom half: the tier badge — `TYPE_A` / `TYPE_B` / `TYPE_C` / `QUIET` — at `text-md`, in tier color, in a bordered rectangle (no fill). Below the badge, direction icon: ▲ for +1 (in `--ask`), ▼ for −1 (in `--bid`), ─ for 0 (in `--text-mute`).

**TYPE_A flash:** when total_score crosses ≥80 OR a TYPE_A signal arrives, the entire pulse does a 200ms white-hot flash:
1. Outer ring: all arcs jump to `#ffffff` then settle to category color
2. Inner number: scales 1.0 → 1.08 → 1.0 with `--lime` glow filter intensified 2x
3. A radial bloom (90px → 200px, `--lime` at 30% opacity → 0%) expands from center
4. Subtle screen-shake on the body element: 4px translation, 80ms (respects `prefers-reduced-motion`)

### 4.2 · Footprint Chart

LW Charts v5.1 custom series + sibling Canvas overlay. Carries over from v1 architecturally; the visual treatment changes:

**Per-row cell:**
- 16px row height
- Bid volume on left, ask volume on right, each as a colored bar extending from the row centerline outward, length = `volume / max_volume_in_bar * (cell_width / 2 - 2px)`
- Fill: solid `--bid` / `--ask` at 90% opacity for normal cells; **100% with bloom filter** for cells with imbalance ≥ 3.0× (the imbalance flag is per-row; runner-cells stand out)
- Volume number rendered **inside** the bar, right-aligned (bid) / left-aligned (ask), at `text-xs` in pure white if the bar fill is wide enough (≥ 32px), else outside in `--text` color
- Stacked imbalance run: a vertical lime line on the imbalance side spans the run (3+ consecutive imbalanced cells)

**POC line:** thin 1px horizontal `--amber` glow line at the POC price, full bar width.

**Signal markers:** when a TYPE_A/B/C fires on a bar, a thin vertical line in the tier color extends from the row to 8px above the bar, terminating in a 6×6 square of the tier color. No labels — the signal feed carries narrative.

**Background grid:** vertical bar separators at `--rule` (1px). No horizontal price grid — the bid/ask bars themselves are the rhythm.

**Crosshair:** `--text-dim` 1px dashed.

**Empty state:** "AWAITING NQ FOOTPRINT" centered, `text-sm`, `--text-mute`, `letter-spacing: 0.16em`. No spinner.

### 4.3 · Signal Feed (right column, top)

12-row ticker, newest at top, infinite scroll. Each row = 44px:

```
[●][TYPE_A] ABSORBED @VAH                    +0.0s
       92  ·  ABS+EXH+IMB+DELTA+AUCT+VOL+TRAP →
```

**Row anatomy (top to bottom):**
- Tier indicator: 4px-wide left border in tier color, full row height
- Top line: status dot (animated: pulses in tier color for 8s after arrival, then steady), tier badge `[TYPE_A]` in tier color, narrative in `--text` (truncate with ellipsis), age timestamp on the right in `--text-dim` (`+1.2s`, `+45s`, `+3m` — relative)
- Bottom line: total_score in tabular-nums (tier color), `·`, agreement string in `--text-dim` UPPERCASE with truncation; trailing `→` chevron in `--text-mute` indicates "more info on hover"
- Hover: row inflates 44 → 88px revealing engine_agreement %, GEX regime, kronos_bias, category_count

**TYPE_A arrival animation:**
1. Row slides in from top with `clip-path` reveal (320ms cubic-bezier)
2. Background flashes lime at 20% opacity, fades to transparent over 800ms
3. Lime glow filter applied to entire row for 1200ms then removed

### 4.4 · Time & Sales Tape (right column, bottom)

Compact 18px rows, monospace columns:

```
05:43:12.481  19483.50  ASK  3       
05:43:12.398  19483.50  BID  1   ⓘ   
05:43:12.211  19483.25  ASK  47  ★   
```

- Time `text-xs` `--text-dim`
- Price `text-xs` `--text` tabular
- Side `text-xs` in `--ask` or `--bid`
- Size `text-xs` tabular; sizes ≥ 50 get `--text` weight 600
- Marker column (last 14px): `★` for sweep prints, `⊟` for iceberg refills, `ⓘ` for Kronos-flagged ticks, blank otherwise
- New rows pulse in: 100ms background flash in side-color at 25% opacity

Auto-scroll unless user has scrolled up (then "↓ NEW (47)" pill appears at bottom-right).

### 4.5 · Kronos E10 Ring

Below the Confluence Pulse (or stacked into it as an inset, designer's call). A horizontal capsule:

```
┌─ KRONOS E10 ──────────────────────────────────┐
│  LONG  72%  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━░░░  │
│        ▲    ════════════════════════════════   │
└────────────────────────────────────────────────┘
```

- Label `text-xs` `--text-dim` `KRONOS E10` letter-spaced
- Direction `text-md` 600 in direction-color (`--ask` long, `--bid` short, `--text-mute` neutral)
- Confidence number `text-md` 600 tabular, magenta (`--magenta` — Kronos always speaks magenta)
- Bar: gradient from magenta (start) to direction-color (end) at fill width = confidence%
- Below bar: thin `═══` fill in magenta showing `kronos_bias / 100` separately (so you see both metrics)

### 4.6 · Zone List (right column, third tier)

A compact table of the 4 most relevant zones from the registry:

```
ZONES                          ALERTS
────────────────────────────────────
POC   19481.50    ━━━━━●        2
VAH   19485.00    ━━━━━━━━━●   
VAL   19478.00    ●━━━━━         1
LVN   19479.50    ━━━━●━━━       
```

- Zone code `text-xs` 600 (`POC` amber, `VAH`/`VAL` text, `LVN` cyan, `HVN` amber)
- Price tabular
- Mini-bar shows current price position relative to that zone (`●` is current price, range = ±5 ticks around zone)
- Alert count: number of times the price has reacted off this zone in the session

### 4.7 · Header Strip (44px)

```
DEEP6 ▸ NQ ▸ 19,483.50 ▲+1.25  │  E10 LONG 72%  │  GEX POS_GAMMA  │  09:43:12 ET   ●
```

- `DEEP6` in `--text` 600
- `▸` separator in `--text-mute`
- Instrument `NQ` in `--text` 600
- Price tabular `text-md` 600 — color shifts: `--ask` if last change was up, `--bid` if down (300ms flash, settle to `--text`)
- Delta `▲+1.25` in change direction color (always; not flashing)
- Three pipes `│` in `--rule` separators
- E10 / GEX / Time labels in `--text-dim`, values in their semantic colors (`--magenta` for E10, `--ask`/`--bid`/`--text-mute` for GEX based on regime)
- Connection dot (8px) on far right: `--ask` connected with subtle pulse, `--bid` disconnected, `--amber` reconnecting (flashing)

### 4.8 · Replay Strip (52px)

```
[2026-04-14 ▾]  ⏮  ▶  ⏭   bar# [____]  142/512   speed [1× ▾]                 ◯ LIVE
```

- Session selector (left): shadcn `<Select>`, dark variant, `--surface-2` background, `--rule-bright` border
- Transport buttons: 36×36, no border, on hover gain `--surface-2` background, lucide icons in `--text` (active) or `--text-mute` (disabled)
- Bar input: 56×36, `--surface-2` background, `--rule` border, focus border `--lime`
- Bar position: `text-sm` tabular `--text-dim`
- Speed selector: shadcn `<Select>` matching session
- LIVE pill (right): when in live mode it's a solid `--ask` filled pill, white text, with a constant breathing pulse (1.5s opacity 0.7→1.0); when in replay mode it's an outlined button in `--text-dim`. Click → returns to live.

---

## 5 · Motion Vocabulary

| Element | Trigger | Duration | Easing | Notes |
|---|---|---|---|---|
| Confluence number tick | score change | 600ms | `ease-out` | Digit-roll via Motion `useMotionValue` |
| Confluence pulse arc ignite | engine fires | 200ms | `cubic-bezier(0.4, 0, 0.2, 1)` | Stagger by `15ms × index` |
| TYPE_A flash | tier=TYPE_A | 200ms flash + 1200ms decay | `ease-out` | White → lime; whole pulse + signal row |
| Signal row arrival | new signal in store | 320ms | `cubic-bezier(0.16, 1, 0.3, 1)` | clip-path reveal |
| Price tick color flash | price change | 300ms | `ease-out` | flash → settle |
| T&S row pulse | new row | 100ms flash + 200ms fade | `ease-out` | side-color background |
| LIVE pill breathe | always (live mode) | 1500ms loop | `ease-in-out` | opacity 0.7 ↔ 1.0 |
| Connection dot pulse | connected | 2000ms loop | `ease-in-out` | scale 1.0 ↔ 1.15 + opacity 0.6 ↔ 1.0 |

**Global rule:** all motion respects `@media (prefers-reduced-motion: reduce)` → reduce all durations to 0 except the digit roll (which becomes instant) and the breathing pulses (disabled).

---

## 6 · Atmosphere & Texture

Three subtle layers applied at the app root, in z-order:

1. **Scanline overlay** — `repeating-linear-gradient(0deg, transparent 0, transparent 2px, rgba(255,255,255,0.012) 2px, rgba(255,255,255,0.012) 3px)` covering the whole viewport, `pointer-events: none`, fixed position. The 0.012 opacity is deliberately at the edge of perception.

2. **Vignette** — `radial-gradient(ellipse at center, transparent 60%, rgba(0,0,0,0.4) 100%)` on a `:before` of the app root. Pulls focus to the center.

3. **Grain** — a 200×200px pre-baked SVG noise texture, `mix-blend-mode: overlay`, opacity `0.04`, repeated as a tile. Critical for making true-black `#000000` not look digitally flat.

Optionally (designer's call): a 1px white horizontal scan-line that sweeps top-to-bottom every 8 seconds at 4% opacity. This is *the* CRT signature. Recommend including it.

---

## 7 · Iconography

**Library:** Lucide React (existing in stack), but with an icon-style override:

```css
.icon {
  stroke-width: 1.25;            /* default lucide is 2 — too heavy for terminal */
  stroke-linecap: square;
  stroke-linejoin: miter;
}
```

**Custom SVG required (executor implements):**
- Direction triangles: ▲ ▼ ─ rendered as solid filled triangles, not arrows
- Sparkline mini-chart for inline trend hints (24×8px)
- Zone marker glyphs: `POC` `VAH` `VAL` `LVN` `HVN` rendered as 14×14px squared monogram tiles in their zone colors

---

## 8 · Empty, Error, and Loading States

Every state has exact copy and exact treatment. No placeholder content.

| State | Where | Copy | Treatment |
|---|---|---|---|
| Footprint empty | Chart | `AWAITING NQ FOOTPRINT` | Center, `text-sm`, `--text-mute`, letter-spaced 0.16em |
| Signal feed empty | Right top | `[ NO SIGNALS ]` `tail -f /dev/orderflow` | Two lines centered. Second line in `--text-mute` italic, 12px |
| T&S empty | Right bottom | `// no prints yet` | Single line `--text-mute`, `text-xs`, monospace comment style |
| Connection lost | Header dot + banner | `LINK DOWN. RETRYING…` (banner under header, `--bid` text on `surface-1`, no fill) | banner persists until reconnect |
| Feed stalled | Header dot becomes amber | `STALE — last tick {N}s ago` | banner same style, in amber |
| Replay session 404 | Replay strip | `SESSION NOT FOUND. SELECT FROM HISTORY.` | replaces the bar position text in amber |
| Confluence pulse loading | Inner core | A single `─` in `--text-mute` for the number; outer arcs all unlit | no spinner ever |

---

## 9 · Inventory: What to Build (executor checklist)

| Component | Status vs v1 | Action |
|---|---|---|
| `app/globals.css` | Replace tokens | New color tokens + scanline/vignette/grain |
| `components/layout/HeaderStrip.tsx` | Rewrite | New copy, separators, price flash, connection dot |
| `components/footprint/FootprintChart.tsx` | Keep wiring | Same |
| `lib/lw-charts/FootprintRenderer.ts` | **Major rewrite** | Volume-bars not text-as-cells; bloom on imbalance; signal markers |
| `components/footprint/ZoneOverlay.tsx` | Keep | Adjust colors only |
| `components/score/ScoreWidget.tsx` | **Replace entirely** | Becomes `ConfluencePulse.tsx` (new) |
| `components/score/ConfluencePulse.tsx` | **NEW** | Hero component, SVG ring + Motion |
| `components/score/KronosBar.tsx` | **NEW** | Replaces inline Kronos in old ScoreWidget |
| `components/zones/ZoneList.tsx` | **NEW** | Compact table with mini-bars |
| `components/signals/SignalFeed.tsx` | Keep wiring | Pass through |
| `components/signals/SignalFeedRow.tsx` | **Major rewrite** | New layout, hover-expand, TYPE_A flash |
| `components/tape/TapeScroll.tsx` | **Major rewrite** | Tighter rows, marker column, pulse-in |
| `components/replay/ReplayControls.tsx` | Restyle | Same wiring, new look |
| `components/replay/SessionSelector.tsx` | Restyle | Match new shadcn dark |
| `components/common/ErrorBanner.tsx` | New copy | `LINK DOWN. RETRYING…` etc. |
| `app/layout.tsx` | Add layers | Mount scanline + vignette + grain + JetBrains Mono variable font |
| `app/page.tsx` | New layout | Asymmetric 3-column with hero center |
| `components/atmosphere/Scanlines.tsx` | **NEW** | Scanlines overlay |
| `components/atmosphere/Grain.tsx` | **NEW** | Grain noise overlay |
| `components/atmosphere/CRTSweep.tsx` | **NEW (optional)** | The 8s sweep line |
| `lib/animations.ts` | **NEW** | Shared Motion variants (TYPE_A flash, digit roll, etc.) |

**Dependencies to add:**
- `motion` (for digit rolls + orchestrated flashes; replace any framer-motion if previously installed)
- No new font deps — JetBrains Mono variable already loaded via `next/font/google`

**Do not add:**
- Charting libraries beyond Lightweight Charts v5.1
- Icon libraries beyond Lucide
- Component libraries beyond shadcn (and use it sparingly — most components are custom)

---

## 10 · Acceptance Criteria (visual)

A trader sitting down at this dashboard for the first time should:

1. Within **one second**, locate the Confluence Pulse and read the current score
2. Within **three seconds**, identify whether any TYPE_A signal has fired in the last 10 seconds (via the pulse arc + signal feed top row)
3. Within **five seconds**, identify the current GEX regime, Kronos bias direction, and connection status without having to scan
4. Feel that the dashboard is *expensive* — not in a glossy way, but in a "this was built by people who know what they're doing" way
5. Not be able to mistake this for any other dashboard product on the market

If a screenshot of this dashboard, isolated and unbranded, would not cause a trader to ask "what is that?" — the implementation has failed the spec.

---

## 11 · What v1 Did Right (preserve)

- Wiring contracts (WebSocket → Zustand → Canvas) — keep entirely
- 30-row footprint density default — keep
- Replay control set (Prev/Play/Pause/Next + speed + session) — keep functionally
- 3-column shell (asymmetric weight changes, but the shell stays)
- TYPE_A pulse concept (intensify per §4.1)

## 12 · What v1 Got Wrong (drop)

- Mixing two fonts (Inter + JetBrains Mono) — diluted the terminal feel
- `#0a0a0f` background — neither black nor distinctive
- Generic shadcn ScoreWidget layout — no signature element
- Even-density 3-column (no hero) — no visual hierarchy
- Flat shadcn badges for signals — no presence, no animation
- 13px everywhere — no scale variety, nothing draws the eye
- No texture / atmosphere — looks like an unfinished demo

---

*This contract supersedes 11-UI-SPEC.md for Phase 11.2 implementation. Stack constraints (Next.js 15, Tailwind v4, shadcn, LW Charts v5.1, WebSocket, Zustand) and functional wiring are unchanged. A planner reading this should produce 3–4 sequential plans: (1) atmosphere + tokens + layout shell, (2) Confluence Pulse hero + Kronos + Zone List, (3) Footprint renderer rewrite + signal/tape rewrite, (4) replay restyle + acceptance pass.*
