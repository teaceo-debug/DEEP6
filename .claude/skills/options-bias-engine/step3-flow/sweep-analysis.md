# Sweep Analysis — Options Sweep Detection and Interpretation

## Purpose

An options sweep is the most urgent signal in the flow tape. It represents a participant who needs exposure immediately and is willing to pay for it across multiple exchanges simultaneously. Sweeps are the loudest signal in the options market. But not all sweeps are equal. This document covers the mechanics of sweep detection, the classification system by conviction level, the cascade pattern, and the cross-validation protocol between Massive.com and Unusual Whales.

Data sources:
- **Massive.com**: Primary sweep detection. Real-time multi-exchange sweep identification.
- **Unusual Whales**: Secondary sweep detection and dark pool cross-validation.
- **FlashAlpha**: GEX context for interpreting which sweeps matter (at which strikes).
- **Rithmic MBO**: Order book impact of sweeps. DOM response to sweep flow.

---

## What Defines a Sweep

A sweep is a multi-exchange simultaneous execution. The buyer (or seller) lifts every offer (or hits every bid) across 5 or more exchanges within 500 milliseconds. This is the signature of urgency.

### The Mechanics

Options trade on multiple exchanges simultaneously: CBOE, PHLX, ISE, AMEX, BOX, MIAX, and others. Each exchange has its own order book with resting orders at various prices.

A normal options trade executes on a single exchange at the best available price. The buyer sends an order to one exchange, gets filled, and is done.

A sweep is different. The buyer sends orders to ALL exchanges simultaneously, lifting every offer at every price level until the desired quantity is filled. This means:
1. The buyer is willing to pay above the best price to get filled immediately.
2. The buyer doesn't care about slippage — they need the exposure NOW.
3. The buyer is signaling urgency. Something is happening or about to happen.

### Why Sweeps Signal Urgency

The cost of a sweep vs a normal trade:
- Normal trade: Best bid/ask spread, single exchange.
- Sweep: Multiple price levels across multiple exchanges. The buyer pays the ask at each level, which may be progressively higher.

A sweep on a liquid option might cost 5-15 cents per contract more than a patient limit order. On 5,000 contracts, that's $25,000-$75,000 in extra cost. The sweeper is paying this premium because the information value of the trade exceeds the slippage cost.

### Sweep vs Block

A sweep is aggressive (public exchange, multi-exchange). A block is patient (dark pool or negotiated, single large trade).

| Characteristic | Sweep | Block |
|----------------|-------|-------|
| Execution | Multi-exchange, simultaneous | Single exchange or dark pool |
| Speed | < 500ms | Minutes to hours |
| Slippage | High (pays up) | Low (negotiated) |
| Signal | URGENCY | CONVICTION |
| Visibility | Immediate (public tape) | Delayed (dark pool reporting) |
| Size | 500-50,000 contracts | 2,000-100,000 contracts |

Both are directional signals, but they have different character. Sweeps say "I need this NOW." Blocks say "I'm building a large position methodically."

---

## Sweep Classification by Conviction Level

Not all sweeps are equal. Classification requires evaluating four dimensions: size, premium, expiry, and strike.

### Dimension 1: Size (Contract Count)

| Size | Classification | Signal Weight |
|------|---------------|---------------|
| < 500 contracts | Noise | 0 (ignore) |
| 500-1,000 contracts | Small sweep | 0.2 |
| 1,000-5,000 contracts | Moderate sweep | 0.5 |
| 5,000-10,000 contracts | Large sweep | 0.8 |
| 10,000+ contracts | Massive sweep | 1.0 |

**Why size matters**: A 500-contract sweep could be a retail trader with a large account. A 10,000-contract sweep is institutional. The signal weight scales with size because larger sweeps represent more capital at risk and more conviction.

### Dimension 2: Premium (Dollar Value)

| Premium | Classification | Signal Weight |
|---------|---------------|---------------|
| < $500K | Noise | 0 (ignore) |
| $500K - $1M | Small | 0.2 |
| $1M - $5M | Moderate | 0.5 |
| $5M - $10M | Significant | 0.8 |
| $10M+ | Institutional | 1.0 |

**Why premium matters**: A 10,000-contract sweep on cheap OTM options might only be $1M in premium. A 1,000-contract sweep on expensive ATM options might be $5M. Premium normalizes for the option's price and reflects the actual capital at risk.

### Dimension 3: Expiry (DTE)

| Expiry | Classification | Signal Weight for Intraday Bias |
|--------|---------------|--------------------------------|
| 0DTE | Same-day bet | 1.0 (maximum intraday signal) |
| 1-5 DTE (weekly) | Short-term bet | 0.7 |
| 6-21 DTE (monthly) | Medium-term bet | 0.4 |
| 22-90 DTE (quarterly) | Long-term positioning | 0.2 |
| 90+ DTE (LEAPS) | Portfolio construction | 0.0 (ignore for intraday) |

**Why expiry matters**: A 0DTE sweep is the highest-conviction intraday bet. The buyer is saying "I believe price moves in this direction TODAY." A monthly sweep is positioning for the next few weeks — it's a signal, but not an intraday signal.

**DTE-adjusted gamma**: The intraday signal weight should be adjusted by the DTE-normalized gamma:
```
gamma_weight = 1 / sqrt(DTE + 0.5)  # +0.5 to avoid division by zero for 0DTE
```

This gives 0DTE sweeps approximately 1.4x the weight of 1DTE sweeps and 3x the weight of 5DTE sweeps.

### Dimension 4: Strike (Moneyness)

| Strike | Classification | Signal Type |
|--------|---------------|-------------|
| Deep ITM (delta > 0.80) | Delta substitute | Strong directional (synthetic stock) |
| ATM (delta 0.40-0.60) | Maximum gamma bet | Directional + gamma |
| Slightly OTM (delta 0.20-0.40) | Leveraged directional | Directional |
| Far OTM (delta < 0.10) | Lottery or tail hedge | Weak directional or hedging |

**ATM sweeps**: The highest-conviction directional signal. The buyer is paying for maximum gamma exposure. They expect a move and want to profit from the acceleration.

**Deep ITM sweeps**: The buyer wants delta exposure without the gamma. This is a synthetic stock position — they're using options as a cheaper alternative to buying/selling the underlying. Strong directional signal.

**Far OTM sweeps**: Ambiguous. Could be a lottery ticket (speculative, low conviction) or a tail hedge (not directional). Require additional context (dark pool, DOM) to classify.

### Composite Sweep Score

```
sweep_score = size_weight × premium_weight × expiry_weight × strike_weight

# Normalize to 0-1 range
sweep_score = (size_weight + premium_weight + expiry_weight + strike_weight) / 4

# Direction
if call_sweep:
    directional_score = +sweep_score
elif put_sweep:
    directional_score = -sweep_score
```

**Example**:
- 5,000-contract call sweep (size_weight = 0.8)
- $8M premium (premium_weight = 0.8)
- 0DTE expiry (expiry_weight = 1.0)
- ATM strike (strike_weight = 1.0)
- sweep_score = (0.8 + 0.8 + 1.0 + 1.0) / 4 = 0.9
- directional_score = +0.9 (strong bullish)

---

## Sweep Cascades — The Strongest Flow Signal

A sweep cascade is 3 or more sweeps in the same direction within 5 minutes, with escalating size. This is the strongest flow signal in the options market.

### Cascade Definition

**Minimum requirements**:
- 3+ sweeps in the same direction (all calls or all puts).
- All within a 5-minute window.
- Each sweep at least 500 contracts.
- Total premium: $5M+ across all sweeps in the cascade.

**Maximum conviction cascade**:
- 5+ sweeps in the same direction.
- Within 3 minutes.
- Each sweep larger than the previous (escalating size).
- Total premium: $20M+.
- All at ask side (bought, not sold).

### Why Cascades Are the Strongest Signal

A single sweep could be a one-off trade. A cascade means someone is building a position urgently and the market hasn't caught up yet.

The escalating size pattern is particularly significant. If the first sweep is 1,000 contracts, the second is 2,000, and the third is 3,500, the buyer is increasing size as they go. This means:
1. They're not getting the fill they want at the initial size.
2. They're willing to pay more and take more risk.
3. The information value of the trade is increasing (they're more confident as they go).

### Cascade Impact on Price

A cascade typically moves price within 5-15 minutes. The price impact is proportional to the total premium:
- $5M cascade: 10-20 NQ point move expected.
- $15M cascade: 30-60 NQ point move expected.
- $30M+ cascade: 60-150 NQ point move expected.

These are rough estimates. The actual price impact depends on the regime (positive gamma dampens, negative gamma amplifies) and the order book depth.

### Cascade Failure

A cascade that doesn't move price within 15 minutes has failed. This means:
1. Someone is absorbing the buying (selling into the cascade).
2. The cascade is being offset by opposing flow.
3. The information in the cascade was wrong or already priced in.

A failed cascade is a bearish signal (if the cascade was bullish) or a bullish signal (if the cascade was bearish). The absorption is the signal.

---

## Sweep vs Block: Cross-Validation

Sweeps and blocks are detected independently by Massive.com and Unusual Whales. When both detect the same directional signal, conviction is maximum.

### Cross-Validation Protocol

**Step 1**: Identify a sweep on Massive.com.
- Note: direction (call/put), size, premium, expiry, strike.

**Step 2**: Check Unusual Whales for a corresponding block or dark pool print.
- Same direction (call/put).
- Same approximate time (within 5 minutes).
- Same approximate strike or nearby strike.

**Step 3**: Classify the cross-validation result.

| Massive.com | Unusual Whales | Classification |
|-------------|----------------|----------------|
| Call sweep | Dark pool buying | CONFIRMED BULLISH (maximum conviction) |
| Call sweep | No dark pool activity | BULLISH (moderate conviction) |
| Call sweep | Dark pool selling | CONFLICTED (reduce conviction) |
| Put sweep | Dark pool selling | CONFIRMED BEARISH (maximum conviction) |
| Put sweep | No dark pool activity | BEARISH (moderate conviction) |
| Put sweep | Dark pool buying | CONFLICTED (reduce conviction) |

**Conflicted signals**: When Massive.com shows a sweep in one direction and Unusual Whales shows dark pool in the opposite direction, the dark pool is almost always the smarter signal. Reduce conviction on the sweep. The sweep may be a hedge or a position adjustment, not a directional bet.

### Why Both Sources Matter

Massive.com detects sweeps on public exchanges. These are visible to everyone. The sweeper knows their activity is visible.

Unusual Whales detects dark pool prints. These are hidden from the public tape (with a delay). The dark pool participant is trying to hide their activity.

When both agree, it means:
1. The public sweep is genuine (not a hedge or adjustment).
2. The dark pool participant is also positioned in the same direction.
3. Two independent institutional participants agree on the direction.

This is the highest-conviction signal available from flow data.

---

## False Sweep Signals

Not every sweep is a genuine directional bet. Understanding false sweeps prevents costly misclassification.

### Type 1: Hedge Adjustment Sweep

**Characteristics**:
- Sweep is immediately offset by opposing flow within 5 minutes.
- Example: Large call sweep followed immediately by a large put sweep of similar size.
- The net premium after both sweeps is near zero.

**Cause**: An institution is adjusting a hedge. They bought calls to hedge a short position, then realized they over-hedged and sold puts to rebalance. The net effect is neutral.

**Detection**: Monitor net premium in the 5 minutes after a sweep. If net premium returns to near zero, the sweep was a hedge adjustment.

### Type 2: Roll Sweep

**Characteristics**:
- Sweep at one strike is accompanied by an opposing sweep at a different strike.
- Example: Call sweep at 21,000 strike + call sell at 20,800 strike.
- The institution is rolling their position from one strike to another.

**Cause**: An institution is rolling their options position to a different strike (usually to maintain a specific delta or to take profit on the old strike).

**Detection**: Look for simultaneous opposing sweeps at different strikes. If the net delta of both sweeps is near zero, it's a roll.

### Type 3: Expiry Roll Sweep

**Characteristics**:
- Sweep at one expiry is accompanied by an opposing sweep at a different expiry.
- Example: Call sweep at weekly expiry + call sell at monthly expiry.
- The institution is rolling from one expiry to another.

**Cause**: An institution is rolling their position from a near-expiry to a far-expiry (or vice versa) to maintain their position without taking delivery.

**Detection**: Look for simultaneous opposing sweeps at different expiries. If the net premium is near zero, it's an expiry roll.

### Type 4: Algorithmic Sweep

**Characteristics**:
- Sweep is very small (< 500 contracts).
- Sweep is at a far OTM strike.
- Sweep is part of a regular pattern (same time every day, same size).

**Cause**: An algorithmic trading system is executing a regular options strategy (e.g., daily delta hedging, systematic covered call writing).

**Detection**: Pattern recognition. If the same sweep appears at the same time every day, it's algorithmic. Ignore.

### Type 5: Market Maker Sweep

**Characteristics**:
- Sweep is immediately followed by an opposing sweep of similar size.
- The two sweeps are at the same strike and expiry.
- The net effect is near zero.

**Cause**: A market maker is adjusting their inventory. They swept one side to rebalance their book.

**Detection**: Look for immediate opposing sweeps. If the round-trip happens within 30 seconds, it's a market maker adjustment.

---

## Sweep Impact on GEX Structure

A large sweep doesn't just signal direction — it changes the GEX structure. This is the second-order effect of sweeps.

### Call Sweep Impact on GEX

A large call sweep creates new call OI at the swept strike. This:
1. Increases call gamma at that strike.
2. Potentially shifts the call wall to the swept strike (if the swept strike now has more gamma than the prior call wall).
3. Creates a new level that didn't exist before the sweep.

**Example**:
- Prior call wall: 21,000 strike (10,000 OI).
- Large call sweep: 5,000 contracts at 21,200 strike.
- New call OI at 21,200: 5,000 contracts.
- If 5,000 OI at 21,200 has more gamma than 10,000 OI at 21,000 (possible if 21,200 is closer to spot), the call wall shifts to 21,200.

**Monitoring**: After a large call sweep, poll FlashAlpha within 15-30 minutes to see if the call wall has shifted.

### Put Sweep Impact on GEX

Same logic. A large put sweep creates new put OI at the swept strike, potentially shifting the put wall.

**Example**:
- Prior put wall: 20,500 strike (8,000 OI).
- Large put sweep: 4,000 contracts at 20,300 strike.
- New put OI at 20,300: 4,000 contracts.
- If 4,000 OI at 20,300 has more gamma than 8,000 OI at 20,500, the put wall shifts to 20,300.

**Monitoring**: After a large put sweep, poll FlashAlpha within 15-30 minutes to see if the put wall has shifted.

### Sweep Impact on the Gamma Flip

A very large sweep can shift the gamma flip. If a massive put sweep creates enough put OI at a high strike, the cumulative GEX zero-crossing moves upward (the flip rises toward spot).

**Monitoring**: After a sweep > $20M premium, poll FlashAlpha immediately to check if the flip has moved.

---

## Order Book Response to Sweeps

The order book (Rithmic MBO) responds to sweeps in predictable ways. Understanding this response helps confirm or deny the sweep's directional signal.

### Immediate Response (0-30 seconds after sweep)

A genuine directional sweep causes immediate order book changes:
- **Bullish sweep**: Bids stack in NQ futures. Offers thin. The book becomes bid-heavy.
- **Bearish sweep**: Offers stack in NQ futures. Bids thin. The book becomes ask-heavy.

If the order book doesn't respond to a sweep within 30 seconds, the sweep may be a false signal (hedge adjustment, roll, etc.).

### Sustained Response (1-5 minutes after sweep)

A genuine directional sweep causes sustained order book changes:
- **Bullish sweep**: Icebergs appear on the bid. Resting buy orders refresh as they're consumed.
- **Bearish sweep**: Icebergs appear on the ask. Resting sell orders refresh as they're consumed.

If the order book response fades within 1 minute (bids thin, offers return), the sweep was absorbed. This is a bearish signal (if the sweep was bullish) or a bullish signal (if the sweep was bearish).

### Price Response (5-15 minutes after sweep)

A genuine directional sweep causes price movement within 5-15 minutes:
- **Bullish sweep**: NQ price rises 10-50 points within 15 minutes.
- **Bearish sweep**: NQ price falls 10-50 points within 15 minutes.

If price doesn't move within 15 minutes, the sweep has failed. The information in the sweep was absorbed by the market.

---

## Sweep Monitoring Protocol

### Real-Time Monitoring (Massive.com)

Set up Massive.com to alert on:
- Any sweep > 1,000 contracts.
- Any sweep > $2M premium.
- Any 0DTE sweep > 500 contracts.

For each alert:
1. Record: direction, size, premium, expiry, strike, time.
2. Compute sweep score (see above).
3. Check Unusual Whales for dark pool cross-validation.
4. Check Rithmic DOM for order book response.
5. Classify: genuine directional, false signal, or ambiguous.

### Cascade Monitoring

Track sweep direction and size in a rolling 5-minute window:
```python
def detect_cascade(sweeps, window_minutes=5):
    """
    sweeps: list of (time, direction, size, premium) tuples
    Returns: (cascade_detected, direction, total_premium, escalating)
    """
    recent = [s for s in sweeps if s.time > now - window_minutes * 60]
    
    call_sweeps = [s for s in recent if s.direction == 'call']
    put_sweeps = [s for s in recent if s.direction == 'put']
    
    if len(call_sweeps) >= 3:
        total_premium = sum(s.premium for s in call_sweeps)
        escalating = all(call_sweeps[i].size < call_sweeps[i+1].size 
                        for i in range(len(call_sweeps)-1))
        return True, 'bullish', total_premium, escalating
    
    if len(put_sweeps) >= 3:
        total_premium = sum(s.premium for s in put_sweeps)
        escalating = all(put_sweeps[i].size < put_sweeps[i+1].size 
                        for i in range(len(put_sweeps)-1))
        return True, 'bearish', total_premium, escalating
    
    return False, None, 0, False
```

### Post-Sweep GEX Update

After any sweep > $10M premium:
1. Poll FlashAlpha within 15-30 minutes.
2. Check if the call wall, put wall, or gamma flip has shifted.
3. Update level map if any level has moved.

---

## Cross-Reference

- For flow state classification: `flow-interpretation.md`
- For opening vs closing distinction: `opening-vs-closing.md`
- For expiry intent: `expiry-intent.md`
- For dark pool cross-validation: `dark-pool-reading.md`
- For GEX level updates after sweeps: `../step2-levels/wall-dynamics.md`
- For order book confirmation: Rithmic MBO integration
