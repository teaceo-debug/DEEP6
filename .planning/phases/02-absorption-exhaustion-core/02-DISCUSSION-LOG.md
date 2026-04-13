# Phase 2: Absorption + Exhaustion Core - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-13
**Phase:** 02-absorption-exhaustion-core
**Areas discussed:** Signal thresholds, Validation methodology, VA extremes bonus, Confirmation logic

---

## Signal Thresholds

| Option | Description | Selected |
|--------|-------------|----------|
| Calibrate now | Hand-tune against backtest data | |
| Defaults until Phase 7 | Use hardcoded defaults, vectorbt sweeps later | ✓ |

**User's choice:** Defaults until Phase 7 (auto-selected, user confirmed "all" areas with defaults)
**Notes:** Thresholds must be extractable into config for Phase 7 sweep.

---

## Validation Methodology

| Option | Description | Selected |
|--------|-------------|----------|
| Visual spot-check | Review top signals against TradingView | ✓ |
| Systematic comparison | Automated divergence measurement | |
| Trust the math | Skip validation, tune in Phase 7 | |

**User's choice:** Visual spot-check of top signals on 5+ days
**Notes:** Systematic replay parity deferred to Phase 7.

---

## VA Extremes Bonus (ABS-07)

| Option | Description | Selected |
|--------|-------------|----------|
| Wire now | Connect to existing POC/VA engine | ✓ |
| Defer to Phase 5 | Wait for Zone Registry | |

**User's choice:** Wire now — POC/VA engine already exists.

---

## Confirmation Logic (ABS-06)

| Option | Description | Selected |
|--------|-------------|----------|
| 3-bar window | Defense within 3 bars upgrades score | ✓ |
| 5-bar window | Longer confirmation window | |

**User's choice:** 3-bar window, +2 points on confirmation.
**Notes:** Defense = price holds within zone + same-direction delta in at least one bar.

---

## Claude's Discretion

- Strength calculation formulas
- Test structure and coverage
- Config dataclass naming

## Deferred Ideas

None
