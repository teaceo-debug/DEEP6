# DepthRadar v4 ML Optimization Plan

## Bottom line

The main weakness is **label impurity**, not model capacity. `mbo_wall_engine.py` currently overcalls `SPOOF_LIKE`, under-specifies `RESERVE_REFRESH`/`MIGRATORY`, and has a live-state bug where `_infer_state()` can never emit `CONSUMED` because `PULLED` returns first. Fix the rules first, then expose the missing causal signals the rules already depend on, then tighten the training split/weights.

## Domain basis used for this review

- **Spoof** = large visible order, short life (`< ~5s`), cancelled before price arrives, with **no trade at that price during its life**. Small routine cancels are not spoof. Basis: `C:\Users\Tea\DEEP6\cross_market\llm_expert\dom_expert_skills.md:35-41`.
- **Reserve / iceberg** = fill -> immediate same-price reload -> fill -> reload. Volume alone is not enough; refresh evidence is required. Basis: `C:\Users\Tea\DEEP6\.claude\skills\options-bias-engine\order-book\iceberg-detection.md:39-55` and `...\level-defense-scoring.md:64-99`.
- **Absorption** = aggressive flow hits the level but price does not advance; passive side holds. Basis: `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\microstructure.md:17-31`.
- **Dealer/GEX context** materially changes bounce/break odds near call wall / put wall / gamma flip. Basis: `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\gex-options.md:74-117`, `121-175`, and `C:\Users\Tea\DEEP6\.claude\skills\options-bias-engine\step1-regimes\regime-identification.md:132-193`.

---

## 1. Labeling improvements

### 1.1 Audit of current rules

### `_infer_state()`

1. **`CONSUMED` is unreachable in live snapshots.**
   - Current code returns `PULLED` when `current_size <= 0` before checking filled volume.
   - Result: snapshot states under-report real trade-through events; the model sees terminal `CONSUMED` only at retirement.

2. **`filled_volume >= 0.5 * max_size_so_far` is too loose for NQ.**
   - With `min_wall_size=50`, a wall is called consumed after ~25 lots trade, which is routine in NQ.
   - For NQ, a better inference threshold is **75% of visible peak** plus disappearance.

3. **`FRESH < 30s` is too long for NQ microstructure.**
   - In NQ, an untouched wall resting for 20-30 seconds is already behaviorally established.
   - `FRESH` should be **< 15s**.

4. **`DEFENDING` fires on too little evidence.**
   - Any `absorbed_volume > 0` plus `recovery_after_test` is enough.
   - A single small print is not defense in NQ. Require **meaningful absorption**.

### `_label_intent()`

1. **`first_test_time is None and final_state == PULLED -> SPOOF_LIKE` is too broad.**
   - False positives: genuine passive quotes that get cancelled for context change, session transition, or repricing.
   - For spoof in NQ, you need **short life + low/no fills + large pull before/into approach**.

2. **`pull_approach_flag` is too binary and too narrow.**
   - It only fires when the wall goes fully to zero within 2s of approach.
   - Spoofers often **pull 60-90% and leave a tiny stub**. Current rule misses these.

3. **`refills >= 2 and depletion_events >= 1 -> RESERVE_REFRESH` is under-specified.**
   - Refill should happen **after attack/fill**, preferably quickly, and ideally more than once.
   - Current rule can misclassify noisy quote resizing as reserve refresh.

4. **`repricing_count >= 3 and bbo_track_count >= 2 -> MIGRATORY` uses a hidden feature the model never sees.**
   - `bbo_track_count` is used for labels but is not in `causal_features.py`.
   - This makes `MIGRATORY` intrinsically hard to learn.

5. **`PASSIVE_REAL` default is too permissive.**
   - It absorbs all ambiguous cases, including weak spoof shelves and weak migrators.
   - This is acceptable only after spoof / reserve / migratory are tightened.

### 1.2 Expected false positives / false negatives from current logic

| Class | Expected false positives | Expected false negatives |
|---|---|---|
| `SPOOF_LIKE` | Untested genuine cancel; BBO repricing; passive wall pulled after meaningful defense | Partial pull leaving 1-2 lots; coordinated shelf pull across adjacent levels |
| `RESERVE_REFRESH` | Noisy size bouncing at top of book without real attack | True iceberg with very fast reloads but only one counted refill |
| `MIGRATORY` | Genuine wall stepping away after one failed test | Top-of-book tracker with many BBO-follow reprices but insufficient current rule evidence |
| `PASSIVE_REAL` | Ambiguous fake shelves default here | Real but short-lived defended walls can still be okay here; this is less harmful |

### 1.3 Exact code changes

## 1A. Add runtime fields needed for cleaner labels

**File:** `C:\Users\Tea\DEEP6\deep6\ml\depth_radar\mbo_wall_engine.py`

Add these fields to `_WallRuntime`:

```python
    approach_pull_ratio_max: float = 0.0
    min_distance_to_mid_ticks: float = 1e9
    same_price_reload_count: int = 0
    reload_latency_ms_sum: float = 0.0
    aggression_toward_wall_2s_on_pull: float = 0.0
```

## 1B. Track partial pull, min distance, reload latency, and flow-into-pull

**File:** `C:\Users\Tea\DEEP6\deep6\ml\depth_radar\mbo_wall_engine.py`

Add helper:

```python
    def _toward_wall_delta_2s(self, timestamp: pd.Timestamp, side: str) -> float:
        delta = self._window_delta(timestamp, 2)
        return float(delta if side == "ask" else -delta)
```

Inside `_advance_market_state()` after `mid_price` is computed, add:

```python
        best_bid, _ = self._dom.best_bid()
        best_ask, _ = self._dom.best_ask()
        for runtime in self._active.values():
            distance_ticks = abs(mid_price - runtime.current_price) / self.tick_size
            runtime.min_distance_to_mid_ticks = min(runtime.min_distance_to_mid_ticks, distance_ticks)
```

Inside `_update_or_create_episode()`, replace the zero/pull block with:

```python
        if previous > size and runtime.approach_near_time is not None:
            secs_from_approach = (timestamp - runtime.approach_near_time).total_seconds()
            if 0.0 <= secs_from_approach <= 1.5:
                pull_ratio = (previous - size) / max(previous, 1)
                runtime.approach_pull_ratio_max = max(runtime.approach_pull_ratio_max, pull_ratio)
                if pull_ratio >= 0.60:
                    runtime.pull_approach_flag = True

        if previous > 0 and size == 0:
            runtime.zero_since = timestamp
            runtime.aggression_toward_wall_2s_on_pull = max(
                runtime.aggression_toward_wall_2s_on_pull,
                self._toward_wall_delta_2s(timestamp, side),
            )
        elif previous == 0 and size > 0:
            runtime.cancel_reappear_count += 1
            if runtime.zero_since is not None:
                reload_ms = (timestamp - runtime.zero_since).total_seconds() * 1000.0
                if reload_ms <= 1000.0:
                    runtime.same_price_reload_count += 1
                    runtime.reload_latency_ms_sum += reload_ms
            runtime.zero_since = None
```

## 1C. Replace `_infer_state()`

**File:** `C:\Users\Tea\DEEP6\deep6\ml\depth_radar\mbo_wall_engine.py`

```python
    def _infer_state(self, runtime: _WallRuntime, timestamp: pd.Timestamp, mid_price: float) -> WallState:
        peak_size = max(runtime.original_size, runtime.max_size_so_far, 1)
        distance_ticks = abs(mid_price - runtime.current_price) / self.tick_size

        if runtime.current_size <= 0:
            if runtime.filled_volume >= max(12, int(0.75 * peak_size)):
                return WallState.CONSUMED
            return WallState.PULLED

        if distance_ticks <= 2:
            if (
                runtime.absorbed_volume >= max(12, int(0.20 * peak_size))
                and (runtime.recovery_after_test or runtime.refills_so_far >= 1)
            ):
                return WallState.DEFENDING
            if runtime.tests_count >= 1 and runtime.current_size <= int(0.20 * peak_size):
                return WallState.EXHAUSTED
            return WallState.UNDER_ATTACK

        if runtime.age_seconds(timestamp) < 15.0 and runtime.tests_count == 0:
            return WallState.FRESH
        if runtime.stale_since is not None:
            return WallState.STALE
        return WallState.ESTABLISHED
```

## 1D. Replace `_infer_terminal_state()`

**File:** `C:\Users\Tea\DEEP6\deep6\ml\depth_radar\mbo_wall_engine.py`

```python
    def _infer_terminal_state(self, runtime: _WallRuntime) -> WallState:
        peak_size = max(runtime.original_size, runtime.max_size_so_far, 1)
        if runtime.current_size <= 0:
            if runtime.filled_volume >= max(12, int(0.75 * peak_size)):
                return WallState.CONSUMED
            return WallState.PULLED
        if runtime.stale_since is not None:
            return WallState.STALE
        if runtime.tests_count >= 1 and runtime.current_size <= int(0.20 * peak_size):
            return WallState.EXHAUSTED
        return WallState.ESTABLISHED
```

## 1E. Replace `_label_intent()`

**File:** `C:\Users\Tea\DEEP6\deep6\ml\depth_radar\mbo_wall_engine.py`

```python
    def _label_intent(self, runtime: _WallRuntime, timestamp: pd.Timestamp, final_state: WallState) -> WallIntent:
        peak_size = max(runtime.original_size, runtime.max_size_so_far, 1)
        age_s = runtime.age_seconds(timestamp)
        bbo_track_ratio = runtime.bbo_track_count / max(runtime.repricing_count, 1)

        small_fill = runtime.filled_volume <= max(3, int(0.05 * peak_size))
        meaningful_fill = runtime.filled_volume >= max(8, int(0.15 * peak_size))
        meaningful_absorption = runtime.absorbed_volume >= max(12, int(0.20 * peak_size))
        defended = runtime.tests_count >= 1 and (
            runtime.recovery_after_test or runtime.refills_so_far >= 1 or meaningful_absorption
        )

        if (
            runtime.tests_count >= 1
            and runtime.depletion_events >= 2
            and runtime.refills_so_far >= 2
            and runtime.same_price_reload_count >= 2
            and runtime.absorbed_volume >= max(20, int(0.40 * peak_size))
        ):
            return WallIntent.RESERVE_REFRESH

        if (
            runtime.repricing_count >= 4
            and runtime.bbo_track_count >= 3
            and bbo_track_ratio >= 0.60
            and runtime.tests_count <= 1
            and runtime.absorbed_volume <= max(8, int(0.10 * peak_size))
        ):
            return WallIntent.MIGRATORY

        if (
            final_state == WallState.PULLED
            and small_fill
            and runtime.refills_so_far == 0
            and not defended
            and (
                (runtime.first_test_time is None and age_s <= 5.0)
                or (
                    runtime.pull_approach_flag
                    and runtime.approach_pull_ratio_max >= 0.60
                    and runtime.min_distance_to_mid_ticks <= 4.0
                    and age_s <= 15.0
                    and runtime.aggression_toward_wall_2s_on_pull >= max(10.0, 0.15 * peak_size)
                )
            )
        ):
            return WallIntent.SPOOF_LIKE

        if age_s >= 20.0 or meaningful_fill or meaningful_absorption or runtime.tests_count >= 2:
            return WallIntent.PASSIVE_REAL

        return WallIntent.PASSIVE_REAL
```

### 1.4 How to handle intent changes mid-life

- **If the wall ever had meaningful interaction** (`tests_count >= 2`, or meaningful fill, or meaningful absorption), **never backfit the later cancel into `SPOOF_LIKE`**.
- A wall that starts real and later drifts away should remain:
  - `intent_label = PASSIVE_REAL`
  - `final_state = STALE` or `PULLED`
- A wall should only become `MIGRATORY` if the dominant behavior is **BBO-follow repricing with low interaction**.

That rule is already enforced by the new `small_fill + not defended + short life / strong pull-on-approach` spoof gate.

---

## 2. Feature additions

### 2.1 Which existing features should matter most by intent class

| Intent class | Most predictive current features | Why |
|---|---|---|
| `SPOOF_LIKE` | `pull_approach_flag`, `age_seconds`, `mod_rate_2s`, `size_volatility_10s`, `distance_from_bbo`, `consecutive_aggressor`, `sweep_flag` | Spoofs are fast, unstable, close to approach, and often coincide with one-sided aggression |
| `RESERVE_REFRESH` | `refills_so_far`, `refill_elasticity`, `absorbed_volume`, `absorption_ratio`, `tests_count`, `recovery_after_test`, `attack_intensity` | Reserve refresh is defense-under-attack, not passive resting |
| `MIGRATORY` | `repricing_count`, `distance_from_bbo`, `time_at_current_size`, `mod_rate_2s`, `ladder_correlation` | Migratory quotes behave like top-of-book trackers, not defended walls |
| `PASSIVE_REAL` | `age_seconds`, `time_at_current_size`, `prominence_zscore`, `same_side_depth_behind`, `absorbed_volume`, `tests_count`, `recovery_after_test` | Genuine walls persist and hold pressure |

### 2.2 Missing causal features that should be added now

The biggest gap is that the labeler uses signals the model cannot see (`bbo_track_count`), while some core microstructure concepts are only weakly approximated.

### 2.2.1 Exact feature list expansion

**File:** `C:\Users\Tea\DEEP6\deep6\ml\depth_radar\causal_features.py`

Append these 14 features and change the feature count from **44 -> 58**.

```python
CAUSAL_FEATURE_NAMES: list[str] = [
    # existing 44 features...
    "bbo_track_ratio",
    "first_test_latency",
    "filled_volume_ratio",
    "min_distance_to_mid",
    "same_price_reload_count",
    "mean_reload_latency_ms",
    "approach_pull_ratio_max",
    "aggression_toward_wall_2s_on_pull",
    "gex_regime_sign",
    "gex_regime_strength",
    "distance_to_gamma_flip_ticks",
    "distance_to_call_wall_ticks",
    "distance_to_put_wall_ticks",
    "gex_wall_position_pct",
]

assert len(CAUSAL_FEATURE_NAMES) == 58, f"Expected 58 features, got {len(CAUSAL_FEATURE_NAMES)}"
NUM_CAUSAL_FEATURES = 58
```

### 2.2.2 Exact feature definitions

**File:** `C:\Users\Tea\DEEP6\deep6\ml\depth_radar\mbo_wall_engine.py`

Add these to `wall_data` inside `_feature_dict()`:

```python
            "bbo_track_ratio": runtime.bbo_track_count / max(runtime.repricing_count, 1),
            "first_test_latency": (
                (runtime.first_test_time - runtime.first_seen).total_seconds()
                if runtime.first_test_time is not None
                else runtime.age_seconds(timestamp)
            ),
            "filled_volume_ratio": runtime.filled_volume / max(runtime.max_size_so_far, 1),
            "min_distance_to_mid": runtime.min_distance_to_mid_ticks,
            "same_price_reload_count": runtime.same_price_reload_count,
            "mean_reload_latency_ms": runtime.reload_latency_ms_sum / max(runtime.same_price_reload_count, 1),
            "approach_pull_ratio_max": runtime.approach_pull_ratio_max,
            "aggression_toward_wall_2s_on_pull": runtime.aggression_toward_wall_2s_on_pull,
```

**File:** `C:\Users\Tea\DEEP6\deep6\ml\depth_radar\causal_features.py`

Add these assignments in `extract()`:

```python
        vec[_IDX["bbo_track_ratio"]] = self._as_float(wall_data.get("bbo_track_ratio"))
        vec[_IDX["first_test_latency"]] = max(self._as_float(wall_data.get("first_test_latency")), 0.0)
        vec[_IDX["filled_volume_ratio"]] = self._as_float(wall_data.get("filled_volume_ratio"))
        vec[_IDX["min_distance_to_mid"]] = self._as_float(wall_data.get("min_distance_to_mid"))
        vec[_IDX["same_price_reload_count"]] = self._as_float(wall_data.get("same_price_reload_count"))
        vec[_IDX["mean_reload_latency_ms"]] = self._as_float(wall_data.get("mean_reload_latency_ms"))
        vec[_IDX["approach_pull_ratio_max"]] = self._as_float(wall_data.get("approach_pull_ratio_max"))
        vec[_IDX["aggression_toward_wall_2s_on_pull"]] = self._as_float(
            wall_data.get("aggression_toward_wall_2s_on_pull")
        )
```

### 2.3 Block G (GEX context): add now, but only for the interaction model first

### Recommendation

- **Intent model:** do **not** rely on GEX first. Intent is primarily a book-behavior problem.
- **Interaction model (BOUNCE/BREAK/CHURN): yes, add Block G now.** Dealer regime and distance to call wall / put wall / gamma flip directly change whether a wall is likely to hold.

### Why now

The repo already has enough GEX primitives in `C:\Users\Tea\DEEP6\deep6\engines\gex.py`:

- `regime`
- `net_gex_at_spot`
- `gamma_flip`
- `call_wall`
- `put_wall`

That is enough for a first useful Block G. Do **not** wait for full DEX/VEX/CHEX before adding the base dealer-context features.

### Exact Block G feature definitions for NQ

Use **NQ prices**, not QQQ prices, in the feature frame.

```python
gex_regime_sign               # +1 positive dampening, -1 negative amplifying, 0 stale/neutral
gex_regime_strength           # regime_sign * min(abs(net_gex_at_spot) / 1e9, 3.0)
distance_to_gamma_flip_ticks  # (wall_price - gamma_flip_nq) / tick_size
distance_to_call_wall_ticks   # (call_wall_nq - wall_price) / tick_size
distance_to_put_wall_ticks    # (wall_price - put_wall_nq) / tick_size
gex_wall_position_pct         # clip((wall_price - put_wall_nq) / (call_wall_nq - put_wall_nq), 0, 1)
```

### Exact extractor code

**File:** `C:\Users\Tea\DEEP6\deep6\ml\depth_radar\causal_features.py`

Change the extractor signature to accept `gex_context`:

```python
    def extract(
        self,
        wall_data: dict,
        market_context: dict,
        flow_context: dict,
        attack_context: dict,
        gex_context: dict[str, Any] | None = None,
    ) -> np.ndarray:
```

Then add:

```python
        gex_context = gex_context or {}
        call_wall_nq = self._as_float(gex_context.get("call_wall_nq"))
        put_wall_nq = self._as_float(gex_context.get("put_wall_nq"))
        gamma_flip_nq = self._as_float(gex_context.get("gamma_flip_nq"))
        regime_sign = self._as_float(gex_context.get("regime_sign"))
        net_gex = self._as_float(gex_context.get("net_gex_at_spot"))
        wall_span = max(call_wall_nq - put_wall_nq, self.tick_size)

        vec[_IDX["gex_regime_sign"]] = regime_sign
        vec[_IDX["gex_regime_strength"]] = regime_sign * min(abs(net_gex) / 1e9, 3.0)
        vec[_IDX["distance_to_gamma_flip_ticks"]] = (
            (wall_price - gamma_flip_nq) / self.tick_size if gamma_flip_nq > 0 else 0.0
        )
        vec[_IDX["distance_to_call_wall_ticks"]] = (
            (call_wall_nq - wall_price) / self.tick_size if call_wall_nq > 0 else 0.0
        )
        vec[_IDX["distance_to_put_wall_ticks"]] = (
            (wall_price - put_wall_nq) / self.tick_size if put_wall_nq > 0 else 0.0
        )
        vec[_IDX["gex_wall_position_pct"]] = (
            min(max((wall_price - put_wall_nq) / wall_span, 0.0), 1.0)
            if call_wall_nq > put_wall_nq > 0
            else 0.5
        )
```

### Exact plumbing change

**File:** `C:\Users\Tea\DEEP6\deep6\ml\depth_radar\mbo_wall_engine.py`

Add a setter:

```python
        self._latest_gex_context: dict[str, float] | None = None

    def update_gex_context(self, context: dict[str, float]) -> None:
        self._latest_gex_context = dict(context)
```

Then in `_feature_dict()`:

```python
        gex_context = self._latest_gex_context or {}
        vec = self._extractor.extract(wall_data, market_context, flow_context, attack_context, gex_context)
```

### Offline training requirement

To train with Block G, persist a timestamped `gex_context.parquet` and ASOF-join it to `snapshots.parquet` / `touches.parquet` by timestamp. Do **not** backfill with current-day GEX values.

### 2.4 Likely noisy / redundant current features

- `cumulative_delta` is likely noisy for **intent**; it is session-level, not wall-local.
- `minutes_since_open` and `session_phase` overlap.
- `distance_from_mid` and `distance_from_bbo` are correlated; `distance_from_bbo` is usually more useful for migratory behavior.
- `absorbed_volume` and `absorption_ratio` are correlated; keep both, but regularize.

**Recommendation:** keep them for the first leak-free retrain; handle redundancy with regularization, not manual deletion, until new importances are inspected.

---

## 3. Training config changes

### 3.1 Keep LightGBM, but change the split, weights, and tree size

`44-58` mostly numeric causal features + non-linear interactions still fits LightGBM well. The current problem is not that LightGBM is too weak; it is that the training frame is too correlated and slightly leaky.

### Main changes

1. **Split by `session_date`, not raw row timestamp.**
   - Current row-wise 80/20 split can place snapshots from the same wall family/day on both sides.
   - For touches, `session_date` must first be joined from `episodes_df`.

2. **Down-weight long-lived walls.**
   - Long passive walls create many snapshots and dominate the intent model.
   - Weight by `1 / snapshots_per_episode` (or `1 / touches_per_episode` for touch data).

3. **Thin snapshots for intent training.**
   - Current `snapshot_interval=2s` oversamples long episodes.
   - Use **every other snapshot** (`4s effective cadence`) and cap at **12 snapshots per episode**.

4. **Use smaller, more regularized trees.**
   - `num_leaves=31` is loose for this feature count and correlation structure.

### 3.2 Exact split change

**File:** `C:\Users\Tea\DEEP6\scripts\train_depth_radar_v4.py`

Replace `split_walk_forward()` with a session-based version:

```python
def split_walk_forward_by_session(
    frame: pd.DataFrame,
    session_col: str,
    timestamp_col: str,
    label_col: str,
    label_to_id: dict[str, int],
    frame_name: str,
) -> dict[str, Any]:
    ensure_required_columns(frame, [session_col, timestamp_col, label_col], frame_name)
    cleaned = frame.copy()
    cleaned[label_col] = cleaned[label_col].astype(str).str.upper()
    cleaned = cleaned[cleaned[label_col].isin(label_to_id)].copy()
    if cleaned.empty:
        raise ValueError(f"{frame_name} has no rows with supported labels in `{label_col}`.")

    cleaned = sort_temporally(cleaned, timestamp_col, frame_name)
    sessions = (
        cleaned[[session_col, timestamp_col]]
        .assign(_ts=pd.to_datetime(cleaned[timestamp_col], errors="coerce", utc=True))
        .groupby(session_col, as_index=False)["_ts"]
        .min()
        .sort_values("_ts", kind="stable")[session_col]
        .astype(str)
        .tolist()
    )
    if len(sessions) < 2:
        raise ValueError(f"{frame_name} needs at least 2 sessions for walk-forward splitting.")

    split_idx = int(len(sessions) * 0.8)
    split_idx = min(max(split_idx, 1), len(sessions) - 1)
    train_sessions = set(sessions[:split_idx])

    train_mask = cleaned[session_col].astype(str).isin(train_sessions)
    train_frame = cleaned.loc[train_mask].copy()
    test_frame = cleaned.loc[~train_mask].copy()

    X_train = build_feature_matrix(train_frame)
    X_test = build_feature_matrix(test_frame)
    y_train = train_frame[label_col].map(label_to_id).astype(np.int8).to_numpy()
    y_test = test_frame[label_col].map(label_to_id).astype(np.int8).to_numpy()

    return {
        "frame": cleaned,
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "train_frame": train_frame,
        "test_frame": test_frame,
    }
```

### 3.3 Exact weighting + thinning changes

**File:** `C:\Users\Tea\DEEP6\scripts\train_depth_radar_v4.py`

Add:

```python
def thin_snapshot_training_rows(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.assign(_ts=pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)).sort_values(
        ["episode_id", "_ts"], kind="stable"
    )
    return (
        ordered.groupby("episode_id", group_keys=False)
        .apply(lambda g: g.iloc[::2].head(12))
        .drop(columns="_ts")
        .reset_index(drop=True)
    )


def compute_group_balanced_weights(frame: pd.DataFrame, targets: np.ndarray, group_col: str) -> np.ndarray:
    class_weights = compute_balanced_sample_weights(targets)
    group_sizes = frame[group_col].astype(str).value_counts()
    group_weights = frame[group_col].astype(str).map(lambda g: 1.0 / float(group_sizes[g])).to_numpy(dtype=np.float64)
    weights = class_weights * group_weights
    return weights / np.mean(weights)
```

Use it in `train_intent_classifier()`:

```python
    training_frame = thin_snapshot_training_rows(training_frame)
    split = split_walk_forward_by_session(
        frame=training_frame,
        session_col="session_date",
        timestamp_col="timestamp",
        label_col="intent_label",
        label_to_id=INTENT_LABEL_TO_ID,
        frame_name="intent training frame",
    )
```

And in the train call, replace sample weights with:

```python
    sample_weight = compute_group_balanced_weights(split["train_frame"], split["y_train"], "episode_id")
```

For touches, first join `session_date`:

```python
    touch_meta = episodes_df.loc[:, ["episode_id", "session_date"]].copy()
    training_frame = touches_df.merge(touch_meta, on="episode_id", how="left", validate="many_to_one")
```

Then split by `session_date` and weight by `episode_id` exactly the same way.

### 3.4 Exact LightGBM params

### Intent model params

```python
INTENT_PARAMS: dict[str, Any] = {
    "objective": "multiclass",
    "metric": "multi_logloss",
    "boosting_type": "gbdt",
    "num_leaves": 15,
    "max_depth": 5,
    "min_data_in_leaf": 64,
    "learning_rate": 0.03,
    "feature_fraction": 0.75,
    "bagging_fraction": 0.75,
    "bagging_freq": 1,
    "lambda_l1": 1.0,
    "lambda_l2": 8.0,
    "min_gain_to_split": 0.05,
    "max_bin": 127,
    "verbose": -1,
}
```

Training loop change:

```python
num_boost_round=600
callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)]
```

### Why these params

- Smaller trees because snapshots from the same wall are highly correlated.
- Lower LR + more rounds because causal wall behavior is noisy and needs smoother partitions.
- `min_data_in_leaf=64` and L1/L2 are there to avoid memorizing per-session wall shapes.

### 3.5 Interaction model architecture: change from flat 3-class to hierarchical 2-stage

### Recommendation

Do **not** keep `BOUNCE/BREAK/CHURN` as one flat 3-class problem.

`CHURN` is structurally different:
- it often means **no clean resolution**, not a third direction,
- it is common during lunch / weak attack / neutral GEX,
- it dilutes the break-vs-bounce decision boundary.

### Exact architecture

#### Stage A — resolution model
- Target: `resolved = outcome in {BOUNCE, BREAK}` vs `CHURN`

#### Stage B — direction model
- On resolved rows only, target: `BREAK` vs `BOUNCE`

### Exact params for both binary models

```python
INTERACTION_BINARY_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": "binary_logloss",
    "boosting_type": "gbdt",
    "num_leaves": 23,
    "max_depth": 5,
    "min_data_in_leaf": 32,
    "learning_rate": 0.03,
    "feature_fraction": 0.80,
    "bagging_fraction": 0.80,
    "bagging_freq": 1,
    "lambda_l1": 0.5,
    "lambda_l2": 5.0,
    "min_gain_to_split": 0.02,
    "max_bin": 127,
    "verbose": -1,
}
```

### Exact training change

**File:** `C:\Users\Tea\DEEP6\scripts\train_depth_radar_v4.py`

Add a binary trainer:

```python
def train_lightgbm_binary(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    feature_names: list[str],
    sample_weight: np.ndarray,
    params: dict[str, Any],
) -> Any:
    require_lightgbm()
    train_set = lgb.Dataset(X_train, label=y_train, weight=sample_weight, feature_name=feature_names)
    valid_set = lgb.Dataset(X_test, label=y_test, feature_name=feature_names, reference=train_set)
    return lgb.train(
        params=params,
        train_set=train_set,
        num_boost_round=600,
        valid_sets=[valid_set],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
    )
```

Replace `train_interaction_predictor()` with:

```python
def train_interaction_predictor(touches_df: pd.DataFrame, episodes_df: pd.DataFrame, output_dir: Path) -> dict[str, Any] | None:
    ensure_required_columns(touches_df, ["episode_id", "timestamp", "outcome"], "touches_df")
    touch_meta = episodes_df.loc[:, ["episode_id", "session_date"]].copy()
    training_frame = touches_df.merge(touch_meta, on="episode_id", how="left", validate="many_to_one")
    training_frame = training_frame[training_frame["outcome"].notna()].copy()
    training_frame["outcome"] = training_frame["outcome"].astype(str).str.upper()

    # Stage A: resolved vs churn
    resolution_frame = training_frame.copy()
    resolution_frame["resolved"] = resolution_frame["outcome"].isin(
        [InteractionOutcome.BOUNCE.value, InteractionOutcome.BREAK.value]
    ).astype(np.int8)
    split_a = split_walk_forward_by_session(
        frame=resolution_frame,
        session_col="session_date",
        timestamp_col="timestamp",
        label_col="resolved",
        label_to_id={"0": 0, "1": 1},
        frame_name="interaction resolution frame",
    )

    # Stage B: break vs bounce on resolved rows only
    direction_frame = training_frame[
        training_frame["outcome"].isin([InteractionOutcome.BOUNCE.value, InteractionOutcome.BREAK.value])
    ].copy()
    direction_frame["break_label"] = (direction_frame["outcome"] == InteractionOutcome.BREAK.value).astype(np.int8)
    split_b = split_walk_forward_by_session(
        frame=direction_frame,
        session_col="session_date",
        timestamp_col="timestamp",
        label_col="break_label",
        label_to_id={"0": 0, "1": 1},
        frame_name="interaction direction frame",
    )

    weight_a = compute_group_balanced_weights(split_a["train_frame"], split_a["y_train"], "episode_id")
    weight_b = compute_group_balanced_weights(split_b["train_frame"], split_b["y_train"], "episode_id")

    resolution_model = train_lightgbm_binary(
        split_a["X_train"], split_a["y_train"], split_a["X_test"], split_a["y_test"], list(CAUSAL_FEATURE_NAMES), weight_a, INTERACTION_BINARY_PARAMS
    )
    direction_model = train_lightgbm_binary(
        split_b["X_train"], split_b["y_train"], split_b["X_test"], split_b["y_test"], list(CAUSAL_FEATURE_NAMES), weight_b, INTERACTION_BINARY_PARAMS
    )

    payload = {
        "mode": "hierarchical",
        "resolution_model": resolution_model,
        "direction_model": direction_model,
        "class_names": list(INTERACTION_CLASS_NAMES),
        "feature_names": list(CAUSAL_FEATURE_NAMES),
        "decision_thresholds": {"resolved": 0.55, "break": 0.55},
        "version": "v4",
    }
    output_path = output_dir / "interaction_predictor_v4.joblib"
    joblib.dump(payload, output_path)
    return {"path": output_path}
```

### Exact inference rule

```python
if p_resolved < 0.55:
    outcome = "CHURN"
else:
    outcome = "BREAK" if p_break >= 0.55 else "BOUNCE"
```

This is the right structure for wall interactions: first ask **does this wall resolve cleanly at all?**, then ask **which way?**

---

## 4. Priority ranking

| Priority | Change | Why it matters most | Effort |
|---|---|---|---|
| P1 | Fix `_infer_state()` / `_infer_terminal_state()` / `_label_intent()` | Removes the largest source of label noise and fixes the unreachable `CONSUMED` state bug | Short |
| P2 | Add the 8 missing microstructure features (`bbo_track_ratio`, reload latency, first-test latency, pull ratio, etc.) | Lets the model actually see the signals the rules are already using | Short |
| P3 | Change training split to `session_date` + apply episode weighting/thinning | Prevents long passive walls from dominating and reduces intra-episode leakage | Short |
| P4 | Replace flat 3-class interaction model with hierarchical binary stages | Better matches wall microstructure: `CHURN` is non-resolution, not a third direction | Medium |
| P5 | Add Block G to the interaction model | Dealer regime materially changes bounce/break odds near walls | Medium |

## Recommended implementation order

1. **Implement P1 first.** Retrain once with no feature additions; inspect how intent distribution changes.
2. **Implement P2 + P3 together.** This is the cleanest first serious retrain.
3. **Then implement P4.** The interaction model will benefit more from cleaned labels + new features than from architecture alone.
4. **Then implement P5.** Add Block G only after you can ASOF-join timestamped historical GEX context.

## Final recommendation

Do **not** chase a bigger model yet. The highest-ROI path is: **clean spoof / reserve / migratory labels -> expose the missing causal signals -> leak-proof the split -> then add dealer-context to the interaction model**.
