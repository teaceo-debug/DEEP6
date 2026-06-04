# Expert Pre-Submission Checklist

Last verified: 2026-05-22

Run this checklist before declaring a Pine repair or build stable.

1. Version declaration correct?
2. All function namespaced?
3. All variables declared before use?
4. All conditions return bool?
5. All history-dependent functions in global scope?
6. All `request.security()` using `lookahead_off`?
7. All strategy signals gated with `barstate.isconfirmed`?
8. All drawings updated only on realtime/last bars?
9. All arrays checked for bounds before access?
10. All loops have fixed iteration count < 500?
11. No circular variable dependencies?
12. No implicit numeric-to-bool casting?
13. No `varip` in backtested strategies?
14. No `request.security()` returning arrays on every bar?
15. No `max_bars_back` unless justified?

## How To Use It

- If any answer is “no”, the script is not submission-ready.
- Apply the smallest safe repair first.
- Re-check replay, alerts, and Strategy Tester behavior after technical fixes.
