# Trailing Stop Loss with Order Flow

## The Core Principle

Trail only when aggressive participants are still on your side. The moment order flow turns against you, stop trailing and exit. Don't wait for price to confirm what the footprint already told you.

## Trailing Conditions

**For Longs:** Trail when Buying Imbalances keep appearing in the footprints as price rises. A Buying Imbalance means Ask volume is at least 300% of Bid volume at that price level — aggressive buyers are still hitting the offer. As long as these imbalances continue printing in the direction of your trade, the move has fuel.

**For Shorts:** Trail when Selling Imbalances keep appearing as price falls. Selling Imbalance = Bid volume at least 300% of Ask volume. Aggressive sellers are still hitting the bid.

Use the **5-minute Bid x Ask footprint** for trailing decisions. The 30-minute chart is for context and S/R identification. The 5-minute is where you read the live order flow.

## How to Trail

Move your stop up (for longs) or down (for shorts) as each new footprint bar closes with imbalances in your favor. Don't trail on every tick — wait for bar closes to confirm the imbalance pattern is holding.

A reasonable trailing approach:
- Move SL to just below the low of the most recent 5-minute bar (for longs)
- Move SL to just above the high of the most recent 5-minute bar (for shorts)
- Only move it if that bar showed imbalances in your favor

## Warning Signals: When to Stop and Exit

Stop trailing immediately and exit when any of these appear in the footprint:

**1. Big Limit Order Against You**
A large passive order sitting on the opposite side. For longs: a big limit sell on the Ask. This is an institution defending a level. Price may not get through.

**2. Absorption Against You**
Heavy volumes on both sides of the footprint at the same price level. Your momentum is being absorbed by the opposing side. The move is losing energy.

**3. Aggressive Orders Against You**
Delta flips against your direction. Buyers were in control, now sellers are hitting harder. The aggression has shifted.

**4. Cumulative Delta Divergence Against You**
Price continues moving in your direction but Cumulative Delta is moving the opposite way. Price is being pushed by passive orders, not aggressive ones. The move is unsupported.

## The Critical Multiplier: S/R Zones

Any warning signal becomes significantly more dangerous when it appears at a heavy volume zone or known S/R level. If you're long and approaching a heavy volume zone overhead, and you see absorption or a big limit sell there, don't wait. Exit.

The combination of a warning signal at S/R is the highest-probability reversal scenario in order flow trading. Trailing through it is how winning trades become losers.

## Summary Decision Tree

```
Imbalances continuing in my favor?
  YES → Keep trailing
  NO  → Check for warning signals

Warning signal present?
  NO  → Hold, watch next bar
  YES → Is it at S/R?
          YES → Exit immediately
          NO  → Exit or tighten stop aggressively
```
