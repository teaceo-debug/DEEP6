# DEEP6 Confluence Rules Reference

**Last verified: 2026-05-12**
**Source version:** Phase 15-03 / RULES.md v1.0 (47 raw → 38 canonical)
**Primary source:** `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py`
**Rule inventory source:** `C:\Users\Tea\DEEP6\.planning\phases\15-levelbus-confluence-rules-trade-decision-fsm\RULES.md`

---

## Overview

The 38 canonical CR-XX rules are a stateless evaluator that runs on every bar close. They take a snapshot of active `Level` objects from the LevelBus, the current `GexSignal`, the closed `FootprintBar`, and a preview `ScorerResult`, then return a `ConfluenceAnnotations` object.

`ConfluenceAnnotations` carries four outputs:
- `flags` — regime and meta labels (e.g. `PIN_REGIME_ACTIVE`, `ABSORB_PUT_WALL`)
- `regime` — one of `PIN`, `TREND`, `BALANCE`, `NEUTRAL` (highest-priority rule wins)
- `score_mutations` — per-Level score deltas keyed by `Level.uid`
- `vetoes` — sentinel strings that force `SignalTier.DISQUALIFIED` in the scorer

Budget constraint: evaluation must complete in under 1ms for 80 active Levels (D-34).

### Regime priority (highest wins)

```
PIN (3) > TREND (2) > BALANCE (1) > NEUTRAL (0)
```

### Scoring cascade (scorer.py)

Rules feed into the two-layer scorer at `C:\Users\Tea\DEEP6\deep6\scoring\scorer.py`.

Multiplier order (locked, phase 12-01):
```
base → category confluence_mult → zone_bonus → IB mult → VPIN modifier → clip(0, 100)
```

Tier thresholds (defaults):
- **TYPE_A**: score ≥ 80, absorption or exhaustion present, zone present, 5+ categories, delta agrees
- **TYPE_B**: score ≥ 72, 4+ categories, delta agrees, narrative strength ≥ 0.3
- **TYPE_C**: score ≥ 50, 4+ categories, narrative strength ≥ 0.3
- **DISQUALIFIED**: any veto from confluence rules (e.g. `SPOOF_DETECTED`)

Category weights (R3 optimization, 2026-04-15):
| Category | Weight |
|----------|--------|
| absorption | 20.0 |
| exhaustion | 15.7 |
| imbalance | 25.0 |
| volume_profile | 20.2 |
| delta | 14.3 |
| auction | 12.6 |
| trapped | 0.0 |
| poc | 0.0 |

---

## Tier Taxonomy

| Tier | Meaning | Default state |
|------|---------|---------------|
| `EASY` | Deterministic proximity + state check on LevelBus. O(n) on ≤80 levels. | ON |
| `MEDIUM` | Needs VAH/VAL or GEX snapshot alongside LevelBus. Still O(n). | ON |
| `CALIBRATION-GATED` | Low-confidence threshold or compute cost > 1ms. | OFF |

---

## Group 1: GEX + Absorption Core (CR-01 to CR-10)

These rules combine GEX structural levels (put wall, call wall, gamma flip) with order-flow signals. They form the highest-conviction setups in the system.

---

## CR-01: Absorption at Put Wall — High-Conviction Long

**Category**: Confluence Rule
**Tags**: absorption, put-wall, GEX, long, high-conviction
**DEEP6 Signal(s)**: ABSORB level (direction=+1), PUT_WALL level
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 112-133)

### Concept

When buyers absorb aggressive selling at the put wall, dealers are simultaneously buying to hedge their short-put exposure. Two independent buying forces converge at the same price. This is the highest-conviction long setup in the system.

### Conditions / Setup

- An `ABSORB` level with `direction=+1` must exist in the active LevelBus
- A `PUT_WALL` level must exist
- The absorb level's midpoint must be within `proximity_med_ticks` of the put wall price

### Entry / Exit Rules

Positive hit adds +20 points to the absorbing level's score. Emits flag `ABSORB_PUT_WALL`.

### DEEP6 Implementation

Score contribution: +20 per qualifying ABSORB level
Required signals: ABSORB (direction=+1), PUT_WALL
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 112-133
Source lineage: DEEP6_INTEGRATION.md §Confluence Rules Rule 1; industry.md §Actionable 3

---

## CR-02: Exhaustion at Call Wall — High-Conviction Fade

**Category**: Confluence Rule
**Tags**: exhaustion, call-wall, GEX, short, fade
**DEEP6 Signal(s)**: EXHAUST level (direction=-1), CALL_WALL level
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 136-153)

### Concept

Symmetric to CR-01. Sellers exhaust buyers at the call wall while dealers sell to hedge short-call exposure. Two independent selling forces at the same price.

### Conditions / Setup

- An `EXHAUST` level with `direction=-1` must exist
- A `CALL_WALL` level must exist
- The exhaust level's midpoint must be within `proximity_med_ticks` of the call wall price

### Entry / Exit Rules

Positive hit adds +15 points to the exhausting level's score. Emits flag `EXHAUST_CALL_WALL_FLAG`.

### DEEP6 Implementation

Score contribution: +15 per qualifying EXHAUST level
Required signals: EXHAUST (direction=-1), CALL_WALL
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 136-153
Source lineage: DEEP6_INTEGRATION.md §Confluence Rules Rule 2; industry.md §Actionable 4

---

## CR-03: LVN Crossing Gamma-Flip — Acceleration Candidate

**Category**: Confluence Rule
**Tags**: LVN, gamma-flip, acceleration, breakout, GEX
**DEEP6 Signal(s)**: LVN level, GAMMA_FLIP level
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 156-175)

### Concept

Low-volume nodes (LVNs) are price areas with thin historical participation — price moves through them quickly. When an LVN sits near the gamma-flip level, a cross through it can trigger dealer hedging that amplifies the move. The combination creates an acceleration setup.

### Conditions / Setup

- An `LVN` level must exist
- A `GAMMA_FLIP` level must exist
- Bar close must be inside the LVN zone (crossed)
- LVN midpoint must be within `proximity_wide_ticks` of the gamma-flip price

### Entry / Exit Rules

Positive hit adds +8 points to the LVN level's score. Emits flag `ACCELERATION_CANDIDATE`.

### DEEP6 Implementation

Score contribution: +8 per qualifying LVN level
Required signals: LVN (crossed), GAMMA_FLIP (nearby)
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 156-175
Source lineage: DEEP6_INTEGRATION.md §Confluence Rules Rule 3; industry.md §Actionable 6

---

## CR-04: VPOC Pinned Near Largest-Gamma — Pin Regime

**Category**: Confluence Rule
**Tags**: VPOC, gamma, pin, regime, balance
**DEEP6 Signal(s)**: VPOC level, LARGEST_GAMMA or HVL level
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 178-196)

### Concept

When the session volume point of control (VPOC) sits near the largest-gamma strike, dealers are actively defending that price through hedging. The market tends to pin near this level. Directional signals below score 70 should be suppressed.

### Conditions / Setup

- A `VPOC` level must exist
- A `LARGEST_GAMMA` or `HVL` level must exist
- Distance between VPOC and the gamma level must be within `proximity_tight_ticks`

### Entry / Exit Rules

No score delta. Emits regime override `PIN` and flag `PIN_REGIME_ACTIVE`. PIN has the highest regime priority — it overrides TREND, BALANCE, and NEUTRAL.

### DEEP6 Implementation

Score contribution: none (regime-only)
Regime override: PIN
Flags: PIN_REGIME_ACTIVE
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 178-196
Source lineage: DEEP6_INTEGRATION.md §Confluence Rules Rule 4; industry.md §Actionable 7

---

## CR-05: Momentum Through Flipped Zone Beyond Zero-Gamma — Regime Change

**Category**: Confluence Rule
**Tags**: momentum, gamma-flip, flipped-zone, regime-change, trend
**DEEP6 Signal(s)**: MOMENTUM level, FLIPPED level, GAMMA_FLIP level
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 199-219)

### Concept

When price breaks through a flipped zone (a level that has changed polarity) beyond the gamma-flip level with momentum, dealers switch from dampening to amplifying. This marks a regime change from balance to trend.

### Conditions / Setup

- A `GAMMA_FLIP` level must exist
- A `MOMENTUM` level must exist in the LevelBus
- A `FLIPPED` level must exist in the LevelBus

### Entry / Exit Rules

Adds +10 points to each MOMENTUM level. Emits flag `REGIME_CHANGE` and regime override `TREND`.

### DEEP6 Implementation

Score contribution: +10 per MOMENTUM level
Regime override: TREND
Flags: REGIME_CHANGE
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 199-219
Source lineage: DEEP6_INTEGRATION.md §Confluence Rules Rule 5; industry.md §Actionable 10

---

## CR-06: ABSORB Confirmed + VAH/VAL Proximity — VA Boost

**Category**: Confluence Rule
**Tags**: absorption, value-area, VAH, VAL, auction-theory
**DEEP6 Signal(s)**: ABSORB or CONFIRMED_ABSORB level, VAH or VAL level
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 222-242)

### Concept

Absorption at the value area high or low is a high-probability setup from auction theory. Responsive sellers at VAH and responsive buyers at VAL are the core of market profile trading. When order-flow absorption confirms the auction-theory level, conviction increases.

### Conditions / Setup

- An `ABSORB` or `CONFIRMED_ABSORB` level must exist
- A `VAH` or `VAL` level must exist
- The absorb level's midpoint must be within 4 ticks of VAH or VAL

### Entry / Exit Rules

Positive hit adds +15 points to the absorb level's score. Emits flag `VA_CONFIRMED`.

### DEEP6 Implementation

Score contribution: +15 per qualifying ABSORB/CONFIRMED_ABSORB level
Required signals: ABSORB or CONFIRMED_ABSORB, VAH or VAL (within 4 ticks)
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 222-242
Source lineage: DEEP6_INTEGRATION.md §Confluence Rules Rule 6; auction_theory.md §9 Trade-Plan 4

---

## CR-07: EXHAUST then ABSORB at Same Price — Compound Short

**Category**: Confluence Rule
**Tags**: exhaustion, absorption, compound, sequential, short
**DEEP6 Signal(s)**: EXHAUST (direction=-1), ABSORB (direction=-1)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 245-262)

### Concept

When exhaustion prints at a level and then absorption confirms in the same direction within a few bars, the two signals compound. Buyers tried to push through, got exhausted, and now sellers are absorbing the remaining buying pressure. This is a high-conviction short setup.

### Conditions / Setup

- An `EXHAUST` level with `direction=-1` must exist
- An `ABSORB` level with `direction=-1` must exist
- The two levels must be within 5 bars of each other (by `origin_bar`)
- The two levels must be within 6 ticks of each other in price

### Entry / Exit Rules

Positive hit adds +20 points to the absorb level's score. Emits flag `EXHAUST_ABSORB_COMPOUND`.

### DEEP6 Implementation

Score contribution: +20 per qualifying ABSORB level
Required signals: EXHAUST (direction=-1) + ABSORB (direction=-1) within 5 bars and 6 ticks
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 245-262
Source lineage: DEEP6_INTEGRATION.md §Confluence Rules Rule 7

---

## CR-08: HVN + Put Wall Alignment — Suppress Shorts

**Category**: Confluence Rule
**Tags**: HVN, put-wall, suppression, soft-veto, GEX
**DEEP6 Signal(s)**: HVN level, PUT_WALL level
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 265-283)

### Concept

A high-volume node (HVN) aligned with the put wall creates a structural floor. Dealers are buying to hedge puts while the HVN provides historical support. Short signals in this zone should be suppressed — the market has two reasons to hold.

### Conditions / Setup

- A `PUT_WALL` level must exist
- An `HVN` level with `score >= 50` must exist
- The HVN midpoint must be within `proximity_tight_ticks` of the put wall price

### Entry / Exit Rules

No score delta. Emits flag `SUPPRESS_SHORTS`. The scorer applies a 0.6× multiplier to short signals when this flag is set (D-40 soft suppression).

### DEEP6 Implementation

Score contribution: none (flag-only)
Flags: SUPPRESS_SHORTS
Scorer effect: 0.6× multiplier on short total_score
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 265-283
Source lineage: DEEP6_INTEGRATION.md §Confluence Rules Rule 8

---

## CR-09: Basis-Corrected GEX Level Mapping

**Category**: Confluence Rule
**Tags**: GEX, basis-correction, QQQ, NQ, structural
**DEEP6 Signal(s)**: CALL_WALL, PUT_WALL, GAMMA_FLIP, HVL, LARGEST_GAMMA levels
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 286-302)

### Concept

GEX data from FlashAlpha is derived from QQQ/NDX options, not NQ futures directly. The NQ/QQQ ratio must be applied to map GEX strikes to NQ prices. This rule is a structural sanity check that confirms the basis-correction path is wired correctly.

### Conditions / Setup

- Any GEX-type level (CALL_WALL, PUT_WALL, GAMMA_FLIP, HVL, LARGEST_GAMMA) must be present in the LevelBus

### Entry / Exit Rules

No score delta. Emits flag `GEX_BASIS_CORRECTED` as an audit trail marker.

### DEEP6 Implementation

Score contribution: none (structural flag only)
Flags: GEX_BASIS_CORRECTED
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 286-302
Source lineage: industry.md §Actionable 1

---

## CR-10: Regime Gate on HVL / Gamma-Flip

**Category**: Confluence Rule
**Tags**: GEX, regime, HVL, gamma-flip, positive-gamma, negative-gamma
**DEEP6 Signal(s)**: GexSignal.regime
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 305-325)

### Concept

The GEX regime determines whether dealers are dampening or amplifying price moves. Above the gamma flip (positive gamma), dealers fade moves — absorption works well. Below the gamma flip (negative gamma), dealers amplify moves — momentum signals dominate.

### Conditions / Setup

- A `GexSignal` must be present with a non-neutral regime

### Entry / Exit Rules

Maps GexRegime to a regime override:
- `POSITIVE_DAMPENING` → regime `BALANCE`, flag `REGIME_POSITIVE_GAMMA`
- `NEGATIVE_AMPLIFYING` → regime `TREND`, flag `REGIME_NEGATIVE_GAMMA`
- Neutral → regime `NEUTRAL`, flag `REGIME_NEUTRAL`

### DEEP6 Implementation

Score contribution: none (regime-only)
Regime override: BALANCE, TREND, or NEUTRAL based on GEX regime
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 305-325
Source lineage: industry.md §Actionable 2

---

## Group 2: GEX Advanced (CR-11 to CR-15) — CALIBRATION-GATED

These rules require time-of-day context, 0DTE data, or compute-intensive calculations. All default to OFF until Phase 7 vectorbt calibration.

---

## CR-11: Exhaustion at Broken Wall — Breakout Continuation

**Category**: Confluence Rule
**Tags**: exhaustion, wall-breach, breakout, continuation, GEX
**DEEP6 Signal(s)**: EXHAUST level (state=BROKEN)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 328-341)

### Concept

When a call wall or put wall is broken by more than 0.25 ATR intraday and exhaustion confirms at the broken level, dealers must re-hedge aggressively. This creates a pro-cyclical flow that extends the breakout. Based on Barbon-Buraschi research on dealer hedging dynamics.

### Conditions / Setup

- An `EXHAUST` level with `state=BROKEN` must exist

### Entry / Exit Rules

Positive hit adds +10 points to the exhausting level's score. Emits flag `BREAKOUT_CONTINUATION`.

### DEEP6 Implementation

Score contribution: +10 per qualifying EXHAUST level
Default state: OFF (CALIBRATION-GATED)
Enable via: `ConfluenceRulesConfig.enable_CR_11 = True`
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 328-341
Source lineage: industry.md §Actionable 5

---

## CR-12: Last-30-Min Regime Play (Baltussen)

**Category**: Confluence Rule
**Tags**: time-of-day, end-of-day, regime, Baltussen, stub
**DEEP6 Signal(s)**: time-of-day context (deferred)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 344-352)

### Concept

Based on Baltussen et al. (2021, JFE): in the last 30 minutes of the cash session, the sign of the day's return predicts whether dealers will boost trend-continuation or mean-reversion. Negative dealer gamma amplifies the effect.

### Conditions / Setup

Stub — time-of-day logic deferred to Phase 7 sweep gating.

### Entry / Exit Rules

Currently emits flag `LAST_30_MIN_STUB` only. No score delta.

### DEEP6 Implementation

Score contribution: none (stub)
Default state: OFF (CALIBRATION-GATED)
Enable via: `ConfluenceRulesConfig.enable_CR_12 = True`
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 344-352
Source lineage: industry.md §Actionable 8

---

## CR-13: Charm Drift Toward High-OI Strike (EOD)

**Category**: Confluence Rule
**Tags**: charm, options, OI, end-of-day, stub
**DEEP6 Signal(s)**: options OI data (deferred)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 355-362)

### Concept

In the final 90 minutes on Wednesday and Friday, charm (the rate of change of delta with respect to time) causes dealers to drift toward the strike with the highest open interest. This creates a low-magnitude but persistent directional bias.

### Conditions / Setup

Stub — requires per-expiry OI data not yet wired.

### Entry / Exit Rules

Currently emits flag `CHARM_DRIFT_STUB` only. No score delta.

### DEEP6 Implementation

Score contribution: none (stub)
Default state: OFF (CALIBRATION-GATED)
Enable via: `ConfluenceRulesConfig.enable_CR_13 = True`
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 355-362
Source lineage: industry.md §Actionable 9

---

## CR-14: 0DTE Dominance Guard

**Category**: Confluence Rule
**Tags**: 0DTE, options, GEX, guard, stub
**DEEP6 Signal(s)**: 0DTE volume share (deferred)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 365-372)

### Concept

When 0DTE options represent more than 40% of NQ options volume, cumulative GEX levels become unreliable because 0DTE gamma expires intraday. Per-expiry GEX levels should be used instead of cumulative totals.

### Conditions / Setup

Stub — requires 0DTE volume share data not yet wired.

### Entry / Exit Rules

Currently emits flag `ZERO_DTE_GUARD_STUB` only. No score delta.

### DEEP6 Implementation

Score contribution: none (stub)
Default state: OFF (CALIBRATION-GATED)
Enable via: `ConfluenceRulesConfig.enable_CR_14 = True`
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 365-372
Source lineage: industry.md §Actionable 11

---

## CR-15: Negative-Gamma Risk Scalar

**Category**: Confluence Rule
**Tags**: negative-gamma, position-sizing, risk, scalar, stub
**DEEP6 Signal(s)**: GEX regime, neg_gamma_z-score (deferred)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 375-382)

### Concept

Below the gamma flip, tail risk increases non-linearly. Position size should scale down as negative gamma deepens. Formula: `size = base_size × (1 − 0.4 × clip(|neg_gamma_z|, 0, 2.5) / 2.5)`. Based on Barbon-Buraschi flash-crash tail research.

### Conditions / Setup

Stub — requires neg_gamma_z-score computation not yet wired.

### Entry / Exit Rules

Currently emits flag `NEG_GAMMA_RISK_SCALAR_STUB` only. No score delta.

### DEEP6 Implementation

Score contribution: none (stub)
Default state: OFF (CALIBRATION-GATED)
Enable via: `ConfluenceRulesConfig.enable_CR_15 = True`
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 375-382
Source lineage: industry.md §Actionable 12

---

## Group 3: Microstructure Signals (CR-16 to CR-27)

These rules consume Level.meta fields populated by upstream microstructure engines. They add precision to absorption/exhaustion detection using formal market microstructure theory.

---

## CR-16: AbsorptionZ — Microstructure Formal

**Category**: Confluence Rule
**Tags**: absorption, z-score, microstructure, Eisler-Bouchaud, Wyckoff
**DEEP6 Signal(s)**: ABSORB or HVN level (score >= 60)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 385-398)

### Concept

AbsorptionZ formalizes absorption as a z-score: aggressor volume divided by absolute tick movement, measured over 60 seconds. A z-score ≥ 2.5 with aggressor-side share ≥ 70% indicates statistically significant absorption. This is the microstructure formalization of Wyckoff's "effort vs result" principle.

### Conditions / Setup

- An `ABSORB` or `HVN` level with `score >= 60` must exist (proxy for AbsorptionZ ≥ 2.5)
- Full formula requires 60-second rolling state stored upstream

### Entry / Exit Rules

Positive hit adds +5 points to qualifying ABSORB/HVN levels. Emits flag `MS_ABSORB_Z`.

### DEEP6 Implementation

Score contribution: +5 per qualifying ABSORB/HVN level
Required: level.score >= 60 (proxy threshold)
Flags: MS_ABSORB_Z
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 385-398
Source lineage: microstructure.md §12 Rules MS-01

### Academic Basis

Eisler, Bouchaud et al. (market impact); Wyckoff (effort vs result formalized)

---

## CR-17: Iceberg at Level

**Category**: Confluence Rule
**Tags**: iceberg, hidden-order, replenishment, microstructure
**DEEP6 Signal(s)**: Level.meta["iceberg"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 401-412)

### Concept

Iceberg orders replenish displayed size after each fill, hiding true order size. Detection requires a hidden-volume ratio (HVr) ≥ 2.0 over 60 seconds and at least 2 Zotikov replenishment events. Icebergs at a level indicate institutional interest at that price.

### Conditions / Setup

- `Level.meta["iceberg"]` must be truthy (set by upstream iceberg detection engine)

### Entry / Exit Rules

Positive hit adds +8 points to the level. Emits flag `ICEBERG_AT_LEVEL`.

### DEEP6 Implementation

Score contribution: +8 per level with meta["iceberg"] = True
Flags: ICEBERG_AT_LEVEL
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 401-412
Source lineage: microstructure.md §12 Rules MS-02

### Academic Basis

Hautsch-Huang (iceberg detection); Zotikov (replenishment events)

---

## CR-18: Queue Imbalance Band

**Category**: Confluence Rule
**Tags**: queue-imbalance, DOM, bid-ask, microstructure
**DEEP6 Signal(s)**: Level.meta["queue_imbalance"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 415-427)

### Concept

Queue imbalance (QI) measures the ratio of bid-side to ask-side depth in the top 3 levels within 3 ticks of a price. |QI| ≥ 0.6 with combined size above the rolling median indicates directional pressure. Against the approach direction = absorption; with the approach direction = breakout accelerant.

### Conditions / Setup

- `Level.meta["queue_imbalance"]` must have absolute value ≥ 0.6

### Entry / Exit Rules

Positive hit adds +4 points to the level. Emits flag `QUEUE_IMBALANCE`.

### DEEP6 Implementation

Score contribution: +4 per level with |meta["queue_imbalance"]| >= 0.6
Flags: QUEUE_IMBALANCE
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 415-427
Source lineage: microstructure.md §12 Rules MS-03

### Academic Basis

Gould-Bonart (queue imbalance); Lipton (LOB dynamics)

---

## CR-19: VPIN Regime Shift

**Category**: Confluence Rule
**Tags**: VPIN, flow-toxicity, regime, stub
**DEEP6 Signal(s)**: VPIN bucket data (deferred)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 430-437)

### Concept

VPIN (Volume-Synchronized Probability of Informed Trading) measures order-flow toxicity. A drop of ≥1σ from the 40-bucket mean while price is near a level signals a fade opportunity. A rise of ≥1σ signals a break confirmation.

### Conditions / Setup

Stub — requires VPIN bucket computation not yet wired.

### Entry / Exit Rules

Currently emits flag `VPIN_REGIME_STUB` only. No score delta.

### DEEP6 Implementation

Score contribution: none (stub)
Default state: OFF (CALIBRATION-GATED)
Enable via: `ConfluenceRulesConfig.enable_CR_19 = True`
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 430-437
Source lineage: microstructure.md §12 Rules MS-04

### Academic Basis

Easley-López de Prado-O'Hara (VPIN); Andersen-Bondarenko (caveats)

---

## CR-20: Kyle Lambda Compression

**Category**: Confluence Rule
**Tags**: Kyle-lambda, price-impact, microstructure, absorption
**DEEP6 Signal(s)**: Level.meta["kyle_lambda_ratio"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 440-452)

### Concept

Kyle's lambda measures price impact per unit of order flow. When lambda at a level is ≤ 0.5× the off-level lambda, it means large orders are moving price less than expected — a sign of absorption. The market is absorbing flow without moving.

### Conditions / Setup

- `Level.meta["kyle_lambda_ratio"]` must be ≤ 0.5

### Entry / Exit Rules

Positive hit adds +5 points to the level. Emits flag `KYLE_LAMBDA_COMPRESSED`.

### DEEP6 Implementation

Score contribution: +5 per level with meta["kyle_lambda_ratio"] <= 0.5
Flags: KYLE_LAMBDA_COMPRESSED
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 440-452
Source lineage: microstructure.md §12 Rules MS-05

### Academic Basis

Hasbrouck (price impact); Kyle (lambda model)

---

## CR-21: CVD Divergence at Level

**Category**: Confluence Rule
**Tags**: CVD, cumulative-delta, divergence, reversal
**DEEP6 Signal(s)**: Level.meta["cvd_divergence"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 455-466)

### Concept

When price makes a local extreme near a level but cumulative volume delta (CVD) fails to confirm by ≥1σ of its rolling noise over a 20-bar window, the move lacks genuine directional commitment. This divergence signals a likely reversal.

### Conditions / Setup

- `Level.meta["cvd_divergence"]` must be truthy (set by upstream CVD engine)

### Entry / Exit Rules

Positive hit adds +6 points to the level. Emits flag `CVD_DIVERGENCE`.

### DEEP6 Implementation

Score contribution: +6 per level with meta["cvd_divergence"] = True
Flags: CVD_DIVERGENCE
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 455-466
Source lineage: microstructure.md §12 Rules MS-06

### Academic Basis

Lillo-Farmer (order flow persistence); Bouchaud et al. (price impact)

---

## CR-22: Hawkes Branching Critical

**Category**: Confluence Rule
**Tags**: Hawkes, self-exciting, branching, breakout, stub
**DEEP6 Signal(s)**: Hawkes branching ratio (deferred)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 469-480)

### Concept

A Hawkes process models self-exciting order arrival. When the same-side branching ratio ≥ 0.85 near a level, order flow is becoming self-reinforcing — a breakout is imminent. The inverse (cross-side > same-side) signals the level will hold. Full MLE computation is deferred to a ThreadPoolExecutor + janus worker to keep evaluate() under 1ms.

### Conditions / Setup

Stub — Poisson baseline only. Full Hawkes MLE deferred (D-35).

### Entry / Exit Rules

Currently emits flag `CLUSTER_POISSON_STUB` only. No score delta.

### DEEP6 Implementation

Score contribution: none (stub)
Default state: OFF (CALIBRATION-GATED)
Enable via: `ConfluenceRulesConfig.enable_CR_22 = True`
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 469-480
Source lineage: microstructure.md §12 Rules MS-07

### Academic Basis

Bacry-Muzy (Hawkes processes in finance); Haghighi et al.

---

## CR-23: Spoof Suppressor (VETO)

**Category**: Confluence Rule
**Tags**: spoofing, cancel-ratio, veto, DISQUALIFIED, microstructure
**DEEP6 Signal(s)**: Level.meta["cancel_ratio"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 483-497)

### Concept

Spoofed orders create false absorption signals. When more than 60% of resting size on the absorbing side has a mean order lifetime under 500ms and a cancel rate above 90% over the last 30 seconds, the absorption signal is likely fake. This rule issues a hard veto.

### Conditions / Setup

- `Level.meta["cancel_ratio"]` must be ≥ `cfg.spoof_detection_min_cancel_ratio`

### Entry / Exit Rules

Emits veto `SPOOF_DETECTED` and flag `SPOOF_VETO`. The scorer forces `SignalTier.DISQUALIFIED` for any level with this veto — regardless of raw score.

### DEEP6 Implementation

Score contribution: none (veto)
Vetoes: SPOOF_DETECTED (forces DISQUALIFIED tier)
Flags: SPOOF_VETO
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 483-497
Source lineage: microstructure.md §12 Rules MS-08

### Academic Basis

Cartea-Jaimungal (spoofing models); CFTC enforcement corpus

---

## CR-24: Aggressor Dominance at Level

**Category**: Confluence Rule
**Tags**: aggressor, order-flow, dominance, microstructure
**DEEP6 Signal(s)**: Level.meta["aggressor_share"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 500-512)

### Concept

When aggressor-side volume share in a ±2-tick band around a level exceeds 75% over 30 seconds, one side is clearly dominating. Paired with CR-16 for absorption confirmation, or with breakout signals for exhaustion dominance.

### Conditions / Setup

- `Level.meta["aggressor_share"]` must be > 0.75

### Entry / Exit Rules

Positive hit adds +4 points to the level. Emits flag `AGGRESSOR_DOMINANT`.

### DEEP6 Implementation

Score contribution: +4 per level with meta["aggressor_share"] > 0.75
Flags: AGGRESSOR_DOMINANT
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 500-512
Source lineage: microstructure.md §12 Rules MS-09

---

## CR-25: Round-Number Proximity (Modifier)

**Category**: Confluence Rule
**Tags**: round-number, psychological-level, modifier, NQ
**DEEP6 Signal(s)**: Level.price_top (any level)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 515-525)

### Concept

Round numbers (every 25, 50, or 100 NQ points) attract order flow because traders place stops and targets at these levels. Any level at a round number gets a small score boost. This modifier amplifies CR-16 through CR-22 by 1.25× on the nearest level.

### Conditions / Setup

- Any level's `price_top` must be a round number (within 0.5 points of a multiple of 25)

### Entry / Exit Rules

Positive hit adds +3 points to the level. Emits flag `ROUND_NUMBER`.

### DEEP6 Implementation

Score contribution: +3 per level at a round number
Flags: ROUND_NUMBER
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 515-525
Source lineage: microstructure.md §12 Rules MS-10

### Academic Basis

Bloomfield-Chin-Craig (2024) on round-number clustering

---

## CR-26: Depth Asymmetry

**Category**: Confluence Rule
**Tags**: depth, DOM, asymmetry, order-book, microstructure
**DEEP6 Signal(s)**: Level.meta["depth_ratio"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 528-540)

### Concept

When cumulative depth within 5 ticks on one side is ≥ 3× the other side and the thick side faces the price approach, the thick side is likely to hold. This is a structural DOM signal independent of trade flow.

### Conditions / Setup

- `Level.meta["depth_ratio"]` must be ≥ 3.0

### Entry / Exit Rules

Positive hit adds +5 points to the level. Emits flag `DEPTH_ASYMMETRY`.

### DEEP6 Implementation

Score contribution: +5 per level with meta["depth_ratio"] >= 3.0
Flags: DEPTH_ASYMMETRY
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 528-540
Source lineage: microstructure.md §12 Rules MS-11

### Academic Basis

Cont-Stoikov-Talreja (LOB dynamics); Cont-de Larrard (price impact)

---

## CR-27: Exhaustion Post-Break (Failed Break)

**Category**: Confluence Rule
**Tags**: failed-break, exhaustion, Hawkes-decay, reversal, stub
**DEEP6 Signal(s)**: Level (state=BROKEN), Level.meta["hawkes_decay"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 543-553)

### Concept

When price crosses a level but the Hawkes same-side excitation decays ≥ 50% within 2 minutes and aggressor dominance reverts to ≤ 55%, the break has failed. The level reasserts. This is a reversal setup.

### Conditions / Setup

- A level with `state=BROKEN` must exist
- `Level.meta["hawkes_decay"]` must be ≥ 0.5

### Entry / Exit Rules

Positive hit adds +7 points to the level. Emits flag `FAILED_BREAK`.

### DEEP6 Implementation

Score contribution: +7 per qualifying broken level
Default state: OFF (CALIBRATION-GATED)
Enable via: `ConfluenceRulesConfig.enable_CR_27 = True`
Flags: FAILED_BREAK
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 543-553
Source lineage: microstructure.md §12 Rules MS-12

### Academic Basis

Bacry-Muzy (Hawkes decay kernels)

---

## Group 4: Auction Theory Trade Plans (CR-28 to CR-38)

These rules encode the 15 trade-plan generators from auction theory (Dalton, Steidlmayer, market profile). They consume Level.meta fields set by the auction engine and bar-level context.

---

## CR-28: Open-Drive + Opening Range Extension (Bullish)

**Category**: Confluence Rule
**Tags**: open-drive, ORU, auction-theory, bullish, Dalton
**DEEP6 Signal(s)**: scorer_result.direction > 0, bar.close > bar.open
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 556-568)

### Concept

An open-drive up (OD-UP) with opening range extension (ORU) and no rejection prints signals strong directional conviction from the open. The market is accepting higher prices immediately. Long on the first pullback to the opening range high.

### Conditions / Setup

- `scorer_result.direction > 0` (bullish signal direction)
- `bar.close > bar.open` (bar closes up)
- Requires Kronos E10 ≥ neutral (per RULES.md; not enforced in current stub)

### Entry / Exit Rules

Emits flag `OD_UP_ORU`. No score delta. Entry: first pullback to opening range high. Stop: open minus 4 ticks. Target: 2× IB projection.

### DEEP6 Implementation

Score contribution: none (flag-only)
Flags: OD_UP_ORU
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 556-568
Source lineage: auction_theory.md §9 Trade-Plan 1

### Academic Basis

Dalton, *Markets in Profile* Ch. 3; *Mind Over Markets* Ch. 4

---

## CR-29: Open-Drive + Opening Range Extension (Bearish)

**Category**: Confluence Rule
**Tags**: open-drive, ORD, auction-theory, bearish, Dalton
**DEEP6 Signal(s)**: scorer_result.direction < 0, bar.close < bar.open
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 571-582)

### Concept

Mirror of CR-28. An open-drive down (OD-DOWN) with opening range decline (ORD) and no rejection prints signals strong bearish conviction from the open. Short on the first pullback to the opening range low.

### Conditions / Setup

- `scorer_result.direction < 0` (bearish signal direction)
- `bar.close < bar.open` (bar closes down)

### Entry / Exit Rules

Emits flag `OD_DOWN_ORD`. No score delta. Entry: first pullback to opening range low. Stop: open plus 4 ticks. Target: 2× IB projection downward.

### DEEP6 Implementation

Score contribution: none (flag-only)
Flags: OD_DOWN_ORD
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 571-582
Source lineage: auction_theory.md §9 Trade-Plan 2

---

## CR-30: Overnight Test + Drive Reversal (OTD-UP)

**Category**: Confluence Rule
**Tags**: overnight, OTD, reversal, auction-theory, prior-day
**DEEP6 Signal(s)**: Level.meta["otd"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 585-599)

### Concept

When price tests the prior day's low overnight and then drives back up, it signals that sellers failed to find acceptance below. The overnight test rejected lower prices. Long on reclaim of the overnight low.

### Conditions / Setup

- A level with `meta["otd"]` truthy must exist (set by auction engine)

### Entry / Exit Rules

Positive hit adds +6 points to the level. Emits flag `OTD_REVERSAL`. Entry: reclaim of overnight low. Stop: tested low minus 2 ticks. Target: prior day POC, then VAH.

### DEEP6 Implementation

Score contribution: +6 per level with meta["otd"] = True
Flags: OTD_REVERSAL
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 585-599
Source lineage: auction_theory.md §9 Trade-Plan 3

---

## CR-31: Failed IB Extension (Both Sides)

**Category**: Confluence Rule
**Tags**: IB, initial-balance, failed-extension, auction-theory, Dalton
**DEEP6 Signal(s)**: Level.meta["failed_ib"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 602-615)

### Concept

When price extends beyond the initial balance (IB) but closes back inside it, the extension has failed. Dalton documents 70-75% historical probability of trading to the opposite IB edge after a failed extension. Trade opposite side toward the opposite IB edge.

### Conditions / Setup

- A level with `meta["failed_ib"]` truthy must exist (set by auction engine)

### Entry / Exit Rules

Positive hit adds +5 points to the level. Emits flag `FAILED_IB`. Trade toward opposite IB edge.

### DEEP6 Implementation

Score contribution: +5 per level with meta["failed_ib"] = True
Flags: FAILED_IB
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 602-615
Source lineage: auction_theory.md §9 Trade-Plans 5 & 6; §6 IB rule 2

### Academic Basis

Dalton (failed IB extension probability); Steidlmayer (market profile)

---

## CR-32: Naked POC Magnet

**Category**: Confluence Rule
**Tags**: naked-POC, nPOC, magnet, auction-theory, volume-profile
**DEEP6 Signal(s)**: VPOC level (meta["naked"] = True)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 618-630)

### Concept

A naked POC (nPOC) is a prior session's point of control that price has not revisited. The market tends to return to these levels because they represent unfinished auction business — the most-traded price of a prior session that hasn't been re-tested. Trade toward the nPOC; exit at it; flip if exhaustion prints there.

### Conditions / Setup

- A `VPOC` level with `meta["naked"]` truthy must exist

### Entry / Exit Rules

Positive hit adds +4 points to the level. Emits flag `NAKED_POC_MAGNET`. Exit at the nPOC; flip if exhaustion prints.

### DEEP6 Implementation

Score contribution: +4 per naked VPOC level
Flags: NAKED_POC_MAGNET
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 618-630
Source lineage: auction_theory.md §9 Trade-Plans 7 & 8

---

## CR-33: Poor High / Poor Low Revisit (Volume-Conditional)

**Category**: Confluence Rule
**Tags**: poor-high, poor-low, volume, auction-theory, Dalton, Steidlmayer
**DEEP6 Signal(s)**: Level.meta["poor_extreme"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 633-644)

### Concept

A poor high or poor low is a session extreme formed on light volume — the market didn't fully explore that price. On revisit, the behavior branches on volume: light volume at the poor extreme signals a fade (absorption likely); heavy volume signals a breakout continuation. Requires absorption at the high for the fade branch.

### Conditions / Setup

- A level with `meta["poor_extreme"]` truthy must exist (set by auction engine)

### Entry / Exit Rules

Positive hit adds +5 points to the level. Emits flag `POOR_EXTREME_REVISIT`. Volume branch determines direction: light volume = fade, heavy volume = breakout.

### DEEP6 Implementation

Score contribution: +5 per level with meta["poor_extreme"] = True
Flags: POOR_EXTREME_REVISIT
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 633-644
Source lineage: auction_theory.md §9 Trade-Plans 9 & 10

### Academic Basis

Dalton (poor high/low); Steidlmayer (market profile extremes)

---

## CR-34: Buying-Tail / Selling-Tail Retest

**Category**: Confluence Rule
**Tags**: tail, buying-tail, selling-tail, retest, auction-theory
**DEEP6 Signal(s)**: Level.meta["tail"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 647-658)

### Concept

A buying tail is a cluster of single prints at the low of a session formed by aggressive buying. A selling tail is the mirror at the high. On pullback into the tail with a delta flip in the tail's direction, the tail is confirming as support/resistance. Trade with the tail.

### Conditions / Setup

- A level with `meta["tail"]` truthy must exist (set by auction engine)

### Entry / Exit Rules

Positive hit adds +4 points to the level. Emits flag `TAIL_RETEST`. Long into buying tail / short into selling tail. Stop: below tail minus 2 ticks. Target: day high or VAH.

### DEEP6 Implementation

Score contribution: +4 per level with meta["tail"] = True
Flags: TAIL_RETEST
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 647-658
Source lineage: auction_theory.md §9 Trade-Plan 11

---

## CR-35: Open-Auction In-Range + Unchanged Value

**Category**: Confluence Rule
**Tags**: open-auction, in-range, balance, responsive, auction-theory
**DEEP6 Signal(s)**: Level.meta["open_auction_in_range"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 661-672)

### Concept

When the open auction occurs within the prior session's value area and value is unchanged, the market is in a responsive (balance) mode. Trend logic should be disabled. Scalp IBH/IBL toward POC; maximum 2 trades per day.

### Conditions / Setup

- A level with `meta["open_auction_in_range"]` truthy must exist

### Entry / Exit Rules

No score delta. Emits flag `OPEN_AUCTION_IN_RANGE` and regime override `BALANCE`. Scalp IBH/IBL toward POC.

### DEEP6 Implementation

Score contribution: none (regime-only)
Regime override: BALANCE
Flags: OPEN_AUCTION_IN_RANGE
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 661-672
Source lineage: auction_theory.md §9 Trade-Plan 12

---

## CR-36: Double-Distribution Single-Print Revisit

**Category**: Confluence Rule
**Tags**: double-distribution, single-print, breakout, auction-theory
**DEEP6 Signal(s)**: Level.meta["double_distribution"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 675-686)

### Concept

A double-distribution day has two separate bell curves with a single-print area between them. When price revisits the single-print area on volume expansion, it signals a continuation of the break through that area. Enter with the direction of the break. Stop in the middle of the single print; target the edge of the second distribution.

### Conditions / Setup

- A level with `meta["double_distribution"]` truthy must exist

### Entry / Exit Rules

Positive hit adds +6 points to the level. Emits flag `DOUBLE_DIST_REVISIT`. Enter with direction of break through single print on volume expansion.

### DEEP6 Implementation

Score contribution: +6 per level with meta["double_distribution"] = True
Flags: DOUBLE_DIST_REVISIT
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 675-686
Source lineage: auction_theory.md §9 Trade-Plan 13

---

## CR-37: Absorption at Prior-Day High + Kronos Bearish + IB Fail-Up

**Category**: Confluence Rule
**Tags**: absorption, prior-day-high, Kronos, IB-fail, compound-short
**DEEP6 Signal(s)**: ABSORB or CONFIRMED_ABSORB level, meta["prior_day_high"], meta["ib_fail_up"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 689-702)

### Concept

Three independent bearish signals converge: absorption at the prior day's high (structural resistance), Kronos E10 bearish bias (foundation model directional signal), and a failed IB extension upward. This is the highest-conviction short setup in the auction-theory group.

### Conditions / Setup

- An `ABSORB` or `CONFIRMED_ABSORB` level must exist
- `Level.meta["prior_day_high"]` must be truthy
- `Level.meta["ib_fail_up"]` must be truthy
- Kronos E10 gate defaults to OFF (D-42); enable via `enable_e10_gating` config flag

### Entry / Exit Rules

Positive hit adds +10 points to the level. Emits flag `ABSORB_PDH_IB_FAIL`. Stop: prior day high plus 2 ticks. Target: prior day POC, then VAL.

### DEEP6 Implementation

Score contribution: +10 per qualifying level
Default state: OFF (CALIBRATION-GATED, Kronos gate)
Enable via: `ConfluenceRulesConfig.enable_CR_37 = True`
Flags: ABSORB_PDH_IB_FAIL
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 689-702
Source lineage: auction_theory.md §9 Trade-Plan 14

---

## CR-38: Neutral-Extreme Close — Next-Day Gap-and-Go

**Category**: Confluence Rule
**Tags**: neutral-extreme, gap-and-go, next-day, auction-theory
**DEEP6 Signal(s)**: Level.meta["neutral_extreme_close"]
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (lines 705-716)

### Concept

A neutral-extreme close occurs when a neutral day (balanced, no directional conviction) closes at its high or low. This signals that one side is building pressure for the next session. The gap-and-go bias means the next open is likely to extend in the direction of the extreme close. Scale in on the first 5-minute pullback.

### Conditions / Setup

- A level with `meta["neutral_extreme_close"]` truthy must exist

### Entry / Exit Rules

Positive hit adds +5 points to the level. Emits flag `GAP_AND_GO_BIAS`. Scale in on first 5-minute pullback. Stop: prior day extreme.

### DEEP6 Implementation

Score contribution: +5 per level with meta["neutral_extreme_close"] = True
Flags: GAP_AND_GO_BIAS
See: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` lines 705-716
Source lineage: auction_theory.md §9 Trade-Plan 15; §4 VA-relationship rules

---

## Rule Summary Table

| Rule ID | Name | Tier | Score Delta | Regime | Flags |
|---------|------|------|-------------|--------|-------|
| CR-01 | Absorption at Put Wall | EASY | +20 | — | ABSORB_PUT_WALL |
| CR-02 | Exhaustion at Call Wall | EASY | +15 | — | EXHAUST_CALL_WALL_FLAG |
| CR-03 | LVN Crossing Gamma-Flip | MEDIUM | +8 | — | ACCELERATION_CANDIDATE |
| CR-04 | VPOC Pinned Near Largest-Gamma | MEDIUM | none | PIN | PIN_REGIME_ACTIVE |
| CR-05 | Momentum Through Flipped Zone | MEDIUM | +10 | TREND | REGIME_CHANGE |
| CR-06 | ABSORB + VAH/VAL Proximity | EASY | +15 | — | VA_CONFIRMED |
| CR-07 | EXHAUST then ABSORB Compound | EASY | +20 | — | EXHAUST_ABSORB_COMPOUND |
| CR-08 | HVN + Put Wall Suppress Shorts | EASY | none | — | SUPPRESS_SHORTS |
| CR-09 | Basis-Corrected GEX Mapping | MEDIUM | none | — | GEX_BASIS_CORRECTED |
| CR-10 | Regime Gate on HVL/Gamma-Flip | MEDIUM | none | BALANCE/TREND/NEUTRAL | REGIME_*_GAMMA |
| CR-11 | Exhaustion at Broken Wall | CALIB-GATED | +10 | — | BREAKOUT_CONTINUATION |
| CR-12 | Last-30-Min Regime Play | CALIB-GATED | none | — | LAST_30_MIN_STUB |
| CR-13 | Charm Drift Toward High-OI | CALIB-GATED | none | — | CHARM_DRIFT_STUB |
| CR-14 | 0DTE Dominance Guard | CALIB-GATED | none | — | ZERO_DTE_GUARD_STUB |
| CR-15 | Negative-Gamma Risk Scalar | CALIB-GATED | none | — | NEG_GAMMA_RISK_SCALAR_STUB |
| CR-16 | AbsorptionZ Microstructure | MEDIUM | +5 | — | MS_ABSORB_Z |
| CR-17 | Iceberg at Level | MEDIUM | +8 | — | ICEBERG_AT_LEVEL |
| CR-18 | Queue Imbalance Band | MEDIUM | +4 | — | QUEUE_IMBALANCE |
| CR-19 | VPIN Regime Shift | CALIB-GATED | none | — | VPIN_REGIME_STUB |
| CR-20 | Kyle Lambda Compression | MEDIUM | +5 | — | KYLE_LAMBDA_COMPRESSED |
| CR-21 | CVD Divergence at Level | MEDIUM | +6 | — | CVD_DIVERGENCE |
| CR-22 | Hawkes Branching Critical | CALIB-GATED | none | — | CLUSTER_POISSON_STUB |
| CR-23 | Spoof Suppressor (VETO) | MEDIUM | none | — | SPOOF_VETO (+ VETO: SPOOF_DETECTED) |
| CR-24 | Aggressor Dominance at Level | MEDIUM | +4 | — | AGGRESSOR_DOMINANT |
| CR-25 | Round-Number Proximity | EASY | +3 | — | ROUND_NUMBER |
| CR-26 | Depth Asymmetry | MEDIUM | +5 | — | DEPTH_ASYMMETRY |
| CR-27 | Exhaustion Post-Break | CALIB-GATED | +7 | — | FAILED_BREAK |
| CR-28 | Open-Drive + ORU (Bullish) | MEDIUM | none | — | OD_UP_ORU |
| CR-29 | Open-Drive + ORD (Bearish) | MEDIUM | none | — | OD_DOWN_ORD |
| CR-30 | Overnight Test + Drive Reversal | MEDIUM | +6 | — | OTD_REVERSAL |
| CR-31 | Failed IB Extension | EASY | +5 | — | FAILED_IB |
| CR-32 | Naked POC Magnet | EASY | +4 | — | NAKED_POC_MAGNET |
| CR-33 | Poor High/Low Revisit | MEDIUM | +5 | — | POOR_EXTREME_REVISIT |
| CR-34 | Buying/Selling Tail Retest | MEDIUM | +4 | — | TAIL_RETEST |
| CR-35 | Open-Auction In-Range | EASY | none | BALANCE | OPEN_AUCTION_IN_RANGE |
| CR-36 | Double-Distribution Revisit | MEDIUM | +6 | — | DOUBLE_DIST_REVISIT |
| CR-37 | Absorption @ PDH + Kronos + IB Fail | CALIB-GATED | +10 | — | ABSORB_PDH_IB_FAIL |
| CR-38 | Neutral-Extreme Close Gap-and-Go | MEDIUM | +5 | — | GAP_AND_GO_BIAS |

---

## Tier Distribution

| Tier | Count | Rule IDs |
|------|-------|----------|
| EASY | 9 | CR-01, CR-02, CR-06, CR-07, CR-08, CR-25, CR-31, CR-32, CR-35 |
| MEDIUM | 20 | CR-03, CR-04, CR-05, CR-09, CR-10, CR-16, CR-17, CR-18, CR-20, CR-21, CR-23, CR-24, CR-26, CR-28, CR-29, CR-30, CR-33, CR-34, CR-36, CR-38 |
| CALIBRATION-GATED | 9 | CR-11, CR-12, CR-13, CR-14, CR-15, CR-19, CR-22, CR-27, CR-37 |

---

## Source Lineage

Rules were de-duplicated from 47 raw rules across four research artifacts:

| Source | Section | Rules contributed | Canonical IDs |
|--------|---------|-------------------|---------------|
| DEEP6_INTEGRATION.md | §Confluence Rules | 8 (DEEP6-01..08) | CR-01..CR-08 |
| industry.md | §Actionable for DEEP6 | 12 (IND-01..12) | CR-09..CR-15 (+ merges into CR-01..CR-05) |
| microstructure.md | §12 Microstructure Rules | 12 (MS-01..12) | CR-16..CR-27 |
| auction_theory.md | §9 Trade-Plan Generators | 15 (AUCT-01..15) | CR-28..CR-38 (+ merge into CR-06) |

Full dedup lineage: `C:\Users\Tea\DEEP6\.planning\phases\15-levelbus-confluence-rules-trade-decision-fsm\RULES.md` lines 86-167
