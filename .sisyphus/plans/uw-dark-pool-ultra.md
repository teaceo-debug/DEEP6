# UW Institutional Dark Pool Ultra — Replication Plan

## TL;DR

> **Quick Summary**: Replicate the "UW Institutional Dark Pool Ultra" NinjaTrader indicator inside the GEX Doctor desktop app AND as an NT8 indicator overlay. Add 13F institutional ownership, floor trades, dark pool levels with volume/count, market tide, 10-signal grid with confluence scoring, and swing equilibrium — all from Unusual Whales + Massive + FlashAlpha APIs.
>
> **Estimated Effort**: Large (multi-session)
> **Parallel Execution**: YES — 6 tracks

---

## What We're Building

### From the Reference Screenshot

**LEFT PANEL — Institutional Intelligence HUD:**
1. INST FLOW — net institutional direction (BUY/SELL LEAN)
2. 13F OWNERSHIP — top 5 holders with $ amounts
3. LATEST 13F FILINGS — recent filing activity
4. FLOOR TRADES / LIT FLOW — buy/sell volume, recent prints
5. DARK POOL TODAY — print count, buy/sell vol, accumulation/distribution %
6. MARKET TIDE — bull/bear premium balance
7. SIGNAL GRID — 10 signals each BUY/SELL/HOLD/MIXED/NEUTRAL
8. CONFLUENCE — X/10 BUY | Y/10 SELL

**CHART OVERLAY:**
- RESIST/SUPPORT levels with price, volume, count, multiplier
- SWING EQUILIBRIUM line
- Dark pool zone shading
- Institutional order blocks

**RIGHT PANEL:**
- Dark Pool Bias box (direction + stats)

### Data Sources
- **Unusual Whales** (primary): dark pool, 13F, institutional flow, market tide, sweeps
- **Massive/Polygon**: options chain, OI, volume profile
- **FlashAlpha**: GEX levels (already wired)

### Architecture Decision
- **Desktop app**: Add as a NEW TAB/PAGE alongside existing GEX terminal (not replace it)
- **NT8 indicator**: Extend GEXTerminal.cs to render DP levels + support/resist OR create new DEEP6DarkPoolUltra.cs
- **Backend**: Extend UW adapter with new endpoints, add new data models

---

## TODOs

- [x] 1. Extend UW Adapter — Institutional Data Endpoints

  **What to do**:
  - Add new methods to `gex_terminal/engine/adapters/unusual_whales.py`:
    - `fetch_institutional_flow(ticker)` — GET /api/option-trades/flow-alerts filtered for QQQ
    - `fetch_13f_ownership(ticker)` — GET /api/stock/{ticker}/ownership  
    - `fetch_latest_filings()` — GET /api/institutions/latest_filings
    - `fetch_dark_pool_detailed(ticker)` — GET /api/darkpool/{ticker} with full print data
    - `fetch_market_tide()` — GET /api/market/market-tide
    - `fetch_oi_change(ticker)` — GET /api/stock/{ticker}/oi-change
    - `fetch_flow_alerts(ticker)` — GET /api/option-trades/flow-alerts with rule filters
  - Create new Pydantic models in schemas.py for each response
  - Rate limit awareness: stagger calls, respect 120 req/min
  - All endpoints use Bearer auth with existing UW key

  **Category**: `deep`
  **Skills**: [`unusual-whales/api-reference`, `unusual-whales/institutional`, `unusual-whales/options-flow`]

- [x] 2. Institutional Intelligence Data Models

  **What to do**:
  - Create `gex_terminal/schemas_institutional.py` with models:
    - `InstitutionalHolder` — name, shares, value, change, pct
    - `Filing13F` — institution, date, total_value, action
    - `FloorTrade` — price, size, premium, timestamp, venue
    - `DarkPoolSession` — print_count, buy_vol, sell_vol, net_premium, bias
    - `MarketTide` — call_premium, put_premium, direction, strength
    - `SignalGridRow` — signal_name, direction (BUY/SELL/HOLD/MIXED/NEUTRAL), score
    - `SignalGrid` — rows list, confluence_buy, confluence_sell
    - `DarkPoolLevel` — price, volume, count, multiplier, level_type (SUPPORT/RESIST)
    - `InstitutionalSnapshot` — aggregates all above into one snapshot
  - All models frozen Pydantic BaseModel

  **Category**: `quick`

- [x] 3. Signal Grid Engine

  **What to do**:
  - Create `gex_terminal/engine/signal_grid.py`
  - 10 signal rows, each independently scored:
    1. 13F Institutions — from ownership changes
    2. Floor/Lit Flow — from flow direction
    3. Zero Push — price at zero premium level
    4. Market Tide — from bull/bear premium
    5. Multi-Day Swing — from dark pool level persistence
    6. Daily OI Bias — from OI change direction
    7. Sweep Flow — from sweep alerts
    8. Block Flow — from large block trades
    9. OI Change — from OI delta
    10. Dark Pool Blocks — from clustered DP prints
  - Each returns: BUY / SELL / HOLD / MIXED / NEUTRAL
  - Confluence: count BUY signals and SELL signals out of 10

  **Category**: `deep`
  **Skills**: [`options-bias-engine/step4-cross-validation/conviction-matrix`]

- [x] 4. Dark Pool Level Computation (Support/Resistance)

  **What to do**:
  - Enhance dark pool clustering with volume, count, multiplier
  - Create `gex_terminal/engine/dp_levels.py`:
    - Cluster prints by 0.5% price proximity
    - For each cluster: compute premium-weighted center, total volume, print count
    - Classify as SUPPORT (below current price) or RESIST (above)
    - Compute multiplier (volume relative to median cluster)
    - Compute STD (standard deviation of print prices within cluster)
  - Convert all levels to NQ via dynamic ratio
  - Sort by total premium (strongest levels first)

  **Category**: `deep`
  **Skills**: [`unusual-whales/dark-pool`, `dark-pool-nq-charting/charting-methodology`]

- [x] 5. Swing Equilibrium Engine

  **What to do**:
  - Create `gex_terminal/engine/swing_equilibrium.py`
  - Computation: weighted average of:
    - Dark pool cluster centers (40% weight)
    - Volume profile POC from Massive (40% weight)
    - GEX gamma flip level (20% weight)
  - Track equilibrium over multiple days (4d default)
  - Output: equilibrium_price, period, confidence
  - Optionally reuse `confluence_system/equilibrium_module.py` SFV computation

  **Category**: `unspecified-high`

- [ ] 6. Desktop App UI — Institutional Intelligence Panel

  **What to do**:
  - Create new React components in `gex_terminal/ui/components/`:
    - `InstitutionalPanel.tsx` — left-side HUD with all institutional data
    - `SignalGridPanel.tsx` — 10-row signal grid with color-coded BUY/SELL
    - `DarkPoolLevelsPanel.tsx` — support/resist levels with volume bars
    - `SwingEquilibriumPanel.tsx` — equilibrium line info
  - Add tab system to page.tsx: "GEX Analysis" (existing) | "Institutional DP"
  - Or: expand window to 1200x800 with left panel for institutional data
  - Style: same retro green terminal aesthetic

  **Category**: `visual-engineering`

- [ ] 7. NT8 Indicator — Dark Pool Levels Overlay

  **What to do**:
  - Extend `GEXTerminal.cs` or create new `DEEP6DarkPoolUltra.cs`
  - Read dark pool levels from NT8 JSON (extend bridge output)
  - Draw support levels (green horizontal lines with labels)
  - Draw resistance levels (red horizontal lines with labels)
  - Draw swing equilibrium line (cyan dashed)
  - Add dark pool zone shading (semi-transparent green/red rectangles)
  - Add dark pool bias text box (bottom-right, like the reference)

  **Category**: `deep`
  **Skills**: [`nt8-expert`, `ninjatrader-builder-doctor`]

- [ ] 8. Bridge + Integration

  **What to do**:
  - Update orchestrator to poll new UW endpoints
  - Update NT8 bridge to include institutional data in JSON
  - Update GEXTerminalSnapshot with institutional fields
  - Rebuild Next.js static export with new components
  - Restart Electron app with new data flowing
  - Verify NT8 indicator shows dark pool levels

  **Category**: `unspecified-high`

---

## Execution Strategy

```
Wave 1 (parallel — data layer):
T1: UW adapter extensions (new API endpoints)
T2: Data models (schemas)

Wave 2 (parallel — computation, after T1+T2):
T3: Signal grid engine
T4: Dark pool level computation
T5: Swing equilibrium engine

Wave 3 (parallel — UI + NT8, after T3-T5):
T6: Desktop app UI panels
T7: NT8 indicator overlay

Wave 4 (integration, after all):
T8: Bridge + orchestrator wiring + restart
```

---

## Success Criteria

- [ ] UW API fetches institutional flow, 13F, dark pool, market tide, sweeps
- [ ] Signal grid shows 10 signals with BUY/SELL/HOLD/MIXED/NEUTRAL
- [ ] Dark pool support/resist levels computed with volume + count
- [ ] Swing equilibrium line visible
- [ ] Desktop app shows institutional panel alongside GEX analysis
- [ ] NT8 indicator draws dark pool levels on chart
- [ ] Confluence score visible (X/10 BUY | Y/10 SELL)
- [ ] All existing tests still pass
