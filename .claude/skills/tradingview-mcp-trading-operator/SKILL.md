# TradingView MCP Trading Operator

Invoke this skill when the user asks you to:
- control the TradingView chart through MCP
- read or replace Pine source in the editor
- compile a script on chart and inspect errors, console output, or drawn objects
- take screenshots, query study values, or manage alerts

## Skill Entry Point

Load `knowledge.md` in this directory first.

## Workflow

1. Confirm MCP/TradingView connectivity first.
2. Choose the narrowest workflow: chart state, Pine source, compile, object inspection, screenshot, or alert operation.
3. Follow the tool sequence in `knowledge.md`.
4. Route strategy interpretation to `tradingview-strategy-backtesting-operator` when needed.

## Dependencies

- `tradingview-machine-profile` — connection/routing context
- `tradingview-pinescript-error-doctor` — when compile/runtime issues need diagnosis

## Base path: `C:\Users\Tea\DEEP6\.claude\skills\tradingview-mcp-trading-operator\`
