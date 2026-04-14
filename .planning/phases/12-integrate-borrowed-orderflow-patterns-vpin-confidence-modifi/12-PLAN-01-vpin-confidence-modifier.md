---
phase: 12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - deep6/orderflow/__init__.py
  - deep6/orderflow/vpin.py
  - deep6/scoring/scorer.py
  - deep6/state/shared.py
  - tests/orderflow/__init__.py
  - tests/orderflow/test_vpin.py
  - tests/scoring/test_scorer_with_vpin.py
autonomous: true
requirements: [OFP-01, OFP-07]

must_haves:
  truths:
    - "VPIN engine produces a continuous confidence multiplier in [0.2, 1.2] at every bar close"
    - "The multiplier is applied to FUSED LightGBM confidence only (not per-signal, not stacked with IB multiplier)"
    - "During warmup (<10 completed buckets) multiplier is neutral 1.0"
    - "Aggressor classification uses DEEP6 exact ask_vol/bid_vol (NOT BVC normal-CDF)"
    - "Final scorer score is clipped to [0, 100] after VPIN application"
  artifacts:
    - path: "deep6/orderflow/vpin.py"
      provides: "VPINEngine class with update_from_bar(bar) and get_confidence_modifier()"
      min_lines: 120
    - path: "tests/orderflow/test_vpin.py"
      provides: "Unit tests for warmup, bucket completion, percentile, modifier bounds"
    - path: "deep6/scoring/scorer.py"
      provides: "VPIN multiplier applied as FINAL stage after IB, with clip"
      contains: "vpin_engine.get_confidence_modifier"
  key_links:
    - from: "deep6/state/shared.py on_bar_close"
      to: "deep6/orderflow/vpin.py VPINEngine.update_from_bar"
      via: "direct call inside on_bar_close before scorer runs"
      pattern: "vpin\\.update_from_bar"
    - from: "deep6/scoring/scorer.py"
      to: "VPINEngine.get_confidence_modifier"
      via: "final-stage multiplier on fused score"
      pattern: "get_confidence_modifier"
---

<objective>
Add VPIN (Volume-Synchronized Probability of Informed Trading) as a continuous 0.2x-1.2x confidence modifier on the final fused LightGBM score. Flow-toxicity percentile high (>0.9) compresses sizing; low (<0.3) expands it. Orthogonal to the 44-signal vote — does not change direction, does not modify per-signal scores, does not stack with IB multiplier on per-signal values.

Purpose: Provide a flow-toxicity gate that adapts position sizing per-bar to current microstructure quality. Reference: Easley, Lopez de Prado, O'Hara (2011) "The Volume Clock".
Output: New `deep6/orderflow/vpin.py` module, integration in scorer, tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-CONTEXT.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-RESEARCH.md

# Reference implementation (read sections, do not copy BVC path)
@/Users/teaceo/Downloads/kronos-tv-autotrader/python/vpin.py
@/Users/teaceo/Downloads/kronos-tv-autotrader/python/orderflow_tv.py

# DEEP6 integration surfaces
@deep6/state/footprint.py
@deep6/state/shared.py
@deep6/scoring/scorer.py

<interfaces>
From deep6/state/footprint.py:
```python
@dataclass
class FootprintBar:
    levels: dict[int, Level]          # tick -> Level(bid_vol, ask_vol)
    total_vol: int
    close: float
    bar_delta: int                    # sum(ask_vol) - sum(bid_vol)
    # ask_vol = aggressor=BUY, bid_vol = aggressor=SELL (DATA-02 verified)
```

From deep6/state/shared.py:
```python
class SharedState:
    def on_bar_close(self, bar: FootprintBar, tf: str) -> ScorerResult: ...
```

From deep6/scoring/scorer.py:
```python
# Current multiplier order: base -> category -> zone -> IB
# VPIN inserts AFTER IB, BEFORE final clip. Clip to [0, 100].
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>T-12-01-01: Scaffold tests/orderflow and write failing VPINEngine tests</name>
  <files>tests/orderflow/__init__.py, tests/orderflow/test_vpin.py, tests/conftest.py (augment with vpin_warmup_data fixture)</files>
  <behavior>
    - test_warmup_returns_neutral: <10 buckets completed → get_confidence_modifier() == 1.0
    - test_exact_aggressor_split: update_from_bar with synthetic bar (ask_vol=800, bid_vol=200) → bucket buy=800 sell=200 (no BVC/erf)
    - test_bucket_completion_at_1000: total accumulated volume 1000 → bucket closes, buckets_completed += 1
    - test_percentile_grows_with_imbalance: sequence of highly imbalanced bars → VPIN percentile rises above 0.8
    - test_confidence_modifier_bounded: modifier always in [0.2, 1.2] across 200 synthetic bars
    - test_no_bvc_path: module must not import math.erf for aggressor split (assert via inspect.getsource)
  </behavior>
  <action>Create tests/orderflow/__init__.py empty. Write tests/orderflow/test_vpin.py with the six tests above using only synthetic FootprintBar fixtures (build minimal bars with levels dict). Add vpin_warmup_data fixture in tests/conftest.py producing 60 balanced bars then 20 imbalanced. DO NOT implement VPINEngine yet — tests must fail on ImportError.</action>
  <verify>
    <automated>pytest tests/orderflow/test_vpin.py -x -q 2>&1 | grep -E "(ImportError|ModuleNotFoundError|6 failed)"</automated>
  </verify>
  <done>Test file exists, 6 tests defined, all fail with ImportError (VPINEngine not yet created).</done>
</task>

<task type="auto" tdd="true">
  <name>T-12-01-02: Implement VPINEngine (exact aggressor, fixed 1000-contract bucket, 50-bucket window)</name>
  <files>deep6/orderflow/__init__.py, deep6/orderflow/vpin.py</files>
  <behavior>
    - Class VPINEngine(bucket_volume=1000, num_buckets=50, history_size=2000, warmup_buckets=10)
    - update_from_bar(bar: FootprintBar) -> None — splits bar.total_vol across buckets filling by exact aggressor (sum ask_vol = buy, sum bid_vol = sell); overflow spills to next bucket
    - get_vpin() -> float in [0,1]: mean of |buy-sell|/bucket_volume over last num_buckets completed buckets
    - get_percentile() -> float in [0,1]: percentile rank of current VPIN within history deque
    - get_confidence_modifier() -> float in [0.2, 1.2]:
        * If buckets_completed < warmup_buckets: return 1.0
        * Linear map: percentile 0.0 → 1.2, percentile 0.5 → 1.0, percentile 1.0 → 0.2
    - get_flow_regime() -> str: CLEAN (<0.3) / NORMAL (0.3-0.7) / ELEVATED (0.7-0.9) / TOXIC (>0.9) by percentile
    - No math.erf, no BVC normal-CDF anywhere in this module
    - Thread-safe: single-threaded call from on_bar_close; no locks needed
  </behavior>
  <action>
    Create deep6/orderflow/__init__.py with `from .vpin import VPINEngine`.
    Create deep6/orderflow/vpin.py (~150 lines) with:
    - Private _bucket_buy_accum, _bucket_sell_accum, _bucket_vol_accum
    - _fill_bucket(buy_vol, sell_vol): appends to accumulators, checks if >= bucket_volume, rolls excess to next bucket
    - _complete_bucket(): appends buy/sell pair to completed_buckets deque(maxlen=num_buckets), computes VPIN, appends to history deque(maxlen=history_size)
    - update_from_bar: iterate level aggressor split; handle ONE bar may complete multiple buckets (large-volume bar) — split volume proportionally preserving buy/sell ratio
    - Use structlog.get_logger(__name__).debug for transitions
    - Unambiguous docstring citing Easley/Lopez de Prado 2011 and noting "exact aggressor split replaces BVC (DEEP6 DATA-02 verified)"
  </action>
  <verify>
    <automated>pytest tests/orderflow/test_vpin.py -x -q</automated>
  </verify>
  <done>All 6 tests pass. VPINEngine usable standalone.</done>
</task>

<task type="auto" tdd="true">
  <name>T-12-01-03: Wire VPIN into scorer as FINAL multiplier stage and add integration test</name>
  <files>deep6/state/shared.py, deep6/scoring/scorer.py, tests/scoring/test_scorer_with_vpin.py</files>
  <behavior>
    - SharedState owns one VPINEngine instance (1m only — 5m VPIN deferred)
    - SharedState.on_bar_close for 1m bar: calls vpin.update_from_bar(bar) BEFORE scorer.score_bar(...)
    - scorer.score_bar receives vpin_modifier via new kwarg (default 1.0 preserves existing tests)
    - Multiplier order locked: base → category → zone → IB → VPIN → clip(0, 100)
    - VPIN multiplier applies to FINAL fused confidence (total_score) only — NOT to per-signal raw scores
    - Test: bar stream with TOXIC VPIN (>0.9 percentile) caps TypeA frequency; CLEAN VPIN (<0.3) unchanged
    - Test: VPIN multiplier NEVER multiplied with IB multiplier pre-fusion (read scorer.py: IB and VPIN are separate line items)
  </behavior>
  <action>
    In deep6/state/shared.py: add self._vpin = VPINEngine() in build(). In on_bar_close 1m path, call self._vpin.update_from_bar(bar) before scoring; pass vpin_modifier=self._vpin.get_confidence_modifier() into score_bar.
    In deep6/scoring/scorer.py: add vpin_modifier: float = 1.0 kwarg to score_bar. After IB multiplier application, insert: total_score *= vpin_modifier; total_score = max(0.0, min(100.0, total_score)). Document order in module docstring.
    Write tests/scoring/test_scorer_with_vpin.py with two tests: test_final_stage_ordering (asserts post-IB, pre-clip via monkeypatch); test_clip_bounds (score > 100 after mult clamps to 100).
    Update tests/test_scorer.py if any existing test now needs explicit vpin_modifier=1.0 (unlikely — default preserves behavior).
  </action>
  <verify>
    <automated>pytest tests/orderflow/ tests/scoring/ tests/test_scorer.py -x -q</automated>
  </verify>
  <done>All VPIN + scorer tests pass; existing scorer tests still pass; VPIN multiplier applied only as final stage on fused score.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Rithmic tick → FootprintBar | DATA-02 aggressor already validated upstream |
| FootprintBar → VPINEngine | Internal, trusted input |
| VPINEngine → scorer | Internal; bounds enforced by clip |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-12-01-01 | Denial of Service | VPINEngine on malformed bar (total_vol=0) | mitigate | Early return in update_from_bar; unit test with zero-volume bar |
| T-12-01-02 | Tampering | Modifier stacking with IB blows past TYPE_A threshold | mitigate | Enforce multiplier order in scorer; clip to [0,100]; integration test verifies |
| T-12-01-03 | Information Disclosure | VPIN metric logged to stdout | accept | Non-sensitive; structlog at debug level only |
</threat_model>

<verification>
- `pytest tests/orderflow/ tests/scoring/ tests/test_scorer.py -x` green
- Manual grep: `grep -n "math.erf" deep6/orderflow/vpin.py` returns nothing
- Manual inspect: `grep -n "vpin_modifier" deep6/scoring/scorer.py` shows single-site application after IB
- Existing tests (phases 01-09) still green: `pytest tests/ -x`
</verification>

<success_criteria>
1. VPINEngine computes buy/sell bucket volumes from exact aggressor split (no BVC/erf path reachable)
2. `get_confidence_modifier()` returns neutral 1.0 during first 10 buckets, then continuous 0.2x-1.2x by percentile
3. Scorer applies the modifier ONLY at the final stage, on fused score, with clip [0, 100]
4. No regression in existing phase 07/09 scorer tests
5. Module is async-safe (synchronous call on bar-close path — no I/O)
</success_criteria>

<footguns>
**FOOTGUN 1 — VPIN/IB compounding:** The reference impl's confidence was in [0,1]; DEEP6's score is [0,100] with an IB multiplier already live. Naively multiplying VPIN × IB on per-signal scores can push TYPE_A frequency to 0 in CLEAN regimes (1.15 × 1.2 saturates) or flatten everything in TOXIC. **Mitigation LOCKED:** VPIN applies to FUSED score only, as final stage, followed by clip.

**FOOTGUN 2 — BVC when aggressor is available:** The reference uses math.erf-based BVC because its data feed lacks aggressor. DEEP6 has exact aggressor per DATA-02. Using BVC here would be strictly worse and is forbidden by this plan's tests.

**FOOTGUN 3 — Warmup NaN:** `_estimate_sigma()` in reference returns 0.001 with <10 buckets, which saturates modifier. We bypass this entirely by returning neutral 1.0 during warmup.
</footguns>

<rollback>
If integration causes regression in scorer tests or live shadow run shows TYPE_A rate collapse:
1. Set `vpin_modifier=1.0` call-site override in SharedState (one-line change) — disables VPIN without removing code.
2. Full rollback: `git revert` this plan's commit; tests and scorer return to pre-VPIN state.
3. VPINEngine module left in place (harmless, unreferenced) for later re-enable.
</rollback>

<output>
After completion, create `.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-01-SUMMARY.md`
</output>
