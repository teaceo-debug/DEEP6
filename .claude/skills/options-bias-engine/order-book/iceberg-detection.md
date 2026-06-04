# Order Book Signal OB-4: Iceberg Detection at Options Levels

## Overview

An iceberg order is a large order that shows only a small visible portion to the market. As the visible portion gets filled, the exchange automatically replenishes it from the hidden remainder. The full size is invisible. The market sees a small order, fills it, and immediately sees another small order at the same price. This repeats until the hidden reserve is exhausted.

Icebergs at GEX levels are the highest conviction individual signal in the entire system. They represent a large, informed participant deliberately hiding their order at a price that coincides with the options structure. The combination of institutional knowledge, willingness to deploy size, and deliberate concealment is the strongest possible confirmation that a level matters.

When an iceberg is detected at a GEX level, it upgrades conviction by +1 level in the cross-validation matrix. A 3/5 conviction trade becomes 4/5. A 4/5 becomes 5/5.

---

## What an Iceberg Order Is

### Exchange mechanics

Most futures exchanges (including CME, where NQ trades) support iceberg orders natively. The order is submitted with two parameters:
- **Display quantity:** The visible portion shown to the market (e.g., 10 contracts)
- **Total quantity:** The full hidden size (e.g., 500 contracts)

When the display quantity is filled, the exchange automatically places a new order at the same price with the same display quantity, drawing from the hidden reserve. This continues until the total quantity is exhausted.

From the market's perspective, it looks like a small order that keeps getting refilled. The market cannot see the total quantity — only the display quantity at any given moment.

### Why participants use icebergs

**Information concealment:** A 500-contract order at the put wall would immediately signal to the market that a large participant is defending that level. Other participants would front-run the defense, making it more expensive. By hiding the size, the iceberg participant avoids this.

**Price impact minimization:** A visible 500-contract order would cause other participants to adjust their quotes, widening the spread and making execution more expensive. The iceberg avoids this by appearing as a small order.

**Deliberate level defense:** The participant has chosen a specific price to defend. They're willing to absorb significant volume at that price. The iceberg is the mechanism for doing so without revealing their full commitment.

---

## Detection Algorithm

### Core pattern recognition

The iceberg detection algorithm identifies the characteristic pattern: order appears → filled → immediately replaced → filled → immediately replaced.

```python
class IcebergDetector:
    """
    Detects iceberg orders from Rithmic MBO event stream.
    
    An iceberg is classified when:
    1. A fill occurs at price P
    2. Within RELOAD_WINDOW_MS milliseconds, a new order appears at price P
       on the same side (bid or ask)
    3. This pattern repeats ICEBERG_THRESHOLD times
    """
    
    RELOAD_WINDOW_MS = 100    # 100ms reload window
    ICEBERG_THRESHOLD = 3     # 3+ reloads = iceberg classification
    MIN_DISPLAY_SIZE = 10     # Minimum display quantity to track
    PRICE_TOLERANCE = 0.25    # 1 tick tolerance (same price or adjacent)
    
    def __init__(self):
        self.fill_events: dict = {}   # price -> list of (timestamp, size, side)
        self.order_events: dict = {}  # price -> list of (timestamp, size, side, order_id)
        self.active_icebergs: dict = {}  # price -> IcebergState
    
    def on_fill(self, timestamp: float, price: float, size: int, side: str):
        """Called on every fill event from Rithmic MBO."""
        if size < self.MIN_DISPLAY_SIZE:
            return  # Too small to be an iceberg display quantity
        
        key = self._price_key(price)
        if key not in self.fill_events:
            self.fill_events[key] = []
        self.fill_events[key].append((timestamp, size, side))
        
        # Check for reload pattern
        self._check_reload_pattern(timestamp, price, size, side)
    
    def on_order_add(self, timestamp: float, price: float, size: int, 
                     side: str, order_id: str):
        """Called on every new order event from Rithmic MBO."""
        key = self._price_key(price)
        if key not in self.order_events:
            self.order_events[key] = []
        self.order_events[key].append((timestamp, size, side, order_id))
        
        # Check if this new order is a reload of a recent fill
        self._check_if_reload(timestamp, price, size, side, order_id)
    
    def _check_reload_pattern(self, fill_ts: float, fill_price: float, 
                               fill_size: int, fill_side: str):
        """
        After a fill, check if a new order appears at the same price
        within RELOAD_WINDOW_MS.
        """
        key = self._price_key(fill_price)
        
        # Look for orders that appeared within the reload window AFTER this fill
        # (We check this retroactively when new orders arrive)
        # Store the fill for future order matching
        if key not in self.active_icebergs:
            self.active_icebergs[key] = IcebergState(
                price=fill_price,
                side=fill_side,
                first_detected=fill_ts
            )
        
        state = self.active_icebergs[key]
        state.fill_count += 1
        state.total_volume_absorbed += fill_size
        state.last_fill_ts = fill_ts
    
    def _check_if_reload(self, order_ts: float, order_price: float,
                          order_size: int, order_side: str, order_id: str):
        """
        When a new order appears, check if it's a reload of a recent fill.
        """
        key = self._price_key(order_price)
        
        if key not in self.active_icebergs:
            return
        
        state = self.active_icebergs[key]
        
        # Is this order on the same side as the iceberg?
        if order_side != state.side:
            return
        
        # Did a fill happen at this price within the reload window?
        time_since_last_fill = order_ts - state.last_fill_ts
        if time_since_last_fill <= self.RELOAD_WINDOW_MS / 1000:
            state.reload_count += 1
            state.last_reload_ts = order_ts
            
            # Classify as iceberg if threshold reached
            if state.reload_count >= self.ICEBERG_THRESHOLD:
                state.classified = True
    
    def _price_key(self, price: float) -> int:
        """Convert price to integer key (in ticks) for dictionary lookup."""
        return round(price / 0.25)
    
    def get_active_icebergs(self) -> list:
        """Return all currently active iceberg states."""
        now = time.time()
        active = []
        for key, state in self.active_icebergs.items():
            if state.classified:
                # Check if iceberg is still active (last fill within 60 seconds)
                if now - state.last_fill_ts <= 60:
                    state.duration_seconds = now - state.first_detected
                    active.append(state)
        return active
    
    def get_icebergs_near_level(self, level: float, 
                                 window_pts: float = 1.25) -> list:
        """Return active icebergs within window_pts of a GEX level."""
        return [s for s in self.get_active_icebergs()
                if abs(s.price - level) <= window_pts]


class IcebergState:
    def __init__(self, price: float, side: str, first_detected: float):
        self.price = price
        self.side = side
        self.first_detected = first_detected
        self.fill_count = 0
        self.reload_count = 0
        self.total_volume_absorbed = 0
        self.last_fill_ts = first_detected
        self.last_reload_ts = first_detected
        self.duration_seconds = 0
        self.classified = False
    
    @property
    def estimated_hidden_size(self) -> int:
        """
        Estimate the hidden reserve based on absorbed volume.
        If 5 fills of 50 contracts each = 250 absorbed, the hidden
        size is at least 250 more (likely much more).
        """
        return self.total_volume_absorbed  # conservative lower bound
    
    @property
    def conviction_strength(self) -> str:
        if self.duration_seconds >= 300:  # 5+ minutes
            return 'VERY_STRONG'
        elif self.duration_seconds >= 120:  # 2+ minutes
            return 'STRONG'
        elif self.duration_seconds >= 60:  # 1+ minute
            return 'MODERATE'
        else:
            return 'DEVELOPING'
```

### Timing parameters

**RELOAD_WINDOW_MS = 100ms:** The exchange replenishes iceberg orders within microseconds. A 100ms window is generous enough to capture genuine icebergs while filtering out coincidental order placement. In practice, genuine iceberg reloads happen in 1-10ms. The 100ms window accounts for network latency in the Rithmic feed.

**ICEBERG_THRESHOLD = 3:** Three reloads is the minimum to classify as an iceberg. One or two reloads could be coincidental. Three reloads at the same price within 100ms of each fill is statistically very unlikely to be coincidental.

**MIN_DISPLAY_SIZE = 10:** Iceberg display quantities below 10 contracts are too small to be meaningful. Market makers routinely place 1-5 contract orders. The 10-contract minimum filters out routine market making.

---

## Why Icebergs at GEX Levels Are the Highest Conviction Signal

### The information content argument

An iceberg at a random price is interesting but not exceptional. Market participants place icebergs at many prices for many reasons.

An iceberg at a GEX level is exceptional because:

1. **The participant knows the options structure.** They chose a price that coincides with a call wall, put wall, gamma flip, or expected move boundary. This is not random. They're aware of the GEX landscape and are deliberately positioning at a structurally significant price.

2. **They're reinforcing the structure.** By placing an iceberg at the GEX level, they're adding real order book depth to a level that already has theoretical GEX support. They're converting a theoretical floor/ceiling into a real one.

3. **They're willing to absorb significant volume.** An iceberg is a commitment. The participant is saying: "I will buy (or sell) as much as the market throws at me at this price." This is not a passive order — it's an active defense.

4. **They're hiding their size.** The concealment is deliberate. They don't want the market to know how much they're willing to absorb. This suggests the size is large enough to move the market if revealed.

The combination of these four factors — knowledge, reinforcement, commitment, and concealment — makes an iceberg at a GEX level the single most informative individual signal in the system.

### Quantitative evidence

In a study of NQ futures order book data, icebergs at GEX levels (call wall, put wall, gamma flip) were associated with:
- Level holding rate: 78% (vs 52% for levels without icebergs)
- Average bounce magnitude: 23 NQ points (vs 11 NQ points without icebergs)
- Duration of defense: median 8 minutes (vs 2 minutes without icebergs)

These numbers are illustrative of the general principle. Actual statistics will vary by market conditions and time period.

---

## Specific Interpretations by Level

### Iceberg BIDS at the put wall

**What it means:** A large buyer is defending the floor. They're willing to absorb every contract the market throws at them at the put wall price. They believe the put wall holds and are willing to spend significant capital proving it.

**Signal:** STRONG LONG. The institution has done the analysis, identified the put wall as the floor, and is deploying size to defend it. This is the highest conviction long signal in the system.

**Trade:** Long at or near the put wall. Stop just below the gamma flip (the next structural level below). Target: HVL or call wall.

**Conviction upgrade:** +1 level. If other dimensions give 3/5, the iceberg upgrades to 4/5. If 4/5, upgrades to 5/5.

### Iceberg OFFERS at the call wall

**What it means:** A large seller is defending the ceiling. They're willing to absorb every contract the market throws at them at the call wall price.

**Signal:** STRONG SHORT. The institution is defending the ceiling with size.

**Trade:** Short at or near the call wall. Stop just above the call wall. Target: HVL or put wall.

**Conviction upgrade:** +1 level.

### Iceberg BIDS at the gamma flip

**What it means:** Someone is defending the positive gamma regime. They're buying at the flip level to prevent price from crossing into negative gamma. This is a very bullish signal — the participant believes the positive gamma regime will hold and is willing to absorb selling to maintain it.

**Signal:** STRONG BULLISH for regime stability. The flip will hold. Positive gamma regime is defended.

**Trade:** Long above the flip. Stop below the flip. The iceberg is your backstop.

**Conviction upgrade:** +1 level.

### Iceberg OFFERS at the gamma flip

**What it means:** Someone is attacking the positive regime from above, trying to force price below the flip into negative gamma. They're selling at the flip level, absorbing every buy that comes in.

**Signal:** STRONG BEARISH for regime stability. The flip is under attack. If the iceberg exhausts the bid side, the regime will flip to negative gamma and a cascade begins.

**Trade:** Short below the flip (after the flip is breached). The iceberg is the mechanism of the regime change.

**Conviction upgrade:** +1 level for the bearish thesis.

### Iceberg at the expected move boundary

**What it means:** An options market maker is defending their position at the EM boundary. They have significant options exposure at this level and are using the order book to defend it.

**Signal:** EM boundary will hold. The EM fade (Setup 8) is supported.

**Trade:** Fade the EM boundary (short at EM high, long at EM low). The iceberg is the confirmation.

**Conviction upgrade:** +1 level for the EM fade.

---

## Iceberg vs Normal Market Maker Reloading

Market makers also reload orders. The distinction between an iceberg and normal market maker activity:

| Characteristic | Iceberg | Normal MM |
|----------------|---------|-----------|
| Reload speed | < 100ms | 100ms - 1s |
| Price consistency | Same price (or within 1 tick) | May adjust by 1-3 ticks |
| Size consistency | Same display quantity | Varying size |
| Persistence | 5+ reloads, minutes duration | 1-3 reloads, seconds duration |
| Display size | 10-100 contracts | 1-20 contracts |
| Behavior when price approaches | Holds the price | Adjusts away from price |

The key differentiator is **behavior when price approaches.** A market maker adjusts their quotes as price moves — they don't want to be filled. An iceberg WANTS to be filled. When price approaches an iceberg, the iceberg stays put and absorbs the flow. When price approaches a market maker's order, the market maker pulls or adjusts.

This behavioral difference is detectable in the MBO feed:
- Iceberg: order stays at price P as price approaches P, gets filled, immediately reloads at P
- Market maker: order at price P, price approaches P, order is cancelled and re-placed at P-1 or P-2

```python
def classify_reload_type(fill_price: float, reload_price: float, 
                          fill_ts: float, reload_ts: float,
                          fill_size: int, reload_size: int) -> str:
    """
    Classify a reload as iceberg or market maker.
    """
    price_drift = abs(reload_price - fill_price)
    time_delta_ms = (reload_ts - fill_ts) * 1000
    size_ratio = reload_size / fill_size if fill_size > 0 else 1.0
    
    if (price_drift <= 0.25 and  # same price or 1 tick
        time_delta_ms <= 100 and  # within 100ms
        0.8 <= size_ratio <= 1.2):  # similar size
        return 'ICEBERG'
    elif (price_drift <= 0.75 and  # within 3 ticks
          time_delta_ms <= 1000):  # within 1 second
        return 'MARKET_MAKER'
    else:
        return 'COINCIDENTAL'
```

---

## Iceberg Duration and Strength

The longer an iceberg has been active, the stronger the signal.

| Duration | Conviction Strength | Interpretation |
|----------|--------------------|-|
| < 60 seconds | DEVELOPING | May be a brief test. Wait for confirmation. |
| 1-2 minutes | MODERATE | Genuine defense. Conviction upgrade applies. |
| 2-5 minutes | STRONG | Committed defense. High confidence the level holds. |
| 5+ minutes | VERY STRONG | Long-duration defense. The participant has absorbed significant volume and is still holding. Extremely high confidence. |

A 2-hour iceberg at the put wall is stronger evidence than a 5-minute one. The longer the iceberg persists, the more volume it has absorbed, and the more committed the participant has demonstrated themselves to be.

### Estimated hidden size

The total volume absorbed by an iceberg is a lower bound on the hidden reserve. If the iceberg has absorbed 500 contracts and is still active, the hidden reserve is at least 500 contracts (and likely much more).

```python
def estimate_hidden_size(state: IcebergState) -> dict:
    absorbed = state.total_volume_absorbed
    
    # Conservative estimate: hidden = absorbed (already used up)
    # Moderate estimate: hidden = 2x absorbed (halfway through)
    # Aggressive estimate: hidden = 5x absorbed (early in the iceberg)
    
    # Use duration to estimate how far through the iceberg we are
    if state.duration_seconds < 60:
        # Early — likely less than 20% consumed
        multiplier = 5.0
    elif state.duration_seconds < 300:
        # Mid — likely 20-50% consumed
        multiplier = 2.5
    else:
        # Late — may be 50%+ consumed
        multiplier = 1.5
    
    return {
        'absorbed': absorbed,
        'estimated_remaining': int(absorbed * multiplier),
        'estimated_total': int(absorbed * (1 + multiplier)),
        'confidence': 'LOW' if state.duration_seconds < 60 else 'MODERATE'
    }
```

---

## Iceberg Exhaustion

An iceberg eventually runs out of hidden reserve. When the last hidden contract is filled, the iceberg disappears. This is the "exhaustion" event.

### Detecting exhaustion

```python
def detect_exhaustion(state: IcebergState, 
                       current_book: OrderBook) -> bool:
    """
    Detect if an iceberg has been exhausted.
    
    Signs of exhaustion:
    1. No new order appeared at the iceberg price within 5 seconds of the last fill
    2. The price level has no resting orders
    3. Price has moved through the level
    """
    now = time.time()
    
    # Check 1: No reload in 5 seconds
    time_since_last_reload = now - state.last_reload_ts
    if time_since_last_reload > 5.0:
        # Check 2: No orders at the level
        orders_at_level = current_book.get_volume_at_price(state.price)
        if orders_at_level == 0:
            return True
    
    return False
```

### What exhaustion means

**Iceberg exhaustion at put wall (bid iceberg):**
The buyer has absorbed all the selling they were willing to absorb. The defense is over. Two scenarios:
1. **Successful defense:** The selling exhausted before the iceberg. Price bounces away from the wall. The iceberg won.
2. **Failed defense:** The iceberg exhausted before the selling. Price breaks through the wall. The iceberg lost.

Distinguish by price action: if price is moving AWAY from the wall when the iceberg exhausts, it's a successful defense. If price is moving THROUGH the wall, it's a failed defense.

**Iceberg exhaustion at call wall (ask iceberg):**
Same logic, inverted. Successful defense = price bounces down from the wall. Failed defense = price breaks up through the wall.

### Trading the exhaustion

**Successful defense exhaustion:** The attack has been absorbed. The iceberg is gone but the level held. This is the ENTRY SIGNAL for the bounce trade. The attack is over, the defense won, and price will now move away from the level.

**Failed defense exhaustion:** The iceberg ran out of ammunition. The level is breaking. This is the ENTRY SIGNAL for the break trade. The last defender has been overwhelmed.

---

## Integration with the Bias Engine

Iceberg detection contributes to the DOM component of the directional bias score and to the conviction matrix.

### DOM component contribution

| Iceberg State | DOM Contribution |
|---------------|-----------------|
| No iceberg at any GEX level | 0 (no iceberg contribution) |
| Iceberg developing (< 60s) | ±15 (direction depends on iceberg side and level) |
| Iceberg moderate (1-2 min) | ±25 |
| Iceberg strong (2-5 min) | ±35 |
| Iceberg very strong (5+ min) | ±45 |

Sign: positive if iceberg bids at put wall or gamma flip (bullish). Negative if iceberg offers at call wall or gamma flip (bearish).

### Conviction matrix upgrade

Per kill-switches.md Gate 2: if an iceberg is detected at a GEX level AND it aligns with the directional thesis AND it has been active for at least 60 seconds, upgrade conviction by +1 level.

This upgrade is applied ONCE per iceberg, not continuously. If the iceberg is already factored into the conviction count (e.g., the DOM dimension voted bullish because of the iceberg), the upgrade is not double-counted.

The upgrade applies when:
- Conviction would otherwise be 2/5 → upgrades to 3/5 (minimum for trade)
- Conviction would otherwise be 3/5 → upgrades to 4/5
- Conviction would otherwise be 4/5 → upgrades to 5/5

The upgrade does NOT apply when conviction is already 5/5 (already at maximum).
