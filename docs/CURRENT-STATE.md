# DEEP6 Current State

This document is the canonical truth for what DEEP6 is today.

If any other project document conflicts with this one, treat this document as authoritative until the conflict is resolved.

## Executive summary

DEEP6 is currently a multi-layer trading system project with:

1. a substantial Python reference engine,
2. an active NinjaTrader/NinjaScript execution path,
3. and a dashboard/replay visualization layer.

It is not yet a fully unified, single-runtime production system.

## Canonical interpretation

### Python (`deep6/`)
Use this as:
- reference implementation
- signal logic source
- replay/backtest environment
- API/backend layer
- dashboard integration layer

Do not assume:
- this is the only live runtime path
- this is the final broker/execution path
- all documented ops flows are fully hardened

### NinjaTrader (`ninjatrader/`)
Use this as:
- execution-oriented implementation
- active runtime direction for NT8-based workflows
- paper/live progression path where broker/API constraints require it

Do not assume:
- all parity or live gating work is complete
- all research/reference capabilities are already fully ported

### Dashboard (`dashboard/`)
Use this as:
- operator-facing visualization
- replay surface
- signal/score/status UI

Do not assume:
- it is the sole source of operational truth
- all backend contracts are fully stabilized
- every doc about ports/endpoints is current

## What works today

The repository clearly contains meaningful implementation across:

- stateful Python architecture
- signal engines and scoring
- replay/backtesting components
- execution/risk components
- FastAPI/websocket surfaces
- dashboard rendering and replay controls
- NT8/NinjaScript porting/execution work
- broad test coverage

## What is still immature or inconsistent

The biggest current weaknesses are not raw code volume. They are:

- project identity drift
- runtime entrypoint ambiguity
- documentation/code mismatch
- port/env mismatch
- paper/live gating clarity
- replay/live parity formalization
- operator health visibility
- install/bootstrap determinism

## Current risks

### 1. Project truth drift
Different docs describe DEEP6 differently:
- Python-first live system
- NT8-first execution system
- dashboard/demo system

This must be unified.

### 2. Runtime ambiguity
There is not yet one clearly dominant startup path for the whole system.

### 3. Operational overstatement
Some docs describe procedures that read more mature than the codebase currently proves.

### 4. Verification fragmentation
There are many tests and many artifacts, but the promotion ladder is not yet centralized into one formal, trustable process.

## What is deferred

Unless explicitly reactivated, treat the following as deferred or non-primary:

- fully unified single-command runtime
- fully hardened paper-to-live promotion path
- complete docs/code alignment
- complete replay/live parity reporting
- complete operator-confidence surfaces
- any “best-ever” performance claims without hard evidence

## Near-term priorities

DEEP6 should prioritize:

1. one project truth
2. one runtime truth
3. one verification ladder
4. one operator safety story
5. one bootstrap/install story

## Decision rule

Before adding major new features, ask:

- Does this improve clarity?
- Does this improve verification?
- Does this improve safety?
- Does this improve operator trust?

If not, it is probably lower priority than consolidation work.
