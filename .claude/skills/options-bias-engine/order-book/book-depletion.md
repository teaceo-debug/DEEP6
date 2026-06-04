# Order Book Signal OB-5: Book Depletion Velocity

## Overview

Book Depletion Velocity measures how fast resting orders at a specific price level are being consumed by incoming market orders. It's measured in contracts per second. When price approaches a GEX wall, the speed at which defending orders are consumed — and whether those orders are being replaced — tells you whether the wall will hold or break.

This signal is the quantitative expression of the DEEP6 system's core thesis: absorption and exhaustion are the highest-alpha reversal signals in order flow. Depletion velocity is how you measure absorption and exhaustion in real time.

---

## Why Depletion Velocity Matters at Options Levels

A GEX wall (call wall or put wall) is a theoretical construct derived from options open interest. It tells you WHERE dealers have gamma exposure. It does not tell you whether that exposure is being actively defended in the order book.

Depletion velocity bridges this gap. When price approaches a GEX wall:
- If orders are being consumed slowly and replaced quickly → the wall is being defended (absorption)
- If orders are being consumed rapidly and NOT replaced → the wall is being overwhelmed (break imminent)
- If orders are being consumed slowly and NOT replaced → the wall is thin and untested

The depletion pattern is the real-time verdict on whether the GEX structure is real or theoretical.

---

## The Three Depletion Patterns

### Pattern 1: SLOW DEPLETION

**Definition:** Depletion rate < 50 contracts/second at the level. Orders last > 30 seconds before reload is needed.

**What it looks like in the MBO feed:**
- Occasional fills at the level (1-5 per minute)
- Each fill is small (5-20 contracts)
- The resting volume at the level changes slowly
- No urgency from either side

**Interpretation:** Normal trading around the level. Neither attackers nor defenders are aggressive. The level is being TESTED but not attacked. Price is probing the level without conviction.

**Trading implication:** Wait for escalation. Slow depletion is not a signal — it's a neutral state. The level may hold or break, but the current data doesn't tell you which. Wait for the depletion pattern to shift to fast depletion before acting.

**Example:** Put wall at 20,850. Depletion rate: 12 contracts/second. Orders resting for 45 seconds before being filled. No urgency. Price is oscillating around 20,852-20,858. This is a probe, not an attack.

### Pattern 2: FAST DEPLETION + RELOAD (ABSORPTION)

**Definition:** Depletion rate > 100 contracts/second consumed AND new orders keep appearing at the level within 5 seconds of each fill.

**What it looks like in the MBO feed:**
- Rapid fills at the level (10-50+ per minute)
- Each fill is larger (20-100+ contracts)
- The resting volume at the level drops rapidly after each fill
- BUT new orders appear within seconds, restoring the volume
- Net result: lots of volume traded, price barely moves

**Interpretation:** ABSORPTION. Massive volume is trading at the level but price is NOT moving through. Someone with effectively unlimited size (relative to the attackers) is defending the level. Every wave of selling (at a put wall) or buying (at a call wall) is being absorbed by the defender.

This is the core DEEP6 thesis applied to options levels. The absorption pattern is the highest conviction signal for a wall bounce trade.

**Trading implication:** HIGHEST CONVICTION for wall bounce trade. The attack is being absorbed. When the attack exhausts (depletion rate drops back to slow), the price will reverse away from the level. The exhaustion of the attack is the entry signal.

**Example:** Put wall at 20,850. Depletion rate: 180 contracts/second. Orders being filled rapidly. But reload rate: 160 contracts/second (new orders appearing almost as fast as they're consumed). Net volume at level: stable at 200-250 contracts. Price: stuck at 20,850-20,852 despite heavy selling. This is absorption. The put wall is holding.

### Pattern 3: FAST DEPLETION + NO RELOAD (BREAK IMMINENT)

**Definition:** Depletion rate > 100 contracts/second consumed AND orders are NOT being replaced (reload rate < 30% of depletion rate).

**What it looks like in the MBO feed:**
- Rapid fills at the level (10-50+ per minute)
- Each fill is larger (20-100+ contracts)
- The resting volume at the level drops rapidly after each fill
- New orders do NOT appear to replace the consumed volume
- Net result: the level is being depleted, volume is disappearing

**Interpretation:** BREAK IMMINENT. The defenders are being overwhelmed. Each wave of selling/buying eats more depth and it doesn't come back. The level will break within seconds to minutes.

**Trading implication:** Prepare for wall break trade. When the last defending order is consumed, price will accelerate through the void behind it. The break is often violent because:
1. The defenders are gone (no more absorption)
2. The attackers are still aggressive (they've been building momentum)
3. The GEX mechanics flip (once the wall breaks, dealer hedging amplifies the move)

**Example:** Put wall at 20,850. Depletion rate: 220 contracts/second. Orders being filled rapidly. Reload rate: 15 contracts/second (almost nothing coming back). Volume at level: dropping from 300 → 200 → 100 → 50 → 0. Price: 20,850 → 20,848 → 20,845 → 20,840 (gamma flip). The wall is breaking.

---

## Measurement Algorithm

### Core depletion calculation

```python
class DepletionVelocityEngine:
    """
    Measures book depletion velocity at specific price levels.
    
    Tracks:
    - orders_consumed: contracts filled or cancelled at the level
    - orders_added: new contracts placed at the level
    - net_depletion: consumed - added (positive = depleting)
    - depletion_rate: contracts per second consumed
    - reload_ratio: added / consumed (1.0 = perfect reload, 0.0 = no reload)
    """
    
    MEASUREMENT_WINDOW_MS = 5000   # 5-second rolling window
    FAST_DEPLETION_THRESHOLD = 100  # contracts/second
    SLOW_DEPLETION_THRESHOLD = 50   # contracts/second
    RELOAD_THRESHOLD = 0.8          # 80% reload = absorption
    NO_RELOAD_THRESHOLD = 0.3       # 30% reload = break imminent
    PRICE_WINDOW_TICKS = 5          # ±5 ticks = ±1.25 NQ points
    
    def __init__(self):
        self.events: dict = {}  # level -> deque of (timestamp, type, size)
    
    def on_order_event(self, timestamp: float, price: float, 
                        event_type: str, size: int, level: float):
        """
        event_type: 'FILL', 'CANCEL', 'ADD'
        level: The GEX level being monitored (may differ from price by up to PRICE_WINDOW_TICKS)
        """
        tick = 0.25
        if abs(price - level) > self.PRICE_WINDOW_TICKS * tick:
            return  # Outside the monitoring window
        
        if level not in self.events:
            self.events[level] = deque()
        
        self.events[level].append((timestamp, event_type, size))
        self._prune(level, timestamp)
    
    def _prune(self, level: float, now: float):
        cutoff = now - self.MEASUREMENT_WINDOW_MS / 1000
        while self.events[level] and self.events[level][0][0] < cutoff:
            self.events[level].popleft()
    
    def compute(self, level: float) -> dict:
        """
        Compute depletion metrics for a specific level.
        Returns a dict with all metrics.
        """
        if level not in self.events or not self.events[level]:
            return self._empty_result()
        
        now = time.time()
        window_start = now - self.MEASUREMENT_WINDOW_MS / 1000
        
        consumed = 0  # fills + cancels (orders leaving the book)
        added = 0     # new orders placed
        
        for ts, event_type, size in self.events[level]:
            if ts >= window_start:
                if event_type in ('FILL', 'CANCEL'):
                    consumed += size
                elif event_type == 'ADD':
                    added += size
        
        window_seconds = self.MEASUREMENT_WINDOW_MS / 1000
        depletion_rate = consumed / window_seconds  # contracts/second
        reload_ratio = added / consumed if consumed > 0 else 1.0
        net_depletion = consumed - added
        
        pattern = self._classify_pattern(depletion_rate, reload_ratio)
        
        return {
            'level': level,
            'depletion_rate_per_sec': depletion_rate,
            'reload_ratio': reload_ratio,
            'net_depletion': net_depletion,
            'consumed': consumed,
            'added': added,
            'pattern': pattern,
            'window_seconds': window_seconds
        }
    
    def _classify_pattern(self, depletion_rate: float, 
                           reload_ratio: float) -> str:
        if depletion_rate < self.SLOW_DEPLETION_THRESHOLD:
            return 'SLOW_DEPLETION'
        elif depletion_rate >= self.FAST_DEPLETION_THRESHOLD:
            if reload_ratio >= self.RELOAD_THRESHOLD:
                return 'ABSORPTION'
            elif reload_ratio <= self.NO_RELOAD_THRESHOLD:
                return 'BREAK_IMMINENT'
            else:
                return 'CONTESTED'  # Fast depletion, partial reload
        else:
            return 'MODERATE_DEPLETION'  # 50-100 contracts/second
    
    def _empty_result(self) -> dict:
        return {
            'depletion_rate_per_sec': 0,
            'reload_ratio': 1.0,
            'net_depletion': 0,
            'consumed': 0,
            'added': 0,
            'pattern': 'SLOW_DEPLETION',
            'window_seconds': self.MEASUREMENT_WINDOW_MS / 1000
        }
```

### Sustained pattern detection

A single 5-second window can be noisy. Require the pattern to be sustained for at least 5 consecutive seconds before acting on it.

```python
class SustainedPatternDetector:
    SUSTAINED_THRESHOLD_SECONDS = 5
    
    def __init__(self):
        self.pattern_history: dict = {}  # level -> deque of (timestamp, pattern)
    
    def record_pattern(self, level: float, timestamp: float, pattern: str):
        if level not in self.pattern_history:
            self.pattern_history[level] = deque()
        self.pattern_history[level].append((timestamp, pattern))
        
        # Keep only last 30 seconds
        cutoff = timestamp - 30
        while (self.pattern_history[level] and 
               self.pattern_history[level][0][0] < cutoff):
            self.pattern_history[level].popleft()
    
    def get_sustained_pattern(self, level: float) -> str:
        """
        Returns the pattern if it has been sustained for SUSTAINED_THRESHOLD_SECONDS.
        Returns 'UNSTABLE' if the pattern is changing rapidly.
        """
        if level not in self.pattern_history:
            return 'UNKNOWN'
        
        history = list(self.pattern_history[level])
        if not history:
            return 'UNKNOWN'
        
        now = time.time()
        recent = [(ts, p) for ts, p in history 
                  if now - ts <= self.SUSTAINED_THRESHOLD_SECONDS]
        
        if not recent:
            return 'UNKNOWN'
        
        # Check if all recent patterns are the same
        patterns = [p for _, p in recent]
        if len(set(patterns)) == 1:
            return patterns[0]  # Sustained pattern
        else:
            return 'UNSTABLE'  # Pattern is changing
```

---

## Depletion at Specific Options Levels

### Call wall depletion

**Fast depletion + no reload at call wall:**
The call wall is being overwhelmed. Buyers are hitting the ask at the call wall faster than sellers can reload. The ceiling is breaking.

Signal: BREAK UP. Go long on the first pullback to the broken wall (which becomes support). This is Setup 2 (Wall Break) long.

Entry timing: Enter when depletion rate drops from fast to slow (the attack has succeeded, price is through the wall, and the momentum is established). Do not enter during the fast depletion phase — the move is already happening.

**Fast depletion + reload at call wall:**
The call wall is absorbing buying pressure. Sellers are defending the ceiling. The wall holds.

Signal: ABSORPTION. Go short. The buying attack is being absorbed. When the attack exhausts (depletion rate drops to slow), enter short.

Entry timing: Enter when the depletion rate drops from fast to slow AND the reload ratio remains high. The attack has exhausted, the defense won.

### Put wall depletion

**Fast depletion + no reload at put wall:**
The put wall is being overwhelmed. Sellers are hitting the bid at the put wall faster than buyers can reload. The floor is breaking.

Signal: BREAK DOWN. Go short. Regime E cascade begins. This is the most dangerous scenario in the system — once the put wall breaks in positive gamma, the regime flips to negative gamma and dealer hedging amplifies the selling.

Entry timing: Enter short when the last defending order is consumed and price accelerates below the put wall. The break is often violent.

**Fast depletion + reload at put wall:**
The put wall is absorbing selling pressure. Buyers are defending the floor. The wall holds.

Signal: ABSORPTION. Go long. This is Setup 1 (Wall Bounce) with the highest possible DOM confirmation. The selling attack is being absorbed. When the attack exhausts, enter long.

Entry timing: Enter when the depletion rate drops from fast to slow AND the reload ratio remains high. The attack has exhausted, the defense won. This is the ENTRY SIGNAL.

---

## The Exhaustion Signal

The exhaustion signal is the most important output of the depletion velocity engine. It marks the transition from fast depletion + reload (absorption) to slow depletion (attack exhausted).

```python
class ExhaustionDetector:
    """
    Detects when an attack on a GEX level has been absorbed and exhausted.
    
    The exhaustion signal is the entry trigger for the bounce trade.
    """
    
    def __init__(self):
        self.was_absorbing: dict = {}  # level -> bool
        self.exhaustion_events: list = []
    
    def update(self, level: float, timestamp: float, 
               pattern: str, sustained_pattern: str):
        
        was_absorbing = self.was_absorbing.get(level, False)
        is_absorbing = sustained_pattern == 'ABSORPTION'
        is_slow = sustained_pattern == 'SLOW_DEPLETION'
        
        if was_absorbing and is_slow:
            # Transition from absorption to slow depletion
            # The attack has been absorbed and exhausted
            self.exhaustion_events.append({
                'level': level,
                'timestamp': timestamp,
                'type': 'ATTACK_EXHAUSTED'
            })
        
        self.was_absorbing[level] = is_absorbing
    
    def get_recent_exhaustion(self, level: float, 
                               max_age_seconds: float = 30) -> dict:
        """
        Returns the most recent exhaustion event at a level,
        if it occurred within max_age_seconds.
        """
        now = time.time()
        recent = [e for e in self.exhaustion_events
                  if e['level'] == level 
                  and now - e['timestamp'] <= max_age_seconds]
        
        if recent:
            return max(recent, key=lambda e: e['timestamp'])
        return None
```

### Exhaustion entry protocol

When an exhaustion event is detected at a GEX level:

1. **Confirm the level held.** Price should still be at or near the level (not through it). If price has already moved 10+ points away from the level, the exhaustion signal is stale.

2. **Confirm the defense won.** The reload ratio should have been > 0.8 during the absorption phase. If the reload ratio was only 0.5-0.7, the defense was partial and the level may still break.

3. **Enter in the direction away from the level.** At a put wall: enter long. At a call wall: enter short.

4. **Stop just beyond the level.** At a put wall: stop 5-8 ticks below the wall. At a call wall: stop 5-8 ticks above the wall. The exhaustion signal means the attack is over, but the level could still break on a second attack.

5. **Target the next significant level.** At a put wall: target HVL or call wall. At a call wall: target HVL or put wall.

---

## Depletion Rate Calibration

The thresholds (100 contracts/second for fast, 50 for slow) are calibrated for NQ futures during normal market hours. They may need adjustment for:

**Low-volume periods (midday, pre-market):**
During midday (11:30 AM - 1:30 PM ET), overall volume drops significantly. A depletion rate of 50 contracts/second during midday may be equivalent to 100 contracts/second during the morning session. Consider scaling thresholds by the current volume relative to the session average.

```python
def adjust_thresholds_for_volume(base_fast: float, base_slow: float,
                                  current_volume_rate: float,
                                  session_avg_volume_rate: float) -> tuple:
    """
    Scale thresholds based on current volume relative to session average.
    """
    volume_ratio = current_volume_rate / session_avg_volume_rate
    adjusted_fast = base_fast * volume_ratio
    adjusted_slow = base_slow * volume_ratio
    return adjusted_fast, adjusted_slow
```

**High-volatility periods (post-FOMC, post-CPI):**
During high-volatility periods, volume spikes dramatically. A depletion rate of 100 contracts/second may be normal background noise. Scale thresholds up by 2-3x during these periods.

**Expiration days (0DTE):**
On expiration days, volume at key strikes is much higher than normal. The thresholds should be scaled up by 1.5-2x to avoid false signals from the elevated baseline volume.

---

## Integration with the Bias Engine

Book depletion velocity contributes to the DOM component of the directional bias score.

| Pattern | DOM Contribution |
|---------|-----------------|
| SLOW_DEPLETION | 0 (neutral, no depletion signal) |
| MODERATE_DEPLETION | ±5 (slight lean based on reload ratio) |
| ABSORPTION | ±30 (strong signal, direction based on level and side) |
| BREAK_IMMINENT | ±25 (opposite direction — break signal) |
| CONTESTED | ±10 (partial signal) |
| ATTACK_EXHAUSTED (exhaustion event) | ±40 (strongest depletion signal — entry trigger) |

Sign convention:
- Absorption at put wall → +30 (bullish)
- Break imminent at put wall → -25 (bearish)
- Absorption at call wall → -30 (bearish)
- Break imminent at call wall → +25 (bullish)
- Attack exhausted at put wall → +40 (bullish entry signal)
- Attack exhausted at call wall → -40 (bearish entry signal)

The depletion signal has a 5% weight in the DOM component (per depth-asymmetry.md weight table). However, the ATTACK_EXHAUSTED event is treated as an event trigger that produces an immediate output cycle (per output-format.md event triggers), regardless of the scheduled cycle timing.
