# Strategy Architecture

Last verified: 2026-05-22

Use this file for Pine strategies intended for Strategy Tester validation.

## Build Order

1. `strategy()` declaration with explicit behavior flags
2. inputs and sizing assumptions
3. signal generation
4. entry logic
5. exit logic
6. optional alert hooks and debug instrumentation

## Code Skeleton

Use an explicit declaration. Do not leave critical behavior implied.

```pinescript
//@version=6
strategy(
    "DEEP6 Strategy Skeleton",
    overlay = true,
    pyramiding = 0,
    calc_on_every_tick = false,
    calc_on_order_fills = false,
    process_orders_on_close = false,
    use_bar_magnifier = true,
    close_entries_rule = "FIFO",
    fill_orders_on_standard_ohlc = true,
    initial_capital = 50000,
    commission_type = strategy.commission.cash_per_contract,
    commission_value = 4.50,
    slippage = 1
)

// ===== Inputs =====
groupSignal = "Signal"
groupRisk = "Risk"
emaLen = input.int(20, "EMA Length", minval = 1, group = groupSignal)
stopTicks = input.int(20, "Stop (ticks)", minval = 1, group = groupRisk)
targetTicks = input.int(40, "Target (ticks)", minval = 1, group = groupRisk)

// ===== Signal =====
emaFast = ta.ema(close, emaLen)
longCondition = ta.crossover(close, emaFast)
shortCondition = ta.crossunder(close, emaFast)

// ===== Entries =====
strategy.entry("Long", strategy.long, when = longCondition and barstate.isconfirmed)
strategy.entry("Short", strategy.short, when = shortCondition and barstate.isconfirmed)

// ===== Exits =====
tickSize = syminfo.mintick
longStop = strategy.position_avg_price - stopTicks * tickSize
longTarget = strategy.position_avg_price + targetTicks * tickSize
shortStop = strategy.position_avg_price + stopTicks * tickSize
shortTarget = strategy.position_avg_price - targetTicks * tickSize

strategy.exit("Long Exit", from_entry = "Long", stop = longStop, limit = longTarget)
strategy.exit("Short Exit", from_entry = "Short", stop = shortStop, limit = shortTarget)
```

## Critical Defaults To Decide Explicitly

- `pyramiding`
- `calc_on_every_tick`
- `calc_on_order_fills`
- `process_orders_on_close`
- commission and slippage assumptions
- `use_bar_magnifier`
- `fill_orders_on_standard_ohlc`
- `close_entries_rule`

## Entry Pattern

Preferred long entry form:

```pinescript
strategy.entry("Long", strategy.long, when = condition and barstate.isconfirmed)
```

Why this pattern is safer:
- stable entry ID
- clear direction
- confirmed-bar behavior is explicit
- entry gating stays readable instead of being hidden in nested `if` blocks

Use the symmetric short form with a distinct ID.

## Exit Pattern

Preferred targeted exit form:

```pinescript
strategy.exit("Long Exit", from_entry = "Long", stop = stopPrice, limit = targetPrice)
```

This makes the relationship between entry and exit explicit and keeps long/short management from bleeding into each other.

## Common Mistake: Same Entry ID For Both Directions

Bad:

```pinescript
strategy.entry("Entry", strategy.long, when = longCondition)
strategy.entry("Entry", strategy.short, when = shortCondition)
```

Use distinct IDs instead:
- `"Long"`
- `"Short"`

This matters for:
- exit targeting
- trade list readability
- debugging no-trade or wrong-trade behavior

## Common Mistake: Exits Without Matching `from_entry`

Bad:

```pinescript
strategy.exit("Exit", stop = stopPrice, limit = targetPrice)
```

If a strategy has multiple directions or possible entries, this can become ambiguous or behave differently from what the author expects.

Prefer:

```pinescript
strategy.exit("Long Exit", from_entry = "Long", stop = longStop, limit = longTarget)
strategy.exit("Short Exit", from_entry = "Short", stop = shortStop, limit = shortTarget)
```

## Common Mistake: `strategy.close_all()` Instead Of Targeted Exits

`strategy.close_all()` is sometimes acceptable for emergency flattening, but it is a poor default architecture pattern.

Why it is risky:
- hides which thesis was invalidated
- reduces clarity in trade review
- makes partial or asymmetric management harder
- can mask exit-wiring mistakes that should be fixed directly

Prefer targeted `strategy.exit()` or `strategy.close("Long")` / `strategy.close("Short")` when the logic is direction-specific.

## Position Sizing Patterns

### Fixed quantity

```pinescript
strategy.entry("Long", strategy.long, qty = 1, when = longCondition)
```

Use when you want deterministic contract count and simple trade review.

### Percent of equity

```pinescript
strategy("Percent Equity Example", default_qty_type = strategy.percent_of_equity, default_qty_value = 5)
```

Use when you want position size to scale with account growth or contraction.

### Risk-based sizing
Compute quantity from stop distance and allowed dollar risk.

Concept:
- define account risk per trade
- convert stop distance to dollar risk per contract
- size contracts from risk budget ÷ per-contract risk

For NQ:
- tick value is `$5`
- 10 ticks of stop distance = `$50` per contract before slippage and commission

Risk-based sizing is the most realistic architecture when strategy stops are meaningful and fixed-size trading would distort the risk profile.

## NQ-Specific Reality Checks

- NQ tick value: `$5`
- typical commission baseline: about `$4.50` round-trip per contract
- realistic slippage baseline: `1-2` ticks for most backtest assumptions unless you have evidence for better fills

Any NQ strategy that ignores these can look materially stronger than it really is.

## Quality Rules

- plot entry conditions before blaming order logic
- keep entry and exit IDs stable
- make stop/target units explicit: price, ticks, or percent
- move to `tradingview-strategy-backtesting-operator` once the strategy compiles
- set flags explicitly so later reviews can explain the execution model without guesswork
