# Strategy History — Every Proven Trading Edge

A complete historical record of systematic trading edges from pit trading to
algorithmic markets. Each era produced distinct, documented edges. Many died.
A few survived. Understanding why separates signal from noise.

---

## ERA 1: FLOOR TRADING (pre-1993)

### What pit traders watched

The pit was a physical information market. Traders extracted edge from signals
that no electronic system could replicate at the time:

**Order flow through the pit**
- Who was buying or selling aggressively (broker identity)
- Size and urgency of orders (nervous broker = stop order incoming)
- Broker hand signals and body language (each firm had recognizable patterns)
- The "feel" of the pit — noise level, crowd density, emotional temperature

**Tape reading (price/volume interpretation)**
- Jesse Livermore's method: watch how price responds to volume
- If large volume produces small price movement = absorption (supply/demand balanced)
- If small volume produces large price movement = thin book, momentum likely
- Repeated tests of a level with declining volume = exhaustion

**Broker identity signals**
- Each clearing firm had a known style: Goldman Sachs brokers executed differently than retail brokers
- Recognizing a Goldman broker buying aggressively = institutional accumulation
- This edge was entirely human-network-based and died with electronic trading

### Documented edges

**Locals as market makers: spread capture**
- Locals stood in the pit and provided two-sided quotes
- Edge: bid-ask spread (typically 1-2 ticks in S&P pit)
- Risk: adverse selection from informed order flow
- Survival requirement: read the order flow well enough to step aside when informed traders arrived
- This edge migrated to HFT market makers after 1993

**Reading the tape: price/volume interpretation**
- Documented by Richard Wyckoff (1910-1930s), Jesse Livermore (1920s-1940s)
- Core principle: price and volume together reveal the intentions of large operators
- Wyckoff's "composite operator" concept: large institutions leave footprints in the tape
- Absorption: large volume at a level with no price progress = institutional buying/selling
- This edge survived into electronic markets as footprint chart analysis

**Scalping at the BBO: queue position advantage**
- Locals with physical proximity to the pit had first-mover advantage on fills
- Edge: fill at better price than electronic participants
- Died completely with electronic trading (latency replaced physical proximity)

**Pit noise as signal**
- Sudden silence = something is wrong (news incoming, large order)
- Roar = momentum, follow it
- Died with the pit

---

## ERA 2: EARLY ELECTRONIC (1993-2005)

### The SOES Bandits (NASDAQ day traders)

The Small Order Execution System (SOES) was designed to protect retail investors
after the 1987 crash. Market makers were required to honor their quotes for small
orders. Day traders exploited this.

**The edge**:
- SOES mandated execution at posted quotes for orders up to 1,000 shares
- Market makers were slow to update quotes after news
- SOES bandits would hit stale quotes before market makers could update
- Edge: 1-5 ticks per trade, dozens of trades per day

**Why it worked**:
- Market makers had no obligation to update quotes instantly
- SOES execution was faster than phone-based quote updates
- Information asymmetry: bandit knew news, market maker hadn't updated yet

**Why it died**:
- NASDAQ reduced SOES order size limits (1998)
- Market makers automated quote updates
- Decimalization (2001) compressed spreads from 1/8 to 1 cent, killing the edge
- ECNs (Island, Archipelago) created direct competition

**Lesson**: Regulatory arbitrage edges die when regulators or market structure adapts.

### Level 2 reading strategies (what worked before HFT)

Before HFT, Level 2 quotes were genuine signals. Market makers posted real
intentions (mostly). Strategies that worked:

**Ax identification**:
- Each stock had a dominant market maker ("the ax") who controlled price
- Identify the ax by watching which MM consistently absorbed large orders
- Trade with the ax: if Goldman is the ax and they're lifting offers, buy

**Quote fade detection**:
- Market maker posts large bid, then pulls it as price approaches
- Pre-HFT: this was a human decision, took 2-5 seconds
- Edge: recognize the fade pattern, don't buy into fake support

**Level 2 momentum**:
- Watch for market makers stacking on one side
- Multiple MMs moving to same side = directional signal
- Worked until HFT made Level 2 a battlefield of spoofing

**Why these died**:
- HFT firms began posting and cancelling quotes in microseconds
- Level 2 became noise: 99% of quotes were never intended to fill
- Human reaction time (200-500ms) couldn't compete with HFT (< 1ms)

### Statistical arbitrage origin: pairs trading

Nunzio Tartaglia's team at Morgan Stanley (1987) discovered that correlated
stocks mean-revert to their historical spread. This became the foundation of
quantitative equity trading.

**The edge**:
- Two correlated stocks (e.g., Coke and Pepsi) diverge temporarily
- The spread mean-reverts with high probability
- Buy the underperformer, short the outperformer, wait for convergence

**Evidence**:
- Gatev, Goetzmann & Rouwenhorst (2006): pairs trading earned 11% annualized
  excess returns from 1962-2002 with Sharpe ratio ~0.6
- Returns concentrated in first 6 months after pair formation
- Works best in liquid, correlated markets (S&P 500 components)

**Why it degraded**:
- Crowding: too many funds running the same strategy
- HFT arbitrage: spreads close faster than human traders can react
- Correlation breakdown during crises (2008, 2020)
- Still works at longer timescales (weekly/monthly) but not intraday

### Early momentum strategies (Jegadeesh & Titman 1993)

**The finding**:
- Stocks that performed well over the past 3-12 months continue to outperform
  over the next 3-12 months
- Jegadeesh & Titman (1993): 12-month momentum portfolio earned 1% per month
  excess return from 1965-1989
- Fama & French (1996) confirmed momentum as a factor anomaly

**Why it works**:
- Underreaction to news: investors update beliefs slowly
- Institutional herding: fund managers chase performance
- Earnings momentum: good earnings predict future good earnings

**Decay**:
- Momentum crashes during market reversals (2009, 2020)
- Works best in trending markets, fails in choppy/mean-reverting regimes
- Still works at 1-12 month horizon; intraday momentum is different (see below)

### Index rebalancing arbitrage

**The edge**:
- When a stock is added to the S&P 500, index funds must buy it
- Announcement to effective date: 5-10 days
- Buy the stock after announcement, sell to index funds on effective date

**Evidence**:
- Shleifer (1986): S&P 500 additions earn 2.8% abnormal return on announcement
- Harris & Gurel (1986): price pressure effect, partially reverses after rebalancing
- Lynch & Mendenhall (1997): 3.8% abnormal return for additions, -1.5% for deletions

**Why it degraded**:
- Too many funds front-running the same trade
- S&P changed announcement timing to reduce predictability
- Still works but returns compressed from 3-4% to 0.5-1%

---

## ERA 3: HFT DOMINANCE (2005-2015)

### Market making (Virtu, Citadel Securities)

Modern electronic market making replaced pit locals. The edge is the same
(bid-ask spread) but the execution is entirely different.

**The edge**:
- Post limit orders at bid and ask simultaneously
- Earn the spread when both sides fill
- Manage inventory risk by adjusting quotes based on order flow

**Virtu's performance**:
- Virtu Financial IPO filing (2014): profitable on 1,237 of 1,238 trading days
  from 2009-2013 (99.9% win rate)
- Revenue: $623M in 2013 from market making
- Edge source: speed (co-location), smart order routing, inventory management

**Why retail can't replicate**:
- Co-location costs: $10,000-$50,000/month per exchange
- Technology: custom FPGAs, kernel bypass networking
- Regulatory: designated market maker status gives queue priority

### Latency arbitrage

**The edge**:
- Price discovery happens first at one venue (e.g., CME for futures)
- Slower venues (NYSE, BATS) lag by 1-10ms
- HFT firms arbitrage the lag: buy cheap on slow venue, sell on fast venue

**Evidence**:
- Budish, Cramton & Shim (2015): HFT latency arbitrage earns $75M/year on
  S&P 500 futures alone
- Spread between co-located and non-co-located traders: 0.5-2 ticks per trade
- Accounts for 20-30% of HFT profits

**Why it matters for DEEP6**:
- Latency arbitrage creates predictable order flow: when ES moves, NQ follows
  within 50-200ms
- This is the ES-NQ lead-lag signal (see mbo-strategy-taxonomy.md, Pattern 21)
- Retail traders can exploit this at 100-500ms timescale (not competing with HFT)

### Statistical arbitrage evolution

By 2005-2015, stat arb had evolved from simple pairs to multi-factor models:

**Factor models**:
- Fama-French 3-factor (1993): market, size, value
- Carhart 4-factor (1997): adds momentum
- Fama-French 5-factor (2015): adds profitability, investment
- Each factor = systematic edge that persists across time

**High-frequency stat arb**:
- Extend pairs trading to millisecond timescales
- Use order flow imbalance (OFI) as the signal, not price
- Cont, Kukanov & Stoikov (2014): OFI predicts next mid-price with 55-65% accuracy

**Mean-reversion at microsecond scale**:
- Bid-ask bounce: price oscillates between bid and ask
- Roll (1984) measure: `Cov(ΔP_t, ΔP_{t-1}) < 0` = bid-ask bounce
- Predictable at < 1ms timescale, exploited by HFT market makers

### The Flash Crash (May 6, 2010)

**What happened**:
- 2:32 PM ET: Waddell & Reed executes a $4.1B sell order in E-mini S&P 500
- Algorithm: VWAP execution, 75,000 contracts over 20 minutes
- HFT firms absorbed initial selling, then began selling to each other ("hot potato")
- 2:45 PM: E-mini falls 5% in 5 minutes, Dow Jones drops 1,000 points intraday
- 2:45:28 PM: CME Stop Logic Functionality triggers 5-second pause
- Market recovers almost entirely within 20 minutes

**Kirilenko et al. (2011) findings**:
- HFT firms were profitable during the crash: earned $3.49M net
- HFT firms withdrew liquidity at the critical moment (reduced quotes)
- HFT "hot potato" trading amplified the move: same contracts traded 27,000 times
- Fundamental buyers (long-term investors) absorbed the selling at the bottom

**What it revealed**:
- Endogenous cascade risk: Hawkes branching ratio → 1.0 during the crash
- Liquidity is not guaranteed: HFT market makers can withdraw simultaneously
- Stop clusters create predictable price targets for momentum ignition
- Recovery was fast because fundamental value was unchanged

**DEEP6 application**:
- Monitor Hawkes branching ratio in real-time
- When branching ratio > 0.85, reduce position size (cascade risk)
- Flash crash pattern: VWAP algo + thin book + stop clusters = momentum ignition

### The Sarao Case (2015)

Navinder Singh Sarao spoofed E-mini S&P 500 futures from his bedroom in
Hounslow, UK. CFTC alleged he contributed to the Flash Crash.

**Method**:
- Placed large layered sell orders (2,000-3,000 contracts) above the market
- Automated cancellation before execution
- Created false impression of supply, suppressing prices
- Profited by buying at artificially low prices

**Scale**:
- $40M in profits over 5 years
- Fined $38.6M, sentenced to time served (1 year house arrest)

**What it proved**:
- One person with a laptop could move the E-mini market
- Spoofing was widespread and profitable before enforcement
- MBO data can detect this: large orders with < 5% fill rate, cancelled before execution

---

## ERA 4: POST-REFORM (2015-present)

### How market structure changes affected edges

**Dodd-Frank (2010) and CFTC enforcement**:
- Spoofing criminalized (2010)
- Enforcement began in earnest 2015-2018
- Reduced but didn't eliminate spoofing (moved to less-surveilled venues)

**MiFID II (2018, Europe)**:
- Transparency requirements reduced dark pool activity
- Best execution requirements changed order routing
- Reduced latency arbitrage opportunities in European markets

**SEC Rule 15c3-5 (Market Access Rule)**:
- Required pre-trade risk checks for all orders
- Added 50-100 microseconds of latency to HFT strategies
- Reduced some latency arbitrage opportunities

**Net effect on edges**:
- Pure latency arbitrage: compressed but not eliminated
- Spoofing: reduced, detectable, still present
- Market making: consolidated (Virtu, Citadel dominate)
- Order flow signals: STRONGER (more data, better tools)

### Surviving edges: order flow, volume profile, options flow

These edges survived because they're based on fundamental market microstructure,
not regulatory arbitrage or speed advantages:

**Order flow edge (OFI)**:
- Cont et al. (2014): 55-65% accuracy at 1-second horizon
- Still works because informed traders must trade, leaving footprints
- DEEP6 signals DELT_01, DELT_02, ABS_04 exploit this

**Volume profile edge**:
- High Volume Nodes (HVN): price gravitates to areas of prior acceptance
- Low Volume Nodes (LVN): price moves quickly through areas of prior rejection
- Single prints: price never traded a level = unfinished auction = magnet
- Works because auction theory is fundamental, not arbitrageable

**Options flow edge**:
- GEX regime determines mean-reversion vs momentum tendency
- Charm/vanna flows create predictable futures order flow at specific times
- FlashAlpha provides this data for $49/month

### Why mean-reversion and momentum both work at different timescales

**The timescale paradox**:
- At < 1 second: mean-reversion (bid-ask bounce, Roll measure)
- At 1-60 minutes: momentum (order flow persistence, Hawkes self-excitation)
- At 1-12 months: momentum (Jegadeesh & Titman)
- At > 3 years: mean-reversion (value investing, Fama-French)

**Why this happens**:
- Short-term: market makers create artificial mean-reversion (bid-ask bounce)
- Medium-term: institutional order execution creates momentum (VWAP algos take days)
- Long-term: fundamental value is mean-reverting (earnings, growth rates)

**DEEP6 application**:
- Intraday (1-60 min): use momentum signals in trending regime, mean-reversion in choppy
- Session-level: use volume profile and auction theory (medium-term mean-reversion)
- Don't mix timescales: a momentum signal at 1-minute doesn't predict 1-hour direction

### The regime dependence problem

Every edge has a regime where it works and a regime where it fails. This is the
central challenge of systematic trading.

**Documented regime dependence**:
- Momentum: works in trending markets, fails in choppy/mean-reverting
- Mean-reversion: works in range-bound markets, fails in trending
- Absorption: works at genuine support/resistance, fails in momentum ignition
- OFI: works in normal conditions, degrades during news/macro events

**DEEP6 solution**:
- Regime detection as a first-order filter (see nq-regime-patterns.md)
- Signal weights adjusted by regime
- Kill switches for adverse regime conditions

---

## PROVEN EDGES (with evidence)

### ORDER FLOW EDGES

**OFI predicts next mid-price**
- Source: Cont, Kukanov & Stoikov (2014), "The Price Impact of Order Book Events"
- Finding: OFI at depth 1 predicts next mid-price move with 55-65% accuracy at 1-second horizon
- Multi-level OFI (depth 5-10) improves accuracy to 60-70%
- Works because: informed traders must trade, creating persistent order flow imbalance
- DEEP6 signals: DELT_01 (OFI-based), DELT_02 (multi-level OFI)

**Stop sweep reversal**
- Source: Multiple practitioner sources; Kirilenko et al. (2011) documents the mechanism
- Finding: ~65-70% win rate on reversal after stop sweep through key level
- Mechanism: stop orders create predictable liquidity at known levels; after sweep, no more sellers
- Conditions: requires key level (prior high/low, round number), volume spike at sweep, immediate delta reversal
- DEEP6 signals: ABS_04 (effort vs result), TRAP_01 (stop sweep detection)

**Absorption at key levels**
- Source: DEEP6 internal backtest, Zones Variant D strategy
- Finding: PF 4.93, WR 80.2% over 16 months on NQ
- Mechanism: large institutional orders absorb aggressive flow at key levels; price cannot progress
- Conditions: requires key level, sustained aggression with no price progress, delta divergence
- DEEP6 signals: ABS_04 (strongest single signal, PF 3.94)

**Delta divergence**
- Source: Practitioner consensus; Dalton, Jones & Dalton (2013) "Markets in Profile"
- Finding: price/CVD divergence predicts reversal with ~60% accuracy
- Mechanism: price makes new high but CVD doesn't = buying exhaustion; reversal likely
- Conditions: requires sustained divergence (3+ bars), not single-bar noise
- DEEP6 signals: DELT_03 (delta divergence), DELT_04 (CVD divergence)

**Iceberg detection**
- Source: Zotikov (2019), "Detection of Iceberg Orders in Limit Order Books"
- Finding: HVr ≥ 2.0 with 2+ refreshes = iceberg with high confidence
- Mechanism: institutional orders hide size to avoid front-running; detection reveals conviction
- Counter-strategy: trade WITH the iceberg (it will hold the level)
- DEEP6 signals: ABS_02 (iceberg detection)

### VOLUME PROFILE EDGES

**HVN/LVN navigation**
- Source: Steidlmayer (1984) Market Profile theory; Dalton et al. (2013)
- Finding: price gravitates to HVNs (prior acceptance) and moves quickly through LVNs (prior rejection)
- Mechanism: auction theory — price seeks areas of prior value acceptance
- Quantification: LVN gaps of > 3 ticks with < 10% of session volume = fast-move zone
- DEEP6 signals: VOLP_01 (HVN proximity), VOLP_02 (LVN detection)

**Single print exploitation**
- Source: Steidlmayer (1984); Dalton et al. (2013)
- Finding: single prints (price traded once, never returned) act as magnets
- Mechanism: unfinished auction — market never accepted value at that level
- Reliability: ~70% of single prints are filled within 5 sessions
- DEEP6 signals: VOLP_03 (single print detection)

**POC magnet effect during session**
- Source: Practitioner consensus; Steidlmayer (1984)
- Finding: price returns to Point of Control (highest volume price) ~60% of sessions
- Mechanism: POC = fair value; price oscillates around fair value in balanced markets
- Conditions: works best in mean-reverting regime; fails in trending regime
- DEEP6 signals: VOLP_04 (POC proximity)

**Value area statistics**
- Source: Steidlmayer (1984); empirically confirmed by multiple practitioners
- Finding: 70% of sessions trade back to prior day's value area
- Mechanism: institutional participants reference prior value area for positioning
- Application: if price opens outside value area, 70% chance it returns inside
- DEEP6 signals: VOLP_05 (value area position), VOLP_06 (value area return)

### AUCTION THEORY EDGES

**Initial balance extension statistics**
- Source: Steidlmayer (1984); Dalton et al. (2013)
- Finding: IB extension (price breaks IB high/low) occurs ~60% of sessions
- When IB is narrow (< 1 ATR): extension probability increases to ~70%
- When IB is wide (> 2 ATR): extension probability decreases to ~45%
- DEEP6 signals: AUCT_01 (IB extension probability)

**Poor high/low = unfinished auction**
- Source: Dalton et al. (2013)
- Finding: poor high (single print at session high) = price will return to test
- Mechanism: market didn't accept value at the extreme; auction is unfinished
- Reliability: ~65% of poor highs/lows are retested within 3 sessions
- DEEP6 signals: AUCT_02 (poor high/low detection)

**Excess at extremes = finished auction**
- Source: Dalton et al. (2013)
- Finding: excess (multiple prints at extreme, aggressive rejection) = finished auction
- Mechanism: market explicitly rejected value at the extreme; reversal confirmed
- Reliability: ~70% of excess formations hold as support/resistance
- DEEP6 signals: AUCT_03 (excess detection)

### OPTIONS FLOW EDGES

**Gamma scalping creates predictable futures flow**
- Source: Taleb (1997) "Dynamic Hedging"; practitioner consensus
- Mechanism: options MM long gamma → buys dips, sells rallies to maintain delta-neutral
- Quantification: GEX > 0 = mean-reversion tendency; GEX < 0 = momentum tendency
- Data source: FlashAlpha API ($49/month) for NQ via QQQ/NDX proxy
- DEEP6 application: GEX regime as first-order filter for signal weights

**Charm/vanna flows at specific times**
- Source: Bittman (2009) "Trading Index Options"; practitioner consensus
- Charm: delta decay of OTM options as time passes → hedges unwind directionally
- Vanna: delta change as vol changes → hedges adjust directionally
- Timing: charm flow strongest in first 2 hours of session (theta decay accelerates)
- Vanna flow: strongest when VIX moves > 1 point intraday
- DEEP6 application: time-of-day filter for options-flow signals

**GEX regime determines mean-reversion vs momentum**
- Source: Kris Sidial (2021) "The Gamma Exposure Framework"; SpotGamma research
- Finding: positive GEX correlates with lower realized volatility and mean-reversion
- Finding: negative GEX correlates with higher realized volatility and momentum
- Quantification: GEX flip level = price where GEX changes sign = key level
- DEEP6 application: GEX regime as regime classifier (see nq-regime-patterns.md)

### TIME-OF-DAY EDGES (NQ specific)

**9:30-10:30 ET: highest institutional participation**
- Source: Admati & Pfleiderer (1988) "A Theory of Intraday Patterns"; empirical confirmation
- Finding: volume, volatility, and informed trading all peak at open
- Mechanism: overnight information resolves at open; institutional orders execute
- Edge: strongest signals, highest win rates, but also highest adverse selection risk
- DEEP6 application: full signal weight, all detectors active

**10:30-11:00 ET: first hour reversal window**
- Source: Practitioner consensus; Toby Crabel (1990) "Day Trading with Short Term Price Patterns"
- Finding: ~55-60% of sessions reverse the opening direction in this window
- Mechanism: opening momentum exhausts, institutional VWAP algos begin mean-reverting
- Edge: fade the opening direction if absorption signals confirm
- DEEP6 application: increase weight on ABS signals, decrease weight on momentum signals

**13:30-14:00 ET: afternoon positioning**
- Source: Practitioner consensus; Admati & Pfleiderer (1988)
- Finding: volume picks up as European close approaches; institutional positioning begins
- Mechanism: European traders close positions; US institutions begin afternoon positioning
- Edge: directional signals more reliable than morning noise period
- DEEP6 application: resume full signal weight after lunch reduction

**14:30-16:00 ET: pre-close momentum**
- Source: Practitioner consensus; Jain & Joh (1988) "The Dependence Between Hourly Prices"
- Finding: volume and directional momentum increase in final 90 minutes
- Mechanism: VWAP algos must complete execution; index rebalancing; options hedging
- Edge: momentum signals work well; mean-reversion signals less reliable
- DEEP6 application: increase weight on momentum signals, decrease on mean-reversion

**11:00-13:00 ET: avoid (lunch, noise, thin)**
- Source: Practitioner consensus; Admati & Pfleiderer (1988)
- Finding: volume drops 40-60% during lunch; spread widens; signals degrade
- Mechanism: institutional traders at lunch; HFT dominates thin market
- Edge: no reliable edge; adverse selection risk increases
- DEEP6 application: reduce all position sizes 50%; require score ≥ 85 for any trade

---

## STRATEGIES THAT STOPPED WORKING

### Early L2 reading (killed by HFT)

**What worked (pre-2005)**:
- Ax identification: dominant market maker signals direction
- Quote fade detection: human-speed cancellations were readable
- Level 2 momentum: MMs stacking on one side = directional signal

**Why it died**:
- HFT firms post and cancel quotes in < 1ms (human reaction: 200-500ms)
- Level 2 became a battlefield of spoofing and layering
- The "ax" concept became meaningless when any firm could post 10,000 quotes/second
- Retail traders reading Level 2 are now reading HFT noise, not institutional intent

**What replaced it**:
- MBO data (order-level, not quote-level) reveals true institutional intent
- Iceberg detection, spoof detection, queue analysis
- These require MBO data and algorithmic processing, not human reading

### Simple momentum (crowded, decay)

**What worked (1993-2010)**:
- Jegadeesh & Titman (1993): 12-month momentum earned 1%/month
- Simple rules: buy 52-week high breakouts, sell 52-week low breakouts
- Works because of underreaction to news and institutional herding

**Why it degraded**:
- Crowding: AQR, Two Sigma, Renaissance all running momentum
- Momentum crashes: 2009 (momentum reversal), 2020 (COVID crash)
- Novy-Marx (2012): momentum works best at 12-month horizon, not shorter
- Intraday momentum is different and requires order flow confirmation

**What replaced it**:
- Regime-conditioned momentum: only trade momentum in trending regime
- Order flow confirmation: momentum signal + OFI confirmation
- Multi-factor: momentum + quality + low volatility (reduces crash risk)

### Pure mean-reversion (doesn't work during trending regimes)

**What worked (range-bound markets)**:
- Bollinger Band mean-reversion: buy lower band, sell upper band
- RSI extremes: buy oversold, sell overbought
- Works in choppy, range-bound markets

**Why it fails**:
- Trending markets: mean-reversion signals generate continuous losses
- "The trend is your friend" is empirically true at medium timescales
- Bollinger Bands expand during trends, giving false signals

**What replaced it**:
- Regime detection first: only apply mean-reversion in mean-reverting regime
- Volume profile confirmation: mean-reversion at HVN/value area (not arbitrary levels)
- Absorption confirmation: mean-reversion only when absorption detected at level

### Single-indicator systems (easy to game by HFT)

**What worked (pre-2000)**:
- Simple RSI crossovers, MACD signals, moving average crossovers
- Worked because few participants were systematic

**Why it died**:
- HFT firms reverse-engineered retail indicator signals
- When RSI hits 30, HFT knows retail will buy → HFT sells into retail buying
- Single indicators are predictable = front-runnable
- Retail indicator signals became a source of liquidity for HFT, not edge

**What replaced it**:
- Multi-signal confluence: require 3+ independent signals to agree
- Order flow confirmation: indicator signal + order flow confirmation
- Regime filtering: indicator signal only valid in appropriate regime
- DEEP6 approach: 44 signals synthesized into confidence score; no single signal trades alone

---

## THE META-LESSON

Every edge in trading history follows the same lifecycle:

1. **Discovery**: Edge found by a small number of participants
2. **Exploitation**: Returns are high, risk is low
3. **Crowding**: More participants discover the edge, returns compress
4. **Decay**: Edge becomes marginal or disappears
5. **Adaptation**: Surviving participants find the next edge

The edges that survive longest are those based on fundamental market microstructure:
- Informed traders must trade (OFI edge)
- Institutions must execute large orders (VWAP, absorption)
- Options market makers must hedge (GEX, charm/vanna)
- Auctions must find fair value (volume profile, value area)

These are structural, not arbitrageable. They persist because they're not
exploitable by speed or capital alone — they require understanding of the
underlying mechanism.

**DEEP6's thesis**: Absorption and exhaustion are the highest-alpha reversal
signals because they detect the moment when institutional supply/demand is
exhausted at a level. This is a fundamental microstructure phenomenon that
cannot be arbitraged away by HFT speed or capital.
