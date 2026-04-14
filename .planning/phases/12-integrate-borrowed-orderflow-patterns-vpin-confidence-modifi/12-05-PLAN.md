---
phase: 12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi
plan: 05
type: execute
wave: 4
depends_on: [04]
files_modified:
  - deep6/orderflow/walk_forward_live.py
  - deep6/orderflow/__init__.py
  - deep6/api/store.py
  - deep6/ml/weight_loader.py
  - deep6/state/shared.py
  - tests/orderflow/test_walk_forward_live.py
  - tests/integration/__init__.py
  - tests/integration/test_phase12_end_to_end.py
autonomous: true
requirements: [OFP-06]

must_haves:
  truths:
    - "Tracker records every signal at bar close with (category, regime, direction, entry_price, entry_bar_index, session_id)"
    - "Outcomes resolve at 5/10/20-bar horizons with labels CORRECT / INCORRECT / NEUTRAL / EXPIRED"
    - "EXPIRED applies when horizon would span RTH session close (signal fired <20 bars before close)"
    - "Per-category (8 groups, matching WeightFile.weights structure from phase 09-02) × per-regime (HMM state) rolling Sharpe computed over 200-signal window"
    - "Auto-disable: category × regime cell with rolling Sharpe < threshold → category weight = 0 in that regime until recovery"
    - "Disabled cells recover when subsequent 50-signal window Sharpe > recovery threshold"
    - "Weight changes feed back into LightGBM meta-learner via WeightFile.regime_adjustments (reuse phase 09-02 slot)"
    - "Persistence via phase 09-01 EventStore (signal_events + new walk_forward_outcomes table) — NO JSON-on-disk sink"
  artifacts:
    - path: "deep6/orderflow/walk_forward_live.py"
      provides: "WalkForwardTracker with record_signal, update_price, get_weights_override, is_disabled"
      min_lines: 250
    - path: "deep6/api/store.py"
      provides: "walk_forward_outcomes table + async record/query methods"
      contains: "walk_forward_outcomes"
    - path: "deep6/ml/weight_loader.py"
      provides: "Apply tracker's per-regime × per-category disable mask to effective weights"
      contains: "regime_adjustments"
    - path: "tests/integration/test_phase12_end_to_end.py"
      provides: "End-to-end phase-12 bar stream through VPIN + TRAP_SHOT + SetupTracker + WalkForwardTracker"
  key_links:
    - from: "deep6/state/shared.py on_bar_close"
      to: "deep6/orderflow/walk_forward_live.py record_signal / update_price"
      via: "called after scorer emits ScorerResult with category votes"
      pattern: "walk_forward\\.record_signal|walk_forward\\.update_price"
    - from: "deep6/ml/weight_loader.py"
      to: "WalkForwardTracker.get_weights_override"
      via: "merged into effective WeightFile at runtime"
      pattern: "get_weights_override"
    - from: "WalkForwardTracker outcomes"
      to: "deep6/api/store.py walk_forward_outcomes table"
      via: "async record on resolution"
      pattern: "record_walk_forward_outcome"
---

<objective>
Build the per-regime × per-category walk-forward tracker. Records every signal at bar-close; resolves 5/10/20-bar outcomes against the price stream. Outcomes are labeled CORRECT / INCORRECT / NEUTRAL / EXPIRED (EXPIRED excludes session-boundary-spanning signals from win-rate stats). Slices by 8 categories × HMM regime states. Computes rolling Sharpe over 200-signal windows; auto-disables any cell falling below threshold, auto-recovers on subsequent 50-signal Sharpe recovery. Disabled cells feed into LightGBM meta-learner via phase 09-02's `WeightFile.regime_adjustments` slot. Reuses phase 09-01 `EventStore` — no JSON-on-disk sink.

Purpose: Closed-loop adaptive weighting — signals that fail in specific regimes automatically suppress themselves; recovery unblocks them. Completes the observability and control surface for phase 12.
Output: `deep6/orderflow/walk_forward_live.py`, EventStore schema addition, weight_loader feedback wiring, end-to-end integration test.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-CONTEXT.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-RESEARCH.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-01-SUMMARY.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-02-SUMMARY.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-03-SUMMARY.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-04-SUMMARY.md
@.planning/phases/09-ml-backend/09-01-SUMMARY.md
@.planning/phases/09-ml-backend/09-02-SUMMARY.md

# Reference implementation (lines 57-345)
@/Users/teaceo/Downloads/kronos-tv-autotrader/python/performance_tracker.py

# DEEP6 integration surfaces
@deep6/api/store.py
@deep6/ml/weight_loader.py
@deep6/ml/hmm_regime.py
@deep6/state/shared.py

<interfaces>
From phase 09-02 WeightFile:
```python
@dataclass
class WeightFile:
    weights: dict[str, float]               # 8 categories
    regime_adjustments: dict[str, dict[str, float]]   # regime -> category -> multiplier
    # regime_adjustments slot is ALREADY THERE — this plan populates it dynamically
```

From phase 09-02 HMMRegimeDetector:
```python
class HMMRegimeDetector:
    def get_current_regime(self) -> str       # "trending" / "mean_reverting" / "choppy"
```

From phase 09-01 EventStore:
```python
class EventStore:
    async def record_signal_event(event: dict) -> None: ...
    # THIS PLAN adds: walk_forward_outcomes table + async record/query methods
```

Eight signal categories (match WeightFile.weights keys):
absorption, exhaustion, imbalance, delta, auction, trap, volume_pattern, context
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>T-12-05-01: Extend EventStore with walk_forward_outcomes table + failing tracker tests</name>
  <files>deep6/api/store.py, tests/orderflow/test_walk_forward_live.py</files>
  <behavior>
    - walk_forward_outcomes table: (id PK, signal_event_id INTEGER FK signal_events.id, category TEXT, regime TEXT, direction TEXT, entry_price REAL, entry_bar_index INTEGER, session_id TEXT, horizon INTEGER, outcome_label TEXT, pnl_ticks REAL, resolved_at_ts REAL)
    - EventStore async methods: record_walk_forward_outcome(row), query_outcomes(category, regime, limit)
    - Failing unit tests in tests/orderflow/test_walk_forward_live.py:
      - test_record_signal_appended_to_pending: record_signal → pending list grows
      - test_5bar_resolution_correct: feed 5 upticks after LONG signal → outcome CORRECT, horizon=5
      - test_5bar_resolution_incorrect: feed 5 downticks after LONG → INCORRECT
      - test_neutral_resolution: price unchanged → NEUTRAL (|pnl_ticks| < neutral_threshold)
      - test_expired_at_session_boundary: LONG signal 15 bars before RTH close → 20-bar horizon EXPIRED (excluded from stats)
      - test_rolling_sharpe_per_category_regime: 200 synthetic signals → per (category, regime) Sharpe computed
      - test_auto_disable_below_threshold: force low Sharpe → get_weights_override returns 0 for that cell
      - test_auto_recovery_above_threshold: subsequent 50 signals with good Sharpe → cell re-enabled
      - test_bounded_pending: pending outcomes cap at 1000 — oldest dropped
  </behavior>
  <action>
    Modify deep6/api/store.py: add walk_forward_outcomes DDL + record/query methods. Keep signal_events/trade_events/setup_transitions untouched.
    Create tests/orderflow/test_walk_forward_live.py with 9 failing tests (WalkForwardTracker not yet implemented).
  </action>
  <verify>
    <automated>pytest tests/test_ml_backend.py -x -q && pytest tests/orderflow/test_walk_forward_live.py -x -q 2>&1 | grep -E "(ImportError|9 failed)"</automated>
  </verify>
  <done>walk_forward_outcomes table created + tested; tracker tests fail on ImportError.</done>
</task>

<task type="auto" tdd="true">
  <name>T-12-05-02: Implement WalkForwardTracker with per-category × per-regime outcome resolution + auto-disable/recovery</name>
  <files>deep6/orderflow/walk_forward_live.py, deep6/orderflow/__init__.py</files>
  <behavior>
    - Class WalkForwardTracker(
        store: EventStore,
        horizons: tuple = (5, 10, 20),
        sharpe_window: int = 200,
        disable_sharpe_threshold: float = 0.0,
        recovery_sharpe_threshold: float = 0.3,
        recovery_window: int = 50,
        neutral_threshold_ticks: float = 0.5,
        max_pending: int = 1000,
        session_close_buffer_bars: int = 20
      )
    - async record_signal(category, regime, direction, entry_price, bar_index, session_id, signal_event_id, bars_until_rth_close): pending entries per (horizon)
    - async update_price(close_price, bar_index, session_id, bars_until_rth_close) -> list[ResolvedOutcome]:
        * resolves any pending whose bar_index + horizon <= current; writes outcome to EventStore
        * if bars_until_rth_close < horizon at the time the signal was recorded → label EXPIRED, exclude from Sharpe stats
    - Private _compute_rolling_sharpe(category, regime) — reads last 200 from store (or in-memory mirror) returning Sharpe
    - get_weights_override() -> dict[str, dict[str, float]]: regime → category → multiplier (0.0 for disabled cells, 1.0 otherwise)
    - Disable cell when _compute_rolling_sharpe < disable_sharpe_threshold over >= sharpe_window signals (excluding EXPIRED)
    - Recovery: after cell disabled, watch next recovery_window signals; if Sharpe > recovery_sharpe_threshold → re-enable
    - All 9 unit tests from T-12-05-01 pass
    - Bounded pending: when max_pending exceeded, oldest pending entries are dropped + logged as EXPIRED
  </behavior>
  <action>
    Create deep6/orderflow/walk_forward_live.py (~280 lines):
    - Dataclass PendingOutcome, ResolvedOutcome
    - deque(maxlen=max_pending) for pending
    - In-memory rolling cache per (category, regime) of last sharpe_window pnl_ticks for fast Sharpe recomputation (avoid DB roundtrip every bar)
    - Sharpe: mean(pnl) / (std(pnl) + 1e-9); annualize unnecessary — rolling ratio is sufficient
    - Disable state kept in self._disabled: dict[(regime, category), bool]
    - structlog transitions ("cell disabled", "cell recovered")
    Update deep6/orderflow/__init__.py.
  </action>
  <verify>
    <automated>pytest tests/orderflow/test_walk_forward_live.py -x -q</automated>
  </verify>
  <done>All 9 tests pass; tracker supports disable + recovery lifecycle.</done>
</task>

<task type="auto" tdd="true">
  <name>T-12-05-03: Wire WalkForwardTracker into SharedState + weight_loader + end-to-end integration test</name>
  <files>deep6/state/shared.py, deep6/ml/weight_loader.py, tests/integration/__init__.py, tests/integration/test_phase12_end_to_end.py</files>
  <behavior>
    - SharedState.build() instantiates WalkForwardTracker(store=self._event_store, ...)
    - In on_bar_close 1m: after scorer_result emitted, if scorer_result.tier != "NONE" and categories_agreeing > 0: for each voting category, await tracker.record_signal(category, current_regime, direction, bar.close, bar_index, session_id, signal_event_id, bars_until_rth_close)
    - At bar close: await tracker.update_price(bar.close, bar_index, session_id, bars_until_rth_close)
    - weight_loader.py: new function apply_walk_forward_overrides(weight_file, tracker) -> WeightFile — merges get_weights_override() into regime_adjustments (multiplicative composition with any existing value)
    - Live LightGBM fusion path reads from the merged WeightFile — disabled cells force category weight to 0 in that regime
    - Integration test end-to-end (tests/integration/test_phase12_end_to_end.py):
      * 3-session synthetic stream (~200 bars total)
      * Drive through VPIN + TRAP_SHOT + SetupTracker + WalkForwardTracker
      * Assert: setup_transitions table populated, walk_forward_outcomes table populated, at least one cell auto-disables and recovers
      * Assert: VPIN multiplier visible on ScorerResult; bit 44 flagged on appropriate bars
      * Assert: EXPIRED outcomes appear for signals within last 20 bars of each session
    - All phase 09-01 FastAPI + EventStore tests still pass
  </behavior>
  <action>
    Modify deep6/state/shared.py: instantiate tracker; wire record_signal + update_price into on_bar_close; provide bars_until_rth_close from session.py helper (or compute from session end vs current time).
    Modify deep6/ml/weight_loader.py: add apply_walk_forward_overrides merging into regime_adjustments. Don't remove existing functionality.
    Create tests/integration/__init__.py empty.
    Create tests/integration/test_phase12_end_to_end.py (~200 lines) using SharedState.build() with injected stubs for EventStore + HMMRegimeDetector; synthetic 3-session bar stream; assertions listed above.
  </action>
  <verify>
    <automated>pytest tests/orderflow/ tests/integration/ tests/test_ml_backend.py tests/test_scorer.py -x -q</automated>
  </verify>
  <done>End-to-end phase-12 pipeline runs; weight overrides feed back into LightGBM fusion; session-boundary outcomes correctly EXPIRED.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Scorer → WalkForwardTracker | Trusted; one call per voting category per bar |
| HMM regime → tracker slicing | Regime string trusted from phase 09-02 detector |
| Tracker → weight_loader → LightGBM | Runtime mutation of effective weights; must not mid-bar flip |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-12-05-01 | Denial of Service | pending_outcomes unbounded growth | mitigate | Capped deque + explicit test |
| T-12-05-02 | Tampering | External tracker state file loaded at startup corrupted | mitigate | Tracker state is always rebuilt from EventStore on startup — no external file load path |
| T-12-05-03 | Tampering | Mid-bar weight flip causes scorer inconsistency | mitigate | apply_walk_forward_overrides called ONLY at bar close, not mid-bar |
| T-12-05-04 | Repudiation | Outcomes lost on crash before DB write | mitigate | aiosqlite WAL mode (existing phase 01 setting); each outcome awaits INSERT |
| T-12-05-05 | Information Disclosure | Per-regime Sharpe leaked in logs | accept | Non-sensitive internal metric |
</threat_model>

<verification>
- `pytest tests/orderflow/ tests/integration/ tests/test_ml_backend.py -x` green
- Full suite green: `pytest tests/ -x`
- Manual: inspect walk_forward_outcomes table after integration test; row count matches signal count minus EXPIRED
- Manual: grep `grep -n "json" deep6/orderflow/walk_forward_live.py` — no JSON-on-disk sink present
</verification>

<success_criteria>
1. Every signal at bar-close recorded with (category, regime, direction, entry_price, bar_index, session_id)
2. Outcomes resolve at 5/10/20 horizons; labeled CORRECT/INCORRECT/NEUTRAL/EXPIRED correctly
3. EXPIRED label applied to signals within 20 bars of RTH close (excluded from Sharpe)
4. Rolling 200-signal Sharpe computed per (category, regime) cell
5. Auto-disable fires when Sharpe < threshold; auto-recovery when subsequent 50-signal window Sharpe recovers
6. Disabled cells propagate to LightGBM fusion via WeightFile.regime_adjustments
7. All persistence via EventStore (phase 09-01) — no JSON-on-disk sink
8. End-to-end integration test passes with all prior phase-12 plans wired together
</success_criteria>

<footguns>
**FOOTGUN 1 — Session-boundary outcome mis-attribution:** Reference impl resolves at `entry_bar_index + horizon` with no session awareness. A signal fired at 15:55 ET resolves at 9:50 ET next day after an overnight gap — PnL dominated by macro, not the signal. **Mitigation LOCKED:** signals fired with `bars_until_rth_close < horizon` are labeled EXPIRED and excluded from rolling Sharpe.

**FOOTGUN 2 — JSON-on-disk sink:** Reference `performance_tracker.py` writes JSON files. Race-prone, not crash-safe, duplicates EventStore capability. **Mitigation LOCKED:** reuse phase 09-01 EventStore with walk_forward_outcomes table.

**FOOTGUN 3 — Mid-bar weight flip:** If `get_weights_override` were queried mid-bar during scoring, a cell transitioning disable→enable during the bar could produce inconsistent scores. **Mitigation LOCKED:** `apply_walk_forward_overrides` called once at bar close, snapshot into WeightFile for that bar's scoring pass.

**FOOTGUN 4 — Per-signal vs per-category granularity:** CONTEXT.md locks per-category (8 groups). Per-signal (44 bits) would have tiny sample sizes and over-disable. Deferred to future phase.

**FOOTGUN 5 — Sharpe with too few samples:** First 200 signals → Sharpe unreliable. Gate: do not auto-disable a cell until it has accumulated >= sharpe_window resolved (non-EXPIRED) outcomes.

**FOOTGUN 6 — HMM regime transitions mid-signal:** A signal fired under regime="trending" may resolve under regime="choppy". Attribution policy: slice by regime AT ENTRY, not at resolution.
</footguns>

<rollback>
1. Set tracker in SharedState to None and short-circuit calls — preserves EventStore data, disables live use.
2. weight_loader.apply_walk_forward_overrides becomes a no-op (return weight_file unchanged).
3. Full revert: `git revert` removes WalkForwardTracker; walk_forward_outcomes table remains (append-only, harmless).
4. LightGBM fusion continues on base WeightFile without overrides.
</rollback>

<output>
After completion, create `.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-05-SUMMARY.md`
</output>
