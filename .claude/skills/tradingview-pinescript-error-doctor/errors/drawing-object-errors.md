# Drawing Object Errors

Last verified: 2026-05-22

Use this file for labels, lines, boxes, and tables that crash, vanish, drift, or exceed limits.

## Failure Classes

### 1. Max count exceeded

Typical causes:

- no `max_labels_count`, `max_lines_count`, or `max_boxes_count` in `indicator()`
- object creation on every bar without reuse or deletion
- historical backfill creating hundreds of event markers

Mitigation:

```pine
indicator("Example", overlay = true, max_labels_count = 100, max_lines_count = 100, max_boxes_count = 50)
```

Counts only raise the ceiling. They do not solve uncontrolled creation.

### 2. Creating objects every bar without cleanup

Wrong:

```pine
label.new(bar_index, high, "X")
```

Safer singleton pattern:

```pine
var label statusLabel = na
if na(statusLabel)
    statusLabel := label.new(time, high, "Init", xloc = xloc.bar_time)
else
    label.set_x(statusLabel, time)
    label.set_y(statusLabel, high)
    label.set_text(statusLabel, "Live")
```

### 3. Calling setters on `na` IDs

Wrong:

```pine
line.set_y1(anchorLine, high)
```

Guard it:

```pine
if not na(anchorLine)
    line.set_y1(anchorLine, high)
```

### 4. `xloc.bar_index` vs `xloc.bar_time` confusion

- `xloc.bar_index`: anchors against integer bar positions; can drift visually after timeframe changes or resampling.
- `xloc.bar_time`: anchors against actual timestamps; better for candle-locked event markers and MTF-aware objects.

If an object must stay attached to a historical candle, prefer:

```pine
label.new(time, high, "Event", xloc = xloc.bar_time)
```

## Singleton `var` Pattern

Use for one dashboard label, one active box, one session line, or one table.

```pine
var box activeBox = na
if na(activeBox)
    activeBox := box.new(time, high, time, low, xloc = xloc.bar_time)
else
    box.set_left(activeBox, time)
    box.set_right(activeBox, time)
    box.set_top(activeBox, high)
    box.set_bottom(activeBox, low)
```

Without `var`, a new object ID is allocated every bar.

## Array-Based Cleanup Pattern For Event Objects

Use when you genuinely need many objects, but only a capped rolling set.

```pine
var array<label> eventLabels = array.new<label>()
maxEvents = 20

if eventSignal
    lbl = label.new(time, high, "Event", xloc = xloc.bar_time)
    array.push(eventLabels, lbl)

if array.size(eventLabels) > maxEvents
    old = array.shift(eventLabels)
    if not na(old)
        label.delete(old)
```

For conditional deletion across many elements, iterate in reverse when removing multiple items.

## Tables: Different Lifecycle Rules

Tables should almost always be singletons.

```pine
var table debugTable = table.new(position.top_right, 2, 3)
if barstate.islast
    table.cell(debugTable, 0, 0, "State")
    table.cell(debugTable, 1, 0, state)
```

Rules:

- declare with `var`
- create once
- update only on `barstate.islast` unless there is a very specific realtime need
- do not recreate the table every bar

## Fast Diagnosis

1. Check `indicator()` max object counts.
2. Search for `label.new`, `line.new`, `box.new`, `table.new` inside ungated bar logic.
3. Confirm every setter is guarded with `not na(id)`.
4. For candle-locked visuals, replace `bar_index` anchors with `time` + `xloc.bar_time`.
5. If many objects are intentional, add array caps and deletion.
