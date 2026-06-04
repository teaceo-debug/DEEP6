# TradingView PineScript Builder Doctor — Master Knowledge Index

Last verified: 2026-05-22

## Purpose

This skill is the DEEP6 project layer for building Pine indicators, strategies, alerts, and integration scripts.
It does **not** try to replace a full Pine language manual. It focuses on build-time decision making, DEEP6 patterns, and when to route to debugging or MCP operations.

## Query Routing Map

- “Build me an indicator” → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\patterns\indicator-architecture.md`
- “Build me a strategy” → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\strategies\strategy-architecture.md`
- “Add alerts/webhooks” → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\patterns\alerts-and-webhooks.md`
- “How should DEEP6 Pine scripts be structured?” → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\deep6\deep6-patterns.md`

## Build Principles

1. Start with the correct declaration: indicator vs strategy vs library.
2. Keep state explicit: `var` for persistent objects, guarded series for history access.
3. Build non-repainting defaults unless the user explicitly requests otherwise.
4. Add visual objects with lifecycle discipline: create once, update deliberately, prune when capped.
5. Keep alerts and webhook payloads deterministic and inspectable.

## DEEP6 Source Anchors

- `C:\Users\Tea\DEEP6\Indicators\sd_anchor_ai.pine` — complex v6 indicator with dynamic history control, pivot scanning, MTF context, and scoring logic
- `C:\Users\Tea\DEEP6\scripts\po3_webhook_additions.pine` — JSON alert payload builder and event-driven webhook bridge
- `C:\Users\Tea\DEEP6\docs\TRADINGVIEW-CHART-READING-GUIDE.md` — chart-reading conventions relevant to visual tool design

## When To Route Out

- compile/runtime/repainting/MTF failures → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\knowledge.md`
- live compile/screenshot/object inspection/alerts on chart → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-mcp-trading-operator\knowledge.md`
- strategy validation and Strategy Tester interpretation → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-strategy-backtesting-operator\knowledge.md`

## File Inventory

- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\SKILL.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\knowledge.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\patterns\indicator-architecture.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\patterns\alerts-and-webhooks.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\strategies\strategy-architecture.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\deep6\deep6-patterns.md`

## Conventions

- Load only one article per build question unless the task clearly spans multiple areas.
- Prefer `indicator()`/`strategy()` arguments that make behavior explicit.
- Route errors out; do not turn build sessions into ad hoc debugging encyclopedias.

## Reference Documents

- `C:\Users\Tea\DEEP6\dashboard\agents\pinescript-expert.md` — complete Pine function reference for build-time signature lookup
- `C:\Users\Tea\DEEP6\dashboard\agents\pinescript-to-python-converter.md` — Pine→Python conversion patterns for DEEP6/VBT integration
