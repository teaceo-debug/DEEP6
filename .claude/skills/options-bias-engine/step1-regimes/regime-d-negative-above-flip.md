# Regime D: Negative Gamma, Price Above Flip

## Classification Conditions

- `total_gex < 0` (FlashAlpha)
- `NQ_spot > NQ_gamma_flip + 25 ticks` (spot comfortably above the flip)
- No macro event within 60 minutes
- Not 0DTE pin conditions

Regime D is the most deceptive regime in the system. Price is above the gamma flip, which sounds bullish. But the overall GEX is negative, which means dealers are amplifying moves rather than dampening them. The combination creates a regime that feels like a recovery but can reverse with brutal speed. More traders lose money in Regime D than in any other regime, because they apply positive gamma intuitions (fade the move, buy the dip) to a negative gamma environment.

## Why It's Deceptive

The deception comes from the apparent contradiction between the two signals:

- **Above the flip:** In positive gamma, being above the flip means you're in the "safe" zone where dealers buy dips. Traders trained on positive gamma regimes associate "above the flip" with stability.
- **Negative total GEX:** But the total GEX is negative, meaning dealers are net short gamma overall. The pro-cyclical amplification is the dominant force.

The result: Price is in a zone where the local gamma (at the flip level) is transitioning from negative to positive, but the aggregate dealer positioning is still amplifying. Rallies overshoot. Reversals are violent. Levels that would hold in positive gamma break without warning.

The regime typically occurs after a significant selloff (Regime E) where price has recovered back above the gamma flip, but the overall options structure hasn't yet turned positive. It's the "dead cat bounce" zone in options terms.

## Market Microstructure: Pro-Cyclical Amplification

In negative gamma, dealers are net short gamma. Their delta exposure changes in the same direction as price moves.

**When price rises in negative gamma:**
- Dealers' short call positions gain delta (calls they sold are now more in-the-money)
- To rehedge, dealers must BUY the underlying (NQ futures)
- This buying ADDS to the rally. Pro-cyclical.
- The higher price goes, the more they buy. Amplifying.

**When price falls in negative gamma:**
- Dealers' short put positions gain delta (puts they sold are now more in-the-money)
- To rehedge, dealers must SELL the underlying
- This selling ADDS to the decline. Pro-cyclical.
- The lower price goes, the more they sell. Amplifying.

In Regime D specifically (above the flip), the rally has some mechanical support from the fact that price is above the flip. But the negative total GEX means the amplification effect is still dominant. Rallies go further than they should. Then when they reverse, the reversal is amplified too.

**The overshoot-then-crash pattern:**
1. Price rallies above the flip (Regime E → Regime D transition)
2. Dealer buying amplifies the rally (pro-cyclical)
3. Rally overshoots fair value
4. Momentum fades (flow dries up, dark pool absent)
5. Price reverses
6. Dealer selling amplifies the reversal (pro-cyclical)
7. Price drops back below the flip (Regime D → Regime E transition)
8. The cascade accelerates

This pattern is why Regime D is dangerous for both longs and shorts. Longs get caught in the reversal. Shorts get squeezed in the overshoot.

## Four-River Reading in Regime D

### River 1: FlashAlpha (GEX Structure)

**What to read:**
- `total_gex`: Negative, but watch the magnitude. Is it becoming less negative (recovering toward positive)? Or is it stable/worsening?
- `gamma_flip`: Where is it relative to spot? The closer spot is to the flip, the more unstable the regime.
- `call_wall` and `put_wall`: In negative gamma, these walls are WEAKER than in positive gamma. They can break without warning.
- `dex` (delta exposure): Increasingly negative DEX means dealers are net short delta, which means they're positioned for further downside. This is a bearish signal even in Regime D.
- `vex` (vanna exposure): If VIX is declining, vanna flows are bullish (dealers buying as vol drops). This can extend the Regime D rally. If VIX is rising, vanna flows are bearish.

**Regime D stability signals:**
- total_gex approaching zero from below: The regime is recovering. If it crosses zero, you're in positive gamma. Regime D → Regime A transition.
- total_gex stable at a negative level: The regime is stable but dangerous. Momentum-follow with tight stops.
- total_gex becoming more negative: The regime is deteriorating. The rally is on borrowed time.

**The flip distance rule:** If spot is within 50 NQ points of the gamma flip, treat the regime as transitional. The flip can be crossed in either direction on a single large move. Reduce size.

### River 2: Massive.com (Options Flow)

This is the most important river for determining whether the Regime D rally has legs.

**Rally has legs (momentum is real):**
- Call buying is ESCALATING. New call premium flowing in, not just existing positions being held.
- Call sweeps appearing at higher strikes. Aggressive positioning for further upside.
- Put buying is declining. Hedgers are unwinding protection (they believe the rally is real).
- New call OI being created at higher strikes. Institutional positioning for continuation.

**Rally is failing (dead cat bounce):**
- Call buying is DECLINING. The flow that drove the rally is drying up.
- Call volume is high but it's CLOSING (OI declining). Longs are taking profits, not adding.
- Put buying is increasing. Hedgers are adding protection (they don't trust the rally).
- No new call OI at higher strikes. No institutional positioning for continuation.
- Put sweeps appearing. Someone is positioning for the reversal.

**The critical distinction:** Volume and premium can look similar whether calls are being bought (new longs) or sold (closing shorts). Watch OI changes. If call OI is INCREASING, new longs are being established. If call OI is DECREASING, existing longs are being closed. A rally on declining call OI is a rally that's running out of buyers.

### River 3: Unusual Whales (Dark Pool)

Dark pool in Regime D tells you whether institutions believe the rally.

**Institutions believe the rally:**
- Dark pool BUYING at or above current price. Institutions are accumulating into the rally.
- Large prints ($30M+) in QQQ-correlated names. Sector-wide institutional conviction.
- Dark pool prints appearing at progressively higher prices. Institutions are chasing the rally (unusual, but it happens in genuine recoveries).

**Institutions don't believe the rally:**
- Dark pool ABSENT. No institutional conviction. The rally is retail-driven. Retail-driven rallies in negative gamma fail more often than not.
- Dark pool SELLING into the rally. Institutions are distributing. The rally is a selling opportunity for them.
- Dark pool prints in QQQ-correlated names at resistance levels. Institutional distribution at technical levels.

**The absence signal:** In Regime D, the absence of dark pool buying is itself a bearish signal. Genuine recoveries from negative gamma environments attract institutional buying. If institutions are not buying, the recovery is suspect.

### River 4: Rithmic MBO (NQ Order Book)

The order book in Regime D has a distinctive character: it's THIN. Negative gamma environments have thinner books than positive gamma environments because market makers are less willing to provide liquidity when they're short gamma (their hedging costs are higher).

**Rally continuation signals:**
- Bid depth building above current price. Buyers are positioning for further upside.
- Offer stack thinning above current price. Sellers are withdrawing. The path up is clearing.
- DOM asymmetry: Bid depth > Offer depth.
- Sweeps hitting the offer and price advancing. Momentum is real.

**Rally failure signals:**
- Offer stack RELOADING above current price. Sellers are returning. The ceiling is reforming.
- Bid depth thinning. Buyers are withdrawing.
- DOM asymmetry reversing: Offer depth > Bid depth.
- Sweeps hitting the offer but price NOT advancing. Absorption. The rally is being sold.
- Book depth asymmetry: Thin bids, thick offers. The market is positioned for a reversal.

**The thin book warning:** In Regime D, moves happen on less volume than in positive gamma. A 30-point rally on 500 contracts in Regime D is not the same as a 30-point rally on 500 contracts in Regime A. In Regime D, the thin book means the move is less reliable. It can reverse just as fast on the same thin volume.

## Trade Style: Momentum-Follow with Tight Stops

The cardinal rule of Regime D: **Never fade. Never buy the dip. Never short the rally.**

In positive gamma, fading moves is the correct strategy. In Regime D (negative gamma), fading moves is how you get destroyed. The pro-cyclical amplification means that what looks like an overextended move can extend much further before reversing.

**The only trade in Regime D: Momentum-follow with tight trailing stops.**

### Long Trade (Rally Continuation)

**Entry conditions:**
- Price is above the gamma flip and trending up
- Massive: Call buying escalating, no put sweeps
- Unusual Whales: Dark pool buying present
- Rithmic DOM: Bid depth building, offer stack thinning

**Entry:** Long NQ on a pullback to a recent support level (not a fade, a pullback in an uptrend). Use a 5-minute chart. Enter on the first pullback after a breakout above a recent high.

**Stop:** TIGHT. 15-20 ticks below the entry. In Regime D, when the momentum turns, it turns fast. A wide stop means a large loss.

**Trailing stop:** Trail the stop aggressively. As price advances, move the stop up to 15-20 ticks below the most recent swing low. Do not give back more than 20 ticks of profit.

**Target:** No fixed target. Trail until stopped out. In Regime D, the rally can go further than expected (pro-cyclical amplification). Let it run, but trail tightly.

**Exit trigger:** Any of these:
- Stop hit (15-20 ticks below entry or trailing stop)
- Massive: Call buying stops and put buying appears
- Unusual Whales: Dark pool selling appears
- Rithmic DOM: Offer stack reloads, bid depth thins
- Price drops back below the gamma flip (Regime D → Regime E transition)

### Short Trade (Rally Failure)

**Entry conditions:**
- Price is above the gamma flip but the rally is showing failure signals
- Massive: Call buying declining, put sweeps appearing
- Unusual Whales: Dark pool absent or selling
- Rithmic DOM: Offer stack reloading, bid depth thinning
- Price has made a lower high (momentum structure breaking)

**Entry:** Short NQ on a break below a recent swing low. Not a fade of the high. Wait for the structure to break.

**Stop:** TIGHT. 15-20 ticks above the entry. If the rally resumes, exit immediately.

**Target:** The gamma flip level. This is the primary target. If price drops below the flip, the regime transitions to E and the short becomes much more powerful. See `regime-e-negative-below-flip.md`.

**The flip cross trade:** If price drops below the gamma flip while you're short, this is the Setup 3 (Gamma Flip Cross) trade. The regime has transitioned from D to E. The short is now in a negative gamma, below-flip environment. The pro-cyclical amplification is now working in your favor. Hold the short with a wider trailing stop. See `regime-transitions.md`.

## Levels Are Weak in Regime D

This is the most important practical point about Regime D. In positive gamma, walls are reliable. In Regime D (negative gamma), walls can break without warning.

**Why walls are weak:**
- In positive gamma, dealer hedging REINFORCES walls (buying at put wall, selling at call wall)
- In negative gamma, dealer hedging AMPLIFIES moves through walls (selling accelerates as price falls through put wall, buying accelerates as price rises through call wall)
- The wall levels still exist in the GEX data, but they don't have the same mechanical support

**Practical implication:** Do not use wall levels as entry points in Regime D. Do not buy at the put wall expecting a bounce. Do not short at the call wall expecting a rejection. These setups have 40-50% win rates in Regime D, not 70-75%. The mechanical support is absent.

**What levels DO work in Regime D:**
- The gamma flip itself (the most important level)
- Round numbers (psychological, not mechanical)
- VPOC and value area from Rithmic (volume-based, not gamma-based)
- Previous day's high/low (structural, not gamma-based)

## VIX and Vanna Context

Vanna is the rate of change of delta with respect to implied volatility. When VIX drops, vanna flows are bullish (dealers buy as their delta exposure decreases). When VIX rises, vanna flows are bearish.

In Regime D, VIX behavior is critical:

**VIX declining (vanna bullish):**
- Dealers are buying as vol drops. This adds to the rally.
- The Regime D rally has more legs when VIX is declining.
- This is the "vol crush" recovery pattern. Common after a spike event.
- FlashAlpha's VEX (vanna exposure) will be positive (bullish vanna flows).

**VIX stalling or reversing:**
- Vanna flows stop supporting the rally.
- The rally loses its mechanical tailwind.
- Exit long positions immediately when VIX stalls after a decline.
- This is often the first signal that the Regime D rally is failing.

**VIX rising:**
- Vanna flows turn bearish. Dealers are selling as their delta exposure increases.
- The rally is fighting both negative gamma amplification AND bearish vanna flows.
- This is the most dangerous Regime D configuration. The reversal will be violent.
- Exit all longs. Consider shorts.

**Practical rule:** In Regime D, check VIX every 15 minutes. If VIX is declining, the rally has support. If VIX stalls, reduce longs. If VIX rises, exit longs immediately.

## The Transition Danger: Regime D → Regime E

The most dangerous moment in Regime D is when price drops back below the gamma flip. This is the Regime D → Regime E transition. It's the most violent transition in the system.

**Why it's violent:**
1. Everyone who bought the "recovery" (Regime D longs) is now wrong
2. Their stops are clustered just below the flip (where they entered)
3. As price drops below the flip, their stops trigger
4. The stop-triggered selling pushes price further below the flip
5. Dealer selling (pro-cyclical in negative gamma) amplifies the move
6. The cascade accelerates

**Early warning signals of the D → E transition:**
- Massive: Put sweeps appearing while price is still above the flip
- Unusual Whales: Dark pool selling appearing
- Rithmic DOM: Bid depth thinning rapidly, offer stack building below the flip
- FlashAlpha: total_gex becoming more negative (not recovering)
- VIX: Rising sharply

**Action on D → E transition:** Exit all longs immediately. Do not wait for confirmation. The transition is the signal. If you're short, hold and trail. See `regime-transitions.md` for the full transition protocol.

## Specific Rules for Trailing Stops in Regime D

Because Regime D can reverse violently, trailing stops must be tighter than in any other regime.

**Long trailing stop rules:**
- Initial stop: 15 ticks below entry
- After 20-tick profit: Move stop to breakeven
- After 40-tick profit: Trail at 15 ticks below most recent 5-minute swing low
- After 80-tick profit: Trail at 20 ticks below most recent 5-minute swing low
- Never give back more than 25 ticks of profit

**Short trailing stop rules:**
- Initial stop: 15 ticks above entry
- After 20-tick profit: Move stop to breakeven
- After 40-tick profit: Trail at 15 ticks above most recent 5-minute swing high
- After 80-tick profit: Trail at 20 ticks above most recent 5-minute swing high
- If price drops below gamma flip: Widen trailing stop to 30 ticks (now in Regime E, more room to run)

## Concrete Example

**Session: NQ at 21,200, QQQ at 247.50**
- Ratio: 85.66x
- FlashAlpha: total_gex = -$1.2B, gamma_flip = 247.00 (NQ: 21,157), call_wall = 252.00 (NQ: 21,586), put_wall = 243.00 (NQ: 20,814)
- Regime: D (negative gamma, spot above flip at 21,200 vs flip at 21,157)

**Scenario: Rally continuation**
- 10:00 AM: NQ at 21,200, above flip at 21,157
- Massive: Call buying escalating, $4M call sweep at QQQ 249 (above current price)
- Unusual Whales: $28M dark pool print at QQQ 248 (above current price)
- Rithmic DOM: Bid depth building above 21,200, offer stack thinning
- VIX: Declining from 22 to 20 (vanna bullish)
- **Action: Long NQ at 21,210 on pullback from 21,230 high**
- Stop: 21,190 (20 ticks below entry)
- Trail: Move stop up as price advances

- 10:45 AM: NQ at 21,380. Stop now at 21,355 (trailing).
- 11:15 AM: NQ at 21,450. Stop now at 21,425.
- 11:30 AM: Massive: Call buying slowing. VIX stalls at 19.8.
- **Action: Exit at 21,450 (don't wait for stop). VIX stall = rally losing tailwind.**
- **Result: 240 NQ points captured. Clean momentum trade.**

**Scenario: Rally failure**
- 10:00 AM: NQ at 21,200, above flip at 21,157
- Massive: Call buying declining. $3M put sweep at QQQ 246.
- Unusual Whales: No dark pool buying. Dark pool selling at QQQ 248.
- Rithmic DOM: Offer stack reloading above 21,200. Bid depth thinning.
- VIX: Rising from 20 to 21.5.
- **Action: Short NQ at 21,185 on break below 21,190 swing low**
- Stop: 21,205 (20 ticks above entry)
- Target: Gamma flip at 21,157

- 10:20 AM: NQ at 21,160 (near flip). Take 50% off.
- 10:25 AM: NQ breaks below flip at 21,157. Regime transitions to E.
- **Action: Hold remaining 50% with wider trailing stop (now in Regime E). Trail at 30 ticks above most recent swing high.**
- 11:00 AM: NQ at 20,950. Stop at 20,980 (trailing).
- 11:15 AM: NQ at 20,920. Stop at 20,950.
- 11:30 AM: NQ bounces to 20,955. Stop hit at 20,950.
- **Result: 35 NQ points on 50% (flip target), 250 NQ points on 50% (Regime E continuation). Total: ~142 NQ points average.**

## Cross-References

- Classification: `regime-identification.md`
- Regime E (negative gamma, below flip): `regime-e-negative-below-flip.md`
- Regime A (positive gamma, between walls): `regime-a-positive-between.md`
- Transition mechanics: `regime-transitions.md`
- Transition D → E: `regime-transitions.md` (most dangerous transition)
