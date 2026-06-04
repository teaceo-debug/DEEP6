# DEEP6 Gamma Decision Surface V2

## TL;DR

> **Quick Summary**: Build `DEEP6GammaDecisionSurface` (V2) as a completely separate, side-by-side NinjaTrader 8 indicator alongside the existing `DEEP6MassiveGexMap` V1. V2 upgrades from a raw level renderer to a behavior-first semantic market map — translating GEX structure into trader-intent states (DEFEND / REJECT / ATTRACT / FLIP / OPEN_SPACE) with right-edge pinned pill labels, lifecycle-aware rendering, and no bulky HUD.
>
> **Files created (new — V1 untouched)**:
> - `scripts/massive_gex_map_service_v2.py` — Python sidecar V2
> - `ninjatrader/Custom/Indicators/DEEP6/DEEP6GammaDecisionSurface.cs` — NT8 renderer V2
> - `tests/test_massive_gex_map_service_v2.py` — test suite V2
>
> **Hard constraint**: V1 (`DEEP6MassiveGexMap.cs`, `massive_gex_map_service.py`, `massive_gex_map.json`) must remain 100% untouched.

---

## Hard Install Constraint

- Do NOT modify `DEEP6MassiveGexMap.cs`
- Do NOT modify `massive_gex_map_service.py`
- Do NOT modify `massive_gex_map.json`
- V2 uses class name: `DEEP6GammaDecisionSurface`
- V2 uses file: `DEEP6GammaDecisionSurface.cs`
- V2 uses JSON path: `massive_gex_map_v2.json`
- V2 uses schema: `deep6.gamma_decision_surface.v2`
- V2 namespace stays in `NinjaTrader.NinjaScript.Indicators.DEEP6`

---

## TODOs

### Phase A — Python Sidecar V2

- [x] **A1**: Create `scripts/massive_gex_map_service_v2.py` — data fetch stage
  - Copy and adapt V1 fetch infrastructure (http_json, fetch_yahoo_price, fetch_option_chain, websocket_probe)
  - New default output path: `massive_gex_map_v2.json`
  - New env var: `MASSIVE_API_KEY` (same key, different output)
  - New schema constant: `deep6.gamma_decision_surface.v2`
  - New service name: `gamma_decision_surface_v2`

- [x] **A2**: Add `StrikeExposure` dataclass + `aggregate_chain()` to V2 sidecar
  - Identical computation to V1 `compute_gex()` + `aggregate_chain()`
  - Keep: `gamma * open_interest * 100 * spot^2 * 0.01`
  - Keep V3 near-price `max_futures_distance_points` cap logic

- [x] **A3**: Add structural detection layer to V2 sidecar
  - `detect_gamma_flip(strikes, spot)` — linear interpolation zero-cross with confidence score
  - `detect_call_wall(strikes, spot)` — max positive GEX at or above spot
  - `detect_put_wall(strikes, spot)` — max negative GEX at or below spot
  - `detect_hvl(strikes)` — highest absolute GEX among near candidates
  - `detect_secondary_nodes(strikes, used_strikes, max_nodes)` — remaining by abs GEX rank
  - `detect_open_space_lanes(selected_levels, futures_spot)` — sparse gaps > 80pts between consecutive major levels

- [x] **A4**: Add behavior translation layer to V2 sidecar
  - `translate_behavior(structural_source, role, spot, futures_spot) -> BehaviorState`
  - Mapping rules:
    - `put_wall` → `DEFEND` (action_hint: `HOLD`)
    - `call_wall` → `REJECT` (action_hint: `FADE`)
    - `hvl` → `ATTRACT` (action_hint: `TARGET`)
    - `gamma_flip` → `FLIP` (action_hint: `WATCH_FOR_FLIP`)
    - `pos_gex_*` above spot → `REJECT` (action_hint: `FADE`)
    - `neg_gex_*` below spot → `DEFEND` (action_hint: `HOLD`)
    - `open_space` → `OPEN_SPACE` (action_hint: `ACCELERATION_IF_LOST`)

- [x] **A5**: Add ranking + confidence scoring to V2 sidecar
  - `score_level_confidence(sx, distance_pts, futures_spot, flip_distance) -> float`
  - Score factors: abs_gex weight 40%, distance_proximity weight 35%, oi_concentration 15%, flip_proximity 10%
  - `assign_tier(confidence_score) -> str` — T1 ≥ 0.75, T2 ≥ 0.50, T3 otherwise
  - `rank_levels(levels) -> list` — sort by confidence_score descending

- [x] **A6**: Add confluence zone detection to V2 sidecar
  - `detect_confluence_zones(levels, futures_spot, merge_window_pts=25) -> list[ConfluenceZone]`
  - If two or more levels are within `merge_window_pts` futures-points of each other, merge
  - Output zone: `zone_high`, `zone_low`, `dominant_behavior`, `dominant_source`, `confidence_score`, `tier`, `member_level_ids`, `action_hint`, `label`
  - Labels: `DEFEND CLUSTER`, `REJECT CLUSTER`, `CONFLUENCE FLIP`, `ATTRACT ZONE`

- [x] **A7**: Add real freshness model to V2 sidecar
  - Track and emit per-asset `freshness` block:
    - `payload_age_seconds`
    - `chain_snapshot_age_seconds`
    - `spot_age_seconds`
    - `futures_spot_age_seconds`
    - `websocket_age_seconds`
    - `compute_duration_ms`
    - `last_successful_refresh_utc`
    - `health_state` — `healthy | degraded | stale | very_stale`
  - Cache last-good payload; on fetch failure, re-emit with `health_state=degraded`

- [x] **A8**: Add explainability metadata to every V2 level
  - Each level must carry:
    - `behavior_state` — DEFEND / REJECT / ATTRACT / FLIP / OPEN_SPACE
    - `structural_source` — put_wall / call_wall / hvl / gamma_flip / pos_gex / neg_gex / open_space
    - `confidence_score` — float 0.0–1.0
    - `selected_because` — human-readable string
    - `distance_points` — float, distance from futures spot (+ above, - below)
    - `tier` — T1 / T2 / T3
    - `lifecycle_state` — always `active` on first emit (renderer upgrades via age)
    - `action_hint` — HOLD / FADE / TARGET / WATCH_FOR_FLIP / ACCELERATION_IF_LOST
    - `confluence_group` — string id if merged, null otherwise
    - `acceleration_context` — description if open_space lane

- [x] **A9**: Add `build_payload_v2()` and `write_atomic()` + `main()` to V2 sidecar
  - Assemble complete V2 payload with assets, levels, confluence_zones, lanes, regime_summary, freshness
  - Write atomically to `massive_gex_map_v2.json`
  - Support `--once`, `--loop`, `--interval`, `--delayed-ws`, `--api-key` CLI args same as V1
  - New default output path separate from V1

---

### Phase B — NT8 Renderer V2

- [x] **B1**: Create `ninjatrader/Custom/Indicators/DEEP6/DEEP6GammaDecisionSurface.cs` — skeleton + state
  - Class name: `DEEP6GammaDecisionSurface`
  - Display name: `DEEP6 Gamma Decision Surface`
  - Description: `DEEP6 Gamma Decision Surface V2 — behavior-first semantic GEX map. Levels communicate trader intent: DEFEND / REJECT / ATTRACT / FLIP / OPEN SPACE. No API key in NinjaTrader.`
  - Namespace: `NinjaTrader.NinjaScript.Indicators.DEEP6`
  - New JSON default: `%USERPROFILE%\Documents\NinjaTrader 8\templates\DEEP6\massive_gex_map_v2.json`
  - All V1 DTOs renamed: `GdsPayload`, `GdsAsset`, `GdsLevel`, `GdsLane`, `GdsConfluenceZone`, `GdsFreshness`, `GdsMapping`, `GdsWebSocket`, `GdsChain`, `GdsSelection`, `GdsRegime`
  - Timer-driven refresh at `RefreshSeconds` (default 2)
  - Lock pattern identical to V1

- [x] **B2**: Add DX brush palette for all 5 behavior states
  - DEFEND: `dxDefend` = teal `new Color4(0f, 0.82f, 0.73f, 1f)` (#00D1BA)
  - DEFEND fill: `dxDefendFill` = teal @ 10% alpha
  - REJECT: `dxReject` = coral-red `new Color4(1f, 0.36f, 0.36f, 1f)` (#FF5C5C)
  - REJECT fill: `dxRejectFill` = red @ 10% alpha
  - ATTRACT: `dxAttract` = gold `new Color4(0.99f, 0.78f, 0.20f, 1f)` (#FCCB33)
  - ATTRACT fill: `dxAttractFill` = gold @ 8% alpha
  - FLIP: `dxFlip` = platinum-white `new Color4(0.92f, 0.94f, 0.98f, 1f)` (#EBF0FA)
  - FLIP fill: `dxFlipFill` = white @ 6% alpha
  - OPEN_SPACE: `dxLane` = blue-gray `new Color4(0.45f, 0.55f, 0.70f, 0.35f)` (#738CB2 @ 35%)
  - Panel: `dxPanel` = near-black `new Color4(0.06f, 0.06f, 0.08f, 0.94f)`
  - Border: `dxBorder` = dim gray `new Color4(0.22f, 0.22f, 0.28f, 1f)`
  - Text primary: `dxText` = near-white `new Color4(0.94f, 0.95f, 0.97f, 1f)`
  - Text muted: `dxMuted` = medium gray `new Color4(0.60f, 0.62f, 0.67f, 1f)`
  - Text halo: `dxHalo` = black @ 85% `new Color4(0f, 0f, 0f, 0.85f)`
  - Stale dim: `dxStaleDim` — 35% alpha overlay for degraded levels
  - Create fonts: `fontPill` = Segoe UI Semibold 11pt, `fontPillBold` = Segoe UI Bold 12pt, `fontMono` = Consolas 10pt, `fontTiny` = Segoe UI 9pt

- [x] **B3**: Implement `DrawStructuralField()` — Layer 2 zone fills
  - For each active level in the rendered set, draw a translucent horizontal band
  - DEFEND: band 8pt tall, teal fill, centered on level price
  - REJECT: band 8pt tall, red fill, centered on level price
  - ATTRACT: band 12pt tall, gold fill, softer + wider
  - FLIP: band 4pt tall, platinum fill, very tight
  - T1 levels: zone fill opacity × 1.0, T2 × 0.6, T3 × 0.35
  - Draw bands before lines (layer underneath)

- [x] **B4**: Implement `DrawPrimaryLines()` — Layer 3 level lines
  - For each level, draw full-width horizontal line across ChartPanel
  - DEFEND: 2.2px solid teal, `dxDefend`
  - REJECT: 2.5px solid coral, `dxReject`
  - ATTRACT: 1.8px dashed gold, `dxAttract` (use custom dash: [6f, 3f])
  - FLIP: 2.8px solid platinum, `dxFlip`
  - Secondary nodes (T2/T3): 1.2px, same color family but 55% opacity
  - Historical/faded: dashed + 30% opacity
  - Lifecycle state `flipped`: switch to dashed + reduce opacity 40%
  - Pinned levels: stroke weight +0.4px bonus

- [x] **B5**: Implement `DrawOpenSpaceLanes()` — Layer 3 corridors
  - For each open-space lane in `asset.lanes`, draw a subtle corridor rectangle
  - Color: `dxLane` (blue-gray @ 35%)
  - Width: full chart panel width
  - Height: lane.end_price to lane.start_price in pixel space
  - No strong border — just the translucent fill
  - Draw before lines so lines overlay on top

- [x] **B6**: Implement `DrawSemanticPills()` — Layer 4 right-edge labels
  - Pinned to right edge: `pillRight = ChartPanel.X + ChartPanel.W - 8f`
  - Pill width: 220px
  - Pill height: 20px
  - For each rendered level, sorted by price descending:
    - Pill background: `dxPanel` rounded-ish rect (use simple FillRectangle)
    - Left edge accent: 3px wide strip in behavior color
    - Label row 1 (bold): behavior state + structural source — e.g. `REJECT  CALL WALL`
    - Label row 2 (mono): distance + tier — e.g. `+42  T1`
    - Halo text: draw text offset ±1px in `dxHalo` then main pass in color
  - Collision management: if two pills would overlap vertically (< 22px apart), shift lower one down
  - Offscreen levels (above/below visible range): stack in top/bottom margin with `▲` / `▼` prefix

- [x] **B7**: Implement `DrawConfluenceZoneLabels()`
  - For each confluence zone in `asset.confluence_zones`:
    - Draw a bracket or accent line at zone_high and zone_low
    - Single merged pill label for the zone: e.g. `DEFEND CLUSTER  T1`
    - Zone price range shown as: `21,432–21,448`
    - Use dominant behavior color for the bracket marks

- [x] **B8**: Implement `DrawRegimeStrip()` — tiny optional summary
  - If `ShowRegimeStrip = true` (default true), draw one compact line at top-right:
    - Background: `dxPanel` @ 90% opacity, very narrow (18px tall)
    - Content: `{regime} | {flip_label} | {magnet_label}` e.g. `POS GEX | FLIP +6 | MAGNET -18`
    - Font: `fontTiny`, color `dxMuted`
    - Width: fit to content, max 320px, right-aligned
  - This strip must be visually subordinate — it is the last thing a trader looks at, not the first

- [x] **B9**: Implement distance badge updates on every timer tick
  - On each `ReadSnapshot()` cycle, recompute `distance_points` = `level.price - asset.futures_spot`
  - Store updated distances in a dictionary keyed by level id
  - Use these live distances in pill labels — do NOT rely on stale JSON distance field

- [x] **B10**: Wire `OnStateChange`, `OnRenderTargetChanged`, `OnRender` and all NT8 lifecycle hooks
  - `SetDefaults`: all property defaults
  - `Historical`: start refresh timer
  - `Terminated`: dispose timer + all DX resources
  - `OnRenderTargetChanged`: dispose + recreate all brushes and fonts
  - `OnRender`: call DrawStructuralField, DrawOpenSpaceLanes, DrawPrimaryLines, DrawSemanticPills, DrawConfluenceZoneLabels, DrawRegimeStrip in that order
  - `OnBarUpdate`: empty body (Calculate.OnEachTick but no bar logic needed)

- [x] **B11**: Add all NinjaScriptProperty definitions
  - Group 1 — Data: `JsonFilePath`, `RefreshSeconds`, `StaleSeconds`, `VeryStaleSeconds`, `MaxRenderedLevels`
  - Group 2 — Display: `ShowStructuralField`, `ShowOpenSpaceLanes`, `ShowConfluenceZones`, `ShowRegimeStrip`, `ShowOffscreenLabels`
  - Group 3 — Behavior Colors: `DefendBrush`, `RejectBrush`, `AttractBrush`, `FlipBrush` (WPF Brush properties with XmlIgnore + Serialize pattern)
  - Serialization helpers for all color properties

---

### Phase C — Tests V2

- [x] **C1**: Create `tests/test_massive_gex_map_service_v2.py` — behavior translation tests
  - Test: `put_wall` always maps to `DEFEND`
  - Test: `call_wall` always maps to `REJECT`
  - Test: `hvl` always maps to `ATTRACT`
  - Test: `gamma_flip` always maps to `FLIP`
  - Test: `pos_gex` node above spot maps to `REJECT`
  - Test: `neg_gex` node below spot maps to `DEFEND`

- [x] **C2**: Add V2 selectivity tests
  - Test: no far-away levels forced (max_futures_distance_points cap honored)
  - Test: empty output when no near actionable structure
  - Test: max rendered levels cap respected (T1 always wins over T3)

- [x] **C3**: Add confluence detection tests
  - Test: two levels within 25pts merged into single confluence zone
  - Test: confluence zone label is correct for dominant behavior
  - Test: member_level_ids are correct

- [x] **C4**: Add open-space lane detection tests
  - Test: lane detected between two levels > 80pts apart
  - Test: no lane emitted when levels are close
  - Test: lane confidence and label are correct

- [x] **C5**: Add freshness model tests
  - Test: health_state = `healthy` when fresh
  - Test: health_state = `stale` when age > StaleSeconds
  - Test: health_state = `very_stale` when age > VeryStaleSeconds
  - Test: last-good payload preserved on fetch failure

- [x] **C6**: Add confidence scoring + tier tests
  - Test: high abs_gex + near price = T1
  - Test: low abs_gex + far price = T3
  - Test: ranking is stable (same input = same order)

---

## Final Verification Wave

- [x] **F1**: V1 is completely untouched — `DEEP6MassiveGexMap.cs` unchanged, `massive_gex_map_service.py` unchanged, `massive_gex_map.json` path unchanged
- [x] **F2**: V2 files exist and compile cleanly — `DEEP6GammaDecisionSurface.cs` has zero LSP errors, `massive_gex_map_service_v2.py` imports cleanly
- [x] **F3**: All V2 tests pass — `pytest tests/test_massive_gex_map_service_v2.py -v` exits 0
- [x] **F4**: V2 sidecar runs cleanly — `python scripts/massive_gex_map_service_v2.py --once --ws-probe-seconds 0` produces valid `massive_gex_map_v2.json` (or fails gracefully with missing API key)
