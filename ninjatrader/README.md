# DEEP6 NinjaTrader Layer

NinjaTrader / NinjaScript execution-oriented implementation for DEEP6.

This directory contains the NT8-facing part of the project:
- indicators
- strategies
- add-ons
- setup and workflow docs
- NT8-specific tests and support tooling

For overall project truth, read first:
- `../README.md`
- `../docs/CURRENT-STATE.md`
- `../docs/VERIFICATION-LADDER.md`

## Current role

The NinjaTrader layer should be understood as:
- the active execution-oriented runtime path in the repo
- the NT8/NinjaScript implementation surface
- the likely paper/live progression path when broker/API constraints make direct Python execution impractical

It should not be assumed that:
- all parity work is complete
- all Python reference logic is already fully ported
- all paper-to-live gates are fully hardened

## What is here

Key contents include:
- `Custom/` — NT8-facing code mirrored against NinjaTrader custom folders
- `docs/` — setup, architecture, signal, and ATM guidance
- `tests/` — NT8/C# test coverage and parity-oriented fixtures
- `scripts/` — NT8 deployment and automation helpers
- `simulator/` — simulation and support tooling

## Recommended reading order

1. `docs/SETUP.md`
2. `docs/ARCHITECTURE.md`
3. `docs/SIGNALS.md`
4. `docs/ATM-STRATEGIES.md`
5. relevant strategy/indicator code under `Custom/`

## Relationship to the Python reference engine

The Python side of DEEP6 remains the broadest reference architecture in the repository.
The NT8 layer should be treated as an execution-oriented implementation path, not as proof that every subsystem is already fully aligned.

In practice, this means:
- signal logic should be compared against the Python reference where parity matters
- divergence should be treated as something to measure, not assume away
- paper-mode confidence should come from verification artifacts, not from code shape alone

## Operational posture

Use the NT8 layer for:
- chart-side visualization and workflow validation
- strategy/runtime evaluation inside NinjaTrader
- paper-trading progression where appropriate
- execution-oriented implementation work

Do not treat this README as a claim of full live-readiness.
Promotion toward live operation should follow the DEEP6 verification and paper-to-live documents.

## Status guidance

Treat the NT8 layer as substantial and active, but still subject to:
- parity verification
- replay/paper validation
- explicit release gating
- operator safety review

## Companion docs

Read alongside:
- `../docs/CURRENT-STATE.md`
- `../docs/VERIFICATION-LADDER.md`
- `../docs/PAPER-TO-LIVE-GATE.md`
- `../docs/RELEASE-CHECKLIST.md`
