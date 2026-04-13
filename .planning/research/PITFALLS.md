# Domain Pitfalls: DEEP6 v2 Python Footprint Trading System

**Domain:** Python real-time footprint auto-trading — 1,000 DOM callbacks/sec, async-rithmic, Kronos inference, direct Rithmic execution
**Researched:** 2026-04-11
**Confidence:** HIGH on Python runtime behavior (official docs + community patterns); MEDIUM on async-rithmic specifics (community library, limited production reports); MEDIUM on Databento MBO live/historical parity (official docs confirm design intent, artifacts unconfirmed); LOW on Kronos CPU inference latency (only one source, A100 extrapolation)

---

## Critical Pitfalls

These mistakes cause silent data corruption, blown accounts, or systems that appear correct in testing but fail live.

---

### Pitfall 1: asyncio Event Loop Blocked by CPU-Bound Signal Computation

**What goes wrong:**
asyncio is single-threaded cooperative multitasking. If any coroutine or callback performs CPU-bound work without yielding — signal scoring, footprint bar finalization, Kronos inference, XGBoost prediction — the entire event loop freezes. At 1,000 DOM callbacks/second, a 5ms blocking operation creates a 5-tick backlog. At 10ms it snowballs. The event loop does not "catch up" after a block; it drops callbacks from the WebSocket buffer or processes them stale.

**Why it happens:**
- Developers see `async def on_dom_update(update)` and assume it runs safely in the event loop regardless of what's inside it
- NumPy operations (footprint accumulation, rolling statistics for CVD, Kalman filter update) look fast but are CPU-bound
- Signal scoring over 44 signals, each computing rolling windows or imbalance ratios, easily crosses 1ms per bar close
- Kronos inference called synchronously on bar close blocks for 500ms–2s on CPU (see Pitfall 4)
- Python's `asyncio` docs state explicitly: "Never call a CPU-intensive function from a coroutine directly" — the callback duration before yielding determines event loop responsiveness

**Consequences:**
- DOM state becomes stale while the loop is blocked — a 10ms gap at 1,000 callbacks/sec means 10 missed DOM updates
- Footprint bars built from stale DOM state have wrong bid/ask volumes at affected price levels
- Signal state computed after the block reflects past market conditions, not present
- The system appears to work fine in slow markets; degrades precisely when NQ is moving fastest

**Prevention:**
1. Establish a 100-microsecond budget for any code running directly in the asyncio event loop hot path — DOM callbacks, tick accumulation, DOM state updates. Nothing else belongs there.
2. For all CPU-bound operations (signal scoring, bar finalization, Kronos inference, XGBoost): use `loop.run_in_executor(ProcessPoolExecutor(...), fn, args)`. ProcessPoolExecutor bypasses the GIL by spawning separate OS processes.
3. Architecture: split into two processes from the start — **Process A** (asyncio event loop: receives DOM + ticks, maintains book state, accumulates footprint bar) and **Process B** (CPU workers: compute signals, run Kronos, score confluence). Use a `multiprocessing.Queue` or shared memory to hand off completed bars.
4. Profile the event loop lag on day one: instrument the loop with a periodic timestamp comparison. If lag exceeds 500 microseconds consistently, the hot path has a CPU leak.
5. Do NOT use `ThreadPoolExecutor` as the escape hatch for CPU-bound computation — threads share the GIL and provide no true parallelism for Python CPU work. Use `ProcessPoolExecutor` for CPU, `ThreadPoolExecutor` only for blocking I/O (database writes, HTTP requests).

**Warning signs:**
- `asyncio.get_event_loop().slow_callback_duration` warnings appearing (default threshold: 100ms)
- DOM update timestamps show gaps > 5ms during normal market hours
- Footprint bars show identical bid/ask volumes for multiple consecutive price levels (sign of stale accumulation)
- Increasing event loop lag correlates with bar close timing

**Phase to address:** Data pipeline design (Phase 1) — the process boundary must be in the architecture from day one, not retrofitted.

**Severity:** CRITICAL

---

### Pitfall 2: Footprint Tick Classification Accuracy — Inferred vs Exchange-Reported Aggressor Side

**What goes wrong:**
Building a footprint chart requires knowing whether each trade was buy-initiated (hit the ask) or sell-initiated (hit the bid). Python implementations typically infer this using the "tick rule" or "last-vs-bid/ask" comparison. This inference is wrong in certain known scenarios, producing incorrect bid/ask volume splits in the footprint bars that all 44 signals depend on.

**The specific gap:**
NinjaTrader's `VolumetricBarsType` (which v1 DEEP6 relied on) uses Rithmic's actual exchange-reported aggressor flags from CME MDP 3.0 — where CME publishes `AggressorSide` = 1 (buy) or 2 (sell) per trade. This is the ground truth. A Python system using inferred tick classification will diverge from NT8's footprint in these cases:

1. **Implied orders:** CME Globex generates implied bids/offers from spread combinations — these trades have no aggressor flag. Classification algorithms must guess, and they guess wrong for approximately 5–15% of trades in liquid months.
2. **Pre-open / auction trades:** Any trade occurring at market open, after a trading halt, or during pre-open has no aggressor indicator from CME. The tick rule assigns direction based on the previous trade — which was itself in a different session state.
3. **Simultaneous fills at the same price:** When multiple orders fill at the same price level in the same microsecond, the tick rule assigns them all to the same side even if they were split.
4. **Price tie at bid = ask:** This occurs rarely but produces ambiguous classification.

**Why it matters for DEEP6:**
- Absorption signals require knowing that passive limit orders defended a price level — this depends on accurate bid-side vs ask-side volume at each tick
- Delta calculations (CVD, per-bar delta, delta divergence) accumulate classification errors across every bar
- The `footprint-system` reference implementation (FutTrader/Sierra Chart C++) notes this explicitly: it relies on Sierra's classified data, not inferred ticks

**What async-rithmic provides:**
Rithmic's TICKER_PLANT does transmit aggressor side flags in the tick stream — this is part of the Rithmic Protocol Buffer spec. Whether async-rithmic exposes this field in its callback data structure needs verification against the actual library source code. If it does, use it. If it does not surface the flag, the library is doing inferred classification internally and the problem is hidden.

**Prevention:**
1. Before building the footprint engine, inspect async-rithmic's `on_trade` callback data structure — confirm whether `aggressor_side` or equivalent field is present with values (BUY/SELL vs UNKNOWN)
2. If the flag is present: use it directly; classify UNKNOWN trades using last-vs-bid comparison as fallback only
3. If the flag is absent: file an issue or PR on the async-rithmic repository; use `UpDownTick` fallback in the interim and document that footprint accuracy is degraded
4. Databento MBO data **does** include the actual CME aggressor flag per trade — for backtesting via Databento MBO replay, accuracy will be higher than live if async-rithmic does inferred classification
5. Track a "classification confidence" metric: percentage of ticks where aggressor side was from exchange flag vs inferred. If this is below 85%, footprint accuracy is materially degraded.

**Warning signs:**
- Live footprint bars show different bid/ask ratios than the same bars in Bookmap (which uses exchange flags)
- Absorption signals fire on bars where Bookmap shows no absorption
- Delta divergence signals appear on bars where CVD direction matches price direction (should be divergent)

**Phase to address:** Data pipeline design, before the footprint engine is built.

**Severity:** CRITICAL

---

### Pitfall 3: Python GC Pauses Corrupting DOM State During High-Frequency Updates

**What goes wrong:**
CPython's garbage collector uses reference counting plus a cyclic GC pass. The cyclic GC can trigger a "stop-the-world" pause where all threads and the asyncio event loop freeze. At 1,000 DOM callbacks/sec, a GC pause of even 2-5ms means the WebSocket read buffer fills, messages are queued, and when the event loop resumes it processes a burst of stale DOM updates — giving the DOM state engine a false view of book depth that persists until the next full update cycle.

**The DOM-specific problem:**
The 40-level DOM state is an 80-price-level structure (bid + ask) updated continuously. If each DOM callback creates new Python objects (dicts, dataclass instances, Decimal values), the allocation rate at 1,000 callbacks/sec creates GC pressure. Common patterns that cause this:

- `dom_level = {'price': update.price, 'size': update.size, 'side': update.side}` — creates a new dict per callback
- `Decimal(str(update.price))` — allocation on every price value
- `asyncio.Queue.put(update)` when the queue consumer is slow — unbounded queue growth forces GC
- `defaultdict(lambda: {'bid_vol': 0, 'ask_vol': 0})` footprint accumulator — a new dict per new price level per bar

**Consequences:**
- GC pauses of 5-50ms appear unpredictably, correlated with high-volume markets (exactly when DOM accuracy matters most)
- DOM state shows price levels with incorrect sizes in the snapshot after a GC event
- Footprint accumulator has duplicate price entries if a GC pause interrupted mid-update

**Prevention:**
1. Pre-allocate the DOM state as a fixed NumPy structured array at startup: `dom_bids = np.zeros(40, dtype=[('price', 'f8'), ('size', 'i4')])` — update in-place, zero allocations per callback
2. Pre-allocate the footprint accumulator for the expected price range: `footprint = np.zeros(200, dtype=[('bid_vol', 'i4'), ('ask_vol', 'i4')])` indexed by `int(price / tick_size)` — array lookup, not dict
3. Disable the cyclic GC during market hours and run it manually at session breaks: `gc.disable()` at session open, `gc.collect()` at lunch and session close
4. Set GC thresholds for performance-critical contexts: `gc.set_threshold(100000, 100, 10)` to delay Gen0 collection
5. Use `__slots__` on any dataclasses or objects in the hot path — prevents per-instance `__dict__` allocation
6. Monitor allocation rate with `tracemalloc` during development; target: < 1KB/sec allocation in the DOM event loop

**Warning signs:**
- DOM state occasionally shows price levels with size=0 that were nonzero moments before
- `gc.get_count()` shows Gen1/Gen2 collection counts rising during trading hours
- Footprint bars show suspicious identical volumes at adjacent price levels (indicative of stale state applied twice)

**Phase to address:** Data pipeline design — the data structures must be designed allocation-free from the start.

**Severity:** CRITICAL

---

### Pitfall 4: Kronos Inference Blocking the Event Loop or Exceeding Bar Duration

**What goes wrong:**
Kronos-small (24.7M parameters) runs inference in approximately 500ms-1s on CPU (10-20x slower than the reported ~50ms on A100 GPU). If inference is called synchronously at bar close and the system is running on CPU, the next bar's DOM accumulation is blocked during inference. On a 1-minute bar: 60 seconds of accumulation time, 1 second of inference — manageable. On a 15-second bar or a volume bar: inference could exceed bar duration, causing the system to skip a Kronos prediction entirely.

**The cascading problem:**
If Kronos inference is dispatched to `ProcessPoolExecutor`, each call requires pickling the input tensor (OHLCV sequence data), sending it to the worker process, running inference, pickling the result, and returning it. For a 24.7M parameter model loaded in a worker process, the first call incurs model loading time (several seconds). Subsequent calls are faster but still include inter-process serialization overhead.

**Specific numbers (MEDIUM confidence):**
- Kronos-base (102.3M params) on A100: ~50ms
- Kronos-small (24.7M params) on A100: estimated ~15ms (extrapolated, unconfirmed)
- Kronos on CPU (any size): 10-20x slower → Kronos-small on CPU = 150ms–300ms estimated
- ProcessPoolExecutor IPC overhead: 1-5ms per call for small tensors; scales with tensor size
- Model load time in worker process: 2-10 seconds per worker (one-time cost at startup)

**Prevention:**
1. If using CPU inference: run Kronos in a dedicated persistent `multiprocessing.Process` (not a pool) that loads the model once at startup, then receives inference requests via `multiprocessing.Queue`. Eliminates per-call model loading overhead.
2. Measure CPU inference time on the target hardware before committing to the bar type — if inference on CPU exceeds 1/3 of bar duration, either: (a) use a longer bar type, (b) use GPU, or (c) use Kronos-mini (4.1M params, lower latency but less accuracy)
3. Design Kronos to produce a prediction that remains valid for N bars — Kronos bias (E10) is a directional context signal, not a per-tick signal. A prediction from bar T is still valid at bar T+2 or T+3. Do not require new Kronos inference on every bar.
4. Never call Kronos inference synchronously in the asyncio event loop — always dispatch to ProcessPoolExecutor or a dedicated inference process
5. GPU is strongly recommended for production: an RTX 3060 provides ~15ms inference on Kronos-small — well within any bar duration. CPU is acceptable only for development/testing.

**Warning signs:**
- Kronos predictions appear in system logs with timestamps 500ms+ after bar close
- Event loop lag spikes correlate with bar close events (sign of synchronous inference)
- System silently skips Kronos prediction on some bars because the previous inference hasn't returned yet

**Phase to address:** Kronos integration phase — inference architecture must be decided before integration begins.

**Severity:** CRITICAL (CPU-only deployment) / HIGH (GPU deployment)

---

### Pitfall 5: async-rithmic Reconnection During Open Position — Position State Desync

**What goes wrong:**
async-rithmic uses separate WebSocket connections per "plant" (TICKER_PLANT for data, ORDER_PLANT for execution). A network interruption disconnects both simultaneously. The library has automatic reconnection with exponential backoff — but during the reconnection window (potentially 5-30 seconds), the ORDER_PLANT has no visibility into fills, partial fills, or stop executions that occurred at the exchange during the gap.

**The specific failure:**
The system has an open long position. The WebSocket drops at 14:23:05. The exchange fills a stop order at 14:23:07. async-rithmic reconnects at 14:23:18. The reconnection restores subscriptions but does NOT automatically replay missed order events — there is no sequence number recovery mechanism confirmed in the library. The system's internal position tracker still shows LONG. The system may re-enter the position or fail to update risk controls.

**Known async-rithmic issue:**
GitHub Issue #49 (opened March 2026): "ForcedLogout reconnection loop when connecting multiple plants simultaneously" — confirmed production bug where connecting TICKER_PLANT and ORDER_PLANT concurrently causes authentication failures and a reconnection loop. This means the recommended approach of lazy sequential plant connection is required, adding latency to reconnection.

**Prevention:**
1. On every reconnection of ORDER_PLANT, immediately query the current position state from Rithmic before resuming any trading logic: use Rithmic's `RequestAccountList` + `RequestPnL` or equivalent to get the authoritative position
2. Implement a "reconnection freeze" state: when the WebSocket drops, set `TRADING_FROZEN = True`. After reconnection + position sync completes, resume with TRADING_FROZEN = False. During frozen state: no new entries, no signal processing
3. For the ForcedLogout issue: connect plants sequentially with a 500ms delay between TICKER_PLANT and ORDER_PLANT connections — do not connect them simultaneously
4. Implement an order state machine with explicit PENDING, SUBMITTED, PARTIAL_FILL, FILLED, CANCELLED states — never infer position from signal state
5. Log every reconnection event with position state before and after — this is the audit trail for any account disputes
6. Test disconnection handling explicitly in the paper trading environment: kill the network interface mid-position and verify the system freezes, reconnects, syncs, and resumes correctly

**Warning signs:**
- System logs show duplicate order submissions after reconnection
- Position tracker shows FLAT when account actually holds a position (or vice versa)
- async-rithmic logs show repeated login attempts after a single disconnect event

**Phase to address:** Execution engine design — reconnection handling must be designed before the execution phase, not added after.

**Severity:** CRITICAL

---

### Pitfall 6: Signal Correlation Masquerading as Independent Confirmation (CARRY-FORWARD)

**What goes wrong:**
(Identical to v1 Pitfall 4 — this pitfall fully carries forward to the Python implementation.)

44 signals built from the same underlying data (bid/ask volume per price level) are naturally correlated. Absorption classic + stopping volume + effort vs result are measuring the same phenomenon. The two-layer consensus scoring system can give false high confidence when correlated signals fire together, because it assumes independence.

**Python-specific addition:**
The Python ML backend (XGBoost + Optuna) will actively discover and exploit correlations in the training data — the optimizer will find that weighting correlated signals together gives better backtest Sharpe (because they amplify the same true signal), but this is an overfitting vector. The ML layer can turn a moderate correlation problem into a severe one.

**Prevention:**
Same as v1: compute pairwise Pearson correlation matrix before finalizing signal taxonomy. Any pair with r > 0.7 must be collapsed or one dropped. Additionally: regularize XGBoost with L1 penalty to force sparse signal weighting; do not allow the ML optimizer to increase any single signal's weight above 3x its baseline without manual review.

**Phase to address:** Signal engine design phase (before implementation of the 44-signal taxonomy in Python).

**Severity:** CRITICAL

---

### Pitfall 7: 44-Signal Overfitting Without Walk-Forward Validation (CARRY-FORWARD)

**What goes wrong:**
(Identical to v1 Pitfall 1 — fully carries forward.)

44 signals × N parameters each = thousands of degrees of freedom optimized against NQ history. Without purged walk-forward cross-validation, the backtest is a measure of in-sample fit, not out-of-sample edge.

**Python-specific addition:**
Databento MBO historical data enables a much more comprehensive backtest than NT8 Market Replay could. This is a double-edged sword: more data to overfit against. The Optuna hyperparameter optimizer will find configurations that exploit noise in 2+ years of NQ data if the validation framework is not rigorous.

**Prevention:**
Same as v1: walk-forward validation with 6-month train / 2-month test windows, WFE > 70% target, 200 minimum OOS trades per signal. Additional Python requirement: use `combinatorial purged cross-validation (CPCV)` via the `mlfinlab` library for the XGBoost components specifically.

**Phase to address:** ML backend design phase.

**Severity:** CRITICAL

---

## High Severity Pitfalls

---

### Pitfall 8: Databento MBO Live vs Historical Replay — Known Structural Difference

**What goes wrong:**
Databento's design intent is identical schemas for historical and live data. However, one confirmed structural difference exists: **all MBO subscriptions for a dataset must be made at node startup** to replay data from the beginning of the session. If a subscription arrives after node start, Databento logs an error and ignores it. This means a mid-session crash and reconnect produces an MBO stream starting from the snapshot minute, not from session open — creating a gap in the historical record and a live/backtest divergence in the first hour of reconstructed signal state.

**Specific scenario:**
Session open: 8:30 AM CT. System runs from session open, MBO streaming from session start — full book state. System crashes at 9:15 AM. Restart at 9:20 AM. MBO snapshot provides book state as of ~9:19 AM. Signal engines that depend on session-open context (Initial Balance, VWAP from open, CVD from 8:30 AM) start with incorrect baselines. The backtest always has full session data; live has the gap.

**Prevention:**
1. Design all session-context signals to work from a "session start anchor" that is explicitly stored to disk at session open — if the system restarts mid-session, read the stored anchor rather than treating the restart time as session open
2. Implement session state persistence: write IB range, opening range, session VWAP, and CVD baseline to a local file every minute. On reconnect, load from file rather than reinitializing to zero
3. Test mid-session restart explicitly: kill the process at 30 minutes into a paper trading session and verify signal state is restored correctly from disk
4. Document the divergence in backtesting framework: historical MBO replay always has full session data from 8:30 AM; live may have a reconnect gap. This means backtest P&L for session-context signals (IB signals, VWAP signals) is optimistic compared to live.

**Warning signs:**
- CVD shows 0 at session start after a mid-session restart
- Initial Balance range is incorrectly calculated as the 30-minute range from restart time
- VWAP diverges from TradingView's VWAP after a restart

**Phase to address:** Data pipeline design and backtesting framework design.

**Severity:** HIGH

---

### Pitfall 9: Direct Order Execution Without NinjaTrader's Safety Layer — Position Risk Exposure

**What goes wrong:**
NT8's ATM Strategy provided: per-trade stop loss, per-trade target, a UI to manually flatten, account-level daily loss limits from the broker, and a clear visual of open positions. Direct Rithmic execution via async-rithmic has none of this. The system must implement every safety layer explicitly.

**The critical gap on connection loss with open position:**
If the ORDER_PLANT WebSocket drops while a trade is open, the server-side Rithmic stop/target orders remain active (Rithmic has server-side OCO/bracket support). But the Python system's position tracker loses visibility. The danger is the system re-entering the market (opening a new position) because it believes no position exists, while the server-side stop is still managing the original position — resulting in doubled exposure.

**Prevention:**
1. Use Rithmic's **server-side bracket orders** from the moment of entry: submit entry + stop + target as a linked bracket. The bracket persists at Rithmic's servers independent of the Python client's connection state.
2. Maintain a position state file on disk that is updated on every fill event. On reconnection, read from disk AND query Rithmic's position API — reconcile discrepancies before allowing any new entries
3. Implement a "no new entries" lockout that persists for 5 seconds after any reconnection event, giving time for position sync to complete
4. Build the circuit breakers before testing any live capital: daily loss limit (tracked from session open), max 1 open position at any time, consecutive-loss cooldown (3 losses → 30-minute halt)
5. Paper trade for a minimum of 30 days before any live capital, specifically testing: mid-trade disconnect, partial fill scenarios, and back-to-back signal firing

**Warning signs:**
- System code has `if open_position:` checks without a corresponding persistence layer
- Circuit breakers are listed as "TODO" while execution code is written
- No test coverage for the reconnect-during-open-position scenario

**Phase to address:** Execution engine design — must be designed before any live trading attempt.

**Severity:** HIGH

---

### Pitfall 10: asyncio WebSocket Heartbeat Failure Causing Silent Stale Data

**What goes wrong:**
Long-running WebSocket connections can enter a "zombie" state where the connection appears open (no TCP disconnect) but no data is flowing — typically because a NAT/firewall timeout silently dropped the connection at the network layer. Without heartbeat/ping-pong, the asyncio WebSocket client believes the connection is active and continues processing a stale DOM state that stopped updating 60+ seconds ago. The system generates signals from data that is minutes old with no indication of the staleness.

**async-rithmic specifics:**
The library implements heartbeats per plant connection. However, the documented behavior on heartbeat timeout is not explicitly described in public documentation. Whether a heartbeat failure triggers automatic reconnection or merely logs an error needs to be verified in the source code before production deployment.

**Prevention:**
1. Implement a "last update" timestamp on the DOM state: if `time.monotonic() - last_dom_update > 5.0`, emit a WARNING and freeze trading
2. Implement a "data watchdog": a separate asyncio task that fires every 2 seconds, checks the last DOM update timestamp, and triggers an alarm if staleness exceeds threshold
3. Verify async-rithmic's heartbeat failure behavior in the test environment: simulate a zombie connection (block traffic at OS level while keeping TCP alive) and confirm the library detects it and reconnects
4. Add application-level heartbeat: send a ping to Rithmic every 10 seconds and verify a response arrives within 2 seconds; if not, force reconnect

**Warning signs:**
- DOM update timestamps frozen while price is moving (visible in TradingView but not updating in system)
- Signal engine producing the same output repeatedly for 30+ seconds in a volatile market
- Heartbeat logs show successful sends but no corresponding receive confirmations

**Phase to address:** Data pipeline design.

**Severity:** HIGH

---

### Pitfall 11: Risk Management Added as an Afterthought (CARRY-FORWARD)

**What goes wrong:**
(Same as v1 Pitfall 11 — fully carries forward with Python-specific additions.)

Direct Rithmic execution without NT8's built-in safety mechanisms means DEEP6 must be its own risk manager. The temptation is to build execution first, risk later.

**Python-specific addition:**
Python's asyncio architecture makes it easy to accidentally allow concurrent signal processing that submits multiple orders simultaneously. With a single-threaded NT8 model, concurrent entries were impossible. With async Python: two coroutines can both pass the `if open_position == False:` check before either has submitted an order, resulting in two simultaneous entries.

**Prevention:**
Use an `asyncio.Lock()` to guard the entry logic — only one coroutine can hold the "consider entry" section at a time. Build circuit breakers (daily loss limit, consecutive-loss cooldown, volatility halt) simultaneously with execution logic, not after.

**Phase to address:** Execution engine design.

**Severity:** HIGH

---

### Pitfall 12: free-threaded CPython 3.13+ Ecosystem Immaturity

**What goes wrong:**
Python 3.13 introduced optional GIL removal (free-threaded build). This appears to solve the GIL problem for trading. However, as of 2026, the free-threaded build has known issues: asyncio was only made properly thread-safe for multiple event loops in Python 3.14; the broader ecosystem (NumPy, pandas, asyncio libraries) has patchy free-threading support. Using the free-threaded build in production introduces new instability without eliminating the need for careful process isolation.

**The trap:**
A developer reads "GIL is now optional" and switches to the free-threaded CPython 3.13 build assuming threading replaces the need for multiprocessing. But NumPy's thread safety in free-threaded mode is not fully guaranteed for all operations; asyncio in 3.13 specifically is not production-ready for free-threading; and C extension libraries may not be reentrant.

**Prevention:**
1. Stick with the standard (GIL-enabled) CPython 3.12 build for the initial production system
2. Use `ProcessPoolExecutor` (multiprocessing) for CPU isolation — this is mature, well-understood, and correct
3. Evaluate free-threading when Python 3.15 is released (likely late 2026) and the ecosystem has stabilized
4. Never assume "free threading" eliminates the architectural need to isolate DOM event loop from CPU-bound computation

**Phase to address:** Stack selection, architecture design.

**Severity:** HIGH

---

## Moderate Pitfalls

---

### Pitfall 13: ProcessPoolExecutor Pickling Overhead for Per-Bar Signal Data

**What goes wrong:**
Dispatching CPU-bound work to `ProcessPoolExecutor` requires pickling all arguments for inter-process communication. A completed footprint bar has price levels (80), per-level bid/ask volumes, tick counts, OHLCV values, and 40-level DOM snapshots. Pickling this per-bar object, transmitting it to the worker process, running 44 signal computations, pickling results back — the IPC round-trip can add 2-5ms per bar.

For a 1-minute bar, this is trivial. For a 15-second bar during high-volume sessions, 5ms of IPC overhead is a material fraction of the bar duration.

**Prevention:**
1. Use `multiprocessing.shared_memory` (Python 3.8+) for the DOM state and footprint bar — the worker process reads directly from shared memory without pickling, reducing IPC to near-zero overhead for read-only data
2. Pre-define a fixed binary layout for the bar object (using `ctypes.Structure` or NumPy structured arrays) that maps directly to shared memory — no serialization needed
3. If `shared_memory` is too complex: minimize what is pickled — send only the bar index and timestamps, have the worker process read bar data from a shared NumPy array (mapped via `mmap`)

**Phase to address:** Data pipeline and signal engine design.

**Severity:** MEDIUM

---

### Pitfall 14: Floating Point Price Level Indexing Errors in Python

**What goes wrong:**
(Analogous to v1 Pitfall 12 — fully carries forward to Python.)

NQ tick size is 0.25 points. Floating point arithmetic on price values introduces accumulation errors: `18500.25 + 0.25 == 18500.50` may evaluate as `18500.499999999998` in IEEE 754. Price level lookups in the footprint accumulator `dom_array[price / 0.25]` then miss the correct bucket, creating ghost price levels adjacent to the correct ones.

**Prevention:**
Convert all prices to integer tick indices immediately on receipt: `tick_idx = round(price / tick_size)`. All internal data structures keyed by price use `int` tick indices. Reconstruct float price only for display: `display_price = tick_idx * tick_size`. Never compare float prices directly — always compare tick indices.

**Phase to address:** Data pipeline design — must be in the footprint accumulator from line 1.

**Severity:** MEDIUM

---

### Pitfall 15: vectorbt Backtesting Cannot Replay DOM State

**What goes wrong:**
(Analogous to v1 Pitfall 3 for NT8 — now the Python equivalent.)

vectorbt is a vectorized backtesting engine — it operates on OHLCV-level data. DOM-dependent signals (E2 trespass, iceberg, absorption using per-tick bid/ask volume) cannot be meaningfully vectorized. Using vectorbt to backtest the full 44-signal system produces a result where DOM-dependent signals are either absent or approximated from OHLCV data, while appearing to be properly tested.

**The Databento MBO solution:**
Databento MBO historical replay is the correct backtesting approach for DOM signals — it replays individual order events with nanosecond timestamps, enabling true tick-level reconstruction. But MBO replay is a sequential event-driven loop, not a vectorized operation. You cannot pass MBO replay into vectorbt's `Portfolio.from_signals()` directly.

**The hybrid approach:**
1. Use Databento MBO replay (event-driven Python loop) to generate ground truth signal labels on historical data: for each bar, record which of the 44 signals fired and the outcome
2. Store these labeled signal records as a DataFrame
3. Use vectorbt `Portfolio.from_signals()` on the labeled DataFrame to simulate portfolio P&L, slippage, commissions — this is vectorbt's strength
4. The event-driven replay step is the bottleneck: a full day of NQ MBO data at 2024 volume levels can produce 2M+ events; replay at full fidelity takes minutes per day of history

**Prevention:**
Treat vectorbt as a portfolio simulation tool, not a signal backtesting tool. Build a separate Databento MBO replay engine for signal generation. Never let vectorbt touch the signal logic directly.

**Phase to address:** Backtesting framework design.

**Severity:** MEDIUM

---

### Pitfall 16: GEX Data Temporal Mismatch (CARRY-FORWARD)

**What goes wrong:**
(Identical to v1 Pitfall 7 — fully carries forward.)

FlashAlpha GEX data updates on REST polling, not per-tick. GEX levels stale after market open are applied to per-tick signal logic, causing regime misclassification and false level entries.

**Prevention (same as v1):**
Treat GEX as session-level context only. Refresh at session open + lunch reset. Add staleness indicator. Reduce GEX weight when data age > 1 hour; zero out after 3 hours. Never use GEX proximity as an entry trigger.

**Phase to address:** GEX integration phase.

**Severity:** HIGH (demoted to Moderate in this document since the fix is well-understood from v1)

---

### Pitfall 17: ML Regime Overfitting (CARRY-FORWARD)

**What goes wrong:**
(Identical to v1 Pitfall 10 — fully carries forward.)

XGBoost trained on a single market regime learns regime-specific patterns that fail when the regime changes. Optuna maximizes IS Sharpe, not OOS stability.

**Prevention (same as v1):**
Regime-aware training (label each trade with VIX level / trend regime). Purged walk-forward cross-validation with embargo periods. Track WFE per regime separately. Add regime classifier as an independent model.

**Phase to address:** ML backend design.

**Severity:** HIGH (demoted to Moderate in this document since the fix is well-understood from v1)

---

## Minor Pitfalls

---

### Pitfall 18: Prop Firm Environment WebSocket URL Differences

**What goes wrong:**
async-rithmic GitHub Issue #50 (April 2026) and #42 (January 2026) reveal that prop firm accounts (Apex, Topstep, etc.) use different Rithmic WebSocket URLs than direct broker accounts. The library does not ship with a comprehensive list of prop firm endpoints. A developer testing on a demo account and then switching to a funded prop firm account will face connection failures with cryptic error messages.

**Prevention:**
Confirm the correct WebSocket URI for your specific broker/prop firm before any live trading attempt. Test connectivity explicitly in the paper trading environment. If using Apex or similar, check their specific Rithmic endpoint documentation.

**Phase to address:** Data pipeline setup (Phase 1).

**Severity:** LOW

---

### Pitfall 19: Session Detection Failure on Mid-Session Process Restart (CARRY-FORWARD)

**What goes wrong:**
(Analogous to v1 Pitfall 15, now in Python context.)

If the Python process restarts mid-session, Initial Balance and session context signals will compute from restart time as their baseline. CVD from session open is lost. VWAP from 8:30 AM CT is lost. IB range computed from 9:20 AM instead of 8:30 AM is wrong.

**Prevention:**
Write session anchor data (IB range, session open price, CVD baseline, VWAP anchor) to a local SQLite or pickle file every minute. On process startup: check if a valid session anchor file exists for today's date; if yes, load it instead of reinitializing from zero.

**Phase to address:** Data pipeline design.

**Severity:** MEDIUM

---

### Pitfall 20: async-rithmic Library Maturity Ceiling

**What goes wrong:**
async-rithmic (version 1.5.9 as of April 2026) is a community library with one primary maintainer (rundef). It has 4 open GitHub issues, one of which (Issue #49) is a production reconnection bug opened March 2026. There is no SLA, no commercial support, and no official Rithmic endorsement. If the maintainer stops maintaining the library or Rithmic protocol version advances, DEEP6 loses its entire data and execution infrastructure.

**Prevention:**
1. Pin to a specific async-rithmic version in `pyproject.toml` — do not auto-upgrade. Test each new version explicitly before upgrading in production
2. Maintain a local fork of async-rithmic with DEEP6-specific patches. If the library goes unmaintained, the fork becomes the source of truth
3. Evaluate the Rust alternative (`rithmic-rs`, `ff_rithmic_api`) as a potential fallback if the Python library has reliability issues — Rust implementations exist and could be wrapped via PyO3
4. Keep the Rithmic R|Protocol Buffer spec documentation locally — if async-rithmic fails, you can fall back to raw WebSocket + protobuf implementation

**Phase to address:** Architecture design. Risk to be acknowledged explicitly before production deployment.

**Severity:** MEDIUM

---

## Phase-Specific Warning Map

| Phase Topic | Specific Pitfall | Mitigation |
|-------------|-----------------|------------|
| Data pipeline design | asyncio event loop blocked by CPU work | Establish 100µs budget; ProcessPoolExecutor for everything else |
| Data pipeline design | DOM state allocation causing GC pauses | Pre-allocate NumPy arrays; disable GC during trading hours |
| Data pipeline design | WebSocket zombie connection (silent stale) | Data watchdog task; last-update timestamp monitoring |
| Footprint engine | Tick classification accuracy | Verify async-rithmic aggressor flag field; use Databento MBO flags for backtesting |
| Footprint engine | Float price comparison errors | Integer tick indices from day one; never compare float prices |
| Execution engine | Reconnection during open position | Server-side bracket orders; position persistence; reconnection freeze |
| Execution engine | Concurrent asyncio entries | asyncio.Lock() on entry logic |
| Execution engine | No safety layer replacing NT8 ATM | Build circuit breakers simultaneously with execution, not after |
| Kronos integration | Inference blocking event loop | Dedicated persistent inference process; never call synchronously in loop |
| Kronos integration | Inference exceeds bar duration on CPU | Measure CPU latency on target hardware; GPU strongly preferred |
| Backtesting design | vectorbt cannot replay DOM signals | Databento MBO replay for signal generation; vectorbt for portfolio sim only |
| Backtesting design | Mid-session crash divergence from historical | Session state persistence to disk every minute |
| Signal engine design | 44-signal correlation inflating confidence | Pairwise correlation matrix before implementation; ML L1 regularization |
| Signal engine design | ProcessPoolExecutor IPC overhead per bar | shared_memory for bar data; minimize what is pickled |
| ML backend | Optuna reinforcing overfit signals | Purged walk-forward; 200 OOS trades per signal minimum |
| GEX integration | GEX staleness during session | Same as v1: session-open refresh + staleness weight reduction |
| Stack selection | Free-threaded CPython instability | Use standard GIL CPython 3.12; re-evaluate in 3.15 era |
| Production deployment | async-rithmic library maturity ceiling | Pin version; maintain local fork; document fallback path |

---

## Pitfalls That Do NOT Carry Forward from v1

| v1 Pitfall | Why It Doesn't Apply |
|-----------|---------------------|
| Pitfall 3: NT8 DOM backtesting impossible | Replaced by Databento MBO replay — Python can actually replay DOM history |
| Pitfall 5: Pine Script → C# execution timing mismatch | No Pine Script port involved; Python implementation is fresh |
| Pitfall 8: Monolithic NinjaScript file collapse | Python allows proper module structure from day one; no partial class constraints |
| Pitfall 9: NT8 race conditions between DOM and bar threads | asyncio is single-threaded; no NT8 internal lock hierarchy to worry about |
| Pitfall 6: ATM Strategy slippage overhead | Direct Rithmic execution eliminates the NT8 order routing layer |

---

## Sources

**Python asyncio performance and GIL:**
- Python asyncio development guide: https://docs.python.org/3/library/asyncio-dev.html
- Scaling asyncio on free-threaded Python (Quansight Labs): https://labs.quansight.org/blog/scaling-asyncio-on-free-threaded-python
- Free-threaded Python production readiness (Optiver, 2025): https://optiver.com/working-at-optiver/career-hub/choosing-between-free-threading-and-async-in-python/
- Python asyncio event loop blocking (Medium, 2025): https://medium.com/@virtualik/python-asyncio-event-loop-blocking-explained-with-code-examples-0b2bba801456

**async-rithmic:**
- async-rithmic GitHub: https://github.com/rundef/async_rithmic
- async-rithmic documentation: https://async-rithmic.readthedocs.io/
- async-rithmic PyPI: https://pypi.org/project/async-rithmic/
- Issue #49 (ForcedLogout reconnection loop): https://github.com/rundef/async_rithmic/issues/49

**Tick classification and aggressor side:**
- NinjaTrader forum — exchange-provided aggressor flags (confirmed NT8 does not expose them): https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1333190-exchange-provided-trade-side-aggressor-flags
- CME MDP 3.0 AggressorSide field: https://ref.onixs.biz/net-cme-mdp3-market-data-handler-guide/f-onixs-cmemdhandler-tags-aggressorside.html
- Elite Trader — CME historical data with aggressor info: https://www.elitetrader.com/et/threads/cme-historical-data-with-trade-aggressor-info.290818/

**Databento MBO:**
- Databento MBO snapshot documentation: https://databento.com/blog/live-MBO-snapshot
- Databento backtesting to live trading: https://databento.com/blog/backtesting-market-replay
- Databento MBO subscription limitation (must subscribe at node startup): https://databento.com/docs/standards-and-conventions/mbo-snapshot

**Kronos inference:**
- Kronos GitHub (inference latency data): https://github.com/shiyu-coder/Kronos
- Kronos arxiv paper: https://arxiv.org/abs/2508.02739
- Kronos BrightCoding overview (April 2026): https://www.blog.brightcoding.dev/2026/04/10/kronos-the-revolutionary-ai-model-for-financial-markets

**Python GC and memory:**
- CPython GC internals: https://blog.codingconfessions.com/p/cpython-garbage-collection-internals
- Python gc module docs: https://docs.python.org/3/library/gc.html
- Order book C-level implementation (performance patterns): https://www.research.hangukquant.com/p/implementing-a-c-level-orderbook

**v1 pitfalls (carry-forward basis):**
- DEEP6 v1 PITFALLS.md: .planning-v1-nt8/research/PITFALLS.md
- Academic: walk-forward validation framework (Dec 2025): https://arxiv.org/html/2512.12924v1
- Academic: backtest overfitting in ML era (2024): https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110
