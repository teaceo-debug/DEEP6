# Draft: Standard Deviation Anchor AI

## Requirements (confirmed)
- Product: AI-assisted indicator for human-style standard deviation swing anchoring.
- Core behavior: find the last clear opposite-direction manipulation leg before displacement.
- Anchor must attach wick-to-wick like a human drawing a fib/deviation tool.
- Bullish anchor: manipulation low wick -> manipulation-leg high wick before displacement confirmation.
- Bearish anchor: manipulation high wick -> manipulation-leg low wick before displacement confirmation.
- Plot only when confidence > 70.
- Reject choppy/unclear/forced structures and show "No valid manipulation leg detected."
- Support multi-timeframe clarity, preferring cleaner 5m/15m structure over messy 1m when needed.
- Visual outputs requested: anchor leg, anchor endpoints, -2/-2.5/-4 levels, -2 to -2.5 zone, status/confidence/timeframe labels.
- Desired system architecture: deterministic swing engine + AI visual validation + live recalibration + screenshot training loop.
- Phased vision: manual labeling skill, rule-based indicator, AI validation layer, live session agent.
- User wants the AI to behave like a sophisticated standard deviation expert that is constantly watching the TradingView chart and continuously adjusting levels.
- User wants the visual representation to stay directly on the TradingView chart and remain easy to understand.
- User wants the final behavior to mimic the original human-style/youtuber workflow, not drift into generic quant logic.
- User wants the system to leverage skill-based training, potentially as a dedicated HERMES standard-deviation expert skillset.
- User is open to additional research and explicit skill-building if needed to achieve visual anchoring quality.
- User explicitly does NOT want prior trading/anchor business logic reused. Reuse only integration patterns/platform scaffolding where necessary, while keeping anchor logic faithful to this new plan alone.

## Technical Decisions
- Primary target platform: TradingView first.
- First milestone scope: full hybrid system, not just labeling or indicator-only MVP.
- Verification strategy: tests-after + chart QA.
- Strong architecture recommendation from research: deterministic anchor engine owns candidate generation; AI validates/vetoes/ranks but should not silently define anchors in live mode.
- Strong platform recommendation: TradingView should be treated as deterministic chart/alert surface with external AI companion if visual validation is required.
- AI validation authority: external veto sidecar.
- Repaint policy: bar-confirmed only.
- MTF authority: 1m primary, higher timeframes provide context/confidence rather than override.
- Deterministic setup taxonomy for v1: narrow MVP focused on the single core pattern — last clean opposite-direction swing before displacement.
- Deterministic displacement confirmation for v1: local structure break plus impulsive candle/range expansion rules.
- New emphasis: AI architecture must preserve the original anchor logic while adding continuous chart watching, sidecar validation, and chart-visible updates.
- TradingView chart update authority: Pine-only drawing. HERMES governs approvals/state but Pine remains the sole on-chart drawer.
- Prior-code reuse rule: do not import old anchor-selection/business logic; only borrow project infrastructure patterns for placement, transport, and chart-control workflows.

## Research Findings
- Repo fit: `deep6/` is the current canonical implementation home; `deep6v2/` is a cleaner future scaffold.
- Existing closest logic: `deep6/bias_engine/ict_concepts.py` contains BOS/CHoCH, liquidity pool, and OTE-style structure logic.
- Existing runtime pattern: backend computes semantic objects, frontend renders typed payloads (`deep6/api/schemas.py`, `dashboard/types/deep6.ts`, `dashboard/components/footprint/*`).
- Existing level/zone architecture: `deep6/engines/level_factory.py`, `deep6/engines/vp_context_engine.py`, and dashboard zone overlays provide the best integration precedent.
- Existing screenshot/AI review pattern: `deep6/copilot/vision.py`, `deep6/copilot/vision_analysis.py`, `deep6/copilot/session.py`, and `deep6v2/tradingview/*`.
- TradingView constraint: Pine cannot call external AI directly or ingest live model outputs natively; AI must operate as a sidecar/companion workflow.
- TradingView rendering pattern: use native lines/labels/boxes with time-based anchoring and explicit object lifecycle management.
- Key risk: without a formal anchor lifecycle (`candidate`, `confirmed`, `active`, `invalidated`, `superseded`) the indicator will either repaint too much or feel late.
- Key risk: screenshot-only training is unsafe unless each image is paired with structured decision-time state to avoid hindsight leakage.

## Open Questions
- What constitutes displacement and break of structure in deterministic terms?
- Where should screenshot dataset live and how should labels be stored?
- Is AI allowed to veto anchors live, or only annotate/rank them?

## Scope Boundaries
- INCLUDE: human-style anchor selection, confidence scoring, strict rejection logic, deviation projection, AI review workflow.
- EXCLUDE: ATM/ATR/VWAP/volatility-band style forecasting approaches.
