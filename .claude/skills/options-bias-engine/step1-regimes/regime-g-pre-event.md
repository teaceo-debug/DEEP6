# Regime G: Pre-Event

## Classification Conditions

Regime G activates when a macro event is within 60 minutes. It overrides all other regime classifications. The event calendar takes priority over GEX structure, wall levels, and pin conditions.

**Primary events (hard override, 60-minute window):**
- FOMC rate decision and statement
- FOMC press conference (separate from the decision, 30 minutes after)
- CPI (Consumer Price Index) release
- NFP (Non-Farm Payrolls) release, first Friday of each month at 8:30 AM ET
- PCE (Personal Consumption Expenditures) release
- PPI (Producer Price Index) release

**Secondary events (soft override, 30-minute window):**
- ISM Manufacturing PMI
- ISM Services PMI
- Retail Sales
- GDP advance estimate
- Mega-cap earnings: AAPL, MSFT, NVDA, GOOG, AMZN, META (after-hours, but pre-market the next day)
- Fed Chair speech or testimony (not scheduled FOMC, but major speeches)

**Mega-cap earnings note:** Earnings are typically after-hours (4:00-5:00 PM ET). The pre-event window for earnings applies to the NEXT MORNING's pre-market session. If NVDA reports after close on Tuesday, Wednesday's pre-market and early RTH session is Regime G until the market has had 30 minutes to digest the reaction.

## What Happens to Options Data Pre-Event

This is the core of why Regime G exists as a separate classification. Every data point from the four rivers becomes unreliable before a major event.

### FlashAlpha (GEX/DEX/VEX/CHEX)

**IV inflation:** Before a major event, implied volatility rises as traders buy options for protection and speculation. This IV inflation distorts the GEX calculation. The gamma values FlashAlpha shows are based on current IV. If IV is 20% above its normal level due to event premium, the GEX values are inflated by approximately 20%.

**Wall positions are pre-event:** The call wall and put wall reflect the current options structure, which was built for the pre-event price range. After the event, if NQ moves 200 points, the entire wall structure shifts. The call wall at 21,843 pre-event may be irrelevant post-event if NQ is now at 22,100.

**Gamma flip is pre-event:** The gamma flip level was computed from the current OI structure. Post-event, as options are repriced and new OI is created, the flip can move 100+ NQ points. The pre-event flip is not the post-event flip.

**DEX is unreliable:** Delta exposure is a function of both OI and delta values. Pre-event, delta values are distorted by the elevated IV. The DEX reading is not a reliable indicator of dealer positioning.

### Massive.com (Options Flow)

**Flow is hedging-dominated:** Pre-event, the dominant flow is hedging. Institutions buy puts to protect long equity portfolios. Traders buy straddles to profit from the move regardless of direction. This hedging flow looks like bearish positioning (put buying) but it's not directional conviction.

**The put buying trap:** A massive surge in put buying before CPI looks like bearish positioning. But it's insurance. The institutions buying those puts may be long NQ futures and just protecting themselves. The put buying does NOT tell you which direction the market will move after the event.

**Straddle buying:** Before major events, straddle buying (buying both calls and puts at the same strike) is common. This shows up as both call and put buying simultaneously. It's not bullish or bearish. It's a bet on volatility, not direction.

**OI changes are misleading:** New OI being created pre-event is often hedging OI, not directional OI. The OI changes don't tell you which way the market will move.

### Unusual Whales (Dark Pool)

**Dark pool goes quiet:** Institutions generally do not make large directional bets via dark pool immediately before major events. They wait for the event to pass and the new information to be priced in. Dark pool activity typically drops 50-70% in the 60 minutes before a major event.

**The absence is expected:** Don't interpret the absence of dark pool activity as a bearish signal. It's the normal pre-event state.

**Exception:** If dark pool buying appears in the 30 minutes before an event, it could signal that an institution has a strong pre-event view. This is rare and should be noted but not acted on. The event can still move the market against the dark pool position.

### Rithmic MBO (NQ Order Book)

**Liquidity withdrawal:** Market makers widen spreads and reduce depth before major events. They don't want to be caught on the wrong side of a large move with a large inventory. The DOM becomes thinner and less reliable.

**Spread widening:** The bid-ask spread in NQ futures typically widens from 0.25 points (1 tick) to 0.50-1.00 points (2-4 ticks) in the 30 minutes before a major event. This makes limit orders less reliable and market orders more expensive.

**False signals:** The thin book means that small orders can move price significantly. A 50-contract market order that would normally move price 1-2 ticks can move it 5-10 ticks in a thin pre-event book. This creates false signals in the DOM.

## Why You Generally Don't Trade Pre-Event

The fundamental problem with trading pre-event is that every level you've computed is valid for the pre-event world. Post-event, the world changes. The GEX structure reprices. The walls shift. The flip moves. Your entire level map becomes stale within seconds of the event.

**The level map problem:**
- Pre-event: Call wall at 21,843, put wall at 20,987, flip at 21,157
- Event: CPI comes in hot (above expectations)
- Post-event: NQ drops 300 points to 21,200
- New call wall: 21,500 (options repriced, new OI structure)
- New put wall: 20,700 (options repriced)
- New flip: 20,900 (options repriced)
- Your pre-event levels are now 200-300 points away from the new structure

If you're short from the pre-event call wall at 21,843 and NQ drops to 21,200, you made money. But if you're long from the pre-event put wall at 20,987 and NQ drops to 21,200, you're fine. But if NQ drops to 20,800 (below the pre-event put wall), you're in trouble. And the pre-event put wall is no longer the floor. The new put wall is at 20,700.

**The uncertainty problem:** You don't know which direction the event will move the market. Even if you have a strong view on the event outcome, the market's reaction to the outcome is uncertain. A "good" CPI number can cause a selloff if the market was expecting an even better number. A "bad" NFP can cause a rally if the market was expecting worse.

## The Exception: Pre-Event Positioning with Defined Risk

If you have a strong pre-event bias from overnight positioning and options structure, and you want to position SMALL with defined risk, use options (capped risk), not futures.

**Why options, not futures:**
- Options have defined maximum loss (the premium paid)
- Futures have unlimited loss potential
- Pre-event, the risk of being wrong is high
- Defined risk is essential when uncertainty is high

**Pre-event options positioning (if you must trade):**
- Use 0DTE or 1DTE options (they expire quickly, limiting time decay risk)
- Buy calls or puts, don't sell them (defined risk)
- Size: 25% of normal position size
- Accept that you may lose the entire premium

**When a pre-event bias is strong enough to act on:**
- Overnight positioning (Unusual Whales dark pool from the previous session) strongly favors one direction
- The options structure (FlashAlpha) shows a clear directional lean
- The event consensus is strongly in one direction AND the market is not pricing it in
- All three must align. If even one is missing, don't trade pre-event.

## Post-Event Protocol

After the event passes, do not immediately re-enter the market. Wait for the four rivers to stabilize.

**The 15-30 minute wait:**

After a major event, the market goes through a repricing phase. Options are repriced. New OI is created. The GEX structure shifts. The DOM normalizes. This takes 15-30 minutes.

**Post-event checklist:**

1. **Wait 15 minutes minimum.** Do not trade in the first 15 minutes after the event. The initial move is often a fake-out. The real direction establishes in the 15-30 minute window.

2. **Get a fresh FlashAlpha poll.** The GEX structure has changed. You need the new call wall, put wall, and gamma flip. Do not use pre-event levels.

3. **Read the new flow direction.** Massive will show the post-event flow. Is it call buying (bullish) or put buying (bearish)? Is it sweeps (aggressive) or limits (passive)?

4. **Check dark pool.** Unusual Whales will show post-event institutional positioning. Dark pool buying = institutions believe the move is real. Dark pool selling = institutions are distributing into the move.

5. **Assess DOM normalization.** Rithmic should show spreads returning to normal (1 tick) and depth rebuilding. If spreads are still wide, wait longer.

6. **Run the full classification.** Use `regime-identification.md` to classify the new regime from scratch. Do not assume the pre-event regime is still valid.

**The 30-minute rule:** If you're not confident in the new regime classification within 30 minutes of the event, don't trade. Wait for the next 15-minute FlashAlpha poll and reassess.

## VIX Behavior Around Events

VIX (implied volatility) has a predictable pattern around major events:

**Pre-event:** VIX rises as traders buy options for protection and speculation. This is the "event premium" being priced in.

**Post-event:** VIX typically drops regardless of price direction. This is the "vol crush." The event uncertainty is resolved. Options sellers collect the event premium. The IV drops back toward its pre-event level.

**The vol crush implication:** Post-event, vanna flows are bullish (VIX dropping → dealers buying as their delta exposure decreases). This creates a mechanical tailwind for the market regardless of the event outcome. A bad event that causes a 100-point NQ drop may see a 50-point recovery in the next 30 minutes as vol crush creates buying pressure.

**Practical rule:** After a major event, the first 15 minutes of price action is often the "event reaction." The next 15-30 minutes is the "vol crush recovery." Don't short the vol crush recovery. Wait for it to complete before establishing directional positions.

**Exception:** If the event is catastrophic (major financial crisis, geopolitical shock), vol crush may not occur. VIX can continue rising. In this case, the vol crush rule doesn't apply. Assess VIX direction before assuming vol crush.

## Event Calendar Reference

**FOMC:**
- 8 meetings per year, approximately every 6 weeks
- Rate decision at 2:00 PM ET
- Press conference at 2:30 PM ET (separate event, separate Regime G window)
- Dates published by the Fed at the start of each year
- Pre-event window: 1:00 PM ET to 2:00 PM ET (decision), 2:00 PM ET to 2:30 PM ET (press conference)

**CPI:**
- Monthly, typically second or third Tuesday of the month
- Release at 8:30 AM ET (pre-market)
- Pre-event window: 7:30 AM ET to 8:30 AM ET
- Post-event: Wait until 9:00 AM ET minimum before trading

**NFP:**
- Monthly, first Friday of the month
- Release at 8:30 AM ET (pre-market)
- Pre-event window: 7:30 AM ET to 8:30 AM ET
- Post-event: Wait until 9:15 AM ET minimum (NFP causes larger moves than CPI)

**PCE:**
- Monthly, typically last Friday of the month
- Release at 8:30 AM ET (pre-market)
- Pre-event window: 7:30 AM ET to 8:30 AM ET

**PPI:**
- Monthly, typically one day before CPI
- Release at 8:30 AM ET (pre-market)
- Pre-event window: 7:30 AM ET to 8:30 AM ET

**ISM Manufacturing:**
- Monthly, first business day of the month
- Release at 10:00 AM ET (during RTH)
- Pre-event window: 9:30 AM ET to 10:00 AM ET (30-minute window, secondary event)

**ISM Services:**
- Monthly, third business day of the month
- Release at 10:00 AM ET (during RTH)
- Pre-event window: 9:30 AM ET to 10:00 AM ET

**Mega-cap earnings (AAPL, MSFT, NVDA, GOOG, AMZN, META):**
- Typically after-hours (4:00-5:00 PM ET)
- Pre-event window for the NEXT DAY: Pre-market until 30 minutes after RTH open
- Post-event: Wait until 10:00 AM ET minimum on the day after earnings

**Maintaining the calendar:**
- Check the economic calendar at the start of each week
- Mark all events on the trading calendar
- Set alerts for 60 minutes before each primary event
- Set alerts for 30 minutes before each secondary event

## Regime G and the Other Regimes

Regime G overrides all other regimes. But the underlying regime is still relevant for post-event analysis.

**Pre-event:** Classify as Regime G. Do not trade (or trade with defined risk only).

**Post-event:** Run the full classification from `regime-identification.md`. The post-event regime may be the same as the pre-event regime (if the event was a non-event) or completely different (if the event caused a large move).

**The regime context matters for post-event trading:**
- If the post-event regime is A (positive gamma, between walls): The event move may be faded back toward HVL. Mean-reversion trade.
- If the post-event regime is E (negative gamma, below flip): The event caused a regime change. The cascade may continue. Short rallies.
- If the post-event regime is D (negative gamma, above flip): The event caused a recovery. Momentum-follow with tight stops.

## Concrete Example

**Scenario: CPI release**
- Date: Tuesday, 8:30 AM ET
- Pre-event: NQ at 21,500, Regime A (positive gamma, between walls)
- 7:30 AM ET: Regime G activates (60 minutes before CPI)
- **Action: No new positions. Close any overnight positions that don't have defined risk.**

- 8:30 AM ET: CPI releases. Core CPI = 3.8% (above 3.5% consensus). Hot print.
- 8:30-8:45 AM ET: NQ drops 250 points to 21,250. Volatile, thin book.
- **Action: Do not trade. Wait for stabilization.**

- 8:45-9:00 AM ET: NQ bounces from 21,250 to 21,350. Vol crush beginning.
- **Action: Still waiting. Vol crush recovery in progress.**

- 9:00 AM ET: Get fresh FlashAlpha poll.
- New structure: total_gex = +$1.8B (still positive), gamma_flip = 21,100 (NQ), call_wall = 21,600 (NQ), put_wall = 20,800 (NQ), hvl = 21,200 (NQ)
- NQ at 21,350: Above flip (21,100), between walls (20,800 and 21,600). Regime A.

- 9:15 AM ET: Massive shows balanced flow. No sweeps. Dark pool buying at 21,200 (Unusual Whales).
- Rithmic DOM: Spreads normalized. Depth rebuilding.
- **Action: Regime A confirmed. Apply Regime A playbook. NQ at 21,350, HVL at 21,200, put wall at 20,800.**
- **Setup: NQ is between HVL and call wall. No immediate edge. Wait for a test of HVL or call wall.**

- 10:00 AM ET: NQ rallies to 21,580 (near call wall at 21,600).
- Massive: Net call premium flat. No sweeps above 21,600.
- Unusual Whales: No dark pool above 21,600.
- Rithmic DOM: Offers reloading at 21,600. Iceberg offers.
- **Action: Short NQ at 21,575, stop 21,625, target 21,200 (HVL).**
- 11:30 AM ET: NQ at 21,210. Close position.
- **Result: 365 NQ points. Post-event Regime A trade.**

## Cross-References

- Classification: `regime-identification.md`
- Post-event regime identification: `regime-identification.md`
- Regime A (most common post-event regime): `regime-a-positive-between.md`
- Regime E (post-event cascade): `regime-e-negative-below-flip.md`
- Transition mechanics: `regime-transitions.md`
