# Task 3 Evidence: V8 Parity Report

**Task:** Validate which Python codebase maps to DEEP6FootprintV7.cs C# signal detection.
**Date:** 2026-05-24

## Files Analyzed

| File | Role | Lines |
|------|------|-------|
| `deep6/engines/absorption.py` | Python v1 absorption detector | 243 |
| `deep6/engines/exhaustion.py` | Python v1 exhaustion detector | 316 |
| `deep6/engines/signal_config.py` | Python v1 config (thresholds) | 521 |
| `deep6v2/signals/absorption.py` | Python v2 absorption detector | 210 |
| `deep6v2/signals/exhaustion.py` | Python v2 exhaustion detector | 296 |
| `ninjatrader/.../AbsorptionDetector.cs` | C# absorption detector | 234 |
| `ninjatrader/.../ExhaustionDetector.cs` | C# exhaustion detector | 388 |
| `.planning/.../PORT-SPEC.md` | Authoritative port specification | 303 |

## Verdict

**Python v1 (`deep6/engines/`) is the authoritative source for V7/V8 C# detectors.**

- All 10 signal variants: **MATCH** (Python v1 ↔ C#)
- All 10 signal variants: **MISMATCH** (Python v2 ↔ C#)
- All 16+ numerical thresholds: **EXACT MATCH** (Python v1 ↔ C#)
- All derived constants (strength formulas, divisors, gate logic): **EXACT MATCH**

## Evidence Method

1. Read all source files in full
2. For each variant: compared algorithm flow, threshold values, strength formulas, direction conventions
3. Verified against PORT-SPEC.md as ground truth
4. Cataloged all Python v2 discrepancies

## Key Findings

1. **C# files explicitly cite Python v1** — line number references in comments (e.g., `deep6/engines/absorption.py detect_absorption() lines 1-244`)
2. **PORT-SPEC.md cites Python v1** — `Source: /deep6/engines/absorption.py:1-244`
3. **Python v2 is a separate reimplementation** — different algorithms, different config structures, missing features
4. **No optimization transfer risk** — Python v1 sweep results directly usable in C#

## Output

Full report: `data/backtests/v8_parity_report.md`
