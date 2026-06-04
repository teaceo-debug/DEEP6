# NQ Proxy Pipeline: QQQ/NDX to NQ Price Conversion

FlashAlpha and Massive.com cover QQQ and NDX options. NQ futures track the Nasdaq-100 index
directly. Every options level from those sources must be converted to NQ price before the
signal engine can use it. This file defines the conversion math, the `ProxyConverter` class,
recalibration triggers, and edge cases.

---

## 1. Conversion Math

The core relationship:

```
nq_level = qqq_level × (NQ_spot / QQQ_spot)
```

This ratio is not fixed. It drifts intraday due to futures basis, dividend seasonality,
and roll periods. Always compute it fresh at session open and recalibrate on large moves.

```python
def qqq_to_nq(qqq_level: float, nq_spot: float, qqq_spot: float) -> float:
    """Convert a QQQ price level to NQ equivalent."""
    if qqq_spot <= 0:
        raise ValueError("QQQ spot must be positive")
    ratio = nq_spot / qqq_spot
    return qqq_level * ratio


def nq_to_qqq(nq_level: float, nq_spot: float, qqq_spot: float) -> float:
    """Convert an NQ price level to QQQ equivalent."""
    if nq_spot <= 0:
        raise ValueError("NQ spot must be positive")
    ratio = qqq_spot / nq_spot
    return nq_level * ratio
```

**Example at typical market levels:**

```
NQ spot:  21,450
QQQ spot: 487.50
Ratio:    21,450 / 487.50 = 44.0

QQQ gamma_flip = 485.00
NQ gamma_flip  = 485.00 × 44.0 = 21,340
```

---

## 2. Ratio Characteristics

### Typical range

The NQ/QQQ ratio typically sits between 42 and 46, depending on:
- QQQ's current NAV (tracks NDX with ~0.02% tracking error)
- NQ futures basis (fair value premium/discount to cash)
- Dividend seasonality (QQQ pays quarterly dividends; ex-div dates cause ratio jumps)

```python
RATIO_TYPICAL_MIN = 42.0
RATIO_TYPICAL_MAX = 46.0
RATIO_ALERT_THRESHOLD = 0.02  # 2% drift from prior session triggers recalibration
```

### Intraday drift

The ratio drifts throughout the session as:
1. NQ futures basis decays toward cash (convergence at expiry)
2. QQQ trades at slight premium/discount to NAV
3. Large NQ moves create temporary divergence before arbitrage closes it

Typical intraday drift: 0.1-0.3% from open ratio. Spikes to 0.5-1.0% during fast markets.

### NDX vs QQQ ratio

NDX is the cash index. NQ tracks NDX directly. The NDX/QQQ ratio is more stable than NQ/QQQ
because it removes futures basis.

```python
# NDX/QQQ ratio is approximately 44.0 (varies with QQQ NAV)
# NQ/QQQ ratio = NDX/QQQ × (1 + futures_basis_pct)
# futures_basis_pct is typically +0.05% to +0.15% (contango)
```

---

## 3. QQQ vs NDX as Proxy

| Use case | Use QQQ | Use NDX |
|----------|---------|---------|
| 0DTE gamma levels | Yes | No — NDX 0DTE volume is much lower |
| Weekly GEX walls | Yes | Supplement with NDX for institutional strikes |
| Monthly expiry levels | Both | NDX has large institutional OI at round numbers |
| IV surface | Yes | QQQ has more strikes for better interpolation |
| Expected move | Yes | QQQ 0DTE expected move is the market consensus |
| Index-level accuracy | No | NDX has zero tracking error vs NQ |

**Practical rule:** Use QQQ for all FlashAlpha and Massive queries. Convert to NQ via the
NQ/QQQ ratio. Cross-check monthly levels against NDX strikes at round numbers (21,000,
21,500, 22,000) since institutional hedges often sit there.

```python
NDX_ROUND_STRIKES = [
    20000, 20500, 21000, 21500, 22000, 22500, 23000
]

def find_nearby_ndx_strikes(nq_level: float, nq_spot: float, qqq_spot: float) -> list[float]:
    """Find NDX round strikes near an NQ level."""
    ndx_level = nq_to_qqq(nq_level, nq_spot, qqq_spot) * (nq_spot / qqq_spot)
    # NDX ≈ NQ (they track the same index)
    ndx_approx = nq_level  # NQ and NDX are nearly identical in price

    nearby = [s for s in NDX_ROUND_STRIKES if abs(s - ndx_approx) < 200]
    return nearby
```

---

## 4. ProxyConverter Class

The `ProxyConverter` maintains the live ratio and converts all levels on demand.

```python
import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RatioSnapshot:
    ratio: float
    nq_spot: float
    qqq_spot: float
    timestamp: float
    source: str  # "session_open" | "recalibration" | "live"


class ProxyConverter:
    """
    Maintains the live NQ/QQQ ratio and converts options levels to NQ prices.

    Usage:
        converter = ProxyConverter()
        await converter.initialize(nq_spot=21450, qqq_spot=487.50)

        # Convert FlashAlpha levels
        nq_flip = converter.to_nq(fa_state.gamma_flip)
        nq_call_wall = converter.to_nq(fa_state.call_wall)
        nq_put_wall = converter.to_nq(fa_state.put_wall)
    """

    def __init__(self):
        self._ratio: float = 0.0
        self._nq_spot: float = 0.0
        self._qqq_spot: float = 0.0
        self._session_open_ratio: float = 0.0
        self._history: list[RatioSnapshot] = []
        self._last_update: float = 0.0
        self._recal_count: int = 0

    async def initialize(self, nq_spot: float, qqq_spot: float):
        """Call once at session open with fresh spot prices."""
        self._update_ratio(nq_spot, qqq_spot, source="session_open")
        self._session_open_ratio = self._ratio
        logger.info(
            f"ProxyConverter initialized: NQ={nq_spot} QQQ={qqq_spot} "
            f"ratio={self._ratio:.4f}"
        )

    def update(self, nq_spot: float, qqq_spot: float):
        """Update with latest spot prices. Call on every tick."""
        if nq_spot <= 0 or qqq_spot <= 0:
            return

        old_ratio = self._ratio
        self._update_ratio(nq_spot, qqq_spot, source="live")

        # Check for significant drift
        if old_ratio > 0:
            drift = abs(self._ratio - old_ratio) / old_ratio
            if drift > RATIO_ALERT_THRESHOLD:
                logger.warning(
                    f"Ratio drift {drift:.3%}: {old_ratio:.4f} -> {self._ratio:.4f}"
                )

    def _update_ratio(self, nq_spot: float, qqq_spot: float, source: str):
        self._nq_spot = nq_spot
        self._qqq_spot = qqq_spot
        self._ratio = nq_spot / qqq_spot
        self._last_update = time.time()

        snap = RatioSnapshot(
            ratio=self._ratio,
            nq_spot=nq_spot,
            qqq_spot=qqq_spot,
            timestamp=self._last_update,
            source=source,
        )
        self._history.append(snap)

        # Keep last 1000 snapshots
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

    def to_nq(self, qqq_level: float) -> float:
        """Convert a QQQ price level to NQ equivalent."""
        if self._ratio <= 0:
            raise RuntimeError("ProxyConverter not initialized")
        if qqq_level <= 0:
            return 0.0
        return qqq_level * self._ratio

    def to_qqq(self, nq_level: float) -> float:
        """Convert an NQ price level to QQQ equivalent."""
        if self._ratio <= 0:
            raise RuntimeError("ProxyConverter not initialized")
        if nq_level <= 0:
            return 0.0
        return nq_level / self._ratio

    @property
    def ratio(self) -> float:
        return self._ratio

    @property
    def ratio_age_s(self) -> float:
        return time.time() - self._last_update

    def is_stale(self, max_age_s: float = 30.0) -> bool:
        return self.ratio_age_s > max_age_s

    def session_drift(self) -> float:
        """Ratio drift from session open. >2% is unusual."""
        if self._session_open_ratio <= 0:
            return 0.0
        return (self._ratio - self._session_open_ratio) / self._session_open_ratio

    def convert_all_levels(self, fa_state) -> dict[str, float]:
        """
        Convert all FlashAlpha QQQ levels to NQ prices in one call.
        Returns dict of NQ-denominated levels.
        """
        return {
            "gamma_flip": self.to_nq(fa_state.gamma_flip),
            "call_wall": self.to_nq(fa_state.call_wall),
            "put_wall": self.to_nq(fa_state.put_wall),
            "zero_dte_magnet": self.to_nq(fa_state.zero_dte_magnet),
            "expected_move_up": self._nq_spot + self.to_nq(fa_state.expected_move_up),
            "expected_move_down": self._nq_spot - self.to_nq(fa_state.expected_move_down),
        }
```

---

## 5. Recalibration Triggers

The ratio must be recalibrated when it may have drifted significantly.

```python
class RecalibrationTrigger:
    """Monitors conditions that require ratio recalibration."""

    def __init__(self, converter: ProxyConverter):
        self.converter = converter
        self._last_nq_spot: float = 0.0
        self._last_recal_ts: float = 0.0

    def should_recalibrate(
        self,
        nq_spot: float,
        qqq_spot: float,
        macro_event_imminent: bool = False,
    ) -> tuple[bool, str]:
        """
        Returns (should_recal, reason).
        Call on every bar.
        """
        now = time.time()

        # Session open — always recalibrate
        if self.converter._session_open_ratio == 0:
            return True, "session_open"

        # Macro event (FOMC, CPI, NFP) — recalibrate before and after
        if macro_event_imminent:
            return True, "macro_event"

        # Large NQ move (100+ points from last recalibration)
        if self._last_nq_spot > 0:
            nq_move = abs(nq_spot - self._last_nq_spot)
            if nq_move >= 100:
                return True, f"nq_move_{nq_move:.0f}pts"

        # Ratio drift > 2% from session open
        drift = self.converter.session_drift()
        if abs(drift) > RATIO_ALERT_THRESHOLD:
            return True, f"ratio_drift_{drift:.2%}"

        # Time-based: recalibrate every 30 minutes regardless
        if now - self._last_recal_ts > 1800:
            return True, "time_30min"

        return False, ""

    def recalibrate(self, nq_spot: float, qqq_spot: float, reason: str):
        self.converter.update(nq_spot, qqq_spot)
        self._last_nq_spot = nq_spot
        self._last_recal_ts = time.time()
        self.converter._recal_count += 1
        logger.info(
            f"Ratio recalibrated ({reason}): "
            f"NQ={nq_spot} QQQ={qqq_spot} ratio={self.converter.ratio:.4f} "
            f"session_drift={self.converter.session_drift():.3%}"
        )
```

---

## 6. ES/SPY Cross-Validation

NQ and ES are correlated but not identical. When NQ levels from QQQ proxy seem off,
cross-check against ES/SPY levels as a sanity check.

```python
# Approximate relationship (varies with relative performance)
# ES/SPY ratio ≈ 5.0 (ES tracks SPX, SPY tracks SPX)
# NQ/ES ratio ≈ 4.3 (varies with tech vs broad market performance)

ES_SPY_RATIO_TYPICAL = 5.0
NQ_ES_RATIO_TYPICAL = 4.3  # NQ is typically ~4.3x ES

def cross_validate_nq_level(
    nq_level: float,
    es_equivalent_level: float,  # From SPY/ES options
    nq_spot: float,
    es_spot: float,
) -> bool:
    """
    Returns True if NQ level is consistent with ES equivalent.
    A 1% discrepancy is normal. >3% suggests a data error.
    """
    # Convert ES level to NQ equivalent
    nq_es_ratio = nq_spot / es_spot
    nq_from_es = es_equivalent_level * nq_es_ratio

    discrepancy = abs(nq_level - nq_from_es) / nq_spot

    if discrepancy > 0.03:
        logger.warning(
            f"NQ/ES cross-validation failed: "
            f"NQ_level={nq_level} NQ_from_ES={nq_from_es:.0f} "
            f"discrepancy={discrepancy:.2%}"
        )
        return False

    return True
```

**When to use cross-validation:**
- After a large NQ move (>150 points) to confirm walls haven't shifted
- When FlashAlpha and Massive disagree on IV (IV drives expected move)
- At session open when ratio is being established

---

## 7. Edge Cases

### After-hours drift

NQ futures trade nearly 24 hours. QQQ only trades 9:30 AM to 4:00 PM ET (with pre/post
market). After hours, the ratio can drift significantly as NQ moves on overnight news
while QQQ is frozen at its closing price.

```python
def is_qqq_market_hours() -> bool:
    from datetime import datetime, timezone, time as dtime
    now = datetime.now(timezone.utc)
    # 13:30-20:00 UTC = 9:30 AM - 4:00 PM ET
    return dtime(13, 30) <= now.time() <= dtime(20, 0)

def get_ratio_confidence(converter: ProxyConverter) -> float:
    """
    Returns 0.0-1.0 confidence in the current ratio.
    Lower during after-hours when QQQ is stale.
    """
    if not is_qqq_market_hours():
        # After hours: ratio is based on stale QQQ price
        # Confidence decays with time since close
        hours_since_close = (time.time() - converter._last_update) / 3600
        return max(0.1, 1.0 - hours_since_close * 0.1)

    if converter.is_stale(max_age_s=30):
        return 0.5

    return 1.0
```

### Contract roll

NQ rolls quarterly (March, June, September, December). During roll week, the front-month
contract trades at a discount to the next contract. The ratio temporarily diverges.

```python
from datetime import date

NQ_ROLL_WEEKS = [
    # Third Friday of March, June, September, December
    # Add dates as needed
    date(2026, 3, 20),
    date(2026, 6, 19),
    date(2026, 9, 18),
    date(2026, 12, 18),
]

def is_roll_week() -> bool:
    today = date.today()
    for roll_date in NQ_ROLL_WEEKS:
        days_to_roll = (roll_date - today).days
        if 0 <= days_to_roll <= 5:
            return True
    return False

def get_roll_adjusted_ratio(
    converter: ProxyConverter,
    use_continuous: bool = True,
) -> float:
    """
    During roll week, the ratio may need adjustment if using front-month NQ.
    If using continuous contract (NQ1!), no adjustment needed.
    """
    if not is_roll_week():
        return converter.ratio

    if use_continuous:
        # Continuous contract handles roll automatically
        return converter.ratio

    # Front-month during roll: add typical roll basis (~0.1%)
    logger.warning("Roll week: ratio may be distorted by front-month basis")
    return converter.ratio * 1.001  # Approximate adjustment
```

### Dividend adjustments

QQQ pays quarterly dividends. On ex-dividend date, QQQ opens lower by the dividend amount
(typically $0.50-$1.00). This causes a one-time ratio jump.

```python
QQQ_QUARTERLY_DIVIDEND_APPROX = 0.75  # Approximate, varies by quarter

def check_dividend_adjustment(
    converter: ProxyConverter,
    qqq_spot: float,
    prior_close_qqq: float,
) -> bool:
    """
    Returns True if today appears to be QQQ ex-dividend date.
    Triggers a ratio recalibration.
    """
    if prior_close_qqq <= 0:
        return False

    gap = prior_close_qqq - qqq_spot
    # If QQQ opened down by ~dividend amount with no corresponding NQ drop
    if 0.3 < gap < 1.5:
        logger.info(
            f"Possible QQQ ex-dividend: gap={gap:.2f}. Recalibrating ratio."
        )
        return True

    return False
```

---

## 8. Historical Proxy Reconstruction for Backtesting

For backtesting, you need the historical NQ/QQQ ratio at each bar. Don't use today's ratio
for historical data.

```python
import pandas as pd
import numpy as np

def reconstruct_historical_ratios(
    nq_bars: pd.DataFrame,   # columns: timestamp, open, high, low, close
    qqq_bars: pd.DataFrame,  # same schema
) -> pd.Series:
    """
    Compute historical NQ/QQQ ratio aligned by timestamp.
    Returns Series indexed by timestamp.
    """
    # Align on timestamp
    nq = nq_bars.set_index("timestamp")["close"]
    qqq = qqq_bars.set_index("timestamp")["close"]

    # Inner join — only bars where both exist
    aligned = pd.DataFrame({"nq": nq, "qqq": qqq}).dropna()

    ratio = aligned["nq"] / aligned["qqq"]

    # Sanity check
    out_of_range = ratio[(ratio < RATIO_TYPICAL_MIN) | (ratio > RATIO_TYPICAL_MAX)]
    if len(out_of_range) > 0:
        logger.warning(
            f"{len(out_of_range)} bars with ratio outside typical range "
            f"[{RATIO_TYPICAL_MIN}, {RATIO_TYPICAL_MAX}]"
        )

    return ratio


def convert_historical_levels(
    qqq_levels: pd.DataFrame,  # columns: timestamp, gamma_flip, call_wall, put_wall
    historical_ratios: pd.Series,
) -> pd.DataFrame:
    """
    Convert historical QQQ levels to NQ prices using period-accurate ratios.
    """
    # Merge on timestamp
    merged = qqq_levels.set_index("timestamp").join(
        historical_ratios.rename("ratio"), how="left"
    )

    # Forward-fill ratio for timestamps between ratio updates
    merged["ratio"] = merged["ratio"].ffill()

    # Convert all level columns
    level_cols = ["gamma_flip", "call_wall", "put_wall", "zero_dte_magnet"]
    for col in level_cols:
        if col in merged.columns:
            merged[f"nq_{col}"] = merged[col] * merged["ratio"]

    return merged.reset_index()
```

### Backtesting with Databento MBO data

When replaying historical NQ data from Databento, use the NQ price from the MBO feed
directly. The QQQ ratio is only needed to convert FlashAlpha levels.

```python
async def backtest_session(
    date: str,  # YYYY-MM-DD
    fa_historical_client,  # FlashAlpha Alpha tier client
    databento_client,
):
    """
    Replay a historical session with period-accurate proxy conversion.
    """
    # Fetch historical FlashAlpha levels at session open
    session_open_levels = await fa_historical_client.get_levels(
        "QQQ", at=f"{date}T13:30:00"  # 9:30 AM ET
    )

    # Get historical QQQ spot at open (from Massive flat files or Databento)
    qqq_open = await get_historical_qqq_spot(date, "09:30:00")
    nq_open = await get_historical_nq_spot(date, "09:30:00")

    converter = ProxyConverter()
    await converter.initialize(nq_spot=nq_open, qqq_spot=qqq_open)

    # Convert levels to NQ
    nq_levels = converter.convert_all_levels(session_open_levels)

    # Now replay NQ MBO data from Databento
    async for event in databento_client.replay(date):
        nq_price = event.price / 1e9  # Databento fixed-point

        # Recalibrate ratio periodically during replay
        # (use historical QQQ prices from flat files)
        qqq_price = await get_historical_qqq_spot(date, event.ts_event)
        converter.update(nq_price, qqq_price)

        # Signal engine uses nq_levels (already in NQ price)
        yield event, nq_levels, converter.ratio
```

---

## 9. Complete Integration Example

```python
async def main():
    from .data_fusion import OptionsFusionLoop, OptionsState
    from .flashalpha_bridge import FlashAlphaPoller

    # Initialize converter with session open prices
    converter = ProxyConverter()
    recal_trigger = RecalibrationTrigger(converter)

    # Get initial spots (from Massive quote or broker feed)
    nq_spot = 21450.0   # From Rithmic/async-rithmic
    qqq_spot = 487.50   # From Massive quote

    await converter.initialize(nq_spot=nq_spot, qqq_spot=qqq_spot)

    # Start fusion system
    fa_poller = FlashAlphaPoller("QQQ")
    fusion = OptionsFusionLoop(fa_poller, ...)

    # On each NQ bar
    async for bar in nq_bar_stream():
        nq_spot = bar.close
        qqq_spot = await get_qqq_spot()  # From Massive WebSocket

        # Check if recalibration needed
        should_recal, reason = recal_trigger.should_recalibrate(nq_spot, qqq_spot)
        if should_recal:
            recal_trigger.recalibrate(nq_spot, qqq_spot, reason)

        # Convert all FA levels to NQ
        fa_state = fusion.state
        nq_levels = converter.convert_all_levels(fa_state)

        # Signal engine now has NQ-denominated levels
        signal_engine.update(
            nq_spot=nq_spot,
            gamma_flip_nq=nq_levels["gamma_flip"],
            call_wall_nq=nq_levels["call_wall"],
            put_wall_nq=nq_levels["put_wall"],
            pin_score=fa_state.pin_score,
            gamma_regime=fa_state.gamma_regime,
        )
```
