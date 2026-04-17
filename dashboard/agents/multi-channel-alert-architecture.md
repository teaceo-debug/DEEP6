I have comprehensive research. Now let me synthesize the full reference document.

---

# DEEP6 Multi-Channel Real-Time Alert Architecture

**Companion Reference for the NinjaTrader Graphics Agent**
**Subject:** End-to-end alert pipeline from NT8 NinjaScript signal detection through cross-process bridge to multi-channel fan-out (in-app toast, sound, email, SMS, Discord, Telegram, custom webhook, mobile push)
**Audience:** DEEP6 institutional NQ futures footprint trading system — NT8 NinjaScript on Windows + FastAPI dashboard on Mac
**Author Note:** This document is mission-critical. A missed absorption signal because the alert chain failed costs real money. Every component has a primary path, a fallback, and an audit trail.

---

## §1. Mental Model: The Alert Pipeline as a Nervous System

Treat alerts the way a body treats nerve impulses:

1. **Receptor (signal detection)** — NT8 NinjaScript indicator/strategy detects an absorption, exhaustion, stacked imbalance, or system event.
2. **Spinal column (transport)** — fast, lossless, same-machine path from NinjaScript to the local alert bridge. Named pipes are the spine; HTTP localhost is the backup.
3. **Brain stem (alert router)** — the FastAPI alert service that classifies, dedupes, throttles, and decides which channels fire.
4. **Effectors (channels)** — Discord, Telegram, SMS, email, push, custom webhook, in-app toast, sound. Each has its own failure mode.
5. **Memory (audit log)** — every alert that fires, every delivery success/failure, every retry, persisted forever for forensics and compliance.
6. **Reflexes (in-process)** — sound and toast happen *inside* NinjaTrader without ever touching the bridge, because if the bridge dies, you still hear the chime.

The architectural commitment: **alerts have at least two independent paths**. In-process (toast + sound, NT8 native) and out-of-process (everything else, via bridge). If the FastAPI bridge crashes, you still see the toast. If NT8 crashes, the bridge's last-known heartbeat tells your phone.

```
+---------------------------------------------------------------+
|                     NT8 (Windows)                             |
|                                                               |
|   [Indicator / Strategy / AddOn]                              |
|     |                                                         |
|     +--> AlertBridge (singleton)                              |
|              |                                                |
|              +--> Local reflex (always fires)                 |
|              |       |- Alert() / PlaySound() / WPF toast     |
|              |                                                |
|              +--> Named pipe -> "deep6-alert-bus"             |
|                          (fallback: HTTP POST localhost:8765) |
+---------------------------------------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|              FastAPI Alert Service (local Windows)            |
|                                                               |
|   [pipe listener]  ->  [normalize]  ->  [dedupe (Redis)]      |
|                                            |                  |
|                                            v                  |
|                                    [throttle / quiet hours]   |
|                                            |                  |
|                                            v                  |
|                                       [router rules]          |
|     ___________________________________/  |  \________________|
|    /    /        /         /        |     |       \           |
|  Email Discord Telegram   SMS    Pushover FCM   custom        |
|    \    \        \         \        |     /       /           |
|     \____\________\_________\_______|____/_______/            |
|                            |                                  |
|                            v                                  |
|                    [audit log: SQLite/JSONL]                  |
|                            |                                  |
|                            v                                  |
|                  [forwarder to Mac dashboard]                 |
|                  Tailscale tunnel -> SSE/WebSocket            |
+---------------------------------------------------------------+
```

---

## §2. NT8 Native Alert APIs — What's Actually There

### 2.1 `Alert()` — the canonical entry point

The full signature ([NinjaTrader docs — Alert](https://ninjatrader.com/support/helpguides/nt8/alert.htm)):

```csharp
public void Alert(
    string id,
    Priority priority,
    string message,
    string soundLocation,
    int rearmSeconds,
    Brush backBrush,
    Brush foreBrush
);
```

| Parameter | Meaning | DEEP6 Convention |
|---|---|---|
| `id` | Dedup key — same id within `rearmSeconds` is suppressed | `"ABS_NQ_{barIndex}_{priceLevel}"` — never reuse across signal types |
| `priority` | `Priority.Low` / `Priority.Medium` / `Priority.High` | High = absorption/exhaustion ≥ conf 85; Medium = stacked imbalance; Low = informational |
| `message` | Free-form text shown in Alerts Window | `"ABS NQ 18452.25 conf 87 [delta -1240]"` |
| `soundLocation` | Absolute path to a `.wav` file (NinjaTrader 8 only plays `.wav`, not mp3/ogg) | Per-signal-type files in `Documents\NinjaTrader 8\sounds\deep6\` |
| `rearmSeconds` | Server-side de-dupe in seconds | 30s for absorption, 5s for connection alerts, 0 for trade fills |
| `backBrush` / `foreBrush` | Color in Alerts Window row | Red-on-white = critical, yellow = warn, default = info |

The `Priority` enum is documented across both the [Alert helpguide](https://ninjatrader.com/support/helpguides/nt8/alert.htm) and the [Configuring Alerts](https://ninjatrader.com/support/helpguides/nt8/configuring_alerts.htm) page. Priority maps to a configurable user action at the **Alerts Window** level (e.g., user can configure "High = popup window, Medium = sound only, Low = log only" in NT preferences). This is the user-side override every NT trader expects.

**Sound file requirement.** `.wav` only. PCM-encoded. Custom sounds go in `Documents\NinjaTrader 8\sounds\`. NT8 will not play mp3/ogg/flac, full stop. Tests in the [sound forum thread](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/103553-audio-alert) confirm 8-bit and 16-bit PCM WAV are both supported; 24-bit PCM and floating-point WAV are flaky.

**When NT alerts are sufficient.** Solo trader at the desk during RTH, single chart, no need to know about signals when away from the screen. The Alerts Window + sound + popup is fine.

**When NT alerts are insufficient.**
- You're away from the desk and need a phone push.
- You want delivery receipts/audit trail across regulators or for trade-journaling.
- Multiple humans on a team need the same signal.
- You want a screenshot embedded in the alert (Discord/email).
- You want programmatic acknowledgment ("dismiss this alert across all my devices when I tap it on phone").

For all of those: bridge to the FastAPI service.

### 2.2 `PlaySound(filePath)` — synchronous and dangerous

`PlaySound()` is **blocking** by design. The [NinjaTrader forum thread on PlaySound in a separate thread](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/101354-how-to-run-playsound-in-separate-thread) confirms calling it from `OnMarketData` or per-tick will freeze NinjaTrader for the duration of the sound. The [Multi-Threading Considerations doc](https://ninjatrader.com/support/helpGuides/nt8/multi-threading.htm) reinforces that you should not spin up new threads inside per-tick callbacks.

**Pattern that actually works:**

```csharp
private DateTime _nextSoundAllowedAt = DateTime.MinValue;

protected override void OnBarUpdate()
{
    if (ShouldFireAlert() && DateTime.Now >= _nextSoundAllowedAt)
    {
        // Fire-and-forget on a background task — don't block OnBarUpdate
        var soundPath = @"C:\Users\...\sounds\deep6\absorption_high.wav";
        Task.Run(() => PlaySound(soundPath));
        _nextSoundAllowedAt = DateTime.Now.AddSeconds(2);  // hard cooldown
    }
}
```

Never call `PlaySound` from `OnRender` — you will drop frames. Never call it from `OnMarketData` without a cooldown — the [forum thread](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/101354-how-to-run-playsound-in-separate-thread) has reports of NT becoming unresponsive when triggered every tick.

For Add-Ons (custom windows), use `Globals.PlaySound(path)` — it wraps the same routine but has slightly better thread context awareness in the add-on container.

### 2.3 `AlertCallback` — for advanced consumers

The `AlertCallback` signature ([docs](https://ninjatrader.com/support/helpguides/nt8/alertcallback.htm)) lets a custom add-on subscribe to *every* alert NT raises (yours, other strategies', the platform's). Useful for the bridge: register one callback, route everything to the FastAPI service, no per-strategy plumbing.

```csharp
NinjaTrader.NinjaScript.Alert.AlertCallback(
    Instrument instrument,
    object source,
    string id,
    DateTime time,
    Priority priority,
    string message,
    string soundLocation,
    Brush backBrush,
    Brush foreBrush,
    int rearmSeconds
);
```

This is the recommended NT-native interception point: subscribe once in an Add-On's `OnWindowCreated`, every `Alert()` call from any indicator/strategy in NT funnels through your callback, you forward to the bridge.

---

## §3. NinjaScript Event Hooks That Should Trigger Alerts

| Event | When it fires | Alert mapping |
|---|---|---|
| `OnBarUpdate` | Per tick (CalculateMode.OnEachTick) or per bar close | Custom signal detection — absorption, exhaustion, stacked imbalance |
| `OnMarketData` | Every L1 quote update | Big-order arrival (≥200 contracts), aggressive sweep |
| `OnExecutionUpdate` | Every fill (and partial fill) | Trade-entered, trade-exited, P&L summary |
| `OnOrderUpdate` | Every order state change (Submitted → Accepted → Working → Filled / Rejected / Cancelled) | Order rejected (CRITICAL — broker refused), order working too long |
| `OnConnectionStatusUpdate` | On connection state change (price feed and order routing tracked separately) | Connection lost, connection restored |
| `OnAccountStatusUpdate` | Margin call, account locked, daily-loss-limit hit | CRITICAL — interrupt trading |
| `OnRender` | Per repaint frame (~60Hz when chart visible) | **Never** alert from here — display only |

### 3.1 OnExecutionUpdate / OnOrderUpdate — fill alerts

From the [OnExecutionUpdate doc](https://ninjatrader.com/support/helpguides/nt8/onexecutionupdate.htm) and [OnOrderUpdate doc](https://ninjatrader.com/support/helpguides/nt8/onorderupdate.htm):

```csharp
protected override void OnOrderUpdate(Order order, double limitPrice, double stopPrice,
    int quantity, int filled, double averageFillPrice, OrderState orderState,
    DateTime time, ErrorCode error, string comment)
{
    if (orderState == OrderState.Rejected)
    {
        // CRITICAL — broker said no
        SendCriticalAlert($"ORDER REJECTED: {order.Name} {error} | {comment}");
    }
    else if (orderState == OrderState.Filled && order.OrderAction == OrderAction.Buy)
    {
        SendAlert(Priority.High, "ENTRY", $"LONG {order.Filled}@{order.AverageFillPrice:F2}");
    }
}

protected override void OnExecutionUpdate(Execution execution, string executionId,
    double price, int quantity, MarketPosition marketPosition, string orderId, DateTime time)
{
    // Use OnExecutionUpdate to confirm protective orders are submitted only after entry fills.
    // Per the NT8 forum, OnOrderUpdate fires first for state changes; OnExecutionUpdate
    // fires only for Filled / PartFilled. For trade journaling, OnExecutionUpdate is the
    // source of truth for fills.
}
```

**Critical gotcha** (from [the OnOrderUpdate vs OnExecutionUpdate forum thread](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/1234525-whats-best-to-use-onexecutionupdate-or-onorderupdate-or-onexecution)): never block in either of these. They run on the data thread. Anything heavy (HTTP, file I/O, sound) goes to a `Task.Run()` or, better, a `Channel<AlertEvent>` consumer.

### 3.2 OnConnectionStatusUpdate — feed alerts

From the [OnConnectionStatusUpdate doc](https://ninjatrader.com/support/helpguides/nt8/onconnectionstatusupdate.htm):

```csharp
protected override void OnConnectionStatusUpdate(ConnectionStatusEventArgs args)
{
    if (args.PriceStatus == ConnectionStatus.ConnectionLost)
    {
        SendCriticalAlert("PRICE FEED LOST — Rithmic gateway disconnected");
    }
    if (args.Status == ConnectionStatus.ConnectionLost)  // order routing
    {
        SendCriticalAlert("ORDER ROUTING LOST — cannot place trades");
    }
    if (args.PriceStatus == ConnectionStatus.Connected && _wasDisconnected)
    {
        SendAlert(Priority.Medium, "RECONNECT", "Price feed restored");
    }
}
```

`PriceStatus` and `Status` are tracked separately because (per the [forum thread](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/92885-onconnectionstatusupdate-pricestatus)) you can lose order routing while still receiving prices — extremely common with Rithmic during their Sunday maintenance windows.

---

## §4. Cross-Process Bridge: NT8 → FastAPI

The bridge is the single most critical architectural decision. It must be:
- **Fast** — sub-millisecond from `Alert()` call to bridge ack so OnBarUpdate doesn't drag.
- **Lossless** — never drop an alert because the bridge was busy.
- **Resilient** — survive bridge restarts without losing alerts in flight.
- **Same-machine** — the bridge runs on the NT8 Windows box; cross-machine forwarding happens *after* the bridge has acked.

### 4.1 Latency comparison

Hard numbers from the [pipesvshttp benchmark](https://github.com/nickntg/pipesvshttp) and the [Anthony Simmon write-up on .NET IPC](https://anthonysimmon.com/local-ipc-over-named-pipes-aspnet-core-streamjsonrpc-dotnet/):

| Transport | Same-machine latency (small msg) | Throughput | Setup complexity | Recommendation |
|---|---|---|---|---|
| **Named pipe** (System.IO.Pipes) | **~0.1 ms** | ~750 MB/s for large payloads | Low (built into .NET) | **PRIMARY** |
| HTTP localhost (Kestrel/FastAPI) | ~0.3 ms | Limited by HTTP framing | Low (any HTTP client) | Fallback only |
| Memory-mapped file | ~0.05 ms | Highest | Medium (manual sync) | Overkill for alerts |
| File watcher (FileSystemWatcher) | 50-500 ms | Filesystem-bound | Low | Last-resort offline buffer |
| WebSocket localhost | ~0.5-1 ms | Good | Medium (handshake + framing) | Use for streaming, not alerts |
| gRPC | ~1-2 ms | Good | High (proto codegen) | Overkill — alerts aren't an RPC |

The [Baeldung IPC comparison](https://www.baeldung.com/linux/ipc-performance-comparison) and [Patrick Dahlke's iceoryx2 numbers](https://patrickdahlke.com/posts/iceoryx2-csharp-performance/) corroborate: named pipes are the right call for same-machine, low-latency, small-payload IPC in .NET.

**Decision: named pipe primary, HTTP localhost fallback.** Rationale: named pipe is 3× faster, requires no port allocation, has built-in OS-level access control. HTTP fallback exists because if the FastAPI service is being restarted, the pipe disappears momentarily; the NT8 client should fail over to `http://localhost:8765/alerts` and the FastAPI startup script binds *both* a pipe server and an HTTP endpoint.

### 4.2 NT8 NinjaScript: AlertBridge singleton

A single shared bridge for all indicators/strategies/add-ons. Drop into `Documents\NinjaTrader 8\bin\Custom\AddOns\Deep6AlertBridge.cs`:

```csharp
using System;
using System.Collections.Concurrent;
using System.IO;
using System.IO.Pipes;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace NinjaTrader.NinjaScript.AddOns
{
    public sealed class Deep6AlertBridge
    {
        private static readonly Lazy<Deep6AlertBridge> _instance =
            new Lazy<Deep6AlertBridge>(() => new Deep6AlertBridge());
        public static Deep6AlertBridge Instance => _instance.Value;

        private const string PipeName = "deep6-alert-bus";
        private const string FallbackUrl = "http://127.0.0.1:8765/alerts";

        private readonly BlockingCollection<AlertEvent> _queue =
            new BlockingCollection<AlertEvent>(boundedCapacity: 10_000);
        private readonly CancellationTokenSource _cts = new CancellationTokenSource();
        private readonly HttpClient _http = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        private NamedPipeClientStream _pipe;

        private Deep6AlertBridge()
        {
            // Background dispatcher thread — never blocks the data thread
            var t = new Thread(DispatchLoop) { IsBackground = true, Name = "Deep6AlertBridge" };
            t.Start();
        }

        public void Send(AlertEvent evt)
        {
            // Non-blocking enqueue — drops oldest if queue is full
            if (!_queue.TryAdd(evt))
            {
                // Queue full — log via NT's own log facility, never throw from here
                NinjaTrader.Code.Output.Process(
                    "Deep6AlertBridge queue full — dropping alert " + evt.Id,
                    PrintTo.OutputTab1);
            }
        }

        private void DispatchLoop()
        {
            foreach (var evt in _queue.GetConsumingEnumerable(_cts.Token))
            {
                if (!TrySendPipe(evt))
                    TrySendHttp(evt);  // fallback
            }
        }

        private bool TrySendPipe(AlertEvent evt)
        {
            try
            {
                if (_pipe == null || !_pipe.IsConnected)
                {
                    _pipe?.Dispose();
                    _pipe = new NamedPipeClientStream(".", PipeName,
                        PipeDirection.Out, PipeOptions.Asynchronous);
                    _pipe.Connect(timeout: 200);  // ms
                }
                var json = JsonSerializer.Serialize(evt);
                var bytes = Encoding.UTF8.GetBytes(json + "\n");  // newline-delimited JSON
                _pipe.Write(bytes, 0, bytes.Length);
                _pipe.Flush();
                return true;
            }
            catch
            {
                _pipe?.Dispose();
                _pipe = null;
                return false;
            }
        }

        private bool TrySendHttp(AlertEvent evt)
        {
            try
            {
                var json = JsonSerializer.Serialize(evt);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                var resp = _http.PostAsync(FallbackUrl, content).Result;
                return resp.IsSuccessStatusCode;
            }
            catch
            {
                // Both paths failed — write to local audit file so we don't lose it
                AppendDeadLetter(evt);
                return false;
            }
        }

        private void AppendDeadLetter(AlertEvent evt)
        {
            try
            {
                var path = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    "NinjaTrader 8", "deep6", "alert_dead_letter.jsonl");
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                File.AppendAllText(path, JsonSerializer.Serialize(evt) + "\n");
            }
            catch { /* if even the filesystem is gone, accept the loss */ }
        }
    }

    public class AlertEvent
    {
        public string Id { get; set; }                      // dedup key
        public string SignalType { get; set; }              // ABS, EXH, IMB3, BIG, REJECT, ...
        public string Instrument { get; set; }              // NQ 12-25
        public DateTime Timestamp { get; set; }
        public double Price { get; set; }
        public int Confidence { get; set; }                 // 0-100
        public string Priority { get; set; }                // P1..P4
        public string Message { get; set; }
        public string ChartScreenshotPath { get; set; }     // optional
        public Dictionary<string, object> Context { get; set; }  // signal-specific telemetry
    }
}
```

**Key design choices in this snippet:**
- `BlockingCollection` with bounded capacity = backpressure without unbounded memory growth.
- Dispatcher runs on its own thread, never blocks `OnBarUpdate`.
- Pipe is reconnected lazily; transient failures fall through to HTTP.
- Both paths failing writes to a JSONL dead-letter file inside `Documents\NinjaTrader 8\deep6\` — the FastAPI service replays this on its own startup.
- Newline-delimited JSON over the pipe = trivial parsing on the Python side, no length-prefix complexity.

### 4.3 FastAPI side: pipe server + HTTP endpoint

Both endpoints feed the same in-process queue:

```python
# alert_service/app.py
import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pywintypes
import win32file
import win32pipe
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

PIPE_NAME = r"\\.\pipe\deep6-alert-bus"

class AlertEvent(BaseModel):
    Id: str
    SignalType: str
    Instrument: str
    Timestamp: datetime
    Price: float
    Confidence: int
    Priority: str           # P1..P4
    Message: str
    ChartScreenshotPath: str | None = None
    Context: dict = {}

app = FastAPI()
alert_queue: asyncio.Queue[AlertEvent] = asyncio.Queue(maxsize=10_000)

# --- HTTP fallback endpoint ---
@app.post("/alerts")
async def http_ingest(evt: AlertEvent, bg: BackgroundTasks):
    await alert_queue.put(evt)
    return {"status": "queued", "id": evt.Id}

# --- Named pipe server (Windows only) ---
async def pipe_server():
    while True:
        try:
            handle = win32pipe.CreateNamedPipe(
                PIPE_NAME,
                win32pipe.PIPE_ACCESS_INBOUND,
                win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_WAIT,
                win32pipe.PIPE_UNLIMITED_INSTANCES,
                65536, 65536,
                0, None,
            )
            win32pipe.ConnectNamedPipe(handle, None)
            buf = b""
            while True:
                try:
                    _, data = win32file.ReadFile(handle, 65536)
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip():
                            continue
                        evt = AlertEvent.model_validate_json(line)
                        await alert_queue.put(evt)
                except pywintypes.error:
                    break
            win32file.CloseHandle(handle)
        except Exception:
            await asyncio.sleep(0.5)  # don't tight-loop on permanent failure

# --- Background processor ---
async def processor():
    while True:
        evt = await alert_queue.get()
        try:
            await route_alert(evt)  # dedupe + throttle + fan-out (next sections)
        except Exception as e:
            await audit_log(evt, status="error", error=str(e))
        finally:
            alert_queue.task_done()

@app.on_event("startup")
async def startup():
    asyncio.create_task(pipe_server())
    asyncio.create_task(processor())
    await replay_dead_letter()  # see §13.3

# Run with: uvicorn alert_service.app:app --port 8765 --host 127.0.0.1
```

The [Greeden practical guide to webhook receivers in FastAPI](https://blog.greeden.me/en/2026/04/07/a-practical-guide-to-safely-implementing-webhook-receiver-apis-in-fastapi-from-signature-verification-and-retry-handling-to-idempotency-and-asynchronous-processing/) is the reference for the "verify, queue, ack fast, process async" pattern used above. The FastAPI [BackgroundTasks docs](https://fastapi.tiangolo.com/) confirm: HTTP ack should return < 50ms, real work happens after.

---

## §5. Multi-Channel Alert Fan-Out

### 5.1 Priority routing matrix

The DEEP6 priority taxonomy:

| Priority | Definition | Channels (default) | Quiet hours behavior |
|---|---|---|---|
| **P1 — CRITICAL** | Drawdown limit hit, broker rejection, daily loss limit, system error preventing trading | Toast + Sound (urgent) + SMS + Pushover (emergency) + Discord + Email | **Always fires**, ignores quiet hours |
| **P2 — HIGH** | Absorption/exhaustion conf ≥ 85, big order ≥ 500 contracts, trade entered/exited | Toast + Sound (alert) + Discord + Pushover (high) + Email | Suppress SMS during quiet hours; rest still fire |
| **P3 — MEDIUM** | Stacked imbalance 3+, conf 70-84 signals, big order 200-499 | Toast + Sound (gentle) + Discord | Suppress Pushover/Email during quiet hours |
| **P4 — INFO** | Connection restored, daily P&L checkpoint, every signal landing on the chart | Toast only (no sound), bridge audit log only | Toast suppressed during quiet hours |

**Concurrency model.** Channels fire **in parallel** (asyncio gather) with **per-channel timeouts**. One channel's failure never blocks another:

```python
# alert_service/router.py
import asyncio
from .channels import discord, telegram, sms, email, pushover, fcm, custom_webhook
from .audit import audit_log
from .dedupe import is_duplicate, mark_seen
from .throttle import is_throttled
from .quiet_hours import is_quiet_now, channel_allowed_in_quiet_hours

PRIORITY_MATRIX = {
    "P1": ["discord", "telegram", "sms", "email", "pushover_emergency", "fcm", "custom"],
    "P2": ["discord", "telegram", "email", "pushover_high", "fcm", "custom"],
    "P3": ["discord", "telegram", "fcm", "custom"],
    "P4": [],  # toast-only, handled in-process at NT8
}

async def route_alert(evt):
    if await is_duplicate(evt.Id):
        await audit_log(evt, status="deduped"); return
    if await is_throttled(evt.SignalType):
        await audit_log(evt, status="throttled"); return
    await mark_seen(evt.Id, ttl=300)

    channels = PRIORITY_MATRIX.get(evt.Priority, [])
    if is_quiet_now() and evt.Priority != "P1":
        channels = [c for c in channels if channel_allowed_in_quiet_hours(c)]

    senders = {
        "discord":             discord.send,
        "telegram":            telegram.send,
        "sms":                 sms.send,
        "email":               email.send,
        "pushover_emergency":  pushover.send_emergency,
        "pushover_high":       pushover.send_high,
        "fcm":                 fcm.send,
        "custom":              custom_webhook.send,
    }

    results = await asyncio.gather(
        *(send_with_timeout(senders[c], evt, timeout=5.0) for c in channels),
        return_exceptions=True,
    )

    for channel, result in zip(channels, results):
        ok = not isinstance(result, Exception)
        await audit_log(evt, channel=channel, status="ok" if ok else "failed",
                        error=str(result) if not ok else None)

async def send_with_timeout(sender, evt, timeout):
    try:
        return await asyncio.wait_for(sender(evt), timeout=timeout)
    except asyncio.TimeoutError:
        raise Exception(f"timeout after {timeout}s")
```

### 5.2 Per-channel retry policy

Each channel sender wraps its HTTP call in `tenacity` with exponential backoff + jitter. Per the [tenacity docs](https://tenacity.readthedocs.io/) and the [Young Gao retry patterns post](https://dev.to/young_gao/retry-patterns-that-actually-work-exponential-backoff-jitter-and-dead-letter-queues-75):

```python
# alert_service/retry.py
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
import httpx

retry_policy = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=0.5, max=10, jitter=2),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    reraise=True,
)
```

5 attempts × exponential-with-jitter caps total wait around 30s, which is the right ceiling for a "hot" alert. After 5 failures, the alert lands in the per-channel dead-letter queue (a SQLite table) and a P1 meta-alert fires ("Discord delivery failed for alert XYZ — manual review needed").

### 5.3 Smart batching

Per the [LogicMonitor alert fatigue guidance](https://www.logicmonitor.com/blog/network-monitoring-avoid-alert-fatigue) and the [Better Stack alert-fatigue post](https://betterstack.com/community/guides/monitoring/best-practices-alert-fatigue/), 3-5 minute deduplication windows for medium-priority alerts are the sweet spot.

DEEP6 implements **batching only for P3 informational signals** — never P1/P2 (you want those instantly). If 5 stacked imbalances fire in 30 seconds, send one Discord message titled "5 stacked imbalances on NQ 16:42-16:43" with the individual prices in fields, instead of 5 separate messages. This keeps Discord under its 30/min webhook limit ([Discord rate limits docs](https://docs.discord.com/developers/topics/rate-limits)) and respects user attention.

---

## §6. In-App Toast Notifications (NT8 native window)

The detail of WPF toast UI lives in §64 of the master graphics agent. A few cross-cutting points specific to alerts:

- **Always dispatch to the UI thread.** From the [WPF toast docs](https://learn.microsoft.com/en-us/windows/apps/develop/notifications/app-notifications/send-local-toast) and the [Microsoft.Toolkit.Uwp.Notifications guidance](https://learn.microsoft.com/en-us/windows/apps/design/shell/tiles-and-notifications/send-local-toast): `Application.Current.Dispatcher.BeginInvoke(...)` from the data thread.
- **Per-priority styling.** P1 = red border + persistent (no auto-dismiss), P2 = orange border + 10s auto-dismiss, P3 = blue border + 5s auto-dismiss, P4 = gray + 3s.
- **Action buttons.** P1 toasts should expose "Acknowledge", "View in dashboard", and (for trade-related P1) "Cancel order" / "Flatten position". Each button posts back to the FastAPI service via the same named pipe (reverse direction) so the audit log captures the human acknowledgment.
- **Stacking.** Newer toasts stack above older ones; max 5 visible; oldest auto-dismiss when a 6th arrives.
- **Persistent for critical.** P1 stays on screen until acknowledged. Period.

Recommended library: [rafallopatka/ToastNotifications](https://github.com/rafallopatka/ToastNotifications) — actively maintained, supports custom positions, themes, and the action-button pattern DEEP6 needs.

---

## §7. Sound Design for Alerts

The human-factors literature on alarm design ([NCBI alarm design review](https://nap.nationalacademies.org/read/5436/chapter/7), [AAMI Designing Effective Alarm Sounds](https://array.aami.org/doi/full/10.2345/0899-8205-45.4.290), [Max Rovensky's notification sound guide](https://medium.com/@fivepointseven/how-to-design-a-pleasant-alert-sound-2ddf7a9724de)) gives concrete numbers:

| Property | Value | Why |
|---|---|---|
| Frequency range | 500-5,000 Hz | Below 500 Hz blends into HVAC/road noise; above 5 kHz is uncomfortable |
| Dominant frequency | 1,000-4,000 Hz | Peak human auditory sensitivity |
| Fundamental | < 1,000 Hz with harmonics | Avoids "shrill" perception |
| Distinct components | ≥ 4 dominant frequencies in first 10 harmonics | Reduces masking, increases distinctiveness |
| Duration | < 500 ms (ideally 200-300 ms) | Anything longer interrupts cognition |
| Envelope | Soft attack (10-30 ms ramp) | Prevents startle response |
| Repetition | Single sound, not a loop | Loops convey "alarm/panic", you want "notice" |

**Per-signal sound mapping for DEEP6.** Use distinct sounds per signal type — auditory icons let your brain identify the signal *before* you look at the screen:

| Signal type | Suggested sound character | File name |
|---|---|---|
| Absorption | Low single chime, descending fifth | `absorption.wav` |
| Exhaustion | Higher chime, ascending fourth | `exhaustion.wav` |
| Stacked imbalance | Three quick blips | `imbalance3.wav` |
| Big order | Single deep "thunk" (woody) | `bigorder.wav` |
| Trade entered | Mechanical "ka-chunk" cash-register style | `entry.wav` |
| Trade exited | Soft "ding" | `exit.wav` |
| Stop hit | Same as exit but lower pitch | `stop.wav` |
| Connection lost | Two-tone falling minor third (NATO "fail" pattern) | `disconnect.wav` |
| **CRITICAL (drawdown limit)** | Repeating triple tone, urgent | `critical.wav` |

**Sources for the actual files.**
- [Bensound](https://www.bensound.com) — royalty-free, has UI/notification packs.
- [Zapsplat](https://www.zapsplat.com) — free with attribution, large UI sound library.
- [Freesound.org](https://freesound.org) — Creative Commons.
- Apple GarageBand or Logic Pro — generate your own from instrument samples.
- [SFX-Buy](https://www.sfx-buy.com) or [AudioJungle](https://audiojungle.net) for premium curated alert packs.

**Mute conditions.**
- Windows "Focus assist" (Do Not Disturb) — bridge respects this; only P1 plays sound.
- Active screen-share / meeting detection (Teams/Zoom presence API) — suppress sounds, route to silent toast + Pushover.
- User-configured "trading hours" toggle in dashboard.

**Volume calibration.** Set the WAV to peak at -6 dBFS, not 0 dBFS. NT8's playback respects system volume but cannot duck other audio (browsers/Spotify), so headroom matters.

---

## §8. Email Alerts

### 8.1 Provider comparison

From the [BuildMVPFast email API comparison](https://www.buildmvpfast.com/api-costs/email), [Postmark vs SendGrid](https://postmarkapp.com/compare/sendgrid-alternative), and the [Mailtrap email API roundup](https://mailtrap.io/blog/email-api-flexibility/):

| Provider | Pricing entry | Deliverability (independent test) | Best for |
|---|---|---|---|
| **Postmark** | $15/mo for 10k | **98.7% inbox** | Transactional alerts (DEEP6's case) |
| Mailgun | Pay-as-you-go ~$0.80/1k | High | High volume + routing |
| SendGrid | No free tier (killed 2025), paid from ~$20/mo | 95.3% inbox | Mixed transactional + marketing |
| Resend | Free tier 100/day | High | Indie / early stage |
| AWS SES | $0.10/1k | Variable (depends on warm-up) | Cost-sensitive, willing to tune |
| Direct SMTP via Gmail | Free | Poor (Gmail flags as spam fast) | Test only, not production |

**Pick Postmark for DEEP6.** Transactional alerts are exactly its niche: separation from marketing infrastructure means absorption alerts don't get filtered with marketing newsletters. 98.7% inbox placement vs 95.3% on SendGrid is a 3.4-point delta — over a year of trading, that's the difference between "I caught the 14:32 absorption" and "I missed it because the email was in spam".

### 8.2 Postmark sender (Python)

```python
# alert_service/channels/email.py
import os
import httpx
from ..retry import retry_policy

POSTMARK_TOKEN = os.environ["POSTMARK_SERVER_TOKEN"]
FROM_ADDRESS   = os.environ["DEEP6_ALERT_FROM"]    # "alerts@deep6.example"
TO_ADDRESS     = os.environ["DEEP6_ALERT_TO"]      # "michael.gonzalez5@gmail.com"

_client = httpx.AsyncClient(timeout=10.0)

@retry_policy
async def send(evt):
    subject = f"[DEEP6 {evt.Priority}] {evt.SignalType} {evt.Instrument} {evt.Price:.2f} conf {evt.Confidence}"
    text_body = (
        f"Signal: {evt.SignalType}\n"
        f"Instrument: {evt.Instrument}\n"
        f"Price: {evt.Price:.2f}\n"
        f"Confidence: {evt.Confidence}\n"
        f"Time: {evt.Timestamp.isoformat()}\n\n"
        f"{evt.Message}\n\n"
        f"View dashboard: https://deep6.example/dashboard?alert={evt.Id}"
    )
    payload = {
        "From": FROM_ADDRESS,
        "To": TO_ADDRESS,
        "Subject": subject,
        "TextBody": text_body,
        "MessageStream": "outbound",  # transactional stream
    }
    if evt.ChartScreenshotPath:
        with open(evt.ChartScreenshotPath, "rb") as f:
            import base64
            payload["Attachments"] = [{
                "Name": "chart.png",
                "Content": base64.b64encode(f.read()).decode(),
                "ContentType": "image/png",
            }]
    r = await _client.post(
        "https://api.postmarkapp.com/email",
        headers={"X-Postmark-Server-Token": POSTMARK_TOKEN, "Accept": "application/json"},
        json=payload,
    )
    r.raise_for_status()
    return r.json()
```

**Subject line convention.** `[DEEP6 P2] ABS NQ 18452.25 conf 87` — bracket-prefixed for Gmail filters, ALL-CAPS signal code (3 chars), instrument, price, confidence. This is scannable on a phone lock screen without opening.

**HTML vs plaintext.** Plaintext only by default. HTML email is a deliverability minefield (one bad styled `<table>` and you're in spam). If you want a chart inline, attach as `image/png` — alerts are always 1:1 to a single human, not bulk.

**Latency.** SMTP via direct TCP: 1-5s. Postmark API: typically 200-800ms.

---

## §9. SMS Alerts (Twilio)

### 9.1 Cost reality check

From [Twilio's US SMS pricing](https://www.twilio.com/en-us/sms/pricing/us) and the [Apidog Twilio cost breakdown](https://apidog.com/blog/twilio-sms-api-cost/):

| Item | 2026 cost |
|---|---|
| Outbound SMS segment (US) | $0.0083 |
| Carrier surcharge | $0.003-0.005/msg |
| Phone number (long code) | $1.15/mo |
| Toll-free number | $2.15/mo |
| 10DLC sole-prop brand | $4.50 one-time |
| 10DLC standard brand | $46 one-time |
| Campaign registration | $15 one-time + $1.50-10/mo |
| Failed-message processing | $0.001/msg |

**Effective per-message: $0.012-0.014** once carrier surcharges are included. A trader receiving 30 P1 alerts/month spends ~$0.50/mo on SMS. Worth every penny when the alternative is missing a drawdown breach.

### 9.2 Pre-flight: 10DLC registration

US carriers (T-Mobile especially after [the Jan 2026 fee changes](https://help.twilio.com/articles/44609260499995)) heavily filter unregistered SMS. You **must** register a 10DLC brand and campaign. For a solo trader: sole-prop brand ($4.50) + 1 campaign ($15 + $1.50/mo). Total setup ~$20 + $1.50/mo recurring. Skipping this = your alerts go to the carrier's "unverified" bucket and arrive 2-30 minutes late, or not at all.

### 9.3 Twilio Python sender

```python
# alert_service/channels/sms.py
import os
from twilio.rest import Client
from ..retry import retry_policy

_client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
MESSAGING_SERVICE_SID = os.environ["TWILIO_MESSAGING_SID"]   # MGxxxx...
TO_NUMBER = os.environ["DEEP6_PHONE_NUMBER"]                 # +1xxx...

@retry_policy
async def send(evt):
    # SMS body — strip to essentials, < 160 chars to fit one segment
    body = f"DEEP6 {evt.Priority} {evt.SignalType} {evt.Instrument} {evt.Price:.2f} c{evt.Confidence}"
    # Twilio Python SDK is sync — run in executor to avoid blocking the loop
    import asyncio
    loop = asyncio.get_running_loop()
    msg = await loop.run_in_executor(None, lambda: _client.messages.create(
        messaging_service_sid=MESSAGING_SERVICE_SID,
        to=TO_NUMBER,
        body=body,
    ))
    return msg.sid
```

**When SMS is right.** Only P1. Drawdown limits, broker rejections, system errors that prevent trading. SMS at 3am is acceptable when it tells you "your stops were not placed". SMS for "absorption detected" at 3am will make you uninstall it inside a week.

**Rate limit / cost cap.** Hard cap 50 SMS/day in code. If you'd exceed it, send Pushover instead and audit-log "SMS rate cap hit". Costs cannot exceed ~$1/day ever.

---

## §10. Discord Webhook

The simplest, fastest, most flexible channel. No bot to maintain, no OAuth, no hosting — just a webhook URL.

### 10.1 Setup

In your Discord server: Server Settings → Integrations → Webhooks → New Webhook → copy URL. URL format:

```
https://discord.com/api/webhooks/{webhook.id}/{webhook.token}
```

Treat it as a secret (stored in env / secrets manager). Anyone with this URL can post to that channel.

### 10.2 Rate limits

Per the [Discord rate-limits doc](https://docs.discord.com/developers/topics/rate-limits) and [Birdie's webhook guide](https://birdie0.github.io/discord-webhooks-guide/other/rate_limits.html): **30 messages/min per webhook URL**. Burst higher returns 429 with `Retry-After`. Your sender must honor that header.

### 10.3 Embed formatting

Embeds are JSON objects with rich layout. For trading alerts:
- **color** in *decimal* (not hex) — `0xFF4444 = 16729156` for red.
- **fields** with `inline: true` — 3 per row.
- **thumbnail** — small image top-right, 80×80, ideal for a signal-type icon.
- **image** — full-width chart screenshot.
- **footer** — `DEEP6 v2.0 • {timestamp}`.
- **author** — bot name + icon.

### 10.4 Sender

```python
# alert_service/channels/discord.py
import os
import httpx
from ..retry import retry_policy

WEBHOOK = os.environ["DEEP6_DISCORD_WEBHOOK"]
_client = httpx.AsyncClient(timeout=10.0)

PRIORITY_COLOR = {
    "P1": 0xFF0000,  # red
    "P2": 0xFF8800,  # orange
    "P3": 0x3498DB,  # blue
    "P4": 0x95A5A6,  # gray
}

@retry_policy
async def send(evt):
    embed = {
        "title": f"{evt.SignalType} • {evt.Instrument}",
        "description": evt.Message,
        "color": PRIORITY_COLOR.get(evt.Priority, 0x95A5A6),
        "timestamp": evt.Timestamp.isoformat(),
        "fields": [
            {"name": "Price", "value": f"{evt.Price:.2f}", "inline": True},
            {"name": "Confidence", "value": f"{evt.Confidence}", "inline": True},
            {"name": "Priority", "value": evt.Priority, "inline": True},
        ],
        "footer": {"text": f"DEEP6 • {evt.Id}"},
    }
    # Add signal-specific context as additional fields
    for key, val in (evt.Context or {}).items():
        embed["fields"].append({"name": key, "value": str(val), "inline": True})

    payload = {
        "username": "DEEP6 Alert",
        "avatar_url": "https://deep6.example/static/d6-icon.png",
        "embeds": [embed],
    }

    r = await _client.post(WEBHOOK, json=payload)
    if r.status_code == 429:
        retry_after = float(r.headers.get("Retry-After", "1"))
        import asyncio; await asyncio.sleep(retry_after)
        raise httpx.HTTPStatusError("rate limited", request=r.request, response=r)
    r.raise_for_status()
    return r.status_code
```

**Why webhook not bot.** Bots require hosting, presence management, login persistence, OAuth scope review on every server, and bot token rotation. Webhooks are URL-only, scoped to a single channel, and Discord's 30/min limit per *webhook* (not per bot) means sharding by signal type is trivial — give absorption its own webhook, exhaustion another, etc., to multiply effective throughput.

---

## §11. Telegram Bot

### 11.1 Setup

1. Open Telegram, message [@BotFather](https://t.me/BotFather), `/newbot`, give it a name, get a token like `123456:ABC-DEF1234ghIkl...`.
2. Start a chat with your new bot and send any message.
3. `https://api.telegram.org/bot{TOKEN}/getUpdates` → find your `chat.id`.
4. Store TOKEN and CHAT_ID in env.

### 11.2 Rate limits

Per [Telegram Bots FAQ](https://core.telegram.org/bots/faq) and the [grammY flood-limit docs](https://grammy.dev/advanced/flood):
- **1 message/sec per chat** (DEEP6's primary constraint).
- 30 messages/sec to *all* users (group/broadcast).
- Bursts above 1/sec/chat get 429 errors after a short tolerance.

For DEEP6 (single trader, single chat) the 1/sec/chat is the only limit that matters. Easily handled by the sender's queue.

### 11.3 Sender

```python
# alert_service/channels/telegram.py
import os
import httpx
from ..retry import retry_policy

TOKEN = os.environ["DEEP6_TELEGRAM_TOKEN"]
CHAT_ID = os.environ["DEEP6_TELEGRAM_CHAT_ID"]
BASE = f"https://api.telegram.org/bot{TOKEN}"
_client = httpx.AsyncClient(timeout=10.0)

@retry_policy
async def send(evt):
    text = (
        f"*DEEP6 {evt.Priority}* `{evt.SignalType}` {evt.Instrument}\n"
        f"`{evt.Price:.2f}` • conf `{evt.Confidence}`\n"
        f"_{evt.Message}_\n"
        f"`{evt.Timestamp:%H:%M:%S}`"
    )
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_notification": evt.Priority in ("P3", "P4"),  # silent for low priority
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "View", "url": f"https://deep6.example/dashboard?alert={evt.Id}"},
                {"text": "Ack", "callback_data": f"ack:{evt.Id}"},
            ]]
        },
    }
    r = await _client.post(f"{BASE}/sendMessage", json=payload)
    if r.status_code == 429:
        retry_after = r.json().get("parameters", {}).get("retry_after", 1)
        import asyncio; await asyncio.sleep(retry_after)
        raise httpx.HTTPStatusError("rate limited", request=r.request, response=r)
    r.raise_for_status()
    return r.json()

# To send a chart screenshot:
@retry_policy
async def send_photo(evt, photo_path):
    with open(photo_path, "rb") as f:
        files = {"photo": ("chart.png", f, "image/png")}
        data = {"chat_id": CHAT_ID, "caption": f"{evt.SignalType} {evt.Instrument} {evt.Price:.2f}"}
        r = await _client.post(f"{BASE}/sendPhoto", data=data, files=files)
    r.raise_for_status()
    return r.json()
```

`disable_notification: true` on P3/P4 = the message arrives silently (no phone vibrate). User sees it next time they open Telegram.

`inline_keyboard` action buttons let the user acknowledge from inside Telegram — the `callback_data` posts back to your bot's webhook (separate Telegram concept) which forwards to the audit log.

---

## §12. Pushover (Desktop + Mobile Push)

### 12.1 Why Pushover for DEEP6

- **$5 one-time per platform** ([Pushover pricing](https://pushover.net/pricing)) — no subscription.
- Native apps for iOS, Android, **and desktop** (macOS/Windows/Linux).
- Emergency priority with **acknowledgment** — keeps repeating until you tap "I got it".
- Custom sounds per device.
- One API, no APNs/FCM credential management on your side.
- Per the [Pushover API docs](https://pushover.net/api): full control over priority, sound, retry, expire.

This is the killer channel for DEEP6 — it's the only one that combines desktop + phone + emergency-acknowledgment in one product without you having to ship a mobile app.

### 12.2 Priority levels

From the [Pushover API doc](https://pushover.net/api):

| `priority` | Behavior |
|---|---|
| -2 | Lowest, no sound, no vibrate |
| -1 | Quiet |
| 0 | Default (sound + vibrate) |
| 1 | High (bypasses quiet hours) |
| 2 | **Emergency** — repeats until user acks; requires `retry` and `expire` |

For DEEP6: P1 → priority 2 emergency, P2 → priority 1, P3 → priority 0.

### 12.3 Sender

```python
# alert_service/channels/pushover.py
import os
import httpx
from ..retry import retry_policy

USER_KEY = os.environ["PUSHOVER_USER_KEY"]
APP_TOKEN = os.environ["PUSHOVER_APP_TOKEN"]
URL = "https://api.pushover.net/1/messages.json"
_client = httpx.AsyncClient(timeout=10.0)

@retry_policy
async def _send(payload):
    r = await _client.post(URL, data=payload)
    r.raise_for_status()
    return r.json()

async def send_high(evt):
    return await _send({
        "token": APP_TOKEN,
        "user": USER_KEY,
        "title": f"DEEP6 {evt.SignalType} {evt.Instrument}",
        "message": evt.Message,
        "priority": 1,
        "sound": "siren" if evt.Priority == "P1" else "pushover",
        "url": f"https://deep6.example/dashboard?alert={evt.Id}",
        "url_title": "View in dashboard",
    })

async def send_emergency(evt):
    return await _send({
        "token": APP_TOKEN,
        "user": USER_KEY,
        "title": f"DEEP6 CRITICAL — {evt.SignalType}",
        "message": evt.Message,
        "priority": 2,
        "retry": 60,        # repeat every 60s
        "expire": 1800,     # for 30 minutes
        "sound": "alien",   # distinctive — won't be confused with normal Pushover
        "url": f"https://deep6.example/dashboard?alert={evt.Id}",
        "url_title": "Acknowledge",
    })
```

`retry` minimum is 30s, `expire` maximum is 10800s (3hr) per API docs. 60/1800 is the DEEP6 default for drawdown alerts: nag every minute for 30 minutes, then give up (you're either dealing with it by then or you're not at the desk).

The 2026 [Pushover update](https://blog.pushover.net/) changed sending limits to per-account from per-application starting May 2026 — this matters for high-volume use cases but DEEP6 is well within free limits.

---

## §13. Mobile Push (FCM, when you ship a DEEP6 mobile app)

If you eventually ship a DEEP6 mobile app, FCM is the unified path. Per the [FCM iOS quickstart](https://firebase.google.com/docs/cloud-messaging/ios/get-started) and the [Courier APNs vs FCM comparison](https://www.courier.com/integrations/compare/apple-push-notification-vs-firebase-fcm):

- **FCM** = unified Android + iOS + web. Free, unlimited.
- **APNs direct** = iOS only. Requires Apple Developer cert ($99/yr).
- FCM iOS path = FCM relays through APNs anyway — Firebase manages the cert.
- Legacy FCM HTTP API was deprecated June 2024; use **FCM HTTP v1** with OAuth2 service account.

```python
# alert_service/channels/fcm.py
import os, json, time
import httpx
from google.oauth2 import service_account
import google.auth.transport.requests

SERVICE_ACCOUNT_FILE = os.environ["FCM_SERVICE_ACCOUNT_JSON"]
PROJECT_ID = os.environ["FCM_PROJECT_ID"]
DEVICE_TOKEN = os.environ["DEEP6_DEVICE_FCM_TOKEN"]

_credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/firebase.messaging"],
)
_client = httpx.AsyncClient(timeout=10.0)

def _access_token():
    _credentials.refresh(google.auth.transport.requests.Request())
    return _credentials.token

async def send(evt):
    token = _access_token()
    payload = {
        "message": {
            "token": DEVICE_TOKEN,
            "notification": {
                "title": f"{evt.SignalType} {evt.Instrument} {evt.Price:.2f}",
                "body": evt.Message,
            },
            "data": {
                "alert_id": evt.Id,
                "signal_type": evt.SignalType,
                "priority": evt.Priority,
                "confidence": str(evt.Confidence),
            },
            "apns": {
                "headers": {"apns-priority": "10" if evt.Priority in ("P1", "P2") else "5"},
                "payload": {"aps": {"sound": "alert.caf" if evt.Priority == "P1" else "default"}}
            },
            "android": {
                "priority": "HIGH" if evt.Priority in ("P1", "P2") else "NORMAL",
                "notification": {"channel_id": f"deep6_{evt.Priority.lower()}"}
            }
        }
    }
    r = await _client.post(
        f"https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
    )
    r.raise_for_status()
    return r.json()
```

**Until you ship the mobile app, use Pushover.** It's strictly faster to ship and the cost ($5 one-time vs $99/yr Apple Developer + dev time) is overwhelmingly favorable. FCM only matters when you want branding ("DEEP6" in the notification chrome) or features Pushover doesn't provide (action buttons mid-trade, in-app rendering).

---

## §14. Custom Webhook (the integration meta-channel)

The most strategically important channel. A user-configured webhook URL receives every DEEP6 alert as JSON. From there it can be wired into Zapier, n8n, IFTTT, Make.com, HomeAssistant, a custom dashboard, a TradingView strategy.alert handler, anything.

### 14.1 Payload schema

```json
{
  "version": "1",
  "event_type": "alert.fired",
  "alert_id": "ABS_NQ_18452.25_1713269520",
  "signal_type": "ABS",
  "instrument": "NQ 12-25",
  "timestamp": "2026-04-16T20:32:01.234Z",
  "price": 18452.25,
  "confidence": 87,
  "priority": "P2",
  "message": "Absorption at 18452.25 — bid stack 1240 absorbed in 4s",
  "context": {
    "delta": -1240,
    "duration_ms": 4023,
    "bar_index": 412,
    "bar_close": 18451.75
  },
  "links": {
    "dashboard": "https://deep6.example/dashboard?alert=ABS_NQ_18452.25_1713269520",
    "screenshot": "https://deep6.example/static/screenshots/ABS_NQ_18452.25_1713269520.png"
  }
}
```

### 14.2 Sender with HMAC

Per the [HMAC webhook security guide](https://webhooks.fyi/security/hmac), every outbound webhook is signed with HMAC-SHA256 over the raw body, with a timestamp to prevent replay (Stripe's pattern, 5-minute window):

```python
# alert_service/channels/custom_webhook.py
import hmac, hashlib, json, os, time
import httpx
from ..retry import retry_policy

WEBHOOK_URL = os.environ["DEEP6_CUSTOM_WEBHOOK_URL"]
WEBHOOK_SECRET = os.environ["DEEP6_CUSTOM_WEBHOOK_SECRET"].encode()
_client = httpx.AsyncClient(timeout=10.0)

def sign(body: bytes, timestamp: str) -> str:
    msg = f"{timestamp}.".encode() + body
    return hmac.new(WEBHOOK_SECRET, msg, hashlib.sha256).hexdigest()

@retry_policy
async def send(evt):
    payload = {
        "version": "1",
        "event_type": "alert.fired",
        "alert_id": evt.Id,
        "signal_type": evt.SignalType,
        "instrument": evt.Instrument,
        "timestamp": evt.Timestamp.isoformat(),
        "price": evt.Price,
        "confidence": evt.Confidence,
        "priority": evt.Priority,
        "message": evt.Message,
        "context": evt.Context or {},
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    ts = str(int(time.time()))
    sig = sign(body, ts)
    r = await _client.post(
        WEBHOOK_URL,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Deep6-Timestamp": ts,
            "X-Deep6-Signature": f"sha256={sig}",
        },
    )
    r.raise_for_status()
    return r.status_code
```

**Receiver verification (for the user's reference):**

```python
import hmac, hashlib, time

def verify(secret: bytes, body: bytes, signature_header: str, timestamp_header: str,
           tolerance_seconds: int = 300) -> bool:
    if abs(time.time() - int(timestamp_header)) > tolerance_seconds:
        return False  # replay protection
    expected = hmac.new(secret, f"{timestamp_header}.".encode() + body, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)  # timing-safe
```

The [Hookdeck SHA256 signature guide](https://hookdeck.com/webhooks/guides/how-to-implement-sha256-webhook-signature-verification) and [GitHub's webhook validation doc](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries) are the canonical references for this pattern. Always use `hmac.compare_digest` to defeat timing attacks.

---

## §15. Deduplication + Throttling

### 15.1 Why both

- **Dedup** = "this exact alert (same id) within N seconds → suppress entirely".
- **Throttle** = "any alert of this signal type within N seconds → suppress new ones".

You need both. Dedup catches NinjaScript firing the same event twice (race in OnMarketData → OnBarUpdate). Throttle prevents notification fatigue when 10 absorption alerts fire in 30 seconds across nearby price levels.

### 15.2 Redis implementation

Per [Redis data deduplication patterns](https://redis.io/tutorials/data-deduplication-with-redis/) and the [Architecture Weekly distributed dedup post](https://www.architecture-weekly.com/p/deduplication-in-distributed-systems):

```python
# alert_service/dedupe.py
import redis.asyncio as aioredis

redis = aioredis.from_url("redis://localhost:6379/0")

async def is_duplicate(alert_id: str) -> bool:
    # Atomic check-and-set: returns True if the key was newly created (== first time)
    was_set = await redis.set(f"dedup:{alert_id}", "1", nx=True, ex=300)
    return not was_set  # if not newly set, it already existed

async def mark_seen(alert_id: str, ttl: int = 300):
    await redis.set(f"dedup:{alert_id}", "1", ex=ttl)

# alert_service/throttle.py
async def is_throttled(signal_type: str) -> bool:
    """Allow at most N alerts of this signal type per minute."""
    limits = {"ABS": 5, "EXH": 5, "IMB3": 10, "BIG": 20, "ENTRY": 100, "EXIT": 100}
    cap = limits.get(signal_type, 30)
    key = f"throttle:{signal_type}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    return count > cap
```

`SET NX EX` is the atomic primitive — one Redis round-trip, no race. `INCR + EXPIRE` is the canonical sliding-window throttle (technically a fixed window; for true sliding, see Redis-cell or token-bucket with Lua).

### 15.3 Smart batching

For P3/P4 only, accumulate alerts of the same `signal_type` for a short window and emit one combined message:

```python
# alert_service/batcher.py
import asyncio
from collections import defaultdict

BATCH_WINDOW = 30  # seconds
_pending = defaultdict(list)
_flush_tasks = {}

async def maybe_batch(evt) -> bool:
    """Returns True if the alert was batched (don't send individually)."""
    if evt.Priority in ("P1", "P2"):
        return False
    key = f"{evt.SignalType}:{evt.Instrument}"
    _pending[key].append(evt)
    if key not in _flush_tasks:
        _flush_tasks[key] = asyncio.create_task(_flush_after(key))
    return True

async def _flush_after(key):
    await asyncio.sleep(BATCH_WINDOW)
    batch = _pending.pop(key, [])
    _flush_tasks.pop(key, None)
    if batch:
        await emit_batch_summary(batch)

async def emit_batch_summary(batch):
    # Construct a synthetic AlertEvent summarizing the batch and route it
    summary = batch[0].copy()
    summary.Id = f"BATCH_{batch[0].SignalType}_{int(batch[0].Timestamp.timestamp())}"
    summary.Message = f"{len(batch)} {batch[0].SignalType} signals, prices {min(b.Price for b in batch):.2f}-{max(b.Price for b in batch):.2f}"
    summary.Context = {"batch_size": len(batch), "alert_ids": [b.Id for b in batch]}
    await route_alert(summary)
```

---

## §16. Quiet Hours

```python
# alert_service/quiet_hours.py
from datetime import datetime, time
from zoneinfo import ZoneInfo

USER_TZ = ZoneInfo("America/New_York")

# Configurable per user — start/end in user's local tz
QUIET_START = time(22, 0)   # 10pm
QUIET_END   = time(6, 30)   # 6:30am

# Channels allowed during quiet hours (P1 still fires everything)
QUIET_HOUR_CHANNELS = {"discord", "telegram", "fcm"}  # silent push only

def is_quiet_now() -> bool:
    now = datetime.now(USER_TZ).time()
    if QUIET_START < QUIET_END:
        return QUIET_START <= now <= QUIET_END
    # crosses midnight
    return now >= QUIET_START or now <= QUIET_END

def channel_allowed_in_quiet_hours(channel: str) -> bool:
    return channel in QUIET_HOUR_CHANNELS
```

Routing layer skips channels not in `QUIET_HOUR_CHANNELS` for non-P1 alerts during quiet hours. P1 always fires everywhere — that's the whole point of P1.

For NQ specifically: quiet hours typically `22:00-06:30 ET` because Asia session opens 18:00 ET and London 03:00 ET, but you only want alerts during your trading windows (most NQ traders work 04:00 ET pre-market through 16:00 ET post-RTH).

---

## §17. Audit Log + Forensics

Every alert that's routed produces multiple audit rows (one per channel attempt). Schema:

```sql
CREATE TABLE alert_audit (
    audit_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id      TEXT NOT NULL,
    signal_type   TEXT NOT NULL,
    instrument    TEXT NOT NULL,
    fired_at      TEXT NOT NULL,        -- ISO timestamp from NT8
    received_at   TEXT NOT NULL,        -- when bridge got it
    routed_at     TEXT,                 -- when fan-out completed
    channel       TEXT,                 -- 'discord', 'sms', etc. NULL for routing-level events
    status        TEXT NOT NULL,        -- 'queued', 'deduped', 'throttled', 'sent', 'failed', 'dead_letter'
    latency_ms    INTEGER,              -- per-channel send latency
    error         TEXT,                 -- on failure
    payload_json  TEXT NOT NULL,        -- full event for replay
    response      TEXT                  -- channel response body / message ID
);
CREATE INDEX idx_audit_alert ON alert_audit(alert_id);
CREATE INDEX idx_audit_fired ON alert_audit(fired_at);
CREATE INDEX idx_audit_channel_status ON alert_audit(channel, status);
```

```python
# alert_service/audit.py
import sqlite3, json
from datetime import datetime
from contextlib import contextmanager

DB_PATH = "deep6_alerts.db"

@contextmanager
def db():
    con = sqlite3.connect(DB_PATH)
    try: yield con; con.commit()
    finally: con.close()

async def audit_log(evt, channel=None, status="queued", error=None,
                    latency_ms=None, response=None):
    with db() as con:
        con.execute("""
          INSERT INTO alert_audit (
            alert_id, signal_type, instrument, fired_at, received_at,
            channel, status, latency_ms, error, payload_json, response
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            evt.Id, evt.SignalType, evt.Instrument,
            evt.Timestamp.isoformat(),
            datetime.utcnow().isoformat(),
            channel, status, latency_ms, error,
            evt.model_dump_json(),
            response,
        ))
```

For high volume, switch to async sqlite (`aiosqlite`) or Postgres. JSONL is the simplest possible alternative — append a line per event, grep for forensics. **For DEEP6, SQLite is plenty** — alert volume is on the order of hundreds/day, not millions/sec.

**Compliance.** Some regulators (especially around prop-trading firm rules) want demonstrable alert delivery for risk events. A SQLite audit log with timestamps + delivery status fulfills this trivially. Keep 1 year minimum.

---

## §18. Configuration UI Schema

This is what the dashboard exposes to the user:

```json
{
  "version": "1",
  "user_id": "michael.gonzalez5",
  "channels": {
    "discord":   { "enabled": true,  "webhook_url": "https://discord.com/api/webhooks/..." },
    "telegram":  { "enabled": true,  "token": "...", "chat_id": "..." },
    "sms":       { "enabled": true,  "twilio_messaging_sid": "MGxxx", "to_number": "+1..." },
    "email":     { "enabled": true,  "to_address": "michael.gonzalez5@gmail.com",
                   "provider": "postmark", "token_ref": "vault://postmark" },
    "pushover":  { "enabled": true,  "user_key": "...", "app_token": "..." },
    "fcm":       { "enabled": false, "device_token": null },
    "custom":    { "enabled": true,  "url": "https://make.com/...", "secret_ref": "vault://make-hmac" }
  },
  "priority_routing": {
    "P1": ["discord", "telegram", "sms", "email", "pushover_emergency", "custom"],
    "P2": ["discord", "telegram", "email", "pushover_high", "custom"],
    "P3": ["discord", "telegram"],
    "P4": []
  },
  "signal_overrides": {
    "ABS":     { "min_confidence": 75, "channels_add": [], "channels_remove": [] },
    "EXH":     { "min_confidence": 75 },
    "IMB3":    { "min_confidence": 0,  "throttle_per_min": 10 },
    "ENTRY":   { "channels_add": ["sms"] },
    "DD_LIMIT":{ "force_priority": "P1" }
  },
  "quiet_hours": {
    "enabled": true,
    "tz": "America/New_York",
    "start": "22:00",
    "end":   "06:30",
    "channels_allowed": ["discord", "telegram", "fcm"],
    "p1_overrides": true
  },
  "rate_caps": {
    "sms_per_day": 50,
    "discord_per_min": 25,
    "email_per_hour": 30
  }
}
```

Validation: **Pydantic** model on the FastAPI side enforces this schema. UI sends a complete config object on save; service validates, atomically swaps. Each channel has a "Send test alert" button that fires a synthetic `P4` event through that channel only — closes the loop on "did the user actually configure this right".

Secrets storage: never in the JSON itself. Reference vault entries (`vault://...`) and resolve at runtime. For solo-trader use, OS keychain (Windows Credential Manager / macOS Keychain) via `keyring` Python lib is sufficient.

---

## §19. Failure Modes + Observability

### 19.1 Failure-mode checklist

| Failure | Detection | Response |
|---|---|---|
| Discord 5xx | HTTP status | Retry per tenacity policy; after 5 fails → dead-letter, fire P1 meta-alert via Pushover |
| Discord 429 | HTTP 429 + Retry-After | Honor header, requeue after delay |
| Telegram 429 | HTTP 429 + `parameters.retry_after` | Same as Discord |
| SMS failure (carrier rejected) | Twilio status callback `failed` | Audit log + Pushover meta-alert |
| Email bounce | Postmark webhook back | Audit log; if persistent, disable channel + P1 meta |
| Pushover unreachable | HTTP timeout | Retry; this is your meta-alert channel so failure is double-bad — also write to local Windows toast |
| FastAPI service crashed | NT8 pipe write fails AND HTTP fallback fails | Dead-letter file in `Documents\NinjaTrader 8\deep6\` |
| NT8 crashes mid-alert | Bridge process sees pipe disconnect | Bridge logs "NT8 disconnected" → fires P1 via Pushover ("DEEP6 NT8 process died") |
| Redis down | `redis.set` throws | Fail open (route alert anyway) — don't suppress alerts because dedup is broken |
| Disk full (audit log) | sqlite write fails | Log to stderr, continue routing — never let logging block alerting |
| Webhook URL leaked | External monitoring (Discord audit log) | Rotate webhook URL via Discord UI; new URL injected via vault |
| User's phone is off | FCM/APNs queues, delivers when device wakes | Acceptable — that's the design |
| Critical alert at 3am, user asleep | Pushover emergency keeps repeating until acked | Working as intended |

### 19.2 Health endpoints

```python
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "queue_depth": alert_queue.qsize(),
        "uptime_seconds": int(time.time() - START_TIME),
        "last_alert_at": LAST_ALERT_AT,
    }

@app.get("/health/channels")
async def channel_health():
    # Per-channel last-success timestamp from audit log
    with db() as con:
        rows = con.execute("""
            SELECT channel, MAX(received_at) AS last_success
            FROM alert_audit WHERE status = 'sent' GROUP BY channel
        """).fetchall()
    return {row[0]: row[1] for row in rows}
```

### 19.3 Prometheus metrics

Per the [Prometheus + Grafana monitoring guide](https://yrkan.com/blog/grafana-prometheus-monitoring/) and the [LiveKit/asserts P99 best practices](https://www.asserts.ai/blog/why-my-p99-mean/), expose:

```python
from prometheus_client import Counter, Histogram, Gauge

alerts_total = Counter("deep6_alerts_total", "Alerts received", ["signal_type", "priority"])
sends_total  = Counter("deep6_alert_sends_total", "Channel sends", ["channel", "status"])
send_latency = Histogram("deep6_alert_send_latency_seconds", "Per-channel send latency",
                         ["channel"], buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
queue_depth  = Gauge("deep6_alert_queue_depth", "Pending alerts in queue")
```

Grafana dashboard panels:
- **Alert rate** by `signal_type` (rps).
- **Per-channel success rate** = `rate(sends_total{status="sent"}) / rate(sends_total)`.
- **Per-channel P99 latency** = `histogram_quantile(0.99, rate(send_latency_bucket[5m]))`.
- **Queue depth** (saturation indicator).
- **Dead-letter count** (anything > 0 is a paged incident).

Alertmanager rule:

```yaml
- alert: Deep6AlertChannelDown
  expr: rate(deep6_alert_sends_total{status="sent"}[5m]) == 0
        and rate(deep6_alert_sends_total[5m]) > 0
  for: 5m
  labels: { severity: critical }
  annotations:
    summary: "DEEP6 channel {{ $labels.channel }} 100% failing"
```

You're alerting on your alerting system. That's correct — without it you'd never know Discord was wedged for 4 hours.

---

## §20. Channel Comparison Reference Table

| Channel | Setup time | Cost | Latency (P50 / P99) | Reliability | When to use | When to avoid |
|---|---|---|---|---|---|---|
| **NT8 toast** | Built-in | $0 | < 50 ms / 200 ms | High (in-process) | Always; primary visual | When you're not at desk |
| **NT8 sound** | WAV file | $0 | < 20 ms blocking warning | High | Always; primary auditory | OnRender / per-tick |
| **Discord webhook** | 5 min | $0 | 200 ms / 800 ms | High | Default text channel; team notifications | When channel hits 30/min cap |
| **Telegram bot** | 10 min | $0 | 300 ms / 1.2 s | High | Personal notifications + action buttons | Group broadcasts (rate limits hurt) |
| **Pushover** | 10 min | $5 one-time | 400 ms / 2 s | Very High | Mobile + desktop push, emergency-ack | When you need branded UX |
| **SMS (Twilio)** | 1-3 days (10DLC) | $0.012/msg + $1.15/mo | 1 s / 30 s | High | P1 only | Anything else (cost + fatigue) |
| **Email (Postmark)** | 30 min | $15/mo (10k/mo) | 800 ms / 3 s | Very High | Audit/journal + chart attachments | Real-time / urgent |
| **FCM** | 4-8 hr (mobile app needed) | Free | 300 ms / 2 s | High | Production mobile app | Until you've shipped the app |
| **APNs direct** | 2-3 days (cert) | $99/yr Apple | 200 ms / 1.5 s | Very High | iOS-only, no FCM | Most cases (FCM is simpler) |
| **Custom webhook** | 5 min | $0 | Depends on receiver | Depends on receiver | Zapier/n8n/IFTTT integration | When schema changes break consumers |
| **Named pipe (bridge)** | (internal) | $0 | 0.1 ms / 1 ms | Very High (same machine) | NT8 → FastAPI primary path | Cross-machine |
| **HTTP localhost (bridge)** | (internal) | $0 | 0.3 ms / 5 ms | Very High | Pipe fallback | Primary; always pipe-first |

---

## §21. DEEP6 Signal Type → Alert Specification

| Signal | Priority | Default channels | Sound | Cooldown | Notes |
|---|---|---|---|---|---|
| Absorption (conf ≥ 85) | P2 | Toast, Sound, Discord, Telegram, Pushover-high, Email | `absorption.wav` | 30s | Includes screenshot |
| Absorption (conf 70-84) | P3 | Toast, Sound, Discord, Telegram | `absorption.wav` | 30s | Batched if > 3 in 30s |
| Exhaustion (conf ≥ 85) | P2 | Same as ABS P2 | `exhaustion.wav` | 30s | |
| Stacked imbalance 3+ | P3 | Toast, Sound, Discord | `imbalance3.wav` | 10s | Often clusters; batching critical |
| Big order ≥ 500 | P2 | Toast, Sound, Discord, Telegram | `bigorder.wav` | 5s | |
| Big order 200-499 | P3 | Toast, Sound, Discord | `bigorder.wav` | 5s | |
| Confidence ≥ 85 (any signal) | promoted to P2 | (per signal) | (per signal) | — | Confidence override always elevates |
| Trade ENTRY | P2 | Toast, Sound, Discord, SMS, Telegram, Pushover, Email | `entry.wav` | 0s | No cooldown — never miss |
| Trade EXIT (with P&L) | P2 | Same as ENTRY | `exit.wav` | 0s | Body includes realized P&L |
| Stop hit | P2 | Same as ENTRY | `stop.wav` | 0s | |
| Daily P&L target reached | P2 | Toast, Sound, Discord, Telegram, Email | `goal.wav` | n/a | One-shot per day |
| **Daily DD limit hit** | **P1** | **All channels including SMS + Pushover EMERGENCY** | `critical.wav` | 0s | **Trading interrupt** |
| Connection lost (price) | P1 | Toast, Sound, Discord, Pushover-emergency, SMS | `disconnect.wav` | 5s | Per-feed |
| Connection lost (orders) | P1 | Same as above | `disconnect.wav` | 5s | |
| Connection restored | P3 | Toast, Discord | `reconnect.wav` | 60s | Don't spam reconnect bursts |
| System error (NT exception) | P1 | Toast, Discord, Pushover-emergency, Email | `critical.wav` | 30s | Body includes stack trace |

---

## §22. Anti-Pattern Catalog

1. **Alert per tick / per render frame.** Notification fatigue + dropped frames + Alerts Window flooded. Use `rearmSeconds` in NT8's `Alert()` and Redis throttle in bridge.

2. **Same alert across all channels with no priority filtering.** Sending P3 informational stacked-imbalance to SMS within a week kills your willingness to look at the phone. Use the priority matrix religiously.

3. **No-acknowledgment alerts.** P1 must require explicit ack. Otherwise at 3am the user puts the phone in DnD and misses the next one.

4. **Generic "Alert!" message with no context.** Useless. Body must include signal type, instrument, price, confidence, and the "why" (e.g., "delta -1240 absorbed in 4s"). Subject line scannable on a lock screen.

5. **Synchronous PlaySound in OnRender / OnMarketData.** Drops chart frames. Always `Task.Run(() => PlaySound(...))` with a cooldown timer.

6. **No retry on transient network failure.** A blip in the user's wifi shouldn't lose an alert. Tenacity exponential backoff with jitter, max 5 attempts.

7. **Storing webhook URLs in plaintext config files.** Anyone who clones the repo / takes the laptop has your Discord webhook + Twilio credentials. Use `keyring` (OS keychain) or a vault. Discord webhooks are equivalent to a write-only API key for that channel.

8. **No dead-letter handling.** Alert lost forever = silent failure = unmonitored gap. Persist failed alerts to disk + meta-alert via Pushover.

9. **Blocking the alert queue with channel sends.** One channel's slowness blocks all others. Each channel send has its own timeout; `asyncio.gather` runs them in parallel.

10. **Alerting on alerting that itself is broken.** Meta-alert for "Discord channel failed" must use a **different** channel (Pushover or SMS). If your Discord webhook is dead, sending a meta-alert via Discord doesn't help.

11. **No quiet hours.** Phone vibrates at 3am for an informational signal → user disables notifications entirely → misses real P1 the next day.

12. **Reusing alert IDs across signal types.** `Alert("absorption", ...)` and `Alert("exhaustion", ...)` with the same id collides on NT8's rearm and dedupe. Always `f"{SIGNAL_TYPE}_{INSTRUMENT}_{BAR_INDEX}_{PRICE_LEVEL}"`.

13. **Hardcoded sound paths.** Breaks on different machines / username. Resolve via `Environment.GetFolderPath(SpecialFolder.MyDocuments)` + relative path.

14. **No timestamp validation on incoming custom webhook.** Replay attacks. HMAC + 5-minute timestamp window.

15. **Audit log writes that block alert sends.** A full disk shouldn't suppress alerts. Audit failures are logged to stderr; alerts continue.

16. **Configuration changes that aren't atomic.** Saving config mid-alert fan-out can route half an alert under the old rules and half under the new. Atomic config swap (load full config at start of each `route_alert` invocation, copy-on-write).

17. **No "test alert" button per channel.** Users will configure Discord webhook with a typo and discover it 6 weeks later. Every channel needs a `POST /channels/{name}/test` that fires a synthetic P4.

---

## §23. Failure-Mode Checklist (operational)

Before going live with this pipeline:

- [ ] Discord webhook URL set; sent test alert; received.
- [ ] Telegram bot created via BotFather; chat ID verified; test alert received.
- [ ] Twilio account created; phone number purchased; 10DLC brand + campaign registered (or sole-prop registered); test SMS received.
- [ ] Postmark account created; sender domain DKIM/SPF verified; test email received in inbox (not spam).
- [ ] Pushover account + iOS app + macOS app installed; test alert received with sound; test emergency P1 received and acknowledged.
- [ ] Custom webhook receiver set up (n8n / Make / Zapier); HMAC verification tested; replay-window enforcement tested.
- [ ] All credentials in OS keychain, not in config files.
- [ ] Quiet hours configured; verified P3 suppressed at midnight; verified P1 still fires.
- [ ] Dedup tested: same alert id within 30s → second one doesn't fire.
- [ ] Throttle tested: 6 ABS alerts in 60s → 6th throttled.
- [ ] Dead-letter file populated when FastAPI service is killed; replayed on restart.
- [ ] Audit DB created; rows present after each test alert; queryable by channel + status.
- [ ] Prometheus metrics scraped; Grafana dashboard renders; "channel down" alert fires when Discord webhook deliberately broken.
- [ ] NT8 connection lost test (kill Rithmic gateway): P1 fires within 5s on Pushover.
- [ ] NT8 process killed test: bridge detects pipe disconnect within 10s, P1 fires via Pushover.
- [ ] Sound files (`.wav`) play successfully via NT8 PlaySound for each signal type.
- [ ] Toast notifications dispatch to UI thread (no exception in NT8 log).
- [ ] All channels respect rate caps configured in `rate_caps` block.
- [ ] At least one cross-machine alert path tested (NT8 Windows → bridge → Mac dashboard via Tailscale).

---

## §24. Architecture Summary Diagram

```
+========================== Windows (NT8 box) ===========================+
|                                                                        |
|  +--- NinjaScript -------------------------+                           |
|  | Indicator/Strategy/AddOn                |                           |
|  | OnBarUpdate, OnExecutionUpdate,         |                           |
|  | OnConnectionStatusUpdate, etc.          |                           |
|  |                                         |                           |
|  | +--> Alert(id, P1/P2/P3, msg, .wav,     |                           |
|  | |       rearmSec, brushes)              |                           |
|  | |          \                            |                           |
|  | |           \-> NT Alerts Window        |                           |
|  | |               + sound (PlaySound)     |                           |
|  | |                                       |                           |
|  | +--> Deep6AlertBridge.Instance.Send(    |                           |
|  |        AlertEvent { Id, SignalType,    | ---------+                |
|  |        Priority, ... })                |          |                |
|  +-----------------------------------------+          v                |
|                                                                        |
|                    [BlockingCollection queue]                          |
|                                |                                       |
|                    [Background dispatcher]                             |
|                                |                                       |
|                  +-------------+--------------+                        |
|                  |                            |                        |
|                  v                            v                        |
|         NamedPipe "deep6-alert-bus"    HTTP POST localhost:8765        |
|                                       (fallback if pipe unavailable)   |
|                                                                        |
|  +---- FastAPI alert-service (Python, on the same Windows box) ------+ |
|  |                                                                   | |
|  |  pipe_server() + http_ingest()  ->  asyncio.Queue                 | |
|  |                                          |                        | |
|  |                                          v                        | |
|  |                                   processor()                     | |
|  |                                          |                        | |
|  |          +-------------------------------+--------+               | |
|  |          v                                        |               | |
|  |  is_duplicate(Redis)?  --yes-->  audit deduped    |               | |
|  |          | no                                     |               | |
|  |          v                                        |               | |
|  |  is_throttled(Redis)?  --yes--> audit throttled   |               | |
|  |          | no                                     |               | |
|  |          v                                        |               | |
|  |  is_quiet_hours()? -> filter channels             |               | |
|  |          |                                        |               | |
|  |          v                                        |               | |
|  |  PRIORITY_MATRIX[priority] -> [channel list]      |               | |
|  |          |                                        |               | |
|  |          v   asyncio.gather(per-channel timeout)  |               | |
|  | +--------+--------+--------+--------+--------+----+----+          | |
|  | |        |        |        |        |        |        |          | |
|  | v        v        v        v        v        v        v          | |
|  | discord  tg     sms      email   pushover  fcm     custom         | |
|  | (httpx + tenacity exponential-jitter retry, dead-letter on fail)  | |
|  |                                                                   | |
|  |  ---> SQLite audit_log (per channel, per attempt)                 | |
|  |  ---> Prometheus metrics (rate, success, P99 latency)             | |
|  +-------------------------------------------------------------------+ |
+========================================================================+
                                |
                                | (Tailscale tunnel)
                                v
+======================= macOS (DEEP6 dashboard) ========================+
|                                                                        |
|   FastAPI dashboard backend  <--  SSE stream of alerts                 |
|                                                                        |
|   Next.js frontend           <--  WebSocket footprint stream           |
|                              <--  Recent alerts list (REST)            |
+========================================================================+
```

---

## Sources

- [NinjaTrader Alert() docs](https://ninjatrader.com/support/helpguides/nt8/alert.htm)
- [NinjaTrader AlertCallback docs](https://ninjatrader.com/support/helpguides/nt8/alertcallback.htm)
- [NinjaTrader Alert and Debug Concepts](https://ninjatrader.com/support/helpGuides/nt8/alert_and_debug_concepts.htm)
- [NinjaTrader Configuring Alerts](https://ninjatrader.com/support/helpguides/nt8/configuring_alerts.htm)
- [NinjaTrader Using Alerts](https://ninjatrader.com/support/helpGuides/nt8/using_alerts.htm)
- [NinjaTrader PlaySound docs](https://ninjatrader.com/support/helpGuides/nt8/playsound.htm)
- [NinjaTrader Multi-Threading Considerations](https://ninjatrader.com/support/helpGuides/nt8/multi-threading.htm)
- [NinjaTrader OnConnectionStatusUpdate docs](https://ninjatrader.com/support/helpGuides/nt8/onconnectionstatusupdate.htm)
- [NinjaTrader ConnectionStatusEventArgs](https://ninjatrader.com/support/helpguides/nt8/connectionstatuseventargs.htm)
- [NinjaTrader OnExecutionUpdate](https://ninjatrader.com/support/helpguides/nt8/onexecutionupdate.htm)
- [NinjaTrader OnOrderUpdate](https://ninjatrader.com/support/helpguides/nt8/onorderupdate.htm)
- [NinjaTrader OnOrderUpdate / OnExecutionUpdate Reference Sample](https://ninjatrader.com/support/helpGuides/nt8/using_onorderupdate_and_onexec.htm)
- [Forum: PlaySound on separate thread](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/101354-how-to-run-playsound-in-separate-thread)
- [Forum: OnConnectionStatusUpdate PriceStatus](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/92885-onconnectionstatusupdate-pricestatus)
- [Forum: OnOrderUpdate vs OnExecutionUpdate vs OnExecution](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/1234525-whats-best-to-use-onexecutionupdate-or-onorderupdate-or-onexecution)
- [pipesvshttp benchmark (named pipes vs HTTP IPC)](https://github.com/nickntg/pipesvshttp)
- [Anthony Simmon: Local IPC over named pipes in .NET](https://anthonysimmon.com/local-ipc-over-named-pipes-aspnet-core-streamjsonrpc-dotnet/)
- [Baeldung: IPC performance comparison](https://www.baeldung.com/linux/ipc-performance-comparison)
- [Patrick Dahlke: iceoryx2 C# vs .NET IPC numbers](https://patrickdahlke.com/posts/iceoryx2-csharp-performance/)
- [.NET NamedPipeClientStream docs](https://learn.microsoft.com/en-us/dotnet/api/system.io.pipes.namedpipeclientstream?view=net-10.0)
- [Microsoft: Named pipes for network IPC](https://learn.microsoft.com/en-us/dotnet/standard/io/how-to-use-named-pipes-for-network-interprocess-communication)
- [Discord rate limits docs](https://docs.discord.com/developers/topics/rate-limits)
- [Discord webhooks guide (Birdie0)](https://birdie0.github.io/discord-webhooks-guide/other/rate_limits.html)
- [Discord embed color guide](https://birdie0.github.io/discord-webhooks-guide/structure/embed/color.html)
- [Discord webhooks complete guide (InventiveHQ)](https://inventivehq.com/blog/discord-webhooks-guide)
- [Telegram Bots FAQ](https://core.telegram.org/bots/faq)
- [grammY — Scaling Up IV: Flood Limits](https://grammy.dev/advanced/flood)
- [Twilio US SMS pricing](https://www.twilio.com/en-us/sms/pricing/us)
- [Twilio 10DLC pricing](https://help.twilio.com/articles/1260803965530-What-pricing-and-fees-are-associated-with-the-A2P-10DLC-service-)
- [Twilio Programmable SMS Python Quickstart](https://static0.twilio.com/docs/sms/quickstart/python)
- [Twilio T-Mobile carrier fee changes Jan 2026](https://help.twilio.com/articles/44609260499995)
- [Apidog: Twilio SMS API cost breakdown 2026](https://apidog.com/blog/twilio-sms-api-cost/)
- [Pushover API](https://pushover.net/api)
- [Pushover Receipts API](https://pushover.net/api/receipts)
- [Pushover blog updates](https://blog.pushover.net/)
- [Postmark vs SendGrid 2026](https://postmarkapp.com/compare/sendgrid-alternative)
- [BuildMVPFast: email API pricing comparison Apr 2026](https://www.buildmvpfast.com/api-costs/email)
- [Mailtrap: Best email APIs 2026](https://mailtrap.io/blog/email-api-flexibility/)
- [FCM iOS quickstart](https://firebase.google.com/docs/cloud-messaging/ios/get-started)
- [Courier APNs vs FCM comparison 2026](https://www.courier.com/integrations/compare/apple-push-notification-vs-firebase-fcm)
- [HMAC webhook security guide (webhooks.fyi)](https://webhooks.fyi/security/hmac)
- [GitHub: Validating webhook deliveries](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)
- [Hookdeck: SHA256 webhook signature verification](https://hookdeck.com/webhooks/guides/how-to-implement-sha256-webhook-signature-verification)
- [Hooklistener: Webhook security fundamentals 2026](https://www.hooklistener.com/learn/webhook-security-fundamentals)
- [Tenacity Python retry library](https://tenacity.readthedocs.io/)
- [Retry patterns: backoff, jitter, dead letter queues 2026 (Young Gao)](https://dev.to/young_gao/retry-patterns-that-actually-work-exponential-backoff-jitter-and-dead-letter-queues-75)
- [HTTPX async docs](https://www.python-httpx.org/async/)
- [HTTPX timeouts docs](https://www.python-httpx.org/advanced/timeouts/)
- [HTTPX resource limits](https://www.python-httpx.org/advanced/resource-limits/)
- [FastAPI webhook receiver guide (Greeden)](https://blog.greeden.me/en/2026/04/07/a-practical-guide-to-safely-implementing-webhook-receiver-apis-in-fastapi-from-signature-verification-and-retry-handling-to-idempotency-and-asynchronous-processing/)
- [Redis: Data deduplication patterns](https://redis.io/tutorials/data-deduplication-with-redis/)
- [Architecture Weekly: Deduplication in distributed systems](https://www.architecture-weekly.com/p/deduplication-in-distributed-systems)
- [LogicMonitor: Preventing alert fatigue](https://www.logicmonitor.com/blog/network-monitoring-avoid-alert-fatigue)
- [Better Stack: Solving noisy alerts and preventing alert fatigue](https://betterstack.com/community/guides/monitoring/best-practices-alert-fatigue/)
- [PagerDuty: Understanding alert fatigue](https://www.pagerduty.com/resources/digital-operations/learn/alert-fatigue/)
- [TradeFundrr: Setting alerts on trading platforms](https://tradefundrr.com/setting-alerts-on-trading-platforms/)
- [NCBI: Auditory factors in display design](https://nap.nationalacademies.org/read/5436/chapter/7)
- [AAMI: Designing effective alarm sounds](https://array.aami.org/doi/full/10.2345/0899-8205-45.4.290)
- [Max Rovensky: How to design a pleasant notification sound](https://medium.com/@fivepointseven/how-to-design-a-pleasant-alert-sound-2ddf7a9724de)
- [Microsoft: Send local toast notification from C#](https://learn.microsoft.com/en-us/windows/apps/design/shell/tiles-and-notifications/send-local-toast)
- [rafallopatka/ToastNotifications WPF library](https://github.com/rafallopatka/ToastNotifications)
- [async_rithmic Connecting docs](https://async-rithmic.readthedocs.io/en/latest/connection.html)
- [async_rithmic GitHub](https://github.com/rundef/async_rithmic)
- [Prometheus + Grafana monitoring guide](https://yrkan.com/blog/grafana-prometheus-monitoring/)
- [Asserts.ai: Why my P99 < average](https://www.asserts.ai/blog/why-my-p99-mean/)
