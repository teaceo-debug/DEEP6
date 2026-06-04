from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from ..schemas import FADealerRisk, FAFeedQuality, FAOISimulator, FAPinData, FARegime, FlashAlphaSnapshot

log = logging.getLogger(__name__)

__all__ = ["FlashAlphaAdapter"]

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="flashalpha")

BASE_URL = "https://lab.flashalpha.com"
MIN_CADENCE_SEC = 15


class FlashAlphaAdapter:
    """Async adapter for FlashAlpha exposure/flow API."""

    def __init__(self, api_key: str, symbol: str = "QQQ") -> None:
        self.api_key = api_key
        self.symbol = symbol
        self._last_poll = 0.0
        self._stale_threshold_sec = 120.0
        self._consecutive_failures = 0
        self._fa: Any | None = None
        self._sdk_available = False

        try:
            import flashalpha as _fa

            self._fa = _fa
            self._sdk_available = True
        except ImportError:
            log.warning("flashalpha SDK not installed — using httpx fallback")

    async def poll(self) -> FlashAlphaSnapshot | None:
        """Fetch current snapshot. Returns None on complete failure."""
        elapsed = time.monotonic() - self._last_poll
        if self._last_poll > 0 and elapsed < MIN_CADENCE_SEC:
            log.debug("cadence guard: %.1fs since last poll, skipping", elapsed)
            return None

        self._last_poll = time.monotonic()
        t0 = time.monotonic()

        try:
            snapshot = await self._fetch_live_bundle()
            if snapshot is None:
                snapshot = await self._fetch_settled_fallback()

            if snapshot is None:
                self._consecutive_failures += 1
                log.error("flashalpha poll failed (attempt %d): no data", self._consecutive_failures)
                return None

            self._consecutive_failures = 0
            latency_ms = (time.monotonic() - t0) * 1000
            log.info(
                "flashalpha poll OK symbol=%s latency_ms=%.0f regime=%s",
                self.symbol,
                latency_ms,
                snapshot.regime.gex_sign,
            )
            return snapshot
        except Exception as exc:
            self._consecutive_failures += 1
            log.error("flashalpha poll failed (attempt %d): %s", self._consecutive_failures, exc)
            return None

    async def _fetch_live_bundle(self) -> FlashAlphaSnapshot | None:
        loop = asyncio.get_running_loop()
        try:
            raw = await loop.run_in_executor(_EXECUTOR, self._sdk_get_live_bundle)
            if raw is None:
                return None
            return self._parse_live_bundle(raw)
        except Exception as exc:
            log.debug("live bundle failed, will try settled fallback: %s", exc)
            return None

    def _sdk_get_live_bundle(self) -> dict[str, Any] | None:
        if not self._sdk_available:
            return self._httpx_get_live_bundle()

        try:
            sdk = self._fa
            if sdk is None:
                return self._httpx_get_live_bundle()

            if hasattr(sdk, "Client"):
                client = sdk.Client(api_key=self.api_key)
                result = client.flow.live(self.symbol)
            elif hasattr(sdk, "FlashAlpha"):
                client = sdk.FlashAlpha(self.api_key)
                result = client.flow_live(self.symbol)
            else:
                return self._httpx_get_live_bundle()

            return self._coerce_to_dict(result)
        except Exception as exc:
            log.debug("SDK live bundle error: %s", exc)
            return self._httpx_get_live_bundle()

    def _httpx_get_live_bundle(self) -> dict[str, Any] | None:
        import httpx

        try:
            response = httpx.get(
                f"{BASE_URL}/v1/flow/live/{self.symbol}",
                headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            log.debug("httpx live bundle error: %s", exc)
            return None

    def _parse_live_bundle(self, raw: dict[str, Any]) -> FlashAlphaSnapshot:
        payload = self._unwrap_symbol_payload(raw)
        missing: list[str] = []

        net_gex = self._as_float(payload.get("live_gex"), default=0.0)
        gex_sign = "positive" if net_gex >= 0 else "negative"
        dealer_risk_payload = payload.get("flow_adjusted_dealer_risk") or {}

        net_dex = self._as_optional_float(dealer_risk_payload.get("live_net_dex"))
        if net_dex is None:
            missing.append("net_dex")

        underlying_price = self._as_float(payload.get("underlying_price") or payload.get("spot"), default=0.0)
        if underlying_price == 0.0 and payload.get("underlying_price") in (None, "") and payload.get("spot") in (None, ""):
            missing.append("underlying_price")

        timestamp = self._coerce_timestamp(payload.get("as_of"))
        latency_seconds = self._compute_latency_seconds(timestamp)
        if latency_seconds is not None and latency_seconds > self._stale_threshold_sec:
            missing.append("stale")

        regime = FARegime(
            net_gex=net_gex,
            gex_sign=gex_sign,
            net_dex=net_dex,
            gamma_flip=self._as_float(payload.get("live_gamma_flip"), default=0.0),
            call_wall=self._as_optional_float(payload.get("live_call_wall")),
            put_wall=self._as_optional_float(payload.get("live_put_wall")),
            max_pain=self._as_optional_float(payload.get("live_max_pain")),
        )

        flow_direction = dealer_risk_payload.get("flow_direction") or "neutral"
        if flow_direction not in {"amplifying", "dampening", "regime flip", "neutral"}:
            flow_direction = "neutral"

        dealer_risk = FADealerRisk(
            flow_direction=flow_direction,
            flow_gex_pct_shift=self._as_optional_float(dealer_risk_payload.get("flow_gex_pct_shift")),
            flow_dex_pct_shift=self._as_optional_float(dealer_risk_payload.get("flow_dex_pct_shift")),
            settled_net_gex=self._as_optional_float(dealer_risk_payload.get("settled_net_gex")),
            settled_net_dex=self._as_optional_float(dealer_risk_payload.get("settled_net_dex")),
            total_abs_delta_contracts=self._as_optional_float(dealer_risk_payload.get("total_abs_delta_contracts")),
            description=dealer_risk_payload.get("description"),
        )

        pin = FAPinData(
            pin_risk=self._as_optional_float(payload.get("live_pin_risk")),
            magnet_strike=self._as_optional_float(payload.get("live_max_pain")),
        )

        oi_simulator = FAOISimulator(
            contracts_with_flow=self._as_optional_int(payload.get("contracts_with_flow")),
            intraday_oi_delta=self._as_optional_float(payload.get("intraday_oi_delta")),
            oi_delta_confidence=self._as_optional_float(payload.get("oi_delta_confidence")),
        )

        return FlashAlphaSnapshot(
            timestamp=timestamp,
            symbol=self.symbol,
            underlying_price=underlying_price,
            expiry=payload.get("expiry"),
            dte=self._as_optional_int(payload.get("dte")),
            session_phase=self._detect_session_phase(),
            regime=regime,
            dealer_risk=dealer_risk,
            pin=pin,
            oi_simulator=oi_simulator,
            feed_quality=FAFeedQuality(
                plan="alpha",
                latency_seconds=latency_seconds,
                missing_fields=missing,
            ),
        )

    async def _fetch_settled_fallback(self) -> FlashAlphaSnapshot | None:
        loop = asyncio.get_running_loop()
        try:
            raw = await loop.run_in_executor(_EXECUTOR, self._httpx_get_settled)
            if raw is None:
                return None
            return self._parse_settled(raw)
        except Exception as exc:
            log.error("settled fallback also failed: %s", exc)
            return None

    def _httpx_get_settled(self) -> dict[str, Any] | None:
        import httpx

        try:
            with httpx.Client(headers={"X-Api-Key": self.api_key, "Accept": "application/json"}, timeout=10) as client:
                gex_response = client.get(f"{BASE_URL}/v1/exposure/gex/{self.symbol}")
                gex_response.raise_for_status()
                levels_response = client.get(f"{BASE_URL}/v1/exposure/levels/{self.symbol}")
                levels_response.raise_for_status()
                return {
                    "gex": gex_response.json(),
                    "levels": levels_response.json(),
                }
        except Exception as exc:
            log.debug("httpx settled fetch error: %s", exc)
            return None

    def _parse_settled(self, raw: dict[str, Any]) -> FlashAlphaSnapshot:
        gex_payload = self._unwrap_symbol_payload(raw.get("gex") or {})
        levels_payload = self._unwrap_symbol_payload(raw.get("levels") or {})

        net_gex = self._as_float(gex_payload.get("net_gex"), default=0.0)
        gex_sign = "positive" if net_gex >= 0 else "negative"
        underlying_price = self._as_float(levels_payload.get("spot") or gex_payload.get("spot"), default=0.0)

        return FlashAlphaSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol=self.symbol,
            underlying_price=underlying_price,
            session_phase=self._detect_session_phase(),
            regime=FARegime(
                net_gex=net_gex,
                gex_sign=gex_sign,
                net_dex=None,
                gamma_flip=self._as_float(levels_payload.get("gamma_flip") or gex_payload.get("gamma_flip"), default=0.0),
                call_wall=self._as_optional_float(levels_payload.get("call_wall")),
                put_wall=self._as_optional_float(levels_payload.get("put_wall")),
                max_pain=self._as_optional_float(levels_payload.get("max_pain")),
            ),
            dealer_risk=FADealerRisk(
                flow_direction="neutral",
                flow_gex_pct_shift=None,
                flow_dex_pct_shift=None,
                settled_net_gex=net_gex,
                settled_net_dex=None,
            ),
            feed_quality=FAFeedQuality(
                plan="basic",
                latency_seconds=None,
                missing_fields=["flow_direction", "oi_delta_confidence", "pin_risk"],
            ),
        )

    def _detect_session_phase(self) -> str:
        try:
            import zoneinfo

            eastern = zoneinfo.ZoneInfo("America/New_York")
            now_et = datetime.now(timezone.utc).astimezone(eastern)
        except Exception:
            return "intraday"

        total_minutes = now_et.hour * 60 + now_et.minute
        if total_minutes < 9 * 60 + 30:
            return "pre_market"
        if total_minutes < 10 * 60:
            return "open"
        if total_minutes < 15 * 60:
            return "intraday"
        return "into_close"

    @staticmethod
    def _coerce_to_dict(result: Any) -> dict[str, Any] | None:
        if result is None:
            return None
        if isinstance(result, dict):
            return result
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if hasattr(result, "dict"):
            return result.dict()
        if hasattr(result, "__dict__"):
            return dict(result.__dict__)
        return dict(result)

    def _coerce_timestamp(self, value: Any) -> str:
        if isinstance(value, str) and value:
            return value
        return datetime.now(timezone.utc).isoformat()

    def _compute_latency_seconds(self, timestamp: str) -> float | None:
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())
        except Exception:
            return None

    def _unwrap_symbol_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        nested = payload.get(self.symbol)
        if isinstance(nested, dict):
            return nested
        return payload

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_optional_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_optional_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None
