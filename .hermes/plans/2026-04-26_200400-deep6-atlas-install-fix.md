# DEEP6 Atlas install/fix plan

Goal
- Locate the downloaded Deep Six Atlas package.
- Install it into NinjaTrader 8 with its original identity and file/class names intact.
- Reproduce actual NT8 compile errors.
- Fix only the compile blockers, then verify a clean compile.

Context
- Package found at `/mnt/c/Users/Tea/Downloads/DEEP6_ATLAS_NT8.zip`.
- NT8 is currently running and baseline compile succeeds before Atlas install.
- User requested Claude Code be used.

Execution steps
1. Stage the downloaded Atlas source into the workspace without renaming the product.
2. Copy Atlas indicator/strategy/addon payload into NT8 Custom folders as shipped.
3. Trigger NT8 compile and scrape the exact error grid.
4. Use Claude Code to analyze the failing Atlas sources and propose minimal fixes.
5. Apply targeted fixes, sync the installed copy, and recompile until clean.
6. Report what was installed and what errors were fixed.

Constraints
- Preserve `DEEP6Atlas`, `DEEP6AtlasDiag`, and `DEEP6AtlasStrategy` names.
- Keep the indicator installed essentially as shipped; only compile-error fixes are allowed.
- Do not change unrelated DEEP6 indicators.
