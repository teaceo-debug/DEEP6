# DEEP6 SuperDOM Intelligence Layer

## TL;DR

> **Quick Summary**: Build a DEEP6-native SuperDOM-inspired intelligence layer that converts live DOM behavior into structured signals, replay-safe features, and a trader-facing dashboard surface. This is **not** a clone of TradingOrderFlow SuperDOM Series and **not** an NT8-only standalone tool. It is a detector-first subsystem that reuses DEEP6 depth-radar, detector, scoring, replay, and dashboard patterns.
>
> **Deliverables**:
> - A canonical DOM-intelligence contract: level state, detector outputs, feature rows, replay parity artifacts
> - Tiered detector stack: **mechanical**, **heuristic**, and **discretionary-overlay-only**
> - Integration into the DEEP6 detector/scoring pipeline without UI coupling
> - Replay/live parity harness and golden-session comparison flow
> - A DEEP6 dashboard surface showing chart + DOM ladder + intelligence rail
> - Optional NT8-facing adapters only after the Python truth path is validated
>
> **Estimated Effort**: Large (5 phases + final verification)
> **Parallel Execution**: YES — architecture/data, detectors, dashboard, and verification can be staged in waves
> **Critical Path**: Phase 0 contracts → Phase 1 DOM truth path → Phase 2 mechanical detectors → Phase 3 heuristic/ML features → Phase 4 dashboard surface → Phase 5 parity hardening

---

## Context

### Original Request
User wants to study TradingOrderFlow SuperDOM Series and determine whether DEEP6 can build upon it to provide maximum trader coverage using algorithms, strategies, and machine learning based on DOM knowledge.

### What We Learned

#### SuperDOM Series is best understood as:
- a **discretionary DOM instrumentation layer**
- optimized for **human ladder reading and execution workflows**
- strong in: depth views, updates/pulls/adds, imbalance, tape reconstruction, queue/order tools, pace gauges, and contextual columns
- weak as a direct machine substrate because it is **UI-first**, not **signal-engine-first**

#### The high-value codifiable signal families are:
- **Mechanical / high-confidence**:
  - order book imbalance
  - absorption
  - sweep + reload
  - iceberg/refill
  - cumulative volume delta
  - liquidity thinness / depth asymmetry
- **Heuristic / tunable**:
  - pull/replace trap
  - micro-momentum
  - large trade burst
  - micro-vol ratio
  - trades-per-second intensity
- **Discretionary / overlay only**:
  - stacked imbalance by itself
  - wall persistence “by feel”
  - failed auction interpretation
  - queue nuance as a standalone setup
  - regime-shift judgment

#### Existing DEEP6 assets already cover much of the foundation:
- `deep6/ml/depth_radar/wall_features.py`
- `deep6/ml/depth_radar/classifier.py`
- `deep6/ml/depth_radar/wall_interaction_model.py`
- `deep6/services/depth_radar_service.py`
- `deep6/engines/trespass.py`
- `deep6/engines/iceberg.py`
- `deep6/engines/counter_spoof.py`
- `deep6v2/signals/registry.py`
- `deep6v2/scoring/scorer.py`
- `deep6v2/state/dom.py`
- `deep6v2/backtest/replay_engine.py`
- `dashboard/components/layout/HeaderStrip.tsx`
- `dashboard/components/footprint/FootprintChart.tsx`
- `dashboard/components/signals/SignalFeed.tsx`

### Architectural Decision
This initiative **extends** DEEP6 depth-radar and detector/scoring infrastructure. It does **not** replace them, and it does **not** run as a disconnected shadow system.

More specifically:
- `deep6-v2-python` remains the upstream runtime and integration truth for registry/scoring/replay patterns
- `depth-radar-v2` is a **sibling** effort whose wall-state and classifier concepts may be reused where valuable
- the SuperDOM intelligence layer is a **peer subsystem** that can consume depth-radar-style outputs but must not depend on `depth-radar-v2.md` being implemented first
- live DOM adapter work in this plan is an **adapter over existing DEEP6/Rithmic transport**, not a new transport stack

### Core Design Rule
This plan defines **detectors and structured outputs**, not “columns.”
The UI is a consumer of the intelligence layer, not its home.

---

## Work Objectives

### Core Objective
Build a DEEP6-native DOM intelligence subsystem that translates SuperDOM-style market behavior into:
- structured detector outputs
- replay-safe feature rows
- confluence/scoring inputs
- trader-facing visual surfaces

without coupling computation to the ladder UI.

### Concrete Deliverables
- `deep6v2/types/dom_intelligence.py` (or equivalent) — canonical event/output contract
- `deep6v2/signals/dom/` detector package for mechanical + heuristic DOM detectors
- live DOM adapter bridging `RithmicClient`/DOM state into detector inputs
- replay DOM adapter bridging historical MBO/reconstructed DOM into the same detector inputs
- parity harness for recorded-live vs replay comparisons
- dashboard DOM ladder component + intelligence panel
- plan-level mapping of which signals are:
  - replay-safe
  - live-only
  - visual-overlay-only

### Definition of Done
- [x] DOM intelligence has a single canonical schema for detector outputs and feature rows
- [x] Mechanical detectors run off the same truth path in live and replay
- [x] Each detector is formally classified as mechanical, heuristic, or discretionary-overlay-only
- [x] Replay parity harness exists and compares golden sessions against recorded live outputs
- [x] Dashboard shows a working DEEP6 DOM ladder + intelligence layout without embedding signal logic in the frontend
- [x] The scoring pipeline accepts DOM-intelligence outputs without breaking existing categories
- [x] NQ-only first release is validated with explicit low-liquidity, disconnect, and session-boundary handling

### Must Have
- A **single source of truth** for DOM state consumed by detectors
- A **single source of truth migration contract** proving the new DOM-intelligence path does not create a parallel scorer/registry truth path
- Explicit detector classification:
  - Tier 1 Mechanical
  - Tier 2 Heuristic
  - Tier 3 Discretionary Overlay Only
- Formal detector definitions with quantitative thresholds and feature names
- Golden-session parity workflow: recorded live vs replay output comparison
- UI and signal engine fully separated
- Dashboard uses existing DEEP6 visual language:
  - header strip
  - footprint/chart canvas
  - right intelligence rail
  - replay controls
- NQ-only scope for initial release
- Session-aware and stale-feed-aware behavior
- Detector metadata field for replay safety / confidence mode

### Required Clarifications Locked By This Plan
- **Tier 3 overlay-only signals** are out of scope for Phase 4 and first-release promotion. They may only be reconsidered in a follow-up plan after Phase 5 passes.
- **Replay-safety metadata schema** must be explicit and versioned. Minimum enum set:
  - `REPLAY_SAFE`
  - `LIVE_ONLY`
  - `REPLAY_DEGRADED`
  This metadata is informative for gating, parity reporting, and benchmark inclusion; it must not silently change score semantics.
- **NQ-only** means all phases in this parent plan, including dashboard/demo-state verification. Multi-instrument readiness is out of scope.
- **Live DOM adapter** means adaptation from existing DEEP6/Rithmic state into the DOM-intelligence contract; it must not duplicate upstream feed connection work.

### Must NOT Have (Guardrails)
- **DO NOT** define signal-engine capabilities in terms of UI columns
- **DO NOT** clone the TradingOrderFlow SuperDOM UX pixel-for-pixel
- **DO NOT** couple detector logic to dashboard rendering
- **DO NOT** make order entry or click-trading part of the initial scope
- **DO NOT** add multi-instrument support in the first release
- **DO NOT** rebuild separate competing DOM engines when existing DEEP6 paths can be reused
- **DO NOT** auto-promote heuristic or discretionary ideas into scoring without replay evidence
- **DO NOT** treat live-only timing-sensitive signals as replay-safe by default
- **DO NOT** use visual confirmation as acceptance criteria
- **DO NOT** render Tier 3 overlays in Phase 4; first release is Tier 1 + Tier 2 only

---

## Verification Strategy

> **Signal truth first. UI second.**
> Verification must prove that the DOM-intelligence layer works independent of the ladder surface.

### Test Decision
- **Infrastructure exists**: YES
  - Python tests in `tests_v2/`
  - replay engine patterns in `deep6v2/backtest/`
  - dashboard component tests
- **Automated tests**: Mandatory
- **Framework**:
  - `pytest`
  - targeted parity harnesses
  - dashboard tests where appropriate

### QA Policy
Every phase must produce machine-checkable evidence.

Evidence examples:
- detector unit tests with synthetic DOM scenarios
- false-positive smoke runs on baseline sessions
- replay/live parity diffs for golden sessions
- performance timing under simulated high-frequency updates
- dashboard rendering checks against deterministic mock state

### Required Verification Types
1. **Detector correctness**
   - trigger on expected patterns
   - remain silent on counterexamples
2. **Replay parity**
   - compare detector outputs between recorded-live and replayed sessions
3. **Performance**
   - verify acceptable latency under bursty DOM update load
4. **Safety / stale data handling**
   - disconnect, resume, and low-liquidity edge cases
5. **UI/data separation**
   - dashboard renders structured state only; no detector math in components

---

## Detector Taxonomy

### Tier 1 — Mechanical (Automate in initial release)
These are deterministic enough to integrate directly into the intelligence layer.

1. Order Book Imbalance
2. Absorption
3. Sweep + Reload
4. Iceberg / Refill
5. Cumulative Volume Delta
6. Liquidity Thinness / Depth Asymmetry

### Tier 2 — Heuristic (Implement with tuning + evidence gates)
These are eligible for feature generation and possibly scored outputs, but only after replay evidence.

1. Pull/Replace Trap
2. Micro-Momentum
3. Large Trade Burst
4. Micro-Vol Ratio
5. Trades-per-Second Intensity

### Tier 3 — Discretionary Overlay Only
These may be visualized for the trader but are **not** first-release scored signals.

1. Stacked Imbalance by itself
2. Wall Persistence by feel
3. Failed Auction interpretation
4. Queue nuance as a standalone setup
5. Regime-shift judgment

---

## Execution Strategy

### Phase 0 — Contracts and Boundary Truth
Goal: lock the architecture boundary before any new detector work.

Deliver:
- DOM intelligence contract
- detector taxonomy doc
- replay-safety metadata model
- explicit relationship to depth-radar, detector registry, and scoring
- detector execution model: serial with revised per-detector budget, or parallel with explicit concurrency strategy and measured overhead

### Phase 1 — Canonical DOM Truth Path
Goal: make live and replay consume the same logical DOM-intelligence input model.

Deliver:
- live DOM adapter from `RithmicClient` / DOM state
- replay DOM adapter from MBO/reconstructed history
- golden-session recorder format
- golden-session acquisition set
- stale/disconnect/session-boundary handling
- compatibility fixture pack capturing old-path and new-path contract shapes for downstream consumers

### Phase 2 — Mechanical Detector Pack
Goal: deliver the highest-confidence DOM-intelligence detectors into the registry/scoring flow.

Deliver:
- imbalance detector extension / normalization
- absorption DOM detector
- sweep + reload detector
- iceberg/refill detector enhancements
- thinness/depth asymmetry detector
- CVD integration / feature emission
- exact old→new mapping for any detector outputs that touch existing `SignalId` / scorer semantics

### Phase 3 — Heuristic + ML Feature Layer
Goal: extend the depth-radar/wall-feature foundation without pretending heuristic outputs are ground truth.

Deliver:
- feature-row builder for heuristic signals
- labeling strategy document for Tier 2 evaluation
- pull/replace trap heuristics
- micro-momentum / TPS / burst / micro-vol features
- wall interaction alignment with scoring interfaces
- calibration/threshold evidence rules

### Compatibility Gate A — Before Any Registry/Scorer Mutation
Goal: freeze the migration contract before deeper integration work changes existing scoring behavior.

Required outputs:
- exact mapping from DOM-intelligence outputs to existing `SignalId`, `SignalCategory`, and scorer inputs
- explicit statement on whether any new IDs/categories are allowed in MVP
- explicit `entry_gate.py` policy for any new DOM-intelligence `SignalId` values
- backward-compatibility fixture suite comparing old and new payload shapes
- rollback rule: how the old path remains available if scorer or parity drift appears

No work that mutates registry/scorer semantics may proceed beyond this gate until these artifacts exist and pass.

### Phase 4 — DEEP6 Dashboard Surface
Goal: expose the intelligence layer through a DEEP6-native screen, not a blind SuperDOM clone.

Target layout:
- top: DEEP6 header strip
- left/center: footprint chart
- center/right: DOM ladder
- right rail: intelligence panel + signals + tape
- bottom: replay controls

Deliver:
- DOM ladder component
- intelligence summary panel
- wall classification visuals
- score + signal linkage
- contract-fixture-fed state for UI verification
- contract-fixture-fed rendering path using outputs recorded from Tasks 4-6, not mock-only state
- data transport split:
  - DOM ladder updates via WebSocket
  - intelligence rail / signal summaries via SSE or equivalent stream

Tier 3 overlays are OUT OF SCOPE for Phase 4. Phase 4 renders Tier 1 and Tier 2 outputs only.

### Phase 5 — Parity, Hardening, and Promotion Gate
Goal: prove trustworthiness before broader rollout.

Deliver:
- golden-session parity harness
- false-positive rate checks
- performance benchmark suite
- replay-safe vs live-only detector audit
- promotion report for initial release

### Final Verification Wave
- plan compliance audit
- code quality review
- QA/replay parity review
- scope fidelity review

---

## Parallel Execution Waves

```text
Wave 1 — Architecture Truth
- Task 1: Define DOM intelligence contract [deep]
- Task 2: Define detector taxonomy + replay-safety metadata [quick]
- Task 3: Map depth-radar/V1/V2 integration boundary [deep]

Wave 2 — Canonical Truth Path
- Task 4: Live DOM adapter [unspecified-high]
- Task 5: Replay DOM adapter [deep]
- Task 6: Golden-session recording format [quick]
- Task 6B: Acquire golden session recordings [unspecified-high]
- Task 7: Stale/disconnect/session-boundary handling [quick]

Compatibility Gate A
- Task 7A: Freeze old→new signal/scorer contract mapping [deep]
- Task 7B: Backward-compat fixture suite for registry/scorer consumers [unspecified-high]
- Task 7C: Rollback/coexistence rule for old and new paths [quick]

Wave 3 — Mechanical Detectors
- Task 8: Order book imbalance + thinness detectors [deep]
- Task 9: Absorption DOM detector [deep]
- Task 10: Sweep + reload detector [deep]
- Task 11: Iceberg/refill enhancement [unspecified-high]
- Task 12: CVD integration [quick]

Wave 4 — Heuristic / ML Feature Layer
- Task 13: Heuristic feature-row builder [unspecified-high]
- Task 14: Pull/replace trap detector [deep]
- Task 15: Micro-momentum + TPS + burst features [unspecified-high]
- Task 16: Calibration / evidence thresholds [quick]

Wave 5 — Dashboard Surface
- Task 17: DOM ladder component [visual-engineering]
- Task 18: Intelligence rail + wall state summary [visual-engineering]
- Task 19: Signal/tape/score integration on layout [visual-engineering]
- Task 20: Demo-state and rendering verification [quick]

Wave 6 — Hardening / Promotion Gate
- Task 21: Golden-session replay/live parity harness [deep]
- Task 22: Detector false-positive benchmarks [unspecified-high]
- Task 23: Performance benchmarks under burst load [unspecified-high]
- Task 24: Replay-safe vs live-only audit report [writing]

Wave FINAL
- F1: Plan compliance audit [oracle]
- F2: Code quality review [unspecified-high]
- F3: QA/replay parity review [unspecified-high]
- F4: Scope fidelity review [deep]
```

---

## Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 4-24 | 1 |
| 2 | — | 8-24 | 1 |
| 3 | — | 4-24 | 1 |
| 4 | 1,3 | 8-20,21-24 | 2 |
| 5 | 1,3 | 8-20,21-24 | 2 |
| 6 | 1,4,5 | 6B,21 | 2 |
| 6B | 4,5,6 | 13,16,21-24 | 2 |
| 7 | 1,4,5 | 7A-7C,8-24 | 2 |
| 7A | 1,2,4,5,7 | 8-24 | 2 |
| 7B | 1,2,4,5,7A | 8-24 | 2 |
| 7C | 1,2,4,5,7A | 8-24 | 2 |
| 8 | 1,2,4,5,7A,7B,7C | 21-24 | 3 |
| 9 | 1,2,4,5,7A,7B,7C | 21-24 | 3 |
| 10 | 1,2,4,5,7A,7B,7C | 21-24 | 3 |
| 11 | 1,2,4,5,7A,7B,7C | 21-24 | 3 |
| 12 | 1,2,4,5,7A,7B,7C | 21-24 | 3 |
| 13 | 1,2,4,5,6B,7A,7B,7C | 14-16,21-24 | 4 |
| 14 | 13 | 16,21-24 | 4 |
| 15 | 13 | 16,21-24 | 4 |
| 16 | 13,14,15 | 21-24 | 4 |
| 17 | 1,2,4,5,6,7B | 18-20 | 5 |
| 18 | 17 | 19,20 | 5 |
| 19 | 17,18 | 20 | 5 |
| 20 | 17,18,19 | FINAL | 5 |
| 21 | 4-16 | FINAL | 6 |
| 22 | 8-16 | FINAL | 6 |
| 23 | 8-16 | FINAL | 6 |
| 24 | 21-23 | FINAL | 6 |

---

## Task QA Matrix

> Every task must leave behind a machine-checkable artifact under `.sisyphus/evidence/`.

### Wave 1 — Architecture Truth

#### Task 1: Define DOM intelligence contract
- **QA Scenario**:
  - Add schema/type tests validating required fields and forbidden omissions
  - Run: `python -m pytest tests_v2/dom_intelligence/test_contract.py -v`
- **Pass Condition**:
  - all contract tests pass
  - contract explicitly states DOM state ownership rule: consume or extend `deep6v2/state/dom.py` without instantiating a parallel DOMState
  - evidence note saved to `.sisyphus/evidence/task-1-contract.txt`

#### Task 2: Define detector taxonomy + replay-safety metadata
- **QA Scenario**:
  - Add tests validating every detector classification enum/metadata value is recognized
  - Run: `python -m pytest tests_v2/dom_intelligence/test_taxonomy.py -v`
- **Pass Condition**:
  - no unknown tiers or replay-safety states
  - replay-safety enum includes `REPLAY_SAFE`, `LIVE_ONLY`, and `REPLAY_DEGRADED`
  - evidence note saved to `.sisyphus/evidence/task-2-taxonomy.txt`

#### Task 3: Map depth-radar/V1/V2 integration boundary
- **QA Scenario**:
  - Add a static architecture check documenting intended imports and forbidden couplings
  - Run: `python -m pytest tests_v2/dom_intelligence/test_architecture_boundary.py -v`
- **Pass Condition**:
  - tests prove dashboard code does not import detector internals
  - tests/documentation prove the live adapter wraps upstream transport rather than recreating it
  - tests/documentation prove depth-radar reuse is optional, not a hard dependency
  - evidence note saved to `.sisyphus/evidence/task-3-boundary.txt`

### Wave 2 — Canonical Truth Path

#### Task 4: Live DOM adapter
- **QA Scenario**:
  - Feed synthetic `DOMUpdate` sequences into the live adapter
  - Run: `python -m pytest tests_v2/dom_intelligence/test_live_adapter.py -v`
- **Pass Condition**:
  - output contract matches Task 1 schema
  - evidence JSON saved to `.sisyphus/evidence/task-4-live-adapter.json`

#### Task 5: Replay DOM adapter
- **QA Scenario**:
  - Replay deterministic MBO fixtures through the replay adapter
  - Run: `python -m pytest tests_v2/dom_intelligence/test_replay_adapter.py -v`
- **Pass Condition**:
  - reconstructed adapter output matches expected fixture snapshots
  - evidence JSON saved to `.sisyphus/evidence/task-5-replay-adapter.json`

#### Task 6: Golden-session recording format
- **QA Scenario**:
  - Serialize and deserialize a sample recorded session artifact
  - Run: `python -m pytest tests_v2/dom_intelligence/test_golden_session_format.py -v`
- **Pass Condition**:
  - round-trip retains timestamps, levels, and detector metadata
  - evidence file saved to `.sisyphus/evidence/task-6-golden-roundtrip.json`

#### Task 6B: Acquire golden session recordings
- **QA Scenario**:
  - Acquire at least 3 golden sessions:
    - 1 quiet RTH session
    - 1 volatile/news-affected session
    - 1 session containing disconnect/reconnect or feed interruption handling
  - Run: `python -m pytest tests_v2/dom_intelligence/test_golden_session_inventory.py -v`
- **Pass Condition**:
  - each session contains at least 30 minutes of continuous usable DOM-intelligence recording
  - serialized artifacts conform to Task 6 format
  - evidence inventory saved to `.sisyphus/evidence/task-6b-golden-sessions.json`

#### Task 7: Stale/disconnect/session-boundary handling
- **QA Scenario**:
  - Simulate disconnect, stale feed, reconnect, and session reset transitions
  - Run: `python -m pytest tests_v2/dom_intelligence/test_feed_safety.py -v`
- **Pass Condition**:
  - no stale state leaks across reconnection/session rollover
  - evidence note saved to `.sisyphus/evidence/task-7-feed-safety.txt`

#### Task 7A: Freeze old→new signal/scorer contract mapping
- **QA Scenario**:
  - Write the explicit mapping contract between new DOM-intelligence outputs and existing `SignalId` / scorer inputs
  - Run: `python -m pytest tests_v2/dom_intelligence/test_signal_contract_mapping.py -v`
- **Pass Condition**:
  - every mapped output has an explicit compatibility rule
  - the MVP explicitly states whether any new IDs/categories are allowed
  - `entry_gate.py` treatment for new DOM-intelligence signals is explicitly declared
  - evidence saved to `.sisyphus/evidence/task-7a-contract-mapping.txt`

#### Task 7B: Backward-compat fixture suite for registry/scorer consumers
- **QA Scenario**:
  - run fixture comparisons across old-path and new-path payloads for downstream consumers
  - Run: `python -m pytest tests_v2/dom_intelligence/test_backward_compat.py -v`
- **Pass Condition**:
  - payload shape compatibility is mechanically verified
  - no silent contract drift is allowed
  - evidence saved to `.sisyphus/evidence/task-7b-backward-compat.json`

#### Task 7C: Rollback/coexistence rule for old and new paths
- **QA Scenario**:
  - verify documented rollback/coexistence behavior with a feature-flag or equivalent control path
  - Run: `python -m pytest tests_v2/dom_intelligence/test_rollforward_rollback.py -v`
- **Pass Condition**:
  - old and new paths can coexist or revert without undefined scorer behavior
  - evidence saved to `.sisyphus/evidence/task-7c-rollback.txt`

### Wave 3 — Mechanical Detectors

#### Task 8: Order book imbalance + thinness detectors
- **QA Scenario**:
  - Run positive and negative synthetic-book fixtures
  - Run: `python -m pytest tests_v2/dom_intelligence/test_imbalance_thinness.py -v`
- **Pass Condition**:
  - detectors fire only on intended asymmetry fixtures
  - evidence JSON saved to `.sisyphus/evidence/task-8-imbalance-thinness.json`

#### Task 9: Absorption DOM detector
- **QA Scenario**:
  - Run fixtures where resting depth absorbs aggressive flow vs cases where price displaces normally
  - Run: `python -m pytest tests_v2/dom_intelligence/test_absorption_dom.py -v`
- **Pass Condition**:
  - absorption fires on the intended fixtures and stays silent on displacement controls
  - evidence JSON saved to `.sisyphus/evidence/task-9-absorption.json`

#### Task 10: Sweep + reload detector
- **QA Scenario**:
  - Replay multi-level sweep fixtures with and without reload behavior
  - Run: `python -m pytest tests_v2/dom_intelligence/test_sweep_reload.py -v`
- **Pass Condition**:
  - sweep and reload states are differentiated correctly
  - evidence JSON saved to `.sisyphus/evidence/task-10-sweep-reload.json`

#### Task 11: Iceberg/refill enhancement
- **QA Scenario**:
  - Run refill/refresh fixtures against displayed-size vs fill-size controls
  - Run: `python -m pytest tests_v2/dom_intelligence/test_iceberg_refill.py -v`
- **Pass Condition**:
  - iceberg/refill confidence rises only on valid refill patterns
  - evidence JSON saved to `.sisyphus/evidence/task-11-iceberg.json`

#### Task 12: CVD integration
- **QA Scenario**:
  - Validate running CVD and reset/session handling on trade streams
  - Run: `python -m pytest tests_v2/dom_intelligence/test_cvd_integration.py -v`
- **Pass Condition**:
  - CVD matches expected accumulation history
  - evidence JSON saved to `.sisyphus/evidence/task-12-cvd.json`

### Wave 4 — Heuristic / ML Feature Layer

#### Task 13: Heuristic feature-row builder
- **QA Scenario**:
  - Build feature rows from deterministic fixtures and validate schema/ordering
  - Run: `python -m pytest tests_v2/dom_intelligence/test_feature_rows.py -v`
- **Pass Condition**:
  - feature vector names and order are stable
  - labeling strategy artifact exists for Tier 2 evaluation, referencing event sourcing from Task 6B sessions
  - evidence CSV saved to `.sisyphus/evidence/task-13-feature-rows.csv`

#### Task 14: Pull/replace trap detector
- **QA Scenario**:
  - Run high-cancel deceptive-liquidity fixtures and non-trap controls
  - Run: `python -m pytest tests_v2/dom_intelligence/test_pull_replace.py -v`
- **Pass Condition**:
  - detector fires only when cancel/replace behavior exceeds defined thresholds
  - evidence JSON saved to `.sisyphus/evidence/task-14-pull-replace.json`

#### Task 15: Micro-momentum + TPS + burst features
- **QA Scenario**:
  - Run feature extraction fixtures for tempo, burst, and momentum windows
  - Run: `python -m pytest tests_v2/dom_intelligence/test_micro_features.py -v`
- **Pass Condition**:
  - tempo and burst features match expected calculations
  - evidence CSV saved to `.sisyphus/evidence/task-15-micro-features.csv`

#### Task 16: Calibration / evidence thresholds
- **QA Scenario**:
  - Run calibration logic against a sample labeled set with threshold reporting
  - Run: `python -m pytest tests_v2/dom_intelligence/test_calibration.py -v`
- **Pass Condition**:
  - threshold outputs are deterministic and serialized
  - calibration input uses the documented labeled set derived from Task 6B / Task 13 artifacts
  - evidence report saved to `.sisyphus/evidence/task-16-calibration.txt`

### Wave 5 — Dashboard Surface

#### Task 17: DOM ladder component
- **QA Scenario**:
  - Render the DOM ladder with deterministic contract fixtures
  - Run: `npm --prefix dashboard run test -- DOMLadder`
- **Pass Condition**:
  - component renders expected rows, bid/ask values, and highlighted ladder state
  - WebSocket ladder message schema is defined and fixture-backed
  - evidence screenshot or snapshot note saved to `.sisyphus/evidence/task-17-dom-ladder.txt`

#### Task 18: Intelligence rail + wall state summary
- **QA Scenario**:
  - Render the intelligence rail with mock wall classifications and summary counts
  - Run: `npm --prefix dashboard run test -- IntelligenceRail`
- **Pass Condition**:
  - wall state counts and score summaries match fixtures
  - evidence note saved to `.sisyphus/evidence/task-18-intel-rail.txt`

#### Task 19: Signal/tape/score integration on layout
- **QA Scenario**:
  - Run integration tests for page layout with DOM ladder + signals + tape + score data using contract fixtures generated from Tasks 4-6/7B
  - Run: `npm --prefix dashboard run test -- page`
- **Pass Condition**:
  - layout consumes structured store state without detector imports
  - evidence note saved to `.sisyphus/evidence/task-19-layout-integration.txt`

#### Task 20: Demo-state and rendering verification
- **QA Scenario**:
  - Run frontend demo mode or deterministic fixture-fed render checks derived from recorded contract artifacts, not mock-only hand-made state
  - Run: `npm --prefix dashboard run test`
- **Pass Condition**:
  - no rendering regressions in the DOM ladder surface
  - all demo fixtures and layout assumptions are NQ-only
  - evidence note saved to `.sisyphus/evidence/task-20-demo-render.txt`

### Wave 6 — Hardening / Promotion Gate

#### Task 21: Golden-session replay/live parity harness
- **QA Scenario**:
  - Compare recorded-live outputs to replay outputs on a golden session
  - Run: `python -m pytest tests_v2/dom_intelligence/test_golden_parity.py -v`
- **Pass Condition**:
  - parity diff remains within these declared tolerances for detectors marked `REPLAY_SAFE`:
    - event timestamp drift: `<= 100ms`
    - price difference: `<= 1 tick`
    - strength/confidence difference: `<= 0.10` absolute
    - per-session replay-safe detector count mismatch: `<= 5%`
    - direction mismatch for matched replay-safe signals: `0 allowed`
  - detectors marked `LIVE_ONLY` are excluded from parity scoring and must appear as excluded in the report
  - detectors marked `REPLAY_DEGRADED` must report separately with explanatory notes rather than causing silent pass/fail ambiguity
  - evidence diff saved to `.sisyphus/evidence/task-21-golden-parity.json`

#### Task 22: Detector false-positive benchmarks
- **QA Scenario**:
  - Run neutral/baseline session smoke benchmarks and count detector fires
  - Run: `python -m pytest tests_v2/dom_intelligence/test_false_positive_rates.py -v`
- **Pass Condition**:
  - false-positive rates remain under declared thresholds
  - thresholds must be explicit in the benchmark report, with initial defaults:
    - Tier 1 mechanical detectors: `<= 12` false positives per RTH hour per detector on neutral baseline sessions
    - high-confidence alert-grade outputs derived from Tier 1 confluence: `<= 3` false positives per RTH hour
    - Tier 2 heuristic detectors must report raw fire counts separately and are not promotion-eligible until calibrated in Task 16
  - evidence report saved to `.sisyphus/evidence/task-22-false-positives.txt`

#### Task 23: Performance benchmarks under burst load
- **QA Scenario**:
  - Stress detectors and adapters under bursty synthetic DOM update load
  - Run: `python -m pytest tests_v2/dom_intelligence/test_performance.py -v`
- **Pass Condition**:
  - benchmark stays within this defined latency budget under a synthetic NQ load of `1000 DOM updates/sec` sustained for `60s` with Tier 1 + Tier 2 detectors enabled:
    - if the execution model remains serial, no detector may individually exceed `0.08 ms` mean latency in isolation
    - if a parallel model is chosen, the plan must document the concurrency strategy and then meet:
      - p95 end-to-end update latency: `<= 1.0 ms` per update
      - max end-to-end update latency: `<= 5.0 ms` per update
    - whichever model is selected in Phase 0 must be the one benchmarked here
    - memory growth over the 60s benchmark window: `<= 10%`
  - evidence report saved to `.sisyphus/evidence/task-23-performance.txt`

#### Task 24: Replay-safe vs live-only audit report
- **QA Scenario**:
  - Generate an audit artifact summarizing detector safety modes
  - Run: `python -m pytest tests_v2/dom_intelligence/test_replay_safety_audit.py -v`
- **Pass Condition**:
  - every detector is classified with evidence-backed replay/live status
  - evidence report saved to `.sisyphus/evidence/task-24-replay-safety.txt`

### Wave FINAL — Review / Promotion

### Final Review Execution Mechanism
- This plan is intended to be executed inside the OpenCode / OMO agent environment.
- Review tasks F1-F4 use the executor's **actual available subagent review mechanism**.
- In OpenCode environments, this is typically `task(...)`.
- In OMO workspaces exposing a different subagent runner (for example `call_omo_agent`), use that equivalent instead.
- The required behavior is the same regardless of syntax: invoke the named reviewer class, capture blocking findings only, and save the evidence artifact noted below.

#### Final review gate
- **QA Scenario**:
  - Run the full targeted suites before review agents are invoked
  - Run:
    - `python -m pytest tests_v2/dom_intelligence -v`
    - `npm --prefix dashboard run test`
- **Pass Condition**:
  - all targeted tests pass before F1-F4 review tasks begin
  - consolidated summary saved to `.sisyphus/evidence/final-superdom-intelligence-summary.txt`

#### F1: Plan compliance audit
- **QA Scenario**:
  - Run an Oracle review against the implemented change set and this plan file
  - Execution: invoke the environment's Oracle review runner (`task(...)` in OpenCode, equivalent subagent runner elsewhere) with prompt: `Audit implemented work against C:\Users\Tea\DEEP6\.sisyphus\plans\superdom-intelligence-layer.md. Return blocking deviations, if any.`
- **Pass Condition**:
  - Oracle returns no blocking plan deviations
  - evidence note saved to `.sisyphus/evidence/f1-plan-compliance.txt`

#### F2: Code quality review
- **QA Scenario**:
  - Run a high-effort code review focused on changed files, complexity, maintainability, and unsafe coupling
  - Execution: invoke the environment's high-effort review runner (`task(...)` in OpenCode, equivalent subagent runner elsewhere) with prompt: `Review the implemented SuperDOM intelligence layer changes for code quality, complexity, duplication, and unsafe coupling. Return only blocking findings.`
- **Pass Condition**:
  - no blocking code-quality findings remain
  - evidence note saved to `.sisyphus/evidence/f2-code-quality.txt`

#### F3: QA / replay parity review
- **QA Scenario**:
  - Run an independent high-effort review of evidence artifacts from Tasks 21-24 and the targeted test runs
  - Execution: invoke the environment's high-effort review runner (`task(...)` in OpenCode, equivalent subagent runner elsewhere) with prompt: `Review the SuperDOM intelligence evidence artifacts, parity outputs, and targeted test results. Return only blocking QA or parity concerns.`
- **Pass Condition**:
  - no blocking QA/parity issues remain
  - evidence note saved to `.sisyphus/evidence/f3-qa-parity.txt`

#### F4: Scope fidelity review
- **QA Scenario**:
  - Run a deep scope review against this plan's Must Have / Must NOT Have sections
  - Execution: invoke the environment's deep review runner (`task(...)` in OpenCode, equivalent subagent runner elsewhere) with prompt: `Compare the implemented SuperDOM intelligence layer against C:\Users\Tea\DEEP6\.sisyphus\plans\superdom-intelligence-layer.md. Identify any scope creep, missing must-haves, or guardrail violations.`
- **Pass Condition**:
  - no blocking scope-fidelity findings remain
  - evidence note saved to `.sisyphus/evidence/f4-scope-fidelity.txt`

---

## Task-Level Acceptance Rules

### Architecture / Contract Tasks
- Must declare exactly how the new subsystem extends existing depth-radar and V2 registry/scoring
- Must define output schemas before implementation work begins

### Detector Tasks
- Must specify thresholds, inputs, outputs, and false-positive guardrails
- Must include at least one positive fixture and one negative fixture

### UI Tasks
- Must consume structured state only
- Must not embed detector math or threshold logic in components
- Must respect DEEP6 visual language already established in dashboard docs/components

### Parity / Hardening Tasks
- Must produce machine-readable parity artifacts
- Must explicitly mark detectors as replay-safe or live-only where appropriate

---

## Cross-Plan Dependency Rules

- This parent plan may reference `.sisyphus/plans/depth-radar-v2.md`, `.sisyphus/plans/dom-liquidity-levels.md`, and `.sisyphus/plans/deep6-v2-python.md` as design/context inputs only.
- No task in this plan may block on unrelated NT8 UI implementation unless that dependency is explicitly declared and justified.
- If upstream `deep6-v2-python` contracts change during execution, Wave 1 boundary tasks must be revalidated before continuing deeper implementation.

---

## Key File References

### Existing Signal / ML Patterns
- `deep6/ml/depth_radar/wall_features.py`
- `deep6/ml/depth_radar/classifier.py`
- `deep6/ml/depth_radar/wall_interaction_model.py`
- `deep6/services/depth_radar_service.py`
- `deep6/engines/trespass.py`
- `deep6/engines/iceberg.py`
- `deep6/engines/counter_spoof.py`

### Existing V2 Integration Patterns
- `deep6v2/signals/registry.py`
- `deep6v2/scoring/scorer.py`
- `deep6v2/state/dom.py`
- `deep6v2/backtest/replay_engine.py`

### Existing UI / Visual Patterns
- `docs/DEEP6_Master_Blueprint_v2.md`
- `dashboard/app/page.tsx`
- `dashboard/components/layout/HeaderStrip.tsx`
- `dashboard/components/footprint/FootprintChart.tsx`
- `dashboard/components/signals/SignalFeed.tsx`
- `dashboard/components/replay/ReplayControls.tsx`

### Existing Related Plans
- `.sisyphus/plans/depth-radar-v2.md`
- `.sisyphus/plans/dom-liquidity-levels.md`
- `.sisyphus/plans/cross-market-dom-ai.md`

---

## Success Criteria Summary

This plan succeeds if DEEP6 ends up with:
- a trustworthy DOM-intelligence truth path
- a detector-first architecture
- replay/live parity discipline
- a compelling ladder + chart + intelligence UI
- and a clear distinction between:
  - what can be automated now,
  - what should be tuned with ML,
  - and what remains trader-facing context only.

It fails if it becomes:
- a literal SuperDOM clone,
- a dashboard-only visual toy,
- or a disconnected side-system that bypasses DEEP6’s truth and verification patterns.
