# DEEP6 Round 1 — Entry Timing Optimization

**Date**: 2026-04-15
**Sessions**: 50 (10 × trend_up, 10 × trend_down, 10 × ranging, 10 × volatile, 10 × slow_grind)
**Analysis mode**: RELAXED (score≥50, any tier, VOLP-03 veto OFF) — see Data Note below
**Exit params**: SL=20t, TP=40t, MaxBars=30, Slippage=1t (P0-fixed)

> **Data Note — Synthetic VOLP-03 Artifact**: All 50 synthetic sessions contain a VOLP-03
> volume-surge signal every 40 bars. With the P0 strict config (TYPE_B+ only, VOLP-03 veto ON)
> this produces only 1 trade(s) across the entire corpus — statistically useless for
> entry-timing analysis. The scorer also produces only 18 TYPE_B signals across 50 sessions.
> This analysis uses RELAXED mode (score≥50, any directional tier, VOLP-03 veto OFF) to
> generate 191 trades with full time-of-day coverage. The timing patterns found here
> apply to signal quality regardless of tier cutoff; re-validate against live TYPE_B+ signals
> when real session data is available from Rithmic or Databento.

---

## Strict P0 Baseline (reference only — 1 trade total)

| Metric | Value |
|---|---|
| Config | score≥60, tier≥TYPE_B, VOLP-03 veto ON |
| Total trades | 1 |
| Win rate | 100.0% |
| Avg PnL/trade | 8.50 ticks |
| Profit factor | 0.00 |

## Relaxed Baseline (used for all analyses below)

| Metric | Value |
|---|---|
| Config | score≥50, any tier, VOLP-03 veto OFF |
| Total trades | 191 |
| Win rate | 93.7% |
| Avg PnL/trade | 32.65 ticks |
| Profit factor | 53.61 |
| Net PnL | 6235 ticks ($31177) |

---

## Analysis 1: Bar-of-Day Distribution (30-Min Windows)

**Method**: Relaxed-mode trades tagged by `barsSinceOpen // 30` at signal bar.
1-min bars; window 0 = 0930-1000 ET, window 12 = 1530-1600 ET.
Midday block (bars 240-330 = ~1400-1430) is hard-blocked by scorer.

| window | count | win_rate | avg_pnl_ticks | profit_factor | net_ticks |
|---|---|---|---|---|---|
| 0930-1000 | 18 | 0.889 | 31.68 | 22.62 | 570.2 |
| 1000-1030 | 24 | 0.958 | 34.61 | 72.93 | 830.7 |
| 1030-1100 | 14 | 0.929 | 34.16 | 338.88 | 478.3 |
| 1100-1130 | 23 | 0.957 | 31.44 | 88.62 | 723.2 |
| 1130-1200 | 15 | 0.867 | 29.42 | 19.96 | 441.2 |
| 1200-1230 | 21 | 0.952 | 33.31 | 60.07 | 699.5 |
| 1230-1300 | 18 | 1.0 | 39.17 | inf | 705.1 |
| 1300-1330 | 19 | 0.895 | 27.6 | 20.64 | 524.4 |
| 1330-1400 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 1400-1430 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 1430-1500 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 1500-1530 | 25 | 1.0 | 36.34 | inf | 908.5 |
| 1530-1600 | 14 | 0.857 | 25.31 | 39.91 | 354.4 |

**Best window**: 1230-1300 — avg 39.17t, WR 100.0%, 18 trades
**Worst window**: 1530-1600 — avg 25.31t, WR 85.7%, 14 trades

**Recommendation**: Blackout 1530-1600 (25.31t avg). Windows with avg_pnl_ticks < 0 and count ≥ 3 are candidates for blackout.

---

## Analysis 2: Confirmation Filter (Entry Delay)

**Method**: Delay entry N bars after signal fires. Enter at bar-N close (pending expires after MaxBars=30).
All runs use relaxed mode (score≥50, any tier, no VOLP-03 veto).

| delay_bars | total_trades | win_rate | avg_pnl_ticks | profit_factor | net_ticks |
|---|---|---|---|---|---|
| 0.0 | 191.0 | 0.937 | 32.65 | 53.61 | 6235.4 |
| 1.0 | 190.0 | 0.921 | 31.86 | 39.31 | 6053.0 |
| 2.0 | 189.0 | 0.915 | 31.79 | 35.34 | 6009.0 |

**Recommendation**: No delay benefit — immediate entry wins. Note: delayed entries lose some fills (price gaps away) — net ticks reflects this.

---

## Analysis 3: Signal Confluence (Multi-Signal Entries)

**Method**: Count signals in trade direction on the signal bar. Bucket by count.
Hypothesis: more simultaneous signals = stronger confirmation = higher win rate.

| signal_count_bucket | total_trades | win_rate | avg_pnl_ticks | profit_factor | net_ticks |
|---|---|---|---|---|---|
| 1 signal | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 2 signals | 77 | 0.974 | 33.49 | 76.01 | 2579.0 |
| 3 signals | 96 | 0.896 | 32.4 | 37.97 | 3110.3 |
| 4+ signals | 18 | 1.0 | 30.33 | inf | 546.0 |
| 3+ signals | 114 | 0.912 | 32.07 | 44.46 | 3656.3 |

**Verdict**: 3+ signals HURT avg PnL by -1.4 ticks vs 1-2 signals (may indicate chasing)

---

## Analysis 4: Pullback Entry (Retrace from Signal Bar Close)

**Method**: After signal fires on bar N, wait for price to retrace N ticks from bar N close.
Entry triggers on first bar where close retraces target amount (pending expires after MaxBars=30).

| retrace_ticks | total_trades | win_rate | avg_pnl_ticks | profit_factor | net_ticks | fill_rate |
|---|---|---|---|---|---|---|
| 0.0 | 191 | 0.937 | 32.65 | 53.61 | 6235.4 | 100% (immediate) |
| 2.0 | 145 | 0.91 | 33.06 | 39.65 | 4793.0 | 145 trades triggered |
| 3.0 | 134 | 0.918 | 34.21 | 43.44 | 4584.0 | 134 trades triggered |
| 4.0 | 120 | 0.942 | 34.42 | 40.34 | 4131.0 | 120 trades triggered |

**Recommendation**: 4-tick retrace improves avg PnL by +1.77t. Larger retraces reduce fill rate but may improve per-trade quality.

---

## Cross-Analysis: Time Window × Entry Delay

**Top 10 window+delay combos by avg PnL (min 3 trades)**

| window | delay_bars | count | total_trades | win_rate | avg_pnl_ticks | profit_factor | net_ticks |
|---|---|---|---|---|---|---|---|
| 1230-1300 | 2 | 17 | 17 | 1.0 | 40.0 | inf | 680.0 |
| 1230-1300 | 1 | 17 | 17 | 1.0 | 39.71 | inf | 675.0 |
| 1230-1300 | 0 | 18 | 18 | 1.0 | 39.17 | inf | 705.1 |
| 1500-1530 | 0 | 25 | 25 | 1.0 | 36.34 | inf | 908.5 |
| 1000-1030 | 0 | 24 | 24 | 0.958 | 34.61 | 72.93 | 830.7 |
| 1500-1530 | 1 | 25 | 25 | 1.0 | 34.44 | inf | 861.0 |
| 1030-1100 | 1 | 13 | 13 | 0.923 | 34.23 | 56.62 | 445.0 |
| 1030-1100 | 0 | 14 | 14 | 0.929 | 34.16 | 338.88 | 478.3 |
| 1030-1100 | 2 | 13 | 13 | 0.923 | 34.0 | 22.05 | 442.0 |
| 1500-1530 | 2 | 25 | 25 | 1.0 | 33.8 | inf | 845.0 |

**Avg PnL pivot (ticks) — rows=window, cols=delay bars**

| window | delay_0bar | delay_1bar | delay_2bar |
|---|---|---|---|
| 0930-1000 | 31.68 | 31.22 | 29.5 |
| 1000-1030 | 34.61 | 32.5 | 32.88 |
| 1030-1100 | 34.16 | 34.23 | 34.0 |
| 1100-1130 | 31.44 | 30.91 | 30.43 |
| 1130-1200 | 29.42 | 28.4 | 29.79 |
| 1200-1230 | 33.31 | 31.36 | 32.05 |
| 1230-1300 | 39.17 | 39.71 | 40.0 |
| 1300-1330 | 27.6 | 29.21 | 28.42 |
| 1500-1530 | 36.34 | 34.44 | 33.8 |
| 1530-1600 | 25.31 | 24.86 | 25.71 |

---

## Parameter Recommendations

| Parameter | Current | Recommended | Rationale |
|---|---|---|---|
| Entry delay | 0 bars | 0 bars | No delay benefit — immediate entry wins |
| Retrace filter | 0 ticks | 4 ticks | 4-tick retrace improves avg PnL by +1.77t |
| Time-of-day filter | None | Blackout 1530-1600 (25.31t avg) | See Analysis 1 |
| Confluence gate | ≥1 signal | ≥1 signal sufficient (no benefit from requiring more) | 3+ signals HURT avg PnL by -1.4 ticks vs 1-2 signals (may indicate chasing) |

---

## Top Finding

**Time-of-day spread: 13.9 ticks peak-to-trough across 30-min windows — best window is 1230-1300 (39.17t avg), worst is 1530-1600 (25.31t avg)**

- Time-of-day spread: 13.9 ticks peak-to-trough across 30-min windows — best window is 1230-1300 (39.17t avg), worst is 1530-1600 (25.31t avg)
- Pullback retrace: 4-tick retrace improves avg PnL by +1.77t
- Confirmation delay: No delay benefit — immediate entry wins
- Signal confluence: 3+ signals HURT avg PnL by -1.4 ticks vs 1-2 signals (may indicate chasing)

---
_Generated by `deep6/backtest/round1_entry_timing.py` — Round 1 Entry Timing Optimization_
