from __future__ import annotations

import logging
from collections import deque

from deep6v2.config.signals import SignalConfig
from deep6v2.signals.absorption import AbsorptionDetector
from deep6v2.signals.auction import AuctionDetector
from deep6v2.signals.delta import DeltaDetector
from deep6v2.signals.engines import (
    CounterSpoofDetector,
    IcebergDetector,
    MicroProbDetector,
    RegimeDetector,
    TrespassDetector,
    VPContextDetector,
)
from deep6v2.signals.exhaustion import ExhaustionDetector
from deep6v2.signals.imbalance import ImbalanceDetector
from deep6v2.signals.trap import TrapDetector
from deep6v2.signals.vol_patterns import VolPatternDetector
from deep6v2.types.bar import FootprintBar
from deep6v2.types.dom import DOMSnapshot
from deep6v2.types.dom_intelligence import DOMIntelligenceEvent
from deep6v2.types.interfaces import IDepthConsumingDetector, ISignalDetector
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import SignalResult

logger = logging.getLogger(__name__)

# Maximum buffered DOM intelligence events before oldest are dropped.
_MAX_DOM_EVENT_BUFFER = 500


class DOMIntelligenceAdapter:
    """Wraps DOM-intelligence detectors (returning events) into the IDepthConsumingDetector interface.

    DOM intelligence detectors have ``on_depth(DOMSnapshot) -> list[DOMIntelligenceEvent]``,
    while the registry expects ``on_depth(DOMSnapshot) -> None``.  This adapter collects
    returned events in a bounded buffer for downstream consumption.
    """

    def __init__(self, detector: object, max_events: int = _MAX_DOM_EVENT_BUFFER) -> None:
        if not hasattr(detector, "on_depth"):
            raise TypeError(
                f"{type(detector).__name__} must have an on_depth method"
            )
        # Support both detector_id (lowercase instance) and DETECTOR_ID (uppercase class)
        det_id = getattr(detector, "detector_id", None) or getattr(detector, "DETECTOR_ID", None)
        if not det_id:
            raise TypeError(
                f"{type(detector).__name__} must have detector_id or DETECTOR_ID attribute"
            )
        self._detector = detector
        self._events: deque[DOMIntelligenceEvent] = deque(maxlen=max_events)
        self.detector_id: str = det_id

    def on_depth(self, snapshot: DOMSnapshot) -> None:
        """Forward to wrapped detector, buffer returned events."""
        try:
            result = self._detector.on_depth(snapshot)
            if result:
                self._events.extend(result)
        except Exception:
            logger.debug("DOM detector %s raised during on_depth", self.detector_id, exc_info=True)

    def drain_events(self) -> list[DOMIntelligenceEvent]:
        """Return and clear all buffered events."""
        events = list(self._events)
        self._events.clear()
        return events


def _create_dom_intelligence_detectors() -> list[DOMIntelligenceAdapter]:
    """Instantiate Tier-1 mechanical DOM-intelligence detectors that consume DOMSnapshot.

    Note: CVDDetector is excluded — it uses ``update_trade()`` not ``on_depth()``,
    so it must be wired into the trade stream separately, not the depth-update path.
    The 5 snapshot-consuming detectors plus CVD (wired elsewhere) form the full 6 Tier-1 set.
    """
    from deep6v2.signals.dom.detectors.absorption import AbsorptionDOMDetector
    from deep6v2.signals.dom.detectors.iceberg import IcebergRefillDetector
    from deep6v2.signals.dom.detectors.imbalance import (
        LiquidityThinnessDetector,
        OrderBookImbalanceDetector,
    )
    from deep6v2.signals.dom.detectors.sweep_reload import SweepReloadDetector

    snapshot_detectors = [
        OrderBookImbalanceDetector(),
        LiquidityThinnessDetector(),
        AbsorptionDOMDetector(),
        SweepReloadDetector(),
        IcebergRefillDetector(),
    ]
    return [DOMIntelligenceAdapter(d) for d in snapshot_detectors]


class DetectorRegistry:
    """Sequential evaluator for signal detectors with exception isolation."""

    def __init__(
        self,
        detectors: list[ISignalDetector],
        depth_detectors: list[IDepthConsumingDetector] | None = None,
        micro_prob: MicroProbDetector | None = None,
        dom_intelligence_adapters: list[DOMIntelligenceAdapter] | None = None,
    ) -> None:
        self._detectors = detectors
        self._depth_detectors = depth_detectors or []
        self._micro_prob = micro_prob
        self._dom_adapters: list[DOMIntelligenceAdapter] = dom_intelligence_adapters or []

    @property
    def dom_intelligence_adapters(self) -> list[DOMIntelligenceAdapter]:
        return list(self._dom_adapters)

    def on_depth(self, snapshot: DOMSnapshot) -> None:
        for detector in self._depth_detectors:
            try:
                detector.on_depth(snapshot)
            except Exception:
                continue
        for adapter in self._dom_adapters:
            try:
                adapter.on_depth(snapshot)
            except Exception:
                continue

    def drain_dom_intelligence_events(self) -> list[DOMIntelligenceEvent]:
        """Drain all buffered DOM intelligence events from all adapters."""
        events: list[DOMIntelligenceEvent] = []
        for adapter in self._dom_adapters:
            events.extend(adapter.drain_events())
        return events

    def evaluate_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        results: list[SignalResult] = []
        for detector in self._detectors:
            try:
                results.extend(detector.on_bar(bar, ctx))
            except Exception:
                continue

        if self._micro_prob is not None:
            try:
                results.extend(self._micro_prob.evaluate(bar, ctx, results))
            except Exception:
                pass

        return results

    @classmethod
    def create_default(cls, config: SignalConfig | None = None) -> "DetectorRegistry":
        signal_config = config or SignalConfig()
        # Engine detectors (some implement IDepthConsumingDetector)
        iceberg = IcebergDetector(signal_config)
        trespass = TrespassDetector(signal_config)
        counter_spoof = CounterSpoofDetector(signal_config)
        vp_context = VPContextDetector(signal_config)
        regime = RegimeDetector(signal_config)
        micro_prob = MicroProbDetector(signal_config)
        # Core detectors — all 8 categories
        absorption = AbsorptionDetector(signal_config, receivers=[iceberg])
        exhaustion = ExhaustionDetector(signal_config)
        imbalance = ImbalanceDetector(signal_config)
        delta = DeltaDetector(signal_config)
        auction = AuctionDetector(signal_config)
        trap = TrapDetector(signal_config, enabled=True)
        vol_patterns = VolPatternDetector(signal_config)
        detectors: list[ISignalDetector] = [
            absorption, exhaustion, imbalance, delta, auction,
            trap, vol_patterns,
            trespass, counter_spoof, iceberg, vp_context, regime,
        ]
        depth_detectors: list[IDepthConsumingDetector] = [trespass, counter_spoof, iceberg]

        # DOM intelligence detectors — guarded by feature flag
        dom_adapters: list[DOMIntelligenceAdapter] = []
        try:
            from deep6v2.signals.dom.compat.feature_flags import is_dom_intelligence_enabled

            if is_dom_intelligence_enabled():
                dom_adapters = _create_dom_intelligence_detectors()
                logger.info("DOM intelligence enabled: %d detectors registered", len(dom_adapters))
            else:
                logger.info("DOM intelligence disabled by feature flag")
        except Exception:
            logger.warning("DOM intelligence registration failed, continuing without", exc_info=True)

        return cls(
            detectors=detectors,
            depth_detectors=depth_detectors,
            micro_prob=micro_prob,
            dom_intelligence_adapters=dom_adapters,
        )


__all__ = ["DetectorRegistry", "DOMIntelligenceAdapter"]
