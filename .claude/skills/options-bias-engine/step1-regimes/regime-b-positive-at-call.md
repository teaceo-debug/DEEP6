# Regime B: Positive Gamma, Price at Call Wall

## Classification Conditions

- `total_gex > 0` (FlashAlpha)
- `NQ_spot >= NQ_call_wall - (NQ_call_wall * 0.003)` AND `NQ_spot <= NQ_call_wall + (NQ_call_wall * 0.003)`
- Spot is within 0.3% of the call wall (approximately 64 NQ points at 21,500)
- `NQ_spot > NQ_gamma_flip + 25 ticks` (above the flip, confirming positive gamma)
- No macro event within 60 minutes
- Not 0DTE pin conditions

Regime B is a decision point, not a sustained regime. Price arrives at the call wall from below (typically from Regime A) and must resolve one of two ways: rejection back into the range, or a wall lift that creates a new higher range. The resolution determines the next regime. This is where the four rivers earn their keep.

## The Two Outcomes

**Outcome 1: Rejection (approximately 65% of call wall tests)**
The call wall holds. Price is repelled back toward HVL. The regime returns to Regime A. The call wall is confirmed as the ceiling.

**Outcome 2: Wall Lift (approximately 35% of call wall tests)**
The call wall breaks. New call buying at higher strikes creates gamma above the current wall. The wall effectively moves up. Price enters a new, higher Regime A range. The old call wall becomes the new HVL or support level.

The 65/35 split is the baseline in positive gamma. It shifts based on the strength of the GEX structure and the four-river confirmation. With strong rejection signals from all four rivers, the rejection probability rises to 80%+. With strong breakout signals from all four rivers, the wall lift probability rises to 60%+.

## Why the Call Wall Is a Ceiling (Mechanics)

In positive gamma, dealers are net long gamma from selling calls. As price approaches the call wall, the gamma concentration at that strike is highest. The dealer hedging effect is at maximum strength.

When price rises toward the call wall:
- Dealers' short call positions gain delta rapidly (gamma is highest here)
- To rehedge, dealers must sell NQ futures aggressively
- This selling is mechanical, not discretionary
- The selling pressure is proportional to the gamma at that strike
- At the call wall, this selling is at its peak

This is why the call wall is not just a technical resistance level. It has a mechanical selling force behind it that scales with the GEX magnitude. A call wall with $500M of gamma behind it is a suggestion. A call wall with $3B of gamma behind it is a wall.

## How to Distinguish Rejection from Wall Lift

This is the core skill of Regime B. The four rivers each provide a different piece of the puzzle.

### River 1: FlashAlpha (GEX Structure)

**Rejection signal:** The call wall strike shows stable or increasing gamma. The total_gex is stable or rising. No new OI appearing at strikes above the current call wall.

**Wall lift signal:** New OI is appearing at strikes ABOVE the current call wall. FlashAlpha's next poll will show the call wall has moved up. You can anticipate this by watching Massive for call buying at higher strikes in real-time (before FlashAlpha updates).

**How to read it:** Compare the current FlashAlpha poll to the previous one. If the call wall strike is the same and gamma there is stable, the wall is holding. If the call wall strike has moved up since the last poll, the wall has already lifted. If you're between polls, use Massive as the leading indicator.

### River 2: Massive.com (Options Flow)

This is the most important river for distinguishing rejection from wall lift, because it updates in real-time while FlashAlpha polls every 15 minutes.

**Rejection signals:**
- Net call premium at the call wall strike is FLAT or DECLINING. Buyers are not adding. The rally is running out of fuel.
- Call buying is concentrated AT the call wall strike, not ABOVE it. This is profit-taking on existing longs, not new positioning for a break.
- Put buying is increasing. Traders are buying protection against a rejection. Smart money is fading the wall.
- No sweeps above the call wall strike. No one is aggressively buying calls at higher strikes.
- 0DTE call volume at the wall strike is high but declining. The gamma squeeze is exhausting itself.

**Wall lift signals:**
- Net call premium INCREASING and accelerating. New money is flowing in.
- Call buying is appearing at strikes ABOVE the current call wall. This is the key signal. When someone buys calls at a strike above the current wall, they're creating new gamma above the wall. If enough of this happens, the wall moves up.
- New OI being created at higher strikes (not just volume, but open interest increasing). This means new positions, not just day-trading.
- Sweeps at higher strikes. Aggressive, large-premium call buying above the wall is the strongest wall lift signal.
- Put selling at the call wall strike. If puts at the wall strike are being sold (premium collected), traders are positioning for the wall to hold as support after a break.

**Quantitative thresholds:**
- Call sweep > $5M premium at a strike above the current wall: Strong wall lift signal
- Net call premium increasing > $10M in 15 minutes: Momentum building for break
- Put buying > $3M premium at wall strike: Rejection signal (protection buying)
- OI increase > 5,000 contracts at a strike above wall: New positioning for break

### River 3: Unusual Whales (Dark Pool)

Dark pool activity at the call wall is a direct read on institutional conviction.

**Rejection signals:**
- No dark pool prints above the call wall. Institutions are not positioning for a break.
- Dark pool selling at or near the call wall. Institutions are distributing into the rally.
- Dark pool prints are at or below the call wall, not above it.

**Wall lift signals:**
- Dark pool buying at or ABOVE the call wall. This is the clearest institutional signal. If a $50M+ dark pool print appears above the current call wall, an institution is positioning for price to trade there. They don't buy above the wall if they think it's going to reject.
- Multiple dark pool prints above the wall within 30 minutes. Accumulation, not a single trade.
- Dark pool prints in QQQ-correlated names (AAPL, MSFT, NVDA) above their respective resistance levels. Sector-wide institutional buying.

**Absence of dark pool:** If there's no dark pool activity at all during a call wall test, the test is retail-driven. Retail-driven tests have lower wall lift probability. Institutions tend to be involved in genuine breakouts.

### River 4: Rithmic MBO (NQ Order Book)

The order book gives you the real-time microstructure of the wall test. It's the fastest-updating river.

**Rejection signals:**
- Offers RELOADING at the call wall level. Every time buy orders hit the offer, new sell orders appear. The wall is being defended. This is the iceberg pattern: large hidden sell orders that replenish as they're filled.
- Bid depth THINNING above the call wall. No one is bidding above the ceiling. The market is not pricing in a break.
- DOM asymmetry: Offer depth significantly exceeds bid depth at the wall level.
- Large market buy orders hitting the offer without price advancing. Absorption. The wall is eating the buying pressure.
- Sweep detection: Buy sweeps hitting the offer but price not moving. The wall is absorbing them.

**Wall lift signals:**
- Offers being PULLED at the call wall level. Sellers are withdrawing. The wall is losing its defenders.
- Bid depth appearing ABOVE the call wall. Someone is bidding above the ceiling, expecting price to trade there.
- DOM asymmetry reversing: Bid depth exceeds offer depth at the wall level.
- Price advancing through the wall on INCREASING volume. Not a spike, but sustained volume. The wall is being consumed, not absorbed.
- Offer stack thinning above the wall. The path above is clearing.

**The iceberg test:** Watch a specific price level at the call wall for 5 minutes. Count how many times buy orders hit that level. If the offer keeps reloading (same size appearing after being hit), it's an iceberg. Icebergs at the call wall = strong rejection signal. If the offer at that level gets consumed and doesn't reload, the wall is breaking.

## Entry Rules: Rejection Trade

When the four rivers confirm rejection, this is a short trade back toward HVL.

**Entry conditions (all four must confirm):**
1. FlashAlpha: Call wall stable, total_gex positive and stable
2. Massive: Net call premium flat/declining, no sweeps above wall
3. Unusual Whales: No dark pool above wall, or dark pool selling at wall
4. Rithmic DOM: Offers reloading at wall, iceberg pattern visible, bid depth thin above wall

**Entry:** Short NQ at or within 10 ticks of NQ_call_wall. Limit order at the wall. If price has already touched the wall and bounced 5-10 ticks, enter on the first pullback to within 15 ticks of the wall.

**Stop:** 25 ticks above NQ_call_wall. If price closes above the wall by 25 ticks on a 1-minute bar, the rejection has failed. Exit immediately. Do not widen the stop.

**Target 1:** NQ_hvl. Take 60-70% of position here.
**Target 2:** NQ_put_wall. Take remaining position here.

**Expected win rate:** 70-75% with full four-river confirmation. This is higher than the baseline 65% because the confirmation filters out the weaker rejection setups.

**Risk/reward:** At NQ 21,843 call wall, stop at 21,869 (26 ticks = 6.5 pts), target HVL at 21,544 (299 pts). R/R = 46:1 on the first target. Even with a 50% win rate, this is profitable. At 70% win rate, it's exceptional.

## Entry Rules: Wall Lift (Breakout) Trade

When the four rivers confirm a wall lift, this is a long trade. The entry is NOT at the wall. The entry is on the FIRST PULLBACK to the wall after the break is confirmed.

**Why not buy the break itself:** The break of the call wall in positive gamma is often violent and fast. Chasing it means buying at the worst price. The wall, once broken, becomes support. The pullback to the old wall is the entry.

**Confirmation of a genuine break:**
1. Price closes above NQ_call_wall by more than 25 ticks on a 1-minute bar
2. Massive: Call sweeps above the old wall are continuing (not stopping after the break)
3. Unusual Whales: Dark pool buying above the old wall
4. Rithmic DOM: Old wall level now showing bid support (offers gone, bids appearing)
5. FlashAlpha (next poll): Call wall has moved up to a higher strike

**Entry:** Long NQ on the first pullback to the old call wall level (now support). Limit order at the old wall.

**Stop:** 25 ticks below the old call wall. If price falls back below the old wall by 25 ticks, the break was false. Exit.

**Target:** The new call wall (from FlashAlpha's updated poll). If the new wall hasn't been identified yet, use the next round number or the expected move upper boundary.

**Expected win rate:** 55-60%. Lower than the rejection trade because false breakouts are common. The four-river confirmation is essential. Without it, don't take this trade.

## The Wall Lift Mechanics in Detail

Understanding how a wall lifts helps you anticipate it before FlashAlpha confirms it.

When call buyers purchase options at strikes ABOVE the current call wall, they create new open interest at those strikes. The dealers who sell those calls must hedge by buying NQ futures. This buying pushes price higher. As price rises toward the new strikes, the gamma at those strikes increases. The old call wall's gamma becomes less relevant as price moves away from it.

The process:
1. Large call buying at strike X (above current call wall Y)
2. Dealers sell those calls and buy NQ to hedge
3. NQ price rises toward X
4. Gamma at X increases as price approaches
5. FlashAlpha's next poll shows call wall has moved from Y to X
6. The old wall Y is now the HVL or support level

You can see step 1 and 2 in real-time on Massive (call buying at X) and Rithmic (NQ buying). Steps 3-5 happen over 15-30 minutes. Step 6 is confirmed on the next FlashAlpha poll.

## The False Breakout Pattern

The most dangerous pattern in Regime B. Price pushes above the call wall, looks like a wall lift, then snaps back violently.

**Why it happens:** A large buy order (or coordinated retail buying) pushes price above the wall. The gamma effect is momentarily overwhelmed. But the dealer hedging (selling) at the wall is still there. As the buying pressure exhausts, the dealer selling reasserts. Price snaps back below the wall.

**How to identify a false breakout:**
- The break happens on a single large buy sweep, not sustained buying
- Massive shows the call buying STOPS immediately after the break (no follow-through)
- No dark pool buying above the wall (Unusual Whales)
- DOM shows offers immediately reloading above the old wall (sellers returning)
- Volume spike on the break, then volume collapses

**Trading the false breakout:** This is a high-conviction short. Wait for price to push above the wall, confirm the false break signals, then short as price falls back below the wall. Stop above the high of the false break. Target HVL.

## Specific Order Book Patterns at the Call Wall

**Pattern 1: The Iceberg Defense**
```
Price: 21,843 (call wall)
DOM:
  Offer: 21,844 - 50 contracts (visible)
  Offer: 21,843 - 50 contracts (visible)
  Bid:   21,842 - 30 contracts
  Bid:   21,841 - 25 contracts

After 100 contracts trade at 21,843:
  Offer: 21,844 - 50 contracts (unchanged)
  Offer: 21,843 - 50 contracts (RELOADED - iceberg)
```
The offer at 21,843 reloads after being hit. This is an iceberg. Strong rejection signal.

**Pattern 2: The Offer Withdrawal (Wall Lift)**
```
Price: 21,843 (call wall)
DOM before:
  Offer: 21,845 - 80 contracts
  Offer: 21,844 - 60 contracts
  Offer: 21,843 - 50 contracts

DOM 5 minutes later:
  Offer: 21,848 - 20 contracts (offers pulled, only thin resistance above)
  Offer: 21,847 - 15 contracts
  Bid:   21,844 - 40 contracts (bids appearing above old wall)
```
Offers being pulled above the wall, bids appearing above the wall. Wall lift in progress.

**Pattern 3: Absorption Without Advance**
```
Price: 21,843 (call wall)
Trade tape: 21,843 x 200, 21,843 x 150, 21,843 x 300, 21,843 x 180
Price: still 21,843 after 830 contracts traded at this level
```
830 contracts traded at the wall without price advancing. The wall is absorbing the buying. Strong rejection signal.

## Historical Examples with NQ Price Levels

**Example 1: Clean Rejection (November 2023)**
- NQ at 16,200, call wall at 16,250 (QQQ 189.50 * 85.7x)
- Morning rally pushed NQ to 16,248
- Massive: Net call premium flat, no sweeps above 189.50 QQQ
- Unusual Whales: No dark pool above 189.50
- Rithmic: Iceberg offers at 16,250, 400 contracts absorbed without advance
- Short at 16,245, stop 16,275, target HVL at 16,100
- NQ rejected to 16,095 by 11:30 AM
- Result: 150 NQ points captured

**Example 2: Wall Lift (February 2024)**
- NQ at 17,800, call wall at 17,850 (QQQ 208.00 * 85.7x)
- 10:15 AM: NQ pushes to 17,855
- Massive: $8M call sweep at QQQ 210 (above wall), new OI appearing
- Unusual Whales: $45M dark pool print at QQQ 209 (above wall)
- Rithmic: Offers at 17,850 pulled, bids appearing at 17,855
- Did NOT short. Waited for pullback.
- NQ pulled back to 17,852 (old wall now support)
- Long at 17,855, stop 17,825, target new call wall at 18,050
- NQ reached 18,040 by 1:30 PM
- Result: 185 NQ points captured

## Cross-References

- Classification: `regime-identification.md`
- Regime A (between walls): `regime-a-positive-between.md`
- Regime C (at put wall): `regime-c-positive-at-put.md`
- Transition mechanics: `regime-transitions.md`
- If wall lifts and GEX turns negative: `regime-d-negative-above-flip.md`
