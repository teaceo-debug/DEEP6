# TradingView PineScript Error Doctor

Invoke this skill when the user asks you to:
- Fix Pine compile errors, runtime failures, editor diagnostics, or broken strategy behavior
- Diagnose repainting, MTF, request.security, bars-back, or drawing-object issues
- Repair alert scripts, webhook payload scripts, or chart-object lifecycle bugs
- Build an expert Pine error knowledge base grounded in official TradingView error docs and real-world failure patterns

## Skill Entry Point

1. Load `knowledge.md` in this directory first.
2. Then load the single matching error article or playbook.

## Workflow

1. Classify the problem: official error code, common compile error, runtime failure, repainting/MTF, visual-object bug, alert bug, or strategy bug.
2. Read the matching article.
3. Follow the repair playbook.
4. If live chart verification is needed, also load `tradingview-mcp-trading-operator`.

## Dependencies

- `tradingview-machine-profile` — platform/routing context
- `tradingview-mcp-trading-operator` — source capture, compile, screenshot, object inspection
- `tradingview-strategy-backtesting-operator` — validate repaired strategy behavior

## Base path: `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\`
