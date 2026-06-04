# AI Chart Copilot

A real-time trading assistant that watches your NinjaTrader 8 chart, reads DEEP6 signal scores, and delivers concise market narratives and advisory trade calls via a screen overlay.

## Overview

The copilot runs as a background Python process alongside NinjaTrader 8 and the DEEP6 engine. Every 15 seconds it synthesizes live market context into a plain-English narrative. When the DEEP6 confluence score crosses 72 and a valid setup tier is detected, it captures a screenshot, analyzes the chart with Claude vision, and generates a concrete advisory trade plan.

Key features:

- **Live narrative** updated every 15 seconds from signal scores, news, sentiment, and internals
- **Vision analysis** every 30 seconds via screenshot of the NT8 chart window
- **MAD levels** read from the madlevels.com indicator overlay on the chart
- **Trade calls** triggered at score >= 72 with a 5-minute cooldown between calls
- **Economic calendar** countdowns for upcoming high-impact events
- **Options flow** from Massive.com (unusual trades, put/call ratio, net premium)
- **RTH watchdog** auto-pauses outside 7:30 AM to 3:00 PM Central Time
- **Token budget** enforced per hour to keep API costs predictable

## Requirements

- Python 3.12+
- NinjaTrader 8 running with a visible chart window
- DEEP6 engine running (data bridge on port 9200, API on port 8765)
- `ANTHROPIC_API_KEY` set in your environment or `deep6/.env`

## Installation

```bash
# From the DEEP6 repo root
pip install -e ".[copilot]"

# Copy the example env file and fill in your keys
cp deep6/copilot/.env.example deep6/.env
```

Edit `deep6/.env` and set at minimum:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Configuration

All settings are read from environment variables. The copilot loads `deep6/.env` automatically if it exists.

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required) | Anthropic API key |
| `MASSIVE_API_KEY` | (optional) | Massive.com options flow API key |
| `CLAUDE_NARRATIVE_MODEL` | `claude-3-5-sonnet-latest` | Model for narrative generation |
| `CLAUDE_VISION_MODEL` | `claude-3-5-sonnet-latest` | Model for chart screenshot analysis |
| `COPILOT_SCREENSHOT_INTERVAL_SEC` | `30` | Seconds between screenshot captures |
| `COPILOT_NARRATIVE_INTERVAL_SEC` | `15` | Seconds between narrative updates |
| `COPILOT_TOKEN_BUDGET_PER_HOUR` | `500000` | Max tokens per hour across all calls |
| `COPILOT_OVERLAY_SIDE` | `right` | Overlay position: `left` or `right` |
| `COPILOT_OVERLAY_WIDTH` | `400` | Overlay width in pixels |
| `COPILOT_CALENDAR_ENABLED` | `true` | Enable economic calendar adapter |
| `COPILOT_NEWS_ENABLED` | `true` | Enable news headlines adapter |
| `COPILOT_SENTIMENT_ENABLED` | `true` | Enable sentiment adapter |
| `COPILOT_INTERNALS_ENABLED` | `true` | Enable market internals adapter |
| `COPILOT_OPTIONS_FLOW_ENABLED` | `true` | Enable options flow adapter |
| `COPILOT_DATA_BRIDGE_HOST` | `127.0.0.1` | DEEP6 data bridge TCP host |
| `COPILOT_DATA_BRIDGE_PORT` | `9200` | DEEP6 data bridge TCP port |
| `COPILOT_API_HOST` | `127.0.0.1` | DEEP6 FastAPI host |
| `COPILOT_API_PORT` | `8765` | DEEP6 FastAPI port |

## Usage

```bash
# Start the copilot (reads deep6/.env automatically)
python -m deep6.copilot

# Preview startup without side effects
python -m deep6.copilot --dry-run

# Test overlay wiring only
python -m deep6.copilot --test-overlay

# Show all options
python -m deep6.copilot --help
```

Stop with `Ctrl+C`. The copilot saves session state to `.copilot_state.json` on shutdown.

## Data Sources

Each adapter runs independently. Disabling one doesn't affect the others.

| Adapter | What it provides | Env flag |
|---|---|---|
| **Calendar** | Upcoming economic events (CPI, FOMC, NFP) with countdown timers | `COPILOT_CALENDAR_ENABLED` |
| **News** | Recent market headlines relevant to NQ/equities | `COPILOT_NEWS_ENABLED` |
| **Sentiment** | Aggregate sentiment indicators (fear/greed, put/call, etc.) | `COPILOT_SENTIMENT_ENABLED` |
| **Internals** | Market breadth, NYSE TICK, ADD, VOLD | `COPILOT_INTERNALS_ENABLED` |
| **Options Flow** | Unusual options trades from Massive.com (requires API key) | `COPILOT_OPTIONS_FLOW_ENABLED` |

Options flow polls every 3 minutes. Trades are flagged as unusual when premium exceeds $100K and volume/OI ratio exceeds 2.0.

## MAD Levels

The copilot reads MAD levels (from the madlevels.com NinjaTrader indicator) directly from the chart screenshot using Claude vision. It does not connect to madlevels.com directly.

When MAD levels are detected in the screenshot, they're included in trade call context as key support/resistance references. If no MAD levels are visible, trade call confidence is capped at 25% and the rationale notes the missing data.

## Trade Calls

A trade call is generated when all of the following are true:

1. DEEP6 confluence score >= 72
2. Setup tier is TYPE_A or TYPE_B
3. At least 5 minutes have passed since the last trade call
4. A screenshot can be captured from the NT8 window

Each trade call includes:

- Direction (long/short), entry price, stop, and target
- Confidence percentage
- Rationale with signal categories firing
- MAD levels visible at the time
- Vision-detected price action and patterns

Trade calls expire from the overlay after 10 minutes.

## Overlay Layout

The overlay is a fixed sidebar panel (default: right side, 400px wide) with five sections:

1. **Status bar** — connection state, RTH indicator, token budget remaining
2. **Narrative** — latest market read, updated every 15 seconds
3. **Trade call** — current advisory setup (blank when no active call)
4. **Data sources** — freshness indicators for each adapter
5. **Calendar** — next 2 hours of economic events with countdown timers

## Cost Management

Approximate API costs at default settings:

| Usage | Model | Est. cost/hr |
|---|---|---|
| Narrative (every 15s) | claude-3-5-sonnet-latest | ~$0.05/hr |
| Vision (every 30s) | claude-3-5-sonnet-latest | ~$0.20/hr |
| Trade calls (rare) | claude-3-5-sonnet-latest | ~$0.01/hr |
| **Total** | | **~$0.25/hr** |

The `COPILOT_TOKEN_BUDGET_PER_HOUR` limit (default 500K tokens) acts as a hard ceiling. The copilot throttles or skips calls when approaching the limit.

To reduce costs, increase the interval settings or switch to a smaller model:

```
COPILOT_NARRATIVE_INTERVAL_SEC=30
COPILOT_SCREENSHOT_INTERVAL_SEC=60
```

## Troubleshooting

**NT8 window not found**
The copilot searches for a visible window with "NinjaTrader" in the title. Make sure NT8 is running and a chart is open. The screen capture module is Windows-only.

**`ANTHROPIC_API_KEY` missing**
The copilot will start but all Claude calls will fail silently. Set the key in `deep6/.env` or your shell environment before launching.

**Overlay not showing**
Run `python -m deep6.copilot --test-overlay` to verify the overlay can render. Check that your display scaling isn't hiding the panel off-screen.

**Options flow returning empty**
Either `MASSIVE_API_KEY` is not set, or the Massive.com endpoint shape has changed. The adapter tries three endpoint candidates and falls back to an empty snapshot on failure. Check logs for `options flow fetch failed`.

**Copilot paused outside market hours**
This is expected. The RTH watchdog pauses the copilot outside 7:30 AM to 3:00 PM Central Time on weekdays. It resumes automatically at the next open.

**Bridge connection failed**
The DEEP6 data bridge must be running on `COPILOT_DATA_BRIDGE_HOST:COPILOT_DATA_BRIDGE_PORT` (default `127.0.0.1:9200`). Start the DEEP6 engine before launching the copilot.
