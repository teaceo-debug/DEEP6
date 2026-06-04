# GSD Quick: Options Level Intelligence NT8 Indicator

## Issue
User does not see the Options Level Intelligence work in the NinjaTrader Indicators dialog.

## Cause
The completed work created a Python sidecar and JSON output only. It did not create/register a NinjaScript indicator.

## Goal
Add a side-by-side NinjaTrader indicator that reads `options_level_intelligence.json` and renders the selected 1-3 prominent levels.

## Constraints
- Do not replace existing indicators.
- New standalone indicator/class/file name.
- Keep options levels as map/context, not trade triggers.
- Read JSON from `C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\options_level_intelligence.json` by default.
- Verify compile/registration as much as possible.
