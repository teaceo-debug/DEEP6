---
phase: 12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi
plan: 04
type: execute
wave: 3
depends_on: [01, 02, 03]
files_modified:
  - deep6/orderflow/setup_tracker.py
  - deep6/orderflow/__init__.py
  - deep6/state/shared.py
  - deep6/api/store.py
  - tests/orderflow/test_setup_tracker.py
  - tests/orderflow/test_setup_tracker_integration.py
autonomous: true
requirements: [OFP-05, OFP-08]

must_haves:
  truths:
    - "Setup state machine tracks SCANNING → DEVELOPING → TRIGGERED → MANAGING → COOLDOWN per timeframe"
    - "Both 1-minute and 5-minute timeframes run independently and simultaneously"
    - "10-bar soak (DEVELOPING) yields 5x weight bonus vs 1-bar signal, linear ramp"
    - "TRAP_SHOT at GEX wall (triggers_state_bypass) jumps SCANNING → TRIGGERED directly"
    - "MANAGING → COOLDOWN is NOT auto — requires explicit close signal (PaperTrader / RithmicExecutor trade_close event)"
    - "All state transitions logged to EventStore (phase 09-01) for post-session debugging"
    - "Failsafe timeout: MANAGING > 30 bars without close forces COOLDOWN (prevents wedge)"
  artifacts:
    - path: "deep6/orderflow/setup_tracker.py"
      provides: "SetupTracker(timeframe) class with update(scorer_result, slingshot_result) and close_trade() methods"
      min_lines: 220
    - path: "tests/orderflow/test_setup_tracker.py"
      provides: "Unit tests for each transition + soak weight + bypass + explicit close"
    - path: "tests/orderflow/test_setup_tracker_integration.py"
      provides: "End-to-end: bar stream on 1m + 5m simultaneously"
  key_links:
    - from: "deep6/state/shared.py on_bar_close"
      to: "deep6/orderflow/setup_tracker.py SetupTracker.update"
      via: "called per TF after scorer + slingshot produce results"
      pattern: "setup_tracker\\.update"
    - from: "deep6/orderflow/setup_tracker.py"
      to: "deep6/api/store.py EventStore (setup_transition events)"
      via: "await store.record_setup_transition(...)"
      pattern: "record_setup_transition"
    - from: "deep6/execution/paper_trader.py (or rithmic_executor) trade_close"
      to: "SetupTracker.close_trade(setup_id)"
      via: "explicit call — no auto-transition"
      pattern: "close_trade"
---

<objective>
Build the setup state machine (`SetupTracker`) that wraps `ScorerResult` with a 5-state lifecycle: SCANNING → DEVELOPING → TRIGGERED → MANAGING → COOLDOWN. Runs simultaneously on 1-min (tactical) AND 5-min (strategic) timeframes. Implements 10-bar soak bonus (5x weight, linear ramp), `TRAP_SHOT` GEX-wall bypass, and **explicit-close-only** transition from MANAGING to COOLDOWN (reference-impl footgun fixed). Logs every transition to the phase 09-01 EventStore.

Purpose: The state machine turns a noisy per-bar signal stream into a structured trade lifecycle. Soak-weighting rewards setups that persist across bars (higher conviction than single-bar fires).
Output: `deep6/orderflow/setup_tracker.py`, EventStore schema addition, SharedState integration.
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
@.planning/phases/09-ml-backend/09-01-SUMMARY.md

# Reference implementation (lines 29-275)
@/Users/teaceo/Downloads/kronos-tv-autotrader/python/setup_tracker.py

# DEEP6 integration surfaces
@deep6/state/shared.py
@deep6/scoring/scorer.py
@deep6/api/store.py

<interfaces>
From deep6/scoring/scorer.py:
```python
@dataclass
class ScorerResult:
    total_score: float     # 0-100, post-VPIN
    tier: str              # TYPE_A / TYPE_B / TYPE_C / NONE
    direction: str         # LONG / SHORT / NEUTRAL
    flags: int             # bitmask incl. bit 44 TRAP_SHOT
    categories_agreeing: int
    # ...
```

From plan 03:
```python
@dataclass
class SlingshotResult:
    fired: bool
    triggers_state_bypass: bool    # → skip DEVELOPING
    direction: str
```

From deep6/api/store.py (phase 09-01 EventStore):
```python
class EventStore:
    async def record_signal_event(event: dict) -> None: ...
    # This plan ADDS: async def record_setup_transition(...)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>T-12-04-01: SetupTracker state machine core — failing tests + implementation (1m only first)</name>
  <files>deep6/orderflow/setup_tracker.py, deep6/orderflow/__init__.py, tests/orderflow/test_setup_tracker.py</files>
  <behavior>
    States: SCANNING, DEVELOPING, TRIGGERED, MANAGING, COOLDOWN
    Transitions (per 12-CONTEXT.md):
      - SCANNING → DEVELOPING: ScorerResult.tier in {TYPE_B, TYPE_C} with aligned direction, score >= 35
      - DEVELOPING → TRIGGERED: soak_bars >= 10 AND score crosses TYPE_A threshold (>=80), OR TRAP_SHOT fires aligned
      - SCANNING/DEVELOPING → TRIGGERED (BYPASS): SlingshotResult.triggers_state_bypass == True AND direction aligned
      - TRIGGERED → MANAGING: after 1 bar (entry confirmed)
      - MANAGING → COOLDOWN: ONLY via explicit close_trade(setup_id) call — NOT auto
      - MANAGING → COOLDOWN (FAILSAFE): bars_managing > 30 — logs warning, forces COOLDOWN
      - COOLDOWN → SCANNING: after cooldown_bars (default 5)
      - DEVELOPING → SCANNING: score drops below 25 OR direction flips (reset soak)
    Soak bonus (exposed via current_weight() -> float):
      - SCANNING/COOLDOWN: 0.0
      - DEVELOPING: linear ramp 1.0 (bar 0) → 5.0 (bar 10+), per formula 1.0 + 0.4 * min(soak_bars, 10)
      - TRIGGERED/MANAGING: 5.0 (held)
    ActiveSetup dataclass: setup_id, setup_type, direction, entry_score, soak_bars, bars_managing, started_at_bar
    Tests:
      - test_scanning_to_developing: feed TYPE_B long → state DEVELOPING, soak=1
      - test_developing_soak_weight_ramps: 10 consecutive bars → current_weight rises to 5.0
      - test_developing_to_triggered_on_tier_cross: score crosses 80 after 10-bar soak → TRIGGERED
      - test_slingshot_bypass: SCANNING + SlingshotResult(triggers_state_bypass=True, direction=LONG) aligned → immediate TRIGGERED (no DEVELOPING phase)
      - test_developing_resets_on_direction_flip: TYPE_B long 5 bars, then TYPE_B short → state → SCANNING, soak=0
      - test_triggered_to_managing: 1 bar after TRIGGERED → MANAGING
      - test_managing_no_auto_cooldown: 29 bars in MANAGING without close_trade → still MANAGING
      - test_managing_failsafe_at_31_bars: 31 bars without close → forced COOLDOWN with log warning
      - test_explicit_close_transitions_to_cooldown: call close_trade(setup_id) → COOLDOWN
      - test_cooldown_returns_to_scanning: cooldown_bars elapse → SCANNING
  </behavior>
  <action>
    Create deep6/orderflow/setup_tracker.py (~250 lines):
    - ActiveSetup dataclass
    - State = Literal["SCANNING","DEVELOPING","TRIGGERED","MANAGING","COOLDOWN"]
    - SetupTracker(timeframe: str, cooldown_bars: int = 5, managing_failsafe_bars: int = 30)
    - update(scorer_result, slingshot_result, current_bar_index) -> Optional[SetupTransition] (for logging)
    - close_trade(setup_id: str, outcome: str) -> Optional[SetupTransition]
    - current_weight() -> float: ramp logic
    - Private _try_bypass, _advance_state, _reset_soak
    - structlog.get_logger for transitions
    Update deep6/orderflow/__init__.py to export.
    Write all 10 unit tests.
    **Do NOT auto-transition MANAGING → COOLDOWN** — the reference impl's `setup_tracker.py:240-248` auto-cycle is the documented footgun and must NOT be ported.
  </action>
  <verify>
    <automated>pytest tests/orderflow/test_setup_tracker.py -x -q</automated>
  </verify>
  <done>All 10 transition tests pass; SetupTracker enforces explicit-close rule.</done>
</task>

<task type="auto" tdd="true">
  <name>T-12-04-02: Extend EventStore with setup_transitions table; log every transition</name>
  <files>deep6/api/store.py, tests/test_ml_backend.py (augment)</files>
  <behavior>
    - EventStore gains async method record_setup_transition(timeframe, setup_id, from_state, to_state, trigger, weight, bar_index, timestamp)
    - New SQLite table: setup_transitions (id INTEGER PK, timeframe TEXT, setup_id TEXT, from_state TEXT, to_state TEXT, trigger TEXT, weight REAL, bar_index INTEGER, ts REAL)
    - Idempotent init: CREATE TABLE IF NOT EXISTS
    - Test: record 3 transitions → SELECT returns 3 rows in order
    - Test: existing signal_events / trade_events tables untouched
    - Query helper: query_setup_transitions(session_start_ts, session_end_ts) -> list[dict]
  </behavior>
  <action>
    Modify deep6/api/store.py:
    - Add table DDL in _initialize
    - Add record_setup_transition async method
    - Add query_setup_transitions async helper
    - Extend tests/test_ml_backend.py with two tests (append — don't break existing): test_setup_transitions_table_created, test_record_and_query_round_trip
  </action>
  <verify>
    <automated>pytest tests/test_ml_backend.py -x -q</automated>
  </verify>
  <done>EventStore persists setup transitions; existing tables/tests unaffected.</done>
</task>

<task type="auto" tdd="true">
  <name>T-12-04-03: Wire dual-TF (1m + 5m) SetupTracker into SharedState.on_bar_close + integration test</name>
  <files>deep6/state/shared.py, tests/orderflow/test_setup_tracker_integration.py</files>
  <behavior>
    - SharedState owns self._tracker_1m = SetupTracker("1m") and self._tracker_5m = SetupTracker("5m")
    - on_bar_close for 1m bar: calls _tracker_1m.update(scorer_result, slingshot_result, bar_idx_1m); awaits store.record_setup_transition if transition returned
    - on_bar_close for 5m bar: calls _tracker_5m.update(...) with 5m scorer result; independent state
    - SharedState.close_trade(setup_id, outcome) → routes to correct tracker by setup_id prefix ("1m-..." / "5m-...")
    - Integration test: 30-bar synthetic stream → both trackers advance independently; 1m reaches TRIGGERED on bar 12, 5m still DEVELOPING (each 5m bar = 5x 1m soak)
    - Integration test: TRAP_SHOT bypass fires on 1m → 1m jumps to TRIGGERED; 5m unaffected
    - Integration test: explicit close_trade on 1m → 1m enters COOLDOWN; 5m still MANAGING until its own close
  </behavior>
  <action>
    Modify deep6/state/shared.py:
    - Instantiate both trackers in build()
    - In on_bar_close handlers, after scorer + slingshot produce results, call tracker.update with the appropriate timeframe's results
    - Await store.record_setup_transition(...) if update returns a transition
    - Add SharedState.close_trade(setup_id, outcome) method routing to correct tracker; to be called from execution layer (plan currently exists as entry point — execution wiring is phase 08 concern and left as explicit call site)
    Create tests/orderflow/test_setup_tracker_integration.py with 3 integration tests using SharedState.build() (or a minimal harness) driving synthetic 1m + 5m bar streams.
  </action>
  <verify>
    <automated>pytest tests/orderflow/ tests/test_ml_backend.py -x -q</automated>
  </verify>
  <done>Dual-TF state machine runs; transitions logged to EventStore; explicit-close rule enforced end-to-end.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Scorer → SetupTracker | Trusted internal dataflow |
| Execution layer → SetupTracker.close_trade | Trusted internal call from PaperTrader / RithmicExecutor |
| SetupTracker → EventStore | Async write; must not block bar-close path |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-12-04-01 | Denial of Service | State machine wedged in MANAGING (forever) | mitigate | Failsafe 30-bar timeout; unit test forces this |
| T-12-04-02 | Denial of Service | EventStore blocking on_bar_close on slow disk | mitigate | Transition logging is await + single row INSERT — aiosqlite non-blocking for single event loop |
| T-12-04-03 | Tampering | Wrong setup_id routed to wrong tracker | mitigate | Prefix convention "1m-..." / "5m-..." enforced in create; unit test asserts |
| T-12-04-04 | Repudiation | Transitions unlogged for post-session forensics | mitigate | All transitions persisted to EventStore — queryable by ts range |
</threat_model>

<verification>
- `pytest tests/orderflow/ tests/test_ml_backend.py -x` green
- `grep -n "MANAGING.*COOLDOWN" deep6/orderflow/setup_tracker.py` shows ONLY failsafe + explicit_close paths (no auto)
- Manual: kill test that attempts a bar-driven auto MANAGING → COOLDOWN; must never pass
- Full suite still green
</verification>

<success_criteria>
1. 5-state machine enforces exact transition rules from 12-CONTEXT.md
2. Both 1m and 5m trackers run simultaneously and independently
3. 10-bar soak → 5x weight via linear ramp
4. Slingshot bypass works when triggers_state_bypass is set
5. MANAGING → COOLDOWN requires explicit close_trade (reference footgun fixed)
6. Failsafe 30-bar timeout prevents permanent wedge
7. Every transition persists to EventStore setup_transitions table
</success_criteria>

<footguns>
**FOOTGUN 1 — Reference impl's auto MANAGING → COOLDOWN (`setup_tracker.py:240-248`):** Ported naively this would transition after a fixed bar count regardless of actual trade status. **Mitigation LOCKED:** explicit-close-only; failsafe only as a 30-bar emergency brake with warning log. This is the defining fix for this plan.

**FOOTGUN 2 — 5m soak ramp math:** If you compute 5m soak as `5x 1m soak bars`, setups trigger too quickly on 5m. Correct: each 5m bar counts as ONE soak bar. Document explicitly in code comment.

**FOOTGUN 3 — EventStore write blocking bar close:** aiosqlite is non-blocking but ~1-5ms per INSERT; at 1 transition/bar it's fine, but if every signal were logged it could queue. Only TRANSITIONS log (typically 1-2/bar max).

**FOOTGUN 4 — setup_id collisions across TFs:** Use prefix "1m-{uuid}" / "5m-{uuid}" — no cross-TF collisions possible. close_trade routes by prefix.

**FOOTGUN 5 — State machine blocking asyncio loop:** All transitions are O(1); no I/O except the awaited EventStore INSERT. Never use `asyncio.sleep` inside the machine — timing is driven by bar-close events only.
</footguns>

<rollback>
1. Disable tracker updates via feature flag in SharedState (skip update calls).
2. `git revert` removes SetupTracker module; setup_transitions table remains (harmless, empty if never used).
3. EventStore schema is append-only; no DROP TABLE required.
</rollback>

<output>
After completion, create `.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-04-SUMMARY.md`
</output>
