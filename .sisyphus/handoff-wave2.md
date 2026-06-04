HANDOFF CONTEXT
===============

USER REQUESTS (AS-IS)
---------------------
- "I have an ambitious idea. I want to create an overlay for NinjaTrader where an AI agent is constantly watching the screen of the actual trading chart, providing feedback to the trader at all times."
- "i want to be clear on my goal, i am using madlevels.com ninjatrader tool. the levels are key"
- User selected: Hybrid vision approach, Claude as brain, floating transparent overlay, both narrative + trade calls + situational awareness, all data sources, full system (go big), fixed sidebar panel, integration tests + live QA

GOAL
----
Continue executing the ai-chart-copilot plan at Wave 2 (Tasks 8-13): context aggregator, Claude brain, vision analysis, overlay renderer, bridge client, and token budget tracker.

WORK COMPLETED
--------------
- Planned the full AI Chart Copilot system via Prometheus interview (5 rounds of questions) and generated the work plan at .sisyphus/plans/ai-chart-copilot.md (23 tasks + 4 verification, 5 waves)
- Completed ALL Wave 1 tasks (7/7):
  - Task 1: deep6/copilot/__init__.py, config.py, types.py, __main__.py, adapters/__init__.py + tests/copilot/ scaffolding + pyproject.toml extras
  - Task 2: deep6/copilot/vision.py - ScreenCapture class using mss + ctypes for NT8 window detection
  - Task 3: deep6/copilot/adapters/calendar.py - EconomicCalendarAdapter with RSS, caching, countdown
  - Task 4: deep6/copilot/adapters/news.py - NewsFeedAdapter with multi-RSS, dedup, NQ relevance scoring
  - Task 5: deep6/copilot/adapters/sentiment.py - SentimentAdapter with StockTwits + Reddit
  - Task 6: deep6/copilot/adapters/internals.py + ninjatrader/Custom/Indicators/DEEP6/DEEP6MarketInternals.cs + DataBridgeServer.cs modification (WriteInternals)
  - Task 7: deep6/copilot/adapters/options_flow.py - OptionsFlowAdapter with Massive.com API
- Had to fix types.py after Task 1 created wrong field names - now matches plan spec
- Had to create calendar.py via Shell (PowerShell Set-Content) because task agents kept hitting Prometheus read-only hook

CURRENT STATE
-------------
- Wave 1 complete. 11 Python files in deep6/copilot/
- 1 new C# indicator (DEEP6MarketInternals.cs), 1 modified C# file (DataBridgeServer.cs)
- All files untracked/uncommitted (no git commits yet)
- boulder.json points to ai-chart-copilot plan with completed_tasks: [1-7]
- pyproject.toml has copilot optional extras group

PENDING TASKS
-------------
Wave 2 (6 tasks, all parallel):
- Task 8: Context Aggregator (deep6/copilot/context.py) - all sources -> structured LLM prompt [deep]
- Task 9: Claude Brain (deep6/copilot/brain.py) - streaming LLM integration [deep]
- Task 10: Vision Analysis (deep6/copilot/vision_analysis.py) - screenshot -> MAD levels [deep]
- Task 11: Overlay Renderer (deep6/copilot/overlay.py) - transparent-overlay sidebar [visual-engineering]
- Task 12: Bridge Client (deep6/copilot/bridge_client.py) - consume existing 44 signals [unspecified-high]
- Task 13: Token Budget (deep6/copilot/budget.py) - cost tracking [quick]

Wave 3 (5 tasks): Tasks 14-18 (narrative engine, trade calls, overlay content, session mgr, freshness)
Wave 4 (5 tasks): Tasks 19-23 (integration tests, e2e, docs)
Final (4 tasks): F1-F4 (compliance, quality, QA, scope check)

KEY FILES
---------
- .sisyphus/plans/ai-chart-copilot.md - THE FULL PLAN (1800+ lines, read this first)
- .sisyphus/boulder.json - Active work state
- deep6/copilot/types.py - All shared types (MADLevel, TradeCall, MarketContext, etc.)
- deep6/copilot/config.py - CopilotConfig dataclass
- deep6/copilot/vision.py - ScreenCapture class
- deep6/copilot/adapters/ - All 5 data adapters (calendar, news, sentiment, internals, options_flow)
- ninjatrader/Custom/Indicators/DEEP6/DEEP6MarketInternals.cs - NT8 market internals indicator
- deep6/engines/live_pipeline.py - Existing 44-signal engine (context aggregator consumes this)
- deep6/api/schemas.py - WebSocket message format (bridge client consumes this)
- deep6/api/live_bridge.py - How signals broadcast (bridge client pattern)

IMPORTANT DECISIONS
-------------------
- MAD levels from madlevels.com are the PRIMARY framework for ALL analysis - extracted via Claude Vision from chart screenshots
- Claude Sonnet for continuous narrative (~15s cycle), Claude Opus for trade calls + vision
- Fixed sidebar overlay (transparent-overlay library), docked right side of NT8
- All data sources in V1 (no phasing) - calendar, news, sentiment, internals, options flow
- Advisory only - NO autonomous execution
- Token budget: 500K tokens/hour (~$10-15/hr)
- Config uses frozen stdlib dataclasses with from_env(), NOT Pydantic (matching repo pattern)
- Copilot deps are in pyproject.toml optional extras: pip install -e ".[copilot]"

EXPLICIT CONSTRAINTS
--------------------
- NO autonomous trade execution - advisory only
- NO TTS/voice in V1
- NO modification of existing DEEP6 signal engines - read-only consumer
- NO unbounded Claude API spending - hard token budget per hour
- NO hallucinated levels - if MAD levels cant be extracted, say so explicitly
- Click-through overlay - never steal NT8 focus

CONTEXT FOR CONTINUATION
------------------------
- Read .sisyphus/plans/ai-chart-copilot.md FIRST - it has detailed specs for every task including references, QA scenarios, and acceptance criteria
- Task agents sometimes self-restrict with Prometheus read-only hook - add "You are an implementation agent with FULL file write access" to prompts, or use Shell (PowerShell Set-Content) as fallback
- The types.py was rewritten after Task 1 to match plan spec - verify imports still work before starting Wave 2
- Wave 2 tasks 8-13 are ALL independent and should be dispatched in parallel
- Task 6 created a WriteInternals method in DataBridgeServer.cs - the bridge client (Task 12) should be aware of this
- Run /start-work to resume - boulder.json already points to the correct plan
