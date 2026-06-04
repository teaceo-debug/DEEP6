# Delta and Cumulative Delta

## Definition

**Delta** = Ask volume minus Bid volume for a single footprint bar. Measures which side dominated that bar.

**Cumulative Delta (Cum Delta)** = Running sum of all deltas from the start of the trading day. Tracks the net directional pressure across the entire session.

## Logic

Delta tells you whether aggressive buyers or aggressive sellers dominated a given bar. In a healthy trend, delta should confirm price direction: bullish bars have positive delta, bearish bars have negative delta.

When delta diverges from price, it signals that the "wrong" side is entering. This is a reversal warning.

Cumulative Delta extends this logic across the session. If price is rising but Cum Delta is falling, sellers are consistently entering on every push up. Price is being propped up by passive buyers, not driven by aggressive buyers. Eventually, price corrects downward to match the Cum Delta direction.

**Delta formula example:**
- Bar 1 delta: +30
- Bar 2 delta: +100
- Bar 3 delta: -50
- Cum Delta after Bar 3: +80

## Step-by-Step Rules

1. Check each bar's delta in the summary panel. Confirm it matches the bar's price direction.
2. Flag any divergence: bullish bar with negative delta, or bearish bar with positive delta.
3. A single divergence bar is a warning. Two or more consecutive divergence bars at an S/R zone is a high-probability reversal signal.
4. Open a 1-minute line chart of Cum Delta overlaid with the 1-minute price chart.
5. At S/R zones, look for divergence between price direction and Cum Delta direction:
   - Price rising + Cum Delta falling at resistance = short confirmation
   - Price falling + Cum Delta rising at support = long confirmation
6. Don't trade Cum Delta divergence in the middle of open space. It's most reliable at established S/R levels.
7. In trending markets, expect delta to confirm price. Divergence in a strong trend is less meaningful than divergence at a key level.
8. In rotational/ranging markets, delta is less reliable. Institutions use both market and limit orders to mask their intentions during accumulation/distribution.

## When to Use

- Confirming trend strength: consistent delta alignment with price = healthy trend.
- Identifying reversal setups at S/R zones: delta/price divergence is the trigger.
- Reading Cum Delta on 1-minute chart as a secondary confirmation for entries on 30-minute setups.
- Filtering out weak setups: if delta doesn't confirm your directional bias, reduce size or skip the trade.

## When NOT to Use

- Don't use delta as a standalone entry signal. It's a confirmation tool, not a setup generator.
- Don't rely on Cum Delta during low-volume periods (pre-market, lunch hour). Thin markets produce noisy delta readings.
- Don't use delta to call reversals in the middle of strong trends. Divergence during a momentum move often resolves with continuation, not reversal.
- Rotational markets: delta is unreliable because institutions deliberately split orders between market and limit to obscure direction.

## NQ-Specific Notes

- NQ's delta is most meaningful during the first 90 minutes of the US session (9:30-11:00 ET) and the afternoon session (2:00-4:00 PM ET).
- Watch for Cum Delta divergence at NQ's key daily levels: prior day high/low, overnight high/low, VWAP, and round numbers.
- NQ often makes a false push through a level (positive delta spike) before reversing. The spike exhausts aggressive buyers, then price drops. This is the "delta exhaustion" pattern.
- A bearish NQ bar with positive delta near support is a strong long signal. Aggressive sellers are entering but being absorbed by passive buyers. When the sellers run out, price snaps up.
- Cum Delta resets at the start of each trading day. Don't carry yesterday's Cum Delta into today's analysis.
