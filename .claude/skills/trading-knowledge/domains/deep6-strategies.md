# DEEP6 Strategies and Scoring Cascade

Last verified: 2026-05-12

---

## STRAT-01: TYPE_A — Triple Confluence Long/Short

**Category**: Strategy
**Tags**: type_a, triple_confluence, absorption, exhaustion, zone, high_conviction
**DEEP6 Signal(s)**: ABS-01..06, EXH-01..06, IMB-03, DELT-04, DELT-08, VOLP-01..06
**Python File**: `C:\Users\Tea\DEEP6\deep6\scoring\scorer.py` (lines 478–485)

### Concept

TYPE_A is DEEP6's highest-conviction trade tier. It requires simultaneous agreement across at least 5 of 8 signal categories, a score of 80+, presence of absorption or exhaustion, proximity to a volume profile zone, and delta agreement with signal direction. When all conditions align, the system labels the bar "TRIPLE CONFLUENCE LONG" or "TRIPLE CONFLUENCE SHORT."

The name reflects three layers of confirmation: (1) a primary reversal signal (absorption or exhaustion), (2) structural context (volume zone), and (3) broad multi-category agreement.

### Conditions / Setup

All of the following must be true simultaneously:

- `total_score >= 80.0` (default threshold, configurable via `ScorerConfig.type_a_min`)
- At least one absorption or exhaustion signal present
- Price is within or near an active volume profile zone (`zone_bonus > 0`)
- `category_count >= 5` (5 of 8 categories agree on direction)
- `delta_agrees = True` (bar delta sign matches signal direction)
- No trap veto (fewer than 3 trap signals present)
- No delta chase (bar delta not aggressively chasing direction)
- Bar is NOT in the midday block (bars 240–330 in session, roughly 10:30–13:00 ET)
- No SPOOF_DETECTED veto from ConfluenceAnnotations

Backtested win rates:
- TYPE_A with delta agreeing: 75% win / +8.7 avg P&L
- TYPE_A during Initial Balance (first 60 bars): 100% win / +21.6 avg P&L
- TYPE_A outside IB: 36% win / -1.7 avg P&L

### Entry / Exit Rules

Entry fires on bar close when `ScorerResult.tier == SignalTier.TYPE_A`.

Direction is determined by majority vote across all signal categories:
- `direction = +1` (LONG) when bull_votes > bear_votes
- `direction = -1` (SHORT) when bear_votes > bull_votes

The label format is: `"TYPE A — TRIPLE CONFLUENCE LONG (N categories, score S)"`

Exit rules are not encoded in the scorer itself — they live in the execution layer. The scorer provides the signal; position management is handled upstream.

### Risk Management

Encoded constraints in the scorer:

1. **Midday block**: Bars 240–330 in session are forced to QUIET regardless of score. Forensic finding: these bars accumulated -$1,622 across 25 days.
2. **Delta agreement gate**: TYPE_A/B require bar delta to agree with signal direction. Disagreement drops win rate from 75% to 33%.
3. **Trap veto**: 3+ trap signals present → TYPE_A blocked (softened from original hard veto).
4. **GEX direction conflict**: Going LONG at call wall or SHORT at put wall → capped at TYPE_C or QUIET.
5. **VPIN modifier**: Final score multiplied by VPIN confidence modifier before tier classification. High toxic flow reduces effective score.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 37–47:   SignalTier enum (DISQUALIFIED=-1, QUIET=0, TYPE_C=1, TYPE_B=2, TYPE_A=3)
  Lines 107–116: CATEGORY_WEIGHTS dict (R3 profile, 2026-04-15)
  Lines 301–314: Delta-direction agreement gate + IB multiplier
  Lines 478–485: TYPE_A tier classification logic
  Lines 499–502: Midday block enforcement
  Lines 427:     Score formula: (base × confluence_mult + zone_bonus + gex_wall_bonus) × agreement × ib_mult
  Lines 440–441: VPIN modifier applied last, then clip(0, 100)
```

Score formula (locked, phase 12-01):
```
base_score = sum(CATEGORY_WEIGHTS[cat] × gex_modifier for cat in categories_agreeing)
total_score = clip((base × confluence_mult + zone_bonus + gex_wall_bonus) × agreement × ib_mult, 0, 100)
total_score *= vpin_modifier
total_score = clip(total_score, 0, 100)
```

### Academic Basis

- Absorption/exhaustion as reversal signals: supported by order flow microstructure literature (see `domains/microstructure.md`)
- Multi-factor confluence: reduces false positive rate vs single-signal systems
- IB (Initial Balance) edge: well-documented in Market Profile theory (Dalton, "Mind Over Markets")

### Examples / Edge Cases

- **Failure mode**: TYPE_A fires at call wall in positive GEX regime → `gex_direction_conflict = True` → demoted to TYPE_C or QUIET. The system correctly suppresses longs into massive dealer selling.
- **Edge case**: SPOOF_DETECTED veto forces DISQUALIFIED regardless of score. This takes priority over all tier logic.
- **Midday trap**: High-score bars between 10:30–13:00 ET are silenced. Do not override this block without fresh backtesting evidence.

### Backtest Notes

R3 optimization (2026-04-15, `ninjatrader/backtests/results/round3/WEIGHT-OPTIMIZATION-R3.md`):
- Named config `5_attribution_r3` yields +12.0% Sharpe vs R1 (0.9026 → 1.0107)
- IMB-03 stacked imbalance confirmed alpha-positive: 81.2% WR, 19.5t avg P&L, SNR=28.76

---

## STRAT-02: TYPE_B — Double Confluence Long/Short

**Category**: Strategy
**Tags**: type_b, double_confluence, tradeable, delta_gate
**DEEP6 Signal(s)**: Any 4+ categories
**Python File**: `C:\Users\Tea\DEEP6\deep6\scoring\scorer.py` (lines 486–489)

### Concept

TYPE_B is DEEP6's second-tier tradeable signal. It requires 4+ categories agreeing, a score of 72+, delta agreement, and minimum narrative strength. It does NOT require absorption/exhaustion or a zone — making it more frequent than TYPE_A but lower conviction.

### Conditions / Setup

- `total_score >= 72.0` (default, configurable via `ScorerConfig.type_b_min`)
- `category_count >= 4`
- `delta_agrees = True`
- `narrative.strength >= 0.3`
- No GEX direction conflict (if conflict present, capped at TYPE_C)
- Not in midday block (bars 240–330)
- No DISQUALIFIED veto

### Entry / Exit Rules

Entry fires on bar close when `ScorerResult.tier == SignalTier.TYPE_B`.

Label format: `"TYPE B — DOUBLE CONFLUENCE LONG (N categories, score S)"`

### Risk Management

Same midday block, delta gate, and VPIN modifier as TYPE_A. Lower score threshold means more frequent signals but also more noise — position sizing should reflect lower conviction.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 486–489: TYPE_B tier classification
  Lines 169–174: ScorerConfig defaults (type_b_min=72.0 legacy default; actual default in ScorerConfig)
```

### Backtest Notes

TYPE_B outside IB has lower win rate than TYPE_A. Use with tighter stops or smaller size.

---

## STRAT-03: TYPE_C — Alert Only

**Category**: Strategy
**Tags**: type_c, alert, low_conviction, watch_only
**DEEP6 Signal(s)**: Any 4+ categories (softened from original 3+)
**Python File**: `C:\Users\Tea\DEEP6\deep6\scoring\scorer.py` (lines 491–493)

### Concept

TYPE_C is an alert-only tier. It indicates emerging confluence but not enough to trade mechanically. Useful for manual review, dashboard highlighting, or as a pre-condition for other setups.

### Conditions / Setup

- `total_score >= 50.0`
- `category_count >= 4` (raised from 3 in optimization to reduce noise)
- `narrative.strength >= 0.3`
- GEX direction conflict is allowed (TYPE_C is the fallback when conflict blocks TYPE_B)

### Entry / Exit Rules

No mechanical entry. Dashboard alert only. Human review required.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 491–493: TYPE_C classification
  Lines 474–477: GEX conflict fallback path to TYPE_C
```

---

## STRAT-04: Signal Category Weighting (R3 Profile)

**Category**: Strategy
**Tags**: category_weights, r3_optimization, signal_weighting, imbalance, absorption
**Python File**: `C:\Users\Tea\DEEP6\deep6\scoring\scorer.py` (lines 93–116)

### Concept

DEEP6 uses 8 signal categories, each with a weight that contributes to the base score. The R3 profile (2026-04-15) is the current production configuration, derived from backtested attribution analysis.

### Conditions / Setup

Category weights (R3):

| Category | Weight | Notes |
|---|---|---|
| absorption | 20.0 | Was 32 in R1; grid optimizer found 20 optimal |
| exhaustion | 15.7 | Was 24 in R1; reduced proportionally |
| trapped | 0.0 | Zero SNR per attribution — disabled |
| delta | 14.3 | Proportional adjustment from R1 |
| imbalance | 25.0 | Was 13 in R1; IMB-03 confirmed alpha-positive |
| volume_profile | 20.2 | Was 5 in R1; 5_attribution_r3 profile raises this |
| auction | 12.6 | Proportional adjustment from R1 |
| poc | 0.0 | Negligible contribution — disabled |

Key insight: IMB-03 (stacked imbalance) is the highest-weight category in R3, overtaking absorption. This reflects the backtested finding that stacked imbalances have 81.2% win rate and SNR=28.76.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 107–116: CATEGORY_WEIGHTS dict
  Lines 413–424: Weight application with GEX regime modifiers
    - absorption/exhaustion weights × gex_abs_mult (1.3 in positive GEX, 0.7 in negative)
    - delta/imbalance weights × gex_momentum_mult (0.8 in positive GEX, 1.3 in negative)
```

### Academic Basis

Attribution-optimized via grid search over 25 days of NQ data. Source: `ninjatrader/backtests/results/round3/WEIGHT-OPTIMIZATION-R3.md`

---

## STRAT-05: Confluence Multiplier (SCOR-02)

**Category**: Strategy
**Tags**: confluence_multiplier, scor_02, category_threshold
**Python File**: `C:\Users\Tea\DEEP6\deep6\scoring\scorer.py` (lines 409–410)

### Concept

When 5 or more signal categories agree on direction, the base score receives a 1.25× multiplier. This rewards high-agreement setups and creates a non-linear jump in score at the 5-category threshold.

### Conditions / Setup

- `category_count >= cfg.confluence_threshold` (default 5)
- Multiplier: 1.25× applied to base score before zone bonus and IB boost

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Line 410: confluence_mult = 1.25 if cat_count >= cfg.confluence_threshold else 1.0
  Line 427: Applied in score formula: base × confluence_mult + zone_bonus + ...
```

---

## STRAT-06: Zone Bonus (SCOR-03)

**Category**: Strategy
**Tags**: zone_bonus, volume_profile, scor_03, structural_confluence
**Python File**: `C:\Users\Tea\DEEP6\deep6\scoring\scorer.py` (lines 385–405)

### Concept

When price is at or near an active volume profile zone, the scorer adds a flat bonus to the score and counts "volume_profile" as an agreeing category. This rewards setups that occur at structurally significant price levels.

### Conditions / Setup

Three bonus tiers:
- Price inside zone AND `zone.score >= zone_high_min`: `zone_bonus = zone_high_bonus` (typically 8 points)
- Price inside zone AND `zone.score >= zone_mid_min`: `zone_bonus = zone_mid_bonus` (typically 6 points)
- Price within `zone_near_ticks` of zone edge AND `zone.score >= zone_high_min`: `zone_bonus = zone_near_bonus`

Zone proximity check uses duck-typing over both `VolumeZone` (legacy) and `Level` (post-15-01) objects.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 385–405: Zone proximity detection and bonus assignment
  Lines 60–71:   Duck-typing helpers (_zone_bot, _zone_top, _zone_invalidated)
  Lines 392–394: High-score zone: adds volume_profile category + zone_high_bonus
  Lines 395–397: Mid-score zone: adds volume_profile category + zone_mid_bonus
```

---

## STRAT-07: IB Multiplier (Initial Balance Boost)

**Category**: Strategy
**Tags**: initial_balance, ib_multiplier, session_timing, morning_edge
**Python File**: `C:\Users\Tea\DEEP6\deep6\scoring\scorer.py` (lines 311–314)

### Concept

The first 60 bars of the RTH session (roughly 9:30–10:30 ET on 1-minute bars) receive a 1.15× score multiplier. Backtesting found TYPE_A signals during IB have 100% win rate vs 36% outside IB.

### Conditions / Setup

- `0 <= bar_index_in_session < 60`
- Multiplier: 1.15× applied inside the score formula

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Line 314: ib_mult = 1.15 if 0 <= bar_index_in_session < 60 else 1.0
  Line 427: Applied in score formula: ... × ib_mult
  Lines 234: bar_index_in_session = i % 390 (in live_pipeline.py)
```

---

## STRAT-08: VPIN Flow-Toxicity Modifier (Phase 12-01)

**Category**: Strategy
**Tags**: vpin, flow_toxicity, final_modifier, phase_12_01
**Python File**: `C:\Users\Tea\DEEP6\deep6\scoring\scorer.py` (lines 434–441)

### Concept

VPIN (Volume-synchronized Probability of Informed Trading) measures the probability that recent order flow is toxic (informed traders dominating). High VPIN reduces the effective score, suppressing signals when the market is dominated by informed flow that could overwhelm reversal setups.

The VPIN modifier is the FINAL stage of the scoring pipeline, applied after all other multipliers. It is a separate line item — never fused with IB multiplier or per-signal weights (FOOTGUN 1 in phase 12-01).

### Conditions / Setup

- `vpin_modifier` is computed by `state.vpin.get_confidence_modifier()` in the live pipeline
- Applied only to the fused `total_score`, not to individual signal scores
- 1m timeframe: reads from SharedState (already advanced upstream)
- 5m timeframe: defaults to 1.0 (deferred)

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 434–441: VPIN modifier application (final stage)
  Lines 1–21:    Module docstring explains multiplier order and FOOTGUN 1

C:\Users\Tea\DEEP6\deep6\engines\live_pipeline.py
  Lines 219–225: VPIN modifier read from SharedState for 1m bars
```

---

## STRAT-09: Full Pipeline Execution Order

**Category**: Strategy
**Tags**: pipeline, execution_order, live_pipeline, bar_close
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\live_pipeline.py`

### Concept

The `LiveSignalPipeline` runs the full 44-signal stack on every closed `FootprintBar`. It is the production entry point for live trading signal generation.

### Conditions / Setup

Per-bar execution order (from `live_pipeline.py`):

1. Compute rolling ATR (20-bar window, min 5 bars, default 15.0)
2. Update volume EMA (α=0.05)
3. Feed volume profile, detect zones every 10 bars, update zones
4. Run narrative cascade (`classify_bar`) → absorption, exhaustion, imbalance signals
5. Run delta engine → DeltaSignal list
6. Run auction engine → AuctionSignal list
7. Run POC engine → POCSignal list
8. Run trap engine (output not passed to scorer directly)
9. Run vol pattern engine (output not passed to scorer directly)
10. Read VPIN modifier from SharedState (1m only)
11. Get active zones from volume profile (min_score=20)
12. Call `score_bar()` → ScorerResult
13. Advance rolling state (prior_bar, cvd_history, bar_history, poc_history)

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\live_pipeline.py
  Lines 108–271: run_bar() — full per-bar execution
  Lines 69–103:  __init__ — per-timeframe engine instantiation
  Lines 54:      _BAR_HISTORY_WINDOW = 20 (rolling bar history)
  Lines 134:     vol_ema α=0.05
  Lines 234:     bar_index_in_session = i % 390
```

Timeframes: default ("1m", "5m"). Each timeframe has independent engine instances and rolling state.

### Examples / Edge Cases

- Any engine failure is caught and logged; the pipeline degrades gracefully to empty signals rather than raising.
- VPIN is only read for 1m; 5m uses modifier=1.0 to match ReplaySession behavior.
- `bar_index_in_session = i % 390` assumes 390 bars per RTH session (6.5 hours × 60 minutes).

---

## STRAT-10: GEX Regime Modifier in Scoring

**Category**: Strategy
**Tags**: gex, regime_modifier, absorption_boost, momentum_boost
**DEEP6 Signal(s)**: GEX-01..06
**Python File**: `C:\Users\Tea\DEEP6\deep6\scoring\scorer.py` (lines 316–342)

### Concept

GEX regime modifies category weights before base score computation. In positive GEX (dealers long gamma), absorption/exhaustion signals are boosted and momentum signals are suppressed. In negative GEX (dealers short gamma), the opposite applies.

Additionally, being near a call wall or put wall adds a directional bonus — but only when the signal direction aligns with dealer flow.

### Conditions / Setup

Positive GEX (POSITIVE_DAMPENING):
- `gex_abs_mult = 1.3` → absorption/exhaustion weights × 1.3
- `gex_momentum_mult = 0.8` → delta/imbalance weights × 0.8

Negative GEX (NEGATIVE_AMPLIFYING):
- `gex_abs_mult = 0.7` → absorption/exhaustion weights × 0.7
- `gex_momentum_mult = 1.3` → delta/imbalance weights × 1.3

Wall bonuses:
- Near call wall AND direction <= 0 (SHORT): +5.0 to score
- Near put wall AND direction >= 0 (LONG): +5.0 to score
- Near call wall AND direction > 0 (LONG): `gex_direction_conflict = True` → blocks TYPE_A/B

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 316–342: GEX regime modifier block
  Lines 413–424: Weight application with gex_abs_mult / gex_momentum_mult
  Lines 334–342: Wall bonus and direction conflict detection
  Lines 470–477: GEX direction conflict tier demotion
```

See also: `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\gex-options.md` for GEX concepts.
