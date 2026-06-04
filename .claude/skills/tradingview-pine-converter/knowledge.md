# TradingView Pine Converter — Knowledge Index

Last verified: 2026-05-22

Purpose: convert Pine indicators and strategies into Python code aligned with DEEP6 VectorBT PRO conventions and `BaseSignalGenerator`.

## Trigger Fit

- convert Pine to Python
- Pine → VBT / VectorBT PRO
- port Pine logic into `BaseSignalGenerator`
- review converted logic for repainting or parameter mistakes

## BANNED Parameter Names

| Banned | Use instead | Why |
|---|---|---|
| `stop_loss_pct` | `sl_stop` | VBT-native stop name |
| `take_profit_pct` | `tp_stop` | VBT-native take-profit name |
| `sl_pct` | `sl_stop` | wrong convention |
| `tp_pct` | `tp_stop` | wrong convention |
| `stop_loss` | `sl_stop` | wrong format/name |
| `take_profit` | `tp_stop` | wrong format/name |
| `atr_mult` | extract explicit stop decimal | do not leave stop logic as ATR parameter |
| `rr_ratio` | derive `tp_stop` from explicit risk/reward math | not a VBT portfolio param |
| `trailing_stop_pct` | `sl_trail` | wrong name |

## REQUIRED VBT Stop Format

- `sl_stop`, `tp_stop`, and `sl_trail` only.
- Use decimal fractions, never percentages.
- `0.02` means 2%, not `2.0`.
- If Pine uses `strategy.exit()`, extract stop/limit intent into params; do not re-implement stop execution inside `generate_signals()`.

## Core Pine → Python Mapping

| Pine | Python |
|---|---|
| `ta.sma(src, n)` | `src.rolling(n).mean()` |
| `ta.ema(src, n)` | `src.ewm(span=n, adjust=False).mean()` |
| `ta.rma(src, n)` | `src.ewm(alpha=1.0 / n, adjust=False).mean()` |
| `ta.highest(src, n)` | `src.rolling(n).max()` |
| `ta.lowest(src, n)` | `src.rolling(n).min()` |
| `ta.sum(src, n)` | `src.rolling(n).sum()` |
| `ta.change(src)` | `src.diff()` |
| `ta.crossover(a, b)` | `(a.shift(1) <= b.shift(1)) & (a > b)` |
| `ta.crossunder(a, b)` | `(a.shift(1) >= b.shift(1)) & (a < b)` |
| `nz(x, 0)` | `x.fillna(0)` |
| `na(x)` | `x.isna()` / `pd.isna(x)` |

## Indexing Inversion Warning

Pine history is bars-back, not Python positional indexing.

- Pine `close[1]` = Python `close.shift(1)`
- Pine `close[5]` = Python `close.shift(5)`
- Never translate Pine `close[1]` into Python `close[1]`

## Boolean Output Rule

Python boolean Series can contain NaN even though Pine v6 bools cannot.

Always finish with:

```python
entries = entries.fillna(False)
exits = exits.fillna(False)
```

## Anti-Repainting MTF Rule

For HTF data converted from `request.security()`, resample then shift after resampling:

```python
htf_close = close.resample('15min').last().shift(1).reindex(close.index, method='ffill')
```

Use this when Pine intent is confirmed higher-timeframe data. Never forward-fill unshifted HTF closes if the original script is meant to be non-repainting.

## `BaseSignalGenerator` Contract Summary

Every converted strategy should implement:

1. `get_default_params()` — mirror Pine inputs and include VBT-native stop params when needed.
2. `get_param_ranges()` — optimization ranges in repo conventions.
3. `generate_signals(data, **params)` — return `(entries, exits)` boolean Series only.

Contract rules:

- inherit from `research.vectorbt_signals.base.BaseSignalGenerator`
- validate required OHLCV columns
- merge default params with overrides
- keep stop execution out of `generate_signals()`
- return boolean outputs with `.fillna(False)`

## 10-Point Quality Checklist

1. Pine version and repainting risk identified?
2. All stop/take-profit values converted to `sl_stop` / `tp_stop` decimals?
3. No banned parameter names left?
4. All Pine bars-back references converted with `.shift()`?
5. All crossover/crossunder logic uses prior-bar comparison?
6. All HTF logic shifted after resampling?
7. No stop execution logic left inside `generate_signals()`?
8. `get_default_params()`, `get_param_ranges()`, and `generate_signals()` all present?
9. Output entries/exits filled with `.fillna(False)`?
10. Code references source assumptions and any manual-review risks?

## Source Reference

Full source oracle: `C:\Users\Tea\DEEP6\dashboard\agents\pinescript-to-python-converter.md` (2,102 lines).
