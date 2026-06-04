# request.security Errors and MTF Failure Modes

Last verified: 2026-05-22

Use this file when multi-timeframe logic compiles but repaints, leaks memory, or misaligns bars.

## 1. Repainting from `lookahead=barmerge.lookahead_on`

This setting can project unfinished higher-timeframe values backward onto lower-timeframe bars.

Risky pattern:

```pine
htfClose = request.security(syminfo.tickerid, "15", close, lookahead = barmerge.lookahead_on)
```

Safer default:

```pine
htfClose = request.security(syminfo.tickerid, "15", close, lookahead = barmerge.lookahead_off)
```

For strict confirmed-bar behavior, shift inside the requested expression or consume the prior confirmed HTF value.

## 2. Returning collections causes `RE10139` memory failures

Bad idea:

```pine
request.security(syminfo.tickerid, "15", myArray)
```

or repeatedly requesting large composite structures every bar.

Prefer returning scalars, tuples of small scalar values, or booleans. Keep heavy arrays on the chart timeframe when possible.

## 3. `bar_index` mismatch across chart/requested timeframes

The `bar_index` inside the requested context belongs to the requested timeframe, not the chart timeframe.

Consequences:

- comparing requested `bar_index` directly to chart `bar_index` gives nonsense
- event anchoring by index can drift badly

If you need stable cross-timeframe anchoring, use time-based coordinates and `xloc.bar_time`.

## 4. Anti-repainting pattern

When you need confirmed HTF data on an LTF chart, this pattern is the honest baseline:

```pine
htfPrevClose = request.security(syminfo.tickerid, "15", close[1], lookahead = barmerge.lookahead_off)
```

Why it works:

- `lookahead_off` avoids future projection
- `close[1]` asks for the previous confirmed HTF bar

## 5. v6 dynamic requests

In v6, dynamic requests work inside loops and conditionals by default. That removes some old structural restrictions, but it does not remove repainting or memory risk.

Still validate:

- are symbol/timeframe changes intentional?
- is the result confirmed or realtime-sensitive?
- are you issuing too many requests or returning too much data?

## 6. Use `calc_bars_count` to limit historical scope

If you only need a bounded amount of HTF history, limit it:

```pine
htfSignal = request.security(syminfo.tickerid, "60", close > open, lookahead = barmerge.lookahead_off, calc_bars_count = 300)
```

This reduces unnecessary history loading and can help prevent memory/runtime issues.

## `sd_anchor_ai.pine` Reference Pattern

Reference: `C:\Users\Tea\DEEP6\Indicators\sd_anchor_ai.pine`

The file uses fixed-timeframe MTF boolean support checks with `lookahead_off`:

```pine
tf5Support = request.security(syminfo.tickerid, "5", close > open and close >= close[1], lookahead=barmerge.lookahead_off)
```

That is a good default because it returns a scalar boolean, uses explicit HTF settings, and does not request collections.

## Repair Checklist

1. Replace `lookahead_on` unless the behavior is explicitly intentional and disclosed.
2. Avoid returning arrays or oversized structures from `request.security()`.
3. Do not compare requested-frame `bar_index` with chart-frame `bar_index`.
4. Prefer time anchoring for objects.
5. Add `calc_bars_count` when full history is unnecessary.
