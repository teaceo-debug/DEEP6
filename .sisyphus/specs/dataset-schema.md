# Dataset Schema + Capture Protocol: Standard Deviation Anchor AI

> Foundation spec for T9 (Pine capture bridge), T10 (HERMES training pipeline), T14 (screenshot dataset).
> This document is the single source of truth for record structure, capture timing, and leakage prevention.

---

## 1. Anchor Record Schema

Each anchor event produces exactly one record. Records are append-only JSONL.

### 1.1 Decision-Time Fields (immutable after capture)

| Field | Type | Description |
|-------|------|-------------|
| `anchor_id` | `string (uuid v4)` | Unique identifier for this anchor instance |
| `captured_at` | `string (ISO 8601)` | Timestamp when the capture was triggered — decision time, NOT outcome time |
| `symbol` | `string` | Instrument symbol (e.g. `"NQ1!"`, `"NQM2026"`) |
| `timeframe_primary` | `string` | Primary chart timeframe (e.g. `"1"` for 1m) |
| `timeframe_context` | `string \| null` | Higher timeframe providing context (e.g. `"5"`, `"15"`, or `null` if none) |
| `direction` | `string enum` | `"bullish"` or `"bearish"` |
| `anchor_low_price` | `float` | Low wick price of the anchor leg |
| `anchor_high_price` | `float` | High wick price of the anchor leg |
| `anchor_low_bar_time` | `int (unix seconds)` | Bar timestamp of the anchor low |
| `anchor_high_bar_time` | `int (unix seconds)` | Bar timestamp of the anchor high |
| `range` | `float` | `anchor_high_price - anchor_low_price` (always positive) |
| `level_minus2` | `float` | -2 standard deviation projection from anchor |
| `level_minus2_5` | `float` | -2.5 standard deviation projection from anchor |
| `level_minus4` | `float` | -4 standard deviation projection from anchor |
| `pine_confidence_score` | `int (0-100)` | Pine Script's deterministic confidence assessment |
| `pine_state` | `string enum` | Lifecycle state at capture: `"candidate"`, `"confirmed"`, `"active"`, `"invalidated"`, `"superseded"` |
| `screenshot_path` | `string` | Relative path from repo root to screenshot image file |
| `chart_metadata` | `object` | Chart presentation state at capture time (see 1.3) |

### 1.2 HERMES Validation Fields (written by sidecar, immutable after verdict)

| Field | Type | Description |
|-------|------|-------------|
| `hermes_verdict` | `string enum \| null` | `"approve"`, `"veto"`, `"abstain"`, or `null` (not yet evaluated) |
| `hermes_reasons` | `string[]` | Array of human-readable reason strings for the verdict |
| `hermes_version` | `string \| null` | Version identifier of the HERMES model/skill that issued the verdict |

### 1.3 Human Override Fields

| Field | Type | Description |
|-------|------|-------------|
| `human_override` | `bool` | Whether a human overrode the HERMES verdict |
| `human_override_reason` | `string \| null` | Free-text reason for override, required if `human_override` is `true` |

### 1.4 Outcome Fields (written ONLY after resolution)

| Field | Type | Description |
|-------|------|-------------|
| `outcome_label` | `string enum \| null` | `null` until resolved. One of: `"reached_minus2"`, `"reached_minus2_5"`, `"reached_minus4"`, `"invalidated_before_target"`, `"pending"` |
| `outcome_resolved_at` | `string (ISO 8601) \| null` | Timestamp when outcome was determined. `null` until resolved |

### 1.5 Chart Metadata Object

The `chart_metadata` field captures chart presentation state to enable reproducible screenshot context:

```json
{
  "zoom_level": "number — bars visible on screen",
  "visible_bar_range_start": "int (unix seconds) — leftmost visible bar",
  "visible_bar_range_end": "int (unix seconds) — rightmost visible bar",
  "candle_style": "string — e.g. 'candles', 'heikin_ashi', 'hollow_candles'",
  "theme": "string — 'dark' or 'light'",
  "chart_width_px": "int — screenshot width in pixels",
  "chart_height_px": "int — screenshot height in pixels"
}
```

---

## 2. Capture Protocol

### 2.1 Trigger Condition

Capture is triggered **at bar close** when Pine Script emits a state change for a candidate anchor. Specifically:

1. Pine's deterministic engine evaluates the closed bar.
2. If a new candidate is identified OR an existing candidate transitions state (`candidate` -> `confirmed`, `confirmed` -> `active`, etc.), Pine emits a capture signal.
3. The capture bridge (external process) receives the signal and executes capture atomically.

**No intrabar captures.** All captures occur on confirmed (closed) bars only.

### 2.2 Capture Sequence (atomic)

When triggered, the following must happen as a single atomic operation:

```
1. Pine emits structured state via alert/webhook/label payload
2. Capture bridge receives the payload
3. Bridge captures screenshot via TradingView MCP (capture_screenshot)
4. Bridge reads chart metadata via TradingView MCP (chart_get_visible_range, chart_get_state)
5. Bridge constructs the full record (all decision-time fields)
6. Bridge writes screenshot to disk at the designated path
7. Bridge appends the JSONL record to the day's record file
8. Steps 6-7 are atomic: if either fails, both are rolled back (no orphan screenshots, no records without screenshots)
```

### 2.3 What Gets Captured

Each capture produces exactly two artifacts:

1. **Screenshot** (PNG): Full chart region showing the anchor, its context, and deviation levels. Taken via `capture_screenshot(region="chart")`.
2. **Structured record** (JSONL line): All decision-time fields from Section 1.1 plus null-initialized outcome fields from Section 1.4.

### 2.4 State Transitions That Trigger Capture

| Transition | Captures? | Notes |
|-----------|-----------|-------|
| New candidate detected | Yes | Initial record creation |
| `candidate` -> `confirmed` | Yes | New record with updated `pine_state` |
| `confirmed` -> `active` | Yes | New record with updated `pine_state` |
| `active` -> `invalidated` | Yes | New record; outcome fields still null (invalidation != outcome) |
| `active` -> `superseded` | Yes | New record; prior anchor's lifecycle ends |
| Any state with no change | No | Do not capture on every bar — only on transitions |

Each state transition produces a **new record** with its own `anchor_id`, `captured_at`, and `screenshot_path`. The lifecycle of a single anchor concept may span multiple records, linked by matching `anchor_low_bar_time` + `anchor_high_bar_time` + `direction`.

---

## 3. Leakage-Prevention Rules

These rules are **non-negotiable**. Violations corrupt the training dataset.

### 3.1 Temporal Isolation

| Rule | Enforcement |
|------|-------------|
| **R1: Decision-time fields are immutable after capture** | Once a record is written, fields in Section 1.1 are never modified. A new state produces a new record. |
| **R2: `outcome_label` is null at capture time** | The capture bridge MUST write `outcome_label: null` and `outcome_resolved_at: null`. No exceptions. |
| **R3: Outcome is written only after the outcome bar closes** | The outcome resolver runs separately. It reads records with `outcome_label: null`, checks if price has reached any target level, and writes the outcome ONLY after the bar that reaches (or invalidates) the level has closed. |
| **R4: Screenshot is taken at decision time** | The screenshot captures what was visible when the anchor was identified. Screenshots are NEVER taken retroactively after the outcome is known. |
| **R5: No future data in structured fields** | All prices, times, and scores in a record reflect information available at `captured_at`. No forward-looking fields. |

### 3.2 Immutability Contract

```
IMMUTABLE after write:
  - anchor_id
  - captured_at
  - symbol, timeframe_primary, timeframe_context
  - direction
  - anchor_low_price, anchor_high_price
  - anchor_low_bar_time, anchor_high_bar_time
  - range
  - level_minus2, level_minus2_5, level_minus4
  - pine_confidence_score, pine_state
  - screenshot_path
  - chart_metadata

WRITE-ONCE (null -> value, never overwritten):
  - hermes_verdict, hermes_reasons, hermes_version
  - outcome_label, outcome_resolved_at

MUTABLE (can be set after capture):
  - human_override, human_override_reason
```

### 3.3 Outcome Resolution Protocol

The outcome resolver is a **separate process** from the capture bridge:

1. Periodically scan records where `outcome_label` is `null`.
2. For each unresolved record, check if price action since `captured_at` has:
   - Reached `level_minus2` -> label `"reached_minus2"`
   - Reached `level_minus2_5` -> label `"reached_minus2_5"`
   - Reached `level_minus4` -> label `"reached_minus4"`
   - Anchor was invalidated before any target -> label `"invalidated_before_target"`
3. The **first target reached** determines the label (hierarchical: -4 > -2.5 > -2).
4. Write `outcome_label` and `outcome_resolved_at` ONLY after the bar that triggers the outcome has **closed**.
5. If still in play, leave as `null` (not `"pending"` — `"pending"` is reserved for display purposes only and is never written to the record file).

---

## 4. Storage Layout

### 4.1 Directory Structure

```
data/sd_anchor/
  screenshots/
    {YYYY-MM-DD}/
      {anchor_id}.png                    # One PNG per capture event
  records/
    {YYYY-MM-DD}.jsonl                   # All records captured on that date, one JSON per line
```

### 4.2 Path Conventions

- **Screenshots**: `data/sd_anchor/screenshots/2026-05-21/550e8400-e29b-41d4-a716-446655440000.png`
- **Records**: `data/sd_anchor/records/2026-05-21.jsonl`
- **Date partitioning**: Based on `captured_at` date (UTC).
- **Screenshot path in record**: Always stored as a relative path from repo root: `"data/sd_anchor/screenshots/2026-05-21/550e8400-e29b-41d4-a716-446655440000.png"`

### 4.3 Record File Format

JSONL (JSON Lines): one complete JSON object per line, newline-delimited.

```json
{"anchor_id":"550e8400-e29b-41d4-a716-446655440000","captured_at":"2026-05-21T14:30:00Z","symbol":"NQ1!","timeframe_primary":"1","timeframe_context":"5","direction":"bullish","anchor_low_price":21450.25,"anchor_high_price":21478.50,"anchor_low_bar_time":1747837200,"anchor_high_bar_time":1747837560,"range":28.25,"level_minus2":21394.25,"level_minus2_5":21380.00,"level_minus4":21337.50,"pine_confidence_score":82,"pine_state":"confirmed","screenshot_path":"data/sd_anchor/screenshots/2026-05-21/550e8400-e29b-41d4-a716-446655440000.png","chart_metadata":{"zoom_level":150,"visible_bar_range_start":1747833600,"visible_bar_range_end":1747838400,"candle_style":"candles","theme":"dark","chart_width_px":1920,"chart_height_px":1080},"hermes_verdict":null,"hermes_reasons":[],"hermes_version":null,"human_override":false,"human_override_reason":null,"outcome_label":null,"outcome_resolved_at":null}
```

### 4.4 Retention and Backup

- Records are append-only. Never delete or modify existing lines.
- Screenshots are never overwritten. Each `anchor_id` maps to exactly one file.
- Daily record files can be concatenated for bulk analysis: `cat records/*.jsonl > all_records.jsonl`

---

## 5. Validation Rules

### 5.1 Record Integrity Checks

Before writing any record, the capture bridge MUST validate:

| Check | Rule |
|-------|------|
| `anchor_id` | Valid UUID v4 |
| `captured_at` | Valid ISO 8601, not in the future |
| `direction` | Exactly `"bullish"` or `"bearish"` |
| `anchor_high_price > anchor_low_price` | Always true |
| `range == anchor_high_price - anchor_low_price` | Computed, not received |
| `pine_state` | One of: `"candidate"`, `"confirmed"`, `"active"`, `"invalidated"`, `"superseded"` |
| `pine_confidence_score` | Integer, 0-100 inclusive |
| `screenshot_path` | File exists on disk at write time |
| `outcome_label` | Must be `null` at capture time |
| `outcome_resolved_at` | Must be `null` at capture time |
| `level_minus2`, `level_minus2_5`, `level_minus4` | All non-null floats, ordered correctly for direction |

### 5.2 Level Ordering Validation

For **bullish** anchors (target is below):
```
level_minus4 < level_minus2_5 < level_minus2 < anchor_low_price
```

For **bearish** anchors (target is above):
```
anchor_high_price < level_minus2 < level_minus2_5 < level_minus4
```

---

## 6. Schema Version

**Version**: `1.0.0`

Changes to field names, types, or semantics require a version bump and migration plan. The `schema_version` field is intentionally omitted from individual records to avoid per-record overhead — version is tracked at the spec level.
