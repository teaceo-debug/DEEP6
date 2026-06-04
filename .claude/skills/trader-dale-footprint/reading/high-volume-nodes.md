# High Volume Nodes and Multiple Nodes

## Definition

**High Volume Node (HVN):** The single price level within one footprint bar with the highest combined Bid+Ask volume. TD Order Flow marks it with a black outline. Every footprint has exactly one HVN.

**Multiple Node (Multiple HVN):** When two or more consecutive footprint bars share the same HVN price level. TD Order Flow highlights these cells in yellow. Also called a Double Node (2 bars), Triple Node (3 bars), etc.

## Logic

The HVN is the price where the most trading occurred within a bar. It's the market's "fairest" price for that period. Institutions transacted most heavily there.

When consecutive bars share the same HVN price, it means the market repeatedly found that price to be the most active level across multiple time periods. This is not random. It signals that institutions were consistently transacting at that exact price, making it a strong reference point.

The more bars that share the same HVN, the stronger the S/R zone:
- Double Node (2 bars) = moderate S/R
- Triple Node (3 bars) = strong S/R
- 4+ bars = very strong S/R

Price tends to react when it returns to a Multiple Node zone. It may bounce, consolidate, or break through with increased volume.

## Step-by-Step Rules

1. On each footprint bar, identify the HVN (black outline). Note its price.
2. Check the adjacent bars. If the next bar's HVN is at the same price, you have a Double Node.
3. Continue checking consecutive bars. Count how many share the same HVN price.
4. Mark the Multiple Node price level as an S/R zone. The more bars that share it, the stronger the zone.
5. Yellow highlighting in TD Order Flow confirms a Multiple Node. Don't manually count if the software marks it.
6. When price approaches a Multiple Node zone from above, treat it as support. From below, treat it as resistance.
7. A break through a Multiple Node zone with strong delta and volume confirms the move. A rejection with delta divergence confirms the reversal.
8. Combine Multiple Nodes with stacked imbalances and volume clusters for highest-conviction S/R zones.

## When to Use

- Building your pre-session S/R map. Identify all Multiple Nodes from the prior session and overnight.
- During live trading, when price approaches a Multiple Node, prepare for a reaction.
- Confirming trade entries: if your setup aligns with a Multiple Node, it has higher conviction.
- Setting profit targets: Multiple Nodes ahead of your trade direction are natural TP levels.
- Setting stop losses: place stops beyond a Multiple Node zone, not inside it.

## When NOT to Use

- Don't treat a single HVN (no multiple) as a strong S/R zone on its own. It's a reference point, not a major level.
- Don't ignore the trend context. A Multiple Node in the middle of a strong trend may be broken cleanly. Wait for confirmation before fading it.
- Don't use Multiple Nodes from very low-volume sessions (overnight, holiday) as primary levels. Low volume means fewer institutional participants, so the node is less significant.

## NQ-Specific Notes

- On a 30-minute NQ chart, Multiple Nodes that form during the US session (9:30 AM - 4:00 PM ET) are the most reliable S/R zones.
- NQ Multiple Nodes near round numbers (18000, 18250, 18500) are especially significant because they combine institutional volume concentration with psychological price levels.
- A Triple Node or higher on NQ's 30-minute chart is a major level. Expect at least a pause, often a full reversal, when price returns to it.
- NQ's overnight session (Globex) frequently forms Double Nodes near the prior day's close. These act as the first S/R test when the US session opens.
- When NQ breaks through a Multiple Node with a large-delta bar, the node often flips: prior support becomes resistance, prior resistance becomes support. Watch for the retest.
