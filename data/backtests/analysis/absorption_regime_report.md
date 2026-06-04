# Absorption Regime Analysis

Source: `/mnt/c/Users/Tea/DEEP6/data/backtests/signal_events.csv`

## Baseline

- N: 899
- WR 5b: 46.16%
- WR 15b: 46.38%
- Avg return 5b: -3.45 ticks

## Findings
- **volatility_regime**: best `mid_vol` (16.60t, 50.17% WR5) vs worst `high_vol` (-21.48t, 44.15% WR5).
- **price_vs_sma**: best `below_sma50` (4.63t, 45.63% WR5) vs worst `above_sma50` (-14.84t, 46.92% WR5).
- **trend_alignment**: best `against_trend` (4.09t, 46.69% WR5) vs worst `with_trend` (-8.19t, 45.83% WR5).
- **session_half**: best `afternoon_1230_1600` (-2.31t, 46.37% WR5) vs worst `morning_0930_1230` (-7.55t, 45.41% WR5).
- **vwap_position**: best `mid_vwap` (18.91t, 46.15% WR5) vs worst `far_vwap` (-16.28t, 47.00% WR5).
- **prior_move_bucket**: best `large_gt150` (-0.91t, 48.34% WR5) vs worst `medium_50_150` (-7.28t, 44.56% WR5).
- **prior_delta_relation**: best `opposite_to_signal` (24.02t, 49.84% WR5) vs worst `same_as_signal` (-18.62t, 44.04% WR5).
- **prior_delta_sign**: best `negative` (13.20t, 46.20% WR5) vs worst `positive` (-22.11t, 45.99% WR5).

## Volatility regime (ATR20 terciles)

| Bucket | N | WR 5b | WR 15b | Avg Ret 5b (ticks) | Δ WR 5b | Δ WR 15b | Δ Avg Ret |
|---|---:|---:|---:|---:|---:|---:|---:|
| mid_vol | 297 | 50.17% | 50.51% | 16.60 | +4.01pp | +4.12pp | +20.05t |
| low_vol | 300 | 43.67% | 43.67% | -6.96 | -2.50pp | -2.72pp | -3.51t |
| high_vol | 299 | 44.15% | 44.82% | -21.48 | -2.02pp | -1.57pp | -18.03t |

## Trend regime proxy (price vs SMA50)

| Bucket | N | WR 5b | WR 15b | Avg Ret 5b (ticks) | Δ WR 5b | Δ WR 15b | Δ Avg Ret |
|---|---:|---:|---:|---:|---:|---:|---:|
| below_sma50 | 526 | 45.63% | 47.91% | 4.63 | -0.54pp | +1.52pp | +8.08t |
| above_sma50 | 373 | 46.92% | 44.24% | -14.84 | +0.75pp | -2.15pp | -11.39t |

## Trend alignment (with-trend vs contrarian)

| Bucket | N | WR 5b | WR 15b | Avg Ret 5b (ticks) | Δ WR 5b | Δ WR 15b | Δ Avg Ret |
|---|---:|---:|---:|---:|---:|---:|---:|
| against_trend | 347 | 46.69% | 48.99% | 4.09 | +0.52pp | +2.61pp | +7.54t |
| with_trend | 552 | 45.83% | 44.75% | -8.19 | -0.33pp | -1.64pp | -4.74t |

## Session type

| Bucket | N | WR 5b | WR 15b | Avg Ret 5b (ticks) | Δ WR 5b | Δ WR 15b | Δ Avg Ret |
|---|---:|---:|---:|---:|---:|---:|---:|
| afternoon_1230_1600 | 703 | 46.37% | 47.08% | -2.31 | +0.21pp | +0.70pp | +1.14t |
| morning_0930_1230 | 196 | 45.41% | 43.88% | -7.55 | -0.75pp | -2.51pp | -4.10t |

## Volume profile position proxy (VWAP distance terciles)

| Bucket | N | WR 5b | WR 15b | Avg Ret 5b (ticks) | Δ WR 5b | Δ WR 15b | Δ Avg Ret |
|---|---:|---:|---:|---:|---:|---:|---:|
| mid_vwap | 299 | 46.15% | 49.50% | 18.91 | -0.01pp | +3.11pp | +22.36t |
| near_vwap | 300 | 45.33% | 44.67% | -12.90 | -0.83pp | -1.72pp | -9.45t |
| far_vwap | 300 | 47.00% | 45.00% | -16.28 | +0.84pp | -1.38pp | -12.83t |

## Prior move magnitude (30 bars)

| Bucket | N | WR 5b | WR 15b | Avg Ret 5b (ticks) | Δ WR 5b | Δ WR 15b | Δ Avg Ret |
|---|---:|---:|---:|---:|---:|---:|---:|
| large_gt150 | 422 | 48.34% | 45.97% | -0.91 | +2.18pp | -0.41pp | +2.54t |
| small_lt50 | 185 | 43.24% | 42.16% | -5.89 | -2.92pp | -4.22pp | -2.44t |
| medium_50_150 | 285 | 44.56% | 49.47% | -7.28 | -1.60pp | +3.09pp | -3.83t |

## Delta accumulation vs signal direction

| Bucket | N | WR 5b | WR 15b | Avg Ret 5b (ticks) | Δ WR 5b | Δ WR 15b | Δ Avg Ret |
|---|---:|---:|---:|---:|---:|---:|---:|
| opposite_to_signal | 319 | 49.84% | 47.02% | 24.02 | +3.68pp | +0.64pp | +27.47t |
| same_as_signal | 579 | 44.04% | 46.11% | -18.62 | -2.12pp | -0.27pp | -15.17t |

## Raw prior delta sign

| Bucket | N | WR 5b | WR 15b | Avg Ret 5b (ticks) | Δ WR 5b | Δ WR 15b | Δ Avg Ret |
|---|---:|---:|---:|---:|---:|---:|---:|
| negative | 474 | 46.20% | 48.95% | 13.20 | +0.04pp | +2.56pp | +16.65t |
| positive | 424 | 45.99% | 43.63% | -22.11 | -0.17pp | -2.75pp | -18.66t |
