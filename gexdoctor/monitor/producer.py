from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from .adapters.flashalpha import FlashAlphaAdapter
from .convert import compute_nq_qqq_factor
from .interpreter import PositioningInterpreter
from .logger import AuditTrail
from .magnet_scorer import MagnetScorer
from .price_service import NQPriceService
from .schemas import EnrichedGexOutput, FARegime, FlashAlphaSnapshot

log = logging.getLogger(__name__)
__all__ = ["GexDoctorProducer"]

_DEFAULT_OUTPUT = Path(
    r"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\gex_nq.json"
)


class GexDoctorProducer:
    """Main orchestrator. Polls FlashAlpha, scores magnets, writes enriched gex_nq.json.

    Pipeline per cycle:
    1. get NQ spot price
    2. fetch FlashAlpha snapshot
    3. normalize QQQ levels to NQ
    4. interpret snapshot -> BiasResult
    5. score magnet candidates -> MagnetResult
    6. build EnrichedGexOutput
    7. write atomically to output path
    8. write audit trail
    """

    def __init__(
        self,
        flashalpha_adapter: FlashAlphaAdapter,
        price_service: NQPriceService,
        scorer: MagnetScorer,
        interpreter: PositioningInterpreter,
        output_path: Path = _DEFAULT_OUTPUT,
        log_dir: Path = Path("logs"),
        interval_sec: int = 15,
    ) -> None:
        self.adapter = flashalpha_adapter
        self.price_service = price_service
        self.scorer = scorer
        self.interpreter = interpreter
        self.output_path = output_path
        self.interval_sec = max(interval_sec, 15)
        self.audit = AuditTrail(log_dir)
        self._last_output: EnrichedGexOutput | None = None
        self._consecutive_failures = 0

    async def run_cycle(self) -> EnrichedGexOutput | None:
        """Run one complete poll-score-write cycle. Returns output or None on failure."""
        t0 = time.monotonic()
        errors: list[str] = []

        # Step 1: NQ price
        current_nq = 0.0
        qqq_factor: float | None = None
        try:
            quote = await self.price_service.get_nq_quote()
            current_nq = quote.nq_price
            qqq_factor = quote.nq_qqq_factor
        except Exception as exc:
            errors.append(f"price_service: {exc}")
            current_nq = self._last_output.flip if self._last_output and self._last_output.flip else 0.0
            log.warning("NQ price unavailable, using fallback: %s", exc)

        # Step 2: FlashAlpha snapshot
        snapshot: FlashAlphaSnapshot | None = None
        try:
            snapshot = await self.adapter.poll()
        except Exception as exc:
            errors.append(f"flashalpha: {exc}")
            log.warning("FlashAlpha poll failed: %s", exc)

        if snapshot is None:
            if self._last_output is not None:
                stale = self._build_stale_output(self._last_output)
                self._write_atomic(stale)
                return stale
            return None

        # Step 3: Normalize QQQ levels to NQ
        try:
            factor = qqq_factor or (
                compute_nq_qqq_factor(current_nq, snapshot.underlying_price)
                if snapshot.underlying_price > 0 and current_nq > 0
                else 45.0
            )
        except Exception as exc:
            errors.append(f"conversion: {exc}")
            factor = 45.0
            log.warning("QQQ->NQ conversion failed, using fallback factor: %s", exc)

        nq_flip = self._scale(snapshot.regime.gamma_flip, factor)
        nq_call = self._scale(snapshot.regime.call_wall, factor)
        nq_put = self._scale(snapshot.regime.put_wall, factor)
        nq_max_pain = self._scale(snapshot.regime.max_pain, factor)

        nq_snapshot = self._make_nq_snapshot(
            snapshot, current_nq, nq_flip, nq_call, nq_put, nq_max_pain,
        )

        # Step 4: Interpret
        bias = None
        try:
            bias = self.interpreter.interpret(nq_snapshot)
        except Exception as exc:
            errors.append(f"interpreter: {exc}")
            log.warning("Interpreter failed: %s", exc)

        # Step 5: Score magnets
        magnet = None
        try:
            magnet = self.scorer.score(nq_snapshot, current_nq)
        except Exception as exc:
            errors.append(f"magnet_scorer: {exc}")
            log.warning("Magnet scorer failed: %s", exc)

        # Step 6: Build enriched output
        regime_str = "POS_GEX" if snapshot.regime.gex_sign == "positive" else "NEG_GEX"

        output = EnrichedGexOutput(
            instrument="NQ",
            flip=nq_flip,
            call_wall=nq_call,
            put_wall=nq_put,
            net_gex=snapshot.regime.net_gex,
            regime=regime_str,
            primary_magnet=magnet.primary_magnet if magnet else None,
            magnet_confidence=magnet.magnet_confidence if magnet else 0.0,
            bias_direction=bias.direction if bias else "no_vote",
            invalidation_level=magnet.invalidation_level if magnet else None,
            invalidation_reason=magnet.invalidation_reason if magnet else "",
            lean=bias.lean if bias else "",
            pin_risk=snapshot.pin.pin_risk,
            max_pain=nq_max_pain,
            caveats=bias.caveats if bias else [],
            as_of=snapshot.timestamp,
            source=f"flashalpha-{snapshot.symbol}-x{factor:.2f}",
        )

        # Step 7: Write atomically
        self._write_atomic(output)
        self._last_output = output
        self._consecutive_failures = 0

        # Step 8: Audit
        elapsed_ms = (time.monotonic() - t0) * 1000
        self.audit.record(
            sources_polled=["flashalpha"],
            levels_received=sum(1 for v in [nq_flip, nq_call, nq_put, nq_max_pain] if v),
            magnet_selected=output.primary_magnet,
            confidence=output.magnet_confidence,
            bias_direction=output.bias_direction,
            errors=errors,
            extra={"latency_ms": round(elapsed_ms, 1)},
        )

        return output

    async def run_loop(self) -> None:
        """Continuous polling loop. Runs until cancelled."""
        log.info("GexDoctorProducer loop started (interval=%ds)", self.interval_sec)
        while True:
            try:
                await self.run_cycle()
            except asyncio.CancelledError:
                log.info("Producer loop cancelled — shutting down")
                raise
            except Exception as exc:
                self._consecutive_failures += 1
                log.error(
                    "Cycle error (failure #%d): %s",
                    self._consecutive_failures, exc,
                )
                if self._consecutive_failures >= 5:
                    log.error("5 consecutive failures — sleeping 5 minutes")
                    await asyncio.sleep(300)
                    self._consecutive_failures = 0
            await asyncio.sleep(self.interval_sec)

    def _scale(self, level: float | None, factor: float) -> float | None:
        if level is None:
            return None
        return round(level * factor, 2)

    def _make_nq_snapshot(
        self,
        snapshot: FlashAlphaSnapshot,
        nq_price: float,
        nq_flip: float | None,
        nq_call: float | None,
        nq_put: float | None,
        nq_max_pain: float | None,
    ) -> FlashAlphaSnapshot:
        """Return snapshot with levels converted to NQ equivalents for scorer."""
        new_regime = FARegime(
            net_gex=snapshot.regime.net_gex,
            gex_sign=snapshot.regime.gex_sign,
            net_dex=snapshot.regime.net_dex,
            gamma_flip=nq_flip or snapshot.regime.gamma_flip,
            call_wall=nq_call,
            put_wall=nq_put,
            max_pain=nq_max_pain,
        )
        return snapshot.model_copy(update={
            "underlying_price": nq_price,
            "regime": new_regime,
        })

    def _build_stale_output(self, last: EnrichedGexOutput) -> EnrichedGexOutput:
        return last.model_copy(update={
            "as_of": datetime.now(timezone.utc).isoformat(),
            "source": last.source + "-stale",
        })

    def _write_atomic(self, output: EnrichedGexOutput) -> None:
        """Write JSON atomically: write to .tmp then rename.
        Prevents NT8 from reading a partially-written file.
        """
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.output_path.with_suffix(".json.tmp")
        payload = output.model_dump()
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.output_path)
        log.debug("wrote %s (magnet=%s)", self.output_path.name, output.primary_magnet)
