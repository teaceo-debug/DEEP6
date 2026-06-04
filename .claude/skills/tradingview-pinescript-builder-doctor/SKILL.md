# TradingView PineScript Builder Doctor

Invoke this skill when the user asks you to:
- Build a Pine Script indicator, strategy, or library
- Add alerts, labels, tables, lines, boxes, or webhook payloads to a Pine script
- Design a TradingView strategy for backtesting or signal visualization
- Implement DEEP6-specific Pine logic such as anchors, context overlays, or webhook bridges

## Skill Entry Point

1. Load `knowledge.md` in this directory first.
2. Then load only the one downstream article that matches the request.

## Workflow

**Inventory convention**: When creating new DEEP6 Pine scripts, update the inventory in `deep6/deep6-patterns.md`.

1. Confirm whether the task is an indicator, strategy, library, alert/webhook script, or DEEP6 integration script.
2. Read the matching article from `patterns/`, `strategies/`, or `deep6/`.
3. Build with the smallest viable architecture.
4. If compile/runtime problems appear, hand off to `tradingview-pinescript-error-doctor`.
5. If MCP interaction is needed, also load `tradingview-mcp-trading-operator`.

## Dependencies

- `tradingview-machine-profile` — platform context and routing
- `tradingview-pinescript-error-doctor` — repair loop once the build hits errors
- `tradingview-mcp-trading-operator` — paste/compile/inspect on live chart
- `tradingview-strategy-backtesting-operator` — validate strategy behavior after build

## Base path: `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\`
