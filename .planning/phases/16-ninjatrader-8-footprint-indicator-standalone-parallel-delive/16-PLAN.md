# Phase 16 Plan — NT8 Footprint Indicator

**Goal:** Deliver a NinjaTrader 8 indicator that renders the DEEP6 footprint with absorption/exhaustion markers and optional GEX overlay, built in parallel to (not replacing) the Python system.

**Status:** Built in single autonomous session (2026-04-14).

## Deliverables — all built

| Path | Purpose |
|---|---|
| `ninjatrader/src/FootprintBar.cs` | Cell, FootprintBar, POC / VAH-VAL computation, delta quality scalar |
| `ninjatrader/src/AbsorptionDetector.cs` | 4 variants + ABS-07 VA proximity bonus |
| `ninjatrader/src/ExhaustionDetector.cs` | 6 variants + delta trajectory gate + cooldown state |
| `ninjatrader/src/MassiveGexClient.cs` | massive.com options chain → GEX profile (gamma flip, call wall, put wall) |
| `ninjatrader/src/DEEP6Footprint.cs` | Main indicator — OnMarketData, OnBarUpdate, OnRender, properties grid, generated-region regions |
| `ninjatrader/README.md` | Project overview |
| `ninjatrader/docs/SETUP.md` | Install + first-run troubleshooting |
| `ninjatrader/docs/SIGNALS.md` | Signal reference with thresholds and visuals |
| `ninjatrader/docs/ARCHITECTURE.md` | Data flow, threading, rendering pipeline |

## Build sequence (actual)

1. Research agents (parallel): (a) Python absorption/exhaustion extraction, (b) NT8 NinjaScript patterns, (c) massive.com API shape
2. Wrote canonical port spec: `PORT-SPEC.md` with exact thresholds + algorithms
3. Wrote supporting .cs files (FootprintBar, AbsorptionDetector, ExhaustionDetector, MassiveGexClient) in parallel Write calls
4. Wrote main indicator DEEP6Footprint.cs with OnStateChange lifecycle, L2 intake, OnBarUpdate detector dispatch, custom OnRender, property grid, NT8-generated regions
5. Wrote documentation (README, SETUP, SIGNALS, ARCHITECTURE)
6. Retroactive GSD artifacts (CONTEXT.md, this PLAN.md)

## Verification (non-execution)

- Code review against PORT-SPEC.md: thresholds match, variants match, gate logic matches
- Cannot run on macOS (NT8 is Windows-only)
- User must verify compile on Windows via NT8 NinjaScript Editor F5
- User must verify first render on an NT8 replay chart before promoting to live

## Known risks / follow-ups

- **Compile untested** — written from NT8 docs + reference repos, not from an NT8 compiler. Syntax errors possible. Requires user to run F5 in NT8 and surface any errors for fix.
- **No unit tests** — NT8 lacks a standard test harness. Logic is ported from Python which has a test suite; divergence checks must be manual (replay cross-check vs Python engine).
- **Aggressor classification lower fidelity** than Python's Rithmic raw-field heuristic — documented in SIGNALS.md divergences section.
- **GEX mapping QQQ→NQ via spot ratio** is visual only; treat levels as context, not tradeable.
- **Running NT8 + Python together** requires subscription separation (two Rithmic logins); see SETUP.md troubleshooting.

## Not in scope (deferred to future phases)

- Order entry / strategy class (would make this an NT8 Strategy, not Indicator)
- Kronos E10 bias overlay — Python-only due to PyTorch dependency
- 44-signal stack beyond absorption + exhaustion
- Automated cross-validation harness
