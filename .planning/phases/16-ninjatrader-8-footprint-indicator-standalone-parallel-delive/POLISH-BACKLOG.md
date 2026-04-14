# DEEP6 NT8 — Polish & Safety Backlog

Synthesized from final UI/UX + functional + logic-audit reviews (3 parallel agents).
Items ranked by trader-impact, not by effort.

## Critical safety (block-on-fix before live trading)

| # | Issue | Fix | File:line |
|---|---|---|---|
| S1 | **L2 walls render full-opacity for 90s after L2 disconnect** — trader could fade a wall that no longer exists | Detect `Connection.Status != Connected` OR no depth update across ANY price for 10s → grey out ALL walls + render banner | `RenderLiquidityWalls` ~L1620 |
| S2 | **GEX QQQ→NQ mapping has no plausibility check** — QQQ stale or NQ-led divergence silently shifts every level by 20+ NQ pts | Track rolling 30-min `nqSpot/qqqSpot` ratio; reject mapping if delta > ±1%; dim labels with `~` prefix when uncertain | `RenderGex` ~L1530 |
| S3 | **No tier hierarchy in markers** — every signal looks identical, A+ vs noise indistinguishable in live tape | Implement Tier 3 entry-card from INTERACTION-LOGIC.md; size markers by computed tier | New code, ~200 lines |

## Visual polish (improves perceived quality immediately)

| # | Issue | Fix |
|---|---|---|
| V1 | **Saturated RGB primaries (cyan #00FFFF, magenta #FF00FF, lime #00FF00)** look amateur | Replace with tuned hues: teal `#4FD1C5`, muted violet `#C77DFF`, balanced green `#34D399` |
| V2 | **3 oranges colliding** — exhaustion-bear, put-wall, ask-wall | Lock exhaustion = pure amber `#FFB000`, put wall = pure red `#E54B4B`, ask wall stays orange |
| V3 | **Markers overlap cell text** | Reserve 18px gutter above/below bar range exclusively for markers + label stack |
| V4 | **Right-edge labels stack and overflow** | Priority order: Wall > GEX Wall > Flip > GEX node; lower priority collapses to colored tick |
| V5 | **Toolbar buttons look like debug UI** | Add 1px border `#2A2A2A` (off) / `#00D97E` (on); group ABS|EXH and GEX|L2 with separators; small caps font |
| V6 | **Line weight chaos (1, 1.5, 2, 4 px all rendered)** | Standardize: 1px context, 2px actionable, 3px critical; encode size with opacity not stroke |

## Functional gaps (what's missing for live use)

| # | Gap | Impact |
|---|---|---|
| F1 | **No entry card** at Tier 3 — trader fumbles SuperDOM for ~11s | Implement entry card with ENTER/STOP/T1/T2 prices ready to copy |
| F2 | **No opposing-signal exit alert** while in position | Hard alert (sound + flash) when contra signal ≥ 0.6 fires during holding |
| F3 | **No session signal log** for post-close review | CSV log of every signal with timestamp, trigger, price, outcome |
| F4 | **Toolbar is fixed top-left, blocks opening drive price action** | Make draggable; remember last position; auto-fade option |
| F5 | **No RTH/pre-market visual gate** — overnight cells look identical to RTH | Grey overnight cells; fresh POC/VA from 9:30 only; "RTH starts in 5:00" badge |
| F6 | **Settings don't persist toolbar state across reload** | Save to NT8 user settings file |

## Logic ambiguities (low frequency, real)

| # | Issue | Fix |
|---|---|---|
| L1 | **Stale BBO** (Last fires but Bid/Ask hasn't updated in 30s+) misclassifies aggressors | Track `_bboLastUpdate`; if > 2s old, skip aggressor classification or mark NEUTRAL |
| L2 | **Cell totals not reconciled to NT8 Bars.GetVolume** on finalize — can drift 1-2% on historical reload | Optional: scale per-level vol to match `Bars.GetVolume(prevIdx)` in `Finalize()` |
| L3 | **Stale comment `"under entry cards"`** at L1430 references nonexistent feature | Update comment or delete |

## What the audit agents agreed is GOOD (don't touch)

- **3-tier escalation concept** (★ → ★★ → ★★★) — design-correct, mirrors how traders allocate attention
- **Imbalance cell highlighting** — fast to read, the core value prop
- **GEX as horizontal levels** — clean, not noisy, correct visual weight
- **Toolbar toggle granularity** (7 independent buttons) — right level of control
- **Detector logic faithfulness** to Python source — verified line-by-line, no drift
- **Documentation honesty** — INTERACTION-LOGIC.md correctly states confluence engine is "next phase"
- **Cooldown + delta-gate ordering** in exhaustion detector — correct (zero print exempt, others gated)

## Recommended ship order

1. **S1, S2** (safety blockers) — must ship before any auto-trading
2. **F1, F2** (entry card + opposing exit) — biggest live-trading uplift
3. **V1, V2, V3** (color + gutter) — visual jumps two tiers
4. **F3** (session log) — needed for expectancy tracking
5. **L1** (stale BBO guard) — minor
6. Everything else — opportunistic
