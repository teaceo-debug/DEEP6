# Playbook: Signal Attribution

## Goal
Determine which of the 44 DEEP6 signals have real edge on NQ futures,
which work in combination, and at what time of day they're strongest.

## Prerequisites
- `data/backtests/nq_1yr_1m.csv` exists (Jan 2025 → Apr 2026)
- deep6v2 package is importable: `python -c "import deep6v2; print('ok')"`

## Step-by-step

### 1. Check if signal_events.csv already exists
```bash
ls -la data/backtests/signal_events.csv
# If < 5MB or missing → re-collect
# If > 20MB → likely valid, skip to step 3
```

### 2. Collect signal fires (once, ~3 min)
```bash
python scripts/signal_collect.py
# Streams incrementally, safe to interrupt and restart
# Output: data/backtests/signal_events.csv
```

### 3. Run base attribution (30 sec)
```bash
python scripts/signal_analyze.py
# Output: data/backtests/analysis/attribution_5b.txt
#         data/backtests/analysis/signal_stats.csv
#         data/backtests/analysis/signal_equity_curves.png
```

### 4. Category drill-downs (parallel)
```bash
# Each takes 5-15 seconds. Run in parallel with different agents.
python scripts/signal_analyze.py --category absorption --window 5
python scripts/signal_analyze.py --category exhaustion --window 5
python scripts/signal_analyze.py --category imbalance --window 10
python scripts/signal_analyze.py --category delta --window 5
python scripts/signal_analyze.py --category volume_profile --window 10
python scripts/signal_analyze.py --category auction --window 15
python scripts/signal_analyze.py --signal ENG_02,ENG_03,ENG_04,ENG_05
```

### 5. Specific signal hypothesis
```bash
# Test a specific hypothesis: does ABS_01 work better with DELT_05?
python scripts/signal_analyze.py --signal ABS_01,ABS_02,DELT_05 --window 5
```

### 6. Walk-forward validation of best signals
For any signal with PF ≥ 1.4, N ≥ 30, validate on time-split:
```python
import pandas as pd
ev = pd.read_csv("data/backtests/signal_events.csv")
ev["session_date"] = pd.to_datetime(ev["session_date"])

# 70/30 time split
cutoff = ev["session_date"].quantile(0.70)
train = ev[ev["session_date"] <= cutoff]
test  = ev[ev["session_date"] > cutoff]

for sig_id in ["ABS_01", "EXH_02", "IMB_03"]:  # replace with your top signals
    for label, df in [("TRAIN", train), ("TEST", test)]:
        grp = df[df["signal_id"] == sig_id]["pnl_5b"].dropna()
        if len(grp) < 5: continue
        wins = (grp > 0).sum()
        pf = grp[grp > 0].sum() / (-grp[grp <= 0].sum() or 1e-9)
        print(f"{sig_id} [{label}] N={len(grp)} WR={wins/len(grp)*100:.0f}% PF={pf:.2f}")
```

## Interpreting Results

### PF reference table
| PF | Interpretation | Action |
|----|----------------|--------|
| >2.0 | Exceptional edge | Prioritize, investigate deeply |
| 1.5-2.0 | Strong edge | Include in strategy |
| 1.2-1.5 | Moderate edge | Include with confirmation |
| 1.0-1.2 | Marginal | Only use in strong combos |
| <1.0 | Negative alpha | Remove from scorer or reweight to 0 |

### Common findings to watch for
- **EXH_01-03** often have high PF but low N (zero/thin prints are rare by definition)
- **IMB** signals tend to have high fire rate — check for overfit on synthetic data
- **ABS_01** should have strongest edge — if not, check synthesizer bias
- **DELT_05** (CVD divergence) often has the most consistent time-of-day edge
- **ENG_03** (counter-spoof) has low N on OHLCV; will be much richer on MBO data

### What changes with MBO data
Re-run collection after downloading Databento MBO:
```bash
# (requires mbo_replay_engine.py to feed MBOAdapter events through pipeline)
python scripts/signal_collect.py --data-source mbo --mbo-path data/databento/nq_mbo/raw_dbn/
```
Expected improvements on MBO vs OHLCV:
- ENG_03 (counter-spoof): N increases 10-100x, PF likely 2x better
- ENG_04 (iceberg): refresh tracking becomes accurate
- ABS signals: delta accuracy improves (true aggressor side, not synthesized)
