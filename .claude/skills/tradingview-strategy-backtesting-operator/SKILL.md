# TradingView Strategy Backtesting Operator

Invoke this skill when the user asks you to:
- evaluate a Pine strategy in Strategy Tester
- interpret trades, equity, or performance metrics
- improve backtest realism, risk assumptions, or execution settings
- debug why a strategy enters no trades, too many trades, or unrealistic trades

## Skill Entry Point

Load `knowledge.md` in this directory first.

## Workflow

1. confirm the script is actually a `strategy()` script
2. inspect Strategy Tester outputs
3. classify the issue: no trades, wrong trades, unrealistic fills, risk misconfiguration, or reporting/interpretation
4. route compile/runtime faults to `tradingview-pinescript-error-doctor`

## Dependencies

- `tradingview-machine-profile`
- `tradingview-mcp-trading-operator`
- `tradingview-pinescript-error-doctor`

## Base path: `C:\Users\Tea\DEEP6\.claude\skills\tradingview-strategy-backtesting-operator\`
