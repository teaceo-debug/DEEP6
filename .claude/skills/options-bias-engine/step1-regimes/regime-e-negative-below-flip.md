# Regime E: Negative Gamma, Price Below Flip

## Classification Conditions

- `total_gex < 0` (FlashAlpha)
- `NQ_spot < NQ_gamma_flip - 25 ticks` (spot comfortably below the flip)
- No macro event within 60 minutes
- Not 0DTE pin conditions

Regime E is the trending bear. It's the most dangerous regime for longs and the most profitable regime for shorts. The pro-cyclical dealer hedging creates a cascade dynamic where every decline accelerates the next decline. Levels that would be support in positive gamma become trapdoors. Bounces are sharp but brief. The regime punishes patience and rewards aggression on the short side.

## The Cascade Mechanics

Understanding the cascade is essential. It's not just "price goes down." It's a self-reinforcing feedback loop driven by dealer hedging.

**The cascade sequence:**
1. Price falls below the gamma flip (Regime D → Regime E transition)
2. Dealers are net short gamma. As price falls, their short put positions gain delta.
3. To rehedge, dealers SELL NQ futures. This selling adds to the decline.
4. The decline triggers stop-losses from longs who bought the "recovery" in Regime D.
5. Stop-triggered selling adds more downward pressure.
6. Dealers sell more to rehedge the additional delta from the further price decline.
7. The cycle repeats. Each iteration pushes price lower.

This is not a linear decline. It's exponential in the early stages. The first 50 NQ points below the flip can happen in 5 minutes. The next 50 points can happen in 3 minutes. The cascade accelerates until one of these stops it:
- Price reaches a structural level with genuine buying (not just gamma-based)
- Total_gex turns positive (regime change)
- A macro catalyst reverses sentiment
- The cascade exhausts itself (sellers run out of supply)

## The Put Wall as Trapdoor

In Regime A and C, the put wall is a floor. In Regime E, the put wall is a trapdoor.

**Why the put wall fails in Regime E:**

In positive gamma, the put wall has mechanical dealer buying behind it. In negative gamma, the dealer hedging is pro-cyclical. When price hits the put wall in Regime E:

1. Price approaches the put wall from above
2. Brief hesitation (the wall's gamma concentration creates a momentary pause)
3. This pause gives false hope to longs ("the floor is holding")
4. The pause is brief because the negative gamma amplification overcomes the wall's resistance
5. Price breaks through the wall
6. The break accelerates because the negative gamma amplification is now working at maximum strength (highest gamma concentration = highest amplification at the wall)
7. The cascade below the wall is faster than the cascade above it

**The false hope pattern:** The put wall in Regime E almost always produces a 5-15 tick bounce before breaking. This bounce is the trapdoor. Longs who buy the bounce get caught when the wall breaks. The bounce is not a reversal. It's the wall's last gasp before the cascade resumes.

**Quantitative rule:** In Regime E, do not buy any bounce at the put wall unless ALL of the following are true:
1. total_gex is turning positive (FlashAlpha)
2. Massive shows put buying stopping AND call buying starting
3. Unusual Whales shows dark pool buying at the wall
4. Rithmic DOM shows iceberg bids absorbing market sells

If even one of these is missing, the bounce is a trap. Do not buy it.

## Four-River Reading in Regime E

### River 1: FlashAlpha (GEX Structure)

**What to read:**
- `total_gex`: Negative. Watch the magnitude. Is it becoming more negative (cascade deepening) or less negative (potential recovery)?
- `gamma_flip`: The most important level. Price is below it. The flip is the target for any recovery.
- `put_wall`: The next structural level below. In Regime E, it's a trapdoor, not a floor.
- `dex` (delta exposure): Increasingly negative DEX means dealers are net short delta. They're positioned for further downside. This is a bearish confirmation.
- `vex` (vanna exposure): If VIX is rising, vanna flows are bearish (dealers selling as vol rises). This amplifies the cascade.

**Recovery signals (rare in Regime E):**
- total_gex approaching zero from below. The regime is recovering.
- total_gex crossing zero: Regime E → Regime D transition. The cascade may be ending.
- Gamma flip declining (moving toward spot). The flip is coming down to meet price. This can happen if put OI is being closed (puts expiring or being bought back).

**Cascade deepening signals:**
- total_gex becoming more negative. The cascade is accelerating.
- Gamma flip rising (moving away from spot). The flip is getting further above price. Recovery is harder.
- DEX becoming more negative. Dealers are more short delta.

### River 2: Massive.com (Options Flow)

**Cascade continuation signals:**
- Put sweeps DOMINATING. Aggressive, large-premium put buying. This is directional positioning for further downside.
- Put OI INCREASING at strikes below current price. New positions being established below the floor.
- Call premium EVAPORATING. Call buying is absent or declining. No one is positioning for a recovery.
- Call OI DECLINING. Existing call longs are closing (taking losses or cutting exposure).
- 0DTE put volume surging. Gamma-seeking put buyers are piling in.

**The call buying trap:** In Regime E, call buying sometimes appears. This is almost always CLOSING of existing short positions (put sellers buying back their puts, which shows up as call buying in some flow aggregators). It is NOT new bullish positioning. Distinguish by watching OI:
- If call OI is DECLINING while call volume is high: Closing, not opening. Bearish.
- If call OI is INCREASING while call volume is high: New longs. Potentially bullish. But verify with other rivers.

**The ONLY buy signal from Massive in Regime E:**
- Net call premium INCREASING (not just volume, but premium)
- Call OI INCREASING at strikes above the gamma flip
- Put sweeps STOPPING (not just slowing, stopping)
- Put OI DECLINING (existing puts being closed)

All four must be present simultaneously. If even one is missing, the call buying is not a reversal signal.

### River 3: Unusual Whales (Dark Pool)

**Cascade continuation signals:**
- Dark pool SELLING. Institutions are distributing. The cascade has institutional backing.
- Large dark pool prints ($30M+) at or below current price. Institutional short positioning.
- Dark pool selling in QQQ-correlated names. Sector-wide institutional distribution.
- Dark pool prints appearing at progressively lower prices. Institutions are chasing the decline.

**The ONLY buy signal from Unusual Whales in Regime E:**
- Dark pool BUYING appearing at a specific level. This is the most reliable bottom signal.
- The dark pool buying must be LARGE ($30M+) and at a level that makes structural sense (previous major support, round number, etc.).
- Multiple dark pool buying prints within 30 minutes. Sustained accumulation, not a single trade.

**The dark pool bottom signal:** When dark pool buying appears in Regime E, it doesn't mean the bottom is in. It means institutions are starting to accumulate. The bottom may be 50-100 NQ points lower. But it's the first signal that the cascade is approaching exhaustion. Reduce short size when dark pool buying appears. Do not go long until the gamma flip is reclaimed.

### River 4: Rithmic MBO (NQ Order Book)

**Cascade continuation signals:**
- Thin bids. The bid stack is shallow. Market sells hit the bid and price drops immediately.
- Offers STACKING. Sellers are queuing up. The offer stack is thick and reloads after being hit.
- DOM asymmetry: Offer depth >> Bid depth. The market is positioned for further downside.
- Market sells hitting the bid relentlessly. No absorption. The floor is not holding.
- Offers appearing below the current price. Sellers are willing to sell lower.

**Rally characteristics in Regime E (how to identify them as traps):**
- Sharp but SHORT. 1-3 bars on a 1-minute chart.
- Low volume. The rally happens on thin volume because there are no real buyers.
- No sweep confirmation. No large buy orders driving the rally.
- DOM shows offers immediately reload above the rally high. Sellers return instantly.
- Bid depth thins as price rises. The rally is running out of buyers.

**The ONLY buy signal from Rithmic in Regime E:**
- Iceberg bids appearing at a specific level. Large hidden buy orders absorbing market sells.
- Absorption: Large market sells hitting the bid without price declining. The floor is eating the selling.
- DOM asymmetry reversing: Bid depth approaching offer depth.
- Offers being pulled above current price. Sellers are withdrawing.

## Trade Style: Short Rallies, Never Buy Dips

The cardinal rule of Regime E: **Never buy the dip. Every bounce is a selling opportunity.**

In positive gamma, buying dips is the correct strategy. In Regime E, buying dips is how you get destroyed. The pro-cyclical amplification means that what looks like a bottom can be the beginning of the next leg down.

### Short Trade: Fading the Bounce

**Entry conditions:**
- Price has bounced 20-40 NQ points from a recent low
- Massive: Call buying is absent or declining. Put buying is pausing (not reversing).
- Unusual Whales: No dark pool buying. Dark pool selling may be present.
- Rithmic DOM: Offers reloading above the bounce high. Bid depth thinning as price rises.
- The bounce is on declining volume (1-minute chart).

**Entry:** Short NQ at the top of the bounce. Use a limit order at the bounce high or within 10 ticks of it. If the bounce has already peaked and price is declining, enter on the first lower high.

**Stop:** 20 ticks above the bounce high. If price makes a new high above the bounce, the rally may be real. Exit.

**Target:** The previous low. If the previous low breaks, trail the stop and target the next structural level below.

**Expected win rate:** 65-70% in strong negative gamma (total_gex < -$2B). 55-60% in moderate negative gamma.

### Short Trade: Gamma Flip Rejection

When price rallies toward the gamma flip from below, this is the highest-conviction short in Regime E.

**Entry conditions:**
- Price rallies to within 25 ticks of the gamma flip
- Massive: Call buying is declining as price approaches the flip (rally losing momentum)
- Unusual Whales: No dark pool buying above the flip
- Rithmic DOM: Offers reloading at the flip level. Iceberg offers visible.
- FlashAlpha: total_gex still negative, flip stable

**Entry:** Short NQ at or within 10 ticks of the gamma flip. Limit order.

**Stop:** 25 ticks above the gamma flip. If price closes above the flip by 25 ticks, the regime is transitioning to D. Exit and reclassify.

**Target:** The previous low. Then the put wall (which will likely break). Then the next structural level.

**Expected win rate:** 70-75%. The gamma flip is the most important level in the system. In Regime E, it's the ceiling.

## The ONLY Buy Signal in Regime E

The only time to go long in Regime E is when the regime is transitioning to Regime D. This requires ALL of the following:

1. **Price reclaims the gamma flip** (NQ_spot > NQ_gamma_flip + 25 ticks)
2. **Flow shifts to net call** (Massive: call buying > put buying, call OI increasing)
3. **Dark pool buying appears** (Unusual Whales: dark pool buying at or above the flip)

All three must confirm. This is the Setup 3 (Gamma Flip Cross) trade. It's the highest-conviction long in a negative gamma environment. See `regime-transitions.md` for the full protocol.

**What does NOT qualify as a buy signal:**
- Price touching the gamma flip without closing above it
- Call buying appearing while price is still below the flip
- Dark pool buying appearing while price is still below the flip
- Any single river showing bullish signals without the others confirming

## Rally Characteristics in Regime E

Knowing what a Regime E rally looks like helps you fade it correctly.

**Typical Regime E rally:**
- Duration: 1-5 minutes on a 1-minute chart
- Magnitude: 15-40 NQ points
- Volume: Below average (thin book, low conviction)
- Trigger: Short covering (not new buying), or a brief pause in selling
- DOM: Offers reload immediately at the rally high
- Flow: No call sweeps, no new call OI
- Dark pool: Absent

**The short-covering rally:** The most common type of Regime E bounce. Shorts take profits, which creates temporary buying pressure. The rally is mechanical (short covering) not fundamental (new buyers). It ends when the short covering is complete. You can identify it by:
- Volume spike at the low (shorts covering)
- Volume declining as price rises (no new buyers joining)
- Call OI declining (shorts closing, not new longs opening)

**The news-driven bounce:** A headline can cause a 30-50 point bounce in Regime E. This is the most dangerous bounce to fade because it can be sustained if the news is genuinely positive. Check the news. If it's a genuine macro positive (Fed pivot, strong economic data), the bounce may be real. If it's a minor headline or a rumor, fade it.

## Historical Cascade Examples

**Pattern 1: March 2020 (COVID Crash)**
- NQ fell from 9,800 to 6,800 in 3 weeks
- Regime E for the entire decline
- Every bounce (and there were many, 200-400 NQ points) was a selling opportunity
- The gamma flip was at approximately 8,500 for most of the decline
- Dark pool buying appeared at 7,200 (first signal of exhaustion)
- Regime transitioned to D when price reclaimed 7,500 and flow shifted to net call
- The lesson: In Regime E, bounces are selling opportunities until the flip is reclaimed

**Pattern 2: August 2024 (Yen Carry Unwind)**
- NQ fell from 20,500 to 17,500 in 3 weeks
- Regime E for the core decline
- The put wall at 18,500 (QQQ 216) produced a 2-day bounce before breaking
- The bounce was the trapdoor: longs who bought the put wall bounce got caught
- Dark pool buying appeared at 17,800 (first signal)
- Regime transitioned to D when price reclaimed 18,200 and VIX started declining
- The lesson: The put wall bounce in Regime E is the trapdoor, not the floor

## Position Sizing in Regime E

Regime E is the highest-volatility regime. Position sizing must reflect this.

**Standard position size:** 50% of normal. The volatility is 2-3x higher than Regime A. A 50% position in Regime E has the same dollar risk as a 100% position in Regime A.

**Maximum position size:** 75% of normal. Never full size in Regime E. The cascade can accelerate beyond any reasonable stop.

**Stop distance:** 20-25 ticks. Wider than Regime A (15-20 ticks) because the book is thinner and price can gap through stops.

**Profit targets:** Use trailing stops, not fixed targets. In Regime E, the cascade can go much further than expected. A fixed target of 50 NQ points might be hit in 5 minutes, but the cascade might continue for 200 more points. Trail aggressively.

## Concrete Example

**Session: NQ at 20,800, QQQ at 242.80**
- Ratio: 85.66x
- FlashAlpha: total_gex = -$2.1B, gamma_flip = 247.00 (NQ: 21,157), call_wall = 252.00 (NQ: 21,586), put_wall = 238.00 (NQ: 20,387)
- Regime: E (negative gamma, spot below flip at 20,800 vs flip at 21,157)

**Scenario: Fading the bounce**
- 10:00 AM: NQ at 20,800, declining
- 10:15 AM: NQ bounces from 20,720 to 20,810 (90-point bounce)
- Massive: Call buying absent. Put buying pausing (not reversing). No call sweeps.
- Unusual Whales: No dark pool buying. Dark pool selling at QQQ 243.
- Rithmic DOM: Offers reloading at 20,810. Volume declining on the bounce.
- **Action: Short NQ at 20,805 (near bounce high)**
- Stop: 20,830 (25 ticks above entry)
- Target: Previous low at 20,720, then put wall at 20,387

- 10:30 AM: NQ at 20,720 (previous low). Take 40% off.
- 10:45 AM: NQ breaks 20,720. Trail stop to 20,750.
- 11:00 AM: NQ at 20,600. Trail stop to 20,640.
- 11:15 AM: NQ at 20,450 (approaching put wall at 20,387). Take 40% more off.
- 11:20 AM: NQ touches 20,390 (put wall). Brief bounce to 20,430.
- 11:25 AM: NQ breaks through 20,387. Cascade accelerates.
- 11:30 AM: NQ at 20,280. Trail stop to 20,320.
- 11:45 AM: NQ at 20,200. Stop at 20,240.
- 12:00 PM: Dark pool buying appears at QQQ 235.50 ($40M print). First exhaustion signal.
- **Action: Close remaining 20% at 20,200. Dark pool buying = potential exhaustion.**
- **Result: 605 NQ points on 40% (previous low), 405 NQ points on 40% (put wall), 605 NQ points on 20% (exhaustion). Exceptional cascade trade.**

## Cross-References

- Classification: `regime-identification.md`
- Regime D (negative gamma, above flip): `regime-d-negative-above-flip.md`
- Regime A (positive gamma, between walls): `regime-a-positive-between.md`
- Transition mechanics: `regime-transitions.md`
- The only buy signal (flip reclaim): `regime-transitions.md` (E → D transition)
