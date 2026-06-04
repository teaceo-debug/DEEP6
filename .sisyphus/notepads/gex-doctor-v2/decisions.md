## 2026-05-29
- Built analyzer output around existing `gex_terminal.schemas` objects only; no new snapshot contract was introduced.
- Kept the QQQ→NQ conversion configurable through `GEXAnalyzer(nq_qqq_ratio=...)` rather than hardcoding it into schemas or adapters.
- Derived `VannaCharmState` from FlashAlpha dealer `net_vex`/`net_chex` fields so the analyzer can publish exposure summaries without recomputing nq_atlas engines.
- Kept Task 9 on `claude-haiku-4-5-20251001` only and computed cost inline from Haiku token pricing instead of introducing a second budget abstraction.
- Wrote interpreter tests as synchronous `asyncio.run(...)` pytest cases so Task 9 verifies cleanly even in environments missing `pytest-asyncio`.
- Added orchestrator-level fallback builders for FlashAlpha and Massive results so the loop can survive even when injected test doubles or future adapters raise before returning their own degraded payloads.
- Wired FastAPI startup/shutdown through a lifespan context manager instead of importing server state into the orchestrator, preserving one-way dependency flow and avoiding circular imports.

- Keep GEX payloads in-memory only (`_latest_gex_doctor`) and surface them through `/api/gex/latest` plus `/api/v3/bias/domains` without changing the DomainScore contract.
- Injected `DEEP6Bridge` into `GEXOrchestrator` as an optional dependency so the live loop gets real HTTP integration by default while tests can still stub the bridge without hitting localhost.

- Kept the PowerShell launcher as a thin orchestration wrapper: validate with `--dry-run` first, then start backend and UI jobs only after config passes.

- Added `DarkPoolData` as an optional top-level `GEXTerminalSnapshot` field instead of folding UW levels into `GEXLevels`, keeping dark-pool context visually available in the terminal without implying equal analytical weight to FlashAlpha gamma levels.
- Kept orchestrator-level fallback handling for Unusual Whales parallel to FlashAlpha/Massive so injected test doubles or unexpected adapter failures still degrade into `SourceHealth(status="error")` snapshots rather than breaking the loop.
- Kept Task 23 fully fixture-driven by stubbing missing third-party imports inside `test_signal_quality.py` instead of weakening production adapter imports or introducing live/test-environment conditionals into app code.

- Added optional NT8 sidecar bridge spawn to desktop/main.js after backend health success so the main app still starts without the bridge.
- Bridge shutdown now runs before backend teardown and kills by PID on quit.

## 2026-05-31
- Extended `MassiveResult` with optional `flow_result` instead of changing the analyzer's positional signature, so existing `analyze(fa_result, massive_result)` callers remain valid while live flow data can ride alongside Massive chain output.
- Let `GEXAnalyzer.analyze()` prefer `massive_result.flow_result` when present and fall back to optional `flow_direction_raw` / `flow_z_score` kwargs, which keeps the analyzer ready for future orchestrator wiring without making flow mandatory today.
- Kept all new VEX/CHEX and 0DTE confidence logic inside `GEXAnalyzer` instead of mutating adapter contracts, preserving the existing `analyze()` signature and keeping FlashAlpha/Massive adapters as thin normalization layers.
- Computed `ZeroDTEState.pin_risk_score` in the analyzer when publishing the final snapshot, allowing normalized UI/risk output without requiring FlashAlpha to supply an extra field.
- Made FlashAlpha and Massive adapter imports lazy around optional third-party SDK dependencies so analyzer/unit tests can import result dataclasses without local FlashAlpha/SciPy installs.

