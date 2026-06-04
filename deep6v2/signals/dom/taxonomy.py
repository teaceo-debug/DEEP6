from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

try:
    from deep6v2.types.dom_intelligence import DetectorTier, ReplaySafety
except ImportError:  # TODO: import from deep6v2.types.dom_intelligence once Task 1 lands.
    class DetectorTier(str, Enum):
        MECHANICAL = "MECHANICAL"
        HEURISTIC = "HEURISTIC"
        DISCRETIONARY_OVERLAY = "DISCRETIONARY_OVERLAY"


    class ReplaySafety(str, Enum):
        REPLAY_SAFE = "REPLAY_SAFE"
        LIVE_ONLY = "LIVE_ONLY"
        REPLAY_DEGRADED = "REPLAY_DEGRADED"


@dataclass(frozen=True)
class DetectorClassification:
    detector_id: str
    name: str
    tier: DetectorTier
    replay_safety: ReplaySafety
    description: str
    first_release: bool


DETECTOR_TAXONOMY: dict[str, DetectorClassification] = {
    "dom.imbalance.v1": DetectorClassification(
        detector_id="dom.imbalance.v1",
        name="Order book imbalance detector",
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        description="Detects aggressive bid/ask imbalance at the DOM and footprint level.",
        first_release=True,
    ),
    "dom.absorption.v1": DetectorClassification(
        detector_id="dom.absorption.v1",
        name="Absorption at resting levels",
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        description="Identifies repeated aggression into resting liquidity that does not dislodge price.",
        first_release=True,
    ),
    "dom.sweep_reload.v1": DetectorClassification(
        detector_id="dom.sweep_reload.v1",
        name="Sweep + reload pattern",
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        description="Captures sweep-through behavior followed by immediate replenishment or reload.",
        first_release=True,
    ),
    "dom.iceberg.v1": DetectorClassification(
        detector_id="dom.iceberg.v1",
        name="Iceberg/refill detection",
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        description="Detects hidden liquidity via refill behavior and persistent resting size.",
        first_release=True,
    ),
    "dom.cvd.v1": DetectorClassification(
        detector_id="dom.cvd.v1",
        name="Cumulative volume delta",
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        description="Tracks cumulative aggressive buy/sell pressure over time.",
        first_release=True,
    ),
    "dom.thinness.v1": DetectorClassification(
        detector_id="dom.thinness.v1",
        name="Liquidity thinness / depth asymmetry",
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        description="Measures asymmetric book depth and thin liquidity conditions that amplify move risk.",
        first_release=True,
    ),
    "dom.pull_replace.v1": DetectorClassification(
        detector_id="dom.pull_replace.v1",
        name="Pull/replace trap heuristic",
        tier=DetectorTier.HEURISTIC,
        replay_safety=ReplaySafety.REPLAY_DEGRADED,
        description="Heuristic for deceptive pulling and replacing of liquidity requiring calibration.",
        first_release=True,
    ),
    "dom.micro_momentum.v1": DetectorClassification(
        detector_id="dom.micro_momentum.v1",
        name="Micro-momentum features",
        tier=DetectorTier.HEURISTIC,
        replay_safety=ReplaySafety.REPLAY_DEGRADED,
        description="Short-horizon momentum features derived from microstructure state.",
        first_release=True,
    ),
    "dom.large_burst.v1": DetectorClassification(
        detector_id="dom.large_burst.v1",
        name="Large trade burst",
        tier=DetectorTier.HEURISTIC,
        replay_safety=ReplaySafety.REPLAY_DEGRADED,
        description="Detects concentrated bursts of large trade activity that may require calibration.",
        first_release=True,
    ),
    "dom.micro_vol.v1": DetectorClassification(
        detector_id="dom.micro_vol.v1",
        name="Micro-vol ratio",
        tier=DetectorTier.HEURISTIC,
        replay_safety=ReplaySafety.REPLAY_DEGRADED,
        description="Compares short-window realized volatility against local baseline behavior.",
        first_release=True,
    ),
    "dom.tps.v1": DetectorClassification(
        detector_id="dom.tps.v1",
        name="Trades-per-second intensity",
        tier=DetectorTier.HEURISTIC,
        replay_safety=ReplaySafety.REPLAY_DEGRADED,
        description="Tracks execution intensity via trades-per-second to gauge activity surges.",
        first_release=True,
    ),
    "dom.stacked_imbalance.v1": DetectorClassification(
        detector_id="dom.stacked_imbalance.v1",
        name="Stacked imbalance visual",
        tier=DetectorTier.DISCRETIONARY_OVERLAY,
        replay_safety=ReplaySafety.LIVE_ONLY,
        description="Operator-side stacked imbalance interpretation intended for live visual context only.",
        first_release=False,
    ),
    "dom.wall_persistence.v1": DetectorClassification(
        detector_id="dom.wall_persistence.v1",
        name="Wall persistence by feel",
        tier=DetectorTier.DISCRETIONARY_OVERLAY,
        replay_safety=ReplaySafety.LIVE_ONLY,
        description="Discretionary assessment of how long walls persist and how they are defended.",
        first_release=False,
    ),
    "dom.failed_auction.v1": DetectorClassification(
        detector_id="dom.failed_auction.v1",
        name="Failed auction interpretation",
        tier=DetectorTier.DISCRETIONARY_OVERLAY,
        replay_safety=ReplaySafety.LIVE_ONLY,
        description="Human interpretation of failed auction structure used as a discretionary overlay.",
        first_release=False,
    ),
    "dom.queue_nuance.v1": DetectorClassification(
        detector_id="dom.queue_nuance.v1",
        name="Queue nuance setup",
        tier=DetectorTier.DISCRETIONARY_OVERLAY,
        replay_safety=ReplaySafety.LIVE_ONLY,
        description="Discretionary queue-position and refill nuance requiring live context.",
        first_release=False,
    ),
    "dom.regime_shift.v1": DetectorClassification(
        detector_id="dom.regime_shift.v1",
        name="Regime-shift judgment",
        tier=DetectorTier.DISCRETIONARY_OVERLAY,
        replay_safety=ReplaySafety.LIVE_ONLY,
        description="Operator judgment for regime transition confirmation, not replay-safe logic.",
        first_release=False,
    ),
}


def _filter_by(predicate: callable) -> list[DetectorClassification]:
    return [item for item in DETECTOR_TAXONOMY.values() if predicate(item)]


def get_mechanical_detectors() -> list[DetectorClassification]:
    return _filter_by(lambda item: item.tier is DetectorTier.MECHANICAL)


def get_heuristic_detectors() -> list[DetectorClassification]:
    return _filter_by(lambda item: item.tier is DetectorTier.HEURISTIC)


def get_first_release_detectors() -> list[DetectorClassification]:
    return _filter_by(lambda item: item.first_release)


def get_replay_safe_detectors() -> list[DetectorClassification]:
    return _filter_by(lambda item: item.replay_safety is ReplaySafety.REPLAY_SAFE)


__all__ = [
    "DETECTOR_TAXONOMY",
    "DetectorClassification",
    "DetectorTier",
    "ReplaySafety",
    "get_first_release_detectors",
    "get_heuristic_detectors",
    "get_mechanical_detectors",
    "get_replay_safe_detectors",
]
