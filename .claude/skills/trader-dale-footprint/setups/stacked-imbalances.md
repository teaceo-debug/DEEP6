# Setup #4: Stacked Imbalances

---

## Overview

An imbalance occurs when the bid volume and ask volume at a price level within a footprint bar are significantly different from each other. The software flags these automatically when the ratio exceeds a set threshold (default: 300%, meaning one side is 3x the other). A single imbalance is interesting. Three or more consecutive imbalances stacked vertically at adjacent price levels within the same bar or across bars is a Stacked Imbalance, and that's a high-conviction institutional signal.

Stacked Buying Imbalances (ask side dominates) are highlighted green and act as support. Stacked Selling Imbalances (bid side dominates) are highlighted red and act as resistance. When price returns to these zones, the same institutional logic applies: position holders defend, opposing side closes.

This setup REQUIRES Bid x Ask display mode.

---

## Logic Behind the Setup

A single imbalance could be noise. Three or more stacked imbalances at consecutive price levels represent a sustained, directional institutional push through a price range. Buyers (or sellers) were so aggressive that they overwhelmed the opposing side across multiple price levels in sequence.

Two factors drive price away from a Stacked Imbalance zone on retest:

1. **Position defense.** The institutions that drove the imbalanced move built positions as they pushed through those levels. When price returns to the zone, they defend. Buyers who created stacked buying imbalances will buy again when price pulls back to that zone.

2. **Opposing side closing.** Traders positioned against the imbalance zone recognize the institutional aggression and close their positions when price approaches. Sellers closing longs at a green zone add buying pressure. Buyers closing shorts at a red zone add selling pressure.

The stacking of imbalances across multiple price levels means the institutional presence is spread across a range, not just a single tick. This makes the zone more robust than a single-level signal.

---

## Step-by-Step Rules

1. Set your Order Flow chart to display **Bid x Ask** mode.
2. Ensure imbalances are enabled in your software settings (see Key Settings below).
3. Look for **3 or more consecutive imbalances** stacked vertically at adjacent price levels. The software highlights these automatically:
   - **Green zone** = Stacked Buying Imbalances = potential support
   - **Red zone** = Stacked Selling Imbalances = potential resistance
4. Confirm the context. The Stacked Imbalance must form in one of these situations:
   - Within a running trend
   - Before a trend begins (at the base of a move)
   - Within a strong one-way directional move (doesn't need to be a multi-bar trend, a single aggressive move is sufficient)
5. Confirm that price has moved **away** from the Stacked Imbalance zone. At least 1-2 complete footprint bars must have formed entirely above (green zone) or below (red zone) the zone.
6. Wait for price to pull back and return to the Stacked Imbalance zone.
7. Enter at the edge of the zone closest to where price is approaching from.
8. Place your stop loss beyond the far edge of the zone with a small buffer.
9. **Trade the first test only.**

---

## Direction Rules

| Zone Color | Price Approach | Trade Direction |
|---|---|---|
| Green (Buying Imbalances) | Price comes down to the zone from above | Long |
| Red (Selling Imbalances) | Price comes up to the zone from below | Short |

Green zones are support. Price approaches from above, you go Long.
Red zones are resistance. Price approaches from below, you go Short.

---

## Two Factors That Drive Price

When price returns to a Stacked Imbalance zone:

- **Aggressive buyers (green zone) or sellers (red zone) defend.** They pushed through multiple price levels with overwhelming force. They're positioned across that entire range. When price returns, they act again.
- **Opposing traders close.** Anyone fighting the imbalance zone exits before the institutional side pushes price away again. Their exits amplify the move.

The more imbalances stacked (3 is minimum, 5+ is high conviction), the stronger the expected reaction. A zone spanning 10 price levels of consecutive imbalances is a major institutional footprint.

---

## Examples Description

**Uptrend example:** NQ is trending up on the 30-minute chart. One footprint bar shows 4 consecutive green-highlighted cells (stacked buying imbalances) spanning 21,040 to 21,060. Price continues up for 2 bars, then pulls back. When price returns to 21,060 (the top of the green zone), you enter long. The buyers who drove those imbalances defend the zone, and price bounces back up.

**Pre-trend example:** NQ consolidates, then one bar shows 5 stacked buying imbalances as price breaks out upward. Two more bars form above the zone. Price pulls back to the zone. You enter long at the top of the green zone. The breakout buyers defend their positions.

**Rejection example:** NQ spikes down aggressively. Within the rejection, one bar shows 3 stacked selling imbalances (red zone) as sellers overwhelmed buyers on the way down. Price then reverses sharply upward. Two bars form above the red zone. Price pulls back down to the red zone. You enter short at the bottom of the red zone.

---

## When to Use

- 3 or more consecutive imbalances stacked at adjacent price levels (auto-highlighted)
- Context is a trend, pre-trend base, or strong directional move
- At least 1-2 complete footprint bars have formed away from the zone
- First test of the zone after price has moved away
- The zone is clearly defined (tight price range, not spread across 20+ levels)

---

## When NOT to Use

- Fewer than 3 consecutive imbalances (not a Stacked Imbalance, just isolated imbalances)
- The zone has already been tested once
- Choppy, directionless price action with no clear context
- Price hasn't moved away from the zone yet
- The imbalance threshold is set too low, causing the entire chart to be highlighted (calibration issue)
- The zone is very old and market structure has changed significantly

---

## Key Settings

| Setting | Value |
|---|---|
| Display mode | Bid x Ask (required) |
| Chart timeframe | 30-minute |
| Display imbalance clusters | ON |
| Imbalance trigger threshold | 300% (one side is 3x the other) |
| Cluster size (minimum stack) | 3 consecutive imbalances |
| Cluster opacity | 50 |
| Green zone | Stacked Buying Imbalances (support) |
| Red zone | Stacked Selling Imbalances (resistance) |
| First test only | Yes |

### Threshold Notes

The 300% trigger means one side must be at least 3x the other to register as an imbalance. At 100%, everything is an imbalance. At 500%, only extreme cases register. 300% is the standard starting point. Adjust based on how many imbalances you see per session. You want meaningful signals, not a chart covered in highlights.

Cluster size of 3 means you need at least 3 consecutive imbalances to form a highlighted zone. Isolated single imbalances are visible but not highlighted as a cluster.

---

## NQ/ES-Specific Notes

- NQ tends to produce more dramatic stacked imbalances than ES because NQ moves faster and institutional orders are more concentrated. A 5-imbalance stack on NQ is common during trending sessions.
- ES stacked imbalances are often tighter in price range (fewer ticks per imbalance level) due to ES's smaller tick size relative to its price. NQ imbalances can span larger point ranges.
- During the RTH open, stacked imbalances form quickly as institutions establish directional positions. These early-session zones often hold for the entire day.
- NQ stacked imbalances at or near VWAP carry extra weight. Institutions use VWAP as a benchmark. A stacked imbalance zone that coincides with VWAP is a high-conviction setup.
- If a Stacked Imbalance zone aligns with a prior day's high or low, treat it as a confluence setup. The technical level + institutional imbalance = stronger expected reaction.
- During low-volatility sessions (summer Fridays, holiday weeks), stacked imbalances may be smaller (3-4 levels instead of 5-8). The setup still works, but the reaction may be less dramatic. Adjust profit targets accordingly.
- On NQ, a red zone (selling imbalances) that forms at a prior resistance level and holds on the first test is one of the cleanest short setups in order flow trading. The combination of prior resistance + institutional selling imbalances + first test is high conviction.
