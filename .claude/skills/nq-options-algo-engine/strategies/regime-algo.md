# RegimeAlgo — Gamma Regime Orchestrator

## Identity

**Class**: `RegimeAlgo`
**Role**: Master orchestrator. Detects the current gamma regime from FlashAlpha data, classifies it into one of seven regimes (A-G), and activates or deactivates sub-strategies accordingly. Every other algo in this directory is a sub-strategy that RegimeAlgo controls.

**Theory reference**: `options-bias-engine/step1-regimes/regime-identification.md` for classification rules, `options-bias-engine/step1-regimes/regime-transitions.md` for transition handling.

**Core principle**: The regime is the context. Trading without knowing the regime is like driving without knowing whether you're on a highway or a parking lot. The same price action means completely different things in Regime A vs Regime E.

---

## Inputs

| Input | Source | Update frequency |
|-------|--------|-----------------|
| `net_gex` | FlashAlpha `exposure_summary` | Every 30-60 sec |
| `gamma_flip` | FlashAlpha `exposure_summary` | Every 30-60 sec |
| `call_wall` | FlashAlpha `exposure_levels` | Every 30-60 sec |
| `put_wall` | FlashAlpha `exposure_levels` | Every 30-60 sec |
| `zero_dte_magnet` | FlashAlpha `zero_dte` | Every 30-60 sec |
| `pin_score` | FlashAlpha `zero_dte.pin_risk.pin_score` | Every 30-60 sec |
| `nq_price` | Rithmic MBO best bid/ask midpoint | Continuous |
| `scheduled_events` | Economic calendar | Session start |

All FlashAlpha levels are QQQ-denominated. Convert to NQ before any comparison:

```python
nq_level = qqq_level * (nq_price / qqq_price)
```

Recompute the ratio at session open and whenever it drifts more than 0.5% from the prior value.

---

## Regime Classification Engine

### Classification rules (in priority order)

**Step 1: Check for pre-event (Regime G)**
If a scheduled macro event (FOMC, CPI, NFP, Fed speaker) is within 30 minutes:
- Classify as Regime G regardless of GEX structure
- Deactivate all sub-strategies
- Do not re-classify until 5 minutes after the event

**Step 2: Check for pin regime (Regime F)**
If `pin_score >= 70` AND it's a 0DTE day AND time is after 11:30 AM ET:
- Classify as Regime F
- Activate only `ZeroDTEAlgo` in pin mode
- Pin regime overrides wall regimes

**Step 3: Determine gamma sign**
```
positive_gamma = net_gex > 0
negative_gamma = net_gex < 0
```

**Step 4: Determine price position relative to flip**
```
above_flip = nq_price > gamma_flip_nq
below_flip = nq_price < gamma_flip_nq
near_flip = abs(nq_price - gamma_flip_nq) < 10  # within 10 NQ points
```

**Step 5: Determine wall proximity**
```
at_call_wall = abs(nq_price - call_wall_nq) < 15
at_put_wall = abs(nq_price - put_wall_nq) < 15
between_walls = not at_call_wall and not at_put_wall
```

**Step 6: Classify**

| Condition | Regime |
|-----------|--------|
| `positive_gamma AND between_walls` | A |
| `positive_gamma AND at_call_wall` | B |
| `positive_gamma AND at_put_wall` | C |
| `negative_gamma AND above_flip` | D |
| `negative_gamma AND below_flip` | E |
| `pin_score >= 70 AND 0DTE AND after 11:30` | F |
| `event within 30 min` | G |

**Near-flip ambiguity**: When `near_flip` is true and gamma is positive, treat as Regime A with reduced conviction. When `near_flip` is true and gamma is negative, treat as Regime D or E based on price side but reduce position size by 50%.

---

## Stability Scoring

Track how long the current regime has held. Confidence in the regime classification increases with time.

```python
stability_minutes = (now - regime_start_time).total_seconds() / 60

if stability_minutes < 5:
    regime_confidence = 0.5   # just transitioned, uncertain
elif stability_minutes < 15:
    regime_confidence = 0.75  # settling in
else:
    regime_confidence = 1.0   # stable
```

Apply `regime_confidence` as a multiplier to position sizing. A regime that just flipped 2 minutes ago gets half the normal size.

---

## Playbook Activation Matrix

When regime is classified, activate the corresponding sub-strategies:

| Regime | Active sub-strategies | Bias | Notes |
|--------|----------------------|------|-------|
| A | `WallReactionAlgo` (both modes), `VolSurfaceAlgo` (charm) | Neutral, range | Fade extremes, mean-revert |
| B | `WallReactionAlgo` (bounce, short bias) | Bearish at wall | Call wall ceiling test |
| C | `WallReactionAlgo` (bounce, long bias) | Bullish at wall | Highest win rate setup |
| D | `WallReactionAlgo` (break mode), `VolSurfaceAlgo` (vanna) | Bullish momentum | Unstable, tight risk |
| E | `WallReactionAlgo` (break mode, short), `VolSurfaceAlgo` (vanna) | Bearish momentum | Trending bear, never buy dips |
| F | `ZeroDTEAlgo` (pin mode only) | Toward magnet | Gravity trade |
| G | NONE | Stand aside | All strategies deactivated |

Sub-strategies are activated by calling their `activate(regime, conviction)` method and deactivated by calling `deactivate(reason)`.

---

## Transition Rules

When `regime_current != regime_prev`, a transition has occurred.

### Transition handling sequence

1. **Emit transition signal** with `(from_regime, to_regime, timestamp, nq_price_at_transition)`
2. **Close existing positions** from the old regime within 2 bars (10 seconds on a 5-second bar)
   - Exception: if the new regime is compatible with the existing position direction, allow it to run with updated stops
3. **Deactivate old sub-strategies** by calling their `deactivate("regime_transition")` method
4. **Wait for stability** — do not activate new sub-strategies until `stability_minutes >= 3`
5. **Activate new sub-strategies** once stability threshold is met

### High-priority transitions (immediate action)

| Transition | Action |
|------------|--------|
| Any → G | Close all positions immediately, deactivate everything |
| D → E or E → D | Flip direction, close and reverse if conviction >= 70 |
| A → D or A → E | Close range trades, switch to momentum mode |
| D/E → A | Close momentum trades, switch to range mode |

### Transition conviction bonus

A regime transition itself is a signal. When price crosses the gamma flip:
- Add 15 points to the composite bias score in the direction of the new regime
- This bonus decays linearly over 30 minutes

---

## Position Sizing

Position sizing is delegated to the conviction score from the composite bias engine. RegimeAlgo provides the regime multiplier.

```python
base_contracts = 1  # minimum unit

regime_multiplier = {
    "A": 1.0,   # standard
    "B": 0.75,  # wall test, uncertain
    "C": 1.25,  # highest win rate, allow slightly larger
    "D": 0.75,  # unstable, tight
    "E": 1.0,   # trending, standard
    "F": 0.5,   # 0DTE, high variance
    "G": 0.0,   # no trades
}

stability_multiplier = regime_confidence  # 0.5 to 1.0

final_contracts = round(
    base_contracts
    * regime_multiplier[current_regime]
    * stability_multiplier
    * conviction_multiplier  # from composite score, 0.5 to 2.0
)
```

Full position sizing rules: `options-bias-engine/step6-risk/position-sizing.md`

---

## Kill Switches

RegimeAlgo monitors these conditions and triggers a full shutdown if any are met.

| Condition | Action |
|-----------|--------|
| 3 consecutive losses today | Deactivate all sub-strategies, set `trading_halted = True` |
| Daily loss > $1,500 (3 NQ points × 5 contracts) | Same as above |
| FlashAlpha data stale > 5 minutes | Deactivate all, log warning |
| Rithmic feed disconnected | Deactivate all, attempt reconnect |
| Regime G detected | Deactivate all, stand aside |
| `net_gex` changes sign within 5 minutes twice | Unstable flip zone, reduce size 75% |

Full kill switch rules: `options-bias-engine/step6-risk/kill-switches.md`

---

## State Machine

```
IDLE
  │
  ▼ on_options_update() called with valid data
REGIME_DETECTING
  │
  ▼ classification complete
REGIME_CLASSIFIED
  │
  ├─ Regime G → STAND_ASIDE (loop back to REGIME_DETECTING on next update)
  │
  ▼ stability_minutes >= 3
PLAYBOOK_ACTIVE
  │
  ▼ sub-strategy emits signal
SIGNAL_GENERATED
  │
  ▼ risk gates pass
POSITION_OPEN
  │
  ├─ TP hit → POSITION_CLOSED → PLAYBOOK_ACTIVE
  ├─ SL hit → POSITION_CLOSED → PLAYBOOK_ACTIVE
  ├─ Regime transition → POSITION_CLOSED → REGIME_DETECTING
  └─ Kill switch → TRADING_HALTED (manual reset required)
```

---

## Performance Characteristics

These are estimated ranges based on the underlying setup win rates from `options-bias-engine/step5-setups/`. RegimeAlgo itself doesn't trade — it orchestrates. Performance depends on which sub-strategies are active.

| Metric | Estimated range |
|--------|----------------|
| Regime classification accuracy | 80-90% (FlashAlpha data quality dependent) |
| Transition detection lag | 30-90 seconds (poll interval dependent) |
| False regime flip rate | ~5% (near-flip zone ambiguity) |
| Sub-strategy activation latency | < 5 seconds after stability threshold |

---

## Python Class Skeleton

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import asyncio
from datetime import datetime, time


class Regime(Enum):
    A = "positive_between_walls"
    B = "positive_at_call_wall"
    C = "positive_at_put_wall"
    D = "negative_above_flip"
    E = "negative_below_flip"
    F = "pin"
    G = "pre_event"
    UNKNOWN = "unknown"


@dataclass
class OptionsState:
    net_gex: float
    gamma_flip_qqq: float
    call_wall_qqq: float
    put_wall_qqq: float
    zero_dte_magnet_qqq: float
    pin_score: float
    qqq_price: float
    nq_price: float
    timestamp: datetime

    @property
    def ratio(self) -> float:
        return self.nq_price / self.qqq_price

    @property
    def gamma_flip_nq(self) -> float:
        return self.gamma_flip_qqq * self.ratio

    @property
    def call_wall_nq(self) -> float:
        return self.call_wall_qqq * self.ratio

    @property
    def put_wall_nq(self) -> float:
        return self.put_wall_qqq * self.ratio


@dataclass
class RegimeState:
    regime: Regime = Regime.UNKNOWN
    prev_regime: Regime = Regime.UNKNOWN
    regime_start: Optional[datetime] = None
    confidence: float = 0.0
    stability_minutes: float = 0.0
    transition_count_today: int = 0


class RegimeAlgo:
    """
    Master orchestrator for gamma regime detection and sub-strategy activation.

    Polls FlashAlpha state, classifies regime, manages sub-strategy lifecycle,
    and enforces kill switches.
    """

    WALL_PROXIMITY_POINTS = 15.0
    NEAR_FLIP_POINTS = 10.0
    PIN_SCORE_THRESHOLD = 70.0
    STABILITY_THRESHOLD_MINUTES = 3.0
    MAX_CONSECUTIVE_LOSSES = 3
    MAX_DAILY_LOSS_USD = 1500.0
    DATA_STALENESS_SECONDS = 300

    def __init__(self, sub_strategies: dict, event_calendar, logger):
        self.sub_strategies = sub_strategies  # {"wall_reaction": WallReactionAlgo, ...}
        self.event_calendar = event_calendar
        self.logger = logger
        self.state = RegimeState()
        self.trading_halted = False
        self.consecutive_losses = 0
        self.daily_pnl = 0.0
        self._last_options_update: Optional[datetime] = None

    async def on_options_update(self, options: OptionsState) -> None:
        """
        Called every time FlashAlpha data refreshes (30-60 sec cadence).
        Classifies regime, handles transitions, activates/deactivates sub-strategies.
        """
        if self.trading_halted:
            return

        self._last_options_update = options.timestamp

        new_regime = self._classify_regime(options)
        self._update_stability(new_regime, options.timestamp)

        if new_regime != self.state.regime:
            await self._handle_transition(self.state.regime, new_regime, options)

        self.state.regime = new_regime
        await self._enforce_kill_switches(options)

        if self.state.stability_minutes >= self.STABILITY_THRESHOLD_MINUTES:
            await self._activate_playbook(new_regime, options)

    def _classify_regime(self, options: OptionsState) -> Regime:
        """Classify current regime from options state."""
        # Priority 1: pre-event
        if self.event_calendar.event_within_minutes(30):
            return Regime.G

        # Priority 2: pin
        is_zero_dte = self.event_calendar.is_zero_dte_day()
        after_midday = datetime.now().time() > time(11, 30)
        if options.pin_score >= self.PIN_SCORE_THRESHOLD and is_zero_dte and after_midday:
            return Regime.F

        # Priority 3: gamma sign + price position
        positive_gamma = options.net_gex > 0
        nq = options.nq_price
        flip = options.gamma_flip_nq
        call = options.call_wall_nq
        put = options.put_wall_nq

        at_call = abs(nq - call) < self.WALL_PROXIMITY_POINTS
        at_put = abs(nq - put) < self.WALL_PROXIMITY_POINTS
        above_flip = nq > flip
        below_flip = nq < flip

        if positive_gamma:
            if at_call:
                return Regime.B
            if at_put:
                return Regime.C
            return Regime.A
        else:
            if above_flip:
                return Regime.D
            return Regime.E

    def _update_stability(self, new_regime: Regime, now: datetime) -> None:
        """Update stability tracking when regime is confirmed or changes."""
        if new_regime != self.state.regime:
            self.state.regime_start = now
            self.state.stability_minutes = 0.0
            self.state.confidence = 0.5
        else:
            if self.state.regime_start:
                elapsed = (now - self.state.regime_start).total_seconds() / 60
                self.state.stability_minutes = elapsed
                if elapsed < 5:
                    self.state.confidence = 0.5
                elif elapsed < 15:
                    self.state.confidence = 0.75
                else:
                    self.state.confidence = 1.0

    async def _handle_transition(
        self, from_regime: Regime, to_regime: Regime, options: OptionsState
    ) -> None:
        """Handle regime transition: close positions, deactivate old, prepare new."""
        self.logger.info(f"Regime transition: {from_regime} → {to_regime}")
        self.state.transition_count_today += 1

        # Immediate close on transition to G
        if to_regime == Regime.G:
            await self._close_all_positions("regime_transition_to_G")
            await self._deactivate_all("regime_G")
            return

        # Close positions from old regime (allow 2 bars = ~10 seconds)
        await self._close_positions_from_regime(from_regime, grace_seconds=10)

        # Deactivate old sub-strategies
        old_strategies = self._get_strategies_for_regime(from_regime)
        for name in old_strategies:
            if name in self.sub_strategies:
                await self.sub_strategies[name].deactivate("regime_transition")

    async def _activate_playbook(self, regime: Regime, options: OptionsState) -> None:
        """Activate sub-strategies appropriate for the current regime."""
        strategies = self._get_strategies_for_regime(regime)
        conviction = self.state.confidence

        for name in strategies:
            if name in self.sub_strategies:
                await self.sub_strategies[name].activate(regime, conviction, options)

    def _get_strategies_for_regime(self, regime: Regime) -> list[str]:
        """Return list of sub-strategy names for a given regime."""
        playbook = {
            Regime.A: ["wall_reaction", "vol_surface"],
            Regime.B: ["wall_reaction"],
            Regime.C: ["wall_reaction"],
            Regime.D: ["wall_reaction", "vol_surface"],
            Regime.E: ["wall_reaction", "vol_surface"],
            Regime.F: ["zero_dte"],
            Regime.G: [],
            Regime.UNKNOWN: [],
        }
        return playbook.get(regime, [])

    async def _enforce_kill_switches(self, options: OptionsState) -> None:
        """Check all kill switch conditions. Halt trading if any trigger."""
        # Consecutive losses
        if self.consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
            await self._halt_trading("consecutive_loss_limit")
            return

        # Daily loss limit
        if self.daily_pnl <= -self.MAX_DAILY_LOSS_USD:
            await self._halt_trading("daily_loss_limit")
            return

        # Data staleness
        if self._last_options_update:
            staleness = (datetime.now() - self._last_options_update).total_seconds()
            if staleness > self.DATA_STALENESS_SECONDS:
                await self._deactivate_all("stale_data")

    async def _halt_trading(self, reason: str) -> None:
        self.trading_halted = True
        await self._close_all_positions(reason)
        await self._deactivate_all(reason)
        self.logger.critical(f"Trading halted: {reason}")

    async def _close_all_positions(self, reason: str) -> None:
        """Signal all sub-strategies to close their positions."""
        for name, strategy in self.sub_strategies.items():
            await strategy.close_all(reason)

    async def _close_positions_from_regime(self, regime: Regime, grace_seconds: int) -> None:
        """Close positions opened under a specific regime."""
        strategies = self._get_strategies_for_regime(regime)
        for name in strategies:
            if name in self.sub_strategies:
                await self.sub_strategies[name].close_all("regime_change", grace_seconds)

    async def _deactivate_all(self, reason: str) -> None:
        for name, strategy in self.sub_strategies.items():
            await strategy.deactivate(reason)

    def on_trade_closed(self, pnl_usd: float) -> None:
        """Called by execution layer when a trade closes. Updates loss tracking."""
        self.daily_pnl += pnl_usd
        if pnl_usd < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def reset_daily(self) -> None:
        """Call at session start to reset daily counters."""
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.trading_halted = False
        self.state = RegimeState()
```

---

## Configuration

```python
REGIME_ALGO_CONFIG = {
    "wall_proximity_points": 15.0,
    "near_flip_points": 10.0,
    "pin_score_threshold": 70.0,
    "stability_threshold_minutes": 3.0,
    "max_consecutive_losses": 3,
    "max_daily_loss_usd": 1500.0,
    "data_staleness_seconds": 300,
    "flashalpha_poll_interval_seconds": 45,
    "transition_conviction_bonus": 15,       # added to bias score on flip cross
    "transition_bonus_decay_minutes": 30,
}
```

---

## Logging and Observability

Every regime change emits a structured log event:

```python
{
    "event": "regime_transition",
    "from": "A",
    "to": "D",
    "nq_price": 21340.25,
    "gamma_flip_nq": 21335.00,
    "net_gex": -2.3e9,
    "stability_before": 47.2,
    "timestamp": "2026-05-25T10:23:41Z"
}
```

Every sub-strategy activation/deactivation emits:

```python
{
    "event": "strategy_activated",
    "strategy": "wall_reaction",
    "regime": "C",
    "conviction": 0.85,
    "timestamp": "2026-05-25T10:26:55Z"
}
```

These events feed the DEEP6 session replay dashboard for post-session review.
