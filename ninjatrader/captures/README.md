# DEEP6 Capture Harness Format

## Overview

The capture harness records NinjaTrader 8 `OnMarketData` + `OnMarketDepth` events to a
deterministic NDJSON log file during live RTH sessions on the Apex sim account.
The harness is implemented in Wave 5 (Plan 17-05). This document defines the format
so that operators can begin recording live sessions off-phase.

## File Path Pattern

```
ninjatrader/captures/YYYY-MM-DD-session.ndjson
```

Example: `ninjatrader/captures/2026-04-15-session.ndjson`

One file per trading session (RTH open to close). Multiple sessions = multiple files.
Minimum 5 recorded sessions covering varied regimes (trending, balanced, news-driven)
are required before Wave 5 parity replay is declared passing (per CONTEXT.md D-07).

## Line Schema

Each line is a self-contained JSON object. Two event types:

### DOM update (`"type":"depth"`)

```json
{"type":"depth","ts_ms":1713196800123,"side":"bid","idx":0,"price":20001.75,"size":125}
{"type":"depth","ts_ms":1713196800124,"side":"ask","idx":0,"price":20002.00,"size":87}
```

| Field    | Type   | Description                                                        |
|----------|--------|--------------------------------------------------------------------|
| `type`   | string | Always `"depth"`                                                   |
| `ts_ms`  | int64  | Unix milliseconds (NY time from NT8 `DateTime.UtcNow.ToUnixMs()`) |
| `side`   | string | `"bid"` or `"ask"`                                                 |
| `idx`    | int    | DOM level index: 0 = best bid/ask, 1 = next, …, 39 = deepest      |
| `price`  | float  | Price at this DOM level                                            |
| `size`   | int64  | Quantity at this DOM level (0 = level removed)                     |

### Trade print (`"type":"trade"`)

```json
{"type":"trade","ts_ms":1713196800200,"price":20002.00,"size":5,"aggressor":1}
```

| Field       | Type   | Description                                                      |
|-------------|--------|------------------------------------------------------------------|
| `type`      | string | Always `"trade"`                                                 |
| `ts_ms`     | int64  | Unix milliseconds                                                |
| `price`     | float  | Trade price                                                      |
| `size`      | int64  | Trade quantity (contracts)                                       |
| `aggressor` | int    | `1` = buy aggressor (price >= bestAsk), `2` = sell aggressor (price <= bestBid), `0` = neutral/unknown |

## Session Boundary Event (`"type":"session"`)

```json
{"type":"session","ts_ms":1713196200000,"event":"open","date":"2026-04-15"}
{"type":"session","ts_ms":1713218400000,"event":"close","date":"2026-04-15"}
```

Optional but recommended. Marks RTH open (9:30 ET) and close (16:00 ET).

## Replay

The Wave 5 replay loader (`ninjatrader/tests/Replay/`) reads the NDJSON file line-by-line
and feeds events through:

1. The C# detector pipeline (`AbsorptionDetector` + `ExhaustionDetector` via registry)
2. A Databento MBO proxy (or log-to-MBO translator) feeding the Python engine

Parity assertion: C# signal count per session within ±2 per signal type vs Python
(per CONTEXT.md D-07 tolerance envelope).

## Notes

- Binary format was considered (write throughput) but NDJSON was chosen for debuggability.
  If benchmarks show NDJSON write throughput bottlenecks live capture, switch to a binary
  format (e.g., MessagePack or Protobuf). See CONTEXT.md D-10.
- The harness itself (NT8 `CaptureHarness.cs` indicator) is implemented in Wave 5.
- `ninjatrader/captures/*.ndjson` is git-ignored (large binary-ish files). Add to `.gitignore`
  if committing test fixtures; keep only schema documentation here.
