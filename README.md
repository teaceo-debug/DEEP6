# DEEP6 v2.0

> Institutional-grade footprint auto-trading system for NQ futures — pure Python, macOS native.

DEEP6 connects directly to Rithmic via `async-rithmic` for real-time Level 2 DOM data
and order execution. 44 independent market microstructure signals across 11 phases —
plus VPIN toxicity, Kronos E10 directional bias, and a WalkForwardTracker — are
synthesized into a two-layer confluence score that drives automated entries on
Tradovate accounts (routed over Rithmic infrastructure).

## Core stack

- **Python 3.12** — entire system, single codebase for live and backtest
- **async-rithmic 1.5.9** — L2 DOM (40+ levels), tick data, order execution
- **Databento MBO** — historical L3 data for backtesting and replay
- **Polygon** — supplementary market data and corporate-action context
- **Kronos-small** — 24.7M-param foundation model for directional bias (E10)
- **FastAPI + Next.js 15** — operator dashboard, SSE + WebSocket push
- **SQLite (WAL)** — session persistence and ML weights store

## Signal surface

11 engine phases plus ML-quality overlay:

1. Absorption / exhaustion (the alpha core)
2. Imbalance (9 variants) + LVN/HVN volume profile
3. Delta (11 types) + auction theory + POC/VA
4. GEX (gamma exposure from options chain)
5. VPIN — volume-synchronized probability of informed trading
6. Two-layer confluence scorer + Kronos E10 bias
7. WalkForwardTracker — rolling out-of-sample performance monitor
8. Imbalance cascade and narrative detection
9. Auction FSM (E9) — initiative/responsive state machine
10. Kronos E10 — foundation-model directional probability
11. Execution + risk layer (bracket orders via Rithmic ORDER_PLANT)

## Quick start

```bash
git clone <repo> DEEP6 && cd DEEP6
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env           # fill in Rithmic creds, DB paths, API keys
python -m deep6                # runs the live pipeline
```

## Running components

| Command | Purpose |
|---------|---------|
| `python -m deep6` | Live Rithmic pipeline (DOM + bars + signals + execution) |
| `pytest tests/` | Unit and integration tests |
| `uvicorn deep6.api.app:app --port 8765` | FastAPI backend (SSE + REST) |
| `cd dashboard && npm run dev` | Next.js 15 operator dashboard |

## Graceful shutdown

SIGTERM and SIGINT are handled by asyncio signal handlers. On shutdown DEEP6
cancels every task, closes SQLite persistence, checkpoints the WAL, and logs
final metrics before exiting.

## Operational procedures

See [docs/RUNBOOK.md](docs/RUNBOOK.md) for:

- Starting and stopping the system
- Enabling live mode (30-day paper gate)
- Rolling back ML weights
- Investigating drawdown
- Handling Rithmic disconnects
- Backing up SQLite DBs
- Rotating API keys

## Thesis

Absorption and exhaustion are the highest-alpha reversal signals in order flow.
Everything else exists to confirm or contextualize them. DEEP6 is built to detect
both with the highest accuracy of any footprint system, and to auto-execute the
resulting trades without human latency.

## License

Proprietary — Peak Asset Performance LLC.
