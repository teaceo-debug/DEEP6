# TradingView MCP Trading Operator — Master Knowledge Index

Last verified: 2026-05-22

## Purpose

This skill defines the operational sequences for using the TradingView MCP bridge safely and efficiently in DEEP6.

## Canonical Tool Sequences

### Connectivity
1. `tv_health_check`
2. if disconnected, route to TradingView machine/profile and connection doctor behavior

### Capture Current Pine Context
1. `chart_get_state`
2. `pine_get_source`
3. `pine_get_errors`
4. `pine_get_console`

### Offline-First Debugging
1. `pine_analyze`
2. `pine_check`
3. only then `pine_set_source`
4. `pine_smart_compile`

### Visual Verification
1. `chart_get_state`
2. `data_get_study_values`
3. object readers as needed:
   - `data_get_pine_labels`
   - `data_get_pine_lines`
   - `data_get_pine_boxes`
   - `data_get_pine_tables`
4. `capture_screenshot`

### Alerts
1. confirm script logic
2. inspect with `alert_list`
3. create or update alerts deliberately

## DEEP6 Usage Notes

- TradingView is a validation surface, not the execution source of truth.
- Prefer MCP reads before UI-click fallbacks.
- Use screenshots and object readers to verify what the Pine script actually drew, not what the code seems like it should draw.

## Detailed Workflows

- compile / fix / re-compile loop → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-mcp-trading-operator\workflows\compile-loop.md`
- inspect Pine-drawn labels, lines, boxes, tables, and study values → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-mcp-trading-operator\workflows\object-inspection.md`
- screenshot-driven chart and strategy verification → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-mcp-trading-operator\workflows\screenshot-verification.md`

## Routing

- if the task becomes build/design → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\knowledge.md`
- if the task becomes diagnosis/repair → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\knowledge.md`
- if the task becomes strategy interpretation → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-strategy-backtesting-operator\knowledge.md`

## File Inventory

- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-mcp-trading-operator\SKILL.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-mcp-trading-operator\knowledge.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-mcp-trading-operator\workflows\compile-loop.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-mcp-trading-operator\workflows\object-inspection.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-mcp-trading-operator\workflows\screenshot-verification.md`
