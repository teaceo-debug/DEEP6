# Strategy Methodology Guide

**Last verified: 2026-05-12**
**Scope:** How to find, evaluate, adapt, and integrate NinjaTrader strategies for NQ futures trading. Includes DEEP6-specific integration guidance.

---

## 1. Where to Find NinjaTrader Strategies

### 1.1 NinjaTrader Official Channels

**NT8 Ecosystem App Share**
- URL: https://ninjatrader.com/support/forum/forum/ninjatrader-8/strategy-development
- What's there: community-submitted NinjaScript strategies, indicators, and add-ons. Free. Quality varies widely.
- How to use: search by instrument (NQ, ES), strategy type (trend, mean-reversion), or signal type (volume, order flow)
- Caveat: most submissions lack out-of-sample results; treat as starting points, not finished products

**NT8 Marketplace**
- URL: https://ninjatrader.com/trading-platform/marketplace/
- What's there: commercial strategies and indicators, some with verified performance records
- Cost: $50–$500+ per strategy; some subscription-based
- Caveat: marketplace listings are not independently audited; vendor-provided backtests may be in-sample only

### 1.2 Community Forums

**Elite Trader Forum**
- URL: https://www.elitetrader.com/et/forums/automated-trading.4/
- What's there: serious discussion of automated strategies, NinjaScript code, and performance analysis. Higher signal-to-noise than most forums.
- Best threads: search "NQ automated", "NinjaTrader strategy", "order flow automation"

**NinjaTrader Community Forum**
- URL: https://ninjatrader.com/support/forum/
- What's there: official support forum; strategy development subforum has code examples and debugging help
- Best for: NinjaScript API questions, compile errors, specific indicator implementations

**Reddit**
- r/FuturesTrading, r/algotrading — occasional NQ strategy discussions; lower quality than Elite Trader but broader reach

### 1.3 GitHub

Search terms that find real NinjaScript code:
- `ninjatrader strategy NQ`
- `NinjaScript indicator order flow`
- `ninjatrader 8 futures automated`

Notable repositories to check:
- Search GitHub for `language:C# ninjatrader` — filters to actual NinjaScript files
- Many open-source indicators exist; strategies are rarer but present

### 1.4 Commercial Vendors

| Vendor | Focus | Notes |
|--------|-------|-------|
| Orderflows (Mike Valtos) | Order flow, delta, footprint | 128-setup encyclopedia; NinjaTrader indicators available |
| Trader Dale | Volume profile, stacked imbalance | NinjaTrader-compatible indicators; strategy guides |
| Axia Futures | Footprint, absorption | Course-based; indicators sold separately |
| Jigsaw Trading | DOM, order flow | Jigsaw Journeys platform; NinjaTrader integration |
| Bookmap | Heatmap, liquidity | Standalone platform; NinjaTrader bridge available |

---

## 2. How to Evaluate a Strategy

### 2.1 Minimum Backtesting Requirements

Before trusting any backtest result, verify these conditions are met:

**Sample size**
- Minimum: 200 completed trades
- Preferred: 500+ trades across multiple market regimes
- Why: below 200 trades, win rate and profit factor estimates have confidence intervals too wide to be actionable

**Time period**
- Minimum: 2 years of data
- Preferred: 5+ years covering at least one trending year, one ranging year, and one high-volatility year
- For NQ: must include at least one period of elevated VIX (>30) and one low-volatility period

**Out-of-sample (OOS) results**
- Non-negotiable: the strategy must have been tested on data it was NOT optimized on
- Standard split: 70% in-sample (IS) for optimization, 30% OOS for validation
- Walk-forward testing is stronger than a single IS/OOS split

**Slippage and commission**
- NQ round-trip commission: ~$4–$8 per contract (broker-dependent)
- Slippage: minimum 1 tick ($5) per side for market orders; 0 for limit orders that fill
- Any backtest without realistic slippage is meaningless for NQ

### 2.2 Key Performance Metrics

| Metric | Minimum Acceptable | Good | Excellent |
|--------|-------------------|------|-----------|
| Profit Factor | 1.3 | 1.6 | 2.0+ |
| Win Rate | 40% (with good R:R) | 50–55% | 60%+ |
| Max Drawdown | <20% of account | <15% | <10% |
| Sharpe Ratio | 0.8 | 1.2 | 1.8+ |
| Average Trade | >2× commission+slippage | >5× | >10× |
| Consecutive Losses | <8 | <6 | <4 |

**Profit factor is the most important single metric.** Win rate alone is meaningless without knowing the average win vs. average loss.

### 2.3 Forward Test Period

After backtesting, paper trade the strategy for a minimum period before live deployment:

- **Minimum forward test**: 30 trading days (6 calendar weeks)
- **Preferred**: 60–90 trading days covering different market conditions
- **Acceptance criteria**: forward test profit factor within 20% of backtest profit factor
- **Red flag**: forward test profit factor below 1.0 — the strategy is likely overfit

### 2.4 Market Condition Dependency

Every strategy works better in some conditions than others. Document explicitly:

- Does it work in trending markets? Ranging markets? Both?
- Does it break down during high-volatility events (FOMC, CPI, earnings)?
- Does it have a session dependency (RTH only? Overnight?)
- Does it degrade during low-volume periods (holidays, summer)?

A strategy that only works in one regime is not a strategy — it's a bet on that regime continuing.

---

## 3. Red Flags: Signs of Curve Fitting

Curve fitting (overfitting) is the most common failure mode in strategy development. The strategy was optimized to fit historical data perfectly but has no predictive power on new data.

### 3.1 Structural Red Flags

**Too many parameters**
- A strategy with 10+ optimizable parameters on 2 years of data is almost certainly overfit
- Rule of thumb: no more than 1 parameter per 50 trades in the backtest

**Suspiciously smooth equity curve**
- Real strategies have drawdowns. A perfectly smooth equity curve means the strategy was fit to avoid every historical drawdown — it will fail on the next one.

**No losing months**
- Any strategy claiming no losing months over 2+ years is either overfit or the backtest is wrong

**Optimal parameters are at extremes**
- If the best parameter value is at the edge of the tested range (e.g., "period = 200" when you tested 10–200), the optimization found a boundary artifact, not a real edge

### 3.2 Backtest Quality Red Flags

**No out-of-sample results**
- If the vendor or developer cannot show OOS performance, assume the strategy is overfit

**Backtest uses "look-ahead" data**
- Common in NinjaScript: using `Close[0]` (current bar's close) in a condition that should only know the prior bar's close. This is a subtle but fatal error.

**Unrealistic fill assumptions**
- Backtests that assume limit orders always fill at the limit price are optimistic — in reality, limit orders at the bid/ask may not fill if price only touches the level briefly

**No slippage or commission**
- A strategy that is profitable before costs but not after is not a strategy

### 3.3 Presentation Red Flags

**No drawdown statistics**
- Any legitimate strategy report includes maximum drawdown, average drawdown, and drawdown duration

**Cherry-picked time periods**
- "This strategy returned 200% in 2023" — what did it do in 2022? 2024?

**Equity curve starts at a convenient point**
- Backtests that start right after a major market event (COVID crash, 2022 bear market) may be avoiding the hardest conditions

---

## 4. Adapting Strategies for NQ Futures

NQ has specific characteristics that require adjustments vs. equity or other futures strategies.

### 4.1 Liquidity Considerations

- **RTH liquidity**: NQ is highly liquid during 9:30–16:00 ET; spreads are 1 tick ($5) or less
- **Pre-market/after-hours**: liquidity drops significantly; spreads widen to 2–5 ticks; avoid market orders
- **Overnight Globex**: thin liquidity; large orders move price; strategies designed for RTH will behave differently overnight
- **News events**: liquidity evaporates 30 seconds before and after major releases (FOMC, CPI, NFP); any strategy must have a news filter

### 4.2 Session Times

| Session | Hours (ET) | Characteristics |
|---------|-----------|-----------------|
| Globex overnight | 18:00–9:30 | Thin; gap-prone; inventory building |
| RTH open | 9:30–10:30 | Highest volatility; Initial Balance forms |
| Mid-session | 10:30–14:00 | Lower volatility; trend or range develops |
| Power hour | 14:00–16:00 | Volume picks up; institutional rebalancing |
| After-hours | 16:00–18:00 | Thin; avoid |

Most strategies should be restricted to RTH (9:30–16:00 ET) unless specifically designed for overnight trading.

### 4.3 News Sensitivity

NQ is the most news-sensitive major futures contract. Required filters:

- **FOMC days**: volatility 2–3× normal; widen stops or disable strategy
- **CPI/PPI/NFP**: first 15 minutes after release are untradeable for most strategies
- **Tech earnings** (AAPL, MSFT, NVDA, AMZN, GOOGL, META): NQ moves 1–3% on major earnings; disable overnight strategies
- **Quad witching / OpEx**: gamma effects dominate; standard strategies underperform

Use an economic calendar filter in NinjaScript: `Globals.MarketHolidays` or a custom news-time exclusion list.

### 4.4 Volatility Scaling

NQ ATR(14) on a daily chart ranges from ~100 points (low volatility) to ~400+ points (high volatility). Strategies with fixed stop sizes will have wildly different risk profiles across regimes.

**Best practice**: scale stops and targets as a multiple of ATR, not fixed points.

```csharp
// Example: ATR-scaled stop
double atr = ATR(14)[0];
double stopDistance = atr * 0.5;  // 50% of daily ATR
```

### 4.5 Tick Size and Contract Specs

- **Tick size**: 0.25 points = $5 per contract
- **Point value**: $20 per point
- **Margin**: ~$1,000–$2,000 intraday (broker-dependent); ~$16,000 overnight
- **Micro NQ (MNQ)**: 1/10th the size; $2 per point; good for testing

Always test new strategies on MNQ before scaling to NQ.

---

## 5. Integrating with DEEP6

DEEP6's 44-signal engine provides a rich set of order-flow and microstructure signals that can dramatically improve any strategy's signal quality. The key principle: **use DEEP6 signals as confirmation filters, not as standalone triggers.**

### 5.1 Which DEEP6 Signals to Use as Confirmation

| Strategy Type | Primary DEEP6 Confirmation Signals |
|--------------|-------------------------------------|
| Reversal at level | ABS-01 (absorption), EXH-01 (exhaustion), MS-06 (CVD divergence), MS-12 (ExhaustionPostBreak) |
| Breakout continuation | STACKED_IMBALANCE, MS-07 (Hawkes branching), MS-09 (AggressorDominance) |
| Mean reversion / fade | MS-04 (VPIN regime shift), MS-05 (Kyle lambda compression), MS-08 (SpoofSuppressor veto) |
| Trend following | MS-03 (QueueImbalanceBand), MS-11 (DepthAsymmetry), CVD alignment |
| Gap fill | MS-06 (CVD divergence at gap zone), ABS-01 (absorption at gap edge) |

### 5.2 Confluence Weighting

Apply the multi-timeframe confluence tier from the practitioners research:

- **A-grade level** (T1+T2 alignment, e.g., prior-day high + weekly VPOC): multiply signal confidence ×1.5
- **B-grade level** (T2 alone, e.g., prior-day VAH): ×1.0
- **C-grade level** (T3/T4 only, e.g., intraday developing VPOC): ×0.6
- **No level**: do not trade reversal patterns; only trend-continuation setups

### 5.3 DEEP6 as a Gate, Not a Signal

The cleanest integration pattern:

1. Your strategy generates a candidate trade (entry, stop, target)
2. DEEP6 scores the setup using its 44-signal engine
3. Only execute if DEEP6 confidence score exceeds a threshold (e.g., TYPE_A ≥ 80)
4. DEEP6's MS-08 (SpoofSuppressor) acts as a hard veto — if it fires, skip the trade regardless of other signals

This keeps your strategy logic clean and uses DEEP6 as a quality filter rather than rebuilding the entire signal stack.

### 5.4 VPIN as a Regime Filter

DEEP6's VPIN engine (MS-04) provides a flow-toxicity regime:

- **CLEAN** (VPIN percentile < 0.5): normal two-sided flow; reversal strategies work well
- **NORMAL** (0.5–0.7): standard conditions
- **ELEVATED** (0.7–0.85): informed flow increasing; reduce reversal trade size
- **TOXIC** (> 0.85): one-sided informed flow; disable reversal strategies; only trade with the flow

Apply the VPIN confidence multiplier (0.3× in TOXIC, 1.15× in CLEAN) to your position sizing.

### 5.5 Kronos E10 Directional Bias

Kronos-small provides a directional bias (E10) from OHLCV data. Use it as a directional filter:

- Only take long setups when Kronos E10 is bullish or neutral
- Only take short setups when Kronos E10 is bearish or neutral
- Skip setups that conflict with Kronos E10 unless DEEP6 confidence is exceptionally high (TYPE_A+)

This single filter can significantly reduce false signals on counter-trend setups.

---

## 6. Strategy Development Workflow

A disciplined workflow for building a new strategy from scratch:

1. **Hypothesis**: define the market inefficiency you're exploiting (e.g., "NQ tends to fill overnight gaps within the first 30 minutes of RTH")
2. **Manual review**: visually verify the hypothesis on 20–30 historical examples before coding
3. **Code the rules**: implement in NinjaScript with explicit, mechanical entry/exit rules
4. **Initial backtest**: run on 1 year of data; check for obvious errors (unrealistic fills, look-ahead bias)
5. **Parameter sensitivity**: test a range of parameter values; prefer parameters where performance is stable across a range (not a single optimal point)
6. **Walk-forward test**: divide data into 6-month windows; optimize on each window, test on the next
7. **DEEP6 integration**: add DEEP6 signal filters; re-run walk-forward to verify improvement
8. **Paper trade**: 30–60 days on live data with no real money
9. **MNQ live**: trade 1 MNQ contract for 30 days; compare to paper trade results
10. **Scale up**: only if MNQ results match paper trade within 20%

---

*Last verified: 2026-05-12*
