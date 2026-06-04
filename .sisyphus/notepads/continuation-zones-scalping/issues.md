# Issues — Continuation Zones Scalping

## Known Issues in Source Code
- ScoreZone(): EMA re-evaluated every bar via EMA(Closes[bip], 50)[1] — expensive in MTF
- UpdateDynamicScorePieces(): drops trend/overlap components for performance but leaves Score inconsistent
- FindPrimaryBarsAgo(): linear scan O(n) — fine for drawing but not for Python port
- TouchCount tracking uses CurrentBars[BarsInProgress] which is TF-relative — ensure Python parity uses correct bar index

## Design Risks
- Data leakage risk: confirmation bar [nextAgo=0] uses bar CLOSE data. In Python, must ensure bar-close-only access. Zone must NOT be created until nextAgo bar is fully closed.
- O(n²) risk: Python port with nested loops over zones + bars = ~19,500 × N_zones. Must vectorize.
- Optuna sweep size: 10 parameters × varying range = potentially 100k+ combinations. Use TPE sampler with pruning.

## Open Questions
- Does Databento provide ohlcv-5m directly or must we resample from 1m? (check SDK docs)
- What is the exact bar index convention for BarsInProgress in MTF context? (confirm with NT8 docs)
- Does DEEP6 already have Optuna installed? (check requirements.txt)

## CONFIRMED: Missing Dependencies
pyproject.toml does NOT include: databento, optuna, vectorbt, pandas
Research module will need a separate requirements-research.txt or added to pyproject extras
Existing backtest uses: deep6.backtest.strategy_config with BracketExit(stop_ticks, target_ticks, rr_ratio)
Pattern to follow: Pydantic models, frozen configs, config_hash() for dedup

## Existing Backtest Pattern
deep6.backtest.strategy_config has:
  - BracketExit(stop_ticks, target_ticks, rr_ratio)
  - LevelTarget enum (LVN, HVN)
  - StrategyConfig with Pydantic v2
Port ATM profile to this pattern.
