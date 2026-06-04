## 2026-05-12 Wave1 done

## 2026-05-12 Budget tracker
- Added a pure-stdlib `TokenBudgetTracker` with hourly reset, session/hour cost tracking, and JSONL logging to `~/.deep6/copilot_usage.jsonl`.
- Verified in WSL with `TokenBudgetTracker(500000)` that 800/200 usage leaves 499000 remaining and stays within budget.

## 2026-05-12 Brain integration
- `CopilotBrain` uses `anthropic.AsyncAnthropic` with `async with client.messages.stream(...)` for streaming narrative and `await stream.get_final_message()` to read final token usage.
- Vision prompts are sent as Anthropic message content blocks with a base64 PNG image block plus text context, and usage is logged + optionally forwarded to `TokenBudgetTracker.record_usage(...)`.
- ContextAggregator uses duck-typed adapters and cached fallbacks so copilot context keeps rendering when live bridge, news, or vision data is unavailable.

## 2026-05-12 TokenBudgetTracker v2
- Added `deep6/copilot/token_budget.py` with a thread-safe in-memory `TokenBudgetTracker` using hourly buckets keyed by UTC hour and a capped last-100 call log.
- `get_status()` now returns a `BudgetStatus` snapshot with used/remaining tokens, hourly call count, percent used, and next-hour reset time.
- Added tests for budget enforcement, hourly reset behavior, and over-budget call rejection; verified the module imports and the targeted pytest file passes.

## 2026-05-12 VisionAnalyzer
- Added `VisionAnalyzer` as a separate `vision_analysis.py` stage so screenshot capture stays isolated from Claude Vision parsing/caching concerns.
- Reliable MAD extraction fallback pattern: parse JSON defensively, clamp confidence, and cap confidence at 0.25 when MAD levels are not visible even if Claude claims high confidence.
- Cheap screenshot reuse works well as a two-layer strategy: SHA256 cache for identical PNG bytes, then Pillow diffing with a `<5%` threshold to skip near-identical frames without another API call.

- CopilotBrain uses a 10-message deque history, sync Anthropic client wrapped from async methods, token accounting with API-usage fallback to 4-chars-per-token estimates, and retry/backoff on 429/500-class failures.
- Mocked Anthropic tests can cover streaming by patching nthropic.Anthropic and supplying a sync context-manager stream object plus SimpleNamespace usage payloads.


## overlay.py � transparent-overlay API learnings (2026-05-12)

- transparent-overlay v2.7.2+ uses `Overlay(x, y, width, height)` for positioned windows
- Lifecycle: `start_layer()` / `stop_layer()` � NOT `start()`/`stop()`
- Render pattern: `frame_clear()` -> draw calls -> `signal_render()`
- Draw methods: `draw_text(x, y, text, color, font_size)`, `draw_rect(x, y, w, h, color)`, `draw_circle(x, y, r, color)`, `draw_line(x1, y1, x2, y2, color, thickness)`
- Color format: RGBA tuples `(R, G, B, A)` with 0-255 range
- Built-in window flags: `WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_NOACTIVATE` � click-through and no-focus-steal baked in
- No live repositioning API � must stop_layer + recreate to move
- Sprite TTL auto-cleanup: `sprite_ttl_seconds`, `enable_auto_ttl_cleanup`
- NT8 window: title varies by chart � use `EnumWindows` + partial "NinjaTrader" match, not `FindWindow`
- CalendarEvent.time is `str`, DataSourceStatus.last_update is `float` � NOT datetime objects

## 2026-05-12 VisionAnalyzer refresh
- Reworked deep6/copilot/vision_analysis.py around nthropic.AsyncAnthropic with cached token usage fields and defensive optional-import handling.
- Cache now short-circuits identical frames via SHA-256 of the base64 payload and reuses the previous ChartAnalysis for near-identical frames using a lightweight decoded-byte change ratio threshold of 5%.
- Claude responses are parsed from embedded JSON into ChartAnalysis/MADLevel tuples, with confidence clamped to <=0.3 when no MAD levels are extracted.

## 2026-05-12 Copilot test fixes
- Added a local `anthropic` stub module when the package is missing so `unittest.mock.patch("anthropic.Anthropic")` and `patch("anthropic.AsyncAnthropic")` work in tests.
- Renamed the vision parser entrypoint to `_parse_analysis` and aligned invalid JSON handling with the tests by returning `ChartAnalysis(confidence=0.0, raw_analysis=...)`.
- Replaced raw PNG byte diffing with Pillow pixel diffing so tiny image mutations stay below the similarity threshold and reuse the cached analysis.

## 2026-05-12 FreshnessTracker
- Added `deep6/copilot/freshness.py` with a pure-stdlib `FreshnessTracker` that stores per-source polling intervals, last-update timestamps, and propagated errors.
- Staleness is computed as `now - last_update > 2 * polling_interval_sec`, using UTC datetimes and a pluggable clock for deterministic tests.
- Default sources are pre-registered for calendar/news/sentiment/options flow/internals/bridge transports/vision, and the targeted pytest file passes.

## 2026-05-12 TradeCallEngine
- `TradeCallEngine` polls `bridge_client.get_latest_score()` every 5 seconds, only fires on `TYPE_A`/`TYPE_B` setups at score `>= 72`, and enforces a 300-second cooldown to stop rapid-fire advisory calls.
- Safe trade-call context pattern: build LLM context from `ContextAggregator`, append screenshot-derived MAD/price-action details, then inject screenshot base64 into `CopilotBrain.generate_trade_call(...)`.
- When vision cannot detect MAD levels, normalize the resulting `TradeCall` by capping confidence and appending an explicit rationale note instead of skipping the advisory cycle entirely.

## 2026-05-12 Documentation

- `deep6/copilot/.env.example` created with all 17 env vars, grouped by: required, external APIs, copilot settings, adapter toggles, and infrastructure.
- Env var names confirmed from `config.py`: all copilot settings use `COPILOT_` prefix (e.g. `COPILOT_SCREENSHOT_INTERVAL_SEC`), not the bare names listed in the task spec.
- `docs/copilot/README.md` created with 11 sections, ~270 lines. Covers overview, requirements, install, config table, usage flags, data sources, MAD levels, trade calls, overlay layout, cost estimates, and troubleshooting.
- Options flow adapter also accepts `FLASHALPHA_API_KEY` as a legacy alias for `MASSIVE_API_KEY`.
- Trade call cooldown is 300 seconds (5 minutes), not configurable via env.
- Trade calls expire from overlay after 600 seconds (10 minutes).
- RTH window: 7:30 AM to 3:00 PM Central Time, weekdays only.

 ## 2026-05-12 NarrativeEngine
 - Added `deep6/copilot/narrative.py` with an async loop that sleeps on `narrative_interval_sec`, skips outside RTH/budget limits, wraps slow context/screenshot/vision/stream work in `asyncio.wait_for(...)`, and logs+continues on iteration failures.
 - Periodic screenshot reuse works best by caching the last base64 payload and only refreshing when `screenshot_interval_sec` elapses; the same frame can still feed multiple narrative cycles in between.
 - Targeted pytest coverage for the engine should mock the async generator brain directly and use tiny loop intervals plus completion callbacks/events to prove streaming, RTH gating, and post-error recovery.

## 2026-05-12 Copilot smoke-test verification
- End-to-end smoke test passed without code changes: package import, explicit module import chain, adapter imports, CLI help, dry-run boot, and `pytest tests/copilot/ -q`.
- Current copilot test count is 93 passing tests, which exceeds the original 65+ expectation in the task brief.
- Import smoke checks returned immediately, so no circular import hang was observed in `deep6.copilot`.
- LSP reported zero copilot errors; only pre-existing Ruff unused-import warnings remain in `adapters/calendar.py`, `bridge_client.py`, and `overlay_content.py`.

## 2026-05-12 Copilot orchestration wiring
- `SessionManager` was not operational until it owned the real runtime graph: adapters, `ContextAggregator`, `NarrativeEngine`, `TradeCallEngine`, `OverlayContentRenderer`, `ScreenCapture`, and `VisionAnalyzer` all need to be instantiated from the session layer and stopped in reverse order.
- Safe adapter wiring pattern for optional integrations: instantiate each adapter behind per-feature config flags, catch import/init failures, and keep the copilot booting with missing adapters represented as `None` rather than crashing startup.
- Budget enforcement is most reliable at the actual Claude call sites: gate `VisionAnalyzer.analyze_chart(...)` before the API request, gate trade-call generation immediately before `CopilotBrain.generate_trade_call(...)`, and record the resulting token usage back into `TokenBudgetTracker` for future decisions.

## 2026-05-12 token_budget cleanup
- `deep6/copilot/budget.py` is the canonical tracker now; `TokenBudgetTracker` needed a compatibility shim for `can_make_call`, `get_status`, and `record_usage(call_type=...)` because the canonical implementation only exposed the cost-tracking API.
- When deleting a duplicate module, update both runtime imports and test imports, then keep the old call surface alive via package-level compatibility if hidden callers still expect it.


- 2026-05-12: The normal copilot session did not pass dedicated GEX/Kronos adapters into ContextAggregator, so collectors must support bridge_client fallback methods to avoid permanently unavailable source status.
## 2026-05-12
- Reverted `_collect_gex()` and `_collect_kronos()` to dedicated-adapter-only behavior in `deep6/copilot/context.py`; missing source is returned when the adapter is absent.
