# Playbook: Hypothesis Testing

## Goal
Test a specific edge hypothesis on the 1yr NQ dataset.
Each hypothesis should be falsifiable — it must have clear pass/fail criteria.

## Template: State the hypothesis first

```
HYPOTHESIS: [Signal X] has positive expected value when [condition Y]
DATASET: data/backtests/signal_events.csv (1yr NQ 1-min, Jan 2025-Apr 2026)
PRIMARY METRIC: Profit Factor ≥ 1.3 at 5-bar forward (falsifiable threshold)
SECONDARY: Win rate, N ≥ 30, holds in 70/30 walk-forward split
NULL HYPOTHESIS: Signal fires randomly (PF = 1.0)
```

## Common hypothesis patterns

### H1: Signal works better at specific time of day
```python
import pandas as pd
ev = pd.read_csv("data/backtests/signal_events.csv")
ev["hour"] = pd.to_datetime(ev["bar_ts"], utc=True).dt.tz_convert("America/New_York").dt.hour

# Compute P&L from forward closes
closes = ev["bar_close"].astype(float)
fwd = ev["fwd_close_5b"].astype(float)
move = fwd - closes
dirs = ev["direction"].map({"1": 1.0, "-1": -1.0, "BULLISH": 1.0, "BEARISH": -1.0}).fillna(0)
ev["pnl"] = dirs * move * 20.0 - 0.70

sig = ev[ev["signal_id"] == "ABS_01"].dropna(subset=["pnl"])
for h, grp in sig.groupby("hour"):
    pnls = grp["pnl"].values
    wins = (pnls > 0).sum()
    pf = pnls[pnls > 0].sum() / (-pnls[pnls <= 0].sum() or 1e-9)
    print(f"  Hour {h:02d}h: N={len(pnls):3d} WR={wins/len(pnls)*100:.0f}% PF={pf:.2f}")
```

### H2: Signal works better with score confirmation
```python
for tier in ["TYPE_C", "TYPE_B", "TYPE_A"]:
    grp = sig[sig["score_tier"] == tier]["pnl"].dropna()
    if len(grp) < 5: continue
    pf = grp[grp > 0].sum() / (-grp[grp <= 0].sum() or 1e-9)
    print(f"  Tier {tier}: N={len(grp)} PF={pf:.2f}")
```

### H3: Signal pair is synergistic
```python
# Find bars where BOTH ABS_01 AND DELT_05 fired same direction
ev_abs  = ev[ev["signal_id"] == "ABS_01"].groupby(["session_date","bar_index","direction"])
ev_delt = ev[ev["signal_id"] == "DELT_05"].groupby(["session_date","bar_index","direction"])

# Merge on bar
abs_keys  = set(zip(ev[ev["signal_id"]=="ABS_01"]["session_date"], ev[ev["signal_id"]=="ABS_01"]["bar_index"], ev[ev["signal_id"]=="ABS_01"]["direction"]))
delt_keys = set(zip(ev[ev["signal_id"]=="DELT_05"]["session_date"], ev[ev["signal_id"]=="DELT_05"]["bar_index"], ev[ev["signal_id"]=="DELT_05"]["direction"]))
both_keys = abs_keys & delt_keys

pair_pnl = ev[(ev["signal_id"]=="ABS_01") & 
              ev[["session_date","bar_index","direction"]].apply(tuple, axis=1).isin(both_keys)]["pnl"]
solo_pnl = ev[(ev["signal_id"]=="ABS_01") & 
              ~ev[["session_date","bar_index","direction"]].apply(tuple, axis=1).isin(delt_keys)]["pnl"]

print(f"ABS_01 alone:        PF={solo_pnl[solo_pnl>0].sum() / (-solo_pnl[solo_pnl<=0].sum() or 1):.2f}  N={len(solo_pnl)}")
print(f"ABS_01 + DELT_05:    PF={pair_pnl[pair_pnl>0].sum() / (-pair_pnl[pair_pnl<=0].sum() or 1):.2f}  N={len(pair_pnl)}")
```

### H4: Signal edge varies by regime
```python
# Regime: trending = abs(monthly return) > 3%, mean-reverting = else
ev["month"] = pd.to_datetime(ev["session_date"]).dt.to_period("M")

monthly_closes = (pd.read_csv("data/backtests/nq_1yr_1m.csv",
    usecols=["ts_event","close"], parse_dates=["ts_event"])
    .assign(month=lambda df: pd.to_datetime(df["ts_event"], utc=True).dt.to_period("M"))
    .groupby("month")["close"].last())

monthly_ret = monthly_closes.pct_change().abs()
trending_months = set(str(m) for m in monthly_ret[monthly_ret > 0.03].index)

ev["regime"] = ev["month"].astype(str).map(
    lambda m: "trending" if m in trending_months else "mean_reverting")

for regime, grp in sig.groupby("regime"):
    pnls = grp["pnl"].dropna()
    pf = pnls[pnls > 0].sum() / (-pnls[pnls <= 0].sum() or 1e-9)
    print(f"  {regime}: N={len(pnls)} PF={pf:.2f}")
```

### H5: Walk-forward holds
```python
dates = pd.to_datetime(sig["session_date"])
cutoff_70 = dates.quantile(0.70)
cutoff_80 = dates.quantile(0.80)

splits = [
    ("Train (70%)", dates <= cutoff_70),
    ("Test (30%)",  dates > cutoff_70),
    ("Recent (20%)", dates > cutoff_80),
]
for label, mask in splits:
    pnls = sig[mask]["pnl"].dropna()
    if len(pnls) < 5: continue
    pf = pnls[pnls > 0].sum() / (-pnls[pnls <= 0].sum() or 1e-9)
    print(f"  {label}: N={len(pnls)} PF={pf:.2f}")
```

## Pass criteria for any hypothesis

A hypothesis passes if:
1. PF ≥ 1.3 in train set
2. PF ≥ 1.1 in test set (some degradation is normal)
3. N ≥ 20 in test set (enough to be meaningful)
4. Time-of-day breakdown shows consistent positive expectancy (not driven by 1 session)
5. No single day accounts for >20% of net P&L

A hypothesis fails if:
- PF < 1.0 in test set (overfit to train)
- N < 10 in test set (insufficient data)
- Single session/day dominates results
- Edge disappears by 10-bar forward (noise, not structure)

## Reporting results

After testing, write a summary:
```
HYPOTHESIS: [X]
RESULT: PASS / FAIL / MARGINAL
TRAIN: PF=X.XX, N=NNN, WR=XX%
TEST:  PF=X.XX, N=NNN, WR=XX%
NOTES: [what you found, edge conditions, failure modes]
RECOMMENDATION: [include in strategy / reweight / discard / test more]
```

Save to: `data/backtests/analysis/hypothesis_[name].txt`
