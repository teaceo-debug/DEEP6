# Flow Interpretation — Reading Options Flow for Directional Bias

## Purpose

Options flow is the real-time record of what market participants are doing with their money. It is the most direct signal of institutional intent available to retail traders. But raw flow data is noise. The skill is in classifying the flow into one of six states, each with distinct directional implications. This document defines those states with quantitative thresholds, explains the decision tree for classification, and covers the time-of-day patterns that modulate flow interpretation.

Data sources:
- **Massive.com**: Primary flow tape. Real-time options transactions, sweep detection, premium tracking.
- **Unusual Whales**: Dark pool prints, institutional flow, block trades.
- **FlashAlpha**: GEX context for interpreting flow (which strikes matter, which don't).
- **Rithmic MBO**: Order book confirmation of flow signals.

---

## The Six Flow States

### State 1: AGGRESSIVE BULLISH

The market is being bought with urgency. Institutions are paying up for upside exposure. This is the highest-conviction bullish signal from flow.

**Quantitative thresholds** (all must be met for maximum conviction; 3 of 4 for moderate conviction):

1. **Net call premium**: Net call premium (calls bought minus puts bought, in dollar terms) exceeds +$15M in a rolling 5-minute window.
   - Moderate signal: +$5M to +$15M
   - Strong signal: +$15M to +$30M
   - Maximum signal: +$30M+

2. **Sweep count**: 3 or more call sweeps in the last 5 minutes.
   - Each sweep must be at least 500 contracts to count.
   - Sweeps at ask side only (bought, not sold).

3. **Premium escalation**: Each successive sweep is larger than the previous. The buyer is increasing size.
   - Sweep 1: $2M premium
   - Sweep 2: $3.5M premium
   - Sweep 3: $5M premium
   - This escalation pattern = maximum conviction. The buyer is not done.

4. **Side**: All sweeps at ask (bought). No offsetting put buying.

**Supporting signals** (not required but increase conviction):
- Unusual Whales: Dark pool net buying in the last 30 minutes.
- Rithmic DOM: Bids stacking in NQ futures. Icebergs on the bid.
- FlashAlpha: Flow is at or above the call wall (attacking the ceiling) or between walls (normal bullish).

**Directional bias**: BULLISH. Strong. Expect upward price movement within 15-30 minutes.

**Duration**: Aggressive bullish flow typically lasts 15-45 minutes before either achieving its target or exhausting. If flow dies after 45 minutes without a price move, the signal has failed.

**Failure mode**: Aggressive bullish flow that doesn't move price = absorption. Someone is selling into the buying. This is a bearish signal. See State 4 (DISTRIBUTION).

---

### State 2: AGGRESSIVE BEARISH

The mirror of State 1. The market is being sold with urgency.

**Quantitative thresholds**:

1. **Net put premium**: Net put premium exceeds +$15M in a rolling 5-minute window (puts bought minus calls bought).
   - Moderate signal: +$5M to +$15M
   - Strong signal: +$15M to +$30M
   - Maximum signal: +$30M+

2. **Sweep count**: 3 or more put sweeps in the last 5 minutes.
   - Each sweep at least 500 contracts.
   - Sweeps at ask side (bought, not sold).

3. **Premium escalation**: Each successive put sweep is larger.

4. **Side**: All sweeps at ask (bought). No offsetting call buying.

**Supporting signals**:
- Unusual Whales: Dark pool net selling in the last 30 minutes.
- Rithmic DOM: Offers stacking in NQ futures. Icebergs on the ask.
- FlashAlpha: Flow is at or below the put wall (attacking the floor) or between walls (normal bearish).

**Directional bias**: BEARISH. Strong. Expect downward price movement within 15-30 minutes.

**Duration**: Same as aggressive bullish. 15-45 minutes.

**Failure mode**: Aggressive bearish flow that doesn't move price = absorption. Someone is buying into the selling. This is a bullish signal. See State 3 (ACCUMULATION).

---

### State 3: ACCUMULATION (Stealth Bullish)

This is the "smart money loading quietly" pattern. The flow looks moderate or even mixed on the surface, but the underlying structure is bullish. This is the highest-value signal because it precedes aggressive bullish flow by 30-90 minutes.

**Characteristics**:

1. **Moderate call buying at bid**: Calls are being bought, but at the bid (patient, not sweeping). This means the buyer is not in a hurry. They're accumulating over time.
   - Volume: 200-1000 contracts per trade (not sweeps, which are 1000+).
   - Side: At bid or mid (not at ask).
   - Frequency: Steady stream of trades, not a burst.

2. **Block trades**: Large single-exchange trades (not sweeps). These are negotiated trades, often between institutions. Block trades at the call side = institutional accumulation.
   - Block size: 2000+ contracts in a single trade.
   - Block premium: $5M+ per trade.

3. **OI building at call strikes**: Open interest is increasing at call strikes without a corresponding price move. This means new positions are being opened, not just traded.
   - Detection: Compare current volume at a strike to prior day's OI. If volume > OI, new positions are being created.

4. **Dark pool BUYING**: Unusual Whales shows net dark pool buying, but visible flow (Massive.com) is quiet or mixed.
   - This divergence is the key signal. Dark pool is buying while visible flow is quiet = stealth accumulation.

5. **Icebergs on bid in DOM**: Rithmic MBO shows iceberg orders on the bid side. Large hidden buyers are accumulating.

**Directional bias**: BULLISH. Moderate to strong. The move is coming, but not yet. Expect upward price movement within 30-90 minutes.

**Why this matters**: Accumulation precedes aggressive bullish flow. The institutions who accumulated quietly will eventually need to push price higher to realize their gains. When they do, the flow shifts to State 1 (AGGRESSIVE BULLISH). Identifying accumulation early gives you a 30-90 minute head start.

**Failure mode**: Accumulation that transitions to State 4 (DISTRIBUTION) = the institutions changed their mind. Exit immediately.

---

### State 4: DISTRIBUTION (Stealth Bearish)

The mirror of State 3. Smart money is exiting while retail buys. This is the most dangerous state because it looks bullish on the surface.

**Characteristics**:

1. **Call selling (closing)**: Calls are being sold at the bid. This is profit-taking on existing long call positions. The visible flow looks bearish (calls being sold) but it's actually closing, not new bearish positioning.
   - Detection: Volume at call strikes is high, but OI is decreasing (positions being closed, not opened).
   - Side: At bid (sold).

2. **Put OI building quietly**: Put open interest is increasing at put strikes without visible put sweeps. Institutions are buying puts quietly (at bid, not sweeping).

3. **Dark pool SELLING**: Unusual Whales shows net dark pool selling, but visible flow (Massive.com) may look bullish (retail buying calls).
   - This divergence is the key signal. Dark pool is selling while visible flow is bullish = distribution.

4. **Icebergs on ask in DOM**: Rithmic MBO shows iceberg orders on the ask side. Large hidden sellers are distributing.

5. **Price not moving despite bullish visible flow**: If visible flow is bullish but price isn't moving, someone is absorbing the buying. That someone is the distributor.

**Directional bias**: BEARISH. Moderate to strong. The move is coming, but not yet. Expect downward price movement within 30-90 minutes.

**Why this matters**: Distribution precedes aggressive bearish flow. The institutions who distributed quietly will eventually need to push price lower to realize their gains (on their puts) or to cover their short positions. When they do, the flow shifts to State 2 (AGGRESSIVE BEARISH).

**The retail trap**: Distribution often occurs at or near the call wall, where retail traders are most bullish. Retail sees price at the call wall and buys calls. Institutions sell those calls (closing their long calls) and buy puts. The retail trader is buying the top.

---

### State 5: HEDGING (Not Directional)

Heavy options activity that looks bearish but is actually insurance, not a directional bet. Misclassifying hedging as bearish is a common and costly error.

**Characteristics**:

1. **Far OTM put buying**: Puts being bought at strikes 5-10% below spot. These are tail hedges, not directional bets. Nobody expects price to fall 10% today — they're buying insurance against a catastrophic event.
   - Strike: More than 5% below spot.
   - Expiry: Long-dated (30+ DTE). Tail hedges are not 0DTE.
   - Premium: High per contract (far OTM options are cheap per contract but the total premium can be large).

2. **Collar structures**: Simultaneous call selling + put buying. The institution is selling upside (call) to finance downside protection (put). This is a neutral-to-bearish hedge, not a directional bet.
   - Detection: Simultaneous call sell + put buy at the same expiry, different strikes.
   - The call sell is at a strike above spot. The put buy is at a strike below spot.

3. **Long-dated put buying**: Puts with 30+ DTE. Directional traders use 0DTE to weekly. Hedgers use monthly to quarterly.

4. **No corresponding dark pool selling**: If the put buying is hedging, dark pool should be neutral or buying (the institution is long the underlying and buying puts as insurance). If dark pool is also selling, it's not hedging — it's distribution.

5. **No DOM confirmation**: Hedging doesn't create order book pressure. The DOM should be neutral.

**Directional bias**: NONE. Ignore for directional bias. This is insurance, not a bet.

**Why this matters**: Misclassifying hedging as bearish leads to shorting into a market that's actually being supported by institutional longs. The institutions buying puts are LONG the underlying — they're not selling it.

**Detection algorithm**:
```
if put_strike < spot × 0.95 AND put_DTE > 21:
    classify as HEDGING (not directional)
elif call_sell AND put_buy at same expiry:
    classify as HEDGING (collar structure)
elif dark_pool_net > 0 AND put_buying > 0:
    classify as HEDGING (long underlying + put protection)
else:
    classify as AGGRESSIVE BEARISH or DISTRIBUTION
```

---

### State 6: DEAD (No Signal)

Nobody is doing anything. The market is in a low-activity period. No trade.

**Quantitative thresholds**:
- Net premium (calls minus puts) in rolling 15-minute window: Less than $5M absolute value.
- Sweep count in last 15 minutes: 0 or 1.
- Block trades in last 15 minutes: 0.
- Dark pool activity: Below average (less than 50% of typical daily rate).

**Time-of-day correlation**: Dead flow is most common during:
- Midday (11:30 AM - 1:30 PM ET): The "lunch lull." Volume drops. Institutions are not active.
- Pre-market (before 9:00 AM ET): Options market is thin.
- Post-close (after 4:00 PM ET): Options market is closed.

**Directional bias**: NONE. Do not trade. Wait for flow to resume.

**Why this matters**: Trading in dead flow is gambling. There's no information in the flow to support a directional bet. The market can move in either direction on thin volume, and the move is not meaningful.

---

## Flow State Classification Decision Tree

```
START: Compute rolling 5-minute net premium (calls bought - puts bought)

IF net_premium > +$15M:
    IF sweep_count >= 3 AND all_at_ask:
        IF premium_escalating:
            → AGGRESSIVE BULLISH (maximum conviction)
        ELSE:
            → AGGRESSIVE BULLISH (moderate conviction)
    ELSE:
        → AGGRESSIVE BULLISH (low conviction, confirm with DOM)

IF net_premium < -$15M:
    IF sweep_count >= 3 AND all_at_ask:
        IF premium_escalating:
            → AGGRESSIVE BEARISH (maximum conviction)
        ELSE:
            → AGGRESSIVE BEARISH (moderate conviction)
    ELSE:
        → AGGRESSIVE BEARISH (low conviction, confirm with DOM)

IF |net_premium| < $5M (rolling 15 min):
    → DEAD (no signal)

IF $5M < |net_premium| < $15M:
    CHECK dark pool direction:
    IF dark_pool_net > 0 AND visible_flow_net < 0:
        → ACCUMULATION (stealth bullish)
    IF dark_pool_net < 0 AND visible_flow_net > 0:
        → DISTRIBUTION (stealth bearish)
    IF dark_pool_net > 0 AND visible_flow_net > 0:
        → AGGRESSIVE BULLISH (low conviction)
    IF dark_pool_net < 0 AND visible_flow_net < 0:
        → AGGRESSIVE BEARISH (low conviction)

CHECK for hedging:
    IF put_strike < spot × 0.95 AND put_DTE > 21:
        → HEDGING (override any bearish classification)
    IF collar_structure detected:
        → HEDGING (override any bearish classification)
```

---

## Flow State Transitions

Flow states don't stay constant. They transition as market conditions change. Understanding transitions is as important as identifying the current state.

### Common Transition Sequences

**ACCUMULATION → AGGRESSIVE BULLISH**:
- The most profitable transition to identify early.
- Timeline: 30-90 minutes from accumulation start to aggressive bullish.
- Signal: Accumulation (quiet call buying, dark pool buying) transitions to sweeps (urgent call buying at ask).
- Trade: Enter long during accumulation. Add on the transition to aggressive bullish.

**AGGRESSIVE BULLISH → DEAD**:
- The move has completed. Flow exhausted.
- Timeline: 15-45 minutes of aggressive bullish, then flow dies.
- Signal: Sweep count drops to 0. Net premium drops below $5M. Dark pool activity normalizes.
- Trade: Take profit. The move is over.

**AGGRESSIVE BULLISH → DISTRIBUTION**:
- The most dangerous transition. The move has attracted retail buyers, and institutions are now selling into them.
- Timeline: Can happen within 30 minutes of aggressive bullish.
- Signal: Visible flow still looks bullish (retail buying calls), but dark pool shifts to selling. DOM shows icebergs on the ask.
- Trade: Exit longs immediately. Prepare for reversal.

**DEAD → AGGRESSIVE BEARISH**:
- A sudden shift from quiet to aggressive selling. Often triggered by news or a technical break.
- Timeline: Instantaneous. The transition is the signal.
- Trade: Enter short immediately on the first sweep. Don't wait for confirmation.

**DISTRIBUTION → AGGRESSIVE BEARISH**:
- The distribution phase is complete. Institutions have finished exiting. Now they're pushing price lower.
- Timeline: 30-90 minutes from distribution start to aggressive bearish.
- Trade: Enter short during distribution. Add on the transition to aggressive bearish.

### Transition Speed as a Signal

Fast transitions (< 5 minutes) = high urgency. Something has changed. News, technical break, or a large institutional decision.

Slow transitions (> 30 minutes) = deliberate positioning. Institutions are methodically building a position.

---

## Time-of-Day Flow Patterns

Flow behavior is not uniform throughout the session. Each time period has characteristic flow patterns that affect interpretation.

### Opening (9:30 AM - 10:00 AM ET)

**Dominant flow type**: Hedging-heavy. Institutions are adjusting positions from overnight.

**Characteristics**:
- High volume of put buying (hedging overnight longs).
- High volume of call selling (closing overnight call positions).
- Sweeps are common but often represent position adjustments, not new directional bets.
- Dark pool is active but mixed (both buying and selling as positions are rebalanced).

**Interpretation caution**: Do not classify opening flow as directional without confirmation. A large put sweep at 9:31 AM may be a hedge adjustment, not a bearish bet. Wait for the opening range to establish (first 15-30 minutes) before classifying flow.

**Exception**: A massive sweep (> $20M premium) in the first 5 minutes is almost always directional. Someone has information or conviction that can't wait.

### Mid-Morning (10:00 AM - 11:30 AM ET)

**Dominant flow type**: Directional. The most reliable flow period.

**Characteristics**:
- Hedging activity has settled. Remaining flow is directional.
- Sweeps are genuine directional bets.
- Dark pool activity is directional (not rebalancing).
- DOM confirms flow direction.

**Interpretation**: Full classification applies. This is the primary trading window.

### Midday (11:30 AM - 1:30 PM ET)

**Dominant flow type**: Dead or low-conviction.

**Characteristics**:
- Volume drops significantly.
- Flow is thin and often noise.
- Dark pool activity is below average.
- DOM is thin.

**Interpretation**: Apply the DEAD classification unless flow exceeds $10M net premium in 5 minutes. Midday flow that exceeds this threshold is significant — it means someone is trading when nobody else is, which implies high conviction.

### Afternoon (1:30 PM - 3:00 PM ET)

**Dominant flow type**: Directional. The second primary trading window.

**Characteristics**:
- Volume picks up. Institutional activity resumes.
- 0DTE flow dominates (high gamma near expiry).
- Sweeps are genuine directional bets.
- Dark pool activity resumes.

**Interpretation**: Full classification applies. 0DTE sweeps carry extra weight (see `expiry-intent.md`).

### Close (3:00 PM - 4:00 PM ET)

**Dominant flow type**: Charm and closing.

**Characteristics**:
- Charm (the rate of change of delta with respect to time) causes automatic delta hedging as 0DTE options approach expiry.
- Positions are being closed (not opened).
- Flow looks directional but is often mechanical (charm-driven hedging).
- The last 30 minutes can be violent as 0DTE positions expire.

**Interpretation**: Be cautious. Closing flow is not directional. Charm-driven hedging is not directional. Only classify as directional if the flow is clearly new (opening, not closing) and exceeds $20M net premium.

### Weekend/Overnight Positioning

**Monday morning flow** reflects weekend positioning changes:
- Institutions who were long over the weekend may sell on Monday morning (reducing weekend risk).
- Institutions who were short over the weekend may cover on Monday morning.
- Monday morning flow is often the opposite of Friday's closing flow.

**Overnight gap flow**:
- If NQ gaps up significantly overnight, expect put buying at the open (hedging the gap).
- If NQ gaps down significantly overnight, expect call buying at the open (buying the dip).
- These are hedging flows, not directional bets. Apply the HEDGING classification.

---

## Flow Confirmation Requirements for Level Trading

Every level trade (fading a wall, buying a floor, etc.) requires flow confirmation. The flow state must align with the level trade.

### Fading the Call Wall (Short Trade)

**Required flow state**: AGGRESSIVE BEARISH or DISTRIBUTION at the call wall.

**Confirmation**:
- Massive.com: Call selling (at bid) at the call wall strike. Put buying at the call wall strike.
- Unusual Whales: Dark pool selling at the call wall price level.
- Rithmic DOM: Icebergs on the ask at the call wall level.

**Disqualifying flow**: AGGRESSIVE BULLISH at the call wall = the wall is being attacked. Do not fade. Stand aside or trade the break.

### Buying the Put Wall (Long Trade)

**Required flow state**: AGGRESSIVE BULLISH or ACCUMULATION at the put wall.

**Confirmation**:
- Massive.com: Put selling (at bid) at the put wall strike. Call buying at the put wall strike.
- Unusual Whales: Dark pool buying at the put wall price level.
- Rithmic DOM: Icebergs on the bid at the put wall level.

**Disqualifying flow**: AGGRESSIVE BEARISH at the put wall = the wall is being attacked. Do not buy. Stand aside or trade the break.

### Trading the Gamma Flip Crossing

**Required flow state**: AGGRESSIVE BEARISH (for flip crossing downward) or AGGRESSIVE BULLISH (for flip reclaim upward).

**Confirmation**:
- Massive.com: Sustained directional flow (not a single sweep). Multiple sweeps in the same direction.
- Unusual Whales: Dark pool confirming the direction.
- Rithmic DOM: Book confirming the direction (ask-heavy for downward crossing, bid-heavy for upward reclaim).

**Disqualifying flow**: DEAD or HEDGING at the flip = the crossing is not confirmed. Wait.

---

## Quantitative Flow Scoring

For the bias engine, flow state is converted to a numeric score:

```
flow_score = 0  # neutral

if state == AGGRESSIVE_BULLISH:
    flow_score = +3 × conviction_multiplier
elif state == ACCUMULATION:
    flow_score = +2 × conviction_multiplier
elif state == AGGRESSIVE_BEARISH:
    flow_score = -3 × conviction_multiplier
elif state == DISTRIBUTION:
    flow_score = -2 × conviction_multiplier
elif state == HEDGING:
    flow_score = 0  # no directional signal
elif state == DEAD:
    flow_score = 0  # no signal

conviction_multiplier:
    maximum (all thresholds met): 1.0
    moderate (3 of 4 thresholds): 0.7
    low (2 of 4 thresholds): 0.4
    minimum (1 of 4 thresholds): 0.2

# Time-of-day adjustment:
if time in OPENING (9:30-10:00):
    flow_score *= 0.5  # reduce conviction during opening
elif time in MIDDAY (11:30-13:30):
    flow_score *= 0.3  # reduce conviction during midday
elif time in CLOSE (15:00-16:00):
    flow_score *= 0.6  # reduce conviction during close
else:
    flow_score *= 1.0  # full conviction during primary windows
```

---

## Cross-Reference

- For sweep analysis: `sweep-analysis.md`
- For opening vs closing flow: `opening-vs-closing.md`
- For expiry intent: `expiry-intent.md`
- For dark pool reading: `dark-pool-reading.md`
- For level confirmation: `../step2-levels/level-hierarchy.md`
- For regime context: `../step1-regimes/`
