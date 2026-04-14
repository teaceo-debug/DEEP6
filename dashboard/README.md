# DEEP6 Dashboard (Phase 11)

View-only footprint + signal + replay frontend for DEEP6 NQ futures trading system.

## Run

```bash
npm install
npm run dev   # http://localhost:3000
```

Python backend (Phase 9) must be running on :8000 for real data.

## Build / Test

```bash
npm run typecheck
npm run build
npm run test
```

## Architecture

- Next.js 16.2.3 App Router, dark-only
- Zustand 5.0.12 with mutable ring buffers (500 bars, 200 signals, 50 T&S)
- Lightweight Charts 5.1.0 custom series for footprint rendering (Wave 2)
- WebSocket from FastAPI backend at ws://localhost:8000 (Wave 2)
- Session replay via HTTP polling against /api/replay/{session}/{bar_index} (Wave 3)
