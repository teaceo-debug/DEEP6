from __future__ import annotations

from collections import deque

from deep6v2.types.dom_intelligence import DOMIntelligenceEvent, DetectorTier, ReplaySafety
from deep6v2.types.signal import Direction, SignalId


class CVDDetector:
    """Cumulative volume delta detector for DOM intelligence."""

    detector_id = "dom.cvd.v1"
    tier = DetectorTier.MECHANICAL
    replay_safety = ReplaySafety.REPLAY_SAFE
    signal_id = SignalId.DELT_01

    def __init__(self, acceleration_threshold: float = 50.0, zero_cross_min_magnitude: float = 100.0) -> None:
        self.acceleration_threshold = float(acceleration_threshold)
        self.zero_cross_min_magnitude = float(zero_cross_min_magnitude)
        self._cvd = 0.0
        self._trade_index = 0
        self._session_index = 0
        self._history: list[float] = []
        self._signed_trade_history: deque[float] = deque(maxlen=3)

    def update_trade(self, volume: int, is_aggressive_buy: bool) -> list[DOMIntelligenceEvent]:
        if volume <= 0:
            return []

        signed_volume = float(volume if is_aggressive_buy else -volume)
        prior_cvd = self._cvd
        self._cvd = prior_cvd + signed_volume
        self._trade_index += 1
        self._history.append(self._cvd)
        self._signed_trade_history.append(signed_volume)

        events: list[DOMIntelligenceEvent] = []

        zero_cross_event = self._detect_zero_cross(prior_cvd, self._cvd)
        if zero_cross_event is not None:
            events.append(zero_cross_event)

        acceleration_event = self._detect_acceleration()
        if acceleration_event is not None:
            if not events or acceleration_event.metadata.get("event_type") != events[-1].metadata.get("event_type"):
                events.append(acceleration_event)

        return events

    def reset(self) -> None:
        self._cvd = 0.0
        self._trade_index = 0
        self._session_index += 1
        self._history.clear()
        self._signed_trade_history.clear()

    @property
    def current_cvd(self) -> float:
        return self._cvd

    @property
    def cvd_history(self) -> tuple[float, ...]:
        return tuple(self._history)

    def _detect_zero_cross(self, prior_cvd: float, current_cvd: float) -> DOMIntelligenceEvent | None:
        if prior_cvd < 0 <= current_cvd:
            if abs(prior_cvd) < self.zero_cross_min_magnitude:
                return None
            return self._build_event(
                direction=Direction.BULLISH,
                confidence=min(1.0, abs(prior_cvd) / (self.zero_cross_min_magnitude * 2.0)),
                event_type="zero_cross_bullish",
                magnitude=abs(current_cvd - prior_cvd),
            )

        if prior_cvd > 0 >= current_cvd:
            if abs(prior_cvd) < self.zero_cross_min_magnitude:
                return None
            return self._build_event(
                direction=Direction.BEARISH,
                confidence=min(1.0, abs(prior_cvd) / (self.zero_cross_min_magnitude * 2.0)),
                event_type="zero_cross_bearish",
                magnitude=abs(current_cvd - prior_cvd),
            )

        return None

    def _detect_acceleration(self) -> DOMIntelligenceEvent | None:
        if len(self._signed_trade_history) < 3:
            return None

        recent = tuple(self._signed_trade_history)
        if all(value > 0 for value in recent):
            window_delta = sum(recent)
            if recent[0] < recent[1] < recent[2] and window_delta >= self.acceleration_threshold:
                return self._build_event(
                    direction=Direction.BULLISH,
                    confidence=min(1.0, window_delta / (self.acceleration_threshold * 2.0)),
                    event_type="acceleration_bullish",
                    magnitude=window_delta,
                )

        if all(value < 0 for value in recent):
            window_delta = abs(sum(recent))
            if recent[0] > recent[1] > recent[2] and window_delta >= self.acceleration_threshold:
                return self._build_event(
                    direction=Direction.BEARISH,
                    confidence=min(1.0, window_delta / (self.acceleration_threshold * 2.0)),
                    event_type="acceleration_bearish",
                    magnitude=window_delta,
                )

        return None

    def _build_event(
        self,
        *,
        direction: Direction,
        confidence: float,
        event_type: str,
        magnitude: float,
    ) -> DOMIntelligenceEvent:
        return DOMIntelligenceEvent(
            signal_id=self.signal_id,
            tier=self.tier,
            replay_safety=self.replay_safety,
            direction=direction,
            confidence=confidence,
            price=0.0,
            timestamp_ns=self._trade_index,
            detector_id=self.detector_id,
            metadata={
                "event_type": event_type,
                "cvd": self._cvd,
                "magnitude": magnitude,
                "session_index": self._session_index,
            },
        )


__all__ = ["CVDDetector"]
