# Standard Deviation Anchor AI

## TL;DR

> **Quick Summary**: Build a TradingView-first hybrid system where PineScript owns deterministic, wick-to-wick anchor detection/rendering and HERMES acts as an external expert sidecar that watches the chart, approves/vetoes anchors, and powers continuous labeling/training.
>
> **Deliverables**:
> - TradingView Pine indicator with human-style anchor + deviation rendering
> - HERMES sidecar spec for chart watching, veto, and audit logging
> - Screenshot/metadata labeling workflow for continuous training
> - Verification/replay/chart-QA workflow
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 3 waves + final verification
> **Critical Path**: T1 -> T5 -> T8 -> T12 -> F1-F4

---

## Context

### Original Request
Build a human-style standard deviation anchor system that finds the last clean opposite-direction manipulation leg before displacement, anchors wick-to-wick exactly like a discretionary trader, projects -2/-2.5/-4 levels, rejects bad/choppy setups, and stays visually simple on the TradingView chart.

### Interview Summary
**Key Discussions**:
- TradingView is the primary platform.
- First milestone is the full hybrid system, not a reduced MVP.
- Verification will use tests-after plus chart QA.
- HERMES will be an external veto sidecar that continuously watches chart state.
- Pine is the only chart drawer.
- Bar-confirmed anchors only; no finalized intrabar repaint behavior.
- 1m is primary; 5m/15m add context/confidence only.
- Initial deterministic taxonomy is narrow: one core manipulation-leg pattern family only.
- Displacement requires both local structure break and impulsive candle/range expansion.
- The system must mimic the original human-style/youtuber workflow.
- Do **not** reuse prior trading/anchor business logic; only reuse infrastructure/integration patterns where needed.

**Research Findings**:
- Pine cannot host the full AI runtime; AI must remain external.
- Existing project fit favors `deep6/` for orchestration/data contracts and TradingView skills/bridge workflows for chart watching.
- Existing screenshot/session-agent patterns can inform capture/logging, but not the new anchor logic.
- Biggest risks are anchor lifecycle drift, AI drifting from the original method, screenshot leakage, and unclear disagreement authority.

### Metis Review
**Identified Gaps** (addressed):
- Need explicit non-reuse guardrail for prior anchor business logic.
- Need explicit authority split: Pine draws, HERMES watches/approves/vetoes.
- Need anchor auditability so AI never becomes a black box.
- Need chart-watching workflow defined without breaking original logic.

---

## Work Objectives

### Core Objective
Define and build a plan for a visually intuitive, human-style TradingView anchor system whose deterministic rules remain faithful to the requested method while HERMES continuously reviews chart state and improves label quality over time.

### Concrete Deliverables
- Pine indicator spec and implementation tasks for candidate anchors, projections, labels, and invalidation states.
- HERMES sidecar spec for TradingView observation, veto workflow, and audit logging.
- Dedicated skill/training workflow for standard-deviation expert review.
- Screenshot + structured-metadata dataset workflow.
- Governed continuous-learning loop with versioned promotion gates.
- Automated and agent-executed QA protocol.

### Definition of Done
- [ ] Pine deterministically renders only valid bar-confirmed anchors and levels on TradingView.
- [ ] HERMES can consume chart state/screenshots and emit approve/veto decisions with audit reasons.
- [ ] Every approved/rejected anchor is traceable to explicit rules.
- [ ] Replay/chart QA proves visuals remain readable and faithful to the original method.

### Must Have
- Wick-to-wick anchoring only.
- Last clear opposite-direction manipulation leg only.
- Pine-only chart drawing.
- External HERMES sidecar continuously watching and evaluating chart state.
- Continuous improvement workflow that refines HERMES skill quality without changing the core anchor doctrine automatically.
- Strict rejection logic with “No valid manipulation leg detected.”
- No finalized anchor repaint after confirmation.

### Must NOT Have (Guardrails)
- No reuse of prior anchor-selection or trading business logic.
- No ATR/VWAP/regression/volatility-band substitution.
- No AI-defined hidden anchor logic.
- No multi-pattern expansion in the first build.
- No higher-timeframe override of 1m anchor authority.
- No invisible AI decisions without audit logs.
- No autonomous self-rewrite of the core anchor rules.

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES (partial)
- **Automated tests**: Tests-after
- **Framework**: pytest + vitest + chart QA via TradingView tooling

### QA Policy
- Python verification: `python -m pytest tests_v2 -q`
- Frontend verification: `cd dashboard && npm run test`, `npm run typecheck`, `npm run build`
- TradingView validation: Pine compile/check + chart-state/screenshot-based QA through TradingView tools
- Evidence path root: `.sisyphus/evidence/standard-deviation-anchor-ai/`

---

## Execution Strategy

### Parallel Execution Waves

```text
Wave 1 (Foundation - can start immediately)
├── T1: Anchor contract + state machine
├── T2: HERMES authority + audit contract
├── T3: Pine visual spec + object lifecycle
├── T4: Skill/training spec for HERMES expert behavior
└── T5: Dataset schema + capture protocol

Wave 2 (Core build)
├── T6: Pine candidate-detection engine
├── T7: Pine visual rendering + invalidation states
├── T8: Sidecar observation bridge + decision pipeline
├── T9: Labeling/review workflow + storage
└── T10: Replay/evaluation harness

Wave 3 (Integration)
├── T11: HERMES standard-deviation expert workflow
├── T12: Pine-sidecar synchronization + disagreement handling
├── T13: Chart-facing status UX + alerts
└── T14: Continuous training/calibration loop

Wave FINAL
├── F1: Plan compliance audit
├── F2: Code quality review
├── F3: Real chart QA execution
└── F4: Scope fidelity check
```

### Dependency Matrix

- **T1**: Blocked By: None | Blocks: T6, T7, T8, T10, T11, T12
- **T2**: Blocked By: None | Blocks: T8, T11, T12, T13, T14
- **T3**: Blocked By: None | Blocks: T7, T13
- **T4**: Blocked By: None | Blocks: T11, T14
- **T5**: Blocked By: None | Blocks: T9, T10, T14
- **T6**: Blocked By: T1 | Blocks: T12, T13
- **T7**: Blocked By: T1, T3 | Blocks: T12, T13
- **T8**: Blocked By: T1, T2 | Blocks: T11, T12, T14
- **T9**: Blocked By: T5 | Blocks: T14
- **T10**: Blocked By: T1, T5 | Blocks: F3
- **T11**: Blocked By: T1, T2, T4, T8 | Blocks: T12, T14
- **T12**: Blocked By: T1, T2, T6, T7, T8, T11 | Blocks: T13, F3
- **T13**: Blocked By: T2, T3, T6, T7, T12 | Blocks: F3
- **T14**: Blocked By: T2, T4, T5, T8, T9, T11 | Blocks: F3

### Agent Dispatch Summary

- **Wave 1**: T1 `deep`, T2 `deep`, T3 `visual-engineering`, T4 `writing`, T5 `unspecified-high`
- **Wave 2**: T6 `deep`, T7 `visual-engineering`, T8 `unspecified-high`, T9 `unspecified-high`, T10 `deep`
- **Wave 3**: T11 `deep`, T12 `unspecified-high`, T13 `visual-engineering`, T14 `unspecified-high`
- **FINAL**: F1 `oracle`, F2 `unspecified-high`, F3 `unspecified-high`, F4 `deep`

---

## TODOs

- [x] T1. **Write Anchor Contract + State Machine**

  **What to do**:
  - Define the canonical anchor contract from scratch: candidate, confirmed, active, invalidated, superseded.
  - Define exact wick-to-wick anchor rules, displacement confirmation rules, rejection rules, and invalidation rules.
  - Explicitly forbid reuse of prior anchor-selection business logic.

  **Must NOT do**:
  - Pull trading logic from older anchor, fib, deviation, or bias modules.
  - Leave repaint/disagreement semantics implicit.

  **Recommended Agent Profile**:
  - **Category**: `deep` — logic contract is the highest-risk foundation.
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T6, T7, T8, T10, T11, T12
  - **Blocked By**: None

  **References**:
  - `.sisyphus/drafts/standard-deviation-anchor-ai.md` - authoritative interview decisions.
  - `docs/FOOTPRINT-LABELING-SPEC.md` - labeling separation pattern only; do not reuse anchor logic.
  - `docs/FOOTPRINT-DATA-CONTRACT.md` - event/state contract style for auditability.

  **Acceptance Criteria**:
  - [ ] Markdown contract created with explicit candidate/confirmed/invalidation states.
  - [ ] Contract includes deterministic examples and non-examples.

  **QA Scenarios**:
  ```
  Scenario: Contract completeness review
    Tool: Bash (python/grep/read workflow)
    Preconditions: Contract file exists
    Steps:
      1. Read the contract file and locate sections for candidate, confirmation, invalidation, superseded.
      2. Assert each state has entry criteria and exit criteria.
      3. Assert a non-reuse guardrail is present verbatim.
    Expected Result: All required sections present and explicit.
    Failure Indicators: Missing state, missing invalidation rule, or no anti-legacy guardrail.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t1-contract-review.txt

  Scenario: Negative check for ambiguity
    Tool: Bash
    Preconditions: Contract file exists
    Steps:
      1. Search for vague phrases like "use prior logic" or "best fit" without rule definition.
      2. Assert none remain in the contract.
    Expected Result: No vague dependency on old logic or subjective fallback language.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t1-contract-ambiguity.txt
  ```

- [x] T2. **Define HERMES Authority + Audit Contract**

  **What to do**:
  - Define exactly what HERMES can see, decide, veto, and log.
  - Define Pine/HERMES disagreement policy and required audit fields.
  - Lock Pine as sole drawer.

  **Must NOT do**:
  - Allow HERMES to silently mutate chart anchors.
  - Make AI authority broader than veto/ranking/explanation.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T8, T11, T12, T13, T14
  - **Blocked By**: None

  **References**:
  - `.sisyphus/drafts/standard-deviation-anchor-ai.md` - HERMES decisions confirmed by user.
  - `deep6/copilot/session.py` - session-agent orchestration pattern only.
  - `deep6/copilot/vision_analysis.py` - audit/result parsing pattern only.

  **Acceptance Criteria**:
  - [ ] Authority matrix written.
  - [ ] Audit schema lists inputs, decision, reason, and disagreement outcome.

  **QA Scenarios**:
  ```
  Scenario: Authority matrix verification
    Tool: Bash
    Preconditions: Authority contract exists
    Steps:
      1. Read the matrix.
      2. Assert Pine is marked "draws" and HERMES is marked "approve/veto/log" only.
      3. Assert human override and disagreement logging are defined.
    Expected Result: No unauthorized AI chart-drawing power.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t2-authority.txt

  Scenario: Negative authority check
    Tool: Bash
    Preconditions: Authority contract exists
    Steps:
      1. Search for any statement granting direct chart drawing to HERMES.
      2. Assert none are found.
    Expected Result: HERMES direct drawing authority absent.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t2-authority-negative.txt
  ```

- [x] T3. **Design Pine Visual Spec + Object Lifecycle**

  **What to do**:
  - Specify exact TradingView visuals: anchor leg, wick markers, -2/-2.5/-4, zone fill, active/invalidated labels.
  - Define object lifecycle for create/update/remove using Pine-only drawing.
  - Optimize for simple “youtuber-readable” visuals.

  **Must NOT do**:
  - Hide state in off-chart logic.
  - Overcomplicate visuals with nonessential overlays.

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T7, T13
  - **Blocked By**: None

  **References**:
  - TradingView Pine line/box/label docs - object primitives and lifecycle patterns.
  - `deep6v2/tradingview/analysis.py` - screenshot-oriented TradingView integration context.

  **Acceptance Criteria**:
  - [ ] Visual spec defines every chart object and label.
  - [ ] Lifecycle states align with T1 contract.

  **QA Scenarios**:
  ```
  Scenario: Visual spec completeness
    Tool: Bash
    Preconditions: Visual spec exists
    Steps:
      1. Read the spec.
      2. Assert presence of anchor line, endpoint markers, -2, -2.5, -4, zone fill, and status label.
    Expected Result: All required objects are specified.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t3-visual-spec.txt

  Scenario: Negative visual clutter check
    Tool: Bash
    Preconditions: Visual spec exists
    Steps:
      1. Search for unsupported extras like ATR bands, VWAP bands, regression channels.
      2. Assert none are specified.
    Expected Result: No banned visuals present.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t3-visual-negative.txt
  ```

- [x] T4. **Specify HERMES Expert Skill + Training Doctrine**

  **What to do**:
  - Define the HERMES standard-deviation expert skill behavior, prompt boundaries, review checklist, and continuous-improvement loop.
  - Encode strict loyalty to the original human-style anchor method.
  - Define how new reviewed examples are allowed to improve judgment quality without changing the doctrine itself.

  **Must NOT do**:
  - Allow HERMES to generalize into unrelated strategy logic.
  - Use legacy anchor heuristics as hidden priors.

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T11, T14
  - **Blocked By**: None

  **References**:
  - `.sisyphus/drafts/standard-deviation-anchor-ai.md` - user’s intended behavior and style.
  - Project TradingView/skill docs - integration workflow patterns only.

  **Acceptance Criteria**:
  - [ ] HERMES skill doctrine explicitly states what it may and may not infer.
  - [ ] Continuous training loop is described without giving HERMES chart-drawing authority.
  - [ ] Skill spec includes versioning and promotion-gate rules.

  **QA Scenarios**:
  ```
  Scenario: Skill doctrine review
    Tool: Bash
    Preconditions: Skill spec exists
    Steps:
      1. Read the skill spec.
      2. Assert "original logic first" and "no legacy business logic reuse" rules exist.
    Expected Result: HERMES doctrine remains tightly scoped.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t4-skill.txt

  Scenario: Negative drift check
    Tool: Bash
    Preconditions: Skill spec exists
    Steps:
      1. Search for terms suggesting autonomous strategy invention.
      2. Assert none remain.
    Expected Result: No freeform strategy drift language.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t4-skill-negative.txt
  ```

- [x] T5. **Define Dataset Schema + Capture Protocol**

  **What to do**:
  - Define the screenshot + structured-state dataset schema.
  - Define event-time capture, chart metadata, review labels, and storage layout.
  - Prevent hindsight leakage.

  **Must NOT do**:
  - Store screenshots without synchronized structured context.
  - Allow post-hoc labels to overwrite decision-time evidence.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T9, T10, T14
  - **Blocked By**: None

  **References**:
  - `docs/FOOTPRINT-DATA-CONTRACT.md` - decision-time data contract pattern only.
  - `deep6/copilot/vision.py` - screenshot capture pattern only.
  - `deep6v2/tradingview/client.py` - TradingView bridge context only.

  **Acceptance Criteria**:
  - [ ] Schema includes image ID, symbol, timeframe, chart state, candidate anchor fields, HERMES verdict, and reasons.
  - [ ] Leakage-prevention rules are explicit.

  **QA Scenarios**:
  ```
  Scenario: Dataset schema verification
    Tool: Bash
    Preconditions: Dataset schema exists
    Steps:
      1. Read the schema.
      2. Assert all required labeling fields are present.
      3. Assert timestamped decision-time capture fields exist.
    Expected Result: Dataset is sufficient for supervised review.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t5-schema.txt

  Scenario: Leakage rule check
    Tool: Bash
    Preconditions: Dataset schema exists
    Steps:
      1. Search for rules around post-hoc contamination and screenshot-only training.
      2. Assert both are addressed.
    Expected Result: Leakage guardrails present.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t5-leakage.txt
  ```

- [x] T6. **Build Pine Candidate-Detection Engine**

  **What to do**:
  - Implement from-scratch deterministic detection for the single approved manipulation-leg pattern family.
  - Enforce: last clear opposite-direction swing, wick-to-wick anchor, structure break + impulse confirmation, chop rejection.

  **Must NOT do**:
  - Import or mirror legacy anchor business logic.
  - Finalize anchors before bar confirmation.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`tradingview-pinescript-builder-doctor`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: T12, T13
  - **Blocked By**: T1

  **References**:
  - T1 anchor contract - exact business logic source of truth.
  - TradingView Pine docs - implementation primitives only.

  **Acceptance Criteria**:
  - [ ] Candidate engine compiles in Pine.
  - [ ] Only candidate anchors matching the contract are emitted.

  **QA Scenarios**:
  ```
  Scenario: Pine compile and candidate emission
    Tool: TradingView Pine compile/check
    Preconditions: Pine source loaded in editor
    Steps:
      1. Compile the script.
      2. Load a known replay segment with one valid bullish setup.
      3. Assert exactly one candidate anchor is created at the expected bars.
    Expected Result: Clean compile and correct candidate placement.
    Failure Indicators: Compile error, no candidate, or multiple conflicting candidates.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t6-valid-candidate.txt

  Scenario: Chop rejection
    Tool: TradingView replay + screenshot
    Preconditions: Replay segment with overlapping/choppy candles
    Steps:
      1. Run the same script on a known choppy sample.
      2. Assert the script outputs no valid manipulation leg.
    Expected Result: No anchor plotted in chop.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t6-chop-reject.png
  ```

- [x] T7. **Build Pine Visual Rendering + Invalidation States**

  **What to do**:
  - Render anchor line, endpoints, deviation levels, zone fill, and status labels.
  - Render active/invalidated states without changing final historical anchors.

  **Must NOT do**:
  - Let HERMES draw directly.
  - Create visuals not defined in T3.

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`tradingview-pinescript-builder-doctor`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: T12, T13
  - **Blocked By**: T1, T3

  **References**:
  - T3 visual spec - exact object set.
  - TradingView line/box/label docs - object lifecycle primitives.

  **Acceptance Criteria**:
  - [ ] All required objects render.
  - [ ] Invalidated anchors visibly change state rather than disappear silently.

  **QA Scenarios**:
  ```
  Scenario: Full visual render
    Tool: TradingView screenshot capture
    Preconditions: Known valid setup on chart
    Steps:
      1. Load the chart with the script active.
      2. Verify anchor leg, endpoint markers, -2, -2.5, -4, zone fill, and label are visible.
    Expected Result: Trader-readable visual package appears on chart.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t7-full-render.png

  Scenario: Invalidation state transition
    Tool: TradingView replay + screenshot
    Preconditions: Known sample where anchor later invalidates
    Steps:
      1. Replay until invalidation condition occurs.
      2. Assert label switches to invalidated and lines follow the visual spec.
    Expected Result: Invalidation is explicit and readable.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t7-invalidated.png
  ```

- [x] T8. **Build Sidecar Observation Bridge + Decision Pipeline**

  **What to do**:
  - Implement HERMES observation inputs: chart state, screenshots, Pine outputs, timeframe context.
  - Build approve/veto pipeline and disagreement logging.

  **Must NOT do**:
  - Give sidecar rendering authority.
  - Allow unlogged overrides.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`tradingview-machine-profile`, `tradingview-mcp-trading-operator`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: T11, T12, T14
  - **Blocked By**: T1, T2

  **References**:
  - T2 authority contract.
  - `deep6v2/tradingview/client.py` - bridge pattern only.
  - `deep6/copilot/session.py` - sidecar orchestration pattern only.

  **Acceptance Criteria**:
  - [ ] Sidecar ingests Pine decision payloads and screenshots.
  - [ ] Approve/veto decisions include reason codes and timestamps.

  **QA Scenarios**:
  ```
  Scenario: Sidecar receives candidate payload
    Tool: API/bridge log inspection
    Preconditions: Pine emits a candidate alert/state payload
    Steps:
      1. Trigger a known valid candidate.
      2. Assert sidecar receives symbol, timeframe, anchor prices, bar times, and chart snapshot reference.
    Expected Result: Complete candidate context reaches HERMES.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t8-payload.json

  Scenario: Disagreement logging
    Tool: API/bridge log inspection
    Preconditions: Test sample where HERMES vetoes Pine candidate
    Steps:
      1. Trigger the veto path.
      2. Assert a disagreement record is written with reason code and preserved Pine candidate values.
    Expected Result: No silent veto; full audit trail exists.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t8-veto.json
  ```

- [x] T9. **Build Labeling/Review Workflow + Storage**

  **What to do**:
  - Implement label creation, reviewer workflow, and persistent storage for screenshots + structured anchor records.
  - Preserve decision-time and outcome-time separation.

  **Must NOT do**:
  - Collapse image-only and structured labels into one ambiguous record.
  - Lose linkage between screenshot and candidate anchor ID.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: T14
  - **Blocked By**: T5

  **References**:
  - T5 dataset schema.
  - `deep6/api/store.py` - persistence pattern only.

  **Acceptance Criteria**:
  - [ ] Every screenshot record links to one candidate anchor ID.
  - [ ] Reviewer/HERMES verdicts can be queried without ambiguity.

  **QA Scenarios**:
  ```
  Scenario: Record linkage verification
    Tool: Bash/API query
    Preconditions: Stored sample labels exist
    Steps:
      1. Query a stored anchor record.
      2. Assert image path, candidate ID, verdict, and reason fields all resolve.
    Expected Result: One-to-one traceability exists.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t9-linkage.txt

  Scenario: Negative orphan check
    Tool: Bash/API query
    Preconditions: Dataset contains multiple records
    Steps:
      1. Scan for screenshot records missing candidate IDs or timestamps.
      2. Assert none exist.
    Expected Result: No orphan training records.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t9-orphans.txt
  ```

- [x] T10. **Build Replay/Evaluation Harness**

  **What to do**:
  - Create deterministic replay samples and evaluation routines for Pine/HERMES behavior.
  - Measure accepted anchors, rejected chop, veto consistency, and invalidation behavior.

  **Must NOT do**:
  - Evaluate only on hindsight screenshots.
  - Mix live and replay evidence without labeling mode.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: F3
  - **Blocked By**: T1, T5

  **References**:
  - T1 contract and T5 schema.
  - `tests_v2/tradingview/test_analysis.py` - evaluation test pattern only.

  **Acceptance Criteria**:
  - [ ] Harness can run known valid and invalid samples.
  - [ ] Results distinguish deterministic output from HERMES verdicts.

  **QA Scenarios**:
  ```
  Scenario: Replay sample run
    Tool: Bash/test command
    Preconditions: Evaluation harness configured
    Steps:
      1. Execute the replay suite on a fixed sample set.
      2. Assert metrics output includes accepted, rejected, vetoed, invalidated.
    Expected Result: Repeatable metrics are produced.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t10-replay.txt

  Scenario: Negative leakage check
    Tool: Bash
    Preconditions: Harness output exists
    Steps:
      1. Inspect evaluation metadata.
      2. Assert mode labels differentiate replay from live and decision-time from hindsight.
    Expected Result: No blended evaluation semantics.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t10-leakage.txt
  ```

- [x] T11. **Implement HERMES Standard-Deviation Expert Workflow**

  **What to do**:
  - Turn the HERMES doctrine into a runnable expert-review workflow for candidate anchors.
  - Ensure it evaluates screenshots and state against the original anchor philosophy only.

  **Must NOT do**:
  - Let HERMES invent new setup families.
  - Let HERMES approve without explicit reasons.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: T12, T14
  - **Blocked By**: T1, T2, T4, T8

  **References**:
  - T4 HERMES skill doctrine.
  - T8 sidecar observation contract.

  **Acceptance Criteria**:
  - [ ] HERMES workflow accepts candidate context and returns approve/veto + reasons.
  - [ ] Review output remains scoped to the agreed method.

  **QA Scenarios**:
  ```
  Scenario: Valid anchor review
    Tool: Sidecar workflow execution
    Preconditions: Known valid candidate context exists
    Steps:
      1. Feed candidate data + screenshot to HERMES.
      2. Assert response is approve with rule-based justification.
    Expected Result: HERMES approves only with explicit matching reasons.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t11-approve.json

  Scenario: Invalid anchor veto
    Tool: Sidecar workflow execution
    Preconditions: Known choppy/ambiguous candidate exists
    Steps:
      1. Feed invalid candidate data + screenshot to HERMES.
      2. Assert response is veto with rejection reason(s).
    Expected Result: HERMES rejects forced setups.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t11-veto.json
  ```

- [x] T12. **Build Pine-Sidecar Synchronization + Disagreement Handling**

  **What to do**:
  - Implement the handshake between Pine candidate states and HERMES verdict states.
  - Define chart-visible behavior when HERMES vetoes or supersedes a candidate.

  **Must NOT do**:
  - Resolve disagreements silently.
  - Break Pine-only drawing authority.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`tradingview-machine-profile`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: T13, F3
  - **Blocked By**: T1, T2, T6, T7, T8, T11

  **References**:
  - T2 authority contract.
  - T6/T7 Pine behavior.
  - T8/T11 HERMES behavior.

  **Acceptance Criteria**:
  - [ ] Vetoed candidates become chart-visible invalid/rejected states via Pine rules.
  - [ ] All disagreements are logged and testable.

  **QA Scenarios**:
  ```
  Scenario: Approved candidate sync
    Tool: TradingView + sidecar logs
    Preconditions: One candidate is approved by HERMES
    Steps:
      1. Trigger a valid candidate.
      2. Assert Pine chart shows active status after HERMES approval state arrives.
    Expected Result: Active state is visible and logged.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t12-approved.png

  Scenario: Vetoed candidate sync
    Tool: TradingView + sidecar logs
    Preconditions: One candidate is vetoed by HERMES
    Steps:
      1. Trigger a known invalid candidate.
      2. Assert Pine chart shows invalidated/rejected state and a matching veto log exists.
    Expected Result: Rejected state is chart-visible and auditable.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t12-veto.png
  ```

- [x] T13. **Build Chart-Facing Status UX + Alerts**

  **What to do**:
  - Add easy-to-read chart labels and alert messages for candidate, active, invalidated, zone-entry, and no-valid-leg states.
  - Keep the on-chart UX simple and educational.

  **Must NOT do**:
  - Overload chart with dense diagnostics.
  - Emit ambiguous alerts.

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`tradingview-pinescript-builder-doctor`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: F3
  - **Blocked By**: T2, T3, T6, T7, T12

  **References**:
  - T3 visual spec.
  - User requirement for simple youtuber-style readability.

  **Acceptance Criteria**:
  - [ ] Alert texts are explicit and map to chart-visible states.
  - [ ] Status labels remain readable on live chart screenshots.

  **QA Scenarios**:
  ```
  Scenario: Active setup messaging
    Tool: TradingView alert/state screenshot
    Preconditions: Approved active anchor exists
    Steps:
      1. Trigger active anchor state.
      2. Assert label includes direction, confidence, timeframe, and active status.
    Expected Result: Trader can understand setup at a glance.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t13-active.png

  Scenario: No-valid-leg messaging
    Tool: TradingView screenshot
    Preconditions: Choppy/no-setup sample loaded
    Steps:
      1. Run the script on no-setup data.
      2. Assert “No valid manipulation leg detected.” is the visible outcome or alert state.
    Expected Result: No forced levels; clear rejection message.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t13-no-valid.png
  ```

- [x] T14. **Build Continuous Training/Calibration Loop**

  **What to do**:
  - Implement the iterative review loop for collecting new examples, auditing disagreements, and refining HERMES without changing the core anchor doctrine.
  - Track false approvals, false vetoes, and ambiguous cases.
  - Add promotion gates so new HERMES skill versions only advance after passing replay/chart QA thresholds.

  **Must NOT do**:
  - Allow self-training to rewrite the core rules autonomously.
  - Blend evaluation data and training data without versioning.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3
  - **Blocks**: F3
  - **Blocked By**: T2, T4, T5, T8, T9, T11

  **References**:
  - T4 doctrine.
  - T5 dataset schema.
  - T8/T9/T11 decision records.

  **Acceptance Criteria**:
  - [ ] Versioned calibration loop defined and implemented.
  - [ ] Rule doctrine remains frozen unless explicitly changed by human review.
  - [ ] Promotion gate requires better or equal replay/chart-QA performance before a new skill version becomes active.

  **QA Scenarios**:
  ```
  Scenario: Calibration batch review
    Tool: Bash/API workflow
    Preconditions: Labeled disagreement batch exists
    Steps:
      1. Run a calibration pass on a batch of reviewed anchors.
      2. Assert outputs include version ID, reviewed counts, false-approve count, false-veto count.
    Expected Result: Continuous training is measurable and versioned.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t14-calibration.txt

  Scenario: Negative doctrine drift check
    Tool: Bash
    Preconditions: Calibration artifacts exist
    Steps:
      1. Inspect calibration output and config.
      2. Assert no core anchor-rule text or rule IDs changed automatically.
    Expected Result: Training refines expert behavior without mutating core doctrine.
    Evidence: .sisyphus/evidence/standard-deviation-anchor-ai/task-t14-drift.txt
  ```

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle`
  Verify all must-have behaviors exist, all must-not-have behaviors are absent, and all evidence files are present.

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run type/build/test checks, scan for AI slop, hidden logic drift, and unlogged decision paths.

- [x] F3. **Real Chart QA** — `unspecified-high`
  Execute every chart scenario on TradingView, capture screenshots, Pine compile evidence, and sidecar-decision logs.

- [x] F4. **Scope Fidelity Check** — `deep`
  Confirm the product stays locked to the original human-style anchor method and did not absorb legacy logic or unrelated strategy ideas.

---

## Commit Strategy

- Foundation/spec commits grouped by contract domain.
- Pine implementation commits grouped by detection/render lifecycle.
- Sidecar/training commits grouped by observation, audit, and calibration.

---

## Success Criteria

### Verification Commands
```bash
python -m pytest tests_v2 -q
cd dashboard && npm run test
cd dashboard && npm run typecheck
cd dashboard && npm run build
```

### Final Checklist
- [ ] Only valid bar-confirmed anchors render
- [ ] HERMES decisions are auditable
- [ ] No prior anchor business logic reused
- [ ] Visuals remain easy to understand on-chart
- [ ] Chop/unclear conditions correctly reject
