# Trades Filter

## Definition

The Trades Filter is a TD Order Flow feature that hides all executed trades below a set minimum size, displaying only the largest single-order executions. Trades below the threshold show as "0." Trades at or above the threshold show their actual volume.

This is a unique TD Order Flow feature not available in most footprint software.

## Logic

Institutions prefer to hide their activity by splitting large orders into many small ones (Iceberg orders). This makes their footprint look like normal retail flow. However, when they need to enter quickly, they sometimes execute a single large market order. Speed matters more than concealment in those moments.

The Trades Filter catches these large single-order executions. When a big number appears through the filter, it means an institution entered with one aggressive order at that price. They weren't hiding. They needed in fast.

Heavy Trades Filter volume at a price level = strong S/R zone. Institutions marked that price as significant enough to enter aggressively.

**Calibration rule:** Set the filter to produce approximately 5-10 signals per day. Too many signals = threshold too low (noise). Too few = threshold too high (missing real signals).

**Instrument-specific thresholds:**
- EUR Futures (6E): 25 lots
- ES (S&P 500 Futures): 300+ lots
- NQ: calibrate to session volume (see NQ-Specific Notes)

## Step-by-Step Rules

1. Open the 30-minute chart in Bid x Ask mode.
2. Set the Trades Filter minimum to the appropriate threshold for your instrument.
3. Scan for cells showing large numbers (not "0"). These are your signals.
4. Note the price level of each filtered trade. Mark it as a potential S/R zone.
5. Classify by context:
   - Large Bid-side filtered trade = aggressive seller entered with a single large order. Potential resistance.
   - Large Ask-side filtered trade = aggressive buyer entered with a single large order. Potential support.
6. Adjust the threshold if you're seeing more than 10 signals per day (raise it) or fewer than 5 (lower it).
7. Account for session volume differences: EU session (3:00-9:30 AM ET) has lower volume than US session (9:30 AM - 4:00 PM ET). You may need a lower threshold for EU session signals.
8. Combine Trades Filter levels with Multiple Nodes and stacked imbalances. Confluence = higher conviction.

## When to Use

- Building your S/R map: Trades Filter levels from prior sessions mark where institutions entered aggressively.
- Confirming setups: if your entry zone has a prior Trades Filter signal, the zone has institutional backing.
- Identifying where institutions couldn't hide their activity. These are the most transparent institutional footprints.
- Spotting absorption: a large Trades Filter signal on the Bid at support means an institution absorbed aggressive sellers with a single large buy order.

## When NOT to Use

- Don't use Trades Filter as a standalone entry signal. It marks S/R zones, not entry triggers.
- Don't ignore the threshold calibration. A poorly calibrated filter produces meaningless signals.
- Don't use Trades Filter signals from overnight/Globex sessions as primary levels during the US session. Volume is too thin overnight for the filter to be meaningful at the same threshold.
- Don't confuse Trades Filter with Iceberg detection. The filter catches single large orders. Iceberg orders (split into many small ones) won't appear through the filter. Iceberg detection requires different analysis.

## NQ-Specific Notes

- NQ's Trades Filter threshold needs calibration per session. During the US open (9:30-11:00 ET), NQ trades with very high volume. A threshold of 100-200 contracts may be appropriate. During quieter afternoon periods, 50-100 contracts may be sufficient.
- Start with a threshold that gives 5-10 signals on a typical NQ trading day. Review after one week and adjust.
- NQ Trades Filter signals near round numbers (18000, 18500, etc.) are especially significant. Institutions entering aggressively at round numbers signals strong conviction about that level.
- A Trades Filter signal on the Ask side at NQ support (aggressive buyer, single large order) is one of the strongest absorption signals available. It means an institution needed to buy immediately and didn't bother hiding it.
- EU session NQ (3:00-9:30 AM ET) has roughly 20-30% of US session volume. Lower your threshold proportionally for EU session analysis.
