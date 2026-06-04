"""Unified direction engine — synthesizes all signals into LONG/SHORT/FLAT."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DirectionSignal:
    direction: str
    confidence: int
    reason: str
    signals_long: int
    signals_short: int
    signals_total: int


class DirectionEngine:
    """Synthesizes all data sources into a single LONG/SHORT/FLAT call."""

    def compute(
        self,
        *,
        gex_regime: str = "neutral",
        gex_confidence: int = 50,
        flow_direction: str = "neutral",
        flow_z_score: float = 0.0,
        dp_bias: str = "neutral",
        dp_conviction: float = 0.0,
        conviction_grade: str = "C",
        conviction_rivers: int = 0,
        grid_buy: int = 0,
        grid_sell: int = 0,
        vex_chex_aligned: bool = False,
        vex_direction: str = "neutral",
        hmm_state: str = "UNKNOWN",
        po3_direction: str = "UNKNOWN",
        market_tide: str = "MIXED",
        price_above_flip: Optional[bool] = None,
    ) -> DirectionSignal:
        long_votes = 0.0
        short_votes = 0.0
        total_votes = 0.0

        if gex_regime == "positive":
            long_votes += 2.0
            total_votes += 2.0
        elif gex_regime == "negative":
            short_votes += 2.0
            total_votes += 2.0

        if flow_direction == "bullish":
            long_votes += 2.0
            total_votes += 2.0
            if abs(flow_z_score) >= 2.0:
                long_votes += 0.5
                total_votes += 0.5
        elif flow_direction == "bearish":
            short_votes += 2.0
            total_votes += 2.0
            if abs(flow_z_score) >= 2.0:
                short_votes += 0.5
                total_votes += 0.5

        if dp_bias.upper() == "BULLISH":
            long_votes += 1.5
            total_votes += 1.5
            if dp_conviction >= 0.6:
                long_votes += 0.5
                total_votes += 0.5
        elif dp_bias.upper() == "BEARISH":
            short_votes += 1.5
            total_votes += 1.5
            if dp_conviction >= 0.6:
                short_votes += 0.5
                total_votes += 0.5

        if grid_buy > grid_sell + 2:
            long_votes += 1.0
            total_votes += 1.0
        elif grid_sell > grid_buy + 2:
            short_votes += 1.0
            total_votes += 1.0

        if market_tide == "BULLISH":
            long_votes += 1.0
            total_votes += 1.0
        elif market_tide == "BEARISH":
            short_votes += 1.0
            total_votes += 1.0

        if vex_chex_aligned and vex_direction == "tailwind":
            long_votes += 0.5
            total_votes += 0.5
        elif vex_chex_aligned and vex_direction == "headwind":
            short_votes += 0.5
            total_votes += 0.5

        if po3_direction == "BULLISH":
            long_votes += 1.0
            total_votes += 1.0
        elif po3_direction == "BEARISH":
            short_votes += 1.0
            total_votes += 1.0

        if price_above_flip is True:
            long_votes += 1.0
            total_votes += 1.0
        elif price_above_flip is False:
            short_votes += 1.0
            total_votes += 1.0

        if total_votes == 0:
            return DirectionSignal("FLAT", 0, "No data", 0, 0, 0)

        long_pct = long_votes / total_votes * 100.0
        short_pct = short_votes / total_votes * 100.0

        hmm_penalty = 0
        if hmm_state == "CHAOTIC":
            hmm_penalty = 25
        elif hmm_state == "TRENDING":
            hmm_penalty = 10

        conviction_penalty = 0
        if conviction_grade == "F":
            conviction_penalty = 20
        elif conviction_grade == "C":
            conviction_penalty = 10

        if conviction_rivers <= 1:
            conviction_penalty += 10
        elif conviction_rivers >= 4:
            conviction_penalty = max(0, conviction_penalty - 5)

        if gex_confidence < 40:
            conviction_penalty += 10
        elif gex_confidence >= 75:
            conviction_penalty = max(0, conviction_penalty - 5)

        forced_flat = (
            conviction_grade == "F" and hmm_state == "CHAOTIC"
        ) or (conviction_rivers <= 1 and gex_confidence < 40)

        if long_pct > short_pct + 15:
            confidence = min(100, max(0, int(long_pct) - hmm_penalty - conviction_penalty))
            if forced_flat or confidence < 30:
                if forced_flat:
                    confidence = min(confidence, 25)
                return DirectionSignal(
                    "FLAT",
                    confidence,
                    "Weak long — stand aside",
                    int(long_votes),
                    int(short_votes),
                    int(total_votes),
                )
            return DirectionSignal(
                "LONG",
                confidence,
                self._build_reason("LONG", gex_regime, flow_direction, dp_bias),
                int(long_votes),
                int(short_votes),
                int(total_votes),
            )

        if short_pct > long_pct + 15:
            confidence = min(100, max(0, int(short_pct) - hmm_penalty - conviction_penalty))
            if forced_flat or confidence < 30:
                if forced_flat:
                    confidence = min(confidence, 25)
                return DirectionSignal(
                    "FLAT",
                    confidence,
                    "Weak short — stand aside",
                    int(long_votes),
                    int(short_votes),
                    int(total_votes),
                )
            return DirectionSignal(
                "SHORT",
                confidence,
                self._build_reason("SHORT", gex_regime, flow_direction, dp_bias),
                int(long_votes),
                int(short_votes),
                int(total_votes),
            )

        return DirectionSignal(
            "FLAT",
            int(max(long_pct, short_pct)),
            "Mixed signals — no edge",
            int(long_votes),
            int(short_votes),
            int(total_votes),
        )

    def _build_reason(self, direction: str, regime: str, flow: str, dp: str) -> str:
        parts: list[str] = []
        if regime in {"positive", "negative"}:
            parts.append(f"GEX {regime}")
        if flow in {"bullish", "bearish"}:
            parts.append(f"flow {flow}")
        if dp.lower() in {"bullish", "bearish"}:
            parts.append(f"DP {dp.lower()}")
        return " + ".join(parts) if parts else direction


__all__ = ["DirectionEngine", "DirectionSignal"]
