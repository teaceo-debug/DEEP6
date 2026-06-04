# Decisions — deep6-gamma-decision-surface-v2

## [2026-05-15] Atlas: Phase Execution Order

Decision: Execute in 3 phases:
1. Phase A (Python sidecar A1-A9) — foundation: all logic + data structures in one file
2. Phase B (NT8 renderer B1-B11) + Phase C (Tests C1-C6) — PARALLEL after Phase A
3. Final Verification Wave (F1-F4) — all in parallel

Rationale:
- Phase B (NT8) can be built against the JSON schema defined in Phase A spec
- Phase C (tests) needs Phase A code to be importable
- B and C don't depend on each other

## [2026-05-15] Atlas: Delegation Strategy

Phase A: Single large delegation — all A1-A9 go into one file
Phase B: Single large delegation — all B1-B11 go into one CS file
Phase C: Single large delegation — all C1-C6 go into one test file
