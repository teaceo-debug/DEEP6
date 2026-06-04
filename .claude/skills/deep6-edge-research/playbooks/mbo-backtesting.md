# Playbook: MBO Backtesting (Databento)

## Goal
When Databento MBO data is available, replace synthesized OHLCV footprints
with true order-book data and re-measure all signal edges.

## Prerequisites
1. `DATABENTO_API_KEY=db-...` in `.env`
2. `databento` Python SDK installed: `pip install databento` (already done)
3. Target date range selected (3 weeks recommended to start)

## Step 1: Download MBO data

```bash
# Cost check first (free, no charge)
python -c "
import databento as db, os
c = db.Historical(os.environ['DATABENTO_API_KEY'])
cost = c.metadata.get_cost(dataset='GLBX.MDP3', symbols=['NQ.c.0'],
    stype_in='continuous', schema='mbo', start='2026-04-28', end='2026-05-19')
size = c.metadata.get_billable_size(dataset='GLBX.MDP3', symbols=['NQ.c.0'],
    stype_in='continuous', schema='mbo', start='2026-04-28', end='2026-05-19')
print(f'Cost: \${cost:.2f}  Size: {size/1e9:.2f} GB billable')
"

# Download (will stream to disk)
python scripts/databento/download_nq_mbo.py \
    --start 2026-04-28 \
    --end 2026-05-19 \
    --dir data/databento/nq_mbo

# Output: data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-28_2026-05-19.dbn.zst
# Manifest updated: data/databento/nq_mbo/manifest.json
```

## Step 2: Verify the download

```python
import databento as db

store = db.DBNStore.from_file("data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-28_2026-05-19.dbn.zst")
df = store.to_df()
print(f"Records: {len(df):,}")
print(f"Actions: {df['action'].value_counts()}")
print(f"First: {df.index[0]}  Last: {df.index[-1]}")
print(df.head(5)[['action', 'side', 'price', 'size', 'order_id']].to_string())
```

Expected action distribution:
- A (add): 60-70% of records
- C (cancel): 25-35%
- M (modify): 5-10%
- T (trade): 2-5%
- F (fill): rare
- R (clear): very rare

## Step 3: Run MBO replay through signal pipeline

The existing `deep6/backtest/mbo_adapter.py` converts Databento MBO events
to the `on_tick` / `on_dom` callback shape that the signal pipeline expects.

```python
import asyncio
import databento as db
from pathlib import Path
from deep6.backtest.mbo_adapter import MBOAdapter
from deep6v2.signals.registry import DetectorRegistry

DBN_PATH = "data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-28_2026-05-19.dbn.zst"

async def replay_mbo():
    registry = DetectorRegistry.create_default()
    adapter = MBOAdapter(path=DBN_PATH)

    async def on_tick(price, size, aggressor):
        # Tick received — route to bar builder
        pass

    async def on_dom(bid_levels, ask_levels):
        # DOM snapshot — route to depth-consuming detectors
        registry.on_depth_from_levels(bid_levels, ask_levels)  # if method exists

    await adapter.run(on_tick, on_dom)

asyncio.run(replay_mbo())
```

## Step 4: Build MBO signal collector

When MBO data is available, create `scripts/signal_collect_mbo.py` that:
1. Reads the .dbn.zst file
2. Feeds events through MBOAdapter (on_tick + on_dom)
3. Accumulates FootprintBars at bar close (1-min)
4. Runs DetectorRegistry on each completed bar
5. Records signal fires with true footprint data

Key differences vs OHLCV synthesis:
- `bar.delta` is accurate (true aggressor from MBO side field)
- `bar.bid_volumes` and `bar.ask_volumes` are real, not estimated
- DOM depth signals (ENG_02, ENG_03, ENG_04) receive actual order book state
- CounterSpoof (ENG_03) detects real DOM disappearance events

## Step 5: Compare OHLCV vs MBO results

After running both collections:
```python
import pandas as pd

ohlcv = pd.read_csv("data/backtests/signal_events.csv")
mbo   = pd.read_csv("data/backtests/signal_events_mbo.csv")

for sig_id in ohlcv["signal_id"].unique():
    o_grp = ohlcv[ohlcv["signal_id"] == sig_id]["pnl_5b"].dropna()
    m_grp = mbo[mbo["signal_id"] == sig_id]["pnl_5b"].dropna()
    if len(o_grp) < 5 or len(m_grp) < 5:
        continue
    o_pf = o_grp[o_grp > 0].sum() / (-o_grp[o_grp <= 0].sum() or 1)
    m_pf = m_grp[m_grp > 0].sum() / (-m_grp[m_grp <= 0].sum() or 1)
    print(f"{sig_id:<12}  OHLCV PF={o_pf:.2f} N={len(o_grp):4d}  |  MBO PF={m_pf:.2f} N={len(m_grp):4d}")
```

## Databento MBO schema reference

```
Field        Type    Description
─────────────────────────────────────────────────
ts_event     int64   Nanoseconds since epoch (exchange timestamp)
action       char    A=add, C=cancel, M=modify, T=trade, F=fill, R=clear
side         char    A=ask-side order, B=bid-side order, N=none
price        int64   Fixed-point (divide by 1e9 for dollars)
size         uint32  Order size
order_id     uint64  Exchange order ID (key for lifecycle tracking)
ts_recv      int64   Local receipt timestamp
sequence     uint32  Message sequence number (for gap detection)
```

### Aggressor mapping (CRITICAL — Phase 13-01 footgun)
- `action='T'` and `side='A'` → trade on ask side → **BUY aggressor** (buyer lifted ask)
- `action='T'` and `side='B'` → trade on bid side → **SELL aggressor** (seller hit bid)
- Inverting this flips every delta signal. Unit tests pin this mapping.

## Rithmic L2 data (when available)

When Rithmic L2 data plan activates (details pending):
- Use `async-rithmic` DepthByOrder proto for live MBO
- Fields: `exchange_order_id`, `update_type` (NEW/CHANGE/DELETE), `depth_order_priority`
- Rithmic native MBO is the live equivalent of Databento historical MBO
- Cross-market plan Task 1 verifies this: `cross_market/tests/test_rithmic_mbo_validation.py`

The signal pipeline is identical for both — only the connector changes.
