# Loop and Scope Errors

Last verified: 2026-05-22

Use this file when Pine fails because iteration or variable lifetime is uncontrolled.

## `Loop is too long (> 500 ms)`

The classic cause is an unbounded or near-unbounded loop:

```pine
for i = 0 to bar_index
```

Why it fails:

- Pine re-runs script logic across historical bars
- the loop grows with chart length
- nested loops multiply the cost fast

Safer patterns:

```pine
for i = 0 to math.min(bar_index, 100)
```

or use a precomputed scan cap as seen in `C:\Users\Tea\DEEP6\Indicators\sd_anchor_ai.pine`:

```pine
scanBars = math.min(calculatedScan, 490)
for barsAgo = rightBars to scanBars
```

## `Script has too many local variables`

Pine local-variable budget is finite; a commonly hit threshold is 1000.

Triggers:

- huge inline expressions split into many temporaries
- deeply nested functions each declaring many locals
- repeated variable declarations in loops or condition branches

Fixes:

- extract shared logic into helper functions
- reuse existing variables when safe
- remove one-use temporary aliases
- split large routines into smaller functions

## Scope Traps

Variables declared inside `if` or `for` do not exist outside that local scope.

Wrong:

```pine
if signal
    float level = high
plot(level)
```

Correct:

```pine
float level = na
if signal
    level := high
plot(level)
```

The same rule applies to object IDs, arrays, and strings.

## Circular Reference Errors

Wrong initialization:

```pine
x = x[1] + 1
```

This references `x` before Pine has a persistent series definition for it.

Correct persistent-state pattern:

```pine
var float x = 0.0
x := x[1] + 1
```

If `na` initialization is needed, type it explicitly:

```pine
var float x = na
x := na(x[1]) ? close : x[1] + 1
```

## `var` vs Assignment

- `var float x = 0.0` initializes once, then persists.
- `float x = 0.0` reinitializes on every bar.

Use `var` for:

- rolling state machines
- object IDs
- arrays
- values that depend on prior bars

Use plain declarations for bar-local calculations that should reset every bar.

## Practical Repair Pattern

1. Cap every loop with a fixed or justified upper bound.
2. Move declarations needed later to outer scope.
3. Add `var` to stateful series or object IDs.
4. Replace self-references on first declaration with `var` + subsequent `:=` assignment.
5. Re-test for both compile errors and runtime slowness.
