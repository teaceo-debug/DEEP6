# NT8 Strategy Operations Knowledge Base

## Scope

This skill owns the operational side of NinjaTrader strategies:
- adding strategies to charts
- setting account and safety properties
- matching ATM templates by name
- enabling/disabling safely
- validating dry-run / sim-first posture

## Relevant Existing Assets

| Purpose | Path |
|---|---|
| UI helpers | `C:\Users\Tea\DEEP6\ninjatrader\scripts\nt8-ui.ps1` |
| Status checks | `C:\Users\Tea\DEEP6\ninjatrader\scripts\nt8-status.ps1` |
| ATM reference | `C:\Users\Tea\DEEP6\ninjatrader\docs\ATM-STRATEGIES.md` |
| Install guide | `C:\Users\Tea\DEEP6\ninjatrader\deploy\INSTALL-EVERYTHING.md` |

## Runtime Safety Rules

1. Prefer `Sim101` or the explicitly approved sim account first.
2. Confirm `EnableLiveTrading = False` when validating new strategy behavior.
3. Confirm account name exactly matches what the strategy expects.
4. Confirm ATM template names exist before enablement.
5. Confirm session limits, daily loss cap, and max trades/session are set coherently.

## DEEP6 ATM Templates

Recommended template set from `ATM-STRATEGIES.md`:

- `DEEP6_Absorption`
- `DEEP6_Exhaustion`
- `DEEP6_Confluence`
- `DEEP6_Practice`

These names matter because DEEP6 strategy properties reference templates **by exact name**.

## Known Failure Modes

### ATM template not found
Symptom:
- strategy falls back to a flat market order or logs that the template was not found

Action:
1. Check the ATM dropdown in NT8.
2. Create or re-save the template with the exact expected name.
3. Re-open strategy properties and verify the property value.

### Wrong account binding
Symptom:
- strategy appears enabled but cannot trade as expected, or binds to the wrong account

Action:
1. Open strategy properties.
2. Check approved account field and actual chart/account selection.
3. Rebind before re-enabling.

### Strategy enabled before compile/runtime validation
Symptom:
- runtime errors, missing indicators, or unsafe execution posture

Action:
1. Disable the strategy.
2. Run `nt8-build-verify` or `nt8-fix` first.
3. Return here only after code health is confirmed.

## Suggested Enablement Sequence

1. Confirm the strategy compiled cleanly.
2. Confirm required indicators are present on the chart.
3. Confirm ATM template names exist.
4. Confirm account = intended account.
5. Confirm safety properties:
   - live trading flag
   - max contracts
   - max trades per session
   - daily loss cap
   - session window / blackout window
6. Enable.
7. Watch Output Window and chart state immediately after enablement.

## Recommended Sim-First Posture

For DEEP6 onboarding and validation:

- start with `Sim101`
- start with `DEEP6_Practice` or other intentionally conservative ATM config
- do not promote to live until chart behavior and trade logs match expectations

## Related Skill Boundaries

- broken code → `nt8-fix`
- deploy/compile/install/screenshot → `nt8-build-verify`
- chart-side truth / indicator correctness → `nt8-chart-verification`
- platform corruption / reinstall → `nt8-install-repair`
