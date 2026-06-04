# Handoff State — deep6-v2-python
## Date: 2026-05-14
## Status: ALL IMPLEMENTATION COMPLETE (T1-T41)

## Progress Summary
- Wave 1: COMPLETE (T1-T6) — Foundation ✅
- Wave 2: COMPLETE (T7-T12) — Data Pipeline ✅
- Wave 3: COMPLETE (T13-T20) — 52 Signal Detectors ✅
- Wave 4: COMPLETE (T21-T23) — Scoring & Confluence ✅
- Wave 5: COMPLETE (T24-T27) — Execution ✅
- Wave 6: COMPLETE (T28-T30) — Kronos E10 ✅
- Wave 7: COMPLETE (T31-T34) — Dashboard MVP ✅
- Wave 8: COMPLETE (T35-T36) — TradingView MCP ✅
- Wave 9: COMPLETE (T37-T41) — Operational Hardening ✅
- Final Wave: PENDING (F1-F4) — Verification

## Test Status
`pytest tests_v2/ --ignore=tests_v2/integration -q` → **406 passed, 2 skipped**

## Completed Tasks (Wave 3)
- T13: `deep6v2/signals/absorption.py` — ABS_01..ABS_04 ✅
- T14: `deep6v2/signals/exhaustion.py` — EXH_01..EXH_06 ✅ (delta gate suppression, 9 tests)
- T15: `deep6v2/signals/imbalance.py` — IMB_01..IMB_09 ✅ (stacked T1/T2/T3, imbalance_history recording, 14 tests)
- T16: `deep6v2/signals/delta.py` — DELT_01..DELT_11 ✅ (+ deep6v2/utils/math.py least_squares_slope, 22 tests)
- T17: `deep6v2/signals/auction.py` — AUCT_01..AUCT_05 ✅
- T18: `deep6v2/signals/trap.py` — TRAP_01..TRAP_05 ✅ (disabled-by-default via enabled=False)
- T19: `deep6v2/signals/vol_patterns.py` — VOLP_01..VOLP_06 ✅ (8 tests)
- T20: `deep6v2/signals/engines/` + `registry.py` ✅
  - ENG_02 (Trespass): DOM queue logistic imbalance
  - ENG_03 (CounterSpoof): Wasserstein-1 DOM distance + cancel rate → SPOOF_VETO
  - ENG_04 (Iceberg): fill > displayed, wired via IAbsorptionZoneReceiver
  - ENG_05 (MicroProb): Naive Bayes P(reversal|signals), called post-pass by registry
  - ENG_06 (VPContext): POC/VAH/VAL proximity, LVN zone lifecycle stub
  - ENG_07 (Regime): TRENDING/RANGING/VOLATILE classifier → REGIME_CHANGE meta-flag
  - DetectorRegistry: sequential evaluation, exception isolation, AbsorptionDetector→IcebergDetector wiring

## Wave 3 Gate: PASSED ✅
- 186 passed, 1 skipped
- LSP diagnostics: 0 errors across 16 signal files
- All 52 signal detectors implemented across 8 categories

## Completed Tasks (Wave 4)
- T21: `deep6v2/scoring/scorer.py` — ConfluenceScorer ✅
  - R3 weights, two-layer category scoring, locked multiplier chain
  - All 5 scoring scenario fixtures pass
- T22: `deep6v2/scoring/entry_gate.py` — EntryGate ✅
  - Type A/B/C/QUIET classification, 4 veto conditions, STACKED/VA_EXTREME confluence
- T23: `deep6v2/scoring/hysteresis.py` — HysteresisFSM ✅
  - BiasState FSM (3-bar confirmation, 5-bar decay)
  - is_midday_blocked(), is_initial_balance(), get_ib_multiplier()

## Wave 5 (sequential after Wave 4)
- T24: `deep6v2/execution/rithmic_broker.py` + integration test [deep]
- T25: `deep6v2/execution/fsm.py` — 7-state FSM [deep]
- T26: `deep6v2/execution/risk_manager.py`, `position_manager.py` [deep]
- T27: `deep6v2/execution/paper_trader.py`, `promotion_gate.py`, `kill_switch.py` [unspecified-high]

## Waves 6-9 (parallel with Waves 5+)
- T28-30: `deep6v2/kronos/` — model, pipeline, E10 integration
- T31-34: FastAPI + Next.js dashboard MVP
- T35-36: TradingView MCP integration
- T37-41: Operational hardening

## Final Wave
- F1: Oracle plan compliance audit
- F2: Code quality review
- F3: Agent integration QA
- F4: Scope fidelity check

## Key Architecture Notes

### Types (read these to understand the API contracts)
- `deep6v2/types/signal.py` — SignalId (55 entries), SignalResult, Direction, SIGNAL_TO_CATEGORY
- `deep6v2/types/bar.py` — FootprintBar, SessionType
- `deep6v2/types/session.py` — SessionContext (mutable dataclass, 7 deque histories maxlen=50)
- `deep6v2/types/scoring.py` — SignalTier, ScorerResult
- `deep6v2/types/dom.py` — DOMLevel (price, volume fields), DOMSnapshot
- `deep6v2/types/interfaces.py` — ISignalDetector, IDepthConsumingDetector, IAbsorptionZoneReceiver

### Signal Detector Pattern
```python
from deep6v2.types.signal import SignalId, SignalResult, Direction
from deep6v2.types.bar import FootprintBar
from deep6v2.types.session import SessionContext

class XxxDetector:
    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        results = []
        # ... detect signals ...
        return results
```

### DetectorRegistry Pattern
```python
from deep6v2.signals.registry import DetectorRegistry
registry = DetectorRegistry.create_default()  # wires all detectors
results = registry.evaluate_bar(bar, ctx)  # exception-isolated per detector
```

### Config Thresholds (from SignalConfig)
- imbalance_ratio: 3.0
- absorption_wick_pct: 0.3
- delta_neutrality_threshold: 0.1
- exhaustion_zero_threshold: 0
- fat_print_mult: 2.5
- stopping_mult: 1.5
- effort_mult: 1.5
- effort_range_pct: 0.5
- surge_mult: 3.0
- big_delta_threshold: 200

### R3 Category Weights (LOCKED)
absorption=20.0, exhaustion=15.7, imbalance=25.0, delta=14.3,
volume_profile=20.2, auction=12.6, trapped=0.0, poc=0.0

### Signal Direction Convention
- Absorption at LOW wick → BULLISH (downward move rejected)
- Absorption at HIGH wick → BEARISH (upward move rejected)
- Zero print at TOP of bar → BEARISH exhaustion
- Zero print at BOTTOM of bar → BULLISH exhaustion
- Stacked buy imbalance (ask > bid ratio) → BULLISH
- CVD trending UP while price DOWN → BEARISH divergence

### Fixture format (tests_v2/fixtures/signals/)
60 JSON files (52 individual + 8 composite) with format:
```json
{"name": "...", "bar": {...}, "context": {...}, "expected_signal": {"signal_id": "ABS_01", "direction": "BULLISH", "strength_min": 0.3, "strength_max": 0.5}}
```

### Important Structural Notes
- DOMLevel has: `price` and `volume` (NOT `size` or `order_count`)
- DOMSnapshot has: `bids`, `asks`, `timestamp` (NO best_bid/best_ask properties)
- SessionContext.vol_history: deque of total_volume per bar (for vol_ema calculations)
- SessionContext.imbalance_history: deque[dict[float, float]] — updated by ImbalanceDetector
- SignalConfig: check actual fields in config/signals.py (no passive_mult)
- deep6v2/utils/math.py: least_squares_slope() for DELT-10/polyfit
- TrapDetector: __init__(enabled=False) — disabled by default, R3 weight=0.0
- MicroProbDetector: NOT a standard ISignalDetector — called via registry.evaluate() post-pass

## How to Resume
1. Run `pytest tests_v2/ --ignore=tests_v2/integration -q` to confirm: 222 passed, 1 skipped
2. Proceed to Wave 5 sequential (T24→T25→T26→T27) — execution layer
3. Waves 6-9 can overlap Wave 5
4. T24 (Rithmic broker research spike) must complete before T25-T27

## Boulder.json Location
`C:\Users\Tea\DEEP6\.sisyphus\boulder.json`
- active_plan: deep6-v2-python.md

## Evidence Directory
`C:\Users\Tea\DEEP6\.sisyphus\evidence\`
