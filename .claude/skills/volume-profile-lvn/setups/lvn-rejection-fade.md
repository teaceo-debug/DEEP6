# LVN Rejection Fade

**First Touch Only — Edge Decays Rapidly After**

## Overview

Fade the first touch of a fresh LVN. The structural edge is highest on the virgin test: 70-80% rejection probability. After each subsequent test, that edge decays rapidly as the LVN fills with volume and loses its structural significance.

The logic is simple. An LVN formed because price moved through that zone quickly in a prior session — no one wanted to trade there. When price returns, the same structural vacuum exists. Buyers and sellers who missed the original move are waiting at the edges of the adjacent HVNs. The LVN itself has no committed participants, so the first probe into it typically gets rejected back toward the HVN it came from.

Best in positive gamma regime. Worst in negative gamma.

---

## Setup Conditions

All conditions must be met. The touch-count rule is the most important.

1. **Fresh LVN identified** on the session or composite profile with clear HVN clusters on both sides
2. **This is the FIRST touch** since the LVN formed (virgin test). Track touch count explicitly.
3. **Price approaching from the HVN side** — not already inside the LVN
4. **Absorption visible on footprint** at or near the LVN boundary: high volume, minimal price movement, large wicks
5. **Delta divergence present:** price making a new extreme toward the LVN but CVD not confirming (CVD flat or reversing)
6. **Gamma regime: POSITIVE preferred** (dealers hedge against price movement, supporting mean reversion)
7. **No breakout catalyst present** (no news, no major level breach, no trend day conditions)

---

## Touch Decay Table

This is the core rule of the setup. Do not trade the 3rd touch.

| Touch number | Rejection probability | Trade decision |
|--------------|----------------------|----------------|
| 1st touch | 70-80% | TRADE with full size |
| 2nd touch | 40-50% | TRADE only with strong OF confirmation (all 3 signals) |
| 3rd touch | <20% | DO NOT TRADE — LVN is filling |
| 4th+ touch | <10% | LVN no longer valid — remove from map |

After the 3rd touch, the LVN has absorbed enough volume to lose its structural significance. Price is now comfortable trading there. The zone is transitioning to an HVN. Remove it from your active LVN map.

---

## Entry Rules

**Entry trigger:** Rejection confirmed at the LVN boundary.

Confirmation requires at least one of:
- Long wick (>50% of bar range) pointing into the LVN with close back toward the HVN
- Failed break: price enters LVN, then closes back outside it on the same bar
- Absorption candle: high volume bar with minimal net movement (see NQ-specific criteria below)

**Entry type:** Limit order at the LVN boundary after rejection signal appears. Do not enter before the rejection is confirmed.

**Entry direction table:**

| Price approaching from | Rejection direction | Entry |
|------------------------|--------------------|----|
| Below (bullish probe into LVN) | Short (fade the probe) | Short at LVN lower boundary |
| Above (bearish probe into LVN) | Long (fade the probe) | Long at LVN upper boundary |

**Timing:** Entry must occur within 2 bars of the rejection signal. If price has already moved 30%+ of the way back to the HVN, the entry is late — skip it.

---

## Stop Loss Rules

**Stop placement:** Beyond the LVN boundary on the opposite side from entry.

- For short entries (fading bullish probe): stop above the LVN upper boundary
- For long entries (fading bearish probe): stop below the LVN lower boundary

If price fully crosses the LVN and closes beyond the far boundary, the rejection has failed. The LVN is being broken, not rejected. Exit immediately.

**Stop adjustment rules:**
- Move to breakeven after price travels 40% of the distance to the target
- Trail to prior swing after 70% of the distance to target
- Do not widen the stop. If the LVN is wide enough that the stop feels uncomfortable, the LVN is not clean enough to trade.

---

## Profit Target Rules

**Primary target:** POC of the HVN the price came from.

The fade is a mean-reversion trade back toward the center of value. The POC is where the most volume traded — it's the gravitational center. That's where the trade ends.

**Target scaling:**
- 60% of position at the near edge of the origin HVN
- Remaining 40% at the HVN POC

**Extended target:** If the origin HVN is thin or price blows through it, extend to the opposite side of the Value Area.

**Do not target the opposite HVN.** This is a fade, not a breakout. The trade ends at the origin HVN, not at the far side of the LVN.

---

## NQ-Specific Rules

**Absorption candle criteria for NQ:**
- Bar volume >= 2x the 20-bar rolling average
- Net price movement <= 25% of the bar's total range (high to low)
- Close in the direction of the fade (away from the LVN)
- Large wick pointing into the LVN (>40% of bar range)

All four criteria must be present for an absorption candle to count as confirmation.

**LVN freshness:** An LVN is "fresh" if it has not been touched since it formed. Track the formation date. LVNs older than 5 sessions that have never been tested are still fresh. LVNs that were tested even once in a prior session are on their 2nd touch.

**Time filter:** Best during 10:30 AM to 2:00 PM ET. First 30 minutes of RTH (9:30-10:00 AM) produce too many false rejections during price discovery. After 2:00 PM, volume thins and absorption signals become unreliable.

**NQ point reference:** LVN boundaries should be at least 15 NQ points wide to be tradeable. Narrower LVNs don't provide enough room for the rejection signal to form cleanly.

---

## Order Flow Confirmation

Required before entry. At least two of three must be present.

**1. Absorption (required)**
- High volume at the LVN boundary with minimal price movement
- Footprint shows large bid/ask numbers at the boundary price levels
- The aggressive side (buyers probing up or sellers probing down) is being absorbed by passive orders

**2. Delta divergence (required)**
- Price making a new extreme toward the LVN
- CVD not confirming: flat, declining, or reversing
- This divergence signals that the aggressive move is losing participation

**3. Footprint rejection signal**
- Large wick on the footprint bar pointing into the LVN
- Imbalances on the rejection bar favor the fade direction (3:1 or better)
- No stacked imbalances in the probe direction (would suggest breakout, not rejection)

If only one signal is present, skip the trade or reduce size to 50%.

---

## Gamma Regime Filter

**POSITIVE gamma (trade this setup):**
- Dealers are long gamma. They hedge by selling into rallies and buying into dips.
- This dampens price movement and supports mean reversion.
- LVN rejections in positive gamma have the highest probability of returning to the HVN POC.
- Identify: GEX is positive, price is below the gamma flip level, FlashAlpha shows positive net GEX.

**NEGATIVE gamma (do not trade this setup):**
- Dealers are short gamma. They hedge with price movement, amplifying momentum.
- LVN probes in negative gamma frequently break through rather than reject.
- In negative gamma, use `lvn-breakout-acceleration.md` instead.

**NEUTRAL gamma (marginal):**
- Near the gamma flip level. Dealer hedging is minimal.
- Only trade if absorption and delta divergence are both exceptionally clear.

---

## Risk-Reward Profile

| Metric | Typical range |
|--------|---------------|
| Win rate (1st touch) | 70-80% |
| Win rate (2nd touch) | 40-50% |
| R:R per trade | 1:2 to 1:3 |
| Stop width | LVN width (typically 10-25 NQ points) |
| Target distance | HVN POC (typically 20-60 NQ points) |
| Expected value | +1.4R to +2.0R per trade (1st touch) |

The win rate is the edge here, not the R:R. This is a high-probability, moderate-reward setup. Do not try to squeeze 3:1 out of it by targeting the far HVN — that turns a high-probability trade into a coin flip.

---

## Common Mistakes

**1. Fading the 2nd or 3rd touch without strong confirmation**
The edge decays fast. A 2nd touch with weak confirmation is a losing trade. A 3rd touch is almost always a losing trade. The touch count rule exists for a reason.

**2. Fading in negative gamma**
Dealers amplify momentum in negative gamma. What looks like a rejection at the LVN boundary is often just a brief pause before the breakout continues. Check gamma before every trade.

**3. No absorption confirmation**
Price touching an LVN is not a signal. Price touching an LVN with absorption visible on the footprint is a signal. The difference is everything.

**4. Entering before the rejection is confirmed**
Anticipating the rejection and entering as price approaches the LVN is a common mistake. Wait for the wick, the failed break, or the absorption candle. Entering early means your stop is inside the LVN, which is structurally meaningless.

**5. Targeting the far HVN**
This is a fade, not a breakout. The trade ends at the origin HVN POC. Holding for the far side of the LVN turns a high-probability mean-reversion trade into a low-probability directional bet.

**6. Not tracking touch count**
If you don't know how many times price has touched this LVN, you don't know your edge. Maintain a live LVN map with touch counts. Remove LVNs after the 3rd touch.

**7. Trading during the first 30 minutes of RTH**
Opening range price discovery produces false absorption signals. The market is still finding its footing. Wait until 10:00 AM at the earliest, 10:30 AM for best conditions.
