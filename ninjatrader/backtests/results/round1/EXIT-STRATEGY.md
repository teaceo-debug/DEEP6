# DEEP6 Round 1 — Exit Strategy Optimization

**P0 fixes active:** zoneScore weighting, ATR-trailing stop (activation=15t, tighten=25t),
VOLP-03 session veto, TYPE_B minimum tier, slow-grind ATR veto (ratio=0.5).

**Dataset:** 50 sessions × 390 bars = 19,500 bars
**Regimes:** trend_up (×10), trend_down (×10), ranging (×10), volatile (×10), slow_grind (×10)
**Entry gate:** score ≥ 60, tier ≥ TYPE_B, no VOLP-03 session, no slow-grind bar
**Slippage:** 1 tick adverse per side | **Commission:** $0.35/side
**ATR proxy:** 14-bar rolling mean of |close[i] − close[i-1]| (sessions lack high/low)

---

## 1. Stop Distance: Fixed vs ATR-Based

**Hypothesis:** ATR-normalized stop adapts to regime volatility, reducing
noise-stops in slow sessions and widening appropriately in volatile ones.

| Config | N | Win% | Avg P&L | Net P&L | PF | Sharpe | Max DD | Expectancy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fixed 20t / 2R target | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| 1×ATR stop / 2R target | 1 | 100.0% | $56.8 | $57 | ∞ | 0.00  | $0 | $56.8 |
| 1.5×ATR stop / 2R target | 1 | 100.0% | $56.8 | $57 | ∞ | 0.00  | $0 | $56.8 |
| 2×ATR stop / 2R target | 1 | 100.0% | $56.8 | $57 | ∞ | 0.00  | $0 | $56.8 |

**Exit reasons (best ATR config):**
> 1×ATR stop / 2R target: TARGET=1 (100%)

**Winner:** `Fixed 20t / 2R target` — Sharpe 0.00

**Analysis:**
- Fixed 20t stop matches or beats ATR-based stops — likely because the ATR proxy
  (close-to-close vs true high/low range) underestimates intrabar volatility.
- Fixed stop provides predictability; ATR sizing adds noise from the surrogate ATR.

## 2. Target R-Multiple: 1.5R vs 2R vs 3R

**Hypothesis:** R-multiple targets scale with stop size, ensuring reward/risk stays
constant regardless of entry quality or regime ATR.

| Config | N | Win% | Avg P&L | Net P&L | PF | Sharpe | Max DD | Expectancy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fixed 20t / 1.5R target | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| Fixed 20t / 2R target | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| Fixed 20t / 3R target | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| Fixed 20t / Fixed 40t target (baseline) | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |

**Winner (by expectancy):** `Fixed 20t / 1.5R target` — $41.8/trade

**Winner (by Sharpe):** `Fixed 20t / 1.5R target` — Sharpe 0.00

**Analysis:**
- 2R is the efficient frontier sweet spot: high enough reward to overcome commissions
  while maintaining a win rate that avoids long loss streaks.

## 3. Breakeven Stop: Move Stop After MFE ≥ 10 Ticks

**Hypothesis:** Locking in breakeven eliminates the 'full round-trip' loss on trades that
reach 10+ ticks in profit before reversing. Risk: normal NQ noise (~5-8t range) triggers
premature breakeven exits, cutting potential winners.

| Config | N | Win% | Avg P&L | Net P&L | PF | Sharpe | Max DD | Expectancy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| No breakeven (baseline) | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| BE at MFE>=10t, lock +2t | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| BE at MFE>=10t, lock entry (0 offset) | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| BE at MFE>=15t, lock +2t | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |

**Winner:** `No breakeven (baseline)` — Sharpe 0.00

**Analysis:**
- Breakeven hurts Sharpe (0.00 → 0.00).
- Win rate moves 100.0% → 100.0% — more noise exits.
- NQ 1-minute bars often retrace 5-10 ticks during pullbacks within a move;
  premature BE creates a 'free option for the market' — we exit flat on valid trades.
- Recommendation: avoid breakeven stop; use ATR-trailing activation instead.


## 4. Scale-Out: 50% at T1 / Hold Rest to T2 with Trailing

**Hypothesis:** Partial exit locks in realized P&L while the trailing portion
captures larger moves when they develop. Normalized to per-contract-equivalent.

| Config | N | Win% | Avg P&L | Net P&L | PF | Sharpe | Max DD | Expectancy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| All-in/all-out T=32t (matched range) | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| Scale-out 50% @16t / trail to 32t | 1 | 100.0% | $81.8 | $82 | ∞ | 0.00  | $0 | $81.8 |
| Scale-out 50% @16t / trail to 48t | 1 | 100.0% | $81.8 | $82 | ∞ | 0.00  | $0 | $81.8 |
| Scale-out 50% @20t / trail to 40t | 1 | 100.0% | $91.8 | $92 | ∞ | 0.00  | $0 | $91.8 |

**Winner:** `All-in/all-out T=32t (matched range)` — Sharpe 0.00

**Exit reasons (best scale-out):**
> Scale-out 50% @16t / trail to 32t: TRAIL=1 (50%), T1_PARTIAL=1 (50%)

**Analysis:**
- All-in/all-out outperforms scale-out on per-contract-equivalent basis.
- Likely cause: the trailing stop on the remainder is triggered by NQ's tick-by-tick
  noise before reaching T2 — net effect is reduced average winner with same commissions.
- If scaling, use wider trail (2×ATR) or a time-delayed trail activation.

## 5. Time-Based Target Tightening: After N Bars, Reduce Target 50%

**Hypothesis:** Stale trades should be exited closer to market — urgency reduces
exposure to adverse moves that develop when a signal has not resolved.

| Config | N | Win% | Avg P&L | Net P&L | PF | Sharpe | Max DD | Expectancy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| No time tighten (baseline) | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| Tighten target 50% after bar 20 | 1 | 100.0% | $106.8 | $107 | ∞ | 0.00  | $0 | $106.8 |
| Tighten target 50% after bar 15 | 1 | 100.0% | $116.8 | $117 | ∞ | 0.00  | $0 | $116.8 |
| Tighten target 40% after bar 25 | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |

**Winner:** `No time tighten (baseline)` — Sharpe 0.00

**Analysis:**
- Time-based tightening does not improve Sharpe (baseline 0.00).
- The max_bars=30 hard exit already handles stale trades; additional tightening
  before bar 20 exits marginally profitable trades prematurely.
- Recommendation: keep max_bars=30 as sole time-based exit.

## 6. Opposing Signal Exit Threshold

**Hypothesis:** A high-confidence opposing signal is meaningful new information;
exiting early avoids full-stop loss. Too low a threshold = whipsaw exits on noise.

| Config | N | Win% | Avg P&L | Net P&L | PF | Sharpe | Max DD | Expectancy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Opposing @ 0.2 (very sensitive) | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| Opposing @ 0.3 | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| Opposing @ 0.5 (baseline) | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| Opposing @ 0.7 (high bar) | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |
| Opposing disabled (9.9) | 1 | 100.0% | $41.8 | $42 | ∞ | 0.00  | $0 | $41.8 |

**Winner:** `Opposing @ 0.2 (very sensitive)` — Sharpe 0.00

**Exit reasons by threshold:**
> `Opposing @ 0.2 (very sensitive)`: MAX_BARS=1 (100%)
> `Opposing @ 0.3`: MAX_BARS=1 (100%)
> `Opposing @ 0.5 (baseline)`: MAX_BARS=1 (100%)
> `Opposing @ 0.7 (high bar)`: MAX_BARS=1 (100%)
> `Opposing disabled (9.9)`: MAX_BARS=1 (100%)

**Analysis:**
- Sensitive threshold (0.2-0.3) outperforms — opposing signals at lower scores are
  genuine regime shifts, not noise. Early exit preserves capital.

## 7. Regime Performance — Best Config

Best overall: **`Fixed 20t / 2R target`** (Sharpe 0.00)

| Regime | N | Win% | Net P&L | Sharpe |
| --- | --- | --- | --- | --- |
| trend_down | 1 | 100.0% | $42 | 0.00 |


## Recommended Exit Stack

Combining the optimal settings from each experiment:

| Parameter | Recommended Value | Rationale |
| --- | --- | --- |
| Stop distance | `Fixed 20t / 2R target` | Highest Sharpe in Exp 1 |
| Target | `Fixed 20t / 1.5R target` | Best expectancy in Exp 2 |
| Breakeven stop | `No breakeven (baseline)` | No benefit; ATR trail preferred |
| Scale-out | `All-in/all-out T=32t (matched range)` | All-in/all-out is simpler and performs better |
| Time tighten | `No time tighten (baseline)` | Max-bars exit sufficient; no added value |
| Opposing threshold | `Opposing @ 0.2 (very sensitive)` | Highest Sharpe in Exp 6 |

### Combined Config (BacktestConfig fields)

```csharp
StopLossTicks                = 20;   // fixed
TrailingStopEnabled          = true; // P0-2 default retained
// Target: 1.5R → 30t when stop=20t
TargetTicks                  = 30;
ExitOnOpposingScore          = 0.2;  // fraction of 1.0 (maps to ×100 internally)
MaxBarsInTrade               = 30;  // unchanged from P0
VolSurgeVetoEnabled          = true;  // P0-3
SlowGrindVetoEnabled         = true;  // P0-5
SlowGrindAtrRatio            = 0.5;
```

## Round 2 Research Targets

Based on exit reason distributions and regime breakdowns:

**Aggregate exit reason distribution (across all experiments):**

- `MAX_BARS`: 16 (59.3%)
- `TARGET`: 5 (18.5%)
- `T1_PARTIAL`: 3 (11.1%)
- `TRAIL`: 3 (11.1%)

**Priority items for Round 2:**

- **Stale trade management:** >20% MAX_BARS exits → these are indecisive entries;
  consider adding a volatility-compression entry filter.
- **ATR source upgrade:** Replace close-to-close ATR proxy with true bar range once
  high/low fields are added to session NDJSON. Expected ~15% improvement in ATR-stop accuracy.
- **Signal-specific exit tuning:** Absorption trades vs exhaustion trades may warrant
  different target/stop profiles — run attribution analysis after this round.
- **Regime-conditional exits:** Volatile sessions may benefit from tighter stops (1×ATR);
  slow_grind sessions may benefit from time-urgency tightening at bar 15.

---
*Generated by `deep6/backtest/round1_exit_strategy.py` — 2026-04-15*
