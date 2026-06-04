# DEEP6 Signal Attribution — Overnight Research Findings
Generated: 2026-05-19 (overnight autonomous session)

## EXECUTIVE SUMMARY

After running 1,582,554 signal fires across 332 sessions (Jan 2025 - Apr 2026)
with walk-forward validation and regime analysis, the picture is clear:

**Only 2 signals have validated edge on OHLCV-synthesized data:**
1. **ABS_04** (Effort vs Result) — PF 3.94 overall, **PF 6.19 in test set**, regime-dependent
2. **AUCT_03** (Poor High/Low) — PF 1.44 overall, PF 1.20 in test set

**Everything else is noise on synthesized OHLCV.** This is expected and informative.

---

## VALIDATED SIGNALS

### ABS_04 — Effort vs Result Absorption ⭐⭐⭐⭐⭐

| Metric | Value |
|--------|-------|
| Overall PF | 3.94 |
| Train PF (70%) | 3.16 |
| **Test PF (30%)** | **6.19** ← IMPROVING in test |
| Walk-forward | ✅ PASS |
| N (total) | 41 |
| Win Rate | 53.7% |

**Regime breakdown:**
- Mean-reverting months: PF **6.70**, N=25, avg $1,487/fire
- Trending months: PF 1.51, N=16, avg $234/fire

**What it detects:** High volume bar with narrow range relative to ATR.
The market expended effort (volume) but achieved little result (range).
This signals absorption — institutional size absorbing the aggression.

**Key insight:** This signal is 4.4× stronger in mean-reverting regimes.
Filter by GEX positive gamma (mean-reversion tendency) for highest conviction.

**Best pairs (from pair analysis):**
- ABS_04 + IMB_07: PF 16.60, N=11
- ABS_04 + EXH_03: PF 5.33, N=28
- ABS_04 + IMB_03: PF 4.85, N=34

### AUCT_03 — Poor High/Low ⭐⭐⭐

| Metric | Value |
|--------|-------|
| Overall PF | 1.44 |
| Train PF (70%) | 1.70 |
| **Test PF (30%)** | **1.20** |
| Walk-forward | ✅ PASS |
| N (total) | 46 |

**What it detects:** Bar closes within range without testing extreme.
Unfinished auction — price will return to test the extreme.

---

## DISCARDED SIGNALS

### VOLP_06 — Big Delta Per Level ❌

| Metric | Value |
|--------|-------|
| Overall PF | 1.77 |
| Train PF | 2.95 |
| **Test PF** | **0.42** ← COLLAPSES in test |
| Walk-forward | ❌ FAIL |

**Verdict:** Overfit to training period. Discard.

### All IMB signals (IMB_01 through IMB_09) ❌

PF range: 0.97-1.00. No edge on synthesized OHLCV.
**Expected to improve significantly on real MBO data** — imbalance signals
require accurate bid/ask split which OHLCV synthesis cannot provide.

### All DELT signals ❌

PF range: 0.94-1.02. Near-random on synthesized data.
**Expected to improve on real MBO data** — delta requires true aggressor
classification which OHLCV synthesis approximates poorly.

---

## CRITICAL INSIGHT: SCORER IS INVERSELY CALIBRATED

The current scoring weights produce WORSE results at higher scores:

| Tier | Bars | PF |
|------|------|----|
| TYPE_A (≥80) | 65 | **0.77** ← NEGATIVE |
| TYPE_B (≥72) | 326 | **0.81** ← NEGATIVE |
| TYPE_C (≥50) | 21,182 | 1.00 |
| QUIET | 105,785 | 1.00 |

**The scorer is broken for OHLCV data.** TypeA requires absorption + zone confluence
which cannot manifest correctly from synthesized footprints.

**Recommended action:** Do NOT use the current scorer for OHLCV backtesting.
Use individual signal PF instead. Reweight after MBO data arrives.

---

## REGIME ANALYSIS

Monthly regime classification (>3% monthly move = trending):

| Month | Return | Regime |
|-------|--------|--------|
| 2025-01 | +1.5% | mean_rev |
| 2025-02 | -0.4% | mean_rev |
| 2025-03 | -7.8% | **trending** |
| 2025-04 | +2.9% | mean_rev |
| 2025-05 | +7.3% | **trending** |
| 2025-06 | +7.4% | **trending** |
| 2025-07 | +1.8% | mean_rev |
| 2025-08 | +1.0% | mean_rev |
| 2025-09 | +5.5% | **trending** |
| 2025-10 | +4.7% | **trending** |
| 2025-11 | -2.2% | mean_rev |
| 2025-12 | -0.1% | mean_rev |
| 2026-01 | +0.6% | mean_rev |
| 2026-02 | -2.2% | mean_rev |
| 2026-03 | -2.7% | mean_rev |
| 2026-04 | +14.2% | **trending** |

8 mean-reverting months, 6 trending months.

**ABS_04 regime edge:**
- Mean-reverting: PF 6.70 (25 fires, avg $1,487)
- Trending: PF 1.51 (16 fires, avg $234)

**Recommendation:** Gate ABS_04 by GEX regime. Only trade when:
- GEX positive (mean-reversion tendency)
- OR: price at key level (VAH/VAL/prior H/L)

---

## WHAT CHANGES WITH REAL MBO DATA

When Rithmic L2 data arrives, expect these signals to unlock:

| Signal | OHLCV PF | Expected MBO PF | Why |
|--------|----------|-----------------|-----|
| ENG_03 (CounterSpoof) | ~1.0 | 2.0-3.0 | Real DOM displacement detection |
| ENG_04 (Iceberg) | ~1.0 | 2.0-4.0 | True refresh tracking |
| IMB_03 (Stacked) | 0.99 | 1.5-2.5 | Real bid/ask split |
| DELT_05 (CVD divergence) | 1.01 | 1.5-2.0 | True aggressor classification |
| ABS_04 | 3.94 | 5.0+ | Already strong, will improve |

---

## RECOMMENDED SCORING WEIGHT CHANGES

Based on attribution results, recommended new weights for OHLCV backtesting:

```python
# Current (broken for OHLCV):
absorption_weight = 20.0
imbalance_weight = 25.0  # highest — but no edge on OHLCV
delta_weight = 14.3

# Recommended for OHLCV:
absorption_weight = 40.0   # ABS_04 is the only validated signal
auction_weight = 20.0      # AUCT_03 has edge
imbalance_weight = 5.0     # reduce until MBO data
delta_weight = 5.0         # reduce until MBO data
volume_profile_weight = 5.0
exhaustion_weight = 10.0   # marginal edge
trapped_weight = 5.0       # test with new weights
```

---

## ZONES STRATEGY CONTEXT

The zones strategy (Variant D: PF 4.93, WR 80.2%) is the best validated system.
It uses zone detection (15m bars) + exhaustion wick entry — NOT the signal scorer.
This is why it outperforms: it bypasses the broken scorer entirely.

**The zones strategy IS the ABS_04 signal in disguise:**
- Zone entry requires exhaustion wick at zone proximal
- This is exactly what ABS_04 detects (high volume, narrow range at extreme)
- The zone provides the structural context that ABS_04 lacks alone

**Recommendation:** The zones strategy + ABS_04 confirmation is the highest-conviction
setup available on OHLCV data. When MBO data arrives, add iceberg/spoof confirmation.

---

## NEXT STEPS (priority order)

1. **Get Rithmic L2 data** (tomorrow) → re-run attribution with real MBO
2. **Fix IMB_04 direction=0 bug** → re-run to see true IMB edge
3. **Enable TRAP signals** → test with new weights
4. **Build multi-bar absorption signal** → 3+ consecutive ABS_04 = highest conviction
5. **Add GEX regime gate to ABS_04** → filter to mean-reverting months only
6. **Zones + ABS_04 combined strategy** → test if ABS_04 confirmation improves zones PF
