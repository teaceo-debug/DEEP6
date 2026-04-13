"""Feature builder for the LightGBM meta-learner.

Converts EventStore signal_events + trade_events rows into a 47-feature
numpy matrix (X) plus binary labels (y) for training.

Per D-05: 44 signal strengths + GEX regime + bar_index_in_session + Kronos bias = 47 features.
Per D-06: Target = 3-bar forward return sign (binary: win=1, loss=0).

The 29 reserved features (e1_imbalance_count … trap_count) are zero-filled
until Phase 5/6 engines are available; they are named explicitly so
LightGBM feature importance is readable from the start.
"""
from __future__ import annotations

import json
import math
from typing import Sequence

import numpy as np

# ---------------------------------------------------------------------------
# FEATURE_NAMES — ordered list of all 47 feature names
# ---------------------------------------------------------------------------
FEATURE_NAMES: list[str] = [
    # ---- 8 category binary flags (1.0 if category fired, 0.0 if not) ----
    "cat_absorption",
    "cat_exhaustion",
    "cat_trapped",
    "cat_delta",
    "cat_imbalance",
    "cat_volume_profile",
    "cat_auction",
    "cat_poc",
    # ---- 8 signal-event scalar fields ----
    "total_score",
    "engine_agreement",
    "category_count",
    "direction",            # +1 / -1 / 0 encoded as float
    "bar_index_in_session",
    "kronos_bias",
    # ---- GEX regime one-hot (2 values; NEUTRAL = both zero) ----
    "gex_positive",         # 1 if POSITIVE_DAMPENING
    "gex_negative",         # 1 if NEGATIVE_AMPLIFYING
    # ---- 29 reserved / future features (zero-filled until Phase 5/6) ----
    "e1_imbalance_count",
    "e1_stacked_tier",
    "e2_dom_imbalance",
    "e3_spoof_score",
    "e4_iceberg_count",
    "e5_micro_prob",
    "e6_vp_zone_score",
    "e7_ml_quality",
    "e8_cvd_slope",
    "e9_auction_state",
    "e10_kronos_direction",
    "atr_ratio",
    "session_vol_ratio",
    "poc_distance_ticks",
    "lvn_proximity",
    "hvn_proximity",
    "gex_wall_distance",
    "ib_position",          # 0=pre-IB, 1=in-IB, 2=post-IB
    "time_of_day_sin",      # cyclical encoding of bar_index_in_session
    "time_of_day_cos",
    "delta_abs_mean",
    "spread_proxy",
    "trade_rate_proxy",
    "bar_range_to_atr",
    "vol_surge_flag",
    "trap_count",
    "consecutive_loss_streak",
    # 4 additional reserved slots to complete the 47-feature spec
    "reserved_44",
    "reserved_45",
    "reserved_46",
    "reserved_47",
]
assert len(FEATURE_NAMES) == 47, f"Expected 47 features, got {len(FEATURE_NAMES)}"

# Category name → feature index (for fast flag insertion)
_CATEGORY_FLAG_MAP: dict[str, int] = {
    "absorption": FEATURE_NAMES.index("cat_absorption"),
    "exhaustion": FEATURE_NAMES.index("cat_exhaustion"),
    "trapped": FEATURE_NAMES.index("cat_trapped"),
    "delta": FEATURE_NAMES.index("cat_delta"),
    "imbalance": FEATURE_NAMES.index("cat_imbalance"),
    "volume_profile": FEATURE_NAMES.index("cat_volume_profile"),
    "auction": FEATURE_NAMES.index("cat_auction"),
    "poc": FEATURE_NAMES.index("cat_poc"),
}

# Feature indices for scalar fields
_IDX = {name: idx for idx, name in enumerate(FEATURE_NAMES)}

# 390 bars = full RTH session (6.5 hours at 1 min). Used for cyclical encoding.
_SESSION_BARS = 390.0


def _build_single_feature_vector(signal_row: dict) -> np.ndarray:
    """Build one 47-element float32 feature vector from a signal_events row.

    All 29 reserved features remain 0.0 until Phase 5/6 engines populate them.
    """
    vec = np.zeros(47, dtype=np.float32)

    # --- Category binary flags ---
    try:
        cats: list[str] = json.loads(signal_row.get("categories", "[]"))
    except (json.JSONDecodeError, TypeError):
        cats = []
    for cat in cats:
        if cat in _CATEGORY_FLAG_MAP:
            vec[_CATEGORY_FLAG_MAP[cat]] = 1.0

    # --- Scalar signal fields ---
    vec[_IDX["total_score"]] = float(signal_row.get("total_score") or 0.0)
    vec[_IDX["engine_agreement"]] = float(signal_row.get("engine_agreement") or 0.0)
    vec[_IDX["category_count"]] = float(signal_row.get("category_count") or 0)
    vec[_IDX["direction"]] = float(signal_row.get("direction") or 0)
    vec[_IDX["bar_index_in_session"]] = float(signal_row.get("bar_index") or 0)
    vec[_IDX["kronos_bias"]] = float(signal_row.get("kronos_bias") or 0.0)

    # --- GEX regime one-hot ---
    gex = (signal_row.get("gex_regime") or "NEUTRAL").upper()
    if gex == "POSITIVE_DAMPENING":
        vec[_IDX["gex_positive"]] = 1.0
    elif gex == "NEGATIVE_AMPLIFYING":
        vec[_IDX["gex_negative"]] = 1.0

    # --- Cyclical time-of-day encoding (using bar_index_in_session) ---
    bar_idx = float(signal_row.get("bar_index") or 0)
    angle = 2.0 * math.pi * bar_idx / _SESSION_BARS
    vec[_IDX["time_of_day_sin"]] = math.sin(angle)
    vec[_IDX["time_of_day_cos"]] = math.cos(angle)

    return vec


def build_feature_matrix(
    signal_rows: list[dict],
    trade_rows: list[dict],
    match_window_seconds: float = 180.0,  # 3 bars × 60 s
) -> tuple[np.ndarray, np.ndarray]:
    """Build feature matrix X and label vector y from EventStore rows.

    Joins signal_rows with trade_rows on nearest-ts within match_window_seconds.
    Only signals with a matched trade outcome are included (supervised learning).

    Args:
        signal_rows: list[dict] from EventStore.fetch_signal_events()
        trade_rows:  list[dict] from EventStore.fetch_trade_events()
        match_window_seconds: Maximum |ts_signal - ts_trade| for a valid match.

    Returns:
        (X, y) as float32 numpy arrays.
        X shape: (N, 47).  y shape: (N,).
        If no matches, returns (np.zeros((0, 47), float32), np.zeros((0,), float32)).
    """
    if not signal_rows or not trade_rows:
        return (
            np.zeros((0, 47), dtype=np.float32),
            np.zeros((0,), dtype=np.float32),
        )

    # Build a sorted array of (ts, pnl) for trade rows to enable binary search
    trade_ts = np.array([float(t.get("ts") or 0.0) for t in trade_rows], dtype=np.float64)
    trade_pnl = np.array([float(t.get("pnl") or 0.0) for t in trade_rows], dtype=np.float64)
    sort_idx = np.argsort(trade_ts)
    trade_ts = trade_ts[sort_idx]
    trade_pnl = trade_pnl[sort_idx]

    X_list: list[np.ndarray] = []
    y_list: list[float] = []

    for sig in signal_rows:
        sig_ts = float(sig.get("ts") or 0.0)

        # Binary search for nearest trade timestamp
        pos = int(np.searchsorted(trade_ts, sig_ts))
        best_idx: int | None = None
        best_dt = float("inf")

        for candidate in (pos - 1, pos):
            if 0 <= candidate < len(trade_ts):
                dt = abs(trade_ts[candidate] - sig_ts)
                if dt <= match_window_seconds and dt < best_dt:
                    best_dt = dt
                    best_idx = candidate

        if best_idx is None:
            continue  # No trade close enough — skip this signal row

        pnl = trade_pnl[best_idx]
        label = 1.0 if pnl > 0 else 0.0

        vec = _build_single_feature_vector(sig)
        X_list.append(vec)
        y_list.append(label)

    if not X_list:
        return (
            np.zeros((0, 47), dtype=np.float32),
            np.zeros((0,), dtype=np.float32),
        )

    X = np.stack(X_list, axis=0)  # (N, 47)
    y = np.array(y_list, dtype=np.float32)
    return X, y
