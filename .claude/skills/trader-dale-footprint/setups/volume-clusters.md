# Setup #1: Volume Clusters

Two sub-setups share the same core logic. The only difference is the context in which the cluster forms: within a running trend, or within a sharp rejection.

---

## Overview

A Volume Cluster is a footprint area where traded volume is noticeably heavier than surrounding bars. On the grey-shading (Volumes) display mode, these appear as darker cells. Institutions accumulate or distribute positions here. When price returns to that zone, those same institutions defend their positions, and traders on the opposing side close out to avoid fighting them. Both forces push price in the same direction, away from the cluster.

This setup does NOT require Bid x Ask data. It works on any instrument where volume is available, including Forex futures.

---

## Logic Behind the Setup

Two factors drive price away from a Volume Cluster on a retest:

1. **Position defense.** Traders who built positions inside the cluster (longs in an uptrend cluster, shorts in a downtrend cluster) defend those positions aggressively when price returns. They add to their positions or hold firm, creating buying or selling pressure.

2. **Opposing side closing.** Traders on the wrong side of the cluster recognize the institutional presence and close their positions to cut losses. Sellers closing shorts in a long cluster = additional buying pressure. Buyers closing longs in a short cluster = additional selling pressure.

Both forces act simultaneously and in the same direction. That's why the reaction at a Volume Cluster tends to be sharp.

---

## Step-by-Step Rules

### Sub-Setup A: Volume Cluster within a TREND

1. Set your Order Flow chart to display **Volumes** (not Bid x Ask). Use the grey shading mode.
2. Identify a clear trend on the 30-minute chart, either up or down.
3. Within that trend, find a footprint bar or group of bars with noticeably darker grey shading compared to surrounding bars. This is your Volume Cluster.
4. Confirm that price has moved **away** from the cluster. At least 1-2 complete footprint bars must have formed entirely above (uptrend) or below (downtrend) the cluster before you consider the setup valid.
5. Wait. Do not enter at the cluster. Wait for price to pull back and return to the cluster zone.
6. Enter at the **beginning of the cluster** (the edge closest to where price is coming from) or at the **heaviest volume cell** within the cluster, whichever is more precise.
7. Place your stop loss below the cluster (long) or above the cluster (short), with a small buffer.

### Sub-Setup B: Volume Cluster within a REJECTION

1. Set your Order Flow chart to display **Volumes** (grey shading mode).
2. Instead of a trend, look for a **strong rejection**: price moves aggressively in one direction, then suddenly and sharply reverses. The reversal must be clear and decisive.
3. Within that rejection candle or group of rejection candles, find the Volume Cluster (darkest grey area).
4. Confirm that price has moved away from the cluster. At least 1-2 complete footprint bars must have formed entirely on the other side.
5. Wait for price to pull back to the cluster zone.
6. Enter at the beginning of the cluster or the heaviest volume cell.
7. Place stop loss beyond the cluster with a small buffer.

---

## Direction Rules

| Context | Cluster Location | Trade Direction |
|---|---|---|
| Uptrend | Within the trend | Long on pullback |
| Downtrend | Within the trend | Short on pullback |
| Rejection of lower prices | Within the rejection | Long on pullback |
| Rejection of higher prices | Within the rejection | Short on pullback |

**Critical:** Direction is determined by context, not by the color of the cluster. A dark cluster in an uptrend = Long. Same cluster in a downtrend = Short.

---

## Two Factors That Drive Price

When price returns to a Volume Cluster, two things happen at the same time:

- **Buyers (in an uptrend cluster) defend their longs.** They bought heavily here. They don't want to lose. They buy more or hold, creating demand.
- **Sellers approaching the cluster close their shorts.** They know strong buyers are sitting here. Fighting that is a losing trade. They buy to close, adding more demand.

Net result: price gets pushed away from the cluster in the direction of the original move.

In a downtrend cluster, the same logic applies in reverse: sellers defend, buyers close longs.

---

## Examples Description

**Uptrend example:** NQ is trending up on the 30-minute chart. One bar in the middle of the trend has significantly darker shading than the bars around it. Price continues up for 3 more bars, then pulls back. When price returns to the dark bar's range, you enter long. Price bounces and continues the uptrend.

**Rejection example:** NQ drops sharply for 4 bars, then one bar shows a massive volume spike (very dark) and price immediately reverses upward. Two bars form above the dark bar. Price pulls back to the dark bar's range. You enter long. Price continues up.

---

## When to Use

- Clear trend on the 30-minute chart with a visible Volume Cluster inside it
- Strong price rejection with a Volume Cluster at the reversal point
- At least 1-2 complete footprint bars have formed away from the cluster before the pullback
- First test of the cluster after price has moved away

---

## When NOT to Use

- Price has already tested the cluster once (first test only)
- The cluster is not clearly darker than surrounding bars (ambiguous shading)
- No clear trend or rejection context, just a random dark bar in choppy price action
- Price is still inside the cluster, hasn't moved away yet
- The cluster is very old (many sessions ago) and market structure has changed significantly

---

## Key Settings

| Setting | Value |
|---|---|
| Display mode | Volumes (grey shading) |
| Chart timeframe | 30-minute |
| Bid x Ask required | No |
| Minimum bars away from cluster | 1-2 complete footprint bars |
| Entry point | Beginning of cluster or heaviest volume cell |
| First test only | Yes |

---

## NQ/ES-Specific Notes

- On NQ 30-minute charts, Volume Clusters often form at round numbers (21000, 21050, etc.) and at prior session highs/lows. These coincide with institutional order placement zones.
- NQ moves fast. The pullback to a cluster can be brief. Have your entry level pre-marked before price arrives.
- ES clusters tend to be slightly more orderly than NQ. NQ clusters can have more noise around them. Give NQ entries a slightly wider buffer on the stop.
- Both instruments work well with this setup. NQ's higher volatility means the reaction off a cluster can be larger in points, but the risk is proportionally higher too.
- During pre-market and overnight sessions, volume is thinner. Clusters formed during RTH (9:30-16:00 ET) carry more weight than those formed in overnight sessions.
- Avoid clusters that formed during major news events (FOMC, CPI). The volume may be event-driven rather than positional, making the defense logic less reliable.
