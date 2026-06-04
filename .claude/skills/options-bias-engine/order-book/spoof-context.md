# Order Book Signal OB-6: Spoof Detection and Context at Options Levels

## Overview

Spoofing is the practice of placing large visible orders with the intent to cancel them before execution. The order is designed to create the appearance of support or resistance, manipulating other traders' behavior. It's illegal under the Commodity Exchange Act (CFTC Rule 180.1) but widespread in futures markets, particularly in NQ.

The key insight for this system is not just detecting spoofs — it's understanding what the spoof's CONTEXT relative to GEX levels tells you about the spoofer's intent. A spoof at a call wall means something very different from a spoof at a put wall. The spoofer is trying to accomplish something specific, and that intent is readable from the context.

Spoof detection is supplementary information, not a primary signal. The four rivers (FlashAlpha, Massive, Unusual Whales, Rithmic MBO) plus icebergs (genuine orders) are more reliable. Use spoof context to adjust conviction, not to generate trades.

---

## What Spoofing Is

### The mechanics

A spoofer places a large order (typically 100-500+ contracts) at a conspicuous price level. The order is visible to all market participants. Other traders see the large order and adjust their behavior:
- Buyers see a large bid and feel comfortable buying (the "support" looks real)
- Sellers see a large offer and hesitate to sell through it (the "resistance" looks real)

As price approaches the spoof order, the spoofer cancels it. The order disappears before it can be filled. The spoofer has achieved their goal: they moved other participants' behavior without risking any capital.

### Why it's profitable

The spoofer profits by:
1. **Creating false support:** Place large fake bids below the market. Other buyers feel safe buying. Price rises. Spoofer sells into the rally. Cancel the fake bids.
2. **Creating false resistance:** Place large fake offers above the market. Other sellers feel safe selling. Price drops. Spoofer buys the dip. Cancel the fake offers.
3. **Directional manipulation:** Push price toward a specific level (e.g., a GEX wall) by creating the appearance of support or resistance at strategic prices.

---

## Detection Algorithm

### Core detection logic

```python
class SpoofDetector:
    """
    Detects spoofing from Rithmic MBO event stream.
    
    A spoof is classified when:
    1. A large order appears (> MIN_SPOOF_SIZE contracts)
    2. The order is cancelled before being filled (or mostly filled)
    3. The cancellation occurs as price approaches the order
    4. This pattern repeats at the same price level
    """
    
    MIN_SPOOF_SIZE = 100          # Minimum order size to track
    CANCEL_FILL_RATIO_THRESHOLD = 0.8  # 80% cancelled = likely spoof
    APPROACH_WINDOW_TICKS = 10    # Price within 10 ticks = "approaching"
    REPEAT_THRESHOLD = 2          # 2+ repeats = confirmed spoof pattern
    PRICE_TOLERANCE_TICKS = 3     # Orders within 3 ticks = same level
    
    def __init__(self):
        self.tracked_orders: dict = {}  # order_id -> OrderTrackState
        self.level_stats: dict = {}     # price_key -> LevelSpoofStats
    
    def on_order_add(self, order_id: str, timestamp: float, 
                     price: float, size: int, side: str):
        if size < self.MIN_SPOOF_SIZE:
            return
        
        self.tracked_orders[order_id] = OrderTrackState(
            order_id=order_id,
            price=price,
            size=size,
            side=side,
            placed_ts=timestamp,
            filled_quantity=0
        )
    
    def on_order_fill(self, order_id: str, timestamp: float, 
                      filled_qty: int, remaining_qty: int):
        if order_id in self.tracked_orders:
            self.tracked_orders[order_id].filled_quantity += filled_qty
    
    def on_order_cancel(self, order_id: str, timestamp: float, 
                        current_spot: float):
        if order_id not in self.tracked_orders:
            return
        
        state = self.tracked_orders.pop(order_id)
        duration = timestamp - state.placed_ts
        
        # Compute fill ratio
        fill_ratio = state.filled_quantity / state.size
        cancel_ratio = 1 - fill_ratio
        
        # Was price approaching when cancelled?
        tick = 0.25
        distance_to_order = abs(current_spot - state.price)
        was_approaching = distance_to_order <= self.APPROACH_WINDOW_TICKS * tick
        
        # Classify
        if (cancel_ratio >= self.CANCEL_FILL_RATIO_THRESHOLD and 
            was_approaching and
            duration < 30.0):  # Cancelled within 30 seconds
            
            self._record_spoof_event(
                price=state.price,
                side=state.side,
                size=state.size,
                timestamp=timestamp,
                duration=duration,
                fill_ratio=fill_ratio
            )
    
    def _record_spoof_event(self, price: float, side: str, size: int,
                             timestamp: float, duration: float, 
                             fill_ratio: float):
        key = self._price_key(price)
        if key not in self.level_stats:
            self.level_stats[key] = LevelSpoofStats(price=price)
        
        stats = self.level_stats[key]
        stats.events.append(SpoofEvent(
            price=price,
            side=side,
            size=size,
            timestamp=timestamp,
            duration_seconds=duration,
            fill_ratio=fill_ratio
        ))
        
        # Classify as confirmed spoof if pattern repeats
        recent_events = [e for e in stats.events 
                         if timestamp - e.timestamp <= 300]  # last 5 min
        if len(recent_events) >= self.REPEAT_THRESHOLD:
            stats.confirmed = True
            stats.dominant_side = self._dominant_side(recent_events)
    
    def _price_key(self, price: float) -> int:
        return round(price / 0.25)
    
    def _dominant_side(self, events: list) -> str:
        bid_count = sum(1 for e in events if e.side == 'BID')
        ask_count = sum(1 for e in events if e.side == 'ASK')
        return 'BID' if bid_count >= ask_count else 'ASK'
    
    def get_confirmed_spoofs(self, max_age_seconds: float = 300) -> list:
        now = time.time()
        result = []
        for key, stats in self.level_stats.items():
            if stats.confirmed:
                recent = [e for e in stats.events 
                          if now - e.timestamp <= max_age_seconds]
                if recent:
                    result.append({
                        'price': stats.price,
                        'dominant_side': stats.dominant_side,
                        'event_count': len(recent),
                        'avg_size': sum(e.size for e in recent) / len(recent),
                        'last_seen': max(e.timestamp for e in recent)
                    })
        return result
    
    def get_spoofs_near_level(self, level: float, 
                               window_pts: float = 2.5) -> list:
        return [s for s in self.get_confirmed_spoofs()
                if abs(s['price'] - level) <= window_pts]
```

### Cancel-to-fill ratio

The primary detection metric. Track every large order (> 100 contracts) and compute what fraction is cancelled vs filled.

```python
class CancelFillTracker:
    def __init__(self, window_minutes: int = 30):
        self.window_seconds = window_minutes * 60
        self.order_outcomes: dict = {}  # price_key -> list of (timestamp, cancel_ratio)
    
    def record_outcome(self, price: float, timestamp: float, 
                        cancel_ratio: float):
        key = round(price / 0.25)
        if key not in self.order_outcomes:
            self.order_outcomes[key] = []
        self.order_outcomes[key].append((timestamp, cancel_ratio))
    
    def get_cancel_ratio_at_level(self, level: float, 
                                   window_pts: float = 1.25) -> float:
        """
        Returns the average cancel ratio for large orders near a level
        in the last 30 minutes.
        """
        now = time.time()
        cutoff = now - self.window_seconds
        
        relevant_outcomes = []
        for key, outcomes in self.order_outcomes.items():
            price = key * 0.25
            if abs(price - level) <= window_pts:
                recent = [(ts, cr) for ts, cr in outcomes if ts >= cutoff]
                relevant_outcomes.extend(recent)
        
        if not relevant_outcomes:
            return 0.0  # No data
        
        return sum(cr for _, cr in relevant_outcomes) / len(relevant_outcomes)
```

**Interpretation:**
- Cancel ratio > 0.80 at a level: High spoofing activity. Orders at this level are mostly fake.
- Cancel ratio 0.50-0.80: Mixed. Some genuine orders, some spoofs.
- Cancel ratio < 0.50: Mostly genuine orders. Low spoofing activity.

---

## Spoof Context at Options Levels

The spoof's location relative to GEX levels reveals the spoofer's intent. This is the key analytical insight.

### Spoof OFFERS above the call wall

**Setup:** Large fake sell orders placed above the call wall. The spoofer is creating the appearance of resistance above the wall.

**Intent:** The spoofer wants price to stay below the call wall. They're reinforcing the wall artificially. They believe the call wall will hold and are using the spoof to discourage buyers from pushing through.

**Implication:** The call wall is likely to hold. The spoofer's view aligns with the GEX mechanics (call wall is a ceiling). The spoof is reinforcing a genuine structural level.

**Conviction adjustment:** If the call wall bounce (short) is the thesis, spoof offers above the wall are CONFIRMING. Note it in the narrative but do not increase conviction (spoofs are unreliable — the spoofer can change their mind). The genuine defense (defense score, icebergs) is more reliable.

**Example:** Call wall at 21,200. Spoof offers at 21,220-21,250 (above the wall). The spoofer is creating a "ceiling above the ceiling." They want buyers to see resistance above the wall and give up. This supports the short thesis at the call wall.

### Spoof BIDS at the call wall

**Setup:** Large fake buy orders placed AT the call wall level. The spoofer is creating the appearance of support at the call wall.

**Intent:** The spoofer wants traders to think there's a floor at the call wall. But they'll pull the bids when price arrives. It's a TRAP — they want to sell the break.

**Implication:** Be cautious longing the "support" at the call wall. The bids are fake. When price arrives at the call wall, the bids will disappear and price will fall through. The spoofer is setting up a short entry.

**Conviction adjustment:** If the call wall bounce (short) is the thesis, spoof bids AT the wall are CONFIRMING the short thesis (the spoofer is also bearish, using the fake bids to attract buyers before selling). If the wall break (long) is the thesis, spoof bids at the wall are a WARNING — the spoofer may be trying to trap longs.

**Example:** Call wall at 21,200. Spoof bids at 21,195-21,200. The spoofer is creating fake support at the wall. Buyers see the bids and feel safe buying. The spoofer sells into the buying, then pulls the bids. Price falls. The spoofer is short.

### Spoof BIDS below the put wall

**Setup:** Large fake buy orders placed BELOW the put wall. The spoofer is creating the appearance of a floor below the put wall.

**Intent:** The spoofer wants traders to think there's support below the put wall. But they'll pull the bids when price arrives. It's a TRAP for longs — they want to sell the break of the put wall.

**Implication:** The put wall may be weaker than it looks. If dark pool is also selling AND spoof bids are below the put wall, the spoofer and the dark pool participant may be coordinating (or independently reaching the same bearish conclusion). The put wall break is more likely.

**Conviction adjustment:** If the put wall bounce (long) is the thesis, spoof bids below the wall are a WARNING. The spoofer is bearish and is setting up a trap. Reduce conviction by 1 level.

**Example:** Put wall at 20,850. Spoof bids at 20,820-20,830 (below the wall). The spoofer is creating fake support below the wall. If the put wall breaks, buyers will see the "support" below and buy. The spoofer sells into the buying, then pulls the bids. Price cascades lower.

### Spoof OFFERS at the put wall

**Setup:** Large fake sell orders placed AT the put wall level from above. The spoofer is creating the appearance of resistance at the put wall.

**Intent:** The spoofer wants price pushed DOWN to the put wall. They're creating fake resistance above the wall to discourage buyers, pushing price toward the wall. But the put wall has genuine defense (from GEX). The spoofer may be SETTING UP a long entry — they push price down artificially, then buy at the put wall.

**Implication:** Potential accumulation. The spoofer is using the fake offers to push price to the put wall, where they intend to buy. When they pull the spoof offers and the put wall holds (from genuine GEX defense), the bounce is violent — the spoofer's buying plus the GEX mechanics create a sharp reversal.

**Conviction adjustment:** If the put wall bounce (long) is the thesis, spoof offers at the wall are POTENTIALLY CONFIRMING — the spoofer may be accumulating at the wall. But this is speculative. Do not increase conviction based on this alone. Wait for the spoof offers to be pulled and the genuine defense to appear.

**Example:** Put wall at 20,850. Spoof offers at 20,852-20,860 (just above the wall). The spoofer is pushing price down to the wall. When price reaches 20,850, the spoofer pulls the offers and starts buying. The put wall holds (genuine GEX defense). Price bounces sharply.

---

## Cross-Referencing Spoofs with Options Flow

The most powerful spoof analysis combines the spoof context with the options flow from Massive.com and dark pool from Unusual Whales.

### Coordinated bearish play

**Pattern:** Spoof offers at call wall + put sweeps in options (Massive.com) + dark pool selling (Unusual Whales)

**Interpretation:** The options trader, the dark pool participant, and the spoofer are all working the same bearish thesis. They may be the same entity (a large institution using multiple channels) or independent participants who have reached the same conclusion.

**Conviction:** HIGH. Three independent channels (options flow, dark pool, order book manipulation) all pointing bearish. This is a coordinated bearish play. The call wall will hold or break to the downside.

**Trade:** Short at or near the call wall. The coordinated bearish pressure is the highest conviction short signal.

### Coordinated bullish trap

**Pattern:** Spoof bids at put wall + call sweeps in options (Massive.com) + dark pool buying (Unusual Whales)

**Interpretation:** The spoofer is creating fake support at the put wall while the options and dark pool participants are building long exposure. When the spoofer pulls the fake bids and the put wall holds (from genuine GEX defense), the bounce is violent — the accumulated long exposure unwinds upward.

**Conviction:** HIGH. The spoofer is creating a trap for bears (who see the fake bids and think the put wall is weak), while the genuine participants are building long exposure. When the trap springs (spoof bids pulled, put wall holds), the bears are squeezed.

**Trade:** Long at the put wall. The coordinated bullish setup is the highest conviction long signal.

### Contradictory signals

**Pattern:** Spoof offers at call wall + call sweeps in options (bullish flow)

**Interpretation:** The spoofer is bearish (creating fake resistance at the call wall) but the options flow is bullish (call sweeps). These are contradictory. One of them is wrong, or they're operating on different time horizons.

**Resolution:** Options flow is more time-sensitive and more directly tied to directional positioning. The spoofer may be a short-term HFT trying to slow the rally, while the options buyer is a longer-term participant. Lean toward the options flow signal but note the contradiction. Reduce conviction by 1 level.

---

## Spoof Velocity

How fast does the spoof order get pulled when price approaches?

```python
def compute_spoof_velocity(cancel_ts: float, placed_ts: float,
                            price_at_cancel: float, 
                            spoof_price: float) -> dict:
    """
    Compute how quickly the spoof was pulled relative to price approach.
    """
    duration = cancel_ts - placed_ts
    distance_at_cancel = abs(price_at_cancel - spoof_price)
    tick = 0.25
    ticks_away = distance_at_cancel / tick
    
    if ticks_away <= 2 and duration < 0.1:
        sophistication = 'ULTRA_HFT'  # Pulled within 100ms, 2 ticks away
    elif ticks_away <= 5 and duration < 0.5:
        sophistication = 'HFT'  # Pulled within 500ms, 5 ticks away
    elif ticks_away <= 10 and duration < 2.0:
        sophistication = 'ALGO'  # Pulled within 2 seconds, 10 ticks away
    else:
        sophistication = 'MANUAL'  # Slower, further away
    
    return {
        'duration_seconds': duration,
        'ticks_away_at_cancel': ticks_away,
        'sophistication': sophistication
    }
```

### Velocity interpretation

**ULTRA_HFT (< 100ms, < 2 ticks away):**
The spoofer is a sophisticated HFT algorithm. They're pulling the order with microsecond precision as price approaches. This is extremely difficult to trade against — by the time you see the order, it may already be cancelled. Treat this spoof as noise. Do not adjust conviction based on ultra-HFT spoofs.

**HFT (< 500ms, < 5 ticks away):**
Still a sophisticated algorithm. Hard to trade against. Note the spoof context but do not rely on it for conviction adjustment.

**ALGO (< 2 seconds, < 10 ticks away):**
A slower algorithm or a human-assisted algo. The spoof is detectable and the context is more reliable. Apply the conviction adjustments described above.

**MANUAL (> 2 seconds, > 10 ticks away):**
A human or slow algorithm. The spoof is clearly detectable. The context is most reliable. Apply full conviction adjustments.

---

## Limitations and Reliability

### Why spoofs are less reliable than icebergs

Icebergs require actual fills. The iceberg participant is spending real capital to defend a level. They cannot change their mind without cost — they've already absorbed volume.

Spoofs require no capital. The spoofer can place and cancel orders at zero cost (beyond exchange fees, which are minimal). They can change their mind instantly. A spoofer who was bearish 5 minutes ago may be bullish now.

This asymmetry means:
- Iceberg at GEX level: +1 conviction level (high reliability)
- Spoof at GEX level: ±0 to -1 conviction level (lower reliability, used for context only)

### The "wasn't a spoof" scenario

Sometimes what looks like a spoof is actually a genuine large order that gets filled. If the order is NOT cancelled (it actually trades), re-classify it as a genuine order.

```python
def reclassify_if_filled(order_id: str, fill_ratio: float, 
                          spoof_registry: SpoofDetector):
    """
    If an order that was classified as a potential spoof actually gets filled,
    remove it from the spoof registry and reclassify as genuine.
    """
    if fill_ratio >= 0.5:  # More than 50% filled = genuine order
        spoof_registry.remove_potential_spoof(order_id)
        # This order is now an iceberg candidate (large order, partially filled)
        # Pass to IcebergDetector for further analysis
```

### Regulatory note

Spoofing is illegal. The system detects spoofs for analytical purposes only — to understand the market microstructure and adjust conviction accordingly. The system does not facilitate or encourage spoofing. All detected spoof activity should be logged for potential regulatory reporting if patterns are systematic and egregious.

---

## Integration with the Bias Engine

Spoof context contributes to the DOM component of the directional bias score, but with lower weight than other DOM signals.

### Conviction adjustments

| Spoof Context | Conviction Adjustment |
|---------------|----------------------|
| Spoof offers above call wall (confirming short thesis) | 0 (note in narrative, no conviction change) |
| Spoof bids at call wall (trap for longs) | -1 level if long thesis |
| Spoof bids below put wall (trap for longs) | -1 level if long thesis |
| Spoof offers at put wall (potential accumulation) | 0 (note in narrative, no conviction change) |
| Coordinated spoof + flow + dark pool (same direction) | +1 level (coordinated signal) |
| Spoof opposing options flow | -1 level (contradiction) |

### DOM component contribution

Spoof context contributes ±5 to ±15 to the DOM component score, depending on the context and sophistication level. Ultra-HFT spoofs contribute 0 (too unreliable). Manual spoofs with clear context contribute ±15.

The spoof contribution is always smaller than the iceberg contribution (±15-45) and the defense score contribution (±30-50). Spoofs are supplementary context, not primary signals.

### Output format

In the output (output-format.md), spoof activity is reported in the ALERTS section:

```
[NEW] Spoof bids detected at 20,820 (below put wall) — 3 events, avg size 180 contracts, ALGO sophistication. Bearish context: spoofer creating fake floor below put wall. Conviction reduced by 1 level for long thesis.
```

Or in the narrative:

"Dark pool is showing net selling ($8M) and spoof bids have appeared below the put wall at 20,820 — a coordinated bearish setup. The spoofer is creating a fake floor to trap longs. Conviction reduced to 2/5 for the long thesis. No trade."
