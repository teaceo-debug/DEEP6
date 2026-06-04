# Dark Pool Foundations — What the Data Actually Is

This file covers dark pool infrastructure at the plumbing level. Not trading strategy. The mechanics, the reporting chain, the biases baked into the data before you ever look at a chart.

---

## 1. What Are Dark Pools

Dark pools are Alternative Trading Systems (ATS) registered under SEC Regulation ATS (Rules 300-304). They're exempt from exchange registration requirements. The defining characteristic: they don't display orders pre-trade. No pre-trade transparency.

As of Q1 2026, there are 33-38 active ATS venues in the US. The number fluctuates as smaller venues open, merge, or shut down. FINRA publishes a quarterly ATS transparency report with volume breakdowns by venue.

The regulatory basis is Reg ATS (17 CFR 242.300-304), adopted 1998, amended 2018 (Reg ATS-N). ATS-N requires Form ATS-N filings disclosing operational details, conflicts of interest, and subscriber information. These filings are public and worth reading if you want to understand how a specific venue works.

---

## 2. Venue Classification

Dark pools aren't monolithic. Three distinct categories with different participant profiles and information content.

### Broker-Dealer Crossing Networks (~70% of ATS volume)

These are the dominant venues. Run by major banks and broker-dealers, primarily serving institutional clients. Order flow is a mix of the broker's own clients plus internalized flow.

| Venue | Operator | ATS Volume Share |
|-------|----------|-----------------|
| Crossfinder | UBS | 22.4% |
| SIGMA X2 | Goldman Sachs | 15.7% |
| Level ATS | Virtu Financial | 11.2% |
| Instinet | Nomura | 9.8% |
| MS Pool | Morgan Stanley | 8.4% |
| Barclays LX | Barclays | 6.1% |
| JPM-X | JPMorgan | 5.9% |

These venues have the highest institutional participation. When you see a large block print in Crossfinder or SIGMA X2, the counterparty is almost certainly institutional.

### Electronic Market Maker Pools (~15-20% of ATS volume)

Run by HFTs and electronic market makers. Citadel Connect and Virtu VEQ Link are the primary examples. These venues handle a mix of retail internalization and institutional flow. The information content is lower on average because retail flow dominates.

### Independent and Specialized Venues (~10-15% of ATS volume)

- **Liquidnet H2O**: Buy-side only. Asset managers trading directly with each other, no broker intermediation. Block-focused. Highest average trade size of any venue.
- **OneChronos**: Uses combinatorial auction matching. Optimizes for multi-leg institutional strategies.
- **IntelligentCross**: ML-driven matching engine that adapts timing to minimize market impact.

---

## 3. Critical Distinction: Dark Pool vs ATS vs Off-Exchange

This is where most retail traders get confused, and where most "dark pool data" products mislead.

**True ATS dark pool volume**: ~15-18% of total US equity volume. These are trades executed on registered ATS venues with institutional participants.

**Retail internalization by wholesalers**: ~25-30% of total US equity volume. Citadel Securities handles ~25-30% of US retail order flow. Virtu handles ~12-15%. These trades never touch an exchange or ATS. They're executed internally by the wholesaler against their own inventory.

**Combined off-exchange**: ~40-45% of total US equity volume. This is the number you see cited in headlines.

Why this matters for trading: retail internalization appears in "dark pool data" sold by most data vendors. But the information content is completely different. A 50,000-share block in Crossfinder is an institutional decision. A 200-share retail order internalized by Citadel is noise. Treating them identically is a category error.

When a data vendor says "dark pool volume," ask them: does this include retail internalization? Most do. The ones that don't are more expensive and more useful.

---

## 4. Trade Reporting Mechanics

All dark pool trades are eventually reported. The question is when and where.

**Reporting venue**: FINRA Trade Reporting Facility (TRF). There are three TRFs: FINRA/Nasdaq TRF, FINRA/NYSE TRF, and FINRA/ORF (OTC Reporting Facility). Dark pool trades report to whichever TRF the ATS is affiliated with.

**Reporting deadlines**:
- Market hours (9:30 AM - 4:00 PM ET): within 10 seconds of execution
- Extended hours: within 10 seconds
- Overnight (8:00 PM - 4:00 AM ET): by 4:15 AM next business day

**Actual latency** (NYU Stern 2021 study):
- Median execution-to-TRF latency: 2.5ms
- 95th percentile: 200ms
- The 200ms tail matters. During high-volatility periods, reporting latency spikes. You can see a cluster of prints appear simultaneously that actually executed over a 200ms window.

**Regulatory basis**: SEC Reg NMS Rule 601 requires all trades to be reported. There are no exemptions for dark pool trades. Every executed trade eventually appears in the consolidated tape.

**The one exception**: canceled orders. If an order is placed in a dark pool and never executes, it's never reported. 7-10% of dark pool orders are canceled before execution. You have no visibility into this order flow.

---

## 5. What Data Is Reported vs Not

**Reported to the tape**:
- Trade price
- Trade size (shares)
- Execution timestamp
- ATS venue identifier (the "exchange" field in the tape)
- Trade condition modifiers (e.g., "Form T" for extended hours, "X" for cross trade)

**Not reported**:
- Counterparty identities (buyer and seller are anonymous)
- Order flow direction (you don't know if the print was buyer-initiated or seller-initiated)
- Participant types (institutional vs retail vs HFT)
- Partial fills (a 500,000-share order filled in 50 tranches of 10,000 each looks like 50 separate trades)
- Resting order size (you can't see the full order behind a partial fill)

The direction problem is the most significant. On a lit exchange, you can infer direction from whether the trade hit the bid or ask. In a dark pool executing at midpoint, there's no bid or ask to reference. You're looking at a price and a size with no directional information.

Some vendors attempt to infer direction using the Lee-Ready algorithm (1991) or the Ellis-Michaely-O'Hara (2000) tick rule. These algorithms are ~70-75% accurate on lit exchange data and significantly less accurate on dark pool midpoint prints.

---

## 6. NBBO and Execution Quality

**Rule 611 (Order Protection Rule)**: Requires all trades to execute at or within the National Best Bid and Offer. Dark pools cannot execute trades at prices worse than the NBBO. This is the floor.

**Midpoint pegging**: The dominant execution type in dark pools. ~60-70% of ATS volume executes at the exact NBBO midpoint. This is why dark pools are attractive to institutions: they get price improvement over the spread without moving the market.

**Execution quality statistics**:
- 69% of dark pool trades execute within 0.5 cents of NBBO (SEC 2014 memo, "Equity Market Structure Literature Review")
- Average price improvement over lit execution: 0.5-1.0 cent per share
- This sounds small but on a 100,000-share block it's $500-$1,000 in savings

**Reading prints relative to NBBO**:
- Print at midpoint: standard dark pool execution, no directional signal
- Print above ask: aggressive institutional buying. Someone paid through the offer to get filled. This is a strong signal.
- Print below bid: aggressive institutional selling. Someone sold through the bid.
- ~4% of dark pool trades execute at stale reference prices (BIS 2023). HFTs profit on 96-99% of these situations by providing liquidity at the stale price and immediately hedging.

**Practical implication**: When you see a large print significantly above the ask or below the bid, that's not a data error. That's an institution that needed to get done and paid for it. These prints have the highest directional information content of any dark pool data.

---

## 7. Seven Data Biases

Before building any signal on dark pool data, internalize these biases. They don't go away. You manage around them.

### Bias 1: Reporting Latency Variance

Median 2.5ms, 95th percentile 200ms. During high-volatility events (FOMC, earnings, macro data), latency spikes further. A cluster of prints appearing simultaneously on your feed may represent trades that executed over a 200ms window. Time-stamping your signals to the print time rather than the execution time introduces systematic error during the moments that matter most.

### Bias 2: Canceled Trade Invisibility

7-10% of dark pool orders cancel before execution. You see the executions. You don't see the attempts. An institution that tried to buy 500,000 shares, got 50,000 filled, then canceled the rest looks identical to an institution that only wanted 50,000 shares. The canceled portion is invisible.

### Bias 3: Retail Internalization Misclassification

Most data vendors bundle retail internalization with true ATS dark pool volume. A 200-share retail order internalized by Citadel has zero institutional information content. Mixing it with a 50,000-share Crossfinder block degrades your signal. If your data source doesn't separate these, your "dark pool signal" is ~25-30% noise by volume.

### Bias 4: Stale Price Execution

~4% of dark pool trades execute at stale reference prices (BIS 2023). These prints appear at prices that no longer reflect current market conditions. They can look like significant above-ask or below-bid prints when they're actually just latency artifacts. HFTs systematically exploit this, which is why the 96-99% HFT profitability figure exists.

### Bias 5: Signal Decay

Academic research (Nimalendran & Ray 2014, Comerton-Forde & Putniñš 2015) consistently finds that only ~35% of dark pool volume carries genuine informational content. The remaining 65% is noise: retail internalization, index rebalancing, ETF creation/redemption, portfolio rebalancing, tax-loss harvesting. Building a signal on raw dark pool volume means 65% of your inputs are noise.

### Bias 6: Midpoint Pegging Ambiguity

When 60-70% of volume executes at the exact midpoint, you lose directional information on the majority of prints. The midpoint is neither bid nor ask. Lee-Ready and tick-rule direction inference drops to ~60-65% accuracy on midpoint prints, barely better than a coin flip.

### Bias 7: Regulatory Arbitrage

European dark pools (MTFs under MiFID II) have different reporting requirements and later reporting deadlines. If you're using a data source that includes European venue data for US-listed ADRs or cross-listed stocks, the reporting timing is inconsistent with US TRF data. This creates phantom clustering effects in time-series analysis.

---

## 8. Volume Statistics (Q1 2026)

**Aggregate**:
- Dark pool ATS volume: 40.3% of total US equity volume (record high as of Q1 2026)
- Growth: +3.1 percentage points over the prior 12 months
- The trend is structural. Institutional adoption of dark pools has increased every year since 2010.

**NQ-relevant equities** (dark pool share of total volume):
| Symbol | Dark Pool Share | Notes |
|--------|----------------|-------|
| NVDA | 11.2% | Lower than average; high retail participation |
| QQQ | 10.7% | ETF; significant creation/redemption flow |
| MU | 18.2% | Higher institutional concentration |
| AMD | 17.2% | Higher institutional concentration |

QQQ's dark pool share is particularly relevant for NQ proxy analysis. ETF creation/redemption activity is a significant component of QQQ dark pool volume and has different information content than directional institutional flow.

**Time-of-day distribution**:
- 85-90% of dark pool volume executes during regular market hours (9:30 AM - 4:00 PM ET)
- 40% of daily dark pool volume is concentrated in the 10:00 AM - 3:00 PM window
- Pre-market and after-hours dark pool volume is primarily earnings-related and index rebalancing

**Block trade activity** (10,000+ shares):
- Average: 18,400 block trades per day across all dark pools
- Largest single Q1 2026 block: 4.8 million shares of AAPL in a single Crossfinder print
- Block trades have the highest information content and the lowest noise contamination (see Comerton-Forde & Putniñš 2015 on block trade exception)

---

## Sources

- SEC Regulation ATS (17 CFR 242.300-304): https://www.sec.gov/rules/final/34-40760.txt
- SEC Reg ATS-N (2018 amendments): https://www.sec.gov/rules/final/2018/34-83663.pdf
- FINRA ATS Transparency Data (quarterly): https://www.finra.org/filing-reporting/market-transparency-reporting/ats-transparency-data
- SEC 2014 Equity Market Structure Literature Review: https://www.sec.gov/marketstructure/research/equity_market_structure_literature_review_part_ii_dark_pools.pdf
- NYU Stern 2021 (reporting latency): Menkveld, A.J. et al., "A Flash Crash in a Dark Pool," NYU Stern Working Paper 2021
- BIS 2023 (stale price execution): BIS Working Papers No. 1089, "Dark pool trading and price discovery," 2023
- Nimalendran & Ray 2014: "Informational Linkages Between Dark and Lit Trading Venues," Journal of Financial Markets, 2014
- Comerton-Forde & Putniñš 2015: "Dark Trading and Price Discovery," Journal of Financial Economics, 2015
