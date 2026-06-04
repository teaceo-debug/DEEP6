# DEEP6 EquiGEX

Institutional equilibrium model overlay for ES/NQ futures. Classifies price into Premium, Equilibrium, and Discount zones using a Synthetic Fair Value (SFV) line derived from GEX zero-gamma levels and anchored VWAP, rendered with Bloomberg Terminal aesthetic SharpDX graphics.

## Phase 1 Features

- **Synthetic Fair Value (SFV)** — Weighted blend of weekly zero-gamma, daily zero-gamma, and weekly AVWAP. Bold yellow line on chart.
- **Premium/Discount Zones** — ATR-based bands around SFV. Red fill above (premium), green fill below (discount), gray equilibrium between.
- **Bias Chip** — Composite directional score from 4 factors: HH/HL trend, zone position, gamma regime, price vs daily zero-gamma. Displayed as a pill in the top-right corner (green BULLISH / red BEARISH / gold NEUTRAL).
- **JSON GEX Sidecar** — Reads GEX data from an external JSON file. 30-second polling via `System.Threading.Timer`. Thread-safe access with lock pattern.
- **Stale Feed Detection** — 10-minute threshold on the `asof` timestamp. Red badge when JSON is missing, stale, or unreadable.
- **Anchored VWAP** — Programmatic weekly VWAP anchored to Sunday 6 PM ET (futures open). Resets automatically. DST-aware via `TimeZoneInfo`.
- **HH/HL Trend Detection** — Market structure via 5-bar left / 2-bar right pivot swing points on the primary 4H series.
- **Instrument Auto-Detection** — Supports ES, NQ, MES, MNQ. Micro contracts normalize to their full-size root (MNQ → NQ, MES → ES).

## File Structure

```
EquiGEX/
├── DEEP6EquiGEX.cs           Main indicator lifecycle, properties, OnBarUpdate dispatch
├── DEEP6EquiGEX.Models.cs    JSON DTOs, enums, GexState holder, JSON loader with stale detection
├── DEEP6EquiGEX.Engines.cs   AVWAP, HH/HL trend, SFV calculation, zone classifier, bias chip scoring
├── DEEP6EquiGEX.Render.cs    Full SharpDX rendering (SFV line, zone fills, bands, bias chip, stale badge, header)
└── gex_snapshot_example.json  Example GEX data file matching the spec schema
```

All 4 `.cs` files are partial classes under namespace `NinjaTrader.NinjaScript.Indicators.DEEP6`.

## JSON Schema

The indicator reads GEX data from an external JSON file. The file is written by an external Python service or manually — the indicator only reads.

**File location** (default):
```
%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\GEX\gex_snapshot.json
```

Override via the `GEX JSON Path` setting if using a custom location.

### Schema

```json
{
  "asof": "2024-05-20T15:30:00Z",
  "underlying": "ES",
  "spot": 5308.75,
  "weekly": {
    "strikes": [
      { "k": 5100, "gex": -0.42 },
      { "k": 5200, "gex": 0.34 }
    ],
    "call_wall": 5375,
    "zero_gamma": 5240,
    "put_wall": 5115,
    "net_gex": 1.32
  },
  "daily": {
    "strikes": [
      { "k": 5270, "gex": -0.25 },
      { "k": 5302, "gex": 0.10 }
    ],
    "call_wall": 5325,
    "zero_gamma": 5302,
    "put_wall": 5270,
    "net_gex": -0.24
  }
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `asof` | string (ISO 8601 UTC) | Timestamp of the GEX snapshot. Used for stale detection. |
| `underlying` | string | Root symbol (`"ES"` or `"NQ"`). Must match chart instrument after normalization. |
| `spot` | number | Underlying spot price at snapshot time. |
| `weekly.strikes` | array | Weekly expiry strike-level GEX data. |
| `weekly.strikes[].k` | number | Strike price. |
| `weekly.strikes[].gex` | number | Gamma exposure at this strike (billions $). |
| `weekly.call_wall` | number | Strike with highest positive GEX (weekly). |
| `weekly.zero_gamma` | number | Price level where net gamma flips sign (weekly). Used in SFV calculation. |
| `weekly.put_wall` | number | Strike with most negative GEX (weekly). |
| `weekly.net_gex` | number | Net aggregate gamma exposure (weekly). Used in gamma regime classification. |
| `daily.strikes` | array | Daily (0DTE) expiry strike-level GEX data. |
| `daily.strikes[].k` | number | Strike price. |
| `daily.strikes[].gex` | number | Gamma exposure at this strike (billions $). |
| `daily.call_wall` | number | Strike with highest positive GEX (daily). |
| `daily.zero_gamma` | number | Price level where net gamma flips sign (daily). Used in SFV calculation and bias chip. |
| `daily.put_wall` | number | Strike with most negative GEX (daily). |
| `daily.net_gex` | number | Net aggregate gamma exposure (daily). Used in gamma regime classification. |

## User Settings

| Setting | Group | Default | Description |
|---------|-------|---------|-------------|
| Weight: Weekly ZeroGamma | SFV Weights | 0.50 | Contribution of weekly zero-gamma level to the SFV blend. |
| Weight: Daily ZeroGamma | SFV Weights | 0.30 | Contribution of daily zero-gamma level to the SFV blend. |
| Weight: AVWAP | SFV Weights | 0.20 | Contribution of weekly anchored VWAP to the SFV blend. |
| Volatility Multiplier | Bands | 2.0 | ATR(14) multiplier for Premium/Discount band width. |
| GEX JSON Path | Data | _(empty — uses default)_ | Custom path to `gex_snapshot.json`. Leave empty for default location. |
| Show Dashboard | Display | true | Show/hide the header bar, bias chip, and stale badge overlay. |
| Show Debug Values | Display | false | Print engine values (AVWAP, SFV, trend, bias score) to the NT8 Output window. |

Weights are automatically normalized if they don't sum to 1.0.

## Supported Instruments

| Instrument | Root | Supported |
|------------|------|-----------|
| ES (E-mini S&P 500) | ES | Yes |
| NQ (E-mini Nasdaq-100) | NQ | Yes |
| MES (Micro E-mini S&P 500) | ES | Yes (normalizes to ES) |
| MNQ (Micro E-mini Nasdaq-100) | NQ | Yes (normalizes to NQ) |

Unsupported instruments display a warning in the Output window and skip all engine calculations.

## Stale Feed Behavior

The indicator monitors the `asof` timestamp in the JSON file:

- **Threshold**: 10 minutes (600 seconds)
- **Polling interval**: 30 seconds
- **When stale or missing**:
  - Red badge appears below the bias chip showing `STALE FEED` or `MISSING JSON`
  - SFV calculation falls back to available components (AVWAP-only if both zero-gamma values are zero)
  - Bias chip continues with reduced inputs (gamma and daily zero-gamma scores become 0)
- **When JSON file is removed entirely**: No crash. Badge shows `MISSING JSON`. Indicator degrades gracefully.
- **When asset doesn't match**: Badge shows `NO MATCHING ASSET`. Indicator waits for matching JSON.

## Recommended Chart Setup

- **Timeframe**: 4H (primary design target)
- **Chart type**: Candlestick
- **Calculate**: On bar close (set automatically by the indicator)

## Phase 2 Roadmap

Future enhancements (not in Phase 1):
- GEX histogram overlay showing strike-level gamma exposure
- Key levels table (call wall, put wall, zero-gamma, expected move)
- Alert conditions for zone transitions
- Sound alerts (EnableSoundAlerts setting)
- Enhanced debug dashboard
