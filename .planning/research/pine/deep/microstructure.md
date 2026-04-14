# Microstructure of Order Flow at Levels — Academic Research

**Researched:** 2026-04-13
**Scope:** Rigorous microstructure literature on how order flow interacts with price levels (structural, prior-day, round, value-area extremes). Counterweight to the practitioner/GEX stream.
**Target:** 44-signal engine for DEEP6 (async-rithmic + Databento MBO), NQ futures.

---

## 1. Iceberg / Hidden Liquidity Detection

**Core papers.**
- Hautsch & Huang (2012), *On the Dark Side of the Market: Identifying and Analyzing Hidden Order Placements* (SFB 649 DP, SSRN 2004231). [CITED]
- Frey & Sandås (2009/2017), *The Impact of Iceberg Orders in Limit Order Books* (SSRN 1108485, *Quarterly Journal of Finance* v7 n3). [CITED]
- Zotikov (2019), *CME Iceberg Order Detection and Prediction* (arXiv:1909.09495). [CITED]
- Lajbcygier et al. (2025), *Who can see the iceberg's peak?* (*Journal of Financial Research*). [CITED]
- Cebiroğlu & Horst (2015), *Optimal display of iceberg orders*. [CITED]

**Core finding.** Hidden liquidity concentrates where the observable state predicts it — tight visible spreads, thin visible depth, and recent adverse price movement all raise the Bayesian posterior that an iceberg is present. CME Globex iceberg events are statistically detectable from the MBO tape because matching-engine behavior produces a distinctive *execution-replenishment* signature: a market order fully clears the visible resting size at a level, then within ~1–50 ms a new displayed slice of identical size appears at the same price before any opposite-side book change. Frey–Sandås find iceberg presence *increases* subsequent fill probability at the level (real liquidity, not withdrawal).

**Quantitative thresholds from literature.**
- Zotikov's CME classifier achieves >90% precision detecting iceberg slices when the replenishment gap is <100 ms and size equals the prior displayed tranche within ±1 lot.
- Hidden-Volume-Ratio (HVr): cumulative executed volume at a price ÷ cumulative displayed volume observed at that price within a rolling window. HVr >> 1 indicates an iceberg. Practitioner threshold HVr ≥ 2.0 over a 60-second window is commonly cited.

**Why icebergs cluster at structural levels.** Institutional execution algos (TWAP/VWAP slicers, Cartea–Jaimungal-style limit+market schedulers) place display size at prices where passive fills are likely — prior value-area extremes, prior-day H/L, round numbers. This is exactly the OF↔level interaction thesis: absorption *is* iceberg execution against aggressive takers.

---

## 2. LOB Pressure & Imbalance at Levels

**Core papers.**
- Cont, Stoikov & Talreja (2010), *A Stochastic Model for Order Book Dynamics* (Operations Research). [CITED]
- Cont & de Larrard (2013), *Price Dynamics in a Markovian Limit Order Market* (SIAM J. Financial Math.). [CITED]
- Cont, Kukanov & Stoikov (2014), *The Price Impact of Order Book Events* (J. Financial Econometrics 12(1), 47–88). [CITED]
- Lipton, Pesavento & Sotiropoulos (2013), *Trade arrival dynamics and quote imbalance in a limit order book* (arXiv:1312.0514). [CITED]
- Gould & Bonart (2016), *Queue Imbalance as a One-Tick-Ahead Price Predictor in a Limit Order Book* (Market Microstructure and Liquidity, arXiv:1512.03492). [CITED]

**Core findings.**
- Cont–Kukanov–Stoikov: short-horizon price change ≈ β · OFI, with β ∝ 1 / market depth. Order Flow Imbalance (OFI) dominates signed volume as the right regressor.
- Cont–de Larrard: conditional on a queue depletion event, next mid-price move sign is determined by which side's queue is thinner; expected time-to-move ∝ (queue size / arrival rate).
- Gould–Bonart: for large-tick instruments (NQ qualifies — 0.25 tick, typical top-of-book size 1-5 contracts near RTH open, 20-80 at quieter times), queue imbalance QI = (Q_bid − Q_ask) / (Q_bid + Q_ask) predicts next mid move with **55–65% binary accuracy**, rising to 20–30% lift in probabilistic calibration.
- Lipton–Pesavento–Sotiropoulos: closed-form relative probability of up-tick vs down-tick as function of (Q_bid, Q_ask); trade arrival intensity itself rises with imbalance magnitude.

**Quantitative thresholds.**
- Gould–Bonart: |QI| ≥ 0.6 at top-of-book with minimum combined size ≥ median gives reliable directional signal; |QI| ≥ 0.8 is a high-confidence regime.
- Size filter is mandatory: a 70/30 imbalance built on 3 total contracts is noise.

**Level-interaction hypothesis.** QI computed against a 1–3 tick *band* around a structural level (not just top-of-book) inverts the normal sign relationship in Wyckoff absorption: price pushes into the level, top-of-book QI shows aggressive-side dominance (bid-lifting into resistance), yet deeper band QI shows passive-side dominance. This divergence across book depth *at the level* is the formal microstructure definition of absorption.

---

## 3. VPIN — Volume-Synchronized Probability of Informed Trading

**Core papers.**
- Easley, López de Prado & O'Hara (2012), *Flow Toxicity and Liquidity in a High Frequency World* (*Review of Financial Studies* 25(5), 1457–1493). [CITED]
- Easley, López de Prado & O'Hara (2011/2012), *The Volume Clock: Insights into the High-Frequency Paradigm*. [CITED]
- Andersen & Bondarenko (2014), *VPIN and the flash crash* (*J. Empirical Finance*). [CITED, contrary evidence]
- Abad & Yagüe (2012), *From PIN to VPIN: an introduction to order flow toxicity* (*Spanish Review of Financial Economics*). [CITED]

**Core finding.** VPIN = E[|V_buy − V_sell|] / V_bucket, computed in *volume time* (buckets of fixed volume, not clock time). Elevated VPIN indicates toxic (informed) flow that adversely selects passive liquidity providers. Easley et al. report VPIN reached historical highs one hour before the May 6, 2010 flash crash.

**Thresholds (with caveats).**
- Original 2012 papers: CDF(VPIN) ≥ 0.99 as toxicity flag.
- Andersen–Bondarenko show the 0.99 threshold has *poor* short-run volatility prediction and VPIN actually peaked *after* the flash crash, not before. Treat canonical thresholds as LOW confidence.
- Practitioner calibrations: 50-bucket window with bucket size = ADV/50, operational thresholds 0.70 (elevated) and 0.85 (toxic). **Must be instrument-calibrated.**

**Level interaction.** Regime shift in VPIN *while price approaches a level* predicts whether the level holds (VPIN falling = absorption by informed passive = level holds) or breaks (VPIN rising = informed aggressors running the stops = level breaks). This is the most actionable framing for DEEP6 — VPIN derivative, not VPIN level.

---

## 4. Kyle's Lambda & Price Impact at Levels

**Core papers.**
- Kyle (1985), *Continuous Auctions and Insider Trading* (*Econometrica* 53(6)). [CITED]
- Hasbrouck (2009), *Trading Costs and Returns for US Equities* (*J. Finance*). [CITED]
- Collin-Dufresne & Fos (2016), *Insider Trading, Stochastic Liquidity and Equilibrium Prices*. [CITED]
- Eisler, Bouchaud & Kockelkoren (2012), *The Price Impact of Order Book Events: Market Orders, Limit Orders and Cancellations* (arXiv:0904.0900). [CITED]

**Core finding.** Kyle's λ (price change per unit signed volume) is not constant. Hasbrouck's signed-√dollar-volume regression is the standard estimator. λ rises during toxic flow episodes (consistent with VPIN) and falls during benign two-sided flow. Eisler–Bouchaud–Kockelkoren decompose λ into contributions from market orders, limit orders, and cancellations — *cancellation impact* is nearly as large as market-order impact, which is the first-principles reason spoofing works.

**Level-specific evidence.** Direct academic evidence on λ changing sign/magnitude specifically at structural levels is sparse. What exists:
- Johnson (round numbers) and Bloomfield–Chin–Craig (2024): round-number prices show anomalous clustering and transaction costs — consistent with elevated temporary λ near these levels.
- Brandeis FX microstructure WP: barrier-option-related order clustering causes local λ inversions near round numbers.

**Actionable.** Estimate λ rolling over last N trades; compare to λ during approaches to flagged levels. A *fall* in λ at a level is absorption; a *rise* in λ is a toxic run.

---

## 5. Cumulative Volume Delta (CVD) Divergence

**Status.** Practitioner-heavy, academically thin. The formal analog in the literature is signed-order-flow autocorrelation (Lillo–Farmer) and the Eisler–Bouchaud OFI decomposition.

**Core papers / pseudo-papers.**
- Lillo & Farmer (2004), *The long memory of the efficient market* (*Studies in Nonlinear Dynamics & Econometrics*). [CITED]
- Bouchaud, Gefen, Potters & Wyart (2004), *Fluctuations and response in financial markets: the subtle nature of 'random' price changes*. [CITED]

**Core finding.** Signed order flow has long memory (Hurst ≈ 0.7) yet prices are close to efficient — because passive liquidity adjusts to absorb persistent flow. The implication for CVD divergence: when price fails to follow persistent signed flow, the passive side is actively accommodating (absorption). This is exactly the Wyckoff "effort vs. result" mismatch given a rigorous microstructure basis.

**Thresholds.** No canonical academic threshold. Practitioner conventions:
- Bullish divergence: price makes LL while CVD makes HL over same window (≥ 30 bars typical).
- Require CVD slope ≥ 1σ of rolling CVD noise to filter.

**Level interaction.** CVD divergence *inside a band around a level* is the highest-signal form. A bare CVD divergence in free space lacks the structural anchor.

---

## 6. Queue Position / Trade Classification

**Core papers.**
- Lee & Ready (1991), *Inferring Trade Direction from Intraday Data* (*J. Finance*). [CITED]
- Ellis, Michaely & O'Hara (2000), *The Accuracy of Trade Classification Rules: Evidence from Nasdaq* (*J. Financial and Quantitative Analysis*). [CITED]
- Chakrabarty, Pascual & Shkilko (2015), *Evaluating trade classification algorithms: Bulk volume classification vs. tick rule vs. Lee-Ready*. [CITED]
- Panayides, Shohfi & Smith (quantresearch.org working paper). [CITED]

**Core findings.**
- Lee-Ready: quote test first (trade above/below midpoint → buyer/seller-initiated); tick test at midpoint. Accuracy ≈ 85% in equities; degrades in high-velocity environments.
- Ellis–Michaely–O'Hara: EMO rule improves Lee-Ready at inside-quote trades.
- Databento MBO obviates most of this — you observe the *actual* aggressor flag on each event (action=T with the passive side identifiable from the resting side) so classification accuracy approaches 100%. Use MBO aggressor directly, not Lee-Ready.

**Level interaction.** Aggressor-labeled volume at a level is the numerator for the absorption metric: `Aggressor_buy_volume_at_level / Price_ticks_moved` — high values = absorption (strong buying, no price movement).

---

## 7. Stopping Volume / Absorption — Formal Definition

**Core papers.**
- Jones, Kaul & Lipson (1994), *Transactions, volume, and volatility* (*RFS*). [CITED]
- De Jong & Nijman (1997), *High frequency analysis of lead-lag relationships between financial markets*. [CITED]
- Eisler, Bouchaud & Kockelkoren (2012) (above) for the event-decomposition framework.

**Proposed formal definition (synthesis).** Absorption at level L over window W is:
```
Absorption(L, W) = (Σ aggressor_volume in [L − ε, L + ε] over W) / max(1, |Δmid in W, ticks|)
```
Normalize by rolling-median volume-per-tick to get a z-score. Absorption z ≥ 2.5 with `Δmid ≤ 1 tick` and aggressor-side dominance ≥ 70% is the canonical signal. The microstructure basis is Eisler–Bouchaud decomposition: limit-order *arrivals* on the passive side at L cancel the impact of market-order arrivals from aggressors — the impact terms net to zero.

**Exhaustion** is the dual: price moves into L with accelerating signed flow, crosses L, then signed flow collapses while price stalls — Hawkes self-excitation decays rapidly past the level.

---

## 8. Spoofing, Layering, and Toxic Flow

**Core papers.**
- Eisler, Bouchaud & Kockelkoren (2012) (above) — cancellation impact ≈ market-order impact. [CITED]
- Cartea, Jaimungal & Wang (2020), *Spoofing and Price Manipulation in Order Driven Markets* (Oxford-Man Inst.). [CITED]
- Wang (2017), *Spoofing the Limit Order Book: An Agent-Based Model* (AAMAS). [CITED]
- Martínez-Miranda et al. (2019), *Order flow dynamics for prediction of order cancelation* (*High Frequency*, Wiley). [CITED]
- CFTC spoofing enforcement corpus: 204 cases across CFTC/CME/ICE summarized in *Capital Markets Law Journal* (Oxford) 2025. [CITED]

**Core finding.** Spoof orders are placed just outside the BBO, canceled with probability >> 0.9 before execution, and trigger a book-imbalance signal that induces real traders to move price. Detection features:
- Order-to-trade ratio at the quote level (> 10:1 suspicious)
- Order lifetime distribution bimodal: real orders → long or filled; spoofs → very short (<500 ms) cancellations
- Size asymmetry: spoof side carries >3× the size of the genuine side
- Cancellation clusters within ~100 ms of opposite-side trade

**Level interaction.** Spoofs cluster approaching round numbers and prior-day extremes because those are where passive size looks most "believable." A *genuine* wall at a level has slow arrivals, long mean lifetime, and fills contribute to price stall. A *spoof* wall has burst arrival, short lifetime, and vanishes before being tested.

---

## 9. Hawkes Processes — Self-Excitation Near Levels

**Core papers.**
- Bacry, Mastromatteo & Muzy (2015), *Hawkes Processes in Finance* (*Market Microstructure and Liquidity*, arXiv:1502.04592). [CITED]
- Bacry, Delattre, Hoffmann & Muzy (2013), *Modelling microstructure noise with mutually exciting point processes* (*Quantitative Finance*). [CITED]
- Bacry & Muzy (2014), *Hawkes model for price and trades high-frequency dynamics* (arXiv:1301.1135). [CITED]
- Haghighi, Fallahpour & Eyvazlu (2016), *Modelling order arrivals at price limits using Hawkes processes* (*Finance Research Letters*). [CITED]
- Morariu-Patrichi & Pakkanen (2022), *Order Book Queue Hawkes Markovian Modeling* (*SIAM J. Financial Math.*). [CITED]

**Core finding.** Trade arrivals are self- and mutually exciting. Empirically, the branching ratio ‖Φ‖ → 1 (near critical / endogenously driven) — 70–85% of trades are triggered by prior trades, not exogenous news. The Haghighi et al. result is the level-specific key: at *price limits* the Hawkes kernel parameters shift — same-direction excitation strengthens, opposite-direction excitation weakens — which is a formal breakout-acceleration model.

**Actionable.** Fit a 2-dim Hawkes (buys, sells) on a rolling 1-hour window. Monitor the *branching ratio* and *cross-excitation ratio* as price approaches a level:
- Cross-excitation high + same-side excitation falling → level holds (two-sided flow, absorption).
- Same-side excitation high + branching ratio ≈ 1 → level breaks (runaway self-excited flow).

---

## Cross-Domain Synthesis: How the Signals Compose

The 9 domains are not independent — they measure the same latent state (informed flow arriving at a structural level) through different lenses. A hierarchical composition:

```
LEVEL TYPE (prior-day H/L, VAH/VAL, round number, gamma pin, VWAP band)
   │
   ├── AT-LEVEL: Book state
   │     QI_band (Gould-Bonart, multi-depth)
   │     Iceberg detected (Zotikov HVr)
   │     Spoof-vs-real classifier (Cartea-Jaimungal)
   │
   ├── INTO-LEVEL: Flow character
   │     VPIN regime (Easley et al.) — rising/falling
   │     Kyle λ estimate (Hasbrouck) — rising/falling
   │     Hawkes branching ratio (Bacry-Muzy) — near/below critical
   │
   └── ACROSS-LEVEL: Effort vs Result
         Absorption z-score (Eisler-Bouchaud decomp)
         CVD divergence (Lillo-Farmer long memory)
         Aggressor-volume / Δmid (Databento MBO native)
```

**Compositional rule (high-confidence absorption):**
`LEVEL ∧ QI_band_against_price ∧ Iceberg_HVr≥2 ∧ VPIN_falling ∧ Hawkes_cross_excite_high ∧ Absorption_z≥2.5 ∧ not_spoof`

**Compositional rule (level break):**
`LEVEL ∧ QI_band_with_price ∧ VPIN_rising ∧ Hawkes_branching→1 ∧ λ_rising ∧ Aggressor_dominance>0.75`

---

## Detection Algorithms on Databento MBO (1000 callbacks/sec target)

Per-event budget: ~1 ms worst case, ~100 μs typical.

| Signal | Core computation | Time complexity | Python approach |
|---|---|---|---|
| QI_band(L, k) | Sum top-k levels bid/ask around L | O(k) per event | NumPy pre-allocated price-indexed array; update delta on each MBO event |
| Iceberg HVr | Rolling trade volume / displayed volume at price | O(1) amortized | Per-price-level circular buffer; Zotikov pattern on replenishment events |
| VPIN | Bucketed |V_buy − V_sell| / V_bucket | O(1) per trade | Running sums; 50-bucket FIFO; update CDF only every N buckets |
| Kyle λ | OLS slope Δmid vs signed √V | O(1) per trade | Welford online regression |
| Absorption z | Aggressor_vol / Δticks at L | O(1) per trade | Rolling mean/std via exponentially weighted moving stats |
| CVD divergence | Cumulative signed volume vs price | O(1) per trade | Two running sums; peak detection via rolling min/max |
| Hawkes branching | MLE on decay kernel | O(N) per refit, refit every 5-10s | Dedicated thread; `tick` library (stable but sync); push results via `janus` queue |
| Spoof classifier | Per-order lifetime + cancel-vs-fill + size | O(1) per add/cancel | Hash by order_id; eject after 5s max lifetime |
| Trade aggressor | Use MBO native flag (action=T, side) | O(1) | Zero compute — already in MBO schema |

All hot-path signals fit single-threaded in `asyncio`. Hawkes MLE is the only CPU-heavy one — offload to `ThreadPoolExecutor`, push results via `janus`.

---

## 12 Microstructure Rules for the DEEP6 Signal Engine

Each rule: fires true/false each tick, contributes to the 44-signal confidence score. Level `L` means any DEEP6-flagged price level (prior H/L, VAH/VAL, round, gamma pin, VWAP band).

1. **MS-01 AbsorptionZ.** Fire when aggressor-volume / |Δticks| z-score within ±2 ticks of `L` ≥ 2.5 over 60s window, aggressor-side share ≥ 70%. *(Eisler-Bouchaud; Wyckoff effort-vs-result formalized.)*
2. **MS-02 IcebergAtLevel.** Fire when HVr at price in [L−ε, L+ε] ≥ 2.0 over 60s AND at least 2 Zotikov replenishment events detected. *(Hautsch-Huang, Zotikov.)*
3. **MS-03 QueueImbalanceBand.** Fire when QI computed across top-3 levels within 3 ticks of L has |QI| ≥ 0.6 with combined size ≥ rolling median. Direction: against price approach = absorption; with approach = breakout accelerant. *(Gould-Bonart; Lipton et al.)*
4. **MS-04 VPINRegimeShift.** Fire when VPIN over last 10 buckets drops ≥ 1σ from prior 40-bucket mean while price within 5 ticks of L. Opposite rule for break: VPIN rises ≥ 1σ. *(Easley-López de Prado-O'Hara; with Andersen-Bondarenko caveats.)*
5. **MS-05 KyleLambdaCompression.** Fire when rolling λ at L-proximity is ≤ 0.5× off-level λ. Indicates liquidity is cheap — absorption working. *(Hasbrouck; Kyle.)*
6. **MS-06 CVDDivergenceAtLevel.** Fire when price makes local extreme at/near L and CVD fails to confirm by ≥ 1σ of its rolling noise. Require ≥ 20-bar window. *(Lillo-Farmer; Bouchaud et al.)*
7. **MS-07 HawkesBranchingCritical.** Fire when 2-dim Hawkes same-side branching ratio ≥ 0.85 AND price within 5 ticks of L: breakout imminent. Inverse rule: cross-excitation ratio > same-side = two-sided, level holds. *(Bacry-Muzy; Haghighi et al.)*
8. **MS-08 SpoofSuppressor.** VETO any absorption signal when > 60% of resting size on the "absorbing" side has mean order lifetime < 500 ms and cancel rate > 90% over last 30s. *(Cartea-Jaimungal; CFTC corpus.)*
9. **MS-09 AggressorDominanceAtL.** Fire when in a ±2-tick band around L, aggressor-side volume share over last 30s exceeds 0.75, regardless of price change. Pair with MS-01 for absorption, or with breakout for exhaustion dominance. *(Databento MBO native; Lee-Ready unnecessary.)*
10. **MS-10 RoundNumberProximity.** Modifier signal — boost weight of MS-01..MS-07 by 1.25× when L is a round number (NQ: every 25, 50, 100 points) due to documented order clustering. *(Bloomfield-Chin-Craig 2024; tradeciety empirical.)*
11. **MS-11 DepthAsymmetry.** Fire when cumulative depth within 5 ticks on one side exceeds the other by ≥ 3× AND the thick side faces the price approach. Strong side wins per Cont-de Larrard queue depletion. *(Cont-Stoikov-Talreja; Cont-de Larrard.)*
12. **MS-12 ExhaustionPostBreak.** Fire when price crosses L, Hawkes same-side excitation decays by ≥ 50% within 2 minutes, and aggressor-dominance reverts to ≤ 55%. Classic failed breakout setup. *(Bacry-Muzy decay kernels.)*

---

## Full Citation Table

| # | Paper | Year | Venue | Key finding | Confidence |
|---|---|---|---|---|---|
| 1 | Hautsch & Huang — On the Dark Side of the Market | 2012 | SFB 649 DP / SSRN 2004231 | Hidden liquidity position predictable from observable book state | HIGH |
| 2 | Frey & Sandås — Impact of Iceberg Orders in LOBs | 2017 | *Quarterly J. of Finance* 7(3) | Iceberg presence increases fill probability; real liquidity | HIGH |
| 3 | Zotikov — CME Iceberg Order Detection | 2019 | arXiv:1909.09495 | Replenishment-pattern classifier >90% precision on CME | HIGH |
| 4 | Cebiroğlu & Horst — Optimal Display of Iceberg Orders | 2015 | *J. Economic Dynamics & Control* | Optimal display size balances detection risk vs execution | MED |
| 5 | Lajbcygier et al. — Who can see the iceberg's peak? | 2025 | *J. Financial Research* | Icebergs used by both informed and liquidity traders | MED |
| 6 | Cont, Stoikov & Talreja — Stochastic Model for LOB Dynamics | 2010 | *Operations Research* | Markovian LOB queueing model | HIGH |
| 7 | Cont & de Larrard — Price Dynamics Markovian LOB | 2013 | *SIAM J. Fin. Math.* | Next move sign ← thinner queue side | HIGH |
| 8 | Cont, Kukanov & Stoikov — Price Impact of Order Book Events | 2014 | *J. Financial Econometrics* 12(1), 47-88 | Δprice ≈ β·OFI, β ∝ 1/depth | HIGH |
| 9 | Lipton, Pesavento & Sotiropoulos — Trade arrival & quote imbalance | 2013 | arXiv:1312.0514 | Closed-form up/down probability from queue state | HIGH |
| 10 | Gould & Bonart — Queue Imbalance as One-Tick-Ahead Predictor | 2016 | *Market Microstructure & Liquidity*, arXiv:1512.03492 | QI predicts next mid move with 55-65% binary accuracy | HIGH |
| 11 | Easley, López de Prado & O'Hara — Flow Toxicity | 2012 | *Review of Financial Studies* 25(5) 1457-1493 | VPIN toxicity metric, volume-time bucketing | HIGH |
| 12 | Easley, López de Prado & O'Hara — Volume Clock | 2012 | *J. Portfolio Management* | Volume-synchronized sampling improves HF inference | HIGH |
| 13 | Andersen & Bondarenko — VPIN and the flash crash | 2014 | *J. Empirical Finance* | VPIN poor flash-crash predictor at 0.99 threshold | HIGH |
| 14 | Abad & Yagüe — From PIN to VPIN | 2012 | *Spanish Rev. of Fin. Econ.* | Overview of toxicity metrics | MED |
| 15 | Kyle — Continuous Auctions and Insider Trading | 1985 | *Econometrica* 53(6) | λ as price-impact-per-order-flow | HIGH |
| 16 | Hasbrouck — Trading Costs and Returns for US Equities | 2009 | *J. Finance* | Signed-√V regression estimator for λ | HIGH |
| 17 | Collin-Dufresne & Fos — Insider Trading & Stochastic Liquidity | 2016 | *J. Finance* | λ varies stochastically with informed flow | HIGH |
| 18 | Eisler, Bouchaud & Kockelkoren — Price Impact of Order Book Events | 2012 | arXiv:0904.0900 | Cancellation impact ≈ market-order impact | HIGH |
| 19 | Lillo & Farmer — Long Memory of Efficient Market | 2004 | *Studies in Nonlinear Dyn. & Econ.* | Signed OF long-memory yet prices efficient | HIGH |
| 20 | Bouchaud, Gefen, Potters & Wyart — Fluctuations and Response | 2004 | *Quantitative Finance* | Passive liquidity adapts to signed flow | HIGH |
| 21 | Lee & Ready — Inferring Trade Direction | 1991 | *J. Finance* | Quote+tick test trade classifier | HIGH |
| 22 | Ellis, Michaely & O'Hara — Accuracy of Trade Classification | 2000 | *JFQA* | EMO rule improves Lee-Ready at inside quotes | HIGH |
| 23 | Chakrabarty, Pascual & Shkilko — Bulk Volume vs Tick vs Lee-Ready | 2015 | *J. Empirical Finance* | BVC competitive at bulk; tick rule good at trade level | HIGH |
| 24 | Jones, Kaul & Lipson — Transactions, volume, and volatility | 1994 | *RFS* | Volume decomposition, frequency of trades matters | HIGH |
| 25 | Cartea, Jaimungal & Wang — Spoofing and Price Manipulation | 2020 | Oxford-Man Institute WP | Optimal spoof strategy + detection conditions | HIGH |
| 26 | Wang — Spoofing LOB Agent-Based Model | 2017 | AAMAS Proceedings | Spoofing viable when detection is imperfect | MED |
| 27 | Martínez-Miranda et al. — Order flow & cancellation prediction | 2019 | *High Frequency* (Wiley) | Cancellation-pattern features for manipulation detection | MED |
| 28 | Bacry, Mastromatteo & Muzy — Hawkes Processes in Finance | 2015 | *Market Microstructure & Liquidity*, arXiv:1502.04592 | Comprehensive Hawkes LOB survey; branching ratio near 1 | HIGH |
| 29 | Bacry & Muzy — Hawkes model for price & trades | 2014 | arXiv:1301.1135 | 4-kernel joint price/trade Hawkes; calibrated on Bund | HIGH |
| 30 | Bacry, Delattre, Hoffmann & Muzy — Mutually exciting point processes | 2013 | *Quantitative Finance* | Microstructure noise as Hawkes | HIGH |
| 31 | Haghighi, Fallahpour & Eyvazlu — Order arrivals at price limits | 2016 | *Finance Research Letters* | Hawkes kernel shifts at price-limit events | MED |
| 32 | Morariu-Patrichi & Pakkanen — Order Book Queue Hawkes | 2022 | *SIAM J. Fin. Math.* | State-dependent Hawkes with queue feedback | HIGH |
| 33 | Bloomfield, Chin & Craig — Allure of Round Number Prices | 2024 | Georgetown CRI WP | $850M/yr wealth transfer from round-number bias | MED |
| 34 | Johnson — Round Numbers and Security Returns | — | Working paper | Empirical abnormal returns near round numbers | LOW |
| 35 | CFTC Spoofing Corpus — 204 cases | 2025 | *Capital Markets Law Journal*, Oxford | Operational patterns across CFTC/CME/ICE enforcement | HIGH |

---

## Key takeaways for DEEP6

1. **Absorption now has a microstructure definition**, not just a Wyckoff one: aggressor-volume / Δticks at a level, filtered by spoof detector, confirmed by QI-band divergence across depth and falling VPIN. This is implementable.
2. **Databento MBO aggressor flags make Lee-Ready obsolete** for your pipeline — skip the classifier layer.
3. **VPIN is a regime indicator, not a threshold trigger** — its *change* around a level is what matters, and canonical 0.99 thresholds have weak academic support (Andersen-Bondarenko 2014).
4. **Spoof detection is a hard prerequisite** for absorption signals — Eisler-Bouchaud show cancellation impact is nearly as large as market-order impact, so walls that vanish dominate walls that hold in naive feature engineering. MS-08 is a veto, not a score.
5. **Hawkes branching ratio** is the cleanest single indicator of "level about to break" (branching → 1, same-side dominant) vs "level holding" (cross-excitation dominant). Fit it on a dedicated thread, update every 5-10s.
6. **Round-number level weighting is empirically justified** (Bloomfield-Chin-Craig $850M/yr finding) — MS-10 should not be dismissed as folklore.

**Confidence summary:** HIGH on imbalance, trade classification, Hawkes, iceberg detection, and Eisler-Bouchaud impact decomposition. MEDIUM on VPIN thresholds (contrary evidence) and round-number quantitative effect size. LOW on academic treatment of CVD divergence specifically — practitioner-dominant; rely on Lillo-Farmer long-memory framing instead.
