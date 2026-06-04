# Institutional Flow Taxonomy — NQ Options Deep Expertise

> Extends `options-bias-engine/step3-flow/flow-interpretation.md` with institutional-grade depth.
> Academic backing: Pan & Poteshman (2006), Hu (2014), Ge Lin Pearson (2016), CBOE 0DTE Report (2025).
> NQ/QQQ focus throughout. Reader is assumed advanced — no retail-level explanations.

---

## 1. The 7-Player Taxonomy

Every options print on the tape comes from one of seven institutional archetypes. Misidentifying the player type leads to wrong directional inference. A pension fund buying puts is NOT the same signal as a macro fund buying puts.

| Player | Primary Strategy | Options Signature | Flow Pattern | Tape Fingerprint | Information Signal |
|--------|-----------------|-------------------|--------------|------------------|--------------------|
| **Pension Fund** | Equity portfolio protection, liability matching | Long-dated (90-180 DTE) OTM puts on SPX/QQQ, collars, covered calls | Systematic, calendar-driven, size-insensitive to premium | Large blocks at mid or below mid, no urgency, often split across days, exchange-reported not dark | LOW — mechanical hedging, not directional conviction. Ignore for NQ bias. |
| **Vol Seller** | Premium collection, short volatility | Short strangles/straddles, short OTM puts (cash-secured), short calls against long equity | Consistent selling at bid, elevated OI at round strikes, OI builds without directional flow | Prints at bid, V/OI stays low (adding to existing short), IV crush after print | NEGATIVE for vol — signals IV is elevated relative to realized. Not directional. Watch for forced unwinds when VIX spikes. |
| **Tail Hedger** | Black swan protection, convexity | Far OTM puts (5-15% OTM), long-dated (90-365 DTE), VIX calls, VVIX calls | Sporadic, event-driven, size-insensitive, often dark pool | Prints at ask on far OTM strikes, V/OI > 2.0 on low-OI strikes, premium per contract is tiny but total premium is large | BEARISH CONTEXT signal — not a trade trigger, but tells you institutional risk appetite is elevated. When tail hedging accelerates, regime is fragile. |
| **Directional Macro** | Leveraged directional bets on macro thesis | Near-ATM or slightly OTM calls/puts, 21-60 DTE, sweeps across exchanges, high premium | Aggressive, urgency-driven, sweeps at ask (calls) or bid (puts), concentrated in 1-3 strikes | Multi-exchange sweep in milliseconds, V/OI > 1.5, premium > $250K, consistently at ask/bid, OI confirms next day | HIGHEST SIGNAL — this is the player you're tracking. Directional macro sweeps are the primary flow signal for NQ bias. |
| **Market Maker** | Delta-neutral inventory management, spread capture | Continuous two-sided quotes, dynamic hedging via futures, short gamma by default | Appears on both sides, net flow is noise, but their HEDGING creates mechanical price pressure | Tight bid/ask, high volume at multiple strikes simultaneously, futures prints coincide with options prints | STRUCTURAL signal — MM hedging creates the GEX walls. Their delta hedging IS the mechanical support/resistance. Not a directional signal from their flow, but their positioning creates the levels. |
| **Equity Portfolio Hedger** | Protect long equity book against drawdown | QQQ/SPX puts, collars, protective puts, ratio spreads | Systematic but reactive to market moves, accelerates on rallies (buying puts when cheap), size correlates with AUM | Large blocks, often at mid, 30-90 DTE, strikes cluster at -5% to -10% OTM | BEARISH LEAN signal — when equity hedgers are active, institutions are nervous about downside. Elevated put buying from this cohort = smart money protecting gains. |
| **Earnings Trader** | Capture IV crush or directional move around earnings | Short straddles/strangles pre-earnings (IV sell), long straddles/strangles for surprise plays, single-leg directional | Concentrated in front-month, spikes in OI 1-2 weeks before earnings, collapses after | V/OI explodes on earnings week, IV skew shifts, put/call ratio distorts | NOISE for NQ macro bias — earnings flow in AAPL/MSFT/NVDA creates QQQ distortion. Identify and filter during mega-cap earnings weeks. See Section 14. |

**Operational Rule**: Before reading any flow print, ask: which player type is this? Pension fund puts = ignore. Macro sweep = act. Vol seller = note IV context. The tape looks the same; the inference is completely different.

---

## 2. Sweep Mechanics Deep Dive

### What a Sweep Actually Is

A sweep is an aggressive market order that crosses multiple exchanges simultaneously to fill a large position immediately, accepting price impact in exchange for speed. The mechanics:

1. Trader submits a large market order (or series of limit orders at ask)
2. Smart order router (SOR) fragments the order across all exchanges with available liquidity
3. Fills arrive from CBOE, ISE, PHLX, AMEX, BOX, MIAX, etc. within milliseconds
4. The tape shows multiple prints at the same strike/expiry in rapid succession, each from a different exchange

The key insight: **urgency equals conviction**. A trader willing to pay the ask across 6 exchanges and accept slippage is not hedging mechanically. They have information or a thesis they need to express NOW.

### Institutional Sweep Characteristics

A sweep qualifies as institutional when it meets ALL of the following:

| Criterion | Threshold | Why It Matters |
|-----------|-----------|----------------|
| Contract size | > 500 contracts | Below 500, retail traders can aggregate to this size |
| Total premium | > $100K | Filters out cheap lottery tickets |
| Exchange count | 2-6 exchanges | Single-exchange = not a true sweep |
| Execution time | < 500ms total | Confirms SOR routing, not manual entry |
| Side consistency | All at ask (calls) or all at bid (puts) | Mixed side = spread, not directional |
| Moneyness | ATM to 5% OTM | Far OTM sweeps are tail hedges, not directional |
| DTE | 7-60 days | < 7 DTE is 0DTE mechanics; > 60 DTE is structural positioning |

### Predictive Value by Premium Tier

This is where the quantitative edge lives. Pan & Poteshman (2006) established that options order flow predicts stock returns. Ge Lin Pearson (2016) extended this to index options with the following directional accuracy over a 5-day forward window:

| Premium Tier | 5-Day Directional Accuracy | Notes |
|--------------|---------------------------|-------|
| > $500K single sweep | 62% | Highest conviction tier |
| $250K-$500K | 58% | High conviction |
| $100K-$250K | 54% | Meaningful signal |
| $50K-$100K | 51% | Marginal edge |
| < $50K | ~50% | Noise |

**62% directional accuracy over 5 days is enormous** in a market where 51% is considered an edge. A $500K+ sweep is not a trade trigger by itself, but it's the strongest single-print signal available from public data.

### Why Sweeps Fail

Sweeps fail to predict direction when:
- The sweep is a HEDGE against an existing position (not new directional exposure)
- The sweep is part of a SPREAD (one leg visible, other leg dark or futures)
- The sweep is CLOSING an existing position (V/OI < 0.5, OI drops next day)
- The sweep is EARNINGS-related (IV play, not directional)

This is why V/OI ratio and OI change analysis (Section 3) are mandatory sweep filters.

---

## 3. Opening vs Closing Trade Detection

### The Core Problem

A 1,000-contract sweep at the ask on QQQ calls looks bullish. But if it's closing a short call position, it's actually bearish (the trader is buying back short calls because they think the market is going up and they want to remove the cap). Reading direction from raw flow without opening/closing context is a systematic error.

### V/OI Ratio Method

Volume-to-Open-Interest ratio is the primary opening/closing detector:

| V/OI Ratio | Interpretation | Confidence |
|------------|----------------|------------|
| > 2.0 | Almost certainly new positioning | High |
| 1.0-2.0 | Likely new positioning | Medium |
| 0.5-1.0 | Mixed — some opening, some closing | Low |
| < 0.5 | Likely closing existing position | Medium |
| < 0.1 | Almost certainly closing | High |

**Critical nuance**: V/OI must be computed at the specific strike/expiry level, not aggregated. A strike with 50K OI and 10K volume (V/OI=0.2) is very different from a strike with 2K OI and 10K volume (V/OI=5.0). The second is a new institutional position being built.

### OI Change Analysis (Next-Day Confirmation)

V/OI is real-time but probabilistic. OI change the next morning is the confirmation:

- OI increases → opening trade confirmed (new contracts created)
- OI flat → offsetting trades (one opened, one closed)
- OI decreases → closing trade confirmed (contracts destroyed)

For NQ trading, this is a next-day confirmation signal, not a real-time one. Use it to validate or invalidate the previous day's sweep interpretation.

### Roll Detection

A roll is a simultaneous close of near-term expiry + open of next expiry at the same strike (or adjusted strike). Rolls appear as:

- Two prints in rapid succession: one at bid (closing), one at ask (opening)
- Same strike, different expiry
- Similar contract count
- Often executed as a spread order (shows as a single complex print)

**Why rolls matter**: A roll is NOT new directional conviction. It's position maintenance. A pension fund rolling its quarterly put hedge from June to September is not a bearish signal. Filter rolls out of your directional flow analysis.

Roll identification heuristics:
1. Near-simultaneous prints on same strike, adjacent expiries
2. One print at bid, one at ask (or both at mid for spread execution)
3. OI in near-term expiry drops; OI in next expiry rises by similar amount
4. Total premium roughly equal (adjusted for time value difference)

---

## 4. Dark Pool Options Mechanics

### Why Institutions Use Dark Pools

Dark pool options execution serves three purposes:

1. **Size concealment**: A $50M options position executed on-exchange moves the market against you. Dark pool execution at midpoint avoids this.
2. **Front-running prevention**: HFT firms read the lit exchange tape and trade ahead of large orders. Dark pools prevent this.
3. **Midpoint execution**: Dark pools execute at the midpoint of the bid/ask spread, saving 0.5-2% on large positions.

The cost: dark pool prints are reported with a delay (up to 90 seconds) and with less granular exchange attribution. This is why dark pool flow is a CONFIRMATION signal, not a real-time trigger.

### Identifying Dark Pool Prints

Dark pool options prints have distinct characteristics on the tape:

| Characteristic | Dark Pool | Lit Exchange |
|----------------|-----------|--------------|
| Exchange code | "D" (FINRA TRF) or "X" (various dark venues) | CBOE, ISE, PHLX, AMEX, etc. |
| Execution price | At or near midpoint | At bid or ask |
| Reporting delay | 30-90 seconds | Near-real-time |
| Size | Typically > 1,000 contracts | Any size |
| Bid/ask side | Neither (midpoint) | Clearly at bid or ask |
| Urgency | Low (willing to wait for midpoint) | High (paying ask) |

Unusual Whales and similar services flag dark pool prints with exchange attribution. The "D" exchange code on a large print is the primary identifier.

### Volume Estimates and Directional Accuracy

CBOE data and academic research (Hu 2014) establish:

- Dark pool options volume: 15-30% of total institutional options flow
- Dark pool prints are more informative than lit exchange flow because they represent deliberate, size-insensitive positioning
- Dark pool + lit exchange alignment: 65-70% directional accuracy over 5 days
- Dark pool alone: 60-65% directional accuracy
- Lit exchange alone: 54-58% directional accuracy

The alignment signal is the key: when dark pool flow and lit exchange sweeps point the same direction, conviction is maximum. When they diverge, trust the dark pool (it's the more deliberate, less reactive signal).

### Dark Pool Integration for NQ Bias

Operational rules:
1. Dark pool call buying + lit exchange call sweeps → MAXIMUM BULLISH conviction
2. Dark pool put buying + lit exchange put sweeps → MAXIMUM BEARISH conviction
3. Dark pool buying + lit exchange selling → ACCUMULATION pattern (stealth bullish)
4. Dark pool selling + lit exchange buying → DISTRIBUTION pattern (stealth bearish, highest priority warning)
5. Dark pool quiet + lit exchange active → Treat lit exchange flow at 70% weight

The distribution pattern (dark bearish + lit bullish) is the most dangerous setup for longs. Institutions are selling into retail buying. This is the setup that precedes sharp reversals.

---

## 5. Premium-Based Flow Analysis

### Dollar Weight Beats Contract Count

This is the most common retail error in flow reading: counting contracts instead of dollars. A 10,000-contract print on $0.05 OTM options expiring tomorrow is $50,000 total premium. A 200-contract print on $25 ATM options is $500,000 total premium. The second print is 10x more informative.

**Why premium matters more than contracts**:
- Premium represents actual capital at risk
- Institutional traders size by dollar risk, not contract count
- High-contract/low-premium prints are often retail lottery tickets or vol sellers closing positions
- Low-contract/high-premium prints are institutional directional bets

### Institutional Premium Thresholds

| Tier | Premium | Classification | Action |
|------|---------|----------------|--------|
| Noise | < $50K | Retail or small institutional | Ignore for NQ bias |
| Meaningful | $50K-$100K | Small institutional or large retail | Note, don't act alone |
| High Conviction | $100K-$250K | Institutional, directional | Include in flow score |
| Mega | $250K-$500K | Large institutional, high conviction | Strong signal, weight heavily |
| Maximum | > $500K | Tier-1 institutional, maximum conviction | Highest weight, near-certain directional intent |

### Premium Concentration Analysis

Beyond single-print thresholds, look at premium concentration by strike:

- If 60%+ of net call premium is concentrated in 1-2 strikes → institutional targeting a specific level
- Distributed premium across many strikes → hedging or vol play, not directional
- Premium concentration at round numbers (QQQ 480, 490, 500) → institutional targeting GEX walls

This concentration pattern is how you identify which specific level institutions are positioning around. When $2M in call premium concentrates at QQQ 490 calls, that strike is the target. Map it to NQ equivalent and watch for GEX wall formation.

---

## 6. Net Delta-Adjusted Volume (NDAV)

### The Formula

Raw put/call volume is misleading because a deep ITM call has 10x the directional exposure of a far OTM call. Delta-weighting corrects for this.

```
NDAV = Σ(Call_Volume_i × Call_Delta_i) - Σ(Put_Volume_i × Put_Delta_i)
```

Where the sum is over all strikes and expiries in the measurement window.

**Interpretation**:
- NDAV > 0 → Net bullish delta exposure being added to the market
- NDAV < 0 → Net bearish delta exposure being added
- |NDAV| magnitude → Strength of directional positioning

### Why Delta-Weighting Matters

Example: Two flow scenarios, same contract count.

**Scenario A**: 10,000 QQQ call contracts at 0.30 delta
- Raw call volume: 10,000
- Delta-adjusted: 10,000 × 0.30 = 3,000 delta units

**Scenario B**: 5,000 QQQ call contracts at 0.70 delta
- Raw call volume: 5,000
- Delta-adjusted: 5,000 × 0.70 = 3,500 delta units

Scenario B has LESS volume but MORE directional exposure. A raw volume analysis would call Scenario A more bullish. Delta-adjusted analysis correctly identifies Scenario B as more bullish.

### NDAV for NQ Bias

Compute NDAV on QQQ flow (NQ proxy) over rolling windows:

| Window | Use |
|--------|-----|
| 30-minute NDAV | Intraday momentum, 0DTE positioning |
| 4-hour NDAV | Session bias, swing positioning |
| Daily NDAV | Multi-day trend, institutional accumulation |

NDAV trend (accelerating positive) is more informative than NDAV level. An NDAV that was -500 yesterday and is +200 today represents a 700-unit swing toward bullish — that's a regime shift signal.

---

## 7. Put/Call Ratio Context

### The Academic Foundation

Pan & Poteshman (2006) is the foundational paper. Key finding: the put/call ratio of INDIVIDUAL STOCK options predicts next-day stock returns with 40bps/day edge. This is one of the largest documented anomalies in options microstructure research.

**Critical distinction that most traders miss**:

| PC Ratio Type | Predictive Power | Why |
|---------------|-----------------|-----|
| Individual stock PC ratio | HIGH (40bps/day) | Informed traders use single-stock options for directional bets |
| SPX/SPY PC ratio | LOW (near zero) | Dominated by institutional hedging, not directional bets |
| QQQ PC ratio | INTERMEDIATE | Mix of directional and hedging; useful but noisy |
| NDX PC ratio | INTERMEDIATE | Similar to QQQ, slightly less liquid |

### Why Index PC Ratio Fails

The SPX put/call ratio is the most-watched options metric in retail trading. It's also the least predictive for directional bias. The reason: SPX options are dominated by pension funds, insurance companies, and portfolio managers buying puts for PROTECTION, not because they're bearish. This hedging demand is systematic and non-informational.

When the SPX PC ratio spikes, it usually means portfolio managers are buying protection after a rally (when puts are cheap), not that they expect a crash.

### QQQ PC Ratio for NQ

QQQ sits between SPX and individual stocks. It has:
- More directional trading than SPX (tech-focused, more speculative)
- More hedging than individual stocks (used as portfolio hedge for tech exposure)

For NQ bias, use QQQ PC ratio with these adjustments:

1. **Separate by DTE**: Short-dated QQQ PC ratio (< 14 DTE) is more directional. Long-dated (> 30 DTE) is more hedging.
2. **Separate by moneyness**: ATM to 5% OTM PC ratio is directional. > 10% OTM is tail hedging.
3. **Use net premium PC ratio, not contract count**: Dollar-weighted PC ratio filters out lottery tickets.

**Operational threshold**: QQQ net premium PC ratio (short-dated, near-ATM) > 1.5 → bearish lean. < 0.7 → bullish lean. 0.7-1.5 → neutral.

---

## 8. Flow Momentum

### Definition

Flow momentum is the rate of change of net premium over time. It's more informative than the level of net premium because it captures whether institutional conviction is building or fading.

```
Flow_Momentum(t, window) = Net_Premium(t) - Net_Premium(t - window)
```

### Time Windows and Interpretation

| Window | Signal Type | Interpretation |
|--------|-------------|----------------|
| 1-hour momentum | Intraday conviction | Accelerating = thesis building; decelerating = thesis fading |
| 4-hour momentum | Session conviction | Positive and accelerating = institutional accumulation in progress |
| Daily momentum | Multi-day trend | Sustained positive momentum = structural bullish positioning |

### Momentum States

**Accelerating flow**: Net premium increasing at an increasing rate. This is the highest-conviction state. Institutions are adding to a position, not just maintaining it. In NQ terms: if QQQ call net premium was +$5M at 10 AM, +$12M at 12 PM, +$22M at 2 PM, that's accelerating bullish flow. The acceleration is the signal.

**Decelerating flow**: Net premium still positive but growing more slowly. Conviction is fading. The thesis may be playing out (profit-taking) or being questioned. Reduce position size or tighten stops.

**Flow reversal**: Net premium changes sign. This is a thesis invalidation signal. If you're long NQ based on bullish flow and net premium flips negative, the institutional thesis has changed. Exit or hedge.

**Dead flow**: Net premium < $5M absolute, no sweeps, no blocks. No institutional activity. This is the DEAD flow state from the flow-interpretation framework. No trade.

---

## 9. V/OI Ratio by Strike

### Why Strike-Level V/OI Matters

Aggregate V/OI across all strikes is noise. Strike-level V/OI identifies exactly WHERE institutions are positioning. This is how you find the specific levels that matter.

### The Signal Threshold

| V/OI at Strike | Interpretation |
|----------------|----------------|
| > 5.0 | Extreme new positioning — institutional targeting this strike |
| 2.0-5.0 | Strong new positioning — high conviction |
| 1.5-2.0 | New positioning — meaningful signal |
| 1.0-1.5 | Likely new, some closing mixed in |
| 0.5-1.0 | Mixed — inconclusive |
| < 0.5 | Primarily closing — not a new signal |

### The Sweep + V/OI Combination

The highest-conviction flow signal in the system is a sweep where V/OI > 1.5 at the swept strike. This combination means:
1. The trade was executed with urgency (sweep)
2. The position is new, not a close (V/OI > 1.5)
3. The size is meaningful relative to existing OI

**Example**: QQQ 490 calls. OI = 8,000 contracts. A 15,000-contract sweep arrives (V/OI = 1.875). This is a new institutional position being built at the 490 strike with urgency. Map 490 QQQ to NQ equivalent (~21,350 NQ). That strike is now a target level.

**Counter-example**: QQQ 490 calls. OI = 80,000 contracts. A 15,000-contract sweep arrives (V/OI = 0.19). This is almost certainly closing an existing position. The directional inference is opposite — someone is reducing their 490 call exposure.

---

## 10. High-Conviction Setup Checklist

### The 5 Golden Criteria

A flow print qualifies as a high-conviction institutional signal when it meets ALL five:

1. **Golden sweep**: Multi-exchange execution (2+ exchanges), all at ask (calls) or bid (puts), < 500ms total
2. **V/OI > 5.0**: New positioning, not closing. Strike-level V/OI, not aggregate.
3. **Premium > $250K**: Institutional size threshold. Dollar-weighted, not contract count.
4. **OTM (not deep ITM)**: ATM to 5% OTM. Deep ITM = delta replacement, not directional bet. Far OTM = lottery ticket.
5. **21-45 DTE**: Long enough to be right, short enough to have urgency. < 7 DTE is 0DTE mechanics. > 60 DTE is structural positioning (lower urgency signal).

### The 3 Context Filters

Even when all 5 criteria are met, apply these filters:

1. **Not earnings week**: If AAPL, MSFT, NVDA, AMZN, META, or GOOGL reports within 5 trading days, QQQ flow is contaminated by earnings positioning. The sweep may be earnings-related, not macro-directional.

2. **Not OPEX week**: The week of monthly options expiration creates mechanical flow from rolls, delta hedging, and position management. Sweeps during OPEX week have lower directional signal because they may be roll-driven.

3. **Macro clear**: No FOMC, CPI, NFP, or major macro event within 30 minutes. Pre-event flow is often hedging, not directional. Post-event flow (first 30 minutes) is often reactive, not predictive.

### Scoring

When all 5 criteria + all 3 context filters are met: **MAXIMUM CONVICTION** signal. Weight at 100% in the flow score.

When 4/5 criteria + all 3 context filters: **HIGH CONVICTION**. Weight at 75%.

When 3/5 criteria: **MODERATE**. Weight at 40%. Do not trade on this alone.

---

## 11. 0DTE Institutional vs Retail Split

### CBOE 2025 Data

The CBOE 2025 0DTE Options Report provides the clearest picture of who is trading 0DTE and when. This data is critical for NQ intraday trading because 0DTE GEX structure dominates intraday price action.

**Volume split**:
- Retail traders: 50-60% of 0DTE volume by contract count
- Institutional traders: 40-50% of 0DTE volume by contract count
- By premium: institutional share rises to 55-65% (larger average trade size)

### Retail 0DTE Behavior

| Characteristic | Data |
|----------------|------|
| Trading pattern | U-shaped: active at open (9:30-10:30 AM), quiet midday, active at close (3:00-4:00 PM) |
| Average max loss per trade | < $2,000 |
| Position holding | Active closing — 70%+ of retail 0DTE positions are closed before expiration |
| Strike preference | ATM to 2% OTM, round strikes |
| Directional bias | Slight call bias (retail is structurally bullish) |

### Institutional 0DTE Behavior

| Characteristic | Data |
|----------------|------|
| Trading pattern | Front-loaded: 18% of institutional 0DTE volume in first 30 minutes (9:30-10:00 AM) |
| Average max loss per trade | > $20,000 |
| Position holding | 65-75% of institutional 0DTE positions held to expiration |
| Strike preference | ATM to 5% OTM, specific GEX-relevant strikes |
| Directional bias | More balanced, often spread-based |

### The Critical Implication for NQ Trading

**After 10:00 AM, 0DTE GEX structure is mostly set.**

Institutional 0DTE positioning is front-loaded. By 10 AM, the major institutional 0DTE positions are in place. The GEX walls derived from 0DTE options are relatively stable from 10 AM onward (barring large market moves that trigger new hedging).

This means:
- Pre-10 AM: 0DTE GEX levels are forming, less reliable
- 10 AM-2 PM: 0DTE GEX levels are most stable and most tradeable
- 2 PM-4 PM: Retail closing activity + charm decay creates mechanical flows (see Section 13 on charm)
- Last 30 minutes: Pin risk dominates, 0DTE GEX levels become gravitational

**Operational rule**: Don't trade against 0DTE GEX walls established before 10 AM. They represent institutional positioning that will be defended mechanically through delta hedging.

---

## 12. Monthly OPEX Roll Behavior

### The Roll Window

Institutional options positions don't expire — they roll. The typical roll window for monthly OPEX is **1-2 weeks before expiration** (roughly the 3rd Friday of the month). This creates predictable flow patterns:

**Week 2 before OPEX (T-10 to T-7 trading days)**:
- First roll activity appears in flow tape
- OI in expiring month begins declining
- OI in next month begins building
- Net premium flow may appear bearish (closing calls) or bullish (closing puts) — this is roll noise, not directional

**Week 1 before OPEX (T-5 to T-1)**:
- Heavy roll activity
- GEX in expiring month decays rapidly
- New GEX structure forms in next month
- Gamma flip level may shift as OI migrates

### OI Shift Patterns

During the roll window, watch for:

1. **Strike migration**: Institutions often roll to the same strike (maintaining the hedge) or to a strike adjusted for the new expected move. If QQQ 490 puts roll to QQQ 485 puts, the institution is adjusting their hedge level downward.

2. **Term structure impact**: Rolling from near-term to next-month increases demand for next-month options, steepening the term structure. This is a mechanical effect, not a directional signal.

3. **GEX concentration shift**: As OI migrates from expiring to next month, the GEX profile reshapes. The call wall and put wall for the new month may be at different strikes than the expiring month.

### Operational Rules for OPEX Week

- Reduce weight on flow signals during OPEX week (T-5 to T-1)
- Treat large prints as potential rolls until confirmed by OI change
- Watch for new GEX structure forming in next month — this is the new battlefield
- The gamma flip level for next month is the most important level to identify during OPEX week

---

## 13. Quarterly OPEX (Triple Witching)

### What Triple Witching Is

Triple witching occurs on the third Friday of March, June, September, and December. Three contract types expire simultaneously:
- Stock options
- Stock index futures (ES, NQ)
- Stock index options (SPX, NDX)

The quarterly OPEX is the largest institutional rebalancing event in the options calendar.

### NQ-Specific Dynamics

**GEX concentration**: In the weeks before quarterly OPEX, GEX concentrates at round strikes as institutions roll to the next quarter. NQ GEX can reach 3-5x normal levels at specific strikes. These strikes become extremely strong support/resistance.

**Rebalancing flows**: Index rebalancing (S&P 500, Nasdaq 100 quarterly rebalancing) coincides with quarterly OPEX. This creates massive futures flows that interact with options hedging flows.

**The opportunity window**: The 2-3 days before quarterly OPEX, as GEX concentration peaks, the market tends to pin to the highest-GEX strike. This is the strongest pin risk of the year. Fade moves away from the pin strike.

**Post-OPEX reset**: The Monday after quarterly OPEX, GEX resets to near-zero. The market loses its mechanical support/resistance structure. Volatility typically increases in the week after quarterly OPEX as the new GEX structure is being built.

### Quarterly OPEX Trading Rules

1. **Week before**: Identify the pin strike (highest GEX concentration). Fade moves away from it.
2. **OPEX day**: Expect pinning behavior. Avoid directional trades. Sell premium if you trade options.
3. **Week after**: Expect elevated volatility. GEX structure is weak. Reduce position size. Wait for new structure to form.

---

## 14. Mega-Cap Earnings Impact on NQ

### The QQQ Contamination Problem

The Nasdaq 100 (NQ) is heavily concentrated in mega-cap tech. The top 6 holdings (AAPL, MSFT, NVDA, AMZN, META, GOOGL) represent approximately 40-45% of QQQ by weight. When any of these report earnings, QQQ options flow is contaminated by earnings positioning.

**The contamination mechanism**:
1. Earnings traders buy straddles/strangles on the individual stock (AAPL, MSFT, etc.)
2. Market makers who sold those straddles hedge their delta exposure using QQQ options (cheaper, more liquid)
3. This creates QQQ options flow that looks directional but is actually earnings hedging
4. The flow appears in your scanner as a bullish or bearish signal — but it's noise

### Hedging Spillover Patterns

| Earnings Event | QQQ Impact | NQ Impact | Duration |
|----------------|------------|-----------|----------|
| AAPL earnings | High (7% QQQ weight) | Moderate | 2 days before, 1 day after |
| MSFT earnings | High (7% QQQ weight) | Moderate | 2 days before, 1 day after |
| NVDA earnings | Very High (5-6% QQQ weight, extreme IV) | High | 3 days before, 2 days after |
| AMZN earnings | Moderate (4% QQQ weight) | Low-Moderate | 1 day before, 1 day after |
| META earnings | Moderate (3% QQQ weight) | Low-Moderate | 1 day before, 1 day after |
| GOOGL earnings | Moderate (4% QQQ weight) | Low-Moderate | 1 day before, 1 day after |

### Operational Rules for Earnings Weeks

1. **Identify the earnings calendar**: Check which mega-caps report in the next 5 trading days.
2. **Reduce flow signal weight**: During mega-cap earnings weeks, reduce QQQ flow signal weight by 30-50%.
3. **Filter by DTE**: Earnings-related flow concentrates in front-month (< 14 DTE). Longer-dated flow (> 30 DTE) is less contaminated.
4. **Watch for post-earnings reset**: After the earnings print, the hedging flow unwinds rapidly. This creates a mechanical flow reversal that can look like a directional signal but is actually delta unwind.
5. **NVDA is special**: NVDA earnings create the largest QQQ/NQ distortion of any single stock. Treat the 3 days before NVDA earnings as a no-trade zone for flow-based NQ signals.

---

## 15. Flow Scoring Framework

### Architecture

The flow scoring framework converts raw flow data into a single -100 to +100 score. This is the quantitative output of the Options Bias Engine's Step 3 (Flow Read). It feeds directly into the Step 4 cross-validation matrix.

The framework is inspired by Flowseeker-style scoring but adapted for NQ/QQQ institutional flow.

### Component Scores

Each component scores -100 to +100. Final score is weighted sum.

| Component | Weight | Scoring Logic |
|-----------|--------|---------------|
| **Spread position** | 15% | Debit call spread = +50 to +80. Debit put spread = -50 to -80. Credit put spread = +30 to +60 (bullish but less conviction). Credit call spread = -30 to -60. |
| **Sweep detection** | 25% | Multi-exchange sweep at ask = +100. Multi-exchange sweep at bid = -100. Single-exchange = ±60. No sweep = 0. |
| **Moneyness** | 10% | ATM to 2% OTM = ±100 (maximum directional). 2-5% OTM = ±70. 5-10% OTM = ±40. > 10% OTM = ±20 (tail hedge, low directional signal). |
| **DTE** | 10% | 21-45 DTE = ±100 (sweet spot). 7-21 DTE = ±80. 45-90 DTE = ±60. < 7 DTE = ±40 (0DTE mechanics). > 90 DTE = ±30 (structural, low urgency). |
| **Size/OI (V/OI)** | 20% | V/OI > 5.0 = ±100. V/OI 2.0-5.0 = ±80. V/OI 1.5-2.0 = ±60. V/OI 1.0-1.5 = ±40. V/OI < 1.0 = ±10. |
| **IV confirmation** | 10% | IV expanding on call sweep = +20 bonus. IV expanding on put sweep = -20 bonus. IV contracting = -20 penalty (suggests closing). |
| **Premium tier** | 10% | > $500K = ±100. $250K-$500K = ±80. $100K-$250K = ±60. $50K-$100K = ±40. < $50K = ±10. |

### Aggregation

For a single print:
```
Flow_Score = Σ(Component_Score_i × Weight_i)
```

For the session flow score (rolling window):
```
Session_Flow_Score = Σ(Print_Score_i × Premium_Weight_i) / Σ(Premium_Weight_i)
```

Where `Premium_Weight_i` is the dollar premium of each print, normalized. This ensures a $500K sweep dominates a $50K print by 10x in the session score.

### Score Interpretation

| Score Range | State | Action |
|-------------|-------|--------|
| +70 to +100 | AGGRESSIVE BULLISH | Full weight in bias engine |
| +40 to +70 | BULLISH | Standard weight |
| +20 to +40 | MILD BULLISH | Half weight |
| -20 to +20 | NEUTRAL / DEAD | No flow signal |
| -20 to -40 | MILD BEARISH | Half weight |
| -40 to -70 | BEARISH | Standard weight |
| -70 to -100 | AGGRESSIVE BEARISH | Full weight in bias engine |

### Decay Function

Flow signals decay over time. A sweep from 3 hours ago is less informative than a sweep from 10 minutes ago.

```
Decayed_Score(t) = Score × exp(-λ × hours_elapsed)
```

Where λ = 0.3 for intraday signals (half-life ≈ 2.3 hours). This means a +80 sweep from 2 hours ago contributes +80 × exp(-0.6) ≈ +44 to the current session score.

For multi-day signals (large sweeps > $500K, 21+ DTE), use λ = 0.05 (half-life ≈ 14 hours). These signals persist across sessions.

---

## Cross-Reference Map

| Section | Connects To |
|---------|-------------|
| 7-Player Taxonomy | `step3-flow/flow-interpretation.md` (six flow states) |
| Sweep Mechanics | `step3-flow/sweep-analysis.md` |
| Opening vs Closing | `step3-flow/opening-vs-closing.md` |
| Dark Pool | `step3-flow/dark-pool-reading.md` |
| Flow Scoring | `step4-cross-validation/conviction-matrix.md` |
| 0DTE Split | `domains/zero-dte-mechanics.md` |
| OPEX Cycles | `domains/opex-cycles.md` |
| Earnings Impact | `domains/nq-options-proxy.md` |
| V/OI + Sweeps | `step5-setups/sweep-cascade.md` |
| Distribution Pattern | `step4-cross-validation/distribution-accumulation.md` |

---

*Academic references: Pan & Poteshman (2006) "The Information in Option Volume for Future Stock Prices", Journal of Financial Studies. Hu (2014) "Does Option Trading Convey Stock Price Information?", Journal of Financial Economics. Ge, Lin & Pearson (2016) "Why Does the Option to Stock Volume Ratio Predict Stock Returns?", Journal of Financial Economics. CBOE (2025) "0DTE Options: A Comprehensive Market Analysis".*
