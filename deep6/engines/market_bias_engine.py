"""Top-level v3 market bias orchestrator."""
from __future__ import annotations

import time
from dataclasses import asdict
from datetime import datetime, time as dt_time
from typing import Optional
from zoneinfo import ZoneInfo

from deep6.engines.bias_composer import BiasComposer
from deep6.engines.bias_contracts import BiasMode, BiasState, DomainScore, MarketBiasSnapshot
from deep6.engines.bias_hysteresis import BiasHysteresisFSM
from deep6.engines.flow_bias import IntradayFlowDomain
from deep6.engines.gex_options_domain import GEXOptionsDomain, GEXSnapshot
from deep6.engines.intermarket_bias import MacroIntermarketDomain
from deep6.engines.kill_switch import KillSwitch
from deep6.engines.kronos_domain import KronosDomainAdapter
from deep6.engines.session_bias import ICTSessionDomain

ET = ZoneInfo("America/New_York")
BIAS_LABELS = {
    BiasState.STRONG_BEAR: "STRONG BEAR",
    BiasState.LEAN_BEAR: "LEAN BEAR",
    BiasState.NEUTRAL: "NEUTRAL",
    BiasState.LEAN_BULL: "LEAN BULL",
    BiasState.STRONG_BULL: "STRONG BULL",
}


class MarketBiasEngine:
    """Collect domain signals and publish a MarketBiasSnapshot."""

    def __init__(
        self,
        symbol: str = "NQ",
        hysteresis_config=None,
        kill_switch_config=None,
        gex_config=None,
    ):
        self._ict = ICTSessionDomain()
        self._macro = MacroIntermarketDomain()
        self._flow = IntradayFlowDomain()
        self._kronos = KronosDomainAdapter()
        self._gex = GEXOptionsDomain(gex_config)
        self._composer = BiasComposer()
        self._fsm = BiasHysteresisFSM(hysteresis_config)
        self._kill = KillSwitch(kill_switch_config)
        self.symbol = symbol

    def compute_bias(
        self,
        po3_state=None,
        intermarket_bars: dict | None = None,
        intermarket_registry=None,
        tick_value: float | None = None,
        cvd_slope: float | None = None,
        price: float | None = None,
        vwap: float | None = None,
        kronos_bias=None,
        kronos_ts: float | None = None,
        gex_snapshot: GEXSnapshot | None = None,
        now_et=None,
        vix_level: float | None = None,
        event_day: bool = False,
    ) -> MarketBiasSnapshot:
        """Compute a market-bias snapshot. All inputs are optional."""
        ict = self._ict.compute(po3_state)
        macro = self._compute_macro(intermarket_bars, intermarket_registry)
        flow = self._flow.compute(
            tick_value=tick_value,
            cvd_slope=cvd_slope,
            price=price,
            vwap=vwap,
            now_et=now_et,
        )
        kronos = self._kronos.compute(kronos_bias, inference_ts=kronos_ts)
        gex = self._gex.compute(gex_snapshot, nq_price=price)

        component = self._composer.compose(
            ict=ict,
            macro=macro,
            flow=flow,
            kronos=kronos,
            gex=gex,
            session_quality=self._is_session_quality(now_et),
            proximity_bonus=self._has_proximity_bonus(po3_state, price),
            flow_clean=self._is_flow_clean(flow),
            rvol_bonus=self._has_rvol_bonus(intermarket_bars),
        )
        bias_state = self._fsm.update(component.total_score)

        all_domains = (ict, macro, flow, kronos, gex)
        active_domains = self._count_active_domains(all_domains)
        stale_domains = sum(1 for domain in all_domains if domain.stale)

        if active_domains == 0:
            mode = BiasMode.CAUTION.value
            mode_reason = "Cold start"
        else:
            self._kill.set_event_day(event_day)
            mode, mode_reason = self._kill.evaluate(
                bias_score=component.total_score,
                vix=vix_level,
                domains_available=active_domains,
                now=self._normalize_now(now_et),
            )

        return MarketBiasSnapshot(
            symbol=self.symbol,
            asof_ts=time.time(),
            bias_label=BIAS_LABELS[bias_state],
            bias_state=bias_state,
            bias_score=component.total_score,
            confidence=component.confidence,
            setup_quality=component.setup_quality,
            mode=mode,
            mode_reason=mode_reason,
            session_label=self._session_label(now_et),
            xamd_phase=self._xamd_phase(po3_state),
            intermarket_alignment=self._intermarket_alignment(macro),
            kronos_confidence=self._kronos_confidence(kronos),
            nearest_support=getattr(po3_state, "pd_low", None),
            nearest_resistance=getattr(po3_state, "pd_high", None),
            domain_detail={
                "ict": asdict(ict),
                "macro": asdict(macro),
                "flow": asdict(flow),
                "kronos": asdict(kronos),
                "gex": asdict(gex),
            },
            meta={
                "active_domains": active_domains,
                "stale_domains": stale_domains,
                "composer": asdict(component),
            },
        )

    def _compute_macro(self, bars: dict | None, registry) -> DomainScore:
        if not bars or registry is None:
            return DomainScore(
                domain="macro",
                score=0,
                max_range=0,
                available=False,
                stale=False,
                detail={"reason": "intermarket_unavailable"},
            )
        return self._macro.compute(bars, registry)

    @staticmethod
    def _count_active_domains(domains: tuple[DomainScore, ...]) -> int:
        return sum(1 for domain in domains if domain.available and not domain.stale)

    @staticmethod
    def _intermarket_alignment(macro: DomainScore) -> float:
        if macro.max_range <= 0:
            return 0.0
        return max(-1.0, min(1.0, macro.score / macro.max_range))

    @staticmethod
    def _kronos_confidence(kronos: DomainScore) -> float:
        raw = float(kronos.detail.get("confidence", 0.0))
        return max(0.0, min(1.0, raw / 100.0))

    def _session_label(self, now_et: Optional[datetime]) -> str:
        if now_et is None:
            return "AVOID"
        current = self._normalize_now(now_et).time()
        if dt_time(9, 30) <= current < dt_time(10, 0):
            return "A+ OPEN"
        if dt_time(10, 0) <= current < dt_time(12, 0):
            return "MID-AM"
        if dt_time(12, 0) <= current < dt_time(13, 0):
            return "LUNCH"
        if dt_time(14, 30) <= current < dt_time(15, 0):
            return "POWER"
        return "AVOID"

    def _is_session_quality(self, now_et: Optional[datetime]) -> bool:
        return self._session_label(now_et) in {"A+ OPEN", "MID-AM", "POWER"}

    @staticmethod
    def _has_proximity_bonus(po3_state, price: float | None) -> bool:
        if po3_state is None or price is None:
            return False
        levels = [
            level
            for level in (
                getattr(po3_state, "pd_high", None),
                getattr(po3_state, "pd_low", None),
                getattr(po3_state, "asia_high", None),
                getattr(po3_state, "asia_low", None),
            )
            if level is not None
        ]
        return any(abs(price - level) <= 10.0 for level in levels)

    @staticmethod
    def _is_flow_clean(flow: DomainScore) -> bool:
        detail = flow.detail
        components = [
            detail.get("cvd_component", 0),
            detail.get("tick_component", 0),
            detail.get("vwap_component", 0),
        ]
        non_zero = [component for component in components if component != 0]
        if len(non_zero) < 2:
            return False
        return len({1 if component > 0 else -1 for component in non_zero}) == 1

    @staticmethod
    def _has_rvol_bonus(intermarket_bars: dict | None) -> bool:
        if not intermarket_bars:
            return False
        volumes = [getattr(bar, "volume", 0.0) for bar in intermarket_bars.values() if bar is not None]
        return bool(volumes) and max(volumes) >= 1_000

    @staticmethod
    def _xamd_phase(po3_state) -> str:
        if po3_state is None:
            return "BETWEEN"
        if hasattr(po3_state, "xamd_phase"):
            phase = getattr(po3_state, "xamd_phase")
        else:
            phase = getattr(po3_state, "phase", "BETWEEN")
        return getattr(phase, "value", phase) or "BETWEEN"

    @staticmethod
    def _normalize_now(now_et: Optional[datetime]) -> datetime:
        if now_et is None:
            return datetime.now(ET)
        if now_et.tzinfo is None:
            return now_et.replace(tzinfo=ET)
        return now_et.astimezone(ET)


__all__ = ["MarketBiasEngine"]
