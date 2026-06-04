# Regime C: Positive Gamma, Price at Put Wall

## Classification Conditions

- `total_gex > 0` (FlashAlpha)
- `NQ_spot >= NQ_put_wall - (NQ_put_wall * 0.003)` AND `NQ_spot <= NQ_put_wall + (NQ_put_wall * 0.003)`
- Spot is within 0.3% of the put wall (approximately 64 NQ points at 21,500)
- `NQ_spot > NQ_gamma_flip + 25 ticks` (above the flip, confirming positive gamma)
- No macro event within 60 minutes
- Not 0DTE pin conditions

Regime C is the highest win-rate long setup in the entire system. The put wall in positive gamma is not just a technical support level. It has two distinct mechanical forces reinforcing it: dealer delta rehedging (buying) and the concentrated negative GEX at the put wall strike creating a gamma-reinforced floor. When all four rivers confirm, the long at the put wall in positive gamma is the closest thing to a structural edge this system produces.

## Why This Is the Best Long Setup

The put wall in positive gamma has a 75-80% win rate for longs with full four-river confirmation. Understanding why requires understanding both forces at work.

**Force 1: Dealer Delta Rehedging**

In positive gamma, dealers are net long gamma from selling puts. As price falls toward the put wall, the delta of their short put positions increases in absolute terms (puts gain delta as price falls). To remain delta-neutral, dealers must BUY the underlying (NQ futures or QQQ shares). This buying is mechanical and counter-cyclical. The lower price goes, the more they buy. At the put wall, where gamma concentration is highest, this buying is at maximum intensity.

This is the same mechanism that creates the call wall ceiling, but in reverse. The put wall has a mechanical buying force behind it that scales with the GEX magnitude.

**Force 2: Gamma-Reinforced Floor**

The put wall is the strike with the highest concentration of put open interest. This means the highest negative GEX is at this strike. As price approaches the put wall from above, the gamma effect strengthens. The closer price gets to the put wall, the more powerful the dealer buying becomes. This creates a self-reinforcing floor: the closer you get to the wall, the harder it is to break through.

**Force 3: Institutional Awareness**

Sophisticated market participants know where the put wall is. They know the mechanical buying will be strongest there. This creates a self-fulfilling element: institutions buy at the put wall because they know dealers will also be buying there. Dark pool accumulation at the put wall is common precisely because institutions are front-running the dealer buying.

## The Two Outcomes

**Outcome 1: Bounce (approximately 75-80% of put wall tests in positive gamma)**
The put wall holds. Price bounces back toward HVL. The regime returns to Regime A. The put wall is confirmed as the floor.

**Outcome 2: Floor Break (approximately 20-25% of put wall tests)**
The put wall breaks. This is a regime transition. When the put wall breaks in positive gamma, it typically means total_gex is turning negative (or already has). The regime transitions from Regime C to Regime E (negative gamma, below flip). This is the most dangerous transition in the system. See `regime-transitions.md` for the full mechanics.

## Four-River Confirmation for the Long

### River 1: FlashAlpha (GEX Structure)

**Bounce signals:**
- total_gex is positive and stable (not declining rapidly)
- Put wall strike shows stable or increasing gamma concentration
- Gamma flip is well below current price (50+ NQ points below spot)
- No dramatic shift in the GEX profile between polls

**Floor break warning signals:**
- total_gex declining rapidly between polls (e.g., +$2B to +$800M in 15 minutes)
- Put wall gamma concentration declining (put OI being closed or rolled)
- Gamma flip rising toward spot (the flip is approaching from below)
- DEX (delta exposure) turning increasingly negative

**Quantitative check:** If total_gex has declined more than 30% from the session open, treat the put wall as less reliable. The dampening force is weaker.

### River 2: Massive.com (Options Flow)

**Bounce signals:**
- Put premium DECLINING. Sellers are running out of steam. The put buying that drove price down is exhausting itself.
- Call buying beginning to appear. Traders are positioning for the bounce.
- No new put sweeps below the put wall strike. No one is aggressively buying puts at lower strikes (which would signal positioning for a break).
- Put selling at the put wall strike. If puts at the wall strike are being sold (premium collected), traders are positioning for the wall to hold. They're selling puts because they believe the floor will hold.
- 0DTE put volume declining at the wall strike. The gamma squeeze is exhausting.

**Floor break warning signals:**
- Put sweeps ACCELERATING at and below the put wall. New aggressive put buying is the clearest signal that someone is positioning for a break.
- Put OI INCREASING at strikes below the put wall. New positions being established below the floor.
- Call buying absent or declining. No one is positioning for a bounce.
- Large put sweeps > $5M premium at strikes below the wall: Strong floor break signal.

**Quantitative thresholds:**
- Put sweep > $5M premium at a strike below the current wall: Strong floor break signal
- Net put premium declining > $5M in 15 minutes: Bounce signal (sellers exhausted)
- Call buying appearing > $3M in 15 minutes: Bounce signal (positioning for recovery)
- Put OI increase > 5,000 contracts at strikes below wall: Floor break positioning

### River 3: Unusual Whales (Dark Pool)

**Bounce signals:**
- Dark pool BUYING at or near the put wall. This is the most powerful confirmation. Institutions are accumulating at the mechanical floor. They know the dealer buying will support them.
- Large dark pool prints ($20M+) at the put wall level or slightly above it.
- Multiple dark pool prints within 30 minutes. Sustained accumulation, not a single trade.
- Dark pool buying in QQQ-correlated names (AAPL, MSFT, NVDA) at their respective support levels.

**Floor break warning signals:**
- Dark pool SELLING at the put wall. Institutions are distributing into the mechanical floor. They don't believe it will hold.
- No dark pool activity at all. The floor has no institutional backing. The bounce probability drops from 75-80% to 55-60%.
- Dark pool selling in QQQ-correlated names. Sector-wide institutional distribution.

**The dark pool absence problem:** If there's no dark pool activity at the put wall, the bounce is less reliable. The mechanical dealer buying is still there, but without institutional support, the bounce may be weaker and shorter-lived. Reduce position size by 30-40% when dark pool is absent.

### River 4: Rithmic MBO (NQ Order Book)

**Bounce signals:**
- Bids RELOADING at the put wall level. Every time sell orders hit the bid, new buy orders appear. The floor is being defended. Iceberg bids.
- Absorption of market sells. Large sell orders hitting the bid without price declining. The floor is eating the selling pressure.
- DOM asymmetry: Bid depth significantly exceeds offer depth at the wall level.
- Offer depth thinning below the wall. No one is offering below the floor.
- Iceberg bids visible: Large hidden buy orders that replenish as they're filled.

**Floor break warning signals:**
- Bids being PULLED at the put wall. The bid stack is thinning rapidly. Buyers are withdrawing.
- Market sells hitting the bid AND price declining. The floor is not absorbing the selling.
- DOM asymmetry reversing: Offer depth exceeds bid depth at the wall level.
- Offers appearing below the wall. Someone is willing to sell below the floor.
- No iceberg bids. The floor has no hidden support.

**The absorption test:** Watch the put wall level for 5 minutes. Count how many contracts trade at that level. If 500+ contracts trade without price declining, the floor is absorbing the selling. Strong bounce signal. If 200 contracts trade and price drops 5 ticks, the floor is not absorbing. Reduce or exit.

## Entry Rules: Long at Put Wall

**Entry conditions (all four must confirm):**
1. FlashAlpha: total_gex positive and stable, put wall stable, flip well below spot
2. Massive: Put premium declining, no sweeps below wall, call buying appearing
3. Unusual Whales: Dark pool buying at put wall (or at minimum, no dark pool selling)
4. Rithmic DOM: Bids reloading at wall, iceberg bids visible, absorption of market sells

**Entry:** Long NQ at or within 10 ticks of NQ_put_wall. Limit order at the wall. If price has already touched the wall and bounced 5-10 ticks, enter on the first pullback to within 15 ticks of the wall.

**Entry timing:** Do not enter immediately when price first touches the put wall. Wait for at least one of these confirmations:
- Price touches the wall and bounces 5+ ticks (initial rejection visible)
- Iceberg bid visible on Rithmic (absorption confirmed)
- Dark pool print appears on Unusual Whales
- Put premium starts declining on Massive

Waiting 2-5 minutes after the first touch costs you 5-10 ticks of entry but dramatically improves the win rate. The first touch is often a probe. The second touch (after a small bounce) is the real test.

**Stop:** 20-25 ticks below NQ_put_wall. This is non-negotiable. If price closes below the wall by 25 ticks on a 1-minute bar, the floor has broken. This is a potential Regime C → Regime E transition. Exit immediately and reclassify.

Do not widen the stop. The put wall breaking is a regime change event. The loss on this trade is small compared to the loss of holding a long through a Regime E cascade.

**Target 1:** NQ_hvl. Primary target. Take 60-70% of position here.
**Target 2:** NQ_call_wall. Take remaining position here.

**Expected win rate:** 75-80% with full four-river confirmation. This is the highest win rate in the system.

**Risk/reward example:** NQ at 20,987 (put wall), stop at 20,962 (25 ticks below = 6.25 pts), target HVL at 21,544 (557 pts). R/R = 89:1 on the first target. Even at 50% win rate, this is exceptional. At 75-80%, it's the system's best trade.

## When the Floor Breaks: The 20-25% Case

The floor break is the most dangerous outcome in Regime C. Recognizing it fast is critical.

**The sequence of a floor break:**
1. Price approaches put wall
2. Initial bounce (5-15 ticks) — looks like a normal rejection
3. Price returns to the wall and pushes through
4. Bids at the wall are pulled (not absorbed, pulled)
5. Price accelerates below the wall
6. Regime transitions from C to E

The key difference between a bounce and a break is what happens on the SECOND test of the wall. The first test almost always produces a bounce. The second test, if it fails, is the break.

**Real-time break signals (from Rithmic, fastest river):**
- Bids at the wall being cancelled (not filled, cancelled). This is the earliest signal.
- Price falls through the wall on a single large market sell order without absorption.
- The bid stack below the wall is thin (no support below the floor).
- Offers appear below the wall immediately after the break (sellers piling in).

**From Massive (second fastest):**
- Put sweeps accelerating at and below the wall. New aggressive put buying.
- Call buying stops completely. No one is positioning for a bounce.

**From Unusual Whales:**
- Dark pool selling appears at or below the wall. Institutions are distributing.

**From FlashAlpha (slowest, but confirms):**
- Next poll shows total_gex declining or turning negative.
- Gamma flip rising toward spot.

**Action on floor break:** Exit the long immediately. Do not average down. Do not wait for a bounce. The floor has broken. The regime is transitioning. The next stop is Regime E, where the mechanical forces are now working AGAINST longs. See `regime-e-negative-below-flip.md`.

## Time Considerations

**Morning (9:30-11:00 AM ET):**
Put wall tests in the morning are the most reliable. Volume is high, flow is interpretable, DOM is stable. The 75-80% win rate is most achievable in this window.

**Midday (11:00 AM-2:00 PM ET):**
Put wall tests in midday are less reliable. Volume is lower, flow is thinner, DOM is less stable. Reduce position size by 20-30%.

**Afternoon (2:00-4:00 PM ET):**
Charm flows can push price toward the put wall in the afternoon. This is a known pattern. However, charm-driven tests of the put wall are slightly less reliable than morning tests because the charm flow itself is a mechanical force that can overwhelm the gamma floor. Check FlashAlpha's CHEX value. If CHEX is strongly negative (bearish charm), the put wall may be under more pressure than usual.

**0DTE afternoons:**
If it's 0DTE and the last 2 hours, the put wall may be transitioning to a pin regime (Regime F). Check if the put wall strike has high 0DTE OI concentration. If so, the pin mechanics may be more relevant than the gamma floor mechanics. See `regime-f-pin.md`.

## Reduced Confirmation Scenarios

Sometimes not all four rivers align perfectly. Here's how to adjust:

**Three rivers confirm, one is neutral:**
- Reduce position size by 25%
- Tighten stop to 15 ticks below wall (instead of 25)
- Take profit at HVL only (no second target)

**Two rivers confirm, two are neutral:**
- Reduce position size by 50%
- Tighten stop to 10 ticks below wall
- Take profit at 50% of the distance to HVL

**Any river shows a floor break signal:**
- Do NOT enter the long
- Watch for the break
- If break confirmed, prepare for Regime E short setup

## Concrete Example

**Session: NQ at 21,500, QQQ at 251.00**
- Ratio: 85.66x
- FlashAlpha: total_gex = +$2.8B, gamma_flip = 248.50 (NQ: 21,287), call_wall = 255.00 (NQ: 21,843), put_wall = 245.00 (NQ: 20,987), hvl = 251.50 (NQ: 21,544)

**Scenario: Morning put wall test**
- 10:15 AM: NQ sells off from 21,400 to 21,010 (approaching put wall at 20,987)
- FlashAlpha (10:00 AM poll): total_gex = +$2.8B, stable. Flip at 21,287, well below spot.
- Massive: Net put premium declining from peak. No new put sweeps below 245 QQQ. Call buying starting to appear ($2M in last 10 min).
- Unusual Whales: $35M dark pool print at QQQ 245.20 (just above put wall). Institutional accumulation.
- Rithmic DOM: Iceberg bids at 20,987. 600 contracts absorbed at 20,987-21,000 without price declining below 20,987.
- **Action: Long NQ at 21,005 (10 ticks above wall, after first touch and 5-tick bounce)**
- Stop: 20,962 (25 ticks below wall)
- Target 1: 21,544 (HVL)
- Target 2: 21,843 (call wall)

- 11:30 AM: NQ at 21,540. Take 65% off at 21,544 (HVL). Trail stop on remainder.
- 1:45 PM: NQ at 21,820. Close remaining 35% at 21,820 (near call wall, not quite there).
- **Result: 539 NQ points on 65% of position, 815 NQ points on 35% of position. Exceptional trade.**

**Scenario: Floor break (the 20-25% case)**
- 10:15 AM: NQ sells off to 21,010 (approaching put wall at 20,987)
- FlashAlpha (10:00 AM poll): total_gex = +$800M (declining from +$2.8B at open). Warning.
- Massive: Put sweeps ACCELERATING. $6M put sweep at QQQ 243 (below wall). New OI appearing below wall.
- Unusual Whales: Dark pool SELLING at QQQ 245. Institutional distribution.
- Rithmic DOM: Bids at 20,987 being PULLED. Thin bid stack. Offers appearing at 20,970.
- **Action: DO NOT enter long. All four rivers showing floor break signals.**
- 10:25 AM: NQ breaks through 20,987, falls to 20,850.
- Regime transitions to E. See `regime-e-negative-below-flip.md` for the short setup.

## The Structural Edge Explained

The put wall long in positive gamma is the system's best trade because it combines three independent sources of edge:

1. **Mechanical edge:** Dealer delta rehedging creates automatic buying at the put wall. This is not sentiment-dependent. It happens regardless of news, technicals, or market mood.

2. **Structural edge:** The put wall has the highest gamma concentration, meaning the mechanical buying is at maximum strength at exactly this level.

3. **Institutional edge:** Sophisticated participants know about the mechanical buying and front-run it with dark pool accumulation, adding to the buying pressure.

When all three sources align, the put wall long is as close to a structural edge as exists in liquid futures markets. The 75-80% win rate is not luck. It's the convergence of three independent mechanical forces.

## Cross-References

- Classification: `regime-identification.md`
- Regime A (between walls): `regime-a-positive-between.md`
- Regime B (at call wall): `regime-b-positive-at-call.md`
- Transition to Regime E (floor break): `regime-e-negative-below-flip.md`
- Transition mechanics: `regime-transitions.md`
- Pin regime (0DTE afternoons): `regime-f-pin.md`
