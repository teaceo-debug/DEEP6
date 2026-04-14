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
