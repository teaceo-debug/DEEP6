# Phase 2: Absorption + Exhaustion Core - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

All 4 absorption variants (classic, passive, stopping volume, effort-vs-result) and all 6 exhaustion variants (zero print, exhaustion print, thin print, fat print, fading momentum, bid/ask fade) fire correctly from live FootprintBar data with proper narrative prioritization. This phase validates, calibrates, and completes the existing engine code — not a greenfield build.

**Key reality:** The absorption.py (223 lines), exhaustion.py (269 lines), and narrative.py (225 lines) engines already exist and fire on real Databento NQ data. This phase is about verification, gap closure, and wiring missing requirements (ABS-06, ABS-07, EXH-07).

</domain>

<decisions>
## Implementation Decisions

### Signal Thresholds
- **D-01:** Use current hardcoded defaults for all thresholds until Phase 7 (vectorbt parameter sweep). Do not hand-tune now — the backtest framework will optimize systematically.
- **D-02:** Thresholds must be extracted into a config dict or dataclass so Phase 7 can sweep them. No magic numbers buried in logic.

### Validation Methodology
- **D-03:** Validate signals by running the backtest script on 5+ trading days of Databento NQ data and visually spot-checking the top 20 highest-strength signals against TradingView charts.
- **D-04:** Systematic validation deferred to Phase 7 (Databento replay parity check). For now, "signals fire on bars where the defining footprint condition is present" is confirmed by code review + spot-check.

### VA Extremes Bonus (ABS-07)
- **D-05:** Wire absorption-at-VA-extremes conviction bonus in this phase. The volume profile engine and POC/VA computation already exist in `deep6/engines/poc.py` and `deep6/engines/volume_profile.py`. The bonus flag should be set on the AbsorptionSignal when price is within 2 ticks of VAH or VAL.

### Confirmation Logic (ABS-06)
- **D-06:** Defense window = 3 bars after absorption signal fires. Defense defined as: price holds within absorption zone (doesn't break through by more than 2 ticks) AND at least one bar shows same-direction delta.
- **D-07:** Zone score upgrade on confirmation is +2 points (additive to base absorption score). This feeds into Phase 7 scorer.

### Delta Trajectory Gate (EXH-07)
- **D-08:** Exhaustion signals require delta trajectory divergence confirmation — exhaustion only fires when cumulative delta is fading relative to price direction. This gate already exists in the fading_momentum detector but needs to be applied as a filter to all exhaustion sub-types, not just fading_momentum.

### Narrative Cascade
- **D-09:** Priority order is LOCKED: absorption > exhaustion > momentum > rejection > quiet. Already implemented in narrative.py.
- **D-10:** Narrative labels must be human-readable trading callouts (e.g., "SELLERS ABSORBED @VAH", "EXHAUSTION — ZERO PRINT"). Already implemented, verify format consistency.

### Cooldown
- **D-11:** Exhaustion cooldown suppresses same sub-type for 5 bars after firing. Already implemented — verify it works correctly and doesn't leak across session boundaries.

### Claude's Discretion
- Exact strength calculation formulas (already implemented, Claude verifies correctness)
- Test structure and coverage targets
- Config dataclass field naming

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Signal Specifications
- `.planning/REQUIREMENTS.md` §ABS (lines 29-37) — ABS-01 through ABS-07 acceptance criteria
- `.planning/REQUIREMENTS.md` §EXH (lines 39-48) — EXH-01 through EXH-08 acceptance criteria

### Existing Engine Code
- `deep6/engines/absorption.py` — 4 absorption variants, AbsorptionSignal dataclass
- `deep6/engines/exhaustion.py` — 6 exhaustion variants, ExhaustionSignal dataclass, cooldown logic
- `deep6/engines/narrative.py` — classify_bar(), NarrativeType enum, cascade priority
- `deep6/engines/poc.py` — POC/VA computation (needed for ABS-07 VA extremes bonus)
- `deep6/engines/volume_profile.py` — SessionProfile with zone detection

### Data Pipeline (Phase 1)
- `deep6/state/footprint.py` — FootprintBar, FootprintLevel, price_to_tick/tick_to_price
- `deep6/data/databento_feed.py` — Historical replay for validation
- `scripts/backtest_signals.py` — Full signal backtest pipeline

### Phase 1 Context
- `.planning/phases/01-data-pipeline-architecture-foundation/01-CONTEXT.md` — Prior decisions on bar config, RTH, validation

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `AbsorptionSignal` dataclass: bar_type, direction, price, wick, strength, wick_pct, delta_ratio, detail
- `ExhaustionSignal` dataclass: bar_type, direction, price, strength, detail
- `classify_bar()` in narrative.py: already wires absorption + exhaustion detection with cascade
- `SessionProfile` in volume_profile.py: provides VA high/low for ABS-07
- `backtest_signals.py`: end-to-end validation pipeline using Databento

### Established Patterns
- Engines return lists of signal dataclasses (not bitmasks — bitmask is at scorer level)
- `detect_absorption(bar, prior_bar, atr, vol_ema)` → list[AbsorptionSignal]
- `detect_exhaustion(bar, prior_bar, bar_index, atr, vol_ema)` → list[ExhaustionSignal]
- `classify_bar()` orchestrates both detectors and returns a NarrativeResult

### Integration Points
- `scoring/scorer.py` already consumes narrative output — changes to signal format must be backwards-compatible
- `backtest_signals.py` calls `classify_bar()` — same entry point for validation

</code_context>

<specifics>
## Specific Ideas

- Databento API key is live and validated — use for all historical validation
- Polygon API key is live — GEX context available for future zone bonus integration
- April 10, 2026 NQ data confirmed working as validation dataset
- backtest_signals.py already produces per-bar signal attribution with P&L — use this for signal quality verification

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-absorption-exhaustion-core*
*Context gathered: 2026-04-13*
