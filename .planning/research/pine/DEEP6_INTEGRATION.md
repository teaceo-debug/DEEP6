# DEEP6 Pine → Python + GEX Integration Blueprint

_Research artifact — no implementation yet._

This document unifies the level primitives produced by two Pine v6 indicators
(`VP_LVN.pine`, `BOOKMAP_LIQUIDITY_MAPPER.pine`) with DEEP6's Python signal
engine and FlashAlpha GEX levels. Goal: a single normalized "level bus" every
producer writes and every consumer reads, with concrete confluence rules that
marry tape-derived zones with dealer-positioning levels.

---

## Level Primitive Inventory

| Primitive | Geometry | Producer | Score Attributes | Lifecycle |
|-----------|----------|----------|-----------------|-----------|
| LVN line (VP_LVN.pine) | Single horizontal line | VP session profile — local minima with ±lvn_strength bin window | None — display only | Created at session TF change; deleted at next period change |
| VPOC bin | Single price row (highest volume bin) | Session VP accumulation | Volume height relative to neighbors | Updated bar-by-bar; no explicit delete |
| VAH / VAL | Single price line (VWAP ±1σ) | Session VWAP accumulation | Dynamic (price moves) | Recomputed each bar within session |
| ABSORB zone | Box (wick span) | BOOKMAP narrative: wick_pct ≥ 30%, delta_ratio ≤ 0.12 | type_weight=1.0 (25) + vol + touch + recency; VA +15; confirm +20; tier 60/35 | Create/merge-or-widen; break→flip; 2nd break→invalidate; evict weakest at cap 80 |
| EXHAUST zone | Box (wick span) | BOOKMAP: wick_pct ≥ 35%, delta fading | type_weight=0.72 (≈18) | Same as ABSORB |
| MOMENTUM zone | Box (body_top..body_bot) | BOOKMAP: body_pct ≥ 72%, delta_ratio ≥ 0.25 | type_weight=0.40 (≈10) | Same lifecycle; zone is the candle body |
| REJECTION zone | Box (wick zone) | BOOKMAP: wick_pct ≥ 55% | type_weight=0.48 (≈12) | Same lifecycle |
| FLIPPED zone | Box (same geometry, inverted direction) | Break event on any zone type | Original score × decay; inverted=True | One more break invalidates |
| CONFIRMED-ABSORB zone | Box (boosted score) | ABSORB + defense OR ABSORB + same-dir MOMENTUM within confirm_window | +20 confirmation boost, border color change | Same as ABSORB thereafter |
| LVN zone (deep6) | Box (adjacent thin-bin run) | `SessionProfile.detect_zones()` — bins < 30% avg | type(35)+recency(25)+touches(25)+defense(15), 0–100 | Created → Defended → Broken → Flipped → Invalidated |
| HVN zone (deep6) | Box (adjacent thick-bin run) | Same — bins > 170% avg | Same scoring | Same FSM |
| GEX call_wall | Single price | `GexEngine._compute_gex()` — max call γ×OI strike | None currently | Refreshed ~60s |
| GEX put_wall | Single price | Same — max put γ×OI | None | Same |
| GEX gamma_flip | Single price (interpolated zero-cross) | Same — linear interpolation | None | Same |
| GEX hvl | Single price (peak \|GEX\| strike) | Same | None | Same |

---

## Current Coverage in `deep6/`

| Primitive | Exists? | File:Line | Gap |
|-----------|---------|-----------|-----|
| LVN zone | Partial | `deep6/engines/volume_profile.py:105-108` | Threshold-based, not local-minima. Pine uses strength-window. |
| HVN zone | Yes | `deep6/engines/volume_profile.py:111-113` | Not in Pine — DEEP6-only |
| VPOC bin | Yes | `deep6/engines/poc.py:1-60` | POCEngine tracks session POC + VA, but VAH/VAL not exposed as scoreable zone objects |
| VAH/VAL as VWAP±1σ | Partial | `deep6/engines/narrative.py:93` (kwarg) | Computed externally and passed in; not a zone object in registry |
| ABSORB zone (persistent) | **NO** | — | `detect_absorption()` at `deep6/engines/absorption.py:46` produces `AbsorptionSignal` but no zone created |
| EXHAUST zone (persistent) | **NO** | — | `detect_exhaustion()` at `deep6/engines/exhaustion.py:109` — signal only |
| MOMENTUM zone (persistent) | **NO** | — | `classify_bar()` at `deep6/engines/narrative.py:206` returns type but no zone |
| REJECTION zone (persistent) | **NO** | — | Same pattern at `deep6/engines/narrative.py:238` |
| FLIPPED zone | Partial | `deep6/engines/volume_profile.py:228-235` | LVN/HVN only; narrative zones have no flip mechanism |
| CONFIRMED-ABSORB zone | Partial | `deep6/engines/narrative.py:36-67`; `deep6/scoring/scorer.py:344-346` | ABS-06 tracking exists; bonus is 2.0 pts (too weak vs Pine's 20) |
| VA-proximity boost on zone score | **NO** | — | `AbsorptionSignal.at_va_extreme` at `deep6/engines/absorption.py:43` boosts signal strength, not `VolumeZone.score` |
| GEX call_wall / put_wall / gamma_flip / hvl | Yes | `deep6/engines/gex.py:39-42` | Present |
| GEX zero_gamma | No (alias gap) | — | Same concept as gamma_flip; needs alias in `GexLevels` |
| GEX largest_gamma_strike | **NO** | — | Different from hvl: peak raw call γ×OI before put netting |
| GEX HIRO | No | — | Not computed/ingested |
| GEX DIX | No | — | Not applicable for NQ/QQQ proxy via Polygon |
| Zone merge-or-create | Yes for LVN/HVN | `deep6/engines/zone_registry.py:50-59` | Not for narrative zones |
| Zone eviction at capacity | Yes | `deep6/engines/volume_profile.py:251-254` | Same mechanism Pine uses |
| Cross-type confluence query | Weak | `deep6/engines/zone_registry.py:100-143` | +6/+8 only; no typed rules (e.g., ABSORB + PUT_WALL = specific action) |

**Critical gap summary:** DEEP6 has two separate object lineages — `VolumeZone`
(from volume profile) and `AbsorptionSignal`/`ExhaustionSignal` (from narrative)
— that never converge into a single queryable level store. GEX levels are bare
floats in a dict. The level bus unifies all four source types.

---

## Level Bus Contract

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto

class LevelKind(Enum):
    # Volume profile origins
    LVN            = auto()
    HVN            = auto()
    VPOC           = auto()
    VAH            = auto()
    VAL            = auto()
    # Narrative zone origins
    ABSORB         = auto()
    EXHAUST        = auto()
    MOMENTUM       = auto()
    REJECTION      = auto()
    FLIPPED        = auto()             # Any zone post-first-break
    CONFIRMED_ABSORB = auto()           # ABSORB that has been defended
    # GEX origins
    CALL_WALL      = auto()
    PUT_WALL       = auto()
    GAMMA_FLIP     = auto()             # zero-gamma line
    ZERO_GAMMA     = auto()             # alias for GAMMA_FLIP; keep both for naming clarity
    HVL            = auto()             # peak |GEX| strike
    LARGEST_GAMMA  = auto()             # peak raw call γ×OI (pre-netting)

class LevelState(Enum):
    ACTIVE      = auto()
    DEFENDED    = auto()
    BROKEN      = auto()
    FLIPPED     = auto()
    INVALIDATED = auto()

@dataclass(slots=True)
class Level:
    """Unified level object. Every producer writes this; every consumer reads it."""
    # Geometry — point levels (GEX) set price_top == price_bot
    price_top:    float
    price_bot:    float
    kind:         LevelKind
    # Identity + timing
    origin_ts:    float    # Unix timestamp — stable across session resets
    origin_bar:   int      # Bar index for fast age math
    last_act_bar: int      # Bar of last touch/break
    # Strength
    score:        float    # 0–100 composite
    confidence:   float    # score / 100 (cached for ML feature builders)
    touches:      int
    # Direction
    direction:    int      # +1 support, -1 resistance, 0 neutral (MOMENTUM, GEX lines)
    inverted:     bool     # True after first break-and-flip
    state:        LevelState
    # Sparse metadata
    meta:         dict = field(default_factory=dict)
    # Example meta keys:
    #   "vol_ratio"        — LVN/HVN: bin volume / session average
    #   "wick_pct"         — ABSORB/EXHAUST: wick volume fraction
    #   "delta_ratio"      — ABSORB: |delta|/volume in wick zone
    #   "absorb_type"      — CLASSIC / PASSIVE / STOPPING / EVR
    #   "gex_net"          — GEX level: net GEX value at strike
    #   "confirmation_window_ends_bar"
    #   "confirmed"        — bool, for CONFIRMED_ABSORB
    #   "confluence"       — tag set by ConfluenceRules (e.g., "ABSORB_PUT_WALL")
```

**Field rationale**

- `price_top/price_bot` over single `price` — point levels (GEX) set both equal;
  zone levels use the full range. Single query `bot <= price <= top` works for both.
- `origin_ts` + `origin_bar` — bar indices reset across sessions in backtests;
  timestamp is stable for cross-session persistence and logging.
- `score` 0–100 — matches Pine's 100-pt scale and DEEP6's existing
  `VolumeZone.score` range. GEX point levels carry a derived score based on
  proximity-weighted influence radius.
- `confidence` = score/100 — redundant but removes repeated division in ML
  feature builders.
- `state` as enum — fast filter pattern.
- `meta` sparse dict rather than typed subclass — avoids dataclass explosion.
- `direction` on GEX — call_wall is resistance (+1 below, −1 above), put_wall is support.

---

## Confluence Rules

Proximity measured in NQ ticks (0.25 pts/tick). All rules idempotent and
stateless — apply on each bar close.

**Rule 1 — Absorption at Put Wall → High-Conviction Long**
Trigger: ABSORB level with direction=+1 within 8 ticks of PUT_WALL.
Action: `level.score = min(level.score + 20, 100)`. Tag
`meta["confluence"] = "ABSORB_PUT_WALL"`. Scorer +8 bonus on top of zone_bonus.
Counts as 2 categories (absorption + volume_profile).
Rationale: Put wall = dealers short puts = buy underlying to hedge. That buying
flow IS the absorption. Two independent signals confirm the same institutional
action — highest-conviction long setup in the system.

**Rule 2 — Exhaustion at Call Wall → High-Conviction Fade**
Trigger: EXHAUST level with direction=−1 within 8 ticks of CALL_WALL.
Action: `level.score = min(level.score + 15, 100)`. Emit
`EXHAUST_CALL_WALL_FLAG` in SignalFlags (new bit, Phase 13+).
Rationale: Call wall = dealers long calls = they sell underlying to hedge.
Tape-confirmed exhaustion at that strike corroborates dealer selling.

**Rule 3 — LVN Crossing Gamma-Flip → Acceleration Candidate**
Trigger: Close through LVN zone boundary AND GAMMA_FLIP within 12 ticks of LVN mid.
Action: `meta["acceleration_candidate"] = True`. Scorer suppresses opposing
absorption signals (fading into negative-gamma is the highest-risk setup).
Rationale: LVN = thin volume → acceleration. Gamma-flip = dealers amplify moves
on the far side. Fading this combo is the most dangerous signal family.

**Rule 4 — VPOC Pinned Near Largest-Gamma Strike → Pin Regime**
Trigger: Session VPOC within 6 ticks of LARGEST_GAMMA (or HVL) for 3+ bars.
Action: Set `regime = "PIN"` in session state. Suppress directional signals with
score < 70. Reduce position size (execution flag).
Rationale: Max-gamma strikes are gravitational wells — dealers buy dips / sell
rallies there. When VPOC pins to that level, the market confirms the gravity
well. Directional signals in pin regime are noise; only very high-conviction
should fire.

**Rule 5 — Momentum Through Flipped Zone Beyond Zero-Gamma → Regime Change**
Trigger: MOMENTUM bar closes beyond (in direction of momentum) a FLIPPED zone
that is itself beyond GAMMA_FLIP from prior session close.
Action: Emit `REGIME_CHANGE` meta flag. Boost momentum-category weight 1.3×.
Suppress prior-direction absorption until next ABSORB_CONFIRMED fires.
Rationale: Flipped zone beyond gamma-flip = (a) structural polarity changed
AND (b) dealer hedging now amplifies rather than dampens. No gravitational pull
back — regime transition, not a tradeable fade.

**Rule 6 — ABSORB Confirmed + VAH/VAL Proximity → VA Boost**
Trigger: ABSORB zone created within 4 ticks of VAH or VAL, then CONFIRMED
within confirmation window.
Action: `level.score = min(level.score + 15, 100)` (the missing VA boost from
Pine). `meta["va_confirmed"] = True`. If score ≥ 60, force `state = DEFENDED`.
Rationale: Replicates Pine BOOKMAP VA-proximity +15. DEEP6 currently flags
`AbsorptionSignal.at_va_extreme` but never persists it onto zone score. VA
extremes = highest-probability reversal locations in auction theory.

**Rule 7 — EXHAUST → ABSORB at Same Price → Compound Short**
Trigger: EXHAUST zone (direction=−1) at P1, then within 5 bars ABSORB zone
(direction=−1) forms within 6 ticks of P1.
Action: Merge into `CONFIRMED_ABSORB`; `score = min(score + 20, 100)`; emit
"EXHAUST + ABSORB NOW WATCH" label (matching Pine).
Rationale: Replicates BOOKMAP confirmation cascade. Sequential signals at the
same price confirm institutional intent. DEEP6 currently has no mechanism to
link sequential signals at the same price.

**Rule 8 — HVN + Put Wall Alignment → Suppress Shorts**
Trigger: Active HVN zone (score ≥ 50) within 6 ticks of PUT_WALL.
Action: If direction=−1, apply 0.6× multiplier to total_score before tier
classification. Do not fully suppress (HVN can break), but raise the bar.
Rationale: HVN = buyer acceptance + put wall = dealer buying hedge. Both
support the same price as a floor. Shorts fight two separate institutional
buyer flows.

---

## Architecture Recommendation

No new engine (E11 is premature). Structural upgrade to `ZoneRegistry` →
`LevelBus`, plus a new stateless `ConfluenceRules` module between
`E6VPContextEngine` and `scorer.py`.

```
BAR CLOSE EVENT
      │
      ▼
[E1 narrative.classify_bar()]      [E6.session_profile.detect_zones()]
      │                                        │
      │ NarrativeResult                        │ new LVN/HVN VolumeZone list
      ▼                                        ▼
[LevelFactory.from_narrative()]  [LevelFactory.from_volume_zone()]
      │                                        │
      └──────────┬───────────────┬─────────────┘
                 ▼
        [LevelBus (upgraded ZoneRegistry)]
        - unified List[Level]
        - GEX dict → List[Level] (point levels)
        - merge_or_create() for all types
        - update_lifecycle(bar) → events
        - query_near(price, ticks) → List[Level]
                 │
                 ▼
        [ConfluenceRules.evaluate(levels, gex_signal, bar)]
        - applies rules 1-8 above
        - mutates level.score in-place
        - returns ConfluenceAnnotations (flags + regime)
                 │
                 ▼
        [scorer.score_bar(..., confluence_annotations)]
        - existing two-layer logic unchanged
        - new: confluence_annotations feed as additional
          category votes + score modifiers
                 │
                 ▼
        [ScorerResult] → execution_loop
```

**Insertion points in current code**

- `deep6/engines/zone_registry.py:50` — `add_zone()` → `add_level()` accepting
  `Level`; GEX dict entries become point-Level objects stored in same list.
- `deep6/engines/vp_context_engine.py:78-112` — `process()` gets a step between
  zone detection and confluence: `LevelFactory.from_narrative(narrative_result)`
  → `registry.add_level()` for any ABSORB/EXHAUST/MOMENTUM/REJECTION with
  score ≥ 35.
- `deep6/scoring/scorer.py:276-298` — GEX modifier block expands to apply rules
  1–8 from `ConfluenceAnnotations`.
- **New file**: `deep6/engines/confluence_rules.py` — stateless
  `evaluate(levels, gex_signal, bar) -> ConfluenceAnnotations`.
- **New file**: `deep6/engines/level_factory.py` — converts `AbsorptionSignal`,
  `ExhaustionSignal`, `NarrativeResult`, `VolumeZone`, `GexLevels` → `Level`.

No new asyncio task. No new subprocess. Runs synchronously in `bar_engine_loop`
at bar close, sequentially after E6 and before scorer. Budget: <1ms for 80
active levels.

---

## Pine Port Priority

Ranked by integration value:

1. **Narrative zone persistence** (ABSORB/EXHAUST/MOMENTUM/REJECTION → VolumeZone).
   Largest gap. BOOKMAP's value is in persistent zones, not bar labels. DEEP6
   throws away zone geometry after each bar. **IMMEDIATE** — implement in
   `LevelFactory`.
2. **VA-proximity boost on zone score** (+15 pts when ABSORB within 0.5σ of
   VAH/VAL). Requires POCEngine to pass VAH/VAL at zone creation. The
   `at_va_extreme` flag already computes proximity — missing step is persisting
   it onto zone score. **IMMEDIATE alongside (1)**.
3. **Confirmation boost cascade** (ABSORB+DEFENSE or ABSORB+MOMENTUM → +20).
   ABS-06 tracks this in `_pending_confirmations`. Wire the confirmed flag into
   zone-score mutation, not just scorer bonus. **Phase 13 / next phase**.
4. **LVN local-minima detection** (strength-window from VP_LVN.pine replacing
   flat-threshold in `SessionProfile.detect_zones()`). Current threshold fires
   too broadly late in session. Port via `scipy.signal.find_peaks` with
   `prominence` ≈ Pine strength window. **Phase 13**.
5. **Volume ratio cap on zone scoring** (Pine: `vol_ratio_cap = 2.0`). DEEP6
   doesn't cap — high-vol bars produce artificial scores. **Phase 13 scorer config**.
6. **Zone `max_visible` filter** (top-N by score). `get_top_n(n=6)` query
   trivial to add. **Phase 10 dashboard** (display only).
7. **Break volume multiplier gate** (break requires `bar_vol ≥ break_vol_mult × vol_ema`).
   Currently any close-through counts — produces false flips on thin bars.
   **Phase 13**.
8. **SKIP — Heatmap rendering.** Visualization only; Python equivalent is Plotly
   / Lightweight Charts custom series. Different pipeline.
9. **SKIP — Intrabar sampling.** DEEP6 has real tick data from Rithmic/Databento.
   Intrabar sampling is a Pine workaround for no DOM access. Python has superior
   data.
10. **SKIP/INVESTIGATE — HIRO / DIX.** Not computable from Polygon options API.
    Research FlashAlpha response schema — if HIRO is exposed as a numeric level,
    add `LevelKind.HIRO`.

---

## Open Questions for User

1. **Narrative zone score threshold for persistence.** BOOKMAP creates a zone
   for every narrative signal meeting the volume gate. Persist every
   ABSORB/EXHAUST as a zone, or only those with `strength ≥ X`? Low threshold
   (e.g., 0.3) could flood registry on volatile NQ sessions. Recommend: start at
   strength ≥ 0.4 and tune from backtest.

2. **ABSORB zone geometry.** BOOKMAP uses body_top..body_bot. DEEP6's
   `AbsorptionSignal.price` is single level (high or low). Zone should span the
   wick, not the body, for absorption. Full wick (`bar.high - body_top` or
   `body_bot - bar.low`), or fixed N-tick band around signal price?

3. **Cross-session zone persistence.** `ZoneRegistry.clear()` is called at
   `on_session_start()`. Do ABSORB zones from prior session carry over with
   decay weight (like VPRO-07 does for VP bins)? High-scoring absorption often
   remains relevant across sessions in NQ.

4. **LevelBus migration strategy.** Upgrading `ZoneRegistry` → `LevelBus` breaks
   existing `VolumeZone`-typed API. In-place refactor (rename + extend) or new
   class with transition adapter? If Phase 13 plan has committed serialized
   state field names, adapter is safer.

5. **`largest_gamma_strike` vs `hvl`.** `GexLevels.hvl` = peak `|net GEX|` strike
   (call + put sum). "Largest gamma strike" in Pine context is usually peak call
   OI × gamma before netting. Different prices. Does the system need both? If
   FlashAlpha exposes both, add `largest_gamma_strike: float = 0.0` at
   `deep6/engines/gex.py:36`.

6. **Confluence rule weight calibration.** Rules 1–8 use boost values mirroring
   Pine defaults. Before production lock, a sweep over these magnitudes is
   needed. Extend Phase 7 vectorbt sweep (`deep6/api/routes/sweep.py`) to
   include `ConfluenceRulesConfig`. Wire into Phase 13 or a dedicated
   calibration phase?

7. **HIRO from FlashAlpha.** CLAUDE.md mentions FlashAlpha at $49/mo. Does the
   NQ/QQQ response include HIRO as a discrete level, or is it derived locally?
   Determines whether `LevelKind.HIRO` is producer or consumer.

---

## Essential Reference Files

- `/Users/teaceo/DEEP6/.planning/research/pine/VP_LVN.pine` — LVN detection algorithm (local minima over strength window)
- `/Users/teaceo/DEEP6/.planning/research/pine/BOOKMAP_LIQUIDITY_MAPPER.pine` — zone lifecycle, scoring, confirmation cascade
- `/Users/teaceo/DEEP6/deep6/engines/volume_profile.py` — existing LVN/HVN zone + FSM (ZoneState, VolumeZone, SessionProfile)
- `/Users/teaceo/DEEP6/deep6/engines/zone_registry.py` — **upgrade target**: ZoneRegistry → LevelBus
- `/Users/teaceo/DEEP6/deep6/engines/absorption.py` — AbsorptionSignal production (no zone created — primary gap)
- `/Users/teaceo/DEEP6/deep6/engines/exhaustion.py` — ExhaustionSignal production (same gap)
- `/Users/teaceo/DEEP6/deep6/engines/narrative.py` — classify_bar cascade
- `/Users/teaceo/DEEP6/deep6/engines/gex.py` — GexLevels, GexEngine, GexSignal
- `/Users/teaceo/DEEP6/deep6/engines/vp_context_engine.py` — orchestration insertion point
- `/Users/teaceo/DEEP6/deep6/scoring/scorer.py` — where confluence rules land
- `/Users/teaceo/DEEP6/deep6/signals/flags.py` — 44-bit SignalFlags; where new flags (EXHAUST_CALL_WALL, REGIME_CHANGE, PIN_REGIME) allocate
