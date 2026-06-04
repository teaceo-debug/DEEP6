# LVN Identification — Quality Scoring & NQ-Specific Thresholds

Not every thin spot in a volume histogram is a tradeable LVN. The difference between a structural LVN and random noise is contrast, context, and formation conditions. This file covers how to identify valid LVNs, score their quality, and apply NQ-specific thresholds from the DEEP6 configuration.

---

## What Makes a Valid LVN

An LVN is a valley in the volume histogram where participation was genuinely thin relative to surrounding price levels. The key word is "relative." A level with 50 contracts traded is an LVN if the adjacent levels traded 500. It's not an LVN if everything nearby also traded 50.

**Three criteria must all be met:**

1. **Clean trough:** The LVN must sit between two adjacent peaks (HVNs). It's a valley, not just a low point at the edge of the profile. Edge thinness is not an LVN.

2. **Minimum width:** The thin zone must span at least 1-3 contiguous price levels. A single tick of low volume surrounded by high volume on both sides is usually noise, not structure.

3. **Volume threshold:** Bins within the LVN zone must fall below 30% of the average bin volume for that profile. DEEP6 uses `lvn_threshold=0.30` as the cutoff.

If any of these three criteria fail, the level is not a valid LVN for trading purposes.

---

## LVN Quality Scoring

Once you've confirmed a valid LVN, score it across six dimensions. Higher scores mean higher probability trades.

### Width (NQ Ticks)

| Width | Classification | Implication |
|-------|---------------|-------------|
| 1-2 ticks | Narrow | Tight stop, fast move, high probability but small target |
| 2-4 ticks | Optimal | Best risk/reward. Wide enough to be structural, narrow enough to be precise. |
| 5+ ticks | Wide | Slower, more noise, lower probability. Treat as a zone, not a level. |

DEEP6 uses `min_zone_ticks=2` to filter out single-tick noise. The sweet spot for NQ is 2-4 ticks.

### Contrast

Contrast is the volume difference between the LVN and its adjacent HVN peaks. High contrast means the market clearly avoided this price zone. Low contrast means the LVN is marginal.

Calculate it as: `(avg_adjacent_HVN_volume - LVN_volume) / avg_adjacent_HVN_volume`

A ratio above 0.70 (LVN is less than 30% of adjacent HVN) is high contrast. Below 0.50 is marginal. DEEP6's `hvn_threshold=1.70` defines what counts as a peak, which indirectly sets the contrast floor.

### Formation Context

How the LVN formed matters as much as its shape.

| Formation Context | Significance |
|------------------|-------------|
| After strong directional move (>20 NQ points) | High. Price moved through this zone with conviction. |
| During a rotation or chop session | Low. Thin volume may reflect indecision, not rejection. |
| At session open or close | Moderate. Time-of-day effects can create artificial thinness. |
| During a news spike | Low. Thin volume reflects illiquidity, not structural rejection. |

The best LVNs form when the market moves through a price zone quickly because it's genuinely uninteresting to participants, not because it's illiquid.

### Confluence

An LVN that aligns with other structural levels is significantly more powerful than an isolated one.

| Confluence Factor | Significance |
|------------------|-------------|
| Aligns with prior session VAH or VAL | High |
| Aligns with prior session POC | High |
| Aligns with a Fair Value Gap (FVG) | High |
| Aligns with a weekly or monthly level | Very High |
| Isolated (no other confluence) | Low |

DEEP6 checks for confluence with prior session levels during zone scoring. An LVN that sits exactly at a prior VAH is treated as a structural level, not just an intraday feature.

### Age

LVNs decay. The older they are, the more likely they've been tested and their edge has diminished.

| Age | Probability |
|-----|------------|
| Same session (fresh) | Highest. Untested, full edge intact. |
| Prior session | Moderate. May have been tested overnight. |
| 2-3 sessions old | Declining. Check if it's been tested. |
| 3+ sessions old | Low, unless it's structural (weekly/monthly composite). |

Structural LVNs from composite profiles don't decay the same way. A weekly composite LVN that's been respected for 3 weeks is more significant than a fresh daily LVN.

### Touch Count

Every time price tests an LVN and reacts, some of the edge is consumed. Participants learn the level exists and start positioning around it.

| Touch Count | Edge |
|-------------|------|
| Untested (0 prior touches) | Maximum edge. First test has highest probability. |
| 1 prior test (held) | Moderate. Level is confirmed but partially discovered. |
| 2+ prior tests | Declining. The level is well-known. Expect more noise. |
| Tested and broken | No longer an LVN. It's now a tested level with no structural significance. |

---

## NQ-Specific Thresholds (DEEP6 Config)

These are the production values used in DEEP6's volume profile engine:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `lvn_threshold` | 0.30 | Bins below 30% of average bin volume qualify as LVN |
| `hvn_threshold` | 1.70 | Bins above 170% of average bin volume qualify as HVN |
| `min_zone_ticks` | 2 | Minimum contiguous ticks for a valid zone |
| `max_zones` | 20 | Maximum zones returned per profile (prevents noise flooding) |

The gap between 0.30 and 1.70 is intentional. Levels between 30% and 170% of average are "neutral" and not classified as either LVN or HVN. This prevents marginal levels from polluting the signal.

---

## Detection Methods

### scipy.argrelextrema (Primary)

The standard approach for NQ profiles. Use `order=2` to find local minima that are lower than their 2 nearest neighbors on each side. This filters single-tick noise while catching real valleys.

The `order` parameter controls sensitivity. Order 1 catches every local minimum (too noisy). Order 3+ misses narrow but real LVNs. Order 2 is the NQ sweet spot.

### KDE Smoothing (Noisy Profiles)

When the raw histogram is jagged (common in low-volume sessions or thin overnight profiles), apply Kernel Density Estimation before running the extrema detection. KDE smooths the histogram into a continuous curve, making real valleys more visible and noise less prominent.

Use a bandwidth that corresponds to roughly 2-4 NQ ticks. Too narrow and you're back to noise. Too wide and you're smoothing out real structure.

### Visual Identification

The fastest check: look for a clear gap in the histogram where bars are noticeably shorter than their neighbors. If you have to squint to see it, it's probably not significant enough to trade.

Real LVNs are obvious. The histogram drops sharply, stays low for 2-4 ticks, then rises sharply on the other side. The contrast is visible without any calculation.

---

## Common Mistakes

**Identifying noise as LVN.** A single tick of low volume between two slightly higher ticks is not an LVN. Apply the minimum width and contrast criteria before calling anything an LVN.

**Confusing time-of-day thinness with structural LVN.** The first and last 15 minutes of the session often have thin volume at certain price levels simply because the market hasn't been there yet that day, or because participants are closing positions. This is not structural.

**Treating a wide LVN as a single level.** A 6-tick LVN is a zone, not a line. Don't place your entry at the midpoint and expect precision. The zone has a top and a bottom, and price can react anywhere within it.

**Ignoring formation context.** An LVN that formed during a news spike is not the same as one that formed during a clean directional move. The spike LVN reflects illiquidity. The directional LVN reflects genuine rejection.

**Counting tested LVNs as fresh.** Once an LVN has been tested and held, it's a different animal. It's confirmed but partially consumed. Adjust your position sizing and target expectations accordingly.
