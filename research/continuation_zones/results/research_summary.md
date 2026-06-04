# NQ Continuation Zone Scalping — Research Summary
**Date**: 2026-05-25
**System**: ContinuationZones_5_15 + Python Backtest Engine
**Status**: Phase 0 complete. Backtest pending data download.

---

## 1. Continuation Zone Theory (R1)

### What RBR/DBD Zones Are

Rally-Base-Rally (RBR) and Drop-Base-Drop (DBD) are continuation patterns where price pauses briefly during a directional move before resuming in the same direction. The three-candle structure is: a strong impulse candle, a tight consolidation candle (the base), and a confirmation candle that breaks out of the base in the original direction.

The institutional mechanic behind these zones: when a trend is underway, institutions that missed the initial entry add to their positions during the pause. The base candle represents that accumulation. When price returns to the zone, those unfilled limit orders absorb selling (for RBR) or buying (for DBD), causing the continuation.

**Why RBR/DBD are weaker than reversal zones (DBR/RBD):** Reversal zones require institutions to reverse the entire trend direction, which demands massive capital and creates a powerful zone. Continuation zones only require adding to an existing position, which is a smaller capital commitment. The result is a 20-30 percentage point lower probability on first touch compared to reversal zones. Multiple practitioner sources (PriceActionNinja, ICT, Quantum Algo) confirm this hierarchy: DBR/RBD (strongest) > RBR/DBD (weaker) > random support/resistance.

**Expected win rate with proper filtering:** 60-70% on first touch, not 75%+. Anyone claiming higher without rigorous filtering is overfitting.

### NQ-Specific Behavior

NQ behaves differently from ES in ways that matter for continuation zone trading:

**Initial Balance statistics (2015-2025, 1,691+ trading days):**
- NQ median extension: 55.6% of IB range (vs ES 63.6%)
- NQ reaches 100% extension: only 12.8% of days (vs ES 18.8%)
- NQ IB high = RTH high: 36.7% of days

NQ is stickier to its early structure than ES. It sets its extremes during the first hour more often and extends less afterward. This means continuation zones formed during the opening hour have higher probability of being retested before price extends further.

**Time-of-day edge (Dokakuri Magic Hours, 2013-2026 data):**
- 07:00 AM ET: 83.4% win rate for continuation trades
- 08:00 AM ET: 79.7% win rate
- 06:00 AM ET: 78.7% win rate

The pre-market window (06:00-08:00 ET) is the highest-probability window for NQ continuation trades. This is before RTH opens at 09:30. Zones formed during this window and traded by 10:00 AM have the strongest edge. After 11:30 AM, edge declines sharply. After 14:00 ET, zones are effectively expired.

### Zone Validity Criteria

**Base candle requirements:**
- Body-to-range ratio: 0.25-0.35 (body is 25-35% of total candle range)
- Below 0.20: too tight, signals low energy rather than consolidation
- Above 0.35: borderline; may be an early breakout candle, not a true base
- Wick-to-body ratio: 2.5-3.5 (wicks are 2.5-3.5x the body size)

**Departure requirements:**
- Confirmation candle body must be at least 2-3x the zone height
- Large-bodied candles (70%+ body-to-range ratio) on the departure
- NQ-specific: departure should be at least 20-30 points on 5m, 50-75 points on 15m

**Invalidation rule (critical distinction):**
- Wick through zone boundary = mitigation (zone weakened but still valid)
- Body CLOSE through zone boundary = invalidation (zone is broken, remove it)
- This is the consensus across all supply/demand sources. Wick pokes are noise; body closes are decisions.

**Touch count decay:**
- 1st touch: highest probability (most unfilled orders remain)
- 2nd touch: weaker (some orders already filled)
- 3rd+ touch: unreliable (most orders consumed)
- Remove zones after 3 touches

### RTH vs ETH

RTH-only (09:30-16:00 ET) backtesting is cleaner for continuation zones. ETH includes thin overnight trading with different microstructure, lower volume, and wider spreads. Most institutional volume occurs during RTH. The practitioner consensus is unanimous on this point. The backtest engine filters to RTH only.

---

## 2. Zone Dissipation Design (R2)

### Lifecycle Model

Zones move through four stages: Fresh, Tested, Delivered, Expired.

**Stage opacity caps:**
- Fresh (touch_count == 0): 1.0 (full opacity)
- Tested (touch_count == 1): 0.8
- Delivered (touch_count == 2): 0.4
- Expired: removed from chart

**Continuous decay formula within each stage:**
```
opacity = stage_cap * 0.98^ageBars * (1 - touchCount * 0.20)
```

This formula combines age decay (0.98 per bar) with touch-count penalty (20% per touch). A fresh zone at 100 bars old has opacity ~0.13 before the stage cap is applied. The formula ensures zones fade gracefully rather than disappearing abruptly.

**Touch counting is edge-triggered:** The `WasInsideOnPriorBar` flag prevents multi-bar residence inside a zone from consuming multiple touches. Only the first bar of entry into the zone increments the touch counter.

### NQ-Specific Bar Counts

Bar counts are calibrated to approximately 4 trading days of RTH data:

- 5m chart: ~78 bars/day RTH, so `MaxAgeBars5m = 300` (78 * 4 = 312, rounded to 300)
- 15m chart: ~26 bars/day RTH, so `MaxAgeBars15m = 100` (26 * 4 = 104, rounded to 100)

The 4-day window is grounded in the hourly retracement research: by 10:00 AM on the day a zone forms, conditional probability of an untouched overnight level drops to 40-50%. By 14:00 ET, it's ~9-12%. Zones that survive 4 trading days without being touched are almost certainly expired.

**15m zones on a 5m execution timeline:** Age is tracked in 15m units, not 5m bars. This preserves the `MaxAgeBars15m` semantics correctly. A 15m zone that is 100 15m-bars old is expired, regardless of how many 5m bars have elapsed.

### Chart Cleanliness

Maximum 8 active zones on chart at any time. When a new zone would exceed the cap, the lowest-scoring active zone is removed. This prevents chart clutter and forces the system to surface only the highest-quality setups.

Low-score zones (below `MinScoreToDisplay`) remain on chart at 10% opacity with labels suppressed. They are visible as faint background context but don't compete for attention with tradeable zones.

---

## 3. Scoring System Design (R3)

### 5-Component Model (0-10)

The scoring system uses 5 ternary components (each 0/1/2), summing to a 0-10 total. Only Freshness is dynamic; all other components are frozen at zone creation. This design is parity-safe between Python and NinjaScript because it avoids per-bar recomputation of expensive indicators.

| Component | 0 | 1 | 2 |
|-----------|---|---|---|
| Freshness | touch_count >= 2 | touch_count == 1 | touch_count == 0 |
| Departure Strength | body_bp < 10000 OR ext_bp <= 0 | body_bp >= 10000 AND ext_bp > 0 | body_bp >= 15000 AND ext_bp >= 5000 |
| Base Quality | count > 3 OR body_bp > 5000 | count <= 3 AND body_bp <= 5000 | count <= 2 AND body_bp <= 3500 |
| Trend Alignment | neither close_ok nor slope_ok | exactly one of {close_ok, slope_ok} | both close_ok AND slope_ok |
| Zone Height (5m) | < 3 or > 12 ticks | 3-12 ticks (excl. 2-point band) | 4-10 ticks |
| Zone Height (15m) | < 5 or > 18 ticks | 5-18 ticks (excl. 2-point band) | 6-14 ticks |

**Component rationale:**

*Freshness* is the only dynamic component because first-touch edge is one of the strongest supply/demand effects. Each subsequent touch materially degrades the zone's remaining order pool.

*Departure Strength* uses basis points relative to zone height. `body_bp` is `(departure_body / zone_height) * 10000`. A score of 2 requires the departure body to be 1.5x the zone height AND the close to extend 0.5x beyond the zone edge. This is the strongest direct evidence of a real imbalance.

*Base Quality* rewards tight, brief consolidations. Two candles or fewer with a body ratio under 35% is the ideal base. Three candles with up to 50% body ratio is acceptable. More than that suggests a noisy battle rather than clean accumulation.

*Trend Alignment* snapshots the 15m EMA50 regime once at zone creation. `close_ok` means price is on the correct side of EMA50 for the zone direction. `slope_ok` means EMA50 slope confirms the trend. Both true = full credit. Neither true = no credit. This is stamped once, not recomputed per bar.

*Zone Height* directly affects execution quality. Too thin (under 3 ticks on 5m) and the entry/stop placement becomes impractical. Too wide (over 12 ticks on 5m) and the scalp expectancy collapses because the stop must be placed outside the zone.

### Score Interpretation

| Score | Meaning | Chart Display |
|-------|---------|---------------|
| 0-4 | Ignore (low conviction noise) | 10% opacity, no label |
| 5-6 | Watch only (visible, not tradeable) | Gray/yellow label |
| 7-8 | Tradeable (qualifies for auto-trading) | White label |
| 9-10 | High conviction (top-tier setup) | White label, highlighted |

**Practical anchors:**
- Score 3: one notable strength, multiple structural weaknesses
- Score 5: mixed zone; visually acceptable, not enough confluence for automatic trading
- Score 7: fresh or near-fresh, decent impulse, clean base, acceptable width, at least some trend support
- Score 10: virgin first retest + explosive departure + tight base + full trend alignment + ideal width

### Minimum Tradeable Score: 7/10

A threshold of 6 still admits too many "2 strong / 1 average / 2 weak" zone combinations for NQ scalping. A score of 7 requires either three strong components or two strong plus three acceptable ones. This is a better starting filter for maintaining win rate after slippage and fees.

The threshold is a starting point. If backtests show that score-7 zones underperform, raise to 8. If too few trades result, lower to 6 and add a session-time filter instead.

### Deterministic Python Scoring Logic

```python
def score_continuation_zone(
    *,
    timeframe_min: int,
    touch_count: int,
    departure_body_to_height_bp: int,
    departure_close_extension_to_height_bp: int,
    base_candle_count: int,
    max_base_body_ratio_bp: int,
    trend_close_side_ok: bool,
    trend_slope_ok: bool,
    zone_height_ticks: int,
) -> tuple[int, dict[str, int]]:

    freshness = 2 if touch_count == 0 else 1 if touch_count == 1 else 0

    departure = (
        2 if departure_body_to_height_bp >= 15000 and departure_close_extension_to_height_bp >= 5000
        else 1 if departure_body_to_height_bp >= 10000 and departure_close_extension_to_height_bp > 0
        else 0
    )

    base_quality = (
        2 if base_candle_count <= 2 and max_base_body_ratio_bp <= 3500
        else 1 if base_candle_count <= 3 and max_base_body_ratio_bp <= 5000
        else 0
    )

    trend_alignment = (
        2 if trend_close_side_ok and trend_slope_ok
        else 1 if (trend_close_side_ok != trend_slope_ok)
        else 0
    )

    if timeframe_min == 5:
        zone_height = 2 if 4 <= zone_height_ticks <= 10 else 1 if 3 <= zone_height_ticks <= 12 else 0
    elif timeframe_min == 15:
        zone_height = 2 if 6 <= zone_height_ticks <= 14 else 1 if 5 <= zone_height_ticks <= 18 else 0

    total = freshness + departure + base_quality + trend_alignment + zone_height
    return total, {
        "freshness": freshness, "departure": departure,
        "base_quality": base_quality, "trend_alignment": trend_alignment,
        "zone_height": zone_height,
    }
```

All ratios are converted to integer basis points and all prices to integer ticks before scoring. This ensures Python and NinjaScript produce identical results.

---

## 4. ATM Research (R4)

### NinjaTrader ATM Architecture

ATM (Automated Trade Management) strategies in NinjaTrader 8 manage exits after a manual or semi-automated entry. Key fields per target:

- **Stop Loss**: distance from entry in ticks where the stop is placed
- **Profit Target**: distance from entry in ticks where the target is placed
- **Auto Breakeven Profit Trigger**: profit in ticks that triggers moving stop to breakeven
- **Auto Breakeven Plus**: offset from entry when BE triggers (can be negative for a small buffer)
- **Auto Trail Profit Trigger**: profit in ticks that activates trailing stop
- **Auto Trail Stop Loss**: trail distance behind current price in ticks
- **Auto Trail Frequency**: how often the stop adjusts (1 tick = every tick)

Critical constraints:
- Stop and Target are OCO (One-Cancels-Other) by default
- Stop never moves backward (only tightens, never widens)
- Auto Trail Profit Trigger must be greater than Auto Breakeven Profit Trigger
- ATM is real-time only and cannot be backtested in Strategy Analyzer

**ATM vs Regular Strategy:** ATM handles exits in live/paper trading. For backtesting, use `SetStopLoss`/`SetProfitTarget` in NinjaScript code, then translate the winning parameters to ATM templates for live use.

### Three Preliminary ATM Profiles

These profiles are pre-optimization estimates based on professional NQ scalper practices. Final profiles require backtest confirmation.

| Profile | Stop | Target 1 | Target 2 | BE Trigger | Trail |
|---------|------|----------|----------|------------|-------|
| Conservative | 8 ticks | 12 ticks | None | 4 ticks | None |
| Balanced | 12 ticks | 16 ticks (50%) | 28 ticks (50%) | 6 ticks | 6-tick trail after 10 ticks |
| Aggressive | 10 ticks | 20 ticks (33%) | 40 ticks (67%) | 8 ticks | 8-tick trail after 12 ticks |

**Conservative (NQ_Conservative_8x12):** Tight stop, single target, no trailing. Prioritizes capital preservation and consistency. Expected win rate 55-60%. R:R 1.5:1. Best for operators who want clear invalidation and no position management complexity.

**Balanced (NQ_Balanced_12x16x28_Split):** Split position, two targets. Takes half at 16 ticks, lets the runner extend to 28 ticks with a trailing stop. Expected win rate 52-55%. Blended R:R ~1.8:1. The sweet spot for most prop traders.

**Aggressive (NQ_Aggressive_10x20x40_Extended):** Takes one-third at 20 ticks, lets two-thirds run to 40 ticks. Higher variance, higher upside. Expected win rate 48-52%. Blended R:R ~2.8:1. Requires discipline to hold through pullbacks.

**Note:** These are pre-optimization estimates. The backtest will determine which profile (or which parameter combination) actually produces the best risk-adjusted returns on NQ continuation zones. Do not use these profiles live until backtest results confirm them.

**Key insight from professional NQ scalper research:** Professional traders use ATR-based stops (1.5-2x ATR on 5m chart), not fixed distances. For NQ, this typically yields 45-90 point stops. The fixed-tick profiles above are simpler for initial backtesting; ATR-based stops are a natural next iteration.

---

## 5. Python Stack Audit (R5)

### Existing DEEP6 Infrastructure Reused

The research module reuses several existing DEEP6 components rather than rebuilding from scratch:

| Component | Location | Reuse |
|-----------|----------|-------|
| Zone schema | `deep6/engines/level.py` | Extend `LevelKind` with `CONTINUATION_RBR`, `CONTINUATION_DBD` |
| Zone registry | `deep6/engines/zone_registry.py` | `LevelBus` unified level store |
| Bracket exit | `deep6/backtest/bracket_exit.py` | Reuse as-is for single-target profiles |
| Backtest config | `deep6/backtest/config.py` | Extend with zone-specific params |
| Backtest runner | `deep6/backtest/research_runner.py` | Port loop pattern to Python |
| Data pipeline | `deep6/data/databento_feed.py` | Reuse Databento feed |
| Result store | `deep6/backtest/result_store.py` | DuckDB persistence |

The backtest engine rebuilds zone lifecycle from scratch during simulation. It does not use the detector's end-state (`touch_count`, `is_active`) as inputs to entry decisions. This prevents future information from leaking into the backtest.

### New Research Module

The continuation zones research lives in `research/continuation_zones/` as an isolated, standalone module. It is not part of the main `deep6v2` package. This isolation allows independent iteration and prevents research code from polluting production paths. Once validated, the detector and scorer can be promoted to `deep6/engines/`.

Module structure:
```
research/continuation_zones/
├── __init__.py
├── continuation_zones.py    # Zone dataclass, detector, scorer
├── data_loader.py           # Databento OHLCV download + RTH filter
├── backtest_engine.py       # Bar-by-bar simulation
├── optimization.py          # Optuna walk-forward optimization
├── results_analyzer.py      # ATM profile derivation from OOS results
├── run_backtest.py          # CLI entry point
└── tests/
    └── test_continuation_zones.py
```

### Missing Dependencies Added

These packages were not in the main `pyproject.toml` and are required for the research module. They are listed in `requirements-research.txt`:

| Package | Version | Purpose |
|---------|---------|---------|
| pandas | >=2.0 | OHLCV DataFrames, RTH filtering |
| databento | >=0.28 | MBO historical data download |
| optuna | >=3.0 | Walk-forward hyperparameter optimization |
| pyarrow | latest | Parquet cache for downloaded data |
| plotly | >=5.0 | Zone and equity curve visualization |

`vectorbt` was considered but excluded from v1. The custom backtest engine handles the zone-specific entry logic (limit fills at zone boundary, touch counting, invalidation) that vectorbt cannot express without significant customization.

---

## 6. Zone Detection Parameters (Final Defaults)

| Parameter | Default | Range Tested | Rationale |
|-----------|---------|--------------|-----------|
| SmallBodyRatio | 0.35 | 0.20-0.70 | Body/range <= 35% identifies tight base candles |
| MinZoneTicks | 2 | 1-5 | Minimum 0.50 point zone height for practical entry |
| MaxAgeBars5m | 300 | 20-300 | ~4 trading days before zone considered stale |
| MaxAgeBars15m | 100 | 10-100 | ~4 trading days on 15m |
| MaxTouchCount | 3 | 1-3 | Remove after 3rd touch (33% reaction probability) |
| MinScoreToDisplay | 5 | 4-7 | Show watchlist zones; trade only >= 7 |
| MaxActiveZones | 8 | fixed | Chart cleanliness cap |

**Tuning guidance:**
- Too few zones on chart: raise `SmallBodyRatio` (0.35 to 0.50)
- Too many zones: lower `SmallBodyRatio` or raise `MinScoreToDisplay`
- Zones expiring too fast: raise `MaxAgeBars5m`/`MaxAgeBars15m`
- Too many low-quality zones cluttering chart: raise `MinScoreToDisplay` to 6

---

## 7. Data Quality Notes

### Databento NQ Data

- Symbol: `NQ.c.0` (continuous front-month, automatic roll handling)
- Schema: `ohlcv-1m`, resampled to 5m and 15m in Python
- Dataset: `GLBX.MDP3` (CME Globex)
- `stype_in`: `continuous`
- Expected date range: 2025-05-25 to 2026-05-25 (1 year)
- RTH filter: 09:30-16:00 ET, Monday-Friday, excluding US market holidays
- Expected bar count after RTH filter: ~19,500 (5m), ~6,500 (15m)

The data loader normalizes Databento OHLC prices defensively: it prefers `to_df(price_type="float", pretty_ts=True)` but still divides OHLC columns by 1e9 if fixed-point values slip through. The RTH filter converts to `America/New_York`, keeps weekdays from 09:30 to 16:00, and optionally removes exchange holidays when `pandas_market_calendars` is installed (soft dependency).

Downloaded data is cached as Parquet to avoid re-downloading on subsequent runs.

### Known Gaps and Caveats

- ETH sessions excluded from backtesting (simpler, cleaner signals; different microstructure)
- Continuous contract rolls introduce synthetic price jumps at expiry. These are not adjusted. Roll dates should be inspected manually if anomalous zones appear around quarterly expiry.
- NQ tick size = 0.25 points; minimum zone = 2 ticks = 0.50 points
- The first 50 bars of any dataset have degraded trend scoring due to EMA50 warmup

---

## 8. Honest Limitations

1. **RBR/DBD zones are weaker than reversal zones.** Expect 55-65% win rate on first touch with proper filtering, not 75%+. Anyone claiming higher without rigorous walk-forward validation is overfitting to in-sample data.

2. **Single-candle base only.** The Python detector uses a prev-base-next (3-bar) pattern. Multi-candle consolidation bases (2-5 candles) are not supported in v1. This misses some valid zones where the base spans multiple bars.

3. **No volume data in scoring.** Departure strength uses price only (body size relative to zone height). Volume confirmation would add signal quality but adds complexity and a data dependency. Left out of v1 to keep the score price-first and parity-simple.

4. **Backtest uses limit fills at zone boundary.** Real fills may differ if price wicks through the zone quickly without pausing. Slippage is modeled as 2 ticks (1 per side) but actual slippage on fast moves can be higher.

5. **Walk-forward covers 1 year only.** Insufficient for regime-change testing across different volatility environments (e.g., 2020 COVID volatility, 2022 rate-hike regime). The parameters may not generalize to extreme volatility regimes.

6. **SmallBodyRatio default (0.35) may be too strict.** It produces fewer zones. Users who see too few signals should loosen to 0.45-0.55 and re-run the backtest to confirm the looser threshold still produces positive expectancy.

7. **EMA50 trend filter requires 50-bar warmup.** The first 50 bars of any dataset have degraded trend alignment scoring. The backtest engine skips entries during this warmup period.

8. **NT8 indicator requires 5m primary chart.** The `ContinuationZones_5_15.cs` indicator assumes the primary series is 5-minute. It will not draw zones correctly on tick, range, volume, or other bar types.

9. **ATM profiles are pre-optimization estimates.** The three profiles (Conservative, Balanced, Aggressive) are derived from professional NQ scalper practices, not from backtested NQ continuation zone data. Treat them as starting points only.

10. **No multi-timeframe confluence in v1 score.** Higher-timeframe zone overlap is a useful filter but was excluded from the core 5-component score to keep it simple and parity-safe. It can be added as a separate execution filter after the base system is validated.

---

## 9. Next Steps

### To Run the Backtest

```bash
# 1. Set API key
export DATABENTO_API_KEY=your_key_here

# 2. Run optimization (200 trials, ~30-60 min depending on hardware)
python research/continuation_zones/run_backtest.py --n-trials 200

# 3. Results saved to:
#    research/continuation_zones/results/optimization_results.csv
#    research/continuation_zones/results/best_trades.csv
#    research/continuation_zones/results/equity_curve.csv
#    research/continuation_zones/results/atm_profiles.json
```

The optimizer uses 8-month in-sample / 4-month out-of-sample walk-forward splits. OOS fitness is ranked by `oos_sharpe * oos_win_rate`. Parameter sets with IS Sharpe > 2x OOS Sharpe are flagged as overfit and excluded from recommendations. Minimum 200 OOS trades required for a valid parameter set.

### To Use the NT8 Indicator

1. Add `ContinuationZones_5_15` to a 5-minute NQ chart
2. Trade only zones with score >= 7 (white label)
3. Enter LIMIT orders at the dotted entry line (zone boundary)
4. Use ATM strategy: Conservative (8 tick stop, 12 tick target) as starting point
5. Paper trade minimum 2 weeks before live
6. Track: win rate, average winner, average loser, max drawdown, daily P&L variance

### Parameter Tuning Priority

After running the backtest, tune in this order:

1. **SmallBodyRatio** (most impactful): controls zone frequency. Start at 0.35, test 0.25-0.55.
2. **MinScoreToDisplay / trading threshold**: controls signal quality. Start at 7, test 6-8.
3. **MaxAgeBars5m/15m**: controls zone staleness. Start at 300/100, test 150-300/50-100.
4. **ATM profile**: Conservative vs Balanced vs Aggressive. Let backtest results decide.

### Promotion Path to Production

Once backtest confirms positive OOS expectancy:
1. Extend `LevelKind` enum in `deep6/engines/level.py` with `CONTINUATION_RBR`, `CONTINUATION_DBD`
2. Move detector and scorer to `deep6/engines/continuation_zones.py`
3. Register zones in `LevelBus` (zone registry)
4. Add continuation zone confluence check to `deep6/engines/confluence_rules.py`
5. Extend `BacktestConfig` with zone-specific parameters
6. Paper trade via NT8 indicator for 4+ weeks
7. Live promotion only after paper trade confirms backtest win rate within 5 percentage points

---

## Appendix: Research Confidence Summary

| Finding | Confidence | Source |
|---------|-----------|--------|
| RBR/DBD weaker than DBR/RBD | HIGH | Multiple practitioner sources, institutional theory |
| NQ stickier to early structure | HIGH | 12-year IB breakout statistical data |
| 06:00-08:00 AM highest probability | HIGH | Dokakuri Magic Hours (2013-2026) |
| Body-to-range 0.25-0.35 optimal | MEDIUM-HIGH | O'Neil Flat Base (34,000 trades), ICT standards |
| Body close = invalidation | HIGH | Consensus across supply/demand sources |
| First touch strongest | HIGH | Multiple sources, institutional order theory |
| RTH-only backtesting cleaner | HIGH | Practitioner consensus, microstructure theory |
| Zone age decay by 10:00 AM | MEDIUM-HIGH | Hourly Retracement research |
| 2-3x impulse move minimum | MEDIUM-HIGH | Practitioner consensus |
| 5-component 0-10 scoring model | DESIGN DECISION | decisions.md, R3 research |
| 7/10 minimum tradeable threshold | DESIGN DECISION | decisions.md, R3 research |
| 8-zone chart cap | DESIGN DECISION | R2 research |
| 0.98^ageBars decay formula | DESIGN DECISION | R2 research |
