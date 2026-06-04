# Official Pine Error Codes

Last verified: 2026-05-22

This file covers the official TradingView error/documentation codes confirmed during research.

## `CE10101` — Condition Must Evaluate To Bool

Use when `if`, `switch`, or ternary conditions receive non-bool values.

Root fixes:
- replace numeric truthiness with explicit comparisons
- use `not na(x)` instead of treating series values as booleans
- add explicit casting only when semantically correct

## `CW10003` — History-Dependent Function In Local Scope

Use when a history-dependent function is called conditionally and risks inconsistent series construction.

Root fixes:
- compute the series every bar
- apply conditions to the result, not to whether the function executes

## `RE10139` — Memory Limits Exceeded

High-probability causes:
- returning arrays/collections from `request.security()` on every bar
- over-allocating with unnecessary historical state
- excessive object churn or large strategy state

Root fixes:
- return collections only when needed, often on `barstate.islast`
- return computed results instead of large objects when possible
- tighten historical scope and object lifecycle

## `RE10143` — Historical Buffer Overflow

High-probability causes:
- dynamic history references beyond inferred buffer depth
- conditionally hidden history usage
- drawings referencing older bars than the buffer contains

Root fixes:
- explicit `max_bars_back()` where justified
- guard and simplify dynamic bars-back logic
- compute history-dependent values outside conditional traps

## Source URLs

- `https://www.tradingview.com/pine-script-docs/errors/overview/`
- `https://www.tradingview.com/pine-script-docs/errors/CE10101/`
- `https://www.tradingview.com/pine-script-docs/errors/CW10003/`
- `https://www.tradingview.com/pine-script-docs/errors/RE10139/`
- `https://www.tradingview.com/pine-script-docs/errors/RE10143/`
