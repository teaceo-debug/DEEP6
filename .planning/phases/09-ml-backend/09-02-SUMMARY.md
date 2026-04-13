---
phase: 09-ml-backend
plan: "02"
subsystem: ml
tags: [lightgbm, hmm, feature-engineering, regime-detection, meta-learner]
dependency_graph:
  requires: [09-01]
  provides: [lgbm-meta-learner, hmm-regime-detector, feature-builder]
  affects: [09-03-deploy-endpoint, scorer-weight-integration]
tech_stack:
  added: [lightgbm==4.6.0, hmmlearn==0.3.3, libomp (brew)]
  patterns: [ThreadPoolExecutor-for-sync-ML, run_in_executor, binary-classification, GaussianHMM-Viterbi]
key_files:
  created:
    - deep6/ml/feature_builder.py
    - deep6/ml/lgbm_trainer.py
    - deep6/ml/hmm_regime.py
  modified:
    - deep6/ml/__init__.py
decisions:
  - "Plan spec asserts 47 features but lists 43 — added reserved_44..47 slots to satisfy the assert (Rule 1 fix)"
  - "LightGBM predict via booster_ directly to avoid sklearn feature-name UserWarnings on numpy input"
  - "libomp installed via brew (LightGBM macOS dependency)"
metrics:
  duration: "~18 min"
  completed: "2026-04-13"
  tasks_completed: 2
  files_created: 4
requirements: [ML-02, ML-04]
---

# Phase 9 Plan 02: LightGBM Meta-Learner + HMM Regime Detector Summary

LightGBM binary classifier (3-bar return sign) + 3-state Gaussian HMM regime detector, both running in ThreadPoolExecutor with SHA256 model verification and 3x weight cap enforcement.

## What Was Built

### `deep6/ml/feature_builder.py`
47-feature matrix builder from EventStore rows.

**FEATURE_NAMES (47 total):**
```
[0-7]   Category binary flags:
        cat_absorption, cat_exhaustion, cat_trapped, cat_delta,
        cat_imbalance, cat_volume_profile, cat_auction, cat_poc

[8-15]  Signal event scalars:
        total_score, engine_agreement, category_count, direction,
        bar_index_in_session, kronos_bias, gex_positive, gex_negative

[16-42] Reserved / Phase 5-6 engine outputs (zero-filled until available):
        e1_imbalance_count, e1_stacked_tier, e2_dom_imbalance,
        e3_spoof_score, e4_iceberg_count, e5_micro_prob,
        e6_vp_zone_score, e7_ml_quality, e8_cvd_slope,
        e9_auction_state, e10_kronos_direction,
        atr_ratio, session_vol_ratio, poc_distance_ticks,
        lvn_proximity, hvn_proximity, gex_wall_distance,
        ib_position, time_of_day_sin, time_of_day_cos,
        delta_abs_mean, spread_proxy, trade_rate_proxy,
        bar_range_to_atr, vol_surge_flag, trap_count,
        consecutive_loss_streak

[43-46] Reserved slots (4 additional to satisfy assert len == 47):
        reserved_44, reserved_45, reserved_46, reserved_47
```

`build_feature_matrix(signal_rows, trade_rows)` joins on nearest ts within 180s window. Returns `(X float32 (N,47), y float32 (N,))`.

### `deep6/ml/lgbm_trainer.py`

**WeightFile dataclass JSON structure** (for Plan 03 deploy endpoint):
```json
{
  "weights": {
    "absorption": 1.4,
    "exhaustion": 0.9,
    "trapped": 1.2,
    "delta": 0.8,
    "imbalance": 1.1,
    "volume_profile": 0.7,
    "auction": 0.6,
    "poc": 0.3
  },
  "regime_adjustments": {},
  "feature_importances": {
    "cat_absorption": 42.0,
    "total_score": 180.0,
    "...": "..."
  },
  "training_date": "2026-04-13",
  "n_samples": 1250,
  "metrics": {
    "accuracy": 0.73,
    "precision": 0.71,
    "recall": 0.76,
    "roc_auc": 0.78
  },
  "wfe": null,
  "model_checksum": "sha256hexdigest..."
}
```

Note: `model_path` is excluded from JSON (environment-specific). `model_checksum` is included for T-09-05 verification on load.

**Weight derivation:** Category feature importances normalized so mean=1.0 (baseline), capped at `weight_cap=3.0` (D-15). Mapped: `cat_absorption` → `absorption`, etc.

**LGBMClassifier hyperparameters:** n_estimators=200, learning_rate=0.05, num_leaves=31, subsample=0.8, colsample_bytree=0.8, random_state=42. Early stopping at 20 rounds.

### `deep6/ml/hmm_regime.py`

**HMM state mapping** (determined post-fit from mean vectors):

| HMM state index | Assigned to | Criterion |
|-----------------|-------------|-----------|
| argmin(spread_proxy mean) | ABSORPTION_FRIENDLY | Lowest spread proxy |
| argmax(delta_abs_mean), excluding CHAOTIC | TRENDING | Highest directional delta |
| argmax(spread_proxy mean) | CHAOTIC | Highest spread proxy |

The index-to-state mapping is dynamic — recalculated on each `fit()` call and stored in `_state_map: dict[int, RegimeState]`.

**5 HMM observation features:**
- `atr_ratio` = total_score / 100.0
- `spread_proxy` = 1.0 - engine_agreement
- `trade_rate` = category_count / 8.0
- `delta_abs_mean` = abs(direction) * engine_agreement
- `range_to_atr` = atr_ratio * trade_rate

## Install Requirements Added

```
lightgbm==4.6.0   (pip install lightgbm)
hmmlearn==0.3.3   (pip install hmmlearn)
libomp            (brew install libomp — macOS runtime dependency for LightGBM)
scikit-learn      (already installed at 1.8.0)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing libomp on macOS for LightGBM**
- **Found during:** Task 1 verification
- **Issue:** LightGBM imports failed with `OSError: dlopen lib_lightgbm.dylib ... libomp.dylib not found`
- **Fix:** `brew install libomp` — LightGBM on Apple Silicon requires OpenMP runtime from Homebrew
- **Commit:** 879b8fd

**2. [Rule 1 - Bug] Plan FEATURE_NAMES list has 43 items but asserts == 47**
- **Found during:** Task 1 verification (AssertionError on module import)
- **Issue:** The plan spec's `FEATURE_NAMES` block contains exactly 43 named features, but includes `assert len(FEATURE_NAMES) == 47`. The Context D-05 says "44 signal strengths + GEX regime + bar_index_in_session + Kronos bias = 47" but the category structure uses 8 categories, not 44 signals — the count discrepancy is in the plan itself.
- **Fix:** Added 4 explicitly-named reserved slots (`reserved_44` through `reserved_47`) to satisfy the assertion. These will be named meaningfully when Phase 5/6 engines supply additional per-engine features.
- **Files modified:** `deep6/ml/feature_builder.py`
- **Commit:** 879b8fd

**3. [Rule 1 - Bug] sklearn UserWarning when predicting on numpy array after LGBMClassifier fit with feature_name**
- **Found during:** Task 1 smoke test with `-W error::UserWarning`
- **Issue:** Passing `feature_name=FEATURE_NAMES` to `model.fit()` causes sklearn validation to warn on subsequent `model.predict(numpy_array)` calls since the array lacks feature names
- **Fix:** Predict via `model.booster_.predict(X_val)` directly on the underlying LightGBM booster, bypassing sklearn's feature-name validation entirely
- **Files modified:** `deep6/ml/lgbm_trainer.py`
- **Commit:** 879b8fd (included in Task 1 commit)

## Known Stubs

- `regime_adjustments: {}` — WeightFile always returns empty dict for this field. The HMM-to-weight integration (feeding regime state as modifiers into the weight file) is deferred to Plan 03 when the deploy endpoint wires LGBMTrainer + HMMRegimeDetector together.
- `wfe: None` — Walk-Forward Efficiency not computed yet; requires walk_forward.py integration (D-16/D-17), deferred to Plan 04.
- 29 reserved features (indices 14-42 + 43-46) — all zero-filled until Phase 5/6 engines provide the underlying data.

## Self-Check: PASSED

- `deep6/ml/feature_builder.py` — FOUND
- `deep6/ml/lgbm_trainer.py` — FOUND
- `deep6/ml/hmm_regime.py` — FOUND
- `deep6/ml/__init__.py` — FOUND (updated)
- Commit 879b8fd — FOUND (Task 1)
- Commit 74de0d2 — FOUND (Task 2)
