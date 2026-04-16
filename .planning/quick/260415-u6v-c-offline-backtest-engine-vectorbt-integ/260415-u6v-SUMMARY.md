---
phase: quick-260415-u6v
plan: 01
subsystem: backtest
tags: [backtest, vectorbt, csharp, nunit, python, csv, e2e]
dependency_graph:
  requires: [CaptureReplayLoader, ConfluenceScorer, ScorerEntryGate, SignalTier]
  provides: [BacktestRunner, CsvTradeExporter, vbt_harness]
  affects: [deep6/backtest/, ninjatrader/Custom/AddOns/DEEP6/Backtest/]
tech_stack:
  added: [vectorbt 0.28.5, plotly (optional heatmap), numpy, pandas, argparse]
  patterns: [TDD NUnit, Python-side trade simulator mirroring C# logic, vbt.Portfolio.from_orders()]
key_files:
  created:
    - ninjatrader/Custom/AddOns/DEEP6/Backtest/BacktestConfig.cs
    - ninjatrader/Custom/AddOns/DEEP6/Backtest/Trade.cs
    - ninjatrader/Custom/AddOns/DEEP6/Backtest/BacktestResult.cs
    - ninjatrader/Custom/AddOns/DEEP6/Backtest/BacktestRunner.cs
    - ninjatrader/Custom/AddOns/DEEP6/Backtest/CsvTradeExporter.cs
    - ninjatrader/tests/Backtest/BacktestRunnerTests.cs
    - ninjatrader/tests/Backtest/CsvTradeExporterTests.cs
    - ninjatrader/tests/Backtest/BacktestE2ETests.cs
    - deep6/backtest/vbt_harness.py
  modified:
    - ninjatrader/tests/ninjatrader.tests.csproj
decisions:
  - BacktestRunner processes exits in priority order matching plan spec (stop-loss > target > opposing > max-bars > session-end); same order in Python _simulate_trades()
  - Python-side scorer (_score_bar_simple) mirrors C# ConfluenceScorer category logic for sweep/walkforward modes; C# engine remains canonical scorer
  - vbt.Portfolio.from_orders() chosen over from_signals() — trade fills already computed by BacktestRunner, so explicit order arrays are the correct abstraction
  - vectorbt soft-imported so vbt_harness.py is importable without vbt installed; error raised at runtime only when mode actually requires vbt
  - E2E test uses .venv/bin/python3 as first candidate (FindPython3 priority list); gracefully Assert.Ignore if python3 unavailable
  - ScoreEntryThreshold=40 / MinTierForEntry=TYPE_C used in fixture tests and E2E to ensure real session bars produce entries (TYPE_A requires zoneScore>0 which stubs at 0 in many bars)
metrics:
  duration_min: ~18
  completed_date: "2026-04-15"
  tasks_completed: 4
  files_created: 9
  files_modified: 1
---

# Phase quick-260415-u6v Plan 01: C# Offline Backtest Engine + vectorbt Integration Summary

**One-liner:** NT8-API-free BacktestRunner replays scored-bar NDJSON through ConfluenceScorer + ScorerEntryGate with 5 exit conditions; CsvTradeExporter + vbt_harness.py close the C# → CSV → vectorbt → HTML report pipeline.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | BacktestRunner core + data types (C#) | 372c33d | BacktestConfig, Trade, BacktestResult, BacktestRunner, CsvTradeExporter |
| 2 | NUnit tests for BacktestRunner + CsvTradeExporter | 1e4fd46 | BacktestRunnerTests (12 tests), CsvTradeExporterTests (3 tests) |
| 3 | Python vectorbt harness (3 modes) | 1a3dd93 | deep6/backtest/vbt_harness.py |
| 4 | E2E integration test | 90812ac | BacktestE2ETests (2 tests) |

## What Was Built

### C# Backtest Engine (NT8-API-free)

**BacktestConfig** — 11 configurable fields with NQ defaults (SlippageTicks=1, StopLossTicks=20, TargetTicks=40, MaxBarsInTrade=30, ScoreEntryThreshold=80, MinTierForEntry=TYPE_A).

**BacktestRunner.Run(config, ndjsonPaths)** — for each session file:
1. `CaptureReplayLoader.LoadScoredBars()` streams scored_bar records
2. `ConfluenceScorer.Score()` scores each bar
3. If in a trade: checks exits in order — stop-loss → target → opposing signal → max bars
4. If flat: `ScorerEntryGate.Evaluate()` gates entries; entry price includes directional slippage
5. Forces SESSION_END exit at last bar

**BacktestResult** — 9 computed summary properties: WinRate, AvgWinTicks, AvgLossTicks, ProfitFactor, MaxDrawdownTicks, MaxConsecutiveLosses, SharpeEstimate (mean/std×√252), NetPnlDollars.

**CsvTradeExporter** — 14-column CSV with InvariantCulture numerics, pipe-delimited CategoriesFiring, CSV-quoting for narratives containing commas.

### Python vectorbt Harness (3 modes)

**mode import**: `pd.read_csv()` → `vbt.Portfolio.from_orders()` → `pf.stats()` saved as JSON + `pf.plot().write_html()` as report.html.

**mode sweep**: 32-combo grid (4 thresholds × 2 tiers × 4 stop-losses) using Python-side `_simulate_trades()` that mirrors C# exit priority exactly. Saves sweep_results.csv + plotly heatmap HTML per tier.

**mode walkforward**: 60/20/20 split, optimise on train, validate, report test Sharpe. Saves walkforward_report.json with `{train_params, train_sharpe, validate_sharpe, test_sharpe, passed}`.

### Test Coverage

| Suite | Tests | Result |
|-------|-------|--------|
| Existing (pre-task) | 238 | all green |
| BacktestRunnerTests | 12 | all green |
| CsvTradeExporterTests | 3 | all green |
| BacktestE2ETests | 2 | all green |
| **Total** | **255** | **255/255 green** |

E2E test produced 24 trades from 5 sessions (scoring-session-01 through 05), exported CSV, invoked `.venv/bin/python3 -m deep6.backtest.vbt_harness --mode import`, and confirmed report.html was generated.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertion wrong for MaxConsecutiveLosses**
- **Found during:** Task 2 TDD RED run
- **Issue:** Test `Run_BacktestResult_SummaryStats_Correct` asserted `MaxConsecutiveLosses == 0` but the 2 losses appended at end of the trade list form a consecutive run of 2 — the implementation correctly returned 2.
- **Fix:** Updated assertion to `Assert.AreEqual(2, result.MaxConsecutiveLosses, "2 losses appended at end = max run of 2")`.
- **Files modified:** ninjatrader/tests/Backtest/BacktestRunnerTests.cs
- **Commit:** 1e4fd46

**2. [Rule 2 - Missing critical functionality] vectorbt soft-import guard**
- **Found during:** Task 3
- **Issue:** Plan said to import vectorbt unconditionally but vbt_harness.py also needs to be importable for unit/CI contexts where vectorbt may not be installed.
- **Fix:** Wrapped `import vectorbt as vbt` in try/except with `_VBT_AVAILABLE` flag; added runtime check in `_trades_to_vbt_portfolio()`.
- **Files modified:** deep6/backtest/vbt_harness.py

**3. [Rule 2 - Missing critical functionality] E2E test uses permissive thresholds**
- **Found during:** Task 4 analysis of session fixtures
- **Issue:** Default ScoreEntryThreshold=80 + MinTierForEntry=TYPE_A requires `zoneScore > 0` (TypeA gate requires zone_bonus > 0 per Phase 18 known stub). With `zoneScore=0` on most bars, zero trades would be produced and E2E would fail.
- **Fix:** E2E test uses ScoreEntryThreshold=40 + MinTierForEntry=TYPE_C to produce entries from real fixture bars. This matches the constraint documented in Phase 18 state ("zoneScore=0.0 stub: VPContext zone proximity deferred").
- **Files modified:** ninjatrader/tests/Backtest/BacktestE2ETests.cs, BacktestRunnerTests.cs (same fix applied to fixture test in Task 2)

## Known Stubs

None — the backtest engine is fully wired. The `zoneScore=0` stub is a pre-existing Phase 18 constraint (VPContext not yet wired) documented in STATE.md, not introduced by this plan.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundary crossings introduced. CSV temp files are cleaned up in TearDown per T-u6v-02 mitigation. 30-second subprocess timeout enforced per T-u6v-03 mitigation.

## Self-Check: PASSED

Files verified present:
- ninjatrader/Custom/AddOns/DEEP6/Backtest/BacktestRunner.cs — FOUND
- ninjatrader/Custom/AddOns/DEEP6/Backtest/CsvTradeExporter.cs — FOUND
- ninjatrader/tests/Backtest/BacktestRunnerTests.cs — FOUND
- ninjatrader/tests/Backtest/BacktestE2ETests.cs — FOUND
- deep6/backtest/vbt_harness.py — FOUND

Commits verified:
- 372c33d — FOUND (BacktestRunner core)
- 1e4fd46 — FOUND (NUnit tests)
- 1a3dd93 — FOUND (vbt_harness)
- 90812ac — FOUND (E2E test)

Test count: 255/255 green (dotnet test confirmed).
