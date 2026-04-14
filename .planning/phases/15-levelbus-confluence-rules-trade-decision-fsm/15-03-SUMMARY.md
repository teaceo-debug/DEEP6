---
phase: 15-levelbus-confluence-rules-trade-decision-fsm
plan: 03
subsystem: engines
tags: [confluence-rules, scorer, meta-flags, phase-15]
requirements: [ZONE-02, GEX-04, GEX-05]
dependency_graph:
  requires:
    - "deep6/engines/level.py Level.uid + LevelKind + LevelState (from 15-01)"
    - "deep6/engines/zone_registry.py LevelBus.query_by_kind / get_all_active (from 15-01)"
    - "deep6/engines/vp_context_engine.py narrative_result wiring (from 15-02)"
    - ".planning/phases/15-.../RULES.md canonical 38 CR-XX rules (from 15-01)"
  provides:
    - "deep6/engines/confluence_rules.py ConfluenceAnnotations + evaluate() + 38 cr_XX rule bodies"
    - "deep6/engines/signal_config.py ConfluenceRulesConfig with per-rule enable flags + tunables"
    - "deep6/signals/flags.py 3 meta-flag bits (PIN_REGIME_ACTIVE, REGIME_CHANGE, SPOOF_VETO) + SIGNAL_BITS_MASK"
    - "deep6/scoring/scorer.py confluence_annotations kwarg + score_mutation application + veto-gated DISQUALIFIED tier"
    - "ScorerResult.meta_flags field for bit 45+ flags"
  affects:
    - "deep6/scoring/scorer.py zone-bonus loop now duck-typed over VolumeZone (legacy) and Level (post-15-01)"
    - "SignalTier enum adds DISQUALIFIED = -1"
tech_stack:
  added: []
  patterns:
    - "Stateless per-rule function dispatch in fixed CR-XX order (D-13)"
    - "Score mutations keyed by Level.uid (C5) — safe across merges"
    - "Regime priority merge (PIN > TREND > BALANCE > NEUTRAL) so specific labels survive generic overrides"
    - "Content-anchored scorer insertion between GEX block and Layer-2 category confluence (D-32)"
    - "Duck-typed zone accessor shims for VolumeZone/Level migration"
key_files:
  created:
    - "deep6/engines/confluence_rules.py"
    - "tests/engines/test_confluence_rules.py"
    - "tests/scoring/test_scorer_with_confluence.py"
  modified:
    - "deep6/engines/signal_config.py"
    - "deep6/signals/flags.py"
    - "deep6/scoring/scorer.py"
    - "tests/test_signal_flags.py"
decisions:
  - "ConfluenceAnnotations.score_mutations keyed by Level.uid (C5) not id(level); VolumeZone has no uid so legacy zones are skipped by design"
  - "Regime merge is priority-based not last-writer-wins, so CR-04 PIN is not clobbered by CR-10 NEUTRAL"
  - "3 meta-flag bits added at positions 45/46/47; bits 0-44 byte-identical to pre-commit (Phase 12 invariant verified)"
  - "SignalTier.DISQUALIFIED = -1 (below QUIET) — safe for existing ordinal comparisons"
  - "ScorerResult.meta_flags is SEPARATE from signal bits 0-44; SIGNAL_BITS_MASK exposed for popcount callers"
  - "CR-08 implements SOFT suppression via SUPPRESS_SHORTS flag only — actual 0.6× multiplier will be wired when FSM consumes the flag in 15-04 (per D-40 scope boundary)"
  - "Hawkes CR-22 ships as Poisson stub per D-35; full MLE deferred to future worker behind ThreadPoolExecutor+janus"
  - "CR-12/13/14/15/19/27/37: calibration-gated stubs — flag-only emission, default OFF"
  - "classify_bar → VPContextEngine.process narrative-wiring: no production call site exists today (verified via grep); 15-02 already enabled the signature. Wiring will land when the bar-engine loop does (Phase 16/FSM)"
metrics:
  duration_min: 35
  tasks_completed: 3
  completed_date: "2026-04-14"
---

# Phase 15 Plan 03: ConfluenceRules + Scorer Integration Summary

Stateless `ConfluenceRules.evaluate()` encoding all 38 canonical CR-XX
rules from `RULES.md`, with scorer integration, 3 meta-flag bits, and
`SignalTier.DISQUALIFIED` veto enforcement.

## What Shipped

### Task 1 — ConfluenceAnnotations + Config + meta-flag bits

- **`deep6/engines/confluence_rules.py` (new, ~450 LOC incl. all 38 rule
  functions)** — `ConfluenceAnnotations` dataclass (D-14): `flags: set[str]`,
  `regime: str`, `score_mutations: dict[int, float]` keyed by `Level.uid`
  (C5), `vetoes: set[str]`, `rule_hits: list[tuple[str, str]]` audit trail.
  `evaluate(levels, gex_signal, bar, scorer_result, config=None,
  prior_regime=None) -> ConfluenceAnnotations` — pure, no input mutation.
- **`deep6/engines/signal_config.py` — `ConfluenceRulesConfig`.** Per-rule
  `enable_CR_XX: bool` flags:
  - EASY/MEDIUM default `True` (29 rules)
  - CALIBRATION-GATED default `False` (9 rules: CR-11, CR-12, CR-13, CR-14,
    CR-15, CR-19, CR-22, CR-27, CR-37) — D-16
  - Proximity tunables (D-39): `proximity_tight_ticks=6`,
    `proximity_med_ticks=8`, `proximity_wide_ticks=12`
  - Calibration-gated thresholds surfaced as knobs: `cr_08_shorts_multiplier`,
    `pin_regime_min_strikes`, `regime_change_min_score_delta`,
    `spoof_detection_min_cancel_ratio`, `cr_25_round_number_mult`
- **`deep6/signals/flags.py`** — 3 new bits appended AFTER `TRAP_SHOT`:
  - `PIN_REGIME_ACTIVE = 1 << 45`
  - `REGIME_CHANGE     = 1 << 46`
  - `SPOOF_VETO        = 1 << 47`
  - Module docstring updated to distinguish bits 0-44 (SIGNAL, IMMUTABLE)
    from bits 45+ (META-FLAGS).
  - `SIGNAL_BITS_MASK = (1 << 45) - 1` exported — callers use `flags &
    SIGNAL_BITS_MASK` when counting signals so meta-flags never inflate
    popcount.

### Task 2 — All 38 CR-XX rule implementations

Every row in `RULES.md` is encoded as a dedicated `cr_XX(levels,
gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]` function:

| Tier | Count | CR IDs | Default state |
|------|-------|--------|---------------|
| EASY | 9 | CR-01, CR-02, CR-06, CR-07, CR-08, CR-25, CR-31, CR-32, CR-35 | ON |
| MEDIUM | 20 | CR-03, CR-04, CR-05, CR-09, CR-10, CR-16, CR-17, CR-18, CR-20, CR-21, CR-23, CR-24, CR-26, CR-28, CR-29, CR-30, CR-33, CR-34, CR-36, CR-38 | ON |
| CALIBRATION-GATED | 9 | CR-11, CR-12, CR-13, CR-14, CR-15, CR-19, CR-22, CR-27, CR-37 | OFF |

(`grep -c "^def cr_" deep6/engines/confluence_rules.py` → 38.)

Each rule function cites `{source_file}:{section}` in its docstring for
traceability (threat T-15-01-03). Rule bodies use only `levels`
inputs + `gex_signal` fields + `bar` attributes + `Level.meta` keys + cfg
tunables — no external I/O.

Special cases:
- **CR-22 Hawkes (MS-07)**: D-35 stub — emits `CLUSTER_POISSON_STUB` flag
  only; full MLE deferred.
- **CR-23 Spoof Veto (MS-08)**: reads `Level.meta["cancel_ratio"]`; when
  ≥ `spoof_detection_min_cancel_ratio`, emits `"SPOOF_DETECTED"` into
  `vetoes` AND `"SPOOF_VETO"` flag → scorer forces DISQUALIFIED.
- **CR-04 PIN Regime**: VPOC within `proximity_tight_ticks` of
  LARGEST_GAMMA (or HVL fallback) → `regime="PIN"` +
  `PIN_REGIME_ACTIVE` flag.
- **Regime priority merge**: `PIN(3) > TREND(2) > BALANCE(1) > NEUTRAL(0)`.
  CR-10's generic regime assignment cannot clobber CR-04's specific PIN.

### Task 3 — Scorer integration (D-32)

- `score_bar()` signature gains optional `confluence_annotations=None`
  (default preserves every pre-15-03 caller).
- **Insertion site (content-anchored):** AFTER the GEX regime-modifier
  block's final `gex_direction_conflict = True` branch; BEFORE the
  `# --- Layer 2: Category confluence ---` header. Applies:
  1. `score_mutations` to Level-shaped entries in `active_zones` (keyed
     by `Level.uid`; VolumeZone entries lack `uid` and are skipped —
     by design, since legacy zones aren't addressable by the rule
     engine).
  2. Meta-flag emission into `meta_flags` local → `ScorerResult.meta_flags`.
  3. Veto latching: any veto → `forced_disqualified = True`.
- **`SignalTier.DISQUALIFIED = -1`** added as lowest ordinal. Placed
  below QUIET so existing tier comparisons remain safe. Veto enforcement
  fires BEFORE `gex_direction_conflict` branch and BEFORE the midday
  window block — so vetoes cannot leak into any TYPE_* band and cannot
  be inadvertently downgraded to QUIET.
- **`ScorerResult.meta_flags: int = 0`** — new field, separate from the
  stable 45-bit signal bitmask. Bit 45+ emissions land here.
- **Zone-bonus loop duck-typed**: `_zone_bot / _zone_top / _zone_invalidated`
  helpers accept both `VolumeZone.top_price/bot_price/state=ZoneState.*`
  and `Level.price_top/price_bot/state=LevelState.*`. This resolves the
  latent type mismatch from 15-01 where `LevelBus.get_all_active()`
  returns `list[Level]` but scorer still read `VolumeZone` fields.
- **VPIN ordering preserved**: Phase 12 multiplier chain unchanged
  (`base → category → zone_bonus → IB → VPIN → clip`). Annotation
  processing runs upstream of VPIN at the GEX→Category boundary.

## Commits

| Task | Hash | Message |
|------|------|---------|
| T-15-03-01 + T-15-03-02 | `557db95` | feat(15-03): ConfluenceAnnotations + 38 CR-XX rules + meta-flag bits |
| T-15-03-03 | `4405164` | feat(15-03): integrate ConfluenceAnnotations into scorer (D-32) |

Commits were intentionally merged for Task 1+2 because the config +
contract + rule bodies land atomically in one file with one test file.

## Test Results

| Suite | Count | Status |
|-------|-------|--------|
| `tests/engines/test_confluence_rules.py` | 57 | pass |
| `tests/scoring/test_scorer_with_confluence.py` | 12 | pass |
| `tests/test_signal_flags.py` (bits 0-44 invariant, plus meta-flag asserts) | 7 | pass |
| `tests/test_scorer.py` (regression) | — (bundled, full pass) | pass |
| `tests/test_vp_context_engine.py` + `tests/test_zone_registry.py` + narrative/absorption/exhaustion | — | pass |
| **Targeted regression** (engines + scoring + signals + scorer + narrative + absorption + exhaustion + zone_registry + vp_context + gex) | **254** | **pass** |

Performance budget (D-34): measured median ~0.1-0.2 ms, p95 well under
1 ms, for 82 synthetic Levels over 100 iterations on M2 (logged via
`test_evaluate_budget_1ms_80_levels`). Soft gate in CI is 5 ms.

## Deviations from Plan

### Auto-fixed during execution

1. **[Rule 1 — Bug/Interpretation] Regime merge semantics.** Plan stated
   "last regime_override wins (log collision)". Literal implementation
   meant CR-10's generic `NEUTRAL/BALANCE/TREND` assignment clobbered
   CR-04's `PIN`. Fixed by switching to priority-based merge
   (`PIN > TREND > BALANCE > NEUTRAL`). Tests updated accordingly. No
   plan decision (D-13/D-14) is violated — "last wins" was a strawman
   implementation note, not a design constraint.

2. **[Rule 3 — Blocking] Scorer zone-bonus loop read VolumeZone fields
   but runtime `active_zones` is `list[Level]`.** Plan handoff declared
   "active_zones is list[Level] post-15-01 refactor" but the scorer had
   not been updated — existing tests still pass `VolumeZone` directly,
   masking the bug. Added duck-typed `_zone_bot / _zone_top /
   _zone_invalidated` helpers so both shapes work. Required for Task 3
   acceptance ("score mutations applied to Level in active_zones").

3. **[Rule 1 — Bug] `SignalTier.DISQUALIFIED` missing from enum.**
   Confirmed via pre-finding S2. Added at ordinal `-1`. Verified no
   existing code uses `.value >` comparisons that would regress.
   `tests/test_scorer_with_confluence.py::test_signal_tier_disqualified_exists_and_is_negative`
   pins the invariant.

4. **[Rule 2 — Additional guard] DISQUALIFIED protected from midday-block
   override.** Without the guard, the subsequent midday-window QUIET
   override would demote DISQUALIFIED to QUIET inside the 10:30-13:00 ET
   window — which would silently unblock vetoed signals. Added
   `if tier != SignalTier.DISQUALIFIED` guard.

### Rule-4 architectural decisions — NONE

No architectural deviations.

### Classify_bar → process() narrative_result wiring

Per handoff: "Wire it here in 15-03 — gap flagged from 15-02".

**Finding:** Exhaustive grep (`E6VPContextEngine|vp_context_engine =
|VPContextEngine\(`) confirms `E6VPContextEngine` is instantiated ONLY
in tests today. The real bar-engine production path
(`scripts/backtest_signals.py`, `scripts/sweep_thresholds.py`) calls
`classify_bar` and `profile.get_active_zones(...)` directly — there is
no intermediate `VPContextEngine` call to wire. `VPContextEngine.process`
already accepts the optional `narrative_result` kwarg from 15-02, so
the wiring is ready when the integrated bar loop lands (Phase 16 / FSM
in 15-04 and beyond).

Not a blocker for 15-03; the confluence pipeline (evaluate → scorer) is
self-contained and caller-agnostic. Documented as a remaining handoff
for Wave 4.

### Authentication Gates

None.

## Known Stubs

Documented — all within plan scope (D-35, D-16 calibration-gating):

| Rule | Stub reason |
|------|-------------|
| CR-12, CR-13, CR-14, CR-15, CR-19, CR-27, CR-37 | Calibration-gated flag-only stubs — default OFF, body emits single flag when externally enabled. Full threshold logic lives behind Phase 7 vectorbt sweeps. |
| CR-22 Hawkes | Per D-35: O(1) Poisson baseline stub. Full MLE deferred to ThreadPoolExecutor+janus worker. Flag-only emission. |
| CR-09 basis correction | Structural flag ("GEX_BASIS_CORRECTED") — actual basis-math is upstream in LevelFactory.from_gex. Phase 15 only emits the audit marker. |

These are explicit per-plan decisions, not hidden placeholders.

## Threat Flags

None. No new network endpoints, file I/O, or auth paths. Confluence
rules operate on in-memory Level snapshots with no serialization or
cross-process surface.

## Phase 12 Invariant Verification

`grep -n "1 << 4[0-4]" deep6/signals/flags.py` and
`test_signal_flags_bits_preserved` both confirm bits 0-44 are byte-identical
to pre-commit. `TRAP_SHOT == 1 << 44` verified via `python -c` smoke test.
45 signal bits + 3 meta-flags = 48 flags total (plus `NONE=0`).

## Handoff to Wave 4 (Plan 15-04 — TradeDecisionMachine)

Plan 15-04 consumes:

- `ConfluenceAnnotations` as **an input argument** to the FSM — FSM MUST
  NOT call `confluence_rules.evaluate()` internally (per plan S6). The
  bar-engine loop is responsible for calling `evaluate()` ONCE per bar
  and passing the result to both `score_bar(..., confluence_annotations=)`
  and the FSM transition function.
- `ScorerResult.meta_flags` to inspect regime state without re-evaluating
  rules.
- `ScorerResult.tier == SignalTier.DISQUALIFIED` as a hard gate — FSM
  transitions must refuse to enter TRIGGERED from DISQUALIFIED.
- `ConfluenceAnnotations.flags` strings (`"ABSORB_PUT_WALL"`,
  `"EXHAUST_CALL_WALL_FLAG"`, `"VA_CONFIRMED"`, `"FAILED_IB"`, etc.) as
  transition triggers for higher-tier setups.
- `ConfluenceRulesConfig` enable flags — FSM config can override per-rule
  enablement without touching the rule code. Recommended: flip
  calibration-gated rules via config only, not by rewiring `_RULES`.

Pipeline ordering arranged in 15-03 (documented; wiring lands in 15-04):

```
bar close
  → classify_bar(bar)                            # narrative
  → VPContextEngine.process(bar, narrative_result)  # zones + narrative Levels
  → confluence_rules.evaluate(levels, gex_signal, bar, None)
  → score_bar(..., confluence_annotations=annotations)
  → FSM.transition(state, scorer_result, annotations)   # 15-04 owns this
```

## Self-Check: PASSED

- Created files exist:
  - `deep6/engines/confluence_rules.py` ✓
  - `tests/engines/test_confluence_rules.py` ✓
  - `tests/scoring/test_scorer_with_confluence.py` ✓
- Modified files exist:
  - `deep6/engines/signal_config.py` ✓ (ConfluenceRulesConfig added)
  - `deep6/signals/flags.py` ✓ (PIN_REGIME_ACTIVE / REGIME_CHANGE / SPOOF_VETO + SIGNAL_BITS_MASK)
  - `deep6/scoring/scorer.py` ✓ (confluence_annotations kwarg, DISQUALIFIED tier, meta_flags field, duck-typed zone accessors)
  - `tests/test_signal_flags.py` ✓ (updated counts for 48 flags)
- Commits on main:
  - `557db95` feat(15-03): ConfluenceAnnotations + 38 CR-XX rules + meta-flag bits ✓
  - `4405164` feat(15-03): integrate ConfluenceAnnotations into scorer (D-32) ✓
- Acceptance grep checks:
  - `grep -c "^def cr_" deep6/engines/confluence_rules.py` → 38 ✓
  - `grep -n "PIN_REGIME_ACTIVE\|REGIME_CHANGE\|SPOOF_VETO" deep6/signals/flags.py` → all at bits 45/46/47 ✓
  - `grep -n "confluence_annotations" deep6/scoring/scorer.py` → integration present at post-GEX site ✓
  - `python -c "from deep6.signals.flags import SignalFlags; assert SignalFlags.TRAP_SHOT == 1 << 44"` → OK ✓
- 254 targeted regression tests pass; 57 new confluence tests + 12 new
  scorer-integration tests + 7 signal-flag invariants = 76 new tests.
