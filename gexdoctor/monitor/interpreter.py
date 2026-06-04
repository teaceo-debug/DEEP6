"""Deterministic FlashAlpha positioning interpreter.

Loads flashalpha_knowledge.yaml on init. On each call to interpret(),
performs 6-step lookup procedure: regime -> zone -> flow -> vol -> heuristics -> bias.

NO LLM calls. Pure deterministic lookups from knowledge.yaml.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .schemas import BiasResult, FlashAlphaSnapshot

log = logging.getLogger(__name__)
__all__ = ["PositioningInterpreter"]

_BRAIN_DIR = Path(__file__).parent.parent / "brain"


class PositioningInterpreter:
    """Deterministic FlashAlpha positioning interpreter.

    Loads flashalpha_knowledge.yaml on init.
    On each call to interpret(), performs 6-step lookup procedure:
    regime -> zone -> flow -> vol -> heuristics -> bias.

    NO LLM calls. Pure deterministic lookups from knowledge.yaml.
    """

    def __init__(self, knowledge_path: Path | None = None) -> None:
        path = knowledge_path or (_BRAIN_DIR / "flashalpha_knowledge.yaml")
        with path.open(encoding="utf-8") as f:
            self._kb: dict[str, Any] = yaml.safe_load(f)
        log.debug("knowledge.yaml loaded from %s", path)

    def interpret(self, snapshot: FlashAlphaSnapshot) -> BiasResult:
        """Run 6-step procedure, return BiasResult."""
        regime = snapshot.regime
        dealer_risk = snapshot.dealer_risk
        pin = snapshot.pin
        oi_sim = snapshot.oi_simulator

        # Step 1: Regime
        regime_label = self._resolve_regime(regime.gex_sign)

        # Step 2: Price zone
        price_zone, zone_read = self._resolve_price_zone(
            price=snapshot.underlying_price,
            gamma_flip=regime.gamma_flip,
            call_wall=regime.call_wall,
            put_wall=regime.put_wall,
        )

        # Step 3: Flow state -> regime_playbook
        playbook_state, playbook_play = self._resolve_playbook(
            gex_sign=regime.gex_sign,
            flow_direction=dealer_risk.flow_direction,
        )

        # Step 4: Vol outlook
        vol_outlook = self._resolve_vol_outlook(
            gex_sign=regime.gex_sign,
            flow_direction=dealer_risk.flow_direction,
        )

        # Step 5: Heuristics
        caveats: list[str] = []
        caveats.extend(self._check_pin_heuristic(pin.pin_risk, snapshot.dte))
        caveats.extend(self._check_stale_anchor(dealer_risk.flow_gex_pct_shift))
        caveats.extend(self._check_low_confidence(oi_sim.oi_delta_confidence))
        caveats.extend(
            self._check_flip_proximity(snapshot.underlying_price, regime.gamma_flip)
        )
        caveats.extend(
            self._check_vanna_heuristic(
                snapshot.higher_order.vex_sign, snapshot.vol_context.vix
            )
        )
        caveats.extend(
            self._check_charm_heuristic(snapshot.session_phase, snapshot.dte)
        )
        caveats.extend(self._check_dex_direction(regime.net_dex))

        # Step 6: Bias direction
        bias_direction = self._resolve_bias(
            price_zone=price_zone,
            gex_sign=regime.gex_sign,
            flow_direction=dealer_risk.flow_direction,
            underlying_price=snapshot.underlying_price,
            gamma_flip=regime.gamma_flip,
        )

        # Confidence label based on feed quality
        conf_label = self._confidence_label(
            oi_sim.oi_delta_confidence, snapshot.feed_quality.missing_fields
        )

        # Lean = playbook play (primary) or zone read (fallback)
        lean = playbook_play if playbook_play else zone_read

        return BiasResult(
            direction=bias_direction,
            regime=regime_label,
            lean=lean,
            confidence_label=conf_label,
            caveats=caveats,
            price_zone=price_zone,
        )

    # ------------------------------------------------------------------
    # Step 1: Regime
    # ------------------------------------------------------------------

    def _resolve_regime(self, gex_sign: str) -> str:
        """Vocabulary lookup for regime label."""
        vocab = self._kb.get("vocabulary", {}).get("gamma_regime", {})
        if gex_sign == "positive":
            return vocab.get("positive_gex", {}).get("label", "long gamma")
        return vocab.get("negative_gex", {}).get("label", "short gamma")

    # ------------------------------------------------------------------
    # Step 2: Price zone
    # ------------------------------------------------------------------

    def _resolve_price_zone(
        self,
        price: float,
        gamma_flip: float,
        call_wall: float | None,
        put_wall: float | None,
    ) -> tuple[str, str]:
        """Price zone lookup from knowledge.yaml."""
        zones = self._kb.get("lookups", {}).get("price_zone", [])
        cw = call_wall if call_wall is not None else float("inf")
        pw = put_wall if put_wall is not None else float("-inf")

        if price > cw:
            zone_key = "above_call_wall"
        elif price > gamma_flip:
            zone_key = "long_gamma_upper"
        elif price > pw:
            zone_key = "short_gamma_lower"
        else:
            zone_key = "below_put_wall"

        read = next((z["read"] for z in zones if z["zone"] == zone_key), "")
        return zone_key, read

    # ------------------------------------------------------------------
    # Step 3: Regime playbook
    # ------------------------------------------------------------------

    def _resolve_playbook(
        self, gex_sign: str, flow_direction: str
    ) -> tuple[str, str]:
        """regime_playbook lookup (gex x flow -> state + play).

        Note: schema uses "regime flip" (space) but YAML uses "regime_flip" (underscore).
        Normalize before matching.
        """
        playbook = self._kb.get("lookups", {}).get("regime_playbook", [])
        # Normalize flow_direction: "regime flip" -> "regime_flip"
        normalized_flow = flow_direction.replace(" ", "_")

        for entry in playbook:
            entry_gex = entry.get("gex", "any")
            entry_flow = entry.get("flow", "")
            gex_match = entry_gex == "any" or entry_gex == gex_sign
            flow_match = entry_flow == normalized_flow
            if gex_match and flow_match:
                return entry.get("state", "unknown"), entry.get("play", "")
        return "unknown", ""

    # ------------------------------------------------------------------
    # Step 4: Vol outlook
    # ------------------------------------------------------------------

    def _resolve_vol_outlook(self, gex_sign: str, flow_direction: str) -> str:
        """vol_outlook lookup."""
        vol_table = self._kb.get("lookups", {}).get("vol_outlook", [])
        normalized_flow = flow_direction.replace(" ", "_")
        for entry in vol_table:
            if entry.get("flow") == normalized_flow and entry.get("gex") == gex_sign:
                return entry.get("vol", "")
        return ""

    # ------------------------------------------------------------------
    # Step 5: Heuristics
    # ------------------------------------------------------------------

    def _check_pin_heuristic(
        self, pin_risk: float | None, dte: int | None
    ) -> list[str]:
        if (pin_risk or 0) > 65 and (dte is not None and dte <= 1):
            h = self._kb.get("heuristics", {}).get("pin_into_expiry", {})
            return [f"pin_into_expiry: {h.get('meaning', '')}"]
        return []

    def _check_stale_anchor(self, flow_gex_pct_shift: float | None) -> list[str]:
        if flow_gex_pct_shift is not None and abs(flow_gex_pct_shift) > 0.10:
            h = self._kb.get("heuristics", {}).get("stale_anchor", {})
            return [f"stale_anchor: {h.get('meaning', '')}"]
        return []

    def _check_low_confidence(self, oi_delta_confidence: float | None) -> list[str]:
        if oi_delta_confidence is not None and oi_delta_confidence < 0.3:
            h = self._kb.get("heuristics", {}).get("low_confidence", {})
            return [f"low_confidence: {h.get('meaning', '')}"]
        return []

    def _check_flip_proximity(self, price: float, gamma_flip: float) -> list[str]:
        if abs(price - gamma_flip) < 10:
            h = self._kb.get("heuristics", {}).get("flip_proximity", {})
            return [f"flip_proximity: {h.get('meaning', '')}"]
        return []

    def _check_vanna_heuristic(
        self, vex_sign: str | None, vix: float | None
    ) -> list[str]:
        if vex_sign and vex_sign != "neutral" and vix and vix > 20:
            h = self._kb.get("heuristics", {}).get("vanna_regime", {})
            return [f"vanna_regime: {h.get('meaning', '')}"]
        return []

    def _check_charm_heuristic(
        self, session_phase: str, dte: int | None
    ) -> list[str]:
        if session_phase == "into_close" and dte is not None and dte <= 1:
            h = self._kb.get("heuristics", {}).get("charm_drift", {})
            return [f"charm_drift: {h.get('meaning', '')}"]
        return []

    def _check_dex_direction(self, net_dex: float | None) -> list[str]:
        if net_dex is not None and abs(net_dex) > 200_000_000:
            h = self._kb.get("heuristics", {}).get("dex_direction", {})
            return [f"dex_direction: {h.get('meaning', '')}"]
        return []

    # ------------------------------------------------------------------
    # Step 6: Bias direction
    # ------------------------------------------------------------------

    def _resolve_bias(
        self,
        price_zone: str,
        gex_sign: str,
        flow_direction: str,
        underlying_price: float,
        gamma_flip: float,
    ) -> str:
        """Determine bullish/bearish/neutral/no_vote from zone + regime + flow."""
        # Near flip = unstable, call neutral
        if abs(underlying_price - gamma_flip) < 5:
            return "neutral"

        if price_zone == "above_call_wall":
            return "neutral" if gex_sign == "positive" else "bullish"

        if price_zone == "below_put_wall":
            return "neutral" if gex_sign == "positive" else "bearish"

        if price_zone == "long_gamma_upper":
            # Above flip in positive GEX: mean-revert down toward flip, call wall caps
            if flow_direction == "amplifying":
                return "bearish"  # stronger range tightening, caps upside
            return "neutral"

        if price_zone == "short_gamma_lower":
            # Below flip: trending/volatile zone
            if flow_direction == "amplifying":
                return "bearish"  # trend expanding downward
            return "bearish"  # short gamma zone biases down

        return "neutral"

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    def _confidence_label(
        self, oi_conf: float | None, missing: list[str]
    ) -> str:
        conf = oi_conf if oi_conf is not None else 0.5
        if conf > 0.7 and len(missing) <= 1:
            return "high"
        if conf > 0.4:
            return "medium"
        return "low"
