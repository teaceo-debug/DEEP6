# Order Book Signal OB-2: Aggression Imbalance

## Overview

Aggression Imbalance measures who is taking liquidity in the NQ order book. A market buy (hitting the ask) is an aggressive buy. A market sell (hitting the bid) is an aggressive sell. The imbalance between these two flows tells you which side is more urgent, more willing to pay the spread, and more likely to be informed.

This is distinct from depth asymmetry (OB-3), which measures resting orders. Aggression is KINETIC — it's what's actually happening. Depth is POTENTIAL — it's what could happen. Price moves because of aggression, not because of depth.

The signal runs from -100 (all market sells, maximum seller aggression) to +100 (all market buys, maximum buyer aggression). Zero means balanced — equal buying and selling pressure.

---

## Calculation

### Trade classification

Every trade in the Rithmic MBO feed is classified as a buy or sell based on the price relative to the prevailing bid/ask at the time of execution.

```python
def classify_trade(trade: Trade, book: OrderBook) -> str:
    best_bid = book.best_bid_price
    best_ask = book.best_ask_price
    mid = (best_bid + best_ask) / 2
    
    if trade.price >= best_ask:
        return 'BUY'   # Buyer lifted the ask — aggressive buy
    elif trade.price <= best_bid:
        return 'SELL'  # Seller hit the bid — aggressive sell
    else:
        # Mid-price trade (rare in NQ, but possible in block trades)
        # Proportional allocation based on distance from bid/ask
        buy_fraction = (trade.price - best_bid) / (best_ask - best_bid)
        return 'BUY' if buy_fraction > 0.5 else 'SELL'
```

**NQ-specific note:** NQ futures have a tick size of 0.25 points. The bid-ask spread is typically 0.25-0.50 points (1-2 ticks) during normal market hours. Mid-price trades are uncommon. Most trades are clearly classifiable as buy or sell.

### Rolling window computation

Compute aggression imbalance over three rolling windows simultaneously:

```python
class AggressionImbalance:
    WINDOWS = {
        '30s': 30,
        '1m': 60,
        '5m': 300
    }
    
    def __init__(self):
        self.trades: deque = deque()  # (timestamp, side, size)
    
    def add_trade(self, timestamp: float, side: str, size: int):
        self.trades.append((timestamp, side, size))
        # Prune old trades (keep 5 min max)
        cutoff = timestamp - 300
        while self.trades and self.trades[0][0] < cutoff:
            self.trades.popleft()
    
    def compute(self, window_seconds: int) -> float:
        now = time.time()
        cutoff = now - window_seconds
        
        buy_volume = 0
        sell_volume = 0
        
        for ts, side, size in self.trades:
            if ts >= cutoff:
                if side == 'BUY':
                    buy_volume += size
                else:
                    sell_volume += size
        
        total = buy_volume + sell_volume
        if total == 0:
            return 0.0
        
        # Scale to -100 to +100
        return (buy_volume - sell_volume) / total * 100
    
    def get_all_windows(self) -> dict:
        return {
            '30s': self.compute(30),
            '1m': self.compute(60),
            '5m': self.compute(300)
        }
```

### Size weighting

The base calculation above treats all trades equally by volume. For the primary signal, apply size weighting to give more influence to large trades:

```python
def compute_size_weighted(self, window_seconds: int) -> float:
    now = time.time()
    cutoff = now - window_seconds
    
    buy_weighted = 0
    sell_weighted = 0
    
    for ts, side, size in self.trades:
        if ts >= cutoff:
            # Weight: 1x for < 10 contracts, 2x for 10-49, 5x for 50+
            if size >= 50:
                weight = 5.0
            elif size >= 10:
                weight = 2.0
            else:
                weight = 1.0
            
            weighted_size = size * weight
            if side == 'BUY':
                buy_weighted += weighted_size
            else:
                sell_weighted += weighted_size
    
    total = buy_weighted + sell_weighted
    if total == 0:
        return 0.0
    
    return (buy_weighted - sell_weighted) / total * 100
```

**Primary signal:** Use the size-weighted 30-second imbalance as the primary signal. The 1-minute and 5-minute windows provide context and trend.

---

## Interpretation

### Signal thresholds

| Imbalance Score | Label | Interpretation |
|-----------------|-------|----------------|
| > +60 | STRONG BUYER AGGRESSION | Market is being lifted. Buyers are urgently taking liquidity. Bullish. |
| +30 to +60 | MODERATE BUYER LEAN | Buyers are more aggressive than sellers. Mild bullish lean. |
| -30 to +30 | BALANCED | No clear aggression either way. Neutral. |
| -60 to -30 | MODERATE SELLER LEAN | Sellers are more aggressive than buyers. Mild bearish lean. |
| < -60 | STRONG SELLER AGGRESSION | Market is being hit. Sellers are urgently taking liquidity. Bearish. |

### Multi-window interpretation

The three windows tell different stories:

**30-second window:** The most recent, most time-sensitive signal. Captures the current moment. High noise but high recency. Use for entry timing.

**1-minute window:** Smoothed version of the 30-second signal. Filters out single large trades that temporarily spike the imbalance. Use for directional confirmation.

**5-minute window:** The trend. Is the aggression sustained or a brief spike? A 5-minute imbalance of +50 means buyers have been consistently aggressive for 5 minutes — much more significant than a 30-second spike to +80 followed by a return to neutral.

**Convergence:** When all three windows agree (e.g., 30s: +65, 1m: +58, 5m: +47), the signal is strong and sustained. When they diverge (30s: +80, 1m: +20, 5m: -10), the current burst is not part of a sustained trend — it may be a single large trade or a brief spike.

---

## How to Use with Options Bias

### Aggression confirms options bias

When the aggression imbalance aligns with the options directional bias, conviction increases.

**Example:** Options bias is bullish (+65 score). Aggression imbalance is +52 (moderate buyer lean). The book is confirming the options signal. The DOM component of the bias score gets a positive contribution. Conviction may increase from 3/5 to 4/5.

**Quantitative rule:** If |aggression_imbalance_1m| > 30 AND sign matches options bias direction → DOM component contribution increases by 15-20 points.

### Aggression opposes options bias

When aggression opposes the options bias, it's a warning signal. One of two things is happening:

1. **The book is leading the options market.** The order book moves faster than options flow data. If sellers are aggressive in NQ but options flow is still showing bullish, the book may be pricing in information that hasn't yet appeared in the options market. The book is often right.

2. **The options read is wrong.** The flow signal may be stale, misinterpreted, or reflecting hedging rather than directional positioning.

**Quantitative rule:** If |aggression_imbalance_1m| > 40 AND sign OPPOSES options bias direction → reduce DOM component contribution by 20-30 points. If |aggression_imbalance_1m| > 60 AND sign OPPOSES → flag as WARNING in output. Conviction may drop by 1 level.

**Example:** Options bias is bullish (+65). Aggression imbalance is -55 (moderate seller lean). Warning: the book is selling while options say buy. Investigate: Is the flow data fresh? Is there a news event? Is the dark pool also selling? If dark pool is also selling, the options flow may be the outlier — reduce conviction to 2/5 (no trade).

### Aggression at options levels

The most important application of aggression imbalance is at specific GEX levels.

**Sellers aggressive AT the call wall:**
The call wall is being attacked. Sellers are hitting bids at the call wall level, trying to push price through. Combined with the defense score (OB-1), this tells you whether the attack will succeed:
- High defense score + seller aggression = ABSORPTION. The wall is holding. Short bounce trade.
- Low defense score + seller aggression = BREAK IMMINENT. The wall is being overwhelmed. Prepare for Setup 2 (Wall Break) long.

**Buyers aggressive AT the put wall:**
The put wall is being tested from below. Buyers are lifting asks at the put wall level, trying to hold the floor.
- High defense score + buyer aggression = ABSORPTION. The floor is holding. Long bounce trade (Setup 1).
- Low defense score + buyer aggression = BREAK IMMINENT. The floor is being overwhelmed. Prepare for Regime E cascade.

**Sellers aggressive AT the gamma flip (from above):**
Someone is trying to push price below the gamma flip into negative gamma territory. This is a bearish attack on the regime itself.
- If sustained (5-minute imbalance < -40 at the flip level), the regime transition is likely. Prepare for Setup 3 (Gamma Flip Cross) short.

**Buyers aggressive AT the gamma flip (from below):**
Someone is trying to push price back above the gamma flip into positive gamma territory. This is a bullish defense of the regime.
- If sustained (5-minute imbalance > +40 at the flip level), the regime may recover. Prepare for Setup 3 long (flip recovery).

---

## Aggression Velocity

The rate of change of aggression imbalance is often more informative than the level itself.

```python
def compute_velocity(self, short_window: int = 30, long_window: int = 300) -> float:
    short_imbalance = self.compute(short_window)
    long_imbalance = self.compute(long_window)
    return short_imbalance - long_imbalance
```

**Interpretation:**

| Velocity | Meaning |
|----------|---------|
| > +40 | Rapidly accelerating buying. Short-term buyers are much more aggressive than the 5-minute trend. Often precedes a breakout or acceleration. |
| +20 to +40 | Buying momentum building. |
| -20 to +20 | Stable. Current aggression matches the trend. |
| -40 to -20 | Selling momentum building. |
| < -40 | Rapidly accelerating selling. Often precedes a breakdown or acceleration. |

**Velocity at options levels:** If aggression velocity is > +40 at the put wall, buyers are accelerating their defense. The wall is being reinforced with increasing urgency. This is a strong signal that the wall will hold. If velocity is < -40 at the put wall, sellers are accelerating their attack. The wall is under increasing pressure.

---

## The Mean-Reversion Trap

Extreme aggression (imbalance > +80 or < -80) sometimes exhausts itself. After a burst of near-100% market buys, the book needs time to replenish. The ask side gets depleted, spreads widen, and a brief pause or pullback is normal before continuation.

This is NOT a reversal signal. It's a pause. The distinction:

**Exhaustion pause (continuation):**
- Imbalance spikes to +85, then drops to +20 over 30 seconds
- Price holds near the high (doesn't give back more than 3-5 ticks)
- Depth on the bid side is still healthy
- The 5-minute imbalance remains positive (+30 to +50)
- Interpretation: Buyers paused to let the book replenish. Continuation likely.

**Genuine reversal:**
- Imbalance spikes to +85, then drops to -30 over 30 seconds
- Price gives back 10+ ticks
- Sellers become aggressive (imbalance goes negative)
- The 5-minute imbalance turns negative
- Interpretation: The buying was exhausted and sellers took control. Reversal.

The key differentiator is whether the 5-minute imbalance changes sign. A brief dip in the 30-second imbalance while the 5-minute remains positive is a pause. A sign change in the 5-minute imbalance is a reversal.

---

## Combining Aggression with Level Defense

The most powerful signal in the DOM dimension is the combination of aggression imbalance and level defense score. The four combinations:

### Buyer aggression + high defense at put wall = ABSORPTION (strongest long signal)

Buyers are hitting the ask at the put wall AND the wall is reloading and holding. This is the textbook absorption pattern. The put wall is being tested by sellers (who are hitting bids, creating the buyer aggression reading as the wall defends) and the defense is absorbing every wave.

Wait for the attack to exhaust (aggression drops from +60 to +20 while price stays at the wall), then enter long. The exhaustion of the attack is the entry signal.

### Seller aggression + low defense at put wall = BREAK IMMINENT (short signal)

Sellers are hitting bids at the put wall AND the wall is not reloading. Each wave of selling depletes the defense without replacement. The wall will break.

Enter short when the last defending order is consumed. Price will accelerate through the void below the wall.

### Seller aggression + high defense at call wall = ABSORPTION (strongest short signal)

Buyers are hitting the ask at the call wall AND the wall is reloading and holding. The ceiling is being tested and held. Enter short after the attack exhausts.

### Buyer aggression + low defense at call wall = BREAK IMMINENT (long signal)

Buyers are hitting the ask at the call wall AND the wall is not reloading. The ceiling will break. Enter long on the break.

---

## Implementation Notes

### Rithmic MBO feed specifics

The Rithmic MBO feed provides every individual order event: add, modify, cancel, and fill. Trade classification requires matching fills to the prevailing bid/ask at the time of the fill.

The bid/ask at any moment is the best bid and best ask from the current order book state. Since the MBO feed provides every order event, the book state can be reconstructed exactly at any timestamp.

```python
class NQOrderBook:
    def __init__(self):
        self.bids: SortedDict = SortedDict(lambda x: -x)  # descending
        self.asks: SortedDict = SortedDict()  # ascending
    
    def on_order_event(self, event: OrderEvent):
        book = self.bids if event.side == 'BID' else self.asks
        if event.type == 'ADD':
            book[event.price] = book.get(event.price, 0) + event.quantity
        elif event.type == 'CANCEL':
            book[event.price] = max(0, book.get(event.price, 0) - event.quantity)
            if book[event.price] == 0:
                del book[event.price]
        elif event.type == 'FILL':
            book[event.price] = max(0, book.get(event.price, 0) - event.quantity)
            if book[event.price] == 0:
                del book[event.price]
    
    @property
    def best_bid_price(self) -> float:
        return next(iter(self.bids)) if self.bids else 0
    
    @property
    def best_ask_price(self) -> float:
        return next(iter(self.asks)) if self.asks else float('inf')
```

### Performance at 1,000 callbacks/second

The Rithmic MBO feed generates 1,000+ callbacks per second during active markets. The aggression imbalance computation must be efficient.

Key optimizations:
- Use `collections.deque` for the trade history (O(1) append and popleft)
- Prune old trades lazily (only when computing, not on every add)
- Pre-compute running totals and update incrementally rather than recomputing from scratch

```python
class EfficientAggressionTracker:
    def __init__(self, max_window: int = 300):
        self.trades = deque()
        self.buy_volume_total = 0
        self.sell_volume_total = 0
        self.max_window = max_window
    
    def add_trade(self, timestamp: float, side: str, size: int):
        self.trades.append((timestamp, side, size))
        if side == 'BUY':
            self.buy_volume_total += size
        else:
            self.sell_volume_total += size
        self._prune(timestamp)
    
    def _prune(self, now: float):
        cutoff = now - self.max_window
        while self.trades and self.trades[0][0] < cutoff:
            ts, side, size = self.trades.popleft()
            if side == 'BUY':
                self.buy_volume_total -= size
            else:
                self.sell_volume_total -= size
```

This approach maintains O(1) amortized complexity for both adding trades and computing the full-window imbalance.
