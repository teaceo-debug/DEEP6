# Footprint Bar Anatomy

## Definition

A footprint bar is an enhanced candlestick that shows every executed order at every price level within the bar's time range. Where a standard candle shows only OHLC, a footprint shows the full volume breakdown at each tick.

## Logic

Price moves through levels as buyers and sellers transact. The footprint captures the exact volume traded on each side at each price. This reveals where institutions were active, where one side dominated, and where the market found or rejected value.

Each row in the footprint corresponds to one price level. The row shows:

```
[Bid volume] x [Ask volume]
```

Example: `154 x 84` means 154 contracts traded on the Bid and 84 on the Ask at that price.

**Cell color:**
- Green cell = Ask > Bid (aggressive buyers dominated at that level)
- Red cell = Bid > Ask (aggressive sellers dominated at that level)

**High Volume Node (HVN):** The single price level within a footprint with the highest combined Bid+Ask volume. Marked with a black outline. Every footprint has exactly one HVN.

**Multiple HVN (Multiple Node):** When two or more consecutive footprints share the same HVN price, TD Order Flow highlights those cells in yellow. This marks a strong S/R zone.

**Delta:** Ask total minus Bid total for the entire footprint bar. Displayed in the summary panel below the bar.

**Summary panel** (Dale's configuration): Delta, Cumulative Delta, Volume only. Keep it minimal.

## Step-by-Step Rules

1. Read each row as `Bid x Ask`. Left number = Bid side. Right number = Ask side.
2. Identify the HVN (black outline). Note its price level. This is where the most institutional activity occurred within this bar.
3. Check the bar's delta (summary panel). Positive = Ask dominated. Negative = Bid dominated.
4. Compare delta direction to price direction:
   - Bullish bar + positive delta = normal, trend-confirming
   - Bullish bar + negative delta = warning, sellers entering despite rising price
   - Bearish bar + negative delta = normal, trend-confirming
   - Bearish bar + positive delta = warning, buyers entering despite falling price
5. Look for volume shading. Darker cells = heavier volume = institutional activity. Track these price levels.
6. Check for Multiple Nodes (yellow cells). Mark these as S/R zones on your chart.

## When to Use

- Reading every footprint bar as part of trade analysis.
- Identifying where institutions were active within a bar.
- Confirming or questioning a trend based on delta vs price direction.
- Locating HVNs and Multiple Nodes for S/R zone mapping.

## When NOT to Use

- Don't read footprints in isolation from context. A single bar's anatomy means little without knowing the surrounding trend, S/R levels, and session context.
- Don't treat green cells as "pure buying" or red cells as "pure selling." Both passive and aggressive participants contribute to each side (see passive-vs-active.md).

## NQ-Specific Notes

- NQ footprints on a 30-minute chart are the primary timeframe for Dale's setups. Use 30-minute bars for setup identification, then drop to 1-minute for entry timing.
- NQ trades in 0.25-point increments. Each row in the footprint = one 0.25-point price level.
- HVNs on NQ often cluster near round numbers (e.g., 18000, 18025, 18050) and prior session highs/lows. These are natural institutional reference points.
- A bullish NQ bar with negative delta near a resistance zone is a high-probability short signal. The delta divergence confirms sellers are entering aggressively despite the price push.
- Volume shading on NQ is most meaningful during the first 90 minutes of the US session (9:30-11:00 ET) when institutional order flow is heaviest.
