# DEEP6 Dashboard

View-focused operator dashboard and replay UI for DEEP6.

This dashboard is best understood as a visualization layer for:
- replay and inspection
- operator-facing score/signal/status display
- backend-connected live-like monitoring
- frontend demo mode when no backend is available

It is not the canonical source of project truth.
For overall system status, read:
- `../README.md`
- `../docs/CURRENT-STATE.md`
- `../docs/VERIFICATION-LADDER.md`

## Current role

The dashboard currently serves three use cases:

1. Demo mode
- frontend-only rendering and interaction validation
- no backend dependency
- useful for layout, UX, and presentation checks

2. Replay / backend-connected mode
- connects to the DEEP6 backend for replay and status-driven workflows
- useful for inspecting score/signal behavior and backend integration

3. Operator-facing visualization
- acts as a display surface for bars, signals, scores, and status
- should not be treated as the only source of operational truth

## Quick start

```bash
npm install
npm run dev
```

Default local URL:
- `http://localhost:3000`

## Backend expectations

Important:
The DEEP6 repo is still consolidating its canonical runtime path and port story.
This dashboard expects a backend URL and websocket URL that match the active backend you are running.

Before trusting backend-connected mode:
- verify the backend host/port you intend to use
- verify the websocket route you intend to use
- verify whether you are in demo, replay, or backend-connected mode

Do not assume every repo document uses the same port until the runtime consolidation work is complete.

## Environment

Examples:

```bash
# Frontend-only demo mode
NEXT_PUBLIC_DEMO_MODE=true

# Backend-connected mode
NEXT_PUBLIC_DEMO_MODE=false
NEXT_PUBLIC_WS_URL=ws://localhost:8765/ws/live
NEXT_PUBLIC_API_BASE=http://localhost:8765
```

If your backend is running on a different port, set both values explicitly.

## Commands

| Command | Purpose |
|---------|---------|
| `npm run dev` | Start local dev server |
| `npm run build` | Production build |
| `npm run typecheck` | TypeScript check |
| `npm run test` | Vitest suite |
| `npm run test:watch` | Vitest watch mode |

## Modes

### Demo mode
Use when:
- no backend is available
- validating UI and interaction behavior
- presenting the dashboard without backend dependencies

Enable with:

```bash
NEXT_PUBLIC_DEMO_MODE=true npm run dev
```

### Backend-connected mode
Use when:
- validating replay and websocket integration
- reviewing live-like backend output
- checking operator-facing status behavior

Enable with explicit URLs:

```bash
NEXT_PUBLIC_DEMO_MODE=false \
NEXT_PUBLIC_WS_URL=ws://localhost:8765/ws/live \
NEXT_PUBLIC_API_BASE=http://localhost:8765 \
npm run dev
```

Adjust ports to match the backend you are actually running.

## Documentation

- `docs/ARCHITECTURE.md` — data flow, store shape, rendering split, replay mode
- `docs/COMPONENT-INDEX.md` — component map
- `docs/EXTENDING.md` — extension points
- `../docs/CURRENT-STATE.md` — canonical project truth
- `../docs/VERIFICATION-LADDER.md` — trust and promotion model

## Important cautions

- Do not confuse demo mode with backend-connected behavior.
- Do not treat the dashboard as proof that execution logic is production-ready.
- Do not assume the dashboard alone is sufficient operator safety instrumentation.
- Treat the dashboard as one subsystem within DEEP6, not the whole system.
