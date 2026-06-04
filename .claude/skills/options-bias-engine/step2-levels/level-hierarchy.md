# Step 2: Level Hierarchy — Options-Derived Price Levels for NQ Futures

## Purpose

This document defines the complete taxonomy of options-derived price levels, their mathematical origins, their behavioral properties, and how to rank them by regime. The hierarchy is not static. The same level that acts as impenetrable resistance in one regime becomes a trapdoor in another. Getting the ranking wrong means trading against the dominant force in the market.

All levels are computed from four data rivers:
- **FlashAlpha**: GEX structure, gamma flip, call/put walls, HVL, expected move
- **Massive.com**: Intraday flow tape, 0DTE volume accumulation by strike
- **Unusual Whales**: Dark pool prints, institutional positioning clusters
- **Rithmic MBO**: Order book confirmation, iceberg detection, depth stacking

NQ levels are derived from QQQ/NDX options using the QQQ-to-NQ conversion ratio of approximately 85.7x. This ratio drifts and should be recalibrated monthly against the actual QQQ/NQ price relationship.

---

## Complete Level Type Taxonomy

### 1. Call Wall

**Source**: FlashAlpha GEX surface  
**Definition**: The strike with the highest positive call gamma exposure (GEX) across all expiries. Dealers who sold these calls are long gamma and must sell the underlying as price rises toward this strike. The selling pressure is mechanical, not discretionary.

**Mathematical basis**:
```
call_gex(K) = sum over all expiries: delta_sensitivity × OI × contract_multiplier
            = sum: (d_delta/d_spot) × OI × 100
            = sum: gamma × OI × 100
```

The call wall is the strike where this sum is maximized across all expiries.

**Behavioral properties**:
- Acts as a ceiling because dealer hedging creates a mechanical headwind. As price approaches the call wall, dealers must sell more of the underlying to remain delta-neutral. This selling pressure increases non-linearly as price gets closer (gamma increases as spot approaches strike).
- The headwind is proportional to the total gamma at the strike. A call wall with 500,000 gamma units is roughly 5x stronger than one with 100,000 units.
- The call wall is NOT a hard ceiling. It can be broken. But breaking it requires sustained buying pressure that overwhelms the dealer hedging flow.
- After a break, the old call wall often becomes support on the first pullback. Dealers who were short gamma at that strike are now long delta and may buy dips.

**Staleness**: FlashAlpha updates GEX every 15-30 minutes during market hours. The call wall can shift between polls as new OI is created or closed. Poll at minimum every 30 minutes. During high-flow periods (open, FOMC, major data), poll every 15 minutes.

**Confirmation requirements**:
- Rithmic DOM: Resting sell orders stacking at or just above the call wall strike. Iceberg detection showing hidden sell orders refreshing as they're consumed.
- Unusual Whales: Dark pool selling at or near the call wall price level.
- Massive.com: Call selling (at bid) at the wall strike, or put buying at the wall strike, as price approaches.

---

### 2. Put Wall

**Source**: FlashAlpha GEX surface  
**Definition**: The strike with the most negative net GEX from puts. Dealers who sold puts are short gamma and must buy the underlying as price falls toward this strike. This buying creates a floor.

**Mathematical basis**:
```
put_gex(K) = -1 × sum over all expiries: gamma × OI × 100
```

The put wall is the strike where this negative sum is most extreme (largest absolute value of negative GEX).

**Behavioral properties in positive gamma regime (spot above gamma flip)**:
- Acts as a floor. Dealer buying as price falls toward the put wall creates mechanical support.
- The closer price gets to the put wall, the stronger the buying pressure (gamma increases near the strike).
- Put wall support is strongest when OI is concentrated (not spread across many strikes) and when expiry is near (higher gamma per unit of OI).
- The put wall in positive gamma is a genuine support level. Fade the breakdown.

**Behavioral properties in negative gamma regime (spot below gamma flip)**:
- The put wall becomes a TRAPDOOR, not a floor. In negative gamma, dealers are amplifying moves, not dampening them. When price breaks through the put wall, dealers must SELL more (not buy) to hedge their now-deeper-in-the-money puts. This creates a cascade.
- Never treat the put wall as support in negative gamma. It's a level to watch for acceleration, not reversal.

**Staleness**: Same as call wall. 30-minute poll minimum, 15-minute during high-activity periods.

**Confirmation requirements**:
- Rithmic DOM: Resting buy orders stacking at or just below the put wall. Icebergs on the bid side.
- Unusual Whales: Dark pool buying at the put wall price level.
- Massive.com: Put selling (at bid) at the wall strike as price approaches, or call buying at the wall.

---

### 3. Gamma Flip

**Source**: FlashAlpha  
**Definition**: The price level where cumulative net GEX across all strikes crosses from positive to negative. This is the regime boundary. Above it, dealers dampen volatility. Below it, dealers amplify volatility.

**Mathematical basis**:
```
net_gex(K) = call_gex(K) - |put_gex(K)|
cumulative_gex(P) = sum of net_gex(K) for all K <= P
gamma_flip = P where cumulative_gex(P) = 0
```

FlashAlpha computes this directly. The flip level is reported as a single price.

**Behavioral properties**: See `gamma-flip-mechanics.md` for full treatment. Summary:
- The gamma flip is the single most important level in the options universe.
- Every other level's behavior changes based on which side of the flip spot is on.
- The flip crossing event is the most dangerous moment in options-driven markets.

**Staleness**: The flip level moves as OI changes. Poll every 30 minutes. Track the direction of movement (rising vs falling flip) as a secondary signal.

**Confirmation requirements**: The flip itself doesn't have order book confirmation in the traditional sense. Instead, look at the zone around the flip for bid/ask imbalance in the DOM. A bid-heavy book near the flip suggests the market is defending positive gamma. An ask-heavy book suggests the market is testing the flip from above.

---

### 4. HVL (High Volatility Level)

**Source**: FlashAlpha  
**Definition**: The strike with the peak absolute GEX, regardless of sign. This is where total hedging activity is maximized. Both call and put dealers are most active here.

**Mathematical basis**:
```
hvl = argmax(|net_gex(K)|) across all strikes
```

Note: HVL is often near the call wall or put wall but not always identical. When HVL and a wall coincide, that level is significantly stronger.

**Behavioral properties**:
- HVL acts as a MAGNET. Price tends to gravitate toward HVL because the hedging activity there creates a self-reinforcing dynamic. Dealers are most active at HVL, which means the most mechanical buying and selling occurs there.
- HVL is particularly powerful as a mean-reversion target. When price is far from HVL, there's a gravitational pull back toward it.
- HVL is also a volatility compression zone. Maximum hedging activity means maximum dampening of moves through that level.
- In pin regime (Regime F), HVL and the pin strike often coincide. This creates near-infinite gamma near expiry.

**Staleness**: Same as walls. 30-minute poll.

**Confirmation requirements**:
- Rithmic DOM: Two-sided depth at HVL. Both bids and offers stacking. This reflects the two-sided hedging activity.
- Massive.com: Mixed flow (both calls and puts trading) at the HVL strike. This is normal — both sides are active.

---

### 5. 0DTE Call/Put Walls

**Source**: Derived from Massive.com intraday flow  
**Definition**: Ephemeral intraday levels created by 0DTE options volume accumulation. These are NOT in FlashAlpha's GEX surface (which includes all expiries). They must be computed separately from the intraday flow tape.

**Computation method**:
```
For each 0DTE strike K:
  0dte_call_volume(K) = sum of call contracts traded at K with 0DTE expiry
  0dte_put_volume(K) = sum of put contracts traded at K with 0DTE expiry
  0dte_net_gex(K) = 0dte_call_volume(K) × gamma(K) - 0dte_put_volume(K) × gamma(K)

0DTE call wall = strike with highest 0dte_call_volume (or highest 0dte_net_gex from calls)
0DTE put wall = strike with highest 0dte_put_volume (or most negative 0dte_net_gex from puts)
```

**Behavioral properties**:
- 0DTE walls are the most powerful INTRADAY levels because 0DTE gamma is the highest gamma per dollar of any options. Near expiry, gamma can be 10-50x higher than equivalent monthly options.
- These walls shift throughout the day as new 0DTE positions are opened and closed.
- By 2:00 PM ET, 0DTE walls are often the dominant force, overriding the multi-expiry walls from FlashAlpha.
- 0DTE walls EVAPORATE at 4:00 PM ET when the options expire. They have zero carryover to the next session.
- The 0DTE call wall is often the intraday high. The 0DTE put wall is often the intraday low.

**Staleness**: Update every 15 minutes from Massive.com flow. These move faster than multi-expiry walls.

**Confirmation requirements**:
- Rithmic DOM: Resting orders at the 0DTE wall level. Icebergs.
- Massive.com: Continued 0DTE flow at the wall strike (confirming the wall is still active, not being closed).

---

### 6. Expected Move High/Low

**Source**: Derived from ATM IV (FlashAlpha Greeks or Massive.com ATM straddle prices)  
**Definition**: The statistical boundary within which price is expected to stay with approximately 68% probability (1 standard deviation). Computed from ATM implied volatility.

**Formulas**:
```
Daily EM = ATM_straddle_price × 0.85
         = spot × IV × sqrt(1/252)

Weekly EM = spot × IV × sqrt(5/252)

NQ EM = QQQ_EM × 85.7  (approximate conversion ratio)
```

The 0.85 adjustment on the straddle method accounts for the fact that the straddle slightly overestimates the expected move due to the convexity of options pricing.

**Behavioral properties**:
- EM boundaries are levels where options sellers' positions become at-risk. When price reaches the EM, short options sellers (who collected premium expecting price to stay within the range) must hedge or close. This creates mechanical support/resistance.
- EM is a STATISTICAL level, not a structural one. It doesn't have the same mechanical force as a GEX wall. But it's self-fulfilling because so many participants use it.
- In low-VIX environments (VIX < 15), EM boundaries are tight and frequently act as precise turning points. The market is "well-behaved" and options sellers are winning.
- In high-VIX environments (VIX > 25), EM boundaries are wide and less reliable. The market is in a regime where moves exceed statistical expectations.

**Staleness**: Recompute at open, midday, and any time IV moves more than 1 point. IV changes throughout the day.

**Confirmation requirements**:
- Rithmic DOM: Resting orders at EM levels. Less reliable than at GEX walls.
- Massive.com: Flow dying at the EM boundary (no new sweeps, premium declining). This is the key confirmation — if flow is still aggressive at the EM, the level may not hold.

---

### 7. Max Pain

**Source**: Derived from OI data (FlashAlpha or CBOE)  
**Definition**: The strike price at which the total dollar value of all outstanding options (calls + puts) is minimized. Options sellers (who are short options) profit most when price expires at max pain.

**Mathematical basis**:
```
For each candidate strike P:
  call_pain(P) = sum over all call strikes K < P: (P - K) × OI(K) × 100
  put_pain(P) = sum over all put strikes K > P: (K - P) × OI(K) × 100
  total_pain(P) = call_pain(P) + put_pain(P)

max_pain = P where total_pain(P) is minimized
```

**Behavioral properties**:
- Max pain has gravitational pull, particularly mid-week to Friday of expiry week. Options market makers (who are net short options) benefit from price gravitating toward max pain, and their hedging activity can create this pull.
- Max pain is most relevant for WEEKLY and MONTHLY expiry. It's irrelevant for 0DTE (too short a timeframe for the gravitational pull to manifest).
- The pull is strongest in the 48 hours before expiry. On Monday and Tuesday of expiry week, max pain is a background signal. By Thursday and Friday, it's a primary signal.
- Max pain can be 50-200 NQ points away from spot. When it's close (within 50 NQ points), the pull is strong. When it's far, it's a background reference only.
- Max pain is NOT a reversal signal. It's a gravitational pull. Price can overshoot max pain and then revert.

**Staleness**: Recompute daily. Max pain shifts as OI changes (new positions opened, old positions closed). The shift direction is a signal: max pain moving toward spot = increasing gravitational pull.

**Confirmation requirements**: Max pain doesn't require order book confirmation in the same way as GEX walls. It's a statistical tendency, not a mechanical force. Use it as a tiebreaker when other signals are mixed.

---

### 8. Pin Strike

**Source**: Derived from 0DTE OI (Massive.com or CBOE)  
**Definition**: The strike with the highest combined 0DTE call + put OI. Relevant only in pin regime (Regime F). Near expiry, the gamma at this strike approaches infinity, creating a near-gravitational pull.

**Mathematical basis**:
```
pin_strike = argmax(call_OI(K, 0DTE) + put_OI(K, 0DTE)) across all strikes K
```

**Behavioral properties**:
- In pin regime, the pin strike is THE ONLY LEVEL THAT MATTERS. Everything else is secondary.
- The pin effect is strongest in the final 2 hours of trading on expiry day. Before that, it's a background force.
- Price "pins" to the strike because: (1) Dealers are long gamma at the pin and must sell rallies and buy dips, creating a self-reinforcing range. (2) Options sellers want price to expire at the pin (max pain often coincides). (3) Retail traders who sold options at the pin are defending their positions.
- The pin can break if a large directional catalyst (news, macro data) overwhelms the gamma force. When the pin breaks, the move is violent because all the gamma that was dampening volatility suddenly reverses.

**Staleness**: Update every 15 minutes on expiry day. The pin strike can shift as 0DTE OI changes.

**Confirmation requirements**:
- Rithmic DOM: Two-sided depth at the pin strike. Both bids and offers. The market is balanced at the pin.
- Massive.com: Mixed 0DTE flow at the pin strike. Both calls and puts trading. This is the hedging activity.

---

### 9. Dark Pool Cluster

**Source**: Unusual Whales  
**Definition**: Price levels where dark pool volume concentrates. These represent institutional positioning zones where large players have been accumulating or distributing.

**Computation**: Unusual Whales aggregates dark pool prints by price level. A cluster is defined as 3+ prints within a 10-tick NQ range, or a single print exceeding $50M notional.

**Behavioral properties**:
- Dark pool clusters are INSTITUTIONAL MEMORY. Large players who accumulated at a level will defend it (if long) or attack it (if short) when price returns.
- A dark pool buying cluster below spot = institutional support. They bought there and will buy again on a retest.
- A dark pool selling cluster above spot = institutional resistance. They sold there and will sell again.
- Dark pool clusters are most reliable when they're recent (within the last 5 trading days). Older clusters fade as positions are adjusted.
- Dark pool clusters at GEX levels (call wall, put wall, HVL) are 2-3x more significant. Institutional positioning aligning with options structure = maximum conviction level.

**Staleness**: Dark pool data has a reporting delay of 10 seconds to several minutes. Update the cluster map at the start of each session and after major moves.

**Confirmation requirements**:
- Rithmic DOM: Icebergs at the cluster level. Institutions who accumulated in dark pools often defend with icebergs on the lit exchange.
- Massive.com: Flow at the cluster level. If institutions are defending, you'll see call buying (if defending a long) or put buying (if defending a short).

---

## Priority Matrix by Regime

### Regime A: Positive Gamma, Between Walls (Spot above flip, between put wall and call wall)

This is the "normal" regime. Dealers are dampening volatility. Price oscillates between the walls.

| Rank | Level | Role | Action |
|------|-------|------|--------|
| 1 | Call Wall | Ceiling | Fade rallies approaching call wall |
| 1 | Put Wall | Floor | Fade selloffs approaching put wall |
| 2 | HVL | Magnet | Expect mean reversion toward HVL |
| 2 | 0DTE Call Wall | Intraday ceiling | Fade intraday rallies (after 11 AM) |
| 2 | 0DTE Put Wall | Intraday floor | Fade intraday selloffs (after 11 AM) |
| 3 | Expected Move High | Statistical ceiling | Secondary fade target |
| 3 | Expected Move Low | Statistical floor | Secondary fade target |
| 4 | Max Pain | Gravitational pull | Background reference (stronger Thu-Fri) |
| 4 | Dark Pool Clusters | Institutional S/R | Confirmation layer |
| 5 | Gamma Flip | Monitor only | Far from spot; watch for approach |

**Trading implication**: Range-bound. Sell call wall, buy put wall. HVL is the mean. 0DTE walls are the intraday range. EM is the outer boundary.

---

### Regime B: At Call Wall (Spot within 0.5% of call wall)

The market is testing the ceiling. This is a decision point.

| Rank | Level | Role | Action |
|------|-------|------|--------|
| 1 | Call Wall | THE level | Everything depends on whether it holds or breaks |
| 2 | 0DTE Call Wall | Intraday ceiling | If 0DTE wall coincides, level is 2x stronger |
| 3 | Dark Pool Clusters | Institutional intent | Dark pool selling = wall holds. Dark pool buying = break incoming. |
| 4 | HVL | Post-break target | If wall breaks, HVL at next strike is the next target |
| 5 | Expected Move High | Outer boundary | If EM high is above call wall, break has room to run |

**Trading implication**: Do NOT fade the call wall blindly. Confirm with DOM (icebergs refreshing = wall holds), flow (call selling at wall = wall holds; call buying = break incoming), and dark pool (selling = wall holds). If all three confirm the wall, fade. If any two suggest a break, stand aside or trade the break.

---

### Regime C: At Put Wall (Spot within 0.5% of put wall)

The market is testing the floor. Mirror of Regime B.

| Rank | Level | Role | Action |
|------|-------|------|--------|
| 1 | Put Wall | THE level | Everything depends on whether it holds or breaks |
| 2 | 0DTE Put Wall | Intraday floor | If 0DTE wall coincides, level is 2x stronger |
| 3 | Dark Pool Clusters | Institutional intent | Dark pool buying = wall holds. Dark pool selling = trapdoor. |
| 4 | HVL | Post-break target | If wall breaks, HVL at next lower strike is the next target |
| 5 | Expected Move Low | Outer boundary | If EM low is below put wall, break has room to run |

**Trading implication**: Same logic as Regime B but inverted. Confirm with DOM (icebergs on bid = wall holds), flow (put selling at wall = wall holds; put buying = break incoming), and dark pool.

---

### Regime D: Negative Gamma, Above Gamma Flip (Spot below call wall, above gamma flip, but in negative gamma zone)

This regime occurs when the gamma flip has risen above the put wall, or when OI structure creates negative gamma above the flip. Rare but important.

| Rank | Level | Role | Action |
|------|-------|------|--------|
| 1 | Gamma Flip | Regime boundary | If lost, transition to Regime E |
| 2 | Call Wall | Weak resistance | Dealers amplifying, not dampening. Wall is weaker. |
| 3 | Put Wall | Weak support | Trapdoor risk if broken |
| 4 | Dark Pool Clusters | Institutional intent | More important than usual — need institutional support |
| 5 | Expected Move | Reference only | Less reliable in negative gamma |

**Trading implication**: Reduce position size. Levels are less reliable. Focus on the gamma flip as the key level. If spot holds above the flip, there's hope for regime recovery. If the flip is lost, transition to Regime E playbook.

---

### Regime E: Negative Gamma, Below Gamma Flip (Spot below gamma flip)

The most dangerous regime. Dealers are amplifying every move. Volatility is self-reinforcing.

| Rank | Level | Role | Action |
|------|-------|------|--------|
| 1 | Gamma Flip | Reclaim = reversal signal | The only bullish signal that matters |
| 2 | Put Wall | Trapdoor, not support | Do NOT buy the put wall. It accelerates on break. |
| 3 | Dark Pool Clusters | Institutional accumulation | The only genuine support signal |
| 4 | Expected Move Low | Outer boundary | May be exceeded. Reference only. |
| 5 | Call Wall | Irrelevant | Too far from spot. Ignore. |
| 6 | HVL | Potential target | If regime recovers, HVL is the first target |

**Trading implication**: Do not fade. Trade with the trend. The only reversal signal is a confirmed reclaim of the gamma flip (price crosses back above, confirmed by call buying in flow and dark pool buying). Until then, every bounce is a selling opportunity.

---

### Regime F: Pin (Expiry day, spot within 0.5% of pin strike)

The pin regime. Near-infinite gamma at the pin strike. Price is trapped.

| Rank | Level | Role | Action |
|------|-------|------|--------|
| 1 | Pin Strike | THE ONLY LEVEL | Everything else is noise |
| 2 | 0DTE Call Wall | Upper pin boundary | If above pin, this is the ceiling |
| 2 | 0DTE Put Wall | Lower pin boundary | If below pin, this is the floor |
| 3 | Max Pain | Coincides with pin | Confirms the pin |
| 4 | All other levels | Irrelevant | Ignore |

**Trading implication**: Do not trade directionally. The pin is a range-bound regime. Sell options (if you trade options). For futures, trade the range between 0DTE walls. The pin breaks violently when it breaks — be ready to exit immediately.

---

### Regime G: Pre-Event (FOMC, CPI, NFP within 24 hours)

All levels are stale. IV is elevated. The market is pricing in a move that hasn't happened yet.

| Rank | Level | Role | Action |
|------|-------|------|--------|
| 1 | Expected Move | Range context | The EM tells you what the market expects the event to cause |
| 2 | Call Wall | Pre-event ceiling | Useful for context, not for trading |
| 2 | Put Wall | Pre-event floor | Useful for context, not for trading |
| 3 | All other levels | Stale | Do not trade against them |

**Trading implication**: Reduce or eliminate positions before the event. Use EM to understand the expected range. After the event, re-poll FlashAlpha immediately — the GEX structure will have changed dramatically as hedges are removed and new positions are opened.

---

## Level Confluence Rules

When multiple level types stack within the same price zone, the combined level is significantly stronger than any individual component.

**Confluence thresholds**:
- Within 10 NQ ticks (2.5 points): Treat as a single level. Strength = sum of individual strengths.
- Within 20 NQ ticks (5 points): Strong confluence. Strength = 1.5x the strongest individual level.
- Within 40 NQ ticks (10 points): Moderate confluence. Strength = 1.2x the strongest individual level.
- Beyond 40 NQ ticks: No confluence. Treat as separate levels.

**Confluence examples**:
- Call wall + 0DTE call wall + EM high all within 10 ticks: Maximum ceiling. Fade with high conviction.
- Put wall + dark pool buying cluster within 10 ticks: Maximum floor. Buy with high conviction.
- HVL + max pain within 20 ticks: Strong magnet. Expect mean reversion toward this zone.
- Gamma flip + dark pool cluster within 20 ticks: Contested regime boundary with institutional interest. High-stakes level.

**Confluence scoring** (for the bias engine):
```
confluence_score = sum of individual level scores within the zone
level_scores:
  call_wall = 10
  put_wall = 10
  gamma_flip = 15
  hvl = 8
  0dte_call_wall = 9
  0dte_put_wall = 9
  expected_move = 6
  max_pain = 5
  pin_strike = 12
  dark_pool_cluster = 7
```

A confluence score above 20 at a level = high-conviction level. Above 30 = maximum conviction.

---

## Level Invalidation Rules

Levels degrade over time and after specific events. A level that has been tested multiple times without holding is no longer reliable.

**Test count rules**:
- First test: Full strength. The level has not been challenged.
- Second test: 80% strength. The level held once but is being challenged again.
- Third test: 50% strength. The level is weakening. Probability of break increases.
- Fourth test: 20% strength. The level is likely to break. Do not fade.
- After break: The level becomes the opposite type (call wall becomes support, put wall becomes resistance) but at 40% strength for the first retest.

**Time-based staleness**:
- GEX walls: Stale after 2 hours without a FlashAlpha poll update.
- 0DTE walls: Stale after 30 minutes without a Massive.com flow update.
- Dark pool clusters: Stale after 5 trading days.
- Expected move: Stale after IV moves more than 1 point.
- Max pain: Stale after 24 hours.

**Event-based invalidation**:
- Any level within 50 NQ points of a major news event print: Invalidated immediately. Re-poll all sources.
- OPEX (monthly options expiration): All levels reset. Re-poll FlashAlpha after 10:00 AM on OPEX Friday.
- Gamma flip crossing: All level rankings reset. Apply new regime's priority matrix.

---

## Cross-Reference

- For gamma flip mechanics in detail: `gamma-flip-mechanics.md`
- For wall movement and break mechanics: `wall-dynamics.md`
- For expected move computation: `expected-move-computation.md`
- For regime definitions: `../step1-regimes/`
- For flow confirmation of levels: `../step3-flow/flow-interpretation.md`
- For order book confirmation: Rithmic MBO integration (absorption signals at level)
