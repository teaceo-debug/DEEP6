# TradingView Strategy Backtesting Operator — Master Knowledge Index

Last verified: 2026-05-22

## Purpose

This skill covers Strategy Tester use, strategy-quality interpretation, and backtest realism for Pine strategies in DEEP6.

## Primary Questions This Skill Answers

- Why are there no trades?
- Why do the trades look unrealistic?
- Which strategy flags are materially changing behavior?
- How should results, trades, and equity be inspected through MCP?

## Core Checks

1. declaration is `strategy()`
2. entry conditions are visible and actually occur
3. exits reference the correct entry IDs
4. date/session filters are not suppressing everything
5. `calc_on_every_tick`, `process_orders_on_close`, and `use_bar_magnifier` are intentional
6. commission, slippage, and sizing assumptions are explicit

## MCP Reads To Use

- strategy results
- trade list
- equity curve
- chart screenshots and study values when context matters

## Debugging Articles

- no trades, signals invisible, gating suspicion → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-strategy-backtesting-operator\debugging\no-trades.md`
- strategy declaration flags changing fill behavior or realism → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-strategy-backtesting-operator\debugging\execution-flags.md`

## Routing

- broken logic or repainting suspicion → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-error-doctor\playbooks\repainting-and-mtf.md`
- structural strategy design changes → `C:\Users\Tea\DEEP6\.claude\skills\tradingview-pinescript-builder-doctor\strategies\strategy-architecture.md`

## File Inventory

- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-strategy-backtesting-operator\SKILL.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-strategy-backtesting-operator\knowledge.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-strategy-backtesting-operator\debugging\no-trades.md`
- `C:\Users\Tea\DEEP6\.claude\skills\tradingview-strategy-backtesting-operator\debugging\execution-flags.md`

## Conventions

- Do not trust a backtest just because it compiles.
- Always interpret results in terms of the configured execution model.
