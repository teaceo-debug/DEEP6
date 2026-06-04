# Rithmic API Networking Knowledge Base

Complete reference for connecting to Rithmic via async-rithmic 1.5.9 in DEEP6.
All gateway URLs, system names, and infrastructure details verified from R|Trader Pro 17.93.0.0
binary config (omneconfig.tbl) extracted 2026-05-19, plus live WebSocket probe data from 2026-05-18.

---

## 1. DEEP6 Active Credentials

**Broker**: Rithmic Direct (Paper Trading)
**Account**: michael@fitsells.com

```bash
RITHMIC_USER=michael@fitsells.com
RITHMIC_PASSWORD=Madmoney1986!
RITHMIC_SYSTEM_NAME=Rithmic Paper Trading
RITHMIC_URI=wss://rprotocol.rithmic.com:443
RITHMIC_INSTRUMENT=NQM6
RITHMIC_EXCHANGE=CME
```

**Level 2/3 Data**: Active — use `subscribe_to_market_depth()` NOT `subscribe_to_market_data(ORDER_BOOK)`.
**Data Type**: MBO (Market-by-Order / L3) — individual order events with exchange_order_id, depth_order_priority.
**Throughput**: ~200+ depth updates/sec on NQ during RTH.
**R|Trader Pro**: v17.93.0.0 at `C:\ProgramData\Rithmic\Rithmic Trader Pro\17.93.0.0\`
**R|Trader Account**: 101651 (Gonzalez, Rithmic) — $100,000 paper balance
**App Name**: `migo:DEEP6-sim` (only conformance-approved app_name — `migo:DEEP6` gets rpCode 13)

---

## 2. R|Protocol WebSocket Gateways (async-rithmic)

These are the WebSocket endpoints used by async-rithmic for DEEP6's Python connections.

### Production Gateways

| Region | WebSocket URL | Latency from NYC |
|--------|---------------|------------------|
| **Chicago (default)** | `wss://rprotocol.rithmic.com:443` | ~8ms |
| **New York** | `wss://rprotocol-nyc.rithmic.com:443` | ~1ms |
| **Colo 75 (CME co-lo)** | `wss://rprotocol-colo75.rithmic.com:443` | <1ms |
| Frankfurt | `wss://rprotocol-de.rithmic.com:443` | ~80ms |
| Ireland | `wss://rprotocol-ie.rithmic.com:443` | ~70ms |
| Tokyo | `wss://rprotocol-jp.rithmic.com:443` | ~160ms |
| Singapore | `wss://rprotocol-sg.rithmic.com:443` | ~220ms |
| Sydney | `wss://rprotocol-au.rithmic.com:443` | ~200ms |
| Hong Kong | `wss://rprotocol-hk.rithmic.com:443` | ~180ms |
| Mumbai | `wss://rprotocol-in.rithmic.com:443` | ~170ms |
| Seoul | `wss://rprotocol-kr.rithmic.com:443` | ~170ms |
| Cape Town | `wss://rprotocol-za.rithmic.com:443` | ~230ms |
| Sao Paulo | `wss://rprotocol-br.rithmic.com:443` | ~120ms |

### Test Gateway

| Environment | WebSocket URL |
|-------------|---------------|
| **Rithmic Test** | `wss://rituz00100.rithmic.com:443` |

---

## 3. All Available System Names (23 systems)

Extracted from R|Trader Pro 17.93.0.0 `omneconfig.tbl` (2026-05-19):

```
4PropTrader          Apex                 Bulenox
DayTraders.com       Earn2Trade           FundedFuturesNetwork
HalcyonTrader        LegendsTrading       LucidTrading
MES Capital          PropShopTrader       Rithmic 01
Rithmic 04 Colo      Rithmic Paper Trading  Rithmic Test
TheTradingPit        ThriveTrading        TopstepTrader
TradeFundrr          Tradeify             tradesea
tradesea-d           tradesea-test
```

### Quick Config by Account Type

| Account | system_name | url | Notes |
|---------|-------------|-----|-------|
| **Apex Trader Funding** | `Apex` | `wss://rprotocol.rithmic.com:443` | Prop firm |
| **Rithmic Test** | `Rithmic Test` | `wss://rituz00100.rithmic.com:443` | Free dev env |
| **Rithmic Paper** | `Rithmic Paper Trading` | `wss://rprotocol.rithmic.com:443` | **DEEP6 primary** — real data, sim fills |
| **Rithmic Live** | `Rithmic 01` | `wss://rprotocol.rithmic.com:443` | Real fills |
| **Rithmic Colo** | `Rithmic 04 Colo` | `wss://rprotocol-colo75.rithmic.com:443` | Co-located |
| **TopstepTrader** | `TopstepTrader` | `wss://rprotocol.rithmic.com:443` | |
| **Bulenox** | `Bulenox` | `wss://rprotocol.rithmic.com:443` | |
| **Earn2Trade** | `Earn2Trade` | `wss://rprotocol.rithmic.com:443` | |
| **Tradeify** | `Tradeify` | `wss://rprotocol.rithmic.com:443` | |
| **TheTradingPit** | `TheTradingPit` | `wss://rprotocol.rithmic.com:443` | |
| **4PropTrader** | `4PropTrader` | `wss://rprotocol.rithmic.com:443` | |
| **FundedFuturesNetwork** | `FundedFuturesNetwork` | `wss://rprotocol.rithmic.com:443` | |
| **HalcyonTrader** | `HalcyonTrader` | `wss://rprotocol.rithmic.com:443` | |
| **LegendsTrading** | `LegendsTrading` | `wss://rprotocol.rithmic.com:443` | |
| **LucidTrading** | `LucidTrading` | `wss://rprotocol.rithmic.com:443` | |
| **MES Capital** | `MES Capital` | `wss://rprotocol.rithmic.com:443` | |
| **PropShopTrader** | `PropShopTrader` | `wss://rprotocol.rithmic.com:443` | |
| **ThriveTrading** | `ThriveTrading` | `wss://rprotocol.rithmic.com:443` | |
| **TradeFundrr** | `TradeFundrr` | `wss://rprotocol.rithmic.com:443` | |
| **DayTraders.com** | `DayTraders.com` | `wss://rprotocol.rithmic.com:443` | |

**CRITICAL**: `system_name` is **case-sensitive**. `"Apex"` works, `"APEX"` or `"apex"` will fail.

---

## 4. R|Trader Pro Native Infrastructure (TCP/Protobuf)

Extracted from `omneconfig.tbl`. This is the underlying TCP infrastructure that R|Trader Pro
connects to directly. The WebSocket gateways (Section 2) proxy to these servers.

### Port Assignments

| Port | Plant / Purpose |
|------|----------------|
| **65000** | ORDER_PLANT — Order routing, fills, brackets |
| **56000** | TICKER_PLANT — Market data (ticks, BBO, DOM) + Login Server Agent |
| **64100** | HISTORY_PLANT — Historical bars and ticks |
| **45454** | PNL_PLANT — Account and instrument PnL |
| **63100** | Repository / Indicator data |
| **40139** | Admin (internal) |

### Regional Server Infrastructure

Each region has dedicated servers for each plant. R|Trader Pro connects to the
closest region for lowest latency. All regions fall back to Chicago servers.

| Region | Domain ID | Primary Ticker (56000) | Primary Order (65000) | History (64100) | PnL (45454) |
|--------|-----------|----------------------|---------------------|----------------|-------------|
| **Chicago** | `rithmic_prod_01_dmz_domain` | ritpz01000.01 / ritpz01001.01 | ritpz01001.01 / ritpz01000.01 | ritpz01000.01 | ritpz01000.01 |
| **NYC** | `rithmic_nyc_dmz_domain` | ritpz24016 + Chicago fallbacks | ritpz24016 + Chicago fallbacks | ritpz24016 | ritpz24016 |
| **Colo 75** | `rithmic_colo_75_domain` | ritpz04421-eth5.75.04 / ritpz04425-eth2.75.04 | ritpz04425-eth2.75.04 / ritpz04421-eth5.75.04 | ritpz04421-eth5.75.04 | ritpz04421-eth5.75.04 |
| **Frankfurt** | `rithmic_prod_aws_eu_domain` | ritpz23010 + secondary pool | ritpz23011 + secondary pool | ritpz23010 | ritpz01000.01 |
| **Ireland** | `rithmic_prod_aws_irl_domain` | ritpz05001 + secondary pool | ritpz05004 + secondary pool | ritpz05001 | ritpz01000.01 |
| **Tokyo** | `rithmic_prod_aws_jp_domain` | ritpz15001 + secondary pool | ritpz15001 + Chicago fallbacks | ritpz15001 | ritpz01000.01 |
| **Singapore** | `rithmic_prod_aws_sg_domain` | ritpz06001 + secondary pool | ritpz06001 + secondary pool | ritpz06001 | ritpz01000.01 |
| **Sydney** | `rithmic_prod_aws_au_domain` | ritpz20001 + secondary pool | ritpz20001 + secondary pool | ritpz20001 | ritpz01000.01 |
| **Hong Kong** | `rithmic_prod_aws_hk_domain` | ritpz19001 | ritpz01001.01 + Chicago | ritpz19001 | ritpz01000.01 |
| **Mumbai** | `rithmic_prod_aws_in_domain` | ritpz21001 | ritpz01001.01 + Chicago | ritpz21001 | ritpz01000.01 |
| **Seoul** | `rithmic_prod_aws_kr_domain` | ritpz22001 | ritpz01001.01 + Chicago | ritpz22001 | ritpz01000.01 |
| **Cape Town** | `rithmic_prod_aws_za_domain` | ritpz25001 | ritpz01001.01 + Chicago | ritpz25001 | ritpz25001.01 |
| **Sao Paulo** | `rithmic_prod_aws_br_domain` | ritpz18001 | ritpz01001.01 + Chicago | ritpz18001 | ritpz01000.01 |

All hostnames are `*.rithmic.com`. Fallback domains: `*.rithmic.net`, `*.theomne.net`, `*.theomne.com`.

### Login Server Agent (LSA) Endpoints

From `omneconfig.lsa` — these are the initial connection points R|Trader Pro uses to discover
available systems and get routed to the correct plant servers:

```
ritpz01000.01.rithmic.com:56000   (Chicago primary)
ritpz01001.01.rithmic.com:56000   (Chicago secondary)
omnebb00420.rithmic.com:56000     (load balancer)
ritpz24050.rithmic.com:56000      (additional)
ritpz23010.rithmic.com:56000      (EU)
ritpz23011.rithmic.com:56000      (EU secondary)
ritpz24013.rithmic.com:56000      (additional)
```

Redundancy via alternate TLDs: `.rithmic.net`, `.theomne.net`, `.theomne.com`.

### Login Agent Naming Convention

R|Trader Pro uses named login agents for each plant per system per region:

```
login_agent_op_{system}_{region}     → ORDER_PLANT
login_agent_tp_{system}_{region}     → TICKER_PLANT
login_agent_pnl_{system}_{region}    → PNL_PLANT
login_agent_hp_{system}_{region}     → HISTORY_PLANT (short sessions)
login_agent_history_{system}_{region} → HISTORY_PLANT (persistent)
login_agent_indicator_{system}       → Indicator data
login_agent_repository_{system}_{region} → Repository
login_agent_tp_agg_{system}_{region} → TICKER_PLANT aggregate (summary data)
```

Examples for Apex Chicago:
- `login_agent_op_apex` → Order plant
- `login_agent_tp_apex` → Ticker plant
- `login_agent_pnl_apex` → PnL plant

---

## 5. R|Trader Pro Installation Reference

### Installation

| Item | Value |
|------|-------|
| **Version** | 17.93.0.0 |
| **Executable** | `C:\ProgramData\Rithmic\Rithmic Trader Pro\17.93.0.0\Rithmic Trader Pro.exe` |
| **Runtime** | .NET Framework 4.7.2 |
| **SSL Certificate** | `RithmicCertificate.pk12` (bundled in install dir) |
| **Config (binary)** | `omneconfig.tbl` — all servers, systems, regions |
| **Config (LSA)** | `omneconfig.lsa` — login server agent endpoints |
| **Settings** | `C:\ProgramData\Rithmic\Rithmic Trader Pro\Settings\` |
| **Previous version** | 17.89.0.0 (also present) |
| **Version selector** | `run_this_version.txt` → `"17.93.0.0"` |

### Key DLLs

| DLL | Purpose |
|-----|---------|
| `OmneChannel.dll` | Network transport layer |
| `OmneStreamEngine.dll` | Market data streaming engine |
| `OmneBook.dll` | Order book management |
| `OmneCache.dll` | Data caching layer |
| `OmneVerse.dll` | Core platform library |
| `RithmicPlugin.dll` | Plugin interface for external apps |
| `ZomboCom.dll` | COM interop |

### Recent Changes (v17.93.0.0)

- Multiple Liquidate Criteria: updated error handling
- Fixed IB Dashboard Downside/Upside Remaining fields
- Fixed Trade Copier system clearing between sessions

---

## 6. Environment Variables

```bash
# Required for any Rithmic connection
RITHMIC_USER=michael@fitsells.com         # Rithmic username
RITHMIC_PASSWORD=Madmoney1986!            # NEVER commit to git
RITHMIC_SYSTEM_NAME=Rithmic Paper Trading # Case-sensitive — must match Section 3
RITHMIC_URI=wss://rprotocol.rithmic.com:443  # WebSocket gateway

# Instrument configuration
RITHMIC_INSTRUMENT=NQM6              # Front-month contract code
RITHMIC_EXCHANGE=CME                  # Exchange

# App identity (conformance)
RITHMIC_APP_NAME=migo:DEEP6-sim      # Only conformance-approved app_name works
RITHMIC_APP_VERSION=2.0              # App version
```

The `.env` file is read by:
- `deep6/config.py` — central Config dataclass
- `deep6v2/config/rithmic.py` — Pydantic BaseSettings (prefix `RITHMIC_`)
- `scripts/mbo_levels_service.py` — manual env file loader (lines 435-450)

---

## 7. Connection Flow (async-rithmic internals)

### Step-by-step (from `plants/base.py`)

```
1. WebSocket connect to gateway URL
2. Send RequestRithmicSystemInfo (template 16)
3. Receive list of valid system names
4. Validate provided system_name is in the list
5. Close WebSocket
6. Reconnect to same gateway
7. Send RequestLogin (template 10) with credentials + infra_type
8. Receive heartbeat_interval from server
9. Send initial heartbeat
10. Plant is now connected and ready
```

### Four Plants (independent WebSocket connections)

| Plant | infra_type | Port (native) | Purpose | Templates |
|-------|-----------|---------------|---------|-----------|
| **TICKER_PLANT** | ticker | 56000 | Live market data (ticks, BBO, DOM) | 100-160 |
| **ORDER_PLANT** | order | 65000 | Order routing, fills, brackets | 300-353, 3504-3505 |
| **HISTORY_PLANT** | history | 64100 | Historical bars and ticks | 200-251 |
| **PNL_PLANT** | pnl | 45454 | Account and instrument PnL | 400-451 |

Default `client.connect()` connects ALL four plants. To connect selectively:

```python
from async_rithmic import SysInfraType

# Market data only (no order routing)
await client.connect(plants=[SysInfraType.TICKER_PLANT])

# Market data + orders (skip history and PnL)
await client.connect(plants=[SysInfraType.TICKER_PLANT, SysInfraType.ORDER_PLANT])
```

### Issue #49 Workaround (MANDATORY)

After `await client.connect()`, wait 500ms before subscribing to data:

```python
await client.connect()
await asyncio.sleep(0.5)  # Prevents ForcedLogout reconnection loop
await client.subscribe_to_market_data(symbol, exchange, DataType.ORDER_BOOK)
```

Implemented in: `deep6/data/rithmic.py` line 128, `scripts/mbo_levels_service.py` line 388

---

## 8. Connection Code Patterns

### Minimal Connection (test environment)

```python
from async_rithmic import RithmicClient, DataType, ReconnectionSettings

client = RithmicClient(
    user="your_user",
    password="your_pass",
    system_name="Rithmic Test",
    app_name="migo:DEEP6",
    app_version="2.0",
    url="rituz00100.rithmic.com:443",
    reconnection_settings=ReconnectionSettings(
        max_retries=10,
        backoff_type="exponential",
        interval=1.0,
        max_delay=60.0,
        jitter_range=(0.5, 1.5),
    ),
)

await client.connect()
await asyncio.sleep(0.5)  # Issue #49

await client.subscribe_to_market_data("NQ", "CME", DataType.ORDER_BOOK)
await client.subscribe_to_market_data("NQ", "CME", DataType.LAST_TRADE)
```

### Production Connection (DEEP6 Primary)

```python
client = RithmicClient(
    user="michael@fitsells.com",
    password="Madmoney1986!",
    system_name="Rithmic Paper Trading",
    app_name="migo:DEEP6-sim",       # Must use conformance-approved app_name
    app_version="2.0",
    url="rprotocol.rithmic.com:443",
    reconnection_settings=ReconnectionSettings(
        max_retries=20,
        backoff_type="exponential",
        interval=1.0,
        max_delay=60.0,
        jitter_range=(0.5, 1.5),
    ),
)
```

### Callback Registration Pattern (VERIFIED 2026-05-20)

```python
# MBO Depth (L2/L3) — individual order events at every price level
# This is the CORRECT way to get depth. Do NOT use on_order_book.
async def on_market_depth(update):
    fields = {f.name: v for f, v in update.ListFields()}
    price = fields.get("depth_price", [None])[0]
    size = fields.get("depth_size", [None])[0]
    update_type = fields.get("update_type", [None])[0]  # 1=add, 2=modify, 3=delete
    txn_type = fields.get("transaction_type", [None])[0]  # 1=buy, 2=sell
    order_id = fields.get("exchange_order_id", [None])[0]
    seq = fields.get("sequence_number", None)
    # process depth update...

client.on_market_depth += on_market_depth

# Ticks (last trade with aggressor) — returns DICT, not object
async def on_tick(tick):
    price = tick["trade_price"]       # float — e.g. 29296.0
    size = tick["trade_size"]         # int — e.g. 1
    aggressor = tick["aggressor"]     # int — 1=BUY, 2=SELL
    vwap = tick.get("vwap")           # float (not always present)
    dt = tick.get("datetime")         # datetime with tz
    order_id = tick.get("exchange_order_id")  # str
    # process tick...

client.on_tick += on_tick

# Connection lifecycle
client.on_connected += lambda plant: logger.info(f"{plant} connected")
client.on_disconnected += lambda plant: logger.warning(f"{plant} disconnected")
```

### CRITICAL: Tick Data Format

Ticks arrive as **dicts** (NOT objects with attributes). Key fields:

| Key | Type | Example | Notes |
|-----|------|---------|-------|
| `trade_price` | float | `29296.0` | Always present |
| `trade_size` | int | `1` | Always present |
| `aggressor` | int | `1`=BUY, `2`=SELL | Always present |
| `vwap` | float | `28907.25` | Not in snapshots |
| `net_change` | float | `-26.5` | From previous close |
| `volume` | int | `7201` | Cumulative session volume |
| `exchange_order_id` | str | `"6876835330373"` | Not in snapshots |
| `datetime` | datetime | `2026-05-19 22:38:34+00:00` | UTC |
| `data_type` | int | `1` | 1=LAST_TRADE |
| `is_snapshot` | bool | `True` | First tick is snapshot |

### Graceful Shutdown

```python
try:
    while running:
        await asyncio.sleep(0.25)
finally:
    await client.disconnect()
```

---

## 9. DEEP6 Connection State Machine

From `deep6v2/data/rithmic_client.py`:

```
DISCONNECTED ──connect()──> CONNECTING ──success──> CONNECTED
     ^                          |                      |
     |                        fail                  disconnect
     |                          |                      |
     |                          v                      v
     +────────────────── give up <──── RECONNECTING <── FROZEN
                                      (backoff)     (halt all
                                                     callbacks)
```

### States

| State | Description | Action |
|-------|-------------|--------|
| `DISCONNECTED` | Initial / terminal | Call `connect()` |
| `CONNECTING` | WebSocket handshake in progress | Wait |
| `CONNECTED` | Active, processing callbacks | Normal operation |
| `FROZEN` | Disconnect detected, callbacks halted | Awaiting reconnection |
| `RECONNECTING` | Exponential backoff retry | Automatic |

### FreezeGuard (D-17, D-19)

On disconnect: immediately enter FROZEN state. ALL callback processing halts.
Before unfreezing: reconcile positions to detect fills during disconnect.

Located in: `deep6/state/connection.py`

---

## 10. Data Subscription Types

### CRITICAL: Two Different Depth Subscriptions

```python
# WRONG for L2 depth — returns empty bid/ask arrays on Rithmic Paper Trading:
await client.subscribe_to_market_data(symbol, exchange, DataType.ORDER_BOOK)  # template 156 — EMPTY

# CORRECT for L2/L3 depth — returns individual order events (MBO):
await client.subscribe_to_market_depth(symbol, exchange, 0.0)  # template 117/160 — WORKS
# depth_price=0.0 subscribes to ALL price levels

# Last Trade (tick-by-tick with aggressor: BUY/SELL)
await client.subscribe_to_market_data(symbol, exchange, DataType.LAST_TRADE)

# Best Bid/Offer only
await client.subscribe_to_market_data(symbol, exchange, DataType.BBO)
```

### Depth-by-Order (MBO) Update Format

Each `on_market_depth` callback delivers a protobuf with:

```python
async def on_market_depth(update):
    fields = {f.name: v for f, v in update.ListFields()}
    # Key fields:
    #   depth_price:    [29296.0]        — price level
    #   depth_size:     [1]              — order size
    #   update_type:    [1]=add [2]=modify [3]=delete
    #   transaction_type: [1]=buy [2]=sell
    #   exchange_order_id: ['6876892018662']
    #   depth_order_priority: [104545033597]  — queue position
    #   template_id:    160
    #   sequence_number: 391749174       — for gap detection

client.on_market_depth += on_market_depth
```

Throughput: ~200+ updates/sec on NQ during RTH (verified 2026-05-20).

### Aggressor Verification Gate (D-03)

Before enabling footprint accumulation, sample 50 ticks to verify aggressor field:
- TransactionType.BUY/SELL must be present (not UNSPECIFIED)
- Fail if >10% of ticks are UNSPECIFIED
- Contact broker if aggressor field is not populated

Located in: `deep6/data/rithmic.py`

---

## 11. Multi-Service Considerations

### ForcedLogout Prevention

Rithmic limits concurrent sessions per account. Running multiple services
on the same credentials will cause ForcedLogout.

**Solutions:**
1. Use separate broker accounts (e.g., Apex for DEEP6, EdgeClear for other)
2. Run services at different times
3. Subscribe to L2 in only one service
4. Use different app_names for each service (still same session limit)

### DEEP6 Services That Connect to Rithmic

| Service | App Name | Plants Used |
|---------|----------|-------------|
| Main engine | `migo:DEEP6` | TICKER + ORDER + PNL |
| MBO levels service | `migo:DEEP6:mbo` | TICKER only |
| Feed adapter | `migo:DEEP6-sim` | TICKER only |

**WARNING**: Running R|Trader Pro AND a DEEP6 Python service simultaneously on the
same Apex account WILL cause ForcedLogout. Close R|Trader Pro before starting DEEP6,
or use separate credentials.

---

## 12. Error Troubleshooting

### Decision Tree

```
Connection fails
├── "You must specify valid SYSTEM_NAME: [...]"
│   → Wrong gateway URL for your system name
│   → Check Section 3 system name table
│   → system_name is CASE-SENSITIVE ("Apex" not "APEX")
│
├── "ForcedLogout" (template 77)
│   → Another session is active with same credentials
│   → Close R|Trader Pro or other Rithmic apps
│   → Or use different credentials
│
├── "Authentication failed"
│   → Wrong username/password
│   → Special chars in password may need URL-encoding
│   → Account locked (wait 15 min)
│   → Account not active with broker
│
├── "[Errno 11001] getaddrinfo failed"
│   → Hostname doesn't resolve (wrong URL)
│   → Check Section 2 for correct gateway hostnames
│
├── "Connection closed immediately after login"
│   → Issue #49: add 500ms delay after connect()
│   → See Section 7
│
├── "No data after subscribing"
│   → Confirm symbol format: "NQ" not "NQM6" for subscribe
│   → Market may be closed (check RTH hours: 6pm-5pm ET Sun-Fri)
│   → L2 subscription limit: one per account per gateway
│
├── "SSL certificate error"
│   → async-rithmic bundles its own cert at:
│   │   site-packages/async_rithmic/certificates/rithmic_ssl_cert_auth_params
│   → R|Trader Pro cert: RithmicCertificate.pk12 in install dir
│   → Cert may be outdated — update async-rithmic
│
└── "Reject" (template 75)
    → Server rejected request
    → Check rp_code in response for details
    → rpCode=13: broker API mode not enabled
```

### Common Error Codes

| rp_code | Meaning |
|---------|---------|
| `0` | Success |
| `7` | No data available |
| `13` | Not authorized — app_name not conformance-approved, or wrong system_name for account |
| `75` | Reject (generic server rejection) |
| `77` | ForcedLogout |

### rpCode 13 "Permission Denied" — Lessons Learned (2026-05-19)

This error means the credentials authenticate but the **API layer** rejects the connection.
Root causes we verified:

1. **Wrong system_name**: `michael@fitsells.com` is on `Rithmic Paper Trading`, NOT `Apex`.
   Using `system_name="Apex"` gives rpCode 13 even though Apex appears in the gateway's system list.
2. **Wrong app_name**: Only `migo:DEEP6-sim` has conformance approval. Using `migo:DEEP6` gives rpCode 13.
3. **Not a password error**: rpCode 13 is permission, not authentication. Wrong password gives a different error.

**Fix checklist**: Verify system_name matches the account (check R|Trader Pro title bar),
then verify app_name is conformance-approved.

---

## 13. Conformance & App Registration

### App Name Convention

All DEEP6 services use the `migo:` prefix (required by Rithmic, per Kashyap Upadhyay).

| Service | app_name | Status |
|---------|----------|--------|
| Feed adapter | `migo:DEEP6-sim` | Conformance granted 2026-04-14 |
| Main engine | `migo:DEEP6` | Pending |
| MBO service | `migo:DEEP6:mbo` | Pending |

### Conformance Process

1. Email `rapi@rithmic.com` with app_name and description
2. Run conformance script: connect ORDER_PLANT to test server, leave running 1+ hour
3. Rithmic reviews logs (1-2 weeks typical)
4. Upon approval: app_name whitelisted for production gateways

Script: `async_rithmic/scripts/conformance.py`

### Registration Email Template

```
Subject: R|API+ App Registration — [app_name]

I am requesting API registration for:
- App name: migo:DEEP6
- App version: 2.0
- Library: async-rithmic 1.5.9 (Python)
- Purpose: NQ futures order flow analysis and execution
- Broker: Apex Trader Funding
- System: Apex
- Gateway: rprotocol.rithmic.com (Chicago)

I have confirmed successful connection to the Rithmic Test environment.
Ready to run conformance testing at your convenience.
```

---

## 14. Gateway Probe Utility

To discover available system names on any gateway:

```python
import asyncio, ssl, websockets
from pathlib import Path
from async_rithmic import protocol_buffers as pb

async def probe_gateway(url):
    ssl_path = Path("site-packages/async_rithmic/certificates/rithmic_ssl_cert_auth_params")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(ssl_path)

    ws = await websockets.connect(url, ssl=ctx)
    req = pb.request_rithmic_system_info_pb2.RequestRithmicSystemInfo()
    req.template_id = 16
    data = req.SerializeToString()
    buf = len(data).to_bytes(4, 'big', signed=True) + data
    await ws.send(buf)

    resp_buf = await ws.recv()
    resp = pb.response_rithmic_system_info_pb2.ResponseRithmicSystemInfo()
    resp.ParseFromString(resp_buf[4:])
    await ws.close()

    return list(resp.system_name)

# Usage:
systems = asyncio.run(probe_gateway("wss://rprotocol.rithmic.com:443"))
print(systems)  # ['Apex', 'Rithmic 01', 'TopstepTrader', ...]
```

---

## 15. NQ Contract Reference

| Symbol | Exchange | Tick Size | Tick Value | Contract |
|--------|----------|-----------|------------|----------|
| NQ | CME | 0.25 | $5.00 | E-mini NASDAQ-100 |
| NQM6 | CME | 0.25 | $5.00 | June 2026 front month |
| MNQ | CME | 0.25 | $0.50 | Micro E-mini NASDAQ-100 |

**Subscribe using root symbol** `"NQ"`, not contract month `"NQM6"`.
The exchange handles continuous contract resolution automatically.

### Trading Hours (all ET)

| Session | Time |
|---------|------|
| Globex (electronic) | Sun 6:00 PM – Fri 5:00 PM |
| Regular Trading Hours (RTH) | Mon-Fri 9:30 AM – 4:15 PM |
| Pre-market | Mon-Fri 6:00 PM (prev) – 9:30 AM |
| Maintenance | Mon-Fri 5:00 PM – 6:00 PM |

---

## 16. Version & Dependency Reference

| Package | Version | Python | Purpose |
|---------|---------|--------|---------|
| async-rithmic | 1.5.9 | 3.10+ | R\|Protocol WebSocket + protobuf |
| websockets | 14.2 | — | WebSocket transport (async-rithmic dep) |
| protobuf | (bundled) | — | Message serialization |

Install location: `C:\Users\Tea\AppData\Local\Programs\Python\Python311\Lib\site-packages\async_rithmic\`

SSL cert: `async_rithmic/certificates/rithmic_ssl_cert_auth_params`

---

## 17. File Reference (DEEP6 Codebase)

| File | Purpose |
|------|---------|
| `scripts/mbo_levels_service.py` | Standalone DOM level tracker → JSON for NT8 |
| `ninjatrader/simulator/rithmic/rithmic_feed.py` | All gateway URLs, NDJSON adapter |
| `ninjatrader/simulator/rithmic/README.md` | Environment table, conformance status |
| `deep6v2/data/rithmic_client.py` | State machine wrapper |
| `deep6v2/config/rithmic.py` | Pydantic config with env prefix |
| `deep6/data/rithmic.py` | Connection factory, Issue #49, aggressor gate |
| `deep6/data/dom_feed.py` | DOM callback factory (SOLO/END filter) |
| `deep6/data/tick_feed.py` | Tick callback with aggressor verification |
| `deep6/state/connection.py` | FreezeGuard state machine |
| `deep6/config.py` | Central Config dataclass |
| `.env` / `.env.example` | Environment variable templates |
| `tests_v2/integration/test_rithmic_connection.py` | Connection integration test |
| `tests_v2/data/test_rithmic_client.py` | State machine unit tests |

### R|Trader Pro Files

| File | Purpose |
|------|---------|
| `C:\ProgramData\Rithmic\Rithmic Trader Pro\17.93.0.0\omneconfig.tbl` | Binary — all server/system/region config |
| `C:\ProgramData\Rithmic\Rithmic Trader Pro\17.93.0.0\omneconfig.lsa` | Login Server Agent endpoints |
| `C:\ProgramData\Rithmic\Rithmic Trader Pro\17.93.0.0\RithmicCertificate.pk12` | SSL certificate |
| `C:\ProgramData\Rithmic\Rithmic Trader Pro\17.93.0.0\Rithmic Trader Pro.exe` | Main executable |
| `C:\ProgramData\Rithmic\Rithmic Trader Pro\run_this_version.txt` | Active version selector |
| `C:\ProgramData\Rithmic\Rithmic Trader Pro\Settings\` | Saved user settings |

---

## Revision History

- **2026-05-20**: L2/L3 data confirmed working. Discovered `subscribe_to_market_depth()` is the
  correct method (template 117/160), NOT `subscribe_to_market_data(ORDER_BOOK)` (template 156 returns
  empty depth). Verified tick data format is dict with `trade_price`/`trade_size`/`aggressor` keys.
  Documented rpCode 13 troubleshooting. Updated all code examples to verified working patterns.
  Account: 101651 (Gonzalez), $100K paper, NQ L2 at 1,739 depth updates in 8 seconds.
- **2026-05-19**: Major rewrite. Extracted complete infrastructure from R|Trader Pro 17.93.0.0
  binary config (omneconfig.tbl). All 23 system names, native TCP port assignments,
  regional server infrastructure, login agent naming conventions, LSA endpoints.
  Switched from Apex (APEX-262674) to Rithmic Direct (michael@fitsells.com, Rithmic Paper Trading).
- **2026-05-18**: Initial creation. All gateway URLs verified via live WebSocket probe.
  Production gateway `rprotocol.rithmic.com:443` confirmed reachable with 22 systems.
