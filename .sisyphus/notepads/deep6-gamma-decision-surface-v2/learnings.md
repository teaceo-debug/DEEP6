# Learnings — deep6-gamma-decision-surface-v2

## [2026-05-15] Session Start: Atlas

### V1 Python Pattern (massive_gex_map_service.py)
- Imports: `from __future__ import annotations`, dataclasses, json, logging, pathlib, urllib
- `StrikeExposure` dataclass with slots=True
- `compute_gex(gamma, oi, spot) -> float` = gamma * oi * 100 * spot^2 * 0.01
- `aggregate_chain(rows, spot) -> dict[float, StrikeExposure]`
- `choose_levels(...)` with near-price cap (V3 magnet rule)
- `gamma_flip(strikes, spot)` returns (float, meta_dict) with linear interpolation
- `build_payload(args, api_key, seq)` assembles full payload
- `write_atomic(path, payload)` uses tmp file + os.replace
- `main()` with argparse, supports --once/--loop/--interval/--delayed-ws/--api-key
- Schema: `"deep6.massive_gex_map.v1"`
- Service name: `"massive_gex_map_service"`
- Default output: resolves from WSL or Windows home to `NinjaTrader 8/templates/DEEP6/massive_gex_map.json`
- ENV: `MASSIVE_API_KEY`

### V1 NT8 Pattern (DEEP6MassiveGexMap.cs)
- Namespace: `NinjaTrader.NinjaScript.Indicators.DEEP6`
- Uses `JavaScriptSerializer` from `System.Web.Script.Serialization`
- Timer-based refresh in `State.Historical`
- `lock (sync) { ... }` pattern for thread safety
- `OnRenderTargetChanged()` disposes and recreates all DX resources
- DTOs are flat public classes with auto-props at the bottom of the file
- `ExpandJsonPath()` handles `%USERPROFILE%` and `%USERPROFILE%\\Documents`
- `MatchAsset()` matches by `futures_root` with NQ/MNQ normalization
- `RefreshChart()` uses `ChartControl.Dispatcher.BeginInvoke`
- `DisposeBrush(ref b)` and `DisposeText(ref f)` static helpers

### V1 Test Pattern (test_massive_gex_map_service.py)
- Imports directly from `scripts.massive_gex_map_service`
- Helper `sx(strike, net_gex)` builds `StrikeExposure` objects
- Tests call `choose_levels()` directly with realistic parameters
- Asserts on `levels` list and `selection` dict

### V2 Constraints
- New file: `scripts/massive_gex_map_service_v2.py`
- New NT8 file: `ninjatrader/Custom/Indicators/DEEP6/DEEP6GammaDecisionSurface.cs`
- New test: `tests/test_massive_gex_map_service_v2.py`
- JSON output: `massive_gex_map_v2.json` (different from V1's `massive_gex_map.json`)
- Schema: `deep6.gamma_decision_surface.v2`
- Service name: `gamma_decision_surface_v2`
- NT8 class: `DEEP6GammaDecisionSurface` with DTOs prefixed `Gds*`
- V1 files MUST NOT be touched

### Behavior States
- DEFEND = put_wall (action_hint: HOLD)
- REJECT = call_wall (action_hint: FADE)  
- ATTRACT = hvl (action_hint: TARGET)
- FLIP = gamma_flip (action_hint: WATCH_FOR_FLIP)
- pos_gex above spot = REJECT (action_hint: FADE)
- neg_gex below spot = DEFEND (action_hint: HOLD)
- open_space = OPEN_SPACE (action_hint: ACCELERATION_IF_LOST)

### V2 NT8 Color Palette
- DEFEND: teal Color4(0f, 0.82f, 0.73f, 1f) = #00D1BA
- REJECT: coral Color4(1f, 0.36f, 0.36f, 1f) = #FF5C5C
- ATTRACT: gold Color4(0.99f, 0.78f, 0.20f, 1f) = #FCCB33
- FLIP: platinum Color4(0.92f, 0.94f, 0.98f, 1f) = #EBF0FA
- OPEN_SPACE: blue-gray Color4(0.45f, 0.55f, 0.70f, 0.35f) = #738CB2@35%
- Panel: Color4(0.06f, 0.06f, 0.08f, 0.94f)
- Border: Color4(0.22f, 0.22f, 0.28f, 1f)
- Text: Color4(0.94f, 0.95f, 0.97f, 1f)
- Muted: Color4(0.60f, 0.62f, 0.67f, 1f)
- Halo: Color4(0f, 0f, 0f, 0.85f)
- Fonts: fontPill=Segoe UI Semibold 11pt, fontPillBold=Segoe UI Bold 12pt, fontMono=Consolas 10pt, fontTiny=Segoe UI 9pt
