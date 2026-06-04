# NT8 Skills Upgrade — Comprehensive Knowledge Consolidation

## TL;DR

> **Quick Summary**: Upgrade 3 opencode NinjaTrader skills from thin shells into comprehensive, self-contained NT8 developer knowledge bases by absorbing 14,000+ lines of existing source material. Refactor 4 project skills into thin DEEP6-specific wrappers.
> 
> **Deliverables**:
> - 3 upgraded opencode skills (machine-profile, builder-doctor, error-doctor)
> - 4 refactored project skill wrappers (nt8-expert, nt8-fix, nt8-new, nt8-architect)
> - Coverage matrix verifying zero knowledge loss
> - Source files archived with canonical-source-moved notices
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 3 waves
> **Critical Path**: Coverage Matrix → machine-profile → error-doctor/builder-doctor (parallel) → project wrappers (parallel) → verification

---

## Context

### Original Request
User wants both opencode-level and project-level NinjaTrader skills upgraded. The opencode skills should become comprehensive NT8 developer education covering: installing/uninstalling NT8, fixing all types of errors, the NinjaScript Editor, and building indicators and strategies. Project skills should become thin DEEP6-specific wrappers.

### Interview Summary
**Key Discussions**:
- User chose to keep 3 opencode skills and expand each (not split into 4 or consolidate into 2)
- Machine-profile gets install/uninstall/editor coverage
- Builder-doctor absorbs the 10,433-line ULTIMATE-NINJASCRIPT-AGENT knowledge
- Error-doctor absorbs the 3,318-line Error Surgeon knowledge
- Project skills become thin local wrappers with DEEP6-specific paths/configs only

**Research Findings**:
- Source material totals ~14,000 lines across 3 large knowledge base files
- Current opencode skills are ~620 lines combined (thin shells with "load these files first")
- Current project skills are ~51KB combined, with 20-100% DEEP6-specific content depending on skill
- Existing opencode skill format: single flat .md file with YAML frontmatter, largest existing is 23.3KB
- ~15-20% content overlap across source files (state machine, namespace rules, forbidden patterns)

### Metis Review
**Identified Gaps** (addressed):
- Token budget per skill: Applied 50KB target ceiling per skill (builder-doctor may be largest at ~60KB)
- Source file disposition: Archive with "canonical source moved" notice
- Self-contained definition: Each skill contains all domain knowledge; may reference other opencode skills by name for shared fundamentals
- Shared content ownership: machine-profile owns fundamentals (state machine, namespaces); duplication allowed for critical items (forbidden patterns, guards)
- nt8-architect: 100% DEEP6-specific, stays as-is (explicit exemption)
- Install/uninstall content: Not in any source file — executor must research NT8 official docs and synthesize new content for machine-profile

---

## Work Objectives

### Core Objective
Transform the NinjaTrader skill architecture from "thin shells referencing external files" into "comprehensive self-contained knowledge bases" at the opencode level, with project skills providing only DEEP6-specific local context.

### Concrete Deliverables
- `~/.config/opencode/skills/ninjatrader-machine-profile.md` — Expanded with NT8 platform knowledge, installation, editor, paths
- `~/.config/opencode/skills/ninjatrader-builder-doctor.md` — Comprehensive NinjaScript development knowledge
- `~/.config/opencode/skills/ninjatrader-error-doctor.md` — Complete error diagnosis encyclopedia
- `.claude/skills/nt8-expert/` — Thinned to DEEP6-specific paths, scripts, deployment only
- `.claude/skills/nt8-fix/` — Thinned to DEEP6-specific error context only
- `.claude/skills/nt8-new/` — Thinned to DEEP6-specific code generation context only
- `.claude/skills/nt8-architect/` — Unchanged (100% DEEP6-specific already)
- Coverage matrix mapping every source section to exactly one target skill

### Definition of Done
- [ ] All 3 opencode skills load correctly when invoked by name
- [ ] Zero DEEP6-specific content in opencode skills (grep verified)
- [ ] Zero universal NT8 knowledge remaining in project wrappers (spot-check verified)
- [ ] Coverage matrix shows 100% of source sections accounted for
- [ ] Each skill has valid YAML frontmatter with updated trigger phrases
- [ ] Each opencode skill under 60KB size ceiling

### Must Have
- Complete NinjaScript development knowledge in builder-doctor (runtime model, patterns, SharpDX, strategies, threading)
- Complete error diagnosis knowledge in error-doctor (every CS error, runtime exceptions, SharpDX crashes, behavioral bugs)
- NT8 platform knowledge in machine-profile (installation, editor, paths, environment)
- Self-contained skills — no "load this file first" instructions
- Project wrappers with explicit cross-references to opencode skills

### Must NOT Have (Guardrails)
- **No DEEP6-specific content in opencode skills**: Zero references to DEEP6 files, paths, namespaces, localhost:19206, C:\Users\Tea\, Sim101, ATM templates
- **No universal NT8 knowledge in project wrappers**: CS error explanations, API patterns, state machine patterns belong in opencode skills only
- **No copy-paste from source files**: Content must be synthesized/compressed for skill format — concise, actionable, tables over prose
- **No new NT8 knowledge invented**: All content traces to source files (exception: install/uninstall researched from official docs)
- **No 4th opencode skill**: Keep exactly 3
- **No project skill directory restructuring**: Only content changes, not file/folder structure
- **No CLAUDE.md updates**: Separate task, out of scope

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: N/A (markdown files, not code)
- **Automated tests**: None — verification via grep, file size, and content checks
- **Framework**: PowerShell commands for grep and size validation

### QA Policy
Every task includes agent-executed QA scenarios. Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Content verification**: PowerShell Select-String and Get-Item for grep/size checks
- **Structure verification**: Head-of-file reads to verify YAML frontmatter
- **Cross-contamination checks**: Grep for forbidden patterns in wrong locations

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — must complete first):
├── Task 1: Build coverage matrix [writing]
├── Task 2: Research NT8 installation/editor content [librarian]
└── Task 3: Analyze content overlap and ownership map [explore + writing]

Wave 2 (Core Skills — MAX PARALLEL after Wave 1):
├── Task 4: Write ninjatrader-machine-profile (depends: 1, 2, 3) [writing]
├── Task 5: Write ninjatrader-error-doctor (depends: 1, 3) [writing]
└── Task 6: Write ninjatrader-builder-doctor (depends: 1, 3) [writing]

Wave 3 (Wrappers + Cleanup — after Wave 2):
├── Task 7: Refactor nt8-expert project skill (depends: 4) [quick]
├── Task 8: Refactor nt8-fix project skill (depends: 5) [quick]
├── Task 9: Refactor nt8-new project skill (depends: 6) [quick]
├── Task 10: Archive source files with notices (depends: 4, 5, 6) [quick]
└── Task 11: Verify coverage matrix completeness (depends: 4, 5, 6) [quick]

Wave FINAL (After ALL tasks — verification):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Content quality review (unspecified-high)
├── Task F3: Cross-contamination QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 4, 5, 6 | 1 |
| 2 | — | 4 | 1 |
| 3 | — | 4, 5, 6 | 1 |
| 4 | 1, 2, 3 | 7, 10 | 2 |
| 5 | 1, 3 | 8, 10 | 2 |
| 6 | 1, 3 | 9, 10 | 2 |
| 7 | 4 | — | 3 |
| 8 | 5 | — | 3 |
| 9 | 6 | — | 3 |
| 10 | 4, 5, 6 | — | 3 |
| 11 | 4, 5, 6 | — | 3 |
| F1-F4 | 7-11 | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: 3 tasks — T1 → `writing`, T2 → `librarian` via task, T3 → `writing`
- **Wave 2**: 3 tasks — T4 → `writing`, T5 → `writing`, T6 → `writing`
- **Wave 3**: 5 tasks — T7-T9 → `quick`, T10 → `quick`, T11 → `quick`
- **FINAL**: 4 tasks — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Build Coverage Matrix

  **What to do**:
  - Read all 3 source knowledge base files: `dashboard/agents/ULTIMATE-NINJASCRIPT-AGENT-v5.md` (10,433 lines), `dashboard/agents/ninjascript-error-surgeon-v2.md` (3,318 lines), `ninjatrader/ninjascript-ai-context.md` (389 lines)
  - Read all 4 project skill knowledge files: `nt8-expert/knowledge.md`, `nt8-fix/knowledge.md`, `nt8-new/knowledge.md`, `nt8-architect/architecture.md`
  - Extract every H2/H3 section header from ALL source files
  - For each section, classify: (a) universal NT8 knowledge → assign to exactly one opencode skill, (b) DEEP6-specific → assign to project wrapper, (c) overlap → designate primary owner + note duplication
  - Map each section to exactly one of: `machine-profile`, `builder-doctor`, `error-doctor`, `nt8-expert-wrapper`, `nt8-fix-wrapper`, `nt8-new-wrapper`, `nt8-architect` (unchanged), or `DISCARD` (if redundant/obsolete)
  - Save the coverage matrix as `.sisyphus/drafts/nt8-coverage-matrix.md`

  **Must NOT do**:
  - Write any skill files yet — this is mapping only
  - Invent sections not present in sources
  - Assign the same section to multiple targets (except explicitly noted shared fundamentals)

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Analytical reading and structured documentation output
  - **Skills**: []
    - No domain skills needed — this is pure content analysis
  - **Skills Evaluated but Omitted**:
    - `nt8-expert`: Not needed — reading source files directly, not operating NT8

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 2, 3)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 4, 5, 6
  - **Blocked By**: None

  **References**:

  **Source Files to Analyze**:
  - `dashboard/agents/ULTIMATE-NINJASCRIPT-AGENT-v5.md` — Full 10,433-line NinjaScript developer encyclopedia; every H2/H3 must be mapped
  - `dashboard/agents/ninjascript-error-surgeon-v2.md` — Full 3,318-line error database; every error tier and code must be mapped
  - `ninjatrader/ninjascript-ai-context.md` — 389-line verified constraints file; every section must be mapped
  - `.claude/skills/nt8-expert/knowledge.md` — 449-line operations knowledge; separate DEEP6-specific from universal
  - `.claude/skills/nt8-expert/scripts.md` — Script documentation; classify as DEEP6-specific
  - `.claude/skills/nt8-fix/knowledge.md` — 250-line error knowledge; separate DEEP6-specific from universal
  - `.claude/skills/nt8-new/knowledge.md` — 259-line code gen knowledge; separate DEEP6-specific from universal
  - `.claude/skills/nt8-architect/architecture.md` — 135-line architecture; 100% DEEP6-specific, leave as-is

  **Target Skill Assignments** (guidelines):
  - `machine-profile` owns: NT8 platform, installation, editor, paths, environment, state machine lifecycle, namespace rules
  - `builder-doctor` owns: NinjaScript development patterns, indicators, strategies, SharpDX rendering, properties, data series, Draw.* methods, order flow implementation, threading for development
  - `error-doctor` owns: Every CS error code, runtime exceptions, SharpDX crashes, behavioral bugs, NT7→NT8 migration, threading errors, deployment errors

  **WHY Each Reference Matters**:
  - This matrix is the single source of truth for all subsequent tasks — every task references it to know what sections to include/exclude

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Coverage completeness — no source section left unmapped
    Tool: Bash (PowerShell)
    Preconditions: Coverage matrix file exists at .sisyphus/drafts/nt8-coverage-matrix.md
    Steps:
      1. Extract all H2 (##) headers from ULTIMATE-NINJASCRIPT-AGENT-v5.md: `Select-String -Path "dashboard\agents\ULTIMATE-NINJASCRIPT-AGENT-v5.md" -Pattern "^## " | Measure-Object`
      2. Count rows in coverage matrix that reference ULTIMATE: `Select-String -Path ".sisyphus\drafts\nt8-coverage-matrix.md" -Pattern "ULTIMATE" | Measure-Object`
      3. Assert: matrix rows >= source H2 count (every section mapped)
    Expected Result: Coverage matrix has at least as many ULTIMATE entries as the source has H2 headers
    Failure Indicators: Matrix row count < source header count
    Evidence: .sisyphus/evidence/task-1-coverage-completeness.txt

  Scenario: No section assigned to multiple targets
    Tool: Bash (PowerShell)
    Preconditions: Coverage matrix exists
    Steps:
      1. Read coverage matrix
      2. Extract the "Target" column
      3. For each source section row, verify exactly one target is listed (not comma-separated or "both")
    Expected Result: Zero rows with multiple target assignments (except rows explicitly marked "SHARED-fundamental")
    Evidence: .sisyphus/evidence/task-1-no-double-assignment.txt
  ```

  **Evidence to Capture:**
  - [ ] task-1-coverage-completeness.txt — header counts from each source vs matrix row counts
  - [ ] task-1-no-double-assignment.txt — validation output

  **Commit**: NO (draft artifact, not deliverable)

- [x] 2. Research NT8 Installation/Editor Content

  **What to do**:
  - Research NinjaTrader 8 installation procedures from official documentation (use ninjatrader-autodocs MCP and/or web search)
  - Cover: downloading NT8, system requirements, installation steps, license activation, uninstallation, clean reinstall procedures
  - Research NinjaScript Editor features: how to open it, editor panes, code completion, compile button, Output Window, error navigation, keyboard shortcuts, editor settings
  - Research NT8 workspace management: creating workspaces, importing/exporting, backup procedures
  - Save findings as `.sisyphus/drafts/nt8-install-editor-research.md`
  - Format as concise, actionable content ready to be incorporated into machine-profile skill

  **Must NOT do**:
  - Include any DEEP6-specific content
  - Write the actual skill file — this is research only
  - Include trading methodology or signal content

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Research task requiring web/doc search and synthesis
  - **Skills**: [`ninjatrader-machine-profile`]
    - `ninjatrader-machine-profile`: Provides current machine-profile context to understand what's already covered vs what's missing
  - **Skills Evaluated but Omitted**:
    - `ninjatrader-builder-doctor`: Not relevant to installation/editor research

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 3)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 4
  - **Blocked By**: None

  **References**:

  **Existing Content to Review**:
  - `~/.config/opencode/skills/ninjatrader-machine-profile.md` — Current machine-profile to understand what's already there (paths, scripts, settings)
  - `ninjatrader/WINDOWS-SETUP-HANDOFF.md` — May contain installation-adjacent content (copy files, compile, add indicators)

  **External Sources to Query**:
  - NinjaTrader official docs via ninjatrader-autodocs MCP or web search
  - NinjaTrader 8 help center for installation and editor documentation

  **WHY Each Reference Matters**:
  - Machine-profile shows what exists; the gap is installation/editor — research fills it
  - WINDOWS-SETUP-HANDOFF may have partial installation content to not duplicate

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Research covers all required topics
    Tool: Bash (PowerShell)
    Preconditions: Research file exists at .sisyphus/drafts/nt8-install-editor-research.md
    Steps:
      1. Verify file contains section on installation: `Select-String -Path ".sisyphus\drafts\nt8-install-editor-research.md" -Pattern "install" -CaseSensitive:$false | Measure-Object`
      2. Verify file contains section on uninstallation: `Select-String -Pattern "uninstall" -CaseSensitive:$false`
      3. Verify file contains section on NinjaScript Editor: `Select-String -Pattern "editor|Editor"`
      4. Verify file contains section on keyboard shortcuts: `Select-String -Pattern "shortcut|keyboard|F5"`
    Expected Result: All 4 topic searches return at least 1 match
    Failure Indicators: Any topic search returns 0 matches
    Evidence: .sisyphus/evidence/task-2-topic-coverage.txt

  Scenario: No DEEP6 contamination in research
    Tool: Bash (PowerShell)
    Preconditions: Research file exists
    Steps:
      1. `Select-String -Path ".sisyphus\drafts\nt8-install-editor-research.md" -Pattern "DEEP6|C:\\Users\\Tea|localhost:19206|Sim101"`
    Expected Result: 0 matches
    Evidence: .sisyphus/evidence/task-2-no-contamination.txt
  ```

  **Evidence to Capture:**
  - [ ] task-2-topic-coverage.txt — grep results for required topics
  - [ ] task-2-no-contamination.txt — grep results for forbidden patterns

  **Commit**: NO (draft artifact, not deliverable)

- [x] 3. Analyze Content Overlap and Build Ownership Map

  **What to do**:
  - Read all 3 source knowledge base files focusing on sections that appear in multiple files
  - Identify shared/overlapping content: state machine (OnStateChange lifecycle), namespace rules, forbidden patterns (C# 7.3/.NET 4.8 constraints), OnBarUpdate guards, built-in indicator list, Draw.* methods, thread safety rules
  - For each shared topic, designate a PRIMARY OWNER skill and decide: (a) include in primary only (others cross-reference), or (b) include in multiple skills (accept token duplication for self-containment)
  - Estimate compressed size of each skill based on section assignments from Task 1
  - Save ownership map as `.sisyphus/drafts/nt8-ownership-map.md` with: topic → primary owner → duplication decision → estimated size contribution

  **Must NOT do**:
  - Write any skill files
  - Change the 3-skill structure
  - Add new topics not in source files

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Analytical comparison and documentation task
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - All NT8 skills: Not needed for content analysis

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 2)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 4, 5, 6
  - **Blocked By**: None

  **References**:

  **Source Files to Compare**:
  - `dashboard/agents/ULTIMATE-NINJASCRIPT-AGENT-v5.md` — Primary source for builder-doctor content; search for sections that also appear in error-surgeon or ai-context
  - `dashboard/agents/ninjascript-error-surgeon-v2.md` — Primary source for error-doctor content; check for builder-overlap (e.g., "runtime model" sections)
  - `ninjatrader/ninjascript-ai-context.md` — Compact constraints file; content here likely appears in both other files
  - `.claude/skills/nt8-new/knowledge.md` — 80% universal content; determine which opencode skill absorbs each section

  **Ownership Guidelines**:
  - State machine / OnStateChange lifecycle → `machine-profile` (it's platform fundamentals)
  - Namespace rules → `machine-profile`
  - Forbidden patterns (C# 7.3 constraints) → `builder-doctor` (development context)
  - Thread safety → `builder-doctor` (development pattern)
  - CS error taxonomy → `error-doctor` exclusively
  - Draw.* methods → `builder-doctor`
  - OnBarUpdate guards → `builder-doctor`

  **WHY Each Reference Matters**:
  - Overlap analysis prevents duplication bloat and ensures the 60KB ceiling is achievable
  - Ownership map is the contract each writing task follows

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Ownership map covers all identified shared topics
    Tool: Bash (PowerShell)
    Preconditions: Ownership map exists at .sisyphus/drafts/nt8-ownership-map.md
    Steps:
      1. Verify file contains entries for known shared topics: `Select-String -Path ".sisyphus\drafts\nt8-ownership-map.md" -Pattern "state machine|namespace|forbidden|thread|OnBarUpdate|Draw\." | Measure-Object`
    Expected Result: At least 5 shared topics documented with ownership decisions
    Evidence: .sisyphus/evidence/task-3-shared-topics.txt

  Scenario: Size estimates are present and under ceiling
    Tool: Bash (PowerShell)
    Preconditions: Ownership map exists
    Steps:
      1. `Select-String -Path ".sisyphus\drafts\nt8-ownership-map.md" -Pattern "estimated.*KB|~.*KB|size.*KB"`
    Expected Result: At least 3 size estimates present (one per opencode skill); none exceeds 60KB
    Evidence: .sisyphus/evidence/task-3-size-estimates.txt
  ```

  **Evidence to Capture:**
  - [ ] task-3-shared-topics.txt — shared topic coverage check
  - [ ] task-3-size-estimates.txt — size estimate validation

  **Commit**: NO (draft artifact, not deliverable)

- [x] 4. Write Upgraded ninjatrader-machine-profile Skill

  **What to do**:
  - Read the coverage matrix (Task 1) to identify all sections assigned to `machine-profile`
  - Read the installation/editor research (Task 2) for new content
  - Read the ownership map (Task 3) for shared content decisions
  - Read the current machine-profile skill at `~/.config/opencode/skills/ninjatrader-machine-profile.md`
  - Write the new comprehensive machine-profile skill covering:
    - **NT8 Platform Overview**: What NinjaTrader 8 is, .NET 4.8 runtime, C# 7.3 constraints
    - **Installation & Setup**: Download, system requirements, install steps, license activation, test vs live environments
    - **Uninstallation & Clean Reinstall**: Complete removal, registry cleanup, fresh install
    - **NinjaScript Editor**: How to open, panes, code completion, compile (F5/F7), Output Window, error navigation, keyboard shortcuts
    - **NT8 File System**: Custom folder structure, namespace-to-folder mapping, how NT8 compiles all custom code into single DLL
    - **NinjaScript Lifecycle**: OnStateChange state machine (SetDefaults → Configure → DataLoaded → Historical → Realtime → Terminated)
    - **Namespace Rules**: Standard NT8 namespaces, subfolder conventions
    - **Workspace & Configuration**: Creating workspaces, templates, import/export
    - **Generic Paths**: Standard NT8 installation paths (not machine-specific), Custom folder location pattern, DLL location, log location
    - **Connection Types**: Data feeds, order routing, simulation vs live
  - Write as self-contained .md file with YAML frontmatter
  - Save to `~/.config/opencode/skills/ninjatrader-machine-profile.md` (overwrites current)
  - Target size: 15-25KB (this is the smallest of the 3 skills — platform knowledge, not development reference)

  **Must NOT do**:
  - Include ANY DEEP6-specific content (no C:\Users\Tea, no DEEP6 files, no Sim101, no ATM templates, no localhost:19206)
  - Include NinjaScript development patterns (that's builder-doctor)
  - Include error diagnosis content (that's error-doctor)
  - Include "load this file first" references
  - Exceed 30KB file size

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Technical documentation writing from synthesized research
  - **Skills**: [`ninjatrader-machine-profile`]
    - `ninjatrader-machine-profile`: Load current skill to understand format and existing content being replaced
  - **Skills Evaluated but Omitted**:
    - `ninjatrader-builder-doctor`: Development patterns not relevant to platform skill

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 5, 6)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 7, 10
  - **Blocked By**: Tasks 1, 2, 3

  **References**:

  **Input Sources**:
  - `.sisyphus/drafts/nt8-coverage-matrix.md` — Which sections from source files are assigned to machine-profile
  - `.sisyphus/drafts/nt8-install-editor-research.md` — Installation and editor content researched in Task 2
  - `.sisyphus/drafts/nt8-ownership-map.md` — Shared content ownership decisions
  - `~/.config/opencode/skills/ninjatrader-machine-profile.md` — Current skill file being replaced (read for format reference)

  **Content Sources (assigned sections only)**:
  - `dashboard/agents/ULTIMATE-NINJASCRIPT-AGENT-v5.md` — Sections on runtime model, state machine, namespace rules (as identified in coverage matrix)
  - `ninjatrader/ninjascript-ai-context.md` — Runtime constraints, namespace rules sections
  - `.claude/skills/nt8-expert/knowledge.md` — Universal NT8 path patterns, folder rules, compilation model (not DEEP6-specific parts)

  **Format Reference**:
  - `~/.config/opencode/skills/imagegen.md` — Largest existing opencode skill (23.3KB) for format/structure reference

  **WHY Each Reference Matters**:
  - Coverage matrix tells you exactly which sections to include — do not deviate
  - Installation research provides the new content not available in any existing source
  - Current skill shows the YAML frontmatter format to preserve

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: YAML frontmatter is valid
    Tool: Bash (PowerShell)
    Preconditions: Skill file written to ~/.config/opencode/skills/ninjatrader-machine-profile.md
    Steps:
      1. `$lines = Get-Content "$env:USERPROFILE\.config\opencode\skills\ninjatrader-machine-profile.md" -TotalCount 5`
      2. Assert $lines[0] equals "---"
      3. Assert $lines[1] starts with "name:"
      4. Assert $lines[2] starts with "description:" and contains trigger phrases
      5. Assert $lines[3] equals "---"
    Expected Result: All 4 assertions pass
    Evidence: .sisyphus/evidence/task-4-frontmatter.txt

  Scenario: Zero DEEP6 contamination
    Tool: Bash (PowerShell)
    Steps:
      1. `Select-String -Path "$env:USERPROFILE\.config\opencode\skills\ninjatrader-machine-profile.md" -Pattern "DEEP6|C:\\Users\\Tea|localhost:19206|Sim101|DEEP6Signal|DEEP6Footprint|DEEP6Strategy|DEEP6DevAddon"`
    Expected Result: 0 matches
    Evidence: .sisyphus/evidence/task-4-no-contamination.txt

  Scenario: Size under ceiling
    Tool: Bash (PowerShell)
    Steps:
      1. `$size = (Get-Item "$env:USERPROFILE\.config\opencode\skills\ninjatrader-machine-profile.md").Length / 1KB; Write-Output "Size: $([math]::Round($size, 1)) KB"`
    Expected Result: Size under 30KB
    Evidence: .sisyphus/evidence/task-4-size.txt

  Scenario: Covers installation and editor topics
    Tool: Bash (PowerShell)
    Steps:
      1. `Select-String -Path "$env:USERPROFILE\.config\opencode\skills\ninjatrader-machine-profile.md" -Pattern "install|uninstall|editor|NinjaScript Editor|F5|compile" -CaseSensitive:$false | Measure-Object`
    Expected Result: At least 5 matches across installation/editor content
    Evidence: .sisyphus/evidence/task-4-topic-coverage.txt

  Scenario: No "load this file first" references
    Tool: Bash (PowerShell)
    Steps:
      1. `Select-String -Path "$env:USERPROFILE\.config\opencode\skills\ninjatrader-machine-profile.md" -Pattern "must read|load first|Required Context to Load|read these before"`
    Expected Result: 0 matches
    Evidence: .sisyphus/evidence/task-4-no-load-refs.txt
  ```

  **Evidence to Capture:**
  - [ ] task-4-frontmatter.txt, task-4-no-contamination.txt, task-4-size.txt, task-4-topic-coverage.txt, task-4-no-load-refs.txt

  **Commit**: YES
  - Message: `docs(skills): upgrade ninjatrader-machine-profile to comprehensive NT8 platform skill`
  - Files: `~/.config/opencode/skills/ninjatrader-machine-profile.md`

- [x] 5. Write Upgraded ninjatrader-error-doctor Skill

  **What to do**:
  - Read the coverage matrix (Task 1) to identify all sections assigned to `error-doctor`
  - Read the ownership map (Task 3) for shared content decisions
  - Read the current error-doctor skill at `~/.config/opencode/skills/ninjatrader-error-doctor.md`
  - Read the PRIMARY source: `dashboard/agents/ninjascript-error-surgeon-v2.md` (3,318 lines)
  - Read SECONDARY sources: `nt8-fix/knowledge.md` (universal error patterns only), `ninjascript-ai-context.md` (forbidden patterns section)
  - **Synthesize, don't copy**: Compress the 3,318-line error surgeon into the skill format:
    - Keep the master error index (quick lookup table)
    - Keep every CS error code with: root cause, broken-vs-fixed code example (one example per error, not multiple), one-line explanation
    - Keep runtime exception patterns with: trigger, fix, guard
    - Keep SharpDX crash patterns
    - Keep behavioral bug patterns
    - Keep the 5-second response protocol (classify → diagnose → fix → explain → harden)
    - Drop verbose prose — use tables and code blocks
    - Drop NT7 migration content if it exceeds 500 lines (summarize to key patterns only)
  - Write as self-contained .md file with YAML frontmatter
  - Save to `~/.config/opencode/skills/ninjatrader-error-doctor.md` (overwrites current)
  - Target size: 40-55KB (this is the error encyclopedia — needs most of the error codes)

  **Must NOT do**:
  - Include ANY DEEP6-specific content
  - Include NinjaScript build patterns (that's builder-doctor)
  - Include "load this file first" references
  - Copy the source file verbatim — must synthesize for density
  - Exceed 60KB file size

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Dense technical documentation synthesis from large source material
  - **Skills**: [`ninjatrader-error-doctor`]
    - `ninjatrader-error-doctor`: Load current skill to understand format being replaced
  - **Skills Evaluated but Omitted**:
    - `ninjatrader-builder-doctor`: Build patterns not relevant to error skill

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 4, 6)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 8, 10
  - **Blocked By**: Tasks 1, 3

  **References**:

  **Input Sources**:
  - `.sisyphus/drafts/nt8-coverage-matrix.md` — Which sections assigned to error-doctor
  - `.sisyphus/drafts/nt8-ownership-map.md` — Shared content decisions

  **Primary Content Source**:
  - `dashboard/agents/ninjascript-error-surgeon-v2.md` — 3,318 lines covering every CS error, runtime exception, SharpDX crash, behavioral bug, with broken/fixed code pairs

  **Secondary Content Sources**:
  - `.claude/skills/nt8-fix/knowledge.md` — Universal error taxonomy sections (not DEEP6 file inventory)
  - `ninjatrader/ninjascript-ai-context.md` — Forbidden patterns section (for cross-reference to errors they cause)

  **Format Reference**:
  - `~/.config/opencode/skills/ninjatrader-error-doctor.md` — Current skill file for YAML format

  **WHY Each Reference Matters**:
  - Error surgeon is the goldmine — it has every error code with fixes. Synthesize it densely.
  - nt8-fix knowledge adds NT8-specific threading/volatile patterns not in the surgeon
  - Coverage matrix ensures nothing is missed or duplicated with other skills

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: YAML frontmatter is valid
    Tool: Bash (PowerShell)
    Steps:
      1. Read first 5 lines, verify --- / name: / description: (with error-related triggers) / ---
    Expected Result: Valid YAML frontmatter with trigger phrases including "fix", "error", "compile", "CS0"
    Evidence: .sisyphus/evidence/task-5-frontmatter.txt

  Scenario: Zero DEEP6 contamination
    Tool: Bash (PowerShell)
    Steps:
      1. `Select-String -Path "$env:USERPROFILE\.config\opencode\skills\ninjatrader-error-doctor.md" -Pattern "DEEP6|C:\\Users\\Tea|localhost:19206|Sim101|DEEP6Signal|DEEP6Footprint"`
    Expected Result: 0 matches
    Evidence: .sisyphus/evidence/task-5-no-contamination.txt

  Scenario: Major CS error codes present
    Tool: Bash (PowerShell)
    Steps:
      1. `Select-String -Path "$env:USERPROFILE\.config\opencode\skills\ninjatrader-error-doctor.md" -Pattern "CS0101|CS0103|CS0246|CS0677|CS1061|CS0019|CS0029" | Measure-Object`
    Expected Result: At least 5 of the 7 major CS codes found (all should be present)
    Evidence: .sisyphus/evidence/task-5-error-codes.txt

  Scenario: Size under ceiling
    Tool: Bash (PowerShell)
    Steps:
      1. Measure file size in KB
    Expected Result: Under 60KB
    Evidence: .sisyphus/evidence/task-5-size.txt

  Scenario: No "load this file first" references
    Tool: Bash (PowerShell)
    Steps:
      1. Grep for "must read|load first|Required Context to Load|read these before"
    Expected Result: 0 matches
    Evidence: .sisyphus/evidence/task-5-no-load-refs.txt
  ```

  **Evidence to Capture:**
  - [ ] task-5-frontmatter.txt, task-5-no-contamination.txt, task-5-error-codes.txt, task-5-size.txt, task-5-no-load-refs.txt

  **Commit**: YES
  - Message: `docs(skills): upgrade ninjatrader-error-doctor to comprehensive error encyclopedia`
  - Files: `~/.config/opencode/skills/ninjatrader-error-doctor.md`

- [x] 6. Write Upgraded ninjatrader-builder-doctor Skill

  **What to do**:
  - Read the coverage matrix (Task 1) to identify all sections assigned to `builder-doctor`
  - Read the ownership map (Task 3) for shared content decisions
  - Read the current builder-doctor skill at `~/.config/opencode/skills/ninjatrader-builder-doctor.md`
  - Read the PRIMARY source: `dashboard/agents/ULTIMATE-NINJASCRIPT-AGENT-v5.md` (10,433 lines)
  - Read SECONDARY sources: `nt8-new/knowledge.md` (universal code gen patterns), `ninjascript-ai-context.md` (forbidden patterns, API patterns)
  - **This is the largest and hardest task.** The 10,433-line ULTIMATE file must be synthesized into ~50-60KB. Strategy:
    - Keep the full indicator pattern template (OnStateChange, OnBarUpdate, properties)
    - Keep the full strategy pattern template (with safety defaults)
    - Keep SharpDX rendering reference (create/dispose lifecycle, OnRender patterns, resource management)
    - Keep threading/performance section (UI thread rules, background thread marshaling)
    - Keep multi-series/multi-timeframe patterns
    - Keep Draw.* method reference (compact table format)
    - Keep built-in indicator/series reference (compact table format)
    - Keep property decoration patterns and enum rules
    - Keep order management patterns (market/limit/stop, ATM workflow, position tracking)
    - Keep forbidden patterns list with explanations
    - Keep Pine Script → NinjaScript conversion section (compact)
    - **Drop or heavily summarize**: ICT methodology details (trading methodology, not NinjaScript), verbose explanations where tables suffice, multiple examples per pattern (keep best one), prop firm compliance rules (edge case, not core NinjaScript)
  - Write as self-contained .md file with YAML frontmatter
  - Save to `~/.config/opencode/skills/ninjatrader-builder-doctor.md` (overwrites current)
  - Target size: 45-60KB (this is the largest skill — full NinjaScript development reference)

  **Must NOT do**:
  - Include ANY DEEP6-specific content
  - Include error diagnosis content (that's error-doctor)
  - Include NT8 platform/installation content (that's machine-profile)
  - Include "load this file first" references
  - Copy the source file verbatim — must compress aggressively (10K lines → ~60KB)
  - Exceed 60KB file size
  - Invent new API patterns not in source files

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Massive technical documentation synthesis — the most demanding writing task
  - **Skills**: [`ninjatrader-builder-doctor`]
    - `ninjatrader-builder-doctor`: Load current skill to understand format being replaced
  - **Skills Evaluated but Omitted**:
    - `ninjatrader-error-doctor`: Error content belongs in separate skill

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 4, 5)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 9, 10
  - **Blocked By**: Tasks 1, 3

  **References**:

  **Input Sources**:
  - `.sisyphus/drafts/nt8-coverage-matrix.md` — Which sections assigned to builder-doctor
  - `.sisyphus/drafts/nt8-ownership-map.md` — Shared content decisions and size estimates

  **Primary Content Source**:
  - `dashboard/agents/ULTIMATE-NINJASCRIPT-AGENT-v5.md` — 10,433-line NinjaScript developer encyclopedia covering runtime architecture, every pattern, SharpDX, orders, threading, performance, ICT, prop firms

  **Secondary Content Sources**:
  - `.claude/skills/nt8-new/knowledge.md` — Enum placement rules, property decoration patterns, pre-generation checklist, mandatory file structure (universal parts only)
  - `ninjatrader/ninjascript-ai-context.md` — Forbidden patterns, API patterns, verified constraints

  **Format Reference**:
  - `~/.config/opencode/skills/ninjatrader-builder-doctor.md` — Current skill for YAML format

  **WHY Each Reference Matters**:
  - ULTIMATE file is the mother lode — 40+ sections of verified NinjaScript patterns. Must be compressed without losing correctness.
  - nt8-new knowledge has battle-tested patterns (enum global namespace rule) verified through actual compilation
  - Coverage matrix prevents including content that belongs in machine-profile or error-doctor

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: YAML frontmatter is valid with expanded triggers
    Tool: Bash (PowerShell)
    Steps:
      1. Read first 5 lines, verify --- / name: / description: (with build-related triggers) / ---
    Expected Result: Valid YAML frontmatter with triggers including "build", "indicator", "strategy", "SharpDX", "NinjaScript"
    Evidence: .sisyphus/evidence/task-6-frontmatter.txt

  Scenario: Zero DEEP6 contamination
    Tool: Bash (PowerShell)
    Steps:
      1. `Select-String -Path "$env:USERPROFILE\.config\opencode\skills\ninjatrader-builder-doctor.md" -Pattern "DEEP6|C:\\Users\\Tea|localhost:19206|Sim101|DEEP6Signal|DEEP6Footprint"`
    Expected Result: 0 matches
    Evidence: .sisyphus/evidence/task-6-no-contamination.txt

  Scenario: Core development topics present
    Tool: Bash (PowerShell)
    Steps:
      1. `Select-String -Path "$env:USERPROFILE\.config\opencode\skills\ninjatrader-builder-doctor.md" -Pattern "OnStateChange|OnBarUpdate|SharpDX|OnRender|NinjaScriptProperty|AddDataSeries|Draw\." | Measure-Object`
    Expected Result: At least 6 of 7 core topics found
    Evidence: .sisyphus/evidence/task-6-topics.txt

  Scenario: Size under ceiling
    Tool: Bash (PowerShell)
    Steps:
      1. Measure file size in KB
    Expected Result: Under 60KB
    Evidence: .sisyphus/evidence/task-6-size.txt

  Scenario: No "load this file first" references
    Tool: Bash (PowerShell)
    Steps:
      1. Grep for "must read|load first|Required Context to Load|read these before"
    Expected Result: 0 matches
    Evidence: .sisyphus/evidence/task-6-no-load-refs.txt

  Scenario: Forbidden patterns section exists
    Tool: Bash (PowerShell)
    Steps:
      1. `Select-String -Pattern "async/await|volatile.*double|Span<T>|record type|C# 7.3" | Measure-Object`
    Expected Result: At least 3 forbidden pattern mentions
    Evidence: .sisyphus/evidence/task-6-forbidden-patterns.txt
  ```

  **Evidence to Capture:**
  - [ ] task-6-frontmatter.txt, task-6-no-contamination.txt, task-6-topics.txt, task-6-size.txt, task-6-no-load-refs.txt, task-6-forbidden-patterns.txt

  **Commit**: YES
  - Message: `docs(skills): upgrade ninjatrader-builder-doctor to comprehensive NinjaScript developer guide`
  - Files: `~/.config/opencode/skills/ninjatrader-builder-doctor.md`

- [x] 7. Refactor nt8-expert Project Skill to DEEP6 Wrapper

  **What to do**:
  - Read the current project skill: `.claude/skills/nt8-expert/SKILL.md`, `knowledge.md`, `scripts.md`
  - Remove ALL universal NT8 knowledge that now lives in opencode skills (paths patterns, folder rules, compilation model, keyboard shortcuts — these are now in machine-profile)
  - Keep ONLY DEEP6-specific content: DEEP6 file inventory, DEEP6 deployment scripts reference, DEEP6DevAddon HTTP API (localhost:19206), DEEP6-specific paths (C:\Users\Tea\...), machine-specific configurations
  - Add explicit cross-references section: "For universal NT8 knowledge, invoke opencode skills: ninjatrader-machine-profile, ninjatrader-builder-doctor, ninjatrader-error-doctor"
  - Keep `scripts.md` as-is (DEEP6-specific automation scripts)
  - Update `SKILL.md` trigger description to reflect wrapper role

  **Must NOT do**:
  - Delete the skill directory or change its structure
  - Remove DEEP6-specific operational knowledge (deployment scripts, file inventory, dev API)
  - Touch `scripts.md` content (it's already DEEP6-specific)
  - Remove the skill entirely

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Content trimming from existing file — straightforward editing
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Load to see the full current content being refactored
  - **Skills Evaluated but Omitted**:
    - `ninjatrader-machine-profile`: The new version isn't needed to trim the old project skill

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 8, 9, 10, 11)
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 4

  **References**:

  **Files to Edit**:
  - `.claude/skills/nt8-expert/SKILL.md` — Update trigger description and add cross-reference section
  - `.claude/skills/nt8-expert/knowledge.md` — Remove universal NT8 content, keep DEEP6-specific
  - `.claude/skills/nt8-expert/scripts.md` — Leave unchanged (already DEEP6-specific)

  **Cross-Reference Target**:
  - `~/.config/opencode/skills/ninjatrader-machine-profile.md` — Confirm universal content moved here before removing from project skill

  **WHY Each Reference Matters**:
  - Must read current knowledge.md to identify which sections are universal vs DEEP6-specific
  - Must verify machine-profile has the universal content before deleting from here

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Cross-references to opencode skills present
    Tool: Bash (PowerShell)
    Steps:
      1. `Select-String -Path ".claude\skills\nt8-expert\SKILL.md" -Pattern "ninjatrader-machine-profile|ninjatrader-builder-doctor|ninjatrader-error-doctor" | Measure-Object`
    Expected Result: At least 1 match (cross-reference section exists)
    Evidence: .sisyphus/evidence/task-7-cross-refs.txt

  Scenario: DEEP6-specific content preserved
    Tool: Bash (PowerShell)
    Steps:
      1. `Select-String -Path ".claude\skills\nt8-expert\knowledge.md" -Pattern "DEEP6|localhost:19206|nt8-deploy|nt8-compile" | Measure-Object`
    Expected Result: At least 3 matches (DEEP6 operational content retained)
    Evidence: .sisyphus/evidence/task-7-deep6-preserved.txt

  Scenario: Universal NT8 knowledge removed
    Tool: Bash (PowerShell)
    Steps:
      1. `Select-String -Path ".claude\skills\nt8-expert\knowledge.md" -Pattern "OnStateChange|SetDefaults.*Configure|namespace NinjaTrader\.NinjaScript" | Measure-Object`
    Expected Result: 0 matches (universal lifecycle/namespace content moved to opencode)
    Evidence: .sisyphus/evidence/task-7-universal-removed.txt
  ```

  **Commit**: YES (groups with Tasks 8, 9)
  - Message: `refactor(skills): thin project skills to DEEP6-specific wrappers`
  - Files: `.claude/skills/nt8-expert/SKILL.md`, `.claude/skills/nt8-expert/knowledge.md`

- [x] 8. Refactor nt8-fix Project Skill to DEEP6 Wrapper

  **What to do**:
  - Read `.claude/skills/nt8-fix/SKILL.md` and `knowledge.md`
  - Remove universal CS error taxonomy (now in error-doctor opencode skill)
  - Remove universal threading rules, volatile constraints, namespace conflict patterns
  - Keep ONLY: DEEP6 file inventory for error context, DEEP6-specific error patterns (FootprintBar.cs duplicate type gotcha, DEEP6 namespace conflicts), deployment drift patterns specific to DEEP6
  - Add cross-references to opencode skills
  - Update SKILL.md trigger description

  **Must NOT do**:
  - Delete the skill directory
  - Remove DEEP6-specific error context (FootprintBar deployment rule, DEEP6 file compile status)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Content trimming — straightforward editing
  - **Skills**: [`nt8-fix`]
  - **Skills Evaluated but Omitted**: All others

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 7, 9, 10, 11)
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 5

  **References**:
  - `.claude/skills/nt8-fix/SKILL.md` — Update trigger description
  - `.claude/skills/nt8-fix/knowledge.md` — Remove universal, keep DEEP6-specific

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Cross-references present and DEEP6 content preserved
    Tool: Bash (PowerShell)
    Steps:
      1. Grep SKILL.md for opencode skill references
      2. Grep knowledge.md for "DEEP6|FootprintBar" (DEEP6-specific content preserved)
      3. Grep knowledge.md for "CS0246.*missing.*using" (universal error explanation removed)
    Expected Result: Cross-refs found, DEEP6 content found, universal explanations absent
    Evidence: .sisyphus/evidence/task-8-wrapper-check.txt
  ```

  **Commit**: YES (groups with Tasks 7, 9)
  - Message: `refactor(skills): thin project skills to DEEP6-specific wrappers`
  - Files: `.claude/skills/nt8-fix/SKILL.md`, `.claude/skills/nt8-fix/knowledge.md`

- [x] 9. Refactor nt8-new Project Skill to DEEP6 Wrapper

  **What to do**:
  - Read `.claude/skills/nt8-new/SKILL.md` and `knowledge.md`
  - This skill is ~80% universal — most content migrates to builder-doctor
  - Remove: mandatory file structure (universal), property decoration patterns (universal), built-in series reference (universal), Draw.* methods (universal), SharpDX patterns (universal), forbidden patterns (universal)
  - Keep ONLY: DEEP6-specific code generation workflow (deploy → compile → fix loop using DEEP6 scripts), DEEP6 file naming conventions, DEEP6 namespace conventions (NinjaTrader.NinjaScript.Indicators.DEEP6)
  - Add cross-references to opencode skills (especially builder-doctor)
  - Update SKILL.md trigger description
  - This will be the most dramatically thinned skill — from 259 lines to ~40-60 lines

  **Must NOT do**:
  - Delete the skill directory
  - Remove the deploy → compile → fix workflow (it uses DEEP6-specific scripts)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Aggressive content trimming — most content moves out
  - **Skills**: [`nt8-new`]
  - **Skills Evaluated but Omitted**: All others

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 7, 8, 10, 11)
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Task 6

  **References**:
  - `.claude/skills/nt8-new/SKILL.md` — Update trigger description
  - `.claude/skills/nt8-new/knowledge.md` — Remove 80% universal content, keep DEEP6 workflow

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Dramatically thinned but DEEP6 workflow preserved
    Tool: Bash (PowerShell)
    Steps:
      1. `(Get-Content ".claude\skills\nt8-new\knowledge.md" | Measure-Object -Line).Lines` — verify under 80 lines
      2. `Select-String -Path ".claude\skills\nt8-new\knowledge.md" -Pattern "nt8-deploy|nt8-compile|DEEP6" | Measure-Object` — verify DEEP6 workflow present
      3. `Select-String -Pattern "ninjatrader-builder-doctor"` — verify cross-reference present
    Expected Result: Under 80 lines, DEEP6 workflow preserved, cross-reference present
    Evidence: .sisyphus/evidence/task-9-wrapper-check.txt
  ```

  **Commit**: YES (groups with Tasks 7, 8)
  - Message: `refactor(skills): thin project skills to DEEP6-specific wrappers`
  - Files: `.claude/skills/nt8-new/SKILL.md`, `.claude/skills/nt8-new/knowledge.md`

- [x] 10. Archive Source Files with Canonical-Source-Moved Notices

  **What to do**:
  - Add a notice to the TOP of each source file (do NOT delete them):
    - `dashboard/agents/ULTIMATE-NINJASCRIPT-AGENT-v5.md` — Add: `> ⚠️ ARCHIVED: Canonical source moved to opencode skill \`ninjatrader-builder-doctor\`. This file is preserved for reference but is no longer the authoritative version. Do not edit.`
    - `dashboard/agents/ninjascript-error-surgeon-v2.md` — Add: `> ⚠️ ARCHIVED: Canonical source moved to opencode skill \`ninjatrader-error-doctor\`. This file is preserved for reference but is no longer the authoritative version. Do not edit.`
    - `ninjatrader/ninjascript-ai-context.md` — Add: `> ⚠️ ARCHIVED: Content absorbed into opencode skills \`ninjatrader-machine-profile\` and \`ninjatrader-builder-doctor\`. This file is preserved for reference but is no longer the authoritative version. Do not edit.`

  **Must NOT do**:
  - Delete any source files
  - Modify content beyond adding the archive notice
  - Touch any other files

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 3 tiny prepend edits
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 7, 8, 9, 11)
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Tasks 4, 5, 6

  **References**:
  - `dashboard/agents/ULTIMATE-NINJASCRIPT-AGENT-v5.md` — Prepend archive notice
  - `dashboard/agents/ninjascript-error-surgeon-v2.md` — Prepend archive notice
  - `ninjatrader/ninjascript-ai-context.md` — Prepend archive notice

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All 3 source files have archive notices
    Tool: Bash (PowerShell)
    Steps:
      1. `Get-Content "dashboard\agents\ULTIMATE-NINJASCRIPT-AGENT-v5.md" -TotalCount 3 | Select-String "ARCHIVED"`
      2. `Get-Content "dashboard\agents\ninjascript-error-surgeon-v2.md" -TotalCount 3 | Select-String "ARCHIVED"`
      3. `Get-Content "ninjatrader\ninjascript-ai-context.md" -TotalCount 3 | Select-String "ARCHIVED"`
    Expected Result: All 3 files have ARCHIVED notice in first 3 lines
    Evidence: .sisyphus/evidence/task-10-archive-notices.txt

  Scenario: Source file content unchanged beyond notice
    Tool: Bash (PowerShell)
    Steps:
      1. `(Get-Content "dashboard\agents\ULTIMATE-NINJASCRIPT-AGENT-v5.md" | Measure-Object -Line).Lines` — should be original line count + 2-3 lines for notice
    Expected Result: Line count within 5 of original (10,433 + 2-3)
    Evidence: .sisyphus/evidence/task-10-content-preserved.txt
  ```

  **Commit**: YES
  - Message: `chore: archive source knowledge bases with canonical-source-moved notices`
  - Files: `dashboard/agents/ULTIMATE-NINJASCRIPT-AGENT-v5.md`, `dashboard/agents/ninjascript-error-surgeon-v2.md`, `ninjatrader/ninjascript-ai-context.md`

- [x] 11. Verify Coverage Matrix Completeness Against Outputs

  **What to do**:
  - Read the coverage matrix from Task 1 (`.sisyphus/drafts/nt8-coverage-matrix.md`)
  - Read all 3 completed opencode skills
  - For each row in the coverage matrix, verify the assigned section header appears in the target skill
  - Sample at least 20 section headers across all 3 skills
  - Report: sections found, sections missing, sections in wrong skill
  - Save verification report

  **Must NOT do**:
  - Modify any skill files
  - Skip sampling — must check at least 20 sections

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Verification/grep task, not creative writing
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 7, 8, 9, 10)
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Tasks 4, 5, 6

  **References**:
  - `.sisyphus/drafts/nt8-coverage-matrix.md` — The mapping to verify against
  - `~/.config/opencode/skills/ninjatrader-machine-profile.md` — Check assigned sections present
  - `~/.config/opencode/skills/ninjatrader-error-doctor.md` — Check assigned sections present
  - `~/.config/opencode/skills/ninjatrader-builder-doctor.md` — Check assigned sections present

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: At least 90% of sampled sections found in correct target
    Tool: Bash (PowerShell)
    Steps:
      1. Extract 20 random section mappings from coverage matrix
      2. For each, grep the target skill for the section header or equivalent content
      3. Count hits vs misses
    Expected Result: At least 18/20 (90%) sections found in correct target skill
    Failure Indicators: More than 2 sections missing from their assigned target
    Evidence: .sisyphus/evidence/task-11-coverage-verification.txt
  ```

  **Commit**: NO (verification artifact)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read skill files, check content). For each "Must NOT Have": grep opencode skills for DEEP6-specific patterns, grep project wrappers for universal NT8 knowledge — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Content Quality Review** — `unspecified-high`
  Read all 3 opencode skills end-to-end. Check: YAML frontmatter valid, trigger phrases cover expanded scope, sections are well-organized, code examples are correct C# 7.3/.NET 4.8, no broken markdown, no placeholder text, no "TODO" markers, no "load this file first" references.
  Output: `Skills [N/N quality] | Frontmatter [N/N valid] | Code Examples [N/N correct] | VERDICT`

- [x] F3. **Cross-Contamination QA** — `unspecified-high`
  Run contamination checks: (1) Grep all 3 opencode skills for forbidden DEEP6 patterns (DEEP6, C:\Users\Tea, localhost:19206, Sim101, ATM template names, DEEP6Signal, DEEP6Footprint, DEEP6Strategy). (2) Grep all 4 project skills for universal NT8 patterns that should have migrated (CS error explanations, NinjaScript API reference, SharpDX tutorial content, state machine patterns). (3) Verify coverage matrix — sample 20 random source sections and confirm they appear in exactly one target.
  Output: `OpenCode Contamination [CLEAN/N issues] | Wrapper Contamination [CLEAN/N issues] | Coverage [N/20 verified] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual output file. Verify 1:1 — everything in spec was built (no missing sections), nothing beyond spec was built (no creep). Check file sizes are under 60KB ceiling. Verify source files have archive notices. Verify nt8-architect was NOT modified. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Size Budget [N/N under limit] | Archives [N/N noticed] | nt8-architect [UNTOUCHED/MODIFIED] | VERDICT`

---

## Commit Strategy

- **Wave 2**: `docs(skills): upgrade ninjatrader-machine-profile to comprehensive NT8 platform skill` — machine-profile.md
- **Wave 2**: `docs(skills): upgrade ninjatrader-error-doctor to comprehensive error encyclopedia` — error-doctor.md
- **Wave 2**: `docs(skills): upgrade ninjatrader-builder-doctor to comprehensive NinjaScript developer guide` — builder-doctor.md
- **Wave 3**: `refactor(skills): thin project skills to DEEP6-specific wrappers` — nt8-expert/, nt8-fix/, nt8-new/
- **Wave 3**: `chore: archive source knowledge bases with canonical-source-moved notices` — dashboard/agents/

---

## Success Criteria

### Verification Commands
```powershell
# 1. Zero DEEP6 contamination in opencode skills
Select-String -Path "$env:USERPROFILE\.config\opencode\skills\ninjatrader-*.md" -Pattern "DEEP6|C:\\Users\\Tea|localhost:19206|Sim101" -CaseSensitive
# Expected: 0 matches

# 2. Size budget compliance
Get-Item "$env:USERPROFILE\.config\opencode\skills\ninjatrader-*.md" | Select-Object Name, @{N='KB';E={[math]::Round($_.Length/1KB,1)}}
# Expected: all under 60KB

# 3. YAML frontmatter valid
Get-Content "$env:USERPROFILE\.config\opencode\skills\ninjatrader-machine-profile.md" -TotalCount 4
# Expected: line 1 = "---", line 2 = "name: ...", line 3 = "description: ...", line 4 = "---"

# 4. No "load this file first" in opencode skills
Select-String -Path "$env:USERPROFILE\.config\opencode\skills\ninjatrader-*.md" -Pattern "must read|load first|Required Context to Load"
# Expected: 0 matches

# 5. Project wrappers have cross-references
Select-String -Path ".claude\skills\nt8-expert\SKILL.md" -Pattern "ninjatrader-builder-doctor|ninjatrader-error-doctor|ninjatrader-machine-profile"
# Expected: at least 1 match
```

### Final Checklist
- [ ] All 3 opencode skills comprehensive and self-contained
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] Coverage matrix 100% complete
- [ ] Source files archived
- [ ] nt8-architect unchanged
