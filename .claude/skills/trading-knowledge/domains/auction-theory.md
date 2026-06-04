# Auction Theory — DEEP6 Knowledge Domain

**Last verified: 2026-05-12**
**Source research:** `C:\Users\Tea\DEEP6\.planning\research\pine\deep\auction_theory.md`
**Source practitioners:** `C:\Users\Tea\DEEP6\.planning\research\pine\deep\practitioners.md`
**DEEP6 engine:** `C:\Users\Tea\DEEP6\deep6\engines\auction.py`
**Primary references:** Dalton, *Mind Over Markets* (Wiley, rev. 2013); Dalton, *Markets in Profile* (Wiley, 2007); Steidlmayer, *Steidlmayer on Markets* (Wiley, 1989/2003)

---

## AUCT-01: Market Profile and TPO Charts

**Category**: Auction Theory
**Tags**: Market Profile, TPO, time-price opportunity, Steidlmayer, Dalton, value area, distribution
**DEEP6 Signal(s)**: Context layer for all auction signals; day-type classification
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py`

### Concept
Market Profile (MP) was developed by J. Peter Steidlmayer at the CBOT in the 1980s and productized by James F. Dalton. It treats price as an advertising mechanism and value as the zone where time and volume accumulate.

A TPO (Time-Price Opportunity) is one letter on the 30-minute profile — the opportunity to transact at that price in that period. The profile is a histogram of TPOs per price over a session. A bell-shaped profile indicates balance (two-sided trade). An elongated profile indicates imbalance (trending, price discovery).

Every session is a two-sided auction that either:
- **Balances:** rotates around value, responsive trade preferred
- **Imbalances:** trends in discovery of new value, initiative trade preferred

For DEEP6, Market Profile provides the *context* (WHERE to trade). Footprint signals (absorption, exhaustion) provide the *trigger* (WHEN to trade). This is Tom Alexander's core teaching: signals are meaningless without context.

### Conditions / Setup
- Build RTH-only profiles: 9:30-16:15 ET for NQ
- Track Globex profile separately as "inventory" context
- 30-minute periods labeled A through M (RTH)
- Value Area = price range containing ~70% of TPOs (1 standard deviation around POC)

### Entry / Exit Rules
- Balance day: fade extremes toward POC; responsive trade
- Imbalance day: trade with trend; initiative trade
- Day-type classification (see AUCT-05) determines which playbook applies

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\auction.py` — AuctionEngine class (lines 52-255).

The E9 Auction State Machine tracks: `EXPLORING_UP`, `EXPLORING_DOWN`, `BALANCED`, `BREAKOUT`, `BREAKDOWN`. State transitions at lines 232-254 based on expanding/contracting range vs prior bar.

AUCT-01 through AUCT-05 signals are computed in `AuctionEngine.process()` (lines 91-230).

### Academic Basis
- Dalton, J.F. *Mind Over Markets* (Wiley, rev. 2013): primary source for day-type and open-type classification.
- Dalton, J.F. *Markets in Profile* (Wiley, 2007): value-area relationships and opening relationships.
- Steidlmayer, J.P. *Steidlmayer on Markets* (Wiley, 1989/2003): original Market Profile framework.
- Alexander, T. *Practical Trading Applications of Market Profile* (Alexander Trading, 2009): footprint × MP synthesis.

---

## AUCT-02: POC (Point of Control)

**Category**: Auction Theory
**Tags**: POC, VPOC, point of control, fairest price, magnet, naked POC, nPOC
**DEEP6 Signal(s)**: POC signals, E9 pin state (AUCT-04 context)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\poc.py`, `C:\Users\Tea\DEEP6\deep6\engines\auction.py`

### Concept
The Point of Control (POC) is the price level with the most time spent (TPO POC) or the most volume traded (VPOC). It represents the "fairest price" of the session — where the most business was done, where buyers and sellers agreed most.

VPOC is more actionable than TPO POC for HFT-dominated markets because institutions trade volume, not time.

**Naked/Virgin POC (nPOC):** A prior-session VPOC that has never been revisited since it was formed. Acts as a magnet — approximately 80% get retested per Dalton. When price drifts toward an nPOC, it is a high-probability target.

At the POC, expect absorption: large resting orders absorb aggressors, delta divergence appears. Trade with the absorbing side.

### Conditions / Setup
- POC is the price with highest volume in the session
- nPOC: prior-session VPOC not yet revisited
- Price drifting toward nPOC = magnet behavior
- At POC: expect two-sided trade, rotation, absorption

### Entry / Exit Rules
- **Naked POC magnet (nPOC above, price drifting up):** Long toward nPOC, exit AT nPOC, flip short if exhaustion prints. Stop = last swing low.
- **Naked POC magnet (nPOC below, drifting down):** Mirror short.
- **At POC during session:** Expect rotation. Fade extremes toward POC. Scalp POC revisits.
- **nPOC absorbed into value:** No longer naked — remove from magnet list.

### Risk Management
- Stop: last swing low (long) or last swing high (short)
- Target: the nPOC itself; flip on exhaustion at nPOC
- Invalidation: nPOC "absorbed" into value (volume builds at nPOC, it becomes a new HVN)

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\poc.py` — POC/VAH/VAL computation.

POC provides `vah` and `val` to the absorption engine (`absorption.py` lines 229-241) for the ABS-07 VA extreme bonus.

E9 pin state in `auction.py`: when VPOC is near the largest gamma level and bar touches VPOC then closes away, E9 entry trigger fires (limit at VPOC ± 2 ticks).

### Academic Basis
- Dalton, *Mind Over Markets* Ch. 4: POC as "fairest price," nPOC magnet behavior (~80% retest rate).
- Cont, Stoikov & Talreja (2010): Markovian LOB model — POC corresponds to price where queue replenishment rate equals depletion rate, creating a natural equilibrium.

### Examples / Edge Cases
- **Globex POC vs RTH POC:** On gap opens, Globex POC frequently acts as magnet during first 30 minutes.
- **Composite POC:** Multi-day profile POC is the strongest fade candidate. Absorption + exhaustion almost always precede reversals at composite HVNs.

---

## AUCT-03: Value Area High and Low (VAH, VAL)

**Category**: Auction Theory
**Tags**: VAH, VAL, value area, responsive trade, initiative trade, support, resistance
**DEEP6 Signal(s)**: ABS-07 (VA extreme bonus), E7 (exhaustion at VAH/VAL), E12 (absorption at VAH/VAL)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\poc.py`, `C:\Users\Tea\DEEP6\deep6\engines\absorption.py`

### Concept
The Value Area High (VAH) and Value Area Low (VAL) are the upper and lower boundaries of the price range containing ~70% of session volume. They represent the edges of "accepted value" — where the market agreed to do business.

VAH and VAL are the most important levels in Market Profile for intraday trading:
- **Responsive trade at VAH:** Price rallies into VAH from below. Sellers are expected to defend. Fade back toward POC.
- **Responsive trade at VAL:** Price drops into VAL from above. Buyers are expected to defend. Fade back toward POC.
- **Initiative break above VAH:** Price breaks above VAH with acceptance (volume, no immediate return). New value is being established higher. Trade continuation.
- **Initiative break below VAL:** Mirror. Trade continuation lower.

Value migration: the directional shift of VA from day to day is the central MP bias signal.

### Conditions / Setup
- **Responsive trade:** Price approaches VAH/VAL from inside the value area
- **Initiative break:** Price breaks VAH/VAL from outside with acceptance (3-period hold, volume expansion)
- **Acceptance test:** Price holds outside a reference with expanding volume and no immediate rejection (Dalton: "three tests")
- **Rejection:** Quick, low-volume return through a reference level

### Entry / Exit Rules
- **Responsive at VAH:** Exhaustion signal + delta agrees + positive gamma regime → limit at 0.5 × (bar high + bar low). Target: POC, then VAL.
- **Responsive at VAL:** Mirror long.
- **Initiative break above VAH:** Sustained delta in breakout direction + volume expansion + no immediate return → continuation long. Target: next composite level.
- **ORR at prior day VAH:** Fade back to POC. Stop beyond VAH + 1 ATR(5min). Require exhaustion footprint at VAH.

### Risk Management
- Stop: beyond the VA boundary by the zone width + 2 ticks
- Target: POC (responsive), or next structural level (initiative)
- Invalidation: acceptance at the level (volume builds where it shouldn't)

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\poc.py` — VAH/VAL computation.
`C:\Users\Tea\DEEP6\deep6\engines\absorption.py` lines 229-241 — ABS-07 VA extreme bonus: absorption signals at VAH or VAL get a strength boost via `cfg.va_extreme_ticks` proximity check.

E7 entry trigger: exhaustion signal + delta agrees at VAH/VAL in positive gamma regime → limit entry.
E12 entry trigger: CONFIRMED_ABSORB at VAH/VAL with VA-proximity boost applied, score >= 80 → limit at zone midpoint.

### Academic Basis
- Dalton, *Markets in Profile* Ch. 3: opening relationships and value-area migration as primary bias filter.
- Cont & de Larrard (2013): queue depletion at VA boundaries produces predictable price moves — formal basis for responsive trade at VAH/VAL.

### Examples / Edge Cases
- **Value migration:** Higher Value, Higher Price (open above prior VAH) = initiative long bias. Buy pullbacks to prior VAH (new support). Lower Value, Lower Price = initiative short bias.
- **Unchanged value:** VA overlaps prior VA >= 80% = balance/rotation. Fade extremes; scalp POC revisits. Avoid directional bets until breakout acceptance.
- **NQ vs ES:** NQ ATR(14) ≈ 250 pts vs ES ≈ 45 pts. Stops and targets scale 5-6x vs ES. VA width norms must be calibrated in NQ points.

---

## AUCT-04: Initial Balance (IB) Range and Extensions

**Category**: Auction Theory
**Tags**: initial balance, IB, range extension, IBH, IBL, first hour, RTH
**DEEP6 Signal(s)**: E14 (IB high/low breakout), failed IB extension setups
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py`

### Concept
The Initial Balance (IB) is the price range of the first 60 minutes of RTH (9:30-10:30 ET for NQ, periods A+B). It defines the initial auction range — where the market first establishes value for the day.

IB width classification:
- **Narrow IB** (< 0.5x 20-day avg): trend-day or double-distribution candidate; range-extension probability HIGH (~75%)
- **Average IB** (0.5-1.5x avg): Normal Variation candidate
- **Wide IB** (> 1.5x avg): Normal Day candidate; OTF already active both sides; responsive trades preferred

Range extension: price moving beyond IBH or IBL after the IB period signals new timeframe (institutional) participation. This is the most important intraday event in Market Profile.

### Conditions / Setup
- IB = first 60 minutes of RTH (A+B periods)
- Successful range extension: period C or later closes beyond IBH/IBL
- Failed range extension: period closes BACK INSIDE IB after excursion beyond
- IB hold: price rotates inside IB all day

### Entry / Exit Rules
- **Successful range extension:** Enter on first pullback toward breakout level. Stop 2-3 ticks back inside IB. Target = 2x IB projection (measured move).
- **Failed range extension (up):** 70-75% probability of drive to OPPOSITE side of IB. Enter on close back inside. Stop beyond excursion high. Target = opposite IB edge, then prior day POC.
- **Failed range extension (down):** Mirror long.
- **IB hold:** Fade IBH and IBL toward POC until break. Disable trend logic.
- **Double IB extension (Neutral):** Extensions both sides. If closes mid-range = Neutral-Center (scalp). If closes at extreme = Neutral-Extreme (directional follow-through next session).

### Risk Management
- Stop: 2-3 ticks back inside IB (for extension trades)
- Target: 2x IB projection for successful extension; opposite IB edge for failed extension
- Invalidation: re-break of the extension level with volume

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\auction.py` — AuctionEngine tracks IB state.

E14 entry trigger: TYPE_A breakout + delta agrees at IB high/low in negative-amplifying GEX regime → stop order 1 tick beyond breakout bar extreme.

Failed IB extension setups (trade logic research): `C:\Users\Tea\DEEP6\.planning\research\pine\deep\trade_logic.md` §3, entries E5 (failed IB extension up) and E6 (failed IB extension down).

### Academic Basis
- Dalton, *Mind Over Markets* Ch. 4: IB framework, range extension rules, 70-75% failed extension reversal probability.
- FuturesTrader71 (Morad Askar): "Initial Balance + 1-sigma extension" framework. Position sizing ATR-scaled: risk budget / (stop distance × $50/pt).

### Examples / Edge Cases
- **NQ IB norms:** Must be calibrated in NQ points, not ticks. NQ ATR(14) ≈ 250 pts means IB width norms are much wider than ES.
- **Narrow IB + trend day:** Narrow IB is the strongest trend-day signal. If IB is narrow AND open-drive occurs, expect 2x-4x IB range for the day.
- **Friday/Opex:** Gamma levels from QQQ/NDX options become harder references than IB on OpEx Fridays.

---

## AUCT-05: Excess (Failed Auction, Single Prints at Extremes)

**Category**: Auction Theory
**Tags**: excess, failed auction, single prints, tail, buying tail, selling tail, rejection
**DEEP6 Signal(s)**: AUCT-01 (Unfinished Business), AUCT-02 (Finished Auction), AUCT-03 (Poor High/Low)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py`

### Concept
Excess marks the end of one auction and the start of another. It is a sharp rejection of a price level — the market explored that price, found no business, and reversed aggressively.

Types of excess:
- **Buying tail:** >= 2 single TPOs at session low formed in the first 2 periods. Aggressive buyer signature — the market rejected lower prices immediately.
- **Selling tail:** Mirror at session high.
- **Single prints in the middle of a profile:** Lone TPOs indicating rapid, one-sided movement. Low-volume nodes — price should move fast through them. Do NOT enter inside a single print.

**Failed auction:** Price breaks prior day H/L or IB extreme on LOW volume (< 80% of 20-period avg) AND returns inside within 2 periods. Strong reversal signal — the market tried to go there and found no participants.

**Unfinished business (AUCT-01):** Non-zero bid at bar high or non-zero ask at bar low. The auction did not find the opposing participant — price will return to complete the auction.

**Finished auction (AUCT-02):** Zero bid at bar high (buyers exhausted) or zero ask at bar low (sellers exhausted). The auction is complete — no unfinished business.

### Conditions / Setup
- **Buying tail:** >= 2 single TPOs at session low in first 2 periods
- **Selling tail:** Mirror at session high
- **Failed auction:** Break of prior H/L or IB extreme on < 80% of 20-period avg volume, returns inside within 2 periods
- **Unfinished business (AUCT-01):** Non-zero bid at bar high OR non-zero ask at bar low

### Entry / Exit Rules
- **Buying tail retest:** Long on pullback into tail with delta flip positive. Stop below tail - 2 ticks. Target = day high or VAH.
- **Selling tail retest:** Mirror short.
- **Failed auction:** Fade — enter on return through the broken level. Target = opposite side of IB. Invalidation: re-break with expanding volume.
- **Unfinished business as target:** Register as high-probability target for current session. Bias exits toward it.

### Risk Management
- Stop: beyond the tail extreme (tail broken with volume = immediate reversal)
- Target: day high/low, VAH/VAL, or opposite IB edge
- Invalidation: tail broken with volume

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\auction.py` lines 101-152:

- **AUCT-01 Unfinished Business** (lines 101-135): non-zero bid at bar high = unfinished business upward (+1 direction); non-zero ask at bar low = unfinished business downward (-1 direction). Tracked in `self.unfinished_levels` dict for cross-bar persistence.
- **AUCT-02 Finished Auction** (lines 137-152): zero bid at bar high + non-zero ask = buyers exhausted (-1); zero ask at bar low + non-zero bid = sellers exhausted (+1).

`AuctionEngine.get_unfinished_levels()` (line 70): returns all tracked unfinished levels for use as targets.
`AuctionEngine.clear_finished_level(price)` (line 87): removes level when price returns to complete the auction.
`AuctionEngine.load_unfinished_levels(levels)` (line 74): cross-session restore of unfinished levels.

### Academic Basis
- Dalton, *Mind Over Markets*: buying/selling tails, single prints, failed auction definitions.
- Bacry & Muzy (2014): Hawkes self-excitation decays rapidly past a level — formal model for why failed auctions reverse quickly (excitation collapses after the break).

---

## AUCT-06: Poor Highs and Poor Lows (Unconfirmed Auction Extremes)

**Category**: Auction Theory
**Tags**: poor high, poor low, incomplete auction, weak extreme, retest, break
**DEEP6 Signal(s)**: AUCT-03 (Poor High/Low)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py`

### Concept
A poor high is a session high with <= 1 TPO of excess AND >= 2 adjacent columns of equal highs. It indicates weak-handed participants created the high — there was no aggressive rejection, just a drift to the extreme. Poor highs are statistically revisited and broken.

A poor low is the mirror.

The distinction from a buying/selling tail: a tail has >= 2 single TPOs showing aggressive rejection. A poor high/low has no such rejection — the extreme was formed passively, without conviction.

**Unsecured high/low:** Similar to poor high/low — extreme lacking a tail/excess. Behaves identically: statistically retested.

In DEEP6's footprint implementation, a poor high is detected when the volume at the bar high is significantly below average — the auction did not find strong participation at the extreme.

### Conditions / Setup
- **Poor high:** Volume at bar high < `cfg.poor_extreme_vol_ratio` × average level volume
- **Poor low:** Volume at bar low < `cfg.poor_extreme_vol_ratio` × average level volume
- Statistically revisited and broken (Dalton)

### Entry / Exit Rules
- **Poor high revisit on light volume (< 70% of 30-period avg):** Short. Stop above poor high + 3 ticks. Target = day POC. Requires absorption signal at high.
- **Poor high revisit on heavy volume (> 130% of avg):** Short breakout. Stop above retest high. Target = measured move of day range. (Heavy volume = break, light volume = fade — critical branch.)
- **Poor low revisit on light volume:** Long. Stop below poor low - 3 ticks. Target = day POC.
- **Poor low revisit on heavy volume:** Long breakout.

### Risk Management
- Stop: 3 ticks beyond the poor extreme
- Target: day POC (fade), or measured move (breakout)
- Invalidation: strong volume retest = buy breakout instead (for poor high) or sell breakdown (for poor low)

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\auction.py` lines 154-173:

- **AUCT-03 Poor High** (lines 158-165): `high_vol < avg_vol * self.config.poor_extreme_vol_ratio` → AuctionSignal with `AuctionType.POOR_HIGH`, direction=-1, strength=0.5.
- **AUCT-03 Poor Low** (lines 167-173): mirror, direction=+1.

Config: `AuctionConfig.poor_extreme_vol_ratio` in `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py`.

### Academic Basis
- Dalton, *Mind Over Markets*: poor high/low definitions, statistical retest behavior.
- Shadow Trader Glossary: poor high/low operational definitions.
- Trade Brigade: poor highs and lows trading guide.

---

## AUCT-07: Bracket Trading (Trading Within Established Value Area)

**Category**: Auction Theory
**Tags**: bracket, balance, responsive trade, value area, rotation, scalp
**DEEP6 Signal(s)**: E9 (VPOC pin), OAIR open type
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py`

### Concept
Bracket trading is the strategy of trading within an established value area — buying at VAL and selling at VAH, with POC as the midpoint target. It is the "responsive trade" in Dalton's framework.

Responsive activity: buying BELOW value or selling ABOVE value — expected behavior, fades the move back toward value. This is the dominant strategy during balance days.

Bracket trading is appropriate when:
- Value area is unchanged or overlapping from prior day (>= 80% overlap)
- Day type is Non-Trend, Normal, or OAIR (Open-Auction In-Range)
- No range extension has occurred
- GEX regime is positive (dealers stabilize, mean-reversion supported)

### Conditions / Setup
- Prior day VA overlaps current developing VA >= 80%
- No range extension (price rotating inside IB)
- OAIR open type: opens inside prior day's range and rotates around open
- Positive gamma regime (dealer stabilization supports bounce thesis)

### Entry / Exit Rules
- **Fade IBH toward POC:** Enter short at IBH, target POC. Stop beyond IBH + tick buffer.
- **Fade IBL toward POC:** Enter long at IBL, target POC. Stop beyond IBL - tick buffer.
- **OAIR + unchanged value:** Responsive scalps only. Fade IBH/IBL to POC. Disable trend logic. Max 2 trades per day.
- **E9 VPOC pin:** Bar touches VPOC then closes away → limit at VPOC ± 2 ticks. Target = opposite VA boundary.

### Risk Management
- Stop: beyond IB extreme + tick buffer
- Target: POC (primary), opposite IB edge (secondary)
- Invalidation: range extension occurs — immediately disable bracket logic, switch to extension playbook

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\auction.py` — AuctionState.BALANCED state.

E9 entry trigger in trade logic: VPOC pin with positive gamma regime → limit at VPOC ± 2 ticks. Full exit at target (no runner — pin is symmetric).

`AuctionState.BALANCED` fires when `balance_count >= config.balance_count_threshold` (lines 248-251).

### Academic Basis
- Dalton, *Markets in Profile*: responsive vs initiative activity framework.
- Jigsaw Trading (Peter Davies): "every trade is a bet on one of three auction outcomes: continuation, rotation, or failure." Rotation = bracket trade.

---

## AUCT-08: Trend Day vs Balance Day Structure

**Category**: Auction Theory
**Tags**: trend day, balance day, day type, P-shape, b-shape, OTF, initiative
**DEEP6 Signal(s)**: E9 state machine (BREAKOUT, BREAKDOWN, BALANCED), day-type classifier
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py`

### Concept
Day-type classification is the most important context decision in Market Profile. The wrong day-type assumption leads to fading trends or chasing rotations.

Six day types (Dalton, *Mind Over Markets* Ch. 4):

| Day Type | Signature | IB Width | Range vs IB |
|----------|-----------|----------|-------------|
| **Normal** | OTF both sides early; wide IB; two-sided all day | Wide | ~1x IB |
| **Normal Variation** | ~42% frequency; smaller IB; one OTF extends range one side | Medium | 1.5-2x IB |
| **Trend Day** | Open near one extreme, close near opposite; narrow IB; minimal horizontal development | Narrow | 2x-4x+ IB |
| **Double Distribution Trend** | Two distinct value areas separated by single prints | Narrow | 3x+ IB |
| **Neutral** | Extensions both sides of IB; close near mid-range or at extreme | Average | ~2x IB |
| **Non-Trend** | Narrow IB holds all day; D-shape; news-anticipation | Narrow | ~1x IB |

Profile shapes:
- **P-shape:** TPOs stack vertically left, thin upper range. Strong one-timeframe buyer conviction. Trend day from open.
- **b-shape:** Mirror. Strong seller conviction.

On a P-shape or b-shape day: disable reversal trades; only permit trend-continuation (stacked imbalance retests) for remainder of session.

### Conditions / Setup
- Classify by end of C-D period (90 minutes into RTH)
- Narrow IB + open-drive = trend day alert
- P-shape / b-shape detected by end of C-D period
- OTF (One-Time Framing): 3+ consecutive 30-min bars without violating prior bar's opposite extreme = trend in progress

### Entry / Exit Rules
- **Trend day:** Enter with trend on pullbacks that respect OTF boundary. Stop = OTF break (bar violates prior boundary).
- **Balance day:** Fade extremes toward POC. Responsive trade only.
- **P-shape / b-shape detected:** Disable reversal trades. Only stacked imbalance retests.
- **OTF break:** End of trend leg. Switch to responsive trade.

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\auction.py` — AuctionEngine state machine.

`AuctionState.BREAKOUT` / `AuctionState.BREAKDOWN` (lines 238-244): fires when range_pct >= `config.breakout_range_threshold` AND expanding in one direction.
`AuctionState.EXPLORING_UP` / `EXPLORING_DOWN` (lines 238-244): expanding but below breakout threshold.
`AuctionState.BALANCED` (lines 248-251): balance_count >= threshold.

### Academic Basis
- Dalton, *Mind Over Markets* Ch. 4: six day types, frequency estimates, next-day implications.
- Market Profile Info: P-shape and b-shape profile reading.
- Bacry & Muzy (2014): Hawkes branching ratio near 1 on trend days — formal basis for why trend days are self-reinforcing.

### Examples / Edge Cases
- **Trend day next-day implication:** Expect gap continuation or pullback to prior VAH/VAL. Avoid fading early next session.
- **Non-Trend next-day implication:** Volatility expansion likely next session. Position for breakout.
- **Neutral-Extreme close at high:** Next-day ORU open = gap-and-go bias. Scale-in long on first 5-min pullback.

---

## AUCT-09: Open-Type Classification

**Category**: Auction Theory
**Tags**: open type, open-drive, OTD, ORR, OAIR, OAOR, opening range
**DEEP6 Signal(s)**: E1/E2 (CONFIRMED_ABSORB open-drive), E3/E4 (GEX wall open-drive)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py`

### Concept
The daily open relative to prior day's value area is the primary bias filter. Dalton identifies five open types, each with a distinct trade plan:

| Open Type | Signature | Confidence | Entry Logic |
|-----------|-----------|-----------|-------------|
| **Open-Drive (OD)** | Opens and immediately auctions aggressively in one direction; no return through opening range | Highest | Enter WITH the drive on first pullback to opening range edge; never fade |
| **Open-Test-Drive (OTD)** | Opens, tests beyond a known reference to confirm no new business, then reverses and drives back | 2nd highest | Enter WITH the drive after the test fails |
| **Open-Rejection-Reverse (ORR)** | Opens, trades one direction, meets opposite activity, reverses back through opening range | Medium | Enter on reversal through open |
| **Open-Auction In-Range (OAIR)** | Opens inside prior day's range and rotates around open; no conviction | Low | Fade IB extremes toward POC; responsive trade |
| **Open-Auction Out-of-Range (OAOR)** | Opens outside prior day's range but then rotates; tentative directional bias | Medium | Wait for acceptance test |

The open range (first 1-5 minutes) is Dalton's primary "conviction proxy."

### Conditions / Setup
- **OD:** No return through opening range in first 15 minutes; aggressive directional move from open
- **OTD:** Tests beyond a known reference (prior day VAH/VAL/high/low), then reverses
- **ORR:** Opens, moves one direction, reverses back through opening range
- **OAIR:** Opens inside prior day's range, rotates around open
- **OAOR:** Opens outside prior day's range, then rotates back

### Entry / Exit Rules
- **OD-UP + ORU + no rejection:** Long on first pullback to opening range high. Stop = open - 4 ticks. Target = 2x IB projection. Kronos E10 must not be bearish.
- **OD-DOWN + ORD + no rejection:** Mirror short.
- **OTD-UP (test prior day low, reverse):** Long on reclaim of overnight low. Stop = tested low - 2 ticks. Target = prior day POC, then VAH.
- **ORR at prior day VAH:** Fade back to POC. Stop beyond VAH + 1 ATR(5min). Require exhaustion footprint at VAH.

### Risk Management
- OD: Stop = 2-4 ticks beyond the open
- OTD: Stop = beyond the tested reference + 2 ticks
- ORR: Stop = beyond rejected extreme
- OAIR: Stop = beyond IB + tick buffer

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\auction.py` — open-type detection feeds into E9 state machine.

E1/E2 entry triggers (CONFIRMED_ABSORB): fire on open-drive confirmation. E3/E4 (GEX wall confluence): immediate market entry on TYPE_A bar close at GEX wall.

Trade logic state machine: `C:\Users\Tea\DEEP6\.planning\research\pine\deep\trade_logic.md` §3, entries E1-E4 for open-drive patterns.

### Academic Basis
- Dalton, *Markets in Profile* Ch. 3: open-type classification, entry logic, stop placement.
- Nature of Markets — Opening Types Course 3: operational definitions and practical applications.
- SMB Capital (Bellafiore, *The PlayBook*): PreSet/Setup/Trigger/Manage/Exit lifecycle — open type is the PreSet.

---

## AUCT-10: Volume Void (LVN Gap Within Bar)

**Category**: Auction Theory
**Tags**: LVN, low volume node, volume void, fast move, gap-through, single prints
**DEEP6 Signal(s)**: AUCT-04 (Volume Void)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py`

### Concept
A Volume Void (AUCT-04) is a low-volume zone within a bar — multiple price levels with volume far below the bar's maximum. It indicates price moved through that zone quickly, with minimal participation. This is the footprint equivalent of a Market Profile LVN (Low Volume Node).

Volume voids are "fast lanes" — price tends to traverse them rapidly when revisited. They are NOT support or resistance; they are the absence of support or resistance. Do not enter countertrend inside a volume void.

The Axia JUMP technique (NASDAQ-specific): market crosses marked resistance, triggers stops, "jumps after two short rotations" creating an LVN. Entry on retest of the LVN with HVN above it.

### Conditions / Setup
- Multiple price levels within bar body with vol < `cfg.void_vol_ratio` × bar max level vol
- `void_count >= cfg.void_min_levels` (minimum number of thin levels)
- Direction: bar close > open = upward void (+1), bar close < open = downward void (-1)

### Entry / Exit Rules
- **LVN traversal:** When price traverses an LVN with stacked imbalance, target the adjacent HVN above/below. Do NOT enter countertrend inside the LVN.
- **LVN gap-through:** Fast traverse of low-volume node with stacked imbalances = price found no interest at LVN, goes to next HVN. Enter on pullback that halts mid-LVN. Stop = back inside originating VA. Target = next HVN.
- **Volume void as target:** Register as high-probability fast-traverse zone. Bias exits through it.

### Risk Management
- Stop: back inside the originating VA
- Target: next HVN in the direction of the void
- Invalidation: price re-enters LVN fully (acceptance building)

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\auction.py` lines 175-190:

- **AUCT-04 Volume Void** (lines 175-190): counts levels with `vol < max_vol * self.config.void_vol_ratio` AND `vol > 0`. Fires when `void_count >= self.config.void_min_levels`. Strength = `min(void_count / 7.0, 1.0)`.

Config: `AuctionConfig.void_vol_ratio`, `AuctionConfig.void_min_levels` in `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py`.

### Academic Basis
- Cont & de Larrard (2013): queue depletion at LVNs produces rapid price moves — formal basis for LVN fast-lane behavior.
- Axia Futures JUMP technique: LVN formation after stop-run, retest entry.

---

## AUCT-11: Market Sweep (Rapid Traversal with Increasing Volume)

**Category**: Auction Theory
**Tags**: market sweep, sweep, stop run, liquidity grab, increasing volume, breakout
**DEEP6 Signal(s)**: AUCT-05 (Market Sweep)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py`

### Concept
A Market Sweep (AUCT-05) is a rapid traversal of price levels with increasing volume as price moves through. The upper half of the bar has more volume than the lower half (for an up sweep), indicating accelerating participation as price moves higher.

This is distinct from a volume void: a sweep has increasing volume (conviction), while a void has decreasing volume (fast move through empty space).

Market sweeps are breakout accelerants. They indicate that new participants are joining the move as it progresses — the opposite of exhaustion.

The sweep/stop-run classifier: on a wick through prior-day H/L, if the next bar closes INSIDE the prior range AND opposite-delta print on close bar = SWEEP (fade). If the next bar closes OUTSIDE = BREAK (follow).

### Conditions / Setup
- Bar range > 0 AND >= `cfg.sweep_min_levels` price levels
- **Up sweep:** second half of bar (upper levels) has volume > first half × `cfg.sweep_vol_increase`
- **Down sweep:** lower half has volume > upper half × `cfg.sweep_vol_increase`

### Entry / Exit Rules
- **Market sweep up:** Continuation long. Enter on first pullback. Stop = below sweep low. Target = next structural level.
- **Market sweep down:** Mirror short.
- **Sweep vs break classifier:** Wick through prior H/L + next bar closes inside + opposite delta = SWEEP (fade). Next bar closes outside = BREAK (follow).

### Risk Management
- Stop: beyond the sweep extreme
- Target: next structural level in sweep direction
- Invalidation: sweep reverses (next bar closes back through sweep origin)

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\auction.py` lines 192-225:

- **AUCT-05 Market Sweep** (lines 192-225): compares first-half vs second-half volume. Up sweep: `second_half_vol > first_half_vol * self.config.sweep_vol_increase` (lines 205-210). Down sweep: mirror (lines 211-225). Strength = `min(second_half_vol / first_half_vol / 3, 1.0)`.

Config: `AuctionConfig.sweep_min_levels`, `AuctionConfig.sweep_vol_increase` in `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py`.

### Academic Basis
- Haghighi, Fallahpour & Eyvazlu (2016): Hawkes kernel shifts at price-limit events — same-direction excitation strengthens during sweeps (formal breakout-acceleration model).
- Bacry & Muzy (2014): branching ratio near 1 during sweeps — self-reinforcing flow.

---

## AUCT-12: E9 Auction State Machine

**Category**: Auction Theory
**Tags**: auction state machine, E9, exploring, balanced, breakout, breakdown, state
**DEEP6 Signal(s)**: E9 (Auction State Machine)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py`

### Concept
The E9 Auction State Machine tracks the current auction state of the market. It classifies each bar into one of five states based on whether price is expanding, contracting, or breaking out.

States:
- **EXPLORING_UP:** Price making higher highs, but not yet at breakout velocity
- **EXPLORING_DOWN:** Price making lower lows, but not yet at breakdown velocity
- **BALANCED:** Price rotating within a range (balance_count >= threshold)
- **BREAKOUT:** Price expanding upward at breakout velocity (range_pct >= breakout_range_threshold)
- **BREAKDOWN:** Price expanding downward at breakdown velocity

The state machine is the context layer for all entry triggers. BALANCED = responsive trade. BREAKOUT/BREAKDOWN = initiative trade. EXPLORING = wait for confirmation.

### Conditions / Setup
- `expanding_up = bar.high > prev_high`
- `expanding_down = bar.low < prev_low`
- `range_pct = bar.bar_range / (prev_high - prev_low)`
- BREAKOUT: expanding_up AND NOT expanding_down AND range_pct >= `config.breakout_range_threshold`
- BALANCED: NOT expanding_up AND NOT expanding_down for >= `config.balance_count_threshold` consecutive bars

### Entry / Exit Rules
- **BALANCED:** Enable responsive trade (bracket, fade extremes). Disable trend-continuation.
- **BREAKOUT/BREAKDOWN:** Enable initiative trade (trend-continuation, stacked imbalance retests). Disable reversal.
- **EXPLORING:** Wait for confirmation. Neither responsive nor initiative trade until state resolves.

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\auction.py` lines 232-254:

`_update_state()` method transitions between states based on `expanding_up`, `expanding_down`, and `range_pct`. State is accessible via `AuctionEngine.state`.

`AuctionEngine.reset()` (line 63): resets state to BALANCED at session start.

Config: `AuctionConfig.breakout_range_threshold`, `AuctionConfig.balance_count_threshold` in `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py`.

### Academic Basis
- Jigsaw Trading (Peter Davies): "every trade is a bet on one of three auction outcomes: continuation, rotation, or failure." E9 state machine encodes this three-way classification.
- Dalton, *Markets in Profile*: balance vs imbalance as the fundamental market state.

---

## AUCT-13: Footprint × Market Profile Synthesis

**Category**: Auction Theory
**Tags**: synthesis, footprint, market profile, context, trigger, Tom Alexander, confluence
**DEEP6 Signal(s)**: All signals — this is the integration layer
**Python File**: All engines

### Concept
Tom Alexander (*Practical Trading Applications of Market Profile*, 2009) and practitioners like Mike Valtos (OrderFlows) and John Grady (No BS Day Trading) argue that Market Profile provides *context* (WHERE to trade) and order flow / footprint provides *trigger* (WHEN to trade).

The footprint read is different at each MP reference:

| MP Reference | Expected Footprint on Entry |
|--------------|-----------------------------|
| At prior day POC / nPOC | Absorption (large resting orders absorb aggressors, delta divergence). Trade with absorbing side. |
| At VAH or VAL (responsive) | Exhaustion of the aggressor: delta declines as price presses; stacked imbalances fail to extend. Fade. |
| At VAH or VAL (initiative break) | Acceptance: sustained delta in breakout direction; volume expansion; no immediate return. Continuation. |
| At prior day high/low (poor) | Absorption PLUS resting liquidity sweep; stop-run pattern. Delta flip after sweep = fade. Delta continues = break. |
| At single print (traversing) | Minimal footprint — single prints are LOW-volume zones. Price should move fast. Do NOT enter IN a single print. |
| At buying/selling tail | Aggressive one-sided delta on formation. On retest: absorption (tail defended) or exhaustion (tail fails). |
| At IB extreme (post-period C) | Confirm extension with stacked imbalance + delta expansion. Break without these = likely failed extension. |
| At composite HVN (multi-day POC) | Strongest fade candidates. Absorption + exhaustion almost always precede reversals here. |

DEEP6's 44-signal stack should be evaluated *conditionally at MP-defined levels* — not in isolation. This is Alexander's core teaching: signals are meaningless without context.

### Conditions / Setup
- Map T1/T2 levels pre-market (weekly H/L, prior-day VPOC/VAH/VAL, gamma walls)
- Map developing T3/T4 (IB, VWAP, current-session VPOC)
- Establish day-type hypothesis (trend/balance/open-drive)
- Only evaluate footprint signals at MP-defined levels

### Entry / Exit Rules
The 15 trade-plan generators from `C:\Users\Tea\DEEP6\.planning\research\pine\deep\auction_theory.md` §9 combine MP context with footprint triggers. Key examples:

1. **OD-UP + ORU + no rejection:** Long on first pullback to opening range high. Kronos E10 must not be bearish.
2. **Absorption at prior day high + Kronos bearish E10 + IB extension failure up:** High-conviction short. Stop = prior day high + 2 ticks. Target = prior day POC, then VAL.
3. **Failed IB extension up (period C closes back inside IB):** Short to opposite IB edge. 70-75% historical probability.
4. **Naked POC magnet:** Long toward nPOC, exit AT nPOC, flip short if exhaustion prints.
5. **Poor high revisit on light volume:** Short. Requires absorption signal at high.

### DEEP6 Implementation
The synthesis layer is the trade decision state machine: `C:\Users\Tea\DEEP6\.planning\research\pine\deep\trade_logic.md` §2.

Data flow: `bar_close → engines/* → LevelFactory → LevelBus → ConfluenceRules → scorer → TradeDecisionMachine → OrderIntent → async-rithmic ORDER_PLANT`.

The `TradeDecisionMachine` consumes `ScorerResult` (compressed 44-signal output) + `LevelBus` (MP levels) + `GexSignal` (gamma context) and emits `OrderIntent` objects.

### Academic Basis
- Alexander, T. *Practical Trading Applications of Market Profile* (Alexander Trading, 2009): footprint × MP synthesis framework.
- SMB Capital (Bellafiore, *The PlayBook*): "Level-first, trigger-second. A level without OF confirmation is not a trade. OF without a level is noise."
- Axia Futures: Three Clues framework — absorption at level, defense on retest, no opposing pressure.
- Jigsaw Trading (Davies): Three Components — absorption, one side fading, opposite side stepping in.

---

## Multi-Timeframe Level Hierarchy

From `C:\Users\Tea\DEEP6\.planning\research\pine\deep\practitioners.md` §3.

| Tier | Level Types | Weight | Half-life |
|------|-------------|--------|-----------|
| **T1 (macro)** | Weekly H/L, prior-week VPOC, monthly VPOC, gamma flip, largest call/put wall | 5 | Weeks |
| **T2 (swing)** | Prior-day H/L, prior-day VPOC/VAH/VAL, 2nd/3rd gamma wall | 3 | Days |
| **T3 (session)** | IB H/L, overnight H/L, RTH VWAP, opening print | 2 | Session |
| **T4 (intraday)** | Current-session developing VPOC/VAH/VAL, intraday LVN, 30-min pivots | 1 | Minutes-hours |

**Confluence rule:** A level is "A-grade" when >= 2 tiers align within a narrow band (NQ: <= 5 points). A-grade levels are where footprint patterns should be trusted.

**DEEP6 confidence weighting:**
- A-grade confluence (T1+T2, or T1+T2+T3): multiply level-based signals × 1.5
- B-grade (T2 alone, or T2+T3): × 1.0
- C-grade (T3 or T4 alone): × 0.6
- No level within threshold: do not trade reversal patterns; only trend-continuation (stacked imbalance on break)

---

*Last verified: 2026-05-12*
*Source files: `.planning/research/pine/deep/auction_theory.md`, `.planning/research/pine/deep/practitioners.md`, `.planning/research/pine/deep/trade_logic.md`, `deep6/engines/auction.py`*
