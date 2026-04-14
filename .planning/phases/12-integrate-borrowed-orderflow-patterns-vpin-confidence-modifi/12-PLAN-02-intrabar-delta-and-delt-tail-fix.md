---
phase: 12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - deep6/state/footprint.py
  - deep6/engines/delta.py
  - tests/state/test_footprint_intrabar.py
  - tests/test_delta.py
autonomous: true
requirements: [OFP-03, OFP-04]

must_haves:
  truths:
    - "FootprintBar tracks running max_delta and min_delta across add_trade() calls"
    - "DELT_TAIL (bit 22) fires based on TRUE intrabar extreme, not bar-geometry proxy"
    - "NO new SignalFlags bit is added (bit positions 0-43 remain stable per STATE.md)"
    - "Delta-quality scalar emitted (1.15x closing-at-max / 0.7x peaked-and-faded) — applied to delta-based signals ONLY"
    - "Scalar is orthogonal to VPIN multiplier (different domain, different consumers)"
  artifacts:
    - path: "deep6/state/footprint.py"
      provides: "FootprintBar with max_delta, min_delta, running_delta, delta_quality_scalar()"
      contains: "max_delta"
    - path: "deep6/engines/delta.py"
      provides: "DELT_TAIL using intrabar extreme; DeltaResult carries delta_quality scalar"
      contains: "intrabar_max_delta|max_delta"
    - path: "tests/state/test_footprint_intrabar.py"
      provides: "Unit tests for running max/min delta monotonicity"
  key_links:
    - from: "deep6/state/footprint.py add_trade"
      to: "FootprintBar.max_delta / min_delta state"
      via: "update on every trade, before level vol accumulation"
      pattern: "self\\.max_delta"
    - from: "deep6/engines/delta.py DELT_TAIL detector"
      to: "bar.max_delta / bar.min_delta"
      via: "final_delta / extreme ratio >= 0.95"
      pattern: "bar\\.max_delta|bar\\.min_delta"
---

<objective>
Add running intrabar `max_delta` / `min_delta` to `FootprintBar.add_trade()`. Use these to FIX the existing `DELT_TAIL` signal (bit 22) which currently approximates via bar-geometry proxy. Emit a delta-quality scalar (1.15x closing-at-extreme / 0.7x peaked-and-faded) for delta-based signals. **No new signal bit — bit positions 0-43 stay locked.**

Purpose: Unblock proper Delta-At-Extreme logic that has been approximating since phase 03. The running intrabar delta is also a prerequisite for future phases.
Output: Modified `FootprintBar`, enhanced `DeltaEngine.DELT_TAIL`, delta-quality scalar in `DeltaResult`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-CONTEXT.md
@.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-RESEARCH.md

# Reference implementation
@/Users/teaceo/Downloads/kronos-tv-autotrader/python/orderflow_tv.py

# DEEP6 integration surfaces
@deep6/state/footprint.py
@deep6/engines/delta.py
@deep6/signals/flags.py

<interfaces>
From deep6/signals/flags.py:
```python
# Bit 22 = DELT_TAIL ("delta closes at 95%+ of its extreme")
# Bits 0-43 STABLE — DO NOT add new bit in this plan.
```

From deep6/state/footprint.py (current, ~129 lines):
```python
@dataclass
class FootprintBar:
    levels: dict[int, Level]
    total_vol: int
    bar_delta: int        # sum ask_vol - bid_vol at close
    # NO intrabar tracking today — this plan adds it.

    def add_trade(self, price: float, size: int, aggressor: str) -> None: ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>T-12-02-01: Add running max_delta / min_delta to FootprintBar.add_trade()</name>
  <files>deep6/state/footprint.py, tests/state/__init__.py (if missing), tests/state/test_footprint_intrabar.py</files>
  <behavior>
    - FootprintBar has fields: running_delta: int = 0, max_delta: int = 0, min_delta: int = 0
    - Each add_trade(price, size, aggressor): running_delta += +size (BUY) / -size (SELL); max_delta = max(max_delta, running_delta); min_delta = min(min_delta, running_delta)
    - Test: monotonic rise — 10 buy trades of size 5 → max_delta = 50, min_delta = 0
    - Test: reversal — 5 buys then 10 sells of size 5 → running_delta final -25, max_delta 25, min_delta -25
    - Test: closing-at-max — running_delta == max_delta at bar close → delta_quality_scalar() == 1.15
    - Test: peaked-and-faded — max_delta=100, final running_delta=20 → delta_quality_scalar() == 0.7
    - Test: neutral — mixed → scalar in (0.7, 1.15)
    - Method delta_quality_scalar() -> float: 1.15 if |final_delta / max_extreme| >= 0.95; 0.7 if |final_delta / max_extreme| < 0.35; linear between
  </behavior>
  <action>
    Modify deep6/state/footprint.py:
    - Add fields max_delta: int = 0, min_delta: int = 0, running_delta: int = 0 (dataclass with default 0)
    - In add_trade: update running_delta by aggressor sign BEFORE or alongside level.bid_vol/ask_vol bump; then max/min clamp
    - Add method delta_quality_scalar() returning the 0.7-1.15 bias based on ratio |bar_delta / max(|max_delta|, |min_delta|, 1)|
    - Update bar_delta finalization at close: bar_delta == running_delta (confirm by assertion in add_trade path or at close)
    - Keep existing __repr__ / serialization — add new fields to any to_dict/from_dict if present
    Create tests/state/test_footprint_intrabar.py with the five tests. Use minimal FootprintBar instances with add_trade calls.
    Verify no existing test (tests/test_footprint.py) regresses — fields default to 0 and existing tests don't read them.
  </action>
  <verify>
    <automated>pytest tests/state/test_footprint_intrabar.py tests/test_footprint.py tests/test_bar_builder.py -x -q</automated>
  </verify>
  <done>All intrabar-delta tests pass; existing footprint + bar-builder tests unchanged.</done>
</task>

<task type="auto" tdd="true">
  <name>T-12-02-02: Rewire DELT_TAIL (bit 22) to use true intrabar extreme; emit delta_quality in DeltaResult</name>
  <files>deep6/engines/delta.py, tests/test_delta.py</files>
  <behavior>
    - DELT_TAIL fires iff: (bar.bar_delta > 0 AND bar.bar_delta / bar.max_delta >= 0.95) OR (bar.bar_delta < 0 AND bar.bar_delta / bar.min_delta >= 0.95)
    - Previous bar-geometry proxy removed (close_pct, body_ratio blend) — replaced with ratio test
    - DeltaResult dataclass gains field delta_quality: float = 1.0 (from bar.delta_quality_scalar())
    - Consumers of DeltaResult apply delta_quality ONLY to delta-family signals (bit 21 DELT_RISE, 22 DELT_TAIL, 23 DELT_REV, 24 DELT_DIV, 25 DELT_FLIP, 26 DELT_TRAP, 27 DELT_SWEEP, 28 DELT_SLINGSHOT, 29 DELT_MIN, 30 DELT_MAX, 31 CVD, 32 DELT_VEL) — explicit whitelist, not all signals
    - Test: DELT_TAIL fires when bar_delta == max_delta (ratio 1.0)
    - Test: DELT_TAIL does NOT fire when bar_delta = 0.5 * max_delta (ratio 0.5)
    - Test: delta_quality == 1.15 when closing-at-extreme; 0.7 when faded
    - Test: existing DELT_TAIL tests updated to populate max_delta/min_delta (synthetic bars need these fields set)
  </behavior>
  <action>
    Modify deep6/engines/delta.py:
    - Locate DELT_TAIL detector (bit 22). Replace the current proxy with the ratio test above.
    - Add delta_quality field to DeltaResult (or whichever dataclass engine returns).
    - Populate delta_quality = bar.delta_quality_scalar() in the detect function before returning.
    - Whitelist delta-signal bits in a module constant DELTA_FAMILY_BITS = {21,22,23,24,25,26,27,28,29,30,31,32} — consumers (scorer) will read this in plan 04 if needed. For THIS plan, just attach the scalar to DeltaResult; consumption is deferred.
    - Add docstring: "delta_quality is orthogonal to VPIN; applies to delta-family signals only."
    Update tests/test_delta.py: any synthetic bar fixture used for DELT_TAIL must now set max_delta/min_delta. Add the four tests above. Remove any assertion relying on the old body_ratio proxy.
  </action>
  <verify>
    <automated>pytest tests/test_delta.py tests/state/test_footprint_intrabar.py -x -q</automated>
  </verify>
  <done>DELT_TAIL uses real intrabar extreme; delta_quality on DeltaResult; all delta tests green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| on_trade callback → FootprintBar.add_trade | Hot path, ~1000/sec; state mutation trusted from one event loop |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-12-02-01 | Denial of Service | add_trade cost increase from 2 extra ops | mitigate | Profile: ~50 ns added per trade; negligible at 1000 cps; unit test measures no >5% regression in bar_builder perf test if any |
| T-12-02-02 | Tampering | Adding new bit 44 by mistake collides with plan 03's TRAP_SHOT | mitigate | Explicit test asserts SignalFlags.DELT_TAIL == bit 22 unchanged AND no new bit emitted in DeltaEngine |
</threat_model>

<verification>
- `pytest tests/state/test_footprint_intrabar.py tests/test_footprint.py tests/test_bar_builder.py tests/test_delta.py -x` green
- `grep -nE "bit\\s*=\\s*4[4-9]" deep6/engines/delta.py` returns nothing
- `grep -n "close_pct\\|body_ratio" deep6/engines/delta.py` returns nothing in DELT_TAIL detector (proxy removed)
- Full phase 01-09 suite still green
</verification>

<success_criteria>
1. FootprintBar exposes max_delta, min_delta, running_delta — updated on every add_trade
2. delta_quality_scalar() returns 1.15 / 0.7 / interpolated per spec
3. DELT_TAIL (bit 22) uses true extreme ratio; proxy code deleted
4. No new SignalFlags bit added (STATE.md bit lock respected)
5. DeltaResult carries delta_quality for downstream scorer consumption
</success_criteria>

<footguns>
**FOOTGUN 1 — Accidentally adding a new bit:** Tempting to add `DELT_AT_EXTREME` as bit 44. **FORBIDDEN** — the existing DELT_TAIL IS the at-extreme signal. This plan fixes it; plan 03 owns bit 44 (TRAP_SHOT). Any PR adding a bit here is a regression.

**FOOTGUN 2 — Running_delta sign convention:** aggressor=BUY is +size (ask_vol), aggressor=SELL is -size (bid_vol). Matches DATA-02 verified convention. Swapping signs silently corrupts every delta signal downstream.

**FOOTGUN 3 — Proxy removal breaks synthetic test fixtures:** Existing tests/test_delta.py may construct FootprintBar without max_delta set (default 0). When bar_delta > 0 and max_delta == 0, the ratio is undefined. Guard: if max_delta == 0 and bar_delta > 0, treat as max_delta = bar_delta (closing-at-trivial-extreme, conservative 1.0x quality).

**FOOTGUN 4 — Delta-quality stacking:** The delta_quality scalar must NOT apply to non-delta signals (e.g., absorption at bit 0-6) — those have their own quality domain. Whitelist enforced.
</footguns>

<rollback>
1. `git revert` this commit restores bar-geometry proxy DELT_TAIL.
2. FootprintBar fields max_delta/min_delta/running_delta retained (harmless unused data) OR removed — full revert removes them.
3. No data-migration needed: session-persistence SQLite rows pre-date the new fields; deserialization uses dataclass defaults.
</rollback>

<output>
After completion, create `.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-02-SUMMARY.md`
</output>
