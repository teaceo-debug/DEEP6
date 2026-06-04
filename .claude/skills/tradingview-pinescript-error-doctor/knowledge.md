# TradingView PineScript Error Doctor — Master Knowledge Index

Last verified: 2026-05-22

## Purpose

This skill is the DEEP6 repair layer for Pine Script. It combines official TradingView error classes, common community error patterns, and a strict MCP-assisted repair workflow.

## Query Routing Map

- official error code like `CE10101`, `CW10003`, `RE10139`, `RE10143` → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\errors\official-error-codes.md`
- undeclared identifier, bad namespace, type mismatch, syntax confusion → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\errors\common-compile-errors.md`
- qualifier mismatch, `const`/`input`/`simple`/`series` confusion, `series int` vs `simple int` → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\errors\type-system-errors.md`
- label/line/box/table lifecycle failures, max object counts, setter-on-`na`, `xloc` anchoring mistakes → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\errors\drawing-object-errors.md`
- loop runtime failures, scope leakage, circular references, `var` persistence bugs → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\errors\loop-and-scope-errors.md`
- `request.security()` repainting, memory limits, MTF index mismatch, dynamic request boundaries → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\errors\request-security-errors.md`
- repainting, MTF, request.security, intrabar/confirmation bugs → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\playbooks\repainting-and-mtf.md`
- runtime crash, array/history/object bug, bad strategy behavior → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\playbooks\repair-workflow.md`
- v5→v6 migration questions and breaking-change triage → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\playbooks\version-migration.md`
- alert not firing, webhook empty, alert fires too often → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\playbooks\alert-debugging.md`
- final validation before paste/save/ship → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\playbooks\expert-checklist.md`
- surgical guard snippets and common one-line repairs → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\patterns\quick-fixes.md`
- temporary debug visibility with plots, labels, tables, and logs → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\patterns\debug-instrumentation.md`

## Canonical Repair Loop

1. capture the exact source and diagnostics
2. classify the first root-cause error
3. fix one root cause, not every downstream symptom
4. re-check / re-compile
5. inspect chart objects, console, and strategy tester if relevant

## Official Error Coverage From Research

Official TradingView error/documentation pages confirmed during research:

- `CE10101` — condition must evaluate to bool
- `CW10003` — history-dependent function should run on each calculation for consistency
- `RE10139` — memory limits exceeded
- `RE10143` — requested historical offset beyond buffer limit

Primary source family:

- `https://www.tradingview.com/pine-script-docs/errors/overview/`
- `https://www.tradingview.com/pine-script-docs/errors/CE10101/`
- `https://www.tradingview.com/pine-script-docs/errors/CW10003/`
- `https://www.tradingview.com/pine-script-docs/errors/RE10139/`
- `https://www.tradingview.com/pine-script-docs/errors/RE10143/`

## High-Frequency Community Error Classes

- undeclared identifier
- missing namespace (`ta.`, `math.`, `str.`, `request.`)
- type mismatch across `const` / `simple` / `series`
- invalid history indexing or negative bars-back logic
- array out-of-bounds
- mismatched input / syntax spillover from a prior line
- repainting due to lookahead or unconfirmed-bar logic

## Local DEEP6 References

- `C:\Users\Tea\DEEP6\skills\tradingview-pine-debugging-mastery.md` — source material for this skill’s repair approach
- `C:\Users\Tea\DEEP6\Indicators\sd_anchor_ai.pine` — reference for guarded dynamic history and MTF patterns
- `C:\Users\Tea\DEEP6\scripts\po3_webhook_additions.pine` — reference for alert/webhook payload repair

## File Inventory

- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\SKILL.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\knowledge.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\errors\official-error-codes.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\errors\common-compile-errors.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\errors\type-system-errors.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\errors\drawing-object-errors.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\errors\loop-and-scope-errors.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\errors\request-security-errors.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\playbooks\repair-workflow.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\playbooks\repainting-and-mtf.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\playbooks\version-migration.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\playbooks\alert-debugging.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\playbooks\expert-checklist.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\patterns\quick-fixes.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\patterns\debug-instrumentation.md`

## Conventions

- Load one article plus one playbook, not the whole directory.
- Prefer official error docs when a documented code exists.
- Preserve originals and use versioned repaired copies when a destructive rewrite would be risky.

## Reference Documents

- `C:\Users\Tea\DEEP6\skills\tradingview-pine-debugging-mastery.md` — 702-line source material for repair approach and guard patterns
- `C:\Users\Tea\DEEP6\dashboard\agents\pinescript-expert.md` — 2,347-line Pine language reference oracle (fallback for function signatures)
