# Phase 1: Architecture Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-12
**Phase:** 01-architecture-foundation
**Areas discussed:** File decomposition strategy, GC fix priority order, Validation approach, Engine boundary design

---

## File Decomposition Strategy

### Q1: How should DEEP6.cs be split into multiple files?

| Option | Description | Selected |
|--------|-------------|----------|
| AddOns/ partial classes | NT8 compiles AddOns separately — community pattern for large NinjaScript | ✓ |
| Indicators/ partial classes | All files in Indicators/ — simpler but may conflict with NT8 wrapper | |
| Separate engine classes | Each engine is own class — cleanest OOP but requires interface passing | |

**User's choice:** AddOns/ partial classes (Recommended)

### Q2: How granular should the split be?

| Option | Description | Selected |
|--------|-------------|----------|
| By layer (~8 files) | Core, Engines, Session, Scorer, SharpDX, WPF, State, Params | |
| By engine (~15 files) | One file per engine + Scorer + Session + SharpDX + WPF + State + Params | |
| You decide | Claude picks based on code structure | ✓ |

**User's choice:** You decide

---

## GC Fix Priority Order

### Q3: Which GC fixes are most critical?

| Option | Description | Selected |
|--------|-------------|----------|
| Fix all before any new code | Std() Welford + brush palette + circular buffers + LINQ removal — all in Phase 1 | ✓ |
| Hot path first, render later | Fix Std() and RemoveAll() immediately, defer brushes to Phase 3 | |
| You decide | Claude prioritizes based on severity | |

**User's choice:** Fix all before any new code

### Q4: Should E3 CounterSpoof move from per-tick to per-bar?

| Option | Description | Selected |
|--------|-------------|----------|
| Move to OnBarUpdate | E3 runs once per bar — dramatic GC reduction, +1 bar latency | ✓ |
| Keep per-tick, fix allocations | E3 stays per-tick with Welford — preserves sub-bar detection | |
| You decide | Claude evaluates tradeoff | |

**User's choice:** Move to OnBarUpdate (Recommended)

---

## Validation Approach

### Q5: How to verify zero behavior change?

| Option | Description | Selected |
|--------|-------------|----------|
| Signal output checksum | CSV export before/after, byte-for-byte comparison | |
| Visual side-by-side | Screenshots of same chart, manual comparison | |
| Both | CSV checksum + visual comparison — belt and suspenders | ✓ |
| Windows box handles it | User validates manually on Windows | |

**User's choice:** Both

---

## Engine Boundary Design

### Q6: How much logic goes into each engine file?

| Option | Description | Selected |
|--------|-------------|----------|
| Run method + state fields + helpers | Self-contained engine files — clean boundaries for testing | ✓ |
| Run method only | State in core file — less refactoring but tighter coupling | |
| You decide | Claude evaluates per-engine | |

**User's choice:** Run method + state fields + helpers

---

## Claude's Discretion

- File granularity (number of files)
- Circular buffer implementation details
- Sub-organization within engine files
- Order of GC fixes within Phase 1

## Deferred Ideas

None
