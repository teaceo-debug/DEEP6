# NT8 Content Ownership Map

**Purpose:** Resolve duplication for shared topics across the 3 opencode NT8 skills. Defines which skill owns each shared section, what secondary skills may include, and provides size estimates per skill.

**Source files analyzed:**
- `dashboard/agents/ULTIMATE-NINJASCRIPT-AGENT-v5.md` (10,433 lines)
- `dashboard/agents/ninjascript-error-surgeon-v2.md` (3,318 lines)
- `ninjatrader/ninjascript-ai-context.md` (389 lines)
- `.claude/skills/nt8-new/knowledge.md` (259 lines)
- `.claude/skills/nt8-fix/knowledge.md` (250 lines)

**Target skills (opencode only):**
- `ninjatrader-machine-profile` (machine-profile)
- `ninjatrader-builder-doctor` (builder-doctor)
- `ninjatrader-error-doctor` (error-doctor)

---

## Shared Topics Analysis

### Topic 1: State Machine / OnStateChange Lifecycle

**Appears in:**
- ULTIMATE `## STATE MACHINE - COMPLETE REFERENCE` (lines 85-181, ~97 lines) — full reference with all states, code examples, critical ordering rules
- ULTIMATE `### State Guards in OnBarUpdate` (lines 156-180, ~25 lines) — guard patterns
- ai-context `## Mandatory State Machine` (lines 67-104, ~38 lines) — compact version with code example
- nt8-new `## OnStateChange - Mandatory Pattern` (lines 49-83, ~35 lines) — DEEP6-specific compact version
- surgeon `### SM-001: Complete State Machine Law` (lines 2846-2966, ~121 lines) — error-focused version with safe/unsafe annotations

**Coverage matrix primary owner:** machine-profile (state machine basics); error-doctor (SM-001 error patterns); builder-doctor (State Guards coding pattern)

**Decision: DUPLICATE (partial)**
- machine-profile: Include FULL state machine reference (~97 lines). This is foundational platform knowledge every developer needs.
- builder-doctor: Include the State Guards in OnBarUpdate section (~25 lines) as a coding pattern. Add a one-line pointer: "Full state machine reference: see machine-profile."
- error-doctor: Include SM-001 in full (~121 lines) — it's error-focused with safe/unsafe annotations that are distinct from the machine-profile version. The two versions serve different purposes (reference vs. error prevention).

**Rationale:** State machine is the single most critical NT8 concept. Missing it causes immediate compile or runtime failures. The three versions are meaningfully different: machine-profile = reference table, builder-doctor = guard patterns, error-doctor = what goes wrong and why.

---

### Topic 2: Namespace Rules

**Appears in:**
- ULTIMATE `### Key Namespace Imports (Always Include)` (lines 55-84, ~30 lines) — full using block
- ai-context `## Namespace Rules` (lines 22-33, ~12 lines) — compact namespace list
- nt8-fix `### Namespace rules` — brief reminder in DEEP6 context
- nt8-new `## DEEP6 Namespace Conventions` — DEEP6-specific namespace table

**Coverage matrix primary owner:** machine-profile

**Decision: DUPLICATE (brief)**
- machine-profile: Include FULL namespace imports block (~30 lines). This is platform-level knowledge.
- builder-doctor: Include the full using block inline in the Complete Indicator Template (it's already embedded there). No separate section needed — the template carries it.
- error-doctor: Reference only. When diagnosing CS0246 (type not found), mention "check namespace imports — see machine-profile for the canonical list." No separate section.

**Rationale:** The full using block is 30 lines and appears in every indicator template anyway. Duplicating it in builder-doctor via the template is acceptable and expected. error-doctor doesn't need a standalone section.

---

### Topic 3: Forbidden C# Patterns (async/await, Span<T>, records, ValueTuple, volatile double)

**Appears in:**
- ULTIMATE `## NT8 RUNTIME ARCHITECTURE` (lines 28-84) — mentions async/await prohibition in execution model
- ai-context `## FORBIDDEN - Do NOT generate these` (lines 46-65, ~20 lines) — table format with CS error codes
- ai-context `## Runtime Constraints` (lines 8-19, ~12 lines) — .NET 4.8 / C# 7.3 constraints
- nt8-new `## FORBIDDEN Patterns (compile errors)` (lines 189-203, ~15 lines) — table with error codes and fixes
- nt8-fix `## NT8 NinjaScript Compile Environment` (lines 1-11, ~11 lines) — brief constraint list

**Coverage matrix primary owner:** builder-doctor (coding constraints); machine-profile (runtime constraints context)

**Decision: DUPLICATE**
- machine-profile: Include Runtime Constraints section (~12 lines: .NET 4.8, C# 7.3, no async, no Span<T>, etc.). This is platform-level context.
- builder-doctor: Include FULL forbidden patterns table (~20 lines) with CS error codes and fixes. This is the authoritative coding reference.
- error-doctor: Do NOT duplicate. When a CS error is caused by a forbidden pattern (e.g., CS4033 from async, CS0677 from volatile double), the individual error entry already explains the fix. Cross-reference builder-doctor for the full list.

**Rationale:** Runtime constraints (~12 lines) are short enough to duplicate in machine-profile for self-containment. The full forbidden table belongs in builder-doctor. error-doctor handles the symptoms (CS codes) not the prevention list.

---

### Topic 4: OnBarUpdate Guards (CurrentBar, BarsInProgress checks)

**Appears in:**
- ULTIMATE `### State Guards in OnBarUpdate` (lines 156-180, ~25 lines) — 5 guard patterns with comments
- ai-context `## OnBarUpdate - Always Guard with CurrentBar` (lines 106-129, ~24 lines) — code example with price series access
- nt8-new `## OnBarUpdate - Mandatory Guard Pattern` (lines 86-97, ~12 lines) — compact version
- nt8-fix `### OnBarUpdate() - always check CurrentBar before indexing` — brief reminder

**Coverage matrix primary owner:** builder-doctor

**Decision: DUPLICATE (brief)**
- builder-doctor: Include FULL guard patterns section (~25 lines) with all 5 guard types. This is the authoritative coding reference.
- machine-profile: Include a 3-line quick reference only: "OnBarUpdate must start with: `if (BarsInProgress != 0) return;` then `if (CurrentBar < BarsRequiredToPlot) return;`" — enough for platform context without duplicating the full section.
- error-doctor: Do NOT duplicate. Runtime errors RT-001 (invalid index) and RT-002 (array out of bounds) already explain what happens when guards are missing.

**Rationale:** Guards are a coding pattern (builder-doctor) but also appear in error-doctor as the root cause of RT-001/RT-002. The error entries handle the symptom side. builder-doctor handles the prevention side.

---

### Topic 5: Thread Safety Rules

**Appears in:**
- ULTIMATE `## NT8 RUNTIME ARCHITECTURE` (lines 28-84) — mentions UI thread constraint
- ai-context `## Thread Safety` (lines 201-223, ~23 lines) — code examples with WRONG/RIGHT patterns
- nt8-fix `### Threading from indicator to UI` — brief code example
- surgeon `### LG-007: Static Variable Threading Corruption` — error case

**Coverage matrix primary owner:** builder-doctor

**Decision: primary-only**
- builder-doctor: Include FULL thread safety section (~23 lines) with WRONG/RIGHT code examples. This is the authoritative development reference.
- machine-profile: Include a 2-line note in the execution model section: "OnBarUpdate runs on a background thread. Marshal UI updates via `Dispatcher.InvokeAsync()` or `TriggerCustomEvent()`." No separate section.
- error-doctor: LG-007 (Static Variable Threading Corruption) is already in the behavioral error database. It cross-references the threading rules without duplicating them.

**Rationale:** Thread safety is a development concern (builder-doctor). The error-doctor entry for LG-007 is the symptom; builder-doctor is the prevention. The machine-profile note is 2 lines — acceptable for self-containment.

---

### Topic 6: Built-In Indicator List

**Appears in:**
- ULTIMATE `### Built-In Indicators (Callable as Methods)` — full list with all built-ins
- ai-context `## Built-in Indicators (Call These - Do Not Reimplement)` (lines 151-167, ~17 lines) — compact list with syntax
- nt8-new `## Built-In Series (use, don't reimplement)` (lines 142-156, ~15 lines) — table format

**Coverage matrix primary owner:** builder-doctor

**Decision: primary-only**
- builder-doctor: Include FULL built-in indicators list. This is a development API reference.
- machine-profile: No separate section. The instrument specs section covers platform-level data; built-in indicators are a coding API.
- error-doctor: No separate section. CS1501 (wrong argument count) and CS1061 (no definition) entries already reference specific built-in indicator signatures where relevant.

**Rationale:** Built-in indicators are purely a development API. 17 lines is short but the content is 100% builder-doctor territory. No meaningful self-containment value in duplicating it elsewhere.

---

### Topic 7: Draw.* Methods

**Appears in:**
- ULTIMATE `## DRAW.* API - COMPLETE REFERENCE` — full reference with all draw methods
- ai-context `## Drawing Objects (NT8 Style - All via Draw.* Static Class)` (lines 170-199, ~30 lines) — code examples
- nt8-new `## Draw.* Methods` (lines 159-185, ~27 lines) — compact code examples
- nt8-fix `### Drawing on chart (use Draw.* helpers)` — brief reminder

**Coverage matrix primary owner:** builder-doctor

**Decision: primary-only**
- builder-doctor: Include FULL Draw.* API reference. This is a development API.
- machine-profile: No separate section. Draw.* is a coding API, not platform knowledge.
- error-doctor: SDX-009 (Draw.* tag collision) is already in the SharpDX error database. It explains the tag uniqueness rule without duplicating the full API.

**Rationale:** Draw.* is a development API (builder-doctor). The error-doctor entry for SDX-009 handles the one error case. No duplication needed.

---

### Topic 8: SharpDX Rendering Lifecycle

**Appears in:**
- ULTIMATE `## SHARPDX RENDERING - COMPLETE GUIDE` — full rendering patterns (brushes, geometry, text, coordinates)
- nt8-new `## SharpDX Custom Rendering (advanced)` (lines 205-231, ~27 lines) — compact version
- surgeon `## TIER 3: SHARPDX ERROR DATABASE` — crash database (SDX-001 through SDX-009)

**Coverage matrix primary owner:** builder-doctor (rendering patterns); error-doctor (crashes)

**Decision: SPLIT (already correct in matrix)**
- builder-doctor: Include FULL SharpDX rendering patterns — brush management, geometry, text rendering, coordinate mapping, anti-aliasing. This is the development reference.
- error-doctor: Include FULL SharpDX crash database (SDX-001 through SDX-009). These are error cases, not patterns.
- machine-profile: No separate section. SharpDX is a rendering API, not platform knowledge.

**Rationale:** The split is clean. Rendering patterns = builder-doctor. Crashes = error-doctor. No overlap needed.

---

### Topic 9: Property Decoration / NinjaScriptProperty Attributes

**Appears in:**
- ULTIMATE `## INDICATOR PROPERTIES & ATTRIBUTES - COMPLETE REFERENCE` — full reference
- ai-context `## Property Decoration (Parameters Visible to User)` (lines 131-148, ~18 lines) — code examples
- nt8-new `## Property Decoration Pattern` (lines 101-138, ~38 lines) — includes brush serialization and enum placement

**Coverage matrix primary owner:** builder-doctor

**Decision: primary-only**
- builder-doctor: Include FULL property decoration reference including brush serialization and enum placement rule.
- machine-profile: No separate section.
- error-doctor: CS0246 entry already notes that enum nested inside class causes boilerplate errors — cross-references the enum placement rule without duplicating it.

**Rationale:** Property decoration is a development pattern. 38 lines is medium-length but 100% builder-doctor territory.

---

### Topic 10: Enum Placement Rule (CRITICAL)

**Appears in:**
- nt8-new `### Enum property (enum MUST be at global namespace)` (lines 129-138, ~10 lines)
- nt8-fix knowledge — mentioned in context
- ULTIMATE `## COMPLETE PROPERTY ATTRIBUTE REFERENCE` — included in property reference

**Coverage matrix primary owner:** builder-doctor (noted as SHARED-fundamental in matrix)

**Decision: DUPLICATE**
- builder-doctor: Include in full as part of property decoration section (~10 lines).
- error-doctor: Include a 3-line note in the CS0246 entry: "Enum nested inside class causes CS0246 in the auto-generated boilerplate. Move enum to global namespace (before all namespace/class declarations)." This is short and critically dangerous to miss.
- machine-profile: No separate section.

**Rationale:** This is a 10-line rule that causes silent CS0246 errors in the auto-generated boilerplate — a trap that's easy to miss and hard to diagnose. Worth duplicating in error-doctor as a targeted note within the CS0246 entry.

---

## Additional Shared Topics Found

### Topic 11: Class Hierarchy (NinjaScriptBase → Indicator / Strategy)

**Appears in:**
- ULTIMATE `### NinjaScript Object Hierarchy` (lines 40-53, ~14 lines)
- ai-context `## Class Hierarchy` (lines 34-43, ~10 lines)

**Coverage matrix primary owner:** machine-profile

**Decision: primary-only**
- machine-profile: Include full class hierarchy. This is platform knowledge.
- builder-doctor: No separate section — the indicator template implicitly shows `class MyIndicator : Indicator`.
- error-doctor: No separate section.

**Rationale:** 10-14 lines, platform knowledge, machine-profile owns it cleanly.

---

### Topic 12: Multi-Series / AddDataSeries Pattern

**Appears in:**
- ULTIMATE `### Multi-Series Data Access` — full multi-series patterns
- ai-context `## Multi-Series (Watching Multiple Instruments or Timeframes)` (lines 225-237, ~13 lines)
- nt8-fix `### AddDataSeries - must be called in OnStateChange / State.Configure` — brief reminder

**Coverage matrix primary owner:** builder-doctor

**Decision: primary-only**
- builder-doctor: Include full multi-series patterns.
- machine-profile: No separate section.
- error-doctor: RT-013 (Series values set on wrong BarsInProgress) already covers the error case.

**Rationale:** Multi-series is a development pattern. The error-doctor entry handles the symptom.

---

## Size Estimates

### Methodology

**Compression ratio basis:**
- ULTIMATE file: 10,433 raw lines → target ~50-60KB for builder-doctor
- Observed ratio: ~4.8-5.8 bytes per raw line after compression (markdown + code blocks compress well)
- Code-heavy sections compress better than prose; error databases with structured tables compress well

**Section line estimates:**
- Average H2 section in ULTIMATE: ~50 lines (ranges from 10 to 200+)
- Average H3 section in ULTIMATE: ~15 lines
- Average H2 section in surgeon: ~40 lines
- Average H3 section in surgeon: ~35 lines (error entries are dense)
- machine-profile sections are shorter (platform specs, tables): ~20 lines average

### Calculation

| Skill | H2 sections | H3 sections | Est. raw lines | Compression ratio | Est. compressed KB | Under 60KB? |
|-------|-------------|-------------|---------------|-------------------|--------------------|-------------|
| machine-profile | 18 | 22 | ~1,800 | 5.5 bytes/line | ~9.9 KB + install research (~8KB) = ~18 KB | ✅ |
| builder-doctor | 57 | 148 | ~8,500 | 5.5 bytes/line | ~46.8 KB + duplication additions (~3KB) = ~50 KB | ✅ |
| error-doctor | 11 | 67 | ~3,200 | 5.5 bytes/line | ~17.6 KB + surgeon content (~22KB) = ~40 KB | ✅ |

**Notes on estimates:**
- machine-profile: 40 sections × ~20 lines avg = ~800 lines from ULTIMATE/ai-context + ~400 lines from install research (Task 2) + ~200 lines from ai-context platform sections = ~1,400 lines → ~18KB total. Well under ceiling.
- builder-doctor: 205 sections. H2 avg ~50 lines, H3 avg ~15 lines. (57 × 50) + (148 × 15) = 2,850 + 2,220 = ~5,070 lines from section headers alone. But many sections have substantial code blocks — actual content is ~8,000-9,000 lines. At 5.5 bytes/line compressed = ~44-50KB. Duplication additions (State Guards, brief namespace note) add ~3KB. Total: ~47-53KB. Under ceiling.
- error-doctor: 78 sections. H2 avg ~40 lines, H3 avg ~35 lines. (11 × 40) + (67 × 35) = 440 + 2,345 = ~2,785 lines. At 5.5 bytes/line = ~15KB. But surgeon content is dense with code blocks — actual ~3,200 lines → ~18KB. Plus ULTIMATE debugging section (~200 lines → ~1KB). Total: ~19-22KB. Well under ceiling.

**Risk assessment:**
- builder-doctor is the only skill approaching the ceiling. At ~50KB it has ~10KB of headroom. If the full footprint engine implementations are included verbatim, it could push toward 55-58KB. Writers should prioritize compression (remove redundant prose, keep code blocks tight).
- error-doctor and machine-profile are both well under ceiling with significant headroom.

---

## Writing Agent Instructions

### For machine-profile writer:

**Include in full:**
- NT8 Runtime Architecture (execution model, object hierarchy)
- Key Namespace Imports (full using block)
- State Machine — Complete Reference (all states table + critical ordering rules code block)
- Calculate Modes (table + when to use each)
- BarsPeriodType enumeration
- Instrument Specifications (NQ, MNQ, ES, MES, RTY, CL, GC)
- NT8 Connection Types
- NT8 Control Center Navigation (universal UI)
- NT8 Keyboard Shortcuts (universal shortcuts)
- Important NT8 Constraints
- Runtime Constraints (.NET 4.8, C# 7.3 — ~12 lines)
- Class Hierarchy (NinjaScriptBase → Indicator/Strategy)
- Install/Editor research content (from Task 2 draft)

**Include as brief reference (3 lines or less):**
- OnBarUpdate guard quick-ref: "Always start with `if (BarsInProgress != 0) return;` then `if (CurrentBar < BarsRequiredToPlot) return;`"
- Thread safety note: "OnBarUpdate runs on a background thread. Marshal UI updates via `Dispatcher.InvokeAsync()` or `TriggerCustomEvent()`."

**Do NOT include:**
- Full forbidden patterns table (builder-doctor owns it)
- Full Draw.* API (builder-doctor owns it)
- Full built-in indicators list (builder-doctor owns it)
- CS error codes (error-doctor owns them)
- SharpDX crash database (error-doctor owns it)

**Shared sections to briefly mention:**
- "For forbidden C# patterns and compile constraints, see builder-doctor."
- "For CS error codes and runtime errors, see error-doctor."

---

### For builder-doctor writer:

**Include in full:**
- All BARS & SERIES API sections
- All PLOTS AND LINES API sections
- All INDICATOR PROPERTIES & ATTRIBUTES sections (including brush serialization, enum placement rule)
- INDICATOR PANEL MANAGEMENT
- CHILD INDICATOR INSTANCES
- Built-In Indicators (callable as methods) — full list
- DRAW.* API — Complete Reference (all draw methods)
- MARKET DATA EVENTS (OnMarketData, OnMarketDepth)
- INSTRUMENT & TICK SIZE access patterns
- STRATEGY SYSTEM — Complete API
- ORDER MANAGEMENT — Complete Reference
- ATM STRATEGY INTEGRATION
- ACCOUNT & PERFORMANCE ACCESS
- SHARPDX RENDERING — Complete Guide (patterns only, not crashes)
- All footprint engine sections (Volume Profile, CVD, Footprint Chart, ICT)
- All signal catalog sections
- All display mode sections
- PERFORMANCE OPTIMIZATION
- COMMON PATTERNS & RECIPES
- COMPLETE PROPERTY ATTRIBUTE REFERENCE
- FULL FILE STRUCTURE TEMPLATES
- FORBIDDEN patterns table (~20 lines) — full table with CS codes and fixes
- State Guards in OnBarUpdate (~25 lines) — all 5 guard patterns
- Thread Safety section (~23 lines) — WRONG/RIGHT code examples
- Multi-Series patterns
- Strategy Order Methods
- Minimal Working Indicator Template (from ai-context)
- Pre-submission checklist (from ai-context)
- All footprint theory sections (Parts I-V)
- All competitor analysis sections
- All strategy bible sections

**Include as brief reference:**
- State machine quick-ref: "Full state machine reference: see machine-profile. Quick summary: SetDefaults → Configure → DataLoaded → Historical → Realtime → Terminated."

**Do NOT include:**
- CS error code database (error-doctor owns it)
- SharpDX crash database (error-doctor owns it)
- NT8 installation/editor procedures (machine-profile owns it)
- DEEP6-specific paths and deployment (wrapper skills own it)

---

### For error-doctor writer:

**Include in full:**
- MASTER ERROR INDEX (quick-lookup)
- TIER 1: All CS compile error entries (CS0019 through CS1612)
- TIER 2: All runtime error entries (RT-001 through RT-017)
- TIER 3: All SharpDX crash entries (SDX-001 through SDX-009)
- TIER 4: All behavioral/logic error entries (LG-001 through LG-009)
- TIER 5: NT7→NT8 migration errors (MIG-001 through MIG-004)
- TIER 6: SM-001 State Machine Error Database (~121 lines) — this is the error-focused version with safe/unsafe annotations, distinct from machine-profile's reference version
- TIER 7: Environment errors (ENV-004 through ENV-008)
- TIER 8: Self-debugging arsenal
- MASTER QUICK-FIX CHEAT SHEET
- DEBUGGING GUIDE from ULTIMATE (NinjaScript Compile Errors, Runtime Debugging, Common Logic Bugs)

**Include as targeted notes within existing entries (not separate sections):**
- Within CS0246 entry: 3-line note on enum placement rule causing boilerplate CS0246
- Within CS0677 entry: Cross-reference to builder-doctor forbidden patterns for full list
- Within RT-001/RT-002 entries: Cross-reference to builder-doctor OnBarUpdate guards

**Do NOT include:**
- Full forbidden patterns table (builder-doctor owns it — error-doctor handles the symptoms)
- Full Draw.* API (builder-doctor owns it)
- Full state machine reference (machine-profile owns it — error-doctor has SM-001 which is the error-focused version)
- SharpDX rendering patterns (builder-doctor owns it — error-doctor has the crash database)
- NT8 installation procedures (machine-profile owns it)

---

## Duplication Decision Summary

| Topic | machine-profile | builder-doctor | error-doctor |
|-------|----------------|----------------|--------------|
| State Machine lifecycle | FULL (~97 lines) | Brief pointer only | SM-001 full (~121 lines) |
| State Guards in OnBarUpdate | 2-line quick-ref | FULL (~25 lines) | Cross-ref in RT-001/RT-002 |
| Namespace imports | FULL (~30 lines) | Via template only | Cross-ref in CS0246 |
| Runtime constraints (.NET 4.8) | FULL (~12 lines) | FULL forbidden table (~20 lines) | Symptoms only (CS codes) |
| Forbidden C# patterns | Brief note only | FULL (~20 lines) | Symptoms only (CS codes) |
| OnBarUpdate guards | 2-line quick-ref | FULL (~25 lines) | Symptoms in RT-001/RT-002 |
| Thread safety | 2-line note | FULL (~23 lines) | LG-007 entry |
| Built-in indicators | None | FULL | None |
| Draw.* methods | None | FULL | SDX-009 entry only |
| SharpDX rendering patterns | None | FULL | None |
| SharpDX crash database | None | None | FULL |
| Property decoration | None | FULL | None |
| Enum placement rule | None | FULL (in property section) | 3-line note in CS0246 |
| Class hierarchy | FULL (~14 lines) | None | None |
| Multi-series patterns | None | FULL | RT-013 entry |
