# Divergence Patterns — When the Rivers Disagree

## Overview

Divergence is the most analytically rich state in the Options Bias Engine. When all four rivers agree, the trade is obvious. When they disagree, the disagreement itself is the signal. Understanding WHY the rivers diverge, and what that divergence predicts, is where the highest-edge opportunities live.

This document catalogs every meaningful divergence pattern, explains the underlying mechanics, provides resolution timelines, and specifies how to trade each one.

The meta-rule: when three or more sources diverge without a clear explanation, the correct response is NO TRADE. Divergences resolve, but the resolution direction is uncertain until more data arrives. Patience is not a weakness here — it's the edge.

---

## Divergence Type 1: FLOW vs DARK (Distribution and Accumulation)

This is the most important divergence in the system. It represents the gap between what is visible to the market and what institutions are doing quietly.

### Pattern 1A: Flow Bullish + Dark Bearish (DISTRIBUTION)

**What it looks like on the surface:**
- Massive.com shows positive net call premium
- Call sweeps are present
- Price is rising or holding
- Sentiment appears bullish

**What is actually happening:**
Institutions are selling into the visible buying. The call flow on Massive may be retail traders and momentum algos chasing the move. Meanwhile, in dark pools, large participants are distributing their long positions. They need the visible buying to absorb their selling — without it, their exits would crater the price.

**Detection signals:**
- UW dark pool direction is net selling despite positive Massive flow
- Net dark premium is negative (dark pool put activity or call selling exceeds call buying)
- Institutional sweep alerts from UW are bearish or absent
- On Massive: call volume is high BUT a significant portion is at the bid (call sellers, not buyers). If calls-at-bid > calls-at-ask, the "bullish flow" is actually distribution.
- DOM: icebergs on the ask side (hidden sellers). Market buys are being absorbed without price advancing. Bids look thick but pull when tested (spoofed support).
- FlashAlpha: call OI is declining (positions being closed, not opened). Put OI is quietly building at lower strikes.

**Resolution:**
Price reverses to the downside. The visible buying exhausts itself, the institutional selling continues, and when the last retail buyer is in, the bid disappears. The reversal is often sharp because the retail longs who bought during distribution all have stops in roughly the same place.

**Timeline:** 30 minutes to 2 hours from the point of detection. Distribution is a process, not an event. The longer it takes, the more supply has been distributed, and the sharper the eventual reversal.

**Historical win rate of fading visible flow and following dark pool:** 65-72% when all three dark signals align (UW direction, net dark premium, institutional alerts).

**Trade:**
- Direction: Short
- Entry: Do NOT short during distribution (price is still supported). Wait for the FIRST sign of visible weakness — the first red candle with above-average volume after the distribution period ends. This is when the institutional selling continues but the retail buying has stopped.
- Stop: New high above the distribution zone (if price makes a new high, distribution failed or wasn't real)
- Target: Put wall or HVL (whichever is closer)
- Size: 75% of maximum (high conviction but not maximum because timing is uncertain)
- DOM confirmation required: Bids pulling (fake support disappearing), offers holding or reloading

### Pattern 1B: Flow Bearish + Dark Bullish (ACCUMULATION)

**What it looks like on the surface:**
- Massive.com shows positive net put premium
- Put sweeps present
- Price is falling or weak
- Sentiment appears bearish

**What is actually happening:**
Institutions are buying into the visible selling. The put flow may be retail panic, stop-outs, or momentum algos following the downtrend. Institutions are quietly accumulating in dark pools, using the visible selling to fill large long positions at favorable prices.

**Detection signals:**
- UW dark pool direction is net buying despite negative Massive flow
- Net dark premium is positive (dark pool call activity or put selling exceeds put buying)
- Institutional sweep alerts from UW are bullish or absent
- On Massive: put volume high but significant portion at the bid (put sellers, not buyers). Puts-at-bid > puts-at-ask = accumulation.
- DOM: icebergs on the bid side (hidden buyers). Market sells being absorbed without price declining. Offers look thick but pull when tested.
- FlashAlpha: put OI declining (positions being closed). Call OI quietly building at higher strikes.

**Resolution:**
Price reverses to the upside. The visible selling exhausts itself, institutional buying continues, and when the last retail seller is out, the offer disappears and price gaps up.

**Timeline:** 30 minutes to 2 hours. Same dynamics as distribution, inverted.

**Historical win rate:** 65-72% when all three dark signals align.

**Trade:**
- Direction: Long
- Entry: Wait for the FIRST sign of stabilization — first green candle with above-average volume after the accumulation period. Or: first candle where the downward momentum clearly stalls (lower volume on down bars, higher volume on up bars).
- Stop: New low below the accumulation zone
- Target: Call wall or HVL
- Size: 75% of maximum
- DOM confirmation required: Offers pulling (resistance disappearing), bids holding and reloading

### Distinguishing Distribution/Accumulation from Normal Flow

The key question: is the visible flow OPENING new positions or CLOSING existing ones?

- Opening: Premium paid at the ask. OI increasing. Unusual volume relative to OI.
- Closing: Premium paid at the bid. OI decreasing. Volume in line with existing OI.

Distribution = visible opening (retail buying) + dark closing (institutions selling their longs).
Accumulation = visible closing (retail selling) + dark opening (institutions buying new longs).

---

## Divergence Type 2: STRUCTURE vs DOM (Paper vs Reality)

This divergence reveals when the mathematical options structure exists on paper but isn't being supported by actual order flow. Or the reverse: when the order book is building support that the options structure doesn't yet reflect.

### Pattern 2A: Structure Positive + DOM Thin/Bearish (TRAP WARNING)

**What it looks like:**
- FlashAlpha shows positive GEX, price above flip, call wall above, put wall below
- The structural setup says levels should hold and price should be contained
- But the DOM shows thin bids, market sells dominating, no icebergs on the bid

**What is actually happening:**
The GEX structure was computed from yesterday's open interest. Today's flow has shifted — positions have been closed, new positions opened at different strikes, or the OI that created the structure is no longer being actively defended. The mathematical structure exists but the participants who created it are no longer in the market defending it.

This is "stale structure." The GEX levels are real in the sense that they were computed correctly, but they're no longer relevant because the underlying positions have changed.

**Detection:**
- FlashAlpha GEX is positive but OI has been declining (positions closing)
- The put wall level is being approached but no defense visible in DOM
- Massive shows put flow increasing (new put buying, not just hedging)
- Dark pool is selling (institutions not defending the level)
- DOM: bids thin at the put wall, no icebergs, market sells dominating

**Resolution:**
The level breaks. The mathematical structure fails because nobody is defending it. This often happens when GEX was computed from a large position that has since been rolled or closed.

**Trade:**
- This is a TRAP WARNING for long trades. If you were planning a put wall bounce (long), abort.
- Consider a wall break trade instead (see step5-setups/wall-break.md)
- Or simply wait for the DOM to show defense before entering

**Quantitative threshold:** If bid depth at the put wall is less than 50% of the 20-day average depth at that level, treat the wall as undefended regardless of what GEX says.

### Pattern 2B: Structure Negative + DOM Strong/Bullish (SUPPORT BUILDING)

**What it looks like:**
- FlashAlpha shows negative GEX, price below flip, regime D or E
- The structural setup says we're in dangerous territory — moves should accelerate
- But the DOM shows thick bids, icebergs on the bid, market buys dominating

**What is actually happening:**
Informed participants are building a floor that the options structure doesn't yet reflect. This could be:
1. A large institution accumulating before the GEX data updates
2. A market maker taking the other side of a large put position (creating positive gamma at that level even if aggregate GEX is negative)
3. A genuine support level from non-options sources (technical, fundamental, macro)

**Resolution:** Two possible outcomes, and this is the key uncertainty:
1. The book is right: support holds, price stabilizes, and eventually the GEX structure updates to reflect the new reality (transition from negative to positive gamma). This is the bullish resolution.
2. The book fails: the thick bids are absorbed and eventually pulled. The support was temporary (institutional accumulation that ran out of buying power, or a spoof). Price then drops sharply because the negative gamma regime amplifies the move.

**Trade:**
- This is a HIGH-RISK, HIGH-REWARD setup
- If taking it: Long with TIGHT stop (below the DOM support level). If the bids pull, exit immediately.
- Size: 50% maximum (uncertainty is high)
- Monitor DOM continuously — the moment bids start pulling, exit
- Confirmation needed: Dark pool buying (UW) to confirm the DOM support is institutional and not a spoof

**Quantitative threshold:** DOM support is "strong" if bid depth at the level is at least 2x the 20-day average depth at that price, AND the bids have reloaded at least twice after being hit.

---

## Divergence Type 3: FLOW vs STRUCTURE (Direction vs Regime)

This divergence occurs when the directional flow signal conflicts with the regime's expected behavior. The flow says "go this way" but the regime says "be careful."

### Pattern 3A: Flow Aggressively Bullish + Negative Gamma Regime (RISKY BULLISH)

**What it looks like:**
- Massive shows strong call buying, sweeps, blocks
- UW confirms institutional call buying
- But FlashAlpha shows negative GEX, price below flip, Regime D or E

**The conflict:**
The flow says buy. The regime says any move — up OR down — will be amplified. The bullish flow could be right, and the rally could be real. But if it fails, the reversal will be 2x to 3x as violent as it would be in positive gamma. The regime doesn't care about direction — it amplifies both.

**Resolution:**
Two scenarios:
1. Flow is right: Rally happens, and because negative gamma amplifies moves, the rally is actually LARGER than it would be in positive gamma. The flow signal was correct and the regime helped.
2. Flow is wrong (or exhausts): The rally fails, and the reversal is violent. Stops get hit, the negative gamma amplification kicks in, and the selloff accelerates.

**Trade:**
- If taking it: Long, but with TIGHT stops (tighter than you'd use in positive gamma)
- The stop must be placed where the trade is definitively wrong, not just temporarily wrong
- Target: The next structural level (call wall if one exists, or the gamma flip if price can reclaim it)
- Size: 50% maximum (regime risk is elevated)
- DOM confirmation: MUST see aggressive market buying, not just passive bid depth. In negative gamma, passive bids can disappear instantly. You need to see actual aggression.

**Quantitative threshold:** Flow is "aggressively bullish" if net call premium is positive by at least $15M (QQQ/NDX) AND call sweeps outnumber put sweeps by at least 3:1 in the last 30 minutes.

### Pattern 3B: Flow Aggressively Bearish + Positive Gamma Regime (CUSHIONED BEARISH)

**What it looks like:**
- Massive shows strong put buying, sweeps, blocks
- UW confirms institutional put buying
- But FlashAlpha shows positive GEX, price above flip, Regime A or B

**The conflict:**
The flow says sell. The regime says dealers will automatically buy dips. The bearish flow is fighting against the mechanical stabilizing force of positive gamma.

**Resolution:**
The selloff is dampened. Price may decline but it will find support at the put wall (where dealers must buy to hedge their short puts). The bearish flow creates a great LONG entry at the put wall rather than a sustained downtrend.

**Trade:**
- Do NOT short aggressively in positive gamma just because flow is bearish
- Instead: Wait for price to reach the put wall, then look for a long entry (Wall Bounce setup)
- The bearish flow tells you WHERE price is going (toward the put wall), not that it will break through
- If the put wall breaks despite positive gamma, THEN the regime has changed and the bearish flow was right

**Exception:** If the bearish flow is extreme (net put premium > $30M, put sweeps 5:1 over calls, dark pool selling), the flow may be strong enough to overwhelm the positive gamma dampening. In this case, treat as a potential regime transition (see step5-setups/gamma-flip-cross.md).

---

## Divergence Type 4: DARK vs DOM (Hidden vs Visible Book)

This divergence reveals the timing gap between institutional activity in dark pools and its eventual impact on the public order book.

### Pattern 4A: Dark Buying + DOM Ask-Heavy (DELAYED IMPACT)

**What it looks like:**
- UW shows dark pool net buying, institutional call activity
- But the DOM shows ask depth > bid depth, market sells dominating

**What is actually happening:**
Institutions are accumulating in dark pools, but the fills haven't yet shown up in the public order book. Dark pool trades are reported with a delay (5-15 minutes for UW). The DOM is showing the current state of the lit market, which hasn't yet absorbed the institutional buying.

**Resolution:**
The DOM will shift in 5-15 minutes as the dark pool fills get reflected in the market. The ask-heavy DOM is a LEADING indicator of a coming DOM shift to bid-heavy. This is a predictive divergence.

**Trade:**
- This is a LEADING SIGNAL for a long entry
- Wait for the DOM to begin shifting (bid depth increasing, market buys picking up)
- Entry: When DOM confirms (bid depth > ask depth, market buys > sells)
- Stop: Below the dark pool accumulation zone (if dark pool was buying at 19,500, stop below 19,490)
- Target: Call wall or HVL
- Size: 75% (high conviction once DOM confirms)
- Time sensitivity: If DOM hasn't shifted within 20 minutes of the dark pool signal, the dark pool buying may have been absorbed without impact. Reduce conviction.

### Pattern 4B: Dark Selling + DOM Bid-Heavy (ARTIFICIAL SUPPORT)

**What it looks like:**
- UW shows dark pool net selling, institutional put activity
- But the DOM shows bid depth > ask depth, market buys dominating

**What is actually happening:**
Someone is propping up the visible order book while institutions exit in dark pools. The thick bids in the DOM may be:
1. A market maker providing liquidity while institutions sell through them
2. A large participant creating the appearance of support to facilitate their own dark pool selling
3. Genuine retail buying that is being overwhelmed by institutional dark pool selling

**Resolution:**
The artificial support evaporates once the dark pool selling finishes. The thick bids pull, and price drops sharply because the support was never real.

**Trade:**
- This is a TRAP WARNING for long trades
- If you're long and see this pattern, tighten your stop or exit
- If considering a long: do NOT enter based on the DOM alone. The dark pool selling invalidates the DOM signal.
- Consider a short: Wait for the DOM support to crack (bids start pulling), then short with a stop above the artificial support zone.

**Quantitative threshold:** Dark selling is "significant" if UW shows net dark premium negative by at least $10M AND dark pool direction has been consistently bearish for at least 30 minutes.

---

## Divergence Type 5: FLOW vs FLOW (Massive vs UW Disagree)

This divergence occurs when the two flow sources give conflicting readings. It's less common than the other divergence types but important to understand.

### Pattern 5A: Massive Bullish + UW Bearish

**What it looks like:**
- Massive shows positive net call premium, call sweeps
- UW shows bearish institutional flow, dark pool selling

**The conflict:**
Massive captures a broader mix of flow including retail, algorithmic, and institutional. UW focuses more on institutional and dark pool activity. When they disagree, the question is: which is driving the market?

**Resolution framework:**
1. Check WHICH data is driving the disagreement. Is Massive bullish because of retail call buying (small size, many trades) or institutional call buying (large size, few trades)?
2. If Massive is bullish due to retail flow and UW is bearish due to institutional flow: generally trust UW. Institutions have more information and more capital. The retail buying is likely being distributed into.
3. If Massive is bullish due to institutional blocks and UW is bearish due to dark pool: check the timing. Massive may be more current (real-time) while UW has a reporting lag. The institutional blocks on Massive may be more recent than the dark pool data on UW.

**Trade:**
- When Massive and UW disagree, reduce conviction by one level
- If the disagreement is retail vs. institutional: follow UW (institutional)
- If the disagreement is timing-based: wait 15 minutes for UW to update before deciding

### Pattern 5B: Massive Bearish + UW Bullish

Mirror of 5A. Visible flow is bearish but institutional/dark pool is bullish. This is the accumulation pattern. Follow UW (institutional).

### Freshness Check

Always check the timestamp of the data you're comparing. UW dark pool data can lag by 5-15 minutes. If Massive is showing a strong move in the last 5 minutes and UW data is 15 minutes old, the UW data may not yet reflect the current situation. In fast-moving markets, weight Massive more heavily for the most recent 15 minutes, then re-check UW once it updates.

---

## Meta-Rules for Divergence Trading

### Rule 1: Three or More Sources Diverging = No Trade

If STRUCTURE, FLOW, and DARK all point in different directions, the market is genuinely uncertain. No edge exists. Wait for alignment.

The exception: if three sources agree and one disagrees, the disagreement is a yellow flag, not a red flag. Reduce size but don't necessarily skip the trade.

### Rule 2: Divergences Have Timelines

Every divergence resolves. The question is when and in which direction. If you can't identify the likely resolution direction with at least 60% confidence, don't trade the divergence.

Typical resolution timelines:
- Flow vs Dark: 30 minutes to 2 hours
- Structure vs DOM: 15 minutes to 1 hour
- Flow vs Structure: Resolves when price reaches the structural level (put wall, call wall, flip)
- Dark vs DOM: 5-20 minutes (DOM catches up to dark pool)
- Flow vs Flow: 15-30 minutes (UW updates to match Massive, or Massive reverses)

### Rule 3: The Divergence Direction Tells You the Trade

When you identify a divergence, the trade is usually to follow the LESS VISIBLE signal:
- Flow vs Dark: Follow Dark (institutional, less visible)
- Structure vs DOM: Follow DOM (real-time, ground truth)
- Flow vs Structure: Follow Structure (mechanical, mathematical)
- Dark vs DOM: Follow Dark (leading indicator)
- Massive vs UW: Follow UW (institutional)

### Rule 4: Divergences Compound

A single divergence is a yellow flag. Two simultaneous divergences (e.g., Flow vs Dark AND Structure vs DOM) is a red flag. Three simultaneous divergences = stay out entirely.

### Rule 5: Divergences Are Not Permanent

A divergence that existed 30 minutes ago may have resolved. Always re-check before acting on a divergence signal. The most dangerous trade is acting on a divergence that has already resolved in the wrong direction.

---

## Divergence Scoring in the Conviction Matrix

Divergences modify the conviction score from the conviction matrix (see conviction-matrix.md):

| Divergence Type | Conviction Adjustment |
|---|---|
| Flow vs Dark (clear distribution/accumulation) | -1 to the visible flow dimension |
| Structure vs DOM (stale structure) | -1 to the STRUCTURE dimension |
| Flow vs Structure (direction vs regime) | No adjustment; apply regime-specific rules |
| Dark vs DOM (delayed impact) | +1 to DARK dimension (leading signal) |
| Massive vs UW (retail vs institutional) | -1 to FLOW dimension; +0.5 to DARK |

These adjustments are applied BEFORE the final conviction level is determined. A trade that scores 4/5 before divergence adjustments may drop to 3/5 or 2/5 after applying the relevant divergence penalties.

---

## Practical Divergence Detection Checklist

Before every trade, run this checklist:

1. Does Massive flow direction match UW dark pool direction? If not, identify the divergence type and apply the appropriate rule.
2. Does FlashAlpha structure match what the DOM is showing? If GEX says levels should hold but DOM shows no defense, flag as stale structure.
3. Does the flow direction match the regime's expected behavior? If flow is fighting the regime, apply the regime-specific rules.
4. Does UW dark pool direction match the DOM? If dark is buying but DOM is ask-heavy, flag as delayed impact (leading signal).
5. Are Massive and UW internally consistent? If they disagree, identify whether it's a timing issue or a genuine retail vs. institutional divergence.

If any of these checks flags a divergence, apply the appropriate conviction adjustment before sizing the trade.
