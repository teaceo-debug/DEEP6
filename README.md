# DEEP6

Institutional-style order-flow trading system for NQ futures, centered on absorption/exhaustion detection, confluence scoring, replay validation, and controlled execution workflows.

## What DEEP6 is today

DEEP6 currently has three distinct layers:

1. Python reference engine
- Research, signal logic, replay, backtesting, API surfaces, and dashboard integration.
- This is the most complete architecture layer in the repository.

2. NinjaTrader / NinjaScript implementation
- Active execution-oriented runtime path.
- Intended paper/live trading path where direct Python broker/API execution is constrained.

3. Dashboard / replay UI
- Operator-facing visualization layer for footprint data, scores, signals, and session replay.

DEEP6 is not yet a single unified runtime with one fully consolidated startup path. It is a serious, evolving system with:
- a substantial Python reference core,
- an active NT8 execution path,
- and an operator/replay dashboard.

## Core thesis

Absorption and exhaustion are the highest-alpha reversal signals in order flow.

Everything else in DEEP6 exists to:
- confirm them,
- contextualize them,
- suppress weak setups,
- and route only the highest-quality opportunities into execution.

## Current subsystem status

| Subsystem | Role | Status |
|----------|------|--------|
| `deep6/` | Python reference engine, replay, scoring, API | Substantial |
| `ninjatrader/` | NT8/NinjaScript execution-oriented implementation | Active |
| `dashboard/` | Operator dashboard and replay UI | Substantial |
| Backtesting / replay | Validation and iteration | Present |
| Execution safety | Risk and gate framework | Partial / needs hardening |
| Paper-to-live promotion | Operational gate | Needs clearer implementation |
| Advanced ML overlays | Extended capability | Mixed / partial / some deferred |

## What DEEP6 is not yet

DEEP6 is not yet a fully unified, turnkey, single-command production trading platform.

The main gaps are:
- canonical runtime clarity,
- docs/code alignment,
- operational hardening,
- and explicit verification gates.

## Repository structure

- `deep6/`
  Python reference engine: data, state, signal engines, scoring, execution, backtest, API

- `dashboard/`
  Next.js operator dashboard and replay UI

- `ninjatrader/`
  NinjaScript / NT8 implementation and execution-facing work

- `tests/`
  Python test suite

- `docs/`
  System and operations docs

- `scripts/`
  Startup helpers, replay/demo utilities, diagnostics

- `.planning/`
  Research, planning, architecture history, and phased work artifacts

## Recommended reading order

If you are evaluating DEEP6 for the first time:

1. `docs/CURRENT-STATE.md`
2. this README
3. `docs/VERIFICATION-LADDER.md`
4. `docs/REPO-GUIDE.md`

Then inspect:
- `deep6/` for reference architecture
- `ninjatrader/` for execution/runtime direction
- `dashboard/` for operator/replay UX

## Current priorities

Highest-priority work:
- unify runtime/documentation truth
- standardize startup paths, ports, and env configuration
- tighten replay/live parity verification
- harden paper-trade and live promotion gates
- improve operator observability and fault detection

## Running the project

Important:
There are currently multiple entrypoints in the repo. Until runtime consolidation is complete, treat startup instructions as subsystem-specific.

Recommended next docs:
- `docs/CURRENT-STATE.md`
- `docs/RUNBOOK.md`
- `dashboard/README.md`
- `ninjatrader/README.md`

## Validation philosophy

DEEP6 should only promote behavior upward through evidence:

- unit tests
- integration tests
- replay verification
- parity checks
- paper trading
- constrained live exposure

No subsystem should be trusted because it is sophisticated.
It should be trusted because it has been verified.

## Direction

The goal is to turn DEEP6 into a trustable order-flow operating system:
- strong signal detection
- strong operator visibility
- strong replay/live parity
- strong risk discipline
- strong promotion gates

That is more important than adding more features.
