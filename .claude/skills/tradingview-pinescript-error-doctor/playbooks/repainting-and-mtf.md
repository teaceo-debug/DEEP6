# Repainting and MTF Playbook

Last verified: 2026-05-22

Use this file when the script compiles but behaves dishonestly or inconsistently across replay, realtime, or timeframe changes.

## Common Causes

- `request.security(..., lookahead=barmerge.lookahead_on)`
- using current higher-timeframe bar data as if confirmed
- signals firing intrabar without the user understanding the consequence
- `varip` state that has no historical equivalent
- drawings anchored to `bar_index` when they should be anchored to `time`

## First Repairs To Try

- default to `barmerge.lookahead_off`
- gate close-confirmed logic with `barstate.isconfirmed` when appropriate
- use previous confirmed HTF values where the strategy requires non-repainting behavior
- move candle-locked drawings to `xloc.bar_time`

## Verification

- compare chart state after replay stepping
- inspect labels/lines/boxes after timeframe changes
- for strategies, compare trade behavior with and without intrabar options consciously enabled
