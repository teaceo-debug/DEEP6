# GEX Doctor v2.0 — Institutional Options Bias Terminal

A standalone, continuously-running Python data center + retro 80s terminal UI that synthesizes options market data from 3 sources and displays NQ directional bias in an 800×800 fixed green terminal window.

## Prerequisites

- Python 3.12+
- Node.js 20+ (for UI)
- API keys: FlashAlpha, Massive.com, Unusual Whales (optional), Anthropic

## Quick Start

### 1. Configure API Keys

```bash
cp .env.gex_terminal.example .env.gex_terminal
# Edit .env.gex_terminal with your API keys
```

### 2. Install Dependencies

```bash
# Python backend
pip install -r gex_terminal/requirements.txt

# Next.js UI
cd gex_terminal/ui && npm install
```

### 3. Validate Configuration

```bash
python -m gex_terminal --dry-run
```

### 4. Start

```bash
# Windows PowerShell
.\scripts\start_gex_terminal.ps1

# Or manually:
# Terminal 1: Python backend
python -m gex_terminal

# Terminal 2: Next.js UI
cd gex_terminal/ui && npm run dev
```

Open http://localhost:3001 in your browser.

## Architecture

```
FlashAlpha API ──┐
Massive.com API ─┼──► Python Orchestrator ──► FastAPI SSE ──► Next.js Terminal UI
Unusual Whales ──┘         │
                           ▼
                    Claude API (narrative)
                           │
                           ▼
                    DEEP6 Bias Engine (bidirectional)
```

## Configuration

All configuration via environment variables (prefix: `GEX_TERMINAL_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `GEX_TERMINAL_FLASHALPHA_API_KEY` | (empty) | FlashAlpha API key |
| `GEX_TERMINAL_MASSIVE_API_KEY` | (empty) | Massive.com API key |
| `GEX_TERMINAL_UW_API_KEY` | (empty) | Unusual Whales API key |
| `GEX_TERMINAL_ANTHROPIC_API_KEY` | (empty) | Anthropic API key |
| `GEX_TERMINAL_SERVER_PORT` | 8780 | Backend port |
| `GEX_TERMINAL_REFRESH_INTERVAL_SEC` | 30 | Data refresh interval |
| `GEX_TERMINAL_CLAUDE_MODEL` | claude-haiku-4-5-20251001 | Claude model |
| `GEX_TERMINAL_CLAUDE_BUDGET_DAILY_USD` | 10.0 | Daily Claude budget |

## Endpoints

- `GET /health` — Source health status
- `GET /state` — Current GEXTerminalSnapshot
- `GET /stream` — SSE stream of snapshots

## Tests

```bash
pytest gex_terminal/tests/ -v
```

## Logs

- `~/.deep6/gexdoctor_v2.log` — Application log (rotating 10MB)
- `~/.deep6/gexdoctor_v2_audit.jsonl` — Claude API usage audit
- `~/.deep6/gexdoctor_v2.pid` — Process ID (deleted on exit)
