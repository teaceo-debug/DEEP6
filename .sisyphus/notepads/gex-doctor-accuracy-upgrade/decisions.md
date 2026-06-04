# GEX Doctor Accuracy Upgrade — Decisions

## 2026-05-31 — T4 HMM regime gate
- Added `gex_terminal/engine/regime_gate.py` as a thin compatibility wrapper instead of calling `deep6.ml.hmm_regime.HMMRegimeDetector` directly from the orchestrator.
- Kept HMM integration fail-open: missing `hmmlearn`, import failures, invalid feature vectors, or unfitted detector state all resolve to `UNKNOWN` so confidence is unchanged.
- Applied tradability gating inside `GEXAnalyzer.analyze(..., hmm_state=...)` so all existing confidence modifiers remain intact and the HMM penalty is the final confidence adjustment before direction/grade.
- Stored the resolved regime in `GEXTerminalSnapshot.hmm_regime` so downstream UI/API consumers can inspect the gate decision independently of the confidence penalty.

## 2026-05-31 — T5/T6 conviction matrix + PO3 anchor
- Added `gex_terminal/engine/conviction.py` as a dedicated 5-river scorer instead of burying river-count logic inside `analyzer.py`; this keeps the analyzer readable and testable.
- Added `gex_terminal/engine/po3_gate.py` as a fail-open adapter over `PO3BiasDetector` rather than binding the analyzer directly to deep6 PO3 stateful internals.
- Kept conviction grade authoritative for directional calls, but only trigger `stand_aside` below 2 agreeing rivers to preserve existing analyzer behavior while still forcing `F` on truly unsupported directional calls.
- Extended `AnalysisResult` + `GEXTerminalSnapshot` with `conviction_grade`, `conviction_rivers`, and `po3_state` so UI/API consumers can read the new confidence evidence without re-deriving it.

## 2026-06-01 — T9 Claude daily learner
- Added `gex_terminal/engine/learner.py` as an optional, fail-open daily memory layer that stores session summaries under `~/.deep6/gex_learnings` and never blocks per-cycle analysis with disk I/O.
- Kept learner persistence end-of-session only by wiring `GEXOrchestrator.run()` cleanup to `save_session(...)`; `_run_cycle()` only records in-memory cycle snapshots.
- Extended `ClaudeInterpreter` with an optional `SessionLearner` dependency so recent learnings can be prepended to the prompt without making learning mandatory for normal runtime paths.
