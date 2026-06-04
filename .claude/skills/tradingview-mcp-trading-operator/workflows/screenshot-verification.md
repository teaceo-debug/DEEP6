# Screenshot Verification Workflow

Last verified: 2026-05-22

Use screenshots when the real question is visual: what the script drew, where it drew it, and whether the rendered chart matches expectations.

## Canonical Workflow

1. `chart_get_state` → confirm symbol, timeframe, and active indicators.
2. Adjust the view if needed with `chart_set_timeframe`, `chart_scroll_to_date`, or `chart_set_visible_range`.
3. `capture_screenshot` using the correct region: `full`, `chart`, or `strategy_tester`.
4. Set `filename` to something descriptive and traceable.
5. Compare the screenshot against the expected visual behavior.
6. For strategies, capture both the chart and the `strategy_tester` region.

## Step Details

### 1. `chart_get_state`
Confirm before every screenshot:
- symbol
- timeframe
- chart type if relevant
- active studies and whether the target study is present

Many screenshot mistakes are actually context mistakes: wrong symbol, wrong timeframe, or wrong indicator loaded.

### 2. Adjust the view
Use the minimum chart manipulation needed to expose the evidence.

Available tools:
- `chart_set_timeframe` for timeframe alignment
- `chart_scroll_to_date` to center a specific event or session
- `chart_set_visible_range` to frame a precise bar range or test window

Typical use cases:
- center on the bar where an alert or trade should have occurred
- zoom out to inspect object placement across multiple sessions
- zoom in to inspect one exact event label or trade marker

### 3. `capture_screenshot`
Pick the smallest region that proves the point.

Region choices:
- `chart` → best for overlays, objects, trade markers, and candles
- `strategy_tester` → best for net profit, drawdown, trade count, and performance panels
- `full` → use when panel context matters or when proving both chart and surrounding UI state

### 4. Use descriptive filenames
Examples:
- `nq1m-anchor-verdict-2026-05-12`
- `strategy-tester-bar-magnifier-on`
- `rsi-divergence-label-missing`

Descriptive names matter because screenshot review often spans multiple iterations.

### 5. Compare expected vs actual
Ask concrete questions:
- Did the expected line/box/label appear?
- Is the object anchored to the correct bar or time?
- Did the strategy place the marker where the signal should have fired?
- Does the visible layout match the numeric state from study values or tester results?

### 6. Strategies need two screenshots
For strategies, capture:
- the `chart` region for entries/exits/marker placement
- the `strategy_tester` region for the numeric result context

One without the other can hide whether the issue is visual placement or strategy accounting.

## When To Use Screenshots

Use screenshots for:
- visual verification of lines, boxes, labels, fills, and tables
- checking trade markers on the chart
- verifying overlay alignment against price action
- comparing before/after behavior across iterations
- documenting evidence for HERMES or operator review

## When NOT To Use Screenshots

Do not use screenshots for pure numeric verification.

If the question is:
- “What is the current RSI value?”
- “Did the score reach 80?”
- “What exact EMA value plotted?”

Use `data_get_study_values` instead. Screenshots are slower and less precise for numeric-only tasks.

## Common Failure Modes

- Screenshot taken on wrong timeframe.
- Correct study not loaded or hidden.
- Chart centered on the wrong date, so the missing object is off-screen.
- `full` screenshot used when `chart` or `strategy_tester` would have been easier to inspect.
- Strategy issue judged from chart alone without the tester panel.

## Suggested Verification Pairings

- screenshot + `data_get_study_values` for overlay correctness plus numeric sanity
- screenshot + object readers for “it looks wrong” investigations
- screenshot + `data_get_strategy_results` for strategy visual vs numeric parity

## Exit Criteria

The screenshot workflow is complete when:
- chart context is confirmed
- the relevant region is captured clearly
- filenames are traceable
- expected vs actual visual behavior is documented
- numeric-only checks were kept out of the screenshot path when a direct data tool was better
