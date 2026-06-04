# Order Book Signal OB-3: Depth Asymmetry

## Overview

Depth Asymmetry compares the total resting order volume on the bid side versus the ask side of the NQ order book. A bid-heavy book means more contracts are waiting to buy than to sell. An ask-heavy book means the opposite.

Depth is POTENTIAL energy. It tells you what COULD happen if price moves in a given direction. Aggression (OB-2) is KINETIC energy — what IS happening. Depth without aggression is a cushion. Aggression without depth is a breakout. The combination of both tells the complete story.

The signal runs from 0.0 (all ask depth, no bid depth) to 1.0 (all bid depth, no ask depth). A ratio of 0.5 means perfectly balanced. Values above 0.5 indicate bid-heavy (bullish lean). Values below 0.5 indicate ask-heavy (bearish lean).

---

## Calculation

### Basic depth ratio

```python
def compute_depth_ratio(book: OrderBook, levels: int = 20) -> float:
    """
    Compare total resting volume on bid vs ask across N levels.
    
    levels: Number of price levels to include on each side.
            20 levels = 5.0 NQ points (20 × 0.25 tick) on each side.
    """
    bid_depth = 0
    ask_depth = 0
    
    # Sum bid depth across top N levels (best bid and below)
    for i, (price, volume) in enumerate(book.bids.items()):
        if i >= levels:
            break
        bid_depth += volume
    
    # Sum ask depth across top N levels (best ask and above)
    for i, (price, volume) in enumerate(book.asks.items()):
        if i >= levels:
            break
        ask_depth += volume
    
    total = bid_depth + ask_depth
    if total == 0:
        return 0.5  # empty book = neutral
    
    return bid_depth / total
```

### Why 20 levels

Twenty levels on each side covers 5.0 NQ points (20 × 0.25 tick). This is the "near book" — the depth that is immediately relevant to price action. Orders 50+ ticks away from the best bid/ask are less relevant to current price dynamics.

For context around specific options levels, use a narrower window (5-10 levels = 1.25-2.50 NQ points) centered on the level rather than the best bid/ask.

### Size-weighted depth ratio

The basic ratio treats all contracts equally. The size-weighted version gives more influence to large orders:

```python
def compute_weighted_depth_ratio(book: OrderBook, levels: int = 20) -> float:
    bid_weighted = 0
    ask_weighted = 0
    
    for i, (price, volume) in enumerate(book.bids.items()):
        if i >= levels:
            break
        weight = 3.0 if volume > 100 else (2.0 if volume > 50 else 1.0)
        bid_weighted += volume * weight
    
    for i, (price, volume) in enumerate(book.asks.items()):
        if i >= levels:
            break
        weight = 3.0 if volume > 100 else (2.0 if volume > 50 else 1.0)
        ask_weighted += volume * weight
    
    total = bid_weighted + ask_weighted
    if total == 0:
        return 0.5
    
    return bid_weighted / total
```

**Primary signal:** Use the size-weighted ratio. Large orders are more meaningful than many small orders.

---

## Interpretation

### Signal thresholds

| Ratio | Label | Interpretation |
|-------|-------|----------------|
| > 0.65 | BID-HEAVY | More contracts waiting to buy than sell. Downside is cushioned. Bullish lean. |
| 0.55-0.65 | SLIGHTLY BID-HEAVY | Mild bullish lean. |
| 0.45-0.55 | BALANCED | No lean from the book. Neutral. |
| 0.35-0.45 | SLIGHTLY ASK-HEAVY | Mild bearish lean. |
| < 0.35 | ASK-HEAVY | More contracts waiting to sell than buy. Upside is capped. Bearish lean. |

### What depth asymmetry tells you

**Bid-heavy book (ratio > 0.65):** There are significantly more resting buy orders than sell orders in the near book. This means:
- If price drops, it will encounter substantial buying interest
- The downside is cushioned — sellers need to absorb a lot of bids before price can fall significantly
- This does NOT mean price will go up. It means the downside is protected.

**Ask-heavy book (ratio < 0.35):** There are significantly more resting sell orders than buy orders. This means:
- If price rises, it will encounter substantial selling interest
- The upside is capped — buyers need to absorb a lot of offers before price can rise significantly
- This does NOT mean price will go down. It means the upside is capped.

**Balanced book (ratio 0.45-0.55):** Neither side has a clear advantage. Price can move in either direction with similar ease. The book is not providing directional information.

---

## Depth Asymmetry at Options Levels

The most important application of depth asymmetry is at specific GEX levels. The depth at these levels tells you whether the options structure is being reinforced by the order book.

### Bid depth at the put wall

The put wall is the primary floor in positive gamma regimes. The depth of the bid side AT the put wall tells you how well the floor is supported.

```python
def depth_at_level(book: OrderBook, level: float, 
                   window_ticks: int = 10) -> tuple[float, float]:
    """
    Returns (bid_depth, ask_depth) within window_ticks of the level.
    window_ticks = 10 → ±2.50 NQ points around the level.
    """
    tick = 0.25
    low = level - window_ticks * tick
    high = level + window_ticks * tick
    
    bid_depth = sum(v for p, v in book.bids.items() if low <= p <= high)
    ask_depth = sum(v for p, v in book.asks.items() if low <= p <= high)
    
    return bid_depth, ask_depth
```

**High bid depth at put wall (bid_depth > 500 contracts within ±2.50 pts):**
The floor is genuinely supported. The GEX structure is being reinforced by real order book depth. This is a strong confirmation for the long bounce trade (Setup 1).

**Low bid depth at put wall (bid_depth < 100 contracts within ±2.50 pts):**
The floor is a paper floor. GEX says it's a level but the book says nobody is defending it. The put wall may break on moderate selling pressure. Do not trade the bounce without additional confirmation from flow and dark pool.

### Ask depth at the call wall

The call wall is the primary ceiling in positive gamma regimes. The depth of the ask side AT the call wall tells you how well the ceiling is defended.

**High ask depth at call wall (ask_depth > 500 contracts within ±2.50 pts):**
The ceiling is genuinely defended. Sellers are positioned at the call wall. This is a strong confirmation for the short bounce trade.

**Low ask depth at call wall (ask_depth < 100 contracts within ±2.50 pts):**
The ceiling is a paper ceiling. The call wall may break on moderate buying pressure. Prepare for Setup 2 (Wall Break) long.

### Depth around the gamma flip

The gamma flip is the most important single level in the system. The depth distribution around it tells you which regime is being defended.

**Bid-heavy below the flip + ask-heavy above the flip:**
The book is confirming the regime boundary. Buyers are defending the positive gamma regime from below (buying dips near the flip). Sellers are defending the negative gamma regime from above (selling rallies near the flip). The flip is a genuine boundary.

**Bid-heavy ABOVE the flip:**
Buyers are positioned above the flip, suggesting they expect price to stay in positive gamma territory. Bullish for the regime.

**Ask-heavy BELOW the flip:**
Sellers are positioned below the flip, suggesting they expect price to stay in negative gamma territory. Bearish for the regime.

**Inverted (ask-heavy below flip, bid-heavy above flip):**
The book is trying to shift the regime. Sellers below the flip are pushing price down (trying to establish negative gamma). Buyers above the flip are trying to hold positive gamma. This is a contested regime — high uncertainty.

### Depth at expected move boundaries

The expected move boundaries are statistical levels derived from implied volatility. They're not GEX levels, but they're important because options market makers have significant exposure at these levels.

**High defense at EM boundaries (both bid at EM low and ask at EM high):**
The statistical boundary is being respected. Options market makers are defending their positions. The EM is likely to hold as the day's range.

**Low defense at EM boundaries:**
The EM may be exceeded. On high-volatility days, the EM can be exceeded by 50-100% of its value. Do not trade the EM fade (Setup 8) if depth at the EM boundaries is below 100 contracts.

---

## Dynamic Depth: Tracking Changes Over Time

The book changes constantly. A snapshot of depth asymmetry is less informative than the TREND in depth asymmetry over time.

### Depth shift detection

```python
class DepthShiftDetector:
    def __init__(self, window_minutes: int = 5):
        self.history: deque = deque()  # (timestamp, ratio)
        self.window_seconds = window_minutes * 60
    
    def record(self, timestamp: float, ratio: float):
        self.history.append((timestamp, ratio))
        cutoff = timestamp - self.window_seconds
        while self.history and self.history[0][0] < cutoff:
            self.history.popleft()
    
    def compute_shift(self) -> float:
        """
        Returns the change in depth ratio over the window.
        Positive = becoming more bid-heavy (bullish shift).
        Negative = becoming more ask-heavy (bearish shift).
        """
        if len(self.history) < 2:
            return 0.0
        oldest_ratio = self.history[0][1]
        newest_ratio = self.history[-1][1]
        return newest_ratio - oldest_ratio
    
    def get_trend(self) -> str:
        shift = self.compute_shift()
        if shift > 0.10:
            return "RAPIDLY_BID_BUILDING"
        elif shift > 0.05:
            return "BID_BUILDING"
        elif shift < -0.10:
            return "RAPIDLY_ASK_BUILDING"
        elif shift < -0.05:
            return "ASK_BUILDING"
        else:
            return "STABLE"
```

### Shift interpretation

**Balanced → Bid-heavy over 5 minutes (shift > +0.10):**
Someone is building support. Large buy orders are being placed in the near book. This often precedes a bullish move — the participant is positioning before buying aggressively. Watch for aggression imbalance to turn positive as they start lifting offers.

**Balanced → Ask-heavy over 5 minutes (shift < -0.10):**
Someone is building resistance. Large sell orders are being placed in the near book. This often precedes a bearish move — the participant is positioning before selling aggressively. Watch for aggression imbalance to turn negative as they start hitting bids.

**Bid-heavy → Balanced (shift from > 0.65 to ~0.50):**
The bid support is being withdrawn. Either the participant achieved their objective (price moved up) or they changed their mind. If price hasn't moved up, this is a warning — the support is being pulled.

**Bid-heavy → Ask-heavy (shift from > 0.65 to < 0.35):**
A dramatic reversal in book composition. This is rare and significant. Someone is aggressively repositioning from long to short (or vice versa). This often precedes a sharp move in the direction of the new dominant side.

---

## Stable Depth vs Fleeting Depth

Not all depth is equal. Orders that persist for 10+ seconds are more reliable than flash orders that appear and disappear in under 1 second.

### Persistence filtering

```python
class PersistentDepthTracker:
    def __init__(self, min_persistence_seconds: float = 10.0):
        self.order_timestamps: dict = {}  # order_id -> placed_timestamp
        self.min_persistence = min_persistence_seconds
    
    def on_order_add(self, order_id: str, timestamp: float, price: float, size: int):
        self.order_timestamps[order_id] = timestamp
    
    def on_order_cancel(self, order_id: str, timestamp: float):
        placed = self.order_timestamps.pop(order_id, None)
        if placed:
            duration = timestamp - placed
            if duration < 1.0:
                # Flash order — likely a spoof or HFT test
                return 'FLASH'
            elif duration < self.min_persistence:
                # Short-lived order — less reliable
                return 'SHORT_LIVED'
            else:
                # Persistent order — genuine participant
                return 'PERSISTENT'
    
    def compute_persistent_depth_ratio(self, book: OrderBook, 
                                        levels: int = 20) -> float:
        """
        Compute depth ratio using only orders that have been resting
        for at least min_persistence_seconds.
        """
        now = time.time()
        
        bid_depth = 0
        ask_depth = 0
        
        for price, orders in book.get_all_orders_with_ids():
            for order_id, size in orders:
                placed = self.order_timestamps.get(order_id, now)
                age = now - placed
                if age >= self.min_persistence:
                    if price <= book.best_bid_price:
                        bid_depth += size
                    else:
                        ask_depth += size
        
        total = bid_depth + ask_depth
        return bid_depth / total if total > 0 else 0.5
```

**Persistent depth ratio:** The depth ratio computed from only orders that have been resting for 10+ seconds. This filters out spoofs and HFT test orders, leaving only genuine participants.

**Flash order ratio:** The fraction of total depth that is flash orders (< 1 second). A high flash order ratio (> 30%) indicates significant spoofing activity. Cross-reference with spoof-context.md.

---

## Depth vs Aggression: The Complete Picture

Depth and aggression together tell the complete story of the order book. The four combinations:

### Bid-heavy depth + buyer aggression = STRONG BULLISH

The book has a cushion of buy orders AND buyers are actively taking liquidity. This is the strongest bullish signal from the DOM. Price is being supported from below (depth) and pushed from below (aggression). Both potential and kinetic energy are bullish.

**Trading implication:** Highest conviction long signal from the DOM dimension. Contributes +40 to +50 to the DOM component of the bias score.

### Bid-heavy depth + seller aggression = ABSORPTION

The book has a cushion of buy orders AND sellers are hitting bids. The bids are absorbing the selling. Price is not moving down despite seller aggression because the bid depth is absorbing every wave.

**Trading implication:** This is the absorption pattern. The selling is being absorbed. If the bid depth holds (doesn't deplete), price will reverse upward when the selling exhausts. Watch for aggression imbalance to turn positive as the selling exhausts.

### Ask-heavy depth + seller aggression = STRONG BEARISH

The book has a wall of sell orders AND sellers are actively taking liquidity. Both potential and kinetic energy are bearish.

**Trading implication:** Highest conviction short signal from the DOM dimension. Contributes -40 to -50 to the DOM component of the bias score.

### Ask-heavy depth + buyer aggression = ABSORPTION (bearish)

The book has a wall of sell orders AND buyers are hitting asks. The asks are absorbing the buying. Price is not moving up despite buyer aggression because the ask depth is absorbing every wave.

**Trading implication:** The buying is being absorbed. If the ask depth holds, price will reverse downward when the buying exhausts. Watch for aggression imbalance to turn negative as the buying exhausts.

---

## Integration with the Bias Engine

The depth asymmetry signal contributes to the DOM component of the directional bias score.

```python
def depth_to_dom_contribution(ratio: float, shift: float) -> float:
    """
    Convert depth ratio and shift to DOM component contribution (-100 to +100).
    """
    # Base contribution from current ratio
    if ratio > 0.65:
        base = 30 + (ratio - 0.65) / 0.35 * 20  # 30 to 50
    elif ratio > 0.55:
        base = 10 + (ratio - 0.55) / 0.10 * 20  # 10 to 30
    elif ratio > 0.45:
        base = (ratio - 0.50) / 0.05 * 10  # -10 to +10
    elif ratio > 0.35:
        base = -10 - (0.45 - ratio) / 0.10 * 20  # -10 to -30
    else:
        base = -30 - (0.35 - ratio) / 0.35 * 20  # -30 to -50
    
    # Shift bonus/penalty
    shift_contribution = shift * 100  # shift of 0.10 = +10 pts
    shift_contribution = max(-20, min(20, shift_contribution))
    
    return max(-100, min(100, base + shift_contribution))
```

The depth asymmetry contribution is combined with aggression imbalance, defense score, iceberg detection, and book depletion to produce the final DOM component score.

**Weight within DOM component:**
- Defense score (OB-1): 35%
- Aggression imbalance (OB-2): 30%
- Depth asymmetry (OB-3): 20%
- Iceberg detection (OB-4): 10% (binary, but high impact when present)
- Book depletion (OB-5): 5% (supplementary)

Depth asymmetry has a 20% weight because it's the most susceptible to spoofing. A spoofer can create the appearance of bid-heavy depth by placing large fake bids. The persistent depth filter reduces this risk, but depth remains less reliable than aggression (which requires actual trades) or icebergs (which require actual fills).
