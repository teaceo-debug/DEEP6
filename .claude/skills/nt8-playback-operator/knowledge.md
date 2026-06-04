# NT8 Playback Operator Knowledge Base

## Scope

This skill owns the NT8 replay / playback operator surface:
- download native NT8 Market Replay data
- prepare playback sessions
- control playback state (play/pause/step/rewind/forward/speed)
- verify loaded replay data and session position
- connect NT8 playback workflows to DEEP6 replay and backtesting flows

## Core Distinction

There are **three different replay/backtest layers** in this repo. Do not confuse them.

### 1. NT8 Market Replay download
- Native `.nrd` data under `Documents\NinjaTrader 8\db\replay\...`
- Used by NinjaTrader Playback / Market Replay workflows
- Current production anchor: `ninjatrader/scripts/nt8-replay-download.ps1`

### 2. NT8 playback UI control
- Opening Playback windows
- loading playback state
- play / pause / step / speed / rewind / forward
- currently only partially mapped through Hermes experimental scripts

### 3. DEEP6 Python replay/backtest engine
- `deep6/backtest/*`
- `deep6/api/routes/replay.py`
- dashboard replay state and controllers
- used for deterministic replay research, scorer validation, and API/dashboard replay

Use the correct layer for the job.

## Existing Production-Grade Assets

| Purpose | Path |
|---|---|
| Native NT8 replay downloads | `C:\Users\Tea\DEEP6\ninjatrader\scripts\nt8-replay-download.ps1` |
| Basic NT8 UI helper | `C:\Users\Tea\DEEP6\ninjatrader\scripts\nt8-ui.ps1` |
| Replay protocol and evaluation | `C:\Users\Tea\DEEP6\docs\FOOTPRINT-REPLAY-EVAL-SPEC.md` |
| NT8 setup notes on Tick Replay | `C:\Users\Tea\DEEP6\ninjatrader\docs\SETUP.md` |
| Test-side deterministic session replay | `C:\Users\Tea\DEEP6\ninjatrader\tests\SessionReplay\CaptureReplayLoader.cs` |
| Live session capture for replay | `C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\CaptureHarness.cs` |
| Python replay session orchestrator | `C:\Users\Tea\DEEP6\deep6\backtest\session.py` |
| Python replay/backtest orchestrator | `C:\Users\Tea\DEEP6\deep6\backtest\research_runner.py` |
| Replay API routes | `C:\Users\Tea\DEEP6\deep6\api\routes\replay.py` |
| Backtest API routes | `C:\Users\Tea\DEEP6\deep6\api\routes\backtest.py` |
| Dashboard replay state | `C:\Users\Tea\DEEP6\dashboard\store\replayStore.ts` |
| Dashboard replay controller | `C:\Users\Tea\DEEP6\dashboard\hooks\useReplayController.ts` |

## Existing Experimental Playback-Control Assets

These are useful references, but they are not yet the same thing as a hardened production skill:

- `C:\Users\Tea\DEEP6\.hermes\tmp\toggle-playback-connection.ps1`
- `C:\Users\Tea\DEEP6\.hermes\tmp\toggle-playback-connection2.ps1`
- `C:\Users\Tea\DEEP6\.hermes\tmp\inspect-playback-window.ps1`
- `C:\Users\Tea\DEEP6\.hermes\tmp\inspect-replay-control-patterns.ps1`
- `C:\Users\Tea\DEEP6\.hermes\tmp\inspect-replay-control-patterns2.ps1`
- `C:\Users\Tea\DEEP6\.hermes\tmp\read-replay-selector-values.ps1`
- `C:\Users\Tea\DEEP6\.hermes\tmp\test-set-replay-values.ps1`
- `C:\Users\Tea\DEEP6\.hermes\tmp\test-sendkeys-replay-values.ps1`
- `C:\Users\Tea\DEEP6\.hermes\tmp\open-select-report-replay.ps1`
- `C:\Users\Tea\DEEP6\.hermes\tmp\poll-continue-replay.ps1`

Use them as probes and references when control automation needs to be extended.

## Download Workflow

Production path for native NT8 replay downloads:

1. Ensure NT8 is running.
2. Run `nt8-replay-download.ps1`.
3. Open `Tools > Historical Data` through UIAutomation.
4. Expand `Get Market Replay data`.
5. Select instrument + contract.
6. Set replay date or date range.
7. Click download.
8. Verify `.nrd` file under:
   `C:\Users\Tea\Documents\NinjaTrader 8\db\replay\<instrument contract>\YYYYMMDD.nrd`

The script already handles:
- contract enumeration
- date-range iteration
- stable file detection
- weekend skip handling
- disabled-button diagnostics
- force re-download

## Playback Control Responsibilities

This skill should reason about these operator actions even when the underlying automation is still evolving:

- open Playback window
- determine if NT8 is in playback mode or live mode
- load or select a replay session/contract/date
- start / pause playback
- set speed
- step forward
- step backward or rewind to known earlier state
- jump to a bar/time/session position
- detect end-of-session or stopped state

## Important Practical Boundary: Rewind

True rewind behavior in NT8 is often not the same as a clean in-memory reverse step.

Treat rewind as one of three possible operations, depending on what the UI actually supports:

1. **Step backward** — a small reverse control if available
2. **Jump back to a prior time/bar** — selector-based repositioning
3. **Restart playback from session start and fast-forward back to target** — fallback when reverse stepping is weak or unavailable

Do not assume reverse controls are reliable until verified in the current UI state.

## Suggested Operator Workflow Categories

### A. Download replay data only
Use when the user just needs `.nrd` replay files.

Primary asset:
- `nt8-replay-download.ps1`

### B. NT8 playback session control
Use when the user wants to operate NT8 playback itself.

Checklist:
1. confirm replay data exists for the requested contract/date
2. open playback controls
3. confirm loaded contract/date/session
4. verify current playback state
5. apply play/pause/speed/step/rewind action
6. verify resulting state visually or through UI state

### C. DEEP6 deterministic replay / backtest research
Use when the user wants repeatable event-driven replay, metrics, or API/dashboard replay rather than NT8 UI playback.

Primary assets:
- `deep6/backtest/session.py`
- `deep6/backtest/research_runner.py`
- `deep6/api/routes/replay.py`
- `deep6/api/routes/backtest.py`
- dashboard replay store/controller

### D. NT8-to-DEEP6 parity validation
Use when the user wants to compare NT8 replay behavior to DEEP6 replay outputs.

Primary references:
- `ninjatrader/tests/SessionReplay/CaptureReplayLoader.cs`
- `docs/FOOTPRINT-REPLAY-EVAL-SPEC.md`

## Known Operator Pitfalls

1. **Tick Replay vs Playback are not the same thing**
   - Tick Replay is a chart/data-series setting for historical tick-based processing.
   - Playback is an NT8 replay session/control mode.

2. **Download success does not mean playback is loaded**
   - `.nrd` existence only proves the file is present.
   - Playback still has to select and load the right contract/date.

3. **Dashboard replay controls are not NT8 playback controls**
   - `replayStore.ts` and `useReplayController.ts` are DEEP6 dashboard-side replay mechanisms, not direct NT8 UI control.

4. **Rewind may be synthetic**
   - In some workflows, rewind means restart + jump/fast-forward.

5. **Historical footprint visibility may still depend on Tick Replay or chart configuration**
   - Use `SETUP.md` rules when replay visuals look wrong.

## Routing to Other Skills

- on-chart correctness after playback changes → `nt8-chart-verification`
- broken indicator/strategy code discovered during replay work → `nt8-fix`
- general NT8 UI/menu help → `nt8-expert`
- deterministic research replay and metrics → Python replay/backtest stack

## Recommended Starting Commands / Assets

### Download replay data
Use:
`C:\Users\Tea\DEEP6\ninjatrader\scripts\nt8-replay-download.ps1`

### Inspect current playback UI state
Use the probe scripts in:
`C:\Users\Tea\DEEP6\.hermes\tmp\`

### Run deterministic replay/backtest research
Use:
- `deep6/backtest/session.py`
- `deep6/backtest/research_runner.py`
- replay/backtest API routes

## Skill Boundary Summary

This skill is the **operator brain** for replay and playback.

It does not replace:
- `nt8-chart-verification` for final visual acceptance
- `nt8-fix` for code repair
- the Python replay/backtest engine for deterministic research

It decides which replay layer is required, then drives the correct one.
