# NT8 Chart Verification Knowledge Base

## Scope

This skill validates that an indicator or strategy is not just compiled, but visibly and functionally correct on an actual NinjaTrader chart.

It is the acceptance layer after build or repair work.

## Existing Automation Assets

| Purpose | Path |
|---|---|
| Full build/install/screenshot pipeline | `C:\Users\Tea\DEEP6\.claude\skills\nt8-build-verify\scripts\orchestrator.ps1` |
| Manual/UI chart actions | `C:\Users\Tea\DEEP6\ninjatrader\scripts\nt8-ui.ps1` |
| Platform status | `C:\Users\Tea\DEEP6\ninjatrader\scripts\nt8-status.ps1` |
| Setup guide | `C:\Users\Tea\DEEP6\ninjatrader\docs\SETUP.md` |

## Verification Layers

### Layer 1: Presence
Confirm the object is actually on the chart.

Checklist:
1. The indicator or strategy appears in the chart’s active list.
2. It is attached to the expected chart, not a different window.
3. It is visible and not hidden behind template defaults or pane state.

### Layer 2: Placement
Confirm it is rendering in the right place.

Examples:
- overlay indicator belongs on the main price panel
- oscillator belongs in a separate pane
- footprint cells belong inside price bars, not floating or clipped

### Layer 3: Inputs and prerequisites
Confirm the chart has the prerequisites the tool expects.

Common NT8 chart prerequisites:
- correct instrument
- correct timeframe / bar type
- Tick Replay enabled when historical tick-level rendering is required
- live data available when the tool only paints in realtime
- expected properties enabled (for example `ShowFootprintCells = True`)

### Layer 4: Behavioral truth
Confirm the chart output matches the intended logic.

Examples:
- markers appear only on bar close when that is the designed behavior
- GEX levels draw and persist according to the expected refresh behavior
- historical bars are blank only when Tick Replay is off and that is expected

## Common False Negatives

These often look like code bugs but are chart/setup issues:

1. **Indicator compiled but does not appear**
   - not actually added to chart
   - hidden by pane / template state
   - required display property disabled

2. **Historical footprint is blank**
   - expected when Tick Replay is off

3. **Signals not firing yet**
   - warmup period not complete
   - signal only fires on bar close
   - cooldown logic suppresses repeated triggers

4. **Levels do not show**
   - feature toggle off
   - API key missing
   - upstream data unavailable

## Verification Workflow

1. Confirm compile success first.
2. Confirm the indicator/strategy is attached to the intended chart.
3. Confirm chart prerequisites:
   - instrument
   - timeframe
   - bar type
   - Tick Replay if required
   - live data if required
4. Confirm the relevant properties are enabled.
5. Inspect Output Window for runtime exceptions.
6. Take a screenshot or use existing screenshot artifacts.
7. Compare expected rendering/behavior to actual rendering/behavior.
8. If mismatch remains, classify it as one of:
   - setup issue
   - parameter issue
   - runtime/data issue
   - actual code bug

## When to Escalate to Other Skills

- compile/install automation needed → `nt8-build-verify`
- code bug discovered → `nt8-fix`
- strategy runtime/account/ATM issue → `nt8-strategy-operations`
- visual redesign needed → `nt8-visual-design`

## DEEP6-Specific Verification Reminders

- `DEEP6Footprint` historical rendering depends on Tick Replay.
- `DEEP6Footprint` signal markers are suppressed during warmup and may fire only on bar close.
- GEX overlays require the feature to be enabled and the API/auth path to be valid.
- A screenshot is evidence, but Output Window state and chart properties are part of the truth set too.

---

## ⚠️ NT8 UIAutomation Critical Pitfalls (LEARNED THE HARD WAY)

### PITFALL 1: Typing in NT8 opens the Symbol Search, NOT indicator search

**What happens**: When you use `$wsh.SendKeys("text")` with NT8 in focus and the chart as the active window, NT8 intercepts the keystrokes as a **symbol/instrument search** — not the Indicators dialog search box.

**Visual symptom**: A popup appears saying "Press esc to cancel" with a searchable list of stocks, futures, crypto, and indices.

**The mistake**: Calling `SendKeys("Institutional Confluence")` or any text while the NT8 chart panel is the focused control.

**CORRECT way to add an indicator to the chart via UIAutomation**:
```
1. Right-click the chart  (Shift+F10 or mouse right-click at chart coords)
2. Navigate to "Indicators..." menu item — use mouse click, NOT keyboard nav
3. The Indicators dialog opens
4. Inside the dialog: click the search box (must click INSIDE the dialog's search field)
5. Type the indicator name
6. Double-click the result
7. Click OK
```

**NEVER DO**:
```powershell
# WRONG — this types into the chart area, triggering symbol search
$wsh.SendKeys("InstitutionalConfluence")
```

**ALWAYS DO**:
```powershell
# Click the search box coordinates INSIDE the Indicators dialog first
[Mouse]::SetCursorPos($searchBoxX, $searchBoxY) | Out-Null
[Mouse]::mouse_event(LEFTDOWN); [Mouse]::mouse_event(LEFTUP)
Start-Sleep -Milliseconds 300
# THEN type
$wsh.SendKeys("InstitutionalConfluence")
```

**Recovery**: Press Escape twice to close the symbol search popup.

---

### PITFALL 2: The NT8 Indicators Dialog is wider than the screen

**What happens**: When the Indicators dialog opens, it spans the full screen width. The "Available" panel, "Configured" panel, and "Properties" panel are laid out horizontally — the Configured panel and OK/Cancel buttons may be completely off-screen.

**Impact**: You cannot see which indicators are applied, cannot find the Remove button, cannot click OK.

**Correct approach**:
1. Drag the dialog title bar LEFT by ~400-600px using mouse drag automation
2. OR use keyboard: Tab to navigate, Enter to confirm — but test this carefully

**Confirmed dialog coordinates** (on this machine, 1440x900 primary screen):
- Dialog top-left: approximately (208, 402)
- Dialog title bar: y ≈ 425
- Available list search box: approximately (811, 81) — INSIDE the dialog
- Available list items start at: approximately y=570
- `PeakAssetPerformance` category: approximately (757, 445)
- Scrollbar: approximately x=1290

---

### PITFALL 3: AddDataSeries() forces indicator into a sub-panel

**What happens**: When an indicator calls `AddDataSeries()` in its `Configure` state, NT8 may place the indicator in a sub-panel (pane) below the price chart instead of overlaying the price panel.

**Impact**: `Draw.TextFixed()`, `Draw.Text()`, `Draw.ArrowUp()`, and SharpDX `RenderTarget.DrawText()` all draw in the sub-panel (invisible or too small). Only `Draw.HorizontalLine()` always draws on the price panel regardless of which pane the indicator is in.

**Detection**: `Draw.HorizontalLine()` appears on price chart ✅ but all text/shapes don't show ❌

**Fix**: Remove all `AddDataSeries()` calls. Recompile. The user must then **remove and re-add** the indicator from the chart — NT8 does not automatically move it to the price panel on recompile.

**After fix**: Re-add the indicator fresh (via right-click → Indicators dialog), and it will load directly on the price panel.

---

### PITFALL 4: Draw.Rectangle() with barsAgo crashes OnRender

**Error message**: `Error on calling 'OnRender' method on bar N: You are accessing an index with a value that is invalid since it is out-of-range. I.E. accessing a series [barsAgo] with a value of M when there are only K bars on the chart.`

**Root cause**: `Draw.Rectangle(barsAgo=N)` in `OnRender` fails when `N` exceeds the number of bars available in the current chart context.

**Impact**: The entire `OnRender` method throws at that line. Nothing after the crash point executes — no HUD, no text, no arrows. Only previously-persisted draw objects (like `HorizontalLine`) remain visible.

**Fix**: Wrap Draw.Rectangle calls in a guard: `if (CurrentBars[0] < barsAgo + 1) return;`. Or, for safety, remove Draw.Rectangle entirely and use SharpDX `RenderTarget.FillRectangle()` instead.

**Diagnosis**: Check NT8 Output Window / DevAddon log for `Error on calling 'OnRender'` messages.

---

### PITFALL 5: Draw.TextFixed() / Draw.Text() don't work from OnRender on footprint charts

**Context**: Indicator is on a chart using a custom bar type (e.g., DEEP6 Footprint).

**What happens**: `Draw.HorizontalLine()` renders correctly. `Draw.TextFixed()`, `Draw.Text()`, and `Draw.ArrowUp()` are called without error but nothing appears.

**Root cause** (suspected): Custom bar type charts may not support the standard managed draw text objects from `OnRender`. The rendering pipeline for footprint charts differs from standard time/price charts.

**Workaround**: Use SharpDX directly (`RenderTarget.DrawText()`, `RenderTarget.FillRectangle()`) — these work at the GPU/Direct2D level regardless of bar type.

**Confirmed working on footprint charts**: `Draw.HorizontalLine()` ✅, SharpDX direct rendering ✅

---

### PITFALL 6: Indicator on footprint chart may not fire Print() to Output Window

**Context**: Indicator is on a chart using DEEP6 Footprint bar type.

**What happens**: `Print()` calls inside the indicator appear to be silently dropped — no messages appear in the Output Window or DevAddon log, even after DataLoaded.

**Impact**: Cannot use Print() as a diagnostic tool for indicators on footprint charts.

**Alternative diagnostic**: Draw a distinctive `Draw.HorizontalLine()` in `DataLoaded` — if it appears on the chart, `DataLoaded` fired. If it doesn't appear, the indicator failed to load.

---

### CORRECT Way to Add Indicator via Indicators Dialog (step-by-step)

```
NT8 chart → right-click → Indicators... (NOT typing — typing opens symbol search)
            ↓
Indicators dialog opens
            ↓
Dialog may be wider than screen → drag title bar LEFT ~400px
            ↓
Click "Available" list → expand "PeakAssetPerformance" (or relevant category)
            ↓
Double-click "Institutional Confluence" (or indicator name)
            ↓
Properties panel appears on right → set ServerUrl, PollInterval, etc.
            ↓
Click OK → indicator added to chart price panel
```

**NOT**:
- Typing directly — triggers symbol search
- Using `SendKeys` without first clicking the dialog search box
- Pressing Ctrl+I (this is the shortcut but still needs chart focus, not typing)
