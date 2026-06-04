# AMT Trend and Mean Reversion

**Auction Market Theory LVN Setups — Two Complementary Models**

## Overview

Two setups built on Auction Market Theory's balance/imbalance framework. They're complementary — one trades LVNs in directional moves (imbalance state), the other trades LVNs after failed breakouts (balance state). Knowing which market state you're in determines which model to use.

**AMT core principle:** Markets alternate between balance (two-sided auction, price oscillating in a range) and imbalance (one-sided auction, price seeking new value). LVNs behave differently in each state.

- In imbalance: LVNs are acceleration zones. Price moves through them fast in the trend direction.
- In balance: LVNs are rejection zones. Price probes them and returns to the balance area.

Misidentifying the market state is the primary source of losses in both setups.

---

## Market State Identification

Before selecting a model, identify the current market state.

**Imbalance (out-of-balance) indicators:**
- Price is making new highs or lows relative to the prior session's range
- Volume Profile shows a P-shape (buying imbalance) or b-shape (selling imbalance)
- Price is trending away from the prior session's Value Area
- CVD trending consistently in one direction across multiple bars

**Balance indicators:**
- Price is oscillating within the prior session's Value Area
- Volume Profile shows a bell curve (D-shape) — balanced two-sided auction
- Price is making equal highs and lows (no new extremes)
- CVD oscillating without a clear trend

**State transition signals:**
- Balance to imbalance: breakout from the balance area with volume confirmation
- Imbalance to balance: price returns to the prior Value Area and begins oscillating

---

## SETUP A: AMT Trend Model

**Use when:** Market is in imbalance — breaking out and seeking new value.

### Overview

In an imbalance state, price is moving directionally. LVNs inside the impulsive leg are the key reaction points — they're where the trend pauses briefly before continuing. The setup is to identify these LVNs and enter on the pullback into them, joining the trend.

The aggression requirement is non-negotiable. Without visible aggressive orders at the LVN, the pullback may be the start of a reversal, not a continuation. No aggression = no trade.

### Setup Conditions

1. **Market is in imbalance** — price is breaking out and seeking new value (confirmed by state identification above)
2. **Identify the impulse leg** that broke structure (the move that initiated the imbalance)
3. **Apply Volume Profile to the impulse leg** — use the start of the impulse to the current extreme
4. **Identify LVNs inside the impulse leg** — these are the key reaction points
5. **Wait for a pullback into the LVN** — price retraces from the extreme back toward the LVN
6. **Confirm aggression at the LVN** — aggressive buyers (bullish trend) or sellers (bearish trend) must be visible on the footprint

### Entry Rules

**Entry trigger:** Aggressive orders visible at the LVN during the pullback.

Aggression confirmation requires at least two of:
- Large bid/ask imbalances in the trend direction (3:1 or better across 3+ price levels)
- Delta spike: CVD making a new extreme in the trend direction as price touches the LVN
- Volume spike: bar volume >= 2x the 20-bar rolling average at the LVN

**Entry type:** Limit order at the LVN boundary in the trend direction.

**Entry direction table:**

| Trend direction | Pullback direction | LVN position | Entry |
|-----------------|-------------------|--------------|-------|
| Bullish | Price pulls back down | Below current price | Long at LVN lower boundary |
| Bearish | Price rallies up | Above current price | Short at LVN upper boundary |

**Critical rule:** If aggression is not visible at the LVN, do not enter. The pullback may be the start of a reversal. Wait for the next LVN or skip the trade.

### Stop Loss Rules

**Stop placement:** 5% to 10% of account risk (dynamic, based on LVN width and account size).

- Minimum stop: LVN width + 5 NQ points buffer
- Maximum stop: 10% of daily risk budget per trade

**Invalidation:** If price closes beyond the LVN in the wrong direction (against the trend), exit immediately. The trend is in trouble.

**Stop adjustment:**
- Move to breakeven after price travels 40% of the distance to the target
- Trail to prior swing after 70% of the distance to target

### Profit Target Rules

**Primary target:** Previous balance POC.

This is the most important rule of the Trend Model. 70% of the time, price reverses from the balance area. Take full profit at the balance POC. Do not hold through it hoping for more.

**Target identification:**
- Identify the balance area that price broke out of to initiate the imbalance
- The POC of that balance area is the target
- If price broke out of multiple balance areas, target the most recent one first

**Scaling:**
- 70% of position at the balance area near edge
- Remaining 30% at the balance POC

**Extended target:** If price blows through the balance area with volume (rare), extend to the next structural level. This happens in strong trend days and is the exception, not the rule.

---

## SETUP B: AMT Mean Reversion Model

**Use when:** Market tries to break out of balance but fails — returning to balance.

### Overview

In a balance state, price oscillates within a defined range. Occasionally, price probes beyond the balance area (a breakout attempt) but fails to sustain the move and returns inside the balance. This failed breakout creates an LVN in the retracement zone — the zone price moved through quickly on the way out and back.

The setup is to identify this LVN in the retracement zone and enter as price returns inside the balance area, targeting the balance POC.

### Setup Conditions

1. **Market is in balance** — price is oscillating within a defined Value Area (confirmed by state identification above)
2. **Price breaks out of the balance area** — moves beyond the Value Area high or low
3. **The breakout CANNOT HOLD** — price fails to sustain the move and begins returning inside the balance area
4. **Plot Volume Profile from the start of the impulse to the top of the failed breakout move**
5. **Identify the LVN in the retracement zone** — the zone price moved through quickly on the way out and back
6. **Wait for footprint confirmation at the LVN** — big aggressive orders in the reversion direction

### Entry Rules

**Entry trigger:** Price firmly back inside the balance area with LVN confirmation.

Confirmation requires at least two of:
- Aggressive orders at the LVN in the reversion direction (3:1 imbalances, delta spike)
- Price closing back inside the balance area on a 5-minute bar
- Volume spike at the LVN as price re-enters the balance area

**Entry type:** Limit order at the LVN boundary as price re-enters the balance area.

**Entry direction table:**

| Failed breakout direction | Reversion direction | Entry |
|---------------------------|--------------------|----|
| Failed bullish breakout (above balance) | Bearish (back into balance) | Short at LVN upper boundary as price re-enters balance |
| Failed bearish breakout (below balance) | Bullish (back into balance) | Long at LVN lower boundary as price re-enters balance |

**Confirmation timing:** Entry must occur within 3 bars of price re-entering the balance area. If price has already traveled 50%+ of the way to the balance POC, the entry is late — skip it.

### Stop Loss Rules

**Stop placement:** Just above the failed high (for bearish reversion) or below the failed low (for bullish reversion).

- For short entries (failed bullish breakout): stop above the failed breakout high
- For long entries (failed bearish breakout): stop below the failed breakout low

If price makes a new extreme beyond the failed breakout level, the reversion thesis is invalidated. Exit immediately.

**Stop adjustment:**
- Move to breakeven after price travels 40% of the distance to the balance POC
- Trail to prior swing after 70% of the distance to target

### Profit Target Rules

**Primary target:** POC inside the balance area.

The reversion trade ends at the center of value. The balance POC is where the most volume traded — it's the gravitational center of the balance area. That's where the trade ends.

**Scaling:**
- 60% of position at the balance area near edge (Value Area boundary)
- Remaining 40% at the balance POC

**Do not target beyond the balance POC.** The reversion trade is complete when price reaches the center of value. Holding beyond the POC is a different trade with a different thesis.

---

## Session Filter (Both Models)

**Best sessions:**
- NY session: 10:30 AM to 2:00 PM ET (highest volume, cleanest signals)
- London session: 3:00 AM to 8:00 AM ET (works for Reversion Model in compressed conditions)

**Avoid:**
- First 30 minutes of RTH (9:30-10:00 AM): too many fakeouts during price discovery
- Last 30 minutes of RTH (3:30-4:00 PM ET): thin volume, erratic moves
- Overnight session (outside London hours): low volume, unreliable signals

**Model-specific session notes:**
- Trend Model: best during NY session when institutional participation is highest
- Reversion Model: works in London session when NQ is in a compressed balance range

---

## NQ-Specific Rules

**Balance area identification for NQ:**
- Use the prior session's Value Area (VA High to VA Low) as the primary balance reference
- Secondary balance: any range where price has oscillated for 3+ hours with no new extremes
- NQ balance areas are typically 50-150 points wide during normal sessions

**Imbalance confirmation for NQ:**
- Price must be outside the prior session's Value Area
- CVD must be trending consistently in one direction for at least 30 minutes
- Volume must be above the 20-bar rolling average on the breakout bars

**LVN identification within impulse legs:**
- Apply Volume Profile to the impulse leg using a fixed-range profile
- LVNs inside the impulse leg are typically 10-30 NQ points wide
- Narrower LVNs produce tighter stops and better R:R

**Aggression threshold for NQ:**
- Volume spike at LVN: >= 2x the 20-bar rolling average
- Imbalance ratio: 3:1 or better across 3+ consecutive price levels
- Delta spike: CVD moving 50+ points in the trend direction within 1 bar

---

## Order Flow Confirmation (Both Models)

Required before entry. At least two of three must be present.

**1. Aggressive orders at the LVN (required)**
- Large bid/ask imbalances in the trade direction (3:1 or better)
- Volume spike at the LVN (2x+ rolling average)
- This is the non-negotiable signal — no aggression = no trade

**2. Delta confirmation**
- CVD trending in the trade direction
- No divergence against the trade direction
- Delta spike at the LVN entry bar

**3. Absorption (for Reversion Model)**
- High volume at the LVN with minimal net movement
- The aggressive counterparty (breakout continuation) is being absorbed
- Relevant primarily for the Reversion Model where the failed breakout is being absorbed

---

## Gamma Regime Filter

**Trend Model:**
- NEGATIVE gamma: best (dealers amplify momentum, supporting the trend continuation)
- POSITIVE gamma: marginal (dealers dampen momentum, may cause deeper pullbacks)
- NEUTRAL: acceptable with standard confirmation

**Reversion Model:**
- POSITIVE gamma: best (dealers dampen momentum, supporting mean reversion)
- NEGATIVE gamma: marginal (dealers amplify momentum, failed breakouts may extend further before reversing)
- NEUTRAL: acceptable with standard confirmation

**Key insight:** The two models have opposite gamma preferences. This is not a coincidence — it reflects the underlying mechanics. Trend continuation is amplified by negative gamma. Mean reversion is supported by positive gamma. Knowing the gamma regime helps you choose which model to apply.

---

## Risk-Reward Profile

| Model | Win rate | R:R | Expected value |
|-------|----------|-----|----------------|
| Trend Model | 60-65% | 2:1 to 3:1 | +1.2R to +1.8R |
| Reversion Model | 55-60% | 2:1 to 3:1 | +1.1R to +1.6R |

Both models produce similar expected value. The Trend Model has a slightly higher win rate because the trend provides directional confirmation. The Reversion Model has a slightly lower win rate because failed breakouts can extend before reversing.

---

## Common Mistakes

**1. Using the Trend Model in a balanced market**
The Trend Model requires imbalance. In a balanced market, LVN pullbacks don't continue — they reverse. Using the Trend Model in balance produces a string of losses. Identify the market state first.

**2. Using the Reversion Model in a trending market**
The Reversion Model requires a failed breakout. In a trending market, breakouts don't fail — they continue. Using the Reversion Model in a trend produces a string of losses. Identify the market state first.

**3. Not identifying balance vs imbalance correctly**
This is the most common mistake. Spend time on the market state identification section. If you're unsure, wait for clarity before entering either model.

**4. Ignoring the aggression requirement**
Both models require visible aggressive orders at the LVN. Without aggression, the pullback (Trend Model) or reversion (Reversion Model) may not have institutional participation. No aggression = no trade.

**5. Holding through the balance POC (Trend Model)**
70% of the time, price reverses from the balance area. The Trend Model target is the balance POC. Holding beyond it is a different trade. Take the profit.

**6. Targeting beyond the balance POC (Reversion Model)**
The Reversion Model ends at the balance POC. Holding beyond it is a different trade. The reversion is complete when price reaches the center of value.

**7. Trading during the first 30 minutes of RTH**
Opening range fakeouts mimic both imbalance breakouts and failed breakouts. The first 30 minutes produce too many false signals for both models. Wait until 10:00 AM at the earliest.

**8. Applying the wrong model to the current state**
If you're in imbalance, use the Trend Model. If you're in balance with a failed breakout, use the Reversion Model. Applying the wrong model to the current state is the fastest way to lose money with these setups.
