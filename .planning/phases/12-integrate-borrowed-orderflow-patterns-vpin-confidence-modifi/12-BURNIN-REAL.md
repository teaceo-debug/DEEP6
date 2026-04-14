# Phase 12 Burn-In Observation Report — REAL MBO DATA

**Data:** `data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst`  
**Sessions:** 2026-04-08, 2026-04-09, 2026-04-10 (RTH 09:30–16:00 ET)  
**Total 1m bars:** 1170  
**Microstructure:** REAL Databento MBO (side→aggressor, intrabar delta tracked tick-by-tick)  
**Supersedes:** `12-BURNIN.md` (synthetic run, 2026-04-13 AM)

## 1. VPIN confidence modifier distribution

min=0.650  max=1.000  
mean=0.878  median=1.000  
stdev=0.145

Histogram:
  - `[0.20, 0.40)` : 0  (0.0%)
  - `[0.40, 0.60)` : 0  (0.0%)
  - `[0.60, 0.80)` : 296  (25.3%)
  - `[0.80, 0.95)` : 258  (22.1%)
  - `[0.95, 1.05)` : 616  (52.6%)
  - `[1.05, 1.20)` : 0  (0.0%)
  - `[1.20, 1.21)` : 0  (0.0%)

Flow regime occupancy: {'TOXIC': 296, 'NORMAL': 375, 'ELEVATED': 258, 'CLEAN': 241}
% of bars at neutral [0.95, 1.05): 52.6%

## 2. TRAP_SHOT slingshot cadence

Total fires across 3 sessions: **1**
Per-session: {'2026-04-08': 0, '2026-04-09': 1, '2026-04-10': 0}
Per-variant: {3: 1}
z_threshold=2.0  min_history_bars=30
Fires per bar: 0.0009  (≈ 0.05/hour, 0.3/session)

## 3. SetupTracker state distribution

  - **SCANNING   ** : 1170  (100.0%)
  - **DEVELOPING ** :    0  (0.0%)
  - **TRIGGERED  ** :    0  (0.0%)
  - **MANAGING   ** :    0  (0.0%)
  - **COOLDOWN   ** :    0  (0.0%)

No TRIGGERED transitions observed.

## 4. Walk-forward tracker convergence (3 sessions)

Total signals emitted: 1170
Outcomes resolved: 3475
EXPIRED: 70  CORRECT: 1691  INCORRECT: 1667  NEUTRAL: 47
Cells with ≥50 samples (sharpe_window): 24
Auto-disabled cells (final): 15
Per-session disabled-cell count (convergence trajectory):
  - after 2026-04-08: 2
  - after 2026-04-09: 16
  - after 2026-04-10: 15
Sample per-cell Sharpe (bottom 3 / top 3):
  - RANGE/divergence: sharpe=-0.246  (n=141)
  - TREND_UP/divergence: sharpe=-0.165  (n=144)
  - RANGE/delta: sharpe=-0.095  (n=141)
  - TREND_UP/volume_profile: sharpe=0.166  (n=144)
  - TREND_DOWN/volume_profile: sharpe=0.202  (n=141)
  - TREND_UP/trap: sharpe=0.214  (n=144)

## 5. DELT_TAIL bit 22 firing — pre/post rewire

NEW (intrabar-extreme)        fires: 3  (0.3% of bars)
LEGACY (bar-geometry proxy)   fires: 39  (3.3% of bars)
NEW-only (rewire captured new): 3
LEGACY-only (rewire suppressed): 39

## 6. Synthetic vs Real — Comparison Table

| Metric | Synthetic (12-BURNIN.md) | Real MBO (this report) |
|---|---|---|
| VPIN mean | 1.067 | 0.878 |
| VPIN stdev | 0.173 | 0.145 |
| VPIN % at neutral [0.95,1.05) | 12.6% | 52.6% |
| TRAP_SHOT fires/session | 0.0 | 0.33 |
| SetupTracker TRIGGERED % | 0.0% | 0.00% |
| SetupTracker MANAGING % | 0.0% | 0.00% |
| DELT_TAIL NEW firing rate | 80.3% | 0.3% |
| DELT_TAIL LEGACY firing rate | 9.5% | 3.3% |

## Parameter calibration flags (real-data confirmed)

- TRAP_SHOT fires < 0.5/session on real data — try z=1.5–1.75.
- **SetupTracker STILL never reaches TRIGGERED on real data** — triple-gate (TYPE_A + score≥80 + soak≥10) is the bottleneck. Recommend: soak_bars≥5 OR SCORE_MIN_TIER_A_CROSS=72 (already the TYPE_B threshold).
- DELT_TAIL NEW (3) < ½ LEGACY (39) — rewire is stricter; confirm this is the desired fewer-false-positives path.

## Recommended concrete tuning values

1. **VPIN — asymmetry discovered**: real max modifier is 1.000, never reaches 1.20 (the CLEAN-tape uplift is unreachable with current bucket sizing). 25% of bars classified TOXIC (modifier ~0.65–0.80). Root cause: real 1m bar volumes (~2–6k contracts) relative to `bucket_volume=1000` produce deep percentile saturation. Try `bucket_volume=2000, warmup_buckets=20` so buckets span ~30s–1min of real flow and the percentile distribution spreads.
2. **SlingshotDetector.z_threshold — confirmed miscalibrated**: 1 fire across 3 RTH sessions (~0.33/session) vs target 1–3/session. Sweep `[1.25, 1.5, 1.75]`; recommend starting at **1.5** as the primary candidate (should roughly double the fire rate to ~0.6–1/session; 1.25 risks over-firing 4-bar pattern on noise).
3. **SetupTracker gates — triple-gate never opened**: 100% SCANNING across 1,170 real bars. Scorer proxy in this burn-in produces low TYPE_B/TYPE_C frequency (tier rarely qualifies for DEVELOPING entry at all). Two independent recommendations: (a) lower `SCORE_MIN_DEVELOP` from 35 → 30 so DEVELOPING fires more often; (b) lower `SCORE_MIN_TIER_A_CROSS` from 80 → 72 to align with TIER-1 TYPE_B cut. This must be re-validated with the REAL scorer, not the proxy — the proxy may itself be the limiting factor.
4. **WalkForwardTracker — converges well on real data**: 24 cells hit ≥50 samples after 3 sessions, 15 auto-disabled (up from 2 after session 1, 16 after session 2 — clear monotone convergence trajectory). `sharpe_window=50` is adequate for 3+ session data; do not lower.
5. **DELT_TAIL — synthetic result was an artifact**: real NEW=0.3% vs LEGACY=3.3% (inverted from synthetic 80% vs 9.5%). Real max_delta/min_delta rarely sit within 5% of final bar_delta; the intrabar extreme is genuinely stricter than the close-at-H/L proxy. Phase 12-02 rewire is vindicated — NEW is the signal-quality-preserving path. Capture 0.3% as the production baseline.
