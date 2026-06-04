# GSD Quick — DEEP6 Atlas Usability Triage

Status: execution kickoff

Goal
- Take the current DEEP6 / NT8 indicator stack as the working baseline for the requested Atlas-style handoff.
- Remove obvious compile/runtime blockers where possible.
- Reduce chart noise and make signals immediately understandable for live use.
- Keep versioned indicator files side-by-side instead of replacing prior versions.

Execution scope for this pass
1. Inspect the current NT8 repo state and identify the active versioned footprint indicator to refine.
2. Spawn parallel reviewers for compile-risk, usability/noise, and signal-language clarity.
3. Apply a version-safe new indicator revision instead of overwriting older versions.
4. Simplify chart language so setup / wait / trigger and long / short are obvious at a glance.
5. Reduce noisy overlays and defaults that obscure execution decisions.
6. Run available static validation and NT8-oriented checks, then summarize deployment steps.

Constraints
- Do not replace or remove prior indicator versions.
- Keep long/short instantly clear with plain-English labels.
- Avoid adding stop/target overlay clutter.
- Use repo source under `ninjatrader/Custom/`, not deployed NT8 copies.

Notes
- The Atlas zip mentioned in the user handoff is not present in the current workspace, so execution will target the existing DEEP6 NT8 codebase in this repo.
- Final host compile validation should use NT8 automation/scripts after code changes are staged.
