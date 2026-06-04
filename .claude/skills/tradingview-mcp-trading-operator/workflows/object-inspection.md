# Object Inspection Through MCP

Last verified: 2026-05-22

Use this workflow when a Pine script compiles but you need to verify what it actually drew on the chart.

## Purpose

Visual objects are often the first place Pine logic silently fails. MCP object readers let you inspect the output directly instead of guessing from source code.

## Core Readers

### `data_get_pine_labels`
Reads text + price pairs created by `label.new()`.

Use it to verify:
- expected label count exists
- label prices are reasonable for the active symbol
- duplicate labels are not being emitted every bar
- label text matches the intended state or verdict

Recommended checks:
- compare label count against the expected number of events
- inspect whether labels cluster at impossible prices like `0`, `na`, or far outside the visible range
- use `study_filter` to isolate one indicator when multiple scripts draw labels

### `data_get_pine_lines`
Reads horizontal levels produced by `line.new()` and returns deduplicated price levels by default.

Use it to verify:
- support/resistance levels appeared
- signal thresholds or anchors were drawn
- duplicate lines are not being recreated at the same price each bar

Especially useful for:
- DEEP6 anchor or reaction levels
- static regime boundaries
- entry, stop, or target guides

### `data_get_pine_boxes`
Reads zone boundaries as `{high, low}` pairs from `box.new()`.

Use it for:
- supply and demand zones
- absorption areas
- session ranges
- anchored value areas or contextual regions

Check that:
- boxes have non-inverted bounds (`high >= low`)
- zone count is reasonable
- repeated zones are not being spammed across bars

### `data_get_pine_tables`
Reads formatted table rows created by `table.new()`.

Use it to verify HUD or dashboard content such as:
- bias state
- score breakdowns
- active mode / regime text
- current parameter summaries

This is better than screenshot-only inspection when the question is “what exact text is the table showing?”

### `data_get_study_values`
Reads current indicator values from the TradingView data window.

Use it for numeric spot checks like:
- RSI / MACD / EMA values
- custom plotted score outputs
- state plots exposed for debugging
- confirming that an internal signal really reached the threshold the code expects

For pure numeric verification, this is usually better than screenshots.

## `verbose=true` vs Default

### Default mode
Use default output when the task is value verification:
- “Did the expected level appear?”
- “Are there three zones?”
- “What text is currently visible?”

Default mode is smaller and easier to reason about when you only need prices, zones, or text.

### `verbose=true`
Use verbose mode when debugging object lifecycle problems:
- object IDs seem to churn every bar
- you need raw coordinates
- you suspect duplicate creation rather than simple wrong values
- you need color, position, or other raw metadata to diagnose unexpected rendering

Verbose mode is for structural debugging, not routine value confirmation.

## When To Use This Workflow

Use object inspection when:
- code compiles but labels/lines/boxes/tables are missing or wrong
- screenshots show “something is off” but not why
- you need to confirm a script is drawing the intended Pine objects
- you want to validate a custom study without relying only on visual eyeballing

## Common Failure Pattern

### Objects exist in code but do not appear on chart
Check these first:
- `barstate.islast` gates are too restrictive, so historical bars never update or create objects
- object count limits were exceeded (`max_labels_count`, `max_lines_count`, `max_boxes_count`)
- missing `var` declarations cause objects to be recreated instead of updated
- logic creates objects behind impossible conditions that never become true
- object setters are called on `na` references because initialization never happened

## Practical Verification Sequence

1. Confirm script and chart context with `chart_get_state`.
2. Use `data_get_study_values` if the question is numeric.
3. Use the matching object reader:
   - labels for `label.new()`
   - lines for `line.new()`
   - boxes for `box.new()`
   - tables for `table.new()`
4. Re-run in `verbose=true` only if lifecycle or metadata issues remain unclear.
5. If objects still do not appear, inspect code for `barstate.islast`, count caps, and `var` lifecycle errors.

## Good Verification Questions

- “Did the study emit exactly one anchor verdict label?”
- “Are the support lines on plausible NQ prices?”
- “Does the HUD table show the same regime seen in console output?”
- “Are there duplicate demand zones because a new box is created every bar?”

## Exit Criteria

This workflow is complete when you can answer:
- what objects exist
- where they are
- whether the count is expected
- whether the values are plausible
- whether lifecycle mistakes, not visual styling, are the real problem
