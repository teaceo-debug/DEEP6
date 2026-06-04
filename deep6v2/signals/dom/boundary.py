"""Static integration boundary for the SuperDOM Intelligence Layer.

This module is documentation-as-code: it captures the only approved coupling
points between `deep6v2.signals.dom` and the rest of DEEP6 so tests can guard
the architecture without instantiating live transports or detector logic.
"""

from __future__ import annotations

APPROVED_IMPORTS: dict[str, list[str]] = {
    "deep6v2.types.dom": ["DOMLevel", "DOMSnapshot", "DOMUpdate"],
    "deep6v2.types.dom_intelligence": [
        "DOMIntelligenceEvent",
        "DetectorTier",
        "ReplaySafety",
        "DOMIntelligenceOutput",
    ],
    "deep6v2.types.interfaces": ["ISignalDetector", "IDepthConsumingDetector"],
    "deep6v2.types.signal": ["SignalId", "SignalCategory", "Direction"],
    "deep6v2.state.dom": ["DOMState"],
    "deep6v2.signals.dom.taxonomy": ["DetectorClassification", "DETECTOR_TAXONOMY"],
    "deep6.ml.depth_radar.wall_features": ["WallFeatureExtractor"],
    "deep6.ml.depth_radar.classifier": ["WallClassifier"],
}

FORBIDDEN_IMPORTS: dict[str, str] = {
    "dashboard -> deep6v2.signals.dom.*": "UI must consume structured state only, never detector logic",
    "deep6v2.signals.dom.* -> deep6v2.data.rithmic_client": (
        "DOM detectors receive DOMSnapshot — they do not connect to Rithmic directly. Use the live adapter."
    ),
    "DOMState() in deep6v2.signals.dom.*": (
        "Must consume deep6v2.state.dom.DOMState — do not instantiate a parallel DOMState or shadow copy"
    ),
}

INTEGRATION_RULES: list[str] = [
    "RULE-1: deep6v2/signals/dom/ detectors implement ISignalDetector or IDepthConsumingDetector",
    "RULE-2: All detectors register via DetectorRegistry.create_default() in registry.py",
    "RULE-3: DOM state flows through deep6v2/state/dom.py — no parallel DOMState",
    "RULE-4: Live adapter wraps RithmicClient — does not replace it",
    "RULE-5: Replay adapter wraps ReplayEngine — does not replace it",
    "RULE-6: depth-radar (V1) may be optionally imported for feature reuse — not required",
    "RULE-7: Dashboard components consume structured state (SSE/WebSocket) — no detector imports",
    "RULE-8: Tier 3 DISCRETIONARY_OVERLAY detectors are visual only — not scored in V1",
]

__all__ = ["APPROVED_IMPORTS", "FORBIDDEN_IMPORTS", "INTEGRATION_RULES"]
