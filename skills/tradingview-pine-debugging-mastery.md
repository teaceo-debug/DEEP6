# TradingView Pine Script Debugging Mastery Guide

Purpose: skill-ready workflow for repairing Pine Script v5/v6 indicators and strategies in this TradingView environment without destroying original scripts. Use this guide whenever the user asks for Pine error support, TradingView compile failures, chart object bugs, alerts, strategy tester issues, or migration between Pine versions.

## Prime directive: never overwrite the original

1. Preserve the original script source exactly as found.
2. Create a new versioned copy for repairs:
   - `<OriginalName>_FIXED_v1`
   - `<OriginalName>_FIXED_v2`
   - `<OriginalName>_STABLE_YYYYMMDD`
   - For local files: `name_FIXED_v1.pine` or `name_STABLE_YYYYMMDD.pine`.
3. Keep changes minimal and targeted unless the user explicitly requests a rewrite.
4. Record what changed and why in comments near the repaired code when helpful.
5. Validate with the layered workflow below before calling the fix done.

## Standard debugging workflow

Use the tools in this order. Do not skip layers unless impossible.

### 1. Capture current context

- Get current chart state when a script is already on TradingView:
  - `mcp_tradingview_chart_get_state`
- Read current Pine source if the editor has the failing script:
  - `mcp_tradingview_pine_get_source`
- If errors are visible in the editor, capture Monaco markers:
  - `mcp_tradingview_pine_get_errors`
- If compiler output exists, read console:
  - `mcp_tradingview_pine_get_console`

### 2. Run offline/static analysis before server compile

- Use `mcp_tradingview_pine_analyze` on the exact source.
- This catches common runtime hazards before TradingView compile:
  - Array first/last on empty arrays.
  - Array get/set/remove with possible out-of-bounds indexes.
  - Bad loop bounds.
  - Implicit bool casts.
  - Unguarded negative or dynamic history offsets in common patterns.

### 3. Run TradingView server validation

- Use `mcp_tradingview_pine_check` with the exact source.
- Treat compile errors as blocking.
- Treat warnings carefully:
  - Pine v5 deprecation warnings are usually not fatal.
  - v5 scripts can often compile and run even when v6 is available.
  - Do not migrate to v6 just to remove warnings unless requested or required.

### 4. Compile/add to chart only after check passes

- Put the fixed source in the editor with `mcp_tradingview_pine_set_source`.
- Use `mcp_tradingview_pine_smart_compile` or `mcp_tradingview_pine_compile`.
- Then verify:
  - `mcp_tradingview_pine_get_errors`
  - `mcp_tradingview_pine_get_console`
  - `mcp_tradingview_chart_get_state`
  - `mcp_tradingview_data_get_study_values` when plots/values matter.

### 5. Inspect Pine-drawn objects when relevant

For scripts using labels, lines, boxes, or tables:

- Labels: `mcp_tradingview_data_get_pine_labels`
- Lines: `mcp_tradingview_data_get_pine_lines`
- Boxes/zones: `mcp_tradingview_data_get_pine_boxes`
- Tables: `mcp_tradingview_data_get_pine_tables`

Use these to verify that objects exist, values are sane, and duplicates are controlled.

## Common Pine v5/v6 error classes and fixes

## Version header and migration

Symptoms:
- `The script must have one declaration statement: indicator(), strategy() or library()`
- `Could not find function or function reference ...`
- v6 warnings or v5 deprecation messages.

Rules:
- Always include exactly one declaration:
  - `//@version=5` then `indicator(...)` or `strategy(...)`
  - `//@version=6` then `indicator(...)` or `strategy(...)`
- Do not include both `indicator()` and `strategy()`.
- Do not auto-convert a strategy into an indicator or the reverse. That changes semantics.
- v5 warning is not automatically fatal; preserve v5 if the script was built around v5 behavior.

## Series vs simple vs const typing

Pine qualifiers matter:

- `const`: known at compile time. Required by some inputs and declaration arguments.
- `input`: user input value, stronger than simple in many contexts.
- `simple`: value fixed during bar execution, not changing bar-to-bar.
- `series`: value can vary on every bar. Most calculations produce series.

Common errors:
- `Cannot call ... with argument ... An argument of 'series int' type was used but a 'simple int' is expected.`
- `An argument of 'series float' type was used but a 'const float' is expected.`
- `Cannot assign a value of the 'series ...' type to the 'simple ...' variable.`

Fix patterns:

```pine
// Bad: dynamic series length where simple length is required
len = close > open ? 10 : 20
ma = ta.sma(close, len)

// Good: use input/simple length
len = input.int(20, "Length", minval = 1)
ma = ta.sma(close, len)
```

```pine
// Bad: using calculated string in a const-only title
name = syminfo.ticker + " EMA"
plot(ta.ema(close, 20), title = name)

// Good: title must be const
plot(ta.ema(close, 20), title = "EMA")
```

When fixing:
- If a parameter requires `simple int`, prefer `input.int()` or a literal.
- If a parameter requires `const`, use a literal or compile-time expression only.
- Do not force-cast with `int()` or `float()` expecting it to remove `series`; it preserves the qualifier.

## input.time constants

Symptoms:
- `Cannot call input.time with argument 'defval'='...' An argument of 'simple int' or 'series int' type was used but a 'const int' is expected.`

Cause:
- `input.time()` default value must be compile-time constant.
- `timestamp()` can be non-const depending on overload/arguments.

Reliable fixes:

```pine
// Good: literal UNIX milliseconds constant
startTime = input.time(1704067200000, "Start time")  // 2024-01-01 00:00:00 UTC
```

```pine
// Often OK if all args are literal constants, but if compile complains, replace with literal ms
startTime = input.time(timestamp("2024-01-01T00:00:00Z"), "Start time")
```

Do not use `time`, `timenow`, `year`, `month`, `dayofmonth`, or calculated timestamps as `input.time` defaults.

## History indexing and bars-back safety

Common errors:
- `The requested historical offset (X) is beyond the historical buffer's limit (Y).`
- `Invalid number of bars back specified in the history-referencing operator. It accepts a value between 0 and 5000.`
- Runtime failures on early bars.

Rules:
- `close[n]` requires `n >= 0` and enough bars loaded.
- Pine history references cannot use negative offsets.
- Dynamic offsets must be guarded.
- Many functions return offsets as negative or positive depending on context. Confirm behavior before indexing.

Safe pattern:

```pine
lookback = input.int(50, "Lookback", minval = 1, maxval = 5000)
enoughBars = bar_index >= lookback
value = enoughBars ? close[lookback] : na
```

Dynamic offset guard:

```pine
offset = ta.highestbars(high, 50)  // often <= 0; 0 means current bar, -n means n bars ago
barsAgo = math.abs(offset)
valid = not na(offset) and barsAgo >= 0 and barsAgo <= bar_index and barsAgo <= 5000
swingHigh = valid ? high[barsAgo] : na
```

If using `ta.lowestbars()` / `ta.highestbars()`:
- Never directly do `high[ta.highestbars(...)]` without checking sign.
- Convert to non-negative bars-ago when needed.
- Guard against `na` and early bars.

## Negative bars-back errors

Typical bad pattern:

```pine
idx = bar_index - someFutureBar
price = close[idx]  // idx can become negative or not be bars-ago at all
```

Correct approach:

```pine
barsAgo = bar_index - targetBarIndex
valid = barsAgo >= 0 and barsAgo <= bar_index and barsAgo <= 5000
price = valid ? close[barsAgo] : na
```

Remember:
- History index means bars ago, not absolute bar index.
- `close[10]` means 10 bars before current, not bar_index 10.

## max_bars_back

Use when TradingView cannot infer dynamic history depth:

```pine
indicator("My Indicator", overlay = true, max_bars_back = 5000)
```

But do not use it as a substitute for guards. It increases available buffer; it does not make negative or impossible indexing valid.

## Labels, tables, lines, boxes: object pitfalls

## Labels

Common problems:
- Too many labels: `max_labels_count` exceeded.
- Labels created on every tick/bar without deletion.
- Labels drift because they use `bar_index` when time anchoring is needed.
- Wrong y coordinate when `yloc` is not what code assumes.

Best practices:

```pine
indicator("Labels", overlay = true, max_labels_count = 500)
var label lastLbl = na
if barstate.islast
    if not na(lastLbl)
        label.delete(lastLbl)
    lastLbl := label.new(bar_index, high, "Last", yloc = yloc.price)
```

For persistent event labels:
- Create only when event triggers.
- Store IDs in arrays if later cleanup is required.
- Limit count manually with `array.size()` and delete oldest.

## Tables

Common problems:
- Recreating table every bar.
- Updating table cells on every historical bar, slow and messy.
- Table disappears because it is not declared `var`.

Best practice:

```pine
var table t = table.new(position.top_right, 2, 3)
if barstate.islast
    table.cell(t, 0, 0, "Trend")
    table.cell(t, 1, 0, str.tostring(close))
```

Rules:
- Declare table with `var` once.
- Update contents inside `if barstate.islast` unless historical table state is specifically needed.
- Ensure row/column indexes are inside declared dimensions.

## Lines and boxes

Common problems:
- `max_lines_count` / `max_boxes_count` exceeded.
- Creating a new line every bar instead of updating an existing line.
- Confusing `xloc.bar_index` and `xloc.bar_time`.
- Drawing objects in the future or too far in the past using bar_index.

Update existing object:

```pine
var line lvl = na
if barstate.isfirst
    lvl := line.new(bar_index, close, bar_index + 1, close, extend = extend.right)
if barstate.islast and not na(lvl)
    line.set_xy1(lvl, bar_index - 1, close)
    line.set_xy2(lvl, bar_index, close)
```

Manual cleanup:

```pine
var array<line> lines = array.new_line()
if newLevel
    array.push(lines, line.new(bar_index, high, bar_index + 1, high))
if array.size(lines) > 100
    line.delete(array.shift(lines))
```

## xloc.bar_time candle locking

Use `xloc.bar_time` when a drawing must stay locked to the candle's timestamp across scrolling, timeframe changes, or replay.

Bad for candle locking:

```pine
label.new(bar_index, high, "Event")
line.new(bar_index, high, bar_index + 5, high)
```

Better:

```pine
label.new(time, high, "Event", xloc = xloc.bar_time, yloc = yloc.price)
line.new(time, high, time + 5 * timeframe.in_seconds(timeframe.period) * 1000, high,
     xloc = xloc.bar_time)
```

Notes:
- Pine `time` is UNIX milliseconds.
- `xloc.bar_time` x-values must be timestamps in milliseconds.
- `xloc.bar_index` x-values must be bar indexes.
- Do not mix timestamp x-values with `xloc.bar_index`.
- For multi-timeframe scripts, use the actual event bar's time, not current chart bar_index, if the object should anchor to the source candle.

## plotshape and absolute locations

Common error:
- Shape not showing or at wrong location.

Rules:
- With `location.absolute`, the first argument is treated as the y-value series.
- Use `na` to hide the shape.

```pine
// Correct absolute y plotting
plotshape(signal ? priceLevel : na,
     title = "Signal",
     style = shape.triangleup,
     location = location.absolute,
     color = color.lime)
```

If using `location.abovebar` or `location.belowbar`, first argument is a boolean condition.

```pine
plotshape(signal, style = shape.triangleup, location = location.belowbar)
```

## Arrays and loops

Common errors:
- `Index 0 is out of bounds, array size is 0.`
- `Cannot call array.get() with index ...` runtime failure.
- Loop with `for i = 0 to array.size(a) - 1` when array is empty.

Safe patterns:

```pine
if array.size(a) > 0
    first = array.get(a, 0)
```

```pine
sz = array.size(a)
if sz > 0
    for i = 0 to sz - 1
        item = array.get(a, i)
```

Reverse deletion pattern:

```pine
for i = array.size(a) - 1 to 0
    // only safe if size > 0 before loop
```

Actually safe:

```pine
sz = array.size(a)
if sz > 0
    for i = sz - 1 to 0
        // delete/remove safely
```

When removing while iterating, usually iterate backward.

## `na` handling

Common errors:
- Comparing directly to `na`.
- Calling setters on `na` object IDs.

Bad:

```pine
if myLine == na
```

Good:

```pine
if na(myLine)
```

Object setter guard:

```pine
if not na(myLine)
    line.set_y1(myLine, close)
```

## request.security pitfalls

Common problems:
- Lookahead/repainting.
- Using lower timeframe arrays incorrectly.
- Expecting `bar_index` from requested symbol/timeframe to match chart `bar_index`.

Best practices:

```pine
htfClose = request.security(syminfo.tickerid, "60", close, barmerge.gaps_off, barmerge.lookahead_off)
```

Rules:
- Default to `barmerge.lookahead_off` unless explicitly building a historical visualization that accepts lookahead.
- Anchor MTF drawings by `time` where possible.
- Do not use requested-timeframe values as object x coordinates unless they are actual timestamps.

## Alerts

There are two Pine alert systems:

1. `alertcondition()`
   - Indicator only style condition exposed in TradingView alert dialog.
   - Message is usually const string.
   - Does not fire by itself; user must create a TradingView alert.

2. `alert()`
   - Can use dynamic messages.
   - Must execute during runtime when condition occurs.
   - User still needs an alert set to script alert calls.

Pattern:

```pine
longSignal = ta.crossover(close, ta.sma(close, 20))
alertcondition(longSignal, title = "Long Signal", message = "Long signal")

if longSignal and barstate.isconfirmed
    alert("Long signal on " + syminfo.ticker + " close=" + str.tostring(close), alert.freq_once_per_bar_close)
```

Alert debugging checklist:
- Is the condition true on chart?
- Is code gated by `barstate.isconfirmed`, session, timeframe, or date filters?
- Did user create the TradingView alert after adding the latest script version?
- For repaint-sensitive alerts, use confirmed bars.
- For intrabar alerts, understand strategies need `calc_on_every_tick = true` to evaluate intrabar in realtime.

Tool workflow for alerts:
- Use `mcp_tradingview_alert_list` to inspect active alerts.
- Use `mcp_tradingview_alert_create` only after confirming desired condition/price.
- Do not delete user alerts unless explicitly requested; if requested, use `mcp_tradingview_alert_delete` carefully.

## Strategy vs indicator differences

Indicator:

```pine
indicator("Name", overlay = true)
plot(close)
```

Strategy:

```pine
strategy("Name", overlay = true, initial_capital = 100000, commission_type = strategy.commission.percent, commission_value = 0.01)
strategy.entry("L", strategy.long, when = longSignal)
```

Key differences:
- Strategies can place backtest orders with `strategy.entry`, `strategy.exit`, `strategy.close`.
- Indicators cannot call strategy order functions.
- Strategies can use Strategy Tester metrics; indicators cannot.
- Strategies may calculate on bar close by default unless configured otherwise.
- `alertcondition()` is primarily indicator-oriented. Strategies often use order-fill alerts or `alert()` calls.
- `timeframe` argument in `indicator()` has restrictions when drawings/side effects are used.

Strategy debugging checklist:
- Confirm the script declares `strategy()`, not `indicator()`.
- Verify Strategy Tester with:
  - `mcp_tradingview_data_get_strategy_results`
  - `mcp_tradingview_data_get_trades`
  - `mcp_tradingview_data_get_equity`
- Check order conditions are not mutually exclusive or blocked by date/session filters.
- Add debug plots/chars for signal booleans before changing order logic.
- Use `process_orders_on_close`, `calc_on_every_tick`, and `calc_on_order_fills` only when their behavioral changes are intended.

## Common syntax and namespace changes

Common v5/v6 namespaces:
- `sma()` -> `ta.sma()`
- `ema()` -> `ta.ema()`
- `rsi()` -> `ta.rsi()`
- `highest()` -> `ta.highest()`
- `lowest()` -> `ta.lowest()`
- `security()` -> `request.security()`
- `tostring()` -> `str.tostring()`
- `round()` -> `math.round()`
- `abs()` -> `math.abs()`

Color fixes:

```pine
// Old/transp style may fail or warn
plot(close, color = color.green, transp = 70)

// Preferred
plot(close, color = color.new(color.green, 70))
```

Input fixes:

```pine
// Old generic input can be ambiguous
len = input(20)

// Preferred
len = input.int(20, "Length", minval = 1)
src = input.source(close, "Source")
```

## Monaco editor errors

Use `mcp_tradingview_pine_get_errors` for Monaco markers. These are editor diagnostics and may differ from server compile output.

How to use them:
- Treat line/column as the first location to inspect, not always the true root cause.
- If Monaco points to a line after the real issue, inspect previous lines for:
  - Missing `)` or `]`.
  - Missing line continuation or bad indentation.
  - Unclosed string.
  - Ternary expression split incorrectly.
  - Extra comma in function arguments.
- After editing source, rerun Monaco errors and server check.

Common misleading cases:
- `Mismatched input 'end of line without line continuation'` usually means a multiline expression needs proper indentation or parentheses.
- Error line at `plot()` may be caused by invalid variable declaration above it.
- Unknown identifier may be caused by declaration inside a local block then used globally.

## Debug instrumentation patterns

Use temporary plots instead of guessing.

```pine
plotchar(longSignal, title = "DBG longSignal", char = "L", location = location.top)
plot(debugValue, title = "DBG value", color = color.yellow)
```

Use labels sparingly:

```pine
if barstate.islast
    label.new(bar_index, high, "state=" + str.tostring(state), yloc = yloc.price)
```

Use tables for last-bar state:

```pine
var table dbg = table.new(position.bottom_right, 2, 4)
if barstate.islast
    table.cell(dbg, 0, 0, "close")
    table.cell(dbg, 1, 0, str.tostring(close))
```

Remove or gate debug output before final `_STABLE` unless the user wants diagnostics visible.

## Repair playbooks

## Compile error repair

1. Save original as-is.
2. Run static analyze.
3. Run server check.
4. Fix the first root-cause error, not every downstream symptom.
5. Re-check.
6. Repeat until no blocking errors.
7. Compile on chart.
8. Verify no Monaco errors and no console errors.
9. Save as `_FIXED_vN` or `_STABLE_YYYYMMDD`.

## Runtime error repair

1. Identify runtime message from console/chart.
2. Locate object/array/history expression mentioned.
3. Add guards:
   - `not na(x)`
   - `array.size(a) > index`
   - `barsAgo >= 0 and barsAgo <= bar_index and barsAgo <= 5000`
   - `bar_index >= lookback`
4. Preserve output behavior when data is unavailable by returning `na` instead of forcing bad values.
5. Recompile and replay/scroll enough bars to hit the previous failure zone.

## Visual object repair

1. Inspect labels/lines/boxes/tables with Pine object tools.
2. Check declared max counts in `indicator()`/`strategy()`.
3. Convert repeated `new()` calls into `var` + setter updates where object should be singular.
4. For historical event markers, keep arrays and delete oldest.
5. Use `xloc.bar_time` for candle-locked drawings.
6. Verify positions after timeframe changes and replay when relevant.

## Alert repair

1. Determine whether the script uses `alertcondition()`, `alert()`, strategy order alerts, or a mix.
2. Plot/plotchar the alert condition.
3. Confirm bar-close vs intrabar behavior.
4. Confirm user recreated TradingView alert after script changes.
5. Do not promise alerts work just because compile passes; verify condition visibility and active alerts.

## Strategy repair

1. Confirm it is a strategy and appears in Strategy Tester.
2. Check results/trades/equity tools.
3. If no trades:
   - Plot entry conditions.
   - Check date/session filters.
   - Check `pyramiding`, position direction, and exits.
   - Check if conditions repaint or only appear intrabar.
4. If trades differ from expected:
   - Verify order execution settings.
   - Verify stop/limit units: price vs ticks vs percent.
   - Verify `strategy.exit()` IDs match entries.

## Final validation checklist

Before saying fixed:

- Original preserved.
- Fixed copy has versioned name.
- Static analyze completed or reason documented.
- Server check completed with no blocking compile errors.
- Chart compile completed when TradingView connection is available.
- Monaco errors checked after compile.
- Console checked after compile.
- For visual scripts: labels/tables/lines/boxes inspected if relevant.
- For strategies: Strategy Tester results/trades checked if relevant.
- For alerts: active alert setup/conditions checked if relevant.
- Summary includes files/script names changed and exact remaining warnings, if any.

## High-value quick fixes library

```pine
// Guard early bars
ready = bar_index >= length
val = ready ? close[length] : na
```

```pine
// Guard array access
val = array.size(a) > i and i >= 0 ? array.get(a, i) : na
```

```pine
// Guard object setters
if not na(l)
    line.set_y1(l, price)
```

```pine
// Last-bar table update
var table t = table.new(position.top_right, 2, 2)
if barstate.islast
    table.cell(t, 0, 0, "Status")
```

```pine
// Candle-locked label
label.new(time, high, "X", xloc = xloc.bar_time, yloc = yloc.price)
```

```pine
// Non-repainting confirmed alert
sig = ta.crossover(close, ta.sma(close, 20))
alertcondition(sig and barstate.isconfirmed, "Signal", "Signal")
```

```pine
// Dynamic barsAgo from target bar index
targetBar = ta.valuewhen(sig, bar_index, 0)
barsAgo = bar_index - targetBar
valid = not na(targetBar) and barsAgo >= 0 and barsAgo <= bar_index and barsAgo <= 5000
priceAtSignal = valid ? close[barsAgo] : na
```

## Operating style for this user

- Be direct and tool-driven.
- Do not guess from memory when tools can read/check/compile the script.
- Preserve originals, create `_FIXED` or `_STABLE` copies.
- Prefer small surgical repairs over rewrites.
- Explain root cause in plain language.
- Include exact TradingView tool outputs or summarized error messages in handoff.
- If TradingView compile is unavailable, still run static analysis/server check where possible and clearly state what could not be verified.
