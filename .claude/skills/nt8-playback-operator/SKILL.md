# NT8 Playback Operator Skill

Invoke this skill when the user wants to:
- download NinjaTrader Market Replay data
- set up or control NT8 Playback sessions
- play, pause, step forward, rewind, or jump around in playback
- validate replay sessions for backtesting or visual review
- connect replay downloads to DEEP6 replay, parity, or backtest workflows

## Entry Point

1. Load `knowledge.md` in this directory first.
2. Classify the task as one of:
   - replay data download
   - playback window/control operations
   - replay-session verification
   - DEEP6 replay/backtest orchestration
3. Reuse existing DEEP6 replay assets before inventing a new workflow.

## Invariants

- Distinguish **Market Replay download** from **Playback control**. They are related but not the same workflow.
- Treat `nt8-replay-download.ps1` as the production-ready download path.
- Treat playback control primitives as more fragile until verified on the current NT8 UI state.
- If the task is Python-side replay/backtest research rather than NT8 playback UI, route through the DEEP6 replay/backtest stack instead of forcing NT8 UI automation.
- If on-chart truth matters after playback changes, hand off to `nt8-chart-verification`.

## OpenCode Skills (Universal NT8 Knowledge)

Use these when broader platform knowledge is needed:
- `ninjatrader-machine-profile`
- `ninjatrader-builder-doctor`
