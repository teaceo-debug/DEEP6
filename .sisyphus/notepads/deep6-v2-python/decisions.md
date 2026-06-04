# Decisions — deep6-v2-python

## 2026-05-14 — Session Start

- Plan: deep6-v2-python (XL, 41 tasks + 4 final verification)
- Execution order: Wave 1 (T1 first, T2-T6 parallel) → Wave 2 (T7-T12 parallel) → Wave 3 (T13-T20 parallel) → etc.
- TDD approach: every task follows RED-GREEN-REFACTOR
- No copy-paste from reference implementations — implement from algorithm descriptions
- Fixtures: adapt from NT8 sources (translate signal IDs and bar indices to v2 conventions)
- TRAP signals: implement but disabled by default (R3 weight=0.0)
- E10 (Kronos): purely advisory, does NOT modify final_score

## 2026-05-23 — Discovery schema

- Discovery loop uses one DuckDB file with exactly three tables: `iterations`, `trades`, `strategies`.
- Convenience query helpers stay read-only; CRUD happens directly through DuckDB.
- Default artifact path: `data/backtests/discovery_loop.duckdb`.

## 2026-05-23 — Config validation layer

- Added `deep6/backtest/config_validator.py` as the semantic validation layer above `param_bounds.validate_config()`.
- Validation returns structured `ValidationResult` objects with errors and warnings instead of mutating configs.
- `suggest_fix()` remains heuristic-only and returns hints keyed by parameter/problem type.

## 2026-05-23 — Backtest harness CLI

- Implement `deep6/backtest/harness.py` as a preprocessed-session runner that consumes pickle payloads only; no live replay path or session-file mutation.
- Emit machine-readable JSON on normal runs and reserve human-readable `VALIDATION PASS` output for `--validate` mode so other tooling can parse results reliably.
- Use a simple 68% chronological IS split by sorted `session_YYYY-MM-DD.pkl` filenames, with status rejection only for insufficient IS trade count and threshold misses captured in `rejection_reasons`.
