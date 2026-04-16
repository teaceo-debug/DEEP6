# Rithmic Feed Adapter

Connects directly to Rithmic via async-rithmic and outputs NDJSON for the NinjaScript Simulator.

## Quick Start (Test Server — Free)

```bash
# 1. Stream to console:
python ninjatrader/simulator/rithmic/rithmic_feed.py \
  --env test --user YOUR_USER --pass YOUR_PASS

# 2. Record a session:
python ninjatrader/simulator/rithmic/rithmic_feed.py \
  --env test --user YOUR_USER --pass YOUR_PASS \
  --output session.ndjson

# 3. Replay through simulator:
dotnet run --project ninjatrader/simulator -- replay session.ndjson

# 4. Full backtest with trade journal:
dotnet run --project ninjatrader/simulator -- backtest session.ndjson \
  --trades trades.csv --equity equity.html
```

## Environments

| Environment | Flag | Server | Cost | Notes |
|-------------|------|--------|------|-------|
| **Test** | `--env test` | rituz00100.rithmic.com | Free | Simulated data, no broker needed |
| **Paper** | `--env paper` | rituz00100.rithmic.com | Free | Paper trading |
| **Live** | `--env live` | rprotocol.rithmic.com | $0 extra | Requires broker API mode (rpCode=13 if not enabled) |

## Live Gateways

Use `--gateway` with `--env live`:

```bash
python rithmic_feed.py --env live --user U --pass P --gateway chicago
```

Available: chicago, newyork, colo75, frankfurt, tokyo, singapore, sydney, hongkong, mumbai, seoul, capetown, saopaolo, ireland

## Output Format

Same NDJSON format as CaptureHarness and the NT8 Data Bridge:

```json
{"type":"session_reset","ts_ms":1744718400000}
{"type":"trade","ts_ms":1744718400001,"price":20000.0,"size":5,"aggressor":1}
{"type":"depth","ts_ms":1744718400002,"side":0,"levelIdx":0,"price":19999.75,"size":200}
{"type":"bar","ts_ms":1744718460000,"open":20000.0,"high":20002.0,"low":19998.0,"close":20001.0,"barDelta":200,"totalVol":500,"cvd":200}
```

## Requirements

```bash
pip install async-rithmic  # already installed (v1.5.9)
```

## Conformance

App name: `migo:DEEP6-sim` (conformance granted 2026-04-14 by Rithmic).
The `migo:` prefix is required on all Rithmic systems.
