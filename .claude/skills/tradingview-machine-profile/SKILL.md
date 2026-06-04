# TradingView Machine Profile

Invoke this skill when the user asks you to:
- Connect to TradingView Desktop or verify MCP connectivity
- Explain TradingView Desktop, Pine Editor, compiler, or Strategy Tester behavior
- Work on Pine Script in this repo and you need platform limits, execution model, or local DEEP6 context first
- Route a TradingView/Pine request to the correct downstream skill

## Skill Entry Point

Load `knowledge.md` in this directory first.

## Workflow

1. Read `knowledge.md` for the platform model, local DEEP6 context, and routing table.
2. Confirm whether the task is platform/setup, Pine building, Pine debugging, MCP operation, or strategy/backtesting.
3. Route to the minimum downstream skill set needed.
4. For DEEP6-specific Pine scripts, also load `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\deep6\deep6-patterns.md`.

## Downstream Skills

- `tradingview-pinescript-builder-doctor` — build indicators, strategies, libraries, alerts, and DEEP6 Pine features
- `tradingview-pinescript-error-doctor` — fix compile/runtime/repainting/MTF issues
- `tradingview-mcp-trading-operator` — chart control, Pine injection, compile loops, screenshots, alerts
- `tradingview-strategy-backtesting-operator` — Strategy Tester, trade interpretation, backtest quality, risk settings

## Base path: `C:\Users\Tea\DEEP6\.claude\skills\tradingview-machine-profile\`
