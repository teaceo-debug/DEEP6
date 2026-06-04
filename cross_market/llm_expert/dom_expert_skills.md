# MBO DOM Expert — Required Competencies & Few-Shot Scaffold

This document defines what the DOM expert must demonstrably know, how those competencies are tested, and provides the seed exemplar corpus that gets injected into the system prompt at inference time. It is paired with `dom_expert_prompt.md` (the operating constitution) but serves a different function: the prompt tells the model *how to reason*, this document tells the model *what good reasoning looks like* via worked examples.

---

## SECTION 1 — REQUIRED COMPETENCIES

The expert must be evaluated against each competency below. Each has a definition, a measurable pass criterion, and a failure mode it must avoid.

### 1.1 — MBO vs MBP discipline

**Knows:** That order-ID lifecycle (add → modify → cancel → trade) is the unit of evidence in MBO data, distinct from aggregated price-level totals (MBP). That refreshes, life durations, and per-order trade history are the substrate of intent inference.

**Pass criterion:** When asked about a level, the expert references specific order IDs and their lifecycle, not just level totals.

**Failure mode (must not exhibit):** Calling "iceberg" because a level total is large. Calling "spoof" because a level disappeared (the relevant question is *whether a specific order_id cancelled before any trade at its price during its life*).

### 1.2 — The intentions-vs-transactions distinction

**Knows:** Visible size is a *claim*, not evidence. The three signs of real liquidity (stays, absorbs, trades). The four signs of fake liquidity (sudden appearance, distance from price, cancellation as price approaches, one-sided imbalance with no opposing aggression).

**Pass criterion:** Every assessment of resting size is qualified by whether the size has been *tested* (price approached it, aggression went into it, fills printed at it).

**Failure mode:** Saying "strong support at X" or "strong resistance at Y" without qualification.

### 1.3 — Iceberg detection

**Knows:** Iceberg = small visible tip + large hidden parent. Detection requires (a) traded cumulative size at a level meaningfully exceeding the peak visible size (rule-of-thumb 3×), and (b) new ADD events at that price arriving shortly after fills (refresh behavior). Distinguishes iceberg from absorption (single hidden party vs. multiple visible parties or one large visible holder).

**Pass criterion:** Cites both `traded_cum/peak_visible` ratio and `refreshes` count when calling iceberg.

**Failure mode:** Calling iceberg on traded volume alone with no refresh evidence.

### 1.4 — Spoof detection

**Knows:** Spoof = visible order placed to influence positioning, with no fill intent, cancelled before price arrives. Detection requires (a) order added with significant size, (b) cancelled within a short life window (< ~5s), (c) no trade at that order's price during its life. Frequently coincides with opposite-side aggressive flow (spoof bid + aggressive selling = trap shorts, spoof ask + aggressive buying = trap longs).

**Pass criterion:** Cites order_id, life_ms, size, and absence of fills at the order's price during its life.

**Failure mode:** Calling spoof on a cancel that happened *after* trades printed at the price (that's normal repricing). Calling spoof on small orders (< 5× surrounding level avg) — most cancels are routine.

### 1.5 — Absorption recognition

**Knows:** Absorption = passive side eating aggressive flow without giving ground. Distinct from iceberg in that the size may be visible; the key signal is that aggressive volume goes *into* the level and the level *holds*.

**Pass criterion:** Cites trades/size/aggressor-direction over a specific window and notes that the level remained resting.

**Failure mode:** Calling absorption when the level cleared (it didn't absorb — it broke).

### 1.6 — Layering recognition

**Knows:** Layering = stacked size across 3+ sequential price levels on one side, manufacturing depth. Frequently dissolved as a block when price approaches. Common at round numbers and prior session H/L.

**Pass criterion:** Cites at least 3 contiguous levels with comparable oversized resting size on the same side.

**Failure mode:** Calling layering on a single large level (that's a wall, not layering).

### 1.7 — Sweep / liquidity-run recognition

**Knows:** Sweep = aggressive multi-level price extension, typically targeting an obvious stop zone, frequently followed by reversal. Evidence is rapid sequential trade prints in one direction taking visible asks/bids.

**Pass criterion:** Cites the multi-level trade sequence and identifies the targeted reference (prior H/L, round number, equal highs/lows).

**Failure mode:** Calling sweep on a single aggressive trade.

### 1.8 — Hidden liquidity recognition (non-iceberg)

**Knows:** Hidden = trades print at prices where no visible order ever existed. Different from iceberg (which has a visible tip).

**Pass criterion:** Cites a trade print with no matching ADD/CANCEL in the recent tape at that price.

**Failure mode:** Conflating hidden with iceberg refresh.

### 1.9 — Quote stuffing / pinging recognition

**Knows:** Stuffing = bursts of add/cancel without fills, typically HFT noise. Pinging = small (often 1-lot) probe orders testing for hidden size.

**Pass criterion:** Cites count of events in a short window or repeated small fills at a single price.

**Failure mode:** Treating these as directional signals (they're meta-signals about *other* participants probing).

### 1.10 — Calibrated uncertainty

**Knows:** Confidence calibration. Default to `medium` or lower. `high` requires both hard MBO evidence (lifecycle-level) *and* contextual fit. `low` is appropriate during macro windows, thin sessions, and ambiguous readings.

**Pass criterion:** Across a sample of 100 calls, the model's stated confidence correlates with subsequent confirmation rate (high-confidence calls confirm more often than low-confidence calls).

**Failure mode:** Always saying `high`. Always saying `medium`. Confidence that does not vary with evidence quality.

### 1.11 — Context modifiers

**Knows:** How to adjust priors for session/killzone, macro releases, GEX levels, ICT killzones. Knows that NY open inflates spoof rate and noise, lunch thins the book, macro windows make all reads unreliable for ±30s.

**Pass criterion:** When context is provided, the expert references it in either evidence or confidence calibration.

**Failure mode:** Ignoring provided context. Pretending it isn't there.

### 1.12 — Falsifiability discipline

**Knows:** Every assessment must include specific, testable confirmation and invalidation criteria — events that *would* happen within a defined time window if the read is right (confirmation) or wrong (invalidation).

**Pass criterion:** Confirmation and invalidation criteria are concrete (cite prices, sizes, time windows) and *opposed* (one is true iff the other is false).

**Failure mode:** Vague criteria ("if it holds" without defining what "hold" means). Criteria that are both consistent with the assessment being right and being wrong.

### 1.13 — No-signal discipline

**Knows:** The expert never recommends a trade. The trader_read describes intent, not action.

**Pass criterion:** No call contains "buy", "sell", "long", "short", "enter", "exit", or directional price targets.

**Failure mode:** Issuing a signal in any form.

---

## SECTION 2 — FEW-SHOT EXEMPLAR CORPUS

These are *seed* exemplars to embed in the system prompt at inference time. They cover the canonical patterns. Replace and expand with your own labeled corpus from replay data as you accumulate it.

Each exemplar has the snapshot the model would receive and the gold-standard assessment.

---

### EXEMPLAR 1 — Clean spoof, high confidence

**Snapshot (excerpt):**
```json
{
  "symbol": "NQ",
  "best_bid_ticks": 86200,
  "best_ask_ticks": 86201,
  "top_levels": {
    "bids": [
      {"price_ticks": 86200, "price": 21550.00, "size": 42, "n_orders": 18},
      {"price_ticks": 86199, "price": 21549.75, "size": 38, "n_orders": 14},
      {"price_ticks": 86196, "price": 21549.00, "size": 412, "n_orders": 1,
       "sample_order_ids": ["R8841290"]}
    ],
    "asks": [
      {"price_ticks": 86201, "price": 21550.25, "size": 35, "n_orders": 12},
      {"price_ticks": 86202, "price": 21550.50, "size": 31, "n_orders": 9}
    ]
  },
  "ofi_depth5": -0.18,
  "last_trade": {"price": 21550.00, "size": 1, "aggressor": 0},
  "iceberg_candidates": [],
  "spoof_flags_recent": [
    {"order_id": "R8841290", "side": 0, "price_ticks": 86196, "size": 412, "life_ms": 2840}
  ],
  "absorption_signals": []
}
```

**Gold assessment:**
```json
{
  "primary_pattern": "spoof",
  "evidence": [
    "Single order R8841290 sized 412 at 21549.00 (3 ticks below touch) — 10× the size of surrounding bid levels (~40 lots, 14-18 orders each)",
    "Order life 2840ms, cancelled before any trade at 21549.00",
    "Concurrent aggressive selling — last trade hit bid (aggressor=0) with negative OFI -0.18"
  ],
  "confidence": "high",
  "confirmation_criteria": "Within next 10s, if no resting order of comparable size (>200 lots) reappears at 21549.00 and another large bid spoof candidate appears 2-4 ticks below new touch, confirms a spoofing participant active on bid side.",
  "invalidation_criteria": "If a fresh 400+ lot bid appears at 21549.00 within 5s and stays resting through next aggressive sell flow, the original cancel was repricing, not spoof.",
  "trader_read": "Single-order spoof on bid pulled into seller aggression — book is leaning offered, the displayed bid wall was not real liquidity."
}
```

---

### EXEMPLAR 2 — Iceberg refreshing into aggressive buying, high confidence

**Snapshot (excerpt):**
```json
{
  "best_bid_ticks": 86220,
  "best_ask_ticks": 86221,
  "top_levels": {
    "asks": [
      {"price_ticks": 86221, "price": 21555.25, "size": 8, "n_orders": 3,
       "sample_order_ids": ["R9012044", "R9012511", "R9012589"]},
      {"price_ticks": 86222, "price": 21555.50, "size": 22, "n_orders": 7}
    ]
  },
  "ofi_depth5": 0.31,
  "last_trade": {"price": 21555.25, "size": 5, "aggressor": 1},
  "iceberg_candidates": [
    {"price_ticks": 86221, "traded_cum": 247, "peak_visible": 12, "ratio": 20.58, "refreshes": 9}
  ],
  "absorption_signals": [
    {"price_ticks": 86221, "size_traded": 247, "n_trades": 31, "buy_aggression": 247, "sell_aggression": 0, "side_resting": "ask"}
  ]
}
```

**Gold assessment:**
```json
{
  "primary_pattern": "iceberg",
  "evidence": [
    "Price 21555.25: traded_cum 247 vs peak_visible 12 (ratio 20.58×), refreshes 9 — classic iceberg signature",
    "31 trades at the level, all buyer-aggressive (247 buy / 0 sell), level still resting at 8 lots visible",
    "Strong buy-side OFI 0.31 but ask not breaking through 21555.25"
  ],
  "confidence": "high",
  "confirmation_criteria": "Continued refreshing visible size at 21555.25 with additional 100+ contracts traded against it in next 30s without level break confirms iceberg holding.",
  "invalidation_criteria": "If 21555.25 clears and price prints at 21555.50 or higher within next 15s with no further fills at 21555.25, iceberg exhausted or was being faded; reassess.",
  "trader_read": "Hidden seller defending 21555.25 — buyer aggression is real but absorbed; book is being held offered by a sized participant, not a passive wall."
}
```

---

### EXEMPLAR 3 — Layering on bid, medium confidence

**Snapshot (excerpt):**
```json
{
  "best_bid_ticks": 86180,
  "best_ask_ticks": 86181,
  "top_levels": {
    "bids": [
      {"price_ticks": 86180, "price": 21545.00, "size": 32, "n_orders": 11},
      {"price_ticks": 86179, "price": 21544.75, "size": 28, "n_orders": 9},
      {"price_ticks": 86178, "price": 21544.50, "size": 245, "n_orders": 3},
      {"price_ticks": 86177, "price": 21544.25, "size": 280, "n_orders": 4},
      {"price_ticks": 86176, "price": 21544.00, "size": 310, "n_orders": 3}
    ],
    "asks": [
      {"price_ticks": 86181, "price": 21545.25, "size": 30, "n_orders": 10},
      {"price_ticks": 86182, "price": 21545.50, "size": 27, "n_orders": 8},
      {"price_ticks": 86183, "price": 21545.75, "size": 24, "n_orders": 7}
    ]
  },
  "ofi_depth5": 0.42,
  "spoof_flags_recent": [],
  "absorption_signals": [],
  "context": {"session": "asia", "near_level": "prior_NY_low_21544"}
}
```

**Gold assessment:**
```json
{
  "primary_pattern": "layering",
  "evidence": [
    "Three contiguous bid levels (86178, 86177, 86176) sized 245/280/310 — 7-10× the comparable ask levels (30/27/24) at equal depth",
    "Concentrated in few orders (3, 4, 3) suggesting same or coordinated participants",
    "Positioned at/below prior NY session low 21544 — classic stop-hunt visibility zone",
    "Asia session — known for layering at NY reference levels"
  ],
  "confidence": "medium",
  "confirmation_criteria": "If price drifts toward 21544.50 and the three-level stack cancels as a block before fills, layering confirmed.",
  "invalidation_criteria": "If price trades into 21544.50 and the stack absorbs the aggression without dissolving (≥100 lots trade with level intact), it was real defensive bid.",
  "trader_read": "Stacked bid below prior NY low looks manufactured — may be designed to trap buyers expecting a defended low; not yet tested, treat the depth as unconfirmed."
}
```

---

### EXEMPLAR 4 — Absorption, high confidence

**Snapshot (excerpt):**
```json
{
  "best_bid_ticks": 86250,
  "best_ask_ticks": 86251,
  "top_levels": {
    "bids": [
      {"price_ticks": 86250, "price": 21562.50, "size": 88, "n_orders": 24}
    ]
  },
  "ofi_depth5": -0.39,
  "last_trade": {"price": 21562.50, "size": 12, "aggressor": 0},
  "iceberg_candidates": [],
  "absorption_signals": [
    {"price_ticks": 86250, "size_traded": 184, "n_trades": 22, "buy_aggression": 0, "sell_aggression": 184, "side_resting": "bid"}
  ]
}
```

**Gold assessment:**
```json
{
  "primary_pattern": "absorption",
  "evidence": [
    "184 contracts sold aggressively into 21562.50 across 22 trades in the recent window, all seller-aggressive (sell_aggression 184 / buy_aggression 0)",
    "Level still resting at 88 lots across 24 orders — multi-participant defense, not single hidden order",
    "Strong negative OFI -0.39 but bid not breaking"
  ],
  "confidence": "high",
  "confirmation_criteria": "If next 100+ contracts of seller aggression continue to hit 21562.50 without the level breaking, absorption is sustained.",
  "invalidation_criteria": "If 21562.50 clears within next 10s and bid drops to 21562.25 or lower with no defending refresh, absorption exhausted.",
  "trader_read": "Bid is being defended at 21562.50 by multiple participants against sustained seller aggression — passive side has size and conviction at this level."
}
```

---

### EXEMPLAR 5 — No high-confidence pattern (calibration test)

**Snapshot (excerpt):**
```json
{
  "best_bid_ticks": 86210,
  "best_ask_ticks": 86211,
  "top_levels": {
    "bids": [
      {"price_ticks": 86210, "price": 21552.50, "size": 41, "n_orders": 14},
      {"price_ticks": 86209, "price": 21552.25, "size": 38, "n_orders": 12}
    ],
    "asks": [
      {"price_ticks": 86211, "price": 21552.75, "size": 44, "n_orders": 15},
      {"price_ticks": 86212, "price": 21553.00, "size": 39, "n_orders": 13}
    ]
  },
  "ofi_depth5": -0.04,
  "last_trade": {"price": 21552.75, "size": 2, "aggressor": 1},
  "iceberg_candidates": [],
  "spoof_flags_recent": [],
  "absorption_signals": []
}
```

**Gold assessment:**
```json
{
  "primary_pattern": "none",
  "evidence": [
    "Balanced book: bid depth 79 vs ask depth 83 in top 2 levels",
    "OFI -0.04 essentially neutral",
    "No iceberg candidates, no spoof flags, no absorption signals from detectors",
    "Trade flow is small and two-way"
  ],
  "confidence": "low",
  "confirmation_criteria": "N/A — null call",
  "invalidation_criteria": "If within next 10s OFI moves beyond ±0.20 with directional aggression or any detector flags fire, reassess.",
  "trader_read": "Quiet, balanced book with no edge visible — nothing to read into right now."
}
```

---

### EXEMPLAR 6 — Macro window, forced low confidence

**Snapshot (excerpt):**
```json
{
  "best_bid_ticks": 86195,
  "best_ask_ticks": 86198,
  "spread_ticks": 3,
  "top_levels": {
    "bids": [
      {"price_ticks": 86195, "price": 21548.75, "size": 8, "n_orders": 4},
      {"price_ticks": 86191, "price": 21547.75, "size": 14, "n_orders": 5}
    ],
    "asks": [
      {"price_ticks": 86198, "price": 21549.50, "size": 6, "n_orders": 3},
      {"price_ticks": 86204, "price": 21551.00, "size": 11, "n_orders": 4}
    ]
  },
  "ofi_depth5": 0.08,
  "context": {"macro_release": "CPI", "seconds_to_release": 12}
}
```

**Gold assessment:**
```json
{
  "primary_pattern": "none",
  "evidence": [
    "12 seconds to CPI release — book is thin and gapped (3-tick spread, only 8 lots at best bid)",
    "All resting size is unreliable; participants pull liquidity into macro"
  ],
  "confidence": "low",
  "confirmation_criteria": "Reassess only ≥30s after release print.",
  "invalidation_criteria": "N/A during macro window.",
  "trader_read": "Pre-CPI thin book — no liquidity assessment is meaningful in this window."
}
```

---

## SECTION 3 — EVALUATION HARNESS

The expert should be evaluated on a held-out set of labeled snapshots before live deployment. Suggested protocol:

1. **Seed set:** Hand-label 100 snapshots from replay tape — 15-20 per primary pattern + a balanced "none" class. You are the labeler; you are the domain expert.
2. **Calibration check:** Run the expert across the seed set. Compute:
   - **Pattern accuracy** per class (precision, recall, F1)
   - **Confidence calibration** — high-confidence calls should confirm >70% on 30s-forward replay; medium 50-70%; low free to be wrong
   - **Falsifiability quality** — confirmation/invalidation criteria are concrete and testable
3. **Outcome-replay validation:** For each call on live shadow tape, the engine replays 30-60s forward and checks whether confirmation or invalidation conditions hit. Build a rolling confirmation rate per pattern.
4. **Failure-mode review:** Periodically sample wrong calls. Most failures will cluster — that cluster becomes the next exemplar batch.

The expert is not "trained" in one pass. It is curated continuously. The outcome database is the asset.
