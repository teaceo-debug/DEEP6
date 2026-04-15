# DEEP6 NT8 Chart — Interaction & ChartTrader Toolbar Spec

**Status:** draft
**Phase target:** post-Phase-17, post-Phase-18 (scoring HUD + tiers), post-GEX extraction
**Surface:** `DEEP6Footprint.cs` `RenderChartTrader()` + `OnChartTraderMouseDown()` (currently lines 724-839, 1215-1272, 1558-1560)
**Scope:** Live feature toggles on the chart panel. Not a menu, not a settings editor.

---

## 1. Toolbar purpose + scope

The ChartTrader toolbar IS:

- A **single row of visible on/off indicators** for runtime-toggleable rendering features.
- A **fat-fingered, click-and-see-it-change** surface for a trader holding a position.
- **≤ 10 buttons.** Past 10, cognitive load exceeds the value of live control — move the toggle into NT8 Properties instead.

The ChartTrader toolbar IS NOT:

- A menu (no nested popovers, no dropdowns, no submenus).
- A settings modal (no numeric inputs, no color pickers, no dialogs).
- A property editor (no fields that need typing). Anything that needs a number or a brush stays in NT8 Properties.
- A trade-entry control. NT8 already owns buy/sell/flatten; DEEP6 does not reinvent them. The name "ChartTrader toolbar" refers to the top-left overlay — it is a **toggle strip**, not an order pad.

Every button must visibly encode its state: fill color, border, and text weight all shift between on and off. A glance at 2 ft away should tell the trader which features are live.

---

## 2. Full button inventory (post-Phase-18, post-GEX-extraction)

Current code (lines 832-838) ships 7 buttons: `CELLS`, `POC`, `VA`, `ANCH`, `ABS`, `EXH`, `L2`. Note `ANCH` already covers the `Levels` concept (Profile Anchor Levels toggle = `ShowProfileAnchors`) and `L2` covers `Walls` (`ShowLiquidityWalls`). There is no GEX button in the indicator today — GEX has been extracted to a separate indicator (`DEEP6GEX`) with its own toggle surface.

Post-Phase-18 target inventory (10 buttons, grouped):

| # | Label | Tooltip | Default | Shortcut | Click | Right-click |
|---|-------|---------|---------|----------|-------|-------------|
| 1 | `CELL` | Footprint bid×ask cell numbers | ON | `C` | Toggle `ShowFootprintCells` | Reset to default |
| 2 | `POC` | Per-bar Point of Control highlight | ON | `P` | Toggle `ShowPoc` | Reset to default |
| 3 | `VA` | Value Area (VAH/VAL) lines | ON | `V` | Toggle `ShowValueArea` | Reset to default |
| 4 | `IMB` | Stacked/single imbalance highlights | ON | `I` | Toggle `ShowImbalances` *(new, Phase 18)* | Reset to default |
| 5 | `ABS` | Absorption markers | ON | `A` | Toggle `ShowAbsorptionMarkers` | Suppress type for session |
| 6 | `EXH` | Exhaustion markers | ON | `E` | Toggle `ShowExhaustionMarkers` | Suppress type for session |
| 7 | `TIER` | T1/T2/T3 entry markers (Phase 18) | ON | `T` | Toggle `ShowTierMarkers` | Cycle: T1 only → T1+T2 → all |
| 8 | `WALL` | L2 liquidity walls | ON | `W` | Toggle `ShowLiquidityWalls` | Reset to default |
| 9 | `LVL` | Profile Anchor Levels (PDH/PDL/PDM/PD POC/VAH/VAL/PW POC/Naked POC) | ON | `L` | Toggle `ShowProfileAnchors` | Cycle: all → prior-day only → naked-only |
| 10 | `HUD` | Scoring HUD badge (Phase 18) | ON | `H` | Cycle compact → expanded → hidden | Reset to compact |

**Is 10 too many?** At the current 56×22px, 10 buttons × 60px pitch = 600px wide. On a 1920px-wide chart that's 31% of width — acceptable. On a 1280px laptop panel it crowds the top-of-chart data series labels. The grouping proposal below resolves this: at narrow widths, collapse to **icon-only 28×22px** (see §10).

**Recommendation:** Ship 10 buttons grouped into 4 visual blocks. Do **not** merge semantically distinct toggles (e.g., ABS+EXH into one "Signals" button) — the trader needs single-purpose live control during a position.

---

## 3. Grouping proposal

Four groups, left → right, ordered by information hierarchy (what you see first = what's most structural):

| Group | Buttons | Rationale |
|-------|---------|-----------|
| **Profile** | `CELL` `POC` `VA` `IMB` | What's inside this bar (microstructure) |
| **Signals** | `ABS` `EXH` `TIER` | Reversal events + entry qualification |
| **Levels** | `WALL` `LVL` | Structural context outside this bar |
| **Score** | `HUD` | Aggregate readout |

**Visual separator:** 12px gap between groups (vs. 4px between buttons within a group), plus a 1px vertical rule in `#3A4450` at the midpoint of the gap. This matches color palette spec 01 neutral-border.

**Group labels?** No. Group labels add a vertical strip of text above the buttons, eat 10-12px of chart height, and do not help a trader who has already learned the layout. The 4-button Profile block, 3-button Signals block, etc. are self-evidently grouped by proximity. Labels become noise after the first session.

---

## 4. Button visual design

Keep current 56×22px — it's already sized to fit a 3-letter label at 10pt without truncation and is borderline-WCAG-AA for touch (44×44 is the full target; chart overlays universally undershoot this and 22px is the NT8 ecosystem norm). Do not shrink below 22px tall.

| State | Fill | Border | Text |
|-------|------|--------|------|
| **On** | `#2E7D4F` (accent green from palette spec 01) | `#3AA36A` 1px | `#F2F4F7` bold |
| **Off** | `#1E2530` (surface-2) | `#2A3340` 1px | `#8892A0` regular |
| **Hover (on)** | `#2E7D4F` | `#6ED39A` 1.5px (brighter) | `#FFFFFF` bold |
| **Hover (off)** | `#262E3A` (surface-2 +1 step) | `#3A4450` 1.5px | `#B8C0CC` regular |
| **Pressed** | state fill darkened 15% | state border | state text | + 1px darker top edge drawn as inset shadow |

**Icon + text vs. text-only:** Stay text-only. Three-letter labels (`CELL`, `POC`, `ABS`) are faster to parse than pictograms for a domain-specific feature set where no universal iconography exists. Icons help when the icon is already well-known (disk = save). None of our 10 features have that.

**Group separator:** 12px gap + 1px vertical rule `#3A4450`, rule drawn at gap-midpoint from `y + 3` to `y + btnH - 3` (inset 3px top/bottom).

**Font:** `Segoe UI Semibold 10pt` via existing `_ctBtnFont` — already the baseline, keep it.

---

## 5. Keyboard shortcuts

All shortcuts require the **chart panel focused** (mouse click on chart first). NT8 routes keyboard input to the focused window only.

| Key | Action |
|-----|--------|
| `C` | Toggle `CELL` |
| `P` | Toggle `POC` |
| `V` | Toggle `VA` |
| `I` | Toggle `IMB` |
| `A` | Toggle `ABS` |
| `E` | Toggle `EXH` |
| `T` | Toggle `TIER` |
| `W` | Toggle `WALL` |
| `L` | Toggle `LVL` |
| `H` | Cycle `HUD` (compact → expanded → hidden → compact) |
| `Shift+R` | Reset all toggles to their `[NinjaScriptProperty]` defaults |
| `?` | Show shortcuts overlay (modal-free — floating card, click anywhere to dismiss) |

**NT8 collision must-check list** (validate before shipping; these are documented NT8 chart-focus hotkeys):

- `F5` — refresh chart (do not override)
- `F11` — fullscreen (do not override)
- `Ctrl+Z / Ctrl+Y` — undo/redo drawings (do not override)
- `Del` — delete selected drawing (do not override)
- `Esc` — close active dialog (do not override)
- Arrow keys — scroll chart (do not override)
- `Ctrl+Shift+P/V/A/E/L/H/T/I/C` — none documented; our plain-letter mapping is clear
- `Ctrl+D` — duplicate workspace (do not override; we don't remap D anyway)

Single-letter hotkeys (no modifier) are safe because NT8 uses modifier combos for its own chart commands. If a future NT8 version introduces a collision, prefix with `Alt+` as a fallback.

Implementation: wire in `OnRenderTargetChanged` next to the existing `MouseDown` hookup, attach `ChartControl.KeyDown += OnChartTraderKeyDown`, unhook on `State.Terminated`.

---

## 6. NT8 Properties organization

Target six properties groups in the `[Display(GroupName=...)]` attribute. Group names are prefixed with a digit so NT8 orders them predictably.

| Group | Properties (source file) |
|-------|--------------------------|
| **`1. Safety`** (Strategy only) | `EnableLiveTrading`, `ApprovedAccountName`, `MaxContractsPerTrade`, `MaxTradesPerSession`, `DailyLossCapDollars`, `RespectNewsBlackouts` (from `DEEP6Strategy.cs` lines 686-740) |
| **`2. Window`** (Strategy only) | `RthStartHour`, `RthStartMinute`, `RthEndHour`, `RthEndMinute`, `MinBarsBetweenEntries` (lines 712-735) |
| **`3. Profile`** (Indicator) | `ShowFootprintCells`, `ShowPoc`, `ShowValueArea`, `ShowImbalances` *(new)*, `ImbalanceRatio`, `CellFontSize`, `CellColumnWidth` (lines 1442-1485) |
| **`4. Signals`** (Indicator + Strategy) | `ShowAbsorptionMarkers`, `ShowExhaustionMarkers`, `AbsorbWickMinPct`, `ExhaustWickMinPct`, `ShowTierMarkers` *(new)*, `MinTierForEntry` *(new)*, `ScoreEntryThreshold` *(new)*, `ConfluenceVaExtremeStrength` (Strategy), `ConfluenceWallProximityTicks` (Strategy) |
| **`5. Levels`** (Indicator) | `ShowProfileAnchors`, `ShowPriorDayLevels`, `ShowNakedPocs`, `ShowCompositeVA`, `NakedPocMaxAgeSessions`, `ShowLiquidityWalls`, `LiquidityWallMin`, `LiquidityWallStaleSec`, `LiquidityMaxPerSide` (lines 1489-1555) |
| **`6. Score`** (Indicator, Phase 18) | `ShowScoreHud`, `ScoreHudPaddingPx`, `HudDetailLevel` *(compact/expanded/hidden)* |
| **`7. Colors`** (Indicator) | All `Brush` properties — `BidCellBrush`, `AskCellBrush`, `CellTextBrush`, `PocBrush`, `VahBrush`, `ValBrush`, `ImbalanceBuyBrush`, `ImbalanceSellBrush`, `AnchorPocBrush`, `AnchorVaBrush`, `AnchorNakedBrush`, `AnchorPwPocBrush`, `AnchorCompositeBrush`, `WallBidBrush`, `WallAskBrush` (lines 1513-1613) |
| **`8. ChartTrader`** (Indicator) | `ShowChartTrader` (lines 1557-1560) |
| **`9. ATM Templates`** (Strategy only) | `AtmTemplateAbsorption`, `AtmTemplateExhaustion`, `AtmTemplateConfluence`, `AtmTemplateDefault` (lines 767-781) |
| **`99. Migration`** (Strategy only) | `UseNewRegistry` (line 787, kept last) |

**Rename:** current group `"5. Liquidity (L2)"` becomes `"5. Levels"` (both walls and anchors live here). Current `"3. Profile Anchors"` merges into `"5. Levels"`. Current `"2. Display"` splits — cell/POC/VA stay in `"3. Profile"`, signal markers move into `"4. Signals"`. Current `"4. Colors"` renumbers to `"7. Colors"`.

Toolbar groups and Properties groups now share labels (`Profile`, `Signals`, `Levels`, `Score`) — muscle memory transfers.

---

## 7. Click behaviors

| Target | Click action |
|--------|-------------|
| Toolbar button | Toggle the bound property; `ForceRefresh()` to repaint. |
| Signal marker (ABS / EXH) | 250ms pulse highlight on the marker (alpha ramp 1.0 → 0.3 → 1.0), print to `Output`: `"[DEEP6] ABS bar=17:32:45 price=20412.75 strength=0.73 delta=-142 variant=PASSIVE"`. |
| Tier marker (T1/T2/T3) | Same 250ms pulse; print full score breakdown: `"[DEEP6] T1 score=82 components={ABS+20, WALL+14, GEX+12, VA+10} multiplier=1.36 decay=1.00 gate=1.00"`. |
| Horizontal level (PDH / PD POC / Naked POC / Wall) | Flash line at 2× stroke width for 250ms; print `"[DEEP6] Level=PDH price=20448.25 age=1d volume=24815"` (Naked POC emits `ageSessions`; Wall emits `size`, `refillCount`, `staleSec`). |
| Footprint cell | Highlight cell border at 2× width for 250ms; print `"[DEEP6] Cell bar=17:32:45 price=20412.75 bid=47 ask=112 delta=+65 imbalance=2.38"`. |
| HUD badge | Cycle `compact → expanded → hidden → compact`. Same as `H` shortcut. |

Hit-testing order is top-down by z-index: HUD → toolbar → entry cards → signal markers → horizontal levels → cells → default (pass through). First hit wins, `e.Handled = true`, rest skipped.

---

## 8. Right-click / context menu

Preserve NT8's native context menu for chart background. Augment only on DEEP6-owned shapes.

| Target | Right-click menu |
|--------|------------------|
| Chart background (not on any DEEP6 shape) | NT8 native menu — **no modification** |
| Toolbar button | `Reset to default` · `Hide button` (persists to a runtime-only hidden-buttons set; reappears on indicator reload) |
| Signal marker (ABS / EXH) | `Inspect` (opens Output with full detail) · `Suppress this type for session` · `Add to notes` (writes to `%USERPROFILE%/Documents/NinjaTrader 8/deep6-notes.txt` with timestamp + bar + price) |
| Tier marker | `Inspect` · `Suppress tier for session` · `Add to notes` |
| Horizontal level | `Copy price to clipboard` · `Hide this level for session` |
| HUD badge | `Compact` · `Expanded` · `Hidden` (direct set, not cycle) |

Menus render via WPF `ContextMenu` attached in the same `OnChartTraderMouseDown` path, extended to handle `MouseButton.Right`. Session-scoped suppression state resets on `SessionChanged` / `State.Realtime` transition.

---

## 9. Hover tooltips

All toolbar buttons show a tooltip after 500ms hover. Implemented as a small SharpDX-rendered card (12px padding, `#0E141C` background, `#2A3340` border, `#F2F4F7` text, Segoe UI 9pt) positioned 4px below the button. No NT8 `ToolTip` control — SharpDX overlay keeps it inside the chart paint loop and avoids WPF interop flicker.

| Button | Tooltip |
|--------|---------|
| `CELL` | "Toggle footprint cells (bid × ask volume per price). Shortcut: C" |
| `POC` | "Toggle per-bar Point of Control. Shortcut: P" |
| `VA` | "Toggle Value Area high/low lines. Shortcut: V" |
| `IMB` | "Toggle stacked/single imbalance highlights. Shortcut: I" |
| `ABS` | "Toggle absorption markers. Right-click: suppress for session. Shortcut: A" |
| `EXH` | "Toggle exhaustion markers. Right-click: suppress for session. Shortcut: E" |
| `TIER` | "Toggle T1/T2/T3 entry markers. Right-click to cycle tier filter. Shortcut: T" |
| `WALL` | "Toggle L2 liquidity walls. Shortcut: W" |
| `LVL` | "Toggle Profile Anchor Levels (PDH/PDL/PDM, PD POC/VAH/VAL, PW POC, Naked POCs). Right-click to cycle. Shortcut: L" |
| `HUD` | "Cycle scoring HUD detail (compact → expanded → hidden). Shortcut: H" |

Tooltip hides on mouse-leave or any mouse-down. Never blocks click.

---

## 10. Failure modes

| Scenario | Behavior |
|----------|----------|
| **Chart panel width < 620px** | Auto-collapse to icon-only mode: buttons shrink to 28×22px, labels drop to 2 chars (`CE`, `PO`, `VA`, `IM`, `AB`, `EX`, `TI`, `WA`, `LV`, `HU`). Tooltip becomes mandatory information channel. Detection: `ChartPanel.W` at `RenderChartTrader()` entry. |
| **Chart panel width < 340px** | Collapse toolbar to a single `≡` button top-left; click opens a vertical stack of full-labeled toggles below it. Dismiss on outside click. |
| **Double-click on button** | Idempotent single-toggle: WPF delivers two `MouseDown` events with ~300ms gap; current handler is already idempotent because each invocation flips the state. Net result of rapid double-click: back to original state. Acceptable (no stuck-state). |
| **Keyboard shortcut fired while chart not focused** | No-op. NT8 routes `KeyDown` only to the focused panel; our handler is attached to `ChartControl`, so unfocused charts never see the event. Document behavior, don't try to grab global hotkeys. |
| **User hides a button via right-click** | Button omitted from next render pass. Preference is runtime-only (not persisted to workspace) — forces a clean state on indicator reload. If we want persistence later, serialize via a `[Browsable(false)] public string HiddenButtonsSerialize` property. |
| **Toolbar overlaps a custom drawing tool placed at top-left** | Toolbar wins z-order (rendered after cells, after entry cards, before tooltips). Trader can toggle off via `ShowChartTrader = false` in Properties if they need the space. |
| **Property group rename causes workspace upgrade noise** | NT8 persists by property name, not `GroupName`. Renaming groups does not break existing workspaces. Only renaming a property itself (which we are not doing) would. |
| **Shortcut conflict at runtime** (hypothetical future NT8 keybind) | Fallback to `Alt+<letter>` via a single `ShortcutsUseAltModifier` property in `8. ChartTrader` group. Default false. |

---

## INTERACTION COMPLETE

**File:** `/Users/teaceo/DEEP6/.planning/design/ninjatrader-chart/04-INTERACTION-TOOLBAR.md`

**Top-3 interaction decisions:**

1. **10 buttons in 4 visual groups (Profile / Signals / Levels / Score), separated by 12px gap + 1px rule — not group labels.** Group labels are noise after session one; proximity is enough. Text-only 3-letter labels beat icons for a domain-specific feature set with no universal iconography.
2. **Single-letter keyboard shortcuts (`C P V I A B E T W L H`) with `Shift+R` reset and `?` overlay.** NT8 has no plain-letter chart hotkeys that collide; single-letter beats modifier combos for speed during a live position. Alt-prefix fallback reserved via a property toggle if a future NT8 release collides.
3. **Toolbar groups mirror Properties groups (Profile, Signals, Levels, Score).** Muscle memory transfers between the live toggle surface and the configuration surface. Rename `"5. Liquidity (L2)"` → `"5. Levels"` and merge `"3. Profile Anchors"` into it; split `"2. Display"` into `"3. Profile"` and `"4. Signals"`. Colors demoted to `"7. Colors"`.
