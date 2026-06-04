# Decisions — superdom-intelligence-layer

## 2026-05-27 — Wave 4 completion + outstanding gaps
- FEATURE_NAMES is a 10-element stable API contract (feature_builder.py)
- Calibration module rejects Tier-1 mechanical events
- All heuristic detectors use SignalId.REGIME_CHANGE placeholder
- **OUTSTANDING GAP**: DetectorRegistry.create_default() has NOT been updated to register DOM detectors — must be done in Wave 5 or a dedicated registry wiring task before Final Wave
- DOM_INTELLIGENCE_ENABLED env var feature flag (feature_flags.py) controls the registry wiring

## 2026-05-27 — Plan kickoff decisions

### Architecture Boundary
- This plan EXTENDS deep6v2 — does NOT replace it
- `deep6v2/signals/dom/` is the new detector package (peer to existing signals/)
- Live adapter wraps existing `RithmicClient` (deep6v2/data/rithmic_client.py) — does NOT recreate transport
- Replay adapter wraps existing `ReplayEngine` (deep6v2/backtest/replay_engine.py)
- depth-radar (v1) is optional reference — not a hard dependency

### Detector Tier Definitions (LOCKED)
- Tier 1 Mechanical: imbalance, absorption, sweep+reload, iceberg/refill, CVD, thinness/depth asymmetry
- Tier 2 Heuristic: pull/replace trap, micro-momentum, large trade burst, micro-vol ratio, TPS intensity
- Tier 3 Discretionary Overlay Only: stacked imbalance alone, wall persistence by feel, failed auction, queue nuance, regime shift
- Tier 3 is OUT OF SCOPE for Phase 4 first release

### Replay Safety Metadata (LOCKED)
- Three-value enum: REPLAY_SAFE, LIVE_ONLY, REPLAY_DEGRADED
- This metadata is informative for gating — must NOT silently change score semantics

### NQ-Only Scope (LOCKED)
- All phases through dashboard/demo are NQ only
- Multi-instrument readiness is explicitly out of scope

### Compatibility Gate A (MANDATORY before Wave 3+)
- Tasks 7A, 7B, 7C must complete before ANY registry/scorer mutation
- Must produce: old→new signal/scorer mapping, backward-compat fixtures, rollback rule
