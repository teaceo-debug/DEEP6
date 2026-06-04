# Imbalances and Stacked Imbalances

## Definition

**Imbalance:** A price level where one side of the footprint is 300% or more stronger than the other side. Default threshold is 300% (configurable in TD Order Flow settings). Marked in blue on the dominant side.

**Stacked Imbalances:** Three or more imbalances stacked vertically (consecutive price levels within the same footprint). Stacked Buying Imbalances are highlighted green. Stacked Selling Imbalances are highlighted red.

## Logic

Imbalances are read **diagonally**, not horizontally. This is the correct way to compare footprint cells. The diagonal comparison reflects how the order book actually works: a buyer at one price is matched against a seller at the adjacent price.

**Buying Imbalance:** Ask at price N >= 300% of Bid at price N-1 (one tick below). Marked in blue on the Ask side.

**Selling Imbalance:** Bid at price N >= 300% of Ask at price N+1 (one tick above). Marked in blue on the Bid side.

A single imbalance shows one side briefly dominating. Stacked imbalances show one side completely overwhelming the other across multiple consecutive price levels. This is the signature of aggressive institutional entry.

**Stacked Buying Imbalances (green):** Aggressive buyers swept through multiple price levels without resistance. Acts as support on pullbacks.

**Stacked Selling Imbalances (red):** Aggressive sellers swept through multiple price levels without resistance. Acts as resistance on bounces.

Stacked imbalances appear most often at the start of strong trends and within trends during impulsive moves. They're rare in rotational markets.

## Step-by-Step Rules

1. Confirm TD Order Flow imbalance settings: trigger percentage = 300% (default), cluster size = 3 (default for stacked), minimum volume filter as appropriate for the instrument.
2. Scan footprints for blue-marked cells. These are individual imbalances.
3. Check if three or more blue cells are stacked vertically within the same footprint. If yes, it's a Stacked Imbalance.
4. Identify the color: green = stacked buying (support zone), red = stacked selling (resistance zone).
5. Mark the price range of the stacked imbalance as an S/R zone. The zone spans from the lowest to highest imbalance price in the stack.
6. When price pulls back to a green stacked imbalance zone, look for long entries. The zone should hold.
7. When price bounces into a red stacked imbalance zone, look for short entries. The zone should hold.
8. A clean break through a stacked imbalance zone with strong opposing delta signals the zone has failed. Don't fade it.
9. Combine stacked imbalances with Multiple Nodes and volume clusters for highest-conviction S/R zones.

## When to Use

- Identifying S/R zones formed during impulsive moves. Stacked imbalances mark where institutions entered aggressively.
- Setting profit targets: stacked imbalances ahead of your trade direction are natural TP levels.
- Confirming trend direction: stacked buying imbalances in an uptrend confirm bullish momentum.
- Filtering entries: only take longs at green stacked imbalance support, only take shorts at red stacked imbalance resistance.

## When NOT to Use

- Don't use single imbalances (not stacked) as primary S/R zones. They're context clues, not major levels.
- Don't fade a stacked imbalance zone that's already been broken and retested. Once broken, it loses its S/R significance.
- Don't use stacked imbalances from very low-volume sessions. The 300% threshold is easier to hit with thin volume, making the signal less meaningful.
- Rotational/ranging markets: imbalances form and fail quickly. Stacked imbalances are most reliable in trending conditions.

## NQ-Specific Notes

- NQ's minimum volume filter for imbalances should be set high enough to filter out noise. During the US session, a minimum of 50-100 contracts per cell is reasonable. Adjust for overnight sessions.
- Stacked imbalances on NQ's 30-minute chart are the most reliable. On 1-minute charts, they form and break too quickly to be useful as S/R zones.
- NQ frequently forms stacked selling imbalances at the top of morning rallies (9:30-10:30 ET) and stacked buying imbalances at the bottom of morning selloffs. These become the key levels for the rest of the day.
- When NQ's stacked imbalance zone aligns with a prior day's high/low or a round number, the confluence makes it a very high-conviction level.
- The 300% default threshold works well for NQ. Lowering it to 200% generates more signals but more false positives. Raising it to 400%+ gives fewer but higher-quality signals.
