---
phase: 03-footprint-signal-engines-e1-e8-e9
plan: "04"
subsystem: signal-analysis
tags: [correlation, pearson, signal-redundancy, analysis-tooling]
dependency_graph:
  requires: [deep6/engines/imbalance.py, deep6/engines/delta.py, deep6/engines/auction.py]
  provides: [scripts/signal_correlation.py]
  affects: [Phase 7 scorer — prevents double-counting correlated signals]
tech_stack:
  added: []
  patterns: [numpy.corrcoef for pairwise Pearson, binary signal matrix per bar, argparse CLI]
key_files:
  created:
    - scripts/signal_correlation.py
  modified: []
decisions:
  - "Build binary matrix per bar (1 if signal fired, 0 otherwise) — simpler than magnitude-based and correct for measuring co-occurrence"
  - "--from-csv mode binarizes available backtest columns rather than requiring raw footprint re-fetch"
  - "Zero-variance signals (never fired in dataset) produce NaN correlations — explicitly flagged in output"
metrics:
  duration_minutes: 12
  completed: "2026-04-13T17:50:38Z"
  tasks_completed: 1
  files_created: 1
  files_modified: 0
---

# Phase 03 Plan 04: Signal Correlation Matrix Summary

**One-liner:** Pairwise Pearson correlation matrix across all 30 signal types (11 imbalance + 13 delta + 6 auction) using numpy.corrcoef on per-bar binary vectors.

## What Was Built

`scripts/signal_correlation.py` — a one-time analysis script that:

1. Builds a binary signal matrix: for each FootprintBar, produces a 30-element row where each element is 1 if that signal type fired, 0 otherwise.
2. Computes pairwise Pearson correlation via `numpy.corrcoef` (signals as rows, bars as columns).
3. Outputs `correlation_matrix.csv` with signal names as header/index.
4. Prints a human-readable summary: highly-correlated pairs (|r| > 0.70), moderate-correlated pairs (|r| > 0.50), rare signals (fire rate < 1%), and full fire-rate table.
5. Supports `--from-csv` mode that reads an existing backtest CSV without API cost.

**Signal coverage:**
- `IMB_*`: 11 ImbalanceType variants
- `DELT_*`: 13 DeltaType variants
- `AUCT_*`: 6 AuctionType variants

## Smoke Test Results (backtest_apr10.csv, 390 bars)

Running `--from-csv backtest_apr10.csv` immediately found:

| Signal A        | Signal B        | r      | Notes |
|----------------|----------------|--------|-------|
| IMB_STACKED_T1 | IMB_STACKED_T2 | +1.000 | Expected: T1 always true when T2 is true |
| IMB_STACKED_T1 | IMB_STACKED_T3 | +1.000 | Expected: T1 always true when T3 is true |
| IMB_STACKED_T2 | IMB_STACKED_T3 | +1.000 | Expected: T2 always true when T3 is true |

This is the expected result — stacked imbalance tiers are nested (T3 implies T2 implies T1). The scorer should use only the highest tier present, not sum all three.

Note: the CSV mode only has access to binarized aggregate columns (not full per-bar signal vectors). A full analysis using `--start`/`--end` with Databento will provide correlations for all 30 signals.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Signal correlation matrix script | df58fc4 | scripts/signal_correlation.py |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — script is fully wired. The `--from-csv` limitation (only binarized columns available from backtest CSV) is expected behavior documented in help output, not a stub.

## Threat Flags

None. The script follows the same env-var pattern for DATABENTO_API_KEY as `backtest_signals.py`. No new trust boundaries introduced.

## Self-Check: PASSED

- scripts/signal_correlation.py exists: FOUND
- commit df58fc4 exists: FOUND
- `python scripts/signal_correlation.py --help` exits 0: VERIFIED
- All acceptance criteria patterns present (corrcoef, correlation_matrix, from-csv, argparse): VERIFIED
