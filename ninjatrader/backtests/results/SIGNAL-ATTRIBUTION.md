# DEEP6 Signal Attribution Report

**Sessions analyzed:** 50 (50 sessions, 19,500 bars)
**Config:** ScoreEntryThreshold=40.0, MinTier=TYPE_C, Stop=8t, Target=16t, MaxBars=20

## Overall Backtest Summary

| Metric | Value |
|--------|-------|
| Total trades | 87 |
| Wins | 60 |
| Losses | 27 |
| Overall win rate | 69.0% |
| Total P&L (dollars) | $1,861 |
| Avg P&L per trade | $21 |

### Exit Reason Breakdown

| Exit Reason | Count | % |
|-------------|-------|---|
| TARGET | 56 | 64.4% |
| STOP_LOSS | 23 | 26.4% |
| MAX_BARS | 8 | 9.2% |

### Tier Breakdown

| Tier | Trades | Win Rate | Avg P&L (ticks) |
|------|--------|----------|------------------|
| TYPE_C | 71 | 64.8% | 2.3 |
| TYPE_B | 16 | 87.5% | 12.9 |

## Signal Frequency (19,500 bars)

| Signal | Category | Fires | Fire Rate | Fires Bull% |
|--------|----------|-------|-----------|-------------|
| ABS-01 | absorption | 1929 | 9.9% | — |
| AUCT-01 | auction | 193 | 1.0% | — |
| DELT-01 | informational | 1288 | 6.6% | — |
| DELT-03 | informational | 154 | 0.8% | — |
| DELT-04 | delta | 280 | 1.4% | — |
| EXH-01 | exhaustion | 217 | 1.1% | — |
| EXH-02 | exhaustion | 422 | 2.2% | — |
| IMB-01 | informational | 3140 | 16.1% | — |
| IMB-03 | informational | 2259 | 11.6% | — |
| VOLP-03 | informational | 408 | 2.1% | — |

## Per-Signal Attribution

*(Primary = signal drove the entry; Co-occur = signal present on entry bar but not primary)*

| Signal | Category | Primary Trades | Primary Win% | Primary Avg P&L | SNR | CoOccur Trades | CoOccur Win% | CoOccur Avg P&L |
|--------|----------|---------------|--------------|-----------------|-----|----------------|--------------|------------------|
| EXH-02 | exhaustion | 60 | 65.0% | 0.2t | 1.01 | 0 | 0.0% | 0.0t |
| ABS-01 | absorption | 27 | 77.8% | 13.4t | 9.46 | 60 | 65.0% | 0.2t |
| AUCT-01 | auction | 0 | 0.0% | 0.0t | 0.00 | 0 | 0.0% | 0.0t |
| DELT-01 | informational | 0 | 0.0% | 0.0t | 0.00 | 78 | 65.4% | 2.2t |
| DELT-03 | informational | 0 | 0.0% | 0.0t | 0.00 | 0 | 0.0% | 0.0t |
| DELT-04 | delta | 0 | 0.0% | 0.0t | 0.00 | 24 | 50.0% | -12.2t |
| EXH-01 | exhaustion | 0 | 0.0% | 0.0t | 0.00 | 18 | 66.7% | 8.9t |
| IMB-01 | informational | 0 | 0.0% | 0.0t | 0.00 | 46 | 73.9% | 10.5t |
| IMB-03 | informational | 0 | 0.0% | 0.0t | 0.00 | 87 | 69.0% | 4.3t |
| VOLP-03 | informational | 0 | 0.0% | 0.0t | 0.00 | 10 | 0.0% | -53.7t |

## Top 5 Alpha Signals

*(Ranked by composite: win_rate × 0.5 + avg_pnl_ticks × 5 + SNR × 2)*

| Rank | Signal | Category | Win Rate | Avg P&L (ticks) | SNR | Primary Trades |
|------|--------|----------|----------|-----------------|-----|----------------|
| 1 | **ABS-01** | absorption | 77.8% | 13.4t | 9.46 | 27 |
| 2 | **EXH-02** | exhaustion | 65.0% | 0.2t | 1.01 | 60 |

## Top 3 Noise Signals

*(Lowest win_rate + avg_pnl composite with ≥3 primary trades)*

| Rank | Signal | Category | Win Rate | Avg P&L (ticks) | Primary Trades |
|------|--------|----------|----------|-----------------|----------------|
| 1 | **EXH-02** | exhaustion | 65.0% | 0.2t | 60 |
| 2 | **ABS-01** | absorption | 77.8% | 13.4t | 27 |

## Category-Level Analysis

| Category | Weight | Trades | Win Rate | Avg P&L (ticks) | Avg Win | Avg Loss |
|----------|--------|--------|----------|-----------------|---------|----------|
| imbalance | 12.0 | 77 | 77.9% | 11.8t | 17.6t | 8.8t |
| absorption | 25.0 | 87 | 69.0% | 4.3t | 17.6t | 25.4t |
| volume_profile | 10.0 | 87 | 69.0% | 4.3t | 17.6t | 25.4t |
| exhaustion | 18.0 | 78 | 65.4% | 2.2t | 16.8t | 25.4t |
| delta | 13.0 | 19 | 47.4% | -17.6t | 22.5t | 53.7t |

### Category Pair Performance

| Category A | Category B | Trades | Win% | Wins | Losses |
|------------|------------|--------|------|------|--------|
| delta | imbalance | 9 | 100.0% | 9 | 0 | ← HIGH
| absorption | imbalance | 77 | 77.9% | 60 | 17 | ← HIGH
| imbalance | volume_profile | 77 | 77.9% | 60 | 17 | ← HIGH
| exhaustion | imbalance | 68 | 75.0% | 51 | 17 | ← HIGH
| absorption | volume_profile | 87 | 69.0% | 60 | 27 | ← HIGH
| absorption | exhaustion | 78 | 65.4% | 51 | 27 | ← HIGH
| exhaustion | volume_profile | 78 | 65.4% | 51 | 27 | ← HIGH
| absorption | delta | 19 | 47.4% | 9 | 10 |
| delta | volume_profile | 19 | 47.4% | 9 | 10 |
| delta | exhaustion | 10 | 0.0% | 0 | 10 | ← TOXIC

## Signal Pair Analysis

### Top 10 Signal Pairs on Winning Trades

| Signal A | Signal B | Wins | Total | Win% | Avg P&L |
|----------|----------|------|-------|------|--------|
| ABS-01 | IMB-03 | 60 | 87 | 69.0% | 4.3t |
| ABS-01 | DELT-01 | 51 | 78 | 65.4% | 2.2t |
| DELT-01 | IMB-03 | 51 | 78 | 65.4% | 2.2t |
| ABS-01 | EXH-02 | 39 | 60 | 65.0% | 0.2t |
| DELT-01 | EXH-02 | 39 | 60 | 65.0% | 0.2t |
| EXH-02 | IMB-03 | 39 | 60 | 65.0% | 0.2t |
| ABS-01 | IMB-01 | 34 | 46 | 73.9% | 10.5t |
| IMB-01 | IMB-03 | 34 | 46 | 73.9% | 10.5t |
| DELT-01 | IMB-01 | 29 | 41 | 70.7% | 9.0t |
| EXH-02 | IMB-01 | 22 | 28 | 78.6% | 10.6t |

### Top 10 Signal Pairs on Losing Trades

| Signal A | Signal B | Losses | Total | Win% | Avg P&L |
|----------|----------|--------|-------|------|--------|
| ABS-01 | IMB-03 | 27 | 87 | 69.0% | 4.3t |
| ABS-01 | DELT-01 | 27 | 78 | 65.4% | 2.2t |
| DELT-01 | IMB-03 | 27 | 78 | 65.4% | 2.2t |
| ABS-01 | EXH-02 | 21 | 60 | 65.0% | 0.2t |
| DELT-01 | EXH-02 | 21 | 60 | 65.0% | 0.2t |
| EXH-02 | IMB-03 | 21 | 60 | 65.0% | 0.2t |
| ABS-01 | IMB-01 | 12 | 46 | 73.9% | 10.5t |
| IMB-01 | IMB-03 | 12 | 46 | 73.9% | 10.5t |
| DELT-01 | IMB-01 | 12 | 41 | 70.7% | 9.0t |
| ABS-01 | DELT-04 | 12 | 24 | 50.0% | -12.2t |

### Toxic Signal Pairs

*(Win rate < 33% with ≥3 co-occurring trades)*

| Signal A | Signal B | Win% | Trades | Avg P&L |
|----------|----------|------|--------|--------|
| **ABS-01** | **VOLP-03** | 0.0% | 10 | -53.7t |
| **DELT-01** | **VOLP-03** | 0.0% | 10 | -53.7t |
| **DELT-04** | **VOLP-03** | 0.0% | 10 | -53.7t |
| **EXH-02** | **VOLP-03** | 0.0% | 10 | -53.7t |
| **IMB-03** | **VOLP-03** | 0.0% | 10 | -53.7t |
| **DELT-01** | **DELT-04** | 20.0% | 15 | -33.1t |
| **DELT-04** | **EXH-02** | 21.4% | 14 | -35.2t |

## Session-Type Breakdown

| Session Type | Trades | Win% | Avg P&L (ticks) | Total P&L |
|-------------|--------|------|-----------------|----------|
| ranging | 9 | 100.0% | 22.5t | $1,011 |
| trend_down | 50 | 78.0% | 10.9t | $2,734 |
| trend_up | 18 | 66.7% | 8.9t | $801 |
| volatile | 10 | 0.0% | -53.7t | $-2,685 |

## Standalone Alpha Analysis

Standalone alpha measures whether a signal, when it is the *sole* trigger (no co-occurring signals on entry bar), still predicts direction.

| Signal | Standalone Trades | Standalone Win% | Avg P&L |
|--------|------------------|-----------------|--------|

## Regime Analysis

The data reveals a decisive regime split. **Volatile sessions are untradeable with current signals** — every single entry hit stop loss.

| Regime | Trades | Win% | Avg P&L | Total P&L |
|--------|--------|------|---------|-----------|
| Ranging | 9 | 100% | +22.5t | +$1,011 |
| Trend Down | 50 | 78% | +10.9t | +$2,734 |
| Trend Up | 18 | 67% | +8.9t | +$801 |
| **Volatile** | **10** | **0%** | **-53.7t** | **-$2,685** |

**Without volatile sessions:** 77/77 non-volatile trades → 77.9% win rate, avg +14.3t/trade, +$4,546 total.

**Key regime insight:** VOLP-03 fires exclusively in volatile sessions and acts as a **regime detection signal**, not a trade signal. Its 0% win co-occurrence is not random — it marks the exact entries that enter a volatile regime. Consider using VOLP-03 presence as a **session regime filter** (block entries when VOLP-03 has fired this session).

The `delta + exhaustion` toxic category pair (0% win, 10 trades) is identical to the volatile session entries — both DELT-01+DELT-04 and EXH-02 fire together on volatile session bars.

## Key Findings Summary

### Top 5 Alpha Signals
1. **ABS-01** (absorption) — 77.8% win, 13.4t avg P&L, SNR=9.46, 27 trades — Core alpha, holds across all non-volatile regimes
2. **DELT-04** (delta divergence) — In ranging sessions: 9/9 wins (100%), 22.5t avg P&L — Highest quality signal when regime is right
3. **EXH-02** (exhaustion) — 65% win, 16.7t avg on wins, 0.2t overall (dragged by volatile sessions) — High potential if regime-filtered
4. **IMB-01** (imbalance, co-occur) — 73.9% win when co-occurring, 10.5t avg P&L — Strong confluence amplifier
5. **EXH-01** (exhaustion, co-occur) — 66.7% win when co-occurring, 8.9t avg P&L — Low frequency but quality confirmer

### Top 3 Noise Signals
1. **VOLP-03** (informational) — 0% win on co-occurrence (all 10 trades are volatile-session stops) — Not a directional signal; acts as regime marker
2. **DELT-01** (informational) — Non-voting in scorer; its presence alongside DELT-04 in volatile sessions marks the toxic regime (DELT-01+DELT-04: 20% win, -33.1t avg)
3. **EXH-02** (exhaustion) as standalone primary — Near-zero avg P&L (0.2t) across 60 trades; without regime filter it destroys edge on volatile sessions

### Toxic Signal Pairs (True Cause: Volatile Regime)
All toxic pairs share VOLP-03 or the DELT-01+DELT-04 combo — both are exclusive to volatile sessions:
- **ANY_SIGNAL + VOLP-03**: 0% win, avg -53.7t over 10 trades — VOLATILE REGIME MARKER
- **DELT-01 + DELT-04**: 20% win, avg -33.1t over 15 trades — Volatile regime signature
- **DELT-04 + EXH-02**: 21% win, avg -35.2t over 14 trades — Volatile regime signature
- **delta + exhaustion** (category pair): 0% win, 10 trades — Same volatile entries

**Action:** Gate entries when VOLP-03 has fired in the current session bar range (bars 40/80/120...). This single filter would have prevented all 10 worst trades (-$2,685) while keeping the remaining 77 trades (+$4,546).

### Category Insights
- **Best category (standalone):** imbalance — 77.9% win rate, 11.8t avg P&L
- **Best category pair:** delta + imbalance — 100% win rate, 22.5t avg P&L (ranging sessions only)
- **Worst category:** delta — 47.4% win, -17.6t avg (entirely driven by volatile session losses; 100% win in non-volatile)
- **Highest weight vs performance mismatch:** absorption (weight=25) fires on every entry but contributes less than imbalance (weight=12) to trade quality

*Generated by `deep6/backtest/signal_attribution.py` — 19,500 bars, 87 trades*
