# DEEP6 Evidence Index

This document maps important DEEP6 claims to evidence.

Purpose:
- reduce hand-waving
- make claims auditable
- show what is implemented vs intended
- prevent “confidence by complexity”

## How to read this

Each row includes:
- claim
- current status
- evidence
- confidence
- notes

Status values:
- Implemented
- Partial
- Planned
- Unverified

Confidence values:
- High
- Medium
- Low

## Evidence table

| Claim | Status | Evidence | Confidence | Notes |
|------|--------|----------|------------|-------|
| Python reference engine exists and is substantial | Implemented | `deep6/`, `tests/` | High | Core architecture is broad and real |
| Dashboard/replay UI exists and is substantial | Implemented | `dashboard/`, dashboard docs/tests | High | UI architecture clearly present |
| NT8 execution-oriented implementation exists | Implemented | `ninjatrader/` | High | Active path in repo |
| Signal engine architecture exists | Implemented | `deep6/engines/` | High | Multiple engines and tests present |
| Scoring architecture exists | Implemented | `deep6/scoring/` | High | Present in code/tests |
| Risk/execution layer exists | Implemented | `deep6/execution/` | Medium | Present, but operational promotion story still needs tightening |
| Replay/backtest infrastructure exists | Implemented | `deep6/backtest/`, tests | High | Present and meaningful |
| Backend/API layer exists | Implemented | `deep6/api/` | High | FastAPI/websocket surfaces present |
| Live operational story is fully unified | Unverified | conflicting docs/entrypoints | Low | Needs canonical runtime truth |
| Paper-to-live promotion gate is fully hardened | Partial | docs + code fragments | Low | Needs explicit coded and documented ladder |
| Replay/live parity is formalized and measured | Partial | parity-oriented artifacts exist | Medium | Needs central report + thresholds |
| Operator health surface is sufficient for trust | Partial | health-related pieces exist | Low | Needs unified operator-facing health view |
| Project documentation is aligned | Unverified | root/docs/planning drift exists | Low | Major improvement area |
| Startup/bootstrap path is deterministic | Partial | multiple paths exist | Low | Needs consolidation |
| Advanced overlays / ML stack are fully production-integrated | Partial | mixed docs/code presence | Low | Some deferred, some partial |

## Required upgrades to this file

This file should evolve into a stronger artifact with links to:
- specific test files
- replay reports
- parity reports
- paper-trade summaries
- release candidate checklists

## Evidence policy

A claim should not be promoted in README or sales-style docs unless:
- it has code evidence,
- verification evidence,
- or is explicitly labeled planned.

## Default rule

If DEEP6 cannot point to evidence for a claim, the claim should be downgraded.
