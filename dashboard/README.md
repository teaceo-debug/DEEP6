# DEEP6 Dashboard

> View-only NQ futures footprint trading dashboard. TERMINAL NOIR aesthetic. Real-time order flow, confluence scoring, Kronos E10 ML bias, and session replay — all in one screen.

<!-- Screenshot: add `docs/screenshot.png` after first live session -->

---

## Quick Start

```bash
npm install
npm run dev        # http://localhost:3000
```

The Python FastAPI backend (Phase 9) must be running at `:8000` to receive live data:

```bash
# From /Users/teaceo/DEEP6 — in a separate terminal
uvicorn deep6.api.app:app --reload
```

The dashboard connects automatically and retries with exponential backoff if the backend is not yet up.

## Commands

| Command | Purpose |
|---------|---------|
| `npm run dev` | Dev server (Turbopack) at localhost:3000 |
| `npm run build` | Production build |
| `npm run typecheck` | TypeScript strict check, no emit |
| `npm run test` | Vitest unit suite (5 test files, 32 tests) |
| `npm run test:watch` | Vitest in watch mode |

## Stack

| Layer | Choice | Version |
|-------|--------|---------|
| Framework | Next.js App Router | 16.2.3 |
| Styling | Tailwind v4 (CSS-first) | 4.x |
| Animation | Motion (Framer Motion) | 11.18.2 |
| Financial charts | Lightweight Charts custom series | 5.1.0 |
| State | Zustand with `subscribeWithSelector` | 5.0.12 |
| UI primitives | Radix UI (headless) + shadcn/ui | latest |
| Font | JetBrains Mono (variable, weights 100-800) | via next/font |
| Icons | Lucide React | 1.8.x |
| Testing | Vitest + jsdom | 2.x |

## Environment

```bash
# Optional — defaults to ws://localhost:8000/ws/live
NEXT_PUBLIC_WS_URL=ws://your-backend:8000/ws/live
```

## Docs

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — data flow, store shape, rendering split, replay mode
- [COMPONENT-INDEX.md](docs/COMPONENT-INDEX.md) — every component with props, store subscriptions, and layout slot
- [EXTENDING.md](docs/EXTENDING.md) — how to add message types, panels, zone types, overlays, and animations
- [Main project README / CLAUDE.md](../CLAUDE.md) — full system context (Rithmic, Kronos, backend stack)
