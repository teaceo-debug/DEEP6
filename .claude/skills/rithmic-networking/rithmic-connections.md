# Rithmic Connection Reference — DEEP6

Quick-reference for all connection details. For full docs see `knowledge.md`.

---

## Active Account

| Field | Value |
|-------|-------|
| **Provider** | Rithmic Direct (Paper Trading) |
| **Username** | `michael@fitsells.com` |
| **Password** | `Madmoney1986!` |
| **System Name** | `Rithmic Paper Trading` |
| **Gateway** | `wss://rprotocol.rithmic.com:443` (Chicago) |
| **App Name** | `migo:DEEP6-sim` (conformance-approved) |
| **R|Trader Account** | 101651 (Gonzalez, Rithmic) — $100K paper |
| **Data** | L2/L3 MBO depth + tick-by-tick with aggressor |
| **Instruments** | NQ, ES, MNQ on CME |
| **Front Month** | NQM6 (June 2026) |

---

## .env Variables (copy-paste ready)

```bash
# Rithmic — Direct Paper Trading
RITHMIC_USER=michael@fitsells.com
RITHMIC_PASSWORD=Madmoney1986!
RITHMIC_SYSTEM_NAME=Rithmic Paper Trading
RITHMIC_URI=wss://rprotocol.rithmic.com:443
RITHMIC_INSTRUMENT=NQM6
RITHMIC_EXCHANGE=CME
RITHMIC_APP_NAME=migo:DEEP6-sim
RITHMIC_APP_VERSION=2.0
```

---

## Quick-Connect Python Snippet (VERIFIED 2026-05-20)

```python
import asyncio
from async_rithmic import RithmicClient, DataType, ReconnectionSettings, SysInfraType

client = RithmicClient(
    user="michael@fitsells.com",
    password="Madmoney1986!",
    system_name="Rithmic Paper Trading",
    app_name="migo:DEEP6-sim",
    app_version="2.0",
    url="rprotocol.rithmic.com:443",
    reconnection_settings=ReconnectionSettings(
        max_retries=20,
        backoff_type="exponential",
        interval=1.0,
        max_delay=60.0,
        jitter_range=(0.5, 1.5),
    ),
)

async def main():
    await client.connect(plants=[SysInfraType.TICKER_PLANT])
    await asyncio.sleep(0.5)  # Issue #49 mandatory delay

    # L2/L3 depth (MBO) — use subscribe_to_market_depth, NOT subscribe_to_market_data(ORDER_BOOK)
    await client.subscribe_to_market_depth("NQ", "CME", 0.0)  # 0.0 = all price levels

    # Tick data with aggressor
    await client.subscribe_to_market_data("NQ", "CME", DataType.LAST_TRADE)

    # Depth callback — protobuf, use ListFields()
    async def on_market_depth(update):
        fields = {f.name: v for f, v in update.ListFields()}
        price = fields.get("depth_price", [None])[0]
        size = fields.get("depth_size", [None])[0]
        utype = fields.get("update_type", [None])[0]  # 1=add 2=modify 3=delete
        side = fields.get("transaction_type", [None])[0]  # 1=buy 2=sell
        print(f"Depth: {price} x{size} {'BUY' if side==1 else 'SELL'} {'ADD' if utype==1 else 'MOD' if utype==2 else 'DEL'}")

    # Tick callback — dict, use bracket access
    async def on_tick(tick):
        print(f"Tick: {tick['trade_price']} x{tick['trade_size']} agg={tick['aggressor']}")

    client.on_market_depth += on_market_depth
    client.on_tick += on_tick

    try:
        while True:
            await asyncio.sleep(1)
    finally:
        await client.disconnect()

asyncio.run(main())
```

---

## CRITICAL: Subscription Methods

| What | Method | Works? |
|------|--------|--------|
| **L2/L3 Depth (MBO)** | `client.subscribe_to_market_depth("NQ", "CME", 0.0)` | YES — 200+ updates/sec |
| **Ticks** | `client.subscribe_to_market_data("NQ", "CME", DataType.LAST_TRADE)` | YES |
| ~~ORDER_BOOK~~ | ~~`client.subscribe_to_market_data("NQ", "CME", DataType.ORDER_BOOK)`~~ | **NO — returns empty depth** |

---

## Data Formats

### Tick (dict)
```python
{
    "trade_price": 29296.0,
    "trade_size": 1,
    "aggressor": 2,          # 1=BUY, 2=SELL
    "vwap": 28907.25,
    "volume": 7201,
    "net_change": -26.5,
    "exchange_order_id": "6876835330373",
    "datetime": datetime(2026, 5, 19, 22, 38, 34, tzinfo=UTC),
    "is_snapshot": False,
}
```

### Depth (protobuf — use ListFields())
```python
{
    "depth_price": [29296.0],
    "depth_size": [1],
    "update_type": [1],       # 1=add, 2=modify, 3=delete
    "transaction_type": [1],  # 1=buy, 2=sell
    "exchange_order_id": ["6876892018662"],
    "depth_order_priority": [104545033597],
    "sequence_number": 391749174,
    "template_id": 160,
}
```

---

## Common Pitfalls

1. **Wrong app_name** → rpCode 13. Only `migo:DEEP6-sim` has conformance. `migo:DEEP6` is rejected.
2. **Wrong system_name** → rpCode 13. Must be `Rithmic Paper Trading`, not `Apex`.
3. **Using ORDER_BOOK for depth** → Returns empty. Use `subscribe_to_market_depth()` instead.
4. **Accessing tick as object** → Ticks are dicts. Use `tick["trade_price"]`, not `tick.price`.
5. **Accessing depth as dict** → Depth is protobuf. Use `update.ListFields()`, not bracket access.
6. **Missing Issue #49 delay** → ForcedLogout loop. Always `await asyncio.sleep(0.5)` after connect.
7. **Using contract month in subscribe** → Use `"NQ"`, not `"NQM6"`.

---

## Gateway Selection Guide

| Your Location | Best Gateway | URL |
|---------------|-------------|-----|
| US East Coast | NYC | `wss://rprotocol-nyc.rithmic.com:443` |
| US Central / Default | Chicago | `wss://rprotocol.rithmic.com:443` |
| Co-located (CME) | Colo 75 | `wss://rprotocol-colo75.rithmic.com:443` |
| Europe | Frankfurt | `wss://rprotocol-de.rithmic.com:443` |
| Asia-Pacific | Tokyo/Singapore | `wss://rprotocol-jp.rithmic.com:443` |
| Testing | Test env | `wss://rituz00100.rithmic.com:443` |

---

## Concurrent Session Warning

R|Trader Pro + DEEP6 Python can coexist on Rithmic Paper Trading (tested 2026-05-20).
Both received ticks simultaneously. However, L2 depth may only flow to one consumer.

**If depth stops flowing**: Check if R|Trader Pro is also subscribed to the same instrument's depth.
