# DEEP6 NT8 — Signal × Level Interaction Logic

Synthesized from 3 parallel agent analyses (trader, quant, systems engineer).
This is the design spec for the next implementation pass — not yet shipped in code.

## Headline rule

> **Fire only when the signal, the wall, and the GEX magnet all point the same direction — and the opposite side is empty.**

## 4-cell confluence matrix

| | **GEX Level** | **Liquidity Wall** |
|---|---|---|
| **Absorption** | Magnet absorption — fade-the-approach. Stop 2t past GEX. Conviction ×1.5. | Proven absorption — wall IS the absorber. Stop 1t past wall. Conviction ×2.0 (highest). |
| **Exhaustion** | Target exhaustion — best R:R combo. Stop past GEX. Conviction ×1.75. | Trapped aggressors — wall on opposite side proves liquidity stacked against the move. Conviction ×1.75. |

## Tier 3 fire decision tree

1. Signal fires with strength ≥ 0.6
2. Is there a wall on the SAME side as the reversal direction (bullish→bid wall below)?
   - **Yes:** Within 3 ticks?
     - **Yes:** Opposite-side wall within 5 ticks? **Yes → SUPPRESS (chop)** | **No → FIRE Tier 3**
     - **No:** Check GEX path
   - **No:** Signal at GEX (±2t)?
     - **Yes:** GEX on the fade side? **Yes → FIRE Tier 3** | **No → SUPPRESS** (fighting dealer flow)
     - **No:** Apply standard stacked-confirmation / VA-extreme rules

## Confluence score (per direction, 0–100)

```
score = clamp(
  sum(component_contributions) × confluence_multiplier × global_gate,
  0, 100
)
```

**Component points (positive = supporting direction; opposing within 3t = subtract 60–80%):**

| Component | Base | Strength bonus | Variant multipliers |
|---|---|---|---|
| Absorption | 20 | +15 × strength | CLASSIC ×1.0, PASSIVE ×1.1, STOPPING_VOLUME ×1.25, EFFORT_VS_RESULT ×1.15 |
| Exhaustion | 18 | +12 × strength | BID_ASK_FADE ×1.0, FADING_MOMENTUM ×1.2, EXHAUSTION_PRINT ×1.25, ZERO_PRINT ×1.30 |
| GEX proximity ≤2t | 12 | — | GammaFlip ×1.30, Wall ×1.20, Major ×1.0 |
| GEX proximity 3–5t | 6 | — | same |
| Wall ≤1t supportive | 14 | +0.02×(MaxSize−200) cap +8 | +3 per RefillCount cap +9 |
| Wall 2–3t supportive | 7 | size bonus ×0.5 | — |
| VAH/VAL extreme | 10 | +4 if AtVaExtreme on absorption | — |
| POC reject (touched + rotated >3t) | 8 | +4 | — |

**Confluence multiplier:** `mult = 1.0 + 0.18 × (categories_agreeing − 1)`
- 1 cat: 1.00 / 2: 1.18 / 3: 1.36 / 4: 1.54 / 5: 1.72 / 6: 1.90

**Decay (signals only, levels are structural):** `decay(n_bars) = max(0, 1 − 0.35n − 0.05n²)`
- bar 0: 1.00 / bar 1: 0.60 / bar 2: 0.10 / bar 3+: 0

**Global gate (applied last):**
| Condition | Multiplier |
|---|---|
| `vol_ema_20 < 0.4 × vol_ema_200` | ×0.0 |
| `atr_5 > 2.5 × atr_20` (news spike) | ×0.5 |
| Time in 09:25–09:31 ET or 15:58–16:02 ET | ×0.3 |
| `bar_range < 2 ticks` | ×0.0 |

**Tier thresholds:**

| Score | Tier | Action |
|---|---|---|
| <30 | Silent | no display |
| 30–54 | T3 Watch | small dot |
| 55–74 | T2 Ready | arrow + soft tick sound |
| **75–89** | **T1 GO** | **arrow + chord sound + draft bracket** |
| ≥90 | T0 A+ | auto-arm if user enabled |

## Lifecycle state machine

```
IDLE → BUILDING → ARMED → ACTIVE → EXIT_SIGNAL/INVALIDATED → COOLDOWN → IDLE
```

| Transition | Trigger |
|---|---|
| IDLE → BUILDING | first component confluence (1 of {signal, wall, GEX, VA}) |
| BUILDING → IDLE | all components decay (no component within 3 bars) |
| BUILDING → ARMED | ≥3 categories aligned AND score ≥75 AND cooldown clear |
| BUILDING → INVALIDATED | opposing signal ≥ current strength |
| ARMED → ACTIVE | price moves ≥2t in direction within 5 bars |
| ARMED → INVALIDATED | invalidation rule (table below) |
| ACTIVE → EXIT_SIGNAL | exit trigger (table below) |
| ACTIVE → INVALIDATED | price retraces ≥1.0R past entry |
| INVALIDATED → COOLDOWN | 100ms settle |
| EXIT_SIGNAL → COOLDOWN | 2 bars after alert shown |
| COOLDOWN → IDLE | timer expires |

## Invalidation rules (ARMED → INVALIDATED)

| Trigger | Threshold | User-visible effect |
|---|---|---|
| Wall pulled | size drops >60% within 10s of fire | grey out, "WALL PULLED" toast |
| Wall stale | no L2 update for 3s on wall price | pulse amber, "STALE L2" |
| GEX freshness | >5 min since last fetch | dim level, downgrade card to ★★ |
| Price excursion | >4t past entry pre-ACTIVE | dismiss card, "MISSED" log |
| Time elapsed | 5 bars from fire, no ACTIVE | dismiss, "EXPIRED" |
| Opposing signal | confidence ≥ current | flip red, "REVERSED" alert |
| Level breach | close through GEX/wall ≥2t | dismiss, "LEVEL BROKEN" |

## Exit signal triggers (ACTIVE → EXIT_SIGNAL)

| Event | Action |
|---|---|
| Opposing absorption + exhaustion stacked within 2 bars | EXIT NOW alert + loud sound |
| Opposing wall appears ≥ entry wall size | "OPPOSING WALL" amber, suggest scale |
| Price reaches T1 GEX target | "SCALE OUT T1" yellow alert |
| Price reaches T2 | "SCALE OUT T2 / trail" alert |
| 8 bars in trade with <0.5R progress | "STALLED — consider exit" amber |
| 3 bars of opposing delta with price stalled | "MOMENTUM FADING" |
| VWAP reclaim against position | "VWAP FLIP" |

## Cooldown

```
key = (symbol, direction, trigger_combo_hash)
combo_hash = hash(sorted(signal_ids + level_ids bucketed to 2-tick zones))
duration = max(5 bars, 90 seconds)

Per-combo: full cooldown
Per-(symbol, direction) any combo: min 2 bars between fires
Per-symbol any direction: min 1 bar (whipsaw guard)
Opposite direction at different level: allowed immediately

Reset: RTH open, manual reset, indicator reload, >20t gap between bars
```

## Hard suppression

1. Same-bar opposing absorption + exhaustion at same price (±1t) → suppress both
2. Bid wall + ask wall both within 4t → suppress all signals until one pulls
3. Price at gamma flip (±1t) with walls both sides → suppress (undefined direction)

## Multi-card

Multiple ARMED allowed if opposite sides OR >10t apart. Ranked by score desc, then proximity asc. Cap 2 visible, 4 tracked. Top card pinned, others stacked at 80% opacity.

## Implementation status

- ✅ Component detection (absorption, exhaustion, GEX, walls, VAH/VAL/POC) — **shipped**
- ⏳ Per-direction confluence score — **next phase**
- ⏳ Tier 3 entry card with state machine — **next phase**
- ⏳ Cooldown + invalidation tracking — **next phase**
- ⏳ EXIT_SIGNAL alerts — **next phase**

This document is the contract for those next-phase patches.
