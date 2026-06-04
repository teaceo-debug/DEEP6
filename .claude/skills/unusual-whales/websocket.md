# Unusual Whales WebSocket — Real-Time Streaming for DEEP6

## Connection

**URL:** `wss://api.unusualwhales.com/socket`

**Auth:** Bearer token passed in connection params (exact field name: check live docs).

```python
import os
TOKEN = os.environ["UNUSUAL_WHALES_TOKEN"]  # never hardcode
```

> **Before writing any subscribe frame:** fetch the live channel spec first.
> Channel names, subscribe frame shape, and auth params can change without notice.
>
> ```bash
> curl https://api.unusualwhales.com/docs/operations/PublicApi.SocketController.channels
> ```
>
> The code in this file uses placeholder field names. Verify against the live response before shipping.

---

## Channels

| Channel | Purpose | NQ Use |
|---------|---------|--------|
| `flow-alerts` | Real-time unusual options activity | QQQ/NDX flow alerts |
| `option-trades` | Full options tape | Volume analysis |
| `off-lit-trades` | Dark pool prints as reported | QQQ institutional levels |
| `lit-trades` | Lit exchange stock trades | Volume confirmation |
| `gex` | Real-time gamma exposure updates | QQQ GEX for NQ regime |
| `market-tide` | Net call/put premium sentiment | Directional bias |
| `price` | Real-time price quotes | Current prices |
| `news` | Market news headlines | Event detection |
| `trading-halts` | Market halt notifications | Risk management |
| `contract-screener` | Hottest options chains | Unusual activity |
| `custom-alerts` | User-defined alert notifications | Custom triggers |
| `interval-flow` | Interval-based flow aggregation | Periodic snapshots |
| `net-flow` | Net premium flow (call/put balance) | Macro flow balance |

---

## High-Throughput Warning

This feed can deliver **hundreds to thousands of messages per second** during active market hours.

**Critical behavior:** if your consumer falls behind, the **server drops messages** on your connection. There's no buffer on their end waiting for you to catch up. You either keep up or you lose data.

What this means in practice:

- The receive loop must do as little work as possible. Parse later, not inline.
- **Never write to a database inside the receive loop.** One insert per message will not keep up.
- All heavy work (JSON parsing, signal computation, DB writes) goes into a separate async task.
- Batch writes are not optional at this throughput. They're the only viable approach.

---

## Production Architecture

### Core Pattern: Receive → Queue → Batch Processor

```python
import asyncio
import json
import os
import time
import websockets

# Tune maxsize to: expected_peak_msg_per_sec * acceptable_lag_seconds
# e.g. 2000 msg/s * 25s lag tolerance = 50_000
queue: asyncio.Queue[str] = asyncio.Queue(maxsize=50_000)

drop_counter = 0
queue_depth_log_interval = 10  # seconds


async def ws_consumer(url: str, token: str) -> None:
    """Receive loop. Does nothing except push raw strings onto the queue."""
    global drop_counter

    # Check live docs for exact connection params and subscribe frame shape:
    # curl https://api.unusualwhales.com/docs/operations/PublicApi.SocketController.channels
    connect_url = f"{url}?token={token}"  # placeholder — verify field name

    async with websockets.connect(connect_url) as ws:
        # Subscribe to channels — shape must be verified against live docs
        subscribe_frame = json.dumps({
            "action": "subscribe",          # placeholder
            "channels": ["off-lit-trades", "flow-alerts", "gex"],  # adjust as needed
        })
        await ws.send(subscribe_frame)

        async for raw_msg in ws:
            try:
                queue.put_nowait(raw_msg)
            except asyncio.QueueFull:
                # Drop oldest to make room for newest
                try:
                    queue.get_nowait()
                    queue.task_done()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(raw_msg)
                drop_counter += 1


BATCH_SIZE = 500          # flush when batch reaches this size
BATCH_MAX_AGE_S = 1.0     # also flush if this many seconds have passed


async def processor() -> None:
    """Parse and batch-flush messages. Runs independently of the receive loop."""
    import orjson  # faster than stdlib json at high rates

    batch: list[dict] = []
    last_flush = time.monotonic()

    while True:
        try:
            # Short timeout so we can flush on age even when queue is quiet
            raw_msg = await asyncio.wait_for(queue.get(), timeout=0.1)
            try:
                batch.append(orjson.loads(raw_msg))
            finally:
                queue.task_done()
        except asyncio.TimeoutError:
            pass  # no message — fall through to age check

        now = time.monotonic()
        age_exceeded = (now - last_flush) >= BATCH_MAX_AGE_S
        size_exceeded = len(batch) >= BATCH_SIZE

        if batch and (size_exceeded or age_exceeded):
            await flush_batch(batch)
            batch.clear()
            last_flush = now


async def flush_batch(batch: list[dict]) -> None:
    """Write a batch to your sink. Replace with DB bulk insert, file append, or HTTP POST."""
    # Example: bulk insert to TimescaleDB, write to Parquet, or POST to internal API
    # This is where you route by channel type, filter for QQQ/NDX, etc.
    pass


async def queue_monitor() -> None:
    """Log queue depth and drop count periodically."""
    global drop_counter
    while True:
        await asyncio.sleep(queue_depth_log_interval)
        depth = queue.qsize()
        print(f"[UW-WS] queue={depth}/{queue.maxsize} drops={drop_counter}")
        drop_counter = 0  # reset per interval
```

### Reconnect Loop with Exponential Backoff

```python
import random

async def ws_consumer_with_reconnect(url: str, token: str) -> None:
    backoff = 1.0
    max_backoff = 60.0

    while True:
        try:
            await ws_consumer(url, token)
            # ws_consumer returned cleanly — treat as disconnect
            backoff = 1.0
        except (websockets.ConnectionClosed, OSError) as exc:
            print(f"[UW-WS] disconnected: {exc}. Reconnecting in {backoff:.1f}s")
        except Exception as exc:
            print(f"[UW-WS] unexpected error: {exc}. Reconnecting in {backoff:.1f}s")

        await asyncio.sleep(backoff + random.uniform(0, 0.5))
        backoff = min(backoff * 2, max_backoff)


async def main() -> None:
    token = os.environ["UNUSUAL_WHALES_TOKEN"]
    url = "wss://api.unusualwhales.com/socket"

    await asyncio.gather(
        ws_consumer_with_reconnect(url, token),
        processor(),
        queue_monitor(),
    )


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Production Additions Checklist

- **`orjson` over `json`** — 2-5x faster at high message rates. `pip install orjson`.
- **Auth from env** — `os.environ["UNUSUAL_WHALES_TOKEN"]`. Never in source.
- **Dual flush trigger** — by size AND by age. Size alone starves the sink during quiet periods. Age alone causes unbounded batches during spikes.
- **Drop counter** — track how many messages were dropped per monitoring interval. A nonzero drop rate means your processor is too slow or your queue is too small.
- **Queue depth logging** — log `queue.qsize()` every N seconds. Sustained high depth means you're falling behind.
- **Resubscribe on reconnect** — the subscribe frame must be resent after every reconnect. The server doesn't remember your subscriptions.
- **Channel filtering in `flush_batch`** — route by `channel` field before writing. Don't write `news` and `gex` to the same table.

---

## DEEP6 Integration

### Channels to Subscribe

For NQ trading, subscribe to three channels:

| Channel | Why |
|---------|-----|
| `off-lit-trades` | Dark pool prints on QQQ reveal institutional accumulation/distribution levels |
| `flow-alerts` | Unusual options activity on QQQ/NDX feeds directly into the flow signal |
| `gex` | Real-time GEX updates drive the gamma regime classification |

Add `market-tide` as a macro overlay. Net call/put premium gives you a directional lean that contextualizes whether flow signals are with or against the crowd.

### Janus Queue Bridge (Async → Signal Engine)

The signal engine runs in the same asyncio event loop. Use `janus` to bridge the WebSocket consumer (async) to any sync processing (e.g., Kronos inference):

```python
import janus

# Shared between async WS consumer and sync signal engine thread
janus_queue: janus.Queue[dict] = janus.Queue(maxsize=10_000)

# In flush_batch — push parsed messages into janus async side
async def flush_batch(batch: list[dict]) -> None:
    for msg in batch:
        await janus_queue.async_q.put(msg)

# In signal engine thread (sync side)
def signal_engine_thread() -> None:
    while True:
        msg = janus_queue.sync_q.get()
        # process msg, compute signals, etc.
```

### Market-Tide Overlay

`market-tide` messages give you net premium flow (calls minus puts). Feed this into a rolling window and use it as a macro sentiment score. When net flow is strongly positive and GEX is positive, that's a high-conviction long regime. When they diverge, reduce position size.

---

## Decisions to Confirm Before Building

These are not defaults. Confirm with the user before implementing:

1. **Batch flush trigger** — size only, time only, or both? (Recommended: both, but confirm thresholds.)
2. **Sink** — TimescaleDB, flat Parquet files, or HTTP bulk endpoint to another service?
3. **Queue overflow policy** — drop oldest (default above), drop newest, or block the receive loop? Blocking is dangerous at high throughput.
4. **Which channels** — the three above are the DEEP6 defaults. Add `option-trades` if you want the full tape for volume analysis.
5. **QQQ vs NDX** — confirm which ticker the flow-alerts and off-lit-trades channels filter on, or whether filtering happens client-side in `flush_batch`.
