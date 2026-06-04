# DEEP6 Repository Guide

This document explains what each major part of the repository is for and where to start.

## Top-level intent

DEEP6 is not a single small app.
It is a trading-system repository with multiple layers:

- reference engine
- execution-oriented implementation
- operator UI
- replay/backtest tooling
- planning/history

## Top-level directories

### `deep6/`
Primary Python codebase.

Contains:
- data ingestion
- state management
- signal engines
- scoring
- execution/risk logic
- backtest/replay logic
- API/backend surfaces

Use this directory when you want to understand:
- the reference architecture
- signal logic
- scoring logic
- Python-side system design

### `dashboard/`
Next.js frontend.

Contains:
- operator UI
- replay controls
- websocket client logic
- state stores
- chart rendering logic

Use this directory when you want to understand:
- how live/replay data is presented
- frontend architecture
- operator-facing UX
- dashboard/backend contracts

### `ninjatrader/`
NinjaTrader / NinjaScript implementation.

Contains:
- NT8-facing indicators/strategies/addons
- NT8 setup/handoff docs
- execution-oriented implementation work
- NT8-specific tests and support files

Use this directory when you want to understand:
- execution/runtime direction in NT8
- ported logic
- NT8 deployment and workflow

### `tests/`
Python test suite.

Use this directory when you want to understand:
- what Python behavior is verified
- where integration boundaries exist
- what the repo considers important enough to test

### `docs/`
Project documentation.

Important docs should live here for:
- current state
- runbooks
- verification ladder
- architecture summaries
- repo navigation

### `scripts/`
Utilities and helpers.

Typical contents:
- demo broadcasters
- health checks
- startup wrappers
- diagnostics
- replay helpers

Rule:
Business logic should ideally live in package modules, not permanently in scripts.

### `.planning/`
Research, phased work, design history, roadmap material.

Use this directory when you want:
- historical context
- decision history
- phase artifacts
- research rationale

Do not treat it as the canonical source for current runtime truth.
That belongs in:
- `README.md`
- `docs/CURRENT-STATE.md`

## Where to start by goal

### “I want to understand the project quickly”
Read:
1. `README.md`
2. `docs/CURRENT-STATE.md`
3. `docs/VERIFICATION-LADDER.md`

### “I want to understand the Python architecture”
Read:
1. `deep6/`
2. key docs in `docs/`
3. `tests/`

### “I want to understand the NT8 direction”
Read:
1. `ninjatrader/README.md`
2. `ninjatrader/docs/`
3. relevant NT8 tests/files

### “I want to understand the dashboard”
Read:
1. `dashboard/README.md`
2. `dashboard/docs/ARCHITECTURE.md`
3. `dashboard/components/`
4. `dashboard/hooks/`
5. `dashboard/store/`

### “I want to know what is actually trustworthy today”
Read:
1. `docs/CURRENT-STATE.md`
2. `docs/VERIFICATION-LADDER.md`
3. test suites
4. replay/parity/paper-trade artifacts

## Canonical truth hierarchy

When docs disagree, use this order:

1. `docs/CURRENT-STATE.md`
2. `README.md`
3. subsystem README/docs
4. planning/history docs

If lower-level docs conflict with higher-level docs, they should be updated.

## Repository discipline rules

As the project matures, prefer:

- one canonical runtime path
- one canonical port/env story
- one canonical runbook
- one canonical verification ladder
- one place for current truth

Avoid:
- runtime truth living only in planning docs
- stale historical claims at the root
- multiple contradictory startup instructions
- undocumented schema or endpoint drift
- stale host-specific absolute paths in operator-facing docs and scripts
