# Composite Volume Profiles — Multi-Session Structural Analysis

A single daily profile shows you what happened today. A composite profile shows you what the market has been doing for days, weeks, or months. The difference matters because structural LVNs, the ones that persist and get respected repeatedly, only become visible when you aggregate across sessions.

---

## Why Composite Profiles Matter

Daily profiles are noisy. An LVN that appears in today's profile might be gone tomorrow if the market consolidates through it overnight. But an LVN that appears in a 5-day or 20-day composite has survived multiple sessions of trading. Participants have repeatedly avoided that price zone. That's not noise. That's structure.

The core insight: **daily LVNs are tactical, composite LVNs are strategic.**

Use daily LVNs for intraday entries and targets. Use composite LVNs for session bias, swing context, and understanding why price is moving the way it is.

---

## LVN Significance by Timeframe

| Timeframe | LVN Type | Persistence | Use Case |
|-----------|----------|-------------|----------|
| Daily | Intraday LVN | Hours to 1 session | Intraday entries, same-day targets |
| Weekly (5-day) | Structural LVN | Days to weeks | Session bias, swing context |
| Monthly (20-day) | Institutional LVN | Weeks to months | Position context, major S/R |

A monthly composite LVN represents a price zone that institutional participants have avoided for weeks. When price approaches it, expect a significant reaction. These levels don't fill casually.

The hierarchy matters for trade management. If your intraday LVN target sits inside a monthly composite HVN, the trade has a ceiling. If your intraday LVN sits in a monthly composite LVN, the move can extend much further.

---

## How to Build Composite Profiles

**Step 1: Select the session range.** For a weekly composite, use the last 5 RTH sessions. For monthly, use the last 20. For a custom range (e.g., since a major swing high), use that specific date range.

**Step 2: Aggregate volume by price level.** Sum all volume traded at each price level across all selected sessions. The result is a single histogram covering the entire price range of the period.

**Step 3: Weight RTH vs overnight.** RTH sessions contain 80-90% of institutional volume. Overnight sessions reflect inventory positioning and retail activity. Weight RTH volume 2x relative to overnight, or exclude overnight entirely for a pure institutional composite.

**Step 4: Use consistent bin sizes.** If your daily profiles use 1-tick bins, your composite must also use 1-tick bins. Mixing bin sizes creates false structure.

**Step 5: Apply the same LVN detection thresholds.** The same `lvn_threshold=0.30` and `min_zone_ticks=2` apply. The composite histogram is just a larger version of the daily histogram.

---

## Reading Composite vs Daily

**Composite POC vs daily POC:** When the composite POC and today's daily POC diverge significantly, the market is away from multi-session fair value. This creates a gravitational pull back toward the composite POC. The further price is from the composite POC, the stronger the mean-reversion tendency.

**Composite LVN = gap between weekly VAs:** When you look at a week of daily profiles, the spaces between each day's Value Area are composite LVNs. Price moved through those zones quickly enough that no session built value there. These gaps are structural highways.

**Composite HVN = multi-session consensus:** A price level that shows up as an HVN in multiple daily profiles becomes a very strong composite HVN. This is where the market repeatedly found fair value. It's a major S/R level that will be defended.

---

## Session Weighting Strategies

**Equal weight:** Every session contributes equally to the composite. Simple and unbiased. Best for understanding the full structural picture without recency bias.

**Recency-weighted:** Recent sessions are weighted higher than older ones. Reflects the current market regime more accurately. DEEP6 uses `session_decay_weight` to apply exponential decay to older sessions. A session from 10 days ago might contribute at 50% weight compared to today's session.

**Volume-weighted:** High-volume sessions (e.g., FOMC days, major earnings) dominate the composite. Useful for identifying where the most significant institutional activity occurred. Risk: one extreme session can distort the composite.

For most NQ analysis, recency-weighted composites give the best balance between structural persistence and current relevance.

---

## Practical Example: Identifying a Structural LVN from a 5-Day NQ Composite

Suppose NQ has been trading between 19,800 and 20,200 for the past week. Here's how to find the structural LVN:

1. Pull the last 5 RTH sessions. Aggregate all volume by price level.

2. The composite shows heavy volume (HVN) at 19,850-19,900 and again at 20,050-20,100. These are the two main value areas where the market spent most of its time.

3. Between them, at 19,950-19,980, the composite shows very thin volume. Price crossed through this zone multiple times during the week but never consolidated there. This is the structural LVN.

4. Score it: Width is 6 ticks (wide zone, treat as a zone not a line). Contrast is high (adjacent HVNs are 3-4x the volume). Formation context is strong (formed during multiple directional moves). Confluence: check if 19,950 aligns with any prior session VAH or POC.

5. Trading implication: When price approaches 19,950-19,980 from either direction, expect fast movement through the zone. If approaching from below, target 20,050+. If approaching from above, target 19,900-.

---

## RTH vs Globex

**RTH profile (9:30 AM - 4:00 PM ET):** This is the primary profile. Institutional participants, market makers, and the majority of volume are active during RTH. RTH LVNs and HVNs reflect genuine institutional consensus.

**Globex / overnight profile (4:00 PM - 9:30 AM ET):** Secondary profile. Lower volume, wider spreads, more retail and international participation. Overnight LVNs are less reliable because they can reflect illiquidity rather than structural rejection.

Use the overnight profile for one specific purpose: inventory detection.

---

## Overnight Inventory Detection

The overnight session reveals what participants are carrying into the next RTH session.

**Long inventory signal:** Overnight POC is above the prior RTH settlement price. Buyers accumulated positions overnight at prices above where RTH closed. They're long and need RTH to move higher to profit.

**Short inventory signal:** Overnight POC is below the prior RTH settlement price. Sellers accumulated positions overnight at prices below where RTH closed. They're short and need RTH to move lower.

**Implication for RTH open:** Long inventory creates buying pressure at the open as longs defend their positions. Short inventory creates selling pressure. When overnight inventory aligns with the composite profile's directional bias, the signal is stronger.

If the overnight POC is sitting in a composite LVN, that's a particularly interesting setup. The overnight participants built positions in a zone where the composite says there's no structural support. One side is wrong, and RTH will resolve it quickly.
