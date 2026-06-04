# Cross-Market MBO DOM + Options/GEX + NQStats + MADLevels AI Engine

## Engineering Handoff — Final Draft

## 0. Mission

Build a production-grade Python intelligence engine for NQ futures that combines:

1. Rithmic MBO / Level 2 DOM data
2. Futures trade tape and order-book lifecycle data
3. Options flow and options chain data from Massive.com
4. GEX / DEX / VEX / CHEX / dealer exposure data from Flash Alpha
5. NQStats statistical session context
6. MADLevels-style absorption/failure levels
7. LLM-based expert reasoning with prompt + exemplars + retrieval + outcome logging
8. Separate statistical classifiers for probability modeling

The goal is not to create a basic DOM indicator.

The goal is to create a cross-market liquidity intelligence engine that can explain whether a level is real, fake, absorbing, spoofing, trapped, pinned, or ready to expand.

Core principle:

- Options/GEX gives the battlefield.
- NQStats gives the statistical session roadmap.
- MADLevels gives proven absorption/failure zones.
- MBO DOM gives the live execution truth.
- Tape confirms aggression.
- The LLM explains the read.
- Classifiers quantify probabilities.
- Replay and outcome logging decide whether the system is actually good.

---

## 1. What You Were Missing

### 1.1 Data entitlement and feed reality checks

Do not assume every source gives the same granularity.

You must explicitly validate:

- Does Rithmic account have CME MBO enabled?
- Is the API access R | API+, R | Protocol, or another bridge?
- Is order ID available and stable enough to track lifecycle?
- Does the feed expose add/modify/cancel/trade events or only aggregate depth?
- What is the timestamp precision?
- Are timestamps exchange time, provider time, or local receive time?
- Is there sequence numbering?
- How are disconnects handled?
- Can the system recover book state after packet loss?
- Does Massive options data subscription include real-time WebSockets, historical OPRA, Greeks, IV, and open interest?
- Does Flash Alpha provide API access or must it be scraped/exported/manual?
- Does MADLevels have an API/export, or must the system create its own MADLevels-style engine?
- Does NQStats expose machine-readable data, or must levels/stats be manually configured?

This must be solved before live trading logic matters.

### 1.2 Book integrity is the foundation

If book reconstruction is wrong, everything above it is garbage.

Add mandatory integrity checks:

- sequence gap detection
- crossed-book detection
- negative size detection
- stale level detection
- inconsistent cancel detection
- duplicate order ID detection
- local clock drift detection
- reconnect snapshot rebuild
- raw event persistence before transformation

### 1.3 Time synchronization matters

You are combining futures MBO, options flow, GEX, NQStats, and MADLevels.

If timestamps are off, cross-market conclusions are fake.

Require:

- monotonic event clock
- provider timestamp and local receipt timestamp
- latency measurement per source
- NTP-synchronized machine
- UTC storage
- exchange/session timezone conversion layer
- event-time vs processing-time separation

### 1.4 LLM is not the classifier

The LLM should not be treated as a model trained through weight updates.

The LLM layer is an expert reasoning layer trained operationally through:

- prompt constitution
- taxonomy
- few-shot exemplars
- retrieval of similar historical cases
- outcome logging
- failure review
- exemplar curation

Fine-tuning comes later only for classifier layers such as:

- XGBoost
- LightGBM
- CatBoost
- TLOB transformer
- sequence model
- meta-label model

### 1.5 The system needs a no-trade engine

Most DOM states are noise.

The engine must be good at saying:

- no edge
- too noisy
- too close to news
- spoof risk high
- options conflict
- GEX pin environment
- DOM not confirming
- level not tested
- low confidence

A system that always has an opinion will fail.

### 1.6 The system needs falsifiable outputs

Every LLM read must include:

- exact confirmation criteria
- exact invalidation criteria
- time window
- level or price zone
- minimum event thresholds
- confidence
- reason codes

If the read cannot be tested 30–60 seconds later, it is not useful.

### 1.7 You need outcome replay, not just backtesting

Traditional bar backtesting is not enough.

You need:

- event replay
- DOM reconstruction replay
- options replay
- GEX context replay
- LLM snapshot replay
- post-call outcome scoring
- calibration scoring
- false positive analysis
- false negative analysis

### 1.8 You need two levels of AI

Use both:

1. LLM reasoning expert
   - Explains market state
   - Produces JSON assessment
   - Uses exemplars
   - Does not issue buy/sell orders

2. Statistical classifier layer
   - Learns from labels
   - Predicts probabilities
   - Can be retrained
   - Scores forward outcomes

### 1.9 You need level hierarchy

Every price level should be graded.

A level is stronger when multiple independent systems agree:

- NQStats target/reference level
- MADLevel absorption/failure level
- GEX/call wall/put wall/zero gamma
- prior RTH high/low
- Asia high/low
- London high/low
- VWAP
- volume profile HVN/LVN
- live MBO iceberg
- live MBO absorption
- options flow alignment

### 1.10 You need a failure mode library

Track failure modes explicitly:

- fake spoof flag
- iceberg exhausted
- absorption broke
- options flow lagged futures
- GEX level failed to matter
- MADLevel stale
- NQStats bias conflicted with live flow
- macro volatility invalidated DOM
- LLM overconfident
- classifier overfit
- timestamp mismatch
- replay/live mismatch

---

## 2. Final System Architecture

```text
/cross_market_liquidity_ai
  /connectors
    rithmic_mbo_connector.py
    databento_optional_connector.py
    massive_options_connector.py
    flashalpha_gex_connector.py
    nqstats_connector.py
    madlevels_connector.py
    websocket_manager.py
    connection_health.py

  /book
    mbo_order_book.py
    mbp_order_book.py
    book_reconstructor.py
    queue_tracker.py
    order_lifecycle_tracker.py
    book_integrity.py

  /tape
    trade_classifier.py
    aggressor_detector.py
    sweep_detector.py
    delta_engine.py

  /options
    options_chain_engine.py
    options_flow_engine.py
    options_quote_engine.py
    gex_engine.py
    dealer_pressure_engine.py
    strike_mapper.py
    cross_asset_mapper.py

  /stats
    nqstats_engine.py
    session_classifier.py
    aln_engine.py
    statistical_bias_engine.py

  /levels
    madlevels_engine.py
    level_registry.py
    level_freshness.py
    level_confluence.py

  /features
    dom_features.py
    spoof_features.py
    iceberg_features.py
    absorption_features.py
    liquidity_vacuum_features.py
    tape_features.py
    options_features.py
    gex_features.py
    nqstats_features.py
    madlevels_features.py
    cross_market_features.py

  /rules
    expert_dom_rules.py
    options_rules.py
    nqstats_rules.py
    madlevels_rules.py
    cross_market_rules.py
    trap_rules.py
    no_trade_rules.py

  /llm_expert
    dom_expert_prompt.md
    dom_expert_skills.md
    snapshot_builder.py
    exemplar_retriever.py
    llm_router.py
    outcome_logger.py
    outcome_critic.py
    exemplar_curator.py
    validation_harness.py

  /models
    train_xgboost.py
    train_lightgbm.py
    train_catboost.py
    train_sequence_model.py
    tlob_transformer.py
    inference_engine.py
    meta_model.py
    model_registry.py

  /labels
    label_generator.py
    forward_return_labels.py
    sweep_labels.py
    trap_labels.py
    absorption_labels.py
    gamma_reaction_labels.py
    madlevel_reaction_labels.py

  /replay
    mbo_replay_engine.py
    options_replay_engine.py
    gex_replay_engine.py
    synchronized_replay.py
    shadow_mode.py

  /storage
    raw_event_store.py
    parquet_writer.py
    feature_store.py
    prediction_store.py
    outcome_store.py
    exemplar_store.py

  /dashboard
    dom_dashboard.py
    gex_dashboard.py
    nqstats_dashboard.py
    madlevels_dashboard.py
    ai_decision_dashboard.py
    replay_dashboard.py

  /risk
    risk_engine.py
    regime_gater.py
    news_filter.py
    trade_filter.py
    confidence_calibrator.py

  /tests
    test_book_reconstruction.py
    test_spoof_detector.py
    test_iceberg_detector.py
    test_absorption_detector.py
    test_mapper.py
    test_outcome_logger.py
    test_replay.py

  /config
    settings.yaml
    symbols.yaml
    thresholds.yaml
    sessions.yaml

  main.py
  README.md
```

---

## 3. Data Schemas

### 3.1 Futures MBO event

```json
{
  "timestamp_exchange_ns": 0,
  "timestamp_receive_ns": 0,
  "source": "rithmic",
  "symbol": "NQ",
  "event_type": "add|modify|cancel|trade|depth_update|snapshot|heartbeat",
  "side": "bid|ask|buy|sell|unknown",
  "price": 0.0,
  "price_ticks": 0,
  "size": 0,
  "order_id": "",
  "sequence_id": 0,
  "level": 0,
  "best_bid": 0.0,
  "best_ask": 0.0,
  "spread_ticks": 0,
  "trade_price": 0.0,
  "trade_size": 0,
  "aggressor_side": "buy|sell|unknown"
}
```

### 3.2 Options event

```json
{
  "timestamp_exchange_ns": 0,
  "timestamp_receive_ns": 0,
  "source": "massive",
  "underlying": "QQQ|NDX|SPX|SPY",
  "option_symbol": "",
  "expiration": "YYYY-MM-DD",
  "strike": 0.0,
  "type": "call|put",
  "event_type": "trade|quote|snapshot|chain_update",
  "price": 0.0,
  "size": 0,
  "premium": 0.0,
  "bid": 0.0,
  "ask": 0.0,
  "mid": 0.0,
  "iv": 0.0,
  "delta": 0.0,
  "gamma": 0.0,
  "theta": 0.0,
  "vega": 0.0,
  "open_interest": 0,
  "volume": 0,
  "trade_side_estimate": "buy|sell|unknown"
}
```

### 3.3 GEX event

```json
{
  "timestamp_ns": 0,
  "source": "flashalpha",
  "underlying": "QQQ|NDX|SPX|SPY",
  "spot": 0.0,
  "net_gex": 0.0,
  "zero_gamma": 0.0,
  "call_wall": 0.0,
  "put_wall": 0.0,
  "peak_gamma": 0.0,
  "dex": 0.0,
  "vex": 0.0,
  "chex": 0.0,
  "regime": "positive_gamma|negative_gamma|transition|unknown"
}
```

### 3.4 Level registry object

```json
{
  "level_id": "",
  "price": 0.0,
  "price_ticks": 0,
  "source_types": ["nqstats", "madlevels", "gex", "dom", "vwap", "profile"],
  "level_type": "support|resistance|magnet|absorption|rejection|breakout|pin",
  "freshness_score": 0.0,
  "touch_count": 0,
  "absorption_score": 0.0,
  "iceberg_score": 0.0,
  "spoof_risk": 0.0,
  "options_alignment": 0.0,
  "nqstats_alignment": 0.0,
  "confluence_score": 0.0,
  "status": "fresh|active|tested|broken|flipped|invalidated"
}
```

---

## 4. Core Detectors

### 4.1 Spoof detector

A spoof is not merely a cancellation.

Required evidence:

- large order relative to surrounding levels
- specific order ID lifecycle tracked
- short lifetime
- canceled before meaningful trade at that price
- near enough to influence behavior
- book imbalance changed while order existed
- optional opposite-side aggression after pull

Output:

```json
{
  "pattern": "spoof",
  "side": "bid|ask",
  "price": 0.0,
  "order_id": "",
  "life_ms": 0,
  "size": 0,
  "executed_qty": 0,
  "distance_to_touch_ticks": 0,
  "spoof_probability": 0.0,
  "reason_codes": []
}
```

### 4.2 Iceberg detector

Required evidence:

- traded cumulative size at level meaningfully exceeds peak visible size
- refresh/add behavior after fills
- level holds despite aggression
- order book replenishment persists

Rule of thumb:

- traded_cum / peak_visible >= 3x
- refresh_count >= 2
- stronger if ratio > 10x and refresh_count > 5

### 4.3 Absorption detector

Bid absorption:

- aggressive sellers hit bid
- price does not break lower
- bid remains or reloads
- seller aggression slows or fails

Ask absorption:

- aggressive buyers lift ask
- price does not break higher
- ask remains or reloads
- buyer aggression slows or fails

### 4.4 Liquidity vacuum detector

Detects when book thins ahead of price.

Inputs:

- near-touch depth collapse
- multi-level cancel wave
- spread instability
- fast aggressive flow
- price acceleration
- low resting liquidity ahead

### 4.5 Layering detector

Layering requires at least 3 contiguous levels.

Evidence:

- stacked oversized size across sequential prices
- comparable sizes
- few orders or repeated participant behavior
- dissolves as price approaches
- often near obvious reference level

### 4.6 Sweep detector

Sweep requires multi-level aggressive execution.

Evidence:

- rapid sequential prints through multiple levels
- obvious target nearby
- liquidity taken, not just quoted
- follow-through or rejection classified separately

---

## 5. Options/GEX Engine

### 5.1 Required features

- net GEX
- distance to zero gamma
- distance to call wall
- distance to put wall
- peak gamma proximity
- GEX regime
- dealer pressure score
- call premium imbalance
- put premium imbalance
- call/put volume imbalance
- sweep intensity
- IV expansion
- OI concentration
- 0DTE concentration
- charm/vanna exposure if available

### 5.2 Regimes

Positive gamma:

- pinning/mean reversion more likely
- breakouts need stronger DOM proof
- absorption at levels matters more

Negative gamma:

- volatility expansion more likely
- liquidity vacuums matter more
- trend continuation can extend

Zero gamma:

- transition zone
- require DOM confirmation
- expect unstable behavior

---

## 6. NQStats Engine

### 6.1 Required concepts

- ALN session structure
- Asia high/low
- London high/low
- NY open behavior
- prior RTH high/low
- prior RTH close
- gap up/gap down/inside range
- 1H continuation/reversal tendencies
- noon curve logic
- NY high/low break probabilities
- one-sided vs two-sided session probabilities

### 6.2 Output

```json
{
  "session_structure": "",
  "statistical_bias": "bullish|bearish|neutral|two_sided",
  "expected_targets": [],
  "invalidation_levels": [],
  "probability_notes": [],
  "confidence": 0.0
}
```

---

## 7. MADLevels-Style Engine

### 7.1 Concept

MADLevel is a mechanical absorption/failure level.

It is created when price shows:

- aggressive traders failing
- repeated rejection
- absorption
- delta divergence
- hidden or visible liquidity holding
- failed continuation
- strong reaction after test

### 7.2 MADLevel object

```json
{
  "level_price": 0.0,
  "level_type": "bid_absorption|ask_absorption|failed_breakout|failed_breakdown",
  "created_time": "",
  "touch_count": 0,
  "absorption_score": 0.0,
  "iceberg_score": 0.0,
  "spoof_risk": 0.0,
  "reaction_score": 0.0,
  "freshness_score": 0.0,
  "confluence_score": 0.0,
  "status": "fresh|active|tested|broken|flipped|invalidated"
}
```

---

## 8. Confluence Scoring

Score every important level from 0 to 100.

Example weights:

- +20 NQStats high-probability target/reference
- +20 active MADLevel
- +15 GEX/call wall/put wall/zero gamma nearby
- +15 DOM absorption confirms
- +10 iceberg/reload confirms
- +10 options flow aligns
- +10 session bias supports direction
- +5 prior RTH/Asia/London/VWAP/profile confluence
- -25 spoof risk high
- -25 DOM rejects expected direction
- -20 options flow conflicts
- -15 macro/noise regime

Grades:

- A+ = 85–100
- A = 70–84
- B = 55–69
- C = 40–54
- Ignore = below 40

---

## 9. LLM Expert Layer

### 9.1 LLM role

The LLM is a reasoning expert, not the statistical model.

It must read structured snapshots and produce strict JSON assessments.

It must not issue direct buy/sell orders.

### 9.2 LLM input

Each call includes:

- current DOM snapshot
- order lifecycle evidence
- spoof candidates
- iceberg candidates
- absorption signals
- liquidity vacuum signals
- active MADLevels
- NQStats context
- GEX/options context
- level confluence scores
- session/macro risk
- similar historical exemplars
- recent outcome stats for similar calls

### 9.3 LLM output

```json
{
  "primary_pattern": "spoof|iceberg|absorption|layering|sweep|hidden_liquidity|quote_stuffing|gamma_pin|madlevel_absorption|none",
  "secondary_patterns": [],
  "evidence": [],
  "confidence": "low|medium|high",
  "market_context": {
    "nqstats_bias": "",
    "gex_context": "",
    "madlevel_context": "",
    "session_context": ""
  },
  "confirmation_criteria": "",
  "invalidation_criteria": "",
  "trader_read": "",
  "do_not_trade_reason": "",
  "reason_codes": []
}
```

### 9.4 Competency requirements

The LLM must demonstrate:

- MBO vs MBP discipline
- intentions vs transactions distinction
- iceberg detection discipline
- spoof detection discipline
- absorption recognition
- layering recognition
- sweep recognition
- hidden liquidity recognition
- quote stuffing/pinging recognition
- calibrated uncertainty
- context modifiers
- falsifiability discipline
- no-signal discipline

---

## 10. Exemplar and Outcome Feedback System

### 10.1 Exemplar database

Each exemplar:

```json
{
  "snapshot": {},
  "gold_assessment": {},
  "pattern": "",
  "session": "",
  "gex_regime": "",
  "madlevel_nearby": true,
  "nqstats_context": "",
  "outcome_30s": {},
  "outcome_60s": {},
  "was_correct": true,
  "failure_reason": ""
}
```

### 10.2 Seed goals

- 30–50 spoof examples
- 30–50 iceberg examples
- 30–50 absorption examples
- 30–50 layering examples
- 30–50 sweep examples
- 30–50 MADLevel absorption examples
- 30–50 gamma level reaction examples
- 30–50 no-signal examples
- 30–50 macro/noise examples

### 10.3 Outcome logger

Every LLM call is checked after 30s and 60s.

Store:

```json
{
  "llm_call_id": "",
  "timestamp": "",
  "snapshot": {},
  "llm_assessment": {},
  "outcome_30s": {},
  "outcome_60s": {},
  "confirmed": true,
  "invalidated": false,
  "ambiguous": false,
  "notes": ""
}
```

Wrong calls become future exemplars.

---

## 11. Classifier Layer

### 11.1 Models

Start with:

- XGBoost
- LightGBM
- CatBoost

Then test:

- LSTM
- Transformer
- TLOB-style event sequence model

### 11.2 Targets

- +10 ticks before -8 ticks
- +20 ticks before -10 ticks
- -10 ticks before +8 ticks
- -20 ticks before +10 ticks
- sweep up/down
- failed breakout/breakdown
- absorption reversal
- gamma pin
- MADLevel reaction
- liquidity vacuum continuation

### 11.3 Meta-model output

```json
{
  "bullish_probability": 0.0,
  "bearish_probability": 0.0,
  "neutral_probability": 0.0,
  "volatility_expansion_probability": 0.0,
  "mean_reversion_probability": 0.0,
  "spoof_probability": 0.0,
  "iceberg_probability": 0.0,
  "absorption_probability": 0.0,
  "dealer_flow_alignment": 0.0,
  "dom_confirmation": 0.0,
  "trap_warning": 0.0,
  "final_state": "",
  "confidence": 0.0,
  "reason_codes": []
}
```

---

## 12. Final Decision States

The system can output:

1. HIGH CONFIDENCE LONG WATCH
2. HIGH CONFIDENCE SHORT WATCH
3. LONG WATCH
4. SHORT WATCH
5. BULL TRAP WARNING
6. BEAR TRAP WARNING
7. LIQUIDITY SWEEP LIKELY
8. ICEBERG ABSORPTION DETECTED
9. SPOOF / FAKE WALL DETECTED
10. GAMMA PIN / MEAN REVERSION
11. NEGATIVE GAMMA EXPANSION
12. MADLEVEL REVERSAL ZONE
13. MADLEVEL CONTINUATION ZONE
14. NO TRADE / CONFLICTING SIGNALS

Use “WATCH,” not automatic execution, unless a later execution system is separately approved.

---

## 13. Build Phases

### Phase 1 — Data and replay foundation

- Build raw event ingestion
- Store raw events
- Build book reconstruction
- Build replay engine
- Validate book integrity
- No LLM yet
- No trading logic yet

Acceptance:

- Can replay full NQ session
- Book reconstruction matches live snapshots
- No negative/crossed/stale book issues

### Phase 2 — Rule detectors

- Spoof detector
- Iceberg detector
- Absorption detector
- Liquidity vacuum detector
- Sweep detector
- Layering detector

Acceptance:

- Detector events are visible on replay
- Each detector provides reason codes
- False positives reviewed manually

### Phase 3 — Options/GEX/NQStats/MADLevels context

- Options connector
- GEX connector
- NQStats engine
- MADLevels engine
- Level registry
- Confluence scoring

Acceptance:

- Every active level has a grade
- Levels can be replayed and reviewed
- DOM events can be linked to levels

### Phase 4 — LLM expert layer

- Build snapshot builder
- Add dom_expert_prompt.md
- Add dom_expert_skills.md
- Add exemplar retrieval
- Add strict JSON parser
- Add outcome logger

Acceptance:

- LLM never outputs direct trade commands
- LLM always includes confirmation/invalidation criteria
- LLM confidence varies with evidence

### Phase 5 — Shadow mode

- Run live without trading
- Log every call
- Score 30s/60s outcomes
- Curate wrong calls into exemplars

Acceptance:

- Calibration improves over time
- High-confidence calls outperform medium/low
- No-signal discipline is strong

### Phase 6 — Classifier training

- Build label generation
- Train tabular models
- Train sequence model if justified
- Add meta-model

Acceptance:

- Out-of-sample performance beats baseline
- No lookahead leakage
- Model has stable calibration

### Phase 7 — Dashboard and production hardening

- Live dashboard
- Replay dashboard
- Health monitor
- Alert engine
- Risk/no-trade gates

Acceptance:

- System can run full session without crash
- Every decision is logged
- Every alert is explainable

---

## 14. Master Build Prompt

Use this with Claude Code or another coding agent.

```text
You are an elite Python quant engineer, futures DOM/MBO microstructure researcher, options dealer-flow analyst, and AI systems architect.

Your mission is to build a production-grade Cross-Market Liquidity AI Engine for NQ futures.

The engine combines:

1. Rithmic MBO / Level 2 DOM data
2. NQ futures trade tape
3. Massive.com options chain, trades, quotes, Greeks, IV, and open interest
4. Flash Alpha GEX / DEX / VEX / CHEX / zero gamma / call wall / put wall data
5. NQStats statistical session structure
6. MADLevels-style absorption/failure levels
7. LLM expert reasoning using prompt + taxonomy + few-shot exemplars + retrieval + outcome logging
8. Separate ML classifiers for probability prediction

This is not a basic indicator.
This is a cross-market liquidity intelligence engine.

Core philosophy:

Options/GEX tells us where dealer pressure, magnets, pins, and volatility zones exist.
NQStats tells us what the session statistically wants to do.
MADLevels tells us where absorption/failure has already proven itself.
MBO DOM tells us whether liquidity is real, fake, pulling, absorbing, spoofing, or breaking.
Tape confirms actual aggression.
The LLM explains the read.
The classifier quantifies probabilities.
Replay and outcome logging prove whether the system works.

Build the full modular Python project using the folder structure in this handoff.

Non-negotiables:

- Raw events must be saved before transformation.
- Book reconstruction must be validated before any AI logic.
- MBO order lifecycle must be tracked by order_id when available.
- MBP fallback must be clearly marked lower confidence.
- No repainting.
- No lookahead in live mode.
- Historical labels must be separate from live inference.
- Every detector output must include reason codes.
- Every LLM output must be strict JSON.
- Every LLM call must include confirmation and invalidation criteria.
- The LLM must not issue direct buy/sell/enter/exit commands.
- The classifier layer may be trained; the LLM reasoning layer is not fine-tuned initially.
- All predictions, alerts, features, snapshots, and outcomes must be logged.
- The system must support replay before live trading.
- The system must support shadow mode before production.

Build in phases:

Phase 1: raw data ingestion, storage, book reconstruction, replay.
Phase 2: rule-based detectors for spoofing, icebergs, absorption, sweeps, layering, liquidity vacuum.
Phase 3: options/GEX/NQStats/MADLevels context engines and confluence scoring.
Phase 4: LLM expert snapshot builder, prompt, exemplars, retrieval, strict JSON output, outcome logger.
Phase 5: live shadow mode and continuous exemplar curation.
Phase 6: classifier label generation and model training.
Phase 7: dashboard, health monitor, risk gates, production hardening.

Deliver actual runnable code, not vague pseudocode.

Deliver:

1. Complete folder structure
2. settings.yaml
3. Rithmic connector skeleton
4. Massive options connector skeleton
5. Flash Alpha connector skeleton
6. NQStats context engine
7. MADLevels-style absorption engine
8. MBO order-book reconstructor
9. Order lifecycle tracker
10. Book integrity validator
11. Spoof detector
12. Iceberg detector
13. Absorption detector
14. Sweep detector
15. Liquidity vacuum detector
16. Options flow engine
17. GEX/dealer pressure engine
18. Cross-asset mapper from QQQ/NDX/SPX levels to NQ
19. Level registry
20. Confluence scoring engine
21. LLM snapshot builder
22. Exemplar retriever
23. LLM router with strict JSON schema
24. Outcome logger and outcome critic
25. Exemplar curator
26. Label generator
27. XGBoost/LightGBM/CatBoost training pipeline
28. Optional sequence model scaffold
29. Synchronized replay engine
30. Live/shadow mode runner
31. DOM + GEX + AI dashboard
32. Unit tests
33. README with setup and run instructions

Final operating principle:

Do not trust visible liquidity until tested.
Do not trust options flow without DOM confirmation.
Do not trust DOM without context.
Do not trust the LLM without outcome logging.
Do not trust the model without replay validation.

Build the system so every read can be audited, replayed, scored, and improved.
```

---

## 15. Immediate Next Step

Do not start with the LLM.

Start with this exact implementation order:

1. Raw event schema
2. Rithmic connector skeleton
3. Parquet raw event store
4. MBO order book reconstructor
5. Replay engine
6. Spoof/iceberg/absorption detectors
7. Snapshot builder
8. Outcome logger
9. Then LLM expert

The first milestone is not “AI predicts NQ.”

The first milestone is:

“Can we reconstruct, replay, and explain DOM behavior accurately from raw MBO events?”

If yes, the AI layer has a real foundation.
