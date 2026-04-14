---
phase: 11
slug: deep6-trading-web-app
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-13
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (Python)** | pytest 9.0.3 |
| **Framework (TypeScript)** | vitest (via `npm run test`) |
| **Config file** | `pyproject.toml` (Python) / `dashboard/vitest.config.ts` (Wave 0 installs) |
| **Quick run command** | `cd /Users/teaceo/DEEP6 && python -m pytest tests/ -x -q` |
| **Full suite command** | `cd /Users/teaceo/DEEP6 && python -m pytest tests/ -v && cd dashboard && npm run test && npm run typecheck && npm run build` |
| **Estimated runtime** | ~30s (pytest) + ~20s (vitest + typecheck + build) |

---

## Sampling Rate

- **After every task commit:** `cd /Users/teaceo/DEEP6 && python -m pytest tests/ -x -q && cd dashboard && npm run typecheck`
- **After every plan wave:** Full suite — `python -m pytest tests/ -v` + `npm run test` + `npm run build`
- **Before `/gsd-verify-work`:** Full suite must be green + operator has approved Phase 11 smoke test checkpoint (Task 3 of Plan 11-04)
- **Max feedback latency:** ~50 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | APP-03 | T-11-01 | WS connections isolated per client; no broadcast overflow | unit + integration | `python -m pytest tests/test_ws_manager.py -x` | ❌ W0 | ⬜ pending |
| 11-01-02 | 01 | 1 | APP-04, APP-03 | T-11-02 | Session ID encoded; bar_index clamped at endpoint | unit (pytest) | `python -m pytest tests/test_replay_endpoint.py -x` | ❌ W0 | ⬜ pending |
| 11-02-01 | 02 | 1 | APP-08 | — | No tradingview-widget or iframe in bundle | grep + typecheck | `grep -r "tradingview-widget\|tv.com/widget" dashboard/ && cd dashboard && npm run typecheck` | N/A | ⬜ pending |
| 11-02-02 | 02 | 1 | APP-03 | T-11-03 | WS message discriminated union routes correctly; no unknown type leaks | unit (vitest) | `cd dashboard && npx vitest run store/tradingStore.test.ts` | ❌ W0 | ⬜ pending |
| 11-03-01 | 03 | 2 | APP-01 | T-11-06 | FootprintSeries priceValueBuilder + isWhitespace type-correct; no XSS in label render | unit (vitest) + typecheck | `cd dashboard && npx vitest run lib/lw-charts/ && npm run typecheck` | ❌ W0 | ⬜ pending |
| 11-03-02 | 03 | 2 | APP-01 | T-11-07 | Zone overlay canvas pointer-events:none; no input capture | manual smoke | Visual inspection — mouse events pass through to LW Charts | N/A | ⬜ pending |
| 11-03-03 | 03 | 2 | APP-03 | T-11-08 | Signal feed renders only last 200 events; no unbounded DOM growth | unit (vitest) | `cd dashboard && npx vitest run store/tradingStore.test.ts -- --filter=signalFeed` | ❌ W0 | ⬜ pending |
| 11-04-01 | 04 | 3 | APP-04 | T-11-15, T-11-16 | fetchSessionRange encodes sessionId; jumpToBar clamps 0..totalBars-1 | unit (vitest) | `cd dashboard && npx vitest run store/replayStore.test.ts` | ❌ W0 | ⬜ pending |
| 11-04-02 | 04 | 3 | APP-04, APP-06 | T-11-18 | P&L display localhost-only; session selector populates from fetchSessions() | manual smoke | Smoke test scenarios 5 + 6 in dashboard/e2e/smoke.md | N/A | ⬜ pending |
| 11-04-03 | 04 | 3 | APP-04, APP-06, APP-08 | — | All 8 scenarios pass end-to-end | operator checkpoint | Operator approval in dashboard/e2e/smoke.md | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ws_manager.py` — stubs for APP-03 WS broadcast (Python unit test: broadcast to 2 mock sockets)
- [ ] `tests/test_replay_endpoint.py` — FastAPI replay endpoint: session query, bar_index slicing, 404 on missing session
- [ ] `tests/test_event_store.py::test_bar_history` — EventStore `insert_bar` + `fetch_bars_for_session` (requires `bar_history` table)
- [ ] `dashboard/store/tradingStore.test.ts` — Zustand ring buffer push + discriminated union dispatch tests
- [ ] `dashboard/store/replayStore.test.ts` — 9 replayStore behaviors + fetch mock for replayClient
- [ ] `dashboard/vitest.config.ts` — vitest config with jsdom + path aliases matching `tsconfig.json`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ZoneOverlay redraws on chart scroll without throwing | APP-01 | Canvas rendering not testable in jsdom | After `npm run dev`, scroll/zoom the footprint chart and confirm zone bands repaint correctly |
| WebSocket reconnects after server restart | APP-03 | Requires live process kill/restart cycle | Kill FastAPI, verify header dot turns yellow then green within 30s |
| TYPE_A pulse (1s lime background glow) | APP-01, APP-03 | CSS animation requires browser | Post TYPE_A signal event; verify lime left border + 1s glow in signal feed row |
| Replay step-through end-to-end | APP-04 | Requires real session data + browser interaction | Smoke test scenario 5: seed `smoke-test` session, navigate to `?session=smoke-test`, step Prev/Next/Play |
| PnlStatus green/red + circuit breaker dot | APP-06 | Requires WS status message + visual check | Smoke test scenario 6: post status payloads and verify colors |
| Session selector populates available dates | APP-04 | Requires real `bar_history` rows + browser | Smoke test: open ReplayControls dropdown and confirm known session dates appear |

---

## Requirement Coverage Matrix

| Req ID | Description | Plans | Test Commands | Status |
|--------|-------------|-------|---------------|--------|
| APP-01 | Custom footprint chart + zone overlays | 11-02, 11-03 | `npm run typecheck`, manual smoke scenarios 2-3 | ⬜ pending |
| APP-03 | Real-time WebSocket push from FastAPI | 11-01, 11-02 | `pytest tests/test_ws_manager.py`, `vitest run store/tradingStore.test.ts`, manual smoke scenarios 1, 4 | ⬜ pending |
| APP-04 | Session replay bar-by-bar with signals | 11-01, 11-04 | `pytest tests/test_replay_endpoint.py`, `pytest tests/test_event_store.py::test_bar_history`, `vitest run store/replayStore.test.ts`, manual smoke scenario 5, 7 | ⬜ pending |
| APP-06 (lite) | Live P&L + circuit breaker state | 11-04 | manual smoke scenario 6 | ⬜ pending |
| APP-08 | Zero TradingView dependency | 11-02 | `grep -r "tradingview-widget\|tv.com/widget" dashboard/` returns empty | ⬜ pending |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
