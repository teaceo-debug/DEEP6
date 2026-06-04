# MCP Compile-Fix Loop

Last verified: 2026-05-22

Use this workflow when Pine code must be validated through the TradingView MCP bridge without skipping offline safeguards.

## Goal

Catch structural Pine problems early, then confirm the exact chart runtime state before declaring the script clean.

## Canonical Loop

1. `pine_get_source` → capture the current chart source before making assumptions.
2. `pine_analyze` → run offline static analysis first.
3. `pine_check` → run server-side validation without touching the chart.
4. If errors exist: fix the root cause locally, note what changed, then return to step 2.
5. `pine_set_source` → inject the fixed local source.
6. `pine_smart_compile` → compile on the active chart.
7. `pine_get_errors` → inspect Monaco markers after compile.
8. `pine_get_console` → inspect runtime output, warnings, and `log.info()` traces.
9. If clean: proceed to verification. If errors remain: fix and repeat from step 2.

## Why Each Step Exists

### 1. `pine_get_source`
- Confirms what is actually loaded in TradingView.
- Prevents debugging a stale local file while the chart holds a different script revision.
- Useful when the user says “I already pasted the fix” but the chart still behaves like the old version.

### 2. `pine_analyze`
Run this every iteration, even when the fix looks obvious.

It is the fastest way to catch:
- array out-of-bounds access
- unguarded history references like `close[idx]` where `idx` can exceed available bars
- `array.first()` / `array.last()` without size guards
- loop ranges that can step beyond valid indices
- implicit bool casts and other structural warnings that may not appear as clean compile errors yet

Never skip static analysis because you “know” the fix. The most common Pine regressions are secondary issues introduced while fixing the first error.

### 3. `pine_check`
Use server validation before chart injection.

This catches:
- compile errors
- warnings from TradingView's compiler
- version/syntax issues
- namespace mistakes
- type/qualifier errors

Because this step does not require adding the script to the chart, it keeps the active chart cleaner during rapid repair loops.

### 4. Fix root cause and note changes
After every fix, record a one-line note such as:
- “Guarded `array.get()` with `array.size() > 0`.”
- “Moved `alertcondition()` to global scope.”
- “Typed `float triggerPrice = na` to fix NA assignment.”

Do not batch speculative edits. Fix the first root cause that explains the downstream symptoms.

### 5. `pine_set_source`
Only inject code after steps 2 and 3 are clean enough to justify chart compile.

This keeps the chart-side source aligned with the local source of truth and reduces confusing partial edits inside TradingView.

### 6. `pine_smart_compile`
Compile on chart only after offline checks pass.

This step is required because some failures only appear once the script is attached to a chart context, especially:
- runtime object creation paths
- study/strategy attachment behavior
- symbol/timeframe-sensitive branches
- console logging or alert execution branches

### 7. `pine_get_errors`
Read Monaco markers immediately after compile.

Use these for:
- exact line/column confirmation
- compile markers not fully reflected in server validation text
- verifying whether the compiler error moved after a prior fix

### 8. `pine_get_console`
Compile-clean does not mean runtime-clean.

Inspect console output for:
- runtime exceptions or warnings
- debug logs showing impossible state
- alert paths not firing
- object count warnings or custom instrumentation messages

### 9. Proceed or loop
- If `pine_check`, `pine_get_errors`, and `pine_get_console` are all clean enough for the task, move to verification.
- If any new compile/runtime issue appears, fix it locally and loop back to step 2.

## Decision Points

### If `pine_analyze` fails but `pine_check` would probably pass
Still stop and fix the static-analysis issue first. Those warnings often become replay/runtime failures later.

### If `pine_check` passes but `pine_smart_compile` fails
Treat chart compile as the source of truth for active deployment. Chart context can expose issues hidden by source-only validation.

### If compile is clean but behavior is wrong
Do not keep recompiling blindly. Route to object inspection, study values, screenshots, or strategy tester verification depending on the symptom.

## Escalation Limit

- Maximum 5 iterations.
- If the fifth loop still surfaces new errors, escalate instead of continuing ad hoc edits.

Escalation means:
- summarize the exact remaining blocker
- list the 5 attempted fixes
- route to `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\knowledge.md`
- if the issue is behavioral rather than compile-related, route to the builder or backtesting skill as appropriate

## Good Iteration Notes

Keep repair notes brief and concrete:
- Iteration 1: “Added `array.size()` guard before `array.last()`.”
- Iteration 2: “Replaced local-scope `plotshape()` with global `plotshape(condition ? price : na)`.”
- Iteration 3: “Changed `security()` call to `request.security(..., lookahead = barmerge.lookahead_off)`.”

## Exit Criteria

The loop is complete only when:
- `pine_analyze` is acceptable
- `pine_check` is acceptable
- `pine_smart_compile` succeeds
- `pine_get_errors` is clean
- `pine_get_console` shows no unresolved runtime issue
- the script is ready for object, screenshot, or backtest verification
