"""Heuristic feature-row builder for the DOM Intelligence Layer.

Assembles Tier-2 detector outputs (from DOMIntelligenceOutput) into
ML-ready feature vectors (DOMIntelligenceFeatureRow). The FEATURE_NAMES
list is an API contract — order and names MUST NOT change between versions.

Missing features default to 0.0 (not NaN) to keep downstream ML pipelines
clean without imputation steps.

Pattern reference: deep6/ml/depth_radar/wall_features.py (WallFeatureExtractor).
"""

from __future__ import annotations

import numpy as np

from deep6v2.types.dom import DOMSnapshot
from deep6v2.types.dom_intelligence import (
    DOMIntelligenceEvent,
    DOMIntelligenceFeatureRow,
    DOMIntelligenceOutput,
    DetectorTier,
)

# ---------------------------------------------------------------------------
# FEATURE_NAMES — stable ordered list (API CONTRACT — DO NOT REORDER)
# ---------------------------------------------------------------------------
FEATURE_NAMES: list[str] = [
    # Imbalance features (from Tier-1 mechanical detectors — always present)
    "bid_ask_imbalance_ratio",  # bid_vol / ask_vol at top 5 levels
    "depth_asymmetry_score",  # (bid_depth - ask_depth) / (bid_depth + ask_depth)
    "book_thinness",  # total_volume / avg_volume_20bar
    # CVD features
    "cvd_value",  # current cumulative delta value
    "cvd_acceleration",  # rate of change of CVD over last 3 snapshots
    # Heuristic features (Tier-2 — may be 0.0 if not computed)
    "pull_replace_ratio",  # cancel/replace events per unit time
    "micro_momentum",  # price velocity over last N snapshots
    "large_burst_count",  # number of large trades in window
    "micro_vol_ratio",  # realized vol / baseline vol
    "tps_intensity",  # trades per second intensity score
]
assert len(FEATURE_NAMES) == 10, f"Expected 10 features, got {len(FEATURE_NAMES)}"

NUM_FEATURES = len(FEATURE_NAMES)

# Feature indices for direct access
_IDX: dict[str, int] = {name: idx for idx, name in enumerate(FEATURE_NAMES)}

# Detector ID → feature name mapping for event-based extraction
_DETECTOR_FEATURE_MAP: dict[str, list[str]] = {
    "dom.imbalance.v1": ["bid_ask_imbalance_ratio", "depth_asymmetry_score", "book_thinness"],
    "dom.thinness.v1": ["depth_asymmetry_score", "book_thinness"],
    "dom.cvd.v1": ["cvd_value", "cvd_acceleration"],
    "dom.pull_replace.v1": ["pull_replace_ratio"],
    "dom.micro_momentum.v1": ["micro_momentum"],
    "dom.large_burst.v1": ["large_burst_count"],
    "dom.micro_vol.v1": ["micro_vol_ratio"],
    "dom.tps.v1": ["tps_intensity"],
}


def get_feature_names() -> list[str]:
    """Return ordered list of feature names for column labeling."""
    return list(FEATURE_NAMES)


def _extract_imbalance_features(snapshot: DOMSnapshot) -> dict[str, float]:
    """Extract mechanical imbalance features from a DOM snapshot."""
    top_n = 5
    bid_vols = [float(lvl.volume) for lvl in snapshot.bids[:top_n]]
    ask_vols = [float(lvl.volume) for lvl in snapshot.asks[:top_n]]

    bid_sum = sum(bid_vols)
    ask_sum = sum(ask_vols)
    total = bid_sum + ask_sum

    imbalance_ratio = (bid_sum / ask_sum) if ask_sum > 0 else 0.0
    asymmetry = (bid_sum - ask_sum) / total if total > 0 else 0.0

    # Book thinness: total depth at top 5 (raw — normalized downstream)
    thinness = total

    return {
        "bid_ask_imbalance_ratio": imbalance_ratio,
        "depth_asymmetry_score": asymmetry,
        "book_thinness": thinness,
    }


def _extract_event_feature(event: DOMIntelligenceEvent) -> dict[str, float]:
    """Extract feature values from a single event's metadata."""
    features: dict[str, float] = {}
    detector_id = event.detector_id
    mapped_names = _DETECTOR_FEATURE_MAP.get(detector_id, [])

    for name in mapped_names:
        # Pull from event.metadata if present, else use confidence as proxy
        val = event.metadata.get(name)
        if val is not None:
            features[name] = float(val)
        elif name in ("cvd_value", "cvd_acceleration"):
            features[name] = event.metadata.get(name, 0.0)
        elif name in ("pull_replace_ratio", "micro_momentum", "large_burst_count",
                       "micro_vol_ratio", "tps_intensity"):
            # For heuristic features, check metadata with fallback to confidence
            features[name] = float(event.metadata.get("value", event.confidence))

    return features


class DOMFeatureBuilder:
    """Assembles DOM intelligence events + metrics into ML-ready feature rows.

    Follows the WallFeatureExtractor pattern: stable feature vector with
    deterministic ordering, 0.0 sentinel for missing data, numpy float64 output.
    """

    def build(
        self,
        output: DOMIntelligenceOutput,
        snapshot: DOMSnapshot,
        bar_index: int,
        session_id: str,
    ) -> DOMIntelligenceFeatureRow:
        """Extract feature vector from DOMIntelligenceOutput.

        Missing features default to 0.0 (not NaN) to avoid downstream
        imputation complexity.

        Args:
            output: Aggregated detector output with events.
            snapshot: Current DOM state for mechanical feature extraction.
            bar_index: Current bar index for row metadata.
            session_id: Session identifier for row metadata.

        Returns:
            DOMIntelligenceFeatureRow with stable feature ordering.
        """
        vec = np.zeros(NUM_FEATURES, dtype=np.float64)
        source_detector_ids: list[str] = []

        # --- Phase 1: Mechanical features from DOM snapshot ---
        imbalance_features = _extract_imbalance_features(snapshot)
        for name, val in imbalance_features.items():
            if name in _IDX:
                vec[_IDX[name]] = val

        # --- Phase 2: Event-sourced features ---
        for event in output.events:
            if event.detector_id not in source_detector_ids:
                source_detector_ids.append(event.detector_id)

            event_features = _extract_event_feature(event)
            for name, val in event_features.items():
                if name in _IDX:
                    # For multiple events from same detector, take max magnitude
                    existing = vec[_IDX[name]]
                    if abs(val) > abs(existing):
                        vec[_IDX[name]] = val

        # --- Build the row ---
        timestamp_ns = output.evaluated_at_ns
        if timestamp_ns == 0 and output.events:
            timestamp_ns = output.events[0].timestamp_ns

        return DOMIntelligenceFeatureRow(
            timestamp_ns=timestamp_ns,
            feature_names=list(FEATURE_NAMES),
            feature_values=vec,
            bar_index=bar_index,
            session_id=session_id,
            source_detector_ids=source_detector_ids,
        )


__all__ = [
    "FEATURE_NAMES",
    "NUM_FEATURES",
    "DOMFeatureBuilder",
    "get_feature_names",
]
