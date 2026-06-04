# Institutional MBO AI Architecture — Complete Specification

Blueprint for a trading system that operates beyond human cognitive capacity.
Every component, every data flow, every decision layer.

---

## THE CORE THESIS

Human traders process signals sequentially. They can hold 5-7 concepts in
working memory simultaneously. They hesitate. They get tired. They have
emotional responses to losses.

This system processes 100+ signals simultaneously, never hesitates, never
tires, and has no emotional response. Its edge is not any single signal —
it's the simultaneous synthesis of everything the order book reveals.

---

## LAYER 0: DATA INGESTION

### Live Data Sources
```
Rithmic DepthByOrder (MBO)
  ├── exchange_order_id (unique per order)
  ├── update_type: NEW / CHANGE / DELETE
  ├── depth_order_priority (queue position)
  ├── sequence_number (gap detection)
  └── transaction_type: BUY / SELL

FlashAlpha (GEX/DEX/VEX/CHEX)
  ├── net_gex, zero_gamma, call_wall, put_wall
  ├── regime: positive / negative / transition
  └── dealer_pressure_score

Massive.com (Options chain)
  ├── Real-time Greeks (delta, gamma, theta, vega)
  ├── IV, OI, signed premium flow
  └── 0DTE concentration

Macro calendar
  └── FOMC, CPI, NFP, earnings — ±30s blackout windows
```

### Throughput requirements
- Rithmic MBO: 1,000-10,000 events/sec during peak
- FlashAlpha: 1 poll/60s (REST)
- Options: WebSocket, ~100 updates/sec
- All events timestamped to nanosecond, UTC

---

## LAYER 1: BOOK RECONSTRUCTION

### MBO Order Book (the foundation)
```
MBOOrderBook
  ├── orders: Dict[order_id → OrderState]
  │     ├── price, size, side
  │     ├── add_time_ns, modify_count
  │     └── depth_order_priority
  ├── bids: SortedDict[tick → PriceLevelState]
  ├── asks: SortedDict[tick → PriceLevelState]
  └── lifecycle: Dict[order_id → LifecycleRecord]
        ├── add_time, cancel_time, life_ms
        ├── fills[], fill_ratio
        └── was_near_touch, imbalance_during_life

BookIntegrityValidator (runs on every event)
  ├── Sequence gap detection → ERROR alert
  ├── Crossed book detection → CRITICAL alert (pause consumers)
  ├── Negative size detection → CRITICAL alert
  ├── Stale level detection → WARN alert
  └── Duplicate order ID → ERROR alert

HARD GATE: No detector runs until book passes integrity check.
```

### Derived views
```
MBPView (aggregated from MBO)
  ├── Top 40 bid/ask levels with total size
  ├── Microprice (quantity-weighted mid)
  └── Spread in ticks

QueueTracker
  ├── Per-price queue ordered by depth_order_priority
  ├── Queue depletion rate (fills/ms)
  └── Time-to-fill estimates
```

---

## LAYER 2: SIGNAL DETECTION (100+ signals)

### Category A: MBO-Native Detectors (require order IDs)
```
SpoofDetector
  Input: lifecycle records on every CANCEL event
  Output: SpoofResult{order_id, life_ms, size, confidence, reason_codes[]}
  Latency: < 500μs

IcebergDetector
  Input: trade events + ADD events at same price
  Output: IcebergResult{price, hvr, refreshes, confidence}
  Latency: < 200μs

LayeringDetector
  Input: book state snapshot every 100ms
  Output: LayeringResult{levels[], side, n_orders, confidence}
  Latency: < 1ms

MomentumIgnitionDetector
  Input: Hawkes branching ratio + trade rate + price velocity
  Output: IgnitionResult{direction, branching_ratio, confidence}
  Latency: < 200μs

QueueDepletionDetector
  Input: QueueTracker state
  Output: DepletionResult{price, rate, time_to_fill_ms}
  Latency: < 100μs
```

### Category B: Footprint Detectors (work on aggregated MBP)
```
AbsorptionDetector (4 variants: ABS_01-04)
ExhaustionDetector (6 variants: EXH_01-06)
ImbalanceDetector (9 variants: IMB_01-09)
DeltaDetector (11 variants: DELT_01-11)
AuctionDetector (5 variants: AUCT_01-05)
TrapDetector (5 variants: TRAP_01-05)
VolPatternDetector (6 variants: VOLP_01-06)
```

### Category C: Flow Detectors
```
OFIDetector
  Computes OFI at depth 1, 5, 10 every 100ms
  Output: OFIResult{ofi_1, ofi_5, ofi_10, trend}

VPINEstimator
  Volume-bucket VPIN, rolling 50 buckets
  Output: VPINResult{vpin, regime: HIGH/MIXED/LOW_INFORMED}

KyleLambdaEstimator
  Rolling OLS on recent trades
  Output: LambdaResult{lambda, regime: THIN/NORMAL/DEEP}

HawkesEstimator
  Branching ratio from inter-arrival variance
  Output: HawkesResult{branching_ratio, regime: ENDOGENOUS/MIXED/EXOGENOUS}
```

### Category D: Cross-Market Detectors
```
GEXRegimeDetector
  Input: FlashAlpha data
  Output: GEXResult{regime, distance_to_flip, dealer_pressure}

OptionsFlowDetector
  Input: Massive.com options data
  Output: FlowResult{net_premium, sweep_intensity, 0dte_concentration}

DarkPoolDetector
  Input: trades at mid with no visible order
  Output: DarkPoolResult{price, size, direction}

ESNQLeadLagDetector
  Input: ES and NQ order flow (if available)
  Output: LeadLagResult{leader, lag_ms, confidence}
```

### Category E: Context Detectors
```
SessionContextDetector
  Input: time, prior session H/L/close, gap type
  Output: SessionResult{session_type, bias, key_levels[]}

MacroWindowDetector
  Input: macro calendar
  Output: MacroResult{is_blackout, seconds_to_event, event_type}

RegimeDetector
  Input: recent price action, volume, volatility
  Output: RegimeResult{regime: TRENDING/MEAN_REVERTING/CHOPPY/THIN}

TimeOfDayDetector
  Input: current time ET
  Output: TODResult{session: OPEN/MORNING/LUNCH/AFTERNOON/CLOSE, bias}
```

---

## LAYER 3: LEVEL REGISTRY

### Unified Level Hierarchy
```
LevelRegistry
  Sources (in priority order):
    1. Live MBO absorption/iceberg (highest conviction — real money)
    2. GEX call wall / put wall / zero gamma
    3. Prior session H/L/close
    4. Value area H/L (70% volume)
    5. VWAP
    6. Volume profile HVN/LVN
    7. Options flow alignment (strikes with heavy OI)

  Per level:
    ├── price, source_types[], freshness_score
    ├── confluence_score (0-100)
    ├── grade: A+(85+) / A(70-84) / B(55-69) / C(40-54) / Ignore(<40)
    └── status: FRESH / ACTIVE / TESTED / BROKEN / INVALIDATED

  Deduplication: merge levels within 2 ticks
  Freshness decay: score × 0.95 per bar, boost on retest
```

### Confluence Scoring
```
Weights:
  +25 Active MBO absorption/iceberg at level
  +20 GEX wall or zero gamma
  +20 DOM absorption (multi-bar)
  +15 Iceberg detected
  +15 Options flow alignment
  +5  Prior session level

Penalties:
  -25 Spoof risk (large order appeared and cancelled)
  -25 DOM rejection (level tested and broke)
  -20 Options conflict (flow against level)
  -15 Noise regime (VPIN < 0.2, thin session)
```

---

## LAYER 4: FEATURE EXTRACTION

### 50-Feature Vector (per bar, per snapshot)
```
LOB State (15 features):
  microprice_deviation, spread_ticks, ofi_1, ofi_5, ofi_10,
  depth_ratio, level_ratio, tob_ratio, bid_depth_5, ask_depth_5,
  bid_depth_10, ask_depth_10, book_pressure, queue_imbalance, spread_trend

Flow Features (10 features):
  vpin, kyle_lambda, branching_ratio, aggressor_ratio, trade_rate,
  avg_trade_size, delta_velocity, cvd_divergence, sweep_intensity, dark_pool_ratio

Detector Outputs (15 features):
  spoof_confidence, iceberg_confidence, absorption_confidence,
  layering_confidence, vacuum_confidence, sweep_confidence,
  ofi_trend, momentum_ignition_risk, queue_depletion_rate,
  imbalance_stacked, delta_trap, exhaustion_signal,
  absorption_multi_bar, stop_cluster_proximity, level_confluence_score

Context Features (10 features):
  gex_regime, distance_to_flip, dealer_pressure, options_flow_direction,
  session_bias, time_of_day_score, macro_blackout, vix_regime,
  es_nq_lead_lag, dark_pool_direction
```

---

## LAYER 5: LLM EXPERT REASONING

### Snapshot Structure (< 4K tokens)
```json
{
  "symbol": "NQ",
  "timestamp": "2026-05-19T10:30:00.123456789Z",
  "price": 21550.25,
  "spread_ticks": 1,
  "microprice_deviation": 0.12,

  "dom_snapshot": {
    "bids": [{"price": 21550.00, "size": 42, "n_orders": 18}, ...],
    "asks": [{"price": 21550.25, "size": 35, "n_orders": 12}, ...]
  },

  "mbo_evidence": {
    "spoof_candidates": [
      {"order_id": "R8841290", "size": 412, "life_ms": 2840,
       "fill_ratio": 0.0, "confidence": 0.87}
    ],
    "iceberg_candidates": [
      {"price": 21555.25, "hvr": 20.58, "refreshes": 9, "confidence": 0.94}
    ],
    "absorption_signals": [
      {"price": 21562.50, "aggressive_vol": 184, "hold_ratio": 0.95}
    ]
  },

  "flow_state": {
    "ofi_1": 0.42, "ofi_5": 0.31, "ofi_10": 0.28,
    "vpin": 0.61, "kyle_lambda": 0.0023,
    "branching_ratio": 0.71, "aggressor_ratio": 0.58
  },

  "gex_context": {
    "regime": "positive", "gamma_flip": 21400.00,
    "call_wall": 21600.00, "put_wall": 21300.00,
    "dealer_pressure": 0.34
  },

  "level_registry": {
    "active_levels": [
      {"price": 21550.00, "grade": "A+", "score": 87,
       "sources": ["mbo_absorption", "gex_put_wall", "prior_low"]}
    ]
  },

  "context": {
    "session": "MORNING", "time_et": "10:30",
    "macro_blackout": false, "vpin_regime": "MIXED"
  },

  "exemplars": [/* top-3 similar historical situations */]
}
```

### 13 Competency Domains (LLM must demonstrate all)
```
1.1  MBO vs MBP discipline — cite order IDs, not level totals
1.2  Intentions vs transactions — qualify every size claim
1.3  Iceberg detection — cite HVr AND refresh count
1.4  Spoof detection — cite order_id, life_ms, fill_ratio
1.5  Absorption recognition — cite aggressive_vol + level_held
1.6  Layering recognition — cite ≥3 levels, same side
1.7  Sweep recognition — cite multi-level sequence + target
1.8  Hidden liquidity — cite trade at price with no visible order
1.9  Quote stuffing — cite event rate, not directional signal
1.10 Calibrated uncertainty — high requires MBO evidence + context
1.11 Context modifiers — reference session/GEX/macro in assessment
1.12 Falsifiability — concrete criteria (prices, sizes, time windows)
1.13 No-signal discipline — NEVER issue buy/sell/enter/exit
```

### Output Schema (strict JSON via tool_use)
```json
{
  "primary_pattern": "spoof|iceberg|absorption|sweep|layering|vacuum|none",
  "evidence": ["specific MBO evidence cited"],
  "confidence": "high|medium|low",
  "trader_read": "What this means for price direction (no trade commands)",
  "confirmation_criteria": "Specific, testable, time-bounded",
  "invalidation_criteria": "Specific, testable, opposed to confirmation",
  "do_not_trade": false,
  "do_not_trade_reason": null
}
```

---

## LAYER 6: STATISTICAL CLASSIFIERS

### Three-Model Ensemble
```
XGBoost (primary)
  Features: 50-feature vector
  Target: forward_return_5b (signed by signal direction)
  Training: 80/20 time-based split, Optuna 50 trials
  Validation: walk-forward, WFE > 70% gate

LightGBM (secondary)
  Same features, different hyperparameters
  Faster inference, better on sparse features

CatBoost (tertiary)
  Handles categorical features (regime, session type)
  More robust to outliers

Meta-model (stacking)
  Input: XGB + LGBM + CatBoost probabilities + LLM confidence
  Output: final_probability, direction, confidence_tier
  Inference: < 100ms total
```

### Label Generation (no lookahead)
```
forward_return_5b: close[t+5] - close[t]
forward_return_15b: close[t+15] - close[t]
sweep_label: did price sweep through level within 10 bars?
absorption_label: did level hold for 30+ bars after signal?
trap_label: did price reverse within 5 bars of extreme?
```

---

## LAYER 7: DECISION ENGINE

### 14 Decision States
```
WATCH states (output only, no execution):
  ABSORBING_BID    — bid absorption confirmed, bullish
  ABSORBING_ASK    — ask absorption confirmed, bearish
  ICEBERG_BID      — hidden bid, bullish
  ICEBERG_ASK      — hidden ask, bearish
  SPOOF_BID        — fake bid, bearish (fade the spoof)
  SPOOF_ASK        — fake ask, bullish (fade the spoof)
  SWEEP_UP         — upward sweep, watch for reversal
  SWEEP_DOWN       — downward sweep, watch for reversal
  LAYERING_BID     — fake bid depth, bearish
  LAYERING_ASK     — fake ask depth, bullish
  MOMENTUM_IGNITION — manufactured move, fade incoming
  STOP_HUNT        — stop sweep, reversal imminent
  DARK_POOL_BID    — institutional buying, bullish
  DARK_POOL_ASK    — institutional selling, bearish

NO_EDGE states:
  NO_EDGE          — insufficient evidence
  MACRO_BLACKOUT   — within ±30s of macro event
  THIN_SESSION     — VPIN < 0.2, unreliable signals
  CONFLICTING      — signals disagree, no clear read
```

### Conviction Requirements
```
HIGH conviction (all required):
  ✓ Primary pattern confirmed by MBO evidence (order IDs)
  ✓ Confluence score ≥ 70 at relevant level
  ✓ LLM confidence = "high"
  ✓ Classifier probability ≥ 0.65
  ✓ No macro blackout
  ✓ VPIN in MIXED or HIGH_INFORMED regime
  ✓ At least 3 signal categories agree

MEDIUM conviction:
  ✓ Primary pattern confirmed
  ✓ Confluence score ≥ 55
  ✓ LLM confidence = "medium"
  ✓ Classifier probability ≥ 0.55

LOW conviction → NO_EDGE (do not trade)
```

---

## LAYER 8: SHADOW MODE AND VALIDATION

### Shadow Mode (live without trading)
```
All data sources → full pipeline → decisions logged
Every decision: timestamp, state, confidence, evidence
30s/60s outcome scoring: was the read correct?
Rolling accuracy by pattern type and confidence level

Promotion gate:
  ✓ 5 full sessions without crash
  ✓ High-confidence calls confirm > 70% on 30s forward
  ✓ No single pattern dominates (diversified edge)
  ✓ Profit factor ≥ 1.3 on simulated trades
```

### Outcome Feedback Loop
```
OutcomeLogger → OutcomeCritic → ExemplarCurator

Wrong high-confidence calls → exemplar store (failure modes)
Right high-confidence calls → exemplar store (success patterns)
Rolling calibration: stated confidence vs actual accuracy
Auto-disable: if pattern accuracy < 50% over 20 calls → disable
```

---

## LAYER 9: EXECUTION (when ready)

### Risk Gates (all must pass)
```
1. Shadow mode passed (5 sessions, 70% accuracy)
2. Profit factor ≥ 1.3 on replay data
3. Max drawdown < $2,000/session on replay
4. No single signal > 30% of decisions
5. Macro blackout respected
6. Position size ≤ 1 contract until 30-day paper gate passed
```

### Kill Switches
```
Session loss > $500 → halt for session
Consecutive losses > 3 → halt for session
Book integrity CRITICAL → halt immediately
LLM timeout > 20% of calls → fall back to rule-based
Rithmic disconnect → halt immediately
```

---

## THE UNBEATABLE ADVANTAGES

What this system does that no human can match:

1. **Simultaneity**: Processes all 100+ signals at once, every 100ms
2. **Speed**: Detects spoof within 500μs of cancel event
3. **Memory**: Tracks every order ID lifecycle simultaneously
4. **Consistency**: Same decision process every time, no fatigue
5. **Pattern depth**: Compares current state to millions of historical instances
6. **Adversarial awareness**: Knows every manipulation tactic and its signature
7. **Cross-market synthesis**: Simultaneously processes MBO + options + GEX
8. **Calibration**: Knows when it doesn't know (no-edge discipline)
9. **Learning**: Every wrong call becomes a training example
10. **Falsifiability**: Every assessment has testable criteria

The human brain can hold 7 concepts simultaneously.
This system holds 100+, never forgets, never hesitates.
