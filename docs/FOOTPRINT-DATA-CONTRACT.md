# DEEP6 Footprint Data Contract

This document defines the machine-readable contract for the **Footprint Specialist Program**.

It standardizes how footprint data moves through the system across:

- live ingestion
- replay
- training dataset generation
- label generation
- model inference
- NT8 advisory overlays
- dashboard/review tooling

This contract is designed to align with:

- `docs/FOOTPRINT-SPECIALIST-PROGRAM.md`
- `docs/FOOTPRINT-PATTERN-ATLAS.md`
- `deep6/state/footprint.py`
- current replay/scored-bar artifacts already present in the repo

If this document conflicts with `docs/CURRENT-STATE.md`, treat `CURRENT-STATE.md` as authoritative.

---

## 1. Goals

This contract exists to solve five problems:

1. define a canonical footprint payload independent of UI
2. preserve decision-time truth for replay and training
3. separate raw events from derived state and labels
4. make Python truth and NT8 display comparable
5. prevent silent schema drift across live, replay, and training paths

---

## 2. Design Principles

### 2.1 Raw truth first

The contract preserves source order:

- raw event stream
- reconstructed footprint state
- deterministic engine emissions
- visual sync artifacts
- outcome labels

No downstream representation is allowed to overwrite upstream truth.

### 2.2 Decision-time discipline

Every derived record must be reconstructible from information known at that moment.

This means:

- no future-known fields inside decision records
- no finalized-bar fields for intrabar decisions unless explicitly versioned as post-close
- no replay-only labels leaking into live inference payloads

### 2.3 Version everything

Every persisted artifact must carry:

- `schemaVersion`
- `producer`
- `producedAtUtc`
- `sourceSessionId`

### 2.4 Stable identity across systems

Every event, bar, candidate, and label must be linkable by stable IDs.

---

## 3. Canonical Layers

The specialist program defines five canonical layers.
This contract gives each layer a concrete shape.

### T0 — Raw Event Records
### T1 — Footprint State Records
### T2 — Deterministic Signal Records
### T3 — Visual Sync Records
### T4 — Outcome / Action Label Records

Each layer may be stored independently or together in NDJSON streams, but layer boundaries must remain explicit.

---

## 4. Global Field Rules

### 4.1 Required timestamp fields

Every persisted record must include at least one UTC timestamp field.

Preferred fields:

- `tsUtc` — ISO-8601 UTC timestamp string
- `tsEpochMs` — Unix epoch milliseconds

If nanosecond or exchange-native timestamps exist, preserve them separately:

- `tsExchangeNs`

### 4.2 Instrument identity

Every market-data-bearing record must include:

- `instrument`
- `exchange`
- `tickSize`

Optional but recommended:

- `contract`
- `sessionDate`

### 4.3 Record identity

Every persisted record should include:

- `recordId`
- `sourceSessionId`
- `type`

Examples of `type`:

- `trade`
- `depth`
- `footprint_bar`
- `signal_event`
- `candidate_event`
- `scored_bar`
- `visual_sync`
- `outcome_label`

---

## 5. T0 — Raw Event Contract

This is the canonical event layer.
It should be append-only and replayable in original order.

### 5.1 Trade event

Minimum shape:

```json
{
  "schemaVersion": "1.0",
  "type": "trade",
  "recordId": "evt_...",
  "sourceSessionId": "ses_...",
  "tsUtc": "2026-05-12T13:35:24.123Z",
  "tsEpochMs": 1778592924123,
  "instrument": "NQ",
  "exchange": "CME",
  "contract": "NQM2026",
  "tickSize": 0.25,
  "price": 19492.25,
  "size": 8,
  "aggressor": 1,
  "sequence": 1048821
}
```

Rules:

- `aggressor`: `1=BUY`, `2=SELL`, `0=UNKNOWN` only if source truly cannot classify
- preserve source ordering field when available (`sequence`, `exchangeSeq`, etc.)

### 5.2 Depth event

Minimum shape:

```json
{
  "schemaVersion": "1.0",
  "type": "depth",
  "recordId": "evt_...",
  "sourceSessionId": "ses_...",
  "tsUtc": "2026-05-12T13:35:24.140Z",
  "instrument": "NQ",
  "exchange": "CME",
  "tickSize": 0.25,
  "side": "bid",
  "price": 19492.00,
  "size": 37,
  "level": 1,
  "action": "update"
}
```

Allowed `action` values:

- `add`
- `update`
- `remove`
- `snapshot`

### 5.3 Session marker event

Use explicit marker records rather than inferring all boundaries later.

Minimum shape:

```json
{
  "schemaVersion": "1.0",
  "type": "session_marker",
  "recordId": "evt_...",
  "sourceSessionId": "ses_...",
  "tsUtc": "2026-05-12T13:30:00.000Z",
  "instrument": "NQ",
  "marker": "rth_open"
}
```

Allowed `marker` examples:

- `rth_open`
- `rth_close`
- `session_reset`
- `halt`
- `news_window_open`
- `news_window_close`

---

## 6. T1 — Footprint State Contract

This is the canonical learning and replay representation.

It is derived from T0 and maps closely to `deep6/state/footprint.py`.

### 6.1 Footprint level record

Canonical per-level shape:

```json
{
  "price": 19492.25,
  "tick": 77969,
  "bidVol": 247,
  "askVol": 89,
  "totalVol": 336,
  "delta": -158
}
```

Rules:

- `tick` is the integer price key from `price_to_tick(price)`
- `delta = askVol - bidVol`
- `totalVol = askVol + bidVol`

### 6.2 Footprint bar record

Canonical minimum shape:

```json
{
  "schemaVersion": "1.0",
  "type": "footprint_bar",
  "recordId": "bar_...",
  "sourceSessionId": "ses_...",
  "tsUtc": "2026-05-12T13:36:00.000Z",
  "instrument": "NQ",
  "exchange": "CME",
  "tickSize": 0.25,
  "barId": "NQ-2026-05-12-0936-1m",
  "timeframe": "1m",
  "barIndex": 42,
  "barsSinceOpen": 6,
  "open": 19490.50,
  "high": 19493.00,
  "low": 19490.25,
  "close": 19492.75,
  "totalVol": 1843,
  "barDelta": 214,
  "cvd": 881,
  "pocPrice": 19492.25,
  "barRange": 2.75,
  "runningDelta": 214,
  "maxDelta": 331,
  "minDelta": -52,
  "deltaQuality": 1.03,
  "levels": []
}
```

Required semantics:

- `barDelta`, `cvd`, `pocPrice`, `barRange` are post-derivation fields
- `runningDelta`, `maxDelta`, `minDelta` preserve intrabar delta behavior
- `deltaQuality` should map to `FootprintBar.delta_quality_scalar()`

### 6.3 Footprint bar state mode

Every footprint bar record must declare whether it is:

- `in_progress`
- `closed`

Field:

- `state`

Rule:

- intrabar inference may consume `in_progress`
- replay close-based scoring may consume `closed`
- these must never be mixed silently

### 6.4 Optional context fields on footprint bars

Recommended additions:

- `vah`
- `val`
- `sessionHigh`
- `sessionLow`
- `hvnLevels`
- `lvnLevels`
- `regimeTag`

These are allowed only if they are decision-time correct for that bar.

---

## 7. T2 — Deterministic Signal Contract

This layer carries expert-engine outputs.

### 7.1 Signal event record

Canonical minimum shape:

```json
{
  "schemaVersion": "1.0",
  "type": "signal_event",
  "recordId": "sig_...",
  "sourceSessionId": "ses_...",
  "tsUtc": "2026-05-12T13:36:00.000Z",
  "instrument": "NQ",
  "barId": "NQ-2026-05-12-0936-1m",
  "barIndex": 42,
  "family": "absorption",
  "subtype": "ABS-01_CLASSIC",
  "direction": 1,
  "strength": 0.82,
  "price": 19490.25,
  "detail": "CLASSIC BULL ABSORB: wick=41.2% delta_ratio=0.08"
}
```

Required fields:

- `family`
- `subtype`
- `direction`
- `strength`
- `price`
- `detail`

### 7.2 Allowed families

- `absorption`
- `exhaustion`
- `delta`
- `imbalance`
- `profile_context`
- `composite`

### 7.3 Allowed subtype naming convention

Subtype names must map directly to the atlas and code.

Examples:

- `ABS-01_CLASSIC`
- `ABS-02_PASSIVE`
- `EXH-01_ZERO_PRINT`
- `DELT-04_DIVERGENCE`
- `IMB-03_STACKED_T2`
- `IMB-05_INVERSE_TRAP`

### 7.4 Candidate event record

This is the contract for rule-generated opportunities that a learned model later ranks.

Canonical minimum shape:

```json
{
  "schemaVersion": "1.0",
  "type": "candidate_event",
  "recordId": "cand_...",
  "sourceSessionId": "ses_...",
  "tsUtc": "2026-05-12T13:36:00.000Z",
  "instrument": "NQ",
  "barId": "NQ-2026-05-12-0936-1m",
  "candidateId": "cand_absorb_rev_42",
  "direction": 1,
  "familySet": ["absorption", "delta", "imbalance"],
  "signalIds": ["sig_a", "sig_b", "sig_c"],
  "context": {
    "atStructure": true,
    "atPoc": false,
    "sessionPhase": "open"
  }
}
```

---

## 8. T3 — Visual Sync Contract

This layer ties structured truth to what the operator saw.

### 8.1 Visual sync record

Canonical minimum shape:

```json
{
  "schemaVersion": "1.0",
  "type": "visual_sync",
  "recordId": "vis_...",
  "sourceSessionId": "ses_...",
  "tsUtc": "2026-05-12T13:36:00.050Z",
  "instrument": "NQ",
  "barId": "NQ-2026-05-12-0936-1m",
  "imagePath": "evidence/session-01/frame-0042.png",
  "videoPath": "evidence/session-01/replay.mp4",
  "frameIndex": 42,
  "viewport": {
    "chartType": "footprint",
    "zoom": 1.35,
    "visibleBars": 68
  },
  "overlayStateId": "ovr_..."
}
```

Rules:

- this layer is optional for pure live inference
- it is mandatory for synchronized human review datasets
- image/video references must not replace T0/T1 as ground truth

---

## 9. T4 — Outcome and Label Contract

This layer defines what happened after the decision point.

### 9.1 Outcome label record

Canonical minimum shape:

```json
{
  "schemaVersion": "1.0",
  "type": "outcome_label",
  "recordId": "lbl_...",
  "sourceSessionId": "ses_...",
  "tsUtc": "2026-05-12T13:36:00.000Z",
  "instrument": "NQ",
  "candidateId": "cand_absorb_rev_42",
  "actionLabel": "candidate",
  "resolvedAs": "invalidated",
  "forwardExcursionTicks": 6.0,
  "adverseExcursionTicks": 10.0,
  "timeToResolutionSec": 134,
  "expiryReason": "session_close",
  "slippageTicks": 1.0,
  "fillAssumption": "best_effort_limit"
}
```

### 9.2 Allowed action labels

Must match the atlas/program:

- `no_trade`
- `watch`
- `candidate`
- `executable`
- `invalidated`
- `expired`

### 9.3 Human-review label record

For disagreement and curation workflows:

```json
{
  "schemaVersion": "1.0",
  "type": "human_review",
  "recordId": "rev_...",
  "sourceSessionId": "ses_...",
  "candidateId": "cand_absorb_rev_42",
  "reviewer": "expert_01",
  "reviewDecision": "valid_but_not_actionable",
  "notes": "absorption real, but free space and no structure anchor"
}
```

---

## 10. Replay Artifact Contract

The repo already contains scored-bar NDJSON concepts.
This contract standardizes them rather than replacing them.

### 10.1 Scored bar record

Minimum shape, aligned with existing replay harness conventions:

```json
{
  "schemaVersion": "1.0",
  "type": "scored_bar",
  "sourceSessionId": "ses_...",
  "barIdx": 42,
  "barsSinceOpen": 6,
  "barDelta": 214,
  "barClose": 19492.75,
  "zoneScore": 0.83,
  "zoneDistTicks": 2.0,
  "atr": 11.25,
  "signals": [
    {
      "signalId": "ABS-01_CLASSIC",
      "direction": 1,
      "strength": 0.82,
      "price": 19490.25,
      "detail": "CLASSIC BULL ABSORB"
    }
  ]
}
```

### 10.2 Event ordering rule

Replay streams must preserve original order.

Preferred sort precedence:

1. `tsExchangeNs`
2. `tsEpochMs`
3. source `sequence`
4. input line order as final fallback

---

## 11. Live Advisory Signal Schema

This is the compact schema the live specialist should emit to NT8 overlays or operator surfaces.

### 11.1 Advisory signal record

```json
{
  "schemaVersion": "1.0",
  "type": "advisory_signal",
  "recordId": "adv_...",
  "sourceSessionId": "ses_...",
  "tsUtc": "2026-05-12T13:36:00.000Z",
  "instrument": "NQ",
  "barId": "NQ-2026-05-12-0936-1m",
  "family": "composite",
  "subtype": "ABSORPTION_REVERSAL",
  "direction": 1,
  "confidence": 0.87,
  "actionLabel": "candidate",
  "expectedHorizonSec": 180,
  "invalidationCondition": "loss_of_low + confirming sell continuation",
  "explanation": "lower-wick absorption plus negative-delta effort/result at structure"
}
```

Required fields:

- `family`
- `subtype`
- `direction`
- `confidence`
- `actionLabel`
- `expectedHorizonSec`
- `invalidationCondition`
- `explanation`

---

## 12. Enum Guidance

Use stable enums for all fields that drive training or replay joins.

### 12.1 Example enums

- `aggressor`: `0|1|2`
- `barState`: `in_progress|closed`
- `actionLabel`: `no_trade|watch|candidate|executable|invalidated|expired`
- `sessionPhase`: `open|midday|close|post_news|overnight`
- `regimeTag`: `balance|trend|volatile|compression|expansion`

Do not use free-form strings for core modeling categories when a bounded enum exists.

---

## 13. Validation Rules for the Contract

Every contract implementation should validate:

1. required fields exist per record type
2. numeric fields are finite
3. `tickSize > 0`
4. `totalVol = sum(level.askVol + level.bidVol)` when levels are present
5. `barDelta = sum(level.askVol - level.bidVol)` when levels are present
6. `pocPrice` corresponds to the max-volume level when levels are present
7. `direction` is one of `-1, 0, +1`
8. timestamps are monotonic within replay ordering rules

---

## 14. Forbidden Contract Drift

Do not:

1. rename atlas subtype values casually
2. mix intrabar and post-close records without explicit `state`
3. remove raw event references once derived records exist
4. serialize screenshot-only records as if they were footprint truth
5. let NT8-only fields become mandatory for Python replay datasets

---

## 15. Immediate Follow-On Artifact

Now that the vocabulary and machine-readable contract exist, the next document should define how labels are assigned:

- `docs/FOOTPRINT-LABELING-SPEC.md`

That document should specify exactly how structural, context, action, and review labels are created without leakage.
