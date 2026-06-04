# DEEP6 TradingView Chart-Reading and Candle/Indicator Integration Guide

Purpose: make Hermes/DEEP6 better at reading TradingView charts for NQ-style visual analysis, replay review, screenshot annotation, and MCP-assisted context extraction.

Scope: this guide supports analysis, documentation, replay study, and decision support only. It is not unconfirmed live trade advice. A chart read can identify context, confluence, risk, and invalidation ideas, but should not be presented as an automatic instruction to enter, exit, size, or hold a live position without the user's confirmed trading plan and live risk controls.

---

## 1. Core Operating Principle

Read the chart in layers, not as isolated indicators.

Recommended order:

1. Instrument/session/timeframe context
2. Market regime: trend, range, transition, volatility expansion/contraction
3. Higher-timeframe location: prior day/week levels, VWAP, sigma bands, GEX/levels, support/resistance
4. Candle structure: body, wick, close location, sequence, pace
5. Volume/order-flow approximations available in TradingView
6. Indicator state: VWAP, EMAs, RSI, MACD, Bollinger Bands
7. Confluence and conflict map
8. Replay/screenshot evidence
9. Clear distinction between observation, hypothesis, confirmation, and non-advice

For DEEP6/NQ use, a good chart read answers:

- Where is price relative to value, VWAP, standard deviations, and major levels?
- Is price accepting, rejecting, rotating, expanding, or exhausting?
- Are candles showing initiative, absorption, exhaustion, or indecision?
- Are indicators confirming momentum or warning of stretched/choppy conditions?
- What evidence is visible, and what would invalidate the read?

---

## 2. NQ/DEEP6 Chart Setup Defaults

TradingView layouts should be clean enough for visual reading and consistent enough for extraction.

Suggested panes:

- Main pane:
  - Candles or hollow candles
  - Session VWAP with standard deviation bands if available
  - 9/21 EMA for short-term momentum
  - 50/200 EMA for higher-timeframe trend context when useful
  - Important drawn levels: prior day high/low/close, overnight high/low, weekly levels, GEX levels, supply/demand zones, liquidity levels
- Lower panes:
  - Volume
  - RSI or MACD, not too many oscillators at once
  - Optional custom Pine labels/tables/lines for DEEP6 levels or signals

Suggested timeframes:

- 1m/2m/5m: execution/replay detail and candle sequence
- 15m: intraday structure and regime
- 30m/60m: session bias and key swings
- Daily: prior levels, volatility, larger support/resistance

NQ-specific caution:

- NQ moves fast and can overshoot levels before resolving.
- Wick tests and quick reversals are common near VWAP/sigma/GEX/round-number zones.
- Avoid treating one candle as decisive without sequence and location.

---

## 3. Candle Anatomy

A candle gives four facts: open, high, low, close. Interpretation comes from the relationship between body, wicks, location, and sequence.

### Body

- Large bullish body: buyers controlled most of the bar from open to close.
- Large bearish body: sellers controlled most of the bar from open to close.
- Small body: two-sided trade, indecision, pause, absorption, or low participation.
- Close near high: bullish control into the close of the bar.
- Close near low: bearish control into the close of the bar.
- Close near middle: unresolved auction; requires next-bar confirmation.

### Wicks

- Upper wick: price traded higher and was rejected or absorbed there.
- Lower wick: price traded lower and was rejected or absorbed there.
- Long wick at a key level: potential rejection, liquidity sweep, stop run, or absorption.
- Long wick in the middle of nowhere: less meaningful; may only be volatility noise.
- Repeated upper wicks at resistance: supply/absorption pressure.
- Repeated lower wicks at support: demand/absorption pressure.

### Body/Wick Balance

- Large body + small wick: initiative movement; cleaner directional control.
- Small body + large wicks both sides: chop, uncertainty, two-sided auction.
- Long wick against trend after extension: possible exhaustion or failed continuation.
- Long wick with strong close back through level: stronger rejection evidence than wick alone.

### Close Location Matters

For DEEP6-style reads, do not simply identify the wick. Ask where the bar closed:

- Rejection candle that closes back inside range = stronger failed breakout clue.
- Wick above resistance but close below resistance = possible upside sweep/rejection.
- Wick below support but close above support = possible downside sweep/rejection.
- Breakout candle that closes beyond level with body = possible acceptance.
- Candle pierces level but closes on level = unresolved.

---

## 4. Candle Sequence and Auction Behavior

Single candles are weak evidence. Sequences reveal intent.

### Initiative Sequence

Signs:

- Consecutive directional bodies
- Pullbacks are shallow
- Closes near highs in uptrend or lows in downtrend
- Volume expands with direction
- EMAs slope in direction
- Price holds above/below VWAP

Interpretation:

- Buyers/sellers are actively repricing.
- Fade attempts are lower quality unless the move reaches a major exhaustion level.

### Absorption Sequence

Signs:

- Price repeatedly tests a level but cannot progress.
- Wicks extend through the level, but closes fail to accept beyond it.
- Volume is elevated, yet net price progress is limited.
- Momentum indicators flatten/diverge.

DEEP6 mapping:

- Potential absorption: aggressive participants hit the level, but passive liquidity prevents continuation.
- In TradingView, this is approximate unless using true bid/ask footprint data. Use candle/volume behavior as a proxy, not proof.

### Exhaustion Sequence

Signs:

- Trend extends into VWAP sigma band, prior high/low, GEX/large level, or round number.
- Final push has a long wick, smaller body, or failed follow-through.
- Momentum oscillator diverges.
- Volume can either climax or dry up.
- Next candle cannot continue and closes back against the move.

Interpretation:

- The move may be running out of responsive buyers/sellers.
- Confirmation requires failure to continue, reclaim/loss of a level, or structural break.

### Rotation/Range Sequence

Signs:

- Alternating candle colors
- Overlapping bodies
- Wicks on both sides
- Failed breakouts at range edges
- VWAP flat or mean-reverting
- Bollinger Bands flatten/contract

Interpretation:

- Price is accepting within a value area.
- Mean-reversion reads may work better than breakout reads until range breaks and accepts.

### Transition Sequence

Signs:

- Prior trend loses body size.
- Pullbacks deepen.
- Breaks of micro trendline or EMA structure occur.
- Price reclaims or loses VWAP.
- Former support becomes resistance or vice versa.

Interpretation:

- Market may be shifting from trend to range, range to trend, or trend reversal.
- Avoid overconfidence; transition zones create false starts.

---

## 5. Trend, Range, and Volatility Regimes

### Trend Regime

Bull trend clues:

- Higher highs and higher lows
- Pullbacks hold above rising VWAP/EMAs
- Candles close near highs
- Breakouts hold retests
- RSI holds bullish range, often 40-80 instead of 30-70
- MACD above zero or rising

Bear trend clues:

- Lower highs and lower lows
- Pullbacks fail below falling VWAP/EMAs
- Candles close near lows
- Breakdowns hold retests
- RSI holds bearish range, often 20-60
- MACD below zero or falling

Trend read discipline:

- Do not call a reversal just because price is extended.
- Require failed continuation plus structure change.

### Range Regime

Range clues:

- Flat VWAP/EMAs
- Price crosses VWAP repeatedly
- Overlapping candles
- Oscillators mean-revert
- Volume concentrates around value
- Breakouts fail back into range

Range read discipline:

- At range highs, look for rejection/exhaustion.
- At range lows, look for rejection/exhaustion.
- In the middle, signals have lower edge.

### Volatility Expansion

Clues:

- Large candles after compression
- Bollinger Bands widen
- VWAP sigma bands are tested rapidly
- Volume increases
- Break of prior session/range level

Interpretation:

- Market is repricing. Avoid assuming mean reversion too early.

### Volatility Contraction

Clues:

- Small candles
- Narrow range
- Bollinger squeeze
- Declining volume
- Price compresses between EMAs/VWAP/levels

Interpretation:

- Breakout risk increases, but direction is unknown until acceptance appears.

---

## 6. VWAP and Standard Deviation Bands

VWAP is a session value anchor. Standard deviation bands frame extension from value.

### VWAP Basics

- Price above rising VWAP: buyers have intraday control.
- Price below falling VWAP: sellers have intraday control.
- Flat VWAP with repeated crosses: balanced/range auction.
- VWAP reclaim: potential shift from bearish to neutral/bullish intraday control.
- VWAP rejection: value defense; continuation or range behavior depends on sequence.

### Sigma Band Interpretation

Common bands:

- VWAP +/- 1 sigma: normal rotation/value boundary
- VWAP +/- 2 sigma: extended; watch for continuation or mean reversion
- VWAP +/- 3 sigma: statistically stretched; watch for exhaustion, but do not fade blindly

DEEP6 use:

- Sigma bands are context, not signals.
- Strong trend days can ride +1/+2 sigma or -1/-2 sigma for long periods.
- Best reads combine sigma location with candle sequence, levels, volume, and momentum divergence.

### VWAP/Sigma Scenarios

1. Trend continuation:
   - Price holds above VWAP and pulls to +1 sigma/EMA support.
   - Candles reject lower prices and close strong.

2. Exhaustion fade context:
   - Price spikes into +2/+3 sigma near prior high/GEX level.
   - Long upper wick, reduced follow-through, bearish divergence, close back below level.

3. Mean reversion:
   - Price fails to accept outside sigma band.
   - Reclaims inside band and targets VWAP/value.

4. Value shift:
   - Price crosses VWAP, retests, and holds.
   - VWAP slope changes and pullbacks respect the new side.

---

## 7. Volume and Order-Flow Approximations in TradingView

TradingView usually does not provide the same footprint/bid-ask detail as NinjaTrader order-flow tools unless using special feeds/indicators. Treat volume/order-flow reads as approximations.

### Useful Proxies

- Volume bars:
  - Rising volume with directional candles = participation confirms move.
  - High volume with little progress = possible absorption or churn.
  - Low volume breakout = risk of failure unless follow-through arrives.

- Candle spread vs volume:
  - Wide spread + high volume + strong close = initiative.
  - Narrow spread + high volume at level = possible absorption.
  - Wide wick + high volume + failed close = possible rejection/sweep.

- Volume Profile / fixed range volume profile:
  - HVN: high-volume node, acceptance/value.
  - LVN: low-volume node, rejection/fast-travel zone.
  - POC: point of control, magnet/acceptance reference.

- Lower-timeframe candle inspection:
  - If a 5m candle has a long wick, inspect 1m/30s when available to see sequence.

- DOM/order book if available:
  - Useful for liquidity context but can be spoofed and changes fast.

### Approximate Absorption Checklist

At a known level:

- Multiple tests fail to progress.
- Wicks penetrate but closes reject.
- Volume is high relative to nearby bars.
- Momentum stalls or diverges.
- Next candles confirm by breaking away from the level.

Label as: "possible absorption" unless true bid/ask footprint confirms it.

### Approximate Exhaustion Checklist

- Extended from VWAP/value.
- At sigma band or major level.
- Final candles get smaller or wick-heavy.
- Volume climax or participation drop.
- RSI/MACD divergence or momentum flattening.
- Follow-through fails.

Label as: "possible exhaustion" until confirmed by structure.

---

## 8. RSI, MACD, EMA, and Bollinger Bands

Indicators should describe conditions and confluence. They should not override price structure.

### EMA

Common setup:

- 9 EMA: short-term momentum
- 21 EMA: intraday pullback/trend guide
- 50 EMA: intermediate trend
- 200 EMA: larger trend/reference

Read:

- Stacked rising EMAs: bullish trend structure.
- Stacked falling EMAs: bearish trend structure.
- Flat/tangled EMAs: range/chop.
- Pullback to rising 9/21 with rejection candle: trend-continuation context.
- Break and failed retest of EMA cluster: possible trend transition.

### RSI

Read:

- Above 50: bullish momentum bias.
- Below 50: bearish momentum bias.
- Overbought/oversold alone is not a signal.
- Bull trend RSI may hold 40-80.
- Bear trend RSI may hold 20-60.
- Divergence matters more at major levels or VWAP sigma bands.

Useful RSI observations:

- Higher price high + lower RSI high: bearish divergence/exhaustion warning.
- Lower price low + higher RSI low: bullish divergence/exhaustion warning.
- RSI failing at 50 during pullback: momentum remains weak.
- RSI reclaiming 50 with VWAP reclaim: potential value/momentum shift.

### MACD

Read:

- MACD above zero: bullish momentum regime.
- MACD below zero: bearish momentum regime.
- Signal cross: momentum shift, stronger when aligned with structure.
- Histogram expansion: momentum increasing.
- Histogram contraction: momentum fading.
- Divergence at a level: exhaustion warning.

Caution:

- MACD lags; use it for confirmation and regime, not early reversal prediction.

### Bollinger Bands

Read:

- Bands expanding: volatility expansion.
- Bands contracting: compression/squeeze.
- Price walking upper band: strong bullish trend, not automatic short.
- Price walking lower band: strong bearish trend, not automatic long.
- Failed close outside band back inside: possible reversal/mean-reversion clue.
- Middle band often acts like dynamic mean in ranges.

DEEP6 integration:

- Bollinger expansion plus VWAP sigma extension = high-volatility state.
- Bollinger squeeze near GEX/level = breakout watch, direction unconfirmed.

---

## 9. Support, Resistance, and Levels

Levels matter because they define where reactions should occur.

### Level Types

- Prior day high/low/close
- Overnight high/low
- Weekly/monthly highs/lows
- Session open
- VWAP and sigma bands
- Round numbers and quarter/half levels on NQ
- Swing highs/lows
- Trendlines/channels
- Volume profile HVN/LVN/POC
- GEX/gamma levels, dealer zones, large option strikes
- Custom DEEP6 liquidity/absorption/exhaustion zones

### Reading a Level

At every level ask:

- Was it approached slowly or with momentum?
- Did price reject instantly or accept beyond it?
- Did the candle close through it or only wick through it?
- Did volume expand or fade?
- Did a retest hold?
- Is this level aligned with VWAP/sigma/EMA/profile/GEX?

### Acceptance vs Rejection

Acceptance:

- Multiple closes beyond the level
- Retest holds from the other side
- Candles build value beyond the level
- VWAP/EMA structure supports continuation

Rejection:

- Wick through level, close back inside
- Failed retest
- Strong opposite candle
- No follow-through
- Momentum divergence or volume churn

### Confluence Strength

Stronger confluence examples:

- Prior high + +2 sigma + bearish RSI divergence + long upper wick
- Overnight low + -2 sigma + lower wick rejection + volume climax
- VWAP reclaim + 21 EMA reclaim + MACD histogram turns positive
- GEX level + volume profile LVN + failed breakout candle

Conflicting confluence examples:

- Price extended at +2 sigma but trend is strong and candles keep closing high.
- RSI overbought but EMAs/VWAP all support bullish continuation.
- A support level exists, but price accepts below it with strong closes.

When confluence conflicts, state the conflict explicitly.

---

## 10. Replay Workflow

Replay is for evidence building, not hindsight storytelling.

Recommended TradingView replay process:

1. Pick symbol, contract, and timeframe.
2. Mark known pre-session levels before replaying.
3. Start replay before the event, not at the event.
4. Step candle by candle.
5. For each decision point record:
   - Time
   - Price/location
   - Regime
   - Candle sequence
   - Indicator state
   - Level interaction
   - Hypothesis
   - Confirmation required
   - Invalidation
   - Outcome after N bars
6. Capture screenshots before and after the resolution.
7. Do not rewrite the hypothesis after seeing outcome.

Replay labels should distinguish:

- Setup appeared
- Confirmation occurred
- Confirmation failed
- Move worked but was not valid by rules
- Signal was late/chasing
- Context was correct but timing was poor
- Chop/no trade environment

---

## 11. Screenshots and Visual Annotation

Screenshots are essential for visual skill building.

A good screenshot should include:

- Symbol and timeframe
- Visible time axis
- Price axis
- Main indicators and levels
- Enough left-side context to see approach
- Enough right-side context to see outcome if reviewing
- Clear labels/arrows/boxes if annotated

Screenshot annotation checklist:

- Mark the key level being tested.
- Mark VWAP/sigma relationship.
- Circle rejection/absorption/exhaustion candles.
- Note candle close behavior.
- Mark RSI/MACD divergence if relevant.
- Identify regime: trend/range/transition/volatility expansion.
- State whether it is observation, hypothesis, or confirmed result.

Avoid screenshots overloaded with indicators where price action is unreadable.

---

## 12. MCP Data Extraction to Support Visual Analysis

MCP extraction should not replace visual analysis; it should ground and verify it.

### Chart State

Use chart state to confirm:

- Current symbol
- Timeframe
- Chart type
- Active indicators/studies
- Layout/pane context

This prevents analyzing the wrong instrument or timeframe.

### OHLCV Extraction

Use recent OHLCV bars to quantify:

- Candle body size
- Wick size
- Close location within range
- Consecutive directional closes
- Range expansion/contraction
- Relative volume
- High/low breaks
- Gaps and session behavior

Useful derived metrics:

- Body = abs(close - open)
- Range = high - low
- Upper wick = high - max(open, close)
- Lower wick = min(open, close) - low
- Close location = (close - low) / (high - low)
- Body-to-range ratio = body / range
- Relative volume = volume / average recent volume

### Study Values

Use study value extraction for:

- RSI current value and slope/change
- MACD line/signal/histogram state
- EMA values and price relation
- Bollinger upper/mid/lower relationship
- VWAP/sigma if exposed as study plots

Do not hallucinate hidden study values. If a custom indicator does not expose plots, use Pine labels/tables/lines extraction when possible.

### Pine Lines, Boxes, Labels, Tables

Use Pine object extraction for custom indicators:

- Lines: support/resistance, VWAP/sigma, GEX levels, prior highs/lows
- Boxes: supply/demand zones, liquidity zones, value areas
- Labels: signals, warnings, regime tags, pattern labels
- Tables: session stats, bias panels, confluence scores

For DEEP6, these should be used to build a machine-readable level map:

- Level name
- Price
- Type: support/resistance/VWAP/sigma/GEX/profile/liquidity
- Directional implication if any
- Confidence/source
- Distance from current price

### Screenshots

Use MCP screenshots to preserve visual context when:

- The user asks for chart reading.
- A replay event is reviewed.
- A level interaction is ambiguous.
- The system needs to compare visual candles with extracted OHLCV.

### Visible Range

Use visible range to ensure extraction aligns with what the user sees.

If OHLCV extraction covers recent bars but the chart is scrolled to history, align date range before making a visual claim.

### Batch Runs

Use batch extraction for:

- Comparing NQ with ES/RTY/YM
- Multi-timeframe reads: 5m/15m/60m/D
- Snapshotting indicator values across symbols/timeframes

### Suggested MCP Chart-Read Procedure

1. Get chart state.
2. Get visible range.
3. Capture screenshot if visual analysis is requested.
4. Extract OHLCV for current timeframe.
5. Extract study values.
6. Extract Pine lines/boxes/labels/tables if custom indicators are active.
7. Summarize:
   - Regime
   - Key levels
   - Candle sequence
   - Indicator confluence
   - Conflicts/uncertainties
   - Non-advisory analysis statement

---

## 13. Standard DEEP6 Chart-Read Template

Use this output structure for user-facing chart reads:

1. Context
   - Symbol/timeframe/session
   - Price relative to VWAP, sigma bands, EMAs, and major levels

2. Regime
   - Trend/range/transition
   - Volatility expansion/contraction

3. Candle read
   - Recent body/wick behavior
   - Sequence and close locations
   - Signs of initiative, absorption, exhaustion, or chop

4. Volume/order-flow proxy
   - Relative volume
   - Volume vs progress
   - Possible absorption/exhaustion language only when appropriate

5. Indicator read
   - VWAP/sigma
   - RSI
   - MACD
   - EMAs
   - Bollinger Bands

6. Levels
   - Support below
   - Resistance above
   - Active reaction zones
   - Acceptance/rejection criteria

7. Confluence and conflict
   - What agrees
   - What disagrees
   - What evidence would confirm or invalidate the hypothesis

8. Risk/non-advice statement
   - "This is chart analysis and decision support, not an unconfirmed live trade recommendation. Confirm with your plan, execution rules, and risk controls."

---

## 14. Language Standards

Use precise language:

- "Price is rejecting" instead of "it will reverse."
- "Possible absorption" instead of "absorption confirmed" without footprint evidence.
- "Momentum is fading" instead of "short now."
- "A bullish hypothesis would need acceptance above X" instead of "buy above X" unless the user explicitly asks for strategy rules and risk framework.
- "Invalidation would be a close back below/above X" instead of certainty.

Avoid:

- Guaranteed predictions
- Live trade calls without confirmation
- Overstating indicator signals
- Treating RSI overbought/oversold as automatic reversal
- Treating VWAP sigma tags as automatic fades
- Ignoring the current regime

---

## 15. Quick Pattern Reference

### Bullish Rejection at Support

- Location: support, -2 sigma, prior low, LVN, GEX support
- Candle: lower wick, close above level
- Sequence: failed downside continuation
- Confirmation: next candle holds/reclaims structure
- Risk: if price accepts below support, rejection failed

### Bearish Rejection at Resistance

- Location: resistance, +2 sigma, prior high, LVN, GEX resistance
- Candle: upper wick, close below level
- Sequence: failed upside continuation
- Confirmation: next candle holds below/rejects retest
- Risk: if price accepts above resistance, rejection failed

### Trend Pullback Continuation

- Location: rising/falling EMA, VWAP side, prior breakout retest
- Candle: controlled pullback, rejection in trend direction
- Sequence: shallow pullback, continuation close
- Confirmation: break of pullback high/low with follow-through
- Risk: loss of VWAP/EMA structure or failed continuation

### Range Edge Fade Context

- Location: established range high/low
- Candle: wick through edge, close back inside
- Sequence: failed breakout
- Confirmation: move back toward range midpoint/VWAP
- Risk: acceptance outside range

### Breakout Acceptance

- Location: range edge or major level
- Candle: strong close beyond level
- Sequence: follow-through or successful retest
- Confirmation: value builds beyond level
- Risk: failed retest and close back inside

### Exhaustion Extension

- Location: +2/+3 or -2/-3 sigma, major level, prior high/low
- Candle: wick-heavy or shrinking bodies after extended move
- Sequence: failed continuation
- Confirmation: structure break/reclaim/loss
- Risk: trend day continuation rides the band

---

## 16. Final Reminder

TradingView chart reading is a support layer for DEEP6. The strongest reads combine:

- Candle sequence
- VWAP/sigma location
- Volume/progress behavior
- Indicator regime
- Support/resistance and GEX/levels
- Replay evidence
- MCP-extracted data for grounding

Never present an unconfirmed chart read as live trade advice. Present observations, hypotheses, confirmation conditions, invalidation conditions, and uncertainty clearly.
