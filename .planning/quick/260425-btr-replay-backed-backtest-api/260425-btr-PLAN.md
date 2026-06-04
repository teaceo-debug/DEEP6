---
phase: quick-260425-btr
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - deep6/api/routes/backtest.py
  - deep6/backtest/session.py
  - deep6/backtest/result_store.py
  - deep6/backtest/config.py
  - deep6/backtest/__init__.py
  - tests/api/test_backtest.py
  - tests/backtest/test_research_runner.py
  - tests/backtest/test_backtest_api_replay_path.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "POST /backtest/run launches a replay-backed runner instead of the legacy scripts.backtest_signals path"
    - "A new Python ResearchRunner wraps ReplaySession and exposes run metadata/results suitable for API use"
    - "Phase 1 stays scoped to replay-backed orchestration and API plumbing, not the full fill-model/walk-forward roadmap"
    - "Tests prove the API path uses the replay stack and returns run-backed status/results"
  artifacts:
    - path: "deep6/backtest/research_runner.py"
      provides: "Replay-backed orchestration entrypoint for historical research runs"
    - path: "deep6/api/routes/backtest.py"
      provides: "Replay-backed HTTP launch/status surface"
    - path: "tests/backtest/test_research_runner.py"
      provides: "Research runner contract coverage"
    - path: "tests/backtest/test_backtest_api_replay_path.py"
      provides: "API integration proof that replay path is used"
---

<objective>
Implement Phase 1 of the credible backtesting plan: unify the public Python backtest API on top of the existing replay stack by introducing a replay-backed ResearchRunner, then update the FastAPI backtest route and tests so DEEP6 stops exposing the legacy bar-script path as the primary backtest interface.
</objective>

<context>
@deep6/api/routes/backtest.py
@deep6/backtest/session.py
@deep6/backtest/config.py
@deep6/backtest/result_store.py
@tests/api/test_backtest.py
@tests/backtest/test_replay_session.py
@.hermes/plans/2026-04-25_115008-deep6-credible-backtesting-system.md
</context>

<tasks>
1. Add a minimal replay-backed `ResearchRunner` abstraction around `ReplaySession`.
2. Add a request/summary contract suitable for the backtest API.
3. Refactor `/backtest/run` to dispatch `ResearchRunner` instead of the legacy scripts path.
4. Keep job-oriented polling semantics for compatibility, but populate results from the replay-backed runner.
5. Add targeted tests first, then implement until they pass.
</tasks>

<verification>
- `pytest tests/backtest/test_research_runner.py -q`
- `pytest tests/backtest/test_backtest_api_replay_path.py -q`
- `pytest tests/api/test_backtest.py -q`
</verification>
