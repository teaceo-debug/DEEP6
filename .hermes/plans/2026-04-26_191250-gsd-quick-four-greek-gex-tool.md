# GSD Quick — Four-Greek GEX/VEX/DEX/CHEX Tool

Status: execution kickoff
Source plan: ad-hoc user request in current session

Goal
- Create a Python service that computes and exports four-greek exposure levels from options chain data.
- Create a NinjaTrader 8 indicator that reads the exported JSON and renders all four exposure groups with actionable labels.
- Deploy to NT8, compile, and fix any errors.

Execution scope for this pass
1. Inspect existing DEEP6 GEX code and repo conventions.
2. Create tests for core Python math/JSON behavior.
3. Implement `scripts/gex_service.py`.
4. Implement `ninjatrader/Custom/Indicators/DEEP6/GEXCommand.cs`.
5. Deploy and compile in NinjaTrader; fix errors.
6. Summarize gaps / next improvements.

Constraints
- Keep implementation side-by-side with existing indicators; do not replace prior GEX indicator files.
- Use a separately named NT8 indicator/class/file.
- Prefer local JSON handoff between Python and NT8.
- Be conservative about vendor/API assumptions and add stale-data handling.

Notes
- User provided a detailed behavior spec but not source files; implementation will be created from the spec.
- NT8 host compile is the final validation gate.
