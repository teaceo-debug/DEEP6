# DEEP6 Release Checklist

Use this checklist before calling any DEEP6 state “ready” for broader use, paper deployment, or live-candidate evaluation.

## 1. Documentation truth

- [ ] `README.md` matches current project reality
- [ ] `docs/CURRENT-STATE.md` is current
- [ ] `docs/REPO-GUIDE.md` is current
- [ ] `docs/RUNBOOK.md` only describes implemented flows or clearly labels planned ones
- [ ] subsystem READMEs do not contradict top-level docs
- [ ] port/env/runtime truth is consistent across docs

## 2. Bootstrap truth

- [ ] canonical startup path is documented
- [ ] env requirements are documented
- [ ] install steps are reproducible
- [ ] demo/replay/backend modes are clearly separated
- [ ] dashboard/backend connection instructions are current

## 3. Backend/runtime health

- [ ] backend starts without ambiguous failures
- [ ] health endpoint responds
- [ ] websocket route behaves as documented
- [ ] replay path behaves as documented
- [ ] no unresolved startup warnings are being ignored
- [ ] instrument/contract assumptions are current

## 4. Verification

- [ ] unit tests are green in the canonical environment
- [ ] integration tests are green in the canonical environment
- [ ] replay validation has been run recently
- [ ] parity status is known
- [ ] unresolved verification failures are documented and blocking where appropriate

## 5. Dashboard/operator visibility

- [ ] dashboard connects as documented
- [ ] live/demo/replay mode distinction is clear
- [ ] status indicators are interpretable
- [ ] stale feed conditions are visible
- [ ] operator cannot easily confuse demo and real data

## 6. Execution/risk posture

- [ ] execution path is clearly identified
- [ ] paper/live distinction is explicit
- [ ] disable conditions are known
- [ ] recovery behavior is documented
- [ ] no unresolved ambiguity exists around arming/execution state

## 7. Promotion readiness

- [ ] release target is defined:
  - [ ] docs cleanup
  - [ ] demo release
  - [ ] replay release
  - [ ] paper-trade candidate
  - [ ] constrained live candidate
- [ ] blocking issues are listed
- [ ] owner is assigned for unresolved blockers
- [ ] this release does not rely on undocumented assumptions

## 8. Final question

Before release, answer:

Can DEEP6 explain why it should be trusted at this release level?

If the answer is unclear, the release is not ready.
