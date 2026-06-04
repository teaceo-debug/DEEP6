# NT8 Backtesting Expert Knowledge Base

## Scope

This skill owns the complete NinjaTrader 8 backtesting surface:
- Strategy Analyzer (all tabs: Backtest, Optimization, Walk-Forward, Multi-Objective)
- Historical data acquisition (download, import, Market Replay, Tick Replay)
- NinjaScript code patterns for backtest accuracy
- Fill accuracy mechanisms (Standard, High, TickReplay, manual tick series)
- Performance metrics interpretation
- Real-time vs backtest discrepancy diagnosis
- Optimization-ready strategy architecture

---

## 1. STRATEGY ANALYZER

### Opening Strategy Analyzer

**Path**: Control Center > New > Strategy Analyzer

**Prerequisites**:
- Historical data loaded for target instrument/date range
- Strategy compiled without errors
- Understanding of backtest properties (this document)

### UI Layout

The Strategy Analyzer has a **type selector** at the top:
- **Backtest** — single parameter set, one run
- **Optimization** — sweep parameter ranges, find best
- **Walk-Forward Optimization** — IS/OOS validation
- **Multi-Objective Optimization** — balance multiple fitness criteria

Results appear in tabs below: **Summary**, **Trades**, **Chart**, **Log**.

---

### 1.1 Backtest Tab

Run a strategy once with fixed parameters on a fixed date range.

**Workflow**:
1. Select Backtest type = "Backtest"
2. Select Strategy from dropdown
3. Configure strategy parameters (expand triangle)
4. Select Instrument (e.g., NQ 09-25)
5. Select Data Series (bar type + interval: 1 Minute, 5 Minute, Daily, etc.)
6. Set Start date and End date
7. Configure backtest properties (below)
8. Click Run

### Critical Backtest Properties

| Property | Default | What It Does | Danger If Wrong |
|----------|---------|-------------|-----------------|
| **Order fill resolution** | Standard | Standard = 3 virtual bars from OHLC. High = secondary data series for fills | Standard overstates fill quality; High is more realistic |
| **Slippage** | 0 ticks | Added to market/stop orders (NOT limit orders) | 0 slippage = unrealistic profit; use 2-5 ticks for NQ |
| **Bars required to trade** | 20 | Min bars before any order allowed | Too low = indicators not warmed up = garbage signals |
| **Maximum bars look back** | 256 | Circular buffer depth for indicator values | 256 is fine for most; use Infinite if strategy looks back 256+ bars |
| **Include commission** | false | Add per-trade commission cost | False = profit inflated by total commission; ALWAYS enable |
| **Fill limit orders on touch** | false | Limit orders fill on first price touch | True = optimistic; false = requires price to trade through |
| **Entries per direction** | 1 | Max concurrent entries in same direction | >1 = pyramiding; usually 1 for single-position strategies |
| **Entry handling** | AllEntries | How to handle duplicate entry signals | UniqueEntries = one per signal name; AllEntries = allow duplicates |
| **Exit on session close** | true | Flatten at session end | True for day-trading; false for swing/position |
| **Exit on session close seconds** | 30 | Seconds before close to flatten | 30s is fine; too close = no fill before close |
| **Start behavior** | WaitUntilFlat | What to do if position exists at strategy start | WaitUntilFlat is safest; ImmediatelySubmit may enter incorrectly |

### Commission Templates

**Path**: Control Center > Tools > Options > Commission

Set per-instrument or per-exchange. Example for NQ:
- Per side: $2.04 (typical retail)
- Round trip: $4.08
- Must be configured BEFORE backtest to appear in results

---

### 1.2 Optimization Tab

Test multiple parameter combinations to find the best-performing set.

**Two Algorithms**:

#### Default (Exhaustive / Brute Force)
- Tests **every** combination
- Guaranteed to find absolute best
- Slow for large parameter spaces
- Example: 3 params × 20 values each = 8,000 iterations
- **Use when**: 2-3 parameters with small ranges

#### Genetic Algorithm (GA)
- Evolutionary approach: fit combinations breed, unfit die
- Tests approximate optimum (not guaranteed absolute best)
- Much faster for large spaces
- **Use when**: 4+ parameters or fine-grained ranges

**Workflow**:
1. Select Backtest type = "Optimization"
2. Select Strategy
3. Expand strategy parameters (click triangle)
4. Set Min, Max, Increment for each parameter to optimize
5. Set "Optimize on..." (fitness metric)
6. Select Optimizer (Default or Genetic)
7. Click Run

### Genetic Algorithm Properties

| Property | Default | Notes |
|----------|---------|-------|
| Generations | 10 | Total iterations = Generation Size x Generations |
| Generation size | 20 | Parameter combos per generation |
| Crossover rate (%) | 80 | % of offspring from parent crossover |
| Mutation rate (%) | 20 | % of offspring with random mutations |
| Mutation strength (%) | 10 | Max offset for mutated parameters |
| Convergence threshold | 5 | Duplicate children before early stopping |
| Minimum performance | 0 | Stop if this fitness reached (0 = disabled) |

### Optimization Fitness Metrics

| Metric | What It Optimizes | When To Use |
|--------|-------------------|-------------|
| Max Net Profit | Total dollars earned | Simple but ignores risk |
| Max Profit Factor | Gross Profit / Gross Loss | Balance profit vs loss; >2.0 is excellent |
| Max Sharpe Ratio | Risk-adjusted return (monthly) | Consistent returns; >2.0 is very good |
| Max Sortino Ratio | Like Sharpe but downside-only vol | When you care about downside more than upside vol |
| Max % Profitable | Win rate | Consistent winners; but ignores trade size |
| Min Drawdown | Smallest max peak-to-trough decline | Risk-focused; <15% is manageable |
| Max Strength | Steadiest equity curve | Favors smooth, consistent growth |
| Custom | Your GetOptimizationMetric() override | Full control; see code section below |

### Custom Optimization Metric (Code)

```csharp
protected override double GetOptimizationMetric()
{
    double netProfit = SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit;
    double maxDD = SystemPerformance.AllTrades.TradesPerformance.Currency.MaxDrawDown;
    int trades = SystemPerformance.AllTrades.Count;

    if (trades < 10 || maxDD == 0) return 0;

    // Profit-to-drawdown ratio — higher is better
    return netProfit / Math.Abs(maxDD);
}
```

---

### 1.3 Walk-Forward Optimization (WFO)

Addresses overfitting by splitting data into In-Sample (optimize) and Out-of-Sample (test).

**Concept**:
```
[IS Period 1: Optimize] -> [OOS Period 1: Test] -> [IS Period 2: Optimize] -> [OOS Period 2: Test] -> ...
```

**Properties**:

| Property | Default | Guidance |
|----------|---------|----------|
| Optimization period (days) | 252 | IS window. Typical: 200-365 days |
| Test period (days) | 30 | OOS window. Typical: 20-60 days |

**IS/OOS Ratio**: 5:1 to 10:1 is standard (e.g., 200 days IS, 30-40 days OOS).

**Robustness Rules**:
- 50%+ of OOS periods profitable = reasonably robust (Robert Pardo rule)
- If optimal parameters change drastically between IS periods, strategy is unstable
- Minimum 10 trades per OOS period for statistical significance
- If OOS performance is dramatically worse than IS, you are overfitting

### Walk-Forward Gotcha

When IS and OOS periods are the same length, multithreading causes different ordering between runs. Use longer IS period to get deterministic results.

---

### 1.4 Multi-Objective Optimization

Balance multiple performance criteria simultaneously using Pareto front.

**Use when**: You want to optimize for BOTH profit AND risk (not just one). The optimizer finds the set of solutions where no single metric can improve without worsening another.

---

## 2. HISTORICAL DATA

### 2.1 Data Sources

#### Built-In Download (Historical Data Manager)

**Access**: Control Center > Tools > Historical Data

**Tabs**: Download | Loaded | Edit | Export

**Download Workflow**:
1. Select instrument (or instrument list)
2. Select Start/End date range
3. Select Intervals (Tick, Minute, Day)
4. Select Data Types (Last, Bid, Ask)
5. Press Download
6. Status appears bottom-right

**Key Rules**:
- Downloads REPLACE existing data in the date range
- For futures: only downloads the selected contract month
- For multi-year futures: download each contract month separately
- Closing the window cancels the download
- Check Edit tab first to see what's already loaded

**Data Loading Hierarchy** (fastest to slowest):
1. Memory (currently in use)
2. Cache (local hard drive: `Documents\NinjaTrader 8\db\`)
3. Provider (internet download)

NT8 uses all three automatically to fill gaps.

#### Provider Data Availability

| Provider | Tick Data | Minute Data | Daily Data |
|----------|----------|-------------|------------|
| Rithmic/CQG (via HDS) | 1 year | 10+ years | 10+ years |
| Kinetick (paid) | 180 days | 2 years | 10+ years |
| Kinetick (free) | None | None | 10+ years |
| IQFeed | 180 days | 2 years | 10+ years |
| Interactive Brokers | None | Limited | Limited |

#### Market Replay Data (Most Accurate)

Compressed files with exact Level I + Level II tick sequence, recorded live.

**Storage**: `Documents\NinjaTrader 8\db\replay\<instrument>\YYYYMMDD.nrd`

**Availability**: ~90 days free for common futures/forex. One day at a time.

**Download**:
1. Open Historical Data window
2. Expand "Get Market Replay data"
3. Select instrument and date
4. Press OK

**Use for**: Most accurate backtesting possible (exact tick sequence + depth).

**Sharing**: Copy entire `db\replay\` folder to another NT8 installation.

#### Kinetick Free (EOD)

- End-of-day (daily) bars only
- Stocks, futures, forex
- 10+ years historical daily data
- No subscription required
- Setup: Control Center > Connections > Kinetick - End Of Day (Free)

#### Manual Import (CSV/Text)

**Access**: Control Center > Tools > Historical Data > Loaded > Import

**File Formats**:

Day bars: `yyyyMMdd;open;high;low;close;volume`
Minute bars: `yyyyMMdd HHmmss;open;high;low;close;volume`
Tick data: `yyyyMMdd HHmmss;price;volume`

**Critical Requirements**:
- File name MUST match exact instrument name (including expiration for futures)
- Futures/Forex instruments MUST exist in database before import
- Timezone must match source data
- Prices rounded to instrument tick size on import

---

### 2.2 Tick Replay

**What It Is**: Replays historical 1-tick data to build bars as if live, enabling `OnEachTick`/`OnPriceChange` processing in backtest.

**Enable**: Tools > Options > Market Data > "Show Tick Replay" (hidden by default)

**What Tick Replay Enables**:
- OnBarUpdate fires on each tick in historical data
- IsFirstTickOfBar works correctly in historical
- OnMarketData(MarketDataType.Last) triggers historically

**What Tick Replay Does NOT Enable**:
- Accurate order fills (still uses OHLC)
- Bid/Ask data (MarketDataType.Bid/Ask won't trigger)

**Critical Limitation**: Cannot combine Tick Replay + High Order Fill Resolution.

**Data Availability**: Only ~1 year of historical tick data available.

**Performance Impact**: Generates thousands of events per bar. Backtests run 10-100x slower.

---

### 2.3 Merge Policy (Futures Rollover)

| Policy | Behavior | Use For |
|--------|----------|---------|
| MergeBackAdjusted (default) | Loads all contract months, back-adjusts prices to prevent gaps | Most analysis and backtesting |
| MergeNonBackAdjusted | Loads all contracts, no offset | Analyzing actual contract prices |
| DoNotMerge | Loads only selected contract month | Single-contract analysis |

---

### 2.4 Data Storage

| What | Where |
|------|-------|
| Historical bars | `Documents\NinjaTrader 8\db\` |
| Market Replay | `Documents\NinjaTrader 8\db\replay\` |
| Cache | `Documents\NinjaTrader 8\db\cache\` |
| Database | `Documents\NinjaTrader 8\db\NinjaTrader.sqlite` |

---

### 2.5 Data Accuracy Hierarchy

Best to worst for backtesting accuracy:

1. **Market Replay + Playback** — exact tick sequence + Level II depth
2. **Tick Replay + 1-Tick series** — intra-bar fills with tick granularity
3. **High Order Fill Resolution** — intra-bar fills, no Tick Replay
4. **Historical Data + OnBarClose** — OHLC only
5. **Historical Data + OnEachTick (no Tick Replay)** — processed as OnBarClose anyway

---

## 3. NINJASCRIPT BACKTEST CODE PATTERNS

### 3.1 State Machine for Backtesting

```csharp
protected override void OnStateChange()
{
    if (State == State.SetDefaults)
    {
        // Called ONCE when strategy instantiated
        // Set: Name, Calculate, BarsRequiredToTrade, all defaults
        // DO: AddPlot(), AddLine()
        // DO NOT: Access bar data, create Series<T>, instantiate indicators
        Name = "MyStrategy";
        Calculate = Calculate.OnBarClose;
        BarsRequiredToTrade = 50;
        IsInstantiatedOnEachOptimizationIteration = true;
        MaximumBarsLookBack = MaximumBarsLookBack.TwoHundredFiftySix;
    }
    else if (State == State.Configure)
    {
        // Called ONCE after SetDefaults
        // DO: AddDataSeries() — MUST be hardcoded, no runtime variables
        // DO NOT: Access bar data, create Series<T>
        AddDataSeries(BarsPeriodType.Minute, 5); // BarsArray[1]
    }
    else if (State == State.DataLoaded)
    {
        // Called ONCE after all bars loaded
        // DO: Create Series<T>, instantiate indicators, initialize collections
        // DO: SetStopLoss(), SetProfitTarget()
        mySignal = new Series<double>(this);
        fastMA = SMA(Close, FastPeriod);
        slowMA = SMA(Close, SlowPeriod);
        SetStopLoss(CalculationMode.Ticks, StopLossTicks);
        SetProfitTarget(CalculationMode.Ticks, ProfitTargetTicks);
    }
    else if (State == State.Historical)
    {
        // Called ONCE when historical processing begins
        // Only in backtest — skipped in realtime-only mode
    }
    else if (State == State.Realtime)
    {
        // Called ONCE when realtime data begins
        // In pure backtest: this state is SKIPPED
    }
    else if (State == State.Terminated)
    {
        // Called ONCE when strategy removed
        // MUST dispose SharpDX resources, unsubscribe events
    }
}
```

### State Machine Backtest Implications

| State | Backtest-Critical Notes |
|-------|------------------------|
| SetDefaults | Runs once per instance. Set BarsRequiredToTrade high enough for ALL indicators |
| Configure | AddDataSeries() MUST be hardcoded (no runtime variables allowed) |
| DataLoaded | ONLY place to create Series<T> and indicators — NOT SetDefaults |
| Historical | Runs once as backtest begins. Can force Calculate mode for historical-only |
| Realtime | SKIPPED in pure backtest. Don't put backtest logic here |
| Terminated | Always runs. Dispose or leak resources |

---

### 3.2 Calculate Modes

| Mode | OnBarUpdate Calls (Historical) | OnBarUpdate Calls (Realtime) |
|------|-------------------------------|------------------------------|
| **OnBarClose** | Once per bar close | Once per bar close |
| **OnEachTick** | Once per bar close (NO tick data without Tick Replay) | Every tick |
| **OnPriceChange** | Once per bar close (NO price change data) | Every price change |

**The Critical Gotcha**: In historical data, `OnEachTick` and `OnPriceChange` behave IDENTICALLY to `OnBarClose` unless Tick Replay is enabled. This is the #1 source of backtest/live discrepancy.

> "On a historical data set, only the OHLCVT of the bar is known and not each tick that made up the bar."
> — NinjaTrader official documentation

---

### 3.3 Multi-Series Strategies

```csharp
protected override void OnStateChange()
{
    if (State == State.Configure)
    {
        // BarsArray[0] = primary series (chart bar type)
        // BarsArray[1] = first AddDataSeries
        AddDataSeries(BarsPeriodType.Minute, 5);  // BarsArray[1]
    }
}

protected override void OnBarUpdate()
{
    // MANDATORY: Guard which series triggered this call
    if (BarsInProgress != 0) return;

    // MANDATORY: Check ALL series have enough bars
    if (CurrentBars[0] < BarsRequiredToTrade || CurrentBars[1] < BarsRequiredToTrade)
        return;

    // Now safe to access both series
    double primaryClose = Close[0];        // Primary series
    double secondaryClose = Closes[1][0];  // Secondary series
}
```

**Multi-Series Backtest Timing Rule**: Orders submitted on primary series are filled IMMEDIATELY, before secondary series runs its OnBarUpdate. Submit orders to the most granular series to avoid timing artifacts.

---

### 3.4 IsFirstTickOfBar — Historical/Realtime Parity

```csharp
protected override void OnBarUpdate()
{
    if (IsFirstTickOfBar)
    {
        // REALTIME (OnEachTick): fires on first tick of new bar
        // BACKTEST (OnEachTick + TickReplay): same as realtime
        // BACKTEST (OnEachTick WITHOUT TickReplay): ALWAYS true (breaks parity)
        // BACKTEST (OnBarClose): ALWAYS true (by definition)

        // Use Close[1] here (the just-closed bar), not Close[0]
        if (Close[1] > SMA(20)[1])
            EnterLong();
    }
}
```

**Without TickReplay**, `IsFirstTickOfBar` is meaningless in backtest — it's always true.

---

### 3.5 Bar Index Differences: Backtest vs Realtime

| Context | Close[0] Means | Close[1] Means |
|---------|----------------|----------------|
| Backtest + OnBarClose | Just-closed bar | Bar before that |
| Realtime + OnBarClose | Just-closed bar | Bar before that |
| Realtime + OnEachTick | Currently BUILDING bar | Just-closed bar |
| Backtest + OnEachTick (no TickReplay) | Just-closed bar | Bar before that |

**Parity Pattern**: Always use `Close[1]` (closed bar) when using OnEachTick with IsFirstTickOfBar, regardless of backtest or realtime.

---

## 4. COMMON BACKTEST-KILLING BUGS

### Bug 1: Look-Ahead Bias

```csharp
// WRONG: Using Close[0] in OnBarClose to decide entry on SAME bar
if (Close[0] > Open[0])  // Green bar — but bar is already closed
    EnterLong();           // Enters at the close price you just used to decide

// RIGHT: Use previous bar to decide, enter on current bar
if (Close[1] > Open[1])  // Previous bar was green
    EnterLong();           // Enters on current bar open
```

### Bug 2: No BarsInProgress Guard (Multi-Series)

```csharp
// WRONG: Runs for EVERY series update
protected override void OnBarUpdate()
{
    if (Close[0] > SMA(20)[0])
        EnterLong();  // Fires 3x per bar if 3 series loaded
}

// RIGHT: Guard the series
protected override void OnBarUpdate()
{
    if (BarsInProgress != 0) return;
    if (Close[0] > SMA(20)[0])
        EnterLong();  // Fires once per bar
}
```

### Bug 3: Not Checking CurrentBars for All Series

```csharp
// WRONG: Only checking primary series
if (CurrentBar < BarsRequiredToTrade) return;
// Secondary might not have enough bars — crash on Closes[1][10]

// RIGHT: Check all series
if (CurrentBars[0] < BarsRequiredToTrade || CurrentBars[1] < BarsRequiredToTrade)
    return;
```

### Bug 4: Creating Series<T> in SetDefaults

```csharp
// WRONG: No bars loaded yet
if (State == State.SetDefaults)
    mySeries = new Series<double>(this);  // ERROR

// RIGHT: Bars are loaded
if (State == State.DataLoaded)
    mySeries = new Series<double>(this);  // OK
```

### Bug 5: Accessing Bar Data in Configure

```csharp
// WRONG: No bars loaded in Configure
if (State == State.Configure)
    double rsi = RSI(14)[0];  // ERROR: No bars!

// RIGHT: Access bar data only in OnBarUpdate
protected override void OnBarUpdate()
{
    if (CurrentBar < 14) return;
    double rsi = RSI(14)[0];  // OK
}
```

### Bug 6: BarsRequiredToTrade Too Low

```csharp
// WRONG: Using 200-period SMA with default BarsRequiredToTrade of 20
BarsRequiredToTrade = 20;  // SMA(200) outputs garbage for bars 0-199

// RIGHT: Set >= longest indicator period
BarsRequiredToTrade = 200;
```

### Bug 7: Indicator Values Differ Between Backtest and Live

When using `Calculate.OnEachTick`, indicators recalculate on every tick in realtime but only on bar close in backtest (without Tick Replay). This causes different indicator values.

**Fix**: Use `IsFirstTickOfBar` and reference `[1]` (closed bar), or force `Calculate.OnBarClose`.

### Bug 8: Non-Deterministic Time Checks Without BarsInProgress Guard

```csharp
// WRONG: Time check runs for every series — each has different timestamps
if (Times[0][0].TimeOfDay >= new TimeSpan(9, 0, 0))
    EnterLong();

// RIGHT: Guard the series
if (BarsInProgress != 0) return;
if (Times[0][0].TimeOfDay >= new TimeSpan(9, 0, 0))
    EnterLong();
```

---

## 5. FILL ACCURACY

### Three Approaches to Intrabar Accuracy

| Approach | Method | Accuracy | Speed | Complexity |
|----------|--------|----------|-------|------------|
| Standard | OnBarClose + OHLC fills | Low | Fast | Low |
| Tick Replay | OnEachTick + tick data | Medium | Slow | Medium |
| High OrderFillResolution | Secondary data series for fills | High | Medium | Medium |
| Manual Tick Series | AddDataSeries(Tick, 1) | Highest | Slowest | High |

### Approach 1: Tick Replay

```csharp
// In SetDefaults:
Calculate = Calculate.OnEachTick;
// Enable "Tick Replay" checkbox in Strategy Analyzer

// Enables: OnBarUpdate fires on each tick historically
// Enables: IsFirstTickOfBar works correctly
// Does NOT enable: Accurate order fills (still OHLC)
// Does NOT enable: Bid/Ask data
// CANNOT combine with: High Order Fill Resolution
```

### Approach 2: High OrderFillResolution

```csharp
// In SetDefaults:
Calculate = Calculate.OnBarClose;
OrderFillResolution = OrderFillResolution.High;

// In Configure:
AddDataSeries(BarsPeriodType.Tick, 1);  // Secondary series for fills

// Enables: Intrabar order fills using secondary series prices
// Does NOT enable: Intrabar OnBarUpdate calls
// CANNOT combine with: Tick Replay
```

### Approach 3: Manual Tick Series (Most Control)

```csharp
// In Configure:
AddDataSeries(BarsPeriodType.Tick, 1);  // BarsArray[1]

// In OnBarUpdate:
if (BarsInProgress == 0)  // Primary series
{
    if (entryCondition)
        EnterLong(1, 1, "Entry");  // Submit to tick series (BarsInProgress 1)
}
// Orders fill at tick prices from secondary series
```

### Order Fill Behavior: Backtest vs Realtime

| Aspect | Backtest | Realtime |
|--------|----------|----------|
| Data available | OHLC only (without Tick Replay) | Tick-by-tick |
| Order fills | At OHLC prices | At actual market prices |
| Intrabar fills | Not possible (unless TickReplay/High) | Every tick |
| Slippage | Deterministic (user-set) | Market-dependent |
| Bid/Ask spread | Not modeled | Real spread |

### Slippage Rules

- Expressed in ticks (minimum price movement)
- Applied to: market orders, stop-market orders, MIT orders
- NOT applied to: limit orders
- Cannot exceed the bar's High-Low range
- Realistic NQ slippage: 2-5 ticks

---

## 6. PERFORMANCE METRICS

### Key Trade Statistics

| Statistic | Definition | Good Threshold |
|-----------|-----------|----------------|
| Net Profit | Total profit after all costs | Positive after commission+slippage |
| Profit Factor | Gross Profit / Gross Loss | >1.5 acceptable, >2.0 excellent |
| Sharpe Ratio | Monthly profit / monthly std dev | >1.0 good, >2.0 very good |
| Sortino Ratio | Like Sharpe, downside vol only | >1.5 good, >2.5 very good |
| Max Drawdown | Largest peak-to-trough equity decline | <15% manageable, <30% acceptable |
| Win Rate (% Profitable) | Winning trades / Total trades | >55% for mean-reversion, >35% for trend |
| Average Trade | Net profit / # of trades | Must exceed commission + slippage |
| Max Consecutive Losers | Longest losing streak | <10 manageable |
| Total Trades | All trades in period | ≥30 for statistical significance |
| Avg Winner / Avg Loser | Reward-to-risk ratio | >1.5 good, >2.0 excellent |

### Red Flags in Backtest Results

- Profit Factor < 1.5 — losing more than earning
- Max Drawdown > 30% — excessive risk
- Sharpe Ratio < 1.0 — poor risk-adjusted return
- Max consecutive losers > 10 — high drawdown risk
- OOS much worse than IS — overfitting
- Win rate > 90% — almost certainly overfitted or look-ahead bias
- Profit Factor > 5.0 with low trade count — curve-fitted
- Average trade < commission + slippage — net negative expectancy

### Green Flags

- Profit Factor > 2.0 — strong edge
- Max Drawdown < 15% — controlled risk
- Sharpe Ratio > 2.0 — excellent risk-adjusted returns
- Win rate 50-70% — realistic range for most strategies
- OOS performance within 30% of IS — robust
- Consistent equity curve — no single trade dominates P&L

---

## 7. OPTIMIZATION-READY STRATEGY CODE

### Exposing Parameters for Strategy Analyzer

```csharp
// In SetDefaults:
FastPeriod = 10;
SlowPeriod = 20;
StopLossTicks = 20;
ProfitTargetTicks = 40;

// Properties with NinjaScriptProperty + Range become optimizer parameters
[NinjaScriptProperty]
[Range(5, 50)]
[Display(Name = "Fast Period", Order = 1, GroupName = "Parameters")]
public int FastPeriod { get; set; }

[NinjaScriptProperty]
[Range(10, 100)]
[Display(Name = "Slow Period", Order = 2, GroupName = "Parameters")]
public int SlowPeriod { get; set; }

[NinjaScriptProperty]
[Range(1, 100)]
[Display(Name = "Stop Loss Ticks", Order = 3, GroupName = "Risk")]
public int StopLossTicks { get; set; }

[NinjaScriptProperty]
[Range(1, 200)]
[Display(Name = "Profit Target Ticks", Order = 4, GroupName = "Risk")]
public int ProfitTargetTicks { get; set; }
```

### IsInstantiatedOnEachOptimizationIteration

```csharp
// DEFAULT (true): Strategy RE-CREATED for each optimization iteration
// - All class variables reset to defaults
// - Slower but safer (no state carryover)
IsInstantiatedOnEachOptimizationIteration = true;

// OPTIMIZED (false): Strategy RE-USED across iterations
// - Class variables CARRY OVER — you MUST reset them manually in DataLoaded
// - Faster (less memory/CPU)
// - DANGEROUS if you forget to reset any variable
if (State == State.DataLoaded)
{
    // MUST reset ALL class variables when reusing instance
    myTrades = new Dictionary<DateTime, string>();
    myCounter = 0;
    myFlag = false;
    myList = new List<int>();
}
```

### MaximumBarsLookBack

```csharp
// TwoHundredFiftySix (default): Circular ring buffer, overwrites old values
// - Best for memory performance
// - Fine for most strategies

// Infinite: All values stored in memory
// - Needed if strategy looks back 256+ bars
// - Higher memory usage during optimization (many iterations)

// Per-series override:
if (State == State.DataLoaded)
{
    shortLookback = new Series<double>(this, MaximumBarsLookBack.TwoHundredFiftySix);
    longLookback  = new Series<double>(this, MaximumBarsLookBack.Infinite);
}
```

---

## 8. REAL-TIME VS BACKTEST DISCREPANCIES

### Why Results Will Always Differ

You should **expect** differences. The question is whether the difference is acceptable.

| Source of Discrepancy | Impact | Mitigation |
|----------------------|--------|------------|
| OHLC-only fill prices | Fills at prices that may not have been tradeable | Use High OrderFillResolution or Tick Replay |
| No bid/ask spread modeling | Fills assume zero spread | Add slippage to approximate |
| OnEachTick only fires on bar close | Intrabar logic never runs historically | Enable Tick Replay |
| Indicator values differ | OnEachTick indicators change intra-bar live, not in backtest | Use IsFirstTickOfBar + [1] indexing |
| Non-standard bar types | Renko, HeikenAshi, P&F form differently | Use standard bars for backtest; use Playback for non-standard |
| Market Replay vs Historical | Market Replay = exact ticks; Historical = OHLC | Use Market Replay for highest fidelity |

### Bar Types That Backtest Poorly

| Bar Type | Backtest Accuracy | Recommendation |
|----------|------------------|----------------|
| Minute/Daily bars | Good | Default choice |
| Tick/Volume bars | Good | Works well with historical tick data |
| Renko | Poor | Cannot be accurately backtested; use Playback |
| HeikenAshi | Poor | Uses averaged OHLC; use HA as indicator overlay instead |
| Point & Figure | Poor | Inherently different formation; expect large discrepancies |
| Range bars | Moderate | Better with Tick Replay |

---

## 9. BEST PRACTICES CHECKLISTS

### Pre-Backtest Checklist

- [ ] Strategy compiles without errors
- [ ] Historical data downloaded for instrument + date range
- [ ] BarsRequiredToTrade >= longest indicator period
- [ ] Commission template configured and enabled
- [ ] Slippage set to realistic value (2-5 ticks for NQ)
- [ ] MaximumBarsLookBack set appropriately
- [ ] Data series type matches intended bar type
- [ ] Start/end dates cover sufficient period (>= 6 months)
- [ ] Date range includes various market conditions (trending + ranging)
- [ ] Account size set realistically (matches actual account)

### Pre-Optimization Checklist

- [ ] Single backtest produces reasonable results first
- [ ] Parameters exposed with [NinjaScriptProperty] + [Range]
- [ ] Parameter ranges are reasonable (not 1-10000)
- [ ] Optimizer selected (Default for 2-3 params, Genetic for 4+)
- [ ] Fitness metric selected (not just Max Net Profit)
- [ ] "Keep best # results" set to prevent memory issues

### Optimization Workflow

1. Start simple: optimize 1-2 most important parameters first
2. Use recent data: optimize on last 6-12 months
3. Check results: ensure >= 30 trades per backtest
4. Compare algorithms: run Default and Genetic, compare
5. Validate robustness: run Walk-Forward Optimization
6. Test forward: run strategy on Playback, compare to backtest
7. Paper trade: run sim with optimized parameters before going live

### Walk-Forward Validation Rules

1. IS/OOS ratio: 5:1 to 10:1
2. Minimum 10 trades per OOS period
3. 50%+ of OOS periods profitable = reasonably robust
4. Parameter stability: optimal params shouldn't change drastically
5. OOS performance within 30% of IS = robust

---

## 10. COMPLETE BACKTEST-READY STRATEGY TEMPLATE

```csharp
namespace NinjaTrader.NinjaScript.Strategies
{
    public class BacktestReadyTemplate : Strategy
    {
        private Series<double> signalSeries;
        private SMA fastSMA;
        private SMA slowSMA;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                                = "BacktestReadyTemplate";
                Description                         = "Template with correct backtest patterns";
                Calculate                           = Calculate.OnBarClose;
                EntriesPerDirection                  = 1;
                EntryHandling                        = EntryHandling.UniqueEntries;
                IsExitOnSessionCloseStrategy         = true;
                ExitOnSessionCloseSeconds            = 30;
                StartBehavior                        = StartBehavior.WaitUntilFlat;
                RealtimeErrorHandling                = RealtimeErrorHandling.StopCancelClose;
                StopTargetHandling                   = StopTargetHandling.PerEntryExecution;
                BarsRequiredToTrade                  = 50;
                MaximumBarsLookBack                  = MaximumBarsLookBack.TwoHundredFiftySix;
                IsInstantiatedOnEachOptimizationIteration = true;

                // Parameters
                FastPeriod       = 10;
                SlowPeriod       = 20;
                StopLossTicks    = 20;
                ProfitTargetTicks = 40;
            }
            else if (State == State.Configure)
            {
                // AddDataSeries(BarsPeriodType.Minute, 5);  // Uncomment for multi-series
            }
            else if (State == State.DataLoaded)
            {
                signalSeries = new Series<double>(this);
                fastSMA = SMA(Close, FastPeriod);
                slowSMA = SMA(Close, SlowPeriod);
                SetStopLoss(CalculationMode.Ticks, StopLossTicks);
                SetProfitTarget(CalculationMode.Ticks, ProfitTargetTicks);
            }
            else if (State == State.Terminated)
            {
                // Dispose resources if needed
            }
        }

        protected override void OnBarUpdate()
        {
            // Guard 1: Only process primary series
            if (BarsInProgress != 0) return;

            // Guard 2: Enough bars for indicators
            if (CurrentBar < BarsRequiredToTrade) return;

            // Guard 3: Multi-series bar count (uncomment if using AddDataSeries)
            // if (CurrentBars[1] < BarsRequiredToTrade) return;

            // Signal calculation
            signalSeries[0] = fastSMA[0] > slowSMA[0] ? 1 : -1;

            // Entry logic — use [1] reference for parity if OnEachTick
            if (Position.MarketPosition == MarketPosition.Flat)
            {
                if (CrossAbove(fastSMA, slowSMA, 1))
                    EnterLong(1, "Long");
                else if (CrossBelow(fastSMA, slowSMA, 1))
                    EnterShort(1, "Short");
            }
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(5, 50)]
        [Display(Name = "Fast Period", Order = 1, GroupName = "Parameters")]
        public int FastPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(10, 100)]
        [Display(Name = "Slow Period", Order = 2, GroupName = "Parameters")]
        public int SlowPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "Stop Loss Ticks", Order = 3, GroupName = "Risk")]
        public int StopLossTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 200)]
        [Display(Name = "Profit Target Ticks", Order = 4, GroupName = "Risk")]
        public int ProfitTargetTicks { get; set; }
        #endregion
    }
}
```

---

## 11. TROUBLESHOOTING

| Problem | Likely Cause | Solution |
|---------|-------------|----------|
| Backtest shows no trades | BarsRequiredToTrade too high, date range too short, or entry conditions never met | Lower BarsRequiredToTrade, extend date range, add Print() to debug |
| Backtest differs from live | OnEachTick without Tick Replay, OHLC fill assumptions | Enable Tick Replay, add slippage, use High fill resolution |
| Optimization runs out of memory | Too many parameter combinations, "Keep best" too high | Use Genetic optimizer, reduce "Keep best # results" to 10-20 |
| Walk-Forward results vary between runs | IS and OOS periods same length + multithreading | Use longer IS period (e.g., 365 IS, 180 OOS) |
| Data not showing on chart | Wrong Trading Hours template, data not downloaded | Change to 24/7 trading hours; verify data in Edit tab |
| Strategy trades before indicators stabilize | BarsRequiredToTrade < longest indicator period | Set BarsRequiredToTrade >= longest indicator |
| "Too many parameters to optimize" error | Default optimizer can't handle the combinatorial space | Switch to Genetic Algorithm |
| Negative P&L despite good signals | Commission and slippage not configured | Enable commission template, set realistic slippage |
| Huge win rate (>90%) | Look-ahead bias or curve fitting | Check for Close[0] usage in entry logic; review signal logic |
| Excellent IS, terrible OOS | Overfitting | Reduce parameter count, widen ranges, use more data |

---

## REFERENCES

| Topic | URL |
|-------|-----|
| Strategy Analyzer | https://ninjatrader.com/support/helpguides/nt8/strategy_analyzer.htm |
| Backtest Guide | https://ninjatrader.com/support/helpGuides/nt8/backtest_a_strategy.htm |
| Optimization Guide | https://ninjatrader.com/support/helpguides/nt8/optimize_a_strategy.htm |
| Genetic Algorithm | https://ninjatrader.com/support/helpguides/nt8/genetic_algorithm.htm |
| Walk-Forward | https://ninjatrader.com/support/helpguides/nt8/walk_forward_optimize_a_strate.htm |
| Fill Processing | https://ninjatrader.com/support/helpguides/nt8/understanding_historical_fill_.htm |
| Performance Stats | https://ninjatrader.com/support/helpguides/nt8/statistics_definitions.htm |
| Discrepancies | https://ninjatrader.com/support/helpGuides/nt8/discrepancies_real-time_vs_bac.htm |
| Calculate Modes | https://ninjatrader.com/support/helpGuides/nt8/calculate.htm |
| OnStateChange | https://ninjatrader.com/support/helpGuides/nt8/onstatechange.htm |
| AddDataSeries | https://ninjatrader.com/support/helpguides/nt8/adddataseries.htm |
| BarsInProgress | https://ninjatrader.com/support/helpGuides/nt8/barsinprogress.htm |
| IsFirstTickOfBar | https://ninjatrader.com/support/helpGuides/nt8/isfirsttickofbar.htm |
| Intrabar Granularity | https://support.ninjatrader.com/s/article/Developer-Guide-Improving-backtest-order-fill-accuracy-with-intrabar-granularity |
| Tick Replay | https://ninjatrader.com/support/helpguides/nt8/developing_for__tick_replay.htm |
| Historical Data Manager | https://ninjatrader.com/support/helpguides/nt8/historical_data_manager.htm |
| Data Import | https://ninjatrader.com/support/helpguides/nt8/importing.htm |
| Merge Policy | https://ninjatrader.com/support/helpguides/nt8/merge_policy.htm |
| MaximumBarsLookBack | https://ninjatrader.com/support/helpGuides/nt8/maximumbarslookback.htm |
| Optimization Metric | https://ninjatrader.com/support/helpGuides/nt8/getoptimizationmetric.htm |
| OrderFillResolution | https://ninjatrader.com/support/helpGuides/nt8/orderfillresolution.htm |
