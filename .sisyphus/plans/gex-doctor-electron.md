# GEX Doctor v2.0 — Electron Desktop App

## TL;DR

> **Quick Summary**: Package the existing GEX Doctor standalone app (Python backend + Next.js UI) into a single Electron desktop app with system tray, Python sidecar management, and NT8 bridge coexistence.
>
> **Deliverables**:
> - Electron app at `gex_terminal/desktop/` wrapping the existing system
> - Python backend serves static Next.js export + API/SSE on port 8780
> - System tray with minimize/restore/quit/always-on-top
> - NT8 bridge runs as second sidecar (keeps writing gex_terminal_nt8.json)
> - Single-click launch via `npm start` or packaged installer
>
> **Estimated Effort**: Medium (tonight)
> **Parallel Execution**: YES — 4 independent tracks
> **Critical Path**: T1+T2 (parallel) → T3 → T4 → T5 → T6 → T7

---

## Context

### What Exists
- `gex_terminal/` — Python async backend (FastAPI on port 8780, orchestrator, adapters, Claude interpreter)
- `gex_terminal/ui/` — Next.js 15 retro green terminal UI (SSE consumer, Zustand store)
- `scripts/gex_terminal_nt8_bridge.py` — writes NT8 JSON every 10s
- `ninjatrader/Custom/Indicators/DEEP6/GEXTerminal.cs` — compiled NT8 indicator reading the JSON
- All 75 Python tests passing

### What Needs to Happen
1. Next.js must be configured for static export (`output: 'export'`)
2. FastAPI must serve the static export + API/SSE on same port
3. Electron wrapper must spawn Python as sidecar, load the URL, manage lifecycle
4. System tray for background operation
5. NT8 bridge spawned as second sidecar
6. electron-builder packages everything

### Metis Review Key Findings
- Server.py has NO static file serving — must add FastAPI StaticFiles
- Next.js NOT configured for static export — must add `output: 'export'`
- useGEXStream.ts API_URL pattern needs fix for same-origin serving
- NT8 bridge should stay as separate sidecar (NOT merged into main process) — zero refactoring risk
- PyInstaller hidden imports: flashalpha, scipy, pydantic_core, uvicorn submodules
- Windows process cleanup: must use `taskkill /T /F /PID`

---

## Work Objectives

### Core Objective
Package GEX Doctor into a single Electron desktop application that launches with one click, manages the Python backend as a sidecar, serves the terminal UI, and keeps the NT8 bridge running — all from a single window with system tray support.

### Must Have
- Electron app window (800×800) loading from http://127.0.0.1:8780
- Python backend spawned as child process with health check polling
- Static Next.js export served by FastAPI alongside API/SSE endpoints
- System tray: minimize to tray, restore on click, quit from context menu, always-on-top toggle
- NT8 bridge as second sidecar writing gex_terminal_nt8.json
- Graceful shutdown: taskkill /T /F on Windows
- Loading/splash state while backend starts
- Error dialog if backend fails to start within 15s

### Must NOT Have
- Custom frameless title bar (use standard window chrome)
- Auto-updater
- Settings UI
- Notification system
- Crash reporting
- PyInstaller --onefile mode (use --onedir)
- Merging NT8 bridge into main Python process
- Any changes to adapter/signal/analysis logic

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### QA Policy
- **Backend**: curl health/state/stream endpoints
- **Frontend**: Electron webContents screenshot or curl for HTML
- **Process**: Verify no orphan Python processes after quit
- **NT8**: Verify gex_terminal_nt8.json written within 15s

---

## Execution Strategy

### Parallel Execution Tracks

```
Track A (Electron Shell — start immediately):
├── T1: Electron project scaffolding (package.json, main.js, preload.js) [quick]
├── T4: System tray + window management [quick]

Track B (Frontend Static Export — start immediately):
├── T2: Next.js static export config + URL fix + build [quick]

Track C (Backend Static Serving — needs T2):
├── T3: Add FastAPI StaticFiles + SPA fallback to server.py [quick]

Track D (Sidecar Wiring — needs T1+T3):
├── T5: Wire Python sidecar lifecycle in Electron main.js [deep]
├── T6: Wire NT8 bridge as second sidecar [quick]

Track E (Assembly):
├── T7: electron-builder config + build script + smoke test [unspecified-high]
```

### Dependency Matrix

| Task | Depends On | Blocks | Track |
|------|-----------|--------|-------|
| T1 | — | T4, T5, T6 | A |
| T2 | — | T3 | B |
| T3 | T2 | T5 | C |
| T4 | T1 | T7 | A |
| T5 | T1, T3 | T7 | D |
| T6 | T1 | T7 | D |
| T7 | T4, T5, T6 | — | E |

---

## TODOs

- [x] 1. Electron Project Scaffolding

  **What to do**:
  - Create `gex_terminal/desktop/` directory
  - Create `package.json` with electron, electron-builder deps
  - Create `main.js` — Electron main process (BrowserWindow 800×800, loads http://127.0.0.1:8780)
  - Create `preload.js` — minimal preload with contextIsolation
  - Dev mode: `npm start` launches Electron pointing at backend URL
  - Create loading HTML shown while backend starts

  **Must NOT do**:
  - Do NOT add custom frameless title bar
  - Do NOT add auto-updater

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - **Can Run In Parallel**: YES (Track A — independent)
  - **Blocks**: T4, T5, T6

  **Acceptance Criteria**:
  - [ ] `npm start` in `gex_terminal/desktop/` opens Electron window
  - [ ] Window is 800×800
  - [ ] Shows loading state if backend not running

  **QA Scenarios**:
  ```
  Scenario: Electron window opens
    Tool: Bash
    Steps:
      1. cd gex_terminal/desktop && npm install
      2. npm start (verify window appears)
    Expected: Electron window opens showing loading state
  ```

- [x] 2. Next.js Static Export + URL Fix

  **What to do**:
  - Add `output: 'export'` to `gex_terminal/ui/next.config.ts`
  - Add `images: { unoptimized: true }` (required for static export)
  - Fix `useGEXStream.ts`: change `process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8780'` to use `process.env.NEXT_PUBLIC_API_URL ?? ''` or empty string pattern for same-origin
  - Run `npm run build` — verify `out/` directory created with `index.html`
  - Verify mock data mode still works

  **Must NOT do**:
  - Do NOT break the existing standalone dev server workflow

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - **Can Run In Parallel**: YES (Track B — independent)
  - **Blocks**: T3

  **Acceptance Criteria**:
  - [ ] `gex_terminal/ui/out/index.html` exists after build
  - [ ] `out/` contains all static assets

  **QA Scenarios**:
  ```
  Scenario: Static export produces valid HTML
    Tool: Bash
    Steps:
      1. cd gex_terminal/ui && npm run build
      2. Test-Path out/index.html → True
      3. Content contains "GEX Doctor"
    Expected: Static export with working HTML
  ```

- [x] 3. FastAPI Static File Serving

  **What to do**:
  - Add `StaticFiles` middleware to `gex_terminal/server.py`
  - Add `GEX_TERMINAL_STATIC_DIR` to config.py (default: `gex_terminal/ui/out`)
  - Mount static files at `/` AFTER all API routes
  - Use `html=True` for SPA fallback (serves index.html for unknown routes)
  - Ensure API routes `/health`, `/state`, `/stream` still work (mounted before static catch-all)
  - Add `/shutdown` endpoint for graceful Electron shutdown

  **Must NOT do**:
  - Do NOT change any API endpoint behavior
  - Do NOT remove CORS middleware

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - **Can Run In Parallel**: NO (needs T2 output path)
  - **Blocks**: T5

  **References**:
  - Metis directive: mount API routes FIRST, static files LAST
  - `from fastapi.staticfiles import StaticFiles` + `html=True`

  **Acceptance Criteria**:
  - [ ] `curl http://127.0.0.1:8780/` returns HTML
  - [ ] `curl http://127.0.0.1:8780/health` returns JSON
  - [ ] `curl -N http://127.0.0.1:8780/stream` returns SSE events
  - [ ] All 75 existing tests still pass

  **QA Scenarios**:
  ```
  Scenario: Static + API coexistence
    Tool: Bash
    Steps:
      1. Start: python -m gex_terminal
      2. curl http://127.0.0.1:8780/ → HTML content
      3. curl http://127.0.0.1:8780/health → JSON with status
      4. curl -N http://127.0.0.1:8780/stream → data: events
    Expected: Both static and API endpoints work on same port
  ```

- [x] 4. System Tray + Window Management

  **What to do**:
  - Add system tray icon (use a simple green circle or GEX icon)
  - Tray context menu: Show/Hide, Always on Top (toggle), Quit
  - Minimize to tray on window close (don't quit)
  - Restore from tray click
  - Keep app alive when window is hidden
  - Always-on-top toggle

  **Must NOT do**:
  - Do NOT add notification popups
  - Do NOT add complex menu system

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - **Can Run In Parallel**: YES (needs T1 main.js to exist)
  - **Blocks**: T7

  **Acceptance Criteria**:
  - [ ] Tray icon visible in system tray
  - [ ] Close button minimizes to tray (not quit)
  - [ ] Tray click restores window
  - [ ] Quit from tray menu exits app

- [x] 5. Python Sidecar Lifecycle in Electron

  **What to do**:
  - In main.js, spawn Python backend as child process on app ready
  - Dev mode: `spawn('python', ['-m', 'gex_terminal'], { cwd: projectRoot })`
  - Health check loop: poll http://127.0.0.1:8780/health every 500ms, timeout 15s
  - On health OK: load URL in BrowserWindow
  - On timeout: show error dialog
  - On app quit: call `/shutdown` endpoint, wait 3s, then `taskkill /T /F /PID`
  - Handle sidecar crash: show error, offer restart
  - Check PID file `~/.deep6/gexdoctor_v2.pid` before spawning — reuse if already running

  **Must NOT do**:
  - Do NOT add auto-restart loop (show error dialog instead)
  - Do NOT use process.kill() on Windows (doesn't work for process trees)

  **Recommended Agent Profile**:
  - **Category**: `deep`

  **Parallelization**:
  - **Can Run In Parallel**: NO (needs T1 main.js + T3 static serving)
  - **Blocks**: T7

  **References**:
  - Metis: use `taskkill /T /F /PID` for Windows cleanup
  - Oracle: poll /health until ready, then show window
  - Existing PID lock: `~/.deep6/gexdoctor_v2.pid`

  **Acceptance Criteria**:
  - [ ] Python backend starts automatically when Electron opens
  - [ ] Window loads terminal UI after health check passes
  - [ ] Closing Electron kills Python process (no orphans)
  - [ ] Error dialog if backend fails to start

- [x] 6. NT8 Bridge Sidecar

  **What to do**:
  - Spawn `scripts/gex_terminal_nt8_bridge.py` as second child process
  - Start after main backend is healthy
  - Kill on app quit (same taskkill pattern)
  - Log bridge stdout/stderr to console

  **Must NOT do**:
  - Do NOT merge into main Python process
  - Do NOT make NT8 bridge required (if it fails, main app continues)

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - **Can Run In Parallel**: YES (needs T1 main.js)
  - **Blocks**: T7

  **Acceptance Criteria**:
  - [ ] gex_terminal_nt8.json written within 15s of app start
  - [ ] Bridge crash doesn't crash the main app

- [x] 7. Electron-Builder Config + Build + Smoke Test

  **What to do**:
  - Add electron-builder config to `gex_terminal/desktop/package.json`
  - Configure `extraResources` for Python backend files
  - Configure `files` to include static frontend
  - Add build scripts: `npm run build:frontend`, `npm run build:app`
  - Run smoke test: `npm run build:app` produces installer/portable
  - Verify packaged app launches correctly

  **Must NOT do**:
  - Do NOT configure auto-updater
  - Do NOT configure code signing (save for later)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`

  **Parallelization**:
  - **Can Run In Parallel**: NO (needs all previous tasks)

  **Acceptance Criteria**:
  - [ ] `npm run build:app` produces output in `dist/`
  - [ ] Packaged app launches and shows terminal UI

---

## Final Verification Wave (after ALL tasks)

- [x] F1. **Integration Test** — Start packaged app, verify terminal UI loads, SSE streams data, NT8 JSON updates
- [x] F2. **Process Cleanup Test** — Close app, verify no orphan Python processes
- [x] F3. **Tray Test** — Minimize to tray, restore, quit from tray

---

## Commit Strategy

- After T1+T2: `feat(gex-terminal): electron scaffolding + static export`
- After T3+T4: `feat(gex-terminal): static serving + system tray`
- After T5+T6: `feat(gex-terminal): sidecar lifecycle + NT8 bridge`
- After T7: `feat(gex-terminal): electron-builder packaging`

---

## Success Criteria

### Final Checklist
- [ ] Electron app opens 800×800 window with retro green terminal
- [ ] Python backend managed as sidecar (auto-start, auto-kill)
- [ ] SSE streaming works through Electron window
- [ ] System tray with minimize/restore/quit/always-on-top
- [ ] NT8 bridge writes JSON in background
- [ ] No orphan processes after quit
- [ ] All 75 existing Python tests still pass
