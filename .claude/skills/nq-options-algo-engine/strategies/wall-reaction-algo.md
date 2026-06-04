# WallReactionAlgo — Wall Bounce and Wall Break Detector

## Identity

**Class**: `WallReactionAlgo`
**Role**: Detects price approaching GEX call/put walls and trades the reaction. Operates in two mutually exclusive modes: BOUNCE (mean-reversion at wall) and BREAK (momentum through wall). The active mode is determined by the current regime from `RegimeAlgo`.

**Theory reference**: `options-bias-engine/step5-setups/wall-bounce.md` and `options-bias-engine/step5-setups/wall-break.md` for full setup specifications. `options-bias-engine/step2-levels/wall-dynamics.md` for how walls form and dissolve.

**Core principle**: GEX walls are mechanical. Dealers must hedge their gamma exposure by buying when price falls toward a put wall and selling when price rises toward a call wall. This creates a predictable, repeatable force at those levels. The wall bounce trades WITH that force. The wall break trades the moment that force is overwhelmed.

---

## Inputs

| Input | Source | Update frequency |
|-------|--------|-----------------|
| `call_wall_nq` | RegimeAlgo (from FlashAlpha, NQ-converted) | Every 30-60 sec |
| `put_wall_nq` | RegimeAlgo (from FlashAlpha, NQ-converted) | Every 30-60 sec |
| `nq_price` | Rithmic MBO midpoint | Continuous |
| `nq_velocity` | Derived: price change per minute | Continuous |
| `absorption_score` | DEEP6 signal engine (signal #7) | Per bar |
| `exhaustion_score` | DEEP6 signal engine (signal #8) | Per bar |
| `delta_bias` | DEEP6 signal engine (cumulative delta) | Per bar |
| `flow_state` | Options flow engine (from Massive.com) | Every 10-15 sec |
| `regime` | RegimeAlgo | On change |
| `active_mode` | Set by RegimeAlgo on activation | On activation |

---

## Two Modes

### BOUNCE mode
Active in: Regimes A, B, C only.

The wall is expected to hold. Dealers are hedged to defend it. Trade the rejection.

### BREAK mode
Active in: Regimes D, E, and during confirmed transitions from A to D/E.

The wall has been overwhelmed or is absent. Trade the momentum through it.

**These modes are never simultaneously active.** RegimeAlgo sets the mode when it calls `activate(regime, conviction, options)`.

---

## Wall Proximity Engine

### Proximity zones

```
APPROACH ZONE:  within 30 NQ points of wall
IN ZONE:        within 15 NQ points of wall
AT WALL:        within 5 NQ points of wall
THROUGH WALL:   price has crossed wall by > 5 NQ points
```

### Approach velocity

```python
velocity = (nq_price_now - nq_price_60s_ago) / 60  # points per second

fast_approach = abs(velocity) > 0.083   # > 5 pts/min
slow_grind = abs(velocity) <= 0.083
```

Fast approach toward a wall in BOUNCE mode is a warning sign. Dealers may not be able to absorb it. Reduce conviction by 20% when `fast_approach` is True and mode is BOUNCE.

---

## BOUNCE Mode — Full Specification

### Entry conditions (ALL must be true)

1. **Regime**: A, B, or C (positive gamma)
2. **Price in zone**: `abs(nq_price - wall_nq) < 15`
3. **Direction**: approaching wall (not already through it)
4. **Absorption confirmed**: `absorption_score >= 60` at the wall level (from DEEP6 signal engine)
5. **Flow alignment**: `flow_state` is not AGGRESSIVE in the direction of the wall (i.e., not aggressive buying at call wall, not aggressive selling at put wall)
6. **Minimum 2 of 3 confirmations**:
   - Absorption/exhaustion at wall (score >= 60)
   - Flow alignment (flow_state matches expected bounce direction)
   - Delta confirmation (cumulative delta turning at wall)

### Entry direction

| Wall | Entry direction |
|------|----------------|
| Call wall | Short NQ |
| Put wall | Long NQ |

### Entry execution

- Use limit order at wall level or 1-2 ticks inside the wall
- If absorption is very strong (score >= 80), use market order to avoid missing the fill
- Do not chase: if price has already moved 8+ points away from wall before entry, skip

### Targets

| Regime | Target | Notes |
|--------|--------|-------|
| A (between walls) | 15-25 NQ points toward opposite wall or midpoint | Scale out: 50% at 15pts, 50% at 25pts |
| B (at call wall) | 15-20 NQ points toward midpoint | Single target |
| C (at put wall) | 20-30 NQ points toward midpoint or call wall | Scale out: 50% at 20pts, 50% at 30pts |

Regime C gets the widest target because it's the highest win-rate setup in the system. The put wall in positive gamma is the most mechanically defended level.

### Stop loss

- **Hard stop**: 10 NQ points beyond the wall (wall fail)
  - Call wall short: stop at `call_wall_nq + 10`
  - Put wall long: stop at `put_wall_nq - 10`
- **Soft stop**: if absorption score drops below 30 after entry, exit at market (wall is dissolving)

### Time stop

- Exit if trade has not reached 50% of target within 20 minutes
- Exit all positions by 3:50 PM ET regardless of P&L

### Estimated performance

| Regime | Estimated win rate | Avg R:R | Notes |
|--------|-------------------|---------|-------|
| C (put wall) | 70-80% | 1.5:1 to 2:1 | Best setup in system |
| A (between walls) | 60-70% | 1.5:1 | Depends on wall strength |
| B (call wall) | 60-70% | 1.5:1 | Slightly lower than C |

Source: `options-bias-engine/step5-setups/wall-bounce.md` estimated ranges.

---

## BREAK Mode — Full Specification

### Entry conditions (ALL must be true)

1. **Regime**: D or E (negative gamma), or confirmed transition from A
2. **Price through wall**: `nq_price > call_wall_nq + 5` (break up) or `nq_price < put_wall_nq - 5` (break down)
3. **Delta confirming**: cumulative delta accelerating in break direction
4. **Sweep cascade** (preferred): 2+ sweeps in break direction within last 10 minutes
5. **Volume surge**: current bar volume > 1.5x 20-bar average
6. **No immediate re-entry**: price has not immediately reversed back through wall

### Entry direction

| Break | Entry direction |
|-------|----------------|
| Through call wall upward | Long NQ |
| Through put wall downward | Short NQ |

### Entry execution

- Use stop-limit order placed 3 NQ points beyond the wall
- This ensures entry only after confirmed break, not on a wick
- If already through wall and conditions met, use market order

### Targets

| Target | NQ points | Notes |
|--------|-----------|-------|
| T1 | 30 NQ points | Take 40% here |
| T2 | 50 NQ points | Take 40% here |
| T3 | Next wall or expected move boundary | Trail remaining 20% |

Wall breaks in negative gamma can run 50-150 NQ points. The trailing stop on T3 captures extended moves.

### Stop loss

- **Hard stop**: 15 NQ points back inside the wall (failed break)
  - Call wall break long: stop at `call_wall_nq - 15`
  - Put wall break short: stop at `put_wall_nq + 15`
- **Trailing stop** (after T1 hit): trail 20 NQ points from highest/lowest price

### Time stop

- No time stop in BREAK mode during Regimes D/E (momentum can persist for hours)
- Exit all positions by 3:50 PM ET

### Estimated performance

| Condition | Estimated win rate | Avg R:R | Notes |
|-----------|-------------------|---------|-------|
| Regime D/E with sweep cascade | 50-60% | 2:1 to 3:1 | Lower WR, higher R:R |
| Transition break (A→D/E) | 55-65% | 2.5:1 | Transition adds conviction |

Source: `options-bias-engine/step5-setups/wall-break.md` estimated ranges.

---

## Mode Selection Logic

RegimeAlgo calls `activate(regime, conviction, options)`. WallReactionAlgo sets its mode based on regime:

```python
BOUNCE_REGIMES = {Regime.A, Regime.B, Regime.C}
BREAK_REGIMES = {Regime.D, Regime.E}

def _set_mode(self, regime: Regime) -> WallMode:
    if regime in BOUNCE_REGIMES:
        return WallMode.BOUNCE
    elif regime in BREAK_REGIMES:
        return WallMode.BREAK
    else:
        return WallMode.INACTIVE
```

When mode switches from BOUNCE to BREAK (regime transition), any open BOUNCE positions are closed before BREAK entries are considered.

---

## Confirmation Requirements

Both modes require a minimum of 2 of 3 confirmations before entry. This prevents trading on a single signal.

### Confirmation sources

| Confirmation | BOUNCE | BREAK |
|-------------|--------|-------|
| Absorption/exhaustion at wall (score >= 60) | Required | Confirming |
| Flow alignment (Massive.com flow_state) | Required | Required |
| Delta confirmation (cumulative delta turning) | Confirming | Required |

"Required" means it must be present. "Confirming" means it counts toward the 2-of-3 minimum but isn't mandatory alone.

---

## Kill Switches

| Condition | Action |
|-----------|--------|
| Wall dissolves (GEX update removes wall) | Close open positions, deactivate |
| Regime transition (RegimeAlgo calls deactivate) | Close all, reset state |
| Daily loss limit hit (from RegimeAlgo) | Deactivate, no new entries |
| Wall moves > 20 NQ points from entry level | Reassess: update stop to new wall location |
| Absorption score drops below 30 after BOUNCE entry | Exit at market (wall failing) |
| Price through wall by > 25 pts in BOUNCE mode | Exit at market (wall broken, stop should have triggered) |

---

## Python Class Skeleton

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import asyncio
from datetime import datetime


class WallMode(Enum):
    INACTIVE = "inactive"
    BOUNCE = "bounce"
    BREAK = "break"


@dataclass
class WallSignal:
    mode: WallMode
    direction: str          # "long" or "short"
    entry_price: float
    target_1: float
    target_2: float
    stop_loss: float
    wall_level: float
    conviction: float       # 0.0 to 1.0
    confirmations: list[str]
    timestamp: datetime


@dataclass
class WallPosition:
    signal: WallSignal
    contracts: int
    entry_fill: float
    t1_hit: bool = False
    t2_hit: bool = False
    trailing_stop: Optional[float] = None
    open_time: Optional[datetime] = None


class WallReactionAlgo:
    """
    Trades GEX wall reactions in two modes: BOUNCE (mean-reversion) and BREAK (momentum).
    Mode is set by RegimeAlgo based on current regime.
    """

    PROXIMITY_ZONE_POINTS = 15.0
    APPROACH_ZONE_POINTS = 30.0
    WALL_FAIL_POINTS = 10.0       # stop beyond wall in BOUNCE mode
    BREAK_FAIL_POINTS = 15.0      # stop back inside wall in BREAK mode
    BREAK_CONFIRM_POINTS = 5.0    # price must be this far through wall to confirm break
    FAST_APPROACH_PTS_PER_MIN = 5.0
    MIN_CONFIRMATIONS = 2
    TIME_STOP_MINUTES = 20        # BOUNCE mode only
    ABSORPTION_THRESHOLD = 60
    VOLUME_SURGE_MULTIPLIER = 1.5

    def __init__(self, execution_engine, signal_engine, flow_engine, logger):
        self.execution = execution_engine
        self.signals = signal_engine
        self.flow = flow_engine
        self.logger = logger
        self.mode = WallMode.INACTIVE
        self.active_regime = None
        self.conviction = 0.0
        self.position: Optional[WallPosition] = None
        self._price_history: list[tuple[datetime, float]] = []

    async def activate(self, regime, conviction: float, options) -> None:
        """Called by RegimeAlgo when this strategy should become active."""
        self.active_regime = regime
        self.conviction = conviction
        self.mode = self._set_mode(regime)
        self.logger.info(f"WallReactionAlgo activated: mode={self.mode}, regime={regime}")

    async def deactivate(self, reason: str) -> None:
        """Called by RegimeAlgo when this strategy should stop."""
        self.mode = WallMode.INACTIVE
        self.active_regime = None
        self.logger.info(f"WallReactionAlgo deactivated: {reason}")

    async def close_all(self, reason: str, grace_seconds: int = 0) -> None:
        """Close any open position."""
        if self.position:
            if grace_seconds > 0:
                await asyncio.sleep(grace_seconds)
            await self.execution.close_position(self.position, reason)
            self.position = None

    async def evaluate(self, options, nq_price: float) -> Optional[WallSignal]:
        """
        Main evaluation loop. Called on each price update or options update.
        Returns a WallSignal if entry conditions are met, None otherwise.
        """
        if self.mode == WallMode.INACTIVE:
            return None

        self._update_price_history(nq_price)

        if self.mode == WallMode.BOUNCE:
            return await self._evaluate_bounce(options, nq_price)
        elif self.mode == WallMode.BREAK:
            return await self._evaluate_break(options, nq_price)

        return None

    async def _evaluate_bounce(self, options, nq_price: float) -> Optional[WallSignal]:
        """Evaluate bounce conditions at call/put walls."""
        call_wall = options.call_wall_nq
        put_wall = options.put_wall_nq

        # Check call wall (short setup)
        if abs(nq_price - call_wall) < self.PROXIMITY_ZONE_POINTS:
            signal = await self._check_bounce_entry(
                nq_price, call_wall, "short", options
            )
            if signal:
                return signal

        # Check put wall (long setup)
        if abs(nq_price - put_wall) < self.PROXIMITY_ZONE_POINTS:
            signal = await self._check_bounce_entry(
                nq_price, put_wall, "long", options
            )
            if signal:
                return signal

        return None

    async def _check_bounce_entry(
        self, nq_price: float, wall: float, direction: str, options
    ) -> Optional[WallSignal]:
        """Check if bounce entry conditions are met at a specific wall."""
        confirmations = []

        # Absorption check
        absorption = await self.signals.get_absorption_score()
        if absorption >= self.ABSORPTION_THRESHOLD:
            confirmations.append("absorption")

        # Flow alignment check
        flow_state = await self.flow.get_current_state()
        if self._flow_aligns_with_bounce(flow_state, direction):
            confirmations.append("flow_alignment")

        # Delta confirmation
        delta = await self.signals.get_cumulative_delta()
        if self._delta_confirms_bounce(delta, direction):
            confirmations.append("delta_confirmation")

        if len(confirmations) < self.MIN_CONFIRMATIONS:
            return None

        # Velocity check: reduce conviction on fast approach
        velocity = self._compute_velocity()
        fast_approach = abs(velocity) > self.FAST_APPROACH_PTS_PER_MIN / 60
        effective_conviction = self.conviction * (0.8 if fast_approach else 1.0)

        # Build targets
        if direction == "short":
            target_1 = wall - 15.0
            target_2 = wall - 25.0
            stop = wall + self.WALL_FAIL_POINTS
        else:
            target_1 = wall + 20.0
            target_2 = wall + 30.0
            stop = wall - self.WALL_FAIL_POINTS

        return WallSignal(
            mode=WallMode.BOUNCE,
            direction=direction,
            entry_price=nq_price,
            target_1=target_1,
            target_2=target_2,
            stop_loss=stop,
            wall_level=wall,
            conviction=effective_conviction,
            confirmations=confirmations,
            timestamp=datetime.now(),
        )

    async def _evaluate_break(self, options, nq_price: float) -> Optional[WallSignal]:
        """Evaluate break conditions through call/put walls."""
        call_wall = options.call_wall_nq
        put_wall = options.put_wall_nq

        # Upward break through call wall
        if nq_price > call_wall + self.BREAK_CONFIRM_POINTS:
            signal = await self._check_break_entry(nq_price, call_wall, "long", options)
            if signal:
                return signal

        # Downward break through put wall
        if nq_price < put_wall - self.BREAK_CONFIRM_POINTS:
            signal = await self._check_break_entry(nq_price, put_wall, "short", options)
            if signal:
                return signal

        return None

    async def _check_break_entry(
        self, nq_price: float, wall: float, direction: str, options
    ) -> Optional[WallSignal]:
        """Check if break entry conditions are met."""
        confirmations = []

        # Delta must confirm
        delta = await self.signals.get_cumulative_delta()
        if self._delta_confirms_break(delta, direction):
            confirmations.append("delta_confirmation")

        # Flow alignment
        flow_state = await self.flow.get_current_state()
        if self._flow_aligns_with_break(flow_state, direction):
            confirmations.append("flow_alignment")

        # Volume surge
        volume_ratio = await self.signals.get_volume_ratio()
        if volume_ratio >= self.VOLUME_SURGE_MULTIPLIER:
            confirmations.append("volume_surge")

        if len(confirmations) < self.MIN_CONFIRMATIONS:
            return None

        if direction == "long":
            target_1 = nq_price + 30.0
            target_2 = nq_price + 50.0
            stop = wall - self.BREAK_FAIL_POINTS
        else:
            target_1 = nq_price - 30.0
            target_2 = nq_price - 50.0
            stop = wall + self.BREAK_FAIL_POINTS

        return WallSignal(
            mode=WallMode.BREAK,
            direction=direction,
            entry_price=nq_price,
            target_1=target_1,
            target_2=target_2,
            stop_loss=stop,
            wall_level=wall,
            conviction=self.conviction,
            confirmations=confirmations,
            timestamp=datetime.now(),
        )

    async def on_price_update(self, nq_price: float) -> None:
        """Monitor open position for stop/target hits and trailing stop updates."""
        if not self.position:
            return

        pos = self.position
        sig = pos.signal

        # Check hard stop
        if sig.direction == "long" and nq_price <= sig.stop_loss:
            await self.close_all("stop_loss_hit")
            return
        if sig.direction == "short" and nq_price >= sig.stop_loss:
            await self.close_all("stop_loss_hit")
            return

        # Check T1
        if not pos.t1_hit:
            if sig.direction == "long" and nq_price >= sig.target_1:
                await self.execution.partial_close(pos, 0.5, "target_1")
                pos.t1_hit = True
            elif sig.direction == "short" and nq_price <= sig.target_1:
                await self.execution.partial_close(pos, 0.5, "target_1")
                pos.t1_hit = True

        # Check T2
        if pos.t1_hit and not pos.t2_hit:
            if sig.direction == "long" and nq_price >= sig.target_2:
                await self.execution.partial_close(pos, 0.8, "target_2")
                pos.t2_hit = True
            elif sig.direction == "short" and nq_price <= sig.target_2:
                await self.execution.partial_close(pos, 0.8, "target_2")
                pos.t2_hit = True

        # BREAK mode: update trailing stop after T1
        if sig.mode == WallMode.BREAK and pos.t1_hit:
            if sig.direction == "long":
                new_trail = nq_price - 20.0
                if pos.trailing_stop is None or new_trail > pos.trailing_stop:
                    pos.trailing_stop = new_trail
                if nq_price <= pos.trailing_stop:
                    await self.close_all("trailing_stop")
            else:
                new_trail = nq_price + 20.0
                if pos.trailing_stop is None or new_trail < pos.trailing_stop:
                    pos.trailing_stop = new_trail
                if nq_price >= pos.trailing_stop:
                    await self.close_all("trailing_stop")

        # BOUNCE mode: time stop
        if sig.mode == WallMode.BOUNCE and pos.open_time:
            elapsed = (datetime.now() - pos.open_time).total_seconds() / 60
            if elapsed >= self.TIME_STOP_MINUTES and not pos.t1_hit:
                await self.close_all("time_stop")

    def _set_mode(self, regime) -> WallMode:
        from .regime_algo import Regime
        if regime in (Regime.A, Regime.B, Regime.C):
            return WallMode.BOUNCE
        elif regime in (Regime.D, Regime.E):
            return WallMode.BREAK
        return WallMode.INACTIVE

    def _compute_velocity(self) -> float:
        """Points per second over last 60 seconds."""
        if len(self._price_history) < 2:
            return 0.0
        recent = [(t, p) for t, p in self._price_history
                  if (datetime.now() - t).total_seconds() <= 60]
        if len(recent) < 2:
            return 0.0
        dt = (recent[-1][0] - recent[0][0]).total_seconds()
        if dt == 0:
            return 0.0
        return (recent[-1][1] - recent[0][1]) / dt

    def _update_price_history(self, price: float) -> None:
        now = datetime.now()
        self._price_history.append((now, price))
        # Keep only last 5 minutes
        cutoff = 300
        self._price_history = [
            (t, p) for t, p in self._price_history
            if (now - t).total_seconds() <= cutoff
        ]

    def _flow_aligns_with_bounce(self, flow_state, direction: str) -> bool:
        """Flow should not be aggressively pushing toward the wall."""
        if direction == "short":
            return flow_state not in ("AGGRESSIVE_BULLISH",)
        else:
            return flow_state not in ("AGGRESSIVE_BEARISH",)

    def _flow_aligns_with_break(self, flow_state, direction: str) -> bool:
        if direction == "long":
            return flow_state in ("AGGRESSIVE_BULLISH", "ACCUMULATION")
        else:
            return flow_state in ("AGGRESSIVE_BEARISH", "DISTRIBUTION")

    def _delta_confirms_bounce(self, delta: float, direction: str) -> bool:
        """Delta should be turning at the wall."""
        if direction == "long":
            return delta > 0  # buying pressure at put wall
        else:
            return delta < 0  # selling pressure at call wall

    def _delta_confirms_break(self, delta: float, direction: str) -> bool:
        if direction == "long":
            return delta > 500  # strong buying through call wall
        else:
            return delta < -500  # strong selling through put wall
```

---

## Configuration

```python
WALL_REACTION_CONFIG = {
    # Proximity
    "proximity_zone_points": 15.0,
    "approach_zone_points": 30.0,
    "break_confirm_points": 5.0,

    # Stops
    "bounce_wall_fail_points": 10.0,
    "break_fail_points": 15.0,
    "break_trailing_stop_points": 20.0,

    # Targets (BOUNCE)
    "bounce_target_1_call": 15.0,
    "bounce_target_2_call": 25.0,
    "bounce_target_1_put": 20.0,
    "bounce_target_2_put": 30.0,

    # Targets (BREAK)
    "break_target_1": 30.0,
    "break_target_2": 50.0,

    # Confirmation thresholds
    "absorption_threshold": 60,
    "volume_surge_multiplier": 1.5,
    "min_confirmations": 2,
    "fast_approach_pts_per_min": 5.0,

    # Time management
    "bounce_time_stop_minutes": 20,
    "session_close_time": "15:50",
}
```

---

## Notes on Wall Dissolution

Walls can dissolve between FlashAlpha polls. If a wall disappears in the next update:

1. If in BOUNCE mode with open position: reassess. If price is still near where the wall was, the mechanical support is gone. Exit at market.
2. If in BREAK mode: the break is now confirmed (wall dissolved = dealers stopped defending). Hold the position.
3. If wall moves more than 20 NQ points: update stop to new wall location. Do not exit unless new stop is hit.

This is why the `on_options_update` callback must be wired to WallReactionAlgo, not just `on_price_update`.
