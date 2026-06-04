# Strategy Execution Flags

Last verified: 2026-05-22

Use this article to interpret how Pine strategy declaration flags materially change backtest behavior and live-vs-backtest parity.

## Why These Flags Matter

Two strategies with identical entry conditions can produce very different results if their execution flags differ. In TradingView, many “alpha improvements” are actually just execution-model changes.

## `calc_on_every_tick`

Recalculates on every realtime tick while the live bar is forming.

Effects:
- live behavior can diverge from historical backtest behavior
- intrabar signals can appear live but not be reproducible on bar-close backtests
- can make alert and order timing feel more responsive in realtime

Important caveat:
- historical backtests do not have full realtime tick-by-tick decision history in the same way, so setting this to `true` creates a live/backtest mismatch unless the strategy is intentionally intrabar-aware

Use only when:
- intrabar behavior is explicitly required
- the user understands the parity tradeoff

## `process_orders_on_close`

Allows fills at the current bar's close instead of the next bar's open.

Effects:
- usually makes entries and exits look more favorable in backtests
- can materially improve metrics without reflecting realistic execution

Default guidance:
- `false` is safer and more conservative
- use `true` only when the strategy is intentionally modeled around close execution and the limitation is documented

## `use_bar_magnifier`

Uses lower-timeframe data to simulate intrabar order fills more realistically.

Effects:
- significantly improves realism for stop and limit order strategies
- helps strategies that depend on intrabar touches not visible in the chart timeframe's OHLC summary
- increases trustworthiness of fill sequencing relative to coarse OHLC assumptions

Recommended for:
- stop entries
- stop-loss and take-profit systems
- strategies whose results are highly sensitive to intrabar path

## `calc_on_order_fills`

Recalculates the script immediately when an order fills.

Effects:
- enables same-bar entry and exit sequences
- can change strategy state mid-bar
- can create feedback loops if fill-triggered recalculation fires logic that issues another order immediately

Use carefully when:
- you intentionally want same-bar management after an entry fills
- you have verified the strategy is not recursively issuing orders in a way that inflates behavior

## `close_entries_rule`

Controls how entries are matched when positions are reduced or closed.

Common modes:
- FIFO behavior
- `any` behavior

Why it matters:
- affects which open leg is considered closed first
- matters more when pyramiding or partial exits are involved
- changes trade accounting and per-trade statistics even if total PnL looks similar

## `fill_orders_on_standard_ohlc`

Forces fills against standard OHLC values even when the chart uses Heikin Ashi or other synthetic bar types.

Why this matters:
- synthetic bars can create unrealistic fill assumptions if used directly for execution simulation
- setting this to `true` is usually more realistic when the displayed chart is not standard candlesticks

Recommended default:
- `true` for realism whenever non-standard chart types are involved

## Commission and Slippage

Always set both explicitly.

For NQ futures, a practical baseline is:
- commission: about `$4.50` per contract round-trip
- slippage: `1-2` ticks depending on session, volatility, and strategy aggressiveness

Why this matters:
- leaving commission at zero can turn mediocre systems into fake winners
- zero slippage especially distorts fast breakout, reversal, and stop-based strategies

## Recommended Reading Of Results

When performance changes after a flag edit, ask:
- did the signal improve, or did fills become more favorable?
- did the strategy become more realistic, or less realistic?
- did live/backtest parity improve, or worsen?

## Safer NQ Baseline Pattern

For most NQ strategy testing, a conservative baseline is:
- `calc_on_every_tick = false`
- `process_orders_on_close = false`
- `use_bar_magnifier = true` when stop/limit fill quality matters
- `calc_on_order_fills = false` unless same-bar management is explicitly required
- `fill_orders_on_standard_ohlc = true`
- commission and slippage explicitly set

## Exit Criteria

This article has done its job when you can explain whether a result change came from:
- signal logic
- fill modeling
- realtime recalculation behavior
- trade matching/accounting rules
- realistic cost assumptions
