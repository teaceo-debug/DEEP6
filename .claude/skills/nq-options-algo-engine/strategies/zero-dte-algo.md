# ZeroDTEAlgo — 0DTE Gamma Mechanics Trader

## Identity

**Class**: `ZeroDTEAlgo`
**Role**: Intraday-only strategy that exploits the unique mechanics of zero-days-to-expiration options. 0DTE options have explosive gamma near expiry, creating mechanical price forces that are distinct from standard GEX dynamics. ZeroDTEAlgo operates in three sequential phases across the trading day, each with different entry logic and targets.

**Theory reference**: `options-bias-engine/domains/zero-dte-mechanics.md` for the full 0DTE gamma explosion mechanics. `options-bias-engine/domains/opex-cycles.md` for expiry cycle context. `options-bias-engine/step1-regimes/regime-f-pin.md` for pin regime playbook.

**Core principle**: 0DTE gamma is the most concentrated force in the options market. Near expiry, a small move in the underlying creates enormous delta changes for 0DTE options, forcing dealers to hedge aggressively. This creates self-reinforcing moves toward pin strikes (when gamma is high) and explosive breakouts away from pin strikes (when gamma is overwhelmed). ZeroDTEAlgo trades both.

---

## Active Days

ZeroDTEAlgo is only active on 0DTE days. For NQ (via QQQ proxy):

| Day | 0DTE product | Notes |
|-----|-------------|-------|
| Monday | QQQ Monday expiry | Active |
| Wednesday | QQQ Wednesday expiry | Active |
| Friday | QQQ Friday expiry + monthly/quarterly OPEX | Active, highest volume |
| Tuesday, Thursday | No QQQ 0DTE | Inactive |

On non-0DTE days, ZeroDTEAlgo returns `INACTIVE` and does nothing.

Check at session start:
```python
is_zero_dte_day = event_calendar.is_zero_dte_day()
is_opex = event_calendar.is_monthly_opex()
is_quarterly_opex = event_calendar.is_quarterly_opex()
```

---

## Inputs

| Input | Source | Update frequency |
|-------|--------|-----------------|
| `zero_dte_magnet_qqq` | FlashAlpha `zero_dte` endpoint | Every 30-60 sec |
| `pin_score` | FlashAlpha `zero_dte.pin_risk.pin_score` | Every 30-60 sec |
| `zero_dte_call_wall_qqq` | FlashAlpha `zero_dte` | Every 30-60 sec |
| `zero_dte_put_wall_qqq` | FlashAlpha `zero_dte` | Every 30-60 sec |
| `expected_move_qqq` | FlashAlpha `zero_dte.expected_move` | Every 30-60 sec |
| `gamma_acceleration` | Derived from GEX rate of change | Per minute |
| `nq_price` | Rithmic MBO midpoint | Continuous |
| `absorption_score` | DEEP6 signal engine | Per bar |
| `flow_state` | Options flow engine | Every 10-15 sec |
| `chex_interpretation` | FlashAlpha `chex` | Every 30-60 sec |
| `session_time` | System clock | Continuous |
| `regime` | RegimeAlgo | On change |

All QQQ levels converted to NQ using the session ratio.

---

## Three Phases

### Phase 1: Morning (9:45 AM to 11:30 AM ET)
**Theme**: 0DTE wall formation. New 0DTE options are freshly written at the open. The walls form quickly. Trade the initial bounce or break at those walls.

### Phase 2: Midday (11:30 AM to 2:00 PM ET)
**Theme**: Pin gravitational pull. As time passes, 0DTE gamma concentrates around the magnet strike. Price is pulled toward it. Fade moves away from the magnet.

### Phase 3: Afternoon (2:00 PM to 3:45 PM ET)
**Theme**: Gamma acceleration. In the final 2 hours, 0DTE gamma explodes. Small moves create enormous dealer hedging flows. Ride the melt-up or melt-down.

---

## Phase 1: Morning Wall Formation

### Entry conditions (ALL must be true)

1. **Time**: 9:45 AM to 11:30 AM ET (skip first 15 minutes of opening noise)
2. **0DTE walls identified**: FlashAlpha `zero_dte` endpoint has valid call/put wall levels
3. **Price in zone**: within 12 NQ points of a 0DTE wall
4. **Absorption confirmed**: `absorption_score >= 55` at the wall level
5. **Flow not aggressive against**: flow_state is not aggressively pushing through the wall

### Entry direction

| Wall | Direction |
|------|-----------|
| 0DTE call wall | Short NQ |
| 0DTE put wall | Long NQ |

### Targets (smaller than standard wall bounce)

| Target | NQ points | Notes |
|--------|-----------|-------|
| T1 | 10 NQ points | Take 60% here |
| T2 | 15 NQ points | Take remaining 40% |

0DTE walls are less stable than standard GEX walls. Take profits faster.

### Stop loss

- **Hard stop**: 8 NQ points beyond the wall
- **Soft stop**: if absorption score drops below 30, exit at market

### Why smaller targets

0DTE walls shift throughout the morning as new options are written and existing ones expire. A wall that holds at 9:50 AM may dissolve by 10:30 AM. Take profits quickly and re-evaluate.

### Estimated performance

| Condition | Estimated win rate | Avg R:R |
|-----------|-------------------|---------|
| Strong absorption + flow alignment | 60-70% | 1.2:1 to 1.5:1 |
| Weak absorption only | 45-55% | 1:1 |

---

## Phase 2: Midday Pin Fade

### Entry conditions (ALL must be true)

1. **Time**: 11:30 AM to 2:00 PM ET
2. **Pin score >= 70**: FlashAlpha `zero_dte.pin_risk.pin_score` must be at least 70
3. **Price displaced from magnet**: `abs(nq_price - magnet_nq) > 10` (price must be away from magnet to have a fade trade)
4. **Direction**: toward the magnet (not away from it)
5. **No aggressive flow against**: flow_state is not aggressively pushing away from magnet

### Entry direction

| Price vs magnet | Direction |
|----------------|-----------|
| Price above magnet | Short NQ (fade toward magnet) |
| Price below magnet | Long NQ (fade toward magnet) |

### Entry execution

- Use limit order 2-3 NQ points in the direction of the magnet
- The pin fade is a gravity trade. Don't chase it.

### Targets

| Target | NQ points | Notes |
|--------|-----------|-------|
| T1 | Magnet strike (50% of distance) | Take 50% here |
| T2 | Magnet strike (full distance) | Take remaining 50% |

The target IS the magnet. If price is 20 NQ points from the magnet, T1 is at 10 points, T2 is at 20 points.

### Stop loss

- **Hard stop**: 15 NQ points beyond entry (pin breaks)
- **Pin score stop**: if `pin_score` drops below 50 after entry, exit at market (pin is dissolving)

### Pin score interpretation

| Pin score | Interpretation | Action |
|-----------|---------------|--------|
| 0-40 | Weak pin, no gravity | Skip Phase 2 entirely |
| 40-60 | Moderate pin | Reduce size 50% |
| 60-80 | Strong pin | Standard size |
| 80-100 | Extreme pin | Allow 1.25x size |

### Estimated performance

| Condition | Estimated win rate | Avg R:R |
|-----------|-------------------|---------|
| Pin score >= 80 | 65-72% | 1.5:1 to 2:1 |
| Pin score 60-80 | 55-65% | 1.2:1 to 1.5:1 |

---

## Phase 3: Afternoon Gamma Acceleration

### Entry conditions (ALL must be true)

1. **Time**: 2:00 PM to 3:45 PM ET
2. **Gamma acceleration detected**: rate of change of GEX is accelerating (see computation below)
3. **Directional flow confirming**: flow_state is AGGRESSIVE_BULLISH or AGGRESSIVE_BEARISH (not neutral)
4. **Direction consistent with flow**: long on AGGRESSIVE_BULLISH, short on AGGRESSIVE_BEARISH
5. **Not fighting pin**: if pin_score >= 70, only trade in the direction of the magnet

### Gamma acceleration computation

```python
# Track GEX readings over time
gex_history = [(t1, gex1), (t2, gex2), ...]

# Rate of change (GEX per minute)
gex_roc = (gex_now - gex_5min_ago) / 5

# Acceleration (rate of change is itself changing)
gex_acceleration = (gex_roc_now - gex_roc_5min_ago) / 5

# Threshold: acceleration must be meaningful
gamma_accelerating = abs(gex_acceleration) > GAMMA_ACCEL_THRESHOLD
```

In practice, gamma acceleration is most visible as a rapid increase in the absolute value of GEX as 0DTE options approach expiry. The FlashAlpha `zero_dte` endpoint's `gamma_acceleration` field (if available) can be used directly.

### Entry direction

| Flow state | Direction |
|-----------|-----------|
| AGGRESSIVE_BULLISH | Long NQ |
| AGGRESSIVE_BEARISH | Short NQ |

### Entry execution

- Use market order. Gamma acceleration moves are fast. Limit orders will miss.
- Enter immediately when conditions are met. Do not wait for a pullback.

### Targets

| Target | NQ points | Notes |
|--------|-----------|-------|
| T1 | 15 NQ points | Take 40% here |
| T2 | Next standard (non-0DTE) wall or expected move boundary | Take 40% here |
| T3 | Trail remaining 20% with 12-point trailing stop | Capture the melt |

The afternoon gamma acceleration can produce 30-80 NQ point moves in 30-60 minutes. The trailing stop on T3 is designed to capture extended runs.

### Stop loss

- **Hard stop**: 12 NQ points against entry
- **Trailing stop** (after T1): trail 12 NQ points from best price
- **Time stop**: exit all by 3:45 PM ET (do not hold into the final 15 minutes)

### Why trailing stop is tight

Gamma acceleration moves can reverse violently. A 50-point melt-up can give back 30 points in 5 minutes if a large order hits the book. The 12-point trailing stop is intentionally tight to protect gains.

### Estimated performance

| Condition | Estimated win rate | Avg R:R |
|-----------|-------------------|---------|
| Strong gamma accel + aggressive flow | 55-65% | 2:1 to 3:1 |
| Moderate accel + moderate flow | 45-55% | 1.5:1 to 2:1 |

---

## Phase State Machine

```
INACTIVE (non-0DTE day)
  │
  ▼ session_start() on 0DTE day
PHASE_1_MORNING (9:45 - 11:30)
  │
  ├─ Wall bounce/break signal → POSITION_OPEN → MONITORING → POSITION_CLOSED → PHASE_1_MORNING
  │
  ▼ 11:30 AM
PHASE_2_MIDDAY (11:30 - 14:00)
  │
  ├─ Pin fade signal (if pin_score >= 70) → POSITION_OPEN → MONITORING → POSITION_CLOSED → PHASE_2_MIDDAY
  │
  ▼ 14:00 PM
PHASE_3_AFTERNOON (14:00 - 15:45)
  │
  ├─ Gamma acceleration signal → POSITION_OPEN → MONITORING → POSITION_CLOSED → PHASE_3_AFTERNOON
  │
  ▼ 15:45 PM
SESSION_CLOSE (close all, reset state)
  │
  ▼ next session
INACTIVE
```

Phase transitions are time-based. Any open position from Phase 1 is closed at 11:30 AM before Phase 2 begins. Any open position from Phase 2 is closed at 2:00 PM before Phase 3 begins.

---

## Timing Rules

| Rule | Detail |
|------|--------|
| No entries before 9:45 AM | Opening noise, 0DTE walls not yet stable |
| No entries after 3:45 PM | Too close to close, gamma can be violent |
| Phase 1 close at 11:30 AM | Close all Phase 1 positions before midday |
| Phase 2 close at 2:00 PM | Close all Phase 2 positions before afternoon |
| Hard close at 3:50 PM | All positions closed regardless of P&L |

---

## Position Sizing

0DTE strategies carry higher variance than standard strategies. Use smaller base sizes.

```python
base_contracts = 1

phase_multiplier = {
    "phase_1": 0.75,    # wall formation, less stable
    "phase_2": 1.0,     # pin fade, most predictable
    "phase_3": 0.75,    # gamma accel, high variance
}

pin_score_multiplier = {
    "weak": 0.5,        # pin_score 40-60
    "strong": 1.0,      # pin_score 60-80
    "extreme": 1.25,    # pin_score 80-100
}

opex_multiplier = 1.25 if is_monthly_opex else 1.0  # OPEX has stronger mechanics

final_contracts = round(
    base_contracts
    * phase_multiplier[current_phase]
    * pin_score_multiplier[pin_strength]
    * opex_multiplier
    * conviction_multiplier  # from RegimeAlgo
)
```

---

## Kill Switches

| Condition | Action |
|-----------|--------|
| Non-0DTE day | Deactivate entirely |
| Regime G (pre-event) | Deactivate, stand aside |
| Pin score drops below 50 during Phase 2 position | Exit at market |
| 0DTE walls dissolve (FlashAlpha removes them) | Exit Phase 1 positions |
| VIX spikes > 2 points in 30 min | Exit all positions (vol expansion overrides pin mechanics) |
| Daily loss limit hit | Deactivate |
| 3 consecutive losses | Deactivate |
| 3:45 PM ET | No new entries |
| 3:50 PM ET | Close all positions |

---

## Historical Patterns

These patterns are documented in `options-bias-engine/domains/zero-dte-mechanics.md`. ZeroDTEAlgo is designed to capture them.

### Gamma squeeze days

When 0DTE call walls are heavily loaded and price approaches them in the afternoon, dealers must buy aggressively to hedge. This creates a self-reinforcing squeeze. Characteristics:
- Price accelerates as it approaches the call wall
- Volume surges in the final 2 hours
- Absorption at the call wall is very high (dealers defending)
- If the wall breaks, the squeeze accelerates further

Phase 3 is designed to capture the squeeze. Phase 1 captures the initial approach.

### Vol crush rallies

When IV is elevated at the open and then collapses during the day (common after overnight events), the vol crush creates mechanical buying. Characteristics:
- VIX drops 1+ point from open
- 0DTE put walls hold (dealers not forced to sell)
- Charm drift is positive (dealers buying into close)

VolSurfaceAlgo's VannaRally and CharmDrift capture this. ZeroDTEAlgo's Phase 3 captures the afternoon acceleration.

### Charm drift into close

In the final 90 minutes, charm (delta decay) creates directional pressure. On 0DTE days, this is amplified because 0DTE options have the highest charm of any expiry. Characteristics:
- CHEX shows directional bias
- Price drifts steadily in one direction from 2:00-3:30 PM
- No large reversals unless a macro event hits

Phase 3 captures this. The 12-point trailing stop is designed to ride the drift while protecting against reversals.

---

## Python Class Skeleton

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import asyncio
from datetime import datetime, time


class ZeroDTEPhase(Enum):
    INACTIVE = "inactive"
    PHASE_1_MORNING = "phase_1_morning"
    PHASE_2_MIDDAY = "phase_2_midday"
    PHASE_3_AFTERNOON = "phase_3_afternoon"
    SESSION_CLOSE = "session_close"


@dataclass
class ZeroDTESignal:
    phase: ZeroDTEPhase
    direction: str              # "long" or "short"
    entry_price: float
    target_1: float
    target_2: float
    target_3: Optional[float]
    stop_loss: float
    trailing_stop_points: Optional[float]
    conviction: float
    rationale: dict
    timestamp: datetime


@dataclass
class ZeroDTEPosition:
    signal: ZeroDTESignal
    contracts: int
    entry_fill: float
    t1_hit: bool = False
    t2_hit: bool = False
    trailing_stop: Optional[float] = None
    open_time: Optional[datetime] = None


class ZeroDTEAlgo:
    """
    Intraday 0DTE options mechanics trader.
    Three phases: morning wall formation, midday pin fade, afternoon gamma acceleration.
    Only active on 0DTE days (Mon, Wed, Fri for QQQ).
    """

    # Phase timing
    PHASE_1_START = time(9, 45)
    PHASE_1_END = time(11, 30)
    PHASE_2_START = time(11, 30)
    PHASE_2_END = time(14, 0)
    PHASE_3_START = time(14, 0)
    PHASE_3_END = time(15, 45)
    SESSION_CLOSE_TIME = time(15, 50)
    NO_NEW_ENTRIES_TIME = time(15, 45)

    # Phase 1 thresholds
    P1_PROXIMITY_POINTS = 12.0
    P1_ABSORPTION_THRESHOLD = 55
    P1_STOP_POINTS = 8.0
    P1_TARGET_1_POINTS = 10.0
    P1_TARGET_2_POINTS = 15.0

    # Phase 2 thresholds
    P2_PIN_SCORE_MIN = 70
    P2_PIN_SCORE_REDUCED = 60
    P2_DISPLACEMENT_MIN = 10.0
    P2_STOP_POINTS = 15.0

    # Phase 3 thresholds
    P3_STOP_POINTS = 12.0
    P3_TARGET_1_POINTS = 15.0
    P3_TRAILING_STOP_POINTS = 12.0
    P3_GAMMA_ACCEL_THRESHOLD = 0.5  # GEX change per minute per minute

    def __init__(self, execution_engine, signal_engine, flow_engine, event_calendar, logger):
        self.execution = execution_engine
        self.signals = signal_engine
        self.flow = flow_engine
        self.calendar = event_calendar
        self.logger = logger
        self.phase = ZeroDTEPhase.INACTIVE
        self.active_regime = None
        self.conviction = 0.0
        self.position: Optional[ZeroDTEPosition] = None
        self._gex_history: list[tuple[datetime, float]] = []
        self._is_zero_dte_day = False

    async def session_start(self) -> None:
        """Call at session open to initialize for the day."""
        self._is_zero_dte_day = self.calendar.is_zero_dte_day()
        if self._is_zero_dte_day:
            self.phase = ZeroDTEPhase.PHASE_1_MORNING
            self.logger.info("ZeroDTEAlgo: 0DTE day detected, activating")
        else:
            self.phase = ZeroDTEPhase.INACTIVE
            self.logger.info("ZeroDTEAlgo: Not a 0DTE day, staying inactive")

    async def activate(self, regime, conviction: float, options) -> None:
        """Called by RegimeAlgo. Only activates if it's a 0DTE day."""
        self.active_regime = regime
        self.conviction = conviction
        if not self._is_zero_dte_day:
            self.phase = ZeroDTEPhase.INACTIVE

    async def deactivate(self, reason: str) -> None:
        self.active_regime = None
        self.logger.info(f"ZeroDTEAlgo deactivated: {reason}")

    async def close_all(self, reason: str, grace_seconds: int = 0) -> None:
        if self.position:
            if grace_seconds > 0:
                await asyncio.sleep(grace_seconds)
            await self.execution.close_position(self.position, reason)
            self.position = None

    async def evaluate(self, options, nq_price: float) -> Optional[ZeroDTESignal]:
        """
        Main evaluation. Called on each price or options update.
        Returns a signal if entry conditions are met.
        """
        if not self._is_zero_dte_day:
            return None

        now_time = datetime.now().time()

        # Update phase based on time
        self._update_phase(now_time)

        if self.phase == ZeroDTEPhase.INACTIVE:
            return None

        if now_time >= self.NO_NEW_ENTRIES_TIME:
            return None

        if self.position:
            return None  # already in a position

        if self.phase == ZeroDTEPhase.PHASE_1_MORNING:
            return await self._evaluate_phase_1(options, nq_price)
        elif self.phase == ZeroDTEPhase.PHASE_2_MIDDAY:
            return await self._evaluate_phase_2(options, nq_price)
        elif self.phase == ZeroDTEPhase.PHASE_3_AFTERNOON:
            return await self._evaluate_phase_3(options, nq_price)

        return None

    def _update_phase(self, now_time: time) -> None:
        """Advance phase based on current time."""
        if not self._is_zero_dte_day:
            return

        if now_time >= self.SESSION_CLOSE_TIME:
            if self.phase != ZeroDTEPhase.SESSION_CLOSE:
                self.phase = ZeroDTEPhase.SESSION_CLOSE
        elif now_time >= self.PHASE_3_START:
            if self.phase == ZeroDTEPhase.PHASE_2_MIDDAY:
                # Transition: close Phase 2 positions
                asyncio.create_task(self.close_all("phase_2_end"))
                self.phase = ZeroDTEPhase.PHASE_3_AFTERNOON
        elif now_time >= self.PHASE_2_START:
            if self.phase == ZeroDTEPhase.PHASE_1_MORNING:
                # Transition: close Phase 1 positions
                asyncio.create_task(self.close_all("phase_1_end"))
                self.phase = ZeroDTEPhase.PHASE_2_MIDDAY
        elif now_time >= self.PHASE_1_START:
            if self.phase == ZeroDTEPhase.INACTIVE:
                self.phase = ZeroDTEPhase.PHASE_1_MORNING

    async def _evaluate_phase_1(self, options, nq_price: float) -> Optional[ZeroDTESignal]:
        """Phase 1: 0DTE wall bounce."""
        zero_dte_call = options.zero_dte_call_wall_nq
        zero_dte_put = options.zero_dte_put_wall_nq

        if zero_dte_call is None or zero_dte_put is None:
            return None

        absorption = await self.signals.get_absorption_score()
        if absorption < self.P1_ABSORPTION_THRESHOLD:
            return None

        flow_state = await self.flow.get_current_state()

        # Check call wall (short)
        if abs(nq_price - zero_dte_call) < self.P1_PROXIMITY_POINTS:
            if flow_state not in ("AGGRESSIVE_BULLISH",):
                return ZeroDTESignal(
                    phase=ZeroDTEPhase.PHASE_1_MORNING,
                    direction="short",
                    entry_price=nq_price,
                    target_1=nq_price - self.P1_TARGET_1_POINTS,
                    target_2=nq_price - self.P1_TARGET_2_POINTS,
                    target_3=None,
                    stop_loss=zero_dte_call + self.P1_STOP_POINTS,
                    trailing_stop_points=None,
                    conviction=self.conviction * 0.75,
                    rationale={"wall": "0dte_call", "absorption": absorption, "flow": flow_state},
                    timestamp=datetime.now(),
                )

        # Check put wall (long)
        if abs(nq_price - zero_dte_put) < self.P1_PROXIMITY_POINTS:
            if flow_state not in ("AGGRESSIVE_BEARISH",):
                return ZeroDTESignal(
                    phase=ZeroDTEPhase.PHASE_1_MORNING,
                    direction="long",
                    entry_price=nq_price,
                    target_1=nq_price + self.P1_TARGET_1_POINTS,
                    target_2=nq_price + self.P1_TARGET_2_POINTS,
                    target_3=None,
                    stop_loss=zero_dte_put - self.P1_STOP_POINTS,
                    trailing_stop_points=None,
                    conviction=self.conviction * 0.75,
                    rationale={"wall": "0dte_put", "absorption": absorption, "flow": flow_state},
                    timestamp=datetime.now(),
                )

        return None

    async def _evaluate_phase_2(self, options, nq_price: float) -> Optional[ZeroDTESignal]:
        """Phase 2: Pin fade toward magnet."""
        pin_score = options.pin_score
        magnet_nq = options.zero_dte_magnet_nq

        if pin_score < self.P2_PIN_SCORE_MIN:
            return None

        if magnet_nq is None:
            return None

        displacement = nq_price - magnet_nq
        if abs(displacement) < self.P2_DISPLACEMENT_MIN:
            return None  # too close to magnet, no fade trade

        flow_state = await self.flow.get_current_state()

        direction = "short" if displacement > 0 else "long"

        # Don't fade if flow is aggressively pushing away from magnet
        if direction == "short" and flow_state == "AGGRESSIVE_BULLISH":
            return None
        if direction == "long" and flow_state == "AGGRESSIVE_BEARISH":
            return None

        # Targets: toward magnet
        half_distance = abs(displacement) / 2
        if direction == "short":
            target_1 = nq_price - half_distance
            target_2 = magnet_nq
            stop = nq_price + self.P2_STOP_POINTS
        else:
            target_1 = nq_price + half_distance
            target_2 = magnet_nq
            stop = nq_price - self.P2_STOP_POINTS

        # Adjust conviction based on pin score
        pin_conviction = 1.0 if pin_score >= 80 else (0.75 if pin_score >= 60 else 0.5)

        return ZeroDTESignal(
            phase=ZeroDTEPhase.PHASE_2_MIDDAY,
            direction=direction,
            entry_price=nq_price,
            target_1=target_1,
            target_2=target_2,
            target_3=None,
            stop_loss=stop,
            trailing_stop_points=None,
            conviction=self.conviction * pin_conviction,
            rationale={"pin_score": pin_score, "magnet_nq": magnet_nq, "displacement": displacement},
            timestamp=datetime.now(),
        )

    async def _evaluate_phase_3(self, options, nq_price: float) -> Optional[ZeroDTESignal]:
        """Phase 3: Gamma acceleration ride."""
        gamma_accel = self._compute_gamma_acceleration(options.net_gex)
        if abs(gamma_accel) < self.P3_GAMMA_ACCEL_THRESHOLD:
            return None

        flow_state = await self.flow.get_current_state()
        if flow_state not in ("AGGRESSIVE_BULLISH", "AGGRESSIVE_BEARISH"):
            return None

        direction = "long" if flow_state == "AGGRESSIVE_BULLISH" else "short"

        # Check pin: if pin is strong, only trade toward magnet
        pin_score = options.pin_score
        magnet_nq = options.zero_dte_magnet_nq
        if pin_score >= 70 and magnet_nq is not None:
            magnet_direction = "long" if nq_price < magnet_nq else "short"
            if direction != magnet_direction:
                return None  # fighting the pin

        # Targets
        next_wall = options.call_wall_nq if direction == "long" else options.put_wall_nq
        if direction == "long":
            target_1 = nq_price + self.P3_TARGET_1_POINTS
            target_2 = next_wall if next_wall else nq_price + 40.0
            stop = nq_price - self.P3_STOP_POINTS
        else:
            target_1 = nq_price - self.P3_TARGET_1_POINTS
            target_2 = next_wall if next_wall else nq_price - 40.0
            stop = nq_price + self.P3_STOP_POINTS

        return ZeroDTESignal(
            phase=ZeroDTEPhase.PHASE_3_AFTERNOON,
            direction=direction,
            entry_price=nq_price,
            target_1=target_1,
            target_2=target_2,
            target_3=None,
            stop_loss=stop,
            trailing_stop_points=self.P3_TRAILING_STOP_POINTS,
            conviction=self.conviction * 0.75,
            rationale={"gamma_accel": gamma_accel, "flow": flow_state, "pin_score": pin_score},
            timestamp=datetime.now(),
        )

    def _compute_gamma_acceleration(self, current_gex: float) -> float:
        """Compute rate of change of GEX rate of change."""
        now = datetime.now()
        self._gex_history.append((now, current_gex))
        # Keep last 15 minutes
        self._gex_history = [
            (t, g) for t, g in self._gex_history
            if (now - t).total_seconds() <= 900
        ]
        if len(self._gex_history) < 3:
            return 0.0

        # Simple: compare current GEX to 5 minutes ago
        five_min_ago = [(t, g) for t, g in self._gex_history
                        if (now - t).total_seconds() <= 300]
        if not five_min_ago:
            return 0.0

        oldest = five_min_ago[0]
        dt_minutes = (now - oldest[0]).total_seconds() / 60
        if dt_minutes == 0:
            return 0.0

        return (current_gex - oldest[1]) / dt_minutes

    async def on_price_update(self, nq_price: float, options) -> None:
        """Monitor open position for stop/target hits."""
        if not self.position:
            return

        now_time = datetime.now().time()
        pos = self.position
        sig = pos.signal

        # Hard session close
        if now_time >= self.SESSION_CLOSE_TIME:
            await self.close_all("session_close")
            return

        # Phase transition close
        if sig.phase == ZeroDTEPhase.PHASE_1_MORNING and now_time >= self.PHASE_1_END:
            await self.close_all("phase_1_end")
            return
        if sig.phase == ZeroDTEPhase.PHASE_2_MIDDAY and now_time >= self.PHASE_2_END:
            await self.close_all("phase_2_end")
            return

        # Hard stop
        if sig.direction == "long" and nq_price <= sig.stop_loss:
            await self.close_all("stop_loss")
            return
        if sig.direction == "short" and nq_price >= sig.stop_loss:
            await self.close_all("stop_loss")
            return

        # Phase 2: pin score soft stop
        if sig.phase == ZeroDTEPhase.PHASE_2_MIDDAY:
            if options.pin_score < 50:
                await self.close_all("pin_dissolved")
                return

        # Target 1
        if not pos.t1_hit:
            if sig.direction == "long" and nq_price >= sig.target_1:
                await self.execution.partial_close(pos, 0.6, "target_1")
                pos.t1_hit = True
            elif sig.direction == "short" and nq_price <= sig.target_1:
                await self.execution.partial_close(pos, 0.6, "target_1")
                pos.t1_hit = True

        # Target 2
        if pos.t1_hit and not pos.t2_hit:
            if sig.direction == "long" and nq_price >= sig.target_2:
                await self.execution.partial_close(pos, 0.9, "target_2")
                pos.t2_hit = True
            elif sig.direction == "short" and nq_price <= sig.target_2:
                await self.execution.partial_close(pos, 0.9, "target_2")
                pos.t2_hit = True

        # Phase 3 trailing stop
        if sig.phase == ZeroDTEPhase.PHASE_3_AFTERNOON and sig.trailing_stop_points and pos.t1_hit:
            if sig.direction == "long":
                new_trail = nq_price - sig.trailing_stop_points
                if pos.trailing_stop is None or new_trail > pos.trailing_stop:
                    pos.trailing_stop = new_trail
                if nq_price <= pos.trailing_stop:
                    await self.close_all("trailing_stop")
            else:
                new_trail = nq_price + sig.trailing_stop_points
                if pos.trailing_stop is None or new_trail < pos.trailing_stop:
                    pos.trailing_stop = new_trail
                if nq_price >= pos.trailing_stop:
                    await self.close_all("trailing_stop")
```

---

## Configuration

```python
ZERO_DTE_CONFIG = {
    # Phase timing
    "phase_1_start": "09:45",
    "phase_1_end": "11:30",
    "phase_2_start": "11:30",
    "phase_2_end": "14:00",
    "phase_3_start": "14:00",
    "phase_3_end": "15:45",
    "no_new_entries_time": "15:45",
    "session_close_time": "15:50",

    # Phase 1
    "p1_proximity_points": 12.0,
    "p1_absorption_threshold": 55,
    "p1_stop_points": 8.0,
    "p1_target_1_points": 10.0,
    "p1_target_2_points": 15.0,

    # Phase 2
    "p2_pin_score_min": 70,
    "p2_pin_score_reduced": 60,
    "p2_displacement_min": 10.0,
    "p2_stop_points": 15.0,

    # Phase 3
    "p3_stop_points": 12.0,
    "p3_target_1_points": 15.0,
    "p3_trailing_stop_points": 12.0,
    "p3_gamma_accel_threshold": 0.5,

    # Position sizing
    "opex_size_multiplier": 1.25,
    "quarterly_opex_size_multiplier": 1.5,
}
```

---

## Notes on 0DTE Wall Stability

0DTE walls are fundamentally different from standard GEX walls:

1. **They form at the open** as market makers write new 0DTE options. The first 15 minutes (9:30-9:45) are noisy as walls establish.
2. **They shift throughout the day** as 0DTE options are bought and sold. A wall at 9:50 AM may be gone by 11:00 AM.
3. **They accelerate near expiry**. In the final 2 hours, 0DTE gamma is enormous. A wall that barely mattered at 10 AM becomes a massive force at 3 PM.
4. **They can dissolve instantly** if a large order sweeps through them. Always monitor FlashAlpha for wall updates.

This is why Phase 1 uses smaller targets (10-15 NQ points) and Phase 3 uses trailing stops rather than fixed targets. The mechanics change throughout the day.
