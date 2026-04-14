# Phase 15: LevelBus + Confluence Rules + Trade Decision FSM — Context

**Gathered:** 2026-04-14
**Status:** Ready for planning
**Source:** Derived from research deliverables in `.planning/research/pine/` (6 documents, ~12,500 words, 47 rules, 35 papers cited). Open questions answered with Claude's Discretion defaults where research didn't force a decision — all are revisitable during planning.

<domain>
## Phase Boundary

Unify DEEP6's three currently-fragmented level lineages into a single `LevelBus` and wire them into a deterministic trade-decision state machine. Three concurrent workstreams:

1. **LevelBus** — normalize `VolumeZone` (LVN/HVN), narrative signals (absorption/exhaustion/momentum/rejection), VA extremes (VPOC/VAH/VAL), and GEX levels (call_wall/put_wall/gamma_flip/zero_gamma/hvl/largest_gamma) into a single `Level` dataclass with unified scoring (type + volume + touches + recency + VA-boost + confirmation-boost) and lifecycle FSM (ACTIVE → DEFENDED → BROKEN → FLIPPED → INVALIDATED).

2. **ConfluenceRules** — stateless evaluator module that applies ~47 cross-stream rules from the research and mutates `Level.score` + emits `ConfluenceAnnotations` (flags + regime). Rules come from four streams: 8 VP/GEX (DEEP6_INTEGRATION.md), 12 vendor/academic (industry.md), 12 microstructure (microstructure.md), 15 auction-theory (auction_theory.md). Deduplication + prioritization happens in this phase's plan-01.

3. **TradeDecisionMachine** — 7-state FSM (IDLE → WATCHING → ARMED → TRIGGERED → IN_POSITION → MANAGING → EXITING) with 17 entry triggers + stop/target/invalidation/sizing policies. **Replaces** the current `deep6/execution/engine.py:24-206` bar-close-only flow, which bypasses the confirmation-bar pattern every prop-desk framework uses. Consumes `LevelBus + ScorerResult + ConfluenceAnnotations`, emits orders via async-rithmic.

This is an **integration + architecture** phase, not greenfield signal research. All 47 rules already exist as text in research artifacts; the work is encoding them deterministically, threading them through the execution surface, and calibrating weights on Databento MBO (via Phase 13 backtest harness).

**Non-goals:** retraining LightGBM weights (Phase 9 territory); adding new signal engines (44-bit SignalFlags stays at bits 0-43 + TRAP_SHOT bit 44 from Phase 12 — no new bits); visual heatmap rendering (Pine-specific display, not portable); intrabar OHLCV sampling (DEEP6 has real MBO from Databento — Pine's workaround is unnecessary).
</domain>

<decisions>
## Implementation Decisions

### LevelBus Data Structure

- **D-01** `Level` dataclass at `deep6/engines/level.py` with `slots=True`. Fields: `price_top, price_bot, kind (LevelKind enum), origin_ts, origin_bar, last_act_bar, score (0-100), confidence (score/100 cache), touches, direction (+1/-1/0), inverted (bool), state (LevelState enum), meta (dict)`. Point levels (GEX) set `price_top == price_bot`; zones use full range. Single query `bot <= price <= top` works for both.
- **D-02** `LevelKind` enum covers 17 variants: LVN, HVN, VPOC, VAH, VAL, ABSORB, EXHAUST, MOMENTUM, REJECTION, FLIPPED, CONFIRMED_ABSORB, CALL_WALL, PUT_WALL, GAMMA_FLIP, ZERO_GAMMA (alias), HVL, LARGEST_GAMMA.
- **D-03** `LevelState` enum: ACTIVE, DEFENDED, BROKEN, FLIPPED, INVALIDATED. Matches existing `deep6/engines/volume_profile.py` `ZoneState` FSM exactly (don't fork semantics).
- **D-04** `origin_ts` (Unix wall time) alongside `origin_bar` (index) — bar indices reset at session boundaries in backtest; timestamp survives reset for cross-session persistence and logging.
- **D-05** `meta` is a sparse dict, not a typed subclass. Known keys (non-exhaustive): `vol_ratio`, `wick_pct`, `delta_ratio`, `absorb_type`, `gex_net`, `confirmation_window_ends_bar`, `confirmed`, `confluence`, `va_confirmed`, `acceleration_candidate`.
- **D-06** **Narrative zone persistence threshold: strength ≥ 0.4** (Claude's Discretion — research did not lock this). Lower thresholds flood the registry on volatile NQ sessions. Tune in Phase 7 vectorbt sweep (extend `ConfluenceRulesConfig`).
- **D-07** **ABSORB zone geometry: full wick, not body.** `z_top = bar.high, z_bot = body_top` for UW absorption; `z_top = body_bot, z_bot = bar.low` for LW. Minimum width = 1 tick (`syminfo.mintick` equivalent).
- **D-08** **Cross-session zone persistence: carry over with decay**, mirroring VPRO-07 pattern. Zones with score ≥ 60 at session close persist into next session with recency decay applied. Zones below threshold are GC'd at session reset. (Claude's Discretion — revisit after Phase 13 replay data.)

### LevelBus Upgrade Path

- **D-09** **In-place rename + extend `ZoneRegistry` → `LevelBus`** at `deep6/engines/zone_registry.py`. No adapter class. Existing `VolumeZone` methods kept as thin wrappers over `Level` for one release window, then removed. Justified by: (a) Phase 12 EventStore serialization uses row schemas, not pickled VolumeZone objects — no on-disk format break; (b) VolumeZone is only consumed in 3 call sites (`scorer.py`, `vp_context_engine.py`, `narrative.py`), all refactored in this phase.
- **D-10** `LevelBus.add_level(level)` subsumes `add_zone()` for all 17 kinds. GEX dict entries become point-Levels stored in the same `List[Level]`. Query API: `query_near(price, ticks) -> List[Level]`, `query_by_kind(kind) -> List[Level]`, `get_top_n(n=6) -> List[Level]` (Pine's `max_visible` filter).
- **D-11** Merge-or-create extends to narrative zones. Overlap + same direction + same kind → widen + boost score + touches++. Evict weakest on `max_levels=80` cap (keep existing eviction code).

### LevelFactory

- **D-12** **New file `deep6/engines/level_factory.py`** — pure conversion layer. Functions: `from_narrative(result) -> List[Level]`, `from_volume_zone(zone) -> Level`, `from_absorption(signal) -> Level`, `from_exhaustion(signal) -> Level`, `from_gex(GexLevels) -> List[Level]`. No state. Callable from any engine.

### Confluence Rules Module

- **D-13** **New file `deep6/engines/confluence_rules.py`** — stateless `evaluate(levels, gex_signal, bar, scorer_result) -> ConfluenceAnnotations`. Idempotent; no external state needed.
- **D-14** `ConfluenceAnnotations` dataclass: `flags: set[str]` (e.g., `{"PIN_REGIME", "ACCELERATION", "REGIME_CHANGE"}`), `regime: str` (e.g., `"PIN" | "TREND" | "BALANCE" | "NEUTRAL"`), `score_mutations: dict[level_id, float]` (applied back to LevelBus), `vetoes: set[str]` (e.g., `{"SPOOF_DETECTED"}` from MS-08 suppresses downstream trade trigger).
- **D-15** **Deduplication pass**: the 47 rules across 4 research streams have overlaps (e.g., "absorption at value-area extreme" appears in DEEP6_INTEGRATION.md rule 6 and auction_theory.md). Plan-01 produces a deduplicated canonical rule table (`.planning/phases/15-levelbus-confluence-rules-trade-decision-fsm/RULES.md`) before any code. Each rule: rule_id (CR-01…CR-NN), trigger, action, source citation, implementability tier (EASY / MEDIUM / CALIBRATION-GATED).
- **D-16** **Calibration-gated rules** (those with research-stated thresholds that the authors flagged LOW-confidence) are implemented with config-driven thresholds and default to OFF until a Phase 7 sweep validates them. Examples: Rule 8 (Baltussen last-30-min), Rule MS-06 (VPIN regime threshold).

### TradeDecisionMachine

- **D-17** **New file `deep6/execution/trade_decision_machine.py`** — 7-state FSM. States: IDLE, WATCHING, ARMED, TRIGGERED, IN_POSITION, MANAGING, EXITING. Transition table T1-T11 per `trade_logic.md` §2.
- **D-18** **Supersedes `deep6/execution/engine.py:24-206`** (not deletes — keep as thin compatibility wrapper that delegates to `TradeDecisionMachine` for one release window). Preserves D-16/D-17 GEX gates from existing `risk_manager.py`.
- **D-19** Interface: `TradeDecisionMachine.on_bar(bar, level_bus, scorer_result, confluence_annotations)`, `.on_fill(fill)`, `.on_reject(reject)`. State persisted to Phase 9 EventStore on every transition (reuses existing schema).
- **D-20** **Confirmation-bar timing**: entry triggers that require confirmation fire on the NEXT bar's close, not same-bar. Current `engine.py` fires same-bar on close — this phase adds the one-bar delay. (Claude's Discretion — research consensus but not empirically validated on NQ.)
- **D-21** Entry trigger taxonomy (4 types): `IMMEDIATE_MARKET`, `CONFIRMATION_BAR_MARKET`, `STOP_AFTER_CONFIRMATION`, `LIMIT_AT_LEVEL`. 17 triggers from `trade_logic.md` §3 mapped to exactly one type each.
- **D-22** **Precedence for simultaneous triggers**: confluence score wins; tie broken by `(ABSORB > EXHAUST > MOMENTUM > REJECTION)` priority. Matches existing narrative cascade.

### Stop / Target / Invalidation / Sizing

- **D-23** **Stop policy**: structural anchor (beyond zone boundary) + 2-tick buffer + max(2.0 × ATR(14), structural). Caps at 1.5% of account per trade (existing risk gate preserved).
- **D-24** **Target policy**: primary = opposing zone (VAH/VAL/next LVN/next GEX wall); R-floor = 1.5R; runner = trail by OF-exhaustion signal (exit remaining on opposing ABSORB/EXHAUST).
- **D-25** **Invalidation rules I1-I9** from `trade_logic.md` §6 ported verbatim. Includes I9 (MFE give-back exit: exit if max favorable excursion erodes by ≥50%).
- **D-26** **Position sizing formula**: `size = floor(risk_budget / stop_distance × conviction_mult × regime_mult × recency_mult × kelly_fraction)`. Kelly fraction = 0.25 (quarter-Kelly) — Claude's Discretion, conservative default, calibratable.
- **D-27** **Pin-regime queueing**: when `regime == "PIN"` (Rule 4), FSM refuses WATCHING→ARMED transitions. Directional signals with score < 70 suppressed. Limit orders at the pinned strike get cancelled if unfilled within 3 bars.

### GEX Engine Extensions

- **D-28** Add `largest_gamma_strike: float = 0.0` to `GexLevels` at `deep6/engines/gex.py:36`. Distinct from `hvl` (peak |net GEX|) — this is peak raw call γ×OI before put netting. Consumed by Rule 4 (Pin Regime).
- **D-29** Add `zero_gamma` as alias property pointing to `gamma_flip`. Naming clarity only, no new computation.
- **D-30** **HIRO/DIX: deferred.** Research indicates FlashAlpha may expose HIRO but schema unverified. If present, adding `LevelKind.HIRO` is additive and non-breaking. Skip until FlashAlpha response is inspected live.

### Integration Points

- **D-31** Orchestration insertion at `deep6/engines/vp_context_engine.py:78-112`. `E6VPContextEngine.process()` gets a new step after zone detection: `LevelFactory.from_narrative(result) → level_bus.add_level(...)` for any ABSORB/EXHAUST/MOMENTUM/REJECTION with `strength >= 0.4` (D-06).
- **D-32** Scorer extension at `deep6/scoring/scorer.py:276-298`. GEX-modifier block expands to consume `ConfluenceAnnotations` — flags become additional category votes, `score_mutations` apply directly to `Level.score` before tier classification, `vetoes` force tier → DISQUALIFIED.
- **D-33** SignalFlags: allocate 3 new meta-flag bits (NOT signal bits): `PIN_REGIME_ACTIVE`, `REGIME_CHANGE`, `SPOOF_VETO`. Place at `signals/flags.py` end of enum; does not reorder bits 0-44 (Phase 12 constraint preserved).

### Budget + Performance

- **D-34** ConfluenceRules.evaluate() budget: < 1ms for 80 active levels on bar close. Synchronous in `bar_engine_loop`. No new asyncio task.
- **D-35** Hawkes MLE rules (MS-09 from microstructure.md) — the only rule type needing offload — run via existing `ThreadPoolExecutor` + `janus` queue pattern. Other 46 rules are O(n) per bar where n=|levels|<=80.

### Testing

- **D-36** Test fixtures: recorded NQ sessions from Databento (use Phase 13's replay harness when it lands). At least 5 sessions covering each day-type (Normal, Trend, Double Distribution, Neutral, Non-Trend).
- **D-37** Golden-file tests for each of CR-01…CR-NN rules: given `(LevelBus state, GexSignal, bar)` → expected `ConfluenceAnnotations`.
- **D-38** FSM tests: every transition T1-T11 reachable from synthetic fixtures. No hand-traced paths.

### Claude's Discretion

- **D-39** **Threshold values** for proximity (`8 ticks`, `12 ticks`, `6 ticks` etc. in confluence rules) ported verbatim from research defaults. Real calibration happens in Phase 7 sweep after this phase lands.
- **D-40** **Rule CR-08 (HVN + Put Wall → suppress shorts)**: apply `0.6×` multiplier rather than hard-suppress. Research split; soft suppression is reversible by scorer override.
- **D-41** **I9 MFE give-back threshold**: 50% default. Tunable; revisit after 30-day paper trading validation (existing Phase 8 gate).
- **D-42** **Kronos E10 interaction**: E10 directional-bias score enters FSM as a transition guard on WATCHING→ARMED. If `E10_confidence > 60 and E10_direction == signal_direction`, boost conviction_mult by 1.15×. If opposite direction with `E10_confidence > 75`, block transition. Not required for Phase 15 MVP — gated behind a `enable_e10_gating` config flag defaulting to False for first release.
</decisions>

<canonical_refs>
## Canonical References

**Downstream planning and execution agents MUST read these before producing plans or code.**

### Research artifacts (primary source — read in full)
- `.planning/research/pine/DEEP6_INTEGRATION.md` — Level bus contract + 8 VP/GEX confluence rules + Pine port priority (primary blueprint)
- `.planning/research/pine/deep/trade_logic.md` — 7-state FSM + 17 entry triggers + stop/target/invalidation/sizing policies (primary execution spec)
- `.planning/research/pine/deep/auction_theory.md` — Day-type / open-type / VA-relationship classifications + 15 trade-plan generators (primary for regime detection)
- `.planning/research/pine/deep/microstructure.md` — 12 MS rules + detection algorithm complexity analysis (primary for veto rules)
- `.planning/research/pine/deep/practitioners.md` — 15-pattern library + Axia "Three Clues" + Jigsaw "Three Components" (primary for entry-trigger encoding)
- `.planning/research/pine/industry.md` — Vendor methodologies + 12 vendor/academic confluence rules + citation table (primary for academic grounding)
- `.planning/research/pine/oss.md` — OSS landscape; `py-market-profile` borrowing approved for VAH/VAL/POC utilities
- `.planning/research/pine/VP_LVN.pine` — reference Pine source for LVN local-minima detection (porting target for D-14 in research — `scipy.signal.find_peaks`)
- `.planning/research/pine/BOOKMAP_LIQUIDITY_MAPPER.pine` — reference Pine source (condensed architecture; full scoring cascade)

### Code surfaces being extended / replaced
- `deep6/engines/zone_registry.py` — upgrade target (ZoneRegistry → LevelBus)
- `deep6/engines/volume_profile.py` — ZoneState FSM + SessionProfile (reuse semantics, integrate into Level)
- `deep6/engines/narrative.py` — classify_bar cascade (unchanged signal logic; new zone-persistence hook)
- `deep6/engines/absorption.py` — AbsorptionSignal (unchanged; LevelFactory converts to Level)
- `deep6/engines/exhaustion.py` — ExhaustionSignal (unchanged; LevelFactory converts)
- `deep6/engines/gex.py` — GexLevels (add `largest_gamma_strike`, `zero_gamma` alias per D-28/D-29)
- `deep6/engines/vp_context_engine.py:78-112` — process() insertion point (D-31)
- `deep6/engines/poc.py` — VAH/VAL computation (used as Level sources)
- `deep6/scoring/scorer.py:276-298` — extension point for ConfluenceAnnotations (D-32)
- `deep6/execution/engine.py:24-206` — supersession target (D-18)
- `deep6/execution/position_manager.py` — MANAGING state logic extension
- `deep6/execution/risk_manager.py` — preserves D-16/D-17 gates
- `deep6/signals/flags.py` — new meta-flag bits (D-33)

### Prior art (prior phases to respect)
- Phase 12 STATE.md decisions: SignalFlags bits 0-44 STABLE; VPIN modulates FUSED score only (not confluence rules); SetupTracker dual-TF transitions persisted to EventStore (reuse pattern for FSM)
- Phase 9 EventStore schema — reuse `signal_events` + `trade_events` + add `fsm_transitions` table (D-19)
- Phase 13 (Backtest Engine Core) — prerequisite for test fixtures (D-36). If 13 not complete when 15 executes, plan-04 uses synthetic fixtures until 13 lands.

### Project constraints (always)
- `CLAUDE.md` — stack, performance budgets, what not to use
- `.planning/PROJECT.md` — goals, recent decisions table
- `.planning/REQUIREMENTS.md` — existing requirement IDs (ABS-*, EXH-*, ZONE-*, GEX-*, EXEC-*)
- `.planning/STATE.md` — current project state, prior-phase decisions
</canonical_refs>

<specifics>
## Specific Ideas

### Concrete rule counts (for planner sizing)

- **CR-01 through CR-08** — from DEEP6_INTEGRATION.md §Confluence Rules (VP↔GEX proximity rules)
- **CR-09 through CR-20** — from industry.md §Actionable (vendor/academic derived)
- **CR-21 through CR-32** — from microstructure.md §MS-01-MS-12 (microstructure veto + score rules)
- **CR-33 through CR-47** — from auction_theory.md §Actionable (15 day/open-type trade-plan generators)

After dedup (D-15), expect ~35-40 canonical CR-IDs. Plan-01 produces `RULES.md` with the deduplicated table.

### Entry trigger counts

- **ET-01 through ET-17** from trade_logic.md §3. Each maps to exactly one of 4 trigger types (D-21).

### Files being created (inventory for planner)

- `deep6/engines/level.py` (new — Level dataclass, LevelKind, LevelState)
- `deep6/engines/level_factory.py` (new — conversion functions)
- `deep6/engines/confluence_rules.py` (new — stateless evaluator + ConfluenceAnnotations)
- `deep6/execution/trade_decision_machine.py` (new — 7-state FSM)
- `deep6/execution/trade_state.py` (new — state enums, transition table, guards)
- `.planning/phases/15-levelbus-confluence-rules-trade-decision-fsm/RULES.md` (new — deduplicated rule table, versioned artifact)

### Files being modified (inventory)

- `deep6/engines/zone_registry.py` (upgrade to LevelBus — D-09/D-10/D-11)
- `deep6/engines/gex.py` (add largest_gamma_strike, zero_gamma alias)
- `deep6/engines/vp_context_engine.py` (insertion at L78-112)
- `deep6/scoring/scorer.py` (extension at L276-298)
- `deep6/execution/engine.py` (thin delegate to TradeDecisionMachine)
- `deep6/signals/flags.py` (3 new meta-flag bits, non-reordering)

### Wave structure (proposed — planner confirms)

- **Wave 1 (parallel)**: Plan-01 (deduplicated RULES.md) + Plan-02 (LevelBus refactor + LevelFactory)
- **Wave 2**: Plan-03 (ConfluenceRules module + scorer integration, depends on Plan-01 RULES.md + Plan-02 LevelBus)
- **Wave 3**: Plan-04 (TradeDecisionMachine FSM + execution integration, depends on Plan-03 annotations)
- **Wave 4**: Plan-05 (comprehensive test suite — fixtures, golden files, FSM reachability)

5 plans. Research calibration sweep deferred to Phase 7 extension (not a plan here).
</specifics>

<deferred>
## Deferred Ideas

- **HIRO / DIX integration** — FlashAlpha response schema unverified (D-30). Add `LevelKind.HIRO` once confirmed; additive, non-breaking.
- **Pine heatmap rendering** — visualization only, Python pipeline differs (Lightweight Charts custom series handles this in Phase 11). No port.
- **Intrabar OHLCV sampling** — Pine-specific workaround for no DOM access; DEEP6 has real MBO. Skip.
- **Iceberg detection tightening** — MS-02/MS-03 from microstructure.md have research-backed algorithms but Bookmap/Axia/Jigsaw practitioner disagreement on reliability. Implement MS-02 (basic detection) this phase; defer MS-03 (tightened thresholds) to post-calibration.
- **Full Hawkes MLE self-exciting trade clustering (MS-12)** — valuable but higher compute cost (`janus` + `ThreadPoolExecutor`). Implement stubs with O(1) Poisson baseline; upgrade to full MLE in a later phase if live evidence warrants.
- **Confluence rule weight calibration** — Rules 1-8 use boost values from Pine defaults. Calibration sweep is Phase 7 vectorbt extension, not this phase.
- **Cross-asset confluence** (ES↔NQ, SPY↔QQQ) — research only covered single-instrument. Defer.
- **0DTE gamma effects modeling** — research noted 0DTE moves gamma intraday but SpotGamma's volume-reweight is proprietary. Defer.
- **Kronos E10 tight integration into FSM** (D-42) — gated behind config flag defaulting to False; real integration is a follow-up phase after Phase 6 Kronos MCP work completes.
- **Auto-reactive rule tuning** — LightGBM-learned rule weights. Phase 9 territory, not here.

---

*Phase: 15-levelbus-confluence-rules-trade-decision-fsm*
*Context gathered: 2026-04-14 from research synthesis. Open questions from DEEP6_INTEGRATION.md §Open Questions (7) and trade_logic.md §9 (10) resolved as Claude's Discretion defaults (D-06, D-07, D-08, D-20, D-22, D-26, D-27, D-40, D-41, D-42) — all revisitable in planning.*
</deferred>
