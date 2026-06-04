"""ICT session-structure bias domain for v3 composition."""
from __future__ import annotations

import time
from typing import Optional

from deep6.bias_engine.models import JudasStatus, PO3BiasState
from deep6.engines.bias_contracts import DomainScore
from deep6.engines.signal_config import SessionBiasConfig


class ICTSessionDomain:
    """Scores bias from PO3 session-structure outputs.

    Components (each +/-1, total +/-4):
    1. Price vs Midnight Open
    2. Price vs Weekly Open
    3. Judas swing confirmation
    4. Premium/Discount zone

    Components with unknown source fields reduce ``max_range`` instead of forcing
    a directional penalty. ``available`` is only false when the entire PO3 state
    is missing.
    """

    MAX_RANGE = 4
    DOMAIN = "ict"

    def __init__(self, config: Optional[SessionBiasConfig] = None) -> None:
        self._config = config or SessionBiasConfig()

    def compute(self, po3_state: Optional[PO3BiasState]) -> DomainScore:
        """Translate ``PO3BiasState`` into a v3 ``DomainScore``."""
        if po3_state is None:
            return DomainScore(
                domain=self.DOMAIN,
                score=0,
                max_range=0,
                available=False,
                stale=False,
                detail={"reason": "po3_state_missing"},
            )

        now = time.time()
        state_ts = po3_state.timestamp.timestamp()
        stale = (now - state_ts) > self._config.stale_threshold_sec

        score = 0
        max_range = self.MAX_RANGE
        detail = {
            "midnight_open": {"available": po3_state.above_midnight_open is not None, "score": 0},
            "weekly_open": {"available": po3_state.above_weekly_open is not None, "score": 0},
            "judas": {"available": po3_state.judas_status is not None, "score": 0},
            "premium_discount": {"available": po3_state.in_discount is not None, "score": 0},
        }

        if po3_state.above_midnight_open is None:
            max_range -= 1
        else:
            component_score = 1 if po3_state.above_midnight_open else -1
            score += component_score
            detail["midnight_open"]["score"] = component_score
            detail["midnight_open"]["value"] = po3_state.above_midnight_open

        if po3_state.above_weekly_open is None:
            max_range -= 1
        else:
            component_score = 1 if po3_state.above_weekly_open else -1
            score += component_score
            detail["weekly_open"]["score"] = component_score
            detail["weekly_open"]["value"] = po3_state.above_weekly_open

        if po3_state.judas_status is None:
            max_range -= 1
        elif po3_state.judas_status is JudasStatus.BULL_CONFIRMED:
            score += 1
            detail["judas"]["score"] = 1
            detail["judas"]["value"] = po3_state.judas_status.value
        elif po3_state.judas_status is JudasStatus.BEAR_CONFIRMED:
            score -= 1
            detail["judas"]["score"] = -1
            detail["judas"]["value"] = po3_state.judas_status.value
        else:
            detail["judas"]["value"] = po3_state.judas_status.value

        if po3_state.in_discount is None:
            max_range -= 1
        else:
            component_score = 1 if po3_state.in_discount else -1
            score += component_score
            detail["premium_discount"]["score"] = component_score
            detail["premium_discount"]["value"] = po3_state.in_discount

        detail["age_sec"] = max(0.0, now - state_ts)

        return DomainScore(
            domain=self.DOMAIN,
            score=max(-self.MAX_RANGE, min(self.MAX_RANGE, score)),
            max_range=max(0, max_range),
            available=True,
            stale=stale,
            detail=detail,
            updated_at=state_ts,
        )


__all__ = ["ICTSessionDomain"]
