# Learnings — Standard Deviation Anchor AI

## Session: ses_1b2a7e1e3ffeL0LdRtksTCdB77 | 2026-05-22

### Project Constraints (CRITICAL — read before every delegation)
- TradingView first. Pine is the ONLY chart drawer.
- HERMES is an external veto sidecar — it watches, approves/vetoes, logs. It does NOT draw.
- Bar-confirmed anchors only. No intrabar finalization.
- 1m is primary. 5m/15m add context/confidence only — they do NOT override.
- Do NOT reuse prior anchor-selection or trading business logic from deep6/ or any other module.
- Only reuse infrastructure/integration patterns (persistence, bridge, capture) where needed.
- Visuals must stay simple and human-style (youtuber-readable).
- HERMES can improve its judgment quality over time but cannot autonomously rewrite the core anchor doctrine.

### Architecture Decisions
- Anchor lifecycle states: candidate → confirmed → active → invalidated → superseded
- Displacement confirmation requires: local structure break + impulsive candle/range expansion
- Chop rejection is mandatory — "No valid manipulation leg detected." is a valid output
- Disagreements between Pine and HERMES must always be logged, never silent
- Dataset = screenshot + synchronized structured state (never screenshot-only)
- Promotion gates required before new HERMES skill versions go active

### File Placement (infrastructure patterns only)
- Sidecar orchestration pattern: deep6/copilot/session.py
- Screenshot capture pattern: deep6/copilot/vision.py
- Audit/result parsing pattern: deep6/copilot/vision_analysis.py
- Persistence pattern: deep6/api/store.py
- TradingView bridge pattern: deep6v2/tradingview/client.py
- Data contract style: docs/FOOTPRINT-DATA-CONTRACT.md (style only, not logic)

## Session: ses_anchor_contract_t1 | 2026-05-21

### Contract Learnings
- Canonical anchor doctrine is now explicitly frozen as wick-to-wick manipulation leg -> displacement confirmation, with state machine candidate -> confirmed -> active -> invalidated -> superseded.
- Promotion threshold is contractually score >= 70 using the fixed 25/25/20/15/15 model.
- Chop rejection must explicitly return `No valid manipulation leg detected.` whenever anchor choice becomes forced, stale, too small, or ambiguous.

## Session: ses_1b2a7e1e3ffeL0LdRtksTCdB77 | 2026-05-21

### HERMES Authority Contract
- Formalized HERMES as approve/veto/abstain sidecar only; Pine remains sole chart drawer and lifecycle owner.
- Added explicit disagreement definition: deterministic Pine pass + HERMES veto, or HERMES approve + later Pine invalidation.
- Locked audit minimum fields for every decision event: anchor_id, timestamp_decision, symbol, timeframe, pine_candidate_state, hermes_verdict, hermes_reasons[], pine_final_state, human_override, disagreement.
- Confirmed async policy: Pine must continue without blocking on HERMES and must log timeout/delay impacts when review completion is affected.

## Session: T4 Skill Authoring | 2026-05-21

### HERMES Skill Created
- File: .claude/skills/hermes-sd-anchor/knowledge.md
- Version: 1.0.0 (doctrine frozen)
- Skill ID: hermes-sd-anchor`n
### Key Structural Decisions
- Verdict format is machine-parseable (structured block, not prose) � required for T11 Pine integration
- ABSTAIN is a distinct state from VETO; it means insufficient data, not a soft rejection
- Promotion gate requires minimum 20 labeled examples; both false-approve and false-veto rates must hold or improve
- Disagreement logging is mandatory and structured � feeds T14 training dataset pipeline
- Continuous improvement calibrates judgment quality only; checklist items and threshold are frozen at v1.0.0

### Downstream Notes for T11 and T14
- T11 (Pine integration): consume VERDICT field; treat ABSTAIN as no-verdict, keep anchor in candidate state
- T14 (training pipeline): pair every screenshot with structured state; never screenshot-only labels
- Both tasks must coordinate before any HERMES MAJOR version bump

## Session: T5 Dataset Schema | 2026-05-21

### Schema Design Decisions
- Each anchor state transition produces its own record with unique anchor_id — not an update to a prior record. Related records are linked by matching anchor endpoints + direction.
- outcome_label uses hierarchical resolution: -4 > -2.5 > -2 (first target reached wins, prioritizing the deepest).
- `pending` is a display-only concept; the actual record stores `null` until resolved.
- Level ordering validation differs by direction: bullish targets are below anchor, bearish targets are above.
- chart_metadata captures presentation state (zoom, visible range, candle style, theme, dimensions) to make screenshots reproducible.
- Outcome resolver is explicitly a SEPARATE process from capture bridge — this is the core leakage firewall.
- JSONL chosen over CSV/Parquet for append-only simplicity and human readability; bulk analysis can cat-concatenate daily files.
- Date partitioning uses captured_at UTC, not trading session date — simpler and avoids session-boundary ambiguity.

## Session: T3 Visual Spec | 2026-05-21

### Visual Spec Decisions
- Object budget: 4 lines + 1 box + 3 labels per setup = 8 objects per setup
- Pine limits set to max_lines_count=10, max_boxes_count=5, max_labels_count=10 — supports 2 concurrent setups
- Superseded setups are fully deleted (no ghost lines) to free budget
- Anchor endpoint markers: xcross for start, circle for end — gives directional reading X→O
- -4 level is always dashed even in active state (speculative nature)
- Zone fill uses box.new() not fill() — box supports dynamic lifecycle and xloc.bar_time natively
- All long-lived objects use xloc.bar_time, never xloc.bar_index
- Status label tracks at -2σ price and moves rightward with each confirmed bar
- Invalidated objects stay visible (gray/dotted) until superseded; completed objects freeze in place
- "No Valid Leg" state uses a single label only — no lines or boxes created

## Session: task-t6-valid-candidate | 2026-05-21

### Detection Engine Learnings
- Deterministic candidate detection can stay rendering-free by exposing hidden plots plus a JSON alert payload; T7 can layer visuals without touching the candidate engine rules.
- Pivot-confirmed manipulation detection works best when the opposite swing is resolved first (previous pivot high before bullish low, previous pivot low before bearish high), then the confirmation bar must close through that structure with an impulsive body.
- Ambiguity rejection is easier to keep deterministic by counting nearby pivot extrema within a mintick-based tolerance window; if more than one comparable endpoint exists, reject as forced.
- Chop rejection can be approximated without ATR/VWAP by combining directional-close ratio, body-overlap ratio, midpoint re-entry, confirmation-delay limit, and minimum wick-to-wick range.

## Session: T10 Replay Harness | 2026-05-21

### Replay Harness Learnings
- Replay fixtures now live under `tests_v2/sd_anchor/fixtures/` and intentionally carry `mode: replay` plus `label_timing: decision_time` to keep replay evidence separate from live or hindsight-labeled samples.
- The test harness separates deterministic Pine acceptance counts from HERMES approve/veto counts, and explicitly measures disagreement instead of collapsing them into one outcome.
- Capture-time fixtures keep `outcome_label: null` and `outcome_resolved_at: null` so replay evaluation stays decision-time clean.
- This task's required bearish `-4` expectation for `(anchor_low=100, anchor_high=110)` is `50`; the replay harness reflects that explicit task contract.

## Session: T8 HERMES Sidecar Bridge | 2026-05-21

### Sidecar Architecture
- SDSidecar uses asyncio.Queue for non-blocking candidate ingestion — Pine never waits on HERMES.
- HERMES timeout returns abstain verdict with CANDIDATE_METADATA_INCOMPLETE reason, not an error.
- _invoke_hermes() is a placeholder stub returning abstain — replaced when hermes-sd-anchor skill (T4) is wired.
- Disagreement detection covers Type 1 only at review time (Pine passes + HERMES vetoes). Type 2 (HERMES approves + Pine later invalidates) requires downstream state transition monitoring.
- Chart state capture follows TradingView MCP graceful degradation pattern from deep6v2/tradingview/client.py — returns empty snapshot when TV not connected.
- Audit and disagreement logs are separate append-only JSONL files, date-partitioned under data/sd_anchor/.
- validate_candidate() checks all required fields from dataset-schema.md Section 1.1 before queueing.
- HermesVerdict is frozen dataclass with post_init validation — verdict must be approve/veto/abstain, reasons must be non-empty.

## Session: T12 Pine-Sidecar Sync | 2026-05-21

### Sync Architecture
- AnchorSyncManager is stateless except for an in-memory disagreement log — all persistent state lives in LabelStore.
- State transition mapping: approve→active, veto→invalidated, abstain→candidate (hold). Clean 1:1 verdict→state mapping.
- Pine alert payload uses underscore-format action names (promote_active, mark_invalidated, hold_candidate) for Pine consumption.
- Disagreement detection is Type 1 only at sync time (Pine score≥70 + HERMES veto). Type 2 (HERMES approve + later Pine invalidation) requires downstream state monitoring.
- write_hermes_verdict is write-once in LabelStore; sync gracefully skips if already written (logs warning, does not crash).
- SyncResult is a frozen dataclass carrying the full log_entry dict for downstream consumers — avoids re-querying the store.
- get_pine_alert_payload prefixes reason with [DISAGREEMENT] when disagreement=True for chart-visible transparency.
