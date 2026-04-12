# External Integrations

**Analysis Date:** 2026-04-11

## APIs & External Services

**Market Data:**
- Rithmic Level 2 DOM (Order Book Feed)
  - What it's used for: E2 TRESPASS, E3 SPOOF, E4 ICEBERG engines consume real-time market depth updates to detect queue imbalances, spoofing, and iceberg orders. Minimum 40+ DOM levels required.
  - Integration: Real-time callbacks via `OnMarketDepth()` handler (DEEP6.cs lines 230-246). Market depth event args contain bid/ask prices and volumes at each DOM level. DEEP6 maintains rolling window of 10 DOM levels in `_bV[]`, `_aV[]`, `_bP[]`, `_aP[]` arrays (lines 131-132).
  - Auth: Integrated via NinjaTrader 8 broker connection (e.g., Rithmic CQG connector). No SDK setup required; NT8 abstracts credential handling.

**Gamma Exposure (GEX) Data:**
- GEX API Integration (Status: **NOT YET INTEGRATED** — Pending Phase 5a per README line 254)
  - What it will do: Provide gamma exposure levels (Call Wall, Put Wall, Gamma Flip, HVL) for E6 VP+CTX engine
  - Current state: GEX parameters are user-supplied via indicator settings (DEEP6.cs lines 101-107):
    - `GexHvl` — Manual input for GEX High Volatility Level price
    - `CallWall`, `PutWall`, `GammaFlip`, `PdVah`, `PdVal`, `PdPoc` — All manually configured
  - Future approach: Planned to auto-fetch from external GEX provider (provider TBD; candidates: Futures Analytica L2Azimuth API, etc.)
  - Impact: Currently E6 context engine relies on manual user calibration; automated GEX will unlock E7 ML quality classifier improvements

## Data Storage

**Databases:**
- None — DEEP6 is a stateless indicator. No persistent database.

**File Storage:**
- Local filesystem only
  - Indicator source: `Indicators\DEEP6.cs` (project-relative, ~1,010 lines)
  - Deployment target: `$(USERPROFILE)\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6.cs` (hot-deploy location)
  - Build artifacts: `bin\` folder (DLL and XML doc output)
  - Backups: `backups\` folder auto-created by Deploy-ToNT8.ps1 with timestamp-versioned backups of previously deployed DEEP6.cs

**Caching:**
- None — In-memory only. DEEP6 maintains rolling queues and circular buffers in memory for real-time processing:
  - E2: `_iLong` (62-tick long window), `_iShort` (12-tick short window) for imbalance histograms
  - E3: `_pLg` (list of large order timestamps) for spoof detection
  - E4: `_pTr` (list of trade prices/times) for iceberg pattern matching
  - All cleared on session reset (SessionReset method, line 310)

## Authentication & Identity

**Auth Provider:**
- None — DEEP6 is a NinjaTrader 8 indicator, not a standalone application. Authentication is handled entirely by:
  - NT8 broker connector (Rithmic, etc.) — handles exchange credentials
  - NT8 username/password for NT8 login

**Implementation approach:**
- No external API keys, OAuth tokens, or authentication headers required
- All market data access flows through NT8's authenticated broker connection

## Monitoring & Observability

**Error Tracking:**
- None — No external error tracking service

**Logs:**
- Console output via `Print()` (NT8 Output window)
  - On load: `"[DEEP6] Loaded. Volumetric=" + v + " Instrument=" + Instrument.FullName` (DEEP6.cs line 223)
  - Used for debugging and validation during development
- Right panel LOG tab (built-in):
  - Timestamped event history of signals and state changes
  - Implemented via `_logItems` List<Tuple> and UpdatePanel method (DEEP6.cs lines 843-927)

**Performance Metrics:**
- Built-in monitoring via header bar and status pills:
  - DOM ● LIVE indicator (green dot when data flowing, red when disconnected)
  - TICK REPLAY toggle (gray = live, orange = historical)
  - Tick counter in CVD column
  - No external APM/monitoring integration

## CI/CD & Deployment

**Hosting:**
- NinjaTrader 8 — Single-machine indicator running inside NT8 process. Not a cloud service.

**Deployment Target:**
- Windows local filesystem: `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6.cs`
- Post-build MSBuild target copies compiled source from project to NT8 Custom folder (DEEP6.csproj lines 124-132)
- Manual recompile in NT8: Tools → Edit NinjaScript → Indicator → DEEP6 → F5

**Deployment Methods:**
1. **Manual Deploy Script** (Deploy-ToNT8.ps1):
   - Copies `Indicators\DEEP6.cs` to NT8 Custom folder
   - Creates timestamped backup of previous version
   - Validates copy integrity (file size check)
   - Optionally triggers NT8 recompile via COM automation
   - Run: `.\scripts\Deploy-ToNT8.ps1` or VS Code task "DEEP6: Deploy to NT8" (tasks.json line 31)

2. **Auto-Deploy (Watch Mode)** (Watch-AndDeploy.ps1):
   - FileSystemWatcher monitors `Indicators\DEEP6.cs` for changes
   - On save: 800ms debounce, then auto-copy to NT8 Custom folder
   - Immediate feedback in PowerShell terminal
   - Run: `.\scripts\Watch-AndDeploy.ps1` or VS Code task "DEEP6: Watch + Auto-Deploy" (tasks.json line 54)
   - Press Ctrl+C to stop watching

3. **Build + Deploy** (VS Code Tasks):
   - "DEEP6: Build + Deploy" (tasks.json line 42) — Release build then auto-deploy
   - Sequence: `dotnet build --configuration Release` → Deploy-ToNT8.ps1

4. **NinjaTrader 8 Compile**:
   - After file deployed to NT8 Custom folder, manual compile required in NT8 NinjaScript Editor
   - Trigger-NT8Compile.ps1 attempts to automate via COM (Trigger-NT8Compile.ps1 line 104)
   - Default flow: F5 key in NT8 editor

**CI Pipeline:**
- Not detected — No GitHub Actions, Azure Pipelines, or other CI configured. Deployment is manual via PowerShell scripts and VS Code tasks.

## Environment Configuration

**Required env vars:**
- `USERPROFILE` — Standard Windows env var; points to user home directory. Used to resolve NT8 Custom folder path (`%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom`)

**NT8 Path Configuration:**
- Default: `C:\Program Files\NinjaTrader 8`
- Override: Set `$(NT8Path)` property in DEEP6.csproj (line 21) or pass to dotnet build: `dotnet build /p:NT8Path="D:\NT8"`
- Used by project to locate NT8 assemblies for compilation

**Secrets location:**
- None — DEEP6 handles no secrets or credentials. Broker authentication is delegated to NT8.

## Webhooks & Callbacks

**Incoming:**
- None — DEEP6 is not a web service

**Outgoing:**
- None — No external HTTP/webhook calls. All communication flows through NinjaTrader 8 broker connector.

## Real-Time Data Processing

**Market Depth Stream:**
- `OnMarketDepth(MarketDepthEventArgs e)` — Callback fired on Level 2 DOM updates. Rithmic feed can fire up to 1,000+ times per second during active markets (README line 10).
- Engine E2 and E3 subscribe to these callbacks to track DOM queue positions and detect spoofing/icebergs in near real-time.

**Last Trade Stream:**
- `OnMarketData(MarketDataEventArgs e)` — Callback fired on every trade (Last price/volume). Used by E4 ICEBERG engine to detect iceberg refills (DEEP6.cs line 249).

**Bar Update Stream:**
- `OnBarUpdate()` — Called on each candle close and every tick (if Calculate = OnEachTick). Runs all scoring engines (E1, E5, E6, E7), updates UI, fires signals (DEEP6.cs lines 226-239).

**Chart Render Stream:**
- `OnRender(ChartControl cc, ChartScale cs)` — Called by NT8 whenever chart needs redraw (tick updates, zoom, scroll). Renders SharpDX footprint cells and signal boxes (DEEP6.cs lines 259-266).

## Data Feed Requirements

**Instrument:**
- NQ (Micro E-mini Nasdaq-100) futures. Optimized for 1-minute volumetric bars.
- Other instruments: Any US futures with Rithmic Level 2 DOM and Volumetric Bars support.

**Bar Type:**
- VolumetricBarsType (NT8 Order Flow+ exclusive) — Provides bid/ask volume breakdown per price level per bar. Required by E1 FOOTPRINT engine (footprint cells show this data).

**Data Depth:**
- Rithmic Level 2: minimum 40+ DOM levels. E4 ICEBERG depends on deep order book to detect synthetic icebergs.

---

*Integration audit: 2026-04-11*
