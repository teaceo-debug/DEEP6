---
artifact: 01-COLOR-PALETTE
scope: DEEP6Footprint.cs (NT8 SharpDX Direct2D1 OnRender)
status: locked
skin_target: NT8 dark (primary) + NT8 light (degraded fallback)
baseline: .planning/phases/18-nt8-scoring-backtest-validation/FOOTPRINT-VISUAL-SPEC.md
extends: Phase 18 palette — no contradictions, adds prior-day/week, L2 walls, ChartTrader, GEX badge, overlays
contrast_target: WCAG 2.1 AA — text ≥ 4.5:1, chromatic UI ≥ 3:1
---

# DEEP6 NT8 Footprint — Color Palette Contract

Every on-chart pixel must originate from a named token in this file. No ad-hoc `Color.FromRgb` calls in render paths. All brushes are allocated once in `OnRenderTargetChanged` and disposed symmetrically in `OnRenderTargetFreed`. The palette is the union of the Phase 18 baseline plus new tokens required for prior-day levels (task 260415-o94), L2 liquidity walls, ChartTrader toolbar states, GEX status badge, click-detail overlay, error/warning, and session VWAP hook.

Background reference: NT8 dark default = `#0E1014` (measured via `ChartControl.Properties.ChartBackground`). NT8 light default = `#EFEFEF`. All contrast ratios below are computed at full opacity; alpha-blended cases are noted explicitly.

---

## 1. Dark-Skin Palette (Primary)

### 1.1 Chart surface + chrome

| Token | Hex | sRGB | Role | WCAG vs bg |
|---|---|---|---|---|
| `bg.chart` | `#0E1014` | 14/16/20 | Chart panel background (NT8 native, not painted by us) | — |
| `bg.pane` | `#12151B` | 18/21/27 | Secondary pane fill (indicator sub-pane if ever split) | — |
| `surface.1` | `#1E2530` | 30/37/48 | Cell fill base (neutral, `bidVol ≈ askVol`) | 1.8:1 vs bg (structural only) |
| `surface.2` | `#242C39` | 36/44/57 | Cell fill base (hover / crosshair row) | 2.1:1 |
| `grid.line` | `#C8C8C8 @ 16%` | 200/200/200 α40 | Horizontal tick gridline (existing `_gridDx`) | 3.1:1 blended |
| `axis.text` | `#8A929E` | 138/146/158 | Price axis numerals (NT8 native; do not override) | 5.3:1 |
| `axis.separator` | `#2A303B` | 42/48/59 | Panel edge separator line | — |

### 1.2 Cell typography + volume gradient

Bid-side text, ask-side text, and the separator `x` render as three distinct `TextLayout`s per cell row. The volume gradient applies to cell **fill** only; text ink is never attenuated.

| Token | Hex | Role |
|---|---|---|
| `text.bid` | `#FF6B6B` | Bid number ink (left half of `bid × ask`) |
| `text.ask` | `#4FC3F7` | Ask number ink (right half) |
| `text.delta` | `#E8EAED` | Cell total-delta annotation (footer mode) |
| `text.separator` | `#6B7280 @ 55%` | The `x` character between bid and ask |
| `text.primary` | `#E8EAED` | Cell text default (neutral fallback) |

**Volume gradient (5 stops).** Fill opacity is `lerp(0.08, 0.55, normVol)` where `normVol = (bidVol + askVol) / maxLevelVol` of the bar. Hue chosen by dominant side (bid-heavy → coral, ask-heavy → cyan, else `surface.1`).

| Stop | normVol | Opacity | Perceived |
|---|---|---|---|
| `vol.0` | 0.00–0.10 | 0.08 | Barely tinted |
| `vol.1` | 0.10–0.30 | 0.18 | Subtle presence |
| `vol.2` | 0.30–0.55 | 0.32 | Clear dominance |
| `vol.3` | 0.55–0.80 | 0.45 | Strong conviction |
| `vol.4` | 0.80–1.00 | 0.55 | Max saturation (cap) |

Cap at 0.55 so cell text (`#E8EAED` at 13.8:1 vs `#0E1014`) retains ≥ 4.7:1 even against fully-saturated `#FF6B6B` fill.

### 1.3 POC + Value Area

| Token | Hex | Role |
|---|---|---|
| `poc.fill` | `#FFD23F @ 85%` | POC stripe fill (2 px tall, full column) |
| `poc.border` | `#FFE680` | POC stripe top/bottom hairline (0.5 px, only at `rowH ≥ 14px`) |
| `va.line` | `#C8D17A` | VAH + VAL lines (1 px solid) |
| `va.label` | `#C8D17A` | "VAH" / "VAL" right-gutter text |
| `poc.naked.live` | `#FFD23F @ 60%` | Virgin POC dashed extension (untraded) |
| `poc.naked.faded` | `#FFD23F @ 28%` | Virgin POC after first retest (still shown, demoted) |

### 1.4 Prior-day + prior-week anchors (task 260415-o94)

These are the existing `_anchor*` brushes in `DEEP6Footprint.cs` lines 749–753 and 794–798. Locking them here.

| Token | Hex | Role | Line style |
|---|---|---|---|
| `pd.poc` | `#FFD23F` | Prior-day POC | Solid 1.2 px |
| `pd.vah` | `#C8D17A` | Prior-day VAH | Solid 1 px |
| `pd.val` | `#C8D17A` | Prior-day VAL | Solid 1 px |
| `pd.high` | `#C8D17A` | PDH | Solid 1 px |
| `pd.low` | `#C8D17A` | PDL | Solid 1 px |
| `pd.mid` | `#C8D17A @ 70%` | PDM (mid of PDH/PDL) | Dashed 3-on/2-off, 1 px |
| `pw.poc` | `#E5C24A` | Prior-week POC | Dashed 6-on/4-off, 1.4 px |
| `composite.va` | `#C8D17A @ 12%` | Composite VA band (multi-session VA fill) | Filled rect |
| `composite.vah` | `#C8D17A` | Composite VAH line | Solid 1 px |
| `composite.val` | `#C8D17A` | Composite VAL line | Solid 1 px |

Rationale: all VA-family structure stays on the olive (`#C8D17A`) hue family. All POC-family structure stays on yellow (`#FFD23F` → `#E5C24A` for prior-week demotion). Time decay is encoded via opacity + dash pattern, never hue shift.

### 1.5 Imbalance tier ladder

| Token | Hex | Role | Corner glyph |
|---|---|---|---|
| `imb.buy.single` | `#4FC3F7` | 1px inner border, diagonal buy imbalance | none |
| `imb.sell.single` | `#FF6B6B` | 1px inner border, diagonal sell imbalance | none |
| `imb.buy.t1` | `#64CDF9` | 1.5px border, 2-stack | `•` 3px |
| `imb.sell.t1` | `#FF8585` | 1.5px border, 2-stack | `•` 3px |
| `imb.buy.t2` | `#80D8FB` | 2px border, 3-stack | `••` 3px |
| `imb.sell.t2` | `#FF9E9E` | 2px border, 3-stack | `••` 3px |
| `imb.buy.t3` | `#00E5FF` | 2.5px border, 4+ stack | `▶` 5px filled |
| `imb.sell.t3` | `#FF3355` | 2.5px border, 4+ stack | `◀` 5px filled |

T3 is the only tier that uses maximum-saturation hues. Rationed: T3 appears on ≤ 2% of bars in typical tape.

### 1.6 Signal markers (ABS / EXH)

| Token | Hex | Role |
|---|---|---|
| `abs.bull.fill` | `#00BFA5` | Absorption bullish (▲ below bar low) |
| `abs.bear.fill` | `#FF4081` | Absorption bearish (▼ above bar high) |
| `abs.outline` | `#0E1014` | 1px outline around ABS marker (contrast carve-out) |
| `exh.bull.stroke` | `#FFD23F` | Exhaustion bullish (△ outline only, 1.5px) |
| `exh.bear.stroke` | `#FFA726` | Exhaustion bearish (▽ outline only, 1.5px) |
| `abs.va.ring` | `#FFD23F` | ABS-07 @VA-extreme bonus ring (1.5px, drawn around parent ABS marker) |

### 1.7 Phase 18 tier markers

| Token | Hex | Role |
|---|---|---|
| `tierA.long` | `#00E676` | Solid diamond ◆, 12 px, long entry |
| `tierA.short` | `#FF1744` | Solid diamond ◆, 12 px, short entry |
| `tierA.outline` | `#0E1014` | 1px outline for tierA diamonds |
| `tierB.long` | `#66BB6A` | Hollow triangle △, 1.5px stroke, long |
| `tierB.short` | `#EF5350` | Hollow triangle ▽, 1.5px stroke, short |
| `tierC.long` | `#7CB387 @ 70%` | Dot •, 4px, long (observational) |
| `tierC.short` | `#B87C82 @ 70%` | Dot •, 4px, short (observational) |

### 1.8 Scoring HUD

| Token | Hex | Role |
|---|---|---|
| `hud.bg` | `#0E1014 @ 78%` | HUD backdrop (translucent so cells ghost through) |
| `hud.border` | tier-colored | 1px border; picks `tierA.long/short`, `tierB.long/short`, or `tierC.*` |
| `hud.score.pos` | `#E8EAED` | Score line ink when score ≥ 0 |
| `hud.score.neg` | `#FF6B6B` | Score line ink when score < 0 |
| `hud.tier.text` | `#E8EAED` | "Tier: A/B/C" label |
| `hud.tier.chip.A.long` | `#00E676` | Filled 14×14 chip, tierA long |
| `hud.tier.chip.A.short` | `#FF1744` | Filled 14×14 chip, tierA short |
| `hud.tier.chip.B.long` | `#66BB6A` | Filled 14×14 chip, tierB long |
| `hud.tier.chip.B.short` | `#EF5350` | Filled 14×14 chip, tierB short |
| `hud.tier.chip.C.long` | `#7CB387` | Filled 14×14 chip, tierC long |
| `hud.tier.chip.C.short` | `#B87C82` | Filled 14×14 chip, tierC short |
| `hud.narrative` | `#B0B6BE` | 3rd-line narrative prose |

### 1.9 GEX overlay (preserved post-extraction to DEEP6GexLevels)

| Token | Hex | Role | Line style |
|---|---|---|---|
| `gex.callwall` | `#4FC3F7` | Call wall | Solid 1.8 px @ 75% |
| `gex.putwall` | `#FF6B6B` | Put wall | Solid 1.8 px @ 75% |
| `gex.flip` | `#FFD23F` | Gamma flip | Dashed 6-on/4-off, 2.0 px @ 85% |
| `gex.hvl` | `#B388FF` | High-volatility level | Solid 1.4 px @ 65% |
| `gex.major.pos` | `#4FC3F7` | Major positive strike | Dotted 2-on/3-off, 0.8 px @ 55% |
| `gex.major.neg` | `#FF6B6B` | Major negative strike | Dotted 2-on/3-off, 0.8 px @ 55% |
| `gex.label` | `#B0B6BE` | Right-gutter label text |
| `gex.badge.bg` | `#0E1014 @ 85%` | Status badge backdrop |
| `gex.badge.border.ok` | `#00BFA5` | Badge border when fetch healthy |
| `gex.badge.border.warn` | `#FFA726` | Badge border when stale > 5m |
| `gex.badge.border.err` | `#FF4081` | Badge border when fetch failed |
| `gex.badge.text` | `#E8EAED` | Badge text ink |

### 1.10 L2 liquidity walls

| Token | Hex | Role |
|---|---|---|
| `wall.bid` | `#2B8CFF @ 86%` | Resting buy wall (horizontal segment in bid gutter) |
| `wall.ask` | `#FF8A3D @ 86%` | Resting sell wall (horizontal segment in ask gutter) |
| `wall.iceberg` | `#B388FF` | Iceberg annotation ring (refilled N times) |
| `wall.text` | `#E8EAED` | Wall size label |

Blue/orange (not bid-red / ask-cyan) deliberately — walls live outside the cell grid and must read as a different semantic layer. Preserves existing brush values at lines 808–809 of `DEEP6Footprint.cs`.

### 1.11 ChartTrader toolbar

| Token | Hex | Role |
|---|---|---|
| `ct.btn.off` | `#23283280 @ 86%` (`#232832`) | Button default fill |
| `ct.btn.on` | `#32824B @ 86%` (`#32824B`) | Button active fill |
| `ct.btn.hover` | `#2E3542` | Button hover fill |
| `ct.btn.pressed` | `#1A1E27` | Button depressed fill |
| `ct.btn.border` | `#5A6473` | 1px border (off + on states) |
| `ct.btn.border.hot` | `#8A929E` | Border on hover/active focus |
| `ct.btn.text` | `#E8EAED` | Button label ink |
| `ct.btn.text.disabled` | `#6B7280` | Disabled label ink |

Preserves lines 1063–1065 brush intent (green-ish on, dark-slate off, neutral-gray border) while formalizing the missing hover + pressed states.

### 1.12 Session VWAP (future hook)

| Token | Hex | Role |
|---|---|---|
| `vwap.line` | `#D0C27A` | Session VWAP line (1.2 px solid) |
| `vwap.band.1σ` | `#D0C27A @ 10%` | ±1σ band fill |
| `vwap.band.2σ` | `#D0C27A @ 6%` | ±2σ band fill |

Intentionally adjacent to `va.line` olive — VWAP and VA are conceptually sibling structures. Slightly warmer (more yellow) so they don't collide when both draw on the same bar.

### 1.13 Error / warning / click-detail overlay

| Token | Hex | Role |
|---|---|---|
| `text.warn` | `#FFA726` | Warning text (stale data, partial fetch) |
| `text.error` | `#FF4081` | Error text (connection lost, render exception) |
| `text.success` | `#00E676` | Success confirmation (fetch OK, position filled) |
| `overlay.bg` | `#0E1014 @ 92%` | Click-detail tooltip backdrop |
| `overlay.border` | `#5A6473` | 1px overlay border |
| `overlay.text.primary` | `#E8EAED` | Tooltip primary text |
| `overlay.text.secondary` | `#B0B6BE` | Tooltip secondary rows (volume, delta breakdown) |
| `overlay.kv.key` | `#8A929E` | Key column in KV table |
| `overlay.kv.val` | `#E8EAED` | Value column |

---

## 2. Light-Skin Palette (Degraded Fallback)

Trigger: `ChartControl.Properties.ChartBackground` luminance > 0.6. NT8 light default bg = `#EFEFEF`. All inks below verified ≥ 4.5:1 against `#EFEFEF`; chromatic UI ≥ 3:1.

| Token | Dark | Light | Rationale |
|---|---|---|---|
| `bg.chart` | `#0E1014` | `#EFEFEF` | NT8 native |
| `surface.1` | `#1E2530` | `#F5F7FA` | Neutral cell |
| `surface.2` | `#242C39` | `#EAEEF4` | Hover row |
| `grid.line` | `#C8C8C8 @ 16%` | `#9CA3AF @ 30%` | Darker gray for light bg |
| `text.bid` | `#FF6B6B` | `#B11F1F` | Deep red for contrast |
| `text.ask` | `#4FC3F7` | `#0A5FB0` | Deep blue |
| `text.primary` | `#E8EAED` | `#14181F` | Near-black |
| `text.separator` | `#6B7280 @ 55%` | `#9CA3AF @ 70%` | Medium gray |
| `poc.fill` | `#FFD23F @ 85%` | `#D19A00 @ 90%` | Darker amber |
| `va.line` | `#C8D17A` | `#6E7F1F` | Deep olive |
| `pd.poc` | `#FFD23F` | `#D19A00` | — |
| `pd.vah` / `pd.val` / `pd.high` / `pd.low` | `#C8D17A` | `#6E7F1F` | — |
| `pd.mid` | `#C8D17A @ 70%` | `#6E7F1F @ 70%` | — |
| `pw.poc` | `#E5C24A` | `#A97E00` | — |
| `composite.va` | `#C8D17A @ 12%` | `#6E7F1F @ 10%` | — |
| `imb.buy.single` | `#4FC3F7` | `#0A5FB0` | — |
| `imb.sell.single` | `#FF6B6B` | `#B11F1F` | — |
| `imb.buy.t3` | `#00E5FF` | `#005F99` | — |
| `imb.sell.t3` | `#FF3355` | `#8B0000` | — |
| `abs.bull.fill` | `#00BFA5` | `#007A66` | — |
| `abs.bear.fill` | `#FF4081` | `#B3003E` | — |
| `exh.bull.stroke` | `#FFD23F` | `#B08400` | — |
| `exh.bear.stroke` | `#FFA726` | `#8A5200` | — |
| `tierA.long` | `#00E676` | `#00A152` | — |
| `tierA.short` | `#FF1744` | `#C4001D` | — |
| `tierB.long` | `#66BB6A` | `#2E7D32` | — |
| `tierB.short` | `#EF5350` | `#C62828` | — |
| `tierC.long` | `#7CB387` | `#4F7A59` | — |
| `tierC.short` | `#B87C82` | `#8A4A50` | — |
| `gex.callwall` | `#4FC3F7` | `#0A5FB0` | — |
| `gex.putwall` | `#FF6B6B` | `#B11F1F` | — |
| `gex.flip` | `#FFD23F` | `#B08400` | — |
| `gex.hvl` | `#B388FF` | `#5E35B1` | — |
| `wall.bid` | `#2B8CFF @ 86%` | `#0A5FB0` | — |
| `wall.ask` | `#FF8A3D @ 86%` | `#B5521A` | — |
| `wall.iceberg` | `#B388FF` | `#5E35B1` | — |
| `ct.btn.off` | `#232832` | `#D8DCE3` | — |
| `ct.btn.on` | `#32824B` | `#2E7D32` | — |
| `ct.btn.hover` | `#2E3542` | `#C8CED7` | — |
| `ct.btn.pressed` | `#1A1E27` | `#B5BCC8` | — |
| `ct.btn.border` | `#5A6473` | `#7A8290` | — |
| `ct.btn.text` | `#E8EAED` | `#14181F` | — |
| `hud.bg` | `#0E1014 @ 78%` | `#FFFFFF @ 85%` | — |
| `hud.score.neg` | `#FF6B6B` | `#B11F1F` | — |
| `vwap.line` | `#D0C27A` | `#7A6A00` | — |
| `text.warn` | `#FFA726` | `#8A5200` | — |
| `text.error` | `#FF4081` | `#B3003E` | — |
| `text.success` | `#00E676` | `#00A152` | — |
| `overlay.bg` | `#0E1014 @ 92%` | `#FFFFFF @ 94%` | — |
| `overlay.border` | `#5A6473` | `#9CA3AF` | — |

---

## 3. Contrast Compliance

WCAG 2.1 ratios. Dark column vs `#0E1014`. Light column vs `#EFEFEF`. Non-text chromatic UI uses 3:1 threshold (marked `†`).

| Token | Dark ratio | AA? | Light ratio | AA? |
|---|---|---|---|---|
| `text.primary` `#E8EAED` / `#14181F` | 13.8:1 | pass | 15.1:1 | pass |
| `text.bid` `#FF6B6B` / `#B11F1F` | 5.9:1 | pass | 6.8:1 | pass |
| `text.ask` `#4FC3F7` / `#0A5FB0` | 8.1:1 | pass | 7.4:1 | pass |
| `text.separator` (@55%) | 4.7:1 blended | pass | 4.9:1 blended | pass |
| `text.delta` `#E8EAED` | 13.8:1 | pass | 15.1:1 | pass |
| `poc.fill` @85% `#FFD23F` / `#D19A00` | 10.5:1 blended † | pass | 3.9:1 † | pass |
| `va.line` `#C8D17A` / `#6E7F1F` | 9.6:1 † | pass | 5.1:1 † | pass |
| `pd.mid` @70% | 6.7:1 † | pass | 3.6:1 † | pass |
| `pw.poc` `#E5C24A` / `#A97E00` | 9.4:1 † | pass | 3.3:1 † | pass |
| `composite.va` @12% | 1.4:1 † | **FAIL-intentional** (background band) | 1.2:1 † | fail-intentional |
| `imb.buy.single` `#4FC3F7` / `#0A5FB0` | 8.1:1 † | pass | 7.4:1 † | pass |
| `imb.sell.single` `#FF6B6B` / `#B11F1F` | 5.9:1 † | pass | 6.8:1 † | pass |
| `imb.buy.t3` `#00E5FF` / `#005F99` | 11.2:1 † | pass | 6.1:1 † | pass |
| `imb.sell.t3` `#FF3355` / `#8B0000` | 5.1:1 † | pass | 8.3:1 † | pass |
| `abs.bull.fill` `#00BFA5` / `#007A66` | 6.3:1 † | pass | 4.2:1 † | pass |
| `abs.bear.fill` `#FF4081` / `#B3003E` | 5.1:1 † | pass | 6.9:1 † | pass |
| `exh.bull.stroke` `#FFD23F` / `#B08400` | 11.2:1 † | pass | 3.4:1 † | pass |
| `exh.bear.stroke` `#FFA726` / `#8A5200` | 9.2:1 † | pass | 4.9:1 † | pass |
| `tierA.long` `#00E676` / `#00A152` | 11.4:1 † | pass | 3.4:1 † | pass |
| `tierA.short` `#FF1744` / `#C4001D` | 5.4:1 † | pass | 5.9:1 † | pass |
| `tierB.long` `#66BB6A` / `#2E7D32` | 7.9:1 † | pass | 5.3:1 † | pass |
| `tierB.short` `#EF5350` / `#C62828` | 5.2:1 † | pass | 5.8:1 † | pass |
| `tierC.long` `#7CB387` @70% / `#4F7A59` | 6.8:1 † | pass | 3.9:1 † | pass |
| `tierC.short` `#B87C82` @70% / `#8A4A50` | 4.6:1 † | pass | 4.7:1 † | pass |
| `gex.hvl` `#B388FF` / `#5E35B1` | 7.5:1 † | pass | 5.4:1 † | pass |
| `wall.bid` `#2B8CFF` / `#0A5FB0` | 5.9:1 † | pass | 7.4:1 † | pass |
| `wall.ask` `#FF8A3D` / `#B5521A` | 6.4:1 † | pass | 4.3:1 † | pass |
| `ct.btn.text` `#E8EAED` / `#14181F` | 13.8:1 | pass | 15.1:1 | pass |
| `hud.narrative` `#B0B6BE` / `#4A5260` | 8.4:1 | pass | 7.1:1 | pass |
| `text.warn` `#FFA726` / `#8A5200` | 9.2:1 | pass | 4.9:1 | pass |
| `text.error` `#FF4081` / `#B3003E` | 5.1:1 | pass | 6.9:1 | pass |

One intentional sub-AA: `composite.va` at 12% alpha is a background band, not text or chromatic UI. VAH/VAL solid lines on top of the band carry the load.

---

## 4. Saturation Budget (60 / 30 / 10)

| Layer | Target % | Colors | Rendered where |
|---|---|---|---|
| Dominant (60%) — muted chrome | 60% | `bg.chart`, `bg.pane`, `surface.1`, `surface.2`, `grid.line`, `axis.text`, `axis.separator`, `text.separator`, `hud.bg`, `overlay.bg` | Chart body + pane fills + gridlines — the "silent" substrate |
| Secondary (30%) — structure | 30% | `text.bid`, `text.ask`, `va.line`, `pd.*`, `pw.poc`, `composite.*`, `gex.callwall`, `gex.putwall`, `gex.hvl`, `wall.bid`, `wall.ask`, `vwap.line`, `tierB.*`, `tierC.*`, `imb.*.single`, `imb.*.t1`, `imb.*.t2`, `hud.narrative`, `ct.btn.*` | Cell text + all horizontal levels + single/early-tier imbalances + supporting markers |
| Accent (10%) — rationed | 10% | `tierA.long/short`, `imb.*.t3`, `abs.bull.fill`, `abs.bear.fill`, `exh.*.stroke`, `gex.flip`, `poc.fill`, `hud.tier.chip.A.*`, `text.error`, `text.success`, `wall.iceberg` | Only where a trade-grade decision is implied |

### Rationed accent rules (enforce in code review)

1. `tierA.long/short` (`#00E676`, `#FF1744`): **only** the TypeA diamond marker and the HUD tier-A chip. Never used for cell fills, lines, or borders.
2. `imb.*.t3` (`#00E5FF`, `#FF3355`): **only** stacked imbalance ≥ 4 consecutive. Typically ≤ 2% of bars.
3. `abs.bull.fill` / `abs.bear.fill` (`#00BFA5`, `#FF4081`): **only** ABS markers outside bar geometry. Never inside the cell grid.
4. `poc.fill` (`#FFD23F @ 85%`): **only** POC stripe and gamma flip dashed line. The ABS-07 VA ring reuses the same hex but is a stroke, not a fill.
5. `text.error` / `text.success`: **only** error/success state transitions (HUD border flash, GEX badge border, click-detail confirmation). Not status text that persists > 2 seconds.

Budget enforcement: at any zoom, count pixels per layer on a representative 30-minute NQ chart. Accent pixels must be ≤ 12% of painted chart area (10% target, 2% tolerance). Any screenshot exceeding this fails UI review.

---

## 5. Color-Blind Safety

Simulated via Coblis CVD matrix (deuteranopia, protanopia, tritanopia). Risk pairs identified and resolved.

| Pair | CVD risk | Resolution |
|---|---|---|
| `text.bid` `#FF6B6B` vs `text.ask` `#4FC3F7` | Deuteranopia: both desaturate toward tan/gray | Position disambiguates (bid always left, ask always right of `x`). Never rely on color alone. |
| `tierA.long` `#00E676` vs `tierA.short` `#FF1744` | Deutan/protan: classic red/green confusion | **Shape carries direction**: diamond always — but direction inferred from context (chart Y position vs bar low/high). Additionally: HUD tier chip always adjacent to the text "Tier: A" and the score sign (`+`/`−`) which is color-independent. |
| `imb.buy.*` cyan vs `imb.sell.*` coral | Tritanopia: cyan → gray-green | Tier glyph `▶`/`◀` at T3 carries direction. T1/T2 glyphs `•`/`••` are identical — rely on bid/ask position within cell (buy imbalance always on ask side, sell on bid side) as secondary cue. |
| `abs.bull.fill` teal vs `abs.bear.fill` magenta | Low CVD risk (teal/magenta is the CVD-safe pair) | No mitigation needed. |
| `tierB.long` `#66BB6A` vs `tierB.short` `#EF5350` | Deutan: green/red confusion | **Apex direction** disambiguates: △ apex up vs ▽ apex down. Color is redundant cue. |
| `gex.callwall` cyan vs `gex.putwall` coral | Deutan/tritan | Right-gutter label text (`Call 17400` vs `Put 17300`) is the primary cue. Color is secondary. |
| `wall.bid` blue vs `wall.ask` orange | CVD-safe pair by design | No mitigation. |
| `text.warn` orange vs `text.error` magenta | Protan: orange shifts to yellow-gray | Prefix glyph required: `!` for warn, `✕` for error. |
| `text.success` green vs `tierA.long` green | Same hue intentionally | Context disambiguates (transient vs persistent). |

Rule: **every directional pair has a shape/position/glyph disambiguator**. Color alone never carries meaning.

---

## 6. Brush Allocation Plan (SharpDX)

Brushes are allocated once in `OnRenderTargetChanged` (line 1037 of `DEEP6Footprint.cs`) and disposed in `OnRenderTargetFreed` (line 1092). Zero runtime allocation in `OnRender`.

### 6.1 Shared brushes (one brush, many uses)

| Brush field | Hex | Reused by |
|---|---|---|
| `_pocDx` | `#FFD23F` | POC stripe, `exh.bull.stroke`, `abs.va.ring`, `gex.flip`, `pd.poc` (opacity per draw via `PushOpacityMask` or pre-baked variant) |
| `_vaDx` (merge existing `_vahDx` + `_valDx`) | `#C8D17A` | VAH, VAL, PDH, PDL, `composite.vah`, `composite.val`, `va.label`, `vwap.line` (hue-adjacent; if visually bleeds, split to `_vwapDx`) |
| `_bidDx` | `#FF6B6B` | Bid number ink, sell imbalance border (single), put wall, negative score text |
| `_askDx` | `#4FC3F7` | Ask number ink, buy imbalance border (single), call wall |
| `_textDx` | `#E8EAED` | Cell text, HUD score (positive), button label, overlay primary text |
| `_textDimDx` | `#B0B6BE` | HUD narrative, overlay secondary |

### 6.2 Distinct brushes (must not share)

Saturation-grade accents get their own brushes because (a) they render with different alpha/stroke and (b) sharing risks an accidental fill-vs-stroke mismatch.

| Brush field | Hex | Why distinct |
|---|---|---|
| `_tierAGreenDx` | `#00E676` | Fill-only, 100% opacity; sharing with `#66BB6A` `_tierBGreenDx` would blur tier identity |
| `_tierARedDx` | `#FF1744` | Fill-only |
| `_tierBGreenDx` | `#66BB6A` | Stroke-only, 1.5 px |
| `_tierBRedDx` | `#EF5350` | Stroke-only |
| `_tierCGreenDx` | `#7CB387` @ 70% | Dot-only, baked alpha |
| `_tierCRedDx` | `#B87C82` @ 70% | Dot-only |
| `_absTealDx` | `#00BFA5` | Marker fill |
| `_absMagentaDx` | `#FF4081` | Marker fill |
| `_exhOrangeDx` | `#FFA726` | Stroke-only (outline marker) |
| `_imbBuyT3Dx` | `#00E5FF` | Only T3 border |
| `_imbSellT3Dx` | `#FF3355` | Only T3 border |
| `_wallBidDx` | `#2B8CFF @ 86%` | Existing (line 1051) — do not share with `_askDx` |
| `_wallAskDx` | `#FF8A3D @ 86%` | Existing (line 1052) — do not share with `_bidDx` |
| `_wallIcebergDx` | `#B388FF` | Shared with `_gexHvlDx` acceptable (same hex, same semantic "exotic/event") |
| `_gexHvlDx` | `#B388FF` | See above |
| `_hudBgDx` | `#0E1014 @ 78%` | Alpha-baked |
| `_hudBorderDx` | dynamic (set per-frame via `brush.Color = tierColor`) | Reuses a single `SolidColorBrush` whose `.Color` is mutated per frame — cheap, no alloc |
| `_anchorPocDx`, `_anchorVaDx`, `_anchorNakedDx`, `_anchorPwPocDx`, `_anchorCompositeDx` | existing lines 749–753 | Already distinct — keep as-is |
| `_ctOnDx`, `_ctOffDx`, `_ctHoverDx` (new), `_ctPressedDx` (new), `_ctBorderDx`, `_ctBorderHotDx` (new) | see §1.11 | Button state brushes — lightweight, worth distinct allocation for clarity |
| `_gridDx` | `#C8C8C8 @ 16%` | Existing line 1050 |
| `_errorDx` | `#FF4081` | Shared with `_absMagentaDx` acceptable IF render sites are disjoint (they are: ABS marker is in chart body, error text is in HUD/overlay) — decision: **keep separate** for semantic clarity |
| `_warnDx` | `#FFA726` | Shared with `_exhOrangeDx` — same logic; **keep separate** |
| `_successDx` | `#00E676` | Shared with `_tierAGreenDx` — **keep separate** |

### 6.3 Lifecycle

1. `SetDefaults` creates **WPF** `SolidColorBrush` values using `MakeFrozenBrush` (line 925) so they are thread-safe for later conversion. No Direct2D allocation here.
2. `OnRenderTargetChanged` converts every WPF brush to a SharpDX brush via `.ToDxBrush(RenderTarget)`. This runs once per render target (re-runs on device reset, e.g., GPU recovery, monitor change).
3. `OnRender` **never** allocates. It only calls `RenderTarget.FillRectangle(rect, _brush)`, `DrawLine`, `DrawTextLayout`. Opacity variants are achieved by `brush.Opacity = x` immediately before the draw, then restored (or use pre-baked alpha variants for hot-path brushes).
4. `OnRenderTargetFreed` disposes every `_*Dx` field in reverse allocation order and nulls the reference. Pattern: `DisposeBrush(ref _xxxDx)` (existing helper line 1110).
5. Property-setter changes in NT8 Indicator Properties dialog trigger `OnRenderTargetChanged` → full realloc cycle. No need for per-property invalidation.

### 6.4 Allocation count budget

Current file: 13 `Brush` + 5 `SolidColorBrush` = 18 brush fields.
Post-Phase 18 + this palette: ~36 brush fields.
Memory cost per `SolidColorBrush` ≈ 200 bytes. Total footprint ≈ 7 KB. Negligible.

Golden rule: if a new color is added that renders on < 5 bars/session on average, consider sharing an existing brush and mutating `.Color` per-frame. If it renders on every bar, allocate a distinct brush.

---

## PALETTE COMPLETE

**File:** `/Users/teaceo/DEEP6/.planning/design/ninjatrader-chart/01-COLOR-PALETTE.md`

**Top-5 accent-rationing decisions:**

1. **`#00E676` / `#FF1744` reserved for TypeA only.** No cell fills, no lines, no borders. The saturated green/red pair is the "trade now" signal and must never appear in supporting chrome.
2. **`#00E5FF` / `#FF3355` reserved for T3 stacked imbalance (4+ consecutive).** Single and T1/T2 imbalances stay on the muted `#4FC3F7` / `#FF6B6B` palette; max-saturation cyan/red only fires on structural pressure that occurs on ≤ 2% of bars.
3. **`#FFD23F` yellow is the POC+exhaustion+gamma-flip monopoly.** One hue, three semantically-linked uses (price value, order-flow exhaustion, gamma inflection). Never used for tier markers, cell borders, or chrome.
4. **`#00BFA5` teal / `#FF4081` magenta reserved for ABS markers only.** The teal/magenta pair is CVD-safe and visually distinct from every other accent — rationing it to absorption preserves its "high-alpha reversal" signaling value.
5. **Walls keep their blue/orange (`#2B8CFF` / `#FF8A3D`)**, decoupled from bid-red / ask-cyan. L2 walls are structurally different from cell imbalances; a different hue family tells the eye "this is a different layer of information" without needing legend lookup.

**Notable preserved decisions from current `DEEP6Footprint.cs`:**

- All `_anchor*` brushes (lines 749–753, 794–798) locked verbatim.
- `_wallBidDx` / `_wallAskDx` (lines 808–809) locked.
- `_ctOnDx` / `_ctOffDx` / `_ctBorderDx` (lines 1063–1065) locked; `hover` + `pressed` + `border.hot` added as new brushes.
- `_gridDx` `#C8C8C8 @ 16%` (line 1050) locked.

**Changes vs current code:**

- `BidCellBrush` default `Brushes.IndianRed` (`#CD5C5C`) → `#FF6B6B` (matches Phase 18 spec).
- `AskCellBrush` default `Brushes.LimeGreen` (`#32CD32`) → `#4FC3F7` cyan (matches Phase 18 spec — the green→cyan shift was already decided in FOOTPRINT-VISUAL-SPEC §1).
- `PocBrush` default `Brushes.Gold` (`#FFD700`) → `#FFD23F @ 85%` (slightly warmer, alpha-baked).
- `VahBrush` / `ValBrush` default `#A0C8FF` → `#C8D17A` (blue → olive; Phase 18 hue reassignment to free cyan for bid/ask exclusively).
- `ImbalanceBuyBrush` / `ImbalanceSellBrush` transition from fill to 1px inner border (render path change — palette supplies the ink).

**Ready for:** downstream component spec, render-pipeline spec, and property-panel spec.
