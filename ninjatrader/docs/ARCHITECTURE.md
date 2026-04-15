# DEEP6 Footprint — Architecture

## Data flow

```
  Rithmic Gateway
        │
        ▼
  NT8 Data Thread  ─── MarketDataType.Bid/Ask ─────► _bestBid / _bestAsk (double fields)
        │
        └─────────── MarketDataType.Last ──────────► OnMarketData
                                                       │
                                                       ▼
                                            aggressor classification
                                                 (price vs BBO)
                                                       │
                                                       ▼
                                            FootprintBar.AddTrade
                                                 (per-bar Dict)
                                                       │
                                                       ▼
                                               stored in _bars[]

  NT8 Bar Close ─── IsFirstTickOfBar on new bar ──► OnBarUpdate
                                                       │
                                                       ├─ prev.Finalize(priorCvd)
                                                       ├─ update ATR / vol EMA
                                                       ├─ detect session reset → ResetCooldowns
                                                       ├─ AbsorptionDetector.Detect
                                                       ├─ ExhaustionDetector.Detect
                                                       └─ Draw.Triangle*/Arrow* per signal
                                                          (GEX fetch is timer-driven, NOT bar-driven)

  NT8 Render Thread ──────────► OnRender
                                    │
                                    ├─ RenderGex(_gexProfile, ...)
                                    ├─ per visible bar: cells, imbalance, POC, VAH/VAL
                                    └─ SharpDX text layouts per cell

  System.Threading.Timer (60s) ─── GexTimerTick ──► MassiveGexClient.FetchAsync
                                         │
                                         ├─ success → _gexProfile (volatile), _gexFailCount=0, reschedule 60s
                                         └─ failure → _gexProfile UNCHANGED, backoff 5s → 15s → 60s → 120s cap
                                         │
                                         ▼
                                 _gexProfile (volatile)
                                         │
                                         └─► read by OnRender
```

## Threading model

| Thread | Entry point | Rules |
|---|---|---|
| NT data thread | `OnMarketData`, `OnMarketDepth` | Touch only `_bars`, `_bestBid`, `_bestAsk`. Never call `Draw.*` or `RenderTarget`. |
| NT bar/chart thread | `OnBarUpdate`, `OnStateChange`, `OnRender`, `OnRenderTargetChanged` | Main coordination thread. Owns detector calls, Draw.* invocations, SharpDX lifecycle. |
| Background timer | `GexTimerTick` (ThreadPool) | HTTP + volatile writes only. Touch no NT APIs. Re-entrance guarded by `Monitor.TryEnter(_gexTimerLock)`. Writes `_gexProfile`, `_gexLastSuccessStatus`, `_gexRetryStatus`. Self-schedules via `ScheduleNextGexTick` (60s steady; 5s/15s/60s/120s-cap backoff on failure). |

`_gexProfile` is a `volatile GexProfile` reference — atomic reference write on reassignment; `OnRender` reads a local copy at the start of each render.

## Rendering pipeline

1. `OnRenderTargetChanged` creates device-dependent SharpDX brushes and text formats once per render target. Brushes stay alive; `TextLayout` objects are built per-cell per-render and disposed.
2. `OnRender` iterates only `ChartBars.FromIndex..ChartBars.ToIndex` (visible bars), not the whole history.
3. Per visible bar:
   - Compute column bounds from `GetXByBarIndex` + `GetBarPaintWidth`.
   - Row height from `GetPixelsForDistance(TickSize)`.
   - For each price level in the bar's footprint: fill imbalance rect if triggered, then draw `"bid × ask"` text layout centered in the cell.
   - Draw POC bar, VAH/VAL lines.
4. GEX levels draw once across the full chart width (not per bar).

## State lifecycle

```
SetDefaults  — defaults for NinjaScriptProperty values, IsOverlay/DrawOnPricePanel flags
     │
     ▼
Configure    — copy property values into detector configs (runs before DataLoaded)
     │
     ▼
DataLoaded   — _bars clear, ATR window clear, detector cooldowns clear, GEX client init if key present
     │
     ▼
Historical   — NT replays historical ticks; OnMarketData fires for each; OnBarUpdate fires per bar close
     │
     ▼
Realtime     — same pipeline, live data
     │
     ▼
Terminated   — cancel GEX task, dispose HttpClient, dispose SharpDX brushes + fonts
```

## Memory management

- `_bars` is trimmed every bar close to the last 500 bar indexes. At 30s bars that's ~4 hours of session.
- SharpDX brushes: one `Dispose()` each in `DisposeDx()`; called in `Terminated` and at the start of `OnRenderTargetChanged` (target can change during chart resize).
- `TextLayout` per cell: `using` block → auto-disposed.
- HttpClient: single instance lifetime-bound to the indicator (not static) — disposed in `Terminated`.

## Failure modes

- **GEX fetch fails** → `_gexProfile` UNCHANGED (last-good levels keep rendering). Retry runs on exponential backoff (5s / 15s / 60s / cap 2 min). `_gexRetryStatus` banner shows countdown to next attempt alongside the sticky `_gexLastSuccessStatus`.
- **OnRenderTargetChanged runs with null target** → early return; no crash.
- **Unknown aggressor (price between spread)** → volume booked to `Cell.NeutralVol`; not counted in `BarDelta`; not visible in cell text. Matches Python DeltaEngine's unclassified-prints handling.
- **Bar skipped silently** (rare Rithmic hiccup) → `_bars[i-1]` is missing when `OnBarUpdate` fires on bar `i`; early return; that bar's signals are skipped. The OHLC reconcile in `OnBarUpdate` uses NT8's authoritative bar data, so even if `FootprintBar.AddTrade`'s internal OHLC is wrong, the finalized bar matches the chart.
