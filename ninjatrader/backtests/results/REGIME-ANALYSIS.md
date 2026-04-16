# DEEP6 Regime-Conditional Performance Analysis

Sessions analyzed: 50 total (10 per regime × 5 regimes)  
Configs: Conservative (threshold=80, TYPE_A) · Aggressive (threshold=50, TYPE_B)  
Instrument: NQ futures · Tick=$0.25 · $5/tick · 1 contract  

---

## 1. Cross-Regime Comparison — Conservative Config

| Regime | Trades | WinRate | PF | Sharpe | AvgPnL | MaxDD | BestSignal | WorstSignal |
|--------|-------:|--------:|---:|-------:|-------:|------:|:-----------|:------------|
| trend\_up | 99 | 84% | 28.95 | 18.78 | $+104 | $70 | exhaustion | imbalance |
| trend\_down | 121 | 81% | 9.37 | 13.60 | $+71 | $168 | imbalance | exhaustion |
| ranging | 116 | 98% | 385.96 | 70.10 | $+207 | $37 | volume_profile | volume_profile |
| volatile | 0 | 0% | 0.00 | 0.00 | $+0 | $0 | N/A | N/A |
| slow\_grind | 0 | 0% | 0.00 | 0.00 | $+0 | $0 | N/A | N/A |

## 2. Cross-Regime Comparison — Aggressive Config

| Regime | Trades | WinRate | PF | Sharpe | AvgPnL | MaxDD | BestSignal | WorstSignal |
|--------|-------:|--------:|---:|-------:|-------:|------:|:-----------|:------------|
| trend\_up | 127 | 87% | 28.64 | 19.43 | $+108 | $116 | exhaustion | absorption |
| trend\_down | 121 | 82% | 9.54 | 13.72 | $+72 | $168 | imbalance | exhaustion |
| ranging | 116 | 98% | 385.83 | 68.93 | $+207 | $37 | volume_profile | volume_profile |
| volatile | 63 | 67% | 1.89 | 5.07 | $+78 | $309 | imbalance | absorption |
| slow\_grind | 87 | 37% | 0.39 | -5.95 | $-14 | $1345 | absorption | volume_profile |

---

## 3. Per-Regime Deep Dives

### Trend Up

**Conservative** (threshold=55.0, tier=TYPE_C)  
- Trades: 99 | Win Rate: 84% | PF: 28.95 | Sharpe: 18.78  
- Total P&L: $+10320 | Avg P&L/trade: $+104 | Max DD: $70  
- Best trade: $+230 | Worst trade: $-70  
- Max consec wins: 13 | Max consec losses: 2  
- Avg bars between trades: 39.4  
- Signal distribution: volume_profile=99, absorption=99, exhaustion=88, imbalance=27  
- Time-of-day breakdown:  
  - opening_30min: 7 trades | WR=100% | Total=$+1041  
  - mid_day: 33 trades | WR=91% | Total=$+3175  
  - closing_60min: 19 trades | WR=53% | Total=$+412  
  - other: 40 trades | WR=90% | Total=$+5692  

**Aggressive** (threshold=25.0, tier=QUIET)  
- Trades: 127 | Win Rate: 87% | PF: 28.64 | Sharpe: 19.43  
- Total P&L: $+13768 | Avg P&L/trade: $+108 | Max DD: $116  
- Best trade: $+230 | Worst trade: $-108  
- Max consec wins: 26 | Max consec losses: 2  
- Avg bars between trades: 30.7  
- Signal distribution: absorption=127, volume_profile=127, exhaustion=52, imbalance=16  
- Time-of-day breakdown:  
  - opening_30min: 10 trades | WR=90% | Total=$+1168  
  - mid_day: 39 trades | WR=87% | Total=$+3993  
  - closing_60min: 26 trades | WR=73% | Total=$+689  
  - other: 52 trades | WR=92% | Total=$+7919  

### Trend Down

**Conservative** (threshold=55.0, tier=TYPE_C)  
- Trades: 121 | Win Rate: 81% | PF: 9.37 | Sharpe: 13.60  
- Total P&L: $+8621 | Avg P&L/trade: $+71 | Max DD: $168  
- Best trade: $+219 | Worst trade: $-113  
- Max consec wins: 20 | Max consec losses: 3  
- Avg bars between trades: 32.2  
- Signal distribution: exhaustion=121, absorption=121, volume_profile=121, imbalance=13  
- Time-of-day breakdown:  
  - opening_30min: 10 trades | WR=70% | Total=$+715  
  - mid_day: 37 trades | WR=76% | Total=$+2186  
  - closing_60min: 27 trades | WR=78% | Total=$+842  
  - other: 47 trades | WR=89% | Total=$+4878  

**Aggressive** (threshold=25.0, tier=QUIET)  
- Trades: 121 | Win Rate: 82% | PF: 9.54 | Sharpe: 13.72  
- Total P&L: $+8676 | Avg P&L/trade: $+72 | Max DD: $168  
- Best trade: $+219 | Worst trade: $-113  
- Max consec wins: 20 | Max consec losses: 3  
- Avg bars between trades: 32.2  
- Signal distribution: exhaustion=121, absorption=121, volume_profile=121, imbalance=10  
- Time-of-day breakdown:  
  - opening_30min: 10 trades | WR=70% | Total=$+715  
  - mid_day: 37 trades | WR=78% | Total=$+2251  
  - closing_60min: 27 trades | WR=78% | Total=$+832  
  - other: 47 trades | WR=89% | Total=$+4878  

### Ranging

**Conservative** (threshold=55.0, tier=TYPE_C)  
- Trades: 116 | Win Rate: 98% | PF: 385.96 | Sharpe: 70.10  
- Total P&L: $+24068 | Avg P&L/trade: $+207 | Max DD: $37  
- Best trade: $+253 | Worst trade: $-37  
- Max consec wins: 58 | Max consec losses: 1  
- Avg bars between trades: 33.6  
- Signal distribution: volume_profile=116, absorption=116, imbalance=116, delta=1  
- Time-of-day breakdown:  
  - opening_30min: 10 trades | WR=100% | Total=$+2254  
  - mid_day: 35 trades | WR=100% | Total=$+7222  
  - closing_60min: 18 trades | WR=89% | Total=$+2953  
  - other: 53 trades | WR=100% | Total=$+11640  

**Aggressive** (threshold=25.0, tier=QUIET)  
- Trades: 116 | Win Rate: 98% | PF: 385.83 | Sharpe: 68.93  
- Total P&L: $+24060 | Avg P&L/trade: $+207 | Max DD: $37  
- Best trade: $+253 | Worst trade: $-37  
- Max consec wins: 58 | Max consec losses: 1  
- Avg bars between trades: 33.6  
- Signal distribution: volume_profile=116, absorption=116, imbalance=116, delta=1  
- Time-of-day breakdown:  
  - opening_30min: 10 trades | WR=100% | Total=$+2254  
  - mid_day: 36 trades | WR=100% | Total=$+7427  
  - closing_60min: 18 trades | WR=89% | Total=$+2957  
  - other: 52 trades | WR=100% | Total=$+11422  

### Volatile

**Conservative** (threshold=55.0, tier=TYPE_C)  
- Trades: 0 | Win Rate: 0% | PF: 0.00 | Sharpe: 0.00  
- Total P&L: $+0 | Avg P&L/trade: $+0 | Max DD: $0  
- Best trade: $+0 | Worst trade: $+0  
- Max consec wins: 0 | Max consec losses: 0  
- Avg bars between trades: 0.0  
- Time-of-day breakdown:  
  - opening_30min: 0 trades | WR=— | Total=$+0  
  - mid_day: 0 trades | WR=— | Total=$+0  
  - closing_60min: 0 trades | WR=— | Total=$+0  
  - other: 0 trades | WR=— | Total=$+0  

**Aggressive** (threshold=25.0, tier=QUIET)  
- Trades: 63 | Win Rate: 67% | PF: 1.89 | Sharpe: 5.07  
- Total P&L: $+4937 | Avg P&L/trade: $+78 | Max DD: $309  
- Best trade: $+410 | Worst trade: $-309  
- Max consec wins: 2 | Max consec losses: 1  
- Avg bars between trades: 61.9  
- Signal distribution: exhaustion=63, imbalance=42, absorption=21, volume_profile=21, delta=21  
- Time-of-day breakdown:  
  - opening_30min: 0 trades | WR=— | Total=$+0  
  - mid_day: 12 trades | WR=67% | Total=$+902  
  - closing_60min: 0 trades | WR=— | Total=$+0  
  - other: 51 trades | WR=67% | Total=$+4035  

### Slow Grind

**Conservative** (threshold=55.0, tier=TYPE_C)  
- Trades: 0 | Win Rate: 0% | PF: 0.00 | Sharpe: 0.00  
- Total P&L: $+0 | Avg P&L/trade: $+0 | Max DD: $0  
- Best trade: $+0 | Worst trade: $+0  
- Max consec wins: 0 | Max consec losses: 0  
- Avg bars between trades: 0.0  
- Time-of-day breakdown:  
  - opening_30min: 0 trades | WR=— | Total=$+0  
  - mid_day: 0 trades | WR=— | Total=$+0  
  - closing_60min: 0 trades | WR=— | Total=$+0  
  - other: 0 trades | WR=— | Total=$+0  

**Aggressive** (threshold=25.0, tier=QUIET)  
- Trades: 87 | Win Rate: 37% | PF: 0.39 | Sharpe: -5.95  
- Total P&L: $-1248 | Avg P&L/trade: $-14 | Max DD: $1345  
- Best trade: $+76 | Worst trade: $-109  
- Max consec wins: 4 | Max consec losses: 9  
- Avg bars between trades: 44.8  
- Signal distribution: absorption=87, volume_profile=55  
- Time-of-day breakdown:  
  - opening_30min: 7 trades | WR=43% | Total=$-71  
  - mid_day: 26 trades | WR=23% | Total=$-609  
  - closing_60min: 11 trades | WR=64% | Total=$-43  
  - other: 43 trades | WR=37% | Total=$-525  

---

## 4. Regime Transition Analysis (Conservative)

Does performance degrade at regime boundaries?

| Transition | Before Trades | Before P&L | Before WR | After Trades | After P&L | After WR |
|:-----------|:-------------:|:----------:|:---------:|:------------:|:---------:|:--------:|
| trend_up → trend_down | 8 | $+902 | 88% | 12 | $+527 | 83% |
| trend_down → ranging | 12 | $+530 | 58% | 11 | $+2459 | 100% |
| ranging → volatile | 12 | $+2464 | 100% | 0 | $+0 | 0% |
| volatile → slow_grind | 0 | $+0 | 0% | 0 | $+0 | 0% |

**Drawdown clustering:** Transitions where the system incurs its worst per-session
P&L are flagged in the table above. Check transitions into `volatile` and `slow_grind`
for the highest drawdown risk.

---

## 5. Time-of-Day Summary (Conservative, All Regimes Combined)

| Regime | Opening 30min | Mid-Day | Closing 60min | Other |
|:-------|:-------------|:--------|:--------------|:------|
| trend_up | 7T / $+1041 | 33T / $+3175 | 19T / $+412 | 40T / $+5692 |
| trend_down | 10T / $+715 | 37T / $+2186 | 27T / $+842 | 47T / $+4878 |
| ranging | 10T / $+2254 | 35T / $+7222 | 18T / $+2953 | 53T / $+11640 |
| volatile | 0T / $+0 | 0T / $+0 | 0T / $+0 | 0T / $+0 |
| slow_grind | 0T / $+0 | 0T / $+0 | 0T / $+0 | 0T / $+0 |

---

## 6. Recommendations

Based on the regime analysis:  

- **Trend Up: TRADE AGGRESSIVELY** — strong win rate (84%) and profit factor (28.95). Lower threshold to TYPE_B.  
- **Trend Down: TRADE AGGRESSIVELY** — strong win rate (81%) and profit factor (9.37). Lower threshold to TYPE_B.  
- **Ranging: TRADE AGGRESSIVELY** — strong win rate (98%) and profit factor (385.96). Lower threshold to TYPE_B.  
- **Volatile: SIT OUT** — insufficient signal frequency (n=0) or negative P&L. Consider disabling auto-execution in this regime.  
- **Slow Grind: SIT OUT** — insufficient signal frequency (n=0) or negative P&L. Consider disabling auto-execution in this regime.  

**Top performing regime:** Ranging ($+24068 conservative)  
**Worst performing regime:** Volatile ($+0 conservative)  

**Adaptive threshold suggestion:**  
- `trend_up` / `trend_down`: lower to TYPE_B in first 30 bars (opening range trend extension)  
- `ranging`: require zone proximity (zoneScore ≥ 50) for any entry, raise to TYPE_A only  
- `volatile`: ABS/EXH + zone required; reject DELT-only entries (chase filter)  
- `slow_grind`: block all entries — signal frequency too low to cover commissions  

**Midday block** (bars 240-330, 10:30-13:00 ET) is already enforced by the scorer.  
Recommend extending to 10:00-13:30 ET in `ranging` and `slow_grind` regimes.  

---

*Generated by deep6/backtest/regime_analysis.py*