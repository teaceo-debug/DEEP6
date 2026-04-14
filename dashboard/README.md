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

## Demo Mode (Vercel / no backend)

The dashboard ships with an in-browser demo mode that generates realistic NQ
futures activity entirely client-side — no backend required.

**Flip between modes via environment variable:**

| Env var | Value | Behavior |
|---------|-------|----------|
| `NEXT_PUBLIC_DEMO_MODE` | `true` | In-browser demo; WebSocket disabled. Works on Vercel. |
| `NEXT_PUBLIC_DEMO_MODE` | `false` (default) | Connects to real backend via WebSocket. |

**Local demo run:**

```bash
NEXT_PUBLIC_DEMO_MODE=true npm run dev
```

**Vercel deployment:**

Set `NEXT_PUBLIC_DEMO_MODE=true` in the Vercel project environment variables.
No backend, no WebSocket URL needed.

The demo ports `scripts/demo_broadcast.py` to TypeScript:
- `PriceModel` — autocorrelated random walk, 0.25-tick snapped, bounded to NQ range
- `ScoreModel` — sine-rippled oscillator 30-92, TYPE_A spikes, Kronos updates every 15-20s
- `SignalScheduler` — Poisson timers (TYPE_C 8-15s, TYPE_B 30-60s, TYPE_A 90-180s)
- `buildBar` — 31-row Gaussian-weighted footprint ladder, 30% one-sided bars
- Dispatches directly to Zustand store at 500ms intervals (rate 2x equivalent)

## Docs

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — data flow, store shape, rendering split, replay mode
- [COMPONENT-INDEX.md](docs/COMPONENT-INDEX.md) — every component with props, store subscriptions, and layout slot
- [EXTENDING.md](docs/EXTENDING.md) — how to add message types, panels, zone types, overlays, and animations
- [Main project README / CLAUDE.md](../CLAUDE.md) — full system context (Rithmic, Kronos, backend stack)
