# Repair Workflow

Last verified: 2026-05-22

## Standard Repair Loop

1. capture source
2. capture editor/server errors
3. run static analysis when available
4. fix the first root cause only
5. re-check
6. compile on chart if possible
7. inspect console / objects / strategy results if relevant

## Guard Library

- `bar_index >= lookback`
- `array.size(a) > i and i >= 0`
- `not na(obj)` before setter calls
- `barsAgo >= 0 and barsAgo <= bar_index and barsAgo <= 5000`

## DEEP6 Bias

- preserve the original
- prefer small surgical fixes
- explain root cause plainly after the repair
