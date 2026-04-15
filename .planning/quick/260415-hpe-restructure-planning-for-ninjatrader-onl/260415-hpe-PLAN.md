---
phase: quick-260415-hpe
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/PROJECT.md
  - .planning/ROADMAP.md
  - .planning/REQUIREMENTS.md
  - .planning/STATE.md
autonomous: true
requirements: []
must_haves:
  truths:
    - "PROJECT.md reframes DEEP6 as NinjaScript C# primary with Python as reference-only source-of-truth"
    - "ROADMAP.md tags Phases 1–15 as REFERENCE-ONLY and appends three new phases (17, 18, 19) with full detail"
    - "REQUIREMENTS.md contains an 'Out of Scope (v1 NT8)' section and async-rithmic requirements are annotated with NT8-native substitution note"
    - "STATE.md current focus points at Phase 17 and total_phases is updated to 19"
    - "CLAUDE.md stale items (FlashAlpha as GEX provider) are not propagated — massive.com is referenced where GEX is mentioned in edited files"
    - "No code files are modified; edits are confined to the four planning documents"
  artifacts:
    - path: ".planning/PROJECT.md"
      provides: "NT8-primary project framing with Python reference-only posture and 2026-04-15 pivot context"
      contains: "NinjaScript"
    - path: ".planning/ROADMAP.md"
      provides: "Reference-only tags on Phases 1–15, Phase 16 unchanged, Phase 17/18/19 appended with goal/depends-on/requirements/success criteria/plan outline"
      contains: "Phase 17: NT8 Detector Refactor"
    - path: ".planning/REQUIREMENTS.md"
      provides: "Out of Scope (v1 NT8) block and NT8-native annotations on async-rithmic requirements; historical IDs preserved"
      contains: "Out of Scope (v1 NT8)"
    - path: ".planning/STATE.md"
      provides: "Updated current focus (Phase 17) and total_phases=19"
      contains: "Phase 17"
  key_links:
    - from: ".planning/PROJECT.md"
      to: ".planning/ROADMAP.md"
      via: "consistent framing — both describe NT8 primary + Python reference-only"
      pattern: "NinjaScript|reference-only"
    - from: ".planning/ROADMAP.md"
      to: ".planning/STATE.md"
      via: "Phase 17 entry in roadmap matches current focus in STATE.md"
      pattern: "Phase 17"
    - from: ".planning/phases/16-*/16-CONTEXT.md"
      to: ".planning/ROADMAP.md"
      via: "Phase 17 depends on Phase 16 and ports remaining signals out of the same PORT-SPEC lineage"
      pattern: "Phase 16"
---

<objective>
Restructure the DEEP6 planning corpus to reflect the 2026-04-15 NT8-only pivot. Apex refused to enable Rithmic API/plugin mode, so the Python async-rithmic live-runtime track is shelved. Python engine is retained as the validated reference implementation for signal porting into NinjaScript. Three new phases (17, 18, 19) are added covering detector refactor + remaining signals port, scoring + backtest validation, and a 30-day Apex/Lucid paper-trade gate.

Purpose: Align PROJECT.md, ROADMAP.md, REQUIREMENTS.md, and STATE.md with the new runtime reality before any Phase 17 planning begins, so later /gsd-plan-phase runs operate against correct context.

Output: Four updated markdown files, one atomic commit per task, no code touched.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/STATE.md
@.planning/phases/16-ninjatrader-8-footprint-indicator-standalone-parallel-delive/16-CONTEXT.md
@CLAUDE.md

<notes>
- CLAUDE.md is stale in two places the executor must not replicate: (a) "Python Edition" framing, (b) "GEX data: FlashAlpha API ($49/mo)". The GEX provider is massive.com per project_gex_provider.md memory and Phase 16 context. Do NOT propagate FlashAlpha into edited docs.
- Phase 16 CONTEXT.md is LOCKED — do not modify. Only referenced for continuity language in ROADMAP.
- STATE.md progress counters: Phase 15 stays COMPLETE. total_phases moves from 17 → 19 after Phase 17/18/19 append. completed_phases stays 13 (do not change).
- Phases to tag as [REFERENCE-ONLY — signal logic source for NT8 port, not live runtime]: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 11.1, 11.2, 12, 13, 14, 15. Phase 16 title stays as-is.
- Phase 6 (Kronos E10) is out-of-scope for v1 NT8 — drop from any live-path discussion but keep reference-only tag.
- REQUIREMENTS.md: do NOT delete any requirement IDs. Historical IDs (DATA-*, ABS-*, EXH-*, etc.) remain valid for the Python reference implementation. Only add the Out-of-Scope block and annotate async-rithmic requirements with "NT8 native OnMarketData/OnMarketDepth substitute for NT8-primary track".
- Do NOT create phase directories for 17/18/19. Only ROADMAP entries.
</notes>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rewrite PROJECT.md for NT8-primary framing</name>
  <files>.planning/PROJECT.md</files>
  <action>
    Rewrite PROJECT.md end-to-end preserving structure (What This Is / Core Value / Requirements / Out of Scope / Context / Constraints / Key Decisions / Evolution):

    1. Title: change "# DEEP6 v2.0 — Python Edition" → "# DEEP6 v2.0 — NinjaScript Edition (Python reference-only)".
    2. "What This Is": replace the Python Edition paragraph with: "DEEP6 is an institutional-grade footprint chart auto-trading system for NQ futures, built on NinjaTrader 8 via NinjaScript C#. The validated Python engine (Phases 1–15) is retained as the reference implementation and source-of-truth for signal logic being ported to NinjaScript. Execution runs through NT8 native Rithmic orders on Apex (APEX-262674) and Lucid (LT-45N3KIV8) funded prop accounts. 44 independent market microstructure signals (minus Kronos E10, which is deferred) are synthesized into a unified confidence score. The system's thesis is unchanged: absorption and exhaustion are the highest-alpha reversal signals in order flow — everything else exists to confirm or contextualize them."
    3. "Core Value": "Detect absorption and exhaustion with the highest accuracy of any footprint system ever built, and auto-execute trades from those signals via NT8 Rithmic orders on Apex/Lucid funded accounts — with the Python engine kept as the validated reference specification."
    4. "Requirements > Validated": keep the existing validated bullets; add: "✓ Python reference signal engine validated through Phase 15 (LevelBus + Confluence Rules + Trade Decision FSM, 757 tests green) — Phases 1–15".
    5. "Requirements > Active": replace with the NT8 active list: NinjaScript footprint indicator (Phase 16, built); NT8 detector refactor + remaining 34 signals port (Phase 17); Two-layer confluence scorer in NinjaScript (Phase 18); Replay harness for C#↔Python parity validation (Phase 18); Apex + Lucid 30-day paper-trade gate (Phase 19); massive.com GEX overlay live in NT8 (Phase 16, built); NT8 native OnMarketData + OnMarketDepth aggregation (Phase 16, built); NT8 OrderPlant execution via ATM strategy templates (Phase 19).
    6. "Out of Scope": REMOVE the line "NinjaTrader 8 / C# — replaced by Python + async-rithmic ...". ADD these v1 out-of-scope items: Python as live runtime (reference-only source-of-truth), Kronos E10 bias engine (revisit post-v1), FastAPI backend (reference-only), TradingView MCP (reference-only), Next.js dashboard (reference-only), Databento live feed (reference-only), EventStore (reference-only), async-rithmic live runtime (blocked by Apex refusing API/plugin mode 2026-04-15). Keep existing v1 out-of-scope items (multi-instrument, mobile, social, options execution).
    7. "Context": replace the Python pivot paragraph with a 2026-04-15 NT8 pivot paragraph: "Architecture pivot (2026-04-15): Apex refused to enable Rithmic API/plugin mode on the APEX-262674 user id, blocking the async-rithmic live-runtime track. Committing to a full C# port into NinjaScript running inside NT8. Python engine (Phases 1–15) is preserved as the validated reference specification — all research (44-signal taxonomy, absorption/exhaustion, LVN lifecycle, scoring architecture) carries forward unchanged; only the runtime and language change. Prior 2026-04-13 Python pivot rationale is archived in this doc's history." Keep the 44-signal taxonomy block unchanged. Keep reference implementations block unchanged.
    8. "Constraints": replace with NT8-primary constraints: Language: NinjaScript C# / .NET Framework 4.8 (NT8 8.1.x); Data feed: NT8 native OnMarketData + OnMarketDepth (Rithmic via NT8 connection, not async-rithmic); Execution: NT8 OrderPlant via ATM strategy templates on Apex + Lucid funded accounts; GEX data: massive.com API (MASSIVE_API_KEY in .env — NOT FlashAlpha, CLAUDE.md is stale on that point); Historical data: NT8 Market Replay + recorded tick/depth fixtures; Reference runtime: Python 3.12 engine retained for parity validation, not live; Dashboard: reference-only (Next.js + FastAPI deferred post-v1); Development: NT8 runs on Windows VM / dedicated box; planning and C# authoring on macOS; Research-first workflow preserved.
    9. "Key Decisions": append rows (keep existing rows intact): "Pivot to NT8-only runtime (2026-04-15) — Apex refused Rithmic API/plugin mode — Pending"; "Python engine reference-only — preserve validated Phase 1–15 logic as port source — Pending"; "massive.com for GEX — CLAUDE.md FlashAlpha reference is stale — ✓ Confirmed (live in Phase 16)"; "NT8 execution via ATM strategy templates on Apex + Lucid — funded accounts already active — Pending (Phase 19)"; "Kronos E10 deferred post-v1 — not required for absorption/exhaustion thesis — Pending".
    10. Footer: "*Last updated: 2026-04-15 after NT8 pivot (Apex refused Rithmic API mode)*".

    Use Write tool (file will be fully rewritten). Preserve markdown heading hierarchy from the original document.
  </action>
  <verify>
    <automated>grep -q "NinjaScript Edition" .planning/PROJECT.md &amp;&amp; grep -q "2026-04-15" .planning/PROJECT.md &amp;&amp; grep -q "massive.com" .planning/PROJECT.md &amp;&amp; ! grep -q "FlashAlpha" .planning/PROJECT.md &amp;&amp; grep -q "reference-only" .planning/PROJECT.md</automated>
  </verify>
  <done>PROJECT.md reframed to NT8 primary + Python reference-only, Apex 2026-04-15 pivot documented, massive.com replaces FlashAlpha, NT8 out-of-scope removed from "Out of Scope", new v1-NT8 out-of-scope items listed.</done>
</task>

<task type="auto">
  <name>Task 2: Rewrite ROADMAP.md — tag Phases 1–15 reference-only and append Phases 17/18/19</name>
  <files>.planning/ROADMAP.md</files>
  <action>
    Edit ROADMAP.md in place:

    1. Title: "# Roadmap: DEEP6 v2.0 — Python Edition" → "# Roadmap: DEEP6 v2.0 — NinjaScript Edition (Python reference-only)".

    2. Insert a reference-only banner directly under the title, before "## Overview":
       ```
       > **2026-04-15 pivot — NT8 primary.** Apex refused to enable Rithmic API/plugin mode, shelving the async-rithmic live-runtime track. Phases 1–15 are retained as the **validated Python reference implementation** and source-of-truth for porting signals into NinjaScript. They are NOT the live runtime. Live implementation begins at Phase 16 (NT8 indicator, built) and continues through Phase 19 (paper-trade gate).
       ```

    3. "## Overview": replace with: "DEEP6 v2.0 is built in two tracks. Track A (Phases 1–15) is the validated Python signal engine — reference-only after the 2026-04-15 Apex pivot. Track B (Phases 16–19) is the live NT8 NinjaScript implementation: a footprint indicator with absorption/exhaustion + GEX overlay (Phase 16, built), full signal port and detector refactor (Phase 17), scoring + backtest parity validation (Phase 18), and a 30-day Apex/Lucid paper-trade gate (Phase 19). The absorption/exhaustion thesis, 44-signal taxonomy, LVN lifecycle, and scoring architecture are unchanged — only the runtime and language change."

    4. In the bulleted phase list under "## Phases", prepend "[REFERENCE-ONLY — signal logic source for NT8 port, not live runtime] " to the title of each of: Phase 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 11.1, 11.2, 12, 13, 14, 15. (Phase 16 stays as-is. Do NOT alter the completion checkbox state.)

    5. Under "## Phase Details", for each of Phases 1–15's "### Phase N: <title>" heading, replace with "### Phase N: <title> [REFERENCE-ONLY — signal logic source for NT8 port, not live runtime]". Do not modify the body of these phase detail blocks — only the heading line.

    6. Phase 6 specifically: add a sub-note immediately below its heading: "> Kronos E10 is deferred post-v1 in the NT8 track. Not on the live path."

    7. Phase 16 section: unchanged. Confirm its heading remains intact.

    8. Append new sections at the end of the file after the last existing phase detail block:

       ```
       ### Phase 17: NT8 Detector Refactor + Remaining Signals Port
       **Goal**: DEEP6Footprint.cs monolith split into per-family detector files with an ISignalDetector registry; all 34 remaining signals (IMB-01..09, DELT-01..11, AUCT-01..05, TRAP-01..05, VOLP-01..06, ENG-02..07) ported from the Python reference engine into NinjaScript and firing correctly against the live NT8 Rithmic feed on NQ. Excludes Kronos E10 (deferred post-v1).
       **Depends on**: Phase 16
       **Requirements**: IMB-01..09, DELT-01..11, AUCT-01..05, TRAP-01..05, VOLP-01..06, ENG-02..07
       **Success Criteria** (what must be TRUE):
         1. DEEP6Footprint.cs split into modular files per detector family under `ninjatrader/Custom/Indicators/DEEP6/` and `ninjatrader/Custom/AddOns/DEEP6/`; no single file exceeds 2000 LOC.
         2. `ISignalDetector` interface + detector registry implemented; `EvaluateEntry` iterates the registry — no hardcoded ABS+EXH routing.
         3. All 34 ported signals fire on a live NT8 Rithmic feed bar-for-bar matching the Python reference engine on a recorded session replay, within configured tolerance.
         4. Per-family unit test fixtures committed under `ninjatrader/tests/`.
         5. No regression in the existing 10 signals from Phase 16 (ABS-01..04, ABS-07, EXH-01..06) or the massive.com GEX overlay behavior.
       **Plans** (outline for later /gsd-plan-phase 17): refactor + ISignalDetector interface; IMB detectors; DELT detectors; AUCT + TRAP + VOLP detectors; ENG-02..07 detectors; parity validation harness.

       ### Phase 18: NT8 Scoring + Backtest Validation
       **Goal**: Two-layer confluence scorer ported from Python into NinjaScript with matching weights and thresholds; chart-side per-bar scoring display; manual replay harness validates signal parity and scoring output against the Python reference on ≥5 recorded NQ sessions.
       **Depends on**: Phase 17
       **Requirements**: (NT8 ports of) scoring/confluence requirements from the Python reference engine
       **Success Criteria** (what must be TRUE):
         1. Two-layer confluence scorer (engine agreement + category agreement) implemented in NinjaScript with weights and thresholds matching the Python reference engine.
         2. Zone bonus + narrative cascade wired; signal narrative rendered on chart.
         3. Replay harness consumes recorded tick/depth data and emits per-bar signal + score output.
         4. Parity report: C# vs Python scoring matches within configured tolerance on ≥5 recorded sessions.
         5. TypeA/B/C signal classification visible in strategy logs.
       **Plans** (outline): scorer port; narrative + on-chart display; replay harness; parity report.

       ### Phase 19: Apex/Lucid Paper-Trade Gate
       **Goal**: DEEP6Strategy runs live on Apex (APEX-262674) and Lucid (LT-45N3KIV8) paper/sim accounts for 30 continuous trading days with dry-run disabled (paper mode only); P&L, slippage, fill quality, and risk-gate behavior reviewed; go/no-go decision for live capital documented.
       **Depends on**: Phase 18
       **Requirements**: Risk-management and execution requirements (NT8 substitutes)
       **Success Criteria** (what must be TRUE):
         1. Strategy runs 30 consecutive RTH sessions on both Apex and Lucid paper accounts without crashes or stalls.
         2. Daily P&L log captured with per-signal attribution.
         3. All risk gates (account whitelist, news blackout, daily loss cap, max trades/session, RTH window) verified firing correctly at least once each.
         4. Slippage report: median and 95th-percentile fill slip documented per signal tier.
         5. Written go/no-go decision for live-capital deployment committed to `.planning/`.
       **Plans** (outline): paper-deployment runbook; telemetry + logging; 30-day observation + review; decision doc.
       ```

    9. Update the bulleted phase list at the top to add (after the Phase 16 bullet):
       - [ ] **Phase 17: NT8 Detector Refactor + Remaining Signals Port** - ISignalDetector registry; IMB/DELT/AUCT/TRAP/VOLP/ENG signals ported from Python reference; live NT8 parity
       - [ ] **Phase 18: NT8 Scoring + Backtest Validation** - Two-layer confluence scorer in NinjaScript; replay harness; C#↔Python parity on ≥5 recorded sessions
       - [ ] **Phase 19: Apex/Lucid Paper-Trade Gate** - 30-day paper run on APEX-262674 and LT-45N3KIV8; risk-gate validation; go/no-go decision

    Do NOT create phase directories under .planning/phases/ for 17/18/19.
  </action>
  <verify>
    <automated>grep -q "REFERENCE-ONLY" .planning/ROADMAP.md &amp;&amp; grep -q "Phase 17: NT8 Detector Refactor" .planning/ROADMAP.md &amp;&amp; grep -q "Phase 18: NT8 Scoring" .planning/ROADMAP.md &amp;&amp; grep -q "Phase 19: Apex/Lucid Paper-Trade" .planning/ROADMAP.md &amp;&amp; grep -q "2026-04-15 pivot" .planning/ROADMAP.md &amp;&amp; grep -q "NinjaScript Edition" .planning/ROADMAP.md</automated>
  </verify>
  <done>ROADMAP.md carries the 2026-04-15 NT8 pivot banner, Phases 1–15 tagged REFERENCE-ONLY in both the bullet list and phase detail headings, Phase 6 has a Kronos-deferred note, Phase 16 unchanged, Phases 17/18/19 appended with full goal/depends-on/requirements/success criteria/plan outline.</done>
</task>

<task type="auto">
  <name>Task 3: Update REQUIREMENTS.md with Out-of-Scope block and NT8 substitution annotations</name>
  <files>.planning/REQUIREMENTS.md</files>
  <action>
    Edit REQUIREMENTS.md in place:

    1. Title line: "# Requirements: DEEP6 v2.0 — Python Edition" → "# Requirements: DEEP6 v2.0 — NinjaScript Edition (Python reference-only)".

    2. Directly under the "**Core Value:**" line, insert a new top-level section BEFORE "## v1 Requirements":

       ```
       ## Out of Scope (v1 NT8)

       Following the 2026-04-15 NT8 pivot (Apex refused to enable Rithmic API/plugin mode), the following are explicitly OUT OF SCOPE for v1 of the NT8 track. Historical requirement IDs below remain valid for the Python reference implementation but are not on the live path.

       - **Python as live runtime** — Python engine is reference-only source-of-truth for C# porting
       - **async-rithmic live runtime** — blocked by Apex refusing API/plugin mode; NT8 native Rithmic connection replaces it on the live path
       - **Kronos E10 bias engine** — deferred post-v1; revisit after NT8 paper-trade gate
       - **FastAPI backend** — reference-only; deferred post-v1
       - **TradingView MCP** — reference-only; deferred post-v1
       - **Next.js dashboard** — reference-only; deferred post-v1
       - **Databento live feed** — reference-only; NT8 Market Replay + recorded fixtures used for backtest/parity validation
       - **EventStore** — reference-only; deferred post-v1
       ```

    3. For every requirement whose body text currently references "async-rithmic" as the data source (e.g., DATA-01, DATA-02, and any other async-rithmic-tagged requirement in the file), append the annotation in parentheses at the end of the bullet text:
       `(NT8-primary track: substitute NT8 native OnMarketData / OnMarketDepth for async-rithmic)`
       Do NOT delete the original wording. Do NOT change requirement IDs. Do NOT change checkbox state.

    4. Preserve all existing requirement IDs (DATA-*, ARCH-*, ABS-*, EXH-*, IMB-*, DELT-*, AUCT-*, TRAP-*, VOLP-*, ENG-*, etc.). No deletions.

    5. If the file has a footer "Last updated" line, update it to "2026-04-15 after NT8 pivot". If not, append one.

    Use Read first to scan the full 437-line file (reading in two passes if needed: offset 0 limit 250, offset 250 limit 200) to identify every async-rithmic reference before editing.
  </action>
  <verify>
    <automated>grep -q "Out of Scope (v1 NT8)" .planning/REQUIREMENTS.md &amp;&amp; grep -q "NT8-primary track" .planning/REQUIREMENTS.md &amp;&amp; grep -q "NinjaScript Edition" .planning/REQUIREMENTS.md &amp;&amp; grep -qE "DATA-01.*async-rithmic" .planning/REQUIREMENTS.md &amp;&amp; grep -q "2026-04-15" .planning/REQUIREMENTS.md</automated>
  </verify>
  <done>REQUIREMENTS.md has the Out-of-Scope (v1 NT8) section, all async-rithmic requirements carry the NT8-native substitution annotation, all historical IDs preserved, no deletions made.</done>
</task>

<task type="auto">
  <name>Task 4: Update STATE.md current focus + total_phases, then commit all four files</name>
  <files>.planning/STATE.md</files>
  <action>
    Edit STATE.md in place:

    1. Frontmatter:
       - `stopped_at:` → "Phase 16 COMPLETE — NT8 indicator + strategy shell; next Phase 17 detector refactor"
       - `last_updated:` → today's ISO timestamp (2026-04-15T...)
       - `last_activity:` → 2026-04-15
       - `progress.total_phases:` 17 → 19
       - Leave `completed_phases: 13` untouched (Phase 15 stays COMPLETE; Phase 16 is built but not marked closed here per user direction — if reader is uncertain, leave unchanged)
       - Recompute `percent:` using `round(completed_phases / total_phases * 100)` → 13/19 = 68. Update `percent: 68`.

    2. Body, "## Project Reference" block:
       - Replace the Core value line with: "**Core value:** Detect absorption and exhaustion with the highest accuracy of any footprint system ever built, and auto-execute trades via NT8 Rithmic orders on Apex + Lucid funded accounts — with the Python engine preserved as the validated reference specification."
       - Replace the Current focus line with: "**Current focus:** Phase 16 built (NT8 indicator + strategy shell with 10/44 signals). Next: Phase 17 — NT8 detector refactor + remaining signals port."

    3. "## Current Position":
       - `Phase: 15` → `Phase: 17 (next)`
       - `Plan: Complete (5/5)` → `Plan: none yet — /gsd-plan-phase 17 pending`
       - `Status:` → "2026-04-15 NT8 pivot: Phases 1–15 reclassified REFERENCE-ONLY (Python reference engine); Phase 16 built; Phase 17/18/19 appended to roadmap."
       - Keep the "Last activity" bullet; add a new bullet: "2026-04-15 - Restructured planning docs for NT8-only pivot after Apex refused Rithmic API/plugin mode"
       - Progress bar: recompute to match 68% (e.g., `[██████▊░░░] 68%`)

    4. "### Roadmap Evolution": append two bullets:
       - "Phase 17 added: NT8 Detector Refactor + Remaining Signals Port — ISignalDetector registry, port IMB/DELT/AUCT/TRAP/VOLP/ENG signals from Python reference engine to NinjaScript, live NT8 parity"
       - "Phase 18 added: NT8 Scoring + Backtest Validation — two-layer confluence scorer in NinjaScript, replay harness, ≥5-session parity vs Python reference"
       - "Phase 19 added: Apex/Lucid Paper-Trade Gate — 30-day paper run on APEX-262674 and LT-45N3KIV8, risk-gate validation, go/no-go decision"
       - "Architecture pivot superseded (2026-04-15): Python + async-rithmic live runtime shelved — Apex refused API/plugin mode. NT8 NinjaScript is now primary; Python engine reference-only."

    5. "### Blockers/Concerns": add: "- [2026-04-15]: Apex refused API/plugin mode on APEX-262674 — async-rithmic live-runtime track unblocked only if Apex reverses or user migrates to a broker that supports API mode (EdgeClear, Tradovate via Rithmic, AMP Futures per CLAUDE.md)."

    After STATE.md write completes, commit all four modified planning files in a single atomic commit:
    ```
    git add .planning/PROJECT.md .planning/ROADMAP.md .planning/REQUIREMENTS.md .planning/STATE.md
    git commit -m "docs(planning): restructure for NT8-only pivot after Apex refused Rithmic API mode"
    ```
    Do NOT use `git add -A`. Do NOT touch any other files.
  </action>
  <verify>
    <automated>grep -q "total_phases: 19" .planning/STATE.md &amp;&amp; grep -q "Phase 17" .planning/STATE.md &amp;&amp; grep -q "NT8 pivot" .planning/STATE.md &amp;&amp; git log -1 --pretty=%s | grep -q "NT8-only pivot" &amp;&amp; git diff HEAD~1 --name-only | sort | diff - <(printf ".planning/PROJECT.md\n.planning/REQUIREMENTS.md\n.planning/ROADMAP.md\n.planning/STATE.md\n")</automated>
  </verify>
  <done>STATE.md reflects Phase 17 as current focus, total_phases=19, percent recomputed, Roadmap Evolution and Blockers updated; single atomic commit covers exactly the four planning files with no stray files.</done>
</task>

</tasks>

<verification>
After all four tasks complete:

1. All four files show the 2026-04-15 NT8 pivot framing consistently (no residual "Python Edition" in titles).
2. No instance of "FlashAlpha" has been introduced into any edited doc (CLAUDE.md staleness not propagated).
3. Phases 1–15 carry REFERENCE-ONLY tags in ROADMAP.md; Phase 16 unchanged; Phases 17/18/19 appended with all required fields.
4. REQUIREMENTS.md retains every original requirement ID; only additions made.
5. STATE.md numeric counters are internally consistent (completed/total/percent).
6. Git log shows a single new commit touching exactly these four files.
7. No files created under .planning/phases/ for 17/18/19.
8. No code files touched anywhere in the repo (`git diff HEAD~1 --stat` shows only the four .planning/*.md files).
</verification>

<success_criteria>
- PROJECT.md reframed (NT8 primary, Python reference-only, massive.com GEX, 2026-04-15 pivot documented).
- ROADMAP.md tagged and extended (Phases 1–15 REFERENCE-ONLY, Phases 17/18/19 appended with full detail).
- REQUIREMENTS.md annotated (Out-of-Scope v1 NT8 block added, async-rithmic requirements carry NT8-native substitution notes, all IDs preserved).
- STATE.md updated (current focus Phase 17, total_phases 19, percent recomputed, Roadmap Evolution entries added, Apex blocker recorded).
- One atomic commit: `docs(planning): restructure for NT8-only pivot after Apex refused Rithmic API mode`.
</success_criteria>

<output>
After completion, the parent /gsd-quick orchestrator handles summary emission. No SUMMARY.md is required for a quick task of this type unless the orchestrator requests it.
</output>
