# DEEP6 Paper-to-Live Gate

This document defines the intended promotion path from paper trading to constrained live trading.

Important:
This is the policy target. Only trust it as operational reality when the code, telemetry, and verification artifacts support it.

## 1. Principle

No DEEP6 subsystem should move from paper to live because:
- it looks promising,
- it had a few good sessions,
- or the operator “feels good” about it.

Promotion must happen through evidence.

## 2. Promotion ladder

The intended ladder is:

1. unit and integration correctness
2. replay correctness
3. parity correctness
4. stable paper trading
5. constrained live candidate
6. constrained live deployment

## 3. Minimum paper requirements

Before live candidacy, DEEP6 should have:

- a defined number of paper sessions
- stable startup/shutdown behavior
- stable health behavior
- no unresolved parity concerns considered critical
- no unclear execution-state transitions
- reviewable logs and session outputs
- no undocumented operator steps

Suggested metrics to require:
- minimum session count
- maximum tolerated drawdown
- minimum rolling performance threshold
- maximum tolerated unexplained disable events
- maximum tolerated replay/live divergence

## 4. Blocking conditions

Any of the following should block live promotion:

- contradictory runtime truth
- unclear startup path
- unresolved port/env confusion
- unresolved parity drift
- replay behavior not understood
- unclear risk disable logic
- missing operator visibility
- inability to explain recent paper behavior
- stale or misleading operational docs

## 5. Live arming expectations

Live mode should require deliberate human action.

Target behavior:
- operator explicitly arms live mode
- operator sees current health summary
- operator sees current verification state
- operator sees current disable state
- operator confirms intended mode knowingly

Live mode should never be a side effect of:
- default startup
- stale env settings
- unclear flag behavior
- ambiguous runtime path

## 6. Constrained live deployment

The first live stage should be intentionally conservative.

Recommended constraints:
- reduced size
- reduced session scope
- stricter disable conditions
- mandatory post-session review
- rapid downgrade back to paper mode on anomalies

## 7. Downgrade triggers

The system should downgrade from live candidate or live mode if any of the following occur:

- unexplained parity drift
- unclear order or execution behavior
- operator health visibility failure
- feed staleness or unstable runtime state
- repeated unexplained disable/reenable cycles
- doc/runtime mismatch affecting operational certainty

## 8. Required evidence for promotion

Before promoting, DEEP6 should be able to produce:

- current-state doc
- verification ladder
- recent replay results
- recent parity results
- paper-trade summary
- release checklist
- operator health summary
- known limitations list

## 9. Final rule

If DEEP6 cannot justify live trust in writing, it should remain paper-only.
