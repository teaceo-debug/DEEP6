# Backtest Spec — TIER 3 Follow-Signal (Gray-Tier Direction Trade)

**Hypothesis:** TIER 3 signals (currently filtered out as low-conviction "gray" signals) are predictive when traded mechanically in the direction of the underlying absorption / exhaustion detection.

## Trigger
- `SignalTier == TYPE_C` (the gray tier — currently `ShowTier3Dots = false` by default)
- AND one of these underlying detections fires on the same bar:
  - Absorption (any of 4 variants: Classic, Passive, StoppingVolume, EffortVsResult)
  - Exhaustion (any of 6 variants + delta gate)

## Direction
- `+1 LONG` if absorption is bullish (e.g. lower-wick absorption defending bid) OR exhaustion is bearish (sell exhaustion at low)
- `-1 SHORT` if absorption is bearish (upper-wick) OR exhaustion is bullish (buy exhaustion at high)

## Entry
- Market order, next bar open

## Run all three R:R configurations
| Variant | Stop | Target | R:R |
|---|---|---|---|
| **A — Aggressive** | 8 pts (32 ticks) | 15 pts (60 ticks) | 1.875:1 |
| **B — Balanced**   | 10 pts (40 ticks) | 20 pts (80 ticks) | 2:1 |
| **C — Tight stop** | 5 pts (20 ticks) | 17.5 pts (70 ticks) | 3.5:1 |

## Hold
- Max 30 bars (1-min) → time-stop at market

## Data
- `data/backtests/nq_3mo_1m.dbn.zst` (3 months NQ 1-min bars)
- Replay sessions in `data/backtests/replay_full_5sessions.duckdb`
- Reference scripts: `scripts/backtest_3mo_full.py`, `scripts/backtest_r1_finetune.py`, `scripts/backtest_r3_stress.py`

## Output deliverables
For each variant (A/B/C):
1. **Trade list CSV** → `data/backtests/tier3_followsignal_{A|B|C}_trades.csv`
2. **Equity curve PNG** → `data/backtests/tier3_followsignal_{A|B|C}_equity.png`
3. **Summary metrics** → trade count, hit rate, avg R, expectancy, total points, Sharpe, max drawdown, longest losing streak

## Comparison report
Single markdown summary at `.planning/backtest-tier3-followsignal-results.md`:
- Side-by-side metrics table for A/B/C
- Best variant + recommendation
- Split breakdown: absorption-only trades vs exhaustion-only trades vs combined
- Time-of-day distribution of winners vs losers
- Push to GitHub for phone viewing

## Implementation notes for next session
- Build `scripts/backtest_tier3_followsignal.py` — single script, runs all 3 variants in one pass
- Reuse existing fixture replay loop from `scripts/backtest_3mo_full.py`
- Filter scorer output by `SignalTier == TYPE_C` BEFORE the existing tier-A/B logic vetoes them
- Load DEEP6 detector registry the same way `DEEP6Strategy.cs` does (registry has the same path AddOns/DEEP6/Detectors/)

## Status
- [x] Spec locked (this file)
- [ ] Pause + new session
- [ ] Build script
- [ ] Run 3 variants
- [ ] Push results to GitHub
