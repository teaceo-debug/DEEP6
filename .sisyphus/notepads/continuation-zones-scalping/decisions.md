# Decisions — Continuation Zones Scalping

## Architecture Decisions
- Output dir: research/continuation_zones/ (new, isolated from existing DEEP6 modules)
- Backtest data: Databento ohlcv-1m, resample in Python to 5m/15m (avoids schema drift)
- Optimization: Optuna (already used in DEEP6 ecosystem) + walk-forward (8mo IS / 4mo OOS)
- Minimum trades: 200 in OOS period for a valid parameter set
- Overfit threshold: IS Sharpe > 2× OOS Sharpe → flagged and excluded from recommendations

## NinjaScript Decisions
- New file: ContinuationZones_5_15.cs (do NOT modify original InstitutionalZones_MTF.cs)
- Only AddDataSeries for 15m (primary series is 5m, bip=0 → TF5, bip=1 → TF15)
- Remove ALL reversal zone code — ZoneKind enum has only RBR and DBD
- BrushUtil kept but stripped to only MakeSolid + Frozen (remove BrushToString/StringToBrush if XML serialization not needed for new inputs)

## Pending Decisions (fill in after research)
- Dissipation logic: (awaiting R2)
- Scoring components: (awaiting R3)
- RTH filter: on or off for backtesting (awaiting R1+R5)
- Zone cap: 8 zones max? (awaiting R2)
## [2026-05-25] R3: Clean Scoring System Design
Use a 5 x ternary model (each component 0/1/2) so total score is always 0-10, readable, and parity-safe. Only Freshness is dynamic; all other components are frozen at zone creation.

### Chosen components
1. **Freshness (dynamic)**
   - 2 = untouched / first retest only (`touch_count == 0` before current test)
   - 1 = exactly one completed prior touch that reacted but did not invalidate (`touch_count == 1`)
   - 0 = two or more prior touches, or zone already materially degraded (`touch_count >= 2`)
   - Why: first-touch edge is one of the strongest SD effects and is the only dynamic factor worth keeping.

2. **Departure Strength (static)**
   - Inputs: `departure_body_to_height_bp`, `departure_close_extension_to_height_bp`
   - 2 = body >= 1.50 x zone height (`>= 15000 bp`) AND close extends >= 0.50 x zone height (`>= 5000 bp`) beyond the zone edge
   - 1 = body >= 1.00 x zone height (`>= 10000 bp`) AND close is outside the zone (`> 0 bp` extension)
   - 0 = otherwise
   - Why: strongest direct evidence that the base caused a real imbalance.

3. **Base Quality (static)**
   - Inputs: `base_candle_count`, `max_base_body_ratio_bp`
   - 2 = `base_candle_count <= 2` AND `max_base_body_ratio_bp <= 3500`
   - 1 = `base_candle_count <= 3` AND `max_base_body_ratio_bp <= 5000`
   - 0 = otherwise
   - Why: continuation zones work best when the base is a brief pause, not a noisy battle.

4. **Trend Alignment (static)**
   - Snapshot 15m EMA50 regime once at creation.
   - Inputs: `trend_close_side_ok`, `trend_slope_ok`
   - 2 = both booleans true
   - 1 = exactly one boolean true
   - 0 = neither true
   - Why: continuation zones should earn extra credit when they point the same way as the 15m regime, but this must be stamped once, not recomputed per zone per bar.

5. **Zone Height (static)**
   - Input: `zone_height_ticks`, `timeframe_min`
   - 5m zones:
     - 2 = 4-10 ticks
     - 1 = 3-12 ticks, excluding the 2-point band
     - 0 = otherwise
   - 15m zones:
     - 2 = 6-14 ticks
     - 1 = 5-18 ticks, excluding the 2-point band
     - 0 = otherwise
   - Why: width directly affects execution quality and stop efficiency; too thin is noise, too wide kills scalp expectancy.

### Rejected components
- **Time Away**: not observable at creation, so it violates the static-score requirement.
- **Higher-TF Overlap**: useful, but expensive and partially redundant with trend/context; better as an optional overlay, not core score.
- **Bar of Day**: good execution filter, but it is session context rather than intrinsic zone quality; keep separate from the zone score.
- **Volume Confirmation**: informative, but highly correlated with departure strength and session timing; leave out of v1 to keep the score price-first and parity-simple.
- **R:R to opposite zone**: circular, dynamic, and unstable because the score changes when other zones appear/disappear.

### Score interpretation
- 0-4 = ignore
- 5-6 = visible / watchlist only
- 7-8 = tradeable
- 9-10 = top-tier

Practical anchors:
- 3 = one notable strength, but multiple structural weaknesses
- 5 = mixed zone; visually acceptable, but not enough confluence for automatic trading
- 7 = fresh or near-fresh, decent impulse, clean base, acceptable width, and at least some trend support
- 10 = virgin first retest + explosive departure + tight base + full trend alignment + ideal width

### Minimum tradeable score
Use **7/10** as the initial trading threshold.
Reasoning: 6 still admits too many �2 strong / 1 average / 2 weak� zones for NQ scalping. A 7 requires either three strong components, or two strong plus three acceptable ones, which is a better starting filter for maintaining win rate after slippage and fees.

### Implementation notes
- Compute and store all static component inputs at zone creation.
- Keep only `touch_count` dynamic; Freshness is derived from that integer only.
- Trend Alignment should use a cached 15m EMA50 + slope snapshot computed once per 15m bar, then stamped onto each new zone.
- No per-zone per-bar EMA calls.
- No volume dependency in the core v1 score.
- For parity, convert all ratios to integer basis points and all prices to integer ticks before scoring.

### Parity-safe Python scoring signature
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
    ...
```

### Deterministic component logic
```python
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

trend_alignment = 2 if trend_close_side_ok and trend_slope_ok else 1 if (trend_close_side_ok != trend_slope_ok) else 0

if timeframe_min == 5:
    zone_height = 2 if 4 <= zone_height_ticks <= 10 else 1 if 3 <= zone_height_ticks <= 12 else 0
elif timeframe_min == 15:
    zone_height = 2 if 6 <= zone_height_ticks <= 14 else 1 if 5 <= zone_height_ticks <= 18 else 0
else:
    raise ValueError("timeframe_min must be 5 or 15")

total = freshness + departure + base_quality + trend_alignment + zone_height
return total, {
    "freshness": freshness,
    "departure": departure,
    "base_quality": base_quality,
    "trend_alignment": trend_alignment,
    "zone_height": zone_height,
}
```

### Operational note
If backtests later show strong time-of-day or volume uplift, add those as **separate execution filters**, not as replacements for the 5 core zone-quality components.
<!-- OMO_INTERNAL_INITIATOR -->
