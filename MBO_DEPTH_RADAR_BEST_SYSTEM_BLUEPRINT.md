# DEEP6 MBO / Depth Radar Best-System Blueprint

Created: 2026-06-05
Scope: NQ-focused MBO levels, order behavior, spoof-like liquidity, iceberg/reload behavior, wall quality, GEX fusion, gray-marker fusion, NinjaTrader/Depth Radar UI.

## 1. Core thesis

The edge is not "there is a big order on the book."

The edge is classifying the lifecycle of liquidity:

- appeared
- persisted
- got tested
- traded
- replenished
- fled
- migrated
- layered
- vanished

For DEEP6, MBO should become the liquidity-intent layer:

1. Gray absorption/exhaustion marker = main entry model.
2. TradeGEX/options map = structural battlefield.
3. MBO/Depth Radar = confirms, warns, or downgrades the gray setup.
4. Footprint/delta = execution refinement.
5. MBO spoof signal alone = warning/context, not standalone entry.

## 2. What MBO gives us

Market-by-order data gives individual resting order lifecycle visibility:

- order_id
- side
- price
- visible quantity
- add/modify/cancel/fill events
- exchange timestamp / sequence
- execution interaction
- order age
- re-add/reprice behavior
- per-level order composition

This is the difference between seeing:

"500 contracts at 21350.00"

and seeing:

"500 contracts made of 34 individual orders, most added 80 ms ago, 92% canceled when price came within 6 ticks, almost no fills, third repeated event in 10 minutes."

That second statement is where the system becomes useful.

## 3. Critical local DEEP6 findings

Current live Depth Radar is already strong, but has important gaps.

Relevant files:

- `deep6/services/live_mbo_radar.py`
- `deep6/ml/depth_radar/mbo_wall_engine.py`
- `deep6/ml/depth_radar/causal_features.py`
- `deep6/ml/depth_radar/causal_classifier.py`
- `depth_radar_desktop/engine_bridge.py`
- `depth_radar_desktop/live/live_tab.py`
- `depth_radar_desktop/live/walls_table.py`
- `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV4.cs`
- `cross_market/book/mbo_order_book.py`
- `cross_market/types/mbo_event.py`

Current strengths:

- Depth Radar live worker already outputs `depth_radar_walls.json`.
- Health API exists at `127.0.0.1:9203/health`.
- Wall states already exist: FRESH, ESTABLISHED, UNDER_ATTACK, DEFENDING, EXHAUSTED, STALE, PULLED, CONSUMED.
- Intent classes already exist: PASSIVE_REAL, SPOOF_LIKE, RESERVE_REFRESH, MIGRATORY.
- The causal engine already extracts many wall features.
- Desktop and NT8 V4 already consume live JSON.

Main gaps:

1. Rithmic live path appears to be L2/order-book aggregate mode, not true order-id MBO.
   - It synthesizes per-price order IDs.
   - Good for wall display.
   - Weak for true spoof/order-lifecycle confidence.
   - Treat as `source_quality = L2_APPROX` unless true order IDs are available.

2. Rithmic live path needs trade/tape input.
   - Without trades, absorption/delta/attack features are underpowered.
   - Add trade subscription alongside order-book updates.

3. Current JSON callback is too thin.
   - It strips useful fields needed by desktop/NT8:
     - episode_id
     - in_touch_band
     - absorption_ratio
     - delta_2s
     - delta_10s
     - approach_speed
     - attack_intensity
     - interaction prediction
     - intent probabilities
     - source quality
     - mid/bid/ask

4. The desktop UI currently receives walls but not enough market payload context.
   - `LiveTab` should not estimate mid by averaging wall prices.
   - EngineBridge should pass full payload including mid/bid/ask/source_quality.

5. There is per-order lifecycle logic in `cross_market/book/mbo_order_book.py` that should be reused or ported into the Depth Radar core.

## 4. Correct architecture

```text
Live Rithmic / Databento historical MBO / Databento live MBO
  -> provider-specific event normalizer
  -> canonical MBO event stream
  -> order-id-aware book state
  -> price-level tracker
  -> wall episode engine
  -> intent + behavior scoring
  -> GEX/options fusion
  -> gray-marker fusion
  -> versioned JSON output
  -> Depth Radar Desktop + NinjaTrader V5 overlay
  -> replay validation and metrics
```

Recommended new/extended modules:

```text
deep6/ml/depth_radar/
  order_lifecycle.py       # order-id lifecycle, queue-age, fill/cancel/reprice behavior
  wall_ranker.py           # quality/spoof/iceberg/migration/break-risk scoring
  source_quality.py        # TRUE_MBO vs L2_APPROX vs STALE/DEGRADED
  schema_v2.py             # versioned output payload contract
  replay_metrics.py        # validation and scorecards
```

Keep existing modules where possible:

```text
deep6/services/live_mbo_radar.py
 deep6/ml/depth_radar/mbo_wall_engine.py
 deep6/ml/depth_radar/causal_features.py
 deep6/ml/depth_radar/causal_classifier.py
```

NinjaTrader should get a side-by-side version:

```text
DEEP6DepthRadarV5.cs
```

Do not replace V4.

## 5. Core classifications

### PASSIVE_REAL / GENUINE

Meaning:
Liquidity remains available, survives approach, interacts with trades, and/or holds price.

High-confidence evidence:

- large relative size
- survives near-touch approach
- meaningful fill interaction
- low pre-touch cancel ratio
- holds/rejects price
- replenishes after being hit
- aligns with GEX support/resistance

Trader meaning:
Real support/resistance context. It improves gray-marker quality if aligned.

### SPOOF_LIKE / FLEETING

Meaning:
Liquidity appeared influential but fled before real interaction.

Evidence:

- large relative size
- short lifetime
- canceled as price approached
- low/no fills
- repeated add/cancel pattern
- synchronized cancellation across levels
- opposite-side benefit or flow continuation

Important wording:
Use `spoof-like`, `fleeting liquidity`, or `pulled liquidity`. Do not accuse intent.

Trader meaning:
Warning/trap context. Penalizes gray setups when the apparent support/resistance is fake.

### RESERVE_REFRESH / ICEBERG_LIKE

Meaning:
Visible liquidity refreshes or absorbs more volume than it displayed.

Evidence:

- executed volume materially exceeds displayed size
- refill_count high
- price does not break despite aggressive volume
- repeated same-price replenishment
- low visible depletion despite prints

Trader meaning:
Very important. A gray absorption marker against iceberg-like behavior should be top tier.

### MIGRATORY

Meaning:
Wall relocates instead of holding.

Evidence:

- repeated cancel/re-add at adjacent prices
- same-size chain
- wall steps up/down with price
- little interaction at old levels

Trader meaning:
Pressure context, less trustworthy than genuine/iceberg.

### LIQUIDITY_VOID / EXHAUSTED_BOOK

Meaning:
Book thins and price can air-pocket.

Evidence:

- pulls exceed adds
- best levels collapse
- no passive refill
- one side depleted

Trader meaning:
Useful after gray exhaustion markers; can support continuation if direction aligns.

## 6. Scoring model

Do not use one binary label. Emit multiple scores:

- quality_score
- spoof_score
- iceberg_score
- genuine_score
- migration_score
- defense_score
- break_risk_score
- gray_alignment_score
- gex_alignment_score

Initial transparent formula approach is better than black-box ML.

Example:

```text
genuine_score =
  20 * persistence_norm
+ 20 * survival_after_touch_norm
+ 20 * fill_ratio_norm
+ 15 * refill_after_trade_norm
+ 15 * size_percentile_norm
+ 10 * gex_alignment_bonus
- 25 * pull_on_approach_penalty
- 15 * high_cancel_ratio_penalty
```

```text
spoof_score =
  25 * size_percentile_norm
+ 25 * pull_on_approach
+ 20 * cancel_ratio_norm
+ 15 * repeated_reappear_norm
+ 10 * low_fill_ratio
+  5 * opposite_flow_confirmation
- 20 * survived_touch_penalty
- 15 * meaningful_fill_penalty
```

```text
iceberg_score =
  30 * executed_vs_displayed_norm
+ 25 * refill_count_norm
+ 20 * price_hold_norm
+ 15 * aggressive_delta_absorbed_norm
+ 10 * gray_absorption_alignment
- 20 * clean_break_penalty
```

## 7. False-positive controls

Never call spoof from one condition.

Bad:

```text
large order canceled = spoof
```

Better:

```text
large relative size
+ short lifetime
+ canceled as price approached
+ low/no fill
+ repeated behavior
+ synchronized layering
+ opposite-side benefit
+ not explained by full-book repricing/news chaos
= high spoof-like score
```

Controls:

- adaptive thresholds by session/time-of-day/regime
- require near-touch approach
- require low fill ratio for spoof-like calls
- detect full-book repricing and penalize spoof score
- suppress or require stronger evidence during news/opening bursts
- distinguish L2_APPROX from TRUE_MBO
- expose reason codes for every signal

## 8. Schema v2 target

Keep current V4 fields, add richer v2 fields.

File remains:

```text
C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\depth_radar_walls.json
```

Recommended payload:

```json
{
  "schema": "DEEP6_DEPTH_RADAR_V2",
  "version": "5.0.0",
  "symbol": "NQ",
  "instrument": "NQM6",
  "source": "rithmic",
  "source_quality": "L2_APPROX",
  "generated_at_utc": "2026-06-05T14:32:15.245Z",
  "sequence": 1849292,
  "latency_ms": 34,
  "data_quality": {
    "order_id_available": false,
    "event_gap_count": 0,
    "last_event_age_ms": 18,
    "confidence_multiplier": 0.65
  },
  "market_state": {
    "last_price": 21345.25,
    "best_bid": 21345.00,
    "best_ask": 21345.25,
    "spread_ticks": 1,
    "book_imbalance_10": 0.58,
    "liquidity_void_up": false,
    "liquidity_void_down": true
  },
  "walls": [
    {
      "episode_id": "NQM6.ask.21352.00.1849001",
      "price": 21352.0,
      "side": "ask",
      "size": 184,
      "max_size": 326,
      "distance_ticks": 27,
      "intent": "SPOOF_LIKE",
      "classification": "SPOOF_LIKE",
      "state": "PULLED_ON_APPROACH",
      "confidence": 0.86,
      "duration_sec": 2.7,
      "refill_count": 0,
      "cancel_ratio": 0.91,
      "fill_ratio": 0.02,
      "absorption_ratio": 0.05,
      "delta_2s": -430,
      "delta_10s": -1260,
      "approach_speed": 4.2,
      "attack_intensity": 0.72,
      "scores": {
        "quality": 22,
        "genuine": 12,
        "spoof": 86,
        "iceberg": 4,
        "migration": 38,
        "break_risk": 74
      },
      "evidence": [
        "large_size_percentile_94",
        "pulled_within_6_ticks",
        "low_fill_ratio",
        "repeated_reappear_3"
      ],
      "gex": {
        "near_level": true,
        "nearest_level": 21350.0,
        "distance_ticks": 8,
        "level_type": "call_wall",
        "alignment": "resistance"
      }
    }
  ],
  "gray_fusion": {
    "active_marker": true,
    "marker_side": "long",
    "marker_price": 21341.25,
    "quality": "A",
    "score": 82,
    "confirmations": ["bid_iceberg_at_marker", "positive_gex_support_below"],
    "warnings": ["genuine_ask_wall_9_ticks_overhead"]
  }
}
```

Atomic write rule:

- write to temp file
- flush
- rename over target
- include sequence
- NT8 ignores older sequence numbers

## 9. NinjaTrader V5 UI

Create side-by-side:

```text
DEEP6DepthRadarV5.cs
```

Do not replace V4.

Visual rules:

- No stops/targets.
- Do not obscure gray marker.
- Show only strongest 5-12 levels near price by default.
- Show stale/missing data clearly.
- Every label should be trader-readable.

Suggested visual vocabulary:

- Genuine: blue/cyan solid band. Label `GEN 184 82%`.
- Spoof-like: red/pink dashed/fading ghost. Label `SPF 326->0 86%`.
- Iceberg/reload: teal/green solid band with refill dots. Label `ICE x7 91%`.
- Migratory: amber arrow/step. Label `MIG up 74%`.
- Void: HUD warning first, chart shading optional/off by default.

HUD:

```text
MBO NQ 34ms Q:100%
BID: 2 GEN / 1 ICE / 0 SPF
ASK: 1 GEN / 0 ICE / 2 SPF
VOID: Down
GRAY FUSION: A 82
GEX: Support + / CallWall 21350
```

Gray marker fusion badge:

- `A+ MBO`
- `ICE CONFIRM`
- `WARN SPF`
- `VOID FOLLOW`

Badge should be optional and only for active/recent gray marker.

## 10. GEX/options fusion

TradeGEX is the map. MBO tells whether liquidity around that map is real/fake/refreshing.

Rules:

Near GEX support:

- genuine bid wall = long gray confirmation
- bid iceberg = strong long gray confirmation
- ask spoof pulled above = long continuation confirmation
- genuine ask wall overhead = warning

Near GEX resistance/call wall:

- genuine ask wall = short gray confirmation
- ask iceberg = strong short gray confirmation
- bid spoof pulled below = short continuation confirmation
- genuine bid wall below = warning

Negative gamma:

- liquidity void and spoof/migration matter more
- walls break easier; reduce genuine score unless tested/filled

Positive gamma:

- mean reversion and pin behavior matter more
- iceberg + gray absorption near GEX pin is high value

## 11. Gray marker fusion

MBO grades the gray marker; it does not replace it.

Long gray boosted by:

- bid iceberg at/under marker
- genuine bid wall under marker
- ask spoof pulled above
- liquidity void upward after absorption
- GEX support/pin below
- aggressive sells absorbed without price continuation

Long gray penalized by:

- spoof-like bid under marker
- genuine ask wall 4-12 ticks above
- ask iceberg overhead
- liquidity void below
- stale MBO data

Short gray boosted by:

- ask iceberg at/above marker
- genuine ask wall above marker
- bid spoof pulled below
- liquidity void downward
- GEX resistance/call wall above
- aggressive buys absorbed without price continuation

Short gray penalized by:

- spoof-like ask above marker
- genuine bid wall 4-12 ticks below
- bid iceberg below
- liquidity void above
- stale MBO data

Output grades:

- A+ = 85-100
- A = 75-84
- B = 60-74
- C = 45-59
- D/avoid = below 45

## 12. Replay validation

Databento historical MBO should be the validation path.

Validation buckets:

- gray only
- gray + MBO confirm
- gray + GEX confirm
- gray + MBO + GEX confirm
- gray + MBO warning
- gray + spoof conflict

Metrics:

- MFE over 5/15/30/60 seconds
- MAE over 5/15/30/60 seconds
- time-to-first-favorable-8-ticks
- time-to-first-adverse-8-ticks
- continuation probability
- reversal probability
- alert rate
- false positive rate

Success criteria:

- A/A+ gray fusion improves MFE/MAE by at least 20% over gray-only baseline.
- Warning/conflict bucket underperforms baseline, proving the warning has value.
- MBO+GEX bucket beats MBO-only and GEX-only.
- Signal count reduction stays under 25% unless expectancy improves materially.

Spoof proxy validation:

- precision > 65%
- false spoof on genuine walls < 20%
- median warning lead time > 250 ms
- high-confidence spoof alerts fewer than 10/hour in normal RTH

Iceberg proxy validation:

- precision > 70%
- executed/displayed ratio after signal > 2.5
- gray marker + iceberg confirmation improves MAE/MFE

Genuine wall validation:

- survival-to-touch rate > 60%
- meaningful interaction rate > 50%
- false genuine pull rate < 25%

## 13. Implementation roadmap

### Stage 0 - Schema and compatibility

Priority: P0

- Define schema v2.
- Keep V4-compatible fields.
- Add example fixtures.
- Add atomic writer/read tests.

Done when:

- V4 can still parse existing fields.
- V5 fixture validates.
- No partial JSON reads in stress test.

### Stage 1 - Rich payload from current Depth Radar

Priority: P0

Extend:

- `deep6/services/live_mbo_radar.py`
- `depth_radar_desktop/engine_bridge.py`
- `depth_radar_desktop/live/live_tab.py`
- `depth_radar_desktop/live/alerts_panel.py`
- `depth_radar_desktop/live/feature_gauges.py`

Add:

- episode_id
- in_touch_band
- interaction
- interaction_confidence
- absorption_ratio
- delta_2s
- delta_10s
- approach_speed
- attack_intensity
- mid_price / bid / ask
- source_quality

Done when:

- Desktop no longer receives thin wall-only payload.
- `/walls` includes rich fields.
- JSON remains fresh.
- Existing table does not crash on `side = bid/ask` or `duration_sec`.

### Stage 2 - Wall ranker

Priority: P0/P1

Create:

- `deep6/ml/depth_radar/wall_ranker.py`

Outputs:

- quality_score
- spoof_score
- iceberg_score
- genuine_score
- migration_score
- defense_score
- break_risk_score
- evidence[]

Done when:

- Every emitted wall has scores and evidence.
- Scores degrade if source is L2_APPROX or stale.

### Stage 3 - Source-quality split

Priority: P0/P1

Add source capability flags:

- TRUE_MBO
- L2_APPROX
- STALE
- DEGRADED

Rules:

- True order-id spoof confidence only with TRUE_MBO.
- Rithmic aggregate mode can still show wall behavior but with lower confidence.

Done when:

- UI says when feed is L2 approximation.
- Confidence multiplier is visible in payload.

### Stage 4 - Add Rithmic trades/tape

Priority: P1

Extend Rithmic live mode to include trade/tick subscription.

Done when:

- delta_2s/delta_10s/absorbed_volume/attack_intensity are non-zero live when tape is active.
- Absorption features no longer depend only on book updates.

### Stage 5 - DEEP6DepthRadarV5

Priority: P1

Create side-by-side V5 indicator.

Done when:

- NT8 F5 compile succeeds.
- V4 remains intact.
- V5 renders top levels/HUD cleanly.
- No stops/targets are drawn.

### Stage 6 - GEX fusion

Priority: P1

Annotate walls with nearest GEX level and alignment.

Done when:

- Every wall has gex block when GEX map available.
- Stale/missing GEX reduces confidence and is shown.

### Stage 7 - Gray marker fusion

Priority: P1

Add gray marker quality scoring and badge.

Done when:

- Active gray marker gets A/B/C/D quality.
- Badge is optional.
- MBO remains context, not entry generator.

### Stage 8 - Replay scorecards

Priority: P1/P2

Build replay validator.

Done when:

- Daily replay produces spoof/iceberg/genuine/gray-fusion metrics.
- Same input produces deterministic classifications.
- Metrics are good enough before live-trade trust.

## 14. Immediate next build recommendation

The best next engineering move is not to jump straight to a new NT8 indicator.

First build the data brain correctly:

1. Add rich schema v2 while preserving current JSON fields.
2. Add `source_quality` and confidence multiplier.
3. Add `wall_ranker.py` for quality/spoof/iceberg/migration scores.
4. Extend `/walls` and `depth_radar_walls.json` with scores/evidence.
5. Validate with targeted Python tests and live JSON freshness.
6. Then create `DEEP6DepthRadarV5.cs` to render the richer payload.

This keeps the system stable and avoids building a pretty UI on thin data.

## 15. Final operating principle

The best DEEP6 MBO system should tell the trader:

- this level is real
- this level is fake/fleeting
- this level is refreshing/iceberg-like
- this level is migrating
- this side is becoming a liquidity void
- this gray marker is stronger/weaker because of those facts
- this GEX area has or does not have real microstructure support

It should not say:

- blind long/short from MBO alone
- illegal spoofing accusation
- hard stops/targets overlays
- far-away always-on levels with no near-price relevance

Best one-line model:

Gray marker finds the trade. TradeGEX defines the battlefield. MBO proves whether the liquidity at that battlefield is real, fake, refreshing, migrating, or gone.
