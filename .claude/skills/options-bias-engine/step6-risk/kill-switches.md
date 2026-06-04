# Step 6: Risk — Kill Switches

## Overview

Eight mandatory gates. Every gate must PASS before any trade executes. A single FAIL blocks the trade entirely, regardless of how strong the setup looks. These are not suggestions. They are hard stops.

The gates exist because the options bias engine synthesizes data from four rivers, each with its own latency, reliability, and interpretation risk. Even when all four rivers agree, the market can be in a state where acting on that agreement is dangerous. The kill switches protect against those states.

Evaluate all eight gates in sequence before every trade recommendation. Log the result of each gate. If any gate fails, log WHY it failed and what condition would need to change for it to pass.

---

## GATE 1: REGIME CLARITY

**Question:** Can the current regime be unambiguously identified from the four rivers?

### What "unclear" looks like

Regime clarity fails when any of the following conditions are true:

**Total GEX near zero.** When total GEX (sum of all strikes, all expirations) is between -$500M and +$500M, the gamma flip level is unreliable. The sign of total GEX can flip on a single large print. You cannot confidently say whether dealers are long or short gamma. Threshold: |Total GEX| < $500M = UNCLEAR.

**Spot oscillating around the gamma flip.** If NQ price has crossed the gamma flip level more than twice in the last 30 minutes, the regime is in transition. Each crossing changes the dealer hedging direction. The system cannot assign a stable regime letter. Detection: track flip crossings with timestamps. If crossing_count_30min >= 3, regime is UNCLEAR.

**Walls shifting rapidly.** If FlashAlpha data shows the call wall or put wall moving by more than 50 NQ points between consecutive polls (5-minute interval), the options market is repricing aggressively. This happens during fast-moving markets when large positions are being rolled or closed. The wall you're trading against may not exist by the time you enter. Detection: |current_wall - prev_wall| > 50 pts on any consecutive poll = UNCLEAR.

**Conflicting regime signals across expirations.** If 0DTE GEX says Regime A (positive, mid-range) but weekly GEX says Regime E (negative, below flip), the expirations are fighting each other. The dominant expiration (by GEX magnitude) wins, but if the magnitudes are within 20% of each other, the conflict is unresolvable. Detection: if |0DTE_GEX| / |weekly_GEX| is between 0.8 and 1.2 AND they imply different regimes = UNCLEAR.

### When regime IS clear

Regime is clear when:
- Total GEX magnitude > $500M with a definitive sign
- Spot has not crossed the flip in the last 30 minutes
- Walls have moved less than 50 pts between the last two polls
- The dominant expiration (by GEX magnitude) is unambiguous

### Response to unclear regime

NO TRADE. Do not attempt to trade through regime ambiguity. The regime is the foundation of every other signal interpretation. Without it, you don't know whether a call wall is a ceiling or a target, whether a put wall is a floor or a trap, or whether dealer hedging is amplifying or dampening your move.

Retry interval: Re-evaluate every 5 minutes. Log each evaluation. When regime stabilizes (all four clarity conditions pass), resume normal evaluation.

Regime transitions are the most dangerous periods in the entire trading day. The gamma flip crossing is where the most violent, unpredictable moves happen. The system is designed to PROFIT from regime transitions via Setup 3 (Gamma Flip Cross), but only when the transition is confirmed and the new regime is established. During the transition itself, stay flat.

---

## GATE 2: MINIMUM CONVICTION

**Question:** Do at least 3 of 5 data dimensions agree on direction?

### The five dimensions

1. Structural (GEX/DEX/VEX/CHEX from FlashAlpha)
2. Flow (options flow from Massive.com)
3. Dark (dark pool prints from Unusual Whales)
4. DOM (order book signals from Rithmic MBO)
5. Derived (vanna/charm/pin calculations)

Each dimension produces a directional vote: BULLISH, BEARISH, or NEUTRAL. NEUTRAL does not count toward either direction.

### Conviction threshold

Minimum 3 of 5 dimensions must agree on the SAME direction (bullish or bearish). If only 2 agree, or if the votes are split 2-2 with 1 neutral, or if 3 are neutral, the conviction is insufficient.

Reference: `step4-cross-validation/conviction-matrix.md` for the full scoring matrix and how each dimension's vote is computed.

### The iceberg exception

If EXACTLY 2 dimensions agree on direction, but one of those 2 is "iceberg detected at GEX level" (from the DOM dimension, specifically OB-4 iceberg detection), treat the conviction as 3/5.

Rationale: An iceberg at a GEX level is the single highest-conviction individual signal in the entire system. It represents a large, informed participant deliberately hiding their order at a price that coincides with the options structure. This combination of institutional knowledge + willingness to deploy size + deliberate concealment is worth an extra conviction point.

This exception applies ONLY when:
- The iceberg is at a GEX level (call wall, put wall, gamma flip, or expected move boundary)
- The iceberg direction aligns with the 2 agreeing dimensions
- The iceberg has been active for at least 60 seconds (not a flash)

### Response to insufficient conviction

NO TRADE. Log which dimensions agreed, which were neutral, which opposed. This log is valuable for post-session review — if a setup had 2/5 conviction and would have been profitable, that's a signal to investigate whether one of the neutral dimensions should have been reading differently.

---

## GATE 3: FLOW IS ALIVE

**Question:** Is there meaningful options activity happening right now?

### Why flow matters

The GEX structure (call walls, put walls, gamma flip) is computed from open interest — positions that were established in the past. OI data is updated daily, not in real time. The structure tells you WHERE the levels are, but not whether those levels are CURRENTLY being reinforced or abandoned.

Options flow (sweeps, blocks, premium) is the CURRENT signal. It tells you what participants are doing RIGHT NOW. Without flow, you're trading on a map that may be outdated.

### Dead market thresholds

**Net premium threshold:** If net options premium (calls minus puts, or directional premium) is less than $3M in the last 15 minutes, the market is effectively dead from an options perspective. No meaningful positioning is happening. Threshold: |net_premium_15min| < $3M = DEAD MARKET.

**Sweep and block count:** If sweep count = 0 AND block count = 0 in the last 30 minutes, confirmed dead. Both conditions must be true simultaneously. A single sweep in 30 minutes is not enough — it could be a one-off hedge, not a directional signal.

**Combined dead market condition:** Either the premium threshold OR the sweep+block threshold triggers a DEAD MARKET classification. Both conditions independently indicate insufficient flow.

### Response to dead market

NO TRADE for directional setups. The structural levels exist but there's no current information confirming they're being respected.

### The vanna/charm exception

Setups 4 (Vanna Rally) and 5 (Charm Flow) are MECHANICAL flows driven by options math, not human decision-making. Vanna flows occur when VIX moves and dealers must rehedge their delta exposure. Charm flows occur as time passes and delta decays. These flows happen whether or not humans are actively trading options.

For Setups 4 and 5 ONLY: the flow-is-alive gate is modified. Instead of requiring human flow (sweeps, blocks, premium), require:
- VIX movement > 0.5 points in the last 30 minutes (for vanna)
- Time within 90 minutes of market close (for charm)
- The mechanical flow calculation showing directional bias > 30 (from `step3-derived/vanna-charm.md`)

If these mechanical conditions are met, the gate passes even in a dead human-flow market.

---

## GATE 4: NO EVENT WITHIN 30 MINUTES

**Question:** Is there a market-moving scheduled event within the next 30 minutes?

### Event categories

**Tier 1 — Absolute no-trade zone (30 min before, 15 min after):**
- FOMC rate decisions (8 per year, 2:00 PM ET)
- FOMC press conferences (2:30 PM ET, same days)
- CPI (monthly, 8:30 AM ET)
- NFP — Non-Farm Payrolls (first Friday of month, 8:30 AM ET)
- PCE — Personal Consumption Expenditures (monthly, 8:30 AM ET)

**Tier 2 — Reduced size zone (15 min before, 10 min after):**
- PPI (monthly, 8:30 AM ET)
- ISM Manufacturing/Services (monthly, 10:00 AM ET)
- Retail Sales (monthly, 8:30 AM ET)
- GDP (quarterly, 8:30 AM ET)
- Consumer Confidence (monthly, 10:00 AM ET)

**Tier 3 — Awareness only (no automatic gate, but note in narrative):**
- Mega-cap earnings: AAPL, MSFT, NVDA, GOOG, AMZN, META, TSLA
  - These move NQ by 0.5-2% on their own. If earnings are after-hours, the pre-earnings session can be distorted by hedging flows.
  - If any of these report within 2 hours of market close, treat the last 30 minutes of the session as elevated risk.
- Fed speaker events (not FOMC decisions, but major speeches)
- Treasury auctions (10-year, 30-year) — can spike rates and move NQ

### Maintaining the event calendar

Check CME Group economic calendar daily before market open. Update the system's event list each morning. For mega-cap earnings, check the earnings calendar weekly (FactSet, Earnings Whispers, or Bloomberg).

The system should maintain a sorted list of upcoming events with timestamps. Before each trade evaluation, check: is any Tier 1 or Tier 2 event within 30 minutes? If yes, gate fails.

### Existing positions during events

If you're already in a position when an event approaches:
- Tier 1 event: Close or tighten stop to breakeven before the event. Do not hold through FOMC or CPI.
- Tier 2 event: Tighten stop. Consider taking partial profits.
- Tier 3 event: Note in narrative. No automatic action required.

### Post-event re-entry

After a Tier 1 event, wait 15-30 minutes for the new regime to establish. The initial reaction is often reversed. The second move (after the initial spike and reversal) is more reliable. Re-evaluate all eight gates from scratch after the waiting period.

---

## GATE 5: NOT IN FIRST 5 MINUTES

**Question:** Is the current time after 9:35 AM ET?

### Why the first 5 minutes are untradeable

**Opening noise.** The first 5 minutes of the session (9:30-9:35 AM ET) are characterized by:
- Overnight orders executing simultaneously, creating artificial volume spikes
- Options spreads widening to 2-5x their normal width
- False signals in every data stream as the market finds its opening price
- DOM depth that is thin and unreliable — large orders can move price 10-20 points with no follow-through

**GEX levels need current spot.** The gamma flip and wall levels are computed relative to current spot price. The first FlashAlpha poll after open needs to see where spot actually opened before the GEX levels are meaningful. If NQ gaps 50 points at open, the pre-open GEX map is stale until FlashAlpha recalculates with the new spot.

**Spoofing is rampant.** The opening 5 minutes see the highest concentration of spoofed orders in the entire session. HFT firms test the book aggressively. Any DOM signal in this window is unreliable.

### The gap exception

If NQ gaps more than 2% at open (approximately 400+ points on NQ at 20,000), the gap direction itself carries information. A 2%+ gap up means overnight buyers were aggressive enough to move price significantly. A 2%+ gap down means sellers were dominant.

Even with a large gap, still wait until 9:35 AM before entering. The gap direction is noted in the morning narrative, but no trade executes before 9:35.

### Implementation

The system checks current time (ET) before every trade evaluation. If time < 9:35:00 AM ET, gate fails automatically. No exceptions beyond the gap note above.

---

## GATE 6: NOT FIGHTING THE REGIME

**Question:** Does the proposed trade direction align with the current regime's character?

### Specific prohibitions

**NEVER long in Regime E (negative gamma, below flip).**
Regime E is the trending-down regime. Dealers are short gamma and must sell into weakness, amplifying every down move. The put wall has broken. There is no structural floor. Longs in Regime E are fighting the dealer hedging cascade. The only valid trade in Regime E is short (trend-following) or flat.

**NEVER short at the put wall in Regime A or C (positive gamma).**
In positive gamma regimes, the put wall is a defended floor. Dealers are long gamma and buy dips. The put wall has massive GEX support. Shorting at the put wall means fighting both the GEX mechanics AND the dealer hedging. The put wall in Regime A/C is the highest win-rate long setup in the system (Setup 1, Wall Bounce). Shorting it is the opposite of the highest win-rate trade.

**NEVER long at the call wall in Regime A or B (positive gamma).**
The call wall is the ceiling. Dealers sell rallies at the call wall. The call wall has massive negative GEX (call gamma creates selling pressure above). Longing at the call wall means fighting the ceiling mechanics. The only valid long at the call wall is a wall break setup (Setup 2) with 5/5 conviction and confirmed depletion.

**NEVER take directional trades in Regime F (pin regime).**
Regime F is the pinning regime — price is being held near a high-OI strike by gamma forces. The expected range is extremely tight (often 10-20 NQ points). Directional trades in Regime F have poor R:R because the target is too close and the stop is too wide relative to the expected move. The only valid trade in Regime F is a fade (sell the top of the pin range, buy the bottom).

**NEVER take any directional trade in Regime G (pre-event).**
Regime G is the pre-event regime — the market is waiting for a scheduled catalyst. Options flow is hedging, not directional. GEX levels may be irrelevant post-event. DOM is thin and unreliable. No trade.

### The Setup 3 exception

Setup 3 (Gamma Flip Cross) is the ONLY regime-opposition trade allowed. By definition, this setup involves entering a trade in the direction that BECOMES the new regime — which means entering while the old regime is still technically in effect.

Specifically: if price is approaching the gamma flip from above (about to cross into negative gamma), Setup 3 allows a short entry BEFORE the flip is confirmed. The entry is in the direction of the new regime (bearish), not the current regime (bullish). This is allowed because:
- The setup has specific confirmation requirements (see `step2-setups/setup3-gamma-flip.md`)
- The stop is tight (just above the flip level)
- The R:R is the highest of any setup in the system

Setup 3 is the ONLY exception. All other regime-opposition trades are prohibited.

---

## GATE 7: DATA FRESHNESS

**Question:** Are all four data sources current?

### Freshness thresholds by source

**FlashAlpha (GEX/DEX/VEX/CHEX):**
- Maximum age: 3 minutes since last successful poll
- Why: GEX levels can shift meaningfully in 3 minutes during active markets. A call wall that was at 21,350 three minutes ago may now be at 21,300 if large positions were closed.
- Staleness indicator: Track `flashalpha_last_success_ts`. If `now - flashalpha_last_success_ts > 180s`, mark STALE.

**Massive.com (options flow):**
- Maximum age: 90 seconds since last successful data pull
- Why: Options flow is the most time-sensitive signal. A sweep that happened 2 minutes ago may already be fully priced in. Flow signals decay rapidly.
- Staleness indicator: Track `massive_last_success_ts`. If `now - massive_last_success_ts > 90s`, mark STALE.

**Unusual Whales (dark pool):**
- Maximum age: 3 minutes since last successful pull
- Note: UW data has inherent lag of 15-30 minutes from the actual dark pool print. The 3-minute freshness threshold refers to the last time the system successfully pulled from UW, not the age of the underlying dark pool data. Dark pool data is always somewhat stale by nature.
- Staleness indicator: Track `uw_last_success_ts`. If `now - uw_last_success_ts > 180s`, mark STALE.

**Rithmic MBO (NQ order book):**
- Maximum age: 5 seconds since last callback
- Why: The order book is a real-time feed. If 5 seconds pass without a callback, the connection is likely broken. Trading on a stale order book is trading blind.
- Staleness indicator: Track `rithmic_last_callback_ts`. If `now - rithmic_last_callback_ts > 5s`, mark CRITICAL STALE.
- Response: IMMEDIATE alert. Attempt reconnection. NO TRADE until reconnected and book is rebuilt.

### Response to staleness

**1 source stale (non-Rithmic):** Reduce position size by 25%. The remaining three sources carry more weight. Log which source is stale and why (network timeout, API error, rate limit).

**Rithmic stale (any duration):** NO TRADE. The order book is the real-time ground truth. Without it, you cannot evaluate DOM signals (OB-1 through OB-6), cannot detect icebergs, cannot measure aggression imbalance. The options signals alone are insufficient for trade execution.

**2+ sources stale (any combination):** NO TRADE. Two stale sources means the synthesis is too incomplete to be reliable.

### Staleness detection implementation

```python
class FreshnessMonitor:
    thresholds = {
        'flashalpha': 180,   # seconds
        'massive': 90,
        'unusual_whales': 180,
        'rithmic': 5
    }
    
    def check_all(self) -> dict:
        now = time.time()
        results = {}
        for source, threshold in self.thresholds.items():
            last_ts = self.last_success[source]
            age = now - last_ts
            results[source] = {
                'age_seconds': age,
                'stale': age > threshold,
                'critical': source == 'rithmic' and age > threshold
            }
        return results
    
    def gate_passes(self, results: dict) -> tuple[bool, str]:
        stale_count = sum(1 for r in results.values() if r['stale'])
        if results['rithmic']['stale']:
            return False, "RITHMIC CRITICAL: order book connection lost"
        if stale_count >= 2:
            return False, f"{stale_count} sources stale: {[k for k,v in results.items() if v['stale']]}"
        return True, "all sources fresh" if stale_count == 0 else "1 source stale: reduce size 25%"
```

---

## GATE 8: CONSECUTIVE LOSS LIMIT

**Question:** Have there been 3 or more consecutive losses in this session?

### The three-loss rule

Three consecutive losses in a single session triggers a mandatory stop for the remainder of that session. No exceptions.

### Why three losses means stop

Three consecutive losses after a calibrated system is running means one of three things:

**The regime has changed and the system hasn't adapted.** The most common cause. The market structure shifted (e.g., a large options position was closed, changing the GEX landscape) and the system is still trading the old regime. Three losses in a row is the signal that the map no longer matches the territory.

**The data sources are unreliable today.** Exchange issues, API anomalies, unusual market structure (e.g., a major index rebalancing day) can corrupt the signals. If the data is wrong, the synthesis is wrong, and the trades are wrong. Three losses is the empirical confirmation.

**It's an anomalous day.** News-driven markets, liquidity crises, flash crashes, or major macro events can render the entire options-based framework irrelevant. On these days, the GEX levels don't hold, the flow signals are noise, and the DOM is chaotic. Three losses is the signal to step aside.

In all three cases, continuing to trade makes the situation worse. The system is not designed to trade through its own failure modes.

### Daily maximum loss

Independent of the consecutive loss count, define a dollar-based daily maximum loss. Suggested: 50 NQ points total session loss OR 2% of account, whichever is smaller.

At $20/point per NQ contract, 50 NQ points = $1,000 per contract. For a 2-contract base position, that's $2,000 maximum daily loss.

Once the daily maximum loss is hit, NO MORE TRADES for the session, regardless of consecutive win/loss count.

### Recovery protocol

After a three-loss stop or daily max loss stop:
1. Do not trade the remainder of the session.
2. Review each losing trade: Was the regime correctly identified? Were the levels reliable? Was the flow reading accurate? Was the DOM signal correct?
3. Identify the failure mode: regime change, data issue, or anomalous day.
4. Next trading day: Re-calibrate. Start with reduced size (50% of base) for the first 2 trades. Return to full size only after 2 consecutive wins.

### Consecutive loss tracking

```python
class SessionLossTracker:
    def __init__(self):
        self.consecutive_losses = 0
        self.total_session_pnl_pts = 0.0
        self.daily_max_loss_pts = 50.0
    
    def record_trade(self, pnl_pts: float):
        self.total_session_pnl_pts += pnl_pts
        if pnl_pts < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0  # reset on any win
    
    def gate_passes(self) -> tuple[bool, str]:
        if self.consecutive_losses >= 3:
            return False, f"3 consecutive losses — session stopped"
        if self.total_session_pnl_pts <= -self.daily_max_loss_pts:
            return False, f"Daily max loss hit: {self.total_session_pnl_pts:.1f} pts"
        return True, f"consecutive_losses={self.consecutive_losses}"
```

---

## Gate Evaluation Summary

```
GATE 1: REGIME CLARITY          [PASS/FAIL]  reason
GATE 2: MINIMUM CONVICTION      [PASS/FAIL]  X/5 dimensions aligned
GATE 3: FLOW IS ALIVE           [PASS/FAIL]  net_premium=$Xm, sweeps=N
GATE 4: NO EVENT WITHIN 30 MIN  [PASS/FAIL]  next_event=HH:MM (type)
GATE 5: NOT IN FIRST 5 MIN      [PASS/FAIL]  current_time=HH:MM ET
GATE 6: NOT FIGHTING REGIME     [PASS/FAIL]  regime=X, direction=Y
GATE 7: DATA FRESHNESS          [PASS/FAIL]  stale_sources=[list]
GATE 8: CONSECUTIVE LOSS LIMIT  [PASS/FAIL]  consecutive=N, session_pnl=X pts

OVERALL: [TRADE ALLOWED / TRADE BLOCKED]
```

All eight gates must show PASS for a trade to execute. One FAIL = blocked. Log every evaluation with timestamp.
