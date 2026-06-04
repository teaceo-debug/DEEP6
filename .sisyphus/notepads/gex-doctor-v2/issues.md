## 2026-05-29
- `MassiveResult` currently exposes GEX levels but not dedicated flow metrics, so analyzer flow output is a conservative synthesized summary rather than a true tape-derived flow state.
- WSL test environment still emits `PytestConfigWarning: Unknown config option: asyncio_mode`, indicating repo pytest config expects `pytest-asyncio` even though Task 9 no longer depends on that plugin.
- HERMES plain `pytest ...` used an environment without `pytest-asyncio`; `uv run pytest ...` was required to pick up the repo-managed test environment and execute async bridge tests successfully.

- Console rendering in the current shell showed the dry-run separator glyph as `�`, but the command still returned exit code 0 and validated config successfully.

- `gex_terminal/ui` had no local `node_modules`, so terminal UI verification required a local `npm install --no-package-lock` before `npm run build` could pass.
- HERMES/WSL test execution for Task 23 lacked optional `flashalpha` and `scipy` packages during pytest collection, so the replay test had to provide import shims locally to keep the fixture-based analyzer test isolated from SDK availability.
