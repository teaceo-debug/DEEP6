# LVN Retest as Support/Resistance

**Breakout Confirmation — The Pullback Entry**

## Overview

After price breaks through an LVN with acceptance, wait for the pullback retest. The broken LVN now acts as new support or resistance — a polarity flip. What was a thin, frictionless zone becomes a structural reference point that the market respects on the retest.

This is not the breakout entry. That's `lvn-breakout-acceleration.md`. This is the pullback entry after the breakout is already confirmed. Lower risk than chasing the initial break, slightly lower reward, but higher probability because you have two confirmations: the breakout itself and the retest rejection.

The setup works because institutions that missed the initial breakout use the retest as their entry. Their buying (or selling) at the broken LVN is what creates the rejection and continuation.

---

## Setup Conditions

All conditions must be met. The acceptance confirmation is the most critical.

1. **Breakout already occurred** through the LVN with acceptance (minimum 2 bars on 5-minute chart closing fully beyond the LVN boundary)
2. **Volume on the breakout was >= 1.2x session average** (confirms the breakout was real, not a probe)
3. **Price has pulled back to retest the broken LVN** from the breakout side
4. **Rejection signal at the retest level:** rejection candle, absorption, or failed re-entry into the LVN
5. **CVD not diverging against the retest direction** (CVD should be trending with the original breakout)
6. **Retest occurs within 60 minutes of the breakout** (see timing rules below)

---

## Entry Rules

**Entry trigger:** Rejection or absorption confirmed at the broken LVN during the retest.

Confirmation requires at least one of:
- Rejection candle: wick pointing back into the LVN with close in the breakout direction
- Absorption: high volume at the LVN level with minimal price movement
- Failed re-entry: price enters the LVN but closes back on the breakout side within the same bar

**Entry type:** Limit order at the broken LVN boundary. Place the order before price reaches the level — do not chase.

**Entry direction table:**

| Breakout direction | Retest behavior | Entry |
|--------------------|-----------------|-------|
| Bullish (upward break) | Pullback to LVN from above | Long at LVN upper boundary |
| Bearish (downward break) | Rally to LVN from below | Short at LVN lower boundary |

**Timing window for entry:** The retest must occur within 60 minutes of the original breakout. After 60 minutes, the structural significance of the retest diminishes. If no retest occurs within 60 minutes, the level may be too far from current price — skip the trade.

---

## Stop Loss Rules

**Stop placement:** Back inside the prior value area.

If price returns fully into the prior Value Area (the HVN cluster the breakout came from), the breakout has failed. The LVN is no longer acting as support/resistance. Exit immediately.

- For long entries (bullish breakout retest): stop below the prior Value Area upper boundary
- For short entries (bearish breakout retest): stop above the prior Value Area lower boundary

This stop is wider than the breakout entry stop (which was just inside the LVN). That's the tradeoff for the higher-probability entry. The R:R is slightly lower, but the win rate is higher.

**Stop adjustment rules:**
- Move to breakeven after price travels 40% of the distance to the target
- Trail to prior swing after 70% of the distance to target
- If price re-enters the LVN on a 5-minute close, exit immediately — do not wait for the stop

---

## Profit Target Rules

**Primary target:** The next major HVN or structural level beyond the breakout.

The breakout has already established directional intent. The retest entry is joining that move. Target the same level the breakout was heading toward.

**Target scaling:**
- 50% of position at the near edge of the target HVN
- Remaining 50% at the HVN POC

**If the target HVN was already reached before the retest:** The trade is late. The breakout has already run its course. Do not enter.

**Extended target:** If the target HVN is thin or price blows through it with volume, extend to the next structural level. This is rare but happens in strong trend days.

---

## NQ-Specific Rules

**Retest timing:** NQ retests typically occur within 15-30 minutes of the breakout. If no retest within 60 minutes, the level is likely too far from current price. Skip the trade.

**Retest depth:** Price should touch the LVN boundary but not close inside it. A close inside the LVN on a 5-minute bar is a failed retest — the breakout is in trouble. Exit any existing position.

**Volume on retest:** Retest volume should be lower than breakout volume. High volume on the retest suggests the breakout is being contested, not confirmed. If retest volume exceeds breakout volume, treat it as a potential reversal, not a continuation.

**NQ point reference:** The LVN boundary used as the retest level should be defined to the nearest 0.25 point. Use the exact boundary from the original LVN identification, not a rounded approximation.

**Session filter:** Best during 10:30 AM to 2:00 PM ET. Retests during the first 30 minutes of RTH are unreliable. After 2:00 PM, volume thins and retests may not produce clean rejection signals.

---

## Order Flow Confirmation

Required before entry. At least two of three must be present.

**1. Absorption at the retest level**
- Footprint shows high volume at the LVN boundary with minimal price movement
- The side trying to push back through the LVN (against the breakout direction) is being absorbed
- Large bid/ask numbers at the boundary price levels

**2. CVD confirmation**
- CVD trending in the breakout direction
- No divergence: CVD not making a lower high (for bullish breakout) or higher low (for bearish breakout)
- CVD should be flat or continuing in the breakout direction during the retest

**3. Imbalance confirmation**
- Footprint imbalances on the retest rejection bar favor the breakout direction (3:1 or better)
- No stacked imbalances pushing back through the LVN (would suggest the breakout is failing)

If only one signal is present, reduce size to 50% or skip.

---

## Gamma Regime Filter

**NEGATIVE gamma (best for this setup):**
- Dealers amplify momentum. The breakout was likely strong in negative gamma.
- Retests in negative gamma are typically shallow and fast — institutions buy the dip aggressively.
- Highest probability of clean rejection and continuation.

**POSITIVE gamma (marginal):**
- Dealers dampen momentum. Breakouts in positive gamma are less common and weaker.
- If a breakout did occur in positive gamma, the retest may be deeper and messier.
- Require all three OF signals before entering in positive gamma.

**NEUTRAL gamma (acceptable):**
- Near the gamma flip level. Standard confirmation requirements apply.

---

## Key Distinction from Related Setups

This setup is frequently confused with two others. The differences matter.

| Setup | When to use | Entry timing |
|-------|-------------|--------------|
| `lvn-breakout-acceleration.md` | During the initial breakout | 2nd bar closing beyond LVN |
| `lvn-retest-support.md` (this file) | After breakout, on the pullback | Rejection at broken LVN during retest |
| `lvn-rejection-fade.md` | Fading a probe into a fresh LVN | Rejection at LVN boundary (no prior breakout) |

The retest setup requires a prior breakout. If there was no breakout, you're in rejection-fade territory. If you're entering during the initial breakout, you're in breakout-acceleration territory.

---

## Risk-Reward Profile

| Metric | Typical range |
|--------|---------------|
| Win rate | 60-65% |
| R:R per trade | 2:1 to 3:1 |
| Stop width | Prior VA boundary to LVN (wider than breakout stop) |
| Target distance | LVN to next HVN (same as breakout target) |
| Expected value | +1.2R to +1.8R per trade |

Slightly lower R:R than the breakout entry, but higher probability because you have two confirmations. The expected value is similar. Choose based on which entry you can execute more cleanly.

---

## Common Mistakes

**1. Entering before acceptance is confirmed**
If the breakout hasn't been confirmed with 2 bars closing beyond the LVN, there's no retest setup. You're just fading a probe. Use `lvn-rejection-fade.md` for that.

**2. Entering if price fully re-enters the prior Value Area**
A return to the prior VA means the breakout failed. The LVN is no longer acting as support/resistance. Do not enter — exit any existing position.

**3. Waiting too long for the retest**
If no retest occurs within 60 minutes, the level is too far from current price. The institutional buyers who would defend the retest have moved on. Skip the trade.

**4. Ignoring retest volume**
High volume on the retest is a warning sign. It means the breakout is being contested. Low volume on the retest (with rejection) is the clean signal.

**5. Confusing this with the breakout entry**
The breakout entry is during the initial move. The retest entry is after the pullback. They have different stops, different timing, and different confirmation requirements. Don't mix them up.

**6. Targeting the same level as a fresh breakout**
If the target HVN was already reached before the retest, the trade is over. Don't enter a retest trade when the target has already been hit.

**7. Skipping the retest if it doesn't come**
A missed trade is not a loss. If the retest doesn't occur within 60 minutes, the market moved on. Accept it and look for the next setup.
