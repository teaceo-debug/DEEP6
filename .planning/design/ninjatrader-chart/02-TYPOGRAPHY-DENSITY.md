---
artifact: 02-TYPOGRAPHY-DENSITY
phase: ninjatrader-chart-design
status: draft
supersedes: none
extends: ../../phases/18-nt8-scoring-backtest-validation/FOOTPRINT-VISUAL-SPEC.md §1, §6, §10
audience: ninjascript executor (DEEP6Footprint.cs SharpDX Direct2D1 / DirectWrite)
skin_target: NT8 dark default (primary) + NT8 light (must degrade)
---

# DEEP6 Footprint — Typography & Information-Density Specification

This spec defines the complete type system and density contract for `DEEP6Footprint.cs`. It extends the baseline from `FOOTPRINT-VISUAL-SPEC.md` (which locked `Consolas` for cells, `Segoe UI` for chrome, `bid x ask` cell format, 10–11pt cells, 2px inset, HUD three-line layout). It does not contradict any decision there. Where the baseline left a gap (zoom degradation matrix, density budgets, bold-on-threshold, 8pt / 14pt / 16pt scale slots, system fallbacks), this document closes it.

The only metric that matters: a professional NQ tape reader must parse a cell, a level label, and the HUD in a **single saccade** (≈250ms) during fast tape. Every rule below is in service of that constraint.

---

## 1. Font Stack

### Monospace (all numeric content)

```
"Consolas", "Cascadia Mono", "Menlo", "Courier New", monospace
```

| Platform | Resolved family | Notes |
|---|---|---|
| Windows 10/11 (primary NT8 host) | Consolas | Ships since Vista; hinting optimized for small sizes; ClearType-tuned |
| Windows Server / LTSC (rare) | Cascadia Mono | Windows Terminal font; installed on modern NT8 boxes |
| macOS (NT8 via Parallels/CrossOver) | Menlo | Apple's Consolas analog; same x-height class |
| Linux / Wine (edge case) | Courier New | Universal fallback; inferior rendering but guaranteed present |

**Why monospace for all numbers:** footprint cells are rendered as `bid x ask` where bid and ask can each be 1–5 digits. In a proportional font, `1 x 9` and `99 x 999` occupy different horizontal envelopes, and the eye has to re-parse the `x` anchor on every row. Monospace makes the separator stable at a fixed column fraction — the reader's eye fixates on the separator once and reads left/right halves in parallel. This is the single largest legibility gain in the entire chart.

Applied to: cell `bid x ask`, HUD score line, vPOC tick-count annotation, prior-day prices in level labels, delta-mode net numbers.

### Sans-serif (all prose + chrome)

```
"Segoe UI", "Inter", "system-ui", "Arial", sans-serif
```

| Platform | Resolved family |
|---|---|
| Windows 10/11 | Segoe UI (ships since Vista, excellent sub-pixel at 9pt) |
| Windows + Inter installed | Segoe UI (no swap — Segoe UI's `tnum` feature is adequate; Inter kept as explicit fallback for admins who strip Segoe) |
| macOS | system-ui resolves to SF Pro |
| Linux | Arial / DejaVu Sans |

**Why sans for labels:** prose elements (`VAH`, `PD POC`, narrative `ABSORBED @VAH + CVD DIV`) are read as words, not digit sequences. Sans has better word shape at 9–10pt than monospace. Segoe UI at 9pt has ~6.2 px x-height — the minimum the eye can word-read without pausing.

**Never mix inside a single element.** The HUD tier chip row uses Segoe UI (`Tier: A`) because `A` is a label, not a number. The HUD score row uses Consolas (`Score: +0.87`) because `+0.87` is a measurement. These are different cognitive channels.

### DirectWrite allocation

Reuse the Phase 16 font pool; add one format per new size introduced below. Zero runtime allocation in `OnRender`.

```
_cellFont10       Consolas 10pt  400   (cells, normal zoom)
_cellFont11       Consolas 11pt  400   (cells, wide zoom)
_cellFont11Bold   Consolas 11pt  700   (bold-on-threshold; see §9)
_glyphFont8       Segoe UI 8pt   400   (imbalance corner glyph, vPOC tick annotation)
_labelFont9       Segoe UI 9pt   400   (level labels, narrative, GEX gutter)
_labelFont9Med    Segoe UI 9pt   500   (VAH/VAL labels, tier chip letter)
_hudScoreFont     Consolas 12pt  600   (HUD line 1 normal)
_hudScoreFontEmph Consolas 14pt  700   (HUD line 1 when TypeA fired)
_hudTierFont      Segoe UI 11pt  600   (HUD line 2)
_detailTitleFont  Segoe UI 16pt  600   (click-detail overlay title — deferred, see §7)
```

Total: 10 `TextFormat` objects, allocated in `OnRenderTargetChanged`, disposed in `OnRenderTargetChanged`'s dispose path.

---

## 2. Size Scale (8pt → 16pt)

Exactly seven slots. No other sizes permitted.

| pt | px @ 96 DPI | Element | Font | Weight | Rationale |
|----|-------------|---------|------|--------|-----------|
| 8  | 10.7 | Imbalance corner glyph (`•`, `••`, `▶`/`◀`); vPOC tick-count annotation (`"12"` next to vPOC line) | Segoe UI | 400 | Glyphs are iconographic — readable below word-reading threshold |
| 9  | 12.0 | TypeA narrative label; VAH/VAL gutter labels; GEX level labels; naked-POC label; prior-day level labels (PDH, PDL, PD POC); Chart Trader button captions | Segoe UI | 400 (narr/PD) / 500 (VAH/VAL) | Minimum word-reading size in fast tape |
| 10 | 13.3 | Cell `bid x ask` at normal zoom (`rowH ≤ 14px`); HUD line 3 narrative | Consolas (cells) / Segoe UI (narr) | 400 | Baseline cell legibility; matches NT8 default bar density |
| 11 | 14.7 | Cell `bid x ask` at wide zoom (`rowH ≥ 15px`); HUD line 2 tier text | Consolas (cells) / Segoe UI (tier) | 400 / 600 | Upgrade path when user zooms in; no added allocation at smaller zooms |
| 12 | 16.0 | HUD line 1 score (`Score: +0.87`); tier chip letter when chip is 14×14px | Consolas (score) / Segoe UI (chip) | 600 | Primary HUD reading target — glanceable from peripheral vision |
| 14 | 18.7 | HUD line 1 score **when TypeA just fired** (first 3 seconds of bar after tier crossing); emphasis form only | Consolas | 700 | Transient attention pull; auto-decays to 12pt after 3s |
| 16 | 21.3 | Click-detail overlay title (reserved; not in Phase 18 scope — see §7) | Segoe UI | 600 | Modal-scale type; only used on explicit user click |

**Why 8 is the floor:** below 8pt, Segoe UI at 96 DPI loses subpixel stroke contrast and becomes a smudge. The corner-glyph role (imbalance dots) is the only place 8pt is tolerable because the glyph is iconographic, not word-read.

**Why 14pt (not 13, not 15) for emphasis:** the step from 12 → 14 is perceptually "one size up" (≈17% larger x-height). Any smaller step fails the peripheral-vision test; any larger breaks the 62px HUD box height budget.

**Why 16pt for detail title only:** if we ever add a click-detail modal (e.g., click a cell to see tick-by-tick breakdown), 16pt title is the minimum "I am a heading" type. Not used anywhere in the live chart body.

---

## 3. Weight Hierarchy

Three weights maximum. Every additional weight trains the eye to notice — and we spend that budget deliberately.

| Weight | Numeric value | Reserved for |
|--------|---------------|--------------|
| Regular | 400 | All cell text (non-threshold); GEX gutter labels; narrative; PDH/PDL/PD POC prior-day labels |
| Medium | 500 | VAH/VAL labels; HUD tier chip letter (when rendered as text, not glyph); Chart Trader button captions; vPOC label |
| Bold | 700 | POC row `bid x ask` text; last-trade price row `bid x ask`; cell text when cell volume ≥ 2× bar median (bold-on-threshold, §9); HUD score line when TypeA just fired; T3 stacked-imbalance corner caret |

Semantic mapping — what bold *means* in this chart:

> "Bold = this number has a structural reason the trader must not miss."

Every bold text occurrence corresponds to a specific structural event. If the executor is tempted to bold something for decoration, the answer is no.

---

## 4. Cell Text Layout

### Format: `bid x ask` (single-row inline)

| Decision | Value | Rationale |
|---|---|---|
| Format string | `"{bid} x {ask}"` | Locked by baseline §1. ASCII lowercase `x` (U+0078), single spaces |
| Separator character | ` x ` (space-x-space) | Visually lighter than `|`; reads as "versus"; monospace keeps column-stable |
| Bid alignment | Right-aligned up to the separator | Bid digits grow leftward from a fixed center column |
| Ask alignment | Left-aligned from the separator | Ask digits grow rightward |
| Separator color | `#6B7280` @ 55% dark / `#9CA3AF` @ 70% light | Dim — the separator is scaffolding, not data |
| Left inset | 2 px | Matches baseline; leaves 1px breathing room inside border |
| Right inset | 2 px | Same |
| Vertical alignment | Centered within `rowH` via DirectWrite `ParagraphAlignment.Center` | No manual baseline math |
| Padding top/bottom | 0 px explicit (centering absorbs it) | |

**Rejected alternatives:**

- **`bid | ask`** — pipe reads as "separator" not "versus"; too visually heavy at 10pt.
- **Split-column (bid in left half, ask in right half)** — doubles `TextLayout` allocations per cell; at 400 visible cells per screen × 60 fps this thrashes DirectWrite's layout cache. The baseline's dual-ink single-layout approach (left half bid-ink, right half ask-ink, separator dim) is already correct; keep it.

### Row-height degradation table

| `rowH` | Cell text behavior |
|--------|---------------------|
| ≥ 15 px | `_cellFont11` (11pt); bold-on-threshold rules from §9 apply |
| 12–14 px | `_cellFont10` (10pt); bold-on-threshold rules from §9 apply |
| 10–11 px | `_cellFont10` (10pt); bold-on-threshold **suppressed** (no weight swap — not enough pixels for bold to read cleanly) |
| 8–9 px | **Color-only** — no text rendered. Cell fill + imbalance border only. |
| < 8 px | Cell suppressed entirely; bar drawn as a thin OHLC-style line (NT8 native fallback) |

This supersedes the baseline's "min row height to render text = 10 px" with a more graceful two-step degradation.

### Delta mode (future toggle — layout reserved)

When user flips `CellMode = Delta` (not in Phase 18; reserved):
- Same `bid x ask` layout replaced with single centered `±{netDelta}` string.
- Sign glyph `+` or `−` (U+2212, not ASCII hyphen) colored cyan / coral respectively.
- Same font, same insets, same degradation table.

---

## 5. Label Typography (Level Lines)

Horizontal level labels: PDH, PDL, PD POC, PD VAH, PD VAL, PW POC, PW VAH, PW VAL, vPOC, ONH, ONL, Globex H/L, and any session anchors.

| Property | Value |
|---|---|
| Position | Right gutter, anchored 4px inside chart frame (inside `panelRight - 4`) |
| Font | `_labelFont9Med` — Segoe UI 9pt 500 |
| Ink | Matches line color; text opacity 100% (line opacity 75%) — text must win pixel ownership |
| Background fill | `#0E1014` @ 72% dark / `#FFFFFF` @ 85% light, rounded rectangle |
| Background corner radius | 2 px |
| Background padding | 4 px left/right, 2 px top/bottom |
| Format | `"{label} {price:F2}"` — label and price together; e.g. `"PD POC 17345.25"` |
| Line-height | 1.0 (labels are single-line; no leading needed) |
| Horizontal position | Label right edge at `panelRight - 6`; label grows leftward |
| Vertical position | Label vertical center at line Y; line is clipped behind label bg to avoid stroke-through-text |
| Collision rule | If two labels within 14px vertical of each other, the lower-priority label offsets +16px and draws a 1px leader line from the price Y to the label |

**Priority order (highest reserves Y first):** POC > vPOC > PDH/PDL > PD POC > PD VAH/VAL > PW POC > ONH/ONL > Globex H/L.

**Why the price is included in the label (not redundant to the axis):** NT8 price axis shows every tick; tape readers scan labels faster than axis. Writing `PD POC 17345.25` inside the label means the eye reads level and price in one fixation.

**Line-height for multi-line labels** (e.g., narrative + price): 1.25 × font size. Applies only in HUD line 3 and click-detail overlay.

---

## 6. HUD Badge Typography Hierarchy

Extends baseline §6. The baseline locked the 3-line layout, 188×62 box, tier chip. This section locks the typographic specifics.

```
┌──────────────────────────────┐   ← 1px tier-colored border, radius 3px
│ Score: +0.87                 │   ← Consolas 12pt 600, ink #E8EAED (or #FF6B6B if neg)
│ Tier: A  ▇                   │   ← Segoe UI 11pt 600 + 14×14 chip, 6px gap
│ ABSORBED @VAH + CVD DIV      │   ← Segoe UI 9pt 400, ink #B0B6BE, ≤40 chars
└──────────────────────────────┘
```

| Property | Value |
|---|---|
| Line 1 → Line 2 gap | 4 px (baseline-to-baseline spacing = 18 px) |
| Line 2 → Line 3 gap | 3 px (baseline-to-baseline = 16 px) |
| Inner padding | 8 px left, 6 px top, 6 px right, 6 px bottom (baseline) |
| Corner radius | 3 px |
| Line 1 emphasis form | `_hudScoreFontEmph` Consolas 14pt 700 for 3 seconds after a TypeA tier crossing, then decay to 12pt 600. Decay is instant swap on next `OnRender` after `Now - tierFiredAt > 3s` |
| Line 2 tier chip | 14×14 px rounded rect, 2px radius, fill = tier color, drawn 6px to the right of `"Tier: A"` text end. Letter inside chip is **not rendered** (the text `A` already precedes it) |
| Line 3 truncation | Last word boundary ≤ 37 chars, append U+2026 (`…`). Never raw `...` |
| Line 3 ellipsis color | Same as line ink (`#B0B6BE`) — no color change |
| Score sign rule | Always signed: `+0.87`, `-0.87`, `+0.00` (never unsigned, never `0.87`) |
| Score decimal places | Exactly 2 |
| Score width | Fixed 6 characters (`+0.87` = 5 chars; 6 reserves one char for score > ±1.0) |

**When HUD is visible:** only when `|score| ≥ threshold_C` (TypeC threshold). Below that, HUD is hidden entirely — no "Score: +0.12 Tier: —" placeholder. This is the single biggest attention-drain preventer. See §7.

---

## 7. Density Targets

Miller's 7±2 applied to chart reading: a trader can hold about 5–9 active items in working memory at once. Every element above that count is cognitive tax.

### Per-screen budgets

| Element class | Max visible at once | Behavior at overflow |
|---|---|---|
| Horizontal level lines (PDH/PDL/PD POC/VAH/VAL/vPOC/GEX walls/HVL) | **6 active** | Fade non-essential to 35% opacity + hide label; priority = §5 order |
| Signal markers (ABS/EXH + tier markers) per 10-bar window | **3 active** | Suppress TypeC dots first; then TypeB triangles; never suppress TypeA |
| GEX lines rendered | 4 (Call Wall, Put Wall, Gamma Flip, HVL) | Fixed set; "Major positive/negative" only render when within ±0.5% of current price |
| Imbalance corner glyphs per 20-bar window | **6** | Rank by tier (T3 > T2 > T1); drop lowest-tier first |
| HUD badge | 1 (or 0) | Hidden when `|score| < threshold_C` |
| Click-detail overlay | 1 | Only on explicit click; auto-dismiss on next bar close |

### Attention drain preventers

1. **HUD visibility gate:** HUD only appears when score has crossed at least TypeC threshold. A constantly-visible HUD displaying low scores trains the eye to ignore it — when TypeA finally fires, the badge is no longer pre-attentive. Hiding it below threshold preserves the "something changed" signal.

2. **TypeA narrative 3-second emphasis:** Line 1 goes 14pt 700 for 3 seconds after tier crossing, then decays. The eye is drawn to the *change*, not the steady state.

3. **Level-line fade at count:** once 6 level lines are visible, the 7th and subsequent lines render at 35% opacity and drop their labels. User can override via `MaxVisibleLevels` property (default 6).

4. **TypeC suppression at density:** if 3 tier markers already exist in the last 10 bars, TypeC is suppressed entirely (not drawn). This is the only tier that suppresses; TypeA and TypeB always draw.

---

## 8. Legibility at Zoom (Test Matrix)

Three NT8 `BarWidth` settings, measured as effective `barPaintWidth` × `rowH`.

| Element | Zoom 50% (bw=2, barPaintW≈7px, rowH≈9px) | Zoom 100% (bw=3, barPaintW≈12px, rowH≈14px) | Zoom 200% (bw=5, barPaintW≈20px, rowH≈22px) |
|---|---|---|---|
| Cell `bid x ask` text | **Suppressed** (color-only cell) | `_cellFont10` 10pt | `_cellFont11` 11pt, bold-on-threshold active |
| Imbalance border | 1 px, drawn | 1 px, drawn | 1 px (T1) → 2.5 px (T3) |
| Imbalance corner glyph | Suppressed | 8pt glyph drawn | 8pt glyph drawn |
| POC fill stripe | Drawn, 1 px (degraded from 2) | Drawn, 2 px | Drawn, 2 px |
| VAH/VAL line | Drawn, no label | Drawn + label at session right edge | Drawn + label |
| Level labels (PDH, etc.) | Background only, no text | Full label + price | Full label + price |
| ABS/EXH marker | 8 px (degraded from 10) | 10 px | 12 px |
| Tier marker | 10 px TypeA; TypeB/C suppressed | 12 px TypeA / 10 px TypeB / 4 px TypeC | Same as 100% (no upscale — markers are landmarks, not charts) |
| TypeA narrative | Suppressed (callout leader only) | Inline, 9pt | Inline, 9pt |
| HUD badge | Drawn, full | Drawn, full | Drawn, full |
| GEX gutter labels | Label only if line within ±0.25% of price | All labels | All labels |

**Rule:** geometry scales with zoom, text does not (text sticks to the 8/9/10/11/12 pt slots). This is because the reader's eye has a fixed angular resolution regardless of chart zoom — making text larger at high zoom wastes space; making it smaller at low zoom loses legibility. Degrade by *suppression*, not by shrinking below 8pt.

---

## 9. Sierra Chart "Bold-on-Threshold" Pattern

Research from Sierra Chart, Bookmap, and ATAS converged on the same answer: in dense numeric cells, **weight** (not size, not color) is the least-disruptive way to flag significance. Color is already fully consumed by bid/ask/imbalance semantics; size would break the column grid; weight is an untapped channel.

### Threshold rules — when a cell flips from Regular (400) to Bold (700)

Evaluated in priority order. First match wins (a cell never escalates further once bold).

| Priority | Rule | Trigger condition | Rendered form |
|---|---|---|---|
| 1 | **Last-trade price row** | Cell at `Close[0]` on the most recent bar (`IsFirstTickOfBar` has not fired for next bar yet) | Both bid and ask numbers bold; separator stays dim |
| 2 | **POC row** | Cell at the bar's POC price (volume-weighted max across the bar's cells) | Both bid and ask numbers bold; separator stays dim — stacks with POC yellow stripe |
| 3 | **High-volume threshold** | `(cell.AskVol + cell.BidVol) ≥ 2.0 × bar.MedianCellVolume` AND `rowH ≥ 12 px` | Both bid and ask numbers bold |
| 4 | **Extreme-volume threshold** | `(cell.AskVol + cell.BidVol) ≥ 4.0 × bar.MedianCellVolume` AND `rowH ≥ 12 px` | Both bold + cell fill rank-opacity capped at 0.55 (already baseline rule; stacks) |

Rules 3 and 4 are gated on `rowH ≥ 12 px` because bold strokes at 10pt / rowH<12 muddy into the fill. At tight zoom, the bold signal is lost anyway — don't pay the allocation cost.

### Suppression rule

If more than 40% of cells in a single bar qualify for bold (rule 3 or 4), suppress the threshold — the bar is uniformly high-volume and bolding everything defeats the purpose. Keep only rules 1 and 2 (last-trade + POC) active.

### Implementation note

DirectWrite cannot swap weight mid-`TextLayout`. The executor must check the threshold per cell before allocating, and pick `_cellFont10` or a bold variant (`_cellFont10Bold`, added to the font pool below) at that point. Add:

```
_cellFont10Bold   Consolas 10pt  700
_cellFont11Bold   Consolas 11pt  700   (already declared in §1)
```

Two extra TextFormats; allocated once; zero runtime cost.

---

## Summary — Typographic Contract

| Channel | Meaning |
|---|---|
| Consolas | This is a number — trust its alignment |
| Segoe UI | This is a word — read its meaning |
| 8pt | Icon / glyph |
| 9pt | Chrome label |
| 10–11pt | Cell data |
| 12pt | HUD steady state |
| 14pt | HUD just-fired emphasis (3s transient) |
| 16pt | Modal title (reserved) |
| Regular (400) | Default |
| Medium (500) | Structure label (VAH/VAL, tier) |
| Bold (700) | Structural signal (last-trade, POC, high-vol cell, TypeA emphasis) |

Every pixel of text on the DEEP6 footprint chart falls into exactly one cell of this matrix. No other typographic variation is permitted.
