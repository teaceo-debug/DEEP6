# DEEP6 AI Chart Copilot

Real-time AI trading copilot for NQ futures. Synthesizes 44-signal engine output,
GEX data, Kronos E10 bias, MAD levels (via screenshot vision), news, market internals,
options flow, and social sentiment into actionable market narrative and trade recommendations.

Displayed as a transparent overlay sidebar docked to NinjaTrader 8.

## Quick Start

### 1. Install dependencies

```bash
pip install -e ".[copilot]"
```

### 2. Configure environment

Copy `.env.example` to `.env` and set:
- `ANTHROPIC_API_KEY` — required for Claude AI analysis
- All other vars have sensible defaults

### 3. Launch

```bash
# Start in advisory mode (overlay + narrative)
python -m deep6.copilot

# Dry run (test startup without overlay)
python -m deep6.copilot --dry-run

# Test overlay rendering
python -m deep6.copilot --test-overlay
```

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | (required) | Claude API key |
| `CLAUDE_NARRATIVE_MODEL` | claude-3-5-sonnet-latest | Model for narrative generation |
| `CLAUDE_VISION_MODEL` | claude-3-5-sonnet-latest | Model for chart screenshot analysis |
| `COPILOT_SCREENSHOT_INTERVAL_SEC` | 30 | Seconds between chart screenshots |
| `COPILOT_NARRATIVE_INTERVAL_SEC` | 15 | Seconds between narrative updates |
| `COPILOT_TOKEN_BUDGET_PER_HOUR` | 500000 | Max Claude API tokens per hour |
| `COPILOT_OVERLAY_SIDE` | right | Overlay position: "left" or "right" |
| `COPILOT_OVERLAY_WIDTH` | 400 | Overlay width in pixels |
| `COPILOT_DATA_BRIDGE_HOST` | 127.0.0.1 | DataBridge TCP host |
| `COPILOT_DATA_BRIDGE_PORT` | 9200 | DataBridge TCP port |
| `COPILOT_API_HOST` | 127.0.0.1 | FastAPI WebSocket host |
| `COPILOT_API_PORT` | 8765 | FastAPI WebSocket port |
| `COPILOT_CALENDAR_ENABLED` | true | Economic calendar adapter |
| `COPILOT_NEWS_ENABLED` | true | News feed adapter |
| `COPILOT_SENTIMENT_ENABLED` | true | Social sentiment adapter |
| `COPILOT_INTERNALS_ENABLED` | true | Market internals adapter |
| `COPILOT_OPTIONS_FLOW_ENABLED` | true | Options flow adapter |

## Architecture

```
DEEP6 Copilot Architecture
│
├── vision.py          — ScreenCapture (mss + win32gui)
├── vision_analysis.py — VisionAnalyzer (Claude Vision → MAD levels)
├── brain.py           — CopilotBrain (Claude API wrapper, streaming)
├── context.py         — ContextAggregator (all sources → LLM prompt)
├── narrative.py       — NarrativeEngine (continuous commentary loop)
├── trade_calls.py     — TradeCallEngine (signal confluence → recommendations)
├── overlay.py         — CopilotOverlay (transparent sidebar renderer)
├── overlay_content.py — OverlayContentManager (engine → overlay bridge)
├── bridge_client.py   — CopilotBridgeClient (TCP + WebSocket consumer)
├── budget.py          — TokenBudgetTracker (cost control)
├── freshness.py       — FreshnessTracker (data source health)
├── session.py         — CopilotSessionManager (lifecycle orchestration)
├── config.py          — CopilotConfig (from .env)
├── types.py           — Shared type definitions
└── adapters/
    ├── calendar.py    — Economic calendar (free RSS feeds)
    ├── news.py        — News headlines (Reuters, CNBC, MarketWatch)
    ├── sentiment.py   — Social sentiment (StockTwits + Reddit)
    ├── options_flow.py — Options flow (Massive.com API)
    └── internals.py   — Market internals (DataBridge TCP)
```

## Data Sources

| Source | Provider | Cost | Polling |
|--------|----------|------|---------|
| 44-signal engine | DEEP6 DataBridge | Free (existing) | Real-time |
| GEX + options flow | Massive.com | Existing sub | 3 min |
| Kronos E10 bias | Local model | Free | Per bar |
| MAD levels | madlevels.com NT8 indicator | Existing sub | 30s (vision) |
| Economic calendar | Free RSS feeds | Free | 5 min |
| News headlines | Reuters/CNBC/MarketWatch RSS | Free | 2 min |
| Social sentiment | StockTwits + Reddit | Free | 5 min |
| Market internals | DataBridge (NT8 TICK/ADD/VOLD) | Free (existing) | Real-time |

## Cost Estimation (Claude API)

| Usage | Model | Tokens/hr | Cost/hr |
|-------|-------|-----------|---------|
| Narrative (15s intervals) | claude-3-5-sonnet-latest | ~240 calls x ~2K tokens | ~$0.72/hr |
| Vision (30s intervals) | claude-3-5-sonnet-latest | ~120 calls x ~3K tokens | ~$0.54/hr |
| Trade calls (occasional) | claude-3-5-sonnet-latest | ~5 calls x ~2K tokens | ~$0.15/hr |
| **Total estimate** | | ~500K tokens | **~$1.41/hr** |

Default budget: 500,000 tokens/hour. Adjust `COPILOT_TOKEN_BUDGET_PER_HOUR` to control costs.

## Troubleshooting

**Overlay not visible**
- Ensure NinjaTrader 8 is running with a chart open
- Check `transparent-overlay` is installed: `pip install transparent-overlay`
- Try `--test-overlay` flag to test without full startup

**No MAD levels in analysis**
- Ensure madlevels.com indicator is loaded on the NT8 chart
- Check that MAD levels are visible in the chart area (not off-screen)
- Increase `COPILOT_SCREENSHOT_INTERVAL_SEC` if API costs are too high

**Claude API errors**
- Verify `ANTHROPIC_API_KEY` is set correctly
- Check remaining budget: monitor logs for "budget exhausted" messages
- Reduce `COPILOT_TOKEN_BUDGET_PER_HOUR` if spending is too high

**DataBridge not connecting**
- Ensure DEEP6 engine is running (DataBridgeIndicator loaded in NT8)
- Verify `COPILOT_DATA_BRIDGE_PORT=9200` matches the bridge server port
- Check NT8 Output window for bridge server startup messages

**Social sentiment API rate limited**
- StockTwits allows 200 requests/hour on the free tier
- Set `COPILOT_SENTIMENT_ENABLED=false` to disable if rate limited
- The adapter automatically backs off with exponential delay on 429 responses

## Safety Notes

- **Advisory only** — no autonomous trade execution
- **No TTS/voice** in V1
- **Read-only** — does not modify existing DEEP6 signal engines
- **API keys** must be in `.env` only, never hardcoded
- **Hard token budget** — prevents runaway Claude API spending
