# Industry State-of-the-Art: Marrying Volume Profile / Order Flow Levels with Dealer Gamma Levels

**Researched:** 2026-04-13
**Context:** DEEP6 NQ futures auto-trading system — integrating tape-derived structural levels (VPOC/VAH/VAL/LVN, absorption/exhaustion/momentum zones) with options-derived dealer positioning levels (gamma flip, call wall, put wall, zero gamma, vanna, charm).
**Confidence baseline:** The vendor methodologies are well-documented (HIGH). The **quantitative confluence rules** — "when both coincide, score X" — are largely proprietary/undocumented; published guides describe directional intuition, not thresholds (MEDIUM/LOW). Where literature gives numbers, they are flagged.

---

## 1. Vendor Methodologies

### 1.1 SpotGamma
SpotGamma originated the "Call Wall / Put Wall / Gamma Flip / Volatility Trigger" vocabulary. Methodology is Black-Scholes unit-gamma across a ±10% spot grid, summed by OI weight, with a proprietary intraday OI+Volume Adjustment to combat stale OI (critical in 0DTE regimes that drive >50% of SPX volume). [HIGH]
- **Call Wall** — single strike with highest net call gamma; dealers short those calls must sell into rallies, creating mechanical resistance. [HIGH]
- **Put Wall** — mirror on puts; dealers short puts buy into declines, creating mechanical support. [HIGH]
- **Gamma Flip / Zero Gamma** — aggregate dealer gamma crosses zero. Above = stabilizing (buy dips, sell rips). Below = destabilizing (sell into weakness, buy into strength). [HIGH]
- **Volatility Trigger** — proprietary; typically sits a few points *above* Zero Gamma. Marks where negative-feedback behavior actually begins, before the mathematical zero crossing. This is the more actionable regime-shift level per SpotGamma. [HIGH]
- **HIRO + Vanna Model** — HIRO measures realized dealer hedging flow (confirmation); Vanna Model shows projected hedging requirements across price × vol grid. SpotGamma's documented NQ setup requires: negative Gamma Notional + Vanna skew in trade direction + HIRO flow confirmation + price approaching Key Gamma Strike. No published numeric thresholds. [MEDIUM]
- Sources: [Call Wall](https://support.spotgamma.com/hc/en-us/articles/15297391724179-Call-Wall), [Put Wall](https://support.spotgamma.com/hc/en-us/articles/15297856056979-Put-Wall), [Gamma Flip](https://support.spotgamma.com/hc/en-us/articles/15413261162387-Gamma-Flip), [Volatility Trigger](https://spotgamma.com/volatility-trigger-zero-gamma-trading/), [NQ Vanna+HIRO](https://spotgamma.com/trading-nq-futures-vanna-hiro-indicator/)

### 1.2 MenthorQ
Publishes the same family of levels under different names and is the only vendor with explicit **futures-mapped** guides for ES and NQ.
- **Call Resistance / Put Support / High Vol Level (HVL)** — one-to-one analogs of Call Wall / Put Wall / Gamma Flip. [HIGH]
- **Blind Spots** — secondary reaction zones (away from primary strikes) where smaller OI clusters exist; they treat these as confluence amplifiers rather than standalone levels. [MEDIUM]
- **Regime rules (explicit):** Above HVL → expect range/chop, fade extremes. Below HVL → expect acceleration, trade with trend. [HIGH]
- **Confluence inputs MenthorQ layers on top of gamma:** Net GEX profile, Net Delta Exposure, Blind Spots, 0DTE gamma, Q-Score, momentum models. They frame gamma as **directional intelligence, not mechanical signal** — no proximity or scoring thresholds are published. [HIGH — confirmed absence]
- **Basis conversion for futures:** NQ levels are mapped from QQQ (not NDX or /NQ chain directly) using AI-adjusted ratio to preserve intraday accuracy while futures trade 24/5 vs. ETF RTH. Manual Ratio conversion is recommended for days when basis is moving. [HIGH]
- Sources: [Gamma Levels on ES](https://menthorq.com/guide/gamma-levels-on-es/), [Gamma Levels in NQ](https://menthorq.com/guide/gamma-levels-in-nq/), [HVL](https://menthorq.com/guide/high-vol-level/), [Futures Conversion](https://menthorq.com/guide/levels-conversion/)

### 1.3 TanukiTrade
TradingView-native GEX publisher. Uses AI-mapped QQQ→/NQ and SPX→/ES (not the futures option chain itself). Provides Cumulative (all expiries) and Selected-Alone (single expiry) views. Refresh 5×/day — slower than SpotGamma intraday reweight, acceptable for non-0DTE swing work but weaker for same-session signals. [HIGH]
- Source: [GEX Profile PRO](https://www.tradingview.com/script/v04Kzl4Q-GEX-Profile-PRO-Real-Auto-Updated-Gamma-Exposure-Levels/)

### 1.4 Volland
Unique value: attributes each trade to **dealer-buy or dealer-write** using price, surrounding orders, Black-Scholes fair value, and bid/ask — claimed >90% accuracy across expiries, 99% on 0DTE, validated against CBOE's distributed open/close data (the ground truth on SPX). Publishes large-gamma strike bands on a 10-minute candlestick, 7 days back. This matters because standard GEX assumes dealers are short gamma by default — Volland empirically checks that. [HIGH]
- Dealer gamma is **inversely correlated with realized-vol standard deviations** (published relationship). [MEDIUM]
- Source: [Volland User Guide](https://vol.land/VollandUserGuide_Jun24.pdf), [White Paper](https://vol.land/VollandWhitePaper.pdf) (PDF access blocked during this research — cite from secondary summaries)

### 1.5 SqueezeMetrics (DIX + GEX)
The original public GEX publisher (pre-SpotGamma). Two signals:
- **GEX** — S&P aggregate gamma, same Black-Scholes OI methodology. [HIGH]
- **DIX (Dark Index)** — dollar-weighted short-sale proportion in FINRA ADF/TRF (dark pool) volume over the trailing week; 0–1 scale. Higher DIX = more long-buying being absorbed off-exchange (bullish); lower = more distribution (bearish). [HIGH]
- Practitioner synthesis: **low GEX + high DIX** has been documented as a bullish setup (dealers short-gamma amplify upside when buying pressure appears). [MEDIUM — cited in FinanceTLDR retrospectives, not peer-reviewed]
- Sources: [DIX monitor](https://squeezemetrics.com/monitor/dix), [SqueezeMetrics docs](https://squeezemetrics.com/monitor/docs), [FinanceTLDR research](https://www.financetldr.com/p/research-dark-index-and-gamma-exposure)

### 1.6 BlackBoxStocks and others
BlackBoxStocks, Unusual Whales, Cheddar Flow, GEXStream, HedgePulse publish GEX dashboards but do not contribute distinct methodology beyond what SpotGamma/SqueezeMetrics established. They generally do not publish confluence rules with tape-derived structure. [MEDIUM]

### Vendor summary — what's actually published vs. not
| Signal | Published | Confluence-with-tape rules published |
|--------|-----------|---------------------------------------|
| Call/Put Wall | HIGH | None quantified |
| Gamma Flip / HVL / Zero Gamma | HIGH | None quantified |
| Volatility Trigger | HIGH (SpotGamma proprietary) | None quantified |
| Vanna / Charm strike exposure | HIGH | SpotGamma Vanna+HIRO setup (qualitative) |
| DIX-style dark pool + GEX synthesis | HIGH | Anecdotal (low-GEX + high-DIX = bullish) |

**The hard truth: no vendor publishes a quantitative "gamma × VP confluence" scoring model.** That gap is the opportunity for DEEP6.

---

## 2. Academic / Practitioner Literature

### 2.1 Barbon & Buraschi (2021) — "Gamma Fragility"
The foundational paper. Key findings: [HIGH]
- Aggregate dealer gamma imbalance predicts intraday momentum (negative gamma) vs. mean reversion (positive gamma).
- Effect is **stronger for less-liquid underlyings** — the feedback loop amplifies where hedging trades move the tape more.
- Gamma imbalance predicts **frequency and magnitude of flash crashes**.
- Mechanism: delta hedging a short-gamma book forces pro-cyclical trading (buy into strength, sell into weakness).
- Source: [Gamma Fragility SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454), [PDF](https://www.abarbon.com/assets/Barbon_Buraschi_2021_Gamma_Fragility.pdf)

### 2.2 Baltussen, Da, Lammers, Martens (2021, JFE) — "Hedging Demand and Market Intraday Momentum"
- Examined 60+ futures 1974–2020. [HIGH]
- **Return in last 30 minutes is positively predicted by return in rest of day** — specifically when net dealer gamma is negative.
- When gamma is positive, the relationship inverts (late-day mean reversion).
- Reverts over the next few days (flow-driven, not informational).
- Critical for NQ: the last-30-min effect is strongest when ex-ante gamma imbalance is negative.
- Source: [Baltussen SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3760365), [PDF](https://www3.nd.edu/~zda/intramom.pdf)

### 2.3 Ni, Pearson, Poteshman and successor work on pinning
- Well-established: large OI strikes act as settlement magnets, especially AM-settled SPX and monthly/quarterly expiries. [HIGH]
- Mechanism is charm (delta decay toward expiry) + gamma pinning when dealers are long gamma. [HIGH]

### 2.4 Charm / Vanna flows — last 90 minutes
Multiple practitioner sources converge: [HIGH]
- Charm (∂δ/∂t) operates continuously, strongest in final 90 min of session.
- On 0DTE days (Mon–Fri SPX, Wed/Fri for weekly-dominated tickers), charm flow dominates closing drift.
- Vanna (∂δ/∂σ) activates on IV regime shifts — matters on CPI/FOMC/NFP days for NQ.
- Source: [MenthorQ Vanna & Charm](https://menthorq.com/guide/why-markets-can-go-wild-after-options-expiration-vanna-and-charm-and-the-volatility-effect/), [FinanceTLDR](https://www.financetldr.com/p/vanna-and-charm)

### 2.5 Connecting order flow microstructure to GEX — the gap
No peer-reviewed paper found that explicitly combines tape-derived absorption/exhaustion signals with GEX. The Barbon-Buraschi illiquidity interaction term is the closest — it implies absorption (a liquidity-supply event at a level) should interact multiplicatively with gamma state. This is a research gap DEEP6 can exploit.

---

## 3. Conceptual Confluence Map — Canonical Level Pairs

The following pairs are repeatedly described in vendor educational material and practitioner Substacks. None has a published win-rate study; all should be validated on DEEP6's own backtest data.

| # | Tape signal | Options signal | Expected behavior | Confidence |
|---|-------------|----------------|--------------------|------------|
| C1 | Absorption zone | Call Wall above | Highest-conviction short fade — mechanical resistance meets revealed supply | MEDIUM (multiple practitioner sources) |
| C2 | Absorption zone | Put Wall below | Highest-conviction long fade | MEDIUM |
| C3 | Exhaustion zone | Past Call/Put Wall (wall breached) | "Wall failure" = acceleration trade in breach direction; dealer hedging flips to pro-cyclical | MEDIUM |
| C4 | VPOC | Zero Gamma / HVL nearby (same session) | Pin magnet — strongest in positive-gamma regime above HVL | MEDIUM |
| C5 | LVN | Gamma Flip coincident | Breakaway trade — LVN removes structural resistance exactly where dealer hedging flips to amplifying | MEDIUM |
| C6 | Momentum zone | Negative gamma regime (below HVL) | Trend-continuation boost — academic basis in Barbon-Buraschi | HIGH (academic) |
| C7 | Rejection/flipped-polarity zone | Volatility Trigger | Regime-change confirmation — structural role reversal aligns with dealer behavior flip | MEDIUM |
| C8 | Session VWAP ±1σ | Largest-gamma strike inside band | Expect pinning within value area in last 90 min, especially 0DTE | HIGH |
| C9 | Absorption at VAL | Put Wall within 0.3σ below | "Double floor" — bounce trade with tight invalidation | LOW (anecdotal) |
| C10 | Absorption at VAH | Call Wall within 0.3σ above | "Double ceiling" — fade trade | LOW (anecdotal) |
| C11 | Exhaustion + rising IV + negative gamma | — | Vanna-amplified reversal — IV crush timing matters | MEDIUM |
| C12 | Naked VPOC from prior session | Key Gamma Strike | Magnet confluence — higher fill probability | LOW (anecdotal) |

---

## 4. How to Encode Confluence — Approaches

### 4.1 Proximity kernels
Gaussian kernel on price distance: `w = exp(-((price_tape - price_gex) / σ)²)` where σ is regime-dependent (tighter in positive gamma, wider in negative gamma). Academic basis: Barbon-Buraschi shows the hedging response scales with local price-move magnitude. [MEDIUM]

### 4.2 Regime-switching weights
Binary regime: above HVL → positive-gamma weights, below → negative-gamma weights. Different level pairs activate in each regime (e.g., C4 pinning only matters in positive gamma; C5 LVN breakout only matters at/below gamma flip). Baltussen et al. directly validates regime-switching for intraday momentum. [HIGH]

### 4.3 Multiplicative confidence boost
Composite score pattern: `final = tape_score × (1 + gamma_boost)` where `gamma_boost = f(proximity, regime, OI-magnitude-percentile)`. Keeps tape as the primary signal (it fires continuously) and treats gamma as a conviction modifier. Aligns with how SpotGamma's Vanna+HIRO setup layers multiple confirmations. [MEDIUM]

### 4.4 Bayesian prior update
Treat gamma state as the prior on reversal/continuation probability; let tape signals update the posterior. Useful if DEEP6 wants per-signal win-rate calibration via Kronos or empirical Bayes. No published implementation in this space. [LOW]

### 4.5 Thresholds published in literature or by vendors
- Baltussen et al.: last 30 min, gamma-sign-conditional, statistically significant predictor of close. [HIGH]
- SpotGamma: Volatility Trigger typically "a few points" above Zero Gamma — no exact distance. [MEDIUM]
- SpotGamma intraday OI reweight: critical when 0DTE >50% of SPX daily volume. [HIGH]
- MenthorQ futures basis: use manual ratio intraday; futures 24/5 vs. ETF RTH. [HIGH]
- Nothing else published with hard numbers. **DEEP6 must calibrate thresholds on Databento backtests.**

---

## 5. Pitfalls — Why Naïve Overlay Fails

### 5.1 Proxy basis error (NQ via QQQ/NDX) [HIGH]
NQ ≠ NDX ≠ QQQ in price. Futures carry fair value (interest + dividend adjustments) and trade 24/5; ETFs only RTH. A static offset breaks intraday when basis moves on rate-expectation shifts or dividend approach. **Fix:** compute live ratio `/NQ ÷ NDX` every minute; apply to every GEX level before overlay. MenthorQ explicitly recommends this. [Source: MenthorQ Conversion Guide]

### 5.2 OI staleness [HIGH]
Official OI updates EOD only. In 0DTE regimes (>50% of SPX volume) gamma can shift dramatically intraday without OI reflecting it. SpotGamma solves this with proprietary volume-based reweighting. **DEEP6 implication:** FlashAlpha's refresh cadence matters — confirm intraday update frequency; if only EOD, treat morning GEX as a prior that decays through the session.

### 5.3 Expiry roll discontinuities [MEDIUM]
When the dominant expiry rolls (Thu→Fri, Fri→Mon), gamma levels can jump. A level that existed at 9:30 may not exist at 9:31. Practitioners handle this by publishing both cumulative and per-expiry views (TanukiTrade, MenthorQ). **DEEP6 implication:** track level identity across snapshots; don't treat a disappeared level as a "broken" level.

### 5.4 Direction-of-hedge assumption [MEDIUM]
Standard GEX assumes dealers are net short calls and short puts (selling premium to the public). In reality this can invert — institutional buying of puts for hedging can flip dealer positioning on put strikes. Volland is the only vendor that measures this empirically. **DEEP6 implication:** flag a caveat when FlashAlpha-derived levels disagree with realized-flow direction (HIRO-equivalent from our own tape).

### 5.5 Timeframe mismatch [HIGH]
Tape absorption events fire on second-scale; gamma levels update on 5-to-EOD scale. Overlay tools that re-render levels every tick create false confidence. **Fix:** lock GEX levels to snapshot timestamps, plot as horizontal bands; treat any tape-level within a proximity window as "in play" — never refresh GEX at tape frequency.

### 5.6 Regime-blind weighting [HIGH]
Using the same confluence score above vs. below HVL is the single most common amateur error. Barbon-Buraschi and Baltussen both show the sign of the effect flips across the gamma-zero line. **Fix:** regime-conditioned weight tables.

### 5.7 0DTE dominance skew [MEDIUM]
On 0DTE-heavy days, same-day gamma dwarfs longer-dated — which means levels derived from cumulative GEX miss the actual hedging driver. MenthorQ/TanukiTrade offer per-expiry views for exactly this. [Source: MenthorQ 0DTE Guide]

### 5.8 Flash-crash tail risk [MEDIUM]
Barbon-Buraschi specifically ties high negative-gamma imbalance to flash-crash frequency. An auto-executing system sized for normal-regime fills can get run over when negative gamma + news hits. **Fix:** regime-conditional position sizing; reduce size below HVL in illiquid tape conditions.

---

## Actionable for DEEP6 — Concrete Integration Rules

These translate the above into signal-engine rules. Thresholds are starting points; calibrate on Databento replay.

1. **Basis-corrected level mapping.** Every GEX level from FlashAlpha (QQQ/NDX-derived) must be multiplied by live `/NQ ÷ QQQ` (or `/NQ ÷ NDX`) ratio, recomputed at ≤1-min cadence. Never use a static offset.

2. **Regime gate on HVL / Gamma Flip.** Compute position relative to HVL once per snapshot. All confluence rules below are conditioned on `regime ∈ {positive_gamma, transition, negative_gamma}` where transition is defined as within ±1 ATR of HVL.

3. **Absorption × Put Wall (long fade).** If an absorption zone forms within `0.3σ` of session range below current price AND a Put Wall sits within `0.5 * ATR(20)` of the zone AND regime is positive or transition → boost long-reversal confidence by +30% of base tape score. Invalidate on break below Put Wall by >0.2 ATR. (Rule C2 operationalized.)

4. **Absorption × Call Wall (short fade).** Symmetric to rule 3. Additional filter: if Volatility Trigger sits *below* price, do NOT take the fade — dealers are in positive-gamma mode but vol trigger flip is imminent; risk/reward degrades.

5. **Exhaustion × Wall breach (breakout).** If exhaustion zone confirms at a prior Call/Put Wall that has been broken by >0.25 ATR intraday, flip bias to breakout-continuation. Academic basis: Barbon-Buraschi pro-cyclical hedging once dealers re-hedge across the wall. Score boost scales with `|gamma_notional|` percentile rank over trailing 20 sessions.

6. **LVN × Gamma Flip (acceleration).** If an LVN is coincident with HVL/Zero Gamma (within `0.5 * ATR`), and price is testing from the positive-gamma side, size up on breakout through LVN — the structural vacuum and the hedging amplification reinforce. Do NOT take the analogous mean-reversion trade; the regime shift kills the reversion thesis.

7. **VPOC pinning (positive-gamma only).** If current session VPOC is within `0.5 * ATR` of the largest-gamma strike AND it is within 120 minutes of the cash close AND regime is positive gamma → suppress breakout signals through VPOC; boost mean-reversion toward VPOC. Turn OFF below HVL.

8. **Last-30-min regime play (Baltussen).** With 30 min to cash close: compute sign of day's return. If net dealer gamma < 0 → boost trend-continuation signals by 20%. If net dealer gamma > 0 → boost mean-reversion signals by 20%. Highest-confidence rule here; direct academic support.

9. **Charm drift toward high-OI strike.** In final 90 min on Wed/Fri sessions, if price is within 0.5% of a strike with 90th-percentile OI for the session → add a low-magnitude directional bias toward that strike proportional to distance. Do not use as primary trigger; use as tiebreaker and to bias partial-exit levels.

10. **Flipped-polarity × Volatility Trigger.** If a support→resistance flip confirms on tape within `0.5 * ATR` of Volatility Trigger → treat as high-conviction regime-shift signal; allow short trades from that zone even when broader trend is up. (Rule C7.)

11. **0DTE dominance guard.** If 0DTE share of NQ options volume (or the NDX proxy) exceeds 40%, use per-expiry GEX levels, not cumulative. Flag cumulative-only signals as degraded.

12. **Negative-gamma risk scalar.** Global position size multiplier: `size = base_size × (1 - 0.4 * clip(|neg_gamma_z|, 0, 2.5)/2.5)` when below HVL, where `neg_gamma_z` is the z-score of current negative gamma vs. 60-day baseline. Hedges the flash-crash tail documented by Barbon-Buraschi.

---

## Citations

| # | Source | URL | Confidence |
|---|--------|-----|-----------|
| 1 | SpotGamma — Call Wall | https://support.spotgamma.com/hc/en-us/articles/15297391724179-Call-Wall | HIGH |
| 2 | SpotGamma — Put Wall | https://support.spotgamma.com/hc/en-us/articles/15297856056979-Put-Wall | HIGH |
| 3 | SpotGamma — Gamma Flip | https://support.spotgamma.com/hc/en-us/articles/15413261162387-Gamma-Flip | HIGH |
| 4 | SpotGamma — Volatility Trigger (ES) | https://spotgamma.com/volatility-trigger-zero-gamma-trading/ | HIGH |
| 5 | SpotGamma — NQ Vanna + HIRO | https://spotgamma.com/trading-nq-futures-vanna-hiro-indicator/ | HIGH |
| 6 | SpotGamma — GEX Explained | https://support.spotgamma.com/hc/en-us/articles/15214161607827-GEX-Gamma-Exposure-Explained-What-It-Is-and-How-SpotGamma-Uses-It | HIGH |
| 7 | SpotGamma — Absorption and Exhaustion | https://support.spotgamma.com/hc/en-us/articles/15245728388627-Absorption-and-Exhaustion | MEDIUM (blocked, cited from summary) |
| 8 | MenthorQ — Gamma Levels Guide | https://menthorq.com/guide/key-gamma-levels/ | HIGH |
| 9 | MenthorQ — HVL | https://menthorq.com/guide/high-vol-level/ | HIGH |
| 10 | MenthorQ — Gamma Levels on ES | https://menthorq.com/guide/gamma-levels-on-es/ | HIGH |
| 11 | MenthorQ — Gamma Levels in NQ | https://menthorq.com/guide/gamma-levels-in-nq/ | HIGH |
| 12 | MenthorQ — Futures Conversion | https://menthorq.com/guide/levels-conversion/ | HIGH |
| 13 | MenthorQ — 0DTE Gamma Levels | https://menthorq.com/guide/0dte-gamma-levels/ | HIGH |
| 14 | MenthorQ — Vanna & Charm | https://menthorq.com/guide/why-markets-can-go-wild-after-options-expiration-vanna-and-charm-and-the-volatility-effect/ | HIGH |
| 15 | TanukiTrade — GEX Profile PRO | https://www.tradingview.com/script/v04Kzl4Q-GEX-Profile-PRO-Real-Auto-Updated-Gamma-Exposure-Levels/ | HIGH |
| 16 | Volland — User Guide | https://vol.land/VollandUserGuide_Jun24.pdf | HIGH |
| 17 | Volland — White Paper | https://vol.land/VollandWhitePaper.pdf | MEDIUM (access blocked in session) |
| 18 | SqueezeMetrics — Dark Index | https://squeezemetrics.com/monitor/dix | HIGH |
| 19 | SqueezeMetrics — Docs | https://squeezemetrics.com/monitor/docs | HIGH |
| 20 | FinanceTLDR — DIX + GEX research | https://www.financetldr.com/p/research-dark-index-and-gamma-exposure | MEDIUM |
| 21 | Barbon & Buraschi — Gamma Fragility (SSRN) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454 | HIGH |
| 22 | Barbon & Buraschi — PDF | https://www.abarbon.com/assets/Barbon_Buraschi_2021_Gamma_Fragility.pdf | HIGH |
| 23 | Baltussen, Da, Lammers, Martens — Hedging Demand (JFE) | https://www.sciencedirect.com/science/article/abs/pii/S0304405X21001598 | HIGH |
| 24 | Baltussen et al. — working paper PDF | https://www3.nd.edu/~zda/intramom.pdf | HIGH |
| 25 | Baltussen et al. — SSRN | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3760365 | HIGH |
| 26 | Perfiliev — GEX and Zero Gamma calculation | https://perfiliev.com/blog/how-to-calculate-gamma-exposure-and-zero-gamma-level/ | HIGH |
| 27 | BSIC — Barbon-Buraschi summary | https://bsic.it/how-dealers-gamma-impacts-underlying-stocks/ | MEDIUM |
| 28 | Jack Meson — GEX model conflicts | https://jackmeson1.github.io/finance/options/2025/10/19/gamma-wall-why-models-conflict/ | MEDIUM |
| 29 | LuxAlgo — SpotGamma Levels | https://www.luxalgo.com/blog/spotgamma-levels-reveal-dealer-positioning/ | MEDIUM |
| 30 | Trader-Dale — Absorption setup | https://www.trader-dale.com/order-flow-how-to-spot-reversals-with-the-absorption-setup-17th-feb-26/ | MEDIUM |
| 31 | FinanceTLDR — Vanna & Charm | https://www.financetldr.com/p/vanna-and-charm | MEDIUM |

---

**Key takeaway for DEEP6 planning:** The vendors publish *what the levels are* (HIGH confidence) but *not how to score confluence quantitatively*. The academic literature gives one rigorous quantitative hook — regime-conditioned intraday momentum (Baltussen + Barbon-Buraschi) — which should be the first confluence rule you validate. Everything in the "Canonical Level Pairs" table is practitioner-anecdotal and must be backtested on Databento MBO before trusting in production. The proprietary edge for DEEP6 is combining **realized tape flow** (which vendors cannot see — they only see options) with **publisher-grade GEX levels** — this is a category no public vendor occupies.
