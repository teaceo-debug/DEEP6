# DEEP6 Scripts

Utility scripts for development, testing, and dashboard validation.

## demo_broadcast.py — Looping Demo Broadcaster

Streams realistic NQ-futures market activity to the DEEP6 backend indefinitely, keeping the dashboard alive and fully populated during visual inspection without needing a live Rithmic feed. The script runs a random-walk price model starting at 19,483.50, fires status heartbeats every second (prevents the STALE banner), emits footprint bars every 3 ticks with 31-row level ladders (30% one-sided/absorption bars), updates the confluence score every 5 seconds with smooth autocorrelated oscillation, and injects TYPE_C/TYPE_B/TYPE_A signals on Poisson-distributed cadences (avg 8-15s / 30-60s / 90-180s respectively). Run it as `python scripts/demo_broadcast.py` with no arguments for sensible defaults, or use `--rate 2.0` to double speed, `--duration 120` to cap at 2 minutes, and `--seed -1` for a non-reproducible run. Press Ctrl-C for a clean exit with a message-count summary.

```
python scripts/demo_broadcast.py                          # stream forever at 1 Hz
python scripts/demo_broadcast.py --rate 2.0               # 2x speed
python scripts/demo_broadcast.py --duration 60 --seed -1  # 60s, random seed
python scripts/demo_broadcast.py --url http://localhost:8001  # alternate port
```

## run_live.py — Production-mode startup

Single entry-point that starts FastAPI + a data source.  Switches between demo
and real engine with `--source`.

```
python scripts/run_live.py                  # default: demo source
python scripts/run_live.py --source=demo    # explicit demo
python scripts/run_live.py --source=live    # real Rithmic engine (see below)
python scripts/run_live.py --port 8001      # alternate port
```

### Going live — pointing the real engine at `live_bridge`

The `LiveBridge` class (`deep6/api/live_bridge.py`) is the single connection
point between the engine and the dashboard.  It is created during app startup
and stored at `app.state.live_bridge`.

To wire the real engine, add these calls to the corresponding engine hooks:

1. **Bar close** — inside `FootprintBuilder.on_bar_close` (or equivalent):
   ```python
   await bridge.on_bar_close(bar)          # bar: FootprintBar dataclass or dict
   ```

2. **Score update** — after every `score_bar()` call:
   ```python
   await bridge.on_score_update(result)    # result: ScorerResult
   ```

3. **Signal fired** — when `result.tier >= TYPE_C`:
   ```python
   await bridge.on_signal_fired(result)    # result: ScorerResult
   ```

4. **Tape prints** — inside the Rithmic `on_trade` callback:
   ```python
   await bridge.on_tape_print(trade)       # dict or dataclass with
                                           #   ts, price, size, aggressor (1=ASK / 2=BID)
   ```

5. **Periodic status** — schedule once at engine startup:
   ```python
   async def _status_loop():
       while True:
           await bridge.periodic_status()
           await asyncio.sleep(10.0)
   asyncio.create_task(_status_loop())
   ```

The bridge is **type-robust**: it accepts real engine dataclass instances
(attribute access) or plain dicts (key access) interchangeably.  Missing
fields fall back to safe defaults; NaN/Infinity floats become 0.0.

### Fallback to demo

Use `--source=demo` (the default).  demo_broadcast.py posts directly to
`/api/live/test-broadcast` — no engine required.

### Mixed mode (engine partially ready)

Start with `--source=demo` for market data (bars + tape), then add real engine
calls for whichever subsystems are ready.  Example: demo supplies bars/tape,
but a partially wired scorer posts real signal events:

```python
# In your partial engine loop:
result = score_bar(...)
await bridge.on_score_update(result)
if result.tier.value >= 1:   # TYPE_C = 1
    await bridge.on_signal_fired(result)
```

The dashboard receives a mix of demo bars and real signals transparently.

---

## deep6_healthcheck.py — Pre-Live Pipeline Health Check

Verifies the entire DEEP6 data pipeline end-to-end before going live. Run this
every time before starting a trading session to catch connectivity or schema
regressions early.

**What it checks (9 stages):**

| # | Check | What it verifies |
|---|-------|-----------------|
| 1 | Backend boot | `uvicorn` responds on `:8000` with HTTP 200 |
| 2 | HTTP endpoints | `/api/session/status` returns valid `LiveStatusMessage` JSON |
| 3 | WebSocket accept | `/ws/live` upgrades to 101 Switching Protocols |
| 4 | Message round-trip | POST to `/api/live/test-broadcast` → message arrives on WS |
| 5 | All 5 message types | `bar`, `signal`, `score`, `tape`, `status` all received |
| 6 | Replay endpoint | `/api/replay/sessions` returns array; unknown session → 404 |
| 7 | Frontend boot | Next.js on `:3000` responds with HTML |
| 8 | Frontend WS reachability | Backend WS port reachable from loopback |
| 9 | Schema sync | `LiveMessage` TS union matches Python union (drift detection) |

**Standard pre-live run:**

```bash
# With both backend and frontend running:
python scripts/deep6_healthcheck.py

# Backend only (no dashboard):
python scripts/deep6_healthcheck.py --skip-frontend

# Verbose output (shows request details):
python scripts/deep6_healthcheck.py --verbose

# Custom ports or longer timeout:
python scripts/deep6_healthcheck.py --backend-url http://localhost:8001 --timeout 10
```

**Expected output (all green):**

```
DEEP6 PIPELINE HEALTH CHECK
═══════════════════════════════════════════════════════

  [✓] Backend boot                         — uvicorn :8000 responds
  [✓] HTTP endpoints                       — /api/session/status → 200 with valid JSON
  [✓] WebSocket accept                     — /ws/live → 101 Switching Protocols
  [✓] Message round-trip                   — POST test-broadcast → received on WS (first: type='status')
  [✓] All 5 message types                  — bar, signal, score, tape, status all received
  [✓] Replay endpoint                      — /api/replay/sessions → [0 sessions]; 404 on unknown
  [✓] Frontend boot                        — Next.js :3000 responds with HTML
  [✓] Frontend WS reachability             — WS port 8000 reachable from loopback
  [✓] Schema sync                          — LiveMessage union aligned (5 types: ...)

═══════════════════════════════════════════════════════
  RESULT: 9/9 GREEN — READY FOR LIVE DATA
```

**Exit codes:**
- `0` — all GREEN (safe to go live)
- `1` — any RED failure (do not go live until resolved)
- `2` — any YELLOW / skipped (degraded — investigate before going live)

**Prerequisites:** No external Python packages needed — uses only stdlib
(`http.client`, `socket`, `struct`, `urllib`). Works with `.venv/bin/python`
or system Python 3.12+.

---

## Stack Lifecycle — deep6_up / down / status

One-command startup that brings up the entire DEEP6 stack (backend + frontend + optional demo broadcaster).

### Quick start

```bash
# Bring up everything (backend + frontend + demo broadcaster)
make up

# Or call the script directly
./scripts/deep6_up.sh           # backend + frontend only
./scripts/deep6_up.sh --demo    # + demo broadcaster at 2x speed
./scripts/deep6_up.sh --force   # skip kill-confirmation prompts

# Status at a glance
make status                     # or ./scripts/deep6_status.sh

# Tail all logs live
make logs                       # or tail -f logs/*.log

# Shut everything down
make down                       # or ./scripts/deep6_down.sh
```

### What `deep6_up.sh` does

1. **Pre-flight** — verifies Python 3.12+, `.venv/`, Node.js, `dashboard/node_modules/`. Runs `npm install` automatically if modules are missing.
2. **Port check** — if :8000 or :3000 are occupied, prompts to kill the blocker (or kills silently with `--force`).
3. **Idempotency** — if both processes are already alive, prints their PIDs and exits cleanly without double-starting.
4. **Backend** — starts `uvicorn deep6.api.app:app --port 8000`, saves PID to `.deep6/backend.pid`, waits up to 10s for HTTP 200.
5. **Frontend** — starts `npx next dev -p 3000`, saves PID to `.deep6/frontend.pid`, waits up to 20s for HTTP 200.
6. **Demo** — if `--demo` flag is set, starts `scripts/demo_broadcast.py --rate 2.0`, saves PID to `.deep6/demo.pid`.
7. **Report** — prints a summary with PIDs, URLs, and quick reference commands.

### Logs

All process stdout/stderr is written to `logs/`:

| File | Contents |
|------|----------|
| `logs/uvicorn.log` | FastAPI backend |
| `logs/next.log` | Next.js frontend |
| `logs/demo.log` | Demo broadcaster |

Both `logs/` and `.deep6/` are git-ignored.

### Makefile targets

| Target | Action |
|--------|--------|
| `make up` | `deep6_up.sh --demo` |
| `make down` | `deep6_down.sh` |
| `make status` | `deep6_status.sh` |
| `make logs` | `tail -f logs/*.log` |
| `make health` | `scripts/deep6_healthcheck.py` |
