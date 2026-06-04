# Classic Trading Patterns Catalog

**Last verified: 2026-05-12**
**Scope:** 15 classic chart and order-flow patterns documented for NQ futures trading. Each entry follows the knowledge.md schema. DEEP6 signal references use the 44-signal engine naming convention.

---

## CP-01: Head and Shoulders (and Inverse)

**Category**: Pattern
**Tags**: reversal, three-peak, neckline, volume confirmation
**Timeframe**: intraday (15m–1h), swing (daily)
**Market Condition**: trending (topping or bottoming)
**DEEP6 Signal(s)**: ABS-01 (absorption at neckline), EXH-01 (exhaustion at head), CVD divergence at right shoulder

### Concept
Three-peak structure where the middle peak (head) exceeds both shoulders. The pattern reflects a failed attempt to extend a trend: the left shoulder is the first push, the head is the climactic extension, and the right shoulder is the failed retest. Volume typically declines from left shoulder to right shoulder, confirming weakening conviction. The inverse (IH&S) is the mirror at bottoms.

### Conditions / Setup
- Established prior trend (at least 3 swing legs)
- Left shoulder: high volume push, moderate pullback
- Head: highest high (or lowest low for inverse), volume may spike but often less than left shoulder
- Right shoulder: lower high than head, volume clearly declining
- Neckline: drawn connecting the two reaction lows (or highs for inverse); can be flat or slightly sloped

### Entry / Exit Rules
- **Entry**: break and close below neckline (or above for inverse); aggressive traders enter on neckline retest
- **Stop**: above right shoulder high (or below for inverse)
- **Target**: measured move = distance from head to neckline, projected from neckline break

### Risk Management
- Avoid if neckline is steeply sloped (>30 degrees) — reliability drops
- Require volume expansion on the neckline break
- On NQ: neckline breaks without volume expansion fail ~40% of the time intraday

---

## CP-02: Double Top / Double Bottom

**Category**: Pattern
**Tags**: reversal, M-pattern, W-pattern, equal highs, equal lows
**Timeframe**: scalping (1m–5m), intraday (15m–1h)
**Market Condition**: trending, at structural levels
**DEEP6 Signal(s)**: EXH-01 (exhaustion on second touch), ABS-01 (absorption at neckline), MS-12 (ExhaustionPostBreak)

### Concept
Price tests a level twice, fails both times, and reverses. The double top (M) forms at resistance; the double bottom (W) at support. The second touch is the key: it either shows equal or declining volume (confirming the pattern) or expanding volume (invalidating it). The "neckline" is the swing low between the two tops (or swing high between two bottoms).

### Conditions / Setup
- Two peaks (or troughs) within 1–3% of each other in price
- Second peak: volume should be less than first peak
- Neckline: the reaction low/high between the two peaks
- Time between peaks: at least 2–4 bars on the chosen timeframe

### Entry / Exit Rules
- **Entry**: break below neckline (double top) or above neckline (double bottom)
- **Stop**: above the second peak (or below second trough)
- **Target**: measured move = height of the pattern from peak to neckline, projected from break

### Risk Management
- False breaks are common on NQ near round numbers — wait for a full bar close beyond neckline
- If second peak exceeds first by more than 0.5 ATR, the pattern is likely a continuation, not reversal

---

## CP-03: Bull Flag / Bear Flag and Pennant

**Category**: Pattern
**Tags**: continuation, consolidation, measured move, momentum
**Timeframe**: scalping (1m–5m), intraday (15m–30m)
**Market Condition**: trending
**DEEP6 Signal(s)**: STACKED_IMBALANCE (on breakout), MS-07 (Hawkes branching on breakout)

### Concept
After a sharp impulsive move (the flagpole), price consolidates in a tight, slightly counter-trend channel (flag) or symmetrical triangle (pennant). The consolidation represents profit-taking and weak-hand shakeout. The breakout from the flag/pennant continues the original trend. Flags are the most reliable continuation pattern in trending markets.

### Conditions / Setup
- **Flagpole**: sharp, high-volume move covering at least 1.5× ATR in 3–5 bars
- **Flag**: 3–7 bars of counter-trend drift, declining volume, parallel channel
- **Pennant**: converging trendlines, declining volume, symmetric
- Volume should contract during consolidation and expand on breakout

### Entry / Exit Rules
- **Entry**: break above flag upper boundary (bull) or below lower boundary (bear)
- **Stop**: below flag low (bull) or above flag high (bear)
- **Target**: measured move = flagpole length, projected from breakout point

### Risk Management
- Flags that consolidate more than 50% of the flagpole are suspect — likely a reversal, not continuation
- On NQ: best flags form in 2–5 bars; longer consolidations lose momentum

---

## CP-04: Ascending / Descending Triangle

**Category**: Pattern
**Tags**: continuation, breakout, horizontal resistance, rising support
**Timeframe**: intraday (15m–1h), swing
**Market Condition**: trending or transitioning
**DEEP6 Signal(s)**: MS-11 (DepthAsymmetry at flat resistance), ABS-01 (absorption at flat level)

### Concept
Ascending triangle: flat resistance with rising lows — buyers are increasingly aggressive, sellers are defending a fixed level. Each test of resistance absorbs more selling until supply is exhausted. Descending triangle is the mirror. The flat side is the key level; the pattern resolves when one side runs out of participants.

### Conditions / Setup
- **Ascending**: at least 2 equal highs (flat resistance) + 2 higher lows
- **Descending**: at least 2 equal lows (flat support) + 2 lower highs
- Minimum 3 touches of the flat side
- Volume typically contracts during formation

### Entry / Exit Rules
- **Entry**: close beyond the flat side (resistance for ascending, support for descending)
- **Stop**: below the last higher low (ascending) or above last lower high (descending)
- **Target**: measured move = widest part of triangle, projected from breakout

### Risk Management
- Breakouts in the final third of the triangle (near apex) are less reliable
- Require volume expansion on breakout; flat-side breaks on low volume fail ~50%

---

## CP-05: Cup and Handle

**Category**: Pattern
**Tags**: continuation, rounded bottom, consolidation, breakout
**Timeframe**: swing (daily–weekly), intraday (1h–4h)
**Market Condition**: uptrend, post-correction
**DEEP6 Signal(s)**: ABS-01 (absorption at handle low), CVD divergence during handle

### Concept
A rounded bottom (cup) followed by a small consolidation (handle) before a breakout to new highs. The cup represents a gradual shift from distribution to accumulation. The handle is a final shakeout of weak longs before the breakout. The rounded shape (vs V-shape) indicates orderly accumulation rather than panic buying.

### Conditions / Setup
- Cup: U-shaped, not V-shaped; depth 12–35% from prior high
- Cup duration: weeks to months on daily; hours on intraday
- Handle: forms in upper third of cup; retraces 10–15% of cup depth; declining volume
- Prior uptrend of at least 30% before the cup

### Entry / Exit Rules
- **Entry**: break above the cup's prior high (the "rim")
- **Stop**: below handle low
- **Target**: measured move = cup depth, projected from rim breakout

### Risk Management
- Handles that retrace more than 50% of the cup are suspect
- Volume on breakout should be at least 1.5× average

---

## CP-06: Wedge (Rising / Falling)

**Category**: Pattern
**Tags**: reversal, continuation, converging trendlines, exhaustion
**Timeframe**: intraday (15m–1h), swing
**Market Condition**: trending
**DEEP6 Signal(s)**: EXH-01 (exhaustion at wedge apex), CVD divergence, MS-06 (CVDDivergenceAtLevel)

### Concept
Two converging trendlines both sloping in the same direction. A rising wedge (both lines slope up) is bearish — price is making higher highs and higher lows but with declining momentum. A falling wedge (both lines slope down) is bullish. The wedge compresses energy until a breakout occurs, typically in the opposite direction of the wedge slope.

### Conditions / Setup
- At least 4 touches (2 per trendline) to define the wedge
- Volume declining as the wedge narrows
- Rising wedge: bearish divergence in delta or CVD is a strong confirmation
- Falling wedge: bullish divergence in delta or CVD

### Entry / Exit Rules
- **Entry**: break below lower trendline (rising wedge) or above upper trendline (falling wedge)
- **Stop**: above the most recent high within the wedge (rising) or below most recent low (falling)
- **Target**: measured move = widest part of wedge, projected from breakout

### Risk Management
- Wedges that break in the direction of the slope (continuation) do occur — require volume confirmation to distinguish
- On NQ: rising wedges near prior-day highs or VAH are highest-probability reversal setups

---

## CP-07: VWAP Reclaim / Rejection

**Category**: Pattern
**Tags**: intraday, VWAP, mean reversion, institutional reference
**Timeframe**: scalping (1m–5m), intraday (15m)
**Market Condition**: any
**DEEP6 Signal(s)**: ABS-01 (absorption at VWAP), MS-03 (QueueImbalanceBand at VWAP), MS-04 (VPINRegimeShift)

### Concept
VWAP (Volume-Weighted Average Price) is the primary institutional benchmark for intraday execution. Price above VWAP = buyers in control; below = sellers. A VWAP reclaim (price crosses from below to above and holds) signals a shift in intraday control. A VWAP rejection (price tests VWAP from above, fails, and reverses) confirms the downtrend. The key is whether price "accepts" above/below VWAP (3+ bars holding) or merely touches and reverses.

### Conditions / Setup
- **Reclaim**: price was below VWAP, crosses above, and closes 2+ consecutive bars above
- **Rejection**: price approaches VWAP from below, touches or slightly exceeds, then closes back below
- Volume on the reclaim/rejection bar should be above average
- Best setups occur when VWAP aligns with a Market Profile level (VAH, VAL, POC)

### Entry / Exit Rules
- **Reclaim entry**: buy on first pullback to VWAP after reclaim; stop below VWAP − 1 ATR(5m)
- **Rejection entry**: sell on close back below VWAP; stop above VWAP + 1 ATR(5m)
- **Target**: prior swing high/low, or next MP level

### Risk Management
- VWAP is less reliable in the first 30 minutes of RTH (developing)
- On trend days, VWAP reclaims fail frequently — check day-type before trading VWAP fades

---

## CP-08: Opening Range Breakout (ORB)

**Category**: Pattern
**Tags**: breakout, opening range, momentum, session open
**Timeframe**: scalping (1m–5m), intraday (15m)
**Market Condition**: trending, volatile
**DEEP6 Signal(s)**: MS-07 (Hawkes branching on breakout), STACKED_IMBALANCE, MS-09 (AggressorDominanceAtL)

### Concept
The opening range (first 5, 15, or 30 minutes of RTH) defines the initial auction. A breakout above the opening range high (ORH) or below the opening range low (ORL) signals that one side has won the opening auction and is extending. The ORB is one of the most statistically reliable intraday setups because it captures the resolution of overnight positioning and pre-market sentiment.

### Conditions / Setup
- Define the opening range: first 5m, 15m, or 30m (30m = Dalton's Initial Balance)
- **Breakout**: price closes beyond ORH or ORL on a 5m or 15m bar
- Volume on breakout bar should exceed the average of the opening range bars
- Best when the opening range is narrow (below 20-day average IB width)

### Entry / Exit Rules
- **Entry**: close beyond ORH/ORL, or on first pullback to the broken level
- **Stop**: back inside the opening range (below ORH for longs, above ORL for shorts)
- **Target**: 1× opening range width projected from breakout; 2× on trend days

### Risk Management
- Failed ORBs (price breaks then returns inside) are strong reversal signals — flip bias
- On NQ: ORBs on FOMC days and CPI days have much higher follow-through than quiet days
- Avoid ORBs when the opening range is wider than 1.5× the 20-day average (already extended)

---

## CP-09: Gap Fill Pattern

**Category**: Pattern
**Tags**: gap, mean reversion, overnight, unfilled gap
**Timeframe**: intraday (15m–1h)
**Market Condition**: any
**DEEP6 Signal(s)**: MS-06 (CVDDivergenceAtLevel at gap fill zone), ABS-01 (absorption at gap edge)

### Concept
A gap occurs when the opening price is significantly above or below the prior session's close. Gaps create "unfilled" price zones that act as magnets — price tends to return to fill them. On NQ, gaps above 0.3% of price fill within the session approximately 65–70% of the time. The gap fill trade fades the opening direction, targeting the prior close.

### Conditions / Setup
- **Gap up**: today's open > yesterday's close by at least 0.2% (NQ: ~4+ points)
- **Gap down**: today's open < yesterday's close by at least 0.2%
- Best gap fills: gaps that open within the prior day's range (not outside-range gaps)
- Confirm with opening type: OAIR or ORR opens are most likely to fill; OD opens are least likely

### Entry / Exit Rules
- **Gap up fill entry**: short when price fails to extend above the open in first 15 min; stop above opening high; target = prior close
- **Gap down fill entry**: long when price fails to extend below the open; stop below opening low; target = prior close
- **Partial fill**: take 50% off at midpoint of gap; trail stop on remainder

### Risk Management
- Outside-range gaps (open beyond prior day's entire range) fill less than 40% of the time — avoid fading these
- News-driven gaps (FOMC, CPI, earnings) have lower fill rates — reduce size or skip

---

## CP-10: Failed Breakout (Fakeout Reversal)

**Category**: Pattern
**Tags**: reversal, fakeout, stop hunt, liquidity sweep, trap
**Timeframe**: scalping (1m–5m), intraday (15m)
**Market Condition**: ranging, at structural levels
**DEEP6 Signal(s)**: MS-12 (ExhaustionPostBreak), ABS-01 (absorption after sweep), MS-08 (SpoofSuppressor)

### Concept
Price breaks a key level (prior high, prior low, IB extreme, round number), triggers stop orders and breakout buyers/sellers, then immediately reverses back inside. The "fakeout" traps participants on the wrong side, creating fuel for a sharp move in the opposite direction. This is one of the highest-probability setups in NQ because the trapped participants must exit, adding momentum to the reversal.

### Conditions / Setup
- Price breaks a well-defined level (at least 2 prior touches)
- Break is on below-average volume OR volume spikes then immediately collapses
- Price closes back inside the level within 1–3 bars of the break
- Delta divergence: price made new extreme but delta did not confirm

### Entry / Exit Rules
- **Entry**: close back inside the broken level; or on the bar that closes back inside
- **Stop**: beyond the fakeout extreme + 1 tick
- **Target**: opposite side of the range, or prior swing in the reversal direction

### Risk Management
- Require the close-back-inside to happen within 3 bars — longer delays reduce reliability
- On NQ: fakeouts at round numbers (21000, 21500, etc.) are extremely common and high-probability

---

## CP-11: Inside Bar / Outside Bar

**Category**: Pattern
**Tags**: consolidation, volatility contraction, breakout, NR4, NR7
**Timeframe**: intraday (15m–1h), swing (daily)
**Market Condition**: any
**DEEP6 Signal(s)**: MS-11 (DepthAsymmetry on breakout), MS-07 (Hawkes branching on breakout)

### Concept
An inside bar is a bar whose high and low are entirely within the prior bar's range — a volatility contraction. It signals indecision and often precedes a directional move. An outside bar (engulfing) exceeds both the prior high and low, signaling a volatility expansion and often a reversal. NR4 (narrowest range of last 4 bars) and NR7 are stronger inside-bar variants.

### Conditions / Setup
- **Inside bar**: current high < prior high AND current low > prior low
- **NR4/NR7**: current bar has the narrowest range of the last 4 or 7 bars
- **Outside bar**: current high > prior high AND current low < prior low
- Context matters: inside bars after a trend are continuation setups; inside bars at extremes are reversal setups

### Entry / Exit Rules
- **Inside bar breakout**: buy stop above inside bar high; sell stop below inside bar low; take whichever triggers first
- **Stop**: opposite side of the inside bar
- **Outside bar reversal**: enter in the direction of the close (bullish close = long); stop beyond the outside bar extreme

### Risk Management
- Inside bars in choppy markets produce many false breakouts — require a trend context or level confluence
- Multiple consecutive inside bars (compression) produce the strongest breakouts

---

## CP-12: Spike and Ledge

**Category**: Pattern
**Tags**: continuation, spike, consolidation, ledge, Market Profile
**Timeframe**: intraday (15m–1h)
**Market Condition**: trending
**DEEP6 Signal(s)**: MS-09 (AggressorDominanceAtL), STACKED_IMBALANCE, MS-07 (Hawkes branching)

### Concept
A spike is a sharp, fast move (often 3–5 bars) that creates a low-volume zone. A ledge forms when price consolidates just above (bull spike) or below (bear spike) the spike's origin, creating a tight range. The ledge is the "launch pad" for the next leg in the spike's direction. This is the Market Profile "spike and ledge" pattern — the ledge represents acceptance of the new price level.

### Conditions / Setup
- **Spike**: 3–5 bars moving sharply in one direction, covering at least 1.5× ATR
- **Ledge**: 3–8 bars of tight consolidation (range < 30% of spike range) at the spike's terminus
- Volume during ledge should be below average
- The spike's origin (base) becomes strong support/resistance

### Entry / Exit Rules
- **Entry**: break of the ledge in the spike's direction; or on pullback to ledge midpoint
- **Stop**: below ledge low (bull) or above ledge high (bear)
- **Target**: measured move = spike length, projected from ledge breakout

### Risk Management
- Ledges that retrace more than 50% of the spike are suspect — likely a reversal
- On NQ: spike-and-ledge patterns on 5m charts during trend days are among the cleanest continuation setups

---

## CP-13: Three Drives Pattern

**Category**: Pattern
**Tags**: reversal, harmonic, exhaustion, three pushes
**Timeframe**: intraday (15m–1h), swing
**Market Condition**: trending (late stage)
**DEEP6 Signal(s)**: EXH-01 (exhaustion on third drive), CVD divergence on third drive, MS-06 (CVDDivergenceAtLevel)

### Concept
Three successive pushes in the same direction, each with declining momentum. The third drive is the exhaustion point — price makes a new extreme but with significantly less volume and delta than the first or second drive. The pattern reflects the final capitulation of trend followers before a reversal. Each drive typically retraces 61.8% of the prior drive before the next push.

### Conditions / Setup
- Three clear swing highs (bull) or swing lows (bear) in the same direction
- Each successive extreme should show declining volume and/or delta
- Retracements between drives: ideally 61.8% Fibonacci
- Third drive often terminates at a structural level (prior high, round number, VAH/VAL)

### Entry / Exit Rules
- **Entry**: reversal bar after the third drive; or on break of the most recent swing low (bull three drives) or high (bear)
- **Stop**: beyond the third drive extreme
- **Target**: retracement to the origin of the first drive; or 50% of the entire three-drive range

### Risk Management
- Three drives can extend to four or five in strong trends — require a structural level at the third drive for higher confidence
- CVD divergence on the third drive is the strongest confirmation

---

## CP-14: Liquidity Sweep Reversal

**Category**: Pattern
**Tags**: reversal, stop hunt, liquidity, equal highs/lows, ICT
**Timeframe**: scalping (1m–5m), intraday (15m)
**Market Condition**: ranging, at structural levels
**DEEP6 Signal(s)**: MS-12 (ExhaustionPostBreak), ABS-01 (absorption after sweep), MS-09 (AggressorDominanceAtL)

### Concept
Institutional participants deliberately push price through obvious stop clusters (equal highs, equal lows, prior session extremes) to fill large orders at better prices. The sweep triggers retail stops, creating a brief spike beyond the level, then price reverses sharply as the institution has filled its position. The reversal is fast and often covers the entire sweep within 1–3 bars.

### Conditions / Setup
- Two or more equal highs or equal lows (within 2–3 ticks of each other) — obvious stop cluster
- Price sweeps beyond the equal highs/lows by 2–10 ticks
- Sweep bar closes back inside the prior range within the same bar or next bar
- Volume spike on the sweep bar (stops being triggered)

### Entry / Exit Rules
- **Entry**: close back inside the prior range after the sweep; or on the next bar's open if sweep bar closes back inside
- **Stop**: beyond the sweep extreme + 2 ticks
- **Target**: opposite side of the range; prior swing in reversal direction

### Risk Management
- Sweeps that do not close back inside within 2 bars are likely genuine breakouts — do not fade
- On NQ: overnight equal highs/lows are the most reliable sweep targets during the first 30 minutes of RTH

---

## CP-15: Orderblock Entry

**Category**: Pattern
**Tags**: reversal, orderblock, institutional, ICT, supply/demand
**Timeframe**: intraday (5m–15m), swing
**Market Condition**: trending, at structural levels
**DEEP6 Signal(s)**: ABS-01 (absorption at orderblock), MS-02 (IcebergAtLevel), MS-03 (QueueImbalanceBand)

### Concept
An orderblock is the last opposing candle before a strong impulsive move. It represents the price zone where institutional orders were placed. When price returns to this zone, the remaining unfilled institutional orders act as support/resistance, creating a high-probability reversal. Bullish orderblock: last bearish candle before a strong bullish impulse. Bearish orderblock: last bullish candle before a strong bearish impulse.

### Conditions / Setup
- Identify a strong impulsive move (at least 3 consecutive bars in one direction, covering 1.5× ATR)
- **Bullish orderblock**: the last bearish (red) candle immediately before the impulse up
- **Bearish orderblock**: the last bullish (green) candle immediately before the impulse down
- The orderblock zone = the body of that candle (open to close)
- Best orderblocks are at structural levels (prior day H/L, VAH/VAL, round numbers)

### Entry / Exit Rules
- **Entry**: price returns to the orderblock zone; enter at the 50% level of the orderblock body
- **Stop**: beyond the orderblock's wick extreme (full candle, not just body)
- **Target**: the origin of the impulse move; or the next structural level in the impulse direction

### Risk Management
- Orderblocks that have been tested more than once lose reliability — fresh (untested) orderblocks are strongest
- Require DEEP6 absorption signal at the orderblock zone for highest-confidence entries
- On NQ: orderblocks at prior-day highs/lows combined with gamma levels are the highest-probability setups

---

*Last verified: 2026-05-12*
