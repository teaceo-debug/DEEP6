# FlashAlpha Bridge: Algo Consumption Guide

This file answers one question: given a live NQ algo that needs options positioning context,
which FlashAlpha endpoints do you poll, how often, and how do you structure the output?

For what GEX/vanna/charm mean, see `options-bias-engine/domains/`. For the full API reference,
see `flashalpha-options/api-reference.md`. This file is purely operational.

---

## 1. Polling Schedule

The right cadence balances freshness against API cost and rate limits. FlashAlpha data
updates on their end every 30-60 seconds during market hours, so polling faster than that
wastes calls without gaining freshness.

| Endpoint | Path | Tier | Poll interval | Priority |
|----------|------|------|--------------|----------|
| Exposure levels | `/v1/exposure/levels/QQQ` | Free | 60s | Critical |
| Exposure summary | `/v1/exposure/summary/QQQ` | Growth | 60s | Critical |
| Zero DTE | `/v1/zero_dte/QQQ` | Growth | 30s (0DTE hours only) | Critical |
| GEX by strike | `/v1/exposure/gex/QQQ` | Basic | 120s | High |
| VEX | `/v1/exposure/vex/QQQ` | Basic | 120s | High |
| CHEX | `/v1/exposure/chex/QQQ` | Basic | 120s | High |
| Flow levels | `/v1/flow/levels/QQQ` | Growth | 60s | Medium |
| Volatility | `/v1/volatility/QQQ` | Growth | 300s | Medium |

**0DTE hours:** 9:30 AM to 4:00 PM ET on days with same-day QQQ expiry (every trading day).
Outside those hours, drop zero_dte to 120s.

**After hours:** Drop all intervals to 300s. Data doesn't change meaningfully.

---

## 2. Python Async Polling Loop

The polling loop runs as a background asyncio task. It maintains a shared `FlashAlphaState`
object that the signal engine reads without blocking.

```python
import asyncio
import aiohttp
import time
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

FLASHALPHA_HOST = "https://lab.flashalpha.com"
FLASHALPHA_KEY = os.environ["FLASHALPHA_API_KEY"]

def fa_headers() -> dict:
    return {"X-Api-Key": FLASHALPHA_KEY, "Accept": "application/json"}


@dataclass
class FlashAlphaState:
    """Normalized state from FlashAlpha. Signal engine reads this."""

    # From /v1/exposure/levels
    gamma_flip: float = 0.0
    call_wall: float = 0.0
    put_wall: float = 0.0
    zero_dte_magnet: float = 0.0

    # From /v1/exposure/summary
    gamma_regime: int = 0          # +1 positive, -1 negative, 0 unknown
    net_gex: float = 0.0
    net_dex: float = 0.0
    regime_narrative: str = ""

    # From /v1/zero_dte
    pin_score: float = 0.0         # 0-100
    expected_move_up: float = 0.0  # QQQ points
    expected_move_down: float = 0.0
    gamma_acceleration: float = 0.0
    charm_regime: str = ""         # "dealers_buy" | "dealers_sell" | "neutral"

    # From /v1/exposure/vex
    net_vex: float = 0.0
    vex_interpretation: str = ""   # "vol_up_dealers_buy" etc.

    # From /v1/exposure/chex
    net_chex: float = 0.0
    chex_interpretation: str = ""

    # From /v1/volatility
    atm_iv: float = 0.0
    iv_rank: float = 0.0
    vrp: float = 0.0               # IV - RV, positive = options rich

    # Freshness tracking
    levels_ts: float = 0.0
    summary_ts: float = 0.0
    zero_dte_ts: float = 0.0
    vex_ts: float = 0.0
    chex_ts: float = 0.0
    vol_ts: float = 0.0

    def is_stale(self, field_ts: float, max_age_s: float = 120.0) -> bool:
        return (time.time() - field_ts) > max_age_s


class FlashAlphaPoller:
    def __init__(self, symbol: str = "QQQ"):
        self.symbol = symbol
        self.state = FlashAlphaState()
        self._session: aiohttp.ClientSession | None = None
        self._running = False

    async def start(self):
        self._session = aiohttp.ClientSession()
        self._running = True
        await asyncio.gather(
            self._poll_levels(),
            self._poll_summary(),
            self._poll_zero_dte(),
            self._poll_vex_chex(),
            self._poll_volatility(),
        )

    async def stop(self):
        self._running = False
        if self._session:
            await self._session.close()

    async def _get(self, path: str) -> dict | None:
        url = f"{FLASHALPHA_HOST}{path}"
        try:
            async with self._session.get(url, headers=fa_headers()) as resp:
                if resp.status == 429:
                    logger.warning("FlashAlpha rate limited, backing off 60s")
                    await asyncio.sleep(60)
                    return None
                if resp.status == 402:
                    logger.error(f"FlashAlpha tier restriction: {path}")
                    return None
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as e:
            logger.warning(f"FlashAlpha request failed {path}: {e}")
            return None

    async def _poll_levels(self):
        while self._running:
            data = await self._get(f"/v1/exposure/levels/{self.symbol}")
            if data:
                self._normalize_levels(data)
            await asyncio.sleep(60)

    async def _poll_summary(self):
        while self._running:
            data = await self._get(f"/v1/exposure/summary/{self.symbol}")
            if data:
                self._normalize_summary(data)
            await asyncio.sleep(60)

    async def _poll_zero_dte(self):
        while self._running:
            data = await self._get(f"/v1/zero_dte/{self.symbol}")
            if data:
                self._normalize_zero_dte(data)
            # Tighter interval during 0DTE hours
            interval = 30 if self._is_0dte_hours() else 120
            await asyncio.sleep(interval)

    async def _poll_vex_chex(self):
        while self._running:
            vex = await self._get(f"/v1/exposure/vex/{self.symbol}")
            chex = await self._get(f"/v1/exposure/chex/{self.symbol}")
            if vex:
                self._normalize_vex(vex)
            if chex:
                self._normalize_chex(chex)
            await asyncio.sleep(120)

    async def _poll_volatility(self):
        while self._running:
            data = await self._get(f"/v1/volatility/{self.symbol}")
            if data:
                self._normalize_volatility(data)
            await asyncio.sleep(300)

    def _is_0dte_hours(self) -> bool:
        from datetime import datetime, timezone, time as dtime
        now = datetime.now(timezone.utc)
        # 13:30-20:00 UTC = 9:30 AM - 4:00 PM ET (no DST adjustment here, add if needed)
        return dtime(13, 30) <= now.time() <= dtime(20, 0)
```

---

## 3. Response Normalization

Each endpoint returns a different shape. These normalizers extract only what the signal
engine needs and write it into the shared `FlashAlphaState`.

```python
    def _normalize_levels(self, data: dict):
        """Parse /v1/exposure/levels response."""
        # FlashAlpha returns levels nested under the symbol key
        payload = data.get(self.symbol, data)

        self.state.gamma_flip = float(payload.get("gamma_flip", 0))
        self.state.call_wall = float(payload.get("call_wall", 0))
        self.state.put_wall = float(payload.get("put_wall", 0))
        self.state.zero_dte_magnet = float(payload.get("zero_dte_magnet", 0))
        self.state.levels_ts = time.time()

    def _normalize_summary(self, data: dict):
        """Parse /v1/exposure/summary response."""
        payload = data.get(self.symbol, data)

        # Regime: positive_gamma / negative_gamma
        regime_str = payload.get("gamma_regime", "")
        if "positive" in regime_str:
            self.state.gamma_regime = 1
        elif "negative" in regime_str:
            self.state.gamma_regime = -1
        else:
            self.state.gamma_regime = 0

        self.state.net_gex = float(payload.get("net_gex", 0))
        self.state.net_dex = float(payload.get("net_dex", 0))

        # Narrative is a human-readable string from Growth tier
        interpretations = payload.get("interpretations", {})
        self.state.regime_narrative = interpretations.get("gamma_regime", "")
        self.state.summary_ts = time.time()

    def _normalize_zero_dte(self, data: dict):
        """Parse /v1/zero_dte response."""
        payload = data.get(self.symbol, data)

        pin_risk = payload.get("pin_risk", {})
        self.state.pin_score = float(pin_risk.get("pin_score", 0))

        em = payload.get("expected_move", {})
        self.state.expected_move_up = float(em.get("upper_bound", 0)) - float(
            em.get("spot", 0)
        )
        self.state.expected_move_down = float(em.get("spot", 0)) - float(
            em.get("lower_bound", 0)
        )

        self.state.gamma_acceleration = float(
            payload.get("gamma_acceleration_ratio", 1.0)
        )

        charm = payload.get("charm_regime", "")
        if "buy" in charm:
            self.state.charm_regime = "dealers_buy"
        elif "sell" in charm:
            self.state.charm_regime = "dealers_sell"
        else:
            self.state.charm_regime = "neutral"

        self.state.zero_dte_ts = time.time()

    def _normalize_vex(self, data: dict):
        payload = data.get(self.symbol, data)
        self.state.net_vex = float(payload.get("net_vex", 0))
        self.state.vex_interpretation = payload.get("interpretation", "")
        self.state.vex_ts = time.time()

    def _normalize_chex(self, data: dict):
        payload = data.get(self.symbol, data)
        self.state.net_chex = float(payload.get("net_chex", 0))
        self.state.chex_interpretation = payload.get("interpretation", "")
        self.state.chex_ts = time.time()

    def _normalize_volatility(self, data: dict):
        payload = data.get(self.symbol, data)
        self.state.atm_iv = float(payload.get("atm_iv", 0))
        self.state.iv_rank = float(payload.get("iv_rank", 0))

        # VRP = IV - RV. Positive means options are rich.
        iv = float(payload.get("atm_iv", 0))
        rv = float(payload.get("realized_vol_20d", 0))
        self.state.vrp = iv - rv
        self.state.vol_ts = time.time()
```

---

## 4. Tier Optimization

What you actually get at each price point, ranked by NQ trading value.

### Free ($0) — Minimum viable

Gives you the three most important structural levels:
- `gamma_flip` — the single most important level for regime classification
- `call_wall` — resistance ceiling from dealer hedging
- `put_wall` — support floor from dealer hedging

This alone is enough to classify regime and identify session boundaries.

```python
# Free tier: just levels
async def get_free_tier_levels(symbol: str = "QQQ") -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{FLASHALPHA_HOST}/v1/exposure/levels/{symbol}",
            headers=fa_headers(),
        ) as resp:
            return await resp.json()
```

### Basic ($29/mo) — Adds dealer flow direction

Adds VEX and CHEX, which tell you whether IV moves or time decay create buying or selling
pressure from dealers. Also adds GEX by strike for building your own dealer positioning map.

Key additions:
- `net_vex` + `vex_interpretation` — vanna pressure direction
- `net_chex` + `chex_interpretation` — charm pressure direction
- GEX per strike — build your own level map

### Growth ($49/mo) — Full session context

Adds the summary (regime narrative), zero_dte (pin risk, expected move, charm regime),
flow levels (simulation-adjusted), and volatility (IV rank, VRP, skew).

This is the recommended tier for live NQ algo work. The zero_dte endpoint alone is worth
the upgrade on 0DTE days, which is every trading day for QQQ.

Key additions:
- `exposure_summary` — regime + all metrics in one call
- `zero_dte` — pin score, expected move, gamma acceleration
- `volatility` — IV rank, VRP, term structure

### Alpha ($149/mo) — Historical replay

Adds the historical host (`historical.flashalpha.com`) with `?at=` timestamp parameter.
Required for backtesting. Also adds VRP z-score, SVI parameters, and raw flow data.

```python
# Alpha tier: historical query
async def get_historical_levels(symbol: str, at: str) -> dict:
    """at format: YYYY-MM-DDTHH:mm:ss"""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://historical.flashalpha.com/v1/exposure/levels/{symbol}",
            headers=fa_headers(),
            params={"at": at},
        ) as resp:
            return await resp.json()

# Example: get levels at 10:00 AM ET on 2026-05-20
levels = await get_historical_levels("QQQ", "2026-05-20T14:00:00")
```

---

## 5. Stale Data Detection and Fallback

FlashAlpha can go down or return stale data. The signal engine must know when to trust
the state and when to fall back to degraded mode.

```python
from enum import Enum

class FADataQuality(Enum):
    FRESH = "fresh"       # All critical fields < 90s old
    DEGRADED = "degraded" # Some fields stale, core levels still fresh
    STALE = "stale"       # Core levels > 120s old
    OFFLINE = "offline"   # No successful fetch in > 300s

def assess_data_quality(state: FlashAlphaState) -> FADataQuality:
    now = time.time()

    levels_age = now - state.levels_ts
    summary_age = now - state.summary_ts

    if state.levels_ts == 0:
        return FADataQuality.OFFLINE

    if levels_age > 300:
        return FADataQuality.OFFLINE

    if levels_age > 120:
        return FADataQuality.STALE

    if summary_age > 180:
        return FADataQuality.DEGRADED

    return FADataQuality.FRESH


def get_regime_with_fallback(
    state: FlashAlphaState,
    spot_qqq: float,
) -> int:
    """
    Returns gamma regime (+1/-1/0) with fallback logic.
    If FlashAlpha is stale, derive regime from spot vs gamma_flip.
    """
    quality = assess_data_quality(state)

    if quality == FADataQuality.OFFLINE:
        # No FlashAlpha data at all — return 0 (unknown)
        return 0

    if quality == FADataQuality.STALE:
        # Levels are stale but we still have gamma_flip from last good fetch
        # Derive regime from spot position
        if state.gamma_flip > 0:
            return 1 if spot_qqq > state.gamma_flip else -1
        return 0

    # Fresh or degraded — use the summary regime directly
    return state.gamma_regime


class FlashAlphaCircuitBreaker:
    """Tracks consecutive failures and opens circuit after threshold."""

    def __init__(self, threshold: int = 5, reset_after_s: float = 300.0):
        self.threshold = threshold
        self.reset_after_s = reset_after_s
        self._failures = 0
        self._opened_at: float | None = None

    def record_failure(self):
        self._failures += 1
        if self._failures >= self.threshold:
            self._opened_at = time.time()
            logger.error("FlashAlpha circuit breaker OPEN")

    def record_success(self):
        self._failures = 0
        self._opened_at = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.time() - self._opened_at > self.reset_after_s:
            # Auto-reset after cooldown
            self._opened_at = None
            self._failures = 0
            return False
        return True
```

---

## 6. Signal Engine Integration

The signal engine reads `FlashAlphaState` synchronously. No awaiting needed since the
poller updates it in the background.

```python
from dataclasses import dataclass

@dataclass
class OptionsContext:
    """What the signal engine sees from FlashAlpha."""
    regime: int                    # +1 / -1 / 0
    gamma_flip_qqq: float          # QQQ price
    call_wall_qqq: float
    put_wall_qqq: float
    pin_score: float               # 0-100
    expected_move_up_qqq: float    # QQQ points
    expected_move_down_qqq: float
    charm_regime: str
    vex_direction: str             # "buy" | "sell" | "neutral"
    iv_rank: float                 # 0-100
    vrp: float                     # positive = options rich
    data_quality: FADataQuality


def build_options_context(
    state: FlashAlphaState,
    spot_qqq: float,
) -> OptionsContext:
    quality = assess_data_quality(state)

    # Derive VEX direction from interpretation string
    vex_dir = "neutral"
    if "buy" in state.vex_interpretation:
        vex_dir = "buy"
    elif "sell" in state.vex_interpretation:
        vex_dir = "sell"

    return OptionsContext(
        regime=get_regime_with_fallback(state, spot_qqq),
        gamma_flip_qqq=state.gamma_flip,
        call_wall_qqq=state.call_wall,
        put_wall_qqq=state.put_wall,
        pin_score=state.pin_score,
        expected_move_up_qqq=state.expected_move_up,
        expected_move_down_qqq=state.expected_move_down,
        charm_regime=state.charm_regime,
        vex_direction=vex_dir,
        iv_rank=state.iv_rank,
        vrp=state.vrp,
        data_quality=quality,
    )
```

The signal engine then converts QQQ levels to NQ prices via the proxy pipeline before
using them. See `nq-proxy-pipeline.md` for that conversion.

---

## 7. Complete Startup Sequence

On algo startup, fetch all endpoints once synchronously before starting the polling loop.
This ensures the signal engine has valid data from the first bar.

```python
async def warm_up_flashalpha(poller: FlashAlphaPoller):
    """Fetch all endpoints once at startup. Blocks until complete."""
    logger.info("Warming up FlashAlpha state...")

    endpoints = [
        (f"/v1/exposure/levels/{poller.symbol}", poller._normalize_levels),
        (f"/v1/exposure/summary/{poller.symbol}", poller._normalize_summary),
        (f"/v1/zero_dte/{poller.symbol}", poller._normalize_zero_dte),
        (f"/v1/exposure/vex/{poller.symbol}", poller._normalize_vex),
        (f"/v1/exposure/chex/{poller.symbol}", poller._normalize_chex),
        (f"/v1/volatility/{poller.symbol}", poller._normalize_volatility),
    ]

    async with aiohttp.ClientSession() as session:
        poller._session = session
        for path, normalizer in endpoints:
            data = await poller._get(path)
            if data:
                normalizer(data)
            else:
                logger.warning(f"Warm-up failed for {path}")
            await asyncio.sleep(0.5)  # Avoid burst rate limiting

    quality = assess_data_quality(poller.state)
    logger.info(f"FlashAlpha warm-up complete. Quality: {quality.value}")

    if quality == FADataQuality.OFFLINE:
        raise RuntimeError("FlashAlpha offline at startup — cannot proceed")
```
