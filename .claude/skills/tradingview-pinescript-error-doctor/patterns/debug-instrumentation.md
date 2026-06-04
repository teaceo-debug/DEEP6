# Debug Instrumentation Patterns

Last verified: 2026-05-22

Use this file when a script compiles but you need to expose hidden state before making a permanent fix.

## `plotchar()` for boolean visibility

```pine
plotchar(longSignal, title = "longSignal", char = "L", location = location.abovebar, color = color.lime)
```

Best for confirming whether a condition ever becomes true.

## `plot()` for numeric debug values

```pine
plot(score, title = "score", color = color.aqua)
plot(threshold, title = "threshold", color = color.orange)
```

Best for thresholds, rolling values, offsets, and MTF state.

## `label.new()` on `barstate.islast` for state snapshots

```pine
if barstate.islast
    label.new(time, high, "state=" + state, xloc = xloc.bar_time)
```

Use sparingly. Repeated last-bar labels still need cleanup or singleton reuse.

## `table.new()` with `var` for multi-field dashboards

```pine
var table dbg = table.new(position.bottom_right, 2, 4)
if barstate.islast
    table.cell(dbg, 0, 0, "state")
    table.cell(dbg, 1, 0, state)
    table.cell(dbg, 0, 1, "score")
    table.cell(dbg, 1, 1, str.tostring(score))
```

Prefer tables when you need several fields at once without polluting the chart with labels.

## `log.info()` for Pine Logs pane debugging (v6)

```pine
if barstate.islast
    log.info("state={0} score={1}", state, score)
```

Best for structured diagnostics that should not alter chart visuals.

## When to remove debug output

Remove or disable instrumentation before stable release when:

- plots change user-facing chart interpretation
- labels/tables consume object budget
- logs spam the Pine Logs pane
- debug paths hide the real business logic

If a debug view remains valuable for operators, convert it into an explicit `showDebug` input.
