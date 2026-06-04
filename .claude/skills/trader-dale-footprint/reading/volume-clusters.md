# Volume Clusters

## Definition

Volume Clusters are areas within the footprint where volume is significantly heavier than surrounding price levels. TD Order Flow software marks them with darker cell shading. The darker the cell, the more volume traded at that price.

## Logic

Institutions don't trade randomly. When an algorithm executes a large position, it leaves a footprint: a concentration of volume at specific price levels. These clusters mark where institutional algorithms were actively buying or selling.

Because institutions return to their own levels (to add, reduce, or defend positions), Volume Clusters become reliable S/R zones. Price tends to react when it revisits a prior cluster.

Volume Clusters work in both display modes:
- **Bid x Ask mode**: shading applies to individual Bid and Ask cells
- **Volume (total) mode**: shading applies to the combined volume cell

The interpretation is the same in both modes. Darker = more significant.

## Step-by-Step Rules

1. Scan the footprint for cells with noticeably darker shading compared to surrounding cells.
2. Note the price level of each cluster. Mark it as a potential S/R zone.
3. Classify the cluster by context:
   - Cluster within an uptrend = institutions adding to longs mid-trend. Acts as support on pullbacks.
   - Cluster within a downtrend = institutions adding to shorts mid-trend. Acts as resistance on bounces.
   - Cluster at a reversal point = institutions aggressively entering at the turn. Strong S/R.
4. When price returns to a prior cluster zone, watch for a reaction. The cluster is your reference level.
5. Combine cluster levels with other S/R tools (HVNs, stacked imbalances, prior day levels) to build a confluence zone.
6. Don't treat every slightly darker cell as a cluster. Look for cells that stand out clearly from their neighbors.

## When to Use

- Building your daily S/R map before the session opens. Identify yesterday's major clusters as today's reference levels.
- During live trading, when price approaches a prior cluster zone, prepare for a reaction.
- Confirming a setup: if your entry zone aligns with a prior volume cluster, the setup has higher conviction.
- Identifying where institutions were active within a trend to anticipate pullback support/resistance.

## When NOT to Use

- Don't use clusters from low-volume sessions (overnight, pre-market) as primary S/R. Thin-market clusters are less reliable.
- Don't treat a cluster as an automatic reversal signal. It's a zone of interest, not a guaranteed turn.
- Don't ignore the broader context. A cluster at a minor level within a strong trend is less significant than a cluster at a major structural level.

## NQ-Specific Notes

- NQ's highest-volume clusters form during the US open (9:30-10:30 ET) and the afternoon session (2:00-4:00 PM ET). These are the most reliable S/R zones.
- NQ clusters near round numbers (18000, 18500, etc.) carry extra weight because retail and institutional orders both concentrate there.
- On a 30-minute NQ chart, a volume cluster that spans multiple consecutive bars at the same price level is equivalent to a Multiple HVN. Treat it as a very strong zone.
- Overnight NQ clusters (Globex session) are relevant but secondary. Use them as context, not primary levels.
- When NQ gaps open above or below a prior session's major cluster, that cluster becomes the first magnet for price to test during the day session.
