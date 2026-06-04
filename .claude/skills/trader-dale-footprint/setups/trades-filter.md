# Setup #3: Trades Filter

---

## Overview

The Trades Filter isolates large single institutional orders from the noise of retail flow. When you set a minimum trade size threshold, the software highlights only the cells where a single order of that size or larger printed. Everything below the threshold stays visible but unhighlighted. What remains highlighted represents institutional intent at a specific price level.

This setup is mechanically very similar to Setup #1 (Volume Clusters), but instead of looking at total volume shading, you're looking at individual large orders. A single 300-lot order in ES tells a different story than 300 lots spread across 50 small trades. The Trades Filter captures that distinction.

This setup REQUIRES Bid x Ask display mode. It does not work in Volumes mode.

---

## Logic Behind the Setup

Large orders don't appear randomly. An institution placing a 300-lot ES order at a specific price is making a deliberate decision. They want to be positioned there. When price returns to that level, the same two forces apply:

1. **Position defense.** The institution that placed the large order is still in that position (or added to it). When price returns, they defend. A 300-lot position is not something you abandon without a fight.

2. **Opposing side closing.** Traders who took the other side of that large order, or who are now positioned against it, recognize the institutional presence and close. Their exits add directional pressure in the same direction as the large order.

The key insight: color does NOT indicate direction. A green (ask-side) large order at a level means buyers were aggressive there. A red (bid-side) large order means sellers were aggressive. But the direction of your trade is determined by which side price approaches the level from, not by the color of the highlighted cell.

---

## Step-by-Step Rules

1. Set your Order Flow chart to display **Bid x Ask** mode.
2. Open the Trades Filter settings. Enable the filter and set the minimum trade size for your instrument (see Key Settings below).
3. Scan the chart for highlighted cells. These are price levels where a single order at or above your threshold printed. Non-highlighted cells are still visible but represent smaller orders.
4. Identify a highlighted area (one or more highlighted cells at a price level or small price range).
5. Confirm that price has moved **away** from the highlighted area. At least 1-2 complete footprint bars must have formed entirely above or below the highlighted area before you consider the setup valid. Use the 30-minute chart.
6. Wait for price to pull back and return to the highlighted area.
7. Enter at the highlighted price level or the beginning of the highlighted zone.
8. Place your stop loss beyond the highlighted area with a small buffer.
9. **Trade the first test only.** Do not take a second test of the same level.

---

## Direction Rules

| Price Approach | Trade Direction |
|---|---|
| Price comes down to the highlighted area from above | Long |
| Price comes up to the highlighted area from below | Short |

**Critical warning:** GREEN highlighted cells do NOT automatically mean Long. RED highlighted cells do NOT automatically mean Short. The color tells you whether the large order was on the ask side (green, aggressive buying) or bid side (red, aggressive selling). But your trade direction is determined purely by which side price is approaching from.

A red (sell-side) large order at a level that price is now approaching from above = Long. The sellers who placed that order are now defending a short position. When price returns from above, they add to shorts or hold, and buyers close longs. Both push price down... wait, no. If price is approaching from above, you're looking for a bounce upward. The sellers at that level placed their orders when price was moving down through it. Now price is pulling back up to test it. The sellers defend by selling again, pushing price back down.

Re-read the direction table. It's simple. Approach from above = Long. Approach from below = Short. Don't overthink the color.

---

## Two Factors That Drive Price

When price returns to a Trades Filter level:

- **The institution defends.** A large single order represents a deliberate position. The institution monitors that level. When price returns, they act again, either adding to the position or defending it.
- **Opposing traders close.** Anyone positioned against a known institutional level recognizes the risk. They close before the institution pushes price away. Their closing orders amplify the move.

The larger the filtered order, the stronger the expected defense. A 500-lot ES order carries more weight than a 300-lot order.

---

## Combining with Other Setups

The Trades Filter works as a standalone setup, but it's also a strong confirmation tool when combined with other setups:

- **Trades Filter + Volume Cluster:** A large single order inside a Volume Cluster = double confirmation. Both institutional volume concentration and a specific large order at the same level.
- **Trades Filter + Multiple Node:** A large order at a Multiple Node level = the HVN pattern is backed by a specific institutional order.
- **Trades Filter + Stacked Imbalances:** A large order within a Stacked Imbalance zone = the imbalance pattern has a specific institutional anchor.

When combining, the primary setup provides the zone, and the Trades Filter confirms institutional presence within it.

---

## Examples Description

**Standalone example:** ES is in an uptrend on the 30-minute chart. One footprint bar has a green highlighted cell at 5,250 (a single 350-lot buy order printed there). Price continues up for 2 bars, then pulls back. When price returns to 5,250, you enter long. The institution that placed the 350-lot order defends the level, and price bounces.

**Combined example:** NQ has a Volume Cluster at 21,100. Within that cluster, the Trades Filter reveals a 40-lot highlighted cell (using NQ-appropriate settings). Price moves away, then pulls back. The combination of cluster + large order at the same level gives higher conviction for the long entry.

---

## When to Use

- Trades Filter is enabled and calibrated for the instrument
- A highlighted cell (large single order) is visible at a clear price level
- Price has moved away from the level (1-2+ complete bars above or below)
- Context supports the trade: trend, pre-trend, or rejection
- First test of the level

---

## When NOT to Use

- Trades Filter threshold is not calibrated for the instrument (too high = no signals, too low = too many signals)
- The highlighted area has already been tested once
- No clear directional context (choppy, ranging market with no trend or rejection)
- Price hasn't moved away from the level yet
- The highlighted cell is very old (multiple sessions ago) and market structure has changed

---

## Key Settings

| Setting | Value |
|---|---|
| Display mode | Bid x Ask (required) |
| Chart timeframe | 30-minute |
| Trades Filter | Enabled |
| EUR Futures minimum size | 25 lots |
| ES minimum size | 300+ lots |
| NQ minimum size | Calibrate to ~5-10 signals/day |
| Target signal frequency | 5-10 highlighted areas per day |
| First test only | Yes |

### Calibrating the Threshold

The goal is 5-10 meaningful signals per trading day. If you're seeing 20+ highlighted cells, raise the threshold. If you're seeing 1-2, lower it. The right threshold varies by instrument, session, and current market volatility.

Start with the instrument-specific defaults above, then adjust based on what you observe over several sessions. During high-volatility periods (earnings, FOMC), you may need to raise the threshold temporarily because large orders are more common.

---

## NQ/ES-Specific Notes

- ES has significantly higher liquidity than NQ. A 300-lot ES order is meaningful but not rare. A 300-lot NQ order would be enormous. Calibrate separately for each instrument.
- NQ's threshold will be much lower than ES in absolute lot terms. Start around 25-50 lots for NQ and adjust based on signal frequency.
- During the RTH open (9:30-10:00 ET), large orders are common as institutions establish positions. The Trades Filter will show more highlighted cells during this window. Be selective and look for the clearest levels.
- Overnight sessions have lower volume. Large orders during overnight hours carry more relative weight because they stand out more against the thin background volume.
- NQ round numbers (21,000, 21,050, etc.) frequently attract large institutional orders. When a Trades Filter highlight appears at a round number, treat it as higher conviction.
- If you see multiple large orders clustered within a 2-3 tick range, treat the entire range as the level rather than trying to pinpoint a single tick entry.
