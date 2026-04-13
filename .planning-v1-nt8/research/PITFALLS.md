# Domain Pitfalls: Footprint Auto-Trading System (DEEP6)

**Domain:** Institutional footprint auto-trading on NQ futures — 44 signals, ML optimization, NT8 execution
**Researched:** 2026-04-11
**Confidence:** HIGH on NT8-specific pitfalls (forum-verified); MEDIUM on ML/overfitting specifics (academic literature);
LOW on GEX API update frequency details (vendor-specific, not publicly documented)

---

## Critical Pitfalls

These mistakes cause rewrites, blown accounts, or systems that work in backtest but fail live.

---

### Pitfall 1: 44-Signal Overfitting on a Single Instrument

**What goes wrong:**
44 signals, all optimized against NQ historical data, appear to have high combined accuracy in backtest. In live trading, the system underperforms because many parameters were fit to regime-specific noise rather than persistent microstructure structure. Academic research shows: for every free parameter optimized, you need approximately 200 out-of-sample trades to validate it. A 44-signal system with even 3 parameters per signal requires 26,400 out-of-sample trades before the backtest is statistically meaningful.

**Why it happens:**
- All 44 signals are scored against the same NQ price history
- Threshold selection (e.g., AbsorbWickMin, ImbRatio) is tuned on in-sample data
- Walk-forward efficiency (WFE = OOS return / IS return) never measured — strategies with WFE < 70% are overfit
- Single-instrument testing hides regime dependency (bull vs bear vs choppy markets behave differently)

**Consequences:**
- System generates strong backtest P&L, then loses money live
- ML parameter optimizer (Python backend) reinforces the overfit by finding local optima on historical data
- No signal survives regime change (COVID volatility, rate shock, etc.) without re-tuning

**Prevention:**
1. Implement walk-forward validation: train on rolling 6-month window, test on next 2 months, advance by 1 month, repeat
2. Measure WFE for every signal class, not just the composite score; target WFE > 70%
3. Enforce a minimum 200 out-of-sample trades per signal before adding it to the voting ensemble
4. Treat NQ-only validation as necessary but not sufficient; validate thresholds make economic sense (absorption wick % should be near 30-60%, not 5% or 95%)
5. Use combinatorial purged cross-validation (CPCV) for ML components — shown to outperform naive walk-forward in preventing false discovery

**Warning signs:**
- Backtest Sharpe > 3.0 with in-sample optimization — almost certainly overfit
- Adding the 40th signal improves backtest more than removing any single signal hurts it
- Signal thresholds converge to extreme values (e.g., AbsorbWickMin = 2% or 98%)
- ML model reports >85% accuracy on training data

**Phase to address:** Auto-execution phase (P4b) and ML backend phase — DO NOT go live until walk-forward validation pipeline exists.

**Severity:** CRITICAL

---

### Pitfall 2: GC Pressure Destroying Real-Time Edge at 1,000 Callbacks/Second

**What goes wrong:**
The existing DEEP6.cs already has confirmed GC-pressure issues (see CONCERNS.md): `v.ToArray()` + LINQ allocations in the Std() helper (called in RunE3 on every OnMarketDepth event), `List<T>.RemoveAll()` scanning growing lists on every tick, and `new SolidColorBrush(...)` per render cell. Adding 44 signals expands the hot path substantially. A .NET GC pause of even 10-20ms causes missed ticks, stale signal state, and execution at the wrong price.

**Why it happens:**
- .NET Framework 4.8 has no generational GC tuning options for real-time workloads
- NinjaScript's single-threaded instrument processing means a GC pause blocks ALL event processing
- Developers add signals incrementally without profiling the aggregate allocation rate
- List<T> with RemoveAll is O(n) per call on every depth tick — at 1,000/sec on a 10,000-item list, this is 10M comparisons/second

**Consequences:**
- GC pauses cause missed DOM updates → stale E2/E3 signal state → false or missed signals
- SharpDX render stutters make the chart unusable during high-volatility periods (exactly when you need it most)
- System appears to work fine in slow markets, fails precisely during high-frequency moves

**Prevention:**
1. Fix known allocations BEFORE adding 44 signals — the order matters:
   - Replace `v.ToArray() + LINQ` in Std() with Welford's online algorithm (O(1), zero allocation)
   - Replace `SolidColorBrush` per cell with a pre-allocated 32-color palette indexed by imbalance ratio
   - Replace `List<T>.RemoveAll()` in E3/E4 with a circular buffer (fixed capacity, timestamp-based eviction)
   - Replace LINQ in Scorer (`.Zip().Sum()`) with a manual loop over pre-allocated float arrays
2. Profile with NT8's NinjaScript Utilization Monitor before and after each engine addition
3. Target: zero allocations in OnMarketDepth hot path; all signal state updates via struct mutation
4. Cap `_pLg` and `_pTr` at 1,000 entries with FIFO eviction regardless of expiry logic

**Warning signs:**
- NT8 Utilization Monitor shows DEEP6 consuming >5% of total indicator time per bar
- Chart rendering visible stutters during news releases or opening bell
- DOM snapshot in E2 shows stale values (not updating with each depth event)
- `GC.CollectionCount()` rising faster than 1 collection/second in Gen0

**Phase to address:** Before the 44-signal expansion phase — this is a prerequisite, not a later cleanup.

**Severity:** CRITICAL

---

### Pitfall 3: DOM Backtesting is Structurally Impossible in NT8

**What goes wrong:**
The entire DEEP6 signal suite — E2 Trespass (DOM queue imbalance), E3 CounterSpoof (Wasserstein-1 on order cancels), E4 Iceberg (refill timing), and all 44 signals that use per-tick bid/ask volume — requires live Level 2 DOM data. NT8's Strategy Analyzer does not replay historical Level 2 data. This is a confirmed hard limitation, not a configuration problem. The only workaround is the Market Replay Recorder (must be enabled in advance; records future live data, cannot reconstruct past).

**Why it happens:**
- Level 2 (DOM) data is streaming-only; no vendor stores full order book state history at millisecond resolution in NT8-compatible format
- NT8 Tick Replay replays `OnMarketData` (trades) but not `OnMarketDepth` (DOM updates)
- Developers assume "tick data = full data" and build backtests that silently skip the DOM-dependent engines

**Consequences:**
- Any "backtest" of DEEP6 without DOM replay is missing E2, E3, E4 signals entirely — the system being backtested is not the system being traded
- P&L attribution per engine is impossible without per-signal ground truth
- ML training on "backtested" signal data is training on incomplete, biased features

**Prevention:**
1. Enable NT8 Market Replay Recorder immediately (Tools > Options > Market Data > Enable market recording for playback) — start recording now so data accumulates
2. Treat Strategy Analyzer results as an approximation of E1+E6+E7 only (footprint + context + ML quality); explicitly exclude E2/E3/E4 from any Strategy Analyzer claim
3. For true DOM backtesting, evaluate third-party solutions: ATAS platform has native historical DOM replay; Deltix/FlexTrade offer institutional-grade full order book replay (expensive: ~$8k/month)
4. Consider a hybrid approach: build a custom NT8 data logger that writes DOM snapshots to disk; replay them via a custom playback harness
5. Accept that the first 3 months of live trading IS the ground truth dataset for DOM-dependent signals

**Warning signs:**
- Strategy Analyzer shows strong E2/E3/E4 contribution to P&L — this is a phantom result
- Backtest results improve when E2/E3/E4 are added — this data is fabricated from tick data, not DOM
- ML model trained on "backtested" DOM signal features shows high training accuracy but poor live performance

**Phase to address:** Backtesting framework design phase — must explicitly document what is and is not testable.

**Severity:** CRITICAL

---

### Pitfall 4: Signal Correlation Masquerading as Independent Confirmation

**What goes wrong:**
The 44-signal taxonomy contains highly correlated signal groups. Absorption classic + stopping volume + effort vs result are three measurements of the same underlying phenomenon (large passive limit orders defending price). The 7-engine voting system requires 4+ engine agreement — but if 6 of 7 engines derive from the same underlying tick data with minor threshold variations, you have 1 real signal dressed as 6. The composite score gives false confidence in signal strength.

**Why it happens:**
- Signals designed from the same data source (bid/ask volume per price level) are naturally correlated
- "Confirmation" in trading systems is often cross-validation of the same measurement, not independent evidence
- The Naïve Bayes combination in E5 explicitly assumes signal independence — violating this assumption inflates the posterior probability estimate

**Consequences:**
- System enters trades with "high confidence" scores that reflect correlation, not true edge
- Adding correlated signals increases complexity without increasing alpha (diminishing returns become negative returns after transaction costs)
- E5's Naïve Bayes probability is systematically overconfident when inputs are correlated

**Prevention:**
1. Compute pairwise signal correlation matrix before finalizing the 44-signal taxonomy — any pair with Pearson r > 0.7 should be collapsed into one signal or one must be dropped
2. Test each signal's independent predictive power with a univariate signal-to-noise ratio before adding to the ensemble
3. For the E5 Naïve Bayes component: either switch to a logistic regression that can model correlation explicitly, or apply a correlation adjustment factor
4. Group the 44 signals by data source (bid/ask volume, DOM depth, CVD, options/GEX) and require at least one signal from each independent source group before triggering a high-confidence alert
5. Track per-signal P&L attribution in live trading; drop signals whose isolated contribution is negative or zero

**Warning signs:**
- Adding signal #40-44 has minimal effect on backtest Sharpe (the information was already captured)
- Absorption classic and stopping volume fire simultaneously on >90% of trade opportunities
- E5 Naïve Bayes confidence regularly exceeds 85% — this is statistically implausible if signals are truly independent

**Phase to address:** 44-signal expansion design phase — correlation analysis before implementation, not after.

**Severity:** CRITICAL

---

### Pitfall 5: Pine Script Execution Model Mismatch in Port to C#

**What goes wrong:**
Pine Script executes once per bar close (by default), with all series values representing the state at that close. The Bookmap Liquidity Mapper Pine Script reference uses `ta.ema()`, `ta.highest()`, `ta.valuewhen()`, and bar-referencing (`[1]`, `[2]`) that all operate on closed-bar series. In NinjaScript, the equivalent code runs on EVERY tick during bar formation. This means:
- A condition that was true at bar close in Pine may be true and then false 40 times during NQ's tick sequence before the bar closes
- `barstate.isconfirmed` in Pine has no direct NinjaScript equivalent — `IsFirstTickOfBar` is not the same as `bar close confirmed`
- Pine's `var` keyword persists a value across bars; NinjaScript field persistence is always-on, but initialization timing differs

**Why it happens:**
- Pine and NinjaScript look syntactically similar (both are C-like signal logic) but have fundamentally different execution models
- Port developers focus on getting conditions to compile, not on verifying they fire at the same logical moment
- Intra-bar signal firing in NT8 can generate phantom entries that would not exist in Pine backtest

**Consequences:**
- Signals fire during bar formation at transient states, creating false entries
- Cooldown logic (e.g., absorption cooldown N bars) counts intra-bar firings as separate events
- Regime detection that was "once per bar" in Pine fires continuously in NT8, causing excessive recalculation

**Prevention:**
1. Document every Pine construct being ported and its NT8 equivalent, with explicit notes on execution timing
2. For all bar-close conditions: wrap in `if (Calculate == Calculate.OnBarClose || IsFirstTickOfBar)` guards
3. For Pine `barstate.isconfirmed` patterns: use `OnBarUpdate` with `Calculate.OnBarClose` mode, not `OnEachTick`
4. For Pine `var` initialization: ensure corresponding NT8 fields are initialized in `OnStateChange(State.DataLoaded)`, not in the class constructor
5. Test each ported signal in isolation on a known historical bar sequence and verify it fires once per bar, not multiple times

**Warning signs:**
- Signal fires 5-10 times per bar in NT8 vs once per bar in Pine backtest
- Cooldown timer expires before bar close, causing multiple entries on the same candle
- Regime state flips back and forth within a single bar

**Phase to address:** Absorption/exhaustion deep system port and 44-signal expansion.

**Severity:** HIGH

---

### Pitfall 6: ATM Entry Slippage Degrading Signal Edge

**What goes wrong:**
Footprint signals (especially exhaustion prints, zero prints, absorption at bid/ask extremes) fire at a specific tick — the signal's value is in entering immediately at that price. NT8 ATM Strategy adds processing overhead: signal detection in indicator → indicator updates state → strategy polls state → order submitted → broker routes → exchange fills. This chain adds latency. On NQ at 1,000 ticks/second in a fast market, 2-3 ticks of slippage on entry is common with market orders. At $5/tick on NQ, that is $10-15 immediate adverse entry per contract before the trade generates any P&L.

**Why it happens:**
- Market orders guarantee fill but not price
- NT8 ATM is not a direct-to-exchange system — it routes through NT8's order management layer
- Signals built for price-at-the-moment translate to entries at best-available-price-after-processing

**Consequences:**
- A signal edge of 3-4 ticks per trade (typical for footprint scalping) is fully consumed by 2-3 tick slippage plus commissions (~1.5 ticks per RT)
- Strategy shows edge in simulation (no slippage) but breaks even or loses live
- High-frequency signals (multiple per session) amplify the slippage cost linearly

**Prevention:**
1. Use limit orders for entries whenever possible: if absorption fires at price X, place a limit at X rather than market — accept non-fill risk for lower slippage
2. Model slippage explicitly in all backtests: assume 1 tick average slippage on entry + 0.5 ticks on exit, and validate the signal still has positive expectancy
3. Track actual slippage in live trading from day one: `actual_fill_price - signal_fire_price` per trade; if average > 1 tick, the entry mechanism needs rethinking
4. For high-urgency signals (zero print, exhaustion), accept market order slippage — these events are rare and high-conviction enough to absorb it; for lower-conviction signals, limit or pass
5. Consider a co-located VPS in Chicago (CME proximity) to reduce network latency from the NT8 machine to the exchange

**Warning signs:**
- Average slippage in the NT8 Performance Reports exceeds 1.0 tick per trade
- Simulated P&L is 40%+ higher than live P&L with identical signals
- Strategy shows positive edge on 5+ tick profit targets but breaks even on 2-3 tick targets (slippage consumed all edge)

**Phase to address:** Auto-execution design phase (P4b) — slippage model must be in the spec before building.

**Severity:** HIGH

---

### Pitfall 7: GEX Data Temporal Mismatch with Per-Tick Signals

**What goes wrong:**
Commercial GEX APIs (SpotGamma, FlashAlpha, InsiderFinance) update GEX levels via REST polling. Free tiers allow 5 requests/day; paid tiers vary but typical implementations update 1-5 times per session, not per-tick. DEEP6's E6 VP+CTX engine uses GEX regime (positive/negative) and GEX levels (call wall, put wall, gamma flip) as context for all 44 signals. But those GEX levels are static snapshots being applied to per-tick signal logic. A GEX level calculated at market open becomes stale as 0DTE options flow changes gamma distribution throughout the session — SpotGamma explicitly notes that their model accounts for intraday 0DTE changes, but the data still isn't per-tick.

**Why it happens:**
- Options OI data updates once daily from exchanges; intraday GEX requires proprietary models and frequent API calls
- Developers treat GEX as a "background context" signal and don't think carefully about when the data is stale
- DEEP6 currently has GEX hardcoded as user-supplied parameters (lines 101-107 in DEEP6.cs) — there is no automated staleness detection

**Consequences:**
- A GEX-driven signal fires "at call wall resistance" but the call wall has shifted 50 points during the session as 0DTE volume rolls
- Regime misclassification: system believes it's in a negative gamma environment (trending) when it has flipped to positive gamma (mean-reverting), inverting the signal interpretation
- False confidence in GEX-based level entries

**Prevention:**
1. Treat GEX as a session-level context signal, not a per-tick signal: refresh GEX data at session open and optionally at lunch reset (12:00 CT), flag levels as "stale" after 2 hours
2. Add a GEX staleness indicator to the DEEP6 header bar — show time since last GEX update alongside the level values
3. Reduce GEX weight in the E6 scoring when data age > 1 hour; zero out GEX contribution after 3 hours
4. Never use GEX proximity as an entry trigger — use it only as a filter (e.g., "do not fade above call wall") rather than a signal source
5. When the GEX API refreshes, re-evaluate all pending signal setups against the new levels before entering

**Warning signs:**
- GEX levels in the system don't change during the trading day (static parameters = definitely stale)
- System enters reversal trades near GEX levels that no longer exist intraday
- P&L degrades after 11 AM ET when GEX drift has accumulated

**Phase to address:** GEX API integration phase (P5a) — staleness handling must be designed in, not retrofitted.

**Severity:** HIGH

---

### Pitfall 8: Monolithic File Collapse Under 44-Signal Expansion

**What goes wrong:**
DEEP6.cs is currently 1,010 lines with 7 engines. The 44-signal expansion adds: ~400 lines for new signal logic, ~200 lines for new engines (E8 CVD, E9 Auction State Machine), ~150 lines for interaction algorithm, ~100 lines for volatility-adaptive thresholds. Projected total: 1,860+ lines in a single file. NinjaScript compiles by loading the entire file into NT8's internal compiler on every save — a 2,000-line file takes 5-8 seconds to compile, breaking the edit-compile-test loop. More critically: with all signal logic interleaved in one class, a bug in absorption logic can corrupt iceberg state through a shared field — debugging becomes archaeology.

**Why it happens:**
- NinjaScript partial classes ARE supported but require careful namespace and folder placement (Indicators folder, same namespace)
- Developers add signals incrementally without a refactoring checkpoint
- NT8's compilation model punishes large single-file indicators non-linearly

**Consequences:**
- A bug in delta trap (signal #28) requires reading 1,800 lines to isolate; fix attempts break absorption (signal #17)
- Compile times slow the development loop to the point where developers stop testing incremental changes
- No unit testability: you cannot instantiate a signal class in isolation to verify its logic

**Prevention:**
1. Adopt partial class decomposition NOW before the 44-signal expansion begins:
   - `DEEP6.Signals.Imbalance.cs` — all 9 imbalance signals
   - `DEEP6.Signals.Delta.cs` — all 11 delta signals
   - `DEEP6.Signals.Absorption.cs` — all 4 absorption signals
   - `DEEP6.Signals.Exhaustion.cs` — all 6 exhaustion signals
   - `DEEP6.Signals.AuctionTheory.cs` — all 5 auction theory signals
   - `DEEP6.Signals.TrappedTraders.cs` — all 5 trapped trader signals
   - `DEEP6.Signals.VolumePatterns.cs` — all 6 volume pattern signals
   - `DEEP6.Signals.POCVA.cs` — all 8 POC/VA signals
   - `DEEP6.Engines.cs` — E8, E9 engines
   - `DEEP6.Rendering.cs` — all SharpDX render code (currently mixed with logic)
2. All partial classes must be in the `Indicators` folder, inside the same namespace (`NinjaTrader.NinjaScript.Indicators`)
3. Each signal class should have a single public method: `SignalResult Evaluate(BarData bar, MarketContext ctx)` — testable in isolation via a mock harness
4. DO NOT create custom base classes for NT8 indicators (confirmed problematic per forum posts)

**Warning signs:**
- DEEP6.cs exceeds 1,200 lines
- Compile time in NT8 exceeds 5 seconds
- A bug fix for one engine requires touching 3+ unrelated areas of the file
- Developer cannot name what lines contain absorption logic without searching

**Phase to address:** Architecture refactoring phase — must precede the 44-signal expansion, not follow it.

**Severity:** HIGH

---

### Pitfall 9: Race Conditions Between DOM and Bar Threads Causing Silent Data Corruption

**What goes wrong:**
NinjaTrader fires `OnMarketDepth` from the instrument thread, but NT8's internal threading model is not fully documented. The existing code (per CONCERNS.md) has `_bV[]`, `_aV[]` arrays written in `OnMarketDepth` and read in `OnBarUpdate` with no synchronization. Adding 44 signals that each maintain state arrays (e.g., running delta per price level, absorption counts per bar, consecutive imbalance counters) across the two event streams multiplies the race condition surface area. Deadlocks are easily created in NT8 when a developer acquires a lock that NT8 is also trying to acquire internally.

**Why it happens:**
- NT8 does not document which internal objects it locks during which events
- NinjaScript appears to handle threading internally for simple indicators; complex shared state breaks this assumption
- Adding `lock()` statements without knowing NT8's lock hierarchy risks deadlock

**Consequences:**
- Signal state reads stale data intermittently — impossible to reproduce or debug
- In fast markets, `_bV[lv]` is written and read concurrently, producing NaN or garbage state
- Kalman filter (E7) state corruption if velocity field is updated mid-computation

**Prevention:**
1. Audit all fields shared between `OnMarketDepth` and `OnBarUpdate` — mark with a comment `// SHARED: accessed from DOM thread and bar thread`
2. For DOM → bar thread data flow: use a single `volatile` snapshot field (not an array) that `OnMarketDepth` writes atomically and `OnBarUpdate` reads — avoid locking entirely
3. For arrays that must be shared: use `Interlocked` operations on scalar values, or accept a one-bar staleness by double-buffering (write to buffer A in DOM thread, swap to buffer B in OnBarUpdate)
4. DO NOT use `lock()` on NT8 internal objects or `lock(this)` — confirmed deadlock risk per NT8 forums
5. Test threading under synthetic load: write a stress test that fires 1,000 `OnMarketDepth` events/second via the NT8 backtester or a mock harness and verify signal state remains consistent

**Warning signs:**
- Occasional NaN in signal scores (not reproducible)
- Signal labels appear one bar late consistently
- NT8 throws `InvalidOperationException` in `OnMarketDepth` during fast markets

**Phase to address:** Architecture refactoring phase (concurrent with partial class decomposition).

**Severity:** HIGH

---

## Moderate Pitfalls

---

### Pitfall 10: ML Curve-Fitting on Regime-Specific Parameters

**What goes wrong:**
The Python ML backend is designed to optimize signal weights, entry/exit timing, and thresholds using trade history. If the training data covers a single market regime (e.g., 2023-2024 low-volatility bull market), the ML model learns regime-specific parameters that catastrophically fail when regime changes (e.g., high-volatility or mean-reverting environment). The ML component cannot distinguish between "absorption is more predictive than imbalance" (structural truth) and "absorption worked better in the specific volatility regime we happened to train on" (regime noise).

**Why it happens:**
- Standard train/test splits don't preserve temporal ordering — future data leaks into training
- Regime changes are non-stationary events that invalidate iid assumptions in ML training
- Hyperparameter optimization (grid search) maximizes IS Sharpe, not OOS stability

**Prevention:**
1. Implement regime-aware training: label each trade with its regime (volatility regime via VIX level, trend vs choppy via ADX) and require balanced training samples across regimes
2. Use purged walk-forward cross-validation that respects time ordering and adds embargo periods between train and test windows to prevent leakage
3. Track the ML model's Walk-Forward Efficiency per regime separately — a model that works in all regimes is more robust than one that works best in only one
4. Add a regime classifier as an independent model that modulates the base ML model's outputs; don't embed regime logic inside the signal weight optimizer

**Warning signs:**
- ML model accuracy degrades 30%+ after a volatility regime shift
- Signal weights recommended by ML concentrate heavily on 1-2 signals during optimization
- Model retraining frequency needs to increase over time (sign of regime-chasing)

**Phase to address:** Python ML backend design phase.

**Severity:** HIGH (demoted from Critical because it's downstream of live signal collection, which provides natural protection)

---

### Pitfall 11: Risk Management Added as an Afterthought

**What goes wrong:**
Auto-execution is built, tested, and works. Risk management (daily loss limits, position sizing, circuit breakers, max drawdown halts) is planned for "later." A sequence of three false absorption signals during a news spike generates three simultaneous losing trades before the first stop fires. Without hard account-level circuit breakers coded into the strategy, an unexpected correlation event (all 44 signals fire in a trending market that immediately reverses) can exceed the acceptable daily loss limit before manual intervention.

**Why it happens:**
- Risk management is unglamorous; developers build the exciting signal logic first
- NT8 has account-level daily loss limits (Account Risk Settings) but these are external to the strategy and have known quirks (daily P&L calculated from 5 PM CT, includes open P&L)
- ATM Strategy's built-in stop is per-trade, not per-session

**Prevention:**
1. Build the following into the auto-execution strategy code from day one:
   - Hard daily loss limit in contract/dollar terms (counted from session open, not 5 PM CT)
   - Max simultaneous open positions (never exceed 1 contract until the system has 60+ live days of positive expectancy)
   - Signal blackout period after N consecutive losses (e.g., stop trading for 30 minutes after 3 consecutive stop-outs)
   - Volatility-based position size scaling (half size when ATR > 2x 20-day average)
2. Test the circuit breaker in simulation: confirm the strategy halts immediately when the daily limit is hit, does not re-enable automatically, and logs the halt with reason
3. Use NT8's account-level Daily Loss Limit as a backstop, not as the primary mechanism — the strategy code should halt itself before the account limit fires

**Warning signs:**
- Strategy documentation lists risk parameters as "TBD" while execution logic is complete
- No per-session trade count limit in strategy code
- Position sizing is hardcoded at 1 contract with no scaling logic

**Phase to address:** Auto-execution phase (P4b) — risk management must be implemented simultaneously with execution, not after.

**Severity:** HIGH

---

## Minor Pitfalls

---

### Pitfall 12: Floating Point Price Comparisons Causing Off-By-One Signal Misses

**What goes wrong:**
NQ tick size is 0.25 points. Price comparisons using `Math.Abs(diff) < TickSize * 0.5` fail due to floating point accumulation when prices are computed as sums of ticks rather than integer multiples. This causes STKt tier boundaries to be missed (confirmed in CONCERNS.md: off-by-one in consecutive imbalance counting).

**Prevention:**
Convert all price-level iteration and comparison to integer tick indices: `int priceIndex = (int)Math.Round(price / TickSize)`. Compare integers, never floating point price values.

**Phase to address:** 44-signal expansion — implement as a utility before adding new signal price logic.

**Severity:** MEDIUM

---

### Pitfall 13: VolumetricBarsType Silent Fallback Invalidating Footprint Signals

**What goes wrong:**
E1 Footprint (the highest-weighted engine at 25 points) silently returns stale state if the chart is not configured with Volumetric Bars. The code catches all exceptions from `GetBidVolumeForPrice()` and `GetAskVolumeForPrice()` silently. A user who loads DEEP6 on a standard candlestick chart gets a "working" system that is missing its core engine with no warning.

**Prevention:**
Add an explicit startup check: if `VolumetricBarsType == null`, display a prominent error in the header bar and set the composite score to 0 until corrected. Never return stale state silently.

**Phase to address:** Can be fixed immediately as a single-method change.

**Severity:** MEDIUM

---

### Pitfall 14: Kalman Filter State Corruption on Gap Opens

**What goes wrong:**
E7's Kalman filter maintains continuous state (`_kSt`, `_kVel`, `_kP`) across bars. A gap open (NQ futures can gap 50-100+ points overnight) produces a measurement that is wildly inconsistent with the filter's current state estimate. The Kalman gain can produce NaN if the innovation covariance becomes singular after an extreme measurement.

**Prevention:**
Add a gap detection check in `OnBarUpdate`: if `Open[0] - Close[1] > N * ATR(20)`, reset the Kalman state to sensible priors (zero velocity, current price as state, high uncertainty covariance). Add an explicit NaN guard on all Kalman gain computations.

**Phase to address:** Next time E7 is touched.

**Severity:** MEDIUM

---

### Pitfall 15: Session Detection Failure on Chart Reload Mid-Session

**What goes wrong:**
`IsFirstBarOfSession` is used to reset Initial Balance and session context. If the chart is loaded mid-session (e.g., NT8 restarted at 10 AM ET), the first bar is not the session open bar. IB detection (`_ibEnd`) is calculated as `_sOpen + IbMins`, where `_sOpen` becomes the mid-session load time — resulting in a fabricated IB range that corrupts all IB-context signals for the rest of the day.

**Prevention:**
Detect chart load time vs actual session open: compare the first bar's time to the expected session open (9:30 AM ET for RTH, 6 PM CT for Globex). If chart loaded mid-session, set a flag `_ibValid = false` and suppress IB-context signals until the next session open.

**Phase to address:** Before auto-execution goes live.

**Severity:** MEDIUM

---

## Phase-Specific Warning Map

| Phase Topic | Specific Pitfall | Mitigation |
|-------------|-----------------|------------|
| 44-signal expansion design | Signal correlation inflating confidence | Compute pairwise correlation matrix first; drop correlated pairs |
| 44-signal expansion design | Pine → C# execution timing mismatch | Document each Pine construct's NT8 equivalent with timing notes |
| Architecture refactoring | NinjaScript partial class gotchas | Stay in Indicators/ folder; same namespace; no custom base classes |
| Architecture refactoring | Race conditions expanding with more shared state | Audit all shared fields first; use volatile snapshot pattern |
| GC / performance | Hot path allocations before adding signals | Fix Std() allocations, brush allocations, RemoveAll() first |
| Backtesting framework | DOM data is not replayable in NT8 Strategy Analyzer | Use Market Replay Recorder; document what is and isn't testable |
| GEX integration | GEX staleness during session | Refresh at session open + once midday; add staleness indicator |
| Auto-execution | ATM slippage consuming signal edge | Model 1 tick slippage in all simulations; use limit entries where possible |
| Auto-execution | No risk management at launch | Build circuit breakers simultaneously with execution logic |
| ML backend | Regime-specific overfitting | Purged walk-forward with regime labels; WFE target > 70% |
| ML backend | Optimizer reinforcing overfit signals | Minimum 200 OOS trades per signal before ML optimization |

---

## Sources

- NinjaTrader Forum: [Level 2 DOM backtesting limitation confirmed](https://forum.ninjatrader.com/forum/historical-beta-archive/version-8-beta/82863-possible-to-backtest-automated-trading-strategies-that-use-level-2-data-in-nt8)
- NinjaTrader Forum: [Slippage on NQ with ATM Strategy](https://forum.ninjatrader.com/forum/ninjatrader-8/platform-technical-support-aa/1329695-slippage-on-nq-with-an-atm-strategy)
- NinjaTrader Forum: [Race condition / deadlock threading patterns](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/104601-common-deadlock-scenario)
- NinjaTrader Forum: [Partial class compilation in NinjaScript](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1042291-partial-class-compiling-issue-for-indicator)
- NinjaTrader Forum: [Circuit breakers and daily loss limits](https://forum.ninjatrader.com/forum/ninjatrader-8/platform-technical-support-aa/1090660-how-circuit-breakers-work)
- NinjaTrader Docs: [Performance tips for indicators](https://ninjatrader.com/support/helpGuides/nt8/performance_tips2.htm)
- Academic: [Interpretable Hypothesis-Driven Trading: Walk-Forward Validation Framework (Dec 2025)](https://arxiv.org/html/2512.12924v1)
- Academic: [Backtest overfitting in the machine learning era (ScienceDirect 2024)](https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110)
- QuantInsti: [Walk-Forward Optimization — WFE methodology](https://blog.quantinsti.com/walk-forward-optimization-introduction/)
- Build Alpha: [Robustness testing and out-of-sample validation](https://www.buildalpha.com/robustness-testing-guide/)
- Bookmap Learning: [Absorption and Exhaustion signal false positives](https://bookmap.com/learning-center/en/supply-demand-setups/supply-demand-setups/absorption-exhaustion)
- PineScript → NinjaScript conversion pitfalls: [Trading Strategies Academy](https://trading-strategies.academy/archives/4174), [PineScript Programming Blog (Aug 2024)](https://pinescriptprogramming.blogspot.com/2024/08/converting-pine-script-to-ninjascript.html)
- Optimus Futures: [Slippage in NQ — market vs limit orders](https://learn.optimusfutures.com/price-impact-analysis)
- FlashAlpha: [GEX API documentation](https://flashalpha.com/docs/lab-api-gex)
- SpotGamma: [GEX methodology and 0DTE coverage](https://spotgamma.com/gamma-exposure-gex/)
