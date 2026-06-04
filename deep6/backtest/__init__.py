"""DEEP6 backtest engine core.

Replay historical Databento MBO data through the exact same signal pipeline
the live Rithmic feed drives. Components:

- clock:        Clock protocol + WallClock (live) / EventClock (replay)
- mbo_adapter:  FeedAdapter protocol + MBOAdapter (Databento MBO → on_tick/on_dom)
- result_store: DuckDB-backed per-bar/per-trade/per-run writer
- session:      ReplaySession orchestrator (async context manager)
- config:       BacktestConfig (pydantic) + YAML loader
- research_runner: replay-backed orchestration for API/CLI research runs
"""

from deep6.backtest.research_runner import ReplayRunRequest, ReplayRunResult, ResearchRunner

__all__ = ["ReplayRunRequest", "ReplayRunResult", "ResearchRunner"]
