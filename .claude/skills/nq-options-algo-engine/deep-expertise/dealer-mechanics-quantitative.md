# Dealer Mechanics — Quantitative Foundation

**Prerequisite**: Read `options-bias-engine/domains/dealer-hedging-mechanics.md` first. That file covers the conceptual framework. This file goes deeper: formulas, worked NQ examples, edge cases, and honest limitations.

---

## 1. The Hedge Obligation Formula

Every option sold by a dealer creates a delta obligation. The dealer must hold a position in the underlying that offsets the option's directional exposure.

```
Shares_to_hedge = Delta × Contracts × Multiplier
```

For equity options, multiplier = 100 (each contract covers 100 shares).

**NQ worked example:**

NQ is trading at 20,000. A dealer sells 500 call contracts on QQQ (proxy for NQ) with delta = 0.45.

```
Shares_to_hedge = 0.45 × 500 × 100 = 22,500 QQQ shares
```

At QQQ ~$490, that's $11.025M in QQQ the dealer must buy to be delta-neutral. If NQ rallies 100 points (QQQ +~$2.40), delta drifts to 0.52:

```
New hedge = 0.52 × 500 × 100 = 26,000 shares
Delta drift = 26,000 - 22,500 = 3,500 additional shares to buy
```

That's $1.715M in forced buying from a single 100-point NQ move. Scale this across the full open interest and you understand why GEX walls hold.

---

## 2. Gamma Rebalancing Formula

Gamma tells you how much delta changes per 1-point move in the underlying. The rebalancing obligation from a price move is:

```
Shares_to_trade = Gamma × Spot × 0.01 × Price_move_in_pct
```

The `Spot × 0.01` term converts gamma (which is per 1% move) into dollar terms.

**NQ worked example — $20M forced hedging from a 50-point move:**

Assume the aggregate gamma across all NQ-proxy options at a given strike is 0.002 per share, with 10 million shares of open interest equivalent.

```
Aggregate gamma = 0.002 × 10,000,000 = 20,000 delta units per 1% move
NQ spot = 20,000
1% of NQ = 200 points
50-point move = 0.25% of spot

Shares_to_trade = 20,000 × 0.25 = 5,000 shares
At QQQ $490 = $2.45M per dealer
```

Across 8-10 major dealers, that's $20-25M in forced hedging from a single 50-point NQ move. This is the mechanical bid/ask that makes GEX walls self-reinforcing. The wall doesn't hold because traders respect it. It holds because dealers are mechanically forced to trade against every approach.

---

## 3. GEX Per Strike Formula

The gamma exposure at a single strike k is:

```
GEX_k = Gamma_k × OI_k × Multiplier × Spot × 0.01
```

Where:
- `Gamma_k` = option gamma at strike k (per share, per 1% move)
- `OI_k` = open interest in contracts at strike k
- `Multiplier` = 100 for equity options
- `Spot × 0.01` = dollar value of a 1% spot move

**Full QQQ worked example — $200K/pt hedging obligation:**

QQQ at $490. Call strike at $495, OI = 50,000 contracts, gamma = 0.008.

```
GEX_495 = 0.008 × 50,000 × 100 × 490 × 0.01
        = 0.008 × 50,000 × 100 × 4.90
        = 0.008 × 24,500,000
        = $196,000 per 1% move
```

That's approximately $200K in forced dealer hedging per 1% QQQ move at that strike. A 1% QQQ move is roughly 50 NQ points. So this single strike generates ~$4,000 in forced hedging per NQ point.

Aggregate across all strikes and you get the total GEX profile. FlashAlpha sums this across the full chain and reports it as the GEX curve.

---

## 4. Sign Convention — Why Calls Stabilize and Puts Amplify

This is the most misunderstood part of GEX. The sign comes from the dealer's position, not the option's direction.

**Call OI (positive GEX — stabilizing):**

Retail and institutions buy calls. Dealers sell calls. A dealer short a call has negative delta (they're short the upside). To hedge, they buy the underlying. As price rises, delta increases, so they buy more. As price falls, delta decreases, so they sell. This is **counter-trend** behavior. The dealer is always trading against the move, providing liquidity and dampening volatility.

**Put OI (negative GEX — amplifying):**

Retail and institutions buy puts for protection. Dealers sell puts. A dealer short a put has positive delta (they're short the downside). To hedge, they sell the underlying. As price falls, delta increases in magnitude, so they sell more. As price rises, delta decreases, so they buy back. This is **pro-trend** behavior. The dealer amplifies every move.

The sign convention in the GEX formula:

```
GEX_calls = +Gamma × OI × 100 × S × 0.01   (stabilizing)
GEX_puts  = -Gamma × OI × 100 × S × 0.01   (amplifying)
Total_GEX = GEX_calls + GEX_puts
```

When total GEX > 0, calls dominate and dealers stabilize. When total GEX < 0, puts dominate and dealers amplify. The zero crossing is the gamma flip.

---

## 5. Gamma Flip (Zero Gamma Level) Mechanics

The gamma flip is the price level where total GEX = 0. Above it, positive gamma dominates. Below it, negative gamma dominates.

**What ACTUALLY changes in dealer behavior at the flip:**

| Condition | Dealer Behavior | Market Character |
|-----------|----------------|-----------------|
| Price well above flip | Buy dips, sell rips aggressively | Tight range, mean-reversion |
| Price approaching flip from above | Hedging activity decreases | Range widens, vol picks up |
| Price at flip | Dealers near-neutral, minimal forced flow | Unstable, can break either way |
| Price just below flip | Dealers begin amplifying | Momentum builds, stops cascade |
| Price well below flip | Sell rallies, buy dips (pro-trend) | Trending, high vol, wide ranges |

The flip isn't a wall. It's a regime boundary. Price doesn't bounce off it. It passes through it and the market's character changes. This is why the gamma flip cross is a setup (see `step5-setups/gamma-flip-cross.md`) rather than a fade.

**Practical identification:**

FlashAlpha reports the gamma flip directly. Cross-check by looking at the GEX profile chart: the flip is where the curve crosses zero. In practice, treat a ±50-point band around the reported flip as the transition zone. Regime doesn't flip instantly.

---

## 6. Negative Gamma Amplification Loop

This is the mechanism behind every major NQ selloff. Understanding it quantitatively lets you distinguish a normal pullback from a cascade.

**Step-by-step cascade:**

```
Step 1: Price falls below gamma flip
        → Dealers now net short puts (negative GEX)
        → Dealer delta exposure increases as price falls

Step 2: Dealers must sell to rebalance
        → Selling pressure adds to the decline
        → Price falls further

Step 3: More strikes come into play
        → OTM puts become ATM, gamma spikes
        → Rebalancing obligation grows non-linearly

Step 4: Vol spikes (VIX rises)
        → Higher vol increases gamma across all strikes
        → Rebalancing obligation grows again

Step 5: VIX dealers hedge their own exposure
        → VIX call buyers force VIX dealers to sell equity futures
        → Additional selling pressure (see Section 11)

Step 6: Stops trigger
        → Retail and institutional stops add market sell orders
        → Dealers absorb these but at worse prices, increasing their short delta

Step 7: Exhaustion mechanism
        → Deep ITM puts have delta approaching -1
        → Gamma approaches 0 for deep ITM options
        → Forced selling from those strikes stops
        → Cascade loses fuel
        → Bounce
```

**Quantitative exhaustion model:**

The cascade self-limits because delta is bounded at [-1, 0] for puts. Once a put is deep ITM, gamma collapses and the rebalancing obligation per point falls toward zero. The exhaustion point is approximately when the weighted average delta of the put chain reaches -0.85 to -0.90. At that point, the mechanical selling from gamma rebalancing is largely complete.

This is why NQ selloffs often have a sharp initial leg (gamma amplification) followed by a slower grind or bounce (exhaustion). The first 150-200 points of a cascade are the most dangerous. After that, the mechanical fuel is largely spent.

---

## 7. DEX vs GEX — First-Order vs Second-Order

GEX is a second-order metric (gamma = second derivative of option price with respect to spot). DEX is a first-order metric (delta = first derivative).

```
DEX = Sum(Delta_k × OI_k × 100 × S)   for all strikes k
GEX = Sum(Gamma_k × OI_k × 100 × S × 0.01)   for all strikes k
```

DEX tells you the current directional lean of dealer hedges. GEX tells you how much that lean will change per unit of price movement.

**The 4-cell DEX × GEX matrix:**

| | GEX Positive (stabilizing) | GEX Negative (amplifying) |
|---|---|---|
| **DEX Positive** (dealers net long) | Dealers long + stabilizing. Bullish bias, tight range. Dips get bought mechanically. | Dealers long + amplifying. Bullish momentum. Rallies accelerate, but so do reversals. |
| **DEX Negative** (dealers net short) | Dealers short + stabilizing. Bearish bias, tight range. Rallies get sold mechanically. | Dealers short + amplifying. Bearish momentum. Selloffs accelerate. Most dangerous regime. |

**Trading implications:**

- DEX+/GEX+ (top-left): Best regime for mean-reversion strategies. Fade extremes.
- DEX+/GEX- (top-right): Trend-following works but reversals are sharp. Use tight stops.
- DEX-/GEX+ (bottom-left): Short bias but contained. Good for selling rallies with defined risk.
- DEX-/GEX- (bottom-right): Avoid longs entirely. Cascade risk is highest here.

FlashAlpha reports both DEX and GEX. Check both before every session.

---

## 8. Inventory Rebalancing Triggers

Dealers don't rebalance continuously. Transaction costs make that prohibitive. They rebalance when their delta drift exceeds a threshold.

**Four trigger types:**

**Delta threshold (most common):**
```
Trigger when: |Current_delta - Target_delta| / Notional > 5-10%
```
A dealer with $100M notional exposure rebalances when delta drifts by $5-10M. For NQ, at $20/point, that's 250-500 points of equivalent exposure drift.

**Gamma threshold:**
```
Trigger when: Gamma × Expected_daily_move > Delta_threshold
```
High-gamma positions (near expiry, near ATM) trigger more frequent rebalancing because small moves create large delta drift.

**Time-based:**
End of day, end of week, and especially end of month/quarter. Dealers clean up books before reporting periods. This creates predictable flow patterns around 3:45-4:00 PM ET and on the last trading day of each month.

**Volatility-based:**
When realized vol spikes above implied vol, dealers' gamma hedges are being tested harder than expected. They tighten thresholds and rebalance more aggressively.

**What to look for in the order book:**

Rebalancing shows up as large, rapid, one-sided order flow that doesn't correlate with news. It's mechanical, not informational. Characteristics:
- Consistent size (not random retail noise)
- Appears at round numbers or known GEX levels
- Doesn't chase price — it executes at the level and stops
- Often followed by a brief pause, then continuation of the original trend

---

## 9. Shares Per 1% Move

A quick formula for estimating the mechanical flow from a given GEX level:

```
Shares_per_1pct = Total_GEX / (Spot × 0.01)
```

**NQ example:**

FlashAlpha reports total GEX = $500M for QQQ. QQQ spot = $490.

```
Shares_per_1pct = $500,000,000 / ($490 × 0.01)
               = $500,000,000 / $4.90
               = 102,040,816 shares per 1% move
```

At QQQ $490, that's ~$50B in forced hedging flow per 1% QQQ move. A 1% QQQ move is roughly 50 NQ points. So each NQ point generates approximately $1B in mechanical flow when GEX is $500M.

This number tells you how "sticky" the current price level is. High GEX = high mechanical flow = harder to move price. Low GEX = thin mechanical support = easier to move price. This is why low-GEX environments (negative gamma, post-expiry) have wider daily ranges.

---

## 10. Cross-Asset Mechanics — When the Proxy Breaks

NQ options don't trade with enough liquidity for reliable GEX analysis. The standard approach is to use QQQ (ETF) and NDX (index) as proxies. Each has structural differences that matter.

**SPX vs SPY structural differences (reference for understanding the QQQ/NDX analog):**

SPX options are European-style (cash-settled, no early exercise). SPY options are American-style (physically settled, early exercise possible). European options have cleaner gamma profiles because there's no early exercise premium distorting delta. SPX also has the 0DTE market (Monday/Wednesday/Friday expirations) that SPY lacks.

**QQQ vs NDX:**

QQQ is American-style, physically settled. NDX is European-style, cash-settled. For GEX purposes, NDX is cleaner. But QQQ has far higher volume and open interest, making its GEX signal more statistically robust.

The QQQ-to-NQ conversion ratio is approximately:
```
NQ_points = QQQ_move_in_dollars × (NQ_spot / QQQ_price) × 10
```

At NQ 20,000 and QQQ $490:
```
Ratio = 20,000 / 490 × 10 ≈ 408 NQ points per $1 QQQ move
```

**When the proxy breaks down:**

1. **Sector rotation**: If tech is selling off while the broader market holds, QQQ/NDX GEX will show bearish pressure that doesn't translate to SPX-correlated instruments. NQ will follow QQQ, not SPX.

2. **Rate shock**: Rising rates hit growth/tech disproportionately. QQQ GEX will show amplified negative gamma during rate spikes that SPX GEX won't capture.

3. **Earnings season**: Major NQ components (AAPL, MSFT, NVDA, AMZN, META, GOOGL) have their own options chains. During earnings, single-stock gamma can overwhelm the index GEX signal. The proxy relationship weakens for 2-3 days around each major earnings event.

4. **ETF rebalancing**: QQQ rebalances quarterly. In the week before rebalancing, ETF arbitrage flow can distort the QQQ/NDX relationship.

**Practical rule**: Use QQQ GEX as primary signal. Cross-check with NDX GEX when they diverge by more than 20%. If they diverge, trust NDX (cleaner structure) but note that QQQ flow will dominate intraday mechanics.

---

## 11. VIX Volatility Feedback Loop

This is the mechanism that turns a normal selloff into a cascade. It's separate from the gamma amplification loop but compounds it.

**The loop:**

```
Step 1: Equity selloff begins
        → Investors buy VIX calls as portfolio insurance
        → VIX call dealers sell VIX calls (short vol)

Step 2: VIX rises
        → VIX call dealers are now short gamma on VIX
        → They must buy VIX futures to hedge (delta hedge)

Step 3: VIX futures buying pushes VIX higher
        → Higher VIX increases implied vol across all equity options
        → Higher IV increases gamma across all equity strikes

Step 4: Higher equity gamma increases dealer rebalancing obligations
        → More forced equity selling per point of decline
        → Equity selloff accelerates

Step 5: Accelerating equity selloff → more VIX buying
        → Loop repeats
```

**Quantitative signal:**

Watch VVIX (volatility of VIX). When VVIX spikes above 100-110, the VIX feedback loop is active. Normal VVIX is 80-95. A VVIX spike above 110 means VIX options are being bought aggressively, which means the feedback loop is engaged.

The loop breaks when:
- VIX reaches a level where put protection becomes too expensive (demand collapses)
- Equity prices reach a level where value buyers overwhelm mechanical sellers
- The Fed or other policy intervention changes the calculus

**NQ trading implication**: When VVIX > 110 and NQ is below the gamma flip, do not buy dips. The mechanical selling from both the gamma amplification loop and the VIX feedback loop is still active. Wait for VVIX to peak and begin declining before considering longs.

---

## 12. Charm Acceleration Formula

Charm (delta decay) is the rate at which delta changes with time. It's what drives the mechanical end-of-day and end-of-week flows.

The approximation:

```
Charm ≈ -Gamma × Spot × Vol / (2 × sqrt(T))
```

Where T is time to expiry in years.

**The acceleration effect:**

As T approaches zero, `sqrt(T)` approaches zero, and charm approaches infinity. This is why 0DTE options create explosive mechanical flows in the final hour.

Relative charm at different times to expiry (normalized to 1 day = 1.0):

```
1 day remaining:    charm multiplier = 1.0x
4 hours remaining:  charm multiplier = 2.5x
1 hour remaining:   charm multiplier = 5.0x
15 minutes:         charm multiplier = 20x
1 minute:           charm multiplier = 50x+
```

**NQ practical implication:**

A 0DTE call position that was delta-neutral at 9:30 AM will have drifted significantly by 3:00 PM purely from charm, even if NQ hasn't moved. Dealers holding large 0DTE positions must rebalance aggressively in the final 90 minutes. This creates the characteristic 3:00-3:30 PM directional push that often has nothing to do with news or order flow.

The direction of charm flow depends on whether dealers are net long or short 0DTE options. If dealers are net short 0DTE calls (common when retail is buying calls), charm causes their delta to decay toward zero, forcing them to sell the underlying into the close. This is the mechanical source of the "3 PM fade" pattern.

---

## 13. Pin Risk Score Formula

Pin risk quantifies the probability that price will be "pinned" to a specific strike at expiry. High pin risk means the market will gravitate toward that strike in the final hours.

```
Pin_Risk_Score = 0.30 × OI_concentration 
               + 0.25 × Magnet_proximity 
               + 0.25 × Time_remaining 
               + 0.20 × Gamma_magnitude
```

Each component is scored 0-100:

- **OI_concentration**: What percentage of total chain OI is at this strike? 100 = all OI at one strike (never happens). Practical range: 5-25% = 0-100 score.
- **Magnet_proximity**: How close is current price to the strike? 100 = price is exactly at strike. 0 = price is 2+ standard deviations away.
- **Time_remaining**: 100 = final 30 minutes. 0 = more than 2 days to expiry. Linear decay.
- **Gamma_magnitude**: Normalized gamma at the strike relative to the chain maximum. 100 = highest gamma strike.

**Interpretation table:**

| Score | Interpretation | Trading Action |
|-------|---------------|----------------|
| 0-30 | No pin risk | Ignore, trade normally |
| 30-55 | Mild gravitational pull | Note the level, don't fight it near expiry |
| 55-70 | Moderate pin risk | Expect price to oscillate around strike in final 2 hours |
| 70-85 | Strong pin | Fade moves away from strike in final 90 minutes |
| 85-100 | Extreme pin | Price will likely close within 5 points of strike |

**NQ example:**

NQ at 20,050. QQQ 490 strike has 18% of total chain OI. Current time is 3:15 PM on expiry Friday. QQQ at $490.20 (proximity score: 85). Gamma at 490 is the chain maximum.

```
OI_concentration: 18% → score 72
Magnet_proximity: $0.20 away → score 85
Time_remaining: 45 min to close → score 90
Gamma_magnitude: chain maximum → score 100

Pin_Risk_Score = 0.30×72 + 0.25×85 + 0.25×90 + 0.20×100
              = 21.6 + 21.25 + 22.5 + 20.0
              = 85.35
```

Extreme pin. NQ will likely close near 20,000 (QQQ $490 equivalent). Fade any move away from 20,000 in the final 45 minutes.

---

## 14. Post-2022 Structural Shift — The 0DTE Revolution

The options market structure changed fundamentally in 2022-2023. Understanding the old regime (pre-2022) is useful for reading academic papers. Trading the current regime requires understanding what changed.

**The shift:**

Before 2022, SPX options were primarily weekly (Friday expiry). GEX was relatively stable through the week, resetting on Friday. Pinning was the dominant expiry effect.

After 2022, CBOE introduced Monday and Wednesday SPX expirations. By 2024, 0DTE options (expiring same day) represented 60-70% of total SPX options volume (Harbourfront Research, 2026). QQQ followed a similar trajectory.

**What this means for GEX:**

1. **Daily reset**: GEX now resets every trading day rather than weekly. The "sticky" walls that held for 3-5 days in the old regime now hold for hours.

2. **Intraday regime shifts**: The gamma flip can cross multiple times in a single session as 0DTE OI builds and decays.

3. **Amplification dominates pinning**: In the old regime, high OI at a strike created pinning (price gravitates to strike). In the 0DTE regime, high OI creates amplification because the gamma is so large that any move away from the strike triggers massive rebalancing. The market oscillates violently around the strike rather than pinning smoothly.

4. **Morning vs afternoon dynamics**: 0DTE options are typically sold in the morning (theta sellers) and bought back or expire in the afternoon. This creates a predictable intraday GEX arc: low GEX at open, building through midday, collapsing in the final hour.

**Practical adjustment:**

Re-evaluate GEX levels every 30 minutes during the session, not just at open. A wall that was valid at 10 AM may have dissolved by 2 PM as 0DTE OI shifts. FlashAlpha's real-time GEX updates are essential for this reason.

---

## 15. Honest Limitations — What GEX Actually Predicts

This section is non-negotiable for institutional-grade analysis. GEX is a useful regime descriptor. It is not a standalone predictor.

**What the research actually shows:**

**Sign reliability (~95% for SPX):** The sign of total GEX (positive vs negative) reliably predicts whether realized volatility will be below or above average. Positive GEX environments have lower realized vol. Negative GEX environments have higher realized vol. This relationship is robust across multiple studies including Barbon & Buraschi (2021) "Gamma Fragility" and the FlashAlpha 8-year backtest.

**Magnitude reliability (~70%):** The magnitude of GEX is noisier. A GEX of $500M doesn't reliably produce twice the mechanical flow of a $250M GEX. The relationship is directionally correct but not linear. Reasons: dealer hedging ratios vary, not all OI is held by dealers, some OI is hedged via other instruments.

**Incremental signal after controlling for vol:** After controlling for VIX level and ATM implied volatility, GEX has minimal incremental predictive power for next-day returns. The Avellaneda & Lipkin (2003) pinning paper and subsequent replications show that most of the "GEX effect" is captured by the vol regime itself. GEX is largely a proxy for the vol regime, not an independent signal.

**What this means in practice:**

GEX is best used as a regime classifier (positive/negative, high/low) rather than a precise level predictor. The walls it identifies are real, but their exact price levels have uncertainty of ±0.5-1.0% of spot. For NQ at 20,000, that's ±100-200 points of uncertainty on any given wall.

**The honest use case:**

- Use GEX to identify the current regime (positive/negative, near flip or not)
- Use GEX walls as zones, not precise levels
- Cross-validate every GEX-derived level with the order book (Section 8 of this file, and `order-book/level-defense-scoring.md`)
- Never trade a GEX level without order book confirmation
- Treat GEX as one of five data rivers, not as the primary signal

**What GEX cannot tell you:**

- Whether a wall will hold or break (only the order book can tell you this in real time)
- The exact timing of dealer rebalancing (threshold-based, not continuous)
- Whether a given options position is held by a dealer or a hedged institutional (the sign convention assumes dealers are short options, which is usually but not always true)
- How much of the OI is already hedged via other instruments (dealers may use futures, ETFs, or other options to hedge rather than the underlying)

---

## Cross-References

- `options-bias-engine/domains/dealer-hedging-mechanics.md` — conceptual framework (read first)
- `options-bias-engine/domains/gex-theory.md` — full GEX math and profile shapes
- `options-bias-engine/domains/dex-vex-chex.md` — the full Greek hedging cascade
- `options-bias-engine/domains/zero-dte-mechanics.md` — 0DTE gamma explosion mechanics
- `options-bias-engine/order-book/level-defense-scoring.md` — order book confirmation of GEX levels
- `options-bias-engine/order-book/iceberg-detection.md` — highest-conviction confirmation signal
- `options-bias-engine/step2-levels/wall-dynamics.md` — how walls behave in practice
- `options-bias-engine/step5-setups/gamma-flip-cross.md` — trading the regime transition

## Academic Sources

- Barbon, A. & Buraschi, A. (2021). "Gamma Fragility." SSRN Working Paper. Documents the relationship between dealer gamma exposure and realized volatility.
- Avellaneda, M. & Lipkin, M. (2003). "A Market-Induced Mechanism for Stock Pinning." Quantitative Finance. The foundational paper on options expiry pinning mechanics.
- FlashAlpha GEX Backtest (8-year study, 2016-2024). Internal research document. Available to FlashAlpha subscribers. Documents GEX sign reliability (~95%) and magnitude reliability (~70%) across SPX.
- Harbourfront Research (2026). "The 0DTE Revolution: How Same-Day Options Reshaped Equity Market Microstructure." Documents the post-2022 structural shift and the 60-70% 0DTE volume figure.
