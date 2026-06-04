# Type System and Qualifier Errors

Last verified: 2026-05-22

Use this file when Pine compiles complain about `const`, `input`, `simple`, or `series` incompatibility.

## Qualifier Hierarchy

Pine qualifiers widen in one direction only:

`const → input → simple → series`

- `const`: compile-time literal or expression derived only from constants.
- `input`: stable user-configured value from `input.*()`.
- `simple`: known once per bar, but not historical series.
- `series`: may vary bar to bar.

You can pass a narrower qualifier into a wider slot. You cannot pass a wider qualifier into a narrower slot.

## Exact Error Patterns To Recognize

Common messages or close variants:

- `Cannot call 'X' with argument 'Y'='series int'. An argument of 'simple int' type was used but a 'series int' is expected.`
- `Cannot call 'request.security' with argument 'timeframe'='series string'. An argument of 'simple string' type is expected.`
- `The argument 'length' should be of type: simple int`.
- `An argument of 'series float' type was used but a 'const float' is expected.`
- `Cannot use 'series bool' in local declaration requiring const/input/simple.`
- `The 'title' argument must be const string.`

The message wording changes slightly by function, but the repair logic is always the same: find the first parameter whose contract requires a narrower qualifier than the value you supplied.

## Why `int()` and `float()` Do NOT Remove `series`

Casting changes the primitive type, not the qualifier.

```pine
seriesLen = bar_index > 100 ? 20 : 50
simpleLen = int(seriesLen)  // still series int, not simple int
plot(ta.ema(close, simpleLen))
```

`int(seriesLen)` is still recomputed every bar, so Pine still treats it as `series int`.

Same for:

- `float(seriesValue)` → still `series float`
- `str.tostring(seriesValue)` → still `series string`
- `bool(seriesExpr)` → still `series bool`

If a parameter requires `simple` or `const`, fix the source, not the cast.

## Safe Fix Patterns

### 1. Use `input.*()` when a `simple` value is required

```pine
length = input.int(20, "Length", minval = 1)
ma = ta.ema(close, length)
```

### 2. Use literals when a `const` value is required

```pine
plot(close, title = "Close")
```

Do not build plot titles from bar-dependent values.

### 3. Split dynamic logic from simple parameters

Wrong:

```pine
dynLen = close > open ? 20 : 50
emaVal = ta.ema(close, dynLen)
```

Safer alternatives:

```pine
ema20 = ta.ema(close, 20)
ema50 = ta.ema(close, 50)
emaVal = close > open ? ema20 : ema50
```

or expose the choices as separate inputs.

### 4. For MTF requests, keep symbol/timeframe arguments non-series unless v6 dynamic behavior is intentionally required

```pine
tf5 = "5"
tf15 = "15"
tf5Bull = request.security(syminfo.tickerid, tf5, close > open, lookahead = barmerge.lookahead_off)
```

If the expression is series, that is fine. The problem is usually a dynamic symbol/timeframe or a simple-only parameter elsewhere.

## `sd_anchor_ai.pine` Examples of Correct Usage

Reference: `C:\Users\Tea\DEEP6\Indicators\sd_anchor_ai.pine`

### Input values correctly feeding simple-only parameters

```pine
swingLeft = input.int(5, "Swing Left Bars", minval=2, maxval=20)
swingRight = input.int(5, "Swing Right Bars", minval=2, maxval=20)
pivotHighValue = ta.pivothigh(high, swingLeft, swingRight)
```

`input.int()` supplies stable input-qualified integers, which are acceptable where `ta.pivothigh()` expects non-series lengths.

### MTF requests using fixed timeframes and confirmed lookahead policy

```pine
tf5Support = request.security(syminfo.tickerid, "5", close > open and close >= close[1], lookahead=barmerge.lookahead_off)
tf15Support = request.security(syminfo.tickerid, "15", close > open and close >= close[1], lookahead=barmerge.lookahead_off)
```

This is the right pattern when the timeframe is intentionally fixed and non-repainting behavior matters.

## Repair Checklist

1. Identify the required qualifier from the error text.
2. Trace the value back to its origin.
3. If it is series, do not try to cast it away.
4. Replace with `input.*()`, literal constants, or precomputed fixed branches.
5. Re-check any downstream functions that inherit the same bad parameter.
