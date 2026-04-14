# Quick Task 260413-s1d — Fix `databento_feed.py` bugs

**Date:** 2026-04-14
**Type:** Bug fix (pre-Phase-13 unblocker)

## Problem

During backtest-engine research (6-agent parallel investigation, 2026-04-13), the codebase audit found `deep6/data/databento_feed.py` had runtime bugs that would crash on first use:

1. **Line 95** — `current_bar.total_volume` → `FootprintBar` attribute is `total_vol` (AttributeError on last partial bar).
2. **Lines 59, 84** — `FootprintBar(tick_size=tick_size)` → `FootprintBar.__init__` has no `tick_size` param (TypeError at construction).
3. **Lines 74, 78, 85, 96** (discovered during fix) — `open_time` / `close_time` attributes do not exist on `FootprintBar`; it only has `timestamp: float`.
4. **CVD chain broken** — `finalize()` was called without `prior_cvd`, so session CVD never accumulated across bars.

No tests or call sites existed; the module was never invoked in production or CI. Bugs would surface on first Phase-13 integration.

## Fix

Rewrote the bar-accumulation loop to:
- Construct `FootprintBar()` with no args
- Set `current_bar.timestamp = float(bar_epoch)` instead of `open_time`
- Drop `close_time` writes (unused downstream)
- Pass `prior_cvd` through `finalize()` to keep CVD chain correct across bars
- Use `current_bar.total_vol` on the final-partial-bar guard

## Scope change

Originally intended to also swap `schema="trades"` → `"mbo"`. **Deferred to Phase 13**: MBO records require `action` field filtering (`A`/`C`/`M`/`T`) and DOM reconstruction, not a one-character schema change. Trade-only replay remains valid for footprint/delta signals; DOM signals (E2/E3/E4) will fire correctly only after the Phase 13 `MBOAdapter` lands.

## Verification

- `python3 -c "from deep6.data.databento_feed import DatabentoFeed"` → OK
- No existing tests or callers impacted (`grep DatabentoFeed` returns only the module itself)

## Files changed

- `deep6/data/databento_feed.py` — bar-loop rewrite
