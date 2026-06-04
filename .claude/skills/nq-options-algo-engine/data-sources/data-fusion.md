# Data Fusion: Massive + FlashAlpha into OptionsState

Massive.com provides raw market data: tick trades, quotes, Greeks computed from market prices,
and OI. FlashAlpha provides derived analytics: dealer positioning, regime classification,
and exposure metrics computed from their own models.

These two sources overlap on some fields (IV, Greeks) and complement each other on others.
This file defines the unified `OptionsState` dataclass, the rules for which source wins
each field, and the async fusion loop that keeps it current.

---

## 1. Unified OptionsState Dataclass

Every field the signal engine needs, with source annotation.

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import time

@dataclass
class StrikeData:
    """Per-strike options data. One instance per strike price."""
    strike: float

    # From Massive snapshot
    call_bid: float = 0.0
    call_ask: float = 0.0
    call_mid: float = 0.0
    call_iv: float = 0.0           # Massive-computed IV
    call_delta: float = 0.0
    call_gamma: float = 0.0
    call_theta: float = 0.0
    call_vega: float = 0.0
    call_oi: int = 0
    call_volume: int = 0
    call_vwap: float = 0.0

    put_bid: float = 0.0
    put_ask: float = 0.0
    put_mid: float = 0.0
    put_iv: float = 0.0
    put_delta: float = 0.0
    put_gamma: float = 0.0
    put_theta: float = 0.0
    put_vega: float = 0.0
    put_oi: int = 0
    put_volume: int = 0
    put_vwap: float = 0.0

    # Derived from Massive data
    gex_contribution: float = 0.0  # (call_gamma * call_oi - put_gamma * put_oi) * 100 * spot
    net_delta: float = 0.0         # call_delta * call_oi - put_delta * put_oi

    # Freshness
    massive_ts: float = 0.0


@dataclass
class OptionsState:
    """
    Unified options state consumed by the signal engine.
    Updated continuously by the fusion loop.
    """

    # --- Structural levels (source: FlashAlpha, fallback: derived from Massive) ---
    gamma_flip: float = 0.0        # QQQ price
    call_wall: float = 0.0
    put_wall: float = 0.0
    zero_dte_magnet: float = 0.0

    # --- Regime (source: FlashAlpha) ---
    gamma_regime: int = 0          # +1 / -1 / 0
    regime_narrative: str = ""

    # --- Dealer flow direction (source: FlashAlpha) ---
    net_gex: float = 0.0
    net_dex: float = 0.0
    net_vex: float = 0.0
    net_chex: float = 0.0
    vex_interpretation: str = ""
    chex_interpretation: str = ""
    charm_regime: str = ""

    # --- 0DTE analytics (source: FlashAlpha) ---
    pin_score: float = 0.0
    expected_move_up: float = 0.0  # QQQ points above spot
    expected_move_down: float = 0.0
    gamma_acceleration: float = 1.0

    # --- Volatility (source: FlashAlpha primary, Massive fallback) ---
    atm_iv: float = 0.0            # FlashAlpha ATM IV
    iv_rank: float = 0.0
    vrp: float = 0.0               # IV - RV20
    massive_atm_iv: float = 0.0    # Massive-computed ATM IV (for conflict detection)

    # --- Per-strike chain (source: Massive) ---
    chain: dict[float, StrikeData] = field(default_factory=dict)

    # --- Spot prices (source: Massive real-time quote) ---
    spot_qqq: float = 0.0
    spot_ndx: float = 0.0          # From Massive NDX quote or derived

    # --- Data quality ---
    fa_quality: str = "offline"    # "fresh" | "degraded" | "stale" | "offline"
    massive_quality: str = "offline"
    last_fusion_ts: float = 0.0

    def age_s(self) -> float:
        return time.time() - self.last_fusion_ts

    def is_tradeable(self) -> bool:
        """Returns True only if minimum viable data is present and fresh."""
        return (
            self.gamma_flip > 0
            and self.spot_qqq > 0
            and self.age_s() < 120
            and self.fa_quality in ("fresh", "degraded")
        )
```

---

## 2. Source Priority Rules

When both sources provide a value for the same field, this table defines which wins.

| Field | Primary source | Fallback | Reason |
|-------|---------------|----------|--------|
| `gamma_flip` | FlashAlpha | None | FA models dealer positioning; Massive has no equivalent |
| `call_wall` | FlashAlpha | Derived from chain | Same |
| `put_wall` | FlashAlpha | Derived from chain | Same |
| `gamma_regime` | FlashAlpha | Spot vs flip | FA has narrative context; spot vs flip is mechanical fallback |
| `net_gex` | FlashAlpha | Computed from chain | FA includes all expirations; Massive chain may be partial |
| `atm_iv` | FlashAlpha | Massive | FA IV is model-smoothed; use Massive for conflict detection |
| `call_gamma` per strike | Massive | None | Massive has per-contract Greeks; FA only has aggregates |
| `call_oi` per strike | Massive | None | Massive has real-time OI; FA uses delayed OI |
| `pin_score` | FlashAlpha | None | FA proprietary model |
| `expected_move` | FlashAlpha | Massive ATM IV * sqrt(T) | FA accounts for skew; Massive is simpler |
| `spot_qqq` | Massive | None | Real-time quote from Massive |

---

## 3. Conflict Resolution

The two sources can disagree on IV. This matters because IV drives regime interpretation.

```python
import logging

logger = logging.getLogger(__name__)

IV_CONFLICT_THRESHOLD = 0.03  # 3 vol points absolute difference

def resolve_iv_conflict(
    fa_iv: float,
    massive_iv: float,
    state: "OptionsState",
) -> float:
    """
    Returns the IV to use. Logs conflicts for monitoring.
    FlashAlpha wins unless it's stale or the gap is extreme.
    """
    if fa_iv == 0:
        return massive_iv

    if massive_iv == 0:
        return fa_iv

    diff = abs(fa_iv - massive_iv)

    if diff > IV_CONFLICT_THRESHOLD:
        logger.warning(
            f"IV conflict: FA={fa_iv:.4f} Massive={massive_iv:.4f} "
            f"diff={diff:.4f}. Using FA."
        )
        # Log for monitoring but still use FA
        # If this fires repeatedly, investigate FA model lag

    # FlashAlpha wins — it's model-smoothed and accounts for skew
    return fa_iv


def derive_call_wall_from_chain(chain: dict[float, "StrikeData"]) -> float:
    """
    Fallback call wall: strike with highest call GEX contribution above spot.
    Used when FlashAlpha is offline.
    """
    if not chain:
        return 0.0

    # Find spot from chain (approximate)
    strikes = sorted(chain.keys())
    if not strikes:
        return 0.0

    # Highest GEX call strike above median
    median_strike = strikes[len(strikes) // 2]
    above = {s: d for s, d in chain.items() if s > median_strike}

    if not above:
        return 0.0

    return max(above.keys(), key=lambda s: above[s].call_gamma * above[s].call_oi)


def derive_put_wall_from_chain(chain: dict[float, "StrikeData"]) -> float:
    """Fallback put wall: strike with highest put GEX contribution below spot."""
    if not chain:
        return 0.0

    strikes = sorted(chain.keys())
    median_strike = strikes[len(strikes) // 2]
    below = {s: d for s, d in chain.items() if s < median_strike}

    if not below:
        return 0.0

    return max(below.keys(), key=lambda s: below[s].put_gamma * below[s].put_oi)
```

---

## 4. Data Freshness Management

Each field has a staleness threshold. The fusion loop tracks timestamps per source.

```python
from enum import Enum

class DataQuality(Enum):
    FRESH = "fresh"
    DEGRADED = "degraded"
    STALE = "stale"
    OFFLINE = "offline"

# Staleness thresholds in seconds
THRESHOLDS = {
    "fa_levels": 120,      # gamma_flip, walls — critical
    "fa_summary": 180,     # regime, net_gex
    "fa_zero_dte": 90,     # pin_score, expected_move
    "fa_vex_chex": 180,    # vex, chex
    "fa_vol": 360,         # IV rank, VRP
    "massive_chain": 60,   # per-strike Greeks and OI
    "massive_quote": 5,    # spot price
}

@dataclass
class FreshnessTracker:
    fa_levels_ts: float = 0.0
    fa_summary_ts: float = 0.0
    fa_zero_dte_ts: float = 0.0
    fa_vex_chex_ts: float = 0.0
    fa_vol_ts: float = 0.0
    massive_chain_ts: float = 0.0
    massive_quote_ts: float = 0.0

    def fa_quality(self) -> DataQuality:
        now = time.time()
        if self.fa_levels_ts == 0:
            return DataQuality.OFFLINE
        if now - self.fa_levels_ts > THRESHOLDS["fa_levels"] * 2.5:
            return DataQuality.OFFLINE
        if now - self.fa_levels_ts > THRESHOLDS["fa_levels"]:
            return DataQuality.STALE
        if now - self.fa_summary_ts > THRESHOLDS["fa_summary"]:
            return DataQuality.DEGRADED
        return DataQuality.FRESH

    def massive_quality(self) -> DataQuality:
        now = time.time()
        if self.massive_quote_ts == 0:
            return DataQuality.OFFLINE
        if now - self.massive_quote_ts > THRESHOLDS["massive_quote"] * 10:
            return DataQuality.STALE
        if now - self.massive_chain_ts > THRESHOLDS["massive_chain"] * 2:
            return DataQuality.DEGRADED
        return DataQuality.FRESH
```

---

## 5. Real-Time Fusion Loop

The fusion loop runs as a background asyncio task. It reads from both pollers and writes
into the shared `OptionsState`.

```python
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .flashalpha_bridge import FlashAlphaPoller, FlashAlphaState
    from .massive_api import MassivePoller

class OptionsFusionLoop:
    def __init__(
        self,
        fa_poller: "FlashAlphaPoller",
        massive_poller: "MassivePoller",
    ):
        self.fa = fa_poller
        self.massive = massive_poller
        self.state = OptionsState()
        self.freshness = FreshnessTracker()
        self._running = False

    async def start(self):
        self._running = True
        # Run fusion at 10Hz — fast enough for signal engine, not wasteful
        while self._running:
            self._fuse()
            await asyncio.sleep(0.1)

    def _fuse(self):
        """Merge FA and Massive state into unified OptionsState."""
        fa = self.fa.state
        massive = self.massive

        now = time.time()

        # --- Spot price from Massive (highest priority, freshest) ---
        if massive.spot_qqq > 0:
            self.state.spot_qqq = massive.spot_qqq
            self.freshness.massive_quote_ts = now

        # --- Structural levels from FlashAlpha ---
        if fa.levels_ts > self.freshness.fa_levels_ts:
            self.state.gamma_flip = fa.gamma_flip
            self.state.call_wall = fa.call_wall
            self.state.put_wall = fa.put_wall
            self.state.zero_dte_magnet = fa.zero_dte_magnet
            self.freshness.fa_levels_ts = fa.levels_ts

        # --- Regime from FlashAlpha ---
        if fa.summary_ts > self.freshness.fa_summary_ts:
            self.state.gamma_regime = fa.gamma_regime
            self.state.net_gex = fa.net_gex
            self.state.net_dex = fa.net_dex
            self.state.regime_narrative = fa.regime_narrative
            self.freshness.fa_summary_ts = fa.summary_ts

        # --- 0DTE analytics ---
        if fa.zero_dte_ts > self.freshness.fa_zero_dte_ts:
            self.state.pin_score = fa.pin_score
            self.state.expected_move_up = fa.expected_move_up
            self.state.expected_move_down = fa.expected_move_down
            self.state.gamma_acceleration = fa.gamma_acceleration
            self.state.charm_regime = fa.charm_regime
            self.freshness.fa_zero_dte_ts = fa.zero_dte_ts

        # --- VEX/CHEX ---
        if fa.vex_ts > self.freshness.fa_vex_chex_ts:
            self.state.net_vex = fa.net_vex
            self.state.vex_interpretation = fa.vex_interpretation
            self.state.net_chex = fa.net_chex
            self.state.chex_interpretation = fa.chex_interpretation
            self.freshness.fa_vex_chex_ts = fa.vex_ts

        # --- Volatility with conflict resolution ---
        if fa.vol_ts > self.freshness.fa_vol_ts:
            self.state.massive_atm_iv = self._compute_massive_atm_iv()
            self.state.atm_iv = resolve_iv_conflict(
                fa.atm_iv, self.state.massive_atm_iv, self.state
            )
            self.state.iv_rank = fa.iv_rank
            self.state.vrp = fa.vrp
            self.freshness.fa_vol_ts = fa.vol_ts

        # --- Per-strike chain from Massive ---
        if massive.chain_cache:
            self._update_chain(massive.chain_cache)
            self.freshness.massive_chain_ts = now

        # --- Fallback: derive walls from chain if FA is stale ---
        fa_q = self.freshness.fa_quality()
        if fa_q in (DataQuality.STALE, DataQuality.OFFLINE) and self.state.chain:
            if self.state.call_wall == 0:
                self.state.call_wall = derive_call_wall_from_chain(self.state.chain)
            if self.state.put_wall == 0:
                self.state.put_wall = derive_put_wall_from_chain(self.state.chain)

        # --- Fallback: derive regime from spot vs flip ---
        if fa_q in (DataQuality.STALE, DataQuality.OFFLINE):
            if self.state.gamma_flip > 0 and self.state.spot_qqq > 0:
                self.state.gamma_regime = (
                    1 if self.state.spot_qqq > self.state.gamma_flip else -1
                )

        # --- Update quality indicators ---
        self.state.fa_quality = self.freshness.fa_quality().value
        self.state.massive_quality = self.freshness.massive_quality().value
        self.state.last_fusion_ts = now

    def _compute_massive_atm_iv(self) -> float:
        """Compute ATM IV from Massive chain data."""
        if not self.state.chain or self.state.spot_qqq == 0:
            return 0.0

        spot = self.state.spot_qqq
        # Find closest strike to spot
        closest = min(self.state.chain.keys(), key=lambda s: abs(s - spot))
        strike_data = self.state.chain[closest]

        # Average call and put IV at ATM
        ivs = [v for v in [strike_data.call_iv, strike_data.put_iv] if v > 0]
        return sum(ivs) / len(ivs) if ivs else 0.0

    def _update_chain(self, massive_chain: dict):
        """Merge Massive chain data into OptionsState.chain."""
        for strike, data in massive_chain.items():
            if strike not in self.state.chain:
                self.state.chain[strike] = StrikeData(strike=strike)

            sd = self.state.chain[strike]
            sd.call_gamma = data.get("call_gamma", sd.call_gamma)
            sd.put_gamma = data.get("put_gamma", sd.put_gamma)
            sd.call_oi = data.get("call_oi", sd.call_oi)
            sd.put_oi = data.get("put_oi", sd.put_oi)
            sd.massive_ts = time.time()

            # Compute GEX contribution
            spot = self.state.spot_qqq or 1.0
            sd.gex_contribution = (
                (sd.call_gamma * sd.call_oi - sd.put_gamma * sd.put_oi)
                * 100  # shares per contract
                * spot
            )
```

---

## 6. Fallback Behavior

### Massive offline, FlashAlpha healthy

Signal engine gets regime, walls, and dealer flow direction from FlashAlpha.
Missing: per-strike Greeks, real-time spot price.

Action: Use last known spot price. Disable signals that require per-strike gamma
(e.g., GEX heatmap). Keep regime-based signals active.

```python
def get_spot_with_fallback(state: OptionsState, last_known: float) -> float:
    if state.spot_qqq > 0 and state.massive_quality != "offline":
        return state.spot_qqq
    # Fall back to last known — acceptable for up to 30s
    return last_known
```

### FlashAlpha offline, Massive healthy

Signal engine gets per-strike data but loses regime classification and dealer flow.

Action: Derive regime mechanically from spot vs gamma_flip (last known). Disable
vanna/charm signals. Keep absorption and exhaustion signals active (they don't need FA).

```python
def get_regime_degraded(state: OptionsState) -> int:
    """Mechanical regime from spot vs last known gamma_flip."""
    if state.gamma_flip == 0 or state.spot_qqq == 0:
        return 0
    return 1 if state.spot_qqq > state.gamma_flip else -1
```

### Both offline

Halt signal generation. Log the outage. Do not trade.

```python
def can_generate_signals(state: OptionsState) -> bool:
    if state.fa_quality == "offline" and state.massive_quality == "offline":
        logger.error("Both data sources offline — halting signal generation")
        return False
    if state.spot_qqq == 0:
        logger.error("No spot price — halting signal generation")
        return False
    return True
```

---

## 7. Validation Before Signal Engine Consumption

Run these checks before passing `OptionsState` to the signal engine on each bar.

```python
from dataclasses import dataclass
from typing import list

@dataclass
class ValidationResult:
    passed: bool
    warnings: list[str]
    errors: list[str]

def validate_options_state(state: OptionsState) -> ValidationResult:
    warnings = []
    errors = []

    # Hard failures — signal engine cannot run
    if state.spot_qqq <= 0:
        errors.append("spot_qqq is zero or negative")

    if state.gamma_flip <= 0:
        errors.append("gamma_flip is zero — FA levels not loaded")

    if state.age_s() > 120:
        errors.append(f"OptionsState is {state.age_s():.0f}s old — fusion loop may be stuck")

    # Soft warnings — signal engine can run with reduced confidence
    if state.fa_quality in ("stale", "offline"):
        warnings.append(f"FlashAlpha quality: {state.fa_quality}")

    if state.massive_quality in ("stale", "offline"):
        warnings.append(f"Massive quality: {state.massive_quality}")

    if state.pin_score == 0 and state.fa_quality == "fresh":
        warnings.append("pin_score is 0 with fresh FA data — zero_dte endpoint may have failed")

    if state.atm_iv > 0 and state.massive_atm_iv > 0:
        iv_diff = abs(state.atm_iv - state.massive_atm_iv)
        if iv_diff > 0.05:
            warnings.append(
                f"Large IV conflict: FA={state.atm_iv:.3f} Massive={state.massive_atm_iv:.3f}"
            )

    if state.call_wall > 0 and state.put_wall > 0:
        if state.call_wall < state.put_wall:
            errors.append(
                f"call_wall ({state.call_wall}) < put_wall ({state.put_wall}) — data inversion"
            )

    # Sanity check: spot should be between walls
    if state.call_wall > 0 and state.put_wall > 0 and state.spot_qqq > 0:
        if not (state.put_wall * 0.95 < state.spot_qqq < state.call_wall * 1.05):
            warnings.append(
                f"Spot {state.spot_qqq} outside expected wall range "
                f"[{state.put_wall}, {state.call_wall}]"
            )

    return ValidationResult(
        passed=len(errors) == 0,
        warnings=warnings,
        errors=errors,
    )
```

---

## 8. Startup and Shutdown

```python
async def run_fusion_system(symbol: str = "QQQ"):
    """
    Full startup sequence for the data fusion system.
    Returns the running OptionsState for the signal engine to read.
    """
    from .flashalpha_bridge import FlashAlphaPoller, warm_up_flashalpha
    from .massive_api import MassivePoller

    fa_poller = FlashAlphaPoller(symbol=symbol)
    massive_poller = MassivePoller()

    # Warm up FlashAlpha synchronously before starting loops
    await warm_up_flashalpha(fa_poller)

    fusion = OptionsFusionLoop(fa_poller, massive_poller)

    # Start all loops concurrently
    tasks = [
        asyncio.create_task(fa_poller.start()),
        asyncio.create_task(massive_poller.run()),
        asyncio.create_task(fusion.start()),
    ]

    # Validate initial state
    result = validate_options_state(fusion.state)
    if not result.passed:
        for err in result.errors:
            logger.error(f"Startup validation error: {err}")
        raise RuntimeError("OptionsState failed startup validation")

    for warn in result.warnings:
        logger.warning(f"Startup validation warning: {warn}")

    return fusion.state, tasks
```
