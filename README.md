# DEEP6 v1.0.0

> **Seven-Layer Institutional-Grade Market Intelligence System for NQ Futures**
> NinjaTrader 8 · Rithmic Level 2 · Volumetric Bars · SharpDX · WPF

---

## What is DEEP6?

DEEP6 is a hedge fund-grade footprint chart indicator for NinjaTrader 8 that processes Rithmic Level 2 DOM data at up to **1,000 callbacks per second** and synthesizes it into a unified 0–100 confidence score per bar.

Seven independent engines vote on market direction. When 4+ engines agree and the combined score exceeds 80 points, DEEP6 fires a **TYPE A (Triple Confluence)** signal with a gold-bordered label box directly on the chart.

```
DEEP6 Unified Score = E1_FOOTPRINT(25) + E2_TRESPASS(20) + E3_SPOOF(15)
                    + E4_ICEBERG(15)   + E5_MICRO(10)    + E6_VP+CTX(15)
                    + E7_ML_QUALITY(classifier)
                    × agreement_ratio  (if ≥ 4 engines align)
```

---

## Project Structure

```
DEEP6/
├── Indicators/
│   └── DEEP6.cs              ← Main NinjaScript indicator (1,010 lines)
│
├── scripts/
│   ├── Deploy-ToNT8.ps1      ← One-click deploy to NT8 Custom folder
│   ├── Watch-AndDeploy.ps1   ← Auto-deploy on every file save (watch mode)
│   └── Trigger-NT8Compile.ps1← Bring NT8 to foreground for manual compile
│
├── docs/
│   ├── DEEP6_Master_Execution_Plan.docx  ← 42-page hedge fund spec
│   └── DEEP6_Master_Blueprint_v2.md      ← Complete UI/UX element catalog
│
├── tests/                    ← Engine unit tests (Phase 4 — see roadmap)
│
├── .vscode/
│   ├── settings.json         ← Editor + OmniSharp config
│   ├── extensions.json       ← Recommended extensions
│   ├── tasks.json            ← Build / deploy / watch tasks
│   └── launch.json           ← Attach debugger to NT8 process
│
├── DEEP6.csproj              ← .NET Framework 4.8 project (NT8 + SharpDX refs)
├── .editorconfig             ← Code style rules
├── .gitignore
└── README.md
```

---

## Quick Start

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| NinjaTrader 8 | 8.0.23+ | Lifetime License required for Volumetric Bars |
| .NET SDK | 7.0+ | For VS Code IntelliSense (not for NT8 runtime) |
| VS Code | 1.85+ | With C# Dev Kit extension |
| Rithmic Data | Level 2 | 40+ DOM levels — required for E2/E3/E4 engines |

### 1. Open in VS Code

```bash
# Clone or extract the project
cd DEEP6
code .
```

Install recommended extensions when VS Code prompts (or run from Command Palette):
`Extensions: Show Recommended Extensions`

### 2. Configure NT8 path (if non-default)

Edit `DEEP6.csproj` line 16 if your NT8 is not in `C:\Program Files\NinjaTrader 8`:

```xml
<NT8Path>D:\NinjaTrader 8</NT8Path>
```

### 3. Build (for IntelliSense)

```
Ctrl+Shift+B  →  DEEP6: Build (Debug)
```

This compiles against NT8 assemblies so VS Code IntelliSense has full type information.

### 4. Deploy to NT8

```
Ctrl+Shift+P  →  Tasks: Run Task  →  DEEP6: Deploy to NT8
```

Or run directly from terminal:
```powershell
.\scripts\Deploy-ToNT8.ps1
```

### 5. Compile in NT8

1. Open NinjaTrader 8
2. `Tools → Edit NinjaScript → Indicator → DEEP6`
3. Press **F5** to compile
4. Add DEEP6 to a Volumetric Bars chart (right-click chart → Indicators → DEEP6)

### 6. Watch mode (hot-reload during development)

```
Ctrl+Shift+P  →  Tasks: Run Task  →  DEEP6: Watch + Auto-Deploy
```

Every time you save `Indicators/DEEP6.cs`, it automatically copies to NT8. Then just press F5 in NT8's NinjaScript Editor to recompile.

---

## Seven Engines

| # | Engine | Max Pts | Algorithm | Source |
|---|--------|---------|-----------|--------|
| E1 | **FOOTPRINT** | 25 | Absorption / Exhaustion / Stacked Imbalances / STKt Tiers / CVD | VolumetricBarsType |
| E2 | **TRESPASS** | 20 | Multi-level weighted DOM queue imbalance + logistic regression | Gould & Bonart (2015) arXiv:1512.03492 |
| E3 | **COUNTERSPOOF** | 15 | Wasserstein-1 distribution monitor + large-order cancel detection | Tao et al. (2020) + Do & Putniņš (2023) |
| E4 | **ICEBERG** | 15 | Native (trade > DOM) + Synthetic (refill < 250ms) iceberg detection | Zotikov & Antonov (2021) |
| E5 | **MICRO** | 10 | Naïve Bayes combination of E1 + E2 + E4 likelihoods → P(bull)/P(bear) | Gould & Bonart extension |
| E6 | **VP+CTX** | 15 | DEX-ARRAY + VWAP zones + IB pattern + GEX regime + POC migration | Futures Analytica (2024) |
| E7 | **ML QUALITY** | — | Kalman filter [price, velocity] + 8-feature logistic quality classifier | Kalman (1960) |

### Signal Classification

| Type | Score | Engines | Description |
|------|-------|---------|-------------|
| **TYPE A** | ≥ 80 | 5+ | Triple Confluence — gold bordered box on chart. Label: `ABSORB·TRESS·ICE·LVN·DEX` |
| **TYPE B** | ≥ 65 | 4+ | Double Confluence — amber bordered box. Label: `GEX+TRESS+MICRO>82` |
| **TYPE C** | ≥ 50 | 4+ | Single Signal — alert only, no chart box |
| **QUIET** | < 50 | — | No signal |

---

## UI Components

### Header Bar (top, full width)
10 live-updating status columns: `DAY TYPE | IB TIER | GEX REGIME | VWAP ZONE | SPOOF SCORE | TRESPASS | CVD | DOM ● LIVE | TICK REPLAY`

### Left Tab Bar (vertical, chart left)
9 tabs: `IN / 3 MIN / 5 MIN / FOOTPRINT / VOL PROFILE / VWAP ±2σ / GEX LEVELS / IB LEVELS / SIGNALS`

### Status Pills (between tabs and chart)
9 live pills: `TREND BULL | IB | NARROW·C-CONFIRMED | GEX | NEG GAMMA·AMPLIFYING | DEV POC | MIGRATING ↑·8 BARS | VWAP-POC | 28 ticks·TRENDING`

### SharpDX Footprint (main chart)
- Bid/Ask volume at each price level inside every bar
- Imbalance color gradient (green = buy pressure, red = sell pressure)
- POC highlighted with gold left border
- Delta row below bars: `△ +1,340` or `△ -2,218 · BULL ABSORB`

### 15 Price Level Lines
`VWAP ±1σ/2σ | IBH/IBL | DEV POC | ⚡GEX HVL | 📞CALL WALL | PUT WALL | Gamma Flip | pdVAH/pdVAL`

### Right Panel (4 tabs)
**DEEP6:** Score gauge (0–100 arc) + 6 score bars + 9 status dots + signal feed
**GEX:** Regime + call/put walls + HVL
**LEVELS:** Session + IB + previous day levels
**LOG:** Timestamped event history

---

## Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `AbsorbWickMin` | 30% | Minimum wick % for absorption signal |
| `AbsorbDeltaMax` | 0.12 | Max |delta|/vol ratio for balanced absorption |
| `ImbRatio` | 1.5 | Ask/bid ratio threshold for imbalance cell coloring |
| `StkT1/T2/T3` | 3/5/7 | Stacked imbalance tier thresholds |
| `DomDepth` | 5 | DOM levels for E2 Trespass calculation |
| `Lambda` | 0.5 | Exponential decay weight per DOM level |
| `LBeta` | 2.5 | Logistic regression slope (NQ-calibrated) |
| `SpooW1` | 0.4 | Wasserstein-1 threshold for spoof detection |
| `SpooQty` | 500 | Minimum contracts to track as potential spoof |
| `IceMs` | 250 | Synthetic iceberg refill detection window (ms) |
| `DexLB` | 3 | DEX-ARRAY lookback bars |
| `GexHvl` | 0 | GEX High Volatility Level price (user-supplied) |
| `CallWall` | 0 | Largest call open interest strike |
| `PutWall` | 0 | Largest put open interest strike |
| `TypeAMin` | 80 | TYPE A signal score threshold |
| `TypeBMin` | 65 | TYPE B signal score threshold |
| `MinAgree` | 4 | Minimum engines that must agree on direction |

---

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | i7-12700K / Ryzen 7 7700X | i9-14900K / Ryzen 9 7950X |
| RAM | 32GB DDR4 | 64GB DDR5 |
| Storage | NVMe SSD 512GB | NVMe SSD 2TB (7,000 MB/s) |
| GPU | 4GB VRAM (SharpDX rendering) | RTX 3060 8GB |
| Network | 1Gbps Ethernet (NO WiFi) | Fiber <20ms to CME Aurora |
| OS | Windows 10 64-bit | Windows 11 Pro |

**VPS (for 24/7 operation):** [QuantVPS](https://quantvps.com) near CME Aurora, Chicago.

---

## Development Workflow

```
┌─────────────────────────────────────────────────────┐
│  VS Code                                            │
│                                                     │
│  Edit Indicators/DEEP6.cs                           │
│         │                                           │
│         │ Ctrl+S (save)                             │
│         ▼                                           │
│  Watch-AndDeploy.ps1 detects change                 │
│         │                                           │
│         │ copy (debounced 800ms)                    │
│         ▼                                           │
│  Documents\NinjaTrader 8\bin\Custom\Indicators\     │
│  DEEP6.cs                                           │
│         │                                           │
│         │ F5 in NT8 NinjaScript Editor              │
│         ▼                                           │
│  NinjaTrader 8 compiles + loads                     │
│  → Live chart updates instantly                     │
└─────────────────────────────────────────────────────┘
```

---

## Build Status

| Phase | Name | Status |
|-------|------|--------|
| P1 | Foundation + WPF Shell | ✅ Complete |
| P2 | All 7 Engines Full | ✅ Complete |
| P3a | Header Bar | ✅ Complete |
| P3b | Left Tab Bar | ✅ Complete |
| P3c | Status Pills | ✅ Complete |
| P3d | SharpDX Footprint Rendering | ✅ Complete |
| P3e | Signal Label Boxes | ✅ Complete |
| P3f | STKt Markers | ✅ Complete |
| P3g | GEX / LEVELS / LOG Tabs | ✅ Complete |
| P3h | DEX-ARRAY + STKt Engine | ✅ Complete |
| P3i | ML Baseline Tracking | ✅ Complete |
| P4a | Backtesting Config | 🔜 Next |
| P4b | Auto-Execution Layer | 🔜 Pending |
| P5a | GEX API Integration | 🔜 Pending |
| P5b | Parameter Calibration | 🔜 Pending |

---

## Academic References

1. Gould, M. D., & Bonart, J. (2015). Queue imbalance as a one-tick-ahead price predictor in a limit order book. *arXiv:1512.03492*
2. Zotikov, D., & Antonov, A. (2021). CME iceberg order detection and prediction. *Quantitative Finance, 21*(11), 1977–1992.
3. Tao, X., Day, A., Ling, L., & Drapeau, S. (2020). On detecting spoofing strategies in high frequency trading. *arXiv:2009.14818*
4. Do, B. L., & Putniņš, T. J. (2023). Detecting layering and spoofing in markets. *SSRN:4525036*
5. Futures Analytica LLC (2024). L2Azimuth Whitepaper. futuresanalytica.com
6. Kalman, R. E. (1960). A new approach to linear filtering and prediction problems. *Journal of Basic Engineering, 82*(1), 35–45.

---

## License & Confidentiality

**CONFIDENTIAL** — Peak Asset Performance LLC — For internal use only.

This system embodies proprietary trading methodology. Do not distribute.

---

*DEEP6 v1.0.0 · Peak Asset Performance LLC · April 2026*
