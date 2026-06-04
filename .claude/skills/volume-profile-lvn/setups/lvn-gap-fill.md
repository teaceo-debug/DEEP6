# LVN Gap Fill

**Overnight Gap Through LVN — RTH Return Trade**

## Overview

When the market gaps overnight through an LVN zone, the gap creates an unfilled auction area. Price moved through that zone without the normal two-sided auction process. During RTH, price often returns to complete that auction — filling the gap and testing the LVN.

The LVN is the key structural element. Not all gaps are worth trading. A gap through an HVN is a different animal — there's volume structure to absorb the return. A gap through an LVN means price skipped over a zone that already had no volume. When price returns, it moves through the LVN quickly (same structural vacuum as always) and the gap fill completes faster and cleaner than a gap through an HVN.

The edge: the LVN provides a clean entry reference, a tight stop, and a clear target (the HVN on the other side of the gap).

---

## Setup Conditions

All conditions must be met before considering entry.

1. **Overnight gap spans through an identified LVN zone** — the gap open and gap close bracket the LVN
2. **The LVN was present in the prior day's profile** — not freshly created by the gap itself
3. **RTH opens with price on the opposite side of the LVN from the prior close** — the gap is real, not a pre-market drift
4. **Order flow showing aggressive activity toward the gap fill direction** — buyers (for a gap-down fill) or sellers (for a gap-up fill) are present at the open
5. **No major fundamental catalyst driving the gap** — earnings gaps, Fed decision gaps, and geopolitical gaps often don't fill on the same day
6. **Gap size is within the expected move range** — gaps larger than 2x the daily expected move rarely fill on the same day

---

## Entry Rules

**Entry trigger:** As price enters the LVN zone during RTH, with footprint confirmation.

Do not enter at the open. Wait for price to begin moving toward the gap fill direction and enter as it reaches the LVN zone.

**Footprint confirmation required (at least one):**
- Absorption at the LVN boundary (high volume, minimal movement, large wick)
- Delta flip: CVD reversing in the gap fill direction as price enters the LVN
- Stacked imbalances in the gap fill direction (3:1 or better across 3+ price levels)

**Entry type:** Limit order placed at the LVN boundary as price approaches. Do not market-order into the LVN.

**Entry direction table:**

| Gap type | Gap fill direction | Entry |
|----------|--------------------|-------|
| Gap up (opened above LVN) | Bearish (price falls back through LVN) | Short as price enters LVN from above |
| Gap down (opened below LVN) | Bullish (price rises back through LVN) | Long as price enters LVN from below |

**Session timing:** Entry must occur before 12:00 PM ET. After noon, unfilled gaps often persist until the next session. Do not force a gap fill entry in the afternoon.

---

## Stop Loss Rules

**Stop placement:** Beyond the opposite side of the LVN from entry.

- For short entries (gap-up fill): stop above the LVN upper boundary
- For long entries (gap-down fill): stop below the LVN lower boundary

If price closes beyond the far LVN boundary in the wrong direction (away from the gap fill), the gap fill thesis is invalidated. Exit immediately.

**Stop adjustment rules:**
- Move to breakeven after price travels 50% of the distance to the target HVN
- Trail to prior swing after 75% of the distance to target
- If price stalls inside the LVN for more than 3 bars on the 5-minute chart, exit — the LVN is absorbing the move

**Hard stop rule:** If the gap fill has not progressed by 11:30 AM ET, tighten the stop to just beyond the LVN boundary. The probability of a same-day fill drops sharply after noon.

---

## Profit Target Rules

**Primary target:** The HVN on the other side of the gap (where price originally came from before the gap).

This is the natural destination of the gap fill. Price is returning to the prior session's value area. The HVN POC is the gravitational center of that value area.

**Target scaling:**
- 60% of position at the near edge of the target HVN
- Remaining 40% at the HVN POC

**Full gap fill target:** If the gap fill target is the prior session's POC, that's the maximum target. Do not hold beyond the prior session's POC hoping for more — the gap fill is complete.

**Partial fill scenario:** If price fills the gap partially (reaches the LVN but doesn't reach the prior HVN), take partial profit at the LVN far boundary and trail the rest.

---

## NQ-Specific Rules

**Gap frequency:** NQ overnight gaps are common, driven by Asian and European session moves, tech earnings, and macro data releases. Not all gaps are tradeable — apply the setup conditions strictly.

**Gap fill timing:** NQ gap fills typically occur within the first 2-3 hours of RTH. The highest probability window is 9:30 AM to 12:00 PM ET. After noon, unfilled gaps often persist.

**Gap size filter:** NQ gaps larger than 150 points rarely fill on the same day. Gaps of 30-100 points through an LVN are the sweet spot for this setup.

**LVN verification:** Confirm the LVN was present in the prior day's composite profile, not just the overnight session. Overnight LVNs are less reliable structural references.

**Volume at open:** NQ opening volume should show directional bias toward the gap fill. If the first 5-minute bar's CVD is moving against the gap fill direction, the market is not interested in filling the gap today. Skip the trade.

**Tick reference:** LVN boundaries defined to the nearest 0.25 NQ point. Gap boundaries defined to the nearest 1.0 NQ point (gap open and gap close prices).

---

## Order Flow Confirmation

Required before entry. At least two of three must be present.

**1. Absorption at LVN boundary**
- High volume at the LVN boundary as price enters the zone
- Minimal net price movement despite the volume
- The side opposing the gap fill (sellers in a gap-down fill, buyers in a gap-up fill) is being absorbed

**2. CVD alignment**
- CVD trending in the gap fill direction from the open
- No divergence: CVD not reversing against the gap fill as price enters the LVN
- CVD should be making new extremes in the gap fill direction

**3. Imbalance confirmation**
- Footprint imbalances on the entry bar favor the gap fill direction (3:1 or better)
- Stacked imbalances across 3+ price levels in the gap fill direction

If only one signal is present, reduce size to 50% or skip.

---

## Gamma Regime Filter

**POSITIVE gamma (best for gap fills):**
- Dealers dampen momentum and support mean reversion.
- Gap fills are mean-reversion trades — positive gamma supports the thesis.
- Highest probability of clean gap fill completion.

**NEGATIVE gamma (marginal):**
- Dealers amplify momentum. If the gap was driven by a strong directional move, negative gamma may extend it rather than allow a fill.
- Only trade gap fills in negative gamma if the gap is small (<60 NQ points) and order flow confirmation is strong.

**NEUTRAL gamma (acceptable):**
- Standard confirmation requirements apply.

**Special case — gamma flip through the gap:**
- If the gamma flip level is inside the gap zone, the gap fill may stall at the flip level.
- Adjust the target to the gamma flip level rather than the full HVN POC.

---

## Risk-Reward Profile

| Metric | Typical range |
|--------|---------------|
| Win rate | 55-60% |
| R:R per trade | 2:1 to 3:1 |
| Stop width | LVN width (typically 10-25 NQ points) |
| Target distance | LVN to prior HVN POC (typically 30-80 NQ points) |
| Expected value | +1.1R to +1.6R per trade |

Lower win rate than the rejection fade, but the structural clarity of the gap fill target (prior HVN POC) makes the R:R reliable. The setup is most consistent when the gap is through a clean, well-defined LVN with clear HVNs on both sides.

---

## Common Mistakes

**1. Trading gaps that aren't through an LVN**
A gap through an HVN is a different setup with different dynamics. The LVN is what makes this setup work. If the gap doesn't span an LVN, skip it.

**2. Entering at the open without waiting for the LVN**
The entry is at the LVN, not at the open. Entering at the open is chasing. Wait for price to reach the LVN zone with footprint confirmation.

**3. Forcing gap fills after noon**
The probability of a same-day gap fill drops sharply after 12:00 PM ET. If the gap hasn't filled by noon, accept that it may not fill today and move on.

**4. Trading fundamental gaps**
Earnings gaps, Fed decision gaps, and major geopolitical gaps often don't fill on the same day. The fundamental catalyst overrides the structural LVN edge. Skip these.

**5. Ignoring gap size**
NQ gaps larger than 150 points rarely fill on the same day. The larger the gap, the lower the probability of a same-day fill. Apply the gap size filter.

**6. Not checking prior session LVN validity**
The LVN must have been present in the prior day's profile. If the LVN was created by the gap itself (overnight session), it's not a reliable structural reference.

**7. Holding through noon without a stop adjustment**
If the gap fill hasn't progressed by 11:30 AM ET, tighten the stop. The afternoon session has different dynamics and gap fills that haven't completed by noon often reverse.
