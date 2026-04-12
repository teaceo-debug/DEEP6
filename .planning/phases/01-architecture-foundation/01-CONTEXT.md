# Phase 1: Architecture Foundation - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Decompose the 1,010-line monolithic DEEP6.cs into partial classes via the AddOns/ pattern, and fix all GC hot-path allocations. Zero behavior change — every engine score, signal label, and rendered pixel must be identical before and after.

</domain>

<decisions>
## Implementation Decisions

### File Decomposition Strategy
- **D-01:** Use AddOns/ partial classes pattern. Engine logic moves to `AddOns/` as `partial class DEEP6` files. NT8 compiles AddOns separately from Indicators — no wrapper code conflict. This is the community-validated pattern for large NinjaScript projects.
- **D-02:** Granularity is Claude's discretion. Analyze the code structure and pick the right split (likely ~10-15 files: one per engine E1-E7 + Scorer + Session + SharpDX + WPF + State/Params + Core facade).
- **D-03:** Each engine file contains its Run method + its private state fields + its helper methods. Clean boundaries for future testing and independent modification.

### GC Fix Priority
- **D-04:** Fix ALL GC hot-path issues in Phase 1 before any new code is written in Phase 2+. This includes:
  - Std() → Welford's online algorithm (O(1) per update, zero allocations)
  - SolidColorBrush per cell → pre-allocated gradient palette in InitDX()
  - List.RemoveAll() → circular buffer with timestamp-based eviction
  - LINQ in Scorer (.Zip().Sum(), .Average()) → manual loops with pre-allocated arrays
- **D-05:** E3 CounterSpoof moves from per-tick (OnMarketDepth, 1,000x/sec) to per-bar (OnBarUpdate). Reduces GC pressure dramatically. Acceptable tradeoff: spoof detection latency increases from ~1ms to ~1 bar duration.

### Validation Approach
- **D-06:** Two-layer validation (belt and suspenders):
  1. **Signal output checksum:** Before refactor, run DEEP6 on a known NQ session and export all engine scores + signals to CSV. After refactor, run same session, compare CSVs byte-for-byte. Any diff = regression.
  2. **Visual side-by-side:** Before/after screenshots of same chart with same data. Manual comparison of labels, colors, positions, and rendering quality.
- **D-07:** Validation runs on Windows NT8 box (macOS cannot compile/run NT8).

### Engine Boundary Design
- **D-08:** Each engine partial class file is self-contained: Run method + state fields + helper methods. No cross-engine state sharing except through the Scorer's well-defined input interface (direction + score per engine).

### Claude's Discretion
- File granularity — Claude picks the right number of files based on code analysis
- Exact circular buffer implementation for E3/E4 queues
- Whether to keep #region blocks within individual engine files for sub-organization
- Order of GC fixes within Phase 1 (all must complete, sequence is flexible)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Codebase Analysis
- `.planning/codebase/ARCHITECTURE.md` — Engine locations (line ranges), layer boundaries, data flow
- `.planning/codebase/CONCERNS.md` — GC hotspots with specific line numbers, fix approaches
- `.planning/codebase/CONVENTIONS.md` — Code style, naming patterns, NinjaScript-specific conventions
- `.planning/codebase/STRUCTURE.md` — Directory layout, file inventory

### Research
- `.planning/research/ARCHITECTURE.md` — NT8 partial class decomposition strategy, AddOns pattern validation
- `.planning/research/PITFALLS.md` — Monolithic growth risk, GC pressure risk, Pine→NT8 execution model differences
- `.planning/research/STACK.md` — NT8 C# architecture, .NET 4.8 constraints

### Source Code
- `Indicators/DEEP6.cs` — The monolith being decomposed (1,010 lines)

</canonical_refs>

<code_context>
## Existing Code Insights

### Engine Locations (from ARCHITECTURE.md)
- `RunE1()` lines 334-387 (Footprint — absorption/exhaustion/stacked imbalances)
- `RunE2()` lines 389-402 (Trespass — DOM queue imbalance)
- `RunE3()` lines 406-424 (CounterSpoof — Wasserstein-1 + cancel detection)
- `RunE4()` lines 427-442 (Iceberg — native + synthetic detection)
- `RunE5()` lines 446-456 (Micro — Naïve Bayes combination)
- `RunE6()` lines 460-480 (VP+CTX — DEX-ARRAY + VWAP + IB + GEX)
- `RunE7()` lines 484-505 (ML Quality — Kalman + logistic classifier)
- `Scorer()` lines 509-526

### GC Hotspots (from CONCERNS.md)
- `Std()` helper lines 421-423 — LINQ ToArray/Sum/Average on every E3 call
- `RenderFP()` lines 636-641 — new SolidColorBrush per imbalanced cell per render
- `_pLg.RemoveAll()` line 412 — full list scan in E3 per-tick
- `_pTr.RemoveAll()` line 434 — full list scan in E4 per-tick
- `Scorer()` lines 501, 503 — .Zip().Sum() and .Average() LINQ allocations

### Established Patterns
- NinjaScript lifecycle: OnStateChange → State.Configure / State.DataLoaded / State.Terminated
- Event handlers: OnMarketDepth (per-tick), OnBarUpdate (per-bar), OnRender (per-frame)
- SharpDX: InitDX/DisposeDX pattern for GPU resource management
- WPF: BuildUI called once, UpdatePanel called per-bar

### Integration Points
- After decomposition, `Indicators/DEEP6.cs` becomes a thin facade calling into AddOns/ partial classes
- All engine state fields must be accessible within the partial class (they share the same class instance)
- SharpDX resources (brushes, fonts) initialized in InitDX must be accessible to RenderFP/RenderSigBoxes/RenderStk

</code_context>

<specifics>
## Specific Ideas

- Research confirmed AddOns/ pattern avoids NT8 wrapper code generation conflicts that Indicators/ partial classes encounter
- The 1,200-line warning threshold from ROADMAP.md success criteria should be enforced — no individual file should approach this limit
- E3 moving to OnBarUpdate is a deliberate design decision, not just an optimization — it simplifies the hot path and makes the per-tick callback path (OnMarketDepth) leaner for E2/E4 which genuinely need per-tick data

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-architecture-foundation*
*Context gathered: 2026-04-12*
