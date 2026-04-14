# Practitioner Orderflow Deep Research — Reading Footprint AT Levels

**Date:** 2026-04-13
**Scope:** How elite orderflow practitioners turn footprint patterns at specific levels into trade decisions. Complements prior DEEP6 research on vendors (SpotGamma/MenthorQ/Volland) and academic literature (Barbon-Buraschi, Baltussen) — does not duplicate.
**Target use:** DEEP6 rule engine design for NQ auto-execution.

---

## 1. Pattern Library

Every pattern below is actionable only at a level. "Level" = VPOC, VAH, VAL, LVN, prior-day H/L, overnight H/L, IB H/L, gamma wall, call/put wall, gamma flip, or swing pivot.

| Pattern | Visual Signature (footprint) | Microstructure Meaning | Actionable AT | Noise AT | Entry Trigger | Stop | Target | Invalidation |
|---|---|---|---|---|---|---|---|---|
| **Absorption (passive)** | Large ask/bid prints at one price, price fails to advance; repeated fills at same level; delta grows while price stalls | Limit orders eating aggressive market orders; large passive defender | VAH/VAL, prior-day H/L, gamma wall, LVN edge | Middle of balance; random intra-bar | Absorbing side flips — offer lifts / bid swept after absorption count ≥ 3 bars | 1 tick beyond absorption price | Opposite VA edge or VPOC | Absorbing price breaks WITH aggression (not drift) |
| **Exhaustion** | Wide-range bar, extreme delta, thin print at extreme, next bar fails to extend | Last aggressive participants filled; no fuel left | Prior-day extremes, LVN terminus, gamma wall tag | Mid-range | Reversal bar closes back inside prior bar's range | Beyond exhaustion extreme | VPOC / prior VAL/VAH | Next bar extends exhaustion direction |
| **Stacked Imbalance** | 3+ consecutive diagonal buy-or-sell imbalances (ask ≥ 3× bid at consecutive prices, or inverse) | Sustained one-sided aggression across price ladder | Breakout FROM level (VAH break, call-wall break) | At level with reversal context (can be bull trap) | Retest of the stack from the "correct" side | Below/above stack base | Next structural level | Stack prices re-visited AND absorbed from opposite side |
| **Unfinished Auction / Single Print** | Bar extreme prints volume on ONE side only (e.g., 56×0 at high); "unfinished business" | Auction did not find the opposing participant; magnet for re-test | Session extremes, weekly extremes | Mid-range extremes | Trade TOWARD the unfinished level (as target, not entry) | N/A (target logic) | The unfinished price | Level completed by a two-sided print |
| **Delta Divergence** | Price makes new high with lower delta, or new low with higher delta | Aggressive side is thinning; passive side quietly accumulating | Retest of prior-day H/L, second touch of VAH/VAL | Trend-day middle | Next bar rejection candle + opposite delta flip | Beyond divergence extreme | Prior swing / VPOC | New delta high/low confirms direction |
| **Delta Tails** (Valtos) | Bar with heavy delta at extreme but price closed far away | Rejection — aggressive side got filled then reversed | VAH/VAL, prior session extremes | Middle of range | Fade the tail direction on next bar | Beyond tail | Mid-bar / opposite end | Price re-prints through the tail |
| **Delta Flip** | Sign of cumulative delta changes from + to − (or inverse) at a level | Control transferring from buyers to sellers | At tested level during retest | Randomly in trend | Flip confirmed + level holds | Beyond level | Next VA edge |Flip reverses back |
| **Iceberg (suspected)** | Same price refills repeatedly; 3+ passive absorption events at one price | Hidden large resting order | Support/resistance, gamma wall | N/A — always structural | Fade iceberg while holding; reverse to trend if it breaks | 1-2 ticks beyond iceberg | Opposite VA | Iceberg disappears AND opposite market orders hit size (Jigsaw rule) |
| **Stopping Volume** | Wide bar with extreme delta at LOW (bull stop) or HIGH (bear stop) followed by opposite bar closing beyond | Capitulation → absorbed by opposing side | Prior-day low, VAL, gamma put-wall | Middle of trend | Confirmation bar closes beyond stopping bar | Beyond stopping extreme | VPOC | Third bar extends stopping direction |
| **Effort vs Result (Wyckoff)** | High volume + small price change (effort, no result) | Absorption by opposing passive | All structural levels | No-volume rotations | Fade on next bar's rejection | Beyond effort bar | POC | Effort sustained with result next bar |
| **Sweep / Stop Run** | Single-bar wick through prior H/L, snap-back close inside | Liquidity grab; stops triggered then faded | Prior-day H/L, overnight H/L, equal highs/lows | Random extensions | Close back inside + opposite delta print | Beyond sweep extreme + ATR buffer | Mid-range / opposite level | Price accepts beyond sweep (close outside) |
| **P-shape profile (intraday forming)** | TPOs stack vertically left, thin upper range | Strong one-timeframe buyer conviction | Trend day from open | Balance days | Pullback into VPOC holds | Below VAL | Upper single prints | VPOC breaks down |
| **b-shape profile** | Mirror: TPOs stack right, thin lower | Strong seller conviction | Trend day from open | Balance | Pullback to VPOC holds | Above VAH | Lower single prints | VPOC breaks up |
| **LVN Gap-through** | Fast traverse of low-volume node with stacked imbalances | Price found no interest at LVN — goes to next HVN | LVN between VPOC and opposite VA | Inside value | Pullback that halts mid-LVN | Back inside originating VA | Next HVN | Price re-enters LVN fully |
| **Spoofing footprint** | Large DOM size that never trades; pulls as price approaches | Manipulation; not real intent | Near round numbers, session opens | N/A — always suspicious | Wait for actual trade; fade the spoof direction if hard reversal | Beyond spoof price | Mean | Size actually trades |

Sources for pattern definitions: Axia Futures blog (Footprint Edge course); Jigsaw Trading Lesson 1/11; Bookmap absorption/iceberg docs; ATAS unfinished auction guide; Valtos Orderflows Encyclopedia (128 setups, 34 delta + 22 imbalance); TradingView volume-footprint guide; Trader Dale stacked imbalance guides; Wyckoff effort-vs-result (Villahermosa). See §6 Sources.

---

## 2. Practitioner Rulebooks

### 2.1 Axia Futures — "The Footprint Edge" (Alex Haywood / Richard Bailey)

35.5-hour course, 10 named strategies. Core strategy is **Absorption and Auctioning**.

**The Three Clues framework** — required conditions for a high-risk-reward absorption reversal trade at a reference area:

1. "Good absorption happens first" — a reference area is confirmed by buyer interest.
2. "The reference block gets defended on the retest by buyers."
3. "No selling pressure stepping in on the retest."

When all three align the trader takes the long. Verbatim framing paraphrased from Axia's blog ([Three Trading Techniques](https://axiafutures.com/blog/three-trading-techniques-using-footprint/) and [Absorption Order Flow Eurostoxx](https://axiafutures.com/blog/absorption-order-flow-eurostoxx/)).

**Eurostoxx example (verbatim rules extracted):**
- "There's very little volume traded" above a level vs. heavy volume below — marks the reference area.
- Wait for "two-way trading around this area" (absorption phase).
- Entry: buyers "lift the offers up" repeatedly after sellers push lower.
- Invalidation: "coming down below [the low-volume patch] should be a clear sign that buyers back off."

**JUMP technique (NASDAQ-specific):** market crosses marked resistance, triggers stops, "jumps after two short rotations" creating an LVN. Entry on retest of the LVN with HVN above it.

### 2.2 Jigsaw Trading — Peter Davies

**Three components of a reversal** (Davies, *Confirming Levels With Order Flow*, 2013):
1. Absorption
2. One side fading
3. Other side jumping in (stepping up)

All three must be present; any one alone is not enough.

**Iceberg / absorption trade rules (Davies):**
> "Fade all iceberg orders / areas of absorption you see. Fade them if they fail to hold. Fade them if they fail to hold and then opposing market orders come in in size."

Three distinct scenarios — same observation, different playbook depending on what happens next. Entry is 50/50 limit vs market "depending on how the order flow looks" — market orders when he thinks the market "is about to break."

**Absorption definition (Davies):** "bids stay firm in the face of continued selling, often across many prices with icebergs. The more absorption that occurs the better, with delta continuing to increase while price does not."

### 2.3 Bookmap — Absorption, Icebergs, Stops

Detection rules (Bookmap official docs):
- **Absorption:** "repeated execution of trades at a certain price level without a corresponding movement in price."
- **Iceberg confirmation:** "3+ passive absorption events at the same price level" (Institutional Footprint Scanner criterion).
- **Caveat (Bookmap docs):** "It is impossible to visually or programmatically identify native icebergs with certainty" — anyone claiming otherwise cannot distinguish absorption from native icebergs. Treat iceberg signals as probabilistic.

Trade application (Bookmap): observe heatmap for liquidity re-appearance → watch reaction on test → confirm with CVD or aggressive-trade imbalance → plan entry.

### 2.4 Mike Valtos — Orderflows (ex-JPM/Cargill/Commerzbank)

**7 rule-based delta setups** with yes/no entry criteria. Larger encyclopedia has 128 setups.

Key named patterns (all in §1 library): Delta Divergence, Delta Flip, Delta Transition, Delta Tails, Delta Bulges, Delta Reversal, Shrinking Deltas, Delta Doji, Effort No Result, Delta Squeeze, Delta Momentum, Stacked Buy/Sell Imbalances, Extreme Imbalances, Trapped Traders Imbalance, Imbalance Flips, Value Rejection.

Valtos emphasizes the pre-market → live read → 7 entry → post-review loop: setups are not standalone; they must be framed by pre-market level map.

### 2.5 Trader Dale — Stacked Imbalance Rules

Stacked imbalance = 3+ consecutive diagonal imbalances (ask ≥ 3× bid at adjacent prices). Rules:
1. Treat as strong support (buy stack) or resistance (sell stack).
2. Enter on pullback that reaches the stack.
3. Stop just below (buy stack) / above (sell stack) the stack base.
4. Strongest setups combine stack + level confirmation + breakout.

### 2.6 Wyckoff Effort-vs-Result (via Villahermosa, Trading Wyckoff)

Volume = effort, price = result.
- **High volume + small price** = absorption → reversal risk.
- **Low volume + large price** = unsustainable → reversal risk.
- **Harmony** (both align) = continuation.

"All effort, no result" *precedes* reversals or range rotations.

### 2.7 Disagreements Between Practitioners

| Topic | Axia | Jigsaw (Davies) | Bookmap | Valtos |
|---|---|---|---|---|
| Iceberg detection | Actionable via ladder | Actionable, fade rules | Caution: cannot be visually confirmed | Treat as cluster event |
| Entry order type | Limit at level | 50/50 limit/market | Limit preferred | Defined per setup |
| Required confirmations | 3 clues (absorption + defense + no sell) | 3 components (absorb + fade + step-up) | Heatmap + CVD + imbalance | Yes/no binary per setup |
| Single-bar signal | Usually rejects | Requires sequence | Requires re-test | Some setups are single-bar (Delta Tail) |

The agreement: **no single bar is a signal without a level and a sequence**. Point of disagreement: how many confirming observations are required before entry.

---

## 3. Multi-Timeframe Level Hierarchy (Confluence Matrix)

Higher weight = more institutional traffic, longer half-life, more magnet behavior.

| Tier | Level Types | Weight | Half-life |
|---|---|---|---|
| **T1 (macro)** | Weekly H/L, prior-week VPOC, monthly VPOC, gamma flip, largest call/put wall | 5 | Weeks |
| **T2 (swing)** | Prior-day H/L, prior-day VPOC/VAH/VAL, 2nd/3rd gamma wall | 3 | Days |
| **T3 (session)** | IB H/L, overnight H/L, RTH VWAP, opening print | 2 | Session |
| **T4 (intraday)** | Current-session developing VPOC/VAH/VAL, intraday LVN, 30-min pivots | 1 | Minutes–hours |

**Confluence rule (synthesized from Axia + Jigsaw + Volume Profile literature):** a level is "A-grade" when ≥ 2 tiers align within a narrow band (NQ: ≤ 5 points). A-grade levels are where footprint patterns should be trusted; at non-confluent T4-only levels, demand 2× the pattern strength.

**Practical weighting for DEEP6 confidence score:**
- A-grade confluence (T1+T2, or T1+T2+T3): multiply level-based signals ×1.5
- B-grade (T2 alone, or T2+T3): ×1.0
- C-grade (T3 or T4 alone): ×0.6
- No level within threshold: do not trade reversal patterns; only trend-continuation (stacked imbalance on break).

**Quote (volume-profile community consensus):** "If you identify a level, and there's a confluence of a higher timeframe level at the same spot and area, that level becomes significant" — a near-universal principle across Axia, Jigsaw, Tradingsim, Optimus Futures educational material.

---

## 4. The Entry-Decision Cascade

Synthesized from Axia (3 clues), Jigsaw (3 components), Trader Dale, Valtos, and Bookmap. This is the sequence an elite discretionary OF trader runs between "price nearing level" and "order sent."

```
STEP 0 — CONTEXT (pre-market)
  ├─ Map T1/T2 levels (weekly, prior-day, gamma)
  ├─ Map developing T3/T4 (IB, VWAP)
  └─ Establish day-type hypothesis (trend/balance/open-drive)

STEP 1 — APPROACH  (price within N ticks of level)
  ├─ Is the level A/B/C grade confluence?            [filter]
  │   └─ If C-grade and not trending TO level → SKIP
  ├─ What is day type?
  │   ├─ P-shape / b-shape  → only trade WITH trend
  │   └─ Balance/Normal     → fade extremes OK
  └─ Direction of approach aggressive or drift?
      └─ Aggressive approach = higher chance of sweep
         (prepare for stop-run playbook, not pure absorption)

STEP 2 — REACTION AT LEVEL  (first contact)
  ├─ Does price stall / absorb?  (effort-no-result)
  │   ├─ YES → proceed to STEP 3
  │   └─ NO  → momentum break; look for stacked imbalance
  │            continuation trade instead
  ├─ Is there a sweep (wick + snap-back)?
  │   └─ YES → jump to STEP 4 sweep path
  └─ Delta behavior?
      ├─ Divergent (new extreme, weaker delta) → reversal setup forming
      └─ Aligned with price → no reversal yet

STEP 3 — CONFIRMATION  (sequence required)
  Axia path:       absorption → retest → defended → no opposing pressure
  Jigsaw path:     absorption → one side fades → opposite side steps in
  Wyckoff path:    effort-no-result → test → secondary test holds
  ├─ All three clues/components present?
  │   ├─ YES → STEP 5 trigger
  │   └─ NO  → wait; do not anticipate
  └─ Iceberg suspected (3+ refills)?
      └─ Treat as stronger defender but Bookmap caveat applies

STEP 4 — SWEEP PATH  (alternate branch)
  ├─ Wick through prior H/L then close inside?
  │   ├─ YES → confirming bar with opposite delta flip?
  │   │       └─ Enter on close back inside, stop beyond wick + ATR
  │   └─ NO  → price accepted outside = breakout, not sweep

STEP 5 — TRIGGER
  ├─ Pattern + level confluence validated
  ├─ Order type: limit at absorption price (Axia/Bookmap) OR
                 market on confirmation bar close (Jigsaw, Davies says
                 "market when about to break")
  └─ Size per risk model

STEP 6 — MANAGEMENT
  ├─ First target: nearest opposite VA / VPOC (per Axia blog on management)
  ├─ Move stop to B/E after price leaves absorption + 1 ATR
  └─ Invalidation: pattern-specific (see §1 invalidation column)
      └─ If invalidation hits, exit immediately — DO NOT average
```

---

## 5. Actionable for DEEP6 (Encodable Rules)

Each rule cites the practitioner source. DEEP6 already has absorption, exhaustion, momentum, rejection signals + VP levels + GEX levels — these rules define how to combine them.

1. **Three-clue absorption gate (Axia):** Fire a long-reversal entry ONLY if (a) absorption signal fires at level, (b) price retests the absorption price within N bars, (c) delta on retest is ≤ 0.2× the delta on the original absorption bar. ([Axia](https://axiafutures.com/blog/three-trading-techniques-using-footprint/))

2. **Three-components reversal gate (Davies/Jigsaw):** Require all of (absorption-signal, exhaustion-signal-on-opposite-side, momentum-signal-in-new-direction) within a rolling 5-bar window before issuing a reversal trade. ([Jigsaw PDF](https://www.jigsawtrading.com/wp-content/uploads/2013/11/ConfirmingLevelsWithOrderFlow.pdf))

3. **Iceberg probability flag (Bookmap):** Mark a level as "iceberg-suspected" when ≥ 3 absorption events fire at the same price within T bars. Promote the level's confluence grade by 1 tier. ([Bookmap](https://bookmap.com/blog/how-to-read-and-trade-iceberg-orders-hidden-liquidity-in-plain-sight))

4. **Iceberg-failure reversal (Davies):** If iceberg-suspected level breaks AND an opposite-direction stacked-imbalance fires within 3 bars, flip bias and enter in break direction (explicit Davies rule). ([Jigsaw Lesson 11](https://www.jigsawtrading.com/learn-to-trade-free-order-flow-analysis-lessons-lesson11/))

5. **Confluence weighting (multi-source):** Scale reversal-signal confidence by confluence tier — A:×1.5, B:×1.0, C:×0.6, none:×0 (no-trade). Applied to final entry score, not to raw signal. (synthesized from Axia + Tradingsim volume-profile literature)

6. **Stacked imbalance continuation (Trader Dale):** Enter WITH trend on pullback that reaches the stack base; NEVER fade a fresh stacked-imbalance in the direction of the stack unless an A-grade level is above (bull) / below (bear) it. ([Trader Dale](https://www.trader-dale.com/order-flow-day-trading-strategy-stacked-imbalances/))

7. **Unfinished-auction magnet (ATAS):** When prior-bar extreme has one-sided print (unfinished), register it as a high-probability target for current session. Bias exits toward it. ([ATAS](https://atas.net/atas-possibilities/unfinished-auction-what-it-is-and-how-to-trade-it/))

8. **Delta divergence + level (Valtos):** Fire reversal only when delta-divergence AND price at T1/T2 level. Alone, delta divergence is noise. ([Orderflows](https://www.orderflows.com/encyclopedia/))

9. **Sweep vs break classifier (multi-source):** On wick through prior-day H/L: if next bar closes INSIDE the prior range AND opposite-delta print on close bar, label SWEEP (fade). If next bar closes OUTSIDE, label BREAK (follow). ([Equiti](https://www.equiti.com/sc-en/news/trading-ideas/liquidity-sweeps-explained-how-to-identify-and-trade-them/))

10. **Day-type overlay (Market Profile):** Detect P-shape / b-shape by end of C-D period (90 min into RTH). If detected, disable reversal trades; only permit trend-continuation (stacked imbalance retests) for remainder of session. ([Market Profile Info](https://marketprofile.info/articles/market-profile-patterns))

11. **Effort-no-result veto (Wyckoff):** If most recent bar at level shows top-quartile volume AND bottom-quartile range, require an additional confirmation bar before reversal entry. ([Villahermosa](https://tradingwyckoff.com/en/effort-vs-result/))

12. **Stopping-volume template (tradedevils/multi):** Template match: bar with |delta| > Nσ at extreme, followed by bar closing through the prior bar's open, with opposite-sign delta. Weight 2× a normal exhaustion signal. ([tradedevils](https://tradedevils-indicators.com/products/orderflow-footprint-indicator-sierrachart))

13. **Gamma-wall behavior gate (DEEP6-specific, synthesized):** At call/put wall, reversal patterns should fire more often than breaks (pin behavior). Invert: at gamma-flip, breaks should fire more than reversals. Use as prior on reversal-vs-continuation classifier.

14. **LVN traversal rule (Axia JUMP):** When price traverses an LVN with a stacked imbalance, target the adjacent HVN above/below. Do not enter countertrend inside the LVN — it has no history of support. ([Axia](https://axiafutures.com/blog/three-trading-techniques-using-footprint/))

15. **Invalidation discipline (all sources agree):** Exit the moment the pattern-specific invalidation fires (§1 invalidation column). Never convert a failed reversal into a hold. This is the single strongest shared rule across Axia, Jigsaw, Valtos, Bookmap.

---

## 6. Sources

All HIGH confidence unless noted.

- Axia Futures — Three Trading Techniques Using Footprint: https://axiafutures.com/blog/three-trading-techniques-using-footprint/
- Axia Futures — Absorption Order Flow & Breakout in Eurostoxx: https://axiafutures.com/blog/absorption-order-flow-eurostoxx/
- Axia Futures — Footprint Strategies You Can Apply: https://axiafutures.com/blog/footprint-strategies-you-can-apply-in-your-trading/
- Axia Futures — How Can Footprint Improve Execution: https://axiafutures.com/blog/how-can-footprint-help-your-trade-execution/
- Axia Futures — How To Manage Trade Using Footprint: https://axiafutures.com/blog/how-to-manage-your-trade-using-footprint/
- Axia Futures — Footprint Edge Course page: https://axiafutures.com/course/the-footprint-edge-course/
- Jigsaw Trading — Lesson 1 Basics of Order Flow: https://www.jigsawtrading.com/learn-to-trade-free-order-flow-analysis-lessons-lesson1/
- Jigsaw Trading — Lesson 11 Making Trading Decisions: https://www.jigsawtrading.com/learn-to-trade-free-order-flow-analysis-lessons-lesson11/
- Jigsaw Trading (Davies) — Confirming Levels With Order Flow PDF: https://www.jigsawtrading.com/wp-content/uploads/2013/11/ConfirmingLevelsWithOrderFlow.pdf (MEDIUM — quotes via secondary summary; PDF binary not parseable by fetch)
- Jigsaw Trading — Fading vs Front-Running Absorption: https://www.jigsawtrading.com/blog/which-dom-trading-setups-actually-work-1/
- Jigsaw / Axia blog — Order Flow Absorption & Market Reversals: https://www.jigsawtrading.com/blog/order-flow-absorption-market-reversals
- Bookmap — Iceberg Orders Reading & Trading: https://bookmap.com/blog/how-to-read-and-trade-iceberg-orders-hidden-liquidity-in-plain-sight
- Bookmap — Detecting Stop Runs / CVD + Iceberg: https://bookmap.com/blog/detecting-stop-runs-using-cvd-and-iceberg-absorption-for-strategic-trading
- Bookmap — Stops & Icebergs MBO detection: https://bookmap.com/blog/stops-and-icebergs-how-to-detect-hidden-orders-using-mbo-data
- Bookmap — Absorption product page: https://bookmap.com/absorption/
- Orderflows / Mike Valtos — Trade Opportunity Encyclopedia: https://www.orderflows.com/encyclopedia/
- Orderflows — Footprints In Focus: https://www.orderflows.com/footprintsinfocus/
- Orderflows — Trading Order Flow book (PDF): https://www.orderflows.com/book/TradingOrderFlow768.pdf
- Trader Dale — Stacked Imbalances strategy: https://www.trader-dale.com/order-flow-day-trading-strategy-stacked-imbalances/
- Trader Dale — Most Powerful Imbalance Setups: https://www.trader-dale.com/the-most-powerful-order-flow-imbalance-setups-full-training-9-dec-25/
- Trader Dale — Absorption Setup Entry Confirmation: https://www.trader-dale.com/order-flow-how-to-trade-the-absorption-setup-trade-entry-confirmation/
- ATAS — Unfinished Auction guide: https://atas.net/atas-possibilities/unfinished-auction-what-it-is-and-how-to-trade-it/
- ATAS — How Footprint Works / Patterns: https://atas.net/atas-possibilities/cluster-charts-footprint/how-footprint-charts-work-footprint-modes-and-what-they-are-for/
- Optimus Futures — Footprint Charts Guide: https://optimusfutures.com/blog/footprint-charts/
- TradingView — Volume Footprint Complete Guide: https://www.tradingview.com/support/solutions/43000726164-volume-footprint-charts-a-complete-guide/
- Market Profile Info — 10 Essential Patterns: https://marketprofile.info/articles/market-profile-patterns
- Market Profile Info — Reading Profile Shapes: https://marketprofile.info/articles/reading-market-profile-shapes
- NinjaTrader — 4 Common Volume Profile Shapes: https://ninjatrader.com/futures/blogs/trade-futures-understanding-the-4-common-volume-profile-shapes/
- Villahermosa / Trading Wyckoff — Effort vs Result: https://tradingwyckoff.com/en/effort-vs-result/
- SpotGamma — Absorption and Exhaustion: https://support.spotgamma.com/hc/en-us/articles/15245728388627-Absorption-and-Exhaustion
- Equiti — Liquidity Sweeps explained: https://www.equiti.com/sc-en/news/trading-ideas/liquidity-sweeps-explained-how-to-identify-and-trade-them/
- International Trading Institute — High vs Low Probability Sweeps: https://internationaltradinginstitute.com/blog/high-vs-low-probability-liquidity-sweeps-avoid-traps/
- Tradingsim — Volume Profile Strategies: https://www.tradingsim.com/blog/advanced-day-trading-strategies-using-volume-profile
- tradedevils — Footprint indicator / stopping-volume ratios: https://tradedevils-indicators.com/products/orderflow-footprint-indicator-sierrachart
- CME Iceberg Detection Preprint (dxFeed): https://downloads.dxfeed.com/articles/CME-Iceberg-Detection-preprint.pdf
- TradeProAcademy — Auction Market Theory guide: https://tradeproacademy.com/full-guide-to-auction-market-theory-how-to-trade-successfully/

**Not located:** The specific "Orderflow_transcript.md" referenced in DEEP6 Pine script comments (likely a local/internal file). The "Chimmy Unger"-style CME SpotGamma transcript with direct quotes ("I was waiting for sellers to be absorbed here") did not surface in web searches — it may be in a private CME webinar archive or gated SpotGamma member content. Recommendation: check the local `.planning/research/pine/` tree for the referenced transcript file directly; if present its verbatim quotes should be layered onto §2 as a dedicated subsection.

---

## 7. Confidence Summary

| Section | Confidence | Notes |
|---|---|---|
| Pattern library | HIGH | Every pattern cross-cited ≥ 3 practitioner sources |
| Axia rulebook | HIGH-MEDIUM | Verbatim framing from blog; full course content gated |
| Jigsaw/Davies rulebook | MEDIUM | Key quotes via secondary summaries of the 2013 PDF |
| Valtos setup taxonomy | HIGH | Official encyclopedia page |
| Bookmap | HIGH | Direct from official docs |
| Trader Dale | HIGH | Public blog |
| Multi-timeframe hierarchy | HIGH | Near-universal practitioner consensus |
| Decision cascade | MEDIUM | Synthesis across sources; not one published tree |
| DEEP6 encodable rules | HIGH for structure, MEDIUM for specific thresholds | Thresholds (N ticks, N bars, Nσ) require backtest calibration |

**Research date:** 2026-04-13. Valid ~60 days for practitioner methodology (slow-moving); ~14 days for platform/vendor details.
