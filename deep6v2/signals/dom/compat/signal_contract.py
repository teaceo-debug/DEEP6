"""Formal compatibility contract for DOM-intelligence signal migration.

This module freezes how DOM-intelligence detector outputs may touch the existing
SignalId, SignalCategory, scorer, and entry-gate pipeline during MVP.

Compatibility rule: DOM detectors may emit feature rows freely, but any scored
signal must reuse an existing ``SignalId`` from ``deep6v2.types.signal``.
"""

from __future__ import annotations

from deep6v2.types.signal import SIGNAL_TO_CATEGORY, SignalCategory, SignalId

MVP_NEW_SIGNAL_IDS_ALLOWED: bool = False
"""
MVP Policy: DOM-intelligence detectors in V1 MUST reuse existing SignalId values
from deep6v2.types.signal. No new SignalId values may be added in MVP.

Rationale: Adding new SignalId values would require scorer weight tables,
entry gate policy updates, and backtesting dataset labels — all out of scope for MVP.

Mapping strategy: Each DOM detector maps its DOMIntelligenceEvent to an existing
SignalId that semantically matches its detection pattern.
"""


DOM_DETECTOR_TO_SIGNAL_ID: dict[str, SignalId | None] = {
    # Tier 1 Mechanical — scored in MVP by reusing existing SignalId families.
    "dom.imbalance.v1": SignalId.IMB_01,
    "dom.absorption.v1": SignalId.ABS_01,
    "dom.sweep_reload.v1": SignalId.ABS_02,
    "dom.iceberg.v1": SignalId.ENG_04,
    "dom.cvd.v1": SignalId.DELT_01,
    "dom.thinness.v1": SignalId.IMB_02,
    # Tier 2 Heuristic — feature rows only in MVP.
    "dom.pull_replace.v1": None,
    "dom.micro_momentum.v1": None,
    "dom.large_burst.v1": None,
    "dom.micro_vol.v1": None,
    "dom.tps.v1": None,
    # Tier 3 Discretionary overlay — out of scored MVP scope.
    "dom.stacked_imbalance.v1": None,
    "dom.wall_persistence.v1": None,
    "dom.failed_auction.v1": None,
    "dom.queue_nuance.v1": None,
    "dom.regime_shift.v1": None,
}


DOM_DETECTOR_COMPATIBILITY_RULES: dict[str, str] = {
    "dom.imbalance.v1": (
        "Reuse SignalId.IMB_01 so ConfluenceScorer continues to treat DOM order-book imbalance "
        "as an existing imbalance-category input with no new scorer table entries."
    ),
    "dom.absorption.v1": (
        "Reuse SignalId.ABS_01 so resting-liquidity absorption remains an absorption-category input "
        "already understood by scorer weighting and entry-gate absorption checks."
    ),
    "dom.sweep_reload.v1": (
        "Reuse SignalId.ABS_02 because sweep-then-reload is operationally closest to absorption/defense "
        "behavior and therefore must stay inside the existing absorption family in MVP."
    ),
    "dom.iceberg.v1": (
        "Reuse SignalId.ENG_04, the existing engine-level iceberg/refill-compatible ID already categorized "
        "as absorption, avoiding any new category or gate semantics."
    ),
    "dom.cvd.v1": (
        "Reuse SignalId.DELT_01 so DOM cumulative volume delta flows through the existing delta bucket and "
        "inherits current ConfluenceScorer delta weighting."
    ),
    "dom.thinness.v1": (
        "Reuse SignalId.IMB_02 so liquidity thinness / depth asymmetry is represented as an imbalance-family "
        "signal instead of introducing a new category."
    ),
    "dom.pull_replace.v1": (
        "Map to None in MVP: heuristic pull/replace behavior is feature-row only and must not emit a scored "
        "SignalId until replay evidence justifies registry/scorer changes."
    ),
    "dom.micro_momentum.v1": (
        "Map to None in MVP: short-horizon micro-momentum remains a heuristic feature generator only."
    ),
    "dom.large_burst.v1": (
        "Map to None in MVP: large-trade burst output may inform future models but is not a scored signal in MVP."
    ),
    "dom.micro_vol.v1": (
        "Map to None in MVP: micro-volatility ratio stays feature-only to prevent unvalidated scorer drift."
    ),
    "dom.tps.v1": (
        "Map to None in MVP: trades-per-second intensity is recorded for features and parity audits, not scoring."
    ),
    "dom.stacked_imbalance.v1": (
        "Map to None in MVP: discretionary stacked-imbalance interpretation is live visual context only."
    ),
    "dom.wall_persistence.v1": (
        "Map to None in MVP: wall-persistence-by-feel is an operator overlay and must not affect scorer inputs."
    ),
    "dom.failed_auction.v1": (
        "Map to None in MVP: failed-auction interpretation remains discretionary and outside replay-safe scoring."
    ),
    "dom.queue_nuance.v1": (
        "Map to None in MVP: queue nuance is overlay-only and cannot mutate entry semantics in MVP."
    ),
    "dom.regime_shift.v1": (
        "Map to None in MVP: discretionary regime-shift judgment is out of scope for scored pipeline integration."
    ),
}


DOM_SIGNAL_TO_CATEGORY: dict[str, SignalCategory] = {
    detector_id: SIGNAL_TO_CATEGORY[signal_id]
    for detector_id, signal_id in DOM_DETECTOR_TO_SIGNAL_ID.items()
    if signal_id is not None and SIGNAL_TO_CATEGORY[signal_id] is not None
}


DOM_ENTRY_GATE_POLICY = """
DOM-intelligence signals in MVP follow this entry_gate.py treatment:

1. REPLAY_SAFE Tier-1 signals: Eligible for entry gating after replaying golden sessions
   and verifying output matches live parity within defined tolerances.

2. REPLAY_DEGRADED Tier-2 signals: NOT eligible for entry gating in MVP.
   They produce feature rows for future ML training only.

3. LIVE_ONLY Tier-3 signals: NOT eligible for entry gating in MVP.
   Visual overlay only.

4. No new DOM-specific SignalId values may be routed into EntryGate.evaluate() in MVP.
   Only the reused SignalId values listed in DOM_DETECTOR_TO_SIGNAL_ID may participate,
   which means existing _ABSORPTION_IDS, _CORE_IDS, SIGNAL_TO_CATEGORY lookups, and
   category-agreement logic remain the sole source of gating semantics.
""".strip()


ROLLBACK_RULE = """
If DOM-intelligence signals cause scorer drift or parity violations:
- Feature flag: set DOM_INTELLIGENCE_ENABLED=False in environment to disable all DOM detector registration.
- The existing DetectorRegistry.create_default() factory must check this flag before registering DOM detectors.
- When disabled, registry behaves exactly as before — zero impact on existing signal/scorer pipeline.
- This rollback preserves the old path as the production truth until parity and scorer drift are resolved.
""".strip()


__all__ = [
    "DOM_DETECTOR_COMPATIBILITY_RULES",
    "DOM_DETECTOR_TO_SIGNAL_ID",
    "DOM_ENTRY_GATE_POLICY",
    "DOM_SIGNAL_TO_CATEGORY",
    "MVP_NEW_SIGNAL_IDS_ALLOWED",
    "ROLLBACK_RULE",
]
