## 2026-05-29
- `gex_terminal.engine.analyzer.GEXAnalyzer` uses FlashAlpha as the primary regime source and Massive as a cross-validation source for gamma flip and wall levels.
- Confidence is more stable when derived from `base_confidence × source_agreement × health × freshness` plus a bounded agreement bonus instead of a simple regime-only mapping.
- Minor flip drift under 100 NQ points avoids noisy `material_change` triggers and keeps downstream interpreter calls selective.
- `gex_terminal.engine.interpreter.ClaudeInterpreter` should gate every Claude call behind `material_change` plus a daily ET budget reset, then reuse the last `ClaudeNarrative` when calls are skipped or fail.
- Using a JSONL audit log with token counts and per-call cost keeps interpreter cost tracking lightweight and matches the repo's existing budget-tracker pattern.
- `gex_terminal.engine.orchestrator.GEXOrchestrator` needs `asyncio.gather(..., return_exceptions=True)` at the polling layer so unexpected adapter exceptions degrade into `SourceHealth(status="error")` snapshots instead of aborting the analytics loop.
- Injecting adapters, analyzer, interpreter, and broadcast callback into the orchestrator constructor makes the 30-second loop easy to unit test without touching real APIs or FastAPI state.

- GEX ingest endpoint can be tested through the full FastAPI app, but app import had to be made resilient to missing optional sweep deps (`optuna`) by lazy-loading sweep helpers.
- `gex_terminal.engine.deep6_bridge.DEEP6Bridge` should stay HTTP-only and fail fast on both POST `/api/gex/ingest` and GET `/api/v3/bias`, returning booleans/`None` tuples instead of bubbling exceptions into the orchestration loop.
- Feeding DEEP6 with `analysis.levels.model_dump()` is enough for the current bridge contract; the bias engine only requires the integer score contract while the detail blob can remain a lightweight raw context payload.

- `python -m gex_terminal --dry-run` prints the validated config summary and exits 0 even when all API keys are unset, so the launch script can safely use it as a preflight gate.

- `UnusualWhalesAdapter.poll()` already degrades to `SourceHealth(status="pending")` with empty levels when `uw_api_key` is unset, so the orchestrator can always publish a `dark_pool` snapshot payload without making UW mandatory.
- Keeping UW polling as a third staggered adapter (T+10s on cycle 1) preserves the existing FlashAlpha-first / Massive-second cadence while surfacing `unusual_whales` health in the footer independently of core GEX analysis.
- `terminalreporter.write_line(...)` from a pytest test body is enough to force metric lines like overall/per-regime accuracy into normal `pytest -v` output without needing `-s`.
- `GEXAnalyzer` currently maps `FlashAlphaResult.dealer.regime` directly to direction when confidence stays above 50, so replay fixtures should measure regime classification quality and catastrophic overconfidence rather than intraday sequencing nuance.

- NT8 bridge is best treated as a non-fatal sidecar: missing script or bridge crash should not block UI startup.
- Piping bridge stdout/stderr with a prefix keeps console logs readable while preserving backend logs separately.

## 2026-05-31
- `nq_atlas.flow.FlowEngine` can be reused inside `gex_terminal.engine.adapters.massive.MassiveAdapter` by feeding each contract's `last`/`bid`/`ask`/`volume`/`call_put` fields from the fetched chain, matching the existing `nq_atlas.orchestrator.compute_loop` pattern.
- Flow confidence adjustments should only run when real flow is present; treating the default `flow_z_score=0.0` neutral fallback as live flow incorrectly penalizes confidence by 5 points.
- Keeping raw flow direction separate from the rendered `FlowSummary.direction` allows the analyzer to expose true signed-premium bias without breaking the prior regime-based fallback display when flow is absent.
- FlashAlpha `dealer.net_vex` / `dealer.net_chex` are sufficient for analyzer-side alignment scoring; no separate vanna/charm engine invocation is needed inside `gex_terminal`.
- Massive `raw_gex_result.by_expiry["0DTE"]` is a useful secondary sanity check: if same-day GEX fights the broader regime, analyzer confidence should be discounted even when FlashAlpha regime stays unchanged.
- Last-hour ET charm drift is best handled as a small additive modifier gated by meaningful 0DTE share, so late-session directional drift strengthens or weakens conviction without changing the analyzer API.

