---
phase: 12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi
plan: 03
type: execute
wave: 2
depends_on: [02]
files_modified:
  - deep6/signals/flags.py
  - deep6/orderflow/slingshot.py
  - deep6/orderflow/__init__.py
  - deep6/state/shared.py
  - tests/orderflow/test_slingshot.py
  - tests/test_signal_flags.py
autonomous: true
requirements: [OFP-02, OFP-08]

must_haves:
  truths:
    - "New signal TRAP_SHOT fires at bit 44 (first free slot; bits 0-43 unchanged)"
    - "Detects 2/3/4-bar trapped-trader reversal using z-score > 2.0 over session window"
    - "delta_history resets at RTH session boundary (prevents cross-session threshold drift)"
    - "Minimum 30 bars of delta_history before any fire (warmup gate)"
    - "When firing within GEX wall distance threshold, signals the setup state machine to bypass DEVELOPING"
    - "Existing DELT_SLINGSHOT (bit 28) is UNTOUCHED — it's a different pattern (compressed-then-explosive intra-pattern)"
  artifacts:
    - path: "deep6/orderflow/slingshot.py"
      provides: "SlingshotDetector class with detect(bars, gex_proximity) -> SlingshotResult"
      min_lines: 140
    - path: "deep6/signals/flags.py"
      provides: "TRAP_SHOT = 44 constant; bits 0-43 preserved"
      contains: "TRAP_SHOT"
    - path: "tests/orderflow/test_slingshot.py"
      provides: "Tests for 2/3/4-bar bull/bear, warmup, session reset, GEX bypass signal"
  key_links:
    - from: "deep6/state/shared.py on_bar_close"
      to: "deep6/orderflow/slingshot.py SlingshotDetector.detect"
      via: "called after bar close with last-N bar history"
      pattern: "slingshot\\.detect"
    - from: "deep6/orderflow/slingshot.py"
      to: "SlingshotResult.triggers_state_bypass (consumed by plan 04 state machine)"
      via: "boolean flag set when GEX proximity < threshold"
      pattern: "triggers_state_bypass"
---

<objective>
Add multi-bar trapped-trader reversal detector (`TRAP_SHOT`) at new SignalFlags bit 44. Covers 2/3/4-bar variants. Z-score threshold > 2.0 over session-bounded delta history. Resets at RTH session boundary. When firing near a GEX wall, emits `triggers_state_bypass=True` so plan 04's setup state machine can jump SCANNING→TRIGGERED.

Purpose: Capture the multi-bar trapped-trader reversal pattern from the reference implementation — different from existing bit 28 `DELT_SLINGSHOT` (compressed→explosive intra-pattern). Both patterns coexist cleanly.
Output: `deep6/orderflow/slingshot.py`, new bit 44 constant, integration in SharedState.on_bar_close.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-CONTEXT.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-RESEARCH.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-02-SUMMARY.md

# Reference implementation (lines 269-378)
@/Users/teaceo/Downloads/kronos-tv-autotrader/python/orderflow_tv.py

# DEEP6 integration surfaces
@deep6/signals/flags.py
@deep6/state/shared.py
@deep6/engines/delta.py
@deep6/engines/gex.py

<interfaces>
From deep6/signals/flags.py (current):
```python
# Bit 28 = DELT_SLINGSHOT — EXISTING pattern (compressed intra-bar → explosive)
#                          "72-78% win rate" from delta.py line 216-232
#                          DIFFERENT math from TRAP_SHOT. DO NOT REUSE.
# Bit 43 = highest currently used
# Bit 44 = free — claimed by this plan as TRAP_SHOT
```

From /Users/teaceo/Downloads/kronos-tv-autotrader/python/orderflow_tv.py lines 269-378:
```python
# 2-bar bull pattern (line 296-307):
#   b2 bearish + b2.delta < -threshold + b1 bullish + b1.close > b2.high + b1.delta > threshold
# threshold = np.mean(np.abs(delta_history[-50:])) * 1.5
```

From deep6/engines/gex.py:
```python
# Provides GEX wall levels; distance-to-wall available via context passed to scorer
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>T-12-03-01: Add TRAP_SHOT bit 44 constant + scaffold failing tests</name>
  <files>deep6/signals/flags.py, tests/orderflow/test_slingshot.py, tests/test_signal_flags.py</files>
  <behavior>
    - SignalFlags.TRAP_SHOT = 44 (first free slot)
    - All existing bit constants (0-43) bit positions UNCHANGED
    - Mask/serialization tests still green
    - DELT_SLINGSHOT (bit 28) name and bit UNTOUCHED
    - Failing tests written for SlingshotDetector (not yet implemented)
  </behavior>
  <action>
    Modify deep6/signals/flags.py: add TRAP_SHOT = 44 with docstring citing 12-CONTEXT.md: "multi-bar trapped-trader reversal — DIFFERENT from DELT_SLINGSHOT (bit 28). 2/3/4-bar variants; z>2.0 session-bounded; may trigger setup state bypass."
    Update tests/test_signal_flags.py: add test_trap_shot_bit_44 asserting SignalFlags.TRAP_SHOT == 44; add test_all_stable_bits_unchanged explicitly listing 0-43 and asserting each is correct (prevents accidental shifts).
    Create tests/orderflow/test_slingshot.py with failing tests:
      - test_2bar_bull_fires: synthetic 2 bars matching template → detect() returns TRAP_SHOT flag set, variant=2, direction=LONG
      - test_2bar_bear_fires: symmetric bear pattern
      - test_3bar_bull_fires, test_4bar_bull_fires
      - test_below_threshold_no_fire: delta < 2-sigma threshold → no fire
      - test_warmup_30_bars: <30 bars of history → no fire regardless of pattern
      - test_session_reset_clears_history: call reset_session() → delta_history empty, warmup restarts
      - test_gex_proximity_sets_bypass: fire with gex_distance < threshold → result.triggers_state_bypass == True
      - test_coexists_with_delt_slingshot: bit 28 can fire without affecting bit 44 (independent detectors)
  </action>
  <verify>
    <automated>pytest tests/test_signal_flags.py -x -q && pytest tests/orderflow/test_slingshot.py -x -q 2>&1 | grep -E "(ImportError|8 failed|7 failed)"</automated>
  </verify>
  <done>Signal flag bit 44 added; flag tests green; slingshot tests fail on ImportError.</done>
</task>

<task type="auto" tdd="true">
  <name>T-12-03-02: Implement SlingshotDetector with 2/3/4-bar variants, z-score threshold, session reset</name>
  <files>deep6/orderflow/slingshot.py, deep6/orderflow/__init__.py</files>
  <behavior>
    - Class SlingshotDetector(
        z_threshold=2.0,
        min_history_bars=30,
        history_maxlen=500,      # bounded; reset at session
        gex_proximity_ticks=8    # within 8 ticks of GEX wall → bypass
      )
    - detect(bars: Sequence[FootprintBar], gex_distance_ticks: float | None) -> SlingshotResult
      * Returns dataclass: fired: bool, variant: int (2|3|4|0), direction: "LONG"|"SHORT"|None, bias: float in [0,1], strength: float, triggers_state_bypass: bool
      * Needs at least max(variant) bars in the tail
    - update_history(bar_delta: int) -> None — appends to delta_history deque(maxlen=500)
    - reset_session() -> None — clears delta_history, bar_cache; called at RTH session boundary
    - Z-score threshold: sigma = np.std(delta_history[-session_window:]) where session_window = min(len, 200); threshold = 2.0 * sigma
    - 2-bar bull template (from reference lines 296-307):
        b[-2] bearish close<open, b[-2].delta < -threshold, b[-1] bullish close>open, b[-1].close > b[-2].high, b[-1].delta > threshold
    - 3-bar and 4-bar variants: extend pattern requiring progressive delta compression before reversal bar
    - Warmup gate: return no-fire if len(delta_history) < 30
  </behavior>
  <action>
    Create deep6/orderflow/slingshot.py (~150 lines):
    - Import numpy, dataclasses, collections.deque, structlog
    - SlingshotResult dataclass with fields above
    - SlingshotDetector with internal deque delta_history
    - Private _check_2bar / _check_3bar / _check_4bar returning Optional[SlingshotResult]
    - detect() calls each in turn, returns first fire (prefer longest variant for higher strength)
    - Strength calc: min(|b[-1].delta| / max(|b[-2].delta|, 1), 3.0) (reference line 297)
    - Bias: min(0.6 * strength / variant, 1.0)
    - triggers_state_bypass = True iff fired AND gex_distance_ticks is not None AND gex_distance_ticks < self.gex_proximity_ticks
    - Update deep6/orderflow/__init__.py: `from .slingshot import SlingshotDetector, SlingshotResult`
  </action>
  <verify>
    <automated>pytest tests/orderflow/test_slingshot.py -x -q</automated>
  </verify>
  <done>All 8 slingshot tests pass; SlingshotDetector importable and deterministic.</done>
</task>

<task type="auto" tdd="true">
  <name>T-12-03-03: Wire SlingshotDetector into SharedState; reset on session boundary; set flag bit 44</name>
  <files>deep6/state/shared.py, tests/orderflow/test_slingshot.py (add integration test)</files>
  <behavior>
    - SharedState owns one SlingshotDetector (1m) + one (5m) — separate state machines per TF
    - SharedState.on_bar_close calls detector.update_history(bar.bar_delta) FIRST, then detector.detect(last_N_bars, gex_distance)
    - If fired: SignalFlags bitmask gains bit 44 for this bar
    - SharedState.on_session_reset() calls detector.reset_session() for both TFs
    - gex_distance_ticks pulled from existing GEXEngine.get_nearest_wall_distance() (or equivalent) if available, else None
    - Result.triggers_state_bypass stored in SharedState.last_slingshot_result (consumed by plan 04)
    - Integration test: feed 2-bar bull template after 30 warmup bars → bit 44 appears in ScorerResult.flags; last_slingshot_result populated
  </behavior>
  <action>
    Modify deep6/state/shared.py:
    - In build(): self._slingshot_1m = SlingshotDetector(); self._slingshot_5m = SlingshotDetector()
    - In on_bar_close: call update_history + detect. If fired, OR bit 44 into the signal bitmask produced for this bar. Store result on self.last_slingshot_1m / last_slingshot_5m.
    - Add on_session_reset method (or augment existing one) that calls reset_session() on both detectors. Hook into existing RTH boundary detector (session.py).
    - Pull gex_distance from self._gex_engine if available; pass None otherwise.
    Add integration test in tests/orderflow/test_slingshot.py:
    - test_end_to_end_flag_set: drive synthetic bars through SharedState.on_bar_close, assert bit 44 appears in final flags
    - test_session_reset_called_at_rth_boundary: mock session boundary, assert reset_session invoked
  </action>
  <verify>
    <automated>pytest tests/orderflow/test_slingshot.py tests/test_signal_flags.py -x -q</automated>
  </verify>
  <done>Bit 44 fires end-to-end; session reset wired; last_slingshot_result exposed for plan 04.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Bar close → SlingshotDetector | Trusted internal state |
| Session boundary → reset_session | Depends on session.py correctness (validated phase 01) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-12-03-01 | Tampering | Accidentally renaming bit 28 DELT_SLINGSHOT or reusing bit | mitigate | Explicit flag test asserts 0-43 stability |
| T-12-03-02 | Denial of Service | Slingshot firing every bar in first 30 min of session (threshold drift) | mitigate | 30-bar warmup gate + session reset — tested explicitly |
| T-12-03-03 | Information Disclosure | GEX distance leaked via debug log | accept | Not sensitive |
</threat_model>

<verification>
- `pytest tests/orderflow/test_slingshot.py tests/test_signal_flags.py -x` green
- `grep -n "DELT_SLINGSHOT" deep6/engines/delta.py deep6/signals/flags.py` shows bit 28 unchanged
- `grep -n "TRAP_SHOT" deep6/signals/flags.py` shows bit 44
- Full suite still green: `pytest tests/ -x`
</verification>

<success_criteria>
1. SignalFlags.TRAP_SHOT exists at bit 44; existing 0-43 unchanged
2. SlingshotDetector detects 2/3/4-bar bull + bear templates on synthetic data
3. Warmup (<30 bars) and session reset both enforce no-fire
4. triggers_state_bypass set when within GEX wall proximity
5. Integration via SharedState.on_bar_close produces bit 44 in bar flag bitmask
</success_criteria>

<footguns>
**FOOTGUN 1 — Name collision with DELT_SLINGSHOT (bit 28):** The existing bit 28 is a completely different pattern (intra-bar compressed→explosive, 72-78% quoted win-rate from `delta.py:216`). If we named this `DELT_SLINGSHOT_V2` or reused bit 28, every backtest report and every LightGBM feature importance dump would silently conflate the two. **Mitigation LOCKED:** name is `TRAP_SHOT` (belongs in TRAP category semantically — it IS a trapped-trader reversal). Bit 28 untouched.

**FOOTGUN 2 — Session boundary drift:** Reference impl uses 500-bar rolling delta_history which spans overnight sessions. First session bar at 9:31 ET computes threshold on a 3pm-to-9:30am mix → garbage. **Mitigation LOCKED:** reset_session() called at RTH boundary (see 12-CONTEXT.md decisions).

**FOOTGUN 3 — Bit 44 collision with plan 02:** Plan 02 must NOT add a new bit. Plan 03 owns bit 44 exclusively. Verified by the explicit stability test in tests/test_signal_flags.py.

**FOOTGUN 4 — Serialization compatibility:** Any existing flag bitmask serialized pre-phase-12 has bit 44 = 0 (forward compatible per STATE.md). New records with bit 44 set will NOT round-trip correctly on a pre-phase-12 consumer — acceptable since phase 12 is the deployed version going forward.
</footguns>

<rollback>
1. Remove bit 44 import from SharedState wiring (one-line disable: skip detector.detect call).
2. Full revert: `git revert` — SignalFlags.TRAP_SHOT constant removed, SlingshotDetector module removed.
3. No schema changes — aiosqlite signal_events JSON will just have bit 44 always 0 post-revert.
</rollback>

<output>
After completion, create `.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-03-SUMMARY.md`
</output>
