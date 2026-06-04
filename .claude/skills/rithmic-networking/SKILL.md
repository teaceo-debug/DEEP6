# Rithmic Networking Skill

Expert-level Rithmic API networking reference for DEEP6. All patterns verified live on 2026-05-20.

## Invoke this skill when:
- Connecting to Rithmic via async-rithmic (any environment: test, paper, live, prop firm)
- Debugging Rithmic connection errors (rpCode 13, ForcedLogout, authentication, heartbeat)
- Subscribing to market data (L2/L3 depth, ticks, BBO)
- Setting up a new Rithmic service (MBO levels, feed adapter, execution broker)
- Configuring environment variables for Rithmic (RITHMIC_USER, RITHMIC_URI, etc.)
- Working with Rithmic gateway discovery, system names, or conformance
- Troubleshooting DOM/tick data feed issues from Rithmic
- Managing multi-service Rithmic connections (avoiding ForcedLogout from concurrent sessions)
- Understanding R|Trader Pro native infrastructure (servers, ports, regions, login agents)

## Skill Files

| File | Purpose |
|------|---------|
| `knowledge.md` | **Complete reference** — 17 sections covering credentials, gateways, system names, infrastructure, connection patterns, data formats, error troubleshooting, conformance |
| `rithmic-connections.md` | **Quick-reference** — copy-paste .env, working Python snippet, data format cheat sheet, common pitfalls |

## Critical Knowledge (load before any Rithmic work)

1. **System**: `Rithmic Paper Trading` (not Apex) — case-sensitive
2. **App name**: `migo:DEEP6-sim` only — `migo:DEEP6` gets rpCode 13
3. **L2 depth**: Use `subscribe_to_market_depth("NQ", "CME", 0.0)` — NOT `subscribe_to_market_data(ORDER_BOOK)`
4. **Tick format**: Dict with `tick["trade_price"]`, `tick["trade_size"]`, `tick["aggressor"]`
5. **Depth format**: Protobuf — use `update.ListFields()` to extract fields
6. **Issue #49**: Always `await asyncio.sleep(0.5)` after `client.connect()`

## Workflow

1. **Identify the environment**: test / paper / live / prop-firm — determines gateway URL and system name
2. **Check rithmic-connections.md**: quick-reference for credentials, .env, code snippets
3. **Check knowledge.md**: full gateway table, system names, infrastructure, error troubleshooting
4. **Follow connection pattern**: Issue #49 workaround, plant selection, correct subscription methods
5. **Handle errors**: use the troubleshooting decision tree in knowledge.md Section 12
6. **For new services**: follow the service template pattern with FreezeGuard and reconnection

## Key Codebase Files

| File | Purpose |
|------|---------|
| `scripts/mbo_levels_service.py` | Standalone MBO levels service (L2 DOM tracking) |
| `ninjatrader/simulator/rithmic/rithmic_feed.py` | Feed adapter with all gateway URLs |
| `deep6v2/data/rithmic_client.py` | RithmicClient wrapper with state machine |
| `deep6v2/config/rithmic.py` | Pydantic configuration class |
| `deep6/data/rithmic.py` | Connection factory with aggressor gate |
| `deep6/state/connection.py` | FreezeGuard state machine |
| `.env` / `.env.example` | Environment variable templates |
