# No-Trades Debugging

Last verified: 2026-05-22

Use this decision tree when a Pine strategy compiles but Strategy Tester shows zero trades.

## Goal

Separate “strategy never generated a valid signal” from “strategy generated signals but order/risk/settings logic suppressed execution.”

## Decision Tree

### 1. Is it actually a `strategy()` script?
If the script starts with `indicator()` instead of `strategy()`, Strategy Tester will not produce trades.

Check first:
- declaration line
- whether `strategy.entry()` / `strategy.exit()` calls even exist

### 2. Do entry conditions ever become true?
Plot them directly.

Use temporary instrumentation like:

```pinescript
plotchar(longCondition, title = "Long condition", char = "L", location = location.bottom)
plotchar(shortCondition, title = "Short condition", char = "S", location = location.top)
```

If the condition never prints, the problem is upstream in signal logic, not order placement.

### 3. Are date or session filters suppressing everything?
Temporarily comment out or bypass:
- date windows
- session restrictions
- weekday filters
- news blackout filters

If trades appear after removing filters, the strategy logic is not dead; the gating logic is too restrictive.

### 4. Is `pyramiding = 0` preventing expected entries?
`pyramiding = 0` allows only one open position in the same direction.

This does not block the first trade, but it will block repeated same-direction entries while a position is still open. If the user expects scaling or repeated same-side signals, check whether pyramiding settings match that expectation.

### 5. Are entry IDs conflicting?
Using the same ID for long and short entries can suppress or overwrite expected behavior.

Bad:

```pinescript
strategy.entry("Entry", strategy.long, when = longCondition)
strategy.entry("Entry", strategy.short, when = shortCondition)
```

Prefer distinct IDs:

```pinescript
strategy.entry("Long", strategy.long, when = longCondition)
strategy.entry("Short", strategy.short, when = shortCondition)
```

### 6. Is the `when` parameter always false?
Many “no trade” bugs are really hidden condition bugs inside `when = ...`.

Check for:
- `when = sessionOk and riskOk and signalOk` where one gate never turns true
- nullable or mistyped booleans
- `barstate.isconfirmed` on logic tested only intrabar

Plot each gate independently if needed.

### 7. Are exits immediately neutralizing entries?
Sometimes the strategy appears to have no usable trades because exits or closes invalidate positions instantly.

Check for:
- `strategy.close()` or `strategy.close_all()` firing on the same bar as entry
- stop/limit levels computed on the wrong side of price
- `calc_on_order_fills` loops causing immediate exit logic

### 8. Is symbol/timeframe mismatch hiding signals?
An intraday logic model on a weekly chart may never trigger. A strategy designed for NQ 1-minute bars may go silent on daily data.

Check:
- active chart timeframe
- symbol family
- bar type
- any `request.security()` dependencies using the wrong higher/lower timeframe assumptions

### 9. Is a risk function killing all trades?
Risk controls such as `strategy.risk.max_drawdown()`, max intraday loss, or custom session kill-switches can block all further entries.

Check:
- built-in `strategy.risk.*` usage
- custom “trading disabled” flags
- persistent `var bool disabled = true` style lockouts that never reset

### 10. MCP verification path
Once the code looks correct, verify the symptom directly:

- use `data_get_trades` to confirm trade count is truly zero
- use `data_get_study_values` to confirm signal indicators are producing live values

If indicators are moving but trade count remains zero, the failure is almost always in gating, entry IDs, order logic, or risk suppression.

## Fast Triage Order

If time is short, check in this order:
1. `strategy()` vs `indicator()`
2. entry condition plots
3. session/date filters
4. `when` gates
5. conflicting IDs
6. immediate exits
7. chart timeframe mismatch
8. risk locks

## Minimal Debug Pattern

```pinescript
plotchar(longCondition, title = "Long raw", char = "L", location = location.bottom)
plotchar(shortCondition, title = "Short raw", char = "S", location = location.top)
plotchar(sessionOk, title = "Session gate", char = "G", location = location.bottom)
plotchar(riskOk, title = "Risk gate", char = "R", location = location.bottom)
```

This quickly shows whether the no-trade issue is signal absence or order suppression.

## Exit Criteria

You are done when you can state which layer failed:
- signal generation
- filtering/gating
- entry ID / order wiring
- exit logic
- chart context mismatch
- risk shutdown
