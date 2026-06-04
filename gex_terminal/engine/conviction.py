"""5-river conviction matrix — scores multi-source agreement for trade quality."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConvictionResult:
    """Result of multi-river conviction scoring."""

    grade: str
    rivers_agreeing: int
    rivers_total: int
    stand_aside: bool


class ConvictionScorer:
    """Scores 5-river agreement to produce conviction grade."""

    _BULLISH = {"BULLISH", "BULL", "STRONG_BULL", "positive", "bullish", "buying"}
    _BEARISH = {"BEARISH", "BEAR", "STRONG_BEAR", "negative", "bearish", "selling"}

    def score(
        self,
        *,
        gex_direction: str,
        flow_direction: str,
        vanna_charm_direction: str,
        dark_pool_direction: str,
        hmm_state: str,
        overall_direction: str,
    ) -> ConvictionResult:
        """Count how many rivers agree with the scored direction."""
        target = self._normalize_direction(overall_direction)
        if target == "NEUTRAL":
            return ConvictionResult("C", 0, 0, True)

        rivers: list[bool] = []

        gex = self._normalize_direction(gex_direction)
        if gex != "NEUTRAL":
            rivers.append(gex == target)

        flow = self._normalize_direction(flow_direction)
        if flow != "NEUTRAL":
            rivers.append(flow == target)

        vanna_charm = (vanna_charm_direction or "neutral").lower()
        if vanna_charm == "tailwind":
            rivers.append(target == "BULLISH")
        elif vanna_charm == "headwind":
            rivers.append(target == "BEARISH")

        dark_pool = self._normalize_direction(dark_pool_direction)
        if dark_pool != "NEUTRAL":
            rivers.append(dark_pool == target)

        hmm = (hmm_state or "UNKNOWN").upper()
        if hmm == "ABSORPTION_FRIENDLY":
            rivers.append(True)
        elif hmm == "CHAOTIC":
            rivers.append(False)

        agreeing = sum(1 for river in rivers if river)
        total = len(rivers)
        if total == 0:
            return ConvictionResult("C", 0, 0, True)

        ratio = agreeing / total
        if agreeing >= 5 or ratio >= 0.9:
            grade = "A+"
        elif agreeing >= 4 or ratio >= 0.75:
            grade = "A"
        elif agreeing >= 3 or ratio >= 0.6:
            grade = "B"
        elif agreeing >= 2 or ratio >= 0.4:
            grade = "C"
        else:
            grade = "F"

        return ConvictionResult(
            grade=grade,
            rivers_agreeing=agreeing,
            rivers_total=total,
            stand_aside=agreeing < 2,
        )

    def _normalize_direction(self, value: str) -> str:
        text = str(value or "").strip()
        if text in self._BULLISH:
            return "BULLISH"
        if text in self._BEARISH:
            return "BEARISH"
        upper = text.upper()
        if upper in self._BULLISH:
            return "BULLISH"
        if upper in self._BEARISH:
            return "BEARISH"
        return "NEUTRAL"


__all__ = ["ConvictionScorer", "ConvictionResult"]
