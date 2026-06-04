# GSD Quick — GEXCommand + Massive Key Wiring + NT8 Install

Status: execution kickoff
Source: current chat request

Goal
- Wire the provided Massive.com API key into the local Python service setup safely.
- Review and fix `scripts/gex_service.py` and `ninjatrader/Custom/Indicators/DEEP6/GEXCommand.cs`.
- Deploy to NinjaTrader 8, compile, and validate installation readiness.

Execution scope
1. Inspect both source files and current key/config expectations.
2. Create local env/config for `MASSIVE_API_KEY` without hardcoding it into the indicator.
3. Fix compile/runtime issues in Python and NinjaScript.
4. Deploy to NT8 and run compile validation.
5. Summarize remaining product gaps or enhancements.

Constraints
- Do not hardcode the Massive key into NinjaScript/C# indicator code.
- Prefer local env/config for the Python service.
- Keep user-provided secrets out of docs and versioned example files.
