# Phase 12 Burn-In Observation Report

**Session:** 2026-03-10  
**Bars:** 390 (1m RTH)  
**Data:** REAL NQ 1m OHLCV from `data/ohlcv/NQ_1m_continuous.parquet`  
**Microstructure:** SYNTHETIC (aggressor split biased by body direction; 
intrabar delta simulated as biased random walk). Not suitable for P&L claims — 
validates firing-rate calibration only.

## 1. VPIN confidence modifier distribution

min=0.277  max=1.200  
mean=1.067  median=1.124  
stdev=0.173

Histogram:
  - `[0.20, 0.40)` : 6  (1.5%)
  - `[0.40, 0.60)` : 7  (1.8%)
  - `[0.60, 0.80)` : 19  (4.9%)
  - `[0.80, 0.95)` : 25  (6.4%)
  - `[0.95, 1.05)` : 49  (12.6%)
  - `[1.05, 1.20)` : 257  (65.9%)
  - `[1.20, 1.21)` : 27  (6.9%)

Flow regime occupancy: {'NORMAL': 118, 'CLEAN': 250, 'ELEVATED': 18, 'TOXIC': 4}
% of bars at neutral [0.95, 1.05): 12.6%

## 2. TRAP_SHOT slingshot cadence

Total fires this session: **0**
Per-variant: {}
z_threshold=2.0  min_history_bars=30
Fires per bar: 0.0000  (≈ 0.00/hour)

## 3. SetupTracker state distribution

  - **SCANNING   ** :  163  (41.8%)
  - **DEVELOPING ** :  227  (58.2%)
  - **TRIGGERED  ** :    0  (0.0%)
  - **MANAGING   ** :    0  (0.0%)
  - **COOLDOWN   ** :    0  (0.0%)

No TRIGGERED transitions observed.

## 4. Walk-forward tracker convergence

Total signals recorded: 390
Outcomes resolved: 1135  (across 3 horizons = 1170 pending emissions)
EXPIRED: 0  CORRECT: 537  INCORRECT: 587  NEUTRAL: 11
Cells with ≥50 samples (sharpe_window): 2
Auto-disabled cells: 2
Sample per-cell Sharpe (bottom 3 / top 3):
  - TREND_DOWN/delta: sharpe=-0.423  (n=47)
  - RANGE/trap: sharpe=-0.365  (n=45)
  - RANGE/imbalance: sharpe=-0.355  (n=47)
  - TREND_UP/structural: sharpe=0.243  (n=46)
  - TREND_DOWN/trap: sharpe=0.248  (n=47)
  - RANGE/structural: sharpe=0.759  (n=48)

## 5. DELT_TAIL bit 22 firing — pre/post rewire

NEW (intrabar-extreme)        fires: 313  (80.3% of bars)
LEGACY (bar-geometry proxy)   fires: 37  (9.5% of bars)
NEW-only (rewire captured new): 276
LEGACY-only (rewire suppressed): 0

## Parameter calibration flags

- **TRAP_SHOT never fired** — z_threshold=2.0 too strict on synthetic microstructure; try z_threshold=1.5 and re-check on real footprint data.
- **SetupTracker never left DEVELOPING → TRIGGERED** — SCORE_MIN_TIER_A_CROSS=80 + soak_bars≥10 + TYPE_A tier is a narrow triple-gate on single-session data. Verify synthetic scorer produces Tier-A bars (threshold 80).
- DELT_TAIL rewire fires more than 2× legacy — synthetic intrabar path may under-represent max_delta; real DOM replay needed for true firing rate.

## Recommended next steps

1. Re-run on Databento MBO replay (real intrabar trade stream) — will give TRUE max_delta / min_delta rather than simulated, finalizing DELT_TAIL rewire firing rate.
2. Sweep VPIN `(bucket_volume, warmup_buckets)` ∈ {(500,5),(1000,10),(2000,15)} across 10 sessions; pick the config where modifier histogram is widest.
3. Sweep SlingshotDetector `z_threshold` ∈ {1.5, 1.75, 2.0, 2.25} — target is 1–3 fires/session on average real RTH data.
4. Verify SetupTracker SCORE_MIN_TIER_A_CROSS=80 using real ScorerResult stream; this burn-in uses a synthetic scorer and cannot validate the threshold.
5. Run WalkForwardTracker across 5+ trading days to exercise the 50-sample auto-disable path.
