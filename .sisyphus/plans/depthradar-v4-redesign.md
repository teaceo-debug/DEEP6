# DepthRadar V4 Redesign — Causality Audit + New Architecture

## Phase 1: Causality Audit

### The Core Problem

The offline labeler (`labeler.py`) tracks walls from **birth to death**, then labels them
using the **complete lifecycle**. Features extracted from these completed walls leak the
answer into the training data. A classifier trained on this data learns to read the label
from the features, not to predict it.

In live trading, you see a wall **partway through its life** and must classify it **now**.
The training data gives you walls at the **end of their life** with full retrospective
information.

### Feature-by-Feature Audit

| # | Feature | Live (causal?) | Offline Labeler | Verdict |
|---|---------|---------------|-----------------|---------|
| 1 | `time_in_book` | `now - first_seen` (time so far) | `completion_time - first_seen` (total lifetime) | **LEAKS** — offline tells model "lasted 0.3s" which directly triggers SPOOF rule (≤0.5s) |
| 2 | `modification_count` | Count so far | Total count across entire lifecycle | **LEAKS** — includes future modifications |
| 3 | `cancellation_count` | Count so far | Total count including final cancellation | **LEAKS** — the final cancellation IS the SPOOF event |
| 4 | `original_size` | Size at placement | Size at placement | **SAFE** |
| 5 | `max_size` | Peak so far | Peak across entire lifecycle | **LEAKS** — includes future refills/growth |
| 6 | `current_size` | Current resting size | Always 0 (wall is completed/dead) | **DEAD** — constant value in training data, zero importance |
| 7 | `size_ratio` | max_size(so far) / avg_wall | max_size(lifetime) / avg_wall(all walls) | **LEAKS** — derives from leaky max_size |
| 8 | `distance_from_mid` | Current mid price distance | Not populated in training data | **DEAD** — zero importance because training data defaults to 0 |
| 9 | `distance_from_bbo` | Current BBO distance | Not populated in training data | **DEAD** — same |
| 10 | `spread_at_placement` | Current spread | Not populated in training data | **DEAD** — same |
| 11 | `book_imbalance` | Current top-10 imbalance | Not populated in training data | **DEAD** — same |
| 12 | `side` | 0=bid, 1=ask | 0=bid, 1=ask | **SAFE** |
| 13 | `refill_count` | Count so far | Total refills across lifecycle | **LEAKS** — directly reveals ICEBERG label (rule: refill_count ≥ 2 → ICEBERG) |
| 14 | `price_crossed` | Has price crossed yet? | Did price ever cross during entire lifecycle | **LEAKS** — directly reveals STALE label (rule: price_crossed → STALE) |
| 15 | `modification_rate` | mod_count(so far) / time(so far) | mod_count(total) / time(total) | **DOUBLE LEAKS** — derives from two leaky features |

### Summary

- **Safe (2):** `original_size`, `side`
- **Leaky (9):** `time_in_book`, `modification_count`, `cancellation_count`, `max_size`, `size_ratio`, `refill_count`, `price_crossed`, `modification_rate`, `current_size`
- **Dead (4):** `distance_from_mid`, `distance_from_bbo`, `spread_at_placement`, `book_imbalance`

**13 of 15 features are either leaky or dead.** The binary F1=1.0 is not overfitting — it's
reading the answer from the features. `time_in_book` alone (importance: 7162) and
`modification_rate` (importance: 3684) together perfectly separate SPOOF from NOT_SPOOF
because they contain the lifetime duration which is the labeling rule itself.

### Why the 4-Class Confusion Exists

GENUINE↔STALE confusion (46 misclassified of 146 test samples):
- Both classes have similar `time_in_book` (long duration)
- Both have low `modification_rate`
- The only separator is `price_crossed` — but this is a binary flag, not a confidence gradient
- With retrospective data, even `price_crossed` doesn't cleanly separate them because
  a GENUINE wall that happens to get crossed late in life looks identical to STALE

---

## Phase 2: New Taxonomy

### Three Separate Prediction Targets

Instead of one flat classifier, we predict three orthogonal dimensions:

#### Target 1: Wall Intent (what kind of order is this?)
Predicted **continuously** as the wall lives. Uses only causal features available at time t.

| Label | Observable Behavior | Key Signals |
|-------|-------------------|-------------|
| `PASSIVE_REAL` | Sits at price, absorbs flow, doesn't pull on approach | Stable size, fills accumulate, no pull-before-test |
| `SPOOF_LIKE` | Placed large, pulls before tested or on approach | Large initial size, short pre-approach life, coordinated pulls |
| `RESERVE_REFRESH` | Refills after partial consumption (iceberg behavior) | Repeated refills after depletion, consistent tranche sizes |
| `MIGRATORY` | Moves to track price, reprices frequently | High repricing rate, price follows BBO movement |

#### Target 2: Wall State (what's happening to it right now?)
Updated **every DOM snapshot**. Pure observation, no prediction.

| State | Definition |
|-------|-----------|
| `FRESH` | Recently placed, not yet tested (age < 30s, no touch) |
| `ESTABLISHED` | Sitting for 30s+, not under attack |
| `UNDER_ATTACK` | Price within 2 ticks, aggressive flow hitting it |
| `DEFENDING` | Under attack but absorbing — refilling or holding |
| `EXHAUSTED` | Size depleted to <25% of max after attack |
| `STALE` | Price moved away, wall no longer relevant (>10 ticks from BBO) |
| `PULLED` | Size went to 0 (cancelled) |
| `CONSUMED` | Filled by aggressive flow (filled_volume > 50% of max) |

#### Target 3: Interaction Outcome (what will price do at this wall?)
Predicted **only when price is within N ticks**. This is the money model.

| Label | Definition (NQ, 4-tick = 1 point) |
|-------|----------------------------------|
| `BOUNCE` | Price reverses ≥8 ticks from wall before breaking ≥4 ticks through |
| `BREAK` | Price trades ≥4 ticks through wall before bouncing ≥8 ticks |
| `CHURN` | Neither clean bounce nor break within 30s lookforward |

---

## Phase 3: New Feature Architecture

### Causal Feature Set (available at any observation time t)

All features computed from information available **up to and including time t**.
No future information. No lifecycle completion required.

#### Block A: Wall Snapshot (8 features) — what the wall looks like RIGHT NOW

```
A1.  current_size          — resting size at time t
A2.  original_size         — size when first appeared
A3.  max_size_so_far       — peak size observed up to time t
A4.  age_seconds           — seconds since first_seen (up to now, not until death)
A5.  side                  — 0=bid, 1=ask
A6.  modifications_so_far  — count of size changes up to time t
A7.  refills_so_far        — count of refill events up to time t
A8.  size_vs_original      — current_size / original_size (depletion ratio)
```

#### Block B: Wall Behavior Trajectory (8 features) — how the wall has been acting

```
B1.  mod_rate_2s           — modifications in last 2 seconds
B2.  mod_rate_10s          — modifications in last 10 seconds
B3.  cancel_reappear_count — times wall went to 0 then came back
B4.  size_volatility_10s   — std dev of size changes over last 10 seconds
B5.  refill_elasticity     — avg(refill_size / depleted_size) across refills
B6.  pull_approach_flag    — did wall size decrease >50% as price approached within 4 ticks?
B7.  repricing_count       — times wall moved to a different price level (if tracking by order)
B8.  time_at_current_size  — seconds since last size change
```

#### Block C: Local Depth Geometry (8 features) — what the book looks like around this wall

```
C1.  prominence_zscore     — wall size vs mean of ±5 same-side levels
C2.  same_side_depth_behind — total volume 1-3 ticks behind wall (support depth)
C3.  same_side_depth_ahead  — total volume 1-3 ticks ahead of wall (toward mid)
C4.  opposite_depth_mirror  — opposite-side volume at same distance from mid
C5.  cluster_density        — number of levels within ±3 ticks with size > 50% of wall
C6.  depth_slope            — regression slope of same-side volume across ±5 ticks
C7.  vacuum_behind          — is there a gap (0 volume) in the 3 ticks behind?
C8.  ladder_correlation     — correlation of size changes across ±3 same-side levels (coordinated?)
```

#### Block D: Market Context (8 features) — where and when

```
D1.  distance_from_mid      — ticks from current mid price
D2.  distance_from_bbo      — ticks from best bid/offer on same side
D3.  spread_ticks            — current bid-ask spread in ticks
D4.  book_imbalance_top10    — (bid_vol - ask_vol) / (bid_vol + ask_vol) top 10
D5.  session_phase           — 0=pre-market, 1=open(first 30m), 2=morning, 3=lunch, 4=afternoon, 5=close(last 30m)
D6.  minutes_since_open      — minutes since RTH open (9:30 ET)
D7.  realized_vol_2m         — realized volatility over last 2 minutes (mid price returns)
D8.  range_expansion_flag    — 1 if current bar range > 1.5x avg of last 10 bars
```

#### Block E: Flow Context (6 features) — what aggressive flow is doing

```
E1.  cumulative_delta        — running buy - sell volume since session open
E2.  delta_2s                — aggressive flow in last 2 seconds (positive = buying)
E3.  delta_10s               — aggressive flow in last 10 seconds
E4.  approach_speed          — rate of mid price movement toward wall (ticks/sec over 5s)
E5.  consecutive_aggressor   — count of consecutive same-direction market orders
E6.  sweep_flag              — 1 if aggressive flow consumed ≥3 price levels in <500ms
```

#### Block F: Attack/Defense (6 features) — only populated when wall is under attack

```
F1.  absorbed_volume         — total aggressive volume absorbed at this level so far
F2.  absorption_ratio        — absorbed_volume / current_size (defense quality)
F3.  tests_count             — number of times price touched this level
F4.  recovery_after_test     — did size recover >75% within 5 seconds after last touch?
F5.  time_since_last_test    — seconds since price last touched this level
F6.  attack_intensity        — aggressive volume per second during current/last approach
```

### Total: 44 causal features
(Matches DEEP6's existing 44-signal architecture — not coincidence, this is the right
granularity for NQ microstructure.)

---

## Phase 4: Wall Episode Data Model

### Episode Structure

A wall episode captures the complete lifecycle of a significant price level,
stored as a time-series of snapshots rather than a single summary row.

```python
@dataclass
class WallEpisode:
    """Complete lifecycle of a significant wall, stored as snapshot series."""
    episode_id: str           # UUID
    session_date: str         # YYYY-MM-DD
    side: str                 # "bid" or "ask"
    price: float              # wall price level
    first_seen: pd.Timestamp  # when wall first exceeded min_wall threshold
    
    # Snapshot series — one row per observation point
    # Each snapshot contains all 44 causal features at that moment
    snapshots: pd.DataFrame   # columns: timestamp + 44 features
    
    # Resolved truth (filled in AFTER episode completes, NOT used in live features)
    intent_label: str | None       # PASSIVE_REAL / SPOOF_LIKE / RESERVE_REFRESH / MIGRATORY
    final_state: str | None        # PULLED / CONSUMED / STALE / ...
    
    # Touch events — each time price came within N ticks
    touches: list[TouchEvent]      # timestamp, mid_price, outcome (BOUNCE/BREAK/CHURN)
    
    # Metadata
    retirement_time: pd.Timestamp | None
    retirement_reason: str | None  # "pulled", "consumed", "stale", "session_end"
```

### Storage Format

```
data/episodes/
  session_2026-01-06/
    episodes.parquet        # one row per episode (metadata + resolved labels)
    snapshots.parquet       # one row per snapshot (episode_id + timestamp + 44 features)
    touches.parquet         # one row per touch event (episode_id + timestamp + outcome)
  session_2026-01-07/
    ...
```

### Training Data Construction

For **intent classification**: sample snapshots at regular intervals (every 5s) from each
episode. Label = episode's resolved intent_label. Features = 44 causal features at that
snapshot time. This gives multiple training rows per episode, all causally valid.

For **interaction prediction**: use touch events. Features = 44 causal features at touch
time + approach context. Label = resolved outcome (BOUNCE/BREAK/CHURN).

---

## Phase 5: Dashboard Integration

### New SQLite Tables

```sql
CREATE TABLE depthradar_episodes (
    episode_id TEXT PRIMARY KEY,
    session_date TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    first_seen TEXT NOT NULL,
    retirement_time TEXT,
    retirement_reason TEXT,
    intent_label TEXT,
    final_state TEXT,
    max_size INTEGER,
    duration_sec REAL,
    touch_count INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE depthradar_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT NOT NULL REFERENCES depthradar_episodes(episode_id),
    timestamp TEXT NOT NULL,
    features_json TEXT NOT NULL,  -- 44 features as JSON object
    intent_prediction TEXT,       -- live model prediction
    intent_confidence REAL,
    state TEXT,                   -- current wall state
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE depthradar_touches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT NOT NULL REFERENCES depthradar_episodes(episode_id),
    timestamp TEXT NOT NULL,
    mid_price REAL NOT NULL,
    outcome_prediction TEXT,     -- BOUNCE/BREAK/CHURN prediction
    outcome_confidence REAL,
    outcome_resolved TEXT,       -- actual outcome (filled later)
    features_json TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### WebSocket Message Types

```python
class LiveDepthradarMessage(BaseModel):
    type: Literal["depthradar"] = "depthradar"
    walls: list[WallSnapshot]     # current active walls with predictions
    episode_count: int            # total active episodes
    
class WallSnapshot(BaseModel):
    episode_id: str
    price: float
    side: str
    size: int
    max_size: int
    age_sec: float
    intent: str                   # predicted intent
    intent_confidence: float
    state: str                    # current state
    interaction: str | None       # predicted outcome (if near price)
    interaction_confidence: float | None
```

### API Endpoints

```
POST /events/depthradar           — ingest wall snapshots from live engine
GET  /api/depthradar/episodes     — list episodes for a session
GET  /api/depthradar/touches      — list touch events with outcomes
GET  /api/depthradar/metrics      — model performance (accuracy by intent, by outcome)
GET  /api/replay/{session}/depthradar — replay depthradar data for a session
```

---

## Phase 6: GEX/Options Context (Future)

Add as Block G features once the base system is validated:

```
G1.  gamma_regime            — positive / negative / near-flip (from FlashAlpha)
G2.  distance_to_call_wall   — ticks to nearest major call OI concentration
G3.  distance_to_put_wall    — ticks to nearest major put OI concentration
G4.  gex_at_price            — gamma exposure at wall price level
G5.  zero_dte_flag           — 1 if significant 0DTE OI near wall price
G6.  time_to_opex_hours      — hours until nearest monthly/weekly expiry
```

---

## Implementation Order

1. Build `WallEpisode` data model + Parquet storage
2. Build new `CausalFeatureExtractor` with 44 features (Blocks A-F)
3. Build `EpisodeLabeler` that processes Databento MBO into episodes with resolved labels
4. Batch-label all available MBO sessions
5. Train intent classifier (LightGBM on snapshot samples)
6. Train interaction predictor (LightGBM on touch events)
7. Wire into dashboard (SQLite + WebSocket + overlay)
8. Add GEX context (Block G) as enhancement
