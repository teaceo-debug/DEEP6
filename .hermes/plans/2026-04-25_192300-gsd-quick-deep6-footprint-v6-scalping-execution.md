# GSD Quick — DEEP6 Footprint V6 Scalping Execution

Status: execution kickoff
Source plan: `.hermes/plans/2026-04-25_191857-deep6-footprint-v6-scalping-plan.md`

Goal
- Execute a side-by-side `DEEP6FootprintV6` NinjaTrader indicator fork from `DEEP6FootprintV5`.
- Optimize for five-minute scalping with clear setup / armed / trigger visuals.
- Keep V5 intact.

Execution scope for this pass
1. Create versioned backup baseline.
2. Fork V5 to V6 with renamed class/name/description/wrapper region.
3. Apply first-slice scalp defaults:
   - Mission Control off
   - Chart Trader off
   - Tier-3 dots off
   - shorter active-signal lifetime
   - keep absorption/exhaustion/POC/profile anchors/score HUD
4. Remove stop/target emphasis from default workflow by simplifying Tier-1 overlay.
5. Preserve strong long/short clarity and gray setup context.
6. Run available static validation and reviews.

Constraints
- Do not replace `DEEP6FootprintV5`.
- Do not add stop/target overlays as the primary V6 workflow.
- Keep versioned indicators side-by-side.
- Keep long/short instantly obvious.

Notes
- This is the execution artifact required before repo edits.
- NT8 host compile will still be the final validation gate.
