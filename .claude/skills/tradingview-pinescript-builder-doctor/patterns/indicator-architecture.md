# Indicator Architecture

Last verified: 2026-05-22

Use this file for Pine indicators that draw context, levels, signals, labels, tables, lines, or zones.

## Recommended Build Order

1. Declaration and limits (`overlay`, `max_*_count`, `max_bars_back` only when justified)
2. Inputs grouped by function
3. Pure calculations
4. State and object lifecycle (`var`, arrays, last-bar update rules)
5. Visual output
6. Optional alerts

## Code Skeleton

Use this structure as the default build order in actual Pine code:

```pinescript
//@version=6
indicator("DEEP6 Indicator Skeleton", overlay = true, max_labels_count = 100, max_lines_count = 100, max_boxes_count = 50)

// ===== Inputs =====
groupMain = "Main"
groupVisual = "Visual"
length = input.int(20, "Length", minval = 1, group = groupMain)
showSignals = input.bool(true, "Show Signals", group = groupVisual)

// ===== Calculations =====
emaFast = ta.ema(close, length)
bullSignal = ta.crossover(close, emaFast)
bearSignal = ta.crossunder(close, emaFast)

// ===== State =====
var label lastSignalLabel = na
var line trendGuide = na

// ===== Visuals =====
plot(emaFast, "EMA", color = color.aqua)
plotshape(showSignals and bullSignal ? low : na, title = "Bull", style = shape.triangleup, location = location.belowbar, color = color.lime)
plotshape(showSignals and bearSignal ? high : na, title = "Bear", style = shape.triangledown, location = location.abovebar, color = color.red)

if bullSignal
    lastSignalLabel := label.new(bar_index, low, "Bull", style = label.style_label_up)

// ===== Alerts =====
alertcondition(bullSignal, "Bull Signal", "Bull signal on {{ticker}} {{interval}}")
alertcondition(bearSignal, "Bear Signal", "Bear signal on {{ticker}} {{interval}}")
```

This sequence keeps series calculations separate from object lifecycle and prevents the script from collapsing into one giant side-effect block.

## Design Rules

- Default to non-repainting logic.
- Guard dynamic history and array access.
- Create long-lived objects once, then update them.
- Use `xloc.bar_time` when drawings must stay candle-locked across timeframe changes or replay.

## `var` + `barstate.islast` Singleton Pattern

Use this when one HUD label, dashboard table, or anchor guide should exist as a single persistent object.

```pinescript
var label statusLabel = na

if barstate.islast
    if na(statusLabel)
        statusLabel := label.new(time, high, "", xloc = xloc.bar_time, style = label.style_label_left)
    label.set_x(statusLabel, time)
    label.set_y(statusLabel, high)
    label.set_text(statusLabel, "Score: " + str.tostring(close, format.mintick))
```

Why this matters:
- the object is created once
- updates happen only on the last visible bar when appropriate
- the script avoids leaking a new label every bar

Reference: `C:\Users\Tea\DEEP6\Indicators\sd_anchor_ai.pine` uses persistent-object thinking and update-in-place patterns instead of uncontrolled object churn.

## Array-Managed Event Object Pattern With Count Cap

Use arrays when the script needs multiple event markers but must respect object limits.

```pinescript
var label[] eventLabels = array.new<label>()
maxEvents = 20

if bullSignal
    newLabel = label.new(bar_index, low, "Bull", style = label.style_label_up)
    array.push(eventLabels, newLabel)

    if array.size(eventLabels) > maxEvents
        oldLabel = array.shift(eventLabels)
        label.delete(oldLabel)
```

This pattern gives you:
- explicit count control
- deterministic cleanup
- easier debugging than implicit object accumulation

Reference: `C:\Users\Tea\DEEP6\Indicators\sd_anchor_ai.pine` is the local model for explicit guardrails around dynamic state, capped structures, and non-fragile update logic.

## Tuple-Returning Helper Function Pattern

Use helper functions that return multiple values when one scan produces a compact diagnostic bundle.

```pinescript
f_legQualityBull(_close, _open, _range) =>
    body = math.abs(_close - _open)
    bodyPct = _range > 0 ? body / _range : 0.0
    strongClose = _close > _open and bodyPct >= 0.6
    [strongClose, bodyPct]

[bullLegOk, bullLegScore] = f_legQualityBull(close, open, high - low)
```

Why this pattern is preferred:
- related outputs stay synchronized
- callers avoid recomputing the same scan logic
- the script becomes easier to read than parallel helper calls returning one value each

Reference: `C:\Users\Tea\DEEP6\Indicators\sd_anchor_ai.pine` uses decomposed helper logic and score-like sub-results that should stay grouped instead of buried in monolithic expressions.

## Anti-Pattern: Monolithic `if barstate.islast` Blocks

Avoid this style:

```pinescript
if barstate.islast
    // calculate everything
    // scan pivots
    // mutate arrays
    // create labels
    // update lines
    // build table
    // fire alerts
```

Why it is bad:
- mixes calculation and side effects
- hides bugs in object lifecycle
- makes replay and verification harder
- encourages missing initialization guards
- often causes “objects exist in code but not on chart” failures

Use `barstate.islast` only for the pieces that truly must run on the last bar, such as dashboard refresh or singleton object repositioning.

Reference: `C:\Users\Tea\DEEP6\Indicators\sd_anchor_ai.pine` is the model for decomposed logic, guarded state, and deliberate visual updates instead of one giant last-bar block.

## DEEP6 Pattern Reference

`C:\Users\Tea\DEEP6\Indicators\sd_anchor_ai.pine` is the local reference for:

- explicit `max_bars_back()` calls on dynamic series
- helper functions for pivot scanning and range search
- score-style decomposition instead of monolithic logic
- optional MTF support using `request.security(..., lookahead=barmerge.lookahead_off)`
- update-in-place state instead of uncontrolled object creation
- helper decomposition patterns that should be extended, not flattened

## Exit Criteria

- declaration matches actual script type
- object caps are intentional
- no unguarded dynamic history or array access
- MTF paths use explicit lookahead settings
- singleton objects are persistent and updated, not recreated blindly
- event objects are capped and cleaned up deterministically
