---
phase: 01-architecture-foundation
plan: 02
subsystem: E3-CounterSpoof, E4-Iceberg, Core-EventHandlers
tags: [gc-optimization, circular-buffer, zero-allocation, welford, ninjatrader]
dependency_graph:
  requires: [01-01]
  provides: [zero-alloc-e3-e4, bar-rate-e3]
  affects: [01-03, 01-04]
tech_stack:
  added: []
  patterns: [circular-buffer-ring, queue-struct-enumerator, welford-online-stats]
key_files:
  created: []
  modified:
    - AddOns/DEEP6.E3.cs
    - AddOns/DEEP6.E4.cs
    - AddOns/DEEP6.Core.cs
decisions:
  - "QueueStats uses two-pass foreach on Queue<double> struct enumerator — no ToArray, no LINQ heap allocations"
  - "LgEntry and TrEntry are private structs on the stack — circular buffers are fixed arrays, zero GC"
  - "RunE3 moved to OnBarUpdate per D-05 — Wasserstein-1 reads same sliding window at bar close, semantically equivalent"
  - "Comment text mentions RemoveAll/ToArray as contrast — actual code has zero allocating patterns"
metrics:
  duration: "2 minutes"
  completed: "2026-04-13"
  tasks_completed: 2
  files_modified: 3
---

# Phase 1 Plan 2: GC Hot-Path Elimination (E3/E4/Core) Summary

**One-liner:** Zero-allocation QueueStats + fixed-capacity circular buffers replace LINQ Std() and List RemoveAll() in the E3/E4 hot paths; RunE3 moved from per-tick to per-bar.

## What Was Built

### Task 1 — E3.cs: QueueStats + _pLg circular buffer

**QueueStats (zero-allocation Std replacement):**
- Removed `Std(IEnumerable<double>)` which called `ToArray()`, `Average()`, and `Sum()` with LINQ — three heap allocations per call
- Replaced with `QueueStats(Queue<double> q, out double mean, out double std)` that iterates via `foreach` over Queue's struct enumerator — zero heap allocations in .NET 4.8

**_pLg circular buffer:**
- Removed `List<(DateTime ts, int lv, bool bid)> _pLg`
- Added `private struct LgEntry { public DateTime ts; public int lv; public bool bid; }`
- Added `LgEntry[] _pLgBuf = new LgEntry[1024]` with `_pLgHead` / `_pLgCount` ring indices
- `RunE3()` evicts stale entries by walking the tail — O(entries-to-evict) with no lambda allocation
- `ChkSpoof()` searches the ring buffer and removes found entry by swapping with tail — O(n) scan, no LINQ FirstOrDefault or Remove heap allocation

**Core.cs large-order add sites:**
- Replaced two `_pLg.Add((DateTime.Now, lv, true/false))` calls in `OnMarketDepth` with direct ring-buffer writes (`_pLgBuf[_pLgHead] = new LgEntry{...}; _pLgHead = (_pLgHead+1) % LG_CAP; if (_pLgCount < LG_CAP) _pLgCount++`)

### Task 2 — E4.cs: _pTr circular buffer + Core.cs RunE3 relocation

**_pTr circular buffer:**
- Removed `List<(DateTime ts, double px, bool buy)> _pTr`
- Added `private struct TrEntry { public DateTime ts; public double px; public bool buy; }`
- Added `TrEntry[] _pTrBuf = new TrEntry[1024]` with `_pTrHead` / `_pTrCount` ring indices
- `RunE4()` scans buffer for synthetic iceberg match, then adds current trade and evicts stale tail — no `RemoveAll`, no `foreach (var t in _pTr)` over a List

**Core.cs — RunE3 migration (D-05):**
- Removed `RunE3()` from `OnMarketDepth` end (was called ~1,000 times/sec)
- Added `RunE3()` to `OnBarUpdate` after `RunE1()` — called once per bar
- `_iLong` / `_iShort` queues are populated continuously by `RunE2()` per tick, so `RunE3` reading them at bar close computes the same Wasserstein-1 approximation over the same window — semantically equivalent

## Verification Results

| Check | Result |
|-------|--------|
| `grep "ToArray\|RemoveAll\|\.Average()\|\.Zip(" E3.cs E4.cs` (code only) | 0 allocating code patterns |
| `grep "_pLgBuf\|LgEntry\|LG_CAP\|QueueStats" E3.cs` | 12 matches |
| `grep "_pTrBuf\|TrEntry\|TR_CAP" E4.cs` | 10 matches |
| `grep "_pLg\.Add" Core.cs` | 0 (replaced) |
| `grep "_pLgBuf\[_pLgHead\]" Core.cs` | 2 (both add sites) |
| `grep "RunE3" Core.cs` | Line 35 (OnBarUpdate only) |
| `grep "RunE2" Core.cs OnMarketDepth` | Line 65 (RunE2 only — RunE3 absent) |
| `_w1`, `_spSc`, `_spSt` in RunE3 | All present |
| `_icBull`, `_icBear`, `_icSc`, `_icDir` in RunE4 | All present |

## Deviations from Plan

### Comment text triggers grep false positives

**Found during:** Task 1 verification

**Issue:** Acceptance criteria `grep -c "ToArray\|RemoveAll"` counts 2 matches in E3.cs and 1 in E4.cs. These are in comments explaining the refactor ("no RemoveAll", "no ToArray"), not in executable code.

**Fix:** No code change needed — comments are informational. All actual allocating code is eliminated. The plan's intent (zero allocating code patterns) is fully met.

**Commits:** b728fea (Task 1), 8cb54c0 (Task 2)

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | b728fea | feat(01-02): replace Std()/List<_pLg> with QueueStats/circular buffer in E3 |
| Task 2 | 8cb54c0 | feat(01-02): replace List<_pTr> with circular buffer in E4, move RunE3 to OnBarUpdate |

## Known Stubs

None. All circular buffers are fully wired. QueueStats is called at both _iLong and _iShort call sites. RunE3 is live in OnBarUpdate.

## Readiness for Plan 03

Plan 03 targets the remaining GC hot paths in Render.cs and Scorer.cs:
- `new SolidColorBrush` per cell in `RenderFP()` — pre-allocated gradient palette needed
- `.Zip().Sum()` and `.Average()` LINQ in `Scorer()` — manual loops needed

No dependencies on Plan 02 changes. Plan 03 can proceed immediately.

## Self-Check: PASSED

- [x] `AddOns/DEEP6.E3.cs` — exists, contains QueueStats, LgEntry, _pLgBuf, LG_CAP
- [x] `AddOns/DEEP6.E4.cs` — exists, contains TrEntry, _pTrBuf, TR_CAP
- [x] `AddOns/DEEP6.Core.cs` — exists, RunE3 in OnBarUpdate, RunE2 only in OnMarketDepth
- [x] Commit b728fea — verified in git log
- [x] Commit 8cb54c0 — verified in git log
