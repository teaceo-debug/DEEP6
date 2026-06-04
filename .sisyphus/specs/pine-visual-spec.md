# Pine Visual Spec — Standard Deviation Anchor AI

> Every chart object, its visual properties, lifecycle, and object-limit budget.
> Pine is the ONLY drawer. HERMES never draws.

---

## 1. Indicator Declaration

```pinescript
//@version=6
indicator(
    "StdDev Anchor AI",
    overlay       = true,
    max_lines_count  = 10,
    max_boxes_count  = 5,
    max_labels_count = 10
)
```

### Object Budget

| Object Type | Pine Limit | Budget Per Setup | Rationale |
|------------|-----------|-----------------|-----------|
| Lines | 10 | 4 per active setup | anchor leg (1) + -2 level (1) + -2.5 level (1) + -4 level (1) |
| Boxes | 5 | 1 per active setup | zone fill between -2 and -2.5 |
| Labels | 10 | 3 per active setup | anchor start marker (1) + anchor end marker (1) + status label (1) |

With these limits, Pine can hold **2 full setups simultaneously** (8 lines, 2 boxes, 6 labels) with headroom for a transitional third during supersession. When a new setup is created and limits would be exceeded, the oldest invalidated/superseded setup's objects are deleted first.

### Anchoring Rule

**All lines, boxes, and labels use `xloc.bar_time`** (not `bar_index`).

Rationale: `bar_index` shifts as the chart loads more history. `bar_time` is absolute — a level drawn at a specific candle's timestamp stays anchored to that candle permanently, even across reloads and timeframe switches.

---

## 2. Color Palette

### Bullish Active

| Element | Color | Hex | Opacity |
|---------|-------|-----|---------|
| Anchor leg line | Teal | `#00BCD4` | 100% |
| Anchor endpoint markers | Teal | `#00BCD4` | 100% |
| -2 level | Green | `#4CAF50` | 100% |
| -2.5 level | Dark green | `#2E7D32` | 100% |
| -4 level | Deep green | `#1B5E20` | 80% |
| Zone fill (-2 to -2.5) | Green | `#4CAF50` | 15% (`color.new(#4CAF50, 85)`) |
| Status label background | Teal | `#00BCD4` | 20% (`color.new(#00BCD4, 80)`) |
| Status label text | White | `#FFFFFF` | 100% |

### Bearish Active

| Element | Color | Hex | Opacity |
|---------|-------|-----|---------|
| Anchor leg line | Coral | `#FF5722` | 100% |
| Anchor endpoint markers | Coral | `#FF5722` | 100% |
| -2 level | Red | `#F44336` | 100% |
| -2.5 level | Dark red | `#C62828` | 100% |
| -4 level | Deep red | `#B71C1C` | 80% |
| Zone fill (-2 to -2.5) | Red | `#F44336` | 15% (`color.new(#F44336, 85)`) |
| Status label background | Coral | `#FF5722` | 20% (`color.new(#FF5722, 80)`) |
| Status label text | White | `#FFFFFF` | 100% |

### Candidate State (either direction)

| Element | Modification |
|---------|-------------|
| All lines | Same directional color but **dashed** (`line.style_dashed`) |
| Zone fill | Same directional color but opacity reduced to 8% (`color.new(..., 92)`) |
| Status label | Background = `color.new(#9E9E9E, 70)`, text = white |

### Invalidated State (either direction)

| Element | Color | Hex | Opacity |
|---------|-------|-----|---------|
| All lines | Gray | `#757575` | 60% (`color.new(#757575, 40)`) |
| Anchor leg line | Gray | `#757575` | 60% |
| Anchor endpoint markers | Gray | `#757575` | 60% |
| Zone fill | Gray | `#757575` | 6% (`color.new(#757575, 94)`) |
| Status label background | Dark gray | `#616161` | 30% (`color.new(#616161, 70)`) |
| Status label text | Light gray | `#BDBDBD` | 100% |

### Superseded State

Superseded setups are **deleted entirely** — their objects are removed from the chart to free the object budget for the new active setup. No ghost lines remain.

---

## 3. Chart Objects — Detailed Specification

### 3.1 Anchor Leg Line

The diagonal line connecting the manipulation leg's start wick to its end wick.

| Property | Value |
|----------|-------|
| Type | `line.new()` |
| xloc | `xloc.bar_time` |
| x1 | Timestamp of manipulation-leg start bar |
| y1 | Wick extreme of start bar (low for bullish, high for bearish) |
| x2 | Timestamp of manipulation-leg end bar |
| y2 | Wick extreme of end bar (high for bullish, low for bearish) |
| Width | 2 |
| Style — Active | `line.style_solid` |
| Style — Candidate | `line.style_dashed` |
| Style — Invalidated | `line.style_dotted` |
| Color | Per direction/state palette above |

**Bullish example:** Line from bar A's low wick up to bar B's high wick.
**Bearish example:** Line from bar A's high wick down to bar B's low wick.

### 3.2 Anchor Endpoint Markers

Two small labels at the wick extremes of the anchor leg, marking the exact anchor points.

| Property | Value |
|----------|-------|
| Type | `label.new()` |
| xloc | `xloc.bar_time` |
| x | Timestamp of the respective bar |
| y | Wick price (same as anchor leg endpoints) |
| Style — Start point | `label.style_xcross` |
| Style — End point | `label.style_circle` |
| Size | `size.tiny` |
| Color | Per direction/state palette (matches anchor leg) |
| Text | `""` (empty — visual marker only) |
| Textcolor | `na` |

The start point (manipulation origin) uses an X-cross. The end point (displacement origin) uses a circle. This gives directional reading: X → O means "from here to here."

### 3.3 -2 Standard Deviation Level

The primary reversal target.

| Property | Value |
|----------|-------|
| Type | `line.new()` |
| xloc | `xloc.bar_time` |
| x1 | Timestamp of anchor-leg end bar |
| x2 | Timestamp of current bar (extended rightward on each confirmed bar) |
| y1, y2 | Computed -2σ price (same for both — horizontal) |
| Width | 2 |
| Style — Active | `line.style_solid` |
| Style — Candidate | `line.style_dashed` |
| Style — Invalidated | `line.style_dotted` |
| Color | Per direction/state palette |

**Extension behavior:** On each confirmed bar while the setup is active, `line.set_x2()` updates the right edge to the current bar's timestamp. This keeps the level visible and extending rightward.

### 3.4 -2.5 Standard Deviation Level

The deep reversal target / zone boundary.

| Property | Value |
|----------|-------|
| Type | `line.new()` |
| xloc | `xloc.bar_time` |
| x1 | Timestamp of anchor-leg end bar |
| x2 | Timestamp of current bar (extended rightward) |
| y1, y2 | Computed -2.5σ price |
| Width | 1 |
| Style — Active | `line.style_solid` |
| Style — Candidate | `line.style_dashed` |
| Style — Invalidated | `line.style_dotted` |
| Color | Per direction/state palette (darker shade than -2) |

### 3.5 -4 Standard Deviation Level

The extreme/capitulation target. Thinner and more muted — it's a "just in case" reference.

| Property | Value |
|----------|-------|
| Type | `line.new()` |
| xloc | `xloc.bar_time` |
| x1 | Timestamp of anchor-leg end bar |
| x2 | Timestamp of current bar (extended rightward) |
| y1, y2 | Computed -4σ price |
| Width | 1 |
| Style — Active | `line.style_dashed` (always dashed — it's speculative) |
| Style — Candidate | `line.style_dashed` |
| Style — Invalidated | `line.style_dotted` |
| Color | Per direction/state palette (deepest shade, 80% opacity) |

### 3.6 Zone Fill (-2 to -2.5)

The reversal zone — the area where price is expected to react.

| Property | Value |
|----------|-------|
| Type | `box.new()` |
| xloc | `xloc.bar_time` |
| left | Timestamp of anchor-leg end bar |
| right | Timestamp of current bar (extended rightward via `box.set_right()`) |
| top | -2σ price (bullish: higher; bearish: lower — always the -2 value) |
| bottom | -2.5σ price |
| bgcolor | Per direction/state palette (semi-transparent fill) |
| border_color | `color.new(color.gray, 100)` (invisible border — the lines already mark the edges) |
| border_width | 0 |
| border_style | `line.style_solid` |

**Why box instead of fill():** `fill()` requires two plots at global scope. Since levels are dynamic per-setup and can have multiple concurrent setups, `box.new()` is the correct primitive. It also supports `xloc.bar_time` natively.

### 3.7 Status Label

The information label showing direction, confidence, timeframe, and state.

| Property | Value |
|----------|-------|
| Type | `label.new()` |
| xloc | `xloc.bar_time` |
| x | Timestamp of current bar (moves rightward with price) |
| y | -2σ price (sits at the primary reversal level) |
| Style | `label.style_label_left` (points leftward, text extends right of the level) |
| Size | `size.small` |
| Color | Per direction/state palette (label background) |
| Textcolor | Per direction/state palette (label text) |

**Label text content by state:**

| State | Text Format | Example |
|-------|-------------|---------|
| Candidate | `"▲ Candidate\n{tf} │ {conf}%"` | `"▲ Candidate\n5m │ 74%"` |
| Active | `"▲ Bullish -2σ\n{tf} │ {conf}%"` | `"▲ Bullish -2σ\n5m │ 82%"` |
| Active (bearish) | `"▼ Bearish -2σ\n{tf} │ {conf}%"` | `"▼ Bearish -2σ\n5m │ 78%"` |
| Invalidated | `"✕ Invalidated\n{tf} │ {reason}"` | `"✕ Invalidated\n5m │ BOS"` |
| No Valid Leg | `"— No Valid Leg"` | `"— No Valid Leg"` |

Where:
- `{tf}` = timeframe that produced the anchor (e.g., `1m`, `5m`, `15m`)
- `{conf}` = confidence score (integer 0-100, only shown when > 70)
- `{reason}` = short invalidation reason (e.g., `BOS`, `Chop`, `Superseded`)
- `▲` / `▼` = directional arrow (bullish up, bearish down)

**Position update:** On each confirmed bar, `label.set_x()` and `label.set_y()` update to track the current bar timestamp and the current -2σ price (in case levels were recalculated).

---

## 4. Object Lifecycle

### 4.1 State Machine

```
[None] ──(candidate detected)──▶ [Candidate]
                                      │
                          (confidence > 70    (confidence ≤ 70
                           + displacement      or chop detected)
                           confirmed)               │
                                      │              ▼
                                      ▼        [No Valid Leg]
                                  [Active]        (label only,
                                      │           no lines/boxes)
                          ┌───────────┼───────────┐
                    (BOS / price     (new setup    (price reaches
                     invalidates)    supersedes)    -4 or beyond)
                          │           │                │
                          ▼           ▼                ▼
                   [Invalidated]  [Superseded]    [Completed]
                   (gray, stays   (deleted from   (stays visible,
                    on chart)      chart)          marked done)
```

### 4.2 Lifecycle Events

#### Creation (Candidate → objects instantiated)

**Trigger:** Bar closes and the deterministic engine detects a valid manipulation leg candidate.

**Actions:**
1. Create anchor leg line (dashed) from start-wick to end-wick.
2. Create start endpoint marker (xcross) at start-wick.
3. Create end endpoint marker (circle) at end-wick.
4. Compute -2σ, -2.5σ, -4σ prices from anchor range.
5. Create -2 level line (dashed) from anchor-end timestamp to current bar.
6. Create -2.5 level line (dashed) from anchor-end timestamp to current bar.
7. Create -4 level line (dashed) from anchor-end timestamp to current bar.
8. Create zone fill box (reduced opacity) between -2 and -2.5.
9. Create status label: `"▲ Candidate\n{tf} │ {conf}%"`.

**Object count at this point:** 4 lines + 1 box + 3 labels = 8 objects.

#### Confirmation (Candidate → Active)

**Trigger:** Displacement confirmed (structure break + impulsive range expansion) AND confidence > 70.

**Actions:**
1. `line.set_style()` → all level lines from `dashed` to `solid` (except -4 which stays dashed).
2. `line.set_style()` → anchor leg from `dashed` to `solid`.
3. `box.set_bgcolor()` → zone fill opacity from 8% to 15%.
4. `label.set_text()` → status label text to `"▲ Bullish -2σ\n{tf} │ {conf}%"`.
5. `label.set_color()` → status label background to directional color.

**No new objects created** — only property updates on existing objects.

#### Extension (Active — ongoing)

**Trigger:** Each confirmed bar while the setup is active.

**Actions:**
1. `line.set_x2()` → extend -2, -2.5, -4 level lines to current bar timestamp.
2. `box.set_right()` → extend zone fill to current bar timestamp.
3. `label.set_x()` → move status label to current bar timestamp.
4. `label.set_y()` → update to current -2σ price if recalculated.

#### Invalidation (Active → Invalidated)

**Trigger:** Price breaks structure against the setup direction (e.g., bearish BOS against a bullish setup), or HERMES veto received.

**Actions:**
1. `line.set_color()` → all lines to gray palette.
2. `line.set_style()` → all lines to `dotted`.
3. `box.set_bgcolor()` → zone fill to gray at 6% opacity.
4. `label.set_text()` → `"✕ Invalidated\n{tf} │ {reason}"`.
5. `label.set_color()` → gray background.
6. `label.set_textcolor()` → light gray.
7. **Stop extending** — no more `set_x2()` / `set_right()` updates.

**Invalidated objects stay on chart** as historical reference until superseded.

#### Supersession (Any → Superseded / deleted)

**Trigger:** A new setup is created and the object budget would be exceeded.

**Actions:**
1. `line.delete()` → all 4 lines of the oldest invalidated/superseded setup.
2. `box.delete()` → the zone fill box.
3. `label.delete()` → all 3 labels (endpoints + status).
4. Free the budget slots for the new setup.

**Priority for deletion:** superseded first, then invalidated (oldest first), then completed. Never delete the currently active setup.

#### Completion (Active → Completed)

**Trigger:** Price reaches the -2σ level (or touches the zone).

**Actions:**
1. `label.set_text()` → `"✓ Hit -2σ\n{tf} │ {conf}%"`.
2. **Stop extending** — freeze all object positions.
3. Objects remain on chart as historical reference.

#### No Valid Leg

**Trigger:** Engine runs but finds no clean manipulation leg (chop, unclear structure).

**Actions:**
1. If a status-only label exists from a prior "No Valid Leg" state, update its text.
2. Otherwise create a single label: `"— No Valid Leg"` at current bar, near current price.
3. No lines, boxes, or endpoint markers are created.
4. This label is deleted when the next candidate is detected.

**Object count:** 1 label only.

---

## 5. Pine Implementation Notes

### 5.1 Persistent Variables

All object references must use `var` for persistence across bars:

```pinescript
var line   anchorLeg    = na
var label  startMarker  = na
var label  endMarker    = na
var line   level2       = na
var line   level25      = na
var line   level4       = na
var box    zoneFill     = na
var label  statusLabel  = na
var string setupState   = "none"  // "none", "candidate", "active", "invalidated", "completed"
```

### 5.2 Object Cleanup Helper

```pinescript
deleteSetup(leg, start, end, l2, l25, l4, zone, status) =>
    line.delete(leg)
    label.delete(start)
    label.delete(end)
    line.delete(l2)
    line.delete(l25)
    line.delete(l4)
    box.delete(zone)
    label.delete(status)
```

### 5.3 Extension Pattern (on each bar)

```pinescript
if setupState == "active" and barstate.isconfirmed
    currentTime = time
    line.set_x2(level2, currentTime)
    line.set_x2(level25, currentTime)
    line.set_x2(level4, currentTime)
    box.set_right(zoneFill, currentTime)
    label.set_x(statusLabel, currentTime)
```

### 5.4 Color Helper Pattern

```pinescript
getColor(element, direction, state) =>
    if state == "invalidated"
        color.new(#757575, 40)
    else if direction == "bull"
        switch element
            "anchor"  => #00BCD4
            "level2"  => #4CAF50
            "level25" => #2E7D32
            "level4"  => color.new(#1B5E20, 20)
            "zone"    => color.new(#4CAF50, 85)
            => #00BCD4
    else  // bear
        switch element
            "anchor"  => #FF5722
            "level2"  => #F44336
            "level25" => #C62828
            "level4"  => color.new(#B71C1C, 20)
            "zone"    => color.new(#F44336, 85)
            => #FF5722
```

---

## 6. Visual Summary

```
Price
  │
  │    ╳ ─────────────────── ● ═══════════════════════════════
  │    start                 end        Anchor Leg (solid/dashed)
  │         (xcross)         (circle)
  │
  │
  │    ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   -2σ level
  │    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   Zone fill
  │    ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   -2.5σ level
  │
  │
  │    · · · · · · · · · · · · · · · · · · · · · · · · · · · ·   -4σ level
  │
  │                                            ┌─────────────┐
  │                                            │ ▲ Bullish -2σ│
  │                                            │ 5m │ 82%     │
  │                                            └─────────────┘
  │                                               Status Label
  └────────────────────────────────────────────────────────────── Time
```

---

## 7. Excluded Visuals (Do NOT Implement)

The following are explicitly banned from this indicator:

- ATR bands or ATR-based envelopes
- VWAP bands or anchored VWAP overlays
- Regression channels or linear regression lines
- Bollinger Bands or Keltner Channels
- Moving average ribbons or clouds
- Dense diagnostic overlays or debug tables
- Any object drawn by HERMES (HERMES is view-only)
- Any object using `xloc.bar_index` for long-lived objects

---

## 8. Revision History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-05-21 | Initial spec — all objects, lifecycle, colors, limits defined |
