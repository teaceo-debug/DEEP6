# TradingView Machine Profile — Master Knowledge Index

Last verified: 2026-05-22

## Purpose

This skill is the foundation layer for TradingView and Pine Script work in DEEP6.
It explains what TradingView is responsible for in this repo, what the MCP bridge can and cannot do, and which project skill should be loaded next.

## DEEP6 Role of TradingView

TradingView is an analysis, validation, replay, and visualization surface in DEEP6.
It is **not** the canonical execution engine. In this repo, TradingView is primarily used for:

- Pine Script indicator and strategy development
- visual review of price action, levels, and signal context
- MCP-assisted chart control, screenshots, Pine compilation, and alert setup
- comparing Pine-side behavior against Python-side DEEP6 logic

Primary local references:

- `C:\Users\Tea\DEEP6\docs\TRADINGVIEW-CHART-READING-GUIDE.md`
- `C:\Users\Tea\DEEP6\deep6v2\tradingview\client.py`
- `C:\Users\Tea\DEEP6\deep6v2\tradingview\analysis.py`
- `C:\Users\Tea\DEEP6\tests_v2\tradingview\test_client.py`
- `C:\Users\Tea\DEEP6\tests_v2\tradingview\test_analysis.py`

## Local Platform Facts

- TradingView tasks should assume MCP-first operation when possible.
- `deep6v2.tradingview.client.TradingViewClient` currently degrades gracefully when not connected.
- Visual capture in repo code is used for signal review and reporting, not live execution authority.
- Pine work in this repo should preserve originals and prefer versioned repaired copies for risky debugging sessions.

## Platform Surface Areas

### 1. Pine Editor / Compiler
- script header: `//@version=5` or `//@version=6`
- single declaration: `indicator()`, `strategy()`, or `library()`
- editor diagnostics can differ from server compile output
- runtime failures often appear only after chart compile or replay/scroll interaction

### 2. Strategy Tester
- strategies only, not indicators
- results depend on broker emulator assumptions
- `calc_on_every_tick`, `process_orders_on_close`, and `use_bar_magnifier` materially change behavior

### 3. MCP Bridge
- chart state
- Pine source read/write
- compile and error retrieval
- screenshots
- drawn-object inspection
- alert operations

## Routing Table

- “Connect to TradingView”, “why is MCP not working?”, “what tools do I use first?” → stay in this skill and then load `tradingview-mcp-trading-operator`
- “Build a Pine indicator/strategy/library” → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\knowledge.md`
- “Fix a Pine error”, “it repaints”, “strategy is broken”, “won’t compile” → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\knowledge.md`
- “Run Strategy Tester properly”, “read trades/equity”, “improve backtest realism” → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-strategy-backtesting-operator\knowledge.md`
- “Paste script, compile it, inspect labels/lines/boxes, create alerts” → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-mcp-trading-operator\knowledge.md`

## HERMES Routing Note

If Hermes or any DEEP6 implementation agent is handling a TradingView request, load this skill first when the task is ambiguous. This skill exists to reduce wrong-skill loading and to route toward the smallest correct downstream bundle.

## File Inventory

- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-machine-profile\SKILL.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-machine-profile\knowledge.md`

## Conventions

- Use absolute paths only.
- Load this skill first when the TradingView task is ambiguous.
- Do not turn this file into a full Pine reference. Route out to the task-specific skill.
