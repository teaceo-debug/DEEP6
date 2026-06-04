# GEX Doctor Accuracy Upgrade — Learnings

## Key Files
- analyzer.py: C:\Users\Tea\DEEP6\gex_terminal\engine\analyzer.py
- orchestrator.py: C:\Users\Tea\DEEP6\gex_terminal\engine\orchestrator.py
- flashalpha adapter: C:\Users\Tea\DEEP6\gex_terminal\engine\adapters\flashalpha.py
- massive adapter: C:\Users\Tea\DEEP6\gex_terminal\engine\adapters\massive.py
- HMM: C:\Users\Tea\DEEP6\deep6\ml\hmm_regime.py
- magnet scorer: C:\Users\Tea\DEEP6\gexdoctor\monitor\magnet_scorer.py
- PO3: C:\Users\Tea\DEEP6\deep6\bias_engine\po3_detector.py
- flow: C:\Users\Tea\DEEP6\nq_atlas\flow.py
- vanna_charm: C:\Users\Tea\DEEP6\nq_atlas\vanna_charm.py
- nq_mapper: C:\Users\Tea\DEEP6\nq_atlas\nq_mapper.py
- UW adapter: C:\Users\Tea\DEEP6\gex_terminal\engine\adapters\unusual_whales.py
- NT8 indicator: C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\GEXTerminal.cs
- NT8 JSON: %USERPROFILE%\Documents\NinjaTrader 8\templates\DEEP6\gex_terminal_nt8.json

## Critical Facts
- DEFAULT_NQ_QQQ_RATIO = 38.5 is hardcoded — WRONG (actual ~40-41) → T1 fix
- VannaCharmEngine computed in nq_atlas but never passed to analyzer → T3
- FlowEngine computed in nq_atlas but never passed to analyzer → T2
- HMM regime detector exists at deep6/ml/hmm_regime.py (3 states: ABSORPTION_FRIENDLY, TRENDING, CHAOTIC) → T4
- Magnet scorer with anti-flicker at gexdoctor/monitor/magnet_scorer.py → T7
- UW API key: 258917e6-c161-4860-ba73-9f0d5b27d1a2 (saved to .env.gex_terminal)
- NT8 JSON is live (age 2-3s), flip=28393.75, cwall=28528.5, pwall=26950.0
- NT8 GEXTerminal.cs compiled and deployed
- 75 Python tests must pass throughout

## Architecture
- orchestrator.py calls: fa_adapter.poll() + massive_adapter.poll() → analyzer.analyze(fa, massive) → interpreter.interpret() → broadcast
- analyzer.analyze takes FlashAlphaResult + MassiveResult, produces AnalysisResult
- We need to add: FlowResult, VannaCharmResult, DailyOHLC for PO3, VIX level, HMM features
- Orchestrator needs to fetch these and pass them through

## Wave Dependencies
Wave 1 (parallel): T1, T4, T7, T8, T10
Wave 2 (after T1): T2, T3, T6
Wave 3 (after T2,T3,T4): T5
Wave 4 (after T5): T9

## 2026-05-31 — T4 HMM gate wiring
- `deep6/ml/hmm_regime.py` does not expose `predict(list[list[float]])`; the usable interface is `fit(signal_rows)` + `predict_current(recent_rows)` where each row is a dict with `total_score`, `engine_agreement`, `category_count`, and `direction`.
- The HMM is not self-trained on init; if `hmmlearn` is missing or the detector has never been fitted, `gex_terminal` must keep the regime at `UNKNOWN` instead of trusting the deep6 fallback state.
- `gex_terminal` can gate tradability safely by deriving a normalized 5-value feature vector in the orchestrator and letting a thin wrapper translate that into synthetic HMM signal rows.
- Verification path that worked: LSP clean on changed files, then Hermes-driven pytest using a temporary WSL venv at `/tmp/deep6-gex-test` because the base WSL Python lacked `pydantic-settings` and `pytest-asyncio`.

## 2026-05-31 — T5/T6 conviction + PO3
- `deep6.bias_engine.po3_detector` exposes `PO3BiasDetector`, not `PO3Detector`; `gex_terminal` needs a wrapper that maps `STRONG_BULL/BULL` → `BULLISH` and `STRONG_BEAR/BEAR` → `BEARISH`.
- Conviction integration is safest as a thin scorer module plus analyzer wiring; keep missing rivers fail-open and only force stand-aside when fewer than 2 rivers agree so baseline positive/negative gamma tests still preserve existing grades.
- Real UW context is only consumed by the live app after explicitly passing `dark_pool_direction` and `dp_levels_nq` from the orchestrator into `analyzer.analyze(...)`.

## 2026-06-01 — T9 Claude learner
- `ClaudeInterpreter._build_prompt()` is the narrowest integration point for recall context; prepending a `<recent_session_learnings>` block avoids touching the hardcoded system prompt while still biasing narrative generation.
- Session JSON should carry both top-level summary fields and per-cycle `levels` payloads; that gives daily recall enough structure for narrative improvement without replaying the full raw session.
- Hermes verification worked after bootstrapping the repo-local WSL `.venv` with pip and installing `gex_terminal/requirements.txt`, `pytest`, and `pytest-asyncio`; targeted learner/interpreter/orchestrator tests then passed.
