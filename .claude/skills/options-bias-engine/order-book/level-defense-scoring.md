# Order Book Signal OB-1: Level Defense Score

## Overview

The Level Defense Score quantifies how well a specific price level is being defended in the NQ order book. It answers the question: is someone actually holding this level, or is the GEX structure just a theoretical construct with no real order book support?

The score runs from 0 to 100. A score of 80+ means the level is a fortress — heavily defended, with icebergs, reloading, and absorption. A score below 20 means the level is paper — GEX says it's important but the book says nobody cares.

This signal is computed for every significant options level: call wall, put wall, gamma flip, expected move boundaries, and major OI clusters. It's updated every 5-10 seconds, or on every significant order event at the level.

---

## What "Defense" Means

Defense is not the presence of resting orders. Defense is the BEHAVIOR of those orders when price approaches.

A defended level has three characteristics:
1. Resting orders absorb incoming market orders without retreating
2. When orders are filled, new orders appear to replace them (reloading)
3. Price tries to move through the level and FAILS — it bounces back

An undefended level has the opposite characteristics:
1. Resting orders are thin or absent
2. When orders are filled, they're not replaced
3. Price moves through the level without resistance

The defense score measures these behaviors quantitatively.

---

## Scoring Algorithm

The defense score is computed from five components, each contributing to the 0-100 total.

### Component 1: Resting Order Density (0-30 points)

Count all resting limit orders within ±5 ticks of the level. One tick = 0.25 NQ points, so ±5 ticks = ±1.25 NQ points.

```python
def resting_density_score(level: float, book: OrderBook) -> float:
    tick = 0.25
    window = 5 * tick  # 1.25 NQ points
    
    total_weighted_contracts = 0
    for price, orders in book.get_levels_in_range(level - window, level + window):
        for order in orders:
            size = order.quantity
            if size > 100:
                weight = 5.0
            elif size > 50:
                weight = 3.0
            elif size > 20:
                weight = 1.5
            else:
                weight = 1.0
            total_weighted_contracts += size * weight
    
    # Scale: 0 contracts = 0 pts, 500+ weighted contracts = 30 pts
    return min(30, total_weighted_contracts / 500 * 30)
```

**Size weighting rationale:** Large orders (50+ contracts) are more significant than small orders. A single 100-contract resting bid is more meaningful than twenty 5-contract bids. The 5x weight for 100+ contract orders reflects this.

### Component 2: Reload Rate (0-25 points)

After a resting order at the level is partially or fully filled, does a new order appear at the same price within 60 seconds? Count reloads in the last 60 seconds.

```python
def reload_rate_score(level: float, fill_events: list, order_events: list) -> float:
    tick = 0.25
    window = 2 * tick  # 0.50 NQ points (tight window for reload detection)
    now = time.time()
    lookback = 60  # seconds
    
    fills_at_level = [f for f in fill_events 
                      if abs(f.price - level) <= window 
                      and now - f.timestamp <= lookback]
    
    reloads = 0
    for fill in fills_at_level:
        # Check if a new order appeared at the same price within 5 seconds of the fill
        subsequent_orders = [o for o in order_events
                             if abs(o.price - fill.price) <= window
                             and 0 < o.timestamp - fill.timestamp <= 5.0
                             and o.side == fill.side]  # same side as the filled order
        if subsequent_orders:
            reloads += 1
    
    # Scale: 0 reloads = 0 pts, 5+ reloads = 25 pts
    return min(25, reloads * 5)
```

**Why 60 seconds:** Reloads that happen more than 60 seconds after a fill are less likely to be intentional defense and more likely to be coincidental order placement. The 60-second window captures active, deliberate defense.

**Why 5 reloads = max score:** Five reloads in 60 seconds means the level is being actively replenished every 12 seconds on average. This is aggressive defense. More than 5 reloads is possible but doesn't increase the score — the maximum is already indicating a fortress.

### Component 3: Iceberg Presence (0-30 points)

If an iceberg order is detected at the level (per iceberg-detection.md), add 30 points. This is a binary component — either there's an iceberg or there isn't.

```python
def iceberg_score(level: float, iceberg_registry: IcebergRegistry) -> float:
    tick = 0.25
    window = 3 * tick  # 0.75 NQ points
    
    active_icebergs = iceberg_registry.get_active_icebergs_near(level, window)
    if not active_icebergs:
        return 0
    
    # Bonus for duration: iceberg active > 5 min = full 30 pts
    # Iceberg active < 1 min = 15 pts (may be a flash)
    best_iceberg = max(active_icebergs, key=lambda i: i.duration_seconds)
    duration_factor = min(1.0, best_iceberg.duration_seconds / 300)  # 300s = 5 min
    return 30 * max(0.5, duration_factor)  # minimum 15 pts if iceberg present
```

**Why 30 points:** An iceberg at a GEX level is the single highest-conviction individual signal in the system. It deserves the largest single component weight. A level with an iceberg and nothing else scores 15-30 out of 100 — moderate defense. A level with an iceberg AND reloading AND density scores 85-100 — fortress.

### Component 4: Absorption Rate (0-10 points)

Absorption rate measures how much volume has traded at the level relative to how much price has moved. High absorption = lots of volume, little price movement = someone is absorbing the flow.

```python
def absorption_score(level: float, trades: list, price_history: list) -> float:
    tick = 0.25
    window = 5 * tick
    now = time.time()
    lookback = 120  # 2 minutes
    
    # Volume traded at level in last 2 minutes
    volume_at_level = sum(t.quantity for t in trades
                          if abs(t.price - level) <= window
                          and now - t.timestamp <= lookback)
    
    # Price movement at level in last 2 minutes
    prices_at_level = [p.price for p in price_history
                       if abs(p.price - level) <= window
                       and now - p.timestamp <= lookback]
    
    if not prices_at_level or volume_at_level == 0:
        return 0
    
    price_range = max(prices_at_level) - min(prices_at_level)
    
    # Absorption ratio: volume per tick of price movement
    # High ratio = lots of volume, little movement = absorption
    if price_range < tick:
        price_range = tick  # avoid division by zero
    
    absorption_ratio = volume_at_level / (price_range / tick)
    
    # Scale: 0 = 0 pts, 1000+ contracts per tick = 10 pts
    return min(10, absorption_ratio / 100)
```

**Interpretation:** If 500 contracts traded at the level and price moved 2 ticks (0.50 pts), the absorption ratio is 250 contracts/tick. If 500 contracts traded and price moved 10 ticks (2.50 pts), the ratio is 50 contracts/tick. The first case shows much stronger absorption.

### Component 5: Time Persistence (0-5 points)

Orders that have been resting at the level for longer periods are more reliable than flash orders. Persistent orders indicate a committed participant, not a spoofer testing the market.

```python
def persistence_score(level: float, book: OrderBook) -> float:
    tick = 0.25
    window = 5 * tick
    now = time.time()
    
    orders_at_level = book.get_orders_in_range(level - window, level + window)
    if not orders_at_level:
        return 0
    
    # Find the oldest order at the level
    oldest_order_age = max(now - o.placed_timestamp for o in orders_at_level)
    
    # +1 pt per 30 seconds of persistence, max 5 pts (150 seconds = 2.5 min)
    return min(5, oldest_order_age / 30)
```

**Why persistence matters:** Spoof orders are typically placed and cancelled within seconds. An order that has been resting for 2+ minutes is almost certainly not a spoof — it's a genuine participant willing to wait for price to come to them.

---

## Total Score Computation

```python
def compute_defense_score(level: float, book: OrderBook, 
                           fill_events: list, order_events: list,
                           trades: list, price_history: list,
                           iceberg_registry: IcebergRegistry) -> float:
    
    density = resting_density_score(level, book)
    reload = reload_rate_score(level, fill_events, order_events)
    iceberg = iceberg_score(level, iceberg_registry)
    absorption = absorption_score(level, trades, price_history)
    persistence = persistence_score(level, book)
    
    total = density + reload + iceberg + absorption + persistence
    return min(100, total)  # cap at 100
```

Maximum possible score breakdown:
- Resting density: 30 pts
- Reload rate: 25 pts
- Iceberg presence: 30 pts
- Absorption rate: 10 pts
- Time persistence: 5 pts
- **Total: 100 pts**

---

## Score Interpretation

### 80-100: FORTRESS

The level is very heavily defended. Multiple components are contributing: high density, active reloading, iceberg present, strong absorption. This level will not break easily.

**Trading implication:** Trade the bounce with high conviction. The defending participant has demonstrated willingness to absorb significant volume. The stop can be placed just beyond the level (5-8 ticks) because the defense is strong enough to make a break unlikely.

**Example:** Put wall at 20,850 with defense score 87. Iceberg bids active, 4 reloads in last 60 seconds, 340 contracts absorbed with price moving only 1 tick. This is a fortress. Long at 20,852 with stop at 20,825.

### 60-79: STRONG

The level has solid support. Not a fortress, but clearly defended. One or two components are strong, others are moderate.

**Trading implication:** Lean toward the bounce. Wait for additional confirmation from flow or dark pool before entering. The stop should be slightly wider (8-12 ticks) to account for the possibility that the defense weakens.

**Example:** Call wall at 21,200 with defense score 68. High density (22 pts), moderate reload (10 pts), no iceberg (0 pts), moderate absorption (6 pts), good persistence (4 pts). The wall is defended but not a fortress. Short at 21,198 with stop at 21,215.

### 40-59: MODERATE

Some defense is present but not conclusive. The level may hold or break depending on the intensity of the attack.

**Trading implication:** Wait for additional confirmation from flow and dark pool before trading the bounce. If flow is also bullish (for a put wall) and dark pool is buying, the combined signal may be sufficient. If flow is neutral or bearish, the moderate defense is not enough to trade against.

**Example:** Gamma flip at 20,840 with defense score 52. Moderate density (15 pts), some reloading (10 pts), no iceberg (0 pts), moderate absorption (5 pts), some persistence (3 pts). The flip is being defended but not aggressively. Wait for iceberg or stronger reload before trading the flip defense.

### 20-39: THIN

Orders are present but sparse. No reloading. No icebergs. The level may be defended by passive market makers who will pull their orders if price approaches aggressively.

**Trading implication:** Do not trade the bounce based on defense alone. The level may hold due to GEX mechanics (dealer hedging) even without strong book defense, but the risk is higher. Require 4/5 or 5/5 conviction from the other dimensions before trading.

**Example:** Expected move high at 21,150 with defense score 28. Low density (8 pts), no reloading (0 pts), no iceberg (0 pts), low absorption (3 pts), some persistence (2 pts). The EM boundary has some passive orders but no active defense. The statistical boundary may hold, but the book isn't confirming it.

### 0-19: PAPER

Virtually nothing defending the level. GEX says it's a level but the book says nobody cares.

**Trading implication:** Ignore the level for bounce trades. If the level is a call wall or put wall with a paper defense score, consider trading the BREAK instead of the bounce. A wall with no book defense is a wall that will break on moderate pressure.

**Example:** Secondary put cluster at 20,700 with defense score 8. Minimal density (3 pts), no reloading (0 pts), no iceberg (0 pts), minimal absorption (1 pt), no persistence (0 pts). This level exists in the GEX data but has no real order book presence. It will not provide meaningful support.

---

## Defense Score at Specific Options Levels

### At the call wall

**High defense score (60+):** The call wall is being actively defended from above. Sellers are holding the ceiling. Trade the short bounce with confidence. The wall will hold.

**Low defense score (<40):** The call wall has no real book defense. The GEX mechanics (dealer selling above the wall) may still create resistance, but the book isn't confirming it. If flow is also bullish (call sweeps, net call premium), the wall may break. Prepare for Setup 2 (Wall Break).

**Defense score transition (falling from 60+ to below 40):** The wall is being depleted. Defenders are being overwhelmed. This is the early warning signal for a wall break. Watch for depletion rate to accelerate (see book-depletion.md).

### At the put wall

**High defense score (60+):** The put wall is a defended floor. Buyers are holding the level. Trade the long bounce with confidence. This is Setup 1 (Wall Bounce) in Regime C — the highest win-rate trade in the system.

**Low defense score (<40):** The put wall has no real book defense. The GEX mechanics may still create some support, but the book isn't confirming it. If flow is also bearish (put sweeps, net put premium), the wall may break. Prepare for Regime E cascade.

**Defense score transition (falling from 60+ to below 40):** The floor is being depleted. This is the early warning signal for a put wall break. Tighten stops on any long positions.

### At the gamma flip

**High defense on bid side:** Someone is defending the positive gamma regime. They're buying at the flip level to prevent price from crossing into negative gamma. Very bullish — the regime is being actively maintained.

**High defense on ask side:** Someone is attacking the positive regime from above, trying to force price below the flip into negative gamma. Very bearish — the regime is under attack.

**Balanced defense (both sides):** The flip is a contested level. Neither bulls nor bears have clear control. Wait for one side to establish dominance before trading.

### At the expected move boundaries

**High defense score:** The statistical boundary is being respected. Options market makers are defending their positions at the EM level. The EM is likely to hold as a boundary for the day.

**Low defense score:** The EM boundary has no book support. On high-volatility days, the EM can be exceeded significantly. Do not trade the EM fade (Setup 8) if the defense score is below 40.

---

## Score Decay

Defense scores decay over time if no new defending activity occurs. This prevents stale scores from misleading the system.

**Decay rate:** -5 points per minute of inactivity. "Inactivity" means no new orders placed at the level, no reloads, no fills.

```python
def apply_decay(score: float, last_activity_timestamp: float) -> float:
    now = time.time()
    minutes_inactive = (now - last_activity_timestamp) / 60
    decay = minutes_inactive * 5
    return max(0, score - decay)
```

**Practical implication:** A level that was a fortress (score 87) 10 minutes ago with no subsequent activity now has a score of 37 (thin). The defense may have been withdrawn. Re-evaluate before trading.

**Why decay matters:** Defenders don't hold levels forever. They place orders, absorb some volume, and then pull their orders when the attack subsides or when they've achieved their objective. A defense score computed 10 minutes ago may not reflect the current state of the book.

---

## Update Frequency

Recompute the defense score every 5-10 seconds during normal market conditions. On every significant order event at the level (new large order, fill, cancel), recompute immediately.

The 5-second update interval is a balance between computational cost and freshness. The Rithmic MBO feed generates 1,000+ callbacks per second. Computing the full defense score on every callback would be computationally expensive. Instead, maintain running tallies of the components and recompute the total score on a timer.

```python
class DefenseScoreEngine:
    def __init__(self, update_interval: float = 5.0):
        self.update_interval = update_interval
        self.scores: dict[float, float] = {}  # level -> score
        self.last_update: dict[float, float] = {}  # level -> timestamp
        self.last_activity: dict[float, float] = {}  # level -> last activity timestamp
    
    def on_order_event(self, event: OrderEvent):
        # Update running tallies
        level = self.snap_to_level(event.price)
        if level:
            self.last_activity[level] = event.timestamp
            # Trigger immediate recompute if significant event
            if event.quantity > 50 or event.type == 'FILL':
                self.recompute(level)
    
    def get_score(self, level: float) -> float:
        raw_score = self.scores.get(level, 0)
        last_activity = self.last_activity.get(level, time.time())
        return apply_decay(raw_score, last_activity)
```

---

## Integration with the Bias Engine

The defense score feeds into the DOM component of the directional bias score. The mapping:

| Defense Score | DOM Component Contribution |
|---------------|---------------------------|
| 80-100 | +40 to +50 (strong bullish at put wall, strong bearish at call wall) |
| 60-79 | +25 to +39 |
| 40-59 | +10 to +24 |
| 20-39 | -10 to +9 (neutral to slight lean) |
| 0-19 | -20 to -11 (paper defense = slight negative signal) |

The sign of the contribution depends on which level is being defended and the direction of the trade:
- High defense at put wall → positive DOM contribution (bullish)
- High defense at call wall → negative DOM contribution (bearish)
- High defense at gamma flip (bid side) → positive DOM contribution
- High defense at gamma flip (ask side) → negative DOM contribution

A paper defense score at a key level is itself a signal — it means the GEX structure is not being reinforced by the book. This is a mild bearish signal for put wall trades and a mild bullish signal for call wall trades (the ceiling isn't being defended, so it may break).
