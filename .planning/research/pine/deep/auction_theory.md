# Auction Theory & Market Profile — Deep Research for DEEP6

**Researched:** 2026-04-13
**Scope:** Steidlmayer → Dalton lineage, day/open classification, value-area migration, auction patterns, IB framework, footprint × MP synthesis, NQ-specific applications, and deterministic trade-plan generators suitable for automated execution.
**Confidence:** HIGH on core Dalton/Steidlmayer definitions; MEDIUM on exact trigger parameters (these require calibration on NQ tick data).

---

## Summary

Auction Market Theory (AMT), seeded by J. Peter Steidlmayer at the CBOT in the 1980s and productized by James F. Dalton in *Mind Over Markets* (1990, rev. 2013) and *Markets in Profile* (2007), treats price as an advertising mechanism and value as the zone where time and volume accumulate. Every session is a two-sided auction that either balances (rotates around value) or imbalances (trends in discovery of new value). The Market Profile (TPO graph) and its volume twin (Volume Profile) are the instruments that make this visible. For a Python auto-trading system like DEEP6, the value of this lineage is that it produces **deterministic, enumerable trade plans from level structure** — the opposite of discretionary "chart reading." Each day-type, open-type, value-area relationship, and micro-structure artifact (poor high, naked POC, buying tail, single print) has a *known* forward implication that can be encoded as a rule.

**Primary recommendation:** Implement Dalton's framework as a **state machine** that classifies the open, projects a day-type prior, and arms a specific playbook. Combine with footprint signals (absorption, exhaustion) as *trigger* confirmation at MP-defined levels — this is the synthesis Tom Alexander and Mike Valtos teach.

---

## 1. Core Concept Glossary

| # | Term | Precise definition |
|---|------|--------------------|
| 1 | **TPO (Time-Price Opportunity)** | One letter on the 30-min profile = opportunity to transact at that price in that period. The atom of Steidlmayer's graph. |
| 2 | **Profile / Distribution** | Histogram of TPOs per price over a session; bell-shaped when balanced, elongated when trending. |
| 3 | **Value Area (VA)** | Price range containing ~70% of TPOs (1 stdev around POC). Contains VAH and VAL. |
| 4 | **POC (Point of Control)** | Longest TPO row = most time spent. "Fairest price" of the session. |
| 5 | **VPOC** | Volume-based POC; often more actionable than TPO POC because HFTs trade volume, not time. |
| 6 | **Naked/Virgin POC (nPOC)** | A prior-session POC not yet revisited. Acts as magnet; ~80% get retested per Dalton. |
| 7 | **Initial Balance (IB)** | First 60 min of RTH (CBOT A+B periods). Defines the initial auction range. |
| 8 | **Range Extension** | Price moving beyond IBH or IBL after the IB period; signals new timeframe participation. |
| 9 | **Excess** | Sharp rejection of a price level (tail). Marks the end of one auction and start of another. |
| 10 | **Buying Tail / Selling Tail** | ≥2 single TPOs at profile extreme showing aggressive entry against the prior move. |
| 11 | **Single Prints** | Lone TPOs in the middle of a profile indicating rapid, one-sided movement. |
| 12 | **Poor High / Poor Low** | Flat extreme with <2 TPOs of excess; indicates weak-handed participants; statistically revisited and broken. |
| 13 | **Failed Auction** | Price extends beyond a known reference but does not gain acceptance (low volume, quick return); strong reversal signal. |
| 14 | **One-Time Framing (OTF-up/down)** | Each bar's low is ≥ prior bar's low (up) or each high ≤ prior high (down); measures trend persistence. |
| 15 | **Initiative Activity** | Buying ABOVE value or selling BELOW value — unexpected; indicates new timeframe conviction. |
| 16 | **Responsive Activity** | Buying BELOW value or selling ABOVE value — expected; fades the move back toward value. |
| 17 | **Balance** | Overlapping profiles across multiple sessions; bracketed range; responsive trade preferred. |
| 18 | **Imbalance** | Elongated profile; price discovery; initiative trade preferred. |
| 19 | **Day Timeframe (DTF) vs Other Timeframe (OTF)** | DTF = scalpers/locals; OTF = institutions/position traders. OTF creates range extensions and trends. |
| 20 | **Two-Timeframe Trader** | Dalton's discipline: align DTF execution with OTF context. |
| 21 | **Spike** | Tail that occurs in the final period (no subsequent period to confirm); rules below. |
| 22 | **Spike Rules** | If next day opens inside the spike → spike is reference; opens beyond → spike is excess. |
| 23 | **Unsecured High/Low** | Extreme lacking excess confirmation (similar to poor) — expect retest and break. |
| 24 | **Open Range** | Price range of the first 1–5 minutes; Dalton's primary "conviction proxy." |
| 25 | **Value Migration** | Directional shift of VA from day-to-day; the central MP bias signal. |
| 26 | **Composite Profile** | Multi-day profile aggregating balance periods; locates longer-timeframe VAH/VAL/POC. |
| 27 | **Rotation** | Intraday oscillation around POC; implies balance. |
| 28 | **Acceptance** | Price holds outside a reference with expanding volume and no immediate rejection (Dalton: "three tests"). |
| 29 | **Rejection** | Quick, low-volume return through a reference level; inverse of acceptance. |
| 30 | **Inventory (Overnight)** | Net positioning of Globex participants vs. settlement; "long inventory" tends to liquidate on open, "short inventory" tends to cover. |

---

## 2. Day-Type Classification (Dalton, *Mind Over Markets* Ch. 4)

| Day Type | Signature | Typical IB | Range vs IB | Next-Day Implication |
|----------|-----------|-----------|-------------|----------------------|
| **Normal** | OTF traders on both sides early; wide IB; two-sided trade all day | Wide | ~1x IB | Expect balance continuation; fade extremes |
| **Normal Variation** | ~42% frequency per Dalton; smaller IB; one OTF extends range to one side, responsive OTF caps it | Medium | 1.5–2x IB | Bias in direction of extension; expect value migration same direction |
| **Trend Day** | Open near one extreme, close near opposite; narrow IB; minimal horizontal development; excess only at closing extreme | Narrow | 2x–4x+ IB | Expect gap continuation or pullback to prior VAH/VAL; avoid fading early next session |
| **Double Distribution Trend** | Two distinct value areas separated by single prints; price finds acceptance, breaks, forms second distribution | Narrow | 3x+ IB | Single prints between distributions become high-conviction targets if revisited |
| **Neutral** | Range extensions both sides of IB; close near mid-range (Neutral-Center) or at extreme (Neutral-Extreme) | Average | ~2x IB | Neutral-Extreme implies directional follow-through; Neutral-Center implies balance/chop |
| **Non-Trend** | Narrow IB holds all day; D-shape; news-anticipation or pre-holiday | Narrow | ~1x IB | Volatility expansion likely next session; position for breakout |

Source: [Six Types of Market Days — Mind Over Markets](https://time-price-research-astrofin.blogspot.com/2023/03/six-types-of-market-days-mind-over.html), [Mind Over Markets (Wiley)](https://www.oreilly.com/library/view/mind-over-markets/9781118659762/).

---

## 3. Open-Type Classification (Dalton, *Markets in Profile* Ch. 3)

| Open Type | Signature | Confidence | Entry Logic | Stop | Target |
|-----------|-----------|-----------|-------------|------|--------|
| **Open-Drive (OD)** | Market opens and immediately auctions aggressively in one direction; no return through opening range | Highest | Enter WITH the drive on first pullback to opening range edge; never fade | 2–4 ticks beyond the open | IB extension = 1.5x IB; full-day target = 2x IB |
| **Open-Test-Drive (OTD)** | Opens, tests beyond a known reference (prior day VAH/VAL/high/low) to confirm no new business, then reverses and drives back through open | 2nd highest | Enter WITH the drive after the test fails; the tested reference becomes the stop | Beyond the tested reference + 2 ticks | Mirror-image reference on other side of value |
| **Open-Rejection-Reverse (ORR)** | Opens, trades one direction, meets opposite activity, reverses back through opening range | Medium | Enter on reversal through open; only ~50% of initial extremes hold | Beyond rejected extreme | Opposite end of IB, then prior day VWAP |
| **Open-Auction In-Range (OAIR)** | Opens inside prior day's range and rotates around open; no conviction | Low | Fade IB extremes toward POC; responsive trade | Beyond IB + tick buffer | POC / opposite IB edge |
| **Open-Auction Out-of-Range (OAOR)** | Opens outside prior day's range but then rotates; tentative directional bias | Medium | Wait for acceptance test; trade in direction of acceptance vs prior range | Back inside prior day's range | Nearest naked POC / prior composite VA edge |

Source: [Market Profile Course 3: Opening Types (Nature of Markets)](https://www.thenatureofmarkets.com/market-profile-course-3-opening-types-open-range-strategy-and-practical-applications/), [Medium: Opening Types](https://medium.com/@bhattacharya.ratul/opening-types-open-range-strategy-and-practical-applications-153df89e2bf5).

---

## 4. Value-Area Relationships (Dalton's "Opening Relationships")

The daily open relative to prior day's value area is the primary bias filter.

| Relationship | Meaning | Trade Plan |
|--------------|---------|-----------|
| **Higher Value, Higher Price** | Open above prior VAH; value migrated up | Initiative long bias. Buy pullbacks to prior VAH (new support). Target = prior day high + IB extension |
| **Lower Value, Lower Price** | Open below prior VAL; value migrated down | Initiative short bias. Sell rallies into prior VAL (new resistance). Target = prior day low − IB extension |
| **Overlapping-to-Higher** | Open within prior VA, value skewed up | Mild bullish bias; trade long on VAL holds; expect Normal Variation up |
| **Overlapping-to-Lower** | Open within prior VA, value skewed down | Mild bearish bias; trade short on VAH rejection; expect Normal Variation down |
| **Unchanged Value** | VA overlaps prior VA ≥80% | Balance / rotation. Fade extremes; scalp POC revisits. Avoid directional bets until breakout acceptance |
| **Outside-Range-Up (ORU)** | Open entirely above prior day's range | Strongest initiative buying; Open-Drive more likely. Trend-day alert |
| **Outside-Range-Down (ORD)** | Open entirely below prior day's range | Strongest initiative selling; Open-Drive more likely. Trend-day alert |
| **Gap Fill Setup** | Open gaps beyond range with no follow-through in first 15 min | Likely gap fill back to prior settle; responsive trade |

Source: [Markets in Profile PDF (Dalton)](http://www.r-5.org/files/books/trading/charts/market-profile/James_Dalton-Markets_in_Profile-EN.pdf), [TopStep: Intro to AMT](https://www.topstep.com/blog/intro-to-auction-market-theory-and-market-profile/).

---

## 5. Auction Pattern Library (Micro-Structure Triggers)

| Pattern | Trigger (detectable in code) | Action | Invalidation |
|---------|------------------------------|--------|--------------|
| **Failed Auction** | Price breaks prior day H/L or IB extreme on LOW volume (<80% of 20-period avg) AND returns inside within 2 periods | Fade — enter on return through the broken level; target opposite side of IB | Re-break with expanding volume |
| **Poor High** | Day high has ≤1 TPO excess AND ≥2 adjacent columns of equal highs | Flag for overnight liquidation hunt. Short if revisited on light volume; expect break if revisited on heavy volume | Strong volume retest = buy breakout instead |
| **Poor Low** | Mirror of poor high | Long on light-volume retest; short-break on heavy-volume retest | Strong volume break = sell breakdown |
| **Naked POC (nPOC)** | Prior-session VPOC never traded since | Treat as magnet; ~80% get retested. Enter WITH trend toward nPOC; exit AT nPOC and fade back | nPOC "absorbed" into value = no longer naked |
| **Single Print** | Column of lone TPOs in middle of profile | Low-volume node; expect rapid traversal. Targets for trend-continuation entries | Acceptance (volume builds) = structure invalidated |
| **Buying Tail** | ≥2 single TPOs at session low formed in first 2 periods | Aggressive buyer signature. Long on pullback into tail; stop below tail | Tail broken with volume — immediate reversal |
| **Selling Tail** | Mirror at session high | Short on rally into tail; stop above tail | Tail broken with volume |
| **Spike (last period)** | Tail in final 30 min of RTH | Apply spike rules: next open INSIDE spike → use as reference; OUTSIDE spike → spike = excess, trade continuation | Open inside low of up-spike = reference broken |
| **Double Distribution Forming** | Single prints separate two clusters of TPOs; volume confirms each cluster | Trade in direction of 2nd distribution; single prints become stop zone | Return into 1st distribution invalidates the break |
| **One-Time Framing (OTF)** | 3+ consecutive 30-min bars without violating prior bar's opposite extreme | Trend in progress. Enter with trend on pullbacks that respect OTF boundary | OTF break (bar violates prior boundary) = end of trend leg |
| **Value-Area Rotation** | Price crosses VAH or VAL intra-session | If rejects (returns) → fade back to POC; if accepts (3-period hold) → extend to next composite level | Acceptance vs rejection test = 30-min confirmation |
| **Unsecured High/Low** | Extreme lacking a tail/excess | Behaves like poor high/low; statistically retested | Tail forms on retest = secured |

Source: [Shadow Trader Glossary](https://www.shadowtrader.net/glossary/poor-high/), [Trade Brigade — Poor Highs & Lows](https://tradebrigade.co/poor-high-poor-low/), [Trade Brigade — Spike Rules](https://tradebrigade.co/market-profile-spikes-and-spike-rules/), [Market Profile Micro Visual Structures (Marketcalls)](https://www.marketcalls.in/market-profile/understanding-micro-visual-structures-in-market-profile.html).

---

## 6. Initial Balance (IB) Framework

**Definition:** First 60 minutes of RTH. For NQ on CME, that is 9:30–10:30 ET (A+B periods).

**Width classification:**
- **Narrow IB** (<0.5x 20-day avg) → trend-day or double-distribution candidate; range-extension probability HIGH (~75%)
- **Average IB** (0.5–1.5x avg) → Normal Variation candidate
- **Wide IB** (>1.5x avg) → Normal Day candidate; OTF already active both sides; responsive trades preferred

**Rules for trading around IB (Dalton's framework, per secondary sources):**
1. **Successful range extension**: Period C or later closes beyond IBH/IBL → expect continuation. Enter on first pullback toward breakout level; stop 2–3 ticks back inside IB; target = 2x IB projection (measured move).
2. **Failed range extension**: Period closes BACK INSIDE IB after an excursion beyond → 70–75% probability of a drive to the OPPOSITE side of IB. Enter on close back inside; stop beyond excursion high/low; target = opposite IB edge, then prior day POC.
3. **IB hold (no extension)**: Price rotates inside IB → expect balanced day; fade IBH and IBL toward POC until break.
4. **Double IB extension (Neutral)**: Extensions both sides → if closes mid-range = Neutral-Center (low conviction, scalp); if closes at extreme = Neutral-Extreme (directional follow-through next session).

Source: [TradePRO — Initial Balance](https://tradeproacademy.com/how-to-use-the-initial-balance/), [Steady Turtle — IB Strategy for ES/NQ](https://www.steady-turtle.com/knowledge/initial-balance-trading-strategy).

---

## 7. Footprint × Market Profile Synthesis

Tom Alexander (*Practical Trading Applications of Market Profile*, 2009) and practitioners like Mike Valtos (OrderFlows) and John Grady (No BS Day Trading) argue MP/AMT provides **context** (WHERE to trade) and order flow / footprint provides **trigger** (WHEN to trade). The footprint read is different at each MP reference:

| MP Reference | Expected Footprint on Entry |
|--------------|-----------------------------|
| **At prior day POC / nPOC** | Expect absorption (large resting orders absorb aggressors, delta divergence). Trade with the absorbing side. |
| **At VAH or VAL (responsive)** | Look for exhaustion of the aggressor: delta declines as price presses; stacked imbalances fail to extend; trade fade. |
| **At VAH or VAL (initiative break)** | Look for acceptance: sustained delta in breakout direction; volume expansion; no immediate return. Trade continuation. |
| **At prior day high/low (poor)** | Expect absorption PLUS resting liquidity sweep; stop-run pattern. If delta flips after sweep → fade. If delta continues → break. |
| **At single print (traversing)** | Expect minimal footprint — single prints are LOW-volume zones. Price should move fast. Do NOT enter IN a single print; wait for it to resolve at the next HVN. |
| **At buying/selling tail** | Expect aggressive one-sided delta on formation. On retest, expect absorption (tail defended) or exhaustion (tail fails). |
| **At IB extreme (post-period C)** | Confirm extension with stacked imbalance + delta expansion. A break without these = likely failed extension → reversal. |
| **At composite HVN (multi-day POC)** | Strongest fade candidates. Absorption + exhaustion almost always precede reversals here. |

DEEP6's 44-signal stack (absorption, exhaustion, stacked imbalance, CVD divergence, aggressor ratio, etc.) should be evaluated **conditionally at MP-defined levels** — not in isolation. This is Alexander's core teaching: signals are meaningless without context.

Source: [Alexander Trading eBooks](https://alexandertrading.com/ebooks/), [CQG Interview with Tom Alexander](https://news.cqg.com/blogs/interview/2013/02/interview-tom-alexander), [Jigsaw — No BS Trading](https://www.jigsawtrading.com/no-bs-day-trading/), [Axia — Trading Key Market Auction Reversals](https://axiafutures.com/blog/trading-key-market-auction-reversals/).

---

## 8. NQ-Specific Applications

NQ is MP-tradeable but requires adjustments vs ES:

- **RTH-only profiles**: Build from 9:30–16:15 ET. Overnight Globex profile tracked separately as "inventory" context.
- **Overnight inventory**: If Globex net position is significantly long going into RTH and RTH opens ORD → expect liquidation (long squeeze) → lower high probability. Mirror for short squeeze.
- **Volatility**: NQ ATR(14) ≈ 250 pts (Q1 2024) vs ES ≈ 45 pts. Stops and targets scale 5–6x vs ES. IB width norms must be calibrated in NQ points, not ticks.
- **Correlation breaks**: When NQ diverges from ES (tech risk-off days), MP levels on NQ hold more conservatively; responsive trades dominate. When NQ leads ES (risk-on, tech momentum), initiative trades dominate.
- **Friday/Opex effect**: Gamma levels from QQQ/NDX options (DEEP6 pulls from FlashAlpha) become harder MP references than prior-day VAH/VAL on OpEx Fridays and monthly expiry.
- **Globex POC vs RTH POC**: On gap opens, Globex POC frequently acts as magnet during first 30 min.

Source: [TradePRO — NQ + AMT](https://tradeproacademy.com/trading-nasdaq-futures-using-auction-market-theory/), [MarketProfile.info — Futures Trading](https://marketprofile.info/articles/futures-trading-market-profile), [Bookmap — NQ vs ES](https://bookmap.com/blog/nq-vs-es-why-they-move-together-until-they-dont), [Tatanka Trading — Profile & ML Levels](https://tatankatrading.com/).

---

## 9. Actionable for DEEP6 — 15 Trade-Plan Generators

Each generator is a **conditional rule** the engine can evaluate. Inputs: MP state (day-type prior, open-type, VA relationship, IB state, level inventory) + footprint state (absorption, exhaustion, delta, CVD).

1. **OD-UP + ORU + no rejection** → Long on first pullback to opening range high. Stop = open − 4 ticks. Target = 2x IB projection. Kronos E10 must not be bearish (≥ neutral).
2. **OD-DOWN + ORD + no rejection** → Mirror short.
3. **OTD-UP (test prior day low, reverse)** → Long on reclaim of overnight low. Stop = tested low − 2 ticks. Target = prior day POC, then VAH.
4. **ORR at prior day VAH** → Fade back to POC. Stop beyond VAH + 1 ATR(5min). Target = prior POC, then VAL. Require exhaustion footprint at VAH.
5. **Failed IB extension up (period C closes back inside IB)** → Short to opposite IB edge. Stop above excursion high. Target = IBL. 70–75% historical probability (Dalton).
6. **Failed IB extension down** → Mirror long.
7. **Naked POC magnet (nPOC above current price, price drifting up)** → Long toward nPOC, exit AT nPOC, flip short if exhaustion prints. Stop = last swing low.
8. **Naked POC magnet (nPOC below, drifting down)** → Mirror.
9. **Poor high revisit on light volume (<70% of 30-period avg)** → Short. Stop above poor high + 3 ticks. Target = day POC. Requires absorption signal at high.
10. **Poor low revisit on heavy volume (>130% of avg)** → Short breakout. Stop above retest high. Target = measured move of day range. (Heavy volume = break, light volume = fade — critical branch.)
11. **Buying tail retest** → Long on pullback into tail with delta flip positive. Stop below tail − 2 ticks. Target = day high or VAH.
12. **Open-Auction In-Range + unchanged value** → Responsive scalps only. Fade IBH/IBL to POC. Disable trend logic. Max 2 trades per day.
13. **Double-distribution single-print revisit** → Enter WITH direction of break through single print on volume expansion. Stop in middle of single print. Target = edge of 2nd distribution.
14. **Absorption at prior day high + Kronos bearish E10 + IB extension failure up** → High-conviction short setup. Stop = prior day high + 2 ticks. Target = prior day POC, then VAL.
15. **Neutral-Extreme close at high → next-day ORU open** → Gap-and-go bias. Scale-in long on first 5-min pullback. Stop = prior day high. Target = 1.5x prior day range extension.

Each generator emits a *candidate plan object* the DEEP6 engine scores and gates through risk controls before routing the order via `async-rithmic` ORDER_PLANT.

---

## 10. Sources

### Primary (HIGH)
- Dalton, J.F. *Mind Over Markets* (Wiley, rev. 2013) — [O'Reilly](https://www.oreilly.com/library/view/mind-over-markets/9781118659762/)
- Dalton, J.F. *Markets in Profile* (Wiley, 2007) — [PDF mirror](http://www.r-5.org/files/books/trading/charts/market-profile/James_Dalton-Markets_in_Profile-EN.pdf)
- Steidlmayer, J.P. *Steidlmayer on Markets* (Wiley, 1989/2003) — referenced via [ATAS AMT guide](https://atas.net/market-theory/the-auction-market-theory/)
- Alexander, T. *Practical Trading Applications of Market Profile* — [Alexander Trading](https://alexandertrading.com/ebooks/)
- [Jim Dalton Trading — Start Here](https://jimdaltontrading.com/starthere/) and [Glossary](https://jimdaltontrading.com/glossarypage/)

### Secondary (MEDIUM — educator interpretations)
- [WindoTrader Market Profile Glossary](https://www.windotrader.com/market-profile/market-profile-glossary-index/)
- [Shadow Trader Glossary](https://www.shadowtrader.net/glossary/)
- [TopStep — Intro to AMT](https://www.topstep.com/blog/intro-to-auction-market-theory-and-market-profile/)
- [TradingRiot — AMT deep dive](https://tradingriot.com/market-profile/)
- [Six Types of Market Days summary](https://time-price-research-astrofin.blogspot.com/2023/03/six-types-of-market-days-mind-over.html)
- [TradePRO — Initial Balance](https://tradeproacademy.com/how-to-use-the-initial-balance/)
- [TradePRO — NQ + AMT](https://tradeproacademy.com/trading-nasdaq-futures-using-auction-market-theory/)
- [Nature of Markets — Opening Types Course 3](https://www.thenatureofmarkets.com/market-profile-course-3-opening-types-open-range-strategy-and-practical-applications/)
- [Marketcalls — Micro Visual Structures](https://www.marketcalls.in/market-profile/understanding-micro-visual-structures-in-market-profile.html)
- [Trade Brigade — Poor Highs and Lows](https://tradebrigade.co/poor-high-poor-low/)
- [Trade Brigade — Spike Rules](https://tradebrigade.co/market-profile-spikes-and-spike-rules/)
- [Axia Futures — Key Market Auction Reversals](https://axiafutures.com/blog/trading-key-market-auction-reversals/)
- [Axia Futures — Price Ladder & Orderflow Tactics](https://axiafutures.com/blog/price-ladder-and-orderflow-trading-tactics/)
- [Jigsaw — No BS Day Trading (John Grady)](https://www.jigsawtrading.com/no-bs-day-trading/)
- [Bookmap — NQ vs ES](https://bookmap.com/blog/nq-vs-es-why-they-move-together-until-they-dont)
- [Tatanka — Profile & ML Levels for ES/NQ](https://tatankatrading.com/)
- [Steady Turtle — IB Strategy for ES/NQ](https://www.steady-turtle.com/knowledge/initial-balance-trading-strategy)

---

## Confidence Notes

- **HIGH**: Day-type and open-type definitions, VA relationships, core glossary — these are directly traceable to Dalton and Steidlmayer and consistent across all secondary sources.
- **MEDIUM**: Exact probability figures (e.g., "70–75% failed extension reversal") — cited from Dalton-derived educators but not all directly verifiable in primary text; treat as prior for calibration rather than ground truth.
- **MEDIUM**: Donnchadh Bradley / Axia — direct Bradley content not found; Axia's public auction-reversal framework (exhaustion, absorption, failed breaks, key reversals) is the actionable substitute.
- **LOW** (requires DEEP6 calibration): Exact tick-level stops, volume thresholds, and NQ-specific parameter tuning — all numbers in Section 9 are starting points that must be validated on Databento MBO historical data before live deployment.
