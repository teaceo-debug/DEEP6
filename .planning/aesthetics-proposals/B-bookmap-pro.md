# DEEP6 Aesthetic Direction B — "Bookmap-Pro"

**Author:** DEEP6 Visual Design Track
**Version:** 1.0 — 2026-04-16

## 1. Design Philosophy

Bookmap-Pro is a heatmap-first, edge-to-edge orderflow surface for traders who live in liquidity. Every pixel earns its place by encoding a measurable quantity — resting depth, traded aggression, absorption pressure, gamma — and nothing decorative survives. The screen is a near-black void (`#0E1014`) onto which only physical signals glow: cyan when buyers lift, magenta when sellers hit, amber when walls thicken, white-hot when something approaches a citadel. Footprint cells are not bordered boxes; they are *rectangles of light* sitting on top of the heatmap, semi-transparent so the underlying liquidity context bleeds through. There are no rounded corners, no gradients-for-decoration, no shadows. Just intensity, hue, and signal.

## 2. Surface tokens
- `surface.canvas` `#0E1014` 100% — main chart background (Bookmap-canonical)
- `surface.panel` `#13161A` 100% — HUD panels, tooltip backdrop
- `surface.elevated` `#1A1E25` 100% — score HUD, stats overlay
- `grid.faint` `#FFFFFF` α 8 — optional sub-grid (off by default)
- `grid.tickmajor` `#FFFFFF` α 18 — major tick grid (every $1 on NQ)
- `axis.line` `#262633` 100% — right-side price ladder divider
- `axis.text` `#8A929E` 100% — Y-axis price labels

## 3. Trade-dot semantic (Bookmap canonical)
- `dot.buy.core` `#00D4FF` — cyan, aggressive buy
- `dot.buy.halo` `#7DF9FF` α 110 — soft outer glow ring
- `dot.sell.core` `#FF36A3` — magenta, aggressive sell
- `dot.sell.halo` `#FF6BC1` α 110

## 4. Heatmap LUT (10 anchor stops, expanded to 256 in code)
| Position | Hex | Meaning |
|---|---|---|
| 0.00 | `#000000` | sub-cutoff floor |
| 0.05 | `#000A1F` | hint of cool |
| 0.20 | `#0F1B3A` | Bookmap deep blue |
| 0.35 | `#1E5FCE` | cooling wall |
| 0.50 | `#2E9988` | perceptual midpoint |
| 0.62 | `#F39200` | warming pressure |
| 0.75 | `#F08C1A` | heavy resting bid/ask |
| 0.88 | `#FF3D2E` | citadel-class wall |
| 0.97 | `#FF0000` | saturated peak |
| 1.00 | `#FFFFFF` | molten rim |

## 5. Imbalance tiers
- T1 (≥150% ratio): cyan/magenta α 70, no glow
- T2 (≥250% ratio): α 130 + 4-px outer glow @ α 30
- T3 (≥400% stacked): α 200 + 6-px outer glow @ α 60 + 1-px inner ring

## 6. DEEP6 signature signals
- `sig.absorb.bull` — `#00D4FF` cyan radial glow halo + 8-px pulse, 1.5 Hz, 4 sec
- `sig.absorb.bear` — `#FF36A3` magenta same treatment
- `sig.exhaust` — `#FFD23F` amber chevron `▼`/`▲`, 12 px tall
- `sig.confluence` — `#FFFFFF` white-hot circular pulse
- `sig.confidence.top` — `#00FFD0` saturated mint border 2-px around top-quintile bars

## 7. Levels
- POC: `#FFD23F` 2-px solid amber
- VAH/VAL: `#C8D17A` 1-px solid
- Naked POC: `#FFD23F` α 90 1-px dashed
- GEX zero: `#FFFFFF` 2-px + 6-px white glow halo
- GEX flip: `#FF36A3` 1.5-px dashed
- Call wall: `#00D4FF` 2.5-px + cyan glow
- Put wall: `#FF36A3` 2.5-px + magenta glow

## 8. Typography
- Cell numerals: JetBrains Mono 10.5 px / 500 / tabular numerals
- Cell numerals (compact): JetBrains Mono 9 px / 500
- Chrome/labels: Inter 10 px / 500
- Tooltips: JetBrains Mono 11 px / 400 / tabular
- Section headers: Inter 11 px / 700 / uppercase / tracking +60
- KPI hero (P&L, Score): Inter 28 px / 800 / tabular
- Signal callouts (ABS / EXH / CONF): Inter 9 px / 800 / uppercase / tracking +120
- Footer status: JetBrains Mono 9 px / 400

## 9. Footprint cell anatomy
```
┌──────────────────────────────────────┐
│  bid 1234  │  ask 1456                │   ← single row, split by midline
└──────────────────────────────────────┘
  α-blended over heatmap underlay
```

Layer composition (bottom to top):
1. Heatmap underlay (bitmap) — full-bleed cyan/amber/red intensity
2. Bar cell rectangle — `#0E1014` α 80 (lets heatmap show through 70%)
3. Mid-line — vertical 1-px hairline `#262633` at column center
4. Bid value text — left-aligned, accent magenta only when imbalanced, else dim
5. Ask value text — right-aligned, accent cyan only when imbalanced, else dim
6. Imbalance tier highlight — fills bid OR ask half with tier color
7. POC marker — 2-px amber spine on left edge, extending ±3 px

## 10. POC marker (Bookmap-style invented)
2-px solid amber `#FFD23F` left-edge spine of POC row, extending 3 px past the cell on each side as a "tab". Not a circle, not a label — a *spine*, like a fader line on a mixing console.

## 11. Stacked-imbalance zone
When ≥3 consecutive price levels share the same imbalance side:
- 1-px outer border around the union rectangle: `#00FFD0` (mint stacked-buy) or `#FF1493` (deep magenta stacked-sell)
- 6-px outer glow at α 50
- 8-px corner accent at top-right (buy) or bottom-right (sell)

## 12. ASCII full-chart mockup
```
┌─NQM6  18,247.25  ▲+47.50 (+0.26%)─────────────────────VWAP 18,201.50──┐
│                                                                         │
│ ····················································· ZERO γ ▬▬▬ 18260│
│ ╔═══╗▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒  CALL +1σ ━━━ 18255│
│ ║cyn║▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                    │
│ ║ABS║░░░▓▓▓▓░░░▒▒▒▒▒▒▒▒▒▒▒▒░░░░░░░░▒▒▒▓▓██████████ 18250  ◀▶          │
│ ╚═══╝░░░▒▒▒░░░░░▒▒▒▒▒▒▒▒▒▒▒▒░░░░░░░░░░▒▒▓▓▓▓████████ 18247.25──        │
│       ░░░░ ●  ●●●●  ●●●● ●●  ●  ●●●● ●●●●●●●●●● [cyan dots]            │
│       ░░░░    ◆   ◆     ◆ ICE 4x                                        │
│       ░░░░░░░░  ◌◌  ◌◌◌◌    ◌  ◌  ◌  ◌◌  [magenta dots]               │
│   FOOTPRINT BAR (overlay):                                              │
│   ┌──────────────┐  18243.50 │ 145 │  892 │ ◀ POC ━━ amber spine      │
│   │ bid │ ask    │  18242.25 │  88 │  431 │                           │
│   │ 145 │ 892 ◀  │  18241.00 │ 312 │  ●67 │ ← imbalance T2 + glow   │
│   │ 312 │ 67  ◀  │  FLIP ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ 18238 dashed   │
│   └──────────────┘                                                      │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ PUT -1σ ━━━━ 18230         │
└─────────────────────────────────────────────────────────────────────────┘
[HUD top-right]
  P&L  +$1,247.50         28px ExtraBold mint #00FFD0
       +12.4 R | 8 trades  11px dim
  SCORE +0.78 TIER A LONG ◀━━━
```

Symbol legend:
- `░ ▒ ▓ █` heatmap intensity (cool → hot)
- `●` cyan dot = aggressive buy
- `◌` magenta dot = aggressive sell
- `◆` mint diamond = iceberg
- `╔═╗` absorption signature halo
- `━━━` thick GEX level
- `┄┄┄` dashed GEX flip

## 13. Why this aesthetic wins

Bookmap-Pro wins because it lets the trader **read order flow as a continuous physical surface** rather than as discrete chart elements — every glance is interpretable as "where is the heat, where is it moving, where did it suddenly go cold." It enforces ruthless semantic discipline: cyan always means buyers, magenta always means sellers, amber always means walls or POC, white-hot always means citadel-class size. Most importantly, it uses the bitmap-cached heatmap pattern that has already been validated by Bookmap to handle 1,000+ DOM updates/sec without dropping below 40 fps — DEEP6 inherits a battle-tested rendering architecture.

Full SharpDX implementation (brushes, LUT, bitmap renderer, trade dots, footprint cells, GEX, absorption signature) lives in the agent output transcript.
