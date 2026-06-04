# DEEP6MASSIVEGEXMAP — Recovery Spec

## What it is

`DEEP6MassiveGexMap` is a NinjaTrader 8 overlay indicator that renders a Gamma Exposure map on the chart from a local JSON snapshot.

It is intentionally split into two parts:

1. `ninjatrader/Custom/Indicators/DEEP6/DEEP6MassiveGexMap.cs`
   - chart renderer only
   - no API key
   - polls a JSON file and draws levels + HUD

2. `scripts/massive_gex_map_service.py`
   - data producer / sidecar
   - owns Massive API access
   - fetches the options chain, computes GEX by strike, selects the actionable levels, probes the websocket, and writes `massive_gex_map.json`

This separation is the core design decision behind the indicator.

---

## Why we built it this way

The older DEEP6 GEX work fetched options data more directly from NinjaScript. That worked, but it created two problems:

- API credentials were too close to the NT8 layer.
- Every provider/auth/schema change forced indicator-side churn.

`DEEP6MassiveGexMap` fixed that by making NinjaTrader a pure renderer.

The Python sidecar handles:

- API key loading from env files
- REST pagination
- retry logic
- websocket auth/subscription probing
- options-chain aggregation
- strike selection
- atomic JSON writes

The NT8 side handles:

- file polling
- chart matching (`MNQ -> NQ`, `MES -> ES`)
- staleness display
- line/label rendering
- operator HUD

---

## Core files

### Primary implementation

- `ninjatrader/Custom/Indicators/DEEP6/DEEP6MassiveGexMap.cs`
- `scripts/massive_gex_map_service.py`

### Tests

- `tests/test_massive_gex_map_service.py`

### Related design/history artifacts

- `docs/TRADEGEX_ARCHITECTURE.md`
- git history around:
  - `MassiveGexClient.cs`
  - `DEEP6GexLevels.cs`
  - `gex_service_v2.py`
  - `GEXGammaOverlay.cs`
  - `GEXCommand.cs`

---

## High-level runtime flow

1. Python service loads `MASSIVE_API_KEY` from `.env`, `.env.local`, `scripts/.env`, or `scripts/.env.local`.
2. It fetches the underlying spot and futures spot from Yahoo Finance.
3. It pulls the Massive options snapshot chain from `https://api.massive.com/v3/snapshot/options/{underlying}`.
4. It aggregates call and put gamma exposure by strike.
5. It selects a focused set of nearby structural levels.
6. It probes the Massive websocket (`wss://socket.massive.com/options` or delayed endpoint) for health/visibility metadata.
7. It writes a JSON payload atomically to:
   - `C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\massive_gex_map.json`
8. The NT8 indicator polls that file every 2 seconds.
9. It matches the current instrument to the payload asset and draws the levels closest to current futures price.

---

## Source of truth and default output path

### Indicator default input file

`%USERPROFILE%\Documents\NinjaTrader 8\templates\DEEP6\massive_gex_map.json`

### Python service default output file

`C:\Users\Tea\Documents\NinjaTrader 8\templates\DEEP6\massive_gex_map.json`

The service writes to the exact location the indicator reads by default.

---

## NT8 indicator specs

File: `ninjatrader/Custom/Indicators/DEEP6/DEEP6MassiveGexMap.cs`

### Purpose

Pure chart renderer for a locally-produced Massive GEX map.

### Important defaults

- `Calculate = OnEachTick`
- `IsOverlay = true`
- `RefreshSeconds = 2`
- `StaleSeconds = 180`
- `VeryStaleSeconds = 600`
- `MaxRenderedLevels = 9`
- `ShowHud = true`
- `ShowOffscreenLabels = true`
- `ShowSourceMetadata = true`
- `LineOpacity = 90`

### Color mapping

- Gamma Flip -> Gold
- Call Wall -> IndianRed
- Put Wall -> LimeGreen
- HVL -> DeepSkyBlue
- +GEX Node -> DodgerBlue
- -GEX Node -> MediumPurple
- Neutral -> Gainsboro

### Instrument normalization

The indicator normalizes micro contracts to their parent root:

- `MNQ -> NQ`
- `MES -> ES`

That means the same JSON map can drive both the micro and full-size futures charts.

### Rendering behavior

The indicator:

- reads the JSON snapshot under a file-share-safe read
- deserializes the payload with `JavaScriptSerializer`
- matches the current chart root against `payload.assets[*].futures_root`
- sorts levels by absolute `distance_from_futures_spot`
- renders only the nearest `MaxRenderedLevels`

If a level is outside the visible chart range:

- it does not draw a full-width line
- it optionally draws a short offscreen marker and label instead

Pinned levels draw thicker than non-pinned levels.

### Status logic

Age is taken from `generated_at_utc`, with file write time as fallback.

HUD states:

- `OK` when age <= `StaleSeconds`
- `STALE` when age > `StaleSeconds`
- `VERY STALE` when age > `VeryStaleSeconds`
- `CHAIN ERROR: ...` if chain fetch failed upstream

### HUD contents

The HUD shows:

- status text
- underlying -> futures mapping ratio
- spot and futures spot
- sequence number
- schema/version metadata
- file age
- websocket state, auth flag, message count, trade count, last error
- chain snapshot stats: contract count, used contracts, strike count, page count

---

## Python service specs

File: `scripts/massive_gex_map_service.py`

### Purpose

Build the GEX map payload that NT8 renders.

### External inputs

- Massive REST API
- Massive websocket endpoint
- Yahoo price endpoint
- local env files for API key

### Default runtime options

- `--underlying QQQ`
- `--futures-root NQ`
- `--source-spot-symbol QQQ`
- `--futures-spot-symbol NQ=F`
- `--max-pages 80`
- `--max-dte 45`
- `--anchor-window-pct 0.07`
- `--max-levels 9`
- `--max-futures-distance-points 350`
- `--ws-probe-seconds 8`
- `--interval 120`

### API key handling

The service looks for `MASSIVE_API_KEY` and exits if it is missing.

It deliberately keeps the credential outside NinjaTrader.

### REST fetch behavior

`http_json(...)` uses:

- a custom user agent
- up to 3 attempts
- retry sleep/backoff
- URL redaction in logs so `apiKey` is not printed raw

### Chain aggregation logic

For each contract row, the service extracts:

- strike
- contract type (`call` / `put`)
- open interest
- gamma
- expiration

Invalid rows are skipped when strike, type, OI, or gamma are missing/useless.

Per-strike aggregation is stored in `StrikeExposure`:

- `call_gex`
- `put_gex`
- `net_gex`
- `abs_gex`
- `call_oi`
- `put_oi`
- `contract_count`
- expirations set

### GEX formula

The current service computes strike gamma exposure as:

`gamma * open_interest * 100 * spot^2 * 0.01`

That is implemented in `compute_gex(...)`.

Calls add positive net GEX. Puts subtract from net GEX.

---

## Level-selection logic

The heart of the system is `choose_levels(...)`.

### 1) Spot-centered strike window

The service first selects strikes around the underlying spot price using `spot_window(...)`.

Default anchor window:

- `spot ± 7%`

If too few strikes are found, it widens to at least `±12%`.

Optional asymmetrical caps can also be applied with:

- `max_above_pct`
- `max_below_pct`

### 2) Map proxy strikes into futures space

The service converts underlying strikes into futures-price space using a spot ratio:

`ratio = futures_spot / source_spot`

Mapped price:

`mapped_price = strike * ratio`

This is how a QQQ-derived options map is projected onto an NQ chart.

### 3) V3 selective near-price rule

This is one of the most important behaviors preserved in tests.

The service does **not** force structurally large but far-away levels onto the chart.

Instead, it applies a futures-distance cap:

- default `350` futures points

Only levels whose mapped futures price is within that distance of current futures spot are considered "near" for structural selection.

This prevents the indicator from pretending a far-away wall is actionable just because it has large absolute gamma.

If there are no near candidates, the service can return no levels at all.

That behavior is explicitly verified in `tests/test_massive_gex_map_service.py`.

### 4) Gamma Flip

`gamma_flip(...)` searches adjacent strikes for a sign change in `net_gex`.

Behavior:

- if one strike is exactly zero -> use that strike
- if two neighboring strikes cross sign -> linearly interpolate between them
- if no zero-cross exists -> fall back to the nearest strike, but that fallback is not promoted as a true gamma flip level

The final gamma flip is only emitted when it is a real zero-cross and still near enough in futures space.

### 5) Structural pinned levels

From the near-candidate set, the service attempts to emit:

- `gamma_flip`
- `call_wall`
- `put_wall`
- `hvl`

Definitions:

- `call_wall`: strongest positive net GEX strike at or above source spot
- `put_wall`: strongest negative net GEX strike at or below source spot
- `hvl`: highest absolute net GEX strike among near candidates

These are emitted as pinned levels.

### 6) Additional node fill

After structural levels, remaining near strikes are added in descending absolute GEX order until `max_levels` is reached.

They are labeled as:

- `+GEX NODE`
- `-GEX NODE`

Their side classification is inferred as:

- positive above spot -> resistance
- negative below spot -> support
- otherwise -> magnet

### 7) No duplicate strike labeling

Once a strike is pinned under one structural role, the algorithm will not attach a second role to the same strike.

This preserves a clean chart and is explicitly documented in the code comments as original-indicator behavior.

---

## Output payload schema

Top-level schema:

- `schema = deep6.massive_gex_map.v1`
- `service = massive_gex_map_service`
- `service_version = 1.0.0`
- `generated_at_utc`
- `sequence`
- `assets[]`
- `errors[]`

### Asset-level fields

Important asset fields include:

- `asset_id`
- `futures_root`
- `underlying`
- `underlying_spot`
- `futures_symbol`
- `futures_spot`
- `mapping`
- `freshness`
- `websocket`
- `chain`
- `selection`
- `levels`
- `levels_list`
- `net_exposures`
- `chain_error`
- `stale`
- `age_seconds`
- `as_of_utc`

### Level fields

Each level includes:

- `id`
- `key`
- `role`
- `symbol`
- `label`
- `action`
- `side`
- `source_underlying`
- `source_strike`
- `source_price`
- `mapped_price`
- `price`
- `gex`
- `value`
- `abs_gex_rank`
- `distance_from_spot_source`
- `distance_from_futures_spot`
- `is_pinned`
- `confidence`
- `metadata`

This schema is broader than what the renderer strictly needs, which is useful because it keeps the payload inspectable and extensible.

---

## Websocket role in the design

The websocket probe is mainly a health/telemetry feature in this implementation.

The code comment in `build_payload(...)` is explicit:

- standard GEX still comes from REST greeks and open interest
- websocket data is subscribed for dashboard-visible probe/stream metadata

So the current indicator is **not** computing live gamma from streaming trades alone. The websocket is there to validate feed access and expose session-health context.

---

## Verified behaviors from tests

`tests/test_massive_gex_map_service.py` locks in two important behaviors:

1. Far-away structural magnets should not be forced onto the chart just because they are large.
2. If no near actionable magnet exists, the correct output is an empty level set, not a misleading one.

That tells us the intended personality of this indicator:

- selective
- contextual
- operator-facing
- biased toward actionable nearby structure rather than maximal raw magnitude

---

## Evolution / how we built it

Recovered from git history:

### Phase 1: embedded Massive client

- `MassiveGexClient.cs` existed inside the NT8 path.
- Early work fetched Massive snapshot data directly and evolved auth/timeouts.

### Phase 2: extracted GEX layer

- GEX functionality was separated from the footprint indicator into dedicated GEX components like `DEEP6GexLevels.cs`.
- Timer-driven fetching and safer rendering/data handoff patterns were introduced.

### Phase 3: multi-source GEX direction

- The repo added more than one possible GEX backend and began treating GEX as a pluggable data source.
- `gex_service_v2.py` shows the move toward sidecar/service architecture.

### Phase 4: final Massive map split

- `DEEP6MassiveGexMap.cs` became the local-file-only NT8 renderer.
- `massive_gex_map_service.py` became the authoritative producer.
- Companion modules like `GEXGammaOverlay.cs` and `GEXCommand.cs` were added in the same family of work.

This makes `DEEP6MassiveGexMap` the clearest expression of the architecture: Python computes and packages; NinjaTrader renders and monitors.

---

## Practical interpretation of the map

The indicator is trying to answer:

- Where is the nearest regime pivot? (`gamma_flip`)
- Where is the strongest likely resistance above? (`call_wall`)
- Where is the strongest likely support below? (`put_wall`)
- Which strike has the highest local gamma gravity? (`hvl`)
- What secondary gamma nodes surround price? (`+GEX` / `-GEX` nodes)

In other words, it is less a raw options dashboard and more a **tradeable structural map** projected into futures space.

---

## Strengths of the design

- Keeps secrets out of NinjaTrader
- Clean failure boundary between producer and renderer
- Atomic file writes reduce partial-read corruption
- Nearest-level rendering keeps the chart readable
- Test coverage protects the most important selection behavior
- JSON schema carries enough metadata to debug stale or degraded data

---

## Current limitations

- Spot and futures prices come from Yahoo in this implementation, which is convenient but not institutional-grade.
- The websocket probe is telemetry-oriented, not a full streaming recalculation engine.
- The map is proxy-based by default (`QQQ -> NQ`) instead of native NQ options.
- The NT8 renderer exposes brush properties, but the current render code uses fixed DX color brushes derived internally rather than those WPF brush properties for every line path.

---

## Canonical one-sentence summary

`DEEP6MassiveGexMap` is a two-part DEEP6 indicator system that computes a selective, near-price, proxy-mapped gamma exposure structure from Massive options-chain data in Python and renders the resulting actionable levels on NinjaTrader charts from a local JSON snapshot.
