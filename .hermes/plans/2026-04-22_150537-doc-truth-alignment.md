# DEEP6 documentation truth-alignment plan

Goal: replace misleading top-level project docs with conservative, current-state documents that match the repo review findings.

Scope for this pass:
- Rewrite `README.md`
- Rewrite `docs/RUNBOOK.md`
- Add `docs/CURRENT-STATE.md`
- Add `docs/VERIFICATION-LADDER.md`
- Add `docs/REPO-GUIDE.md`
- Add `docs/EVIDENCE.md`
- Add `docs/RELEASE-CHECKLIST.md`
- Add `docs/PAPER-TO-LIVE-GATE.md`

Assumptions:
- User wants exact file edits, not just drafts.
- We are intentionally not changing code, ports, or runtime behavior in this pass.
- The docs should be conservative and avoid claiming features that are not clearly implemented.

Approach:
1. Preserve repo reality over ambition.
2. Make current-state docs authoritative.
3. Remove unsupported operational promises from the runbook.
4. Introduce verification/promotion framework docs that clearly distinguish target policy from implemented reality.

Validation:
- Re-read updated files after writing.
- Ensure README and RUNBOOK no longer claim a single fully unified Python-live runtime.
- Ensure all new docs use consistent language about current state, verification, and promotion.
