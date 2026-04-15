# Phase 18: NT8 Scoring + Backtest Validation — Context

**Gathered:** 2026-04-15
**Status:** Ready for planning
**Source:** `/gsd-discuss-phase 18` — 1 gray area deep-dived (on-chart display); 3 areas left as Claude's Discretion with sensible defaults

<domain>
## Phase Boundary

Port `deep6/scoring/scorer.py` — the two-layer confluence scorer (engine agreement + category agreement, zone bonus, narrative cascade, TypeA/B/C classification) — into NinjaScript. Wire it into `DEEP6Strategy.EvaluateEntry` as the replacement for the hardcoded Tier-3 rules from Phase 16. Render per-bar scoring output on the NT8 chart via a HUD badge + tier-coded markers. Build a parity harness that validates scoring output against the Python reference on ≥5 recorded NQ sessions.

Phase delivers:
- `AddOns/DEEP6/Scoring/ConfluenceScorer.cs` — two-layer scorer with weights/thresholds verbatim from Python
- `AddOns/DEEP6/Scoring/NarrativeCascade.cs` — narrative string assembly ("ABSORBED @VAH + CVD DIVERGENCE") matching Python format
- On-chart HUD badge (top-right of main pane) showing current-bar score + TypeA/B/C tier
- Tier-coded glyph markers at entry price (diamond/triangle/dot with color saturation)
- TypeA-only narrative label next to the marker for high-conviction signals
- `DEEP6Strategy.EvaluateEntry` cut over to scorer output — hardcoded STACKED / VA-EXTREME / WALL-ANCHORED rules removed
- Parity harness extending Phase 17's NDJSON replay loader — emits per-bar `(bar_index, score, tier, narrative)` from both engines, compares
- Per-session parity report committed alongside 5+ recorded sessions

Kronos E10, FastAPI, TradingView MCP, Next.js dashboard remain **out of scope** for v1.

</domain>

<decisions>
## Implementation Decisions

### On-chart scoring display — HUD badge (top-right)
- **Fixed HUD badge at top-right of the main pane.** Single text box rendered in `OnRender` via SharpDX, anchored to top-right corner with configurable padding (default 12px).
- Badge content (3 lines): (1) `Score: +0.87` (signed, 2 decimals), (2) `Tier: A` with color fill, (3) narrative preview truncated to 40 chars (e.g., `ABSORBED @VAH + CVD DIVERGENCE`).
- Updates on each bar close (not on tick — avoids flicker).
- Typography: 12pt monospace via existing Phase 16 SharpDX text format pool; no new font allocation.
- Does NOT overlap footprint cells, GEX levels, or liquidity walls. Badge is explicitly anchored to the chart frame, not to a price.
- Configurable via NT8 Properties: `ShowScoreHud` (bool, default true), `ScoreHudPaddingPx` (int, default 12).

### TypeA/B/C tier encoding — color + glyph
- **Color + glyph combined.** Entry-price markers use distinct shapes per tier AND tier-specific color/saturation:
  - **TypeA** (high conviction): solid diamond, fully saturated green (long) or red (short). Drawn via `Draw.Diamond` with `isOutline: false`.
  - **TypeB** (moderate conviction): hollow triangle pointing in entry direction, medium saturation. `Draw.TriangleUp/Down` with `isOutline: true`.
  - **TypeC** (observational): small solid dot, 50% saturation gray-green / gray-red. `Draw.Dot` at 4px.
- Matches existing Phase 16 signal marker language (triangle/arrow for ABS/EXH) — tier variants extend it naturally.
- Marker placement: at entry price on the bar the signal fired. Label side (above/below bar) follows direction (above for bearish signals at highs, below for bullish at lows).

### Narrative text rendering — TypeA only, compact on-chart
- **Only TypeA bars get on-chart narrative text.** TypeB/C show the score + tier in the HUD only (narrative still available in strategy log).
- TypeA narrative rendered as a single-line compact label adjacent to the marker. Max 50 chars; truncated with ellipsis if longer.
- Format: the Python `detail` field from the dominant signal plus up to 2 supporting signal labels (e.g., `ABSORBED @VAH + CVD DIV + OVERSIZED IMB`).
- Rendered via `Draw.Text` with small font (9pt), low-opacity background box for legibility.

### Scoring formula fidelity — verbatim port (Claude's Discretion default)
- Port weights and thresholds **verbatim** from Python `scoring/scorer.py`. Do not expose as NT8 Properties in Phase 18.
- Future tuning (e.g., vectorbt parameter sweeps) happens in Phase 19+ or a later ML phase — out of scope here.
- Zone bonus is folded into the raw score (not a separate display field). Narrative cascade is assembled separately but driven off the same signal set.

### Parity bar — bit-for-bit on scores (Claude's Discretion default)
- Fixture-level parity: bit-for-bit score match (4 decimals) vs Python reference on all hand-crafted fixtures.
- Session-replay parity: `|python_score - csharp_score| <= 0.05` per bar on ≥5 recorded NQ sessions, AND identical TypeA/B/C verdict per bar. Tighter than Phase 17's ±2 signals/session because scoring is deterministic given signals — any divergence traces to a scoring-formula bug.
- If divergence exceeds the 0.05 envelope on any bar, root-cause via per-layer diff (engine-agreement delta vs category-agreement delta vs zone bonus delta vs narrative mismatch) and fix before parity is declared passing.

### Replay harness — extend Phase 17 infrastructure (Claude's Discretion default)
- Reuse Phase 17's `CaptureHarness` (NDJSON writer) and `CaptureReplayLoader`. Extend the loader to emit `(bar_index, signals[], score, tier, narrative)` tuples per bar.
- Add a `ScoringParityHarness` test class that runs the same NDJSON through `ConfluenceScorer` (C#) and `deep6/scoring/scorer.py` (via subprocess call from the test) and diffs outputs.
- Recorded sessions live in `ninjatrader/captures/` — reuse whatever Phase 17 committed; add more if 5 aren't available.

### DEEP6Strategy confluence migration — cut hardcoded rules (Claude's Discretion default)
- Remove `EvaluateEntry`'s hardcoded STACKED / VA-EXTREME / WALL-ANCHORED Tier-3 rules from Phase 16.
- Replace with scorer-driven gate: entry fires when `score >= ScoreEntryThreshold` (NT8 property, default = Python's `entry_threshold`) AND tier == TypeA (configurable via `MinTierForEntry`).
- Keep risk gates (AccountWhitelist, news blackout, daily loss cap, RTH window, max trades/session) untouched and still evaluated BEFORE scorer output is consumed.
- Strategy log output extended: on every scored bar, Print `[DEEP6 Scorer] bar={N} score={S:+F2} tier={T} narrative={NARR}` regardless of whether an entry fires — per SC5.

### Python reference bug policy
- Carry forward from Phase 17: if port reveals a bug in `deep6/scoring/scorer.py`, fix Python first (keeps it honest as source-of-truth), re-run Python tests, then mirror into C#, document in SUMMARY.md.

### Claude's Discretion
- Exact SharpDX render order for HUD badge vs GEX lines vs footprint cells (planner to verify z-order)
- Narrative label opacity / background-box color (planner to pick readable default)
- `ScoreEntryThreshold` default value — use Python's `entry_threshold` constant verbatim, expose as NT8 property for future tuning
- Whether the HUD badge shows the previous bar's score or the forming bar's partial score (planner to default: previous bar only, to avoid flicker)
- File-by-file test fixture coverage — target at least 3 fixtures per scoring scenario (all-TypeA, mixed, suppressed-by-category-disagreement)
- Scorer subprocess test harness: use `Python.exe`/`python3` path from env, or commit a Python replay entry-point script

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Python scoring source-of-truth
- `deep6/scoring/scorer.py` — two-layer confluence scorer, zone bonus, TypeA/B/C classification (PRIMARY port target)
- `deep6/scoring/narrative.py` (if exists) — narrative cascade assembly
- `deep6/engines/signal_config.py` — scorer thresholds (entry_threshold, tier_thresholds, category_weights)
- `tests/test_scorer.py` (or equivalent) — reference behavior fixtures for port validation

### Phase 17 baseline (extend, don't rebuild)
- `ninjatrader/Custom/AddOns/DEEP6/Registry/DetectorRegistry.cs` — EvaluateBar returns SignalResult[]
- `ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs` — shared state
- `ninjatrader/Custom/AddOns/DEEP6/Registry/SignalResult.cs` — signal shape consumed by scorer
- `ninjatrader/tests/CaptureHarness/` (and replay loader) — extend for scoring parity
- `ninjatrader/tests/ninjatrader.tests.csproj` — add scoring tests here

### Phase 16 baseline (touch carefully)
- `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` — SharpDX render pipeline; HUD badge plugs into `OnRender`
- `ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs` — `EvaluateEntry` is the migration target; risk gates above it must not be touched

### Planning context
- `.planning/PROJECT.md` — NT8-primary framing
- `.planning/ROADMAP.md` Phase 18 entry — 5 success criteria
- `.planning/REQUIREMENTS.md` — scoring/confluence requirements (reclassified under "NT8 substitutes" for v1 NT8)
- `.planning/phases/17-nt8-detector-refactor-remaining-signals-port/17-CONTEXT.md` — inherited decisions (parity-bar pattern, bug policy, NUnit net8.0)

</canonical_refs>

<specifics>
## Specific Ideas

- Existing NT8 strategy risk gates must remain above the scorer call in OnBarUpdate — scorer output is consumed only after gates pass
- Keep `AbsorptionSignal` / `ExhaustionSignal` legacy types as compatibility wrappers until scorer is live end-to-end; remove once `EvaluateEntry` no longer references them
- Python-side scorer harness: call via `python3 -m deep6.scoring.replay_scorer` with NDJSON on stdin, JSON lines on stdout — keeps the test subprocess boundary clean
- Tier thresholds (TypeA = score ≥ 0.70, TypeB = 0.50–0.69, TypeC = 0.30–0.49 if Python matches these) — planner to verify by reading scorer.py constants, not by guessing

</specifics>

<deferred>
## Deferred Ideas

- User-tunable scoring weights via NT8 Properties — Phase 19 or later (vectorbt/ML optimization phase)
- Separate indicator pane with score as line chart — could be added later if HUD badge proves insufficient; not in Phase 18
- Per-bar score history visualization — out of scope; can be seen in strategy log
- Hover-to-show narrative on TypeB/C bars — deferred; not worth the interaction complexity in Phase 18
- Kronos E10 bias influence on scoring — out of scope v1
- Real-time parity dashboard / Next.js live view — out of scope v1
- Databento historical MBO vs Phase 17 NDJSON as parity dataset — Phase 19+ if paper-trading gate reveals a gap

</deferred>

---

*Phase: 18-nt8-scoring-backtest-validation*
*Context gathered: 2026-04-15 via /gsd-discuss-phase*
