# Learnings — NT8 Skills Upgrade
<!-- Append entries with ## [TIMESTAMP] Task: {id} format. Never overwrite. -->

## [2026-05-12] Task: 1 — Coverage Matrix

### What was built
`.sisyphus/drafts/nt8-coverage-matrix.md` maps all 443 H2/H3 headers from 7 source files to exactly one target skill.

### Header counts (verified exact match)
- ULTIMATE-NINJASCRIPT-AGENT-v5.md: 263 headers (78 H2 + 185 H3)
- ninjascript-error-surgeon-v2.md: 79 headers (12 H2 + 67 H3)
- ninjascript-ai-context.md: 15 headers (15 H2 + 0 H3)
- nt8-expert/knowledge.md: 43 headers (27 H2 + 16 H3)
- nt8-fix/knowledge.md: 19 headers (10 H2 + 9 H3)
- nt8-new/knowledge.md: 13 headers (10 H2 + 3 H3)
- nt8-architect/architecture.md: 11 headers (6 H2 + 5 H3)
- GRAND TOTAL: 443 headers, all mapped

### Target distribution
- builder-doctor: ~205 sections (dominant — all footprint, ICT, SharpDX patterns, signal implementations)
- error-doctor: ~78 sections (all CS#### codes, runtime errors, SharpDX crashes, behavioral bugs)
- machine-profile: ~40 sections (state machine, namespace rules, platform specs, instrument specs)
- nt8-expert-wrapper: ~30 sections (DEEP6 deployment, paths, automation, lessons learned)
- nt8-fix-wrapper: ~19 sections (DEEP6 error context, compile detection, fix workflow)
- nt8-new-wrapper: ~13 sections (DEEP6 code gen workflow, namespace conventions)
- nt8-architect: 11 sections (unchanged — 100% DEEP6-specific)
- DISCARD: ~22 sections (agent identity, response protocols)

### Key patterns discovered
- ULTIMATE file is 3 concatenated modules (v3.0 base + Footprint Mastery v1/v2/v3 + Absolute Edition v5.0)
- ~15% content overlap exists — state machine appears in both machine-profile and error-doctor contexts
- SHARED-fundamental sections documented in matrix footer with primary owner noted
- nt8-architect is 100% DEEP6-specific — zero sections discarded or reassigned
- Agent identity/response protocol sections (ROLE & IDENTITY, RESPONSE PROTOCOL, etc.) all DISCARD

### Verification
- All 443 source headers mapped to exactly 443 matrix rows (7/7 source files PASS)
- No double assignments found (PASS)
- Evidence: `.sisyphus/evidence/task-1-coverage-completeness.txt`, `.sisyphus/evidence/task-1-no-double-assignment.txt`

## [2026-05-12] Task: 2 — NT8 Install/Editor Research

### What was built
`.sisyphus/drafts/nt8-install-editor-research.md` — comprehensive universal NT8 knowledge covering installation, uninstallation, clean reinstall, NinjaScript Editor features, keyboard shortcuts, Output Window, workspace management, backup/restore, and data folder structure.

### Key findings
- F5 compiles ALL NinjaScript files into a single DLL — not just the open file. Critical behavior.
- No global hotkey opens the NinjaScript Editor — accessed via New menu or right-click indicator.
- Exclude From Compilation is the key escape hatch when 3rd-party scripts block compilation.
- Documents\NinjaTrader 8\ is NEVER deleted by the uninstaller — must be manually removed or renamed.
- UI.xml rename is the fix for NT8 launch failures due to corrupted window layout.
- Safe Mode (hold Ctrl while launching) isolates 3rd-party add-on issues.
- Cloud backup sync (OneDrive/Dropbox) on the NT8 folder causes file access conflicts — must be excluded.
- Workspace recovery retains 10 versions by default; configurable in Options.

### Verification
- Topic coverage: install=29, uninstall=13, editor=22, F5=5, compile=15, shortcut=10, workspace=29 (ALL PASS)
- Contamination check: CLEAN - 0 matches for DEEP6/C:\Users\Tea/localhost:19206/Sim101
- Evidence: `.sisyphus/evidence/task-2-topic-coverage.txt`, `.sisyphus/evidence/task-2-no-contamination.txt`

## [2026-05-12] Task: 3 — Content Ownership Map

### What was built
`.sisyphus/drafts/nt8-ownership-map.md` — ownership decisions for 12 shared topics across the 3 opencode NT8 skills, plus size estimates per skill.

### Shared topics identified (12 total)
1. State Machine / OnStateChange — DUPLICATE: machine-profile (full), builder-doctor (guards only), error-doctor (SM-001 error version)
2. Namespace Rules — DUPLICATE (partial): machine-profile (full), builder-doctor (via template), error-doctor (cross-ref only)
3. Forbidden C# Patterns — DUPLICATE: machine-profile (runtime constraints ~12 lines), builder-doctor (full forbidden table ~20 lines), error-doctor (symptoms only)
4. OnBarUpdate Guards — DUPLICATE (brief): builder-doctor (full ~25 lines), machine-profile (2-line quick-ref), error-doctor (RT-001/RT-002 entries)
5. Thread Safety — primary-only: builder-doctor (full ~23 lines), machine-profile (2-line note), error-doctor (LG-007 entry)
6. Built-In Indicators — primary-only: builder-doctor only
7. Draw.* Methods — primary-only: builder-doctor only
8. SharpDX Rendering — SPLIT: builder-doctor (patterns), error-doctor (crashes)
9. Property Decoration — primary-only: builder-doctor only
10. Enum Placement Rule — DUPLICATE: builder-doctor (full), error-doctor (3-line note in CS0246)
11. Class Hierarchy — primary-only: machine-profile only
12. Multi-Series Patterns — primary-only: builder-doctor only

### Size estimates (compressed)
- machine-profile: ~18 KB (well under 60KB ceiling)
- builder-doctor: ~50 KB (under ceiling, ~10KB headroom — watch footprint engine verbosity)
- error-doctor: ~40 KB (well under ceiling)

### Key decisions
- State machine appears in all 3 skills but each version serves a different purpose: reference (machine-profile), coding pattern (builder-doctor), error prevention (error-doctor)
- SharpDX split is clean: rendering patterns = builder-doctor, crash database = error-doctor
- builder-doctor is the only skill near the 60KB ceiling — writers should compress footprint engine sections
- Enum placement rule is duplicated in error-doctor as a targeted note within CS0246 (not a separate section) — it's a silent trap

### Verification
- All 6 shared topic patterns found in ownership map (state machine=13, namespace=12, forbidden=13, thread=12, OnBarUpdate=15, Draw.*=13)
- 9 size estimate matches found in ownership map
- Evidence: `.sisyphus/evidence/task-3-shared-topics.txt`, `.sisyphus/evidence/task-3-size-estimates.txt`

## Task 4: ninjatrader-machine-profile upgrade (2026-05-12)

### What was done
- Replaced the DEEP6-specific machine-profile (204 lines, 6.8KB) with a universal NT8 platform knowledge base (23.6KB).
- New file covers: installation, uninstallation, clean reinstall, NinjaScript Editor, compilation, Output Window, keyboard shortcuts, file system, state machine lifecycle, runtime constraints, namespace rules, class hierarchy, calculate modes, bar types, instrument specs, workspace management, backup/restore, connection setup, Control Center navigation.

### QA results
- YAML frontmatter: PASS (name + description with triggers on lines 1-4)
- DEEP6 contamination: CLEAN (0 matches)
- Size: 23.6 KB (PASS, under 30KB ceiling)
- Topic coverage: install=19, uninstall=8, editor=14, NinjaScript Editor=8, F5=5, compile=15 (all present)
- Load-first refs: Match only in YAML description field (required trigger phrase per task spec). Body is clean.

### Key decisions
- "Load FIRST before any NT8 task" kept in YAML description field — this is the required trigger phrase per task spec and ownership map. The QA check pattern catches it but it's a false positive (body is clean).
- State machine section includes full reference table + critical ordering rules code block (~50 lines) per ownership map instruction.
- OnBarUpdate guard quick-ref included as 2-line summary per ownership map; full 5-guard patterns deferred to builder-doctor.
- Thread safety included as 2-line note per ownership map; full WRONG/RIGHT examples deferred to builder-doctor.
- Forbidden patterns included as summary table (no CS codes) per ownership map; full table with CS codes deferred to builder-doctor.
- Instrument specs table included (NQ, MNQ, ES, MES, RTY, CL, GC) per coverage matrix.
- No DEEP6-specific content anywhere in the body.

### Patterns confirmed
- OpenCode skill format: single flat .md file, YAML frontmatter with name + description (triggers in description), then markdown body.
- The YAML description field is the trigger phrase surface — include all relevant trigger phrases there.

## [2026-05-20] Task: DEEP6DaleSetupScanner verification

### NT8 workflow learnings
- `ninjatrader/scripts/nt8-compile.ps1` can timeout on the first automation attempt even with NT8 running; a second foreground + F5 cycle succeeded and updated `NinjaTrader.Custom.dll`.
- For Trader Dale footprint overlays, a hidden `AddVolumetric(..., VolumetricDeltaType.BidAsk, 1)` secondary series compiles clean in NT8 and is a workable way to drive TDOFBars overlays without referencing Trader Dale DLLs.
- QA check for "load first" will always match the description field if the trigger phrase is present — this is expected and acceptable.

## Task 5: ninjatrader-error-doctor upgrade (2026-05-12)

### What was built
Replaced the thin 158-line DEEP6-specific error-doctor (which said "load these files first")
with a comprehensive 59.7KB self-contained NT8 error diagnosis encyclopedia.

### Content coverage
- Master Error Index (compact format: CS####, RT-###, SDX-###, LG-###, MIG-###, SM-###, ENV-###)
- 32 CS compile error codes with broken/fixed code examples
- CS0677 (volatile double) - notorious NT8-specific gotcha - given prominent dedicated section
- CS0246 - deep treatment with 5 root causes including enum-inside-class trap
- CS1501 - master reference with all order/exit/stop/profit/addplot/alert/crossabove overloads
- 17 runtime error entries (RT-001 through RT-017)
- 6 SharpDX crash entries (SDX-001 through SDX-009)
- 7 behavioral/logic error entries (LG-001 through LG-009)
- 4 NT7->NT8 migration errors (MIG-001 through MIG-004)
- 4 state machine errors (SM-001 through SM-004) with complete SM-001 lifecycle code
- 8 environment/deployment errors (ENV-001 through ENV-008)
- Self-debugging arsenal (6 strategies)
- Master Quick-Fix Cheat Sheet (one-liner for every error code)

### QA results
- YAML frontmatter: PASS (name + description with triggers on lines 1-4)
- DEEP6 contamination: CLEAN (0 matches)
- Major CS error codes: CS0101=4, CS0103=3, CS0246=8, CS0677=5, CS1061=3, CS0019=3, CS0029=3 (all present)
- Size: 59.7 KB (PASS, under 60KB ceiling)
- Load-first refs: CLEAN (0 matches)

### Key decisions
- Master Error Index compressed to compact format (saves ~2KB vs verbose list)
- CS0677 (volatile double) given dedicated section - it's a notorious NT8-specific trap
- CS0246 includes enum-inside-class note per ownership map instruction
- CS1501 includes complete overload tables for all order methods, SetStopLoss, SetProfitTarget, AddPlot, Alert, CrossAbove, OnOrderUpdate, OnExecutionUpdate
- SM-001 includes complete state machine lifecycle code (SetDefaults/Configure/DataLoaded/Terminated)
- SDX-004 includes complete bulletproof brush lifecycle pattern
- Self-debugging arsenal compressed to 6 strategies in compact form
- ENV sections trimmed to essential fix steps only

### Patterns confirmed
- 60KB ceiling is tight for this content - requires aggressive compression of verbose sections
- Master Error Index can be compressed to a compact grid format without losing navigability
- The Quick-Fix Cheat Sheet at the bottom is the most valuable single section - preserve it fully
- Error surgeon's 5-second response protocol (classify/diagnose/fix/explain/harden) is gold - kept verbatim

## [2026-05-12] Task: 11 — Coverage Verification

### What was checked
- Sampled 20 matrix sections across the 3 core skills and grep-checked the assigned targets.
- Breakdown: machine-profile 7/7, builder-doctor 7/7, error-doctor 6/6.

### Verification result
- PASS: 20/20 sampled sections found in the correct target skill.
- Evidence: `.sisyphus/evidence/task-11-coverage-verification.txt`

## Task 6: ninjatrader-builder-doctor upgrade (2026-05-12)

### What was built
Replaced the thin 262-line DEEP6-specific builder-doctor (which said "load these files first" and had DEEP6 paths)
with a comprehensive 52.1KB self-contained NinjaScript developer reference.

### Content coverage
- Build Planning Checklist (pre-build decision tree)
- State Machine Quick Reference (6 states, what to do in each)
- Forbidden Patterns table (C# 7.3/.NET 4.8 constraints with CS codes and fixes)
- Complete Indicator Template (compilable, with SharpDX scaffold, properties, generated code region)
- Complete Strategy Template (with all safety defaults)
- Bars & Series API (primary access, Series<T>, ISeries<T> chaining)
- Plots & Lines (AddPlot overloads, PlotStyle, dynamic coloring, AddLine)
- Indicator Properties & Attributes (full decoration reference including brush serialization, enum placement rule)
- Draw.* API Reference (all draw methods with signatures)
- Market Data Events (OnMarketData, OnMarketDepth with DOM ladder pattern)
- Instrument & Session Access (tick size, point value, session iterator)
- Order Management (market/limit/stop, SetStopLoss/SetProfitTarget, OnOrderUpdate/OnExecutionUpdate)
- ATM Strategy Workflow (AtmStrategyCreate, AtmStrategyClose, state queries)
- Account & Performance Access (Account.Get, SystemPerformance, custom optimization metric)
- Multi-Series / Multi-Timeframe (AddDataSeries, BarsInProgress guard, CurrentBars guard)
- SharpDX Rendering (resource lifecycle, brush cache, text rendering, path geometry, gradient brush)
- Threading & Performance (UI thread rules, Dispatcher, Interlocked, hot-path allocation rules)
- Built-In Indicators (full list: MA, volatility, momentum, volume, price)
- Common Patterns & Recipes (IsFirstTickOfBar, bar color, alerts, CrossAbove, session high/low)
- Footprint Chart Engine (tick classification, FootprintBar model, imbalance detection, delta analysis, absorption)
- Volume Profile Engine (full implementation with POC/VAH/VAL calculation)
- Footprint Signal Catalog (delta signals, POC signals, imbalance types - tables)
- Session & Time Utilities (session times, VWAP with stddev bands)
- WPF / UI Integration (Dispatcher pattern for chart controls)
- Optimization & Backtesting (optimizer properties, walk-forward notes)
- Pine Script to NinjaScript Conversion (translation table + workflow)
- Deploy & Compile Loop (generic workflow, F5 behavior, key compile facts)
- Pre-Generation Checklist (18-item checklist)

### QA results
- YAML frontmatter: PASS (name + description with triggers on lines 1-4)
- DEEP6 contamination: CLEAN (0 matches)
- Core topics: OnStateChange=6, OnBarUpdate=18, SharpDX=54, OnRender=13, NinjaScriptProperty=11, AddDataSeries=8, Draw.*=24 (all present)
- Size: 52.1 KB (PASS, under 60KB ceiling, ~8KB headroom)
- Load-first refs: CLEAN (0 matches)
- Forbidden patterns: 6 mentions (PASS, >= 3 required)

### Key decisions
- Enum placement rule preserved verbatim with CRITICAL callout — it's the most notorious NT8 gotcha
- SharpDX section includes full create/dispose lifecycle pattern with brush cache helper
- Footprint engine included as compact but complete implementation (tick classification, FootprintBar, imbalance, delta, absorption, volume profile)
- ICT methodology sections (FVG, Order Block, BOS/ChoCH) dropped per task spec — trading methodology, not NinjaScript API
- Competitor analysis sections dropped — not core NinjaScript API
- Academic theory sections dropped — not core NinjaScript API
- State machine quick-ref included (6 states table) with pointer to machine-profile for full reference
- Threading section includes explicit "OnBarUpdate runs on background thread" warning
- No DEEP6-specific content anywhere in the body
- Generated code region included in indicator template (NT8 requires it)
