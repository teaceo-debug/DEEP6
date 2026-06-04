# NT8 Backtesting Expert Skill

Invoke this skill when the user wants to:
- Run a backtest in NinjaTrader 8 Strategy Analyzer
- Download or import historical data for backtesting
- Optimize strategy parameters (exhaustive, genetic, walk-forward)
- Debug why backtest results differ from live trading
- Write NinjaScript strategy code that backtests accurately
- Understand Strategy Analyzer settings, metrics, or output
- Set up multi-timeframe or multi-instrument backtests
- Improve backtest fill accuracy (Tick Replay, OrderFillResolution)
- Export or interpret backtest performance results
- Build optimization-ready strategies with proper parameter exposure

## Entry Point

1. Load `knowledge.md` in this directory first.
2. Classify the task as one of:
   - **data acquisition** — downloading, importing, or verifying historical data
   - **strategy analyzer operation** — running backtests, optimization, walk-forward
   - **code correctness** — writing or debugging NinjaScript for accurate backtesting
   - **results interpretation** — reading metrics, diagnosing discrepancies, exporting
   - **fill accuracy** — Tick Replay, OrderFillResolution, intrabar granularity
3. Route to the matching section of `knowledge.md`.

## Invariants

- Never assume data is present. Always verify data exists for the requested instrument, date range, and bar type before running any backtest.
- Distinguish **Tick Replay** (intra-bar indicator updates) from **OrderFillResolution** (intra-bar order fills). They cannot be used together.
- Distinguish **Market Replay** (playback .nrd files with Level II) from **Historical Data** (OHLC bars). They are different data pipelines.
- Treat `Calculate.OnBarClose` as the safe default for backtesting. Only use `OnEachTick` with Tick Replay enabled.
- Set `BarsRequiredToTrade` >= the longest indicator period in the strategy. Failure to do this is the #1 cause of invalid backtest results.
- Set realistic slippage (2-5 ticks for NQ) and commission before trusting any profit figure.
- Never trust optimization results without Walk-Forward validation or out-of-sample testing.
- If backtest shows >90% win rate or >5.0 profit factor on a meaningful sample, suspect overfitting before celebrating.

## Scope Boundaries

| Task | Owner |
|------|-------|
| Downloading Market Replay .nrd files | `nt8-playback-operator` (for download workflow), this skill (for understanding what to download) |
| Playback UI control (play/pause/step) | `nt8-playback-operator` |
| Strategy code compilation errors | `nt8-fix` or `nt8-build-verify` |
| Strategy enablement on live chart | `nt8-strategy-operations` |
| Chart visual verification after backtest | `nt8-chart-verification` |
| Python-side backtest/replay research | DEEP6 Python replay/backtest stack |
| Writing new NinjaScript from scratch | `nt8-new` (for generation), this skill (for backtest-correct patterns) |
| Platform installation or corruption | `nt8-install-repair` |

## OpenCode Skills (Universal NT8 Knowledge)

Use when broader platform/NinjaScript knowledge is needed:
- `ninjatrader-builder-doctor` — NinjaScript development patterns
- `ninjatrader-machine-profile` — NT8 platform, state machine, namespaces
- `ninjatrader-error-doctor` — Compile errors, runtime exceptions
