# DEEP6 Runbook

This runbook covers implemented and currently intended operator workflows for DEEP6.

Important:
If a workflow here is marked “planned,” do not treat it as production-ready until the code and verification artifacts support it.

For overall project truth, read:
- `README.md`
- `docs/CURRENT-STATE.md`
- `docs/VERIFICATION-LADDER.md`

## 1. Purpose

This runbook exists to answer:
- how to start the relevant DEEP6 subsystem
- how to verify health
- how to stop it safely
- how to investigate failures
- what should block promotion toward live trading

## 2. Scope

DEEP6 currently has multiple operational surfaces:

1. Python/backend/reference engine
2. Dashboard/replay UI
3. NinjaTrader execution-oriented path

This runbook is intentionally conservative:
- only describe flows that are clearly represented in the repo
- label planned workflows explicitly
- do not imply live-readiness where verification is incomplete

## 3. Pre-flight checklist

Before running anything:

- confirm which subsystem you are operating
- confirm which port/endpoints are expected for that subsystem
- confirm env/config values are present
- confirm the intended data source is correct
- confirm instrument/contract is current
- confirm you are not treating a demo or replay path as a live path

Minimum pre-flight:
- project dependencies installed
- dashboard dependencies installed if using UI
- canonical env file reviewed
- backend port and websocket URL verified
- no conflicting stale docs being followed

## 4. Startup modes

### Mode A: Dashboard-only demo / local UI validation
Use when:
- validating frontend behavior
- checking replay/demo rendering
- working without live backend connectivity

Expected:
- dashboard starts
- demo mode or mock data path is active
- no claims of live signal or execution truth

Verification:
- UI renders
- charts update
- signal/score panels behave coherently
- no websocket confusion if demo mode is intended

### Mode B: Python backend/reference runtime
Use when:
- validating backend/API behavior
- testing replay/reference behavior
- checking integration with dashboard

Expected:
- backend process starts cleanly
- health endpoint responds
- websocket endpoint responds if enabled
- logging is coherent
- no silent config ambiguity

Verification:
- health check passes
- websocket connects
- replay or synthetic/live path behaves as expected
- dashboard receives data if connected

### Mode C: NinjaTrader execution-oriented runtime
Use when:
- validating NT8-based indicator/strategy/runtime behavior
- testing paper-trade workflows
- validating execution-facing behavior

Expected:
- NT8-specific docs and setup are followed
- runtime state is checked from NT8-side tooling and logs
- parity/reference assumptions are documented, not guessed

Verification:
- NT8 loads expected components
- relevant indicator/strategy state is visible
- paper-trade behavior is logged and reviewable

## 5. Safe startup procedure

1. Identify the subsystem you are starting.
2. Confirm its intended port, websocket route, and env values.
3. Start only one canonical entrypoint for that subsystem.
4. Capture startup logs immediately.
5. Verify health before trusting behavior.
6. Do not assume signal correctness from successful startup alone.

## 6. Health checks

Minimum health signals DEEP6 should expose or verify:

- process is running
- health endpoint responds
- websocket handshake succeeds if applicable
- feed is not stale
- expected instrument is loaded
- no unresolved startup exceptions
- no ambiguity about demo vs replay vs live-like mode

If any of these are unclear, treat the system as degraded.

## 7. Safe shutdown

General shutdown rules:

- prefer graceful shutdown
- preserve logs
- do not kill processes abruptly unless already broken
- document whether shutdown occurred during:
  - idle
  - replay
  - paper execution
  - reconnect state

Expected shutdown outcome:
- process stops cleanly
- no orphaned ambiguous operator state
- last-known session status remains reviewable

## 8. Incident categories

### Category A: Documentation incident
Examples:
- startup instructions conflict
- port docs conflict
- runbook disagrees with actual runtime

Action:
- stop following assumptions
- identify authoritative doc
- record mismatch
- update docs before proceeding further

### Category B: Runtime incident
Examples:
- backend starts but websocket fails
- dashboard connects but shows stale data
- replay endpoint behaves inconsistently
- startup path only partially works

Action:
- capture exact command used
- capture logs
- confirm env/config values
- verify whether behavior is expected, degraded, or broken

### Category C: Verification incident
Examples:
- replay does not match expected session behavior
- score path drifts unexpectedly
- parity assumptions fail
- execution gate behavior is unclear

Action:
- block promotion
- produce a verification artifact
- treat as trust issue, not cosmetic issue

### Category D: Execution/risk incident
Examples:
- unexpected enable/disable state
- unclear order submission behavior
- unclear flatten/cancel semantics
- unresolved paper/live state confusion

Action:
- halt promotion
- review state transition logs
- do not continue toward live deployment until resolved

## 9. Paper-trading posture

Paper mode should be treated as mandatory validation, not as a formality.

Minimum expectations before promotion:
- repeatable startup
- stable health state
- explainable signal behavior
- explainable disable/reenable logic
- reviewable sessions
- no unresolved parity concerns

## 10. Live trading posture

Live trading should be treated as restricted and explicitly armed.

Rules:
- live mode must never be assumed from startup success
- live mode should require deliberate operator acknowledgment
- any unresolved verification or health issue blocks promotion
- any major anomaly should downgrade the system back to paper-only

## 11. What this runbook does not claim

This runbook does not claim:
- all DEEP6 modes are production-ready
- all live-mode gates are already implemented exactly as desired
- all docs in the repo are already aligned
- all replay/live parity work is complete

## 12. Required companion docs

Operate DEEP6 alongside:
- `docs/CURRENT-STATE.md`
- `docs/VERIFICATION-LADDER.md`
- `docs/EVIDENCE.md`
- `docs/PAPER-TO-LIVE-GATE.md`
