# Academic Papers Index

**Last verified: 2026-05-12**
**Scope:** Academic citations found in DEEP6 research files. Each entry includes the key finding relevant to DEEP6 and which signals or concepts it supports. All citations sourced from `.planning/research/pine/deep/microstructure.md` and related phase research files.

---

## Iceberg / Hidden Liquidity

## Hautsch & Huang (2012): On the Dark Side of the Market

**Full Title**: On the Dark Side of the Market: Identifying and Analyzing Hidden Order Placements
**Source**: SFB 649 Discussion Paper / SSRN 2004231
**Key Finding**: Hidden liquidity concentrates where the observable book state predicts it. Tight visible spreads, thin visible depth, and recent adverse price movement all raise the Bayesian posterior that an iceberg is present.
**DEEP6 Relevance**: Supports MS-02 (IcebergAtLevel). Provides the theoretical basis for detecting icebergs from observable book state rather than requiring direct visibility of hidden orders.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 1

---

## Frey & Sandås (2017): Impact of Iceberg Orders in Limit Order Books

**Full Title**: The Impact of Iceberg Orders in Limit Order Books
**Source**: Quarterly Journal of Finance, Vol. 7, No. 3
**Key Finding**: Iceberg presence increases subsequent fill probability at the level — icebergs represent real liquidity, not withdrawal. The execution-replenishment signature is detectable from the MBO tape.
**DEEP6 Relevance**: Supports MS-02 (IcebergAtLevel). Confirms that iceberg detection is actionable — detected icebergs are genuine defenders, not noise.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 1

---

## Zotikov (2019): CME Iceberg Order Detection and Prediction

**Full Title**: CME Iceberg Order Detection and Prediction
**Source**: arXiv:1909.09495
**Key Finding**: Replenishment-pattern classifier achieves >90% precision detecting iceberg slices on CME when the replenishment gap is <100ms and size equals the prior displayed tranche within ±1 lot. Hidden-Volume-Ratio (HVr) ≥ 2.0 over a 60-second window is the operational threshold.
**DEEP6 Relevance**: Directly implements MS-02 (IcebergAtLevel). The HVr ≥ 2.0 threshold and Zotikov replenishment event detection are the core of the iceberg signal.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 1, Detection Algorithms table

---

## Cebiroğlu & Horst (2015): Optimal Display of Iceberg Orders

**Full Title**: Optimal Display of Iceberg Orders
**Source**: Journal of Economic Dynamics and Control
**Key Finding**: Optimal display size balances detection risk against execution probability. Institutions choose display sizes that minimize detection while maximizing fill rates.
**DEEP6 Relevance**: Contextualizes why icebergs are hard to detect and why the Zotikov replenishment signature is the most reliable detection method.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 1

---

## Lajbcygier et al. (2025): Who Can See the Iceberg's Peak?

**Full Title**: Who can see the iceberg's peak?
**Source**: Journal of Financial Research
**Key Finding**: Icebergs are used by both informed and liquidity traders — not exclusively by informed participants. This complicates the interpretation of iceberg detection as a pure informed-flow signal.
**DEEP6 Relevance**: Caution for MS-02 — iceberg detection alone does not confirm informed flow direction. Must be combined with VPIN and aggressor-side analysis.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 1

---

## LOB Pressure and Imbalance

## Cont, Stoikov & Talreja (2010): A Stochastic Model for Order Book Dynamics

**Full Title**: A Stochastic Model for Order Book Dynamics
**Source**: Operations Research
**Key Finding**: Markovian LOB queueing model. Queue depletion events determine next price move direction — the thinner queue side determines which way price moves when a queue empties.
**DEEP6 Relevance**: Supports MS-11 (DepthAsymmetry) and MS-03 (QueueImbalanceBand). The formal basis for using queue depth asymmetry as a directional predictor.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 2

---

## Cont & de Larrard (2013): Price Dynamics in a Markovian Limit Order Market

**Full Title**: Price Dynamics in a Markovian Limit Order Market
**Source**: SIAM Journal on Financial Mathematics
**Key Finding**: Conditional on a queue depletion event, next mid-price move sign is determined by which side's queue is thinner. Expected time-to-move is proportional to queue size divided by arrival rate.
**DEEP6 Relevance**: Supports MS-11 (DepthAsymmetry). Provides the closed-form basis for the depth asymmetry signal — the thick side wins per queue depletion mechanics.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 2

---

## Cont, Kukanov & Stoikov (2014): The Price Impact of Order Book Events

**Full Title**: The Price Impact of Order Book Events
**Source**: Journal of Financial Econometrics, 12(1), 47–88
**Key Finding**: Short-horizon price change ≈ β × OFI (Order Flow Imbalance), with β proportional to 1/market depth. OFI dominates signed volume as the correct regressor for price impact.
**DEEP6 Relevance**: Supports MS-03 (QueueImbalanceBand) and the general OFI-based signal framework. Establishes that depth-normalized imbalance is the right measure, not raw signed volume.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 2

---

## Lipton, Pesavento & Sotiropoulos (2013): Trade Arrival Dynamics and Quote Imbalance

**Full Title**: Trade arrival dynamics and quote imbalance in a limit order book
**Source**: arXiv:1312.0514
**Key Finding**: Closed-form relative probability of up-tick vs down-tick as a function of (Q_bid, Q_ask). Trade arrival intensity itself rises with imbalance magnitude.
**DEEP6 Relevance**: Supports MS-03 (QueueImbalanceBand). Provides the closed-form probability model underlying queue imbalance signals.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 2

---

## Gould & Bonart (2016): Queue Imbalance as a One-Tick-Ahead Price Predictor

**Full Title**: Queue Imbalance as a One-Tick-Ahead Price Predictor in a Limit Order Book
**Source**: Market Microstructure and Liquidity / arXiv:1512.03492
**Key Finding**: Queue imbalance QI = (Q_bid − Q_ask) / (Q_bid + Q_ask) predicts next mid move with 55–65% binary accuracy for large-tick instruments. |QI| ≥ 0.6 at top-of-book with minimum combined size ≥ median gives reliable directional signal; |QI| ≥ 0.8 is a high-confidence regime.
**DEEP6 Relevance**: Directly implements MS-03 (QueueImbalanceBand). The |QI| ≥ 0.6 threshold is the operational parameter for the queue imbalance signal.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 2, Detection Algorithms table

---

## VPIN and Flow Toxicity

## Easley, López de Prado & O'Hara (2012): Flow Toxicity and Liquidity

**Full Title**: Flow Toxicity and Liquidity in a High Frequency World
**Source**: Review of Financial Studies, 25(5), 1457–1493
**Key Finding**: VPIN (Volume-Synchronized Probability of Informed Trading) = E[|V_buy − V_sell|] / V_bucket, computed in volume time. Elevated VPIN indicates toxic (informed) flow that adversely selects passive liquidity providers. VPIN reached historical highs one hour before the May 6, 2010 flash crash.
**DEEP6 Relevance**: Supports MS-04 (VPINRegimeShift). The VPIN engine in DEEP6 uses this paper's volume-clock bucketing methodology. The regime shift (change in VPIN) around a level is more actionable than the absolute VPIN level.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 3; `.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-RESEARCH.md`

---

## Easley, López de Prado & O'Hara (2012): The Volume Clock

**Full Title**: The Volume Clock: Insights into the High-Frequency Paradigm
**Source**: Journal of Portfolio Management
**Key Finding**: Volume-synchronized sampling improves high-frequency inference. Volume time (buckets of fixed volume) is more stationary than clock time for financial data.
**DEEP6 Relevance**: Supports the VPIN engine's volume-clock bucketing approach. Establishes why volume time is preferred over clock time for toxicity measurement.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 3; `.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-RESEARCH.md`

---

## Andersen & Bondarenko (2014): VPIN and the Flash Crash

**Full Title**: VPIN and the flash crash
**Source**: Journal of Empirical Finance
**Key Finding**: VPIN is a poor short-run volatility predictor at the canonical 0.99 threshold. VPIN actually peaked after the flash crash, not before. The 0.99 threshold has weak empirical support.
**DEEP6 Relevance**: Critical caveat for MS-04. DEEP6 uses VPIN as a regime indicator (change in VPIN around a level), not as a threshold trigger. The canonical 0.99 threshold is explicitly rejected in favor of instrument-calibrated thresholds (0.70 elevated, 0.85 toxic).
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 3

---

## Abad & Yagüe (2012): From PIN to VPIN

**Full Title**: From PIN to VPIN: an introduction to order flow toxicity
**Source**: Spanish Review of Financial Economics
**Key Finding**: Overview of the evolution from PIN (Probability of Informed Trading) to VPIN. Establishes the conceptual lineage and key differences between the two metrics.
**DEEP6 Relevance**: Background context for the VPIN implementation. Confirms VPIN as the operationally superior metric for high-frequency environments.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 3

---

## Price Impact and Kyle's Lambda

## Kyle (1985): Continuous Auctions and Insider Trading

**Full Title**: Continuous Auctions and Insider Trading
**Source**: Econometrica, 53(6)
**Key Finding**: Introduced λ (lambda) as the price change per unit of signed order flow — the fundamental price impact parameter. In equilibrium, informed traders optimally spread their orders to minimize detection.
**DEEP6 Relevance**: Supports MS-05 (KyleLambdaCompression). Kyle's λ is the theoretical basis for measuring price impact at levels. A falling λ at a level indicates absorption (cheap liquidity); a rising λ indicates toxic flow.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 4

---

## Hasbrouck (2009): Trading Costs and Returns for US Equities

**Full Title**: Trading Costs and Returns for US Equities
**Source**: Journal of Finance
**Key Finding**: Signed-√dollar-volume regression is the standard estimator for Kyle's λ. λ rises during toxic flow episodes and falls during benign two-sided flow.
**DEEP6 Relevance**: Supports MS-05 (KyleLambdaCompression). Provides the Welford online regression estimator approach for computing rolling λ in the DEEP6 hot path.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 4, Detection Algorithms table

---

## Collin-Dufresne & Fos (2016): Insider Trading and Stochastic Liquidity

**Full Title**: Insider Trading, Stochastic Liquidity and Equilibrium Prices
**Source**: Journal of Finance
**Key Finding**: λ varies stochastically with informed flow — it is not a constant. Liquidity is endogenous to the information environment.
**DEEP6 Relevance**: Supports the dynamic λ estimation in MS-05. Confirms that λ must be estimated on a rolling basis, not treated as a fixed parameter.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 4

---

## Eisler, Bouchaud & Kockelkoren (2012): Price Impact of Order Book Events

**Full Title**: The Price Impact of Order Book Events: Market Orders, Limit Orders and Cancellations
**Source**: arXiv:0904.0900
**Key Finding**: Cancellation impact is nearly as large as market-order impact. This is the first-principles reason spoofing works — large cancellations move price almost as much as large market orders.
**DEEP6 Relevance**: Supports MS-08 (SpoofSuppressor) and the formal absorption definition. The Eisler-Bouchaud decomposition provides the mathematical basis for the absorption z-score: limit-order arrivals on the passive side cancel the impact of market-order arrivals from aggressors.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Sections 4, 7, 8

---

## CVD and Signed Order Flow

## Lillo & Farmer (2004): The Long Memory of the Efficient Market

**Full Title**: The long memory of the efficient market
**Source**: Studies in Nonlinear Dynamics and Econometrics
**Key Finding**: Signed order flow has long memory (Hurst exponent ≈ 0.7) yet prices are close to efficient — because passive liquidity adjusts to absorb persistent flow. When price fails to follow persistent signed flow, the passive side is actively accommodating (absorption).
**DEEP6 Relevance**: Supports MS-06 (CVDDivergenceAtLevel). Provides the rigorous microstructure basis for CVD divergence — the "effort vs. result" mismatch has a formal long-memory explanation.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 5

---

## Bouchaud, Gefen, Potters & Wyart (2004): Fluctuations and Response in Financial Markets

**Full Title**: Fluctuations and response in financial markets: the subtle nature of 'random' price changes
**Source**: Quantitative Finance
**Key Finding**: Passive liquidity adapts to absorb persistent signed flow. The market impact of a trade decays over time as liquidity providers adjust their quotes.
**DEEP6 Relevance**: Supports MS-06 (CVDDivergenceAtLevel). Confirms the Lillo-Farmer finding from a different angle — persistent flow is absorbed, not followed, by efficient markets.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 5

---

## Trade Classification

## Lee & Ready (1991): Inferring Trade Direction from Intraday Data

**Full Title**: Inferring Trade Direction from Intraday Data
**Source**: Journal of Finance
**Key Finding**: Quote test first (trade above/below midpoint → buyer/seller-initiated); tick test at midpoint. Accuracy ≈ 85% in equities; degrades in high-velocity environments.
**DEEP6 Relevance**: Historical context only. Databento MBO provides native aggressor flags, making Lee-Ready obsolete for DEEP6. The paper is cited to explain why DEEP6 does NOT use Lee-Ready.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 6

---

## Ellis, Michaely & O'Hara (2000): Accuracy of Trade Classification Rules

**Full Title**: The Accuracy of Trade Classification Rules: Evidence from Nasdaq
**Source**: Journal of Financial and Quantitative Analysis
**Key Finding**: EMO rule improves Lee-Ready at inside-quote trades. Bulk Volume Classification (BVC) is competitive at the bulk level.
**DEEP6 Relevance**: Historical context. DEEP6 uses Databento MBO native aggressor flags instead of any classification algorithm. BVC is used in the VPIN reference implementation but replaced with exact aggressor split in DEEP6's port.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 6; `.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-RESEARCH.md`

---

## Chakrabarty, Pascual & Shkilko (2015): Evaluating Trade Classification Algorithms

**Full Title**: Evaluating trade classification algorithms: Bulk volume classification vs. tick rule vs. Lee-Ready
**Source**: Journal of Empirical Finance
**Key Finding**: BVC is competitive with tick rule at bulk level; tick rule is good at trade level. All algorithms degrade in high-velocity environments.
**DEEP6 Relevance**: Confirms the decision to use Databento MBO native aggressor flags rather than any classification algorithm. At 1,000 callbacks/sec, classification accuracy of any algorithm is insufficient.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 6

---

## Stopping Volume and Absorption

## Jones, Kaul & Lipson (1994): Transactions, Volume, and Volatility

**Full Title**: Transactions, volume, and volatility
**Source**: Review of Financial Studies
**Key Finding**: Volume decomposition — frequency of trades matters more than size of trades for volatility. High trade frequency with small price change is the signature of absorption.
**DEEP6 Relevance**: Supports MS-01 (AbsorptionZ). The formal basis for the absorption metric: high aggressor volume with small price change = absorption.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 7

---

## Spoofing and Manipulation

## Cartea, Jaimungal & Wang (2020): Spoofing and Price Manipulation in Order Driven Markets

**Full Title**: Spoofing and Price Manipulation in Order Driven Markets
**Source**: Oxford-Man Institute Working Paper
**Key Finding**: Optimal spoof strategy and detection conditions. Spoof orders are placed just outside the BBO, canceled with probability >> 0.9 before execution. Detection features: order-to-trade ratio > 10:1, order lifetime < 500ms, size asymmetry > 3×.
**DEEP6 Relevance**: Directly implements MS-08 (SpoofSuppressor). The detection features (lifetime < 500ms, cancel rate > 90%, size asymmetry) are the operational parameters for the spoof veto signal.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 8

---

## Wang (2017): Spoofing the Limit Order Book: An Agent-Based Model

**Full Title**: Spoofing the Limit Order Book: An Agent-Based Model
**Source**: AAMAS Proceedings
**Key Finding**: Spoofing is viable when detection is imperfect. Agent-based simulation confirms the Cartea-Jaimungal analytical results.
**DEEP6 Relevance**: Supports MS-08 (SpoofSuppressor). Confirms that spoof detection is necessary — without it, absorption signals will be contaminated by spoof walls.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 8

---

## Martínez-Miranda et al. (2019): Order Flow Dynamics for Prediction of Order Cancellation

**Full Title**: Order flow dynamics for prediction of order cancelation
**Source**: High Frequency (Wiley)
**Key Finding**: Cancellation-pattern features (burst arrival, short lifetime, size asymmetry) are predictive of manipulation. Order lifetime distribution is bimodal: real orders have long or filled lifetimes; spoofs have very short (<500ms) cancellations.
**DEEP6 Relevance**: Supports MS-08 (SpoofSuppressor). The bimodal lifetime distribution is the key feature for distinguishing genuine walls from spoof walls.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 8

---

## CFTC Spoofing Enforcement Corpus (2025)

**Full Title**: 204 cases across CFTC/CME/ICE spoofing enforcement
**Source**: Capital Markets Law Journal (Oxford), 2025
**Key Finding**: Operational patterns across 204 enforcement cases. Spoofs cluster approaching round numbers and prior-day extremes. Genuine walls have slow arrivals, long mean lifetime, and fills contribute to price stall.
**DEEP6 Relevance**: Supports MS-08 (SpoofSuppressor) and MS-10 (RoundNumberProximity). Confirms that round numbers are the primary spoofing targets — the spoof suppressor must be especially active near round numbers.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 8

---

## Hawkes Processes

## Bacry, Mastromatteo & Muzy (2015): Hawkes Processes in Finance

**Full Title**: Hawkes Processes in Finance
**Source**: Market Microstructure and Liquidity / arXiv:1502.04592
**Key Finding**: Comprehensive Hawkes LOB survey. Trade arrivals are self- and mutually exciting. Empirically, the branching ratio ‖Φ‖ → 1 (near critical) — 70–85% of trades are triggered by prior trades, not exogenous news.
**DEEP6 Relevance**: Supports MS-07 (HawkesBranchingCritical). The branching ratio is the cleanest single indicator of "level about to break" (branching → 1, same-side dominant) vs "level holding" (cross-excitation dominant).
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 9

---

## Bacry & Muzy (2014): Hawkes Model for Price and Trades High-Frequency Dynamics

**Full Title**: Hawkes model for price and trades high-frequency dynamics
**Source**: arXiv:1301.1135
**Key Finding**: 4-kernel joint price/trade Hawkes model calibrated on Bund futures. Same-side excitation and cross-excitation have distinct roles in price dynamics.
**DEEP6 Relevance**: Supports MS-07 (HawkesBranchingCritical). The 2-dimensional Hawkes (buys, sells) model used in DEEP6 is based on this paper's framework.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 9

---

## Bacry, Delattre, Hoffmann & Muzy (2013): Mutually Exciting Point Processes

**Full Title**: Modelling microstructure noise with mutually exciting point processes
**Source**: Quantitative Finance
**Key Finding**: Microstructure noise can be modeled as a Hawkes process. Mutual excitation between buy and sell arrivals captures the bid-ask bounce.
**DEEP6 Relevance**: Background context for the Hawkes implementation. Confirms the mutual excitation structure used in MS-07.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 9

---

## Haghighi, Fallahpour & Eyvazlu (2016): Order Arrivals at Price Limits Using Hawkes Processes

**Full Title**: Modelling order arrivals at price limits using Hawkes processes
**Source**: Finance Research Letters
**Key Finding**: At price limits, the Hawkes kernel parameters shift — same-direction excitation strengthens, opposite-direction excitation weakens. This is a formal breakout-acceleration model.
**DEEP6 Relevance**: Directly supports MS-07 (HawkesBranchingCritical). The level-specific Hawkes kernel shift is the theoretical basis for using branching ratio changes near structural levels as breakout predictors.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 9

---

## Morariu-Patrichi & Pakkanen (2022): Order Book Queue Hawkes Markovian Modeling

**Full Title**: Order Book Queue Hawkes Markovian Modeling
**Source**: SIAM Journal on Financial Mathematics
**Key Finding**: State-dependent Hawkes model with queue feedback. The branching ratio depends on the current queue state, not just the history of arrivals.
**DEEP6 Relevance**: Advanced context for MS-07. The state-dependent extension is a potential future enhancement to the DEEP6 Hawkes implementation.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 9

---

## Round Numbers

## Bloomfield, Chin & Craig (2024): Allure of Round Number Prices

**Full Title**: Allure of Round Number Prices
**Source**: Georgetown CRI Working Paper
**Key Finding**: Round-number prices show anomalous order clustering and transaction costs. Estimated $850M/year wealth transfer from round-number bias. Empirical evidence of abnormal returns near round numbers.
**DEEP6 Relevance**: Supports MS-10 (RoundNumberProximity). The $850M/year finding justifies the 1.25× weight boost for signals at round numbers (NQ: every 25, 50, 100 points). Round-number level weighting is empirically justified, not folklore.
**DEEP6 Reference**: `.planning/research/pine/deep/microstructure.md` — Section 4, MS-10 rule

---

## Auction Theory and Market Profile

## Dalton, J.F. (2013): Mind Over Markets

**Full Title**: Mind Over Markets: Power Techniques for Consistent Profits
**Source**: Wiley (revised edition, 2013; original 1990)
**Key Finding**: Auction Market Theory framework. Six day types, five open types, value-area relationships, and Initial Balance framework. The 70–75% failed IB extension reversal probability is the most cited quantitative claim.
**DEEP6 Relevance**: Foundational framework for the level classification system. Day-type and open-type classification feed into the DEEP6 trade-plan generator (15 trade-plan generators in auction_theory.md). IB width classification drives the IB multiplier in the scorer.
**DEEP6 Reference**: `.planning/research/pine/deep/auction_theory.md` — Sections 2, 3, 6

---

## Dalton, J.F. (2007): Markets in Profile

**Full Title**: Markets in Profile: Profiting from the Auction Process
**Source**: Wiley, 2007
**Key Finding**: Opening relationship framework (Higher Value/Higher Price, Lower Value/Lower Price, etc.). Naked POC magnet behavior (~80% retest rate). Value migration as the primary daily bias signal.
**DEEP6 Relevance**: Supports the value-area relationship classifier and naked POC magnet logic in the DEEP6 level registry. The ~80% nPOC retest rate is used as a prior for the naked POC magnet trade-plan generator.
**DEEP6 Reference**: `.planning/research/pine/deep/auction_theory.md` — Sections 3, 4, 5

---

## Steidlmayer, J.P. (2003): Steidlmayer on Markets

**Full Title**: Steidlmayer on Markets: Trading with Market Profile
**Source**: Wiley (revised edition, 2003; original 1989)
**Key Finding**: Original Market Profile framework. Price as an advertising mechanism; value as the zone where time and volume accumulate. TPO graph as the instrument for making auction structure visible.
**DEEP6 Relevance**: Foundational theory for the Market Profile integration. The TPO-based day-type classification and value-area definitions trace directly to Steidlmayer.
**DEEP6 Reference**: `.planning/research/pine/deep/auction_theory.md` — Section 1

---

## Alexander, T. (2009): Practical Trading Applications of Market Profile

**Full Title**: Practical Trading Applications of Market Profile
**Source**: Alexander Trading (eBook)
**Key Finding**: Market Profile provides context (WHERE to trade); order flow / footprint provides trigger (WHEN to trade). Signals are meaningless without structural context.
**DEEP6 Relevance**: The synthesis principle underlying DEEP6's entire architecture — 44 signals are evaluated conditionally at MP-defined levels, not in isolation. This is the core design philosophy.
**DEEP6 Reference**: `.planning/research/pine/deep/auction_theory.md` — Section 7; `.planning/research/pine/deep/practitioners.md`

---

## Confidence Summary

| Domain | Confidence | Notes |
|--------|-----------|-------|
| Iceberg detection (Zotikov, Hautsch-Huang, Frey-Sandås) | HIGH | Directly implementable; CME-specific results |
| LOB imbalance (Cont-Kukanov-Stoikov, Gould-Bonart) | HIGH | Quantitative thresholds verified |
| VPIN (Easley et al.) | HIGH for methodology; LOW for canonical thresholds | Andersen-Bondarenko contrary evidence; use regime shift, not absolute threshold |
| Kyle's lambda (Hasbrouck) | HIGH | Standard estimator; rolling implementation verified |
| Eisler-Bouchaud decomposition | HIGH | Cancellation impact finding is foundational for spoof detection |
| Lillo-Farmer long memory | HIGH | Formal basis for CVD divergence |
| Hawkes processes (Bacry-Muzy) | HIGH | Branching ratio is the cleanest level-break predictor |
| Spoofing (Cartea-Jaimungal, CFTC corpus) | HIGH | Detection features are operational |
| Round numbers (Bloomfield-Chin-Craig) | MEDIUM | Working paper; $850M figure is striking but not peer-reviewed |
| Auction theory (Dalton, Steidlmayer) | HIGH for framework; MEDIUM for exact probabilities | Probability figures (70-75% failed extension) are educator-derived, not primary text |

---

*Last verified: 2026-05-12*
