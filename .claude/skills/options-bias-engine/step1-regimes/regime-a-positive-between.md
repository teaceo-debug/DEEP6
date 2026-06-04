# Regime A: Positive Gamma, Price Between Walls

## Classification Conditions

- `total_gex > 0` (FlashAlpha, preferably > $500M for reliable dampening)
- `NQ_spot > NQ_gamma_flip + 25 ticks` (spot comfortably above the flip)
- `NQ_spot < NQ_call_wall - (NQ_call_wall * 0.003)` (spot more than 0.3% below call wall)
- `NQ_spot > NQ_put_wall + (NQ_put_wall * 0.003)` (spot more than 0.3% above put wall)
- No macro event within 60 minutes
- Not 0DTE last 2 hours with pin conditions

This is the most common regime, occurring in approximately 40% of RTH sessions. It is the regime where options sellers win, range traders win, and directional breakout traders lose money.

## Market Microstructure: Why Price Is Dampened

Understanding the mechanics is not optional. If you don't understand why the dampening happens, you'll fight it.

When dealers sell options (calls and puts), they become net long gamma. Their delta exposure changes as price moves. To remain delta-neutral, they must continuously rehedge.

**When price rises in positive gamma:**
- Call options they sold gain delta. Their short call position becomes more delta-negative.
- To rehedge, dealers must SELL the underlying (NQ futures or QQQ shares).
- This selling pressure pushes price back down.
- The higher price goes, the more they sell. Counter-cyclical.

**When price falls in positive gamma:**
- Put options they sold gain delta (in absolute terms). Their short put position becomes more delta-positive.
- To rehedge, dealers must BUY the underlying.
- This buying pressure pushes price back up.
- The lower price goes, the more they buy. Counter-cyclical.

The result is a mechanical mean-reversion force. It doesn't care about news, sentiment, or technicals. It's pure delta-hedging math. The call wall and put wall are the strikes with the highest gamma concentration, so the dampening effect is strongest at those levels.

The HVL (High Volume Level, also called the zero-gamma level) is the price where dealer delta exposure is approximately zero. It acts as a gravitational center within the range. Price tends to oscillate around HVL within the walls.

## Regime Character

**Price behavior:** Oscillating. Moves toward walls get rejected. Moves away from walls get pulled back toward HVL. The range is defined by the walls. The center of gravity is HVL.

**Volatility:** Compressed. Realized volatility is lower than implied volatility. Options sellers are collecting premium that exceeds realized moves. This is why options sellers love this regime.

**Momentum:** Weak and unreliable. A strong move toward the call wall looks like momentum but is actually approaching maximum resistance. Momentum signals (MACD, RSI divergence, etc.) are less reliable here than in any other regime.

**Volume:** Moderate and balanced. No extreme volume spikes unless approaching walls. Volume at walls is higher as both sides fight for control.

**Time of day variation:**
- 9:30-10:30 AM ET: Opening range. Price often tests one wall early. The first test of a wall in the morning is frequently a rejection.
- 10:30 AM-12:00 PM ET: Most stable period. Range-bound oscillation. Best time for mean-reversion trades.
- 12:00-2:00 PM ET: Lunch lull. Volume drops. Range narrows. Avoid trading.
- 2:00-3:00 PM ET: Charm flows begin. Delta decays as time passes, causing dealers to rebalance. This can push price toward one wall. Watch FlashAlpha's CHEX (charm exposure) for direction.
- 3:00-4:00 PM ET: Final hour. If 0DTE, pin effects may activate. If not 0DTE, charm flows continue. Volume picks up. Range can expand.

## What to Trust in Regime A

**Trust these signals:**

1. **Wall levels as hard boundaries.** The call wall and put wall are not just technical levels. They have mechanical dealer hedging behind them. A first test of a wall in positive gamma has a 65-70% rejection rate.

2. **HVL as the magnet.** After a wall rejection, price tends to return toward HVL. This is the highest-probability target for mean-reversion trades.

3. **Expected move boundaries.** FlashAlpha's expected move (derived from ATM straddle price) defines the statistical range for the session. In Regime A, price rarely exceeds the expected move.

4. **VPOC and value area from Rithmic.** Volume Point of Control and value area align with HVL in most Regime A sessions. They reinforce each other as mean-reversion targets.

5. **Dark pool prints at walls.** If Unusual Whales shows dark pool buying at the put wall, that's institutional support confirming the mechanical floor. If dark pool selling at call wall, institutional distribution confirming the mechanical ceiling.

## What to Fade in Regime A

**Fade these signals:**

1. **Directional breakout attempts without full four-river confirmation.** A price push through the call wall that isn't supported by call sweeps on Massive, dark pool buying above the wall on Unusual Whales, AND DOM showing offers being pulled on Rithmic is almost certainly a false breakout. Fade it.

2. **Momentum signals at walls.** RSI at 70 near the call wall is not a buy signal. It's a sell signal. The momentum is running into maximum resistance.

3. **News-driven spikes that don't change the GEX structure.** A headline can push NQ 30 points in 2 minutes. In Regime A, if the GEX structure hasn't changed, that spike is a fade. The dealer hedging will pull it back.

4. **Volume spikes at walls without flow confirmation.** High volume at the call wall can be dealers hedging (selling), not buyers breaking through. Check Massive for the flow direction before interpreting volume.

## Trade Style: Mean-Reversion Playbook

### Setup 1: Short at Call Wall

**Entry conditions:**
- NQ_spot within 0.3% of NQ_call_wall
- Massive: Net call premium FLAT or DECLINING (buyers exhausted, not adding)
- Massive: No sweeps above the call wall strike (no positioning for a break)
- Unusual Whales: No dark pool buying above the call wall
- Rithmic DOM: Offers reloading at call wall level (sellers defending). Bid depth thin above wall. Iceberg offers visible (large hidden sell orders).
- FlashAlpha: total_gex still positive, call wall not shifting upward

**Entry:** Sell NQ at or within 10 ticks of NQ_call_wall. Limit order preferred. If using market, wait for a 5-tick bounce off the wall first.

**Stop:** 20-25 ticks above NQ_call_wall. If price closes above the wall by more than 25 ticks on a 1-minute bar, the wall is breaking. Exit immediately.

**Target 1:** NQ_hvl (HVL level). This is the primary target. Take 50-75% of position here.
**Target 2:** NQ_put_wall if momentum continues. Take remaining position here.

**Expected win rate:** 65-70% in strong positive gamma (total_gex > $2B). 55-60% in moderate positive gamma ($500M-$2B).

### Setup 2: Long at Put Wall

**Entry conditions:**
- NQ_spot within 0.3% of NQ_put_wall
- Massive: Net put premium FLAT or DECLINING (sellers exhausted)
- Massive: No put sweeps below the put wall strike (no positioning for a break)
- Unusual Whales: Dark pool buying at or near put wall (institutional support)
- Rithmic DOM: Bids reloading at put wall level. Iceberg bids visible. Absorption of market sells (large sell orders hitting without price declining).
- FlashAlpha: total_gex still positive, put wall not shifting downward

**Entry:** Buy NQ at or within 10 ticks of NQ_put_wall. Limit order preferred.

**Stop:** 20-25 ticks below NQ_put_wall. If price closes below the wall by more than 25 ticks on a 1-minute bar, the wall is breaking. This is a potential Regime A → Regime E transition. Exit immediately and reclassify.

**Target 1:** NQ_hvl. Primary target. Take 50-75% here.
**Target 2:** NQ_call_wall if momentum continues. Take remaining position here.

**Expected win rate:** 70-75% in strong positive gamma. This is slightly higher than the call wall short because put walls in positive gamma have the additional mechanical support of dealer buying (delta rehedging).

### Setup 3: HVL Fade (Mid-Range Mean Reversion)

When price is between the walls but has moved significantly away from HVL, fade the move back toward HVL.

**Entry conditions:**
- NQ_spot is 30+ NQ points from NQ_hvl
- Price has moved away from HVL on declining volume (momentum fading)
- Massive: Flow is not confirming the directional move (no sweeps in the direction of the move)
- Rithmic DOM: Book is balanced or slightly favoring the fade direction

**Entry:** Fade the move. If price is 30+ points above HVL, short. If 30+ points below HVL, long.

**Stop:** 15 ticks beyond the entry point (tight stop, this is a low-conviction setup).

**Target:** NQ_hvl. Single target. Exit fully at HVL.

**Expected win rate:** 55-60%. Lower than wall setups because HVL is a weaker level than the walls. Use smaller size.

## Flow Characteristics in Regime A

In a healthy Regime A session, options flow is moderate and balanced. What you typically see on Massive:

- Net premium: Slightly positive (more call premium than put premium) or balanced
- Sweep ratio: Low. Most flow is limit orders, not aggressive sweeps.
- 0DTE vs multi-day split: Mixed. Some 0DTE activity but not dominant.
- OI changes: Stable. No large OI additions or reductions at key strikes.

**Warning signs in the flow:**
- Sudden large put sweep (> $3M premium, aggressive): Someone is buying protection. Could signal a regime transition incoming. Reduce long exposure.
- Sudden large call sweep above the call wall: Someone is positioning for a break. Reduce short exposure at call wall. Watch for wall lift.
- Accelerating put buying with increasing OI: New bearish positions being established. This is not hedging. This is directional. Regime may be transitioning.

## Dark Pool Behavior in Regime A

Unusual Whales in Regime A typically shows:

- **At put wall:** Accumulation prints. Institutions buying at the mechanical floor. These are often large ($20M-$100M+) and appear at or slightly above the put wall.
- **At call wall:** Distribution prints. Institutions selling into the mechanical ceiling. Smaller than accumulation prints typically.
- **Mid-range:** Sporadic. No clear pattern. Institutions are not aggressively positioning mid-range.

**Dark pool absence:** If you see NO dark pool activity at the put wall when price is testing it, that's a warning. The mechanical floor may not have institutional backing. The rejection is less reliable.

## Order Book Patterns in Regime A

Rithmic MBO in Regime A has a distinctive character:

**At the call wall:**
- Thick offer stack. Multiple large limit sell orders at and just above the wall.
- Iceberg orders: Large hidden sell orders that reload as they get hit. You see this as repeated absorption of buy orders without price advancing.
- Bid depth thins out above the wall. No one is bidding above the ceiling.
- DOM asymmetry: Offer depth > Bid depth at the wall level.

**At the put wall:**
- Thick bid stack. Multiple large limit buy orders at and just below the wall.
- Iceberg bids: Large hidden buy orders absorbing market sells.
- Offer depth thins out below the wall. No one is offering below the floor.
- DOM asymmetry: Bid depth > Offer depth at the wall level.

**Mid-range:**
- Balanced book. Bid and offer depth roughly equal.
- Thinner overall. Less total depth than at the walls.
- Moves happen on less volume. Price can drift 10-15 points on moderate volume.

**Iceberg detection on Rithmic MBO:**
An iceberg is a large order that shows only a small visible portion (e.g., 10 contracts visible) but has a much larger hidden quantity. You detect it by watching a level get hit repeatedly without the price moving. If 500 contracts trade at 21,500 but the price doesn't move, there's an iceberg absorbing the flow. This is the strongest order book confirmation of a wall holding.

## Danger Signals: Regime A Breaking Down

Watch for these. When they appear, reduce size immediately and prepare for reclassification.

**Signal 1: VIX spike > 10% intraday**
A sudden VIX spike means implied volatility is rising sharply. This often precedes a GEX regime change. The put buying that drives VIX up also reduces total_gex. If VIX spikes 10%+ in 30 minutes, reclassify immediately.

**Signal 2: Gamma flip rising toward spot**
If FlashAlpha's gamma_flip is rising (OI restructuring is moving the flip upward toward current price), the regime is becoming unstable. When the flip is within 50 NQ points of spot, treat as transitional.

**Signal 3: Massive put sweeps accelerating**
Three or more large put sweeps (> $2M each) within 30 minutes is not hedging. It's directional positioning. Someone knows something or is forcing a move. Reduce long exposure.

**Signal 4: Dark pool selling at put wall**
If Unusual Whales shows dark pool selling at the put wall (not buying), the institutional support is absent. The mechanical floor may not hold. The put wall rejection probability drops from 70-75% to 50-55%.

**Signal 5: DOM bids being pulled at put wall**
If Rithmic shows the bid stack at the put wall thinning rapidly (bids being cancelled, not filled), the floor is weakening. This is the earliest real-time signal of a potential wall break, before FlashAlpha updates.

**Signal 6: Total GEX declining rapidly**
If FlashAlpha shows total_gex dropping significantly between polls (e.g., from +$2B to +$800M in 15 minutes), the regime is weakening. The dampening effect is proportional to GEX magnitude. A weakening GEX means walls are less reliable.

## Win Rates by Setup Type

These are empirical estimates based on NQ/QQQ options structure analysis. They assume proper four-river confirmation.

| Setup | Regime A Win Rate | Notes |
|-------|------------------|-------|
| Short at call wall (full confirmation) | 65-70% | Drops to 55% without dark pool confirmation |
| Long at put wall (full confirmation) | 70-75% | Highest win rate in the system |
| HVL fade (mid-range) | 55-60% | Use smaller size |
| Breakout fade (false break) | 60-65% | Only when all four rivers deny the break |

## Time-of-Day Variations

**9:30-10:00 AM ET (Opening):**
Regime A is most volatile in the first 30 minutes. The opening range is being established. Walls are being tested. Do not trade the first 15 minutes. Observe. Let the opening range form. The first test of a wall in the first 30 minutes is often the best trade of the day.

**10:00 AM-12:00 PM ET (Morning session):**
Most reliable period for Regime A setups. Volume is good, flow is interpretable, DOM is stable. This is when the 70-75% win rates are achievable.

**12:00-2:00 PM ET (Lunch):**
Volume drops 40-60%. Range narrows. Spreads widen. Avoid trading. If you must trade, use smaller size and wider stops.

**2:00-3:00 PM ET (Charm flows):**
Charm (the rate of change of delta with respect to time) causes delta to decay as options approach expiry. This creates systematic dealer rebalancing. The direction of charm flows depends on whether calls or puts are dominant in the OI structure. FlashAlpha's CHEX value tells you the direction and magnitude. Positive CHEX = charm flows are bullish (pushing price up). Negative CHEX = charm flows are bearish. In Regime A, charm flows can push price toward one wall in the afternoon. Adjust your bias accordingly.

**3:00-4:00 PM ET (Final hour):**
Volume picks up. If 0DTE, pin effects may activate (see `regime-f-pin.md`). If not 0DTE, the range can expand as positions are squared. The final 30 minutes can see the largest moves of the day. Be cautious with open positions.

## Concrete Example

**Session: NQ at 21,500, QQQ at 251.00**
- Ratio: 85.66x
- FlashAlpha: total_gex = +$3.2B, gamma_flip = 248.50 (NQ: 21,287), call_wall = 255.00 (NQ: 21,843), put_wall = 245.00 (NQ: 20,987), hvl = 251.50 (NQ: 21,544)
- Regime: A (positive gamma, spot between walls, above flip)

**Morning scenario:**
- 9:45 AM: NQ rallies to 21,820 (within 0.3% of call wall at 21,843)
- Massive: Net call premium flat, no sweeps above 255 QQQ
- Unusual Whales: No dark pool prints above 255 QQQ
- Rithmic DOM: Thick offer stack at 21,843, iceberg offers absorbing buy flow
- **Action: Short NQ at 21,820, stop at 21,870 (27 ticks above wall), target 21,544 (HVL)**
- 10:30 AM: NQ at 21,560, near HVL. Take 75% off. Trail stop on remainder.
- 11:15 AM: NQ at 21,544 (HVL). Close remaining position.
- **Result: 276 NQ points on 75% of position, 276 points on 25% of position. Full target hit.**

**Afternoon scenario:**
- 2:15 PM: FlashAlpha CHEX = -$800M (negative charm, bearish drift)
- NQ drifts from 21,544 to 21,050 (approaching put wall at 20,987)
- Massive: Put premium declining, no new put sweeps
- Unusual Whales: Dark pool buying at 20,987 QQQ equivalent
- Rithmic DOM: Iceberg bids at 21,000, absorption of market sells
- **Action: Long NQ at 21,010, stop at 20,960 (20 ticks below wall), target 21,544 (HVL)**
- 3:30 PM: NQ at 21,500. Close position.
- **Result: 490 NQ points. Clean put wall long.**

## Cross-References

- Classification: `regime-identification.md`
- Transition to Regime B (call wall test): `regime-b-positive-at-call.md`
- Transition to Regime C (put wall test): `regime-c-positive-at-put.md`
- Transition mechanics: `regime-transitions.md`
- If GEX turns negative: `regime-d-negative-above-flip.md` or `regime-e-negative-below-flip.md`
