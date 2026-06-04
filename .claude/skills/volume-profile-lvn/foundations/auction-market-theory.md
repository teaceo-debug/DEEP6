# Auction Market Theory

## Overview

Auction Market Theory (AMT) is the conceptual foundation for all Volume Profile and Market Profile analysis. Developed by J. Peter Steidlmayer at the Chicago Board of Trade in the 1980s and later expanded by James Dalton in *Mind Over Markets*, AMT provides a framework for understanding why prices move, where they pause, and what volume distribution reveals about market structure.

The core principle: **markets are continuous two-way auctions that discover fair value**. Price is not random. It's an advertising mechanism. Time regulates the auction. Volume measures success.

---

## The Three Pillars

| Pillar | Role | What It Tells You |
|--------|------|-------------------|
| **Price** | Advertising | Attracts buyers and sellers; moves until it finds two-sided interest |
| **Time** | Regulation | How long price stays at a level determines whether the market accepts or rejects it |
| **Volume** | Success measurement | High volume = acceptance; low volume = rejection or transit |

These three pillars work together. Price alone is noise. Price + time + volume = structure.

---

## Two Market States

Markets spend their time in one of two states. Recognizing which state you're in determines your entire trading approach.

### Balance (~70% of time)

- Buyers and sellers agree on approximate fair value
- Price oscillates within a range, building volume at the center
- Mean reversion is the dominant behavior
- Characterized by overlapping TPO periods and a well-defined Value Area
- Trading strategy: fade extremes, target the POC

### Imbalance (~30% of time)

- One side dominates; the other withdraws
- Price moves directionally with little time spent at any level
- Trending behavior; volume is thin at prices traversed
- Characterized by single prints, poor highs/lows, and elongated profiles
- Trading strategy: trade with the imbalance, not against it

The transition between states is where the highest-probability setups occur. A market breaking out of balance into imbalance, or an imbalance exhausting and returning to balance, creates the clearest structural signals.

---

## The Two-Way Auction Process

Understanding how price discovers value requires following the auction mechanics step by step.

1. **Buyers probe higher** -- they advertise higher prices to attract sellers
2. **Sellers test the response** -- if sellers appear, a transaction occurs; if not, buyers continue higher
3. **Transaction or rejection** -- volume at the level determines acceptance (high volume) or rejection (low volume, quick reversal)
4. **Opposite direction probed** -- once buyers find resistance, sellers probe lower; the same process repeats
5. **Value area found** -- the range where both sides transact repeatedly becomes the Value Area; the price with the most volume becomes the POC

This process never stops. Even within a "balanced" day, the auction is continuously probing. The profile is a snapshot of where the auction found agreement.

---

## Market Profile Components

Market Profile uses TPO (Time Price Opportunity) letters to map where price traded during each 30-minute period.

| Component | Definition | Significance |
|-----------|------------|--------------|
| **TPO** | One letter per 30-min period price traded at that level | Shows time-at-price; each letter = 30 min of market acceptance |
| **Value Area (VA)** | The range containing 70% of TPO count | Where the market spent most of its time; "fair value" zone |
| **POC** | Price of Control; the single price with the most TPOs | The most accepted price of the session |
| **Single Prints** | Prices with only one TPO letter | Rapid transit; market rejected or moved through without acceptance |
| **Poor High/Low** | Session extreme with multiple TPOs (not a single print) | Unfinished auction; market may return to probe further |

---

## Volume Profile vs Market Profile

Both tools map price structure, but they measure different things.

| Dimension | Market Profile | Volume Profile |
|-----------|---------------|----------------|
| **Measures** | Time at price (TPO count) | Volume at price |
| **Metaphor** | Democratic (each 30-min period = one vote) | Plutocratic (large volume = more weight) |
| **POC** | Most time spent | Most volume traded |
| **Strength** | Shows market structure and day type clearly | Shows where institutional money actually transacted |
| **Weakness** | Ignores volume; a quiet 30-min period = same weight as a high-volume one | Requires tick-level data; computationally heavier |
| **Best for** | Day type identification, session structure | Identifying HVN/LVN, institutional footprints |

For DEEP6's purposes, Volume Profile is primary. Time-at-price is a secondary confirmation. When both agree on a level, conviction is higher.

---

## Dalton's Day Types

James Dalton identified five recurring day types based on how the profile develops. Recognizing the day type early changes how you interpret LVN signals.

### Normal Day

- Wide Initial Balance (IB) set in the first hour
- Price stays within or near the IB for the rest of the session
- Profile is bell-shaped; well-defined Value Area
- LVN signals at IB extremes have high rejection probability

### Normal Variation Day

- Moderate IB; one extension beyond IB in one direction
- Most common day type
- Profile is slightly skewed; one tail is longer
- LVN signals work well at the extended extreme

### Trend Day

- Narrow IB; price extends significantly in one direction all day
- Profile is elongated; single prints dominate
- LVN signals against the trend fail; trade with the imbalance
- The entire day's range may become an LVN relative to adjacent sessions

### Double Distribution Day

- Two distinct value areas separated by a gap or thin area
- The thin area between distributions is a structural LVN
- Price often returns to this gap; high-probability rejection zone
- Most relevant day type for LVN trading

### Non-Trend Day

- Very narrow range; market in tight balance
- Profile is compressed; no clear directional conviction
- LVN signals are unreliable; wait for breakout confirmation

---

## The 80% Rule

One of the most statistically robust observations in Market Profile analysis:

**If price opens outside the prior session's Value Area and then returns to the Value Area boundary, there is approximately an 80% probability that price will traverse the entire Value Area to the opposite side.**

### Mechanics

- The Value Area represents accepted fair value from the prior session
- Opening outside VA signals potential imbalance or gap fill attempt
- Once price re-enters VA, the auction process pulls it toward the opposite extreme
- The POC acts as a magnet; price rarely stops at the VA boundary

### Application

- Entry: first bar that closes back inside the VA after opening outside
- Target: opposite VA boundary (VAL if opened above VAH, VAH if opened below VAL)
- Stop: outside the VA boundary (invalidation = market rejects re-entry)

This rule works because it's grounded in auction mechanics, not pattern recognition. The VA is where the market found value. Re-entry triggers the same auction forces that built the VA in the first place.

---

## Initial Balance (IB)

The Initial Balance is the price range established during the first hour of the regular trading session (9:30-10:30 ET for NQ).

### Why IB Matters

- Sets the reference range for the day
- Other timeframe participants (OTF) observe IB before committing
- IB extension signals directional conviction from OTF buyers or sellers
- Narrow IB = uncertainty; wide IB = early conviction

### IB Extension Rules

| Extension | Interpretation |
|-----------|---------------|
| No extension | Non-trend day likely; range-bound |
| One-sided extension | Normal Variation day; directional bias established |
| Two-sided extension | Volatile, two-sided; wait for structure |
| Extension > 2x IB | Trend day developing; trade with extension |

### IB and LVN Interaction

When an LVN sits just outside the IB boundary, it becomes a high-probability target if price breaks the IB. The LVN provides low friction for the extension to accelerate through. Conversely, an HVN just outside the IB acts as a brake on extension.

---

## Key Takeaways for DEEP6

1. **Balance vs imbalance identification comes first.** Every LVN signal must be interpreted within the current market state. LVN rejection signals work in balance; LVN traversal signals work in imbalance.

2. **Volume is the vote that counts.** Time-at-price is useful context, but volume-at-price reveals where institutions actually committed capital.

3. **The auction never stops.** Every LVN is a record of a past auction that was interrupted. Price will eventually return to complete the auction or confirm the rejection.

4. **Day type changes signal interpretation.** A trend day makes LVN rejection signals unreliable. A double distribution day makes the gap between distributions the highest-probability LVN in the session.

5. **The 80% rule is structural, not statistical.** It works because of auction mechanics, not because of historical pattern frequency. Understanding why it works makes you a better trader than memorizing that it works.

---

## References

- Steidlmayer, J.P. & Koy, K. (1986). *Markets and Market Logic*. Chicago: Porcupine Press.
- Dalton, J.F., Jones, E.T. & Dalton, R.B. (1990). *Mind Over Markets*. Chicago: Probus Publishing.
- Dalton, J.F. (2007). *Markets in Profile*. Hoboken: Wiley.
- Steidlmayer, J.P. (2003). *Steidlmayer on Markets: Trading with Market Profile* (2nd ed.). Hoboken: Wiley.
