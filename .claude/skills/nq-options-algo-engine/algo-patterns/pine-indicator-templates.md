# Pine Script Indicator Templates

Reusable Pine Script patterns for displaying options-derived data on TradingView charts.
These patterns receive data from the DEEP6 Python backend and render it as overlays,
tables, and alert conditions.

Theory for GEX regimes, walls, and flow states lives in `options-bias-engine/`.
Visual design conventions (colors, fonts, spacing) reference `nt8-visual-design/knowledge.md`.
MCP operations for injecting and compiling these scripts: `tradingview-mcp-trading-operator/knowledge.md`.

---

## Data Injection Architecture

The Python backend cannot push data directly into Pine Script. Two patterns work:

**Pattern A: Input-based injection (recommended for levels)**
The backend writes levels to a JSON file or API endpoint. A companion Pine script reads
them via `input.float()` parameters that the DEEP6 dashboard updates via TradingView MCP
(`indicator_set_inputs`). Fast, no security() overhead.

**Pattern B: Symbol-based injection (for time-series data)**
The backend publishes a synthetic symbol (e.g., via a data vendor or custom feed).
Pine reads it via `request.security()`. Adds latency and complexity — avoid unless
you need historical bar-by-bar data.

For DEEP6, Pattern A is the standard. The Python backend updates Pine inputs via MCP
whenever FlashAlpha data refreshes (every 30-60 seconds).

---

## Template 1: GEX Level Overlay

Draws horizontal lines for gamma flip, call wall, put wall, and 0DTE magnet.
Inputs are updated by the Python backend via `indicator_set_inputs`.

```pine
//@version=5
indicator("DEEP6 GEX Levels", overlay=true, max_lines_count=20, max_labels_count=20)

// ─── Inputs (updated by Python backend via MCP indicator_set_inputs) ───────
i_gamma_flip   = input.float(0.0,  "Gamma Flip",   group="GEX Levels")
i_call_wall    = input.float(0.0,  "Call Wall",    group="GEX Levels")
i_put_wall     = input.float(0.0,  "Put Wall",     group="GEX Levels")
i_dte_magnet   = input.float(0.0,  "0DTE Magnet",  group="GEX Levels")
i_show_magnet  = input.bool(true,  "Show 0DTE Magnet", group="GEX Levels")
i_regime       = input.string("A", "Current Regime (A-G)", group="GEX Levels")

// ─── Color palette (DEEP6 institutional palette) ────────────────────────────
C_FLIP         = color.new(#FF6B35, 0)    // Orange — regime boundary
C_CALL_WALL    = color.new(#E63946, 0)    // Red — resistance
C_PUT_WALL     = color.new(#2DC653, 0)    // Green — support
C_MAGNET       = color.new(#A8DADC, 80)   // Light blue, semi-transparent
C_LABEL_BG     = color.new(#1A1A2E, 85)
C_LABEL_TEXT   = color.new(#FFFFFF, 0)

// ─── Line style by regime ────────────────────────────────────────────────────
// Solid lines in positive gamma (A/B/C), dashed in negative (D/E)
_is_neg_gamma  = i_regime == "D" or i_regime == "E"
_line_style    = _is_neg_gamma ? line.style_dashed : line.style_solid
_line_width    = _is_neg_gamma ? 1 : 2

// ─── Draw levels (only on last bar to avoid line proliferation) ──────────────
if barstate.islast
    // Gamma flip
    if i_gamma_flip > 0
        line.new(bar_index - 50, i_gamma_flip, bar_index + 20, i_gamma_flip,
                 color=C_FLIP, style=line.style_solid, width=2, extend=extend.right)
        label.new(bar_index + 5, i_gamma_flip, "GEX FLIP " + str.tostring(i_gamma_flip, "#.##"),
                  color=C_LABEL_BG, textcolor=C_FLIP, style=label.style_label_left, size=size.small)

    // Call wall
    if i_call_wall > 0
        line.new(bar_index - 50, i_call_wall, bar_index + 20, i_call_wall,
                 color=C_CALL_WALL, style=_line_style, width=_line_width, extend=extend.right)
        label.new(bar_index + 5, i_call_wall, "CALL WALL " + str.tostring(i_call_wall, "#.##"),
                  color=C_LABEL_BG, textcolor=C_CALL_WALL, style=label.style_label_left, size=size.small)

    // Put wall
    if i_put_wall > 0
        line.new(bar_index - 50, i_put_wall, bar_index + 20, i_put_wall,
                 color=C_PUT_WALL, style=_line_style, width=_line_width, extend=extend.right)
        label.new(bar_index + 5, i_put_wall, "PUT WALL " + str.tostring(i_put_wall, "#.##"),
                  color=C_LABEL_BG, textcolor=C_PUT_WALL, style=label.style_label_left, size=size.small)

    // 0DTE magnet (only show if enabled and non-zero)
    if i_show_magnet and i_dte_magnet > 0
        line.new(bar_index - 30, i_dte_magnet, bar_index + 20, i_dte_magnet,
                 color=C_MAGNET, style=line.style_dotted, width=1, extend=extend.right)
        label.new(bar_index + 5, i_dte_magnet, "0DTE " + str.tostring(i_dte_magnet, "#.##"),
                  color=C_LABEL_BG, textcolor=C_MAGNET, style=label.style_label_left, size=size.tiny)
```

---

## Template 2: Regime Badge Table

Displays current regime (A-G) with color coding and key stats in a corner table.

```pine
//@version=5
indicator("DEEP6 Regime Badge", overlay=true, max_tables_count=1)

// ─── Inputs ──────────────────────────────────────────────────────────────────
i_regime        = input.string("A",    "Regime",          group="Regime")
i_regime_min    = input.float(0.0,     "Regime Duration (min)", group="Regime")
i_bias_score    = input.float(0.0,     "Bias Score (-100 to 100)", group="Regime")
i_conviction    = input.string("HIGH", "Conviction",      group="Regime")
i_table_pos     = input.string("top_right", "Table Position",
                               options=["top_right","top_left","bottom_right","bottom_left"],
                               group="Display")

// ─── Regime color map ────────────────────────────────────────────────────────
_regime_color(r) =>
    switch r
        "A" => color.new(#4CAF50, 0)   // Green — positive gamma, range
        "B" => color.new(#FF9800, 0)   // Orange — at call wall
        "C" => color.new(#2196F3, 0)   // Blue — at put wall (best long)
        "D" => color.new(#FFEB3B, 0)   // Yellow — negative gamma above flip
        "E" => color.new(#F44336, 0)   // Red — negative gamma below flip
        "F" => color.new(#9C27B0, 0)   // Purple — pin regime
        "G" => color.new(#607D8B, 0)   // Grey — pre-event
        => color.new(#607D8B, 0)

_regime_desc(r) =>
    switch r
        "A" => "RANGE"
        "B" => "CALL WALL"
        "C" => "PUT WALL"
        "D" => "NEG-GAMMA ↑"
        "E" => "NEG-GAMMA ↓"
        "F" => "PIN"
        "G" => "PRE-EVENT"
        => "UNKNOWN"

_conviction_color(c) =>
    switch c
        "MAX"    => color.new(#00E676, 0)
        "HIGH"   => color.new(#69F0AE, 0)
        "MEDIUM" => color.new(#FFD740, 0)
        "LOW"    => color.new(#FF6D00, 0)
        => color.new(#607D8B, 0)

_bias_color(score) =>
    score > 50  ? color.new(#00E676, 0) :
     score > 20  ? color.new(#69F0AE, 0) :
     score > -20 ? color.new(#ECEFF1, 0) :
     score > -50 ? color.new(#FF8A65, 0) :
                   color.new(#F44336, 0)

// ─── Table (varip: persists across bars, only redraws on change) ─────────────
var table regime_table = table.new(
    position = i_table_pos == "top_right"     ? position.top_right :
               i_table_pos == "top_left"      ? position.top_left :
               i_table_pos == "bottom_right"  ? position.bottom_right :
                                                position.bottom_left,
    columns = 2, rows = 5,
    bgcolor = color.new(#0D0D1A, 10),
    border_color = color.new(#333355, 0),
    border_width = 1,
    frame_color = color.new(#333355, 0),
    frame_width = 1
)

if barstate.islast
    C_REGIME = _regime_color(i_regime)
    C_CONV   = _conviction_color(i_conviction)
    C_BIAS   = _bias_color(i_bias_score)
    C_HEADER = color.new(#1A1A2E, 0)
    C_TEXT   = color.new(#ECEFF1, 0)
    C_DIM    = color.new(#90A4AE, 0)

    // Header
    table.cell(regime_table, 0, 0, "REGIME", text_color=C_DIM, bgcolor=C_HEADER, text_size=size.tiny)
    table.cell(regime_table, 1, 0, i_regime + " · " + _regime_desc(i_regime),
               text_color=C_REGIME, bgcolor=C_HEADER, text_size=size.small)

    // Duration
    table.cell(regime_table, 0, 1, "DURATION", text_color=C_DIM, bgcolor=C_HEADER, text_size=size.tiny)
    table.cell(regime_table, 1, 1, str.tostring(math.round(i_regime_min, 1)) + " min",
               text_color=C_TEXT, bgcolor=C_HEADER, text_size=size.small)

    // Bias score
    table.cell(regime_table, 0, 2, "BIAS", text_color=C_DIM, bgcolor=C_HEADER, text_size=size.tiny)
    _bias_str = (i_bias_score > 0 ? "+" : "") + str.tostring(math.round(i_bias_score, 1))
    table.cell(regime_table, 1, 2, _bias_str, text_color=C_BIAS, bgcolor=C_HEADER, text_size=size.small)

    // Conviction
    table.cell(regime_table, 0, 3, "CONVICTION", text_color=C_DIM, bgcolor=C_HEADER, text_size=size.tiny)
    table.cell(regime_table, 1, 3, i_conviction, text_color=C_CONV, bgcolor=C_HEADER, text_size=size.small)

    // Timestamp
    table.cell(regime_table, 0, 4, "UPDATED", text_color=C_DIM, bgcolor=C_HEADER, text_size=size.tiny)
    table.cell(regime_table, 1, 4, str.format("{0,time,HH:mm:ss}", timenow),
               text_color=C_DIM, bgcolor=C_HEADER, text_size=size.tiny)
```

---

## Template 3: Flow State Panel

Displays institutional flow classification with per-source breakdown.

```pine
//@version=5
indicator("DEEP6 Flow State", overlay=false, max_tables_count=1)

// ─── Inputs (updated by Python backend) ──────────────────────────────────────
i_flow_state    = input.string("DEAD",  "Flow State",
                               options=["AGGRESSIVE_BULLISH","AGGRESSIVE_BEARISH",
                                        "ACCUMULATION","DISTRIBUTION","HEDGING","DEAD"],
                               group="Flow")
i_flow_intensity = input.float(0.0,    "Flow Intensity (0-1)", group="Flow")
i_net_prem_5m   = input.float(0.0,     "Net Premium 5m ($M)",  group="Flow")
i_net_prem_1h   = input.float(0.0,     "Net Premium 1h ($M)",  group="Flow")
i_sweep_bull    = input.int(0,          "Bullish Sweeps (15m)", group="Flow")
i_sweep_bear    = input.int(0,          "Bearish Sweeps (15m)", group="Flow")
i_dark_dir      = input.float(0.0,     "Dark Pool Direction (-1 to 1)", group="Flow")

_flow_color(s) =>
    switch s
        "AGGRESSIVE_BULLISH" => color.new(#00E676, 0)
        "AGGRESSIVE_BEARISH" => color.new(#F44336, 0)
        "ACCUMULATION"       => color.new(#40C4FF, 0)
        "DISTRIBUTION"       => color.new(#FF6D00, 0)
        "HEDGING"            => color.new(#FFD740, 0)
        "DEAD"               => color.new(#546E7A, 0)
        => color.new(#546E7A, 0)

_prem_str(v) =>
    prefix = v >= 0 ? "+" : ""
    prefix + str.tostring(math.round(v, 1)) + "M"

_dir_bar(v) =>
    // Simple ASCII direction bar: ████░░░░ style
    pct = math.round((v + 1.0) / 2.0 * 10)
    filled = math.max(0, math.min(10, pct))
    str.repeat("█", filled) + str.repeat("░", 10 - filled)

var table flow_table = table.new(
    position.top_left, columns=2, rows=7,
    bgcolor=color.new(#0D0D1A, 10),
    border_color=color.new(#333355, 0), border_width=1
)

if barstate.islast
    C_STATE = _flow_color(i_flow_state)
    C_DIM   = color.new(#90A4AE, 0)
    C_TEXT  = color.new(#ECEFF1, 0)
    C_BG    = color.new(#1A1A2E, 0)
    C_POS   = color.new(#69F0AE, 0)
    C_NEG   = color.new(#FF8A65, 0)

    table.cell(flow_table, 0, 0, "FLOW STATE", text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
    table.cell(flow_table, 1, 0, i_flow_state, text_color=C_STATE, bgcolor=C_BG, text_size=size.small)

    table.cell(flow_table, 0, 1, "INTENSITY", text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
    table.cell(flow_table, 1, 1, str.tostring(math.round(i_flow_intensity * 100)) + "%",
               text_color=C_TEXT, bgcolor=C_BG, text_size=size.small)

    table.cell(flow_table, 0, 2, "PREM 5m", text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
    table.cell(flow_table, 1, 2, _prem_str(i_net_prem_5m),
               text_color=i_net_prem_5m >= 0 ? C_POS : C_NEG, bgcolor=C_BG, text_size=size.small)

    table.cell(flow_table, 0, 3, "PREM 1h", text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
    table.cell(flow_table, 1, 3, _prem_str(i_net_prem_1h),
               text_color=i_net_prem_1h >= 0 ? C_POS : C_NEG, bgcolor=C_BG, text_size=size.small)

    table.cell(flow_table, 0, 4, "SWEEPS ↑/↓", text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
    table.cell(flow_table, 1, 4,
               str.tostring(i_sweep_bull) + " / " + str.tostring(i_sweep_bear),
               text_color=C_TEXT, bgcolor=C_BG, text_size=size.small)

    table.cell(flow_table, 0, 5, "DARK POOL", text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
    table.cell(flow_table, 1, 5, _dir_bar(i_dark_dir),
               text_color=i_dark_dir >= 0 ? C_POS : C_NEG, bgcolor=C_BG, text_size=size.tiny)

    table.cell(flow_table, 0, 6, "UPDATED", text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
    table.cell(flow_table, 1, 6, str.format("{0,time,HH:mm:ss}", timenow),
               text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
```

---

## Template 4: Expected Move Boundaries

Shaded zone showing the ±1σ expected move range for the session.

```pine
//@version=5
indicator("DEEP6 Expected Move", overlay=true, max_boxes_count=5, max_labels_count=10)

// ─── Inputs ──────────────────────────────────────────────────────────────────
i_em_upper      = input.float(0.0, "Expected Move Upper", group="Expected Move")
i_em_lower      = input.float(0.0, "Expected Move Lower", group="Expected Move")
i_em_remaining  = input.float(0.0, "Remaining EM (pts)",  group="Expected Move")
i_session_open  = input.float(0.0, "Session Open Price",  group="Expected Move")
i_show_zone     = input.bool(true,  "Show EM Zone",        group="Display")
i_show_labels   = input.bool(true,  "Show Labels",         group="Display")

C_EM_ZONE   = color.new(#1565C0, 88)   // Dark blue, very transparent
C_EM_BORDER = color.new(#42A5F5, 60)   // Light blue border
C_EM_LABEL  = color.new(#42A5F5, 0)
C_OPEN_LINE = color.new(#FFF176, 70)   // Yellow — session open reference

// ─── Session open reference line ─────────────────────────────────────────────
var line open_line = na
if barstate.islast and i_session_open > 0
    if not na(open_line)
        line.delete(open_line)
    open_line := line.new(bar_index - 100, i_session_open, bar_index + 30, i_session_open,
                          color=C_OPEN_LINE, style=line.style_dotted, width=1, extend=extend.right)

// ─── Expected move zone box ───────────────────────────────────────────────────
var box em_box = na
if barstate.islast and i_em_upper > 0 and i_em_lower > 0 and i_show_zone
    if not na(em_box)
        box.delete(em_box)
    em_box := box.new(
        left=bar_index - 5, top=i_em_upper,
        right=bar_index + 40, bottom=i_em_lower,
        bgcolor=C_EM_ZONE,
        border_color=C_EM_BORDER,
        border_width=1,
        border_style=line.style_dashed,
        extend=extend.right
    )

// ─── Labels ───────────────────────────────────────────────────────────────────
var label upper_label = na
var label lower_label = na
var label rem_label   = na

if barstate.islast and i_show_labels
    if not na(upper_label)
        label.delete(upper_label)
    if not na(lower_label)
        label.delete(lower_label)
    if not na(rem_label)
        label.delete(rem_label)

    if i_em_upper > 0
        upper_label := label.new(bar_index + 42, i_em_upper,
                                 "+1σ " + str.tostring(i_em_upper, "#.##"),
                                 color=color.new(#0D0D1A, 85),
                                 textcolor=C_EM_LABEL,
                                 style=label.style_label_left,
                                 size=size.small)

    if i_em_lower > 0
        lower_label := label.new(bar_index + 42, i_em_lower,
                                 "-1σ " + str.tostring(i_em_lower, "#.##"),
                                 color=color.new(#0D0D1A, 85),
                                 textcolor=C_EM_LABEL,
                                 style=label.style_label_left,
                                 size=size.small)

    if i_em_remaining > 0
        mid_price = (i_em_upper + i_em_lower) / 2
        rem_label := label.new(bar_index + 42, mid_price,
                               "EM rem: " + str.tostring(math.round(i_em_remaining, 1)) + " pts",
                               color=color.new(#0D0D1A, 85),
                               textcolor=color.new(#90A4AE, 0),
                               style=label.style_label_left,
                               size=size.tiny)
```

---

## Template 5: Conviction Meter

Visual confidence score display as a horizontal bar with color gradient.

```pine
//@version=5
indicator("DEEP6 Conviction Meter", overlay=false, max_tables_count=1)

// ─── Inputs ──────────────────────────────────────────────────────────────────
i_score         = input.float(0.0,  "Bias Score (-100 to 100)", group="Score")
i_rivers_agree  = input.int(3,      "Rivers Agreeing (0-5)",    group="Score",
                             minval=0, maxval=5)
i_options_weight = input.float(0.30, "Options Category Weight", group="Score")

// ─── Score bar rendering ──────────────────────────────────────────────────────
// Normalize score to 0-20 bar segments
_score_bar(score) =>
    // score: -100 to +100
    // bar: 20 segments, center at 10
    center = 10
    filled = math.round((score / 100.0) * 10)
    bull_count = math.max(0, filled)
    bear_count = math.max(0, -filled)

    bull_bar = str.repeat("█", bull_count) + str.repeat("░", 10 - bull_count)
    bear_bar = str.repeat("░", 10 - bear_count) + str.repeat("█", bear_count)
    bear_bar + "|" + bull_bar

_score_color(score) =>
    score > 60  ? color.new(#00E676, 0) :
     score > 30  ? color.new(#69F0AE, 0) :
     score > 10  ? color.new(#B9F6CA, 0) :
     score > -10 ? color.new(#ECEFF1, 0) :
     score > -30 ? color.new(#FFCCBC, 0) :
     score > -60 ? color.new(#FF8A65, 0) :
                   color.new(#F44336, 0)

_rivers_color(n) =>
    n >= 5 ? color.new(#00E676, 0) :
     n >= 4 ? color.new(#69F0AE, 0) :
     n >= 3 ? color.new(#FFD740, 0) :
     n >= 2 ? color.new(#FF6D00, 0) :
              color.new(#F44336, 0)

var table meter_table = table.new(
    position.bottom_center, columns=2, rows=4,
    bgcolor=color.new(#0D0D1A, 10),
    border_color=color.new(#333355, 0), border_width=1
)

if barstate.islast
    C_DIM  = color.new(#90A4AE, 0)
    C_BG   = color.new(#1A1A2E, 0)
    C_SC   = _score_color(i_score)
    C_RV   = _rivers_color(i_rivers_agree)

    table.cell(meter_table, 0, 0, "BIAS", text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
    _score_str = (i_score > 0 ? "+" : "") + str.tostring(math.round(i_score, 1))
    table.cell(meter_table, 1, 0, _score_str, text_color=C_SC, bgcolor=C_BG, text_size=size.normal)

    table.cell(meter_table, 0, 1, "BAR", text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
    table.cell(meter_table, 1, 1, _score_bar(i_score), text_color=C_SC, bgcolor=C_BG, text_size=size.tiny)

    table.cell(meter_table, 0, 2, "RIVERS", text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
    table.cell(meter_table, 1, 2, str.tostring(i_rivers_agree) + "/5",
               text_color=C_RV, bgcolor=C_BG, text_size=size.small)

    table.cell(meter_table, 0, 3, "OPT WT", text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
    table.cell(meter_table, 1, 3, str.tostring(math.round(i_options_weight * 100)) + "%",
               text_color=C_DIM, bgcolor=C_BG, text_size=size.tiny)
```

---

## Template 6: Alert Conditions

Pine alerts that fire on regime change, wall break, and flow shift.
These complement the Python-side alerting — use for TradingView-native notifications.

```pine
//@version=5
indicator("DEEP6 Options Alerts", overlay=true)

// ─── Inputs ──────────────────────────────────────────────────────────────────
i_regime        = input.string("A",   "Current Regime",    group="Alerts")
i_bias_score    = input.float(0.0,    "Bias Score",        group="Alerts")
i_flow_state    = input.string("DEAD","Flow State",        group="Alerts")
i_call_wall     = input.float(0.0,    "Call Wall",         group="Alerts")
i_put_wall      = input.float(0.0,    "Put Wall",          group="Alerts")
i_gamma_flip    = input.float(0.0,    "Gamma Flip",        group="Alerts")

// ─── State tracking with varip ────────────────────────────────────────────────
// varip: persists across bars AND within the same bar on updates
// Use for alert state to avoid re-firing on the same condition
varip string prev_regime     = "A"
varip string prev_flow_state = "DEAD"
varip float  prev_bias_sign  = 0.0

// ─── Derived conditions ───────────────────────────────────────────────────────
regime_changed    = i_regime != prev_regime
flow_changed      = i_flow_state != prev_flow_state
bias_sign         = i_bias_score > 10 ? 1.0 : i_bias_score < -10 ? -1.0 : 0.0
bias_flipped      = bias_sign != prev_bias_sign and prev_bias_sign != 0.0

// Wall proximity (within 0.3%)
near_call_wall    = i_call_wall > 0 and math.abs(close - i_call_wall) / close < 0.003
near_put_wall     = i_put_wall > 0 and math.abs(close - i_put_wall) / close < 0.003
near_gamma_flip   = i_gamma_flip > 0 and math.abs(close - i_gamma_flip) / close < 0.002

// Negative gamma entry (regime D or E)
entered_neg_gamma = regime_changed and (i_regime == "D" or i_regime == "E")
entered_pos_gamma = regime_changed and (i_regime == "A" or i_regime == "B" or i_regime == "C")

// High conviction signals
high_conviction_bull = i_bias_score > 60 and (i_flow_state == "AGGRESSIVE_BULLISH" or i_flow_state == "ACCUMULATION")
high_conviction_bear = i_bias_score < -60 and (i_flow_state == "AGGRESSIVE_BEARISH" or i_flow_state == "DISTRIBUTION")

// ─── Update state ─────────────────────────────────────────────────────────────
if barstate.islast
    prev_regime     := i_regime
    prev_flow_state := i_flow_state
    prev_bias_sign  := bias_sign

// ─── Alert declarations ───────────────────────────────────────────────────────
alertcondition(regime_changed,
               title="Regime Change",
               message="DEEP6: Regime changed to {{plot('Regime')}} | Bias: {{plot('Bias')}}")

alertcondition(entered_neg_gamma,
               title="Entered Negative Gamma",
               message="DEEP6: NEGATIVE GAMMA — Regime {{plot('Regime')}} | Trend mode active")

alertcondition(entered_pos_gamma,
               title="Entered Positive Gamma",
               message="DEEP6: POSITIVE GAMMA — Regime {{plot('Regime')}} | Range mode active")

alertcondition(near_call_wall,
               title="Near Call Wall",
               message="DEEP6: Price approaching CALL WALL {{plot('Call Wall')}} | Expect resistance")

alertcondition(near_put_wall,
               title="Near Put Wall",
               message="DEEP6: Price approaching PUT WALL {{plot('Put Wall')}} | Expect support")

alertcondition(near_gamma_flip,
               title="Near Gamma Flip",
               message="DEEP6: Price near GAMMA FLIP {{plot('Gamma Flip')}} | Regime transition risk")

alertcondition(bias_flipped,
               title="Bias Direction Flip",
               message="DEEP6: Bias flipped direction | New score: {{plot('Bias')}}")

alertcondition(high_conviction_bull,
               title="High Conviction Bullish",
               message="DEEP6: HIGH CONVICTION BULL | Score: {{plot('Bias')}} | Flow: {{plot('Flow')}}")

alertcondition(high_conviction_bear,
               title="High Conviction Bearish",
               message="DEEP6: HIGH CONVICTION BEAR | Score: {{plot('Bias')}} | Flow: {{plot('Flow')}}")

// ─── Invisible plots for alert message interpolation ─────────────────────────
plot(i_bias_score,  "Bias",      display=display.none)
plot(i_call_wall,   "Call Wall", display=display.none)
plot(i_put_wall,    "Put Wall",  display=display.none)
plot(i_gamma_flip,  "Gamma Flip",display=display.none)
```

---

## Template 7: Price Labels at Key Levels

Annotates key options levels with metadata labels that update dynamically.

```pine
//@version=5
indicator("DEEP6 Level Labels", overlay=true, max_labels_count=30)

// ─── Inputs ──────────────────────────────────────────────────────────────────
i_gamma_flip    = input.float(0.0, "Gamma Flip",   group="Levels")
i_call_wall     = input.float(0.0, "Call Wall",    group="Levels")
i_put_wall      = input.float(0.0, "Put Wall",     group="Levels")
i_net_gex       = input.float(0.0, "Net GEX ($B)", group="Levels")
i_regime        = input.string("A","Regime",       group="Levels")
i_pin_score     = input.float(0.0, "Pin Score (0-100)", group="Levels")
i_dte_magnet    = input.float(0.0, "0DTE Magnet",  group="Levels")

// ─── Label factory ────────────────────────────────────────────────────────────
_make_level_label(price, txt, txt_color, offset_bars) =>
    label.new(
        x=bar_index + offset_bars,
        y=price,
        text=txt,
        color=color.new(#0D0D1A, 80),
        textcolor=txt_color,
        style=label.style_label_left,
        size=size.small,
        tooltip=txt
    )

// ─── Draw on last bar only ────────────────────────────────────────────────────
var label[] level_labels = array.new<label>()

if barstate.islast
    // Clear previous labels
    for lbl in level_labels
        label.delete(lbl)
    array.clear(level_labels)

    offset = 3

    if i_gamma_flip > 0
        gex_str = str.tostring(math.round(i_net_gex, 2))
        txt = "GEX FLIP " + str.tostring(i_gamma_flip, "#") +
              " | GEX: $" + gex_str + "B | Regime: " + i_regime
        array.push(level_labels, _make_level_label(i_gamma_flip, txt, color.new(#FF6B35, 0), offset))

    if i_call_wall > 0
        txt = "CALL WALL " + str.tostring(i_call_wall, "#") + " | Resistance"
        array.push(level_labels, _make_level_label(i_call_wall, txt, color.new(#E63946, 0), offset))

    if i_put_wall > 0
        txt = "PUT WALL " + str.tostring(i_put_wall, "#") + " | Support"
        array.push(level_labels, _make_level_label(i_put_wall, txt, color.new(#2DC653, 0), offset))

    if i_dte_magnet > 0 and i_pin_score > 30
        txt = "0DTE MAGNET " + str.tostring(i_dte_magnet, "#") +
              " | Pin: " + str.tostring(math.round(i_pin_score)) + "%"
        array.push(level_labels, _make_level_label(i_dte_magnet, txt, color.new(#A8DADC, 0), offset))
```

---

## Performance Notes

**Use `varip` for state that must persist within a bar** (e.g., alert tracking, table references).
`var` persists across bars but resets on the same bar's recalculation. `varip` does not.

**Avoid recalculating on every bar** when data only changes on input updates:
```pine
// BAD: recalculates every bar
line.new(bar_index - 50, i_call_wall, bar_index, i_call_wall, ...)

// GOOD: only on last bar
if barstate.islast
    line.new(...)
```

**Delete before redrawing** to avoid hitting `max_lines_count` / `max_labels_count` limits:
```pine
var line my_line = na
if barstate.islast
    if not na(my_line)
        line.delete(my_line)
    my_line := line.new(...)
```

**Table cells don't need deletion** — `table.cell()` overwrites in place. Only delete the
table itself if you need to change its position or column/row count.

**MCP update pattern** (Python side):
```python
# After FlashAlpha poll, update Pine inputs via MCP
await mcp.indicator_set_inputs(entity_id=gex_levels_entity_id, inputs={
    "in_0": gamma_flip_nq,   # matches input order in Pine
    "in_1": call_wall_nq,
    "in_2": put_wall_nq,
    "in_3": dte_magnet_nq,
    "in_4": True,
    "in_5": regime_label,
})
```

Input IDs (`in_0`, `in_1`, etc.) correspond to the order inputs are declared in the script.
Use `data_get_indicator(entity_id)` to inspect current input values and verify the mapping.
