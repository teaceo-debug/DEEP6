# VolSurfaceAlgo — Volatility Surface Mechanics Trader

## Identity

**Class**: `VolSurfaceAlgo`
**Role**: Exploits three distinct volatility surface mechanics for directional NQ bias: vanna-driven dealer hedging flows (VannaRally), charm-driven time-decay hedging (CharmDrift), and volatility risk premium mean-reversion (VRPHarvest). These are slower, structural trades compared to wall reactions. They operate on timescales of hours, not minutes.

**Theory reference**: `options-bias-engine/domains/dex-vex-chex.md` for the full Greek hedging cascade. `options-bias-engine/domains/volatility-structure.md` for VRP mechanics and term structure. `options-bias-engine/step5-setups/vanna-rally.md` and `options-bias-engine/step5-setups/charm-flow.md` for setup specifications.

**Core principle**: Dealers don't just hedge gamma. They hedge vanna (sensitivity of delta to volatility) and charm (sensitivity of delta to time). When IV moves or time passes, dealers must rebalance their hedges. That rebalancing creates predictable, mechanical buying or selling pressure in the underlying. VolSurfaceAlgo trades that pressure.

---

## Inputs

| Input | Source | Update frequency |
|-------|--------|-----------------|
| `net_vex` | FlashAlpha `vex` endpoint | Every 30-60 sec |
| `vex_interpretation` | FlashAlpha `vex.vex_interpretation` | Every 30-60 sec |
| `net_chex` | FlashAlpha `chex` endpoint | Every 30-60 sec |
| `chex_interpretation` | FlashAlpha `chex.chex_interpretation` | Every 30-60 sec |
| `iv_rank` | FlashAlpha volatility endpoint | Every 30-60 sec |
| `iv_percentile` | FlashAlpha volatility endpoint | Every 30-60 sec |
| `vix_current` | Market data (VIX quote) | Continuous |
| `vix_1h_change` | Derived from VIX history | Per minute |
| `realized_vol_20d` | Derived from NQ price history | Per session |
| `nq_price` | Rithmic MBO midpoint | Continuous |
| `regime` | RegimeAlgo | On change |
| `call_wall_nq` | RegimeAlgo (from FlashAlpha) | Every 30-60 sec |
| `expected_move_nq` | Derived from IV | Per session |
| `session_time` | System clock | Continuous |

---

## Three Sub-Strategies

### Sub-strategy 1: VannaRally

**What it is**: When IV declines, dealers who are short vanna must buy the underlying to rebalance. This creates mechanical upward pressure on NQ. The reverse (IV rising) creates selling pressure.

**Direction logic**:
- IV declining + positive VEX → dealers buying → **Long NQ**
- IV rising + negative VEX → dealers selling → **Short NQ** (or reduce long exposure)

**Timescale**: Hours. Vanna flows are gradual, not tick-level. This is not a scalp.

### Sub-strategy 2: CharmDrift

**What it is**: As time passes, the delta of options changes (charm). Dealers must rebalance. In the last 2-4 hours of a trading day, charm accelerates. The direction of that rebalancing creates a predictable drift in NQ.

**Direction logic**:
- Positive CHEX (time_decay_dealers_buy) → dealers buying into close → **Long NQ**
- Negative CHEX (time_decay_dealers_sell) → dealers selling into close → **Short NQ**

**Timescale**: 1-3 hours. Best on 0DTE days and OPEX week when charm is largest.

### Sub-strategy 3: VRPHarvest

**What it is**: The volatility risk premium (VRP) is the spread between implied volatility (IV) and realized volatility (RV). When VRP is extremely elevated, IV is overpriced relative to actual movement. This typically precedes a vol crush, which is mechanically bullish for NQ (dealers unwind hedges as IV falls).

**Direction logic**:
- VRP > 2σ above mean → IV overpriced → expect vol crush → **Long NQ** (or hold longs)
- VRP < -1σ below mean → RV exceeding IV → vol expansion likely → **Reduce exposure or short**

**Timescale**: Days. VRP normalizes slowly. This is a multi-session position or a bias filter, not a day trade.

---

## VannaRally — Full Specification

### Entry conditions (ALL must be true)

1. **VEX positive**: `net_vex > 0` (dealers are net short vanna, must buy when IV falls)
2. **IV declining**: `iv_rank` has dropped at least 3 percentile points in the last 30 minutes, OR `vix_1h_change < -0.5`
3. **Regime compatible**: Regime A or D (not E — don't fight a trending bear with a vanna long)
4. **No event within 60 minutes**: vanna flows are disrupted by macro events
5. **Not at call wall**: if price is within 15 NQ points of call wall, wait for wall reaction to resolve first

### Entry direction

Always long NQ when conditions are met. VannaRally is a bullish setup by definition (IV declining + positive VEX = dealer buying).

### Entry execution

- Use limit order 2-3 NQ points below current price (vanna flows are gradual, no need to chase)
- If IV is declining rapidly (VIX down 1+ point in 30 min), use market order to capture the move

### Targets

| Target | NQ points | Notes |
|--------|-----------|-------|
| T1 | 15 NQ points | Take 40% here |
| T2 | Call wall or expected move boundary (whichever closer) | Take 40% here |
| T3 | Trail remaining 20% with 15-point trailing stop | Capture extended vanna squeeze |

### Stop loss

- **Hard stop**: 12 NQ points below entry
- **Soft stop**: if `net_vex` flips negative (VEX reversal), exit at market regardless of P&L
- **Regime stop**: if regime transitions to E, exit immediately

### Duration

- Typical hold: 1-4 hours
- Exit by 3:50 PM ET regardless
- If IV stabilizes (VIX flat for 30+ minutes) and T1 not hit, exit at market

### Estimated performance

| Condition | Estimated win rate | Avg R:R |
|-----------|-------------------|---------|
| Strong VEX + IV declining | 65-70% | 1.5:1 to 2:1 |
| Weak VEX + mild IV decline | 50-60% | 1:1 to 1.5:1 |

Source: `options-bias-engine/step5-setups/vanna-rally.md` estimated ranges.

---

## CharmDrift — Full Specification

### Entry conditions (ALL must be true)

1. **CHEX directional**: `chex_interpretation` is `time_decay_dealers_buy` or `time_decay_dealers_sell`
2. **Time window**: 2:00 PM to 3:45 PM ET (charm accelerates in final hours)
3. **0DTE or OPEX context** (preferred, not required): charm is largest on 0DTE days and OPEX week
4. **Regime compatible**: Any regime except G (pre-event)
5. **Minimum CHEX magnitude**: `abs(net_chex)` must be in the top 30th percentile of recent readings (charm must be meaningful, not noise)

### Entry direction

| CHEX interpretation | NQ direction |
|--------------------|-------------|
| `time_decay_dealers_buy` | Long NQ |
| `time_decay_dealers_sell` | Short NQ |

### Entry execution

- Use limit order at current price or 1-2 NQ points in the direction of entry
- CharmDrift is a slow drift, not a spike. Don't pay up.

### Targets

| Target | NQ points | Notes |
|--------|-----------|-------|
| T1 | 10 NQ points | Take 50% here |
| T2 | 20 NQ points | Take remaining 50% here |

CharmDrift targets are smaller than VannaRally. Charm creates drift, not explosions.

### Stop loss

- **Hard stop**: 8 NQ points against entry
- **Time stop**: exit all by 3:50 PM ET (charm stops at close)
- **Soft stop**: if `chex_interpretation` flips direction, exit at market

### Best conditions

- Friday afternoon (weekly OPEX): charm is largest
- OPEX week (monthly): charm is elevated all week
- 0DTE days (Mon, Wed, Fri for QQQ): intraday charm is most concentrated
- Avoid: days with major macro events in the afternoon (charm gets overwhelmed by event vol)

### Estimated performance

| Condition | Estimated win rate | Avg R:R |
|-----------|-------------------|---------|
| 0DTE day, strong CHEX | 60-65% | 1.2:1 to 1.5:1 |
| Non-0DTE, moderate CHEX | 50-55% | 1:1 to 1.2:1 |

Source: `options-bias-engine/step5-setups/charm-flow.md` estimated ranges.

---

## VRPHarvest — Full Specification

### VRP computation

```python
vrp = iv_current - realized_vol_20d  # both in annualized % terms

# Historical mean and std of VRP (compute from rolling 60-day window)
vrp_mean = rolling_mean(vrp, 60)
vrp_std = rolling_std(vrp, 60)
vrp_zscore = (vrp - vrp_mean) / vrp_std
```

### Entry conditions

**Bullish (vol crush expected)**:
1. `vrp_zscore > 2.0` (IV is more than 2 standard deviations above its typical premium over RV)
2. VIX is elevated but not spiking (VIX between 20-35, not actively rising)
3. Regime A or D (not E)
4. No macro event within 24 hours

**Bearish/reduce exposure (vol expansion expected)**:
1. `vrp_zscore < -1.0` (RV is exceeding IV — unusual, suggests vol is underpriced)
2. VIX is low and declining (VIX < 15)
3. Any regime

### Entry direction

| VRP condition | Action |
|--------------|--------|
| `vrp_zscore > 2.0` | Long NQ (or add to existing longs) |
| `vrp_zscore < -1.0` | Reduce NQ exposure (or short if other signals confirm) |

### Entry execution

- VRPHarvest is a multi-session position. Enter at session open when conditions are met.
- Use limit order 5-10 NQ points below current price for long entries (vol crush is not immediate)

### Targets

| Target | NQ points | Notes |
|--------|-----------|-------|
| T1 | 30 NQ points | Take 30% here |
| T2 | 60 NQ points | Take 40% here |
| T3 | Trail remaining 30% with 25-point trailing stop | VRP normalization can take days |

### Stop loss

- **Hard stop**: 20 NQ points below entry (wider stop for multi-session position)
- **VRP stop**: if `vrp_zscore` drops below 1.0 (VRP normalizing), take partial profits and tighten stop
- **Regime stop**: if regime transitions to E, exit immediately

### Duration

- Typical hold: 1-3 sessions
- Review at each session open: if VRP has normalized, close the position

### Estimated performance

| Condition | Estimated win rate | Avg R:R |
|-----------|-------------------|---------|
| VRP > 2σ, no event risk | 60-65% | 2:1 to 3:1 |
| VRP > 1.5σ, moderate conditions | 50-55% | 1.5:1 to 2:1 |

---

## Sub-Strategy Selection and Stacking

Multiple sub-strategies can be active simultaneously if their conditions are independently met. They can stack.

### Stacking rules

| Combination | Action |
|-------------|--------|
| VannaRally + CharmDrift (same direction) | Allow both, combined position = 1.5x normal size |
| VannaRally + CharmDrift (opposite direction) | Take the stronger signal only |
| VRPHarvest + VannaRally (same direction) | Allow both, combined = 1.5x normal size |
| VRPHarvest + CharmDrift (same direction) | Allow both, combined = 1.5x normal size |
| All three (same direction) | Maximum conviction, 2x normal size |
| Any combination (opposite directions) | No trade — signals are contradicting |

### Selection priority when signals conflict

1. VannaRally (fastest-moving, most actionable)
2. CharmDrift (time-constrained, must act in window)
3. VRPHarvest (slowest, can wait for next session)

---

## Position Sizing

VolSurfaceAlgo uses smaller base sizes than WallReactionAlgo because these strategies have wider stops and longer durations.

```python
base_contracts = 1

sub_strategy_multiplier = {
    "vanna_rally": 1.0,
    "charm_drift": 0.75,    # smaller, shorter duration
    "vrp_harvest": 0.75,    # smaller, multi-session
}

conviction_multiplier = conviction  # 0.5 to 1.0 from RegimeAlgo

final_contracts = round(
    base_contracts
    * sub_strategy_multiplier[active_sub]
    * conviction_multiplier
)
```

---

## Kill Switches

| Condition | Action |
|-----------|--------|
| VEX flips sign (VannaRally) | Exit VannaRally position immediately |
| CHEX flips direction (CharmDrift) | Exit CharmDrift position immediately |
| VRP normalizes below 1σ (VRPHarvest) | Tighten stop to breakeven |
| Regime transitions to G | Exit all positions |
| Regime transitions to E | Exit all long positions |
| VIX spikes > 2 points in 30 min | Exit all positions (vol expansion overrides vanna/charm) |
| Daily loss limit hit | Deactivate all sub-strategies |
| 3:50 PM ET | Exit all intraday positions (VannaRally, CharmDrift) |

---

## Python Class Skeleton

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import asyncio
from datetime import datetime, time


class VolSubStrategy(Enum):
    VANNA_RALLY = "vanna_rally"
    CHARM_DRIFT = "charm_drift"
    VRP_HARVEST = "vrp_harvest"
    INACTIVE = "inactive"


@dataclass
class VolSignal:
    sub_strategy: VolSubStrategy
    direction: str              # "long" or "short"
    entry_price: float
    target_1: float
    target_2: float
    target_3: Optional[float]
    stop_loss: float
    conviction: float
    rationale: dict             # {"vex": float, "chex": str, "vrp_zscore": float}
    timestamp: datetime


@dataclass
class VolPosition:
    signal: VolSignal
    contracts: int
    entry_fill: float
    t1_hit: bool = False
    t2_hit: bool = False
    trailing_stop: Optional[float] = None
    open_time: Optional[datetime] = None


class VolSurfaceAlgo:
    """
    Trades volatility surface mechanics: vanna flows, charm drift, and VRP mean-reversion.
    Operates on longer timescales than WallReactionAlgo (hours to days).
    """

    # VannaRally thresholds
    VANNA_IV_RANK_DROP_THRESHOLD = 3.0      # percentile points in 30 min
    VANNA_VIX_CHANGE_THRESHOLD = -0.5       # VIX drop in 1 hour
    VANNA_STOP_POINTS = 12.0
    VANNA_TARGET_1_POINTS = 15.0

    # CharmDrift thresholds
    CHARM_START_TIME = time(14, 0)
    CHARM_END_TIME = time(15, 45)
    CHARM_STOP_POINTS = 8.0
    CHARM_TARGET_1_POINTS = 10.0
    CHARM_TARGET_2_POINTS = 20.0

    # VRPHarvest thresholds
    VRP_BULLISH_ZSCORE = 2.0
    VRP_BEARISH_ZSCORE = -1.0
    VRP_STOP_POINTS = 20.0
    VRP_TARGET_1_POINTS = 30.0
    VRP_TARGET_2_POINTS = 60.0

    SESSION_CLOSE_TIME = time(15, 50)

    def __init__(self, execution_engine, signal_engine, vol_data, logger):
        self.execution = execution_engine
        self.signals = signal_engine
        self.vol_data = vol_data
        self.logger = logger
        self.active_regime = None
        self.conviction = 0.0
        self.positions: dict[VolSubStrategy, VolPosition] = {}
        self._active = False

    async def activate(self, regime, conviction: float, options) -> None:
        self.active_regime = regime
        self.conviction = conviction
        self._active = True
        self.logger.info(f"VolSurfaceAlgo activated: regime={regime}, conviction={conviction}")

    async def deactivate(self, reason: str) -> None:
        self._active = False
        self.active_regime = None
        self.logger.info(f"VolSurfaceAlgo deactivated: {reason}")

    async def close_all(self, reason: str, grace_seconds: int = 0) -> None:
        if grace_seconds > 0:
            await asyncio.sleep(grace_seconds)
        for sub, pos in list(self.positions.items()):
            await self.execution.close_position(pos, reason)
        self.positions.clear()

    async def evaluate(self, options, vol_state: dict) -> list[VolSignal]:
        """
        Evaluate all three sub-strategies. Returns list of signals (may be empty or multiple).
        Called on each options/vol update.
        """
        if not self._active:
            return []

        signals = []

        vanna_signal = await self._evaluate_vanna_rally(options, vol_state)
        if vanna_signal:
            signals.append(vanna_signal)

        charm_signal = await self._evaluate_charm_drift(options, vol_state)
        if charm_signal:
            signals.append(charm_signal)

        vrp_signal = await self._evaluate_vrp_harvest(options, vol_state)
        if vrp_signal:
            signals.append(vrp_signal)

        return self._resolve_conflicts(signals)

    async def _evaluate_vanna_rally(self, options, vol_state: dict) -> Optional[VolSignal]:
        """Check VannaRally entry conditions."""
        net_vex = vol_state.get("net_vex", 0)
        iv_rank_change = vol_state.get("iv_rank_30m_change", 0)
        vix_1h_change = vol_state.get("vix_1h_change", 0)
        nq_price = options.nq_price

        if net_vex <= 0:
            return None

        iv_declining = (
            iv_rank_change <= -self.VANNA_IV_RANK_DROP_THRESHOLD
            or vix_1h_change <= self.VANNA_VIX_CHANGE_THRESHOLD
        )
        if not iv_declining:
            return None

        from .regime_algo import Regime
        if self.active_regime not in (Regime.A, Regime.D):
            return None

        call_wall = options.call_wall_nq
        if abs(nq_price - call_wall) < 15.0:
            return None  # at call wall, let wall reaction handle it

        target_1 = nq_price + self.VANNA_TARGET_1_POINTS
        target_2 = min(call_wall, nq_price + options.expected_move_nq * 0.5)
        stop = nq_price - self.VANNA_STOP_POINTS

        return VolSignal(
            sub_strategy=VolSubStrategy.VANNA_RALLY,
            direction="long",
            entry_price=nq_price,
            target_1=target_1,
            target_2=target_2,
            target_3=None,
            stop_loss=stop,
            conviction=self.conviction,
            rationale={"net_vex": net_vex, "iv_rank_change": iv_rank_change, "vix_1h_change": vix_1h_change},
            timestamp=datetime.now(),
        )

    async def _evaluate_charm_drift(self, options, vol_state: dict) -> Optional[VolSignal]:
        """Check CharmDrift entry conditions."""
        now_time = datetime.now().time()
        if not (self.CHARM_START_TIME <= now_time <= self.CHARM_END_TIME):
            return None

        chex_interp = vol_state.get("chex_interpretation", "")
        net_chex = vol_state.get("net_chex", 0)
        chex_percentile = vol_state.get("chex_percentile", 50)

        if chex_interp not in ("time_decay_dealers_buy", "time_decay_dealers_sell"):
            return None

        if chex_percentile < 70:  # must be in top 30th percentile
            return None

        from .regime_algo import Regime
        if self.active_regime == Regime.G:
            return None

        nq_price = options.nq_price
        direction = "long" if chex_interp == "time_decay_dealers_buy" else "short"

        if direction == "long":
            target_1 = nq_price + self.CHARM_TARGET_1_POINTS
            target_2 = nq_price + self.CHARM_TARGET_2_POINTS
            stop = nq_price - self.CHARM_STOP_POINTS
        else:
            target_1 = nq_price - self.CHARM_TARGET_1_POINTS
            target_2 = nq_price - self.CHARM_TARGET_2_POINTS
            stop = nq_price + self.CHARM_STOP_POINTS

        return VolSignal(
            sub_strategy=VolSubStrategy.CHARM_DRIFT,
            direction=direction,
            entry_price=nq_price,
            target_1=target_1,
            target_2=target_2,
            target_3=None,
            stop_loss=stop,
            conviction=self.conviction * 0.75,
            rationale={"chex_interpretation": chex_interp, "net_chex": net_chex, "chex_percentile": chex_percentile},
            timestamp=datetime.now(),
        )

    async def _evaluate_vrp_harvest(self, options, vol_state: dict) -> Optional[VolSignal]:
        """Check VRPHarvest entry conditions."""
        vrp_zscore = vol_state.get("vrp_zscore", 0)
        vix = vol_state.get("vix_current", 20)
        nq_price = options.nq_price

        from .regime_algo import Regime

        if vrp_zscore > self.VRP_BULLISH_ZSCORE:
            if self.active_regime == Regime.E:
                return None
            if not (20 <= vix <= 35):
                return None

            target_1 = nq_price + self.VRP_TARGET_1_POINTS
            target_2 = nq_price + self.VRP_TARGET_2_POINTS
            stop = nq_price - self.VRP_STOP_POINTS

            return VolSignal(
                sub_strategy=VolSubStrategy.VRP_HARVEST,
                direction="long",
                entry_price=nq_price,
                target_1=target_1,
                target_2=target_2,
                target_3=nq_price + 90.0,
                stop_loss=stop,
                conviction=self.conviction * 0.75,
                rationale={"vrp_zscore": vrp_zscore, "vix": vix},
                timestamp=datetime.now(),
            )

        elif vrp_zscore < self.VRP_BEARISH_ZSCORE:
            if vix >= 15:
                return None

            target_1 = nq_price - self.VRP_TARGET_1_POINTS
            target_2 = nq_price - self.VRP_TARGET_2_POINTS
            stop = nq_price + self.VRP_STOP_POINTS

            return VolSignal(
                sub_strategy=VolSubStrategy.VRP_HARVEST,
                direction="short",
                entry_price=nq_price,
                target_1=target_1,
                target_2=target_2,
                target_3=nq_price - 90.0,
                stop_loss=stop,
                conviction=self.conviction * 0.75,
                rationale={"vrp_zscore": vrp_zscore, "vix": vix},
                timestamp=datetime.now(),
            )

        return None

    def _resolve_conflicts(self, signals: list[VolSignal]) -> list[VolSignal]:
        """Remove conflicting signals. Keep same-direction signals, drop opposite."""
        if len(signals) <= 1:
            return signals

        directions = {s.direction for s in signals}
        if len(directions) > 1:
            # Conflicting directions: keep highest conviction only
            return [max(signals, key=lambda s: s.conviction)]

        return signals

    async def on_price_update(self, nq_price: float, vol_state: dict) -> None:
        """Monitor open positions for stop/target hits."""
        now_time = datetime.now().time()

        for sub, pos in list(self.positions.items()):
            sig = pos.signal

            # Session close time stop (intraday strategies only)
            if sub in (VolSubStrategy.VANNA_RALLY, VolSubStrategy.CHARM_DRIFT):
                if now_time >= self.SESSION_CLOSE_TIME:
                    await self.execution.close_position(pos, "session_close")
                    del self.positions[sub]
                    continue

            # Hard stop
            if sig.direction == "long" and nq_price <= sig.stop_loss:
                await self.execution.close_position(pos, "stop_loss")
                del self.positions[sub]
                continue
            if sig.direction == "short" and nq_price >= sig.stop_loss:
                await self.execution.close_position(pos, "stop_loss")
                del self.positions[sub]
                continue

            # VannaRally soft stop: VEX flipped
            if sub == VolSubStrategy.VANNA_RALLY:
                if vol_state.get("net_vex", 1) <= 0:
                    await self.execution.close_position(pos, "vex_flip")
                    del self.positions[sub]
                    continue

            # CharmDrift soft stop: CHEX flipped
            if sub == VolSubStrategy.CHARM_DRIFT:
                chex_interp = vol_state.get("chex_interpretation", "")
                expected = "time_decay_dealers_buy" if sig.direction == "long" else "time_decay_dealers_sell"
                if chex_interp != expected and chex_interp != "":
                    await self.execution.close_position(pos, "chex_flip")
                    del self.positions[sub]
                    continue

            # Target management
            if not pos.t1_hit:
                if sig.direction == "long" and nq_price >= sig.target_1:
                    await self.execution.partial_close(pos, 0.4, "target_1")
                    pos.t1_hit = True
                elif sig.direction == "short" and nq_price <= sig.target_1:
                    await self.execution.partial_close(pos, 0.4, "target_1")
                    pos.t1_hit = True

            if pos.t1_hit and not pos.t2_hit:
                if sig.direction == "long" and nq_price >= sig.target_2:
                    await self.execution.partial_close(pos, 0.7, "target_2")
                    pos.t2_hit = True
                elif sig.direction == "short" and nq_price <= sig.target_2:
                    await self.execution.partial_close(pos, 0.7, "target_2")
                    pos.t2_hit = True

            # VRPHarvest trailing stop after T2
            if sub == VolSubStrategy.VRP_HARVEST and pos.t2_hit:
                if sig.direction == "long":
                    new_trail = nq_price - 25.0
                    if pos.trailing_stop is None or new_trail > pos.trailing_stop:
                        pos.trailing_stop = new_trail
                    if nq_price <= pos.trailing_stop:
                        await self.execution.close_position(pos, "trailing_stop")
                        del self.positions[sub]
                else:
                    new_trail = nq_price + 25.0
                    if pos.trailing_stop is None or new_trail < pos.trailing_stop:
                        pos.trailing_stop = new_trail
                    if nq_price >= pos.trailing_stop:
                        await self.execution.close_position(pos, "trailing_stop")
                        del self.positions[sub]
```

---

## Configuration

```python
VOL_SURFACE_CONFIG = {
    # VannaRally
    "vanna_iv_rank_drop_threshold": 3.0,
    "vanna_vix_change_threshold": -0.5,
    "vanna_stop_points": 12.0,
    "vanna_target_1_points": 15.0,

    # CharmDrift
    "charm_start_time": "14:00",
    "charm_end_time": "15:45",
    "charm_stop_points": 8.0,
    "charm_target_1_points": 10.0,
    "charm_target_2_points": 20.0,
    "charm_percentile_threshold": 70,

    # VRPHarvest
    "vrp_bullish_zscore": 2.0,
    "vrp_bearish_zscore": -1.0,
    "vrp_stop_points": 20.0,
    "vrp_target_1_points": 30.0,
    "vrp_target_2_points": 60.0,
    "vrp_trailing_stop_points": 25.0,
    "vrp_vix_range_low": 20,
    "vrp_vix_range_high": 35,

    # Stacking
    "max_stacked_size_multiplier": 2.0,
    "session_close_time": "15:50",
}
```

---

## Notes on Vol Data Requirements

VolSurfaceAlgo requires data that isn't always available from a single source:

- **VRP computation** requires both IV (from FlashAlpha or options chain) and realized vol (computed from NQ price history). The 20-day realized vol window should be pre-computed at session start.
- **CHEX percentile** requires a rolling history of CHEX readings to compute the percentile rank. Maintain a 30-day rolling buffer.
- **VIX 1-hour change** requires a VIX quote feed. Use the CBOE VIX index or a VIX futures quote.

If any required data is unavailable, the corresponding sub-strategy should return `None` rather than error. Partial operation (e.g., only CharmDrift active because VRP data is missing) is acceptable.
