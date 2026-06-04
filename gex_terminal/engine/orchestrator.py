"""GEX Terminal orchestrator — 30-second polling loop coordinating all components."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from gex_terminal.config import Settings
from gex_terminal.engine.adapters.flashalpha import FlashAlphaAdapter, FlashAlphaResult
from gex_terminal.engine.adapters.massive import MassiveAdapter, MassiveResult
from gex_terminal.engine.adapters.rithmic_feed import RithmicNQFeed
from gex_terminal.engine.adapters.unusual_whales import DarkPoolSummary, UnusualWhalesAdapter, UWGEXResult
from gex_terminal.engine.analyzer import GEXAnalyzer
from gex_terminal.engine.deep6_bridge import DEEP6Bridge
from gex_terminal.engine.dp_levels import DarkPoolLevelEngine
from gex_terminal.engine.direction_engine import DirectionEngine
from gex_terminal.engine.flashalpha_mcp import FlashAlphaMCPClient
from gex_terminal.engine.interpreter import ClaudeInterpreter
from gex_terminal.engine.learner import SessionLearner
from gex_terminal.engine.magnet import GEXMagnetSelector
from gex_terminal.engine.regime_gate import HMMRegimeGate
from gex_terminal.engine.signal_grid import SignalGridEngine
from gex_terminal.engine.swing_equilibrium import SwingEquilibriumEngine
from gex_terminal.engine.uw_mcp import UWMCPClient
from gex_terminal.schemas import (
    BiasVerdict,
    ClaudeNarrative,
    DarkPoolData,
    DealerPositioning,
    GEXLevels,
    GEXTerminalSnapshot,
    SourceHealth,
    ZeroDTEState,
)
from gex_terminal.schemas_institutional import (
    DarkPoolSession,
    Filing13F,
    FloorTrade,
    InstitutionalHolder,
    InstitutionalSnapshot,
    MarketTide,
)

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Awaitable[None]]


class GEXOrchestrator:
    """Main orchestration loop: polls adapters, analyzes, interprets, broadcasts."""

    def __init__(
        self,
        settings: Settings,
        *,
        fa_adapter: FlashAlphaAdapter | None = None,
        massive_adapter: MassiveAdapter | None = None,
        uw_adapter: UnusualWhalesAdapter | None = None,
        analyzer: GEXAnalyzer | None = None,
        regime_gate: HMMRegimeGate | None = None,
        interpreter: ClaudeInterpreter | None = None,
        learner: SessionLearner | None = None,
        bridge: DEEP6Bridge | None = None,
        initial_massive_delay_sec: float = 5.0,
        initial_uw_delay_sec: float = 10.0,
    ) -> None:
        self._settings = settings
        self._flashalpha_enabled = settings.flashalpha_enabled

        if self._flashalpha_enabled:
            self._fa_adapter = fa_adapter or FlashAlphaAdapter(api_key=settings.flashalpha_api_key)
            self._fa_mcp: FlashAlphaMCPClient | None = (
                FlashAlphaMCPClient(api_key=settings.flashalpha_api_key)
                if settings.flashalpha_mcp_enabled
                else None
            )
        else:
            self._fa_adapter = fa_adapter  # None when disabled
            self._fa_mcp = None
            logger.info("FlashAlpha disabled — using Massive + UW GEX")

        self._uw_mcp = UWMCPClient(api_key=settings.uw_api_key) if settings.uw_api_key else None
        self._massive_adapter = massive_adapter or MassiveAdapter(api_key=settings.massive_api_key)
        self._uw_adapter = uw_adapter or UnusualWhalesAdapter(api_key=settings.uw_api_key)
        self._analyzer = analyzer or GEXAnalyzer()
        self._regime_gate = regime_gate or HMMRegimeGate()
        self._learner = learner or SessionLearner()
        self._interpreter = interpreter or ClaudeInterpreter(
            api_key=settings.anthropic_api_key,
            model=settings.claude_model,
            budget_daily_usd=settings.claude_budget_daily_usd,
            learner=self._learner,
            mcp_client=self._fa_mcp,
            uw_mcp_client=self._uw_mcp,
        )
        self._bridge = bridge or DEEP6Bridge(settings.deep6_bias_url)
        self._magnet_selector = GEXMagnetSelector()
        self._signal_grid = SignalGridEngine()
        self._dp_level_engine = DarkPoolLevelEngine()
        self._direction_engine = DirectionEngine()
        self._swing_eq_engine = SwingEquilibriumEngine()
        self._broadcast_fn: BroadcastFn | None = None
        self._running = False
        self._cycle_count = 0
        self._startup_time = time.time()
        self._initial_massive_delay_sec = max(0.0, initial_massive_delay_sec)
        self._initial_uw_delay_sec = max(0.0, initial_uw_delay_sec)
        self._last_fa_result: FlashAlphaResult | None = None
        self._last_massive_result: MassiveResult | None = None
        self._last_uw_result: DarkPoolSummary | None = None
        self._rithmic_feed = self._build_rithmic_feed(settings)

    def set_broadcast(self, fn: BroadcastFn) -> None:
        """Inject the SSE broadcast function from server.py."""
        self._broadcast_fn = fn

    async def run(self) -> None:
        """Main loop: poll every refresh_interval_sec seconds."""
        self._running = True
        logger.info("GEX Orchestrator starting (interval=%ds)", self._settings.refresh_interval_sec)

        try:
            if self._rithmic_feed is not None:
                await self._rithmic_feed.start()
            while self._running:
                cycle_start = time.time()
                try:
                    await self._run_cycle()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Orchestrator cycle error: %s", exc)

                elapsed = time.time() - cycle_start
                sleep_time = max(0.0, self._settings.refresh_interval_sec - elapsed)
                await asyncio.sleep(sleep_time)
        finally:
            if self._rithmic_feed is not None:
                await self._rithmic_feed.stop()
            self._save_session_learning()

    async def _run_cycle(self) -> GEXTerminalSnapshot:
        """Single orchestration cycle: poll → analyze → interpret → broadcast."""
        self._cycle_count += 1
        logger.debug("Cycle %d starting", self._cycle_count)

        fa_result, massive_result, uw_result = await self._poll_sources()
        qqq_spot = self._extract_qqq_spot(massive_result)
        nq_spot = self._rithmic_feed.get_nq_price() if self._rithmic_feed is not None else None

        hmm_state = self._regime_gate.update(self._build_hmm_features(fa_result, massive_result))
        analysis = self._analyzer.analyze(
            fa_result,
            massive_result,
            nq_spot=nq_spot,
            qqq_spot=qqq_spot,
            hmm_state=hmm_state,
            dark_pool_direction=uw_result.institutional_bias,
            dp_levels_nq=uw_result.levels_nq,
        )

        current_price_nq = self._resolve_live_nq_spot(
            fa_result,
            massive_result,
            analysis.nq_qqq_ratio,
            rithmic_nq_spot=nq_spot,
        )

        if self._cycle_count <= 2 and self._has_massive_data(massive_result):
            analysis = analysis.__class__(
                bias=analysis.bias,
                levels=analysis.levels,
                dealer=analysis.dealer,
                flow=analysis.flow,
                vanna_charm=analysis.vanna_charm,
                zero_dte=analysis.zero_dte,
                material_change=True,
                nq_qqq_ratio=analysis.nq_qqq_ratio,
                vix=analysis.vix,
                conviction_grade=analysis.conviction_grade,
                conviction_rivers=analysis.conviction_rivers,
                po3_state=analysis.po3_state,
            )

        inst_raw: dict[str, dict | None] = {}
        try:
            inst_raw = await self._uw_adapter.poll_institutional()
        except Exception as exc:
            logger.debug("Institutional poll failed: %s", exc)

        dp_prints = inst_raw.get("dp_detailed", {}) if isinstance(inst_raw, dict) else {}
        dp_print_list = dp_prints.get("data", []) if isinstance(dp_prints, dict) else []
        dp_levels = self._dp_level_engine.compute_levels(
            dp_print_list if isinstance(dp_print_list, list) else [],
            current_price_nq=current_price_nq,
            nq_qqq_ratio=analysis.nq_qqq_ratio,
        )

        signal_grid = self._signal_grid.compute(
            inst_flow_direction=(uw_result.institutional_bias or "neutral").upper(),
            dp_bias=uw_result.institutional_bias,
            market_tide_direction=self._resolve_market_tide(inst_raw.get("market_tide")),
            sweep_flow_direction=self._resolve_flow_alerts(inst_raw.get("flow_alerts")),
            daily_oi_bias=self._resolve_oi_bias(inst_raw.get("oi_change")),
            oi_change_direction=self._resolve_oi_bias(inst_raw.get("oi_change")),
            dp_level_bias=self._resolve_dp_level_bias(dp_levels, current_price_nq),
        )

        dp_centers = [level.price_nq for level in dp_levels]
        dp_premiums = [level.total_premium for level in dp_levels]
        swing_eq = self._swing_eq_engine.compute(
            dp_centers,
            dp_premiums,
            gamma_flip_nq=analysis.levels.gamma_flip,
            hvl_nq=analysis.levels.hvl,
        )
        market_tide_direction = self._resolve_market_tide(inst_raw.get("market_tide"))
        direction_signal = self._direction_engine.compute(
            gex_regime=analysis.dealer.regime,
            gex_confidence=analysis.bias.confidence,
            flow_direction=analysis.flow.direction,
            flow_z_score=analysis.flow.z_score,
            dp_bias=uw_result.institutional_bias,
            dp_conviction=self._resolve_dark_pool_conviction(uw_result, dp_levels),
            conviction_grade=analysis.conviction_grade,
            conviction_rivers=analysis.conviction_rivers,
            grid_buy=signal_grid.confluence_buy,
            grid_sell=signal_grid.confluence_sell,
            vex_chex_aligned=self._is_vex_chex_aligned(analysis.dealer),
            vex_direction=analysis.vanna_charm.net_hedge_direction,
            hmm_state=hmm_state,
            po3_direction=analysis.po3_state,
            market_tide=market_tide_direction,
            price_above_flip=(current_price_nq > analysis.levels.gamma_flip) if current_price_nq is not None and analysis.levels.gamma_flip is not None else None,
        )

        institutional = InstitutionalSnapshot(
            timestamp=time.time(),
            inst_flow_direction=(uw_result.institutional_bias or "neutral").upper(),
            top_holders=self._parse_top_holders(inst_raw.get("ownership")),
            recent_filings=self._parse_recent_filings(inst_raw.get("filings")),
            floor_trades=self._parse_floor_trades(inst_raw.get("inst_flow")),
            dark_pool_session=DarkPoolSession(
                print_count=len(dp_print_list) if isinstance(dp_print_list, list) else 0,
                net_premium=uw_result.net_premium or 0.0,
                bias=(uw_result.institutional_bias or "neutral").upper(),
            ),
            market_tide=MarketTide(
                call_premium=self._extract_market_tide_premium(inst_raw.get("market_tide"), "call_premium"),
                put_premium=self._extract_market_tide_premium(inst_raw.get("market_tide"), "put_premium"),
                direction=market_tide_direction,
                strength_pct=self._resolve_market_tide_strength(inst_raw.get("market_tide")),
            ),
            signal_grid=signal_grid,
            dp_levels=dp_levels,
            swing_equilibrium=swing_eq,
            dp_bias=(uw_result.institutional_bias or "neutral").upper(),
        )

        narrative = await self._interpreter.interpret(
            bias=analysis.bias,
            levels=analysis.levels,
            dealer=analysis.dealer,
            material_change=analysis.material_change,
            cycle_count=self._cycle_count,
        )
        magnet_price, magnet_conf = self._magnet_selector.select(
            gamma_flip=analysis.levels.gamma_flip,
            call_wall=analysis.levels.call_wall,
            put_wall=analysis.levels.put_wall,
            hvl=analysis.levels.hvl,
            zero_dte_magnet=analysis.levels.zero_dte_magnet,
            regime=analysis.dealer.regime,
            spot_nq=None,
        )

        bias_score, bias_label, confidence = await self._read_deep6_bias(
            bias=analysis.bias,
            detail=analysis.levels.model_dump(),
        )

        snapshot = GEXTerminalSnapshot(
            timestamp=time.time(),
            bias=analysis.bias,
            levels=analysis.levels,
            dealer=analysis.dealer,
            flow=analysis.flow,
            vanna_charm=analysis.vanna_charm,
            zero_dte=analysis.zero_dte,
            dark_pool=DarkPoolData(
                levels_nq=uw_result.levels_nq,
                net_premium=uw_result.net_premium,
                institutional_bias=uw_result.institutional_bias,
            ),
            institutional=institutional,
            narrative=narrative,
            primary_magnet=magnet_price,
            magnet_confidence=round(magnet_conf, 3) if magnet_conf else None,
            sources={
                **({"flashalpha": fa_result.source_health} if self._flashalpha_enabled else {"uw_gex": fa_result.source_health}),
                "massive": massive_result.source_health,
                "unusual_whales": uw_result.source_health,
                **self._build_rithmic_source_health(),
            },
            hmm_regime=hmm_state,
            conviction_grade=analysis.conviction_grade,
            conviction_rivers=analysis.conviction_rivers,
            direction_signal=direction_signal.direction,
            direction_confidence=direction_signal.confidence,
            direction_reason=direction_signal.reason,
            po3_state=analysis.po3_state,
            deep6_bias_score=bias_score,
            deep6_bias_label=bias_label,
            deep6_confidence=confidence,
            cost_today_usd=self._interpreter.daily_spend,
        )

        self._learner.record_cycle(
            timestamp=snapshot.timestamp,
            bias_direction=snapshot.bias.direction,
            confidence=snapshot.bias.confidence,
            conviction_grade=snapshot.conviction_grade,
            regime=snapshot.bias.regime_name,
            gamma_flip=snapshot.levels.gamma_flip,
            call_wall=snapshot.levels.call_wall,
            put_wall=snapshot.levels.put_wall,
            hmm_state=snapshot.hmm_regime,
            flow_direction=snapshot.flow.direction,
        )

        if self._broadcast_fn is not None:
            await self._broadcast_fn(snapshot.model_dump())

        logger.info(
            "Cycle %d: %s confidence=%d%% material=%s cost=$%.3f uptime=%ds",
            self._cycle_count,
            snapshot.bias.direction,
            snapshot.bias.confidence,
            analysis.material_change,
            self._interpreter.daily_spend,
            int(time.time() - self._startup_time),
        )
        return snapshot

    async def _read_deep6_bias(
        self,
        *,
        bias: BiasVerdict,
        detail: dict[str, Any],
    ) -> tuple[int | None, str | None, float | None]:
        """Read optional DEEP6 bias state without blocking standalone operation."""
        if not self._settings.deep6_bias_url:
            return None, "STANDALONE", None

        try:
            await asyncio.wait_for(self._bridge.push_gex_snapshot(bias, detail), timeout=2.0)
            bias_score, bias_label, confidence = await asyncio.wait_for(
                self._bridge.read_bias(), timeout=2.0
            )
        except (asyncio.TimeoutError, Exception) as exc:
            logger.debug("DEEP6 bridge unavailable; using standalone badge: %s", exc)
            return None, "STANDALONE", None

        if bias_score is None and bias_label is None and confidence is None:
            return None, "STANDALONE", None

        return bias_score, bias_label, confidence

    def _should_poll_flashalpha(self) -> bool:
        """FlashAlpha is throttled to every Nth cycle to conserve API quota.

        Massive.com is the primary GEX source; FlashAlpha supplements with
        DEX/VEX/CHEX/0DTE data that Massive cannot provide.
        """
        n = max(1, self._settings.flashalpha_poll_every_n_cycles)
        if n <= 1:
            return True
        # Always poll on cycle 1 (startup) and every Nth cycle thereafter
        return self._cycle_count == 1 or self._cycle_count % n == 0

    async def _poll_sources(self) -> tuple[FlashAlphaResult, MassiveResult, DarkPoolSummary]:
        massive_coro = self._poll_massive_with_optional_delay()
        uw_coro = self._poll_uw_with_optional_delay()

        if not self._flashalpha_enabled:
            # FlashAlpha disabled — poll UW GEX instead
            uw_gex_coro = self._uw_adapter.poll_gex()
            results = await asyncio.gather(
                uw_gex_coro,
                massive_coro,
                uw_coro,
                return_exceptions=True,
            )
            uw_gex_raw, massive_result, uw_result = results

            if isinstance(uw_gex_raw, Exception):
                logger.error("UW GEX poll raised: %s", uw_gex_raw)
                fa_result = self._build_flashalpha_fallback("UW GEX error: " + str(uw_gex_raw))
            else:
                fa_result = self._build_fa_from_uw_gex(uw_gex_raw)
                self._last_fa_result = fa_result
        else:
            # FlashAlpha enabled — original throttled polling
            poll_fa = self._should_poll_flashalpha()
            if poll_fa:
                logger.info("Cycle %d: polling FlashAlpha (every %d cycles)",
                            self._cycle_count, self._settings.flashalpha_poll_every_n_cycles)
                fa_coro = self._fa_adapter.poll()
            else:
                logger.debug("Cycle %d: skipping FlashAlpha (cached), Massive is primary",
                             self._cycle_count)
                fa_coro = asyncio.sleep(0)  # no-op placeholder for gather

            results = await asyncio.gather(
                fa_coro,
                massive_coro,
                uw_coro,
                return_exceptions=True,
            )
            fa_result_raw, massive_result, uw_result = results

            if not poll_fa:
                fa_result = self._last_fa_result or self._build_flashalpha_fallback("Throttled — using Massive as primary")
            elif isinstance(fa_result_raw, Exception):
                logger.error("FlashAlpha adapter raised unexpectedly: %s", fa_result_raw)
                fa_result = self._build_flashalpha_fallback(str(fa_result_raw))
            else:
                fa_result = fa_result_raw
                self._last_fa_result = fa_result

        if isinstance(massive_result, Exception):
            logger.error("Massive adapter raised unexpectedly: %s", massive_result)
            massive_result = self._build_massive_fallback(str(massive_result))
        else:
            self._last_massive_result = massive_result

        if isinstance(uw_result, Exception):
            logger.error("Unusual Whales adapter raised unexpectedly: %s", uw_result)
            uw_result = self._build_uw_fallback(str(uw_result))
        else:
            self._last_uw_result = uw_result

        return fa_result, massive_result, uw_result

    def _build_hmm_features(
        self,
        fa_result: FlashAlphaResult,
        massive_result: MassiveResult,
    ) -> list[float]:
        net_gex = abs(float(fa_result.dealer.net_gex or 0.0))
        atr_ratio = min(1.0, net_gex / 5_000_000_000.0)

        spread = self._average_level_divergence(fa_result.levels, massive_result.levels)

        flow_result = massive_result.flow_result
        if flow_result is not None:
            premium_scale = min(1.0, abs(float(flow_result.signed_premium_5m)) / 1_000_000.0)
            z_scale = min(1.0, abs(float(flow_result.z_score)) / 3.0)
            trade_rate = max(premium_scale, z_scale)
            delta = min(1.0, abs(int(flow_result.net_direction)) * trade_rate)
        else:
            trade_rate = 0.0
            delta = 0.0

        range_to_atr = min(1.0, atr_ratio * trade_rate)
        return [atr_ratio, spread, trade_rate, delta, range_to_atr]

    def _average_level_divergence(self, fa_levels: GEXLevels, massive_levels: GEXLevels) -> float:
        divergences: list[float] = []
        for left, right in (
            (fa_levels.gamma_flip, massive_levels.gamma_flip),
            (fa_levels.call_wall, massive_levels.call_wall),
            (fa_levels.put_wall, massive_levels.put_wall),
        ):
            if left is None or right is None:
                continue
            baseline = max(abs(float(left)), abs(float(right)), 1.0)
            divergences.append(min(1.0, abs(float(left) - float(right)) / baseline))
        return round(sum(divergences) / len(divergences), 4) if divergences else 0.0

    def _has_massive_data(self, massive_result: MassiveResult) -> bool:
        if massive_result.raw_gex_result is not None:
            return True
        levels = massive_result.levels
        return any(
            level is not None
            for level in (levels.gamma_flip, levels.call_wall, levels.put_wall, levels.hvl)
        )

    def _resolve_current_price_nq(self, analysis) -> float | None:
        for level in (analysis.levels.gamma_flip, analysis.levels.hvl, analysis.levels.call_wall, analysis.levels.put_wall):
            if isinstance(level, (int, float)) and level > 0:
                return float(level)
        return None

    def _resolve_live_nq_spot(
        self,
        fa_result: FlashAlphaResult,
        massive_result: MassiveResult,
        nq_qqq_ratio: float,
        rithmic_nq_spot: float | None = None,
    ) -> float | None:
        if isinstance(rithmic_nq_spot, (int, float)) and rithmic_nq_spot > 0:
            return float(rithmic_nq_spot)
        summary = fa_result.raw.get("summary") if isinstance(fa_result.raw, dict) else None
        if isinstance(summary, dict):
            for key in ("spot", "price", "underlying_price", "underlyingPrice"):
                value = self._safe_float(summary.get(key), 0.0)
                if value > 0:
                    return value

        raw_gex = massive_result.raw_gex_result
        qqq_spot = getattr(raw_gex, "spot", None)
        qqq_price = self._safe_float(qqq_spot, 0.0)
        if qqq_price > 0 and nq_qqq_ratio > 0:
            return qqq_price * nq_qqq_ratio
        return None

    def _extract_qqq_spot(self, massive_result: MassiveResult) -> float | None:
        raw_gex = massive_result.raw_gex_result
        value = getattr(raw_gex, "spot", None)
        return self._safe_float(value, 0.0) or None

    def _build_rithmic_feed(self, settings: Settings) -> RithmicNQFeed | None:
        if not settings.rithmic_enabled:
            return None
        if not settings.rithmic_user or not settings.rithmic_password:
            logger.info("Rithmic NQ feed disabled: missing credentials")
            return None
        return RithmicNQFeed(
            user=settings.rithmic_user,
            password=settings.rithmic_password,
            system_name=settings.rithmic_system_name,
            uri=settings.rithmic_uri,
            app_name=settings.rithmic_app_name,
        )

    def _build_rithmic_source_health(self) -> dict[str, SourceHealth]:
        if self._rithmic_feed is None:
            return {}
        connected = self._rithmic_feed.connected
        return {
            "rithmic": SourceHealth(
                name="rithmic",
                status="ok" if connected else "error",
                last_update=self._rithmic_feed.last_update,
                ttl_sec=60,
                error_msg="" if connected else "disconnected",
            )
        }

    def _resolve_dark_pool_conviction(self, uw_result: DarkPoolSummary, dp_levels: list[Any]) -> float:
        premium = abs(float(uw_result.net_premium or 0.0))
        level_count = len(dp_levels)
        premium_score = min(1.0, premium / 10_000_000.0)
        level_score = min(1.0, level_count / 3.0)
        return round((premium_score * 0.7) + (level_score * 0.3), 3)

    def _is_vex_chex_aligned(self, dealer: DealerPositioning) -> bool:
        if dealer.net_vex is None or dealer.net_chex is None:
            return False
        return (dealer.net_vex > 0 and dealer.net_chex > 0) or (dealer.net_vex < 0 and dealer.net_chex < 0)

    def _resolve_market_tide(self, data: Any) -> str:
        payload = self._unwrap_data_payload(data)
        if isinstance(payload, dict):
            call_prem = self._safe_float(payload.get("call_premium"), 0.0)
            put_prem = self._safe_float(payload.get("put_premium"), 0.0)
            if call_prem > put_prem * 1.2:
                return "BULLISH"
            if put_prem > call_prem * 1.2:
                return "BEARISH"
        return "MIXED"

    def _resolve_market_tide_strength(self, data: Any) -> float:
        payload = self._unwrap_data_payload(data)
        if not isinstance(payload, dict):
            return 0.0
        call_prem = self._safe_float(payload.get("call_premium"), 0.0)
        put_prem = self._safe_float(payload.get("put_premium"), 0.0)
        total = call_prem + put_prem
        if total <= 0:
            return 0.0
        return round(abs(call_prem - put_prem) / total * 100.0, 2)

    def _extract_market_tide_premium(self, data: Any, key: str) -> float:
        payload = self._unwrap_data_payload(data)
        if not isinstance(payload, dict):
            return 0.0
        return self._safe_float(payload.get(key), 0.0)

    def _resolve_flow_alerts(self, data: Any) -> str:
        alerts = self._unwrap_data_payload(data)
        if not isinstance(alerts, list) or not alerts:
            return "neutral"
        call_prem = sum(
            self._safe_float(alert.get("premium"), 0.0)
            for alert in alerts
            if str(alert.get("type") or alert.get("call_put") or "").upper() == "CALL"
        )
        put_prem = sum(
            self._safe_float(alert.get("premium"), 0.0)
            for alert in alerts
            if str(alert.get("type") or alert.get("call_put") or "").upper() == "PUT"
        )
        if call_prem > put_prem * 1.3:
            return "bullish"
        if put_prem > call_prem * 1.3:
            return "bearish"
        return "neutral"

    def _resolve_oi_bias(self, data: Any) -> str:
        payload = self._unwrap_data_payload(data)
        if isinstance(payload, dict):
            call_change = self._safe_float(
                payload.get("call_oi_change", payload.get("call_change", payload.get("call_oi_delta"))),
                0.0,
            )
            put_change = self._safe_float(
                payload.get("put_oi_change", payload.get("put_change", payload.get("put_oi_delta"))),
                0.0,
            )
            if call_change > put_change:
                return "bullish"
            if put_change > call_change:
                return "bearish"
        elif isinstance(payload, list):
            call_change = 0.0
            put_change = 0.0
            for row in payload:
                option_type = str(row.get("type") or row.get("call_put") or "").upper()
                delta = self._safe_float(
                    row.get("oi_change", row.get("change", row.get("open_interest_change"))),
                    0.0,
                )
                if option_type == "CALL":
                    call_change += delta
                elif option_type == "PUT":
                    put_change += delta
            if call_change > put_change:
                return "bullish"
            if put_change > call_change:
                return "bearish"
        return "neutral"

    def _resolve_dp_level_bias(self, dp_levels, current_price_nq: float | None) -> str:
        if not dp_levels or current_price_nq is None:
            return "neutral"
        support_premium = sum(level.total_premium for level in dp_levels if level.price_nq <= current_price_nq)
        resist_premium = sum(level.total_premium for level in dp_levels if level.price_nq > current_price_nq)
        if support_premium > resist_premium * 1.1:
            return "bullish"
        if resist_premium > support_premium * 1.1:
            return "bearish"
        return "neutral"

    def _parse_top_holders(self, data: Any) -> list[InstitutionalHolder]:
        payload = self._unwrap_data_payload(data)
        if not isinstance(payload, list):
            return []
        holders: list[InstitutionalHolder] = []
        for row in payload[:10]:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("institution_name") or "").strip()
            if not name:
                continue
            holders.append(
                InstitutionalHolder(
                    name=name,
                    shares=int(self._safe_float(row.get("shares"), 0.0)),
                    value_usd=self._safe_float(row.get("value_usd", row.get("value")), 0.0),
                    change_shares=int(self._safe_float(row.get("change_shares", row.get("share_change")), 0.0)),
                    pct_of_float=self._safe_float(row.get("pct_of_float", row.get("percent_of_float")), 0.0),
                )
            )
        return holders

    def _parse_recent_filings(self, data: Any) -> list[Filing13F]:
        payload = self._unwrap_data_payload(data)
        if not isinstance(payload, list):
            return []
        filings: list[Filing13F] = []
        for row in payload[:10]:
            if not isinstance(row, dict):
                continue
            institution_name = str(row.get("institution_name") or row.get("name") or "").strip()
            if not institution_name:
                continue
            filings.append(
                Filing13F(
                    institution_name=institution_name,
                    filing_date=str(row.get("filing_date") or row.get("date") or ""),
                    total_value_usd=self._safe_float(row.get("total_value_usd", row.get("value")), 0.0),
                    action=str(row.get("action") or row.get("transaction_type") or ""),
                )
            )
        return filings

    def _parse_floor_trades(self, data: Any) -> list[FloorTrade]:
        payload = self._unwrap_data_payload(data)
        if not isinstance(payload, list):
            return []
        trades: list[FloorTrade] = []
        for row in payload[:25]:
            if not isinstance(row, dict):
                continue
            price = self._safe_float(row.get("price"), 0.0)
            size = int(self._safe_float(row.get("size", row.get("volume")), 0.0))
            if price <= 0 and size <= 0:
                continue
            trades.append(
                FloorTrade(
                    price=price,
                    size=size,
                    premium=self._safe_float(row.get("premium"), 0.0),
                    timestamp=str(row.get("timestamp") or row.get("executed_at") or ""),
                    side=str(row.get("side") or row.get("sentiment") or row.get("direction") or ""),
                )
            )
        return trades

    def _unwrap_data_payload(self, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = data.get("data", data)
        if isinstance(payload, dict) and "data" in payload and len(payload) == 1:
            return payload.get("data")
        return payload

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    async def _poll_massive_with_optional_delay(self) -> MassiveResult:
        if self._cycle_count == 1 and self._initial_massive_delay_sec > 0:
            await asyncio.sleep(self._initial_massive_delay_sec)
        return await self._massive_adapter.poll()

    async def _poll_uw_with_optional_delay(self) -> DarkPoolSummary:
        if self._cycle_count == 1 and self._initial_uw_delay_sec > 0:
            await asyncio.sleep(self._initial_uw_delay_sec)
        return await self._uw_adapter.poll()

    def _build_flashalpha_fallback(self, error_msg: str) -> FlashAlphaResult:
        last = self._last_fa_result
        return FlashAlphaResult(
            levels=last.levels if last else GEXLevels(),
            dealer=last.dealer if last else DealerPositioning(),
            zero_dte=last.zero_dte if last else ZeroDTEState(),
            source_health=SourceHealth(
                name="flashalpha",
                status="error",
                last_update=last.source_health.last_update if last else None,
                ttl_sec=60,
                error_msg=error_msg,
            ),
            raw=last.raw if last else {},
        )

    def _build_massive_fallback(self, error_msg: str) -> MassiveResult:
        last = self._last_massive_result
        return MassiveResult(
            levels=last.levels if last else GEXLevels(),
            source_health=SourceHealth(
                name="massive",
                status="error",
                last_update=last.source_health.last_update if last else None,
                ttl_sec=60,
                error_msg=error_msg,
            ),
            raw_gex_result=last.raw_gex_result if last else None,
            flow_result=last.flow_result if last else None,
        )

    def _build_uw_fallback(self, error_msg: str) -> DarkPoolSummary:
        last = self._last_uw_result
        if last:
            return DarkPoolSummary(
                levels=last.levels,
                net_premium=last.net_premium,
                institutional_bias=last.institutional_bias,
                source_health=SourceHealth(
                    name="unusual_whales",
                    status="error",
                    last_update=last.source_health.last_update,
                    ttl_sec=60,
                    error_msg=error_msg,
                ),
            )
        return DarkPoolSummary(
            source_health=SourceHealth(
                name="unusual_whales",
                status="error",
                ttl_sec=60,
                error_msg=error_msg,
            )
        )

    def _build_fa_from_uw_gex(self, uw_gex: UWGEXResult) -> FlashAlphaResult:
        """Build a synthetic FlashAlphaResult from Unusual Whales GEX data."""
        return FlashAlphaResult(
            levels=uw_gex.levels,
            dealer=uw_gex.dealer,
            zero_dte=uw_gex.zero_dte,
            source_health=SourceHealth(
                name="unusual_whales_gex",
                status=uw_gex.source_health.status,
                last_update=uw_gex.source_health.last_update,
                ttl_sec=60,
                error_msg=uw_gex.source_health.error_msg,
            ),
            raw={},
        )

    def stop(self) -> None:
        """Signal the loop to stop."""
        self._running = False

    def _save_session_learning(self) -> None:
        """Persist one end-of-session learning summary without touching the main loop."""
        self._learner.save_session(notes=f"Session ended after {self._cycle_count} cycles.")

    @property
    def cycle_count(self) -> int:
        return self._cycle_count


__all__ = ["GEXOrchestrator", "BroadcastFn", "ClaudeNarrative", "SourceHealth"]
