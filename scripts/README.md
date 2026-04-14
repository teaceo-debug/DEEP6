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
