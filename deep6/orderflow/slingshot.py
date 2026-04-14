"""SlingshotDetector — TRAP_SHOT (SignalFlags bit 44) detector.

Multi-bar trapped-trader reversal pattern. 2/3/4-bar bull and bear variants.
Z-score threshold > 2.0 over session-bounded delta history. Resets at RTH
session boundary. Emits triggers_state_bypass=True when firing within
gex_proximity_ticks of a GEX wall — consumed by phase 12-04 setup state
machine to bypass DEVELOPING → TRIGGERED.

IMPORTANT — NOT to be confused with DELT_SLINGSHOT (bit 28):
  * DELT_SLINGSHOT = intra-bar compressed→explosive delta expansion
  * TRAP_SHOT      = multi-bar reversal with trapped-trader signature
  The two coexist; this module owns only bit 44.

Reference design: kronos-tv-autotrader/python/orderflow_tv.py lines 269-378,
adapted to DEEP6 conventions (session reset + z-score threshold instead of
1.5× avg magnitude; rolling history bounded; no per-signal logging noise).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import structlog

log = structlog.get_logger(__name__)


# Default parameters — tuned from 12-CONTEXT.md locked decisions.
_DEFAULT_Z_THRESHOLD = 2.0
_DEFAULT_MIN_HISTORY_BARS = 30
_DEFAULT_HISTORY_MAXLEN = 500
_DEFAULT_GEX_PROXIMITY_TICKS = 8
_SESSION_STD_WINDOW = 200


@dataclass
class SlingshotResult:
    """Detector output.

    Attributes:
        fired: True iff a valid 2/3/4-bar pattern matched above threshold.
        variant: 2, 3, or 4 when fired; else 0.
        direction: "LONG" on bull reversal, "SHORT" on bear, None when not fired.
        bias: directional conviction in [-1, 1]. Sign matches direction.
        strength: raw strength multiplier, clamped to [0, 3]. 0 when not fired.
        triggers_state_bypass: True iff fired AND within gex_proximity_ticks
            of a wall. Consumed by phase 12-04 setup state machine.
    """
    fired: bool = False
    variant: int = 0
    direction: Optional[str] = None
    bias: float = 0.0
    strength: float = 0.0
    triggers_state_bypass: bool = False


_NEUTRAL = SlingshotResult()


class SlingshotDetector:
    """Stateful per-timeframe TRAP_SHOT detector.

    One instance per timeframe (1m + 5m maintained independently by
    SharedState). Feed delta_history incrementally via update_history(bar_delta)
    on each bar close BEFORE calling detect(). Call reset_session() at the
    RTH open (9:30 ET) to avoid cross-session threshold drift.
    """

    def __init__(
        self,
        z_threshold: float = _DEFAULT_Z_THRESHOLD,
        min_history_bars: int = _DEFAULT_MIN_HISTORY_BARS,
        history_maxlen: int = _DEFAULT_HISTORY_MAXLEN,
        gex_proximity_ticks: int = _DEFAULT_GEX_PROXIMITY_TICKS,
    ) -> None:
        self.z_threshold = float(z_threshold)
        self.min_history_bars = int(min_history_bars)
        self.history_maxlen = int(history_maxlen)
        self.gex_proximity_ticks = int(gex_proximity_ticks)
        self.delta_history: deque[int] = deque(maxlen=self.history_maxlen)

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------
    def update_history(self, bar_delta: int) -> None:
        """Append one bar's bar_delta to the rolling session history.

        Call on each bar close BEFORE detect(). The deque is bounded by
        history_maxlen — older samples age out automatically.
        """
        self.delta_history.append(int(bar_delta))

    def reset_session(self) -> None:
        """Clear delta_history at RTH session boundary (9:30 ET).

        Without this reset the first 30 bars of a new session compute their
        threshold against overnight-mixed history, producing a biased σ and
        spurious fires. See 12-CONTEXT.md FOOTGUN 2.
        """
        self.delta_history.clear()

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------
    def detect(
        self,
        bars: Sequence,
        gex_distance_ticks: Optional[float],
    ) -> SlingshotResult:
        """Run 2/3/4-bar variant checks and return the first match.

        Args:
            bars: tail of most-recent bars, chronological. Each bar must
                expose ``open``, ``high``, ``low``, ``close``, ``bar_delta``.
                Minimum 2 bars required for any fire.
            gex_distance_ticks: distance in ticks to nearest GEX wall, or
                None if GEX context unavailable. Used only to set
                triggers_state_bypass.

        Returns:
            Neutral SlingshotResult when warmup incomplete, no bars, or no
            pattern; otherwise a fired result with variant 2/3/4.
        """
        # Warmup gate
        if len(self.delta_history) < self.min_history_bars:
            return _NEUTRAL

        if bars is None or len(bars) < 2:
            return _NEUTRAL

        # Rolling-window σ over the current session's history.
        window = list(self.delta_history)[-_SESSION_STD_WINDOW:]
        sigma = float(np.std(window))
        # Degenerate case: flat history → no threshold meaningful.
        if sigma <= 0.0:
            return _NEUTRAL
        threshold = self.z_threshold * sigma

        # Prefer the LONGEST matching variant (more bars ⇒ stronger structure).
        for variant_fn in (self._check_4bar, self._check_3bar, self._check_2bar):
            result = variant_fn(bars, threshold)
            if result is not None:
                return self._apply_gex_bypass(result, gex_distance_ticks)
        return _NEUTRAL

    # ------------------------------------------------------------------
    # Variant checks
    # ------------------------------------------------------------------
    def _check_2bar(self, bars: Sequence, threshold: float) -> Optional[SlingshotResult]:
        if len(bars) < 2:
            return None
        b2, b1 = bars[-2], bars[-1]

        # Bullish 2-bar
        if (b2.close < b2.open
                and b2.bar_delta < -threshold
                and b1.close > b1.open
                and b1.close > b2.high
                and b1.bar_delta > threshold):
            strength = min(abs(b1.bar_delta) / max(abs(b2.bar_delta), 1), 3.0)
            return SlingshotResult(
                fired=True, variant=2, direction="LONG",
                bias=min(0.6 * strength / 2, 1.0),
                strength=round(strength, 2),
            )
        # Bearish 2-bar
        if (b2.close > b2.open
                and b2.bar_delta > threshold
                and b1.close < b1.open
                and b1.close < b2.low
                and b1.bar_delta < -threshold):
            strength = min(abs(b1.bar_delta) / max(abs(b2.bar_delta), 1), 3.0)
            return SlingshotResult(
                fired=True, variant=2, direction="SHORT",
                bias=max(-0.6 * strength / 2, -1.0),
                strength=round(strength, 2),
            )
        return None

    def _check_3bar(self, bars: Sequence, threshold: float) -> Optional[SlingshotResult]:
        if len(bars) < 3:
            return None
        b3, b2, b1 = bars[-3], bars[-2], bars[-1]

        # Bullish 3-bar: b3 bearish-extreme, b2 consolidates below, b1 breakout.
        if (b3.close < b3.open
                and b3.bar_delta < -threshold
                and b2.high <= b3.high
                and b1.close > b1.open
                and b1.close > b3.high
                and b1.bar_delta > threshold * 0.8):
            strength = min(abs(b1.bar_delta) / max(abs(b3.bar_delta), 1), 3.0)
            return SlingshotResult(
                fired=True, variant=3, direction="LONG",
                bias=min(0.7 * strength / 2, 1.0),
                strength=round(strength, 2),
            )
        # Bearish 3-bar
        if (b3.close > b3.open
                and b3.bar_delta > threshold
                and b2.low >= b3.low
                and b1.close < b1.open
                and b1.close < b3.low
                and b1.bar_delta < -threshold * 0.8):
            strength = min(abs(b1.bar_delta) / max(abs(b3.bar_delta), 1), 3.0)
            return SlingshotResult(
                fired=True, variant=3, direction="SHORT",
                bias=max(-0.7 * strength / 2, -1.0),
                strength=round(strength, 2),
            )
        return None

    def _check_4bar(self, bars: Sequence, threshold: float) -> Optional[SlingshotResult]:
        if len(bars) < 4:
            return None
        b4 = bars[-4]
        mid = bars[-3:-1]
        b1 = bars[-1]

        # Bullish 4-bar
        if (b4.close < b4.open
                and b4.bar_delta < -threshold
                and all(b.high <= b4.high for b in mid)
                and b1.close > b4.high
                and b1.bar_delta > threshold * 0.6):
            strength = min(abs(b1.bar_delta) / max(abs(b4.bar_delta), 1), 3.0)
            return SlingshotResult(
                fired=True, variant=4, direction="LONG",
                bias=min(0.8 * strength / 2, 1.0),
                strength=round(strength, 2),
            )
        # Bearish 4-bar
        if (b4.close > b4.open
                and b4.bar_delta > threshold
                and all(b.low >= b4.low for b in mid)
                and b1.close < b4.low
                and b1.bar_delta < -threshold * 0.6):
            strength = min(abs(b1.bar_delta) / max(abs(b4.bar_delta), 1), 3.0)
            return SlingshotResult(
                fired=True, variant=4, direction="SHORT",
                bias=max(-0.8 * strength / 2, -1.0),
                strength=round(strength, 2),
            )
        return None

    # ------------------------------------------------------------------
    # GEX-bypass coupling
    # ------------------------------------------------------------------
    def _apply_gex_bypass(
        self,
        result: SlingshotResult,
        gex_distance_ticks: Optional[float],
    ) -> SlingshotResult:
        """Set triggers_state_bypass iff firing AND within GEX-wall proximity."""
        bypass = (
            result.fired
            and gex_distance_ticks is not None
            and gex_distance_ticks < self.gex_proximity_ticks
        )
        if bypass == result.triggers_state_bypass:
            return result
        # Return a copy with the bypass flag set; SlingshotResult is a dataclass
        # so we can reuse all other fields.
        return SlingshotResult(
            fired=result.fired,
            variant=result.variant,
            direction=result.direction,
            bias=result.bias,
            strength=result.strength,
            triggers_state_bypass=bypass,
        )
