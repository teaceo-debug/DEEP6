---
phase: 260415-fdu
plan: 01
subsystem: ninjatrader-indicator
tags: [ninjatrader, gex, threading, http, reliability]
dependency_graph:
  requires: []
  provides:
    - background-timer-driven-gex
    - query-param-auth-for-massive-com
    - exponential-backoff-retry
  affects:
    - ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs
    - ninjatrader/docs/SETUP.md
    - ninjatrader/docs/ARCHITECTURE.md
tech_stack:
  added:
    - System.Threading.Timer (self-scheduling callback pattern)
  patterns:
    - Split sticky/transient status strings composed via read-only property
    - Monitor.TryEnter re-entrance guard around fetch callback
    - Timer disposed BEFORE CTS.Cancel in Terminated to prevent post-cancel ticks
key_files:
  created: []
  modified:
    - ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs
    - ninjatrader/docs/SETUP.md
    - ninjatrader/docs/ARCHITECTURE.md
decisions:
  - Query-param apiKey for first-page URL; next_url followed unchanged (Polygon embeds apiKey in next_url already)
  - HttpClient.Timeout raised 8s -> 30s to tolerate up to 20 paginated pages
  - ServicePointManager.DefaultConnectionLimit raised to 8 (prevents per-host serialization)
  - _gexStatus is now a read-only computed property; all writes target _gexLastSuccessStatus (sticky) or _gexRetryStatus (transient)
  - Backoff 5s -> 15s -> 60s -> 120s cap; cap = existing _gexInterval constant
  - First fetch fires at dueTime=0; subsequent ticks self-schedule via ScheduleNextGexTick (period=Infinite)
metrics:
  duration_min: 10
  completed: 2026-04-15
  tasks: 3
  files: 3
---

# Quick Task 260415-fdu: Fix GEX Level Disconnects in DEEP6Footprint Summary

One-liner: Replaced OnBarUpdate-driven GEX fetch with background `System.Threading.Timer` + 5s/15s/60s exponential backoff + split sticky/transient status, and switched MassiveGexClient to Polygon-compatible `?apiKey=` query-param auth with a 30s HTTP timeout.

## Changes

### Task 1 — `MassiveGexClient` auth + timeout + connection limits
- Commit: `18174b2`
- Removed `Authorization: Bearer` header from `_http.DefaultRequestHeaders`
- First-page URL: `/v3/snapshot/options/{underlying}?limit=250&apiKey={Uri.EscapeDataString(_apiKey)}`
- `next_url` pagination unchanged (Polygon embeds `apiKey` in `next_url`)
- `HttpClient.Timeout` raised 8s → 30s
- `ServicePointManager.DefaultConnectionLimit` raised to ≥8; keep-alive is HTTP/1.1 default and intentionally preserved
- Fallback comment in ctor documents the one-line Bearer-auth switch if massive.com ever rejects query-param

### Task 2 — Background timer + backoff + split status
- Commit: `a273a0a`
- New field `System.Threading.Timer _gexTimer` initialized in `State.DataLoaded` with `dueTime=0, period=Infinite` — self-rescheduling via `ScheduleNextGexTick`
- New methods:
  - `GexTimerTick(object state)` — ThreadPool callback, guarded by `Monitor.TryEnter(_gexTimerLock)`, runs `client.FetchAsync(...).GetAwaiter().GetResult()` synchronously inside the lock, calls `OnGexFetchSuccess` / `OnGexFetchFailure`, then schedules next tick in `finally`
  - `OnGexFetchSuccess(GexProfile)` — updates `_gexProfile`, resets `_gexFailCount`, sets `_gexLastSuccessStatus`, clears `_gexRetryStatus`
  - `OnGexFetchFailure(Exception)` — increments `_gexFailCount`, sets `_gexRetryStatus` with retry countdown; **does NOT clear `_gexProfile`** (last-good levels stay drawn)
  - `ComputeGexRetryDelay(int failCount)` — 5s / 15s / 60s / 120s cap (cap = `_gexInterval`)
  - `ScheduleNextGexTick()` — 60s when healthy, backoff delay when failing
- `_gexStatus` is now a read-only computed property that composes `"<sticky>  [<transient>]"` — all 5 previous writer sites now target `_gexLastSuccessStatus` or `_gexRetryStatus`
- New fields: `_gexFailCount`, `_gexLastSuccess`, `_gexLastSuccessStatus`, `_gexRetryStatus`, `_gexTimerLock`
- Removed: `_lastGexFetch`, the original `MaybeFetchGex()` method, and its call site in `OnBarUpdate`
- Timer disposed in `State.Terminated` **before** `_gexCts.Cancel()` so no new tick can start post-cancel

### Task 3 — Docs
- Commit: `22a4b80`
- `SETUP.md` troubleshooting rewritten: 60s timer cadence, backoff schedule, last-good persistence, query-param auth note
- `ARCHITECTURE.md` data-flow diagram: removed `MaybeFetchGex (every 2 min)` from OnBarUpdate branch; added dedicated `System.Threading.Timer (60s) → GexTimerTick` branch with success / failure arrows
- `ARCHITECTURE.md` threading table: replaced the `Task.Run(async FetchAsync)` row with a Background-timer row describing re-entrance guard, volatile writes, and self-scheduling
- `ARCHITECTURE.md` failure-modes: `GEX fetch fails → _gexProfile UNCHANGED (last-good), retry on 5s/15s/60s/120s-cap backoff, `_gexRetryStatus` countdown banner

## Deviations from Plan

None — plan executed exactly as written. All seven `_gexStatus = ...` writer sites listed in the plan (988, 1066, 1070, 1077, 1294, 1305, 1310, 1316) were rewritten to target either `_gexLastSuccessStatus` or `_gexRetryStatus`, and the one reader site (line 1407 in the render layer) consumes the unchanged computed-property signature.

## Verification Results

Static checks (automated, plan verify blocks):

| Check | Result |
|---|---|
| `grep "apiKey="` in DEEP6Footprint.cs | PASS (line 804) |
| `grep "TimeSpan.FromSeconds(30)"` | PASS (line 789) |
| `! grep 'AuthenticationHeaderValue("Bearer"'` | PASS (absent) |
| `grep "DefaultConnectionLimit"` | PASS (lines 782-783) |
| `grep "System.Threading.Timer"` | PASS (field + ctor) |
| `grep "GexTimerTick"` | PASS |
| `grep "ScheduleNextGexTick"` | PASS |
| `grep "_gexLastSuccessStatus\|_gexRetryStatus"` | PASS (17+ sites) |
| `! grep "MaybeFetchGex"` | PASS (absent) |
| `! grep "_lastGexFetch"` | PASS (absent) |
| `! grep -E '_gexStatus\s*='` (no assignments to computed property) | PASS (absent) |
| `grep "60s on a background timer\|query-param"` SETUP.md | PASS |
| `grep "GexTimerTick\|backoff"` ARCHITECTURE.md | PASS |

Brace balance: file reports 1 via naïve `awk` (same as baseline at `d8ae365`, so off-by-one is pre-existing — likely a `{` / `}` inside a comment or string literal). Not introduced by this plan.

## Runtime Verification (user, on NT8)

Because NinjaScript only compiles inside NT8 via F5, the user must:
1. Copy `DEEP6Footprint.cs` into `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\`
2. Open NinjaScript Editor → F5 — expect zero compile errors
3. Attach indicator to any NQ chart with `GexApiKey` populated
4. Output Window within 1-2s should show `[DEEP6] GEX fetch start` then `[DEEP6] GEX OK: N levels` (success) OR `[DEEP6] GEX EXCEPTION (#1)` with specific error
5. If failure path: subsequent retries at ~5s, ~15s, ~60s visible in Output Window; chart levels stay drawn from any prior successful fetch
6. Let chart idle with no tape for >60s — a new `GEX fetch start` log line should still appear (proves timer is independent of OnBarUpdate)

## Commits

- `18174b2` fix(260415-fdu): MassiveGexClient auth + timeout + connection limits
- `a273a0a` fix(260415-fdu): timer-driven GEX fetch + backoff + split status
- `22a4b80` docs(260415-fdu): GEX timer behavior, backoff, query-param auth

## Self-Check: PASSED

- Files modified exist:
  - FOUND: ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs
  - FOUND: ninjatrader/docs/SETUP.md
  - FOUND: ninjatrader/docs/ARCHITECTURE.md
- All three commits present in `git log --oneline --all`.
