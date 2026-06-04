# DEEP6 Verification Ladder

This document defines how DEEP6 earns trust.

A subsystem is not trusted because it is complex.
It is trusted because it has passed the next verification gate.

## Principle

Promotion only happens upward through evidence.

The ladder is:

1. unit correctness
2. integration correctness
3. replay correctness
4. parity correctness
5. paper-trading correctness
6. constrained live correctness

## Gate 0: Static and structural correctness

Objective:
Catch obvious breakage before runtime.

Evidence:
- package install succeeds
- imports resolve
- frontend dependencies install
- type/lint/test commands are documented and runnable

Minimum expectations:
- backend environment can install
- dashboard environment can install
- canonical commands are documented
- env examples are current

Pass criteria:
- no missing critical install steps
- no broken top-level startup docs
- no contradictory port/env defaults

## Gate 1: Unit correctness

Objective:
Each component behaves correctly in isolation.

Evidence:
- unit tests for signal engines
- unit tests for scoring
- unit tests for execution/risk state transitions
- unit tests for frontend state/store logic

Pass criteria:
- tests are green in the canonical environment
- failures are triaged and categorized
- critical engine modules have direct test coverage

## Gate 2: Integration correctness

Objective:
Subsystems work together without hidden contract breakage.

Evidence:
- backend integration tests
- API message contract verification
- dashboard/backend integration checks
- persistence/replay wiring checks

Pass criteria:
- core flows work end to end in a controlled environment
- backend and frontend schemas match documented behavior
- startup and shutdown behavior are verified

## Gate 3: Replay correctness

Objective:
Historical playback produces stable, explainable behavior.

Evidence:
- replay sessions
- score traces
- signal traces
- bar-by-bar comparisons
- deterministic session summaries

Pass criteria:
- replay runs complete successfully
- critical signals are reproducible
- score behavior is stable enough to analyze
- known deviations are documented, not ignored

## Gate 4: Parity correctness

Objective:
Reference behavior and execution-oriented behavior remain aligned enough to trust.

Examples:
- Python reference vs NT8 implementation
- replay output vs live-captured output
- expected score path vs emitted score path

Evidence:
- parity reports
- mismatch counts
- score delta distributions
- signal firing comparisons
- session-level summaries

Pass criteria:
- parity thresholds are explicitly defined
- mismatches are measured, not hand-waved
- unacceptable divergence blocks promotion

## Gate 5: Paper-trading correctness

Objective:
The system behaves safely and coherently with no real capital risk.

Evidence:
- minimum paper session count
- rolling performance metrics
- drawdown behavior
- operator intervention logs
- disconnect/recovery behavior
- risk disable/reenable behavior

Suggested pass criteria:
- minimum number of paper sessions completed
- no unresolved execution-state inconsistencies
- no unexplained disable events
- no unacceptable replay/live divergence
- operator dashboard health remains stable

## Gate 6: Constrained live correctness

Objective:
The system can be trusted with limited real exposure.

Evidence:
- explicitly armed live mode
- low-risk position sizing
- tracked live metrics
- reject/disable/failure logs
- post-session reviews

Pass criteria:
- live mode requires deliberate human arming
- risk limits are tighter than paper mode
- every live session is reviewable
- any major anomaly automatically downgrades the system back to paper-only

## Promotion rules

A higher gate cannot override failure at a lower gate.

Examples:
- Good paper results do not excuse bad parity
- Good replay results do not excuse broken operator health
- Strong signal logic does not excuse unclear execution gating

## Blocking conditions

The following should block promotion:

- contradictory runtime truth
- unclear startup path
- undocumented env requirements
- broken install/bootstrap path
- stale runbooks
- unmeasured parity drift
- unclear risk disable logic
- missing operator visibility into health state

## Required artifacts

DEEP6 should maintain these artifacts as first-class evidence:

- current-state doc
- runbook
- repo guide
- parity reports
- replay reports
- paper-trade summaries
- operator health dashboard/status output
- release candidate checklist

## Final rule

If DEEP6 cannot explain why it should be trusted, it is not ready to be trusted.
